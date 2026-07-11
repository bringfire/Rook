# Rook OpenProse Compile Run Alignment Note

Status: architecture note

Date: 2026-07-08

## Purpose

This note freezes the architectural insight from the post-LM8G `gh_edit`
discussion and the local OpenProse source review in `D:\prose`.

The short version:

```text
OpenProse:
  semantic contracts
  -> intelligent compile
  -> topology/canonicalizers/postcondition validators
  -> dumb run/reconciler

Rook:
  user intent
  -> Planner-authored semantic contract
  -> bounded intelligent compile
  -> deterministic validation of gh_create_* / gh_edit / verifier IR
  -> mechanical executor + authoritative verifier floor
```

The key correction is that `gh_edit` should be treated as compiled execution
IR, not as the Planner's semantic authoring surface and not as a broad small
worker language.

## OpenProse Grounding

The OpenProse claim is not just README wording. It is repeated in the canonical
skill docs, compiler contract, IR contract, and runtime code.

OpenProse checkout reviewed:

```text
D:\prose
commit: dbdc810b8191c4059e8e3d26a30d86f63bf461e0
status: clean
```

### Compile / Run Split

`D:\prose\skills\open-prose\responsibility-runtime.md`

- Lines 38-44 define the compile/run split: compile is intelligent; run is
  dumb.
- Lines 66-70 list the compile outputs: topology world-model, per-node
  canonicalizers, and per-node postcondition validators.
- Lines 135-137 state the layer rule: do not put semantic intelligence in the
  harness and do not reintroduce a judge in the wake or commit decision.

### Forme As Compile-Time Topology

`D:\prose\skills\open-prose\forme.md`

- Lines 27-31 say Forme emits the topology world-model and the run phase follows
  the frozen topology instead of re-deriving wiring.
- Lines 188-190 pin the failure posture: unsatisfied or ambiguous wiring is a
  diagnostic, never a silent guess.
- Lines 239-290 summarize the topology emission into compile-phase IR and the
  run-time reconciler reading those edges.

### Compiler Program

`D:\prose\skills\open-prose\compiler\index.prose.md`

- Lines 9-15 define the compiler as the intelligent compile phase whose output
  the dumb reconciler consumes.
- Lines 52-64 say contracts lower into topology nodes, canonicalizers, and
  postcondition validators only when relationships are clear; host routes,
  payloads, and tools must not be invented; wiring failure is surfaced.
- Lines 313-318 keep the writer step mechanical: write the already validated
  manifest only.

### Compile-Phase IR

`D:\prose\skills\open-prose\compiler\ir-v0.md`

- Lines 24-35 define the IR as generated JSON for the dumb reconciler, not an
  authoring surface, with no judge/verdict/pressure loop and no custom fields.
- Lines 104-124 define topology as Forme's resolved DAG.
- Lines 174-241 define canonicalizers as deterministic fingerprint artifacts.
- Lines 242-280 define postconditions as validator references, not a judge beat.
- Lines 281-296 define diagnostics, including compile rejection for error
  diagnostics such as ambiguous Forme matches.

### Runtime Code

`D:\prose\packages\reactor\src\sdk\run-project.ts`

- Lines 8-25 describe the two phases in code: `compileProject` runs compile
  sessions; `runProject` is the dumb run phase over compiled artifacts.
- Lines 407-414 mount the compiled project and run the boot sweep with compiled
  canonicalizers so propagation follows Forme's edges.
- Lines 514-551 show each node mounted with the canonicalizer emitted by the
  canonicalizer session, then booted.

`D:\prose\packages\reactor\src\reactor\index.ts`

- Lines 4-23 state the reconciler has no judge or policy artifact; it performs
  memo/skip, schedule, commit, and propagate.
- Lines 391-392 say the entire decision is fingerprint comparison.
- Lines 697-705 resolve memo inputs and skip by pure fingerprint comparison.
- Lines 815 and 949 show render spawning, while the reconciler remains dumb.
- Line 1008 begins the exact memo-key rule: key equals contract fingerprint plus
  input fingerprints.

### Nuance: Postcondition Enforcement

