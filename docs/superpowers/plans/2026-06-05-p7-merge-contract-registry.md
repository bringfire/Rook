# P7 Slice 1 — Merge-Contract Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A coordinator-plane registry that records Work Units + their P6 artifact provenance and Merge Contracts (a `sources → target` dependency DAG), then validates well-formedness + present-bar against P6 and returns the topological **contract** recompose order — recording fan-in intent without executing any merge.

**Architecture:** New leaf module `work_units.py` owning a separate `work_units.db` (the `artifacts.py` SQLite substrate — `BEGIN IMMEDIATE`/WAL/additive-version-gated). It reads P6 artifacts **read-only** via `rook.artifacts.ArtifactRegistry` (resolve `artifact_id` → row, check `file_state=='present'`) and **never** writes `artifacts.db`. Five MCP tools, non-routed, Rhino-independent. Invariant: **P7 references P6 by `artifact_id`; P6 never references P7.**

**Tech Stack:** Python 3.10+ (editable install — no rebuild for unit tests), `sqlite3`, `networkx` (already a dependency; `lexicographical_topological_sort`), `pytest`. Spec: `docs/superpowers/specs/2026-06-05-p7-slice1-merge-contract-registry-design.md`.

**Pytest:** `mcp_server/.venv/Scripts/python.exe -m pytest`

---

## Setup

- [ ] **Branch off main:**

```bash
cd C:/Users/aryan/source/repos/Rook
git checkout main && git pull && git checkout -b feature/p7-merge-contract-registry
```

## File structure

- **Create** `mcp_server/src/rook/work_units.py` — the registry (5 tables) + the shared resolvers + the 5 async tool functions. One module: it is a self-contained coordinator-plane store ~ the size of `artifacts.py`.
- **Create** `mcp_server/tests/test_work_units.py` — unit + pure-Python integration (real P6 `ArtifactRegistry`, real temp files, **no Rhino**).
- **Modify** `mcp_server/src/rook/server.py` — `from . import work_units` (near `from . import artifacts`), 5 `Tool(...)` decls (after the artifact decls ~l.2881), 5 dispatch `case` arms (after the artifact cases ~l.12884).
- **Modify** `mcp_server/src/rook/targeting.py` — add the 5 tool names to `_ALL_KNOWN_TOOLS` (l.148) and `_META_TOOLS` (l.546).
- **(Optional, deferrable)** `scripts/run_rhino_runtime_harness.py` + `mcp_server/tools/p7_merge_contract_live_harness.py` — the end-to-end live smoke (Task 9).

---

## Task 1: `work_units.py` storage substrate + 5-table schema

**Files:** Create `mcp_server/src/rook/work_units.py`; Test `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing test** (`test_work_units.py`):

```python
from __future__ import annotations
import sqlite3
from pathlib import Path
import pytest
from rook import work_units


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
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: rook.work_units`).

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -q`

- [ ] **Step 3: Create `work_units.py`** with imports, constants, `_ImmediateTx` (verbatim from `artifacts.py:87-109`), and `WorkUnitRegistry` with the 5-table schema:

```python
"""P7 Slice 1 — coordinator-plane merge-contract registry.

Records Work Units + their P6 artifact provenance and Merge Contracts (a sources->target
dependency DAG), and validates fan-in intent. Records intent ONLY — no merge executes, no
geometry enters Rhino. Reads P6 artifacts READ-ONLY; never writes artifacts.db.
Invariant: P7 references P6 by artifact_id; P6 never references P7.
See docs/superpowers/specs/2026-06-05-p7-slice1-merge-contract-registry-design.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from . import artifacts as _artifacts   # read-only P6 access (resolve + present check)

WORK_UNITS_REGISTRY_VERSION = "p7.1"

MERGE_KINDS = ("worksession", "import", "linked_block", "reference", "block", "report")
REFRESH_POLICIES = ("refresh_after_save", "refresh_on_demand")
RELATIONS = ("produced", "consumed")


def resolve_work_units_db_path() -> Path:
    """%LOCALAPPDATA%/Rook/registry/work_units.db, falling back to %TEMP%/rook/registry.
    Separate file from P5 owned_sessions.db and P6 artifacts.db."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = (Path(local_app_data) / "Rook" / "registry") if local_app_data \
        else (Path(tempfile.gettempdir()) / "rook" / "registry")
    return root / "work_units.db"


class _ImmediateTx:
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error) holding the RLock — verbatim from
    artifacts.py (duplication accepted; no shared base in Slice 1)."""
    def __init__(self, conn: sqlite3.Connection, lock: "threading.RLock"):
        self._conn = conn
        self._lock = lock

    def __enter__(self):
        self._lock.acquire()
        try:
            self._conn.execute("BEGIN IMMEDIATE;")
        except Exception:
            self._lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._conn.execute("COMMIT;" if exc_type is None else "ROLLBACK;")
        finally:
            self._lock.release()
        return False


@dataclass(frozen=True)
class WorkUnitRow:
    work_unit_id: str
    label: str
    role: str | None
    metadata: str | None
    created_at: int


@dataclass(frozen=True)
class ContractRow:
    contract_id: str
    target_artifact_id: str
    merge_kind: str
    refresh_policy: str
    created_at: int


class WorkUnitRegistry:
    """Durable coordinator-plane store. Additive / version-gated / fail-closed (NEVER DROP)."""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.schema_unsupported: str | None = None
        self._conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._ensure_schema()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _immediate(self) -> "_ImmediateTx":
        return _ImmediateTx(self._conn, self._lock)

    def _ensure_schema(self) -> None:
        c = self._conn
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
        stored = c.execute(
            "SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
        if stored is not None and stored[0] != WORK_UNITS_REGISTRY_VERSION:
            self.schema_unsupported = stored[0]
            return
        c.execute("""CREATE TABLE IF NOT EXISTS work_units (
            work_unit_id TEXT PRIMARY KEY, label TEXT NOT NULL, role TEXT,
            metadata TEXT, created_at INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS work_unit_artifacts (
            work_unit_id TEXT NOT NULL, artifact_id TEXT NOT NULL, relation TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (work_unit_id, artifact_id, relation));""")
        c.execute("""CREATE TABLE IF NOT EXISTS merge_contracts (
            contract_id TEXT PRIMARY KEY, target_artifact_id TEXT NOT NULL,
            merge_kind TEXT NOT NULL, refresh_policy TEXT NOT NULL, created_at INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS merge_contract_sources (
            contract_id TEXT NOT NULL, source_artifact_id TEXT NOT NULL,
            PRIMARY KEY (contract_id, source_artifact_id));""")
        c.execute("""CREATE TABLE IF NOT EXISTS work_unit_merge_contracts (
            work_unit_id TEXT NOT NULL, contract_id TEXT NOT NULL, created_at INTEGER NOT NULL,
            PRIMARY KEY (work_unit_id, contract_id));""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wua_wu ON work_unit_artifacts(work_unit_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mcs_contract ON merge_contract_sources(contract_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wumc_wu ON work_unit_merge_contracts(work_unit_id);")
        if stored is None:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('work_units_registry_version', ?);",
                      (WORK_UNITS_REGISTRY_VERSION,))
```

