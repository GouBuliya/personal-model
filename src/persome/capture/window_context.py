"""Short-lived cache of frontmost window identity from watcher events.

``mac-ax-watcher`` events already carry the frontmost application's ``pid``,
``app_name``, ``bundle_id``, and ``window_title``. Historically the dispatcher
dropped everything but ``bundle_id`` / ``window_title`` and every capture then
paid an AppleScript ``System Events`` round-trip to re-derive the same fields.

This module keeps the most recent *reliable* frontmost context so a capture can
reuse it instead of shelling out to ``osascript``. Freshness is measured with a
monotonic clock (never the wall-clock event timestamp): a system clock change
therefore cannot turn stale context into fresh context. A bundle/PID conflict
between the trigger and the cached entry rejects reuse — attributing content to
the wrong application is worse than paying the lookup cost.

The cache is touched by two threads — the watcher reader thread calls
``observe_event`` while the capture worker calls ``resolve`` — so all shared
state is guarded by a lock.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..logger import get
from .window_meta import WindowMeta

logger = get("persome.capture")

# Events that establish frontmost user context. Background value changes,
# title-only changes, and internal watcher lifecycle events do not.
_FRONTMOST_EVENTS = frozenset(
    {
        "AXApplicationActivated",
        "AXFocusedWindowChanged",
        "UserMouseClick",
        "UserTextInput",
    }
)


@dataclass(frozen=True)
class WindowContext:
    """An immutable snapshot of frontmost window identity from one event."""

    pid: int | None
    app_name: str
    bundle_id: str
    window_title: str
    observed_monotonic: float

    def to_meta(self) -> WindowMeta:
        return WindowMeta(
            app_name=self.app_name,
            title=self.window_title,
            bundle_id=self.bundle_id,
        )


def _coerce_pid(value: Any) -> int | None:
    """Return a positive int PID or None; ignore malformed values."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        pid = int(value.strip())
        return pid if pid > 0 else None
    return None


def _coerce_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


class WindowContextCache:
    """Thread-safe latest-frontmost cache with a bounded freshness window."""

    def __init__(
        self,
        *,
        cache_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache_seconds = float(cache_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._latest: WindowContext | None = None

    def observe_event(self, event: Mapping[str, Any]) -> WindowContext | None:
        """Record a watcher event as latest context when it is reliable.

        Returns the stored ``WindowContext`` on acceptance, else ``None``. Never
        raises: malformed events are ignored so a bad event cannot abort capture.
        """
        try:
            event_type = _coerce_str(event.get("event_type"))
            if event_type not in _FRONTMOST_EVENTS:
                return None

            pid = _coerce_pid(event.get("pid"))
            bundle_id = _coerce_str(event.get("bundle_id"))
            app_name = _coerce_str(event.get("app_name"))
            window_title = _coerce_str(event.get("window_title"))

            # Require at least one stable identity and one display field.
            if pid is None and not bundle_id:
                return None
            if not app_name and not window_title:
                return None

            ctx = WindowContext(
                pid=pid,
                app_name=app_name,
                bundle_id=bundle_id,
                window_title=window_title,
                observed_monotonic=self._clock(),
            )
        except Exception as exc:  # noqa: BLE001 — never let the cache abort capture
            logger.debug("window context observe ignored malformed event: %s", exc)
            return None

        with self._lock:
            self._latest = ctx
        return ctx

    def remember_meta(self, meta: WindowMeta) -> None:
        """Cache a successful AppleScript fallback as latest context.

        Only stored when it carries usable identity + display fields, so an empty
        ``WindowMeta`` (osascript failure) does not poison the cache.
        """
        if not meta.bundle_id and not meta.app_name and not meta.title:
            return
        if not meta.app_name and not meta.title:
            return
        ctx = WindowContext(
            pid=None,
            app_name=meta.app_name,
            bundle_id=meta.bundle_id,
            window_title=meta.title,
            observed_monotonic=self._clock(),
        )
        with self._lock:
            self._latest = ctx

    def resolve(self, trigger: Mapping[str, Any] | None) -> WindowMeta | None:
        """Return fresh cached window metadata usable for ``trigger``.

        Accepts the latest entry when it is no older than ``cache_seconds`` and a
        trigger ``bundle_id`` / ``pid``, when present, does not conflict with the
        cached entry. Returns ``None`` when the cache is empty, stale, or conflicts.
        """
        with self._lock:
            ctx = self._latest
        if ctx is None:
            return None
        if (self._clock() - ctx.observed_monotonic) > self._cache_seconds:
            return None
        if trigger is not None and self._conflicts(ctx, trigger):
            return None
        return ctx.to_meta()

    @staticmethod
    def _conflicts(ctx: WindowContext, trigger: Mapping[str, Any]) -> bool:
        trigger_bundle = _coerce_str(trigger.get("bundle_id"))
        if trigger_bundle and ctx.bundle_id and trigger_bundle != ctx.bundle_id:
            return True
        trigger_pid = _coerce_pid(trigger.get("_pid"))
        return bool(trigger_pid is not None and ctx.pid is not None and trigger_pid != ctx.pid)
