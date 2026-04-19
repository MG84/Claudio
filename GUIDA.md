# Claudio — Assistente Personale AI

Assistente AI personale controllabile via Telegram, alimentato da Claude Code. Gira in Docker sul tuo Mac e ha accesso ai tuoi progetti di sviluppo.

## Architettura

```
Telegram (telefono/desktop)
    │
    ▼
Docker Container "claudio" (OrbStack)
    ├── Bot Telegram (aiogram)
    ├── Claude Agent SDK → Claude Code CLI
    ├── faster-whisper (Speech-to-Text locale)
    ├── Kronos-small (previsioni candlestick BTC/USDT)
    ├── Mem0 → Ollama + Qdrant (memoria persistente per-chat)
    └── Accesso a ~/Documents/Development/
            │
            ▼
Docker Container "claudio-ollama"
    ├── nomic-embed-text (embedding)
    └── llama3.1:8b (estrazione fatti)

Docker Container "claudio-qdrant"
    └── Vector store (memorie persistenti)

Mac bare metal
    └── Qwen3-TTS via MLX (Text-to-Speech con voice cloning)
        Server HTTP su porta 8880
```

## Cosa può fare

- **Rispondere a domande** — qualsiasi cosa, in italiano
- **Cercare sul web** — notizie, documentazione, informazioni
- **Lavorare sui tuoi progetti** — implementare feature, fixare bug, refactoring
- **Creare script e programmi** — nel workspace o nei tuoi progetti
- **Installare pacchetti** — ha accesso completo al sistema Linux nel container
- **Capire vocali** — trascrive i tuoi messaggi vocali con Whisper
- **Rispondere a voce** — genera audio con Qwen3-TTS (voice cloning disponibile)
- **Analizzare immagini** — manda foto o screenshot
- **Analizzare documenti** — manda PDF, file di testo, archivi
- **Previsioni crypto** — predice candlestick 12h avanti con Kronos AI + Chronos-Bolt (multi-pair: BTC, ETH, SOL)
- **Trading** — paper trading simulato + live trading via ccxt, risk manager hard-coded, comandi Telegram
- **Market data** — indicatori tecnici (RSI, EMA, MACD, Bollinger, ATR) multi-pair via ccxt + pandas-ta
- **Kraken MCP** — accesso diretto a dati di mercato e paper trading Kraken via MCP server nativo
- **Auto-modificarsi** — ha accesso al proprio codice sorgente

## Accesso

- **Bot Telegram:** @ClaudioDockerBot
- **Autorizzato solo per:** Marco (Telegram ID 487334262)
- **Chat privata:** domande generali, ricerche, task vari
- **Gruppo "Claudio Projects":** un Forum Topic per progetto

## Autenticazione

Claudio usa il tuo abbonamento Claude Max tramite un token OAuth generato con `claude setup-token`. Il token è valido 1 anno (scade ~aprile 2027). Zero costi aggiuntivi.

## Comandi Telegram

