"""Chat API history stays owner-only even under a permissive process umask."""

from __future__ import annotations

import os
import stat

from persome.api import chat_routes


def test_api_chat_history_directory_and_file_are_private(ac_root) -> None:
    session = chat_routes.ChatSession(
        id="private01",
        created_at="2026-07-11T12:00:00+08:00",
        updated_at="2026-07-11T12:00:00+08:00",
        messages=[{"role": "user", "content": "private message"}],
    )
    previous = os.umask(0o022)
    try:
        chat_routes._save_session(session)
    finally:
        os.umask(previous)

    history_dir = ac_root / "chat-history"
    history_file = history_dir / "api-private01.json"
    assert stat.S_IMODE(history_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(history_file.stat().st_mode) == 0o600
