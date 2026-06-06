# P7 Slice 2 — Declared-Target State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a P7-only `declared_targets` ledger (`declare` + `promote` + `declared_targets`) that records coordinator intent toward a master/anchor file before it exists and binds it to the real P6 artifact on explicit, drift-safe promotion — no merge execution, no geometry, no change to Slice 1.

**Architecture:** Extends the Slice 1 leaf `mcp_server/src/rook/work_units.py` and its `work_units.db` with one new table and three non-routed MCP tools. Pure logic over SQLite + a read-only P6 lookup, with the single exception of promotion calling P6's public `register_artifact()`. Schema advances `p7.1 → p7.2` via an additive supported-set migration that never bricks existing dbs.

**Tech Stack:** Python 3 (`from __future__ import annotations`), stdlib `sqlite3`, `networkx` (already a dep, unused here), `pytest`. Editable install — pure-Python edits need **no rebuild** for unit tests.

**Spec:** `docs/superpowers/specs/2026-06-06-p7-slice2-declared-target-state-machine-design.md` (on main+origin at `b6151db`).

**Pytest:** `mcp_server/.venv/Scripts/python.exe -m pytest`

---

## Pre-flight

- [ ] **Create the feature branch off main**

```bash
git checkout main && git pull
git checkout -b feature/p7-slice2-declared-targets
```

## File structure

| File | Responsibility | Change |
|---|---|---|
| `mcp_server/src/rook/work_units.py` | The P7 registry leaf | Modify: version + migration, `declared_targets` schema, `DeclaredTargetRow`/`DeclaredTargetConflict`, 5 registry methods, 3 tool functions, `_observe_declared_target`, `_RETRYABLE` additions, `list_work_units_tool` join |
| `mcp_server/src/rook/server.py` | MCP tool decls + dispatch | Modify: 3 `Tool(...)` decls after `rhino_work_units` (~2926), 3 `case` arms after the `rhino_work_units` dispatch (~12952) |
| `mcp_server/src/rook/targeting.py` | Tool classification sets | Modify: 3 names into `_ALL_KNOWN_TOOLS` (~160) and `_META_TOOLS` (~563) |
| `mcp_server/tests/test_work_units.py` | P7 unit tests | Add: schema/migration, registry-method, declare, promote, observation tests |
| `mcp_server/tests/test_work_units_tools.py` | P7 tool-classification tests | Add: meta/no-Rhino + `call_tool` dispatch for the 3 new tools |

---

## Task 1: Schema — `declared_targets` table + additive `p7.1 → p7.2` migration

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (version constants, `_REQUIRED_COLUMNS`, `_ensure_schema`, `DeclaredTargetRow`)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

Add to `mcp_server/tests/test_work_units.py`:

```python
# ----- P7 Slice 2: declared_targets schema + additive migration -----
def test_declared_targets_table_created_at_p72(tmp_path):
    reg = _fresh_registry(tmp_path)
    names = {r[0] for r in reg._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "declared_targets" in names
    ver = reg._conn.execute(
        "SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
    assert ver[0] == "p7.2" == work_units.WORK_UNITS_REGISTRY_VERSION
    reg.close()


def test_additive_migration_p71_to_p72_preserves_data(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('work_units_registry_version','p7.1');")
    raw.execute("CREATE TABLE work_units (work_unit_id TEXT PRIMARY KEY, label TEXT NOT NULL, "
                "role TEXT, metadata TEXT, created_at INTEGER NOT NULL);")
    raw.execute("CREATE TABLE work_unit_artifacts (work_unit_id TEXT NOT NULL, artifact_id TEXT NOT NULL, "
                "relation TEXT NOT NULL, created_at INTEGER NOT NULL, "
                "PRIMARY KEY(work_unit_id, artifact_id, relation));")
    raw.execute("CREATE TABLE merge_contracts (contract_id TEXT PRIMARY KEY, target_artifact_id TEXT NOT NULL, "
                "merge_kind TEXT NOT NULL, refresh_policy TEXT NOT NULL, created_at INTEGER NOT NULL);")
    raw.execute("CREATE TABLE merge_contract_sources (contract_id TEXT NOT NULL, "
                "source_artifact_id TEXT NOT NULL, PRIMARY KEY(contract_id, source_artifact_id));")
    raw.execute("CREATE TABLE work_unit_merge_contracts (work_unit_id TEXT NOT NULL, contract_id TEXT NOT NULL, "
                "created_at INTEGER NOT NULL, PRIMARY KEY(work_unit_id, contract_id));")
    raw.execute("INSERT INTO work_units VALUES('wu-keep','Keep',NULL,NULL,1);")
    raw.commit(); raw.close()

    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported is None
    names = {r[0] for r in reg._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "declared_targets" in names                       # additively created
    ver = reg._conn.execute(
        "SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
    assert ver[0] == "p7.2"                                   # upgraded forward
    assert reg.get_work_unit("wu-keep").label == "Keep"       # existing data intact
    reg.close()


def test_malformed_declared_targets_fails_closed(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE declared_targets (id TEXT, junk TEXT);")  # wrong shape, no version meta
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported == "unknown"
    reg.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "p72 or migration or malformed_declared" -v`
Expected: FAIL — `declared_targets` not created; `WORK_UNITS_REGISTRY_VERSION` is still `"p7.1"`.

- [ ] **Step 3: Bump the version + supported-set constant**

In `work_units.py`, change the version line and add the supported-set just below it:

```python
WORK_UNITS_REGISTRY_VERSION = "p7.2"
# Additive-compatible predecessors: an older db at one of these is migrated FORWARD (new tables
# created, meta upgraded), never failed closed. Unknown/newer versions still fail closed.
_SUPPORTED_PRIOR_VERSIONS = frozenset({"p7.1"})
```

- [ ] **Step 4: Add `declared_targets` to the shape guard**

Add this entry to the `_REQUIRED_COLUMNS` dict:

```python
    "declared_targets": {"declared_target_id", "work_unit_id", "intended_path", "normalized_path",
                         "predicted_artifact_id", "status", "bound_artifact_id", "label",
                         "created_at", "materialized_at"},
```

- [ ] **Step 5: Update `_ensure_schema` (gate + table + meta upgrade)**

Replace the version-gate line:

```python
        if stored is not None and stored[0] != WORK_UNITS_REGISTRY_VERSION:
            self.schema_unsupported = stored[0]
            return
```

with the supported-set gate:

```python
        if stored is not None and stored[0] != WORK_UNITS_REGISTRY_VERSION \
                and stored[0] not in _SUPPORTED_PRIOR_VERSIONS:
            self.schema_unsupported = stored[0]
            return
```

Add the new table + index immediately after the `work_unit_merge_contracts` CREATE and before the
existing `CREATE INDEX` lines:

```python
        c.execute("""CREATE TABLE IF NOT EXISTS declared_targets (
            declared_target_id TEXT PRIMARY KEY, work_unit_id TEXT, intended_path TEXT NOT NULL,
            normalized_path TEXT NOT NULL, predicted_artifact_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL, bound_artifact_id TEXT, label TEXT,
            created_at INTEGER NOT NULL, materialized_at INTEGER);""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_declared_targets_work_unit ON declared_targets(work_unit_id);")
```

Replace the meta-write tail:

```python
        if stored is None:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('work_units_registry_version', ?);",
                      (WORK_UNITS_REGISTRY_VERSION,))
```

with an upgrade-aware write (fires on fresh db AND on a `p7.1 → p7.2` migration; no-op when already current):

```python
        if stored is None or stored[0] != WORK_UNITS_REGISTRY_VERSION:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('work_units_registry_version', ?);",
                      (WORK_UNITS_REGISTRY_VERSION,))
```

- [ ] **Step 6: Add the `DeclaredTargetRow` dataclass + column constant**

After the `ContractRow` dataclass, add:

```python
_DECLARED_TARGET_COLUMNS = ("declared_target_id, work_unit_id, intended_path, normalized_path, "
                            "predicted_artifact_id, status, bound_artifact_id, label, "
                            "created_at, materialized_at")


@dataclass(frozen=True)
class DeclaredTargetRow:
    declared_target_id: str
    work_unit_id: str | None
    intended_path: str
    normalized_path: str
    predicted_artifact_id: str
    status: str
    bound_artifact_id: str | None
    label: str | None
    created_at: int
    materialized_at: int | None
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "p72 or migration or malformed_declared" -v`
Expected: PASS (3 tests). Also run the full Slice 1 file to confirm no regression:
`mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -q`

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S2 T1: declared_targets schema + additive p7.1->p7.2 migration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Registry methods — insert (with conflict) / get / list / set-materialized / work-unit join

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (`DeclaredTargetConflict`, 5 methods on `WorkUnitRegistry`)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_declared_target_insert_get_list_and_conflict(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.insert_declared_target("dt1", work_unit_id=None, intended_path="C:/p/m.3dm",
        normalized_path="c:\\p\\m.3dm", predicted_artifact_id="pid1", label="M", now=5)
    row = reg.get_declared_target("dt1")
    assert row.status == "declared" and row.predicted_artifact_id == "pid1" and row.bound_artifact_id is None
    assert [r.declared_target_id for r in reg.list_declared_targets()] == ["dt1"]
    with pytest.raises(work_units.DeclaredTargetConflict) as ei:
        reg.insert_declared_target("dt2", work_unit_id=None, intended_path="C:/p/m.3dm",
            normalized_path="c:\\p\\m.3dm", predicted_artifact_id="pid1", label=None, now=6)
    assert ei.value.existing_id == "dt1"
    assert [r.declared_target_id for r in reg.list_declared_targets()] == ["dt1"]  # atomic: dt2 not written
    reg.set_declared_target_materialized("dt1", bound_artifact_id="pid1", now=7)
    m = reg.get_declared_target("dt1")
    assert m.status == "materialized" and m.bound_artifact_id == "pid1" and m.materialized_at == 7
    reg.close()


def test_declared_targets_for_work_unit(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.register_work_unit("wu", label="W", role=None, metadata=None, now=1)
    reg.insert_declared_target("dtA", work_unit_id="wu", intended_path="a", normalized_path="a",
        predicted_artifact_id="pa", label=None, now=2)
    reg.insert_declared_target("dtB", work_unit_id="wu", intended_path="b", normalized_path="b",
        predicted_artifact_id="pb", label=None, now=3)
    assert reg.declared_targets_for("wu") == ["dtA", "dtB"]
    reg.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "declared_target_insert or declared_targets_for" -v`
Expected: FAIL — `AttributeError: 'WorkUnitRegistry' has no attribute 'insert_declared_target'` / `DeclaredTargetConflict`.

- [ ] **Step 3: Add the `DeclaredTargetConflict` exception**

Next to `ContractCycleError`, add:

```python
class DeclaredTargetConflict(RuntimeError):
    """insert_declared_target: the intended path (predicted_artifact_id) is already declared.
    Carries the existing declaration id so the tool layer can surface it."""
    def __init__(self, existing_id: str):
        super().__init__("declared_target_path_conflict")
        self.existing_id = existing_id
```

- [ ] **Step 4: Add the 5 registry methods**

Add inside `WorkUnitRegistry` (after `contracts_for`):

```python
    # ----- declared targets (P7 Slice 2) -----
    def insert_declared_target(self, declared_target_id: str, *, work_unit_id: str | None,
                               intended_path: str, normalized_path: str, predicted_artifact_id: str,
                               label: str | None, now: int) -> str:
        """Insert a 'declared' row. UNIQUE(predicted_artifact_id) => one declaration per path; an
        existing one raises DeclaredTargetConflict (ROLLBACK, nothing written)."""
        with self._immediate():
            existing = self._conn.execute(
                "SELECT declared_target_id FROM declared_targets WHERE predicted_artifact_id=?;",
                (predicted_artifact_id,)).fetchone()
            if existing is not None:
                raise DeclaredTargetConflict(existing[0])
            self._conn.execute(
                "INSERT INTO declared_targets(declared_target_id, work_unit_id, intended_path, "
                "normalized_path, predicted_artifact_id, status, bound_artifact_id, label, "
                "created_at, materialized_at) VALUES(?,?,?,?,?,'declared',NULL,?,?,NULL);",
                (declared_target_id, work_unit_id, intended_path, normalized_path,
                 predicted_artifact_id, label, now))
        return declared_target_id

    def set_declared_target_materialized(self, declared_target_id: str, *, bound_artifact_id: str,
                                         now: int) -> None:
        with self._immediate():
            self._conn.execute(
                "UPDATE declared_targets SET status='materialized', bound_artifact_id=?, "
                "materialized_at=? WHERE declared_target_id=?;",
                (bound_artifact_id, now, declared_target_id))

    def get_declared_target(self, declared_target_id: str) -> "DeclaredTargetRow | None":
        with self._lock:
            raw = self._conn.execute(
                f"SELECT {_DECLARED_TARGET_COLUMNS} FROM declared_targets WHERE declared_target_id=?;",
                (declared_target_id,)).fetchone()
            return None if raw is None else DeclaredTargetRow(*raw)

    def list_declared_targets(self) -> "list[DeclaredTargetRow]":
        with self._lock:
            return [DeclaredTargetRow(*r) for r in self._conn.execute(
                f"SELECT {_DECLARED_TARGET_COLUMNS} FROM declared_targets "
                "ORDER BY created_at, declared_target_id;").fetchall()]

    def declared_targets_for(self, work_unit_id: str) -> "list[str]":
        with self._lock:
            return [d for (d,) in self._conn.execute(
                "SELECT declared_target_id FROM declared_targets WHERE work_unit_id=? "
                "ORDER BY created_at, declared_target_id;", (work_unit_id,)).fetchall()]
```

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "declared_target_insert or declared_targets_for" -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S2 T2: declared-target registry methods (insert/get/list/materialize/join)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `declare` tool + `_RETRYABLE` additions

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (`_RETRYABLE`, `declared_target_declare_tool`)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_declare_computes_predicted_id_and_status(tmp_path, monkeypatch):
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "m.3dm"
    out = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f), label="Master"))
    assert out["success"] is True
    assert out["data"]["predictedArtifactId"] == artifacts.artifact_id_for(artifacts.normalize_path(str(f)))
    assert out["data"]["status"] == "declared"


def test_declare_conflict_returns_existing_id(tmp_path, monkeypatch):
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "dup.3dm"
    first = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))
    assert first["success"] is True
    second = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))
    assert second["success"] is False and second["data"]["code"] == "declared_target_path_conflict"
    assert second["data"]["existingDeclaredTargetId"] == first["data"]["declaredTargetId"]
    assert second["data"]["retryable"] is False


def test_declare_validates_work_unit_and_path(tmp_path, monkeypatch):
    _repoint_p7(tmp_path, monkeypatch)
    bad_wu = asyncio.run(work_units.declared_target_declare_tool(
        intended_path=str(tmp_path / "a.3dm"), work_unit_id="nope"))
    assert bad_wu["success"] is False and bad_wu["data"]["code"] == "work_unit_not_found"
    bad_path = asyncio.run(work_units.declared_target_declare_tool(intended_path="   "))
    assert bad_path["success"] is False and bad_path["data"]["code"] == "invalid_path"
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_declare_" -v`
Expected: FAIL — `declared_target_declare_tool` does not exist.

- [ ] **Step 3: Extend `_RETRYABLE`**

Add these entries to the `_RETRYABLE` dict:

```python
    "invalid_path": False,
    "declared_target_not_found": False,
    "declared_target_path_conflict": False,
    "declared_target_not_materialized": True,
    "declared_target_unreachable": True,
    "declared_target_path_identity_changed": False,
    "declared_target_promotion_failed": False,
```

- [ ] **Step 4: Add `declared_target_declare_tool`**

Add to the tool layer (after `list_work_units_tool`):

```python
async def declared_target_declare_tool(*, intended_path: str, label: str | None = None,
                                       work_unit_id: str | None = None) -> "dict[str, Any]":
    """Declare intent toward a not-yet-existing anchor. Pure P7 + a path hash — does NOT touch P6
    and does NOT require the file to exist. The predicted id is a prediction, verified at promote."""
    if (u := await _registry_unusable()) is not None:
        return u
    if not isinstance(intended_path, str) or not intended_path.strip():
        return _err("invalid_path", "'intended_path' must be a non-empty string.")
    if work_unit_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
            return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    norm = await asyncio.to_thread(_artifacts.normalize_path, intended_path)
    predicted = await asyncio.to_thread(_artifacts.artifact_id_for, norm)
    dt_id = f"dt-{uuid.uuid4().hex[:12]}"
    try:
        await asyncio.to_thread(lambda: work_units_registry().insert_declared_target(
            dt_id, work_unit_id=work_unit_id, intended_path=intended_path, normalized_path=norm,
            predicted_artifact_id=predicted, label=label, now=int(time.time())))
    except DeclaredTargetConflict as exc:
        return _err("declared_target_path_conflict",
                    f"Intended path is already declared by {exc.existing_id!r}.",
                    existingDeclaredTargetId=exc.existing_id)
    return {"success": True, "data": {
        "declaredTargetId": dt_id, "intendedPath": intended_path, "normalizedPath": norm,
        "predictedArtifactId": predicted, "status": "declared", "workUnitId": work_unit_id}}
```

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_declare_" -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S2 T3: declared_target_declare tool + retryable codes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `promote` tool — drift check, P6 envelope mapping, bind verification, idempotency

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (`declared_target_promote_tool`)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
def _point_p6_empty(tmp_path, monkeypatch):
    """Point P6 at a throwaway empty artifacts.db (real registry, no rows)."""
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()


def test_promote_registers_and_binds(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "master.3dm"; f.write_text("x")
    predicted = artifacts.artifact_id_for(artifacts.normalize_path(str(f)))
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    prom = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    assert prom["success"] is True and prom["data"]["status"] == "materialized"
    assert prom["data"]["boundArtifactId"] == predicted
    assert artifacts.artifact_registry().get(artifact_id=predicted).file_state == "present"  # P6 now knows it


def test_promote_not_materialized_when_file_absent(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    ghost = tmp_path / "ghost.3dm"  # never created
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(ghost)))["data"]["declaredTargetId"]
    prom = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    assert prom["success"] is False and prom["data"]["code"] == "declared_target_not_materialized"
    assert prom["data"]["retryable"] is True
    assert work_units.work_units_registry().get_declared_target(dt).status == "declared"


def test_promote_drift_fails_closed(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "drift.3dm"; f.write_text("x")
    reg = work_units.work_units_registry()
    with reg._immediate():  # raw-insert a WRONG predicted id but the correct real path
        reg._conn.execute(
            "INSERT INTO declared_targets(declared_target_id, work_unit_id, intended_path, "
            "normalized_path, predicted_artifact_id, status, bound_artifact_id, label, "
            "created_at, materialized_at) VALUES('dt-wrong',NULL,?,?,'wrong-pid','declared',NULL,NULL,1,NULL);",
            (str(f), artifacts.normalize_path(str(f))))
    prom = asyncio.run(work_units.declared_target_promote_tool(declared_target_id="dt-wrong"))
    assert prom["success"] is False and prom["data"]["code"] == "declared_target_path_identity_changed"
    assert work_units.work_units_registry().get_declared_target("dt-wrong").status == "declared"


def test_promote_idempotent_and_not_found(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "anchor.3dm"; f.write_text("x")
    predicted = artifacts.artifact_id_for(artifacts.normalize_path(str(f)))
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    again = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))  # idempotent
    assert again["success"] is True and again["data"]["status"] == "materialized"
    assert again["data"]["boundArtifactId"] == predicted
    nf = asyncio.run(work_units.declared_target_promote_tool(declared_target_id="dt-none"))
    assert nf["success"] is False and nf["data"]["code"] == "declared_target_not_found"


def test_promote_completes_after_p6_already_registered(tmp_path, monkeypatch):
    # §6.1 cross-DB window: P6 row already present, P7 target still 'declared' -> retry completes the bind.
    ids, files = _p6_with(tmp_path, monkeypatch, ["anchor.3dm"])  # registers anchor present in P6
    _repoint_p7(tmp_path, monkeypatch)
    path = str(files["anchor.3dm"])
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=path))["data"]["declaredTargetId"]
    prom = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    assert prom["success"] is True and prom["data"]["status"] == "materialized"
    assert prom["data"]["boundArtifactId"] == ids["anchor.3dm"]
    norm = artifacts.normalize_path(path)
    assert len([r for r in artifacts.artifact_registry().list_all() if r.path == norm]) == 1  # no duplicate row


