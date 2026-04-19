# Kronos — Analisi e Strategia di Integrazione

> Data analisi: 2026-04-12
> Repo: https://github.com/shiyu-coder/Kronos

---

## 1. Cos'e' Kronos

Kronos e' il primo modello foundation open-source per dati finanziari (candlestick/K-line), pre-addestrato su 12 miliardi di record da 45+ exchange globali.

**Architettura:**
1. **Tokenizer specializzato** — converte dati OHLCV continui e multidimensionali in token discreti gerarchici (Binary Spherical Quantization)
2. **Transformer autoregressivo** (decoder-only) — genera token uno alla volta, poi il tokenizer li decodifica in candele OHLCV

**Non e' un bot di trading** — e' solo il "cervello" per le previsioni. La logica di trading (risk management, execution, position sizing) va costruita attorno.

---

## 2. Come funziona la predizione

### Input
DataFrame pandas con colonne:
- **Obbligatori**: `open`, `high`, `low`, `close` (float)
- **Opzionali**: `volume`, `amount` (float; auto-riempiti con 0 se mancanti)
- **Timestamp**: due `pd.Series` di datetime — uno per la finestra storica (`x_timestamp`) e uno per la finestra futura (`y_timestamp`)

### Output
DataFrame con le stesse colonne (open, high, low, close, volume, amount), una riga per ogni candela futura predetta. **Non restituisce**:
- Probabilita' direzionale (up/down)
- Score di confidenza
- Bande di incertezza (ma generabili con sample_count=1 multipli)

### Codice esempio

```python
from model import Kronos, KronosTokenizer, KronosPredictor
import pandas as pd

# 1. Carica modello (download da HuggingFace al primo avvio)
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
predictor = KronosPredictor(model, tokenizer, max_context=512)

# 2. Prepara dati OHLCV (da qualsiasi sorgente)
df = pd.read_csv("data.csv")
df['timestamps'] = pd.to_datetime(df['timestamps'])

lookback = 400    # candele storiche
pred_len = 48     # candele da predire

x_df = df.iloc[-lookback:][['open', 'high', 'low', 'close', 'volume', 'amount']]
x_timestamp = df.iloc[-lookback:]['timestamps'].reset_index(drop=True)

last_ts = df['timestamps'].iloc[-1]
interval = df['timestamps'].iloc[-1] - df['timestamps'].iloc[-2]
y_timestamp = pd.Series(pd.date_range(start=last_ts + interval, periods=pred_len, freq=interval))

# 3. Predici
pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=0.6,           # temperature (piu' bassa = piu' conservativo)
    top_p=0.9,       # nucleus sampling
    sample_count=5,  # genera 5 percorsi, ritorna la media
    verbose=True
)

# 4. Usa l'output
last_close = x_df['close'].iloc[-1]
predicted_close = pred_df['close'].iloc[0]
direction = "UP" if predicted_close > last_close else "DOWN"
pct_change = (predicted_close - last_close) / last_close * 100
```

### Batch prediction
Supportata per inference parallela su piu' serie:

```python
pred_dfs = predictor.predict_batch(
    df_list=[df1, df2, ...],
    x_timestamp_list=[ts1, ts2, ...],
    y_timestamp_list=[yts1, yts2, ...],
    pred_len=120,
)
```

---

## 3. Varianti del modello

| Modello | Parametri | Context Window | Tokenizer | Open Source |
|---------|-----------|----------------|-----------|-------------|
| Kronos-mini | 4.1M | 2048 | Kronos-Tokenizer-2k | Si |
| Kronos-small | 24.7M | 512 | Kronos-Tokenizer-base | Si |
| Kronos-base | 102.3M | 512 | Kronos-Tokenizer-base | Si |
| Kronos-large | 499.2M | 512 | Kronos-Tokenizer-base | No (proprietario) |

**HuggingFace IDs:**
- `NeoQuasar/Kronos-mini` + `NeoQuasar/Kronos-Tokenizer-2k`
- `NeoQuasar/Kronos-small` + `NeoQuasar/Kronos-Tokenizer-base`
- `NeoQuasar/Kronos-base` + `NeoQuasar/Kronos-Tokenizer-base`

**Raccomandazione:** Kronos-small (24.7M) per server modesti — gira comodamente su CPU in pochi secondi. Kronos-base (102.3M) se c'e' una GPU anche modesta (4GB+ VRAM).

---

## 4. Requisiti hardware

