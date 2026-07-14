# RookVisionDirector Curve-Follow Target Implementation Plan

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Python-owned `curve_follow_target` camera strategy that samples a Rhino curve and emits explicit per-frame cameras for the existing Director frame-capture path.

**Architecture:** `camera_planner.py` becomes strategy-aware while preserving keyframe behavior. `validate_camera_request()` performs native-free authoring validation; `resolve_camera_plan()` calls existing native `/director/curve-samples`, strictly validates indexed samples, and emits per-frame cameras directly. `director.py` writes strategy-aware manifest provenance while preserving legacy keyframe fields.

**Tech Stack:** Python MCP server, pytest, existing Director planner/orchestrator, existing native `/director/curve-samples`, existing `rhino_director_run` MCP schema.

---

## Source Design

Implement this plan against:

- `docs/superpowers/specs/2026-05-21-rookvisiondirector-curve-follow-target-design.md`
- `docs/superpowers/specs/2026-05-20-rookvisiondirector-camera-video-roadmap.md`

## Constraints

- Do not change `src/RookNative/**`.
- Do not change `/director/frame-capture`.
- Do not change `/director/video-assemble` or `rhino_director_assemble_video`.
- Do not change managed companion code.
- Do not add artifact-store, gallery, RookVision publishing, or automatic video assembly behavior.
- Do not add target-by-id or target-by-name.
- Do not add arc-length sampling.
- Preserve existing `camera_keyframes` and `camera.strategy == "keyframes"` behavior.
- Keep `target` numeric-only: `[x, y, z]`.
- Keep `curve_id` as a Rhino curve object UUID string, not a name lookup.

## File Structure

- Modify `mcp_server/src/rook/camera_planner.py`
  Add strategy-aware validation, UUID and boolean-safe numeric helpers, curve-follow native dispatch, strict sample indexing, optics authority, up/direction rejection, and direct per-frame camera output.
- Modify `mcp_server/src/rook/timeline.py`
  Normalize `camera.keyframes` only for `camera.strategy == "keyframes"`; leave `curve_follow_target` camera requests unchanged.
- Modify `mcp_server/src/rook/director.py`
  Make manifest camera fields strategy-aware. Keep legacy keyframe fields stable for keyframes and write empty legacy arrays for non-keyframe plans.
- Modify `mcp_server/src/rook/server.py`
  Update `rhino_director_run` schema so `camera.required == ["strategy"]` and the new fields are documented without rejected schema keywords.
- Modify `mcp_server/tests/test_camera_planner.py`
  Add planner tests for success, validation, native failure parsing, strict sample indexing, optics authority, and no view-state calls.
- Modify `mcp_server/tests/test_timeline.py`
  Add timeline normalization coverage that proves `curve_follow_target` cameras pass through without keyframe normalization.
- Modify `mcp_server/tests/test_director.py`
  Add orchestration and manifest compatibility tests, including fail-fast validation before `/director/object-states`.
- Modify `mcp_server/tests/test_director_mcp_tools.py`
  Add schema tests for the new strategy and required-field change.
- Modify `mcp_server/tests/test_director_routes_live.py`
  Add only a guarded live smoke if existing helpers can resolve a fixture curve to UUID without adding a runtime lookup path.

---

### Task 1A: Timeline Pass-Through For Non-Keyframe Camera Strategies

**Files:**
- Modify: `mcp_server/tests/test_timeline.py`
- Modify: `mcp_server/src/rook/timeline.py`

- [ ] **Step 1: Add a failing timeline pass-through test**

Add a test proving `timeline.normalize_director_request()` does not treat
`curve_follow_target` as keyframe input:

```python
def test_timeline_leaves_curve_follow_target_camera_unchanged():
    camera = {
        "strategy": "curve_follow_target",
        "curve_id": "00000000-0000-0000-0000-000000000001",
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        "lens_length": 35.0,
    }

    normalized, manifest = timeline.normalize_director_request(
        {
            "object_ids": ["a"],
            "timeline": {"fps": 24, "duration_seconds": 0.125},
            "resolution": {"width": 320, "height": 180},
            "camera": camera,
        }
    )

    assert normalized["frame_count"] == 3
    assert normalized["camera"] == camera
    assert manifest["frame_count"] == 3
```

- [ ] **Step 2: Run the timeline test and verify red**

Run:

```powershell
python -m pytest mcp_server/tests/test_timeline.py::test_timeline_leaves_curve_follow_target_camera_unchanged -q
```

