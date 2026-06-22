# LM4E Live Producer Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two opt-in, one-node `requires_rhino` smokes that drive a real `RookAgent(tool_executor=_mcp_tool_executor)` through `agent.run_live_producer_node` against the live `gh_create_script` tool, proving the receipt travels the production executor seam and projects correctly by role — including the live "two successes" seam (a `success:False` envelope still drives an `artifact_producer` node to `succeeded`).

**Architecture:** One test-only module under `mcp_server/tests/`. It constructs a real agent wired to the production MCP executor, builds a single `artifact_producer` PlanGraph node whose `execution_ref` is `gh_create_script` and whose `execution_params` are the real tool arguments, awaits `run_live_producer_node`, and asserts the outcome + the captured `NodeEvidence` read off `result.graph.nodes[NODE_ID].evidence`. No production code changes.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio (live-test convention: `pytestmark = [requires_rhino, asyncio]`), the existing `fresh_document` graceful-skip fixture, `rook.server._mcp_tool_executor`.

## Global Constraints

- **Test-only slice.** No change under `mcp_server/src/**`. `base_agent.py`, `plan_graph_live*.py`, `server.py`, and the pure `learning/plan_graph_*` layer stay unchanged.
- **Two independent one-node smokes.** No scheduler, no chain advancement, no chat-loop integration, no helper/CLI extraction.
- **Executor:** inject `_mcp_tool_executor` into a real `RookAgent` — `RookAgent(tool_executor=_mcp_tool_executor)`. NOT a bare `RookAgent()` / auto-built `ToolDispatcher`.
- **Evidence** is read off `result.graph.nodes[NODE_ID].evidence`.
- **Broken-C# body** is exactly `B = new Box();` with `pins_out=["B:Brep"]` (grounded post-create compile error, `test_server_contract_hardening.py:559`). NOT a syntax-error body.
- **Skip-safety:** the module uses `fresh_document` so it skips cleanly when Rhino is unreachable, and is deselected from normal CI via `-m "not requires_rhino"`.
- **Producer hinge (must not regress):** broken C# under `artifact_producer` projects to `succeeded` / `verified=False`, NOT `needs_repair`.
- Live-test runner (from repo root, Rhino up): `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider -m requires_rhino mcp_server/tests/test_base_agent_live_producer_live.py`.

---

### Task 1: Live producer smoke module (both tests + fixture + all gates)

This is a single right-sized task: one small test-only file. A reviewer reviews the whole module at once. All verification gates are folded in as steps.

**Files:**
- Create: `mcp_server/tests/test_base_agent_live_producer_live.py`

**Interfaces:**
- Consumes:
  - `RookAgent(tool_executor=...)` and `agent.run_live_producer_node(graph, node_id) -> LiveProducerResult` (`mcp_server/src/rook/agent/base_agent.py:1192`). `LiveProducerResult` fields: `.graph`, `.applied`, `.node_id`, `.tool_name`, `.outcome_status`, `.reason`.
  - `_mcp_tool_executor(name, params)` async callable (`from rook.server import _mcp_tool_executor`).
  - `PlanGraph`, `PlanGraphNode` (`from rook.learning.plan_graph import ...`); node carries `.status` and `.evidence` (a `NodeEvidence` with `.tool_status`, `.verified`, `.receipt`, `.repair_anchor`).
  - `EXECUTION_PARAMS_KEY` (`from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY`).
  - `OUTCOME_PROJECTION_ROLE_KEY` (`from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY`).
  - `fresh_document` fixture (`mcp_server/tests/conftest.py:115`) — graceful skip + blank Rhino doc.
- Produces: nothing consumed by later tasks (terminal slice).

- [ ] **Step 1: Write the full live smoke module**

Create `mcp_server/tests/test_base_agent_live_producer_live.py` with exactly this content:

```python
"""LM4E — opt-in live producer smoke (Stage 5).

Drives a REAL RookAgent wired to the production MCP executor through
`agent.run_live_producer_node` against the live `gh_create_script` tool, proving
the receipt travels the production executor seam and projects correctly by role.

Two independent ONE-NODE smokes:
  1. clean component  -> artifact_status "usable"          -> producer succeeded
  2. B = new Box()    -> success:False + "created_with_errors" (created but bad)
                      -> producer STILL succeeded / verified False  (the live
                         "two successes" seam; `needs_repair` here would mean the
                         producer projection was bypassed for conservative/
                         direct-task semantics)

Test-only: no production code is touched. `requires_rhino` keeps the module out
of normal CI by deselection; `fresh_document` makes it skip cleanly when Rhino is
unreachable.

Run (from repo root, with Rhino open and Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_base_agent_live_producer_live.py

IMPORTANT: the `fresh_document` fixture REPLACES the active Rhino document. Run in
a throwaway Rhino session.
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


NODE_ID = "create_script"
GH_CREATE_SCRIPT = "gh_create_script"


def _producer_graph(declared_params: dict) -> PlanGraph:
    """One ready `artifact_producer` node whose execution_ref is the real tool."""
    node = PlanGraphNode(
        id=NODE_ID,
        intent="Create C# script component via RookAgent live producer method",
        execution_ref=GH_CREATE_SCRIPT,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={NODE_ID: node})
    node.status = "ready"
    return graph


async def test_clean_component_live_producer_succeeds(fresh_document):
    """Live happy path: a valid C# component -> artifact_status 'usable' ->
    the producer node projects to succeeded / verified True."""
    declared_params = {
        "language": "csharp",
        "code": "A = Convert.ToDouble(R) * 2.0;",
        "pins_in": ["R:double"],
        "pins_out": ["A:double"],
        "name": "LM4ECleanLive",
        "x": 350,
        "y": 650,
    }
    graph = _producer_graph(declared_params)
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await agent.run_live_producer_node(graph, NODE_ID)

    assert result.applied is True, f"expected applied; got {result!r}"
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == GH_CREATE_SCRIPT
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph

    node = result.graph.nodes[NODE_ID]
    assert node.status == "succeeded"
    assert node.evidence is not None
    assert node.evidence.receipt is not None
    assert node.evidence.receipt["artifact_status"] == "usable"
    assert node.evidence.verified is True
    # Component identity captured on the repair anchor.
    assert node.evidence.repair_anchor is not None
    component_guid = node.evidence.repair_anchor.get("component_guid")
    assert isinstance(component_guid, str) and component_guid


async def test_broken_csharp_live_producer_two_successes_seam(fresh_document):
    """Live two-successes seam: `B = new Box();` is created but fails to compile
    (type-conversion error). The raw envelope is success:False, yet because the
    node is an artifact_producer the graph node still succeeds with verified
    False. A `needs_repair` landing here would mean the producer projection was
    bypassed for conservative/direct-task semantics."""
    declared_params = {
        "language": "csharp",
        "code": "B = new Box();",
        "pins_in": [],
        "pins_out": ["B:Brep"],
        "name": "LM4EBrokenLive",
        "x": 350,
        "y": 760,
    }
    graph = _producer_graph(declared_params)
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await agent.run_live_producer_node(graph, NODE_ID)

    assert result.applied is True, f"expected applied; got {result!r}"
    assert result.reason is None
    assert result.graph is not graph

    node = result.graph.nodes[NODE_ID]
    assert node.evidence is not None
    # The tool failed functionally: the raw envelope was success:False.
    assert node.evidence.tool_status == "failed"
    assert node.evidence.receipt is not None
    assert node.evidence.receipt["artifact_status"] == "created_with_errors"
    # The producer hinge: created-but-bad -> succeeded / verified False.
    assert result.outcome_status == "succeeded"
    assert node.status == "succeeded"
    assert node.evidence.verified is False
```

