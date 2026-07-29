# Minimal C# Repair-Capability Planner/Worker Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use Markdown checkboxes for tracking.

**Goal:** Add one internal product compositor that takes an exact validated four-field Planner draft through the existing C# create/verify workflow, one real worker adapter/harness/action turn, and the existing repair/reverify terminal path.

**Architecture:** A new module under `rook.agent` owns only the strict draft boundary, the private repair specimen contract, deterministic worker-instruction assembly, a two-phase use of the existing current-step stream, and a thin aggregate result. Existing workflow compilation, template selection, PlanGraph execution, worker prompt/response handling, action application, tool dispatch, and receipt interpretation remain the sole behavioral authorities.

**Tech Stack:** Python 3.12, frozen dataclasses, existing `rook.agent` and `rook.learning` modules, `pytest`, `pytest-asyncio`, injected test-only worker transport and tool executor.

## Global Constraints

**Design:** `docs/superpowers/specs/2026-07-28-minimal-csharp-repair-handoff-design.md`

**Development lane:** `C:/UDEV/Rook/.worktrees/minimal-planner-worker-handoff-design` on `codex/minimal-planner-worker-handoff-design`. Do not modify, stash, reset, clean, or reuse the primary checkout.

**Test interpreter:** The isolated worktree reuses the environment executable at `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe`; commands run with the isolated worktree as their current directory and do not modify primary-checkout source files.

**Authorization boundary:** Offline implementation and deterministic fake-backed tests only. Do not add or invoke Chat, MCP, CLI, providers, readiness, Rhino, Grasshopper, or live worker transports.

---

## Constructive reachability ledger

Every supported transition must retain its real producer and consumer:

| Claim or value | Producer | Consumer/proof |
|---|---|---|
| Valid Planner draft | `load_minimal_csharp_repair_draft()` | Exact-type guard in compositor |
| Workflow topology | `_build_repair_specimen_contract()` + existing contract compiler | `CompiledWorkflowScaffold` and compile record |
| Invalid initial C# body | Private code-owned constant | Fake create tool receives it through real typed dispatch |
| Create diagnostic and GUID | Fake create tool's receipt, causally derived from received request | Existing receipt projection and acceptance-source extractor |
| Worker instruction | Draft goal + compiled interface + one convention packet + actual receipt | Existing context/request/prompt renderers |
| Repair code | Loaded worker action response | Existing disposition and `apply_worker_action_to_node()` |
| Repair GUID | Existing create receipt | Controller-supplied anchor binding only |
| Clean result | Fake update tool's existing receipt shape | Existing producer/verifier projection and terminal provider halt |
| Terminal reason | Native adapter/disposition/action/stream record | Thin result projection with no new outcome vocabulary |

An authored summary never substitutes for the native record that owns the claim.

The complete transaction line is:

```text
validated draft
-> compiled contract/scaffold
-> actual create request
-> actual create receipt
-> closed diagnostic/GUID projections
-> actual worker request
-> adapter-loaded response
-> disposition
-> action-applied graph
-> second execution segment
-> concatenated native ledger
```

Apply three rules throughout every task:

1. No parallel reconstruction.
2. No broad mapping passed across a narrower boundary.
3. No execution prefix discarded.

---

### Task 1: Walk the complete repair path vertically

**Files:**

- Create: `mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py`
- Create: `mcp_server/tests/test_minimal_csharp_repair_handoff.py`

**Interfaces:**

- Consumes: `RookWorkflowContract`, `compile_workflow_contract()`, `run_current_step_stream()`, `LocalWorkerTransport`, `run_local_worker_adapter()`, `run_local_worker_turn()`, `apply_worker_action_to_node()`, and `run_live_producer_node_with_executor()`.
- Produces: `PlannerDraftOutput`, `PlannerDraftInterface`, `ValidatedPlannerDraft`, `MinimalCSharpRepairHandoffResult`, `load_minimal_csharp_repair_draft(payload)`, and `run_minimal_csharp_repair_handoff(draft, *, worker_transport, tool_executor)`.

The public internal signature is exact:

```python
async def run_minimal_csharp_repair_handoff(
    draft: ValidatedPlannerDraft,
    *,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalCSharpRepairHandoffResult:
    ...
```

