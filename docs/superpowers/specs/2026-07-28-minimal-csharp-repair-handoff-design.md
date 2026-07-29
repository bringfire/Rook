# Minimal C# Repair-Capability Planner/Worker Handoff Design

- **Date:** 2026-07-28
- **Status:** Approved design captured for independent specification review; implementation planning has not begun
- **Base:** `origin/main` at `d68459a9fe074e5a5107c991125a625c7463c430`
- **Branch:** `codex/minimal-planner-worker-handoff-design`
- **Scope:** One internal, callable C# repair-capability handoff using the existing workflow compiler, PlanGraph runners, one bounded worker turn, existing action application, typed tool dispatch, and receipt interpretation
- **Authorization:** Specification work only. No provider, Planner, worker model, readiness, Rhino, Grasshopper, MCP, CLI, or product mutation contact is authorized

## 1. Purpose

Rook already has the principal parts of a bounded Planner/worker path:

```text
RookWorkflowContract
-> compile_workflow_contract()
-> CompiledWorkflowScaffold
-> CatalogCurrentStepProvider
-> current-step runner
-> typed tool executor
```

and:

```text
LocalWorkerTurnContext
-> worker request/response contracts
-> response disposition
-> apply_worker_action_to_node()
```

The missing product seam is their composition. The complete worker splice has
previously existed in experimental scripts, but no production module under
`mcp_server/src/rook/agent` joins a validated Planner artifact to the existing
workflow, worker, action, and receipt paths.

This slice adds that composition for one existing capability only:

> Create a Grasshopper C# component with the declared `A:double` output shape
> and obtain a clean compile receipt through exactly one bounded worker repair.

Earlier create or verification stops may prevent the worker turn. Because the
private initial body is deliberately invalid, every successful path necessarily
enters the worker exactly once.

This is the first **repair-path specimen**. It is not a general Planner
contract, a general worker runtime, or the future normal C# creation path.

## 2. Falsifiable hypothesis

> A strict four-field semantic draft can be deterministically compiled into
> the existing C# create/verify/repair/reverify workflow, resolved by one
> bounded worker action, executed through existing PlanGraph and typed-tool
> seams, and terminated by the existing clean-receipt path without allowing
> either model to author or alter workflow topology.

The existing worker context may expose opaque workflow identity and status
summaries, including compiler, provider, template, node, ready-node, and
terminal-node identities. Those summaries are accepted existing behavior.
Neither model receives or authors graph edges, graph rules, staged execution
parameters, fixture code, component GUIDs, action wiring, or compiler
internals.

The hypothesis is falsified for this slice if the deterministic vertical
cannot traverse the exact existing components without introducing another
template, action, runner, receipt type, or scenario-specific scripts harness.

## 3. Current product seams

| Seam | Current status | Use in this slice |
|---|---|---|
| `RookWorkflowContract` and `compile_workflow_contract()` | Production module; deterministically selects and compiles registered templates | Reused unchanged |
| `gh_csharp_create_verify_repair_verify` | Existing registered PlanGraph template | Reused unchanged |
| `CatalogCurrentStepProvider` and current-step runner | Existing deterministic selection, mapping, execution, and records | Reused unchanged |
| `run_live_producer_node_with_executor()` | Existing bridge from PlanGraph producer nodes to injected typed tool execution | Reused unchanged |
| `LocalWorkerTurnContext` and request renderer | Existing bounded worker-visible context | Reused unchanged |
| Worker response loader, harness, and disposition | Existing closed response and outcome semantics | Reused unchanged |
| `draft_repair_params` and `apply_worker_action_to_node()` | Existing C# body candidate validation and deterministic GUID binding | Reused unchanged |
| Existing script receipt interpretation | Existing create, repair, and verification evidence | Reused unchanged |
| LM7A request/materializer and LM6/LM7 probe scripts | Scenario-specific prior evidence, not a product architecture | Not promoted or imported |
| Stored v2 recipe `recipe_to_edit()` -> `gh_edit` | Separate live deterministic replay seam | Deferred to a later capability |

