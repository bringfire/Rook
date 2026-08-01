# Minimal Worker-First C# Draft Design

**Date:** 2026-07-31

**Status:** Proposed for independent specification review

**Branch:** `codex/minimal-worker-first-csharp-draft-design`

**Reviewed base:** `90242fa4f09abf8f3b8ec994044787b61e77b446`

**Scope:** Internal product composition and deterministic tests only

**Authorization:** No provider, Worker box, Rhino, Grasshopper, Chat, MCP, CLI, or live operator contact

## 1. Purpose

The completed repair specimen proves this real path for one fixed capability:

```text
exact user intent
-> frontier Planner
-> strict four-field draft
-> deterministic workflow compiler
-> deliberately invalid create body
-> real Grasshopper compile diagnostic
-> one local Worker repair
-> receipt-bound update
-> deterministic re-verification
-> terminal success
```

The result and its non-claims are recorded in
`docs/superpowers/2026-07-31-minimal-intent-worker-real-compile-milestone.md`.
That path is intentionally a repair specimen. It does not yet represent the
normal product sequence, because deterministic code authors the first body and
the Worker sees only the resulting failure.

This slice adds the smallest normal-path sibling:

```text
exact user intent
-> one Planner draft
-> strict existing draft admission
-> deterministic compilation of an incomplete create graph
-> one Worker initial-body draft
-> pure code-only graph completion
-> one create call
-> deterministic verification of the create receipt
-> success or compile-failure stop
```

There is no repair opportunity. A second Worker call could hide failure of the
initial-authoring hypothesis and is therefore prohibited.

## 2. Falsifiable hypothesis

> Given the admitted Planner goal, the fixed `A:double` interface, a
> compiler-owned body convention, and a compiler-owned clean-receipt
> acceptance contract, the local Worker can author a compilable initial C#
> body before the first tool call.

For this slice, success requires exactly:

```text
one Planner call
one Worker call
one gh_create_csharp_script call
one deterministic verification record
done ready
```

The hypothesis is unsuccessful, but the product transaction remains valid,
when the single create receipt reports compile errors. That path preserves the
receipt and stops without update, repair, retry, fallback, or a second Worker
call.

This slice proves one internal composition only. It does not prove general
intent coverage, arbitrary component interfaces, runtime output correctness,
or a user-facing product surface.

## 3. Current seams and the missing boundary

| Seam | Current status | Treatment |
|---|---|---|
| `MinimalPlannerDraftAdapter` | Exact code-owned prompt, one transport call, strict JSON-object decoding, typed record | Reuse unchanged |
| `load_minimal_csharp_repair_draft()` | Strict four-field admission into `ValidatedPlannerDraft` | Reuse unchanged despite its historical repair-oriented name |
| `compile_workflow_contract()` | Deterministic contract-to-scaffold compiler | Reuse unchanged |
| Current-step provider, runner, mapping, receipts, and records | Native deterministic execution path | Reuse unchanged |
| Local Worker context, adapter, response loader, harness, and disposition | Existing one-turn Worker path | Reuse unchanged |
| `gh_csharp_create_verify_repair_verify` | Proven forced-repair topology | Preserve unchanged |
| `draft_repair_params` and `apply_worker_action_to_node()` | Proven receipt-bound repair action | Preserve unchanged |
| `gh_csharp_create_verify` | Missing | Add one narrow topology template |
| Pre-execution initial-body action | Missing | Add one explicit sibling action and copy-on-write applicator |
| Normal-path handoff and intent integration | Missing | Add sibling compositors and separate ephemeral result types |

The missing product boundary is not a new runner or Planner language. It is the
explicit transition from an incomplete compiler-owned create scaffold to a
Worker-completed scaffold before the existing runner sees it.

## 4. Considered approaches

### 4.1 Approach 1: sibling normal-path compositor — selected

Add one `create -> verify -> done` template, one initial-body action, one pure
copy-on-write applicator, one handoff compositor, and one Planner-facing
integration function. Reuse the existing Planner, compiler, Worker, runner,
tool, receipt, and terminal semantics.

This keeps the forced repair specimen stable and tests the new hypothesis
directly.

### 4.2 Approach 2: mutate the forced repair compositor — rejected

