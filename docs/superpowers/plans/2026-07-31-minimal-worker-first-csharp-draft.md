# Minimal Worker-First C# Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one internal normal-path composition in which the existing strict Planner draft is deterministically compiled into an incomplete `create -> verify -> done` scaffold, one bounded Worker supplies only the initial C# body, and the existing runner performs one create plus deterministic receipt verification with no repair.

**Architecture:** Register one narrow `gh_csharp_create_verify` topology, complete its compiler-owned `create_script` parameters through a pure scaffold applicator, and execute it through a sibling handoff compositor. Extend the existing Planner integration module with a separately owned initial-body aggregate so Planner/draft stops remain outside the handoff result. Preserve the forced repair path unchanged.

**Tech Stack:** Python 3.11, frozen dataclasses, existing Rook workflow compiler and PlanGraph runners, existing local Worker adapter/harness/disposition, pytest, PowerShell, Git.

## Global Constraints

- Begin from clean branch `codex/minimal-worker-first-csharp-draft-design` at specification amendment commit `fb52d278`.
- Implement against [the approved specification](../specs/2026-07-31-minimal-worker-first-csharp-draft-design.md).
- No provider, Worker box, Rhino, Grasshopper, Chat, MCP, CLI, or operator-script contact.
- Exactly one Planner call, at most one Worker call, at most one `gh_create_csharp_script` call, and no `gh_update_script` call.
- No retries, fallback, alternate model, deterministic code patching, or repair continuation.
- Planner authors only the existing four-field draft. Worker authors only `draft_create_body.input.code`.
- Compiler owns topology, tool reference, pins, name, position, body convention, verification, node identity, and terminal semantics.
- The new graph contains exactly `create_script`, `verify_create`, and `done`; both edges are `requires`.
- `create_script` initially contains exactly `pins_in`, `pins_out`, `name`, `x`, and `y`; `code` and `mode` are absent.
- The pure applicator consumes the exact compiled scaffold, preserves every original parameter projection, and adds only `code` to a copied graph.
- `draft_create_body` is the only initial context action. `draft_repair_params` remains the only repair context action.
- Existing repair compositor, repair action, workflow, public interfaces, prompts, receipts, smoke scripts, and flight recorder remain unchanged.
- New aggregate results are ephemeral internal transaction objects, not archives, proofs, checkpoints, retry tokens, or public evidence.
- Do not implement the deferred topology-guidance hypothesis or a generic pre-execution affordance framework.
- Use `apply_patch` for source and document edits. Do not introduce dependencies.

---

## File Structure

### Production

- Modify `mcp_server/src/rook/learning/plan_graph_templates.py`
  - Register and construct only the new `gh_csharp_create_verify` graph.
- Create `mcp_server/src/rook/agent/plan_graph_worker_create_body_apply.py`
  - Own the pure scaffold-bound `draft_create_body` applicator and its small result.
- Create `mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py`
  - Own the incomplete contract builder, initial Worker context/action, one-turn handoff, native execution, and `MinimalCSharpInitialBodyHandoffResult`.
- Modify `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
  - Reuse the existing Planner adapter/prompt/loader and add only the initial-body integration result and runner.

### Tests

- Modify `mcp_server/tests/test_plan_graph_templates.py`
  - Prove the exact registered topology and non-overlap with repair templates.
- Create `mcp_server/tests/test_plan_graph_worker_create_body_apply.py`
  - Prove exact scaffold custody, copy-on-write union, and adversarial refusals.
- Create `mcp_server/tests/test_minimal_csharp_initial_body_handoff.py`
  - Prove contract construction, Worker visibility, one-turn action, native success/failure, and handoff lineage.
- Create `mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py`
  - Prove exact intent-to-Planner-to-handoff ownership and complete stop matrix.

### Durable plan ledger

- Modify this plan only during execution to mark completed steps and record final commands, counts, and HEAD.

---

### Task 1: Compiler-Owned Create/Verify Topology and Incomplete Scaffold

**Files:**
- Create: `mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py`
- Modify: `mcp_server/src/rook/learning/plan_graph_templates.py`
- Modify: `mcp_server/tests/test_plan_graph_templates.py`
- Create: `mcp_server/tests/test_minimal_csharp_initial_body_handoff.py`

**Interfaces:**
- Consumes: `ValidatedPlannerDraft`, `RookWorkflowContract`, `compile_workflow_contract()`.
- Produces: private `_build_initial_body_contract(draft) -> RookWorkflowContract`; registered template ID `gh_csharp_create_verify`; exact incomplete `CompiledWorkflowScaffold` used by Tasks 2 and 3.

- [ ] **Step 1: Create an importable behavioral skeleton**

Create `minimal_csharp_initial_body_handoff.py` with imports, exact constants, and a deliberately unimplemented pure builder:

```python
"""One-turn Worker-authored initial C# body handoff."""

from rook.agent.minimal_csharp_repair_handoff import ValidatedPlannerDraft
from rook.agent.plan_graph_workflow_contract import RookWorkflowContract