The module `__all__` contains only the four public dataclasses plus the loader
and compositor. Contract/knowledge/runner helpers and fixture constants remain
private.

This task intentionally builds the thinnest complete offline transaction first. Later tasks harden its input, information, and failure boundaries.

### Step 1: Write a valid-red end-to-end witness

- [x] Add a test-only `FakePlanner` helper that returns the exact raw mapping. It is not passed into production code; the test calls the strict loader itself.
- [x] Add a recording `FakeWorkerTransport.send(prompt_artifact)` that returns one raw JSON action response containing all required fields:

```python
{
    "schema": "rook.local_worker_turn_response:v1",
    "kind": "action_request",
    "action_id": "draft_repair_params",
    "rationale": "Replace the invalid body while preserving A:double.",
    "input": {"code": "A = 42.0;", "mode": "body"},
}
```

- [x] Add a recording fake tool executor that derives its create receipt from the request it actually receives:

```python
def __call__(self, tool_name: str, params: dict[str, object]) -> dict[str, object]:
    self.calls.append((tool_name, copy.deepcopy(params)))
    if tool_name == "gh_create_csharp_script":
        assert params["code"] == "A = DefinitelyMissingSymbol;"
        diagnostic = (
            "The name 'DefinitelyMissingSymbol' does not exist in the current context"
        )
        return created_with_errors_receipt(
            guid=self.guid,
            target_errors=[diagnostic],
        )
    if tool_name == "gh_update_script":
        assert params == {
            "guid": self.guid,
            "code": "A = 42.0;",
            "mode": "body",
            "language": "csharp",
        }
        return usable_clean_receipt(guid=self.guid)
    raise AssertionError(f"unexpected tool: {tool_name}")
```

The receipt helpers live in the test file and return the existing `script_receipt` shapes. Do not import probe fixtures or add production fake behavior.

- [x] Assert the complete observed path:

```python
raw = FakePlanner().draft()
draft = load_minimal_csharp_repair_draft(raw)
result = await run_minimal_csharp_repair_handoff(
    draft,
    worker_transport=worker_transport,
    tool_executor=tool_executor,
)

assert result.terminal_stage == "terminal"
assert result.terminal_reason == "terminal_node_selected:done"
assert result.final_graph.nodes["done"].status == "ready"
assert [name for name, _ in tool_executor.calls] == [
    "gh_create_csharp_script",
    "gh_update_script",
]
assert len(worker_transport.calls) == 1
assert result.worker_record.disposition.disposition == "candidate_action_request"
assert result.action_apply_result.applied is True
assert [record.accepted_node_id for record in result.step_records] == [
    "create_script",
    "verify_create",
    "repair_same_component",
    "verify_repair",
]
assert result.step_records[-1].verifier_outcome_status == "succeeded"
assert result.supply_records[-1].decision == "HALT"
assert result.supply_records[-1].reason == "terminal_node_selected:done"
```

### Step 2: Run the test and prove the red is the missing product module

- [x] Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py -q
```

- [x] Expected RED: collection fails with `ModuleNotFoundError` for `rook.agent.minimal_csharp_repair_handoff`. An unrelated fixture, import, or test-construction failure is not a valid red state.

### Step 3: Add the exact immutable draft types and strict loader

- [x] Define the minimum public types in the new module:

```python
@dataclass(frozen=True)
class PlannerDraftOutput:
    name: Literal["A"]
    type: Literal["double"]


@dataclass(frozen=True)
class PlannerDraftInterface:
    inputs: tuple[()]
    outputs: tuple[PlannerDraftOutput, ...]


@dataclass(frozen=True)
class ValidatedPlannerDraft:
    goal: str
    capability: Literal["grasshopper_csharp_component"]
    interface: PlannerDraftInterface
    acceptance: Literal["clean_compile_receipt"]
```

Each dataclass validates direct construction in `__post_init__`, snapshots owned tuples, and rejects subclasses at the compositor boundary. The loader requires exact field sets at every level; strings are not treated as generic sequences.

- [x] Implement:

```python
def load_minimal_csharp_repair_draft(
    payload: Mapping[str, Any],
) -> ValidatedPlannerDraft:
    ...
