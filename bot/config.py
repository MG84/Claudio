"""
Centralized configuration — all constants, env vars, and defaults.
"""

import os
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


# ── Runtime config (hot-reloadable, no rebuild needed) ────────────────
import json as _json

RUNTIME_CONFIG_PATH = Path("/home/assistant/memory/runtime_config.json")


def get_runtime(key: str, default: str = "") -> str:
    """Read a value from runtime_config.json, falling back to env, then default."""
    try:
        if RUNTIME_CONFIG_PATH.exists():
            data = _json.loads(RUNTIME_CONFIG_PATH.read_text())
            if key in data:
                return str(data[key])
    except Exception:
        pass
    return os.getenv(key, default)


# ── Paths ─────────────────────────────────────────────────────────────
PROJECTS_BASE = Path("/home/assistant/projects")
GENERAL_WORKSPACE = Path("/home/assistant/projects/Claudio")
MEMORY_DIR = Path("/home/assistant/memory")
UPLOADS_DIR = Path("/home/assistant/uploads")
TOPIC_MAP_FILE = MEMORY_DIR / "topic_map.json"

# ── User ──────────────────────────────────────────────────────────────
USER_NAME = _env("USER_NAME", "User")

# ── Claude Models ─────────────────────────────────────────────────────
MODEL_OPUS = "claude-opus-4-6"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

DEFAULT_MODEL = _env("CLAUDE_MODEL", MODEL_SONNET)
DEFAULT_EFFORT = _env("CLAUDE_EFFORT", "high")
DEFAULT_MAX_TURNS = _env_int("CLAUDE_MAX_TURNS", 25)
MIN_TURNS = 1
MAX_TURNS_LIMIT = 100

# ── Claude Agent SDK ──────────────────────────────────────────────────
ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Bash",
    "Glob", "Grep", "WebSearch", "WebFetch",
]
PERMISSION_MODE = "bypassPermissions"
GENERAL_SESSION_KEY = "__general__"
NO_OUTPUT_MESSAGE = "Ho completato il task ma non ho generato output testuale."

# ── Voice — STT (faster-whisper) ──────────────────────────────────────
WHISPER_MODEL = "large-v3-turbo"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_LANGUAGE = "it"
WHISPER_BEAM_SIZE = 5
STT_SAMPLE_RATE = 16000

# ── Voice — TTS (Qwen3-TTS / Edge TTS fallback) ──────────────────────
TTS_HOST = _env("TTS_HOST", "http://host.docker.internal:8880")
TTS_VOICE = _env("TTS_VOICE", "ryan")
TTS_LANGUAGE = "Italian"
TTS_MODEL_NAME = "qwen3-tts"
TTS_TIMEOUT_SECONDS = 120
TTS_SAMPLE_RATE = 24000
OGG_BITRATE = "64k"
EDGE_TTS_VOICE = "it-IT-DiegoNeural"

# ── Telegram ──────────────────────────────────────────────────────────
TELEGRAM_MAX_MESSAGE_LENGTH = 4000
VOICE_RESPONSE_MAX_LENGTH = 3000
TYPING_INTERVAL_SECONDS = 4

# ── Send queue (Claude Code → Telegram) ───────────────────────────────
SEND_VOICE_DIR = UPLOADS_DIR / "send_voice"
SEND_FILE_DIR = UPLOADS_DIR / "send_file"

# ── Monitor (WebSocket + SQLite) ───────────────────────────────────────
DASHBOARD_PORT = _env_int("DASHBOARD_PORT", 3333)
DASHBOARD_PASSWORD = _env("DASHBOARD_PASSWORD", "")
AUTH_COOKIE_NAME = "claudio_session"
AUTH_COOKIE_MAX_AGE = 86400 * 30  # 30 giorni
DASHBOARD_STATIC_DIR = Path("/home/assistant/dashboard")
WS_PATH = "/ws"
MONITOR_DB_PATH = MEMORY_DIR / "monitor.db"
METRICS_INTERVAL_SECONDS = 5
MONITOR_RETENTION_DAYS = 7
MONITOR_EVENT_HISTORY_LIMIT = 100
HISTORY_ON_CONNECT_LIMIT = 100

