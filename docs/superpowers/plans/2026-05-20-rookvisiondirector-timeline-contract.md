# RookVisionDirector Timeline Contract Implementation Plan

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

**Goal:** Add a Python-only Director timeline authoring contract that derives canonical frame count and normalizes camera keyframe timing before camera planning.

**Architecture:** `director.py` remains the run orchestrator, `camera_planner.py` remains focused on camera state, and a new `timeline.py` module owns FPS/duration/frame-index semantics. The normalized request passed to `camera_planner` always contains `frame_index` keyframes, so future camera strategies and curve sampling consume one canonical timing model.

**Tech Stack:** Python 3, pytest, existing `rook.director`, existing `rook.camera_planner`, no native changes, no new dependencies.

---

## Source Documents

- Roadmap/spec: `docs/superpowers/specs/2026-05-20-rookvisiondirector-camera-video-roadmap.md`
- Current Director orchestrator: `mcp_server/src/rook/director.py`
- Current camera planner: `mcp_server/src/rook/camera_planner.py`
- Current MCP tool schema: `mcp_server/src/rook/server.py`
- Current Director tests: `mcp_server/tests/test_director.py`
- Current camera planner tests: `mcp_server/tests/test_camera_planner.py`
- Current MCP tool schema tests: `mcp_server/tests/test_director_mcp_tools.py`

## File Structure

Create:

- `mcp_server/src/rook/timeline.py`
  - Owns timeline validation, deterministic rounding, derived frame count, keyframe timing normalization, and manifest timing provenance.

- `mcp_server/tests/test_timeline.py`
  - Pure Python tests for timeline validation, endpoint mapping, exact-one timing field checks, and normalized request output.

Modify:

- `mcp_server/src/rook/director.py`
  - Call `timeline.normalize_director_request` before authoring validation and before `camera_planner`.
  - Use the normalized request for `frame_count`, camera validation, camera planning, motion expansion, and manifest timing provenance.

- `mcp_server/src/rook/server.py`
  - Update `rhino_director_run` input schema so timeline-only requests are accepted by MCP before Python validation.

- `mcp_server/tests/test_director.py`
  - Add manifest and fail-fast tests proving `timeline` requests work through `run_director`.

- `mcp_server/tests/test_director_mcp_tools.py`
  - Add schema and dispatch tests proving `timeline` is exposed without OpenAI-rejected JSON Schema keywords.

- `mcp_server/tests/test_camera_planner.py`
  - No required behavior changes. It should continue to assert the planner receives `frame_index` keyframes.

Do not modify:

- `src/RookNative/**`
- `src/Rook/**/*.cs`
- `scripts/deploy-local-testing.ps1`
- FFmpeg/video assembly code

## Contract

Legacy frame-count request remains valid:

```json
{
  "frame_count": 120,
  "camera_keyframes": [
    { "frame_index": 1, "source": { "kind": "active_view" } }
  ]
}
```

Timeline request:

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
      { "at": 1.0, "source": { "kind": "named_view", "name": "End" } }
    ]
  }
}
```

Canonical rules:

```text
derived_frame_count = round_half_up(duration_seconds * fps)
frame_time(frame_index) = (frame_index - 1) / fps
normalized_time = time / duration_seconds
frame_index = round_half_up(1 + normalized_time * (frame_count - 1))
frame_index = round_half_up(1 + at * (frame_count - 1))
```

`round_half_up` is deterministic for nonnegative values:

```python
math.floor(value + 0.5)
```

Validation:

- `fps` must be a positive integral value for this slice and normalizes to `int`.
- `duration_seconds` must be finite and positive.
- `derived_frame_count >= 1`.
- If top-level `frame_count` is present with `timeline`, it must equal `derived_frame_count`.
- Each camera keyframe must contain exactly one of `frame_index`, `time`, or `at`.
- `frame_index` must be a positive integral value in `1..frame_count`.
- `time` must be finite and in `0..duration_seconds`.
- `at` must be finite and in `0..1`.

Positive integral value means values accepted by the existing Director integer
style and normalized to `int`: JSON integers, integral floats like `24.0`, and
plain decimal strings like `"24"` are accepted; booleans, non-integral floats,
and non-decimal strings are rejected.

Active camera shape:

- If top-level `camera` is an object, normalize only `camera.keyframes`.
- If top-level `camera` is absent, normalize legacy `camera_keyframes`.
- Preserve current `camera_planner` precedence: ignored legacy `camera_keyframes` must not reject an otherwise valid explicit `camera` request.

Manifest timing provenance:

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

For legacy requests:

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

MCP tool schema contract:

- `rhino_director_run` must accept timeline-only requests through the schema.
- Schema `required` must be `["object_ids", "resolution"]`; `frame_count` remains an optional legacy property.
- Add a `timeline` object property with simple `fps` and `duration_seconds` fields.
- Preserve the existing OpenAI-compatible schema rule: no `oneOf`, `anyOf`, `allOf`, or `not` anywhere in the tool input schema.

## Task 1: Add Timeline Failing Contract Tests

**Files:**
- Create: `mcp_server/tests/test_timeline.py`

- [ ] **Step 1: Create timeline test module imports**

Create `mcp_server/tests/test_timeline.py`:

```python
from __future__ import annotations

