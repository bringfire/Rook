# P6 Slice 1 — Durable Artifact Perception Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A durable, perception-only artifact registry — saved work products stay visible after their producing session is gone — without composing them and without reopening P5.

**Architecture:** New `artifacts.py` (an `ArtifactRegistry` over its own `artifacts.db`, mirroring P5's hardened SQLite discipline) + four meta tools. Population is explicit `register` plus a stat-gated, owned-Workbench-only observe hook fired as a post-list side effect inside `workbench.list_owned_workbenches`. Zero edits to `registry.py`.

**Tech Stack:** Python, stdlib `sqlite3` (WAL + `BEGIN IMMEDIATE` + `busy_timeout` + RLock), `asyncio.to_thread` for all blocking work, `hashlib.sha256`, `os.stat`. Spec: `docs/superpowers/specs/2026-06-04-p6-artifact-perception-design.md` (`32bbb02` on `main`).

**Branch:** `feature/router-p6-artifact-perception` off `main` (spec already pushed). **Editable install — pure-Python edits need no rebuild for pytest.** Gate: `python -m pytest mcp_server/tests -m "not requires_rhino"`.

---

## File Structure

- **Create `mcp_server/src/rook/artifacts.py`** — the whole orchestration-plane artifact layer: path/id/stat module fns, `ArtifactRow`, `ArtifactRegistry` (SQLite store), lazy singleton + fail-closed guard, and the four async tool functions (`list/register/refresh/deregister`). The registry **never infers ownership**; callers pass `source`.
- **Create `mcp_server/tests/test_artifacts.py`** — unit tests for the module.
- **Modify `mcp_server/src/rook/workbench.py`** — add `_best_effort_observe_owned_artifact(inst, session_id)` and call it as a post-list side effect in `list_owned_workbenches`. Imports `artifacts` (never the reverse).
- **Modify `mcp_server/tests/test_workbench.py`** — observe-glue tests + the `rhino_sessions`-doesn't-observe regression guard.
- **Modify `mcp_server/src/rook/targeting.py`** — add the 4 tool names to `_META_TOOLS` and `_ALL_KNOWN_TOOLS`.
- **Modify `mcp_server/src/rook/server.py`** — 4 `Tool(...)` decls + 4 dispatch `case`s.
- **Create `mcp_server/tools/p6_artifact_perception_live_harness.py`** + add a `p6-artifact-perception` choice to `scripts/run_rhino_runtime_harness.py`.
- **Untouched:** `mcp_server/src/rook/registry.py` (I6, zero P5 edits).

---

## Task 1: Path identity + stat helpers (pure module fns)

**Files:**
- Create: `mcp_server/src/rook/artifacts.py`
- Test: `mcp_server/tests/test_artifacts.py`

- [ ] **Step 1: Write the failing test**

```python
# mcp_server/tests/test_artifacts.py
import os
import sys
from pathlib import Path

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
```

- [ ] **Step 2: Run it — expect failure** (`ModuleNotFoundError: rook.artifacts`).

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_artifacts.py -q`

- [ ] **Step 3: Create `artifacts.py` with the helpers**

```python
# mcp_server/src/rook/artifacts.py
"""P6 Slice 1 — durable artifact perception (orchestration plane).

A saved work product is addressable by its normalized path, independent of any
live session. This module is a dumb store: it accepts `source` from callers and
NEVER infers ownership (spec I8). See docs/superpowers/specs/2026-06-04-p6-artifact-perception-design.md.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def normalize_path(path: str) -> str:
    """Absolute, symlink-resolved, case-folded (os.normcase) — so C:/A.3dm and
    c:/a.3dm are ONE artifact on Windows. The durable dedup identity."""
    return os.path.normcase(os.path.normpath(os.path.realpath(os.path.abspath(path))))


def artifact_id_for(norm_path: str) -> str:
    """Deterministic, collision-free stable handle = full SHA-256 hex of the
    normalized path (idempotent re-observation; UNIQUE in the schema)."""
    return hashlib.sha256(norm_path.encode("utf-8")).hexdigest()


def stat_file_state(norm_path: str) -> "tuple[str, int | None, int | None]":
    """(file_state, size_bytes, mtime). present iff os.stat succeeds; missing on
    FileNotFound/NotADirectory; unreachable on any other OSError (permission /
    unreachable drive / OneDrive flap) — NEVER assert missing on a flap (I2)."""
    try:
        st = os.stat(norm_path)
        return ("present", int(st.st_size), int(st.st_mtime))
    except (FileNotFoundError, NotADirectoryError):
        return ("missing", None, None)
    except OSError:
        return ("unreachable", None, None)
```

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/artifacts.py mcp_server/tests/test_artifacts.py
git commit -m "feat(p6): artifact path identity + stat helpers"
```

---

## Task 2: ArtifactRegistry connection + additive/fail-closed schema

**Files:**
- Modify: `mcp_server/src/rook/artifacts.py`
- Test: `mcp_server/tests/test_artifacts.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

(Add `import sqlite3` to the test file.)

- [ ] **Step 2: Run — expect failure** (`AttributeError: ArtifactRegistry`).

- [ ] **Step 3: Add the registry scaffold to `artifacts.py`** (mirrors `registry.py:166-308`, additive/fail-closed, never drops)

```python
ARTIFACT_REGISTRY_VERSION = "p6.1"

_ARTIFACT_COLUMNS = ("artifact_id, path, file_state, source, origin_session_id, "
                     "document_name, size_bytes, mtime, label, created_at, "
                     "last_verified_at, last_missing_at")


@dataclass(frozen=True)
class ArtifactRow:
    artifact_id: str
    path: str
    file_state: str            # present | missing | unreachable
    source: str                # owned_workbench | explicit
    origin_session_id: str | None
    document_name: str | None
    size_bytes: int | None
    mtime: int | None
    label: str | None
    created_at: int
    last_verified_at: int | None
    last_missing_at: int | None


def _artifact_row(raw: "sqlite3.Row | tuple | None") -> "ArtifactRow | None":
    return None if raw is None else ArtifactRow(*raw)


def resolve_artifact_db_path() -> Path:
    """%LOCALAPPDATA%/Rook/registry/artifacts.db, falling back to %TEMP%/rook/registry.
    Separate file from P5's owned_sessions.db (Approach A, zero blast radius)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = (Path(local_app_data) / "Rook" / "registry") if local_app_data \
        else (Path(tempfile.gettempdir()) / "rook" / "registry")
    return root / "artifacts.db"


class _ImmediateTx:
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error) holding the RLock — verbatim
    from registry.py:200 (duplication accepted; no shared base class in Slice 1)."""
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


class ArtifactRegistry:
    """SQLite durable-artifact store. Mark-never-auto-delete; born-present. The
    registry accepts `source` from callers and never infers ownership (I8)."""

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
        # NEVER DROP artifacts — a missing file is a tombstone, not a reason to forget
        # history (I1/I7). Additive or fail-closed, never destructive. Decide
        # compatibility BEFORE touching the table (mirror registry.py:259).
        c = self._conn
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
        stored = c.execute("SELECT value FROM meta WHERE key='artifact_registry_version';").fetchone()
        if stored is not None and stored[0] != ARTIFACT_REGISTRY_VERSION:
            self.schema_unsupported = stored[0]
            return
        table_exists = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts';").fetchone() is not None
        if table_exists:
            cols = {row[1] for row in c.execute("PRAGMA table_info(artifacts);").fetchall()}
            required = {col.strip() for col in _ARTIFACT_COLUMNS.split(",")}
            if not required.issubset(cols):
                self.schema_unsupported = "unknown"
                return
        c.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id      TEXT NOT NULL UNIQUE,
                path             TEXT PRIMARY KEY,
                file_state       TEXT NOT NULL,
                source           TEXT NOT NULL,
                origin_session_id TEXT,
                document_name    TEXT,
                size_bytes       INTEGER,
                mtime            INTEGER,
                label            TEXT,
                created_at       INTEGER NOT NULL,
                last_verified_at INTEGER,
                last_missing_at  INTEGER);""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_artifact_source ON artifacts(source);")
        if stored is None:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('artifact_registry_version', ?);",
                      (ARTIFACT_REGISTRY_VERSION,))
```

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/artifacts.py mcp_server/tests/test_artifacts.py
git commit -m "feat(p6): ArtifactRegistry connection + additive/fail-closed schema"
```

---

## Task 3: Registry CRUD — get / list_all / upsert (born-present) / set_state / delete

**Files:** Modify `artifacts.py`; Test `test_artifacts.py`.

- [ ] **Step 1: Write the failing test**

```python
def _reg(tmp_path):
    return artifacts.ArtifactRegistry(tmp_path / "artifacts.db")


def test_upsert_born_present_creates_only_when_present(tmp_path):
    reg = _reg(tmp_path)
    # new + absent → no row (born-present)
    assert reg.upsert("/p/a.3dm", source="owned_workbench", file_state="missing",
                      size=None, mtime=None, document_name=None, origin_session_id=None,
                      label=None, now=100) == "skipped_absent"
    assert reg.get(path="/p/a.3dm") is None
    # new + present → created
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
    # existing + missing → updated to missing, sets last_missing_at, ONE row
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
```

- [ ] **Step 2: Run — expect failure** (`AttributeError: upsert`).

- [ ] **Step 3: Add the CRUD methods to `ArtifactRegistry`**

```python
    # ----- reads (RLock-guarded) -----
    def get(self, *, artifact_id: str | None = None, path: str | None = None) -> "ArtifactRow | None":
        with self._lock:
            if path is not None:
                raw = self._conn.execute(
                    f"SELECT {_ARTIFACT_COLUMNS} FROM artifacts WHERE path=?;", (path,)).fetchone()
            elif artifact_id is not None:
                raw = self._conn.execute(
                    f"SELECT {_ARTIFACT_COLUMNS} FROM artifacts WHERE artifact_id=?;", (artifact_id,)).fetchone()
            else:
                return None
            return _artifact_row(raw)

    def list_all(self) -> "list[ArtifactRow]":
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_ARTIFACT_COLUMNS} FROM artifacts ORDER BY created_at, path;").fetchall()
            return [_artifact_row(r) for r in rows]

    # ----- writes (BEGIN IMMEDIATE) -----
    def upsert(self, norm_path: str, *, source: str, file_state: str, size: int | None,
               mtime: int | None, document_name: str | None, origin_session_id: str | None,
               label: str | None, now: int) -> str:
        """Born-present rule: a NEW row is created only when file_state == 'present';
        a new+absent observe is 'skipped_absent' (no phantom). An EXISTING row is
        updated (state transition); source/created_at are NOT overwritten, and
        document_name/origin/label backfill only when currently NULL."""
        with self._immediate():
            existing = self.get(path=norm_path)
            if existing is None:
                if file_state != "present":
                    return "skipped_absent"
                self._conn.execute(
                    "INSERT INTO artifacts(artifact_id, path, file_state, source, origin_session_id, "
                    "document_name, size_bytes, mtime, label, created_at, last_verified_at, last_missing_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL);",
                    (artifact_id_for(norm_path), norm_path, "present", source, origin_session_id,
                     document_name, size, mtime, label, now, now))
                return "created"
            last_missing = now if file_state == "missing" else existing.last_missing_at
            self._conn.execute(
                "UPDATE artifacts SET file_state=?, size_bytes=?, mtime=?, last_verified_at=?, "
                "last_missing_at=?, document_name=COALESCE(document_name, ?), "
                "origin_session_id=COALESCE(origin_session_id, ?), label=COALESCE(label, ?) "
                "WHERE path=?;",
                (file_state, size, mtime, now, last_missing, document_name, origin_session_id,
                 label, norm_path))
            return "updated"

    def set_state(self, norm_path: str, *, file_state: str, size: int | None,
                  mtime: int | None, now: int) -> bool:
        """Refresh: update an EXISTING row's tri-state; never creates. False if absent."""
        with self._immediate():
            existing = self.get(path=norm_path)
            if existing is None:
                return False
            last_missing = now if file_state == "missing" else existing.last_missing_at
            self._conn.execute(
                "UPDATE artifacts SET file_state=?, size_bytes=?, mtime=?, last_verified_at=?, "
                "last_missing_at=? WHERE path=?;", (file_state, size, mtime, now, last_missing, norm_path))
            return True

    def delete(self, norm_path: str) -> bool:
        """Deregister: forget the registry row. NEVER touches the file (I5)."""
        with self._immediate():
            cur = self._conn.execute("DELETE FROM artifacts WHERE path=?;", (norm_path,))
            return cur.rowcount > 0
