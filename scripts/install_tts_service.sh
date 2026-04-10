#!/bin/bash
# Installa il TTS server come launchd service (autostart al login)

set -e

TTS_DIR="$HOME/.claudio-tts"
PLIST_PATH="$HOME/Library/LaunchAgents/com.claudio.tts.plist"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claudio.tts</string>
    <key>ProgramArguments</key>
    <array>
        <string>${TTS_DIR}/.venv/bin/python</string>
        <string>${TTS_DIR}/mlx-tts-api/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${TTS_DIR}/mlx-tts-api</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${TTS_DIR}/tts.log</string>
    <key>StandardErrorPath</key>
    <string>${TTS_DIR}/tts.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>MLX_TTS_HOST</key>
        <string>0.0.0.0</string>
        <key>MLX_TTS_PORT</key>
        <string>8880</string>
    </dict>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"

echo "TTS service installato e avviato!"
echo "  Status: launchctl list | grep claudio.tts"
echo "  Stop:   launchctl unload $PLIST_PATH"
echo "  Logs:   tail -f $TTS_DIR/tts.log"