```

The exact accepted payload is:

```python
{
    "goal": <non-empty string>,
    "capability": "grasshopper_csharp_component",
    "interface": {
        "inputs": [],
        "outputs": [{"name": "A", "type": "double"}],
    },
    "acceptance": "clean_compile_receipt",
}
```

### Step 4: Add the pure specimen contract and runner adapter

- [x] Add private constants for the fixed workflow, descriptor, template, node IDs, initial body, action ID, interface, and convention packet. The initial body has no injection or configuration path:

```python
_SPECIMEN_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_WORKFLOW_ID = "minimal_csharp_repair_handoff"
_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"
_ACTION_ID = "draft_repair_params"
```

The one convention packet is constructed exactly once per handoff and is both
visible knowledge and the acceptance-source input:

```python
WorkerKnowledgePacket(
    packet_id="script_body_gotcha",
    kind="gotcha",
    title="C# script components use body-style code",
    content={"body_mode": "body"},
)
```

- [x] Implement `_build_repair_specimen_contract(draft)` as a pure constructor. The repair rule is exactly:

```python
WorkflowNodeRule(
    "repair_same_component",
    (ProducerStepSpec("repair_same_component"),),
)
```

It contains no `BindStepSpec`; only `create_script` has initial execution parameters.

- [x] Add a private runner adapter that owns no outcome policy:

```python
@dataclass(frozen=True)
class _ToolExecutorRunner:
    tool_executor: Callable[[str, dict[str, Any]], Any]

    async def run_live_producer_node(
        self,
        graph: PlanGraph,
        node_id: str,
    ) -> LiveProducerResult:
        return await run_live_producer_node_with_executor(
            graph,
            node_id,
            self.tool_executor,
        )
```

### Step 5: Add the exact result carrier and minimum compositor

- [x] Define `MinimalCSharpRepairHandoffResult` with the exact fields and stage literal approved by the design. Add `__post_init__` checks for the optional-field equations so impossible combinations raise instead of becoming operational results.

- [x] Implement the successful path as two uses of the real current-step stream:

```text
phase 1, max_steps=2
  create_script -> verify_create -> repair frontier

worker splice
  acceptance sources -> context -> request -> adapter -> harness
  -> disposition -> receipt GUID + action -> staged repair graph

phase 2
  repair_same_component -> verify_repair -> terminal provider halt
```

Phase 1 must require its exact successful frontier before calling a worker:

```python
phase_one = await run_current_step_stream(
    scaffold.graph,
    scaffold.provider,
    max_steps=2,
    runner=runner,
)
```

The expected internal pause is `max_steps_reached` with accepted node IDs `create_script`, `verify_create`, and a graph whose only next ready nonterminal node is `repair_same_component`. Other states return the appropriate existing operational result or raise if the native records are contradictory.

- [x] Build the worker knowledge from real sources:

  - one code-owned `script_body_gotcha` packet;
  - one immutable Planner goal/interface packet;
  - `extract_acceptance_criteria_sources()` over the actual post-create graph;
  - `assemble_acceptance_criteria_packet()` over those sources;
  - one acceptance packet wrapping that existing packet;
  - one current-diagnostic packet projecting the exact admitted
    `sources.receipt_diagnostic.value` without rereading the graph;
  - exactly one `WorkerAllowedAction` for `draft_repair_params`.

Project the worker-visible interface from the actual compiled create
parameters, and prove it equals the validated draft before rendering it:

```python
compiled_create_params = scaffold.graph.nodes["create_script"].metadata[
    EXECUTION_PARAMS_KEY
]
compiled_interface = {
    "inputs": [
        _pin_from_contract_token(token)
        for token in compiled_create_params["pins_in"]
    ],
    "outputs": [
        _pin_from_contract_token(token)
        for token in compiled_create_params["pins_out"]
    ],
}
if compiled_interface != _render_draft_interface(draft.interface):
    raise RuntimeError("compiled create interface differs from validated draft")
