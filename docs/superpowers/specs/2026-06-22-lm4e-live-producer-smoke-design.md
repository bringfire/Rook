# LM4E — Opt-in Live Producer Smoke

**Date:** 2026-06-22
**Campaign:** Local/Internal-Models (LM) reliability — Stage 5 (live PlanGraph execution)
**Slice:** LM4E — first live smoke over the agent live-producer method
**Status:** Design approved (brainstorming), ready for implementation plan

---

## Goal

Prove the live producer path end-to-end through a **real agent**:

```
RookAgent(tool_executor=_mcp_tool_executor)
  -> agent.run_live_producer_node(graph, node_id)        (LM4D method)
  -> run_live_producer_node_with_executor                (LM4C bridge)
  -> run_live_producer_node -> apply_live_producer_node   (LM4B/LM4A)
  -> real gh_create_script (MCP tool surface, real Rhino + Grasshopper)
  -> node_evidence_from_tool_result (receipt capture)     (LM3I/LM1F)
  -> project_receipt_outcome(role="artifact_producer")    (LM3F)
  -> reducer apply_outcome
```

LM4E is a **test-only** slice: two independent, opt-in, one-node `requires_rhino`
smokes. No production code changes, no scheduler, no chain advancement, no chat
loop, no reusable helper.

## Position in the campaign

The executor-contract stack is closed and reachable from a real agent (LM4A→D).
Every prior proof used a synthetic raw dict or an injected fake executor. LM4E is
the first slice that drives the path against a **live Rhino/Grasshopper-backed
tool result**, confirming the receipt actually travels through the production
agent executor seam and projects correctly by role.

This is the appropriate altitude for a first live smoke: opt-in, isolated from
normal CI, and strictly one node — not a default merge gate, not a runner, not an
eval harness (those, if ever wanted, are later slices with a real second caller).

## Decisions locked in brainstorming

- **Boundary (Q1) — Option 1: a `requires_rhino` pytest smoke.** The test *is* the
  harness. No script/CLI, no reusable helper until a second caller exists.
- **Definition of live (Q2) — Option B + correction: clean node + live seam.** Two
  independent one-node smokes. The second proves the "two successes" decoupling:
  a tool result that is functionally `success: False` still drives an
  `artifact_producer` node to `succeeded` because a repairable artifact exists.
- **Executor shape:** inject the production MCP executor —
  `RookAgent(tool_executor=_mcp_tool_executor)` — matching the existing live-test
  convention. NOT a bare `RookAgent()` / auto-built `ToolDispatcher`; that is a
  possible later live-path comparison slice.

## Grounding (verified against merged code)

The receipt bridge is already wired through the live tool — LM4E confirms it
live, it does not discover it:

- `gh_create_script` runs `/gh/errors` verification **inline**
  (`verification_method="gh_errors"`, not deferred) and always attaches
  `data["script_receipt"]` via `build_script_receipt`
  (`server.py:2607-2645`). The final envelope (`_gh_create_script_result_from_data`,
  `server.py:2447`) preserves it at exactly the path the consumer reads:
  `result["data"]["script_receipt"]` (`plan_graph_outcomes.py:35-42`).
- **Clean trivial component:** `component_errors == []` → verification `"passed"`
  → `derive_artifact_status("create","passed") == "usable"`. For role
  `artifact_producer`, `_producer_outcome` returns `_producer_success(..., True)`
  → `status="succeeded"`, `verified=True`
  (`plan_graph_projection.py:190-193`).
- **Post-create compile error (`B = new Box();`):** the component IS created, so
  `mutation_status="created"` is hardcoded (`server.py:2628`); compilation fails
  → `data["compilation_errors"]` set → top-level envelope is
  `{"success": False, ...}` (`server.py:2448-2454`) AND
  `artifact_status="created_with_errors"`. For role `artifact_producer`,
  `_has_mutation_evidence` is True (via `mutation.status=="created"`), so
  `_producer_outcome` promotes to `_producer_success(..., False)` →
  `status="succeeded"`, `verified=False`
  (`plan_graph_projection.py:199-205`). The conservative `needs_repair` mapping
  (`_conservative_outcome`, `plan_graph_projection.py:120-122`) is the
  `direct_task`/`artifact_verifier` path and must NOT be reached here.
- **Broken body is grounded:** `test_server_contract_hardening.py:559` uses
  `"B = new Box();"` with `pins_out=["B:Brep"]` and asserts
  `receipt["artifact_status"] == "created_with_errors"`,
  `repair_anchor.component_guid == component_guid`, and
  `target_errors == ["Cannot convert Box to Brep"]`. This is a created-but-bad
  artifact (type-conversion failure at solve), NOT an early validation rejection —
  exactly the seam the smoke needs. `A = ;` is rejected: it risks being caught by
  a future create-time preflight before the component exists, which would prove
  early-validation failure instead of the producer seam.
- **Evidence location:** the reducer stores `NodeEvidence` at
  `graph.nodes[node_id].evidence` (`plan_graph_runner.py:96`, `:171-183`), and
  `node.status` carries the outcome status. The tests read the hinge off the
  applied node's `.evidence`.
- **No copy hazard:** `apply_producer_result` internally calls `runnable_nodes`
  (a deep-copy snapshot), but real `execution_params` are plain JSON-shaped dicts
  (`language`/`code`/`pins`), fully deep-copyable — no LM4A non-copyable-param
  hazard here.

## Architecture

### File

