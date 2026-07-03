# Director Restore Hardening Design

Date: 2026-07-03
Status: ready for user review
Branch: `codex/rookvision-canvas-director`
Planned commit scope: `fix(director): harden bbox restore verification for large block instances`

## Purpose

The Pearson V2 CanvasDirector live smoke proved that extraction, project spec
persistence, and Director track compilation work. The failure moved into the
existing native Director capture safety path:

```text
extract -> spec -> compile -> run_compiled_track -> /director/frame-capture
```

Native frame capture stopped after frame 2 with `unsafe_failed`. Evidence showed
that the frame image was written and the viewport/display restored, but object
restore verification failed for a top-level `InstanceReference` because the
post-inverse bbox did not match the baked source bbox.

This design hardens native Director restore verification so the CanvasDirector
acceptance path can complete without weakening dirty-state safety.

## Branch Guidance

This work stays on `codex/rookvision-canvas-director` for now because it is the
native Director hardening needed to complete CanvasDirector acceptance. The code
touch should remain limited to:

- `src/RookNative/Handlers/DirectorFrame.*`
- frame-capture/replay restore evidence behavior that uses those helpers;
- focused native source/live tests and existing Python artifact behavior tests.

Do not change CanvasDirector extraction, authoring spec persistence, compiler
shape, or Python `dirty_partial_state` stop behavior for this task.

If evidence shows real cumulative drift or the fix grows into object replacement,
snapshot restore, undo semantics, or broader Director runtime semantics, stop
and split a child branch such as `codex/director-restore-hardening`.

## Core Invariant

**Instrumentation first, tolerance second.**

The observed rounded readback delta was approximately `0.000067`, which is below
the current apparent `1e-4` tolerance. That means the raw native delta may be
larger than the later readback suggests, the mismatch may be on a different bbox
coordinate, or restore verification may be observing a different object state
than a later `/director/object-states` call.

The implementation must first record native restore comparison evidence. Only
after that evidence is available should it apply the narrowest bounded tolerance
policy justified by the raw native data. If the evidence shows real drift, the
implementation must not hide it with tolerance; it must stop and escalate to a
stronger snapshot/original-state restore design.

## Scope

In scope:

- add per-object restore comparison evidence on both success and failure;
- replace restore-verification magic numbers with named bounded policies;
- keep source-state validation and restore verification as separate gates;
- add synthetic live coverage for large-coordinate block instances;
- rerun the Pearson V2 smoke through video assembly after the native fix.

Out of scope:

- CanvasDirector extraction or schema changes;
- Python run behavior changes;
- assembling video after any `unsafe_failed` run;
- changing `absolute_from_source` track semantics;
- object replacement, cloned object snapshots, or original-state restore
  semantics unless evidence proves tolerance cannot safely solve the issue.

## Two Restore Gates

Director currently relies on bbox-only source validation for slice 1. This work
must keep two gates distinct:

1. Source-state validation gate:
   "Is the document currently in the baked source pose before applying this
   frame?"
2. Restore verification gate:
   "After applying and reversing this frame transform, did the object return to
   the source pose?"

The Pearson failure is in the restore verification gate. The gates may share a
bbox-delta helper, but they must have separate named constants or policies and
separate evidence wording.

## Restore Evidence

`DirectorObjectPoseGuard::Restore()` should record restore comparison evidence
for every applied object, on both success and failure. Some hard-failure paths
cannot produce a valid restored object or restored bbox, so the evidence contract
must distinguish object-level restore status from bbox-comparison availability.

Every per-object detail should include:

- `object_id`
- `source_object_type`, when known, otherwise `null`
- `restored_object_type`, when available, otherwise `null`
- `applied`
- `restored`
- `validation_strength`
- `bbox_comparison_available`
- `bbox_tolerance`
- `bbox_tolerance_policy` or `bbox_tolerance_reason`
- `restore_error` when restore fails

When `bbox_comparison_available:true`, the detail should also include:

- `source_bbox`
- `restored_bbox`
- `bbox_delta_min`
- `bbox_delta_max`
- `bbox_max_delta`

When `bbox_comparison_available:false`, the comparison fields may be `null` or
omitted, but the detail must include a clear reason, either in `restore_error`
or a dedicated comparison-unavailable field. This applies to failed inverse
transform, missing object, deleted object, and invalid restored bbox paths.

The bbox fields should reflect what native compared at restore time, not a later
Python readback. Deltas should be per-axis absolute differences between the
restored bbox and source bbox, with `bbox_max_delta` equal to the maximum
coordinate delta across min and max corners.

## Tolerance Policy

