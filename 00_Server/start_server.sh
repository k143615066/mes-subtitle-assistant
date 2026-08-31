#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 was not found. Install Python 3.10 or later, then run this file again."
    exit 1
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -r app/requirements.txt

if [ ! -f "../.env" ]; then
    echo "Missing ../.env. Copy ../.env.example to ../.env and set DeepSeek_Key first."
    exit 1
fi

set -a
source ../.env
set +a

echo "MES Subtitle Assistant is starting."
echo "Open: http://localhost:15000"

cd app
python main.py
