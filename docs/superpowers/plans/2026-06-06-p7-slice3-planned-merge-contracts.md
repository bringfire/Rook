# P7 Slice 3 — Planned Merge Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `planned_merge_contracts` table family that records a future fan-in graph over typed refs (`artifact:`/`declared_target:`) with topology over a canonical future-artifact key, plus an idempotent, fail-closed `activate` bridge that turns one planned contract into a strict Slice-1 `merge_contract` in a single atomic P7 transaction — `merge_contracts` untouched, no execution, no geometry, zero P6 writes.

**Architecture:** Extends the leaf `mcp_server/src/rook/work_units.py` and its `work_units.db` with three new tables and three non-routed MCP tools, reusing the existing `_contract_graph`/`_contract_cycle` topo helpers (over canonical keys) and the `insert_contract` strict-insert pattern (extended with an in-transaction CAS). Schema advances `p7.2 → p7.3` via the additive supported-set migration Slice 2 established.

**Tech Stack:** Python 3 (`from __future__ import annotations`), stdlib `sqlite3`, `networkx` (already a dep), `pytest`. Editable install — pure-Python edits need **no rebuild** for unit tests.

**Spec:** `docs/superpowers/specs/2026-06-06-p7-slice3-planned-merge-contracts-design.md` (on main+origin at `ed68fcf`).

**Pytest:** `mcp_server/.venv/Scripts/python.exe -m pytest`

---

## Pre-flight

- [ ] **Create the feature branch off main**

```bash
git checkout main && git pull
git checkout -b feature/p7-slice3-planned-contracts
```

## File structure

| File | Responsibility | Change |
|---|---|---|
| `mcp_server/src/rook/work_units.py` | P7 registry leaf | Modify: version+migration, 3 tables, `PlannedContractRow`, `PlannedContractCycle`/`PlannedContractInvalid`, canonical-key + blocker + state helpers, 8 registry methods, 3 tool fns, `_RETRYABLE`, `list_work_units_tool` join |
| `mcp_server/src/rook/server.py` | MCP decls + dispatch | Modify: 3 `Tool(...)` decls + 3 `case` arms after the Slice-2 P7 tools |
| `mcp_server/src/rook/targeting.py` | Tool classification | Modify: 3 names into `_ALL_KNOWN_TOOLS` + `_META_TOOLS` |
| `mcp_server/tests/test_work_units.py` | P7 unit tests | Add: schema/migration, registry, record, activation-helpers, activate, inspector tests |
| `mcp_server/tests/test_work_units_tools.py` | tool-classification tests | Add: meta/no-Rhino + `call_tool` dispatch for the 3 new tools |

**Naming contract (used across tasks):** `REF_KINDS = ("artifact", "declared_target")`; ids `pc-<uuid12>` (planned) and `mc-<uuid12>` (strict, reused). Registry methods: `insert_planned_contract`, `get_planned_contract`, `list_planned_contracts`, `sources_for_planned`, `planned_contracts_for`, `work_units_for_planned_contract`, `activate_planned_contract`. Module helpers: `_planned_artifact_key`, `_planned_key_or_sentinel`, `_planned_graph_pairs`, `_classify_planned_state`, `_planned_structural_problems`, `_resolve_planned_ref_present`, `_blk`, `_activation_blockers`, `_observe_planned_contract`, `_planned_graph_view`, `_parse_ref`. Tools: `record_planned_contract`, `activate_planned_contract_tool`, `list_planned_contracts_tool`.

---

## Task 1: Schema + additive `p7.2→p7.3` (and `p7.1→p7.3`) migration