The broad historical `Planner` orchestration and its autonomous MCP entry
points are not the foundation of this slice. Future RookChat, DSPy, or other
frontier-model adapters may produce the small draft defined here.

## 4. Considered approaches

### 4.1 Approach 1: thin capability compositor — selected

Add one internal C# repair-handoff module containing the strict draft loader,
immutable draft type, private pure specimen contract builder, one async
composition function, and one thin aggregate result. Delegate all meaningful
state changes to existing components.

This proves the missing composition directly while keeping the new product
surface deliberately narrow.

### 4.2 Approach 2: generalize `planner_worker_contract_request:v1` — rejected

The LM7A request contains scenario-specific routing, intent, pin, fixture, and
hidden-answer assumptions. Generalizing it would promote experimental history
into a premature product language and create migration work unrelated to the
missing composition.

### 4.3 Approach 3: begin with stored recipes and `gh_edit` — deferred

Stored recipe replay is a real deterministic path, but composing it into
PlanGraph would first require a new workflow capability and likely a new
worker-resolvable action. That broadens the slice before the existing
workflow/worker seam has been proven.

## 5. Planner draft boundary

### 5.1 Exact model-authored payload

The first version accepts exactly:

```yaml
goal: string
capability: grasshopper_csharp_component
interface:
  inputs: []
  outputs:
    - name: A
      type: double
acceptance: clean_compile_receipt
```

This fixed interface is truthful to the current worker acceptance path.
Although the underlying Grasshopper tools support broader pin shapes, this
slice does not advertise arbitrary pin names, input pins, or output types.

### 5.2 Field consumers

| Planner field | Sole consumer |
|---|---|
| `goal` | Immutable worker-visible knowledge |
| `capability` | Deterministic capability/template compiler selection |
| `interface` | Create parameters and worker-visible acceptance context |
| `acceptance` | Existing clean-receipt verifier expectation |

The Planner does not author a worker hole. The selected capability's
compiler-owned workflow determines that the existing bounded repair step may
be required.

### 5.3 Strict loader

The module exposes a strict loader that accepts an already parsed mapping and
returns an exact immutable `ValidatedPlannerDraft` instance. It:

- requires the exact top-level and nested field sets;
- requires a non-empty string `goal`;
- requires the exact capability, interface, and acceptance values above;
- rejects code, action IDs, template IDs, graph data, worker policy, execution
  parameters, and all other unknown fields;
- snapshots all admitted values into immutable owned state.

The async compositor accepts only the exact validated type. A raw mapping,
duck-typed replacement, or subclass does not cross the product boundary.
Invalid drafts stop before any worker or tool capability is invoked.

The boundary is:

```text
untrusted model/provider output
-> caller-owned parsing
-> strict draft loader
-> ValidatedPlannerDraft
------------------------------
-> deterministic compiler and execution
```

The compositor knows nothing about prompts, providers, model identity,
frontier-model retries, or parsing model text.

## 6. Pure repair-specimen contract builder

The C# repair-handoff module owns exactly one private fixture:

```python
_SPECIMEN_INITIAL_BODY = "A = DefinitelyMissingSymbol;"

def _build_repair_specimen_contract(
    draft: ValidatedPlannerDraft,
) -> RookWorkflowContract:
    ...
```

The private builder is pure. It constructs a `RookWorkflowContract` but does
not compile it, execute tools, assemble worker context, inspect receipts, or
call a worker.

It deterministically owns:

- the workflow identity;
- the exact descriptor selecting
  `gh_csharp_create_verify_repair_verify`;
- the existing template identity;
- canonical node IDs and graph rules;
- initial create parameters, including the private invalid body and fixed
  `A:double` output;
- expected execution references;
- the existing verifier expectations;
- the terminal `done` identity;
- the existing maximum step count and compiler-owned metadata.

The fixture exists only to force this specimen through the already-existing
repair path. It is not inferred from the Planner goal, configurable, injected,
registered, or described as future normal creation behavior.

