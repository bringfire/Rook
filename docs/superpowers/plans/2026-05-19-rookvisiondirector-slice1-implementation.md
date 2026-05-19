# RookVisionDirector Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first deterministic RookVisionDirector slice: a Python-orchestrated run that emits sequential RGB Rhino captures, a resolved manifest, status, and per-frame evidence, using a native guarded per-frame transaction.

**Architecture:** Python owns authoring, frame expansion, run folders, manifest/status/evidence, cancellation, and status transitions. RookNative owns the atomic Rhino frame transaction: validate, snapshot, apply object deltas and explicit camera/display state, capture, restore, verify, and return evidence. Native output writes are constrained by native-side allowed director roots, and source-relative transforms are protected by native source-state validation.

**Tech Stack:** C++ RookNative HTTP handlers with `nlohmann::json` and Rhino 8 SDK patterns; Python MCP server with `pytest`; existing Rook bridge, tool catalog, and live Rhino smoke-test harness.

---

## Source Documents

- Design spec: `docs/superpowers/specs/2026-05-19-rookvisiondirector-slice1-design.md`
- Architecture reference: `docs/CURRENT_ARCHITECTURE.md`
- Repo instructions: `AGENTS.md` content supplied in the conversation

## File Structure

Create:

- `mcp_server/src/rook/director.py`  
  Python director service: request validation, shared director-output-root resolution, motion expansion, camera interpolation, manifest/status/evidence writes, and per-frame native calls.

- `mcp_server/tests/test_director.py`  
  Pure Python tests for output policy, manifest shape, motion expansion, camera validation, status transitions, cancellation, evidence failure, and unsafe failure.

- `mcp_server/tests/test_director_mcp_tools.py`  
  MCP/tool-dispatch tests for `rhino_director_run`, tool group registration, and agent dispatcher parity where applicable.

- `mcp_server/tests/test_director_routes_live.py`  
  Live Rhino smoke tests for `/director/object-states`, `/director/view-state`, and `/director/frame-capture`. These skip when Rhino/RookNative is not discoverable.

- `src/RookNative/Handlers/DirectorHandler.h`

- `src/RookNative/Handlers/DirectorHandler.cpp`  
  Native read-only director context routes and the guarded frame transaction route.

Modify:

- `src/RookNative/RookServer.h`  
  Add private route-delegation method declarations for the director routes.

- `src/RookNative/RookServer.cpp`  
  Include `DirectorHandler.h`, register `/director/object-states`, `/director/view-state`, and `/director/frame-capture`, and delegate to `Rook::Handlers`.

- `mcp_server/src/rook/server.py`  
  Register `rhino_director_run` and dispatch it through `rook.director.run_director`.

- `mcp_server/src/rook/agent/tool_groups.py`  
  Add `director` and `director_readonly` groups. Keep `director` MCP-only unless agent-direct dispatch is explicitly wired.

- `mcp_server/src/rook/agent/tool_dispatcher.py`  
  Add native read-only director bridge routes if agents need direct read access. Do not add `rhino_director_run` to `BRIDGE_ROUTES`; it is Python-orchestrated.

- `src/RookNative/RookNative.vcxproj`

- `src/RookNative/RookNative.vcxproj.filters`  
  Execution preflight: ask the user for explicit approval before modifying these project files. New native `.cpp/.h` files will not build in Visual Studio unless project files include them.

## Phase 0 Gate: Inventory And Enum Decision

This phase prevents guessed Rhino SDK usage from entering the implementation. It also fixes the first slice's `validation_strength` enum and the shared Python/native director output-root contract before coding.

### Task 1: Record Route And Capability Inventory

**Files:**
- Create: `docs/superpowers/plans/2026-05-19-rookvisiondirector-slice1-phase0-inventory.md`

- [x] **Step 1: Run focused inventory searches**

Run:

```powershell
rg -n "CaptureToBitmap|ViewCaptureToFile|SetVP|ViewportInfo|SetDisplayMode|TransformObject|BoundingBox|UnitSystem|NamedView|ActiveViewport" src/RookNative src/Rook
rg -n "rhino_viewport|rhino_views|rhino_display_modes|rhino_transform|rhino_objects|call_rhino|TOOL_GROUPS|BRIDGE_ROUTES" mcp_server/src/rook mcp_server/tests
```

Expected:

- Capture/camera/display patterns are found in `src/RookNative/Handlers/ViewportHandler.cpp`, `src/Rook/Handlers/ViewportHandler.cs`, `src/RookNative/Handlers/DisplayModeHandler.cpp`, and `src/RookNative/Handlers/DocumentOpsHandler.cpp`.
- Object transform and bounding-box patterns are found in `src/RookNative/Handlers/GeometryOpsHandler.cpp`, `src/RookNative/Handlers/MeasureHandler.cpp`, and `src/RookNative/Models/DocumentHelpers.h`.

- [x] **Step 2: Write the inventory note**

Create `docs/superpowers/plans/2026-05-19-rookvisiondirector-slice1-phase0-inventory.md` with this structure:

```markdown
# RookVisionDirector Slice 1 Phase 0 Inventory

Date: 2026-05-19

## Existing Patterns To Reuse

- View capture:
- View/camera state:
- Display mode:
- Object transform:
- Object bounds/source state:
- Document units:
- MCP tool registration:
- Live Rhino tests:

## Native Routes To Add

- `POST /director/object-states`
- `POST /director/view-state`
- `POST /director/frame-capture`

## Validation Strength Enum

Slice 1 accepts exactly:

- `bbox_only`: bbox min/max comparison within tolerance; degraded validation, not proof.
- `runtime_serial_and_bbox`: include only if Phase 0 verifies a stable Rhino object runtime serial or equivalent transform-relevant token is accessible and reliable for this use.

If `runtime_serial_and_bbox` cannot be verified from existing Rhino/Rook APIs, slice 1 ships only `bbox_only` and evidence records degraded source-state validation.

## Parallel Camera Decision

- `parallel_supported`: yes/no
- Evidence:
- If no, native rejects `camera.projection = "parallel"` with `unsupported_projection`.

## Shared Director Output Root Contract

Python and native use the same root contract:

1. If `ROOK_DIRECTOR_OUTPUT_ROOT` is set, canonicalize it and use it as the only allowed director output root.
2. Otherwise use `%LOCALAPPDATA%/Rook/rookvision_director`.
3. Python-created `run_root` values must be descendants of this root.
4. Native independently reads the same native-side environment/default contract and rejects any `run_root` or `output_path` outside it.
5. `runtime.data_root / "rookvision_director"` is not the slice 1 default because the dev fallback currently resolves to `repo/knowledge`, which native should not implicitly allow for frame output.
```

