# Director Pose Bbox Design

Date: 2026-07-03
Status: ready for user review
Branch: `codex/director-instance-restore-semantics`
Parent branch: `codex/rookvision-canvas-director`

## Purpose

The minimized Pearson restore probe reproduced the Director frame-capture
failure on object `a28cbdb5-51fa-46b2-b18b-ab880b54ded7`, but the phase
evidence narrowed the problem:

- `TransformObject` applied the requested Z translation.
- `InstanceXform()` moved to Z `0.628483` and returned to identity after
  restore.
- The immediate bbox readback was wrong in X/Y after transform and after
  restore.
- A later `/director/object-states` readback reported the object back at the
  source bbox.

The working hypothesis is therefore:

```text
Director's pose truth is currently plain cached CRhinoObject::BoundingBox().
For complex block instances, that cached bbox can be stale or unstable
immediately after TransformObject, even when the object transform has
round-tripped correctly.
```

This slice should prove whether object-level `GetTightBoundingBox()` is the
right Director pose bbox primitive. It must not change restore semantics until
the probe gate is clean.

## Current Evidence And Precedent

Director currently uses plain `obj->BoundingBox()` for:

- `/director/object-states` in `DirectorHandler.cpp`;
- source-state validation in `ValidateFrameObjects()`;
- phase evidence in `NativeObjectPhaseEvidence()`;
- restore verification in `DirectorObjectPoseGuard::Restore()`.

Rook already has a local native precedent in `BlocksHandler.cpp`: block
definition bounds prefer object-level `CRhinoObject::GetTightBoundingBox()` and
fall back to `BoundingBox()`. The comment there says object-level tight bounds
are representation-independent and preserve nested `CRhinoInstanceObject`
instance transforms.

This slice should apply that lesson only to Director pose verification. It is
not a repository-wide bbox semantics change.

## Scope

This is a Director-only slice. Allowed production scope:

- `src/RookNative/Handlers/DirectorFrame.cpp`
- `src/RookNative/Handlers/DirectorFrame.h`
- `src/RookNative/Handlers/DirectorHandler.cpp`

Allowed tests and docs:

- native/source tests for Director bbox contracts;
- a live/minimized Pearson probe harness or one-off documented diagnostic;
- this spec and the follow-up implementation plan.

Do not change:

- CanvasDirector extraction, persistence, or compile behavior;
- Python `dirty_partial_state` behavior;
- bbox tolerances;
- snapshot/original-state restore semantics;
- global `/measure/bbox`, selection bbox filtering, block tools, scene graph,
  or unrelated geometry handlers.

## Design Overview

The slice has two checkpoints and two commits.

### Checkpoint 1: Bbox Method Probe

Add diagnostic evidence that compares two bbox methods at each Director object
phase:

- `raw_bbox`: `obj->BoundingBox()`;
- `tight_bbox`: object-level `obj->GetTightBoundingBox(...)`;
- method validity for both;
- deltas from the phase-expected bbox for both;
- `InstanceXform()` and existing instance definition evidence.

This probe keeps existing restore behavior unchanged. It may still report
`dirty_partial_state:true`; that is expected if the existing raw bbox verifier
fails.

### Checkpoint 2: Director Pose Bbox Helper

Only if Checkpoint 1 passes the gate, add a shared Director helper named
`DirectorObjectPoseBbox()`.

The helper contract is:

```text
Return the world-space bbox used for Director source-state and restore
verification. Prefer object-level GetTightBoundingBox(); fall back to
BoundingBox(); report which method was used.
```

Use the helper consistently in the Director runtime:

- `/director/object-states`;
- source-state validation;
- phase evidence;
- restore verification.

The helper should record `bbox_method` in native responses and frame evidence,
for example:

- `tight_object`;
- `raw_object_fallback`;
- `unavailable`.

The goal is one Director definition of "pose bbox truth." Do not fix only
restore verification while leaving `/director/object-states` on a different
primitive.