```

For this fixed specimen `_pin_from_contract_token("A:double")` produces the
closed `{"name": "A", "type": "double"}` row and rejects every malformed token.
The goal/interface packet renders `compiled_interface`, never a second literal.

The goal/interface and action rows are:

```python
goal_packet = WorkerKnowledgePacket(
    packet_id="planner_goal_and_interface",
    kind="requirement",
    title="Planner goal and fixed component interface",
    content={
        "goal": draft.goal,
        "interface": compiled_interface,
    },
)
allowed_action = WorkerAllowedAction(
    action_id="draft_repair_params",
    kind="draft_repair_params",
    description="Draft a complete replacement C# body.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "code": {"type": "string"},
            "mode": {"const": "body"},
        },
        "required": ["code", "mode"],
    },
)
```

The same `_script_body_gotcha_packet()` instance is passed to acceptance extraction and worker knowledge. Do not duplicate `mode: body` independently.

- [x] Immediately after extracting the existing sources, enforce the explicit
  convention equality that the existing extractor does not own:

```python
packet_mode = convention_packet.content["body_mode"]
extracted_mode = sources.convention.value["mode"]
if packet_mode != extracted_mode:
    raise RuntimeError("worker convention mode differs from acceptance source")
```

- [x] Render the request with `render_local_worker_turn_request_payload()`, call `run_local_worker_adapter()` once, then—only for `response_loaded`—call `run_local_worker_turn(context, lambda _: adapter_record.response)` once. The callback performs no transport or parsing.

- [x] Project rather than pass through the receipt anchor. Require the receipt
  GUID to equal the graph-memory repair-anchor GUID, then construct exactly:

```python
receipt_anchor = create_receipt["repair_anchor"]
memory_anchor = phase_one.final_graph.memory.facts["repair_anchor"]
if receipt_anchor["component_guid"] != memory_anchor["component_guid"]:
    raise RuntimeError("receipt and graph-memory repair anchors differ")
anchor_binding = {
    "component_guid": receipt_anchor["component_guid"],
    "language": "csharp",
}
```

Pass only `action_id`, validated `input`, and `anchor_binding` into
`apply_worker_action_to_node()`. Never pass either broad anchor mapping. Resume
the real current-step stream on `action_apply_result.graph`.

- [x] Concatenate, never replace, both native execution ledgers:

```python
step_records = phase_one.records + phase_two.records
supply_records = phase_one.supply_records + phase_two.supply_records
```

On success assert the step order is exactly `create_script`, `verify_create`,
`repair_same_component`, `verify_repair`, followed by the terminal HALT supply
record. Every early return retains the complete prefix collected before its
terminal stage.

### Step 6: Run the vertical and focused baseline

- [x] Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py -q

& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_gh_edit_contract.py `
  mcp_server\tests\test_plan_graph_workflow_contract_chain.py `
  mcp_server\tests\test_plan_graph_live_dispatch.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py -q
```

- [x] Expected: new vertical passes; established focused baseline remains at least its pre-implementation `222 passed` with only the new test count added where applicable.

### Step 7: Commit the walking skeleton and stop for review

- [x] Inspect `git diff --check` and `git status --short`.
- [x] Commit only the new production module and focused test:

```powershell
git add mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py `
        mcp_server/tests/test_minimal_csharp_repair_handoff.py
