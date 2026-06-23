# LM4H Live Producer → Verifier Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the first explicit live graph handoff — one live producer run's captured evidence drives one pure verifier step, advancing the registered 3-node template through `requires`/`on_repair` edges to unlock repair — with two new test files and no production code.

**Architecture:** Test-only composition over already-merged seams. A pure CI guard constructs producer-applied state through the reducer (`apply_outcome`) on the registered `gh_csharp_create_verify_repair` template and composes LM4G's `build_live_producer_record` with LM3E's `apply_verifier_step`. A `requires_rhino` live proof drives a real `RookAgent` through `run_live_producer_node` against `gh_create_script`, then the same verifier step over the live producer graph.

**Tech Stack:** Python 3.12, pytest (+ `pytest-asyncio`, `requires_rhino` marker), Rook MCP/agent/learning packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

- **No production code.** Only two new test files (plus this plan + the already-committed spec). Touch no `src/` module.
- **Diff guard — exactly these four paths:** `mcp_server/tests/test_plan_graph_live_handoff.py`, `mcp_server/tests/test_live_producer_verifier_handoff_live.py`, `docs/superpowers/specs/2026-06-22-lm4h-live-producer-verifier-handoff-design.md` (already committed), `docs/superpowers/plans/2026-06-22-lm4h-live-producer-verifier-handoff.md` (this plan).
- **Never stage/commit `knowledge/gh/operations_knowledge.json`** — it mutates only on live runs; `git restore` it after any live acceptance pass.
- **Both tests assert `create_script.execution_ref == "gh_create_csharp_script:v1"` before any mutation.** The live test overrides only the producer *dispatch* ref to `gh_create_script`, on a cloned graph; the registry/template definition is never mutated.
- **Broken body is `A = DefinitelyMissingSymbol;`** — empirically `created_with_errors` on RhinoCode 8.33; `B = new Box();` does not error on this build.
- **Boundary:** producer → verifier only. Stop at `repair_same_component.status == "ready"`. No repair dispatch, no scheduler, no chain runner.
- **LM4H does not prove `gh_create_csharp_script` live dispatch compatibility** (separate future slice).
- **Run from repo root** (`C:\UDEV\Rook`) with the venv interpreter `mcp_server\.venv\Scripts\python.exe`.

**Seam reference (do not modify — consume only):**
- `select_template(descriptor) -> TemplateSelection` — `rook.learning.plan_graph_templates`; fields `.selected_template_id`, `.graph` (`.graph` may be `None`).
- `apply_outcome(graph, node_id, NodeOutcome) -> PlanGraph` — `rook.learning.plan_graph`; sets node status + evidence, unlocks matching pending edge targets. Does NOT gate on the source node's prior status.
- `NodeEvidence(tool_status, verified, receipt, repair_anchor, message, error)` and `NodeOutcome(status, evidence, ...)` — `rook.learning.plan_graph`. `NodeOutcome.status` must be an outcome state (`succeeded`/`needs_repair`/etc.; not `pending`/`ready`/`running`).
- `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)` — `rook.agent.plan_graph_live` (frozen).
- `LiveProducerExpectation(applied, outcome_status, node_status, tool_status, verified, artifact_status, reason)` and `build_live_producer_record(result, expectation) -> LiveProducerRecord` — `rook.agent.plan_graph_live_runner`. Record fields used: `.evaluated`, `.passed`, `.mismatches`, `.tool_status`, `.outcome_status`, `.node_status`, `.verified`, `.artifact_status`.
- `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult` — `rook.learning.plan_graph_runner`; fields `.applied`, `.outcome_status`, `.graph`.
- `RookAgent(tool_executor=...).run_live_producer_node(graph, node_id) -> LiveProducerResult` — `rook.agent.base_agent` (LM4D).
- `_mcp_tool_executor` — `rook.server`. `EXECUTION_PARAMS_KEY == "execution_params"` — `rook.agent.plan_graph_live`.
- `fresh_document` fixture — `mcp_server/tests/conftest.py`; resets the Rhino doc, `pytest.skip`s when Rhino is unreachable.