Expected before implementation: fails because timeline normalization attempts to
normalize missing `camera.keyframes`.

- [ ] **Step 3: Make top-level camera normalization strategy-aware**

In `mcp_server/src/rook/timeline.py`, replace the current unconditional
top-level camera keyframe normalization with:

```python
if isinstance(normalized.get("camera"), dict):
    camera = dict(normalized["camera"])
    if camera.get("strategy") == "keyframes":
        camera["keyframes"] = _normalize_keyframes(
            camera.get("keyframes"),
            timeline_manifest=timeline_manifest,
        )
    normalized["camera"] = camera
```

Do not change legacy top-level `camera_keyframes` normalization.

- [ ] **Step 4: Run timeline tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_timeline.py -q
```

Expected: all timeline tests pass.

---

### Task 1: Camera Planner Failing Tests

**Files:**
- Modify: `mcp_server/tests/test_camera_planner.py`
- Read: `mcp_server/src/rook/camera_planner.py`

- [ ] **Step 1: Add a fake native for real curve-sample response shape**

Add this helper near the existing `FakeNative` class:

```python
class FakeCurveNative(FakeNative):
    def __init__(self, *, samples=None, curve_response=None):
        super().__init__([])
        self.samples = samples or [
            {
                "frame_index": 1,
                "normalized_parameter": 0.0,
                "curve_parameter": 2.0,
                "point": [0.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
            {
                "frame_index": 2,
                "normalized_parameter": 0.5,
                "curve_parameter": 6.0,
                "point": [5.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
            {
                "frame_index": 3,
                "normalized_parameter": 1.0,
                "curve_parameter": 10.0,
                "point": [10.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
        ]
        self.curve_response = curve_response

    async def __call__(self, endpoint, method, data, *, port=None):
        if endpoint == "/director/curve-samples":
            self.calls.append((endpoint, method, data, port))
            if self.curve_response is not None:
                return self.curve_response
            return {
                "success": True,
                "data": {
                    "schema_version": 1,
                    "curve_id": data["curve_id"],
                    "frame_count": data["frame_count"],
                    "samples": self.samples,
                    "provenance": {
                        "sampling_mode": "normalized_parameter",
                        "parameter_mapping": "curve_domain_parameter_at",
                        "frame_count_source": "caller_canonical_frame_count",
                        "arc_length_sampled": False,
                        "validation_strength": "curve_parameter_sampled",
                    },
                },
            }
        return await super().__call__(endpoint, method, data, port=port)
```

- [ ] **Step 2: Add success test with UUID curve id and no view-state call**

```python
@pytest.mark.asyncio
async def test_curve_follow_target_samples_curve_and_emits_camera_frames():
    curve_id = "00000000-0000-0000-0000-000000000001"
    native = FakeCurveNative()

    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": curve_id,
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            }
        },
        frame_count=3,
        resolution={"width": 1280, "height": 720},
        call_native=native,
        port=12345,
    )

    assert result["strategy"] == "curve_follow_target"
    assert result["provenance"]["request_shape"] == "camera_strategy"
    assert result["provenance"]["curve_id"] == curve_id
    assert result["provenance"]["curve_sampling"]["parameter_mapping"] == "curve_domain_parameter_at"
    assert result["provenance"]["optics_authority"] == "lens_length"
    assert [frame["location"] for frame in result["frames"]] == [
        [0.0, -10.0, 5.0],
        [5.0, -10.0, 5.0],
        [10.0, -10.0, 5.0],
    ]
    assert all(frame["target"] == [0.0, 0.0, 0.0] for frame in result["frames"])
    assert all(frame["projection"] == "perspective" for frame in result["frames"])
    assert all(frame["aspect"] == pytest.approx(1280 / 720) for frame in result["frames"])
    assert [call[0] for call in native.calls] == ["/director/curve-samples"]
    assert native.calls[0] == (
        "/director/curve-samples",
        "POST",
        {
            "curve_id": curve_id,
            "frame_count": 3,
            "sampling": {
                "mode": "normalized_parameter",
                "start": 0.0,
                "end": 1.0,
            },
        },
        12345,
    )
```

- [ ] **Step 3: Add authoring validation tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("camera", "message"),
    [
        ({}, "curve_id"),
        ({"curve_id": "not-a-uuid"}, "curve_id"),
        ({"curve_id": "00000000-0000-0000-0000-000000000001"}, "target"),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [True, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "target",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 0.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "up",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, True],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "up",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "arc_length", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "normalized_parameter",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": True, "end": 1.0},
                "lens_length": 35.0,
            },
            "sampling",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.8, "end": 0.2},
                "lens_length": 35.0,
            },
            "sampling",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
            },
            "lens_length or fov_degrees",
        ),
    ],
)
async def test_curve_follow_target_rejects_invalid_authoring(camera, message):
    camera["strategy"] = "curve_follow_target"
    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {"camera": camera},
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(),
            port=None,
        )
```

- [ ] **Step 4: Add optics authority tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("optics", "authority", "expected_lens", "expected_fov"),
    [
        ({"lens_length": 35.0}, "lens_length", 35.0, None),
        ({"fov_degrees": 45.0}, "fov_degrees", None, 45.0),
        ({"lens_length": 35.0, "fov_degrees": 45.0}, "lens_length", 35.0, 45.0),
    ],
)
async def test_curve_follow_target_records_optics_authority(optics, authority, expected_lens, expected_fov):
    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                **optics,
            }
        },
        frame_count=3,
        resolution={"width": 640, "height": 360},
        call_native=FakeCurveNative(),
        port=None,
    )

    assert result["provenance"]["optics_authority"] == authority
    assert result["frames"][0]["lens_length"] == expected_lens
    assert result["frames"][0]["fov_degrees"] == expected_fov
