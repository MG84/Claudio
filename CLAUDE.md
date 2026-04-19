# Claudio — Personal AI Assistant

Bot Telegram che usa Claude Agent SDK per fornire un assistente personale AI via Docker.

## Struttura
- `bot/main.py` — Entrypoint, wiring router e startup task in background
- `bot/config.py` — Tutte le costanti, variabili d'ambiente e hot-reload da `runtime_config.json`
- `bot/prompts.py` — System prompt (BASE_PROMPT, PROJECT_PROMPT_SUFFIX, PLANNING_PREFIX, MEMORY_SECTION, TRADING_PROMPT)
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
- `bot/handlers/trading_cmds.py` — /portfolio, /market, /trades, /mode, /kill, /autonomous, /scan
- `bot/handlers/messages.py` — Handler messaggi (testo, vocali, foto, documenti, send queue)
- `bot/market.py` — Market data aggregator: OHLCV, ticker, orderbook, indicatori tecnici (RSI, EMA, MACD, Bollinger, ATR) via ccxt + pandas-ta
- `bot/chronos_predictor.py` — Chronos-Bolt: univariate close-price forecasting con bande di incertezza (quantili)
- `bot/kronos.py` — Kronos advisor: model loading, OHLCV fetch, inference, SQLite, verifica, loop periodico, multi-pair, confidence scoring
- `bot/trading.py` — Execution layer: paper + live trading via ccxt, risk manager hard-coded, trade journal SQLite
- `bot/scanner.py` — Market scanner (hourly) + risk monitor (every 5 min), background loops
- `scripts/entrypoint.sh` — Startup container
- `scripts/deploy_dashboard.sh` — Deploy script: build claudio-monitor, copy to dashboard/, rebuild Docker
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
- Tipi evento: message_received, query_start, tool_use, query_end, cost, stt_start, stt_end, tts_end, metrics, status, error, changes, kronos_prediction, chronos_prediction, market_scan, portfolio_update, risk_alert, trade_executed
- Metriche sistema pubblicate ogni 5 secondi
- Storico eventi in SQLite: /home/assistant/memory/monitor.db (retention 7 giorni)
- Al connect WebSocket, il server invia gli ultimi 100 eventi dalla SQLite + lo stato git di tutti i progetti
- WebSocket: heartbeat ping/pong ogni 30s (cleanup automatico connessioni zombie), max 20 client simultanei (503 se superato)
- Frontend: WebSocket si connette solo dopo autenticazione (`enabled` flag in `useWebSocket`), no retry se non autenticato
- Frontend: `useWebSocket` usa refs per callback (`onMessageRef`, `onHistoryRef`) così `connect` è stabile e non causa riconnessioni spurie
- Repo sorgente dashboard: github.com/MG84/claudio-monitor

### REST API Endpoints
- `GET /api/market/{pair}/{timeframe}` — OHLCV candles, ticker, and technical indicators (pair format: BTC-USDT)
- `GET /api/portfolio` — balance, positions, daily P&L, risk status
- `GET /api/trades?limit=N` — trade history with reasoning (default 20, max 100)
- `GET /api/kronos` — Kronos prediction history
- `GET /api/chronos` — Chronos-Bolt prediction history
- Tutti gli endpoint richiedono autenticazione (cookie session token)
- CORS abilitato per localhost:3000 (Next.js dev server)
- Auth token deterministico (stabile tra restart), calcolato via SHA-256 da password

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
- Multi-pair: loop su `TRADING_PAIRS`, non solo BTC/USDT
- `get_latest_prediction(pair?)` — ultima previsione dal DB senza inference
- `predict_pair(pair, timeframe?)` — previsione per qualsiasi coppia
- `get_prediction_confidence(pair?)` — confidenza 0-1 basata su storico, scalata per sample size
- Comandi Telegram: `/predict` (previsione manuale), `/accuracy` (statistiche)
- Config: `bot/config.py` (costanti `KRONOS_*`), disabilitabile con `KRONOS_ENABLED=false`
- Modello: repo Kronos clonato nel Dockerfile, solo `model/` (~50KB) in `/home/assistant/kronos_model/`
- Weights: ~100MB da HuggingFace, cached in volume Docker `hf_cache`
- File: `bot/kronos.py` (core), `bot/handlers/kronos_cmds.py` (comandi)
- Zero rischio finanziario — solo osservazione e tracking

