import asyncio
import os
import sys
from pathlib import Path

import pytest
import sqlite3

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rook import artifacts


def test_normalize_path_is_absolute_and_case_folded(tmp_path):
    f = tmp_path / "Model.3dm"
    f.write_bytes(b"x")
    a = artifacts.normalize_path(str(f))
    b = artifacts.normalize_path(str(f).upper())  # Windows: case-insensitive
    assert os.path.isabs(a)
    if os.name == "nt":
        assert a == b  # same artifact regardless of case


def test_artifact_id_is_deterministic_sha256_hex():
    norm = artifacts.normalize_path("C:/proj/site.3dm") if os.name == "nt" else artifacts.normalize_path("/proj/site.3dm")
    i1 = artifacts.artifact_id_for(norm)
    i2 = artifacts.artifact_id_for(norm)
    assert i1 == i2 and len(i1) == 64 and all(c in "0123456789abcdef" for c in i1)


def test_stat_file_state_present_missing(tmp_path):
    f = tmp_path / "x.3dm"
    f.write_bytes(b"abc")
    norm = artifacts.normalize_path(str(f))
    state, size, mtime = artifacts.stat_file_state(norm)
    assert state == "present" and size == 3 and isinstance(mtime, int)

    missing = artifacts.normalize_path(str(tmp_path / "nope.3dm"))
    state2, size2, mtime2 = artifacts.stat_file_state(missing)
    assert state2 == "missing" and size2 is None and mtime2 is None


def test_fresh_db_creates_table_and_persists_version(tmp_path):
    reg = artifacts.ArtifactRegistry(tmp_path / "artifacts.db")
    assert reg.schema_unsupported is None
    reg.close()
    reg2 = artifacts.ArtifactRegistry(tmp_path / "artifacts.db")  # reopen, no error
    assert reg2.schema_unsupported is None
    reg2.close()


def test_version_skew_fails_closed_without_dropping(tmp_path):
    db = tmp_path / "artifacts.db"
    reg = artifacts.ArtifactRegistry(db)
    reg._conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('artifact_registry_version','p99.9');")
    reg.close()
    reg2 = artifacts.ArtifactRegistry(db)
    assert reg2.schema_unsupported == "p99.9"   # fail closed, rows intact, table not dropped
    assert reg2._conn.execute("SELECT 1 FROM sqlite_master WHERE name='artifacts';").fetchone() is not None
    reg2.close()


def test_foreign_table_shape_fails_closed(tmp_path):
    db = tmp_path / "artifacts.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE artifacts (wrong TEXT);")
    conn.commit(); conn.close()
    reg = artifacts.ArtifactRegistry(db)
    assert reg.schema_unsupported == "unknown"
    reg.close()


def _reg(tmp_path):
    return artifacts.ArtifactRegistry(tmp_path / "artifacts.db")


def test_upsert_born_present_creates_only_when_present(tmp_path):
    reg = _reg(tmp_path)
    assert reg.upsert("/p/a.3dm", source="owned_workbench", file_state="missing",
                      size=None, mtime=None, document_name=None, origin_session_id=None,
                      label=None, now=100) == "skipped_absent"
    assert reg.get(path="/p/a.3dm") is None
    assert reg.upsert("/p/a.3dm", source="owned_workbench", file_state="present",
                      size=5, mtime=9, document_name="a", origin_session_id="rhino-1",
                      label=None, now=101) == "created"
    row = reg.get(path="/p/a.3dm")
    assert row.file_state == "present" and row.source == "owned_workbench" and row.size_bytes == 5
    assert row.artifact_id == artifacts.artifact_id_for("/p/a.3dm")
    reg.close()


def test_upsert_existing_transitions_state_and_is_idempotent(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=5, mtime=9,
               document_name=None, origin_session_id=None, label=None, now=100)
    assert reg.upsert("/p/a.3dm", source="owned_workbench", file_state="missing",
                      size=None, mtime=None, document_name=None, origin_session_id=None,
                      label=None, now=200) == "updated"
    row = reg.get(path="/p/a.3dm")
    assert row.file_state == "missing" and row.last_missing_at == 200 and row.size_bytes is None
    assert row.source == "explicit"  # source is NOT overwritten on update
    assert len(reg.list_all()) == 1
    reg.close()


