from __future__ import annotations
import asyncio
import pytest
from rook import merge_execution, work_units, artifacts


@pytest.fixture
def temp_registries(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
    yield tmp_path
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()


async def _never_call(name, args):  # call_tool that must not be reached in gate tests
    raise AssertionError(f"call_tool should not be invoked here, got {name!r}")


def _run(coro):
    return asyncio.run(coro)


def test_invalid_contract_id(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="", session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "invalid_argument"


def test_unknown_expected_merge_kind(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="mc-x", session="rhino-1", expected_merge_kind="linkedblock",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "invalid_argument"


def test_session_required(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="mc-x", session="", expected_merge_kind="linked_block",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "session_required"


def _make_contract(tmp_path, merge_kind="linked_block", refresh="refresh_on_demand"):
    """Register a present target+source in P6 and record a contract; return (contract_id, tgt, src)."""
    tgt = tmp_path / "target.3dm"
    src = tmp_path / "source.3dm"
    tgt.write_bytes(b"t")
    src.write_bytes(b"s")
    rt = _run(artifacts.register_artifact(str(tgt)))
    rs = _run(artifacts.register_artifact(str(src)))
    tgt_id = rt["data"]["artifact"]["artifactId"]
    src_id = rs["data"]["artifact"]["artifactId"]
    rec = _run(work_units.record_merge_contract(
        target_artifact_id=tgt_id, source_artifact_ids=[src_id],
        merge_kind=merge_kind, refresh_policy=refresh))
    return rec["data"]["contractId"], tgt_id, src_id, str(tgt), str(src)


def test_contract_not_found(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="mc-nope", session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "contract_not_found"


def test_merge_kind_mismatch(temp_registries):
    cid, *_ = _make_contract(temp_registries, merge_kind="linked_block")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="import",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "merge_kind_mismatch"


def test_unsupported_merge_kind(temp_registries):
    cid, *_ = _make_contract(temp_registries, merge_kind="import")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="import",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False
    assert out["data"]["code"] == "unsupported_merge_kind"
    assert out["data"]["supportedMergeKinds"] == ["linked_block"]
