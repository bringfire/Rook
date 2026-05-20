# RookVisionDirector Slice 1 Design

Date: 2026-05-19

Status: approved design, pre-implementation planning

## Purpose

RookVisionDirector explores the space between deterministic Rhino control and
probabilistic AI video/image generation. The first slice must prove the
deterministic spine of a director workflow, not just viewport screenshots.

Given a known Rhino scene, Rook must produce a sequential RGB frame set and
durable run records:

```text
rookvision_director/<run_id>/
  manifest.json
  status.json
  frames/
    frame_0001.png
    frame_0002.png
  logs/
    frame_evidence.jsonl
```

Each frame must be reproducible from explicit resolved camera state, display
settings, output resolution, object IDs, and per-object transform deltas stored
in the manifest.

## Design Center

Slice 1 uses a Python-first director with a native per-frame document
transaction.

Python owns run-level authoring and orchestration:

- target object resolution;
- explode motion strategy authoring;
- camera keyframe resolution and interpolation;
- output folder creation under a Rook-controlled or configured director output
  root;
- `manifest.json`, `status.json`, and `logs/frame_evidence.jsonl`;
- progress, cancellation, and status transitions;
- future RookVision handoff.

Native owns the dangerous Rhino operation:

- resolve the active Rhino viewport at the start of each frame transaction;
- snapshot top-level object transform/location state needed for slice 1
  restoration;
- snapshot the camera/projection and viewport display mode needed to restore
  that same viewport;
- apply resolved per-frame object transform deltas;
- apply explicit camera and display state;
- capture a fixed-resolution PNG;
- explicitly restore objects and viewport;
- verify restoration where feasible;
- return structured evidence.

Python must pass resolved per-frame object transforms and resolved per-frame
camera state. Native must not compute explode motion, interpolate cameras, or
infer creative intent.

Every native frame call must leave the document and active viewport as it found
them, regardless of success or failure. Python can stop, retry, or cancel
between frames because no frame may leave the model posed.

Native frame execution also validates that each referenced object still matches
the source state recorded for the run before applying the frame delta. This
prevents source-relative transforms from being applied to a model that changed
between frames. If the available source-state fields are too weak to prove that
the transform-relevant state is unchanged, native must record degraded
validation in evidence.

## Current Architecture Fit

This design follows the live Rook architecture:

- `RookNative` remains the sole HTTP surface for Rhino document work.
- The Python MCP/server layer is the right home for tool orchestration,
  manifests, status, cancellation, and future skills.
- Managed C# stays out of slice 1 unless a specific existing API is required.
- Existing RookVision artifact-store publication is deferred until the plain
  file contract stabilizes.

The implementation plan must begin with a route and capability inventory. In
particular, inspect existing `/viewport`, `/views`, `/display-mode`,
`/transform`, object metadata, selection, and bounding-box patterns before
adding new native code. Do not design against imagined Rhino SDK APIs or
invented routes.

## Scope

Slice 1 includes:

- top-level Rhino document objects as moving units;
- active-viewport-based capture, resolved per native frame transaction;
- explicit per-frame camera execution input;
- one default explode motion strategy, `radial_bbox_center`;
- fixed-resolution RGB PNG output;
- durable manifest, status, and evidence logs;
- state-integrity behavior after success, failure, and cancellation.

Slice 1 excludes:

- block-definition mutation;
- Grasshopper objects and the Grasshopper NLE;
- layout/detail views;
- true depth passes;
- edge/cartoon passes;
- RookVision artifact-store ingestion;
- RookVision AI generation handoff;
- staged duplicate inspection/export mode;
- non-active viewport targeting.

## Motion Authoring Strategy

The general concept is an explode motion authoring strategy. Slice 1 implements
one default strategy:

```json
{
  "motion": {
    "strategy": "radial_bbox_center",
    "parameters": {
      "distance": 10.0,
      "per_object_scale": {}
    },
    "warnings": []
  }
}
```

`radial_bbox_center` computes a vector from the selection world-aligned
bounding-box center to each object's world-aligned bounding-box center:

```text
if frame_count == 1:
  t = 0
else:
  t = (frame_index - 1) / (frame_count - 1)

translation = direction * distance * per_object_scale * t
```

For single-frame runs, the run captures the un-exploded state.

Edge cases are explicit:

- if an object center equals the selection center, use a fallback direction and
  record a warning;
- if multiple objects have near-identical centers, record an overlap warning;
- block instances are treated only as top-level moving units in slice 1;
- world-aligned bounding boxes are accepted and recorded as slice 1 behavior.

