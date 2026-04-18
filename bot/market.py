"""
Market Data Aggregator — multi-pair OHLCV, ticker, orderbook, technical indicators.
Fetches from Binance via ccxt, computes indicators with pandas-ta, caches with TTL.
"""

import asyncio
import logging
import time

import ccxt.async_support as ccxt_async
import pandas as pd

from bot.config import (
    TRADING_PAIRS,
    MARKET_CACHE_SECONDS,
    MARKET_TICKER_CACHE_SECONDS,
    MARKET_OHLCV_LIMIT,
)

log = logging.getLogger("claudio.market")

# ── Module-level state (singleton pattern) ──────────────────────────
_exchange: ccxt_async.binance | None = None
_cache: dict[str, tuple[float, object]] = {}  # key -> (expires_at, data)


# ── Exchange singleton ──────────────────────────────────────────────

def _get_exchange() -> ccxt_async.binance:
    """Get or create the Binance exchange instance (reuse for connection pooling)."""
    global _exchange
    if _exchange is None:
        _exchange = ccxt_async.binance({"enableRateLimit": True})
    return _exchange


async def close():
    """Close exchange connection. Call on shutdown."""
    global _exchange
    if _exchange is not None:
        await _exchange.close()
        _exchange = None


# ── Cache helpers ───────────────────────────────────────────────────

def _cache_key(*parts: str) -> str:
    return ":".join(parts)