- [ ] **Step 4: Run → PASS** (3 tests).
- [ ] **Step 5: Commit**

```bash
git checkout -- knowledge/ 2>/dev/null ; rm -rf knowledge/selectors 2>/dev/null
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "feat(p7): work_units.py storage substrate + 5-table schema (version-gated, fail-closed)"
```

---

## Task 2: Work-unit register + many-to-many links (registry reads/writes)

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing test** (append):

```python
def test_register_link_and_work_unit_centric_read(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.register_work_unit("facade-study", label="Facade", role="study", metadata=None, now=100)
    # many-to-many: one work unit, several artifacts; relations distinct
    reg.link_artifact("facade-study", "artA", "produced", now=101)
    reg.link_artifact("facade-study", "artB", "produced", now=102)
    reg.link_artifact("facade-study", "master", "consumed", now=103)
    assert reg.get_work_unit("facade-study").label == "Facade"
    arts = {(a, rel) for a, rel in reg.artifacts_for("facade-study")}
    assert arts == {("artA", "produced"), ("artB", "produced"), ("master", "consumed")}
    # an artifact may belong to many work units (many-to-many the other way)
    reg.register_work_unit("ctx", label="Context", role=None, metadata=None, now=110)
    reg.link_artifact("ctx", "artA", "consumed", now=111)
    assert {wu for wu, _ in reg.work_units_for_artifact("artA")} == {"facade-study", "ctx"}
    reg.close()
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: register_work_unit`).

- [ ] **Step 3: Implement** (append to `WorkUnitRegistry`):

```python
    # ----- work units (writes are single-statement; RLock-guarded) -----
    def register_work_unit(self, work_unit_id: str, *, label: str, role: str | None,
                           metadata: str | None, now: int) -> None:
        with self._immediate():
            self._conn.execute(
                "INSERT OR REPLACE INTO work_units(work_unit_id, label, role, metadata, created_at) "
                "VALUES(?,?,?,?,?);", (work_unit_id, label, role, metadata, now))

    def link_artifact(self, work_unit_id: str, artifact_id: str, relation: str, *, now: int) -> None:
        with self._immediate():
            self._conn.execute(
                "INSERT OR IGNORE INTO work_unit_artifacts(work_unit_id, artifact_id, relation, created_at) "
                "VALUES(?,?,?,?);", (work_unit_id, artifact_id, relation, now))

    def get_work_unit(self, work_unit_id: str) -> "WorkUnitRow | None":
        with self._lock:
            raw = self._conn.execute(
                "SELECT work_unit_id, label, role, metadata, created_at FROM work_units "
                "WHERE work_unit_id=?;", (work_unit_id,)).fetchone()
            return None if raw is None else WorkUnitRow(*raw)

    def list_work_units(self) -> "list[WorkUnitRow]":
        with self._lock:
            return [WorkUnitRow(*r) for r in self._conn.execute(
                "SELECT work_unit_id, label, role, metadata, created_at FROM work_units "
                "ORDER BY created_at, work_unit_id;").fetchall()]

    def artifacts_for(self, work_unit_id: str) -> "list[tuple[str, str]]":
        with self._lock:
            return [(a, rel) for a, rel in self._conn.execute(
                "SELECT artifact_id, relation FROM work_unit_artifacts WHERE work_unit_id=? "
                "ORDER BY created_at, artifact_id;", (work_unit_id,)).fetchall()]

    def work_units_for_artifact(self, artifact_id: str) -> "list[tuple[str, str]]":
        with self._lock:
            return [(wu, rel) for wu, rel in self._conn.execute(
                "SELECT work_unit_id, relation FROM work_unit_artifacts WHERE artifact_id=? "
                "ORDER BY work_unit_id;", (artifact_id,)).fetchall()]
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(p7): work-unit register + many-to-many artifact links`

