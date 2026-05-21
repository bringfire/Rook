# RookVisionDirector Camera And Video Roadmap

Date: 2026-05-20
Last updated: 2026-05-21

Status: active roadmap; Phases 1, 1.5, 2, and 3 are complete. The next slice is
Phase 4, the `curve_follow_target` camera strategy.

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

## Current State As Of 2026-05-21

The deterministic frame spine and local playback loop are now implemented on
`main`:

- PR #162 fixed Director frame capture validation and proved the slice 1 live
  end-to-end frame run.
- PR #164 extracted keyframe camera planning into
  `mcp_server/src/rook/camera_planner.py`.
- PR #168 added timeline authoring, canonical FPS/duration/frame-count
  resolution, and keyframe timing normalization.
- PR #170 added the native read-only `/director/curve-samples` primitive.
- PR #172 added explicit post-run MP4 assembly through
  `rhino_director_assemble_video` and native `/director/video-assemble`.

Completed Director runs can now produce PNG frame sequences, keep frame-run
status separate from video assembly status, and assemble local Windows H.264 MP4
previews through Media Foundation. The roadmap now moves to camera-path authoring
on top of that proven frame/video loop.

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
contract. Timeline semantics have also been extracted: FPS, duration, and
endpoint mapping can now produce a canonical frame count before frames are
captured.

Live testing has also proven the current combined frame spine: a completed
Director run can interpolate camera keyframes and radial object motion together
across a PNG sequence while restoring objects, viewport, and display mode after
each frame. Local video playback from a completed frame run is now complete; the
next practical gap is authoring camera movement from Rhino curve paths.

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

### Phase 1.5: Timeline Authoring Contract (Complete)

Add a Python-only timeline resolver before native curve sampling or video
assembly. The frame run should know shot timing before any frame files exist;
video assembly later consumes that metadata rather than becoming the first
owner of FPS.

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

### Phase 2: Native Curve Sampling Primitive (Complete)

Add a read-only native route for curve sampling:

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

### Phase 3: Platform-Native MP4 Video Assembly (Complete)

Add an explicit post-run assembly tool/API that turns a completed Director PNG
frame run into a local MP4 preview.

This shipped in PR #172. Python now owns post-run orchestration, frame-run
validation, FPS resolution, stale-preview semantics, and deterministic
`video_manifest.json` writing. RookNative exposes `/director/video-assemble`,
enforces Director output-root policy independently, decodes PNG frames with WIC,
and encodes H.264 MP4 with Media Foundation on Windows.

The contract is intentionally narrow:

```text
completed Director frame run + timeline fps or explicit fps override -> videos/preview.mp4 + video_manifest.json
```

This phase must not change frame-run status semantics. `status.json` remains
the status of frame capture only. Video assembly status lives separately in
`video_manifest.json`, so a completed frame run remains complete even if video
assembly fails.

The first implementation is Windows-only through Media Foundation because the
current Rook runtime is Windows-first. The design must define the matching Mac
backend contract for AVFoundation/VideoToolbox, but Mac implementation is
deferred until the Mac Rook runtime exists. This does not introduce a new
platform split; Rook already needs separate Windows and Mac native builds.

Python owns post-run orchestration, run-folder validation, and deterministic
manifest writing. The actual MP4 encoding backend must live behind a
platform-native boundary below Python, likely native C++ for the Windows Media
Foundation implementation.

The native backend must independently canonicalize `run_root`, `frames_dir`, and
`output_path` against the configured Director output root. Python validation is
not enough because the native route is a public HTTP surface that reads PNG
frames and writes MP4 output.

Video assembly must validate before encoding:

- frame run `status.json.state == "complete"`;
- `manifest.json` exists and has `timeline.fps`, or the caller supplies an
  explicit FPS override;
- frame count in the manifest matches the number of expected frame files;
- every `frames/frame_%04d.png` exists from frame 1 through frame count;
- every frame dimension matches the manifest resolution;
- v1 H.264/MP4 dimensions and frame formats are compatible with the platform
  backend, or fail with structured capability errors;
