---
phase: "01-market-data"
plan: "01-01"
subsystem: "market-data"
tags: ["ccxt", "pandas-ta", "indicators", "cache", "async"]
dependency-graph:
  requires: []
  provides: ["bot/market.py", "market-data-api"]
  affects: ["bot/config.py", "requirements.txt", "CLAUDE.md"]
tech-stack:
  added: ["pandas-ta"]
  patterns: ["singleton-exchange", "ttl-cache", "lazy-import", "asyncio.to_thread"]
key-files:
  created:
    - bot/market.py
    - tests/test_market.py
  modified:
    - bot/config.py
    - requirements.txt
    - CLAUDE.md
decisions:
  - "Lazy import pandas_ta in _compute_indicators to avoid import-time errors in environments without the lib"
  - "Reuse ccxt singleton exchange with enableRateLimit for connection pooling and rate limiting"
  - "Cache key includes pair + timeframe + limit for proper cache isolation"
metrics:
  duration: "8m"
  completed: "2026-04-18"
  tasks: 4
  files-created: 2
  files-modified: 3
  tests-added: 31
---

# Phase 01 Plan 01: Market Data + Indicators Summary

Multi-pair market data aggregator with OHLCV, ticker, orderbook, and 5 technical indicators (RSI, EMA, MACD, Bollinger, ATR) via ccxt + pandas-ta, with TTL cache to avoid exchange rate limiting.

## Tasks Completed

| Task | Description | Commit | Key Changes |
|------|-------------|--------|-------------|
| 1 | Create bot/market.py core module | abbf8a5 | 320-line module: get_ohlcv, get_ticker, get_orderbook, get_indicators, get_market_summary |
| 2 | Add config constants | 97a135e | TRADING_PAIRS, MARKET_CACHE_SECONDS, MARKET_TICKER_CACHE_SECONDS, MARKET_OHLCV_LIMIT |
| 3 | Add pandas-ta dependency | 0a0480d | pandas-ta>=0.3.0 in requirements.txt |
| 4 | Test market data functions | 952a54b | 31 tests covering OHLCV, ticker, orderbook, indicators, cache, summary, exchange |

## Additional Commits

| Commit | Description |
|--------|-------------|
| 67b480d | Lazy import pandas_ta in _compute_indicators (startup optimization) |
| 81d6ee2 | Update CLAUDE.md with market data module documentation |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Lazy import pandas_ta to fix import-time failure**
- **Found during:** Task 4 (tests failed to import bot.market because pandas_ta unavailable in dev)
- **Issue:** `import pandas_ta as ta` at module top level caused ImportError in environments without pandas-ta (dev machine has Python 3.11, pandas-ta requires 3.12+)
- **Fix:** Moved import inside `_compute_indicators()` function (lazy import). Also improves startup time since pandas-ta is heavy and only needed for indicator computation.
- **Files modified:** bot/market.py
- **Commit:** 67b480d

## Implementation Details

### Module Architecture (bot/market.py)
- **Singleton exchange:** `_get_exchange()` creates/reuses one ccxt Binance instance with `enableRateLimit=True`
- **TTL cache:** `_cache_get/_cache_set` using `time.monotonic()` for expiry. Keys encode function+pair+timeframe+limit for proper isolation
- **Async pattern:** All exchange calls are native async (ccxt.async_support). Indicator computation uses `asyncio.to_thread()` for CPU-bound pandas operations
- **Error handling:** `get_market_summary()` uses `return_exceptions=True` in gather, gracefully shows errors per-pair without crashing

### Functions Implemented
| Function | Purpose | Cache TTL |
|----------|---------|-----------|
| `get_ohlcv(pair, timeframe, limit)` | OHLCV candles from Binance | 60s |
| `get_ticker(pair)` | Price, volume, 24h change | 30s |
| `get_orderbook(pair, depth)` | Bids/asks with spread | 30s |
| `get_indicators(pair, timeframe)` | RSI, EMA, MACD, Bollinger, ATR | 60s |
| `get_market_summary(pairs)` | Formatted text for Claude context | (composed) |

### Config Constants (bot/config.py)
```python
TRADING_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
MARKET_CACHE_SECONDS = 60
MARKET_TICKER_CACHE_SECONDS = 30
MARKET_OHLCV_LIMIT = 400
```

## Verification Results

- bot/market.py created and importable (verified)
- Config constants added to bot/config.py (verified)
- pandas-ta>=0.3.0 added to requirements.txt (verified)
- 31 tests pass: OHLCV structure/cache, ticker keys/cache, orderbook spread, indicators structure/cache, market summary formatting/error handling, cache TTL/clear, exchange singleton/close
- Existing tests unaffected: test_git_ops.py (37 pass), test_memory.py (20 pass)

## Self-Check: PASSED

- All 6 commits found in git log
- All 3 created/modified files verified on disk
- Config constants importable with correct values
- bot/market.py importable with all expected functions
- pandas-ta present in requirements.txt
