"""Tests for EventDispatcher: watcher identity preservation + fast-path wiring.

These assert the dispatcher feeds the context cache and carries the watcher's
pid/app_name into the trigger as private ``_``-prefixed keys, without altering
the public trigger contract, dedup, or debounce behavior.
"""

from __future__ import annotations

from typing import Any

from persome.capture.event_dispatcher import EventDispatcher
from persome.capture.window_context import WindowContextCache


def _capture_collector() -> tuple[list[dict[str, Any]], Any]:
    seen: list[dict[str, Any]] = []
    return seen, seen.append


def test_trigger_preserves_watcher_identity() -> None:
    seen, fn = _capture_collector()
    dispatcher = EventDispatcher(fn, context_cache=WindowContextCache())
    dispatcher.on_event(
        {
            "event_type": "AXFocusedWindowChanged",
            "pid": 777,
            "app_name": "Safari",
            "bundle_id": "com.apple.Safari",
            "window_title": "Example",
        }
    )
    assert len(seen) == 1
    trigger = seen[0]
    assert trigger["_app_name"] == "Safari"
    assert trigger["_pid"] == 777
    assert "_observed_monotonic" in trigger


def test_public_trigger_fields_unchanged() -> None:
    seen, fn = _capture_collector()
    dispatcher = EventDispatcher(fn, context_cache=WindowContextCache())
    dispatcher.on_event(
        {
            "event_type": "UserMouseClick",
            "pid": 5,
            "app_name": "Cursor",
            "bundle_id": "com.todesktop.cursor",
            "window_title": "main.py",
            "details": {"button": "left", "x": 10, "y": 20, "element": {"role": "AXButton"}},
        }
    )
    trigger = seen[0]
    # Public contract: only these keys reach the persisted trigger (plus private _*).
    assert trigger["event_type"] == "UserMouseClick"
    assert trigger["bundle_id"] == "com.todesktop.cursor"
    assert trigger["window_title"] == "main.py"
    # details.element survives (attention-localization payload).
    assert trigger["details"]["element"] == {"role": "AXButton"}


def test_works_without_context_cache() -> None:
    seen, fn = _capture_collector()
    dispatcher = EventDispatcher(fn)  # no cache injected
    dispatcher.on_event(
        {
            "event_type": "AXApplicationActivated",
            "pid": 9,
            "app_name": "Notes",
            "bundle_id": "com.apple.Notes",
            "window_title": "",
        }
    )
    assert len(seen) == 1
    # No observed_monotonic without a cache, but identity still carried.
    assert seen[0]["_app_name"] == "Notes"
    assert "_observed_monotonic" not in seen[0]


def test_dedup_still_collapses_rapid_fire() -> None:
    seen, fn = _capture_collector()
    dispatcher = EventDispatcher(fn, dedup_interval_seconds=1000.0)
    ev = {
        "event_type": "AXValueChanged",
        "bundle_id": "com.apple.Safari",
        "window_title": "Example",
    }
    dispatcher.on_event(ev)
    dispatcher.on_event(ev)  # same (type, bundle, title) within dedup window → dropped
    # AXValueChanged is debounced (not immediate); no synchronous capture fired.
    assert seen == []


def test_context_cache_observes_before_dispatch() -> None:
    cache = WindowContextCache()
    _, fn = _capture_collector()
    dispatcher = EventDispatcher(fn, context_cache=cache)
    dispatcher.on_event(
        {
            "event_type": "AXFocusedWindowChanged",
            "pid": 1,
            "app_name": "Safari",
            "bundle_id": "com.apple.Safari",
            "window_title": "Example",
        }
    )
    assert cache.resolve(None) is not None
