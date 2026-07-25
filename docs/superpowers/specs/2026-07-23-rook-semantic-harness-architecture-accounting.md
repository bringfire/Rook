# Rook Semantic Harness Architecture Accounting And Theory Reconciliation

- **Date:** 2026-07-23
- **Status:** Architecture accounting and hypothesis reconciliation
- **Baseline:** `8a5013bd61b4954b92e4cb654da9cd99e61b551e`
- **Scope:** Reconcile the implemented LM4-LM9 substrate, the LM9 empirical
  results, and the proposed governed-resolution work against the existing Rook
  North Stars.
- **Non-scope:** This document is not an implementation specification, does not
  authorize a model call, and does not make the current LM9 probe machinery a
  product authority surface.

## 1. Decision

The governed-resolution proposal is **not a replacement architecture**.

It is:

1. the next empirical hypothesis inside the existing architecture; and
2. a contract-level elaboration of the authority-amendment and replan seam that
   the Planner Harness North Star already predicted but did not fully specify.

The architectural theory remains:

```text
models propose artifacts and judge meaning
deterministic systems establish authority and control advancement
runners execute only authorized inert artifacts
receipts establish what actually happened
the Planner returns only when authority or reality materially changes
```

The next empirical hypothesis is new in the ordinary scientific sense: prior
experiments tested Planner authorship and compiler sufficiency separately; the
next experiment tests whether new explicit user authority can transform an
honestly blocked parent recipe into an isolated successor that can continue
through the same downstream path. That is hypothesis N+1 under the same theory,
not theory N+1.

## 2. Existing Theory Being Extended

### 2.1 Multi-file topology

`2026-06-03-rook-north-star-topology.md` defines the economic destination:

```text
one scarce, expensive coordinator
-> many bounded, cheap/local in-file workers
-> durable verified artifacts
-> dependency-ordered fan-in to a master deliverable
```

It separates Session, Document/Artifact, Work Unit, and Merge Contract identity.
Nothing in governed resolution changes that topology. A successor recipe and
successor task envelope are durable work-unit artifacts; they do not become
session identity or merge state.

### 2.2 Local/internal model theory

`2026-06-19-rook-local-internal-models-north-star.md` establishes the inversion:

```text
frontier model: the model may plan; Rook subsidizes it
local model:    the scaffold plans; the model resolves one bounded node
```

It also establishes schema/dispatcher parity, preflight before mutation,
verification as state, pushed context, bounded escalation, and external graph
ownership. Governed resolution preserves this allocation. A frontier Planner
may revise semantic meaning; a local worker does not decide absent user facts or
amend recipe authority.

### 2.3 Planner harness theory

`2026-07-02-rook-planner-harness-north-star.md` defines three boxes:

```text
Planner -> immutable compiled artifact
Runner  -> model-free scheduling, policy, gates, receipts, escalation
Worker  -> bounded response inside a closed request/response contract
```

Its replan-frontier contract already requires:

```text
parent fingerprint + new receipts/evidence
-> Planner re-invocation
-> amended artifact with parent-linked provenance
-> deterministic validation
-> runner resume
```

Governed clarification is the first semantic, pre-execution instance of that
same re-entry pattern. The new authority is a successor task envelope rather
than a worker/runtime receipt, but the control theory is unchanged.

### 2.4 LM9 semantic and compile theory

`2026-07-13-lm9a-planner-graph-recipe-design.md` and the LM9 additions to the
Planner Harness North Star establish:

```text
trusted ingress authority
-> Planner-authored semantic recipe
-> deterministic semantic validation
-> bounded intelligent compile
-> deterministic compiled-IR and authorization validation
-> model-free execution
-> authoritative runtime verification
```

They also separate semantic authority from implementation representation. The
Planner owns desired truth, explicit assumptions, unresolved intent, and
delegation bounds. The compiler owns inert representation and topology choices.
Workers may fill declared implementation slots but may not author execution
batches or resolve missing semantic authority.

The current governed-resolution proposal fills a missing transition between
the first two stages. It does not alter their ownership.

## 3. Grounded Implementation Accounting

### 3.1 Product/runtime substrate: landed

The live product architecture remains the one documented in
`docs/CURRENT_ARCHITECTURE.md`:

- `RookNative` is the sole public in-Rhino HTTP/control surface.
- The managed companion owns the Grasshopper callback bridge and UI surfaces.
- The Python MCP server owns intent, knowledge, agent, and orchestration logic.

The lower harness is real product code:

- `mcp_server/src/rook/agent/plan_graph_workflow_contract.py` loads and compiles
  `RookWorkflowContract` into a PlanGraph scaffold.
- `mcp_server/src/rook/agent/plan_graph_*` owns deterministic sequencing,
  dispatch, evidence, and live runner behavior.
- `mcp_server/src/rook/agent/local_worker_turn_*` and
  `local_worker_adapter.py` own bounded worker request, response, disposition,
  and transport truth.
- `mcp_server/src/rook/agent/workflow_validate.py` exposes deterministic request,
  contract, routing, and intent validation for the older worker-contract path.

LM5-LM8 provided live evidence for bounded worker execution, repair, managed
Grasshopper solve-readiness, receipt-fenced reads, and the local Gemma affine
scalar case at `20/20`.

### 3.2 Generic validation kernel: landed, not semantically composed

`mcp_server/src/rook/validation_kernel/` is production code. It provides:

- owned immutable JSON and canonical fingerprints;
- bounded parsing and schema evaluation;
- a fixed budget ledger;
- immutable phase contracts and sealed-program composition;
- deterministic phase execution;
- closed issue/report projection;
- report sealing, conformance, and the public `validate_artifacts()` API.

What is absent is equally important: there is no landed LM9A semantic
`ValidationProgramContribution` in product code. The kernel can execute a
semantic program, but the recipe-specific program is not implemented.

### 3.3 Planner recipe probe: landed scientific machinery

The current recipe language and empirical harness live under `scripts/`:

- `lm9b_p_fixtures/planner_recipe_probe_schema.json`;
- `lm9b_p_planner_recipe_transfer_support.py`;
- `lm9b_p_planner_recipe_transfer_artifacts.py`;
- `lm9b_p_planner_recipe_transfer_probe.py`;
- the readiness and evaluator-only continuation modules.

This machinery has strong exact-byte, normalization, authority-binding,
provider, classification, and evidence-sealing tests. Its
`evaluate_mechanical_gate()` is deliberately a non-authoritative observation
gate. It is not the missing LM9A semantic program and must not silently become
one.

The product `mcp_server/src/rook/agent/planner.py` is an older `Plan`/`TaskSpec`
worker-dispatch loop. It is not connected to the LM9 semantic recipe path. The
two paths must eventually converge or the older path must be explicitly
contained; they must not remain competing product planners.

### 3.4 Empirical results: separately positive, not yet joined

The preserved evidence establishes:

1. A frontier Planner authored one mechanically accepted recipe after the full
   accepted language was made model-visible.
2. An independent corrected evaluator judged the exact recipe
   `semantically_faithful`.
3. Deterministic classification produced `probe_candidate_blocked` because the
   recipe honestly retained five unresolved material values.
4. Separately, the unchanged hand-authored R01 supported one bounded compiler
   lowering to exact-contract C#.
5. The unmodified C# compiled and solved in Grasshopper, produced 100 boxes,
   and satisfied the controlled geometric checks.

The evidence does **not** establish:

- an authoritative LM9A `valid` or `compile_ready` result;
- governed resolution of unresolved intent;
- a model-authored ready recipe entering the compiler;
- compiler generality or representation plurality;
- executable-IR authorization;
- product execution, replan, or multi-file fan-in.

## 4. Theoretical Completeness Assessment

The architecture is **directionally complete but transitionally incomplete**.

| Altitude | Assessment |
|---|---|
| Governing invariants | Substantially complete: authority, model, runner, worker, and verification ownership are coherent. |
| Lower worker/runtime box | Implemented and live-proven for narrow families. |
| Planner semantic artifact | Designed and empirically authorable, but still probe-local. |
| Deterministic semantic authority | Kernel exists; LM9A semantic contribution does not. |
| Authority amendment/replan | Predicted by the North Star; concrete governed-resolution contract is missing. |
| Intelligent compile | Positive evidence for one hand-authored recipe and one C# representation. |
| Compiled IR authorization | Not yet designed to product completeness or implemented. |
| Recipe-to-runtime product vertical | Not present. |
| Multi-file work allocation/fan-in | North-Star-defined but beyond the current single-file semantic harness. |

The most mature LM9 code today is scientific evidence infrastructure. It is a
trustworthy instrument, not yet the product machine being measured.

## 5. New Contract Elaboration: Open Keys Inside Closed Authority

The five observed unresolved values exposed a missing scalable ingress shape.
The permanent solution must not be a global catalog containing every possible
semantic fact.

The theory is:

```text
semantic_key = task-local join identity
value_schema = closed, versioned value shape
authority_kind + provenance = who established the value
typed-value fingerprint = exact established value identity
artifact pointer = exact dereference location
```