import pytest

from rook import timeline
```

- [ ] **Step 2: Add legacy frame-count test**

Add:

```python
def test_legacy_frame_count_gets_timeline_manifest():
    normalized, manifest = timeline.normalize_director_request(
        {
            "frame_count": 3,
            "camera_keyframes": [
                {"frame_index": 1, "source": {"kind": "active_view"}}
            ],
        }
    )

    assert normalized["frame_count"] == 3
    assert normalized["camera_keyframes"] == [
        {"frame_index": 1, "source": {"kind": "active_view"}}
    ]
    assert manifest == {
        "source": "frame_count",
        "fps": None,
        "duration_seconds": None,
        "frame_count": 3,
    }
```

- [ ] **Step 3: Add timeline-derived frame count and endpoint mapping test**

Add:

```python
def test_timeline_derives_frame_count_and_maps_endpoints():
    normalized, manifest = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24, "duration_seconds": 5.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}},
                    {"time": 5.0, "source": {"kind": "named_view", "name": "End"}},
                ],
            },
        }
    )

    assert normalized["frame_count"] == 120
    assert normalized["camera"]["keyframes"] == [
        {"frame_index": 1, "source": {"kind": "active_view"}},
        {"frame_index": 120, "source": {"kind": "named_view", "name": "End"}},
    ]
    assert manifest == {
        "source": "timeline",
        "fps": 24,
        "duration_seconds": 5.0,
        "frame_count": 120,
    }
```

- [ ] **Step 4: Add normalized `at` mapping test**

Add:

```python
def test_timeline_maps_normalized_at_values():
    normalized, _ = timeline.normalize_director_request(
        {
            "timeline": {"fps": 10, "duration_seconds": 1.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"at": 0.0, "source": {"kind": "active_view"}},
                    {"at": 0.5, "source": {"kind": "named_view", "name": "Middle"}},
                    {"at": 1.0, "source": {"kind": "named_view", "name": "End"}},
                ],
            },
        }
    )

    assert [k["frame_index"] for k in normalized["camera"]["keyframes"]] == [1, 6, 10]
```

This locks half-up rounding: `1 + 0.5 * (10 - 1) == 5.5`, so midpoint maps to frame `6`.

- [ ] **Step 5: Add integral-value normalization test**

Add:

```python
def test_timeline_normalizes_integral_fps_and_frame_indexes():
    normalized, manifest = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24.0, "duration_seconds": 0.125},
            "camera_keyframes": [
                {"frame_index": "3", "source": {"kind": "active_view"}}
            ],
        }
    )

    assert normalized["frame_count"] == 3
    assert normalized["camera_keyframes"][0]["frame_index"] == 3
    assert manifest["fps"] == 24
```

- [ ] **Step 6: Add top-level frame-count consistency test**

Add:

```python
def test_timeline_rejects_inconsistent_top_level_frame_count():
    with pytest.raises(timeline.TimelineError, match="frame_count must equal"):
        timeline.normalize_director_request(
            {
                "frame_count": 119,
                "timeline": {"fps": 24, "duration_seconds": 5.0},
                "camera_keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}}
                ],
            }
        )