```

- [ ] **Step 5: Add native failure parsing and strict sample indexing tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("curve_response", "message"),
    [
        ({"success": False, "data": {"code": "curve_not_found", "message": "missing"}}, "curve_not_found"),
        ({"success": False, "data": {"error": {"code": "not_curve", "message": "not curve"}}}, "not_curve"),
        ({"success": False, "data": "plain failure"}, "plain failure"),
        ({"success": False, "data": None}, "curve sample resolution failed"),
    ],
)
async def test_curve_follow_target_reports_native_failure_shapes(curve_response, message):
    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                    "lens_length": 35.0,
                }
            },
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(curve_response=curve_response),
            port=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("samples", "message"),
    [
        ([{"frame_index": 1, "point": [0.0, -10.0, 5.0]}], "missing"),
        (
            [
                {"frame_index": 1, "point": [0.0, -10.0, 5.0]},
                {"frame_index": 1, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 2, "point": [2.0, -10.0, 5.0]},
            ],
            "duplicate",
        ),
        (
            [
                {"frame_index": 1, "point": [0.0, -10.0, 5.0]},
                {"frame_index": 2, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 4, "point": [2.0, -10.0, 5.0]},
            ],
            "frame_index",
        ),
        ([None, {"frame_index": 2, "point": [1.0, -10.0, 5.0]}, {"frame_index": 3, "point": [2.0, -10.0, 5.0]}], "sample"),
        (
            [
                {"frame_index": 1, "point": [True, -10.0, 5.0]},
                {"frame_index": 2, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 3, "point": [2.0, -10.0, 5.0]},
            ],
            "point",
        ),
    ],
)
async def test_curve_follow_target_rejects_bad_curve_samples(samples, message):
    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                    "lens_length": 35.0,
                }
            },
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(samples=samples),
            port=None,
        )
```

- [ ] **Step 6: Add direction and up-parallel tests**

```python
@pytest.mark.asyncio
async def test_curve_follow_target_rejects_sample_at_target():
    with pytest.raises(camera_planner.CameraPlanError, match="location and target"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                    "lens_length": 35.0,
                }
            },
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(samples=[{"frame_index": 1, "point": [0.0, 0.0, 0.0]}]),
            port=None,
        )


@pytest.mark.asyncio
async def test_curve_follow_target_rejects_up_parallel_to_view_direction():
    with pytest.raises(camera_planner.CameraPlanError, match="parallel"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                    "lens_length": 35.0,
                }
            },
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(samples=[{"frame_index": 1, "point": [0.0, 0.0, 10.0]}]),
            port=None,
        )
```

- [ ] **Step 7: Run tests and verify red**

Run:

```powershell
python -m pytest mcp_server/tests/test_camera_planner.py -q
```

Expected before implementation: new curve-follow tests fail because
`camera.strategy` still only accepts `keyframes`.

---

### Task 2: Camera Planner Implementation

**Files:**
- Modify: `mcp_server/src/rook/camera_planner.py`
- Test: `mcp_server/tests/test_camera_planner.py`

- [ ] **Step 1: Add imports and numeric helpers**

Add `uuid`. Keep legacy keyframe numeric-string coercion intact, but reject
booleans explicitly. Add a stricter helper only for curve-follow authoring and
native sample validation:

```python
import uuid
```

```python
def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _strict_float(value: Any) -> float | None:
    if isinstance(value, bool) or type(value) not in (int, float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _finite_positive(value: Any) -> float | None:
    result = _coerce_float(value)
    if result is None or result <= 0:
        return None
    return result


def _valid_fov(value: Any) -> float | None:
    result = _coerce_float(value)
    if result is None or result <= 0 or result >= 180:
        return None
    return result


def _point3(camera: dict[str, Any], field: str) -> list[float]:
    value = camera.get(field)
    if not isinstance(value, list) or len(value) != 3:
        raise CameraPlanError(f"camera.{field} must be a 3-number array")
    values = [_coerce_float(item) for item in value]
    if any(item is None for item in values):
        raise CameraPlanError(f"camera.{field} must be a 3-number array")
    return [float(item) for item in values]


def _strict_point3(value: Any, message: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise CameraPlanError(message)
    values = [_strict_float(item) for item in value]
    if any(item is None for item in values):
        raise CameraPlanError(message)
    return [float(item) for item in values]
```

Use `_coerce_float()`, `_finite_positive()`, `_valid_fov()`, and `_point3()` for
existing keyframe paths so numeric strings continue to work while booleans do
not. Use `_strict_float()` and `_strict_point3()` only for
`curve_follow_target` authoring fields and native curve samples.

- [ ] **Step 2: Make `normalize_camera_request()` strategy-aware**

Replace the top-level camera branch with:

```python
if isinstance(request.get("camera"), dict):
    camera_request = dict(request["camera"])
    strategy = camera_request.get("strategy")
    if strategy == "keyframes":
        if not isinstance(camera_request.get("keyframes"), list) or not camera_request["keyframes"]:
            raise CameraPlanError("camera.keyframes must be a non-empty array")
        return camera_request, "camera_strategy"
    if strategy == "curve_follow_target":
        return camera_request, "camera_strategy"
    raise CameraPlanError("camera.strategy must be keyframes or curve_follow_target for this slice")
```

Do not change the legacy `camera_keyframes` branch.

- [ ] **Step 3: Add native-free curve-follow validation**

Add:

```python
def _validated_uuid_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CameraPlanError(f"camera.{field} must be a Rhino curve object UUID string")
    try:
        uuid.UUID(value.strip())
    except ValueError as ex:
        raise CameraPlanError(f"camera.{field} must be a Rhino curve object UUID string") from ex
    return value.strip()


def _validated_sampling(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CameraPlanError("camera.sampling is required")
    if value.get("mode") != "normalized_parameter":
        raise CameraPlanError("camera.sampling.mode must be normalized_parameter")
    start = _strict_float(value.get("start"))
    end = _strict_float(value.get("end"))
    if start is None or end is None:
        raise CameraPlanError("camera.sampling start and end must be finite numbers")
    if start < 0.0 or start > 1.0 or end < 0.0 or end > 1.0:
        raise CameraPlanError("camera.sampling start and end must be in 0..1")
    if end < start:
        raise CameraPlanError("camera.sampling end must be greater than or equal to start")
    return {"mode": "normalized_parameter", "start": start, "end": end}


def _validate_curve_follow_request(camera_request: dict[str, Any], *, aspect: float) -> dict[str, Any]:
    curve_id = _validated_uuid_string(camera_request.get("curve_id"), "curve_id")
    target = _strict_point3(
        camera_request.get("target"),
        "camera.target must be a finite 3-number array",
    )
    up = _normalize(
        _strict_point3(
            camera_request.get("up"),
            "camera.up must be a finite 3-number array",
        )
    )
    if up is None:
        raise CameraPlanError("camera up vector became degenerate")
    sampling = _validated_sampling(camera_request.get("sampling"))
    lens_length = _optional_lens_length(camera_request)
    fov_degrees = _optional_fov_degrees(camera_request)
    if lens_length is None and fov_degrees is None:
        raise CameraPlanError("perspective camera requires lens_length or fov_degrees")
    return {
        "strategy": "curve_follow_target",
        "curve_id": curve_id,
        "target": target,
        "up": up,
        "sampling": sampling,
        "lens_length": lens_length,
        "fov_degrees": fov_degrees,
        "aspect": aspect,
        "optics_authority": "lens_length" if lens_length is not None else "fov_degrees",
    }
```

- [ ] **Step 4: Make `validate_camera_request()` strategy-aware**

