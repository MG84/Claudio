"""
Tests for bot.memory — Mem0 wrapper with fully mocked Mem0.
"""

import asyncio
from unittest.mock import patch, MagicMock

import pytest


# ── Helpers ──────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_module():
    """Reset the memory module singleton before each test."""
    import bot.memory as mod
    mod._mem = None
    yield
    mod._mem = None


@pytest.fixture
def mock_mem0():
    """Provide a mocked Memory instance and patch Memory.from_config."""
    m = MagicMock()
    with patch("bot.memory.Memory") as cls:
        cls.from_config.return_value = m
        yield m


# ── init ─────────────────────────────────────────────────────────────

def test_init_creates_mem0_instance(mock_mem0):
    from bot.memory import init
    init()
    from bot.memory import _mem
    assert _mem is mock_mem0


def test_init_failure_graceful():
    """If Mem0 can't connect, init logs warning and doesn't crash."""
    with patch("bot.memory.Memory") as cls:
        cls.from_config.side_effect = Exception("connection refused")
        from bot.memory import init
        init()  # should not raise
        from bot.memory import _mem
        assert _mem is None


@patch("bot.memory.MEM0_ENABLED", False)
def test_init_disabled_skips():
    """When MEM0_ENABLED=False, init does nothing."""
    from bot.memory import init, _mem
    init()
    assert _mem is None


# ── search ───────────────────────────────────────────────────────────

def test_search_returns_formatted_memories(mock_mem0):
    mock_mem0.search.return_value = {
        "results": [
            {"memory": "L'utente si chiama Marco", "score": 0.9},
            {"memory": "Vive a Roma", "score": 0.8},
        ]
    }
    from bot.memory import init, search
    init()
    result = _run(search("come mi chiamo", 12345))
    assert result == ["L'utente si chiama Marco", "Vive a Roma"]
    mock_mem0.search.assert_called_once_with(
        "come mi chiamo", user_id="12345", limit=10,
    )


def test_search_empty_returns_empty(mock_mem0):
    mock_mem0.search.return_value = {"results": []}
    from bot.memory import init, search
    init()
    result = _run(search("qualcosa", 99))
    assert result == []


@patch("bot.memory.MEM0_ENABLED", False)
def test_search_disabled_returns_empty():
    from bot.memory import search
    result = _run(search("test", 1))
    assert result == []


def test_search_not_initialized_returns_empty():
    """If init was never called or failed, search returns empty."""
    from bot.memory import search
    result = _run(search("test", 1))
    assert result == []


def test_search_exception_returns_empty(mock_mem0):
    mock_mem0.search.side_effect = Exception("qdrant down")
    from bot.memory import init, search
    init()
    result = _run(search("test", 1))
    assert result == []


def test_search_result_missing_memory_key(mock_mem0):
    """Results without 'memory' key are filtered out gracefully."""
    mock_mem0.search.return_value = {
        "results": [
            {"memory": "Fatto valido", "score": 0.9},
            {"score": 0.8},  # missing "memory" key
            {"memory": "", "score": 0.7},  # empty memory string
            {"memory": "Altro fatto", "score": 0.6},
        ]
    }
    from bot.memory import init, search
    init()
    result = _run(search("test", 1))
    assert result == ["Fatto valido", "Altro fatto"]


# ── add ──────────────────────────────────────────────────────────────

def test_add_calls_mem0_with_correct_user_id(mock_mem0):
    mock_mem0.add.return_value = {"results": []}
    from bot.memory import init, add
    init()
    _run(add("Ciao, mi chiamo Marco", "Ciao Marco! Come stai?", 12345))
    mock_mem0.add.assert_called_once()
    call_args = mock_mem0.add.call_args
    messages = call_args[0][0]
    assert any("Marco" in m.get("content", "") for m in messages)
    assert call_args[1]["user_id"] == "12345"


@patch("bot.memory.MEM0_ENABLED", False)
def test_add_disabled_does_nothing():
    from bot.memory import add
    _run(add("msg", "resp", 1))  # should not raise


def test_add_not_initialized_does_nothing():
    from bot.memory import add
    _run(add("msg", "resp", 1))  # should not raise


def test_add_exception_does_not_crash(mock_mem0):
    mock_mem0.add.side_effect = Exception("ollama timeout")
    from bot.memory import init, add
    init()
    _run(add("msg", "resp", 1))  # should not raise


# ── delete_all ───────────────────────────────────────────────────────

def test_delete_all_calls_mem0(mock_mem0):
    from bot.memory import init, delete_all
    init()
    _run(delete_all(12345))
    mock_mem0.delete_all.assert_called_once_with(user_id="12345")


@patch("bot.memory.MEM0_ENABLED", False)
def test_delete_all_disabled_does_nothing():
    from bot.memory import delete_all
    _run(delete_all(1))  # should not raise


def test_delete_all_exception_does_not_crash(mock_mem0):
    mock_mem0.delete_all.side_effect = Exception("error")
    from bot.memory import init, delete_all
    init()
    _run(delete_all(1))  # should not raise


# ── get_all ──────────────────────────────────────────────────────────

def test_get_all_returns_memories(mock_mem0):
    mock_mem0.get_all.return_value = {
        "results": [
            {"memory": "Si chiama Marco", "created_at": "2025-01-01"},
            {"memory": "Vive a Roma", "created_at": "2025-01-02"},
        ]
    }
    from bot.memory import init, get_all
    init()
    result = _run(get_all(12345))
    assert len(result) == 2
    assert result[0]["memory"] == "Si chiama Marco"
    mock_mem0.get_all.assert_called_once_with(user_id="12345")


def test_get_all_empty(mock_mem0):
    mock_mem0.get_all.return_value = {"results": []}
    from bot.memory import init, get_all
    init()
    result = _run(get_all(99))
    assert result == []


@patch("bot.memory.MEM0_ENABLED", False)
def test_get_all_disabled_returns_empty():
    from bot.memory import get_all
    result = _run(get_all(1))
    assert result == []


def test_get_all_exception_returns_empty(mock_mem0):
    mock_mem0.get_all.side_effect = Exception("error")
    from bot.memory import init, get_all
    init()
    result = _run(get_all(1))
    assert result == []
