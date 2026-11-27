#!/usr/bin/env bash
# AegisVision — run the full app (backend + dashboard) in one shot.
#
# The dashboard is a static SPA served by FastAPI itself (SERVE_FRONTEND=true),
# so a single uvicorn process runs the entire product: REST + WebSocket + MJPEG
# streams + API docs at /docs.
#
# Usage:
#   ./run.sh               # start in dev mode (--reload)
#   ./run.sh --no-reload   # start production-style (no auto reload)
#   HOST=127.0.0.1 PORT=9000 ./run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ---- pick the Python interpreter (uv-managed venv wins) -------------------
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="$(command -v python3 || true)"
  if [ -z "$PYTHON" ]; then
    echo "error: no usable python. Create a venv first:  uv sync" >&2
    exit 1
  fi
fi
echo "using python: $PYTHON"

# ---- ensure dependencies are installed ------------------------------------
if ! "$PYTHON" -c "import fastapi, uvicorn, chromadb" >/dev/null 2>&1; then
  echo "missing dependencies — installing from backend/requirements.txt ..."
  "$PYTHON" -m pip install -r "$ROOT/backend/requirements.txt"
fi

# ---- env template ---------------------------------------------------------
if [ ! -f "$ROOT/backend/.env" ]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "created backend/.env from template (edit it to add camera sources / API keys)"
fi

# ---- config ---------------------------------------------------------------
# Precedence: shell env > backend/.env > defaults (0.0.0.0:8000)
HOST_ARG="${HOST:-}"; PORT_ARG="${PORT:-}"
if [ -f "$ROOT/backend/.env" ]; then
  [ -z "$HOST_ARG" ] && HOST_ARG="$(grep '^HOST=' "$ROOT/backend/.env" | head -1 | cut -d= -f2)"
  [ -z "$PORT_ARG" ] && PORT_ARG="$(grep '^PORT=' "$ROOT/backend/.env" | head -1 | cut -d= -f2)"
fi
HOST="${HOST_ARG:-0.0.0.0}"
PORT="${PORT_ARG:-8000}"
RELOAD=1
if [[ "${1:-}" == "--no-reload" ]]; then RELOAD=0; fi
RELOAD_FLAG=()
[ "$RELOAD" = "1" ] && RELOAD_FLAG=(--reload)

# ---- run the full app -----------------------------------------------------
echo "------------------------------------------------------------"
echo "  AegisVision        -> http://localhost:${PORT}"
echo "  Dashboard          -> http://localhost:${PORT}/"
echo "  API + docs         -> http://localhost:${PORT}/docs"
echo "  (frontend is served by the backend — one process)"

(cd "$ROOT/backend" && exec "$PYTHON" -m uvicorn main:app "${RELOAD_FLAG[@]}" --host "$HOST" --port "$PORT")