"""Security boundaries for unsafe Chat tools."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from persome.chat import tool_handlers
from persome.chat.agent import _make_mcp_tracking_tool
from persome.chat.approvals import ToolApprovalContext, execute_tool_handler
from persome.chat.handler import _terminal_safe_json
from persome.chat.tools import CHAT_SCHEMAS


class _FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes = b"<html><title>ok</title><body>safe</body></html>",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.reason = "synthetic"
        self._body = body
        self._offset = 0
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.read_sizes: list[int] = []

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name.lower(), default)

    def read(self, amount: int) -> bytes:
        self.read_sizes.append(amount)
        chunk = self._body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk


class _FakeConnection:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, target, headers))

    def getresponse(self) -> _FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def _public_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
    return [(2, 1, 6, "", ("93.184.216.34", 80))]


def test_fetch_page_rejects_private_ip_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = False

    def fail_open(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal opened
        opened = True
        raise AssertionError("private destination must be rejected before connect")

    monkeypatch.setattr(tool_handlers, "_open_pinned_connection", fail_open)

    with pytest.raises(tool_handlers.UnsafeFetchError, match="non-public"):
        tool_handlers.tool_fetch_page({"url": "http://127.0.0.1/admin"})

    assert not opened


def test_fetch_page_rejects_hostname_resolving_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tool_handlers.socket,
        "getaddrinfo",
        lambda *_a, **_kw: [(2, 1, 6, "", ("10.20.30.40", 80))],
    )

    with pytest.raises(tool_handlers.UnsafeFetchError, match="non-public"):
        tool_handlers.tool_fetch_page({"url": "http://internal.example/secrets"})


def test_fetch_page_revalidates_public_to_private_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", _public_dns)
    redirect = _FakeResponse(
        status=302,
        headers={"Location": "http://169.254.169.254/latest/meta-data"},
    )
    connection = _FakeConnection(redirect)
    opened: list[tuple[str, str, int, str]] = []

    def fake_open(scheme: str, host: str, port: int, connect_ip: str, timeout: float) -> Any:
        del timeout
        opened.append((scheme, host, port, connect_ip))
        return connection

    monkeypatch.setattr(tool_handlers, "_open_pinned_connection", fake_open)

    with pytest.raises(tool_handlers.UnsafeFetchError, match="non-public"):
        tool_handlers.tool_fetch_page({"url": "https://public.example/start"})

    assert opened == [("https", "public.example", 443, "93.184.216.34")]
    assert connection.closed


def test_fetch_page_streams_and_rejects_oversized_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", _public_dns)
    response = _FakeResponse(body=b"x" * (tool_handlers._FETCH_MAX_RESPONSE_BYTES + 50_000))
    connection = _FakeConnection(response)
    monkeypatch.setattr(
        tool_handlers,
        "_open_pinned_connection",
        lambda *_a, **_kw: connection,
    )

    with pytest.raises(tool_handlers.UnsafeFetchError, match="response body exceeds"):
        tool_handlers.tool_fetch_page({"url": "http://public.example/large"})

    assert sum(response.read_sizes) <= tool_handlers._FETCH_MAX_RESPONSE_BYTES + 1
    assert max(response.read_sizes) <= tool_handlers._FETCH_READ_CHUNK_BYTES
    assert connection.closed


def test_fetch_page_pins_validated_dns_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    dns_calls = 0

    def rebinding_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        nonlocal dns_calls
        dns_calls += 1
        address = "93.184.216.34" if dns_calls == 1 else "127.0.0.1"
        return [(2, 1, 6, "", (address, 80))]

    monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", rebinding_dns)
    response = _FakeResponse(
        body=b"<html><title>Public</title><body>hello</body></html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
    connection = _FakeConnection(response)
    opened: list[tuple[str, str, int, str]] = []

    def fake_open(scheme: str, host: str, port: int, connect_ip: str, timeout: float) -> Any:
        del timeout
        opened.append((scheme, host, port, connect_ip))
        return connection

    monkeypatch.setattr(tool_handlers, "_open_pinned_connection", fake_open)

    result = tool_handlers.tool_fetch_page({"url": "http://public.example/page"})

    assert dns_calls == 1
    assert opened == [("http", "public.example", 80, "93.184.216.34")]
    assert result == {
        "url": "http://public.example/page",
        "title": "Public",
        "content": "Public\nhello",
    }


def test_fetch_page_allows_only_http_and_https() -> None:
    with pytest.raises(tool_handlers.UnsafeFetchError, match="http or https"):
        tool_handlers.tool_fetch_page({"url": "file:///etc/passwd"})


def test_safe_chat_handlers_clamp_resource_knobs(ac_root, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}
    monkeypatch.setattr(
        tool_handlers.fts,
        "recent",
        lambda _conn, *, since, limit: seen.update(recent=limit) or [],
    )
    monkeypatch.setattr(
        tool_handlers.captures_mod,
        "search_captures",
        lambda **kwargs: seen.update(captures=kwargs["limit"]) or [],
    )
    monkeypatch.setattr(
        tool_handlers.chat_history,
        "search_chat_history",
        lambda _query, limit: seen.update(history=limit) or [],
    )
    from persome.retrieval import associative

    monkeypatch.setattr(
        associative,
        "associative_read",
        lambda _conn, **kwargs: seen.update(memory=kwargs["top_k"]) or [],
    )

    tool_handlers.tool_recent_activity({"limit": -1})
    tool_handlers.tool_search_captures({"query": "x", "limit": -1})
    tool_handlers.tool_search_chat_history({"query": "x", "limit": 10**12})
    tool_handlers.tool_search_memory({"query": "x", "top_k": 10**12})

    assert seen == {"recent": 1, "captures": 1, "history": 50, "memory": 50}


def test_safe_chat_schema_declares_matching_resource_limits() -> None:
    schemas = {item["function"]["name"]: item["function"]["parameters"] for item in CHAT_SCHEMAS}

    top_k = schemas["search_memory"]["properties"]["top_k"]
    assert (top_k["minimum"], top_k["maximum"], top_k["default"]) == (1, 50, 5)
    assert schemas["recent_activity"]["properties"]["limit"]["maximum"] == 200
    assert schemas["search_captures"]["properties"]["limit"]["maximum"] == 50
    assert schemas["search_chat_history"]["properties"]["limit"]["maximum"] == 50
    assert schemas["read_memory"]["properties"]["tail_n"]["maximum"] == 500
    for tool, field in (
        ("search_memory", "query"),
        ("search_captures", "query"),
        ("search_chat_history", "query"),
    ):
        assert schemas[tool]["properties"][field]["maxLength"] == 20_000


def test_tool_approval_is_exact_single_use_and_model_invisible() -> None:
    calls: list[dict[str, Any]] = []
    args = {"path": "/tmp/approved.txt", "content": "approved"}
    context = ToolApprovalContext.for_call("write_file", args, ttl_seconds=60)

    def handler(payload: dict[str, Any]) -> dict[str, bool]:
        calls.append(payload)
        return {"ok": True}

    wrong = execute_tool_handler(
        "write_file",
        {**args, "content": "changed"},
        handler,
        approval_required=True,
        approval_context=context,
    )
    first = execute_tool_handler(
        "write_file",
        args,
        handler,
        approval_required=True,
        approval_context=context,
    )
    replay = execute_tool_handler(
        "write_file",
        args,
        handler,
        approval_required=True,
        approval_context=context,
    )

    assert wrong["error"] == "approval_required"
    assert first == {"ok": True}
    assert replay["error"] == "approval_required"
    assert calls == [args]
    assert "token" not in wrong
    assert "token" not in args


@pytest.mark.parametrize("control", ["\u202e", "\u2066", "\u009b", "\u2028"])
def test_approval_rendering_escapes_terminal_and_direction_controls(control: str) -> None:
    rendered = _terminal_safe_json(
        {"command": f"echo safe {control}; rm -rf ~/target"},
        indent=2,
    )

    assert control not in rendered
    assert f"\\u{ord(control):04x}" in rendered
    assert "rm -rf ~/target" in rendered


def test_tool_approval_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    times: Iterator[float] = iter([100.0, 102.0])
    monkeypatch.setattr("persome.chat.approvals.time.monotonic", lambda: next(times))
    context = ToolApprovalContext.for_call("run_command", {"command": "true"}, ttl_seconds=1)

    result = execute_tool_handler(
        "run_command",
        {"command": "true"},
        lambda _args: {"ok": True},
        approval_required=True,
        approval_context=context,
    )

    assert result["error"] == "approval_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_anthropic_external_mcp_tool_requires_exact_approval(approved: bool) -> None:
    arguments = {"channel": "ops", "message": "ship"}
    calls: list[tuple[str, dict[str, Any]]] = []

    class _Session:
        async def call_tool(self, *, name: str, arguments: dict[str, Any]) -> Any:
            calls.append((name, arguments))
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(text="sent")],
            )

    spec = SimpleNamespace(
        name="send_external_message",
        description="synthetic side effect",
        inputSchema={"type": "object", "properties": {}},
    )
    context = ToolApprovalContext.for_call("send_external_message", arguments) if approved else None
    tool = _make_mcp_tracking_tool(
        spec,
        _Session(),  # type: ignore[arg-type]
        approval_required=True,
        approval_context=context,
    )

    result = await tool.call(arguments)

    if approved:
        assert result == "sent"
        assert calls == [("send_external_message", arguments)]
    else:
        assert json.loads(result)["error"] == "approval_required"
        assert calls == []