- [x] **Step 3: Commit the inventory note**

Run:

```powershell
git add docs/superpowers/plans/2026-05-19-rookvisiondirector-slice1-phase0-inventory.md
git commit -m "docs: record RookVisionDirector phase 0 inventory"
```

Expected: commit succeeds.

## Phase 1: Python Contract And Manifest Runner

Python is implemented first behind a fake native caller so schema, status, and failure behavior are pinned before native code exists.

### Task 2: Add Python Director Data Contract Tests

**Files:**
- Create: `mcp_server/tests/test_director.py`
- Create: `mcp_server/src/rook/director.py`

- [x] **Step 1: Write failing tests for request validation and output roots**

Create `mcp_server/tests/test_director.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rook import director


def test_default_output_root_uses_local_app_data_rook_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = director.resolve_output_root(None)
    assert root == (tmp_path / "local" / "Rook" / "rookvision_director").resolve()


def test_env_output_root_is_shared_allowlist_source(tmp_path, monkeypatch):
    configured = tmp_path / "configured" / "director"
    monkeypatch.setenv("ROOK_DIRECTOR_OUTPUT_ROOT", str(configured))
    assert director.resolve_output_root(None) == configured.resolve()


def test_output_root_must_stay_under_shared_director_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOK_DIRECTOR_OUTPUT_ROOT", str(tmp_path / "allowed"))
    with pytest.raises(director.DirectorInputError, match="output_root"):
        director.resolve_output_root(str(tmp_path / "outside"))


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"frame_count": 0}, "frame_count"),
        ({"frame_count": 1, "resolution": {"width": 0, "height": 720}}, "resolution"),
        ({"frame_count": 1, "resolution": {"width": 1280, "height": -1}}, "resolution"),
        ({"frame_count": 1, "resolution": {"width": 1280, "height": 720}, "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": -1}}}, "distance"),
    ],
)
def test_validate_request_rejects_bad_authoring_inputs(payload, message):
    with pytest.raises(director.DirectorInputError, match=message):
        director.validate_authoring_request(payload)
```

- [x] **Step 2: Run tests and verify they fail because module is missing**

Run:

```powershell
pytest mcp_server/tests/test_director.py -q
```

Expected: fails with `ImportError` or missing symbols from `rook.director`.

- [x] **Step 3: Implement minimal contract helpers**

Create `mcp_server/src/rook/director.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .runtime_paths import resolve_runtime_paths

SCHEMA_VERSION = 1
DIRECTOR_VERSION = "slice1"


class DirectorError(Exception):
    pass


class DirectorInputError(DirectorError):
    pass


@dataclass(frozen=True)
class DirectorRuntimePaths:
    director_output_root: Path | None = None


def _runtime_paths() -> DirectorRuntimePaths:
    resolve_runtime_paths()
    return DirectorRuntimePaths()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _default_director_output_root(runtime: DirectorRuntimePaths | None = None) -> Path:
    runtime = runtime or _runtime_paths()
    if runtime.director_output_root is not None:
        return Path(runtime.director_output_root).expanduser().resolve()
    env_root = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorInputError("LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set")
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def resolve_output_root(output_root: str | None, runtime: DirectorRuntimePaths | None = None) -> Path:
    allowed_root = _default_director_output_root(runtime)
    if output_root is None:
        return allowed_root
    candidate = Path(output_root).expanduser().resolve()
    if not _is_relative_to(candidate, allowed_root):
        raise DirectorInputError("output_root must resolve under the configured RookVisionDirector output root")
    return candidate


def validate_authoring_request(request: dict[str, Any]) -> None:
    frame_count = int(request.get("frame_count", 0))
    if frame_count < 1:
        raise DirectorInputError("frame_count must be >= 1")

    resolution = request.get("resolution") or {}
    width = int(resolution.get("width", 0))
    height = int(resolution.get("height", 0))
    if width <= 0 or height <= 0:
        raise DirectorInputError("resolution width and height must be positive")

    motion = request.get("motion") or {}
    if motion.get("strategy", "radial_bbox_center") != "radial_bbox_center":
        raise DirectorInputError("motion strategy must be radial_bbox_center for slice1")
    params = motion.get("parameters") or {}
    distance = float(params.get("distance", 10.0))
    if distance < 0:
        raise DirectorInputError("motion distance must be nonnegative")
```

- [x] **Step 4: Run tests and verify they pass**

Run:

```powershell
pytest mcp_server/tests/test_director.py -q
```

Expected: all tests in the file pass.

- [x] **Step 5: Commit**

Run:

```powershell
git add mcp_server/src/rook/director.py mcp_server/tests/test_director.py
git commit -m "feat: add director Python contract helpers"
```

### Task 3: Add Motion Expansion And Manifest Tests

**Files:**
- Modify: `mcp_server/tests/test_director.py`
- Modify: `mcp_server/src/rook/director.py`

- [x] **Step 1: Add failing tests for radial source-relative frame deltas**

Append to `mcp_server/tests/test_director.py`:

```python
def _obj(object_id, bbox_min, bbox_max, name=None):
    return {
        "object_id": object_id,
        "object_display_name": name,
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "validation_strength": "bbox_only",
        "state_hash": None,
    }


def test_radial_bbox_center_single_frame_has_identity_delta():
    objects = [_obj("a", [0, 0, 0], [2, 2, 2])]
    frames, warnings = director.expand_radial_bbox_center(objects, frame_count=1, distance=10.0, per_object_scale={})
    assert warnings[0]["code"] == "center_direction_fallback"
    assert frames[0]["frame_index"] == 1
    assert frames[0]["object_transforms"][0]["transform"] == director.identity_matrix()


def test_radial_bbox_center_final_frame_moves_from_selection_center():
    objects = [
        _obj("left", [-2, -1, 0], [-1, 1, 1]),
        _obj("right", [1, -1, 0], [2, 1, 1]),
    ]
    frames, warnings = director.expand_radial_bbox_center(objects, frame_count=3, distance=4.0, per_object_scale={})
    assert warnings == []
    final = frames[-1]["object_transforms"]
    left = next(item for item in final if item["object_id"] == "left")
    right = next(item for item in final if item["object_id"] == "right")
    assert left["transform"][0][3] == pytest.approx(-4.0)
    assert right["transform"][0][3] == pytest.approx(4.0)


def test_radial_bbox_center_records_fallback_direction_warning():
    objects = [_obj("center", [-1, -1, -1], [1, 1, 1])]
    frames, warnings = director.expand_radial_bbox_center(objects, frame_count=2, distance=2.0, per_object_scale={})
    assert warnings
    assert warnings[0]["code"] == "center_direction_fallback"
    final = frames[-1]["object_transforms"][0]
    assert final["transform"][0][3] == pytest.approx(2.0)
```

- [x] **Step 2: Run tests and verify missing function failures**

Run:

```powershell
pytest mcp_server/tests/test_director.py -q
```

Expected: fails for `expand_radial_bbox_center` and `identity_matrix`.

- [x] **Step 3: Implement motion helpers**

Add to `mcp_server/src/rook/director.py`:

```python
import math


def identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def translation_matrix(vector: list[float]) -> list[list[float]]:
    matrix = identity_matrix()
    matrix[0][3] = float(vector[0])
    matrix[1][3] = float(vector[1])
    matrix[2][3] = float(vector[2])
    return matrix


def _center(bbox_min: list[float], bbox_max: list[float]) -> list[float]:
    return [(float(a) + float(b)) / 2.0 for a, b in zip(bbox_min, bbox_max)]


def _normalize(vector: list[float]) -> list[float] | None:
    length = math.sqrt(sum(float(v) * float(v) for v in vector))
    if length < 1e-9:
        return None
    return [float(v) / length for v in vector]


def expand_radial_bbox_center(
    objects: list[dict[str, Any]],
    *,
    frame_count: int,
    distance: float,
    per_object_scale: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_mins = [float(v) for obj in objects for v in obj["bbox_min"]]
    all_maxs = [float(v) for obj in objects for v in obj["bbox_max"]]
    selection_min = [min(all_mins[i::3]) for i in range(3)]
    selection_max = [max(all_maxs[i::3]) for i in range(3)]
    selection_center = _center(selection_min, selection_max)

    directions: dict[str, list[float]] = {}
    warnings: list[dict[str, Any]] = []
    for obj in objects:
        object_id = obj["object_id"]
        object_center = _center(obj["bbox_min"], obj["bbox_max"])
        raw = [object_center[i] - selection_center[i] for i in range(3)]
        direction = _normalize(raw)
        if direction is None:
            direction = [1.0, 0.0, 0.0]
            warnings.append({"code": "center_direction_fallback", "object_id": object_id})
        directions[object_id] = direction

    frames: list[dict[str, Any]] = []
    for index in range(1, frame_count + 1):
        t = 0.0 if frame_count == 1 else (index - 1) / (frame_count - 1)
        object_transforms = []
        for obj in objects:
            object_id = obj["object_id"]
            scale = float(per_object_scale.get(object_id, 1.0))
            direction = directions[object_id]
            vector = [component * float(distance) * scale * t for component in direction]
            object_transforms.append(
                {
                    "object_id": object_id,
                    "source_state": {
                        "bbox_min": obj["bbox_min"],
                        "bbox_max": obj["bbox_max"],
                        "validation_strength": obj.get("validation_strength", "bbox_only"),
                        "state_hash": obj.get("state_hash"),
                    },
                    "transform": translation_matrix(vector),
                }
            )
        frames.append({"frame_index": index, "object_transforms": object_transforms})
    return frames, warnings
```

- [x] **Step 4: Run tests**

Run:

```powershell
pytest mcp_server/tests/test_director.py -q
```

Expected: all tests pass.

- [x] **Step 5: Commit**

Run:

```powershell
git add mcp_server/src/rook/director.py mcp_server/tests/test_director.py
git commit -m "feat: expand director radial motion frames"
```

### Task 4: Add Status, Evidence, And Run-Orchestration Tests

**Files:**
- Modify: `mcp_server/tests/test_director.py`
- Modify: `mcp_server/src/rook/director.py`

- [x] **Step 1: Add fake-native run tests**

Append to `mcp_server/tests/test_director.py`:

```python
import asyncio


class FakeNative:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, method, data, port))
        if endpoint == "/director/object-states":
            return {"success": True, "data": {"objects": [_obj("a", [0, 0, 0], [1, 1, 1], "A")], "units": "Inches"}}
        if endpoint == "/director/view-state":
            source = data["source"]
            if source.get("kind") == "named_view" and source.get("name") == "End":
                location = [8, -4, 3]
                lens = 55.0
                provenance = {"source": "named_view", "name": "End"}
            else:
                location = [4, -4, 3]
                lens = 35.0
                provenance = {"source": "active_view"}
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": "perspective",
                        "location": location,
                        "target": [0, 0, 0],
                        "up": [0, 0, 1],
                        "lens_length": lens,
                        "fov_degrees": None,
                        "parallel_scale": None,
                        "near_clip": None,
                        "far_clip": None,
                        "aspect": 1.7778,
                    },
                    "provenance": provenance,
                },
            }
        return self.responses.pop(0)


def _run_request(tmp_path):
    return {
        "object_ids": ["a"],
        "frame_count": 2,
        "resolution": {"width": 320, "height": 180},
        "display": {"mode": "Rendered"},
        "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
        "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 2.0}},
        "output_root": str(tmp_path / "data" / "rookvision_director"),
    }


def _runtime(tmp_path):
    return director.DirectorRuntimePaths(director_output_root=tmp_path / "data" / "rookvision_director")


def test_two_camera_keyframes_interpolate_per_frame(tmp_path):
    request = _run_request(tmp_path)
    request["frame_count"] = 3
    request["camera_keyframes"] = [
        {"frame_index": 1, "source": {"kind": "active_view"}},
        {"frame_index": 3, "source": {"kind": "named_view", "name": "End"}},
    ]
    fake = FakeNative([
        {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
        {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        {"success": True, "data": {"frame_id": "frame_0003", "dirty_partial_state": False}},
    ])
    result = asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))
    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    locations = [frame["camera"]["location"] for frame in manifest["frames"]]
    lens_lengths = [frame["camera"]["lens_length"] for frame in manifest["frames"]]
    assert locations == [[4.0, -4.0, 3.0], [6.0, -4.0, 3.0], [8.0, -4.0, 3.0]]
    assert lens_lengths == [35.0, 45.0, 55.0]


def test_run_complete_writes_manifest_status_and_evidence(tmp_path):
    fake = FakeNative([
        {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False, "output_path": "x"}},
        {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False, "output_path": "y"}},
    ])
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    run_root = Path(result["run_root"])
    assert result["state"] == "complete"
    assert (run_root / "manifest.json").exists()
    assert (run_root / "status.json").exists()
    assert (run_root / "logs" / "frame_evidence.jsonl").exists()
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["document_units"] == "Inches"
    assert manifest["frames"][0]["frame_index"] == 1
    evidence_lines = (run_root / "logs" / "frame_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(evidence_lines) == 2


def test_run_marks_failed_when_native_frame_fails_safely(tmp_path):
    fake = FakeNative([
        {"success": False, "data": {"frame_id": "frame_0001", "dirty_partial_state": False, "error": {"code": "capture_failed"}}},
    ])
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    assert result["state"] == "failed"


def test_run_marks_unsafe_failed_and_stops(tmp_path):
    fake = FakeNative([
        {"success": False, "data": {"frame_id": "frame_0001", "dirty_partial_state": True, "error": {"code": "restore_failed"}}},
        {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
    ])
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    assert result["state"] == "unsafe_failed"
    frame_calls = [call for call in fake.calls if call[0] == "/director/frame-capture"]
    assert len(frame_calls) == 1
```

- [x] **Step 2: Run tests and verify failures**

Run:

```powershell
pytest mcp_server/tests/test_director.py -q
```

Expected: fails for missing `run_director`.

- [x] **Step 3: Implement run orchestration**

Add to `mcp_server/src/rook/director.py`:

```python
import asyncio
import json
import uuid
from datetime import datetime, timezone

from .bridge import call_rhino


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")


async def _resolve_objects(call_native, object_ids: list[str], port: int | None):
    result = await call_native("/director/object-states", "POST", {"object_ids": object_ids}, port=port)
    if not result.get("success"):
        raise DirectorInputError(f"object state resolution failed: {result.get('data')}")
    return result["data"]


async def _resolve_camera_keyframes(
    call_native,
    keyframes: list[dict[str, Any]],
    *,
    frame_count: int,
    port: int | None,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for keyframe in sorted(keyframes, key=lambda item: int(item["frame_index"])):
        frame_index = int(keyframe["frame_index"])
        if frame_index < 1 or frame_index > frame_count:
            raise DirectorInputError("camera keyframe frame_index must be inside 1..frame_count")
        result = await call_native("/director/view-state", "POST", {"source": keyframe["source"]}, port=port)
        if not result.get("success"):
            raise DirectorInputError(f"camera resolution failed: {result.get('data')}")
        data = result["data"]
        resolved.append(
            {
                "frame_index": frame_index,
                "camera": data["camera"],
                "provenance": data.get("provenance"),
            }
        )
    if not resolved:
        raise DirectorInputError("camera_keyframes must contain at least one keyframe")
    return resolved


def _lerp(a: float, b: float, t: float) -> float:
    return float(a) + (float(b) - float(a)) * t


def _lerp_vec(a: list[float], b: list[float], t: float) -> list[float]:
    return [_lerp(a[i], b[i], t) for i in range(3)]


def _normalized_required(vector: list[float], field: str) -> list[float]:
    normalized = _normalize(vector)
    if normalized is None:
        raise DirectorInputError(f"camera {field} vector became degenerate during interpolation")
    return normalized


def _interpolate_camera(a: dict[str, Any], b: dict[str, Any], t: float) -> dict[str, Any]:
    if a["projection"] != b["projection"]:
        raise DirectorInputError("camera projection cannot change during slice1 interpolation")
    camera = dict(a)
    camera["location"] = _lerp_vec(a["location"], b["location"], t)
    camera["target"] = _lerp_vec(a["target"], b["target"], t)
    camera["up"] = _normalized_required(_lerp_vec(a["up"], b["up"], t), "up")
    for field in ("lens_length", "fov_degrees", "parallel_scale", "near_clip", "far_clip", "aspect"):
        av = a.get(field)
        bv = b.get(field)
        if av is None or bv is None:
            camera[field] = av if t < 0.5 else bv
        else:
            camera[field] = _lerp(float(av), float(bv), t)
    return camera


def interpolate_camera_frames(resolved_keyframes: list[dict[str, Any]], frame_count: int) -> list[dict[str, Any]]:
    keyframes = sorted(resolved_keyframes, key=lambda item: item["frame_index"])
    if len(keyframes) == 1:
        return [dict(keyframes[0]["camera"]) for _ in range(frame_count)]

    cameras: list[dict[str, Any]] = []
    for frame_index in range(1, frame_count + 1):
        previous = keyframes[0]
        next_key = keyframes[-1]
        for idx, candidate in enumerate(keyframes):
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
        cameras.append(_interpolate_camera(previous["camera"], next_key["camera"], t))
    return cameras


def _frame_id(index: int) -> str:
    return f"frame_{index:04d}"


async def run_director(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    runtime: DirectorRuntimePaths | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    validate_authoring_request(request)
    runtime = runtime or _runtime_paths()
    output_root = resolve_output_root(request.get("output_root"), runtime)
    run_id = request.get("run_id") or f"director_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run_root = (output_root / run_id).resolve()
    frames_dir = run_root / "frames"
    logs_dir = run_root / "logs"
    frames_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=True)

    object_ids = list(request.get("object_ids") or [])
    if not object_ids:
        raise DirectorInputError("object_ids must contain at least one object for slice1")

    object_data = await _resolve_objects(call_native, object_ids, port)
    objects = object_data["objects"]
    frame_count = int(request["frame_count"])
    resolved_camera_keyframes = await _resolve_camera_keyframes(
        call_native,
        request["camera_keyframes"],
        frame_count=frame_count,
        port=port,
    )
    frame_cameras = interpolate_camera_frames(resolved_camera_keyframes, frame_count)
    motion_params = (request.get("motion") or {}).get("parameters") or {}
    motion_frames, motion_warnings = expand_radial_bbox_center(
        objects,
        frame_count=frame_count,
        distance=float(motion_params.get("distance", 10.0)),
        per_object_scale=dict(motion_params.get("per_object_scale") or {}),
    )

    manifest_frames = []
    for frame in motion_frames:
        index = frame["frame_index"]
        frame_name = _frame_id(index)
        manifest_frames.append(
            {
                "frame_index": index,
                "frame_id": frame_name,
                "camera": frame_cameras[index - 1],
                "object_transforms": frame["object_transforms"],
                "output_path": str((frames_dir / f"{frame_name}.png").resolve()),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "director_version": DIRECTOR_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "output_root": str(output_root),
        "created_at": _utc_now(),
        "document_units": object_data.get("units"),
        "source_objects": objects,
        "motion": {
            "strategy": "radial_bbox_center",
            "parameters": motion_params,
            "warnings": motion_warnings,
        },
        "camera_keyframes": request["camera_keyframes"],
        "camera_keyframe_provenance": [
            {
                "frame_index": keyframe["frame_index"],
                "provenance": keyframe.get("provenance"),
            }
            for keyframe in resolved_camera_keyframes
        ],
        "resolution": request["resolution"],
        "display": request.get("display") or {"mode": "Rendered"},
        "frames": manifest_frames,
        "exclusions": [
            "true_depth",
            "edge_pass",
            "rookvision_artifact_handoff",
            "grasshopper_nle",
        ],
    }
    _atomic_write_json(run_root / "manifest.json", manifest)
    _atomic_write_json(run_root / "status.json", {"state": "running", "run_id": run_id, "updated_at": _utc_now()})

    state = "complete"
    evidence_path = logs_dir / "frame_evidence.jsonl"
    for frame in manifest_frames:
        instruction = {
            "schema_version": SCHEMA_VERSION,
            "director_version": DIRECTOR_VERSION,
            "run_id": run_id,
            "frame_index": frame["frame_index"],
            "frame_id": frame["frame_id"],
            "run_root": str(run_root),
            "output_path": frame["output_path"],
            "resolution": request["resolution"],
            "display": request.get("display") or {"mode": "Rendered"},
            "camera": frame["camera"],
            "object_transforms": frame["object_transforms"],
        }
        result = await call_native("/director/frame-capture", "POST", instruction, port=port)
        evidence = result.get("data") if isinstance(result.get("data"), dict) else {"error": result.get("data")}
        evidence["success"] = bool(result.get("success"))
        try:
            _append_evidence(evidence_path, evidence)
        except OSError:
            state = "evidence_failed"
            break
        if evidence.get("dirty_partial_state"):
            state = "unsafe_failed"
            break
        if not result.get("success"):
            state = "failed"
            break

    summary = {"state": state, "run_id": run_id, "run_root": str(run_root), "updated_at": _utc_now()}
    _atomic_write_json(run_root / "status.json", summary)
    return summary
```

- [x] **Step 4: Run tests**

Run:

```powershell
pytest mcp_server/tests/test_director.py -q
```

Expected: all tests pass.

- [x] **Step 5: Commit**

Run:

```powershell
git add mcp_server/src/rook/director.py mcp_server/tests/test_director.py
git commit -m "feat: add director manifest runner"
```

### Task 5: Add MCP Tool Registration And Dispatch

**Files:**
- Create: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`

- [x] **Step 1: Write failing MCP registration and dispatch tests**

Create `mcp_server/tests/test_director_mcp_tools.py` with:

```python
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server, targeting
from rook.agent import tool_groups


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])


@pytest.mark.asyncio
async def test_director_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_run" in by_name
    schema = by_name["rhino_director_run"].inputSchema
    assert schema["required"] == ["object_ids", "frame_count", "resolution", "camera_keyframes"]


@pytest.mark.asyncio
async def test_director_tool_dispatches_to_python_runner():
    request = {
        "object_ids": ["a"],
        "frame_count": 1,
        "resolution": {"width": 320, "height": 180},
        "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
    }
    with patch.object(server.director, "run_director", new_callable=AsyncMock) as mock:
        mock.return_value = {"state": "complete", "run_root": "C:/runs/x"}
        result = await server.call_tool("rhino_director_run", request)
    mock.assert_awaited_once()
    assert "complete" in result[0].text


