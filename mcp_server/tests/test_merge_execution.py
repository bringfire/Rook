from __future__ import annotations
import asyncio
import pytest
from rook import merge_execution, work_units, artifacts, targeting, bridge


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


class FakeRhino:
    """Records context port on every call; returns canned envelopes by tool name."""
    def __init__(self, doc_path, blocks=None, blocks_ok=True,
                 link_ok=True, refresh_ok=True, save_ok=True, doc_path_after=None):
        self.doc_path = doc_path
        self.doc_path_after = doc_path_after  # if set, returned on the 2nd+ rhino_document read (drift)
        self._doc_reads = 0
        self.blocks = blocks if blocks is not None else []
        self.blocks_ok = blocks_ok
        self.link_ok, self.refresh_ok, self.save_ok = link_ok, refresh_ok, save_ok
        self.seen_ports = []
        self.calls = []

    async def __call__(self, name, args):
        self.seen_ports.append(bridge.get_rhino_request_context()["port"])
        # Pin the "routing via context, not args" rule (the stale-port correction):
        assert "port" not in args and "session" not in args, \
            f"sub-call {name!r} must not carry routing selectors: {args!r}"
        self.calls.append((name, args))
        if name == "rhino_document":
            self._doc_reads += 1
            p = (self.doc_path if (self._doc_reads == 1 or self.doc_path_after is None)
                 else self.doc_path_after)
            return {"success": True, "data": {"documentPath": p}}
        if name == "rhino_blocks":
            return {"success": self.blocks_ok, "data": {"blocks": self.blocks}}
        if name == "rhino_block_link":
            return {"success": self.link_ok, "data": {"name": args["name"]}}
        if name == "rhino_block_refresh":
            return {"success": self.refresh_ok, "data": {"name": args["name"]}}
        if name == "rhino_document_ops":
            return {"success": self.save_ok, "data": {}}
        raise AssertionError(f"unexpected tool {name!r}")


_PINNED = 59123


def _pin_route(monkeypatch, *, success=True, error=None):
    route = targeting.ToolRoute(
        success=success, error=error,
        target=(targeting.InstanceRef(port=_PINNED, process_id=4242) if success else None),
        selection="session")
    monkeypatch.setattr(targeting, "resolve_tool_route", lambda *a, **k: route)
    return route


def test_session_not_found(temp_registries, monkeypatch):
    cid, *_ = _make_contract(temp_registries)
    _pin_route(monkeypatch, success=False, error="rhino_session_not_found")
    fake = FakeRhino(doc_path="C:/whatever.3dm")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-9", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "rhino_session_not_found"
    assert fake.calls == []  # never touched Rhino


def test_target_document_mismatch(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path="C:/someone-elses-doc.3dm")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "target_document_mismatch"
    # Finding 1: the rhino_document read happened on the pinned port.
    assert fake.seen_ports and all(p == _PINNED for p in fake.seen_ports)


def test_target_not_open(temp_registries, monkeypatch):
    cid, *_ = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path="")  # unsaved / no path
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "target_not_open"


def test_session_resolution_passes_has_explicit_session(temp_registries, monkeypatch):
    # Finding 3 (load-bearing spec correction): a broken impl that omits has_explicit_session=True
    # would silently fall through to ambient routing. A dedicated fake resolver records the kwargs
    # so omission FAILS this test (has_explicit_session would default to False).
    cid, *_ = _make_contract(temp_registries)
    seen = {}

    def _fake(name, *, explicit_port=None, explicit_session=None, has_explicit_session=False):
        seen.update(name=name, explicit_session=explicit_session,
                    has_explicit_session=has_explicit_session)
        return targeting.ToolRoute(
            success=True, target=targeting.InstanceRef(port=_PINNED, process_id=4242),
            selection="session")

    monkeypatch.setattr(targeting, "resolve_tool_route", _fake)
    fake = FakeRhino(doc_path="C:/wrong.3dm")  # mismatch → returns early after resolution
    _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=True, call_tool=fake))
    assert seen == {"name": "rhino_document", "explicit_session": "rhino-1",
                    "has_explicit_session": True}
