"""
Kronos Advisor — BTC/USDT candlestick predictions via Kronos-small.
Fetches OHLCV from Binance, runs inference, stores in SQLite, verifies past predictions.
"""

import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone

import ccxt.async_support as ccxt_async
import pandas as pd

from bot.config import (
    KRONOS_ENABLED, KRONOS_MODEL_NAME, KRONOS_TOKENIZER_NAME,
    KRONOS_MODEL_DIR, KRONOS_MAX_CONTEXT, KRONOS_SYMBOL, KRONOS_TIMEFRAME,
    KRONOS_LOOKBACK, KRONOS_PRED_LEN, KRONOS_TEMPERATURE, KRONOS_TOP_P,
    KRONOS_SAMPLE_COUNT, KRONOS_INTERVAL_SECONDS, KRONOS_DB_PATH, MEMORY_DIR,
    TRADING_PAIRS,
)

log = logging.getLogger("claudio.kronos")

_predictor = None
_db: sqlite3.Connection | None = None

# Display/verification constants
_DISPLAY_HORIZONS = [1, 6, 12]          # hours shown in Telegram message
_HIT_RATE_HORIZONS = [1, 6, 12]         # hours for per-horizon hit rate stats
_DIRECTION_THRESHOLD_PCT = 0.1          # % change to consider non-flat
_VERIFY_FETCH_BUFFER = 5               # extra candles when fetching actuals


