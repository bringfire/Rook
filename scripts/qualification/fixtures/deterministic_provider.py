"""Deterministic local provider and Rook MCP double for model-free ACP qualification."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import selectors
import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse


MAX_PROVIDER_REQUEST_BYTES = 1024 * 1024
CONNECT_PATTERN = re.compile(r"([A-Za-z0-9.-]+):(\d{1,5})")


class BoundedJsonlJournal:
    def __init__(self, path: Path, *, max_records: int, max_bytes: int) -> None:
        if max_records <= 0 or max_bytes <= 0:
            raise ValueError("journal bounds must be positive")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb"):
            pass
        self.path = path
        self.max_records = max_records
        self.max_bytes = max_bytes
        self._records = 0
        self._bytes = 0
        self._lock = threading.Lock()

    def append(self, value: dict[str, Any]) -> None:
        wire = (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8", "strict")
        with self._lock:
            if self._records >= self.max_records:
                raise RuntimeError("journal record limit exceeded")
            if self._bytes + len(wire) > self.max_bytes:
                raise RuntimeError("journal byte limit exceeded")
            with self.path.open("ab") as stream:
                stream.write(wire)
                stream.flush()
            self._records += 1
            self._bytes += len(wire)


def _message_text(message: object) -> str:
    if type(message) is not dict:
        return ""
    content = message.get("content")
    if type(content) is str:
        return content
    if type(content) is list:
        return "\n".join(
            item.get("text", "")
            for item in content
            if type(item) is dict and type(item.get("text")) is str
        )
    return ""


def project_context_markers(body_text: str) -> dict[str, bool]:
    return {
        "globalSystemPresent": "ROOK_QUALIFICATION_GLOBAL_SYSTEM" in body_text,
        "goalSkillPresent": "completion_budget_report" in body_text,
        "hostileMarkerPresent": "ROOK_QUALIFICATION_HOSTILE_PROJECT_RESOURCE" in body_text,
        "rookContractPresent": "# RookChat Operating Contract" in body_text,
    }


def _chunk(delta: dict[str, Any], finish_reason: str | None) -> dict[str, Any]:
    return {
        "choices": [{"delta": delta, "finish_reason": finish_reason, "index": 0}],
        "created": 0,
        "id": "rookchat-prime-acp-deterministic",
        "model": "qualification/deterministic",
        "object": "chat.completion.chunk",
    }


def _tool_call(code: str, call_id: str) -> list[dict[str, Any]]:
    return [
        _chunk(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "arguments": json.dumps({"code": code}, separators=(",", ":")),
                            "name": "ipython",
                        },
                        "id": call_id,
                        "index": 0,
                        "type": "function",
                    }
                ],
            },
            "tool_calls",
        )
    ]


def _text(value: str) -> list[dict[str, Any]]:
    return [
        _chunk({"content": value, "role": "assistant"}, None),
        {
            **_chunk({}, "stop"),
            "usage": {
                "completion_tokens": 1,
                "prompt_tokens": 1,
                "total_tokens": 2,
            },
        },
    ]


def plan_openai_response(request: dict[str, Any], assigned_file: Path) -> list[dict[str, Any]]:
    messages = request.get("messages")
    if type(messages) is not list:
        return _text("INVALID_REQUEST")
    user_indexes = [index for index, item in enumerate(messages) if type(item) is dict and item.get("role") == "user"]
    if not user_indexes:
        return _text("NO_USER_MESSAGE")
    last_user = user_indexes[-1]
    prompt = _message_text(messages[last_user])
    subsequent = messages[last_user + 1 :]

    if "CANCEL_ME" in prompt:
        code = 'await mcp.call_tool("rook", "qualification_wait", {"value":"cancel"})'
        return _tool_call(code, "qualification-wait-1")
    if "PROVE_CONTEXT" in prompt:
        tool_result = any(type(item) is dict and item.get("role") == "tool" for item in subsequent)
        if not tool_result:
            code = 'await mcp.call_tool("rook", "qualification_echo", {"value":"reopen"})'
            return _tool_call(code, "qualification-reopen-1")
        prior = "\n".join(_message_text(item) for item in messages[:last_user])
        return _text("REOPEN_OK:FIRST_OK:alpha" if "FIRST_OK:alpha" in prior else "CONTEXT_MISSING")
    if "CREATE_AND_CALL_ROOK" in prompt:
        tool_result = any(type(item) is dict and item.get("role") == "tool" for item in subsequent)
        if tool_result:
            return _text("FIRST_OK:alpha")
        quoted = repr(str(assigned_file))
        code = (
            "from pathlib import Path\n"
            f"Path({quoted}).write_text('qualified\\n', encoding='utf-8')\n"
            'rook_result = await mcp.call_tool("rook", "qualification_echo", {"value":"alpha"})\n'
            "print(rook_result)"
        )
        return _tool_call(code, "qualification-call-1")
    return _text("UNEXPECTED_PROMPT")


def encode_sse(chunks: Sequence[dict[str, Any]]) -> bytes:
    rows = [
        "data: " + json.dumps(chunk, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n\n"
        for chunk in chunks
    ]
    rows.append("data: [DONE]\n\n")
    return "".join(rows).encode("utf-8", "strict")


def qualification_echo(arguments: dict[str, Any]) -> dict[str, Any]:
    if set(arguments) != {"value"} or type(arguments["value"]) is not str:
        raise ValueError("qualification_echo arguments are invalid")
    return {"success": True, "data": {"echo": arguments["value"]}}


def admit_connect_authority(authority: str, admitted_hosts: set[str]) -> tuple[str, int]:
    if type(authority) is not str or CONNECT_PATTERN.fullmatch(authority) is None:
        raise ValueError("CONNECT authority is invalid")
    host_value, port_value = authority.rsplit(":", 1)
    host = host_value.lower()
    port = int(port_value)
    if port != 443 or host not in admitted_hosts:
        raise ValueError("CONNECT authority is not admitted")
    return host, port


class _ProviderHandler(BaseHTTPRequestHandler):
    server_version = "RookQualificationProvider/1"

    def do_POST(self) -> None:
        owner: DeterministicProviderServer = self.server.owner  # type: ignore[attr-defined]
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            declared = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            declared = -1
        if declared < 0 or declared > MAX_PROVIDER_REQUEST_BYTES:
            self.send_error(413)
            return
        body = self.rfile.read(declared)
        if len(body) != declared:
            self.send_error(413)
            return
        try:
            body_text = body.decode("utf-8", "strict")
            request = json.loads(body_text)
            if type(request) is not dict:
                raise ValueError("request is not an object")
            response = encode_sse(plan_openai_response(request, owner.assigned_file))
            owner.journal.append(
                {
                    "bodyBytes": len(body),
                    "bodySha256": hashlib.sha256(body).hexdigest().upper(),
                    "event": "provider_request",
                    "messageRoles": [
                        item.get("role") for item in request.get("messages", []) if type(item) is dict
                    ],
                    "path": self.path,
                    **project_context_markers(body_text),
                }
            )
        except (UnicodeError, ValueError, json.JSONDecodeError, RuntimeError):
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self.wfile.flush()

    def log_message(self, _format: str, *_args: object) -> None:
        return


class DeterministicProviderServer:
    def __init__(
        self,
        url: str,
        assigned_file: Path,
        journal: BoundedJsonlJournal,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None or parsed.path != "/v1":
            raise ValueError("deterministic provider URL is invalid")
        self.host = parsed.hostname
        self.port = parsed.port
        self.assigned_file = assigned_file
        self.journal = journal
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("deterministic provider is already started")
        server = ThreadingHTTPServer((self.host, self.port), _ProviderHandler)
        server.owner = self  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, name="rook-qualification-provider", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        self.journal.append({"event": "provider_started", "host": self.host, "port": self.port})

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.journal.append({"event": "provider_stopped"})
        self._server = None
        self._thread = None

    def __enter__(self) -> "DeterministicProviderServer":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


class _ProxyHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        owner: ConnectProxyServer = self.server.owner  # type: ignore[attr-defined]
        try:
            first = self.rfile.readline(16 * 1024 + 1)
            if len(first) > 16 * 1024:
                raise ValueError("proxy header exceeds byte limit")
            parts = first.decode("ascii", "strict").strip().split(" ")
            if len(parts) != 3 or parts[0] != "CONNECT":
                raise ValueError("proxy accepts CONNECT only")
            authority = parts[1]
            total = len(first)
            while True:
                line = self.rfile.readline(16 * 1024 + 1)
                total += len(line)
                if total > 16 * 1024:
                    raise ValueError("proxy header exceeds byte limit")
                if line in {b"\r\n", b"\n", b""}:
                    break
            host, port = admit_connect_authority(authority, owner.admitted_hosts)
        except (UnicodeError, ValueError) as exc:
            owner.journal.append(
                {
                    "authority": locals().get("authority", ""),
                    "detail": str(exc),
                    "event": "proxy_refused",
                }
            )
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            self.wfile.flush()
            return

        owner.journal.append({"authority": authority, "event": "proxy_admitted", "host": host, "port": port})
        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError as exc:
            owner.journal.append({"authority": authority, "detail": str(exc), "event": "proxy_connect_failed"})
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            self.wfile.flush()
            return
        with upstream:
            self.connection.setblocking(False)
            upstream.setblocking(False)
            self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.wfile.flush()
            selector = selectors.DefaultSelector()
            selector.register(self.connection, selectors.EVENT_READ, upstream)
            selector.register(upstream, selectors.EVENT_READ, self.connection)
            try:
                while not owner.stopping.is_set():
                    events = selector.select(timeout=0.25)
                    for key, _ in events:
                        try:
                            data = key.fileobj.recv(64 * 1024)
                        except (BlockingIOError, ConnectionResetError, OSError):
                            return
                        if not data:
                            return
                        key.data.sendall(data)
            finally:
                selector.close()


class _ThreadingProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True


class ConnectProxyServer:
    def __init__(self, url: str, admitted_hosts: set[str], journal: BoundedJsonlJournal) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None or parsed.path not in {"", "/"}:
            raise ValueError("qualification proxy URL is invalid")
        if set(admitted_hosts) != admitted_hosts or not admitted_hosts:
            raise ValueError("qualification proxy allowlist is invalid")
        self.host = parsed.hostname
        self.port = parsed.port
        self.admitted_hosts = admitted_hosts
        self.journal = journal
        self.stopping = threading.Event()
        self._server: _ThreadingProxyServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        server = _ThreadingProxyServer((self.host, self.port), _ProxyHandler)
        server.owner = self  # type: ignore[attr-defined]
        self.port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, name="rook-qualification-proxy", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        self.journal.append({"event": "proxy_started", "host": self.host, "port": self.port})

    def close(self) -> None:
        if self._server is None:
            return
        self.stopping.set()
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.journal.append({"event": "proxy_stopped"})
        self._server = None
        self._thread = None

    def __enter__(self) -> "ConnectProxyServer":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


class NamedPipeTripwire:
    def __init__(self, path: str) -> None:
        if not path.startswith("\\\\.\\pipe\\") or "\0" in path:
            raise ValueError("daemon tripwire path is invalid")
        self.path = path
        self.contact_count = 0
        self._listener: Listener | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._condition = threading.Condition()
        self._failure: BaseException | None = None

    def start(self) -> None:
        if self._listener is not None:
            raise RuntimeError("daemon tripwire is already started")
        self._listener = Listener(self.path, family="AF_PIPE", authkey=None)

        def accept_connections() -> None:
            try:
                while True:
                    connection = self._listener.accept()
                    connection.close()
                    if self._stopping.is_set():
                        return
                    with self._condition:
                        self.contact_count += 1
                        self._condition.notify_all()
            except BaseException as exc:
                if not self._stopping.is_set():
                    self._failure = exc
                    with self._condition:
                        self._condition.notify_all()

        self._thread = threading.Thread(target=accept_connections, name="rook-daemon-tripwire", daemon=True)
        self._thread.start()

    def wait_for_contacts(self, count: int, *, timeout_seconds: float) -> None:
        with self._condition:
            reached = self._condition.wait_for(
                lambda: self.contact_count >= count or self._failure is not None,
                timeout=timeout_seconds,
            )
        if self._failure is not None:
            raise RuntimeError("daemon tripwire failed") from self._failure
        if not reached or self.contact_count < count:
            raise TimeoutError("daemon tripwire contact was not observed")

    def close(self) -> None:
        if self._listener is None:
            return
        self._stopping.set()
        wake = Client(self.path, family="AF_PIPE", authkey=None)
        wake.close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError("daemon tripwire did not stop")
        self._listener.close()
        self._listener = None
        self._thread = None

    def __enter__(self) -> "NamedPipeTripwire":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


async def _run_rook_mcp(journal: BoundedJsonlJournal) -> None:
    from mcp import types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    server = Server("rook-qualification")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        journal.append({"event": "mcp_list_tools"})
        return [
            types.Tool(
                name="qualification_echo",
                description="Return one deterministic Rook success envelope.",
                inputSchema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            ),
            types.Tool(
                name="qualification_wait",
                description="Wait until the owning ACP lifecycle cancels this server.",
                inputSchema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        journal.append({"arguments": arguments, "event": "mcp_call_started", "name": name})
        if name == "qualification_echo":
            result = qualification_echo(arguments)
            journal.append({"event": "mcp_call_finished", "name": name})
            return result
        if name == "qualification_wait":
            await asyncio.Event().wait()
        raise ValueError("unknown qualification tool")

    journal.append({"event": "mcp_process_started"})
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--rook-mcp", action="store_true")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--max-records", type=int, required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args(argv)
    if not args.rook_mcp:
        parser.error("--rook-mcp is required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    journal = BoundedJsonlJournal(args.journal, max_records=args.max_records, max_bytes=args.max_bytes)
    try:
        asyncio.run(_run_rook_mcp(journal))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
