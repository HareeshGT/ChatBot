import json
import os
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)

app = FastAPI(title="Local Ollama ChatBot")
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
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
        return {"status": "ok", "ollama": "connected", "model": DEFAULT_MODEL,
                "models": [item.get("name") for item in data.get("models", [])]}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=503, detail="Ollama is not reachable")


@app.get("/api/models")
async def models():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            return {"models": response.json().get("models", []), "default": DEFAULT_MODEL}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {exc}") from exc


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    model = (payload.model or DEFAULT_MODEL).strip()
    if not model:
        raise HTTPException(status_code=400, detail="A model is required")

    messages: list[dict[str, str]] = []
    # Only accept valid role/content pairs from the client history.
    for item in payload.history[-40:]:
        role, content = item.get("role"), item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content[:20000]})
    messages.append({"role": "user", "content": payload.message})

    async def stream() -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={"model": model, "messages": messages, "stream": True},
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        detail = body.decode("utf-8", errors="replace")
                        yield (json.dumps({"error": f"Ollama returned {response.status_code}: {detail}"}) + "\n").encode()
                        return
                    async for line in response.aiter_lines():
                        if line:
                            yield (line + "\n").encode()
        except httpx.HTTPError as exc:
            yield (json.dumps({"error": f"Could not connect to Ollama: {exc}"}) + "\n").encode()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
