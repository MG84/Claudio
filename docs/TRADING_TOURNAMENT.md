# Trading Architecture — Tournament Theory

Analisi tournament theory per decidere l'architettura trading di Claudio.

Data: 2026-04-19

---

## I 6 contendenti

| # | Approccio | Descrizione |
|---|-----------|-------------|
| 1 | **ccxt puro** | Stack attuale: ccxt + pandas-ta + Kronos/Chronos. Claude usa tool Python wrapper. |
| 2 | **Kraken CLI puro** | Sostituire ccxt con Kraken CLI come unico layer. Claude usa MCP nativo. |
| 3 | **Ibrido (ccxt + Kraken CLI MCP)** | Tenere ccxt come layer primario, aggiungere Kraken CLI come MCP server per accesso diretto. |
| 4 | **Custom MCP wrapper** | Scrivere un MCP server custom che wrappa ccxt e pandas-ta. |
| 5 | **Multi-exchange CLI** | Usare Kraken CLI + un secondo CLI per Binance (non esiste). |
| 6 | **API dirette Kraken** | Chiamate REST dirette alle API Kraken senza librerie. |

---

## Matrice decisionale

| Criterio (peso) | ccxt puro | Kraken CLI puro | Ibrido | Custom MCP | Multi-CLI | API dirette |
|------------------|-----------|-----------------|--------|------------|-----------|-------------|
| **Effort implementazione** (20%) | 10 (gia' fatto) | 4 (riscrivere tutto) | 8 (aggiunta incrementale) | 3 (da zero) | 2 (non esiste) | 2 (basso livello) |
| **Multi-exchange** (15%) | 10 | 1 (solo Kraken) | 8 (ccxt + Kraken) | 8 (ccxt sotto) | 3 | 1 |
| **Indicatori tecnici** (15%) | 10 (pandas-ta) | 1 (nessuno) | 10 (pandas-ta resta) | 10 | 1 | 1 |
| **Integrazione Claude** (20%) | 5 (tool wrapper) | 10 (MCP nativo) | 9 (MCP + wrapper) | 8 (MCP custom) | 5 | 3 |
| **Paper trading** (10%) | 6 (custom SQLite) | 9 (built-in, prezzi live) | 9 (entrambi) | 6 | 5 | 2 |
| **Risk management** (10%) | 10 (hard-coded) | 3 (agente deve gestire) | 10 (hard-coded resta) | 10 | 3 | 10 |
| **Manutenibilita'** (10%) | 8 | 7 (binary esterno) | 7 (due layer) | 4 (codice custom) | 2 | 3 |

### Punteggi pesati

| Approccio | Score |
|-----------|-------|
| ccxt puro | 8.15 |
| Kraken CLI puro | 4.45 |
| **Ibrido** | **8.85** |
| Custom MCP | 6.70 |
| Multi-CLI | 2.85 |
| API dirette | 2.80 |

---

## Analisi per approccio

### 1. ccxt puro (score: 8.15)

**Pro:** Gia' funzionante, multi-exchange, indicatori tecnici, risk management hard-coded.
**Contro:** Claude non ha accesso diretto ai dati di mercato — tutto passa per tool Python wrapper. Niente paper trading Kraken con prezzi live.
**Verdetto:** Buono ma perde l'opportunita' MCP.

### 2. Kraken CLI puro (score: 4.45)

**Pro:** MCP nativo, paper trading built-in, 151 comandi.
**Contro:** Solo Kraken (no Binance), zero indicatori tecnici, perde Kronos/Chronos, risk management va riscritto.
**Verdetto:** Troppo limitante come sostituto.

### 3. Ibrido (score: 8.85)

**Pro:** Prende il meglio di entrambi. ccxt resta per indicatori, previsioni ML, risk management. Kraken CLI aggiunge MCP nativo per market data e paper trading Kraken. Claude ha due canali: tool Python + MCP diretto.
**Contro:** Due layer da mantenere, possibile confusione su quale fonte dati usare.
**Verdetto:** Miglior rapporto costo/beneficio.

### 4. Custom MCP wrapper (score: 6.70)

**Pro:** MCP server su misura per le esigenze di Claudio.
**Contro:** Effort enorme per scrivere e mantenere un MCP server Python custom. Reinventa la ruota quando Kraken CLI esiste gia'.
**Verdetto:** Over-engineering.

### 5. Multi-exchange CLI (score: 2.85)

**Pro:** Copertura multi-exchange via CLI.
**Contro:** Non esiste un CLI per Binance. Progetto fantasma.
**Verdetto:** Non praticabile.

### 6. API dirette Kraken (score: 2.80)

**Pro:** Zero dipendenze.
**Contro:** Basso livello, niente indicatori, niente paper trading, niente MCP, tutto da scrivere.
**Verdetto:** Spreco di tempo.

---

## Verdetto: Ibrido (ccxt + Kraken CLI MCP)

L'approccio ibrido vince con 8.85/10. Strategia:

1. **ccxt resta il layer primario** — indicatori tecnici, previsioni ML (Kronos/Chronos), risk management hard-coded, multi-exchange
2. **Kraken CLI si aggiunge come MCP server** — market data Kraken, paper trading con prezzi live, accesso diretto per Claude
3. **Nessuna rimozione** — tutto lo stack esistente resta intatto
4. **Effort minimo** — download binary, configurazione MCP, update prompt

### Cosa guadagniamo

- Claude puo' interrogare Kraken direttamente via MCP (ticker, orderbook, OHLC) senza passare per wrapper Python
- Paper trading Kraken con prezzi live e fee simulate
- Seconda fonte dati mercato (diversificazione Binance + Kraken)
- 50 workflow skills come reference per strategie di trading
- Futures paper trading (feature nuova)

### Cosa manteniamo

- Risk management hard-coded in Python (non bypassabile)
- Indicatori tecnici via pandas-ta
- Previsioni Kronos + Chronos-Bolt
- Trade journal in SQLite
- Scanner e risk monitor loop

### Rischio residuo

- Binary esterno (Kraken CLI) va pinnato a versione specifica
- Due fonti dati (Binance via ccxt, Kraken via CLI) — usare ccxt come primaria, Kraken come supplementare
- Kraken CLI e' alpha — fallback a ccxt se MCP instabile
