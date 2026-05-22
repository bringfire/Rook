# RookVisionDirector Video Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `rhino_director_publish_video` support that publishes a completed/current Director MP4 preview as a durable RookVision `generated_video` artifact, guarded by `director_publish_standard_v1`.

**Architecture:** Python owns Director lifecycle, video-profile validation, hashes, compact provenance, idempotency, and `publish_manifest.json`. Managed C# owns the artifact-boundary safety envelope and creates or confirms the `generated_video/video.mp4` artifact. Native gets at most thin Vision-route proxy wiring and must not own Director publish validation, artifact creation, video assembly, or sidecar behavior.

**Tech Stack:** Python MCP server with pytest, managed C# Vision handler and `ArtifactStore`, thin RookNative Vision proxy route through the existing `vision_dispatch` bridge, existing `nlohmann::json`/`httplib` native route patterns, no new external dependencies.

---

## Source Documents

- Approved design: `docs/superpowers/specs/2026-05-21-rookvisiondirector-video-publish-design.md`
- Director run orchestration: `mcp_server/src/rook/director.py`
- Director video assembly: `mcp_server/src/rook/director_video.py`
- Managed artifact store: `src/Rook/Artifacts/ArtifactStore.cs`
- Managed Vision boundary: `src/Rook/Handlers/VisionHandler.cs`
- Native bridge allowlist/dispatch: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Native Vision proxy: `src/RookNative/Handlers/VisionHandler.cpp`
- Route registration: `src/RookNative/RookServer.cpp`
- Repo instructions: `AGENTS.md` content supplied in the conversation

## File Structure

Create:

- `mcp_server/src/rook/director_publish.py`
  Python source of truth for `director_publish_standard_v1`, run/video manifest validation, manifest consistency checks, source hashes, compact `metadata.director`, idempotency, managed publish call, and `publish_manifest.json`.

- `mcp_server/tests/test_director_publish.py`
  Pure Python tests for success, profile rejection, manifest mismatch, idempotency, managed rejection preservation, and failure manifest writing.

- `src/Rook/Services/Vision/Director/DirectorVideoPublishModels.cs`
  Managed request parsing/result models and small helpers for contract field extraction.

- `src/Rook/Services/Vision/Director/DirectorVideoPublisher.cs`
  Managed artifact-boundary safety checks and `ArtifactStore.Create(...)` call.

- `src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs`
  Managed unit tests for Director-root policy, advisory path handling, fact/hash mismatch, creation, prior-artifact confirmation, and sidecar absence.

Modify:

- `mcp_server/src/rook/server.py`
  Register `rhino_director_publish_video` and dispatch to `director_publish.publish_director_video`.

- `mcp_server/src/rook/agent/tool_groups.py`
  Add `rhino_director_publish_video` to the `director` group. Keep it out of `director_readonly`.

- `mcp_server/tests/test_director_mcp_tools.py`
  Add MCP schema, dispatch, and tool-group tests.

- `src/Rook/Handlers/VisionHandler.cs`
  Route `publish_director_video` through the off-UI dispatcher and call `DirectorVideoPublisher`.

- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
  Add source-level or handler-level tests proving the op is off-UI and creates only a generated-video/video artifact through the publisher path.

- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
  Add `publish_director_video` to the native `vision_dispatch` allowlist and route it through `Vision.DispatchOffUi`.

- `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
  Update the expected-op count from 15 to 16 and add a test pinning the Director publish op.

- `src/RookNative/Handlers/VisionHandler.h`
  Declare `HandleVisionDirectorPublishVideo`.

- `src/RookNative/Handlers/VisionHandler.cpp`
  Add one thin handler that calls `DispatchVisionOp(req, res, "publish_director_video")`.

- `src/RookNative/RookServer.cpp`
  Register `POST /vision/director/publish-video` before broader `/vision/...` routes if ordering matters.

- `mcp_server/tests/test_director_routes_live.py`
  Add guarded live smoke only after non-live tests pass.

Do not modify:

- `src/RookNative/Handlers/DirectorHandler.cpp`
- `src/RookNative/Handlers/DirectorHandler.h`
- `mcp_server/src/rook/director.py`
- `mcp_server/src/rook/director_video.py`
- `src/RookNative/RookNative.vcxproj`
- `src/RookNative/RookNative.vcxproj.filters`
- Vision Gallery UI files

The native files already exist in the project; adding declarations/functions to existing compiled files does not require project-file edits.

---

## Task 1: Add Python Publish Contract Tests

**Files:**
- Create: `mcp_server/tests/test_director_publish.py`
- Read: `mcp_server/src/rook/director_video.py`

- [ ] **Step 1: Create focused test helpers**

Create `mcp_server/tests/test_director_publish.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rook import director_publish


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _standard_manifest(
    run_root: Path,
    *,
    run_id: str = "run-a",
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    frame_count: int = 96,
    camera_plan: dict | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "director_version": "slice1",
        "run_id": run_id,
        "run_root": str(run_root),
        "frame_count": frame_count,
        "resolution": {"width": width, "height": height},
        "timeline": {
            "source": "timeline",
            "fps": fps,
            "duration_seconds": frame_count / fps,
            "frame_count": frame_count,
        },
        "camera_plan": camera_plan
        or {
            "strategy": "curve_follow_target",
            "request_shape": "camera_strategy",
            "aspect_authority": "output_resolution",
            "optics_authority": "lens_length",
            "provenance": {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "curve_sampling": {"sampling_mode": "normalized_parameter"},
            },
        },
        "camera_keyframes": [],
        "camera_keyframe_provenance": [],
        "frames": [
            {"frame_index": index, "frame_id": f"frame_{index:04d}"}
            for index in range(1, frame_count + 1)
        ],
    }


def _standard_video_manifest(
    *,
    run_id: str = "run-a",
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    frame_count: int = 96,
    state: str = "complete",
    output_current: bool = True,
    format_value: str = "mp4",
    container: str = "mp4",
    codec: str = "h264",
) -> dict:
    return {
        "schema_version": 1,
        "state": state,
        "run_id": run_id,
        "backend": "media_foundation",
        "platform": "windows",
        "format": format_value,
        "container": container,
        "codec": codec,
        "fps": fps,
        "fps_source": "timeline",
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "input_pattern": "frames/frame_%04d.png",
        "output_path": "videos/preview.mp4",
        "bytes": 8,
        "output_current": output_current,
        "preserved_previous_output": False,
        "completed_at": "2026-05-21T00:00:00+00:00",
        "error": None,
    }


def _write_standard_run(root: Path, **overrides) -> Path:
    run_root = root / "run-a"
    run_root.mkdir(parents=True)
    manifest = _standard_manifest(
        run_root,
        width=overrides.get("width", 1280),
        height=overrides.get("height", 720),
        fps=overrides.get("fps", 24),
        frame_count=overrides.get("frame_count", 96),
        camera_plan=overrides.get("camera_plan"),
    )
    video_manifest = _standard_video_manifest(
        width=overrides.get("video_width", overrides.get("width", 1280)),
        height=overrides.get("video_height", overrides.get("height", 720)),
        fps=overrides.get("video_fps", overrides.get("fps", 24)),
        frame_count=overrides.get("video_frame_count", overrides.get("frame_count", 96)),
        state=overrides.get("video_state", "complete"),
        output_current=overrides.get("output_current", True),
        format_value=overrides.get("format_value", "mp4"),
        container=overrides.get("container", "mp4"),
        codec=overrides.get("codec", "h264"),
    )
    _write_json(run_root / "manifest.json", manifest)
    _write_json(run_root / "status.json", {"state": overrides.get("state", "complete"), "run_id": "run-a"})
    _write_json(run_root / "video_manifest.json", video_manifest)
    video_path = run_root / "videos" / "preview.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(overrides.get("video_bytes", b"fake-mp4"))
    return run_root


class FakeManagedPublish:
    def __init__(self, response: dict | None = None):
        self.calls: list[tuple[str, str, dict, int | None]] = []
        self.response = response or {
            "success": True,
            "data": {
                "artifact_id": "00000000-0000-0000-0000-000000000099",
                "kind": "generated_video",
                "files": [{"role": "video", "path": "video.mp4"}],
            },
        }

    async def __call__(self, endpoint, method="GET", data=None, port=None):
        self.calls.append((endpoint, method, data, port))
        return self.response
