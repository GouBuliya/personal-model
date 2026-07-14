"""MCP Sampling-backed Personal Model inference."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from mcp import types

from persome.config import Config
from persome.writer import llm as llm_mod
from persome.writer.agent_funded import SamplingBridge, use_bridge


class _FakeSession:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def create_message(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append({"messages": messages, **kwargs})
        return self.result


def test_sampling_bridge_adapts_text_and_tool_calls() -> None:
    result = types.CreateMessageResultWithTools(
        role="assistant",
        model="client-owned-model",
        stopReason="toolUse",
        content=[
            types.TextContent(type="text", text="working"),
            types.ToolUseContent(
                type="tool_use",
                id="call-1",
                name="commit",
                input={"content": "durable fact"},
            ),
        ],
    )
    session = _FakeSession(result)

    async def run() -> Any:
        bridge = SamplingBridge(loop=asyncio.get_running_loop(), session=session)
        return await bridge._complete(  # noqa: SLF001 - direct async seam avoids thread deadlock
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "model this"},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "commit",
                        "description": "persist",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            max_tokens=256,
        )

    response = asyncio.run(run())
    assert llm_mod.extract_text(response) == "working"
    assert llm_mod.extract_tool_calls(response) == [
        {"id": "call-1", "name": "commit", "arguments": {"content": "durable fact"}}
    ]
    assert response.choices[0].finish_reason == "tool_calls"
    assert session.calls[0]["system_prompt"] == "system"
    assert session.calls[0]["tools"][0].name == "commit"


def test_call_llm_prefers_request_scoped_sampling_bridge(monkeypatch) -> None:
    monkeypatch.delenv("PERSOME_LLM_MOCK", raising=False)
    seen: dict[str, Any] = {}

    class _Bridge:
        def complete(self, **kwargs: Any) -> Any:
            seen.update(kwargs)
            return SimpleNamespace(source="sampling")

    with use_bridge(_Bridge()):  # type: ignore[arg-type]
        result = llm_mod.call_llm(
            Config(),
            "timeline",
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
        )

    assert result.source == "sampling"
    assert seen["messages"][0]["content"] == "hello"
    assert seen["max_tokens"] > 0


def test_sampling_bridge_round_trips_tool_results() -> None:
    result = types.CreateMessageResultWithTools(
        role="assistant",
        model="client-owned-model",
        stopReason="endTurn",
        content=types.TextContent(type="text", text=json.dumps({"ok": True})),
    )
    session = _FakeSession(result)

    async def run() -> None:
        bridge = SamplingBridge(loop=asyncio.get_running_loop(), session=session)
        await bridge._complete(  # noqa: SLF001
            messages=[
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "read_memory", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": '{"value": 1}'},
            ],
            tools=None,
            max_tokens=128,
        )

    asyncio.run(run())
    sent = session.calls[0]["messages"]
    assert sent[0].content[0].type == "tool_use"
    assert sent[1].content[1].type == "tool_result"
    assert sent[1].content[1].toolUseId == "call-1"
