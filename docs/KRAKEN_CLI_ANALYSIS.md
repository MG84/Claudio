# Kraken CLI — Analisi completa

Analisi di [krakenfx/kraken-cli](https://github.com/krakenfx/kraken-cli) per integrazione in Claudio.

Data analisi: 2026-04-19
Versione analizzata: v0.3.1 (14 aprile 2026)

---

## Cos'e'

Tool CLI ufficiale Kraken, scritto in **Rust**, binary singolo (~6MB), zero dipendenze runtime. 486 stars, MIT license, prima release marzo 2026. Si definisce "the first AI-native CLI for trading crypto, stocks, forex, and derivatives."

- CLI puro (non TUI), ogni comando produce JSON strutturato (`-o json`)
- Include REPL interattivo (`kraken shell`) per uso umano
- **MCP server built-in** (`kraken mcp`) — tool server nativo per agenti AI
- Sperimentale/alpha — disclaimer esplicito sui rischi finanziari

---

## Feature

### Asset supportati (6 classi)

| Classe | Dettagli |
|--------|----------|
| Crypto spot | 1400+ pair, margin fino a 10x su major |
| xStocks | 79 azioni US tokenizzate (AAPL, NVDA, TSLA, GOOGL...), margin 3x |
| Forex | 11 pair fiat (EUR/USD, GBP/USD, etc.) |
| Futures perpetui | 317 contratti, leva fino a 50x |
| Futures inverse/fixed-date | 20 contratti |
| Earn/staking | Strategie flessibili e bonded |

### Comandi (151 totali, 13 gruppi)

| Gruppo | Comandi | API key | Descrizione |
|--------|---------|---------|-------------|
| `market` | 10 | No | Ticker, orderbook, OHLC, trades, spread |
| `account` | 18 | Si | Bilanci, ordini, trade, ledger, posizioni |
| `trade` | 9 | Si | Piazzamento ordini, modifica, cancellazione |
| `funding` | 10 | Si | Depositi, prelievi, trasferimenti |
| `earn` | 6 | Si | Strategie staking |
| `subaccount` | 2 | Si | Creazione subaccount, trasferimenti |
| `futures` | 39 | Misto | Trading e dati futures |
| `futures-paper` | 17 | No | Paper trading futures |
| `futures-ws` | 9 | Misto | WebSocket streaming futures |
| `websocket` | 15 | Misto | WebSocket v2 spot streaming |
| `paper` | 10 | No | Paper trading spot |
| `auth` | 4 | No | Gestione credenziali |
| `utility` | 2 | No | Setup wizard, REPL shell |

34 comandi marcati "dangerous" (ordini, prelievi, trasferimenti, cancel-all, staking).

---

## MCP Server

Feature chiave per integrazione con Claude. Il binary include un MCP server che comunica via stdio.

### Avvio

```bash
kraken mcp                           # Default: market + account + paper (safe)
kraken mcp -s market,paper           # Solo dati pubblici + paper trading
kraken mcp -s all                    # Tutto; dangerous richiede acknowledged=true
kraken mcp -s all --allow-dangerous  # Full autonomo, nessuna conferma per-call
kraken mcp -s market,trade,paper     # Selezione specifica servizi
```

### Servizi MCP

| Servizio | API key | Rischio | Descrizione |
|----------|---------|---------|-------------|
| `market` | No | Nessuno | Dati di mercato pubblici |
| `paper` | No | Nessuno | Paper trading spot (10 cmd) |
| `futures-paper` | No | Nessuno | Paper trading futures (17 cmd) |
| `account` | Si | Read-only | Bilanci, ordini, ledger |
| `trade` | Si | Dangerous | Ordini reali live |
| `funding` | Si | Dangerous | Depositi, prelievi |
| `earn` | Si | Dangerous | Staking |
| `subaccount` | Si | Dangerous | Gestione subaccount |
| `futures` | Misto | Dangerous | Trading futures live |
| `auth` | No | Read-only | Verifica credenziali |

### Default (senza flag)

`market`, `account`, `paper` — safe per uso senza supervisione.

### Configurazione Claude Desktop

```json
{
  "mcpServers": {
    "kraken": {
      "command": "kraken",
      "args": ["mcp", "-s", "all"]
    }
  }
}
```

### Vincoli MCP

- Solo REST in v1 — no WebSocket streaming via MCP
- `auth set` e `auth reset` non disponibili in modalita' MCP (stateless by design)
- Tool names con underscore: `kraken_order_buy`, `kraken_ticker`, etc.
- Operazioni dangerous flaggate con `destructive_hint: true`
- In modalita' guarded (default), dangerous richiede `acknowledged=true` nel parametro
- `--allow-dangerous` rimuove la conferma per-call (uso autonomo)

---

## Paper trading

Due engine indipendenti, entrambi con **prezzi live Kraken**, zero API key.

### Spot

```bash
kraken paper init --balance 10000 -o json     # Init con $10,000
kraken paper buy BTCUSD 0.01 -o json          # Buy 0.01 BTC a mercato
kraken paper sell BTCUSD 0.005 --type limit --price 70000 -o json
kraken paper status -o json                    # Portfolio completo
kraken paper orders -o json                    # Ordini aperti
kraken paper positions -o json                 # Posizioni
kraken paper history -o json                   # Storico trade
kraken paper balance -o json                   # Bilancio
kraken paper reset -o json                     # Reset tutto
```

### Futures

```bash
kraken futures paper init --balance 10000 -o json
kraken futures paper buy PF_XBTUSD 1 --leverage 10 --type market -o json
kraken futures paper sell PF_ETHUSD 5 --leverage 20 --type market -o json
kraken futures paper buy PF_XBTUSD 1 --type limit --price 50000 -o json
kraken futures paper positions -o json
kraken futures paper balance -o json
kraken futures paper fills -o json
kraken futures paper reset -o json
```

### Caratteristiche paper trading

- Fee simulate: 0.26% taker (tier Starter)
- Limit order fill quando il mercato attraversa il prezzo
- Futures: tutti gli 8 tipi ordine, leva, margin tracking, position netting, simulazione liquidazione
- Persistenza locale (stato nel config directory)

### Limitazioni paper vs live

- Status ordine con singolo ID
- Ordini post-only cancellati invece di messi in coda
- Fill usano prezzo snapshot senza slippage di profondita'
- No fill parziali

---

## Installazione

### One-liner (raccomandato)

```bash
curl --proto '=https' --tlsv1.2 -LsSf \
  https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh
```

### Da sorgente

```bash
cargo install --git https://github.com/krakenfx/kraken-cli
```

### Binary pre-built

| Piattaforma | File | Size |
|-------------|------|------|
| macOS Apple Silicon | `kraken-cli-aarch64-apple-darwin.tar.gz` | 5.45 MB |
| macOS Intel | `kraken-cli-x86_64-apple-darwin.tar.gz` | 5.96 MB |
| **Linux ARM64** | **`kraken-cli-aarch64-unknown-linux-gnu.tar.gz`** | **5.93 MB** |
| Linux x86_64 | `kraken-cli-x86_64-unknown-linux-gnu.tar.gz` | 6.10 MB |

Il binary ARM64 Linux esiste — compatibile con il container Docker di Claudio.

### Dockerfile

```dockerfile
RUN curl -L https://github.com/krakenfx/kraken-cli/releases/download/v0.3.1/kraken-cli-aarch64-unknown-linux-gnu.tar.gz \
    | tar xz -C /usr/local/bin/
```

---

## Autenticazione

### Cosa funziona SENZA API key

- Tutti i comandi `market` (10)
- Tutti i comandi `paper` (10)
- Tutti i comandi `futures-paper` (17)
- Alcuni comandi `futures` pubblici
- Alcuni stream `websocket` pubblici
- MCP server in modalita' default
- Comandi `auth` e `utility`

### Cosa RICHIEDE API key

- `account`: bilanci, ordini, trade, ledger (permessi: Query Funds + Query Open Orders & Trades)
- `trade`: ordini (permessi: Create & Modify Orders + Cancel/Close Orders)
- `funding`: depositi, prelievi (permessi: Deposit/Withdraw + Query Funds)
- `earn`: staking
- `subaccount`: gestione subaccount
- `futures` endpoint autenticati (API key futures separata)

### Risoluzione credenziali (precedenza decrescente)

1. Flag CLI (`--api-key`, `--api-secret`)
2. Variabili ambiente (`KRAKEN_API_KEY`, `KRAKEN_API_SECRET`)
3. File config (`~/.config/kraken/config.toml`, permessi 0600)

### Override endpoint API

Variabili ambiente: `KRAKEN_SPOT_URL`, `KRAKEN_FUTURES_URL`, `KRAKEN_WS_PUBLIC_URL`, `KRAKEN_WS_AUTH_URL` (solo https:// e wss://).

---

## Ecosistema agenti AI

Kraken CLI include documentazione machine-readable per agenti:

- `agents/tool-catalog.json` — 151 comandi con schema parametri completo, requisiti auth, flag safety
- `agents/error-catalog.json` — 9 categorie errore con strategie retry
- `agents/examples/` — Script workflow di esempio (market monitor, paper trading, portfolio rebalance)
- `skills/` — **50 workflow goal-oriented** (DCA, grid trading, basis trading, emergency flatten, morning market brief, etc.)

---

## Limitazioni

| Limitazione | Impatto per Claudio |
|-------------|---------------------|
| **Solo Kraken** — niente multi-exchange | ccxt resta necessario per Binance e altri exchange |
| **No indicatori tecnici** — niente RSI, EMA, MACD | `bot/market.py` + pandas-ta restano necessari |
| **No modelli ML** | Non sostituisce Kronos/Chronos |
| **No WebSocket via MCP** (solo REST in v1) | Nessun streaming real-time via MCP |
| **No backtest built-in** | Non copre questa esigenza |
| **No fill parziali** nel paper trading | Simulazione meno realistica |
| **Alpha/sperimentale** | Possibili breaking change tra versioni |
| **xStocks non disponibili in US** | Non rilevante per crypto |
| **No rate-limit client-side** | L'agente deve gestire backoff su errori rate-limit |

---

## Confronto con stack attuale

| Funzionalita' | Stack attuale (ccxt) | Kraken CLI | Vincitore |
|---------------|---------------------|------------|-----------|
| Market data | Binance via ccxt (pubblico) | Kraken API (pubblico) | Pari (fonti diverse) |
| Multi-exchange | Si (100+ exchange) | No (solo Kraken) | ccxt |
| Paper trading | Custom in SQLite | Built-in con prezzi live | Kraken CLI |
| Live trading | ccxt async | Comandi CLI o MCP | Pari |
| Indicatori tecnici | pandas-ta (RSI, EMA, MACD...) | Nessuno | ccxt + pandas-ta |
| Previsioni ML | Kronos + Chronos-Bolt | Nessuno | Stack attuale |
| Integrazione Claude | Via tool Python (claude_bridge) | MCP server nativo | Kraken CLI |
| Futures | Non implementato | Si, con leva fino a 50x | Kraken CLI |
| Risk management | Hard-coded in Python | Nessuno (agente deve gestire) | Stack attuale |
| Persistenza | SQLite (trades.db) | Stato locale CLI | Stack attuale |

---

## Potenziale integrazione con Claudio

### Approccio raccomandato: complementare, non sostitutivo

Kraken CLI aggiunge valore come **layer aggiuntivo** accanto allo stack esistente:

1. **MCP server** per dare a Claude accesso diretto a market data Kraken + paper trading — senza codice wrapper
2. **Futures paper trading** — feature non presente nello stack attuale
3. **Market data Kraken** come seconda fonte dati accanto a Binance (diversificazione)
4. **50 workflow skills** come guide per strategie di trading

Lo stack attuale (ccxt + pandas-ta + Kronos + Chronos + risk manager) resta necessario per:
- Indicatori tecnici
- Previsioni ML
- Multi-exchange
- Risk management hard-coded
- Persistenza trade journal

### Integrazione Docker

```dockerfile
# Download e install binary ARM64
ARG KRAKEN_CLI_VERSION=v0.3.1
RUN curl -L "https://github.com/krakenfx/kraken-cli/releases/download/${KRAKEN_CLI_VERSION}/kraken-cli-aarch64-unknown-linux-gnu.tar.gz" \
    | tar xz -C /usr/local/bin/ \
    && chmod +x /usr/local/bin/kraken
```

### Integrazione MCP con Claude Agent SDK

```python
# In bot/claude_bridge.py — aggiungere come MCP server
mcp_servers = [
    {
        "command": "kraken",
        "args": ["mcp", "-s", "market,paper"],  # safe, no API key
    }
]
```

Con API key configurate:
```python
mcp_servers = [
    {
        "command": "kraken",
        "args": ["mcp", "-s", "market,account,paper"],
        "env": {
            "KRAKEN_API_KEY": os.environ.get("KRAKEN_API_KEY", ""),
            "KRAKEN_API_SECRET": os.environ.get("KRAKEN_API_SECRET", ""),
        },
    }
]
```

### Variabili ambiente (docker-compose.yml)

```yaml
environment:
  - KRAKEN_API_KEY=${KRAKEN_API_KEY:-}
  - KRAKEN_API_SECRET=${KRAKEN_API_SECRET:-}
```

---

## Rischi

| Rischio | Probabilita' | Impatto | Mitigazione |
|---------|-------------|---------|-------------|
| Breaking change in versioni future | Media | Medio | Pinnare versione nel Dockerfile |
| Binary non compatibile con container | Bassa | Alto | Testare in CI, fallback a ccxt |
| Rate-limit Kraken non gestiti | Media | Basso | Retry con backoff nel wrapper |
| MCP server instabile | Bassa | Medio | Fallback a subprocess calls |
| Conflitto con ccxt (stessi pair, dati diversi) | Bassa | Basso | Usare una fonte primaria, l'altra come verifica |

---

## Decisione

**Valido come aggiunta complementare.** Il valore principale e' il MCP server nativo che permette a Claude di interagire direttamente con Kraken senza codice intermediario. Da integrare come tool aggiuntivo, non come sostituto dello stack ccxt esistente.

---

## Decisione finale

**Implementato come approccio ibrido** (vedi `docs/TRADING_TOURNAMENT.md` per l'analisi tournament theory completa).

### Cosa e' stato fatto

1. **Dockerfile**: download binary Kraken CLI v0.3.1 ARM64 in `/usr/local/bin/kraken`
2. **bot/config.py**: costanti `KRAKEN_CLI_ENABLED`, `KRAKEN_CLI_PATH`, `KRAKEN_MCP_SERVICES`
3. **bot/claude_bridge.py**: `mcp_servers` dict con config stdio passato a `ClaudeAgentOptions`
4. **bot/prompts.py**: sezione "Kraken CLI (MCP)" in `TRADING_PROMPT` con lista strumenti MCP
5. **docker-compose.yml**: env vars `KRAKEN_CLI_ENABLED`, `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`
6. **.env.example**: documentazione nuove variabili
7. **CLAUDE.md**: sezione documentazione Kraken CLI MCP

### Architettura risultante

```
Claude Agent SDK
├── Tool Python (ccxt) — layer primario
│   ├── Indicatori tecnici (pandas-ta)
│   ├── Previsioni ML (Kronos + Chronos-Bolt)
│   ├── Risk management hard-coded
│   └── Trade journal SQLite
└── MCP Server (Kraken CLI) — layer complementare
    ├── Market data Kraken (ticker, OHLC, orderbook)
    └── Paper trading spot (prezzi live, fee simulate)
```

### Configurazione servizi MCP

| Configurazione | Servizi | API key | Uso |
|----------------|---------|---------|-----|
| Default | `market,paper` | No | Dati pubblici + paper trading |
| Con account | `market,account,paper` | Si | + bilanci e ordini |
| Full | `market,account,trade,paper` | Si | + ordini reali (dangerous) |
