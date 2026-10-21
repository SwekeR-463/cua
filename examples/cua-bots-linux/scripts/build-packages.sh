#!/usr/bin/env bash
# Build the self-contained backend, then the .deb and AppImage.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON="${PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements-dev.txt pyinstaller

(cd web && npm ci --no-audit --no-fund && npm run build)

rm -rf build dist
pyinstaller --noconfirm --clean --onedir --name cua-bots-server \
  --paths . \
  --collect-all cua \
  --collect-submodules cua_bots \
  --add-data 'web/dist:web/dist' \
  packaging/entrypoint.py

(cd electron && npm ci --no-audit --no-fund)
(cd electron && CSC_IDENTITY_AUTO_DISCOVERY=false \
  ./node_modules/.bin/electron-builder --linux deb AppImage --publish never)

printf '\nArtifacts:\n'
ls -lh dist-packages
