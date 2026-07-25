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

# The web UI ships as package data. pytest puts src/ on sys.path ahead of site-packages,
# so no Python test can detect a packaging regression — this is the only check that can.
RUN python -c "import pathlib, payment_assistant.ui as ui; \
    d = pathlib.Path(ui.__file__).parent / 'static'; \
    missing = [f for f in ('index.html', 'style.css', 'app.js') if not (d / f).is_file()]; \
    assert not missing, f'static assets missing from the installed wheel: {missing} — check [tool.setuptools.package-data] in pyproject.toml'"

# App code (scripts + defaults). Corpus/chroma live under ./data (a mounted volume).
COPY scripts ./scripts
COPY eval ./eval
COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod +x ./docker/entrypoint.sh

EXPOSE 7860

# Long start period on purpose: the first boot downloads the embedding model and the
# cross-encoder re-ranker (~2.7 GB combined) before the server accepts connections.
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('APP_PORT', '7860') + '/api/health', timeout=4)"

ENTRYPOINT ["./docker/entrypoint.sh"]
