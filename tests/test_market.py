"""
Tests for bot.market — OHLCV fetching, ticker, orderbook, indicators, cache, and summary.
All exchange calls are mocked (no real API calls).
pandas_ta is mocked for indicator tests (not available on all dev environments).
"""

import time
from unittest.mock import AsyncMock, patch, MagicMock

import pandas as pd
import pytest

from bot import market


# ── Fixtures ─────────────────────────────────────────────────────────

def _make_ohlcv(count: int = 200) -> list[list]:
    """Generate realistic OHLCV candles for testing."""
    base_time = 1700000000000  # ms
    base_price = 50000.0
    candles = []
    for i in range(count):
        ts = base_time + i * 3600000  # 1h intervals
        o = base_price + i * 10
        h = o + 200
        l = o - 100
        c = o + 50
        v = 1000.0 + i
        candles.append([ts, o, h, l, c, v])
    return candles


SAMPLE_OHLCV = _make_ohlcv(200)

SAMPLE_TICKER_RAW = {
    "last": 51000.0,
    "quoteVolume": 5_000_000_000.0,
    "percentage": 2.5,
    "bid": 50999.0,
    "ask": 51001.0,
    "high": 52000.0,
    "low": 49000.0,
}

SAMPLE_ORDERBOOK_RAW = {
    "bids": [[50999.0, 1.5], [50998.0, 2.0], [50997.0, 0.8]],
    "asks": [[51001.0, 1.2], [51002.0, 3.0], [51003.0, 0.5]],
}

SAMPLE_INDICATORS = {
    "rsi": 55.42,
    "ema20": 51800.0,
    "ema50": 51500.0,
    "ema200": 50800.0,
    "macd": {"macd": 120.5, "signal": 95.3, "histogram": 25.2},
    "bollinger": {
        "lower": 50200.0, "mid": 51000.0, "upper": 51800.0,
        "bandwidth": 0.0314, "pct_b": 0.75,
    },
    "atr": 350.0,
}


@pytest.fixture(autouse=True)
def _reset_module():
    """Reset module-level state before each test."""
    market._exchange = None
    market._cache.clear()
    yield
    # Cleanup: don't leave a real exchange open
    market._exchange = None
    market._cache.clear()


# ── get_ohlcv ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ohlcv_returns_list_of_candles():
    """get_ohlcv returns list of [ts, o, h, l, c, v] lists."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_ohlcv("BTC/USDT", "1h", 200)

    assert isinstance(result, list)
    assert len(result) == 200
    assert len(result[0]) == 6  # [timestamp, open, high, low, close, volume]


@pytest.mark.asyncio
async def test_get_ohlcv_candle_structure():
    """Each candle has correct field types."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_ohlcv("BTC/USDT", "1h", 200)

    candle = result[0]
    assert isinstance(candle[0], (int, float))  # timestamp
    for i in range(1, 6):
        assert isinstance(candle[i], (int, float))  # OHLCV values


@pytest.mark.asyncio
async def test_get_ohlcv_cache_hit():
    """Second call within TTL returns cached data without calling exchange."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result1 = await market.get_ohlcv("BTC/USDT", "1h", 200)
        result2 = await market.get_ohlcv("BTC/USDT", "1h", 200)

    assert result1 is result2  # same object from cache
    mock_exchange.fetch_ohlcv.assert_called_once()  # only one API call


@pytest.mark.asyncio
async def test_get_ohlcv_different_pairs_not_cached():
    """Different pairs get separate cache entries."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        await market.get_ohlcv("BTC/USDT", "1h", 200)
        await market.get_ohlcv("ETH/USDT", "1h", 200)

    assert mock_exchange.fetch_ohlcv.call_count == 2


@pytest.mark.asyncio
async def test_get_ohlcv_different_timeframes_not_cached():
    """Different timeframes for the same pair get separate cache entries."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        await market.get_ohlcv("BTC/USDT", "1h", 200)
        await market.get_ohlcv("BTC/USDT", "4h", 200)

    assert mock_exchange.fetch_ohlcv.call_count == 2


# ── get_ticker ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ticker_returns_expected_keys():
    """get_ticker returns dict with required fields."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_ticker("BTC/USDT")

    expected_keys = {"symbol", "last", "volume_24h", "change_pct_24h", "bid", "ask", "high_24h", "low_24h"}
    assert set(result.keys()) == expected_keys
    assert result["symbol"] == "BTC/USDT"
    assert result["last"] == 51000.0
    assert result["change_pct_24h"] == 2.5


@pytest.mark.asyncio
async def test_get_ticker_cache_hit():
    """Ticker is cached on second call."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result1 = await market.get_ticker("BTC/USDT")
        result2 = await market.get_ticker("BTC/USDT")

    assert result1 is result2
    mock_exchange.fetch_ticker.assert_called_once()


@pytest.mark.asyncio
async def test_get_ticker_volume_and_prices():
    """Ticker contains volume and price range info."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_ticker("BTC/USDT")

    assert result["volume_24h"] == 5_000_000_000.0
    assert result["high_24h"] == 52000.0
    assert result["low_24h"] == 49000.0
    assert result["bid"] == 50999.0
    assert result["ask"] == 51001.0