Different valid goal values must produce identical fixture body, template,
wiring, action configuration, and all other compiler-owned fields.

### 6.1 Sole-source repair-code equation

The constructed workflow must satisfy:

```text
repair_same_component rule
= exactly one ProducerStepSpec(repair_same_component)
```

and:

```text
repair_same_component BindStepSpec count = 0
repair_same_component staged execution_params = absent
```

Therefore:

```text
validated worker action input
+ receipt-derived anchor binding
-> apply_worker_action_to_node()
-> repair_same_component execution_params
```

is the sole path by which repair code enters the compiled graph. No hidden
repair body, deterministic fallback body, pre-staged repair parameters, or
compiler-authored repair answer is permitted.

## 7. Worker-visible instruction boundary

### 7.1 Deterministic sources

After the existing create and verify steps produce genuine repair evidence,
deterministic code derives the worker-visible knowledge from:

```text
immutable validated goal
+ interface projected from the compiled create parameters
+ existing body-style convention source
+ existing acceptance-criteria assembler
+ exact current receipt diagnostic admitted by the existing acceptance-source machinery
```

The compositor projects `inputs` and `outputs` from the actual compiled
`create_script` execution parameters, proves that projection exactly equals
the validated draft interface, and renders that proven projection. It does not
reconstruct an equivalent interface literal beside the compiled artifact.

The serialized worker request contains:

- the immutable goal;
- fixed empty inputs and `A:double` output;
- `body_mode: body`;
- the existing acceptance packet;
- the exact current diagnostic admitted by the existing acceptance-source
  machinery;
- exactly one existing allowed action, `draft_repair_params`.

The existing acceptance-source extractor derives `{"mode": "body"}` from the
convention packet's identity and title; it does not inspect packet content.
The compositor therefore enforces the explicit equality:

```text
convention_packet.content.body_mode
== extracted_sources.convention.value.mode
```

Only after that equality passes does it expose the packet and assembled
acceptance criteria to the worker. The same convention packet instance feeds
both paths. A mismatch is an internal contract failure before worker contact;
independent hardcoded interpretations are not allowed to drift.

The exact diagnostic is a dedicated worker knowledge packet projected from
`sources.receipt_diagnostic` after the existing acceptance assembler admits
that source. The compositor neither rereads the graph nor assumes that the
generic acceptance packet contains the diagnostic value.

The existing `LocalWorkerTurnContext` also renders its current opaque workflow
identity and status summaries. This slice does not remove or misdescribe those
existing fields.

### 7.2 Explicit exclusions

Recursive inspection of the serialized worker request must prove absence of:

- `_SPECIMEN_INITIAL_BODY` and all original C# body text;
- the initial `code` execution parameter;
- component GUIDs;
- graph edges and graph rules;
- staged repair execution parameters;
- expected repair code or deterministic repair suggestions;
- compiler-owned template selection and wiring details beyond existing opaque
  context identities;
- compiler internals.

This is a specimen-specific information boundary. It is not a permanent claim
that every future repair worker must be denied existing source code.

### 7.3 Exact worker response

The accepted response retains the complete existing
`rook.local_worker_turn_response:v1` action shape:

```yaml
schema: rook.local_worker_turn_response:v1
kind: action_request
action_id: draft_repair_params
rationale: string
input:
  code: string
  mode: body
```

`rationale` is retained as non-authoritative worker evidence. Only the existing
validated `action_id` and `input` are passed to action application.

The component GUID never enters the worker request. The controller derives it
from the existing create receipt and supplies it separately as the
`anchor_binding` to `apply_worker_action_to_node()`.

## 8. Thin product compositor

### 8.1 Public internal function

The new module exposes one async internal product composition function:

```python
async def run_minimal_csharp_repair_handoff(
    draft: ValidatedPlannerDraft,
    *,
    worker_transport: LocalWorkerTransport,
    tool_executor: ToolExecutor,
) -> MinimalCSharpRepairHandoffResult:
    ...
```

