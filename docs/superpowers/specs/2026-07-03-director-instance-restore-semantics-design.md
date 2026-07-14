# Director Instance Restore Semantics Design

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md

Date: 2026-07-03
Status: diagnostic result recorded
Branch: `codex/director-instance-restore-semantics`
Parent branch: `codex/rookvision-canvas-director`
Planned first commit scope: `test(director): probe instance restore semantics`

## Purpose

The CanvasDirector Pearson smoke reached the existing Director runtime path and
then failed inside native frame-capture restore safety. The failure was not in
CanvasDirector extraction, authoring spec persistence, track compilation, or
video assembly. It happened while Director tried to apply a frame transform and
then restore the Rhino object back to its baked source pose.

The restore hardening instrumentation did its job: it showed that frame 2 asked
for a pure Z translation of about `0.628483`, but the restored bbox for an
`InstanceReference` returned thousands of model units away in X/Y. That is not
a tolerance problem. It is a native Director restore-semantics problem until
proven otherwise.

This design defines the next diagnostic slice. It should answer whether the
current native transform call behaves differently for block instances than for
simple objects, and whether Director's inverse-transform restore assumption is
valid for `InstanceReference` objects.

## Branch Guidance

This work lives on a child branch named:

```text
codex/director-instance-restore-semantics
```

The name is intentional. Snapshot/original-state restore is only one possible
fix. The first slice must diagnose restore semantics before choosing a fix.

Keep the touched code narrowly scoped to native Director restore diagnostics and
focused tests. CanvasDirector, bounded restore tolerance, compiler shape,
Python `dirty_partial_state` behavior, and video assembly remain parked.

## Current Call Under Test

The current Director object mutation helper in
`src/RookNative/Handlers/DirectorFrame.cpp` uses this exact call:

```cpp
pDoc->TransformObject(objRef, xform, true, false, true)
```

The first diagnostic slice must record that this call path was used. Do not
infer what the three boolean parameters mean unless their semantics are verified
from Rhino SDK documentation or an existing, trusted repo pattern.

The slice should answer concrete questions about this call:

- does it mutate the existing Rhino object or replace it?
- does it preserve object UUID?
- does it preserve runtime serial number?
- does it preserve instance definition identity for block instances?
- does an `InstanceReference` round-trip `InstanceXform()` through
  apply-and-inverse restore?
- does the bbox round-trip match the source pose when the same transform is
  applied to a simple non-instance control object?

## Non-Goals

Do not do any of the following in this slice:

- change CanvasDirector extraction, persistence, or compile behavior;
- continue from `unsafe_failed` or suppress `dirty_partial_state`;
- tune restore bbox tolerance;
- implement a general object replacement or snapshot restore system;
- make Pearson the automated regression fixture;
- infer Rhino SDK boolean meanings from intuition.

If the repro proves that snapshot/original-state restore is needed, write that
as a follow-up design after the evidence is in.

## Synthetic Repro Fixture

Prefer a fresh synthetic Rhino fixture over the Pearson model. Pearson remains
the final acceptance smoke after the native behavior is understood.

The repro must run only in a scratch/throwaway Rhino document or a disposable
test fixture with explicit cleanup. It may intentionally produce
`dirty_partial_state:true`, so it must not mutate an open user/project model by
accident. If the harness cannot prove it is operating in a disposable document,
it must refuse to run before creating objects or calling frame capture.

The repro should create two objects at the same Pearson-scale coordinate
neighborhood:

1. A simple non-instance control object.
2. A block instance / `InstanceReference`.

Both objects should be subjected to the same small pure Z translation through
the same Director frame-capture restore path. The control object is important:

- if the simple object restores and the `InstanceReference` does not, the bug
  is isolated to instance semantics;
- if both fail, investigate matrix convention, source-state setup, or
  `TransformObject` call usage before designing an instance-specific fix.

The two objects should use comparable source bboxes. A good fixture is the same
small box-like source geometry placed near coordinates on the order of the
Pearson smoke, for example around X `125000..370000`, Y `-330000..3000`, and Z
`-30000..37000`, with one copy left as normal document geometry and one copy
inserted through a block definition. The minimum animation sequence is two
frames:

```text
frame 0: identity/source pose
frame 1: tiny pure Z translation
```

A one-shot transform is not enough; it can pass while still missing the restore
failure pattern exposed by the Pearson smoke.

The fixture should be deterministic and cheap. It should not depend on a
project file, Pearson object IDs, or Grasshopper.

