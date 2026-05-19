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
