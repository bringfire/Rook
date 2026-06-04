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
from typing import Any, Callable

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
        # Set to the stored version string when the db was written by an INCOMPATIBLE
        # registry version. Operations then fail CLOSED (structured error) instead of
        # touching/destroying rows — a schema skew must never orphan a live Rhino.
        self.schema_unsupported: str | None = None
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
        # NEVER DROP owned_sessions — dropping would erase durable ownership for LIVE
        # Rhinos (delete-only-when-confirmed-dead). Schema bootstrap is ADDITIVE or
        # FAIL-CLOSED, never destructive. Decide compatibility BEFORE touching the table:
        # a CREATE INDEX / read on a foreign-or-older schema would RAISE instead of failing
        # closed (Codex finding). So: create+read meta, branch on version AND column shape,
        # and only then create the table + indexes + stamp.
        c = self._conn
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
        stored = c.execute("SELECT value FROM meta WHERE key='registry_version';").fetchone()

        if stored is not None and stored[0] != REGISTRY_VERSION:
            # version skew -> fail closed, leave rows intact, touch owned_sessions no further.
            self.schema_unsupported = stored[0]
            return
        if stored is None:
            table_exists = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='owned_sessions';"
            ).fetchone() is not None
            if table_exists:
                # meta lost but a table exists: adopt ONLY if its shape is the P5 shape;
                # otherwise fail closed (foreign/older table) — never index/read blindly.
                cols = {row[1] for row in c.execute("PRAGMA table_info(owned_sessions);").fetchall()}
                required = {col.strip() for col in _COLUMNS.split(",")}
                if not required.issubset(cols):
                    self.schema_unsupported = "unknown"
                    return

        # Fresh db, or a current-version / compatible-shape db -> safe to create + index + stamp.
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
        if stored is None:
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

    # ----- close / reclaim / reap writes -----
    def claim_for_close(self, session_id: str, owner: "RuntimeOwner") -> "tuple[str, OwnedRow | None]":
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

    def finish_close(self, session_id: str, owner: "RuntimeOwner", *, success: bool) -> None:
        """Finish a close that THIS owner holds in 'closing'. TERMINATE_OK -> delete;
        TERMINATE_FAIL -> revert to resting per port (§8.3). Both writes guard on owner
        identity AND status='closing', so a stray/late call can never delete a live owned
        row or touch a row owned by someone else (finding 5)."""
        with self._immediate():
            cur = self._conn.execute(
                "SELECT status, port FROM owned_sessions "
                "WHERE session_id=? AND owner_pid=? AND owner_token=? AND status='closing';",
                (session_id, owner.pid, owner.token)).fetchone()
            if cur is None:
                return
            status, port = cur
            d = decide(Observation(status=status, port_is_null=port is None,
                                   event=(Event.TERMINATE_OK if success else Event.TERMINATE_FAIL)))
            guard = "WHERE session_id=? AND owner_pid=? AND owner_token=? AND status='closing'"
            args = (session_id, owner.pid, owner.token)
            if d.action is Action.DELETE:
                self._conn.execute(f"DELETE FROM owned_sessions {guard};", args)
            else:  # REVERT_TO_RESTING
                self._conn.execute(
                    f"UPDATE owned_sessions SET status=? {guard};", (d.next_status, *args))

    def reclaim(self, session_id: str, *, expected: "RuntimeOwner", expected_status: str,
                new_owner: "RuntimeOwner", next_status: str, next_port: "int | None",
                port_up: "bool | None", observed_at: int) -> bool:
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


# =====================================================================================
# Layer 4: the reconcile driver (probe outside, decide, apply under CAS). NEVER kills.
# =====================================================================================

DEFAULT_HOST = "127.0.0.1"


def reconcile_owned_registry(
    registry: OwnedSessionRegistry,
    owner: "RuntimeOwner",
    scope: str,
    *,
    is_pid_alive: Callable[[int], bool],
    is_port_listening: Callable[[str, int], bool],
    rebind_probe: Callable[[int], "int | None"],
    now: Callable[[], int],
) -> "list[OwnedRow]":
    """Snapshot rows, probe liveness OUTSIDE transactions, decide per row, apply
    each under its own BEGIN IMMEDIATE with a CAS recheck (spec §9). Returns the
    rows now owned by `owner` (caller rebuilds _OWNED). NEVER terminates a process.
    `rebind_probe(pid) -> port | None`: the discovered port if a launching row bound
    after its owner died (used to promote launching->bound WITH the port), else None."""
    for row in registry.snapshot_all():
        rhino_alive = is_pid_alive(row.rhino_pid)
        owner_alive = is_pid_alive(row.owner_pid)
        # port_up is an OBSERVATION, tri-state: None = "no port probed" (a launching row,
        # or a late-bind promotion whose new port we haven't probed) — NEVER conflate that
        # with 0 = "real port probed and down" (findings 3 & 4). 0/1 only for a real probe.
        if row.port and rhino_alive:
            port_up = is_port_listening(DEFAULT_HOST, row.port)
        else:
            port_up = None
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
