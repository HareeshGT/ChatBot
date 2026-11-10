# Deploy Python GGUF ChatBot on Render

This service runs FastAPI and **llama-cpp-python in the same container**. It does not install or run Ollama. The Qwen 2.5 0.5B Instruct Q4_K_M GGUF file is downloaded from Hugging Face on first startup and stored on a persistent disk.

## Configuration

The included `render.yaml` sets:

- Dockerfile: `./Dockerfile`
- Instance plan: Standard as a starting point; review current memory limits and pricing before applying
- Persistent disk: 1 GB mounted at `/models`
- Model repository: `Qwen/Qwen2.5-0.5B-Instruct-GGUF`
- Model file: `qwen2.5-0.5b-instruct-q4_k_m.gguf`
- CPU threads: 4

The GGUF file is approximately 491 MB. The disk stores the file across restarts and redeploys; the model is loaded into RAM when the app starts. The persistent disk must be mounted at `/models` because that is the configured model directory.

## Deploy

1. Open the [Render dashboard](https://dashboard.render.com/).
2. Create or update a Blueprint from this repository.
3. Review the plan and disk settings before applying.
4. Deploy. The Docker image build compiles llama-cpp-python's CPU backend and may take several minutes.
5. On the first start, the app downloads the GGUF model, loads it, and performs a short warm-up inference before passing the health check.
6. Open `https://YOUR-SERVICE.onrender.com/api/health`. A healthy response contains `"engine":"llama-cpp-python"` and the model name.

## Environment variables

- `MODEL_REPO`: Hugging Face repository ID.
- `MODEL_FILE`: GGUF filename in that repository.
- `MODEL_DIR`: model directory, default `/models`.
- `MODEL_PATH`: full path to the GGUF file.
- `LLAMA_THREADS`: CPU threads, default 4.
- `LLAMA_CONTEXT_SIZE`: context window, default 2048.
- `PORT`: provided by Render.

If you change `MODEL_FILE`, update `MODEL_PATH` to the same filename. Choose a compatible GGUF model supported by llama.cpp.

## Notes

- Render Free is not recommended: local inference needs RAM for model weights, context cache, and Python runtime, and the model should be kept on persistent storage.
- CPU inference performance depends on the instance. Increasing thread count does not always improve speed.
- The API currently has no authentication; add access controls before using it for a public-facing service.
