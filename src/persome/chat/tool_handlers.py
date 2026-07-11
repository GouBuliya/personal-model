"""Chat tool handlers — each takes the raw args dict and returns a Python object."""

from __future__ import annotations

import contextlib
import http.client
import ipaddress
import os
import re
import socket
import ssl
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urljoin, urlsplit

from ..mcp import captures as captures_mod
from ..mcp.limits import bounded_int, bounded_optional_text, bounded_text
from ..store import fts
from . import history as chat_history

# ─── memory tools ─────────────────────────────────────────────────────────


def tool_search_memory(args: dict[str, Any]) -> Any:
    from ..retrieval import associative as assoc_mod

    query = bounded_text("query", args["query"], maximum=20_000)
    top_k = bounded_int(args.get("top_k", 5), minimum=1, maximum=50)
    since = bounded_optional_text("since", args.get("since"), maximum=64)
    until = bounded_optional_text("until", args.get("until"), maximum=64)
    with fts.cursor() as conn:
        # §5 read cutover: the associative entrance (slot-less queries degrade to
        # search_hybrid byte-identically; kill-switch [search] associative_read_enabled)
        hits = assoc_mod.associative_read(
            conn,
            query=query,
            top_k=top_k,
            since=since,
            until=until,
        )
    return [
        {
            "id": h.id,
            "path": h.path,
            "timestamp": h.timestamp,
            "content": h.content,
            "rank": h.rank,
        }
        for h in hits
    ]


def tool_list_memories(args: dict[str, Any]) -> Any:
    limit = bounded_int(args.get("limit", 200), minimum=1, maximum=500)
    with fts.cursor() as conn:
        rows = fts.list_files(conn, limit=limit)
    return [
        {
            "path": r.path,
            "description": r.description,
            "tags": r.tags.split() if r.tags else [],
            "status": r.status,
            "entry_count": r.entry_count,
            "updated": r.updated,
        }
        for r in rows
    ]


def tool_read_memory(args: dict[str, Any]) -> Any:
    from ..store import files as files_mod

    memory_path = bounded_text("path", args["path"], maximum=512)
    p = files_mod.memory_path(memory_path)
    if not p.exists():
        return {"error": f"file not found: {memory_path}"}
    parsed = files_mod.read_file(p)
    entries = parsed.entries
    tail_n = (
        bounded_int(args["tail_n"], minimum=1, maximum=500)
        if args.get("tail_n") is not None
        else None
    )
    if tail_n is not None:
        entries = entries[-tail_n:]
    with fts.cursor() as conn:
        fts.increment_retrieval_counts(conn, (e.id for e in entries))
    return {
        "path": memory_path,
        "description": parsed.description,
        "tags": parsed.tags,
        "entries": [{"id": e.id, "timestamp": e.timestamp, "body": e.body} for e in entries],
    }


def tool_recent_activity(args: dict[str, Any]) -> Any:
    since = bounded_optional_text("since", args.get("since"), maximum=64)
    limit = bounded_int(args.get("limit", 20), minimum=1, maximum=200)
    with fts.cursor() as conn:
        hits = fts.recent(
            conn,
            since=since,
            limit=limit,
        )
    return [
        {
            "id": h.id,
            "path": h.path,
            "timestamp": h.timestamp,
            "content": h.content,
        }
        for h in hits
    ]


# ─── capture / context tools ──────────────────────────────────────────────


def tool_current_context(args: dict[str, Any]) -> Any:
    return captures_mod.current_context(
        app_filter=bounded_optional_text("app_filter", args.get("app_filter"), maximum=512),
    )


def tool_search_captures(args: dict[str, Any]) -> Any:
    return captures_mod.search_captures(
        query=bounded_text("query", args["query"], maximum=20_000),
        app_name=bounded_optional_text("app_name", args.get("app_name"), maximum=512),
        since=bounded_optional_text("since", args.get("since"), maximum=64),
        until=bounded_optional_text("until", args.get("until"), maximum=64),
        limit=bounded_int(args.get("limit", 10), minimum=1, maximum=50),
    )