```

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/artifacts.py mcp_server/tests/test_artifacts.py
git commit -m "feat(p6): registry CRUD with born-present upsert + tri-state set_state"
```

---

## Task 4: Lazy singleton, fail-closed guard, `_err`, projection

**Files:** Modify `artifacts.py`; Test `test_artifacts.py`.

- [ ] **Step 1: Write the failing test**

```python
import asyncio


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
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Add singleton + guard + `_err` + `_project`**

```python
_RETRYABLE = {
    "artifact_file_not_found": False,
    "artifact_not_found": False,
    "artifact_selector_conflict": False,
    "artifact_selector_required": False,
    "invalid_path": False,
    "artifact_id_collision": False,
    "artifact_registry_unavailable": True,
}


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "data": {
        "code": code, "message": message, "retryable": _RETRYABLE.get(code, True), **extra}}


_ARTIFACT_REGISTRY: "ArtifactRegistry | None" = None


def artifact_registry() -> "ArtifactRegistry":
    global _ARTIFACT_REGISTRY
    if _ARTIFACT_REGISTRY is None:
        _ARTIFACT_REGISTRY = ArtifactRegistry(resolve_artifact_db_path())
    return _ARTIFACT_REGISTRY


def _reset_artifact_registry_singleton() -> None:
    """Test-only: drop the process-global registry so a fixture can repoint the db path."""
    global _ARTIFACT_REGISTRY
    if _ARTIFACT_REGISTRY is not None:
        _ARTIFACT_REGISTRY.close()
    _ARTIFACT_REGISTRY = None