# ── get_orderbook ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_orderbook_returns_expected_keys():
    """get_orderbook returns dict with spread info."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_order_book = AsyncMock(return_value=SAMPLE_ORDERBOOK_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_orderbook("BTC/USDT", depth=3)

    expected_keys = {"symbol", "bids", "asks", "spread", "spread_pct", "mid_price"}
    assert set(result.keys()) == expected_keys
    assert result["symbol"] == "BTC/USDT"
    assert result["spread"] == 2.0  # 51001 - 50999
    assert result["mid_price"] == 51000.0
    assert len(result["bids"]) == 3
    assert len(result["asks"]) == 3


@pytest.mark.asyncio
async def test_get_orderbook_spread_percent():
    """Spread percent should be calculated correctly."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_order_book = AsyncMock(return_value=SAMPLE_ORDERBOOK_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_orderbook("BTC/USDT", depth=3)

    # spread=2.0, mid=51000, pct = 2/51000*100 = 0.003921...
    assert result["spread_pct"] == round(2.0 / 51000.0 * 100, 4)


# ── get_indicators (with mocked pandas_ta) ───────────────────────────

@pytest.mark.asyncio
async def test_get_indicators_returns_all_keys():
    """get_indicators returns dict with rsi, ema20/50/200, macd, bollinger, atr."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_indicators("BTC/USDT", "1h")

    expected_keys = {"rsi", "ema20", "ema50", "ema200", "macd", "bollinger", "atr"}
    assert set(result.keys()) == expected_keys


@pytest.mark.asyncio
async def test_get_indicators_rsi_in_range():
    """RSI should be between 0 and 100."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_indicators("BTC/USDT", "1h")

    assert result["rsi"] is not None
    assert 0 <= result["rsi"] <= 100


@pytest.mark.asyncio
async def test_get_indicators_emas_are_numeric():
    """EMA values should be numeric floats."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_indicators("BTC/USDT", "1h")

    assert isinstance(result["ema20"], float)
    assert isinstance(result["ema50"], float)
    assert isinstance(result["ema200"], float)


@pytest.mark.asyncio
async def test_get_indicators_macd_structure():
    """MACD should have macd, signal, histogram keys."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_indicators("BTC/USDT", "1h")

    macd = result["macd"]
    assert macd is not None
    assert "macd" in macd
    assert "signal" in macd
    assert "histogram" in macd
    assert isinstance(macd["macd"], float)


@pytest.mark.asyncio
async def test_get_indicators_bollinger_structure():
    """Bollinger bands should have lower, mid, upper."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_indicators("BTC/USDT", "1h")

    bb = result["bollinger"]
    assert bb is not None
    assert "lower" in bb
    assert "mid" in bb
    assert "upper" in bb
    assert bb["lower"] < bb["mid"] < bb["upper"]


@pytest.mark.asyncio
async def test_get_indicators_atr_positive():
    """ATR should be a positive number."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_indicators("BTC/USDT", "1h")

    assert result["atr"] is not None
    assert result["atr"] > 0


@pytest.mark.asyncio
async def test_get_indicators_cached():
    """Indicators should be cached on second call."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS) as mock_compute:
        result1 = await market.get_indicators("BTC/USDT", "1h")
        result2 = await market.get_indicators("BTC/USDT", "1h")

    assert result1 is result2
    # _compute_indicators called only once, second call uses cache
    mock_compute.assert_called_once()


# ── _compute_indicators (unit test with mocked pandas_ta) ────────────

def test_compute_indicators_calls_ta_functions():
    """_compute_indicators should call pandas_ta functions and return correct keys."""
    # Create a mock pandas_ta module
    mock_ta = MagicMock()

    # Mock each indicator function to return a pandas Series
    mock_ta.rsi.return_value = pd.Series([55.42])
    mock_ta.ema.side_effect = lambda close, length: pd.Series([51000.0 + length])
    mock_ta.macd.return_value = pd.DataFrame(
        {"MACD_12_26_9": [120.5], "MACDs_12_26_9": [95.3], "MACDh_12_26_9": [25.2]}
    )
    mock_ta.bbands.return_value = pd.DataFrame({
        "BBL_20_2.0": [50200.0], "BBM_20_2.0": [51000.0], "BBU_20_2.0": [51800.0],
        "BBB_20_2.0": [0.0314], "BBP_20_2.0": [0.75],
    })
    mock_ta.atr.return_value = pd.Series([350.0])

    with patch.dict("sys.modules", {"pandas_ta": mock_ta}):
        result = market._compute_indicators(SAMPLE_OHLCV)

    assert "rsi" in result
    assert "ema20" in result
    assert "ema50" in result
    assert "ema200" in result
    assert "macd" in result
    assert "bollinger" in result
    assert "atr" in result

    # Verify indicator functions were called
    mock_ta.rsi.assert_called_once()
    assert mock_ta.ema.call_count == 3  # 20, 50, 200
    mock_ta.macd.assert_called_once()
    mock_ta.bbands.assert_called_once()
    mock_ta.atr.assert_called_once()


# ── get_market_summary ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_market_summary_contains_pair_name():
    """Summary text should contain the pair name."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_market_summary(["BTC/USDT"])

    assert isinstance(result, str)
    assert "BTC/USDT" in result
    assert "Market Data" in result
    assert "Price:" in result
    assert "RSI" in result