_WORKFLOW_ID = "minimal_csharp_initial_body_handoff"
_TEMPLATE_ID = "gh_csharp_create_verify"
_CREATE_NODE_ID = "create_script"
_VERIFY_NODE_ID = "verify_create"
_TERMINAL_NODE_ID = "done"
_ACTION_ID = "draft_create_body"


def _build_initial_body_contract(
    draft: ValidatedPlannerDraft,
) -> RookWorkflowContract:
    raise NotImplementedError("initial-body contract builder not implemented")
```

This skeleton makes the RED behavioral rather than a missing-module collection error.

- [ ] **Step 2: Add exact topology and incomplete-scaffold tests**

Add a template test with these assertions:

```python
selection = select_template(
    {
        "domain": "grasshopper",
        "operation": "create_verify",
        "language": "csharp",
    }
)
assert selection.selected_template_id == "gh_csharp_create_verify"
assert selection.graph is not None
assert tuple(selection.graph.nodes) == (
    "create_script",
    "verify_create",
    "done",
)
assert [
    (edge.source, edge.target, edge.kind)
    for edge in selection.graph.edges
] == [
    ("create_script", "verify_create", "requires"),
    ("verify_create", "done", "requires"),
]
assert selection.graph.nodes["create_script"].execution_ref == (
    "gh_create_csharp_script:v1"
)
assert selection.graph.nodes["create_script"].metadata == {
    "outcome_projection_role": "artifact_producer"
}
assert selection.graph.nodes["verify_create"].metadata == {
    "outcome_projection_role": "artifact_verifier"
}
assert selection.graph.nodes["done"].is_terminal is True
```

In the new handoff test, load a valid draft through the existing loader, call the builder and compiler, then assert:

```python
contract = _build_initial_body_contract(_valid_draft())
scaffold = compile_workflow_contract(contract)

assert scaffold.compile_record.expected_template_id == "gh_csharp_create_verify"
assert scaffold.compile_record.selected_template_id == "gh_csharp_create_verify"
assert scaffold.max_steps == 4
assert tuple(scaffold.graph.nodes) == (
    "create_script",
    "verify_create",
    "done",
)
params = scaffold.graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
assert set(params) == {"pins_in", "pins_out", "name", "x", "y"}
assert params["pins_in"] == ()
assert params["pins_out"] == ("A:double",)
assert "code" not in params
assert "mode" not in params
assert scaffold.compile_record.expected_refs == (
    ("create_script", "gh_create_csharp_script:v1"),
)
assert scaffold.compile_record.step_kinds_by_rule == (
    ("create_script", ("producer",)),
    ("verify_create", ("verifier",)),
)
assert all(
    not isinstance(step, BindStepSpec)
    for rule in contract.rules
    for step in rule.steps_by_seen_count
)
```

Add a second valid goal and assert both contracts compile to identical
compiler-owned template selection, initial parameters, rules, terminal IDs,
expected refs, and maximum steps. The goal is carried separately into Worker
knowledge; the contract builder must not convert it into topology or execution
parameters.

- [ ] **Step 3: Run the focused RED**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_templates.py `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py -q
```

Expected RED:

- template selection rejects the unregistered `create_verify` descriptor; and
- the importable builder raises its deliberate `NotImplementedError`.

Any fixture, import, or unrelated failure is not a valid RED.

- [ ] **Step 4: Implement the exact registered template**

Add this graph builder beside the existing C# templates:

```python
def _build_gh_csharp_create_verify() -> PlanGraph:
    return PlanGraph(
        nodes={
            "create_script": PlanGraphNode(
                id="create_script",
                intent="Create C# script component",
                execution_ref="gh_create_csharp_script:v1",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                metadata={"outcome_projection_role": "artifact_producer"},
            ),
            "verify_create": PlanGraphNode(
                id="verify_create",
                intent="Verify the created component's receipt",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                metadata={"outcome_projection_role": "artifact_verifier"},
            ),
            "done": PlanGraphNode(
                id="done",
                intent="Finalize: initial artifact verified clean",
                is_terminal=True,
            ),
        },
        edges=[
            PlanGraphEdge(
                source="create_script",
                target="verify_create",
                kind="requires",
            ),
            PlanGraphEdge(
                source="verify_create",
                target="done",
                kind="requires",
            ),
        ],
    )