---

## Task 3: Shared present-bar resolver against P6 (read-only)

The single source of truth for "is this artifact usable in a merge?" — backs `record` AND `validate`. Reads P6 via `rook.artifacts.artifact_registry()` (read-only); never writes.

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing test** (append) — uses a REAL P6 registry over a temp db + real temp files:

```python
import time as _time
from rook import artifacts


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
    # all present -> no problems
    assert work_units._resolve_present([ids["a.3dm"], ids["b.3dm"]]) == []
    # unknown id -> artifact_not_registered
    probs = work_units._resolve_present(["deadbeef"])
    assert probs == [{"code": "artifact_not_registered", "artifactId": "deadbeef"}]
    # delete the file on disk + refresh P6 -> present row goes missing -> artifact_not_present
    files["a.3dm"].unlink()
    artifacts.artifact_registry().set_state(
        artifacts.normalize_path(str(files["a.3dm"])), file_state="missing", size=None, mtime=None,
        now=int(_time.time()))
    probs = work_units._resolve_present([ids["a.3dm"]])
    assert probs == [{"code": "artifact_not_present", "artifactId": ids["a.3dm"]}]
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: _resolve_present`).

- [ ] **Step 3: Implement** (append, module level):

```python
def _p6_row(artifact_id: str):
    """Read-only P6 lookup. Returns the ArtifactRow or None. Never writes artifacts.db."""
    return _artifacts.artifact_registry().get(artifact_id=artifact_id)


def _resolve_present(artifact_ids) -> "list[dict[str, Any]]":
    """The present-bar: each id must resolve to a P6 row currently file_state=='present'.
    Returns a problems list ([] when all pass). Shared by record and validate."""
    problems: list[dict[str, Any]] = []
    for aid in artifact_ids:
        row = _p6_row(aid)
        if row is None:
            problems.append({"code": "artifact_not_registered", "artifactId": aid})
        elif row.file_state != "present":
            problems.append({"code": "artifact_not_present", "artifactId": aid})
    return problems


def _is_registered(artifact_id: str) -> bool:
    """The link-bar: provenance is historical — a since-missing artifact is still a valid link.
    Registered is enough; present is NOT required (spec §9 / decision log)."""
    return _p6_row(artifact_id) is not None
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(p7): shared present-bar resolver (read-only P6) + registered link-bar`

---

## Task 4: `insert_contract` — atomic, all-or-nothing write

The registry-level atomic write. **Validation is the tool layer's job (Task 6); this method only writes, in one transaction.**

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing test** (append):