def test_set_state_updates_existing_only(tmp_path):
    reg = _reg(tmp_path)
    assert reg.set_state("/p/missing.3dm", file_state="present", size=1, mtime=1, now=1) is False
    reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=5, mtime=9,
               document_name=None, origin_session_id=None, label=None, now=100)
    assert reg.set_state("/p/a.3dm", file_state="unreachable", size=None, mtime=None, now=300) is True
    assert reg.get(path="/p/a.3dm").file_state == "unreachable"
    reg.close()


def test_delete_removes_row_only(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=5, mtime=9,
               document_name=None, origin_session_id=None, label=None, now=100)
    assert reg.delete("/p/a.3dm") is True
    assert reg.delete("/p/a.3dm") is False
    assert reg.get(path="/p/a.3dm") is None
    reg.close()


def test_get_by_id_and_path_agree(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=5, mtime=9,
               document_name=None, origin_session_id=None, label=None, now=100)
    by_path = reg.get(path="/p/a.3dm")
    by_id = reg.get(artifact_id=artifacts.artifact_id_for("/p/a.3dm"))
    assert by_path == by_id
    reg.close()


def test_unreachable_does_not_advance_last_verified(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=5, mtime=9,
               document_name=None, origin_session_id=None, label=None, now=100)
    assert reg.set_state("/p/a.3dm", file_state="unreachable", size=None, mtime=None, now=200) is True
    row = reg.get(path="/p/a.3dm")
    assert row.file_state == "unreachable" and row.last_verified_at == 100  # NOT bumped to 200


def test_different_path_same_id_fails_closed(tmp_path, monkeypatch):
    reg = _reg(tmp_path)
    monkeypatch.setattr(artifacts, "artifact_id_for", lambda p: "collide")
    assert reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=1, mtime=1,
                      document_name=None, origin_session_id=None, label=None, now=1) == "created"
    assert reg.upsert("/p/b.3dm", source="explicit", file_state="present", size=1, mtime=1,
                      document_name=None, origin_session_id=None, label=None, now=2) == "id_collision"
    assert len(reg.list_all()) == 1  # second never inserted


def test_registry_unusable_returns_structured_error(tmp_path, monkeypatch):
    db = tmp_path / "artifacts.db"
    r = artifacts.ArtifactRegistry(db)
    r._conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('artifact_registry_version','p99.9');")
    r.close()
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: db)
    artifacts._reset_artifact_registry_singleton()
    err = asyncio.run(artifacts._artifact_registry_unusable())
    assert err is not None and err["success"] is False
    assert err["data"]["code"] == "artifact_registry_unavailable"
    artifacts._reset_artifact_registry_singleton()


def test_err_sets_retryable_from_map():
    assert artifacts._err("artifact_not_found", "x")["data"]["retryable"] is False
    assert artifacts._err("artifact_registry_unavailable", "x")["data"]["retryable"] is True


@pytest.fixture
def _isolated_artifact_db(tmp_path, monkeypatch):
    # Patch the artifacts-LOCAL name and manage the singleton MANUALLY, or tool fns
    # open the REAL %LOCALAPPDATA% db (the P5 from-import local-name trap).
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    yield
    artifacts._reset_artifact_registry_singleton()


def test_register_requires_existing_file(tmp_path, _isolated_artifact_db):
    missing = str(tmp_path / "ghost.3dm")
    res = asyncio.run(artifacts.register_artifact(missing))
    assert res["success"] is False and res["data"]["code"] == "artifact_file_not_found"


def test_register_present_then_list(tmp_path, _isolated_artifact_db):
    f = tmp_path / "site.3dm"; f.write_bytes(b"abc")
    res = asyncio.run(artifacts.register_artifact(str(f)))
    assert res["success"] is True and res["data"]["artifact"]["source"] == "explicit"
    assert res["data"]["artifact"]["fileExists"] is True
    listing = asyncio.run(artifacts.list_artifacts())
    assert len(listing["data"]["artifacts"]) == 1