Update it so `curve_follow_target` validates without native calls:

```python
def validate_camera_request(
    request: dict[str, Any],
    *,
    frame_count: int,
    resolution: dict[str, int],
) -> dict[str, Any]:
    aspect = _aspect_from_resolution(resolution)
    camera_request, request_shape = normalize_camera_request(request)
    if camera_request.get("strategy") == "curve_follow_target":
        validated_curve = _validate_curve_follow_request(camera_request, aspect=aspect)
        validated_curve["request_shape"] = request_shape
        return validated_curve
    keyframes = _validated_keyframes(camera_request, frame_count)
    return {
        "strategy": "keyframes",
        "request_shape": request_shape,
        "keyframes": keyframes,
    }
```

Update all direct callers and tests so `resolution` is supplied. This keeps the
fail-fast path native-free while using the same aspect calculation as final
camera resolution.

- [ ] **Step 5: Add strict sample and native-error helpers**

Add:

```python
def _native_error_message(data: Any) -> str:
    if isinstance(data, dict):
        nested = data.get("error")
        if isinstance(nested, dict):
            return str(nested.get("code") or nested.get("message") or nested)
        return str(data.get("code") or data.get("message") or data)
    if data is None:
        return "curve sample resolution failed"
    return str(data)


def _sample_point(sample: dict[str, Any]) -> list[float]:
    return _strict_point3(
        sample.get("point"),
        "curve sample point must be a finite 3-number array",
    )


def _indexed_curve_samples(samples: Any, *, frame_count: int) -> dict[int, dict[str, Any]]:
    if not isinstance(samples, list):
        raise CameraPlanError("curve sample response samples must be an array")
    indexed: dict[int, dict[str, Any]] = {}
    for sample in samples:
        if not isinstance(sample, dict):
            raise CameraPlanError("curve sample entries must be objects")
        frame_index = sample.get("frame_index")
        if isinstance(frame_index, bool) or type(frame_index) is not int:
            raise CameraPlanError("curve sample frame_index must be an integer")
        if frame_index < 1 or frame_index > frame_count:
            raise CameraPlanError("curve sample frame_index must be inside 1..frame_count")
        if frame_index in indexed:
            raise CameraPlanError("curve sample response contains duplicate frame_index")
        _sample_point(sample)
        indexed[frame_index] = sample
    missing = [index for index in range(1, frame_count + 1) if index not in indexed]
    if missing:
        raise CameraPlanError(f"curve sample response is missing frame_index {missing[0]}")
    return indexed
```

- [ ] **Step 6: Add up/direction threshold and curve-follow resolver**

Add:

```python
def _reject_curve_follow_parallel_up(camera: dict[str, Any]) -> None:
    direction = _normalize(
        [camera["target"][i] - camera["location"][i] for i in range(3)]
    )
    if direction is None:
        raise CameraPlanError("camera location and target must differ")
    dot = abs(sum(direction[i] * camera["up"][i] for i in range(3)))
    if dot >= 0.999:
        raise CameraPlanError("curve_follow_target up vector is parallel to the view direction")


async def _resolve_curve_follow_target(
    camera_request: dict[str, Any],
    *,
    frame_count: int,
    aspect: float,
    call_native,
    port: int | None,
) -> dict[str, Any]:
    validated = _validate_curve_follow_request(camera_request, aspect=aspect)
    native_request = {
        "curve_id": validated["curve_id"],
        "frame_count": frame_count,
        "sampling": validated["sampling"],
    }
    result = await call_native(
        "/director/curve-samples", "POST", native_request, port=port
    )
    if not result.get("success"):
        raise CameraPlanError(
            f"curve sample resolution failed: {_native_error_message(result.get('data'))}"
        )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    samples = _indexed_curve_samples(data.get("samples"), frame_count=frame_count)

    frames = []
    for frame_index in range(1, frame_count + 1):
        sample = samples[frame_index]
        camera = {
            "projection": "perspective",
            "location": _sample_point(sample),
            "target": validated["target"],
            "up": validated["up"],
            "lens_length": validated["lens_length"],
            "fov_degrees": validated["fov_degrees"],
            "aspect": aspect,
        }
        _reject_curve_follow_parallel_up(camera)
        frames.append(_validate_resolved_camera(camera, aspect=aspect))

    return {
        "strategy": "curve_follow_target",
        "frames": frames,
        "provenance": {
            "request_shape": "camera_strategy",
            "curve_id": validated["curve_id"],
            "target": validated["target"],
            "up": validated["up"],
            "sampling": validated["sampling"],
            "curve_sampling": data.get("provenance", {}),
            "aspect_authority": "output_resolution",
            "optics_authority": validated["optics_authority"],
        },
    }
```

