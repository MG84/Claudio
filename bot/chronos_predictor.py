"""
Chronos-Bolt Predictor — univariate close-price forecasting with uncertainty bands.
Uses amazon/chronos-bolt-small via ChronosPipeline, stores in SQLite, emits dashboard events.
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone

import torch

from bot.config import (
    CHRONOS_ENABLED, CHRONOS_MODEL_NAME, CHRONOS_PRED_LEN,
    CHRONOS_LOOKBACK, CHRONOS_INTERVAL_SECONDS, CHRONOS_DB_PATH,
    MEMORY_DIR, TRADING_PAIRS,
)

log = logging.getLogger("claudio.chronos")

_pipeline = None
_db: sqlite3.Connection | None = None

# Display/verification constants
_DISPLAY_HORIZONS = [1, 6, 12]
_DIRECTION_THRESHOLD_PCT = 0.1


# -- SQLite ----------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(CHRONOS_DB_PATH))
        _db.execute("""
            CREATE TABLE IF NOT EXISTS chronos_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                current_price REAL NOT NULL,
                point_forecast TEXT NOT NULL,
                quantile_forecast TEXT NOT NULL,
                direction TEXT NOT NULL,
                change_pct REAL NOT NULL,
                verified INTEGER DEFAULT 0,
                actual_prices TEXT,
                direction_correct INTEGER,
                mae REAL
            )
        """)
        _db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chronos_verified "
            "ON chronos_predictions(verified)"
        )
        _db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chronos_created "
            "ON chronos_predictions(created_at DESC)"
        )
        _db.commit()
        log.info(f"Chronos DB initialized at {CHRONOS_DB_PATH}")
    return _db


# -- Model loading ---------------------------------------------------------

def _load_model():
    """Load Chronos-Bolt pipeline (CPU). Blocks -- call via asyncio.to_thread."""
    global _pipeline
    if _pipeline is not None:
        return

    from chronos import ChronosPipeline

    _pipeline = ChronosPipeline.from_pretrained(
        CHRONOS_MODEL_NAME,
        device_map="cpu",
        torch_dtype=torch.float32,
    )
    log.info(f"Chronos-Bolt model loaded: {CHRONOS_MODEL_NAME} (CPU)")


def is_ready() -> bool:
    """True if the Chronos-Bolt pipeline has been loaded and is available."""
    return _pipeline is not None


async def init():
    """Async init -- loads model in a thread to avoid blocking."""
    if not CHRONOS_ENABLED:
        log.info("Chronos-Bolt disabled (CHRONOS_ENABLED=false)")
        return
    try:
        await asyncio.to_thread(_load_model)
    except Exception as e:
        log.error(f"Failed to load Chronos-Bolt model: {e}")


# -- Inference -------------------------------------------------------------

def _run_inference(closes: list[float], horizon: int) -> dict:
    """Run Chronos-Bolt prediction on close prices. Blocks -- call via asyncio.to_thread."""
    if _pipeline is None:
        raise RuntimeError("Chronos-Bolt model not loaded")

    context = torch.tensor(closes, dtype=torch.float32)
    # predict returns (forecast, quantile_levels) where forecast shape is
    # (batch, num_quantiles, prediction_length)
    quantile_levels = [0.1, 0.5, 0.9]
    forecast, _ = _pipeline.predict(
        context,
        prediction_length=horizon,
        quantile_levels=quantile_levels,
    )

    # forecast shape: (1, 3, horizon) -- squeeze batch dim
    q10 = forecast[0, 0].tolist()
    q50 = forecast[0, 1].tolist()
    q90 = forecast[0, 2].tolist()

    current = closes[-1]
    final_pred = q50[-1]
    change_pct = (final_pred - current) / current * 100

    if change_pct > _DIRECTION_THRESHOLD_PCT:
        direction = "UP"
    elif change_pct < -_DIRECTION_THRESHOLD_PCT:
        direction = "DOWN"
    else:
        direction = "FLAT"

    return {
        "point_forecast": q50,
        "quantile_forecast": {
            "q10": q10,
            "q50": q50,
            "q90": q90,
        },
        "direction": direction,
        "change_pct": round(change_pct, 4),
    }


# -- Public prediction API -------------------------------------------------

async def predict(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    horizon: int = CHRONOS_PRED_LEN,
) -> dict:
    """Fetch close prices, run inference, store in DB, return result dict."""
    from bot.market import get_ohlcv

    ohlcv = await get_ohlcv(pair=symbol, timeframe=timeframe, limit=CHRONOS_LOOKBACK)
    closes = [candle[4] for candle in ohlcv]  # index 4 = close
    current_price = closes[-1]

    result = await asyncio.to_thread(_run_inference, closes, horizon)

    created_at = datetime.now(timezone.utc).isoformat()
    db = _get_db()
    db.execute(
        "INSERT INTO chronos_predictions "
        "(created_at, symbol, timeframe, current_price, point_forecast, "
        "quantile_forecast, direction, change_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            created_at, symbol, timeframe, current_price,
            json.dumps(result["point_forecast"]),
            json.dumps(result["quantile_forecast"]),
            result["direction"],
            result["change_pct"],
        ),
    )
    db.commit()

    return {
        "created_at": created_at,
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": current_price,
        **result,
    }


# -- Verification ----------------------------------------------------------

async def verify_predictions() -> int:
    """Verify past predictions against actual close prices. Returns count verified."""
    from bot.market import get_ohlcv

    db = _get_db()
    rows = db.execute(
        "SELECT id, symbol, timeframe, current_price, point_forecast, created_at "
        "FROM chronos_predictions WHERE verified = 0"
    ).fetchall()

    verified_count = 0
    now = datetime.now(timezone.utc)

    for row_id, symbol, timeframe, current_price, pf_json, created_at in rows:
        point_forecast = json.loads(pf_json)
        horizon = len(point_forecast)

        # Check if enough time has passed (horizon hours since creation)
        created = datetime.fromisoformat(created_at)
        hours_elapsed = (now - created).total_seconds() / 3600
        if hours_elapsed < horizon:
            continue

        # Fetch actual candles since prediction time
        since_ms = int(created.timestamp() * 1000)
        try:
            ohlcv = await get_ohlcv(pair=symbol, timeframe=timeframe, limit=horizon + 5)
        except Exception as e:
            log.warning(f"Failed to fetch actuals for Chronos verification: {e}")
            continue

        # Extract actual close prices (last `horizon` candles)
        actual_closes = [c[4] for c in ohlcv[-horizon:]]
        if len(actual_closes) < horizon:
            continue

        # MAE
        errors = [abs(p - a) for p, a in zip(point_forecast, actual_closes)]
        mae = round(sum(errors) / len(errors), 2)

        # Direction
        pred_direction = point_forecast[-1] > current_price
        actual_direction = actual_closes[-1] > current_price
        direction_correct = 1 if pred_direction == actual_direction else 0

        db.execute(
            "UPDATE chronos_predictions SET verified = 1, actual_prices = ?, "
            "direction_correct = ?, mae = ? WHERE id = ?",
            (json.dumps(actual_closes), direction_correct, mae, row_id),
        )
        verified_count += 1

    if verified_count:
        db.commit()
        log.info(f"Chronos: verified {verified_count} predictions")

    return verified_count


# -- Formatting ------------------------------------------------------------

def format_prediction(result: dict) -> str:
    """Format prediction result for Telegram with uncertainty bands."""
    current = result["current_price"]
    point = result["point_forecast"]
    q = result["quantile_forecast"]
    direction = result["direction"]
    change = result["change_pct"]

    dir_icon = {
        "UP": "\u2197\ufe0f",
        "DOWN": "\u2198\ufe0f",
        "FLAT": "\u27a1\ufe0f",
    }.get(direction, "")

    lines = [
        f"\U0001f52e Chronos-Bolt \u2014 {result['symbol']} ({result['timeframe']})",
        f"Prezzo attuale: ${current:,.2f}",
        "",
        "Previsione (mediana \u00b1 bande 10%-90%):",
    ]

    for i, h in enumerate(_DISPLAY_HORIZONS):
        if h - 1 >= len(point):
            continue
        idx = h - 1
        p = point[idx]
        lo = q["q10"][idx]
        hi = q["q90"][idx]
        pct = (p - current) / current * 100
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"  +{h}h:  ${p:,.0f} ({sign}{pct:.2f}%)  "
            f"[${lo:,.0f} - ${hi:,.0f}]"
        )

    lines.append(f"\nDirezione: {dir_icon} {direction} ({change:+.2f}%)")
    return "\n".join(lines)


# -- Background loop -------------------------------------------------------

async def chronos_loop() -> None:
    """Periodic task: predict every hour for configured pairs, verify, emit events."""
    if not CHRONOS_ENABLED:
        return

    from bot.monitor import emit

    # Wait for model to be ready
    while _pipeline is None:
        await asyncio.sleep(5)

    log.info("Chronos-Bolt loop started")

    while True:
        for symbol in TRADING_PAIRS:
            try:
                result = await predict(symbol=symbol)
                log.info(
                    f"Chronos-Bolt prediction: {symbol} current=${result['current_price']:,.2f} "
                    f"direction={result['direction']} change={result['change_pct']:+.2f}%"
                )

                await emit("chronos_prediction", {
                    "symbol": result["symbol"],
                    "current_price": result["current_price"],
                    "direction": result["direction"],
                    "change_pct": result["change_pct"],
                    "point_forecast": result["point_forecast"],
                    "quantile_forecast": result["quantile_forecast"],
                })

            except Exception as e:
                log.error(f"Chronos-Bolt loop error for {symbol}: {e}")

        try:
            await verify_predictions()
        except Exception as e:
            log.error(f"Chronos-Bolt verification error: {e}")

        await asyncio.sleep(CHRONOS_INTERVAL_SECONDS)