def test_selector_required_and_conflict(tmp_path, _isolated_artifact_db):
    none = asyncio.run(artifacts.refresh_artifact())
    assert none["data"]["code"] == "artifact_selector_required"
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    conflict = asyncio.run(artifacts.refresh_artifact(artifact_id="deadbeef", path=str(f)))
    assert conflict["data"]["code"] == "artifact_selector_conflict"


def test_refresh_transitions_to_missing_after_delete(tmp_path, _isolated_artifact_db):
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    asyncio.run(artifacts.register_artifact(str(f)))
    os.remove(f)
    res = asyncio.run(artifacts.refresh_artifact(path=str(f)))
    assert res["success"] is True and res["data"]["artifact"]["fileState"] == "missing"


def test_deregister_removes_row_but_not_file(tmp_path, _isolated_artifact_db):
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    asyncio.run(artifacts.register_artifact(str(f)))
    res = asyncio.run(artifacts.deregister_artifact(path=str(f)))
    assert res["success"] is True and res["data"]["fileUntouched"] is True
    assert f.exists()  # I5: the .3dm is never touched
    assert asyncio.run(artifacts.list_artifacts())["data"]["artifacts"] == []


def test_get_artifact_by_path_and_unknown(tmp_path, _isolated_artifact_db):
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    asyncio.run(artifacts.register_artifact(str(f)))
    got = asyncio.run(artifacts.get_artifact(path=str(f)))
    assert got["success"] is True and got["data"]["artifact"]["fileExists"] is True
    miss = asyncio.run(artifacts.get_artifact(path=str(tmp_path / "nope.3dm")))
    assert miss["data"]["code"] == "artifact_not_found"


def test_register_unreachable_is_not_not_found(tmp_path, monkeypatch, _isolated_artifact_db):
    # Tri-state honesty: permission-denied / unreachable is NOT "not found".
    monkeypatch.setattr(artifacts, "stat_file_state", lambda p: ("unreachable", None, None))
    res = asyncio.run(artifacts.register_artifact(str(tmp_path / "x.3dm")))
    assert res["data"]["code"] == "artifact_file_unreachable" and res["data"]["retryable"] is True


def test_register_id_collision_returns_house_envelope(tmp_path, monkeypatch, _isolated_artifact_db):
    monkeypatch.setattr(artifacts, "artifact_id_for", lambda p: "collide")
    a = tmp_path / "a.3dm"; a.write_bytes(b"x")
    b = tmp_path / "b.3dm"; b.write_bytes(b"y")
    assert asyncio.run(artifacts.register_artifact(str(a)))["success"] is True
    res = asyncio.run(artifacts.register_artifact(str(b)))
    assert res["data"]["code"] == "artifact_id_collision"


def test_artifact_tools_are_meta_and_known():
    from rook import targeting
    for name in ("rhino_artifacts", "rhino_artifact_register",
                 "rhino_artifact_refresh", "rhino_artifact_deregister"):
        assert name in targeting._META_TOOLS
        assert name in targeting._ALL_KNOWN_TOOLS
        p = targeting.policy_for_tool(name)
        assert p.requires_rhino is False and p.risk == "meta"


def test_rhino_sessions_does_not_call_artifact_observer(monkeypatch):
    # Regression guard for the structural boundary (spec Finding 2): listing the
    # FLEET must never auto-persist artifacts. Mirrors test_session_tools.py:27 —
    # dispatch calls server.list_sessions_result(), so patch THAT name.
    from rook import server, workbench
    called = {"n": 0}

    async def spy(inst, session_id):
        called["n"] += 1

    monkeypatch.setattr(workbench, "_best_effort_observe_owned_artifact", spy)
    monkeypatch.setattr(server, "list_sessions_result",
                        lambda: {"success": True, "data": {"sessions": []}})
    result = asyncio.run(server._call_tool_dispatch("rhino_sessions", {}))
    assert result["success"] is True
    assert called["n"] == 0


