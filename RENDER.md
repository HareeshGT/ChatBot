# Deploy Ollama + ChatBot together on Render

This configuration runs Ollama and the ChatBot web app inside the **same Render service/container**. It uses the compact `qwen2.5:0.5b` model (approximately 398 MB to download), not the previous multi-gigabyte model.

## Render requirements

- Use the **Standard** web service plan (2 GB RAM) or a larger plan.
- Attach a persistent disk mounted at `/root/.ollama`. The included `render.yaml` defines a 1 GB disk.
- Render Free is not suitable: it has 512 MB RAM and does not support persistent disks. Even a small model can exceed the available memory once Ollama and the web app are running.

## Deploy

1. Open the [Render dashboard](https://dashboard.render.com/).
2. Create or update the service from this repository using the included Blueprint `render.yaml`.
3. Confirm the service uses `./Dockerfile` (not `Dockerfile.render`).
4. Confirm the service plan is Standard or higher and the disk mount path is `/root/.ollama`.
5. Deploy. On first startup, Ollama downloads the model. On subsequent starts, the persistent disk lets Ollama reuse it instead of downloading it again.
6. After deployment, open `https://YOUR-SERVICE.onrender.com/api/health`. A healthy response includes `"ollama":"connected"` and the installed model list.

## Change the model

Set `OLLAMA_MODEL` to another Ollama model tag in Render's Environment settings. Smaller models use less memory but generally produce less capable answers. The default is `qwen2.5:0.5b`.

## Note

The configuration changes the Render Blueprint to a paid Standard service because Render Free cannot provide the RAM and persistent disk needed for this architecture. Review the selected plan and estimated cost in Render before applying it.