```python
def test_insert_contract_atomic_and_dedup_join(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.register_work_unit("wu", label="W", role=None, metadata=None, now=1)
    cid = reg.insert_contract("c1", target="M", sources=["A", "B"], merge_kind="linked_block",
                              refresh_policy="refresh_after_save", work_unit_id="wu", now=10)
    assert cid == "c1"
    assert reg.get_contract("c1").target_artifact_id == "M"
    assert set(reg.sources_for("c1")) == {"A", "B"}
    assert reg.contracts_for("wu") == ["c1"]
    # a second insert with a fresh id (no idempotency) coexists
    reg.insert_contract("c2", target="M", sources=["A"], merge_kind="reference",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=11)
    assert {r.contract_id for r in reg.list_contracts()} == {"c1", "c2"}
    reg.close()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append to `WorkUnitRegistry`):

```python
    # ----- merge contracts (atomic, all-or-nothing) -----
    def insert_contract(self, contract_id: str, *, target: str, sources: "list[str]",
                        merge_kind: str, refresh_policy: str, work_unit_id: str | None, now: int) -> str:
        """ONE transaction: contract row + every source row + the optional work-unit join.
        Caller (the tool layer) has already validated; this method only persists."""
        with self._immediate():
            self._conn.execute(
                "INSERT INTO merge_contracts(contract_id, target_artifact_id, merge_kind, "
                "refresh_policy, created_at) VALUES(?,?,?,?,?);",
                (contract_id, target, merge_kind, refresh_policy, now))
            self._conn.executemany(
                "INSERT INTO merge_contract_sources(contract_id, source_artifact_id) VALUES(?,?);",
                [(contract_id, s) for s in sources])
            if work_unit_id is not None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO work_unit_merge_contracts(work_unit_id, contract_id, created_at) "
                    "VALUES(?,?,?);", (work_unit_id, contract_id, now))
        return contract_id

    def get_contract(self, contract_id: str) -> "ContractRow | None":
        with self._lock:
            raw = self._conn.execute(
                "SELECT contract_id, target_artifact_id, merge_kind, refresh_policy, created_at "
                "FROM merge_contracts WHERE contract_id=?;", (contract_id,)).fetchone()
            return None if raw is None else ContractRow(*raw)

    def list_contracts(self) -> "list[ContractRow]":
        with self._lock:
            return [ContractRow(*r) for r in self._conn.execute(
                "SELECT contract_id, target_artifact_id, merge_kind, refresh_policy, created_at "
                "FROM merge_contracts ORDER BY created_at, contract_id;").fetchall()]

    def sources_for(self, contract_id: str) -> "list[str]":
        with self._lock:
            return [s for (s,) in self._conn.execute(
                "SELECT source_artifact_id FROM merge_contract_sources WHERE contract_id=? "
                "ORDER BY source_artifact_id;", (contract_id,)).fetchall()]

    def contracts_for(self, work_unit_id: str) -> "list[str]":
        with self._lock:
            return [c for (c,) in self._conn.execute(
                "SELECT contract_id FROM work_unit_merge_contracts WHERE work_unit_id=? "
                "ORDER BY created_at, contract_id;", (work_unit_id,)).fetchall()]
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(p7): insert_contract — atomic contract+sources+join write`

---

## Task 5: The pure graph validator (cycle + deterministic contractOrder)

A pure function over a registry snapshot: present re-check + structural + acyclicity over the **contract** graph, returning the deterministic `contractOrder`.

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing test** (append):

```python
def test_validate_graph_order_determinism_and_cycle(tmp_path, monkeypatch):
    ids, _ = _p6_with(tmp_path, monkeypatch, ["A.3dm", "B.3dm", "C.3dm", "M1.3dm", "master.3dm"])
    reg = _fresh_registry(tmp_path)
    A, B, C, M1, MASTER = (ids["A.3dm"], ids["B.3dm"], ids["C.3dm"], ids["M1.3dm"], ids["master.3dm"])
    # stage 1: A,B -> M1 ; stage 2: M1,C -> master  (c_stage2 depends on c_stage1 via M1)
    reg.insert_contract("c_stage2", target=MASTER, sources=[M1, C], merge_kind="import",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=20)
    reg.insert_contract("c_stage1", target=M1, sources=[A, B], merge_kind="linked_block",
                        refresh_policy="refresh_after_save", work_unit_id=None, now=10)
    res = work_units._validate_graph(reg)
    assert res["ok"] is True
    # c_stage1 (produces M1) MUST precede c_stage2 (consumes M1), regardless of insert order
    assert res["contractOrder"] == ["c_stage1", "c_stage2"]
    # determinism: run twice -> identical
    assert work_units._validate_graph(reg)["contractOrder"] == res["contractOrder"]

    # a cycle: target(cX)=X used by cY, target(cY)=Y used by cX
    reg2 = _fresh_registry(tmp_path / "two")
    reg2.insert_contract("cX", target=A, sources=[B], merge_kind="reference",
                         refresh_policy="refresh_on_demand", work_unit_id=None, now=1)
    reg2.insert_contract("cY", target=B, sources=[A], merge_kind="reference",
                         refresh_policy="refresh_on_demand", work_unit_id=None, now=2)
    res2 = work_units._validate_graph(reg2)
    assert res2["ok"] is False
    assert any(p["code"] == "merge_cycle_detected" for p in res2["problems"])
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append, module level). Precedence: **contract A precedes B iff `target(A)` ∈ `sources(B)`**; independent contracts tiebreak `(created_at, contract_id)`:

```python
def _structural_problems(target: str, sources: "list[str]", merge_kind: str,
                         refresh_policy: str) -> "list[dict[str, Any]]":
    """Local well-formedness shared by record + validate (NOT present, NOT acyclicity)."""
    problems: list[dict[str, Any]] = []
    if not sources:
        problems.append({"code": "empty_sources"})
    if len(sources) != len(set(sources)):
        problems.append({"code": "duplicate_contract_source"})
    if merge_kind not in MERGE_KINDS:
        problems.append({"code": "unknown_merge_kind", "value": merge_kind})
    if refresh_policy not in REFRESH_POLICIES:
        problems.append({"code": "unknown_refresh_policy", "value": refresh_policy})
    if target in sources:
        problems.append({"code": "merge_self_reference", "artifactId": target})
    return problems


def _validate_graph(reg: "WorkUnitRegistry") -> "dict[str, Any]":
    """Pure, on-demand validation of the WHOLE contract graph. Never stored."""
    contracts = reg.list_contracts()
    problems: list[dict[str, Any]] = []
    target_of: dict[str, str] = {}
    sources_of: dict[str, list[str]] = {}
    order_key: dict[str, tuple] = {}
    for ct in contracts:
        srcs = reg.sources_for(ct.contract_id)
        target_of[ct.contract_id] = ct.target_artifact_id
        sources_of[ct.contract_id] = srcs
        order_key[ct.contract_id] = (ct.created_at, ct.contract_id)
        problems += [{**p, "contractId": ct.contract_id} for p in
                     _structural_problems(ct.target_artifact_id, srcs, ct.merge_kind, ct.refresh_policy)]
        problems += [{**p, "contractId": ct.contract_id} for p in
                     _resolve_present(srcs + [ct.target_artifact_id])]

    # Contract dependency graph: edge A -> B iff target(A) is a source of B.
    g = nx.DiGraph()
    g.add_nodes_from(order_key)
    for a in contracts:
        for b in contracts:
            if a.contract_id != b.contract_id and target_of[a.contract_id] in sources_of[b.contract_id]:
                g.add_edge(a.contract_id, b.contract_id, viaArtifact=target_of[a.contract_id])

    contract_order: list[str] | None = None
    try:
        contract_order = list(nx.lexicographical_topological_sort(g, key=lambda n: order_key[n]))
    except nx.NetworkXUnfeasible:
        cycle = nx.find_cycle(g)
        problems.append({"code": "merge_cycle_detected",
                         "cycle": [u for u, _, _ in cycle] + [cycle[-1][1]]})

    if problems:
        return {"ok": False, "problems": problems}

    artifact_order: list[str] = []
    for cid in contract_order:
        for s in sources_of[cid]:
            if s not in artifact_order:
                artifact_order.append(s)
        if target_of[cid] not in artifact_order:
            artifact_order.append(target_of[cid])
    return {
        "ok": True,
        "contractOrder": contract_order,
        "artifactOrder": artifact_order,
        "edges": [{"from": u, "to": v, "viaArtifact": d["viaArtifact"]} for u, v, d in g.edges(data=True)],
        "contracts": [{"contractId": c.contract_id, "target": target_of[c.contract_id],
                       "sources": sources_of[c.contract_id], "mergeKind": c.merge_kind,
                       "refreshPolicy": c.refresh_policy} for c in contracts],
    }
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(p7): pure graph validator — deterministic contractOrder + cycle detection`