**Files:** Modify `mcp_server/src/rook/work_units.py`; Test `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests** (append to `test_work_units.py`)

```python
# ----- P7 Slice 3: planned-contract schema + migration -----
def test_planned_tables_created_at_p73(tmp_path):
    reg = _fresh_registry(tmp_path)
    names = {r[0] for r in reg._conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert {"planned_merge_contracts", "planned_merge_contract_sources",
            "work_unit_planned_merge_contracts"}.issubset(names)
    ver = reg._conn.execute("SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
    assert ver[0] == "p7.3" == work_units.WORK_UNITS_REGISTRY_VERSION
    reg.close()


def test_additive_migration_p72_to_p73(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('work_units_registry_version','p7.2');")
    for ddl in (
        "CREATE TABLE work_units (work_unit_id TEXT PRIMARY KEY, label TEXT NOT NULL, role TEXT, metadata TEXT, created_at INTEGER NOT NULL)",
        "CREATE TABLE work_unit_artifacts (work_unit_id TEXT NOT NULL, artifact_id TEXT NOT NULL, relation TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(work_unit_id, artifact_id, relation))",
        "CREATE TABLE merge_contracts (contract_id TEXT PRIMARY KEY, target_artifact_id TEXT NOT NULL, merge_kind TEXT NOT NULL, refresh_policy TEXT NOT NULL, created_at INTEGER NOT NULL)",
        "CREATE TABLE merge_contract_sources (contract_id TEXT NOT NULL, source_artifact_id TEXT NOT NULL, PRIMARY KEY(contract_id, source_artifact_id))",
        "CREATE TABLE work_unit_merge_contracts (work_unit_id TEXT NOT NULL, contract_id TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(work_unit_id, contract_id))",
        "CREATE TABLE declared_targets (declared_target_id TEXT PRIMARY KEY, work_unit_id TEXT, intended_path TEXT NOT NULL, normalized_path TEXT NOT NULL, predicted_artifact_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL, bound_artifact_id TEXT, label TEXT, created_at INTEGER NOT NULL, materialized_at INTEGER)",
    ):
        raw.execute(ddl)
    raw.execute("INSERT INTO merge_contracts VALUES('mc-keep','A','import','refresh_on_demand',1);")
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported is None
    names = {r[0] for r in reg._conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "planned_merge_contracts" in names
    assert reg._conn.execute("SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()[0] == "p7.3"
    assert reg.get_contract("mc-keep").target_artifact_id == "A"   # existing data intact
    reg.close()


def test_additive_migration_p71_to_p73_creates_slice2_and_slice3(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('work_units_registry_version','p7.1');")
    raw.execute("CREATE TABLE work_units (work_unit_id TEXT PRIMARY KEY, label TEXT NOT NULL, role TEXT, metadata TEXT, created_at INTEGER NOT NULL);")
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported is None
    names = {r[0] for r in reg._conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "declared_targets" in names and "planned_merge_contracts" in names   # both created
    assert reg._conn.execute("SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()[0] == "p7.3"
    reg.close()


def test_malformed_planned_table_fails_closed(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE planned_merge_contracts (id TEXT, junk TEXT);")
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported == "unknown"
    reg.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "p73 or migration_p7 or malformed_planned" -v`
Expected: FAIL — planned tables absent; version still `p7.2`.

- [ ] **Step 3: Bump version + supported-set + REF_KINDS**

In `work_units.py`, change the version line + supported-set (currently `"p7.2"` / `{"p7.1"}`):
```python
WORK_UNITS_REGISTRY_VERSION = "p7.3"
_SUPPORTED_PRIOR_VERSIONS = frozenset({"p7.1", "p7.2"})
```
Add next to `MERGE_KINDS`/`REFRESH_POLICIES`/`RELATIONS`:
```python
REF_KINDS = ("artifact", "declared_target")
```

- [ ] **Step 4: Add the three `_REQUIRED_COLUMNS` entries** (after the `declared_targets` entry)

```python
    "planned_merge_contracts": {"planned_contract_id", "target_ref_kind", "target_ref_id", "merge_kind",
                                "refresh_policy", "status", "activated_contract_id", "activated_at", "created_at"},
    "planned_merge_contract_sources": {"planned_contract_id", "source_ref_kind", "source_ref_id"},
    "work_unit_planned_merge_contracts": {"work_unit_id", "planned_contract_id", "created_at"},
```

- [ ] **Step 5: Create the three tables + two indexes in `_ensure_schema`**

After the `declared_targets` index line (`CREATE INDEX IF NOT EXISTS idx_declared_targets_work_unit ...`) and before `idx_wua_wu`:
```python
        c.execute("""CREATE TABLE IF NOT EXISTS planned_merge_contracts (
            planned_contract_id TEXT PRIMARY KEY, target_ref_kind TEXT NOT NULL, target_ref_id TEXT NOT NULL,
            merge_kind TEXT NOT NULL, refresh_policy TEXT NOT NULL, status TEXT NOT NULL,
            activated_contract_id TEXT, activated_at INTEGER, created_at INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS planned_merge_contract_sources (
            planned_contract_id TEXT NOT NULL, source_ref_kind TEXT NOT NULL, source_ref_id TEXT NOT NULL,
            PRIMARY KEY (planned_contract_id, source_ref_kind, source_ref_id));""")
        c.execute("""CREATE TABLE IF NOT EXISTS work_unit_planned_merge_contracts (
            work_unit_id TEXT NOT NULL, planned_contract_id TEXT NOT NULL, created_at INTEGER NOT NULL,
            PRIMARY KEY (work_unit_id, planned_contract_id));""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pmcs_contract ON planned_merge_contract_sources(planned_contract_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wupmc_wu ON work_unit_planned_merge_contracts(work_unit_id);")
```
(The meta-upgrade tail `if stored is None or stored[0] != WORK_UNITS_REGISTRY_VERSION` already migrates the version forward — no change needed.)

- [ ] **Step 6: Add the `PlannedContractRow` dataclass + column constant** (after `DeclaredTargetRow`)

```python
_PLANNED_CONTRACT_COLUMNS = ("planned_contract_id, target_ref_kind, target_ref_id, merge_kind, "
                             "refresh_policy, status, activated_contract_id, activated_at, created_at")


@dataclass(frozen=True)
class PlannedContractRow:
    planned_contract_id: str
    target_ref_kind: str
    target_ref_id: str
    merge_kind: str
    refresh_policy: str
    status: str
    activated_contract_id: str | None
    activated_at: int | None
    created_at: int
```

- [ ] **Step 7: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -q`
Expected: PASS (34 Slice-1/2 + 4 new = 38).

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S3 T1: planned-contract schema + additive p7.2->p7.3 migration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Canonical-key helpers + record-side registry methods

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
# ----- P7 Slice 3: canonical key + record-side registry -----
def test_planned_artifact_key_projection(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.insert_declared_target("dt-m", work_unit_id=None, intended_path="C:/m.3dm",
        normalized_path="c:\\m.3dm", predicted_artifact_id="pred-m", label=None, now=1)
    assert work_units._planned_artifact_key(reg, "artifact", "aid-1") == ("aid-1", None)
    assert work_units._planned_artifact_key(reg, "declared_target", "dt-m") == ("pred-m", None)
    key, prob = work_units._planned_artifact_key(reg, "declared_target", "dt-nope")
    assert key is None and prob["code"] == "declared_target_not_found"
    reg.close()


def test_insert_planned_contract_and_reads(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.register_work_unit("wu", label="W", role=None, metadata=None, now=1)
    reg.insert_planned_contract("pc1", target_ref_kind="artifact", target_ref_id="M",
        sources=[("artifact", "A"), ("declared_target", "dt-x")], merge_kind="import",
        refresh_policy="refresh_on_demand", work_unit_id="wu", now=10)
    row = reg.get_planned_contract("pc1")
    assert row.status == "planned" and row.activated_contract_id is None and row.activated_at is None
    assert reg.sources_for_planned("pc1") == [("artifact", "A"), ("declared_target", "dt-x")]
    assert reg.planned_contracts_for("wu") == ["pc1"]
    assert reg.work_units_for_planned_contract("pc1") == ["wu"]
    assert [r.planned_contract_id for r in reg.list_planned_contracts()] == ["pc1"]
    reg.close()


def test_insert_planned_contract_rejects_canonical_cycle(tmp_path):
    # canonical keys: pc1 target M, source A; pc2 target A, source M -> cycle over keys.
    reg = _fresh_registry(tmp_path)
    reg.insert_planned_contract("pc1", target_ref_kind="artifact", target_ref_id="M",
        sources=[("artifact", "A")], merge_kind="import", refresh_policy="refresh_on_demand",
        work_unit_id=None, now=1)
    with pytest.raises(work_units.PlannedContractCycle):
        reg.insert_planned_contract("pc2", target_ref_kind="artifact", target_ref_id="A",
            sources=[("artifact", "M")], merge_kind="import", refresh_policy="refresh_on_demand",
            work_unit_id=None, now=2)
    assert [r.planned_contract_id for r in reg.list_planned_contracts()] == ["pc1"]  # atomic
    reg.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "planned_artifact_key or insert_planned_contract" -v`
Expected: FAIL — helpers/methods undefined.

- [ ] **Step 3: Add `PlannedContractCycle` + canonical-key module helpers** (next to `ContractCycleError`/`DeclaredTargetConflict`)

```python
class PlannedContractCycle(RuntimeError):
    """insert_planned_contract's atomic pre-check: the candidate would make the canonical planned graph cyclic."""
    def __init__(self, cycle: "list[str]"):
        super().__init__("planned_contract_cycle_detected")
        self.cycle = cycle


class PlannedContractInvalid(RuntimeError):
    """activate_planned_contract's in-tx CAS: the planned row violates the stored-state invariant."""
    pass
```
And (in the "shared contract-graph helpers" region, after `_contract_cycle`):
```python
def _planned_artifact_key(reg, ref_kind: str, ref_id: str) -> "tuple[str | None, dict | None]":
    """Project a typed ref to its canonical FUTURE-ARTIFACT key: artifact -> the artifact id itself;
    declared_target -> its predicted_artifact_id. Returns (key, None) or (None, problem)."""
    if ref_kind == "artifact":
        return ref_id, None
    if ref_kind == "declared_target":
        dt = reg.get_declared_target(ref_id)
        if dt is None:
            return None, {"code": "declared_target_not_found", "ref": {"kind": ref_kind, "id": ref_id}}
        return dt.predicted_artifact_id, None
    return None, {"code": "invalid_ref_kind", "ref": {"kind": ref_kind, "id": ref_id}}


def _planned_key_or_sentinel(reg, ref_kind: str, ref_id: str) -> str:
    """Canonical key for graph building; an unresolvable ref gets a unique sentinel so it never falsely
    unifies with another node (defensive — record validates resolution before persisting)."""
    key, _ = _planned_artifact_key(reg, ref_kind, ref_id)
    return key if key is not None else f"__unresolved__:{ref_kind}:{ref_id}"


def _planned_graph_pairs(reg) -> "list[tuple]":
    """(planned_contract_id, target_key, [source_keys]) over canonical keys, for ALL planned rows
    (planned AND activated)."""
    pairs = []
    for pc in reg.list_planned_contracts():
        tkey = _planned_key_or_sentinel(reg, pc.target_ref_kind, pc.target_ref_id)
        skeys = [_planned_key_or_sentinel(reg, k, i) for k, i in reg.sources_for_planned(pc.planned_contract_id)]
        pairs.append((pc.planned_contract_id, tkey, skeys))
    return pairs
```

- [ ] **Step 4: Add the record-side registry methods** (inside `WorkUnitRegistry`, after `declared_targets_for`)

```python
    # ----- planned merge contracts (P7 Slice 3) -----
    def insert_planned_contract(self, planned_contract_id: str, *, target_ref_kind: str, target_ref_id: str,
                                sources: "list[tuple[str, str]]", merge_kind: str, refresh_policy: str,
                                work_unit_id: str | None, now: int) -> str:
        """ONE tx: canonical cycle pre-check over existing + candidate (shared _contract_cycle) ->
        PlannedContractCycle (ROLLBACK, nothing written); else insert planned row + sources + optional
        ownership link. Re-entrant reads (list_planned_contracts/sources_for_planned) are RLock-safe."""
        with self._immediate():
            pairs = _planned_graph_pairs(self)
            cand_tkey = _planned_key_or_sentinel(self, target_ref_kind, target_ref_id)
            cand_skeys = [_planned_key_or_sentinel(self, k, i) for k, i in sources]
            pairs.append((planned_contract_id, cand_tkey, cand_skeys))
            cycle = _contract_cycle(pairs)
            if cycle is not None:
                raise PlannedContractCycle(cycle)
            self._conn.execute(
                "INSERT INTO planned_merge_contracts(planned_contract_id, target_ref_kind, target_ref_id, "
                "merge_kind, refresh_policy, status, activated_contract_id, activated_at, created_at) "
                "VALUES(?,?,?,?,?,'planned',NULL,NULL,?);",
                (planned_contract_id, target_ref_kind, target_ref_id, merge_kind, refresh_policy, now))
            self._conn.executemany(
                "INSERT INTO planned_merge_contract_sources(planned_contract_id, source_ref_kind, source_ref_id) "
                "VALUES(?,?,?);", [(planned_contract_id, k, i) for k, i in sources])
            if work_unit_id is not None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO work_unit_planned_merge_contracts(work_unit_id, planned_contract_id, "
                    "created_at) VALUES(?,?,?);", (work_unit_id, planned_contract_id, now))
        return planned_contract_id

    def get_planned_contract(self, planned_contract_id: str) -> "PlannedContractRow | None":
        with self._lock:
            raw = self._conn.execute(
                f"SELECT {_PLANNED_CONTRACT_COLUMNS} FROM planned_merge_contracts WHERE planned_contract_id=?;",
                (planned_contract_id,)).fetchone()
            return None if raw is None else PlannedContractRow(*raw)

    def list_planned_contracts(self) -> "list[PlannedContractRow]":
        with self._lock:
            return [PlannedContractRow(*r) for r in self._conn.execute(
                f"SELECT {_PLANNED_CONTRACT_COLUMNS} FROM planned_merge_contracts "
                "ORDER BY created_at, planned_contract_id;").fetchall()]

    def sources_for_planned(self, planned_contract_id: str) -> "list[tuple[str, str]]":
        with self._lock:
            return [(k, i) for k, i in self._conn.execute(
                "SELECT source_ref_kind, source_ref_id FROM planned_merge_contract_sources "
                "WHERE planned_contract_id=? ORDER BY source_ref_kind, source_ref_id;",
                (planned_contract_id,)).fetchall()]

    def planned_contracts_for(self, work_unit_id: str) -> "list[str]":
        with self._lock:
            return [p for (p,) in self._conn.execute(
                "SELECT planned_contract_id FROM work_unit_planned_merge_contracts WHERE work_unit_id=? "
                "ORDER BY created_at, planned_contract_id;", (work_unit_id,)).fetchall()]

    def work_units_for_planned_contract(self, planned_contract_id: str) -> "list[str]":
        with self._lock:
            return [w for (w,) in self._conn.execute(
                "SELECT work_unit_id FROM work_unit_planned_merge_contracts WHERE planned_contract_id=? "
                "ORDER BY work_unit_id;", (planned_contract_id,)).fetchall()]
```

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "planned_artifact_key or insert_planned_contract" -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S3 T2: canonical-key helpers + record-side planned-contract registry methods

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `record` tool — conditional P6 guard (refs parsed FIRST), two bars, atomic

**Files:** Modify `work_units.py`; Test `test_work_units.py`

> **HARD ORDERING RULE (do not violate):** `record` must parse/validate refs and derive `has_artifact_ref`
> **before** calling `_p6_unusable()`. A P6 guard at the top of `record` would wrongly block an
> all-`declared_target:` planned contract under P6 skew. The dedicated test below pins this.

- [ ] **Step 1: Write the failing tests**

```python
# ----- P7 Slice 3: record tool -----
def test_record_planned_contract_happy(tmp_path, monkeypatch):
    ids, _ = _p6_with(tmp_path, monkeypatch, ["A.3dm"])   # A registered+present
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "M.3dm")))
    dt = asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"][0]["declaredTargetId"]
    out = asyncio.run(work_units.record_planned_contract(
        target={"kind": "declared_target", "id": dt},
        sources=[{"kind": "artifact", "id": ids["A.3dm"]}],
        merge_kind="import", refresh_policy="refresh_on_demand"))
    assert out["success"] is True and out["data"]["status"] == "planned"
    assert out["data"]["plannedContractId"].startswith("pc-")


def test_record_rejects_bad_refs_and_structural(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    bad_kind = asyncio.run(work_units.record_planned_contract(target={"kind": "bogus", "id": "x"},
        sources=[{"kind": "artifact", "id": "a"}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert bad_kind["success"] is False and bad_kind["data"]["code"] == "invalid_ref_kind"
    empty = asyncio.run(work_units.record_planned_contract(target={"kind": "artifact", "id": "a"},
        sources=[], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert empty["success"] is False and empty["data"]["code"] == "empty_sources"
    dangling = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": "dt-nope"},
        sources=[{"kind": "declared_target", "id": "dt-nope2"}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert dangling["success"] is False and dangling["data"]["code"] == "declared_target_not_found"


def test_record_canonical_self_reference_cross_kind(tmp_path, monkeypatch):
    # LOAD-BEARING: target declared_target:dtM and source artifact:<dtM.predicted_artifact_id> collapse to
    # the SAME canonical key -> planned_self_reference. An impl that compared (kind,id) instead of the
    # canonical artifact key would WRONGLY accept this. Register the artifact first so the link-bar passes
    # and the only possible rejection is the canonical self-reference.
    ids, files = _p6_with(tmp_path, monkeypatch, ["M.3dm"])    # M registered+present; id == hash(M path)
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(files["M.3dm"])))  # predicted == ids["M.3dm"]
    dtm = asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"][0]["declaredTargetId"]
    out = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dtm},
        sources=[{"kind": "artifact", "id": ids["M.3dm"]}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert out["success"] is False and out["data"]["code"] == "planned_self_reference"


def test_record_canonical_duplicate_source_cross_kind(tmp_path, monkeypatch):
    # sources [declared_target:dtM, artifact:<dtM.predicted>] resolve to the SAME canonical key under a
    # DIFFERENT target -> duplicate_planned_source (again pins canonical-key, not (kind,id), comparison).
    ids, files = _p6_with(tmp_path, monkeypatch, ["M.3dm", "F.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(files["M.3dm"])))
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(files["F.3dm"])))
    dts = {d["intendedPath"]: d["declaredTargetId"]
           for d in asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"]}
    dtm = [v for k, v in dts.items() if k.endswith("M.3dm")][0]
    dtf = [v for k, v in dts.items() if k.endswith("F.3dm")][0]
    out = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dtf},
        sources=[{"kind": "declared_target", "id": dtm}, {"kind": "artifact", "id": ids["M.3dm"]}],
        merge_kind="import", refresh_policy="refresh_on_demand"))
    assert out["success"] is False and out["data"]["code"] == "duplicate_planned_source"


def test_record_artifact_linkbar_registered_not_present(tmp_path, monkeypatch):
    ids, files = _p6_with(tmp_path, monkeypatch, ["A.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    # registered + missing on disk -> still ACCEPTED at record (link-bar, present not required)
    files["A.3dm"].unlink()
    artifacts.artifact_registry().set_state(artifacts.normalize_path(str(files["A.3dm"])),
        file_state="missing", size=None, mtime=None, now=1)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "M.3dm")))
    dt = asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"][0]["declaredTargetId"]
    ok = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt},
        sources=[{"kind": "artifact", "id": ids["A.3dm"]}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert ok["success"] is True
    # unregistered artifact -> rejected
    bad = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt},
        sources=[{"kind": "artifact", "id": "ghost-id"}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert bad["success"] is False and bad["data"]["code"] == "artifact_not_registered"


def test_record_conditional_p6_guard(tmp_path, monkeypatch):
    # version-skewed P6: all-declared_target record SUCCEEDS (P7-only); any artifact ref FAILS.
    raw = sqlite3.connect(str(tmp_path / "artifacts.db"))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('artifact_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "M.3dm")))
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "L.3dm")))
    dts = [d["declaredTargetId"] for d in asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"]]
    ok = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dts[0]},
        sources=[{"kind": "declared_target", "id": dts[1]}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert ok["success"] is True   # all-declared_target proceeds under P6 skew
    bad = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dts[0]},
        sources=[{"kind": "artifact", "id": "some-id"}], merge_kind="import", refresh_policy="refresh_on_demand"))
    assert bad["success"] is False and bad["data"]["code"] == "artifact_registry_unavailable"
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_record_" -v`
Expected: FAIL — `record_planned_contract` undefined.

- [ ] **Step 3: Extend `_RETRYABLE`** (add to the dict)

```python
    "invalid_ref_kind": False, "duplicate_planned_source": False, "planned_self_reference": False,
    "declared_target_bound_missing": False, "declared_target_bound_identity_changed": False,
    "declared_target_bound_not_present": True,
    "planned_contract_not_found": False, "planned_contract_cycle_detected": False,
    "strict_merge_cycle_detected": False, "planned_contract_already_invalid": False,
    "planned_contract_not_activatable": False, "artifact_registry_unavailable": True,
```

- [ ] **Step 4: Add `_parse_ref` + `_planned_structural_problems` + `record_planned_contract`**

Module helpers (near the other `_planned_*` helpers):
```python
def _planned_structural_problems(target_key: str, source_keys: "list[str]", merge_kind: str,
                                 refresh_policy: str) -> "list[dict[str, Any]]":
    problems: list[dict[str, Any]] = []
    if not source_keys:
        problems.append({"code": "empty_sources"})
    if len(source_keys) != len(set(source_keys)):
        problems.append({"code": "duplicate_planned_source"})
    if merge_kind not in MERGE_KINDS:
        problems.append({"code": "unknown_merge_kind", "value": merge_kind})
    if refresh_policy not in REFRESH_POLICIES:
        problems.append({"code": "unknown_refresh_policy", "value": refresh_policy})
    if target_key in source_keys:
        problems.append({"code": "planned_self_reference"})
    return problems


def _parse_ref(ref) -> "tuple[tuple[str, str] | None, dict | None]":
    """Validate a typed-ref object {kind, id}. Returns ((kind, id), None) or (None, {code, message})."""
    if not isinstance(ref, dict):
        return None, {"code": "invalid_argument", "message": "ref must be an object {kind, id}."}
    kind, rid = ref.get("kind"), ref.get("id")
    if not isinstance(rid, str) or not rid.strip():
        return None, {"code": "invalid_argument", "message": "ref 'id' must be a non-empty string."}
    if kind not in REF_KINDS:
        return None, {"code": "invalid_ref_kind", "message": f"ref 'kind' must be one of {REF_KINDS}.", "value": kind}
    return (kind, rid), None
```
Tool (after `list_declared_targets_tool`):
```python
async def record_planned_contract(*, target, sources, merge_kind: str, refresh_policy: str,
                                  work_unit_id: str | None = None) -> "dict[str, Any]":
    """Record future fan-in intent over typed refs. Conditional P6 guard: refs are parsed FIRST, then
    P6 is required ONLY if an artifact ref is present (all-declared_target planning works under P6 skew)."""
    if (u := await _registry_unusable()) is not None:
        return u
    # 1. parse refs FIRST (before any P6 guard)
    tref, terr = _parse_ref(target)
    if terr is not None:
        return _err(terr["code"], terr.get("message", "bad target ref"),
                    **{k: v for k, v in terr.items() if k not in ("code", "message")})
    if not isinstance(sources, list) or not sources:
        return _err("empty_sources", "'sources' must be a non-empty list of typed refs.")
    parsed_sources: list[tuple[str, str]] = []
    for s in sources:
        sref, serr = _parse_ref(s)
        if serr is not None:
            return _err(serr["code"], serr.get("message", "bad source ref"),
                        **{k: v for k, v in serr.items() if k not in ("code", "message")})
        parsed_sources.append(sref)
    all_refs = [tref] + parsed_sources
    has_artifact_ref = any(k == "artifact" for k, _ in all_refs)
    # 2. CONDITIONAL P6 guard — only when an artifact ref exists
    if has_artifact_ref:
        if (p6u := await _p6_unusable()) is not None:
            return p6u
    # 3. resolution (declared_target exists) + structural over canonical keys
    def _checks():
        reg = work_units_registry()
        keys, res_probs = [], []
        for (k, i) in all_refs:
            key, prob = _planned_artifact_key(reg, k, i)
            if prob is not None:
                res_probs.append(prob)
            keys.append(key)
        if res_probs:
            return res_probs, []
        struct = _planned_structural_problems(keys[0], keys[1:], merge_kind, refresh_policy)
        return [], struct
    res_probs, struct = await asyncio.to_thread(_checks)
    if res_probs:
        p = res_probs[0]
        return _err(p["code"], f"Reference does not resolve: {p['code']}.",
                    **{k: v for k, v in p.items() if k != "code"})
    if struct:
        p = struct[0]
        return _err(p["code"], f"Planned contract is not well-formed: {p['code']}.",
                    **{k: v for k, v in p.items() if k != "code"})
    # 4. artifact link-bar (registered; present NOT required) — only reachable when P6 usable
    if has_artifact_ref:
        def _linkbar():
            return [i for k, i in all_refs if k == "artifact" and not _is_registered(i)]
        unregistered = await asyncio.to_thread(_linkbar)
        if unregistered:
            return _err("artifact_not_registered", "An artifact ref is not registered in P6.",
                        ref={"kind": "artifact", "id": unregistered[0]})
    # 5. optional work unit exists
    if work_unit_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
            return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    # 6. atomic insert + canonical cycle pre-check
    pc_id = f"pc-{uuid.uuid4().hex[:12]}"
    try:
        await asyncio.to_thread(lambda: work_units_registry().insert_planned_contract(
            pc_id, target_ref_kind=tref[0], target_ref_id=tref[1], sources=parsed_sources,
            merge_kind=merge_kind, refresh_policy=refresh_policy, work_unit_id=work_unit_id, now=int(time.time())))
    except PlannedContractCycle as exc:
        return _err("planned_contract_cycle_detected",
                    "Recording this planned contract would introduce a cycle into the planned graph; nothing written.",
                    cycle=exc.cycle)
    return {"success": True, "data": {"plannedContractId": pc_id,
            "target": {"kind": tref[0], "id": tref[1]},
            "sources": [{"kind": k, "id": i} for k, i in parsed_sources],
            "mergeKind": merge_kind, "refreshPolicy": refresh_policy, "status": "planned",
            "workUnitId": work_unit_id}}
```

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_record_" -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S3 T3: planned-contract record tool (conditional P6 guard, two bars, atomic cycle pre-check)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Activation-blocker + state-classifier helpers (pure, shared by activate + inspect)

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
# ----- P7 Slice 3: activation helpers -----
def test_classify_planned_state(tmp_path):
    reg = _fresh_registry(tmp_path)
    Row = work_units.PlannedContractRow
    assert work_units._classify_planned_state(Row("p", "artifact", "M", "import", "refresh_on_demand", "planned", None, None, 1)) == "planned"
    assert work_units._classify_planned_state(Row("p", "artifact", "M", "import", "refresh_on_demand", "activated", "mc-1", 5, 1)) == "activated"
    assert work_units._classify_planned_state(Row("p", "artifact", "M", "import", "refresh_on_demand", "activated", None, None, 1)) == "invalid"
    reg.close()


def test_activation_blockers_matrix(tmp_path, monkeypatch):
    ids, files = _p6_with(tmp_path, monkeypatch, ["A.3dm", "M.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    reg = work_units.work_units_registry()
    # declared target NOT materialized
    reg.insert_declared_target("dt-x", work_unit_id=None, intended_path=str(tmp_path / "X.3dm"),
        normalized_path=artifacts.normalize_path(str(tmp_path / "X.3dm")),
        predicted_artifact_id="pred-x", label=None, now=1)
    reg.insert_planned_contract("pc1", target_ref_kind="artifact", target_ref_id=ids["M.3dm"],
        sources=[("declared_target", "dt-x")], merge_kind="import", refresh_policy="refresh_on_demand",
        work_unit_id=None, now=2)
    blockers, resolved = work_units._activation_blockers(reg, reg.get_planned_contract("pc1"), True)
    assert resolved is None
    assert any(b["code"] == "declared_target_not_materialized" for b in blockers)
    # bound identity changed -> retryable false
    reg.set_declared_target_materialized("dt-x", bound_artifact_id="DIFFERENT", now=3)
    blockers2, _ = work_units._activation_blockers(reg, reg.get_planned_contract("pc1"), True)
    bad = [b for b in blockers2 if b["code"] == "declared_target_bound_identity_changed"]
    assert bad and bad[0]["retryable"] is False
    # P6 unavailable -> single artifact_registry_unavailable blocker
    blockers3, _ = work_units._activation_blockers(reg, reg.get_planned_contract("pc1"), False)
    assert blockers3 == [{"code": "artifact_registry_unavailable", "retryable": True}]
    reg.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "classify_planned or activation_blockers" -v`
Expected: FAIL — helpers undefined.

- [ ] **Step 3: Add the state classifier + resolution + blocker helpers**

```python
def _classify_planned_state(row: "PlannedContractRow") -> str:
    """'planned' | 'activated' | 'invalid' by the FULL stored-state invariant (never status alone)."""
    if row.status == "planned" and row.activated_contract_id is None and row.activated_at is None:
        return "planned"
    if row.status == "activated" and row.activated_contract_id is not None and row.activated_at is not None:
        return "activated"
    return "invalid"


def _blk(code: str, **extra: Any) -> "dict[str, Any]":
    """A blocker dict carrying its retryable flag (derived from _RETRYABLE)."""
    return {"code": code, "retryable": _RETRYABLE.get(code, False), **extra}


def _resolve_planned_ref_present(reg, ref_kind: str, ref_id: str) -> "tuple[str | None, dict | None]":
    """Resolve a typed ref to a PRESENT P6 artifact id, or return a (bare) blocker. Assumes P6 is usable
    (the caller guards p6_available). artifact -> present P6 row; declared_target -> materialized,
    bound==predicted, bound present."""
    ref = {"kind": ref_kind, "id": ref_id}
    if ref_kind == "artifact":
        row = _p6_row(ref_id)
        if row is None:
            return None, {"code": "artifact_not_registered", "ref": ref}
        if row.file_state != "present":
            return None, {"code": "artifact_not_present", "ref": ref}
        return ref_id, None
    if ref_kind == "declared_target":
        dt = reg.get_declared_target(ref_id)
        if dt is None:
            return None, {"code": "declared_target_not_found", "ref": ref}
        if dt.status != "materialized":
            return None, {"code": "declared_target_not_materialized", "ref": ref}
        if dt.bound_artifact_id is None:
            return None, {"code": "declared_target_bound_missing", "ref": ref}
        if dt.bound_artifact_id != dt.predicted_artifact_id:
            return None, {"code": "declared_target_bound_identity_changed", "ref": ref}
        b = _p6_row(dt.bound_artifact_id)
        if b is None or b.file_state != "present":
            return None, {"code": "declared_target_bound_not_present", "ref": ref}
        return dt.bound_artifact_id, None
    return None, {"code": "invalid_ref_kind", "ref": ref}


def _activation_blockers(reg, planned: "PlannedContractRow",
                         p6_available: bool) -> "tuple[list[dict], dict | None]":
    """ALL blockers for activating `planned` (each carrying retryable), plus {target, sources} resolved
    artifact ids when fully clear. Stored-state-invalid -> one blocker. P6 skew -> one blocker. Strict-graph
    cycle blocker ONLY when every ref resolves."""
    if _classify_planned_state(planned) == "invalid":
        return [_blk("planned_contract_already_invalid")], None
    if not p6_available:
        return [_blk("artifact_registry_unavailable")], None
    raw: list[dict] = []
    # structural re-check over canonical keys (defensive)
    tkey = _planned_key_or_sentinel(reg, planned.target_ref_kind, planned.target_ref_id)
    src_refs = reg.sources_for_planned(planned.planned_contract_id)
    skeys = [_planned_key_or_sentinel(reg, k, i) for k, i in src_refs]
    raw += _planned_structural_problems(tkey, skeys, planned.merge_kind, planned.refresh_policy)
    # resolve every ref to a PRESENT artifact id
    rt, pt = _resolve_planned_ref_present(reg, planned.target_ref_kind, planned.target_ref_id)
    if pt is not None:
        raw.append(pt)
    resolved_sources: list[str] = []
    for k, i in src_refs:
        r, p = _resolve_planned_ref_present(reg, k, i)
        if p is not None:
            raw.append(p)
        else:
            resolved_sources.append(r)
    # strict-graph cycle ONLY when everything resolved
    if not raw and rt is not None and len(resolved_sources) == len(src_refs):
        pairs = [(c.contract_id, c.target_artifact_id, reg.sources_for(c.contract_id)) for c in reg.list_contracts()]
        pairs.append((planned.planned_contract_id, rt, resolved_sources))
        cyc = _contract_cycle(pairs)
        if cyc is not None:
            raw.append({"code": "strict_merge_cycle_detected", "cycle": cyc})
    blockers = [_blk(b["code"], **{k: v for k, v in b.items() if k != "code"}) for b in raw]
    resolved = None if blockers else {"target": rt, "sources": resolved_sources}
    return blockers, resolved
```

- [ ] **Step 4: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "classify_planned or activation_blockers" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S3 T4: activation state-classifier + blocker helpers (shared by activate/inspect)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `activate` tool + atomic `activate_planned_contract` registry method (in-tx CAS)

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
# ----- P7 Slice 3: activate -----
def _materialize_dt(tmp_path, monkeypatch, name):
    """Helper: declare + materialize a declared target at tmp_path/name; return (dt_id, artifact_id)."""
    f = tmp_path / name; f.write_text("x")
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    prom = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    return dt, prom["data"]["boundArtifactId"]


def test_activate_happy_creates_strict_contract(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    dt_m, aid_m = _materialize_dt(tmp_path, monkeypatch, "M.3dm")
    dt_a, aid_a = _materialize_dt(tmp_path, monkeypatch, "A.3dm")
    pc = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt_m},
        sources=[{"kind": "declared_target", "id": dt_a}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    out = asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id=pc))
    assert out["success"] is True and out["data"]["alreadyActivated"] is False
    cid = out["data"]["contractId"]
    # strict contract is indistinguishable from a record_merge_contract row
    strict = work_units.work_units_registry().get_contract(cid)
    assert strict.target_artifact_id == aid_m
    assert work_units.work_units_registry().sources_for(cid) == [aid_a]
    # planned row stamped activated
    assert work_units.work_units_registry().get_planned_contract(pc).status == "activated"


def test_activate_idempotent_no_second_contract(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    dt_m, _ = _materialize_dt(tmp_path, monkeypatch, "M.3dm")
    dt_a, _ = _materialize_dt(tmp_path, monkeypatch, "A.3dm")
    pc = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt_m},
        sources=[{"kind": "declared_target", "id": dt_a}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    first = asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id=pc))
    again = asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id=pc))
    assert again["success"] is True and again["data"]["alreadyActivated"] is True
    assert again["data"]["contractId"] == first["data"]["contractId"]
    assert len(work_units.work_units_registry().list_contracts()) == 1   # no second strict contract


def test_activate_not_activatable_all_blockers(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "M.3dm")))  # NOT materialized
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "A.3dm")))
    dts = [d["declaredTargetId"] for d in asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"]]
    pc = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dts[0]},
        sources=[{"kind": "declared_target", "id": dts[1]}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    out = asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id=pc))
    assert out["success"] is False and out["data"]["code"] == "planned_contract_not_activatable"
    codes = {b["code"] for b in out["data"]["blockers"]}
    assert "declared_target_not_materialized" in codes
    assert out["data"]["retryable"] is True   # all blockers retryable
    assert len(work_units.work_units_registry().list_contracts()) == 0   # nothing written


def test_activate_not_found_and_invalid_state(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    nf = asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id="pc-nope"))
    assert nf["success"] is False and nf["data"]["code"] == "planned_contract_not_found"
    reg = work_units.work_units_registry()
    with reg._immediate():   # raw-insert an invariant-violating row
        reg._conn.execute("INSERT INTO planned_merge_contracts(planned_contract_id, target_ref_kind, "
            "target_ref_id, merge_kind, refresh_policy, status, activated_contract_id, activated_at, created_at) "
            "VALUES('pc-bad','artifact','M','import','refresh_on_demand','activated',NULL,NULL,1);")
    bad = asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id="pc-bad"))
    assert bad["success"] is False and bad["data"]["code"] == "planned_contract_already_invalid"
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_activate_" -v`
Expected: FAIL — `activate_planned_contract_tool` / `activate_planned_contract` undefined.

- [ ] **Step 3: Add the atomic registry method** (inside `WorkUnitRegistry`, after `work_units_for_planned_contract`)

```python
    def activate_planned_contract(self, planned_contract_id: str, *, candidate_contract_id: str,
                                  target: str, sources: "list[str]", merge_kind: str, refresh_policy: str,
                                  work_unit_ids: "list[str]", now: int) -> "tuple[str, bool]":
        """ONE tx with a durable CAS. Re-read + classify by the stored-state invariant: valid-activated ->
        (existing_id, True); invalid -> PlannedContractInvalid (rollback); valid-planned -> strict cycle
        pre-check + insert merge_contracts/sources/ownership + stamp planned -> (candidate, False).
        Two concurrent activations serialize on BEGIN IMMEDIATE; the loser returns the existing id."""
        with self._immediate():
            row = self.get_planned_contract(planned_contract_id)
            if row is None or _classify_planned_state(row) == "invalid":
                raise PlannedContractInvalid()
            if _classify_planned_state(row) == "activated":
                return row.activated_contract_id, True
            pairs = [(c.contract_id, c.target_artifact_id, self.sources_for(c.contract_id))
                     for c in self.list_contracts()]
            pairs.append((candidate_contract_id, target, list(sources)))
            cyc = _contract_cycle(pairs)
            if cyc is not None:
                raise ContractCycleError(cyc)
            self._conn.execute(
                "INSERT INTO merge_contracts(contract_id, target_artifact_id, merge_kind, refresh_policy, "
                "created_at) VALUES(?,?,?,?,?);", (candidate_contract_id, target, merge_kind, refresh_policy, now))
            self._conn.executemany(
                "INSERT INTO merge_contract_sources(contract_id, source_artifact_id) VALUES(?,?);",
                [(candidate_contract_id, s) for s in sources])
            for wu in work_unit_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO work_unit_merge_contracts(work_unit_id, contract_id, created_at) "
                    "VALUES(?,?,?);", (wu, candidate_contract_id, now))
            self._conn.execute(
                "UPDATE planned_merge_contracts SET status='activated', activated_contract_id=?, "
                "activated_at=? WHERE planned_contract_id=?;", (candidate_contract_id, now, planned_contract_id))
        return candidate_contract_id, False
```

- [ ] **Step 4: Add the `activate_planned_contract_tool`** (after `record_planned_contract`)

```python
async def activate_planned_contract_tool(*, planned_contract_id: str) -> "dict[str, Any]":
    """One-at-a-time, idempotent (in-tx CAS), fail-closed-with-all-blockers bridge from a planned contract
    to a strict merge_contract. The only failures that escape the blocker envelope are not_found,
    already_invalid, and registry-unavailable."""
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    row = await asyncio.to_thread(lambda: work_units_registry().get_planned_contract(planned_contract_id))
    if row is None:
        return _err("planned_contract_not_found", f"No planned contract {planned_contract_id!r}.")
    state = _classify_planned_state(row)
    if state == "activated":
        return {"success": True, "data": {"plannedContractId": planned_contract_id, "status": "activated",
                "contractId": row.activated_contract_id, "alreadyActivated": True}}
    if state == "invalid":
        return _err("planned_contract_already_invalid",
                    f"Planned contract {planned_contract_id!r} violates the stored-state invariant.")
    blockers, resolved = await asyncio.to_thread(
        lambda: _activation_blockers(work_units_registry(), row, True))
    if blockers:
        return {"success": False, "data": {"code": "planned_contract_not_activatable",
                "blockers": blockers, "retryable": all(b["retryable"] for b in blockers)}}
    contract_id = f"mc-{uuid.uuid4().hex[:12]}"
    def _activate():
        reg = work_units_registry()
        return reg.activate_planned_contract(
            planned_contract_id, candidate_contract_id=contract_id, target=resolved["target"],
            sources=resolved["sources"], merge_kind=row.merge_kind, refresh_policy=row.refresh_policy,
            work_unit_ids=reg.work_units_for_planned_contract(planned_contract_id), now=int(time.time()))
    try:
        final_contract_id, already = await asyncio.to_thread(_activate)
    except ContractCycleError as exc:
        return {"success": False, "data": {"code": "planned_contract_not_activatable",
                "blockers": [{"code": "strict_merge_cycle_detected", "retryable": False, "cycle": exc.cycle}],
                "retryable": False}}
    except PlannedContractInvalid:
        return _err("planned_contract_already_invalid",
                    f"Planned contract {planned_contract_id!r} violates the stored-state invariant.")
    return {"success": True, "data": {"plannedContractId": planned_contract_id, "status": "activated",
            "contractId": final_contract_id, "alreadyActivated": already,
            "target": resolved["target"], "sources": resolved["sources"],
            "mergeKind": row.merge_kind, "refreshPolicy": row.refresh_policy}}
```

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_activate_" -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S3 T5: activate tool + atomic activate_planned_contract registry method (in-tx CAS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `rhino_planned_contracts` inspector + `rhino_work_units` planned-contract join

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
# ----- P7 Slice 3: inspector + work-unit join -----
def test_planned_inspector_single_and_graph(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    dt_m, aid_m = _materialize_dt(tmp_path, monkeypatch, "M.3dm")
    dt_f, aid_f = _materialize_dt(tmp_path, monkeypatch, "F.3dm")
    # pc_stage1: M <- A(declared, not materialized) ; pc_stage2: F <- M(artifact id) -> canonical edge stage1->stage2
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "A.3dm")))
    dt_a = [d["declaredTargetId"] for d in asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"]
            if d["intendedPath"].endswith("A.3dm")][0]
    pc1 = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt_m},
        sources=[{"kind": "declared_target", "id": dt_a}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    pc2 = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt_f},
        sources=[{"kind": "artifact", "id": aid_m}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    one = asyncio.run(work_units.list_planned_contracts_tool(planned_contract_id=pc1))
    obs = one["data"]["plannedContracts"][0]["observed"]
    assert obs["activatable"] is False  # dt_a not materialized
    assert any(b["code"] == "declared_target_not_materialized" for b in obs["blockers"])
    whole = asyncio.run(work_units.list_planned_contracts_tool())["data"]
    assert whole["plannedContractOrder"].index(pc1) < whole["plannedContractOrder"].index(pc2)  # canonical edge
    assert any(e["from"] == pc1 and e["to"] == pc2 for e in whole["edges"])


def test_planned_inspector_includes_activated_rows_and_skew(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    dt_m, _ = _materialize_dt(tmp_path, monkeypatch, "M.3dm")
    dt_a, _ = _materialize_dt(tmp_path, monkeypatch, "A.3dm")
    pc = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt_m},
        sources=[{"kind": "declared_target", "id": dt_a}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id=pc))
    whole = asyncio.run(work_units.list_planned_contracts_tool())["data"]
    assert pc in whole["plannedContractOrder"]  # activated rows still in order
    assert whole["plannedContracts"][0]["status"] == "activated"
    nf = asyncio.run(work_units.list_planned_contracts_tool(planned_contract_id="pc-nope"))
    assert nf["success"] is False and nf["data"]["code"] == "planned_contract_not_found"


def test_planned_inspector_p6_skew_blocker(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "M.3dm")))
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "A.3dm")))
    dts = [d["declaredTargetId"] for d in asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"]]
    asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dts[0]},
        sources=[{"kind": "declared_target", "id": dts[1]}], merge_kind="import", refresh_policy="refresh_on_demand"))
    # now skew P6
    raw = sqlite3.connect(str(tmp_path / "artifacts.db"))
    raw.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('artifact_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    artifacts._reset_artifact_registry_singleton()
    out = asyncio.run(work_units.list_planned_contracts_tool())
    assert out["data"]["p6Available"] is False
    obs = out["data"]["plannedContracts"][0]["observed"]
    assert obs["activatable"] is False
    assert any(b["code"] == "artifact_registry_unavailable" for b in obs["blockers"])


def test_work_unit_planned_join(tmp_path, monkeypatch):
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.register_work_unit_tool(label="W", work_unit_id="wu"))
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "M.3dm")))
    asyncio.run(work_units.declared_target_declare_tool(intended_path=str(tmp_path / "A.3dm")))
    dts = [d["declaredTargetId"] for d in asyncio.run(work_units.list_declared_targets_tool())["data"]["declaredTargets"]]
    pc = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dts[0]},
        sources=[{"kind": "declared_target", "id": dts[1]}], merge_kind="import",
        refresh_policy="refresh_on_demand", work_unit_id="wu"))["data"]["plannedContractId"]
    wu = asyncio.run(work_units.list_work_units_tool(work_unit_id="wu"))
    assert wu["data"]["workUnits"][0]["plannedContracts"] == [pc]