```

- [ ] **Step 2: Add success test for managed request and metadata**

Append:

```python
@pytest.mark.asyncio
async def test_publish_video_validates_profile_and_calls_managed_route(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "complete"
    assert result["artifact_id"] == "00000000-0000-0000-0000-000000000099"
    assert result["profile"] == "director_publish_standard_v1"
    assert result["preset"] == "hd_720"
    assert result["source_video"] == "videos/preview.mp4"
    assert result["sidecar_policy"] == "existing_generated_video_pipeline"

    assert managed.calls[0][0:2] == ("/vision/director/publish-video", "POST")
    request = managed.calls[0][2]
    assert request["profile"] == "director_publish_standard_v1"
    assert request["preset"] == "hd_720"
    assert request["source"]["relative_path"] == "videos/preview.mp4"
    assert request["source"]["byte_size"] == len(b"fake-mp4")
    assert len(request["source"]["sha256"]) == 64
    assert request["facts"] == {
        "container": "mp4",
        "format": "mp4",
        "codec": "h264",
        "width": 1280,
        "height": 720,
        "fps": 24,
        "frame_count": 96,
    }
    director_meta = request["metadata"]["director"]
    assert director_meta["profile"] == "director_publish_standard_v1"
    assert director_meta["preset"] == "hd_720"
    assert director_meta["source_video"] == "videos/preview.mp4"
    assert director_meta["camera_strategy"] == "curve_follow_target"
    assert director_meta["camera"]["curve_id"] == "00000000-0000-0000-0000-000000000001"
    assert "run_root" not in director_meta

    publish_manifest = json.loads((run_root / "publish_manifest.json").read_text(encoding="utf-8"))
    assert publish_manifest["state"] == "complete"
    assert publish_manifest["artifact_id"] == result["artifact_id"]
    assert publish_manifest["preset"] == "hd_720"
    assert publish_manifest["sidecar_policy"] == "existing_generated_video_pipeline"
```

- [ ] **Step 3: Add failure tests for required Director state**

Append:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"state": "failed"}, "run_not_complete"),
        ({"video_state": "failed"}, "video_not_assembled"),
        ({"output_current": False}, "video_not_current"),
    ],
)
async def test_publish_video_rejects_incomplete_or_stale_runs(tmp_path, overrides, code):
    run_root = _write_standard_run(tmp_path / "director", **overrides)
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == code
    assert managed.calls == []
    publish_manifest = json.loads((run_root / "publish_manifest.json").read_text(encoding="utf-8"))
    assert publish_manifest["error"]["code"] == code


@pytest.mark.asyncio
async def test_publish_video_missing_video_manifest_is_video_not_assembled(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    (run_root / "video_manifest.json").unlink()
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "video_not_assembled"
    assert managed.calls == []
```

- [ ] **Step 4: Add profile and manifest consistency tests**

Append:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"width": 1024, "height": 768, "video_width": 1024, "video_height": 768}, "unsupported_video_profile"),
        ({"fps": 60, "video_fps": 60}, "unsupported_video_profile"),
        ({"codec": "H.264"}, "unsupported_video_profile"),
        ({"container": "mov"}, "unsupported_video_profile"),
        ({"format_value": "mpeg4"}, "unsupported_video_profile"),
    ],
)
async def test_publish_video_rejects_nonstandard_profile(tmp_path, overrides, code):
    run_root = _write_standard_run(tmp_path / "director", **overrides)
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == code
    assert "director_publish_standard_v1" in result["error"]["message"]
    assert managed.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"video_width": 1920},
        {"video_height": 1080},
        {"video_fps": 30},
        {"video_frame_count": 95},
    ],
)
async def test_publish_video_rejects_frame_video_manifest_mismatch(tmp_path, overrides):
    run_root = _write_standard_run(tmp_path / "director", **overrides)
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "video_manifest_invalid"
    assert managed.calls == []
