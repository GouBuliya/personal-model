"""Unit tests for the frontmost window-context fast-path cache.

Pure logic, no macOS: an injected monotonic clock exercises the freshness
boundary deterministically and a bare event dict stands in for a watcher event.
"""

from __future__ import annotations

import threading

from persome.capture.window_context import WindowContext, WindowContextCache
from persome.capture.window_meta import WindowMeta


class _Clock:
    """Deterministic monotonic clock; advance with ``tick``."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def _event(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "event_type": "AXFocusedWindowChanged",
        "pid": 4321,
        "app_name": "Safari",
        "bundle_id": "com.apple.Safari",
        "window_title": "Example",
    }
    base.update(over)
    return base


def test_complete_event_populates_and_resolves() -> None:
    clock = _Clock()
    cache = WindowContextCache(cache_seconds=5.0, clock=clock)

    ctx = cache.observe_event(_event())
    assert isinstance(ctx, WindowContext)
    assert ctx.app_name == "Safari"
    assert ctx.pid == 4321

    meta = cache.resolve(trigger={"bundle_id": "com.apple.Safari"})
    assert meta == WindowMeta(app_name="Safari", title="Example", bundle_id="com.apple.Safari")


def test_background_and_title_events_cannot_replace_context() -> None:
    cache = WindowContextCache(cache_seconds=5.0, clock=_Clock())
    assert cache.observe_event(_event()) is not None
    assert cache.observe_event(_event(event_type="AXValueChanged", app_name="Sneaky")) is None
    assert cache.observe_event(_event(event_type="AXTitleChanged", app_name="Sneaky")) is None
    # The frontmost context stands, untouched by the background events.
    assert cache.resolve(None) == WindowMeta("Safari", "Example", "com.apple.Safari")


def test_lifecycle_event_with_empty_identity_does_not_replace() -> None:
    cache = WindowContextCache(cache_seconds=5.0, clock=_Clock())
    cache.observe_event(_event())
    # Frontmost event type but no stable identity (no pid, no bundle) → rejected.
    assert cache.observe_event(_event(pid=0, bundle_id="", app_name="Ghost")) is None
    # Frontmost + identity but no display fields → rejected.
    assert cache.observe_event(_event(app_name="", window_title="")) is None
    assert cache.resolve(None) == WindowMeta("Safari", "Example", "com.apple.Safari")


def test_freshness_boundary_uses_injected_clock() -> None:
    clock = _Clock()
    cache = WindowContextCache(cache_seconds=5.0, clock=clock)
    cache.observe_event(_event())

    clock.tick(5.0)  # exactly at the boundary is still fresh
    assert cache.resolve(None) is not None
    clock.tick(0.001)  # just past → stale
    assert cache.resolve(None) is None


def test_bundle_conflict_returns_no_result() -> None:
    cache = WindowContextCache(cache_seconds=5.0, clock=_Clock())
    cache.observe_event(_event())
    assert cache.resolve({"bundle_id": "com.google.Chrome"}) is None
    # No trigger bundle → no conflict.
    assert cache.resolve({"bundle_id": ""}) is not None


def test_pid_conflict_returns_no_result() -> None:
    cache = WindowContextCache(cache_seconds=5.0, clock=_Clock())
    cache.observe_event(_event())
    assert cache.resolve({"bundle_id": "com.apple.Safari", "_pid": 9999}) is None
    assert cache.resolve({"bundle_id": "com.apple.Safari", "_pid": 4321}) is not None


def test_stale_entry_returns_no_result() -> None:
    clock = _Clock()
    cache = WindowContextCache(cache_seconds=5.0, clock=clock)
    cache.observe_event(_event())
    clock.tick(60.0)
    assert cache.resolve(None) is None


def test_successful_applescript_fallback_can_be_remembered() -> None:
    clock = _Clock()
    cache = WindowContextCache(cache_seconds=5.0, clock=clock)
    cache.remember_meta(WindowMeta("Cursor", "main.py", "com.todesktop.cursor"))
    assert cache.resolve(None) == WindowMeta("Cursor", "main.py", "com.todesktop.cursor")
    # An empty osascript result must not poison the cache.
    cache.remember_meta(WindowMeta())
    assert cache.resolve(None) == WindowMeta("Cursor", "main.py", "com.todesktop.cursor")


def test_malformed_event_is_ignored_not_raised() -> None:
    cache = WindowContextCache(cache_seconds=5.0, clock=_Clock())
    assert cache.observe_event({"event_type": "AXFocusedWindowChanged", "pid": object()}) is None
    assert cache.observe_event({}) is None


def test_concurrent_observe_and_resolve_do_not_expose_partial_state() -> None:
    cache = WindowContextCache(cache_seconds=100.0, clock=_Clock())
    stop = threading.Event()
    seen_bad = []

    def writer() -> None:
        i = 0
        while not stop.is_set():
            cache.observe_event(_event(bundle_id=f"com.app.{i % 3}", app_name=f"App{i % 3}"))
            i += 1

    def reader() -> None:
        while not stop.is_set():
            meta = cache.resolve(None)
            # Any resolved entry must be internally consistent (app+bundle set).
            if meta is not None and (not meta.app_name or not meta.bundle_id):
                seen_bad.append(meta)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    stop.wait(0.2)
    stop.set()
    for t in threads:
        t.join()
    assert seen_bad == []
