# RookVisionDirector Camera Planning Contract Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract RookVisionDirector camera planning into a focused, test-covered Python contract while preserving existing slice 1 request compatibility.

**Architecture:** Python continues to own camera planning and run packaging; RookNative continues to own only Rhino evaluation/capture primitives. This slice introduces a `camera_planner` module that resolves camera requests into per-frame camera dictionaries and provenance, then wires `director.run_director` through that module without changing native `/director/frame-capture`.

**Tech Stack:** Python 3, pytest, existing `rook.director` orchestration, existing RookNative `/director/view-state` route, no new external dependencies.

---

## Source Documents

- Roadmap/spec: `docs/superpowers/specs/2026-05-20-rookvisiondirector-camera-video-roadmap.md`
- Existing slice 1 design: `docs/superpowers/specs/2026-05-19-rookvisiondirector-slice1-design.md`
- Existing slice 1 implementation: `mcp_server/src/rook/director.py`
- Existing tests: `mcp_server/tests/test_director.py`

## File Structure

Create:

- `mcp_server/src/rook/camera_planner.py`
  - Owns camera request normalization, view-state resolution, keyframe interpolation, optics/aspect authority, frame validation, and provenance.

- `mcp_server/tests/test_camera_planner.py`
  - Pure Python tests for request compatibility, strategy validation, interpolation, optics/aspect rules, provenance, and failure cases.

Modify:

- `mcp_server/src/rook/director.py`
  - Remove embedded camera helper implementations after equivalent behavior exists in `camera_planner.py`.
  - Call `camera_planner.resolve_camera_plan` from `run_director`.
  - Preserve existing `manifest.frames[*].camera` shape.
  - Add camera planning provenance to the manifest without changing per-frame camera shape.

- `mcp_server/tests/test_director.py`
  - Update existing tests only where they assert manifest camera provenance or camera validation messages that move to `camera_planner`.

Do not modify:

- `src/RookNative/Handlers/DirectorHandler.cpp`
- `src/RookNative/RookServer.cpp`
- `src/RookNative/RookNative.vcxproj`
- `src/RookNative/RookNative.vcxproj.filters`

## Contract

The new module exposes this API:

```python
def validate_camera_request(
    request: dict[str, Any],
    *,
    frame_count: int,
) -> dict[str, Any]:
    raise CameraPlanError("camera request validation is defined in Task 2")


async def resolve_camera_plan(
    request: dict[str, Any],
    *,
    frame_count: int,
    resolution: dict[str, int],
    call_native,
    port: int | None,
) -> dict[str, Any]:
    raise CameraPlanError("camera planner implementation is defined in Task 2")
```

`validate_camera_request` is non-I/O. `director.run_director` calls it before
object-state resolution so malformed camera input still fails before any native
request is made.

Return shape:

```python
{
    "strategy": "keyframes",
    "frames": [
        {
            "projection": "perspective",
            "location": [0.0, 0.0, 10.0],
            "target": [0.0, 0.0, 0.0],
            "up": [0.0, 1.0, 0.0],
            "lens_length": 35.0,
            "fov_degrees": 45.0,
            "parallel_scale": None,
            "near_clip": 0.1,
            "far_clip": 1000.0,
            "aspect": 1.777778,
        }
    ],
    "provenance": {
        "strategy": "keyframes",
        "request_shape": "legacy_camera_keyframes",
        "aspect_authority": "output_resolution",
        "optics_authority": "lens_length",
        "keyframes": [
            {
                "frame_index": 1,
                "source": {"kind": "active_view"},
                "provenance": {"source": "active_view"}
            }
        ]
    }
}
```

Existing legacy input:

```json
{
  "camera_keyframes": [
    { "frame_index": 1, "source": { "kind": "active_view" } }
  ]
}
```

is normalized to:

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

## Task 1: Add Camera Planner Failing Contract Tests

**Files:**
- Create: `mcp_server/tests/test_camera_planner.py`

- [ ] **Step 1: Create the test module with fake native helpers**

Add:

```python
from __future__ import annotations

import pytest

from rook import camera_planner


def _camera(**overrides):
    data = {
        "projection": "perspective",
        "location": [0.0, 0.0, 10.0],
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 1.0, 0.0],
        "lens_length": 35.0,
        "fov_degrees": 37.8493,
        "parallel_scale": None,
        "near_clip": 0.1,
        "far_clip": 1000.0,
        "aspect": 0.75,
    }
    data.update(overrides)
    return data


class FakeNative:
    def __init__(self, cameras):
        self.cameras = list(cameras)
        self.calls = []

    async def __call__(self, endpoint, method, data, *, port=None):
        self.calls.append((endpoint, method, data, port))
        if endpoint != "/director/view-state":
            return {"success": False, "data": {"code": "unexpected_endpoint"}}
        if not self.cameras:
            return {"success": False, "data": {"code": "no_camera"}}
        index = len(self.calls)
        return {
            "success": True,
            "data": {
                "camera": self.cameras.pop(0),
                "provenance": {
                    "source": data["source"]["kind"],
                    "call_index": index,
                },
            },
        }
```

- [ ] **Step 2: Add legacy request compatibility test**

Add:

```python
@pytest.mark.asyncio
async def test_legacy_camera_keyframes_resolve_to_keyframes_strategy():
    native = FakeNative([_camera()])
    result = await camera_planner.resolve_camera_plan(
        {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
        frame_count=3,
        resolution={"width": 1920, "height": 1080},
        call_native=native,
        port=12345,
    )

    assert result["strategy"] == "keyframes"
    assert result["provenance"]["request_shape"] == "legacy_camera_keyframes"
    assert result["provenance"]["aspect_authority"] == "output_resolution"
    assert result["provenance"]["optics_authority"] == "lens_length"
    assert len(result["frames"]) == 3
    assert result["frames"][0]["location"] == [0.0, 0.0, 10.0]
    assert result["frames"][0]["aspect"] == pytest.approx(1920 / 1080)
    assert native.calls[0] == (
        "/director/view-state",
        "POST",
        {"source": {"kind": "active_view"}},
        12345,
    )
```

- [ ] **Step 3: Add explicit strategy compatibility test**

Add:

```python
@pytest.mark.asyncio
async def test_explicit_keyframes_strategy_matches_legacy_output_frames():
    keyframes = [{"frame_index": 1, "source": {"kind": "active_view"}}]
    legacy_native = FakeNative([_camera()])
    explicit_native = FakeNative([_camera()])

    legacy = await camera_planner.resolve_camera_plan(
        {"camera_keyframes": keyframes},
        frame_count=2,
        resolution={"width": 1280, "height": 720},
        call_native=legacy_native,
        port=None,
    )
    explicit = await camera_planner.resolve_camera_plan(
        {"camera": {"strategy": "keyframes", "keyframes": keyframes}},
        frame_count=2,
        resolution={"width": 1280, "height": 720},
        call_native=explicit_native,
        port=None,
    )

    assert explicit["provenance"]["request_shape"] == "camera_strategy"
    assert explicit["frames"] == legacy["frames"]
```

- [ ] **Step 4: Add interpolation and validation tests**

Add:

```python
@pytest.mark.asyncio
async def test_keyframes_interpolate_location_target_up_and_optics():
    native = FakeNative([
        _camera(
            location=[0.0, 0.0, 10.0],
            target=[0.0, 0.0, 0.0],
            up=[0.0, 1.0, 0.0],
            lens_length=35.0,
            fov_degrees=40.0,
        ),
        _camera(
            location=[10.0, 0.0, 10.0],
            target=[0.0, 10.0, 0.0],
            up=[0.0, 1.0, 0.0],
            lens_length=55.0,
            fov_degrees=20.0,
        ),
    ])

    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"frame_index": 1, "source": {"kind": "named_view", "name": "A"}},
                    {"frame_index": 3, "source": {"kind": "named_view", "name": "B"}},
                ],
            }
        },
        frame_count=3,
        resolution={"width": 1000, "height": 500},
        call_native=native,
        port=None,
    )

    middle = result["frames"][1]
    assert middle["location"] == [5.0, 0.0, 10.0]
    assert middle["target"] == [0.0, 5.0, 0.0]
    assert middle["up"] == [0.0, 1.0, 0.0]
    assert middle["lens_length"] == pytest.approx(45.0)
    assert middle["fov_degrees"] == pytest.approx(40.0)
    assert middle["aspect"] == pytest.approx(2.0)
```

Add:

```python
@pytest.mark.asyncio
async def test_interpolated_degenerate_direction_is_rejected():
    native = FakeNative([
        _camera(location=[0.0, 0.0, 0.0], target=[10.0, 0.0, 0.0]),
        _camera(location=[10.0, 0.0, 0.0], target=[0.0, 0.0, 0.0]),
    ])

    with pytest.raises(camera_planner.CameraPlanError, match="location and target"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "keyframes",
                    "keyframes": [
                        {"frame_index": 1, "source": {"kind": "named_view", "name": "A"}},
                        {"frame_index": 3, "source": {"kind": "named_view", "name": "B"}},
                    ],
                }
            },
            frame_count=3,
            resolution={"width": 1000, "height": 500},
            call_native=native,
            port=None,
        )
```

- [ ] **Step 5: Add invalid strategy and unsupported projection tests**

Add:

```python
@pytest.mark.asyncio
async def test_unknown_camera_strategy_is_rejected():
    with pytest.raises(camera_planner.CameraPlanError, match="camera.strategy"):
        await camera_planner.resolve_camera_plan(
            {"camera": {"strategy": "curve_follow_target"}},
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeNative([]),
            port=None,
        )
```

Add:

```python
@pytest.mark.asyncio
async def test_parallel_camera_is_rejected():
    native = FakeNative([_camera(projection="parallel")])

    with pytest.raises(camera_planner.CameraPlanError, match="parallel"):
        await camera_planner.resolve_camera_plan(
            {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )
```

- [ ] **Step 6: Add optics validation tests**

Add:

```python
@pytest.mark.asyncio
async def test_perspective_camera_requires_lens_or_fov():
    native = FakeNative([_camera(lens_length=None, fov_degrees=None)])

    with pytest.raises(camera_planner.CameraPlanError, match="lens_length or fov_degrees"):
        await camera_planner.resolve_camera_plan(
            {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )
```

Add:

```python
@pytest.mark.asyncio
async def test_perspective_camera_rejects_nonpositive_lens_and_invalid_fov():
    native = FakeNative([_camera(lens_length=-1.0, fov_degrees=180.0)])

    with pytest.raises(camera_planner.CameraPlanError, match="valid lens_length or fov_degrees"):
        await camera_planner.resolve_camera_plan(
            {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )
```

- [ ] **Step 7: Run tests and verify they fail because the module does not exist**

Run:

```powershell
python -m pytest mcp_server\tests\test_camera_planner.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'rook.camera_planner'
```

## Task 2: Implement Camera Planner Module

**Files:**
- Create: `mcp_server/src/rook/camera_planner.py`

- [ ] **Step 1: Add module skeleton and public error type**

Create:

```python
from __future__ import annotations

import math
from typing import Any


class CameraPlanError(ValueError):
    pass
```

- [ ] **Step 2: Add vector helpers**

Add:

```python
def _normalize(vector: list[float]) -> list[float] | None:
    length = math.sqrt(sum(float(v) * float(v) for v in vector))
    if length < 1e-9:
        return None
    return [float(v) / length for v in vector]


def _lerp(a: float, b: float, t: float) -> float:
    return float(a) + (float(b) - float(a)) * t


def _lerp_vec(a: list[float], b: list[float], t: float) -> list[float]:
    return [_lerp(a[i], b[i], t) for i in range(3)]


def _aspect_from_resolution(resolution: dict[str, int]) -> float:
    width = int(resolution.get("width", 0))
    height = int(resolution.get("height", 0))
    if width <= 0 or height <= 0:
        raise CameraPlanError("resolution width and height must be positive")
    return width / height
```

- [ ] **Step 3: Add request normalization**

Add:

```python
def normalize_camera_request(request: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(request.get("camera"), dict):
        camera_request = dict(request["camera"])
        strategy = camera_request.get("strategy")
        if strategy != "keyframes":
            raise CameraPlanError("camera.strategy must be keyframes for this slice")
        if not isinstance(camera_request.get("keyframes"), list):
            raise CameraPlanError("camera.keyframes must be a non-empty array")
        return camera_request, "camera_strategy"

    if "camera_keyframes" in request:
        keyframes = request.get("camera_keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            raise CameraPlanError("camera_keyframes must contain at least one keyframe")
        return {"strategy": "keyframes", "keyframes": keyframes}, "legacy_camera_keyframes"

    raise CameraPlanError("camera.keyframes or camera_keyframes is required")
```

- [ ] **Step 4: Add keyframe validation**

Add:

```python
def _validate_keyframe_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict) or not source.get("kind"):
        raise CameraPlanError("camera keyframe source.kind is required")
    source_kind = source["kind"]
    if source_kind not in {"active_view", "named_view"}:
        raise CameraPlanError("camera keyframe source.kind must be active_view or named_view")
    if source_kind == "named_view" and not source.get("name"):
        raise CameraPlanError("named_view camera keyframes require source.name")
    return dict(source)


def _validated_keyframes(camera_request: dict[str, Any], frame_count: int) -> list[dict[str, Any]]:
    keyframes = camera_request.get("keyframes")
    if not isinstance(keyframes, list) or not keyframes:
        raise CameraPlanError("camera keyframes must contain at least one keyframe")

    validated = []
    for keyframe in keyframes:
        if not isinstance(keyframe, dict):
            raise CameraPlanError("camera keyframe entries must be objects")
        try:
            frame_index = int(keyframe.get("frame_index"))
        except (TypeError, ValueError) as ex:
            raise CameraPlanError("camera keyframe frame_index must be an integer") from ex
        if frame_index < 1 or frame_index > frame_count:
            raise CameraPlanError("camera keyframe frame_index must be inside 1..frame_count")
        validated.append(
            {
                "frame_index": frame_index,
                "source": _validate_keyframe_source(keyframe.get("source")),
            }
        )
    return sorted(validated, key=lambda item: item["frame_index"])


def validate_camera_request(
    request: dict[str, Any],
    *,
    frame_count: int,
) -> dict[str, Any]:
    camera_request, request_shape = normalize_camera_request(request)
    keyframes = _validated_keyframes(camera_request, frame_count)
    return {
        "strategy": "keyframes",
        "request_shape": request_shape,
        "keyframes": keyframes,
    }
```

- [ ] **Step 5: Add camera validation and authority normalization**

Add:

```python
def _validate_resolved_camera(camera: dict[str, Any], *, aspect: float) -> dict[str, Any]:
    projection = str(camera.get("projection", "")).lower()
    if projection == "parallel":
        raise CameraPlanError("parallel cameras are not supported by RookVisionDirector")
    if projection != "perspective":
        raise CameraPlanError(f"camera projection is unsupported: {projection}")

    location = [float(v) for v in camera["location"]]
    target = [float(v) for v in camera["target"]]
    up = _normalize([float(v) for v in camera["up"]])
    if up is None:
        raise CameraPlanError("camera up vector became degenerate")

    direction = _normalize([target[i] - location[i] for i in range(3)])
    if direction is None:
        raise CameraPlanError("camera location and target must differ")

    lens = camera.get("lens_length")
    fov = camera.get("fov_degrees")
    lens_value = None
    fov_value = None
    if lens is not None:
        lens_value = float(lens)
        if not math.isfinite(lens_value) or lens_value <= 0:
            lens_value = None
    if fov is not None:
        fov_value = float(fov)
        if not math.isfinite(fov_value) or fov_value <= 0 or fov_value >= 180:
            fov_value = None
    if lens_value is None and fov_value is None:
        raise CameraPlanError("perspective camera requires valid lens_length or fov_degrees")

    normalized = dict(camera)
    normalized["projection"] = "perspective"
    normalized["location"] = location
    normalized["target"] = target
    normalized["up"] = up
    normalized["lens_length"] = lens_value
    normalized["fov_degrees"] = fov_value
    normalized["aspect"] = aspect
    return normalized
```

- [ ] **Step 6: Add interpolation with lens authority**

Add:

```python
def _interpolate_camera(a: dict[str, Any], b: dict[str, Any], t: float, *, aspect: float) -> dict[str, Any]:
    if a["projection"] != b["projection"]:
        raise CameraPlanError("camera projection cannot change during interpolation")

    camera = dict(a)
    camera["location"] = _lerp_vec(a["location"], b["location"], t)
    camera["target"] = _lerp_vec(a["target"], b["target"], t)
    raw_up = _lerp_vec(a["up"], b["up"], t)
    up = _normalize(raw_up)
    if up is None:
        raise CameraPlanError("camera up vector became degenerate during interpolation")
    camera["up"] = up

    if a.get("lens_length") is not None and b.get("lens_length") is not None:
        camera["lens_length"] = _lerp(float(a["lens_length"]), float(b["lens_length"]), t)
        camera["fov_degrees"] = a.get("fov_degrees")
    elif a.get("fov_degrees") is not None and b.get("fov_degrees") is not None:
        camera["lens_length"] = None
        camera["fov_degrees"] = _lerp(float(a["fov_degrees"]), float(b["fov_degrees"]), t)
    else:
        raise CameraPlanError("camera optics require lens_length or fov_degrees on both keyframes")

    for field in ("parallel_scale", "near_clip", "far_clip"):
        av = a.get(field)
        bv = b.get(field)
        if av is None or bv is None:
            camera[field] = av if t < 0.5 else bv
        else:
            camera[field] = _lerp(float(av), float(bv), t)

    camera["aspect"] = aspect
    return _validate_resolved_camera(camera, aspect=aspect)
```

