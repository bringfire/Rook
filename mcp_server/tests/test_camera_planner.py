from __future__ import annotations

import pytest

from rook import camera_planner


def _camera(**overrides):
    data = {
        "projection": "perspective",
        "location": [0.0, 0.0, 10.0],
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 1.0, 0.0],
        "lens_length": 35.0,
        "fov_degrees": 37.8493,
        "parallel_scale": None,
        "near_clip": 0.1,
        "far_clip": 1000.0,
        "aspect": 0.75,
    }
    data.update(overrides)
    return data


class FakeNative:
    def __init__(self, cameras):
        self.cameras = list(cameras)
        self.calls = []

    async def __call__(self, endpoint, method, data, *, port=None):
        self.calls.append((endpoint, method, data, port))
        if endpoint != "/director/view-state":
            return {"success": False, "data": {"code": "unexpected_endpoint"}}
        if not self.cameras:
            return {"success": False, "data": {"code": "no_camera"}}
        index = len(self.calls)
        return {
            "success": True,
            "data": {
                "camera": self.cameras.pop(0),
                "provenance": {
                    "source": data["source"]["kind"],
                    "call_index": index,
                },
            },
        }


@pytest.mark.asyncio
async def test_legacy_camera_keyframes_resolve_to_keyframes_strategy():
    native = FakeNative([_camera()])
    result = await camera_planner.resolve_camera_plan(
        {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
        frame_count=3,
        resolution={"width": 1920, "height": 1080},
        call_native=native,
        port=12345,
    )

    assert result["strategy"] == "keyframes"
    assert result["provenance"]["request_shape"] == "legacy_camera_keyframes"
    assert result["provenance"]["aspect_authority"] == "output_resolution"
    assert result["provenance"]["optics_authority"] == "lens_length"
    assert len(result["frames"]) == 3
    assert result["frames"][0]["location"] == [0.0, 0.0, 10.0]
    assert result["frames"][0]["aspect"] == pytest.approx(1920 / 1080)
    assert native.calls[0] == (
        "/director/view-state",
        "POST",
        {"source": {"kind": "active_view"}},
        12345,
    )


@pytest.mark.asyncio
async def test_explicit_keyframes_strategy_matches_legacy_output_frames():
    keyframes = [{"frame_index": 1, "source": {"kind": "active_view"}}]
    legacy_native = FakeNative([_camera()])
    explicit_native = FakeNative([_camera()])

    legacy = await camera_planner.resolve_camera_plan(
        {"camera_keyframes": keyframes},
        frame_count=2,
        resolution={"width": 1280, "height": 720},
        call_native=legacy_native,
        port=None,
    )
    explicit = await camera_planner.resolve_camera_plan(
        {"camera": {"strategy": "keyframes", "keyframes": keyframes}},
        frame_count=2,
        resolution={"width": 1280, "height": 720},
        call_native=explicit_native,
        port=None,
    )

    assert explicit["provenance"]["request_shape"] == "camera_strategy"
    assert explicit["frames"] == legacy["frames"]


@pytest.mark.asyncio
async def test_explicit_camera_keyframe_bypasses_view_state_resolution():
    camera = _camera(
        lens_length="35.0",
        fov_degrees="45.0",
        near_clip="0.1",
        far_clip="1000.0",
    )
    native = FakeNative([])

    result = await camera_planner.resolve_camera_plan(
        {
            "camera_keyframes": [
                {
                    "frame_index": 1,
                    "source": {"kind": "explicit_camera", "camera": camera},
                }
            ]
        },
        frame_count=2,
        resolution={"width": 320, "height": 180},
        call_native=native,
        port=12345,
    )

    assert native.calls == []
    assert result["provenance"]["request_shape"] == "legacy_camera_keyframes"
    keyframe = result["provenance"]["keyframes"][0]
    assert keyframe["frame_index"] == 1
    assert keyframe["source"]["kind"] == "explicit_camera"
    assert keyframe["source"]["camera"]["lens_length"] == 35.0
    assert keyframe["source"]["camera"]["fov_degrees"] == 45.0
    assert keyframe["provenance"] == {"source": "explicit_camera"}
    frame_camera = result["frames"][0]
    assert frame_camera["lens_length"] == 35.0
    assert frame_camera["fov_degrees"] == 45.0
    assert frame_camera["near_clip"] == 0.1
    assert frame_camera["far_clip"] == 1000.0
    assert frame_camera["aspect"] == pytest.approx(320 / 180)


@pytest.mark.asyncio
async def test_keyframes_interpolate_location_target_up_and_optics():
    native = FakeNative(
        [
            _camera(
                location=[0.0, 0.0, 10.0],
                target=[0.0, 0.0, 0.0],
                up=[0.0, 1.0, 0.0],
                lens_length=35.0,
                fov_degrees=40.0,
            ),
            _camera(
                location=[10.0, 0.0, 10.0],
                target=[0.0, 10.0, 0.0],
                up=[0.0, 1.0, 0.0],
                lens_length=55.0,
                fov_degrees=20.0,
            ),
        ]
    )

    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"frame_index": 1, "source": {"kind": "named_view", "name": "A"}},
                    {"frame_index": 3, "source": {"kind": "named_view", "name": "B"}},
                ],
            }
        },
        frame_count=3,
        resolution={"width": 1000, "height": 500},
        call_native=native,
        port=None,
    )

    middle = result["frames"][1]
    assert middle["location"] == [5.0, 0.0, 10.0]
    assert middle["target"] == [0.0, 5.0, 0.0]
    assert middle["up"] == [0.0, 1.0, 0.0]
    assert middle["lens_length"] == pytest.approx(45.0)
    assert middle["fov_degrees"] is None
    assert middle["aspect"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_interpolated_degenerate_direction_is_rejected():
    native = FakeNative(
        [
            _camera(location=[0.0, 0.0, 0.0], target=[10.0, 0.0, 0.0]),
            _camera(location=[10.0, 0.0, 0.0], target=[0.0, 0.0, 0.0]),
        ]
    )

    with pytest.raises(camera_planner.CameraPlanError, match="location and target"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "keyframes",
                    "keyframes": [
                        {"frame_index": 1, "source": {"kind": "named_view", "name": "A"}},
                        {"frame_index": 3, "source": {"kind": "named_view", "name": "B"}},
                    ],
                }
            },
            frame_count=3,
            resolution={"width": 1000, "height": 500},
            call_native=native,
            port=None,
        )