def test_server_dispatches_artifact_tools(tmp_path, monkeypatch, _isolated_artifact_db):
    from rook import server
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    reg = asyncio.run(server._call_tool_dispatch("rhino_artifact_register", {"path": str(f)}))
    assert reg["success"] is True and reg["data"]["artifact"]["source"] == "explicit"
    listing = asyncio.run(server._call_tool_dispatch("rhino_artifacts", {}))
    assert len(listing["data"]["artifacts"]) == 1
    got = asyncio.run(server._call_tool_dispatch("rhino_artifacts", {"path": str(f)}))
    assert got["data"]["artifact"]["fileExists"] is True
    dereg = asyncio.run(server._call_tool_dispatch("rhino_artifact_deregister", {"path": str(f)}))
    assert dereg["data"]["fileUntouched"] is True and f.exists()


def test_source_precedence_explicit_outranks_owned(tmp_path):
    # explicit (deliberate campaign membership) outranks owned_workbench (automatic
    # perception) and NEVER downgrades (Codex finding).
    reg = _reg(tmp_path)
    reg.upsert("/p/a.3dm", source="owned_workbench", file_state="present", size=1, mtime=1,
               document_name=None, origin_session_id="rhino-1", label=None, now=1)
    reg.upsert("/p/a.3dm", source="explicit", file_state="present", size=1, mtime=1,
               document_name=None, origin_session_id=None, label=None, now=2)
    assert reg.get(path="/p/a.3dm").source == "explicit"  # observed -> explicit promotes
    reg.upsert("/p/a.3dm", source="owned_workbench", file_state="present", size=1, mtime=1,
               document_name=None, origin_session_id=None, label=None, now=3)
    assert reg.get(path="/p/a.3dm").source == "explicit"  # never downgrades
    reg.close()


def test_register_promotes_observed_row(tmp_path, _isolated_artifact_db):
    f = tmp_path / "wb.3dm"; f.write_bytes(b"x")
    norm = artifacts.normalize_path(str(f))
    artifacts.artifact_registry().upsert(norm, source="owned_workbench", file_state="present",
        size=1, mtime=1, document_name=None, origin_session_id="rhino-1", label=None, now=1)
    res = asyncio.run(artifacts.register_artifact(str(f)))
    assert res["data"]["artifact"]["source"] == "explicit"


def test_mesh2splat_capture_promotes_explicit_and_replaces_provenance(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/capture.ply", source="explicit", file_state="present", size=1, mtime=1,
               document_name="manual-doc", origin_session_id="manual-session",
               label="manual-label", now=1)
    reg.upsert("/p/capture.ply", source="mesh2splat_capture", file_state="present", size=2, mtime=2,
               document_name="capture-doc", origin_session_id="capture-session",
               label="capture-label", now=2)

    row = reg.get(path="/p/capture.ply")
    assert row.source == "mesh2splat_capture"
    assert row.document_name == "capture-doc"
    assert row.origin_session_id == "capture-session"
    assert row.label == "capture-label"
    reg.close()


def test_mesh2splat_capture_rerun_replaces_owned_provenance(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/capture.ply", source="mesh2splat_capture", file_state="present", size=1, mtime=1,
               document_name="capture-doc-1", origin_session_id="capture-session-1",
               label="capture-label-1", now=1)
    reg.upsert("/p/capture.ply", source="mesh2splat_capture", file_state="present", size=2, mtime=2,
               document_name="capture-doc-2", origin_session_id="capture-session-2",
               label="capture-label-2", now=2)

    row = reg.get(path="/p/capture.ply")
    assert row.source == "mesh2splat_capture"
    assert row.document_name == "capture-doc-2"
    assert row.origin_session_id == "capture-session-2"
    assert row.label == "capture-label-2"
    reg.close()


def test_lower_ranked_updates_do_not_downgrade_or_replace_mesh2splat_provenance(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert("/p/capture.ply", source="mesh2splat_capture", file_state="present", size=1, mtime=1,
               document_name="capture-doc", origin_session_id="capture-session",
               label="capture-label", now=1)

    for source in ("explicit", "owned_workbench"):
        reg.upsert("/p/capture.ply", source=source, file_state="present", size=2, mtime=2,
                   document_name=f"{source}-doc", origin_session_id=f"{source}-session",
                   label=f"{source}-label", now=2)
        row = reg.get(path="/p/capture.ply")
        assert row.source == "mesh2splat_capture"
        assert row.document_name == "capture-doc"
        assert row.origin_session_id == "capture-session"
        assert row.label == "capture-label"
    reg.close()