def _cache_get(key: str) -> object | None:
    """Return cached value if still valid, else None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, data = entry
    if time.monotonic() > expires_at:
        del _cache[key]
        return None
    return data


def _cache_set(key: str, data: object, ttl: float) -> None:
    _cache[key] = (time.monotonic() + ttl, data)


def clear_cache() -> None:
    """Clear all cached data."""
    _cache.clear()


# ── OHLCV ───────────────────────────────────────────────────────────

async def get_ohlcv(
    pair: str = "BTC/USDT",
    timeframe: str = "1h",
    limit: int = MARKET_OHLCV_LIMIT,
) -> list[list]:
    """Fetch OHLCV candles from Binance.

    Returns list of [timestamp_ms, open, high, low, close, volume].
    Cached for MARKET_CACHE_SECONDS.
    """
    key = _cache_key("ohlcv", pair, timeframe, str(limit))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    exchange = _get_exchange()
    ohlcv = await exchange.fetch_ohlcv(pair, timeframe, limit=limit)
    _cache_set(key, ohlcv, MARKET_CACHE_SECONDS)
    log.debug(f"Fetched {len(ohlcv)} candles for {pair} {timeframe}")
    return ohlcv


# ── Ticker ──────────────────────────────────────────────────────────

async def get_ticker(pair: str = "BTC/USDT") -> dict:
    """Get current price, 24h volume, and 24h change %.

    Returns dict with keys: symbol, last, volume_24h, change_pct_24h, bid, ask, high_24h, low_24h.
    """
    key = _cache_key("ticker", pair)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    exchange = _get_exchange()
    raw = await exchange.fetch_ticker(pair)

    ticker = {
        "symbol": pair,
        "last": raw.get("last"),
        "volume_24h": raw.get("quoteVolume"),
        "change_pct_24h": raw.get("percentage"),
        "bid": raw.get("bid"),
        "ask": raw.get("ask"),
        "high_24h": raw.get("high"),
        "low_24h": raw.get("low"),
    }
    _cache_set(key, ticker, MARKET_TICKER_CACHE_SECONDS)
    log.debug(f"Fetched ticker for {pair}: ${ticker['last']:,.2f}")
    return ticker


# ── Order book ──────────────────────────────────────────────────────

async def get_orderbook(pair: str = "BTC/USDT", depth: int = 10) -> dict:
    """Get order book with bid/ask spread.

    Returns dict with keys: symbol, bids, asks, spread, spread_pct, mid_price.
    """
    key = _cache_key("orderbook", pair, str(depth))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    exchange = _get_exchange()
    raw = await exchange.fetch_order_book(pair, limit=depth)

    best_bid = raw["bids"][0][0] if raw["bids"] else 0
    best_ask = raw["asks"][0][0] if raw["asks"] else 0
    mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0
    spread = best_ask - best_bid
    spread_pct = (spread / mid_price * 100) if mid_price else 0

    orderbook = {
        "symbol": pair,
        "bids": raw["bids"][:depth],
        "asks": raw["asks"][:depth],
        "spread": round(spread, 2),
        "spread_pct": round(spread_pct, 4),
        "mid_price": round(mid_price, 2),
    }
    _cache_set(key, orderbook, MARKET_TICKER_CACHE_SECONDS)
    log.debug(f"Fetched orderbook for {pair}: spread={orderbook['spread_pct']}%")
    return orderbook


# ── Technical indicators ────────────────────────────────────────────

def _compute_indicators(ohlcv: list[list]) -> dict:
    """Compute technical indicators from OHLCV data. Blocks — call via asyncio.to_thread."""
    import pandas_ta as ta  # lazy import — heavy lib, only needed here

    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # RSI(14)
    rsi_series = ta.rsi(close, length=14)
    rsi = round(float(rsi_series.iloc[-1]), 2) if rsi_series is not None and not rsi_series.empty else None

    # EMA(20, 50, 200)
    ema20_series = ta.ema(close, length=20)
    ema50_series = ta.ema(close, length=50)
    ema200_series = ta.ema(close, length=200)
    ema20 = round(float(ema20_series.iloc[-1]), 2) if ema20_series is not None and not ema20_series.empty else None
    ema50 = round(float(ema50_series.iloc[-1]), 2) if ema50_series is not None and not ema50_series.empty else None
    ema200 = round(float(ema200_series.iloc[-1]), 2) if ema200_series is not None and not ema200_series.empty else None

    # MACD(12, 26, 9)
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    macd = None
    if macd_df is not None and not macd_df.empty:
        last = macd_df.iloc[-1]
        macd = {
            "macd": round(float(last.iloc[0]), 2),
            "signal": round(float(last.iloc[1]), 2),
            "histogram": round(float(last.iloc[2]), 2),
        }

    # Bollinger Bands(20, 2)
    bbands_df = ta.bbands(close, length=20, std=2)
    bollinger = None
    if bbands_df is not None and not bbands_df.empty:
        last = bbands_df.iloc[-1]
        bollinger = {
            "lower": round(float(last.iloc[0]), 2),
            "mid": round(float(last.iloc[1]), 2),
            "upper": round(float(last.iloc[2]), 2),
            "bandwidth": round(float(last.iloc[3]), 4) if len(last) > 3 else None,
            "pct_b": round(float(last.iloc[4]), 4) if len(last) > 4 else None,
        }

    # ATR(14)
    atr_series = ta.atr(high, low, close, length=14)
    atr = round(float(atr_series.iloc[-1]), 2) if atr_series is not None and not atr_series.empty else None

    return {
        "rsi": rsi,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "macd": macd,
        "bollinger": bollinger,
        "atr": atr,
    }


async def get_indicators(
    pair: str = "BTC/USDT",
    timeframe: str = "1h",
) -> dict:
    """Compute RSI, EMA, MACD, Bollinger, ATR from OHLCV data.

    Fetches OHLCV first (uses cache), then computes indicators in a thread.
    Returns dict with keys: rsi, ema20, ema50, ema200, macd, bollinger, atr.
    """
    key = _cache_key("indicators", pair, timeframe)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    ohlcv = await get_ohlcv(pair, timeframe)
    indicators = await asyncio.to_thread(_compute_indicators, ohlcv)
    _cache_set(key, indicators, MARKET_CACHE_SECONDS)
    return indicators


# ── Market summary ──────────────────────────────────────────────────

async def get_market_summary(pairs: list[str] | None = None) -> str:
    """Formatted text snapshot of all pairs for Claude's context.

    Fetches ticker + indicators for each pair concurrently.
    Returns multi-line string suitable for system prompt injection.
    """
    if pairs is None:
        pairs = TRADING_PAIRS

    # Fetch all data concurrently
    tasks = []
    for pair in pairs:
        tasks.append(_get_pair_summary(pair))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    lines = ["--- Market Data ---"]
    for pair, result in zip(pairs, results):
        if isinstance(result, Exception):
            lines.append(f"\n{pair}: Error fetching data ({result})")
            continue
        lines.append(result)

    lines.append("--- End Market Data ---")
    return "\n".join(lines)


async def _get_pair_summary(pair: str) -> str:
    """Build summary text for a single pair."""
    ticker, indicators = await asyncio.gather(
        get_ticker(pair),
        get_indicators(pair),
    )

    price = ticker["last"]
    change = ticker["change_pct_24h"]
    volume = ticker["volume_24h"]

    parts = [
        f"\n{pair}:",
        f"  Price: ${price:,.2f} ({'+' if change >= 0 else ''}{change:.2f}% 24h)",
        f"  Volume 24h: ${volume:,.0f}" if volume else "  Volume 24h: N/A",
        f"  Bid/Ask: ${ticker['bid']:,.2f} / ${ticker['ask']:,.2f}" if ticker.get("bid") else "",
        f"  RSI(14): {indicators['rsi']}" if indicators.get("rsi") is not None else "",
    ]

    # EMAs
    emas = []
    if indicators.get("ema20") is not None:
        emas.append(f"20={indicators['ema20']:,.2f}")
    if indicators.get("ema50") is not None:
        emas.append(f"50={indicators['ema50']:,.2f}")
    if indicators.get("ema200") is not None:
        emas.append(f"200={indicators['ema200']:,.2f}")
    if emas:
        parts.append(f"  EMA: {', '.join(emas)}")

    # MACD
    macd = indicators.get("macd")
    if macd:
        parts.append(
            f"  MACD: {macd['macd']:+.2f} signal={macd['signal']:.2f} hist={macd['histogram']:+.2f}"
        )

    # Bollinger
    bb = indicators.get("bollinger")
    if bb:
        parts.append(
            f"  Bollinger(20,2): {bb['lower']:,.2f} / {bb['mid']:,.2f} / {bb['upper']:,.2f}"
        )

    # ATR
    if indicators.get("atr") is not None:
        parts.append(f"  ATR(14): {indicators['atr']:,.2f}")

    return "\n".join(p for p in parts if p)
