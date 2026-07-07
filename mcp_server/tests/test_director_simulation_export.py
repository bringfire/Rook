import pytest

from rook import director_simulation_export as sx


def _meta():
    return {
        "actor_set_id": "actor_x",
        "source_block_name": "BLK",
        "source_top_level_object_id": "a28cbdb5",
        "fps": 24,
        "units": "millimeters",
        "component_provenance": {
            "component_nick": "Director Band Peel Wave Preview",
        },
    }


def test_build_samples_artifact_shape():
    art = sx.build_samples_artifact(
        ["id0", "id1"],
        [[0.0, 0.0], [0.0, 5.0], [0.0, 10.0]],
        _meta(),
    )
    assert art["metadata_kind"] == "director_member_motion_samples_v1"
    assert art["schema_version"] == 1
    assert art["frame_count"] == 3
    assert art["transform_semantics"] == "absolute_from_source"
    assert art["sample_kind"] == "translate_z"
    assert art["id_space"] == "top_level_definition_object_id"
    assert art["ids"] == ["id0", "id1"]
    assert art["frames"][0] == {"frame_index": 1, "translate_z": [0.0, 0.0]}
    assert art["frames"][2] == {"frame_index": 3, "translate_z": [0.0, 10.0]}
    assert art["ids_sha256"] == sx.ids_sha256(["id0", "id1"])