- [ ] **Step 2: `py_compile` the new file**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tests/test_base_agent_live_producer_live.py`
Expected: exit 0, no output.

- [ ] **Step 3: Prove the skip path — run the module WITHOUT Rhino**

Run (from repo root, with Rhino NOT running / unreachable):
`mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_base_agent_live_producer_live.py -v`
Expected: collection succeeds and both tests report **SKIPPED** (the `fresh_document` fixture pings Rhino, fails to reach it, and calls `pytest.skip`). Expected summary: `2 skipped`. It must NOT error on collection and must NOT hard-fail. (If Rhino happens to be up in this environment, the tests run live instead — Step 5 — which is also acceptable; the requirement is "no error/no hard-fail.")

- [ ] **Step 4: Prove deselection — normal-CI selector excludes the module**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_base_agent_live_producer_live.py -m "not requires_rhino" -v`
Expected: `2 deselected`, 0 run. Confirms normal CI (which deselects `requires_rhino`) never executes this module.

- [ ] **Step 5: Live acceptance — run WITH Rhino up (operator step)**

This step requires a throwaway Rhino session with Rook loaded. If Rhino is not available in the execution environment, mark this step as deferred-to-operator and record that Steps 3–4 proved CI-safety; the live green is confirmed by the operator before merge.

Run (from repo root, Rhino open):
`mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider -m requires_rhino mcp_server/tests/test_base_agent_live_producer_live.py -v`
Expected: `2 passed`. Both the clean-`usable`→`succeeded` path and the broken-`created_with_errors`→`succeeded`/`verified False` seam land as specified. (Inherent live dependency: RhinoCode must flag `B = new Box();`; that flagging is the behavior the seam test confirms.)

- [ ] **Step 6: Confirm the focused PlanGraph gate is unchanged**

The live module is not matched by the PlanGraph glob, and there is no `src/` change, so the gate is trivially unaffected. Confirm it still passes from repo root:
`mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_live.py mcp_server/tests/test_plan_graph_live_dispatch.py mcp_server/tests/test_base_agent_live_producer.py`
Expected: all pass (same count as on `origin/main`; the LM4D unit file `test_base_agent_live_producer.py` = 4 passed).

- [ ] **Step 7: Test-only guard — no production diff**

Run: `git add mcp_server/tests/test_base_agent_live_producer_live.py`
Then: `git diff --name-only origin/main`
Expected: the output lists ONLY:
- `docs/superpowers/specs/2026-06-22-lm4e-live-producer-smoke-design.md`
- `docs/superpowers/plans/2026-06-22-lm4e-live-producer-smoke.md`
- `mcp_server/tests/test_base_agent_live_producer_live.py`

There must be NO `mcp_server/src/**` path in the diff. (PowerShell: pipe to `Select-String 'mcp_server/src/'` and confirm zero matches.)

- [ ] **Step 8: Commit**

```bash
git add mcp_server/tests/test_base_agent_live_producer_live.py
git commit -m "test(lm4e): live producer smoke over agent live-producer method"
```

(Commit message body should note: two opt-in one-node requires_rhino smokes; clean→usable→succeeded; B = new Box()→success:False+created_with_errors→producer succeeded/verified False; test-only, no src diff. End with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.)

## Self-Review

- **Spec coverage:** Both spec tests (clean `usable`→`succeeded`; broken `created_with_errors`→`succeeded`/`verified False`) are implemented in Step 1. Skip-safety (Steps 3–4), live acceptance (Step 5), test-only guard (Step 7), `py_compile` (Step 2), and the unchanged focused gate (Step 6) are all gated. The producer hinge is pinned exactly as the spec requires.
- **Placeholder scan:** none — Step 1 carries the complete file content; every command is concrete.
- **Type consistency:** `LiveProducerResult` fields (`.applied/.reason/.outcome_status/.tool_name/.graph`) and `NodeEvidence` fields (`.tool_status/.verified/.receipt/.repair_anchor`) match the merged code (`plan_graph_live.py`, `plan_graph_outcomes.py`). `NODE_ID`/`GH_CREATE_SCRIPT` constants are used consistently.
