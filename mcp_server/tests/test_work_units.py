from __future__ import annotations
import asyncio
import sqlite3
import time as _time
from pathlib import Path
import pytest
from rook import artifacts, work_units


@pytest.fixture(autouse=True)
def _isolate_registries():
    """Reset both registry singletons after each test so a repointed db path never leaks
    across tests/files (monkeypatch restores the resolve_* functions; this drops the
    lazily-built singletons that may still hold a temp-db connection)."""
    yield
    from rook import artifacts
    artifacts._reset_artifact_registry_singleton()
    work_units._reset_work_units_registry_singleton()


def _fresh_registry(tmp_path) -> "work_units.WorkUnitRegistry":
    return work_units.WorkUnitRegistry(tmp_path / "work_units.db")


def test_schema_bootstrap_creates_five_tables_and_version(tmp_path):
    reg = _fresh_registry(tmp_path)
    names = {r[0] for r in reg._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert {"work_units", "work_unit_artifacts", "merge_contracts",
            "merge_contract_sources", "work_unit_merge_contracts"}.issubset(names)
    ver = reg._conn.execute(
        "SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
    assert ver[0] == work_units.WORK_UNITS_REGISTRY_VERSION
    assert reg.schema_unsupported is None
    reg.close()


def test_reopen_is_clean_and_additive(tmp_path):
    work_units.WorkUnitRegistry(tmp_path / "work_units.db").close()
    reg = work_units.WorkUnitRegistry(tmp_path / "work_units.db")  # no error second time
    assert reg.schema_unsupported is None
    reg.close()


def test_wrong_version_db_fails_closed(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('work_units_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported == "p0.legacy"
    reg.close()


# ----- Task 2: register + many-to-many links -----
def test_register_link_and_work_unit_centric_read(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.register_work_unit("facade-study", label="Facade", role="study", metadata=None, now=100)
    reg.link_artifact("facade-study", "artA", "produced", now=101)
    reg.link_artifact("facade-study", "artB", "produced", now=102)
    reg.link_artifact("facade-study", "master", "consumed", now=103)
    assert reg.get_work_unit("facade-study").label == "Facade"
    assert {(a, rel) for a, rel in reg.artifacts_for("facade-study")} == {
        ("artA", "produced"), ("artB", "produced"), ("master", "consumed")}
    reg.register_work_unit("ctx", label="Context", role=None, metadata=None, now=110)
    reg.link_artifact("ctx", "artA", "consumed", now=111)
    assert {wu for wu, _ in reg.work_units_for_artifact("artA")} == {"facade-study", "ctx"}
    reg.close()


# ----- Task 3: present-bar / link-bar against a REAL P6 registry -----
def _p6_with(tmp_path, monkeypatch, present_names):
    """Point P6 at a throwaway artifacts.db (monkeypatch auto-restores); register real present
    files; return ({name: artifact_id}, {name: path})."""
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    ids = {}
    for name in present_names:
        f = tmp_path / name
        f.write_text("x")
        norm = artifacts.normalize_path(str(f))
        artifacts.artifact_registry().upsert(norm, source="explicit", file_state="present",
            size=1, mtime=1, document_name=None, origin_session_id=None, label=None, now=int(_time.time()))
        ids[name] = artifacts.artifact_id_for(norm)
    return ids, {name: tmp_path / name for name in present_names}


def test_resolve_present_flags_registered_and_present(tmp_path, monkeypatch):
    ids, files = _p6_with(tmp_path, monkeypatch, ["a.3dm", "b.3dm"])
    assert work_units._resolve_present([ids["a.3dm"], ids["b.3dm"]]) == []
    assert work_units._resolve_present(["deadbeef"]) == [{"code": "artifact_not_registered", "artifactId": "deadbeef"}]
    files["a.3dm"].unlink()
    artifacts.artifact_registry().set_state(
        artifacts.normalize_path(str(files["a.3dm"])), file_state="missing", size=None, mtime=None,
        now=int(_time.time()))
    assert work_units._resolve_present([ids["a.3dm"]]) == [{"code": "artifact_not_present", "artifactId": ids["a.3dm"]}]


# ----- Task 4: cycle helper + atomic insert_contract with pre-check -----
def test_contract_cycle_helper():
    assert work_units._contract_cycle([("c1", "M1", ["A", "B"]), ("c2", "MASTER", ["M1", "C"])]) is None
    cyc = work_units._contract_cycle([("cX", "A", ["B"]), ("cY", "B", ["A"])])
    assert cyc is not None and set(cyc) == {"cX", "cY"}


def test_insert_contract_atomic_and_rejects_cycle(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.register_work_unit("wu", label="W", role=None, metadata=None, now=1)
    reg.insert_contract("c1", target="M", sources=["A", "B"], merge_kind="linked_block",
                        refresh_policy="refresh_after_save", work_unit_id="wu", now=10)
    assert reg.get_contract("c1").target_artifact_id == "M"
    assert set(reg.sources_for("c1")) == {"A", "B"}
    assert reg.contracts_for("wu") == ["c1"]
    with pytest.raises(work_units.ContractCycleError):
        reg.insert_contract("c2", target="A", sources=["M"], merge_kind="reference",
                            refresh_policy="refresh_on_demand", work_unit_id=None, now=11)
    assert {r.contract_id for r in reg.list_contracts()} == {"c1"}
    assert reg.sources_for("c2") == []
    reg.insert_contract("c3", target="FINAL", sources=["M"], merge_kind="import",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=12)
    assert {r.contract_id for r in reg.list_contracts()} == {"c1", "c3"}
    reg.close()


# ----- Task 5: pure graph validator -----
def test_validate_graph_order_determinism_and_cycle(tmp_path, monkeypatch):
    ids, _ = _p6_with(tmp_path, monkeypatch, ["A.3dm", "B.3dm", "C.3dm", "M1.3dm", "master.3dm"])
    reg = _fresh_registry(tmp_path)
    A, B, C, M1, MASTER = (ids["A.3dm"], ids["B.3dm"], ids["C.3dm"], ids["M1.3dm"], ids["master.3dm"])
    reg.insert_contract("c_stage2", target=MASTER, sources=[M1, C], merge_kind="import",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=20)
    reg.insert_contract("c_stage1", target=M1, sources=[A, B], merge_kind="linked_block",
                        refresh_policy="refresh_after_save", work_unit_id=None, now=10)
    res = work_units._validate_graph(reg)
    assert res["ok"] is True
    assert res["contractOrder"] == ["c_stage1", "c_stage2"]
    assert work_units._validate_graph(reg)["contractOrder"] == res["contractOrder"]   # determinism

    # _validate_graph DEFENDS against a cyclic graph even though insert_contract's pre-check prevents
    # creating one normally (e.g. an externally-edited db). Insert cyclic rows RAW to bypass the pre-check.
    reg2 = _fresh_registry(tmp_path / "two")
    with reg2._immediate():
        for cid, tgt, src in [("cX", A, B), ("cY", B, A)]:
            reg2._conn.execute(
                "INSERT INTO merge_contracts(contract_id, target_artifact_id, merge_kind, "
                "refresh_policy, created_at) VALUES(?,?,?,?,?);",
                (cid, tgt, "reference", "refresh_on_demand", 1))
            reg2._conn.execute(
                "INSERT INTO merge_contract_sources(contract_id, source_artifact_id) VALUES(?,?);",
                (cid, src))
    res2 = work_units._validate_graph(reg2)
    assert res2["ok"] is False
    assert any(p["code"] == "merge_cycle_detected" for p in res2["problems"])


# ----- Task 6: async tool functions -----
def _repoint_p7(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()


def test_tools_record_rejects_and_validates(tmp_path, monkeypatch):
    ids, files = _p6_with(tmp_path, monkeypatch, ["A.3dm", "B.3dm", "M.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    A, B, M = ids["A.3dm"], ids["B.3dm"], ids["M.3dm"]

    reg_wu = asyncio.run(work_units.register_work_unit_tool(label="W", role=None, metadata=None, work_unit_id="wu"))
    assert reg_wu["success"] is True and reg_wu["data"]["workUnitId"] == "wu"

    bad = asyncio.run(work_units.record_merge_contract(target_artifact_id=M,
        source_artifact_ids=[A, "ghost"], merge_kind="linked_block",
        refresh_policy="refresh_after_save", work_unit_id=None))
    assert bad["success"] is False and bad["data"]["code"] == "artifact_not_registered"
    assert work_units.work_units_registry().list_contracts() == []   # atomicity

    dup = asyncio.run(work_units.record_merge_contract(target_artifact_id=M,
        source_artifact_ids=[A, A], merge_kind="linked_block",
        refresh_policy="refresh_after_save", work_unit_id=None))
    assert dup["success"] is False and dup["data"]["code"] == "duplicate_contract_source"

    ok = asyncio.run(work_units.record_merge_contract(target_artifact_id=M,
        source_artifact_ids=[A, B], merge_kind="linked_block",
        refresh_policy="refresh_after_save", work_unit_id="wu"))
    assert ok["success"] is True
    cid = ok["data"]["contractId"]

    cyc = asyncio.run(work_units.record_merge_contract(target_artifact_id=A,
        source_artifact_ids=[M], merge_kind="reference", refresh_policy="refresh_on_demand",
        work_unit_id=None))
    assert cyc["success"] is False and cyc["data"]["code"] == "merge_cycle_detected"
    assert {r.contract_id for r in work_units.work_units_registry().list_contracts()} == {cid}   # atomic

    val = asyncio.run(work_units.validate_merge_contract(contract_id=None))
    assert val["success"] is True and val["data"]["ok"] is True
    assert val["data"]["contractOrder"] == [cid]

    wu = asyncio.run(work_units.list_work_units_tool(work_unit_id="wu"))
    assert wu["data"]["workUnits"][0]["contracts"] == [cid]

    nf = asyncio.run(work_units.validate_merge_contract(contract_id="nope"))
    assert nf["success"] is False and nf["data"]["code"] == "contract_not_found"


# ----- review-fix round (Codex findings) -----
def test_malformed_existing_table_fails_closed(tmp_path):
    # Finding 1: a foreign 'work_units' table (missing required columns) with NO version meta must
    # fail closed to schema_unsupported, not crash later reads.
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE work_units (id TEXT, junk TEXT);")
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported == "unknown"
    reg.close()


def test_p6_unusable_fails_closed(tmp_path, monkeypatch):
    # Finding 2: a version-skewed P6 registry -> P7 tools that resolve artifacts fail closed
    # structured (artifact_registry_unavailable), never crash.
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    raw = sqlite3.connect(str(tmp_path / "artifacts.db"))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('artifact_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    artifacts._reset_artifact_registry_singleton()
    _repoint_p7(tmp_path, monkeypatch)
    out = asyncio.run(work_units.record_merge_contract(target_artifact_id="x", source_artifact_ids=["y"],
        merge_kind="import", refresh_policy="refresh_on_demand", work_unit_id=None))
    assert out["success"] is False and out["data"]["code"] == "artifact_registry_unavailable"
    val = asyncio.run(work_units.validate_merge_contract(contract_id=None))
    assert val["success"] is False and val["data"]["code"] == "artifact_registry_unavailable"


def test_record_rejects_non_list_sources(tmp_path, monkeypatch):
    # Finding 3: a bare string must NOT be coerced into character sources.
    ids, _ = _p6_with(tmp_path, monkeypatch, ["A.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    out = asyncio.run(work_units.record_merge_contract(target_artifact_id=ids["A.3dm"],
        source_artifact_ids="abc", merge_kind="import", refresh_policy="refresh_on_demand", work_unit_id=None))
    assert out["success"] is False and out["data"]["code"] == "invalid_argument"
    out2 = asyncio.run(work_units.record_merge_contract(target_artifact_id=ids["A.3dm"],
        source_artifact_ids=["", "x"], merge_kind="import", refresh_policy="refresh_on_demand", work_unit_id=None))
    assert out2["success"] is False and out2["data"]["code"] == "invalid_argument"


def test_validate_scoped_to_one_contract(tmp_path, monkeypatch):
    # Finding 4: validate(contractId) scopes to that contract; an unrelated broken contract must not
    # fail a valid one.
    ids, files = _p6_with(tmp_path, monkeypatch, ["A.3dm", "B.3dm", "M.3dm", "X.3dm", "Y.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    A, B, M, X, Y = (ids[n] for n in ["A.3dm", "B.3dm", "M.3dm", "X.3dm", "Y.3dm"])
    good = asyncio.run(work_units.record_merge_contract(target_artifact_id=M, source_artifact_ids=[A, B],
        merge_kind="linked_block", refresh_policy="refresh_after_save", work_unit_id=None))["data"]["contractId"]
    other = asyncio.run(work_units.record_merge_contract(target_artifact_id=Y, source_artifact_ids=[X],
        merge_kind="import", refresh_policy="refresh_on_demand", work_unit_id=None))["data"]["contractId"]
    # break the OTHER contract: X goes missing in P6
    files["X.3dm"].unlink()
    artifacts.artifact_registry().set_state(artifacts.normalize_path(str(files["X.3dm"])),
        file_state="missing", size=None, mtime=None, now=int(_time.time()))
    # whole-graph -> ok:false (the OTHER contract's source is missing)
    whole = asyncio.run(work_units.validate_merge_contract(contract_id=None))
    assert whole["data"]["ok"] is False
    # scoped to the GOOD contract -> ok:true (NOT polluted by the other)
    one = asyncio.run(work_units.validate_merge_contract(contract_id=good))
    assert one["data"]["ok"] is True and one["data"]["contractId"] == good
    # scoped to the OTHER -> ok:false with its own present-bar problem
    bad = asyncio.run(work_units.validate_merge_contract(contract_id=other))
    assert bad["data"]["ok"] is False
    assert any(p["code"] == "artifact_not_present" for p in bad["data"]["problems"])


def test_validate_independent_contracts_tiebreak_order(tmp_path, monkeypatch):
    # Two INDEPENDENT contracts (no shared artifact -> no edge). contractOrder must follow the
    # (created_at, contract_id) tiebreak, NOT insertion order — the deterministic-ordering guarantee.
    ids, _ = _p6_with(tmp_path, monkeypatch, ["P.3dm", "Q.3dm", "R.3dm", "S.3dm"])
    reg = _fresh_registry(tmp_path)
    P, Q, R, S = (ids[n] for n in ["P.3dm", "Q.3dm", "R.3dm", "S.3dm"])
    reg.insert_contract("c_late", target=Q, sources=[P], merge_kind="import",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=200)
    reg.insert_contract("c_early", target=S, sources=[R], merge_kind="import",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=100)
    res = work_units._validate_graph(reg)
    assert res["ok"] is True
    assert res["edges"] == []                                  # independent: no edges between them
    assert res["contractOrder"] == ["c_early", "c_late"]       # created_at 100 before 200, not insert order
    reg.close()
