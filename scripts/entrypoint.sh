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

# Fix ownership of mounted volumes (Docker creates them as root)
sudo chown -R assistant:assistant /home/assistant/.cache 2>/dev/null || true

# Initialize memory directory
if [ ! -f /home/assistant/memory/MEMORY.md ]; then
    echo "# Claudio Memory" > /home/assistant/memory/MEMORY.md
    echo "" >> /home/assistant/memory/MEMORY.md
    echo "Appunti e memoria persistente di Claudio." >> /home/assistant/memory/MEMORY.md
fi

# Wait for Ollama and pull models if needed (for Mem0 memory)
if [ "${MEM0_ENABLED:-true}" != "false" ]; then
    OLLAMA_URL="${OLLAMA_HOST:-http://ollama:11434}"
    EMBED_MODEL="${MEM0_EMBEDDING_MODEL:-nomic-embed-text:latest}"
    LLM_MODEL="${MEM0_LLM_MODEL:-llama3.1:8b}"

    echo "Waiting for Ollama at $OLLAMA_URL..."
    RETRIES=0
    MAX_RETRIES=30
    until curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; do
        RETRIES=$((RETRIES + 1))
        if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
            echo "WARNING: Ollama not reachable after ${MAX_RETRIES} attempts. Starting without memory."
            break
        fi
        sleep 2
    done

    if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
        echo "Ollama ready."
        # Pull embedding model if not present
        if ! curl -sf "$OLLAMA_URL/api/show" -d "{\"name\":\"$EMBED_MODEL\"}" > /dev/null 2>&1; then
            echo "Pulling $EMBED_MODEL..."
            if ! curl -sf -X POST "$OLLAMA_URL/api/pull" -d "{\"name\":\"$EMBED_MODEL\",\"stream\":false}"; then
                echo "WARNING: Failed to pull $EMBED_MODEL"
            fi
        fi
        # Pull LLM for fact extraction if not present
        if ! curl -sf "$OLLAMA_URL/api/show" -d "{\"name\":\"$LLM_MODEL\"}" > /dev/null 2>&1; then
            echo "Pulling $LLM_MODEL..."
            if ! curl -sf -X POST "$OLLAMA_URL/api/pull" -d "{\"name\":\"$LLM_MODEL\",\"stream\":false}"; then
                echo "WARNING: Failed to pull $LLM_MODEL"
            fi
        fi
    fi
else
    echo "Mem0 disabled, skipping Ollama setup."
fi

echo "Starting Claudio bot..."
exec python3 -m bot.main

# Avvia email auto-responder in background (ogni 5 minuti)
(while true; do
    python3 /home/assistant/projects/Claudio/scripts/email_responder.py >> /home/assistant/memory/email_responder.log 2>&1
    sleep 300
done) &
echo "Email auto-responder avviato (intervallo: 5 minuti)"
