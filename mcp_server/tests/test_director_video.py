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
        "timeline": timeline
        or {
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
    assert native_request["output_path"].endswith(
        "videos\\preview.mp4"
    ) or native_request["output_path"].endswith("videos/preview.mp4")

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
async def test_assemble_video_failed_with_existing_preview_preserves_stale_output(
    tmp_path,
):
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
async def test_assemble_video_rejects_incomplete_frame_run_without_changing_status(
    tmp_path,
):
    run_root = _write_run(tmp_path / "director", state="failed")
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "frame_run_incomplete"
    assert (
        json.loads((run_root / "status.json").read_text(encoding="utf-8"))["state"]
        == "failed"
    )
    assert fake.calls == []


@pytest.mark.asyncio
async def test_assemble_video_missing_status_after_manifest_keeps_known_context(
    tmp_path,
):
    run_root = _write_run(tmp_path / "director", frame_count=3, width=640, height=360)
    (run_root / "status.json").unlink()
    fake = FakeNative()

    result = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        call_native=fake,
        director_output_root=tmp_path / "director",
    )

    assert result["state"] == "failed"
    assert result["error"]["code"] == "missing_run_metadata"
    manifest = json.loads((run_root / "video_manifest.json").read_text(encoding="utf-8"))
    assert manifest["output_path"] == "videos/preview.mp4"
    assert manifest["frame_count"] == 3
    assert manifest["width"] == 640
    assert manifest["height"] == 360
    assert manifest["fps"] == 24
    assert manifest["fps_source"] == "timeline"
    assert manifest["input_pattern"] == "frames/frame_%04d.png"
    assert "completed_at" in manifest
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
