#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

export VITE_API_URL="${VITE_API_URL:-http://localhost:8000}"

if [[ ! -d node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm install
fi

PORT="${FRONTEND_PORT:-5173}"
echo "Starting vyravid frontend on :${PORT} (API=${VITE_API_URL})"
exec npm run dev -- --host 0.0.0.0 --port "$PORT"