# ── SQLite ────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(KRONOS_DB_PATH))
        _db.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                current_price REAL NOT NULL,
                predictions TEXT NOT NULL,
                verified INTEGER DEFAULT 0,
                actual_prices TEXT,
                direction_correct INTEGER,
                mae REAL
            )
        """)
        _db.execute("CREATE INDEX IF NOT EXISTS idx_pred_verified ON predictions(verified)")
        _db.execute("CREATE INDEX IF NOT EXISTS idx_pred_created ON predictions(created_at DESC)")
        _db.commit()
        log.info(f"Kronos DB initialized at {KRONOS_DB_PATH}")
    return _db


# ── Model loading ─────────────────────────────────────────────────────

def _load_model():
    """Load Kronos-small model (CPU). Blocks — call via asyncio.to_thread."""
    global _predictor
    if _predictor is not None:
        return

    model_dir = str(KRONOS_MODEL_DIR)
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    from model import Kronos, KronosTokenizer, KronosPredictor

    tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER_NAME)
    model = Kronos.from_pretrained(KRONOS_MODEL_NAME)
    _predictor = KronosPredictor(model, tokenizer, max_context=KRONOS_MAX_CONTEXT)
    log.info("Kronos model loaded (CPU)")


def is_ready() -> bool:
    """True if the Kronos model has been loaded and is available for inference."""
    return _predictor is not None


async def init():
    """Async init — loads model in a thread to avoid blocking."""
    if not KRONOS_ENABLED:
        log.info("Kronos disabled (KRONOS_ENABLED=false)")
        return
    try:
        await asyncio.to_thread(_load_model)
    except Exception as e:
        log.error(f"Failed to load Kronos model: {e}")


# ── Data fetching ─────────────────────────────────────────────────────

async def fetch_ohlcv(symbol: str = KRONOS_SYMBOL,
                      timeframe: str = KRONOS_TIMEFRAME,
                      limit: int = KRONOS_LOOKBACK,
                      since: int | None = None) -> list[list]:
    """Fetch OHLCV candles from Binance (public, no API key).
    Args:
        since: start timestamp in milliseconds (optional).
    """
    exchange = ccxt_async.binance()
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        return ohlcv
    finally:
        await exchange.close()


# ── Inference ─────────────────────────────────────────────────────────

def _run_inference(ohlcv: list[list], timeframe: str = KRONOS_TIMEFRAME) -> list[dict]:
    """Run Kronos prediction on OHLCV data. Blocks — call via asyncio.to_thread."""
    if _predictor is None:
        raise RuntimeError("Kronos model not loaded")

    # Build DataFrame from OHLCV [timestamp_ms, open, high, low, close, volume]
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

    if len(df) > KRONOS_MAX_CONTEXT:
        df = df.iloc[-KRONOS_MAX_CONTEXT:]

    # Historical timestamps (Series, not DatetimeIndex — Kronos uses .dt accessor)
    x_timestamp = pd.to_datetime(df["timestamp"], unit="ms", utc=True).reset_index(drop=True)

    # Future timestamps
    tf_ms = _timeframe_to_ms(timeframe)
    last_ts = int(df["timestamp"].iloc[-1])
    y_timestamps_ms = [last_ts + (i + 1) * tf_ms for i in range(KRONOS_PRED_LEN)]
    y_timestamp = pd.Series(pd.to_datetime(y_timestamps_ms, unit="ms", utc=True))

    # Input DataFrame (OHLC columns expected by Kronos)
    x_df = df[["open", "high", "low", "close"]].copy()

    pred_df = _predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=KRONOS_PRED_LEN,
        T=KRONOS_TEMPERATURE,
        top_p=KRONOS_TOP_P,
        sample_count=KRONOS_SAMPLE_COUNT,
    )

    # Build predictions list from output DataFrame
    predictions = []
    for i in range(len(pred_df)):
        row = pred_df.iloc[i]
        ts_ms = y_timestamps_ms[i]
        ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        predictions.append({
            "timestamp": ts_iso,
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "offset_hours": i + 1,
        })

    return predictions


def _timeframe_to_ms(tf: str) -> int:
    """Convert timeframe string (e.g. '1h', '15m') to milliseconds."""
    unit = tf[-1]
    val = int(tf[:-1])
    multipliers = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return val * multipliers.get(unit, 3_600_000)


# ── Public prediction API ─────────────────────────────────────────────

async def predict(symbol: str = KRONOS_SYMBOL,
                  timeframe: str = KRONOS_TIMEFRAME) -> dict:
    """Fetch data, run inference, store in DB, return result dict."""
    ohlcv = await fetch_ohlcv(symbol, timeframe)
    current_price = ohlcv[-1][4]  # last close

    predictions = await asyncio.to_thread(_run_inference, ohlcv, timeframe)

    created_at = datetime.now(timezone.utc).isoformat()
    db = _get_db()
    db.execute(
        "INSERT INTO predictions (created_at, symbol, timeframe, current_price, predictions) "
        "VALUES (?, ?, ?, ?, ?)",
        (created_at, symbol, timeframe, current_price, json.dumps(predictions)),
    )
    db.commit()

    return {
        "created_at": created_at,
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": current_price,
        "predictions": predictions,
    }


# ── Quick-access API ──────────────────────────────────────────────────

def get_latest_prediction(pair: str | None = None) -> dict | None:
    """Return most recent prediction from DB, optionally filtered by pair.
    Does NOT run inference — just reads what's already stored."""
    db = _get_db()
    if pair:
        row = db.execute(
            "SELECT created_at, symbol, timeframe, current_price, predictions "
            "FROM predictions WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
            (pair,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT created_at, symbol, timeframe, current_price, predictions "
            "FROM predictions ORDER BY created_at DESC LIMIT 1",
        ).fetchone()

    if not row:
        return None

    return {
        "created_at": row[0],
        "symbol": row[1],
        "timeframe": row[2],
        "current_price": row[3],
        "predictions": json.loads(row[4]),
    }


async def predict_pair(pair: str, timeframe: str = KRONOS_TIMEFRAME) -> dict:
    """Run Kronos prediction for any pair/timeframe. Alias for predict()."""
    return await predict(symbol=pair, timeframe=timeframe)


def get_prediction_confidence(pair: str | None = None) -> dict:
    """Confidence score based on historical direction accuracy.

    Returns dict with confidence (0-1), based_on (sample count),
    direction_accuracy (percentage).

    With few samples confidence is pulled toward 0.5 (uncertain).
    Full weight at 20+ verified predictions.
    """
    db = _get_db()

    where = "WHERE verified = 1"
    params: list = []
    if pair:
        where += " AND symbol = ?"
        params.append(pair)

    total = db.execute(
        f"SELECT COUNT(*) FROM predictions {where}", params
    ).fetchone()[0]

    if total == 0:
        return {"confidence": 0.5, "based_on": 0, "direction_accuracy": 0.0}

    correct = db.execute(
        f"SELECT COUNT(*) FROM predictions {where} AND direction_correct = 1",
        params,
    ).fetchone()[0]

    direction_accuracy = correct / total

    # Scale confidence by sample size — pull toward 0.5 with few samples
    sample_weight = min(total / 20, 1.0)
    confidence = 0.5 + (direction_accuracy - 0.5) * sample_weight

    return {
        "confidence": round(confidence, 3),
        "based_on": total,
        "direction_accuracy": round(direction_accuracy * 100, 1),
    }


# ── Verification ──────────────────────────────────────────────────────

async def verify_predictions() -> int:
    """Verify past predictions against actual prices. Returns count of newly verified."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, symbol, timeframe, current_price, predictions FROM predictions "
        "WHERE verified = 0"
    ).fetchall()

    verified_count = 0
    now = datetime.now(timezone.utc)

    for row_id, symbol, timeframe, current_price, preds_json in rows:
        preds = json.loads(preds_json)

        # Check if all predicted timestamps have passed
        last_pred_ts = datetime.fromisoformat(preds[-1]["timestamp"])
        if last_pred_ts > now:
            continue

        # Fetch actual candles starting from the first predicted timestamp
        first_pred_ts = datetime.fromisoformat(preds[0]["timestamp"])
        since_ms = int(first_pred_ts.timestamp() * 1000)
        try:
            ohlcv = await fetch_ohlcv(
                symbol, timeframe,
                limit=KRONOS_PRED_LEN + _VERIFY_FETCH_BUFFER,
                since=since_ms,
            )
        except Exception as e:
            log.warning(f"Failed to fetch actuals for verification: {e}")
            continue

        # Build timestamp->candle map from actual data
        actual_map = {}
        for c in ohlcv:
            ts_iso = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).isoformat()
            actual_map[ts_iso] = {
                "open": c[1], "high": c[2], "low": c[3], "close": c[4],
            }

        actual_prices = []
        errors = []
        for p in preds:
            actual = actual_map.get(p["timestamp"])
            if actual is not None:
                actual_prices.append({"timestamp": p["timestamp"], **actual})
                errors.append(abs(p["close"] - actual["close"]))

        if not actual_prices:
            continue

        # Direction: compare last predicted close vs current_price
        pred_direction = preds[-1]["close"] > current_price
        actual_direction = actual_prices[-1]["close"] > current_price
        direction_correct = 1 if pred_direction == actual_direction else 0

        mae = round(sum(errors) / len(errors), 2) if errors else None

        db.execute(
            "UPDATE predictions SET verified = 1, actual_prices = ?, "
            "direction_correct = ?, mae = ? WHERE id = ?",
            (json.dumps(actual_prices), direction_correct, mae, row_id),
        )
        verified_count += 1

    if verified_count:
        db.commit()
        log.info(f"Verified {verified_count} predictions")

    return verified_count


# ── Stats ─────────────────────────────────────────────────────────────

def get_accuracy_stats() -> dict:
    """Aggregate accuracy statistics from verified predictions."""
    db = _get_db()

    total = db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    verified = db.execute("SELECT COUNT(*) FROM predictions WHERE verified = 1").fetchone()[0]

    if verified == 0:
        return {"total": total, "verified": 0}

    direction_correct = db.execute(
        "SELECT COUNT(*) FROM predictions WHERE verified = 1 AND direction_correct = 1"
    ).fetchone()[0]

    avg_mae = db.execute(
        "SELECT AVG(mae) FROM predictions WHERE verified = 1 AND mae IS NOT NULL"
    ).fetchone()[0]

    hit_rates = {}
    for offset in _HIT_RATE_HORIZONS:
        hit_rates[f"hit_rate_{offset}h"] = _compute_hit_rate(db, offset)

    return {
        "total": total,
        "verified": verified,
        "direction_correct": direction_correct,
        "direction_accuracy": round(direction_correct / verified * 100, 1) if verified else 0,
        "avg_mae": round(avg_mae, 2) if avg_mae else None,
        **hit_rates,
    }


def _compute_hit_rate(db: sqlite3.Connection, offset_hours: int) -> float | None:
    """Compute direction hit rate for a specific forecast horizon."""
    rows = db.execute(
        "SELECT current_price, predictions, actual_prices FROM predictions "
        "WHERE verified = 1 AND actual_prices IS NOT NULL"
    ).fetchall()

    correct = 0
    total = 0
    idx = offset_hours - 1  # 0-based

    for current_price, preds_json, actuals_json in rows:
        preds = json.loads(preds_json)
        actuals = json.loads(actuals_json)

        if idx >= len(preds) or idx >= len(actuals):
            continue

        pred_up = preds[idx]["close"] > current_price
        actual_up = actuals[idx]["close"] > current_price
        if pred_up == actual_up:
            correct += 1
        total += 1

    return round(correct / total * 100, 1) if total else None


# ── Formatting ────────────────────────────────────────────────────────

def format_prediction(result: dict) -> str:
    """Format prediction result for Telegram (key horizons only)."""
    current = result["current_price"]
    preds = result["predictions"]

    lines = [
        f"\U0001f4ca Kronos \u2014 {result['symbol']} ({result['timeframe']})",
        f"Prezzo attuale: ${current:,.2f}",
        "",
        "Previsione:",
    ]

    for p in preds:
        if p["offset_hours"] not in _DISPLAY_HORIZONS:
            continue
        offset = p["offset_hours"]
        close = p["close"]
        pct = (close - current) / current * 100
        sign = "+" if pct >= 0 else ""
        lines.append(f"  +{offset}h:  ${close:,.0f} ({sign}{pct:.2f}%)")

    # Overall direction based on last prediction
    final_pct = (preds[-1]["close"] - current) / current * 100
    if final_pct > _DIRECTION_THRESHOLD_PCT:
        direction = "\u2197\ufe0f UP"
    elif final_pct < -_DIRECTION_THRESHOLD_PCT:
        direction = "\u2198\ufe0f DOWN"
    else:
        direction = "\u27a1\ufe0f FLAT"

    lines.append(f"\nDirezione: {direction}")
    return "\n".join(lines)


def format_accuracy(stats: dict) -> str:
    """Format accuracy stats for Telegram."""
    if stats["verified"] == 0:
        return (
            f"\U0001f4c8 Kronos Accuracy \u2014 {KRONOS_SYMBOL}\n"
            f"Previsioni totali: {stats['total']}\n"
            f"Verificate: 0\n"
            "Serve almeno una previsione verificata per le statistiche."
        )

    lines = [
        f"\U0001f4c8 Kronos Accuracy \u2014 {KRONOS_SYMBOL}",
        f"Previsioni totali: {stats['total']}",
        f"Verificate: {stats['verified']}",
        f"Direzione corretta: {stats['direction_accuracy']}%",
    ]

    if stats.get("avg_mae") is not None:
        lines.append(f"Errore medio (MAE): ${stats['avg_mae']:,.2f}")

    for hours in _HIT_RATE_HORIZONS:
        key = f"hit_rate_{hours}h"
        rate = stats.get(key)
        if rate is not None:
            lines.append(f"Hit rate {hours}h: {rate}%")

    return "\n".join(lines)


# ── Background loop ──────────────────────────────────────────────────

async def kronos_loop() -> None:
    """Periodic task: predict every hour, verify old predictions, emit dashboard event.
    Loops over TRADING_PAIRS if configured, otherwise uses KRONOS_SYMBOL."""
    if not KRONOS_ENABLED:
        return

    from bot.monitor import emit

    # Wait for model to be ready
    while _predictor is None:
        await asyncio.sleep(5)

    pairs = TRADING_PAIRS if TRADING_PAIRS else [KRONOS_SYMBOL]
    log.info(f"Kronos loop started — pairs: {pairs}")

    while True:
        for pair in pairs:
            try:
                result = await predict(symbol=pair)
                log.info(
                    f"Kronos prediction: {result['symbol']} current=${result['current_price']:,.2f} "
                    f"pred_12h=${result['predictions'][-1]['close']:,.2f}"
                )

                await emit("kronos_prediction", {
                    "symbol": result["symbol"],
                    "current_price": result["current_price"],
                    "predictions": result["predictions"],
                })

            except Exception as e:
                log.error(f"Kronos loop error ({pair}): {e}")

        try:
            await verify_predictions()
        except Exception as e:
            log.error(f"Kronos verification error: {e}")

        await asyncio.sleep(KRONOS_INTERVAL_SECONDS)
