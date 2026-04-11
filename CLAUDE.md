# Claudio — Personal AI Assistant

Bot Telegram che usa Claude Agent SDK per fornire un assistente personale AI via Docker.

## Struttura
- `bot/main.py` — Router Telegram (aiogram), comandi, message handler
- `bot/claude_bridge.py` — Bridge verso Claude Code via Agent SDK, sessioni per-progetto
- `bot/git_ops.py` — Operazioni git per il tab Changes (diff parsing, stage, revert, commit)
- `bot/projects.py` — Discovery progetti e mapping Forum Topics
- `bot/auth.py` — Filtro utenti autorizzati
- `scripts/entrypoint.sh` — Startup container
- `docker-compose.yml` — Configurazione Docker
- `Dockerfile` — Immagine container
- `tests/test_git_ops.py` — Test per diff parsing e operazioni git

## Regole
- Il bot gira dentro Docker, i progetti sono montati in /home/assistant/projects/
- L'auth usa OAuth token di Claude Max subscription (CLAUDE_CODE_OAUTH_TOKEN)
- Solo gli utenti in TELEGRAM_ALLOWED_USERS possono interagire
- Dopo modifiche: `docker compose down && docker compose up -d --build`
- **Dopo ogni cambiamento al progetto, aggiornare SEMPRE la documentazione (GUIDA.md, CLAUDE.md, IMPLEMENTAZIONE.md se rilevante)**
- Non considerare mai completa una modifica senza aver aggiornato la documentazione

## Monitoring
- Dashboard locale su porta 3333 (servita dal bot via aiohttp)
- Eventi inviati via WebSocket diretto (/ws) — zero servizi cloud
- Cloudflare Tunnel per accesso remoto (URL nei log di claudio-tunnel)
- Tipi evento: message_received, query_start, tool_use, query_end, cost, stt_start, stt_end, tts_end, metrics, status, error, changes
- Metriche sistema pubblicate ogni 5 secondi
- Storico eventi in SQLite: /home/assistant/memory/monitor.db (retention 7 giorni)
- Al connect WebSocket, il server invia gli ultimi 100 eventi dalla SQLite
- Repo sorgente dashboard: github.com/MG84/claudio-monitor

## Changes tab (Code Review)
- Tab "Changes" nella dashboard per review dei diff dopo ogni query Claude
- Dopo ogni query_end su un progetto, `claude_bridge.py` emette evento `changes` con diff strutturato
- Backend: `bot/git_ops.py` esegue `git diff` + `git diff --cached`, parsa unified diff in JSON
- Azioni dalla dashboard via WebSocket: git_stage, git_unstage, git_revert, git_revert_all, git_commit, git_diff
- Handler azioni in `bot/ws_server.py` → `_execute_git_action()`
- Validazione path: progetto sotto PROJECTS_BASE, file path no `..`, no assoluti
- Frontend: DiffViewer, FileCard, ChangesTab, CommitBar componenti in claudio-monitor
- Layout responsive: mobile stacked (accordion), desktop side-by-side (md: breakpoint)
- Test backend: `pytest tests/test_git_ops.py` (30 test)
- Test frontend: `npm test` in claudio-monitor (27 test, vitest + testing-library)

## Gestione voci clonate
- Registro in `/home/assistant/memory/voices/voices.json`
- File originali WAV in `/home/assistant/memory/voices/originals/`
- Audio di prova in `/home/assistant/memory/voices/samples/`
- Flusso: Marco manda vocale → Claudio clona → salva nel registro → invia sample per valutazione → Marco decide se usarla
- Per attivare una voce: aggiornare `TTS_VOICE=<uuid>` nel `.env` e rebuilda
