#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "python3 missing"; exit 1; }
[ -d .venv ] || python3 -m venv .venv || { echo "Run: sudo apt install -y python3-venv"; exit 1; }
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
