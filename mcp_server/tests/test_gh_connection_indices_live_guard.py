from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_live_module():
    path = Path(__file__).with_name("test_gh_connection_indices_live.py")
    spec = importlib.util.spec_from_file_location("gh_connection_indices_live", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_live_regression_refuses_mutation_without_harness_ownership(monkeypatch):
    module = _load_live_module()
    monkeypatch.delenv("ROOK_RHINO_PORT", raising=False)
    monkeypatch.delenv("ROOK_RHINO_PROCESS_ID", raising=False)
    mutations: list[str] = []

    async def unexpected_prepare(_base_url):
        mutations.append("prepare")
        raise RuntimeError("mutation attempted")

    async def unexpected_mcp(*_args, **_kwargs):
        mutations.append("mcp")
        raise RuntimeError("mutation attempted")

    monkeypatch.setattr(module, "get_rhino_host", lambda **_kwargs: "http://127.0.0.1:9999", raising=False)
    monkeypatch.setattr(module, "_prepare_blank_grasshopper_document", unexpected_prepare)
    monkeypatch.setattr(module, "_raw_post", unexpected_mcp)
    monkeypatch.setattr(module, "_mcp_tool_executor", unexpected_mcp)

    with pytest.raises(AssertionError, match="ROOK_RHINO_PORT"):
        await module.test_mcp_connect_and_raw_disconnect_honor_indices_five_through_seven()

    assert mutations == []


@pytest.mark.asyncio
async def test_live_regression_rejects_mismatched_owned_discovery_record(monkeypatch):
    module = _load_live_module()
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")
    monkeypatch.setattr(
        "rook.runtime_harness.OwnedRhinoDiscovery",
        lambda: SimpleNamespace(
            read_owned_record=lambda _pid: SimpleNamespace(pid=7102, port=9952)
        ),
    )
    monkeypatch.setattr(module, "get_rhino_host", lambda **_kwargs: "http://127.0.0.1:9951", raising=False)

    async def unexpected_prepare(_base_url):
        raise RuntimeError("mutation attempted")

    monkeypatch.setattr(module, "_prepare_blank_grasshopper_document", unexpected_prepare)
    monkeypatch.setattr(module, "_raw_post", unexpected_prepare)

    with pytest.raises(AssertionError, match="same owned runtime"):
        await module.test_mcp_connect_and_raw_disconnect_honor_indices_five_through_seven()


@pytest.mark.asyncio
async def test_live_regression_preserves_body_and_cleanup_failures(monkeypatch):
    module = _load_live_module()
    monkeypatch.setattr(module, "_require_owned_runtime_base_url", lambda: "http://127.0.0.1:9951", raising=False)
    monkeypatch.setattr(module, "get_rhino_host", lambda **_kwargs: "http://127.0.0.1:9951", raising=False)

    async def no_preexisting(_base_url):
        return None

    async def prepare(_base_url):
        return None

    async def fail_body(_base_url):
        raise ValueError("body failed")

    async def fail_cleanup(_base_url):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(module, "_assert_no_preexisting_gh_documents", no_preexisting, raising=False)
    monkeypatch.setattr(module, "_prepare_blank_grasshopper_document", prepare)
    monkeypatch.setattr(module, "_exercise_indexed_wiring", fail_body, raising=False)
    monkeypatch.setattr(module, "_discard_disposable_document_changes", fail_cleanup)
    monkeypatch.setattr(module, "_mcp_tool_executor", fail_body)

    with pytest.raises(BaseExceptionGroup) as captured:
        await module.test_mcp_connect_and_raw_disconnect_honor_indices_five_through_seven()

    assert [str(error) for error in captured.value.exceptions] == [
        "body failed",
        "cleanup failed",
    ]
