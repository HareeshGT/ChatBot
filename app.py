import asyncio
import json
import os
import threading
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
LLAMA_THREADS = max(1, int(os.getenv("LLAMA_THREADS", str(min(os.cpu_count() or 2, 4)))))
CONTEXT_SIZE = max(512, int(os.getenv("LLAMA_CONTEXT_SIZE", "2048")))

llm: Llama | None = None
inference_lock = threading.Lock()


def load_model() -> Llama:
    """Download the configured GGUF once into persistent storage and load it."""
    global MODEL_PATH
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

    print(f"Loading GGUF model from {MODEL_PATH}", flush=True)
    model = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=CONTEXT_SIZE,
        n_threads=LLAMA_THREADS,
        n_batch=256,
        verbose=False,
    )
    # Fail early if the model cannot run, rather than serving a misleading healthy status.
    model.create_chat_completion(
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=4,
        temperature=0,
    )
    print("GGUF model loaded and warm-up completed.", flush=True)
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

    # Keep the existing frontend contract: stream newline-delimited JSON chunks
    # shaped as {message:{content:...}, done:...} response chunks.
    messages: list[dict[str, str]] = []
    for item in payload.history[-40:]:
        role, content = item.get("role"), item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content[:20000]})
    messages.append({"role": "user", "content": payload.message})

    def stream() -> Iterator[bytes]:
        try:
            with inference_lock:
                chunks = model.create_chat_completion(
                    messages=messages,
                    stream=True,
                    max_tokens=512,
                    temperature=0.7,
                )
                for chunk in chunks:
                    choice = (chunk.get("choices") or [{}])[0]
                    content = (choice.get("delta") or {}).get("content")
                    if content:
                        item = {
                            "message": {"role": "assistant", "content": content},
                            "done": False,
                        }
                        yield (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")
                yield (json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n").encode("utf-8")
        except Exception as exc:
            yield (json.dumps({"error": f"Local model inference failed: {exc}"}, ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
