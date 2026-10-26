#!/usr/bin/env bash
# One-command setup for a Mac (Apple Silicon or Intel).
# Installs Python, ffmpeg, and Node with Homebrew, then the app.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and run this again."
  exit 1
fi

brew install python@3.12 ffmpeg node

cd "$root/backend"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

cd "$root/frontend"
npm install
npm run build

cat <<EOF

Qalam is installed.

The built site is served by the API (frontend/dist):

  cd "$root/backend"
  source .venv/bin/activate
  python3 -m uvicorn qalam.main:app --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000

For development, with the page reloading as you edit:

  cd "$root/frontend" && npm run dev

The first voice transcription downloads the Whisper base model into
~/.cache/qalam/whisper. Everything after that stays on this Mac.
EOF