---

## Task 6: The 5 async tool functions ({success, data} envelopes)

The public surface. `record` runs ALL checks before any write (atomic). Singleton + `_err` + fail-closed mirror `artifacts.py`.

**Files:** Modify `work_units.py`; Test `test_work_units.py`

- [ ] **Step 1: Write the failing test** (append):

```python
import asyncio


def _repoint_p7(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()


def test_tools_record_rejects_and_validates(tmp_path, monkeypatch):
    ids, files = _p6_with(tmp_path, monkeypatch, ["A.3dm", "B.3dm", "M.3dm"])
    _repoint_p7(tmp_path, monkeypatch)
    A, B, M = ids["A.3dm"], ids["B.3dm"], ids["M.3dm"]

    reg_wu = asyncio.run(work_units.register_work_unit_tool(label="W", role=None, metadata=None,
                                                            work_unit_id="wu"))
    assert reg_wu["success"] is True and reg_wu["data"]["workUnitId"] == "wu"

    # record present-bar reject (unregistered source) -> _err, NOTHING written
    bad = asyncio.run(work_units.record_merge_contract(target_artifact_id=M,
        source_artifact_ids=[A, "ghost"], merge_kind="linked_block",
        refresh_policy="refresh_after_save", work_unit_id=None))
    assert bad["success"] is False and bad["data"]["code"] == "artifact_not_registered"
    assert work_units.work_units_registry().list_contracts() == []   # atomicity

    # structural reject: duplicate source
    dup = asyncio.run(work_units.record_merge_contract(target_artifact_id=M,
        source_artifact_ids=[A, A], merge_kind="linked_block",
        refresh_policy="refresh_after_save", work_unit_id=None))
    assert dup["success"] is False and dup["data"]["code"] == "duplicate_contract_source"

    # good record (with work-unit link)
    ok = asyncio.run(work_units.record_merge_contract(target_artifact_id=M,
        source_artifact_ids=[A, B], merge_kind="linked_block",
        refresh_policy="refresh_after_save", work_unit_id="wu"))
    assert ok["success"] is True
    cid = ok["data"]["contractId"]

    # validate whole graph -> ok + contractOrder
    val = asyncio.run(work_units.validate_merge_contract(contract_id=None))
    assert val["success"] is True and val["data"]["ok"] is True
    assert val["data"]["contractOrder"] == [cid]

    # work-unit-centric query sees the artifact links + the contract
    wu = asyncio.run(work_units.list_work_units_tool(work_unit_id="wu"))
    assert wu["data"]["workUnits"][0]["contracts"] == [cid]

    # malformed validate request -> _err
    nf = asyncio.run(work_units.validate_merge_contract(contract_id="nope"))
    assert nf["success"] is False and nf["data"]["code"] == "contract_not_found"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (append, module level):

```python
_RETRYABLE = {
    "artifact_not_registered": False, "artifact_not_present": True,
    "empty_sources": False, "duplicate_contract_source": False,
    "unknown_merge_kind": False, "unknown_refresh_policy": False,
    "merge_self_reference": False, "work_unit_not_found": False,
    "contract_not_found": False, "invalid_relation": False, "invalid_argument": False,
    "work_units_registry_unavailable": True,
}


def _err(code: str, message: str, **extra: Any) -> "dict[str, Any]":
    return {"success": False, "data": {
        "code": code, "message": message, "retryable": _RETRYABLE.get(code, True), **extra}}


_WORK_UNITS_REGISTRY: "WorkUnitRegistry | None" = None


def work_units_registry() -> "WorkUnitRegistry":
    global _WORK_UNITS_REGISTRY
    if _WORK_UNITS_REGISTRY is None:
        _WORK_UNITS_REGISTRY = WorkUnitRegistry(resolve_work_units_db_path())
    return _WORK_UNITS_REGISTRY


