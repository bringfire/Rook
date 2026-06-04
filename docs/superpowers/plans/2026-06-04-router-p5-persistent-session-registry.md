# P5 — Persistent Owned-Session Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make P4's in-process owned-Workbench set durable + cross-process via a SQLite ownership ledger, with adopt-on-restart reclaim, all governed by one total lifecycle state machine.

**Architecture:** A pure transition function `decide(observation) -> Decision` (the spec's §8.3 machine) is the single source of truth; an `OwnedSessionRegistry` (SQLite, `BEGIN IMMEDIATE`/WAL/`busy_timeout`) persists ownership; `reconcile_owned_registry` and `workbench.py`'s launch/list/close are thin transactional drivers that probe liveness, call `decide`, and apply the result. `_OWNED` becomes a derived process-handle cache holding a real `Popen` (this-session launches) or a `PidProcessHandle` (reclaimed sessions).

**Tech Stack:** Python 3, stdlib `sqlite3`, `asyncio.to_thread` for blocking primitives, `pytest`/`pytest-asyncio`. Spec: `docs/superpowers/specs/2026-06-04-p5-persistent-session-registry-design.md` (commit `97d9915`, 5 Codex rounds).

**Branch:** create `feature/router-p5-persistent-session-registry` off `main` before Task 1. Specs/plan are already on `main`.

**Hard constraints (carry through every task):**
- `decide()` is PURE — no DB, no PID probes, no `_OWNED`, no `targeting`. Drivers gather observations; `decide` returns a `Decision`; the registry/driver applies it.
- A row is deleted only when its process is confirmed dead (§8.2 L1). `closing` never rests (§8.2 L2).
- All tool results are `{"success": bool, "data": {...}}`; every failure carries `retryable` (§14).
- Blocking primitives (SQLite calls, terminate) run via `asyncio.to_thread` — never block the MCP event loop.
- `rhino_workbench_list` is a behavior change from P4: include `launching`/`closing` rows with `lifecycleStatus` + nullable `port`.
- A `force_kill_failed` launch must return the `session` handle (else reachability is docs-only).

---

## File map

| File | Responsibility |
|---|---|
| `mcp_server/src/rook/registry.py` (new) | pure `decide` machine; `RuntimeOwner`/`get_runtime_owner`/`resolve_registry_path`; `OwnedSessionRegistry` (SQLite); `reconcile_owned_registry` driver |
| `mcp_server/src/rook/workbench.py` (modify) | `PidProcessHandle`; `current_owner_scope()`; `_OWNED` derived cache; launch/list/close drivers |
| `mcp_server/tests/test_registry.py` (new) | pure-machine canonical decision table + full-product invariant sweep; registry CRUD; reconcile branches |
| `mcp_server/tests/test_workbench.py` (modify) | launch/list/close behavior incl. retained-launching, superseded, resting-return-retry |
| `mcp_server/tools/p5_registry_reclaim_live_harness.py` (new) | live reclaim smoke (real dead owner pid) |
| `scripts/run_rhino_runtime_harness.py` (modify) | add `p5-registry-reclaim` smoke choice |

**Pre-task setup (run once):**
```bash
cd /c/Users/aryan/source/repos/Rook
git rev-parse --abbrev-ref HEAD   # MUST be main
git checkout -b feature/router-p5-persistent-session-registry
```

---

## Task 1: The pure `decide()` transition machine (§8.3) + canonical decision table + invariant sweep

**Files:**
- Create: `mcp_server/src/rook/registry.py`
- Test: `mcp_server/tests/test_registry.py`

- [ ] **Step 1: Write the failing totality table test**

Create `mcp_server/tests/test_registry.py`:

```python
import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook.registry import (
    Action, Event, Observation, Decision, decide,
    LAUNCHING, BOUND, CLOSING,
)


def obs(status, event, *, port_is_null=False, rhino_alive=True,
        owner_alive=True, scope="external", rebind_available=False):
    return Observation(status=status, port_is_null=port_is_null, event=event,
                       rhino_alive=rhino_alive, owner_alive=owner_alive,
                       scope=scope, rebind_available=rebind_available)


# Executable mirror of spec §8.3 — (observation, expected Decision). NOT scraped
# from markdown: each row is hand-encoded so a wrong edge is a failing row.
TRANSITION_TABLE = [
    # bind
    (obs(LAUNCHING, Event.BIND_OK),                              Decision(Action.SET_BOUND, next_status=BOUND)),
    (obs(CLOSING,   Event.BIND_OK),                              Decision(Action.SUPERSEDED, code="workbench_launch_superseded", retryable=False)),
    (obs(LAUNCHING, Event.BIND_FAIL_DEAD),                       Decision(Action.DELETE)),
    (obs(LAUNCHING, Event.BIND_FAIL_ALIVE),                      Decision(Action.RETAIN, next_status=LAUNCHING)),
    # close
    (obs(BOUND,     Event.CLOSE_START),                          Decision(Action.SET_CLOSING, next_status=CLOSING)),
    (obs(LAUNCHING, Event.CLOSE_START),                          Decision(Action.SET_CLOSING, next_status=CLOSING)),
    (obs(CLOSING,   Event.CLOSE_START),                          Decision(Action.CLOSE_IN_PROGRESS, code="workbench_close_in_progress", retryable=True)),
    (obs(CLOSING,   Event.TERMINATE_OK),                         Decision(Action.DELETE)),
    (obs(CLOSING,   Event.TERMINATE_FAIL, port_is_null=False),   Decision(Action.REVERT_TO_RESTING, next_status=BOUND)),
    (obs(CLOSING,   Event.TERMINATE_FAIL, port_is_null=True),    Decision(Action.REVERT_TO_RESTING, next_status=LAUNCHING)),
    # reconcile — rhino dead
    (obs(BOUND,     Event.RECONCILE, rhino_alive=False),         Decision(Action.DELETE)),
    (obs(LAUNCHING, Event.RECONCILE, rhino_alive=False),         Decision(Action.DELETE)),
    (obs(CLOSING,   Event.RECONCILE, rhino_alive=False),         Decision(Action.DELETE)),
    # reconcile — rhino alive, owner alive -> leave/observe
    (obs(BOUND,     Event.RECONCILE, owner_alive=True),          Decision(Action.RETAIN)),
    # reconcile — rhino alive, owner dead, panel_locked -> no reclaim
    (obs(BOUND,     Event.RECONCILE, owner_alive=False, scope="panel_locked"), Decision(Action.NOOP)),
    # reconcile — rhino alive, owner dead, external -> reclaim
    (obs(BOUND,     Event.RECONCILE, owner_alive=False),                       Decision(Action.RECLAIM, next_status=BOUND)),
    (obs(CLOSING,   Event.RECONCILE, owner_alive=False, port_is_null=False),   Decision(Action.RECLAIM, next_status=BOUND)),
    (obs(CLOSING,   Event.RECONCILE, owner_alive=False, port_is_null=True),    Decision(Action.RECLAIM, next_status=LAUNCHING)),
    (obs(LAUNCHING, Event.RECONCILE, owner_alive=False, rebind_available=True),  Decision(Action.RECLAIM, next_status=BOUND)),
    (obs(LAUNCHING, Event.RECONCILE, owner_alive=False, rebind_available=False), Decision(Action.RECLAIM, next_status=LAUNCHING)),
]


def test_decide_matches_transition_table():
    for observation, expected in TRANSITION_TABLE:
        assert decide(observation) == expected, f"wrong edge for {observation}"


def test_closing_never_rests_L2():
    # No terminate-failure or crash-reclaim Decision may leave a row at rest in 'closing'.
    for observation, expected in TRANSITION_TABLE:
        if observation.event in (Event.TERMINATE_FAIL, Event.RECONCILE):
            assert expected.next_status != CLOSING, f"L2 violated by {observation}"


def test_decide_total_and_invariant_over_full_product():
    # Truly exhaustive: enumerate status × port_is_null × event × rhino_alive ×
    # owner_alive × scope × rebind_available (672 tuples) and assert decide is total
    # and every load-bearing invariant holds for EVERY input — not just the canonical
    # rows. A wrong edge anywhere in the space fails here.
    statuses = (LAUNCHING, BOUND, CLOSING)
    bools = (True, False)
    scopes = ("external", "panel_locked")
    resting = {LAUNCHING, BOUND}

    for status, port_null, event, rhino_alive, owner_alive, scope, rebind in itertools.product(
            statuses, bools, Event, bools, bools, scopes, bools):
        o = Observation(status=status, port_is_null=port_null, event=event,
                        rhino_alive=rhino_alive, owner_alive=owner_alive,
                        scope=scope, rebind_available=rebind)
        d = decide(o)                                   # totality: must never raise
        assert d.action in set(Action)
        assert d.next_status in (None, LAUNCHING, BOUND, CLOSING)

        # L2: a failure/crash transition never leaves a row at rest in 'closing'.
        if event in (Event.TERMINATE_FAIL, Event.RECONCILE):
            assert d.next_status != CLOSING, o

        # Reclaim is gated: only an external runtime, only a dead owner over a live rhino.
        if d.action is Action.RECLAIM:
            assert rhino_alive and not owner_alive and scope == "external", o
            assert d.next_status in resting, o

        if event is Event.RECONCILE:
            if not rhino_alive:
                assert d.action is Action.DELETE, o
            elif owner_alive:
                assert d.action is Action.RETAIN, o
            elif scope != "external":
                assert d.action is Action.NOOP, o          # panel_locked cannot reclaim
            else:
                assert d.action is Action.RECLAIM, o
```

- [ ] **Step 2: Run it to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.registry'`.

- [ ] **Step 3: Implement the pure machine**

Create `mcp_server/src/rook/registry.py`:

```python
"""P5 persistent owned-session registry.

Layer 1 (this section): the PURE lifecycle transition machine (spec §8.3).
decide() takes an Observation and returns a Decision. It performs NO I/O — no DB,
no PID probes, no _OWNED, no targeting. Drivers gather observations, call decide,
and apply the result transactionally.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

LAUNCHING = "launching"
BOUND = "bound"
CLOSING = "closing"


class Event(str, Enum):
    BIND_OK = "bind_ok"
    BIND_FAIL_DEAD = "bind_fail_dead"
    BIND_FAIL_ALIVE = "bind_fail_alive"
    CLOSE_START = "close_start"
    TERMINATE_OK = "terminate_ok"
    TERMINATE_FAIL = "terminate_fail"
    RECONCILE = "reconcile"


class Action(str, Enum):
    SET_BOUND = "set_bound"
    SUPERSEDED = "superseded"
    SET_CLOSING = "set_closing"
    CLOSE_IN_PROGRESS = "close_in_progress"
    DELETE = "delete"
    REVERT_TO_RESTING = "revert_to_resting"   # same owner: closing -> resting per port
    RECLAIM = "reclaim"                        # rewrite owner; set next_status
    RETAIN = "retain"                          # keep row + record observation
    NOOP = "noop"                              # leave untouched (panel_locked cannot reclaim)


@dataclass(frozen=True)
class Observation:
    status: str
    port_is_null: bool
    event: Event
    rhino_alive: bool = True
    owner_alive: bool = True
    scope: str = "external"
    rebind_available: bool = False


@dataclass(frozen=True)
class Decision:
    action: Action
    next_status: str | None = None
    code: str | None = None
    retryable: bool | None = None


def _resting_for_port(port_is_null: bool) -> str:
    """§8.2 L3: a closing row falls back to launching iff it never bound (port NULL)."""
    return LAUNCHING if port_is_null else BOUND


def decide(obs: Observation) -> Decision:
    """The single implementation of the §8.3 transition table. Pure."""
    e = obs.event

    if e is Event.BIND_OK:
        if obs.status == LAUNCHING:
            return Decision(Action.SET_BOUND, next_status=BOUND)
        # a concurrent close moved the row to 'closing' (or it is already bound):
        # never report success, never resurrect 'closing' (§8.5).
        return Decision(Action.SUPERSEDED, code="workbench_launch_superseded", retryable=False)

    if e is Event.BIND_FAIL_DEAD:
        return Decision(Action.DELETE)

    if e is Event.BIND_FAIL_ALIVE:
        return Decision(Action.RETAIN, next_status=LAUNCHING)

    if e is Event.CLOSE_START:
        if obs.status == CLOSING:
            return Decision(Action.CLOSE_IN_PROGRESS,
                            code="workbench_close_in_progress", retryable=True)
        return Decision(Action.SET_CLOSING, next_status=CLOSING)

    if e is Event.TERMINATE_OK:
        return Decision(Action.DELETE)

    if e is Event.TERMINATE_FAIL:
        return Decision(Action.REVERT_TO_RESTING, next_status=_resting_for_port(obs.port_is_null))

    if e is Event.RECONCILE:
        if not obs.rhino_alive:
            return Decision(Action.DELETE)
        if obs.owner_alive:
            return Decision(Action.RETAIN)            # live owner (mine or peer): leave
        if obs.scope != "external":
            return Decision(Action.NOOP)              # panel_locked cannot reclaim
        if obs.status == BOUND:
            return Decision(Action.RECLAIM, next_status=BOUND)
        if obs.status == CLOSING:
            return Decision(Action.RECLAIM, next_status=_resting_for_port(obs.port_is_null))
        return Decision(Action.RECLAIM,
                        next_status=(BOUND if obs.rebind_available else LAUNCHING))

    raise ValueError(f"unhandled event: {e}")
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/registry.py mcp_server/tests/test_registry.py
git commit -m "feat(p5): pure decide() lifecycle machine + totality table test"
```

---

## Task 2: Runtime identity (`RuntimeOwner`) + `resolve_registry_path`

**Files:**
- Modify: `mcp_server/src/rook/registry.py`
- Test: `mcp_server/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_registry.py`:

```python
from pathlib import Path
from rook.registry import (
    RuntimeOwner, get_runtime_owner, mint_runtime_owner, resolve_registry_path,
)


def test_mint_runtime_owner_has_stable_fields():
    owner = mint_runtime_owner()
    assert isinstance(owner.pid, int) and owner.pid > 0
    assert isinstance(owner.token, str) and len(owner.token) >= 8
    assert isinstance(owner.started_at, int)


def test_get_runtime_owner_is_cached(monkeypatch):
    import rook.registry as reg
    monkeypatch.setattr(reg, "_RUNTIME_OWNER", None)
    a = get_runtime_owner()
    b = get_runtime_owner()
    assert a is b   # minted once, cached for the process


def test_resolve_registry_path_under_localappdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(Path("C:/Users/x/AppData/Local")))
    p = resolve_registry_path()
    assert p.name == "owned_sessions.db"
    assert "Rook" in p.parts and "registry" in p.parts
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -k "runtime_owner or registry_path" -v`
Expected: FAIL — `ImportError: cannot import name 'RuntimeOwner'`.

- [ ] **Step 3: Implement identity + path**

Append to `mcp_server/src/rook/registry.py` (add these imports at the TOP of the file, beside the existing `from dataclasses import dataclass` / `from enum import Enum`):

```python
import os
import tempfile
import time
import uuid
from pathlib import Path
```

Then append the identity + path code to the module body:

```python
@dataclass(frozen=True)
class RuntimeOwner:
    """Stable lineage identity for this MCP runtime. Minted ONCE per process.
    The token survives nothing but disambiguates a restarted same-PID process."""
    pid: int
    token: str
    started_at: int


def mint_runtime_owner() -> RuntimeOwner:
    return RuntimeOwner(pid=int(os.getpid()), token=uuid.uuid4().hex, started_at=int(time.time()))


_RUNTIME_OWNER: RuntimeOwner | None = None


def get_runtime_owner() -> RuntimeOwner:
    """Process-global stable identity. Scope is NOT here — it is computed live
    per call by workbench.current_owner_scope() (spec §7)."""
    global _RUNTIME_OWNER
    if _RUNTIME_OWNER is None:
        _RUNTIME_OWNER = mint_runtime_owner()
    return _RUNTIME_OWNER


def resolve_registry_path() -> Path:
    """Mirror bridge.resolve_discovery_folder: %LOCALAPPDATA%\\Rook\\registry\\owned_sessions.db,
    falling back to %TEMP%\\rook\\registry\\owned_sessions.db when LOCALAPPDATA is absent."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "Rook" / "registry"
    else:
        root = Path(tempfile.gettempdir()) / "rook" / "registry"
    return root / "owned_sessions.db"
```

(`resolve_registry_path` computes the path directly from `LOCALAPPDATA` — it deliberately does NOT import from `bridge`, to keep `registry.py` decoupled.)

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/registry.py mcp_server/tests/test_registry.py
git commit -m "feat(p5): RuntimeOwner stable identity + resolve_registry_path"
```

---

## Task 3: `OwnedSessionRegistry` — connection, schema, ephemeral version-wipe

**Files:**
- Modify: `mcp_server/src/rook/registry.py`
- Test: `mcp_server/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_registry.py`:

```python
from rook.registry import OwnedSessionRegistry, REGISTRY_VERSION


def _reg(tmp_path):
    return OwnedSessionRegistry(tmp_path / "owned.db")


def test_schema_created_and_empty(tmp_path):
    r = _reg(tmp_path)
    try:
        assert r.snapshot_all() == []
        assert r.get("rhino-1") is None
    finally:
        r.close()


def test_version_mismatch_wipes(tmp_path):
    r = _reg(tmp_path)
    r.insert_launching("rhino-5", 5, _owner(), "external", 1000)
    r.close()

    # Re-open with a bumped stored version -> table wiped.
    import sqlite3
    conn = sqlite3.connect(tmp_path / "owned.db")
    conn.execute("UPDATE meta SET value='0.0.0-old' WHERE key='registry_version';")
    conn.commit()
    conn.close()

    r2 = _reg(tmp_path)
    try:
        assert r2.get("rhino-5") is None    # wiped because stored version != REGISTRY_VERSION
    finally:
        r2.close()


def _owner(pid=4242, token="tok-a", started_at=900):
    return RuntimeOwner(pid=pid, token=token, started_at=started_at)
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -k "schema or version_mismatch" -v`
Expected: FAIL — `ImportError: cannot import name 'OwnedSessionRegistry'`.

- [ ] **Step 3: Implement connection + schema**

Append to `mcp_server/src/rook/registry.py`:

```python
import sqlite3
import threading
from typing import Any

REGISTRY_VERSION = "p5.1"


@dataclass(frozen=True)
class OwnedRow:
    session_id: str
    rhino_pid: int
    port: int | None
    status: str
    owner_pid: int
    owner_token: str
    owner_started_at: int
    owner_scope: str
    launched_at: int
    # Non-authoritative document snapshot — the reserved P6 seam (spec §2/§6).
    # P5 has no writer, so these stay NULL; they exist so P6 needs no migration.
    last_document_path: str | None
    last_document_serial_number: int | None
    last_document_name: str | None
    last_port_up: int | None
    observed_at: int | None


_COLUMNS = ("session_id, rhino_pid, port, status, owner_pid, owner_token, "
            "owner_started_at, owner_scope, launched_at, last_document_path, "
            "last_document_serial_number, last_document_name, last_port_up, observed_at")


def _row(raw: sqlite3.Row | None) -> OwnedRow | None:
    if raw is None:
        return None
    return OwnedRow(*raw)


class OwnedSessionRegistry:
    """SQLite ownership ledger. Liveness is NEVER stored — only claims + last
    observations (spec §3). All load-bearing writes use BEGIN IMMEDIATE (§12)."""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # A reentrant lock serialises all connection access WITHIN this process —
        # methods run on asyncio.to_thread worker threads, so check_same_thread
        # must be False and we must serialise ourselves (sqlite3 Connection objects
        # are not safe for concurrent use). RLock so a write-txn helper can call a
        # read (get) without self-deadlock. Cross-PROCESS concurrency is handled by
        # WAL + busy_timeout, not this lock.
        self._lock = threading.RLock()
        # isolation_level=None -> we drive BEGIN IMMEDIATE / COMMIT explicitly.
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

    def _ensure_schema(self) -> None:
        c = self._conn
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
        stored = c.execute("SELECT value FROM meta WHERE key='registry_version';").fetchone()
        if stored is None or stored[0] != REGISTRY_VERSION:
            c.execute("DROP TABLE IF EXISTS owned_sessions;")
            c.execute("DELETE FROM meta;")
        c.execute("""
            CREATE TABLE IF NOT EXISTS owned_sessions (
                session_id   TEXT PRIMARY KEY,
                rhino_pid    INTEGER NOT NULL,
                port         INTEGER,
                status       TEXT NOT NULL,
                owner_pid    INTEGER NOT NULL,
                owner_token  TEXT NOT NULL,
                owner_started_at INTEGER NOT NULL,
                owner_scope  TEXT NOT NULL,
                launched_at  INTEGER NOT NULL,
                last_document_path TEXT,
                last_document_serial_number INTEGER,
                last_document_name TEXT,
                last_port_up INTEGER,
                observed_at  INTEGER);""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_owned_rhino_pid ON owned_sessions(rhino_pid);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_owned_owner_pid ON owned_sessions(owner_pid);")
        c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('registry_version', ?);",
                  (REGISTRY_VERSION,))

    # ----- reads (RLock-guarded; reentrant so write-txns can call get()) -----
    def get(self, session_id: str) -> OwnedRow | None:
        with self._lock:
            raw = self._conn.execute(
                f"SELECT {_COLUMNS} FROM owned_sessions WHERE session_id=?;", (session_id,)).fetchone()
        return _row(raw)

    def snapshot_all(self) -> list[OwnedRow]:
        with self._lock:
            rows = self._conn.execute(f"SELECT {_COLUMNS} FROM owned_sessions;").fetchall()
        return [_row(r) for r in rows]

    def list_owned(self, owner_pid: int, owner_token: str) -> list[OwnedRow]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM owned_sessions WHERE owner_pid=? AND owner_token=?;",
                (owner_pid, owner_token)).fetchall()
        return [_row(r) for r in rows]
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/registry.py mcp_server/tests/test_registry.py
git commit -m "feat(p5): OwnedSessionRegistry connection + schema + version-wipe"
```

---

## Task 4: Registry lifecycle writes — `insert_launching`, `bind`, `record_observation`

**Files:**
- Modify: `mcp_server/src/rook/registry.py`
- Test: `mcp_server/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_registry.py`:

```python
def test_insert_then_bind(tmp_path):
    r = _reg(tmp_path)
    try:
        r.insert_launching("rhino-10", 10, _owner(), "external", 1000)
        row = r.get("rhino-10")
        assert row.status == LAUNCHING and row.port is None
        assert r.bind("rhino-10", 64100) == "set_bound"
        row = r.get("rhino-10")
        assert row.status == BOUND and row.port == 64100
    finally:
        r.close()


def test_bind_supersedes_when_closing(tmp_path):
    r = _reg(tmp_path)
    try:
        r.insert_launching("rhino-11", 11, _owner(), "external", 1000)
        # simulate a concurrent close having claimed the row
        r._conn.execute("UPDATE owned_sessions SET status='closing' WHERE session_id='rhino-11';")
        assert r.bind("rhino-11", 64101) == "superseded"
        row = r.get("rhino-11")
        assert row.status == CLOSING and row.port is None   # not resurrected to bound
    finally:
        r.close()


def test_record_observation(tmp_path):
    r = _reg(tmp_path)
    try:
        r.insert_launching("rhino-12", 12, _owner(), "external", 1000)
        r.bind("rhino-12", 64102)
        r.record_observation("rhino-12", port_up=False, observed_at=2000)
        row = r.get("rhino-12")
        assert row.last_port_up == 0 and row.observed_at == 2000
    finally:
        r.close()
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -k "insert_then_bind or supersedes or record_observation" -v`
Expected: FAIL — `AttributeError: 'OwnedSessionRegistry' object has no attribute 'insert_launching'`.

- [ ] **Step 3: Implement the writes**

Append to the `OwnedSessionRegistry` class in `mcp_server/src/rook/registry.py`:

```python
    # ----- transaction helper -----
    def _immediate(self):
        """Context-manager: acquire the RLock, BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error)."""
        return _ImmediateTx(self._conn, self._lock)

    # ----- lifecycle writes -----
    def insert_launching(self, session_id: str, rhino_pid: int, owner: "RuntimeOwner",
                         scope: str, launched_at: int) -> None:
        with self._immediate():
            self._conn.execute(
                "INSERT INTO owned_sessions(session_id, rhino_pid, port, status, owner_pid, "
                "owner_token, owner_started_at, owner_scope, launched_at, last_document_path, "
                "last_document_serial_number, last_document_name, last_port_up, observed_at) "
                "VALUES(?,?,NULL,'launching',?,?,?,?,?,NULL,NULL,NULL,NULL,NULL);",
                (session_id, rhino_pid, owner.pid, owner.token, owner.started_at, scope, launched_at))

    def bind(self, session_id: str, port: int) -> str:
        """Decide BIND_OK against the in-txn status, then apply. Returns 'set_bound'
        or 'superseded'. CAS: a concurrent close (status=='closing') yields superseded."""
        with self._immediate():
            cur = self.get(session_id)
            if cur is None:
                return "superseded"
            d = decide(Observation(status=cur.status, port_is_null=cur.port is None,
                                   event=Event.BIND_OK))
            if d.action is Action.SET_BOUND:
                self._conn.execute(
                    "UPDATE owned_sessions SET port=?, status='bound' "
                    "WHERE session_id=? AND status='launching';", (port, session_id))
                return "set_bound"
            return "superseded"

    def record_observation(self, session_id: str, port_up: bool | None, observed_at: int) -> None:
        with self._immediate():
            self._conn.execute(
                "UPDATE owned_sessions SET last_port_up=?, observed_at=? WHERE session_id=?;",
                (None if port_up is None else int(bool(port_up)), observed_at, session_id))
```

And add the transaction context manager near the top of the module body (after the imports, before the class):

```python
class _ImmediateTx:
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
            if exc_type is None:
                self._conn.execute("COMMIT;")
            else:
                self._conn.execute("ROLLBACK;")
        finally:
            self._lock.release()
        return False
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/registry.py mcp_server/tests/test_registry.py
git commit -m "feat(p5): registry insert_launching / bind (CAS) / record_observation"
```

---

## Task 5: Registry close + reclaim + reap writes

**Files:**
- Modify: `mcp_server/src/rook/registry.py`
- Test: `mcp_server/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_registry.py`:

```python
def _bound(r, session_id="rhino-20", pid=20, owner=None, port=64200):
    owner = owner or _owner()
    r.insert_launching(session_id, pid, owner, "external", 1000)
    r.bind(session_id, port)
    return owner


def test_claim_for_close_paths(tmp_path):
    r = _reg(tmp_path)
    try:
        owner = _bound(r)
        # not owned (wrong token)
        assert r.claim_for_close("rhino-20", RuntimeOwner(owner.pid, "other", 1))[0] == "not_owned"
        # absent
        assert r.claim_for_close("rhino-404", owner)[0] == "not_owned"
        # success -> closing
        result, row = r.claim_for_close("rhino-20", owner)
        assert result == "set_closing"
        assert r.get("rhino-20").status == CLOSING
        # second claim while closing -> in progress
        assert r.claim_for_close("rhino-20", owner)[0] == "close_in_progress"
    finally:
        r.close()


def test_finish_close_delete_vs_revert(tmp_path):
    r = _reg(tmp_path)
    try:
        owner = _bound(r, "rhino-21", 21, port=64201)
        r.claim_for_close("rhino-21", owner)
        # terminate ok -> delete
        r.finish_close("rhino-21", success=True)
        assert r.get("rhino-21") is None

        # bound row, claim, terminate fail -> revert to bound (port set)
        owner = _bound(r, "rhino-22", 22, port=64202)
        r.claim_for_close("rhino-22", owner)
        r.finish_close("rhino-22", success=False)
        assert r.get("rhino-22").status == BOUND

        # launching zombie, claim, terminate fail -> revert to launching (port NULL)
        r.insert_launching("rhino-23", 23, owner, "external", 1000)
        r.claim_for_close("rhino-23", owner)
        r.finish_close("rhino-23", success=False)
        assert r.get("rhino-23").status == LAUNCHING
    finally:
        r.close()


def test_reclaim_cas(tmp_path):
    r = _reg(tmp_path)
    try:
        old = RuntimeOwner(9001, "dead-tok", 1)
        new = RuntimeOwner(9002, "new-tok", 2)
        _bound(r, "rhino-24", 24, owner=old, port=64204)
        # reclaim succeeds against the observed old owner AND status
        assert r.reclaim("rhino-24", expected=old, expected_status=BOUND, new_owner=new,
                         next_status=BOUND, next_port=64204, port_up=True, observed_at=5000) is True
        row = r.get("rhino-24")
        assert row.owner_pid == 9002 and row.owner_token == "new-tok" and row.status == BOUND
        assert row.port == 64204 and row.last_port_up == 1 and row.observed_at == 5000
        # a stale expected OWNER -> CAS loses
        assert r.reclaim("rhino-24", expected=old, expected_status=BOUND, new_owner=new,
                         next_status=BOUND, next_port=64204, port_up=True, observed_at=5000) is False
        # a stale expected STATUS (owner correct, status changed) -> CAS loses, row untouched
        dead2 = RuntimeOwner(9003, "dead2", 1)
        r.insert_launching("rhino-26", 26, dead2, "external", 1000)   # status == launching
        assert r.reclaim("rhino-26", expected=dead2, expected_status=BOUND, new_owner=new,
                         next_status=BOUND, next_port=64206, port_up=True, observed_at=5000) is False
        assert r.get("rhino-26").status == LAUNCHING
    finally:
        r.close()


def test_reap_dead(tmp_path):
    r = _reg(tmp_path)
    try:
        _bound(r, "rhino-25", 25, port=64205)
        r.reap("rhino-25")
        assert r.get("rhino-25") is None
    finally:
        r.close()
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -k "claim_for_close or finish_close or reclaim_cas or reap_dead" -v`
Expected: FAIL — `AttributeError: ... 'claim_for_close'`.

- [ ] **Step 3: Implement**

Append to the `OwnedSessionRegistry` class:

```python
    def claim_for_close(self, session_id: str, owner: "RuntimeOwner") -> tuple[str, OwnedRow | None]:
        """Verify owner identity, then decide CLOSE_START against in-txn status.
        Returns ('not_owned'|'set_closing'|'close_in_progress', row|None)."""
        with self._immediate():
            cur = self.get(session_id)
            if cur is None or cur.owner_pid != owner.pid or cur.owner_token != owner.token:
                return ("not_owned", None)
            d = decide(Observation(status=cur.status, port_is_null=cur.port is None,
                                   event=Event.CLOSE_START))
            if d.action is Action.CLOSE_IN_PROGRESS:
                return ("close_in_progress", cur)
            self._conn.execute(
                "UPDATE owned_sessions SET status='closing' "
                "WHERE session_id=? AND status IN ('bound','launching');", (session_id,))
            return ("set_closing", cur)

    def finish_close(self, session_id: str, *, success: bool) -> None:
        """TERMINATE_OK -> delete; TERMINATE_FAIL -> revert to resting per port (§8.3)."""
        with self._immediate():
            cur = self.get(session_id)
            if cur is None:
                return
            event = Event.TERMINATE_OK if success else Event.TERMINATE_FAIL
            d = decide(Observation(status=cur.status, port_is_null=cur.port is None, event=event))
            if d.action is Action.DELETE:
                self._conn.execute("DELETE FROM owned_sessions WHERE session_id=?;", (session_id,))
            else:  # REVERT_TO_RESTING
                self._conn.execute(
                    "UPDATE owned_sessions SET status=? WHERE session_id=? AND status='closing';",
                    (d.next_status, session_id))

    def reclaim(self, session_id: str, *, expected: "RuntimeOwner", expected_status: str,
                new_owner: "RuntimeOwner", next_status: str, next_port: int | None,
                port_up: bool | None, observed_at: int) -> bool:
        """CAS reclaim on owner identity AND status (spec §9), in ONE transaction.
        Applies only if the row still shows the expected dead owner AND the expected
        status. The status guard matters because the Decision was computed for the
        snapshot status: without `AND status=?`, a stale-status decision could apply
        to a row whose status changed (e.g. downgrade a just-bound row to launching,
        losing its port). `next_port` carries the discovered port for a late-bind
        promotion (launching->bound) so a bound row never has a NULL port (§8.2 L3);
        for every other reclaim it is the row's unchanged port. `last_port_up`/
        `observed_at` are recorded here so a port-down reclaim still updates telemetry
        (findings 1 & 2). Returns True if committed."""
        with self._immediate():
            cur = self._conn.execute(
                "UPDATE owned_sessions SET owner_pid=?, owner_token=?, owner_started_at=?, "
                "owner_scope='external', status=?, port=?, last_port_up=?, observed_at=? "
                "WHERE session_id=? AND owner_pid=? AND owner_token=? AND status=?;",
                (new_owner.pid, new_owner.token, new_owner.started_at, next_status, next_port,
                 None if port_up is None else int(bool(port_up)), observed_at,
                 session_id, expected.pid, expected.token, expected_status))
            return cur.rowcount == 1

    def reap(self, session_id: str) -> None:
        with self._immediate():
            self._conn.execute("DELETE FROM owned_sessions WHERE session_id=?;", (session_id,))
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/registry.py mcp_server/tests/test_registry.py
git commit -m "feat(p5): registry close (claim/finish) + reclaim CAS + reap"
```

---

## Task 6: `reconcile_owned_registry` driver

**Files:**
- Modify: `mcp_server/src/rook/registry.py`
- Test: `mcp_server/tests/test_registry.py`

The driver probes liveness OUTSIDE transactions, calls `decide` per row, and applies. It is injectable (probes + rebind passed as callables) so unit tests need no real processes/Rhino. It returns the set of `OwnedRow`s now owned by `current_owner` (the caller rebuilds `_OWNED` from these).

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_registry.py`:

```python
from rook.registry import reconcile_owned_registry


def _reconcile(r, owner, scope, *, alive_pids, listening_ports=(), rebind_pids=(), rebind_port=64999):
    return reconcile_owned_registry(
        r, owner, scope,
        is_pid_alive=lambda pid: pid in alive_pids,
        is_port_listening=lambda host, port: port in listening_ports,
        rebind_probe=lambda pid: rebind_port if pid in rebind_pids else None,
        now=lambda: 5000,
    )


def test_reconcile_reaps_dead_rhino(tmp_path):
    r = _reg(tmp_path)
    try:
        me = _owner(pid=100, token="me")
        _bound(r, "rhino-30", 30, owner=me, port=64300)
        owned = _reconcile(r, me, "external", alive_pids={100})  # rhino 30 dead
        assert r.get("rhino-30") is None and owned == []
    finally:
        r.close()


def test_reconcile_reclaims_dead_owner_external(tmp_path):
    r = _reg(tmp_path)
    try:
        dead = RuntimeOwner(9001, "dead", 1)
        me = _owner(pid=100, token="me")
        _bound(r, "rhino-31", 31, owner=dead, port=64301)
        owned = _reconcile(r, me, "external", alive_pids={31})  # rhino alive, owner 9001 dead
        row = r.get("rhino-31")
        assert row.owner_pid == 100 and row.status == BOUND
        assert [o.session_id for o in owned] == ["rhino-31"]
    finally:
        r.close()


def test_reconcile_panel_locked_no_reclaim(tmp_path):
    r = _reg(tmp_path)
    try:
        dead = RuntimeOwner(9001, "dead", 1)
        me = _owner(pid=100, token="me")
        _bound(r, "rhino-32", 32, owner=dead, port=64302)
        owned = _reconcile(r, me, "panel_locked", alive_pids={32})
        assert r.get("rhino-32").owner_pid == 9001   # untouched
        assert owned == []
    finally:
        r.close()


def test_reconcile_live_peer_no_steal(tmp_path):
    r = _reg(tmp_path)
    try:
        peer = RuntimeOwner(9001, "peer", 1)
        me = _owner(pid=100, token="me")
        _bound(r, "rhino-33", 33, owner=peer, port=64303)
        owned = _reconcile(r, me, "external", alive_pids={33, 9001})  # peer alive
        assert r.get("rhino-33").owner_pid == 9001   # not stolen
        assert owned == []
    finally:
        r.close()


def test_reconcile_port_down_still_reclaims(tmp_path):
    r = _reg(tmp_path)
    try:
        dead = RuntimeOwner(9001, "dead", 1)
        me = _owner(pid=100, token="me")
        _bound(r, "rhino-34", 34, owner=dead, port=64304)
        # rhino alive, owner dead, port NOT listening -> reclaim anyway + record port down
        owned = _reconcile(r, me, "external", alive_pids={34}, listening_ports=set())
        row = r.get("rhino-34")
        assert row.owner_pid == 100 and row.status == BOUND
        assert row.last_port_up == 0
        assert [o.session_id for o in owned] == ["rhino-34"]
    finally:
        r.close()


def test_reconcile_launching_late_bind_promotes(tmp_path):
    r = _reg(tmp_path)
    try:
        dead = RuntimeOwner(9001, "dead", 1)
        me = _owner(pid=100, token="me")
        r.insert_launching("rhino-35", 35, dead, "external", 1000)
        owned = _reconcile(r, me, "external", alive_pids={35}, rebind_pids={35}, rebind_port=64950)
        row = r.get("rhino-35")
        assert row.status == BOUND and row.port == 64950   # promoted WITH discovered port (L3)
        assert [o.session_id for o in owned] == ["rhino-35"]
    finally:
        r.close()
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -k reconcile -v`
Expected: FAIL — `ImportError: cannot import name 'reconcile_owned_registry'`.

- [ ] **Step 3: Implement the driver**

Append to `mcp_server/src/rook/registry.py` (module-level function, after the class):

```python
from typing import Callable

DEFAULT_HOST = "127.0.0.1"


def reconcile_owned_registry(
    registry: OwnedSessionRegistry,
    owner: "RuntimeOwner",
    scope: str,
    *,
    is_pid_alive: Callable[[int], bool],
    is_port_listening: Callable[[str, int], bool],
    rebind_probe: Callable[[int], int | None],
    now: Callable[[], int],
) -> list[OwnedRow]:
    """Snapshot rows, probe liveness OUTSIDE transactions, decide per row, apply
    each under its own BEGIN IMMEDIATE with a CAS recheck (spec §9). Returns the
    rows now owned by `owner` (caller rebuilds _OWNED). NEVER terminates a process.
    `rebind_probe(pid) -> port | None`: the discovered port if a launching row bound
    after its owner died (used to promote launching->bound WITH the port), else None."""
    for row in registry.snapshot_all():
        rhino_alive = is_pid_alive(row.rhino_pid)
        owner_alive = is_pid_alive(row.owner_pid)
        port_up = bool(row.port) and rhino_alive and is_port_listening(DEFAULT_HOST, row.port)
        rebind_port = None
        if row.status == LAUNCHING and rhino_alive and not owner_alive and scope == "external":
            rebind_port = rebind_probe(row.rhino_pid)

        d = decide(Observation(status=row.status, port_is_null=row.port is None,
                               event=Event.RECONCILE, rhino_alive=rhino_alive,
                               owner_alive=owner_alive, scope=scope,
                               rebind_available=rebind_port is not None))

        if d.action is Action.DELETE:
            registry.reap(row.session_id)
        elif d.action is Action.RECLAIM:
            # A promoted launching row carries the discovered port; every other
            # reclaim keeps the row's existing port (§8.2 L3: a bound row is never NULL).
            next_port = rebind_port if (row.status == LAUNCHING and rebind_port is not None) else row.port
            registry.reclaim(row.session_id, expected=_owner_of(row), expected_status=row.status,
                             new_owner=owner, next_status=d.next_status, next_port=next_port,
                             port_up=port_up, observed_at=now())
        elif d.action is Action.RETAIN:
            registry.record_observation(row.session_id, port_up, now())
        # NOOP -> leave untouched

    return registry.list_owned(owner.pid, owner.token)


def _owner_of(row: OwnedRow) -> "RuntimeOwner":
    return RuntimeOwner(pid=row.owner_pid, token=row.owner_token, started_at=row.owner_started_at)
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_registry.py -v`
Expected: PASS (22 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/registry.py mcp_server/tests/test_registry.py
git commit -m "feat(p5): reconcile_owned_registry driver (probe-outside, CAS-apply)"
```

---

## Task 7: `PidProcessHandle` surrogate

**Files:**
- Modify: `mcp_server/src/rook/workbench.py`
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_workbench.py`:

```python
def test_pid_process_handle(monkeypatch):
    alive = {555}
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: pid in alive)
    h = workbench.PidProcessHandle(555)
    assert h.pid == 555
    assert h.poll() is None            # alive
    alive.discard(555)
    assert h.poll() == 0               # dead -> exit sentinel
    assert h.returncode == 0


def test_pid_process_handle_wait_timeout(monkeypatch):
    import subprocess
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    h = workbench.PidProcessHandle(556)
    with pytest.raises(subprocess.TimeoutExpired):
        h.wait(timeout=0.05)
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k pid_process_handle -v`
Expected: FAIL — `AttributeError: module 'rook.workbench' has no attribute 'PidProcessHandle'`.

- [ ] **Step 3: Implement**

In `mcp_server/src/rook/workbench.py`, add to the imports near the top:

```python
import subprocess
import time
```

(Confirm `subprocess` is already imported — it is, from P4. Add `time` if missing; P4 already imports `time`.) Update the existing bridge import line to also bring in the probes:

```python
from .bridge import _process_id_from_session_id, classify_session_liveness, _is_pid_alive, _is_port_listening
```

Then add the surrogate class (after the imports, before `DEFAULT_RHINO_EXE`):

```python
class PidProcessHandle:
    """A pid-backed stand-in for a subprocess.Popen lost across an MCP restart.
    Implements exactly the surface P4's close path touches: .pid/.poll/.wait/.kill
    (spec §13). Reclaimed Workbenches close as cleanly as freshly-launched ones."""

    def __init__(self, pid: int):
        self.pid = int(pid)
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if _is_pid_alive(self.pid):
            return None
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while _is_pid_alive(self.pid):
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(cmd=f"pid {self.pid}", timeout=timeout)
            time.sleep(0.05)
        self.returncode = 0
        return 0

    def kill(self) -> None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.pid), "/F"],
                           capture_output=True, text=True, check=False)
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
```

Add `import signal` to the imports if not present (P4's workbench.py does not import signal — add it).

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k pid_process_handle -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(p5): PidProcessHandle reclaim surrogate"
```

---

## Task 8: `workbench.py` wiring + `launch_owned_workbench` refactor

**Files:**
- Modify: `mcp_server/src/rook/workbench.py`
- Test: `mcp_server/tests/test_workbench.py`

This task introduces `current_owner_scope()`, the registry singleton, the per-call claim, and rewrites launch to: insert `launching` → bind off-thread → bind CAS (`set_bound`/`superseded`) → on failure reap-and-delete or retain-launching-with-session.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_workbench.py`:

```python
import rook.registry as registry


@pytest.fixture
def fresh_registry(tmp_path, monkeypatch):
    db = tmp_path / "owned.db"
    monkeypatch.setattr(workbench, "_REGISTRY", None)
    monkeypatch.setattr(registry, "resolve_registry_path", lambda: db)
    monkeypatch.setattr(registry, "_RUNTIME_OWNER",
                        registry.RuntimeOwner(pid=4242, token="me-tok", started_at=1))
    monkeypatch.setattr(workbench, "current_owner_scope", lambda: "external")
    yield
    r = workbench._REGISTRY
    if r is not None:
        r.close()


@pytest.mark.asyncio
async def test_launch_writes_bound_row_and_session(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7000))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready",
                        lambda self, *a, **k: _record(7000, port=64500))

    out = await workbench.launch_owned_workbench(readiness_timeout_seconds=5)
    assert out["success"] is True and out["data"]["session"] == "rhino-7000"
    row = workbench._registry().get("rhino-7000")
    assert row.status == registry.BOUND and row.port == 64500
    assert 7000 in workbench._OWNED


@pytest.mark.asyncio
async def test_launch_force_kill_failed_retains_launching_with_session(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7001))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid", lambda pid: [])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)  # reap fails
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready",
                        lambda self, *a, **k: (_ for _ in ()).throw(
                            DiscoveryError("boom", reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY)))

    out = await workbench.launch_owned_workbench()
    d = out["data"]
    assert out["success"] is False
    assert d["session"] == "rhino-7001"
    assert d["lifecycleStatus"] == "launching"
    assert d["port"] is None
    assert d["cleanupStatus"] == "force_kill_failed"
    assert workbench._registry().get("rhino-7001").status == registry.LAUNCHING


@pytest.mark.asyncio
async def test_launch_superseded_when_bind_loses_to_close(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7002))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def wfr_then_close(self, *a, **k):
        # a concurrent close moved the row to 'closing' before bind commits
        workbench._registry()._conn.execute(
            "UPDATE owned_sessions SET status='closing' WHERE session_id='rhino-7002';")
        return _record(7002, port=64502)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", wfr_then_close)

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "workbench_launch_superseded"
    assert out["data"]["retryable"] is False
    assert workbench._registry().get("rhino-7002").status == registry.CLOSING  # not resurrected


@pytest.mark.asyncio
async def test_launch_registry_claim_failure_reaps(monkeypatch, fresh_registry):
    # insert_launching raises after Popen -> the live Rhino must be REAPED, not orphaned (finding 1).
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7003))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    reaped = []
    monkeypatch.setattr(workbench, "force_owned_process_cleanup",
                        lambda p, d: reaped.append(p.pid) or True)

    class _BoomReg:
        def insert_launching(self, *a, **k):
            raise RuntimeError("db locked")
    monkeypatch.setattr(workbench, "_registry", lambda: _BoomReg())

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "workbench_registry_claim_failed"
    assert out["data"]["cleanupStatus"] == "forced_kill"
    assert reaped == [7003]   # the live Rhino was reaped, not orphaned


@pytest.mark.asyncio
async def test_launch_panel_locked_does_not_popen(monkeypatch, fresh_registry):
    # Panel-scope defense-in-depth (finding 2): refuse BEFORE Popen; never launch a Rhino.
    monkeypatch.setattr(workbench, "current_owner_scope", lambda: "panel_locked")
    popened = []
    monkeypatch.setattr(workbench.subprocess, "Popen",
                        lambda *a, **k: popened.append(1) or _FakeProc(1))

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "workbench_requires_external_scope"
    assert popened == []   # Popen NEVER called under panel lock
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k "writes_bound or force_kill_failed_retains or superseded or registry_claim_failure or panel_locked_does_not_popen" -v`
Expected: FAIL — `AttributeError: ... '_registry'` / `current_owner_scope`.

- [ ] **Step 3: Implement wiring + launch refactor**

In `mcp_server/src/rook/workbench.py`, add imports for the registry + targeting:

```python
from . import registry as _reg
from .registry import get_runtime_owner, reconcile_owned_registry, resolve_registry_path
from . import targeting
```

Add the scope helper, the registry singleton, and probe wiring (after `_LOCK = asyncio.Lock()`):

```python
def current_owner_scope() -> str:
    """Live panel scope — recomputed every call, NEVER cached (spec §7). The only
    place workbench imports targeting; the gate that forbids a panel agent from
    reclaiming/closing across its lock."""
    if (targeting.get_panel_target_lock() is not None
            or targeting.get_panel_target_config_error() is not None):
        return "panel_locked"
    return "external"


_REGISTRY: "_reg.OwnedSessionRegistry | None" = None


def _registry() -> "_reg.OwnedSessionRegistry":
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _reg.OwnedSessionRegistry(resolve_registry_path())
    return _REGISTRY


def _rebind_probe(pid: int) -> int | None:
    """Single discovery re-probe for a launching dead-owner row: did it bind after
    its owner died? Returns the discovered port (PID-correlated) so reconcile can
    promote launching->bound WITH the port (§8.2 L3), else None."""
    try:
        return OwnedRhinoDiscovery().read_owned_record(pid).port
    except DiscoveryError:
        return None


def _reconcile_sync(owner, scope) -> list:
    return reconcile_owned_registry(
        _registry(), owner, scope,
        is_pid_alive=_is_pid_alive,
        is_port_listening=_is_port_listening,
        rebind_probe=_rebind_probe,
        now=lambda: int(time.time()),
    )


def _rebuild_owned(owned_rows) -> None:
    """Derived-cache rebuild: ensure _OWNED has a handle for each owned live row,
    PRESERVING an existing real Popen over a surrogate (spec §9)."""
    keep = set()
    for row in owned_rows:
        keep.add(row.rhino_pid)
        if row.rhino_pid not in _OWNED:
            _OWNED[row.rhino_pid] = OwnedWorkbench(
                record=None, process=PidProcessHandle(row.rhino_pid),
                session=row.session_id, launched_at=row.launched_at)
    for pid in list(_OWNED):
        if pid not in keep:
            _OWNED.pop(pid, None)
```

Note: `OwnedWorkbench.record` may now be `None` for reclaimed rows. Confirm the dataclass allows it — change its annotation in P4's definition from `record: OwnedRhinoRecord` to `record: "OwnedRhinoRecord | None"` (no runtime effect; documents the reclaim case).

Now replace the body of `launch_owned_workbench` (keep its signature). The new body:

```python
async def launch_owned_workbench(readiness_timeout_seconds: int = 90) -> dict[str, Any]:
    timeout = _validate_timeout(readiness_timeout_seconds)
    if timeout is None:
        return _err("invalid_readiness_timeout",
                    f"readinessTimeoutSeconds must be a positive number, got "
                    f"{readiness_timeout_seconds!r}.")
    # Panel-scope defense-in-depth (finding 2): a panel-scoped runtime acquires
    # NOTHING. Check BEFORE Popen so we never even launch a Rhino we may not own.
    # (The server guard already blocks the tool pre-dispatch; this is belt-and-suspenders.)
    scope = current_owner_scope()
    if scope != "external":
        return _err("workbench_requires_external_scope",
                    "Only an external coordinator runtime may launch Workbenches.")
    exe = _resolve_rhino_exe()
    if not exe.exists():
        return _err("rhino_executable_not_found", f"Rhino executable not found: {exe}")
    try:
        process = subprocess.Popen([str(exe)])
    except OSError as exc:
        return _err("workbench_launch_failed", f"Rhino launch failed: {exc}")

    pid = int(process.pid)
    session = f"rhino-{pid}"
    owner = get_runtime_owner()
    # Durably claim the launch FIRST (first statement after Popen). insert_launching
    # can THROW (DB lock / schema build / disk error) — a CATCHABLE failure that would
    # otherwise leave a live Rhino with no row. Reap-and-report rather than orphan it
    # (finding 1). The lambda defers _registry() into the worker thread (finding 5).
    try:
        await asyncio.to_thread(
            lambda: _registry().insert_launching(session, pid, owner, scope, int(time.time())))
    except Exception as exc:
        return await _reap_unclaimable(process, pid, exc)

    discovery = OwnedRhinoDiscovery()
    started = time.monotonic()
    try:
        record = await asyncio.to_thread(
            discovery.wait_for_ready, pid, process, ping_native, timeout, 0.25)
    except DiscoveryError as exc:
        return await _handle_launch_failure(exc, process, pid, session)

    # bind CAS — a concurrent close may have superseded us. bind() can also THROW
    # (DB error) while the Rhino is already live + bound: reap it and drop the
    # stranded launching claim rather than orphan it (finding 1).
    try:
        outcome = await asyncio.to_thread(lambda: _registry().bind(session, record.port))
    except Exception as exc:
        return await _reap_unclaimable(process, pid, exc, session=session)
    if outcome == "superseded":
        return {"success": False, "data": {
            "code": "workbench_launch_superseded", "processId": pid, "retryable": False,
            "message": "Launch was superseded by a concurrent close; launch again if a "
                       "new Workbench is still wanted."}}

    async with _LOCK:
        _OWNED[pid] = OwnedWorkbench(record=record, process=process, session=session,
                                     launched_at=time.time())
    return {"success": True, "data": {
        "session": session, "processId": pid, "port": record.port, "owned": True,
        "mode": "workbench", "boundInSeconds": round(time.monotonic() - started, 2)}}


async def _reap_unclaimable(process, pid: int, exc: Exception, *, session: str | None = None) -> dict[str, Any]:
    """A live Rhino we could not durably claim (a registry failure) — reap it rather
    than orphan it (§8 / finding 1). Best-effort drop of any stranded launching row."""
    reaped = await asyncio.to_thread(force_owned_process_cleanup, process, [])
    if session is not None:
        try:
            await asyncio.to_thread(lambda: _registry().reap(session))
        except Exception:
            pass
    return {"success": False, "data": {
        "code": "workbench_registry_claim_failed",
        "message": f"Failed to record the launch in the registry: {exc}",
        "processId": pid,
        "cleanupStatus": "forced_kill" if reaped else "force_kill_failed",
        "retryable": bool(reaped)}}


async def _handle_launch_failure(exc: DiscoveryError, process, pid: int, session: str) -> dict[str, Any]:
    code = _REASON_TO_CODE.get(exc.reason, "workbench_launch_failed")
    data: dict[str, Any] = {"code": code, "message": str(exc), "processId": pid,
                            "retryable": _RETRYABLE.get(code, True)}
    if exc.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY:
        windows = describe_windows_for_pid(pid)
        if windows:
            data["blockingWindows"] = windows
            data["diagnosticConfidence"] = "window_present_no_discovery"
            data["next_action"] = (
                "RookNative never published discovery before the timeout and a startup "
                "window was open — likely a modal. The launch was cleaned up; resolve the "
                "condition (e.g., activate Rhino) and retry.")
    reaped = await asyncio.to_thread(force_owned_process_cleanup, process, [])
    if reaped:
        # confirmed dead -> drop the durable row (§8 L1)
        await asyncio.to_thread(lambda: _registry().reap(session))
        data["cleanupStatus"] = "forced_kill"
    else:
        # process alive but unkillable -> RETAIN the launching row + return a handle (§8.4)
        async with _LOCK:
            _OWNED[pid] = OwnedWorkbench(record=None, process=process, session=session,
                                        launched_at=time.time())
        data["cleanupStatus"] = "force_kill_failed"
        data["session"] = session
        data["lifecycleStatus"] = "launching"
        data["port"] = None
        data["retryable"] = True
    return {"success": False, "data": data}
```

Finally, add these codes to the `_RETRYABLE` dict in `workbench.py` (the first task that introduces them; `_err` and `_handle_launch_failure` read this map):

```python
    "workbench_requires_external_scope": False,
    "workbench_registry_claim_failed": True,
    "workbench_launch_superseded": False,
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k "writes_bound or force_kill_failed_retains or superseded or registry_claim_failure or panel_locked_does_not_popen" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(p5): registry-backed launch — scope guard, claim-failure reap, insert/bind CAS, superseded"
```

---

## Task 9: `list_owned_workbenches` refactor (behavior change: all statuses)

**Files:**
- Modify: `mcp_server/src/rook/workbench.py`
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_workbench.py`:

```python
@pytest.mark.asyncio
async def test_list_includes_launching_and_bound(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    owner = registry.get_runtime_owner()
    reg = workbench._registry()
    reg.insert_launching("rhino-7100", 7100, owner, "external", 1000)
    reg.insert_launching("rhino-7101", 7101, owner, "external", 1000)
    reg.bind("rhino-7101", 64511)

    out = await workbench.list_owned_workbenches()
    by = {w["session"]: w for w in out["data"]["workbenches"]}
    assert by["rhino-7100"]["lifecycleStatus"] == "launching" and by["rhino-7100"]["port"] is None
    assert by["rhino-7101"]["lifecycleStatus"] == "bound" and by["rhino-7101"]["port"] == 64511
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k list_includes_launching -v`
Expected: FAIL — list returns the P4 shape (no `lifecycleStatus`, bound-only).

- [ ] **Step 3: Implement**

Replace the body of `list_owned_workbenches`:

```python
async def list_owned_workbenches() -> dict[str, Any]:
    owner = get_runtime_owner()
    scope = current_owner_scope()
    owned_rows = await asyncio.to_thread(_reconcile_sync, owner, scope)
    async with _LOCK:
        _rebuild_owned(owned_rows)
    workbenches = []
    for row in owned_rows:
        inst = {"processId": row.rhino_pid, "host": DEFAULT_HOST, "port": row.port}
        workbenches.append({
            "session": row.session_id,
            "processId": row.rhino_pid,
            "port": row.port,
            "lifecycleStatus": row.status,
            "mode": "workbench",
            "launchedAt": row.launched_at,
            "lastPortUp": (None if row.last_port_up is None else bool(row.last_port_up)),
            # lifecycleStatus carries the lifecycle truth; for a port-less row
            # (launching, or a launching-derived closing) there is no listener to
            # probe, so liveness uses a NEUTRAL state, not a lifecycle word (finding 5).
            "liveness": classify_session_liveness(inst) if row.port else {
                "state": "not_bound", "pidAlive": _is_pid_alive(row.rhino_pid),
                "portListening": False, "code": None},
        })
    return {"success": True, "data": {"workbenches": workbenches}}
```

Add `DEFAULT_HOST` to the bridge import line:

```python
from .bridge import (_process_id_from_session_id, classify_session_liveness,
                     _is_pid_alive, _is_port_listening, DEFAULT_HOST)
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k list_includes_launching -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(p5): list includes launching/closing rows with lifecycleStatus + nullable port"
```

---

## Task 10: `close_owned_workbench` refactor (claim-by-update, resting-return, concurrency)

**Files:**
- Modify: `mcp_server/src/rook/workbench.py`
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_workbench.py`:

```python
@pytest.mark.asyncio
async def test_close_success_deletes_row(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    owner = registry.get_runtime_owner()
    reg = workbench._registry()
    reg.insert_launching("rhino-7200", 7200, owner, "external", 1000)
    reg.bind("rhino-7200", 64600)
    _OWNED_set(7200, "rhino-7200")
    monkeypatch.setattr(workbench, "_terminate", lambda proc, graceful: ("forced_kill", True))

    out = await workbench.close_owned_workbench("rhino-7200")
    assert out["success"] is True and out["data"]["closed"] is True
    assert reg.get("rhino-7200") is None


@pytest.mark.asyncio
async def test_close_force_kill_failed_reverts_to_resting_and_retries(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    owner = registry.get_runtime_owner()
    reg = workbench._registry()
    reg.insert_launching("rhino-7201", 7201, owner, "external", 1000)
    reg.bind("rhino-7201", 64601)
    _OWNED_set(7201, "rhino-7201")

    monkeypatch.setattr(workbench, "_terminate", lambda proc, graceful: ("force_kill_failed", True))
    out = await workbench.close_owned_workbench("rhino-7201")
    assert out["success"] is False and out["data"]["code"] == "force_kill_failed"
    assert out["data"]["retryable"] is True
    assert reg.get("rhino-7201").status == registry.BOUND   # back to RESTING, not stuck closing

    # a SECOND close re-enters Tx1 and starts another terminate (now succeeds)
    monkeypatch.setattr(workbench, "_terminate", lambda proc, graceful: ("forced_kill", True))
    out2 = await workbench.close_owned_workbench("rhino-7201")
    assert out2["success"] is True and reg.get("rhino-7201") is None


@pytest.mark.asyncio
async def test_close_not_owned(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    out = await workbench.close_owned_workbench("rhino-9999")
    assert out["success"] is False and out["data"]["code"] == "not_owned"


def _OWNED_set(pid, session):
    workbench._OWNED[pid] = workbench.OwnedWorkbench(
        record=None, process=workbench.PidProcessHandle(pid), session=session, launched_at=1.0)
```

- [ ] **Step 2: Run to confirm RED**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -k "close_success_deletes or reverts_to_resting or close_not_owned" -v`
Expected: FAIL — close still uses the P4 dict path.

- [ ] **Step 3: Implement**

Replace the body of `close_owned_workbench` (keep the `_terminate` helper from P4 unchanged):

```python
async def close_owned_workbench(session: str, graceful: bool = False) -> dict[str, Any]:
    if not isinstance(graceful, bool):
        return _err("invalid_graceful_flag", f"graceful must be a boolean, got {graceful!r}.")
    # Panel-scope defense-in-depth (same gate as launch): a panel-scoped runtime
    # closes nothing. Distinct code from not_owned (which is "no owned row for you").
    scope = current_owner_scope()
    if scope != "external":
        return _err("workbench_requires_external_scope",
                    "Only an external coordinator runtime may close Workbenches.")
    owner = get_runtime_owner()
    owned_rows = await asyncio.to_thread(_reconcile_sync, owner, scope)
    async with _LOCK:
        _rebuild_owned(owned_rows)

    pid = _process_id_from_session_id(session)
    if pid is None or pid <= 0:
        return _err("invalid_session_id", f"Not a valid session id: {session!r}")

    # Tx1: verify owner + claim-by-update to 'closing' (or in_progress / not_owned).
    result, row = await asyncio.to_thread(lambda: _registry().claim_for_close(session, owner))
    if result == "not_owned":
        return _err("not_owned",
                    f"Session {session} is not an owned Workbench of this runtime.")
    if result == "close_in_progress":
        return _err("workbench_close_in_progress",
                    f"A close of {session} is already in progress.", session=session)

    async with _LOCK:
        wb = _OWNED.get(pid)
    handle = wb.process if wb is not None else PidProcessHandle(pid)

    # terminate off the event loop
    status, discarded = await asyncio.to_thread(_terminate, handle, graceful)
    success = status in ("forced_kill", "graceful_exit", "already_exited")

    # Tx2: delete on confirmed death, else revert to RESTING (§8.3) — never rest in 'closing'.
    await asyncio.to_thread(lambda: _registry().finish_close(session, success=success))

    if not success:   # force_kill_failed
        async with _LOCK:
            _OWNED[pid] = wb or OwnedWorkbench(record=None, process=handle, session=session,
                                               launched_at=time.time())
        return _err("force_kill_failed", f"Failed to terminate owned Workbench {session}.",
                    session=session)

    async with _LOCK:
        _OWNED.pop(pid, None)
    return {"success": True, "data": {
        "session": session, "owned": True, "mode": "workbench", "closed": True,
        "cleanupStatus": status, "discardedUnsavedChanges": discarded}}
```

Add `"workbench_close_in_progress": True` to the `_RETRYABLE` dict in `workbench.py` (the launch codes `workbench_requires_external_scope` / `workbench_registry_claim_failed` / `workbench_launch_superseded` were already added in Task 8):

```python
    "workbench_close_in_progress": True,
```

- [ ] **Step 4: Run to confirm GREEN**

Run: `cd mcp_server && python -m pytest tests/test_workbench.py -v`
Expected: PASS (all workbench tests, old + new).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(p5): registry-backed close — claim-by-update, resting-return retry, concurrency guard"
```

---

## Task 11: Live smoke `p5-registry-reclaim` (real dead owner pid)

**Files:**
- Create: `mcp_server/tools/p5_registry_reclaim_live_harness.py`
- Modify: `scripts/run_rhino_runtime_harness.py`

- [ ] **Step 1: Add the harness smoke choice**

In `scripts/run_rhino_runtime_harness.py`, add to `_smoke_command` (after the `p4-workbench-lifecycle` block):

```python
    if name == "p5-registry-reclaim":
        return (
            [
                sys.executable,
                "mcp_server/tools/p5_registry_reclaim_live_harness.py",
            ],
            repo_root,
        )
```

And add `"p5-registry-reclaim"` to the `--smoke` `choices=[...]` list.

- [ ] **Step 2: Write the live harness**

Create `mcp_server/tools/p5_registry_reclaim_live_harness.py`:

```python
"""Live P5 registry-reclaim smoke.

Run via `scripts/run_rhino_runtime_harness.py --smoke p5-registry-reclaim`. The
runner launches its OWN owned Rhino. This smoke launches a SECOND owned Workbench
through the real registry-backed path, then exercises adopt-on-restart reclaim
HONESTLY: it rewrites the row's owner to a REAL DEAD pid (a throwaway process that
exited) + a stale token, then reconciles with this runtime's live identity and
asserts reclaim + close-via-surrogate. No fabricated pids.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


