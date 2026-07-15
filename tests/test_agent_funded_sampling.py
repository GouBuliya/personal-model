"""MCP Sampling-backed Personal Model inference."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from mcp import types
from mcp.server.session import ServerSession

from persome.config import Config
from persome.writer import llm as llm_mod
from persome.writer.agent_funded import (
    SamplingBridge,
    SamplingRequestCancelled,
    SamplingRequestTimeout,
    run_request_scoped,
    use_bridge,
)


class _FakeSession:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def create_message(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append({"messages": messages, **kwargs})
        return self.result


class _ValidatingServerSession(ServerSession):
    """Minimal ServerSession seam that retains the SDK's request validation."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[Any] = []
        self._client_params = SimpleNamespace(  # noqa: SLF001
            capabilities=types.ClientCapabilities(
                sampling=types.SamplingCapability(tools=types.SamplingToolsCapability())
            )
        )

    async def send_request(self, request, result_type, **kwargs):  # type: ignore[no-untyped-def]
        del result_type, kwargs
        self.requests.append(request)
        return self.result


class _BlockingSession:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.calls = 0

    async def create_message(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        del messages, kwargs
        self.calls += 1
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


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
    session = _ValidatingServerSession(result)

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
                        },
                        {
                            "id": "call-2",
                            "function": {"name": "search_memory", "arguments": "{}"},
                        },
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": '{"value": 1}'},
                {"role": "tool", "tool_call_id": "call-2", "content": '{"value": 2}'},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "read_memory",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "search_memory",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
            ],
            max_tokens=128,
        )

    asyncio.run(run())
    sent = session.requests[0].root.params.messages
    assert [block.type for block in sent[0].content] == ["tool_use", "tool_use"]
    assert [block.type for block in sent[1].content] == ["tool_result", "tool_result"]
    assert [block.toolUseId for block in sent[1].content] == ["call-1", "call-2"]


def test_sampling_timeout_cancels_pending_and_rejects_further_spend() -> None:
    async def run() -> None:
        session = _BlockingSession()
        bridge = SamplingBridge(
            loop=asyncio.get_running_loop(),
            session=session,
            timeout_seconds=0.01,
        )

        def complete() -> Any:
            return bridge.complete(
                messages=[{"role": "user", "content": "model this"}],
                tools=None,
                max_tokens=32,
            )

        with pytest.raises(SamplingRequestTimeout, match="exceeded"):
            await asyncio.to_thread(complete)
        await asyncio.wait_for(session.cancelled.wait(), timeout=1)
        assert bridge.cancel_reason == "sampling_timeout"
        with pytest.raises(SamplingRequestCancelled, match="sampling_timeout"):
            await asyncio.to_thread(complete)
        assert session.calls == 1

    asyncio.run(run())


def test_request_cancellation_cancels_pending_and_rejects_further_spend() -> None:
    async def run() -> None:
        session = _BlockingSession()
        bridge = SamplingBridge(loop=asyncio.get_running_loop(), session=session)

        def complete() -> Any:
            return bridge.complete(
                messages=[{"role": "user", "content": "model this"}],
                tools=None,
                max_tokens=32,
            )

        task = asyncio.create_task(run_request_scoped(bridge, complete))
        await asyncio.wait_for(session.started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(session.cancelled.wait(), timeout=1)
        assert bridge.cancel_reason == "request_cancelled"
        with pytest.raises(SamplingRequestCancelled, match="request_cancelled"):
            await asyncio.to_thread(complete)
        assert session.calls == 1

    asyncio.run(run())
