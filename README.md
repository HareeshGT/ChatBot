# Local-first AI ChatBot

A FastAPI web chatbot with a **local Qwen GGUF model selected by default**, plus optional cloud providers: OpenAI, Groq, Mistral, Google Gemini, Anthropic, and a custom OpenAI-compatible endpoint.

## How model selection works

- **Local · Qwen** is always the default. It runs inside this app with llama-cpp-python; no API key or external inference service is needed.
- Cloud providers appear in the model selector only when their server-side API key is configured.
- Select a provider from the dropdown to route the next prompt to that provider. Switch back to Local at any time.
- API keys are read only by the backend from environment variables. They are never sent to the browser or returned by the models endpoint.

## Supported providers

| Provider | Environment key | Default model |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Mistral | `MISTRAL_API_KEY` | `mistral-small-latest` |
| Google Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-3-5-haiku-latest` |
| Custom | `CUSTOM_API_KEY` + `CUSTOM_API_BASE` + `CUSTOM_MODEL_NAME` | User-defined |

Provider model names can be changed using the corresponding `*_MODEL` environment variable. The custom endpoint must implement the OpenAI-compatible `/chat/completions` streaming API. Anthropic uses its native Messages streaming API.

## Configure providers from the chat UI (recommended for personal use)

1. Open the chatbot and click **＋ Add model**.
2. Select a provider, paste your API key, and enter the model ID (the default field value is a suggested model).
3. For a custom provider, also enter its HTTPS OpenAI-compatible API base URL.
4. Click **Save model**. Select the newly added model from the top model dropdown.

UI-entered credentials are held in browser session storage and are sent to the backend only with requests to that provider. They are not persisted on the server. Do not use this on a shared or untrusted device. The app currently has no user authentication; add authentication before making a public multi-user service.

## Configure shared server-side keys (alternative)

You can still add provider environment variables in the [Render dashboard](https://dashboard.render.com/) under `chatbot-web` → **Environment**. These server-side keys are shared by everyone who can access the deployed app. Never commit real API keys to GitHub or put them in `.env.example`.

## Local GGUF model

- Repository: [Qwen/Qwen2.5-0.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF)
- File: `qwen2.5-0.5b-instruct-q4_k_m.gguf`
- Downloaded to `/models` and reused from persistent storage.

## Run with Docker Compose

```bash
git clone https://github.com/HareeshGT/ChatBot.git
cd ChatBot
cp .env.example .env
docker compose up -d --build
```

Open http://localhost:8000. Add optional keys to your local `.env` file to enable cloud providers.

## Environment variables

| Variable | Purpose |
|---|---|
| `DEFAULT_MODEL` | Defaults to `local`; may be set to an enabled provider model ID |
| `OPENAI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | Enable the corresponding provider |
| `OPENAI_MODEL`, `GROQ_MODEL`, `MISTRAL_MODEL`, `GEMINI_MODEL`, `ANTHROPIC_MODEL` | Override provider model IDs |
| `CUSTOM_API_BASE` | Base URL for custom OpenAI-compatible API, without `/chat/completions` |
| `CUSTOM_API_KEY` | Custom provider key |
| `CUSTOM_MODEL_NAME` | Model identifier sent to custom endpoint |
| `CUSTOM_MODEL_LABEL` | Friendly label shown in dropdown |
| `MODEL_REPO`, `MODEL_FILE`, `MODEL_DIR`, `MODEL_PATH` | Local GGUF location |
| `LLAMA_THREADS`, `LLAMA_CONTEXT_SIZE` | Local inference tuning |

## API

- `GET /api/health` — local model readiness and provider count.
- `GET /api/models` — configured model choices (never includes API keys).
- `POST /api/chat` — streams newline-delimited JSON with the same `message.content` contract for local and cloud models.

## Security

This app currently has no user authentication. Anyone who can access the public chat can use any provider keys configured on the server and incur charges. Put the app behind authentication or add user access controls before sharing it publicly. Provider prompts are sent to the selected third-party provider; only Local keeps inference inside this app.