- [ ] **Step 7: Route `resolve_camera_plan()` by strategy**

At the top of `resolve_camera_plan()`, after computing `aspect` and validating
the camera request:

```python
validated = validate_camera_request(
    request,
    frame_count=frame_count,
    resolution=resolution,
)
if validated["strategy"] == "curve_follow_target":
    return await _resolve_curve_follow_target(
        request["camera"],
        frame_count=frame_count,
        aspect=aspect,
        call_native=call_native,
        port=port,
    )
```

Keep the existing keyframe resolution path for `validated["strategy"] ==
"keyframes"`.

- [ ] **Step 8: Run camera planner tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_camera_planner.py -q
```

Expected: all camera planner tests pass.

---

### Task 3: Director Orchestration And Manifest Tests

**Files:**
- Modify: `mcp_server/tests/test_director.py`
- Modify: `mcp_server/src/rook/director.py`

- [ ] **Step 1: Extend `FakeNative` with curve samples**

In `mcp_server/tests/test_director.py`, extend `FakeNative.__call__`:

```python
if endpoint == "/director/curve-samples":
    return {
        "success": True,
        "data": {
            "schema_version": 1,
            "curve_id": data["curve_id"],
            "frame_count": data["frame_count"],
            "samples": [
                {
                    "frame_index": index,
                    "normalized_parameter": 0.0 if data["frame_count"] == 1 else (index - 1) / (data["frame_count"] - 1),
                    "curve_parameter": float(index),
                    "point": [float(index), -10.0, 5.0],
                    "tangent": [1.0, 0.0, 0.0],
                }
                for index in range(1, data["frame_count"] + 1)
            ],
            "provenance": {
                "sampling_mode": "normalized_parameter",
                "parameter_mapping": "curve_domain_parameter_at",
                "frame_count_source": "caller_canonical_frame_count",
                "arc_length_sampled": False,
                "validation_strength": "curve_parameter_sampled",
            },
        },
    }
```

- [ ] **Step 2: Add fail-fast validation test**

```python
@pytest.mark.asyncio
async def test_director_rejects_invalid_curve_follow_before_object_resolution(tmp_path):
    native = FakeNative([], create_outputs=True)
    allowed_root = tmp_path / "data" / "rookvision_director"

    with pytest.raises(director.DirectorInputError, match="curve_id"):
        await director.run_director(
            {
                "object_ids": ["a"],
                "frame_count": 1,
                "resolution": {"width": 320, "height": 180},
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "not-a-uuid",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {
                        "mode": "normalized_parameter",
                        "start": 0.0,
                        "end": 1.0,
                    },
                    "lens_length": 35.0,
                },
                "output_root": str(allowed_root),
            },
            call_native=native,
            runtime=_runtime(tmp_path),
        )

    assert not any(call[0] == "/director/object-states" for call in native.calls)
```

- [ ] **Step 3: Add manifest and native call sequence test**

```python
@pytest.mark.asyncio
async def test_director_curve_follow_target_writes_strategy_manifest_and_frame_cameras(tmp_path):
    native = FakeNative([], create_outputs=True)
    curve_id = "00000000-0000-0000-0000-000000000001"
    allowed_root = tmp_path / "data" / "rookvision_director"

    result = await director.run_director(
        {
            "object_ids": ["a"],
            "timeline": {"fps": 24, "duration_seconds": 0.125},
            "resolution": {"width": 320, "height": 180},
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": curve_id,
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            },
            "output_root": str(allowed_root),
        },
        call_native=native,
        runtime=_runtime(tmp_path),
    )

    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["camera_plan"]["strategy"] == "curve_follow_target"
    assert manifest["camera_plan"]["request_shape"] == "camera_strategy"
    assert manifest["camera_plan"]["aspect_authority"] == "output_resolution"
    assert manifest["camera_plan"]["optics_authority"] == "lens_length"
    assert manifest["camera_plan"]["provenance"]["curve_id"] == curve_id
    assert manifest["camera_plan"]["provenance"]["curve_sampling"]["parameter_mapping"] == "curve_domain_parameter_at"
    assert manifest["camera_keyframes"] == []
    assert manifest["camera_keyframe_provenance"] == []
    assert all(frame["camera"]["projection"] == "perspective" for frame in manifest["frames"])

    endpoints = [call[0] for call in native.calls]
    assert "/director/view-state" not in endpoints
    assert endpoints.count("/director/curve-samples") == 1
    assert endpoints.count("/director/frame-capture") == manifest["frame_count"]
