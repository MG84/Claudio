# Trading Agent — Roadmap

> Imported from: docs/TRADING_ARCHITECTURE.md
> Created: 2026-04-18

## Milestone 1: Autonomous Trading Agent

### Phase 1: Market Data + Indicators
- **Goal:** Centralized multi-pair market data aggregator with technical indicators
- **Key files:** `bot/market.py`, `bot/config.py`
- **Plans:** 01-01-PLAN.md

### Phase 2: Chronos-Bolt Predictions
- **Goal:** Second forecasting signal with uncertainty bands, parallel to Kronos
- **Key files:** `bot/chronos_predictor.py`, `Dockerfile`, `docker-compose.yml`
- **Depends on:** Phase 1 (shared config.py/requirements.txt)
- **Plans:** 02-01-PLAN.md

### Phase 3: Execution Layer + Kraken CLI
- **Goal:** Trading execution with hard-coded risk limits via Kraken CLI
- **Key files:** `bot/trading.py`, `Dockerfile`, `scripts/entrypoint.sh`
- **Depends on:** Phase 1
- **Plans:** 03-01-PLAN.md

### Phase 4: Kronos Expansion
- **Goal:** Extend existing Kronos module with multi-pair, latest prediction access, confidence scoring
- **Key files:** `bot/kronos.py`
- **Depends on:** —
- **Plans:** 04-01-PLAN.md

### Phase 5: Trading Commands
- **Goal:** Telegram commands for portfolio, market, trades, mode, kill, autonomous, scan
- **Key files:** `bot/handlers/trading_cmds.py`, `bot/main.py`
- **Depends on:** Phase 1, Phase 3, Phase 4
- **Plans:** 05-01-PLAN.md

### Phase 6: Market Scanner + Risk Monitor
- **Goal:** Background loops for autonomous market analysis and risk monitoring
- **Key files:** `bot/main.py`
- **Depends on:** Phase 1, Phase 2, Phase 3, Phase 4
- **Plans:** 06-01-PLAN.md

### Phase 7: System Prompt + Documentation
- **Goal:** Trading roles in system prompt, updated CLAUDE.md and GUIDA.md
- **Key files:** `bot/prompts.py`, `CLAUDE.md`, `GUIDA.md`
- **Depends on:** Phase 1-6
- **Plans:** 07-01-PLAN.md

### Phase 8: Dashboard Backend Prerequisites
- **Goal:** REST endpoints, trade_executed events, auth fix, deploy tooling for trading dashboard
- **Key files:** `bot/trading.py`, `bot/ws_server.py`, `scripts/deploy_dashboard.sh`
- **Depends on:** Phase 1-7
- **Plans:** 08-01-PLAN.md (cleanup + events + auth), 08-02-PLAN.md (REST endpoints + CORS + deploy + docs)
- **Source:** `docs/TRADING_DASHBOARD.md` (Wave 0)