`mcp_server/tests/test_base_agent_live_producer_live.py`
(mirrors the LM4D unit file `test_base_agent_live_producer.py` plus the `*_live.py`
live-convention suffix).

```python
pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]
```

### Skip-safety (normal CI untouched)

Each test takes the existing `fresh_document` fixture (`conftest.py:115`) — the
codebase's blessed graceful-skip path: it pings Rhino, `pytest.skip`s when Rhino
is unreachable, and hard-fails only under the owned runtime harness
(`ROOK_RHINO_PORT`/`ROOK_RHINO_PROCESS_ID`). Normal CI / the focused PlanGraph
gate stay untouched because `requires_rhino` modules are deselected
(`-m "not requires_rhino"`), exactly as the other 60 live modules.

`fresh_document` resets the Rhino document (harmless for a GH-only smoke; it does
not touch the GH canvas). Accepted as the established skip path.

### Local graph fixture

A small builder mirroring the LM4D fixture, parameterized by the real tool name
and the real argument dict:

```python
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY

NODE_ID = "create_script"
GH_CREATE_SCRIPT = "gh_create_script"

def _producer_graph(declared_params: dict) -> PlanGraph:
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
```

The agent is a real one wired to the MCP executor:

```python
from rook.agent.base_agent import RookAgent
from rook.server import _mcp_tool_executor

agent = RookAgent(tool_executor=_mcp_tool_executor)
result = await agent.run_live_producer_node(graph, NODE_ID)
```

## Tests

### Test 1 — clean component (live happy path)

`declared_params` = a valid C# create:

```python
{
    "language": "csharp",
    "code": "A = Convert.ToDouble(R) * 2.0;",
    "pins_in": ["R:double"],
    "pins_out": ["A:double"],
    "name": "LM4ECleanLive",
    "x": 350, "y": 650,
}
```

Assertions:

- `result.applied is True`
- `result.reason is None`
- `result.outcome_status == "succeeded"`
- `result.tool_name == "gh_create_script"`
- `result.graph is not graph` (applied → fresh reducer graph)
- `node = result.graph.nodes[NODE_ID]`; `node.status == "succeeded"`
- `node.evidence.receipt["artifact_status"] == "usable"`
- `node.evidence.verified is True` (grounded: `_producer_success(..., True)` for
  `usable`)
- `node.evidence.repair_anchor["component_guid"]` is a non-empty `str`

### Test 2 — deliberately broken C# (live two-successes seam)

`declared_params` = the grounded post-create compile-error create:

```python
{
    "language": "csharp",
    "code": "B = new Box();",
    "pins_in": [],
    "pins_out": ["B:Brep"],
    "name": "LM4EBrokenLive",
    "x": 350, "y": 760,
}
```

Assertions (pin the role-projection hinge strongly):

- `result.applied is True`
- `result.reason is None`
- `result.graph is not graph`
- `node = result.graph.nodes[NODE_ID]`
- `node.evidence.tool_status == "failed"` (raw envelope was `success: False`)
- `node.evidence.receipt["artifact_status"] == "created_with_errors"`
- **because the node is `artifact_producer`:**
  - `result.outcome_status == "succeeded"`
  - `node.status == "succeeded"`
  - `node.evidence.verified is False`

This is the alarm bell: if this node lands `needs_repair`, the producer
projection was bypassed and the path fell back to conservative/direct-task
semantics. Its one inherent live dependency — that RhinoCode flags the bad body
(`component_errors` → `compilation_errors` → `success:False` +
`created_with_errors`) — is precisely the live behavior the smoke exists to
confirm.

## Out of scope / byte-stable

- **No production code change.** Test-only slice. `base_agent.py`,
  `plan_graph_live*.py`, `server.py`, the pure `learning/plan_graph_*` layer:
  all unchanged.
- No bare `RookAgent()` / auto-built `ToolDispatcher` in this slice.
- No scheduler, no chain advancement, no chat-loop integration, no helper/CLI
  extraction.
- Assert only grounded fields. `evidence.verified` IS grounded and pinned in both
  tests (True for `usable` at `plan_graph_projection.py:192`, False for
  `created_with_errors` at `:203`). Do not pin ungrounded surface such as exact
  `message` / `error` text or solver-dependent error strings.

## Verification gates

- New live module green with Rhino up:
  `pytest -m requires_rhino mcp_server/tests/test_base_agent_live_producer_live.py`
  (run from repo root, throwaway Rhino session).
- Same module **skips cleanly** with Rhino down (graceful skip via
  `fresh_document`, not a hard failure).
- Focused PlanGraph gate from the repo root unchanged (the live module is
  separate and deselected from that gate).
- `py_compile` clean on the new test file.
- **No production diff:** `git diff --name-only origin/main` shows only the new
  test file plus this spec and its plan — no `src/` change.

## Constraints (Global)

- Test-only; no production code touched.
- Two independent one-node smokes; no scheduler, no chain, no chat loop, no
  helper extraction.
- Executor is `_mcp_tool_executor` injected into a real `RookAgent`.
- Evidence is read off `result.graph.nodes[NODE_ID].evidence`.
- Broken-C# body is `B = new Box();` / `pins_out=["B:Brep"]` (grounded
  post-create compile error), NOT a syntax-error body.
- `requires_rhino` keeps the module out of normal CI by deselection; skip-safe
  when Rhino is down.
- Live-test runner (from repo root, Rhino up):
  `pytest -m requires_rhino mcp_server/tests/test_base_agent_live_producer_live.py`.
