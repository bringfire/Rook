# RookVisionDirector Curve-Follow Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Python-owned `curve_follow_target` camera strategy that samples a Rhino curve and emits the same explicit per-frame camera objects consumed by the existing Director frame-capture path.

**Architecture:** Python remains the camera-planning owner. The new strategy calls the existing native `/director/curve-samples` read-only primitive, treats each sample point as the camera location, uses a fixed target point, validates every resolved perspective camera through the existing camera validation path, and leaves native `/director/frame-capture` and video assembly unchanged.

**Tech Stack:** Python MCP server, pytest, existing `camera_planner.py`, existing `timeline.py`, native `/director/curve-samples`, existing `rhino_director_run` MCP schema.

---

## Constraints

- Do not change `/director/frame-capture`.
- Do not change `/director/video-assemble` or `rhino_director_assemble_video`.
- Do not add artifact-store, gallery, or RookVision publishing behavior.
- Do not add true arc-length sampling; v1 consumes existing
  `normalized_parameter` curve samples only.
- Do not support parallel cameras in this slice.
- Preserve legacy `camera_keyframes` and `camera.strategy == "keyframes"` request
  compatibility.
- Keep the native curve-sampling route read-only.
- Keep `aspect` authority from output resolution.

## File Structure

- Modify `mcp_server/src/rook/camera_planner.py`
  Add `curve_follow_target` request validation, native curve-sample dispatch,
  per-sample camera construction, and provenance.
- Modify `mcp_server/src/rook/server.py`
  Extend the `rhino_director_run` MCP schema description and camera object
  properties so clients can author `curve_follow_target` without schema
  composition keywords.
- Modify `mcp_server/tests/test_camera_planner.py`
  Add unit tests for successful curve-follow planning, invalid inputs, native
  failure propagation, and no regression to keyframe planning.
- Modify `mcp_server/tests/test_director_mcp_tools.py`
  Add schema coverage for the new camera strategy fields.
- Modify `mcp_server/tests/test_director.py`
  Add Director orchestration coverage proving `rhino_director_run` forwards the
  new camera strategy into frame instructions without changing frame capture.
- Modify `mcp_server/tests/test_director_routes_live.py`
  Add a guarded live smoke that runs curve-follow planning when a fixture curve
  and target are available.

---

### Task 1: Camera Planner Unit Tests

**Files:**
- Modify: `mcp_server/tests/test_camera_planner.py`
- Read: `mcp_server/src/rook/camera_planner.py`

- [ ] **Step 1: Add a fake native that supports curve samples**

Add this helper near the existing `FakeNative` helper:

```python
class FakeCurveNative(FakeNative):
    def __init__(self, cameras=None, *, samples=None, curve_success=True):
        super().__init__(cameras or [])
        self.samples = samples or [
            {
                "frame_index": 1,
                "parameter": 0.0,
                "point": [0.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
            {
                "frame_index": 2,
                "parameter": 0.5,
                "point": [5.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
            {
                "frame_index": 3,
                "parameter": 1.0,
                "point": [10.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
        ]
        self.curve_success = curve_success

    async def __call__(self, endpoint, method, data, *, port=None):
        if endpoint == "/director/curve-samples":
            self.calls.append((endpoint, method, data, port))
            if not self.curve_success:
                return {
                    "success": False,
                    "data": {
                        "error": {
                            "code": "curve_not_found",
                            "message": "curve was not found",
                        }
                    },
                }
            return {
                "success": True,
                "data": {
                    "schema_version": 1,
                    "curve_id": data["curve_id"],
                    "frame_count": data["frame_count"],
                    "samples": self.samples,
                    "provenance": {
                        "sampling_mode": "normalized_parameter",
                        "validation_strength": "curve_parameter_sampled",
                    },
                },
            }
        return await super().__call__(endpoint, method, data, port=port)
```

- [ ] **Step 2: Add the successful strategy test**

