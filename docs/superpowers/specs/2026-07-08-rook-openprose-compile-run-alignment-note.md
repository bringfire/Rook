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
  -> Planner-authored semantic recipe
  -> deterministic compiler/lowering
  -> gh_create_* / gh_edit / verifier plan
  -> dumb executor + verifier floor
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

## Rook Grounding

The `gh_edit` interpretation below is grounded in the current Rook managed GH
handler, not only inferred from OpenProse:

- `C:\UDEV\Rook\src\Rook\Handlers\ShortIdRegistry.cs` lines 7-11 define the
  short-ID registry as a bidirectional mapping between stable canvas-facing short
  IDs and Grasshopper instance GUIDs.
- `ShortIdRegistry.cs` lines 29-75 show epoch rebuild and newly-created object
  registration, including persistent short-ID caching inside the session.
- `C:\UDEV\Rook\src\Rook\Handlers\GrasshopperHandler.cs` lines 6345-6537 show
  `gh_snapshot` rebuilding the registry and returning the current `epoch`.
- `GrasshopperHandler.cs` lines 7024-7063 show `ApplyEdit` requiring and
  validating the request epoch before mutating the canvas.
- `GrasshopperHandler.cs` lines 7070, 7125-7128, 7182-7183, 7395-7397, and
  7589-7593 show batch-local temp IDs being mapped to live GUIDs and resolved
  during create / disconnect / connect operations.
- `GrasshopperHandler.cs` lines 7496-7515 show `edit_summary` reporting
  `solve_scheduled`, `verification_deferred`, `temp_id_map`, and instance GUIDs.

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
-> Planner-authored semantic graph recipe
-> recipe_validate
-> deterministic compiler/lowering
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

for the deterministic lowering from a validated semantic recipe to exact Rook
tool calls and verifier choreography.

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

The recipe should express:

- task family: parametric generated geometry;
- acceptable template family: generated field geometry with bounded controls;
- source-owned field semantics: a 10 x 10 box array whose heights are lowest at
  the center and rise with radial distance;
- exposed controls desired by the task: grid count, spacing, min height, max
  height;
- relationship: radial distance from center maps to height;
- worker slots, if any: bounded script body or formula fragment;
- verifier expectations: 100 boxes, height range min/max, no GH errors;

The compiler/template layer may choose a concrete representation such as one
C# generator component plus sliders/controls, then lower that to:

- create script component;
- snapshot epoch;
- `gh_edit` sliders / connections / grouping;
- settle and inspect.

Anti-goal for LM9A:

```text
Do not ask a small worker to write a gh_edit batch.
Do not ask the Planner to author short IDs, temp IDs, connection strings, or
epoch-specific mutation payloads.
```

Those are compiler responsibilities.

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
