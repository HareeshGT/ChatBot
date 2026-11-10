# Deploy the chat UI on Render Free

## Important limitation

Render Free web services have 512 MB RAM and an ephemeral filesystem. They do not support persistent disks. This makes running Ollama and a local model inside the same Free service impractical: the model files disappear after a restart/spin-down/redeploy, and the available memory is too small for the default `llama3.2:3b` model.

For a Render Free deployment, use the lightweight `Dockerfile.render` for the web UI and connect it to an Ollama server running on a different machine that you control. That Ollama machine must be reachable over HTTPS/network and have sufficient RAM/storage. Do not expose an unauthenticated Ollama API publicly.

## Setup

1. Deploy this repository on Render using the included `render.yaml` Blueprint, or set the Dockerfile path to `Dockerfile.render`.
2. In the Render service environment settings, set `OLLAMA_URL` to your reachable Ollama server base URL (for example, `https://your-secured-ollama-host.example.com`, without a trailing slash).
3. Set `OLLAMA_MODEL` to a model already pulled on that Ollama server, such as `llama3.2:3b`.
4. Redeploy and check `/api/health`.

The Render deployment will no longer install Ollama or download a 2 GB model as part of the Render service startup. It only hosts the chat UI/API proxy.

## If Ollama must run on the same host

Use a paid Render service with enough RAM and a persistent disk mounted at `/root/.ollama`, or host the all-in-one `Dockerfile` on a machine with adequate memory and persistent storage. Render Free cannot attach persistent disks, and changing the startup script alone cannot preserve model files after the service's filesystem is reset.
