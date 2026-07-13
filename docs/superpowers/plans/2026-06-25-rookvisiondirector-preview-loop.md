# RookVisionDirector Preview Loop Implementation Plan

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

**Goal:** Add a Python-only `rhino_director_preview_motion` tool that compiles a PR4 motion spec, replays the compiled track, and returns a compact preview outcome.

**Architecture:** Add a focused `director_preview.py` orchestration module that shallow-validates nested `preview` controls, calls the existing compiler, calls the existing replay helper, and shapes a compact result. Wire it through `server.py` as one MCP tool and update Director tool discovery narrowly for the preview, compile, and replay tools.

**Tech Stack:** Python 3, pytest, MCP `Tool` definitions in `mcp_server/src/rook/server.py`, existing `director_compiler.compile_motion`, existing `director.run_replay`.

---

## File Structure

- Create `mcp_server/src/rook/director_preview.py`: pure Python orchestration and response shaping. Depends only on `copy`, `numbers`, `typing`, `director`, and `director_compiler`.
- Create `mcp_server/tests/test_director_preview.py`: unit tests with injected compiler and replay fakes; no Rhino dependency.
- Modify `mcp_server/src/rook/server.py`: import `director_preview`, add `rhino_director_preview_motion` `Tool`, add dispatch case.
- Modify `mcp_server/tests/test_director_mcp_tools.py`: MCP schema, dispatch, and Director tool-group tests.
- Modify `mcp_server/src/rook/agent/tool_groups.py`: add preview tool and the focused missing compile/replay tools to `TOOL_GROUPS["director"]`.

## Task 1: Preview Module Contract

**Files:**
- Create: `mcp_server/tests/test_director_preview.py`
- Create: `mcp_server/src/rook/director_preview.py`

- [ ] **Step 1: Write failing unit tests for compact success, include_track, and preview pass-through**

Create `mcp_server/tests/test_director_preview.py` with this content:

```python
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_preview


U1 = "11111111-1111-1111-1111-111111111111"


def _track(frame_count: int = 2, fps: int = 24) -> dict:
    return {
        "transform_semantics": "absolute_from_source",
        "fps": fps,
        "frame_count": frame_count,
        "animated_object_ids": [U1],
        "camera_frames": [
            {"frame_index": index, "camera": {"projection": "perspective"}}
            for index in range(1, frame_count + 1)
        ],
        "object_frames": [
            {
                "frame_index": index,
                "object_transforms": [{"object_id": U1, "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}],
            }
            for index in range(1, frame_count + 1)
        ],
    }


def _spec(**overrides) -> dict:
    spec = {
        "timeline": {"fps": 24, "frame_count": 2},
        "groups": {"parts": [U1]},
        "motion": [
            {
                "target": "parts",
                "keyframes": [{"t": 1.0, "translate": [0, 0, 4]}],
            }
        ],
        "preview": {"replay_session_id": "preview-1", "restore_on_finish": True},
    }
    spec.update(overrides)
    return spec


class FakeCompiler:
    def __init__(self, output: dict):
        self.output = output
        self.calls: list[tuple[dict, int | None]] = []

    async def __call__(self, arguments: dict, *, port=None) -> dict:
        self.calls.append((copy.deepcopy(arguments), port))
        return copy.deepcopy(self.output)


class FakeReplay:
    def __init__(self, output: dict):
        self.output = output
        self.calls: list[tuple[dict, int | None]] = []

    async def __call__(self, arguments: dict, *, port=None) -> dict:
        self.calls.append((copy.deepcopy(arguments), port))
        return copy.deepcopy(self.output)


@pytest.mark.asyncio
async def test_preview_motion_compact_success_omits_track_and_passes_preview_controls():
    compiler = FakeCompiler(
        {
            "track": _track(frame_count=2, fps=24),
            "provenance": {"frame_count": 2, "fps": 24, "duration_ms": 83.3333333333},
        }
    )
    replay = FakeReplay(
        {
            "status": "completed",
            "frames_played": 2,
            "restored": True,
            "replay_session_id": "preview-1",
        }
    )
    spec = _spec(preview={"replay_session_id": "preview-1", "restore_on_finish": False, "fps": 12})
    original = copy.deepcopy(spec)

    result = await director_preview.preview_motion(
        spec,
        compile_motion=compiler,
        run_replay=replay,
        port=9950,
    )

    assert result["state"] == "completed"
    assert "track" not in result["compile"]
    assert result["compile"]["provenance"]["frame_count"] == 2
    assert result["compile"]["track_summary"] == {
        "frame_count": 2,
        "fps": 24,
        "duration_ms": 83.3333333333,
        "animated_object_ids": [U1],
        "camera_frame_count": 2,
        "object_frame_count": 2,
    }
    assert result["replay"]["status"] == "completed"
    assert result["next_edit_hooks"] == {
        "motion_targets": ["parts"],
        "animated_object_ids": [U1],
        "timeline": {"fps": 24, "frame_count": 2, "duration_ms": 83.3333333333},
        "preview_controls": ["restore_on_finish", "fps", "replay_session_id"],
    }
    assert compiler.calls == [
        (
            {
                "timeline": {"fps": 24, "frame_count": 2},
                "groups": {"parts": [U1]},
                "motion": [
                    {
                        "target": "parts",
                        "keyframes": [{"t": 1.0, "translate": [0, 0, 4]}],
                    }
                ],
            },
            9950,
        )
    ]
    assert replay.calls == [
        (
            {
                "track": _track(frame_count=2, fps=24),
                "replay_session_id": "preview-1",
                "restore_on_finish": False,
                "fps": 12,
            },
            9950,
        )
    ]
    assert spec == original


@pytest.mark.asyncio
async def test_preview_motion_include_track_opt_in_adds_track():
    track = _track(frame_count=1, fps=30)
    compiler = FakeCompiler(
        {
            "track": track,
            "provenance": {"frame_count": 1, "fps": 30, "duration_ms": 33.3333333333},
        }
    )
    replay = FakeReplay({"status": "completed", "frames_played": 1, "restored": True})

    result = await director_preview.preview_motion(
        _spec(preview={"include_track": True}),
        compile_motion=compiler,
        run_replay=replay,
    )

    assert result["state"] == "completed"
    assert result["compile"]["track"] == track
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_preview.py -q
```

Expected: FAIL during import because `rook.director_preview` does not exist.

- [ ] **Step 3: Implement minimal preview module for success path**

Create `mcp_server/src/rook/director_preview.py` with this content:

```python
"""RookVisionDirector preview orchestration.

PR5 composes the PR4 compiler with native replay through the existing Python
helper. It does not add motion semantics, persistence, or async state.
"""
from __future__ import annotations

import copy
from numbers import Real
from typing import Any, Protocol

from . import director, director_compiler


class Compiler(Protocol):
    async def __call__(self, arguments: dict[str, Any], *, port: int | None = None) -> dict[str, Any]:
        raise NotImplementedError


class ReplayRunner(Protocol):
    async def __call__(self, arguments: dict[str, Any], *, port: int | None = None) -> dict[str, Any]:
        raise NotImplementedError


SUPPORTED_PREVIEW_CONTROLS = ["restore_on_finish", "fps", "replay_session_id"]


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _compile_failed(error: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "compile_failed",
        "compile": {"error": error},
        "replay": None,
        "next_edit_hooks": {},
    }


def _preview_block(arguments: dict[str, Any]) -> dict[str, Any] | dict[str, Any]:
    preview = arguments.get("preview", {})
    if preview is None:
        return {}
    if not isinstance(preview, dict):
        return _error("invalid_preview", "preview must be an object", field="preview")
    if preview.get("loop") is True:
        return _error(
            "unsupported_preview_option",
            "preview.loop is not supported",
            option="loop",
        )
    if "include_track" in preview and not isinstance(preview["include_track"], bool):
        return _error("invalid_preview", "preview.include_track must be boolean", field="include_track")
    if "restore_on_finish" in preview and not isinstance(preview["restore_on_finish"], bool):
        return _error("invalid_preview", "preview.restore_on_finish must be boolean", field="restore_on_finish")
    if "fps" in preview:
        fps = preview["fps"]
        if isinstance(fps, bool) or not isinstance(fps, Real) or fps <= 0:
            return _error("invalid_preview", "preview.fps must be a positive number", field="fps")
    if "replay_session_id" in preview and not isinstance(preview["replay_session_id"], str):
        return _error("invalid_preview", "preview.replay_session_id must be a string", field="replay_session_id")
    return preview


def _compiler_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(arguments)
    copied.pop("preview", None)
    return copied


def _track_summary(track: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    frame_count = track.get("frame_count")
    fps = track.get("fps")
    duration_ms = provenance.get("duration_ms")
    if duration_ms is None and isinstance(frame_count, Real) and isinstance(fps, Real) and fps > 0:
        duration_ms = frame_count * (1000.0 / fps)
    return {
        "frame_count": frame_count,
        "fps": fps,
        "duration_ms": duration_ms,
        "animated_object_ids": list(track.get("animated_object_ids") or []),
        "camera_frame_count": len(track.get("camera_frames") or []),
        "object_frame_count": len(track.get("object_frames") or []),
    }


def _motion_targets(arguments: dict[str, Any]) -> list[Any]:
    motion = arguments.get("motion")
    if not isinstance(motion, list):
        return []
    return [entry.get("target") for entry in motion if isinstance(entry, dict) and "target" in entry]


def _next_edit_hooks(arguments: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "motion_targets": _motion_targets(arguments),
        "animated_object_ids": list(summary.get("animated_object_ids") or []),
        "timeline": {
            "fps": summary.get("fps"),
            "frame_count": summary.get("frame_count"),
            "duration_ms": summary.get("duration_ms"),
        },
        "preview_controls": list(SUPPORTED_PREVIEW_CONTROLS),
    }


def _replay_arguments(track: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    args: dict[str, Any] = {
        "track": track,
        "restore_on_finish": preview.get("restore_on_finish", True),
    }
    if "replay_session_id" in preview:
        args["replay_session_id"] = preview["replay_session_id"]
    if "fps" in preview:
        args["fps"] = preview["fps"]
    return args


def _state_from_replay_payload(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if status == "completed":
        return "completed"
    if status == "cancelled":
        return "cancelled"
    return "replay_failed"


async def preview_motion(
    arguments: dict[str, Any],
    *,
    compile_motion: Compiler = director_compiler.compile_motion,
    run_replay: ReplayRunner = director.run_replay,
    port: int | None = None,
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return _compile_failed(_error("invalid_preview", "preview request must be an object"))

    preview = _preview_block(arguments)
    if "code" in preview:
        return _compile_failed(preview)

    try:
        compiled = await compile_motion(_compiler_arguments(arguments), port=port)
    except director_compiler.DirectorCompileError as exc:
        return _compile_failed(exc.to_data())

    track = compiled["track"]
    provenance = compiled.get("provenance") or {}
    summary = _track_summary(track, provenance)
    compile_block: dict[str, Any] = {
        "provenance": provenance,
        "track_summary": summary,
    }
    if preview.get("include_track") is True:
        compile_block["track"] = track

    try:
        replay_payload = await run_replay(_replay_arguments(track, preview), port=port)
    except director.DirectorError as exc:
        return {
            "state": "replay_failed",
            "compile": compile_block,
            "replay": {"error": _error("director_error", str(exc))},
            "next_edit_hooks": _next_edit_hooks(arguments, summary),
        }

    state = _state_from_replay_payload(replay_payload if isinstance(replay_payload, dict) else {})
    replay_block: dict[str, Any]
    if state == "replay_failed":
        replay_block = {"error": _error("unexpected_replay_result", "replay returned an unexpected status"), "raw": replay_payload}
    else:
        replay_block = replay_payload

    return {
        "state": state,
        "compile": compile_block,
        "replay": replay_block,
        "next_edit_hooks": _next_edit_hooks(arguments, summary),
    }
```