Making the repair compositor optionally draft first would mix two hypotheses,
weaken its historical meaning, and create configuration branches through code
that is already proven.

### 4.3 Approach 3: add a Worker graph node — rejected

A graph node whose purpose is only to collect one pre-execution value would
invent an execution kind and confuse model interaction with deterministic
workflow topology. The Worker transaction belongs explicitly in the sibling
compositor before graph execution.

## 5. Unchanged Planner draft boundary

The Planner continues to author exactly:

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

The existing strict loader remains the sole semantic admission path. It admits
an exact `ValidatedPlannerDraft`; it supplies no code, topology, tool name,
node identity, action identity, position, or verification rule.

The existing Planner adapter remains exact and concrete. The new
Planner-facing integration accepts that adapter, not an arbitrary producer.
Provider, model, and generation construction remain outside the integration.

The authority equation remains:

```text
validated_draft.goal == exact input intent
```

No trimming, paraphrasing, normalization, repair, or defaulting is permitted.

## 6. New compiler-owned topology

### 6.1 Registered template

Add exactly one registered template:

```text
template_id: gh_csharp_create_verify
descriptor:
  domain: grasshopper
  operation: create_verify
  language: csharp
```

Its graph contains exactly:

```text
create_script --requires--> verify_create --requires--> done
```

Both edges are explicitly `requires`. There is no `on_repair` edge.

The nodes are:

| Node | Ownership |
|---|---|
| `create_script` | `gh_create_csharp_script:v1`, producer projection, existing script-receipt verifier reference |
| `verify_create` | Deterministic verifier over the receipt owned by `create_script`; expected outcome `succeeded` |
| `done` | Terminal marker; becomes ready only after successful verification |

Verification does not call Grasshopper. It evaluates the compile evidence
already contained in the create receipt through the existing verifier node and
workflow machinery.

A compile-error receipt follows the existing semantics:

```text
create_script producer outcome: succeeded artifact creation
verify_create verifier outcome: needs_repair
done: pending
ready-node set: empty
native stop: selector_halt:none_ready
```

Because this topology has no repair edge, that is an ordinary unsuccessful
result rather than an invitation to repair.

### 6.2 Pure incomplete-contract builder

The sibling handoff module owns one private pure builder:

```python
def _build_initial_body_contract(
    draft: ValidatedPlannerDraft,
) -> RookWorkflowContract:
    ...
```

It constructs but does not compile or execute the contract. The contract owns:

- workflow identity;
- the exact `gh_csharp_create_verify` template reference and descriptor;
- `create_script`, `verify_create`, and `done` identities;
- the two `requires` edges through the selected registered template;
- one producer rule for `create_script`;
- one verifier rule for `verify_create`, sourcing `create_script` and expecting
  `succeeded`;
- the terminal `done` identity;
- the sole expected tool reference, `gh_create_csharp_script:v1`;
- fixed capability and acceptance metadata;
- `max_steps=4`, a fixed bound sufficient for create, verify, and terminal
  halt.

Before Worker application, `create_script.execution_params` has exactly these
keys:

```text
pins_in
pins_out
name
x
y
```

The values derive from the validated interface and compiler-owned component
placement. `code` is absent. Body mode is not stored in execution parameters;
it remains a separate compiler-owned convention.

The contract contains no `BindStepSpec`, repair rule, update reference,
pre-authored body, hidden fallback, or Worker answer.

## 7. Pre-execution Worker transaction

### 7.1 Context ownership

The compositor compiles the incomplete contract and builds a
`LocalWorkerTurnContext` before invoking the current-step runner.

The context is derived from the actual compiled scaffold and contains:

- the exact validated goal;
- the interface projected from compiled `create_script` parameters and proven
  equal to the validated draft interface;
- the code-owned body-only convention;
- the existing clean-compile acceptance meaning derived from the compiled
  verifier contract;
- exactly one allowed action, `draft_create_body`.

There is no current diagnostic because no create call has occurred. The
context contains no prior C# body, expected body, deterministic code hint,
repair action, component GUID, graph edge, graph rule, staged execution
parameter mapping, or tool-call answer.