async def _artifact_registry_unusable() -> "dict[str, Any] | None":
    reg = await asyncio.to_thread(artifact_registry)
    bad = getattr(reg, "schema_unsupported", None)
    if bad is not None:
        return _err("artifact_registry_unavailable",
                    f"Artifact registry was written by an incompatible version {bad!r}; "
                    "rows are left intact. Resolve the version skew before using artifact tools.")
    return None


def _project(row: "ArtifactRow") -> dict[str, Any]:
    """Tool projection. fileExists is DERIVED here, never stored (single source of truth)."""
    return {
        "artifactId": row.artifact_id, "path": row.path, "fileState": row.file_state,
        "fileExists": (True if row.file_state == "present"
                       else False if row.file_state == "missing" else None),
        "source": row.source, "originSessionId": row.origin_session_id,
        "documentName": row.document_name, "sizeBytes": row.size_bytes, "mtime": row.mtime,
        "label": row.label, "createdAt": row.created_at,
        "lastVerifiedAt": row.last_verified_at, "lastMissingAt": row.last_missing_at,
    }
```

Add `import asyncio` to the top of `artifacts.py`.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/artifacts.py mcp_server/tests/test_artifacts.py
git commit -m "feat(p6): artifact registry singleton, fail-closed guard, envelopes"
```