def test_planned_inspector_activated_row_ignores_drift(tmp_path, monkeypatch):
    # an ACTIVATED planned row whose source artifact later goes missing in P6 stays 'activated' in the
    # inspector — NOT "not activatable: artifact_not_present". Drift after activation is Slice-1
    # validate_merge_contract's concern, never the planned inspector's.
    _p6_with(tmp_path, monkeypatch, [])
    _repoint_p7(tmp_path, monkeypatch)
    dt_m, _ = _materialize_dt(tmp_path, monkeypatch, "M.3dm")
    dt_a, _ = _materialize_dt(tmp_path, monkeypatch, "A.3dm")
    pc = asyncio.run(work_units.record_planned_contract(target={"kind": "declared_target", "id": dt_m},
        sources=[{"kind": "declared_target", "id": dt_a}], merge_kind="import",
        refresh_policy="refresh_on_demand"))["data"]["plannedContractId"]
    asyncio.run(work_units.activate_planned_contract_tool(planned_contract_id=pc))
    artifacts.artifact_registry().set_state(artifacts.normalize_path(str(tmp_path / "A.3dm")),
        file_state="missing", size=None, mtime=None, now=9)   # drift AFTER activation
    obs = asyncio.run(work_units.list_planned_contracts_tool(
        planned_contract_id=pc))["data"]["plannedContracts"][0]["observed"]
    assert obs["alreadyActivated"] is True and obs["activatable"] is False and obs["blockers"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "planned_inspector or work_unit_planned_join" -v`
Expected: FAIL — `list_planned_contracts_tool` undefined; `workUnits[0]` has no `plannedContracts`.

- [ ] **Step 3: Add the observation + graph-view helpers + the inspector tool**

```python
def _observe_planned_contract(reg, row: "PlannedContractRow", p6_available: bool) -> "dict[str, Any]":
    """Per-row observations; transitions nothing. An ACTIVATED row is classified FIRST and short-circuits
    — it never re-enters the activation-blocker path (post-activation artifact drift is Slice-1
    validate_merge_contract's concern, not the planned inspector's). A planned/invalid row reports its
    activation blockers; partial resolved ids are best-effort (planned + P6-usable only)."""
    state = _classify_planned_state(row)
    if state == "activated":
        return {"activatable": False, "alreadyActivated": True,
                "activatedContractId": row.activated_contract_id, "blockers": []}
    blockers, _ = _activation_blockers(reg, row, p6_available)   # 'planned' or 'invalid'
    obs: dict[str, Any] = {"activatable": (len(blockers) == 0), "alreadyActivated": False, "blockers": blockers}
    if state == "planned" and p6_available:
        rt, _pt = _resolve_planned_ref_present(reg, row.target_ref_kind, row.target_ref_id)
        if rt is not None:
            obs["resolvedTargetArtifactId"] = rt
        rs = []
        for k, i in reg.sources_for_planned(row.planned_contract_id):
            r, _p = _resolve_planned_ref_present(reg, k, i)
            if r is not None:
                rs.append(r)
        obs["resolvedSourceArtifactIds"] = rs
    else:
        obs["resolvedSourceArtifactIds"] = []
    return obs


def _planned_graph_view(reg) -> "dict[str, Any]":
    """Whole-graph view over canonical keys: plannedContractOrder (incl. activated rows), edges, graphOk,
    graphProblems. Never stored."""
    contracts = reg.list_planned_contracts()
    pairs = _planned_graph_pairs(reg)
    g, target_of, sources_of = _contract_graph(pairs)
    problems: list[dict[str, Any]] = []
    for pc in contracts:
        problems += [{**p, "plannedContractId": pc.planned_contract_id} for p in _planned_structural_problems(
            target_of[pc.planned_contract_id], sources_of[pc.planned_contract_id], pc.merge_kind, pc.refresh_policy)]
    order: list[str] | None = None
    okey = {pc.planned_contract_id: (pc.created_at, pc.planned_contract_id) for pc in contracts}
    try:
        order = list(nx.lexicographical_topological_sort(g, key=lambda n: okey[n]))
    except nx.NetworkXUnfeasible:
        problems.append({"code": "planned_contract_cycle_detected", "cycle": _contract_cycle(pairs)})
    return {"plannedContractOrder": order,
            "edges": [{"from": u, "to": v, "viaArtifactKey": d["viaArtifact"]} for u, v, d in g.edges(data=True)],
            "graphOk": (len(problems) == 0), "graphProblems": problems}


async def list_planned_contracts_tool(*, planned_contract_id: str | None = None) -> "dict[str, Any]":
    """Inspect one (with observations) or the whole graph (+ order/edges/graphOk). Transitions nothing;
    DEGRADES on P6 skew (every row activatable=false + artifact_registry_unavailable blocker)."""
    if (u := await _registry_unusable()) is not None:
        return u
    if planned_contract_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_planned_contract(planned_contract_id)) is None:
            return _err("planned_contract_not_found", f"No planned contract {planned_contract_id!r}.")
    p6_available = (await _p6_unusable()) is None
    def _build():
        reg = work_units_registry()
        if planned_contract_id is not None:
            rows, graph = [reg.get_planned_contract(planned_contract_id)], None
        else:
            rows, graph = reg.list_planned_contracts(), _planned_graph_view(reg)
        out_rows = []
        for r in [r for r in rows if r is not None]:
            out_rows.append({"plannedContractId": r.planned_contract_id,
                             "target": {"kind": r.target_ref_kind, "id": r.target_ref_id},
                             "sources": [{"kind": k, "id": i} for k, i in reg.sources_for_planned(r.planned_contract_id)],
                             "mergeKind": r.merge_kind, "refreshPolicy": r.refresh_policy, "status": r.status,
                             "activatedContractId": r.activated_contract_id, "activatedAt": r.activated_at,
                             "createdAt": r.created_at,
                             "observed": _observe_planned_contract(reg, r, p6_available)})
        return out_rows, graph
    out_rows, graph = await asyncio.to_thread(_build)
    data: dict[str, Any] = {"plannedContracts": out_rows, "p6Available": p6_available}
    if graph is not None:
        data.update(graph)
    return {"success": True, "data": data}