| Comando | Descrizione |
|---|---|
| `/start` | Benvenuto e lista comandi |
| `/projects` | Lista progetti disponibili |
| `/link <nome>` | Collega il Forum Topic corrente a un progetto |
| `/unlink` | Scollega il topic |
| `/new` | Nuova conversazione (salva la precedente e resetta contesto) |
| `/resume` | Ripristina la sessione precedente (quella prima dell'ultimo /new) |
| `/status` | Stato attuale (modello, progetto, sessione) |
| `/model <nome>` | Cambia modello Claude |
| `/opus` | Shortcut per Claude Opus 4.6 |
| `/sonnet` | Shortcut per Claude Sonnet 4.6 |
| `/haiku` | Shortcut per Claude Haiku 4.5 |
| `/effort <low\|medium\|high>` | Profondità di ragionamento |
| `/turns <n>` | Max step per risposta (default: 25) |
| `/plan` | Prossimo messaggio in planning mode (ragiona senza eseguire) |
| `/compact` | Resetta contesto (come clear) |
| `/voice` | Forza risposta vocale per il prossimo messaggio di testo |
| `/text` | Mostra il testo dell'ultima risposta vocale |
| `/memories` | Mostra i ricordi che Claudio ha su di te in questa chat |
| `/forget` | Cancella tutti i ricordi di questa chat |
| `/predict` | Previsione BTC/USDT on-demand (Kronos AI) |
| `/accuracy` | Statistiche accuracy delle previsioni Kronos |
| `/portfolio` | Bilancio, posizioni aperte, P&L giornaliero |
| `/market [pair]` | Snapshot mercato con indicatori + previsioni (default BTC/USDT) |
| `/trades [n]` | Ultimi N trade con P&L |
| `/mode paper\|live` | Switch modalita' trading (live richiede "CONFERMA") |
| `/kill` | Emergency close — chiude tutte le posizioni |
| `/autonomous on\|off` | Abilita/disabilita trading autonomo |
| `/scan` | Scan completo: mercato + previsioni + risk + posizioni |

## Comportamento vocale

Il bot risponde nello stesso formato in cui ricevi il messaggio:

| Tu mandi | Claudio risponde |
|---|---|
| Testo | Testo |
| Vocale | Vocale (Qwen3-TTS) |
| `/voice` + testo | Vocale |
| `/text` dopo un vocale | Mostra la versione testuale dell'ultima risposta vocale |

Quando Claudio genera un vocale, il testo viene automaticamente pulito: niente emoji, markdown, simboli o formattazione. Il testo è scritto per essere ascoltato, non letto.

## Forum Topics (progetti)

Ogni progetto ha il suo topic nel gruppo Telegram. Quando scrivi in un topic collegato, Claude Code lavora automaticamente nella cartella di quel progetto e ne legge il CLAUDE.md.

**Progetti collegati:**
- aloesuite
- nutribot
- brum-backend-cms
- Catechesi

**Per collegare un nuovo progetto:** crea un topic nel gruppo, entra nel topic, scrivi `/link nome-progetto`.

## Memoria persistente

Claudio ha una memoria a lungo termine per ogni chat, alimentata da **Mem0** (100% locale, zero API a pagamento).

**Come funziona:**
- Dopo ogni messaggio, Claudio estrae automaticamente i fatti importanti dalla conversazione (nomi, preferenze, decisioni, ecc.)
- Prima di rispondere, cerca i ricordi rilevanti e li include nel contesto
- I ricordi sopravvivono a `/new`, reset sessione, e rebuild Docker
- Tutto gira localmente: Ollama (LLM + embedding) e Qdrant (vector store) in container Docker separati

**Sessione vs Memoria:**
| | Sessione (SDK) | Memoria (Mem0) |
|---|---|---|
| Cosa contiene | Conversazione corrente | Fatti estratti |
| Durata | Fino a `/new` o context pieno | Permanente |
| Reset | `/new`, `/compact` | `/forget` |
| Sopravvive a rebuild | Si (sessions.json) | Si (volume Qdrant) |

**Primo avvio:** al primo `docker compose up`, Ollama scarica i modelli necessari (~5 GB). Le volte successive il boot è istantaneo.

**Disabilitare:** settare `MEM0_ENABLED=false` nel `.env` per disattivare completamente la memoria.

## Gestione sessioni

Ogni topic e ogni chat hanno sessioni indipendenti. Claude Code ricorda il contesto della conversazione tra messaggi.

| Azione | Cosa succede |
|---|---|
| Scrivi messaggi | La sessione accumula contesto |
| `/new` | La sessione corrente viene salvata, ne inizia una pulita |
| `/resume` | Torna alla sessione salvata con `/new` (ripristina il contesto) |
| `/compact` | Come `/new` — resetta il contesto |

Le sessioni sono isolate per progetto: fare `/new` in nutribot non tocca la sessione di aloesuite.

## Gestione vocale — Dettagli tecnici

**Speech-to-Text (STT):** faster-whisper con modello large-v3-turbo (int8 quantizzato). Gira localmente nel container Docker su CPU ARM64. Latenza: ~5 secondi per un vocale di 30 secondi. Il modello (~1.6GB) viene scaricato al primo utilizzo e cachato nel volume `whisper_cache`.

**Text-to-Speech (TTS):** Qwen3-TTS via MLX gira sul Mac bare metal (fuori Docker) sulla porta 8880, esposto come HTTP API tramite mlx-tts-api. Se il server TTS non è attivo, Claudio usa automaticamente Edge TTS (Microsoft, voce "Diego" italiana) come fallback.

**Voci preset disponibili:** serena, vivian, ryan, aiden, eric, dylan, uncle_fu, ono_anna, sohee

**Voice cloning:** il flusso è interamente conversazionale — dì a Claudio "voglio clonare la mia voce" e lui ti guida:

1. Manda un vocale di 15-30 secondi di parlato naturale
2. Claudio mostra la trascrizione — conferma o correggi
3. Dopo la conferma, Claudio registra la voce e genera 5 sample audio con frasi diverse
4. Ricevi i 5 vocali su Telegram — scegli il migliore
5. Se vuoi, Claudio lo imposta come voce predefinita

Nessun codice hardcodato — Claudio orchestra tutto via bash (ffmpeg + curl al TTS server). Puoi iterare quante volte vuoi.

**Invio file da Claude a Telegram:** Claudio può inviarti file su Telegram (audio, documenti, immagini) salvandoli in cartelle speciali:
- `/home/assistant/uploads/send_voice/` — inviati come messaggi vocali (.ogg, .wav, .mp3)
- `/home/assistant/uploads/send_file/` — inviati come documenti (qualsiasi formato)

I file vengono inviati automaticamente al termine della risposta e poi cancellati.

**Registro voci clonate:** tutte le voci sono tracciate in:
```
/home/assistant/memory/voices/
  voices.json          — registro (nome, UUID, data, note)
  originals/           — file WAV usati per la clonazione
  samples/             — audio di prova per la valutazione
```

**Per registrare una voce manualmente:**
```
curl -X POST http://localhost:8880/v1/voices \
  -F 'audio=@tuo_vocale.wav' \
  -F 'name=marco' \
  -F 'ref_text=Trascrizione esatta di quello che dici nel vocale' \
  -F 'language=Italian'
```
Il comando ritorna un UUID. Aggiungilo nel `.env` come `TTS_VOICE=<uuid>` e rebuilda il container.

**Per cambiare voce senza rebuild (a caldo):** scrivi in `/home/assistant/memory/runtime_config.json`:
```json
{"TTS_VOICE": "serena"}
```
Il cambiamento è immediato, senza riavviare il container.

**Per cambiare voce in modo permanente (con rebuild):** modifica `TTS_VOICE` nel `.env` (es. `TTS_VOICE=serena`) e rebuilda.

## Kronos — Previsioni crypto

Claudio include **Kronos-small**, un modello AI (24.7M parametri) per previsioni candlestick crypto. Fetcha candele BTC/USDT da Binance ogni ora, predice le prossime 12 candele (12h avanti), e traccia l'accuracy nel tempo. Zero rischio finanziario — solo osservazione.

### Primo avvio

Al primo `docker compose up -d --build` dopo l'integrazione:

1. Il build Docker clona il codice modello Kronos (~50KB) e installa le dipendenze (torch, ccxt, pandas, etc.)
2. All'avvio del container, Kronos scarica i pesi del modello da HuggingFace (~100MB) — una sola volta, poi cached nel volume `hf_cache`
3. Nei log vedrai `Kronos model loaded (CPU)` seguito da `Kronos loop started`
4. Da quel momento, una previsione parte automaticamente ogni ora

**Verifica:** `docker logs -f claudio` — cerca "Kronos model loaded" e "Kronos prediction".

### Comandi

| Comando | Cosa fa |
|---|---|
| `/predict` | Lancia una previsione on-demand e mostra il risultato |
| `/accuracy` | Mostra le statistiche aggregate (direction accuracy, MAE, hit rate) |

**Esempio output `/predict`:**
```
📊 Kronos — BTC/USDT (1h)
Prezzo attuale: $84,250.30

Previsione:
  +1h:  $84,500 (+0.30%)
  +6h:  $85,100 (+1.01%)
  +12h: $86,200 (+2.31%)

Direzione: ↗️ UP
```

**Esempio output `/accuracy`** (dopo alcune ore di raccolta dati):
```
📈 Kronos Accuracy — BTC/USDT
Previsioni totali: 48
Verificate: 42
Direzione corretta: 58.3%
Errore medio (MAE): $320.50
Hit rate 1h: 62.1%
Hit rate 6h: 55.4%
Hit rate 12h: 51.2%
```

### Come funziona

1. **Ogni ora** il loop periodico fetcha le ultime 400 candele 1h BTC/USDT da Binance (dati pubblici, no API key)
2. Kronos-small predice le prossime 12 candele (OHLC completo), mediando 5 sample
3. La previsione viene salvata in SQLite (`kronos.db`) e emessa come evento dashboard
4. In parallelo, il loop verifica le previsioni passate confrontandole con i prezzi reali, calcolando direction accuracy e MAE

### Configurazione

| Variabile | Default | Descrizione |
|---|---|---|
| `KRONOS_ENABLED` | `true` | Abilita/disabilita Kronos |

Per disabilitare senza rebuild: `KRONOS_ENABLED=false` nel `.env`.

Tutti gli altri parametri (symbol, timeframe, lookback, temperature, etc.) sono in `bot/config.py` come costanti `KRONOS_*`.

### Dati e storage

- **Database:** `/home/assistant/memory/kronos.db` (nel volume Docker `memory`, persiste tra rebuild)
- **Pesi modello:** cached nel volume Docker `hf_cache` (persiste tra rebuild)
- **Codice modello:** `/home/assistant/kronos_model/model/` (nel container, ricostruito ad ogni build)

### Prerequisiti

Nessuno. Kronos usa solo dati pubblici di Binance (no API key) e gira su CPU. Le dipendenze aggiuntive (torch, ccxt, pandas) sono installate automaticamente nel build Docker.

## Trading

Claudio e' il tuo personal trader. Analizza i mercati, decide la strategia, propone azioni, e puo' eseguirle — anche in autonomia. Claude e' il cervello, Python enforza i limiti di rischio.

### Modalita'

| Modalita' | Comportamento |
|---|---|
| **Paper** (default) | Trading simulato in SQLite, zero rischio |
| **Live** | Ordini reali via ccxt (richiede API key exchange) |

### Segnali previsionali

- **Kronos-small** — previsione candlestick OHLC multivariate, 12h avanti
- **Chronos-Bolt** — previsione close univariate con bande di incertezza (q10/q50/q90)
- Quando concordano sulla direzione → maggiore confidenza; quando discordano → cautela
- Loop automatico ogni ora su BTC/USDT, ETH/USDT, SOL/USDT

### Indicatori tecnici

RSI(14), EMA(20/50/200), MACD(12/26/9), Bollinger(20,2), ATR(14) — via ccxt (Binance) + pandas-ta.

### Limiti di rischio (hard-coded, non bypassabili)

| Limite | Valore |
|---|---|
| Max posizione | 20% del portfolio |
| Max posizioni aperte | 3 |
| Max perdita giornaliera | 5% (stop trading) |
| Max drawdown | 15% (kill switch automatico) |
| Stop-loss | Obbligatorio |
| Max trade al giorno | 10 |

### Scanner e Risk Monitor

- **Market scanner** (ogni ora): assembla contesto completo e lo invia a Claude (autonomous) o su Telegram (supervised)
- **Risk monitor** (ogni 5 min): controlla drawdown e perdite, attiva kill switch se necessario

### Kraken CLI MCP

Claudio ha accesso diretto a Kraken via MCP server (Kraken CLI v0.3.1). Claude puo' interrogare ticker, orderbook, OHLC e fare paper trading su Kraken con prezzi live — senza passare per wrapper Python.

Servizi MCP abilitati di default: `market` (dati pubblici) + `paper` (paper trading spot). Configurabile con `KRAKEN_MCP_SERVICES` nel docker-compose.

**Ruolo:** complementare a ccxt. ccxt resta il layer primario per indicatori tecnici, previsioni ML e risk management.

**Disabilitare:** `KRAKEN_CLI_ENABLED=false` nel `.env`.

## Avvio e arresto

**Bot (Docker):**
```
docker compose up -d              # avvia
docker compose down                # ferma
docker compose up -d --build       # ricostruisci dopo modifiche al codice
docker logs claudio                # vedi log
docker logs -f claudio             # segui log in tempo reale
docker stats claudio --no-stream   # uso CPU/RAM
```

**TTS Server (Mac bare metal):**
```
cd ~/.claudio-tts/mlx-tts-api
source ../.venv/bin/activate
MLX_TTS_PORT=8880 python server.py
```

**Per autostart del TTS al login:**
```
bash scripts/install_tts_service.sh
```

**Per fermare il servizio TTS:**
```
launchctl unload ~/Library/LaunchAgents/com.claudio.tts.plist
```

**Per verificare che il TTS funziona:**
```
curl -s http://localhost:8880/docs > /dev/null && echo "OK" || echo "SPENTO"
```

## File di configurazione

**`.env`** — contiene tutti i segreti (token OAuth, bot token, user ID, voce TTS). Mai committare.

**`CLAUDE.md`** — istruzioni per Claude Code quando lavora su questo progetto.

**`topic_map.json`** (nel volume memory) — mapping tra Forum Topic ID e nome progetto. Persistito automaticamente.

## Struttura file

```
Claudio/
├── .env                        # Segreti (gitignored)
├── .env.example                # Template per .env
├── .gitignore
├── CLAUDE.md                   # Contesto progetto per Claude Code
├── GUIDA.md                    # Questo file
├── Dockerfile                  # Immagine container
├── docker-compose.yml          # Configurazione Docker
├── requirements.txt            # Dipendenze Python
├── bot/
│   ├── main.py                 # Entrypoint, wiring handler e startup
│   ├── config.py               # Tutte le costanti e variabili d'ambiente
│   ├── prompts.py              # System prompt e project prompt
│   ├── claude_bridge.py        # Bridge Claude Agent SDK, lock, sessioni, retry, memory injection
│   ├── memory.py               # Memoria persistente per-chat via Mem0 (Ollama + Qdrant)
│   ├── kronos.py               # Kronos advisor: previsioni crypto, SQLite, verifica, loop
│   ├── chronos_predictor.py    # Chronos-Bolt: forecasting univariate con bande incertezza
│   ├── market.py               # Market data aggregator multi-pair (ccxt + pandas-ta)
│   ├── trading.py              # Execution layer: paper + live trading, risk manager
│   ├── scanner.py              # Market scanner (orario) + risk monitor (5 min)
│   ├── voice.py                # STT (faster-whisper) + TTS (Qwen3/Edge)
│   ├── text_cleaner.py         # Pulizia testo per TTS, split messaggi
│   ├── monitor.py              # Capture eventi, SQLite, broadcast WebSocket, metriche
│   ├── ws_server.py            # Server aiohttp: dashboard statica, /ws, git action handler
│   ├── git_ops.py              # Operazioni git per tab Changes (diff, untracked, stage, revert, commit, scan all)
│   ├── cleanup.py              # Task periodico pulizia file (>24h)
│   ├── projects.py             # Discovery progetti, mapping Forum Topics
│   ├── auth.py                 # Filtro utenti autorizzati
│   └── handlers/               # Comandi Telegram separati per area
│       ├── _state.py           # Stato condiviso (bridge, topic_map, flags)
│       ├── commands.py         # /start, /status, /new, /resume, /compact, /memories, /forget
│       ├── model.py            # /model, /opus, /sonnet, /haiku, /effort, /turns, /plan
│       ├── projects_cmds.py    # /projects, /link, /unlink
│       ├── voice_cmds.py       # /voice, /text
│       ├── kronos_cmds.py      # /predict, /accuracy
│       ├── trading_cmds.py     # /portfolio, /market, /trades, /mode, /kill, /autonomous, /scan
│       └── messages.py         # Handler messaggi (testo, vocali, foto, documenti, send queue)
├── tests/
│   ├── test_git_ops.py         # Test operazioni git (37 test)
│   ├── test_market.py          # Test market data aggregator (31 test)
│   └── test_memory.py          # Test memoria Mem0 (20 test)
├── scripts/
│   ├── entrypoint.sh           # Startup container
│   ├── setup_tts.sh            # Installazione Qwen3-TTS sul Mac
│   └── install_tts_service.sh  # Autostart TTS come launchd service
└── memory/                     # Memoria persistente (volume Docker)
    └── voices/                 # Registro voci clonate
        ├── voices.json         # Metadati voci (nome, UUID, data, note)
        ├── originals/          # File WAV originali per la clonazione
        └── samples/            # Audio di prova per la valutazione

~/.claudio-tts/                 # TTS server (fuori dal progetto)
├── .venv/                      # Virtual environment Python
├── mlx-tts-api/                # Server HTTP per Qwen3-TTS
├── tts.log                     # Log del server
└── tts.err                     # Errori del server
```

## Sicurezza

- Solo il tuo Telegram ID può interagire col bot
- Il token OAuth e il bot token sono nel `.env`, protetto da `.gitignore`
- Claude Code gira con `bypassPermissions` dentro il container — ha accesso completo
- I tuoi progetti sono montati in read-write — Claude può modificare i file
- Regole di sicurezza git nel system prompt: mai commit su main, mai force push

## Auto-evoluzione

Claudio ha accesso al proprio codice sorgente in `/home/assistant/projects/Claudio/`. Puoi chiedergli di modificarsi via Telegram. Dopo le modifiche, serve un rebuild:
```
docker compose down && docker compose up -d --build
```

Claudio conosce la propria architettura (è nel suo system prompt) e sa come funzionano il TTS, lo STT, i Forum Topics e i progetti.

## Dashboard di monitoraggio

Dashboard web real-time per monitorare Claudio: [claudio-monitor.vercel.app](https://claudio-monitor.vercel.app)

**Cosa mostra:**
- Stato sistema: online/offline, CPU, RAM, uptime, sessioni attive, messaggi oggi
- Attività: task corrente (idle/thinking/executing/listening), tool in uso, progetto attivo
- Costi: costo per query, costo giornaliero cumulativo
- Log real-time per progetto: card separate per ogni chat/progetto (collassabili)
- Stato TTS server

**Architettura:** tutto locale. Il bot serve la dashboard come file statici su porta 3333 e invia eventi via WebSocket diretto. Cloudflare Tunnel per accesso remoto.

**Accesso:**
- Locale: `http://localhost:3333`
- Remoto: URL Cloudflare Tunnel (visibile con `docker logs claudio-tunnel`)

**Autenticazione:** protetta da password (configurata in `.env` come `DASHBOARD_PASSWORD`). Cookie di sessione valido 30 giorni.

**Storico:** al refresh della pagina, il server invia gli ultimi 100 eventi da SQLite. I dati non si perdono.

**Quick Actions:** puoi mandare messaggi a Claudio direttamente dalla dashboard (barra in basso), senza aprire Telegram. Bottoni rapidi per cambiare modello, effort, reset sessione.

**Notifiche browser:** ricevi una notifica quando Claudio finisce un task o ha un errore (solo se la tab non è in focus).

**Tab Changes (Code Review):** la dashboard mostra lo stato git di tutti i progetti all'apertura, stile Fork. Puoi:
- Vedere subito tutte le modifiche pending in ogni progetto (non solo dopo una query Claude)
- File untracked (nuovi, non in git) visibili con icona "?" in blu
- Vedere i file modificati con diff colorati (aggiunte in verde, rimozioni in rosso)
- Stage/unstage singoli file
- Revert singoli file o tutti
- Committare con un messaggio
- Bottone "Refresh" per aggiornare manualmente lo stato di tutti i progetti
- Layout responsive: su mobile i file sono impilati (accordion), su desktop split con file list a sinistra e diff a destra

**Repo sorgente dashboard:** github.com/MG84/claudio-monitor (Next.js, static export)

## Regola fondamentale: documentazione

**Dopo ogni modifica al progetto, aggiornare SEMPRE la documentazione:**
- `GUIDA.md` — documentazione utente (questo file)
- `CLAUDE.md` — contesto per Claude Code
- `IMPLEMENTAZIONE.md` — piano tecnico (se rilevante)

Questo vale sia per modifiche fatte da qui (Claude Code sul Mac) sia per modifiche fatte da Claudio via Telegram. La documentazione deve sempre riflettere lo stato attuale del progetto.
