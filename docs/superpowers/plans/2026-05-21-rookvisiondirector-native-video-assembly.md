# RookVisionDirector Native Video Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit post-run Director tool that assembles a completed PNG frame run into `videos/preview.mp4` plus deterministic `video_manifest.json`.

**Architecture:** Python owns post-run orchestration, frame-run validation, status separation, and manifest writing. RookNative exposes a thin `/director/video-assemble` backend route that independently enforces Director output-root path policy, decodes PNG frames with OS-provided Windows imaging APIs, encodes H.264 MP4 with Media Foundation, and returns backend evidence. The slice implements Windows Media Foundation now and documents the Mac AVFoundation/VideoToolbox backend contract without implementing Mac.

**Tech Stack:** Python MCP server, pytest, Rhino 8 C++ native plugin, `httplib`, `nlohmann::json`, Windows Media Foundation, Windows Imaging Component, existing Director output-root policy helpers.

---

## Completion Status

Status as of 2026-05-21: implemented and merged in PR #172,
`[codex] Add RookVisionDirector native video assembly`.

This plan is retained as the historical execution plan for the completed Phase 3
slice. The unchecked task boxes below are historical plan scaffolding, not open
work. The source of truth for completion is PR #172 and commit
`a36be9a Add RookVisionDirector native video assembly` on `main`.

Verified completion recorded in PR #172:

- focused Python/MCP/native-source tests passed: `43 passed`;
- native Debug build with MSVC `14.44.35207` succeeded earlier on the branch;
- native-only local deploy succeeded;
- live Rhino smoke produced a completed 96-frame, 1280x720, 24 FPS Director run;
- `rhino_director_assemble_video` produced
  `videos/preview.mp4` through the `media_foundation` backend;
- `video_manifest.json` recorded `state: complete`, `output_current: true`,
  `preserved_previous_output: false`, and no `error`;
- `status.json` remained the frame-run status.

## Constraints

- Do not add automatic video generation to `rhino_director_run`.
- Do not alter frame-run `status.json`; video assembly writes only `video_manifest.json` and `videos/preview.mp4`.
- Do not use FFmpeg, `libx264`, or any GPL fallback.
- Do not implement Mac encoding in this slice.
- Do not implement artifact store, Gallery, RookVision publishing, preview UI, or video job lifecycle.
- Do not change `/director/frame-capture` behavior.
- Do not modify `.vcxproj` or `.vcxproj.filters`; keep native implementation in existing compiled source files.
- Native path validation is an enforcement boundary, not a trust boundary delegated to Python.
- Native must independently canonicalize `run_root`, `frames_dir`, and `output_path` against the configured Director output root before reading PNGs or writing MP4.
- Python may validate PNG dimensions from headers; native owns PNG decode/conversion validation and returns `unsupported_frame_format` when decode or conversion fails.
- V1 accepts only even positive dimensions for H.264 MP4 and rejects odd dimensions with `unsupported_dimensions`.
- Alpha PNGs are composited against opaque black `#000000`; evidence records `alpha_composited: true` and `alpha_background: "#000000"` only when alpha is encountered.
- A failed assembly preserves previous `videos/preview.mp4` if one exists and marks it as not current with `output_current: false`.

## File Structure

- Create `mcp_server/src/rook/director_video.py`
  Owns `assemble_director_video`, completed-run validation, every-frame existence and dimension checks, FPS resolution, native request creation, deterministic manifest writing, and stale-preview flags.
- Modify `mcp_server/src/rook/server.py`
  Registers `rhino_director_assemble_video` and dispatches it to `director_video.assemble_director_video`.
- Modify `mcp_server/src/rook/agent/tool_groups.py`
  Adds `rhino_director_assemble_video` to the mutating `director` group only.
- Modify `mcp_server/tests/test_director_video.py`
  Adds Python unit tests for validation, manifest semantics, FPS override success, stale preview semantics, and native-call shape.
- Modify `mcp_server/tests/test_director_mcp_tools.py`
  Adds MCP schema, dispatch, and tool group tests.
- Modify `mcp_server/tests/test_director_native_source.py`
  Adds native source-contract tests for route registration, policy enforcement, Media Foundation/WIC backend evidence, and structured error codes.
- Modify `mcp_server/tests/test_director_routes_live.py`
  Adds live route rejection tests and a guarded live smoke for native backend availability.
- Modify `src/RookNative/Handlers/DirectorHandler.h`
  Declares `HandleDirectorVideoAssemble`.
- Modify `src/RookNative/Handlers/DirectorHandler.cpp`
  Adds the native request parser, stricter video path policy check, WIC PNG decode, BGRA-to-NV12 conversion, Media Foundation MP4 assembly, temp-output replacement, and route handler.
- Modify `src/RookNative/RookServer.h`
  Adds the CRookServer delegate declaration.
- Modify `src/RookNative/RookServer.cpp`
  Registers `/director/video-assemble` and delegates to the handler.

---

### Task 1: Python Video Assembly Unit Tests

**Files:**
- Create: `mcp_server/tests/test_director_video.py`
- Read: `mcp_server/src/rook/director.py`

- [ ] **Step 1: Add tests for Python validation and manifest semantics**

Create `mcp_server/tests/test_director_video.py` with:

```python
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from rook import director_video


def _png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _write_run(
    root: Path,
    *,
    state: str = "complete",
    frame_count: int = 2,
    width: int = 320,
    height: int = 180,
    timeline: dict | None = None,
) -> Path:
    run_root = root / "run-a"
    frames_dir = run_root / "frames"
    frames_dir.mkdir(parents=True)
    for index in range(1, frame_count + 1):
        (frames_dir / f"frame_{index:04d}.png").write_bytes(_png_header(width, height))
    manifest = {
        "schema_version": 1,
        "director_version": "slice1",
        "run_id": "run-a",
        "run_root": str(run_root),
        "frame_count": frame_count,
        "resolution": {"width": width, "height": height},
        "timeline": timeline or {
            "source": "timeline",
            "fps": 24,
            "duration_seconds": frame_count / 24,
            "frame_count": frame_count,
        },
        "frames": [
            {
                "frame_index": index,
                "frame_id": f"frame_{index:04d}",
                "output_path": str(frames_dir / f"frame_{index:04d}.png"),
            }
            for index in range(1, frame_count + 1)
        ],
    }
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_root / "status.json").write_text(
        json.dumps({"state": state, "run_id": "run-a"}),
        encoding="utf-8",
    )
    return run_root


class FakeNative:
    def __init__(self, *, success: bool = True):
        self.calls = []
        self.success = success

    async def __call__(self, endpoint, method="GET", data=None, port=None):
        self.calls.append((endpoint, method, data, port))
        if self.success:
            output = Path(data["output_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"mp4")
            return {
                "success": True,
                "data": {
                    "backend": "media_foundation",
                    "platform": "windows",
                    "output_path": data["output_path"],
                    "bytes": 3,
                    "evidence": {"codec": "h264", "container": "mp4"},
                },
            }
        return {
            "success": False,
            "data": {
                "error": {
                    "code": "backend_unavailable",
                    "message": "Media Foundation H.264 encoder is unavailable",
                },
                "evidence": {"backend": "media_foundation"},
            },
        }


@pytest.mark.asyncio
async def test_assemble_video_success_uses_timeline_fps_and_writes_manifest(tmp_path):
    run_root = _write_run(tmp_path / "director")
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "complete"
    assert result["output_current"] is True
    assert result["preserved_previous_output"] is False
    assert fake.calls[0][0:2] == ("/director/video-assemble", "POST")
    native_request = fake.calls[0][2]
    assert native_request["fps"] == 24
    assert native_request["fps_source"] == "timeline"
    assert native_request["frame_count"] == 2
    assert native_request["width"] == 320
    assert native_request["height"] == 180
    assert native_request["output_path"].endswith("videos\\preview.mp4") or native_request["output_path"].endswith("videos/preview.mp4")

    manifest = json.loads((run_root / "video_manifest.json").read_text(encoding="utf-8"))
    assert manifest["state"] == "complete"
    assert manifest["backend"] == "media_foundation"
    assert manifest["fps"] == 24
    assert manifest["fps_source"] == "timeline"
    assert manifest["output_path"] == "videos/preview.mp4"
    assert "completed_at" in manifest
    assert "finished_at" not in manifest
    assert manifest["output_current"] is True
    assert manifest["preserved_previous_output"] is False


@pytest.mark.asyncio
async def test_assemble_video_explicit_fps_override_succeeds_for_legacy_run(tmp_path):
    run_root = _write_run(
        tmp_path / "director",
        timeline={"source": "legacy_frame_count", "frame_count": 2},
    )
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root), "fps": 30},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "complete"
    assert fake.calls[0][2]["fps"] == 30
    assert fake.calls[0][2]["fps_source"] == "explicit_override"
    manifest = json.loads((run_root / "video_manifest.json").read_text(encoding="utf-8"))
    assert manifest["fps"] == 30
    assert manifest["fps_source"] == "explicit_override"
    assert manifest["output_path"] == "videos/preview.mp4"


@pytest.mark.asyncio
async def test_assemble_video_legacy_without_fps_fails_without_native_call(tmp_path):
    run_root = _write_run(
        tmp_path / "director",
        timeline={"source": "legacy_frame_count", "frame_count": 2},
    )
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "fps_missing"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_assemble_video_invalid_explicit_fps_fails_without_native_call(tmp_path):
    run_root = _write_run(tmp_path / "director")
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root), "fps": "bad"},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "fps_missing"
    assert result["output_current"] is False
    assert fake.calls == []


@pytest.mark.asyncio
async def test_assemble_video_failed_first_attempt_marks_no_previous_preview(tmp_path):
    run_root = _write_run(tmp_path / "director")
    fake = FakeNative(success=False)

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["output_current"] is False
    assert result["preserved_previous_output"] is False
    assert result["overwrote_existing"] is False


@pytest.mark.asyncio
async def test_assemble_video_failed_with_existing_preview_preserves_stale_output(tmp_path):
    run_root = _write_run(tmp_path / "director")
    preview = run_root / "videos" / "preview.mp4"
    preview.parent.mkdir()
    preview.write_bytes(b"old")
    fake = FakeNative(success=False)

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert preview.read_bytes() == b"old"
    assert result["state"] == "failed"
    assert result["output_current"] is False
    assert result["preserved_previous_output"] is True
    assert result["overwrote_existing"] is False


@pytest.mark.asyncio
async def test_assemble_video_rejects_incomplete_frame_run_without_changing_status(tmp_path):
    run_root = _write_run(tmp_path / "director", state="failed")
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "frame_run_incomplete"
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["state"] == "failed"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_assemble_video_rejects_frame_dimension_mismatch(tmp_path):
    run_root = _write_run(tmp_path / "director", frame_count=2)
    (run_root / "frames" / "frame_0002.png").write_bytes(_png_header(640, 180))
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "dimension_mismatch"
    manifest = json.loads((run_root / "video_manifest.json").read_text(encoding="utf-8"))
    assert manifest["output_path"] == "videos/preview.mp4"
    assert manifest["fps"] == 24
    assert manifest["fps_source"] == "timeline"
    assert manifest["frame_count"] == 2
    assert manifest["width"] == 320
    assert manifest["height"] == 180
    assert manifest["input_pattern"] == "frames/frame_%04d.png"
    assert "completed_at" in manifest
    assert fake.calls == []


@pytest.mark.asyncio
async def test_assemble_video_rejects_run_root_outside_director_root(tmp_path):
    run_root = _write_run(tmp_path / "outside")
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "run_root_policy_violation"
    assert fake.calls == []
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_video.py -q
```

Expected: import failure for `rook.director_video`.

- [ ] **Step 3: Commit failing tests**

```powershell
git add mcp_server/tests/test_director_video.py
git commit -m "test: pin Director video assembly orchestration"
```

---

### Task 2: Python Video Assembly Orchestrator

**Files:**
- Create: `mcp_server/src/rook/director_video.py`
- Test: `mcp_server/tests/test_director_video.py`

- [ ] **Step 1: Implement the orchestration module**

Create `mcp_server/src/rook/director_video.py`:

```python
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

SCHEMA_VERSION = 1
VIDEO_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_NAME = "preview.mp4"
RELATIVE_OUTPUT_PATH = "videos/preview.mp4"
RELATIVE_INPUT_PATTERN = "frames/frame_%04d.png"


class DirectorVideoError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _default_output_root() -> Path:
    env_root = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorVideoError(
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set"
        )
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise DirectorVideoError(f"invalid PNG header: {path}")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def _failure_manifest(
    *,
    run_id: str,
    run_root: Path,
    output_path: Path,
    error_code: str,
    message: str,
    started_at: str,
    evidence: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_exists = output_path.exists()
    context = context or {}
    manifest = {
        "schema_version": VIDEO_SCHEMA_VERSION,
        "state": "failed",
        "run_id": run_id,
        "backend": "media_foundation",
        "platform": "windows",
        "format": "mp4",
        "codec": "h264",
        "container": "mp4",
        "fps": context.get("fps"),
        "fps_source": context.get("fps_source"),
        "frame_count": context.get("frame_count"),
        "width": context.get("width"),
        "height": context.get("height"),
        "input_pattern": context.get("input_pattern", RELATIVE_INPUT_PATTERN),
        "output_path": RELATIVE_OUTPUT_PATH,
        "bytes": 0,
        "overwrote_existing": False,
        "output_current": False,
        "preserved_previous_output": previous_exists,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "error": {"code": error_code, "message": message},
        "evidence": evidence or {},
    }
    return manifest


def _write_failure(
    *,
    run_id: str,
    run_root: Path,
    output_path: Path,
    error_code: str,
    message: str,
    started_at: str,
    evidence: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _failure_manifest(
        run_id=run_id,
        run_root=run_root,
        output_path=output_path,
        error_code=error_code,
        message=message,
        started_at=started_at,
        evidence=evidence,
        context=context,
    )
    _atomic_write_json(run_root / "video_manifest.json", manifest)
    return manifest


def _resolve_fps(request: dict[str, Any], manifest: dict[str, Any]) -> tuple[float, str] | tuple[None, None]:
    if request.get("fps") is not None:
        try:
            fps = float(request["fps"])
        except (TypeError, ValueError):
            return None, None
        if fps > 0:
            return fps, "explicit_override"
        return None, None
    timeline = manifest.get("timeline") if isinstance(manifest.get("timeline"), dict) else {}
    fps = timeline.get("fps")
    try:
        timeline_fps = float(fps)
    except (TypeError, ValueError):
        return None, None
    if timeline_fps > 0:
        return timeline_fps, "timeline"
    return None, None


async def assemble_director_video(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    director_output_root: Path | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    allowed_root = (director_output_root or _default_output_root()).expanduser().resolve()
    run_root = Path(str(request.get("run_root", ""))).expanduser().resolve()
    output_path = run_root / "videos" / DEFAULT_OUTPUT_NAME
    run_id = run_root.name or ""

    if not run_root or not _is_relative_to(run_root, allowed_root):
        return _failure_manifest(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="run_root_policy_violation",
            message="run_root must resolve under the configured Director output root",
            started_at=started_at,
        )

    manifest_path = run_root / "manifest.json"
    status_path = run_root / "status.json"
    try:
        manifest = _read_json(manifest_path)
        status = _read_json(status_path)
    except (OSError, json.JSONDecodeError) as ex:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="missing_run_metadata",
            message=str(ex),
            started_at=started_at,
        )

    run_id = str(manifest.get("run_id") or run_id)
    resolution = manifest.get("resolution") if isinstance(manifest.get("resolution"), dict) else {}
    context = {
        "frame_count": int(manifest.get("frame_count", 0) or 0),
        "width": int(resolution.get("width", 0) or 0),
        "height": int(resolution.get("height", 0) or 0),
        "input_pattern": RELATIVE_INPUT_PATTERN,
    }
    if status.get("state") != "complete":
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="frame_run_incomplete",
            message="Director frame run must be complete before video assembly",
            started_at=started_at,
            context=context,
        )

    fps, fps_source = _resolve_fps(request, manifest)
    context["fps"] = fps
    context["fps_source"] = fps_source
    if fps is None or fps_source is None:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="fps_missing",
            message="timeline fps or explicit fps override is required",
            started_at=started_at,
            context=context,
        )

    frame_count = context["frame_count"]
    frames = manifest.get("frames")
    if not isinstance(frames, list) or len(frames) != frame_count:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="frame_count_mismatch",
            message="manifest frame_count must match frames length",
            started_at=started_at,
            context=context,
        )

    width = context["width"]
    height = context["height"]
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="unsupported_dimensions",
            message="v1 H.264 MP4 assembly requires positive even dimensions",
            started_at=started_at,
            context=context,
        )

    frames_dir = run_root / "frames"
    for index in range(1, frame_count + 1):
        frame_path = frames_dir / f"frame_{index:04d}.png"
        if not frame_path.is_file():
            return _write_failure(
                run_id=run_id,
                run_root=run_root,
                output_path=output_path,
                error_code="missing_frame",
                message=f"missing frame file: {frame_path}",
                started_at=started_at,
                context=context,
            )
        try:
            frame_width, frame_height = _png_size(frame_path)
        except DirectorVideoError as ex:
            return _write_failure(
                run_id=run_id,
                run_root=run_root,
                output_path=output_path,
                error_code="unsupported_frame_format",
                message=str(ex),
                started_at=started_at,
                context=context,
            )
        if (frame_width, frame_height) != (width, height):
            return _write_failure(
                run_id=run_id,
                run_root=run_root,
                output_path=output_path,
                error_code="dimension_mismatch",
                message=f"{frame_path.name} is {frame_width}x{frame_height}, expected {width}x{height}",
                started_at=started_at,
                context=context,
            )

    native_request = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "frames_dir": str(frames_dir),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": frame_count,
        "fps": fps,
        "fps_source": fps_source,
        "width": width,
        "height": height,
        "output_path": str(output_path),
        "codec": "h264",
        "container": "mp4",
    }

    native = await call_native("/director/video-assemble", "POST", native_request, port=port)
    native_data = native.get("data") if isinstance(native.get("data"), dict) else {}
    if not native.get("success"):
        error = native_data.get("error") if isinstance(native_data.get("error"), dict) else {}
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code=str(error.get("code") or "backend_encode_failed"),
            message=str(error.get("message") or native_data or "native video assembly failed"),
            started_at=started_at,
            evidence=native_data.get("evidence") if isinstance(native_data.get("evidence"), dict) else native_data,
            context=context,
        )

    result = {
        "schema_version": VIDEO_SCHEMA_VERSION,
        "state": "complete",
        "run_id": run_id,
        "backend": native_data.get("backend", "media_foundation"),
        "platform": native_data.get("platform", "windows"),
        "format": "mp4",
        "codec": "h264",
        "container": "mp4",
        "fps": fps,
        "fps_source": fps_source,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "input_pattern": RELATIVE_INPUT_PATTERN,
        "output_path": RELATIVE_OUTPUT_PATH,
        "bytes": int(native_data.get("bytes") or output_path.stat().st_size),
        "overwrote_existing": bool(native_data.get("overwrote_existing")),
        "output_current": True,
        "preserved_previous_output": False,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "error": None,
        "evidence": native_data.get("evidence") or {},
    }
    _atomic_write_json(run_root / "video_manifest.json", result)
    return result
```