Do not overstate the present implementation. `D:\prose\packages\reactor\src\sdk\run-project.ts`
lines 132-134 say the run phase does not consult `perNode[...].postconditions`
today in that path, so postconditions are part of the compile contract and IR,
with deterministic lowering in `D:\prose\packages\reactor\src\postcondition\index.ts`,
but runtime enforcement is not uniformly load-bearing in every path yet.

For Rook this means: keep verifier-floor/postcondition language precise. The
principle is valid; implementation evidence should name which verifier/gate is
actually active.

### Hooks, Ports, And Bootstrapping

OpenProse does have hook-like seams, but they are deliberately boxed. They are
not arbitrary lifecycle callbacks where semantic authority can hide.

`D:\prose\skills\open-prose\SKILL.md`

- Lines 115-144 define command routing for `prose compile`, `prose serve`,
  `prose react`, `prose run`, and `prose status`.
- Lines 156-167 define the host primitive adapter: `spawn_session`, `ask_user`,
  `read_state` / `write_state`, `copy_binding`, and `check_env`.
- Line 182 names `kind: gateway` files as external-driven responsibility
  surfaces.
- Line 205 says run state snapshots referenced responsibility, function,
  gateway, and pattern sources.

`D:\prose\skills\open-prose\responsibility-runtime.md`

- Lines 127-131 say the harness serves compiled intent by registering concrete
  trigger adapters and translating trigger events into wakes.
- Lines 198-201 classify wake receipts as input-driven, self-driven, or
  external-driven.
- Lines 187-190 say authors may declare optional gateway metadata, while the
  compiler infers concrete trigger setup only when the source graph is clear.

`D:\prose\packages\reactor\src\reactor\index.ts`

- Lines 61-67 define seam ports as the injection boundary.
- Lines 215-237 define reconciler ports such as `spawnRender`,
  `resolveInputFingerprints`, `spawnRenderAsync`, and the reserved
  `onTopologyMoved` forward seam.

`D:\prose\packages\reactor-cli\src\run\run-core.ts`

- Lines 160-198 define `ensureCompiledIR`, the shared "ensure IR fresh /
  compile-if-stale" preflight used by run-phase commands.

`D:\prose\packages\reactor-cli\src\run\http-server.ts`

- Lines 8-20 and 115-119 define `POST /trigger/<node>` as an external wake
  ingress, serialized through one queue.

`D:\prose\packages\reactor\src\sdk\run-project.ts`

- Lines 293-349 expose injected runtime seams such as `contractFor`,
  `projectTruthFor`, `buildRender`, `sandbox`, and `renderBackend`.

So "hooks" exist, but as boxed gates, injected ports, and ingress paths that
produce or lead to receipts:

```text
activation / command routing
-> host primitive adapter
-> gateway or trigger ingress
-> compile-if-stale preflight
-> reconciler ports
-> receipts / world model updates
```

The governing rule:

```text
Hooks force process, not meaning.
```

They are literal machine parts in the host/runtime. They can force command
routing, skill loading, compile freshness checks, validation gates, execution
steps, verifier reads, receipts, and downstream wakes. They must not secretly
decide user intent, invent a design, or mutate semantic authority outside a
declared source artifact.

They do not replace the compile/run split. The skill itself solves the
bootstrapping problem: before the compiled graph exists, the host agent needs an
activation contract that tells it which language it is in, which docs to load,
which source/compiled/runtime distinctions matter, and when to call the real
binary instead of improvising a runtime. After that activation layer, durable
semantics belong in authored source and compiled artifacts, not in hidden hook
logic.

For Rook, the corresponding layer should be an explicit boot skill or task
builder hook that produces a versioned, receipted task envelope. If it classifies
the request or proposes a path such as direct tool, scalar worker splice,
Planner recipe, or compiler-to-`gh_edit`, that decision must be part of the
envelope's explicit schema, fingerprint, diagnostics, and validation report. The
authority model for this router is not settled by this note: it could be
deterministic, model-authored, or hybrid in a later reviewed slice. Until that
slice exists, the boot layer is a named seam, not a hidden callback with
semantic authority.

The Rook boot/task-envelope hook is therefore a mandatory mechanical gate. It
may require classification, validation, fingerprints, and receipts, but any
semantic choice it records must be explicit, schema-bound, and reviewable.

