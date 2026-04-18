# Claudio — Personal AI Assistant

Bot Telegram che usa Claude Agent SDK per fornire un assistente personale AI via Docker.

## Struttura
- `bot/main.py` — Entrypoint, wiring router e startup task in background
- `bot/config.py` — Tutte le costanti, variabili d'ambiente e hot-reload da `runtime_config.json`
- `bot/prompts.py` — System prompt (BASE_PROMPT, PROJECT_PROMPT_SUFFIX, PLANNING_PREFIX, MEMORY_SECTION)
- `bot/claude_bridge.py` — Bridge Claude Agent SDK, sessioni per-chat/progetto, asyncio.Lock, retry, memory injection
- `bot/memory.py` — Memoria persistente per-chat via Mem0 (Ollama + Qdrant, 100% locale)
- `bot/voice.py` — STT (faster-whisper) + TTS (Qwen3-TTS con fallback Edge TTS)
- `bot/text_cleaner.py` — Pulizia testo per TTS, split messaggi Telegram
- `bot/monitor.py` — Capture eventi, storage SQLite, broadcast WebSocket, metriche sistema
- `bot/ws_server.py` — Server aiohttp porta 3333: dashboard statica, WebSocket `/ws`, git action handler
- `bot/git_ops.py` — Operazioni git per il tab Changes (diff parsing, untracked files, stage, revert, commit, scan all projects)
- `bot/projects.py` — Discovery progetti e mapping Forum Topics
- `bot/cleanup.py` — Task periodico pulizia file uploads (>24h)
- `bot/auth.py` — Filtro utenti autorizzati
- `bot/handlers/_state.py` — Stato condiviso (bridge, topic_map, flags voice/plan)
- `bot/handlers/commands.py` — /start, /status, /new, /resume, /compact, /memories, /forget
- `bot/handlers/model.py` — /model, /opus, /sonnet, /haiku, /effort, /turns, /plan
- `bot/handlers/projects_cmds.py` — /projects, /link, /unlink
- `bot/handlers/voice_cmds.py` — /voice, /text
- `bot/handlers/kronos_cmds.py` — /predict, /accuracy (Kronos crypto predictions)
- `bot/handlers/messages.py` — Handler messaggi (testo, vocali, foto, documenti, send queue)
- `bot/market.py` — Market data aggregator: OHLCV, ticker, orderbook, indicatori tecnici (RSI, EMA, MACD, Bollinger, ATR) via ccxt + pandas-ta
- `bot/kronos.py` — Kronos advisor: model loading, OHLCV fetch, inference, SQLite, verifica, loop periodico
- `scripts/entrypoint.sh` — Startup container
- `docker-compose.yml` — Configurazione Docker (servizi: assistant, ollama, qdrant, tunnel)
- `Dockerfile` — Immagine Ubuntu 24.04, Node.js 22, ffmpeg
- `tests/test_git_ops.py` — Test per diff parsing e operazioni git (37 test)
- `tests/test_market.py` — Test per market data aggregator (31 test)
- `tests/test_memory.py` — Test per memoria persistente Mem0 (20 test)

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
- Tipi evento: message_received, query_start, tool_use, query_end, cost, stt_start, stt_end, tts_end, metrics, status, error, changes, kronos_prediction
- Metriche sistema pubblicate ogni 5 secondi
- Storico eventi in SQLite: /home/assistant/memory/monitor.db (retention 7 giorni)
- Al connect WebSocket, il server invia gli ultimi 100 eventi dalla SQLite + lo stato git di tutti i progetti
- WebSocket: heartbeat ping/pong ogni 30s (cleanup automatico connessioni zombie), max 20 client simultanei (503 se superato)
- Frontend: WebSocket si connette solo dopo autenticazione (`enabled` flag in `useWebSocket`), no retry se non autenticato
- Frontend: `useWebSocket` usa refs per callback (`onMessageRef`, `onHistoryRef`) così `connect` è stabile e non causa riconnessioni spurie
- Repo sorgente dashboard: github.com/MG84/claudio-monitor

## Changes tab (Code Review)
- Tab "Changes" nella dashboard per review dei diff — stile Fork (Git GUI)
- All'apertura della dashboard, scan automatico di tutti i progetti con modifiche pending
- Dopo ogni query_end su un progetto, `claude_bridge.py` emette evento `changes` con diff strutturato
- File untracked (nuovi, non in git) visibili con icona "?" e colore blu
- Backend: `bot/git_ops.py` esegue `git diff` + `git diff --cached` + `git ls-files --others`, parsa unified diff in JSON
- `get_all_projects_changes()` scansiona tutti i progetti git-enabled per lo stato iniziale
- Azioni dalla dashboard via WebSocket: git_stage, git_unstage, git_revert, git_revert_all, git_commit, git_diff, git_refresh_all
- Handler azioni in `bot/ws_server.py` → `_execute_git_action()`, `_refresh_all_changes()`
- Bottone "Refresh" nella Changes tab per aggiornare manualmente lo stato di tutti i progetti
- Validazione path: progetto sotto PROJECTS_BASE, file path no `..`, no assoluti
- Frontend: DiffViewer, FileCard, ChangesTab, CommitBar componenti in claudio-monitor
- Layout responsive: mobile stacked (accordion), desktop side-by-side (md: breakpoint)
- Test backend: `pytest tests/test_git_ops.py` (37 test)
- Test frontend: `npm test` in claudio-monitor (32 test, vitest + testing-library)

