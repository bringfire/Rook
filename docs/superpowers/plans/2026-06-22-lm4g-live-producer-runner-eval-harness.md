# LM4G Live Producer Runner / Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A behaviorally-pure, agent-layer record/eval harness that turns one `LiveProducerResult` (+ its returned graph) into a structured `LiveProducerRecord` with a self-explaining pass/fail verdict, plus a thin async wrapper that drives one producer node through a structural runner and records the result.

**Architecture:** New module `agent/plan_graph_live_runner.py` holds frozen dataclasses + a pure `build_live_producer_record` + a thin async `run_and_record_live_producer_node` over a structural `SupportsLiveProducerNode` Protocol. Pure unit tests fabricate `LiveProducerResult`s (no Rhino); one `requires_rhino` live test proves the wrapper records a real run. No kernel change, no `base_agent` import.

**Tech Stack:** Python 3.12, pytest (pure tests synchronous + `asyncio.run` for the wrapper test; live test uses pytest-asyncio via `pytestmark`), the existing `fresh_document` fixture, `rook.server._mcp_tool_executor`.

> **POST-REVIEW AMENDMENT (2026-06-22):** `tool_status` was added as a captured +
> evaluable field (`LiveProducerRecord.tool_status`, optional
> `LiveProducerExpectation.tool_status`, in `_EXPECTATION_FIELDS`, captured from
> `node.evidence.tool_status`). The broken-applied unit test asserts
> `tool_status == "failed"` and the multi-mismatch test exercises it; the clean
> unit test asserts `"success"`; not-applied tests assert `None`. The embedded code
> blocks below predate this one-field amendment — the merged module/tests are the
> source of truth. Counts unchanged (13 pure tests, focused gate 255).

## Global Constraints