```

Register it with:

```python
_make_entry(
    "gh_csharp_create_verify",
    {
        "domain": "grasshopper",
        "operation": "create_verify",
        "language": "csharp",
    },
    _build_gh_csharp_create_verify,
    bindings=(
        BindingSpec("goal", "memory_fact", "goal"),
        BindingSpec(
            "component_name",
            "node_metadata",
            "component_name",
            node_id="create_script",
        ),
    ),
)
```

Do not edit any existing template builder or descriptor.

- [ ] **Step 5: Implement the pure incomplete contract builder**

Replace the skeleton body with an exact `RookWorkflowContract`:

```python
return RookWorkflowContract(
    workflow_id=_WORKFLOW_ID,
    template=WorkflowTemplateRef(
        descriptor={
            "domain": "grasshopper",
            "operation": "create_verify",
            "language": "csharp",
        },
        expected_template_id=_TEMPLATE_ID,
    ),
    initial_params=(
        InitialNodeParams(
            node_id=_CREATE_NODE_ID,
            execution_params={
                "pins_in": list(draft.interface.inputs),
                "pins_out": [
                    f"{output.name}:{output.type}"
                    for output in draft.interface.outputs
                ],
                "name": "RookMinimalInitialBodyHandoff",
                "x": 375,
                "y": 1080,
            },
        ),
    ),
    rules=(
        WorkflowNodeRule(
            node_id=_CREATE_NODE_ID,
            steps_by_seen_count=(ProducerStepSpec(_CREATE_NODE_ID),),
        ),
        WorkflowNodeRule(
            node_id=_VERIFY_NODE_ID,
            steps_by_seen_count=(
                VerifierStepSpec(
                    verifier_node_id=_VERIFY_NODE_ID,
                    source_node_id=_CREATE_NODE_ID,
                    expected_outcome="succeeded",
                ),
            ),
        ),
    ),
    terminal_node_ids=(_TERMINAL_NODE_ID,),
    expected_refs=(
        ExpectedNodeRef(_CREATE_NODE_ID, "gh_create_csharp_script:v1"),
    ),
    max_steps=4,
    metadata={
        "capability": "grasshopper_csharp_component",
        "acceptance": "clean_compile_receipt",
    },
)
```

Import and call the existing private `_require_validated_draft()` from
`minimal_csharp_repair_handoff` before construction so the sibling path uses
the same forged-carrier defense rather than a parallel validator. Do not place
a body-mode field or code in initial parameters.

- [ ] **Step 6: Run GREEN and regression selection**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_templates.py `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py -q
```

Expected: all selected tests pass. Confirm the pre-existing repair template tests still select `gh_csharp_create_verify_repair_verify`.

- [ ] **Step 7: Commit Task 1**

```powershell
git add `
  mcp_server/src/rook/learning/plan_graph_templates.py `
  mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py `
  mcp_server/tests/test_plan_graph_templates.py `
  mcp_server/tests/test_minimal_csharp_initial_body_handoff.py
git commit -m "feat: add compiler-owned C# create verify scaffold"
```

- [ ] **Step 8: Mandatory independent review stop**

Stop after the commit. Request review of only Task 1. Do not begin Task 2 until the reviewer confirms the exact topology, both `requires` edges, incomplete parameter shape, verifier ownership, descriptor non-overlap, and unchanged repair selection.

---

### Task 2: Pure Scaffold-Bound Initial-Body Applicator

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_worker_create_body_apply.py`
- Create: `mcp_server/tests/test_plan_graph_worker_create_body_apply.py`
- Reuse: `mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py`

**Interfaces:**
- Consumes: exact `CompiledWorkflowScaffold`, node ID, action ID, and closed `{code}` mapping.
- Produces: `WorkerCreateBodyApplyResult` and `apply_worker_create_body_to_scaffold()` for Task 3.

- [ ] **Step 1: Write the valid copy-on-write RED**

Compile the Task 1 scaffold and call the missing applicator:

```python
original_graph = copy.deepcopy(scaffold.graph)
result = apply_worker_create_body_to_scaffold(
    scaffold,
    "create_script",
    action_id="draft_create_body",
    action_input={"code": "A = 42.0;"},
)

assert result.applied is True
assert result.reason is None
assert result.node_id == "create_script"
assert result.params_sha256 is not None
assert scaffold.graph == original_graph
original_params = scaffold.graph.nodes["create_script"].metadata[
    EXECUTION_PARAMS_KEY
]
returned_params = result.graph.nodes["create_script"].metadata[
    EXECUTION_PARAMS_KEY
]
assert set(returned_params) == set(original_params) | {"code"}
assert {key: returned_params[key] for key in original_params} == original_params
assert returned_params["code"] == "A = 42.0;"
```

- [ ] **Step 2: Run the RED**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_create_body_apply.py -q
```

Expected RED: import fails specifically because the new applicator module does not exist.

- [ ] **Step 3: Implement the exact result and validation helpers**

Create:

```python
@dataclass(frozen=True)
class WorkerCreateBodyApplyResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    reason: str | None
    params_sha256: str | None
