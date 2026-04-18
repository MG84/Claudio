---
phase: "02-chronos-bolt"
plan: "02-01"
subsystem: predictions
tags: [chronos-bolt, forecasting, quantile, uncertainty-bands]
dependency_graph:
  requires: [bot/market.py, bot/config.py, bot/monitor.py]
  provides: [bot/chronos_predictor.py, chronos_predictions table]
  affects: [bot/main.py, requirements.txt, CLAUDE.md]
tech_stack:
  added: [chronos-forecasting]
  patterns: [ChronosPipeline, quantile forecasting, asyncio.to_thread]
key_files:
  created: [bot/chronos_predictor.py]
  modified: [bot/config.py, bot/main.py, requirements.txt, CLAUDE.md]
decisions:
  - Used chronos-forecasting package (ChronosPipeline) rather than raw transformers AutoModelForSeq2SeqLM
  - Shared kronos.db with separate chronos_predictions table (not a new DB file)
  - Multi-pair prediction loop (all TRADING_PAIRS) rather than BTC-only like Kronos
metrics:
  duration: "216s"
  completed: "2026-04-18T20:47:00Z"
  tasks: 4
  files: 5
---

# Phase 2 Plan 01: Chronos-Bolt Predictions Summary

Chronos-Bolt univariate close-price forecaster with quantile uncertainty bands (q10/q50/q90) using amazon/chronos-bolt-small, parallel hourly loop alongside Kronos for all trading pairs.

## Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create chronos_predictor.py | 27c9387 | bot/chronos_predictor.py |
| 2 | Add config constants | 0c1befe | bot/config.py |
| 3 | Add dependency | 0428638 | requirements.txt |
| 4 | Wire into main.py | 6651ed1 | bot/main.py |
| - | Update CLAUDE.md | 4e9ea7d | CLAUDE.md |

## Decisions Made

1. **ChronosPipeline over raw transformers**: Used the `chronos-forecasting` package which provides `ChronosPipeline.from_pretrained()` -- cleaner API, handles quantile extraction natively.
2. **Shared DB, separate table**: `chronos_predictions` table in existing `kronos.db` rather than a new DB file. Keeps the memory directory clean.
3. **Multi-pair loop**: Unlike Kronos (BTC-only), Chronos-Bolt iterates over all `TRADING_PAIRS` each hour, since it uses the shared `market.py` infrastructure.

## Deviations from Plan

### Auto-added (Rule 2)

**1. [Rule 2 - Missing functionality] CLAUDE.md documentation update**
- **Found during:** Post-task review
- **Issue:** CLAUDE.md rules require documentation updates after every change
- **Fix:** Added Chronos-Bolt section and Struttura entry to CLAUDE.md
- **Files modified:** CLAUDE.md
- **Commit:** 4e9ea7d

## Architecture

```
bot/market.py (get_ohlcv)
       |
       v
bot/chronos_predictor.py
  - init() -> ChronosPipeline.from_pretrained (asyncio.to_thread)
  - predict() -> quantile forecasts (q10, q50, q90)
  - chronos_loop() -> hourly for all TRADING_PAIRS
  - _get_db() -> chronos_predictions table in kronos.db
       |
       v
bot/monitor.py (emit chronos_prediction events)
```

## Self-Check: PASSED

- FOUND: bot/chronos_predictor.py
- FOUND: 27c9387
- FOUND: 0c1befe
- FOUND: 0428638
- FOUND: 6651ed1
- FOUND: 4e9ea7d