```python
@pytest.mark.asyncio
async def test_curve_follow_target_strategy_samples_curve_and_emits_camera_frames():
    native = FakeCurveNative()

    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": "curve-1",
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
    assert result["provenance"]["sampling"]["mode"] == "normalized_parameter"
    assert result["provenance"]["curve_id"] == "curve-1"
    assert [frame["location"] for frame in result["frames"]] == [
        [0.0, -10.0, 5.0],
        [5.0, -10.0, 5.0],
        [10.0, -10.0, 5.0],
    ]
    assert all(frame["target"] == [0.0, 0.0, 0.0] for frame in result["frames"])
    assert all(frame["projection"] == "perspective" for frame in result["frames"])
    assert all(frame["lens_length"] == 35.0 for frame in result["frames"])
    assert all(frame["aspect"] == pytest.approx(1280 / 720) for frame in result["frames"])
    assert native.calls[0] == (
        "/director/curve-samples",
        "POST",
        {
            "curve_id": "curve-1",
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

- [ ] **Step 3: Add validation tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("camera", "message"),
    [
        ({}, "curve_id"),
        ({"curve_id": "curve-1"}, "target"),
        (
            {
                "curve_id": "curve-1",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 0.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "up",
        ),
        (
            {
                "curve_id": "curve-1",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "arc_length", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "normalized_parameter",
        ),
        (
            {
                "curve_id": "curve-1",
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

- [ ] **Step 4: Add native failure and degenerate direction tests**

```python
@pytest.mark.asyncio
async def test_curve_follow_target_propagates_curve_sample_failure():
    with pytest.raises(camera_planner.CameraPlanError, match="curve_not_found"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "missing-curve",
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
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(curve_success=False),
            port=None,
        )


@pytest.mark.asyncio
async def test_curve_follow_target_rejects_sample_at_target():
    native = FakeCurveNative(
        samples=[
            {
                "frame_index": 1,
                "parameter": 0.0,
                "point": [0.0, 0.0, 0.0],
                "tangent": [1.0, 0.0, 0.0],
            }
        ]
    )
    with pytest.raises(camera_planner.CameraPlanError, match="location and target"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "curve-1",
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
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )
```

- [ ] **Step 5: Run the focused tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_camera_planner.py -q
```

Expected before implementation: the new `curve_follow_target` tests fail because
`camera.strategy` only accepts `keyframes`.

---

### Task 2: Camera Planner Implementation

**Files:**
- Modify: `mcp_server/src/rook/camera_planner.py`
- Test: `mcp_server/tests/test_camera_planner.py`

- [ ] **Step 1: Extend strategy normalization**

Replace the `normalize_camera_request` strategy check with a branch that accepts
`keyframes` and `curve_follow_target`:

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

- [ ] **Step 2: Add curve-follow request validation helpers**

Add helpers that reuse `_point3`, `_normalize`, `_optional_lens_length`,
`_optional_fov_degrees`, and `_validate_resolved_camera`:

```python
def _validated_sampling(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CameraPlanError("camera.sampling is required")
    if value.get("mode") != "normalized_parameter":
        raise CameraPlanError("camera.sampling.mode must be normalized_parameter")
    try:
        start = float(value.get("start"))
        end = float(value.get("end"))
    except (TypeError, ValueError) as ex:
        raise CameraPlanError("camera.sampling start and end must be numbers") from ex
    if not math.isfinite(start) or not math.isfinite(end):
        raise CameraPlanError("camera.sampling start and end must be finite")
    if start < 0.0 or start > 1.0 or end < 0.0 or end > 1.0:
        raise CameraPlanError("camera.sampling start and end must be in 0..1")
    if end < start:
        raise CameraPlanError("camera.sampling end must be greater than or equal to start")
    return {"mode": "normalized_parameter", "start": start, "end": end}


def _validate_curve_follow_request(camera_request: dict[str, Any], *, aspect: float) -> dict[str, Any]:
    curve_id = camera_request.get("curve_id")
    if not isinstance(curve_id, str) or not curve_id.strip():
        raise CameraPlanError("camera.curve_id is required")
    target = _point3(camera_request, "target")
    up = _normalize(_point3(camera_request, "up"))
    if up is None:
        raise CameraPlanError("camera up vector became degenerate")
    sampling = _validated_sampling(camera_request.get("sampling"))
    lens_length = _optional_lens_length(camera_request)
    fov_degrees = _optional_fov_degrees(camera_request)
    if lens_length is None and fov_degrees is None:
        raise CameraPlanError("perspective camera requires lens_length or fov_degrees")
    return {
        "strategy": "curve_follow_target",
        "curve_id": curve_id.strip(),
        "target": target,
        "up": up,
        "sampling": sampling,
        "lens_length": lens_length,
        "fov_degrees": fov_degrees,
        "aspect": aspect,
    }
```

- [ ] **Step 3: Add curve sample dispatch and camera construction**

Add:

```python
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
        data = result.get("data")
        code = None
        if isinstance(data, dict):
            error = data.get("error") if isinstance(data.get("error"), dict) else data
            code = error.get("code") if isinstance(error, dict) else None
        raise CameraPlanError(f"curve sample resolution failed: {code or data}")

    samples = result.get("data", {}).get("samples")
    if not isinstance(samples, list) or len(samples) != frame_count:
        raise CameraPlanError("curve sample response must contain one sample per frame")

    frames = []
    for sample in sorted(samples, key=lambda item: int(item.get("frame_index", 0))):
        camera = {
            "projection": "perspective",
            "location": _point3({"location": sample.get("point")}, "location"),
            "target": validated["target"],
            "up": validated["up"],
            "lens_length": validated["lens_length"],
            "fov_degrees": validated["fov_degrees"],
            "aspect": aspect,
        }
        frames.append(_validate_resolved_camera(camera, aspect=aspect))

    return {
        "strategy": "curve_follow_target",
        "frames": frames,
        "provenance": {
            "request_shape": "camera_strategy",
            "curve_id": validated["curve_id"],
            "sampling": validated["sampling"],
            "curve_sampling": result.get("data", {}).get("provenance", {}),
            "aspect_authority": "output_resolution",
            "optics_authority": "lens_length"
            if validated["lens_length"] is not None
            else "fov_degrees",
        },
    }
```

- [ ] **Step 4: Route `resolve_camera_plan` by strategy**

In `resolve_camera_plan`, branch after `camera_request, request_shape =
normalize_camera_request(request)`:

```python
if camera_request.get("strategy") == "curve_follow_target":
    return await _resolve_curve_follow_target(
        camera_request,
        frame_count=frame_count,
        aspect=aspect,
        call_native=call_native,
        port=port,
    )
```

Keep the existing keyframe path unchanged after that branch.

- [ ] **Step 5: Run camera planner tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_camera_planner.py -q
```

Expected after implementation: all tests pass.

---

### Task 3: MCP Schema And Dispatch Coverage

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Add schema assertions**

Extend `test_director_tool_registered` with assertions that the `camera`
schema describes `curve_follow_target`, `curve_id`, `target`, `up`, `sampling`,
`lens_length`, and `fov_degrees`, and still has no rejected schema keywords.

- [ ] **Step 2: Extend the `rhino_director_run` schema**

In `server.py`, update the camera property description and properties without
using `oneOf`, `anyOf`, `allOf`, or `not`. The schema remains permissive enough
for both strategies, while runtime validation owns exact requirements.

- [ ] **Step 3: Run MCP schema tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: all Director MCP tests pass and rejected schema keyword scan remains
empty.

---

### Task 4: Director Orchestration Regression

**Files:**
- Modify: `mcp_server/tests/test_director.py`

- [ ] **Step 1: Add a Director run test using `curve_follow_target`**

Extend the existing `FakeNative` in `test_director.py` so it returns
`/director/curve-samples` samples, then add a test that runs
`director.run_director` with:

```python
{
    "object_ids": ["a"],
    "timeline": {"fps": 24, "duration_seconds": 0.125},
    "resolution": {"width": 320, "height": 180},
    "camera": {
        "strategy": "curve_follow_target",
        "curve_id": "curve-1",
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        "lens_length": 35.0,
    },
}
```

Assert that frame capture requests contain explicit per-frame camera objects and
that the manifest records `camera_plan.strategy == "curve_follow_target"`.

- [ ] **Step 2: Run Director orchestration tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director.py mcp_server/tests/test_camera_planner.py -q
```

Expected: all tests pass.

---

### Task 5: Guarded Live Smoke

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add a live smoke gated on fixture names**

Add a `requires_rhino` test that looks for a named curve fixture such as
`RVD_CameraPath_01` plus the existing `RVD_TestPart_###` objects. If the fixture
curve is absent, skip with a clear message. If present, run a short timeline
request with `curve_follow_target`, then assemble video with
`rhino_director_assemble_video`.

- [ ] **Step 2: Run guarded live tests when Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_director_routes_live.py -q
```

Expected: the new smoke either skips because the fixture curve is absent or
passes with a completed frame run and assembled MP4.

---

### Task 6: Final Verification

**Files:**
- Potentially modify only files touched by prior tasks if verification reveals defects.

- [ ] **Step 1: Run focused non-live tests**

```powershell
python -m pytest mcp_server/tests/test_camera_planner.py mcp_server/tests/test_director.py mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run diff hygiene**

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Build native only if native files changed**

This slice should not require native code changes. If native files changed, stop
and re-check scope before building.

## Review Checklist

- `camera_keyframes` and `camera.strategy == "keyframes"` still work.
- `curve_follow_target` calls `/director/curve-samples` exactly once per plan.
- The planner emits one explicit perspective camera per frame.
- Aspect comes from output resolution.
- Lens length is the primary optics authority when supplied.
- Degenerate camera direction and up vector fail before frame capture.
- Frame capture and video assembly routes are unchanged.
- The MCP schema remains free of `oneOf`, `anyOf`, `allOf`, and `not`.