# ── Memory (Mem0 + Ollama + Qdrant) ─────────────────────────────────
OLLAMA_HOST = _env("OLLAMA_HOST", "http://ollama:11434")
QDRANT_HOST = _env("QDRANT_HOST", "qdrant")
QDRANT_PORT = _env_int("QDRANT_PORT", 6333)
MEM0_COLLECTION = "claudio_memories"
MEM0_EMBEDDING_MODEL = "nomic-embed-text:latest"
MEM0_EMBEDDING_DIMS = 768
MEM0_LLM_MODEL = "llama3.1:8b"
MEM0_LLM_TEMPERATURE = 0
MEM0_LLM_MAX_TOKENS = 2000
MEM0_ENABLED = _env_bool("MEM0_ENABLED", default=True)
MEM0_SEARCH_LIMIT = 10

# ── Git operations (Changes tab) ─────────────────────────────────────
GIT_DIFF_CONTEXT_LINES = 3
GIT_MAX_DIFF_SIZE = 500_000  # bytes — skip file se diff troppo grande
CHANGES_EVENT = "changes"
GIT_ACTIONS = frozenset({
    "git_stage", "git_unstage", "git_revert",
    "git_commit", "git_revert_all", "git_diff",
    "git_refresh_all",
})

# ── Market data ─────────────────────────────────────────────────────
TRADING_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
MARKET_CACHE_SECONDS = 60
MARKET_TICKER_CACHE_SECONDS = 30
MARKET_OHLCV_LIMIT = 400

# ── Kronos (crypto predictions) ──────────────────────────────────────
KRONOS_ENABLED = _env_bool("KRONOS_ENABLED", default=True)
KRONOS_MODEL_NAME = "NeoQuasar/Kronos-small"
KRONOS_TOKENIZER_NAME = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_MODEL_DIR = Path("/home/assistant/kronos_model")
KRONOS_MAX_CONTEXT = 512
KRONOS_EXCHANGE = "binance"
KRONOS_SYMBOL = "BTC/USDT"
KRONOS_TIMEFRAME = "1h"
KRONOS_LOOKBACK = 400
KRONOS_PRED_LEN = 12            # 12 candele = 12h avanti con timeframe 1h
KRONOS_TEMPERATURE = 0.6
KRONOS_TOP_P = 0.9
KRONOS_SAMPLE_COUNT = 5
KRONOS_INTERVAL_SECONDS = 3600  # ogni ora
KRONOS_DB_PATH = MEMORY_DIR / "kronos.db"

# ── Trading safety limits ────────────────────────────────────────────
TRADING_ENABLED = _env_bool("TRADING_ENABLED", default=True)
TRADING_MODE = _env("TRADING_MODE", "paper")
MAX_POSITION_PCT = 0.20          # max 20% of portfolio per position
MAX_OPEN_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 0.05        # 5% → stop trading for the day
MAX_DRAWDOWN_PCT = 0.15          # 15% → kill switch
STOP_LOSS_REQUIRED = True
MAX_TRADES_PER_DAY = 10
TRADES_DB_PATH = MEMORY_DIR / "trades.db"

# ── Chronos-Bolt (univariate close-price forecasting) ────────────────
CHRONOS_ENABLED = _env_bool("CHRONOS_ENABLED", default=True)
CHRONOS_MODEL_NAME = "amazon/chronos-bolt-small"
CHRONOS_PRED_LEN = 12
CHRONOS_LOOKBACK = 400
CHRONOS_INTERVAL_SECONDS = 3600
CHRONOS_DB_PATH = MEMORY_DIR / "kronos.db"  # shared DB, separate table

# ── Cleanup ───────────────────────────────────────────────────────────
UPLOADS_MAX_AGE_HOURS = 24
CLEANUP_INTERVAL_SECONDS = 3600

# ── Effort labels ─────────────────────────────────────────────────────
EFFORT_LEVELS = {"low", "medium", "high"}
EFFORT_LABELS = {
    "low": "Veloce, meno ragionamento",
    "medium": "Bilanciato",
    "high": "Approfondito",
}
