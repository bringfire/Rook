"""P5 persistent owned-session registry.

Layer 1 (this section): the PURE lifecycle transition machine (spec §8.3).
decide() takes an Observation and returns a Decision. It performs NO I/O — no DB,
no PID probes, no _OWNED, no targeting. Drivers gather observations, call decide,
and apply the result transactionally.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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