- [ ] **Step 2: Run Python video tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_video.py -q
```

Expected: all tests in `test_director_video.py` pass.

- [ ] **Step 3: Commit Python orchestrator**

```powershell
git add mcp_server/src/rook/director_video.py mcp_server/tests/test_director_video.py
git commit -m "feat: add Director video assembly orchestrator"
```

---

### Task 3: MCP Tool Registration

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Add MCP tests**

Append these tests to `mcp_server/tests/test_director_mcp_tools.py`:

```python
@pytest.mark.asyncio
async def test_director_assemble_video_tool_registered_as_mutating_post_run_tool():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_assemble_video" in by_name

    schema = by_name["rhino_director_assemble_video"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["run_root"]
    assert _find_rejected_schema_keywords(schema) == []
    assert schema["properties"]["run_root"]["type"] == "string"
    assert schema["properties"]["fps"]["type"] == "number"
    assert schema["properties"]["fps"]["exclusiveMinimum"] == 0


@pytest.mark.asyncio
async def test_director_assemble_video_tool_dispatches_to_python_orchestrator():
    request = {"run_root": "C:/runs/director/run-a", "fps": 30}
    with patch.object(server.director_video, "assemble_director_video", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "state": "complete",
            "output_path": "videos/preview.mp4",
        }
        result = await server.call_tool("rhino_director_assemble_video", request)
    mock.assert_awaited_once()
    assert mock.await_args.args[0] == request
    assert "preview.mp4" in result[0].text


def test_director_tool_groups_include_assemble_video_only_in_mutating_director_group():
    assert "rhino_director_assemble_video" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_assemble_video" not in tool_groups.TOOL_GROUPS["director_readonly"]
```

- [ ] **Step 2: Run MCP tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: failures because the tool is not registered and `server.director_video` is not imported.

- [ ] **Step 3: Register tool and dispatch**

In `mcp_server/src/rook/server.py`, change the Director import line:

```python
from . import director, director_video, script_library, targeting
```

Add this `Tool(...)` immediately after `rhino_director_run` and before `rhino_director_curve_samples`:

```python
        Tool(
            name="rhino_director_assemble_video",
            description=(
                "Post-run RookVisionDirector operation: assemble a completed Director "
                "PNG frame run into videos/preview.mp4 and video_manifest.json. "
                "This does not run frame capture and does not publish artifacts."
            ),
            inputSchema={
                "type": "object",
                "required": ["run_root"],
                "properties": {
                    "run_root": {
                        "type": "string",
                        "description": "Completed Director run root under the configured Director output root.",
                    },
                    "fps": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "description": "Optional explicit FPS override for legacy frame-count runs without timeline fps.",
                    },
                },
            },
        ),
```

Add this `case` immediately after `rhino_director_run`:

```python
        case "rhino_director_assemble_video":
            try:
                result = {
                    "success": True,
                    "data": await director_video.assemble_director_video(arguments, port=port),
                }
            except director_video.DirectorVideoError as exc:
                result = {
                    "success": False,
                    "data": {
                        "code": "director_video_error",
                        "message": str(exc),
                    },
                }
```

In `mcp_server/src/rook/agent/tool_groups.py`, add the tool to the mutating Director group:

```python
    "director": [
        "rhino_director_run",
        "rhino_director_assemble_video",
        "rhino_director_curve_samples",
    ],
```

Do not add it to `director_readonly`.

- [ ] **Step 4: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: all Director MCP tests pass.

- [ ] **Step 5: Commit MCP registration**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat: expose Director video assembly tool"
```

---

### Task 4: Native Source Contract Tests

**Files:**
- Modify: `mcp_server/tests/test_director_native_source.py`
- Read: `src/RookNative/Handlers/DirectorHandler.cpp`
- Read: `src/RookNative/Handlers/DirectorHandler.h`
- Read: `src/RookNative/RookServer.cpp`
- Read: `src/RookNative/RookServer.h`

- [ ] **Step 1: Add source-contract tests**

Append to `mcp_server/tests/test_director_native_source.py`:

```python
def test_director_video_assemble_route_is_registered_and_delegated():
    handler_header = DIRECTOR_HEADER.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_HEADER.read_text(encoding="utf-8")
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    assert re.search(
        r"void\s+HandleDirectorVideoAssemble\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        handler_header,
    )
    assert re.search(
        r"void\s+HandleDirectorVideoAssemble\s*\(\s*const\s+httplib::Request&\s+req,\s*httplib::Response&\s+res\s*\)\s*;",
        server_header,
    )
    assert 'm_server->Post("/director/video-assemble"' in server_source
    assert "Rook::Handlers::HandleDirectorVideoAssemble(req, res);" in server_source


def test_director_video_assemble_has_native_policy_and_backend_contract():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    parser_body = _extract_function(source, "VideoAssembleRequest ParseVideoAssembleRequest")
    policy_body = _extract_function(source, "void ValidateVideoAssemblyPolicy")
    handler_body = _extract_function(source, "void HandleDirectorVideoAssemble")

    assert "run_root is required" in parser_body
    assert "frames_dir is required" in parser_body
    assert "output_path is required" in parser_body
    assert "frame_count must be a positive integer" in parser_body
    assert "fps must be a positive finite number" in parser_body
    assert "width and height must be positive even integers" in parser_body
    assert "codec must be h264" in parser_body
    assert "container must be mp4" in parser_body
    assert "input_pattern must be frame_%04d.png" in parser_body

    assert "GetAllowedDirectorRoot()" in policy_body
    assert "run_root_policy_violation" in policy_body
    assert "frames_dir_policy_violation" in policy_body
    assert "output_policy_violation" in policy_body
    assert 'request.runRoot / L"frames"' in policy_body
    assert 'request.runRoot / L"videos"' in policy_body

    assert "MFCreateSinkWriterFromURL" in source
    assert "MFVideoFormat_H264" in source
    assert "MFVideoFormat_NV12" in source
    assert "MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH" in source
    assert ".tmp.mp4" in source
    assert "CLSID_WICImagingFactory" in source
    assert "unsupported_frame_format" in source
    assert "unsupported_dimensions" in source
    assert "backend_unavailable" in source
    assert "backend_encode_failed" in source
    assert "alpha_background" in source
    assert "MakeVideoErrorData" in handler_body
```

- [ ] **Step 2: Run source tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: the new source-contract tests fail because native route and backend code are not present.

- [ ] **Step 3: Commit failing native source tests**

```powershell
git add mcp_server/tests/test_director_native_source.py
git commit -m "test: pin Director native video backend contract"
```

---

### Task 5: Native Route Skeleton and Policy Enforcement

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.h`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`
- Test: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Add route declarations**

Add to `src/RookNative/Handlers/DirectorHandler.h` beside the other Director handlers:

```cpp
void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res);
```

Add to `src/RookNative/RookServer.h` beside `HandleDirectorFrameCapture`:

```cpp
    void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Register and delegate the route**

In `src/RookNative/RookServer.cpp`, add this registration next to the other Director registrations:

```cpp
    m_server->Post("/director/video-assemble", [this](const httplib::Request& req, httplib::Response& res)
    {
        HandleDirectorVideoAssemble(req, res);
    });
```

Add this CRookServer delegate near the other Director delegates:

```cpp
void CRookServer::HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDirectorVideoAssemble(req, res);
}
```

- [ ] **Step 3: Add native request parsing and policy helpers**

In the anonymous namespace of `src/RookNative/Handlers/DirectorHandler.cpp`, add the following after the existing `PathToUtf8` helper so `MakeVideoErrorData` can call it:

```cpp
struct VideoAssembleRequest
{
    std::string runId;
    fs::path runRoot;
    fs::path framesDir;
    fs::path outputPath;
    std::string inputPattern;
    int startNumber = 1;
    int frameCount = 0;
    double fps = 0.0;
    std::string fpsSource;
    int width = 0;
    int height = 0;
    std::string codec;
    std::string container;
};