- [ ] **Step 7: Add keyframe resolution**

Add:

```python
async def _resolve_keyframes(
    keyframes: list[dict[str, Any]],
    *,
    aspect: float,
    call_native,
    port: int | None,
) -> list[dict[str, Any]]:
    resolved = []
    for keyframe in keyframes:
        result = await call_native(
            "/director/view-state",
            "POST",
            {"source": keyframe["source"]},
            port=port,
        )
        if not result.get("success"):
            raise CameraPlanError(f"camera resolution failed: {result.get('data')}")
        data = result["data"]
        camera = _validate_resolved_camera(data["camera"], aspect=aspect)
        resolved.append(
            {
                "frame_index": keyframe["frame_index"],
                "source": keyframe["source"],
                "camera": camera,
                "provenance": data.get("provenance"),
            }
        )
    return resolved
```

- [ ] **Step 8: Add frame interpolation and public resolver**

Add:

```python
def interpolate_camera_frames(
    resolved_keyframes: list[dict[str, Any]],
    frame_count: int,
    *,
    aspect: float,
) -> list[dict[str, Any]]:
    keyframes = sorted(resolved_keyframes, key=lambda item: item["frame_index"])
    if len(keyframes) == 1:
        return [dict(keyframes[0]["camera"]) for _ in range(frame_count)]

    cameras = []
    for frame_index in range(1, frame_count + 1):
        previous = keyframes[0]
        next_key = keyframes[-1]
        for candidate in keyframes:
            if candidate["frame_index"] <= frame_index:
                previous = candidate
            if candidate["frame_index"] >= frame_index:
                next_key = candidate
                break
        if previous["frame_index"] == next_key["frame_index"]:
            cameras.append(dict(previous["camera"]))
            continue
        span = next_key["frame_index"] - previous["frame_index"]
        t = (frame_index - previous["frame_index"]) / span
        cameras.append(_interpolate_camera(previous["camera"], next_key["camera"], t, aspect=aspect))
    return cameras


async def resolve_camera_plan(
    request: dict[str, Any],
    *,
    frame_count: int,
    resolution: dict[str, int],
    call_native,
    port: int | None,
) -> dict[str, Any]:
    aspect = _aspect_from_resolution(resolution)
    validated = validate_camera_request(request, frame_count=frame_count)
    keyframes = validated["keyframes"]
    resolved_keyframes = await _resolve_keyframes(
        keyframes,
        aspect=aspect,
        call_native=call_native,
        port=port,
    )
    frames = interpolate_camera_frames(resolved_keyframes, frame_count, aspect=aspect)
    optics_authority = "lens_length" if all(k["camera"].get("lens_length") is not None for k in resolved_keyframes) else "fov_degrees"
    return {
        "strategy": "keyframes",
        "frames": frames,
        "provenance": {
            "strategy": "keyframes",
            "request_shape": validated["request_shape"],
            "aspect_authority": "output_resolution",
            "optics_authority": optics_authority,
            "keyframes": [
                {
                    "frame_index": keyframe["frame_index"],
                    "source": keyframe["source"],
                    "provenance": keyframe.get("provenance"),
                }
                for keyframe in resolved_keyframes
            ],
        },
    }
```