```

- [ ] **Step 4: Add the planned-contract join to `list_work_units_tool`**

In `list_work_units_tool`'s `_build`, append to each unit's dict (next to `"declaredTargets"`):
```python
                        "declaredTargets": reg.declared_targets_for(r.work_unit_id),
                        "plannedContracts": reg.planned_contracts_for(r.work_unit_id)})
```
(The existing line ends `reg.declared_targets_for(r.work_unit_id)})` — replace the closing `})` so the new key is inside the dict.)

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -q`
Expected: PASS (Slice 1/2 + all Slice 3 unit tests; ~58).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S3 T6: planned-contract inspector (order/edges/observations) + work-unit join

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Wiring — server decls + dispatch, targeting sets, tool tests + 4-surface audit

**Files:** Modify `server.py`, `targeting.py`; Test `test_work_units_tools.py`

- [ ] **Step 1: Write the failing tests** (append to `test_work_units_tools.py`)

```python
def test_p7_slice3_tools_are_meta_no_rhino():
    for name in ("rhino_planned_contract_record", "rhino_planned_contract_activate", "rhino_planned_contracts"):
        assert name in targeting._ALL_KNOWN_TOOLS
        assert name in targeting._META_TOOLS
        assert targeting.policy_for_tool(name).requires_rhino is False


def test_call_tool_dispatches_planned_record(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()
    # all-declared_target so no P6 needed; declare two targets first
    asyncio.run(server.call_tool("rhino_declared_target_declare", {"intendedPath": str(tmp_path / "M.3dm")}))
    asyncio.run(server.call_tool("rhino_declared_target_declare", {"intendedPath": str(tmp_path / "A.3dm")}))
    listed = asyncio.run(server.call_tool("rhino_declared_targets", {}))
    from rook.tool_result import parse_call_tool_data
    dts = [d["declaredTargetId"] for d in parse_call_tool_data(listed)["declaredTargets"]]
    out = asyncio.run(server.call_tool("rhino_planned_contract_record", {
        "target": {"kind": "declared_target", "id": dts[0]},
        "sources": [{"kind": "declared_target", "id": dts[1]}],
        "mergeKind": "import", "refreshPolicy": "refresh_on_demand"}))
    assert parse_call_tool_data(out)["plannedContractId"].startswith("pc-")
    work_units._reset_work_units_registry_singleton()
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py -v`
Expected: FAIL — names absent; `call_tool` has no `rhino_planned_contract_record` case.

