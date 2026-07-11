"""Execution-layer limits for concurrent paid Chat turns."""

from __future__ import annotations

from persome.api import chat_routes


def setup_function() -> None:
    chat_routes._active_turns.clear()


def teardown_function() -> None:
    chat_routes._active_turns.clear()


def test_same_session_cannot_run_overlapping_turns() -> None:
    assert chat_routes._reserve_chat_turn("session-a") is None
    assert chat_routes._reserve_chat_turn("session-a") == "session_busy"


def test_global_chat_turn_limit_rejects_excess_work() -> None:
    for index in range(chat_routes.MAX_CONCURRENT_CHAT_TURNS):
        assert chat_routes._reserve_chat_turn(f"session-{index}") is None

    assert chat_routes._reserve_chat_turn("one-too-many") == "server_busy"


def test_releasing_turn_restores_capacity() -> None:
    for index in range(chat_routes.MAX_CONCURRENT_CHAT_TURNS):
        assert chat_routes._reserve_chat_turn(f"session-{index}") is None

    chat_routes._release_chat_turn("session-0")
    assert chat_routes._reserve_chat_turn("replacement") is None
