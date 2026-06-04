"""P5 persistent owned-session registry.

Layer 1 (this section): the PURE lifecycle transition machine (spec §8.3).
decide() takes an Observation and returns a Decision. It performs NO I/O — no DB,
no PID probes, no _OWNED, no targeting. Drivers gather observations, call decide,
and apply the result transactionally.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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


# =====================================================================================
# Layer 2: runtime identity (stable) and the registry file path.
# =====================================================================================


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
    falling back to %TEMP%\\rook\\registry\\owned_sessions.db when LOCALAPPDATA is absent.
    Computes the path directly from LOCALAPPDATA to keep registry.py decoupled from bridge."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "Rook" / "registry"
    else:
        root = Path(tempfile.gettempdir()) / "rook" / "registry"
    return root / "owned_sessions.db"


# =====================================================================================
# Layer 3: the SQLite ownership ledger. Liveness is NEVER stored — only claims + last
# observations (spec §3). All load-bearing writes use BEGIN IMMEDIATE (§12).
# =====================================================================================

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


def _row(raw: "sqlite3.Row | tuple | None") -> "OwnedRow | None":
    if raw is None:
        return None
    return OwnedRow(*raw)


class _ImmediateTx:
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error), holding the registry's RLock
    for the whole transaction so connection access is serialised across worker threads."""

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


class OwnedSessionRegistry:
    """SQLite ownership ledger. Liveness is NEVER stored — only claims + last
    observations (spec §3). All load-bearing writes use BEGIN IMMEDIATE (§12)."""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # A reentrant lock serialises all connection access WITHIN this process —
        # methods run on asyncio.to_thread worker threads, so check_same_thread must
        # be False and we must serialise ourselves (sqlite3 Connection objects are not
        # safe for concurrent use). RLock so a write-txn helper can call a read (get)
        # without self-deadlock. Cross-PROCESS concurrency is handled by WAL +
        # busy_timeout, not this lock.
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
    def get(self, session_id: str) -> "OwnedRow | None":
        with self._lock:
            raw = self._conn.execute(
                f"SELECT {_COLUMNS} FROM owned_sessions WHERE session_id=?;", (session_id,)).fetchone()
        return _row(raw)

    def snapshot_all(self) -> "list[OwnedRow]":
        with self._lock:
            rows = self._conn.execute(f"SELECT {_COLUMNS} FROM owned_sessions;").fetchall()
        return [_row(r) for r in rows]

    def list_owned(self, owner_pid: int, owner_token: str) -> "list[OwnedRow]":
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM owned_sessions WHERE owner_pid=? AND owner_token=?;",
                (owner_pid, owner_token)).fetchall()
        return [_row(r) for r in rows]

    # ----- transaction helper -----
    def _immediate(self) -> "_ImmediateTx":
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

    def record_observation(self, session_id: str, port_up: "bool | None", observed_at: int) -> None:
        with self._immediate():
            self._conn.execute(
                "UPDATE owned_sessions SET last_port_up=?, observed_at=? WHERE session_id=?;",
                (None if port_up is None else int(bool(port_up)), observed_at, session_id))