- [ ] **Step 4: Run tests to verify success path passes**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_preview.py -q
```

Expected: PASS for the two success-path tests.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server\src\rook\director_preview.py mcp_server\tests\test_director_preview.py
git commit -m "feat(director): add preview motion orchestration"
```

Expected: commit succeeds.

## Task 2: Preview Validation And Failure Mapping

**Files:**
- Modify: `mcp_server/tests/test_director_preview.py`
- Modify: `mcp_server/src/rook/director_preview.py`

- [ ] **Step 1: Add failing tests for invalid preview controls**

Append these tests to `mcp_server/tests/test_director_preview.py`:

```python
class ShouldNotCall:
    async def __call__(self, arguments: dict, *, port=None) -> dict:
        raise AssertionError("this dependency should not be called")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preview, field, code",
    [
        ({"loop": True}, "loop", "unsupported_preview_option"),
        ({"include_track": "yes"}, "include_track", "invalid_preview"),
        ({"restore_on_finish": "yes"}, "restore_on_finish", "invalid_preview"),
        ({"fps": 0}, "fps", "invalid_preview"),
        ({"fps": True}, "fps", "invalid_preview"),
        ({"replay_session_id": 123}, "replay_session_id", "invalid_preview"),
    ],
)
async def test_preview_motion_rejects_invalid_preview_controls_before_compile_or_replay(preview, field, code):
    result = await director_preview.preview_motion(
        _spec(preview=preview),
        compile_motion=ShouldNotCall(),
        run_replay=ShouldNotCall(),
    )

    assert result["state"] == "compile_failed"
    assert result["compile"]["error"]["code"] == code
    assert result["compile"]["error"].get("field") == field or result["compile"]["error"].get("option") == field
    assert result["replay"] is None
```

- [ ] **Step 2: Run invalid-preview tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_preview.py -k invalid_preview -q
```

Expected: PASS if Task 1 implementation already includes shallow validation. If this fails, update `_preview_block` to match the exact validation rules in the tests.

- [ ] **Step 3: Add failing tests for compile and replay failure mapping**

Append these tests to `mcp_server/tests/test_director_preview.py`:

```python
from rook import director, director_compiler


class FailingCompiler:
    def __init__(self):
        self.calls = 0

    async def __call__(self, arguments: dict, *, port=None) -> dict:
        self.calls += 1
        raise director_compiler.DirectorCompileError("unknown_group", "missing group", target="ghost")


class FailingReplay:
    async def __call__(self, arguments: dict, *, port=None) -> dict:
        raise director.DirectorError("replay_already_active: busy")


@pytest.mark.asyncio
async def test_preview_motion_compile_failure_skips_replay():
    compiler = FailingCompiler()

    result = await director_preview.preview_motion(
        _spec(),
        compile_motion=compiler,
        run_replay=ShouldNotCall(),
    )

    assert compiler.calls == 1
    assert result["state"] == "compile_failed"
    assert result["compile"]["error"] == {
        "code": "unknown_group",
        "message": "missing group",
        "target": "ghost",
    }
    assert result["replay"] is None


@pytest.mark.asyncio
async def test_preview_motion_replay_exception_keeps_compile_context():
    compiler = FakeCompiler(
        {
            "track": _track(frame_count=2, fps=24),
            "provenance": {"frame_count": 2, "fps": 24, "duration_ms": 83.3333333333},
        }
    )

    result = await director_preview.preview_motion(
        _spec(),
        compile_motion=compiler,
        run_replay=FailingReplay(),
    )

    assert result["state"] == "replay_failed"
    assert result["compile"]["track_summary"]["frame_count"] == 2
    assert result["replay"]["error"]["code"] == "director_error"
    assert "replay_already_active" in result["replay"]["error"]["message"]