```

- [ ] **Step 5: Add idempotency and managed rejection tests**

Append:

```python
@pytest.mark.asyncio
async def test_publish_video_idempotent_path_passes_prior_artifact_id(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    previous = {
        "schema_version": 1,
        "state": "complete",
        "artifact_id": "00000000-0000-0000-0000-000000000099",
        "profile": "director_publish_standard_v1",
        "preset": "hd_720",
        "source_video": "videos/preview.mp4",
        "source_sha256": director_publish._sha256_file(run_root / "videos" / "preview.mp4"),
        "source_byte_size": (run_root / "videos" / "preview.mp4").stat().st_size,
        "video_manifest_hash": director_publish._sha256_file(run_root / "video_manifest.json"),
        "frame_manifest_hash": director_publish._sha256_file(run_root / "manifest.json"),
        "sidecar_policy": "existing_generated_video_pipeline",
    }
    _write_json(run_root / "publish_manifest.json", previous)
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "complete"
    assert managed.calls[0][2]["prior_artifact_id"] == previous["artifact_id"]
    publish_manifest = json.loads((run_root / "publish_manifest.json").read_text(encoding="utf-8"))
    assert publish_manifest["prior_artifact_id"] == previous["artifact_id"]


@pytest.mark.asyncio
async def test_publish_video_malformed_prior_artifact_id_fails(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    _write_json(
        run_root / "publish_manifest.json",
        {
            "schema_version": 1,
            "state": "complete",
            "artifact_id": "not-a-guid",
            "profile": "director_publish_standard_v1",
            "preset": "hd_720",
            "source_video": "videos/preview.mp4",
            "source_sha256": director_publish._sha256_file(run_root / "videos" / "preview.mp4"),
            "source_byte_size": (run_root / "videos" / "preview.mp4").stat().st_size,
            "video_manifest_hash": director_publish._sha256_file(run_root / "video_manifest.json"),
            "frame_manifest_hash": director_publish._sha256_file(run_root / "manifest.json"),
        },
    )

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=FakeManagedPublish(),
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "publish_manifest_invalid"


@pytest.mark.asyncio
async def test_publish_video_preserves_managed_subcode(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    managed = FakeManagedPublish(
        {
            "success": False,
            "data": {
                "code": "artifact_boundary_mismatch",
                "managed_subcode": "source_hash_mismatch",
                "message": "Managed publish rejected the source video hash.",
            },
        }
    )

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "artifact_boundary_mismatch"
    assert result["error"]["managed_subcode"] == "source_hash_mismatch"
    publish_manifest = json.loads((run_root / "publish_manifest.json").read_text(encoding="utf-8"))
    assert publish_manifest["error"]["managed_subcode"] == "source_hash_mismatch"
```

- [ ] **Step 6: Run tests and verify module-missing failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_publish.py -q
```

Expected:

```text
ImportError or AttributeError for rook.director_publish / publish_director_video
```

Do not implement managed or MCP code in this task.

---

## Task 2: Implement Python Director Publish Module

**Files:**
- Create: `mcp_server/src/rook/director_publish.py`
- Test: `mcp_server/tests/test_director_publish.py`

- [ ] **Step 1: Add module constants, error type, and filesystem helpers**

Create `mcp_server/src/rook/director_publish.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

PUBLISH_SCHEMA_VERSION = 1
PROFILE_NAME = "director_publish_standard_v1"
RELATIVE_SOURCE_VIDEO = "videos/preview.mp4"
SIDECAR_POLICY = "existing_generated_video_pipeline"
ALLOWED_PRESETS: dict[tuple[int, int], str] = {
    (1280, 720): "hd_720",
    (1920, 1080): "full_hd_1080",
    (3840, 2160): "uhd_4k",
    (7680, 4320): "uhd_8k",
}
ALLOWED_FPS = {24, 30}


class DirectorPublishError(Exception):
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
        raise DirectorPublishError(
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set"
        )
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DirectorPublishError(f"{path.name} must contain a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

- [ ] **Step 2: Add manifest writers and failure helper**

Append:

```python
def _base_publish_manifest(
    *,
    state: str,
    run_id: str,
    run_root: Path,
    started_at: str,
    artifact_id: str | None = None,
    prior_artifact_id: str | None = None,
    profile: str | None = None,
    preset: str | None = None,
    source_sha256: str | None = None,
    source_byte_size: int | None = None,
    video_manifest_hash: str | None = None,
    frame_manifest_hash: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLISH_SCHEMA_VERSION,
        "state": state,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "prior_artifact_id": prior_artifact_id,
        "profile": profile,
        "preset": preset,
        "run_root": str(run_root),
        "source_path": str((run_root / RELATIVE_SOURCE_VIDEO).resolve()),
        "source_video": RELATIVE_SOURCE_VIDEO,
        "source_sha256": source_sha256,
        "source_byte_size": source_byte_size,
        "video_manifest_hash": video_manifest_hash,
        "frame_manifest_hash": frame_manifest_hash,
        "sidecar_policy": SIDECAR_POLICY,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "error": error,
    }


def _failure(
    *,
    run_id: str,
    run_root: Path,
    started_at: str,
    code: str,
    message: str,
    managed_subcode: str | None = None,
    prior_artifact_id: str | None = None,
    profile: str | None = None,
    preset: str | None = None,
    source_sha256: str | None = None,
    source_byte_size: int | None = None,
    video_manifest_hash: str | None = None,
    frame_manifest_hash: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if managed_subcode:
        error["managed_subcode"] = managed_subcode
    manifest = _base_publish_manifest(
        state="failed",
        run_id=run_id,
        run_root=run_root,
        started_at=started_at,
        prior_artifact_id=prior_artifact_id,
        profile=profile,
        preset=preset,
        source_sha256=source_sha256,
        source_byte_size=source_byte_size,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
        error=error,
    )
    _atomic_write_json(run_root / "publish_manifest.json", manifest)
    return manifest
```

- [ ] **Step 3: Add profile and manifest validation helpers**

Append:

```python
def _positive_int(value: Any) -> int | None:
    if type(value) is not int or value <= 0:
        return None
    return value


def _integer_fps(value: Any) -> int | None:
    if type(value) is int and value > 0:
        return value
    if type(value) is float and value.is_integer() and value > 0:
        return int(value)
    return None


def _timeline_fps(manifest: dict[str, Any]) -> int | None:
    timeline = manifest.get("timeline")
    if not isinstance(timeline, dict):
        return None
    return _integer_fps(timeline.get("fps"))


def _validate_manifest_pair(
    manifest: dict[str, Any],
    video_manifest: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    resolution = manifest.get("resolution")
    if not isinstance(resolution, dict):
        return "manifest resolution is required", None
    width = _positive_int(resolution.get("width"))
    height = _positive_int(resolution.get("height"))
    frame_count = _positive_int(manifest.get("frame_count"))
    fps = _timeline_fps(manifest)
    if width is None or height is None or frame_count is None or fps is None:
        return "manifest must contain positive resolution, frame_count, and timeline fps", None
    video_width = _positive_int(video_manifest.get("width"))
    video_height = _positive_int(video_manifest.get("height"))
    video_frame_count = _positive_int(video_manifest.get("frame_count"))
    video_fps = _integer_fps(video_manifest.get("fps"))
    if (
        video_width != width
        or video_height != height
        or video_frame_count != frame_count
        or video_fps != fps
    ):
        return "manifest.json and video_manifest.json disagree on frame count, resolution, or fps", None
    return None, {
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
    }


def _validate_profile(video_manifest: dict[str, Any], facts: dict[str, Any]) -> tuple[str | None, str | None]:
    required = ("format", "container", "codec")
    for field in required:
        if not isinstance(video_manifest.get(field), str):
            return "video_manifest_invalid", f"video_manifest.{field} is required"
    if (
        video_manifest["format"] != "mp4"
        or video_manifest["container"] != "mp4"
        or video_manifest["codec"] != "h264"
    ):
        return "unsupported_video_profile", (
            "Director publish supports director_publish_standard_v1: "
            "1280x720, 1920x1080, 3840x2160, or 7680x4320 MP4/H.264 "
            "at supported FPS values."
        )
    preset = ALLOWED_PRESETS.get((facts["width"], facts["height"]))
    if preset is None or facts["fps"] not in ALLOWED_FPS:
        return "unsupported_video_profile", (
            "Director publish supports director_publish_standard_v1: "
            "1280x720, 1920x1080, 3840x2160, or 7680x4320 MP4/H.264 "
            "at supported FPS values."
        )
    return None, preset
```

- [ ] **Step 4: Add compact camera metadata builder**

Append:

```python
def _camera_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    plan = manifest.get("camera_plan")
    plan = plan if isinstance(plan, dict) else {}
    strategy = str(plan.get("strategy") or "")
    if strategy == "curve_follow_target":
        provenance = plan.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        camera = {
            "strategy": "curve_follow_target",
            "curve_id": provenance.get("curve_id"),
            "target": provenance.get("target"),
            "up": provenance.get("up"),
            "sampling": provenance.get("sampling"),
        }
        return {"camera_strategy": strategy, "camera": camera}
    if strategy == "keyframes":
        keyframes = manifest.get("camera_keyframes")
        keyframes = keyframes if isinstance(keyframes, list) else []
        sources = []
        for keyframe in keyframes:
            if not isinstance(keyframe, dict):
                continue
            source = keyframe.get("source")
            source = source if isinstance(source, dict) else {}
            sources.append(
                {
                    "kind": source.get("kind"),
                    "name": source.get("name"),
                }
            )
        return {
            "camera_strategy": strategy,
            "camera": {
                "strategy": "keyframes",
                "keyframe_count": len(keyframes),
                "sources": sources,
            },
        }
    return {"camera_strategy": strategy, "camera": {"strategy": strategy}}


def _metadata_director(
    *,
    run_id: str,
    manifest: dict[str, Any],
    facts: dict[str, Any],
    preset: str,
    video_manifest_hash: str,
    frame_manifest_hash: str,
) -> dict[str, Any]:
    timeline = manifest.get("timeline")
    timeline = timeline if isinstance(timeline, dict) else {}
    camera = _camera_metadata(manifest)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "profile": PROFILE_NAME,
        "preset": preset,
        "source_video": RELATIVE_SOURCE_VIDEO,
        "video_manifest_hash": video_manifest_hash,
        "frame_manifest_hash": frame_manifest_hash,
        "camera_strategy": camera["camera_strategy"],
        "camera": camera["camera"],
        "timeline": {
            "fps": facts["fps"],
            "duration_seconds": timeline.get("duration_seconds"),
            "frame_count": facts["frame_count"],
        },
        "resolution": {
            "width": facts["width"],
            "height": facts["height"],
        },
    }
```

- [ ] **Step 5: Add prior publish validation**

Append:

```python
def _prior_publish_artifact_id(
    publish_manifest_path: Path,
    *,
    source_sha256: str,
    source_byte_size: int,
    video_manifest_hash: str,
    frame_manifest_hash: str,
    preset: str,
) -> tuple[str | None, str | None]:
    if not publish_manifest_path.exists():
        return None, None
    try:
        previous = _read_json(publish_manifest_path)
    except (OSError, json.JSONDecodeError, DirectorPublishError):
        return None, "publish_manifest_invalid"
    if previous.get("state") != "complete":
        return None, None
    artifact_id = previous.get("artifact_id")
    try:
        uuid.UUID(str(artifact_id))
    except (TypeError, ValueError):
        return None, "publish_manifest_invalid"
    expected = {
        "profile": PROFILE_NAME,
        "preset": preset,
        "source_video": RELATIVE_SOURCE_VIDEO,
        "source_sha256": source_sha256,
        "source_byte_size": source_byte_size,
        "video_manifest_hash": video_manifest_hash,
        "frame_manifest_hash": frame_manifest_hash,
    }
    for key, value in expected.items():
        if previous.get(key) != value:
            return None, "publish_facts_changed"
    return str(artifact_id), None
```

- [ ] **Step 6: Add public publisher**

Append:

```python
async def publish_director_video(
    request: dict[str, Any],
    *,
    call_managed=call_rhino,
    director_output_root: Path | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    allowed_root = (director_output_root or _default_output_root()).expanduser().resolve()
    run_root = Path(str(request.get("run_root", ""))).expanduser().resolve()
    run_id = run_root.name or ""
    if not _is_relative_to(run_root, allowed_root):
        return {
            "schema_version": PUBLISH_SCHEMA_VERSION,
            "state": "failed",
            "run_id": run_id,
            "error": {
                "code": "run_root_policy_violation",
                "message": "run_root must resolve under the configured Director output root",
            },
        }
    if not run_root.is_dir():
        return {
            "schema_version": PUBLISH_SCHEMA_VERSION,
            "state": "failed",
            "run_id": run_id,
            "error": {
                "code": "missing_run_metadata",
                "message": "run_root must be an existing Director run directory",
            },
        }

    try:
        status = _read_json(run_root / "status.json")
    except (OSError, json.JSONDecodeError, DirectorPublishError) as ex:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="run_not_complete", message=str(ex))
    if status.get("state") != "complete":
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="run_not_complete", message="Director frame run must be complete before publish")

    try:
        manifest = _read_json(run_root / "manifest.json")
    except (OSError, json.JSONDecodeError, DirectorPublishError) as ex:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="missing_run_metadata", message=str(ex))
    run_id = str(manifest.get("run_id") or run_id)

    try:
        video_manifest = _read_json(run_root / "video_manifest.json")
    except (OSError, json.JSONDecodeError, DirectorPublishError) as ex:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="video_not_assembled", message=str(ex))
    if video_manifest.get("state") != "complete":
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="video_not_assembled", message="Director video must be assembled before publish")
    if video_manifest.get("output_current") is not True:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="video_not_current", message="Director preview is stale or not current")
    if video_manifest.get("output_path") != RELATIVE_SOURCE_VIDEO:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="video_manifest_invalid", message="video_manifest output_path must be videos/preview.mp4")

    mismatch, facts = _validate_manifest_pair(manifest, video_manifest)
    if mismatch is not None or facts is None:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="video_manifest_invalid", message=mismatch or "invalid manifest facts")

    profile_error, preset = _validate_profile(video_manifest, facts)
    if profile_error is not None or preset is None:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code=profile_error, message=preset or "unsupported video profile")

    source_path = run_root / RELATIVE_SOURCE_VIDEO
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        return _failure(run_id=run_id, run_root=run_root, started_at=started_at, code="video_not_assembled", message="videos/preview.mp4 is missing or empty", profile=PROFILE_NAME, preset=preset)

    source_sha256 = _sha256_file(source_path)
    source_byte_size = source_path.stat().st_size
    video_manifest_hash = _sha256_file(run_root / "video_manifest.json")
    frame_manifest_hash = _sha256_file(run_root / "manifest.json")

    prior_artifact_id, prior_error = _prior_publish_artifact_id(
        run_root / "publish_manifest.json",
        source_sha256=source_sha256,
        source_byte_size=source_byte_size,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
        preset=preset,
    )
    if prior_error is not None:
        code = prior_error
        message = "publish_manifest.json is invalid" if code == "publish_manifest_invalid" else "publish facts changed from prior successful publish"
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code=code,
            message=message,
            profile=PROFILE_NAME,
            preset=preset,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            video_manifest_hash=video_manifest_hash,
            frame_manifest_hash=frame_manifest_hash,
        )

    metadata_director = _metadata_director(
        run_id=run_id,
        manifest=manifest,
        facts=facts,
        preset=preset,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
    )
    managed_request = {
        "run_id": run_id,
        "profile": PROFILE_NAME,
        "preset": preset,
        "source": {
            "run_root": str(run_root),
            "relative_path": RELATIVE_SOURCE_VIDEO,
            "absolute_path": str(source_path.resolve()),
            "byte_size": source_byte_size,
            "sha256": source_sha256,
        },
        "facts": {
            "container": "mp4",
            "format": "mp4",
            "codec": "h264",
            "width": facts["width"],
            "height": facts["height"],
            "fps": facts["fps"],
            "frame_count": facts["frame_count"],
        },
        "hashes": {
            "video_manifest_sha256": video_manifest_hash,
            "frame_manifest_sha256": frame_manifest_hash,
        },
        "metadata": {"director": metadata_director},
    }
    if prior_artifact_id is not None:
        managed_request["prior_artifact_id"] = prior_artifact_id

    managed = await call_managed(
        "/vision/director/publish-video", "POST", managed_request, port=port
    )
    data = managed.get("data") if isinstance(managed.get("data"), dict) else {}
    if not managed.get("success"):
        code = str(data.get("code") or "managed_publish_rejected")
        managed_subcode = data.get("managed_subcode")
        result = _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code=code,
            message=str(data.get("message") or "Managed publish rejected the request"),
            managed_subcode=str(managed_subcode) if managed_subcode else None,
            prior_artifact_id=prior_artifact_id,
            profile=PROFILE_NAME,
            preset=preset,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            video_manifest_hash=video_manifest_hash,
            frame_manifest_hash=frame_manifest_hash,
        )
        if code == "published_artifact_missing":
            result["error"]["code"] = "published_artifact_missing"
        return result

    artifact_id = str(data.get("artifact_id") or "")
    success_manifest = _base_publish_manifest(
        state="complete",
        run_id=run_id,
        run_root=run_root,
        started_at=started_at,
        artifact_id=artifact_id,
        prior_artifact_id=prior_artifact_id,
        profile=PROFILE_NAME,
        preset=preset,
        source_sha256=source_sha256,
        source_byte_size=source_byte_size,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
        error=None,
    )
    _atomic_write_json(run_root / "publish_manifest.json", success_manifest)
    return {
        "schema_version": PUBLISH_SCHEMA_VERSION,
        "state": "complete",
        "run_id": run_id,
        "artifact_id": artifact_id,
        "profile": PROFILE_NAME,
        "preset": preset,
        "source_video": RELATIVE_SOURCE_VIDEO,
        "sidecar_policy": SIDECAR_POLICY,
    }
