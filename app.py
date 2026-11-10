import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import httpx
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
MODEL_NAME = os.getenv("LOCAL_MODEL_LABEL", MODEL_FILE)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "local")
LLAMA_THREADS = max(1, int(os.getenv("LLAMA_THREADS", str(min(os.cpu_count() or 2, 2)))))
CONTEXT_SIZE = max(512, int(os.getenv("LLAMA_CONTEXT_SIZE", "2048")))
MAX_PROMPT_CHARS = max(1000, int(os.getenv("MAX_PROMPT_CHARS", "4500")))
MAX_HISTORY_MESSAGES = max(0, int(os.getenv("MAX_HISTORY_MESSAGES", "8")))
MAX_GENERATION_TOKENS = max(128, int(os.getenv("MAX_GENERATION_TOKENS", "2048")))
LOCAL_MAX_GENERATION_TOKENS = max(64, int(os.getenv("LOCAL_MAX_GENERATION_TOKENS", "512")))

PROVIDERS = {
    "openai": {
        "key": "OPENAI_API_KEY", "base": "https://api.openai.com/v1",
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "label": "OpenAI",
    },
    "groq": {
        "key": "GROQ_API_KEY", "base": "https://api.groq.com/openai/v1",
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), "label": "Groq",
    },
    "mistral": {
        "key": "MISTRAL_API_KEY", "base": "https://api.mistral.ai/v1",
        "model": os.getenv("MISTRAL_MODEL", "mistral-small-latest"), "label": "Mistral",
    },
    "gemini": {
        "key": "GEMINI_API_KEY", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), "label": "Google Gemini",
    },
    "anthropic": {
        "key": "ANTHROPIC_API_KEY", "base": "https://api.anthropic.com/v1",
        "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"), "label": "Anthropic",
    },
}
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_API_BASE = os.getenv("CUSTOM_API_BASE", "").rstrip("/")
CUSTOM_MODEL_NAME = os.getenv("CUSTOM_MODEL_NAME", "")
CUSTOM_MODEL_LABEL = os.getenv("CUSTOM_MODEL_LABEL", "Custom API model")

llm: Llama | None = None
inference_lock = threading.Lock()


GITHUB_URL_RE = __import__("re").compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/tree/([A-Za-z0-9._-]+))?(?:/[^\s]*)?", __import__("re").IGNORECASE)
REPO_FILE_PRIORITY = (
    "README.md", "pyproject.toml", "requirements.txt", "package.json",
    "Dockerfile", "docker-compose.yml", "render.yaml",
    "app.py", "main.py", "server.py", "index.js", "src/index.ts",
)