Task-local keys are open under the existing machine-identifier grammar. The
record structure, value kinds, authority kinds, provenance, and binding
equations are closed. Deterministic code compares exact identities and does not
interpret the English meaning of key names.

For resolution:

```text
parent unresolved semantic_key
== successor task-envelope value_binding semantic_key
== successor recipe artifact_value target semantic_key
```

The successor task envelope is the sole authority for the new values. A
clarification delta may describe the transition but carries no authority. The
Planner receives exact parent and successor identities; it does not reconstruct
key names from prose.

This is an elaboration of the existing task-envelope/value-binding contract,
not a new authority vocabulary or a new receipt subsystem.

## 6. Governed Resolution As The First Replan Primitive

The immediate vertical is:

```text
immutable faithful blocked parent recipe
+ immutable parent task envelope
+ explicit user clarification
-> trusted ingress issues successor task envelope
-> one bounded Planner revision session
-> complete immutable successor recipe
-> deterministic parent/successor isolation validation
-> ordinary recipe validation
```

The first experiment resolves exactly the five observed keys through
`user_fact` bindings. Planner assumptions, policy-selected values, derived
facts, and receipts may not satisfy those five keys.

The isolation relation is derived from authenticated parent intent and
successor authority. Production logic may not contain radial key names, radial
values, or the radial clause ID. Exact radial expectations belong only to
reviewed experimental data.

The relation permits only:

- replacement of the parent task-envelope binding with the successor binding;
- removal of exactly the resolved unresolved-intent rows and projections;
- addition of exact successor-envelope artifact-value support to the affected
  clauses derived from those parent rows;
- recomputation and independent verification of successor recipe identity.

Every other normalized semantic element remains identical. The gate performs
no patching or repair. A non-isolated candidate is an attributable failed
observation.

Lineage is evidence, not semantic authority. The transition ledger binds parent
recipe, parent task envelope, successor task envelope, authority delta, and
successor recipe fingerprints. In the later product harness this should reuse
the Planner/runner provenance ledger pattern rather than becoming a second
semantic source.

## 7. Falsifiable Hypothesis Ladder

### 7.1 Generic task-local fact carrier

**Hypothesis:** Existing task-envelope authority can carry arbitrary task-local
facts using closed registered value shapes and existing `user_fact` provenance,
without a global semantic-key registry or scenario-specific production code.

**Proof:** Deterministic radial and unrelated synthetic fixtures pass through
the same loader, schema, fingerprint, and binding logic. Invalid type, unit,
authority, provenance, duplicate key, unbound value, or pointer fails.

**Falsifier:** A second unrelated fact requires a new production branch or the
gate must understand a key's domain meaning.

### 7.2 Governed Planner revision

**Hypothesis:** Given the exact parent recipe and successor user authority, one
bounded Planner session can emit a complete successor recipe whose only
normalized semantic movement is the derived resolution delta.

**Proof:** Exact parent/successor isolation, no deterministic repair, no second
Planner attempt, and independent semantic evaluation.

**Falsifier:** The Planner invents authority, retains stale unresolved intent,
changes unrelated semantics, or succeeds only with fixture-specific guidance.

### 7.3 Joined experimental transfer

**Hypothesis:** Exact accepted successor bytes can enter the unchanged LM9B-C
compiler boundary and produce a mechanically valid inert candidate.

**Proof:** Byte-bound handoff, no brief/evaluator leakage, existing compiler
controller and gates unchanged.

**Falsifier:** Translation, repair, hidden R01 content, compiler feedback to the
Planner, or a changed compiler contract is required.

This remains scientific evidence. It does not substitute for LM9A semantic
authority.

### 7.4 Production semantic validation

**Hypothesis:** One sealed LM9A semantic contribution can derive generic
`valid`, `blocked`, and `compile_ready` outcomes from recipes and trusted
companions without model judgment or scenario logic.

**Proof:** Reconciled authority vocabulary, generic campaign fixtures,
combined-failure cases, and exact kernel reports through the existing public
validation API.

**Falsifier:** The validator needs an evaluator recommendation, fixture names,
recipe prose interpretation, or a shadow parser/scheduler/report seal.

The checked-in LM9A design must be reconciled before implementation. It remains
marked `design draft` and includes the superseded
`permitted_assumption_outcomes` field explicitly warned about by the derivative
result note.

### 7.5 Common compiled envelope and representation variants

**Hypothesis:** One recipe language and one authority-traced compiled envelope
can support closed C# script, native Grasshopper graph, and later hybrid/worker
slot variants without separate Planner dialects.

