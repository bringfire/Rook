from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rook import director_publish


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    _write_json(
        run_root / "status.json",
        {"state": overrides.get("state", "complete"), "run_id": "run-a"},
    )
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
    assert director_meta["camera"]["curve_id"] == (
        "00000000-0000-0000-0000-000000000001"
    )
    assert "run_root" not in director_meta

    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["state"] == "complete"
    assert publish_manifest["artifact_id"] == result["artifact_id"]
    assert publish_manifest["preset"] == "hd_720"
    assert publish_manifest["sidecar_policy"] == "existing_generated_video_pipeline"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"state": "failed"}, "run_not_complete"),
        ({"video_state": "failed"}, "video_not_assembled"),
        ({"output_current": False}, "video_not_current"),
    ],
)
async def test_publish_video_rejects_incomplete_or_stale_runs(
    tmp_path, overrides, code
):
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
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (
            {"width": 1024, "height": 768, "video_width": 1024, "video_height": 768},
            "unsupported_video_profile",
        ),
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
async def test_publish_video_rejects_frame_video_manifest_mismatch(
    tmp_path, overrides
):
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


@pytest.mark.asyncio
async def test_publish_video_rejects_source_symlink_escape(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside-video")
    source_path = run_root / "videos" / "preview.mp4"
    source_path.unlink()
    try:
        source_path.symlink_to(outside)
    except OSError as ex:
        pytest.skip(f"symlink creation is unavailable: {ex}")
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "source_path_invalid"
    assert managed.calls == []
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["error"]["code"] == "source_path_invalid"


@pytest.mark.asyncio
async def test_publish_video_sends_validated_absolute_source_path(
    tmp_path, monkeypatch
):
    run_root = _write_standard_run(tmp_path / "director")
    expected_source_path = (run_root / "videos" / "preview.mp4").resolve()
    escaped_path = (tmp_path / "escaped.mp4").resolve()
    escaped_path.write_bytes(b"escaped-video")
    original_resolve = type(expected_source_path).resolve
    source_resolve_calls = 0

    def resolve_with_swap(self, *args, **kwargs):
        nonlocal source_resolve_calls
        resolved = original_resolve(self, *args, **kwargs)
        if resolved == expected_source_path:
            source_resolve_calls += 1
            if source_resolve_calls >= 2:
                return escaped_path
        return resolved

    monkeypatch.setattr(type(expected_source_path), "resolve", resolve_with_swap)
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "complete"
    assert managed.calls[0][2]["source"]["absolute_path"] == str(expected_source_path)
    assert managed.calls[0][2]["source"]["absolute_path"] != str(escaped_path)


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
        "source_sha256": _sha256_file(run_root / "videos" / "preview.mp4"),
        "source_byte_size": (run_root / "videos" / "preview.mp4").stat().st_size,
        "video_manifest_hash": _sha256_file(run_root / "video_manifest.json"),
        "frame_manifest_hash": _sha256_file(run_root / "manifest.json"),
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
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["prior_artifact_id"] == previous["artifact_id"]


@pytest.mark.asyncio
async def test_publish_video_changed_source_after_prior_success_fails(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    previous = {
        "schema_version": 1,
        "state": "complete",
        "artifact_id": "00000000-0000-0000-0000-000000000099",
        "profile": "director_publish_standard_v1",
        "preset": "hd_720",
        "source_video": "videos/preview.mp4",
        "source_sha256": "0" * 64,
        "source_byte_size": (run_root / "videos" / "preview.mp4").stat().st_size,
        "video_manifest_hash": _sha256_file(run_root / "video_manifest.json"),
        "frame_manifest_hash": _sha256_file(run_root / "manifest.json"),
        "sidecar_policy": "existing_generated_video_pipeline",
    }
    _write_json(run_root / "publish_manifest.json", previous)
    managed = FakeManagedPublish()

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "publish_facts_changed"
    assert managed.calls == []


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
            "source_sha256": _sha256_file(run_root / "videos" / "preview.mp4"),
            "source_byte_size": (run_root / "videos" / "preview.mp4").stat().st_size,
            "video_manifest_hash": _sha256_file(run_root / "video_manifest.json"),
            "frame_manifest_hash": _sha256_file(run_root / "manifest.json"),
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
async def test_publish_video_propagates_published_artifact_missing(tmp_path):
    run_root = _write_standard_run(tmp_path / "director")
    previous = {
        "schema_version": 1,
        "state": "complete",
        "artifact_id": "00000000-0000-0000-0000-000000000099",
        "profile": "director_publish_standard_v1",
        "preset": "hd_720",
        "source_video": "videos/preview.mp4",
        "source_sha256": _sha256_file(run_root / "videos" / "preview.mp4"),
        "source_byte_size": (run_root / "videos" / "preview.mp4").stat().st_size,
        "video_manifest_hash": _sha256_file(run_root / "video_manifest.json"),
        "frame_manifest_hash": _sha256_file(run_root / "manifest.json"),
        "sidecar_policy": "existing_generated_video_pipeline",
    }
    _write_json(run_root / "publish_manifest.json", previous)
    managed = FakeManagedPublish(
        {
            "success": False,
            "data": {
                "code": "published_artifact_missing",
                "message": "Prior published artifact no longer exists.",
            },
        }
    )

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "published_artifact_missing"
    assert managed.calls[0][2]["prior_artifact_id"] == previous["artifact_id"]
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["error"]["code"] == "published_artifact_missing"


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
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["error"]["managed_subcode"] == "source_hash_mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize("artifact_id", [None, "", "not-a-guid"])
async def test_publish_video_rejects_managed_success_without_valid_artifact_id(
    tmp_path, artifact_id
):
    run_root = _write_standard_run(tmp_path / "director")
    managed = FakeManagedPublish({"success": True, "data": {"artifact_id": artifact_id}})

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "managed_publish_rejected"
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["state"] == "failed"
    assert publish_manifest["artifact_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("success_value", ["false", 1, None])
async def test_publish_video_rejects_malformed_managed_success_flag(
    tmp_path, success_value
):
    run_root = _write_standard_run(tmp_path / "director")
    managed = FakeManagedPublish(
        {
            "success": success_value,
            "data": {"artifact_id": "00000000-0000-0000-0000-000000000099"},
        }
    )

    result = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        call_managed=managed,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "managed_publish_rejected"
    publish_manifest = json.loads(
        (run_root / "publish_manifest.json").read_text(encoding="utf-8")
    )
    assert publish_manifest["state"] == "failed"
    assert publish_manifest["artifact_id"] is None