- [ ] **Step 3: Add three `Tool(...)` decls in `server.py`** (immediately after the `rhino_declared_targets` `Tool(...)` block, before `rhino_ping`)

```python
        Tool(
            name="rhino_planned_contract_record",
            description="Record a PLANNED merge contract over typed refs ({kind:'artifact'|'declared_target', "
                        "id}) — future fan-in intent before every artifact exists. Records intent only; no "
                        "execution, no Rhino. P6 needed only when an artifact ref is present.",
            inputSchema={"type": "object", "properties": {
                "target": {"type": "object", "properties": {"kind": {"type": "string"}, "id": {"type": "string"}}},
                "sources": {"type": "array", "items": {"type": "object",
                            "properties": {"kind": {"type": "string"}, "id": {"type": "string"}}}},
                "mergeKind": {"type": "string",
                              "enum": ["worksession", "import", "linked_block", "reference", "block", "report"]},
                "refreshPolicy": {"type": "string", "enum": ["refresh_after_save", "refresh_on_demand"]},
                "workUnitId": {"type": "string"}},
                "required": ["target", "sources", "mergeKind", "refreshPolicy"]},
        ),
        Tool(
            name="rhino_planned_contract_activate",
            description="Activate ONE planned contract into a strict present-only merge_contract — idempotent, "
                        "fail-closed with all blockers, one atomic P7 transaction. Requires every ref present/"
                        "materialized. No Rhino.",
            inputSchema={"type": "object", "properties": {"plannedContractId": {"type": "string"}},
                "required": ["plannedContractId"]},
        ),
        Tool(
            name="rhino_planned_contracts",
            description="List/inspect planned contracts with computed observations (activatable, blockers, "
                        "resolved ids) and, whole-graph, plannedContractOrder/edges/graphOk. Read-only; never "
                        "transitions. Optional plannedContractId.",
            inputSchema={"type": "object", "properties": {"plannedContractId": {"type": "string"}}},
        ),
```

