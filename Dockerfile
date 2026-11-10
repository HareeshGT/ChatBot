FROM python:3.12-slim

ARG OLLAMA_VERSION=0.12.6
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_MODELS=/root/.ollama/models \
    OLLAMA_MODEL=qwen2.5:0.5b \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl bash && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh && mkdir -p /root/.ollama

EXPOSE 8000
VOLUME ["/root/.ollama"]

ENTRYPOINT ["./docker-entrypoint.sh"]