```

- [ ] **Step 7: Add invalid timeline validation tests**

Add:

```python
@pytest.mark.parametrize(
    ("timeline_payload", "message"),
    [
        ({"fps": 0, "duration_seconds": 5.0}, "fps"),
        ({"fps": 24.5, "duration_seconds": 5.0}, "fps"),
        ({"fps": 24, "duration_seconds": 0}, "duration_seconds"),
        ({"fps": 24, "duration_seconds": float("inf")}, "duration_seconds"),
    ],
)
def test_timeline_rejects_invalid_values(timeline_payload, message):
    with pytest.raises(timeline.TimelineError, match=message):
        timeline.normalize_director_request(
            {
                "timeline": timeline_payload,
                "camera_keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}}
                ],
            }
        )
```

- [ ] **Step 8: Add keyframe timing exclusivity and bounds tests**

Add:

```python
@pytest.mark.parametrize(
    ("keyframe", "message"),
    [
        ({"source": {"kind": "active_view"}}, "exactly one"),
        (
            {"frame_index": 1, "time": 0.0, "source": {"kind": "active_view"}},
            "exactly one",
        ),
        ({"frame_index": 0, "source": {"kind": "active_view"}}, "frame_index"),
        ({"frame_index": 1.5, "source": {"kind": "active_view"}}, "frame_index"),
        ({"frame_index": "3.5", "source": {"kind": "active_view"}}, "frame_index"),
        ({"time": -0.1, "source": {"kind": "active_view"}}, "time"),
        ({"time": 5.1, "source": {"kind": "active_view"}}, "time"),
        ({"at": -0.1, "source": {"kind": "active_view"}}, "at"),
        ({"at": 1.1, "source": {"kind": "active_view"}}, "at"),
    ],
)
def test_timeline_rejects_invalid_keyframe_timing(keyframe, message):
    with pytest.raises(timeline.TimelineError, match=message):
        timeline.normalize_director_request(
            {
                "timeline": {"fps": 24, "duration_seconds": 5.0},
                "camera": {"strategy": "keyframes", "keyframes": [keyframe]},
            }
        )
```

- [ ] **Step 9: Add active camera precedence test**

Add:

```python
def test_timeline_preserves_camera_precedence_over_legacy_keyframes():
    normalized, _ = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24, "duration_seconds": 1.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}}
                ],
            },
            "camera_keyframes": [
                {"time": 2.0, "source": {"kind": "active_view"}}
            ],
        }
    )

    assert normalized["camera"]["keyframes"] == [
        {"frame_index": 1, "source": {"kind": "active_view"}}
    ]
    assert normalized["camera_keyframes"] == [
        {"time": 2.0, "source": {"kind": "active_view"}}
    ]
```

This preserves the existing `camera_planner` rule: explicit `camera` takes
precedence and ignored legacy `camera_keyframes` are not allowed to fail the
request.

- [ ] **Step 10: Run tests and verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_timeline.py -q
```

Expected:

```text
ImportError or AttributeError because rook.timeline does not exist yet.
```

## Task 2: Implement Timeline Resolver

**Files:**
- Create: `mcp_server/src/rook/timeline.py`
- Test: `mcp_server/tests/test_timeline.py`

- [ ] **Step 1: Add module skeleton and deterministic rounding helper**

Create `mcp_server/src/rook/timeline.py`:

```python
from __future__ import annotations

import math
from typing import Any


class TimelineError(ValueError):
    pass


TIMING_FIELDS = ("frame_index", "time", "at")


def _round_half_up(value: float) -> int:
    if not math.isfinite(value) or value < 0:
        raise TimelineError("timeline rounding input must be finite and nonnegative")
    return int(math.floor(value + 0.5))
```

- [ ] **Step 2: Add numeric validators**

Add:

```python
def _positive_integral(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise TimelineError(f"{field} must be a positive integral value")
    try:
        numeric = int(value)
    except (TypeError, ValueError) as ex:
        raise TimelineError(f"{field} must be a positive integral value") from ex
    if numeric != value and not (isinstance(value, str) and str(numeric) == value):
        raise TimelineError(f"{field} must be a positive integral value")
    if numeric <= 0:
        raise TimelineError(f"{field} must be a positive integral value")
    return numeric


def _finite_float(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as ex:
        raise TimelineError(f"{field} must be finite") from ex
    if not math.isfinite(numeric):
        raise TimelineError(f"{field} must be finite")
    return numeric
```

- [ ] **Step 3: Add timeline derivation**

Add:

```python
def resolve_timeline(request: dict[str, Any]) -> dict[str, Any]:
    timeline = request.get("timeline")
    if timeline is None:
        frame_count = _positive_integral(request.get("frame_count"), "frame_count")
        return {
            "source": "frame_count",
            "fps": None,
            "duration_seconds": None,
            "frame_count": frame_count,
        }

    if not isinstance(timeline, dict):
        raise TimelineError("timeline must be an object")

    fps = _positive_integral(timeline.get("fps"), "timeline.fps")
    duration_seconds = _finite_float(
        timeline.get("duration_seconds"), "timeline.duration_seconds"
    )
    if duration_seconds <= 0:
        raise TimelineError("timeline.duration_seconds must be positive")

    derived_frame_count = _round_half_up(duration_seconds * fps)
    if derived_frame_count < 1:
        raise TimelineError("timeline derived frame_count must be >= 1")

    if "frame_count" in request:
        supplied_frame_count = _positive_integral(request.get("frame_count"), "frame_count")
        if supplied_frame_count != derived_frame_count:
            raise TimelineError(
                "frame_count must equal timeline-derived frame_count"
            )

    return {
        "source": "timeline",
        "fps": fps,
        "duration_seconds": duration_seconds,
        "frame_count": derived_frame_count,
    }
```

- [ ] **Step 4: Add timing-field mapping**

Add:

```python
def _timing_fields_present(keyframe: dict[str, Any]) -> list[str]:
    return [field for field in TIMING_FIELDS if field in keyframe]


def _frame_index_from_keyframe(
    keyframe: dict[str, Any],
    *,
    timeline_manifest: dict[str, Any],
) -> int:
    present = _timing_fields_present(keyframe)
    if len(present) != 1:
        raise TimelineError(
            "camera keyframe must contain exactly one of frame_index, time, or at"
        )

    frame_count = int(timeline_manifest["frame_count"])
    field = present[0]
    if field == "frame_index":
        frame_index = _positive_integral(keyframe.get("frame_index"), "frame_index")
    elif field == "time":
        if timeline_manifest["duration_seconds"] is None:
            raise TimelineError("camera keyframe time requires timeline.duration_seconds")
        time_value = _finite_float(keyframe.get("time"), "time")
        duration = float(timeline_manifest["duration_seconds"])
        if time_value < 0 or time_value > duration:
            raise TimelineError("camera keyframe time must be inside 0..duration_seconds")
        frame_index = _round_half_up(1 + (time_value / duration) * (frame_count - 1))
    else:
        at_value = _finite_float(keyframe.get("at"), "at")
        if at_value < 0 or at_value > 1:
            raise TimelineError("camera keyframe at must be inside 0..1")
        frame_index = _round_half_up(1 + at_value * (frame_count - 1))

    if frame_index < 1 or frame_index > frame_count:
        raise TimelineError("camera keyframe frame_index must be inside 1..frame_count")
    return frame_index
```

- [ ] **Step 5: Add camera request normalization**

Add:

```python
def _normalize_keyframe(
    keyframe: Any,
    *,
    timeline_manifest: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(keyframe, dict):
        raise TimelineError("camera keyframe entries must be objects")
    normalized = dict(keyframe)
    frame_index = _frame_index_from_keyframe(
        normalized, timeline_manifest=timeline_manifest
    )
    for field in ("time", "at"):
        normalized.pop(field, None)
    normalized["frame_index"] = frame_index
    return normalized


def _normalize_keyframes(
    keyframes: Any,
    *,
    timeline_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(keyframes, list) or not keyframes:
        raise TimelineError("camera keyframes must contain at least one keyframe")
    return [
        _normalize_keyframe(keyframe, timeline_manifest=timeline_manifest)
        for keyframe in keyframes
    ]


def normalize_director_request(
    request: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    timeline_manifest = resolve_timeline(request)
    normalized = dict(request)
    normalized["frame_count"] = timeline_manifest["frame_count"]

    if isinstance(normalized.get("camera"), dict):
        camera = dict(normalized["camera"])
        camera["keyframes"] = _normalize_keyframes(
            camera.get("keyframes"), timeline_manifest=timeline_manifest
        )
        normalized["camera"] = camera
    elif "camera_keyframes" in normalized:
        normalized["camera_keyframes"] = _normalize_keyframes(
            normalized.get("camera_keyframes"), timeline_manifest=timeline_manifest
        )

    return normalized, timeline_manifest
```

- [ ] **Step 6: Run timeline tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_timeline.py -q
```

Expected:

```text
all tests pass
```

## Task 3: Wire Director Through Timeline Resolver

**Files:**
- Modify: `mcp_server/src/rook/director.py`
- Test: `mcp_server/tests/test_director.py`

- [ ] **Step 1: Add failing Director manifest test for timeline input**

In `mcp_server/tests/test_director.py`, add a test using the existing `FakeNative` helpers if available. If this file already has `_run_request` and `_runtime` helpers, keep their local style. Add:

```python
@pytest.mark.asyncio
async def test_run_director_accepts_timeline_and_writes_manifest_timing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    fake = FakeNative([], create_outputs=True)
    request = _run_request(tmp_path)
    request.pop("frame_count")
    request["timeline"] = {"fps": 24, "duration_seconds": 0.125}
    request["camera_keyframes"] = [
        {"time": 0.0, "source": {"kind": "active_view"}},
        {"at": 1.0, "source": {"kind": "active_view"}},
    ]

    result = await director.run_director(
        request,
        call_native=fake,
        runtime=_runtime(tmp_path),
    )

    assert result["state"] == "complete"
    manifest = json.loads(
        (Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["timeline"] == {
        "source": "timeline",
        "fps": 24,
        "duration_seconds": 0.125,
        "frame_count": 3,
    }
    assert manifest["frame_count"] == 3
    assert manifest["camera_keyframes"][0]["frame_index"] == 1
    assert manifest["camera_keyframes"][1]["frame_index"] == 3
```

- [ ] **Step 2: Add failing Director consistency test**

Add:

```python
def test_timeline_frame_count_mismatch_does_not_create_run_directory(tmp_path):
    request = _run_request(tmp_path)
    request["run_id"] = "bad-timeline"
    request["frame_count"] = 4
    request["timeline"] = {"fps": 24, "duration_seconds": 0.125}
    request["camera_keyframes"] = [
        {"time": 0.0, "source": {"kind": "active_view"}}
    ]

    with pytest.raises(director.DirectorInputError, match="frame_count"):
        asyncio.run(
            director.run_director(
                request,
                call_native=FakeNative([]),
                runtime=_runtime(tmp_path),
            )
        )

    assert not (tmp_path / "data" / "rookvision_director" / "bad-timeline").exists()
```

- [ ] **Step 3: Run new Director tests and verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_director.py -k "timeline" -q
```

Expected:

```text
one or more tests fail because director.py does not call rook.timeline yet.
```

- [ ] **Step 4: Import timeline and normalize request before validation**

In `mcp_server/src/rook/director.py`, change:

```python
from . import camera_planner
```

to:

```python
from . import camera_planner, timeline
```

At the start of `run_director`, replace:

```python
validate_authoring_request(request)
```

with:

```python
try:
    request, timeline_manifest = timeline.normalize_director_request(request)
except timeline.TimelineError as ex:
    raise DirectorInputError(str(ex)) from ex

validate_authoring_request(request)
```

This must happen before `validate_authoring_request` reads `frame_count`.

- [ ] **Step 5: Use the normalized request for all frame-count consumers**

After Step 4, every later `run_director` read of `request["frame_count"]`, `request["camera"]`, and `request["camera_keyframes"]` must use the normalized request returned by `timeline.normalize_director_request`. The final code should have exactly one `timeline_manifest` variable, created by the timeline resolver.

Confirm the existing assignment remains after normalization:

```python
frame_count = int(request["frame_count"])
```

- [ ] **Step 6: Write timeline provenance into manifest**

In the `manifest` dictionary in `director.py`, add:

```python
"frame_count": frame_count,
"timeline": timeline_manifest,
```

This is an additive manifest contract: `timeline.frame_count` records timing
provenance, while top-level `frame_count` keeps the canonical count easy to
inspect beside `resolution`.

- [ ] **Step 7: Run Director timeline tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director.py -k "timeline" -q
```

Expected:

```text
timeline tests pass
```

## Task 4: Preserve Camera Planner Boundary

**Files:**
- Test: `mcp_server/tests/test_timeline.py`
- Test: `mcp_server/tests/test_camera_planner.py`
- Test: `mcp_server/tests/test_director.py`

- [ ] **Step 1: Add test proving time fields are removed before camera planner**

In `mcp_server/tests/test_timeline.py`, add:

```python
def test_timeline_removes_time_fields_before_camera_planner():
    normalized, _ = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24, "duration_seconds": 1.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}},
                    {"at": 1.0, "source": {"kind": "active_view"}},
                ],
            },
        }
    )

    for keyframe in normalized["camera"]["keyframes"]:
        assert set(keyframe).issuperset({"frame_index", "source"})
        assert "time" not in keyframe
        assert "at" not in keyframe
