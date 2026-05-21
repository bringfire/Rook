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


class FakeCurveNative(FakeNative):
    def __init__(self, *, samples=None, curve_response=None):
        super().__init__([])
        self.samples = samples or [
            {
                "frame_index": 1,
                "normalized_parameter": 0.0,
                "curve_parameter": 2.0,
                "point": [0.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
            {
                "frame_index": 2,
                "normalized_parameter": 0.5,
                "curve_parameter": 6.0,
                "point": [5.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
            {
                "frame_index": 3,
                "normalized_parameter": 1.0,
                "curve_parameter": 10.0,
                "point": [10.0, -10.0, 5.0],
                "tangent": [1.0, 0.0, 0.0],
            },
        ]
        self.curve_response = curve_response

    async def __call__(self, endpoint, method, data, *, port=None):
        if endpoint == "/director/curve-samples":
            self.calls.append((endpoint, method, data, port))
            if self.curve_response is not None:
                return self.curve_response
            return {
                "success": True,
                "data": {
                    "schema_version": 1,
                    "curve_id": data["curve_id"],
                    "frame_count": data["frame_count"],
                    "samples": self.samples,
                    "provenance": {
                        "sampling_mode": "normalized_parameter",
                        "parameter_mapping": "curve_domain_parameter_at",
                        "frame_count_source": "caller_canonical_frame_count",
                        "arc_length_sampled": False,
                        "validation_strength": "curve_parameter_sampled",
                    },
                },
            }
        return await super().__call__(endpoint, method, data, port=port)


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
async def test_curve_follow_target_samples_curve_and_emits_camera_frames():
    curve_id = "00000000-0000-0000-0000-000000000001"
    native = FakeCurveNative()

    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": curve_id,
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            }
        },
        frame_count=3,
        resolution={"width": 1280, "height": 720},
        call_native=native,
        port=12345,
    )

    assert result["strategy"] == "curve_follow_target"
    assert result["provenance"]["request_shape"] == "camera_strategy"
    assert result["provenance"]["curve_id"] == curve_id
    assert (
        result["provenance"]["curve_sampling"]["parameter_mapping"]
        == "curve_domain_parameter_at"
    )
    assert result["provenance"]["optics_authority"] == "lens_length"
    assert [frame["location"] for frame in result["frames"]] == [
        [0.0, -10.0, 5.0],
        [5.0, -10.0, 5.0],
        [10.0, -10.0, 5.0],
    ]
    assert all(frame["target"] == [0.0, 0.0, 0.0] for frame in result["frames"])
    assert all(frame["projection"] == "perspective" for frame in result["frames"])
    assert all(
        frame["aspect"] == pytest.approx(1280 / 720) for frame in result["frames"]
    )
    assert [call[0] for call in native.calls] == ["/director/curve-samples"]
    assert native.calls[0] == (
        "/director/curve-samples",
        "POST",
        {
            "curve_id": curve_id,
            "frame_count": 3,
            "sampling": {
                "mode": "normalized_parameter",
                "start": 0.0,
                "end": 1.0,
            },
        },
        12345,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("camera", "message"),
    [
        ({}, "curve_id"),
        ({"curve_id": "not-a-uuid"}, "curve_id"),
        ({"curve_id": "00000000-0000-0000-0000-000000000001"}, "target"),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [True, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            },
            "target",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 0.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            },
            "up",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, True],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            },
            "up",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "arc_length", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
            "normalized_parameter",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": True,
                    "end": 1.0,
                },
                "lens_length": 35.0,
            },
            "sampling",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.8,
                    "end": 0.2,
                },
                "lens_length": 35.0,
            },
            "sampling",
        ),
        (
            {
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
            },
            "lens_length or fov_degrees",
        ),
    ],
)
async def test_curve_follow_target_rejects_invalid_authoring(camera, message):
    camera["strategy"] = "curve_follow_target"
    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {"camera": camera},
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(),
            port=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("optics", "authority", "expected_lens", "expected_fov"),
    [
        ({"lens_length": 35.0}, "lens_length", 35.0, None),
        ({"fov_degrees": 45.0}, "fov_degrees", None, 45.0),
        ({"lens_length": 35.0, "fov_degrees": 45.0}, "lens_length", 35.0, 45.0),
    ],
)
async def test_curve_follow_target_records_optics_authority(
    optics, authority, expected_lens, expected_fov
):
    result = await camera_planner.resolve_camera_plan(
        {
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": "00000000-0000-0000-0000-000000000001",
                "target": [0.0, 0.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {
                    "mode": "normalized_parameter",
                    "start": 0.0,
                    "end": 1.0,
                },
                **optics,
            }
        },
        frame_count=3,
        resolution={"width": 640, "height": 360},
        call_native=FakeCurveNative(),
        port=None,
    )

    assert result["provenance"]["optics_authority"] == authority
    assert result["frames"][0]["lens_length"] == expected_lens
    assert result["frames"][0]["fov_degrees"] == expected_fov


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("curve_response", "message"),
    [
        (
            {"success": False, "data": {"code": "curve_not_found", "message": "missing"}},
            "curve_not_found",
        ),
        (
            {
                "success": False,
                "data": {"error": {"code": "not_curve", "message": "not curve"}},
            },
            "not_curve",
        ),
        ({"success": False, "data": "plain failure"}, "plain failure"),
        ({"success": False, "data": None}, "curve sample resolution failed"),
    ],
)
async def test_curve_follow_target_reports_native_failure_shapes(
    curve_response, message
):
    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {
                        "mode": "normalized_parameter",
                        "start": 0.0,
                        "end": 1.0,
                    },
                    "lens_length": 35.0,
                }
            },
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(curve_response=curve_response),
            port=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("samples", "message"),
    [
        ([{"frame_index": 1, "point": [0.0, -10.0, 5.0]}], "missing"),
        (
            [
                {"frame_index": 1, "point": [0.0, -10.0, 5.0]},
                {"frame_index": 1, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 2, "point": [2.0, -10.0, 5.0]},
            ],
            "duplicate",
        ),
        (
            [
                {"frame_index": 1, "point": [0.0, -10.0, 5.0]},
                {"frame_index": 2, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 4, "point": [2.0, -10.0, 5.0]},
            ],
            "frame_index",
        ),
        (
            [
                None,
                {"frame_index": 2, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 3, "point": [2.0, -10.0, 5.0]},
            ],
            "sample",
        ),
        (
            [
                {"frame_index": 1, "point": [True, -10.0, 5.0]},
                {"frame_index": 2, "point": [1.0, -10.0, 5.0]},
                {"frame_index": 3, "point": [2.0, -10.0, 5.0]},
            ],
            "point",
        ),
    ],
)
async def test_curve_follow_target_rejects_bad_curve_samples(samples, message):
    with pytest.raises(camera_planner.CameraPlanError, match=message):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {
                        "mode": "normalized_parameter",
                        "start": 0.0,
                        "end": 1.0,
                    },
                    "lens_length": 35.0,
                }
            },
            frame_count=3,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(samples=samples),
            port=None,
        )


@pytest.mark.asyncio
async def test_curve_follow_target_rejects_sample_at_target():
    with pytest.raises(camera_planner.CameraPlanError, match="location and target"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {
                        "mode": "normalized_parameter",
                        "start": 0.0,
                        "end": 1.0,
                    },
                    "lens_length": 35.0,
                }
            },
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(
                samples=[{"frame_index": 1, "point": [0.0, 0.0, 0.0]}]
            ),
            port=None,
        )


@pytest.mark.asyncio
async def test_curve_follow_target_rejects_up_parallel_to_view_direction():
    with pytest.raises(camera_planner.CameraPlanError, match="parallel"):
        await camera_planner.resolve_camera_plan(
            {
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "00000000-0000-0000-0000-000000000001",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {
                        "mode": "normalized_parameter",
                        "start": 0.0,
                        "end": 1.0,
                    },
                    "lens_length": 35.0,
                }
            },
            frame_count=1,
            resolution={"width": 640, "height": 360},
            call_native=FakeCurveNative(
                samples=[{"frame_index": 1, "point": [0.0, 0.0, 10.0]}]
            ),
            port=None,
        )


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
            {"camera": {"strategy": "orbit"}},
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
