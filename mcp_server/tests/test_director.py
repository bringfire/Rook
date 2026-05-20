from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from rook import director


def test_default_output_root_uses_local_app_data_rook_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = director.resolve_output_root(None)
    assert root == (tmp_path / "local" / "Rook" / "rookvision_director").resolve()


def test_env_output_root_is_shared_allowlist_source(tmp_path, monkeypatch):
    configured = tmp_path / "configured" / "director"
    monkeypatch.setenv("ROOK_DIRECTOR_OUTPUT_ROOT", str(configured))
    assert director.resolve_output_root(None) == configured.resolve()


def test_output_root_must_stay_under_shared_director_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOK_DIRECTOR_OUTPUT_ROOT", str(tmp_path / "allowed"))
    with pytest.raises(director.DirectorInputError, match="output_root"):
        director.resolve_output_root(str(tmp_path / "outside"))


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"frame_count": 0}, "frame_count"),
        ({"frame_count": 1, "resolution": {"width": 0, "height": 720}}, "resolution"),
        ({"frame_count": 1, "resolution": {"width": 1280, "height": -1}}, "resolution"),
        (
            {
                "frame_count": 1,
                "resolution": {"width": 1280, "height": 720},
                "motion": {
                    "strategy": "radial_bbox_center",
                    "parameters": {"distance": -1},
                },
            },
            "distance",
        ),
        (
            {
                "frame_count": 1,
                "resolution": {"width": 1280, "height": 720},
                "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
                "motion": {
                    "strategy": "radial_bbox_center",
                    "parameters": {"distance": 1, "per_object_scale": {"a": -1}},
                },
            },
            "per_object_scale",
        ),
        (
            {
                "frame_count": 1,
                "resolution": {"width": 1280, "height": 720},
                "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
                "motion": {
                    "strategy": "radial_bbox_center",
                    "parameters": {"distance": 1, "per_object_scale": {"a": "large"}},
                },
            },
            "per_object_scale",
        ),
        (
            {
                "frame_count": 1,
                "resolution": {"width": 1280, "height": 720},
                "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
                "motion": {
                    "strategy": "radial_bbox_center",
                    "parameters": {"distance": 1, "per_object_scale": []},
                },
            },
            "per_object_scale",
        ),
        (
            {"frame_count": 1, "resolution": {"width": 1280, "height": 720}},
            "camera.keyframes",
        ),
    ],
)
def test_validate_request_rejects_bad_authoring_inputs(payload, message):
    with pytest.raises(director.DirectorInputError, match=message):
        director.validate_authoring_request(payload)


def _obj(object_id, bbox_min, bbox_max, name=None):
    return {
        "object_id": object_id,
        "object_display_name": name,
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "validation_strength": "bbox_only",
        "state_hash": None,
    }


def test_radial_bbox_center_single_frame_has_identity_delta():
    objects = [_obj("a", [0, 0, 0], [2, 2, 2])]
    frames, warnings = director.expand_radial_bbox_center(
        objects, frame_count=1, distance=10.0, per_object_scale={}
    )
    assert warnings[0]["code"] == "center_direction_fallback"
    assert frames[0]["frame_index"] == 1
    assert frames[0]["object_transforms"][0]["transform"] == director.identity_matrix()


def test_radial_bbox_center_final_frame_moves_from_selection_center():
    objects = [
        _obj("left", [-2, -1, 0], [-1, 1, 1]),
        _obj("right", [1, -1, 0], [2, 1, 1]),
    ]
    frames, warnings = director.expand_radial_bbox_center(
        objects, frame_count=3, distance=4.0, per_object_scale={}
    )
    assert warnings == []
    final = frames[-1]["object_transforms"]
    left = next(item for item in final if item["object_id"] == "left")
    right = next(item for item in final if item["object_id"] == "right")
    assert left["transform"][0][3] == pytest.approx(-4.0)
    assert right["transform"][0][3] == pytest.approx(4.0)


def test_radial_bbox_center_records_fallback_direction_warning():
    objects = [_obj("center", [-1, -1, -1], [1, 1, 1])]
    frames, warnings = director.expand_radial_bbox_center(
        objects, frame_count=2, distance=2.0, per_object_scale={}
    )
    assert warnings
    assert warnings[0]["code"] == "center_direction_fallback"
    final = frames[-1]["object_transforms"][0]
    assert final["transform"][0][3] == pytest.approx(2.0)