_ensure_import_path()

from rook import server, workbench  # noqa: E402
from rook import registry as reg    # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _text(result) -> str:
    return result[0].text if result else ""


def _json(text: str) -> dict:
    t = text.strip()
    if t.startswith("Error:"):
        t = t[len("Error:"):].strip()
    try:
        return json.loads(t)
    except Exception:
        return {}


def _real_dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
    p.wait(timeout=10)
    # give the OS a moment to release the pid object; the pid is now a dead pid
    for _ in range(20):
        if not workbench._is_pid_alive(p.pid):
            return p.pid
        time.sleep(0.05)
    return p.pid


async def main() -> int:
    runner_pid = int(os.environ["ROOK_RHINO_PROCESS_ID"])
    print(f"Runner-owned Rhino pid={runner_pid}", flush=True)

    session = None
    try:
        # 1. launch a real owned Workbench through the registry-backed path
        out = _json(_text(await server.call_tool("rhino_workbench_launch",
                                                 {"readinessTimeoutSeconds": 120})))
        session = out.get("session")
        _record("launch", out.get("owned") is True and bool(session), f"session={session}")

        registry = workbench._registry()
        row = registry.get(session)
        _record("bound_row", row is not None and row.status == "bound", f"status={row.status if row else None}")

        # 2. rewrite owner to a REAL dead pid + stale token (a dead predecessor MCP)
        dead_pid = _real_dead_pid()
        registry._conn.execute(
            "UPDATE owned_sessions SET owner_pid=?, owner_token='stale-token' WHERE session_id=?;",
            (dead_pid, session))
        _record("seed_dead_owner", workbench._is_pid_alive(dead_pid) is False,
                f"dead_owner_pid={dead_pid}")

        # 3. reconcile with THIS runtime's live identity -> reclaim
        await asyncio.to_thread(workbench._reconcile_sync, reg.get_runtime_owner(), "external")
        reclaimed = reg.get_runtime_owner()
        row = registry.get(session)
        # _reconcile_sync settles the registry; _OWNED is rebuilt by the close driver
        # at its own entry (step 4), which is what actually proves closability.
        _record("reclaimed",
                row is not None and row.owner_pid == reclaimed.pid,
                f"owner_pid={row.owner_pid if row else None}")

        # 4. close still works via the surrogate
        closed = _json(_text(await server.call_tool("rhino_workbench_close", {"session": session})))
        if closed.get("closed"):
            session = None
        _record("close_after_reclaim", closed.get("closed") is True,
                f"cleanupStatus={closed.get('cleanupStatus')}")

        # 5. a dead-Rhino row is reaped by reconcile
        registry.insert_launching("rhino-999999", 999999, reg.get_runtime_owner(), "external", 1000)
        registry.bind("rhino-999999", 65000)
        await asyncio.to_thread(workbench._reconcile_sync, reg.get_runtime_owner(), "external")
        _record("dead_rhino_reaped", registry.get("rhino-999999") is None, "reaped")
    finally:
        if session:
            await server.call_tool("rhino_workbench_close", {"session": session})

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P5 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 3: Run the live smoke** (requires a local Rhino 8)

