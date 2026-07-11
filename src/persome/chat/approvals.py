"""Out-of-band, per-call approval capabilities for unsafe Chat tools.

The model never receives approval tokens and no tool schema accepts one.  A
trusted caller (CLI/API/UI) creates a :class:`ToolApprovalContext`, grants the
exact tool call the user approved, and passes that context to ``_run_turn``.
Grants are bound to the canonical arguments, expire quickly, and are consumed
once so a model cannot broaden or replay an approval.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any


def tool_call_digest(name: str, arguments: Mapping[str, Any]) -> str:
    """Return the stable digest to which an approval grant is bound."""
    canonical = json.dumps(
        {"name": name, "arguments": dict(arguments)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


@dataclass
class _ApprovalGrant:
    token: str
    tool_name: str
    call_digest: str
    expires_at: float
    consumed: bool = False


@dataclass(frozen=True)
class ToolApprovalRequest:
    """Exact call details shown only to a trusted approval surface."""

    tool_name: str
    arguments: dict[str, Any]
    call_digest: str


ApprovalCallback = Callable[[ToolApprovalRequest], bool]


class ToolApprovalContext:
    """A trusted, model-invisible collection of one-shot approval grants."""

    def __init__(self, approval_callback: ApprovalCallback | None = None) -> None:
        self._grants: list[_ApprovalGrant] = []
        self._lock = threading.Lock()
        self._callback_lock = threading.Lock()
        self._approval_callback = approval_callback

    @classmethod
    def with_callback(cls, approval_callback: ApprovalCallback) -> ToolApprovalContext:
        """Create a context that asks a trusted UI about each unmatched call."""
        return cls(approval_callback=approval_callback)

    @classmethod
    def for_call(
        cls,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        ttl_seconds: float = 120,
    ) -> ToolApprovalContext:
        """Create a context containing one approval for an exact tool call."""
        context = cls()
        context.approve_call(tool_name, arguments, ttl_seconds=ttl_seconds)
        return context

    @classmethod
    def for_calls(
        cls,
        calls: Iterable[tuple[str, Mapping[str, Any]]],
        *,
        ttl_seconds: float = 120,
    ) -> ToolApprovalContext:
        """Create a context for a trusted UI approving several exact calls."""
        context = cls()
        for tool_name, arguments in calls:
            context.approve_call(tool_name, arguments, ttl_seconds=ttl_seconds)
        return context

    def approve_call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        ttl_seconds: float = 120,
    ) -> str:
        """Add a one-shot grant and return its audit token to the trusted caller.

        The returned token is deliberately not part of tool arguments or denial
        results.  Possession of this context, not text emitted by the model, is
        what authorizes execution.
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        grant = _ApprovalGrant(
            token=secrets.token_urlsafe(24),
            tool_name=tool_name,
            call_digest=tool_call_digest(tool_name, arguments),
            expires_at=time.monotonic() + ttl_seconds,
        )
        with self._lock:
            self._grants.append(grant)
        return grant.token

    def consume(self, tool_name: str, arguments: Mapping[str, Any]) -> bool:
        """Consume one live grant matching the exact call, if present."""
        digest = tool_call_digest(tool_name, arguments)
        now = time.monotonic()
        with self._lock:
            for grant in self._grants:
                if grant.consumed or grant.expires_at < now:
                    continue
                if grant.tool_name != tool_name:
                    continue
                if not hmac.compare_digest(grant.call_digest, digest):
                    continue
                grant.consumed = True
                return True
        if self._approval_callback is not None:
            request = ToolApprovalRequest(tool_name, dict(arguments), digest)
            # Anthropic may execute parallel tools in worker threads.  A UI
            # approval surface must never interleave two confirmation prompts.
            with self._callback_lock:
                return bool(self._approval_callback(request))
        return False


def approval_required_result(name: str, arguments: Mapping[str, Any]) -> dict[str, str]:
    """Return a structured denial without leaking an approval capability."""
    return {
        "error": "approval_required",
        "tool": name,
        "call_digest": tool_call_digest(name, arguments),
        "message": "This exact tool call requires approval from a trusted user interface.",
    }


def execute_tool_handler(
    name: str,
    arguments: dict[str, Any],
    handler: Callable[[dict[str, Any]], Any],
    *,
    approval_required: bool,
    approval_context: ToolApprovalContext | None,
) -> Any:
    """Enforce approval immediately before invoking a static handler."""
    if approval_required and (
        approval_context is None or not approval_context.consume(name, arguments)
    ):
        return approval_required_result(name, arguments)
    return handler(arguments)