@pytest.mark.asyncio
async def test_preview_motion_cancelled_replay_maps_to_cancelled():
    compiler = FakeCompiler(
        {
            "track": _track(frame_count=2, fps=24),
            "provenance": {"frame_count": 2, "fps": 24, "duration_ms": 83.3333333333},
        }
    )
    replay = FakeReplay({"status": "cancelled", "frames_played": 1, "restored": True})

    result = await director_preview.preview_motion(_spec(), compile_motion=compiler, run_replay=replay)

    assert result["state"] == "cancelled"
    assert result["replay"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_preview_motion_unexpected_replay_payload_maps_to_replay_failed_with_raw_payload():
    compiler = FakeCompiler(
        {
            "track": _track(frame_count=2, fps=24),
            "provenance": {"frame_count": 2, "fps": 24, "duration_ms": 83.3333333333},
        }
    )
    replay = FakeReplay({"status": "failed", "code": "track_invalid"})

    result = await director_preview.preview_motion(_spec(), compile_motion=compiler, run_replay=replay)

    assert result["state"] == "replay_failed"
    assert result["replay"]["error"]["code"] == "unexpected_replay_result"
    assert result["replay"]["raw"] == {"status": "failed", "code": "track_invalid"}
```

- [ ] **Step 4: Run failure-mapping tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_preview.py -k "compile_failure or replay_exception or cancelled_replay or unexpected_replay" -q
```

Expected: PASS if Task 1 implementation already includes failure mapping. If this fails, update `preview_motion` to match the exact mapping in the tests.

- [ ] **Step 5: Run all preview unit tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_preview.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add mcp_server\src\rook\director_preview.py mcp_server\tests\test_director_preview.py
git commit -m "test(director): cover preview validation and replay outcomes"
```

Expected: commit succeeds. If only tests changed because Task 1 implementation already satisfied them, still commit the added coverage.

## Task 3: MCP Tool Registration And Dispatch

**Files:**
- Modify: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add failing MCP schema and dispatch tests**

In `mcp_server/tests/test_director_mcp_tools.py`, append these tests after `test_compile_motion_tool_dispatch_error_surfaces_code`:

```python

@pytest.mark.asyncio
async def test_preview_motion_tool_registered_with_clean_schema():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}

    assert "rhino_director_preview_motion" in by_name
    schema = by_name["rhino_director_preview_motion"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["timeline", "motion"]
    assert _find_rejected_schema_keywords(schema) == []
    assert "timeline" in schema["properties"]
    assert "motion" in schema["properties"]
    assert "preview" in schema["properties"]

    props = schema["properties"]
    preview_props = props.get("preview", {}).get("properties", {})
    for banned in ["capture", "output_path", "output_dir", "output_root", "artifact", "persist"]:
        assert banned not in props
        assert banned not in preview_props


@pytest.mark.asyncio
async def test_preview_motion_tool_dispatch_success():
    request = {
        "timeline": {"fps": 24, "frame_count": 2},
        "motion": [
            {
                "target": "11111111-1111-1111-1111-111111111111",
                "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}],
            }
        ],
        "preview": {"restore_on_finish": True},
    }

    async def fake_preview(arguments, *, port=None):
        assert arguments == request
        assert port is None
        return {"state": "completed", "compile": {"track_summary": {"frame_count": 2}}, "replay": {"status": "completed"}}

    with patch("rook.server.director_preview.preview_motion", new=fake_preview):
        out = await server.call_tool("rhino_director_preview_motion", request)

    data = json.loads(out[0].text)
    assert data["state"] == "completed"
    assert data["replay"]["status"] == "completed"
```

- [ ] **Step 2: Run MCP preview tests to verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py -k preview_motion -q
```

Expected: FAIL because `rhino_director_preview_motion` is not registered and `rook.server` does not import `director_preview`.

- [ ] **Step 3: Import `director_preview` in `server.py`**

In `mcp_server/src/rook/server.py`, change the existing import line:

```python
from . import artifacts, director, director_compiler, director_publish, director_video, merge_execution, script_library, targeting, workbench, work_units
```

to:

```python
from . import artifacts, director, director_compiler, director_preview, director_publish, director_video, merge_execution, script_library, targeting, workbench, work_units
```

- [ ] **Step 4: Add the MCP Tool definition**

In `mcp_server/src/rook/server.py`, insert this `Tool` block immediately after the existing `rhino_director_compile_motion` `Tool` block and before `rhino_views`:

```python
        Tool(
            name="rhino_director_preview_motion",
            description=(
                "RookVisionDirector: compile a high-level object-motion authoring spec "
                "and synchronously preview it through live replay. Returns compact "
                "compile provenance, track summary, replay outcome, and deterministic "
                "next-edit hooks by default; preview.include_track=true includes the "
                "full baked track. Does not capture, persist, or create async jobs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timeline": {"type": "object", "description": "fps (positive int) plus exactly one of duration_seconds or frame_count."},
                    "motion": {"type": "array", "items": {"type": "object"}, "description": "Per-target keyframe tracks; each {target, keyframes[]}."},
                    "groups": {"type": "object", "description": "Optional map of local group name -> [object UUIDs]. Names must not be UUID-shaped."},
                    "camera": {"type": "object", "description": "Optional camera_planner spec (keyframes|curve_follow_target). Omitted = hold active view."},
                    "resolution": {"type": "object", "description": "Optional {width,height}; defaults 1920x1080 (camera aspect only)."},
                    "default_easing": {"type": "string", "description": "Track-level default easing: linear|ease_in|ease_out|ease_in_out (default linear)."},
                    "preview": {
                        "type": "object",
                        "description": "Optional preview controls: replay_session_id, restore_on_finish, fps, loop=false, include_track.",
                        "properties": {
                            "replay_session_id": {"type": "string", "description": "Optional caller id passed through to replay; replay validates exact id rules."},
                            "restore_on_finish": {"type": "boolean", "description": "Default true: restore objects+camera after completed replay."},
                            "fps": {"type": "number", "description": "Optional positive replay fps override; omitted uses track.fps."},
                            "loop": {"type": "boolean", "description": "Must be false in PR5; true is rejected before compile/replay."},
                            "include_track": {"type": "boolean", "description": "Default false; true includes the full compiled replay track."},
                        },
                    },
                },
                "required": ["timeline", "motion"],
            },
        ),
```

- [ ] **Step 5: Add the dispatch case**

In `mcp_server/src/rook/server.py`, insert this case immediately after the existing `rhino_director_compile_motion` case:

```python
        case "rhino_director_preview_motion":
            result = {"success": True, "data": await director_preview.preview_motion(arguments, port=port)}
```

Do not wrap preview states as MCP transport errors. `director_preview.preview_motion` returns `state` data for expected compile/replay outcomes.

- [ ] **Step 6: Run MCP preview tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py -k preview_motion -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add mcp_server\src\rook\server.py mcp_server\tests\test_director_mcp_tools.py
git commit -m "feat(mcp): expose director preview motion tool"
```

Expected: commit succeeds.

## Task 4: Director Tool Discovery Group

**Files:**
- Modify: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`

- [ ] **Step 1: Add failing tool-group test**

In `mcp_server/tests/test_director_mcp_tools.py`, update `test_director_tool_groups_include_curve_samples_readonly` so the Director group assertions include the preview, compile, and replay tools:

```python
def test_director_tool_groups_include_curve_samples_readonly():
    assert "director" in tool_groups.TOOL_GROUPS
    assert "rhino_director_run" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_replay" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_replay_cancel" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_compile_motion" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_preview_motion" in tool_groups.TOOL_GROUPS["director"]
    assert "director_readonly" in tool_groups.TOOL_GROUPS
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director_readonly"]
    assert "director" in tool_groups.MCP_ONLY_GROUPS
```

- [ ] **Step 2: Run tool-group test to verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py::test_director_tool_groups_include_curve_samples_readonly -q
```

Expected: FAIL because `TOOL_GROUPS["director"]` is missing at least `rhino_director_replay`, `rhino_director_replay_cancel`, `rhino_director_compile_motion`, and `rhino_director_preview_motion`.

- [ ] **Step 3: Update Director tool group narrowly**

In `mcp_server/src/rook/agent/tool_groups.py`, change the Director group from:

```python
    "director": [
        "rhino_director_run",
        "rhino_director_curve_samples",
        "rhino_director_assemble_video",
        "rhino_director_publish_video",
    ],
```

to:

```python
    "director": [
        "rhino_director_run",
        "rhino_director_curve_samples",
        "rhino_director_replay",
        "rhino_director_replay_cancel",
        "rhino_director_compile_motion",
        "rhino_director_preview_motion",
        "rhino_director_assemble_video",
        "rhino_director_publish_video",
    ],
```

This is a focused discovery fix only. Do not change readonly groups or registry policy.

- [ ] **Step 4: Run tool-group tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py -k "tool_groups or preview_motion" -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add mcp_server\src\rook\agent\tool_groups.py mcp_server\tests\test_director_mcp_tools.py
git commit -m "fix(mcp): include director preview tools in discovery group"
```

Expected: commit succeeds.

## Task 5: Focused Verification

**Files:**
- Verify: `mcp_server/src/rook/director_preview.py`
- Verify: `mcp_server/src/rook/server.py`
- Verify: `mcp_server/src/rook/agent/tool_groups.py`
- Verify: `mcp_server/tests/test_director_preview.py`
- Verify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Run focused Director Python suite**

Run:

```powershell
python -m pytest `
  mcp_server\tests\test_director_motion.py `
  mcp_server\tests\test_director_compiler.py `
  mcp_server\tests\test_director_replay.py `
  mcp_server\tests\test_director_mcp_tools.py `
  mcp_server\tests\test_director_preview.py `
  -q
```

Expected: PASS. The pre-plan baseline on this worktree was `100 passed` before adding PR5 tests; the final count should be greater than 100 and have zero failures.

- [ ] **Step 2: Search for accidental native, managed, persistence, or capture scope creep**

Run:

```powershell
git diff --name-only origin/main HEAD
```

Expected changed production files are limited to:

```text
docs/superpowers/specs/2026-06-25-rookvisiondirector-preview-loop-design.md
docs/superpowers/plans/2026-06-25-rookvisiondirector-preview-loop.md
mcp_server/src/rook/director_preview.py
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_groups.py
mcp_server/tests/test_director_preview.py
mcp_server/tests/test_director_mcp_tools.py
```

If any `src/RookNative`, `src/Rook`, `src/RookBim`, artifact store, video assembly, or publish files appear, inspect them and remove unrelated changes before proceeding.

- [ ] **Step 3: Search schema for rejected keywords**

Run:

```powershell
python -m pytest mcp_server\tests\test_director_mcp_tools.py::test_preview_motion_tool_registered_with_clean_schema -q
```

Expected: PASS. This pins that the preview schema avoids `oneOf`, `anyOf`, `allOf`, and `not`.

- [ ] **Step 4: Confirm git status is clean after commits**

Run:

```powershell
git status --short
```

Expected: no output.

- [ ] **Step 5: Report completion**

Report the final commit list:

```powershell
git log --oneline origin/main..HEAD
```

Expected: includes the design commit plus three implementation commits from Tasks 1, 3, and 4; Task 2 may be a separate test commit if it added coverage after Task 1.

## Plan Self-Review

Spec coverage:

- Python-only orchestration: Task 1 creates `director_preview.py`.
- Nested `preview` and no input mutation: Task 1 tests and implements stripping `preview` from a deep copy.
- Compact default and `include_track`: Task 1 tests both shapes.
- Preview shallow validation: Task 2 tests invalid controls before compile/replay.
- `loop: true` early rejection: Task 2 tests `unsupported_preview_option`.
- Compile failure skips replay: Task 2 tests compiler exception with `ShouldNotCall` replay.
- Replay exception, cancelled, and unexpected payload mapping: Task 2 tests all three paths.
- MCP tool and schema: Task 3.
- Focused Director group discovery fix: Task 4.
- No native/C#/persistence/async state: Task 5 diff scope check.

Placeholder scan:

- No deferred implementation markers are intentionally present.
- Code snippets define concrete test names, concrete functions, and exact commands.

Type consistency:

- Public function name is consistently `preview_motion`.
- Tool name is consistently `rhino_director_preview_motion`.
- Error codes are consistently `unsupported_preview_option`, `invalid_preview`, `director_error`, and `unexpected_replay_result`.
- Output fields are consistently `state`, `compile`, `replay`, and `next_edit_hooks`.