For this slice, `bbox_method` is native response/evidence metadata. Python
currently reduces source state to `bbox_min`, `bbox_max`,
`validation_strength`, and `state_hash`; preserving `bbox_method` into run
inputs would require explicit Python scope and is not required for this native
Director probe/fix slice.

## Phase Expected Bbox

Checkpoint 1 must compare bbox methods against the expected bbox for each
phase, not only against source bbox.

Phase expectations:

- `phase_before_apply`: source bbox;
- `phase_after_apply`: source bbox transformed by the requested transform;
- `phase_before_restore`: source bbox transformed by the requested transform;
- `phase_after_restore`: source bbox.

For the hard gate, this comparison is scoped to the minimized Pearson pure-Z
translation probe. In that case the phase-expected bbox is the source min/max
translated by the vector and is a strict expected value.

For any general affine transform, transforming all eight source-bbox corners
and taking the resulting axis-aligned bounding box is only a coarse diagnostic
unless the source geometry is box-equivalent. It is the AABB of the old bbox,
not necessarily the tight bbox of transformed non-box geometry. Do not use that
coarse affine expectation as a hard gate for rotations, shears, or scales on
arbitrary geometry.

The evidence should make the comparison explicit:

- `phase_expected_bbox`;
- `raw_bbox_delta_min`, `raw_bbox_delta_max`, `raw_bbox_max_delta`;
- `tight_bbox_delta_min`, `tight_bbox_delta_max`, `tight_bbox_max_delta`;
- `bbox_tolerance`;
- `bbox_tolerance_policy`.

Signed delta arrays remain directional: `observed - expected`. Max-delta
fields remain absolute.

## Hard Gate

Proceed from probe to helper only if the minimized Pearson probe shows all of
the following:

- raw `BoundingBox()` reproduces the wrong X/Y in the same phase where Pearson
  currently fails;
- object-level `GetTightBoundingBox()` is valid;
- tight bbox matches the pure-translation phase-expected bbox within the
  existing strict tolerance for before-apply, after-apply, before-restore, and
  after-restore;
- `InstanceXform()` remains correct: source, Z `0.628483`, Z `0.628483`,
  source;
- no hard failure path is being hidden or downgraded.

If any condition is false, stop after Checkpoint 1 and review the evidence.

Do not proceed if the result is ambiguous. Do not raise tolerance, add sleeps,
or change restore semantics in this slice.

## Implementation Notes

The probe can be implemented by extending the existing native phase evidence
rather than adding a new public route. The minimized Pearson run already
exercises the exact Director frame-capture path that failed.

The helper implementation should reuse the local block-handler pattern:

```cpp
ON_BoundingBox bbox;
if (obj->GetTightBoundingBox(bbox) && bbox.IsValid())
    return tight_object;

bbox = obj->BoundingBox();
if (bbox.IsValid())
    return raw_object_fallback;

return unavailable;
```

Use the object-level `GetTightBoundingBox()`, not geometry-level
`Geometry()->GetTightBoundingBox()`, so nested instance transforms remain part
of the object-space-to-world-space calculation.

If `GetTightBoundingBox()` has overload details that affect transform handling,
verify usage against existing repo patterns or Rhino SDK documentation before
coding. Do not guess the overload semantics.

## Evidence And Failure Behavior

For Checkpoint 1:

- keep `dirty_partial_state` behavior unchanged;
- keep raw restore verification as-is until the gate is reviewed;
- record both raw and tight evidence even on failing frames when possible;
- preserve hard failures for missing objects, deleted objects, invalid
  transforms, invalid bboxes, and failed `TransformObject`.

For Checkpoint 2:

- after the helper is adopted, source validation and restore validation should
  compare against helper-produced Director pose bboxes;
- native responses and frame evidence should say which method was used;
- fallback to raw bbox should be visible and should not silently masquerade as
  tight bbox;
- if neither method returns a valid bbox, keep the current hard failure shape.

