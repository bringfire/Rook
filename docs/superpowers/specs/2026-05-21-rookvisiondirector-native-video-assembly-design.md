# RookVisionDirector Native Video Assembly Design

Date: 2026-05-21

Status: draft for review

## Purpose

RookVisionDirector can now produce a deterministic PNG frame sequence from a
completed Director run. A live fixture run proved that camera interpolation,
radial object-motion interpolation, display-mode application, PNG capture, and
state restoration can all succeed together.

The next slice turns a completed frame run into a local preview MP4 without
weakening the frame-run contract or adding GPL licensing ambiguity.

The v1 contract is:

```text
completed Director frame run + timeline fps or explicit fps override -> preview video + video_manifest.json
```

Video assembly is an explicit post-run operation first. `rhino_director_run`
does not gain an automatic assembly flag in this slice.

## Decision

Choose a platform-native video backend route:

- Windows v1 implementation: Media Foundation.
- Mac future implementation: AVFoundation / VideoToolbox.
- Shared Director-facing contract: completed run folder in, local preview MP4
  and deterministic manifest out.

This is intentionally not an FFmpeg slice. The bundled Rook FFmpeg binary is an
extraction-oriented sidecar tool and cannot currently encode Director PNG frames
into MP4. Broad FFmpeg builds with GPL encoders such as libx264 must not become
the Director product path. This slice has no FFmpeg fallback.

## Scope

Included:

- explicit post-run MCP/API surface for assembling a completed Director run;
- Python orchestration and input validation around a run folder;
- a thin native/platform backend boundary for actual encoding;
- Windows Media Foundation implementation;
- `videos/preview.mp4` output inside the Director run folder;
- `video_manifest.json` with complete or failed state;
- tests for validation, manifest shape, backend dispatch, and failure
  separation from frame-run status;
- live Windows verification against a completed Director frame run.

Excluded:

- Mac AVFoundation implementation;
- automatic assembly as part of `rhino_director_run`;
- FFmpeg invocation or fallback;
- artifact-store registration;
- gallery/UI work;
- RookVision publishing or provider handoff;
- changing `/director/frame-capture`;
- new camera strategies such as `curve_follow_target`.

## Architecture

Python remains the run-level owner. It validates the completed Director run,
decides the output paths, calls the platform backend, and writes
`video_manifest.json`.

The platform backend owns encoding. On Windows the backend is Media Foundation,
behind a narrow native boundary. The boundary should be small enough that a Mac
backend can later implement the same contract without inheriting Windows
details.

The shared backend request shape is:

```json
{
  "run_root": "C:/.../rookvision_director/run-id",
  "frames_dir": "C:/.../rookvision_director/run-id/frames",
  "input_pattern": "frame_%04d.png",
  "start_number": 1,
  "frame_count": 120,
  "fps": 24,
  "width": 1280,
  "height": 720,
  "output_path": "C:/.../rookvision_director/run-id/videos/preview.mp4",
  "codec": "h264",
  "container": "mp4"
}
```

All request paths in this shape are advisory inputs, not trusted authorities.
The native backend must canonicalize and policy-check `run_root`, `frames_dir`,
and `output_path` independently against the configured Director output root
before it reads frames or writes video. A path is accepted only when:

- `run_root` resolves under the configured Director output root;
- `frames_dir` resolves to `run_root/frames`;
- `output_path` resolves under `run_root/videos`;
- no path escapes through relative segments, symlinks, junctions, casing
  tricks, or alternate path spelling;
- the canonical output parent exists or can be created under `run_root/videos`.

The Python orchestration performs the same policy checks early for good errors,
but native validation is the enforcement boundary because the native route is a
public HTTP surface with filesystem read/write effects.

The backend response shape is:

```json
{
  "success": true,
  "backend": "media_foundation",
  "platform": "windows",
  "codec": "h264",
  "container": "mp4",
  "output_path": "C:/.../videos/preview.mp4",
  "bytes": 123456,
  "output_current": true,
  "preserved_previous_output": false,
  "evidence": {
    "frames_encoded": 120
  },
  "error": null
}
```

The exact native route name can be selected during implementation planning, but
it should be Director-owned and platform-specific under the hood rather than a
generic media framework.

## Input Validation

The post-run assembler must validate before encoding:

- `run_root` exists and resolves to a Director run directory;
- `status.json` exists and has `state == "complete"`;
- `manifest.json` exists and has `schema_version`, `director_version`,
  `frame_count`, `resolution`, `frames`, and `timeline`;