```

Use closed constants:

```python
_TEMPLATE_ID = "gh_csharp_create_verify"
_CREATE_NODE_ID = "create_script"
_CREATE_EXECUTION_REF = "gh_create_csharp_script:v1"
_ACTION_ID = "draft_create_body"
_ORIGINAL_PARAM_KEYS = frozenset({"pins_in", "pins_out", "name", "x", "y"})
_ACTION_INPUT_KEYS = frozenset({"code"})
```

Implement exact-string checks before equality. Reject with fixed tokens from this closed set:

```text
invalid_template
unknown_node
invalid_tool_ref
invalid_action_id
invalid_action_input
unexpected_action_input_key
missing_code
invalid_code
invalid_execution_params
execution_params_shape_mismatch
code_already_present
graph_copy_failed
```

Wrong Python carrier types for the scaffold itself raise `TypeError`; product-domain mismatches return a rejected result.

- [ ] **Step 4: Implement the pure union**

The success branch must use this order:

```python
original_params = node.metadata[EXECUTION_PARAMS_KEY]
new_graph = deepcopy(scaffold.graph)
completed_params = dict(original_params)
completed_params["code"] = code
new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = completed_params
```

Compute `params_sha256` from canonical JSON of `completed_params` with `sort_keys=True`, `separators=(",", ":")`, and `ensure_ascii=True`. Do not mutate `scaffold`, `scaffold.graph`, `original_params`, or `action_input`.

- [ ] **Step 5: Add the closed adversarial table**

Parameterize these mutations and exact expected reasons:

```text
expected template changed                    -> invalid_template
selected template changed                    -> invalid_template
node id verify_create                        -> invalid_tool_ref
node id absent_from_graph                    -> unknown_node
create execution_ref changed                 -> invalid_tool_ref
action id draft_repair_params                -> invalid_action_id
action input list                            -> invalid_action_input
empty input                                  -> missing_code
extra mode key                               -> unexpected_action_input_key
pin/name/x/y key in action input             -> unexpected_action_input_key
blank code                                   -> invalid_code
string-subclass/equality-spoof code           -> invalid_code
pre-populated create code                     -> code_already_present
missing original parameter                   -> execution_params_shape_mismatch
extra original parameter                     -> execution_params_shape_mismatch
non-mapping execution params                 -> invalid_execution_params
deepcopy exception                           -> graph_copy_failed
```

Check `code_already_present` before comparing the original key set, so a
pre-populated code field receives its specific reason rather than the generic
shape reason. For every rejected case assert:

```python
assert result.applied is False
assert result.graph is scaffold.graph
assert scaffold.graph == before
assert result.params_sha256 is None
```

Add a caller-custody test proving tuple/list inputs and the action mapping are unchanged after success and rejection.

- [ ] **Step 6: Run Task 2 GREEN and repair-action regression**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_create_body_apply.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py -q
```

Expected: all tests pass; the existing repair applicator still accepts only `draft_repair_params` with `{code, mode}` plus a receipt anchor.

- [ ] **Step 7: Commit Task 2 and stop for review**

```powershell
git add `
  mcp_server/src/rook/agent/plan_graph_worker_create_body_apply.py `
  mcp_server/tests/test_plan_graph_worker_create_body_apply.py
git commit -m "feat: add Worker initial-body scaffold applicator"
```

Request review of scaffold binding, exact union, original-scaffold immutability, closed action input, and repair-action separation before Task 3.

---

### Task 3: One-Turn Initial-Body Handoff and Native Execution

**Files:**
- Modify: `mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py`
- Modify: `mcp_server/tests/test_minimal_csharp_initial_body_handoff.py`

**Interfaces:**
- Consumes: `ValidatedPlannerDraft`, `LocalWorkerTransport`, callable typed tool executor, Task 1 scaffold, Task 2 applicator.
- Produces: `MinimalCSharpInitialBodyHandoffResult` and `run_minimal_csharp_initial_body_handoff()` for Task 4.

- [ ] **Step 1: Add a real-boundary success RED**

Use the existing response envelope and a fake transport that asserts the rendered request before returning:

```python
{
    "schema": "rook.local_worker_turn_response:v1",
    "kind": "action_request",
    "action_id": "draft_create_body",
    "rationale": "Author the initial body for the declared interface.",
    "input": {"code": "A = 42.0;"},
}
```

Use a causal fake executor that accepts only `gh_create_csharp_script`, exact compiler-owned pins/name/position, and one admitted body. Return the existing clean create-receipt shape derived from the received body.

Assert:

```python
result = await run_minimal_csharp_initial_body_handoff(
    _valid_draft(),
    worker_transport=worker_transport,
    tool_executor=tool_executor,
)

assert result.terminal_stage == "terminal"
assert result.terminal_reason == "terminal_node_selected:done"
assert len(worker_transport.calls) == 1
assert [name for name, _ in tool_executor.calls] == [
    "gh_create_csharp_script"
]
assert [record.accepted_node_id for record in result.step_records] == [
    "create_script",
    "verify_create",
]
assert result.step_records[-1].verifier_outcome_status == "succeeded"
assert result.final_graph.nodes["done"].status == "ready"
assert "code" not in result.scaffold.graph.nodes["create_script"].metadata[
    EXECUTION_PARAMS_KEY
]
assert result.action_apply_result.graph.nodes[
    "create_script"
].metadata[EXECUTION_PARAMS_KEY]["code"] == "A = 42.0;"
```