- [ ] **Step 9: Run planner tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_camera_planner.py -q
```

Expected:

```text
8 passed
```

## Task 3: Wire Director Through Camera Planner

**Files:**
- Modify: `mcp_server/src/rook/director.py`
- Modify: `mcp_server/tests/test_director.py`

- [ ] **Step 1: Add failing manifest provenance test**

In `mcp_server/tests/test_director.py`, add a test using the existing fake native style in this file:

```python
@pytest.mark.asyncio
async def test_run_director_writes_camera_plan_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    calls = []

    async def fake_native(endpoint, method, data, *, port=None):
        calls.append((endpoint, method, data))
        if endpoint == "/director/object-states":
            return {
                "success": True,
                "data": {
                    "units": "Millimeters",
                    "objects": [
                        {
                            "object_id": "obj-1",
                            "bbox_min": [0, 0, 0],
                            "bbox_max": [1, 1, 1],
                            "validation_strength": "bbox_only",
                            "state_hash": None,
                        }
                    ],
                },
            }
        if endpoint == "/director/view-state":
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": "perspective",
                        "location": [0, 0, 10],
                        "target": [0, 0, 0],
                        "up": [0, 1, 0],
                        "lens_length": 35.0,
                        "fov_degrees": 37.8493,
                        "parallel_scale": None,
                        "near_clip": 0.1,
                        "far_clip": 1000.0,
                        "aspect": 0.75,
                    },
                    "provenance": {"source": "active_view"},
                },
            }
        if endpoint == "/director/frame-capture":
            output_path = Path(data["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return {
                "success": True,
                "data": {
                    "success": True,
                    "dirty_partial_state": False,
                    "objects": {"requested": 1, "restored": 1},
                    "viewport": {"restore_verified": True},
                },
            }
        raise AssertionError(endpoint)

    result = await director.run_director(
        {
            "run_id": "camera-plan-provenance",
            "object_ids": ["obj-1"],
            "frame_count": 1,
            "resolution": {"width": 640, "height": 360},
            "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
        },
        call_native=fake_native,
    )

    assert result["state"] == "complete"
    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["camera_plan"]["strategy"] == "keyframes"
    assert manifest["camera_plan"]["request_shape"] == "legacy_camera_keyframes"
    assert manifest["camera_plan"]["aspect_authority"] == "output_resolution"
    assert manifest["camera_plan"]["optics_authority"] == "lens_length"
    assert manifest["camera_keyframe_provenance"][0]["provenance"] == {"source": "active_view"}
    assert manifest["frames"][0]["camera"]["aspect"] == pytest.approx(640 / 360)
```

- [ ] **Step 2: Add explicit camera strategy manifest compatibility test**

In `mcp_server/tests/test_director.py`, add:

```python
@pytest.mark.asyncio
async def test_run_director_accepts_explicit_camera_strategy_and_writes_compatibility_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    async def fake_native(endpoint, method, data, *, port=None):
        if endpoint == "/director/object-states":
            return {
                "success": True,
                "data": {
                    "units": "Millimeters",
                    "objects": [
                        {
                            "object_id": "obj-1",
                            "bbox_min": [0, 0, 0],
                            "bbox_max": [1, 1, 1],
                            "validation_strength": "bbox_only",
                            "state_hash": None,
                        }
                    ],
                },
            }
        if endpoint == "/director/view-state":
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": "perspective",
                        "location": [0, 0, 10],
                        "target": [0, 0, 0],
                        "up": [0, 1, 0],
                        "lens_length": 35.0,
                        "fov_degrees": 37.8493,
                        "parallel_scale": None,
                        "near_clip": 0.1,
                        "far_clip": 1000.0,
                        "aspect": 0.75,
                    },
                    "provenance": {"source": "named_view", "name": "Shot_A"},
                },
            }
        if endpoint == "/director/frame-capture":
            output_path = Path(data["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return {
                "success": True,
                "data": {
                    "success": True,
                    "dirty_partial_state": False,
                    "objects": {"requested": 1, "restored": 1},
                    "viewport": {"restore_verified": True},
                },
            }
        raise AssertionError(endpoint)

    result = await director.run_director(
        {
            "run_id": "explicit-camera-strategy",
            "object_ids": ["obj-1"],
            "frame_count": 1,
            "resolution": {"width": 640, "height": 360},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"frame_index": 1, "source": {"kind": "named_view", "name": "Shot_A"}}
                ],
            },
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
        },
        call_native=fake_native,
    )

    assert result["state"] == "complete"
    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["camera_plan"]["request_shape"] == "camera_strategy"
    assert manifest["camera_keyframes"] == [
        {"frame_index": 1, "source": {"kind": "named_view", "name": "Shot_A"}}
    ]
    assert manifest["camera_keyframe_provenance"][0]["provenance"] == {
        "source": "named_view",
        "name": "Shot_A",
    }
