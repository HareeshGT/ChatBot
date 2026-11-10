#!/usr/bin/env bash
set -Eeuo pipefail

: "${OLLAMA_MODEL:=qwen2.5:0.5b}"
: "${OLLAMA_HOST:=127.0.0.1:11434}"
: "${PORT:=8000}"

echo "Starting Ollama on ${OLLAMA_HOST}..."
ollama serve &
OLLAMA_PID=$!

cleanup() {
  kill "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Waiting for Ollama API..."
for attempt in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
    break
  fi
  if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
    echo "Ollama exited unexpectedly." >&2
    exit 1
  fi
  sleep 2
done

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "Ollama did not become ready in time." >&2
  exit 1
fi

echo "Ensuring model is available: ${OLLAMA_MODEL}"
ollama pull "${OLLAMA_MODEL}"

echo "Starting ChatBot web server on port ${PORT}..."
exec uvicorn app:app --host 0.0.0.0 --port "${PORT}"
