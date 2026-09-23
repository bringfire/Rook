"""The native HTTP server must reject browser-originated requests.

The C++ server binds 127.0.0.1 with an OS-assigned port and has no client token:
any local process may call it, by design. A web page in the user's browser must
not be able to, even blind. Cross-origin "simple" requests (text/plain or form
POSTs) reach a loopback server without a CORS preflight and several routes
execute code, so the server rejects, before routing, every request that carries
an Origin header; browsers always attach one to such requests and Rook's own
clients never do.

Two tests: a source scan that pins the guard in RookServer.cpp (runs everywhere),
and a live check against a running Rhino (``requires_rhino``).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

_NATIVE_SERVER = Path(__file__).resolve().parents[2] / "src" / "RookNative" / "RookServer.cpp"


def test_native_server_source_rejects_origin_before_routing():
    source = _NATIVE_SERVER.read_text(encoding="utf-8")
    guard = source.index("set_pre_routing_handler")
    routes = source.index("RegisterRoutes();")
    assert guard < routes, "the Origin guard must be installed before routes are registered"
    body = source[guard:routes]
    assert 'has_header("Origin")' in body
    assert "res.status = 403" in body
    assert "cross_origin_request_rejected" in body
    assert "HandlerResponse::Handled" in body and "HandlerResponse::Unhandled" in body


def _native_port_or_skip() -> int:
    scoped = os.environ.get("ROOK_RHINO_PORT")
    if scoped:
        return int(scoped)
    from rook.bridge import discover_instances

    instances = [i for i in discover_instances() if i.get("pluginType") == "native"]
    if not instances:
        pytest.skip("no live Rhino native instance")
    return int(instances[0]["port"])


@pytest.mark.requires_rhino
def test_live_native_server_rejects_browser_origin_and_serves_local_clients():
    port = _native_port_or_skip()
    base = f"http://127.0.0.1:{port}"
    with httpx.Client(timeout=10.0) as client:
        ok = client.get(f"{base}/ping")
        assert ok.status_code == 200
        assert "Origin" not in ok.request.headers

        # A blind cross-origin "simple" POST from a web page: text/plain body, Origin set.
        blocked = client.post(
            f"{base}/execute",
            content='{"code": "print(1)"}',
            headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"] == "cross_origin_request_rejected"

        # Even a read-only route is refused when the request is browser-originated.
        blocked_get = client.get(f"{base}/ping", headers={"Origin": "http://127.0.0.1:1"})
        assert blocked_get.status_code == 403