---

## Task 5: Async tool functions + selector rules

**Files:** Modify `artifacts.py`; Test `test_artifacts.py`.

- [ ] **Step 1: Write the failing test** (autouse fixture isolates the db — the P5 T9 monkeypatch-LOCAL-name lesson)

```python
import pytest


@pytest.fixture(autouse=True)
def _isolated_artifact_db(tmp_path, monkeypatch):
    # Patch the artifacts-LOCAL name and manage the singleton MANUALLY, or tool fns
    # open the REAL %LOCALAPPDATA% db (the P5 from-import local-name trap).
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    yield
    artifacts._reset_artifact_registry_singleton()


def test_register_requires_existing_file(tmp_path):
    missing = str(tmp_path / "ghost.3dm")
    res = asyncio.run(artifacts.register_artifact(missing))
    assert res["success"] is False and res["data"]["code"] == "artifact_file_not_found"


def test_register_present_then_list(tmp_path):
    f = tmp_path / "site.3dm"; f.write_bytes(b"abc")
    res = asyncio.run(artifacts.register_artifact(str(f)))
    assert res["success"] is True and res["data"]["artifact"]["source"] == "explicit"
    assert res["data"]["artifact"]["fileExists"] is True
    listing = asyncio.run(artifacts.list_artifacts())
    assert len(listing["data"]["artifacts"]) == 1


def test_selector_required_and_conflict(tmp_path):
    none = asyncio.run(artifacts.refresh_artifact())
    assert none["data"]["code"] == "artifact_selector_required"
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    conflict = asyncio.run(artifacts.refresh_artifact(artifact_id="deadbeef", path=str(f)))
    assert conflict["data"]["code"] == "artifact_selector_conflict"


def test_refresh_transitions_to_missing_after_delete(tmp_path):
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    asyncio.run(artifacts.register_artifact(str(f)))
    os.remove(f)
    res = asyncio.run(artifacts.refresh_artifact(path=str(f)))
    assert res["success"] is True and res["data"]["artifact"]["fileState"] == "missing"


def test_deregister_removes_row_but_not_file(tmp_path):
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    asyncio.run(artifacts.register_artifact(str(f)))
    res = asyncio.run(artifacts.deregister_artifact(path=str(f)))
    assert res["success"] is True and res["data"]["fileUntouched"] is True
    assert f.exists()  # I5: the .3dm is never touched
    assert asyncio.run(artifacts.list_artifacts())["data"]["artifacts"] == []


def test_get_artifact_by_path_and_unknown(tmp_path):
    f = tmp_path / "a.3dm"; f.write_bytes(b"x")
    asyncio.run(artifacts.register_artifact(str(f)))
    got = asyncio.run(artifacts.get_artifact(path=str(f)))
    assert got["success"] is True and got["data"]["artifact"]["fileExists"] is True
    miss = asyncio.run(artifacts.get_artifact(path=str(tmp_path / "nope.3dm")))
    assert miss["data"]["code"] == "artifact_not_found"
```

