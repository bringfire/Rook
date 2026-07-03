from __future__ import annotations

import asyncio
import hashlib
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
        if endpoint == "/director/curve-samples":
            return {
                "success": True,
                "data": {
                    "schema_version": 1,
                    "curve_id": data["curve_id"],
                    "frame_count": data["frame_count"],
                    "samples": [
                        {
                            "frame_index": index,
                            "normalized_parameter": 0.0
                            if data["frame_count"] == 1
                            else (index - 1) / (data["frame_count"] - 1),
                            "curve_parameter": float(index),
                            "point": [float(index), -10.0, 5.0],
                            "tangent": [1.0, 0.0, 0.0],
                        }
                        for index in range(1, data["frame_count"] + 1)
                    ],
                    "provenance": {
                        "sampling_mode": "normalized_parameter",
                        "parameter_mapping": "curve_domain_parameter_at",
                        "frame_count_source": "caller_canonical_frame_count",
                        "arc_length_sampled": False,
                        "validation_strength": "curve_parameter_sampled",
                    },
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


def _canonical_hash(payload):
    data = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _compiled_track():
    object_id = "11111111-1111-1111-1111-111111111111"
    return {
        "transform_semantics": "absolute_from_source",
        "fps": 24,
        "frame_count": 2,
        "animated_object_ids": [object_id],
        "camera_frames": [
            {"frame_index": 1, "camera": _explicit_camera()},
            {"frame_index": 2, "camera": _explicit_camera(location=[6.0, -4.0, 3.0])},
        ],
        "object_frames": [
            {
                "frame_index": 1,
                "object_transforms": [
                    {
                        "object_id": object_id,
                        "source_state": {
                            "bbox_min": [0, 0, 0],
                            "bbox_max": [1, 1, 1],
                            "validation_strength": "bbox_only",
                            "state_hash": "state-a",
                        },
                        "transform": director.identity_matrix(),
                    }
                ],
            },
            {
                "frame_index": 2,
                "object_transforms": [
                    {
                        "object_id": object_id,
                        "source_state": {
                            "bbox_min": [0, 0, 0],
                            "bbox_max": [1, 1, 1],
                            "validation_strength": "bbox_only",
                            "state_hash": "state-a",
                        },
                        "transform": director.translation_matrix([1, 0, 0]),
                    }
                ],
            },
        ],
    }


def test_run_compiled_track_writes_manifest_frames_inputs_and_evidence(tmp_path):
    spec = {
        "metadata_kind": "director_authoring_spec",
        "spec_id": "spec_a",
        "timeline": {"fps": 24, "frame_count": 2},
        "resolution": {"width": 320, "height": 180},
    }
    source_hash = _canonical_hash(spec)
    fake = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )

    result = asyncio.run(
        director.run_compiled_track(
            {
                "track": _compiled_track(),
                "resolution": {"width": 320, "height": 180},
                "display": {"mode": "Rendered"},
                "output_root": str(
                    tmp_path / "data" / "rookvision_director" / "canvas_runs"
                ),
                "run_id": "compiled-track-a",
                "run_inputs": {
                    "director_authoring_spec": spec,
                    "provenance": {
                        "source_spec_id": "spec_a",
                        "source_spec_sha256": source_hash,
                        "canvas_export_state_sha256": "export-hash",
                    },
                },
                "compile_provenance": {
                    "frame_count": 2,
                    "fps": 24,
                    "warnings": [],
                },
            },
            call_native=fake,
            runtime=_runtime(tmp_path),
        )
    )

    run_root = Path(result["run_root"])
    assert result["state"] == "complete"
    assert run_root == (
        tmp_path
        / "data"
        / "rookvision_director"
        / "canvas_runs"
        / "compiled-track-a"
    ).resolve()
    assert json.loads(
        (run_root / "inputs" / "director_authoring_spec.json").read_text(
            encoding="utf-8"
        )
    ) == spec
    provenance = json.loads(
        (run_root / "inputs" / "provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["source_spec_sha256"] == source_hash
    assert provenance["copied_spec_sha256"] == source_hash
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["motion"]["strategy"] == "compiled_track"
    assert manifest["motion"]["transform_semantics"] == "absolute_from_source"
    assert manifest["motion"]["provenance"] == {
        "frame_count": 2,
        "fps": 24,
        "warnings": [],
    }
    assert manifest["camera_plan"]["strategy"] == "compiled_track"
    assert manifest["frame_count"] == 2
    assert manifest["timeline"] == {
        "source": "compiled_track",
        "fps": 24,
        "frame_count": 2,
        "duration_seconds": pytest.approx(2 / 24),
    }
    assert (run_root / "frames" / "frame_0001.png").is_file()
    assert (run_root / "frames" / "frame_0002.png").is_file()
    evidence_lines = (
        run_root / "logs" / "frame_evidence.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(evidence_lines) == 2


@pytest.mark.parametrize(
    "run_inputs",
    [
        [],
        {},
        {"director_authoring_spec": []},
        {"director_authoring_spec": {"spec_id": "spec_a"}, "provenance": None},
        {"director_authoring_spec": {"spec_id": "spec_a"}, "provenance": []},
    ],
)
def test_validate_run_inputs_rejects_malformed_inputs(run_inputs):
    with pytest.raises(director.DirectorInputError):
        director._validate_run_inputs(run_inputs)


def test_write_run_inputs_rejects_conflicting_source_spec_hash(tmp_path):
    spec = {"metadata_kind": "director_authoring_spec", "spec_id": "spec_a"}
    run_root = tmp_path / "run"

    with pytest.raises(director.DirectorInputError, match="source_spec_sha256"):
        director._write_run_inputs(
            run_root,
            director_authoring_spec=spec,
            provenance={"source_spec_sha256": "not-the-copied-hash"},
        )

    assert not (run_root / "inputs").exists()


@pytest.mark.parametrize(
    "kind, frames",
    [
        ("camera", [{"camera": _explicit_camera()}, {"frame_index": 2, "camera": _explicit_camera()}]),
        ("camera", [{"frame_index": "1", "camera": _explicit_camera()}, {"frame_index": 2, "camera": _explicit_camera()}]),
        ("camera", [{"frame_index": 1, "camera": _explicit_camera()}, {"frame_index": 1, "camera": _explicit_camera()}]),
        ("camera", [{"frame_index": 1, "camera": _explicit_camera()}, {"frame_index": 3, "camera": _explicit_camera()}]),
        ("object", [{"object_transforms": []}, {"frame_index": 2, "object_transforms": []}]),
        ("object", [{"frame_index": "1", "object_transforms": []}, {"frame_index": 2, "object_transforms": []}]),
        ("object", [{"frame_index": 1, "object_transforms": []}, {"frame_index": 1, "object_transforms": []}]),
        ("object", [{"frame_index": 1, "object_transforms": []}, {"frame_index": 3, "object_transforms": []}]),
    ],
)
def test_indexed_track_frames_rejects_bad_frame_indexes(kind, frames):
    track = _compiled_track()
    key = "camera_frames" if kind == "camera" else "object_frames"
    track[key] = frames

    with pytest.raises(director.DirectorInputError, match="frame_index"):
        director._indexed_track_frames(track, 2)


def test_run_compiled_track_rejects_bad_resolution_before_creating_run(tmp_path):
    output_root = tmp_path / "data" / "rookvision_director" / "canvas_runs"

    with pytest.raises(director.DirectorInputError, match="resolution"):
        asyncio.run(
            director.run_compiled_track(
                {
                    "track": _compiled_track(),
                    "resolution": {"width": 0, "height": 180},
                    "output_root": str(output_root),
                    "run_id": "bad-resolution",
                },
                call_native=FakeNative([]),
                runtime=_runtime(tmp_path),
            )
        )

    assert not (output_root / "bad-resolution").exists()


def test_run_compiled_track_rejects_conflicting_provenance_before_creating_run(tmp_path):
    output_root = tmp_path / "data" / "rookvision_director" / "canvas_runs"

    with pytest.raises(director.DirectorInputError, match="source_spec_sha256"):
        asyncio.run(
            director.run_compiled_track(
                {
                    "track": _compiled_track(),
                    "resolution": {"width": 320, "height": 180},
                    "output_root": str(output_root),
                    "run_id": "bad-provenance",
                    "run_inputs": {
                        "director_authoring_spec": {"spec_id": "spec_a"},
                        "provenance": {"source_spec_sha256": "wrong"},
                    },
                },
                call_native=FakeNative([]),
                runtime=_runtime(tmp_path),
            )
        )

    assert not (output_root / "bad-provenance").exists()


@pytest.mark.parametrize(
    "bad_run_id",
    [
        "../escape",
        "/tmp/escape",
        "C:/escape",
        "bad/slash",
        "",
        ".",
        "..",
        "bad.name",
        "_bad",
        "CON",
        "con",
        "COM1",
        "LPT9",
    ],
)
def test_run_compiled_track_rejects_bad_run_id_before_creating_run(
    tmp_path, bad_run_id
):
    output_root = tmp_path / "data" / "rookvision_director" / "canvas_runs"

    with pytest.raises(director.DirectorInputError, match="run_id"):
        asyncio.run(
            director.run_compiled_track(
                {
                    "track": _compiled_track(),
                    "resolution": {"width": 320, "height": 180},
                    "output_root": str(output_root),
                    "run_id": bad_run_id,
                },
                call_native=FakeNative([]),
                runtime=_runtime(tmp_path),
            )
        )

    assert not output_root.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "field, value",
    [
        ("frame_count", 0),
        ("frame_count", -1),
        ("frame_count", 1.5),
        ("frame_count", True),
        ("fps", 0),
        ("fps", -1),
        ("fps", 24.0),
        ("fps", False),
    ],
)
def test_run_compiled_track_rejects_bad_track_positive_ints(tmp_path, field, value):
    output_root = tmp_path / "data" / "rookvision_director" / "canvas_runs"
    track = _compiled_track()
    track[field] = value

    with pytest.raises(director.DirectorInputError, match=field):
        asyncio.run(
            director.run_compiled_track(
                {
                    "track": track,
                    "resolution": {"width": 320, "height": 180},
                    "output_root": str(output_root),
                    "run_id": "bad-track",
                },
                call_native=FakeNative([]),
                runtime=_runtime(tmp_path),
            )
        )

    assert not (output_root / "bad-track").exists()


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


@pytest.mark.asyncio
async def test_director_rejects_invalid_curve_follow_before_object_resolution(tmp_path):
    native = FakeNative([], create_outputs=True)
    allowed_root = tmp_path / "data" / "rookvision_director"

    with pytest.raises(director.DirectorInputError, match="curve_id"):
        await director.run_director(
            {
                "object_ids": ["a"],
                "frame_count": 1,
                "resolution": {"width": 320, "height": 180},
                "camera": {
                    "strategy": "curve_follow_target",
                    "curve_id": "not-a-uuid",
                    "target": [0.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "sampling": {
                        "mode": "normalized_parameter",
                        "start": 0.0,
                        "end": 1.0,
                    },
                    "lens_length": 35.0,
                },
                "output_root": str(allowed_root),
            },
            call_native=native,
            runtime=_runtime(tmp_path),
        )

    assert not any(call[0] == "/director/object-states" for call in native.calls)


@pytest.mark.asyncio
async def test_director_curve_follow_target_writes_strategy_manifest_and_frame_cameras(
    tmp_path,
):
    native = FakeNative(
        [
            {"success": True, "data": {"frame_id": "frame_0001", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0002", "dirty_partial_state": False}},
            {"success": True, "data": {"frame_id": "frame_0003", "dirty_partial_state": False}},
        ],
        create_outputs=True,
    )
    curve_id = "00000000-0000-0000-0000-000000000001"
    allowed_root = tmp_path / "data" / "rookvision_director"

    result = await director.run_director(
        {
            "object_ids": ["a"],
            "timeline": {"fps": 24, "duration_seconds": 0.125},
            "resolution": {"width": 320, "height": 180},
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
            },
            "output_root": str(allowed_root),
        },
        call_native=native,
        runtime=_runtime(tmp_path),
    )

    manifest = json.loads(
        (Path(result["run_root"]) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["camera_plan"]["strategy"] == "curve_follow_target"
    assert manifest["camera_plan"]["request_shape"] == "camera_strategy"
    assert manifest["camera_plan"]["aspect_authority"] == "output_resolution"
    assert manifest["camera_plan"]["optics_authority"] == "lens_length"
    assert manifest["camera_plan"]["provenance"]["curve_id"] == curve_id
    assert (
        manifest["camera_plan"]["provenance"]["curve_sampling"]["parameter_mapping"]
        == "curve_domain_parameter_at"
    )
    assert manifest["camera_keyframes"] == []
    assert manifest["camera_keyframe_provenance"] == []
    assert all(
        frame["camera"]["projection"] == "perspective" for frame in manifest["frames"]
    )

    endpoints = [call[0] for call in native.calls]
    assert "/director/view-state" not in endpoints
    assert endpoints.count("/director/curve-samples") == 1
    assert endpoints.count("/director/frame-capture") == manifest["frame_count"]


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
