"""Deterministic local provider and Rook MCP double for model-free ACP qualification."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import re
import selectors
import socket
import socketserver
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
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


def project_context_markers(body_text: str, goal_skill_path: Path | None = None) -> dict[str, bool]:
    goals = []
    try:
        for block in re.findall(r"<available_skills>.*?</available_skills>", body_text, re.DOTALL):
            goals.extend(skill for skill in ET.fromstring(block).findall("skill")
                         if skill.findtext("name") == "goal")
    except ET.ParseError:
        goals = []
    goal_present = (goal_skill_path is not None and len(goals) == 1
                    and goals[0].findtext("type") == "python"
                    and goals[0].findtext("python_import") == "goal"
                    and goals[0].findtext("location") == str(goal_skill_path))
    return {
        "globalSystemPresent": "ROOK_QUALIFICATION_GLOBAL_SYSTEM" in body_text,
        "goalSkillPresent": goal_present,
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


def _successful_echo(results: list[dict[str, Any]], call_id: str, value: str) -> bool:
    if len(results) != 1 or results[0].get("tool_call_id") != call_id or results[0].get("isError"):
        return False
    try:
        result = json.loads(_message_text(results[0]))
    except (ValueError, TypeError):
        return False
    return (type(result) is dict and result.get("success") is True
            and result == {"success": True, "data": {"echo": value}})


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
    tool_results = [item for item in subsequent if type(item) is dict and item.get("role") == "tool"]

    if "CANCEL_ME" in prompt:
        code = 'await mcp.call_tool("rook", "qualification_wait", {"value":"cancel"})'
        return _tool_call(code, "qualification-wait-1")
    if "PROVE_CONTEXT" in prompt:
        if not tool_results:
            code = ('import json\n'
                    'rook_result = await mcp.call_tool("rook", "qualification_echo", {"value":"reopen"})\n'
                    'print(json.dumps(rook_result, sort_keys=True))')
            return _tool_call(code, "qualification-reopen-1")
        if not _successful_echo(tool_results, "qualification-reopen-1", "reopen"):
            return _text("TOOL_FAILED: expected successful qualification_echo reopen result")
        prior = "\n".join(_message_text(item) for item in messages[:last_user])
        return _text("REOPEN_OK:FIRST_OK:alpha" if "FIRST_OK:alpha" in prior else "CONTEXT_MISSING")
    if "CREATE_AND_CALL_ROOK" in prompt:
        if tool_results:
            return _text("FIRST_OK:alpha" if _successful_echo(tool_results, "qualification-call-1", "alpha")
                         else "TOOL_FAILED: expected successful qualification_echo alpha result")
        quoted = repr(str(assigned_file))
        code = (
            "from pathlib import Path\nimport json\n"
            f"Path({quoted}).write_bytes(b'qualified\\n')\n"
            'rook_result = await mcp.call_tool("rook", "qualification_echo", {"value":"alpha"})\n'
            "print(json.dumps(rook_result, sort_keys=True))"
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
            last_user = next((item for item in reversed(request.get("messages", []))
                              if type(item) is dict and item.get("role") == "user"), None)
        except (UnicodeError, ValueError, json.JSONDecodeError, RuntimeError):
            self.send_error(400)
            return
        owner.journal.append(
            {
                "bodyBytes": len(body),
                "bodySha256": hashlib.sha256(body).hexdigest().upper(),
                "event": "provider_request",
                "lastUserSha256": hashlib.sha256(_message_text(last_user).encode("utf-8")).hexdigest().upper(),
                "messageRoles": [
                    item.get("role") for item in request.get("messages", []) if type(item) is dict
                ],
                "path": self.path,
                **project_context_markers("\n".join(_message_text(item) for item in request.get("messages", [])
                    if type(item) is dict and item.get("role") in {"system", "developer"}), owner.goal_skill_path),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self.wfile.flush()

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _OwnedRequestThreads(socketserver.ThreadingMixIn):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        # socketserver normally only prints request/dispatch failures. Journal writes
        # can themselves fail, so reporting to the owner must not depend on them.
        self.owner._failed.set()

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        except BaseException:
            # Includes request cleanup and non-Exception thread failures.
            self.owner._failed.set()

    def serve_forever(self, poll_interval=0.5):
        try:
            super().serve_forever(poll_interval)
        except BaseException:
            self.owner._failed.set()

    def process_request(self, request, client_address):
        self.request_threads = [(thread, sock) for thread, sock in getattr(self, "request_threads", [])
                                if thread.is_alive()]
        if len(self.request_threads) >= self.owner.journal.max_records:
            self.shutdown_request(request)
            raise RuntimeError("qualification request-thread limit exceeded")
        thread = threading.Thread(target=self.process_request_thread, args=(request, client_address), daemon=True)
        self.request_threads.append((thread, request))
        thread.start()

    def server_close(self):
        super().server_close()
        deadline = time.monotonic() + 5
        for thread, request in getattr(self, "request_threads", []):
            with contextlib.suppress(OSError):
                request.shutdown(socket.SHUT_RDWR)
            if thread.ident is not None:
                thread.join(timeout=max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread, _ in getattr(self, "request_threads", [])):
            raise RuntimeError("request thread shutdown remains unobserved")


class _ProviderServer(_OwnedRequestThreads, HTTPServer):
    pass


class DeterministicProviderServer:
    def __init__(
        self,
        url: str,
        assigned_file: Path,
        journal: BoundedJsonlJournal,
        *,
        goal_skill_path: Path | None = None,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None or parsed.path != "/v1":
            raise ValueError("deterministic provider URL is invalid")
        self.host = parsed.hostname
        self.port = parsed.port
        self.assigned_file = assigned_file
        self.goal_skill_path = goal_skill_path
        self.journal = journal
        self._server: _ProviderServer | None = None
        self._thread: threading.Thread | None = None
        self._failed = threading.Event()

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("deterministic provider is already started")
        server = _ProviderServer((self.host, self.port), _ProviderHandler)
        self._server = server
        try:
            server.owner = self  # type: ignore[attr-defined]
            self._thread = threading.Thread(target=server.serve_forever, name="rook-qualification-provider", daemon=True)
            self._thread.start()
            self.journal.append({"event": "provider_started", "host": self.host, "port": self.port})
        except BaseException as exc:
            self._failed.set()
            try:
                self.close()
            except BaseException as cleanup_error:
                exc.add_note(f"provider startup cleanup failed: {cleanup_error}")
            raise

    def close(self) -> None:
        if self._server is None:
            if self._failed.is_set():
                raise RuntimeError("qualification service failed")
            return
        started = self._thread is not None and self._thread.ident is not None
        if started:
            self._server.shutdown()
        self._server.server_close()
        if started:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError("provider thread shutdown remains unobserved")
        self._server = None
        self._thread = None
        try:
            self.journal.append({"event": "provider_stopped"})
        except BaseException:
            self._failed.set()
            raise
        if self._failed.is_set():
            raise RuntimeError("qualification service failed")

    def __enter__(self) -> "DeterministicProviderServer":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


def _forward_tunnel(
    left: socket.socket, right: socket.socket, stopping: threading.Event, failure_details: dict[str, Any]
) -> None:
    # At most 64 KiB pending per destination; pause its peer's reads under backpressure.
    limit = 64 * 1024
    peers = {left: right, right: left}
    pending = {left: bytearray(), right: bytearray()}
    eof: set[socket.socket] = set()
    write_closed: set[socket.socket] = set()
    sides = {left: "client", right: "upstream"}
    operation, side, direction = "set_nonblocking", "client", "none"
    socket_abort: ConnectionError | None = None
    try:
        for sock in peers:
            side = sides[sock]
            sock.setblocking(False)
        with selectors.DefaultSelector() as selector:
            while not stopping.is_set():
                for source in eof:
                    destination = peers[source]
                    if not pending[destination] and destination not in write_closed:
                        operation, side = "shutdown_write", sides[destination]
                        direction = f"{sides[source]}_to_{side}"
                        try:
                            destination.shutdown(socket.SHUT_WR)
                        except ConnectionError as exc:
                            socket_abort = exc
                            raise
                        write_closed.add(destination)
                if len(eof) == 2 and not any(pending.values()):
                    return
                operation, side, direction = "select", "both", "both"
                for sock, peer in peers.items():
                    events = selectors.EVENT_READ if sock not in eof and len(pending[peer]) < limit else 0
                    if pending[sock]:
                        events |= selectors.EVENT_WRITE
                    if sock in selector.get_map():
                        if events:
                            selector.modify(sock, events)
                        else:
                            selector.unregister(sock)
                    elif events:
                        selector.register(sock, events)
                for key, events in selector.select(timeout=0.25):
                    sock = key.fileobj
                    if events & selectors.EVENT_WRITE:
                        operation, side = "send", sides[sock]
                        direction = f"{sides[peers[sock]]}_to_{side}"
                        try:
                            sent = sock.send(pending[sock])
                        except ConnectionError as exc:
                            socket_abort = exc
                            raise
                        except (BlockingIOError, InterruptedError):
                            pass
                        else:
                            if sent <= 0:
                                raise OSError("proxy write made no progress")
                            del pending[sock][:sent]
                    if events & selectors.EVENT_READ:
                        operation, side = "recv", sides[sock]
                        direction = f"{side}_to_{sides[peers[sock]]}"
                        try:
                            data = sock.recv(limit - len(pending[peers[sock]]))
                        except ConnectionError as exc:
                            socket_abort = exc
                            raise
                        except (BlockingIOError, InterruptedError):
                            continue
                        if data:
                            pending[peers[sock]].extend(data)
                        else:
                            eof.add(sock)
            operation, side, direction = "stop", "both", "both"
            if any(pending.values()):
                raise OSError("proxy stopped with unsent bytes")
            raise OSError("proxy stopped before tunnel EOF")
    except OSError as exc:
        # Bounded transport facts only: an abort does not establish application success.
        failure_details.update(
            event="proxy_transport_aborted" if exc is socket_abort and not stopping.is_set() else "proxy_forward_failed",
            exceptionType=type(exc).__name__,
            operation=operation, socketSide=side, direction=direction,
            pendingBytes={"toClient": len(pending[left]), "toUpstream": len(pending[right])},
            eof={sides[sock]: sock in eof for sock in peers},
            writeClosed={sides[sock]: sock in write_closed for sock in peers},
            stopping=stopping.is_set(),
        )
        raise


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
            failure_details: dict[str, Any] = {
                "operation": "connect_response", "socketSide": "client", "direction": "proxy_to_client",
                # sendall may fail after partial progress on the CONNECT response.
                "pendingBytes": {"toClient": None, "toUpstream": 0},
                "eof": {"client": False, "upstream": False},
                "writeClosed": {"client": False, "upstream": False},
            }
            try:
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.wfile.flush()
                _forward_tunnel(self.connection, upstream, owner.stopping, failure_details)
            except OSError as exc:
                if owner.stopping.is_set():
                    failure_details.update(event="proxy_forward_failed", stopping=True)
                owner.journal.append({
                    "authority": authority, "detail": str(exc)[:512], "event": "proxy_forward_failed",
                    "stopping": owner.stopping.is_set(), **failure_details,
                    "errno": exc.errno, "winerror": getattr(exc, "winerror", None),
                })


class _ThreadingProxyServer(_OwnedRequestThreads, socketserver.TCPServer):
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
        self._failed = threading.Event()

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("qualification proxy is already started")
        server = _ThreadingProxyServer((self.host, self.port), _ProxyHandler)
        self._server = server
        try:
            server.owner = self  # type: ignore[attr-defined]
            self.port = int(server.server_address[1])
            self._thread = threading.Thread(target=server.serve_forever, name="rook-qualification-proxy", daemon=True)
            self._thread.start()
            self.journal.append({"event": "proxy_started", "host": self.host, "port": self.port})
        except BaseException as exc:
            self._failed.set()
            try:
                self.close()
            except BaseException as cleanup_error:
                exc.add_note(f"proxy startup cleanup failed: {cleanup_error}")
            raise

    def close(self) -> None:
        if self._server is None:
            if self._failed.is_set():
                raise RuntimeError("qualification service failed")
            return
        self.stopping.set()
        started = self._thread is not None and self._thread.ident is not None
        if started:
            self._server.shutdown()
        self._server.server_close()
        if started:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError("proxy thread shutdown remains unobserved")
        self._server = None
        self._thread = None
        try:
            self.journal.append({"event": "proxy_stopped"})
        except BaseException:
            self._failed.set()
            raise
        if self._failed.is_set():
            raise RuntimeError("qualification service failed")

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

        try:
            self._thread = threading.Thread(target=accept_connections, name="rook-daemon-tripwire", daemon=True)
            self._thread.start()
        except BaseException as exc:
            try:
                self.close()
            except BaseException as cleanup_error:
                exc.add_note(f"tripwire startup cleanup failed: {cleanup_error}")
            raise

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
        if self._thread is not None and self._thread.ident is not None:
            if self._thread.is_alive():
                wake = Client(self.path, family="AF_PIPE", authkey=None)
                wake.close()
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
