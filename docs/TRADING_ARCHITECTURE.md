# Agente Trading Autonomo — Architettura Completa

## Context

L'obiettivo e' un agente con cui parli su Telegram che: analizza i mercati, decide la strategia, propone azioni, e le esegue — anche in totale autonomia. Un singolo agente conversazionale (Claudio) con tutti gli strumenti necessari per operare end-to-end.

Claudio e' gia' un agente AI con tool (Read, Write, Bash, WebSearch, etc.) via Claude Agent SDK. L'architettura si basa su **estendere le sue capacita'** con nuovi moduli, non su costruire un sistema separato.

---

## Analisi critica del piano originale

### Il problema fondamentale: strategy.py e' un rules engine, non un agente

Il piano descrive un `strategy.py` che combina segnali con if/else:
```
Kronos UP + TimesFM UP → confidence 0.7 → BUY
```

Ma il tuo obiettivo e' un **personal trader che ragiona**, non un bot con regole statiche. Claude e' gia' il cervello — non ha senso costruirgli un cervellino parallelo in Python con logica cablata. Il vero flusso dovrebbe essere:

```
Dati (previsioni, indicatori, news, portfolio)
    ↓
Claude ragiona: "Kronos prevede UP ma il RSI e' a 78,
siamo in ipercomprato. La Fed ha alzato i tassi ieri.
Meglio aspettare un pullback."
    ↓
Decisione: HOLD (con spiegazione)
```

`strategy.py` diventa un **data aggregator** che prepara il contesto per Claude, non un decision engine. Claude decide, Python enforza i limiti di rischio.

### TimesFM: l'alternativa migliore e' Chronos-Bolt

**Problemi con TimesFM:**
- 200M params, ~800MB — pesante su CPU ARM, 30-60 sec per inference
- Architettura univariate — ogni serie forecast indipendentemente
- Richiede Flax/JAX — dependency tree pesante in Docker

**Chronos-Bolt (Amazon) e' oggettivamente meglio per questo caso:**
- 250x piu' veloce del Chronos originale, 20x meno memoria
- Gira su CPU senza problemi (T5-based, pure PyTorch)
- 4 taglie: tiny (9M), mini, small, base — si scala
- 5% piu' accurato dell'originale Chronos su benchmark
- HuggingFace transformers standard — zero dipendenze esotiche
- Gia' available: `amazon/chronos-bolt-small` su HuggingFace

**Alternativa top-tier per multivariate: Moirai 2.0 (Salesforce)**
- "Any-variate attention" — modella correlazioni tra asset (BTC + ETH + macro)
- Decoder-only + MoE — architettura moderna
- Ma richiede GPU — skip per ora, tenere come upgrade futuro

**CAVEAT IMPORTANTE:** Studi recenti mostrano che i benchmark dei time-series foundation models sono gonfiati del 47-184% per overlap tra training e test data. Non fidarsi ciecamente delle metriche — il vero test e' la performance live su crypto, dove le distribuzioni cambiano continuamente.

### Kraken CLI: confermato, ha anche MCP server

Il binary arm64 esiste: `kraken-cli-aarch64-unknown-linux-gnu.tar.gz` su GitHub releases.

Dettaglio che cambia le carte in tavola: **Kraken CLI ha un MCP server built-in** (`kraken mcp`). Questo significa che Claude potrebbe usare i tool Kraken nativamente tramite MCP, senza wrapper Python. Ma questo e' un'ottimizzazione futura — per ora il wrapper Python con risk checks e' piu' sicuro e controllabile.

**Paper trading built-in:**
```bash
kraken paper init --balance 10000
kraken paper buy BTCUSD 0.01
kraken paper status
```
Zero API key necessarie. Prezzi live da Kraken public API. Stato persistente locale.

### Solo BTC/USDT e' troppo limitante