## Rook Grounding

The `gh_edit` interpretation below is grounded in the current Rook managed GH
handler, not only inferred from OpenProse:

```text
Rook source revision reviewed: 1e04ca8576c642e466f6822468b3323a7a1d76b0
```

- `C:\UDEV\Rook\src\Rook\Handlers\ShortIdRegistry.cs` lines 7-11 define the
  short-ID registry as a bidirectional mapping between stable canvas-facing short
  IDs and Grasshopper instance GUIDs.
- `ShortIdRegistry.cs` lines 21-75 show epoch rebuild and newly-created object
  registration, including persistent short-ID caching inside the session.
- `C:\UDEV\Rook\src\Rook\Handlers\GrasshopperHandler.cs` lines 6420 and
  6608-6615 show `gh_snapshot` rebuilding the registry and returning the
  current `epoch`.
- `GrasshopperHandler.cs` lines 7099-7145 show `ApplyEdit` requiring and
  validating the request epoch before mutating the canvas.
- `GrasshopperHandler.cs` lines 7197-7204, 7254-7258, and 7468-7472 show
  batch-local temp IDs being mapped to live GUIDs and resolved during create,
  disconnect, and connect operations.
- `GrasshopperHandler.cs` lines 7569-7593 show `edit_summary` reporting
  `solve_scheduled`, `verification_deferred`, `temp_id_map`, and instance
  GUIDs.

So the Rook claim is concrete: `gh_edit` already has an epoch-sensitive,
short-ID/temp-ID, solve/verification contract. That is a compiler target shape,
not a friendly semantic authoring surface.

## Rook Interpretation

The Rook equivalent should not be:

```text
Planner writes gh_edit.
Worker writes gh_edit.
Executor trusts gh_edit because a model produced it.
```

The Rook equivalent should be:

```text
User brief
-> Planner Task Builder / Intent Envelope Builder
-> Planner-authored semantic graph contract
-> semantic_contract_validate
-> bounded intelligent compile
-> deterministic IR validation
-> tool IR:
     gh_create_csharp_script
     gh_snapshot epoch and short-id discovery
     gh_edit batch with temp ids / short-id flows
     settle / inspect / errors verifier plan
-> executor
-> verifier floor and receipts
```

`gh_edit` is analogous to compiled IR. It is operationally precise:

- it needs the current canvas epoch;
- it uses temp IDs inside one batch;
- it returns live short IDs through `temp_id_map`;
- it can defer verification until the solver settles;
- it is excellent as a compiler target and poor as a semantic authoring
  language.

## Naming Correction

The phrase `Intent Compiler / Request Builder` is too muddy.

Use:

```text
Planner Task Builder / Intent Envelope Builder
```

for the deterministic step that packages:

- user brief;
- canvas/project context;
- template or recipe menu;
- output schema;
- policy and safety rules;
- available worker slots.

It does not decide the design and does not lower to tools.

Use:

```text
Planner
```

for the model or authoring process that selects a semantic recipe shape,
declares intent gaps, chooses bounded worker slots, and states verifier
expectations.

Use:

```text
Compiler
```

for the fixed, constrained compile program that lowers a validated semantic
contract to exact Rook tool calls and verifier choreography. Compile stages may
use bounded model judgment to select representation, resolve semantic
relationships, construct topology, or author schema-bounded implementation
artifacts. The compiler harness deterministically validates those outputs for
schema, authority, provenance, topology, and IR safety before execution.

Use:

```text
Worker
```

for bounded authored content inside an already-validated box: script body,
formula fragment, scalar value, repair parameters, or other narrow action input.
The worker does not receive raw GUID authority or broad `gh_edit` authority by
default.

## Implication For The Next Family

The next graph-building line should start with a semantic recipe surface, not
with a worker or Planner writing `gh_edit` directly.

Candidate slice:

```text
LM9A = Planner Graph Recipe Surface
```

Recommended first fixture:

```text
10 x 10 radial box height field
```

