# RookVisionDirector Video Publish Design

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md

Date: 2026-05-21

Status: approved design for Phase 5A implementation

## Purpose

Phase 5A publishes completed RookVisionDirector MP4 previews as durable
RookVision `generated_video` artifacts.

The slice adds an explicit publish operation with conservative video-profile
guardrails. It does not transcode, resize, create sidecars, change Director
frame or video assembly behavior, or add Gallery UI.

The user-facing workflow is:

```text
Run Director frames.
Assemble videos/preview.mp4.
Publish that preview as a RookVision generated_video artifact.
```

## Architecture

Phase 5A adds one explicit publish path:

```text
rhino_director_publish_video({ run_root })
  -> Python director_publish.py validates Director run + standard profile
  -> Python computes hashes, byte size, compact metadata.director
  -> Python checks prior publish_manifest.json, if present
  -> Python calls managed /vision/director/publish-video
  -> Managed re-checks artifact-boundary safety
  -> Managed creates or confirms generated_video artifact with video.mp4 only
  -> Python writes publish_manifest.json in the Director run folder
```

Ownership is split deliberately:

- Python owns Director lifecycle and profile semantics:
  `status.json`, `manifest.json`, `video_manifest.json`, `output_current`,
  `director_publish_standard_v1`, hashes, source-relative path, compact camera
  provenance, idempotency decisions, and publish state.
- Managed C# owns the irreversible artifact boundary: Director-root containment,
  exact `videos/preview.mp4`, manifest/request consistency, byte/hash
  consistency, existing-artifact verification, and `ArtifactStore.Create(...)`.
- Native gets at most thin Vision-route proxy wiring. Native does not own
  Director publish validation, artifact creation, video assembly, sidecar
  behavior, or any Director frame/video behavior changes.

Managed confirms only when Python supplies a prior artifact id from
`publish_manifest.json`. Confirmation verifies that artifact exists, is
`generated_video`, has a `video` blob, and has matching contract metadata/source
facts. Managed does not globally scan for duplicate artifacts.

## Director Output Root Contract

Managed C# must use the same Director output root contract as Python and
RookNative:

1. If `ROOK_DIRECTOR_OUTPUT_ROOT` is set, canonicalize it and use it as the only
   allowed Director output root.
2. Otherwise, canonicalize `%LOCALAPPDATA%/Rook/rookvision_director`.
3. If `LOCALAPPDATA` is unavailable and `ROOK_DIRECTOR_OUTPUT_ROOT` is not set,
   reject the publish request before reading or copying files.

Managed must not use `%APPDATA%/Rook`, `RookPaths.ArtifactsRoot`, the Vision
artifact root, or a request-provided path as the Director output-root fallback.
This keeps publish containment aligned with the existing Director frame and
video assembly policies.

## Public Tool Contract

Add:

```text
rhino_director_publish_video
```

Input:

```json
{
  "run_root": "C:/Users/aryan/AppData/Local/Rook/rookvision_director/<run_id>"
}
```

Phase 5A has no `force`, no republish option, no output path override, no
sidecar option, and no provider-specific profile selection.

The successful response includes:

```json
{
  "state": "complete",
  "artifact_id": "00000000-0000-0000-0000-000000000000",
  "profile": "director_publish_standard_v1",
  "preset": "hd_720",
  "source_video": "videos/preview.mp4",
  "sidecar_policy": "existing_generated_video_pipeline"
}
```

## Profile Policy

Phase 5A defines one Python-owned profile:

```text
director_publish_standard_v1
```

Accepted output:

```text
format: mp4
container: mp4
codec: h264
dimensions:
  hd_720        1280x720
  full_hd_1080  1920x1080
  uhd_4k        3840x2160
  uhd_8k        7680x4320
fps:
  24
  30
```

The 16:9 rule is derived from the dimension whitelist. There is no independent
floating-point aspect check.

Manifest validation is strict for v1:

- `format` must be present and equal to `mp4`;
- `container` must be present and equal to `mp4`;
- `codec` must be present and equal to `h264`;
- no codec aliases are accepted in Phase 5A: not `H.264`, `avc1`, or `AVC`.

If required manifest fields are missing or internally inconsistent, Python
returns `video_manifest_invalid`. If the facts are valid but outside
`director_publish_standard_v1`, Python returns `unsupported_video_profile`.

Profile validation is publish-time only. Phase 5A does not change
`rhino_director_run`, does not add `video_profile` authoring, and does not
auto-publish or auto-assemble.

## Python Validation

Python validates before managed publish:

- `run_root` resolves under the configured Director output root;
- `status.json` exists and has `state == "complete"`;
- `manifest.json` exists and is readable;
- `video_manifest.json` exists and has `state == "complete"`;
- `video_manifest.json.output_current == true`;
- `manifest.json` and `video_manifest.json` agree on frame count, resolution,
  and FPS before Python builds `metadata.director`;
- source video is exactly `videos/preview.mp4`;
- source video exists, is non-empty, and its byte size and SHA-256 are computed;
- format/container/codec/dimensions/FPS match `director_publish_standard_v1`;
- `publish_manifest.json`, if present, is valid enough to evaluate idempotency;
- prior successful publish facts match current hashes/profile before idempotent
  confirmation is attempted.

If `publish_manifest.json` records a successful publish with malformed
`artifact_id`, Python returns `publish_manifest_invalid`. If the artifact id is
well-formed but no longer exists, the publish returns `published_artifact_missing`
instead of silently republishing.

If source hashes or profile differ from a previous successful publish manifest,
Python returns `publish_facts_changed`. Phase 5A intentionally has no `force`
or republish path.

## Managed Publish Request

Python calls this narrow managed route:

```text
POST /vision/director/publish-video
```

The request contains:

```json
{
  "run_id": "...",
  "profile": "director_publish_standard_v1",
  "preset": "hd_720",
  "source": {
    "run_root": "...",
    "relative_path": "videos/preview.mp4",
    "absolute_path": ".../videos/preview.mp4",
    "byte_size": 894175,
    "sha256": "..."
  },
  "facts": {
    "container": "mp4",
    "format": "mp4",
    "codec": "h264",
    "width": 1280,
    "height": 720,
    "fps": 24,
    "frame_count": 96
  },
  "hashes": {
    "video_manifest_sha256": "...",
    "frame_manifest_sha256": "..."
  },
  "metadata": {
    "director": {
      "schema_version": 1,
      "run_id": "...",
      "profile": "director_publish_standard_v1",
      "preset": "hd_720",
      "source_video": "videos/preview.mp4",
      "video_manifest_hash": "...",
      "frame_manifest_hash": "...",
      "camera_strategy": "curve_follow_target",
      "camera": {
        "strategy": "curve_follow_target",
        "curve_id": "...",
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "sampling": {
          "mode": "normalized_parameter",
          "start": 0.0,
          "end": 1.0
        }
      },
      "timeline": {
        "fps": 24,
        "duration_seconds": 4.0,
        "frame_count": 96
      },
      "resolution": {
        "width": 1280,
        "height": 720
      }
    }
  },
  "prior_artifact_id": "optional-guid-from-publish-manifest"
}
```

`source.absolute_path` is advisory only. Managed recomputes the absolute path
from `run_root + relative_path`, normalizes it, verifies containment under the
configured Director output root, verifies the relative path is exactly
`videos/preview.mp4`, and only then compares the recomputed path to the supplied
advisory path if present.

Managed also verifies:

- `run_id` matches the run folder and manifests;
- `video_manifest.json.state == "complete"`;
- `video_manifest.json.output_current == true`;
- manifest facts match request facts;
- source byte size and hash match disk reality;
- `profile`, preset, manifest hashes, and stable Director metadata contract
  fields match a supplied prior artifact;
- when confirming a prior artifact, the existing artifact's `video` blob is
  resolved through `ArtifactStore`, hashed, and byte-counted, then compared to
  the request `source.sha256` and `source.byte_size`;