git commit -m "feat: compose minimal C# repair handoff"
```

- [x] Mandatory review checkpoint: independently inspect the real prompt, tool calls, receipts, repair-code source, and terminal records before Task 2. Do not harden forward on top of a fake or bypassed vertical.

---

### Task 2: Close the draft and deterministic compiler boundaries

**Files:**

- Modify: `mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py`
- Modify: `mcp_server/tests/test_minimal_csharp_repair_handoff.py`

**Interfaces:**

- Consumes: Task 1's draft dataclasses, loader, private contract builder, compositor, and recording fakes.
- Produces: a closed loader/direct-construction boundary and a constructively proven compiler-owned contract with no repair bind or staged repair parameters.

### Step 1: Write the invalid-draft and direct-construction table

- [x] Parameterize mutations for:

  - raw non-mappings;
  - missing or extra top-level fields;
  - empty/non-string goal;
  - wrong capability;
  - non-mapping or extra-field interface;
  - nonempty inputs;
  - missing, extra, duplicated, or malformed output rows;
  - output name other than `A`;
  - output type other than `double`;
  - wrong acceptance;
  - Planner-supplied `code`, template, graph, action, worker, routing, GUID, or execution parameter fields;
  - forged direct dataclass values and subclasses.

- [x] Every case must establish zero downstream capability use:

```python
assert worker_transport.calls == []
assert tool_executor.calls == []
```

The invalid raw cases stop in the loader. Exact-type/subclass cases stop at compositor entry before `_build_repair_specimen_contract()`, worker construction, or tool execution.

### Step 2: Run the table and confirm valid red failures

- [x] Run the new loader/compiler selection with `-k "draft or contract"`.
- [x] Expected RED: missing strict checks or direct-construction invariants, not fake failures.

### Step 3: Harden the loader without adding a schema framework

- [x] Add small private helpers such as `_require_exact_fields()`, `_require_mapping()`, and `_require_non_empty_string()` inside the module. Do not add JSON Schema, a registry, a new draft version family, or external dependencies.
- [x] Use exact field admission rather than permissive `.get()` checks:

```python
def _require_exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    observed = set(value)
    if observed != expected:
        raise ValueError(
            f"{context} fields must be exactly {sorted(expected)!r}; "
            f"observed {sorted(observed)!r}"
        )
```

- [x] Keep error types deterministic (`TypeError` for wrong container/value types; `ValueError` for wrong admitted values/field sets).
- [x] Snapshot the accepted interface into the exact frozen dataclasses; mutation of the input mapping after load must not affect the draft.

### Step 4: Prove compiler ownership and sole-source repair authority

- [x] Add tests that build contracts for two different valid goals and compare their normalized snapshots. They must be identical because goal is worker-visible knowledge, not workflow authorship.
- [x] Assert:

```python
contract = _build_repair_specimen_contract(draft)
scaffold = compile_workflow_contract(contract)

assert scaffold.compile_record.selected_template_id == (
    "gh_csharp_create_verify_repair_verify"
)
assert create_params["code"] == "A = DefinitelyMissingSymbol;"
assert create_params["pins_in"] == ()
assert create_params["pins_out"] == ("A:double",)

repair_rule = next(r for r in contract.rules if r.node_id == "repair_same_component")
assert repair_rule.steps_by_seen_count == (
    ProducerStepSpec("repair_same_component"),
)
assert not any(isinstance(step, BindStepSpec) for step in repair_rule.steps_by_seen_count)
assert EXECUTION_PARAMS_KEY not in scaffold.graph.nodes["repair_same_component"].metadata
```

- [x] Prove no production branch recognizes goal wording or fixture values except the one private code constant and exact fixed capability/interface checks. A source scan is secondary evidence; contract equality is authoritative.

### Step 5: Run and commit

- [x] Run the new file and the workflow contract/compiler suites.
- [x] Run `git diff --check`.
- [x] Commit:

```powershell
git add mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py `
        mcp_server/tests/test_minimal_csharp_repair_handoff.py
git commit -m "test: close repair handoff draft authority"
```

---

### Task 3: Close worker visibility and response custody

**Files:**

- Modify: `mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py`
- Modify: `mcp_server/tests/test_minimal_csharp_repair_handoff.py`

**Interfaces:**

- Consumes: Task 1's successful worker splice and Task 2's closed validated draft/compiler boundary.
- Produces: a recursively tested real prompt boundary, one-source body convention, and exact adapter-to-harness response custody.

### Step 1: Capture and recursively inspect the real serialized request

- [x] In the recording fake transport, retain the exact prompt artifact and decode only its existing user message for assertions.
- [x] Require the user message to be the canonical serialization of `result.worker_request`:

```python
expected_user = json.dumps(
    dict(result.worker_request),
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
)
assert transport.prompt["messages"][1] == {
    "role": "user",
    "content": expected_user,
}
```

- [x] Assert the request contains:

  - exact immutable goal;
  - fixed `inputs: []`, `outputs: [{name: A, type: double}]`;
  - the convention-derived body mode;
  - the existing acceptance packet and its fingerprint;
  - the actual target diagnostic from the create receipt;
  - exactly one allowed action with ID/kind `draft_repair_params`.