**TDD note for a test-only slice:** there is no production code to drive red→green. Each test is expected to pass *immediately* over the existing seams. A failure is a real finding about seam behavior (e.g., the verifier does not map `created_with_errors → needs_repair`, or `runnable_nodes` excludes the unlocked node) — investigate and report it, do not patch the test to be green.

---

### Task 1: Pure composition guard (focused-gate CI contract)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_live_handoff.py`

**Interfaces:**
- Consumes: `select_template`, `apply_outcome`, `NodeEvidence`, `NodeOutcome`, `LiveProducerResult`, `LiveProducerExpectation`, `build_live_producer_record`, `apply_verifier_step` (all per the seam reference above).
- Produces: nothing consumed by Task 2 (independent test file). Named `test_plan_graph_live_handoff.py` so it lands in the `test_plan_graph*` focused gate.

- [ ] **Step 1: Write the pure guard test file**

Create `mcp_server/tests/test_plan_graph_live_handoff.py` with exactly this content:

```python
"""LM4H pure composition guard — CI contract over the live producer→verifier handoff.

Constructs producer-applied state through `apply_outcome` (SYNTHETIC evidence, not
live capture) on the registered 3-node gh_csharp_create_verify_repair template,
proves the requires-edge unlock into verify_create, then composes LM4G's record
builder with LM3E's verifier step and asserts the on_repair unlock into repair.

This is a composition contract: the registered template topology + LM4G record
builder + LM3E verifier step still compose as LM4H expects. It is NOT a live-capture
proof — the live truth is test_live_producer_verifier_handoff_live.py.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import NodeEvidence, NodeOutcome, apply_outcome
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair",
    "language": "csharp",
}


def _broken_producer_evidence() -> NodeEvidence:
    """Synthetic evidence mirroring a live created_with_errors capture shape."""
    return NodeEvidence(
        tool_status="failed",
        verified=False,
        receipt={"artifact_status": "created_with_errors"},
        repair_anchor={"component_guid": "pure-guard-guid"},
    )


def test_live_handoff_composition_contract():
    # Registry path + template contract pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"

    # Construct producer-applied state THROUGH the reducer (proves requires unlock).
    applied = apply_outcome(
        graph,
        "create_script",
        NodeOutcome(status="succeeded", evidence=_broken_producer_evidence()),
    )
    assert applied.nodes["create_script"].status == "succeeded"
    assert applied.nodes["verify_create"].status == "ready"  # requires-edge unlock

    # LM4G record builder over the graph-bearing synthetic result.
    result = LiveProducerResult(
        graph=applied,
        applied=True,
        node_id="create_script",
        tool_name="gh_create_script",
        outcome_status="succeeded",
        reason=None,
    )
    expectation = LiveProducerExpectation(
        outcome_status="succeeded",
        node_status="succeeded",
        tool_status="failed",
        verified=False,
        artifact_status="created_with_errors",
    )
    record = build_live_producer_record(result, expectation)
    assert record.evaluated is True
    assert record.passed is True, f"mismatches={record.mismatches!r}"
    assert record.tool_status == "failed"
    assert record.artifact_status == "created_with_errors"

    # LM3E verifier step over the producer evidence -> on_repair unlock.
    verifier_step = apply_verifier_step(applied, "verify_create", "create_script")
    assert verifier_step.applied is True
    assert verifier_step.outcome_status == "needs_repair"
    assert verifier_step.graph.nodes["verify_create"].status == "needs_repair"
    assert verifier_step.graph.nodes["repair_same_component"].status == "ready"
```

