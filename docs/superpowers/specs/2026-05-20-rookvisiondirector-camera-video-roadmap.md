# RookVisionDirector Camera And Video Roadmap

Date: 2026-05-20

Status: approved roadmap, pre-implementation planning

## Purpose

RookVisionDirector slice 1 proved the deterministic frame spine: Python can
orchestrate a run, RookNative can capture each frame transactionally, and the run
folder can preserve manifest, status, frames, and evidence.

The next direction is to make camera movement and animation output first-class
without weakening that spine. A user should eventually be able to say:

```text
Here is a curve path and a focus point.
Move the camera along the path and keep it focused on the point.
Render the frames and package them into a video.
```

This roadmap defines the path from the current slice to that workflow.

## Point A

Current Director behavior is orchestrated by `mcp_server/src/rook/director.py`.
Python owns run orchestration, object-state resolution, radial object motion,
manifest/status/evidence writes, and calls to native `/director/frame-capture`.
Phase 1 extracted camera request validation, keyframe resolution, and camera
interpolation into `mcp_server/src/rook/camera_planner.py`.

RookNative owns the atomic per-frame Rhino transaction:

- validate source object state;
- snapshot objects and active model viewport;
- apply per-frame object transforms;
- apply explicit camera and display state;
- capture a PNG;
- restore objects and viewport/display;
- return structured evidence.

The current camera input is:

```json
{
  "camera_keyframes": [
    { "frame_index": 1, "source": { "kind": "active_view" } },
    { "frame_index": 30, "source": { "kind": "named_view", "name": "Shot_30" } }
  ]
}
```

This is useful, and the extracted camera planner now gives it a focused Python
contract. The remaining gap is timeline semantics: FPS, duration, and endpoint
mapping are still implicit in frame indexes rather than first-class authoring
inputs.

## Point B

RookVisionDirector should support multiple camera-planning strategies that all
produce the same explicit per-frame camera state consumed by
`/director/frame-capture`.

The central contract is:

```text
camera request + frame_count + resolution
  -> resolved per-frame camera list + provenance
```

Native frame capture should not need to know whether a camera came from named
views, active views, a curve-follow strategy, an orbit tool, or a future shot
planner. It should keep receiving one explicit camera per frame.

## Architecture Boundaries

Python owns:

- camera request validation and planning;
- run-level authoring and packaging;
- object motion planning;
- frame manifest/status/evidence;
- video assembly orchestration;
- future artifact/RookVision publishing decisions.

RookNative owns:

- Rhino document/object/curve evaluation primitives;
- active/named model-view resolution;
- per-frame capture transactions;
- source-state and restore verification.

Managed C# remains out of the Director core unless a later publishing phase
explicitly uses the existing artifact or video subsystem.

## Backward Compatibility

Existing slice 1 requests must remain valid:

```json
{
  "camera_keyframes": [
    { "frame_index": 1, "source": { "kind": "active_view" } }
  ]
}
```

That shape is shorthand for the future explicit form:

```json
{
  "camera": {
    "strategy": "keyframes",
    "keyframes": [
      { "frame_index": 1, "source": { "kind": "active_view" } }
    ]
  }
}
```

For a current slice 1 request, `manifest.frames[*].camera` must remain
byte-shape compatible except for additive provenance fields elsewhere in the
manifest. This keeps the extraction honest and avoids a schema migration before
there is a second strategy.

## Camera State Decisions

### Optics Authority

Camera state can currently contain both `lens_length` and `fov_degrees`.
RookNative applies lens length first and falls back to FOV only when lens length
is unavailable.

The camera planning contract follows the same rule:

- `lens_length` is the primary optics authority when present on both endpoints;
- `fov_degrees` is readback/provenance in that case;
- if lens length is unavailable, `fov_degrees` may be the authority;
- planners must not independently interpolate authoritative lens and
  authoritative FOV as if both control the camera.

### Direction Validation

Every resolved camera frame must have a non-degenerate view direction:

```text
target - location
```

The planner must validate the interpolated location-to-target direction, not
only the up vector. Linear interpolation can create invalid camera states even
when the source keyframes are individually valid.

### Up Vector Validation

The planner normalizes the interpolated up vector and rejects degenerate up
vectors. Later curve-follow work may add transported-frame behavior, but the
first contract should preserve the current world-up-compatible behavior.