### Step 2: Prove the exclusions against all keys and scalar values

- [x] Add a recursive walker over test data and reject appearance of:

  - `A = DefinitelyMissingSymbol;`;
  - any concrete initial or expected repair code value;
  - any execution-parameter object containing the initial `code` field;
  - the create component GUID;
  - graph `edges` or `rules`;
  - staged execution parameters;
  - expected repair code;
  - deterministic repair suggestions.

Permit the current opaque identity/status summaries already rendered by `LocalWorkerTurnContext`, including compiler/provider/template IDs, node IDs, ready IDs, and terminal IDs. The test must not mislabel those existing fields as hidden topology authorship.
Also permit the word `code` only in the existing response/action schema that
tells the worker which field it may author. A schema property is not leaked
code or an initial execution parameter; the test must distinguish the path
from a concrete code value.

### Step 3: Prove one convention source owns both body-mode claims

- [x] Arrange the production helper so one local `WorkerKnowledgePacket` instance is:

  1. passed to `extract_acceptance_criteria_sources()`;
  2. included in the context knowledge;
  3. the source of the visible body-mode packet.

- [x] Add a valid-red mutation that changes
  `convention_packet.content.body_mode` before assembly and prove the
  compositor's explicit packet/extracted-source equality rejects it before
  worker contact. Do not claim the existing extractor or acceptance assembler
  validates packet content; do not add a new acceptance system.

### Step 4: Close adapter, response, and rationale behavior

- [x] Add tests for missing each required action-response field: `schema`, `kind`, `action_id`, `rationale`, and `input`; extra fields; wrong schema/kind/action; malformed input; and `mode != body`.
- [x] Prove raw JSON traverses `run_local_worker_adapter()` before the harness; no production test directly constructs the successful `LocalWorkerTurnResponse`.
- [x] Return two otherwise identical responses with different `rationale` values and assert action application stages identical execution parameters and `params_sha256`. The loaded response retains each rationale, but rationale never enters application.
- [x] Verify exactly one transport call and one harness/disposition evaluation. The one-shot harness callback must return the adapter's exact loaded response object by identity.

### Step 5: Run and commit

- [x] Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py -q
```

- [x] Run `git diff --check` and commit:

```powershell
git add mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py `
        mcp_server/tests/test_minimal_csharp_repair_handoff.py
git commit -m "test: close repair worker information boundary"
```

---

### Task 4: Make terminal results total and native-reason preserving

**Files:**

- Modify: `mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py`
- Modify: `mcp_server/tests/test_minimal_csharp_repair_handoff.py`

**Interfaces:**

- Consumes: Task 1's result carrier/compositor plus the native stream, adapter, disposition, and action records exercised in Tasks 2–3.
- Produces: a total operational stop matrix, exact native reason projection, and enforced result optional-field equations.

### Step 1: Build a stage-by-stage stop matrix

- [x] Parameterize the following operational cases using recording fakes and native record mutation only at the owning seam:

| Case | Expected terminal stage | Native reason owner | Downstream zero-call assertion |
|---|---|---|---|
| create tool raises/refuses/malformed receipt | `create` | create `CurrentStepRecord` or supply record | no worker, no update |
| verify-create cannot produce the repair frontier | `verify_create` | verifier/current supply record | no worker, no update |
| declared transport error | `worker_adapter` | `LocalWorkerAdapterRecord.failure_reason` | no harness/action/update |
| invalid raw JSON or response payload | `worker_adapter` | adapter failure reason | no harness/action/update |
| clarification/refusal/observation | `worker_disposition` | exact disposition reason | no action/update |
| unknown action ID | `worker_disposition` | exact blocked disposition reason | no action/update |
| loaded action has unsupported keys, blank code, or wrong mode | `action_apply` | `WorkerActionApplyResult.reason` | no update |
| repair dispatch/receipt refuses | `repair` | repair current-step/supply reason | verify-repair not run |
| verify-repair stops | `verify_repair` | verifier/current supply reason | no terminal success claim |
| done selected | `terminal` | `terminal_node_selected:done` | exactly one worker and two tools total |

