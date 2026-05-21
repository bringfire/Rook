# RookVisionDirector Curve-Follow Target Design

Date: 2026-05-21

Status: approved design for Phase 4 implementation

## Purpose

Phase 4 adds the first non-keyframe RookVisionDirector camera strategy:
`curve_follow_target`.

The user-facing goal is:

```text
Use this Rhino curve as the camera path.
Keep the camera aimed at this fixed point.
Render the frames and review them as a local video preview.
```

This slice proves the camera-path planner on top of the already-complete frame
and video loop. It does not add target lookup, artifact publishing, UI/gallery
behavior, or new native frame-capture behavior.

## Contract

Phase 4 v1 accepts this camera shape:

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

`curve_id` is a Rhino curve object UUID string. It is not a name lookup.

`target` is numeric-only by design. Phase 4 does not accept target ids, target
names, object centroids, bounding-box centers, or other target resolution
policies. Future target resolution can be added deliberately as a separate
`target_source` shape after this path proves stable.

Optics follow the existing camera planner rule:

- positive finite `lens_length` is authoritative when supplied;
- finite `fov_degrees` in `(0, 180)` is accepted when `lens_length` is absent;
- if both are supplied, `lens_length` wins;
- at least one optics field is required.

## Validation Boundaries

`validate_camera_request()` becomes strategy-aware but stays native-free. For
`curve_follow_target`, it validates:

- `strategy == "curve_follow_target"`;
- `curve_id` is a non-empty string that parses with `uuid.UUID(...)`;
- `target` is a finite numeric 3-number array;
- `up` is a finite non-degenerate 3-number vector;
- `sampling.mode == "normalized_parameter"`;
- `sampling.start` and `sampling.end` are finite numbers in `0..1`;
- `sampling.end >= sampling.start`;
- optics follow the rule above.

Every numeric validator rejects booleans explicitly. Python's `float(True)` is
not acceptable authoring input.

`resolve_camera_plan()` owns native-dependent validation. It calls
`/director/curve-samples` after request-shape validation, then validates each
resolved camera frame.

## Camera Data Flow

`resolve_camera_plan()` handles `curve_follow_target` as a direct per-frame
camera producer:

1. Validate the authoring shape without native calls.
2. Call `/director/curve-samples` once with `curve_id`, `frame_count`, and
   `sampling`.
3. Parse native failure shapes defensively:
   - direct `{ "code": "...", "message": "..." }` under `data`;
   - nested `{ "error": { "code": "...", "message": "..." } }` under `data`;
   - plain string `data`;
   - `None`.
4. Strictly validate the sample response:
   - `samples` is an array;
   - every sample is an object;
   - each `frame_index` is an integer in `1..frame_count`;
   - exactly one sample exists for every frame index;
   - no duplicate frame indexes;
   - every sample `point` is a finite numeric 3-number array;
   - booleans are rejected in sample points;
   - tests mirror the real native response fields `normalized_parameter` and
     `curve_parameter`.
5. Build a sample dictionary keyed by `frame_index`, then iterate
   `1..frame_count`. This makes missing, duplicate, and out-of-range samples
   unambiguous.
6. For each frame, construct a perspective camera:
   - `location = sample.point`;
   - `target = request.target`;
   - `up = normalized request.up`;
   - `aspect = resolution.width / resolution.height`;
   - optics according to the shared authority rule.
7. Validate each resolved frame through the existing camera validation path plus
   a curve-follow-specific up/direction threshold:

```text
abs(dot(normalized(target - location), normalized(up))) >= 0.999
```

Frames crossing that threshold are rejected. Transported-frame and roll handling
are deferred to a later strategy option.

The planner emits per-frame cameras directly. It does not synthesize keyframes
and does not route curve-follow through the keyframe interpolation path.

## Manifest Shape

`camera_plan` remains the canonical strategy summary, but existing keyframe
manifest fields stay where they are. Phase 4 does not migrate existing keyframe
fields into a nested object.

Existing keyframe runs continue to write:

```json
{
  "camera_plan": {
    "strategy": "keyframes",
    "request_shape": "legacy_camera_keyframes",
    "aspect_authority": "output_resolution",
    "optics_authority": "lens_length"
  },
  "camera_keyframes": [
    {
      "frame_index": 1,
      "source": { "kind": "active_view" }
    }
  ],
  "camera_keyframe_provenance": [
    {
      "frame_index": 1,
      "provenance": { "source": "active_view" }
    }
  ]
}
```

`curve_follow_target` writes the same top-level summary fields plus nested
strategy-specific provenance:

```json
{
  "camera_plan": {
    "strategy": "curve_follow_target",
    "request_shape": "camera_strategy",
    "aspect_authority": "output_resolution",
    "optics_authority": "lens_length",
    "provenance": {
      "curve_id": "00000000-0000-0000-0000-000000000000",
      "target": [10.0, 5.0, 3.0],
      "up": [0.0, 0.0, 1.0],
      "sampling": {
        "mode": "normalized_parameter",
        "start": 0.0,
        "end": 1.0
      },
      "curve_sampling": {
        "sampling_mode": "normalized_parameter",
        "parameter_mapping": "curve_domain_parameter_at",
        "frame_count_source": "caller_canonical_frame_count",
        "arc_length_sampled": false,
        "validation_strength": "curve_parameter_sampled"
      }
    }
  },
  "camera_keyframes": [],
  "camera_keyframe_provenance": []
}
```

`curve_sampling` preserves the full native provenance object from
`/director/curve-samples`, not a curated subset. This keeps diagnostics such as
`parameter_mapping`, `frame_count_source`, and `arc_length_sampled`.

`optics_authority` is:

- `"lens_length"` when `lens_length` is supplied, including when both optics
  fields are supplied;
- `"fov_degrees"` only when `lens_length` is absent and `fov_degrees` is
  supplied.

`manifest.frames[*].camera` remains the explicit per-frame camera state and the
only camera data consumed by frame capture. `camera_plan` explains how those
cameras were produced.

## MCP Schema

The `rhino_director_run` schema will describe `curve_follow_target` without JSON
Schema composition keywords.

The `camera` object currently requires `["strategy", "keyframes"]`. Phase 4
changes that to require only `["strategy"]`; runtime validation enforces
strategy-specific required fields.

The schema documents:

- `strategy` accepts `keyframes` or `curve_follow_target`;
- `curve_id` is a Rhino curve object UUID string, not a name;
- `target` is a numeric `[x, y, z]` point array, not an object/name reference;
- `up` is a numeric 3-vector;
- `sampling` supports only `normalized_parameter` with `start` and `end`;
- optics use `lens_length` first, otherwise `fov_degrees`.

## Tests

`mcp_server/tests/test_camera_planner.py` covers:

- success path with the real native sample shape:
  `normalized_parameter`, `curve_parameter`, `point`, and `tangent`;
- `curve_id` syntax rejection;
- target, up, sampling, and optics validation;
- boolean rejection in authoring and native sample numeric fields;
- native failure parsing for direct, nested, string, and `None` shapes;
- strict sample indexing: missing, duplicate, out-of-range, non-object,
  non-finite point, and boolean point;
- sample-at-target direction rejection;
- up/view parallel threshold rejection;
- optics authority:
  - `lens_length` only -> `"lens_length"`;
  - `fov_degrees` only -> `"fov_degrees"`;
  - both supplied -> `"lens_length"`;
- no regression for existing keyframe planning;
- `curve_follow_target` does not call `/director/view-state`.

`mcp_server/tests/test_director.py` covers:

- `run_director` accepts `curve_follow_target`;
- invalid curve-follow authoring rejects before `/director/object-states`;
- `camera_plan.strategy == "curve_follow_target"`;
- `camera_keyframes == []`;
- `camera_keyframe_provenance == []`;
- `manifest.frames[*].camera` contains explicit cameras;
- the native call sequence is one `/director/curve-samples` call followed by
  `/director/frame-capture` per frame, with no `/director/view-state` call.

`mcp_server/tests/test_director_mcp_tools.py` covers:

- the `camera` schema requires only `strategy`;
- schema text includes the new fields and numeric-only target wording;
- rejected schema keyword scan remains empty;
- dispatch still routes through `director.run_director`.

`mcp_server/tests/test_director_routes_live.py` may add a guarded smoke:

- if the fixture contains a named curve/path object, existing discovery/test
  helpers may resolve it to a UUID;
- the strategy input must still send `curve_id` as a UUID;
- if the fixture curve is absent, the test skips cleanly;
- the smoke may assemble an MP4 after the frame run, but Phase 4 does not add
  automatic assembly.

## Scope Exclusions

Phase 4 does not include:

- native C++ changes;
- `/director/frame-capture` changes;
- `/director/video-assemble` changes;
- managed companion changes;
- artifact store, gallery, or RookVision publishing;
- target-by-id or target-by-name;
- arc-length sampling;
- transported-frame or roll behavior;
- automatic video assembly inside `rhino_director_run`.

## Self-Review

- The design keeps `target` numeric-only and names future target resolution as a
  separate shape.
- The native boundary is unchanged: curve sampling is read-only; frame capture
  consumes explicit cameras; video assembly remains post-run.
- Manifest compatibility is preserved by leaving keyframe `camera_plan` fields
  in place and writing empty legacy arrays for non-keyframe plans.
- Strict sample indexing prevents native or fake responses from silently
  reordering, dropping, or duplicating frames.
- All required implementation work is Python planner, schema, and tests.
