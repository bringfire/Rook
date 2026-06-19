# RookVisionDirector Animation Track (PR1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the baked **animation track** artifact and make `run_director` bake it, validate it, freeze it to `<run>/animation_track.json`, and capture frames *from it* — with zero change to existing run behavior or manifest shape (parity).

**Architecture:** A new pure-Python module `animation_track.py` owns the two-section track schema (`camera_frames` + `object_frames`), its completeness validation, and an atomic freeze-to-disk. `director.run_director` is refactored to assemble the track from the camera plan and the existing radial motion frames, validate it in memory (before any run directory is created), freeze it alongside `manifest.json`, and derive the per-frame capture instructions from the track. The existing `manifest.json` fields are preserved unchanged; the track is purely additive.

**Tech Stack:** Python 3.11+, `pytest` / `pytest-asyncio`, no new dependencies. Follows the existing director idiom: hand-rolled validation raising typed errors, atomic JSON writes.

## Global Constraints

These apply to **every** task; values are copied verbatim from the spec (`docs/superpowers/specs/2026-06-19-rookvisiondirector-arbitrary-motion-replay-design.md`):

- Track top-level metadata: `schema_version = 1`, `animation_version = "v1"`, `transform_semantics = "absolute_from_source"` (the semantics value scopes object motion only).
- `object_frames` entries use native's existing `object_transforms[]` shape directly: each entry is `{object_id, source_state, transform}` — no map format, no lossy adapter.
- **Completeness:** the track declares `animated_object_ids` once; **every frame must carry a transform entry for exactly that set**; identity transforms are allowed; a missing entry is a **validation error**, never an implicit identity.
- The track is **one file, two sections**: shared metadata + `camera_frames` (one explicit camera per frame) + `object_frames`. `camera_frames` keeps its own provenance; `absolute_from_source`/source-hash guarantees apply to `object_frames`.
- **Backward compatibility:** existing `radial_bbox_center` / `keyframes` / `curve_follow_target` requests keep working; the track is **additive**; all existing `manifest.json` fields are preserved. The full existing `mcp_server/tests/test_director.py` suite must stay green.
- **Out of PR1 scope (do not build here):** native `/director/replay`, MCP tool changes, the agent-script generator, the draft-before-capture lifecycle (PR1 ships the *frozen* artifact + the `build`/`validate`/`freeze` functions the PR2 draft path will reuse), additional generators, video/publish changes. PR1 touches **no** C++ and **no** `server.py`.
- Style: validation raises a typed exception (`AnimationTrackError`) with a message naming the offending field, mirroring `director.DirectorInputError`. JSON writes are atomic (temp file + `replace`). `animation_track.py` must **not** import `director` (director imports it — avoid a cycle).
- **Dirty worktree caution:** the repo has unrelated pre-existing modifications (`mcp_server/src/rook/server.py`, `knowledge/gh/component_observations.json`). Every commit stages **only** the explicit files named in its task — never `git add -A` or `git add .`.
- **Validation strength:** because PR2 (replay) depends on this artifact, validation is comprehensive — input guards in `build_animation_track` (fail with `AnimationTrackError`, never `IndexError`), full top-level metadata checks (`fps`, `resolution`, `animated_object_ids`, `camera_frames[*].camera`), and per-entry `object_transforms` checks (`object_id`, `source_state`, `validation_strength`, bbox fields when `bbox_only`).

**Working directory:** `mcp_server/` (run `pytest` from there). Branch: `feature/rookvisiondirector-arbitrary-motion-replay` (already checked out).

---

## File Structure

- **Create** `mcp_server/src/rook/animation_track.py` — the animation-track schema: constants, `AnimationTrackError`, `build_animation_track`, `validate_animation_track`, `freeze_animation_track`, and a local `_atomic_write_json`. One responsibility: the track artifact. No director import.
- **Create** `mcp_server/tests/test_animation_track.py` — unit tests for build/validate/freeze.
- **Modify** `mcp_server/src/rook/director.py` — `run_director` assembles, validates, freezes, and captures-from the track. (`import` the new module at top with the other `from . import ...` line.)
- **Modify** `mcp_server/tests/test_director.py` — add the track-freeze and capture-from-track parity tests.