Run: `python scripts/run_rhino_runtime_harness.py --smoke p5-registry-reclaim --readiness-timeout 120`
Expected: prints an `Artifact directory:` path; open `<dir>/manifest.json` and confirm `"success": true` and the smoke stdout shows `5/5 PASS`. (If the first run hits a transient "Rhino Plug-in Error"/Chaos-V-Ray modal, retry once.)

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tools/p5_registry_reclaim_live_harness.py scripts/run_rhino_runtime_harness.py
git commit -m "test(p5): live registry-reclaim smoke (real dead owner pid)"
```

---

## Task 12: Full regression, baseline parity, finish the branch

**Files:** none (verification + close-out)

- [ ] **Step 1: Restore test-dirtied knowledge artifacts**

```bash
git restore knowledge/contextual_mab.pkl knowledge/gh/component_observations.json 2>/dev/null || true
git status --short
```

- [ ] **Step 2: Run the P5 unit suites green**

Run: `cd mcp_server && python -m pytest tests/test_registry.py tests/test_workbench.py tests/test_session_routing.py -v`
Expected: all PASS.

- [ ] **Step 3: Baseline parity vs `main`** (curated selection, not whole-repo green)

Run on the feature branch:
```bash
cd mcp_server && python -m pytest -m "not requires_rhino" --continue-on-collection-errors --tb=no -q \
  --ignore=tests/test_phase2c_standalone.py \
  --ignore=tests/test_phase3_canvas.py \
  --ignore=tests/test_phase4_chat.py \
  --ignore=tests/test_phase5_learning.py \
  --ignore=tests/test_pattern_store.py \
  --ignore=tests/test_scene_graph_rhino.py \
  --ignore=tests/test_scene_graph_python.py 2>&1 | tail -5
