FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ── Base system packages ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git build-essential ca-certificates gnupg \
    python3 python3-pip python3-venv python3-dev \
    fonts-liberation \
    ffmpeg \
    tmux htop jq unzip zip \
    openssh-client \
    sudo \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 22 (for Claude Code CLI) ─────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Claude Code CLI ──────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code

# ── Kraken CLI (MCP server for market data + paper trading) ─────────
ARG KRAKEN_CLI_VERSION=v0.3.1
RUN curl -L "https://github.com/krakenfx/kraken-cli/releases/download/${KRAKEN_CLI_VERSION}/kraken-cli-aarch64-unknown-linux-gnu.tar.gz" \
    | tar xz --strip-components=1 -C /usr/local/bin/ kraken-cli-aarch64-unknown-linux-gnu/kraken \
    && chmod +x /usr/local/bin/kraken

# ── Non-root user ────────────────────────────────────────────────────
RUN useradd -m -s /bin/bash assistant \
    && echo "assistant ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
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
RUN python3 -m pip install --break-system-packages --timeout=300 -r /home/assistant/bot/requirements.txt

# ── Kronos model code (only model/ dir, ~50KB) ────────────────────────
RUN git clone --depth 1 https://github.com/shiyu-coder/Kronos.git /tmp/kronos \
    && mkdir -p /home/assistant/kronos_model \
    && cp -r /tmp/kronos/model /home/assistant/kronos_model/model \
    && rm -rf /tmp/kronos

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