nlohmann::json MakeVideoErrorData(const VideoAssembleRequest& request, const std::string& code, const std::string& message)
{
    nlohmann::json data;
    data["success"] = false;
    data["backend"] = "media_foundation";
    data["platform"] = "windows";
    data["output_path"] = PathToUtf8(request.outputPath);
    data["error"] = MakeErrorData(code, message);
    data["evidence"] = {
        { "backend", "media_foundation" },
        { "codec", "h264" },
        { "container", "mp4" }
    };
    return data;
}

VideoAssembleRequest ParseVideoAssembleRequest(const nlohmann::json& body)
{
    VideoAssembleRequest request;
    request.runId = body.value("run_id", "");
    if (!body.contains("run_root") || !body["run_root"].is_string() || body["run_root"].get<std::string>().empty())
        throw DirectorFrameValidationError("run_root_policy_violation", "run_root is required");
    if (!body.contains("frames_dir") || !body["frames_dir"].is_string() || body["frames_dir"].get<std::string>().empty())
        throw DirectorFrameValidationError("frames_dir_policy_violation", "frames_dir is required");
    if (!body.contains("output_path") || !body["output_path"].is_string() || body["output_path"].get<std::string>().empty())
        throw DirectorFrameValidationError("output_policy_violation", "output_path is required");

    request.runRoot = NormalizePolicyPath(PathFromUtf8(body["run_root"].get<std::string>()));
    request.framesDir = NormalizePolicyPath(PathFromUtf8(body["frames_dir"].get<std::string>()));
    request.outputPath = NormalizePolicyPath(PathFromUtf8(body["output_path"].get<std::string>()));
    request.inputPattern = body.value("input_pattern", "frame_%04d.png");
    if (request.inputPattern != "frame_%04d.png")
        throw DirectorFrameValidationError("invalid_input", "input_pattern must be frame_%04d.png");
    request.startNumber = body.value("start_number", 1);

    if (!body.contains("frame_count") || !body["frame_count"].is_number_integer() || body["frame_count"].get<int>() < 1)
        throw DirectorFrameValidationError("frame_count_mismatch", "frame_count must be a positive integer");
    request.frameCount = body["frame_count"].get<int>();

    if (!body.contains("fps") || !body["fps"].is_number() || !std::isfinite(body["fps"].get<double>()) || body["fps"].get<double>() <= 0.0)
        throw DirectorFrameValidationError("fps_missing", "fps must be a positive finite number");
    request.fps = body["fps"].get<double>();
    request.fpsSource = body.value("fps_source", "");

    if (!body.contains("width") || !body.contains("height") || !body["width"].is_number_integer() || !body["height"].is_number_integer())
        throw DirectorFrameValidationError("unsupported_dimensions", "width and height must be positive even integers");
    request.width = body["width"].get<int>();
    request.height = body["height"].get<int>();
    if (request.width <= 0 || request.height <= 0 || (request.width % 2) != 0 || (request.height % 2) != 0)
        throw DirectorFrameValidationError("unsupported_dimensions", "width and height must be positive even integers");

    request.codec = body.value("codec", "");
    request.container = body.value("container", "");
    if (request.codec != "h264")
        throw DirectorFrameValidationError("unsupported_frame_format", "codec must be h264");
    if (request.container != "mp4")
        throw DirectorFrameValidationError("unsupported_frame_format", "container must be mp4");
    return request;
}

void ValidateVideoAssemblyPolicy(const VideoAssembleRequest& request)
{
    const fs::path allowedRoot = GetAllowedDirectorRoot();
    if (!IsSameOrDescendantPath(allowedRoot, request.runRoot))
        throw DirectorFrameValidationError("run_root_policy_violation", "run_root must be inside the native director output root");

    const fs::path expectedFrames = NormalizePolicyPath(request.runRoot / L"frames");
    if (!IsSamePath(expectedFrames, request.framesDir))
        throw DirectorFrameValidationError("frames_dir_policy_violation", "frames_dir must resolve to run_root/frames");

    const fs::path expectedVideos = NormalizePolicyPath(request.runRoot / L"videos");
    if (!IsSameOrDescendantPath(expectedVideos, request.outputPath))
        throw DirectorFrameValidationError("output_policy_violation", "output_path must resolve under run_root/videos");
    if (IsSamePath(expectedVideos, request.outputPath))
        throw DirectorFrameValidationError("output_policy_violation", "output_path must be a file path under run_root/videos");
}
```

- [ ] **Step 4: Add temporary handler that validates and returns backend unavailable**

Add this handler at the bottom of `DirectorHandler.cpp`, before `HandleDirectorFrameCapture` or after it:

```cpp
void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res)
{
    VideoAssembleRequest request;
    try
    {
        auto [docSn, body] = ParseBodyAndDocSn(req);
        request = ParseVideoAssembleRequest(body);
        ValidateVideoAssemblyPolicy(request);
        CRookServer::SendErrorData(res, MakeVideoErrorData(request, "backend_unavailable", "Media Foundation backend is not implemented yet"));
    }
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(request, ex.code, ex.what()));
    }
    catch (const nlohmann::json::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(request, "invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(request, "backend_encode_failed", ex.what()));
    }
}
```

- [ ] **Step 5: Run source tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: route and policy assertions pass; Media Foundation/WIC assertions still fail.

- [ ] **Step 6: Commit route skeleton**

```powershell
git add src/RookNative/Handlers/DirectorHandler.h src/RookNative/Handlers/DirectorHandler.cpp src/RookNative/RookServer.h src/RookNative/RookServer.cpp
git commit -m "feat: add Director native video assembly route"
```

---

### Task 6: Native Media Foundation Backend

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Test: `mcp_server/tests/test_director_native_source.py`

- [ ] **Step 1: Add OS media headers and linker directives**

At the top of `DirectorHandler.cpp`, add:

```cpp
#include <cstdint>
#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <numeric>
#include <wincodec.h>
#include <wrl/client.h>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "windowscodecs.lib")
#pragma comment(lib, "ole32.lib")
```

Add this alias near `namespace fs = std::filesystem;`:

```cpp
using Microsoft::WRL::ComPtr;
```

- [ ] **Step 2: Add HRESULT and path helpers**

In the anonymous namespace, add:

```cpp
void ThrowIfFailed(HRESULT hr, const std::string& code, const std::string& message)
{
    if (FAILED(hr))
        throw DirectorFrameValidationError(code, message + " HRESULT=0x" + std::to_string(static_cast<unsigned long>(hr)));
}

fs::path FramePathForIndex(const VideoAssembleRequest& request, int index)
{
    wchar_t fileName[64] = {};
    swprintf_s(fileName, L"frame_%04d.png", index);
    return request.framesDir / fileName;
}