```

- [ ] **Step 7: Run Python publish tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_publish.py -q
```

Expected:

```text
all tests pass
```

If tests expose small message mismatches, adjust tests only when the code still satisfies the spec; otherwise adjust implementation.

- [ ] **Step 8: Commit Python publish module**

Run:

```powershell
git add mcp_server/src/rook/director_publish.py mcp_server/tests/test_director_publish.py
git commit -m "feat: add Director video publish contract"
```

---

## Task 3: Add MCP Tool Registration And Dispatch

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Add failing MCP schema and dispatch tests**

In `mcp_server/tests/test_director_mcp_tools.py`, add:

```python
@pytest.mark.asyncio
async def test_director_publish_video_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_publish_video" in by_name
    schema = by_name["rhino_director_publish_video"].inputSchema
    assert schema["required"] == ["run_root"]
    assert schema["properties"]["run_root"]["type"] == "string"
    assert _find_rejected_schema_keywords(schema) == []


@pytest.mark.asyncio
async def test_director_publish_video_dispatches_to_python(monkeypatch):
    request = {"run_root": "C:/Users/aryan/AppData/Local/Rook/rookvision_director/run-a"}
    called = {}

    async def fake_publish(arguments, *, port=None):
        called["arguments"] = arguments
        called["port"] = port
        return {
            "state": "complete",
            "artifact_id": "00000000-0000-0000-0000-000000000099",
            "profile": "director_publish_standard_v1",
            "preset": "hd_720",
        }

    monkeypatch.setattr(server.director_publish, "publish_director_video", fake_publish)
    result = await server.call_tool("rhino_director_publish_video", request)

    assert called["arguments"] == request
    assert result[0].text
    payload = json.loads(result[0].text)
    assert payload["state"] == "complete"


def test_director_publish_video_in_director_group_only():
    assert "rhino_director_publish_video" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_publish_video" not in tool_groups.TOOL_GROUPS["director_readonly"]
```

If `server` or `tool_groups` are not imported under those names in the file, use the existing imports and style in `test_director_mcp_tools.py`.

- [ ] **Step 2: Run MCP tests and verify failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected:

```text
fails because rhino_director_publish_video is not registered/imported
```

- [ ] **Step 3: Import `director_publish` in server**

In `mcp_server/src/rook/server.py`, update the Director imports near existing `director` / `director_video` imports:

```python
from . import director, director_publish, director_video
```

Use the local import layout already present in this file. Do not duplicate imports.

- [ ] **Step 4: Add tool schema**

In the tool list near `rhino_director_assemble_video`, add:

```python
Tool(
    name="rhino_director_publish_video",
    description=(
        "Publish a completed/current RookVisionDirector videos/preview.mp4 "
        "as a durable RookVision generated_video artifact. Validates "
        "director_publish_standard_v1 and writes publish_manifest.json. "
        "Does not create sidecars or transcode."
    ),
    inputSchema={
        "type": "object",
        "required": ["run_root"],
        "properties": {
            "run_root": {
                "type": "string",
                "description": "Absolute path to a completed Director run root with current videos/preview.mp4.",
            },
        },
    },
),
```

Do not add `force`, `video_profile`, sidecar options, or output path overrides.

- [ ] **Step 5: Add dispatch case**

In `call_tool`, after `rhino_director_assemble_video`, add:

```python
        case "rhino_director_publish_video":
            try:
                result = {
                    "success": True,
                    "data": await director_publish.publish_director_video(
                        arguments, port=port
                    ),
                }
            except director_publish.DirectorPublishError as exc:
                result = {
                    "success": False,
                    "data": {
                        "code": "director_publish_error",
                        "message": str(exc),
                    },
                }
```

- [ ] **Step 6: Add tool group membership**

In `mcp_server/src/rook/agent/tool_groups.py`, add `rhino_director_publish_video` to `TOOL_GROUPS["director"]` next to `rhino_director_run` and `rhino_director_assemble_video`.

Do not add it to `director_readonly`.

- [ ] **Step 7: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected:

```text
all Director MCP tests pass
```

- [ ] **Step 8: Commit MCP wiring**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat: expose Director video publish MCP tool"
```

---

## Task 4: Add Managed Publisher Unit Tests

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs`
- Create later: `src/Rook/Services/Vision/Director/DirectorVideoPublisher.cs`
- Create later: `src/Rook/Services/Vision/Director/DirectorVideoPublishModels.cs`

- [ ] **Step 1: Create managed test file with fixtures**