## Memoria persistente per-chat (Mem0)
- Memoria long-term per-chat via Mem0, 100% locale (Ollama + Qdrant in Docker)
- Stack: Qdrant (vector store), nomic-embed-text (embedding via Ollama), llama3.1:8b (estrazione fatti via Ollama)
- Servizi Docker: `claudio-ollama` (LLM + embedding), `claudio-qdrant` (vector store)
- Volumi persistenti: `ollama_data` (modelli), `qdrant_data` (memorie)
- Flusso: utente manda messaggio → `memory.search()` inietta ricordi nel system prompt → Claude risponde → `memory.add()` estrae fatti (fire-and-forget, usa testo puro utente via `user_text`)
- Separazione: **session** (SDK) = conversazione corrente (short-term) vs **memory** (Mem0/Qdrant) = fatti estratti (long-term)
- `/new` resetta la sessione ma preserva le memorie; rebuild Docker preserva tutto (volumi)
- Comandi: `/memories` lista ricordi, `/forget` cancella tutti i ricordi della chat
- Config: `bot/config.py` (costanti MEM0_*), `bot/memory.py` (wrapper), disabilitabile con `MEM0_ENABLED=false`
- `scripts/entrypoint.sh` aspetta Ollama (con timeout 60s) e pulla i modelli al primo avvio; skip se `MEM0_ENABLED=false`
- `OPENAI_API_KEY=not-needed` nel docker-compose.yml (workaround per code path interni di Mem0)
- Nomi modelli Ollama configurabili via env vars `MEM0_EMBEDDING_MODEL`, `MEM0_LLM_MODEL` (docker-compose + entrypoint)
- Ollama pinnato a versione `0.20.5` in docker-compose.yml
- Test: `pytest tests/test_memory.py` (20 test)

## Market Data (indicatori tecnici)
- Aggregatore dati di mercato multi-pair via ccxt (Binance, dati pubblici, no API key)
- Pairs configurabili: `TRADING_PAIRS` in config (default: BTC/USDT, ETH/USDT, SOL/USDT)
- Funzioni: `get_ohlcv()`, `get_ticker()`, `get_orderbook()`, `get_indicators()`, `get_market_summary()`
- Indicatori tecnici via `pandas-ta`: RSI(14), EMA(20/50/200), MACD(12/26/9), Bollinger(20,2), ATR(14)
- Cache con TTL configurabile: 60s OHLCV/indicatori, 30s ticker/orderbook
- Calcolo indicatori in thread separato via `asyncio.to_thread()` (CPU-bound)
- Exchange singleton con `enableRateLimit` per rispettare limiti Binance
- `get_market_summary()` produce snapshot testuale per injection nel contesto di Claude
- Config: `bot/config.py` (costanti `TRADING_PAIRS`, `MARKET_*`)
- File: `bot/market.py`
- Test: `pytest tests/test_market.py` (31 test)

## Kronos (crypto predictions)
- Advisor BTC/USDT basato su Kronos-small (24.7M params), inference CPU via `asyncio.to_thread()`
- Fetch candele OHLCV da Binance via `ccxt` (dati pubblici, no API key)
- Previsione: 12 candele avanti (12h con timeframe 1h), media di 5 sample
- Loop periodico ogni ora: predict + verify + emit evento dashboard `kronos_prediction`
- SQLite separato: `/home/assistant/memory/kronos.db` (tabella `predictions`)
- Schema: id, created_at, symbol, timeframe, current_price, predictions (JSON), verified, actual_prices (JSON), direction_correct, mae
- Verifica automatica: confronta previsioni passate con prezzi reali, calcola direction_correct e MAE
- Comandi Telegram: `/predict` (previsione manuale), `/accuracy` (statistiche)
- Config: `bot/config.py` (costanti `KRONOS_*`), disabilitabile con `KRONOS_ENABLED=false`
- Modello: repo Kronos clonato nel Dockerfile, solo `model/` (~50KB) in `/home/assistant/kronos_model/`
- Weights: ~100MB da HuggingFace, cached in volume Docker `hf_cache`
- File: `bot/kronos.py` (core), `bot/handlers/kronos_cmds.py` (comandi)
- Zero rischio finanziario — solo osservazione e tracking

## Gestione voci clonate
- Registro in `/home/assistant/memory/voices/voices.json`
- File originali WAV in `/home/assistant/memory/voices/originals/`
- Audio di prova in `/home/assistant/memory/voices/samples/`
- Flusso: Marco manda vocale → Claudio clona → salva nel registro → invia sample per valutazione → Marco decide se usarla
- Per attivare una voce senza rebuild: scrivere `{"TTS_VOICE": "<uuid>"}` in `/home/assistant/memory/runtime_config.json`
- Per attivare una voce con rebuild (persistente nel `.env`): aggiornare `TTS_VOICE=<uuid>` nel `.env` e rebuilda