## Required Evidence

For each object and for each apply/restore phase, record enough native evidence
to determine whether the object was mutated in place, replaced, or restored
through a different state than Director expects.

The important evidence must be captured inside the native Director
transform/restore path at the moment the object is looked up, transformed, and
restored. A diagnostic-only native evidence envelope or a temporary native probe
helper is acceptable. A Python readback after frame capture may be useful as
secondary corroboration, but it is not sufficient for the fields below.

Required common fields:

- object id requested by Director;
- object type before apply, after apply, and after restore;
- runtime serial number before apply, after apply, and after restore;
- UUID before apply, after apply, and after restore;
- requested transform matrix;
- requested inverse transform matrix;
- exact call path string, including
  `pDoc->TransformObject(objRef, xform, true, false, true)`;
- apply transform return value;
- restore transform return value;
- bbox before apply, after apply, and after restore;
- signed `bbox_delta_min` and `bbox_delta_max` as `restored - source`;
- absolute `bbox_max_delta`.

Required instance-only fields:

- instance definition id or name before apply, after apply, and after restore,
  when available from RhinoCommon/Rhino SDK APIs already used in the repo;
- `InstanceXform()` before apply, after apply, and after restore;
- whether the instance object can still be resolved by the original UUID after
  apply and after restore.

If a field cannot be produced for a given object type, the evidence should say
so explicitly rather than silently omitting it.

## Decision Criteria

Use the synthetic repro to choose the next move:

- Simple object restores, instance does not:
  isolate the next design to `InstanceReference` restore semantics.
- Both simple object and instance fail:
  inspect matrix convention, source-state setup, or the `TransformObject` call
  path before any instance-specific fix.
- UUID or runtime serial changes:
  Director may be observing replacement semantics, and source-state/restore
  bookkeeping must account for that before relying on inverse restore.
- Instance definition identity changes:
  block instance mutation is not preserving the definition relationship that
  Director assumes.
- `InstanceXform()` fails to round-trip while bbox drifts:
  the likely failure is instance transform restore, not bbox serialization.
- Both objects round-trip cleanly:
  Pearson may involve nested block definitions, non-trivial instance transforms,
  definition geometry, or source-state mismatch beyond the simple repro.

Do not proceed to a fix until the evidence clearly points to one of these
branches.

## Diagnostic Result

The first synthetic live diagnostic was run against a native-only deployed
Debug build from `codex/director-instance-restore-semantics`.

