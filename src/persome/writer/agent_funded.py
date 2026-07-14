"""Bridge synchronous modeling stages to an originating MCP client's model.

MCP sampling is deliberately request-scoped: Persome never reads a client's
login token and never attempts background sampling without an originating MCP
request.  The synchronous writer runs in a worker thread while this bridge
marshals ``sampling/createMessage`` calls back onto the MCP session's event
loop.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class SamplingBridge:
    """Thread-safe facade over one connected MCP client session."""

    loop: asyncio.AbstractEventLoop
    session: Any
    timeout_seconds: float = 120.0

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        future = asyncio.run_coroutine_threadsafe(
            self._complete(messages=messages, tools=tools, max_tokens=max_tokens),
            self.loop,
        )
        return future.result(timeout=self.timeout_seconds)

    async def _complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> Any:
        from mcp import types

        from .llm import _build_response

        system_parts: list[str] = []
        sampling_messages: list[Any] = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                system_parts.append(_text(message.get("content")))
                continue

            content: list[Any] = []
            plain = _text(message.get("content"))
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
            elif role == "tool":
                content.append(
                    types.ToolResultContent(
                        type="tool_result",
                        toolUseId=str(message.get("tool_call_id") or ""),
                        content=[types.TextContent(type="text", text=plain)],
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
