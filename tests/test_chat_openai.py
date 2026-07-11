from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from persome.chat.agent import ChatAgent, complete_sync
from persome.chat.approvals import ToolApprovalContext
from persome.config import ChatConfig


def _openai_chat_config() -> ChatConfig:
    return ChatConfig(
        provider="openai",
        protocol="openai",
        model="gpt-4.1-mini",
        base_url="https://gateway.example/v1",
        api_key_env="OPENAI_API_KEY",
    )


class _Stream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __anext__(self):  # type: ignore[no-untyped-def]
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _chunk(*, content: str | None = None, tool_calls: list[Any] | None = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


@pytest.mark.asyncio
async def test_openai_chat_stream_executes_tools_and_persists_rounds(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    schema = {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Look up memory",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
    seen: list[dict[str, Any]] = []
    agent = ChatAgent(
        _openai_chat_config(),
        [schema],
        {"lookup": lambda args: seen.append(args) or {"answer": "remembered"}},
    )
    await agent.client.close()

    first = _Stream(
        [
            _chunk(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_1",
                        function=SimpleNamespace(name="lookup", arguments='{"query":"project"}'),
                    )
                ]
            )
        ]
    )
    second = _Stream([_chunk(content="I found it.")])

    class _FakeCompletions:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **kwargs: Any) -> _Stream:
            self.calls += 1
            assert kwargs["stream"] is True
            assert kwargs["tools"][0]["function"]["name"] == "lookup"
            return first if self.calls == 1 else second

    fake_completions = _FakeCompletions()

    class _FakeClient:
        chat = SimpleNamespace(completions=fake_completions)

        async def close(self) -> None:
            return None

    agent.client = _FakeClient()  # type: ignore[assignment]
    messages = [{"role": "user", "content": "What do you remember?"}]
    streamed: list[str] = []

    async def on_token(token: str) -> None:
        streamed.append(token)

    result = await agent.run_turn(messages, "Use memory tools.", on_token=on_token)
    await agent.aclose()

    assert result.error is None
    assert result.assistant_message == "I found it."
    assert streamed == ["I found it."]
    assert seen == [{"query": "project"}]
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert result.tool_calls_executed == [{"name": "lookup", "arguments": {"query": "project"}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_openai_chat_enforces_exact_tool_approval(monkeypatch, approved: bool) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    arguments = {"path": "/tmp/security-test", "content": "exact"}
    schema = {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "synthetic side effect",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    seen: list[dict[str, Any]] = []
    agent = ChatAgent(
        _openai_chat_config(),
        [schema],
        {"write_file": lambda args: seen.append(args) or {"written": True}},
        approval_required_tools={"write_file"},
    )
    await agent.client.close()

    first = _Stream(
        [
            _chunk(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_write",
                        function=SimpleNamespace(
                            name="write_file",
                            arguments=json.dumps(arguments),
                        ),
                    )
                ]
            )
        ]
    )
    second = _Stream([_chunk(content="Finished.")])

    class _FakeCompletions:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_kwargs: Any) -> _Stream:
            self.calls += 1
            return first if self.calls == 1 else second

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

        async def close(self) -> None:
            return None

    agent.client = _FakeClient()  # type: ignore[assignment]
    approval_context = ToolApprovalContext.for_call("write_file", arguments) if approved else None
    messages = [{"role": "user", "content": "write it"}]

    result = await agent.run_turn(
        messages,
        "system",
        approval_context=approval_context,
    )
    await agent.aclose()

    assert result.error is None
    tool_result = json.loads(messages[2]["content"])
    if approved:
        assert seen == [arguments]
        assert tool_result == {"written": True}
    else:
        assert seen == []
        assert tool_result["error"] == "approval_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_openai_external_mcp_tool_requires_exact_approval(
    monkeypatch, approved: bool
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    arguments = {"destination": "production", "release": "v1"}
    agent = ChatAgent(_openai_chat_config(), [], {})
    await agent.client.close()

    called: list[tuple[str, dict[str, Any]]] = []

    class _ExternalSession:
        async def call_tool(self, *, name: str, arguments: dict[str, Any]) -> Any:
            called.append((name, arguments))
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(text="published")],
            )

    external_session = _ExternalSession()
    agent._mcp_tool_specs = [
        (
            SimpleNamespace(
                name="publish_remote",
                description="synthetic remote side effect",
                inputSchema={"type": "object", "properties": {}},
            ),
            external_session,
        )
    ]

    first = _Stream(
        [
            _chunk(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_publish",
                        function=SimpleNamespace(
                            name="publish_remote",
                            arguments=json.dumps(arguments),
                        ),
                    )
                ]
            )
        ]
    )
    second = _Stream([_chunk(content="Done.")])

    class _FakeCompletions:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_kwargs: Any) -> _Stream:
            self.calls += 1
            return first if self.calls == 1 else second

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

        async def close(self) -> None:
            return None

    agent.client = _FakeClient()  # type: ignore[assignment]
    context = ToolApprovalContext.for_call("publish_remote", arguments) if approved else None
    messages = [{"role": "user", "content": "publish it"}]

    result = await agent.run_turn(messages, "system", approval_context=context)
    await agent.aclose()

    assert result.error is None
    tool_result = messages[2]["content"]
    if approved:
        assert tool_result == "published"
        assert called == [("publish_remote", arguments)]
    else:
        assert json.loads(tool_result)["error"] == "approval_required"
        assert called == []


def test_complete_sync_uses_openai_profile(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    captured: dict[str, Any] = {}

    class _FakeCompletions:
        def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))]
            )

    class _FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr("openai.OpenAI", _FakeClient)

    result = complete_sync(_openai_chat_config(), [{"role": "user", "content": "Summarize"}])

    assert result == "summary"
    assert captured["model"] == "gpt-4.1-mini"
    assert captured["client"]["base_url"] == "https://gateway.example/v1"