# ─── file / shell tools ───────────────────────────────────────────────────


def tool_run_command(args: dict[str, Any]) -> Any:
    cwd = args.get("cwd") or str(Path.home())
    timeout = args.get("timeout", 30)
    try:
        # shell=True is intentional: this handler is invoked via LLM tool-call from
        # the local chat scope; users expect shell features (pipes, globs, $VAR).
        # Do not "harden" this to a list — that breaks the contract.
        proc = subprocess.run(
            args["command"],
            shell=True,  # noqa: S602
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "en_US.UTF-8"},
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-10000:] if len(proc.stdout) > 10000 else proc.stdout,
            "stderr": proc.stderr[-5000:] if len(proc.stderr) > 5000 else proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}


def tool_read_file(args: dict[str, Any]) -> Any:
    p = Path(args["path"]).expanduser()
    if not p.exists():
        return {"error": f"file not found: {args['path']}"}
    if not p.is_file():
        return {"error": f"not a file: {args['path']}"}
    text = p.read_text(errors="replace")
    lines = text.splitlines(keepends=True)
    offset = args.get("offset", 1) - 1
    limit = args.get("limit", len(lines))
    selected = lines[max(0, offset) : offset + limit]
    numbered = "".join(f"{i + offset + 1:>5} | {line}" for i, line in enumerate(selected))
    return {
        "path": str(p),
        "total_lines": len(lines),
        "showing": f"{offset + 1}-{offset + len(selected)}",
        "content": numbered[-20000:],
    }


def tool_write_file(args: dict[str, Any]) -> Any:
    p = Path(args["path"]).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(args["content"])
    return {"path": str(p), "bytes_written": len(args["content"])}


def tool_edit_file(args: dict[str, Any]) -> Any:
    p = Path(args["path"]).expanduser()
    if not p.exists():
        return {"error": f"file not found: {args['path']}"}
    text = p.read_text()
    old = args["old_string"]
    if old not in text:
        return {"error": "old_string not found in file"}
    count = text.count(old)
    if count > 1:
        return {"error": f"old_string found {count} times, must be unique"}
    new_text = text.replace(old, args["new_string"], 1)
    p.write_text(new_text)
    return {"path": str(p), "replaced": True}


def tool_grep_search(args: dict[str, Any]) -> Any:
    search_path = args.get("path", ".")
    cmd = ["grep", "-rn", "--color=never"]
    if args.get("include"):
        cmd.extend(["--include", args["include"]])
    cmd.extend([args["pattern"], search_path])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(Path.home()),
        )
        all_lines = proc.stdout.strip().splitlines()
        lines = all_lines[:50]
        return {
            "matches": lines,
            "count": len(lines),
            "truncated": len(all_lines) > 50,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Search timed out"}


def tool_list_dir(args: dict[str, Any]) -> Any:
    p = Path(args.get("path", ".")).expanduser()
    if not p.exists():
        return {"error": f"path not found: {p}"}
    entries = []
    for item in sorted(p.iterdir()):
        if item.name.startswith("."):
            continue
        kind = "dir" if item.is_dir() else "file"
        size = item.stat().st_size if item.is_file() else None
        entries.append({"name": item.name, "type": kind, "size": size})
    return {"path": str(p), "entries": entries[:100]}


# ─── web tools ────────────────────────────────────────────────────────────


def tool_web_search(args: dict[str, Any]) -> Any:
    from ddgs import DDGS

    with DDGS() as ddgs:
        raw = list(ddgs.text(args["query"], max_results=args.get("max_results", 5)))
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in raw
    ]


_FETCH_MAX_REDIRECTS = 5
_FETCH_MAX_RESPONSE_BYTES = 1_048_576
_FETCH_READ_CHUNK_BYTES = 65_536
_FETCH_MAX_TEXT_CHARS = 100_000
_FETCH_TIMEOUT_SECONDS = 15.0
_FETCH_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_FETCH_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Persome/0.1"


class UnsafeFetchError(ValueError):
    """The requested page violated Chat's outbound-fetch security policy."""