- [ ] **Step 4: Add three dispatch arms in `server.py`** (immediately after the `case "rhino_declared_targets":` block, before `case "rhino_ping":`)

```python
        case "rhino_planned_contract_record":
            result = await work_units.record_planned_contract(
                target=arguments.get("target"), sources=arguments.get("sources"),
                merge_kind=arguments.get("mergeKind"), refresh_policy=arguments.get("refreshPolicy"),
                work_unit_id=arguments.get("workUnitId"))

        case "rhino_planned_contract_activate":
            result = await work_units.activate_planned_contract_tool(
                planned_contract_id=arguments.get("plannedContractId"))

        case "rhino_planned_contracts":
            result = await work_units.list_planned_contracts_tool(
                planned_contract_id=arguments.get("plannedContractId"))
```

- [ ] **Step 5: Add three names to `targeting.py`** (after `"rhino_declared_targets",` in `_ALL_KNOWN_TOOLS` AND in `_META_TOOLS`)

```python
    "rhino_planned_contract_record",
    "rhino_planned_contract_activate",
    "rhino_planned_contracts",
```

- [ ] **Step 6: 4-surface audit**

Run: `grep -rn "rhino_declared_targets" mcp_server/ docs/ --include=*.py --include=*.md`
For any surface that lists the Slice-2 P7 tools as a catalog/persona/knowledge set (not the decl/dispatch/targeting handled above), add the three new names. If the only hits are `server.py`/`targeting.py`/tests, record "no additional surface."