Command:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_routes_live.py::test_director_instance_restore_semantics_large_coordinate_probe -q -s
```

Result:

- pytest result: `1 passed`;
- run root:
  `C:\Users\bring\AppData\Local\Rook\rookvision_director\instance_restore_semantics_558860aa12a941f3be09e6e44726ced2`;
- persisted summary:
  `logs\instance_restore_semantics_probe.json`;
- run state: `complete`;
- frame indices: `[1, 2]`;
- simple Brep control `restored`: `[true, true]`;
- simple Brep control `bbox_max_delta`: `[0.0, 0.0]`;
- `InstanceReference` `restored`: `[true, true]`;
- `InstanceReference` `bbox_max_delta`: `[0.0, 0.0]`;
- `InstanceReference` definition id/name and `InstanceXform()` round-tripped
  cleanly for the simple large-coordinate pure-Z fixture.

The synthetic fixture did not reproduce the Pearson failure. It shows that a
simple large-coordinate block instance with identity scale/rotation can
round-trip through the current Director apply/inverse-restore path. It also
shows that the runtime serial number changes on the transformed frame for both
the Brep control and the `InstanceReference`, while the object UUID remains
resolvable and the bbox returns to the source pose.

Classification:

- the observed Pearson failure is not explained by a simple large-coordinate
  `InstanceReference` plus a small pure-Z translation;
- the next diagnostic should extend the synthetic fixture toward Pearson-like
  block structure before changing restore semantics, especially nested block
  definitions, non-identity instance transforms, non-uniform scale or rotation
  if supported by the relevant route, definition geometry complexity, and
  source-state mismatch;
- any future restore design should account for runtime-serial churn under
  `TransformObject`, but this diagnostic alone does not justify snapshot or
  replacement restore semantics.

### Minimized Pearson Probe

A second live diagnostic was run against the actual Pearson object that failed
the CanvasDirector smoke:

```text
a28cbdb5-51fa-46b2-b18b-ab880b54ded7
```

The Pearson file was open in Rhino, and the MCP session was rebound to the live
RookNative instance on port `62574` after the previous active binding was found
to be stale. The probe used only two frames:

```text
frame 1: identity/source pose
frame 2: pure Z translation of 0.628483
```

Run root:

```text
C:\Users\bring\AppData\Local\Rook\rookvision_director\pearson_restore_min_probe_20260703_214114
```

Persisted summary:

```text
logs\pearson_restore_min_probe_summary.json
```

Result:

- run state: `unsafe_failed`;
- frame 1: `dirty_partial_state:false`;
- frame 2: `dirty_partial_state:true`;
- object type: `InstanceReference`;
- instance definition id:
  `2a38c499-7763-4532-a5ff-d71b90d9d95c`;
- instance definition name:
  `3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL`;
- frame 2 requested transform:
  pure Z translation `0.628483`;
- frame 2 `InstanceXform()` after apply:
  pure Z translation `0.628483`;
- frame 2 `InstanceXform()` after restore:
  identity/source pose;
- frame 2 `restore_transform_returned:true`;
- frame 2 immediate restore verifier bbox delta:
  `bbox_delta_min:[-3675.6218127947213, 1.0617077350616455e-07, 4.5180058805271983e-07]`;
- frame 2 immediate restore verifier bbox delta:
  `bbox_delta_max:[963.9053885611938, 69.40132311977459, 4.792309482581913e-07]`;
- frame 2 `bbox_max_delta:3675.6218127947213`.

A read-only `/director/object-states` check immediately after the failed run
reported the Pearson object back at the source bbox:

```text
min [125718.338195, -328450.993563, -29189.909203]
max [367191.403245, 2881.052246, 37014.791026]
```

Classification:

- the Pearson object reproduces the failure in the minimized two-frame probe;
- the failure is not explained by `InstanceXform()` failing to apply or return
  to identity; it did both;
- the later document readback being clean suggests the live document was not
  left displaced even though the frame evidence correctly reported
  `dirty_partial_state:true`;
- the likely failing surface is the immediate native bbox readback used by the
  restore verifier for this complex block definition after `TransformObject`,
  not the simple inverse transform itself;
- the next diagnostic should compare immediate bbox readback against a forced
  redraw/regeneration or alternate precise bbox path for this same object,
  before designing snapshot/original-state restore.

## Evidence Contract Note

The existing restore evidence contract remains:

- `bbox_delta_min` and `bbox_delta_max` are signed directional deltas computed
  as `restored - source`;
- `bbox_max_delta` is absolute and is the guard value;
- hard failures stay hard;
- Python continues to stop on native `dirty_partial_state:true`.

This branch should not reintroduce absolute per-axis directional arrays.

## Testing Strategy

### Native Source Tests

Add source-level tests that pin:

- the current transform call expression under test;
- the presence of the call-path evidence field;
- signed directional bbox delta wording;
- no bounded tolerance constants or CanvasDirector changes in this slice.

These tests are cheap and prevent the diagnostic contract from drifting while
the live repro is being built.

### Live Rhino Repro

Add a live Rhino repro that creates the synthetic large-coordinate control
object and block instance, applies the same tiny Z transform through the
Director frame-capture restore path, and writes/prints structured evidence for
both objects.

The live repro should assert only the diagnostic envelope and hard safety
behavior initially. It should not force a fix outcome. The useful product is the
comparison between the simple object and the `InstanceReference`.

### Pearson Acceptance

Do not use Pearson as the automated regression fixture. After the synthetic
diagnosis is understood and an implementation fix is separately approved, rerun
the full Pearson chain:

```text
extract -> spec -> compile -> run_compiled_track -> assemble_director_video
```

## Acceptance For This Spec Slice

This slice is complete when:

- the synthetic repro can produce structured evidence for the simple control
  object and `InstanceReference`;
- the evidence records the exact native transform call path;
- UUID/runtime serial/definition identity/instance transform/bbox state are
  visible before apply, after apply, and after restore where applicable;
- the result distinguishes instance-specific failure from broader transform
  usage failure;
- no CanvasDirector or tolerance behavior has changed.

## Open Questions

- What are the verified Rhino SDK semantics of the three boolean arguments in
  `TransformObject` for the overload currently used?
- Does `TransformObject` mutate or replace `InstanceReference` objects under
  this call path?
- Does the runtime serial number remain stable for transformed instances?
- Does `InstanceXform()` round-trip exactly for a pure translation at large
  coordinates?
- Does a nested or non-uniform block instance behave differently from the simple
  synthetic fixture?
