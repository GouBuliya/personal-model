"""capture privacy gating (spec E7): lock/sleep + secure-input suppression.

Drives the scheduler's capture-build entry (`_build_capture`) with the
`screen_state` probes monkeypatched to controllable values — no real lock
screen / password box needed. Covers:

* locked → whole capture skipped (no screenshot, no AX, returns None);
* secure-input focused → that tick drops screenshot + AX;
* normal state → capture proceeds as before;
* toggles off → no suppression;
* a probe that raises → no crash, fail-safe behaviour.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from persome.capture import scheduler as scheduler_mod
from persome.capture import screen_state


class _FakeProvider:
    """Minimal ax_capture.AXProvider stand-in returning a canned AX result."""

    available = True
    last_status = "ok"

    def __init__(self, ax_tree: dict[str, Any] | None = None) -> None:
        self._ax_tree = ax_tree if ax_tree is not None else _normal_ax_tree()

    def capture_frontmost(self, *, focused_window_only: bool = True, target: Any = None) -> Any:
        class _Result:
            raw_json = self._ax_tree
            metadata = {"node_count": 1}
            apps = self._ax_tree.get("apps", [])

        return _Result()


class _Cfg:
    """A tiny CaptureConfig stand-in with just the fields _build_capture reads."""

    include_screenshot = True
    screenshot_max_width = 100
    screenshot_jpeg_quality = 50
    enable_ocr_fallback = False
    ocr_min_gap_seconds = 0
    ocr_tier = "tiny"
    ocr_structured = False
    cmux_source_enabled = False
    window_context_cache_seconds = 5.0
    # privacy toggles (default on); flipped per test
    pause_on_lock = True
    suppress_secure_input = True
    encrypt_screenshots = False


def _normal_ax_tree() -> dict[str, Any]:
    return {
        "apps": [
            {
                "bundle_id": "com.test.editor",
                "name": "Editor",
                "is_frontmost": True,
                "focused_element": {
                    "role": "AXTextArea",
                    "value": "def foo()",
                    "is_editable": True,
                },
                "windows": [
                    {
                        "title": "main.py",
                        "focused": True,
                        "elements": [{"role": "AXStaticText", "value": "def foo(): return 1"}],
                    }
                ],
            }
        ],
        "timestamp": "2026-04-22T14:00:00+08:00",
    }


def _secure_ax_tree() -> dict[str, Any]:
    return {
        "apps": [
            {
                "bundle_id": "com.test.bank",
                "name": "Bank",
                "is_frontmost": True,
                "focused_element": {
                    "role": "AXTextField",
                    "subrole": "AXSecureTextField",
                    "value": "[REDACTED]",
                    "is_editable": True,
                },
                "windows": [
                    {
                        "title": "Login",
                        "focused": True,
                        "elements": [{"role": "AXStaticText", "value": "Enter your password"}],
                    }
                ],
            }
        ],
        "timestamp": "2026-04-22T14:00:00+08:00",
    }


@pytest.fixture(autouse=True)
def _stub_screenshot_and_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make screenshot grab + window_meta deterministic and offline."""

    class _Shot:
        image_base64 = "AAAA"
        mime_type = "image/jpeg"
        width = 100
        height = 50

    monkeypatch.setattr(scheduler_mod.screenshot, "grab", lambda **_: _Shot())

    class _Meta:
        app_name = "Editor"
        title = "main.py"
        bundle_id = "com.test.editor"

    monkeypatch.setattr(scheduler_mod.window_meta, "active_window", lambda: _Meta())
    # No cmux injection in these tests.
    monkeypatch.setattr(scheduler_mod.cmux_source, "maybe_inject", lambda *a, **k: False)


# --------------------------------------------------------------------------- #
# Lock / sleep
# --------------------------------------------------------------------------- #
def test_locked_skips_whole_capture(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: True)
    out = scheduler_mod._build_capture(_Cfg(), _FakeProvider(), None)
    assert out is None


def test_locked_toggle_off_does_not_suppress(
    ac_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: True)
    cfg = _Cfg()
    cfg.pause_on_lock = False
    out = scheduler_mod._build_capture(cfg, _FakeProvider(), None)
    assert out is not None
    assert "ax_tree" in out
    assert "screenshot" in out


def test_unlocked_captures_normally(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: False)
    out = scheduler_mod._build_capture(_Cfg(), _FakeProvider(), None)
    assert out is not None
    assert "ax_tree" in out
    assert "screenshot" in out
    assert out.get("visible_text")  # s1_parser enriched it
    assert not out.get("secure_input_suppressed")


# --------------------------------------------------------------------------- #
# Secure input
# --------------------------------------------------------------------------- #
def test_secure_input_drops_screenshot_and_ax(
    ac_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: False)
    provider = _FakeProvider(_secure_ax_tree())
    out = scheduler_mod._build_capture(_Cfg(), provider, None)
    assert out is not None  # the window_meta row still lands, just no content
    assert "screenshot" not in out
    assert "ax_tree" not in out
    assert "ax_metadata" not in out
    assert out.get("secure_input_suppressed") is True
    assert out.get("visible_text") == ""
    assert out.get("ax_unavailable") is True


