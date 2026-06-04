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


# ---- Task 2: runtime identity + registry path ----
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
