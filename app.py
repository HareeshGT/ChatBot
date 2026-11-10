import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
from pydantic import BaseModel, Field

MODEL_REPO = os.getenv("MODEL_REPO", "Qwen/Qwen2.5-0.5B-Instruct-GGUF")
MODEL_FILE = os.getenv("MODEL_FILE", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", str(MODEL_DIR / MODEL_FILE)))
MODEL_NAME = MODEL_FILE
LLAMA_THREADS = max(1, int(os.getenv("LLAMA_THREADS", str(min(os.cpu_count() or 2, 2)))))
CONTEXT_SIZE = max(512, int(os.getenv("LLAMA_CONTEXT_SIZE", "2048")))
MAX_PROMPT_CHARS = max(1000, int(os.getenv("MAX_PROMPT_CHARS", "4500")))
MAX_HISTORY_MESSAGES = max(0, int(os.getenv("MAX_HISTORY_MESSAGES", "8")))
MAX_GENERATION_TOKENS = max(32, int(os.getenv("MAX_GENERATION_TOKENS", "256")))

llm: Llama | None = None
inference_lock = threading.Lock()


def build_messages(history: list[dict[str, str]], current_message: str) -> list[dict[str, str]]:
    """Keep recent context bounded so old chats cannot overwhelm the small context window."""
    current = current_message.strip()[-MAX_PROMPT_CHARS:]
    remaining = max(0, MAX_PROMPT_CHARS - len(current))
    recent: list[dict[str, str]] = []

    for item in reversed(history[-MAX_HISTORY_MESSAGES:]):
        role, content = item.get("role"), item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        content = content.strip()
        if remaining <= 0:
            break
        # Walk backwards so the newest turns consume the budget first.
        content = content[-remaining:]
        recent.append({"role": role, "content": content})
        remaining -= len(content)

    recent.reverse()
    recent.append({"role": "user", "content": current})
    return recent


def load_model() -> Llama:
    """Download the configured GGUF once into persistent storage and load it."""
    global MODEL_PATH
    started = time.perf_counter()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_PATH.is_file():
        print(f"Downloading GGUF model {MODEL_REPO}/{MODEL_FILE} into {MODEL_DIR}", flush=True)
        downloaded_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILE,
            local_dir=str(MODEL_DIR),
        )
        MODEL_PATH = Path(downloaded_path)

    if not MODEL_PATH.is_file():
        raise RuntimeError(f"GGUF model file was not found at {MODEL_PATH}")

    print(f"Loading GGUF model from {MODEL_PATH} with {LLAMA_THREADS} CPU threads", flush=True)
    model = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=CONTEXT_SIZE,
        n_threads=LLAMA_THREADS,
        n_threads_batch=LLAMA_THREADS,
        n_batch=128,
        use_mmap=True,
        verbose=False,
    )
    model.create_chat_completion(
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=4,
        temperature=0,
    )
    print(
        f"GGUF model ready in {time.perf_counter() - started:.2f}s "
        f"(context={CONTEXT_SIZE}, threads={LLAMA_THREADS}).",
        flush=True,
    )
    return model


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm
    # Downloading and loading are blocking native operations; keep them off the event loop.
    llm = await asyncio.to_thread(load_model)
    yield
    llm = None


app = FastAPI(title="Python GGUF ChatBot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    model: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/health")
async def health():
    if llm is None:
        raise HTTPException(status_code=503, detail="GGUF model is not loaded")
    return {
        "status": "ok",
        "engine": "llama-cpp-python",
        "model": MODEL_NAME,
        "models": [MODEL_NAME],
        "context_size": CONTEXT_SIZE,
        "cpu_threads": LLAMA_THREADS,
    }


@app.get("/api/models")
async def models():
    if llm is None:
        raise HTTPException(status_code=503, detail="GGUF model is not loaded")
    return {"models": [{"name": MODEL_NAME}], "default": MODEL_NAME}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    model = llm
    if model is None:
        raise HTTPException(status_code=503, detail="GGUF model is not loaded")

    messages = build_messages(payload.history, payload.message)

    def stream() -> Iterator[bytes]:
        started = time.perf_counter()
        first_token_at: float | None = None
        output_chunks = 0
        try:
            with inference_lock:
                chunks = model.create_chat_completion(
                    messages=messages,
                    stream=True,
                    max_tokens=MAX_GENERATION_TOKENS,
                    temperature=0.7,
                )
                for chunk in chunks:
                    choice = (chunk.get("choices") or [{}])[0]
                    content = (choice.get("delta") or {}).get("content")
                    if content:
                        now = time.perf_counter()
                        if first_token_at is None:
                            first_token_at = now
                        output_chunks += 1
                        item = {
                            "message": {"role": "assistant", "content": content},
                            "done": False,
                        }
                        yield (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")

            elapsed = time.perf_counter() - started
            first_delay = (first_token_at - started) if first_token_at is not None else elapsed
            print(
                f"Chat timing: first_token={first_delay:.2f}s total={elapsed:.2f}s "
                f"stream_chunks={output_chunks} prompt_chars={sum(len(m['content']) for m in messages)}",
                flush=True,
            )
            yield (json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n").encode("utf-8")
        except Exception as exc:
            print(f"Chat inference error after {time.perf_counter() - started:.2f}s: {exc}", flush=True)
            yield (json.dumps({"error": f"Local model inference failed: {exc}"}, ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