def _is_non_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return _is_non_public_address(address.ipv4_mapped)
    return (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _parse_fetch_url(raw_url: str) -> tuple[SplitResult, str, int]:
    if not isinstance(raw_url, str) or not raw_url:
        raise UnsafeFetchError("fetch_page URL must be a non-empty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_url):
        raise UnsafeFetchError("fetch_page URL contains control characters")
    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeFetchError("fetch_page URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeFetchError("fetch_page URL must not contain user credentials")
    host = parsed.hostname
    if not host:
        raise UnsafeFetchError("fetch_page URL must contain a host")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeFetchError("fetch_page URL contains an invalid port") from exc
    return parsed, host, port


def _resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    """Resolve once, reject any unsafe answer, and return addresses to pin."""
    literal = host.split("%", 1)[0]
    try:
        addresses = (str(ipaddress.ip_address(literal)),)
    except ValueError:
        try:
            records = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except socket.gaierror as exc:
            raise UnsafeFetchError(f"fetch_page DNS resolution failed for {host}") from exc
        addresses = tuple(dict.fromkeys(str(record[4][0]).split("%", 1)[0] for record in records))
    if not addresses:
        raise UnsafeFetchError(f"fetch_page DNS resolution returned no addresses for {host}")
    for resolved in addresses:
        try:
            address = ipaddress.ip_address(resolved)
        except ValueError as exc:
            raise UnsafeFetchError("fetch_page DNS returned an invalid address") from exc
        if _is_non_public_address(address):
            raise UnsafeFetchError(f"fetch_page refuses non-public destination address {address}")
    return addresses


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection whose TCP peer is the address already policy-checked."""

    def __init__(self, host: str, port: int, connect_ip: str, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._connect_ip = connect_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._connect_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to an IP while retaining hostname TLS checks."""

    def __init__(self, host: str, port: int, connect_ip: str, timeout: float) -> None:
        context = ssl.create_default_context()
        super().__init__(host, port=port, timeout=timeout, context=context)
        self._connect_ip = connect_ip
        self._tls_context = context

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._connect_ip, self.port), self.timeout)
        try:
            self.sock = self._tls_context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _open_pinned_connection(
    scheme: str,
    host: str,
    port: int,
    connect_ip: str,
    timeout: float,
) -> http.client.HTTPConnection:
    connection_cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    return connection_cls(host, port, connect_ip, timeout)


def _read_fetch_body(response: http.client.HTTPResponse) -> bytes:
    content_length = response.getheader("Content-Length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = -1
        if declared_length > _FETCH_MAX_RESPONSE_BYTES:
            raise UnsafeFetchError(
                f"fetch_page response body exceeds {_FETCH_MAX_RESPONSE_BYTES} bytes"
            )

    content_encoding = (response.getheader("Content-Encoding") or "identity").lower()
    if content_encoding not in {"", "identity"}:
        raise UnsafeFetchError("fetch_page refuses encoded response bodies")

    chunks: list[bytes] = []
    received = 0
    while True:
        remaining_probe = _FETCH_MAX_RESPONSE_BYTES + 1 - received
        if remaining_probe <= 0:
            raise UnsafeFetchError(
                f"fetch_page response body exceeds {_FETCH_MAX_RESPONSE_BYTES} bytes"
            )
        chunk = response.read(min(_FETCH_READ_CHUNK_BYTES, remaining_probe))
        if not chunk:
            break
        received += len(chunk)
        if received > _FETCH_MAX_RESPONSE_BYTES:
            raise UnsafeFetchError(
                f"fetch_page response body exceeds {_FETCH_MAX_RESPONSE_BYTES} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _fetch_page_bytes(raw_url: str) -> tuple[str, bytes, str]:
    """Fetch a page with per-hop validation and a DNS-pinned TCP connection."""
    current_url = raw_url
    for redirect_count in range(_FETCH_MAX_REDIRECTS + 1):
        parsed, host, port = _parse_fetch_url(current_url)
        addresses = _resolve_public_addresses(host, port)
        # Every DNS answer was validated.  Pin the actual TCP connection to
        # the first answer so a second resolver lookup cannot rebind the host.
        connection = _open_pinned_connection(
            parsed.scheme.lower(),
            host,
            port,
            addresses[0],
            _FETCH_TIMEOUT_SECONDS,
        )
        target = parsed.path or "/"
        if parsed.query:
            target += f"?{parsed.query}"
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "User-Agent": _FETCH_USER_AGENT,
                    "Accept": "text/html, text/plain;q=0.9, */*;q=0.1",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if response.status in _FETCH_REDIRECT_STATUSES:
                location = response.getheader("Location")
                if not location:
                    raise UnsafeFetchError("fetch_page redirect has no Location header")
                if redirect_count >= _FETCH_MAX_REDIRECTS:
                    raise UnsafeFetchError("fetch_page exceeded redirect limit")
                # The next loop validates scheme, DNS, and every returned IP
                # before opening a connection to the redirect target.
                current_url = urljoin(current_url, location)
                continue
            if response.status >= 400:
                raise UnsafeFetchError(
                    f"fetch_page HTTP error {response.status} {response.reason or ''}".strip()
                )
            body = _read_fetch_body(response)
            content_type = response.getheader("Content-Type") or ""
            return current_url, body, content_type
        finally:
            connection.close()
    raise UnsafeFetchError("fetch_page exceeded redirect limit")


def _response_charset(content_type: str) -> str:
    match = re.search(r"charset\s*=\s*['\"]?([^;'\"\s]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def tool_fetch_page(args: dict[str, Any]) -> Any:
    from bs4 import BeautifulSoup

    max_len = int(args.get("max_length", 10000))
    if not 1 <= max_len <= _FETCH_MAX_TEXT_CHARS:
        raise UnsafeFetchError(
            f"fetch_page max_length must be between 1 and {_FETCH_MAX_TEXT_CHARS}"
        )
    final_url, body, content_type = _fetch_page_bytes(args["url"])
    try:
        decoded = body.decode(_response_charset(content_type), errors="replace")
    except LookupError:
        decoded = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(decoded, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)
    if len(text) > max_len:
        text = text[:max_len] + "\n...(truncated)"
    return {
        "url": final_url,
        "title": soup.title.get_text(strip=True) if soup.title else "",
        "content": text,
    }


# ─── chat-history tools ───────────────────────────────────────────────────


def tool_search_chat_history(args: dict[str, Any]) -> Any:
    return chat_history.search_chat_history(
        bounded_text("query", args["query"], maximum=20_000),
        bounded_int(args.get("limit", 10), minimum=1, maximum=50),
    )


def tool_list_chat_sessions(args: dict[str, Any]) -> Any:
    limit = bounded_int(args.get("limit", 20), minimum=1, maximum=200)
    return chat_history.list_chat_sessions(limit=limit)


# ─── registry ─────────────────────────────────────────────────────────────


def tool_set_user_name(args: dict[str, Any]) -> Any:

    name = (args.get("name") or "").strip()
    if not name:
        return {"error": "name cannot be empty"}

    from ..store import entries as entries_mod
    from ..store import fts

    profile_name = "user-profile"
    with fts.cursor() as conn:
        with contextlib.suppress(FileExistsError):
            entries_mod.create_file(
                conn,
                name=profile_name,
                description="User's identity, background, and long-term stable basic information",
                tags=["identity", "background"],
            )
        entries_mod.append_entry(
            conn,
            name=profile_name,
            content=f"Name: {name}",
            tags=["identity", "name"],
        )
    return {"ok": True, "name": name}


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "set_user_name": tool_set_user_name,
    "search_memory": tool_search_memory,
    "list_memories": tool_list_memories,
    "read_memory": tool_read_memory,
    "recent_activity": tool_recent_activity,
    "current_context": tool_current_context,
    "search_captures": tool_search_captures,
    "run_command": tool_run_command,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "grep_search": tool_grep_search,
    "list_dir": tool_list_dir,
    "web_search": tool_web_search,
    "fetch_page": tool_fetch_page,
    "search_chat_history": tool_search_chat_history,
    "list_chat_sessions": tool_list_chat_sessions,
}
