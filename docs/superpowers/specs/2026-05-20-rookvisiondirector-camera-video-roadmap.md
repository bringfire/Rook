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

Current Director behavior is centered in `mcp_server/src/rook/director.py`.
Python owns run orchestration, object-state resolution, camera keyframe
resolution, camera interpolation, radial object motion, manifest/status/evidence
writes, and calls to native `/director/frame-capture`.

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

This is useful, but the camera planning logic is embedded inside the run
orchestrator and there is no explicit contract for other camera strategies.

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

### Phase 1: Camera Planning Contract Extraction

Extract the current keyframe camera logic into a focused Python planning module.

Deliverable:

```text
camera request + frame_count + resolution
  -> resolved per-frame camera list + provenance
```

The phase preserves current behavior while making the camera planner an
independent, test-covered seam. It does not add curve sampling, FFmpeg, artifact
publishing, or native frame-capture changes.

Acceptance:

- existing `camera_keyframes` requests still work;
- explicit `camera.strategy == "keyframes"` works;
- resolved per-frame camera dictionaries are compatible with slice 1 output;
- optics authority is deterministic;
- interpolated direction and up vector are validated;
- default aspect comes from output resolution;
- manifest provenance records the camera planning strategy and source keyframes.

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

The first slice exists to make camera planning modular enough that those later
features are additive.

## Self-Review

- No phase depends on artifact publishing before deterministic local outputs
  exist.
- Native frame capture remains the atomic Rhino mutation boundary.
- The first implementation slice is limited to camera planning extraction.
- Existing slice 1 requests remain valid.
- MP4 output is explicitly separated from frame-run status.
- Curve sampling provenance avoids claiming arc-length behavior before native
  implements it.