- `timeline.fps` is positive, or the caller supplied an explicit positive FPS
  override;
- manifest frame count equals the expected frame list length;
- every expected `frames/frame_0001.png` through `frame_NNNN.png` exists;
- every frame dimension matches manifest resolution before backend invocation;
- width and height are positive even integers for v1 H.264 MP4 output;
- output path resolves under `run_root/videos/`;
- existing preview output replacement follows the v1 replacement policy below.

Decode and pixel-format conversion are backend responsibilities. Python does
not need a full PNG decode/conversion stack to call the backend. The native
backend validates that each frame can be decoded and converted to the v1 encoder
input format, returning `unsupported_frame_format` if not.

Legacy frame-count runs without timeline FPS fail by default unless the caller
supplies an explicit FPS override. The manifest must record whether FPS came
from timeline metadata or caller override.

## Replacement Policy

V1 writes one deterministic preview target:

```text
videos/preview.mp4
video_manifest.json
```

Repeated assembly for the same completed run replaces the previous preview
atomically. Python records `overwrote_existing: true` in `video_manifest.json`
when either previous file existed. The backend writes to a temporary file inside
`run_root/videos/`, validates that the completed file exists and is non-empty,
then atomically replaces `videos/preview.mp4`.

If validation fails before backend invocation, the prior `videos/preview.mp4`
is left untouched and `video_manifest.json` is replaced with the failed
manifest. That failed manifest must set `output_current: false` and
`preserved_previous_output: true` when an older preview still exists, so
consumers cannot mistake the stale preview for the failed attempt's output.
For a failed first attempt with no previous preview, the manifest sets
`output_current: false`, `preserved_previous_output: false`, and
`overwrote_existing: false`.

If backend encoding fails after a temporary file is created, the temporary file
is deleted where possible and the prior completed preview is left untouched.
The failed manifest uses the same stale-output fields. Any cleanup failure is
recorded in `evidence`.

## Manifest Contract

Frame-run status remains in `status.json`. Video assembly status is separate in
`video_manifest.json`.

Successful manifest:

```json
{
  "schema_version": 1,
  "state": "complete",
  "run_id": "rvd_combined_camera_geometry_12fps_2s",
  "backend": "media_foundation",
  "platform": "windows",
  "format": "mp4",
  "codec": "h264",
  "container": "mp4",
  "fps": 12,
  "fps_source": "timeline",
  "frame_count": 24,
  "width": 1280,
  "height": 720,
  "input_pattern": "frames/frame_%04d.png",
  "output_path": "videos/preview.mp4",
  "bytes": 123456,
  "overwrote_existing": false,
  "output_current": true,
  "preserved_previous_output": false,
  "started_at": "2026-05-21T00:00:00Z",
  "completed_at": "2026-05-21T00:00:03Z",
  "error": null,
  "evidence": {
    "frames_encoded": 24
  }
}
```

Failed manifest:

```json
{
  "schema_version": 1,
  "state": "failed",
  "run_id": "rvd_combined_camera_geometry_12fps_2s",
  "backend": "media_foundation",
  "platform": "windows",
  "format": "mp4",
  "codec": "h264",
  "container": "mp4",
  "fps": 12,
  "fps_source": "timeline",
  "frame_count": 24,
  "width": 1280,
  "height": 720,
  "input_pattern": "frames/frame_%04d.png",
  "output_path": "videos/preview.mp4",
  "bytes": 0,
  "overwrote_existing": true,
  "output_current": false,
  "preserved_previous_output": true,
  "started_at": "2026-05-21T00:00:00Z",
  "completed_at": "2026-05-21T00:00:01Z",
  "error": {
    "code": "missing_frame",
    "message": "Expected frame was missing: frames/frame_0012.png"
  },
  "evidence": {}
}
```

The manifest is deterministic in field names and relative path presentation.
Timestamps and backend evidence are the only inherently run-specific values.

## Error Handling

Validation failures write `video_manifest.json` with `state: "failed"` when the
run folder can be safely identified. They do not alter `status.json`.

Backend failures also write `video_manifest.json` with `state: "failed"` and a
structured error code. The backend should clean up partial output where
possible, or record partial output evidence if cleanup fails.

V1 structured error codes include at least:

- `run_root_policy_violation`;
- `frames_dir_policy_violation`;
- `output_policy_violation`;
- `frame_run_incomplete`;
- `fps_missing`;
- `missing_frame`;
- `frame_count_mismatch`;
- `dimension_mismatch`;
- `unsupported_dimensions`;
- `unsupported_frame_format`;
- `backend_unavailable`;
- `backend_encode_failed`;
- `output_replace_failed`.

The MCP/API response mirrors the manifest summary and returns the manifest path.

## Media Foundation Compatibility

V1 targets H.264 in an MP4 container through Media Foundation. Before invoking
the backend, Python validates frame existence and dimensions. The native backend
then validates platform capabilities and frame conversion requirements at the
enforcement boundary.

The v1 backend accepts Director PNG frames that can be decoded and converted to
an H.264-compatible pixel format such as NV12. Alpha, if present, is ignored by
compositing against opaque black (`#000000`) before encoding. If any frame has
alpha, the backend records `alpha_composited: true` and
`alpha_background: "#000000"` in `evidence`. Frames that cannot be decoded or
converted fail with `unsupported_frame_format`.

V1 rejects odd output dimensions with `unsupported_dimensions`; callers can
rerun frame capture at even dimensions. If the Media Foundation H.264 encoder is
not available on the host, the backend fails with `backend_unavailable` and a
diagnostic evidence payload. Backend-specific capability details stay under
`evidence`; the public v1 API does not expose Media Foundation-specific encoder
options.

The Windows dependency is expected to be present on supported Windows desktop
machines rather than bundled with Rook. Microsoft documents Media Foundation's
MPEG-4 file sink as native support on Windows 7+ and the H.264 video encoder as
a Media Foundation transform exposed by `Mfh264enc.dll`, also with Windows 7
desktop-client support. The implementation must still perform runtime
capability detection and return `backend_unavailable` if the expected Media
Foundation components are absent or unusable on a specific installation.

## Mac Backend Contract

The deferred Mac backend implements the same backend request and response
contract using AVFoundation / VideoToolbox. It should write the same relative
output path and manifest shape. Differences such as backend-specific evidence
belong under `evidence`, not in the top-level contract.

The Windows implementation must not expose Media Foundation-specific settings
through the v1 public API unless the same field can be mapped cleanly to the Mac
backend later.

## Testing

Unit and contract tests:

- completed run with timeline FPS validates;
- legacy completed run without FPS fails unless override is supplied;
- missing frame fails before backend invocation;
- any frame with mismatched dimensions fails before backend invocation;
- odd dimensions fail with `unsupported_dimensions`;
- unsupported frame decode/conversion fails with `unsupported_frame_format`;
- failed frame-run status rejects video assembly without changing
  `status.json`;
- successful backend response writes a complete manifest;
- failed backend response writes a failed manifest;
- failed manifest distinguishes stale preserved preview from current output;
- native backend rejects `run_root`, `frames_dir`, or `output_path` outside the
  configured Director output root and run folder;
- MCP/tool schema exposes a post-run assembly tool without adding automatic
  `rhino_director_run` behavior.

Native/source tests:

- Windows backend route is registered;
- backend independently canonicalizes and rejects paths outside the configured
  Director output root, `run_root/frames`, and `run_root/videos`;
- backend returns structured errors for unsupported platform/backend failures;
- Media Foundation implementation is isolated behind the Director video backend
  boundary.

Live verification:

- run the assembler against a known completed Director run;
- verify `videos/preview.mp4` exists and is non-empty;
- verify `video_manifest.json.state == "complete"`;
- verify manifest FPS, frame count, width, height, codec, backend, and output
  path;
- manually play or inspect the MP4 enough to confirm camera and geometry
  interpolation are visible.

## Acceptance

On Windows, a completed Director frame run with timeline FPS or explicit FPS
override can be assembled into `videos/preview.mp4` using Media Foundation. The
operation produces `video_manifest.json` with complete or failed state and
enough evidence to debug backend and input failures. The design documents the
matching AVFoundation backend contract, but Mac implementation is deferred.

The implementation must not call FFmpeg, must not use libx264, must not modify
frame-run `status.json`, and must not add artifact-store, gallery, UI, or
RookVision publishing behavior.

## Self-Review

- Scope is one post-run assembly feature, not a general codec framework.
- Frame-run and video-run status remain separate.
- FFmpeg fallback is explicitly excluded.
- Windows implementation is real; Mac implementation is documented but deferred.
- The manifest records backend, platform, FPS, frame count, dimensions, paths,
  codec/container, state, timestamps, and structured error.
- The design keeps publishing/UI out of this slice.
