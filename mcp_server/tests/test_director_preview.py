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