def _reset_work_units_registry_singleton() -> None:
    """Test-only: drop the process-global registry so a fixture can repoint the db path."""
    global _WORK_UNITS_REGISTRY
    if _WORK_UNITS_REGISTRY is not None:
        _WORK_UNITS_REGISTRY.close()
    _WORK_UNITS_REGISTRY = None


async def _registry_unusable() -> "dict[str, Any] | None":
    reg = await asyncio.to_thread(work_units_registry)
    bad = getattr(reg, "schema_unsupported", None)
    if bad is not None:
        return _err("work_units_registry_unavailable",
                    f"Work-unit registry was written by an incompatible version {bad!r}; "
                    "rows are left intact. Resolve the version skew before using P7 tools.")
    return None


async def register_work_unit_tool(*, label: str, role: str | None = None,
                                  metadata: Any = None, work_unit_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if not isinstance(label, str) or not label.strip():
        return _err("invalid_argument", "'label' must be a non-empty string.")
    wid = work_unit_id if (isinstance(work_unit_id, str) and work_unit_id.strip()) else f"wu-{uuid.uuid4().hex[:12]}"
    meta_json = None if metadata is None else json.dumps(metadata)
    await asyncio.to_thread(lambda: work_units_registry().register_work_unit(
        wid, label=label, role=role, metadata=meta_json, now=int(time.time())))
    return {"success": True, "data": {"workUnitId": wid, "label": label}}


async def link_artifact_tool(*, work_unit_id: str, artifact_id: str, relation: str) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if relation not in RELATIONS:
        return _err("invalid_relation", f"'relation' must be one of {RELATIONS}, got {relation!r}.")
    if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
        return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    if not await asyncio.to_thread(_is_registered, artifact_id):   # link-bar: registered (present NOT required)
        return _err("artifact_not_registered", f"Artifact {artifact_id!r} is not registered in P6.")
    await asyncio.to_thread(lambda: work_units_registry().link_artifact(
        work_unit_id, artifact_id, relation, now=int(time.time())))
    return {"success": True, "data": {"workUnitId": work_unit_id, "artifactId": artifact_id,
                                      "relation": relation}}


async def record_merge_contract(*, target_artifact_id: str, source_artifact_ids: "list[str]",
                                merge_kind: str, refresh_policy: str,
                                work_unit_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if not isinstance(target_artifact_id, str) or not target_artifact_id.strip():
        return _err("invalid_argument", "'target_artifact_id' must be a non-empty string.")
    sources = list(source_artifact_ids or [])
    # 1. local structural
    structural = _structural_problems(target_artifact_id, sources, merge_kind, refresh_policy)
    if structural:
        p = structural[0]
        return _err(p["code"], f"Contract is not well-formed: {p['code']}.", **{k: v for k, v in p.items() if k != "code"})
    # 2. present-bar (same as validate) — every source + target
    present = await asyncio.to_thread(_resolve_present, sources + [target_artifact_id])
    if present:
        p = present[0]
        return _err(p["code"], f"Referenced artifact failed the present-bar: {p['code']}.", artifactId=p.get("artifactId"))
    # 3. optional work unit must exist
    if work_unit_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
            return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    # 4. atomic write (only after ALL checks pass)
    contract_id = f"mc-{uuid.uuid4().hex[:12]}"
    await asyncio.to_thread(lambda: work_units_registry().insert_contract(
        contract_id, target=target_artifact_id, sources=sources, merge_kind=merge_kind,
        refresh_policy=refresh_policy, work_unit_id=work_unit_id, now=int(time.time())))
    return {"success": True, "data": {"contractId": contract_id, "target": target_artifact_id,
                                      "sources": sources, "mergeKind": merge_kind,
                                      "refreshPolicy": refresh_policy}}


async def validate_merge_contract(*, contract_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if contract_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_contract(contract_id)) is None:
            return _err("contract_not_found", f"No merge contract {contract_id!r}.")
    data = await asyncio.to_thread(lambda: _validate_graph(work_units_registry()))
    if contract_id is not None and data["ok"]:
        # single-contract view: still report the graph order + whether this one is in it
        data = {**data, "contractId": contract_id}
    return {"success": True, "data": data}


async def list_work_units_tool(*, work_unit_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    def _build() -> list[dict[str, Any]]:
        reg = work_units_registry()
        rows = [reg.get_work_unit(work_unit_id)] if work_unit_id else reg.list_work_units()
        rows = [r for r in rows if r is not None]
        out = []
        for r in rows:
            out.append({"workUnitId": r.work_unit_id, "label": r.label, "role": r.role,
                        "metadata": (json.loads(r.metadata) if r.metadata else None),
                        "createdAt": r.created_at,
                        "artifacts": [{"artifactId": a, "relation": rel} for a, rel in reg.artifacts_for(r.work_unit_id)],
                        "contracts": reg.contracts_for(r.work_unit_id)})
        return out
    return {"success": True, "data": {"workUnits": await asyncio.to_thread(_build)}}
```

- [ ] **Step 4: Run → PASS.** Then run the FULL `test_work_units.py`: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -q` → all green.
- [ ] **Step 5: Commit** `feat(p7): 5 async tool functions — register/link/record/validate/list (atomic, fail-closed)`

---

## Task 7: Wire the 5 tools into server.py + targeting.py

**Files:** Modify `mcp_server/src/rook/server.py`, `mcp_server/src/rook/targeting.py`; Test `mcp_server/tests/test_work_units_tools.py`

- [ ] **Step 1: Add the import** in `server.py` next to `from . import artifacts` (grep `^from \. import artifacts` / `import artifacts`): add `from . import work_units`.

- [ ] **Step 2: Add 5 `Tool(...)` decls** in `server.py` immediately after the `rhino_artifact_deregister` decl (~l.2881, before `rhino_ping`):

```python
        Tool(
            name="rhino_work_unit_register",
            description="Register a coordinator Work Unit (an assignment: role/constraints/expected "
                        "output). Coordinator-plane intent; no Rhino. Returns its workUnitId.",
            inputSchema={"type": "object", "properties": {
                "label": {"type": "string"}, "role": {"type": "string"},
                "metadata": {"type": "object"}, "workUnitId": {"type": "string"}},
                "required": ["label"]},
        ),
        Tool(
            name="rhino_work_unit_link_artifact",
            description="Link a registered P6 artifact to a Work Unit as produced/consumed "
                        "(provenance). Requires the artifact be REGISTERED (present not required).",
            inputSchema={"type": "object", "properties": {
                "workUnitId": {"type": "string"}, "artifactId": {"type": "string"},
                "relation": {"type": "string", "enum": ["produced", "consumed"]}},
                "required": ["workUnitId", "artifactId", "relation"]},
        ),
        Tool(
            name="rhino_merge_contract_record",
            description="Record fan-in INTENT: a merge contract (sources -> target, declared "
                        "strategy). Records only; executes nothing. All referenced artifacts must be "
                        "registered + present in P6.",
            inputSchema={"type": "object", "properties": {
                "targetArtifactId": {"type": "string"},
                "sourceArtifactIds": {"type": "array", "items": {"type": "string"}},
                "mergeKind": {"type": "string",
                              "enum": ["worksession", "import", "linked_block", "reference", "block", "report"]},
                "refreshPolicy": {"type": "string", "enum": ["refresh_after_save", "refresh_on_demand"]},
                "workUnitId": {"type": "string"}},
                "required": ["targetArtifactId", "sourceArtifactIds", "mergeKind", "refreshPolicy"]},
        ),
        Tool(
            name="rhino_merge_contract_validate",
            description="Validate merge contracts (well-formed + every artifact registered+present + "
                        "acyclic) and return the topological CONTRACT recompose order. Pure / on-demand; "
                        "no execution. Omit contractId to validate the whole graph.",
            inputSchema={"type": "object", "properties": {"contractId": {"type": "string"}}},
        ),
        Tool(
            name="rhino_work_units",
            description="List Work Units with their linked artifacts AND merge contracts "
                        "(what fan-in intent belongs to each assignment). Optional workUnitId.",
            inputSchema={"type": "object", "properties": {"workUnitId": {"type": "string"}}},
        ),
```

- [ ] **Step 3: Add 5 dispatch `case` arms** in `server.py` immediately after the `case "rhino_artifact_deregister":` block (~l.12884):

```python
        case "rhino_work_unit_register":
            result = await work_units.register_work_unit_tool(
                label=arguments.get("label"), role=arguments.get("role"),
                metadata=arguments.get("metadata"), work_unit_id=arguments.get("workUnitId"))

        case "rhino_work_unit_link_artifact":
            result = await work_units.link_artifact_tool(
                work_unit_id=arguments.get("workUnitId"), artifact_id=arguments.get("artifactId"),
                relation=arguments.get("relation"))

        case "rhino_merge_contract_record":
            result = await work_units.record_merge_contract(
                target_artifact_id=arguments.get("targetArtifactId"),
                source_artifact_ids=arguments.get("sourceArtifactIds"),
                merge_kind=arguments.get("mergeKind"), refresh_policy=arguments.get("refreshPolicy"),
                work_unit_id=arguments.get("workUnitId"))

        case "rhino_merge_contract_validate":
            result = await work_units.validate_merge_contract(contract_id=arguments.get("contractId"))

        case "rhino_work_units":
            result = await work_units.list_work_units_tool(work_unit_id=arguments.get("workUnitId"))
```

- [ ] **Step 4: Add the 5 names to `targeting.py`** — into `_ALL_KNOWN_TOOLS` (l.148 block) AND `_META_TOOLS` (l.546 block), each as a new line (mirroring `"rhino_artifacts",`):

```python
    "rhino_work_unit_register",
    "rhino_work_unit_link_artifact",
    "rhino_merge_contract_record",
    "rhino_merge_contract_validate",
    "rhino_work_units",
```

- [ ] **Step 5: Write the dispatch + classification test** (`mcp_server/tests/test_work_units_tools.py`):

```python
from __future__ import annotations
import asyncio
import json
from rook import server, work_units, artifacts, targeting


def test_p7_tools_are_meta_no_rhino():
    for name in ("rhino_work_unit_register", "rhino_work_unit_link_artifact",
                 "rhino_merge_contract_record", "rhino_merge_contract_validate", "rhino_work_units"):
        assert name in targeting._ALL_KNOWN_TOOLS
        pol = targeting.policy_for_tool(name)
        assert pol.requires_rhino is False   # non-routed, works at 0/1/many Rhinos


def test_call_tool_dispatches_register(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()
    out = asyncio.run(server.call_tool("rhino_work_unit_register", {"label": "X"}))
    from rook.tool_result import parse_call_tool_data
    data = parse_call_tool_data(out)
    assert data["workUnitId"].startswith("wu-")
    work_units._reset_work_units_registry_singleton()
```

`policy_for_tool(name).requires_rhino` is the established admission accessor (P3); `_META_TOOLS` get `RhinoToolPolicy(False, "meta")` at `targeting.py:700`, so the P7 tools resolve to `requires_rhino is False`.

- [ ] **Step 6: Run** `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py -q` → PASS. Then `mcp_server/.venv/Scripts/python.exe -c "import rook.server; print('import ok')"`.
- [ ] **Step 7: Commit** (restore knowledge/ first) `feat(p7): wire 5 merge-contract tools into server + targeting (meta, no Rhino)`

---

## Task 8: Baseline parity + finish

- [ ] **Step 1: Full non-live gate + knowledge hygiene:**

```bash
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no \
  2>&1 | grep -E "^(FAILED|ERROR)" | sort > /tmp/p7_fails.txt
git checkout -- knowledge/ ; rm -rf knowledge/selectors
```

- [ ] **Step 2: Prove baseline parity vs `main`** — capture `main`'s named failures the same way and `comm -3` both directions; the only delta must be the **new** P7 tests added to *passed* (failed/error sets identical to `main`, currently **64 failed / 41 errors**). The new `test_work_units*.py` must contribute zero failures/errors.

```bash
comm -23 /tmp/p7_fails.txt /tmp/main_fails.txt   # only-in-branch: MUST be empty
comm -13 /tmp/p7_fails.txt /tmp/main_fails.txt   # only-in-main: MUST be empty
```

- [ ] **Step 3: Finish** — `superpowers:finishing-a-development-branch` → push + PR. PR body: coordinator-plane registry (P6 untouched, reference-only invariant); 5 tables / hyperedge contracts; present-bar at record + re-check at validate; deterministic `contractOrder`; opaque strategies (no execution); Rhino-independent (unit + pure-integration coverage; live e2e optional). **User pulls the merge trigger.**

---

## Task 9 (OPTIONAL — deferrable): end-to-end live smoke

**Adds nothing to P7 logic coverage** (P7 never touches Rhino); it proves the P4→P6→P7 chain. Include only if end-to-end confidence is wanted; otherwise skip without loss.

**Files:** Create `mcp_server/tools/p7_merge_contract_live_harness.py`; Modify `scripts/run_rhino_runtime_harness.py` (`--smoke p7-merge-contract` choice + dispatch, mirroring the p6 entry).

- [ ] **Step 1:** Mirror `p6_artifact_perception_live_harness.py`: launch a disposable owned Workbench, create + `SaveAs` two real source `.3dm` + one master `.3dm`, register all three in P6 via `rhino_artifact_register`, `rhino_work_unit_register` + `rhino_work_unit_link_artifact` (the two sources `produced`, master `consumed`), `rhino_merge_contract_record` (2 sources → master, `linked_block`, `refresh_after_save`) → assert `success`; `rhino_merge_contract_validate` → `ok` + `contractOrder == [that contract]`; `rhino_artifact_deregister` one source → re-`validate` → `ok:false` with `artifact_not_registered`. Use the `tool_result` parser; isolated throwaway dbs (repoint P6 + P7 db paths to the smoke temp dir) so nothing touches real registries.
- [ ] **Step 2:** Add the `--smoke p7-merge-contract` arm; run `scripts/run_rhino_runtime_harness.py --smoke p7-merge-contract --readiness-timeout 90`; READ the manifest — `success: true`, smoke stdout `P7 live smoke: N/N PASS`.
- [ ] **Step 3: Commit** `test(p7): optional end-to-end live smoke (workbench -> save -> P6 -> P7 record+validate)`

---

## Notes for the implementer

- **`knowledge/` hygiene before every commit:** if `git status` shows `knowledge/` changes (importing `rook.server` dirties `knowledge/contextual_mab.pkl` + `knowledge/gh/component_observations.json`), `git checkout -- knowledge/ && rm -rf knowledge/selectors`.
- **P7 → P6 is reference-only.** `work_units.py` reads P6 via `_artifacts.artifact_registry().get(...)`; it MUST NEVER write `artifacts.db`. There is no FK across the db files — `artifact_id`s are validated at record/validate time only.
- **Two bars, by intent:** a provenance *link* needs only `_is_registered` (historical); a merge *reference* (record/validate) needs `_resolve_present` (present). Don't conflate them.
- **`record` is atomic:** every check runs before `insert_contract`; on any problem return `_err` and never open the transaction.
- **Determinism:** `contractOrder` uses `nx.lexicographical_topological_sort(g, key=order_key)` with `order_key=(created_at, contract_id)` — never the unordered `nx.topological_sort` (flaky).
- **Rhino-independence:** Tasks 1–8 need no Rhino. Tests use a real P6 `ArtifactRegistry` over a temp `artifacts.db` + real temp files; repoint `artifacts.resolve_artifact_db_path` / `work_units.resolve_work_units_db_path` and reset the singletons (per the test helpers).
- **Non-goals:** no merge execution; no geometry into Rhino; no P6 mutation; no planned/declared artifacts; no changes to P3 routing / P5 registry / P6 perception / P4 launch.