fs::path BuildTempVideoPath(const fs::path& outputPath)
{
    GUID guid = {};
    HRESULT hr = CoCreateGuid(&guid);
    if (FAILED(hr))
        throw DirectorFrameValidationError("backend_encode_failed", "Failed to create temp video GUID");

    wchar_t guidText[40] = {};
    StringFromGUID2(guid, guidText, 40);
    std::wstring suffix = guidText;
    suffix.erase(std::remove(suffix.begin(), suffix.end(), L'{'), suffix.end());
    suffix.erase(std::remove(suffix.begin(), suffix.end(), L'}'), suffix.end());

    return outputPath.parent_path() /
        (outputPath.stem().wstring() + L"." + suffix + L".tmp.mp4");
}

uint8_t ClampByte(int value)
{
    if (value < 0)
        return 0;
    if (value > 255)
        return 255;
    return static_cast<uint8_t>(value);
}

void FrameRateRatio(double fps, UINT32& numerator, UINT32& denominator)
{
    const double rounded = std::round(fps);
    if (std::abs(fps - rounded) < 0.000001)
    {
        numerator = static_cast<UINT32>(rounded);
        denominator = 1;
        return;
    }

    numerator = static_cast<UINT32>(std::round(fps * 1000.0));
    denominator = 1000;
    const UINT32 divisor = std::gcd(numerator, denominator);
    numerator /= divisor;
    denominator /= divisor;
}
```

- [ ] **Step 3: Add WIC PNG decode to BGRA**

Add:

```cpp
struct DecodedFrame
{
    std::vector<uint8_t> bgra;
    bool alphaSeen = false;
};