Create `src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Vision.Director;
using Xunit;

namespace Rook.Tests.Services.Vision.Director
{
    public sealed class DirectorVideoPublisherTests : IDisposable
    {
        private readonly string _root;
        private readonly string _directorRoot;
        private readonly ArtifactStore _store;

        public DirectorVideoPublisherTests()
        {
            _root = Path.Combine(Path.GetTempPath(), "rook-director-publish-" + Guid.NewGuid().ToString("N"));
            _directorRoot = Path.Combine(_root, "director");
            Directory.CreateDirectory(_directorRoot);
            _store = new ArtifactStore(Path.Combine(_root, "artifacts"));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                try { Directory.Delete(_root, recursive: true); }
                catch { }
            }
        }

        private string WriteStandardRun(
            string runId = "run-a",
            int width = 1280,
            int height = 720,
            int fps = 24,
            int frameCount = 96,
            byte[]? bytes = null)
        {
            var runRoot = Path.Combine(_directorRoot, runId);
            Directory.CreateDirectory(Path.Combine(runRoot, "videos"));
            File.WriteAllBytes(Path.Combine(runRoot, "videos", "preview.mp4"), bytes ?? Encoding.ASCII.GetBytes("fake-mp4"));
            File.WriteAllText(
                Path.Combine(runRoot, "manifest.json"),
                JsonSerializer.Serialize(new
                {
                    schema_version = 1,
                    director_version = "slice1",
                    run_id = runId,
                    frame_count = frameCount,
                    resolution = new { width, height },
                    timeline = new { fps, duration_seconds = (double)frameCount / fps, frame_count = frameCount },
                }));
            File.WriteAllText(
                Path.Combine(runRoot, "video_manifest.json"),
                JsonSerializer.Serialize(new
                {
                    schema_version = 1,
                    state = "complete",
                    run_id = runId,
                    format = "mp4",
                    container = "mp4",
                    codec = "h264",
                    fps,
                    frame_count = frameCount,
                    width,
                    height,
                    output_path = "videos/preview.mp4",
                    output_current = true,
                }));
            return runRoot;
        }

        private static string Sha256(string path)
        {
            using var stream = File.OpenRead(path);
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        private JsonObject BuildRequest(string runRoot, Guid? priorArtifactId = null)
        {
            var sourcePath = Path.Combine(runRoot, "videos", "preview.mp4");
            var videoManifestPath = Path.Combine(runRoot, "video_manifest.json");
            var frameManifestPath = Path.Combine(runRoot, "manifest.json");
            var request = new JsonObject
            {
                ["run_id"] = Path.GetFileName(runRoot),
                ["profile"] = "director_publish_standard_v1",
                ["preset"] = "hd_720",
                ["source"] = new JsonObject
                {
                    ["run_root"] = runRoot,
                    ["relative_path"] = "videos/preview.mp4",
                    ["absolute_path"] = sourcePath,
                    ["byte_size"] = new FileInfo(sourcePath).Length,
                    ["sha256"] = Sha256(sourcePath),
                },
                ["facts"] = new JsonObject
                {
                    ["container"] = "mp4",
                    ["format"] = "mp4",
                    ["codec"] = "h264",
                    ["width"] = 1280,
                    ["height"] = 720,
                    ["fps"] = 24,
                    ["frame_count"] = 96,
                },
                ["hashes"] = new JsonObject
                {
                    ["video_manifest_sha256"] = Sha256(videoManifestPath),
                    ["frame_manifest_sha256"] = Sha256(frameManifestPath),
                },
                ["metadata"] = new JsonObject
                {
                    ["director"] = new JsonObject
                    {
                        ["schema_version"] = 1,
                        ["run_id"] = Path.GetFileName(runRoot),
                        ["profile"] = "director_publish_standard_v1",
                        ["preset"] = "hd_720",
                        ["source_video"] = "videos/preview.mp4",
                        ["video_manifest_hash"] = Sha256(videoManifestPath),
                        ["frame_manifest_hash"] = Sha256(frameManifestPath),
                        ["camera_strategy"] = "curve_follow_target",
                        ["camera"] = new JsonObject
                        {
                            ["strategy"] = "curve_follow_target",
                            ["curve_id"] = "00000000-0000-0000-0000-000000000001",
                            ["target"] = new JsonArray(0.0, 0.0, 0.0),
                            ["up"] = new JsonArray(0.0, 0.0, 1.0),
                            ["sampling"] = new JsonObject
                            {
                                ["mode"] = "normalized_parameter",
                                ["start"] = 0.0,
                                ["end"] = 1.0,
                            },
                        },
                        ["timeline"] = new JsonObject
                        {
                            ["fps"] = 24,
                            ["duration_seconds"] = 4.0,
                            ["frame_count"] = 96,
                        },
                        ["resolution"] = new JsonObject
                        {
                            ["width"] = 1280,
                            ["height"] = 720,
                        },
                    },
                },
            };
            if (priorArtifactId.HasValue)
                request["prior_artifact_id"] = priorArtifactId.Value.ToString("D");
            return request;
        }
    }
}
```

- [ ] **Step 2: Add success creation test**

Inside the class, add:

```csharp
[Fact]
public void Publish_CreatesGeneratedVideoWithOnlyVideoBlob()
{
    var runRoot = WriteStandardRun();
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(BuildRequest(runRoot));

    Assert.True(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    var artifactId = Guid.Parse(data["artifact_id"]!.GetValue<string>());
    var artifact = _store.Get(artifactId);
    Assert.NotNull(artifact);
    Assert.Equal("generated_video", artifact!.Kind);
    Assert.Single(artifact.Files);
    Assert.Equal("video", artifact.Files[0].Role);
    Assert.Equal("video.mp4", artifact.Files[0].Path);
    Assert.True(File.Exists(_store.GetBlobAbsolutePath(artifactId, "video")));
    Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(artifactId, "poster"));
    Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(artifactId, "start_frame"));
    Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(artifactId, "end_frame"));
    Assert.Equal("director_publish_standard_v1", artifact.Metadata["director"]!["profile"]!.GetValue<string>());
    Assert.Equal("hd_720", artifact.Metadata["director"]!["preset"]!.GetValue<string>());
}
```

- [ ] **Step 3: Add safety rejection tests**

Add:

```csharp
[Fact]
public void Publish_RejectsSourceOutsideDirectorRoot()
{
    var outside = Path.Combine(_root, "outside", "run-a");
    Directory.CreateDirectory(Path.Combine(outside, "videos"));
    File.WriteAllBytes(Path.Combine(outside, "videos", "preview.mp4"), Encoding.ASCII.GetBytes("fake-mp4"));
    var request = BuildRequest(WriteStandardRun());
    request["source"]!["run_root"] = outside;
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("artifact_boundary_mismatch", data["code"]!.GetValue<string>());
    Assert.Equal("source_path_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsNonPreviewRelativePath()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["source"]!["relative_path"] = "videos/other.mp4";
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("source_path_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsAdvisoryAbsolutePathMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["source"]!["absolute_path"] = Path.Combine(_root, "not-preview.mp4");
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("source_path_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsSourceHashMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["source"]!["sha256"] = new string('0', 64);
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("source_hash_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsSourceSizeMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["source"]!["byte_size"] = 999;
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("source_size_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsVideoManifestHashMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["hashes"]!["video_manifest_sha256"] = new string('0', 64);
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsFrameManifestHashMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["hashes"]!["frame_manifest_sha256"] = new string('0', 64);
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsDirectorMetadataResolutionMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["metadata"]!["director"]!["resolution"]!["width"] = 1920;
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
}
```

- [ ] **Step 4: Add manifest and prior-artifact tests**

Add:

```csharp
[Fact]
public void Publish_RejectsManifestFactMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["facts"]!["width"] = 1920;
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_RejectsRunIdMismatch()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    request["run_id"] = "other-run";
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
}

[Fact]
public void Publish_ConfirmsPriorArtifactAndAllowsExtraMetadataFields()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot);
    var requestMetadata = Assert.IsType<JsonObject>(request["metadata"]);
    var sourcePath = Path.Combine(runRoot, "videos", "preview.mp4");
    var priorMetadata = new Dictionary<string, JsonNode?>
    {
        ["director"] = requestMetadata["director"]!.DeepClone(),
        ["extra_future_field"] = JsonValue.Create("allowed"),
    };
    var prior = _store.CreateFromFiles(
        "generated_video",
        new[]
        {
            new BlobFileInput(
                "video",
                sourcePath,
                "mp4",
                ExpectedBytes: new FileInfo(sourcePath).Length),
        },
        metadata: priorMetadata);
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(BuildRequest(runRoot, prior.Id));

    Assert.True(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal(prior.Id.ToString("D"), data["artifact_id"]!.GetValue<string>());
    Assert.True(data["confirmed_prior_artifact"]!.GetValue<bool>());
}

[Fact]
public void Publish_MissingPriorArtifactReturnsPublishedArtifactMissing()
{
    var runRoot = WriteStandardRun();
    var request = BuildRequest(runRoot, Guid.NewGuid());
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("published_artifact_missing", data["code"]!.GetValue<string>());
}

[Fact]
public void Publish_WrongPriorArtifactBlobHashReturnsMismatch()
{
    var runRoot = WriteStandardRun();
    var wrong = _store.Create("generated_video", new[] { new BlobInput("video", Encoding.ASCII.GetBytes("different"), "mp4") });
    var request = BuildRequest(runRoot, wrong.Id);
    var publisher = new DirectorVideoPublisher(_store, _directorRoot);

    var response = publisher.Publish(request);

    Assert.False(response.Success);
    var data = Assert.IsType<JsonObject>(response.Data);
    Assert.Equal("prior_artifact_mismatch", data["managed_subcode"]!.GetValue<string>());
}
```

- [ ] **Step 5: Run managed tests and verify compile failures**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~DirectorVideoPublisherTests
```

Expected:

```text
fails to compile because Rook.Services.Vision.Director.DirectorVideoPublisher is missing
```

Do not add route or native code in this task.

---

## Task 5: Implement Managed Director Video Publisher

**Files:**
- Create: `src/Rook/Services/Vision/Director/DirectorVideoPublishModels.cs`
- Create: `src/Rook/Services/Vision/Director/DirectorVideoPublisher.cs`
- Test: `src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs`

- [ ] **Step 1: Add model/helper file**

Create `src/Rook/Services/Vision/Director/DirectorVideoPublishModels.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook;

namespace Rook.Services.Vision.Director
{
    internal static class DirectorVideoPublishResponses
    {
        public static ApiResponse BoundaryMismatch(string subcode, string message)
            => new ApiResponse
            {
                Success = false,
                Data = new JsonObject
                {
                    ["code"] = "artifact_boundary_mismatch",
                    ["managed_subcode"] = subcode,
                    ["message"] = message,
                },
            };