The name and documentation explicitly identify this as a C# repair-capability
handoff, not a generic Planner/worker runtime.

Planner invocation remains outside the function. A future Planner adapter only
needs to produce the four-field payload and pass it through the strict loader.

The worker capability is injected at the existing provider-agnostic
`LocalWorkerTransport` seam. The compositor delegates request-to-prompt
rendering, raw transport, and response loading to `run_local_worker_adapter()`;
it does not inspect prompts, construct a provider, select a model, or parse
model text itself. Provider construction and model policy remain outside this
compositor. The deterministic tests use a fake transport, never production
fake behavior.

### 8.2 Fixed execution sequence

The compositor:

1. Requires the exact `ValidatedPlannerDraft` type.
2. Calls the private pure contract builder.
3. Calls the real `compile_workflow_contract()`.
4. Uses the compiled `CatalogCurrentStepProvider` and existing current-step
   runner to select and execute `create_script` through an injected typed tool
   executor.
5. Uses the same provider and existing verifier step to derive the create
   outcome and reach the repair boundary.
6. Derives the bounded worker instruction from the validated draft, compiled
   contract, same convention source, and actual create receipt diagnostic.
7. Builds the real `LocalWorkerTurnContext` and exact serialized request.
8. Calls `run_local_worker_adapter()` exactly once with the rendered request
   and injected transport. An adapter failure returns its existing status and
   reason without constructing a parallel worker outcome.
9. For a loaded response, calls the existing worker harness/disposition path
   exactly once through a closed one-shot callback returning that exact loaded
   response. It performs no second transport call or response interpretation.
10. For an accepted `action_request`, constructs the exact closed anchor
   projection:

   ```python
   anchor_binding = {
       "component_guid": receipt_anchor["component_guid"],
       "language": "csharp",
   }
   ```

   It requires that GUID to equal the graph-memory repair-anchor projection,
   never passes the broader receipt or memory anchor mapping, and passes only
   the validated action ID, input, and closed anchor binding to
   `apply_worker_action_to_node()`.
11. Uses the existing provider/current-step runner to execute
    `repair_same_component` and `verify_repair`.
12. Obtains the existing provider halt when terminal `done` is selected.
13. Returns native records and the final graph without constructing another
    receipt or evidence archive.

Because execution is intentionally split around the worker boundary, result
custody is exact concatenation rather than replacement:

```python
step_records = phase_one.records + phase_two.records
supply_records = phase_one.supply_records + phase_two.supply_records
```

The successful ordered ledger is create, verify-create, repair,
verify-repair, then the terminal halt supply record. Every early result retains
the complete native prefix observed before its stop.

A small private `SupportsLiveProducerNode` adapter may delegate to
`run_live_producer_node_with_executor()`. It normalizes the injected executor
shape only and owns no tool, receipt, or outcome semantics.

There is one worker turn. There is no hidden repair, worker retry, fallback
model, alternate action, deterministic repair body, or Planner re-entry in this
slice.

### 8.3 Continuous transaction lineage

The compositor is a continuous typed pipeline:

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

Three rules govern every handoff:

1. No parallel reconstruction: downstream values are projected from the
   actual upstream native artifact.
2. No broad passthrough: a narrower consumer receives an exact closed
   projection, never an adjacent evidence mapping with extra fields.
3. No discarded execution prefix: a later segment extends the native ledger;
   it never replaces earlier records.

This requires no proof-carrier, archive, fingerprint, or additional verifier
framework. The existing typed objects and explicit equality checks are the
transaction line.

## 9. Result and terminal semantics

`MinimalCSharpRepairHandoffResult` is a thin aggregate over existing records.
Its exact fields are:

```python
@dataclass(frozen=True)
class MinimalCSharpRepairHandoffResult:
    draft: ValidatedPlannerDraft
    scaffold: CompiledWorkflowScaffold
    final_graph: PlanGraph
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    step_records: tuple[CurrentStepRecord, ...]
    worker_request: Mapping[str, Any] | None
    worker_context: LocalWorkerTurnContext | None
    adapter_record: LocalWorkerAdapterRecord | None
    worker_record: LocalWorkerTurnHarnessRecord | None
    action_apply_result: WorkerActionApplyResult | None
    terminal_stage: Literal[
        "create",
        "verify_create",
        "worker_adapter",
        "worker_disposition",
        "action_apply",
        "repair",
        "verify_repair",
        "terminal",
    ]
    terminal_reason: str
```

The result does not copy receipt evidence into another field. The final graph
and native current-step records remain the sole owners of receipt evidence.

The optional-record equations are closed:

| Terminal stage | Worker request/context | Adapter record | Worker record | Action-apply result |
|---|---|---|---|---|
| `create` or `verify_create` | both `None` | `None` | `None` | `None` |
| `worker_adapter` | both present | present | `None` | `None` |
| `worker_disposition` | both present | present and `response_loaded` | present with a disposition other than `candidate_action_request` | `None` |
| `action_apply` | both present | present and `response_loaded` | present with `candidate_action_request` | present and `applied=False` |
| `repair`, `verify_repair`, or `terminal` | both present | present and `response_loaded` | present with `candidate_action_request` | present and `applied=True` |

No other optional-field combination is constructible. `draft`, `scaffold`,
`final_graph`, `supply_records`, `step_records`, `terminal_stage`, and
`terminal_reason` are always present. Contract building or compilation failure
raises and therefore produces no result.

`terminal_reason` is copied from exactly one native owner according to
`terminal_stage`:

| Terminal stage | Native reason owner |
|---|---|
| `create`, `verify_create`, `repair`, `verify_repair`, `terminal` | the last `EnvelopeSupplyRecord` or `CurrentStepRecord` that stopped that stage |
| `worker_adapter` | `LocalWorkerAdapterRecord.failure_reason` |
| `worker_disposition` | `LocalWorkerTurnDispositionRecord.reason` inside `worker_record` |
| `action_apply` | `WorkerActionApplyResult.reason` |

When a current-step record is the owner, the reason is its applicable existing
producer, verifier, mapping, or execution reason; the compositor does not
translate it. When a supply record is the owner, its existing `reason` or
`invalid_reason` is retained exactly. `terminal_reason` never contains a new
classification or friendly summary.

The aggregate does not introduce parallel meanings for refusal,
clarification, observation, invalid response, action rejection, runner refusal,
or receipt failure. A projected terminal label must map one-to-one to the
native record and preserve the native reason alongside it.

Expected operational stops return `MinimalCSharpRepairHandoffResult`.
Violated internal contracts, impossible native-record combinations, or a
forged validated draft raise rather than being flattened into an operational
outcome.

### 9.1 Terminal truthfulness

The current `CatalogCurrentStepProvider` halts when terminal `done` becomes the
selected ready node. It does not apply a synthetic success outcome to `done`.
Accordingly, successful completion for this slice is exactly:

```text
verify_repair outcome = succeeded
+ clean existing receipt evidence
+ provider halt reason = terminal_node_selected:done
```

The final graph retains the existing native state, including `done.status ==
"ready"`. The compositor must not mutate the terminal node merely to make
`graph_status()` return `complete`.

## 10. Deterministic test strategy

All fake Planner, worker, and tool-executor behavior exists only in tests.

### 10.1 One vertical witness

The primary test traverses:

```text
raw four-field payload from fake Planner
-> strict loader
-> ValidatedPlannerDraft
-> private pure contract builder
-> real compile_workflow_contract()
-> real CatalogCurrentStepProvider/current-step runners
-> fake typed create tool
-> diagnostic causally derived from the received create request
-> real LocalWorkerTurnContext and request renderer
-> one fake worker-transport call
-> real adapter response loading
-> one real worker harness/disposition pass
-> real response disposition
-> real apply_worker_action_to_node()
-> fake typed update tool using the receipt-derived GUID
-> existing clean-receipt interpretation
-> verify_repair succeeded
-> terminal_node_selected:done
```