## Testing Strategy

### Source Tests

Add or update native source tests that pin:

- `BoundingBox()` and `GetTightBoundingBox()` are both present in the probe
  evidence path;
- phase-expected bbox comparison exists for apply and restore phases;
- the shared helper is used by `/director/object-states`,
  `ValidateFrameObjects()`, phase evidence, and restore verification after the
  gate;
- no tolerance constants, sleeps, CanvasDirector files, or unrelated bbox
  handlers are changed.

### Live Diagnostic

Rerun the minimized Pearson probe:

```text
object: a28cbdb5-51fa-46b2-b18b-ab880b54ded7
frame 1: identity
frame 2: Z translation 0.628483
```

The probe output must show raw-vs-tight comparison for all four phases.

### Acceptance After Helper

After the helper commit, rerun the minimized Pearson probe first. It must
complete without `dirty_partial_state:true` and must record the expected
`bbox_method`.

Only after the minimized probe passes should the team rerun the full Pearson
CanvasDirector acceptance chain:

```text
extract -> spec -> compile -> run_compiled_track -> assemble_director_video
```

## Non-Goals

- No snapshot/original-state restore.
- No tolerance changes.
- No sleeps or timing waits.
- No CanvasDirector changes.
- No global bbox behavior changes.
- No full Pearson acceptance until the minimized probe passes.

## Open Questions

- Does object-level `GetTightBoundingBox()` return the correct immediate bbox
  for the minimized Pearson object after apply and after restore?
- Does it remain correct for other existing Director fixture objects?
- If a later slice needs run-input provenance for bbox method, should Python
  preserve native `bbox_method` in `source_state` or store it separately as
  evidence metadata?

## Implementation Result

The first probe showed the source-state side of the contract was still using
raw cached `BoundingBox()` data. That made the later tight-bbox phase evidence
look wrong because the comparison source itself was wrong. The implementation
therefore changed Director pose truth consistently to `DirectorObjectPoseBbox()`
with object-level `GetTightBoundingBox()` preferred and raw `BoundingBox()` only
as an explicit fallback.

Checkpoint 1 diagnostic result:

- run root: `C:\Users\bring\AppData\Local\Rook\rookvision_director\pearson_pose_bbox_probe_20260703_223547`
- object id: `a28cbdb5-51fa-46b2-b18b-ab880b54ded7`
- task state: `unsafe_failed`
- diagnosis correction: the failure was caused by raw-bbox Director source
  state, not by `GetTightBoundingBox()` being unsuitable

After wiring `DirectorObjectPoseBbox()` through Director object states, source
validation, phase evidence, and restore verification, the minimized Pearson
probe passed:

- run root: `C:\Users\bring\AppData\Local\Rook\rookvision_director\pearson_tight_pose_bbox_probe_20260703_230708`
- state: `complete`
- frames: `2`
- dirty frames: none
- restore bbox method: `tight_object`
- max restore bbox delta: approximately `4.8e-7`
- raw bbox diagnostic still reproduced the bad X/Y delta of approximately
  `3675.62`, proving the old cached bbox path was the bug

Full Pearson CanvasDirector acceptance also passed:

- run root: `C:\Users\bring\AppData\Local\Rook\rookvision_director\canvas_director_tight_bbox_acceptance_20260703_2318`
- project root: `C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2`
- GH document: `animation test_smoke-01.gh`
- spec id: `pearson_smoke_tight_bbox_20260703_2309`
- state: `complete`
- frame evidence records: `240`
- frame PNGs: `240`
- dirty frames: none
- failed frames: none
- restore bbox method counts: `tight_object: 240`
- max restore bbox delta: `4.793328116647899e-7`
- max raw bbox diagnostic delta: `3675.6218127947213`
- video manifest state: `complete`
- video: `C:\Users\bring\AppData\Local\Rook\rookvision_director\canvas_director_tight_bbox_acceptance_20260703_2318\videos\preview.mp4`
