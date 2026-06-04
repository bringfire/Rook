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


# ---- Task 3: OwnedSessionRegistry connection + schema + version-wipe ----
import sqlite3
from rook.registry import OwnedSessionRegistry, REGISTRY_VERSION


def _reg(tmp_path):
    return OwnedSessionRegistry(tmp_path / "owned.db")


def _owner(pid=4242, token="tok-a", started_at=900):
    return RuntimeOwner(pid=pid, token=token, started_at=started_at)


def test_schema_created_and_empty(tmp_path):
    r = _reg(tmp_path)
    try:
        assert r.snapshot_all() == []
        assert r.get("rhino-1") is None
    finally:
        r.close()


def _raw_insert(r, session_id, pid):
    r._conn.execute(
        "INSERT INTO owned_sessions(session_id, rhino_pid, status, owner_pid, owner_token, "
        "owner_started_at, owner_scope, launched_at) "
        f"VALUES('{session_id}', {pid}, 'bound', 1, 't', 1, 'external', 1000);")


def test_version_mismatch_preserves_rows_and_marks_unsupported(tmp_path):
    # A version skew must NEVER drop ownership rows (that would orphan live Rhinos);
    # fail CLOSED instead, leaving rows intact (Codex finding 1).
    r = _reg(tmp_path)
    _raw_insert(r, "rhino-5", 5)
    assert r.get("rhino-5") is not None
    r.close()

    conn = sqlite3.connect(tmp_path / "owned.db")
    conn.execute("UPDATE meta SET value='0.0.0-old' WHERE key='registry_version';")
    conn.commit()
    conn.close()

    r2 = _reg(tmp_path)
    try:
        assert r2.schema_unsupported == "0.0.0-old"   # fail closed
        assert r2.get("rhino-5") is not None           # row PRESERVED, not dropped
    finally:
        r2.close()


def test_missing_meta_does_not_drop_rows(tmp_path):
    # A corrupted/lost meta row must not erase durable ownership (Codex finding 1).
    r = _reg(tmp_path)
    _raw_insert(r, "rhino-6", 6)
    r.close()

    conn = sqlite3.connect(tmp_path / "owned.db")
    conn.execute("DELETE FROM meta;")
    conn.commit()
    conn.close()

    r2 = _reg(tmp_path)
    try:
        assert r2.schema_unsupported is None    # re-adopts the current version
        assert r2.get("rhino-6") is not None     # row PRESERVED, not orphaned
    finally:
        r2.close()


# ---- Task 4: insert_launching / bind (CAS) / record_observation ----
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


# ---- Task 5: close (claim/finish) + reclaim CAS + reap ----
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
        r.finish_close("rhino-21", owner, success=True)
        assert r.get("rhino-21") is None

        # bound row, claim, terminate fail -> revert to bound (port set)
        owner = _bound(r, "rhino-22", 22, port=64202)
        r.claim_for_close("rhino-22", owner)
        r.finish_close("rhino-22", owner, success=False)
        assert r.get("rhino-22").status == BOUND

        # launching zombie, claim, terminate fail -> revert to launching (port NULL)
        r.insert_launching("rhino-23", 23, owner, "external", 1000)
        r.claim_for_close("rhino-23", owner)
        r.finish_close("rhino-23", owner, success=False)
        assert r.get("rhino-23").status == LAUNCHING

        # a finish_close on a NON-closing row this owner holds is a no-op (finding 5)
        owner2 = _bound(r, "rhino-27", 27, port=64207)   # status == bound, never claimed
        r.finish_close("rhino-27", owner2, success=True)
        assert r.get("rhino-27").status == BOUND          # NOT deleted
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


# ---- Task 6: reconcile_owned_registry driver ----
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