**Proof:** A checked discriminator selects a variant-specific deterministic
validator under a common provenance, trace, invariant, and authorization
envelope.

**Falsifier:** Each representation requires a different semantic recipe or a
new top-level Planner.

### 7.6 Executable authorization

**Hypothesis:** Deterministic authority can distinguish valid inert IR from IR
that may execute now by rechecking implementation, operation, target, scope,
policy, capability, freshness, and invariant evidence.

**Proof:** Missing, stale, or mismatched evidence always refuses before
mutation; exact complete evidence permits only the declared attempt.

**Falsifier:** A compiler/model recommendation grants target or mutation
authority, or stale registry/receipt evidence remains executable.

### 7.7 Mechanical execution and receipt-fenced verification

**Hypothesis:** The model-free runner can execute authorized IR through existing
Rook operations and issue receipts that prove application and verification
truth without inferring success from transport completion.

**Proof:** C# and later native-graph paths cross managed solve-readiness, exact
target readback, verifier checks, and failure containment.

**Falsifier:** Success requires manual interpretation, unreceipted settle waits,
or model judgment inside runner advancement.

### 7.8 Bounded local worker slots

**Hypothesis:** Local models can perform a material fraction of implementation
labor when assigned narrow formula, script-body, topology, or repair slots whose
inputs and outputs are independently validated.

**Proof:** Frontier control and local-model panels run the same slot contracts;
eligibility is assigned from measured success, cost, and failure taxonomy.

**Falsifier:** A local model requires whole-task semantics, broad mutation
authority, or unbounded conversational repair to succeed.

### 7.9 Surprise, replanning, and product convergence

**Hypothesis:** Clarification, runtime failure, and changed authority can use the
same pattern: runner halt, typed evidence, Planner re-entry, immutable
parent-linked amendment, deterministic revalidation, and bounded resume.

**Proof:** No transcript dependence, no runner-authored semantics, no silent
graph mutation, and stale authority cannot cross amendments.

**Falsifier:** Product behavior depends on hidden chat state or a parallel
Planner path that bypasses recipe, validation, lineage, or receipts.

Only after this single-file vertical is stable should the same artifact/receipt
discipline be applied to multi-file Work Units and Merge Contracts.

## 8. Ordered Completion Strategy

The next work should proceed in this order:

1. Design and deterministically prove the generic task-local fact carrier.
2. Run the governed-resolution Planner revision as a separate empirical
   checkpoint.
3. Optionally continue exact accepted bytes through unchanged LM9B-C for the
   first joined model-authored transfer observation.
4. Stop empirical expansion and reconcile/implement the production LM9A
   semantic contribution.
5. Define the common compiled envelope and the C# representation variant using
   the already observed candidate shape.
6. Add deterministic executable authorization.
7. Connect authorized IR to the existing runner and managed verification
   receipts.
8. Add bounded worker slots and qualify local models by evidence.
9. Implement receipt-driven semantic/runtime replan and converge product entry
   points on the same artifact path.
10. Extend the proven single-file system to macro Work Units and fan-in.

The optional compiler continuation in step 3 is a scientific observation only.
No additional representation or execution work should proceed before step 4,
or the probe path will become a shadow product validator.

## 9. Architectural Review Rule For New Elements

Every proposed new field, record, artifact, receipt, vocabulary, gate, or model
role must answer:

```text
Who creates it?
What authority does it carry?
What is its identity and scope?
How does each model see it?
How is it deterministically verified?
What consumes it?
How is it versioned or superseded?
Can a second unrelated witness use the same mechanism?
```

An element without these answers is not ready to enter the architecture.

## 10. Final Reconciliation

The current proposal does not pivot away from the hard-won architecture.

It preserves:

- the topology's scarce-intelligence/cheap-worker gradient;
- scaffold-held local execution;
- the three-box Planner/Runner/Worker separation;
- semantic recipe authority above representation;
- intelligent compile producing inert output;
- deterministic advancement and execution authority;
- receipt-fenced verification and parent-linked replanning.

It adds the missing constructive answer to one question:

> How does authenticated new user meaning enter an already valid-but-blocked
> semantic artifact without mutation, invention, or loss of lineage?

The answer is: trusted ingress issues successor authority; the Planner authors
a complete successor artifact; deterministic machinery verifies exact authority,
isolation, identity, and readiness; the existing downstream path remains
unchanged.

That is the next hypothesis under the existing theory, and the first concrete
proof of the North Star's amendment/replan mechanism.