async def inspect_github_repository(message: str) -> str | None:
    """Fetch real public GitHub repository metadata, tree and key source files."""
    match = GITHUB_URL_RE.search(message)
    if not match:
        return None
    owner, repo_name, branch = match.groups()
    repo_name = repo_name.removesuffix(".git")
    if repo_name in {".", ".."}:
        return None
    api = "https://api.github.com"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    timeout = httpx.Timeout(20.0, connect=8.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            meta_response = await client.get(f"{api}/repos/{owner}/{repo_name}", headers=headers)
            if meta_response.status_code == 404:
                return f"GitHub repository inspection failed: {owner}/{repo_name} was not found or is private. Do not guess its contents."
            meta_response.raise_for_status()
            meta = meta_response.json()
            branch = branch or meta.get("default_branch", "main")
            tree_response = await client.get(
                f"{api}/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1", headers=headers
            )
            tree_response.raise_for_status()
            tree_data = tree_response.json()
            paths = [item["path"] for item in tree_data.get("tree", []) if item.get("type") == "blob"]
            if not paths:
                return f"GitHub repository {owner}/{repo_name} exists but its file tree is empty or unavailable."
            selected = []
            for priority in REPO_FILE_PRIORITY:
                found = next((p for p in paths if p.lower() == priority.lower()), None)
                if found and found not in selected:
                    selected.append(found)
            # Add likely source/config files so repo analysis is not based on README alone.
            source_ext = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".yaml", ".yml", ".toml")
            for path in paths:
                low = path.lower()
                if len(selected) >= 6:
                    break
                if low.endswith(source_ext) and not any(part in low for part in ("/node_modules/", "/.git/", "/dist/", "/build/")):
                    if path not in selected:
                        selected.append(path)
            chunks = [
                f"VERIFIED GITHUB REPOSITORY CONTEXT",
                f"Repository: {meta.get('html_url')}",
                f"Description: {meta.get('description') or 'No description provided'}",
                f"Default branch: {meta.get('default_branch')}",
                f"Branch inspected: {branch}",
                f"Visibility: {'private' if meta.get('private') else 'public'}",
                "Repository file tree (first 120 paths):",
                *[f"- {p}" for p in paths[:120]],
            ]
            total = sum(len(x) for x in chunks)
            for path in selected:
                if total > 7000:
                    break
                file_response = await client.get(
                    f"{api}/repos/{owner}/{repo_name}/contents/{path}",
                    params={"ref": branch}, headers=headers
                )
                if file_response.status_code != 200:
                    continue
                item = file_response.json()
                if item.get("encoding") != "base64" or not item.get("content"):
                    continue
                import base64
                content = base64.b64decode(item["content"]).decode("utf-8", errors="replace")
                content = content[:1200]
                section = f"\n--- FILE: {path} ---\n{content}"
                chunks.append(section)
                total += len(section)
            chunks.append(
                "\nINSTRUCTIONS: Use only this fetched repository evidence for claims about its implementation. "
                "If a needed file was not fetched, say so and request the specific path or inspect it before making claims. "
                "Do not claim to have modified, committed, deployed, or tested anything; this chat backend currently has read-only repository inspection."
            )
            return "\n".join(chunks)
    except Exception as exc:
        print(f"GitHub repository inspection error for {owner}/{repo_name}: {exc}", flush=True)
        return f"GitHub repository inspection could not be completed for {owner}/{repo_name}: {type(exc).__name__}. Do not invent repository details."


def build_messages(history: list[dict[str, str]], current_message: str) -> list[dict[str, str]]:
    current = current_message.strip()[-MAX_PROMPT_CHARS:]
    remaining = max(0, MAX_PROMPT_CHARS - len(current))
    recent: list[dict[str, str]] = []
    for item in reversed(history[-MAX_HISTORY_MESSAGES:]):
        role, content = item.get("role"), item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        if remaining <= 0:
            break
        content = content.strip()[-remaining:]
        recent.append({"role": role, "content": content})
        remaining -= len(content)
    recent.reverse()
    recent.append({"role": "user", "content": current})
    return recent


def load_model() -> Llama:
    global MODEL_PATH
    started = time.perf_counter()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if not MODEL_PATH.is_file():
        print(f"Downloading GGUF model {MODEL_REPO}/{MODEL_FILE} into {MODEL_DIR}", flush=True)
        MODEL_PATH = Path(hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILE, local_dir=str(MODEL_DIR)))
    if not MODEL_PATH.is_file():
        raise RuntimeError(f"GGUF model file was not found at {MODEL_PATH}")
    model = Llama(
        model_path=str(MODEL_PATH), n_ctx=CONTEXT_SIZE, n_threads=LLAMA_THREADS,
        n_threads_batch=LLAMA_THREADS, n_batch=128, use_mmap=True, verbose=False,
    )
    model.create_chat_completion(messages=[{"role": "user", "content": "Reply with OK."}], max_tokens=4, temperature=0)
    print(f"Local GGUF model ready in {time.perf_counter() - started:.2f}s", flush=True)
    return model


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm
    llm = await asyncio.to_thread(load_model)
    yield
    llm = None


