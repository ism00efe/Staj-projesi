# syntax=docker/dockerfile:1
FROM python:3.11-slim

# System deps kept minimal; sentence-transformers pulls a CPU torch wheel via pip.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/hf-cache \
    APP_HOST=0.0.0.0 \
    APP_PORT=7860

WORKDIR /app

# Install dependencies first (better layer caching). Only pyproject is needed for deps.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# App code (scripts + defaults). Corpus/chroma live under ./data (a mounted volume).
COPY scripts ./scripts
COPY eval ./eval
COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod +x ./docker/entrypoint.sh

EXPOSE 7860
ENTRYPOINT ["./docker/entrypoint.sh"]
