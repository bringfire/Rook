"""The native HTTP server accepts only local Rook clients.

The C++ server binds 127.0.0.1 with an OS-assigned port. Any process running as
the user may call it, by design; nothing a web page does may reach it, because
several routes execute code or write files and a loopback server is reachable
from a browser tab through cross-origin "simple" requests, <img>/<script>
loads and navigations, none of which need a CORS preflight and not all of
which carry an Origin header (an Origin-only guard admitted an Origin-less GET).

Contract, enforced before routing:
  1. positive: every request must carry the X-Rook-Client header. A
     cross-origin page can only add a custom header through a CORS-preflighted
     request, and the server never answers a preflight; <img>, <script>, forms
     and navigations cannot set headers at all. Rook's own clients send it.
  2. negative, defense in depth: requests carrying Origin or the browser-set
     fetch-metadata headers (Sec-Fetch-*) are rejected regardless.
  3. authority: Host must be 127.0.0.1 or localhost (optionally :port). Rule 1
     does not cover DNS rebinding: an attacker hostname resolving to 127.0.0.1
     makes the page SAME-origin with the server, so its requests may add custom
     headers without a preflight and carry no Origin or Sec-Fetch-* over plain
     HTTP. They still say ``Host: <attacker hostname>``, which rule 3 refuses.

Tests: a source scan that pins the contract in RookServer.cpp, checks that
every Python client that talks to the native server sends the header (the httpx
factory, the urllib bootstrap executor, the standalone scripts, and a sweep for
raw client construction), and a live check against a running Rhino
(``requires_rhino``) covering the Origin-less GET and the rebinding Host cases.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

import httpx
import pytest

from rook.bridge import NATIVE_CLIENT_HEADER, NATIVE_CLIENT_HEADERS, native_client

_REPO = Path(__file__).resolve().parents[2]
_NATIVE_SERVER = _REPO / "src" / "RookNative" / "RookServer.cpp"


def test_native_server_source_requires_client_header_rejects_browser_metadata_and_checks_host():
    source = _NATIVE_SERVER.read_text(encoding="utf-8")
    assert 'kRookClientHeader = "X-Rook-Client"' in source
    assert "bool IsAllowedLoopbackAuthority(const std::string& host)" in source
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
        'has_header("Host")',
        'IsAllowedLoopbackAuthority(req.get_header_value("Host"))',
        "browser_marked || !client_marked || !host_allowed",
        "res.status = 403",
        'set_header("Connection", "close")',
        "browser_request_rejected",
        "client_header_required",
        "host_not_allowed",
        "HandlerResponse::Handled",
        "HandlerResponse::Unhandled",
    ):
        assert needle in body, needle


def test_client_header_names_agree_across_python_cpp_and_csharp():
    assert NATIVE_CLIENT_HEADER == "X-Rook-Client"
    cs = (_REPO / "src" / "Rook" / "Services" / "Reconstruction" / "ReconstructionImportClient.cs").read_text(encoding="utf-8")
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


def test_bootstrap_http_executor_sends_the_header_on_ping_get_and_post(monkeypatch):
    """The bootstrap executor uses urllib, not httpx, so it cannot use the factory."""
    from rook.bootstrap.executor import HttpExecutor, create_http_executor

    seen: list[urllib.request.Request] = []

    class _Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        return _Response(json.dumps({"success": True, "data": {}}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    executor = HttpExecutor("http://127.0.0.1:1")
    assert executor.ping() is True
    executor.execute("rhino_objects", {"layer": "Default"})   # GET with query params
    executor.execute("rhino_create", {"type": "box"})          # POST with JSON body

    assert [r.get_method() for r in seen] == ["GET", "GET", "POST"]
    for req in seen:
        assert req.get_header("X-rook-client") == NATIVE_CLIENT_HEADERS[NATIVE_CLIENT_HEADER], req.header_items()
    assert seen[2].get_header("Content-type") == "application/json"

    # create_http_executor() pings first; a 403 from a header-less ping made it return None.
    assert create_http_executor("http://127.0.0.1:1") is not None


def test_gh_readiness_harness_sends_the_header_on_its_sync_client(monkeypatch):
    """`--smoke gh-readiness` / `gh-python-geometry-output` call the native server through this helper."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gh_readiness_live_harness", _REPO / "mcp_server" / "tools" / "gh_readiness_live_harness.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"success": True, "data": {}})

    real_client = httpx.Client
    monkeypatch.setattr(harness.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    harness.call("http://127.0.0.1:1", "GET", "/gh/status")
    harness.call("http://127.0.0.1:1", "POST", "/gh/edit", {"epoch": 1})
    assert [r.method for r in seen] == ["GET", "POST"]
    for request in seen:
        assert request.headers.get(NATIVE_CLIENT_HEADER) == NATIVE_CLIENT_HEADERS[NATIVE_CLIENT_HEADER]


_NATIVE_CALLING_SCRIPTS = (
    "scripts/run_simulation_export.py",
    "scripts/validate_rhino_operational_suite.py",
    "scripts/validate_gh_runtime.py",
)


@pytest.mark.parametrize("script", _NATIVE_CALLING_SCRIPTS)
def test_standalone_scripts_build_their_native_clients_through_the_factory(script):
    source = (_REPO / script).read_text(encoding="utf-8")
    assert "native_client" in source and "from rook.bridge import" in source, script
    assert "native_client(" in source, script
    assert "httpx.AsyncClient(" not in source and "httpx.Client(" not in source, (
        f"{script} constructs a raw httpx client; native calls must go through rook.bridge.native_client"
    )


# Files allowed to construct raw HTTP clients because they never talk to the
# native server (Chirp, model providers, LLM/API probes, a local fake provider)
# or do so deliberately (this file's live test crafts hostile requests).
# Anything else that grows a raw constructor must route through
# native_client / NATIVE_CLIENT_HEADERS (or conftest's _native_headers()).
_RAW_CLIENT_ALLOWLIST = {
    "mcp_server/tests/test_native_origin_guard.py",
    "mcp_server/tests/test_local_testing_proof.py",   # posts to its own fake slow provider
    "mcp_server/src/rook/bridge.py",                  # the factory itself
    "mcp_server/src/rook/chirp_manager.py",           # Chirp health checks
    "mcp_server/src/rook/server.py",                  # chirp_client (Chirp, not native)
    "mcp_server/src/rook/agent/model_profiles.py",    # provider model listings
    "mcp_server/src/rook/providers/openrouter_catalog.py",
    "mcp_server/src/rook/providers/vertex_backend.py",
    "mcp_server/src/rook/providers/vertex_oauth.py",
    "scripts/lm5p_ollama_think_format_spike.py",      # LLM probes
    "scripts/lm5r_two_pass_publication_probe.py",
    "scripts/lm_worker_two_pass_publication.py",
}
_RAW_CLIENT_ALLOWED_PREFIXES = ("tools/spikes/",)   # third-party API probes (fal, Gemini, Replicate)
_HEADER_MARKERS = ("native_client", "NATIVE_CLIENT_HEADERS", "_native_headers(")
_RAW_CLIENT = re.compile(
    r"httpx\.(?:AsyncClient|Client)\(|httpx\.(?:get|post|put|delete)\(|urllib\.request\.Request\("
)


def _tracked_python_files() -> list[Path]:
    """Every tracked .py file: package, tests, tools, scripts, docs spikes, benchmarks."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=_REPO, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - no git in the sandbox
        pytest.skip(f"git ls-files unavailable: {exc}")
    return [_REPO / rel for rel in out.decode("utf-8").split("\0") if rel]


def test_no_new_raw_http_clients_outside_the_allowlist():
    offenders: list[str] = []
    files = _tracked_python_files()
    assert any(p.as_posix().endswith("mcp_server/tools/gh_readiness_live_harness.py") for p in files)
    for path in files:
        rel = path.relative_to(_REPO).as_posix()
        if rel in _RAW_CLIENT_ALLOWLIST or rel.startswith(_RAW_CLIENT_ALLOWED_PREFIXES) or not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for n, line in enumerate(lines, 1):
            if not _RAW_CLIENT.search(line):
                continue
            # A multi-line call may pass headers=NATIVE_CLIENT_HEADERS on a later line.
            call = " ".join(lines[n - 1 : n + 8])
            if not any(marker in call for marker in _HEADER_MARKERS):
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, (
        "raw HTTP client construction outside the allowlist; native-server callers must use "
        "rook.bridge.native_client (httpx) or send NATIVE_CLIENT_HEADERS (urllib):\n" + "\n".join(offenders)
    )


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
        # Rook client: header present, loopback Host, no browser metadata -> served.
        ok = client.get(f"{base}/ping", headers=NATIVE_CLIENT_HEADERS)
        assert ok.status_code == 200
        ok_localhost = client.get(f"{base}/ping", headers={**NATIVE_CLIENT_HEADERS, "Host": f"localhost:{port}"})
        assert ok_localhost.status_code == 200
        ok_bare_host = client.get(f"{base}/ping", headers={**NATIVE_CLIENT_HEADERS, "Host": "127.0.0.1"})
        assert ok_bare_host.status_code == 200

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

        # DNS rebinding: same-origin from the page's point of view, so the custom
        # header is present and there is no Origin or fetch metadata (plain HTTP,
        # non-trustworthy URL). Only the Host header gives it away -> refused.
        for host in ("attacker.example", f"attacker.example:{port}", "127.0.0.1.attacker.example", "127.0.0.1:1x"):
            rebound = client.get(f"{base}/execute", headers={**NATIVE_CLIENT_HEADERS, "Host": host, "User-Agent": browser_ua})
            assert rebound.status_code == 403, host
            assert rebound.json()["error"] == "host_not_allowed", host

        # A blind cross-origin "simple" POST (text/plain body, Origin set) -> refused.
        blind_post = client.post(
            f"{base}/execute",
            content='{"code": "print(1)"}',
            headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
        )
        assert blind_post.status_code == 403
        # httplib reads bodies after the gate, so a refused POST must close the
        # connection or its unread body becomes the "next request" (HTTP 400).
        assert blind_post.headers.get("connection", "").lower() == "close"

        # Even with the client header, browser metadata is refused (defense in depth).
        marked = client.get(f"{base}/ping", headers={**NATIVE_CLIENT_HEADERS, "Origin": "http://127.0.0.1:1"})
        assert marked.status_code == 403
        assert marked.json()["error"] == "browser_request_rejected"

        # A refused request with a body followed by a legitimate one on the same
        # client must not disturb the legitimate one.
        refused = client.post(f"{base}/ping", content="abc", headers={"Content-Type": "text/plain"})
        assert refused.status_code == 403
        assert client.get(f"{base}/ping", headers=NATIVE_CLIENT_HEADERS).status_code == 200
