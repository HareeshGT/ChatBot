# Local Ollama ChatBot

A self-hosted web chat application powered by [Ollama](https://ollama.com/). Ollama runs **inside the same Docker container** as the application, on the machine hosting the container. The browser communicates with the Python backend; the backend communicates with Ollama over the container's loopback interface.

## Features

- Clean, responsive chat interface with streaming responses.
- Ollama model selector (lists models already installed).
- Configurable default model; automatically pulled on first startup.
- Conversation context sent to Ollama on each turn.
- Persistent model storage using a Docker named volume.
- No external AI API key or hosted inference service required.

## Run with Docker Compose (recommended)

Requirements: Docker Engine/Desktop and the Docker Compose plugin. The first build downloads Ollama and Python dependencies. The first startup also downloads the configured model, so allow time and disk space for it.

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
OLLAMA_MODEL=qwen2.5:3b
PORT=8000
```

```bash
docker compose up -d --build
```

The configured model is pulled automatically on container startup. You can also pull another model from inside the running container:

```bash
docker exec -it local-ollama-chatbot ollama pull mistral
```

The model selector refreshes from the models installed in Ollama when the page is loaded.

## Run without Compose

```bash
docker build -t local-ollama-chatbot .
docker run -d --name local-ollama-chatbot \
  -p 8000:8000 \
  -e OLLAMA_MODEL=llama3.2:3b \
  -v ollama_data:/root/.ollama \
  --restart unless-stopped \
  local-ollama-chatbot
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2:3b` | Model pulled at startup and used by default |
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
  -d '{"message":"Explain Docker in one paragraph","model":"llama3.2:3b","history":[]}'
```

## Hosting and resources

Ollama performs inference on the host machine's resources available to the Docker container (CPU/RAM by default). Model files persist in the `ollama_data` named volume. Choose a model that fits the host's available memory and storage. Smaller quantized models are more practical on CPU-only machines; GPU acceleration depends on compatible host drivers and Docker runtime configuration.

**Important:** this single-container setup is designed for a machine you control. Do not expose the web app to the public internet without adding authentication, HTTPS, request limits, and appropriate network controls. The Ollama API is bound to the container loopback and is not published as a host port.

## Troubleshooting

- Check logs with `docker compose logs -f chatbot`.
- Check health with `curl http://localhost:8000/api/health`.
- Initial startup may take a while while the model downloads. The app starts after the model is available.
- If the container exits during model download, check network connectivity and available disk space, then start it again.