Un personal trader deve poter guardare piu' asset. Non serve supportare 500 pair, ma almeno:
- BTC/USDT (primario)
- ETH/USDT
- SOL/USDT
- Eventualmente altri su richiesta

Il modulo market deve essere multi-pair. Kronos e Chronos-Bolt possono generare previsioni per qualsiasi pair — basta passare dati diversi.

### Manca: news/sentiment analysis strutturato

Il piano dice "News/sentiment via WebSearch (gia' disponibile)" ma non costruisce nulla. Le news market-moving (regolazioni, ETF, hack di exchange, dichiarazioni Fed) contano molto piu' del pattern matching sui prezzi per crypto. Servono:
- Ricerca periodica news crypto (WebSearch gia' disponibile)
- Parsing e summarization delle news rilevanti
- Feed al contesto di Claude per il reasoning

### Manca: backtesting

Non c'e' modo di testare la strategia su dati storici prima di andare live. Minimo necessario:
- Replay delle previsioni passate contro prezzi reali (Kronos gia' verifica, estendere)
- Simulazione decisioni su dati storici per capire se il sistema avrebbe fatto soldi

### Il confidence scoring e' naive

"Kronos UP + TimesFM UP = 0.7" e' arbitrario. Due modelli che guardano gli stessi dati storici possono concordare per le stesse ragioni sbagliate. La vera confidence dovrebbe venire da:
- Accuracy storica dei modelli su quel tipo di mercato (trending vs ranging)
- Volatilita' attuale (alta volatilita' = bassa confidence)
- Ampiezza delle bande di incertezza di Chronos-Bolt
- Coerenza tra timeframe diversi

### Lo strategy loop ogni ora e' troppo rigido

I mercati non si muovono a intervalli fissi. Servono anche trigger event-driven:
- Prezzo attraversa un livello chiave → rivaluta
- Notizia market-moving → rivaluta
- Posizione in perdita significativa → rivaluta subito

---

## Alternative analizzate (Tournament Theory)

### Framework AI trading open-source nel 2026

| Framework | Approccio | Pro | Contro | Verdetto |
|---|---|---|---|---|
| **AI-Trader (HKUDS)** | Marketplace di agenti autonomi, FastAPI + OpenClaw | Copy-trading, multi-asset, collective intelligence | Infrastruttura pesante, progetto accademico | Ispirazione, non adozione |
| **TradingAgents (Tauric)** | 7 agenti specializzati (analyst, trader, risk mgr) su LangGraph | Architettura multi-agent matura, supporta Claude 4.x | Over-engineered per un singolo utente, dipendenza LangGraph | Buone idee da copiare |
| **AgenticTrading (Open-Finance-Lab)** | Agent pools con MCP + A2A, DAG execution | Usa MCP (!), memory agent, interpretabile | Accademico, early stage | Architettura MCP interessante |
| **FinMem** | LLM + layered memory per stock trading | Memoria a livelli, decision framework | Solo azioni, non crypto, non mantenuto | Skip |
| **Hummingbot** | Market-making bot open-source | Maturo, multi-exchange, battle-tested | Non e' un agente AI, solo regole statiche | Irrelevante |
| **Costruire dentro Claudio** | Estendere l'agente esistente | Zero overhead, Claude e' gia' il cervello, infrastruttura gia' pronta | Devi costruire tutto | **Vincitore** |

**Verdetto:** Nessuno di questi framework si integra bene con la nostra architettura. Claudio ha gia' Claude come cervello, tool system, memoria, Telegram. Costruire dentro Claudio e' la scelta giusta. Da TradingAgents copiamo l'idea di dare a Claude ruoli multipli (analyst, trader, risk manager) nel prompt, non come agenti separati.

### Modelli forecasting

| Modello | Params | CPU ARM? | Speed | Multivariate | Uncertainty bands | Verdetto |
|---|---|---|---|---|---|---|
| **Kronos-small** (gia' in uso) | 24.7M | Si | Veloce | Si (OHLC) | No | Tenere come segnale primario |
| **TimesFM 2.5** | 200M | Lento | 30-60s | No | Si (quantili) | Troppo pesante, Flax/JAX problematico |
| **Chronos-Bolt small** | ~48M | Si | Molto veloce | No | Si (quantili) | **Vincitore come secondo segnale** |
| **Chronos-2** | 120M | GPU preferred | Veloce su GPU | Si | Si | Upgrade futuro se si aggiunge GPU |
| **Moirai 2.0** | Varies | GPU preferred | Veloce | Si (any-variate!) | Si | Upgrade futuro, best multivariate |
| **Lag-Llama** | 7M | Si | Moderato | No | Si (distribuzione piena) | Troppo piccolo, meno accurato |

**Verdetto:** Chronos-Bolt small al posto di TimesFM. Stesse feature utili (bande di incertezza), CPU-friendly, PyTorch nativo, nessuna dipendenza esotica.

### Exchange execution

| Tool | Pro | Contro | Verdetto |
|---|---|---|---|
| **ccxt** (gia' nel progetto) | Multi-exchange, gia' usato, async support | No paper trading nativo (implementato in SQLite) | **Vincitore — usato per data + execution** |
| **Kraken CLI** | Binary arm64, paper trading built-in, MCP server | Solo Kraken, binary esterno | Opzione futura per MCP |
| **krakenex** | Leggero | Non mantenuto, no paper | Skip |

**Verdetto:** ccxt per tutto (data fetching da Binance + live execution su qualsiasi exchange). Paper trading custom in SQLite.

---

## Architettura rivista

```
Telegram (Marco)
    │
    ▼
Claudio (Claude Agent SDK)
    │
    ├── CERVELLO: Claude ragiona, decide, spiega
    │   └── System prompt con ruoli: Analyst + Trader + Risk Manager
    │
    ├── OCCHI: Market intelligence (data per Claude)
    │   ├── Kronos predictions — OHLC multivariate (gia' fatto)
    │   ├── Chronos-Bolt predictions — close univariate + bande incertezza
    │   ├── Market data via CCXT (OHLCV, ticker, orderbook) — multi-pair
    │   ├── Technical indicators (RSI, EMA, Bollinger, MACD, ATR)
    │   └── News digest via WebSearch (strutturato, periodico)
    │
    ├── BRACCIA: Execution
    │   ├── ccxt (paper + live trading, multi-exchange)
    │   └── Risk manager (hard limits in Python, non bypassabili)
    │
    ├── MEMORIA: Tracking
    │   ├── kronos.db — previsioni e accuracy (gia' fatto)
    │   ├── trades.db — ordini, posizioni, P&L
    │   ├── Mem0 — memoria conversazionale (gia' fatto)
    │   └── Journal — trade rationale log (perche' ha deciso cosa)
    │
    └── LOOP AUTONOMI: Background tasks
        ├── Kronos + Chronos-Bolt loop — predizione oraria (parallele)
        ├── Market scanner — assembla contesto per Claude, trigger su eventi
        └── Risk monitor — controlla posizioni, drawdown, kill switch
```

### Differenza chiave: Claude decide, Python esegue

Il vecchio piano:
```
Kronos + TimesFM + indicatori → strategy.py (if/else) → BUY/SELL/HOLD → trading.py
```

Il nuovo piano:
```
market.py assembla contesto completo (previsioni, indicatori, news, portfolio, rischi)
    ↓
Claude riceve il contesto nel system prompt o come tool result
    ↓
Claude ragiona: analizza, pondera, decide, spiega il perche'
    ↓
Claude chiama tool: place_order(BTC/USDT, buy, 0.001, stop_loss=-2%)
    ↓
trading.py: risk_check() → PASS/DENIED (limiti in codice, non nel prompt)
    ↓
ccxt esegue (paper in SQLite o live su exchange)
```

Vantaggi:
- Claude puo' integrare informazioni qualitative (news, macro, sentiment) — un rules engine no
- Claude spiega il reasoning in italiano — debugging molto piu' facile
- Nessun confidence score arbitrario — Claude valuta tutto insieme come farebbe un trader umano
- Puo' decidere di NON tradare per ragioni che un if/else non catturerebbe mai

---

## Stato implementazione

Tutti i 7 step sono stati implementati e deployati. Di seguito lo stato di ciascuno.

### 1. `bot/market.py` — Market data aggregator (multi-pair) ✅ COMPLETATO
- `get_ohlcv(pair, timeframe, limit)` — da Binance via ccxt (dati pubblici, no API key)
- `get_ticker(pair)` — prezzo attuale, volume 24h, variazione
- `get_orderbook(pair, depth)` — bid/ask spread
- `get_indicators(pair, timeframe)` — RSI(14), EMA(20/50/200), MACD(12/26/9), Bollinger(20,2), ATR(14) via pandas-ta
- `get_market_summary(pairs)` — snapshot completo per Claude (formattato come testo)
- Cache con TTL: 60s OHLCV/indicatori, 30s ticker/orderbook
- Exchange singleton con `enableRateLimit`
- Calcolo indicatori in thread separato via `asyncio.to_thread()` (CPU-bound)
- Test: `pytest tests/test_market.py` (31 test)

### 2. `bot/chronos_predictor.py` — Chronos-Bolt come secondo segnale ✅ COMPLETATO
- Usa `ChronosBoltPipeline` (NON `ChronosPipeline`) — classe dedicata per modelli Bolt
- `from_pretrained` con `dtype=torch.float32` (NON `torch_dtype`, deprecato)
- Il predict ritorna tensor (batch, 9, horizon) con 9 quantili fissi [0.1..0.9]
- Quantili estratti: q10=indice 0, q50=indice 4, q90=indice 8
- Richiede `chronos-forecasting>=2.2.0`
- Loop periodico ogni ora per tutti i TRADING_PAIRS
- Verifica automatica previsioni passate (direction_correct, MAE)
- SQLite: tabella `chronos_predictions` in `kronos.db` (DB condiviso con Kronos)

### 3. `bot/trading.py` — Execution layer con risk manager ✅ COMPLETATO
**DEVIAZIONE dal piano:** Paper + live implementati in puro Python con ccxt + SQLite, NON con Kraken CLI.
Motivazione: puro Python e' piu' testabile, nessuna dipendenza binaria esterna, risk checks integrati nativamente, ccxt supporta 100+ exchange.

- `place_order(side, pair, type, volume, price?, stop_loss?, take_profit?)` — risk check + execute
  - Paper: simula in SQLite
  - Live: invia ordine reale via `ccxt.async_support` + log in SQLite
- `close_position(trade_id, close_price?)` — P&L calculation
  - Paper: aggiorna balance in SQLite
  - Live: invia ordine market inverso via ccxt + log in SQLite
- `cancel_order(trade_id)` — paper: restituisce fondi, live: chiude via market order
- `emergency_close_all()` → kill switch (chiude tutto, paper o live)
- `risk_check()` eseguito PRIMA di ogni trade in ENTRAMBE le modalita' — 6 check, non bypassabile
- `_get_live_exchange()` — singleton ccxt con API key, `enableRateLimit=True`
- `set_mode("live")` valida che `EXCHANGE_API_KEY` + `EXCHANGE_API_SECRET` siano configurate
- `log_trade_rationale(trade_id, reasoning)` — salva reasoning di Claude
- Portfolio: `get_balance()`, `get_positions()`, `get_trade_history()`, `get_daily_pnl()`, `get_risk_status()`
- SQLite in `/home/assistant/memory/trades.db` (WAL mode)
- Mode: `paper` (default) / `live` (richiede API key + conferma esplicita)
- Config exchange: `EXCHANGE_ID` (default kraken), `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`

### 4. Espandere `bot/kronos.py` ✅ COMPLETATO
- `get_latest_prediction(pair?)` — ultima previsione dal DB senza inference
- `predict_pair(pair, timeframe?)` — previsione per qualsiasi coppia
- `get_prediction_confidence(pair?)` — confidenza 0-1 basata su storico, scalata per sample size
- `kronos_loop()` itera su tutti i `TRADING_PAIRS` (non solo BTC/USDT)
- `_run_inference()` accetta parametro `timeframe` (non piu' hardcoded)

### 5. Kraken CLI nel container ✅ IMPLEMENTATO come MCP server complementare
Kraken CLI v0.3.1 installato nel Dockerfile (`/usr/local/bin/kraken`). Integrato come MCP server nativo per Claude Agent SDK (stdio transport). ccxt resta il layer primario per trading e risk management.

**Approccio ibrido** (analisi completa in `docs/TRADING_TOURNAMENT.md`):
- ccxt: layer primario — indicatori tecnici, previsioni ML, risk management hard-coded, multi-exchange
- Kraken CLI MCP: layer complementare — market data Kraken, paper trading con prezzi live
- Claude ha due canali: tool Python (ccxt) + MCP diretto (Kraken CLI)

Config: `KRAKEN_CLI_ENABLED=true`, `KRAKEN_MCP_SERVICES=market,paper` (default, safe, no API key)

### 6. `bot/handlers/trading_cmds.py` — Comandi Telegram ✅ COMPLETATO
- `/portfolio` — bilancio, posizioni aperte, P&L giornaliero
- `/market [pair]` — snapshot mercato con indicatori + previsioni Kronos/Chronos (default BTC/USDT)
- `/trades [n]` — storico trade recenti con P&L
- `/mode paper|live` — switch (live richiede "CONFERMA" testuale)
- `/kill` — emergency close all
- `/autonomous on|off` — abilita/disabilita trading autonomo
- `/scan` — scan completo: mercato + previsioni + risk status + posizioni
- Tutti gated da `is_allowed_user()`, graceful degradation se `TRADING_ENABLED=false`

### 7. Market scanner + Risk monitor (background tasks) ✅ COMPLETATO
**Market scanner** (`bot/scanner.py`):
- Loop orario, aspetta che Kronos e Chronos siano ready
- Assembla contesto: indicatori + previsioni + portfolio + rischio
- Concordanza segnali: se Kronos e Chronos concordano → segnalato
- Due modalita':
  - **Autonomous** (`/autonomous on`): invia contesto a Claude via `bridge.query()`, Claude analizza e decide (trade o HOLD), risposta su Telegram
  - **Supervised** (default): invia brief direttamente su Telegram per review umana

**Risk monitor** (`bot/scanner.py`):
- Loop ogni 5 minuti
- Drawdown >= 15% → `emergency_close_all()` + disabilita autonomous
- Perdita giornaliera >= 5% → disabilita autonomous
- Warning a 80% dei limiti → emit `risk_alert`
- Emit `portfolio_update` ad ogni ciclo

**NON implementato (trigger event-driven):**
- Variazione prezzo > X% → market scan immediato
- Notizia rilevante → market scan
- Posizione in perdita significativa → alert immediato
Questi restano come upgrade futuri.

### 8. System prompt trading (`bot/prompts.py`) ✅ COMPLETATO
- `TRADING_PROMPT` con 3 ruoli: Analyst, Trader, Risk Manager
- Iniettato nel system prompt quando `TRADING_ENABLED=true` (in `claude_bridge.py`)
- Lista strumenti disponibili e limiti hard-coded nel prompt
- Regola d'oro: meglio perdere un'opportunita' che perdere capitale

### 9. Documentazione ✅ COMPLETATO
- CLAUDE.md aggiornato con tutte le sezioni trading
- docs/TRADING_ARCHITECTURE.md — questo documento

### Non ancora implementato
- **News/sentiment analysis** — WebSearch periodico + summarization (previsto ma non prioritario)
- **Backtesting** — replay previsioni passate su dati storici
- **Trigger event-driven** — variazione prezzo, notizie, perdita significativa
- **Position sizing Half-Kelly + ATR** — attualmente size manuale, non calcolato automaticamente
- **Trading dashboard** — piano in `docs/TRADING_DASHBOARD.md` (frontend Next.js)

---

## Safety architecture

**Principio:** i limiti sono nel CODICE Python, non nel prompt. Claude puo' sbagliare — il codice no.

```
Claude dice: "compra 50% del portfolio"
    ↓
trading.py: risk_check() → DENIED (max 20% per posizione)
    ↓
Claude riceve: "Trade rifiutato: supera max position size (20%)"
```

**Limiti hard-coded in `bot/config.py`:**

```python
# ── Trading safety limits ────────────────────────────
TRADING_MODE = "paper"                 # "paper" o "live"
TRADING_AUTONOMOUS = False             # se True, esegue senza conferma
MAX_POSITION_PCT = 0.20                # max 20% del capitale per posizione
MAX_OPEN_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 0.05              # stop trading dopo 5% loss giornaliero
MAX_DRAWDOWN_PCT = 0.15                # kill switch a 15% drawdown dal picco
STOP_LOSS_REQUIRED = True              # ogni trade DEVE avere stop-loss
MAX_TRADES_PER_DAY = 10
TRADING_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
```

**Position sizing: half-Kelly + ATR-based**

Non size fisso. La dimensione della posizione si adatta:
- **Half-Kelly:** calcola size ottimale basata su edge storico, poi dimezza (conservativo)
- **ATR-based cap:** se ATR alto (volatilita'), riduci size proporzionalmente
- **Hard cap:** mai oltre MAX_POSITION_PCT indipendentemente dai calcoli

**Livelli di autonomia:**

| Livello | Comportamento |
|---|---|
| `autonomous=False` (default) | Claude propone, Marco conferma su Telegram |
| `autonomous=True, mode=paper` | Esegue paper trade automaticamente |
| `autonomous=True, mode=live` | Esegue trade reali (con tutti i limiti hard-coded) |

---

## Dipendenze aggiuntive

```
# requirements.txt (nuove)
pandas-ta>=0.3.0         # indicatori tecnici (RSI, EMA, MACD, Bollinger, ATR)
```

Chronos-Bolt: solo `torch` + `transformers` (gia' presenti o triviali da aggiungere).
Kraken CLI: binary pre-built per linux/arm64, non dipendenza Python.

---

## File implementati — Riepilogo

| # | File | Stato | Note |
|---|------|-------|------|
| 1 | `bot/market.py` | ✅ Creato | Market data aggregator multi-pair + indicatori via pandas-ta |
| 2 | `bot/chronos_predictor.py` | ✅ Creato | ChronosBoltPipeline, quantili fissi, chronos-forecasting>=2.2.0 |
| 3 | `bot/trading.py` | ✅ Creato | Paper + live trading via ccxt + SQLite |
| 4 | `bot/kronos.py` | ✅ Espanso | get_latest_prediction, predict_pair, confidence, multi-pair |
| 5 | `bot/handlers/trading_cmds.py` | ✅ Creato | 7 comandi: /portfolio, /market, /trades, /mode, /kill, /autonomous, /scan |
| 6 | `bot/scanner.py` | ✅ Creato | Market scanner (orario) + risk monitor (5 min) |
| 7 | `bot/prompts.py` | ✅ Modificato | TRADING_PROMPT con ruoli Analyst/Trader/Risk Manager |
| 8 | `bot/claude_bridge.py` | ✅ Modificato | Iniezione TRADING_PROMPT quando TRADING_ENABLED=true |
| 9 | `bot/config.py` | ✅ Modificato | Costanti TRADING_*, MARKET_*, CHRONOS_*, MAX_* |
| 10 | `bot/main.py` | ✅ Modificato | Wiring: init_trading, scanner loops, trading_cmds router |
| 11 | `Dockerfile` | ✅ Modificato | pip --timeout=300, Kraken CLI v0.3.1 ARM64 |
| 12 | `requirements.txt` | ✅ Modificato | chronos-forecasting>=2.2.0, pandas_ta, ccxt, torch, einops |
| 13 | `CLAUDE.md` | ✅ Aggiornato | Sezioni trading complete |
| 14 | `tests/test_market.py` | ✅ Creato | 31 test per market data aggregator |

---

## Verifica end-to-end (risultati deploy 2026-04-18)

1. ✅ `docker compose up -d --build` — tutti i container up (assistant, ollama, qdrant, tunnel)
2. ✅ Trading inizializzato — paper mode, DB ready
3. ✅ Kronos multi-pair — loop attivo su BTC/USDT, ETH/USDT, SOL/USDT
4. ✅ Chronos-Bolt — model loaded (ChronosBoltPipeline), previsioni per tutti e 3 i pair
5. ✅ Scanner e risk monitor — avviati, scanner aspetta modelli ready
6. ✅ 88 test passano (37 git_ops + 31 market + 20 memory)
7. ⏳ Comandi Telegram (/portfolio, /market, /scan, etc.) — da testare live
8. ✅ Trading autonomo — scanner → Claude via bridge.query() → decide e agisce
9. ✅ Live trading — ordini reali via ccxt (richiede EXCHANGE_API_KEY + EXCHANGE_API_SECRET)

---

## Rischi e mitigazioni

| Rischio | Probabilita' | Impatto | Mitigazione |
|---|---|---|---|
| Modelli di previsione inaccurati su crypto | Alta | Medio | Claude ragiona, non segue ciecamente. Stop-loss sempre. Paper trading prima. |
| Claude hallucina analisi di mercato | Media | Alto | Risk checks in codice, non nel prompt. Limiti hard-coded non bypassabili. |
| Kraken CLI API cambia | Bassa | Medio | Wrapper isolato in trading.py, facile da aggiornare. |
| Overtrading (troppi trade, commissioni mangiano profitti) | Media | Medio | MAX_TRADES_PER_DAY, min confidence threshold. |
| Flash crash / black swan | Bassa | Alto | Kill switch automatico a 15% drawdown. Emergency close via /kill. |
| Latenza CPU su Chronos-Bolt | Bassa | Basso | Predizioni ogni ora, 30s accettabili. Disabilitabile con flag. |

---

## Fonti ricerca

- [Kraken CLI — GitHub](https://github.com/krakenfx/kraken-cli) — binary arm64 confermato, MCP server built-in
- [Chronos-Bolt — HuggingFace](https://huggingface.co/amazon/chronos-bolt-small) — 250x faster, CPU-friendly
- [Chronos-2 — Amazon Science](https://www.amazon.science/blog/introducing-chronos-2-from-univariate-to-universal-forecasting)
- [TimesFM 2.5 — Google Research](https://research.google/blog/a-decoder-only-foundation-model-for-time-series-forecasting/)
- [Moirai 2.0 — Salesforce](https://www.salesforce.com/blog/moirai-2-0/) — any-variate attention, upgrade futuro
- [TradingAgents — Tauric Research](https://github.com/TauricResearch/TradingAgents) — multi-agent framework
- [AI-Trader — HKUDS](https://github.com/HKUDS/AI-Trader) — agent marketplace
- [TSFM Benchmark Inflation](https://paperswithbacktest.com/course/timesfm-vs-chronos-vs-moirai) — 47-184% inflated
- [ESMA Algo Trading Supervisory Briefing Feb 2026](https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf)
- [Position Sizing — Half-Kelly](https://saintquant.com/blog/161-how-to-build-a-profitable-crypto-trading-bot-in-2026-a-quantitative-guide-for-algorithmic-traders)