- [ ] **Step 2: Run — expect failure** (`AttributeError: register_artifact`).

- [ ] **Step 3: Add the async tool fns + selector resolver**

```python
async def _resolve_row(artifact_id: str | None, path: str | None):
    """Selector rules (§10.1): one-of, or both-agree, → resolve a row. Returns
    (row, None) or (None, error_envelope)."""
    has_id = isinstance(artifact_id, str) and artifact_id.strip() != ""
    has_path = isinstance(path, str) and path.strip() != ""
    if not has_id and not has_path:
        return None, _err("artifact_selector_required", "Provide 'id' or 'path'.")
    norm = normalize_path(path) if has_path else None
    if has_id and has_path and artifact_id_for(norm) != artifact_id:
        return None, _err("artifact_selector_conflict", "'id' and 'path' refer to different artifacts.")
    reg = artifact_registry()
    row = await asyncio.to_thread(
        lambda: reg.get(path=norm) if norm is not None else reg.get(artifact_id=artifact_id))
    if row is None:
        return None, _err("artifact_not_found", "No registered artifact for that id/path.")
    return row, None


async def list_artifacts() -> dict[str, Any]:
    if (unusable := await _artifact_registry_unusable()) is not None:
        return unusable
    rows = await asyncio.to_thread(lambda: artifact_registry().list_all())
    return {"success": True, "data": {"artifacts": [_project(r) for r in rows]}}


async def register_artifact(path: str) -> dict[str, Any]:
    """Explicit registration = a coordinator/user ASSERTION the artifact is in
    scope. Requires the file to exist now. NEVER deletes or edits the file."""
    if (unusable := await _artifact_registry_unusable()) is not None:
        return unusable
    if not isinstance(path, str) or not path.strip():
        return _err("invalid_path", f"'path' must be a non-empty string, got {path!r}.")
    norm = normalize_path(path)
    state, size, mtime = await asyncio.to_thread(stat_file_state, norm)
    if state != "present":
        return _err("artifact_file_not_found",
                    f"No durable file at {norm!r} (state={state}); register only existing files.")
    await asyncio.to_thread(lambda: artifact_registry().upsert(
        norm, source="explicit", file_state="present", size=size, mtime=mtime,
        document_name=None, origin_session_id=None, label=None, now=int(time.time())))
    row = await asyncio.to_thread(lambda: artifact_registry().get(path=norm))
    return {"success": True, "data": {"artifact": _project(row)}}


async def refresh_artifact(artifact_id: str | None = None, path: str | None = None) -> dict[str, Any]:
    if (unusable := await _artifact_registry_unusable()) is not None:
        return unusable
    row, err = await _resolve_row(artifact_id, path)
    if err is not None:
        return err
    state, size, mtime = await asyncio.to_thread(stat_file_state, row.path)
    await asyncio.to_thread(lambda: artifact_registry().set_state(
        row.path, file_state=state, size=size, mtime=mtime, now=int(time.time())))
    updated = await asyncio.to_thread(lambda: artifact_registry().get(path=row.path))
    return {"success": True, "data": {"artifact": _project(updated)}}


async def deregister_artifact(artifact_id: str | None = None, path: str | None = None) -> dict[str, Any]:
    if (unusable := await _artifact_registry_unusable()) is not None:
        return unusable
    row, err = await _resolve_row(artifact_id, path)
    if err is not None:
        return err
    await asyncio.to_thread(lambda: artifact_registry().delete(row.path))
    return {"success": True, "data": {
        "deregistered": row.artifact_id, "path": row.path, "fileUntouched": True}}


async def get_artifact(artifact_id: str | None = None, path: str | None = None) -> dict[str, Any]:
    """Single-artifact lookup used by rhino_artifacts when given id/path."""
    if (unusable := await _artifact_registry_unusable()) is not None:
        return unusable
    row, err = await _resolve_row(artifact_id, path)
    if err is not None:
        return err
    return {"success": True, "data": {"artifact": _project(row)}}
```

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/artifacts.py mcp_server/tests/test_artifacts.py
git commit -m "feat(p6): artifact tool fns (list/register/refresh/deregister/get) + selector rules"
```

---

## Task 6: Owned-Workbench observe hook (post-list side effect)

**Files:** Modify `mcp_server/src/rook/workbench.py`; Test `mcp_server/tests/test_workbench.py`.

- [ ] **Step 1: Write the failing test** (in `test_workbench.py`; reuse its existing `fresh_registry` autouse fixture + add artifact-db isolation)

```python
# in test_workbench.py
import asyncio
from rook import artifacts, targeting, workbench