def test_director_tool_groups_are_mcp_only():
    assert "director" in tool_groups.TOOL_GROUPS
    assert "rhino_director_run" in tool_groups.TOOL_GROUPS["director"]
    assert "director" in tool_groups.MCP_ONLY_GROUPS
```

- [x] **Step 2: Run tests and verify failures**

Run:

```powershell
pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: fails because `rhino_director_run` is not registered and no director group exists.

- [x] **Step 3: Register the MCP tool**

Modify `mcp_server/src/rook/server.py`:

```python
from . import director
```

Add a `Tool(...)` entry near viewport/vision tools:

```python
Tool(
    name="rhino_director_run",
    description=(
        "Run RookVisionDirector slice 1: resolve objects/camera, apply a "
        "radial_bbox_center motion strategy, call native per-frame capture, "
        "and write manifest/status/evidence plus sequential PNG frames."
    ),
    inputSchema={
        "type": "object",
        "required": ["object_ids", "frame_count", "resolution", "camera_keyframes"],
        "properties": {
            "object_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "frame_count": {"type": "integer", "minimum": 1},
            "resolution": {
                "type": "object",
                "required": ["width", "height"],
                "properties": {
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                },
            },
            "display": {
                "type": "object",
                "properties": {"mode": {"type": "string"}},
            },
            "camera_keyframes": {"type": "array", "items": {"type": "object"}, "minItems": 1},
            "motion": {"type": "object"},
            "output_root": {"type": "string"},
            "run_id": {"type": "string"},
        },
    },
)
```

Add the `call_tool` case:

```python
        case "rhino_director_run":
            result = await director.run_director(arguments, port=port)
```

- [x] **Step 4: Add tool group catalog entries**

Modify `mcp_server/src/rook/agent/tool_groups.py`:

```python
    "director": [
        "rhino_director_run",
    ],
    "director_readonly": [
        "rhino_objects", "rhino_views", "rhino_display_modes", "rhino_document",
    ],
```

Add to `MCP_ONLY_GROUPS`:

```python
    "director",
```

- [x] **Step 5: Run tests**

Run:

```powershell
pytest mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat: expose director run MCP tool"
```

## Phase 2: Native Read-Only Director Context Routes

These routes provide trustworthy Rhino state for Python authoring without mutating the document.

### Task 6: Add Live Tests For Read-Only Native Routes

**Files:**
- Create: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Write failing live route tests**

Create `mcp_server/tests/test_director_routes_live.py` with:

```python
from __future__ import annotations

import pytest

from rook.bridge import call_rhino

pytestmark = pytest.mark.requires_rhino


@pytest.mark.asyncio
async def test_director_view_state_active_view_contract(requires_rhino):
    result = await call_rhino("/director/view-state", "POST", {"source": {"kind": "active_view"}})
    assert result["success"] is True
    camera = result["data"]["camera"]
    assert camera["projection"] in {"perspective", "parallel"}
    assert len(camera["location"]) == 3
    assert len(camera["target"]) == 3
    assert len(camera["up"]) == 3
    assert "aspect" in camera
    assert result["data"]["provenance"]["source"] == "active_view"


@pytest.mark.asyncio
async def test_director_object_states_rejects_empty_ids(requires_rhino):
    result = await call_rhino("/director/object-states", "POST", {"object_ids": []})
    assert result["success"] is False
    assert "object_ids" in str(result["data"])
```

- [ ] **Step 2: Run live tests and verify route-not-found failures**

Run:

```powershell
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected with Rhino/RookNative running: fails because `/director/*` routes are not registered. Expected without Rhino: skipped by the existing live harness.

- [ ] **Step 3: Commit tests**

Run:

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test: add director live route contracts"
```

### Task 7: Implement Native Director Read-Only Routes

**Files:**
- Create: `src/RookNative/Handlers/DirectorHandler.h`
- Create: `src/RookNative/Handlers/DirectorHandler.cpp`
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`
- Modify after explicit approval: `src/RookNative/RookNative.vcxproj`
- Modify after explicit approval: `src/RookNative/RookNative.vcxproj.filters`

- [ ] **Step 1: Get explicit project-file approval**

Ask the user:

```text
New native handler files require updating src/RookNative/RookNative.vcxproj and .filters so Visual Studio builds them. Do you approve those project-file edits for this implementation?
```

Proceed with the project-file steps only after approval. If approval is not granted, place the temporary implementation in an existing compiled handler file and record that compromise in the final summary.

- [ ] **Step 2: Add handler declarations**

Create `src/RookNative/Handlers/DirectorHandler.h`:

```cpp
#pragma once

#include "httplib.h"

namespace Rook::Handlers
{
    void HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorViewState(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res);
}
```

- [ ] **Step 3: Add read-only handler implementation**

Create `src/RookNative/Handlers/DirectorHandler.cpp` using existing server response helpers and main-thread dispatch patterns. The implementation must:

- parse JSON with `nlohmann::json::parse(req.body)`;
- reject empty `object_ids`;
- resolve each GUID with existing object lookup patterns;
- return bbox min/max, optional display name/type/layer provenance, `validation_strength`, and `state_hash`;
- resolve active or named view camera state into the explicit camera schema;
- reject parallel projection unless Phase 0 confirmed the fields needed to apply it faithfully.

Minimum response shape for `/director/object-states`:

```json
{
  "objects": [
    {
      "object_id": "guid",
      "object_display_name": "Name",
      "object_type": "brep",
      "layer": "Layer 01",
      "bbox_min": [0, 0, 0],
      "bbox_max": [1, 1, 1],
      "validation_strength": "bbox_only",
      "state_hash": null
    }
  ],
  "units": "Inches"
}
```

Minimum response shape for `/director/view-state`:

```json
{
  "camera": {
    "projection": "perspective",
    "location": [10, -10, 8],
    "target": [0, 0, 0],
    "up": [0, 0, 1],
    "lens_length": 35.0,
    "fov_degrees": null,
    "parallel_scale": null,
    "near_clip": null,
    "far_clip": null,
    "aspect": 1.7777777778
  },
  "provenance": {
    "source": "active_view"
  }
}
```

- [ ] **Step 4: Wire routes through `RookServer`**

Modify `src/RookNative/RookServer.h`:

```cpp
    void HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorViewState(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res);
```

Modify `src/RookNative/RookServer.cpp`:

```cpp
#include "Handlers/DirectorHandler.h"
```

Register routes in `RegisterRoutes()`:

```cpp
    m_server->Post("/director/object-states", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDirectorObjectStates(req, res);
    });
    m_server->Post("/director/view-state", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDirectorViewState(req, res);
    });
    m_server->Post("/director/frame-capture", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDirectorFrameCapture(req, res);
    });
```

Add delegators:

```cpp
void CRookServer::HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDirectorObjectStates(req, res);
}

void CRookServer::HandleDirectorViewState(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDirectorViewState(req, res);
}

void CRookServer::HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDirectorFrameCapture(req, res);
}
```

- [ ] **Step 5: Update native project files after approval**

Add the new handler files to `src/RookNative/RookNative.vcxproj` and `src/RookNative/RookNative.vcxproj.filters` following the neighboring `Handlers/*Handler.cpp` and `.h` entries exactly.

- [ ] **Step 6: Build native**

Run from a fresh developer shell:

```cmd
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If the Rhino/MFC toolchain is unavailable, record the exact missing-toolchain error and do not claim native build verification.

- [ ] **Step 7: Run live read-only tests**

Run:

```powershell
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected: read-only tests pass with Rhino/RookNative running, or skip without Rhino.

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/RookNative/Handlers/DirectorHandler.h src/RookNative/Handlers/DirectorHandler.cpp src/RookNative/RookServer.h src/RookNative/RookServer.cpp src/RookNative/RookNative.vcxproj src/RookNative/RookNative.vcxproj.filters
git commit -m "feat: add director native context routes"
```

## Phase 3: Native Guarded Frame Transaction

### Task 8: Extend Live Tests For Frame Capture Failure Boundaries

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add path security and validation tests**

Append:

```python
@pytest.mark.asyncio
async def test_director_frame_capture_rejects_path_outside_allowed_root(requires_rhino, tmp_path):
    instruction = {
        "schema_version": 1,
        "director_version": "slice1",
        "run_id": "bad_path",
        "frame_index": 1,
        "frame_id": "frame_0001",
        "run_root": str(tmp_path / "outside"),
        "output_path": str(tmp_path / "outside" / "frame_0001.png"),
        "resolution": {"width": 320, "height": 180},
        "display": {"mode": "Rendered"},
        "camera": {
            "projection": "perspective",
            "location": [4, -4, 3],
            "target": [0, 0, 0],
            "up": [0, 0, 1],
            "lens_length": 35.0,
            "fov_degrees": None,
            "parallel_scale": None,
            "near_clip": None,
            "far_clip": None,
            "aspect": 1.7778,
        },
        "object_transforms": [],
    }
    result = await call_rhino("/director/frame-capture", "POST", instruction)
    assert result["success"] is False
    assert "output" in str(result["data"]).lower()
```

- [ ] **Step 2: Run live tests and verify failure**

Run:

```powershell
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected with Rhino/RookNative running: path-security test fails until native validation is implemented. Expected without Rhino: skipped.

### Task 9: Implement Native Frame Validation And Output Allowlist

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`

- [ ] **Step 1: Implement native-side output root policy**

In `DirectorHandler.cpp`, add a helper that resolves the allowed director root from native-side configuration only:

```cpp
// Native source of truth. Do not trust request run_root/output_path as an allowlist.
// Root contract must match Python:
// 1. ROOK_DIRECTOR_OUTPUT_ROOT if set.
// 2. Otherwise %LOCALAPPDATA%/Rook/rookvision_director.
// Do not include repo/knowledge or request-provided roots as implicit fallbacks.
```

Required behavior:

- canonicalize allowed roots, `run_root`, and `output_path`;
- reject if `run_root` is outside every allowed root;
- reject if `output_path` is not below `run_root`;
- reject path traversal after canonicalization;
- create only directories below an allowed root.

- [ ] **Step 2: Implement schema and pre-mutation validation**

Validation must reject before any document or viewport mutation when:

- `schema_version != 1`;
- `director_version != "slice1"`;
- `frame_index < 1`;
- `resolution.width <= 0` or `resolution.height <= 0`;
- display mode cannot be resolved;
- camera vectors are missing or degenerate;
- projection is unsupported;
- any object ID is missing or unresolvable;
- object is not a top-level document object;
- source-state bbox mismatch exceeds tolerance;
- transform matrix is not 4x4 numeric.

Evidence error shape:

```json
{
  "frame_id": "frame_0001",
  "frame_index": 1,
  "success": false,
  "dirty_partial_state": false,
  "error": {
    "code": "invalid_input",
    "message": "resolution width and height must be positive"
  },
  "affected_object_ids": []
}
```

- [ ] **Step 3: Run native build**

Run:

```cmd
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds or records exact unavailable-toolchain error.

- [ ] **Step 4: Run live route tests**

Run:

```powershell
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected: path-security and validation tests pass with Rhino/RookNative running.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/RookNative/Handlers/DirectorHandler.cpp mcp_server/tests/test_director_routes_live.py
git commit -m "feat: validate director frame transactions"
```

### Task 10: Implement Native Snapshot, Capture, Restore, And Evidence

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add live success smoke test**

Extend `mcp_server/tests/test_director_routes_live.py` with a fixture-backed smoke test that:

- creates or uses a simple top-level object through existing test helpers;
- gets `/director/object-states`;
- gets `/director/view-state`;
- writes a frame into an allowed director output root;
- verifies `success: true`;
- verifies output file exists and has nonzero size;
- verifies evidence contains `objects_restored`, `viewport_restored`, `dirty_partial_state: false`, and `validation_strength`.

Expected assertion shape:

```python
assert result["success"] is True
data = result["data"]
assert data["dirty_partial_state"] is False
assert data["objects"]["restored"] == data["objects"]["requested"]
assert data["viewport"]["restored"] is True
assert Path(data["output_path"]).exists()
assert Path(data["output_path"]).stat().st_size > 0
```

- [ ] **Step 2: Implement guard classes or scoped structs**

In `DirectorHandler.cpp`, implement scoped guards with explicit `Restore()`:

```cpp
struct DirectorObjectPoseGuard
{
    bool Restore(nlohmann::json& evidence);
    ~DirectorObjectPoseGuard();
};

struct DirectorViewportGuard
{
    bool Restore(nlohmann::json& evidence);
    ~DirectorViewportGuard();
};
```

Rules:

- destructors perform best-effort restore only;
- the route calls `Restore()` explicitly before building final evidence;
- restoration failures are written into evidence;
- verification uses the same tolerance as source-state validation where possible.

- [ ] **Step 3: Apply frame, capture, and restore**

Implement `HandleDirectorFrameCapture` so the transaction order is:

1. parse request;
2. pre-mutation validate;
3. resolve active viewport at transaction start;
4. snapshot object pose state and viewport camera/display mode;
5. apply object delta transforms using existing `TransformObject` and redraw patterns;
6. apply explicit camera/display state using existing viewport/display patterns;
7. capture PNG to a temp file inside the target directory;
8. verify temp file exists and has nonzero size;
9. replace target output path;
10. explicitly restore objects and viewport;
11. verify restoration;
12. return evidence.

- [ ] **Step 4: Run native build and live smoke**

Run:

```cmd
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected: build succeeds if toolchain is available; live tests pass or skip without Rhino.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/RookNative/Handlers/DirectorHandler.cpp mcp_server/tests/test_director_routes_live.py
git commit -m "feat: capture director frames transactionally"
```

## Phase 4: End-To-End Slice Proof

### Task 11: Add Python-To-Native End-To-End Smoke Test

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add end-to-end live test**

Append a live test that calls `director.run_director` with:

```python
request = {
    "object_ids": [created_object_id_1, created_object_id_2],
    "frame_count": 3,
    "resolution": {"width": 320, "height": 180},
    "display": {"mode": "Rendered"},
    "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
    "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 2.0}},
}
```

Assertions:

```python
assert result["state"] == "complete"
run_root = Path(result["run_root"])
assert (run_root / "manifest.json").exists()
assert (run_root / "status.json").exists()
assert (run_root / "logs" / "frame_evidence.jsonl").exists()
assert (run_root / "frames" / "frame_0001.png").exists()
assert (run_root / "frames" / "frame_0002.png").exists()
assert (run_root / "frames" / "frame_0003.png").exists()
manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
assert manifest["frames"][0]["object_transforms"][0]["transform"] == director.identity_matrix()
assert len((run_root / "logs" / "frame_evidence.jsonl").read_text(encoding="utf-8").splitlines()) == 3
```

- [ ] **Step 2: Run all director tests**

Run:

```powershell
pytest mcp_server/tests/test_director.py mcp_server/tests/test_director_mcp_tools.py -q
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected: pure Python tests pass; live tests pass with Rhino/RookNative running or skip without Rhino.

- [ ] **Step 3: Add manual visual smoke notes**

Open the run folder from the live test and inspect:

- `frame_0001.png` is nonblank and un-exploded;
- final frame is visibly exploded;
- if two camera keyframes are included in a manual run, framing changes.

Record the inspected run folder path in the final response. These are smoke checks, not formal visual regression thresholds.

- [ ] **Step 4: Commit**

Run:

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test: prove director slice one end to end"
```

## Final Verification

- [ ] **Run Python unit and MCP tests**

```powershell
pytest mcp_server/tests/test_director.py mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: pass.

- [ ] **Run live Rhino tests**

```powershell
pytest mcp_server/tests/test_director_routes_live.py -q -m requires_rhino
```

Expected: pass with Rhino/RookNative running, or skip without Rhino.

- [ ] **Build native when toolchain is available**

```cmd
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: pass if Rhino 8 SDK and MFC toolchain are available. If unavailable, report the exact reason.

- [ ] **Review generated run artifacts**

Verify one successful run contains:

```text
manifest.json
status.json
frames/frame_0001.png
frames/frame_0002.png
frames/frame_0003.png
logs/frame_evidence.jsonl
```

Expected:

- `status.json.state == "complete"`;
- evidence line count equals frame count;
- each evidence object records `dirty_partial_state: false`;
- manifest records `document_units`, source object provenance, `motion.strategy`, camera provenance, resolved per-frame cameras, and resolved source-relative transforms.

## Self-Review

- Spec coverage: Python owns orchestration; native owns per-frame transaction; manifest/status/evidence are separate; output allowlist is native-side; source-state validation has explicit strength; failed and unsafe states are distinct.
- Placeholder scan: no vague error-handling instruction remains without concrete error states or evidence shape.
- Type consistency: `schema_version`, `director_version`, `frame_index`, `frame_id`, `run_root`, `output_path`, `resolution`, `display`, `camera`, `object_transforms`, `source_state`, `validation_strength`, and `dirty_partial_state` match the approved design.
- Review caveat carried forward: Phase 0 decides the first acceptable `validation_strength` values before implementation; the enum does not grow ad hoc.
- Repo constraint carried forward: `.vcxproj` and `.filters` edits require explicit user approval at execution time.