Future strategies must fit the same resolved output contract:

- `explicit_vectors`;
- `captured_start_end`;
- `world_axis`;
- `surface_normal`;
- `semantic_group`;
- `keyframed_pose`.

Motion strategies are authoring logic. Native receives only resolved per-frame
transform deltas.

## Camera Authoring And Execution

Camera keyframes are authoring inputs. Per-frame camera states are execution
inputs.

Slice 1 supports two camera authoring paths:

- capture active view as keyframe;
- resolve named view as keyframe.

Both paths produce the same explicit camera schema in the manifest. After
resolution, a named view is only provenance metadata; execution must not depend
on named views.

Camera execution input uses `location + target + up` as the authoritative form:

```json
{
  "projection": "perspective",
  "location": [10.0, -10.0, 8.0],
  "target": [0.0, 0.0, 0.0],
  "up": [0.0, 0.0, 1.0],
  "lens_length": 35.0,
  "fov_degrees": null,
  "parallel_scale": null,
  "near_clip": null,
  "far_clip": null,
  "aspect": 1.7778
}
```

`direction` may appear in evidence as a derived value, but is not an
independent execution input in slice 1.

Projection-specific fields are required where applicable:

- perspective cameras require a reliably resolved lens length or FOV;
- parallel cameras require a reliably resolved parallel scale/frustum-height
  value, plus aspect;
- clipping fields are recorded when available and omitted or null only when the
  inventory proves they are not needed for faithful slice 1 execution.

If Phase 0 cannot verify the Rhino SDK calls needed to resolve and apply
parallel camera scale/frustum data, slice 1 must explicitly restrict execution
to perspective cameras until a later slice adds parallel support. It must not
silently execute named parallel views with incomplete camera data.

Python linearly interpolates per-frame `location`, `target`, and lens/FOV
fields. `up` is interpolated only with normalization and degeneracy checks.
Roll flips or near-zero up vectors must warn or fail rather than silently
producing invalid camera states.

Camera interpolation upgrades are deferred: easing, spherical/quaternion or
arcball paths, focus/framing behavior, clipping strategy, and roll control.

## Contracts

Both the manifest and native frame instruction include:

```json
{
  "schema_version": 1,
  "director_version": "slice1"
}
```

Frame indexes are one-based, matching filenames such as `frame_0001.png`.

The Python authoring request may include explicit object IDs or current
selection, frame count, resolution, display mode, camera keyframes, motion
strategy parameters, and optional output root. If `output_root` is absent,
Python resolves a Rook-controlled default output root. If `output_root` is
present, Python resolves it only through configured or registered director
output roots. The resolved absolute run folder path is recorded in the
manifest.

Native does not trust `output_root`, `run_root`, `output_path`, or manifest
metadata as an allowlist source of truth. The native route must check
canonicalized paths against its own native-side configured or compiled
director-output allowlist before creating, replacing, or moving any file.

`manifest.json` is the source of resolved intent. It records:

- schema and director version;
- run ID;
- resolved absolute output folder;
- resolved allowed output root;
- document identity when available;
- document units when available;
- source object IDs, transform-relevant source-state records, and optional
  display-name/type/layer provenance;
- motion strategy, parameters, and warnings;
- camera keyframe provenance;
- resolved per-frame camera states;
- resolved per-object per-frame transform deltas;
- display and capture settings;
- expected frame output paths;
- slice 1 exclusions.

`status.json` records mutable run state and final summary. It must be written
with temp-then-replace behavior.

`logs/frame_evidence.jsonl` is append-only observed execution.

Native frame instruction shape:

```json
{
  "schema_version": 1,
  "director_version": "slice1",
  "run_id": "run-id",
  "frame_index": 1,
  "frame_id": "frame_0001",
  "run_root": "C:/.../rookvision_director/run-id",
  "output_path": "C:/.../frames/frame_0001.png",
  "resolution": { "width": 1280, "height": 720 },
  "display": { "mode": "Rendered" },
  "camera": {
    "projection": "perspective",
    "location": [10.0, -10.0, 8.0],
    "target": [0.0, 0.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "lens_length": 35.0,
    "fov_degrees": null,
    "parallel_scale": null,
    "near_clip": null,
    "far_clip": null,
    "aspect": 1.7778
  },
  "object_transforms": [
    {
      "object_id": "object-guid",
      "source_state": {
        "bbox_min": [0.0, 0.0, 0.0],
        "bbox_max": [1.0, 1.0, 1.0],
        "validation_strength": "bbox_only",
        "state_hash": null
      },
      "transform": [
        [1, 0, 0, 2.5],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
      ]
    }
  ]
}
```

