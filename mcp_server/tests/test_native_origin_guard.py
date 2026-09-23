"""The native HTTP server accepts only local Rook clients.

The C++ server binds 127.0.0.1 with an OS-assigned port. Any process running as
the user may call it, by design; nothing a web page does may reach it, because
several routes execute code or write files and a loopback server is reachable
from a browser tab through cross-origin "simple" requests, <img>/<script>
loads and navigations, none of which need a CORS preflight and not all of
which carry an Origin header (an Origin-only guard admitted an Origin-less GET).

Contract, enforced before routing:
  1. positive: every request must carry the X-Rook-Client header. A page can
     only add a custom header through a CORS-preflighted request, and the
     server never answers a preflight; <img>, <script>, forms and navigations
     cannot set headers at all. Rook's own clients send it.
  2. negative, defense in depth: requests carrying Origin or the browser-set
     fetch-metadata headers (Sec-Fetch-*) are rejected regardless.

Tests: a source scan that pins the contract in RookServer.cpp, a check that the
Python client factory sends the header, and a live check against a running
Rhino (``requires_rhino``) covering the Origin-less GET case.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from rook.bridge import NATIVE_CLIENT_HEADER, NATIVE_CLIENT_HEADERS, native_client

_NATIVE_SERVER = Path(__file__).resolve().parents[2] / "src" / "RookNative" / "RookServer.cpp"


def test_native_server_source_requires_client_header_and_rejects_browser_metadata():
    source = _NATIVE_SERVER.read_text(encoding="utf-8")
    assert 'kRookClientHeader = "X-Rook-Client"' in source
    guard = source.index("set_pre_routing_handler")
    routes = source.index("RegisterRoutes();")
    assert guard < routes, "the client gate must be installed before routes are registered"
    body = source[guard:routes]
    for needle in (
        'has_header("Origin")',
        'has_header("Sec-Fetch-Mode")',
        'has_header("Sec-Fetch-Site")',
        'has_header("Sec-Fetch-Dest")',
        "get_header_value(kRookClientHeader)",
        "res.status = 403",
        "browser_request_rejected",
        "client_header_required",
        "HandlerResponse::Handled",
        "HandlerResponse::Unhandled",
    ):
        assert needle in body, needle


def test_client_header_names_agree_across_python_cpp_and_csharp():
    assert NATIVE_CLIENT_HEADER == "X-Rook-Client"
    cs = (Path(__file__).resolve().parents[2] / "src" / "Rook" / "Services" / "Reconstruction" / "ReconstructionImportClient.cs").read_text(encoding="utf-8")
    assert 'NativeClientHeader = "X-Rook-Client"' in cs
    assert "TryAddWithoutValidation(NativeClientHeader" in cs


@pytest.mark.asyncio
async def test_native_client_factory_sends_the_header_on_every_request():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="pong")

    async with native_client(transport=httpx.MockTransport(handler), timeout=1.0) as client:
        await client.get("http://127.0.0.1:1/ping")
        await client.post("http://127.0.0.1:1/execute", json={"code": "1"})
        await client.request("DELETE", "http://127.0.0.1:1/x", headers={"Content-Type": "application/json"})
    assert len(seen) == 3
    for request in seen:
        assert request.headers.get(NATIVE_CLIENT_HEADER) == NATIVE_CLIENT_HEADERS[NATIVE_CLIENT_HEADER]
        assert "Origin" not in request.headers


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
def test_live_native_server_admits_only_rook_clients():
    port = _native_port_or_skip()
    base = f"http://127.0.0.1:{port}"
    browser_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
    with httpx.Client(timeout=10.0) as client:
        # Rook client: header present, no browser metadata -> served.
        ok = client.get(f"{base}/ping", headers=NATIVE_CLIENT_HEADERS)
        assert ok.status_code == 200

        # The review's case: an Origin-less GET exactly as an <img> or no-cors fetch
        # would send it (browser UA, fetch metadata, no custom header) -> refused.
        img_like = client.get(
            f"{base}/gh/canvas/image",
            headers={"User-Agent": browser_ua, "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Dest": "image", "Accept": "image/*"},
        )
        assert img_like.status_code == 403
        assert img_like.json()["error"] == "browser_request_rejected"

        # An Origin-less GET with NO metadata at all (old browser) and no client header -> refused.
        bare = client.get(f"{base}/gh/canvas/image", headers={"User-Agent": browser_ua})
        assert bare.status_code == 403
        assert bare.json()["error"] == "client_header_required"

        # A blind cross-origin "simple" POST (text/plain body, Origin set) -> refused.
        blind_post = client.post(
            f"{base}/execute",
            content='{"code": "print(1)"}',
            headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
        )
        assert blind_post.status_code == 403

        # Even with the client header, browser metadata is refused (defense in depth).
        marked = client.get(f"{base}/ping", headers={**NATIVE_CLIENT_HEADERS, "Origin": "http://127.0.0.1:1"})
        assert marked.status_code == 403
        assert marked.json()["error"] == "browser_request_rejected"