- [ ] **Step 2: Run the handoff RED**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py -q
```

Expected RED: `run_minimal_csharp_initial_body_handoff` or its result type is not yet defined. The Task 1 builder tests must remain green in the same run.

- [ ] **Step 3: Add the exact Worker context and action**

Define the action as:

```python
WorkerAllowedAction(
    action_id="draft_create_body",
    kind="draft_create_body",
    description="Draft the complete initial C# body.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    },
)
```

Build three private knowledge packets from actual retained inputs:

```text
planner_goal_and_interface
  <- draft.goal + interface projected from scaffold create params

script_body_gotcha
  <- code-owned {body_mode: body}

clean_compile_acceptance
  <- exact contract verifier rule with content:
     {
       "verifier_node_id": "verify_create",
       "source_node_id": "create_script",
       "expected_outcome": "succeeded",
       "criterion":
         "The initial C# body must compile cleanly for the declared interface."
     }
```

Do not call `extract_acceptance_criteria_sources()` or `assemble_acceptance_criteria_packet()`: those existing functions are intentionally repair-specific, require a receipt diagnostic, and bind `verify_repair`. The private initial packet introduces no shared schema and contains only the exact projected fields above plus a short code-owned description that the initial body must satisfy the declared output and compile cleanly.

Project the interface from `scaffold.graph.nodes["create_script"]` parameters and require exact equality with the rendered validated interface before Worker contact.

Call `build_local_worker_turn_context()` with:

```python
graph=scaffold.graph
records=()
supply_records=()
current_node_id="create_script"
allowed_actions=(_draft_create_body_action(),)
```

Render through `render_local_worker_turn_request_payload()` and call `run_local_worker_adapter()` exactly once.

- [ ] **Step 4: Implement the exact handoff result ownership**

Add the frozen result exactly as specified:

```python
@dataclass(frozen=True)
class MinimalCSharpInitialBodyHandoffResult:
    draft: ValidatedPlannerDraft
    scaffold: CompiledWorkflowScaffold
    final_graph: PlanGraph
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    step_records: tuple[CurrentStepRecord, ...]
    worker_request: Mapping[str, Any]
    worker_context: LocalWorkerTurnContext
    adapter_record: LocalWorkerAdapterRecord
    worker_record: LocalWorkerTurnHarnessRecord | None
    action_apply_result: WorkerCreateBodyApplyResult | None
    terminal_stage: Literal[
        "worker_adapter",
        "worker_disposition",
        "action_apply",
        "create",
        "verify_create",
        "terminal",
    ]
    terminal_reason: str
```

Every returned result contains request, context, and adapter record. The stage table is exact:

```text
worker_adapter     -> no worker_record, no action result, empty native records
worker_disposition -> worker_record, no action result, empty native records
action_apply       -> worker_record, rejected action result, empty native records
create             -> applied action; native prefix () or (create_script)
verify_create      -> applied action; native prefix (create_script, verify_create); done not ready
terminal           -> applied action; exact two-record prefix; done ready
```

- [ ] **Step 5: Implement one-shot Worker disposition and graph completion**

After a loaded response, pass that exact response through the existing one-shot harness callback and disposition. For a candidate action:

```python
payload = loaded_response.payload
if type(payload) is not WorkerActionRequest:
    raise RuntimeError("candidate disposition lacks exact action payload")

action_apply_result = apply_worker_create_body_to_scaffold(
    scaffold,
    "create_script",
    action_id=payload.action_id,
    action_input=payload.input,
)
```

Return `action_apply` on a rejected result. Do not construct a tool runner until application succeeds.

- [ ] **Step 6: Execute the completed graph through the existing stream**

Create the same small private executor adapter pattern used by the repair compositor and call:

```python
stream = await run_current_step_stream(
    action_apply_result.graph,
    scaffold.provider,
    max_steps=scaffold.max_steps,
    runner=_ToolExecutorRunner(tool_executor),
)
```

Derive stages only from native records and the terminal supply record:

```text
terminal_node_selected:done + exact two-record prefix + verifier succeeded + done ready
-> terminal

exact two-record prefix without terminal selection
-> verify_create

