"""
Persistent per-chat memory via Mem0 (Ollama + Qdrant, fully local).

All functions are async-safe: Mem0 is synchronous, so blocking calls
are wrapped in asyncio.to_thread().  Every function catches exceptions
and returns safe defaults — memory failures never crash the bot.
"""

import asyncio
import logging

from mem0 import Memory

from bot.config import (
    OLLAMA_HOST,
    QDRANT_HOST,
    QDRANT_PORT,
    MEM0_COLLECTION,
    MEM0_EMBEDDING_MODEL,
    MEM0_EMBEDDING_DIMS,
    MEM0_LLM_MODEL,
    MEM0_LLM_TEMPERATURE,
    MEM0_LLM_MAX_TOKENS,
    MEM0_ENABLED,
    MEM0_SEARCH_LIMIT,
)

log = logging.getLogger("claudio.memory")

_mem: Memory | None = None


def init() -> None:
    """Create the Mem0 Memory instance.  Call once at startup."""
    global _mem

    if not MEM0_ENABLED:
        log.info("Mem0 disabled (MEM0_ENABLED=false)")
        return

    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": MEM0_COLLECTION,
                "host": QDRANT_HOST,
                "port": QDRANT_PORT,
                "embedding_model_dims": MEM0_EMBEDDING_DIMS,
            },
        },
        "llm": {
            "provider": "ollama",
            "config": {
                "model": MEM0_LLM_MODEL,
                "temperature": MEM0_LLM_TEMPERATURE,
                "max_tokens": MEM0_LLM_MAX_TOKENS,
                "ollama_base_url": OLLAMA_HOST,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": MEM0_EMBEDDING_MODEL,
                "ollama_base_url": OLLAMA_HOST,
            },
        },
        "version": "v1.1",
    }

    try:
        _mem = Memory.from_config(config)
        log.info("Mem0 initialized (Qdrant=%s, Ollama=%s)", QDRANT_HOST, OLLAMA_HOST)
    except Exception as e:
        log.warning("Mem0 init failed (will run without memory): %s", e)
        _mem = None


async def search(query: str, chat_id: int) -> list[str]:
    """Return relevant memories for this chat as a list of strings."""
    if not MEM0_ENABLED or _mem is None:
        return []
    try:
        result = await asyncio.to_thread(
            _mem.search, query, user_id=str(chat_id), limit=MEM0_SEARCH_LIMIT,
        )
        return [m for r in result.get("results", []) if (m := r.get("memory", ""))]
    except Exception as e:
        log.warning("Memory search failed for chat %d: %s", chat_id, e)
        return []


async def add(user_msg: str, assistant_msg: str, chat_id: int) -> None:
    """Extract and store facts from a conversation turn (fire-and-forget safe)."""
    if not MEM0_ENABLED or _mem is None:
        return
    messages = [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    try:
        await asyncio.to_thread(_mem.add, messages, user_id=str(chat_id))
    except Exception as e:
        log.warning("Memory add failed for chat %d: %s", chat_id, e)


async def delete_all(chat_id: int) -> None:
    """Delete all memories for a chat."""
    if not MEM0_ENABLED or _mem is None:
        return
    try:
        await asyncio.to_thread(_mem.delete_all, user_id=str(chat_id))
        log.info("Deleted all memories for chat %d", chat_id)
    except Exception as e:
        log.warning("Memory delete_all failed for chat %d: %s", chat_id, e)


async def get_all(chat_id: int) -> list[dict]:
    """Return all memories for a chat (for debug / /memories command)."""
    if not MEM0_ENABLED or _mem is None:
        return []
    try:
        result = await asyncio.to_thread(_mem.get_all, user_id=str(chat_id))
        return result.get("results", [])
    except Exception as e:
        log.warning("Memory get_all failed for chat %d: %s", chat_id, e)
        return []
