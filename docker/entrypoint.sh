#!/usr/bin/env bash
# Container entrypoint: ensure the corpus exists and is indexed, then serve the app.
# Idempotent — safe to run on every container start (data persists via the mounted volume).
set -euo pipefail

echo "[entrypoint] Ensuring synthetic corpus exists..."
if [ -z "$(ls -A "${CORPUS_DIR:-./data/corpus}" 2>/dev/null || true)" ]; then
  python scripts/generate_data.py
else
  echo "[entrypoint] Corpus already present, skipping generation."
fi

echo "[entrypoint] Ingesting corpus into the vector store..."
python scripts/ingest.py

echo "[entrypoint] Launching API + web UI on ${APP_HOST:-0.0.0.0}:${APP_PORT:-7860}..."
exec python scripts/run_app.py