@pytest.mark.asyncio
async def test_unknown_camera_strategy_is_rejected():
    with pytest.raises(camera_planner.CameraPlanError, match="camera.strategy"):
        await camera_planner.resolve_camera_plan(
            {"camera": {"strategy": "curve_follow_target"}},
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeNative([]),
            port=None,
        )


@pytest.mark.asyncio
async def test_parallel_camera_is_rejected():
    native = FakeNative([_camera(projection="parallel")])

    with pytest.raises(camera_planner.CameraPlanError, match="parallel"):
        await camera_planner.resolve_camera_plan(
            {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )


@pytest.mark.asyncio
async def test_perspective_camera_requires_lens_or_fov():
    native = FakeNative([_camera(lens_length=None, fov_degrees=None)])

    with pytest.raises(camera_planner.CameraPlanError, match="lens_length or fov_degrees"):
        await camera_planner.resolve_camera_plan(
            {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )


@pytest.mark.asyncio
async def test_perspective_camera_rejects_nonpositive_lens_and_invalid_fov():
    native = FakeNative([_camera(lens_length=-1.0, fov_degrees=180.0)])

    with pytest.raises(camera_planner.CameraPlanError, match="lens_length"):
        await camera_planner.resolve_camera_plan(
            {"camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=native,
            port=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("camera_overrides", "message"),
    [
        ({"lens_length": -1.0, "fov_degrees": 45.0}, "lens_length"),
        ({"lens_length": 35.0, "fov_degrees": 180.0}, "fov_degrees"),
    ],
)
async def test_explicit_camera_rejects_invalid_provided_optics(
    camera_overrides, message
):
    camera = _camera(**camera_overrides)

    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {
                "camera_keyframes": [
                    {
                        "frame_index": 1,
                        "source": {"kind": "explicit_camera", "camera": camera},
                    }
                ]
            },
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=FakeNative([]),
            port=None,
        )