The semantic contract should express the source-owned goal, observations and
dependencies, desired maintained truth, semantic postconditions, assumptions,
unresolved intent, invariants, shape boundaries, required capabilities, and any
bounded worker slots. The fixture brief supplies the 10 x 10 box count and the
radial height relationship. It does not itself supply spacing, box footprint,
minimum or maximum height, or falloff behavior. The Planner must either leave
those details unresolved or label any policy-permitted defaults as assumptions;
they must not be smuggled in as user facts.

The bounded intelligent compile phase may choose a concrete representation such
as one C# generator component plus sliders/controls, then lower that to:

- create script component;
- snapshot epoch;
- `gh_edit` sliders / connections / grouping;
- managed readiness wait and receipt-fenced inspect.

Anti-goal for LM9A:

```text
Do not ask a small worker to write a gh_edit batch.
Do not ask the Planner to author short IDs, temp IDs, connection strings, or
epoch-specific mutation payloads.
```

Those are compiler responsibilities. Intelligence inside that boundary remains
narrower than Planner intelligence and is constrained by fixed compile stages,
limited context, exact output schemas, deterministic IR validation, and
fail-closed diagnostics for ambiguous or unsupported lowering.

## LM8 Exit Checkpoint And Live-Execution Prerequisite

The evidence line advanced after this note was first drafted:

- the scalar family reached live identity, non-identity, and affine-projection
  receipts;
- the affine worker case repeated `20/20` with the same worker-authored `3.0`
  and source-owned observed result `7.5`;
- LM8K moved `gh_set_value` freshness from settle polling into a managed
  Grasshopper solve-readiness receipt;
- LM8M replayed the affine sample `20/20` with one managed wait and one
  receipt-fenced read per child, zero settle reads, and no provenance
  discrepancies.

That closes scalar-family harness qualification for this roadmap horizon. More
scalar arithmetic can still compare model floors, but it should not delay the
semantic recipe/compiler boundary.

The live compiler path has one known product prerequisite. Today the template
instantiator's deferred `gh_edit` path still waits by polling `gh_status` and
sleeping in
`mcp_server/src/rook/canvas_director_templates/instantiator.py`.
`gh_edit` does not yet emit the managed readiness receipt that `gh_set_value`
now emits. Consequently:

```text
LM9A semantic recipe design and validation: not blocked
bounded intelligent recipe-to-tool/verifier compile and deterministic IR validation: not blocked
live compiled recipe through gh_edit: blocked on managed readiness fencing
```

The durable follow-up is to extend the managed receipt mechanism to the exact
`gh_edit` mutation contract selected by the compiler. It is not a blanket task
to replace every historical delay in `server.py`; the compiler IR and its final
mutation boundary should determine the receipt that live verification consumes.

## Testability Consequence

The OpenProse split also clarifies how Rook can test this abstraction before a
full user-intent-to-live-graph run exists. The semantic-contract grammar can
remain generic while each evaluation fixture carries a private, domain-specific
oracle. A test may require radial ordering, forbid invented spacing, or expect
an unsupported-capability diagnostic without making any of those fields part of
the product schema.

Rook should evaluate the boundary in three stages:

```text
deterministic semantic-contract conformance
-> real Planner authorship over paired briefs and frozen real environment state
-> bounded intelligent compile to deterministically validated IR, no dispatch
```

Counterfactual and metamorphic cases are more informative than exact recipe
goldens: change one user fact, environment observation, policy, or capability
and pre-register which clauses or compile decisions may move. Hard validity and
semantic fidelity remain separate scores. Irreducibly semantic fidelity may use
independent model review and human spot review; runtime mutation and verifier
truth never do.

This preserves the architecture's extensibility. New examples usually add
evaluation coverage. They become product-language requirements only when they
expose a genuinely unsupported semantic or compiler capability.

## Why This Matters

The LM6-LM8 evidence proved that small workers can be useful when the box is
validated and narrow. The live `gh_edit` exercise showed a different boundary:
large canvas construction is not just "more worker work." It requires a semantic
source artifact and a compiler.

This aligns Rook with OpenProse:

```text
semantic source stays durable and inspectable;
compiled IR is disposable and exact;
runtime executes compiled artifacts dumbly;
verification decides acceptance;
model judgment is moved to bounded authoring phases, not hidden in tool calls.
```
