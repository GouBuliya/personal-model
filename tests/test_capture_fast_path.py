"""Scheduler window-metadata resolution + AX-circuit OCR suppression.

Drives ``_build_capture`` with fake providers and monkeypatched screenshot /
window_meta so it runs offline. Covers the spec's resolution order (AX >
watcher > cache > AppleScript) and the circuit-open metadata-only path.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from persome.capture import ax_models, screen_state, window_meta
from persome.capture import scheduler as sched_mod
from persome.capture.window_context import WindowContextCache
from persome.config import CaptureConfig


class _Provider:
    """Configurable AX provider stand-in."""

    available = True

    def __init__(self, *, apps: list[dict[str, Any]] | None = None, status: str = "ok") -> None:
        self._apps = apps
        self.last_status = status

    def capture_frontmost(self, *, focused_window_only: bool = True, target: Any = None) -> Any:
        if self.last_status == "circuit_open" or self._apps is None:
            return None
        return ax_models.AXCaptureResult(
            raw_json={"apps": self._apps}, timestamp="2026-01-01T00:00:00Z", apps=self._apps
        )


def _cfg(**over: Any) -> CaptureConfig:
    base: dict[str, Any] = {
        "include_screenshot": True,
        "screenshot_max_width": 100,
        "screenshot_jpeg_quality": 50,
        "enable_ocr_fallback": True,
        "ocr_min_gap_seconds": 0,
        "cmux_source_enabled": False,
        "encrypt_screenshots": False,
    }
    base.update(over)
    return CaptureConfig(**base)


def _ax_app() -> dict[str, Any]:
    return {
        "name": "Safari",
        "bundle_id": "com.apple.Safari",
        "is_frontmost": True,
        "windows": [{"title": "Example Page"}],
    }


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen_state, "is_screen_locked", lambda: False)

    class _Shot:
        image_base64 = "AAAA"
        mime_type = "image/jpeg"
        width = 10
        height = 10

    monkeypatch.setattr(sched_mod.screenshot, "grab", lambda **_: _Shot())
    monkeypatch.setattr(sched_mod.cmux_source, "maybe_inject", lambda *a, **k: False)


def _no_applescript(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch active_window to record calls; returns the call counter list."""
    calls: list[int] = []

    def _fake() -> window_meta.WindowMeta:
        calls.append(1)
        return window_meta.WindowMeta("AppleScriptApp", "AS Title", "com.as.app")

    monkeypatch.setattr(sched_mod.window_meta, "active_window", _fake)
    return calls


def test_ax_success_prevents_applescript(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _no_applescript(monkeypatch)
    out = sched_mod._build_capture(_cfg(), _Provider(apps=[_ax_app()]), None)
    assert out is not None
    assert out["meta_source"] == "ax"
    assert out["window_meta"] == {
        "app_name": "Safari",
        "title": "Example Page",
        "bundle_id": "com.apple.Safari",
    }
    assert calls == []  # AppleScript never called


def test_fresh_watcher_context_prevents_applescript(
    ac_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _no_applescript(monkeypatch)
    trigger = {
        "event_type": "AXFocusedWindowChanged",
        "bundle_id": "com.google.Chrome",
        "window_title": "Docs",
        "_app_name": "Chrome",
        "_pid": 55,
        "_observed_monotonic": time.monotonic(),
    }
    # AX returns nothing usable (empty apps) → falls to the watcher context.
    out = sched_mod._build_capture(_cfg(), _Provider(apps=[]), trigger)
    assert out is not None
    assert out["meta_source"] == "watcher"
    assert out["window_meta"]["app_name"] == "Chrome"
    assert calls == []


def test_stale_context_calls_applescript_once(
    ac_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _no_applescript(monkeypatch)
    trigger = {
        "event_type": "AXFocusedWindowChanged",
        "bundle_id": "com.google.Chrome",
        "window_title": "Docs",
        "_app_name": "Chrome",
        "_pid": 55,
        "_observed_monotonic": time.monotonic() - 60.0,  # stale
    }
    out = sched_mod._build_capture(_cfg(), _Provider(apps=[]), trigger)
    assert out is not None
    assert out["meta_source"] == "applescript"
    assert out["window_meta"]["app_name"] == "AppleScriptApp"
    assert len(calls) == 1


def test_cache_used_when_no_ax_or_watcher(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _no_applescript(monkeypatch)
    cache = WindowContextCache(cache_seconds=5.0)
    cache.observe_event(
        {
            "event_type": "AXApplicationActivated",
            "pid": 9,
            "app_name": "Notes",
            "bundle_id": "com.apple.Notes",
            "window_title": "Todo",
        }
    )
    # Heartbeat (no trigger) with no AX apps → cache resolves it.
    out = sched_mod._build_capture(_cfg(), _Provider(apps=[]), None, context_cache=cache)
    assert out is not None
    assert out["meta_source"] == "cache"
    assert out["window_meta"]["app_name"] == "Notes"
    assert calls == []


def test_circuit_open_suppresses_screenshot_and_ocr(
    ac_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_applescript(monkeypatch)
    ocr_calls: list[int] = []
    monkeypatch.setattr(sched_mod, "_daemon_ocr_jpeg_provider", lambda cfg: ocr_calls.append(1))
    out = sched_mod._build_capture(_cfg(), _Provider(apps=None, status="circuit_open"), None)
    assert out is not None
    assert out["ax_unavailable"] is True
    assert out["ax_skip_reason"] == "circuit_open"
    assert out["secure_state_unknown"] is True
    assert "screenshot" not in out
    assert "_ocr_pending_jpeg" not in out
    # The daemon OCR jpeg provider is never even constructed while open.
    assert ocr_calls == []


def test_public_trigger_strips_private_keys(ac_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_applescript(monkeypatch)
    trigger = {
        "event_type": "UserMouseClick",
        "bundle_id": "com.apple.Safari",
        "window_title": "Example",
        "details": {"button": "left"},
        "_app_name": "Safari",
        "_pid": 12,
        "_observed_monotonic": time.monotonic(),
    }
    out = sched_mod._build_capture(_cfg(), _Provider(apps=[_ax_app()]), trigger)
    assert out is not None
    persisted = out["trigger"]
    assert set(persisted) == {"event_type", "bundle_id", "window_title", "details"}
    assert not any(k.startswith("_") for k in persisted)
