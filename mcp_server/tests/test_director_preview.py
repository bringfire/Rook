from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director, director_compiler, director_preview


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


@pytest.mark.asyncio
async def test_preview_motion_preview_code_key_is_not_treated_as_validation_error():
    compiler = FakeCompiler(
        {
            "track": _track(frame_count=1, fps=24),
            "provenance": {"frame_count": 1, "fps": 24, "duration_ms": 41.6666666667},
        }
    )
    replay = FakeReplay({"status": "completed", "frames_played": 1, "restored": True})

    result = await director_preview.preview_motion(
        _spec(preview={"code": "note", "restore_on_finish": True}),
        compile_motion=compiler,
        run_replay=replay,
    )

    assert result["state"] == "completed"
    assert compiler.calls[0][0]["timeline"] == {"fps": 24, "frame_count": 2}
    assert replay.calls[0][0] == {
        "track": _track(frame_count=1, fps=24),
        "restore_on_finish": True,
    }


class ShouldNotCall:
    async def __call__(self, arguments: dict, *, port=None) -> dict:
        raise AssertionError("this dependency should not be called")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preview, expected_key, expected_value, code",
    [
        ({"loop": True}, "option", "loop", "unsupported_preview_option"),
        ({"include_track": "yes"}, "field", "include_track", "invalid_preview"),
        ({"restore_on_finish": "yes"}, "field", "restore_on_finish", "invalid_preview"),
        ({"fps": 0}, "field", "fps", "invalid_preview"),
        ({"fps": True}, "field", "fps", "invalid_preview"),
        ({"replay_session_id": 123}, "field", "replay_session_id", "invalid_preview"),
    ],
)
async def test_preview_motion_rejects_invalid_preview_controls_before_compile_or_replay(
    preview, expected_key, expected_value, code
):
    result = await director_preview.preview_motion(
        _spec(preview=preview),
        compile_motion=ShouldNotCall(),
        run_replay=ShouldNotCall(),
    )

    assert result["state"] == "compile_failed"
    assert result["compile"]["error"]["code"] == code
    assert result["compile"]["error"].get(expected_key) == expected_value
    assert result["replay"] is None


class FailingCompiler:
    def __init__(self):
        self.calls = 0

    async def __call__(self, arguments: dict, *, port=None) -> dict:
        self.calls += 1
        raise director_compiler.DirectorCompileError("unknown_group", "missing group", target="ghost")


class FailingReplay:
    async def __call__(self, arguments: dict, *, port=None) -> dict:
        raise director.DirectorError("replay_already_active: busy")


class RuntimeFailingReplay:
    async def __call__(self, arguments: dict, *, port=None) -> dict:
        raise RuntimeError("transport dropped")


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
async def test_preview_motion_generic_replay_exception_returns_structured_failure_with_context():
    compiler = FakeCompiler(
        {
            "track": _track(frame_count=2, fps=24),
            "provenance": {"frame_count": 2, "fps": 24, "duration_ms": 83.3333333333},
        }
    )

    result = await director_preview.preview_motion(
        _spec(),
        compile_motion=compiler,
        run_replay=RuntimeFailingReplay(),
    )

    assert result["state"] == "replay_failed"
    assert result["compile"] == {
        "provenance": {"frame_count": 2, "fps": 24, "duration_ms": 83.3333333333},
        "track_summary": {
            "frame_count": 2,
            "fps": 24,
            "duration_ms": 83.3333333333,
            "animated_object_ids": [U1],
            "camera_frame_count": 2,
            "object_frame_count": 2,
        },
    }
    assert result["replay"] == {
        "error": {
            "code": "replay_exception",
            "message": "transport dropped",
            "exception_type": "RuntimeError",
        }
    }
    assert result["next_edit_hooks"] == {
        "motion_targets": ["parts"],
        "animated_object_ids": [U1],
        "timeline": {"fps": 24, "frame_count": 2, "duration_ms": 83.3333333333},
        "preview_controls": ["restore_on_finish", "fps", "replay_session_id"],
    }


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