### Aspect Authority

Aspect defaults to the requested output resolution:

```text
aspect = width / height
```

A deliberate camera aspect override may be supported, but source viewport aspect
must not silently override output resolution. This matters before video output
because frame dimensions, camera frustum, and encoded video dimensions should
agree by default.

## Roadmap

### Phase 1: Camera Planning Contract Extraction (Complete)

The current keyframe camera logic has been extracted into a focused Python
planning module.

Deliverable:

```text
camera request + frame_count + resolution
  -> resolved per-frame camera list + provenance
```

The phase preserved current behavior while making the camera planner an
independent, test-covered contract. It did not add curve sampling, FFmpeg,
artifact publishing, or native frame-capture changes.

Acceptance:

- existing `camera_keyframes` requests still work;
- explicit `camera.strategy == "keyframes"` works;
- resolved per-frame camera dictionaries are compatible with slice 1 output;
- optics authority is deterministic;
- interpolated direction and up vector are validated;
- default aspect comes from output resolution;
- manifest provenance records the camera planning strategy and source keyframes.

### Phase 1.5: Timeline Authoring Contract

Add a Python-only timeline resolver before native curve sampling or video
assembly. The frame run should know shot timing before any frame files exist;
FFmpeg later consumes that metadata rather than becoming the first owner of FPS.

Legacy requests without `timeline` remain frame-count based:

```json
{
  "frame_count": 120,
  "camera_keyframes": [
    { "frame_index": 1, "source": { "kind": "active_view" } }
  ]
}
```

Timeline requests derive canonical frame count from duration and FPS:

```json
{
  "timeline": {
    "fps": 24,
    "duration_seconds": 5.0
  },
  "camera": {
    "strategy": "keyframes",
    "keyframes": [
      { "time": 0.0, "source": { "kind": "active_view" } },
      { "time": 5.0, "source": { "kind": "named_view", "name": "End" } }
    ]
  }
}
```

The canonical contract is:

```text
derived_frame_count = round(duration_seconds * fps)
frame_time(frame_index) = (frame_index - 1) / fps
normalized_time = time / duration_seconds
frame_index = round(1 + normalized_time * (frame_count - 1))
```

For implementation, Director's timeline `round` is deterministic nonnegative
half-up rounding, equivalent to `floor(value + 0.5)`. This avoids
runtime-specific banker's rounding at midpoint frame positions.

Camera keyframes may specify exactly one timing field:

- `frame_index`: positive integral value in `1..frame_count`;
- `time`: finite seconds in `0..duration_seconds`;
- `at`: finite normalized position in `0..1`.

Timeline normalization happens before `camera_planner` runs. The planner still
receives keyframes with canonical `frame_index` values and remains focused on
camera state, interpolation, and provenance.

If the request contains explicit top-level `camera`, timeline normalization
normalizes that active shape and preserves the existing rule that legacy
`camera_keyframes` are ignored by planning. If `camera` is absent, legacy
`camera_keyframes` are normalized.

The manifest records canonical timing:

```json
{
  "frame_count": 120,
  "timeline": {
    "source": "timeline",
    "fps": 24,
    "duration_seconds": 5.0,
    "frame_count": 120
  }
}
```

When no `timeline` is present, the manifest records:

```json
{
  "frame_count": 120,
  "timeline": {
    "source": "frame_count",
    "fps": null,
    "duration_seconds": null,
    "frame_count": 120
  }
}
```

Acceptance:

- existing frame-count requests still work;
- `timeline.fps` is a positive integral value for this slice and normalizes to
  an integer;
- `timeline.duration_seconds` is positive;
- `derived_frame_count >= 1`;
- top-level `frame_count`, when present with `timeline`, equals the derived
  count;
- camera keyframes using `frame_index`, `time`, or `at` normalize to the same
  canonical frame-index contract;
- MCP `rhino_director_run` accepts timeline-only requests without requiring
  top-level `frame_count`;
- endpoint mapping is exact: `time=0` and `at=0` map to frame `1`, while
  `time=duration_seconds` and `at=1` map to `frame_count`;
- manifest provenance records the timing source and canonical values.

### Phase 2: Native Curve Sampling Primitive

Add a read-only native route for curve sampling. A likely shape is:

```text
POST /director/curve-samples
```

Input:

```json
{
  "curve_id": "00000000-0000-0000-0000-000000000000",
  "frame_count": 120,
  "sampling": {
    "mode": "normalized_parameter",
    "start": 0.0,
    "end": 1.0
  }
}
```

Output:

```json
{
  "schema_version": 1,
  "curve_id": "00000000-0000-0000-0000-000000000000",
  "samples": [
    {
      "frame_index": 1,
      "parameter": 0.0,
      "point": [0.0, 0.0, 0.0],
      "tangent": [1.0, 0.0, 0.0]
    }
  ],
  "provenance": {
    "sampling_mode": "normalized_parameter",
    "validation_strength": "curve_parameter_sampled"
  }
}
```

The route must not overclaim arc-length sampling. If native later implements true
arc-length sampling, the response should record that as a distinct sampling mode
and provenance value.

This phase consumes the canonical `frame_count` produced by Phase 1.5. It does
not derive frame count from FPS or duration itself.

### Phase 3: Curve-Follow Target Camera Strategy

Add a Python camera strategy:

```json
{
  "camera": {
    "strategy": "curve_follow_target",
    "curve_id": "00000000-0000-0000-0000-000000000000",
    "target": [10.0, 5.0, 3.0],
    "up": [0.0, 0.0, 1.0],
    "sampling": {
      "mode": "normalized_parameter",
      "start": 0.0,
      "end": 1.0
    },
    "lens_length": 35.0
  }
}
```

The strategy calls native curve sampling, turns samples into camera locations,
uses the fixed point as target, validates each resolved camera, and emits the
same per-frame camera objects used by current keyframe planning.

### Phase 4: MP4 Video Assembly

Add a post-processing stage that can stitch completed PNG frames into an MP4.
This phase should not change frame-run status semantics.
FPS is read from the run timeline metadata when available; MP4 assembly must not
invent shot timing after frames have already been resolved.

Frame run status remains in `status.json`:

```json
{
  "state": "complete"
}
```

Video assembly status lives separately in `video_manifest.json`:

```json
{
  "schema_version": 1,
  "state": "complete",
  "format": "mp4",
  "fps": 24,
  "input_pattern": "frames/frame_%04d.png",
  "output_path": "videos/preview.mp4",
  "started_at": "2026-05-20T00:00:00Z",
  "completed_at": "2026-05-20T00:00:03Z"
}
```

The first target is MP4 only. WebM or codec matrices should wait for a concrete
publishing surface that needs them.

The FFmpeg command should include `-start_number 1` because Director frame names
start at `frame_0001.png`:

```powershell
ffmpeg -y `
  -framerate 24 `
  -start_number 1 `
  -i frames/frame_%04d.png `
  -c:v libx264 `
  -pix_fmt yuv420p `
  videos/preview.mp4
```

Video assembly should only run automatically for frame runs with
`status.state == "complete"`. Failed or unsafe frame runs may be stitched only by
an explicit diagnostic command.

### Phase 5: Artifact And RookVision Publishing

After the local frame/video contract stabilizes, add an optional publishing
layer:

- register `videos/preview.mp4` with the existing artifact store;
- expose completed Director videos through an existing UI or gallery surface;
- hand selected frames or videos to RookVision generation workflows.

This phase should consume completed Director outputs. It should not become a
dependency of camera planning, native frame capture, or local MP4 assembly.

## Non-Goals For The First Follow-Up Slice

The first follow-up slice does not implement:

- native curve sampling;
- `curve_follow_target`;
- FFmpeg invocation;
- MP4 output;
- artifact store publication;
- UI/gallery changes;
- native `/director/frame-capture` changes.

The first follow-up slice after camera planning is the timeline contract. It
exists to make later curve sampling, curve-follow, easing, holds, variable
pacing, and MP4 assembly consume one canonical timing model.

## Self-Review

- No phase depends on artifact publishing before deterministic local outputs
  exist.
- Native frame capture remains the atomic Rhino mutation boundary.
- Phase 1 is complete: camera planning now lives in `camera_planner.py`.
- Existing slice 1 requests remain valid.
- Timeline/FPS/duration semantics are now separated from MP4 assembly and run
  before future camera strategies.
- MP4 output is explicitly separated from frame-run status.
- Curve sampling provenance avoids claiming arc-length behavior before native
  implements it.