- output path resolves under the completed run folder.

`video_manifest.json` records enough information to debug both input and
backend failures:

```json
{
  "schema_version": 1,
  "state": "complete",
  "backend": "media_foundation",
  "platform": "windows",
  "format": "mp4",
  "codec": "h264",
  "container": "mp4",
  "fps": 24,
  "frame_count": 120,
  "width": 1280,
  "height": 720,
  "input_pattern": "frames/frame_%04d.png",
  "output_path": "videos/preview.mp4",
  "output_current": true,
  "preserved_previous_output": false,
  "started_at": "2026-05-21T00:00:00Z",
  "completed_at": "2026-05-21T00:00:03Z",
  "error": null
}
```

Failed manifests use the same shape with `state: "failed"` and structured
`error`. If a failed attempt preserves an older successful
`videos/preview.mp4`, the manifest must set `output_current: false` and
`preserved_previous_output: true`.

This phase explicitly does not use FFmpeg as the Director video assembly path.
The existing bundled Rook FFmpeg is a sidecar-extraction build, not an MP4
encoder, and broad FFmpeg builds with GPL encoders such as libx264 are outside
the Director product path. The slice should not add an FFmpeg fallback because
that would make release behavior ambiguous.

Video assembly is an explicit post-run operation first. A future convenience
flag on `rhino_director_run` may opt into automatic assembly only after the
post-run contract is stable.

Acceptance:

- completed frame runs assemble through `rhino_director_assemble_video`;
- `status.json` remains the frame-run status and is not rewritten by video
  assembly success or failure;
- `video_manifest.json` records success and failure state separately;
- frame count, FPS, dimensions, frame sequence completeness, and output path
  policy are validated before encoding;
- Windows Media Foundation MP4 assembly was live-smoked against a 96-frame,
  1280x720, 24 FPS Director run;
- FFmpeg, artifact publication, UI/gallery exposure, and Mac encoding remain out
  of this slice.

### Phase 4: Curve-Follow Target Camera Strategy

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
same per-frame camera objects used by current keyframe planning. This phase
comes after local video assembly so curve-follow smoothness can be reviewed as
both individual frames and a playable preview.

### Phase 5: Artifact And RookVision Publishing

After the local frame/video contract stabilizes, add an optional publishing
layer:

- register `videos/preview.mp4` with the existing artifact store;
- expose completed Director videos through an existing UI or gallery surface;
- hand selected frames or videos to RookVision generation workflows.

This phase should consume completed Director outputs. It should not become a
dependency of camera planning, native frame capture, or local native video
assembly.

## Non-Goals For The Completed Phase 3 Slice

The platform-native MP4 assembly slice does not implement:

- `curve_follow_target`;
- FFmpeg invocation or FFmpeg fallback;
- artifact store publication;
- UI/gallery changes;
- RookVision publishing;
- native `/director/frame-capture` changes;
- Mac AVFoundation implementation.

It existed to prove that completed Director frame runs can become local preview
videos without weakening the deterministic frame-run spine or introducing GPL
licensing ambiguity. That proof is complete; these remain non-goals for the
Phase 4 camera-path slice.

## Self-Review

- No phase depends on artifact publishing before deterministic local outputs
  exist.
- Native frame capture remains the atomic Rhino mutation boundary.
- Phase 1 is complete: camera planning now lives in `camera_planner.py`.
- Existing slice 1 requests remain valid.
- Timeline/FPS/duration semantics are now separated from native video assembly
  and run before future camera strategies.
- MP4 output is explicitly separated from frame-run status.
- The next video path avoids FFmpeg/libx264 licensing ambiguity by using a
  platform-native backend boundary.
- Phase 3 is complete: local MP4 previews now provide the playback surface for
  reviewing camera-path smoothness.
- Phase 4 should add `curve_follow_target` without changing frame capture,
  video assembly, artifact publishing, or UI/gallery behavior.
