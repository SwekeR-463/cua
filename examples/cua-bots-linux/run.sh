#!/usr/bin/env bash
# Start Cua Bots for Linux: the Python backend, then Electron (or a Chrome
# app window when Electron is not installed).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODE="${1:-desktop}"
PYTHON="${PYTHON:-python3}"

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
. .venv/bin/activate
python -m pip install -q -r requirements.txt

if [[ ! -f web/dist/index.html ]]; then
  (cd web && npm install --no-audit --no-fund && npm run build)
fi

export CUA_BOTS_PORT="${CUA_BOTS_PORT:-8765}"
export CUA_BOTS_HOST="${CUA_BOTS_HOST:-127.0.0.1}"

if [[ "$MODE" == "--backend-only" ]]; then
  exec python -m cua_bots
fi

python -m cua_bots &
BACK=$!
cleanup() {
  kill "$BACK" 2>/dev/null || true
  wait "$BACK" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${CUA_BOTS_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if [[ -x electron/node_modules/electron/dist/electron ]]; then
  (cd electron && ./node_modules/.bin/electron --no-sandbox .)
elif command -v google-chrome >/dev/null 2>&1; then
  google-chrome --app="http://127.0.0.1:${CUA_BOTS_PORT}" --window-size=1280,800 --class=CuaBots
elif command -v chromium >/dev/null 2>&1; then
  chromium --app="http://127.0.0.1:${CUA_BOTS_PORT}" --window-size=1280,800
else
  xdg-open "http://127.0.0.1:${CUA_BOTS_PORT}"
fi
