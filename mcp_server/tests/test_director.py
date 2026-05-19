from __future__ import annotations

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