| Use Case | GPU | RAM | Disco |
|----------|-----|-----|-------|
| Inference Kronos-mini | No (CPU ok) | 2GB | ~50MB |
| Inference Kronos-small | No (CPU ok) | 4GB | ~100MB |
| Inference Kronos-base | Opzionale | 4-8GB | ~400MB |
| Finetuning Kronos-small | 1x GPU 4GB+ | 16GB | 1-5GB dati |
| Finetuning Kronos-base | 1x GPU 8GB+ | 32GB | 1-5GB dati |

Supporta `cuda`, `mps` (Apple Silicon), `cpu` (auto-detect).

---

## 5. Finetuning su pair specifiche

Due percorsi disponibili:

### CSV-based (quello rilevante per crypto)
```yaml
# config.yaml
data:
  data_path: "/path/to/btcusdt_5min.csv"
  lookback_window: 512
  predict_window: 48
  max_context: 512
  clip: 5.0
  train_ratio: 0.9
  val_ratio: 0.1

training:
  tokenizer_epochs: 30
  basemodel_epochs: 20
  batch_size: 32
  tokenizer_learning_rate: 0.0002
  predictor_learning_rate: 0.000001

model_paths:
  pretrained_tokenizer: "NeoQuasar/Kronos-Tokenizer-base"
  pretrained_predictor: "NeoQuasar/Kronos-base"
  exp_name: "btcusdt_5min"
  base_path: "./finetuned/"
```

```bash
python finetune_csv/train_sequential.py --config my_config.yaml
```

Training in due fasi: prima il tokenizer (VQ-VAE), poi il predictor (cross-entropy). Si puo' partire dai pesi pre-addestrati o da zero.

---

## 6. Limitazioni note

1. **Inference autoregressiva e sequenziale** — ogni candela predetta richiede un forward pass completo. 120 candele = 120 pass sequenziali. Non adatto a HFT.
2. **Errori si accumulano** — piu' si predice in avanti, meno affidabile. Per candele 5min, 120 step = 10 ore avanti.
3. **Nessuna quantificazione dell'incertezza** built-in — `sample_count > 1` genera percorsi multipli ma li media, perdendo l'informazione sulla distribuzione.
4. **Context window limitata** — max 512 candele (2048 per Kronos-mini).
5. **Solo OHLCV** — niente order book, funding rate, sentiment, on-chain data.
6. **Non e' una strategia di trading** — predice candele, non genera segnali buy/sell. La logica decisionale va costruita sopra.
7. **Temporal embeddings** — usa minuto/ora/giorno settimana/mese. Addestrato su mix di mercati tradizionali (chiudono) e crypto (24/7), pattern temporali potrebbero non essere ottimali per solo crypto.

---

## 7. Landscape exchange per trading bot

### Exchange consigliati

| Exchange | Maker Fee | Taker Fee | API | Testnet | Note |
|----------|-----------|-----------|-----|---------|------|
| Bybit | 0.10% | 0.10% | Unified V5, <10ms latenza | Si (testnet.bybit.com) | API piu' pulita, 10K USDT test |
| Binance | 0.10% | 0.10% | REST + WebSocket + WS API | Si (testnet.binance.vision) | Ecosistema piu' grande, -25% fee con BNB |
| Kraken | 0.25% | 0.40% | REST + WS + FIX | Limitato | Regolamentazione EU forte |

### Librerie Python

| Libreria | Uso |
|----------|-----|
| **CCXT** | Interfaccia unificata per 100+ exchange (dati + ordini) |
| **CCXT Pro** | WebSocket streaming real-time (a pagamento) |
| **VectorBT** | Backtesting veloce (vectorized, NumPy) |
| **Freqtrade** | Framework completo: backtesting + dry-run + live + Telegram |
| **pandas-ta** | Indicatori tecnici (RSI, MACD, Bollinger, ecc.) |

---

## 8. Risk management per micro-budget ($50-200)

### Regole fondamentali
- **Regola 1-2%**: mai rischiare piu' dell'1-2% del capitale per trade
- **Esposizione totale**: max 6% del portfolio a rischio contemporaneamente
- **Zero leva**: su micro-budget la leva e' suicide
- **1-3 pair**: concentrare su BTC/USDT, max ETH/USDT

### Safety controls hard-coded

```python
MAX_POSITION_PCT = 0.20       # Max 20% del capitale per posizione
MAX_OPEN_POSITIONS = 3         # Max posizioni simultanee
MAX_DAILY_LOSS_PCT = 0.05     # Stop trading dopo 5% loss giornaliero
MAX_DRAWDOWN_PCT = 0.15       # Kill switch a 15% drawdown dal picco
STOP_LOSS_REQUIRED = True      # Ogni trade DEVE avere stop-loss
MAX_TRADES_PER_DAY = 10        # Previeni trading compulsivo
```