## Chronos-Bolt (univariate forecasting)
- Secondo segnale previsionale accanto a Kronos, basato su amazon/chronos-bolt-small (ChronosBoltPipeline)
- IMPORTANTE: usa `ChronosBoltPipeline` (NON `ChronosPipeline`) — classe dedicata per modelli Bolt in chronos-forecasting>=2.2.0
- `from_pretrained` usa `dtype=torch.float32` (NON `torch_dtype`, deprecato)
- Il predict ritorna tensor (batch, 9, horizon) con 9 quantili fissi [0.1..0.9] — q10=indice 0, q50=indice 4, q90=indice 8
- Input: close prices (ultimi 400 candles via `bot/market.py` `get_ohlcv()`)
- Output: quantile forecasts (q10, q50, q90) per bande di incertezza + direzione + change%
- Previsione: 12 candele avanti (12h con timeframe 1h), inference CPU via `asyncio.to_thread()`
- Loop periodico ogni ora per tutti i TRADING_PAIRS: predict + verify + emit evento `chronos_prediction`
- SQLite: tabella `chronos_predictions` in `/home/assistant/memory/kronos.db` (DB condiviso con Kronos)
- Schema: id, created_at, symbol, timeframe, current_price, point_forecast (JSON), quantile_forecast (JSON), direction, change_pct, verified, actual_prices, direction_correct, mae
- Verifica automatica: confronta previsioni passate con prezzi reali, calcola direction_correct e MAE
- Config: `bot/config.py` (costanti `CHRONOS_*`), disabilitabile con `CHRONOS_ENABLED=false`
- Weights da HuggingFace, cached in volume Docker `hf_cache`
- File: `bot/chronos_predictor.py`
- Se Kronos e Chronos-Bolt concordano sulla direzione → maggiore confidenza; se discordano → cautela

## Trading (execution layer)
- Due modalita': **paper** (simulato in SQLite) e **live** (ordini reali via ccxt)
- Paper: simulato localmente in SQLite (`/home/assistant/memory/trades.db`)
- Live: ordini reali sull'exchange via `ccxt.async_support` (richiede `EXCHANGE_API_KEY` + `EXCHANGE_API_SECRET`)
- Exchange singleton: `_get_live_exchange()` crea istanza ccxt con API key, `enableRateLimit=True`
- `set_mode("live")` valida che le API key siano configurate prima di attivare
- Limiti di rischio hard-coded in Python (NON nel prompt, NON bypassabili):
  - Max posizione: 20% del portfolio (`MAX_POSITION_PCT`)
  - Max posizioni aperte: 3 (`MAX_OPEN_POSITIONS`)
  - Max perdita giornaliera: 5% (`MAX_DAILY_LOSS_PCT`) → stop trading
  - Max drawdown: 15% (`MAX_DRAWDOWN_PCT`) → kill switch automatico
  - Stop-loss obbligatorio (`STOP_LOSS_REQUIRED`)
  - Max trade al giorno: 10 (`MAX_TRADES_PER_DAY`)
- `risk_check()` eseguito PRIMA di ogni trade in ENTRAMBE le modalita', non bypassabile
- Funzioni: `place_order()`, `close_position()`, `cancel_order()`, `emergency_close_all()`
- `place_order()`: paper simula in SQLite, live invia `create_order()` via ccxt + log in SQLite
- `close_position()`: paper aggiorna balance, live invia ordine market inverso via ccxt
- `emergency_close_all()`: chiude tutte le posizioni aperte (paper o live)
- Portfolio: `get_balance()`, `get_positions()`, `get_trade_history()`, `get_daily_pnl()`, `get_risk_status()`
- Trade journal: ogni trade salvato con timestamp, parametri, esito, reasoning di Claude, mode (paper/live)
- Config: `bot/config.py` (costanti `TRADING_*`, `MAX_*`, `EXCHANGE_*`), disabilitabile con `TRADING_ENABLED=false`
- Exchange config: `EXCHANGE_ID` (default kraken), `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`
- File: `bot/trading.py`

