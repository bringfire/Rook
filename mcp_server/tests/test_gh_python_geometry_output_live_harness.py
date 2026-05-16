import importlib.util
from pathlib import Path

import pytest


def _load_geometry_harness_module():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "mcp_server" / "tools" / "gh_python_geometry_output_live_harness.py"
    spec = importlib.util.spec_from_file_location("gh_python_geometry_output_live_harness", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return _load_geometry_harness_module()


def test_owned_base_url_requires_runtime_harness_env(monkeypatch, module):
    monkeypatch.delenv("ROOK_RHINO_PORT", raising=False)
    monkeypatch.delenv("ROOK_RHINO_PROCESS_ID", raising=False)

    with pytest.raises(AssertionError, match="ROOK_RHINO_PORT"):
        module.resolve_owned_base_url()


def test_owned_base_url_uses_runtime_harness_env(monkeypatch, module):
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")

    assert module.resolve_owned_base_url() == "http://127.0.0.1:9951"


def test_main_pings_prepares_gh_then_runs_selected_pytest(monkeypatch, module):
    calls = []
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")
    monkeypatch.setattr(
        module,
        "assert_owned_ping",
        lambda base_url: calls.append(("ping", base_url)),
    )
    monkeypatch.setattr(
        module,
        "prepare_gh_open",
        lambda base_url: calls.append(("prepare_gh_open", base_url)),
    )
    monkeypatch.setattr(
        module,
        "run_selected_pytest",
        lambda repo_root: calls.append(("pytest", repo_root)) or 0,
    )

    assert module.main([]) == 0
    assert calls == [
        ("ping", "http://127.0.0.1:9951"),
        ("prepare_gh_open", "http://127.0.0.1:9951"),
        ("pytest", module.repo_root()),
    ]
