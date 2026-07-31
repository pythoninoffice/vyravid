#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export VYRAVID_ROOT="$ROOT"
export VYRAVID_LOCAL=true
export PYTHONPATH="$ROOT:$ROOT/app:${PYTHONPATH:-}"

cd "$ROOT/app"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
elif [[ -f "$ROOT/app/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/app/.env"
  set +a
fi

# Keep local runtime paths bound to this checkout even if a copied .env points
# at another local clone.
export VYRAVID_ROOT="$ROOT"
export VYRAVID_DATA="$ROOT/data"
export VYRAVID_DB="$ROOT/data/db/openvid.sqlite3"
export DATABASE_URL="sqlite:///$VYRAVID_DB"

PORT="${PORT:-8000}"
export VYRAVID_PUBLIC_BASE="${VYRAVID_PUBLIC_BASE:-http://localhost:${PORT}}"
export WEBHOOK_BASE_URL="${WEBHOOK_BASE_URL:-http://localhost:${PORT}}"
# Video processor is embedded in this process at /vp
export CLOUD_VIDEO_PROCESSOR_URL="${CLOUD_VIDEO_PROCESSOR_URL:-${VYRAVID_PUBLIC_BASE}/vp}"
export USE_CLOUD_PROCESSING="${USE_CLOUD_PROCESSING:-true}"

if [[ -x "$ROOT/venv/bin/python" ]]; then
  PY="$ROOT/venv/bin/python"
elif [[ -x /app/venv/bin/python ]]; then
  PY=/app/venv/bin/python
elif [[ -x /home/jz/content-gen/app/venv/bin/python ]]; then
  PY=/home/jz/content-gen/app/venv/bin/python
else
  PY=python3
fi

echo "Starting vyravid (API + video processor) on :${PORT}"
echo "  VYRAVID_PUBLIC_BASE=${VYRAVID_PUBLIC_BASE}"
echo "  CLOUD_VIDEO_PROCESSOR_URL=${CLOUD_VIDEO_PROCESSOR_URL}"
echo "  Video processor routes: ${VYRAVID_PUBLIC_BASE}/vp/*"
exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
