# Local Ollama ChatBot

A self-hosted web chat application powered by [Ollama](https://ollama.com/). Ollama runs **inside the same Docker container** as the application, on the machine hosting the container. The browser communicates with the Python backend; the backend communicates with Ollama over the container's loopback interface.

## Features

- Clean, responsive chat interface with streaming responses.
- Ollama model selector (lists models already installed).
- Configurable default model; automatically pulled on first startup.
- Conversation context sent to Ollama on each turn.
- Persistent model storage using a Docker named volume.
- No external AI API key or hosted inference service required.

## Default model

The default is `qwen2.5:0.5b`, a compact instruction-tuned model with an approximately **398 MB model download**. It is much smaller than the previous 3B model, though its answers will be less capable than larger models. See the [official Ollama model page](https://ollama.com/library/qwen2.5:0.5b-instruct).

## Run with Docker Compose (recommended)

Requirements: Docker Engine/Desktop and the Docker Compose plugin. The first build downloads Ollama and Python dependencies. The first startup downloads the configured model; allow time and disk space for it.

```bash
git clone https://github.com/HareeshGT/ChatBot.git
cd ChatBot
cp .env.example .env
docker compose up -d --build
```

Open **http://localhost:8000**.

To follow startup and model download logs:

```bash
docker compose logs -f chatbot
```

To stop the app without deleting downloaded models:

```bash
docker compose down
```

To remove the application and its downloaded model data:

```bash
docker compose down -v
```

## Choose another model

Edit `.env` and set a model tag supported by Ollama, then recreate the service:

```env
OLLAMA_MODEL=qwen2.5:0.5b
PORT=8000
```

```bash
docker compose up -d --build
```

The configured model is checked/pulled at startup. If its files already exist in the persistent model directory, Ollama reuses them. You can also pull another model from inside the running container:

```bash
docker exec -it local-ollama-chatbot ollama pull qwen2.5:1.5b
```

The model selector refreshes from the models installed in Ollama when the page is loaded.

## Run without Compose

```bash
docker build -t local-ollama-chatbot .
docker run -d --name local-ollama-chatbot \
  -p 8000:8000 \
  -e OLLAMA_MODEL=qwen2.5:0.5b \
  -v ollama_data:/root/.ollama \
  --restart unless-stopped \
  local-ollama-chatbot
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | Model pulled at startup and used by default |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Backend-to-Ollama URL (normally leave unchanged) |
| `PORT` | `8000` | Web application port inside the container |
| Compose `PORT` | `8000` | Host port exposed by Compose |

## API endpoints

- `GET /api/health` — app/Ollama health and installed model names.
- `GET /api/models` — installed Ollama models.
- `POST /api/chat` — streams Ollama chat response as newline-delimited JSON.

Example:

```bash
curl -N http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Explain Docker in one paragraph","model":"qwen2.5:0.5b","history":[]}'
```

## Deploy on Render

The included `render.yaml` deploys the **all-in-one Dockerfile** so Ollama and the web app run in the same Render service. It uses the compact `qwen2.5:0.5b` model, a paid Standard instance (2 GB RAM), and a 1 GB persistent disk mounted at `/root/.ollama` so model files survive restarts and redeploys.

**Render Free is not suitable for this setup:** its 512 MB RAM and lack of persistent disks make an in-container Ollama model unreliable. The small model reduces memory and download needs, but does not remove that platform limitation.

## Security

Do not expose the web app to the public internet without adding authentication, HTTPS, request limits, and appropriate network controls. The Ollama API is bound to the container loopback and is not published as a host port.

## Troubleshooting

- Check logs with `docker compose logs -f chatbot`.
- Check health with `curl http://localhost:8000/api/health`.
- Initial startup may take a while while the model downloads. The app starts after the model is available.
- If the container exits during model download, check network connectivity and available disk space, then start it again.