- [ ] **Step 7: Run to verify pass + import**

Run: `mcp_server/.venv/Scripts/python.exe -c "import rook.server" && mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py -v`
Expected: import OK; PASS (Slice-1/2 + Slice-3 tool tests).

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/targeting.py mcp_server/tests/test_work_units_tools.py
git commit -m "P7 S3 T7: wire planned-contract record/activate/inspect tools (server + targeting)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Full suite + baseline parity + finish branch

**Files:** none (verification only)

- [ ] **Step 1: Run the two P7 test files**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py mcp_server/tests/test_work_units_tools.py -v`
Expected: ALL PASS (Slice 1 + 2 + 3).

- [ ] **Step 2: knowledge/ hygiene**

```powershell
git checkout -- knowledge/
if (Test-Path knowledge\selectors) { Remove-Item -Recurse -Force knowledge\selectors }
```

- [ ] **Step 3: Baseline parity vs main (blessed non-live gate, named sets both directions)**

```powershell
# Helper: run the blessed non-live gate and write a SORTED named FAILED/ERROR set to a file.
function Get-NamedSet($outFile) {
    mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" `
        -p no:cacheprovider -q -rfE --tb=no *> "$env:TEMP\p7s3_run.txt"
    Select-String -Path "$env:TEMP\p7s3_run.txt" -Pattern '^(FAILED|ERROR)' |
        ForEach-Object { ($_.Line -split '\s+')[0..1] -join ' ' } | Sort-Object | Set-Content $outFile
}