app = FastAPI(title="Local and Cloud ChatBot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    model: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    provider: str | None = None
    api_key: str | None = Field(default=None, max_length=1000)
    api_base: str | None = Field(default=None, max_length=500)
    provider_model: str | None = Field(default=None, max_length=200)


def available_models():
    result = [{"name": "local", "label": f"Local · {MODEL_NAME}", "provider": "local"}]
    for provider, config in PROVIDERS.items():
        if os.getenv(config["key"]):
            result.append({
                "name": f"{provider}:{config['model']}",
                "label": f"{config['label']} · {config['model']}",
                "provider": provider,
            })
    if CUSTOM_API_KEY and CUSTOM_API_BASE and CUSTOM_MODEL_NAME:
        result.append({
            "name": f"custom:{CUSTOM_MODEL_NAME}",
            "label": f"{CUSTOM_MODEL_LABEL} · {CUSTOM_MODEL_NAME}",
            "provider": "custom",
        })
    return result


def ndjson(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")


def stream_local(messages: list[dict[str, str]]) -> Iterator[bytes]:
    model = llm
    if model is None:
        yield ndjson({"error": "Local model is not loaded"})
        return
    started = time.perf_counter()
    first_token_at = None
    try:
        with inference_lock:
            for chunk in model.create_chat_completion(
                messages=messages, stream=True, max_tokens=LOCAL_MAX_GENERATION_TOKENS, temperature=0.7,
            ):
                content = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                if content:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    yield ndjson({"message": {"role": "assistant", "content": content}, "done": False})
        elapsed = time.perf_counter() - started
        first_delay = first_token_at - started if first_token_at else elapsed
        print(f"Local chat timing: first_token={first_delay:.2f}s total={elapsed:.2f}s", flush=True)
        yield ndjson({"message": {"role": "assistant", "content": ""}, "done": True})
    except Exception as exc:
        print(f"Local inference error: {exc}", flush=True)
        yield ndjson({"error": "Local model inference failed. Check service logs."})


def stream_openai_compatible(base_url: str, api_key: str, model_name: str, messages: list[dict[str, str]]) -> Iterator[bytes]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model_name, "messages": messages, "stream": True, "temperature": 0.7, "max_tokens": MAX_GENERATION_TOKENS}
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            with client.stream("POST", url, headers={"Authorization": f"Bearer {api_key}"}, json=payload) as response:
                if response.is_error:
                    raw_detail = response.read().decode("utf-8", errors="replace")[:4000]
                    try:
                        parsed = json.loads(raw_detail)
                        error_obj = parsed.get("error", parsed)
                        if isinstance(error_obj, dict):
                            provider_message = error_obj.get("message") or error_obj.get("detail") or str(error_obj)
                            provider_code = error_obj.get("code") or error_obj.get("type")
                        else:
                            provider_message, provider_code = str(error_obj), None
                    except (json.JSONDecodeError, AttributeError):
                        provider_message, provider_code = raw_detail[:800], None
                    retry_after = response.headers.get("retry-after")
                    print(f"Provider error {response.status_code} code={provider_code} retry_after={retry_after}: {raw_detail}", flush=True)
                    if response.status_code == 429:
                        message = "Provider rate limit or quota reached."
                        if provider_message:
                            message += f" Details: {provider_message[:500]}"
                        if retry_after:
                            message += f" Retry after: {retry_after} seconds."
                        message += " Check your provider usage, billing/credits, and rate limits. You can switch to Local in the model selector."
                    elif response.status_code in (401, 403):
                        message = "Provider rejected the API key or access. Check that the key is valid and has permission for this model."
                        if provider_message:
                            message += f" Details: {provider_message[:400]}"
                    elif response.status_code == 404:
                        message = "Provider could not find this model or endpoint. Check the model ID and API base URL."
                        if provider_message:
                            message += f" Details: {provider_message[:400]}"
                    else:
                        message = f"Provider request failed ({response.status_code})."
                        if provider_message:
                            message += f" Details: {provider_message[:500]}"
                    yield ndjson({"error": message})
                    return
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                        content = (data.get("choices") or [{}])[0].get("delta", {}).get("content")
                        if isinstance(content, str) and content:
                            yield ndjson({"message": {"role": "assistant", "content": content}, "done": False})
                    except json.JSONDecodeError:
                        continue
        yield ndjson({"message": {"role": "assistant", "content": ""}, "done": True})
    except Exception as exc:
        print(f"Cloud provider connection error: {exc}", flush=True)
        yield ndjson({"error": "Could not connect to the selected AI provider. Check its configuration and try again."})


def stream_anthropic(model_name: str, api_key: str, messages: list[dict[str, str]]) -> Iterator[bytes]:
    system_text = "\n".join(m["content"] for m in messages if m["role"] == "system")
    chat_messages = [m for m in messages if m["role"] != "system"]
    payload = {"model": model_name, "messages": chat_messages, "max_tokens": MAX_GENERATION_TOKENS, "stream": True}
    if system_text:
        payload["system"] = system_text
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            with client.stream(
                "POST", "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=payload,
            ) as response:
                if response.is_error:
                    detail = response.read().decode("utf-8", errors="replace")[:1200]
                    print(f"Anthropic error {response.status_code}: {detail}", flush=True)
                    yield ndjson({"error": f"Anthropic request failed ({response.status_code}). Check API key, model name, and provider limits."})
                    return
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("type") == "content_block_delta":
                            content = data.get("delta", {}).get("text")
                            if content:
                                yield ndjson({"message": {"role": "assistant", "content": content}, "done": False})
                    except json.JSONDecodeError:
                        continue
        yield ndjson({"message": {"role": "assistant", "content": ""}, "done": True})
    except Exception as exc:
        print(f"Anthropic connection error: {exc}", flush=True)
        yield ndjson({"error": "Could not connect to Anthropic. Check its API key and configuration."})


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/health")
async def health():
    if llm is None:
        raise HTTPException(status_code=503, detail="Local GGUF model is not loaded")
    return {
        "status": "ok", "engine": "llama-cpp-python", "model": MODEL_NAME,
        "default_model": DEFAULT_MODEL, "available_models": len(available_models()),
        "context_size": CONTEXT_SIZE, "cpu_threads": LLAMA_THREADS,
    }


@app.get("/api/models")
async def models():
    choices = available_models()
    default = DEFAULT_MODEL if any(item["name"] == DEFAULT_MODEL for item in choices) else "local"
    return {"models": choices, "default": default}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    messages = build_messages(payload.history, payload.message)
    repository_prompt = payload.message + "\n" + "\n".join(
        item.get("content", "") for item in payload.history[-MAX_HISTORY_MESSAGES:]
        if item.get("role") == "user" and isinstance(item.get("content"), str)
    )
    repo_context = await inspect_github_repository(repository_prompt)
    if repo_context:
        messages.insert(0, {"role": "system", "content": repo_context})
    selected = payload.model or DEFAULT_MODEL
    if selected == "local":
        if llm is None:
            raise HTTPException(status_code=503, detail="Local model is not loaded")
        return StreamingResponse(stream_local(messages), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    provider = (payload.provider or "").lower()
    if not provider and ":" in selected:
        provider = selected.split(":", 1)[0].lower()
    if provider in PROVIDERS or provider == "custom":
        config = PROVIDERS.get(provider, {})
        model_name = (payload.provider_model or selected.split(":", 1)[-1]).strip()
        api_key = (payload.api_key or os.getenv(config.get("key", ""), "")).strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="Add an API key in Model settings before using this provider.")
        if provider == "anthropic":
            generator = stream_anthropic(model_name, api_key, messages)
        else:
            base_url = (payload.api_base or config.get("base") or CUSTOM_API_BASE).strip().rstrip("/")
            if provider == "custom" and not base_url:
                raise HTTPException(status_code=400, detail="Add an API base URL in Model settings.")
            generator = stream_openai_compatible(base_url, api_key, model_name, messages)
        return StreamingResponse(generator, media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    raise HTTPException(status_code=400, detail="Unknown model. Select Local or configure a provider in Model settings.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
