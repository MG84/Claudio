#!/bin/bash
# Deploy dashboard from claudio-monitor to Claudio
set -e
MONITOR_DIR="${CLAUDIO_MONITOR_DIR:-$HOME/Documents/Development/claudio-monitor}"
CLAUDIO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$MONITOR_DIR" ]; then
    echo "Error: claudio-monitor not found at $MONITOR_DIR"
    echo "Set CLAUDIO_MONITOR_DIR to override."
    exit 1
fi

echo "Building claudio-monitor..."
cd "$MONITOR_DIR" && npm run build

echo "Copying static export..."
rm -rf "$CLAUDIO_DIR/dashboard/"*
cp -r out/* "$CLAUDIO_DIR/dashboard/"

echo "Rebuilding Docker..."
cd "$CLAUDIO_DIR" && docker compose down && docker compose up -d --build

echo "Deploy complete."