The fake create tool inspects the exact received request. It emits the existing
created-with-errors receipt only because the received body contains
`DefinitelyMissingSymbol`. The orchestrator does not inject a canned diagnostic
independently of that request.

The fake worker transport receives the real prompt artifact. Its user message
must equal the canonical serialized request produced by the existing prompt
renderer. The transport returns one raw JSON response in the existing closed
response shape, and the real adapter loads that response before the
harness/disposition path evaluates it.

The fake update tool verifies that the GUID came from the create receipt and
that the submitted code came from the worker candidate. It returns an existing
clean/usable receipt shape. No fake-tool behavior enters production modules.

### 10.2 Draft and compiler table

Compact parameterized coverage proves:

- unknown top-level and nested fields are rejected;
- Planner-supplied code, action, graph, template, or worker fields are rejected;
- wrong capability, interface, or acceptance values are rejected;
- different valid goals compile to identical fixture body, template, wiring,
  rules, action configuration, and execution references;
- the create node receives the exact private initial body;
- the repair rule has exactly its producer step;
- the repair rule contains no `BindStepSpec`;
- the compiled repair node has no staged execution parameters.

Every invalid-draft case proves zero worker and tool calls.

### 10.3 Worker-boundary table

Tests prove:

- the serialized request includes the exact goal, fixed interface, body mode,
  acceptance packet, current diagnostic, and one allowed action;
- worker-visible interface is the compiled-create projection and equals the
  validated draft interface;
- body mode equals the mode extracted from the same convention source;
- all explicit excluded fields and values are recursively absent;
- the complete worker response requires `schema`, `kind`, `action_id`,
  `rationale`, and closed `input`;
- rationale never feeds action application;
- only the controller combines accepted worker code with the receipt GUID.
- the controller passes only the closed GUID/language anchor projection and
  proves its GUID agrees with graph memory.
- the result ledger concatenates both execution segments in exact order.

### 10.4 Stop table

Parameterized tests exercise existing semantics for:

- worker clarification;
- worker refusal;
- worker observation;
- adapter-invalid raw or structured worker response;
- worker transport exception;
- unknown or malformed action;
- action-application rejection;
- create dispatch/receipt stop;
- create verification stop;
- repair dispatch/receipt stop;
- repair verification stop;
- unexpected provider halt or native runner refusal.

Each case asserts its exact native record and reason and proves all expected
downstream worker, action, or tool calls remain zero.

### 10.5 Baseline

Before implementation, the established focused baseline is:

```text
222 passed
```

covering workflow compilation, worker context/harness/action application,
`gh_edit` contract behavior, workflow-chain execution, live dispatch, and
current-step streaming. Implementation must preserve that baseline and add the
new focused vertical without live contact.

## 11. Deliberate non-claims

This slice does not prove:

- a real frontier Planner can author the draft;
- a real local or cheap model can resolve the worker turn;
- live Rhino or Grasshopper behavior;
- runtime output `A` equals a user-requested value;
- arbitrary pin shapes, interfaces, templates, or capabilities;
- a normal first-pass C# creation path;
- stored-recipe or `gh_edit` PlanGraph integration;
- RookChat, MCP, or CLI usability;
- retry, fallback, replanning, escalation, or generalized orchestration;
- authoritative success beyond the existing clean compile receipt.

It proves only that the missing internal product composition works for one
existing workflow capability.

## 12. Delivery boundary

The implementation slice, once separately planned and authorized, ends with:

- one internal production module under `mcp_server/src/rook/agent`;
- the strict four-field loader and immutable draft;
- the private pure contract builder;
- the thin async compositor and aggregate result;
- deterministic fake-backed tests.

It introduces no Chat registration, MCP tool, CLI, provider adapter, live
worker transport, readiness flow, credential behavior, Rhino contact,
Grasshopper contact, new action, new template, registry, archive, or scripts
harness.

Specification approval is followed by independent specification review. The
`superpowers:writing-plans` skill is not invoked until that review approves the
specification.