class FakeNative:
    def __init__(self, responses, *, create_outputs=False, projection="perspective"):
        self.responses = list(responses)
        self.calls = []
        self.create_outputs = create_outputs
        self.projection = projection

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, method, data, port))
        if endpoint == "/director/object-states":
            return {
                "success": True,
                "data": {
                    "objects": [_obj("a", [0, 0, 0], [1, 1, 1], "A")],
                    "units": "Inches",
                },
            }
        if endpoint == "/director/view-state":
            source = data["source"]
            if source.get("kind") == "named_view" and source.get("name") == "End":
                location = [8, -4, 3]
                lens = 55.0
                provenance = {"source": "named_view", "name": "End"}
            else:
                location = [4, -4, 3]
                lens = 35.0
                provenance = {"source": "active_view"}
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": self.projection,
                        "location": location,
                        "target": [0, 0, 0],
                        "up": [0, 0, 1],
                        "lens_length": lens,
                        "fov_degrees": None,
                        "parallel_scale": None,
                        "near_clip": None,
                        "far_clip": None,
                        "aspect": 1.7778,
                    },
                    "provenance": provenance,
                },
            }
        result = self.responses.pop(0)
        if endpoint == "/director/frame-capture" and self.create_outputs and result.get("success"):
            output_path = Path(data["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"not-a-real-png-yet")
        return result


def _run_request(tmp_path):
    return {
        "object_ids": ["a"],
        "frame_count": 2,
        "resolution": {"width": 320, "height": 180},
        "display": {"mode": "Rendered"},
        "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
        "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 2.0}},
        "output_root": str(tmp_path / "data" / "rookvision_director"),
    }


def _runtime(tmp_path):
    return director.DirectorRuntimePaths(
        director_output_root=tmp_path / "data" / "rookvision_director"
    )


def _explicit_camera(location=None, lens_length=35.0):
    return {
        "projection": "perspective",
        "location": location or [4.0, -4.0, 3.0],
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "lens_length": lens_length,
        "fov_degrees": None,
        "parallel_scale": None,
        "near_clip": None,
        "far_clip": None,
        "aspect": 1.7778,
    }


def test_two_camera_keyframes_interpolate_per_frame(tmp_path):
    request = _run_request(tmp_path)
    request["frame_count"] = 3
    request["camera_keyframes"] = [
        {"frame_index": 1, "source": {"kind": "active_view"}},
        {"frame_index": 3, "source": {"kind": "named_view", "name": "End"}},
    ]
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0003", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    result = asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))
    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    locations = [frame["camera"]["location"] for frame in manifest["frames"]]
    lens_lengths = [frame["camera"]["lens_length"] for frame in manifest["frames"]]
    assert locations == [[4.0, -4.0, 3.0], [6.0, -4.0, 3.0], [8.0, -4.0, 3.0]]
    assert lens_lengths == [35.0, 45.0, 55.0]


def test_explicit_camera_keyframe_bypasses_view_state_resolution(tmp_path):
    request = _run_request(tmp_path)
    request["run_id"] = "explicit-camera"
    request["camera_keyframes"] = [
        {
            "frame_index": 1,
            "source": {"kind": "explicit_camera", "camera": _explicit_camera()},
        }
    ]
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    result = asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))

    view_state_calls = [call for call in fake.calls if call[0] == "/director/view-state"]
    frame_calls = [call for call in fake.calls if call[0] == "/director/frame-capture"]
    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    assert view_state_calls == []
    assert frame_calls[0][2]["camera"]["location"] == [4.0, -4.0, 3.0]
    assert manifest["camera_keyframe_provenance"] == [
        {"frame_index": 1, "provenance": {"source": "explicit_camera"}}
    ]


def test_explicit_camera_keyframe_normalizes_optional_numeric_fields(tmp_path):
    request = _run_request(tmp_path)
    request["run_id"] = "explicit-camera-normalized"
    camera = _explicit_camera(lens_length="35.0")
    camera.update(
        {
            "fov_degrees": "45.0",
            "aspect": "1.7778",
            "near_clip": "0.1",
            "far_clip": "1000.0",
        }
    )
    request["camera_keyframes"] = [
        {"frame_index": 1, "source": {"kind": "explicit_camera", "camera": camera}}
    ]
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )

    asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))

    frame_camera = next(call for call in fake.calls if call[0] == "/director/frame-capture")[2][
        "camera"
    ]
    assert frame_camera["lens_length"] == 35.0
    assert frame_camera["fov_degrees"] == 45.0
    assert frame_camera["aspect"] == pytest.approx(320 / 180)
    assert frame_camera["near_clip"] == 0.1
    assert frame_camera["far_clip"] == 1000.0