def test_observe_owned_saved_present_upserts(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()
    f = tmp_path / "wb.3dm"; f.write_bytes(b"abc")

    async def fake_md(inst):
        return {"documentPath": str(f), "documentName": "wb.3dm"}
    monkeypatch.setattr(targeting, "fetch_document_metadata", fake_md)

    asyncio.run(workbench._best_effort_observe_owned_artifact(
        {"processId": 42, "host": "127.0.0.1", "port": 1234}, "rhino-42"))
    row = artifacts.artifact_registry().get(path=artifacts.normalize_path(str(f)))
    assert row is not None and row.source == "owned_workbench" and row.file_state == "present"
    artifacts._reset_artifact_registry_singleton()


def test_observe_unsaved_makes_no_row(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()

    async def fake_md(inst):
        return {"documentName": "Untitled"}  # no documentPath
    monkeypatch.setattr(targeting, "fetch_document_metadata", fake_md)
    asyncio.run(workbench._best_effort_observe_owned_artifact(
        {"processId": 42, "host": "127.0.0.1", "port": 1234}, "rhino-42"))
    assert artifacts.artifact_registry().list_all() == []
    artifacts._reset_artifact_registry_singleton()


def test_observe_swallows_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    artifacts._reset_artifact_registry_singleton()

    async def boom(inst):
        raise RuntimeError("bridge down")
    monkeypatch.setattr(targeting, "fetch_document_metadata", boom)
    # Must NOT raise (I4).
    asyncio.run(workbench._best_effort_observe_owned_artifact(
        {"processId": 42, "host": "127.0.0.1", "port": 1234}, "rhino-42"))
    artifacts._reset_artifact_registry_singleton()
```

- [ ] **Step 2: Run — expect failure** (`AttributeError: _best_effort_observe_owned_artifact`).

- [ ] **Step 3: Add the helper + hook to `workbench.py`**

Add the import near the other `from . import` lines:
```python
from . import artifacts
```

Add the helper (place after `_rebuild_owned`):
```python
async def _best_effort_observe_owned_artifact(inst: dict[str, Any], session_id: str) -> None:
    """Stat-gated durable observe for ONE owned, live Workbench. EVERY failure
    (metadata fetch / stat / SQLite) is swallowed — perception must never fail
    listing (spec I4). source is hard-coded 'owned_workbench' because this is the
    ONLY caller and it is reached only from the owned path (I8 is structural)."""
    try:
        md = await targeting.fetch_document_metadata(inst)
        path = md.get("documentPath")
        if not isinstance(path, str) or not path.strip():
            return  # unsaved / no durable path
        norm = artifacts.normalize_path(path)
        state, size, mtime = await asyncio.to_thread(artifacts.stat_file_state, norm)
        await asyncio.to_thread(lambda: artifacts.artifact_registry().upsert(
            norm, source="owned_workbench", file_state=state, size=size, mtime=mtime,
            document_name=md.get("documentName"), origin_session_id=session_id,
            label=None, now=int(time.time())))
    except Exception:
        return
```

In `list_owned_workbenches`, immediately before `return {"success": True, "data": {"workbenches": workbenches}}` (after the `workbenches` list is fully built), add:
```python
    # Post-list side effect: durable artifact perception for owned, LIVE workbenches
    # only (I8 structural — this is the owned path). The returned list is unaffected.
    for row in owned_rows:
        if row.port:
            await _best_effort_observe_owned_artifact(
                {"processId": row.rhino_pid, "host": DEFAULT_HOST, "port": row.port}, row.session_id)
```

- [ ] **Step 4: Run tests — expect PASS.** Also run the existing P5 list test to confirm the list still returns unchanged:

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -q`

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(p6): owned-Workbench observe hook as post-list side effect"
```

---

## Task 7: Tool wiring (targeting meta-membership + server decls/dispatch) + regression guard

**Files:** Modify `targeting.py`, `server.py`; Test `test_artifacts.py` (or `test_session_tools.py`).

- [ ] **Step 1: Write the failing tests**

```python
# in test_artifacts.py
from rook import targeting, server


def test_artifact_tools_are_meta_and_known():
    for name in ("rhino_artifacts", "rhino_artifact_register",
                 "rhino_artifact_refresh", "rhino_artifact_deregister"):
        assert name in targeting._META_TOOLS
        assert name in targeting._ALL_KNOWN_TOOLS
        assert targeting.policy_for_tool(name).requires_rhino is False


def test_rhino_sessions_does_not_call_artifact_observer(monkeypatch):
    # Regression guard for the structural boundary (spec Finding 2): listing the
    # FLEET must never auto-persist artifacts.
    called = {"n": 0}
    async def spy(inst, session_id):
        called["n"] += 1
    monkeypatch.setattr(workbench, "_best_effort_observe_owned_artifact", spy)
    async def fake_list_sessions():
        return {"success": True, "data": {"sessions": []}}
    monkeypatch.setattr(server, "list_sessions", fake_list_sessions, raising=False)
    asyncio.run(server._mcp_tool_executor("rhino_sessions", {}))
    assert called["n"] == 0
```

(If `policy_for_tool` is named differently, check `targeting.py` for the public accessor used by P1's `test_session_tools.py`; reuse that exact symbol. If `rhino_sessions` dispatch needs a different stub, mirror `test_session_tools.py`'s existing approach — the assertion that matters is `called["n"] == 0`.)

- [ ] **Step 2: Run — expect failure** (tools not in `_META_TOOLS`).

- [ ] **Step 3a: Add the 4 names to `targeting.py`** — insert into `_META_TOOLS` (alphabetical, after `agent_status` / near the rhino_ entries, e.g. before `rhino_clear_active_instance`):

```python
    "rhino_artifact_deregister",
    "rhino_artifact_refresh",
    "rhino_artifact_register",
    "rhino_artifacts",
```

Add the same four names to the `_ALL_KNOWN_TOOLS` set (find it near `targeting.py:148`).

- [ ] **Step 3b: Add 4 `Tool(...)` decls to `server.py`** (after the `rhino_workbench_close` decl at ~2849):

```python
        Tool(
            name="rhino_artifacts",
            description="List durable artifacts this runtime has perceived or registered "
                        "(saved files that persist after their producing session is gone). "
                        "Optional 'id' or 'path' returns a single artifact.",
            inputSchema={"type": "object", "properties": {
                "id": {"type": "string", "description": "artifact id"},
                "path": {"type": "string", "description": "file path"}}},
        ),
        Tool(
            name="rhino_artifact_register",
            description="Register an EXISTING durable file as an artifact in scope "
                        "(a coordinator/user assertion). Records a registry row; never "
                        "deletes or edits the file.",
            inputSchema={"type": "object", "properties": {
                "path": {"type": "string", "description": "path to an existing file"}},
                "required": ["path"]},
        ),
        Tool(
            name="rhino_artifact_refresh",
            description="Re-check an artifact's file state (present/missing/unreachable). "
                        "Never touches the file. Select by 'id' or 'path'.",
            inputSchema={"type": "object", "properties": {
                "id": {"type": "string"}, "path": {"type": "string"}}},
        ),
        Tool(
            name="rhino_artifact_deregister",
            description="Forget an artifact's registry row. Does NOT delete the .3dm. "
                        "Select by 'id' or 'path'.",
            inputSchema={"type": "object", "properties": {
                "id": {"type": "string"}, "path": {"type": "string"}}},
        ),
```

- [ ] **Step 3c: Add 4 dispatch `case`s to `server.py`** (after the `rhino_workbench_close` case at ~12834). Add `from rook import artifacts` near the top imports if not present (alongside `workbench`).

```python
        case "rhino_artifacts":
            if arguments and (arguments.get("id") or arguments.get("path")):
                result = await artifacts.get_artifact(
                    artifact_id=arguments.get("id"), path=arguments.get("path"))
            else:
                result = await artifacts.list_artifacts()

        case "rhino_artifact_register":
            result = await artifacts.register_artifact(path=arguments.get("path"))

        case "rhino_artifact_refresh":
            result = await artifacts.refresh_artifact(
                artifact_id=arguments.get("id"), path=arguments.get("path"))

        case "rhino_artifact_deregister":
            result = await artifacts.deregister_artifact(
                artifact_id=arguments.get("id"), path=arguments.get("path"))
```

(`get_artifact` is defined in Task 5.)

- [ ] **Step 4: Run tests — expect PASS.** Confirm the four tools dispatch and the regression guard holds.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/src/rook/server.py mcp_server/tests/test_artifacts.py
git commit -m "feat(p6): wire artifact meta tools + rhino_sessions-no-observe regression guard"
```

---

## Task 8: Live smoke `p6-artifact-perception` (HELD — needs Rhino)

**Files:** Create `mcp_server/tools/p6_artifact_perception_live_harness.py`; Modify `scripts/run_rhino_runtime_harness.py`.

**Pattern:** mirror `mcp_server/tools/p5_registry_reclaim_live_harness.py` exactly (owned-Rhino launch, `ROOK_RHINO_PORT`/`ROOK_RHINO_PROCESS_ID` scoping, results to `manifest.json`, `--readiness-timeout 120`, retry-once on a transient plugin modal). Restore `knowledge/` + remove `knowledge/selectors/` after (the import side-effect cleanup).

- [ ] **Step 1: Write the harness** with these PASS assertions (each printed PASS/FAIL, overall `success`):
  1. Launch an owned Workbench (`workbench.launch_owned_workbench`).
  2. In that Workbench, create a box and **save** to a throwaway temp path (`document/save` to `%TEMP%/rook-p6-smoke-<n>.3dm`). **Confirm in chat before any `document_ops(new)`/save on a real doc.**
  3. `workbench.list_owned_workbenches()` (fires observe) → `artifacts.list_artifacts()` shows the row, `source=owned_workbench`, `fileState=present`. **(headline)**
  4. `workbench.close_owned_workbench(session)` → `artifacts.list_artifacts()` still shows the row, `fileState=present`. **(persists after session gone)**
  5. The runner Rhino's own (non-owned) document is **NOT** in the artifact list (I8 live).
  6. `artifacts.deregister_artifact(path=...)` → row gone, but `os.path.exists(path)` is still `True` (I5 live). Then delete the temp file.

- [ ] **Step 2: Add a `p6-artifact-perception` choice** in `scripts/run_rhino_runtime_harness.py` (mirror the `p5-registry-reclaim` wiring).

- [ ] **Step 3: Run live (requires Rhino):**

Run: `mcp_server/.venv/Scripts/python.exe scripts/run_rhino_runtime_harness.py --smoke p6-artifact-perception --readiness-timeout 120`
Expected: all 6 PASS, `success: true` in `manifest.json`. Retry once on a transient V-Ray/plugin modal.

- [ ] **Step 4: Restore knowledge artifacts and commit**

```bash
git checkout -- knowledge/ && rm -rf knowledge/selectors 2>/dev/null
git add mcp_server/tools/p6_artifact_perception_live_harness.py scripts/run_rhino_runtime_harness.py
git commit -m "test(p6): live smoke p6-artifact-perception (owned save persists, deregister keeps file)"
```

---

## Task 9: Regression, baseline parity, finish

- [ ] **Step 1: Targeted suite green**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_artifacts.py mcp_server/tests/test_workbench.py mcp_server/tests/test_session_tools.py -q`
Expected: all green.

- [ ] **Step 2: Baseline parity vs `main`** — run the blessed gate on the branch and confirm `failed`/`errors` are UNCHANGED from `main` (P6 is additive):

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q`
Expected: `passed` rises by the new artifact tests; `failed`/`errors` identical to `main` (64 / 37–41 per env). `git checkout -- knowledge/` after.

- [ ] **Step 3: Finish** — `superpowers:finishing-a-development-branch` → push + PR (Codex review), then squash-merge after approval. PR body: call out the structural owned-only boundary, the born-present rule, zero P5 blast radius, and the residual-parity numbers.

---

## Self-Review notes

- **Spec coverage:** §4 store → T2; §5 identity → T1; §6 schema → T2/T3; §7.1 observe → T6; §7.2 register → T5; §8 lifecycle/refresh/deregister → T3/T5; §10 tools + §10.1 selectors → T5/T7; §11 errors → T4/T5; §12 invariants → distributed (I1/I7 T2-3, I2 T1/T3, I4 T6, I5 T5/T8, I6 "untouched registry.py", I8 T6/T7); §13 tests → T1–T8; §14 files → all.
- **Cross-phase seams:** `_META_TOOLS`+`_ALL_KNOWN_TOOLS` (T7); `{success,data}`+`retryable` (T4); `asyncio.to_thread` (T3-6); `_format_tool_result` is reached via the existing non-Rhino dispatch branch (server.py:19359) — no change needed there.
- **Type consistency:** `upsert`/`set_state`/`get`/`delete`/`list_all` signatures are used identically in T5/T6; `_project` keys are camelCase tool surface; `source` values `owned_workbench`/`explicit` only.
- **No P5 edits:** the only P5 read is `list_owned_workbenches` iterating `owned_rows` (T6) — already in workbench.py, registry.py untouched.
