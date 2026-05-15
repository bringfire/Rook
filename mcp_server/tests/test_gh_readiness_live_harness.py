from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_harness_module():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "mcp_server" / "tools" / "gh_readiness_live_harness.py"
    spec = importlib.util.spec_from_file_location("gh_readiness_live_harness", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_base_url_uses_runtime_harness_port(monkeypatch):
    harness = _load_harness_module()
    monkeypatch.setenv("ROOK_RHINO_PORT", "54321")

    assert harness.resolve_base_url(None) == "http://127.0.0.1:54321"


def test_prepare_gh_open_runs_explicit_lifecycle_sequence():
    harness = _load_harness_module()
    calls = []
    status_calls = 0

    def fake_call(base_url, method, path, payload=None):
        nonlocal status_calls
        calls.append((method, path, payload))
        if path == "/command":
            return {"success": True}
        if path == "/gh/status":
            status_calls += 1
            if status_calls == 1:
                return {"success": True, "data": {"available": True}}
            return {"success": True, "data": {"readyForEdit": True}}
        if path == "/gh/document/new":
            return {"success": True, "data": {"created": True}}
        raise AssertionError(f"unexpected call: {method} {path}")

    status = harness.prepare_gh_open(
        "http://127.0.0.1:54321",
        call_fn=fake_call,
        sleep_fn=lambda _seconds: None,
        poll_attempts=1,
    )

    assert status["data"]["readyForEdit"] is True
    assert calls == [
        ("POST", "/command", {"command": "_Grasshopper"}),
        ("GET", "/gh/status", None),
        ("POST", "/gh/document/new", {}),
        ("GET", "/gh/status", None),
    ]


def test_prepare_gh_open_tolerates_grasshopper_command_timeout_if_runtime_loads():
    harness = _load_harness_module()
    calls = []
    status_calls = 0

    def fake_call(base_url, method, path, payload=None):
        nonlocal status_calls
        calls.append((method, path, payload))
        if path == "/command":
            return {"success": False, "error": "HTTP request timed out"}
        if path == "/gh/status":
            status_calls += 1
            if status_calls == 1:
                return {"success": True, "data": {"available": True}}
            return {"success": True, "data": {"readyForEdit": True}}
        if path == "/gh/document/new":
            return {"success": True, "data": {"created": True}}
        raise AssertionError(f"unexpected call: {method} {path}")

    status = harness.prepare_gh_open(
        "http://127.0.0.1:54321",
        call_fn=fake_call,
        sleep_fn=lambda _seconds: None,
        poll_attempts=1,
    )

    assert status["data"]["readyForEdit"] is True
    assert calls[0] == ("POST", "/command", {"command": "_Grasshopper"})