`object_transforms[].transform` is a delta from the object's pre-frame source
state, computed by Python for that frame. `source_state` carries the
transform-relevant source pose observed when the manifest was resolved. Native
checks the current object against this source state before mutation, snapshots
current state, applies the delta, captures, and restores the snapshot. Because
native restores after every frame, frame deltas are source-relative, not
accumulated from prior frames.

Source-state validation strength is explicit. A stronger transform-relevant
state token or hash must be used if Phase 0 identifies a reliable one.
`bbox_only` validation is allowed for slice 1 only as a degraded check: it can
detect many stale-source cases but cannot prove all transform-relevant state is
unchanged. Native evidence must record the validation strength used for each
object and must not report bbox-only validation as full source-state proof.

Native validates before mutation:

- schema/version are supported;
- frame fields are valid and one-based;
- resolution is within supported bounds;
- `run_root` and `output_path` canonicalize under a native-side
  Rook-controlled or configured director output root;
- `output_path` canonicalizes as a descendant of `run_root`;
- output directory exists or can be created inside the allowed run root;
- display mode is supported;
- camera vectors and projection fields are valid and nondegenerate;
- all object IDs resolve;
- objects are eligible top-level document objects;
- current object state matches the supplied source state within tolerance;
- transform matrices parse as valid `ON_Xform` deltas.

Validation failure must not mutate the document or viewport.

Native evidence includes:

- frame ID and index;
- output path;
- capture dimensions;
- display requested and resolved;
- applied camera echo plus derived direction;
- object counts requested/applied/restored;
- source-state validation result;
- affected object IDs on failure;
- viewport restore status;
- restoration verification status;
- `dirty_partial_state`;
- warnings;
- structured error code and message;
- timings;
- `overwrote_existing`.

## Native Frame Transaction

`POST /director/frame-capture` is a guarded per-frame document transaction.

Pre-mutation validation happens first. If any validation fails, the route
returns a structured error before object or viewport mutation.

Execution uses scoped guards:

- object pose guard captures restorable transform/location state for each
  referenced top-level object;
- viewport guard captures the active viewport resolved at transaction start,
  plus camera/projection and viewport display mode needed to restore it;
- output guard avoids stale success.

Guards expose explicit `restore()` methods so the route can record restoration
evidence. Guard destructors perform best-effort restore only as a last line of
defense.

The route applies object deltas using existing document transform/redraw
patterns, applies explicit camera and viewport display mode, captures a PNG,
explicitly restores objects and viewport, verifies restoration within
tolerance, and returns evidence.

Output handling must canonicalize `run_root` and `output_path`, reject writes
outside the native-side allowed director output roots, write to a temp file in
the target directory, verify it exists and has nonzero size, then replace or
move it to `output_path`. Evidence records whether an existing output file was
overwritten.

Slice 1 verifies transform/location and viewport camera/display restoration
pragmatically. It does not claim full geometry, material, user-data, layer, or
global display-setting rollback.

If capture fails after mutation, native still restores and returns failure
evidence. If explicit restore fails or verification cannot prove restoration,
the response includes `dirty_partial_state: true` and high-severity structured
error data.

## Python Director

Python may call existing or new read-only native routes for:

- current selection;
- object bounds and metadata;
- document units;
- active view camera state;
- named view camera state.

Python must not mutate Rhino outside the native frame transaction route.

Python validates before manifest creation:

- `frame_count >= 1`;
- positive resolution;
- nonnegative motion distance;
- at least one selected or resolved object;
- per-object scales are valid;
- camera keyframes are within `1..frame_count`;
- keyframe sources resolve;
- output root is usable and resolves under a Rook-controlled or configured
  director output root;
- motion strategy is supported.

Python creates the run folder, writes `manifest.json`, writes initial
`status.json`, calls native once per frame, appends each evidence response to
`logs/frame_evidence.jsonl`, and stops cleanly between frames on cancellation.
The manifest stores source-state records for each target object, and Python
passes those records to every native frame instruction so native can reject
stale source poses before mutation.

## Run States And Recovery

Run states distinguish normal failure from unsafe failure:

- `complete`: every frame succeeded, every output exists, and evidence exists
  for every frame.
- `failed`: a frame failed, but native restored successfully and evidence was
  written.