```

- [ ] **Step 4: Run Director tests and verify red**

Run:

```powershell
python -m pytest mcp_server/tests/test_director.py -q
```

Expected before implementation: new tests fail because curve-follow planning is
not implemented and manifest writing assumes keyframe provenance.

- [ ] **Step 5: Make `director.py` pass resolution to fail-fast validation**

Find the early validation before object resolution and update it so camera
validation has the request resolution:

```python
camera_planner.validate_camera_request(
    request,
    frame_count=frame_count,
    resolution=request["resolution"],
)
```

Wrap `CameraPlanError` as the existing `DirectorInputError` path already does.

- [ ] **Step 6: Make manifest writing strategy-aware**

When building the manifest, replace direct assumptions about
`camera_plan["provenance"]["keyframes"]` with strategy-aware fields:

```python
plan_provenance = camera_plan.get("provenance", {})
manifest_camera_plan = {
    "strategy": camera_plan["strategy"],
    "request_shape": plan_provenance.get("request_shape"),
    "aspect_authority": plan_provenance.get("aspect_authority"),
    "optics_authority": plan_provenance.get("optics_authority"),
}
if camera_plan["strategy"] == "curve_follow_target":
    manifest_camera_plan["provenance"] = {
        "curve_id": plan_provenance["curve_id"],
        "target": plan_provenance["target"],
        "up": plan_provenance["up"],
        "sampling": plan_provenance["sampling"],
        "curve_sampling": plan_provenance.get("curve_sampling", {}),
    }

if camera_plan["strategy"] == "keyframes":
    keyframe_provenance = plan_provenance.get("keyframes", [])
    camera_keyframes = [
        {"frame_index": item["frame_index"], "source": item["source"]}
        for item in keyframe_provenance
    ]
    camera_keyframe_provenance = [
        {"frame_index": item["frame_index"], "provenance": item.get("provenance")}
        for item in keyframe_provenance
    ]
else:
    camera_keyframes = []
    camera_keyframe_provenance = []
```

Use these variables in the manifest. Preserve the existing keyframe output shape:
do not move `request_shape`, `aspect_authority`, or `optics_authority` under a
nested object for keyframes.

- [ ] **Step 7: Run Director and planner tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_camera_planner.py mcp_server/tests/test_director.py -q
```

Expected: all selected tests pass.

---

### Task 4: MCP Schema Tests And Schema Update

**Files:**
- Modify: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add schema assertions**

Extend `test_director_tool_registered`:

```python
camera_request_schema = schema["properties"]["camera"]
assert camera_request_schema["required"] == ["strategy"]
assert "curve_follow_target" in camera_request_schema["properties"]["strategy"]["description"]
assert "curve_id" in camera_request_schema["properties"]
assert "Rhino curve object UUID" in camera_request_schema["properties"]["curve_id"]["description"]
assert "not a name" in camera_request_schema["properties"]["curve_id"]["description"]
assert "target" in camera_request_schema["properties"]
assert "numeric" in camera_request_schema["properties"]["target"]["description"]
assert "not an object" in camera_request_schema["properties"]["target"]["description"]
assert "sampling" in camera_request_schema["properties"]
assert "lens_length" in camera_request_schema["properties"]
assert "fov_degrees" in camera_request_schema["properties"]
```

Keep `_find_rejected_schema_keywords(schema) == []`.