@pytest.mark.asyncio
async def test_get_market_summary_multiple_pairs():
    """Summary should include all requested pairs."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_market_summary(["BTC/USDT", "ETH/USDT"])

    assert "BTC/USDT" in result
    assert "ETH/USDT" in result


@pytest.mark.asyncio
async def test_get_market_summary_handles_error_gracefully():
    """Summary should show error text if a pair fails, not crash."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(side_effect=Exception("API error"))
    mock_exchange.fetch_ticker = AsyncMock(side_effect=Exception("API error"))

    with patch.object(market, "_get_exchange", return_value=mock_exchange):
        result = await market.get_market_summary(["BTC/USDT"])

    assert "Error" in result
    assert "BTC/USDT" in result


@pytest.mark.asyncio
async def test_get_market_summary_uses_default_pairs():
    """Summary should use TRADING_PAIRS from config when no pairs specified."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_market_summary()

    # Default pairs: BTC/USDT, ETH/USDT, SOL/USDT
    assert "BTC/USDT" in result
    assert "ETH/USDT" in result
    assert "SOL/USDT" in result


@pytest.mark.asyncio
async def test_get_market_summary_includes_indicators():
    """Summary should include EMA, MACD, Bollinger, ATR values."""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=SAMPLE_OHLCV)
    mock_exchange.fetch_ticker = AsyncMock(return_value=SAMPLE_TICKER_RAW)

    with patch.object(market, "_get_exchange", return_value=mock_exchange), \
         patch.object(market, "_compute_indicators", return_value=SAMPLE_INDICATORS):
        result = await market.get_market_summary(["BTC/USDT"])

    assert "EMA:" in result
    assert "MACD:" in result
    assert "Bollinger" in result
    assert "ATR" in result


# ── Cache TTL ────────────────────────────────────────────────────────

def test_cache_expires_after_ttl():
    """Cache entry should expire after TTL."""
    market._cache_set("test_key", "test_value", 0.01)  # 10ms TTL
    assert market._cache_get("test_key") == "test_value"

    time.sleep(0.02)  # wait for expiry
    assert market._cache_get("test_key") is None


def test_cache_clear():
    """clear_cache removes all entries."""
    market._cache_set("key1", "val1", 60)
    market._cache_set("key2", "val2", 60)
    assert len(market._cache) == 2

    market.clear_cache()
    assert len(market._cache) == 0


def test_cache_key_generation():
    """Cache keys should be deterministic."""
    k1 = market._cache_key("ohlcv", "BTC/USDT", "1h", "100")
    k2 = market._cache_key("ohlcv", "BTC/USDT", "1h", "100")
    k3 = market._cache_key("ohlcv", "ETH/USDT", "1h", "100")
    assert k1 == k2
    assert k1 != k3


def test_cache_get_returns_none_for_missing():
    """Cache get on missing key returns None."""
    assert market._cache_get("nonexistent") is None


# ── Exchange singleton ───────────────────────────────────────────────

def test_get_exchange_creates_singleton():
    """_get_exchange should return the same instance on repeated calls."""
    with patch("bot.market.ccxt_async") as mock_ccxt:
        mock_instance = MagicMock()
        mock_ccxt.binance.return_value = mock_instance

        ex1 = market._get_exchange()
        ex2 = market._get_exchange()

    assert ex1 is ex2
    mock_ccxt.binance.assert_called_once()


def test_get_exchange_enables_rate_limit():
    """Exchange should be created with enableRateLimit=True."""
    with patch("bot.market.ccxt_async") as mock_ccxt:
        mock_ccxt.binance.return_value = MagicMock()
        market._get_exchange()

    mock_ccxt.binance.assert_called_once_with({"enableRateLimit": True})


@pytest.mark.asyncio
async def test_close_resets_exchange():
    """close() should set _exchange to None."""
    mock_exchange = AsyncMock()
    market._exchange = mock_exchange

    await market.close()

    assert market._exchange is None
    mock_exchange.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_when_no_exchange():
    """close() should be safe when no exchange exists."""
    market._exchange = None
    await market.close()  # should not raise
    assert market._exchange is None