# 1. On the branch:
Get-NamedSet "$env:TEMP\p7s3_branch.txt"
# 2. On main (commit/stash the branch first, then `git checkout main`), SAME helper:
#    Get-NamedSet "$env:TEMP\p7s3_main.txt"   ; then `git checkout feature/p7-slice3-planned-contracts`
# 3. Compare BOTH directions — EMPTY output == identical named sets (parity holds):
Compare-Object (Get-Content "$env:TEMP\p7s3_branch.txt") (Get-Content "$env:TEMP\p7s3_main.txt")
```
Baseline reference: main is **64 failed / 41 errors**. The gate passes only when `Compare-Object` prints
nothing (named failed/error sets identical both directions) AND every new Slice-3 test passes (absent from
both named sets). A non-empty `Compare-Object` (`SideIndicator =>` = new branch failure, `<=` = vanished)
is a real regression — fix before proceeding.

- [ ] **Step 4: Finish the branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Verify tests pass, then push + open PR (per project workflow; user pulls the squash-merge trigger):

```powershell
git push -u origin feature/p7-slice3-planned-contracts
$body = @'
## Summary
- Adds a `planned_merge_contracts` family (3 tables) recording future fan-in intent over typed refs (`artifact:`/`declared_target:`), with topology over a canonical future-artifact key.
- `rhino_planned_contract_activate` is the idempotent, fail-closed-with-all-blockers bridge: one atomic P7 transaction (in-tx CAS) inserts a strict Slice-1 `merge_contract` (indistinguishable from `record_merge_contract`) + copies ownership + stamps the planned row. `merge_contracts` untouched; zero P6 writes.
- Record's P6 guard is conditional (refs parsed first -> P6 only when an `artifact:` ref is present). Additive `p7.2 -> p7.3` migration (a `p7.1` db gains both declared_targets and the planned tables).

## Test Plan
- [ ] `test_work_units.py` + `test_work_units_tools.py` green (Slice 1 + 2 + 3)
- [ ] Baseline parity vs main: 64 failed / 41 errors unchanged, named sets identical both directions
- [ ] (Optional) live smoke deferrable - P7 never touches Rhino

🤖 Generated with [Claude Code](https://claude.com/claude-code)
'@
gh pr create --title "P7 Slice 3: planned merge contracts — record future fan-in, activate into strict contracts" --body $body
```

---

## Self-Review

**Spec coverage (against `2026-06-06-p7-slice3-...-design.md`):**
- §5 schema + §12 migration → T1 (`p7.2→p7.3` + `p7.1→p7.3` + malformed-fail-closed tests).
- §6 canonical projection → T2 (`_planned_artifact_key`, graph pairs); §7 record (two bars, atomic cycle) → T2 (registry) + T3 (tool, **conditional P6 guard with its dedicated test**).
- §8 activate (state invariant, all-blockers, in-tx CAS, bound-code split, strict-cycle wrapper) → T4 (helpers: `_classify_planned_state`, `_activation_blockers`, the three bound codes) + T5 (tool + atomic method, idempotency, invalid-state, cycle wrapper).
- §9 inspector (single/whole-graph shape, order incl. activated, P6-skew blocker) → T6; §13 work-unit join → T6 Step 4.
- §11 taxonomy → `_RETRYABLE` (T3) + raised across T2–T6. §13 tool surface + non-routed → T7. §14 testing incl. baseline parity → T1–T8.

**Placeholder scan:** none — every step has complete code or an exact command.

**Type/name consistency:** `record_planned_contract` / `activate_planned_contract_tool` / `list_planned_contracts_tool` used identically in their defining task, T7 dispatch, and tests. `PlannedContractRow` field order matches `_PLANNED_CONTRACT_COLUMNS`. `_activation_blockers` returns `(blockers, resolved)` consumed the same way by T5 (`resolved["target"]/["sources"]`) and T6. `_classify_planned_state` returns `'planned'|'activated'|'invalid'` used consistently in T4/T5. `activate_planned_contract(candidate_contract_id=…, work_unit_ids=…)` signature matches its T5 caller. Blocker dicts always carry `retryable` (via `_blk`), so `all(b["retryable"] …)` in T5 is safe.

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended by skill)** — fresh subagent per task + two-stage review.
2. **Inline Execution** — execute in this session with checkpoints.

Given the plan is self-contained and mirrors the just-shipped Slice 1/2 substrate, **inline** is the likely lower-overhead choice (the call made for Slice 1/2). Awaiting your pick.
