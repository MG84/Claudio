#!/bin/bash
set -e

echo "========================================="
echo "  Claudio — Personal AI Assistant"
echo "========================================="
echo ""

# Check required env vars
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN not set"
    exit 1
fi

if [ -z "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    echo "WARNING: CLAUDE_CODE_OAUTH_TOKEN not set"
    echo "Claude Code will not be able to authenticate."
    echo "Run 'claude setup-token' on your host machine and add the token to .env"
fi

# Check projects mount
if [ -d /home/assistant/projects ] && [ "$(ls /home/assistant/projects 2>/dev/null | head -1)" ]; then
    PROJECT_COUNT=$(ls -d /home/assistant/projects/*/ 2>/dev/null | wc -l)
    echo "Projects directory mounted: $PROJECT_COUNT directories"
else
    echo "WARNING: Projects directory empty or not mounted"
fi

# Initialize memory directory
if [ ! -f /home/assistant/memory/MEMORY.md ]; then
    echo "# Claudio Memory" > /home/assistant/memory/MEMORY.md
    echo "" >> /home/assistant/memory/MEMORY.md
    echo "Appunti e memoria persistente di Claudio." >> /home/assistant/memory/MEMORY.md
fi

echo "Starting Claudio bot..."
exec python3 -m bot.main