- [ ] **Step 2: Run the pure guard and confirm it passes green over existing seams**

Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_plan_graph_live_handoff.py -v
```
Expected: `1 passed`.

If it fails, it is a real seam finding — read the assertion that failed:
- `verify_create` not `ready` after `apply_outcome` → the `requires`-edge unlock or `_requires_satisfied` does not behave as the spec assumes.
- `record.passed` False → inspect `record.mismatches`; the LM4G builder read a different field than expected.
- `verifier_step.outcome_status != "needs_repair"` → `script_receipt_verifier_outcome` does not map `created_with_errors → needs_repair`.
- `repair_same_component` not `ready` → the `on_repair` edge did not unlock.
Report the finding; do not weaken the test to force green.

- [ ] **Step 3: Confirm the diff guard (only the new file is changed)**

Run:
```
git status --short
```
Expected: exactly `?? mcp_server/tests/test_plan_graph_live_handoff.py` (plus this plan if not yet committed). Confirm `knowledge/gh/operations_knowledge.json` is NOT listed.

- [ ] **Step 4: Commit**

```
git add mcp_server/tests/test_plan_graph_live_handoff.py
git commit -m "test(lm4h): pure composition guard for live producer→verifier handoff"
```

---

### Task 2: Live proof (`requires_rhino`)

**Files:**
- Create: `mcp_server/tests/test_live_producer_verifier_handoff_live.py`

**Interfaces:**
- Consumes: `select_template`, `RookAgent`, `EXECUTION_PARAMS_KEY`, `LiveProducerExpectation`, `build_live_producer_record`, `apply_verifier_step`, `_mcp_tool_executor`, `fresh_document` fixture (all per the seam reference).
- Produces: nothing. Named OUTSIDE the `test_plan_graph*` glob so it stays out of the focused gate; `requires_rhino` keeps it out of normal CI.

- [ ] **Step 1: Write the live proof test file**

Create `mcp_server/tests/test_live_producer_verifier_handoff_live.py` with exactly this content:

```python
"""LM4H live proof — real captured producer evidence drives the verifier handoff.

Drives a real RookAgent(_mcp_tool_executor) through run_live_producer_node against
the live gh_create_script tool on the registered 3-node gh_csharp_create_verify_repair
template, then hands the graph-bearing LiveProducerResult to LM3E's apply_verifier_step
and asserts the on_repair unlock into repair_same_component.

The slice's only live variable is the handoff. The live test overrides ONLY the
producer dispatch ref to the LM4E/LM4G-proven gh_create_script — it does NOT prove
gh_create_csharp_script live dispatch compatibility (a separate future slice). The
registered gh_create_csharp_script:v1 ref is asserted before the override so the
override is deliberate and template drift is caught.

requires_rhino: deselected from normal CI; fresh_document skips when Rhino is
unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_producer_verifier_handoff_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair",
    "language": "csharp",
}


async def test_live_producer_evidence_drives_verifier_handoff(fresh_document):
    # Registry path + template contract pinned before the deliberate override.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"

    # LM4H overrides ONLY the producer dispatch ref to reuse the proven
    # gh_create_script contract. It does NOT prove gh_create_csharp_script live.
    graph.nodes["create_script"].execution_ref = "gh_create_script"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "language": "csharp",
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4HHandoffLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)
    producer_result = await agent.run_live_producer_node(graph, "create_script")

    # Durable producer record (LM4G) — the two-successes seam, live.
    expectation = LiveProducerExpectation(
        outcome_status="succeeded",
        node_status="succeeded",
        tool_status="failed",
        verified=False,
        artifact_status="created_with_errors",
    )
    producer_record = build_live_producer_record(producer_result, expectation)
    assert producer_record.evaluated is True
    assert producer_record.passed is True, f"mismatches={producer_record.mismatches!r}"
    assert producer_record.tool_status == "failed"
    assert producer_record.outcome_status == "succeeded"
    assert producer_record.node_status == "succeeded"
    assert producer_record.verified is False
    assert producer_record.artifact_status == "created_with_errors"

    # Handoff on producer_result.graph BEFORE the verifier step.
    assert producer_result.graph.nodes["create_script"].status == "succeeded"
    assert producer_result.graph.nodes["verify_create"].status == "ready"

    # LM3E verifier step over LIVE producer evidence -> on_repair unlock.
    verifier_step = apply_verifier_step(
        producer_result.graph, "verify_create", "create_script"
    )
    assert verifier_step.applied is True
    assert verifier_step.outcome_status == "needs_repair"
    assert verifier_step.graph.nodes["verify_create"].status == "needs_repair"
    assert verifier_step.graph.nodes["repair_same_component"].status == "ready"
```

- [ ] **Step 2: Collection / skip-safety check**

Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_live_producer_verifier_handoff_live.py -v
```
Expected: either `1 skipped` (when Rhino is down — the `fresh_document` fixture skips) OR `1 passed` (when Rhino + Grasshopper happen to be open and the live path runs). Both outcomes are acceptable here; what must NOT happen is a collection `error` or a `failed` — those mean an import or marker problem, fix it before committing. The authoritative live proof remains Step 5 with `-m requires_rhino`.

- [ ] **Step 3: Confirm the diff guard**

Run:
```
git status --short
```
Expected: exactly `?? mcp_server/tests/test_live_producer_verifier_handoff_live.py` (plus this plan if not yet committed). Confirm `knowledge/gh/operations_knowledge.json` is NOT listed.

- [ ] **Step 4: Commit**

```
git add mcp_server/tests/test_live_producer_verifier_handoff_live.py
git commit -m "test(lm4h): live proof — captured producer evidence drives verifier handoff"
```

- [ ] **Step 5: Live acceptance (run only with Rhino + Grasshopper open)**

This step is the authoritative live proof and is run during a live acceptance pass (Rhino + Grasshopper open, Rook loaded), not in normal CI. Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_producer_verifier_handoff_live.py -v
```
Expected: `1 passed`. The live run creates a `LM4HHandoffLive` C# component on the canvas and mutates `knowledge/gh/operations_knowledge.json`.

After the live run, restore the runtime mutation (never commit it):
```
git restore knowledge/gh/operations_knowledge.json
git status --short
```
Expected after restore: clean (or only intended files). If the live run failed, capture the exact assertion + the `producer_record.mismatches` / node statuses and report — do not adjust the test to pass.

---

## Final verification (whole-branch)

- [ ] **Focused gate green (Rhino-independent):** from repo root, run the focused PlanGraph gate including the new pure guard. PowerShell does not expand `test_plan_graph*.py`, so enumerate the files explicitly (proven command):
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_live_handoff.py` (gate count rises from the LM4G baseline of 255).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly the four allowed paths (spec, plan, two test files) and nothing else — especially not `operations_knowledge.json` or any `src/` module.

## Self-Review

**Spec coverage:**
- Goal / first explicit handoff → Tasks 1 + 2.
- D1 boundary (producer→verifier, stop at repair `ready`) → both tests stop at `repair_same_component.status == "ready"`.
- D2 seam (pure builder + graph-bearing result) → live test uses `run_live_producer_node` + `build_live_producer_record` + `apply_verifier_step` over `producer_result.graph`.
- D3 test surface (live + pure guard) → Task 1 (pure, in gate) + Task 2 (live).
- D4 ref override → live test asserts `gh_create_csharp_script:v1` then overrides to `gh_create_script` on the cloned graph.
- D5 broken body → `A = DefinitelyMissingSymbol;` in the live test.
- D6 unlock via `apply_outcome` → Task 1 Step 1 uses `apply_outcome(NodeOutcome("succeeded", ...))` and asserts `verify_create.ready`.
- Pure guard verbatim ref assertion → Task 1 asserts `gh_create_csharp_script:v1`.
- Non-goals (no production code, no repair dispatch, no scheduler, defer `gh_create_csharp_script` compat) → Global Constraints + no `src/` edits.
- Diff guard / `operations_knowledge.json` restore → Global Constraints + Task 1 Step 3, Task 2 Steps 3 & 5.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `select_template` → `.selected_template_id`/`.graph`; `apply_outcome(graph, node_id, NodeOutcome)`; `NodeEvidence`/`NodeOutcome`/`LiveProducerResult`/`LiveProducerExpectation` field names match the seam reference and the merged modules; `apply_verifier_step(graph, verifier_node_id, source_node_id)` argument order matches `plan_graph_runner.py`. Consistent across both tasks.