Existing opaque context summaries such as compiler, provider, template, node,
ready-node, and terminal-node identities may remain visible. Neither model can
author or alter topology.

The initial-body context permits only:

```text
draft_create_body
```

The existing repair context continues to permit only:

```text
draft_repair_params
```

The action vocabularies never overlap or substitute for one another.

### 7.2 Worker response

The Worker uses the existing response envelope:

```yaml
schema: rook.local_worker_turn_response:v1
kind: action_request
action_id: draft_create_body
rationale: string
input:
  code: string
```

The `input` object contains exactly `code`. `mode` is deliberately absent.
Body mode is fixed by the compiler-owned convention, so asking the Worker to
repeat it would add no authority.

`rationale` remains non-authoritative evidence. Only the adapter-loaded exact
action ID and strictly validated input enter action application.

Refusal, clarification, adapter failure, invalid response, or any disposition
other than the candidate `draft_create_body` action stops before tool
execution.

## 8. Pure scaffold applicator

### 8.1 Boundary

Add one narrow pure function conceptually shaped as:

```python
def apply_worker_create_body_to_scaffold(
    scaffold: CompiledWorkflowScaffold,
    node_id: str,
    *,
    action_id: str,
    action_input: Mapping[str, Any],
) -> WorkerCreateBodyApplyResult:
    ...
```

The input is the exact compiled scaffold retained by the handoff, not an
arbitrary graph. The applicator binds all of these facts before copying:

```text
scaffold.compile_record.expected_template_id
== gh_csharp_create_verify

scaffold.compile_record.selected_template_id
== gh_csharp_create_verify

snapshot_scaffold
= compile_workflow_contract(
    load_workflow_contract_payload(
        scaffold.contract_snapshot.normalized_contract
    )
  )

type_sensitive_equal(scaffold, snapshot_scaffold)

node_id == create_script
node execution_ref == gh_create_csharp_script:v1
action_id == draft_create_body
action_input exact keys == {code}
type(action_input[code]) is str
action_input[code].strip() is nonempty
```

It also requires the existing `create_script` parameter mapping to contain
exactly `pins_in`, `pins_out`, `name`, `x`, and `y`, with no `code`, `mode`, or
additional field. It rejects a populated code field, the wrong node, the wrong
tool reference, a different template, unknown input shapes, equality-spoof
scalar values, unknown input keys, or any attempted change to compiler-owned
parameters.

### 8.2 Copy-on-write equation

The applicator deep-copies the scaffold graph and performs exactly:

```text
original_params
= scaffold.graph.create_script.execution_params

keys(returned_graph.create_script.execution_params)
= keys(original_params) union {code}

project(
  returned_graph.create_script.execution_params,
  keys(original_params),
)
= original_params

returned_graph.create_script.execution_params[code]
= admitted Worker string
```

The canonical serialized bytes of every original key/value projection remain
unchanged; the sole added key is `code`. All other nodes, edges, metadata,
statuses, and graph memory remain equal.

The original incomplete scaffold and its graph remain unchanged and contain no
code. The retained adapter/harness response is the sole authority for the
Worker-authored body. The applicator is the first operation that introduces
that body into graph state. The body may then propagate normally through the
native graph and current-step records produced from that graph; the aggregate
adds no manually copied parallel code field. Rejection returns no mutated graph
and performs no tool call.

`WorkerCreateBodyApplyResult` is a small sibling of the existing repair action
result. It retains the returned graph, application verdict, node ID, fixed
reason token when rejected, and a deterministic hash of the completed
execution parameters when applied. It creates no receipt or evidence type.

## 9. Minimal C# initial-body handoff

### 9.1 Function

The sibling compositor exposes:

```python
async def run_minimal_csharp_initial_body_handoff(
    draft: ValidatedPlannerDraft,
    *,
    worker_transport: LocalWorkerTransport,
    tool_executor: ToolExecutor,
) -> MinimalCSharpInitialBodyHandoffResult:
    ...
```

It requires the exact validated draft type. Raw mappings cannot enter. It
knows nothing about Planner prompts, providers, models, retries, or parsing.

### 9.2 Fixed sequence

The compositor performs exactly:

1. Build the incomplete compiler-owned contract.
2. Compile it through `compile_workflow_contract()`.
3. Project and validate the Worker-visible goal, interface, convention, and
   acceptance from the actual draft and scaffold.
4. Build the initial `LocalWorkerTurnContext` with only
   `draft_create_body`.
5. Render the exact existing Worker request.
6. Call the existing local Worker adapter once.
7. Run the exact loaded response through the existing one-shot harness and
   disposition path without a second transport call.
8. For the sole admitted action, apply it to the exact retained scaffold via
   the pure copy-on-write applicator.
9. Only after successful application, expose the completed graph to the
   existing current-step stream.
10. Execute `create_script` once through the injected typed tool executor.
11. Run `verify_create` once as deterministic receipt evaluation.
12. Stop at terminal success or at the native unsuccessful compile path.

The allowed tool ledger is:

```text
[]
[gh_create_csharp_script]
```

`gh_update_script`, a second create, a second Worker call, repair, retry,
fallback, deterministic body patching, and Planner re-entry are impossible in
this compositor.

### 9.3 Ephemeral handoff result

The handoff begins only after draft admission, so its exact result type is:

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

The result does not copy Worker code or receipt evidence into parallel fields.
The adapter/harness record owns the Worker response. The action result owns the
completed pre-execution graph. Native current-step records and the final graph
own tool receipts and execution state.

The optional ownership equations are:

| Stage | Worker record | Action result | Native record prefix | Final graph |
|---|---|---|---|---|
| `worker_adapter` | absent | absent | empty | original incomplete scaffold graph |
| `worker_disposition` | present | absent | empty | original incomplete scaffold graph |
| `action_apply` | present | present and rejected | empty | original incomplete scaffold graph |
| `create` | present | present and applied | empty or `create_script` | native returned graph |
| `verify_create` | present | present and applied | exactly `create_script`, `verify_create` | native returned graph with `done` not ready |
| `terminal` | present | present and applied | exactly `create_script`, `verify_create` | `done.status == ready` |

Every returned handoff result has a Worker request, context, and adapter record
because no handoff result exists until after compilation, context construction,
and the single adapter invocation. Internal compiler or context contradictions
raise rather than inventing a terminal stage.

The result validates only its own transaction lineage using existing pure
producers and exact comparisons:

```text
draft
-> contract/scaffold
-> worker context/request
-> adapter-loaded response
-> disposition
-> pure scaffold application
-> native graph/record chain
```

It re-renders the request from the retained context, re-derives disposition,
recompiles `_build_initial_body_contract(draft)` and requires the retained
scaffold to equal that exact compiler output under the same private
type-sensitive tree comparison, replays the pure applicator from that retained
scaffold, and validates each native record through the existing current-step
projection. It does not create an archive, proof carrier, fingerprint
framework, or second receipt system.

## 10. Planner-facing integration and ownership split

The Planner boundary is a separate sibling function:

```python
async def run_minimal_intent_worker_initial_body_integration(
    intent: str,
    *,
    planner_adapter: MinimalPlannerDraftAdapter,
    worker_transport: LocalWorkerTransport,
    tool_executor: ToolExecutor,
) -> MinimalIntentWorkerInitialBodyIntegrationResult:
    ...
```

It reuses the existing intent bounds, exact Planner prompt, concrete adapter,
strict response decoding, strict draft loader, and exact-goal equality. It
does not change the existing repair-oriented integration function.

Its ephemeral result is:

```python
@dataclass(frozen=True)
class MinimalIntentWorkerInitialBodyIntegrationResult:
    intent: str
    planner_adapter_record: MinimalPlannerDraftAdapterRecord
    validated_draft: ValidatedPlannerDraft | None
    handoff_result: MinimalCSharpInitialBodyHandoffResult | None
    terminal_stage: str
    terminal_reason: str
```

The ownership equations are closed:

### Planner adapter stop

```text
validated_draft is None
handoff_result is None
terminal_stage == planner_adapter
terminal_reason == planner_adapter_record.failure_reason
Worker calls == 0
tool calls == 0
```

### Draft admission stop

```text
planner_adapter_record.status == decoded
validated_draft is None
handoff_result is None
terminal_stage == draft_admission
terminal_reason in {draft_payload_rejected, goal_mismatch}
Worker calls == 0
tool calls == 0
```