---

## Task 1: Animation track module — constants + `build_animation_track`

**Files:**
- Create: `mcp_server/src/rook/animation_track.py`
- Test: `mcp_server/tests/test_animation_track.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `ANIMATION_SCHEMA_VERSION = 1`, `ANIMATION_VERSION = "v1"`, `TRANSFORM_SEMANTICS = "absolute_from_source"`
  - `class AnimationTrackError(Exception)`
  - `build_animation_track(*, frame_count: int, fps: int | None, resolution: dict[str, int], camera_per_frame: list[dict], motion_frames: list[dict], camera_provenance: dict, object_provenance: dict) -> dict`
    - `camera_per_frame`: list length `frame_count`, each an explicit camera dict.
    - `motion_frames`: list length `frame_count`, each `{"frame_index": int, "object_transforms": [{object_id, source_state, transform}]}` (exactly what `director.expand_radial_bbox_center` returns).
    - Returns the track dict: `schema_version`, `animation_version`, `frame_count`, `fps`, `resolution`, `transform_semantics`, `animated_object_ids` (list, derived from `motion_frames[0]`), `camera_frames` (`[{frame_index, camera}]`), `object_frames` (`[{frame_index, object_transforms}]`), `camera_provenance`, `object_provenance`.

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_animation_track.py`:

```python
from __future__ import annotations

import pytest

from rook import animation_track


def _identity():
    return [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def _camera(location):
    return {
        "projection": "perspective",
        "location": location,
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "lens_length": 35.0,
        "fov_degrees": None,
        "parallel_scale": None,
        "near_clip": None,
        "far_clip": None,
        "aspect": 1.7778,
    }


def _motion_frame(frame_index, object_id="a"):
    return {
        "frame_index": frame_index,
        "object_transforms": [
            {
                "object_id": object_id,
                "source_state": {
                    "bbox_min": [0, 0, 0],
                    "bbox_max": [1, 1, 1],
                    "validation_strength": "bbox_only",
                    "state_hash": None,
                },
                "transform": _identity(),
            }
        ],
    }


def test_build_animation_track_assembles_two_sections_and_metadata():
    track = animation_track.build_animation_track(
        frame_count=2,
        fps=24,
        resolution={"width": 320, "height": 180},
        camera_per_frame=[_camera([4, -4, 3]), _camera([6, -4, 3])],
        motion_frames=[_motion_frame(1), _motion_frame(2)],
        camera_provenance={"strategy": "keyframes"},
        object_provenance={"generator": "radial_bbox_center"},
    )

    assert track["schema_version"] == 1
    assert track["animation_version"] == "v1"
    assert track["transform_semantics"] == "absolute_from_source"
    assert track["frame_count"] == 2
    assert track["fps"] == 24
    assert track["resolution"] == {"width": 320, "height": 180}
    assert track["animated_object_ids"] == ["a"]
    assert [f["frame_index"] for f in track["camera_frames"]] == [1, 2]
    assert track["camera_frames"][1]["camera"]["location"] == [6, -4, 3]
    assert [f["frame_index"] for f in track["object_frames"]] == [1, 2]
    assert track["object_frames"][0]["object_transforms"][0]["object_id"] == "a"
    assert track["camera_provenance"] == {"strategy": "keyframes"}
    assert track["object_provenance"] == {"generator": "radial_bbox_center"}


def test_build_rejects_empty_motion_frames():
    with pytest.raises(animation_track.AnimationTrackError, match="motion_frames"):
        animation_track.build_animation_track(
            frame_count=1,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=[],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_camera_motion_length_mismatch():
    with pytest.raises(animation_track.AnimationTrackError, match="frame_count"):
        animation_track.build_animation_track(
            frame_count=2,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=[_motion_frame(1), _motion_frame(2)],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_bad_frame_count():
    with pytest.raises(animation_track.AnimationTrackError, match="frame_count"):
        animation_track.build_animation_track(
            frame_count=0,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[],
            motion_frames=[],
            camera_provenance={},
            object_provenance={},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_animation_track.py -k build -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.animation_track'`.