all earlier native prefixes
-> create
```

Preserve the native reason with the same closed reason extraction pattern used by the repair compositor. Do not invent a compile-failure outcome.

- [ ] **Step 7: Close handoff transaction lineage**

In `MinimalCSharpInitialBodyHandoffResult.__post_init__`, validate only this module's chain:

1. exact draft and exact scaffold type;
2. scaffold selected/expected template equals `gh_csharp_create_verify`;
3. scaffold create params have no code;
4. `worker_request == render_local_worker_turn_request_payload(worker_context)`;
5. Worker context workflow identity matches scaffold;
6. adapter record is the exact retained adapter type and its loaded response is
   the response passed to the one-shot harness; transport-bound prompt
   equality is asserted at the fake transport boundary rather than claimed by
   this ephemeral aggregate;
7. loaded response disposition re-derives from retained context and response;
8. accepted action application exactly equals replaying `apply_worker_create_body_to_scaffold()` from the retained scaffold and response;
9. every `CurrentStepRecord` equals `project_current_step_record()` from its native nested mapping/revalidation/execution fields;
10. graph chain is `scaffold.graph -> applied graph -> create -> verify -> final graph`;
11. original scaffold contains no code; first graph-state occurrence is the applied graph; later occurrences are native propagation only;
12. stage-specific optional fields, record prefixes, node statuses, verifier outcome, and reason agree.

Use existing pure functions and equality checks. Do not add carriers, hashes beyond the action parameter hash, or durable evidence.

- [ ] **Step 8: Add the full Worker and native stop matrix**

Add tests for:

```text
adapter transport failure             -> worker_adapter, zero tools
invalid raw response                  -> worker_adapter, zero tools
refusal                               -> worker_disposition, zero tools
clarification                         -> worker_disposition, zero tools
observation                           -> worker_disposition, zero tools
wrong action id                       -> adapter/disposition rejection, zero tools
input contains mode                   -> adapter/disposition rejection, zero tools
blank code                            -> adapter/disposition rejection, zero tools
applicator rejection                  -> action_apply, zero tools
create executor raises                -> create, one entered tool call
create response malformed             -> create, one tool call
clean create receipt                  -> terminal, one tool call
compile-error create receipt          -> verify_create, one tool call
```

For compile failure assert:

```python
assert result.step_records[-1].verifier_outcome_status == "needs_repair"
assert result.final_graph.nodes["done"].status == "pending"
assert result.supply_records[-1].reason == "selector_halt:none_ready"
assert [name for name, _ in tool_executor.calls] == [
    "gh_create_csharp_script"
]
```

The fake create receipt must derive its clean/error branch from the exact received Worker body. It must reject unexpected pins, name, position, tool name, call order, second create, and all update calls.

- [ ] **Step 9: Add Worker visibility and code-custody regressions**

Recursively inspect the serialized Worker request and prove:

- exact goal, `A:double`, body convention, verifier source, and `succeeded` outcome are present;
- exactly one allowed action is `draft_create_body`;
- `draft_repair_params`, diagnostic text, C# code, GUIDs, graph edges/rules, execution parameter mappings, update instructions, and expected Worker code are absent.

Mutate the Worker body and prove the retained adapter/harness response changes, the applicator returned graph contains that exact changed value, the original scaffold remains code-free, and no parallel result field stores it.

- [ ] **Step 10: Run Task 3 GREEN and existing repair seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py `
  mcp_server\tests\test_plan_graph_worker_create_body_apply.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py -q
```

Expected: all pass. Confirm the existing repair fake still receives one create and one update and its Worker action remains `draft_repair_params`.

- [ ] **Step 11: Commit Task 3 and stop for review**

```powershell
git add `
  mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py `
  mcp_server/tests/test_minimal_csharp_initial_body_handoff.py
git commit -m "feat: compose one-turn Worker initial C# draft"
```

Request review of request visibility, one-call Worker custody, code-authority lineage, pure application replay, native record chain, compile-failure stop, and absence of update/repair before Task 4.

---

### Task 4: Planner-Facing Initial-Body Integration and Two-Result Ownership

**Files:**
- Modify: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
- Create: `mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py`
- Reuse: `mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py`

**Interfaces:**
- Consumes: exact intent, exact `MinimalPlannerDraftAdapter`, existing strict loader, initial-body handoff.
- Produces: `MinimalIntentWorkerInitialBodyIntegrationResult` and `run_minimal_intent_worker_initial_body_integration()`.

- [ ] **Step 1: Write the complete raw-intent vertical RED**

Use a fake `MinimalPlannerTransport` that captures the one request and returns the exact four-field object with `goal` copied byte-for-byte from the test intent. Use the Task 3 fake Worker transport and causal tool executor.

Assert:

```python
result = await run_minimal_intent_worker_initial_body_integration(
    intent,
    planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
    worker_transport=worker_transport,
    tool_executor=tool_executor,
)

assert result.intent == intent
assert len(planner_transport.calls) == 1
assert result.planner_adapter_record.status == "decoded"
assert result.validated_draft is not None
assert result.validated_draft.goal == intent
assert result.handoff_result is not None
assert result.terminal_stage == result.handoff_result.terminal_stage == "terminal"
assert result.terminal_reason == result.handoff_result.terminal_reason
assert len(worker_transport.calls) == 1
assert [name for name, _ in tool_executor.calls] == [
    "gh_create_csharp_script"
]
```

- [ ] **Step 2: Run the integration RED**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_initial_body_integration.py -q
```

Expected RED: the new result/function import is missing while existing Planner adapter imports succeed.

- [ ] **Step 3: Add the exact Planner-owned aggregate**

In the existing Planner integration module, import the new handoff result/runner and add:

```python
@dataclass(frozen=True, slots=True)
class MinimalIntentWorkerInitialBodyIntegrationResult:
    intent: str
    planner_adapter_record: MinimalPlannerDraftAdapterRecord
    validated_draft: ValidatedPlannerDraft | None
    handoff_result: MinimalCSharpInitialBodyHandoffResult | None
    terminal_stage: str
    terminal_reason: str
```