def test_run_complete_writes_manifest_status_and_evidence(tmp_path):
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False, "output_path": "x"}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False, "output_path": "y"}},
        ],
        create_outputs=True,
    )
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    run_root = Path(result["run_root"])
    assert result["state"] == "complete"
    assert (run_root / "manifest.json").exists()
    assert (run_root / "status.json").exists()
    assert (run_root / "logs" / "frame_evidence.jsonl").exists()
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["document_units"] == "Inches"
    assert manifest["frames"][0]["frame_index"] == 1
    evidence_lines = (run_root / "logs" / "frame_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(evidence_lines) == 2
    assert (run_root / "frames" / "frame_0001.png").exists()
    assert (run_root / "frames" / "frame_0002.png").exists()


@pytest.mark.asyncio
async def test_run_director_accepts_timeline_and_writes_manifest_timing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0003", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
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
    assert len(manifest["frames"]) == 3


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


@pytest.mark.asyncio
async def test_run_director_writes_camera_plan_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    async def fake_native(endpoint, method, data, *, port=None):
        if endpoint == "/director/object-states":
            return {
                "success": True,
                "data": {
                    "units": "Millimeters",
                    "objects": [
                        {
                            "object_id": "obj-1",
                            "bbox_min": [0, 0, 0],
                            "bbox_max": [1, 1, 1],
                            "validation_strength": "bbox_only",
                            "state_hash": None,
                        }
                    ],
                },
            }
        if endpoint == "/director/view-state":
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": "perspective",
                        "location": [0, 0, 10],
                        "target": [0, 0, 0],
                        "up": [0, 1, 0],
                        "lens_length": 35.0,
                        "fov_degrees": 37.8493,
                        "parallel_scale": None,
                        "near_clip": 0.1,
                        "far_clip": 1000.0,
                        "aspect": 0.75,
                    },
                    "provenance": {"source": "active_view"},
                },
            }
        if endpoint == "/director/frame-capture":
            output_path = Path(data["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return {
                "success": True,
                "data": {
                    "success": True,
                    "dirty_partial_state": False,
                    "objects": {"requested": 1, "restored": 1},
                    "viewport": {"restore_verified": True},
                },
            }
        raise AssertionError(endpoint)

    result = await director.run_director(
        {
            "run_id": "camera-plan-provenance",
            "object_ids": ["obj-1"],
            "frame_count": 1,
            "resolution": {"width": 640, "height": 360},
            "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
        },
        call_native=fake_native,
    )

    assert result["state"] == "complete"
    manifest = json.loads(
        (Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["camera_plan"]["strategy"] == "keyframes"
    assert manifest["camera_plan"]["request_shape"] == "legacy_camera_keyframes"
    assert manifest["camera_plan"]["aspect_authority"] == "output_resolution"
    assert manifest["camera_plan"]["optics_authority"] == "lens_length"
    assert manifest["camera_keyframe_provenance"][0]["provenance"] == {
        "source": "active_view"
    }
    assert manifest["frames"][0]["camera"]["aspect"] == pytest.approx(640 / 360)


@pytest.mark.asyncio
async def test_run_director_accepts_explicit_camera_strategy_and_writes_compatibility_fields(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    async def fake_native(endpoint, method, data, *, port=None):
        if endpoint == "/director/object-states":
            return {
                "success": True,
                "data": {
                    "units": "Millimeters",
                    "objects": [
                        {
                            "object_id": "obj-1",
                            "bbox_min": [0, 0, 0],
                            "bbox_max": [1, 1, 1],
                            "validation_strength": "bbox_only",
                            "state_hash": None,
                        }
                    ],
                },
            }
        if endpoint == "/director/view-state":
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": "perspective",
                        "location": [0, 0, 10],
                        "target": [0, 0, 0],
                        "up": [0, 1, 0],
                        "lens_length": 35.0,
                        "fov_degrees": 37.8493,
                        "parallel_scale": None,
                        "near_clip": 0.1,
                        "far_clip": 1000.0,
                        "aspect": 0.75,
                    },
                    "provenance": {"source": "named_view", "name": "Shot_A"},
                },
            }
        if endpoint == "/director/frame-capture":
            output_path = Path(data["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"png")
            return {
                "success": True,
                "data": {
                    "success": True,
                    "dirty_partial_state": False,
                    "objects": {"requested": 1, "restored": 1},
                    "viewport": {"restore_verified": True},
                },
            }
        raise AssertionError(endpoint)

    result = await director.run_director(
        {
            "run_id": "explicit-camera-strategy",
            "object_ids": ["obj-1"],
            "frame_count": 1,
            "resolution": {"width": 640, "height": 360},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"frame_index": 1, "source": {"kind": "named_view", "name": "Shot_A"}}
                ],
            },
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
        },
        call_native=fake_native,
    )

    assert result["state"] == "complete"
    manifest = json.loads(
        (Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["camera_plan"]["request_shape"] == "camera_strategy"
    assert manifest["camera_keyframes"] == [
        {"frame_index": 1, "source": {"kind": "named_view", "name": "Shot_A"}}
    ]
    assert manifest["camera_keyframe_provenance"][0]["provenance"] == {
        "source": "named_view",
        "name": "Shot_A",
    }


@pytest.mark.asyncio
async def test_run_director_rejects_bad_camera_before_resolving_objects(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    calls = []

    async def fake_native(endpoint, method, data, *, port=None):
        calls.append(endpoint)
        raise AssertionError(
            f"native should not be called for invalid camera input: {endpoint}"
        )

    with pytest.raises(director.DirectorInputError, match="frame_index"):
        await director.run_director(
            {
                "run_id": "bad-camera-fail-fast",
                "object_ids": ["obj-1"],
                "frame_count": 1,
                "resolution": {"width": 640, "height": 360},
                "camera": {
                    "strategy": "keyframes",
                    "keyframes": [
                        {"frame_index": 2, "source": {"kind": "active_view"}}
                    ],
                },
                "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            },
            call_native=fake_native,
        )

    assert calls == []


def test_run_fails_when_native_success_does_not_create_frame_file(tmp_path):
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ]
    )
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    assert result["state"] == "failed"
    status = json.loads((Path(result["run_root"]) / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed"


def test_run_marks_failed_when_native_frame_fails_safely(tmp_path):
    fake = FakeNative(
        [
            {
                "success": False,
                "data": {
                    "frame_id": "frame_0001",
                    "dirty_partial_state": False,
                    "error": {"code": "capture_failed"},
                },
            },
        ]
    )
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    assert result["state"] == "failed"


def test_run_marks_unsafe_failed_and_stops(tmp_path):
    fake = FakeNative(
        [
            {
                "success": False,
                "data": {
                    "frame_id": "frame_0001",
                    "dirty_partial_state": True,
                    "error": {"code": "restore_failed"},
                },
            },
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ]
    )
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    assert result["state"] == "unsafe_failed"
    frame_calls = [call for call in fake.calls if call[0] == "/director/frame-capture"]
    assert len(frame_calls) == 1


def test_run_marks_cancelled_between_frames(tmp_path):
    checks = iter([False, True])
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    result = asyncio.run(
        director.run_director(
            _run_request(tmp_path),
            call_native=fake,
            runtime=_runtime(tmp_path),
            should_cancel=lambda: next(checks),
        )
    )
    assert result["state"] == "cancelled"
    frame_calls = [call for call in fake.calls if call[0] == "/director/frame-capture"]
    assert len(frame_calls) == 1


def test_run_marks_evidence_failed_and_stops(tmp_path, monkeypatch):
    def fail_append(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(director, "_append_evidence", fail_append)
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    result = asyncio.run(director.run_director(_run_request(tmp_path), call_native=fake, runtime=_runtime(tmp_path)))
    assert result["state"] == "evidence_failed"
    frame_calls = [call for call in fake.calls if call[0] == "/director/frame-capture"]
    assert len(frame_calls) == 1


def test_empty_object_ids_does_not_create_run_directory(tmp_path):
    request = _run_request(tmp_path)
    request["object_ids"] = []
    request["run_id"] = "bad-empty-objects"
    with pytest.raises(director.DirectorInputError, match="object_ids"):
        asyncio.run(director.run_director(request, call_native=FakeNative([]), runtime=_runtime(tmp_path)))
    assert not (tmp_path / "data" / "rookvision_director" / "bad-empty-objects").exists()


def test_bad_camera_keyframe_does_not_create_run_directory(tmp_path):
    request = _run_request(tmp_path)
    request["run_id"] = "bad-camera"
    request["camera_keyframes"] = [{"frame_index": 3, "source": {"kind": "active_view"}}]
    with pytest.raises(director.DirectorInputError, match="camera keyframe"):
        asyncio.run(director.run_director(request, call_native=FakeNative([]), runtime=_runtime(tmp_path)))
    assert not (tmp_path / "data" / "rookvision_director" / "bad-camera").exists()


def test_missing_camera_keyframes_does_not_call_native(tmp_path):
    request = _run_request(tmp_path)
    request.pop("camera_keyframes")
    fake = FakeNative([])
    with pytest.raises(director.DirectorInputError, match="camera_keyframes"):
        asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))
    assert fake.calls == []


def test_parallel_camera_rejected_before_run_directory_creation(tmp_path):
    request = _run_request(tmp_path)
    request["run_id"] = "parallel-camera"
    fake = FakeNative([], projection="parallel")
    with pytest.raises(director.DirectorInputError, match="parallel"):
        asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))
    assert not (tmp_path / "data" / "rookvision_director" / "parallel-camera").exists()