The restore verification tolerance must be named, explicit, bounded, and
recorded in evidence. It must not be an unbounded relative tolerance.

Recommended policy shape:

```text
restore_tolerance = min(
  absolute_cap,
  serialization_floor + bounded_model_scale_allowance
)
```

The exact constants should be chosen during implementation from native evidence
and existing document tolerances. The policy must have a fixed absolute ceiling
so huge site coordinates do not weaken dirty-state detection without bound.

Source-state validation may continue to use its own named policy. If source and
restore tolerances share an implementation helper, the public names and evidence
must still distinguish the two gates.

## Hard Failures

These conditions remain hard failures regardless of bbox tolerance:

- inverse transform application fails;
- object is missing after restore;
- object is deleted after restore;
- restored bbox is invalid;
- source bbox is invalid.

Only a valid restored bbox comparison can be tolerated. If the bbox delta is
above the restore policy tolerance, native must keep reporting `restored:false`
and `dirty_partial_state:true`.

## Implementation Sequence

The implementation must proceed in two gated steps:

1. Instrumentation-only patch:
   add restore evidence fields and comparison availability without changing the
   restore acceptance threshold. Deploy and run a targeted live capture, either
   the Pearson failing smoke or a fresh synthetic large-coordinate instance
   fixture, to collect raw native source/restored bbox deltas.
2. Bounded tolerance patch:
   choose the narrowest named restore verification tolerance justified by that
   evidence, with a fixed absolute cap. Record the policy and numeric tolerance
   in evidence.

If step 1 shows real cumulative drift, missing restore, or object-state mutation
that cannot be explained as bounded bbox precision noise, stop before step 2 and
escalate to a stronger snapshot/original-state restore design.

## Python Behavior

Python behavior remains unchanged.

`director.run_compiled_track()` and `director.run_director()` must continue to
stop on any native frame evidence with `dirty_partial_state:true`. They must not
continue capture, assemble video, or reinterpret `unsafe_failed`.

This preserves the Director runtime truth model: native owns document mutation
safety, and Python refuses to proceed when native reports dirty partial state.

## Testing Strategy

### Native Source Contract Tests

Add source-level assertions that:

- source-state validation and restore verification use separate named policies;
- restore evidence includes comparison availability, tolerance,
  tolerance policy/reason, source/restored object type fields, and, when
  comparison is available, source/restored bboxes, deltas, and max delta;
- hard failure branches for transform failure, missing/deleted object, and
  invalid bbox remain ahead of any tolerance acceptance path.

These tests catch contract regression without requiring Rhino.

### Replay Verification

`DirectorObjectPoseGuard` is shared by frame capture and native replay, so the
verification set must cover replay dirty-state semantics as well as capture.

At minimum, run the existing replay native/source tests that assert shared helper
usage, restore ordering, and hard-failure handling. If implementation changes
the helper's public evidence shape or hard-failure ordering, add focused replay
source or live coverage so replay cannot silently start tolerating real dirty
state.

### Python Artifact Tests

Keep existing Python behavior tests green. In particular:

- `dirty_partial_state:true` still stops the run;
- unsafe runs do not proceed to video assembly;
- compiled-track run artifacts still write manifest, status, frame evidence,
  run-local authoring spec, and provenance as before.

No CanvasDirector tests should require changes for this hardening slice.

### Live Rhino Regression

Prefer a synthetic fixture over the Pearson model for automated regression.
Create a fresh large-coordinate block instance or instance reference, capture
repeated frames with small sub-unit transforms, and assert:

- every frame reports `dirty_partial_state:false`;
- every frame records the restore evidence fields;
- final `/director/object-states` bbox is within the same restore policy
  tolerance of the original source bbox;
- exact rounded bbox equality is not required.

The repeated-frame check is load-bearing: a tolerated restore mismatch must not
hide cumulative drift.

Add a negative live/source assertion where possible so hard failures still
produce `restored:false` and `dirty_partial_state:true`.

## Acceptance Smoke

After native hardening and focused tests pass, rerun the Pearson V2 chain:

```text
extract -> spec -> compile -> run_compiled_track -> assemble_director_video
```

Acceptance requires:

- `rhino_director_canvas_extract` succeeds with `require_fresh_solve`;
- the generated `DirectorAuthoringSpec` persists under V2 `.rook`;
- compile resolves the V2 actor and camera frames without provenance warnings;
- `run_compiled_track()` completes all frames without `dirty_partial_state`;
- frame evidence contains the new restore comparison fields;
- video assembly creates `videos/preview.mp4` and `video_manifest.json`.

If native evidence shows real drift rather than a bounded restore-verification
precision issue, stop before video assembly and escalate to snapshot/original
state restore design.