### Fee erosion
Con 0.10% per side, un round trip (entry + exit) costa 0.20%. Su $50, sono $0.10 per trade. Con 10 trade/giorno = $1/giorno = $30/mese. Su un budget di $100, servono rendimenti >30%/mese solo per coprire le fee. **Minimizzare la frequenza dei trade.**

### Correlazione crypto
Posizioni multiple in crypto sono effettivamente **una mega-posizione** — BTC, ETH, SOL sono altamente correlati. Se sei long su tutti e tre, l'esposizione effettiva e' ~3x.

---

## 9. Failure modes comuni

### Statistiche
- 73% dei bot automatici fallisce entro 6 mesi
- 95% dei bot AI perde soldi entro 90 giorni
- 44% delle strategie pubblicate non si replicano su nuovi dati (overfitting)

### Categorie principali
1. **Overfitting** — performa perfettamente su dati storici, crolla su dati live
2. **Risk management inadeguato** — niente stop-loss, posizioni troppo grandi
3. **Fee erosion** — spread + slippage + commissioni mangiano i profitti
4. **Guasti tecnici** — API down, WebSocket disconnessi, crash con posizioni aperte
5. **Cambio di regime** — strategia che funziona in trend fallisce in range e viceversa
6. **Intervento emotivo** — spegnere il bot durante un drawdown (o non spegnerlo quando si dovrebbe)

---

## 10. Tournament Theory — 4 strategie a confronto

| | A. Kronos Trader | B. Kronos Advisor | C. Freqtrade + Kronos | D. Freqtrade classico |
|---|---|---|---|---|
| **Cosa fa** | Bot custom: Kronos predice, Claudio esegue ordini via CCXT | Claudio usa Kronos come analista, manda alert Telegram, l'utente decide | Freqtrade con Kronos come segnale via FreqAI | Freqtrade con strategie classiche (EMA, RSI) |
| **Complessita' build** | Alta | Bassa | Media | Bassa |
| **Rischio** | Alto | Zero | Medio | Basso |
| **Autonomia Claudio** | Totale | Solo analisi | Totale (via Freqtrade) | Totale (via Freqtrade) |
| **Valore educativo** | Massimo | Medio | Alto | Medio |
| **Tempo per MVP** | 2-3 settimane | 2-3 giorni | 1 settimana | 1-2 giorni |
| **Paper trading** | Da implementare | Intrinseco | Built-in | Built-in |

### Verdetti per round

| Round | Criterio | Vincitore |
|---|---|---|
| 1 | Velocita' di deploy | D |
| 2 | Integrazione con Claudio | B |
| 3 | Sicurezza soldi | B |
| 4 | Uso effettivo di Kronos | A/C |
| 5 | Scalabilita' futura | C |
| 6 | Valore educativo | A |
| 7 | Adatto a micro-budget | C |

### Classifica finale

| # | Strategia | Motivazione |
|---|-----------|-------------|
| 1 | **B -> C (percorso incrementale)** | Parti con advisor (zero rischio), validi Kronos, poi migri a Freqtrade quando sei convinto |
| 2 | C (Freqtrade + Kronos) | Se vuoi andare dritto al trading, il framework gestisce il 90% della complessita' |
| 3 | A (custom) | Massimo controllo ma massimo rischio di bug costosi |
| 4 | D (no Kronos) | Funziona ma non usi il modello |

---

## 11. Piano operativo completo

### Panoramica

Il piano segue un percorso incrementale B -> C: si parte con Kronos come analista (zero rischio finanziario), si validano le previsioni, e solo dopo evidenza positiva si passa al trading reale.

```
Fase 1: Advisor (2-4 settimane)
   |
   v  previsioni accurate? ──No──> fermarsi, valutare finetuning o abbandonare
   |
  Si
   |
   v
Fase 2: Paper Trading (2-4 settimane)
   |
   v  strategia profittevole in paper? ──No──> iterare strategia, tornare a Fase 2
   |
  Si
   |
   v
Fase 3: Micro-Live (1-2 mesi, $50-100)
   |
   v  profittevole dopo fee e slippage? ──No──> iterare o fermarsi
   |
  Si
   |
   v
Fase 4: Scale up (budget reale, multi-pair)
```

### Decisione architetturale
Il modulo Kronos vive **dentro Claudio** (non repo separato):
- Si incastra nel bot esistente (Telegram, Docker, monitoring, dashboard)
- Evita duplicazione infrastruttura
- Le previsioni appaiono nella dashboard come eventi
- Quando si passa alle fasi successive, e' gia' tutto connesso