- prior artifact confirmation accepts additional metadata fields but requires
  the contract fields to match.

Managed creates only:

```text
kind: generated_video
blob role: video
extension: mp4
```

Managed does not create `poster`, `start_frame`, or `end_frame` sidecars.

## Artifact Metadata

The artifact metadata is compact and portable. It must not include local
absolute paths such as `run_root`.

The artifact contains:

```json
{
  "director": {
    "schema_version": 1,
    "run_id": "...",
    "profile": "director_publish_standard_v1",
    "preset": "hd_720",
    "source_video": "videos/preview.mp4",
    "video_manifest_hash": "...",
    "frame_manifest_hash": "...",
    "camera_strategy": "curve_follow_target",
    "camera": {
      "strategy": "curve_follow_target",
      "curve_id": "...",
      "target": [0.0, 0.0, 0.0],
      "up": [0.0, 0.0, 1.0],
      "sampling": {
        "mode": "normalized_parameter",
        "start": 0.0,
        "end": 1.0
      }
    },
    "timeline": {
      "fps": 24,
      "duration_seconds": 4.0,
      "frame_count": 96
    },
    "resolution": {
      "width": 1280,
      "height": 720
    }
  }
}
```

Camera metadata is strategy-specific and intentionally small:

- `curve_follow_target`: include `strategy`, `curve_id`, `target`, `up`, and
  `sampling`;
- `keyframes`: include `strategy`, keyframe count, and source kinds/names, but
  not resolved per-frame cameras.

The artifact metadata does not copy whole manifests, object ids, resolved
per-frame camera arrays, native evidence, or local absolute paths. Manifest
hashes are the integrity link back to local Director run files.

## Publish Manifest

`publish_manifest.json` lives in the Director run folder and records local/debug
state.

Success:

```json
{
  "schema_version": 1,
  "state": "complete",
  "artifact_id": "...",
  "prior_artifact_id": null,
  "profile": "director_publish_standard_v1",
  "preset": "hd_720",
  "run_root": "...",
  "source_path": ".../videos/preview.mp4",
  "source_video": "videos/preview.mp4",
  "source_sha256": "...",
  "source_byte_size": 894175,
  "video_manifest_hash": "...",
  "frame_manifest_hash": "...",
  "sidecar_policy": "existing_generated_video_pipeline",
  "started_at": "...",
  "completed_at": "...",
  "error": null
}
```

`prior_artifact_id` may be omitted or null for first publish. During a
successful idempotent return, `artifact_id` and `prior_artifact_id` may be the
same value.

Managed rejections preserve both the Python umbrella code and the managed
subcode:

```json
{
  "schema_version": 1,
  "state": "failed",
  "artifact_id": null,
  "prior_artifact_id": "...",
  "profile": "director_publish_standard_v1",
  "preset": "hd_720",
  "sidecar_policy": "existing_generated_video_pipeline",
  "error": {
    "code": "artifact_boundary_mismatch",
    "managed_subcode": "source_hash_mismatch",
    "message": "Managed publish rejected the source video hash."
  }
}
```

## Errors

Python-facing error codes:

- `run_not_complete`;
- `video_not_assembled`;
- `video_not_current`;
- `video_manifest_invalid`;
- `unsupported_video_profile`;
- `publish_manifest_invalid`;
- `publish_facts_changed`;
- `published_artifact_missing`;
- `managed_publish_rejected`;
- `artifact_boundary_mismatch`.

The unsupported profile message should be actionable:

```json
{
  "state": "failed",
  "error": {
    "code": "unsupported_video_profile",
    "message": "Director publish supports director_publish_standard_v1: 1280x720, 1920x1080, 3840x2160, or 7680x4320 MP4/H.264 at supported FPS values."
  }
}
```

Managed rejection subcodes:

- `source_path_mismatch`;
- `source_hash_mismatch`;
- `source_size_mismatch`;
- `manifest_fact_mismatch`;
- `prior_artifact_mismatch`.

Python may surface `artifact_boundary_mismatch` while preserving the managed
subcode in response details and `publish_manifest.json`.