- [ ] **Step 3: Write minimal implementation**

Create `mcp_server/src/rook/animation_track.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ANIMATION_SCHEMA_VERSION = 1
ANIMATION_VERSION = "v1"
TRANSFORM_SEMANTICS = "absolute_from_source"


class AnimationTrackError(Exception):
    pass


def build_animation_track(
    *,
    frame_count: int,
    fps: int | None,
    resolution: dict[str, int],
    camera_per_frame: list[dict[str, Any]],
    motion_frames: list[dict[str, Any]],
    camera_provenance: dict[str, Any],
    object_provenance: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise AnimationTrackError("frame_count must be an integer >= 1")
    if len(camera_per_frame) != frame_count:
        raise AnimationTrackError("camera_per_frame length must equal frame_count")
    if len(motion_frames) != frame_count:
        raise AnimationTrackError("motion_frames length must equal frame_count")

    animated_object_ids = [
        transform["object_id"]
        for transform in motion_frames[0]["object_transforms"]
    ]
    camera_frames = [
        {"frame_index": index + 1, "camera": camera_per_frame[index]}
        for index in range(frame_count)
    ]
    object_frames = [
        {
            "frame_index": frame["frame_index"],
            "object_transforms": frame["object_transforms"],
        }
        for frame in motion_frames
    ]
    return {
        "schema_version": ANIMATION_SCHEMA_VERSION,
        "animation_version": ANIMATION_VERSION,
        "frame_count": frame_count,
        "fps": fps,
        "resolution": resolution,
        "transform_semantics": TRANSFORM_SEMANTICS,
        "animated_object_ids": animated_object_ids,
        "camera_frames": camera_frames,
        "object_frames": object_frames,
        "camera_provenance": camera_provenance,
        "object_provenance": object_provenance,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_animation_track.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/animation_track.py mcp_server/tests/test_animation_track.py
git commit -m "feat(director): add animation_track.build_animation_track"
```

---

## Task 2: `validate_animation_track` — schema + completeness

**Files:**
- Modify: `mcp_server/src/rook/animation_track.py`
- Test: `mcp_server/tests/test_animation_track.py`

**Interfaces:**
- Consumes: `build_animation_track` (Task 1), `AnimationTrackError`.
- Produces: `validate_animation_track(track: dict) -> None` — raises `AnimationTrackError` (message names the field) when the track is structurally invalid; returns `None` on success.

Validation rules (each raises with a message containing the quoted token below):
- `schema_version` must equal `1` → `"schema_version"`.
- `animation_version` must equal `"v1"` → `"animation_version"`.
- `transform_semantics` must equal `"absolute_from_source"` → `"transform_semantics"`.
- `frame_count` must be an `int >= 1` → `"frame_count"`.
- `len(camera_frames) == frame_count` and its `frame_index` values are exactly `1..frame_count` in order → `"camera_frames"`.
- `len(object_frames) == frame_count` and its `frame_index` values are exactly `1..frame_count` in order → `"object_frames"`.
- For every object frame, the set of `object_transforms[*].object_id` equals `set(animated_object_ids)` (no missing, no extra) → `"animated_object_ids"`.
- Every `transform` is a 4×4 list of finite numbers → `"transform"`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_animation_track.py` (`pytest` is already imported at the top of the file from Task 1):

```python
import math


def _valid_track():
    return animation_track.build_animation_track(
        frame_count=2,
        fps=24,
        resolution={"width": 320, "height": 180},
        camera_per_frame=[_camera([4, -4, 3]), _camera([6, -4, 3])],
        motion_frames=[_motion_frame(1), _motion_frame(2)],
        camera_provenance={"strategy": "keyframes"},
        object_provenance={"generator": "radial_bbox_center"},
    )


def test_validate_accepts_well_formed_track():
    animation_track.validate_animation_track(_valid_track())