## Trading Commands (Telegram)
- `/portfolio` — bilancio, posizioni aperte, P&L giornaliero
- `/market [pair]` — snapshot mercato con indicatori + previsioni Kronos/Chronos (default BTC/USDT)
- `/trades [n]` — ultimi N trade (default 10) con P&L
- `/mode paper|live` — switch modalita' (live richiede "CONFERMA")
- `/kill` — emergency close all, chiusura immediata tutte le posizioni
- `/autonomous on|off` — abilita/disabilita trading autonomo
- `/scan` — scan completo: mercato + previsioni + risk status + posizioni
- Tutti i comandi gated da `is_allowed_user()`, graceful degradation se `TRADING_ENABLED=false`
- File: `bot/handlers/trading_cmds.py`

## Market Scanner + Risk Monitor
- Market scanner loop (ogni ora): assembla contesto completo (indicatori, Kronos, Chronos, portfolio)
- Due modalita' operative:
  - **Autonomous** (`/autonomous on`): scanner invia il brief a Claude via `bridge.query()`, Claude analizza e decide se fare trade con `place_order()` o HOLD. Risposta inviata su Telegram.
  - **Supervised** (default): scanner invia il brief direttamente su Telegram per review umana
- Concordanza segnali: se Kronos e Chronos concordano → segnalato, se discordano → cautela
- Risk monitor loop (ogni 5 min): controlla limiti di rischio
  - Drawdown >= 15% → `emergency_close_all()` + disabilita autonomous
  - Perdita giornaliera >= 5% → disabilita autonomous
  - Warning a 80% dei limiti → emit `risk_alert`
  - Emit `portfolio_update` ad ogni ciclo
- Notifiche Telegram via first user in `TELEGRAM_ALLOWED_USERS`
- File: `bot/scanner.py`

## System Prompt (Trading)
- Quando `TRADING_ENABLED=true`, il system prompt include `TRADING_PROMPT` con 3 ruoli:
  - **Analyst**: legge previsioni, indicatori, cerca pattern e divergenze
  - **Trader**: decide entrate/uscite, spiega sempre il reasoning
  - **Risk Manager**: mai >2% per trade, sempre stop-loss, HOLD e' valido
- Lista strumenti disponibili e limiti hard-coded nel prompt
- Regola d'oro: meglio perdere un'opportunita' che perdere capitale

## Kraken CLI MCP (market data + paper trading)
- Kraken CLI v0.3.1 binary ARM64 installato nel Dockerfile in `/usr/local/bin/kraken`
- MCP server nativo: `kraken mcp -s market,paper` — comunicazione via stdio con Claude Agent SDK
- Servizi MCP abilitati di default: `market` (dati pubblici) + `paper` (paper trading spot)
- Market data: ticker, OHLC, orderbook, trades, spread — dati pubblici Kraken, no API key
- Paper trading: buy/sell con prezzi live Kraken, fee simulate 0.26% taker, persistenza locale
- Configurazione MCP in `bot/claude_bridge.py`: `mcp_servers` dict passato a `ClaudeAgentOptions`
- Se `KRAKEN_API_KEY` e `KRAKEN_API_SECRET` sono configurati, vengono passati come env al processo MCP
- Servizi configurabili via `KRAKEN_MCP_SERVICES` (default: `market,paper`); per account info: `market,account,paper`
- Config: `bot/config.py` (costanti `KRAKEN_CLI_*`), disabilitabile con `KRAKEN_CLI_ENABLED=false`
- Prompt: sezione "Kraken CLI (MCP)" in `TRADING_PROMPT` (`bot/prompts.py`)
- Ruolo: complementare a ccxt — ccxt resta layer primario per indicatori, previsioni ML, risk management
- Analisi decisionale: `docs/TRADING_TOURNAMENT.md` (tournament theory, 6 contendenti, verdetto ibrido)
- Analisi tecnica: `docs/KRAKEN_CLI_ANALYSIS.md` (151 comandi, MCP server, paper trading, limitazioni)
- Docker: env vars `KRAKEN_CLI_ENABLED`, `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` in docker-compose.yml

## Gestione voci clonate
- Registro in `/home/assistant/memory/voices/voices.json`
- File originali WAV in `/home/assistant/memory/voices/originals/`
- Audio di prova in `/home/assistant/memory/voices/samples/`
- Flusso: Marco manda vocale → Claudio clona → salva nel registro → invia sample per valutazione → Marco decide se usarla
- Per attivare una voce senza rebuild: scrivere `{"TTS_VOICE": "<uuid>"}` in `/home/assistant/memory/runtime_config.json`
- Per attivare una voce con rebuild (persistente nel `.env`): aggiornare `TTS_VOICE=<uuid>` nel `.env` e rebuilda