Its validation equations are exact:

```text
adapter stop:
  draft None, handoff None, stage planner_adapter,
  reason adapter native failure reason

draft stop:
  adapter decoded, draft None, handoff None,
  stage draft_admission,
  reason draft_payload_rejected or goal_mismatch

handoff reached:
  strict loader over retained decoded object reproduces draft,
  draft.goal equals retained intent,
  handoff.draft equals draft,
  stage/reason equal handoff stage/reason
```

Revalidate `intent` with the existing `_require_exact_intent()` and require the retained prompt snapshot to equal `_render_prompt_snapshot(intent)`. There is no state with a retained draft and absent handoff.

- [ ] **Step 4: Implement the exact integration runner**

Add to `__all__` and implement:

```python
async def run_minimal_intent_worker_initial_body_integration(
    intent: str,
    *,
    planner_adapter: MinimalPlannerDraftAdapter,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalIntentWorkerInitialBodyIntegrationResult:
    intent = _require_exact_intent(intent)
    if type(planner_adapter) is not MinimalPlannerDraftAdapter:
        raise TypeError(
            "planner_adapter must be the exact MinimalPlannerDraftAdapter"
        )
    if not callable(getattr(worker_transport, "send", None)):
        raise TypeError("worker_transport must provide callable send")
    if not callable(tool_executor):
        raise TypeError("tool_executor must be callable")

    adapter_record = planner_adapter.produce(intent)
    if adapter_record.status != "decoded":
        return _initial_body_adapter_stop(intent, adapter_record)
    if adapter_record.decoded_object is None:
        raise RuntimeError("decoded Planner adapter record lacks an object")
    try:
        draft = load_minimal_csharp_repair_draft(
            adapter_record.decoded_object
        )
    except (TypeError, ValueError):
        return _initial_body_draft_stop(
            intent,
            adapter_record,
            "draft_payload_rejected",
        )
    if draft.goal != intent:
        return _initial_body_draft_stop(
            intent,
            adapter_record,
            "goal_mismatch",
        )
    handoff = await run_minimal_csharp_initial_body_handoff(
        draft,
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )
    return MinimalIntentWorkerInitialBodyIntegrationResult(
        intent=intent,
        planner_adapter_record=adapter_record,
        validated_draft=draft,
        handoff_result=handoff,
        terminal_stage=handoff.terminal_stage,
        terminal_reason=handoff.terminal_reason,
    )
```

The two private stop helpers construct only the new result type. Do not route through or alter `MinimalIntentWorkerIntegrationResult`.

- [ ] **Step 5: Add the Planner/draft zero-downstream matrix**

Parameterize:

```text
oversized/non-string/blank intent       -> raises before Planner contact
adapter transport failure               -> planner_adapter result
response not string                     -> planner_adapter result
response too large                      -> planner_adapter result
duplicate key/nonfinite/trailing JSON   -> planner_adapter result
non-object JSON                         -> planner_adapter result
missing/extra/wrong draft field         -> draft_payload_rejected
goal mismatch                           -> goal_mismatch
escaped lone-surrogate goal             -> goal_mismatch
adapter subclass/substitute producer    -> raises before contact
```

For every Planner/draft stop assert:

```python
assert result.validated_draft is None
assert result.handoff_result is None
assert worker_transport.calls == []
assert tool_executor.calls == []
```

Use direct string equality for goal matching; never UTF-8 encode untrusted decoded output.

- [ ] **Step 6: Add aggregate valid-red substitutions**

Starting from a valid terminal result, use `dataclasses.replace()` to substitute:

- different retained intent;
- Planner record from another intent;
- decoded object from another valid draft;
- different validated draft;
- handoff from a different transaction;
- mismatched stage;
- mismatched reason;
- validated draft with `handoff_result=None`.

Each must fail in `MinimalIntentWorkerInitialBodyIntegrationResult` validation. Do not replay the handoff's Worker/graph/tool internals here; its exact type owns that validation.

- [ ] **Step 7: Run Task 4 GREEN and existing integration regression**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_initial_body_integration.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py -q
```

Expected: all pass. Confirm the pre-existing integration still delegates only to `run_minimal_csharp_repair_handoff()`.

- [ ] **Step 8: Commit Task 4 and stop for review**

```powershell
git add `
  mcp_server/src/rook/agent/minimal_intent_worker_integration.py `
  mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py
git commit -m "feat: connect Planner intent to Worker initial C# draft"
```

Request review of the two-result ownership split, exact Planner adapter boundary, strict draft admission, direct goal equality, zero-downstream stops, and delegation of handoff lineage before Task 5.

---

### Task 5: Full Regression, Surface Audit, and Plan Reconciliation

**Files:**
- Modify: `docs/superpowers/plans/2026-07-31-minimal-worker-first-csharp-draft.md`
- Inspect only: production imports, registrations, smoke scripts, repair modules, and working tree.

**Interfaces:**
- Consumes: Tasks 1–4 complete merge diff.
- Produces: review-ready branch with verified deterministic behavior and reconciled plan ledger.

- [ ] **Step 1: Run the focused new seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_templates.py `
  mcp_server\tests\test_plan_graph_worker_create_body_apply.py `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py `
  mcp_server\tests\test_minimal_intent_worker_initial_body_integration.py -q