### Tracking
Anche senza obblighi fiscali (residenza Dubai), tracking completo fin dal giorno 1:
- Ogni previsione (timestamp, pair, timeframe, predicted vs actual)
- Accuracy nel tempo (hit rate, MAE, direction accuracy)
- Ogni trade (quando si passa al trading): entry/exit, P&L, fee, slippage
- Report periodici su Telegram e dashboard

---

### Fase 1 — Kronos Advisor (2-4 settimane)

**Obiettivo:** validare se le previsioni di Kronos hanno valore predittivo reale.

**Cosa si costruisce:**
- `bot/kronos.py` — modulo inference Kronos + fetch candele via CCXT
- Comando `/predict` — previsione on-demand su Telegram
- Task periodico — ogni ora fetcha candele BTC/USDT, predice 12h avanti
- Alert Telegram — "Kronos prevede BTC a $X tra 6h (+2.1%)"
- Database previsioni — SQLite, ogni previsione salvata con timestamp
- Task di verifica — confronta previsioni passate con prezzi reali, calcola accuracy
- Evento dashboard — previsioni visibili nel monitoring

**Pair iniziali:** BTC/USDT (solo una, per semplicita')
**Timeframe:** 1h
**Modello:** Kronos-small (24.7M, CPU ok)
**Metriche da tracciare:**
- Direction accuracy (ha predetto su/giu' correttamente?)
- MAE (Mean Absolute Error) sul prezzo
- Hit rate a 1h, 6h, 12h
- Distribuzione errori

**Criteri per passare alla Fase 2:**
- Direction accuracy > 55% consistente su 2+ settimane
- Le previsioni battono un baseline naive (es. "il prezzo resta uguale")
- Nessun pattern sistematico di errore (es. sempre ottimista)

**Rischio finanziario:** zero.

---

### Fase 2 — Paper Trading (2-4 settimane)

**Obiettivo:** validare una strategia di trading completa basata sui segnali Kronos, senza soldi veri.

**Cosa si costruisce:**
- Logica di segnale: Kronos prediction -> BUY/SELL/HOLD
- Position sizing (regola 1-2%)
- Stop-loss automatico
- Paper trading engine (o Freqtrade dry-run, o testnet exchange)
- P&L tracking con fee simulate realistiche (0.10% per side)
- Report giornaliero su Telegram

**Exchange testnet:** Bybit testnet (testnet.bybit.com) — 10K USDT test, API identica alla produzione.

**Strategia base:**
- Kronos predice prossime 12 candele 1h
- Se predicted_close > current_close + threshold: BUY
- Se predicted_close < current_close - threshold: SELL
- Stop-loss: 2% sotto entry
- Take-profit: basato su predicted price
- Max 1 posizione aperta alla volta

**Metriche da tracciare:**
- Win rate
- Profit factor
- Max drawdown
- Sharpe ratio
- Fee impact (% dei profitti mangiato dalle fee)

**Criteri per passare alla Fase 3:**
- Profittevole dopo fee simulate per 2+ settimane consecutive
- Max drawdown < 15%
- Sharpe ratio > 1.0
- Nessun periodo di 5+ giorni in perdita consecutiva

**Rischio finanziario:** zero.

---

### Fase 3 — Micro-Live Trading (1-2 mesi)

**Obiettivo:** validare la strategia con soldi veri, verificare che slippage e latenza reali non distruggano i profitti.

**Budget:** $50-100 (soldi che si e' disposti a perdere completamente)
**Exchange:** Bybit o Binance (API keys trade-only, NO withdrawal)

**Cosa si costruisce:**
- Connessione a exchange reale via CCXT
- Esecuzione ordini reali
- Kill switch automatici:
  - Max 5% loss giornaliero -> stop trading per il giorno
  - Max 15% drawdown dal picco -> stop totale, notifica Telegram
  - Max 3 posizioni simultanee
  - Max 10 trade/giorno
- Riconciliazione: confronto stato interno vs stato exchange
- Alert Telegram per ogni trade eseguito

**Safety controls:**
```python
MAX_POSITION_PCT = 0.20       # Max 20% del capitale per posizione
MAX_OPEN_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 0.05
MAX_DRAWDOWN_PCT = 0.15
STOP_LOSS_REQUIRED = True
MAX_TRADES_PER_DAY = 10
```

**Criteri per passare alla Fase 4:**
- Profittevole dopo fee reali per 1+ mese
- Performance in linea con il paper trading (no degradazione significativa)
- Sistema stabile (no crash, no ordini fantasma, no posizioni bloccate)

**Rischio finanziario:** limitato al budget ($50-100).

---

### Fase 4 — Scale Up

**Obiettivo:** aumentare budget e diversificare.

**Solo se Fase 3 e' positiva.** Decisioni da prendere al momento:
- Aumentare budget (quanto?)
- Aggiungere pair (ETH/USDT, SOL/USDT)
- Finetuning di Kronos sulle pair specifiche
- Multi-timeframe (1h + 4h)
- Eventuale migrazione a Freqtrade per infrastruttura piu' robusta
- Considerare Kronos-base (102.3M) per predizioni migliori

**Rischio finanziario:** proporzionale al budget scelto.

---

## 12. Note fiscali

**Residenza Dubai** — zero tasse su capital gain e redditi personali. Nessun obbligo di reporting fiscale su crypto trading. Tracking mantenuto comunque per:
- Valutare performance del bot
- Storico pulito in caso di cambio residenza futuro
- Audit trail per gli exchange (KYC/AML)

---

## 13. TimesFM — Confronto con Kronos

> Data analisi: 2026-04-13
> Repo: https://github.com/google-research/timesfm

### Cos'e' TimesFM

Google TimesFM e' un modello foundation general-purpose per serie temporali (200M parametri, versione 2.5). Pre-addestrato su 100 miliardi di data point eterogenei (meteo, traffico, vendite, energia, finanza). Apache 2.0 license. Zero-shot forecasting — nessun training specifico necessario.

### Confronto diretto

| | Kronos (attuale) | TimesFM |
|---|---|---|
| Parametri | 24.7M (small) | 200M |
| Training data | 12B record finanziari da 45+ exchange | 100B data point generici (multi-dominio) |
| Input | DataFrame OHLC (multivariate, nativo) | Univariate (array/lista singola) |
| Output | OHLC completo (open, high, low, close) | Un valore per step + quantili |
| CPU inference | ~8 sec / 12 candele | Significativamente piu' lento (8x parametri) |
| Specializzazione crypto | Progettato per candlestick | Zero — general purpose |
| Quantificazione incertezza | Nessuna built-in (sample_count multipli) | Quantile forecast nativo |
| Licenza | MIT | Apache 2.0 |

### Perche' Kronos e' migliore per il nostro use case

1. **Multivariate nativo** — Kronos predice OHLC come dato strutturato unico. TimesFM e' univariate: servirebbe lanciare 4 run separati (open, high, low, close) e i risultati non sarebbero coerenti tra loro (high potrebbe uscire sotto low).

2. **Specializzazione** — Kronos e' addestrato esclusivamente su dati finanziari (candlestick da 45+ exchange). TimesFM e' generalista: i suoi 100B data point includono meteo, traffico, vendite — dati con dinamiche completamente diverse dai mercati finanziari.

3. **Efficienza** — 24.7M vs 200M parametri. Su CPU ARM (Docker su Mac), la differenza e' enorme: 8 secondi vs potenzialmente minuti.

4. **Tokenizer specializzato** — Kronos usa Binary Spherical Quantization progettato per dati OHLCV continui. TimesFM usa un tokenizer generico per serie temporali qualsiasi.

### Quando TimesFM potrebbe avere senso

- Se si volessero predire serie temporali NON finanziarie (metriche sistema, traffico web, etc.)
- Come baseline di confronto per validare che Kronos effettivamente batte un modello general-purpose
- Se servissero quantile forecast nativi (bande di incertezza) senza dover generare sample multipli

### Meta-analisi: la strategia di Google

L'open-sourcing di TimesFM e' strategia di colonizzazione ecosistema: licenza Apache, 200M parametri, "gratis". Quando tutti usano la stessa architettura, gli stessi bias di pre-training, le stesse assunzioni su cosa sono "100B real-world data points" — Google definisce il fitness landscape per tutti gli altri giocatori. Lock-in senza lock-in apparente.

### Il punto cieco strutturale

Se molti trader adottano lo stesso modello predittivo, le predizioni diventano un input del mercato stesso (la mappa modifica cio' che mappa). Le predizioni convergono, i comportamenti convergono, il sistema perde varianza, diventa fragile. Il prossimo shock e' amplificato perche' nessuno era posizionato diversamente. Questo vale per QUALSIASI modello adottato in massa — Kronos, TimesFM, o altro.

### Decisione

**Kronos rimane il modello primario** per previsioni candlestick. TimesFM non aggiunge valore per questo use case specifico. Rivalutare se/quando si espandera' a previsioni su dati non-finanziari