def test_ids_sha256_order_sensitive_and_canonical():
    assert sx.ids_sha256(["a", "b"]) != sx.ids_sha256(["b", "a"])
    import hashlib
    import json

    expected = hashlib.sha256(
        json.dumps(["a", "b"], indent=2, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert sx.ids_sha256(["a", "b"]) == expected


def test_invariants_pass_on_valid_artifact():
    art = sx.build_samples_artifact(["id0", "id1"], [[0.0, 0.0], [0.0, 5.0]], _meta())
    sx.assert_samples_invariants(art)


def test_invariants_reject_frame_count_lt_2():
    art = sx.build_samples_artifact(["id0"], [[0.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "frame_count_too_small"


def test_invariants_reject_duplicate_ids():
    art = sx.build_samples_artifact(["id0", "id0"], [[0.0, 0.0], [0.0, 5.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "duplicate_member_id"


def test_invariants_reject_frame0_not_rest():
    art = sx.build_samples_artifact(["id0"], [[3.0], [5.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "frame0_not_rest"


def test_invariants_reject_member_count_mismatch():
    art = sx.build_samples_artifact(["id0", "id1"], [[0.0, 0.0], [0.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_samples_invariants(art)
    assert ei.value.code == "member_count_mismatch"


def test_build_actor_member_ids_formats_index_4wide():
    objs = [{"id": "d0", "index": 3}, {"id": "d1", "index": 239}]
    mid, idx = sx.build_actor_member_ids(objs, "actor_x")
    assert mid == {"d0": "actor_x_member_0003", "d1": "actor_x_member_0239"}
    assert idx == {"d0": 3, "d1": 239}


def test_build_actor_member_ids_rejects_duplicate_def_id():
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.build_actor_member_ids(
            [{"id": "d0", "index": 1}, {"id": "d0", "index": 2}],
            "actor_x",
        )
    assert ei.value.code == "duplicate_definition_object_id"


def test_build_motion_json_per_member_dense_keyframes():
    art = sx.build_samples_artifact(
        ["d0", "d1"],
        [[0.0, 0.0], [0.0, 6.0], [0.0, 12.0]],
        _meta(),
    )
    def_to_member = {"d0": "actor_x_member_0003", "d1": "actor_x_member_0239"}
    mj = sx.build_motion_json(art, def_to_member, fps=24)
    assert mj["timeline"] == {"fps": 24, "frame_count": 3}
    assert mj["groups"] == {}
    assert mj["default_easing"] == "linear"
    assert len(mj["motion"]) == 2
    track = next(t for t in mj["motion"] if t["target"] == "actor_x_member_0239")
    assert track["keyframes"] == [
        {"t": 0.5, "translate": [0.0, 0.0, 6.0]},
        {"t": 1.0, "translate": [0.0, 0.0, 12.0]},
    ]


def test_build_motion_json_rejects_unknown_def_id():
    art = sx.build_samples_artifact(["dX"], [[0.0], [0.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.build_motion_json(art, {"d0": "actor_x_member_0003"}, fps=24)
    assert ei.value.code == "nested_or_unknown_id"


def test_build_motion_json_rejects_duplicate_generated_member_id():
    art = sx.build_samples_artifact(["d0", "d1"], [[0.0, 0.0], [0.0, 5.0]], _meta())
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.build_motion_json(
            art,
            {"d0": "actor_x_member_0003", "d1": "actor_x_member_0003"},
            fps=24,
        )
    assert ei.value.code == "duplicate_member_id"


def _track_with(members):
    object_frames = []
    for frame_index in sorted(members):
        transforms = [
            {
                "object_id": cid,
                "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, dz], [0, 0, 0, 1]],
            }
            for cid, dz in members[frame_index].items()
        ]
        object_frames.append({"frame_index": frame_index, "object_transforms": transforms})
    return {"object_frames": object_frames}


def test_manifest_matches_ok_and_drift():
    manifest = {
        "actor_sets": [
            {
                "actor_set_id": "actor_x",
                "members": [
                    {
                        "definition_object_id": "d0",
                        "definition_object_index": 3,
                        "actor_member_id": "actor_x_member_0003",
                    }
                ],
            }
        ]
    }
    sx.assert_manifest_matches(manifest, "actor_x", {"d0": "actor_x_member_0003"}, {"d0": 3})
    bad = {
        "actor_sets": [
            {
                "actor_set_id": "actor_x",
                "members": [
                    {
                        "definition_object_id": "d0",
                        "definition_object_index": 99,
                        "actor_member_id": "actor_x_member_0003",
                    }
                ],
            }
        ]
    }
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.assert_manifest_matches(bad, "actor_x", {"d0": "actor_x_member_0003"}, {"d0": 3})
    assert ei.value.code == "manifest_drift"


def test_motion_roundtrip_ok_including_nested_member():
    art = sx.build_samples_artifact(["d0", "dNest"], [[0.0, 0.0], [0.0, 7.0]], _meta())
    member_map = {"d0": ["c0"], "dNest": ["cA", "cB"]}
    track = _track_with(
        {
            1: {"c0": 0.0, "cA": 0.0, "cB": 0.0},
            2: {"c0": 0.0, "cA": 7.0, "cB": 7.0},
        }
    )
    sx.verify_motion_roundtrip(track, art, member_map, ["d0", "dNest"])


def test_motion_roundtrip_mismatch():
    art = sx.build_samples_artifact(["d0"], [[0.0], [9.0]], _meta())
    track = _track_with({1: {"c0": 0.0}, 2: {"c0": 8.0}})
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.verify_motion_roundtrip(track, art, {"d0": ["c0"]}, ["d0"])
    assert ei.value.code == "motion_roundtrip_mismatch"


def test_camera_roundtrip_ok_and_length_mismatch():
    cam = {
        "projection": "perspective",
        "location": [1, 2, 3],
        "target": [0, 0, 0],
        "up": [0, 0, 1],
        "lens_length": 50,
    }
    kfs = [
        {"frame_index": 1, "source": {"kind": "explicit_camera", "camera": cam}},
        {"frame_index": 2, "source": {"kind": "explicit_camera", "camera": cam}},
    ]
    track = {
        "camera_frames": [
            {"frame_index": 1, "camera": cam},
            {"frame_index": 2, "camera": cam},
        ]
    }
    sx.verify_camera_roundtrip(track, kfs)
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.verify_camera_roundtrip({"camera_frames": [{"frame_index": 1, "camera": cam}]}, kfs)
    assert ei.value.code == "camera_frame_count_mismatch"


def test_camera_roundtrip_rejects_lens_or_projection_mismatch():
    cam = {
        "projection": "perspective",
        "location": [1, 2, 3],
        "target": [0, 0, 0],
        "up": [0, 0, 1],
        "lens_length": 50,
    }
    kfs = [{"frame_index": 1, "source": {"kind": "explicit_camera", "camera": cam}}]
    bad_lens = dict(cam, lens_length=35)
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.verify_camera_roundtrip(
            {"camera_frames": [{"frame_index": 1, "camera": bad_lens}]},
            kfs,
        )
    assert ei.value.code == "camera_roundtrip_mismatch"

    bad_projection = dict(cam, projection="parallel")
    with pytest.raises(sx.SimulationExportError) as ei:
        sx.verify_camera_roundtrip(
            {"camera_frames": [{"frame_index": 1, "camera": bad_projection}]},
            kfs,
        )
    assert ei.value.code == "camera_roundtrip_mismatch"
