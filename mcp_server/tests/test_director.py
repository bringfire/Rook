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
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

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
                        "projection": "perspective",
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
        return self.responses.pop(0)


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
        ]
    )
    result = asyncio.run(director.run_director(request, call_native=fake, runtime=_runtime(tmp_path)))
    manifest = json.loads((Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8"))
    locations = [frame["camera"]["location"] for frame in manifest["frames"]]
    lens_lengths = [frame["camera"]["lens_length"] for frame in manifest["frames"]]
    assert locations == [[4.0, -4.0, 3.0], [6.0, -4.0, 3.0], [8.0, -4.0, 3.0]]
    assert lens_lengths == [35.0, 45.0, 55.0]


def test_run_complete_writes_manifest_status_and_evidence(tmp_path):
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False, "output_path": "x"}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False, "output_path": "y"}},
        ]
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