        public static ApiResponse PublishedArtifactMissing(Guid id)
            => new ApiResponse
            {
                Success = false,
                Data = new JsonObject
                {
                    ["code"] = "published_artifact_missing",
                    ["message"] = $"Previously published artifact '{id:D}' no longer exists.",
                },
            };
    }
}
```

If `ApiResponse` lives in another namespace in this repo, use the existing namespace imported by `VisionHandler.cs`.

- [ ] **Step 2: Add publisher skeleton and parsing helpers**

Create `src/Rook/Services/Vision/Director/DirectorVideoPublisher.cs`:

```csharp
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook;
using Rook.Artifacts;

namespace Rook.Services.Vision.Director
{
    internal sealed class DirectorVideoPublisher
    {
        private const string ProfileName = "director_publish_standard_v1";
        private const string SourceRelativePath = "videos/preview.mp4";

        private readonly ArtifactStore _artifactStore;
        private readonly string _directorRoot;

        public DirectorVideoPublisher(ArtifactStore artifactStore, string? directorRoot = null)
        {
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _directorRoot = Canonicalize(directorRoot ?? ResolveDirectorOutputRoot());
        }

        public ApiResponse Publish(JsonObject request)
        {
            try
            {
                return PublishCore(request);
            }
            catch (ArgumentException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (InvalidDataException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (IOException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", ex.Message);
            }
        }

        private ApiResponse PublishCore(JsonObject request)
        {
            var runId = RequireString(request, "run_id");
            var profile = RequireString(request, "profile");
            var preset = RequireString(request, "preset");
            if (!string.Equals(profile, ProfileName, StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "profile mismatch.");

            var source = RequireObject(request, "source");
            var runRoot = Canonicalize(RequireString(source, "run_root"));
            var relativePath = RequireString(source, "relative_path");
            if (!string.Equals(relativePath, SourceRelativePath, StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "source relative_path must be videos/preview.mp4.");
            if (!IsRelativeTo(runRoot, _directorRoot))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "run_root must resolve under the configured Director output root.");

            var sourcePath = Canonicalize(Path.Combine(runRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
            if (!IsRelativeTo(sourcePath, runRoot) || !string.Equals(sourcePath, Canonicalize(Path.Combine(runRoot, "videos", "preview.mp4")), StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "source path must resolve to run_root/videos/preview.mp4.");

            if (source.TryGetPropertyValue("absolute_path", out var advisoryNode) && advisoryNode is not null)
            {
                var advisory = Canonicalize(advisoryNode.GetValue<string>());
                if (!string.Equals(advisory, sourcePath, StringComparison.OrdinalIgnoreCase))
                    return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "advisory absolute_path does not match recomputed source path.");
            }

            if (!File.Exists(sourcePath))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "source video is missing.");

            var expectedSize = RequireLong(source, "byte_size");
            var actualSize = new FileInfo(sourcePath).Length;
            if (actualSize != expectedSize)
                return DirectorVideoPublishResponses.BoundaryMismatch("source_size_mismatch", "source video byte size mismatch.");

            var expectedHash = RequireString(source, "sha256");
            var actualHash = Sha256(sourcePath);
            if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_hash_mismatch", "source video hash mismatch.");

            var manifestCheck = ValidateManifests(runRoot, request, runId);
            if (!manifestCheck.Success) return manifestCheck;

            var requestContractCheck = ValidateRequestHashesAndMetadata(runRoot, request, runId);
            if (!requestContractCheck.Success) return requestContractCheck;

            if (request.TryGetPropertyValue("prior_artifact_id", out var priorNode) && priorNode is not null)
            {
                if (!Guid.TryParse(priorNode.GetValue<string>(), out var priorId))
                    return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior_artifact_id must be a GUID.");
                return ConfirmPriorArtifact(priorId, request, expectedHash, expectedSize);
            }

            var metadata = RequireObject(request, "metadata").DeepClone().AsObject();
            var artifact = _artifactStore.CreateFromFiles(
                "generated_video",
                new[] { new BlobFileInput("video", sourcePath, "mp4", ExpectedBytes: expectedSize) },
                metadata: metadata.ToDictionary(kvp => kvp.Key, kvp => kvp.Value?.DeepClone()));

            return new ApiResponse
            {
                Success = true,
                Data = new JsonObject
                {
                    ["artifact_id"] = artifact.Id.ToString("D"),
                    ["kind"] = artifact.Kind,
                    ["confirmed_prior_artifact"] = false,
                    ["files"] = new JsonArray(
                        artifact.Files.Select(f => new JsonObject
                        {
                            ["role"] = f.Role,
                            ["path"] = f.Path,
                        }).ToArray<JsonNode?>()),
                },
            };
        }
```

Keep appending in the same file in the next step.

- [ ] **Step 3: Add manifest validation and prior confirmation helpers**

Append before the closing class brace:

```csharp
        private ApiResponse ValidateManifests(string runRoot, JsonObject request, string runId)
        {
            var manifestPath = Path.Combine(runRoot, "manifest.json");
            var videoManifestPath = Path.Combine(runRoot, "video_manifest.json");
            var manifest = JsonNode.Parse(File.ReadAllText(manifestPath))!.AsObject();
            var videoManifest = JsonNode.Parse(File.ReadAllText(videoManifestPath))!.AsObject();
            if (!string.Equals(manifest["run_id"]?.GetValue<string>(), runId, StringComparison.Ordinal)
                || !string.Equals(videoManifest["run_id"]?.GetValue<string>(), runId, StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "run_id does not match manifests.");
            if (!string.Equals(videoManifest["state"]?.GetValue<string>(), "complete", StringComparison.Ordinal)
                || videoManifest["output_current"]?.GetValue<bool>() != true)
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "video_manifest is not current and complete.");
            var facts = RequireObject(request, "facts");
            if (videoManifest["width"]?.GetValue<int>() != RequireInt(facts, "width")
                || videoManifest["height"]?.GetValue<int>() != RequireInt(facts, "height")
                || videoManifest["frame_count"]?.GetValue<int>() != RequireInt(facts, "frame_count")
                || videoManifest["fps"]?.GetValue<int>() != RequireInt(facts, "fps")
                || !string.Equals(videoManifest["format"]?.GetValue<string>(), RequireString(facts, "format"), StringComparison.Ordinal)
                || !string.Equals(videoManifest["container"]?.GetValue<string>(), RequireString(facts, "container"), StringComparison.Ordinal)
                || !string.Equals(videoManifest["codec"]?.GetValue<string>(), RequireString(facts, "codec"), StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "request facts do not match video_manifest.json.");
            return new ApiResponse { Success = true, Data = new JsonObject() };
        }

        private ApiResponse ValidateRequestHashesAndMetadata(string runRoot, JsonObject request, string runId)
        {
            var hashes = RequireObject(request, "hashes");
            var videoManifestHash = Sha256(Path.Combine(runRoot, "video_manifest.json"));
            var frameManifestHash = Sha256(Path.Combine(runRoot, "manifest.json"));
            if (!string.Equals(videoManifestHash, RequireString(hashes, "video_manifest_sha256"), StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "video_manifest hash does not match request.");
            if (!string.Equals(frameManifestHash, RequireString(hashes, "frame_manifest_sha256"), StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "frame manifest hash does not match request.");

            var facts = RequireObject(request, "facts");
            var director = RequireObject(RequireObject(request, "metadata"), "director");
            if (!string.Equals(director["run_id"]?.GetValue<string>(), runId, StringComparison.Ordinal)
                || !string.Equals(director["profile"]?.GetValue<string>(), ProfileName, StringComparison.Ordinal)
                || !string.Equals(director["preset"]?.GetValue<string>(), RequireString(request, "preset"), StringComparison.Ordinal)
                || !string.Equals(director["source_video"]?.GetValue<string>(), SourceRelativePath, StringComparison.Ordinal)
                || !string.Equals(director["video_manifest_hash"]?.GetValue<string>(), videoManifestHash, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(director["frame_manifest_hash"]?.GetValue<string>(), frameManifestHash, StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "metadata.director identity fields do not match request facts.");

            var resolution = RequireObject(director, "resolution");
            if (RequireInt(resolution, "width") != RequireInt(facts, "width")
                || RequireInt(resolution, "height") != RequireInt(facts, "height"))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "metadata.director resolution does not match request facts.");
            var timeline = RequireObject(director, "timeline");
            if (RequireInt(timeline, "fps") != RequireInt(facts, "fps")
                || RequireInt(timeline, "frame_count") != RequireInt(facts, "frame_count"))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "metadata.director timeline does not match request facts.");
            return new ApiResponse { Success = true, Data = new JsonObject() };
        }

        private ApiResponse ConfirmPriorArtifact(Guid artifactId, JsonObject request, string expectedHash, long expectedSize)
        {
            var artifact = _artifactStore.Get(artifactId);
            if (artifact is null)
                return DirectorVideoPublishResponses.PublishedArtifactMissing(artifactId);
            if (!string.Equals(artifact.Kind, "generated_video", StringComparison.Ordinal)
                || artifact.Files.Count != 1
                || artifact.Files[0].Role != "video")
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact is not generated_video/video.");
            var blobPath = _artifactStore.GetBlobAbsolutePath(artifactId, "video");
            if (new FileInfo(blobPath).Length != expectedSize)
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact video size mismatch.");
            if (!string.Equals(Sha256(blobPath), expectedHash, StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact video hash mismatch.");
            var requestDirector = RequireObject(RequireObject(request, "metadata"), "director");
            var artifactDirectorNode = artifact.Metadata.TryGetValue("director", out var node) ? node : null;
            if (artifactDirectorNode is not JsonObject artifactDirector)
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact lacks director metadata.");
            foreach (var field in new[] { "run_id", "profile", "preset", "source_video", "video_manifest_hash", "frame_manifest_hash", "camera_strategy" })
            {
                if (!JsonNode.DeepEquals(requestDirector[field], artifactDirector[field]))
                    return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", $"prior artifact director.{field} mismatch.");
            }
            return new ApiResponse
            {
                Success = true,
                Data = new JsonObject
                {
                    ["artifact_id"] = artifact.Id.ToString("D"),
                    ["kind"] = artifact.Kind,
                    ["confirmed_prior_artifact"] = true,
                    ["files"] = new JsonArray(new JsonObject
                    {
                        ["role"] = "video",
                        ["path"] = artifact.Files[0].Path,
                    }),
                },
            };
        }
```

- [ ] **Step 4: Add scalar/path helpers and close class**

Append before the class/namespace closing braces:

```csharp
        private static string ResolveDirectorOutputRoot()
        {
            var configured = Environment.GetEnvironmentVariable("ROOK_DIRECTOR_OUTPUT_ROOT");
            if (!string.IsNullOrWhiteSpace(configured))
                return configured;
            var localAppData = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (string.IsNullOrWhiteSpace(localAppData))
                throw new InvalidOperationException("LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set.");
            return Path.Combine(localAppData, "Rook", "rookvision_director");
        }

        private static string Canonicalize(string path)
            => Path.GetFullPath(path);

        private static bool IsRelativeTo(string path, string root)
        {
            var relative = Path.GetRelativePath(root, path);
            return relative != "."
                && !relative.StartsWith("..", StringComparison.Ordinal)
                && !Path.IsPathRooted(relative);
        }

        private static JsonObject RequireObject(JsonObject obj, string name)
            => obj[name] as JsonObject ?? throw new ArgumentException($"{name} must be an object.");

        private static string RequireString(JsonObject obj, string name)
            => obj[name]?.GetValue<string>() ?? throw new ArgumentException($"{name} must be a string.");

        private static int RequireInt(JsonObject obj, string name)
            => obj[name]?.GetValue<int>() ?? throw new ArgumentException($"{name} must be an integer.");

        private static long RequireLong(JsonObject obj, string name)
            => obj[name]?.GetValue<long>() ?? throw new ArgumentException($"{name} must be an integer.");

        private static string Sha256(string path)
        {
            using var stream = File.OpenRead(path);
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
    }
}
```

- [ ] **Step 5: Run managed publisher tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~DirectorVideoPublisherTests
```

Expected:

```text
DirectorVideoPublisherTests pass
```

`ArtifactStore.Get(Guid)` exists in `src/Rook/Artifacts/ArtifactStore.cs` and returns `Artifact?`; missing artifacts should flow to `PublishedArtifactMissing(...)`, not a caught exception path.

- [ ] **Step 6: Commit managed publisher**

Run:

```powershell
git add src/Rook/Services/Vision/Director/DirectorVideoPublishModels.cs src/Rook/Services/Vision/Director/DirectorVideoPublisher.cs src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs
git commit -m "feat: add managed Director video publisher"
```

---

## Task 6: Wire Managed Vision Dispatch

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Test: `src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs`

- [ ] **Step 1: Add failing handler dispatch/source tests**

In `src/Rook.Tests/Handlers/VisionHandlerTests.cs`, add tests following the existing source-test or handler-test style:

```csharp
[Fact]
public void VisionHandler_DispatchOffUi_RoutesDirectorPublishVideo()
{
    var source = File.ReadAllText(Path.Combine(TestPaths.RepoRoot, "src", "Rook", "Handlers", "VisionHandler.cs"));

    Assert.Contains("\"publish_director_video\" => PublishDirectorVideo(args)", source);
    Assert.Contains("or \"publish_director_video\" => Fail(", source);
}
```

If this file does not use `TestPaths.RepoRoot`, use the helper already used in nearby source tests. The intent is to pin that `publish_director_video` is accepted by `DispatchOffUi` and rejected by sync/async dispatchers.

- [ ] **Step 2: Run focused handler tests and verify failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VisionHandler
```

Expected:

```text
new test fails because publish_director_video is not routed
```

- [ ] **Step 3: Import managed Director namespace**

In `src/Rook/Handlers/VisionHandler.cs`, add:

```csharp
using Rook.Services.Vision.Director;
```

- [ ] **Step 4: Route through off-UI dispatcher**

In `DispatchOffUi`, add:

```csharp
"publish_director_video" => PublishDirectorVideo(args),
```

In `Dispatch` and `DispatchAsync`, add `publish_director_video` to the off-UI rejection groups:

```csharp
or "publish_director_video" => Fail(
    $"op '{op}' must be routed through the off-UI dispatcher, not the sync UI-thread dispatcher.")
```

and:

```csharp
or "publish_director_video" => Fail(
    $"op '{op}' must be routed through the off-UI dispatcher, not the async dispatcher.")
```

Match the exact string style already used in those switch expressions.

- [ ] **Step 5: Add `PublishDirectorVideo` method**

Near artifact-management methods in `VisionHandler.cs`, add:

```csharp
internal ApiResponse PublishDirectorVideo(Dictionary<string, JsonElement> args)
{
    var json = new JsonObject();
    foreach (var kvp in args)
    {
        json[kvp.Key] = JsonNode.Parse(kvp.Value.GetRawText());
    }
    var publisher = new DirectorVideoPublisher(_artifactStore);
    return publisher.Publish(json);
}
```

- [ ] **Step 6: Run managed focused tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~DirectorVideoPublisherTests|FullyQualifiedName~VisionHandlerTests"
```

Expected:

```text
focused managed tests pass
```

- [ ] **Step 7: Commit managed dispatch**

Run:

```powershell
git add src/Rook/Handlers/VisionHandler.cs src/Rook.Tests/Handlers/VisionHandlerTests.cs
git commit -m "feat: route Director video publish through Vision handler"
```

---

## Task 7: Wire Native Bridge Allowlist

**Files:**
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
- Test: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

- [ ] **Step 1: Add bridge allowlist tests**

In `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`, add this test near the `ExpectedVisionOps` tests:

```csharp
[Fact]
public void ExpectedVisionOps_ContainsDirectorPublishVideo()
{
    Assert.Contains("publish_director_video", NativeGhBridgeRegistrar.ExpectedVisionOps);
}
```

Update the existing count test:

```csharp
[Fact]
public void ExpectedVisionOps_HasExactly16Ops()
{
    // Pinned count: 8 image + 1 Director publish + 5 V2 video + 2 V4 video list ops.
    // If this drifts, either a new op landed (update both the
    // count and the per-op test above) or one was removed
    // (intentional retirement).
    Assert.Equal(16, NativeGhBridgeRegistrar.ExpectedVisionOps.Count);
}
```

Add a source-level route pin in the same class:

```csharp
[Fact]
public void VisionDispatch_RoutesDirectorPublishVideoThroughOffUi()
{
    var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
    var caseIndex = source.IndexOf("case \"publish_director_video\":", StringComparison.Ordinal);
    Assert.True(caseIndex >= 0);
    var offUiIndex = source.IndexOf("reqJson => Vision.DispatchOffUi(reqJson)", caseIndex, StringComparison.Ordinal);
    Assert.True(offUiIndex > caseIndex);
}
```

Add this helper at the bottom of `NativeGhBridgeRegistrarTests` before the closing class brace:

```csharp
private static string FindRepoRoot()
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir is not null)
    {
        if (File.Exists(Path.Combine(dir.FullName, "Rook.sln")))
            return dir.FullName;
        dir = dir.Parent;
    }
    throw new DirectoryNotFoundException("Could not locate Rook.sln from test output directory.");
}
```

- [ ] **Step 2: Run bridge tests and verify failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeGhBridgeRegistrarTests
```

Expected:

```text
new bridge tests fail because publish_director_video is not allowlisted or routed
```

- [ ] **Step 3: Add Director publish to expected Vision ops**

In `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`, add this value to `ExpectedVisionOps` after `consume_approved` and before the V2 video block:

```csharp
// Director publish
"publish_director_video",
```

- [ ] **Step 4: Route Director publish through the off-UI Vision dispatcher**

In the `switch (op)` inside `VisionDispatch`, add the case to the existing artifact-management off-UI group:

```csharp
case "list_artifacts":
case "get_artifact":
case "approve_artifact":
case "delete_artifact":
case "consume_approved":
case "publish_director_video":
    // Off-UI sync path — disk-only artifact-store ops and Director
    // publish boundary checks. Native remains transport-only; Python
    // owns Director profile semantics and managed owns ArtifactStore
    // safety.
    return ExecuteOffUiApiResponseCallback(
        responseJsonUtf8,
        responseJsonCapacity,
        responseJsonLength,
        httpStatusCode,
        requestJson,
        reqJson => Vision.DispatchOffUi(reqJson),
        timeoutSeconds: 30);
```

Keep the existing arguments and formatting in that return call; the required change is adding `case "publish_director_video":` to the `Vision.DispatchOffUi` arm, not creating a new dispatcher path.

- [ ] **Step 5: Run bridge tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeGhBridgeRegistrarTests
```

Expected:

```text
NativeGhBridgeRegistrarTests pass
```

- [ ] **Step 6: Commit bridge route wiring**

Run:

```powershell
git add src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs
git commit -m "feat: allow Director video publish through vision bridge"
```

---

## Task 8: Add Native Thin Vision Proxy Route

**Files:**
- Modify: `src/RookNative/Handlers/VisionHandler.h`
- Modify: `src/RookNative/Handlers/VisionHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `mcp_server/tests/test_director_native_source.py` or existing native source test

- [ ] **Step 1: Add source-level native proxy tests**

In `mcp_server/tests/test_director_native_source.py`, add:

```python
def test_director_publish_video_native_route_is_thin_vision_proxy():
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")
    header_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "VisionHandler.h").read_text(encoding="utf-8")
    handler_source = (REPO_ROOT / "src" / "RookNative" / "Handlers" / "VisionHandler.cpp").read_text(encoding="utf-8")

    assert 'm_server->Post("/vision/director/publish-video"' in server_source
    assert "HandleVisionDirectorPublishVideo" in header_source
    assert "void HandleVisionDirectorPublishVideo" in handler_source
    assert 'DispatchVisionOp(req, res, "publish_director_video")' in handler_source
    assert 'DirectorVideoPublisher' not in handler_source
    assert 'ArtifactStore' not in handler_source
    assert 'director_publish_standard_v1' not in handler_source
```

- [ ] **Step 2: Run source test and verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected:

```text
fails because the native route/proxy handler is not wired
```

- [ ] **Step 3: Declare native handler**

In `src/RookNative/Handlers/VisionHandler.h`, add near artifact routes:

```cpp
// POST /vision/director/publish-video — Thin proxy to managed
// publish_director_video. Native owns transport only; Python owns
// Director publish validation and managed owns ArtifactStore safety.
void HandleVisionDirectorPublishVideo(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 4: Implement thin native handler**

In `src/RookNative/Handlers/VisionHandler.cpp`, add:

```cpp
void HandleVisionDirectorPublishVideo(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "publish_director_video");
}
```

Do not add Director root validation, artifact code, profile logic, file I/O, or sidecar logic in native.

- [ ] **Step 5: Register native route**

In `src/RookNative/RookServer.cpp`, register before generic `/vision/artifacts/...` routes and near the other Vision routes:

```cpp
m_server->Post("/vision/director/publish-video", [](const httplib::Request& req, httplib::Response& res) {
    Rook::Handlers::HandleVisionDirectorPublishVideo(req, res);
});
```

- [ ] **Step 6: Run source test**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected:

```text
source-level route/proxy tests pass
```

- [ ] **Step 7: Build native if toolchain is available**

Run:

```cmd
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected:

```text
Build succeeds with 0 errors
```

If Rhino SDK or MFC toolchain is unavailable, record the exact error and do not claim native build verification.

- [ ] **Step 8: Commit native proxy route**

Run:

```powershell
git add src/RookNative/Handlers/VisionHandler.h src/RookNative/Handlers/VisionHandler.cpp src/RookNative/RookServer.cpp mcp_server/tests/test_director_native_source.py
git commit -m "feat: proxy Director video publish route"
```

---

## Task 9: Add Live Smoke Coverage

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add guarded live smoke**

Append a guarded test that reuses existing Director fixture helpers from `test_director_routes_live.py`. Use the existing curve-follow fixture path if available.

```python
@pytest.mark.asyncio
async def test_director_publish_video_live_smoke(requires_rhino):
    # Use an existing standard-profile Director run if the previous
    # curve-follow video smoke created one; otherwise skip cleanly.
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        pytest.skip("LOCALAPPDATA is not available")
    director_root = Path(local_app_data) / "Rook" / "rookvision_director"
    candidates = sorted(
        [
            path
            for path in director_root.glob("*")
            if (path / "manifest.json").exists()
            and (path / "video_manifest.json").exists()
            and (path / "videos" / "preview.mp4").exists()
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        pytest.skip("No completed Director video run is available for publish smoke")

    result = await server.call_tool(
        "rhino_director_publish_video",
        {"run_root": str(candidates[0])},
    )
    payload = json.loads(result[0].text)
    if payload.get("state") == "failed" and payload.get("error", {}).get("code") == "unsupported_video_profile":
        pytest.skip("Latest Director video run is not in director_publish_standard_v1")
    assert payload["state"] == "complete"
    artifact_id = payload["artifact_id"]

    artifact_result = await server.call_tool(
        "rhino_vision_get_artifact",
        {"artifact_id": artifact_id},
    )
    artifact_payload = json.loads(artifact_result[0].text)
    artifact = artifact_payload["artifact"]
    assert artifact["kind"] == "generated_video"
    files = artifact["files"]
    assert any(file["role"] == "video" and file["path"] == "video.mp4" for file in files)
```

Add the import used by the smoke helper:

```python
from rook import server
```

- [ ] **Step 2: Run live smoke when Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_director_routes_live.py -q
```

Expected:

```text
new smoke passes or skips for absent standard-profile run/Rhino
```

Do not claim live verification if the test skips.

- [ ] **Step 3: Commit live smoke**

Run:

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test: add Director video publish live smoke"
```

---

## Task 10: Final Verification

**Files:**
- Modify only files touched above if verification exposes defects.

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_publish.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_native_source.py -q
```

Expected:

```text
all selected Python tests pass
```

- [ ] **Step 2: Run focused managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~DirectorVideoPublisherTests|FullyQualifiedName~VisionHandlerTests"
```

Expected:

```text
focused managed tests pass
```

- [ ] **Step 3: Run bridge managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeGhBridgeRegistrarTests
```

Expected:

```text
NativeGhBridgeRegistrarTests pass
```

- [ ] **Step 4: Run native build if available**

Run:

```cmd
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected:

```text
Build succeeds with 0 errors
```

If unavailable, record the exact missing-toolchain error.

- [ ] **Step 5: Run guarded live smoke if Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_director_routes_live.py -q
```

Expected:

```text
passes or skips cleanly
```

- [ ] **Step 6: Run diff hygiene**

Run:

```powershell
git diff --check
```

Expected:

```text
no whitespace errors
```

- [ ] **Step 7: Check scope**

Run:

```powershell
git diff --name-only HEAD~9..HEAD
```

Expected changed files are limited to:

```text
mcp_server/src/rook/director_publish.py
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_groups.py
mcp_server/tests/test_director_publish.py
mcp_server/tests/test_director_mcp_tools.py
mcp_server/tests/test_director_native_source.py
mcp_server/tests/test_director_routes_live.py
src/Rook/Services/Vision/Director/DirectorVideoPublishModels.cs
src/Rook/Services/Vision/Director/DirectorVideoPublisher.cs
src/Rook/Handlers/VisionHandler.cs
src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs
src/Rook.Tests/Services/Vision/Director/DirectorVideoPublisherTests.cs
src/Rook.Tests/Handlers/VisionHandlerTests.cs
src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs
src/RookNative/Handlers/VisionHandler.h
src/RookNative/Handlers/VisionHandler.cpp
src/RookNative/RookServer.cpp
```

If `src/RookNative/Handlers/DirectorHandler.cpp`, `mcp_server/src/rook/director.py`, `mcp_server/src/rook/director_video.py`, Vision UI files, `.vcxproj`, or `.filters` changed, stop and re-check scope before proceeding.

## Review Checklist

- `rhino_director_publish_video` is explicit and idempotent.
- Python owns `director_publish_standard_v1` and publish manifest semantics.
- Managed uses `ROOK_DIRECTOR_OUTPUT_ROOT` or `%LOCALAPPDATA%/Rook/rookvision_director`, not artifact roots.
- Python rejects stale `output_current == false`.
- Python rejects `manifest.json` / `video_manifest.json` mismatches before metadata construction.
- Managed treats `absolute_path` as advisory only.
- Managed recomputes and contains source path under the Director output root.
- Managed rejects non-`videos/preview.mp4`.
- Managed verifies source hash and byte size.
- Managed verifies `hashes.video_manifest_sha256`, `hashes.frame_manifest_sha256`, and first-publish `metadata.director` contract fields before creating the artifact.
- Managed prior-artifact confirmation hashes and byte-counts the existing `video` blob.
- Managed compares contract metadata fields only, not byte-for-byte metadata JSON equality.
- Created artifacts are exactly `generated_video` with one `video.mp4` blob.
- No `poster`, `start_frame`, or `end_frame` sidecars are created by publish.
- `NativeGhBridgeRegistrar` allowlists `publish_director_video` and routes it through `Vision.DispatchOffUi`.
- Native route is only a Vision proxy and contains no Director publish logic.
- No transcoding, resizing, FPS conversion, Gallery UI, or authoring preset changes are included.