```
Record `passed / failed / errors`. Check out `main`, run the identical command, and confirm `failed` and `errors` are **UNCHANGED** (only `passed` rises by the P5 additions). Return to the feature branch.

- [ ] **Step 4: Restore artifacts again if the run dirtied them**

```bash
git restore knowledge/contextual_mab.pkl knowledge/gh/component_observations.json 2>/dev/null || true
```

- [ ] **Step 5: Finish the branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Then follow `superpowers:finishing-a-development-branch` — verify tests, present the 4 options, and on the user's choice run the PR/merge flow (`gh pr create` → Codex review → `gh pr merge --squash --delete-branch`). Update `project_rhinomcp_router_plane.md` memory to record P5 COMPLETE + the merge commit.

---

## Self-review notes (author)

- **Spec coverage:** §3 ownership-not-liveness (registry stores claims only) ✓ T3–T5; §6 schema incl. `last_port_up` ✓ T3; §7 stable identity + live scope ✓ T2/T8; §8.1–8.3 machine ✓ T1; §8.4 surface reachability (session on retained launch, list all statuses) ✓ T8/T9; §8.5 superseded ✓ T1/T8; §9 reconcile probe-outside/CAS-inside ✓ T6; §10 reclaim + panel-scope ✓ T6; §11 close claim-by-update + resting-return ✓ T10; §12 BEGIN IMMEDIATE/WAL/busy_timeout/ephemeral ✓ T3–T5; §13 PidProcessHandle ✓ T7; §17 canonical decision table + full-product invariant sweep + safety tests + live smoke ✓ T1/T6/T11.
- **decide() purity:** the only callers that pass probe results are the drivers (T6/T8/T10); `decide` itself imports nothing and touches no I/O ✓.
- **Type consistency:** `OwnedRow`, `RuntimeOwner`, `Observation`, `Decision`, `Action`, `Event`, `decide`, `OwnedSessionRegistry.{insert_launching,bind,claim_for_close,finish_close,reclaim,reap,record_observation,get,list_owned,snapshot_all}`, `reconcile_owned_registry`, `workbench.{current_owner_scope,_registry,_reconcile_sync,_rebuild_owned,_rebind_available,PidProcessHandle}` are referenced consistently across tasks.
- **Cross-phase seams:** `{success,data}` + `retryable` everywhere; blocking calls via `asyncio.to_thread`; no server.py dispatch change (P4 already wired the three tools; result shapes flow through `_format_tool_result`).