- [x] Expected operational stops return a `MinimalCSharpRepairHandoffResult`. Contract compilation failure, forged result-state combinations, or impossible record ownership raise.

### Step 2: Define one closed native-reason projection helper

- [x] Implement small private helpers that inspect the owning existing record, for example:

```python
def _current_step_reason(record: CurrentStepRecord) -> str:
    for value in (
        record.execution_failure,
        record.mapping_failure,
        record.producer_reason,
        record.verifier_reason,
        record.bind_reason,
    ):
        if value is not None:
            return value
    raise RuntimeError("current-step stop lacks a native reason")
```

Use a stage-specific order rather than this illustrative generic order if multiple reason fields can coexist. Never synthesize `planner_failure`, `worker_failure`, `success`, or another parallel taxonomy.

- [x] Supply-owned stops retain exact `reason` when present, otherwise the exact existing `invalid_reason`. Adapter, disposition, and action stages use the fields pinned in the design.

### Step 3: Enforce the exact optional-field equations

- [x] Add `MinimalCSharpRepairHandoffResult.__post_init__` tests for every valid row and representative invalid cross-product combinations:

  - early stages cannot carry worker records;
  - adapter failure cannot carry worker/action records;
  - disposition stage requires a loaded adapter and a non-candidate disposition;
  - action-apply rejection requires a candidate disposition and `applied=False`;
  - repair/verify/terminal require loaded adapter, candidate disposition, and `applied=True`;
  - no result duplicates receipt evidence.

- [x] Confirm final graph and native records retain receipt ownership. The result class has no receipt, diagnostic, GUID, or classification field.

### Step 4: Prove terminal truthfulness

- [x] Assert on success:

```python
assert result.step_records[-1].verifier_node_id == "verify_repair"
assert result.step_records[-1].verifier_outcome_status == "succeeded"
assert result.supply_records[-1].decision == "HALT"
assert result.supply_records[-1].reason == "terminal_node_selected:done"
assert result.final_graph.nodes["done"].status == "ready"
```

- [x] Assert the compositor does not apply a synthetic done outcome and does not claim `graph_status == complete`.

### Step 5: Run and commit

- [x] Run the new file plus current-step, action, and receipt-focused suites.
- [x] Run `git diff --check`.
- [x] Commit:

```powershell
git add mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py `
        mcp_server/tests/test_minimal_csharp_repair_handoff.py
git commit -m "test: close repair handoff terminal semantics"
```

---

### Task 5: Audit the product boundary and prepare review

**Files:**

- Modify only if review exposes a concrete defect:
  - `mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py`
  - `mcp_server/tests/test_minimal_csharp_repair_handoff.py`

**Interfaces:**

- Consumes: the complete implementation and evidence from Tasks 1–4.
- Produces: fresh focused/broader verification evidence and a review-ready two-module product change with no public/live integration.

### Step 1: Run the complete focused suite

- [x] Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_gh_edit_contract.py `
  mcp_server\tests\test_plan_graph_workflow_contract_chain.py `
  mcp_server\tests\test_plan_graph_live_dispatch.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py `
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py -q
```

- [x] Record exact passed/failed/skipped counts. Do not report the historical `222 passed` as a new result unless the fresh command proves it.

### Step 2: Run the broader Python agent regression

- [x] Run the complete relevant agent family, not live Rhino tests:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests -q `
  -k "plan_graph or local_worker or workflow_contract or gh_edit_contract or minimal_csharp_repair_handoff"
```

- [x] If the command exceeds a practical review timeout, report the timeout honestly and preserve the complete focused result. Do not call a timed-out run passed.

### Step 3: Audit imports and product-surface scope

- [x] Verify the new production module imports no:

  - `scripts` or probe modules;
  - Chat registration or runner modules;
  - MCP server/tool registration;
  - LiteLLM/provider/model construction;
  - readiness or credential code;
  - Rhino/Grasshopper runtime client;
  - LM9 artifacts;
  - fake transport/tool behavior.

- [x] Verify the branch adds no Chat registration, MCP tool, CLI, template, action, registry, archive, or public provider surface:

```powershell
git diff --name-only d68459a9fe074e5a5107c991125a625c7463c430...HEAD
rg -n "scripts\.|LiteLLM|readiness|mcp.tool|click|argparse|Fake|LM9" `
  mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py
```