DecodedFrame DecodePngBgra(IWICImagingFactory* factory, const fs::path& path, int expectedWidth, int expectedHeight)
{
    ComPtr<IWICBitmapDecoder> decoder;
    HRESULT hr = factory->CreateDecoderFromFilename(
        path.c_str(),
        nullptr,
        GENERIC_READ,
        WICDecodeMetadataCacheOnLoad,
        &decoder);
    ThrowIfFailed(hr, "unsupported_frame_format", "Failed to decode PNG frame");

    ComPtr<IWICBitmapFrameDecode> frame;
    ThrowIfFailed(decoder->GetFrame(0, &frame), "unsupported_frame_format", "Failed to read PNG frame");

    UINT width = 0;
    UINT height = 0;
    ThrowIfFailed(frame->GetSize(&width, &height), "unsupported_frame_format", "Failed to read PNG dimensions");
    if (static_cast<int>(width) != expectedWidth || static_cast<int>(height) != expectedHeight)
        throw DirectorFrameValidationError("dimension_mismatch", "Decoded PNG dimensions do not match requested video dimensions");

    ComPtr<IWICFormatConverter> converter;
    ThrowIfFailed(factory->CreateFormatConverter(&converter), "unsupported_frame_format", "Failed to create WIC format converter");
    ThrowIfFailed(
        converter->Initialize(
            frame.Get(),
            GUID_WICPixelFormat32bppBGRA,
            WICBitmapDitherTypeNone,
            nullptr,
            0.0,
            WICBitmapPaletteTypeCustom),
        "unsupported_frame_format",
        "Failed to convert PNG to BGRA");

    DecodedFrame decoded;
    decoded.bgra.resize(static_cast<size_t>(expectedWidth) * static_cast<size_t>(expectedHeight) * 4);
    const UINT stride = static_cast<UINT>(expectedWidth * 4);
    ThrowIfFailed(
        converter->CopyPixels(nullptr, stride, static_cast<UINT>(decoded.bgra.size()), decoded.bgra.data()),
        "unsupported_frame_format",
        "Failed to copy PNG pixels");

    for (size_t i = 3; i < decoded.bgra.size(); i += 4)
    {
        const uint8_t alpha = decoded.bgra[i];
        if (alpha < 255)
        {
            decoded.alphaSeen = true;
            decoded.bgra[i - 3] = static_cast<uint8_t>((static_cast<int>(decoded.bgra[i - 3]) * alpha) / 255);
            decoded.bgra[i - 2] = static_cast<uint8_t>((static_cast<int>(decoded.bgra[i - 2]) * alpha) / 255);
            decoded.bgra[i - 1] = static_cast<uint8_t>((static_cast<int>(decoded.bgra[i - 1]) * alpha) / 255);
            decoded.bgra[i] = 255;
        }
    }
    return decoded;
}
```

- [ ] **Step 4: Add BGRA to NV12 conversion**

Add:

```cpp
std::vector<uint8_t> ConvertBgraToNv12(const std::vector<uint8_t>& bgra, int width, int height)
{
    const size_t yPlaneSize = static_cast<size_t>(width) * static_cast<size_t>(height);
    std::vector<uint8_t> nv12(yPlaneSize + yPlaneSize / 2);
    uint8_t* yPlane = nv12.data();
    uint8_t* uvPlane = nv12.data() + yPlaneSize;

    for (int y = 0; y < height; ++y)
    {
        for (int x = 0; x < width; ++x)
        {
            const size_t offset = (static_cast<size_t>(y) * width + x) * 4;
            const int b = bgra[offset + 0];
            const int g = bgra[offset + 1];
            const int r = bgra[offset + 2];
            yPlane[static_cast<size_t>(y) * width + x] = ClampByte(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
        }
    }

    for (int y = 0; y < height; y += 2)
    {
        for (int x = 0; x < width; x += 2)
        {
            int rSum = 0;
            int gSum = 0;
            int bSum = 0;
            for (int dy = 0; dy < 2; ++dy)
            {
                for (int dx = 0; dx < 2; ++dx)
                {
                    const size_t offset = (static_cast<size_t>(y + dy) * width + (x + dx)) * 4;
                    bSum += bgra[offset + 0];
                    gSum += bgra[offset + 1];
                    rSum += bgra[offset + 2];
                }
            }
            const int r = rSum / 4;
            const int g = gSum / 4;
            const int b = bSum / 4;
            const size_t uvOffset = static_cast<size_t>(y / 2) * width + x;
            uvPlane[uvOffset + 0] = ClampByte(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
            uvPlane[uvOffset + 1] = ClampByte(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
        }
    }
    return nv12;
}
```

- [ ] **Step 5: Add Media Foundation sink-writer encoding**

Add:

```cpp
struct VideoBackendResult
{
    bool overwroteExisting = false;
    uintmax_t bytes = 0;
    bool alphaComposited = false;
};

VideoBackendResult EncodeMp4WithMediaFoundation(const VideoAssembleRequest& request)
{
    std::error_code ec;
    fs::create_directories(request.outputPath.parent_path(), ec);
    if (ec)
        throw DirectorFrameValidationError("output_policy_violation", "Failed to create videos directory: " + ec.message());

    const fs::path tempPath = BuildTempVideoPath(request.outputPath);
    fs::remove(tempPath, ec);
    if (ec)
        throw DirectorFrameValidationError("backend_encode_failed", "Failed to clear temp video output: " + ec.message());

    HRESULT hr = MFStartup(MF_VERSION);
    ThrowIfFailed(hr, "backend_unavailable", "Media Foundation startup failed");

    VideoBackendResult result;
    HRESULT coHr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool uninitializeCom = SUCCEEDED(coHr);
    if (FAILED(coHr) && coHr != RPC_E_CHANGED_MODE)
    {
        MFShutdown();
        throw DirectorFrameValidationError("backend_unavailable", "COM initialization failed");
    }

    try
    {
        UINT32 frameRateNumerator = 0;
        UINT32 frameRateDenominator = 0;
        FrameRateRatio(request.fps, frameRateNumerator, frameRateDenominator);

        ComPtr<IWICImagingFactory> wicFactory;
        ThrowIfFailed(
            CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wicFactory)),
            "backend_unavailable",
            "Windows Imaging Component is unavailable");

        ComPtr<IMFSinkWriter> writer;
        ThrowIfFailed(
            MFCreateSinkWriterFromURL(tempPath.c_str(), nullptr, nullptr, &writer),
            "backend_unavailable",
            "Failed to create Media Foundation MP4 sink writer");

        ComPtr<IMFMediaType> outputType;
        ThrowIfFailed(MFCreateMediaType(&outputType), "backend_unavailable", "Failed to create output media type");
        outputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        outputType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_H264);
        outputType->SetUINT32(MF_MT_AVG_BITRATE, 8000000);
        outputType->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
        MFSetAttributeSize(outputType.Get(), MF_MT_FRAME_SIZE, request.width, request.height);
        MFSetAttributeRatio(outputType.Get(), MF_MT_FRAME_RATE, frameRateNumerator, frameRateDenominator);
        MFSetAttributeRatio(outputType.Get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1);

        DWORD streamIndex = 0;
        ThrowIfFailed(writer->AddStream(outputType.Get(), &streamIndex), "backend_unavailable", "Failed to add H.264 output stream");

        ComPtr<IMFMediaType> inputType;
        ThrowIfFailed(MFCreateMediaType(&inputType), "backend_unavailable", "Failed to create input media type");
        inputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        inputType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_NV12);
        inputType->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
        MFSetAttributeSize(inputType.Get(), MF_MT_FRAME_SIZE, request.width, request.height);
        MFSetAttributeRatio(inputType.Get(), MF_MT_FRAME_RATE, frameRateNumerator, frameRateDenominator);
        MFSetAttributeRatio(inputType.Get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
        ThrowIfFailed(writer->SetInputMediaType(streamIndex, inputType.Get(), nullptr), "backend_unavailable", "Failed to set NV12 input media type");
        ThrowIfFailed(writer->BeginWriting(), "backend_unavailable", "Failed to begin Media Foundation writing");

        const LONGLONG frameDuration = static_cast<LONGLONG>(10000000.0 / request.fps);
        for (int i = 0; i < request.frameCount; ++i)
        {
            const fs::path framePath = FramePathForIndex(request, request.startNumber + i);
            if (!fs::exists(framePath, ec))
                throw DirectorFrameValidationError("missing_frame", "Frame does not exist: " + PathToUtf8(framePath));

            DecodedFrame decoded = DecodePngBgra(wicFactory.Get(), framePath, request.width, request.height);
            result.alphaComposited = result.alphaComposited || decoded.alphaSeen;
            std::vector<uint8_t> nv12 = ConvertBgraToNv12(decoded.bgra, request.width, request.height);

            ComPtr<IMFMediaBuffer> buffer;
            ThrowIfFailed(MFCreateMemoryBuffer(static_cast<DWORD>(nv12.size()), &buffer), "backend_encode_failed", "Failed to create frame buffer");
            BYTE* destination = nullptr;
            DWORD maxLength = 0;
            DWORD currentLength = 0;
            ThrowIfFailed(buffer->Lock(&destination, &maxLength, &currentLength), "backend_encode_failed", "Failed to lock frame buffer");
            memcpy(destination, nv12.data(), nv12.size());
            buffer->Unlock();
            buffer->SetCurrentLength(static_cast<DWORD>(nv12.size()));

            ComPtr<IMFSample> sample;
            ThrowIfFailed(MFCreateSample(&sample), "backend_encode_failed", "Failed to create video sample");
            sample->AddBuffer(buffer.Get());
            sample->SetSampleTime(i * frameDuration);
            sample->SetSampleDuration(frameDuration);
            ThrowIfFailed(writer->WriteSample(streamIndex, sample.Get()), "backend_encode_failed", "Failed to write video sample");
        }

        ThrowIfFailed(writer->Finalize(), "backend_encode_failed", "Failed to finalize MP4");
        result.overwroteExisting = fs::exists(request.outputPath, ec);
        if (!MoveFileExW(
                tempPath.c_str(),
                request.outputPath.c_str(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        {
            throw DirectorFrameValidationError(
                "output_replace_failed",
                "Failed to atomically replace preview output with temp MP4");
        }
        result.bytes = fs::file_size(request.outputPath, ec);
    }
    catch (...)
    {
        fs::remove(tempPath, ec);
        if (uninitializeCom)
            CoUninitialize();
        MFShutdown();
        throw;
    }

    if (uninitializeCom)
        CoUninitialize();
    MFShutdown();
    return result;
}
```

- [ ] **Step 6: Replace temporary handler body with backend call**

In `HandleDirectorVideoAssemble`, replace the temporary `backend_unavailable` response after policy validation with:

```cpp
        VideoBackendResult backend = EncodeMp4WithMediaFoundation(request);
        nlohmann::json evidence = {
            { "backend", "media_foundation" },
            { "codec", "h264" },
            { "container", "mp4" },
            { "width", request.width },
            { "height", request.height },
            { "frame_count", request.frameCount },
            { "fps", request.fps }
        };
        if (backend.alphaComposited)
        {
            evidence["alpha_composited"] = true;
            evidence["alpha_background"] = "#000000";
        }

        nlohmann::json data;
        data["success"] = true;
        data["backend"] = "media_foundation";
        data["platform"] = "windows";
        data["output_path"] = PathToUtf8(request.outputPath);
        data["bytes"] = backend.bytes;
        data["overwrote_existing"] = backend.overwroteExisting;
        data["evidence"] = std::move(evidence);
        CRookServer::SendSuccess(res, data);
```

- [ ] **Step 7: Run native source tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: all native source tests pass.

- [ ] **Step 8: Commit backend implementation**

```powershell
git add src/RookNative/Handlers/DirectorHandler.cpp mcp_server/tests/test_director_native_source.py
git commit -m "feat: assemble Director preview MP4 with Media Foundation"
```

---

### Task 7: Live Route Tests

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add live route tests**

Append to `mcp_server/tests/test_director_routes_live.py`:

```python
async def test_director_video_assemble_rejects_output_outside_run_videos():
    allowed_root = _director_output_root()
    run_root = allowed_root / f"video_policy_{uuid4().hex}"
    frames_dir = run_root / "frames"
    output_path = allowed_root / "escaped.mp4"
    request = {
        "schema_version": 1,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "frames_dir": str(frames_dir),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": 1,
        "fps": 24,
        "fps_source": "timeline",
        "width": 320,
        "height": 180,
        "output_path": str(output_path),
        "codec": "h264",
        "container": "mp4",
    }

    _, envelope = await _post_director("video-assemble", request)

    assert envelope["success"] is False
    assert _error_code(envelope) == "output_policy_violation"


async def test_director_video_assemble_rejects_odd_dimensions_before_backend():
    allowed_root = _director_output_root()
    run_root = allowed_root / f"video_odd_{uuid4().hex}"
    request = {
        "schema_version": 1,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "frames_dir": str(run_root / "frames"),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": 1,
        "fps": 24,
        "fps_source": "timeline",
        "width": 321,
        "height": 180,
        "output_path": str(run_root / "videos" / "preview.mp4"),
        "codec": "h264",
        "container": "mp4",
    }

    _, envelope = await _post_director("video-assemble", request)

    assert envelope["success"] is False
    assert _error_code(envelope) == "unsupported_dimensions"
```

- [ ] **Step 2: Add guarded live success smoke**

Append:

```python
async def test_director_video_assemble_live_smoke_after_completed_run():
    _require_host()
    object_id = await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_video_smoke_{uuid4().hex}",
    )
    _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert view_envelope["success"] is True
    if view_envelope["data"]["camera"]["projection"] != "perspective":
        pytest.skip("Active Rhino view is not perspective; slice 1 director rejects parallel cameras.")

    run_id = f"video_smoke_{uuid4().hex}"
    result = await director.run_director(
        {
            "run_id": run_id,
            "output_root": str(_director_output_root()),
            "object_ids": [object_id],
            "timeline": {"fps": 12, "duration_seconds": 0.25},
            "resolution": {"width": 320, "height": 180},
            "display": {"mode": "Rendered"},
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            "camera_keyframes": [
                {"time": 0.0, "source": {"kind": "active_view"}},
                {"at": 1.0, "source": {"kind": "active_view"}},
            ],
        },
        port=_director_port(),
    )
    assert result["state"] == "complete"
    run_root = Path(result["run_root"])
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    request = {
        "schema_version": 1,
        "run_id": run_id,
        "run_root": str(run_root),
        "frames_dir": str(run_root / "frames"),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": manifest["frame_count"],
        "fps": manifest["timeline"]["fps"],
        "fps_source": "timeline",
        "width": manifest["resolution"]["width"],
        "height": manifest["resolution"]["height"],
        "output_path": str(run_root / "videos" / "preview.mp4"),
        "codec": "h264",
        "container": "mp4",
    }

    _, envelope = await _post_director("video-assemble", request)

    if envelope["success"] is False and _error_code(envelope) == "backend_unavailable":
        pytest.skip(f"Media Foundation backend unavailable on this machine: {envelope['data']}")
    assert envelope["success"] is True
    assert (run_root / "videos" / "preview.mp4").is_file()
    assert (run_root / "videos" / "preview.mp4").stat().st_size > 0
```

- [ ] **Step 3: Run live tests when Rhino is available**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_routes_live.py -q
```

Expected: route rejection tests pass. Success smoke passes on a machine with Media Foundation H.264 available, or skips with `backend_unavailable`.

- [ ] **Step 4: Commit live tests**

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test: cover Director video assembly live route"
```

---

### Task 8: End-to-End Verification and Build

**Files:**
- Potentially modify files touched in prior tasks only if verification reveals defects.

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_video.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_native_source.py -q
```

Expected: all pass.

- [ ] **Step 2: Build RookNative with the working MSVC toolset**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: `Build succeeded`. If it fails because a Media Foundation symbol or library is wrong, fix only `src/RookNative/Handlers/DirectorHandler.cpp` and rerun this exact build.

- [ ] **Step 3: Deploy local testing build if live Rhino will verify the route**

Use the existing local testing deployment workflow for this repo. If invoking the Rook skill manually, use `rook:deploy-local-testing`.

Expected: installed local RookNative is updated with the new `/director/video-assemble` route.

- [ ] **Step 4: Run guarded live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_routes_live.py -q
```

Expected: all existing live Director tests still pass. The new MP4 smoke passes or skips only with structured `backend_unavailable`.

- [ ] **Step 5: Manual artifact verification**

Run a short Director frame run with timeline FPS, then call:

```python
await director_video.assemble_director_video(
    {"run_root": "C:/Users/aryan/AppData/Local/Rook/rookvision_director/<run_id>"}
)
```

Expected:

```text
<run_root>/videos/preview.mp4 exists and is non-empty
<run_root>/video_manifest.json has state "complete"
<run_root>/status.json remains state "complete"
video_manifest.json records backend "media_foundation", fps, frame_count, dimensions, output_current true, preserved_previous_output false
video_manifest.json records output_path "videos/preview.mp4" and completed_at
```

- [ ] **Step 6: Verify failed backend/status separation**

Use a run with odd dimensions or temporarily force a native `backend_unavailable` path, then assemble.

Expected:

```text
video_manifest.json has state "failed"
status.json still has the original frame-run state
videos/preview.mp4 is absent on first failure or preserved as stale if it existed
output_current is false
preserved_previous_output matches whether a prior preview existed
```

- [ ] **Step 7: Commit verification fixes**

If any verification fixes were needed:

```powershell
git add <fixed-files>
git commit -m "fix: harden Director video assembly verification"
```

If no fixes were needed, do not create an empty commit.

---

## Review Checklist

- Python validates completed run, every frame exists, every frame has expected PNG dimensions, FPS is timeline or explicit override, and odd dimensions fail before native invocation.
- Explicit FPS override has a positive success test.
- Native independently enforces configured Director output root for `run_root`, `frames_dir`, and `output_path`.
- Native reads only `run_root/frames/frame_%04d.png` and writes only under `run_root/videos`.
- `status.json` is not modified by video assembly success or failure.
- Failed assembly cannot make a stale `preview.mp4` appear current.
- Native preview replacement uses an atomic Windows replace operation; it does not remove the previous good preview before moving the new MP4 into place.
- Native Media Foundation temp output path still ends in `.mp4`.
- `video_manifest.json` presents `output_path` as `videos/preview.mp4` and uses `completed_at`, not absolute output paths or `finished_at`.
- No FFmpeg code path exists.
- No publishing/UI/gallery code is touched.
- Native build verification is reported only if the MSVC/Rhino toolchain build actually ran.
