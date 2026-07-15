"""Bridge synchronous modeling stages to an originating MCP client's model.

MCP sampling is deliberately request-scoped: Persome never reads a client's
login token and never attempts background sampling without an originating MCP
request.  The synchronous writer runs in a worker thread while this bridge
marshals ``sampling/createMessage`` calls back onto the MCP session's event
loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar

_T = TypeVar("_T")

_ACTIVE_BRIDGE: ContextVar[SamplingBridge | None] = ContextVar(
    "persome_agent_funded_bridge", default=None
)


def active_bridge() -> SamplingBridge | None:
    return _ACTIVE_BRIDGE.get()


@contextmanager
def use_bridge(bridge: SamplingBridge) -> Iterator[None]:
    token = _ACTIVE_BRIDGE.set(bridge)
    try:
        yield
    finally:
        _ACTIVE_BRIDGE.reset(token)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class SamplingRequestCancelled(RuntimeError):
    """The request-scoped Sampling bridge can no longer spend allowance."""


class SamplingRequestTimeout(SamplingRequestCancelled):
    """One client Sampling request exceeded the bridge deadline."""


@dataclass
class SamplingBridge:
    """Thread-safe facade over one connected MCP client session."""

    loop: asyncio.AbstractEventLoop
    session: Any
    timeout_seconds: float = 120.0
    _cancelled: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _pending_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _pending: set[concurrent.futures.Future[Any]] = field(
        default_factory=set, init=False, repr=False
    )
    _cancel_reason: str | None = field(default=None, init=False, repr=False)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def cancel_reason(self) -> str | None:
        with self._pending_lock:
            return self._cancel_reason

    def cancel(self, reason: str = "request_cancelled") -> None:
        """Reject future Sampling calls and cancel any currently pending one."""
        with self._pending_lock:
            if not self._cancelled.is_set():
                self._cancel_reason = reason
                self._cancelled.set()
            pending = tuple(self._pending)
        for future in pending:
            future.cancel()

    def _raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise SamplingRequestCancelled(
                f"MCP Sampling bridge cancelled: {self.cancel_reason or 'request_cancelled'}"
            )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        self._raise_if_cancelled()
        future = asyncio.run_coroutine_threadsafe(
            self._complete(messages=messages, tools=tools, max_tokens=max_tokens),
            self.loop,
        )
        with self._pending_lock:
            if self._cancelled.is_set():
                future.cancel()
                reason = self._cancel_reason or "request_cancelled"
            else:
                self._pending.add(future)
                reason = None
        if reason is not None:
            raise SamplingRequestCancelled(f"MCP Sampling bridge cancelled: {reason}")

        try:
            return future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            self.cancel("sampling_timeout")
            raise SamplingRequestTimeout(
                f"MCP Sampling request exceeded {self.timeout_seconds:g}s"
            ) from exc
        except concurrent.futures.CancelledError as exc:
            self.cancel(self.cancel_reason or "request_cancelled")
            raise SamplingRequestCancelled(
                f"MCP Sampling bridge cancelled: {self.cancel_reason or 'request_cancelled'}"
            ) from exc
        finally:
            with self._pending_lock:
                self._pending.discard(future)

    async def _complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        from mcp import types

        from .llm import _build_response

        self._raise_if_cancelled()
        system_parts: list[str] = []
        sampling_messages: list[Any] = []
        pending_tool_results: list[Any] = []

        def flush_tool_results() -> None:
            if not pending_tool_results:
                return
            sampling_messages.append(
                types.SamplingMessage(role="user", content=list(pending_tool_results))
            )
            pending_tool_results.clear()

        for message in messages:
            role = message.get("role")
            if role == "system":
                system_parts.append(_text(message.get("content")))
                continue

            plain = _text(message.get("content"))
            if role == "tool":
                pending_tool_results.append(
                    types.ToolResultContent(
                        type="tool_result",
                        toolUseId=str(message.get("tool_call_id") or ""),
                        content=[types.TextContent(type="text", text=plain)],
                    )
                )
                continue

            # SEP-1577 requires all results for one assistant tool-use turn to be
            # in one user message containing only tool_result blocks.
            flush_tool_results()
            content: list[Any] = []
            if plain:
                content.append(types.TextContent(type="text", text=plain))
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    raw = fn.get("arguments") or "{}"
                    try:
                        arguments = json.loads(raw) if isinstance(raw, str) else raw
                    except json.JSONDecodeError:
                        arguments = {}
                    content.append(
                        types.ToolUseContent(
                            type="tool_use",
                            id=str(call.get("id") or ""),
                            name=str(fn.get("name") or ""),
                            input=arguments if isinstance(arguments, dict) else {},
                        )
                    )
            if not content:
                content.append(types.TextContent(type="text", text=""))
            sampling_messages.append(
                types.SamplingMessage(
                    role="assistant" if role == "assistant" else "user",
                    content=content,
                )
            )
        flush_tool_results()

        sampling_tools = None
        if tools:
            sampling_tools = []
            for tool in tools:
                fn = tool.get("function") if tool.get("type") == "function" else tool
                fn = fn if isinstance(fn, dict) else {}
                sampling_tools.append(
                    types.Tool(
                        name=str(fn.get("name") or ""),
                        description=str(fn.get("description") or ""),
                        inputSchema=fn.get("parameters")
                        or fn.get("input_schema")
                        or {"type": "object", "properties": {}},
                    )
                )

        result = await self.session.create_message(
            sampling_messages,
            max_tokens=max_tokens,
            system_prompt="\n\n".join(system_parts) or None,
            tools=sampling_tools,
            tool_choice=types.ToolChoice(mode="auto") if sampling_tools else None,
        )
        blocks = result.content if isinstance(result.content, list) else [result.content]
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in blocks:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", None),
                        "function": {
                            "name": getattr(block, "name", ""),
                            "arguments": json.dumps(
                                getattr(block, "input", {}) or {}, ensure_ascii=False
                            ),
                        },
                    }
                )
        response = _build_response("\n".join(text_parts), tool_calls)
        stop_reason = str(getattr(result, "stopReason", "") or "")
        response.choices[0].finish_reason = {
            "maxTokens": "length",
            "toolUse": "tool_calls",
        }.get(stop_reason, "stop")
        return response


async def run_request_scoped(
    bridge: SamplingBridge,
    func: Callable[[], _T],
) -> _T:
    """Run synchronous work while tying its Sampling calls to this request."""
    try:
        return await asyncio.to_thread(func)
    except asyncio.CancelledError:
        bridge.cancel("request_cancelled")
        raise
    except BaseException:
        bridge.cancel("request_failed")
        raise