### Handoff reached

```text
validated_draft is present
handoff_result is present
strict_load(planner_adapter_record.decoded_object) == validated_draft
validated_draft.goal == intent
handoff_result.draft == validated_draft
terminal_stage == handoff_result.terminal_stage
terminal_reason == handoff_result.terminal_reason
```

There is no returned integration state containing a validated draft without a
handoff result. An internal compositor exception raises. The integration
aggregate validates only its Planner-to-handoff ownership; it delegates the
Worker, graph, tool, and receipt lineage to
`MinimalCSharpInitialBodyHandoffResult`.

Both results are ephemeral internal transaction aggregates. Neither is a
durable record, authority artifact, public proof, checkpoint, or retry token.

## 11. Failure and stop semantics

| First stopping boundary | Returned owner | Worker calls | Tool calls | Meaning |
|---|---|---:|---:|---|
| Planner transport/response failure | Integration result, `planner_adapter` | 0 | 0 | Existing typed adapter stop |
| Draft rejection or goal mismatch | Integration result, `draft_admission` | 0 | 0 | Existing strict admission stop |
| Worker adapter failure | Handoff result, `worker_adapter` | 1 | 0 | Existing adapter reason |
| Worker refusal/clarification/non-action disposition | Handoff result, `worker_disposition` | 1 | 0 | Existing disposition reason |
| Invalid or inapplicable `draft_create_body` | Handoff result, `action_apply` | 1 | 0 | Fixed applicator rejection reason |
| Create mapping/dispatch/receipt stop | Handoff result, `create` | 1 | 0 or 1 | Existing native reason |
| Compile-error receipt | Handoff result, `verify_create` | 1 | 1 | Ordinary unsuccessful result; receipt retained; no repair |
| Clean compile receipt | Handoff result, `terminal` | 1 | 1 | `done` selected and ready |
| Internal type, ownership, topology, or lineage contradiction | Exception | bounded prefix | bounded prefix | Programmer contract violation, not an operational outcome |

Expected operational stops return the owning ephemeral result and preserve the
underlying native reason. The new code does not flatten native stops into a
parallel outcome vocabulary.

## 12. Deterministic test strategy

All implementation and review tests are no-contact. Planner and Worker
transports and the typed tool executor are fakes in tests only.

### 12.1 Template and contract tests

Prove:

- template ID and descriptor are exact;
- nodes are exactly `create_script`, `verify_create`, and `done`;
- edges are exactly the two ordered `requires` edges;
- create and verifier roles and references are exact;
- no repair/update node, `on_repair` edge, or update execution reference exists;
- the compiled create parameter key set is exactly
  `pins_in`, `pins_out`, `name`, `x`, `y`;
- code and body mode are absent;
- the two rules are exactly one producer and one verifier, with no bind step;
- different valid goals do not move compiler-owned topology, parameters,
  action identity, or acceptance semantics.

### 12.2 Applicator tests

Prove:

- exact `draft_create_body` input adds only the Worker code;
- the applicator consumes the compiled scaffold and rejects a wrong template;
- wrong node, wrong tool reference, pre-populated code, extra/missing input
  keys, `mode`, attempted pin/name/position changes, non-exact strings, blank
  code, subclasses, and unknown shapes reject;
- the incomplete scaffold and its graph remain unchanged;
- caller-owned input values are not mutated;
- the original scaffold contains no code, the retained Worker response is the
  sole code authority, and the applicator first introduces that exact value
  into its returned graph;
- any later code occurrence is owned by native graph/record propagation, and
  neither ephemeral aggregate adds a parallel code field;
- all compiler-owned graph and parameter values remain identical;
- no tool capability is invoked by the pure applicator.

### 12.3 Worker-boundary tests

Through the real context renderer, adapter, response loader, harness, and
disposition, prove:

- one Worker request contains the exact goal, compiled interface, body
  convention, and clean-receipt acceptance;
- the request permits only `draft_create_body`;
- `draft_repair_params`, diagnostic text, code, GUIDs, execution parameters,
  edges, rules, expected code, and repair instructions are absent;
- the response requires the existing schema, action envelope, rationale, and
  exact `{code}` input;