- `cancelled`: cancellation was requested between frames.
- `evidence_failed`: frame execution occurred but Python could not persist
  evidence; no further frames may run.
- `unsafe_failed`: native reported `dirty_partial_state`, restore failed, or
  restoration could not be verified.

If any frame evidence reports `dirty_partial_state`, Python must stop
immediately, mark the run `unsafe_failed`, perform no retries, and tell the
agent/user not to continue automated frame execution until the document is
inspected or reverted. Evidence must identify affected object IDs and viewport
restore status.

Partial runs are inspectable. They are rerunnable from the manifest only if the
source document is clean or has been restored. Replayability is suspended for
`unsafe_failed`.

## Testing And Phases

### Phase 0: Route And Capability Inventory

Confirm existing selection, object metadata/bounds, view/camera, display mode,
transform, redraw, and viewport capture patterns. Identify the minimum
read-only native additions needed. This phase exists to prevent imagined Rhino
SDK usage from entering implementation.

### Phase 1: Native Frame Transaction With Explicit Camera Input

Add `POST /director/frame-capture`.

Use native unit/integration tests where possible for parsing, schema validation,
output-path handling, and error shaping. Use live Rhino smoke tests where
document mutation, capture, camera/display application, and restoration require
Rhino.

Test:

- pre-mutation validation;
- output-root allowlist and path traversal rejection;
- temp/replace output behavior;
- source-state mismatch rejection before mutation;
- object restore on success;
- object restore on induced capture failure;
- viewport restore;
- `dirty_partial_state` reporting.

### Phase 2: Python Director Manifest Runner

Add Python service/tool support for run folders, object metadata resolution,
`motion.strategy = "radial_bbox_center"`, active/named view keyframe
resolution, per-frame expansion, manifest/status/evidence writing, and
per-frame native calls.

Test authoring failures before manifest creation and status transitions:
`complete`, `failed`, `cancelled`, `evidence_failed`, and `unsafe_failed`.
Also test output-root resolution, manifest source-state recording, stale-source
native evidence handling, and projection-specific camera validation.

### Phase 3: End-To-End Slice Proof

Given a known Rhino fixture scene, produce a 3 to 5 frame sequence and verify:

- `manifest.json`, `status.json`, and `logs/frame_evidence.jsonl` exist;
- `frames/frame_0001.png ... frame_000N.png` exist at fixed resolution;
- every frame has evidence;
- object and viewport state are restored after success, failure, and
  cancellation;
- manifest records units, object display names when available, camera
  provenance, resolved per-frame cameras, source-state records, and resolved
  per-frame transform deltas.

Visual checks in Phase 3 are smoke checks, not formal visual regression tests:

- captures are nonblank;
- frame 1 is un-exploded;
- final frame is visibly exploded;
- framing changes when two camera keyframes are used.

## Deferred Work

- True depth pass.
- Edge/cartoon pass.
- RookVision artifact-store ingestion.
- RookVision AI generation handoff.
- Staged duplicate inspection/export mode.
- Richer motion strategies.
- Non-active viewport targeting.
- Block-definition animation.
- Grasshopper and NLE integration.
- Camera interpolation upgrades.

## Senior Reviewer Focus

The reviewer evaluates:

- Does Python own intent and run orchestration while native owns only the
  atomic Rhino transaction?
- Are per-frame object transforms and cameras fully resolved before native
  execution?
- Does native leave the document and active viewport as it found them after
  every frame call?
- Are failed and unsafe runs clearly distinguished?
- Does native reject frame output paths outside allowed director roots?
- Does native reject source-state mismatches before applying source-relative
  deltas?
- Are parallel camera states either fully represented or explicitly rejected?
- Does the manifest describe resolved intent while evidence describes observed
  execution?
- Are slice 1 exclusions honest enough to keep the workflow testable?

## Self-Review

- No placeholders remain.
- Scope is limited to slice 1 deterministic RGB frame capture.
- Radial motion is named as the first strategy, not the conceptual limit.
- Transform delta semantics are explicit and source-relative.
- Camera execution input has one authority: `location + target + up`.
- Projection-specific camera fields now cover perspective and parallel
  execution, with explicit restriction if parallel cannot be verified.
- Native output paths are constrained to allowed director roots.
- Source-state validation protects source-relative transform semantics.
- Per-frame native transaction boundaries are explicit.
- Failed and unsafe run states are distinct.
- Replayability is conditional on a clean/restored source document.
- RookVision artifact and AI-generation handoff are deferred.
