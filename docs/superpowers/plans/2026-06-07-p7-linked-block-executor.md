# P7 Linked-Block Merge Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `rhino_merge_contract_execute` — the first P7 tool that mutates Rhino — driving a strict `linked_block` merge contract into linked block definitions in a verified target document, idempotently, with a non-mutating dry-run.

**Architecture:** A pure decision core (`plan_source_action` in `linked_blocks.py`) classifies each source from read facts; an I/O orchestrator (`merge_execution.py`) resolves the contract + P6 sources, pins the selected session via `bridge.rhino_request_context`, classifies, and (unless dry-run) applies + saves. The injected `call_tool` is the internal `_call_tool_dispatch` (`{success,data}` dicts, never public text). No durable writes; the saved `.3dm` is the execution artifact.

**Tech Stack:** Python 3.11 (editable install — pure-Python edits need no rebuild for pytest), pytest + pytest-asyncio, SQLite (existing P6/P7 registries), the existing Rhino MCP dispatch + routing-context machinery. **No native build** (the #227 read substrate already shipped).

**Spec:** `docs/superpowers/specs/2026-06-07-p7-linked-block-executor-design.md` (read it first).

**Pytest:** `mcp_server/.venv/Scripts/python.exe -m pytest`

**Branch:** `feature/p7-linked-block-executor` off `main` (spec already on `main`/`origin` at `f6db0a4`).

---

## File Structure

- **MODIFY** `mcp_server/src/rook/linked_blocks.py` — add planned-action/outcome string constants + the pure `plan_source_action`. Stays import-pure (no `server`/Rhino/`artifacts`/`work_units`).
- **CREATE** `mcp_server/src/rook/merge_execution.py` — the orchestrator (the first Rhino-touching P7 module). Imports `work_units`, `artifacts`, `linked_blocks`, `targeting`, `bridge`; injected `call_tool`.
- **MODIFY** `mcp_server/src/rook/targeting.py` — register the tool: `_ALL_KNOWN_TOOLS`, `_RHINO_INDEPENDENT_MUTATE_TOOLS` (→ `RhinoToolPolicy(False,"mutate")`), `_NON_ROUTED_SESSION_ARGUMENT_TOOLS`.
- **MODIFY** `mcp_server/src/rook/server.py` — declare `rhino_merge_contract_execute`; dispatch case calls `merge_execution.execute_merge_contract(..., call_tool=_call_tool_dispatch)`.
- **MODIFY** `mcp_server/tests/test_linked_blocks.py` — `plan_source_action` decision table.
- **CREATE** `mcp_server/tests/test_merge_execution.py` — orchestrator unit tests (fake `call_tool` + monkeypatched `resolve_tool_route` + temp registries).
- **MODIFY** `mcp_server/tests/test_session_routing.py` — extend the exact-set membership assertion.
- **MODIFY** `mcp_server/tests/test_work_units_tools.py` — add the executor's `(False,"mutate")` policy test (NOT the meta lists).
- **CREATE** `mcp_server/tests/test_merge_contract_execute_live.py` — gated end-to-end live smoke (HELD — needs Rhino).

---

## Task 1: Pure planner `plan_source_action` + constants

**Files:**
- Modify: `mcp_server/src/rook/linked_blocks.py`
- Test: `mcp_server/tests/test_linked_blocks.py`

- [ ] **Step 1: Write the failing tests** — append to `mcp_server/tests/test_linked_blocks.py`:

```python
from rook import linked_blocks as lb

_AID_A = "a" * 64          # a valid-looking 64-hex source artifact id
_AID_B = "b" * 64          # a different one


def _facts(is_linked, source_path, block_type="Linked"):
    return {"isLinked": is_linked, "sourcePath": source_path, "blockType": block_type}


def test_plan_absent_block_present_source_creates():
    assert lb.plan_source_action(
        block_facts=None, expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=True,
        refresh_policy="refresh_on_demand") == lb.WOULD_CREATE_LINK


def test_plan_absent_block_missing_source_not_present():
    assert lb.plan_source_action(
        block_facts=None, expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=False,
        refresh_policy="refresh_on_demand") == lb.SOURCE_ARTIFACT_NOT_PRESENT


def test_plan_existing_nonlinked_is_conflict():
    assert lb.plan_source_action(
        block_facts=_facts(False, ""), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=True,
        refresh_policy="refresh_on_demand") == lb.CONFLICT_NONLINKED


def test_plan_linked_unparseable_path_is_unresolvable():
    assert lb.plan_source_action(
        block_facts=_facts(True, "??"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=True,
        refresh_policy="refresh_on_demand") == lb.SOURCE_PATH_UNRESOLVABLE


def test_plan_linked_different_source_is_conflict():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/x.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_B, source_present=True,
        refresh_policy="refresh_on_demand") == lb.CONFLICT_DIFFERENT_SOURCE


def test_plan_same_source_on_demand_refreshes():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=True,
        refresh_policy="refresh_on_demand") == lb.WOULD_REFRESH_EXISTING


def test_plan_same_source_after_save_is_already_linked():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=True,
        refresh_policy="refresh_after_save") == lb.ALREADY_LINKED


def test_plan_same_source_absent_present_bar_blocks_already_linked():
    # Finding 2: present-bar applies to already_linked too.
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=False,
        refresh_policy="refresh_after_save") == lb.SOURCE_ARTIFACT_NOT_PRESENT


def test_plan_same_source_absent_present_bar_blocks_refresh():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=False,
        refresh_policy="refresh_on_demand") == lb.SOURCE_ARTIFACT_NOT_PRESENT
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_linked_blocks.py -q`
Expected: FAIL — `AttributeError: module 'rook.linked_blocks' has no attribute 'plan_source_action'` (and the constants).

- [ ] **Step 3: Implement** — append to `mcp_server/src/rook/linked_blocks.py`:

```python
# ----- P7 Slice 4: per-source planned actions (dry-run) + outcomes (execute) -----
# Planned actions (also the dry-run plannedAction values):
WOULD_CREATE_LINK = "would_create_link"
WOULD_REFRESH_EXISTING = "would_refresh_existing"
ALREADY_LINKED = "already_linked"
CONFLICT_NONLINKED = "conflict_nonlinked"
CONFLICT_DIFFERENT_SOURCE = "conflict_different_source"
SOURCE_ARTIFACT_NOT_PRESENT = "source_artifact_not_present"
SOURCE_PATH_UNRESOLVABLE = "source_path_unresolvable"
# Execute-mode outcomes for the actionable plans:
CREATED_LINK = "created_link"
REFRESHED_EXISTING = "refreshed_existing"
BLOCK_LINK_FAILED = "block_link_failed"
BLOCK_REFRESH_FAILED = "block_refresh_failed"


def plan_source_action(*, block_facts, expected_source_artifact_id,
                       observed_source_artifact_id, source_present, refresh_policy):
    """PURE classification of one source against the target document's block table.

    block_facts: the /blocks entry for the deterministic block name, or None if absent.
        When present: {"isLinked": bool, "sourcePath": str, "blockType": str}.
    observed_source_artifact_id: artifact_id_for(resolved observed sourcePath), or None
        if the observed linked path can't be resolved.
    source_present: True iff the contract source resolves to a P6 row file_state=='present'.

    Hard conflicts dominate (the name is taken by the wrong thing — a blocker regardless).
    The strict present-bar (Finding 2) gates EVERY success-eligible action, including
    already_linked: refresh_policy chooses refresh-vs-no-op only AFTER presence is proven.
    """
    if block_facts is None:
        return WOULD_CREATE_LINK if source_present else SOURCE_ARTIFACT_NOT_PRESENT
    if not block_facts.get("isLinked"):
        return CONFLICT_NONLINKED
    if observed_source_artifact_id is None:
        return SOURCE_PATH_UNRESOLVABLE
    if observed_source_artifact_id != expected_source_artifact_id:
        return CONFLICT_DIFFERENT_SOURCE
    if not source_present:                       # present-bar before refresh-vs-no-op
        return SOURCE_ARTIFACT_NOT_PRESENT
    if refresh_policy == "refresh_on_demand":
        return WOULD_REFRESH_EXISTING
    return ALREADY_LINKED
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_linked_blocks.py -q`
Expected: PASS (all prior tests + the 9 new ones).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/linked_blocks.py mcp_server/tests/test_linked_blocks.py
git commit -m "feat(p7): pure plan_source_action + planned-action/outcome constants"
```

---

## Task 2: Targeting policy — non-routed mutating tool

**Files:**
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_work_units_tools.py`, `mcp_server/tests/test_session_routing.py`

- [ ] **Step 1: Write the failing tests** — append to `mcp_server/tests/test_work_units_tools.py`:

```python
def test_merge_contract_execute_is_non_routed_mutate():
    # Finding 1: it MUTATES Rhino via internal subcalls, so it is NOT meta — but it is
    # non-routed (resolves its own session) and owns a non-routing `session` argument.
    name = "rhino_merge_contract_execute"
    assert name in targeting._ALL_KNOWN_TOOLS
    assert name not in targeting._META_TOOLS
    assert targeting.policy_for_tool(name) == targeting.RhinoToolPolicy(False, "mutate")
    assert targeting.allows_non_routed_session_argument(name) is True
```

And update the exact-set assertion in `mcp_server/tests/test_session_routing.py`:

```python
def test_non_routed_session_argument_tools_membership():
    # rhino_session_capabilities (P1) + rhino_workbench_close (P4) + rhino_merge_contract_execute
    # (P7 Slice 4) own a non-routing `session` argument — the set grows only by intentional addition.
    assert targeting._NON_ROUTED_SESSION_ARGUMENT_TOOLS == {
        "rhino_session_capabilities", "rhino_workbench_close", "rhino_merge_contract_execute"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py::test_merge_contract_execute_is_non_routed_mutate mcp_server/tests/test_session_routing.py::test_non_routed_session_argument_tools_membership -q`
Expected: FAIL — tool not in `_ALL_KNOWN_TOOLS`; membership set differs.

- [ ] **Step 3: Implement** — three edits in `mcp_server/src/rook/targeting.py`.

In `_ALL_KNOWN_TOOLS`, after `"rhino_planned_contracts",`:

```python
    "rhino_merge_contract_execute",
```

In `_RHINO_INDEPENDENT_MUTATE_TOOLS`, add (keeps it non-routed but `risk="mutate"` — the set name is imperfect for a Rhino-mutating tool, but `RhinoToolPolicy(False,"mutate")` is the load-bearing policy; a dedicated set is a deferred cleanup):

```python
    "rhino_merge_contract_execute",
```

In `_NON_ROUTED_SESSION_ARGUMENT_TOOLS`:

```python
_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {
    "rhino_session_capabilities", "rhino_workbench_close", "rhino_merge_contract_execute"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py mcp_server/tests/test_session_routing.py mcp_server/tests/test_multi_instance_targeting.py -q`
Expected: PASS (incl. `test_every_exposed_tool_has_policy_entry`, which now sees a policy for the new tool once it's declared in Task 7 — if it runs before Task 7 and asserts over declared tools, it still passes because the tool is in `_ALL_KNOWN_TOOLS`; the declared-vs-policy cross-check is exercised in Task 7).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_work_units_tools.py mcp_server/tests/test_session_routing.py
git commit -m "feat(p7): targeting policy for rhino_merge_contract_execute (non-routed mutate)"
```

---

## Task 3: Orchestrator scaffold — preconditions 1–6 (gates, no Rhino yet)

**Files:**
- Create: `mcp_server/src/rook/merge_execution.py`
- Test: `mcp_server/tests/test_merge_execution.py`

- [ ] **Step 1: Write the failing tests** — create `mcp_server/tests/test_merge_execution.py`:

```python
from __future__ import annotations
import asyncio
import pytest
from rook import merge_execution, work_units, artifacts


@pytest.fixture
def temp_registries(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
    yield tmp_path
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()


async def _never_call(name, args):  # call_tool that must not be reached in gate tests
    raise AssertionError(f"call_tool should not be invoked here, got {name!r}")


def _run(coro):
    return asyncio.run(coro)


def test_invalid_contract_id(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="", session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "invalid_argument"


def test_unknown_expected_merge_kind(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="mc-x", session="rhino-1", expected_merge_kind="linkedblock",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "invalid_argument"


def test_session_required(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="mc-x", session="", expected_merge_kind="linked_block",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "session_required"


def _make_contract(tmp_path, merge_kind="linked_block", refresh="refresh_on_demand"):
    """Register a present target+source in P6 and record a contract; return (contract_id, tgt, src)."""
    tgt = tmp_path / "target.3dm"
    src = tmp_path / "source.3dm"
    tgt.write_bytes(b"t")
    src.write_bytes(b"s")
    rt = _run(artifacts.register_artifact(str(tgt)))
    rs = _run(artifacts.register_artifact(str(src)))
    tgt_id = rt["data"]["artifact"]["artifactId"]
    src_id = rs["data"]["artifact"]["artifactId"]
    rec = _run(work_units.record_merge_contract(
        target_artifact_id=tgt_id, source_artifact_ids=[src_id],
        merge_kind=merge_kind, refresh_policy=refresh))
    return rec["data"]["contractId"], tgt_id, src_id, str(tgt), str(src)


def test_contract_not_found(temp_registries):
    out = _run(merge_execution.execute_merge_contract(
        contract_id="mc-nope", session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "contract_not_found"


def test_merge_kind_mismatch(temp_registries):
    cid, *_ = _make_contract(temp_registries, merge_kind="linked_block")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="import",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False and out["data"]["code"] == "merge_kind_mismatch"


def test_unsupported_merge_kind(temp_registries):
    cid, *_ = _make_contract(temp_registries, merge_kind="import")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="import",
        dry_run=False, call_tool=_never_call))
    assert out["success"] is False
    assert out["data"]["code"] == "unsupported_merge_kind"
    assert out["data"]["supportedMergeKinds"] == ["linked_block"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.merge_execution'`.

- [ ] **Step 3: Implement** — create `mcp_server/src/rook/merge_execution.py`:

```python
"""P7 Slice 4 — linked-block merge executor (the first Rhino-mutating P7 tool).

I/O shell: resolves a strict linked_block merge_contract + its P6 sources, pins the
selected session via bridge.rhino_request_context, classifies each source via the PURE
linked_blocks.plan_source_action, and (unless dry_run) ensures each linked block + saves
the target. Writes nothing durable; the saved .3dm is the execution artifact.
See docs/superpowers/specs/2026-06-07-p7-linked-block-executor-design.md.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from . import artifacts as _artifacts
from . import bridge as _bridge
from . import linked_blocks as _lb
from . import targeting as _targeting
from . import work_units as _work_units

CallTool = Callable[[str, dict], Awaitable[dict]]

_SUPPORTED_MERGE_KINDS = ("linked_block",)

_RETRYABLE = {
    "invalid_argument": False, "session_required": False,
    "invalid_session_id": False, "rhino_session_not_found": False,
    "panel_target_locked": False, "panel_target_stale": True,
    "panel_target_config_error": False, "rhino_target_unavailable": True,
    "contract_not_found": False, "merge_kind_mismatch": False, "unsupported_merge_kind": False,
    "target_not_open": True, "target_document_mismatch": True,
    "block_table_read_failed": True,
    "merge_contract_not_executable": False,
    "document_save_failed": True, "merge_contract_execution_incomplete": True,
}

_HARD_BLOCKERS = frozenset({
    _lb.CONFLICT_NONLINKED, _lb.CONFLICT_DIFFERENT_SOURCE,
    _lb.SOURCE_ARTIFACT_NOT_PRESENT, _lb.SOURCE_PATH_UNRESOLVABLE,
})


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "data": {
        "code": code, "message": message, "retryable": _RETRYABLE.get(code, True), **extra}}


async def execute_merge_contract(*, contract_id: str, session: str, expected_merge_kind: str,
                                 dry_run: bool, call_tool: CallTool) -> dict[str, Any]:
    # 1-2. lower-plane guards (reuse work_units' shared guards → identical codes)
    if (u := await _work_units._registry_unusable()) is not None:
        return u
    if (p6u := await _work_units._p6_unusable()) is not None:
        return p6u
    # 3. arguments
    if not isinstance(contract_id, str) or not contract_id.strip():
        return _err("invalid_argument", "'contractId' must be a non-empty string.")
    if expected_merge_kind not in _work_units.MERGE_KINDS:
        return _err("invalid_argument",
                    f"'expectedMergeKind' must be one of {_work_units.MERGE_KINDS}.")
    if not isinstance(session, str) or not session.strip():
        return _err("session_required",
                    "'session' is required (e.g. 'rhino-<pid>'); no ambient routing fallback.")
    # 4-6. contract + kind gates
    reg = _work_units.work_units_registry()
    contract = await asyncio.to_thread(lambda: reg.get_contract(contract_id))
    if contract is None:
        return _err("contract_not_found", f"No merge contract {contract_id!r}.")
    if contract.merge_kind != expected_merge_kind:
        return _err("merge_kind_mismatch",
                    f"Contract kind {contract.merge_kind!r} != expectedMergeKind {expected_merge_kind!r}.",
                    contractMergeKind=contract.merge_kind, expectedMergeKind=expected_merge_kind)
    if contract.merge_kind not in _SUPPORTED_MERGE_KINDS:
        return _err("unsupported_merge_kind",
                    f"Slice 4 executes only {list(_SUPPORTED_MERGE_KINDS)}.",
                    supportedMergeKinds=list(_SUPPORTED_MERGE_KINDS))
    # (Task 4 continues here: session resolution + Rhino-facing work.)
    raise NotImplementedError("session + apply path lands in Task 4-6")
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -q`
Expected: PASS (the 7 gate tests; none reach the `NotImplementedError`).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/merge_execution.py mcp_server/tests/test_merge_execution.py
git commit -m "feat(p7): merge_execution scaffold — preconditions + kind gates"
```

---

## Task 4: Session resolution + routing-context pin + target identity

**Files:**
- Modify: `mcp_server/src/rook/merge_execution.py`
- Test: `mcp_server/tests/test_merge_execution.py`

- [ ] **Step 1: Write the failing tests** — append to `mcp_server/tests/test_merge_execution.py`:

```python
from rook import targeting, bridge


class FakeRhino:
    """Records context port on every call; returns canned envelopes by tool name."""
    def __init__(self, doc_path, blocks=None, blocks_ok=True,
                 link_ok=True, refresh_ok=True, save_ok=True, doc_path_after=None):
        self.doc_path = doc_path
        self.doc_path_after = doc_path_after  # if set, returned on the 2nd+ rhino_document read (drift)
        self._doc_reads = 0
        self.blocks = blocks if blocks is not None else []
        self.blocks_ok = blocks_ok
        self.link_ok, self.refresh_ok, self.save_ok = link_ok, refresh_ok, save_ok
        self.seen_ports = []
        self.calls = []

    async def __call__(self, name, args):
        self.seen_ports.append(bridge.get_rhino_request_context()["port"])
        # Pin the "routing via context, not args" rule (the stale-port correction):
        assert "port" not in args and "session" not in args, \
            f"sub-call {name!r} must not carry routing selectors: {args!r}"
        self.calls.append((name, args))
        if name == "rhino_document":
            self._doc_reads += 1
            p = (self.doc_path if (self._doc_reads == 1 or self.doc_path_after is None)
                 else self.doc_path_after)
            return {"success": True, "data": {"documentPath": p}}
        if name == "rhino_blocks":
            return {"success": self.blocks_ok, "data": {"blocks": self.blocks}}
        if name == "rhino_block_link":
            return {"success": self.link_ok, "data": {"name": args["name"]}}
        if name == "rhino_block_refresh":
            return {"success": self.refresh_ok, "data": {"name": args["name"]}}
        if name == "rhino_document_ops":
            return {"success": self.save_ok, "data": {}}
        raise AssertionError(f"unexpected tool {name!r}")


_PINNED = 59123


def _pin_route(monkeypatch, *, success=True, error=None):
    route = targeting.ToolRoute(
        success=success, error=error,
        target=(targeting.InstanceRef(port=_PINNED, process_id=4242) if success else None),
        selection="session")
    monkeypatch.setattr(targeting, "resolve_tool_route", lambda *a, **k: route)
    return route


def test_session_not_found(temp_registries, monkeypatch):
    cid, *_ = _make_contract(temp_registries)
    _pin_route(monkeypatch, success=False, error="rhino_session_not_found")
    fake = FakeRhino(doc_path="C:/whatever.3dm")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-9", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "rhino_session_not_found"
    assert fake.calls == []  # never touched Rhino


def test_target_document_mismatch(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path="C:/someone-elses-doc.3dm")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "target_document_mismatch"
    # Finding 1: the rhino_document read happened on the pinned port.
    assert fake.seen_ports and all(p == _PINNED for p in fake.seen_ports)


def test_target_not_open(temp_registries, monkeypatch):
    cid, *_ = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path="")  # unsaved / no path
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "target_not_open"


def test_session_resolution_passes_has_explicit_session(temp_registries, monkeypatch):
    # Finding 3 (load-bearing spec correction): a broken impl that omits has_explicit_session=True
    # would silently fall through to ambient routing. A dedicated fake resolver records the kwargs
    # so omission FAILS this test (has_explicit_session would default to False).
    cid, *_ = _make_contract(temp_registries)
    seen = {}

    def _fake(name, *, explicit_port=None, explicit_session=None, has_explicit_session=False):
        seen.update(name=name, explicit_session=explicit_session,
                    has_explicit_session=has_explicit_session)
        return targeting.ToolRoute(
            success=True, target=targeting.InstanceRef(port=_PINNED, process_id=4242),
            selection="session")

    monkeypatch.setattr(targeting, "resolve_tool_route", _fake)
    fake = FakeRhino(doc_path="C:/wrong.3dm")  # mismatch → returns early after resolution
    _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=True, call_tool=fake))
    assert seen == {"name": "rhino_document", "explicit_session": "rhino-1",
                    "has_explicit_session": True}
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -k "session_not_found or target_ or has_explicit" -q`
Expected: FAIL — `NotImplementedError` (the session/apply path isn't built).

- [ ] **Step 3: Implement** — in `mcp_server/src/rook/merge_execution.py`, add the helpers above `execute_merge_contract`:

```python
def _resolve_session(session: str):
    """Resolve the explicit selector to a concrete route. has_explicit_session=True is
    load-bearing — without it resolve_tool_route ignores the selector and falls through to
    ambient routing (the very thing this slice forbids)."""
    route = _targeting.resolve_tool_route(
        "rhino_document", explicit_session=session, has_explicit_session=True)
    if not route.success:
        return None, _err(route.error or "rhino_target_unavailable",
                          f"Could not resolve session {session!r}: {route.error}.")
    if route.target is None:
        return None, _err("rhino_target_unavailable",
                          f"Session {session!r} resolved to no live instance.")
    return route, None


async def _read_active_doc_path(call_tool: CallTool):
    """(path, err). path is the active document's OS path; target_not_open when absent/unsaved."""
    resp = await call_tool("rhino_document", {})
    if resp.get("success") is False:
        return None, _err("target_not_open", "Could not read the active document on the session.")
    data = resp.get("data") or {}
    path = data.get("documentPath") or data.get("path")
    if not path:
        return None, _err("target_not_open",
                          "The selected session has no saved active document (no path).")
    return path, None


def _verify_target_identity(active_path: str, target_artifact_id: str):
    norm = _artifacts.normalize_path(active_path)
    if _artifacts.artifact_id_for(norm) != target_artifact_id:
        return _err("target_document_mismatch",
                    "The selected session's active document is not the contract target.",
                    activeDocumentPath=active_path, targetArtifactId=target_artifact_id)
    return None
```

Then replace the `raise NotImplementedError(...)` tail of `execute_merge_contract` with:

```python
    sources = await asyncio.to_thread(lambda: reg.sources_for(contract_id))
    # 7. resolve + pin the session
    route, serr = _resolve_session(session)
    if serr is not None:
        return serr
    # 8+. all Rhino-facing work inside the pinned routing context (Finding 1)
    with _bridge.rhino_request_context(
            port=route.target.port, process_id=route.target.process_id,
            document_serial_number=route.document_serial_number):
        active_path, terr = await _read_active_doc_path(call_tool)
        if terr is not None:
            return terr
        if (merr := _verify_target_identity(active_path, contract.target_artifact_id)) is not None:
            return merr
        # (Task 5 continues here: classify; Task 6: apply + save.)
        raise NotImplementedError("classify + apply lands in Task 5-6")
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -k "session_not_found or target_ or has_explicit" -q`
Expected: PASS. (The Task-5/6 classify+apply path is still a `NotImplementedError` stub, but none of these tests reach it — each returns at session resolution or the target-identity check.)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/merge_execution.py mcp_server/tests/test_merge_execution.py
git commit -m "feat(p7): merge_execution session pin + routing-context + target identity"
```

---

## Task 5: Per-source resolution + classify + dry-run envelope

**Files:**
- Modify: `mcp_server/src/rook/merge_execution.py`
- Test: `mcp_server/tests/test_merge_execution.py`

- [ ] **Step 1: Write the failing tests** — append to `mcp_server/tests/test_merge_execution.py`:

```python
from rook import linked_blocks as lb


def test_dry_run_absent_block_is_executable_create(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path=tgt_path, blocks=[])  # no defs yet
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=True, call_tool=fake))
    assert out["success"] is True
    assert out["data"]["dryRun"] is True and out["data"]["executable"] is True
    assert out["data"]["blockers"] == []
    ps = out["data"]["perSource"]
    assert len(ps) == 1 and ps[0]["plannedAction"] == lb.WOULD_CREATE_LINK
    assert ps[0]["blockName"] == lb.block_def_name(cid, src_id)
    # dry-run mutates nothing
    assert [n for n, _ in fake.calls] == ["rhino_document", "rhino_blocks"]


def test_dry_run_present_bar_blocks_already_linked(temp_registries, monkeypatch):
    # Existing correct link, but the source file is deregistered → not P6-present.
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(
        temp_registries, refresh="refresh_after_save")
    _run(artifacts.deregister_artifact(artifact_id=src_id))  # source no longer present
    _pin_route(monkeypatch)
    name = lb.block_def_name(cid, src_id)
    fake = FakeRhino(doc_path=tgt_path, blocks=[
        {"name": name, "isLinked": True, "sourcePath": src_path, "blockType": "Linked"}])
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=True, call_tool=fake))
    assert out["data"]["executable"] is False
    assert out["data"]["perSource"][0]["plannedAction"] == lb.SOURCE_ARTIFACT_NOT_PRESENT


def test_dry_run_conflict_different_source(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    name = lb.block_def_name(cid, src_id)
    fake = FakeRhino(doc_path=tgt_path, blocks=[
        {"name": name, "isLinked": True, "sourcePath": "C:/different/other.3dm", "blockType": "Linked"}])
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=True, call_tool=fake))
    assert out["data"]["executable"] is False
    assert out["data"]["perSource"][0]["plannedAction"] == lb.CONFLICT_DIFFERENT_SOURCE
    assert out["data"]["blockers"][0]["code"] == lb.CONFLICT_DIFFERENT_SOURCE


def test_block_table_read_failure_fails_closed(temp_registries, monkeypatch):
    # Finding 1: a FAILED /blocks read must NOT look like an empty table; fail closed, no mutation.
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path=tgt_path, blocks_ok=False)  # /blocks returns success:false
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "block_table_read_failed"
    assert out["data"]["retryable"] is True
    assert "rhino_block_link" not in [n for n, _ in fake.calls]    # never mutated
    assert "rhino_document_ops" not in [n for n, _ in fake.calls]  # never saved
```

The `_read_blocks` failure check sits before the `dry_run`/execute branch, so it fails closed in **both** modes (a dry-run over an unreadable table must not report a fake `would_create_link` plan either).

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -k "dry_run or block_table_read_failure" -q`
Expected: FAIL — `NotImplementedError` ("classify + apply lands in Task 5-6").

- [ ] **Step 3: Implement** — in `mcp_server/src/rook/merge_execution.py`, add the classify helpers above `execute_merge_contract`:

```python
async def _resolve_source(source_artifact_id: str):
    """(path, present). path is the normalized P6 path or None; present iff a P6 row exists
    and file_state == 'present'."""
    row = await asyncio.to_thread(
        lambda: _artifacts.artifact_registry().get(artifact_id=source_artifact_id))
    if row is None:
        return None, False
    return row.path, (row.file_state == "present")


def _observed_source_artifact_id(block_facts: dict, target_dir: str):
    """artifact id of an existing linked block's sourcePath; relative paths resolve against the
    target document's directory first. None when empty/unparseable."""
    raw = (block_facts or {}).get("sourcePath") or ""
    if not raw:
        return None
    try:
        p = raw if os.path.isabs(raw) else os.path.join(target_dir, raw)
        return _artifacts.artifact_id_for(_artifacts.normalize_path(p))
    except Exception:
        return None


async def _read_blocks(call_tool: CallTool):
    """Read the target document's block table ONCE. (by_name, None) on success — a SUCCESSFUL read
    of an empty table is {}; a FAILED read is fail-closed to (None, err) so a read failure is NEVER
    mistaken for 'no existing defs' (which would let mutation proceed past a failed pre-flight read)."""
    resp = await call_tool("rhino_blocks", {})
    if resp.get("success") is False:
        return None, _err("block_table_read_failed",
                          "Could not read the target document's block table; not mutating.")
    blocks = (resp.get("data") or {}).get("blocks") or []
    return {b.get("name"): b for b in blocks if isinstance(b, dict)}, None


async def _classify(by_name: dict, contract_id: str, sources, refresh_policy: str, target_dir: str):
    """Classify every source via the PURE planner over an already-read block snapshot. Returns the
    perSource list."""
    per_source = []
    for sid in sources:
        name = _lb.block_def_name(contract_id, sid)
        facts = by_name.get(name)
        src_path, present = await _resolve_source(sid)
        observed = _observed_source_artifact_id(facts, target_dir) if facts else None
        action = _lb.plan_source_action(
            block_facts=facts, expected_source_artifact_id=sid,
            observed_source_artifact_id=observed, source_present=present,
            refresh_policy=refresh_policy)
        per_source.append({
            "sourceArtifactId": sid, "blockName": name, "plannedAction": action,
            "sourcePath": src_path, "observedSourcePath": (facts or {}).get("sourcePath"),
            "observedSourceArtifactId": observed, "isLinked": (facts or {}).get("isLinked"),
            "blockType": (facts or {}).get("blockType")})
    return per_source


def _blockers_of(per_source):
    return [{"sourceArtifactId": e["sourceArtifactId"], "blockName": e["blockName"],
             "code": e["plannedAction"],
             "retryable": e["plannedAction"] == _lb.SOURCE_ARTIFACT_NOT_PRESENT}
            for e in per_source if e["plannedAction"] in _HARD_BLOCKERS]
```

Then replace the `raise NotImplementedError("classify + apply lands in Task 5-6")` with:

```python
        target_dir = os.path.dirname(active_path)
        by_name, berr = await _read_blocks(call_tool)   # fail closed on a failed pre-flight read
        if berr is not None:
            return berr
        per_source = await _classify(by_name, contract_id, sources, contract.refresh_policy, target_dir)
        blockers = _blockers_of(per_source)
        if dry_run:
            return {"success": True, "data": {
                "dryRun": True, "executable": (len(blockers) == 0),
                "blockers": blockers, "perSource": per_source}}
        # (Task 6 continues here: pre-flight gate, apply, re-verify, save.)
        raise NotImplementedError("apply + save lands in Task 6")
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -k "dry_run or block_table_read_failure" -q`
Expected: PASS (3 dry-run tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/merge_execution.py mcp_server/tests/test_merge_execution.py
git commit -m "feat(p7): merge_execution per-source classify + dry-run envelope"
```

---

## Task 6: Execute — pre-flight gate, apply, re-verify, save

**Files:**
- Modify: `mcp_server/src/rook/merge_execution.py`
- Test: `mcp_server/tests/test_merge_execution.py`

- [ ] **Step 1: Write the failing tests** — append to `mcp_server/tests/test_merge_execution.py`:

```python
def test_execute_full_success_creates_and_saves(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path=tgt_path, blocks=[])
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is True
    assert out["data"]["executed"] is True and out["data"]["saved"] is True
    assert out["data"]["perSource"][0]["outcome"] == lb.CREATED_LINK
    names = [n for n, _ in fake.calls]
    assert "rhino_block_link" in names and names[-1] == "rhino_document_ops"
    assert all(p == _PINNED for p in fake.seen_ports)


def test_execute_preflight_blocker_no_mutation(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    name = lb.block_def_name(cid, src_id)
    fake = FakeRhino(doc_path=tgt_path, blocks=[
        {"name": name, "isLinked": False, "sourcePath": "", "blockType": "Embedded"}])
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False
    assert out["data"]["code"] == "merge_contract_not_executable"
    assert out["data"]["blockers"][0]["code"] == lb.CONFLICT_NONLINKED
    assert "rhino_block_link" not in [n for n, _ in fake.calls]  # no mutation
    assert "rhino_document_ops" not in [n for n, _ in fake.calls]  # no save


def test_execute_save_failure(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path=tgt_path, blocks=[], save_ok=False)
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False
    assert out["data"]["code"] == "document_save_failed"
    assert out["data"]["executed"] is True and out["data"]["saved"] is False
    assert out["data"]["retryable"] is True  # Finding 4: failure envelopes carry retryable


def test_execute_mid_apply_failure(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    fake = FakeRhino(doc_path=tgt_path, blocks=[], link_ok=False)
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False
    assert out["data"]["code"] == "merge_contract_execution_incomplete"
    assert out["data"]["executed"] is False and out["data"]["saved"] is False
    assert out["data"]["retryable"] is True  # Finding 4: failure envelopes carry retryable
    assert out["data"]["perSource"][0]["outcome"] == lb.BLOCK_LINK_FAILED
    assert "rhino_document_ops" not in [n for n, _ in fake.calls]  # never saved


def test_execute_idempotent_rerun_already_linked(temp_registries, monkeypatch):
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(
        temp_registries, refresh="refresh_after_save")
    _pin_route(monkeypatch)
    name = lb.block_def_name(cid, src_id)
    # Source IS present (still registered); the def already exists, correctly linked.
    norm_src = artifacts.normalize_path(src_path)
    fake = FakeRhino(doc_path=tgt_path, blocks=[
        {"name": name, "isLinked": True, "sourcePath": norm_src, "blockType": "Linked"}])
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is True and out["data"]["saved"] is True
    assert out["data"]["perSource"][0]["outcome"] == lb.ALREADY_LINKED
    assert "rhino_block_link" not in [n for n, _ in fake.calls]  # no duplicate def


def test_execute_target_drift_before_save(temp_registries, monkeypatch):
    # Finding 4: pre-save drift (active doc changed under us) → target_document_mismatch, no save,
    # with executed:true/saved:false and an explicit retryable.
    cid, tgt_id, src_id, tgt_path, src_path = _make_contract(temp_registries)
    _pin_route(monkeypatch)
    # 1st rhino_document read == target (verify passes); 2nd (pre-save re-verify) drifts.
    fake = FakeRhino(doc_path=tgt_path, blocks=[], doc_path_after="C:/swapped-under-us.3dm")
    out = _run(merge_execution.execute_merge_contract(
        contract_id=cid, session="rhino-1", expected_merge_kind="linked_block",
        dry_run=False, call_tool=fake))
    assert out["success"] is False and out["data"]["code"] == "target_document_mismatch"
    assert out["data"]["executed"] is True and out["data"]["saved"] is False
    assert out["data"]["retryable"] is True
    assert "rhino_document_ops" not in [n for n, _ in fake.calls]  # never saved
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -k execute_ -q`
Expected: FAIL — `NotImplementedError` ("apply + save lands in Task 6").

- [ ] **Step 3: Implement** — in `mcp_server/src/rook/merge_execution.py`, add the apply helper above `execute_merge_contract`:

```python
async def _apply_one(call_tool: CallTool, entry: dict):
    """Mutate one source per its planned action; return the outcome string."""
    action, name = entry["plannedAction"], entry["blockName"]
    if action == _lb.ALREADY_LINKED:
        return _lb.ALREADY_LINKED
    if action == _lb.WOULD_CREATE_LINK:
        resp = await call_tool("rhino_block_link", {
            "path": entry["sourcePath"], "name": name,
            "updateType": "linked", "insertionPoint": [0, 0, 0]})
        return _lb.CREATED_LINK if resp.get("success") is not False else _lb.BLOCK_LINK_FAILED
    if action == _lb.WOULD_REFRESH_EXISTING:
        resp = await call_tool("rhino_block_refresh", {"name": name})
        return _lb.REFRESHED_EXISTING if resp.get("success") is not False else _lb.BLOCK_REFRESH_FAILED
    return action  # unreachable for an all-clear plan
```

Then replace the `raise NotImplementedError("apply + save lands in Task 6")` with:

```python
        # pre-flight gate — any hard blocker → no mutation, no save
        if blockers:
            return {"success": False, "data": {
                "code": "merge_contract_not_executable",
                "retryable": all(b["retryable"] for b in blockers),
                "blockers": blockers, "perSource": per_source}}
        # apply the all-clear plan, in deterministic source order
        for entry in per_source:
            entry["outcome"] = await _apply_one(call_tool, entry)
            if entry["outcome"] in (_lb.BLOCK_LINK_FAILED, _lb.BLOCK_REFRESH_FAILED):
                return _err("merge_contract_execution_incomplete",
                            "A block op failed mid-apply; the live target holds unsaved partial "
                            "changes (close-without-save discards them).",
                            executed=False, saved=False, perSource=per_source)
        # re-verify identity immediately before the save membrane
        recheck_path, rerr = await _read_active_doc_path(call_tool)
        if rerr is not None or _verify_target_identity(recheck_path, contract.target_artifact_id) is not None:
            return _err("target_document_mismatch",
                        "The active document changed before save; not saved.",
                        executed=True, saved=False, perSource=per_source)
        save = await call_tool("rhino_document_ops", {"action": "save", "path": active_path})
        if save.get("success") is False:
            return _err("document_save_failed",
                        "All links applied but the save failed; the live target holds complete "
                        "unsaved changes.",
                        executed=True, saved=False, perSource=per_source)
        return {"success": True, "data": {
            "executed": True, "saved": True, "perSource": per_source}}
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_execution.py -q`
Expected: PASS (all gate, session, dry-run, and execute tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/merge_execution.py mcp_server/tests/test_merge_execution.py
git commit -m "feat(p7): merge_execution apply + save membrane + result envelopes"
```

---

## Task 7: Server wiring — tool declaration + dispatch

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_work_units_tools.py`

- [ ] **Step 1: Write the failing test** — append to `mcp_server/tests/test_work_units_tools.py`:

```python
def test_call_tool_dispatches_execute_session_required(tmp_path, monkeypatch):
    # End-to-end through public call_tool: a non-routed tool that owns `session`, dispatching
    # to merge_execution; with no session it returns the executor's session_required.
    from rook import artifacts
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
    out = asyncio.run(server.call_tool(
        "rhino_merge_contract_execute",
        {"contractId": "mc-x", "expectedMergeKind": "linked_block"}))
    from rook.tool_result import parse_call_tool_data
    # session_required surfaces as a failure envelope → "Error: {...}"; parse it.
    text = out[0].text
    assert "session_required" in text
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py::test_call_tool_dispatches_execute_session_required -q`
Expected: FAIL — no dispatch case; `call_tool` returns an "unknown tool" error (no `session_required`).

- [ ] **Step 3: Implement** — two edits in `mcp_server/src/rook/server.py`.

(a) Add the `import` near the other rook imports (the dispatch already imports `work_units`; add `merge_execution`). Find the existing `from . import ... work_units ...` / module imports and add:

```python
from rook import merge_execution
```

(If imports are `from rook import work_units`-style, mirror it; if `from . import work_units`, use `from . import merge_execution`. Match the file's existing convention.)

(b) Declare the tool — in `list_tools`, immediately after the `Tool(name="rhino_planned_contracts", ...)` block:

```python
        Tool(
            name="rhino_merge_contract_execute",
            description="EXECUTE a strict linked_block merge contract into a Rhino document: ensure "
                        "each source artifact is a deterministic linked block in the target, then save. "
                        "Requires an explicit `session` whose active document IS the contract target "
                        "(verified); no ambient routing. Slice 4 supports merge_kind='linked_block' only; "
                        "other kinds return unsupported_merge_kind. `expectedMergeKind` is a required "
                        "caller-intent guard. dryRun=true previews per-source actions + blockers with no "
                        "mutation and no save. Idempotent; writes nothing durable.",
            inputSchema={"type": "object", "properties": {
                "contractId": {"type": "string"},
                "session": {"type": "string", "description": "rhino-<pid> from rhino_sessions"},
                "expectedMergeKind": {"type": "string",
                    "enum": ["worksession", "import", "linked_block", "reference", "block", "report"]},
                "dryRun": {"type": "boolean", "default": False}},
                "required": ["contractId", "session", "expectedMergeKind"]},
        ),
```

(c) Dispatch — in `_call_tool_dispatch`'s `match name:`, immediately after the `case "rhino_planned_contracts":` block:

```python
        case "rhino_merge_contract_execute":
            result = await merge_execution.execute_merge_contract(
                contract_id=arguments.get("contractId"),
                session=arguments.get("session"),
                expected_merge_kind=arguments.get("expectedMergeKind"),
                dry_run=bool(arguments.get("dryRun", False)),
                call_tool=_call_tool_dispatch)
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_work_units_tools.py mcp_server/tests/test_multi_instance_targeting.py -q`
Expected: PASS (dispatch test + `test_every_exposed_tool_has_policy_entry` now sees the declared tool with its policy).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_work_units_tools.py
git commit -m "feat(p7): wire rhino_merge_contract_execute tool decl + dispatch"
```

---

## Task 8: Held live smoke (HELD — needs Rhino)

**Files:**
- Create: `mcp_server/tests/test_merge_contract_execute_live.py`

- [ ] **Step 1: Write the live test** — create `mcp_server/tests/test_merge_contract_execute_live.py`:

```python
"""Live-Rhino end-to-end for the P7 linked-block executor. HELD: requires a running Rhino
with the #227 RookNative deployed. Skips cleanly when Rhino is unreachable (fresh_document).
Run (throwaway session):
    mcp_server\\.venv\\Scripts\\python.exe -m pytest -m requires_rhino ^
        mcp_server/tests/test_merge_contract_execute_live.py -s
IMPORTANT: replaces the active Rhino document; use a throwaway session.
"""
from __future__ import annotations
import os
import tempfile
import pytest

from rook import artifacts, work_units, linked_blocks as lb
from rook.server import _mcp_tool_executor
from .conftest import fresh_document  # noqa: F401

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _tmp(tag):
    return os.path.join(tempfile.gettempdir(), f"rook_p7exec_{os.getpid()}_{tag}.3dm")


async def _save_box_source(path):
    await _mcp_tool_executor("rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "srcbox"})
    s = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": path})
    assert s.get("success") is not False, f"save source failed: {s!r}"


async def _session_for_doc(target_path):
    """Select the session whose active document IS our target — the explicit-session contract.
    rhino_sessions entries carry a 'session' id (e.g. 'rhino-<pid>'); pick by document identity,
    NOT ordering ('first live' would be wrong on a multi-Rhino machine). A dead session won't
    return a matching doc, so the match also filters liveness implicitly."""
    sess = await _mcp_tool_executor("rhino_sessions", {})
    items = (sess.get("data") or {}).get("sessions") or sess.get("sessions") or []
    target_norm = artifacts.normalize_path(target_path)
    for s in items:
        sid = s.get("session") or s.get("sessionId") or s.get("id")
        if not sid:
            continue
        doc = await _mcp_tool_executor("rhino_document", {"session": sid})
        path = (doc.get("documentPath") or doc.get("path")
                or (doc.get("data") or {}).get("documentPath"))
        if path and artifacts.normalize_path(path) == target_norm:
            return sid
    raise AssertionError(f"no session's active doc == {target_path!r}; sessions={items!r}")


async def test_execute_linked_block_contract_end_to_end(fresh_document):
    src = _tmp("src")
    tgt = _tmp("tgt")
    try:
        # source doc
        await _save_box_source(src)
        # target doc (separate content), saved so it has a path
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        await _mcp_tool_executor("rhino_create",
            {"type": "BOX", "corner1": [5, 5, 0], "corner2": [6, 6, 1], "name": "tgtbox"})
        st = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": tgt})
        assert st.get("success") is not False

        rt = await artifacts.register_artifact(tgt)
        rs = await artifacts.register_artifact(src)
        tgt_id = rt["data"]["artifact"]["artifactId"]
        src_id = rs["data"]["artifact"]["artifactId"]
        rec = await work_units.record_merge_contract(
            target_artifact_id=tgt_id, source_artifact_ids=[src_id],
            merge_kind="linked_block", refresh_policy="refresh_on_demand")
        cid = rec["data"]["contractId"]
        session = await _session_for_doc(tgt)  # explicit-session contract: pick by document identity

        # dry-run: executable, would_create_link
        dry = await _mcp_tool_executor("rhino_merge_contract_execute",
            {"contractId": cid, "session": session, "expectedMergeKind": "linked_block", "dryRun": True})
        assert dry.get("dryRun") is True and dry.get("executable") is True, dry
        assert dry["perSource"][0]["plannedAction"] == lb.WOULD_CREATE_LINK

        # execute: creates + saves
        ex = await _mcp_tool_executor("rhino_merge_contract_execute",
            {"contractId": cid, "session": session, "expectedMergeKind": "linked_block"})
        assert ex.get("executed") is True and ex.get("saved") is True, ex
        assert ex["perSource"][0]["outcome"] == lb.CREATED_LINK

        # the linked def is present + correct
        name = lb.block_def_name(cid, src_id)
        info = await _mcp_tool_executor("rhino_block_info", {"name": name})
        assert info.get("isLinked") is True, info

        # idempotent re-run: refreshed_existing (refresh_on_demand), no duplicate
        ex2 = await _mcp_tool_executor("rhino_merge_contract_execute",
            {"contractId": cid, "session": session, "expectedMergeKind": "linked_block"})
        assert ex2.get("saved") is True, ex2
        assert ex2["perSource"][0]["outcome"] == lb.REFRESHED_EXISTING, ex2
    finally:
        for p in (src, tgt):
            try:
                os.remove(p)
            except OSError:
                pass
```

- [ ] **Step 2: Verify it collects (held — no Rhino run)**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_merge_contract_execute_live.py --collect-only -q`
Expected: collects `test_execute_linked_block_contract_end_to_end` with no import/collection errors.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_merge_contract_execute_live.py
git commit -m "test(p7): held live smoke for linked-block executor (requires_rhino)"
```

---

## Task 9: Full suite + baseline parity + finish branch

**Files:** none (verification only)

- [ ] **Step 1: Run the blessed non-Rhino gate**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no`
Expected: the new tests pass; PASS count rises by the tasks' additions.

- [ ] **Step 2: Baseline parity vs `main` (both directions)**

Capture named FAILED/ERROR sets on this branch and on `main`, then compare in BOTH directions (counts lie — #220 lesson):

```bash
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no | Select-String -Pattern "^(FAILED|ERROR)" | ForEach-Object { $_.Line } | Sort-Object | Set-Content branch.txt
git stash; git checkout main
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no | Select-String -Pattern "^(FAILED|ERROR)" | ForEach-Object { $_.Line } | Sort-Object | Set-Content main.txt
git checkout -; git stash pop
Compare-Object (Get-Content main.txt) (Get-Content branch.txt)
```

Expected: `Compare-Object` prints nothing (zero drift) — the branch introduces no new failures/errors vs `main` (baseline `64 failed / 41 errors`). (PowerShell shell; this is the established parity ritual.)

- [ ] **Step 3: Restore `knowledge/` before any commit if dirty**

```bash
git checkout -- knowledge/ ; if (Test-Path knowledge/selectors) { Remove-Item -Recurse -Force knowledge/selectors }
git status --short
```

Expected: only the intended source/test files are tracked changes; `knowledge/` clean.

- [ ] **Step 4: Finish the branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Then per that skill: verify tests, push the branch, open a PR for Codex review (the established bringfire/Rook flow), and let the user pull the squash-merge trigger:

```bash
git push -u origin feature/p7-linked-block-executor
gh pr create --title "P7 Slice 4: linked-block merge executor (rhino_merge_contract_execute)" --body "..."
```

(PR body ends with the `🤖 Generated with [Claude Code](https://claude.com/claude-code)` line; the live smoke is reported as gated evidence — run it on the dev machine before merge, or report it explicitly as Rhino-blocked.)

---

## Self-Review

**Spec coverage:** §3 tool contract → Task 7; §5 precondition ladder → Tasks 3–4; §6 planner → Task 1; §7 apply+save → Task 6; §8 session pin (`has_explicit_session=True` + `rhino_request_context`) → Task 4; §9 path identity → Tasks 4–5 (`_verify_target_identity`, `_observed_source_artifact_id`); §10/§11 envelopes+taxonomy → Tasks 3–6; §12 idempotency/present-bar → Tasks 1, 6; §13 four test layers → Tasks 1 (pure), 2 (policy), 3–6 (orchestrator), 8 (live); §14 no-native-build + parity + gated-live → Task 9; §3 Finding-1 policy → Task 2.

**Placeholder scan:** the `raise NotImplementedError(...)` markers in Tasks 3–5 are intentional, scoped scaffolding that the very next task replaces (each named for its successor); no `TODO`/`TBD`/"add validation" placeholders.

**Type consistency:** the planner constants (`lb.WOULD_CREATE_LINK`, `lb.CONFLICT_NONLINKED`, …) are defined in Task 1 and referenced identically in Tasks 5–6; `plan_source_action`'s keyword params match its callers in `_classify`; `execute_merge_contract`'s signature (`contract_id, session, expected_merge_kind, dry_run, call_tool`) matches the Task 7 dispatch call; envelope `code` strings match `_RETRYABLE` keys.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-07-p7-linked-block-executor.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
