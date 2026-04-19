# Trading Dashboard — Piano di Implementazione

## Context

Claudio ha gia' una dashboard (claudio-monitor) con 3 tab: Timeline, Changes, Kronos. Il tab Kronos e' un semplice grafico recharts con linee di previsione. L'obiettivo e' trasformarlo in un **trading dashboard completo** che mostri andamento, previsioni, indicatori tecnici, portfolio, trade, risk — tutto. L'architettura trading backend e' documentata in `docs/TRADING_ARCHITECTURE.md` ed e' **gia' implementata**.

Questo piano copre la **dashboard UI + gli endpoint backend necessari per alimentarla**.

Data analisi: 2026-04-19

---

## Analisi decisionale (Tournament Theory)

### Domanda zero: serve una dashboard web?

| Contendente | Pro | Contro | Verdetto |
|---|---|---|---|
| **Solo Telegram (status quo)** | 7 comandi gia' funzionanti (/portfolio, /market, /trades, /scan, /kill, /autonomous, /mode), funziona dal telefono, zero effort | Niente grafici, niente overview visuale, niente monitoraggio passivo — il testo di `/market` dice "RSI 55" ma non sai se e' in salita da 30 o in discesa da 70 | No come soluzione unica |
| **Dashboard web** | Candlestick con previsioni Kronos/Chronos overlay (il vero valore — nessun tool esterno lo fa), risk monitoring at-a-glance, review trade reasoning | Effort significativo (11 componenti, 4 endpoint, repo separato) | **Si — le previsioni overlay sono il motivo** |

**Verdetto: serve.** Le previsioni Kronos/Chronos hanno senso solo visualizzate su un grafico di prezzo. Nessun tool esterno (TradingView, Grafana, etc.) puo' mostrare candele future custom + bande di incertezza. Questo e' il valore unico della dashboard.

---

### Tournament 1: Approccio tecnico (6 contendenti)

**Criteri pesati:**

| Criterio | Peso | Motivo |
|----------|------|--------|
| Prediction overlay custom | 10 | Feature unica — se non si puo' fare, la dashboard perde il suo valore |
| Dati custom (portfolio, risk, reasoning) | 9 | Stack trading e' 100% custom, serve mostrarlo |
| Effort di sviluppo | 8 | Tempo per arrivare a qualcosa di usabile |
| Manutenzione futura | 7 | Costo di tenere il codice allineato |
| Qualita' charting | 7 | Candlestick, indicatori, interazione |
| Coerenza con stack esistente | 6 | Si integra con Timeline, Changes, auth, WS |
| Trade reasoning display | 5 | Mostrare perche' Claude ha deciso cosa |

**Matrice decisionale:**

| Contendente | Overlay (10) | Custom (9) | Effort (8) | Manutenzione (7) | Chart (7) | Coerenza (6) | Reasoning (5) | **Totale** |
|---|---|---|---|---|---|---|---|---|
| **Custom claudio-monitor** | 10 | 10 | 4 | 6 | 9 | 10 | 10 | **437** |
| **react-financial-charts** | 10 | 10 | 3 | 5 | 8 | 8 | 10 | **407** |
| **Evolvi Kronos tab (incrementale)** | 8 | 7 | 8 | 8 | 7 | 10 | 6 | **402** |
| **Standalone Vite app** | 10 | 10 | 5 | 4 | 9 | 5 | 10 | **401** |
| **TradingView embed** | 0 | 2 | 8 | 8 | 10 | 3 | 0 | **226** |
| **Grafana + InfluxDB** | 2 | 5 | 7 | 3 | 6 | 2 | 3 | **211** |

