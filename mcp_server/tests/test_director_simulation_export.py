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