- [ ] **Step 2: Run MCP schema test and verify red**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py::test_director_tool_registered -q
```

Expected before schema update: fails because `camera.required` still includes
`keyframes` and curve-follow fields are absent.

- [ ] **Step 3: Update `rhino_director_run` schema**

In `mcp_server/src/rook/server.py`, change the `camera` schema:

```python
"camera": {
    "type": "object",
    "required": ["strategy"],
    "additionalProperties": True,
    "description": (
        "Camera planning request. strategy may be keyframes or "
        "curve_follow_target. Runtime validation enforces "
        "strategy-specific required fields."
    ),
    "properties": {
        "strategy": {
            "type": "string",
            "description": "Camera strategy: keyframes or curve_follow_target.",
        },
        "keyframes": {
            "type": "array",
            "items": {"type": "object"},
            "minItems": 1,
            "description": "Camera keyframes using the same shape as camera_keyframes.",
        },
        "curve_id": {
            "type": "string",
            "description": "Rhino curve object UUID string for curve_follow_target; not a name lookup.",
        },
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
            "description": "Numeric [x, y, z] target point for curve_follow_target; not an object id or name.",
        },
        "up": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
            "description": "Numeric 3-vector up direction for curve_follow_target.",
        },
        "sampling": {
            "type": "object",
            "required": ["mode", "start", "end"],
            "additionalProperties": True,
            "description": "Curve sampling for curve_follow_target. v1 supports normalized_parameter only.",
            "properties": {
                "mode": {"type": "string", "description": "Use normalized_parameter for v1."},
                "start": {"type": "number", "minimum": 0, "maximum": 1},
                "end": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "lens_length": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Perspective lens length. Authoritative when supplied.",
        },
        "fov_degrees": {
            "type": "number",
            "exclusiveMinimum": 0,
            "exclusiveMaximum": 180,
            "description": "Perspective FOV in degrees. Used only when lens_length is absent.",
        },
    },
}
```

Do not use `oneOf`, `anyOf`, `allOf`, or `not`.

- [ ] **Step 4: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: all Director MCP tests pass.

---

### Task 5: Optional Guarded Live Smoke

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py` only if existing helpers make this small.

- [ ] **Step 1: Inspect live-test helper availability**

Check whether `test_director_routes_live.py` already has helper functions for
finding fixture objects by name and returning UUIDs. If there is no existing
helper path, skip live-smoke edits in this slice and document that non-live tests
cover the strategy.

- [ ] **Step 2: Add guarded smoke only if no new lookup path is needed**

If existing helpers can resolve a fixture named `RVD_CameraPath_01` to UUID, add
a guarded `requires_rhino` test that:

```python
curve_id = _find_fixture_object_id("RVD_CameraPath_01")
if curve_id is None:
    pytest.skip("RVD_CameraPath_01 fixture curve is not present")
```

The request must send:

```python
"camera": {
    "strategy": "curve_follow_target",
    "curve_id": curve_id,
    "target": [0.0, 0.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
    "lens_length": 35.0,
}
```

Do not add a production target or curve name lookup path.

- [ ] **Step 3: Run guarded live tests when Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_director_routes_live.py -q
```

Expected: the new smoke either skips due to absent fixture or passes. Do not
claim live verification unless Rhino actually runs the test.

---

### Task 6: Final Verification

**Files:**
- Modify only files touched above if verification exposes defects.

- [ ] **Step 1: Run focused non-live tests**

```powershell
python -m pytest mcp_server/tests/test_timeline.py mcp_server/tests/test_camera_planner.py mcp_server/tests/test_director.py mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run diff hygiene**

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Check scope**

Run:

```powershell
git diff --name-only
```

Expected changed files are limited to:

```text
mcp_server/src/rook/camera_planner.py
mcp_server/src/rook/timeline.py
mcp_server/src/rook/director.py
mcp_server/src/rook/server.py
mcp_server/tests/test_camera_planner.py
mcp_server/tests/test_timeline.py
mcp_server/tests/test_director.py
mcp_server/tests/test_director_mcp_tools.py
mcp_server/tests/test_director_routes_live.py
```

If any `src/RookNative/**` or `src/Rook/**/*.cs` files changed, stop and re-check
scope before proceeding.

## Review Checklist

- `target` is numeric-only and schema text does not imply ids or names are accepted.
- `curve_id` validates as a UUID string before native calls.
- Timeline normalization leaves `camera.strategy == "curve_follow_target"` unchanged instead of requiring `camera.keyframes`.
- Existing keyframe numeric-string coercion remains supported while booleans are rejected.
- `validate_camera_request()` stays native-free.
- Invalid curve-follow authoring fails before `/director/object-states`.
- `curve_follow_target` calls `/director/curve-samples` once and never calls `/director/view-state`.
- Sample validation requires exactly one sample for every frame index.
- Native response tests use `normalized_parameter` and `curve_parameter`.
- Native provenance is preserved in full under `camera_plan.provenance.curve_sampling`.
- `camera_plan` keeps current keyframe top-level fields stable.
- Non-keyframe manifests write `camera_keyframes: []` and `camera_keyframe_provenance: []`.
- `manifest.frames[*].camera` remains the frame-capture contract.
- `camera.required == ["strategy"]`.
- The MCP schema remains free of `oneOf`, `anyOf`, `allOf`, and `not`.
- No native, managed, video assembly, artifact, gallery, or publishing behavior changed.
