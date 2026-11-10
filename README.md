# Python GGUF ChatBot

A self-hosted web chatbot powered by **llama-cpp-python** and a local GGUF model. The FastAPI app loads the model directly into Python; there is no Ollama server and no external inference API.

## Features

- Responsive chat interface with streaming responses.
- Python-native inference through llama-cpp-python.
- Qwen 2.5 0.5B Instruct in Q4_K_M GGUF quantization.
- Conversation history passed to the model on each turn.
- Model downloaded once to a persistent model directory.
- Existing FastAPI endpoints and newline-delimited JSON streaming contract retained.
- No API key or hosted AI inference service required.

## Default model

- Repository: [Qwen/Qwen2.5-0.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF)
- File: `qwen2.5-0.5b-instruct-q4_k_m.gguf`
- Quantization: Q4_K_M
- File size: approximately 491 MB.

This is a compact model intended for CPU inference. It is much smaller than 3B models, but responses and reasoning are less capable than larger models. CPU speed depends on the Render instance's available compute.

## Run with Docker Compose

Requirements: Docker Engine/Desktop and Docker Compose. The first build compiles the CPU backend for llama-cpp-python; this may take several minutes. The first app startup downloads the GGUF model to the persistent volume and loads it into memory.

```bash
git clone https://github.com/HareeshGT/ChatBot.git
cd ChatBot
cp .env.example .env
docker compose up -d --build
```

Open **http://localhost:8000**.

Follow logs:

```bash
docker compose logs -f chatbot
```

Stop the service while keeping the downloaded model:

```bash
docker compose down
```

Remove the service and its downloaded model volume:

```bash
docker compose down -v
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MODEL_REPO` | `Qwen/Qwen2.5-0.5B-Instruct-GGUF` | Hugging Face repository |
| `MODEL_FILE` | `qwen2.5-0.5b-instruct-q4_k_m.gguf` | GGUF filename |
| `MODEL_DIR` | `/models` | Model directory; mount persistent storage here |
| `MODEL_PATH` | `/models/qwen2.5-0.5b-instruct-q4_k_m.gguf` | Full model path |
| `LLAMA_THREADS` | `4` | CPU inference threads |
| `LLAMA_CONTEXT_SIZE` | `2048` | Context window size |
| `PORT` | `8000` | Web server port |

Change model repository/file only if they refer to a compatible GGUF model. If changing the file, update `MODEL_PATH` to match.

## API endpoints

- `GET /api/health` — app and model readiness.
- `GET /api/models` — the configured model exposed to the frontend selector.
- `POST /api/chat` — streams newline-delimited JSON with `message.content` chunks, preserving the existing frontend contract.

Example:

```bash
curl -N http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Explain Docker in one paragraph","history":[]}'
```

## Deploy on Render

The included `render.yaml` deploys the main Dockerfile and mounts a **1 GB persistent disk at `/models`**. It uses a Standard web service plan as a starting point for CPU inference and model memory. Review Render's current plan limits and pricing before deploying.

1. Open the [Render dashboard](https://dashboard.render.com/).
2. Create/update a Blueprint from this repository and review `render.yaml`.
3. Confirm the service uses `./Dockerfile`, has the persistent disk mounted at `/models`, and has enough RAM for the model plus the Python process.
4. Deploy. The first startup downloads the GGUF model and loads it; later starts reuse the persistent file.
5. Check `https://YOUR-SERVICE.onrender.com/api/health`. A healthy response includes `"engine":"llama-cpp-python"`.

Render Free is not recommended for this configuration: its resource limits and lack of persistent disks can make local model inference unreliable. A small model still requires memory for the model, context/KV cache, and runtime.

## Troubleshooting

- Check logs in Render or run `docker compose logs -f chatbot`.
- Health endpoint: `curl http://localhost:8000/api/health`.
- If startup fails during model download, verify outbound access to Hugging Face and available disk space.
- If the model fails to load, verify the repository/file pair and ensure the service has sufficient memory.
- The first Docker build may take time because llama-cpp-python's CPU backend is compiled during image build.

## Security

The API does not include authentication. Before exposing it publicly, add authentication, request limits, and appropriate access controls. Prompts are processed locally by the running container, but the model file is downloaded from Hugging Face on initial startup.