- **One node only** — no selection, no successor advancement, no scheduler, no chat loop.
- **No kernel change** — no edit to `plan_graph_live.py`, `plan_graph_live_dispatch.py`, `base_agent.py`, or the pure `learning/` layer. Pure-consumer of `LiveProducerResult`.
- **Structural Protocol** — the wrapper's `runner` is typed `SupportsLiveProducerNode` (a `Protocol`); **no `from rook.agent.base_agent import RookAgent`**.
- **`_safe_declared_params` requires a `Mapping`** (mirrors LM4A's `execution_params_invalid` rule — no `dict()`-coercion of a non-Mapping) and is **non-throwing** (deepcopy failure → `None`, guarding the LM4A `params_copy_failed` alarm).
- **Read `result.graph`** (the returned fresh reducer copy), node looked up with `.get` — not-applied paths build a record, never crash.
- Record summarizes **captured evidence**, not raw transport payload. **JSON serialization is out of scope** (`declared_params` may hold non-JSON values).
- Module runtime imports: `from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult` + stdlib only (`dataclasses`, `copy`, `collections.abc.Mapping`, `typing`); learning types `TYPE_CHECKING`-only.
- **Diff guard:** final diff confined to the new module + `tests/test_plan_graph_live_runner.py` + `tests/test_live_producer_runner_live.py` + LM4G spec/plan. No `knowledge/**`, no edits to merged LM4 modules.
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Focused PlanGraph gate runs from the **repo root**.

---

### Task 1: Pure record/eval harness module + unit tests

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_live_runner.py`
- Test: `mcp_server/tests/test_plan_graph_live_runner.py`

**Interfaces:**
- Consumes: `LiveProducerResult` (frozen; fields `graph`, `applied`, `node_id`, `tool_name`, `outcome_status`, `reason`) and `EXECUTION_PARAMS_KEY` from `rook.agent.plan_graph_live`; `PlanGraph`, `PlanGraphNode`, `NodeEvidence` from `rook.learning.plan_graph` (node has `.status`, `.evidence`, `.metadata`).
- Produces: `LiveProducerExpectation`, `Mismatch`, `LiveProducerRecord` (frozen dataclasses); `SupportsLiveProducerNode` (Protocol); `build_live_producer_record(result, expectation=None) -> LiveProducerRecord`; `async run_and_record_live_producer_node(runner, graph, node_id, expectation=None) -> LiveProducerRecord`.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_live_runner.py`:

```python
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    LiveProducerRecord,
    Mismatch,
    build_live_producer_record,
    run_and_record_live_producer_node,
)
from rook.learning.plan_graph import NodeEvidence, PlanGraph, PlanGraphNode


def _evidence(tool_status="success", verified=True, artifact_status="usable", guid="guid-1"):
    return NodeEvidence(
        tool_status=tool_status,
        verified=verified,
        receipt={"artifact_status": artifact_status} if artifact_status else None,
        repair_anchor={"component_guid": guid} if guid else None,
    )


def _node(node_id="create", status="succeeded", evidence=None, params=None):
    meta = {}
    if params is not None:
        meta[EXECUTION_PARAMS_KEY] = params
    return PlanGraphNode(
        id=node_id, intent="create", metadata=meta, status=status, evidence=evidence
    )


def _result(applied, node_id="create", tool_name="gh_create_script",
            outcome_status="succeeded", reason=None, nodes=None):
    graph = PlanGraph(nodes=nodes if nodes is not None else {})
    return LiveProducerResult(
        graph=graph, applied=applied, node_id=node_id,
        tool_name=tool_name, outcome_status=outcome_status, reason=reason,
    )


class _Undeepcopyable:
    def __deepcopy__(self, memo):
        raise RuntimeError("cannot deepcopy")


class _FakeRunner:
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append((graph, node_id))
        return self._result


def test_clean_applied_record():
    node = _node(status="succeeded",
                 evidence=_evidence(verified=True, artifact_status="usable", guid="g1"),
                 params={"language": "csharp", "code": "A=1;"})
    rec = build_live_producer_record(_result(True, nodes={"create": node}))
    assert rec.applied is True
    assert rec.outcome_status == "succeeded"
    assert rec.node_status == "succeeded"
    assert rec.verified is True
    assert rec.artifact_status == "usable"
    assert rec.repair_anchor_guid == "g1"
    assert rec.tool_name == "gh_create_script"
    assert rec.declared_params == {"language": "csharp", "code": "A=1;"}
    assert rec.evaluated is False and rec.passed is None and rec.mismatches == ()


def test_broken_applied_record():
    node = _node(status="succeeded",
                 evidence=_evidence(tool_status="failed", verified=False,
                                    artifact_status="created_with_errors", guid="g2"))
    rec = build_live_producer_record(_result(True, nodes={"create": node}))
    assert rec.verified is False
    assert rec.artifact_status == "created_with_errors"
    assert rec.outcome_status == "succeeded"
    assert rec.node_status == "succeeded"


def test_not_applied_unknown_node_record():
    rec = build_live_producer_record(
        _result(False, node_id="missing", tool_name=None,
                outcome_status=None, reason="unknown_node", nodes={})
    )
    assert rec.applied is False
    assert rec.reason == "unknown_node"
    assert rec.node_status is None
    assert rec.verified is None
    assert rec.artifact_status is None
    assert rec.repair_anchor_guid is None
    assert rec.declared_params is None


def test_not_applied_node_present_evidence_none():
    node = _node(status="pending", evidence=None,
                 params={"language": "csharp", "code": "x"})
    rec = build_live_producer_record(
        _result(False, outcome_status=None, reason="node_not_runnable",
                nodes={"create": node})
    )
    assert rec.node_status == "pending"  # graph-native read
    assert rec.verified is None
    assert rec.artifact_status is None
    assert rec.repair_anchor_guid is None
    assert rec.reason == "node_not_runnable"
    assert rec.declared_params == {"language": "csharp", "code": "x"}


def test_not_applied_params_copy_failed_declared_params_none():
    node = _node(status="ready", evidence=None, params={"bad": _Undeepcopyable()})
    rec = build_live_producer_record(
        _result(False, outcome_status=None, reason="params_copy_failed",
                nodes={"create": node})
    )
    assert rec.reason == "params_copy_failed"
    assert rec.declared_params is None  # deepcopy failed -> None, no crash
    assert rec.node_status == "ready"


def test_non_mapping_execution_params_declared_params_none():
    node = _node(status="ready", evidence=None, params=[("language", "csharp")])
    rec = build_live_producer_record(
        _result(False, outcome_status=None, reason="execution_params_invalid",
                nodes={"create": node})
    )
    assert rec.declared_params is None
    assert rec.reason == "execution_params_invalid"


def test_eval_no_expectation():
    node = _node(evidence=_evidence())
    rec = build_live_producer_record(_result(True, nodes={"create": node}), None)
    assert rec.evaluated is False
    assert rec.passed is None
    assert rec.mismatches == ()


def test_eval_all_none_expectation_vacuous_pass():
    node = _node(evidence=_evidence())
    rec = build_live_producer_record(_result(True, nodes={"create": node}),
                                     LiveProducerExpectation())
    assert rec.evaluated is True
    assert rec.passed is True
    assert rec.mismatches == ()


def test_eval_single_mismatch():
    node = _node(status="succeeded", evidence=_evidence(verified=True, artifact_status="usable"))
    rec = build_live_producer_record(
        _result(True, outcome_status="succeeded", nodes={"create": node}),
        LiveProducerExpectation(verified=False),
    )
    assert rec.evaluated is True
    assert rec.passed is False
    assert rec.mismatches == (Mismatch(field="verified", expected=False, observed=True),)


def test_eval_multiple_mismatches():
    node = _node(status="succeeded", evidence=_evidence(verified=True, artifact_status="usable"))
    rec = build_live_producer_record(
        _result(True, outcome_status="succeeded", nodes={"create": node}),
        LiveProducerExpectation(verified=False, artifact_status="created_with_errors"),
    )
    assert rec.passed is False
    assert {m.field for m in rec.mismatches} == {"verified", "artifact_status"}


def test_declared_params_deepcopy_isolation():
    params = {"nested": {"k": "v"}}
    node = _node(evidence=_evidence(), params=params)
    rec = build_live_producer_record(_result(True, nodes={"create": node}))
    rec.declared_params["nested"]["k"] = "MUTATED"
    assert params["nested"]["k"] == "v"  # graph metadata untouched


def test_run_and_record_wrapper_uses_runner_result():
    node = _node(status="succeeded", evidence=_evidence(verified=True, artifact_status="usable"))
    g = PlanGraph(nodes={"create": node})
    result = LiveProducerResult(graph=g, applied=True, node_id="create",
                                tool_name="gh_create_script", outcome_status="succeeded", reason=None)
    runner = _FakeRunner(result)
    exp = LiveProducerExpectation(outcome_status="succeeded", node_status="succeeded",
                                  verified=True, artifact_status="usable")
    rec = asyncio.run(run_and_record_live_producer_node(runner, g, "create", exp))
    assert runner.calls == [(g, "create")]
    assert rec.evaluated is True and rec.passed is True and rec.mismatches == ()
    assert rec.artifact_status == "usable"
    assert isinstance(rec, LiveProducerRecord)


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_runner_module_import_boundary():
    # Repo-root-relative path -> run from repo root (the focused gate does).
    imports = _direct_import_modules(
        "mcp_server/src/rook/agent/plan_graph_live_runner.py"
    )
    # Consumes the live kernel for the type + key, nothing heavier.
    assert "rook.agent.plan_graph_live" in imports
    # Must NOT couple back into the agent runtime / dispatcher / server / chat.
    assert "rook.agent.base_agent" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.server" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.agent.plan_graph_live_dispatch" not in imports
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_live_runner.py -q`
Expected: collection error / `ModuleNotFoundError: rook.agent.plan_graph_live_runner` (the module does not exist yet).

- [ ] **Step 3: Write the module**

Create `mcp_server/src/rook/agent/plan_graph_live_runner.py`:

```python
"""LM4G one-node live producer runner / eval harness (Stage 5).

A downstream, behaviorally-PURE record/eval layer over ONE LiveProducerResult:
- build_live_producer_record(result, expectation) reads the RETURNED graph node
  (status + evidence) into a structured record and evaluates it against a
  declarative expectation (declared fields -> mismatches + pass/fail).
- run_and_record_live_producer_node(runner, graph, node_id, expectation) is a thin
  async wrapper: await runner.run_live_producer_node(...), then build the record.

Boundary: agent-layer (consumes LiveProducerResult) but NO I/O, no dispatcher, no
Rhino, no base_agent import. The runner arrives only as a structural Protocol. The
graph node's evidence is the canonical execution record -- no raw side channel.
One node only: no selection, no successor advancement, no scheduler.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


@dataclass(frozen=True)
class LiveProducerExpectation:
    applied: bool | None = None
    outcome_status: str | None = None
    node_status: str | None = None
    verified: bool | None = None
    artifact_status: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Mismatch:
    field: str
    expected: Any
    observed: Any


@dataclass(frozen=True)
class LiveProducerRecord:
    node_id: str
    tool_name: str | None
    applied: bool
    reason: str | None
    outcome_status: str | None
    node_status: str | None
    verified: bool | None
    artifact_status: str | None
    repair_anchor_guid: str | None
    declared_params: dict | None
    expectation: "LiveProducerExpectation | None"
    evaluated: bool
    passed: bool | None
    mismatches: tuple[Mismatch, ...]


class SupportsLiveProducerNode(Protocol):
    async def run_live_producer_node(
        self, graph: "PlanGraph", node_id: str
    ) -> LiveProducerResult: ...


_EXPECTATION_FIELDS = (
    "applied",
    "outcome_status",
    "node_status",
    "verified",
    "artifact_status",
    "reason",
)


def _safe_declared_params(node: Any) -> dict | None:
    """Best-effort declared-params capture; deep copy when possible, else None.
    NEVER raises. Mirrors LM4A's validity rule: a non-Mapping execution_params is
    execution_params_invalid, NOT declared params (do not dict()-coerce). A
    non-deepcopyable Mapping (the shape that makes LM4A return params_copy_failed)
    is swallowed to None rather than crashing the record."""
    if node is None:
        return None
    meta = getattr(node, "metadata", None)
    if not isinstance(meta, dict) or EXECUTION_PARAMS_KEY not in meta:
        return None
    params_source = meta[EXECUTION_PARAMS_KEY]
    if not isinstance(params_source, Mapping):
        return None
    try:
        return deepcopy(dict(params_source))
    except Exception:
        return None


def _artifact_status(evidence: Any) -> str | None:
    receipt = getattr(evidence, "receipt", None)
    if isinstance(receipt, dict):
        value = receipt.get("artifact_status")
        if isinstance(value, str):
            return value
    return None


def _repair_anchor_guid(evidence: Any) -> str | None:
    anchor = getattr(evidence, "repair_anchor", None)
    if isinstance(anchor, dict):
        value = anchor.get("component_guid")
        if isinstance(value, str) and value:
            return value
    return None


def _evaluate(
    observed: dict[str, Any], expectation: "LiveProducerExpectation | None"
) -> tuple[bool, bool | None, tuple[Mismatch, ...]]:
    if expectation is None:
        return False, None, ()
    mismatches: list[Mismatch] = []
    for field in _EXPECTATION_FIELDS:
        expected = getattr(expectation, field)
        if expected is None:
            continue
        actual = observed[field]
        if actual != expected:
            mismatches.append(Mismatch(field=field, expected=expected, observed=actual))
    return True, len(mismatches) == 0, tuple(mismatches)


def build_live_producer_record(
    result: LiveProducerResult,
    expectation: "LiveProducerExpectation | None" = None,
) -> LiveProducerRecord:
    """Build a structured record from ONE LiveProducerResult + its returned graph,
    then evaluate against an optional declarative expectation. Reads result.graph
    (the fresh reducer copy on applied paths); never crashes on not-applied /
    missing-node / non-copyable params."""
    node = result.graph.nodes.get(result.node_id)
    if node is None:
        node_status: str | None = None
        verified: bool | None = None
        artifact_status: str | None = None
        repair_anchor_guid: str | None = None
    else:
        node_status = node.status
        evidence = getattr(node, "evidence", None)
        verified = getattr(evidence, "verified", None) if evidence is not None else None
        artifact_status = _artifact_status(evidence)
        repair_anchor_guid = _repair_anchor_guid(evidence)

    observed = {
        "applied": result.applied,
        "outcome_status": result.outcome_status,
        "node_status": node_status,
        "verified": verified,
        "artifact_status": artifact_status,
        "reason": result.reason,
    }
    evaluated, passed, mismatches = _evaluate(observed, expectation)

    return LiveProducerRecord(
        node_id=result.node_id,
        tool_name=result.tool_name,
        applied=result.applied,
        reason=result.reason,
        outcome_status=result.outcome_status,
        node_status=node_status,
        verified=verified,
        artifact_status=artifact_status,
        repair_anchor_guid=repair_anchor_guid,
        declared_params=_safe_declared_params(node),
        expectation=expectation,
        evaluated=evaluated,
        passed=passed,
        mismatches=mismatches,
    )


async def run_and_record_live_producer_node(
    runner: SupportsLiveProducerNode,
    graph: "PlanGraph",
    node_id: str,
    expectation: "LiveProducerExpectation | None" = None,
) -> LiveProducerRecord:
    """Thin live wrapper: drive ONE producer node through the runner, then record +
    evaluate. One node only -- no selection, no successor advancement, no
    scheduler."""
    result = await runner.run_live_producer_node(graph, node_id)
    return build_live_producer_record(result, expectation)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_live_runner.py -q`
Expected: `13 passed` (12 functional + the AST import-boundary test). Run from the **repo root** so the AST test's repo-root-relative path resolves.

- [ ] **Step 5: Run the full focused PlanGraph gate**

Run from repo root:
```powershell
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
(bash equivalent: `files=$(ls mcp_server/tests/test_plan_graph*.py); mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider $files -q`)
Expected: `255 passed` (the prior 242 + the 13 new pure tests; `test_plan_graph_live_runner.py` matches the glob).

- [ ] **Step 6: `py_compile` + import-boundary check**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/plan_graph_live_runner.py mcp_server/tests/test_plan_graph_live_runner.py`
Expected: exit 0.

Then confirm the module imports nothing forbidden (the AST test in Step 1 already
pins this; this is a quick manual cross-check). PowerShell:
```powershell
Select-String -Path mcp_server/src/rook/agent/plan_graph_live_runner.py `
  -Pattern 'base_agent|tool_dispatcher|rook\.server|rook\.agent\.chat|bridge|httpx|call_rhino'
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/agent/plan_graph_live_runner.py mcp_server/tests/test_plan_graph_live_runner.py
git commit -m "feat(lm4g): pure one-node live producer record/eval harness"
```
(Body: agent-layer pure build_live_producer_record + thin run_and_record wrapper over a structural Protocol; declarative expectation -> evaluated/passed/mismatches; _safe_declared_params Mapping-only + non-throwing; reads result.graph; one node, no scheduler, no base_agent import. End with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.)

---

### Task 2: Clean-path live test + diff guard

**Files:**
- Create: `mcp_server/tests/test_live_producer_runner_live.py`

**Interfaces:**
- Consumes: `run_and_record_live_producer_node`, `LiveProducerExpectation` (Task 1); `RookAgent`, `_mcp_tool_executor`, `EXECUTION_PARAMS_KEY`, `OUTCOME_PROJECTION_ROLE_KEY`, `PlanGraph`, `PlanGraphNode`; the `fresh_document` fixture (`conftest.py`).
- Produces: nothing downstream (terminal slice).

- [ ] **Step 1: Write the live test**

Create `mcp_server/tests/test_live_producer_runner_live.py`:

```python
"""LM4G — clean-path live proof that the runner/eval harness records a real run.

ONE opt-in requires_rhino test: drive a clean producer node through
run_and_record_live_producer_node against the live gh_create_script tool and
assert the produced record + verdict. The broken/two-successes live seam is
already carried by LM4E; the exhaustive eval/not-applied matrix is in the pure
unit tests (test_plan_graph_live_runner.py).

Named OUTSIDE the test_plan_graph* glob so it stays out of the focused gate.

Run (from repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_producer_runner_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    run_and_record_live_producer_node,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

NODE_ID = "create"


def _producer_graph() -> PlanGraph:
    node = PlanGraphNode(
        id=NODE_ID,
        intent="Create C# script via LM4G live runner",
        execution_ref="gh_create_script",
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: {
                "language": "csharp",
                "code": "A = Convert.ToDouble(R) * 2.0;",
                "pins_in": ["R:double"],
                "pins_out": ["A:double"],
                "name": "LM4GRunnerLive",
                "x": 360,
                "y": 980,
            },
        },
    )
    graph = PlanGraph(nodes={NODE_ID: node})
    node.status = "ready"
    return graph


async def test_run_and_record_clean_node_records_and_passes(fresh_document):
    agent = RookAgent(tool_executor=_mcp_tool_executor)
    expectation = LiveProducerExpectation(
        outcome_status="succeeded",
        node_status="succeeded",
        verified=True,
        artifact_status="usable",
    )

    record = await run_and_record_live_producer_node(
        agent, _producer_graph(), NODE_ID, expectation
    )

    # Assert the RECORD, not the implementation.
    assert record.evaluated is True
    assert record.passed is True
    assert record.mismatches == ()
    assert record.artifact_status == "usable"
    assert record.node_status == "succeeded"
    assert record.verified is True
    assert record.tool_name == "gh_create_script"
```

- [ ] **Step 2: `py_compile` + prove CI-safety**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tests/test_live_producer_runner_live.py`
Expected: exit 0.

Deselection (normal CI excludes it):
`mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_live_producer_runner_live.py -m "not requires_rhino"`
Expected: `1 deselected`.

Skip-safety (run without `-m`; with Rhino down it skips, not fails):
`mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_live_producer_runner_live.py -q`
Expected: `1 skipped` when Rhino is unreachable. (If Rhino+GH are up it instead runs live — also acceptable; the requirement is no error/hard-fail. The live `1 passed` is captured in Step 3.)

- [ ] **Step 3: Live acceptance — run WITH Rhino + Grasshopper open**

Requires a throwaway Rhino session with Rook loaded **and Grasshopper open with an active document** (Rhino-alone returns `grasshopper_not_ready` → the test fails, not skips). If not reachable in-session, mark this step deferred-to-operator and record that Steps 2 proved CI-safety.

Run (from repo root): `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider -m requires_rhino mcp_server/tests/test_live_producer_runner_live.py -v`
Expected: `1 passed`.

- [ ] **Step 4: Diff guard — confined scope**

Run: `git add -A`
Then: `git diff --cached --name-only main`
Expected EXACTLY these five paths and no others:
- `mcp_server/src/rook/agent/plan_graph_live_runner.py`
- `mcp_server/tests/test_plan_graph_live_runner.py`
- `mcp_server/tests/test_live_producer_runner_live.py`
- `docs/superpowers/specs/2026-06-22-lm4g-live-producer-runner-eval-harness-design.md`
- `docs/superpowers/plans/2026-06-22-lm4g-live-producer-runner-eval-harness.md`

Confirm **no `knowledge/`** path and **no edits to merged LM4 modules**. Use an
**exact-path** guard (substring matching would false-positive on the new
`plan_graph_live_runner.py`). PowerShell:
```powershell
$changed = git diff --cached --name-only main
$forbidden = $changed | Where-Object {
  $_ -like 'knowledge/*' -or
  $_ -eq 'mcp_server/src/rook/agent/plan_graph_live.py' -or
  $_ -eq 'mcp_server/src/rook/agent/plan_graph_live_dispatch.py' -or
  $_ -eq 'mcp_server/src/rook/agent/base_agent.py' -or
  $_ -eq 'mcp_server/src/rook/learning/plan_graph_outcomes.py'
}
if ($forbidden) { $forbidden; exit 1 } else { 'OK: no forbidden paths' }
```
Expected: `OK: no forbidden paths`. If `knowledge/gh/operations_knowledge.json` appears (runtime mutation), `git restore` it before committing.

- [ ] **Step 5: Commit**

```bash
git commit -m "test(lm4g): clean-path live proof of the runner/eval harness"
```
(Body: one requires_rhino test driving run_and_record_live_producer_node against live gh_create_script clean body, asserting record evaluated/passed/usable/succeeded; CI-deselected + skip-safe; test-only. End with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.)

## Self-Review

- **Spec coverage:** module + dataclasses + Protocol + pure builder + thin wrapper (Task 1 Step 3); `_safe_declared_params` Mapping-only + non-throwing (Step 3, tests 5/5b/6 → mapped to `test_not_applied_params_copy_failed...` and `test_non_mapping_execution_params...`); capture from `result.graph` with not-applied guards (tests 3/4); eval matrix incl. `evaluated` flag (tests 7–10); declared-params deep-copy isolation (test 10); wrapper over structural Protocol with fake runner (test 11); AST import-boundary test pinning no base_agent/dispatcher/server/chat coupling (test 13); one clean live test (Task 2). Verification gates: focused gate 255, py_compile, exact-path diff guard, deselection/skip. All present.
- **Placeholder scan:** none — every code/command step is concrete.
- **Type consistency:** `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)`; `NodeEvidence(tool_status, verified, receipt, repair_anchor, ...)`; `PlanGraphNode(id, intent, metadata, status, evidence)`; record/expectation/mismatch field names match between module and tests; `build_live_producer_record` / `run_and_record_live_producer_node` / `LiveProducerExpectation` / `Mismatch` used identically in module, unit tests, and live test.