```

- [ ] **Step 3: Add camera validation fail-fast test**

In `mcp_server/tests/test_director.py`, add:

```python
@pytest.mark.asyncio
async def test_run_director_rejects_bad_camera_before_resolving_objects(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    calls = []

    async def fake_native(endpoint, method, data, *, port=None):
        calls.append(endpoint)
        raise AssertionError(f"native should not be called for invalid camera input: {endpoint}")

    with pytest.raises(director.DirectorInputError, match="frame_index"):
        await director.run_director(
            {
                "run_id": "bad-camera-fail-fast",
                "object_ids": ["obj-1"],
                "frame_count": 1,
                "resolution": {"width": 640, "height": 360},
                "camera": {
                    "strategy": "keyframes",
                    "keyframes": [
                        {"frame_index": 2, "source": {"kind": "active_view"}}
                    ],
                },
                "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            },
            call_native=fake_native,
        )

    assert calls == []
```

- [ ] **Step 4: Run the new tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_director.py -k "camera_plan_provenance or explicit_camera_strategy or bad_camera_before_resolving_objects" -q
```

Expected:

```text
one or more tests fail because camera_plan is missing, explicit camera.strategy is unsupported, or invalid camera input is not rejected before native calls
```

- [ ] **Step 5: Import and call camera planner in director**

In `mcp_server/src/rook/director.py`, add:

```python
from . import camera_planner
```

In `run_director`, after:

```python
object_ids = list(request.get("object_ids") or [])
if not object_ids:
    raise DirectorInputError("object_ids must contain at least one object for slice1")
```

move or add `frame_count` assignment immediately after the object-id check:

```python
frame_count = int(request["frame_count"])
```

Then insert this non-I/O camera validation before `_resolve_objects`:

```python
try:
    camera_planner.validate_camera_request(request, frame_count=frame_count)
except camera_planner.CameraPlanError as ex:
    raise DirectorInputError(str(ex)) from ex
```

This preserves the existing fail-fast behavior for malformed camera input.

Then replace:

```python
resolved_camera_keyframes = await _resolve_camera_keyframes(
    call_native,
    request["camera_keyframes"],
    frame_count=frame_count,
    port=port,
)
frame_cameras = interpolate_camera_frames(resolved_camera_keyframes, frame_count)
```

with:

```python
try:
    camera_plan = await camera_planner.resolve_camera_plan(
        request,
        frame_count=frame_count,
        resolution=request["resolution"],
        call_native=call_native,
        port=port,
    )
except camera_planner.CameraPlanError as ex:
    raise DirectorInputError(str(ex)) from ex
frame_cameras = camera_plan["frames"]
resolved_camera_keyframes = camera_plan["provenance"]["keyframes"]
```

- [ ] **Step 6: Derive manifest camera compatibility fields from resolved keyframes**

Before the manifest dictionary, add:

```python
manifest_camera_keyframes = [
    {
        "frame_index": keyframe["frame_index"],
        "source": keyframe["source"],
    }
    for keyframe in resolved_camera_keyframes
]
```

In the manifest dictionary, replace:

```python
"camera_keyframes": request["camera_keyframes"],
```

with:

```python
"camera_keyframes": manifest_camera_keyframes,
```

This preserves the manifest compatibility field for both legacy
`camera_keyframes` requests and explicit `camera.strategy == "keyframes"`
requests.

- [ ] **Step 7: Add manifest camera plan provenance**

In the manifest dictionary, add:

```python
"camera_plan": {
    "strategy": camera_plan["provenance"]["strategy"],
    "request_shape": camera_plan["provenance"]["request_shape"],
    "aspect_authority": camera_plan["provenance"]["aspect_authority"],
    "optics_authority": camera_plan["provenance"]["optics_authority"],
},
```

Keep `camera_keyframes` and `camera_keyframe_provenance` in the manifest for
slice 1 compatibility.

- [ ] **Step 8: Preserve director error type at the boundary**

Wrap camera planner failures in `DirectorInputError` so existing callers do not need to import `CameraPlanError`:

```python
try:
    camera_plan = await camera_planner.resolve_camera_plan(
        request,
        frame_count=frame_count,
        resolution=request["resolution"],
        call_native=call_native,
        port=port,
    )
except camera_planner.CameraPlanError as ex:
    raise DirectorInputError(str(ex)) from ex
```

- [ ] **Step 9: Run focused director tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director.py -q
```

Expected:

```text
all tests pass
```

## Task 4: Remove Duplicate Camera Logic From Director

**Files:**
- Modify: `mcp_server/src/rook/director.py`
- Test: `mcp_server/tests/test_director.py`
- Test: `mcp_server/tests/test_camera_planner.py`

- [ ] **Step 1: Delete moved helper functions from director**

Remove these functions from `director.py` after equivalent tests pass in
`test_camera_planner.py`:

```text
_lerp
_lerp_vec
_normalized_required
_interpolate_camera
interpolate_camera_frames
_resolve_camera_keyframes
```

Keep shared helpers used by object motion:

```text
_normalize
_center
expand_radial_bbox_center
```

- [ ] **Step 2: Keep only non-I/O camera presence validation in `validate_authoring_request`**

Replace camera-keyframe-specific validation in `validate_authoring_request` with only this presence check:

```python
has_legacy_camera = "camera_keyframes" in request
has_camera_request = isinstance(request.get("camera"), dict)
if not has_legacy_camera and not has_camera_request:
    raise DirectorInputError("camera.keyframes or camera_keyframes is required")
```

Camera source validation, strategy validation, and frame-index validation now live in `camera_planner.py`. `run_director` must still call `camera_planner.validate_camera_request` before `_resolve_objects`, as described in Task 3, so invalid camera requests do not trigger object-state native calls.

- [ ] **Step 3: Run combined pure Python tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_camera_planner.py mcp_server\tests\test_director.py mcp_server\tests\test_director_mcp_tools.py -q
```

Expected:

```text
all tests pass
```

## Task 5: Verify Live Compatibility

**Files:**
- No file changes unless tests reveal a compatibility gap.

- [ ] **Step 1: Run live Director tests**

With Rhino/RookNative discoverable, run:

```powershell
python -m pytest mcp_server\tests\test_director_routes_live.py -q
```

Expected:

```text
all live tests pass, or skip only when Rhino/RookNative is not discoverable
```

- [ ] **Step 2: Inspect one generated manifest**

Open the newest live `task11_live_*` run under:

```powershell
$env:LOCALAPPDATA\Rook\rookvision_director
```

Confirm:

```json
{
  "camera_plan": {
    "strategy": "keyframes",
    "request_shape": "legacy_camera_keyframes",
    "aspect_authority": "output_resolution",
    "optics_authority": "lens_length"
  }
}
```

Also confirm:

```text
manifest.frames[*].camera still has the same camera fields consumed by native /director/frame-capture.
```

- [ ] **Step 3: Run diff hygiene**

Run:

```powershell
git diff --check
```

Expected:

```text
no output
```

## Task 6: Commit

**Files:**
- `mcp_server/src/rook/camera_planner.py`
- `mcp_server/src/rook/director.py`
- `mcp_server/tests/test_camera_planner.py`
- `mcp_server/tests/test_director.py`

- [ ] **Step 1: Review changed files**

Run:

```powershell
git diff --stat
git diff -- mcp_server/src/rook/camera_planner.py mcp_server/src/rook/director.py
```

Expected:

```text
camera planning code is isolated in camera_planner.py; director.py only orchestrates it.
```

- [ ] **Step 2: Commit**

Run:

```powershell
git add mcp_server/src/rook/camera_planner.py mcp_server/src/rook/director.py mcp_server/tests/test_camera_planner.py mcp_server/tests/test_director.py
git commit -m "refactor director camera planning contract"
```

## Final Verification

- [ ] **Run pure Python Director tests**

```powershell
python -m pytest mcp_server\tests\test_camera_planner.py mcp_server\tests\test_director.py mcp_server\tests\test_director_mcp_tools.py -q
```

Expected: pass.

- [ ] **Run live Director tests when Rhino is available**

```powershell
python -m pytest mcp_server\tests\test_director_routes_live.py -q
```

Expected: pass with Rhino/RookNative discoverable, or skip only when Rhino/RookNative is unavailable.

- [ ] **Run diff hygiene**

```powershell
git diff --check
```

Expected: clean.

## Self-Review

- Spec coverage: the plan implements only Phase 1 from the roadmap and does not touch curve sampling, FFmpeg, artifact publishing, or native frame capture.
- Backward compatibility: legacy `camera_keyframes` remains valid and maps to `camera.strategy == "keyframes"`.
- Camera output compatibility: `manifest.frames[*].camera` remains the explicit per-frame camera shape consumed by native frame capture.
- Optics authority: `lens_length` is primary when available; FOV is authoritative only when lens length is unavailable.
- Aspect authority: output resolution controls default aspect.
- Validation: interpolated location-to-target direction and up vector are both validated.