## Sidecar Policy

Publish creates only the primary MP4 artifact:

```text
kind: generated_video
role: video
extension: mp4
```

No sidecars are created during publish. Publish success is independent of
thumbnail or frame sidecar availability.

The existing generated-video sidecar/backfill pipeline remains responsible for:

- `poster`;
- `start_frame`;
- `end_frame`.

`publish_manifest.json` records:

```json
{
  "sidecar_policy": "existing_generated_video_pipeline"
}
```

## Tests

Python tests cover:

- successful publish request construction for a completed/current standard run;
- `status.json.state != "complete"` fails as `run_not_complete`;
- missing `video_manifest.json` or `video_manifest.state != "complete"` fails
  as `video_not_assembled`;
- `video_manifest.output_current == false` fails as `video_not_current`, even
  when `videos/preview.mp4` exists;
- `manifest.json` and `video_manifest.json` mismatch on frame count,
  resolution, or FPS fails before metadata construction;
- missing/inconsistent manifest facts fail as `video_manifest_invalid`;
- valid but nonstandard dimensions/FPS/codec fail as
  `unsupported_video_profile`;
- source/video/frame-manifest hash computation;
- compact `metadata.director`, including `profile`, `preset`, timeline,
  resolution, and camera provenance;
- success and failure `publish_manifest.json` writes;
- idempotent return when prior publish facts match and managed confirms the
  prior artifact;
- malformed prior artifact id fails as `publish_manifest_invalid`;
- missing prior artifact fails as `published_artifact_missing`;
- changed source hashes/profile fails as `publish_facts_changed`;
- managed umbrella code plus `managed_subcode` is preserved on safety-envelope
  rejection.

Managed tests cover:

- source path outside Director root is rejected;
- source relative path other than `videos/preview.mp4` is rejected;
- advisory absolute path is not path-authoritative;
- source hash mismatch and source size mismatch are rejected;
- request facts that do not match `video_manifest.json` are rejected;
- request `run_id` must match the run folder and manifests;
- creation produces exactly `generated_video` with one `video.mp4` blob;
- creation stores compact `metadata.director`, including `profile` and `preset`;
- prior artifact confirmation checks contract fields, not byte-for-byte
  metadata equality;
- prior artifact confirmation accepts additional metadata fields;
- prior artifact confirmation hashes and byte-counts the existing artifact's
  `video` blob before accepting idempotency;
- missing prior artifact returns `published_artifact_missing`;
- wrong prior artifact kind/blob/profile/hash returns
  `prior_artifact_mismatch`;
- creation does not trigger or require `poster`, `start_frame`, or `end_frame`
  sidecars.

MCP/tool tests cover:

- `rhino_director_publish_video` is registered in the Director group;
- schema only requires `run_root`;
- dispatch calls Python `director_publish.publish_director_video`;
- rejected schema keyword scan remains clean where applicable.

A guarded live smoke may:

- run or reuse a completed Director run with a standard profile;
- assemble video;
- publish it;
- retrieve the artifact through existing Vision artifact routes;
- assert artifact kind and role are `generated_video` and `video`;
- avoid any sidecar existence expectation.

## Scope Exclusions

Phase 5A does not include:

- transcoding, resizing, FPS conversion, or re-encoding;
- `rhino_director_run` authoring preset changes;
- automatic publish during Director run or video assembly;
- sidecar extraction;
- Gallery/UI changes;
- provider-specific model ingest mapping;
- native Director/frame/video behavior changes;
- artifact deduplication by global artifact scan;
- force republish.

## Self-Review

- The design keeps Python as the source of truth for Director profile policy.
- Managed C# is not a trust-only file copy endpoint; it owns safety at the
  artifact boundary.
- Artifact metadata is portable and compact; local paths are limited to the
  Director run's `publish_manifest.json`.
- Sidecar production stays with the existing generated-video sidecar/backfill
  pipeline.
- Idempotency is explicit and does not silently recreate missing or changed
  artifacts.