```

- [ ] **Step 2: Run combined timeline and camera tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_timeline.py mcp_server\tests\test_camera_planner.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run focused Director suite**

Run:

```powershell
python -m pytest mcp_server\tests\test_director.py mcp_server\tests\test_director_mcp_tools.py -q
```

Expected:

```text
all tests pass
```

## Task 5: Update MCP Tool Schema

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Update MCP schema tests**

In `mcp_server/tests/test_director_mcp_tools.py`, update the
`rhino_director_run` schema expectations:

```python
assert schema["required"] == ["object_ids", "resolution"]
assert "frame_count" in schema["properties"]
assert "timeline" in schema["properties"]
assert schema["properties"]["timeline"]["type"] == "object"
assert "fps" in schema["properties"]["timeline"]["properties"]
assert "duration_seconds" in schema["properties"]["timeline"]["properties"]
```

Keep or add a recursive assertion that `rhino_director_run` contains no
OpenAI-rejected JSON Schema keywords:

```python
BAD_SCHEMA_KEYS = {"oneOf", "anyOf", "allOf", "not"}
```

- [ ] **Step 2: Add timeline-only MCP dispatch test**

Add a dispatch test that calls `server.call_tool("rhino_director_run", request)`
with `timeline` present and no top-level `frame_count`, monkeypatches
`director.run_director`, and asserts the request reaches `director.run_director`
unchanged enough for the timeline resolver to own validation.

Use an input shape like:

```python
request = {
    "object_ids": ["obj-1"],
    "timeline": {"fps": 24, "duration_seconds": 0.125},
    "resolution": {"width": 64, "height": 64},
    "camera_keyframes": [
        {"time": 0.0, "source": {"kind": "active_view"}}
    ],
}
```

- [ ] **Step 3: Run MCP tool tests and verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py -q
```

Expected:

```text
one or more tests fail because server.py still requires frame_count and lacks timeline.
```

- [ ] **Step 4: Update `rhino_director_run` input schema**

In `mcp_server/src/rook/server.py`, update the `rhino_director_run` tool
schema:

- remove `frame_count` from `required`;
- keep `frame_count` as an optional legacy property;
- add a `timeline` object property with `fps` and `duration_seconds`;
- avoid `oneOf`, `anyOf`, `allOf`, and `not`.

The schema intentionally remains permissive enough that Python validation owns
the exact timeline and camera-keyframe timing rules.

