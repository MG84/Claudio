# Claudio — Personal AI Assistant

An AI-powered personal assistant running in Docker, controlled via Telegram, with voice cloning and real-time monitoring. Built on Claude Code (Anthropic) via the Claude Agent SDK.

## Architecture

```
Telegram (phone/desktop)
    │
    ▼
Docker Container "claudio" (OrbStack)
    ├── Telegram Bot (aiogram)
    ├── Claude Agent SDK → Claude Code CLI
    ├── faster-whisper (local STT)
    ├── Monitoring Dashboard (WebSocket + static)
    └── Access to ~/Documents/Development/
            │
            ▼
Mac bare metal
    └── Qwen3-TTS via MLX (TTS with voice cloning)
```

Everything runs locally. No cloud services, no API costs beyond the Claude Max subscription.

## Features

### Core
- **Full AI assistant** via Telegram — text and voice
- **Claude Code under the hood** — can read/write files, run commands, search the web, install packages
- **Persistent sessions** — remembers context across messages, with `/new` and `/resume`
- **Project-aware** — Forum Topics map to local projects, Claude reads each project's `CLAUDE.md`

### Voice
- **Speech-to-Text** — faster-whisper (large-v3-turbo, local, Italian)
- **Text-to-Speech** — Qwen3-TTS via MLX with Edge TTS fallback
- **Voice cloning** — clone any voice from a 15-30s audio sample, fully conversational flow
- **Voice in → voice out** — send a voice message, get a voice response

### Projects
- **Forum Topics** — one Telegram topic per project, isolated sessions
- **Auto-discovery** — scans `~/Documents/Development/` for projects with `.git` or `CLAUDE.md`
- **Git safety** — system prompt enforces feature branches, no force push

### Monitoring
- **Dashboard** at `localhost:3333` — real-time events via WebSocket
- **Cloudflare Tunnel** sidecar for remote access
- **Password protected** — cookie-based auth
- **Event timeline** per project with tool use details

### Self-evolution
- Claudio has access to its own source code
- Can modify itself via Telegram (rebuild required to apply)
- Hot-reload for config changes (model, voice, effort) via `runtime_config.json`

## Requirements

- **Mac with Apple Silicon** (M1/M2/M3/M4) — for MLX-based TTS
- **Docker** (OrbStack recommended)
- **Claude Max subscription** — for Claude Code access
- **Telegram account** — for the bot interface

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/MG84/Claudio.git
cd Claudio
cp .env.example .env
```

Edit `.env` with your credentials:

```env
USER_NAME=YourName         # Your name (used in system prompt)
PROJECTS_PATH=/path/to/dev # Folder with your projects (mounted into Docker)
CLAUDE_CODE_OAUTH_TOKEN=   # Run: claude setup-token
TELEGRAM_BOT_TOKEN=        # From @BotFather on Telegram
TELEGRAM_ALLOWED_USERS=    # Your Telegram user ID (from @userinfobot)
DASHBOARD_PASSWORD=        # Password for the monitoring dashboard
```

### 2. Create the Telegram bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, choose a name and username
3. Copy the token into `.env`
4. Send `/setprivacy` → select your bot → **Disable** (required for group messages)

### 3. Generate Claude OAuth token

```bash
claude setup-token
```

This opens a browser for login. Copy the token (`sk-ant-oat01-...`) into `.env`.

### 4. Start the bot

```bash
docker compose up -d --build
```

The bot is now running. Send a message to your bot on Telegram.

### 5. Set up TTS (optional, for voice responses)

```bash
bash scripts/setup_tts.sh
```

Then start the TTS server:

```bash
cd ~/.claudio-tts/mlx-tts-api
source ../.venv/bin/activate
MLX_TTS_PORT=8880 python server.py
```

For autostart at login:

```bash
bash scripts/install_tts_service.sh
```

### 6. Set up Forum Topics (optional, for projects)

1. Create a Telegram group with Forum Topics enabled
2. Add your bot as admin
3. Create topics for your projects
4. In each topic, send `/link project-name`

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Welcome and command list |
| `/projects` | List available projects |
| `/link <name>` | Link current topic to a project |
| `/unlink` | Unlink current topic |
| `/new` | New conversation (saves previous) |
| `/resume` | Restore previous session |
| `/status` | Current status (model, project, session) |
| `/model <name>` | Change Claude model |
| `/opus` `/sonnet` `/haiku` | Quick model switch |
| `/effort <low\|medium\|high>` | Reasoning depth |
| `/turns <n>` | Max steps per response |
| `/plan` | Next message in planning mode |
| `/compact` | Reset context |
| `/voice` | Force voice response for next text message |
| `/text` | Show text of last voice response |

## Voice Cloning

Tell Claudio "clone my voice" on Telegram. The flow:

1. Send a 15-30 second voice message of natural speech
2. Claudio shows the transcription — confirm or correct it
3. Claudio registers the voice and generates sample audio
4. Listen to the samples and choose the best one
5. Optionally set it as the default voice

No hardcoded workflow — Claudio orchestrates everything via bash commands to the TTS server.

## Monitoring Dashboard

Access at `http://localhost:3333` (password in `.env`).

For remote access, the Cloudflare Tunnel URL is in the logs:

```bash
docker logs claudio-tunnel 2>&1 | grep trycloudflare
```

## Project Structure

```
Claudio/
├── .env.example            # Template for configuration
├── CLAUDE.md               # Context for Claude Code
├── GUIDA.md                # User guide (Italian)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── bot/
│   ├── main.py             # Entrypoint
│   ├── config.py            # All constants and env vars
│   ├── prompts.py           # System prompts
│   ├── claude_bridge.py     # Claude Agent SDK bridge
│   ├── voice.py             # STT + TTS
│   ├── monitor.py           # Event tracking + WebSocket
│   ├── ws_server.py         # Dashboard server
│   ├── projects.py          # Project discovery
│   ├── text_cleaner.py      # TTS text cleaning
│   ├── cleanup.py           # Periodic file cleanup
│   ├── auth.py              # User authorization
│   └── handlers/            # Telegram command handlers
├── scripts/
│   ├── entrypoint.sh
│   ├── setup_tts.sh
│   └── install_tts_service.sh
├── ideas/                   # Future project ideas
└── memory/                  # Persistent memory (Docker volume)
```

## Tech Stack

| Component | Technology |
|---|---|
| Bot framework | aiogram 3 |
| AI engine | Claude Agent SDK → Claude Code CLI |
| Auth | Claude Max subscription (OAuth token) |
| STT | faster-whisper (large-v3-turbo, int8) |
| TTS | Qwen3-TTS via MLX + Edge TTS fallback |
| Container | Docker (OrbStack) on ARM64 |
| Monitoring | aiohttp WebSocket + Next.js static |
| Tunnel | Cloudflare Quick Tunnel |
| Event storage | SQLite (7-day retention) |

## License

MIT License — see [LICENSE](LICENSE).