**Eliminati:**
- **TradingView embed (226)** — Non puo' mostrare previsioni Kronos/Chronos. L'intero punto della dashboard e' l'overlay custom. Eliminato.
- **Grafana + InfluxDB (211)** — No candlestick nativo, no prediction overlay, altro servizio Docker, auth separata. Over-engineering per un progetto single-user.
- **Standalone Vite app (401)** — Buon punteggio ma aggiunge un secondo progetto frontend da mantenere, duplica auth/WS logic. Guadagno marginale (Vite HMR) non giustifica il costo.
- **react-financial-charts (407)** — D3-based, SVG rendering (piu' lento di Canvas per migliaia di candele), non mantenuto attivamente dal 2024, bundle ~200kB. Non cambia l'approccio architetturale — e' solo un'alternativa peggiore a lightweight-charts.

**Vincitore: Custom claudio-monitor (437), approccio incrementale.**

La differenza tra "Custom claudio-monitor" e "Evolvi Kronos tab" non e' architetturale — e' di scope. Costruire incrementalmente dentro claudio-monitor riduce il rischio senza sacrificare il risultato finale.

---

### Tournament 2: Libreria charting (6 contendenti)

| Libreria | Bundle | Candlestick | Multi-pane | Indicatori | React 19 | Licenza | **Verdetto** |
|---|---|---|---|---|---|---|---|
| **lightweight-charts v5** | 35-45kB | Nativo | Si (v5) | Plugin (70+) | Wrapper custom | Apache 2.0 | **Vincitore** |
| react-financial-charts | ~200kB | Si | Si | Si (30+) | Non testato | MIT | SVG, pesante, non mantenuto |
| Apache ECharts | 200-300kB | Si | Parziale | Parziale | Via wrapper | Apache 2.0 | Troppo pesante |
| Recharts 3.8 | 60-80kB | No | No | No | Nativo | MIT | No candlestick — teniamo per grafici supplementari |
| Syncfusion Stock Chart | ~100kB | Si | Si | Si | Si | **Commercial** | Licenza a pagamento |
| amCharts 5 | ~300kB | Si | Si | Si | Via wrapper | **Commercial** | Licenza a pagamento, pesante |

**Vincitore: lightweight-charts v5.** Standard de facto (TradingView), 35kB gzipped (piu' leggero di recharts gia' nel progetto), Canvas rendering, multi-pane nativo in v5, plugin ecosystem con 70+ indicatori, Apache 2.0.

---

### Tournament 3: Scope — cosa costruire e in che ordine

Ogni componente valutato per valore (quanto e' utile) vs effort (quanto costa). Ratio = valore/effort.

| Componente | Valore (1-10) | Effort (1-10) | Ratio | Categoria |
|---|---|---|---|---|
| `trade_executed` emit (backend) | 9 | 1 | **9.0** | Quick win |
| PairSelector + TimeframeSelector | 6 | 1 | **6.0** | Quick win |
| REST endpoints (backend) | 8 | 2 | **4.0** | Quick win |
| PortfolioPanel + RiskGauge | 8 | 2 | **4.0** | Core |
| PositionsTable | 4 | 1 | **4.0** | Core |
| Prediction overlay (ghost + bande) | 10 | 3 | **3.3** | Feature unica |
| TradeHistory con reasoning | 6 | 2 | **3.0** | Review |
| PriceChart (candlestick base) | 10 | 4 | **2.5** | Feature unica |
| PredictionLog (migra da KronosTab) | 5 | 2 | **2.5** | Review |
| BottomTabs | 2 | 1 | **2.0** | Container |
| Sub-pane RSI/MACD | 4 | 3 | **1.3** | Nice to have |

**Verdetto: 3 wave, non 9 step monolitici.**

---

### Blind spot: problemi non coperti dal piano originale

| # | Problema | Impatto | Soluzione |
|---|----------|---------|-----------|
| 1 | **No CORS** — il backend aiohttp non ha header CORS. Next.js dev server (porta 3000) contro bot (porta 3333) → request REST falliscono | Blocca lo sviluppo frontend | Aggiungere CORS headers in `ws_server.py` per dev, oppure proxy in `next.config.ts` |
| 2 | **Deploy pipeline manuale** — edit → npm build → cp out/ dashboard/ → docker build per ogni modifica | Rallenta iterazione | Script `scripts/deploy_dashboard.sh` |
| 3 | **Auth token si resetta a ogni restart** — `_generate_auth_token()` usa `secrets.token_hex(8)` random. Ogni rebuild → cookie invalido → re-login | UX pessima durante sviluppo | Derivare token da hash deterministico del password |
| 4 | **`bot/static/` e' stale** — 1.2MB di chunk Next.js del 12 aprile, stessi file di `dashboard/`. Non usato dal Dockerfile | Confusione, spazio | Eliminare `bot/static/` |
| 5 | **Nessun loading/empty state** — al boot fresco, Kronos/Chronos impiegano ~60s. Dashboard mostrerebbe pannelli vuoti | UX confusa | Skeleton loading + "In attesa prima previsione..." |
| 6 | **No error boundary** — se Binance e' down, `/api/market` fallisce. Chart crasherebbe | Crash UI | Error boundary React + fallback per componente |
| 7 | **Cookie non `secure=True`** — funziona su HTTP localhost, ma su Cloudflare tunnel (HTTPS) andrebbe marcato secure | Rischio minimo (single user) | Aggiungere flag condizionale |
| 8 | **No dev mode con hot-reload** — sviluppo frontend richiede rebuild Docker per testare | Rallenta enormemente | Proxy config in next.config.ts per `/api/*` e `/ws` |

---

### Verdetto finale

```
Approccio:    Custom claudio-monitor, incrementale (score 437/520)
Libreria:     lightweight-charts v5 (35kB, Canvas, Apache 2.0)
Scope:        3 wave (MVP → monitoring → review)
Prerequisiti: fix blind spot 1-4 prima di scrivere codice frontend
Quick win:    emit("trade_executed") in trading.py (5 min, valore immediato)
```

---

## Stack esistente (da rispettare)

### Frontend (claudio-monitor — repo separato: github.com/MG84/claudio-monitor)
- **Framework:** Next.js 16 + React 19 + Tailwind v4 + shadcn/ui + recharts 3.8
- **Build:** Static export (`next build` → `/out/`) copiato in `dashboard/` nel repo Claudio, servito da aiohttp nel bot
- **Real-time:** WebSocket su `/ws` (bot/ws_server.py → broadcast)
- **Dati iniziali:** REST endpoint (`GET /api/kronos`) + history on WS connect (100 eventi)
- **Auth:** Cookie-based (`claudio_session`)
- **Charting attuale:** recharts (line/area/bar — NO candlestick)
- **Tab attuali:** Timeline, Changes, Kronos

### Backend trading (gia' implementato)
- `bot/market.py` — OHLCV, ticker, orderbook, indicatori tecnici (RSI, EMA, MACD, Bollinger, ATR) via ccxt + pandas-ta, cache con TTL, multi-pair. 31 test.
- `bot/trading.py` — Paper + live trading via ccxt, risk manager hard-coded (6 check non-bypassabili), trade journal SQLite, portfolio queries.
- `bot/scanner.py` — Market scanner (orario) + risk monitor (ogni 5 min), background loops.
- `bot/chronos_predictor.py` — Chronos-Bolt forecasting con bande di incertezza (quantili q10/q50/q90), loop orario.
- `bot/kronos.py` — Kronos forecasting OHLC multivariate, loop orario, multi-pair, confidence scoring.
- `bot/handlers/trading_cmds.py` — 7 comandi Telegram: /portfolio, /market, /trades, /mode, /kill, /autonomous, /scan.

### Endpoint REST attuali
- `POST /api/auth` — login
- `GET /api/auth/check` — verifica sessione
- `GET /api/kronos` — previsioni Kronos + OHLCV reali + accuracy stats

### Eventi WebSocket attuali (emessi dal backend)

| Evento | Sorgente | Dati |
|--------|----------|------|
| `kronos_prediction` | `bot/kronos.py` (ogni ora) | symbol, current_price, predictions (JSON) |
| `chronos_prediction` | `bot/chronos_predictor.py` (ogni ora) | symbol, current_price, direction, change_pct, point_forecast, quantile_forecast |
| `market_scan` | `bot/scanner.py` (ogni ora) | pairs (lista pair scansionati) |
| `portfolio_update` | `bot/scanner.py` (ogni 5 min) | risk status completo (daily_loss_pct, drawdown_pct, etc.) |
| `risk_alert` | `bot/scanner.py` (su breach/warning) | type, current, limit, message |
| `metrics` | `bot/monitor.py` (ogni 5s) | cpu_percent, ram_mb, uptime_s, active_sessions |
| `query_start/end` | `bot/claude_bridge.py` | project, model, duration |
| `changes` | `bot/claude_bridge.py` | diff git strutturato |

### Gap backend — prerequisiti per la dashboard

1. **`trade_executed` non emesso** — `trading.py` non chiama `emit()` quando un trade viene eseguito (`place_order()`) o chiuso (`close_position()`). La dashboard non puo' sapere in tempo reale dei trade.
2. **Indicatori solo scalari** — `get_indicators()` restituisce solo l'ultimo valore (es. RSI=55.2), NON serie temporali. Per overlay chart servono le serie complete. Soluzione: calcolo client-side da OHLCV con `lightweight-charts-indicators`.
3. **No endpoint REST trading** — mancano `/api/portfolio`, `/api/trades`, `/api/market/{pair}/{tf}`, `/api/chronos`.
4. **No ticker periodico** — nessun background task emette prezzi strutturati periodicamente. Il frontend dovra' usare polling REST o la dashboard accettera' aggiornamenti solo dalle predictions/portfolio_update.

---

## Nuova dipendenza

- **`lightweight-charts` v5.1** — TradingView candlestick charts (35kB gzipped, Canvas, Apache 2.0)
- **`lightweight-charts-indicators`** — 70+ indicatori tecnici calcolati client-side da OHLCV (EMA, RSI, MACD, Bollinger)
- Wrapper React custom (thin, ~50 righe, usando `useRef` + `useEffect` — pattern raccomandato da TradingView per React 19)
- Recharts resta per grafici supplementari (portfolio allocation, P&L curve, hit rates)

---

## Architettura del tab Trading

### Layout desktop (md+)

```
+-----------------------------------------------------------------------+
| [BTC/USDT] [ETH/USDT] [SOL/USDT]    [1H] [4H] [1D]    [Refresh]     |
+-----------------------------------------------------------------------+
|                                              | PREDICTIONS            |
|                                              | Kronos: UP +1.2%       |
|         CANDLESTICK CHART                    | Chronos: UP +0.8%      |
|         + Volume bars (histogram)            | Band 90%: [$94k-$97k]  |
|         + EMA 20/50 overlays                 +------------------------+
|         + Prediction ghost candles           | PORTFOLIO              |
|         + Uncertainty bands (Chronos)        | Bilancio: $10,000      |
|                                              | BTC: 0.05 (+2.3%)      |
|                                              | P&L oggi: +$230        |
+----------------------------------------------+------------------------+
| RSI (sub-pane)          | MACD (sub-pane)                            |
+-----------------------------------------------------------------------+
| [Posizioni] [Trade] [Previsioni]                                      |
| BTC Long 0.01 | entry $95,000 | P&L +$230 | SL $93,100 | Reasoning  |
+-----------------------------------------------------------------------+
| RISK GAUGE: Daily loss 1.2%/5%       Drawdown 3.1%/15%               |
+-----------------------------------------------------------------------+
```

### Layout mobile (<md)

```
+--------------------+
| [BTC] [1H]    [R]  |
+--------------------+
|                    |
| CANDLESTICK CHART  |
| (full width, 300px)|
+--------------------+
| Kronos UP +1.2%    |
| Chronos UP +0.8%   |
| Balance: $10,000   |
+--------------------+
| [Pos] [Trade] [Pred]|
| (tab switcher)     |
| BTC Long +2.3%     |
+--------------------+
```

---

## Componenti frontend (claudio-monitor)

### Nuovi componenti

| # | Componente | File | Descrizione |
|---|-----------|------|-------------|
| 1 | **TradingTab** | `components/trading/TradingTab.tsx` | Container principale, sostituisce KronosTab. Gestisce state, pair/timeframe selection, layout |
| 2 | **PriceChart** | `components/trading/PriceChart.tsx` | Wrapper Lightweight Charts: candlestick + volume + EMA + prediction overlay + uncertainty bands. Multi-pane con RSI/MACD sotto |
| 3 | **PredictionPanel** | `components/trading/PredictionPanel.tsx` | Riassunto previsioni Kronos + Chronos-Bolt: direzione, %, bande, concordanza |
| 4 | **PortfolioPanel** | `components/trading/PortfolioPanel.tsx` | Bilancio, posizioni aperte con P&L, daily P&L, mode (paper/live) |
| 5 | **BottomTabs** | `components/trading/BottomTabs.tsx` | Tab switcher per la sezione inferiore: Posizioni / Trade History / Previsioni Log |
| 6 | **PositionsTable** | `components/trading/PositionsTable.tsx` | Tabella posizioni aperte (pair, side, size, entry, current, P&L%, SL, TP) |
| 7 | **TradeHistory** | `components/trading/TradeHistory.tsx` | Storico trade recenti con reasoning di Claude, filtri per pair |
| 8 | **PredictionLog** | `components/trading/PredictionLog.tsx` | Migrazione della lista previsioni da KronosTab + aggiunta Chronos-Bolt |
| 9 | **RiskGauge** | `components/trading/RiskGauge.tsx` | Barre progresso: daily loss vs limite, drawdown vs limite, trades oggi vs limite |
| 10 | **PairSelector** | `components/trading/PairSelector.tsx` | Bottoni per BTC/ETH/SOL con prezzo e variazione 24h |
| 11 | **TimeframeSelector** | `components/trading/TimeframeSelector.tsx` | Bottoni 1H / 4H / 1D |

### File da modificare

| File | Modifica |
|------|----------|
| `app/page.tsx` | Sostituire KronosTab con TradingTab, aggiungere handler per nuovi event types (trade_executed, portfolio_update, risk_alert, chronos_prediction), nuovo state per trading data |
| `lib/constants.ts` | Aggiungere nuovi EventType, rinominare tab KRONOS → TRADING, aggiungere TRADING_ACTIONS |
| `lib/types.ts` | Aggiungere interfacce: MarketData, OHLCV, Position, Trade, PortfolioData, PredictionData, RiskStatus, ChronosPrediction |
| `hooks/useWebSocket.ts` | Nessuna modifica (gia' generico) |
| `package.json` | Aggiungere `lightweight-charts`, `lightweight-charts-indicators` |

### File da rimuovere

| File | Motivo |
|------|--------|
| `components/KronosTab.tsx` | Sostituito da TradingTab (funzionalita' migrate in PredictionLog + PriceChart) |

---

## Backend — Nuovi endpoint REST

I dati OHLCV sono grossi (400+ candle). Meglio REST per il caricamento iniziale, WebSocket per gli aggiornamenti real-time.

### `GET /api/market/{pair}/{timeframe}` (bot/ws_server.py)

Ritorna OHLCV + ticker + indicatori correnti per un pair/timeframe.

**Nota formato URL:** i pair contengono `/` (es. `BTC/USDT`), quindi nell'URL si usa il trattino: `/api/market/BTC-USDT/1h`. Il backend converte `BTC-USDT` → `BTC/USDT` prima di chiamare le funzioni.

```json
{
  "pair": "BTC/USDT",
  "timeframe": "1h",
  "ohlcv": [
    [1713398400000, 95000, 95500, 94800, 95200, 1234.5]
  ],
  "ticker": {
    "last": 95200,
    "volume_24h": 45000000,
    "change_pct_24h": 1.5,
    "bid": 95190,
    "ask": 95210,
    "high_24h": 96000,
    "low_24h": 94000
  },
  "indicators": {
    "rsi": 55.2,
    "ema20": 95100,
    "ema50": 94800,
    "ema200": 93500,
    "macd": { "macd": 120.5, "signal": 95.3, "histogram": 25.2 },
    "bollinger": { "lower": 93500, "mid": 95000, "upper": 96500, "bandwidth": 0.0315, "pct_b": 0.65 },
    "atr": 350.5
  }
}
```

**Nota indicatori:** il campo `indicators` contiene solo i valori correnti (scalari) da `bot/market.py:get_indicators()`. Gli overlay grafici (linee EMA, curva RSI, istogramma MACD) vengono calcolati **client-side** dalla libreria `lightweight-charts-indicators` a partire dai dati OHLCV. Questo evita di trasferire serie di 400 valori per ogni indicatore.

**Implementazione:** Chiama `bot/market.py:get_ohlcv()`, `get_ticker()`, e `get_indicators()` — tutte funzioni gia' esistenti.

### `GET /api/portfolio` (bot/ws_server.py)

Ritorna stato portfolio (paper o live) con dati reali da `bot/trading.py`.

```json
{
  "mode": "paper",
  "balance_usd": 10000.00,
  "initial_balance": 10000.00,
  "positions": [
    {
      "id": 1,
      "pair": "BTC/USDT",
      "side": "buy",
      "volume": 0.05,
      "entry_price": 94000,
      "stop_loss": 93000,
      "take_profit": 98000,
      "created_at": "2026-04-18T14:00:00Z"
    }
  ],
  "daily_pnl": { "pnl_usd": 230, "pnl_pct": 1.5, "trades_today": 3 },
  "risk": {
    "daily_loss_pct": 1.2,
    "max_daily_loss_pct": 5.0,
    "drawdown_pct": 3.1,
    "max_drawdown_pct": 15.0,
    "trades_today": 3,
    "max_trades_per_day": 10,
    "open_positions": 1,
    "max_open_positions": 3,
    "autonomous": false,
    "trading_active": true
  }
}
```

**Implementazione:** Chiama `bot/trading.py:get_balance()`, `get_positions()`, `get_daily_pnl()`, `get_risk_status()` — tutte funzioni gia' esistenti.

### `GET /api/trades?limit=20` (bot/ws_server.py)

Ritorna storico trade recenti.

```json
{
  "trades": [
    {
      "id": 1,
      "created_at": "2026-04-18T14:00:00Z",
      "pair": "BTC/USDT",
      "side": "buy",
      "type": "market",
      "volume": 0.01,
      "price": 95000,
      "stop_loss": 93100,
      "take_profit": null,
      "status": "open",
      "close_price": null,
      "closed_at": null,
      "pnl_usd": null,
      "reasoning": "Kronos UP +1.2%, RSI 45 neutral, EMA bullish crossover",
      "mode": "paper"
    }
  ]
}
```

**Implementazione:** Chiama `bot/trading.py:get_trade_history(limit)` — funzione gia' esistente. Formato di risposta identico a cio' che la funzione gia' ritorna.

### `GET /api/chronos` (bot/ws_server.py)

Ritorna storico previsioni Chronos-Bolt + accuracy stats.

```json
{
  "predictions": [
    {
      "created_at": "2026-04-18T14:00:00Z",
      "symbol": "BTC/USDT",
      "current_price": 95000,
      "direction": "UP",
      "change_pct": 1.2,
      "point_forecast": [95100, 95200, "..."],
      "quantile_forecast": { "q10": ["..."], "q50": ["..."], "q90": ["..."] },
      "verified": false,
      "direction_correct": null,
      "mae": null
    }
  ]
}
```

**Implementazione:** Query diretta sulla tabella `chronos_predictions` in `kronos.db` (DB condiviso, tabella separata), pattern identico a `_kronos_handler()` gia' esistente.

---

## Backend — Fix prerequisiti

### 1. Emettere `trade_executed` da trading.py

`place_order()` e `close_position()` devono emettere un evento monitor per notificare la dashboard in tempo reale.

```python
# In place_order(), dopo il commit SQLite:
from bot.monitor import emit
asyncio.create_task(emit("trade_executed", {
    "trade_id": trade_id, "pair": pair, "side": side,
    "volume": volume, "price": price, "mode": _mode,
    "stop_loss": stop_loss, "take_profit": take_profit,
    "action": "opened",
}))

# In close_position(), dopo il commit SQLite:
asyncio.create_task(emit("trade_executed", {
    "trade_id": trade_id, "pair": pair, "side": side,
    "volume": volume, "close_price": close_price,
    "pnl_usd": round(pnl, 2), "mode": trade_mode,
    "action": "closed",
}))
```

### 2. Aggiungere i 4 endpoint REST a ws_server.py

Aggiungere le route in `start_server()`:

```python
app.router.add_get("/api/market/{pair}/{timeframe}", _market_handler)
app.router.add_get("/api/portfolio", _portfolio_handler)
app.router.add_get("/api/trades", _trades_handler)
app.router.add_get("/api/chronos", _chronos_pred_handler)
```

Tutti protetti da `_check_auth()`.

### 3. Fix auth token (blind spot #3)

Il token attuale si rigenera a ogni restart. Derivarlo dal password hash in modo deterministico:

```python
def _generate_auth_token() -> str:
    if not DASHBOARD_PASSWORD:
        return ""
    return hashlib.sha256(f"claudio:{DASHBOARD_PASSWORD}".encode()).hexdigest()
```

### 4. Eliminare `bot/static/` (blind spot #4)

Directory stale con 1.2MB di chunk Next.js del 12 aprile, duplicati di `dashboard/`. Non usata dal Dockerfile. Da eliminare.

### 5. CORS per dev mode (blind spot #1)

Aggiungere CORS condizionale in `ws_server.py` o proxy in `next.config.ts` di claudio-monitor per permettere sviluppo con hot-reload su porta 3000 contro bot su porta 3333.

### 6. Script deploy dashboard (blind spot #2)

```bash
#!/bin/bash
# scripts/deploy_dashboard.sh
cd /path/to/claudio-monitor && npm run build
rm -rf /path/to/Claudio/dashboard/*
cp -r out/* /path/to/Claudio/dashboard/
cd /path/to/Claudio && docker compose down && docker compose up -d --build
```

---

## Backend — Nuovi eventi WebSocket

| Evento | Trigger | Dati | Frontend handler |
|--------|---------|------|-----------------|
| `trade_executed` | Dopo ogni place_order/close_position | trade object completo + action (opened/closed) | Aggiunge a trade history, aggiorna posizioni |
| `portfolio_update` | Gia' esistente (ogni 5 min via risk monitor) | risk status completo | Aggiorna PortfolioPanel + RiskGauge |
| `risk_alert` | Gia' esistente (su breach/warning) | type, current, limit, message | Notifica browser + aggiorna RiskGauge |
| `chronos_prediction` | Gia' esistente (ogni ora) | symbol, direction, change_pct, forecasts | Aggiorna PredictionPanel + uncertainty bands |
| `kronos_prediction` | Gia' esistente (ogni ora) | symbol, current_price, predictions | Aggiorna PredictionPanel + prediction overlay |

**Nota:** l'unico evento nuovo da implementare e' `trade_executed`. Tutti gli altri sono gia' emessi dal backend.

---

## Flusso dati

```
                    INIZIALIZZAZIONE
Frontend si connette → GET /api/market/BTC-USDT/1h → OHLCV + ticker + indicatori → PriceChart
                     → GET /api/portfolio → posizioni + bilancio + risk → PortfolioPanel + RiskGauge
                     → GET /api/trades → storico → TradeHistory
                     → GET /api/kronos → previsioni Kronos → PredictionLog
                     → GET /api/chronos → previsioni Chronos → PredictionLog
                     → WS history (100 eventi) → ripopola stato

                    REAL-TIME
Bot emette kronos_prediction → WS → aggiorna PredictionPanel + overlay chart
Bot emette chronos_prediction → WS → aggiorna PredictionPanel + uncertainty bands
Bot emette trade_executed → WS → aggiorna TradeHistory + PortfolioPanel
Bot emette portfolio_update → WS → aggiorna PortfolioPanel + RiskGauge
Bot emette risk_alert → WS → notifica + aggiorna RiskGauge

                    INTERAZIONE
User cambia pair → GET /api/market/{pair}/{tf} → aggiorna PriceChart + indicatori
User cambia timeframe → GET /api/market/{pair}/{tf} → aggiorna PriceChart
User clicca Refresh → re-fetch tutti gli endpoint
```

---

## Dettaglio componente: PriceChart

Il componente piu' complesso. Usa Lightweight Charts v5 con multi-pane.

```
Pane 0 (principale):
+-- CandlestickSeries — OHLCV storiche (colori standard: green up, red down)
+-- HistogramSeries — Volume (sotto le candele, semi-trasparente)
+-- LineSeries x 2 — EMA 20 (giallo) e EMA 50 (viola)
|   (calcolati client-side da OHLCV via lightweight-charts-indicators)
+-- CandlestickSeries — Prediction overlay (candele future semi-trasparenti da Kronos)
+-- AreaSeries x 2 — Uncertainty bands Chronos-Bolt (fill tra q10 e q90, giallo 10% opacita')
+-- Markers — Buy/Sell signals sui trade eseguiti

Pane 1 (sotto):
+-- LineSeries — RSI (0-100, linee a 30 e 70)
    (calcolato client-side da OHLCV close prices)

Pane 2 (sotto):
+-- LineSeries — MACD line + signal line
+-- HistogramSeries — MACD histogram
    (calcolati client-side da OHLCV close prices)
```

**Indicatori overlay:** Calcolati client-side dalla libreria `lightweight-charts-indicators` a partire dai dati OHLCV ricevuti via REST. Il backend fornisce solo i valori correnti (scalari) per il pannello laterale (PredictionPanel, display testuale). Questo approccio evita di trasferire 400+ valori per indicatore e sfrutta il calcolo ottimizzato della libreria.

**Aggiornamento real-time:** Quando arriva `kronos_prediction` via WS, aggiorna il prediction overlay con nuove candele future. Quando arriva `chronos_prediction`, aggiorna le bande di incertezza.

**Interazione:** Zoom, pan, crosshair con tooltip (built-in in Lightweight Charts).

---

## Ordine di implementazione (3 wave)

### Wave 0 — Prerequisiti (backend + tooling)

Prima di scrivere codice frontend.

1. Eliminare `bot/static/` (stale)
2. Aggiungere `emit("trade_executed", ...)` in `bot/trading.py:place_order()` e `close_position()`
3. Fix `_generate_auth_token()` — derivare da password hash deterministico
4. Aggiungere 4 endpoint REST in `bot/ws_server.py`: `/api/market/{pair}/{tf}`, `/api/portfolio`, `/api/trades`, `/api/chronos`
5. Creare `scripts/deploy_dashboard.sh`
6. Configurare proxy dev in claudio-monitor (`next.config.ts`) per `/api/*` e `/ws` verso `localhost:3333`

**Risultato:** backend pronto, tooling pronto. Il frontend puo' essere sviluppato con hot-reload.

### Wave 1 — MVP: chart + previsioni (la feature unica)

Il motivo per cui la dashboard esiste: candlestick con previsioni overlay.

1. `npm install lightweight-charts lightweight-charts-indicators`
2. Aggiornare `lib/constants.ts` e `lib/types.ts`
3. PriceChart wrapper (candlestick + volume)
4. Prediction overlay (Kronos ghost candles + Chronos uncertainty bands)
5. PairSelector + TimeframeSelector
6. PredictionPanel (sommario previsioni Kronos + Chronos)
7. TradingTab container con layout base
8. Fetch OHLCV da `/api/market/{pair}/{tf}`

**Risultato:** Apri la dashboard → vedi il grafico BTC/USDT con previsioni Kronos/Chronos overlay. La feature unica e' gia' li'. Puoi cambiare pair e timeframe.

### Wave 2 — Monitoring: portfolio + risk + trade

Monitoraggio operativo — sai cosa sta succedendo senza aprire Telegram.

1. PortfolioPanel (bilancio, posizioni, P&L da `/api/portfolio`)
2. PositionsTable
3. RiskGauge (daily loss, drawdown, trades — da `portfolio_update` WS + `/api/portfolio`)
4. TradeHistory con reasoning (da `/api/trades`)
5. PredictionLog (migra da KronosTab + Chronos)
6. BottomTabs con switcher
7. Handler WS per `trade_executed`, `portfolio_update`, `risk_alert`
8. Notifiche browser per `risk_alert` e `trade_executed`

**Risultato:** Dashboard completa. Monitoring in tempo reale, review decisioni Claude.

### Wave 3 — Polish: sub-pane indicatori + pulizia

Nice to have — indicatori tecnici gia' disponibili via /market su Telegram.

1. RSI sub-pane in PriceChart (pane 1, calcolato client-side)
2. MACD sub-pane in PriceChart (pane 2, calcolato client-side)
3. Toggle indicatori (mostra/nascondi)
4. Loading/skeleton states per componenti vuoti al boot
5. Error boundaries per ogni sezione
6. Rimuovere KronosTab.tsx
7. Test end-to-end
8. Build statico finale

**Risultato:** Dashboard production-ready, resiliente a errori, con analisi tecnica completa.

---

## File toccati — Riepilogo

### claudio-monitor (frontend — repo separato)

| File | Azione | Wave |
|------|--------|------|
| `next.config.ts` | Proxy `/api/*` e `/ws` per dev mode | 0 |
| `package.json` | Aggiungere `lightweight-charts`, `lightweight-charts-indicators` | 1 |
| `lib/constants.ts` | Nuovi EventType, TABS.TRADING | 1 |
| `lib/types.ts` | Interfacce MarketData, Position, Trade, Portfolio, ChronosPrediction, RiskStatus | 1 |
| `app/page.tsx` | Sostituire KronosTab → TradingTab, handler nuovi eventi, nuovo state | 1-2 |
| `components/trading/TradingTab.tsx` | **Nuovo** — container principale | 1 |
| `components/trading/PriceChart.tsx` | **Nuovo** — Lightweight Charts wrapper | 1 |
| `components/trading/PredictionPanel.tsx` | **Nuovo** — previsioni Kronos + Chronos | 1 |
| `components/trading/PairSelector.tsx` | **Nuovo** — selezione pair | 1 |
| `components/trading/TimeframeSelector.tsx` | **Nuovo** — selezione timeframe | 1 |
| `components/trading/PortfolioPanel.tsx` | **Nuovo** — bilancio + posizioni | 2 |
| `components/trading/PositionsTable.tsx` | **Nuovo** — tabella posizioni | 2 |
| `components/trading/RiskGauge.tsx` | **Nuovo** — indicatori rischio | 2 |
| `components/trading/TradeHistory.tsx` | **Nuovo** — storico trade | 2 |
| `components/trading/PredictionLog.tsx` | **Nuovo** — log previsioni (da KronosTab) | 2 |
| `components/trading/BottomTabs.tsx` | **Nuovo** — tab switcher sezione inferiore | 2 |
| `components/KronosTab.tsx` | **Rimuovere** (migrato in trading/) | 3 |

### Claudio (backend)

| File | Azione | Wave |
|------|--------|------|
| `bot/trading.py` | Aggiungere `emit("trade_executed", ...)` in `place_order()` e `close_position()` | 0 |
| `bot/ws_server.py` | Aggiungere 4 endpoint REST + fix auth token | 0 |
| `bot/static/` | **Eliminare** (stale, 1.2MB di duplicati) | 0 |
| `scripts/deploy_dashboard.sh` | **Nuovo** — build + copy + rebuild | 0 |

---

## Non incluso (rimandato)

| Feature | Motivo |
|---------|--------|
| **News/Sentiment Engine** | Nessun backend news esiste. Implementazione futura: feed crypto news (CryptoPanic API gratuita o RSS CoinDesk/CoinTelegraph), sentiment analysis via LLM locale (Ollama), evento `news_alert` via WS, componente NewsFeed nella dashboard. Prerequisito: decidere fonte dati e modello sentiment. |
| **market_update periodico** | Nessun background task emette ticker ogni 5 min. Per ora la dashboard aggiorna i prezzi su cambio pair (REST) e ad ogni prediction (WS). Se servira' real-time ticker, aggiungere un loop dedicato. |
| **Azioni trading dalla dashboard** | Bottoni buy/sell dalla UI. Richiede un design sicuro (conferma, risk check visuale). Fase successiva dopo che il monitoring funziona. |
| **Half-Kelly + ATR position sizing** | Documentato in TRADING_ARCHITECTURE.md ma non implementato nel codice. `risk_check()` usa solo limiti hard-coded. Feature futura del backend, non della dashboard. |

---

## Verifica end-to-end

### Wave 1 (MVP)
1. `cd claudio-monitor && npm install && npm run build` — build senza errori
2. Aprire dashboard → tab "Trading" visibile
3. PriceChart mostra candlestick BTC/USDT 1H con volume + EMA
4. Cambiare pair (ETH, SOL) → chart si aggiorna
5. Cambiare timeframe (1H, 4H, 1D) → chart si aggiorna
6. PredictionPanel mostra ultima previsione Kronos + Chronos
7. Prediction overlay visibile come candele semi-trasparenti nel futuro
8. Uncertainty bands Chronos visibili come area colorata

### Wave 2 (monitoring)
9. PortfolioPanel mostra bilancio paper reale (non mock)
10. RiskGauge mostra barre progresso limiti reali
11. Trade eseguito → `trade_executed` WS → compare in TradeHistory
12. `risk_alert` → notifica browser

### Wave 3 (polish)
13. RSI/MACD sub-pane sotto il chart
14. Skeleton loading al boot fresco (prima che le previsioni siano pronte)
15. Responsive: mobile layout stacked, desktop side-by-side
16. `npm test` — tutti i test passano

---

## Fonti

- [Lightweight Charts — TradingView](https://www.tradingview.com/lightweight-charts/)
- [Top 5 React Stock Chart Libraries 2026 — Syncfusion](https://www.syncfusion.com/blogs/post/top-5-react-stock-charts-in-2026)
- [Best Chart Libraries for React 2026 — Weavelinx](https://weavelinx.com/best-chart-libraries-for-react-projects-in-2026/)
- [Basic React example — Lightweight Charts docs](https://tradingview.github.io/lightweight-charts/tutorials/react/simple)
