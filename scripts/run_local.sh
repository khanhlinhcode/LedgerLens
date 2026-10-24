#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo "[setup] Creating local .env and random API key."
  if command -v python >/dev/null 2>&1; then PYTHON_BIN=python; else PYTHON_BIN=python3; fi
  KEY=$("$PYTHON_BIN" -c 'import secrets;print(secrets.token_urlsafe(32))')
  printf 'APP_API_KEY=%s\nDATABASE_URL=sqlite:///./copilot.db\n' "$KEY" > .env
  chmod 600 .env
fi
set -a
source .env
set +a
if [[ -z "${APP_API_KEY:-}" ]]; then echo 'APP_API_KEY is required';exit 1;fi
printf 'Open http://127.0.0.1:8000\nOpen the protected local .env file in your editor and paste APP_API_KEY into the login dialog. The key is not printed.\n'
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