def test_validate_rejects_missing_object_in_a_frame():
    track = _valid_track()
    track["object_frames"][1]["object_transforms"] = []
    with pytest.raises(animation_track.AnimationTrackError, match="animated_object_ids"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_extra_object_in_a_frame():
    track = _valid_track()
    extra = _motion_frame(2, object_id="b")["object_transforms"][0]
    track["object_frames"][1]["object_transforms"].append(extra)
    with pytest.raises(animation_track.AnimationTrackError, match="animated_object_ids"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_camera_frame_count_mismatch():
    track = _valid_track()
    track["camera_frames"] = track["camera_frames"][:1]
    with pytest.raises(animation_track.AnimationTrackError, match="camera_frames"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_non_finite_transform():
    track = _valid_track()
    track["object_frames"][0]["object_transforms"][0]["transform"][0][3] = math.inf
    with pytest.raises(animation_track.AnimationTrackError, match="transform"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_bad_transform_semantics():
    track = _valid_track()
    track["transform_semantics"] = "relative_from_previous"
    with pytest.raises(animation_track.AnimationTrackError, match="transform_semantics"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_bool_fps():
    track = _valid_track()
    track["fps"] = True
    with pytest.raises(animation_track.AnimationTrackError, match="fps"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_nonpositive_resolution():
    track = _valid_track()
    track["resolution"] = {"width": 0, "height": 180}
    with pytest.raises(animation_track.AnimationTrackError, match="resolution"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_duplicate_animated_object_ids():
    track = _valid_track()
    track["animated_object_ids"] = ["a", "a"]
    with pytest.raises(animation_track.AnimationTrackError, match="animated_object_ids"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_missing_validation_strength():
    track = _valid_track()
    del track["object_frames"][0]["object_transforms"][0]["source_state"][
        "validation_strength"
    ]
    with pytest.raises(animation_track.AnimationTrackError, match="validation_strength"):
        animation_track.validate_animation_track(track)


def test_validate_rejects_missing_bbox_for_bbox_only():
    track = _valid_track()
    del track["object_frames"][0]["object_transforms"][0]["source_state"]["bbox_min"]
    with pytest.raises(animation_track.AnimationTrackError, match="bbox_min"):
        animation_track.validate_animation_track(track)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_animation_track.py -k validate -v`
Expected: FAIL with `AttributeError: module 'rook.animation_track' has no attribute 'validate_animation_track'`.

- [ ] **Step 3: Write minimal implementation**

Append to `mcp_server/src/rook/animation_track.py`:

```python
import math


def _is_4x4_finite(matrix: Any) -> bool:
    if not isinstance(matrix, list) or len(matrix) != 4:
        return False
    for row in matrix:
        if not isinstance(row, list) or len(row) != 4:
            return False
        for value in row:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            if not math.isfinite(float(value)):
                return False
    return True


def _validate_frame_index_sequence(frames: list[dict[str, Any]], frame_count: int, field: str) -> None:
    if not isinstance(frames, list) or len(frames) != frame_count:
        raise AnimationTrackError(
            f"{field} must contain exactly frame_count ({frame_count}) entries"
        )
    for position, frame in enumerate(frames, start=1):
        if frame.get("frame_index") != position:
            raise AnimationTrackError(
                f"{field} frame_index must be 1..frame_count in order"
            )


def validate_animation_track(track: dict[str, Any]) -> None:
    if track.get("schema_version") != ANIMATION_SCHEMA_VERSION:
        raise AnimationTrackError("schema_version must be 1")
    if track.get("animation_version") != ANIMATION_VERSION:
        raise AnimationTrackError("animation_version must be 'v1'")
    if track.get("transform_semantics") != TRANSFORM_SEMANTICS:
        raise AnimationTrackError(
            "transform_semantics must be 'absolute_from_source'"
        )

    frame_count = track.get("frame_count")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise AnimationTrackError("frame_count must be an integer >= 1")

    fps = track.get("fps")
    if fps is not None and (not isinstance(fps, int) or isinstance(fps, bool) or fps < 1):
        raise AnimationTrackError("fps must be null or a positive integer")

    resolution = track.get("resolution")
    if not isinstance(resolution, dict):
        raise AnimationTrackError("resolution must be an object")
    for axis in ("width", "height"):
        value = resolution.get(axis)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise AnimationTrackError(f"resolution.{axis} must be a positive integer")

    object_ids = track.get("animated_object_ids")
    if (
        not isinstance(object_ids, list)
        or not object_ids
        or not all(isinstance(oid, str) for oid in object_ids)
        or len(set(object_ids)) != len(object_ids)
    ):
        raise AnimationTrackError(
            "animated_object_ids must be a non-empty list of unique strings"
        )

    _validate_frame_index_sequence(track.get("camera_frames"), frame_count, "camera_frames")
    _validate_frame_index_sequence(track.get("object_frames"), frame_count, "object_frames")

    for frame in track["camera_frames"]:
        if not isinstance(frame.get("camera"), dict):
            raise AnimationTrackError("camera_frames[*].camera must be an object")

    expected_ids = set(object_ids)
    for frame in track["object_frames"]:
        transforms = frame.get("object_transforms")
        if not isinstance(transforms, list):
            raise AnimationTrackError("object_frames.object_transforms must be a list")
        frame_ids = [t.get("object_id") for t in transforms]
        if set(frame_ids) != expected_ids or len(frame_ids) != len(expected_ids):
            raise AnimationTrackError(
                "every object frame must cover exactly animated_object_ids "
                f"(frame {frame.get('frame_index')})"
            )
        for transform in transforms:
            if not isinstance(transform.get("object_id"), str):
                raise AnimationTrackError("object_transforms.object_id must be a string")
            source_state = transform.get("source_state")
            if not isinstance(source_state, dict):
                raise AnimationTrackError(
                    "object_transforms.source_state must be an object"
                )
            strength = source_state.get("validation_strength")
            if not isinstance(strength, str):
                raise AnimationTrackError(
                    "source_state.validation_strength is required"
                )
            if strength == "bbox_only":
                for bbox_field in ("bbox_min", "bbox_max"):
                    box = source_state.get(bbox_field)
                    if not isinstance(box, list) or len(box) != 3:
                        raise AnimationTrackError(
                            f"source_state.{bbox_field} is required for bbox_only"
                        )
            if not _is_4x4_finite(transform.get("transform")):
                raise AnimationTrackError(
                    "object_transforms.transform must be a 4x4 matrix of finite numbers"
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_animation_track.py -v`
Expected: PASS (all build + validate tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/animation_track.py mcp_server/tests/test_animation_track.py
git commit -m "feat(director): add animation track schema + completeness validation"
```

---

## Task 3: `freeze_animation_track` — validate-then-atomic-write

**Files:**
- Modify: `mcp_server/src/rook/animation_track.py`
- Test: `mcp_server/tests/test_animation_track.py`

**Interfaces:**
- Consumes: `validate_animation_track` (Task 2).
- Produces: `freeze_animation_track(track: dict, path: str | Path) -> None` — validates the track, then atomically writes it as pretty JSON to `path`. If validation fails, raises `AnimationTrackError` and writes **no** file.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_animation_track.py`:

```python
import json


def test_freeze_writes_valid_track_json(tmp_path):
    path = tmp_path / "run" / "animation_track.json"
    animation_track.freeze_animation_track(_valid_track(), path)

    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["frame_count"] == 2
    assert loaded["animated_object_ids"] == ["a"]


def test_freeze_rejects_invalid_track_without_writing(tmp_path):
    path = tmp_path / "run" / "animation_track.json"
    bad = _valid_track()
    bad["object_frames"][1]["object_transforms"] = []
    with pytest.raises(animation_track.AnimationTrackError):
        animation_track.freeze_animation_track(bad, path)
    assert not path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_animation_track.py -k freeze -v`
Expected: FAIL with `AttributeError: ... has no attribute 'freeze_animation_track'`.

- [ ] **Step 3: Write minimal implementation**

Append to `mcp_server/src/rook/animation_track.py`:

```python
def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def freeze_animation_track(track: dict[str, Any], path: str | Path) -> None:
    validate_animation_track(track)
    _atomic_write_json(Path(path), track)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_animation_track.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/animation_track.py mcp_server/tests/test_animation_track.py
git commit -m "feat(director): add freeze_animation_track (validate then atomic write)"
```

---

## Task 4: `run_director` bakes, validates, and freezes the track

**Files:**
- Modify: `mcp_server/src/rook/director.py` (import line near top; build/validate after motion is computed; freeze after run directories exist)
- Test: `mcp_server/tests/test_director.py`

**Interfaces:**
- Consumes: `animation_track.build_animation_track`, `validate_animation_track`, `freeze_animation_track`.
- Produces: a frozen `<run_root>/animation_track.json` whose `camera_frames[i].camera` and `object_frames[i].object_transforms` equal the corresponding `manifest.json` `frames[i]` values (parity). No change to `manifest.json`.

In `director.py`, `run_director` currently (around lines 272–285) computes `frame_cameras`, `plan_provenance`, `motion_params`, and `motion_frames`/`motion_warnings`, then (around 287–305) creates `run_root`/`frames_dir`/`logs_dir` and builds `manifest_frames`, then (330–369) writes `manifest.json` and `status.json`. This task inserts a track build+validate (in memory, after motion is computed) and a freeze (after the run directories exist), leaving the manifest path untouched.

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_director.py`:

```python
def test_run_writes_animation_track_in_parity_with_manifest(tmp_path):
    request = _run_request(tmp_path)
    request["run_id"] = "track-parity"
    request["frame_count"] = 3
    request["camera_keyframes"] = [
        {"frame_index": 1, "source": {"kind": "active_view"}},
        {"frame_index": 3, "source": {"kind": "named_view", "name": "End"}},
    ]
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0003", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    result = asyncio.run(
        director.run_director(request, call_native=fake, runtime=_runtime(tmp_path))
    )
    run_root = Path(result["run_root"])

    track = json.loads((run_root / "animation_track.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))

    assert track["schema_version"] == 1
    assert track["animation_version"] == "v1"
    assert track["transform_semantics"] == "absolute_from_source"
    assert track["frame_count"] == 3
    assert track["animated_object_ids"] == ["a"]
    assert track["object_provenance"]["generator"] == "radial_bbox_center"

    # Parity: each track section equals the corresponding manifest frame value.
    for index, manifest_frame in enumerate(manifest["frames"]):
        assert track["camera_frames"][index]["camera"] == manifest_frame["camera"]
        assert (
            track["object_frames"][index]["object_transforms"]
            == manifest_frame["object_transforms"]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_director.py::test_run_writes_animation_track_in_parity_with_manifest -v`
Expected: FAIL — `animation_track.json` does not exist (`FileNotFoundError`).

- [ ] **Step 3: Add the import**

In `director.py`, extend the existing relative import line:

```python
from . import camera_planner, timeline, animation_track
```

- [ ] **Step 4: Build + validate the track in memory after motion is computed**

In `run_director`, immediately after the `motion_frames, motion_warnings = expand_radial_bbox_center(...)` call (currently ~line 280–285) and **before** `run_root = (output_root / run_id).resolve()`, insert:

```python
    object_provenance = {
        "generator": "radial_bbox_center",
        "parameters": motion_params,
        "script_artifact_id": None,
        "warnings": motion_warnings,
    }
    camera_provenance = {
        "strategy": camera_plan["strategy"],
        "request_shape": plan_provenance.get("request_shape"),
        "aspect_authority": plan_provenance.get("aspect_authority"),
        "optics_authority": plan_provenance.get("optics_authority"),
    }
    track = animation_track.build_animation_track(
        frame_count=frame_count,
        fps=timeline_manifest.get("fps"),
        resolution=request["resolution"],
        camera_per_frame=frame_cameras,
        motion_frames=motion_frames,
        camera_provenance=camera_provenance,
        object_provenance=object_provenance,
    )
    animation_track.validate_animation_track(track)
```

- [ ] **Step 5: Freeze the track before manifest/status are written**

The frozen `animation_track.json` is PR1's deliverable, so it must be written **before** `manifest.json` and `status.json` — a freeze failure must not leave a run folder carrying a manifest but no track. In `run_director`, immediately after the run directories are created (after `logs_dir.mkdir(parents=True, exist_ok=True)`, ~line 291) and before `manifest_frames` is built, insert:

```python
    animation_track.freeze_animation_track(track, run_root / "animation_track.json")
```

(`freeze_animation_track` re-validates before writing, so the in-memory `validate_animation_track` call in Step 4 plus this freeze give two gates; that is intentional and cheap.)

- [ ] **Step 6: Run the new test and the full director suite**

Run: `python -m pytest tests/test_director.py::test_run_writes_animation_track_in_parity_with_manifest tests/test_animation_track.py -v`
Expected: PASS.

Run: `python -m pytest tests/test_director.py -v`
Expected: PASS (all existing tests still green — manifest shape unchanged).

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/director.py mcp_server/tests/test_director.py
git commit -m "feat(director): bake, validate, and freeze animation_track.json per run"
```

---

## Task 5: `run_director` captures frames from the track

**Files:**
- Modify: `mcp_server/src/rook/director.py` (`manifest_frames` construction; the freeze placement from Task 4 moves earlier)
- Test: `mcp_server/tests/test_director.py`

**Interfaces:**
- Consumes: the in-memory `track` built in Task 4.
- Produces: the per-frame capture instructions (and `manifest_frames`) are derived from `track["camera_frames"]` + `track["object_frames"]`, making the track the single source of truth for what gets captured. External behavior and `manifest.json` shape are unchanged (parity).

Currently `manifest_frames` (lines ~293–305) is built by zipping `motion_frames` with `frame_cameras[index - 1]`. This task rebuilds `manifest_frames` from the track instead, so the frame-capture loop (which already reads `frame["camera"]` and `frame["object_transforms"]`) is driven by the track.

- [ ] **Step 1: Write the failing test**

This test proves the *source of truth* — not just parity. It monkeypatches the track build to inject a sentinel camera location that radial motion / `frame_cameras` would never produce, then asserts the capture payloads carry the sentinel. Before the refactor, capture is sourced from `frame_cameras` (real interpolated locations), so the sentinel assertion **fails**; after the refactor it is sourced from the track and **passes**. An incidental pass is impossible.

Append to `mcp_server/tests/test_director.py`:

```python
def test_capture_is_sourced_from_the_track_not_motion(tmp_path, monkeypatch):
    real_build = director.animation_track.build_animation_track

    def sentinel_build(**kwargs):
        track = real_build(**kwargs)
        for camera_frame in track["camera_frames"]:
            camera_frame["camera"] = {
                **camera_frame["camera"],
                "location": [99.0, 99.0, 99.0],
            }
        return track

    monkeypatch.setattr(
        director.animation_track, "build_animation_track", sentinel_build
    )

    request = _run_request(tmp_path)
    request["run_id"] = "capture-source-of-truth"
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    asyncio.run(
        director.run_director(request, call_native=fake, runtime=_runtime(tmp_path))
    )

    capture_calls = [c for c in fake.calls if c[0] == "/director/frame-capture"]
    assert capture_calls, "expected frame-capture calls"
    for call in capture_calls:
        assert call[2]["camera"]["location"] == [99.0, 99.0, 99.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_director.py::test_capture_is_sourced_from_the_track_not_motion -v`
Expected: FAIL — capture still reads `frame_cameras` (real interpolated location `[4.0, -4.0, 3.0]`), not the sentinel `[99.0, 99.0, 99.0]`. This proves the test is red before the refactor.

- [ ] **Step 3: Rebuild `manifest_frames` from the track**

Replace the existing `manifest_frames` construction loop (currently ~lines 293–305):

```python
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
```

with a version sourced from the track:

```python
    manifest_frames = []
    for camera_frame, object_frame in zip(
        track["camera_frames"], track["object_frames"]
    ):
        index = camera_frame["frame_index"]
        frame_name = _frame_id(index)
        manifest_frames.append(
            {
                "frame_index": index,
                "frame_id": frame_name,
                "camera": camera_frame["camera"],
                "object_transforms": object_frame["object_transforms"],
                "output_path": str((frames_dir / f"{frame_name}.png").resolve()),
            }
        )
```

- [ ] **Step 4: Run the new test and the full suites**

Run: `python -m pytest tests/test_director.py::test_capture_is_sourced_from_the_track_not_motion tests/test_director.py::test_run_writes_animation_track_in_parity_with_manifest -v`
Expected: PASS.

Run: `python -m pytest tests/test_director.py tests/test_animation_track.py -v`
Expected: PASS (full parity — every existing director test stays green).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director.py mcp_server/tests/test_director.py
git commit -m "refactor(director): derive frame capture from the baked animation track"
```

---

## Task 6: Full regression sweep + branch verification

**Files:** none (verification only).

- [ ] **Step 1: Run the Director-related suites**

Run: `python -m pytest tests/test_animation_track.py tests/test_director.py tests/test_timeline.py tests/test_camera_planner.py -v`
Expected: PASS. (These are the non-live suites touching the director path; live suites — `test_director_routes_live.py` — require Rhino and are out of scope for PR1.)

- [ ] **Step 2: Confirm no unintended files changed**

Run: `git status --short`
Expected: clean working tree (all changes already committed across Tasks 1–5).

- [ ] **Step 3: Confirm PR1 touched only the intended files**

Run: `git diff --name-only main...HEAD`
Expected: exactly `docs/superpowers/specs/2026-06-19-...-design.md`, `docs/superpowers/plans/2026-06-19-...-pr1.md`, `mcp_server/src/rook/animation_track.py`, `mcp_server/src/rook/director.py`, `mcp_server/tests/test_animation_track.py`, `mcp_server/tests/test_director.py`. No `server.py`, no C++.

---

## Self-Review

**Spec coverage (PR1 slice = "schema + radial port + `run_director` captures-from-track, draft↔frozen, parity test"):**
- Animation-track schema (two sections, `absolute_from_source`, `animated_object_ids`, completeness) → Tasks 1–2.
- Hardened validation for the PR2 dependency: build-time input guards (Task 1: empty/length/frame_count), full metadata validation, and per-entry `source_state`/`validation_strength`/bbox checks (Task 2) → so no malformed track can be frozen.
- `object_frames` use native `object_transforms` shape (lossless) → Task 1 (`motion_frames` passed through unchanged).
- Radial port emits track `object_frames` → Task 4 (radial `motion_frames` feed `build_animation_track`; `object_provenance.generator == "radial_bbox_center"`).
- Camera section from existing planner → Task 4 (`frame_cameras` → `camera_per_frame`).
- Run-scoped frozen `<run>/animation_track.json` → Tasks 3–4. (Draft-before-capture lifecycle is explicitly deferred to PR2 per Global Constraints — PR1 ships the frozen artifact + the `build`/`validate`/`freeze` functions the draft path reuses.)
- Captures-from-track → Task 5.
- Parity test → Tasks 4 and 5 (track vs manifest; capture payloads vs track).
- Backward compatibility (manifest unchanged, suite green) → Tasks 4–6.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; tests have real assertions.

**Type consistency:** `build_animation_track` / `validate_animation_track` / `freeze_animation_track` names and signatures are used identically in Tasks 1–5. `motion_frames` shape (`{frame_index, object_transforms:[{object_id, source_state, transform}]}`) matches `director.expand_radial_bbox_center`'s output and the native `object_transforms` payload. `camera_per_frame` matches `camera_plan["frames"]` (the `frame_cameras` list, indexed 0..n-1). `timeline_manifest.get("fps")` matches `timeline.normalize_director_request`'s manifest (`fps` int or null).

**Scope:** single subsystem (the track artifact + director integration); no native, no `server.py`; later PRs (replay, agent-script, skills) build on this artifact.