def test_secure_input_toggle_off_keeps_content(
    ac_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: False)
    cfg = _Cfg()
    cfg.suppress_secure_input = False
    provider = _FakeProvider(_secure_ax_tree())
    out = scheduler_mod._build_capture(cfg, provider, None)
    assert out is not None
    assert "screenshot" in out
    assert "ax_tree" in out
    assert not out.get("secure_input_suppressed")


def test_non_secure_field_not_suppressed(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: False)
    out = scheduler_mod._build_capture(_Cfg(), _FakeProvider(), None)
    assert out is not None
    assert "screenshot" in out
    assert "ax_tree" in out
    assert not out.get("secure_input_suppressed")


# --------------------------------------------------------------------------- #
# Fail-safe: a raising lock probe never crashes the build and fails CLOSED
# --------------------------------------------------------------------------- #
def test_lock_probe_raises_fails_closed(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> bool:
        raise RuntimeError("probe blew up")

    # Patch the *internal* probes so the public is_screen_locked exercises its
    # own try/except fail-closed path rather than us patching the public function.
    monkeypatch.setattr(screen_state, "_quartz_screen_is_locked", _boom)
    monkeypatch.setattr(screen_state, "_ioreg_says_locked", _boom)
    # Unknown lock state must suppress capture; leaking behind a lock screen is
    # worse than missing a frame until the next successful probe.
    assert screen_state.is_screen_locked() is True
    out = scheduler_mod._build_capture(_Cfg(), _FakeProvider(), None)
    assert out is None


def test_secure_probe_raises_does_not_crash(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: False)

    def _boom(_out: dict) -> bool:
        raise RuntimeError("secure probe blew up")

    monkeypatch.setattr(screen_state, "_focused_element_from_capture", _boom)
    # The public helper swallows and returns False (nothing concrete to suppress).
    assert screen_state.is_secure_input_active({"ax_tree": {}}) is False
    out = scheduler_mod._build_capture(_Cfg(), _FakeProvider(_secure_ax_tree()), None)
    assert out is not None
    # Probe error → not suppressed (only a positive signal suppresses).
    assert "ax_tree" in out


# --------------------------------------------------------------------------- #
# Pure probe unit checks (no scheduler)
# --------------------------------------------------------------------------- #
def test_is_secure_input_active_positive_by_subrole() -> None:
    assert screen_state.is_secure_input_active({"ax_tree": _secure_ax_tree()}) is True


def test_is_secure_input_active_negative_normal() -> None:
    assert screen_state.is_secure_input_active({"ax_tree": _normal_ax_tree()}) is False


def test_is_secure_input_active_no_ax_tree() -> None:
    assert screen_state.is_secure_input_active({}) is False


def test_lock_quartz_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "_quartz_screen_is_locked", lambda: True)
    monkeypatch.setattr(screen_state, "_ioreg_says_locked", lambda: False)
    assert screen_state.is_screen_locked() is True


def test_quartz_missing_lock_key_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "Quartz",
        SimpleNamespace(CGSessionCopyCurrentDictionary=lambda: {"kCGSessionUserNameKey": "user"}),
    )

    assert screen_state._quartz_screen_is_locked() is None


def test_quartz_explicit_unlocked_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "Quartz",
        SimpleNamespace(CGSessionCopyCurrentDictionary=lambda: {"CGSSessionScreenIsLocked": 0}),
    )

    assert screen_state._quartz_screen_is_locked() is False


def test_lock_falls_back_to_ioreg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "_quartz_screen_is_locked", lambda: None)
    monkeypatch.setattr(screen_state, "_ioreg_says_locked", lambda: True)
    assert screen_state.is_screen_locked() is True


def test_lock_none_everywhere_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "_quartz_screen_is_locked", lambda: None)
    monkeypatch.setattr(screen_state, "_ioreg_says_locked", lambda: None)
    assert screen_state.is_screen_locked() is True


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ('    "IOConsoleLocked" = Yes\n', True),
        (
            '    "IOConsoleLocked" = No\n'
            '    "IOConsoleUsers" = ({"CGSSessionScreenIsLocked"=No})\n',
            False,
        ),
        (
            '    "IOConsoleLocked" = No\n'
            '    "IOConsoleUsers" = ({"CGSSessionScreenIsLocked"=Yes})\n',
            False,
        ),
        (
            '    "IOConsoleUsers" = ('
            '{"kCGSSessionOnConsoleKey"=No,"CGSSessionScreenIsLocked"=Yes},'
            '{"kCGSSessionOnConsoleKey"=Yes,"CGSSessionScreenIsLocked"=No})\n',
            False,
        ),
        (
            '    "IOConsoleUsers" = ('
            '{"kCGSSessionOnConsoleKey"=No,"CGSSessionScreenIsLocked"=No},'
            '{"kCGSSessionOnConsoleKey"=Yes,"CGSSessionScreenIsLocked"=Yes})\n',
            True,
        ),
        ('    "Unrelated" = 1\n', None),
    ],
)
def test_ioreg_root_lock_flags(
    monkeypatch: pytest.MonkeyPatch, output: str, expected: bool | None
) -> None:
    command: list[str] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        command.extend(args[0])
        return subprocess.CompletedProcess(args[0], 0, output, "")

    monkeypatch.setattr(
        screen_state.subprocess,
        "run",
        fake_run,
    )
    assert screen_state._ioreg_says_locked() is expected
    assert command[0] == "/usr/sbin/ioreg"