```

Record the exact passing count in this plan. Any failure stops the task.

- [ ] **Step 2: Run the compiler/runner/Worker/repair regression seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py -q
```

Record the exact passing count. Treat existing deprecation warnings as informational only when unchanged.

- [ ] **Step 3: Run smoke and recorder regressions without live flags**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py -q
```

Do not execute any operator script or `--execute-live` flag. Record the exact passing count.

- [ ] **Step 4: Compile changed Python files**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall `
  mcp_server\src\rook\learning\plan_graph_templates.py `
  mcp_server\src\rook\agent\plan_graph_worker_create_body_apply.py `
  mcp_server\src\rook\agent\minimal_csharp_initial_body_handoff.py `
  mcp_server\src\rook\agent\minimal_intent_worker_integration.py `
  mcp_server\tests\test_plan_graph_worker_create_body_apply.py `
  mcp_server\tests\test_minimal_csharp_initial_body_handoff.py `
  mcp_server\tests\test_minimal_intent_worker_initial_body_integration.py
```

Expected: compilation succeeds with no syntax errors.

- [ ] **Step 5: Audit the product surface and prohibited behavior**

Run:

```powershell
rg -n "draft_create_body|gh_csharp_create_verify|run_minimal_csharp_initial_body_handoff|run_minimal_intent_worker_initial_body_integration" `
  mcp_server/src mcp_server/tests scripts

rg -n "gh_update_script|draft_repair_params" `
  mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py `
  mcp_server/src/rook/agent/plan_graph_worker_create_body_apply.py
```

Require:

- new symbols occur only in the intended internal modules, template registry, and tests;
- the second command returns no matches;
- no Chat, MCP, CLI, script, provider constructor, model configuration, readiness, archive, or recorder registration was added;
- existing repair module source is unchanged in the merge diff;
- the topology-guidance hypothesis remains documentation-only.

- [ ] **Step 6: Inspect transaction ownership manually**

From the deterministic success and compile-failure test objects, inspect:

```text
exact intent
-> one Planner adapter record
-> one strict validated draft
-> exact incomplete scaffold with no code
-> one Worker request/adapter/harness record
-> one draft_create_body disposition
-> pure applied graph whose original projection is unchanged
-> one create request containing Worker code
-> one native create receipt
-> one verifier record
-> terminal done OR selector_halt:none_ready
```

Confirm the original scaffold contains no code, the Worker response is the sole code authority, the applied graph is the first graph-state occurrence, and any later copy is native record propagation rather than a parallel aggregate field.

- [ ] **Step 7: Verify Git scope and reconcile this plan**

```powershell
git diff --check
git status --short
git diff --name-status fb52d278...HEAD
git rev-parse HEAD
```

Mark every completed checkbox in this plan. Add a final execution ledger containing:

- Task commit SHAs;
- exact focused/regression/smoke test counts;
- compilation result;
- merge-diff file list;
- final HEAD;
- statement that no external contact occurred;
- statement that results are ephemeral and no live/product surface was added.

- [ ] **Step 8: Commit the docs-only reconciliation**

```powershell
git add docs/superpowers/plans/2026-07-31-minimal-worker-first-csharp-draft.md
git commit -m "docs: reconcile Worker-first C# draft plan"
```

If reconciliation exposes a code defect, fix it in a separate bounded code commit, rerun the affected RED/GREEN and full verification, then update the ledger.

- [ ] **Step 9: Stop for final independent implementation review**

Do not push, open a PR, merge, register a product surface, or perform a live test until the complete implementation diff and recorded verification are independently approved.

---

## Completion Criteria

- [ ] One exact Planner draft reaches the new initial-body handoff.
- [ ] The new template is exactly `create_script -> verify_create -> done` with two `requires` edges.
- [ ] The compiled create node lacks only `code` and retains no body-mode parameter.
- [ ] One Worker action supplies only `draft_create_body.input.code`.
- [ ] The original scaffold remains unchanged; the pure returned graph is an exact parameter union.
- [ ] The Worker response is the sole code authority; no aggregate copies code into a parallel field.
- [ ] Worker refusal or invalid output produces zero tool calls.
- [ ] Execution performs zero or one create call and never performs update.
- [ ] Verification evaluates the create receipt without another tool call.
- [ ] Clean receipt reaches `done`; compile-error receipt stops unsuccessfully without repair.
- [ ] `MinimalCSharpInitialBodyHandoffResult` and `MinimalIntentWorkerInitialBodyIntegrationResult` enforce their separate ownership boundaries.
- [ ] Existing repair and smoke behavior remains unchanged.
- [ ] No external contact occurs during implementation or review.
- [ ] The plan ledger, test counts, scope, and final HEAD are reconciled before PR work.
