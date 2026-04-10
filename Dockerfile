FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ── Base system packages ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git build-essential ca-certificates gnupg \
    python3 python3-pip python3-venv python3-dev \
    chromium-browser fonts-liberation \
    ffmpeg \
    tmux htop jq unzip zip \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 22 (for Claude Code CLI) ─────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Claude Code CLI ──────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code

# ── Non-root user ────────────────────────────────────────────────────
RUN useradd -m -s /bin/bash assistant
USER assistant
WORKDIR /home/assistant

# ── Directory structure ──────────────────────────────────────────────
RUN mkdir -p \
    /home/assistant/.claude \
    /home/assistant/projects \
    /home/assistant/bot \
    /home/assistant/memory

# ── Python dependencies ──────────────────────────────────────────────
COPY --chown=assistant:assistant requirements.txt /home/assistant/bot/requirements.txt
RUN python3 -m pip install --break-system-packages -r /home/assistant/bot/requirements.txt

# ── Bot code ─────────────────────────────────────────────────────────
COPY --chown=assistant:assistant bot/ /home/assistant/bot/
COPY --chown=assistant:assistant scripts/ /home/assistant/scripts/
COPY --chown=assistant:assistant memory/ /home/assistant/memory/

# ── Dashboard (pre-built static export) ──────────────────────────────
COPY --chown=assistant:assistant dashboard/ /home/assistant/dashboard/

# ── Entrypoint ───────────────────────────────────────────────────────
COPY --chown=assistant:assistant scripts/entrypoint.sh /home/assistant/entrypoint.sh
RUN chmod +x /home/assistant/entrypoint.sh

ENTRYPOINT ["/home/assistant/entrypoint.sh"]