- [ ] **Step 5: Run MCP tool tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py -q
```

Expected:

```text
all tests pass
```

## Task 6: Verify Live Compatibility

**Files:**
- No source changes unless tests reveal a compatibility gap.

- [ ] **Step 1: Run focused non-live Director tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_timeline.py mcp_server\tests\test_camera_planner.py mcp_server\tests\test_director.py mcp_server\tests\test_director_mcp_tools.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Deploy AppData payload if live Rhino testing is requested**

Run from the worktree under test:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning
```

Expected:

```text
Installed runtime imports from C:\Users\aryan\AppData\Local\Rook\app\mcp_server.
No native/managed build is claimed.
```

- [ ] **Step 3: Clear stale AppData Rook MCP processes**

Run:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*AppData*Local*Rook*venv*Scripts*python.exe* -m rook*' -or $_.CommandLine -like '*AppData*Local*Rook*venv*python* -m rook*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Expected:

```text
No stale AppData python.exe -m rook processes remain.
```

- [ ] **Step 4: Run installed schema preflight**

Run:

```powershell
@'
import asyncio
import sys
sys.path.insert(0, r'C:\Users\aryan\AppData\Local\Rook\app\mcp_server\src')
from rook import server

BAD = {'oneOf', 'anyOf', 'allOf', 'not'}

def find_bad(value, path='$'):
    hits = []
    if isinstance(value, dict):
        for key in BAD:
            if key in value:
                hits.append(f'{path}.{key}')
        for key, child in value.items():
            hits.extend(find_bad(child, f'{path}.{key}'))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(find_bad(child, f'{path}[{idx}]'))
    return hits

async def main():
    tools = await server.list_tools()
    schema = {tool.name: tool for tool in tools}['rhino_director_run'].inputSchema
    print('type=', schema.get('type'))
    print('bad_hits=', find_bad(schema))

asyncio.run(main())
'@ | C:\Users\aryan\AppData\Local\Rook\venv\Scripts\python.exe -
```

Expected:

```text
type= object
bad_hits= []
```

- [ ] **Step 5: Run live Director module when Rhino is available**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_routes_live.py -q
```

Expected:

```text
all live Director tests pass, or skip only when Rhino/RookNative is unavailable.
```

## Task 7: Commit

**Files:**
- `mcp_server/src/rook/timeline.py`
- `mcp_server/src/rook/director.py`
- `mcp_server/src/rook/server.py`
- `mcp_server/tests/test_timeline.py`
- `mcp_server/tests/test_director.py`
- `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Review changed files**

Run:

```powershell
git diff --stat
git diff -- mcp_server/src/rook/timeline.py mcp_server/src/rook/director.py mcp_server/src/rook/server.py
```

Expected:

```text
timeline code is isolated in timeline.py; camera_planner.py remains focused on camera state.
```

- [ ] **Step 2: Run diff hygiene**

Run:

```powershell
git diff --check
```

Expected:

```text
no output
```

- [ ] **Step 3: Commit**

Run:

```powershell
git add mcp_server/src/rook/timeline.py mcp_server/src/rook/director.py mcp_server/src/rook/server.py mcp_server/tests/test_timeline.py mcp_server/tests/test_director.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "add director timeline authoring contract"
```

## Final Verification

- [ ] **Run pure Python Director timing tests**

```powershell
python -m pytest mcp_server\tests\test_timeline.py mcp_server\tests\test_camera_planner.py mcp_server\tests\test_director.py mcp_server\tests\test_director_mcp_tools.py -q
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

- Spec coverage: this plan implements only Phase 1.5 from the roadmap. It does not add native curve sampling, curve-follow, FFmpeg, MP4 output, artifact publishing, or frame-capture changes.
- Boundary check: timeline rules live in `timeline.py`; camera planning still consumes canonical `frame_index` keyframes.
- Compatibility: legacy `frame_count` requests remain valid and gain manifest timing provenance.
- MCP boundary: `rhino_director_run` accepts timeline-only requests before Python validation and still avoids rejected schema composition keywords.
- Endpoint correctness: `time=0` and `at=0` map to frame `1`; `time=duration_seconds` and `at=1` map to `frame_count`.
- Rounding: midpoint behavior is explicit half-up rounding for nonnegative timeline values.