Expected source diff after implementation remains one production module, one test module, the approved specification, and this plan unless a reviewed concrete dependency requires otherwise.

### Step 4: Inspect the exact success witness

- [x] From test-held records, manually verify:

```text
raw draft
-> exact validated type
-> real workflow compile record
-> create call containing private invalid body
-> actual create receipt diagnostic/GUID
-> real prompt artifact excluding body/GUID/topology
-> one raw worker response loaded by real adapter
-> one candidate disposition
-> action-applied params containing worker code + receipt GUID
-> update call
-> clean receipt
-> verify_repair succeeded
-> terminal_node_selected:done
```

- [x] Confirm neither model authored or altered graph topology, while existing opaque context identities remain truthfully visible.

### Step 5: Verify repository state and commit any final bounded correction

- [x] Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall `
  mcp_server\src\rook\agent\minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py
git diff --check
git status --short
```

- [x] If Task 5 required no code changes, do not create an empty commit. If it required a reviewed bounded correction, rerun the affected red/green test and commit only that correction:

```powershell
git add mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py `
        mcp_server/tests/test_minimal_csharp_repair_handoff.py
git commit -m "fix: close minimal repair handoff review findings"
```

### Step 6: Stop for independent review

- [x] Request review of the complete merge diff against base `d68459a9fe074e5a5107c991125a625c7463c430`.
- [x] Do not expose the compositor through Chat, MCP, CLI, or a live worker test in this branch.
- [x] Do not merge until the review confirms the causal tool/worker path, worker visibility boundary, repair-code sole-source equation, terminal truthfulness, and focused regression evidence.

---

## Completion criteria

This implementation slice is complete only when all are true:

- [x] The raw four-field payload is accepted only through the strict loader.
- [x] The compositor rejects raw/forged drafts before capabilities are invoked.
- [x] The private invalid body is compiler-owned and goal-independent.
- [x] The real existing workflow compiler/template/provider/current-step runners are used.
- [x] The create diagnostic and GUID come from the typed tool receipt caused by the received request.
- [x] The real prompt renderer, adapter, response loader, harness, and disposition are traversed exactly once.
- [x] The worker request excludes body, GUID, graph topology, staged parameters, and deterministic repair answers.
- [x] Repair code comes only from the accepted worker action; the GUID comes only from receipt authority.
- [x] The existing action application is the only repair-parameter staging path.
- [x] The existing clean receipt, verifier, and terminal provider halt establish the narrow success.
- [x] Every expected stop preserves its native reason and zero downstream calls.
- [x] The result optional-field equations are enforced and no receipt evidence is copied.
- [x] Focused and broader relevant tests are freshly reported.
- [x] No live contact or new public product surface was introduced.

---

## Execution reconciliation

Reconciled on 2026-07-29 after completion of Tasks 1–5:

- Base: `d68459a9fe074e5a5107c991125a625c7463c430`.
- Verified implementation HEAD before this docs-only reconciliation:
  `683f4c2dc93d929ba2080e4fd5a447c14ca38918`.
- Complete focused command above, including
  `test_plan_graph_current_step_runner.py`: **492 passed in 1.39s**.
- Broader relevant Python-agent regression: **1,217 passed, 8,228
  deselected, 11 pre-existing DSPy deprecation warnings in 49.54s**.
- Python compilation, working-tree and merge-diff `git diff --check`, import
  audit, product-surface audit, and exact success-transaction inspection
  passed.
- The shared `project_current_step_record()` extraction is the reviewed
  concrete dependency that expands the implementation diff to two production
  modules. It preserves the existing runner path while providing one pure
  native-record projection for transaction validation.
- `MinimalCSharpRepairHandoffResult` is an ephemeral internal transaction
  aggregate over existing native records. It is not a durable evidence object,
  an immutable evidence claim, or a public integration surface.
- No Chat, MCP, CLI, provider, live worker-box, Rhino, or Grasshopper contact
  occurred.
