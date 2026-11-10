#!/usr/bin/env sh
set -eu

: "${MODEL_REPO:=Qwen/Qwen2.5-0.5B-Instruct-GGUF}"
: "${MODEL_FILE:=qwen2.5-0.5b-instruct-q4_k_m.gguf}"
: "${MODEL_DIR:=/models}"
: "${MODEL_PATH:=${MODEL_DIR}/${MODEL_FILE}}"
: "${PORT:=8000}"

mkdir -p "${MODEL_DIR}"
echo "Starting Python ChatBot with llama-cpp-python."
echo "GGUF model: ${MODEL_REPO}/${MODEL_FILE}"
echo "Model storage: ${MODEL_PATH}"
echo "The model is downloaded to persistent storage and loaded by FastAPI on startup."

exec uvicorn app:app --host 0.0.0.0 --port "${PORT}"