def test_promote_fails_closed_on_p6_skew(tmp_path, monkeypatch):
    # P6 hard guard: a version-skewed P6 -> promote dies at its artifact_registry_unavailable guard,
    # NO P7 transition (declare is pure P7, so it still succeeds).
    raw = sqlite3.connect(str(tmp_path / "artifacts.db"))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('artifact_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "anchor.3dm"; f.write_text("x")
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    out = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    assert out["success"] is False and out["data"]["code"] == "artifact_registry_unavailable"
    assert work_units.work_units_registry().get_declared_target(dt).status == "declared"


def test_promote_maps_unreachable_envelope(tmp_path, monkeypatch):
    # envelope-by-data.code: register_artifact -> artifact_file_unreachable maps to
    # declared_target_unreachable (retryable), with NO bind. Monkeypatch P6's register to force it.
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "locked.3dm"  # need not exist; register is monkeypatched
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    async def fake_register(path):
        return {"success": False, "data": {"code": "artifact_file_unreachable",
                                           "message": "unreachable", "retryable": True}}
    monkeypatch.setattr(artifacts, "register_artifact", fake_register)
    out = asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    assert out["success"] is False and out["data"]["code"] == "declared_target_unreachable"
    assert out["data"]["retryable"] is True
    assert work_units.work_units_registry().get_declared_target(dt).status == "declared"
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_promote_" -v`
Expected: FAIL — `declared_target_promote_tool` does not exist.

- [ ] **Step 3: Add `declared_target_promote_tool`**

```python
async def declared_target_promote_tool(*, declared_target_id: str) -> "dict[str, Any]":
    """The ONLY transition to 'materialized'. Drift-check, register the real file through P6's public
    api, verify the bind, flip. Idempotent + re-entrant (safe to retry after a §6.1 crash window)."""
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    row = await asyncio.to_thread(lambda: work_units_registry().get_declared_target(declared_target_id))
    if row is None:
        return _err("declared_target_not_found", f"No declared target {declared_target_id!r}.")
    if row.status == "materialized":
        return {"success": True, "data": {"declaredTargetId": row.declared_target_id,
                "status": "materialized", "boundArtifactId": row.bound_artifact_id,
                "normalizedPath": row.normalized_path}}
    # (a) declared-path drift — pure recompute, no P6/disk write
    cur_norm = await asyncio.to_thread(_artifacts.normalize_path, row.intended_path)
    cur_id = await asyncio.to_thread(_artifacts.artifact_id_for, cur_norm)
    if cur_id != row.predicted_artifact_id:
        return _err("declared_target_path_identity_changed",
                    "The declared path now normalizes to a different artifact id; not promoted.",
                    predictedArtifactId=row.predicted_artifact_id, currentArtifactId=cur_id)
    # register through P6's PUBLIC api — parse the {success, data} envelope by data.code (never generic)
    r = await _artifacts.register_artifact(row.intended_path)
    if r["success"] is False:
        code = r["data"]["code"]
        if code == "artifact_file_not_found":
            return _err("declared_target_not_materialized",
                        f"No file at the declared path yet; cannot materialize {declared_target_id!r}.")
        if code == "artifact_file_unreachable":
            return _err("declared_target_unreachable",
                        f"The declared path is unreachable; cannot materialize {declared_target_id!r}.")
        if code == "artifact_id_collision":
            return _err("declared_target_path_conflict",
                        "A different registered path already owns this artifact id; not promoted.")
        if code == "artifact_registry_unavailable":
            return r  # pass the P6 envelope through unchanged
        return _err("declared_target_promotion_failed",
                    f"P6 registration failed unexpectedly: {code}.", p6Code=code)
    artifact = r["data"]["artifact"]
    # (b) bind verification — the real P6 row must match the prediction and be present
    if artifact["artifactId"] != row.predicted_artifact_id or artifact["fileState"] != "present":
        return _err("declared_target_path_identity_changed",
                    "The registered artifact does not match the prediction; not promoted.",
                    predictedArtifactId=row.predicted_artifact_id,
                    registeredArtifactId=artifact["artifactId"], fileState=artifact["fileState"])
    await asyncio.to_thread(lambda: work_units_registry().set_declared_target_materialized(
        declared_target_id, bound_artifact_id=row.predicted_artifact_id, now=int(time.time())))
    return {"success": True, "data": {"declaredTargetId": declared_target_id, "status": "materialized",
            "boundArtifactId": row.predicted_artifact_id, "normalizedPath": row.normalized_path}}
```

- [ ] **Step 4: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_promote_" -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S2 T4: declared_target_promote (drift + P6 envelope + bind + idempotent)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `declared_targets` tool — computed observations + work-unit join

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (`_observe_declared_target`, `list_declared_targets_tool`, `list_work_units_tool`)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_declared_targets_observation_transitions_nothing(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "later.3dm"
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    obs = asyncio.run(work_units.list_declared_targets_tool(
        declared_target_id=dt))["data"]["declaredTargets"][0]["observed"]
    assert obs["promotable"] is False and obs["promotionBlockedReason"] == "declared_target_not_materialized"
    assert obs["artifactRegistered"] is False
    f.write_text("x")  # file appears
    row = asyncio.run(work_units.list_declared_targets_tool(
        declared_target_id=dt))["data"]["declaredTargets"][0]
    assert row["observed"]["promotable"] is True and row["status"] == "declared"  # listing never promotes
    assert work_units.work_units_registry().get_declared_target(dt).status == "declared"


def test_declared_targets_promotable_honors_p6_availability(tmp_path, monkeypatch):
    raw = sqlite3.connect(str(tmp_path / "artifacts.db"))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('artifact_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "blocked.3dm"; f.write_text("x")  # present + path-stable
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    out = asyncio.run(work_units.list_declared_targets_tool(declared_target_id=dt))
    assert out["success"] is True and out["data"]["p6Available"] is False
    obs = out["data"]["declaredTargets"][0]["observed"]
    assert obs["promotable"] is False and obs["promotionBlockedReason"] == "artifact_registry_unavailable"
    assert obs["p6Available"] is False and obs["artifactRegistered"] is None


def test_materialized_is_non_authoritative(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    f = tmp_path / "anchor.3dm"; f.write_text("x")
    dt = asyncio.run(work_units.declared_target_declare_tool(intended_path=str(f)))["data"]["declaredTargetId"]
    asyncio.run(work_units.declared_target_promote_tool(declared_target_id=dt))
    norm = artifacts.normalize_path(str(f)); f.unlink()
    artifacts.artifact_registry().set_state(norm, file_state="missing", size=None, mtime=None, now=1)
    row = asyncio.run(work_units.list_declared_targets_tool(
        declared_target_id=dt))["data"]["declaredTargets"][0]
    assert row["status"] == "materialized"  # NO demotion
    assert row["observed"]["boundArtifactPresent"] is False
    assert row["observed"]["fileState"] == "missing"


def test_declared_target_work_unit_join(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)  # isolation: list_declared_targets_tool reads P6 for observations
    _repoint_p7(tmp_path, monkeypatch)
    asyncio.run(work_units.register_work_unit_tool(label="W", work_unit_id="wu"))
    dt = asyncio.run(work_units.declared_target_declare_tool(
        intended_path=str(tmp_path / "x.3dm"), work_unit_id="wu"))["data"]["declaredTargetId"]
    wu = asyncio.run(work_units.list_work_units_tool(work_unit_id="wu"))
    assert wu["data"]["workUnits"][0]["declaredTargets"] == [dt]
    one = asyncio.run(work_units.list_declared_targets_tool(
        declared_target_id=dt))["data"]["declaredTargets"][0]
    assert one["workUnitId"] == "wu"


def test_declared_targets_unknown_id_is_not_found(tmp_path, monkeypatch):
    _point_p6_empty(tmp_path, monkeypatch)
    _repoint_p7(tmp_path, monkeypatch)
    out = asyncio.run(work_units.list_declared_targets_tool(declared_target_id="dt-nope"))
    assert out["success"] is False and out["data"]["code"] == "declared_target_not_found"
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_declared_targets_observation or promotable_honors or non_authoritative or work_unit_join or unknown_id_is_not_found" -v`
Expected: FAIL — `list_declared_targets_tool` does not exist; `workUnits[0]` has no `declaredTargets` key.

- [ ] **Step 3: Add the observation helper + listing tool**

```python
def _observe_declared_target(row: "DeclaredTargetRow", p6_available: bool) -> "dict[str, Any]":
    """Read-only observations computed at call time — NEVER a transition. fileState is a fresh disk
    stat; P6-derived fields are null when P6 is unavailable. promotable INCLUDES p6_available, so it
    never claims promotion can work when promote would die at its artifact_registry_unavailable guard.
    promotionBlockedReason is the first failing precondition in promote's own order."""
    cur_norm = _artifacts.normalize_path(row.intended_path)
    file_state, _, _ = _artifacts.stat_file_state(cur_norm)
    path_identity_stable = (_artifacts.artifact_id_for(cur_norm) == row.predicted_artifact_id)
    artifact_registered: bool | None = None
    bound_present: bool | None = None
    if p6_available:
        artifact_registered = _p6_row(row.predicted_artifact_id) is not None
        if row.status == "materialized" and row.bound_artifact_id is not None:
            b = _p6_row(row.bound_artifact_id)
            bound_present = (b is not None and b.file_state == "present")
    promotable = (row.status == "declared" and p6_available
                  and path_identity_stable and file_state == "present")
    reason: str | None = None
    if not promotable:
        if row.status == "materialized":
            reason = "already_materialized"
        elif not p6_available:
            reason = "artifact_registry_unavailable"
        elif not path_identity_stable:
            reason = "declared_target_path_identity_changed"
        elif file_state == "unreachable":
            reason = "declared_target_unreachable"
        elif file_state == "missing":
            reason = "declared_target_not_materialized"
    return {"fileState": file_state, "pathIdentityStable": path_identity_stable,
            "p6Available": p6_available, "artifactRegistered": artifact_registered,
            "boundArtifactPresent": bound_present, "promotable": promotable,
            "promotionBlockedReason": reason}


async def list_declared_targets_tool(*, declared_target_id: str | None = None) -> "dict[str, Any]":
    """List/inspect declared targets with a computed 'observed' block. Guards P7-unusable; DEGRADES
    (does not fail closed) on a P6 skew so perception is never fully blocked by the lower plane.
    An explicit unknown declared_target_id is a malformed request -> declared_target_not_found."""
    if (u := await _registry_unusable()) is not None:
        return u
    if declared_target_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_declared_target(declared_target_id)) is None:
            return _err("declared_target_not_found", f"No declared target {declared_target_id!r}.")
    p6_available = (await _p6_unusable()) is None
    def _build() -> "list[dict[str, Any]]":
        reg = work_units_registry()
        rows = ([reg.get_declared_target(declared_target_id)] if declared_target_id
                else reg.list_declared_targets())
        rows = [r for r in rows if r is not None]
        return [{"declaredTargetId": r.declared_target_id, "workUnitId": r.work_unit_id,
                 "intendedPath": r.intended_path, "normalizedPath": r.normalized_path,
                 "predictedArtifactId": r.predicted_artifact_id, "status": r.status,
                 "boundArtifactId": r.bound_artifact_id, "label": r.label,
                 "createdAt": r.created_at, "materializedAt": r.materialized_at,
                 "observed": _observe_declared_target(r, p6_available)} for r in rows]
    return {"success": True, "data": {"declaredTargets": await asyncio.to_thread(_build),
                                      "p6Available": p6_available}}
```

- [ ] **Step 4: Add the work-unit join to `list_work_units_tool`**

In `list_work_units_tool`'s `_build`, add `"declaredTargets"` to each unit's dict (next to `"contracts"`):

```python
                        "contracts": reg.contracts_for(r.work_unit_id),
                        "declaredTargets": reg.declared_targets_for(r.work_unit_id)})
```

(The existing line ends with `reg.contracts_for(r.work_unit_id)})` — replace the closing `})` so the new key is inside the dict.)

- [ ] **Step 5: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "test_declared_targets_observation or promotable_honors or non_authoritative or work_unit_join or unknown_id_is_not_found" -v`
Expected: PASS (5 tests). Then the whole file: `... -m pytest mcp_server/tests/test_work_units.py -q` (all green).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "P7 S2 T5: declared_targets listing + observations + work-unit join

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Wiring — server decls + dispatch, targeting sets, tool tests + 4-surface audit

**Files:**
- Modify: `mcp_server/src/rook/server.py`, `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_work_units_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `mcp_server/tests/test_work_units_tools.py`:

```python
def test_p7_slice2_tools_are_meta_no_rhino():
    for name in ("rhino_declared_target_declare", "rhino_declared_target_promote", "rhino_declared_targets"):
        assert name in targeting._ALL_KNOWN_TOOLS
        assert name in targeting._META_TOOLS
        assert targeting.policy_for_tool(name).requires_rhino is False


def test_call_tool_dispatches_declare(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()
    out = asyncio.run(server.call_tool("rhino_declared_target_declare",
        {"intendedPath": str(tmp_path / "m.3dm"), "label": "M"}))
    from rook.tool_result import parse_call_tool_data
    data = parse_call_tool_data(out)
    assert data["declaredTargetId"].startswith("dt-")
    work_units._reset_work_units_registry_singleton()
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py -v`
Expected: FAIL — names not in `_ALL_KNOWN_TOOLS`; `call_tool` has no case for `rhino_declared_target_declare`.

- [ ] **Step 3: Add the three `Tool(...)` decls in `server.py`**

Immediately after the `rhino_work_units` `Tool(...)` block (ends ~line 2926, before `rhino_ping`):

```python
        Tool(
            name="rhino_declared_target_declare",
            description="Declare coordinator intent toward a master/anchor file BEFORE it exists "
                        "(intendedPath -> predicted artifact id). Records intent only; no P6 write, "
                        "no Rhino. Optional workUnitId links it to an assignment.",
            inputSchema={"type": "object", "properties": {
                "intendedPath": {"type": "string"}, "label": {"type": "string"},
                "workUnitId": {"type": "string"}},
                "required": ["intendedPath"]},
        ),
        Tool(
            name="rhino_declared_target_promote",
            description="Materialize a declared target: register the now-saved file through P6, "
                        "verify path identity, and bind it. The ONLY state transition; idempotent. No Rhino.",
            inputSchema={"type": "object", "properties": {
                "declaredTargetId": {"type": "string"}},
                "required": ["declaredTargetId"]},
        ),
        Tool(
            name="rhino_declared_targets",
            description="List/inspect declared targets with computed observations (fileState, "
                        "promotable, promotionBlockedReason, ...). Read-only; never transitions. "
                        "Optional declaredTargetId.",
            inputSchema={"type": "object", "properties": {"declaredTargetId": {"type": "string"}}},
        ),
```

- [ ] **Step 4: Add the three dispatch arms in `server.py`**

Immediately after the `case "rhino_work_units":` block (ends ~line 12952, before `case "rhino_ping":`):

```python
        case "rhino_declared_target_declare":
            result = await work_units.declared_target_declare_tool(
                intended_path=arguments.get("intendedPath"), label=arguments.get("label"),
                work_unit_id=arguments.get("workUnitId"))

        case "rhino_declared_target_promote":
            result = await work_units.declared_target_promote_tool(
                declared_target_id=arguments.get("declaredTargetId"))

        case "rhino_declared_targets":
            result = await work_units.list_declared_targets_tool(
                declared_target_id=arguments.get("declaredTargetId"))
```

- [ ] **Step 5: Add the three names to `targeting.py`**

After `"rhino_work_units",` in `_ALL_KNOWN_TOOLS` (~line 160) AND in `_META_TOOLS` (~line 563), add:

```python
    "rhino_declared_target_declare",
    "rhino_declared_target_promote",
    "rhino_declared_targets",
```

- [ ] **Step 6: 4-surface audit — find any other surface enumerating P7 tools**

Run: `grep -rn "rhino_work_units\b" mcp_server/ docs/ --include=*.py --include=*.md`
For every surface that lists the Slice-1 P7 tools as a *catalog/persona/knowledge* set (not the dispatch/decl/targeting already handled above), add the three new names alongside. If the only hits are `server.py` / `targeting.py` / tests (already covered), record "no additional surface" and move on.

- [ ] **Step 7: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py -v`
Expected: PASS (existing Slice-1 tests + 2 new). Sanity-import the server: `mcp_server/.venv/Scripts/python.exe -c "import rook.server"` (no syntax error).

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/targeting.py mcp_server/tests/test_work_units_tools.py
git commit -m "P7 S2 T6: wire declare/promote/declared_targets tools (server + targeting)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Full suite + baseline parity + finish branch

**Files:** none (verification only)

- [ ] **Step 1: Run the two P7 test files**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py mcp_server/tests/test_work_units_tools.py -v`
Expected: ALL PASS (Slice 1 + the ~17 new Slice 2 tests).

- [ ] **Step 2: Restore knowledge/ hygiene (pre-parity)**

```bash
git checkout -- knowledge/ 2>/dev/null; rm -rf knowledge/selectors 2>/dev/null; true
```

- [ ] **Step 3: Full-suite baseline parity vs main (blessed non-live gate, named sets both directions)**

The gate is **named-set parity**, not counts. Use the blessed non-live command (scoped to `tests`,
stable collection, no cache, names only) on BOTH the branch and `main`, then `comm` the sorted
failed/error name sets both directions:

```bash
# on the branch:
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" \
    -p no:cacheprovider -q -rfE --tb=no > /tmp/p7s2_branch.txt 2>&1
grep -E "^(FAILED|ERROR)" /tmp/p7s2_branch.txt | awk '{print $1, $2}' | sort > /tmp/p7s2_branch_named.txt

# on main (git stash or a second worktree), the SAME command -> /tmp/p7s2_main_named.txt
# then compare BOTH directions:
comm -23 /tmp/p7s2_branch_named.txt /tmp/p7s2_main_named.txt   # NEW failures on branch — MUST be empty
comm -13 /tmp/p7s2_branch_named.txt /tmp/p7s2_main_named.txt   # failures that vanished — MUST be empty
```

Baseline reference: main is **64 failed / 41 errors** under this exact command. The gate passes only when
the branch's named failed/error set is **identical** to main's (empty `comm` both directions) AND every
new P7-S2 test PASSES (absent from both named sets). A non-empty `comm -23` is a real regression — fix
before proceeding; never accept a count that merely "looks close."

- [ ] **Step 4: Finish the branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Verify tests pass, then present the 4 options. Default per project workflow: **push + open PR** for Codex review, then the user pulls the squash-merge trigger:

```bash
git push -u origin feature/p7-slice2-declared-targets
gh pr create --title "P7 Slice 2: declared-target state machine — declare + promote a master before it exists" --body "$(cat <<'EOF'
## Summary
- Adds a P7-only `declared_targets` ledger: `declare` intent toward a not-yet-existing anchor, `promote` it (register through P6 + drift-verify + bind), and `declared_targets` to list/inspect with computed observations.
- Stored states `{declared, materialized}` only; `materialized` is non-authoritative for current existence. No merge execution, no geometry, no change to Slice 1 `merge_contracts`.
- Additive `p7.1 -> p7.2` migration (never bricks existing dbs). Promotion is the first P7->P6 write, via P6's public `register_artifact` (no P7 vocabulary into P6). Cross-DB window made safe by idempotent retry.

## Test Plan
- [ ] `test_work_units.py` + `test_work_units_tools.py` green (Slice 1 + ~17 new)
- [ ] Baseline parity vs main: 64 failed / 41 errors unchanged, named sets identical both directions
- [ ] (Optional) live smoke `p7-declared-target` through the harness — deferrable; P7 never touches Rhino

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage (against `2026-06-06-p7-slice2-...-design.md`):**
- §5 schema + `_REQUIRED_COLUMNS` shape guard → Task 1. §10 additive `p7.1→p7.2` (existing-tables-only guard, meta upgrade) → Task 1 Steps 3–5 + `test_additive_migration_p71_to_p72_preserves_data`.
- §6 promote (drift check, P6 envelope-by-`data.code`, bind verification, idempotency) → Task 4, incl. the P6 hard guard (`test_promote_fails_closed_on_p6_skew`) and the unreachable mapping (`test_promote_maps_unreachable_envelope`). §6.1 cross-DB window → `test_promote_completes_after_p6_already_registered`.
- §7 declare + conflict envelope (`success:false` + `existingDeclaredTargetId`) → Task 3. `materialized` non-authoritative → `test_materialized_is_non_authoritative`.
- §8 observations + `promotable` includes `p6Available` + `promotionBlockedReason` ordering → Task 5 (`_observe_declared_target`, `test_declared_targets_promotable_honors_p6_availability`, `test_declared_targets_observation_transitions_nothing`); inspect-unknown-id → `declared_target_not_found` (`test_declared_targets_unknown_id_is_not_found`). Work-unit join → Task 5 Step 4.
- §9 failure taxonomy → `_RETRYABLE` (Task 3) + raised across Tasks 3–4. §11 tool surface + non-routed/no-Rhino → Task 6.
- §12 testing incl. baseline parity → Tasks 1–7.

**Placeholder scan:** none — every step shows complete code or an exact command.

**Type/name consistency:** `declared_target_declare_tool` / `declared_target_promote_tool` / `list_declared_targets_tool` used identically in their defining task, the `server.py` dispatch (Task 6 Step 4), and tests. `DeclaredTargetRow` field order matches `_DECLARED_TARGET_COLUMNS`. `DeclaredTargetConflict.existing_id` set in Task 2, consumed in Task 3. Envelope keys (`declaredTargetId`, `predictedArtifactId`, `boundArtifactId`, `promotable`, `promotionBlockedReason`, `existingDeclaredTargetId`, `p6Available`) consistent across tools and tests.

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended by skill)** — fresh subagent per task + two-stage review.
2. **Inline Execution** — execute in this session with checkpoints.

Given the plan is self-contained and small (one module + two test files, mirroring the just-shipped Slice 1), **inline** is likely the lower-overhead choice — the same call made for Slice 1. Awaiting your pick.
