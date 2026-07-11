"""Screen-state privacy signals for the capture layer.

Two read-only probes the scheduler consults at capture time to honour the
privacy guardrails (spec E7):

* :func:`is_screen_locked` — is the macOS login/lock screen up (or the machine
  asleep)? When True the scheduler skips the whole capture — nothing should be
  collected behind the lock screen.
* :func:`is_secure_input_active` — is the currently focused element a secure
  text field (a password box)? When True the scheduler skips the screenshot AND
  AX collection for that window so a password (or the screen around it) never
  lands in the buffer.

Both are deliberately small, side-effect-free, and privacy-conservative. Lock
detection is **fail-CLOSED** — an error / "don't know" is treated as locked.
Secure-input detection likewise lets a positive "looks secure" signal win. A
missed frame is recoverable; buffering a lock screen or password is not.

The macOS lock probe is monkeypatch-friendly: the Quartz call is isolated in
:func:`_quartz_screen_is_locked` and the subprocess fallbacks in
:func:`_ioreg_says_locked`. Tests patch those (or the public functions) rather
than depending on a real lock screen.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from ..logger import get

logger = get("persome.capture.screen_state")

_SECURE_TEXT_SUBROLE = "AXSecureTextField"
_SECURE_TEXT_ROLE = "AXTextField"
_LOCK_VALUE = r"(Yes|No|true|false|1|0)"
_IOREG_CONSOLE_LOCK = re.compile(
    rf'"IOConsoleLocked"\s*=\s*{_LOCK_VALUE}\b',
    re.IGNORECASE,
)
_IOREG_SESSION_BLOCK = re.compile(r"\{([^{}]*)\}")
_IOREG_ON_CONSOLE = re.compile(rf'"kCGSSessionOnConsoleKey"\s*=\s*{_LOCK_VALUE}\b', re.I)
_IOREG_SESSION_LOCK = re.compile(rf'"CGSSessionScreenIsLocked"\s*=\s*{_LOCK_VALUE}\b', re.I)


def _lock_value(value: str) -> bool:
    return value.lower() in {"yes", "true", "1"}


# --------------------------------------------------------------------------- #
# Lock / sleep detection (fail-closed)
# --------------------------------------------------------------------------- #
def _quartz_screen_is_locked() -> bool | None:
    """Read ``CGSSessionScreenIsLocked`` via Quartz (pyobjc).

    Returns the boolean lock state, or ``None`` when Quartz is unavailable or
    the session dictionary doesn't carry the key (then the caller falls back).
    Isolated so tests can monkeypatch it without importing Quartz.
    """
    try:
        from Quartz import CGSessionCopyCurrentDictionary
    except Exception:  # noqa: BLE001 — pyobjc not present (e.g. Linux CI / minimal venv)
        return None
    try:
        session = CGSessionCopyCurrentDictionary()
        if not session:
            return None
        if "CGSSessionScreenIsLocked" not in session:
            return None
        return bool(session["CGSSessionScreenIsLocked"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("Quartz lock probe failed: %s", exc)
        return None


def _ioreg_says_locked() -> bool | None:
    """Subprocess fallback: read explicit console/session lock flags from ``ioreg``.

    Modern macOS no longer reliably exposes ``IODisplayWrangler`` power state,
    but the Root registry includes ``IOConsoleLocked`` and the active session's
    ``CGSSessionScreenIsLocked``. Any explicit true wins conservatively; all
    explicit false values mean unlocked; missing/malformed output stays unknown.
    """
    try:
        out = subprocess.run(
            ["/usr/sbin/ioreg", "-n", "Root", "-d", "1"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except Exception as exc:  # noqa: BLE001 — not macOS, no ioreg, timeout, etc.
        logger.debug("ioreg lock probe unavailable: %s", exc)
        return None
    if out.returncode != 0:
        return None
    # Root's top-level flag describes the current console and is authoritative.
    # Do not let a locked, inactive fast-user-switching session override it.
    console = _IOREG_CONSOLE_LOCK.search(out.stdout)
    if console is not None:
        return _lock_value(console.group(1))

    active_values: list[bool] = []
    for block in _IOREG_SESSION_BLOCK.findall(out.stdout):
        on_console = _IOREG_ON_CONSOLE.search(block)
        if on_console is None or not _lock_value(on_console.group(1)):
            continue
        locked = _IOREG_SESSION_LOCK.search(block)
        if locked is not None:
            active_values.append(_lock_value(locked.group(1)))
    if not active_values:
        return None
    # Conflicting signals for the active console stay fail-closed.
    return any(active_values)


def is_screen_locked() -> bool:
    """True when the screen is locked, asleep, or cannot be established.

    Order: Quartz ``CGSSessionScreenIsLocked`` (authoritative) → explicit
    ``ioreg`` Root session flags. If neither yields a definite answer, returns True
    (fail-closed) so a broken probe cannot collect private lock-screen context.
    Never raises.
    """
    try:
        quartz = _quartz_screen_is_locked()
        if quartz is not None:
            return quartz
        ioreg = _ioreg_says_locked()
        if ioreg is not None:
            return ioreg
    except Exception as exc:  # noqa: BLE001 — fail-closed belt-and-suspenders
        logger.warning("lock detection errored; suppressing capture: %s", exc)
    return True


# --------------------------------------------------------------------------- #
# Secure-input (password box) detection (fail-conservative)
# --------------------------------------------------------------------------- #
def _focused_element_from_capture(out: dict[str, Any]) -> dict[str, Any] | None:
    """The OS-reported focused element from a built capture's ax_tree.

    Reads the frontmost app's ``focused_element`` (the AX helper emits a compact
    ``{role, subrole, ...}`` dict — secure fields are role ``AXTextField`` +
    subrole ``AXSecureTextField``). Returns ``None`` when the capture has no
    ax_tree / no frontmost app / no focused element.
    """
    ax_tree = out.get("ax_tree")
    if not isinstance(ax_tree, dict):
        return None
    apps = ax_tree.get("apps") or []
    if not isinstance(apps, list):
        return None
    front = next(
        (a for a in apps if isinstance(a, dict) and a.get("is_frontmost")),
        None,
    )
    if front is None:
        front = next((a for a in apps if isinstance(a, dict)), None)
    if front is None:
        return None
    fe = front.get("focused_element")
    return fe if isinstance(fe, dict) else None


def is_secure_input_active(out: dict[str, Any]) -> bool:
    """True when the focused element of ``out`` is a secure text field.

    Reads the (already-captured, read-only) AX info on the built capture dict.
    **Fail-conservative**: if the role/subrole markers say "secure", suppress —
    but a probe error returns ``False`` (we have nothing concrete to suppress)
    rather than raising; the suppression only fires on a positive signal. Never
    raises.
    """
    try:
        fe = _focused_element_from_capture(out)
        if not fe:
            return False
        subrole = (fe.get("subrole") or "").strip()
        role = (fe.get("role") or "").strip()
        if subrole == _SECURE_TEXT_SUBROLE:
            return True
        # Conservative belt: some helpers report only the redaction marker / a
        # secure role without the subrole. A redacted value on an editable text
        # field is the strongest "this is a password box" signal we have.
        if role == _SECURE_TEXT_ROLE and (fe.get("value") or "") == "[REDACTED]":
            return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("secure-input probe errored: %s", exc)
    return False
