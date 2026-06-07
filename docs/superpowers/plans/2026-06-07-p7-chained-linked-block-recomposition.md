# P7 Slice 5 — Chained Linked-Block Recomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the already-merged strict contract DAG + the per-contract linked-block executor compose across `contractOrder` (the Save→consume handoff and nested linked-block behavior) via one pure ordering helper and one live regression — no new tool, no native, no server/targeting change.

**Architecture:** Add a shared pure ordering factor `_ordered_contract_ids` (one source of truth, reused by `_validate_graph`) and a narrow pure helper `plan_linked_block_execution` (orders over the whole graph, then filters to a requested contract-id subset) in `work_units.py`. Offline unit tests in `test_work_units.py` prove ordering/gating (including the transitive omitted-dependency regression). A `requires_rhino` live harness drives `[A,B]` through the existing `rhino_merge_contract_execute` tool on one Rhino with document-switching, hard-asserting core composition via deterministic `block_def_name` and recording nested-refresh behavior.

**Tech Stack:** Python 3, pytest, networkx (already a dependency), SQLite registry (`work_units.db`), the existing P6 artifact registry and P7 merge-contract registry.

**Spec:** `docs/superpowers/specs/2026-06-07-p7-chained-linked-block-recomposition-design.md`

**Test runner:** `mcp_server/.venv/Scripts/python.exe -m pytest` (editable install — pure-Python edits need no rebuild).

---

## Setup

- [ ] **Create the feature branch off `main`**

```bash
git checkout main
git pull
git checkout -b feature/p7-chain-recomposition
```

The repo root is `C:\Users\aryan\source\repos\Rook`. The active shell is PowerShell; use `;`/`&&` chaining and `mcp_server/.venv/Scripts/python.exe` for pytest.

---

## Task 1: Factor `_ordered_contract_ids`; refactor `_validate_graph` (parity-preserving)

Extract the one topological-sort implementation so the new helper reuses it instead of growing a second DAG order.

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (add `_ordered_contract_ids` after `_contract_cycle`, ~line 561; refactor the order block inside `_validate_graph`, ~lines 788–792)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

Add to `mcp_server/tests/test_work_units.py` (the file already has `_fresh_registry(tmp_path)` and an autouse `_isolate_registries` fixture):

```python
def test_ordered_contract_ids_orders_a_chain(tmp_path):
    reg = _fresh_registry(tmp_path)
    # edge A->B iff target(A) in sources(B): target(A)=X in sources(B)=[X]
    reg.insert_contract("A", target="X", sources=["w"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=1)
    reg.insert_contract("B", target="Y", sources=["X"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=2)
    pairs = [(c.contract_id, c.target_artifact_id, reg.sources_for(c.contract_id))
             for c in reg.list_contracts()]
    order_key = {c.contract_id: (c.created_at, c.contract_id) for c in reg.list_contracts()}
    order, cycle = work_units._ordered_contract_ids(pairs, order_key)
    assert cycle is None
    assert order == ["A", "B"]
    reg.close()


def test_ordered_contract_ids_reports_cycle():
    # Built directly (insert_contract would reject a cycle): A<->B.
    pairs = [("A", "X", ["Y"]), ("B", "Y", ["X"])]
    order_key = {"A": (1, "A"), "B": (2, "B")}
    order, cycle = work_units._ordered_contract_ids(pairs, order_key)
    assert order is None
    assert cycle is not None and set(cycle) >= {"A", "B"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k ordered_contract_ids -q`
Expected: FAIL — `AttributeError: module 'rook.work_units' has no attribute '_ordered_contract_ids'`.

- [ ] **Step 3: Add `_ordered_contract_ids` and refactor `_validate_graph`**

In `mcp_server/src/rook/work_units.py`, immediately after `_contract_cycle` (the function ending ~line 561), add:

```python
def _ordered_contract_ids(pairs, order_key):
    """The ONE source of truth for strict-contract execution order. pairs: list of
    (contract_id, target_artifact_id, sources_list); order_key: cid -> (created_at, contract_id).
    Returns (order, None) on success or (None, cycle) on a cyclic graph. Reused by
    _validate_graph (whole graph) and plan_linked_block_execution (whole-graph order, then
    filtered to a requested subset)."""
    g, _, _ = _contract_graph(pairs)
    try:
        return list(nx.lexicographical_topological_sort(g, key=lambda n: order_key[n])), None
    except nx.NetworkXUnfeasible:
        return None, _contract_cycle(pairs)
```

Then, inside `_validate_graph`, replace the inline try/except order block (currently):

```python
    contract_order: list[str] | None = None
    try:
        contract_order = list(nx.lexicographical_topological_sort(g, key=lambda n: order_key[n]))
    except nx.NetworkXUnfeasible:
        problems.append({"code": "merge_cycle_detected", "cycle": _contract_cycle(pairs)})
```

with:

```python
    contract_order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:
        problems.append({"code": "merge_cycle_detected", "cycle": cycle})
```

Leave the preceding `g, _, _ = _contract_graph(pairs)` line in place — `g` is still used to build `edges` later in the function.

- [ ] **Step 4: Run the new tests + the existing `_validate_graph` parity**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -q`
Expected: PASS (new tests pass; all pre-existing `validate`/`_validate_graph` tests still pass — the refactor is output-identical).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "p7(s5): factor _ordered_contract_ids; refactor _validate_graph (parity)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `plan_linked_block_execution` — happy path + gates (minimal v1)

Add the helper with input gating and ordering over the **requested** ids. (Task 3 then proves this v1 ordering is insufficient for the transitive case and drives it to whole-graph ordering — genuine red→green for the load-bearing correctness property.)

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (add `plan_linked_block_execution` after `_validate_one`, ~line 832)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_plan_linked_block_execution_chain(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.insert_contract("A", target="X", sources=["s1", "s2"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=1)
    reg.insert_contract("B", target="M", sources=["X"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=2)
    out = work_units.plan_linked_block_execution(reg, ["A", "B"])
    assert out == {"ok": True, "plan": [
        {"contractId": "A", "targetArtifactId": "X"},
        {"contractId": "B", "targetArtifactId": "M"}]}
    reg.close()


def test_plan_rejects_unknown_contract_id(tmp_path):
    reg = _fresh_registry(tmp_path)
    out = work_units.plan_linked_block_execution(reg, ["mc-nope"])
    assert out == {"ok": False, "problems": [{"code": "contract_not_found", "contractId": "mc-nope"}]}
    reg.close()


def test_plan_rejects_unsupported_merge_kind(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.insert_contract("A", target="X", sources=["s1"], merge_kind="import",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=1)
    out = work_units.plan_linked_block_execution(reg, ["A"])
    assert out == {"ok": False, "problems": [
        {"code": "unsupported_merge_kind", "contractId": "A", "mergeKind": "import"}]}
    reg.close()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "plan_linked_block_execution_chain or plan_rejects" -q`
Expected: FAIL — `AttributeError: module 'rook.work_units' has no attribute 'plan_linked_block_execution'`.

- [ ] **Step 3: Add the minimal `plan_linked_block_execution` (v1 — orders the requested subset)**

In `mcp_server/src/rook/work_units.py`, after `_validate_one` (~line 832, before the `# ----- tool layer` marker ~line 835), add:

```python
_PLANNABLE_MERGE_KIND = "linked_block"


def plan_linked_block_execution(reg, contract_ids):
    """Pure, Rhino-free. Derive the deterministic linked-block execution plan for a requested
    subset of strict contracts. Consumes contract ids, not sessions. Does NOT execute, inspect
    Rhino, check the present-bar, or define any execution-result envelope.

    Omitted-producer policy: ALLOW. A requested contract may depend on a contract not in the
    request; ordering still holds and no problem is raised. Artifact availability is the
    executor's runtime present-bar, not a pure planner's call.

    Returns {"ok": True, "plan": [{"contractId", "targetArtifactId"}, ...]} in execution order,
    or {"ok": False, "problems": [{"code", ...}]}.
    """
    requested = list(dict.fromkeys(contract_ids))   # dedupe, preserve first-seen
    requested_set = set(requested)

    problems: list[dict[str, Any]] = []
    target_of: dict[str, str] = {}
    for cid in requested:
        ct = reg.get_contract(cid)
        if ct is None:
            problems.append({"code": "contract_not_found", "contractId": cid})
        elif ct.merge_kind != _PLANNABLE_MERGE_KIND:
            problems.append({"code": "unsupported_merge_kind", "contractId": cid,
                             "mergeKind": ct.merge_kind})
        else:
            target_of[cid] = ct.target_artifact_id
    if problems:
        return {"ok": False, "problems": problems}

    pairs = [(cid, target_of[cid], reg.sources_for(cid)) for cid in requested]
    order_key = {cid: (reg.get_contract(cid).created_at, cid) for cid in requested}
    order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:
        return {"ok": False, "problems": [{"code": "merge_cycle_detected", "cycle": cycle}]}

    plan = [{"contractId": cid, "targetArtifactId": target_of[cid]}
            for cid in order if cid in requested_set]
    return {"ok": True, "plan": plan}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "plan_linked_block_execution_chain or plan_rejects" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "p7(s5): plan_linked_block_execution — gates + subset ordering (v1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Drive ordering over the whole graph (transitive omitted-dependency regression)

The v1 helper orders a scoped subgraph, which drops transitive edges through omitted contracts and can invert order. Add the two robustness tests; the transitive one fails against v1 and forces whole-graph ordering.

**Files:**
- Modify: `mcp_server/src/rook/work_units.py` (`plan_linked_block_execution` ordering section)
- Test: `mcp_server/tests/test_work_units.py`

- [ ] **Step 1: Write the failing/guard tests**

```python
def test_plan_unrelated_contract_does_not_affect_subchain(tmp_path):
    reg = _fresh_registry(tmp_path)
    reg.insert_contract("A", target="X", sources=["s1"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=1)
    reg.insert_contract("B", target="M", sources=["X"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=2)
    # Unrelated contract D whose source 'ghost' is never produced/registered.
    reg.insert_contract("D", target="Z", sources=["ghost"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=3)
    out = work_units.plan_linked_block_execution(reg, ["A", "B"])
    assert out["ok"] is True
    assert [p["contractId"] for p in out["plan"]] == ["A", "B"]
    reg.close()


def test_plan_transitive_omitted_dependency_orders_over_full_graph(tmp_path):
    """Regression for the scoped-subgraph inverted-order bug. Full graph: A -> C -> B
    (C.sources=[target(A)], B.sources=[target(C)]). Requesting [A, B] (omitting C) must yield
    [A, B], not [B, A]. created_at is chosen so key(B) < key(A): a scoped-only subgraph over
    {A, B} has no edge and tie-breaks to [B, A]; whole-graph order then filter yields [A, B]."""
    reg = _fresh_registry(tmp_path)
    reg.insert_contract("B", target="M", sources=["Y"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=1)  # earliest
    reg.insert_contract("A", target="X", sources=["s1"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=2)
    reg.insert_contract("C", target="Y", sources=["X"], merge_kind="linked_block",
                        refresh_policy="refresh_on_demand", work_unit_id=None, now=3)
    out = work_units.plan_linked_block_execution(reg, ["A", "B"])
    assert out["ok"] is True
    assert [p["contractId"] for p in out["plan"]] == ["A", "B"]   # NOT ["B", "A"]
    # Omitting the producer C raises no problem (allow-omitted policy).
    reg.close()
```

- [ ] **Step 2: Run them — the transitive test fails against v1**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "unrelated_contract or transitive_omitted" -q`
Expected: `test_plan_unrelated_contract_does_not_affect_subchain` PASS; `test_plan_transitive_omitted_dependency_orders_over_full_graph` **FAIL** with `assert ['B', 'A'] == ['A', 'B']` — proving the scoped-subgraph order is wrong.

- [ ] **Step 3: Order over the whole graph, then filter (v2)**

In `plan_linked_block_execution`, replace the ordering section (everything after the gate `if problems: return ...`) with whole-graph ordering:

```python
    # Order over the WHOLE contract graph (one source of truth), then filter to the requested
    # ids — a scoped subgraph drops transitive edges through omitted contracts and can invert
    # order. target_of must cover every node, so rebuild it across all contracts.
    contracts = reg.list_contracts()
    target_of = {ct.contract_id: ct.target_artifact_id for ct in contracts}
    order_key = {ct.contract_id: (ct.created_at, ct.contract_id) for ct in contracts}
    pairs = [(ct.contract_id, ct.target_artifact_id, reg.sources_for(ct.contract_id))
             for ct in contracts]
    order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:   # defensive: insert_contract prevents cycles atomically
        return {"ok": False, "problems": [{"code": "merge_cycle_detected", "cycle": cycle}]}

    plan = [{"contractId": cid, "targetArtifactId": target_of[cid]}
            for cid in order if cid in requested_set]
    return {"ok": True, "plan": plan}
```

Note: the gate loop above still computes a partial `target_of` for the requested ids — that local is now superseded by the whole-graph `target_of`; the gate loop's job is only validation (`contract_not_found` / `unsupported_merge_kind`). The final function reads:

```python
def plan_linked_block_execution(reg, contract_ids):
    """... (docstring unchanged from Task 2) ..."""
    requested = list(dict.fromkeys(contract_ids))
    requested_set = set(requested)

    problems: list[dict[str, Any]] = []
    for cid in requested:
        ct = reg.get_contract(cid)
        if ct is None:
            problems.append({"code": "contract_not_found", "contractId": cid})
        elif ct.merge_kind != _PLANNABLE_MERGE_KIND:
            problems.append({"code": "unsupported_merge_kind", "contractId": cid,
                             "mergeKind": ct.merge_kind})
    if problems:
        return {"ok": False, "problems": problems}

    contracts = reg.list_contracts()
    target_of = {ct.contract_id: ct.target_artifact_id for ct in contracts}
    order_key = {ct.contract_id: (ct.created_at, ct.contract_id) for ct in contracts}
    pairs = [(ct.contract_id, ct.target_artifact_id, reg.sources_for(ct.contract_id))
             for ct in contracts]
    order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:
        return {"ok": False, "problems": [{"code": "merge_cycle_detected", "cycle": cycle}]}

    plan = [{"contractId": cid, "targetArtifactId": target_of[cid]}
            for cid in order if cid in requested_set]
    return {"ok": True, "plan": plan}
```

- [ ] **Step 4: Run the whole helper test set**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units.py -k "plan_" -q`
Expected: PASS — all five `plan_*` tests (chain, two gates, unrelated, transitive) green.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/work_units.py mcp_server/tests/test_work_units.py
git commit -m "p7(s5): order over whole graph then filter (transitive-omission regression)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Live harness `test_merge_contract_chain_live.py` (collect-only; live run HELD)

The end-to-end chained recomposition proof. It cannot run in CI (`requires_rhino`); this task verifies it imports + collects, then commits. The live run happens at the verification gate (Task 6 / checkpoint) against a throwaway Rhino.

**Files:**
- Create: `mcp_server/tests/test_merge_contract_chain_live.py`

- [ ] **Step 1: Write the live harness**

Create `mcp_server/tests/test_merge_contract_chain_live.py`:

```python
"""Live-Rhino end-to-end for P7 Slice 5 — chained linked-block recomposition.
HELD: requires a running Rhino with RookNative deployed; skips cleanly when Rhino is
unreachable (fresh_document). Hermetic P6/P7 registries (temp dbs) keep the in-process
contract graph to exactly {A, B} and leave the real stores untouched.

Run (throwaway session — replaces the active document repeatedly):
    mcp_server\\.venv\\Scripts\\python.exe -m pytest -m requires_rhino ^
        mcp_server/tests/test_merge_contract_chain_live.py -s
"""
from __future__ import annotations
import os
import tempfile
import pytest

from rook import artifacts, work_units, linked_blocks as lb
from rook.server import _mcp_tool_executor
from .conftest import fresh_document  # noqa: F401

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


@pytest.fixture
def hermetic_registries(tmp_path, monkeypatch):
    """In-process P6/P7 registries pointed at temp dbs so the contract graph is exactly what
    this test records and the real stores are untouched."""
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
    yield tmp_path
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()


def _tmp(tag):
    return os.path.join(tempfile.gettempdir(), f"rook_p7chain_{os.getpid()}_{tag}.3dm")


async def _single_live_session():
    """Single-Rhino harness contract: exactly one live Rhino. More than one is a harness
    safety refusal (close extras / use an owned Workbench later), not a product failure."""
    sess = await _mcp_tool_executor("rhino_sessions", {})
    items = (sess.get("data") or {}).get("sessions") or sess.get("sessions") or []
    live = [s for s in items if (s.get("liveness") or {}).get("state") == "live"]
    assert len(live) == 1, (
        f"expected exactly one live Rhino; got {len(live)}. Multiple live Rhino sessions: "
        "close the extras, or run under an owned Workbench in a later slice. "
        "Harness safety guard, not a product failure.")
    return live[0]["session"]


async def _new_doc_with_box(name, c1, c2, path):
    await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
    await _mcp_tool_executor("rhino_create",
        {"type": "BOX", "corner1": c1, "corner2": c2, "name": name})
    s = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": path})
    assert s.get("success") is not False, f"save {name} failed: {s!r}"


async def _open(path):
    r = await _mcp_tool_executor("rhino_document_ops", {"action": "open", "path": path})
    assert r.get("success") is not False, f"open {path} failed: {r!r}"


async def _execute(cid, session):
    return await _mcp_tool_executor("rhino_merge_contract_execute",
        {"contractId": cid, "session": session, "expectedMergeKind": "linked_block"})


async def _assert_linked(session, names):
    """Each deterministic name resolves and isLinked on the active doc of `session`."""
    for nm in names:
        info = await _mcp_tool_executor("rhino_block_info", {"name": nm, "session": session})
        assert info.get("isLinked") is True, f"{nm}: {info!r}"


async def test_chain_recomposition_end_to_end(fresh_document, hermetic_registries):
    s1 = _tmp("s1"); s2 = _tmp("s2"); inter = _tmp("inter"); master = _tmp("master")
    paths = [s1, s2, inter, master]
    try:
        # 1. four saved docs, each registered in P6 (temp registry)
        await _new_doc_with_box("s1box", [0, 0, 0], [1, 1, 1], s1)
        await _new_doc_with_box("s2box", [2, 0, 0], [3, 1, 1], s2)
        await _new_doc_with_box("interbox", [0, 2, 0], [1, 3, 1], inter)
        await _new_doc_with_box("masterbox", [2, 2, 0], [3, 3, 1], master)
        ids = {}
        for p in paths:
            r = await artifacts.register_artifact(p)
            ids[p] = r["data"]["artifact"]["artifactId"]
        s1_id, s2_id, inter_id, master_id = ids[s1], ids[s2], ids[inter], ids[master]

        # 2. record A: [s1,s2] -> inter ; B: [inter] -> master
        recA = await work_units.record_merge_contract(
            target_artifact_id=inter_id, source_artifact_ids=[s1_id, s2_id],
            merge_kind="linked_block", refresh_policy="refresh_on_demand")
        recB = await work_units.record_merge_contract(
            target_artifact_id=master_id, source_artifact_ids=[inter_id],
            merge_kind="linked_block", refresh_policy="refresh_on_demand")
        cid_A = recA["data"]["contractId"]; cid_B = recB["data"]["contractId"]

        # 3. scoped plan == [A, B]
        reg = work_units.work_units_registry()
        plan = work_units.plan_linked_block_execution(reg, [cid_A, cid_B])
        assert plan["ok"] is True, plan
        assert plan["plan"] == [{"contractId": cid_A, "targetArtifactId": inter_id},
                                {"contractId": cid_B, "targetArtifactId": master_id}], plan

        session = await _single_live_session()
        name_A1 = lb.block_def_name(cid_A, s1_id)
        name_A2 = lb.block_def_name(cid_A, s2_id)
        name_B = lb.block_def_name(cid_B, inter_id)

        # 4. step A: open inter, execute, assert WHILE inter is active
        await _open(inter)
        exA = await _execute(cid_A, session)
        assert exA.get("executed") is True and exA.get("saved") is True, exA
        assert {e["sourceArtifactId"]: e["outcome"] for e in exA["perSource"]} == {
            s1_id: lb.CREATED_LINK, s2_id: lb.CREATED_LINK}, exA
        await _assert_linked(session, [name_A1, name_A2])

        # step B: open master, execute, assert WHILE master is active
        await _open(master)
        exB = await _execute(cid_B, session)
        assert exB.get("executed") is True and exB.get("saved") is True, exB
        assert exB["perSource"][0]["outcome"] == lb.CREATED_LINK, exB
        await _assert_linked(session, [name_B])   # master consumes the intermediate id, not s1/s2
        infoB = await _mcp_tool_executor("rhino_block_info", {"name": name_B, "session": session})
        print("OBSERVE master name_B sourcePath:", infoB.get("sourcePath"))

        # 5. idempotent re-run: refreshed_existing, saved, deterministic names still resolve
        await _open(inter)
        exA2 = await _execute(cid_A, session)
        assert exA2.get("saved") is True, exA2
        assert {e["outcome"] for e in exA2["perSource"]} == {lb.REFRESHED_EXISTING}, exA2
        await _assert_linked(session, [name_A1, name_A2])

        await _open(master)
        exB2 = await _execute(cid_B, session)
        assert exB2.get("saved") is True, exB2
        assert exB2["perSource"][0]["outcome"] == lb.REFRESHED_EXISTING, exB2
        await _assert_linked(session, [name_B])

        # 6. OBSERVATIONS (non-failing): evict master from the single active slot, reopen, and
        # record sourcePath + whether /blocks surfaces nested source defs. Nested-refresh
        # propagation is observed, not asserted (spec §6).
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})  # evict master
        await _open(master)
        reopened = await _mcp_tool_executor("rhino_block_info", {"name": name_B, "session": session})
        print("OBSERVE master name_B after evict+reopen:", reopened)
        blocks = await _mcp_tool_executor("rhino_blocks", {"session": session})
        names_in_master = [b.get("name") for b in (blocks.get("data") or {}).get("blocks") or []]
        print("OBSERVE master /blocks names (nested presentation?):", names_in_master)
    finally:
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass
```

- [ ] **Step 2: Verify it imports and collects (no live run)**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_contract_chain_live.py --collect-only -q`
Expected: collects `test_chain_recomposition_end_to_end` with no import/syntax error (1 test collected). It will not execute here.

- [ ] **Step 3: Byte-compile to catch syntax errors**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tests/test_merge_contract_chain_live.py`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_merge_contract_chain_live.py
git commit -m "p7(s5): held live harness for chained linked-block recomposition (collect-only)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Full offline suite + baseline parity (both directions)

**Files:** none (verification only)

- [ ] **Step 1: Run the full offline suite on the branch**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no`
Capture the summary line (e.g. `N passed, M skipped`) and the named FAILED/ERROR set (should be only pre-existing, unrelated failures, if any).

- [ ] **Step 2: Capture the `main` baseline for comparison**

```powershell
git stash --include-untracked  # only if any uncommitted scratch remains; normally a no-op
git checkout main
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no > $env:TEMP\rook_main_tests.txt 2>&1
git checkout feature/p7-chain-recomposition
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no > $env:TEMP\rook_branch_tests.txt 2>&1
```

- [ ] **Step 3: Diff the named FAILED/ERROR sets in BOTH directions**

```powershell
$main   = Select-String -Path $env:TEMP\rook_main_tests.txt   -Pattern '^(FAILED|ERROR) ' | ForEach-Object { $_.Line }
$branch = Select-String -Path $env:TEMP\rook_branch_tests.txt -Pattern '^(FAILED|ERROR) ' | ForEach-Object { $_.Line }
"main-only:";   Compare-Object $main $branch | Where-Object SideIndicator -eq '<=' | ForEach-Object { $_.InputObject }
"branch-only:"; Compare-Object $main $branch | Where-Object SideIndicator -eq '=>' | ForEach-Object { $_.InputObject }
```

Expected: **branch-only is empty** (no new failures), and the branch shows **+5 passed** (the five `plan_*` tests) plus the two `_ordered_contract_ids` tests over `main`. Counts alone are insufficient — the named-set comparison both ways is the parity gate (#220 lesson).

- [ ] **Step 4: Checkpoint — pause for review before the live gate**

Report: branch summary line, the both-directions parity result, and the new-test count. Do not proceed to merge/PR until the live gate is run (Task 6) and reviewed.

---

## Task 6: Live verification gate + finish the branch

The live run requires a throwaway Rhino. **Per the standing fixture rule, confirm a throwaway Rhino document/session in chat before running** (the test repeatedly calls `rhino_document_ops(action="new"/"open")` and the `fresh_document` fixture).

**Files:** none (verification + branch completion)

- [ ] **Step 1: Confirm a throwaway Rhino is available**

Ensure exactly one live Rhino (with RookNative deployed) and a disposable document — or launch one via `rhino_launch` if none is running (no user document to clobber). Confirm in chat.

- [ ] **Step 2: Run the live harness**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -m requires_rhino mcp_server/tests/test_merge_contract_chain_live.py -s`
Expected: `1 passed`. Capture the `OBSERVE ...` lines (sourcePath forms, evict+reopen state, `/blocks` nested presentation) — these are the slice's deliverable observations.

- [ ] **Step 3: Record the observed Save-membrane / nested-link behavior**

Summarize the `OBSERVE` output (sourcePath absolute/relative; whether master's nested view reflected the intermediate refresh; whether `/blocks` surfaced nested source defs; any lock/stale symptom) for the spec follow-up and the memory update.

- [ ] **Step 4: Finish the development branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Then follow `superpowers:finishing-a-development-branch` — verify the offline suite passes, present the options, and (per the user's standard flow) push + open a PR for Codex review, then squash-merge with `gh pr merge --squash --delete-branch` when the user pulls the trigger.

---

## Self-Review

**1. Spec coverage:**
- §3.1 `_ordered_contract_ids` factor + `_validate_graph` parity → Task 1. ✓
- §3.2 `plan_linked_block_execution` (gates, whole-graph order, filter) → Tasks 2–3. ✓
- §3.3 omitted-producer allow → Task 3 transitive test asserts no problem. ✓
- §4 live harness (hermetic registries, one-Rhino doc-switching, per-step interleaved asserts, evict+reopen) → Task 4 + Task 6. ✓
- §5 hard assertions tied to `block_def_name` (master consumes intermediate id; refreshed_existing idempotency) → Task 4 assertions. ✓
- §6 observations (sourcePath, nested presentation, nested-refresh propagation observed-not-asserted) → Task 4 step 6 `print` + Task 6 step 3. ✓
- §8 offline tests incl. unrelated-isolation + transitive regression with `created_at` detail → Tasks 1–3. ✓
- §8 baseline parity both directions → Task 5. ✓

**2. Placeholder scan:** No TBD/TODO/"handle errors". Every code step shows complete code; every run step shows the exact command + expected result.

**3. Type consistency:** `plan_linked_block_execution(reg, contract_ids)` returns `{"ok", "plan"|"problems"}` consistently across Tasks 2–4 and is consumed identically in Task 4 (`plan["ok"]`, `plan["plan"]`, entries `{"contractId","targetArtifactId"}`). `_ordered_contract_ids(pairs, order_key) -> (order, cycle)` is consistent in Task 1 and both helper versions. `block_def_name(contract_id, source_artifact_id)` matches `linked_blocks.py`. Problem codes (`contract_not_found`, `unsupported_merge_kind`, `merge_cycle_detected`) match the spec and the existing `_RETRYABLE` vocabulary. Live-tool argument shapes (`rhino_merge_contract_execute`, `rhino_block_info`, `rhino_document_ops`, `rhino_blocks`, `rhino_sessions`) match their handlers.

No issues found.