- rationale changes cannot alter applied code or graph parameters;
- refusal, clarification, malformed response, wrong action, or invalid input
  produces zero tool calls;
- the existing repair context still permits only `draft_repair_params`.

### 12.4 Native execution tests

Use a causal fake typed executor that derives its receipt from the exact
received create body and rejects any unexpected tool, parameters, call order,
second call, or update call.

Prove two verticals:

```text
Worker valid body
-> one create
-> clean receipt
-> verifier succeeded
-> done ready
-> terminal
```

and:

```text
Worker invalid body
-> one create
-> compile-error receipt
-> verifier needs_repair
-> no ready nodes
-> selector_halt:none_ready
-> verify_create unsuccessful result
```

Both retain the original scaffold, exact Worker transaction, application
result, full native record prefix, and final graph. Neither calls update or a
second Worker.

### 12.5 Planner-to-terminal vertical

Prove the complete no-contact product path:

```text
raw exact user intent
-> fake one-call Planner transport
-> real MinimalPlannerDraftAdapter
-> strict existing loader
-> MinimalIntentWorkerInitialBodyIntegrationResult
-> real new handoff compositor
-> fake one-call Worker transport through the real adapter
-> pure applicator
-> causal fake typed executor
-> native terminal result
```

Assert exactly one Planner call, one Worker call, one create call, zero update
calls, exact goal authority, and the two aggregate ownership equations.

Adversarial aggregate substitutions cover intent, Planner record, admitted
draft, handoff result, scaffold, Worker request/context, adapter response,
action result, native record prefix, and final graph. Each test mutates the
actual upstream source or substitutes a fully shaped sibling object; no test
claims lineage merely by changing an already-rejected downstream field.

### 12.6 Regression surface

Run the focused new tests plus the existing seams for:

- workflow templates and contract compilation;
- current-step mapping, runner, stream, and record projection;
- local Worker context, request, response, adapter, harness, and disposition;
- repair action application and minimal repair handoff;
- minimal intent integration;
- synthetic and real-compile smoke tests;
- flight recorder projections.

The existing forced-repair path must remain behaviorally unchanged at its
public boundaries.

## 13. Scope and non-goals

### In scope

- one `gh_csharp_create_verify` template;
- one private pure incomplete-contract builder;
- one `draft_create_body` action description;
- one pure scaffold-to-completed-graph applicator;
- one initial-body handoff compositor and result;
- one Planner-facing initial-body integration function and result;
- deterministic no-contact tests.

### Out of scope

- changes to the forced repair compositor or `draft_repair_params`;
- a generic pre-execution affordance framework;
- a second Worker call, repair, retry, fallback, or update;
- arbitrary pins, capabilities, templates, or action registries;
- Worker-authored body mode, topology, tool choice, position, verification, or
  component identity;
- Planner-authored topology or implementation code;
- provider/model construction;
- operator scripts, live smokes, Chat, MCP, CLI, Chirp, or DSPy registration;
- Rhino or Grasshopper contact;
- archives, receipts beyond existing native receipts, fingerprints,
  checkpoints, readiness, or scientific evidence machinery.

## 14. Deferred topology-guidance hypothesis

A provisional architectural hypothesis remains for later work:

> As Rook gains more compiler-owned workflows, selected topology and node
> state may help deterministic orchestration decide where a bounded Worker
> affordance belongs.

This slice does not test or implement that hypothesis. It does not expose
graph topology to either model, add a Planner topology field, infer actions
from arbitrary graphs, or build a generic affordance layer. It explicitly
composes one known pre-execution action against one exact compiled template.

Only after a second distinct product path needs the same orchestration should
the repeated structure be evaluated for extraction.

## 15. Stop condition

This slice is complete when deterministic tests prove:

```text
exact intent
-> one strict Planner draft
-> exact incomplete gh_csharp_create_verify scaffold
-> one Worker draft_create_body action
-> pure code-only graph completion
-> one create call
-> one deterministic verification
-> clean terminal or retained compile-failure stop
```

with the existing repair path unchanged and no external contact.

After implementation review and merge, any real Worker/Rhino execution is a
separate product-integration decision and requires separate explicit
authorization.
