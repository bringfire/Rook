import asyncio
import json as _json

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


class _FakeNative:
    """Simulates /gh/value + /gh/inspect-output for a 2-member, 3-frame wave."""

    def __init__(self):
        self.frame_in = 0
        self._z = {0: [0.0, 0.0], 120: [0.0, 5.0], 240: [0.0, 10.0]}

    async def __call__(self, endpoint, method="GET", data=None, *, port=None):
        if endpoint == "/gh/value" and method == "POST":
            self.frame_in = data["value"]
            return {"success": True, "data": {}}
        if endpoint.startswith("/gh/inspect-output"):
            param = data["param"] if data else None
            local_t = self.frame_in / 240.0
            if param == "H":  # wave emits packed samples JSON on the H output
                payload = _json.dumps({"ids": ["d0", "d1"], "z": self._z[self.frame_in]})
                return {"success": True, "data": {"preview": [payload]}}
            if param == "Camera":
                cam = {
                    "projection": "perspective",
                    "location": [self.frame_in, 0, 0],
                    "target": [0, 0, 0],
                    "up": [0, 0, 1],
                    "lens_length": 50,
                    "local_t": local_t,
                }
                return {"success": True, "data": {"preview": [_json.dumps(cam)]}}
        raise AssertionError(f"unexpected {endpoint} {data}")


def test_harvest_samples_maps_frames_and_hashes_ids():
    fake = _FakeNative()
    roles = {"frame_in": "fi", "camera_ctrl": "cc", "wave": "wv"}
    ids, per_frame_z, cams = asyncio.run(
        sx.harvest_samples(fake, roles, frame_count=3, clock_denominator=240)
    )
    assert ids == ["d0", "d1"]
    assert per_frame_z == [[0.0, 0.0], [0.0, 5.0], [0.0, 10.0]]
    assert [c["frame_index"] for c in cams] == [1, 2, 3]
    assert cams[1]["source"]["camera"]["location"] == [120, 0, 0]
    assert fake.frame_in == 0


def test_harvest_samples_rejects_ids_drift():
    fake = _FakeNative()
    orig = fake.__call__

    async def drift(endpoint, method="GET", data=None, *, port=None):
        r = await orig(endpoint, method, data, port=port)
        if data and data.get("param") == "H" and fake.frame_in == 240:
            r = {
                "success": True,
                "data": {"preview": [_json.dumps({"ids": ["d0", "dX"], "z": [0.0, 10.0]})]},
            }
        return r

    with pytest.raises(sx.SimulationExportError) as ei:
        asyncio.run(
            sx.harvest_samples(
                drift,
                {"frame_in": "fi", "camera_ctrl": "cc", "wave": "wv"},
                frame_count=3,
                clock_denominator=240,
            )
        )
    assert ei.value.code == "ids_unstable"


def test_resolve_canvas_roles_matches_exact_nickname_and_type():
    async def fake(endpoint, method="GET", data=None, *, port=None):
        assert endpoint == "/gh/query"
        return {
            "success": True,
            "data": {
                "objects": [
                    {"guid": "group", "nickName": "Director Camera Controller v0", "type": "GH_Group"},
                    {"guid": "fi", "nickName": "FrameIn", "type": "GH_NumberSlider"},
                    {"guid": "cc", "nickName": "Director Camera Controller", "type": "CSharpComponent"},
                    {"guid": "wv", "nickName": "Director Band Peel Wave Preview", "type": "CSharpComponent"},
                ]
            },
        }

    assert asyncio.run(sx.resolve_canvas_roles(fake)) == {
        "frame_in": "fi",
        "camera_ctrl": "cc",
        "wave": "wv",
    }


def test_run_simulation_export_drives_capture_only_pipeline(tmp_path, monkeypatch):
    from rook import director_take_package as dtp
    from rook import director_worker_capture as dwcap
    from rook import director_worker_compile as dwc
    from rook import director_worker_prepare as dprep

    cam = {
        "projection": "perspective",
        "location": [1, 2, 3],
        "target": [0, 0, 0],
        "up": [0, 0, 1],
        "lens_length": 50,
    }
    cam_keyframes = [
        {"frame_index": 1, "source": {"kind": "explicit_camera", "camera": cam}},
        {"frame_index": 2, "source": {"kind": "explicit_camera", "camera": cam}},
    ]
    package_root = tmp_path / "take"
    capture_calls = []

    async def fake_resolve(call_native):
        return {"frame_in": "fi", "camera_ctrl": "cc", "wave": "wv"}

    async def fake_harvest(call_native, roles, frame_count, clock_denominator):
        assert frame_count == 2
        assert clock_denominator == 240
        return ["d0", "d1"], [[0.0, 0.0], [0.0, 5.0]], cam_keyframes

    async def fake_package(args, *, call_native):
        package_root.mkdir()
        assert args["motion"]["motion"][1]["target"] == "actor_x_member_0001"
        assert args["camera"] == {"strategy": "keyframes", "keyframes": cam_keyframes}
        (package_root / "scene_manifest.json").write_text(
            _json.dumps(
                {
                    "actor_sets": [
                        {
                            "actor_set_id": "actor_x",
                            "members": [
                                {
                                    "definition_object_id": "d0",
                                    "definition_object_index": 0,
                                    "actor_member_id": "actor_x_member_0000",
                                },
                                {
                                    "definition_object_id": "d1",
                                    "definition_object_index": 1,
                                    "actor_member_id": "actor_x_member_0001",
                                },
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return {"package_root": str(package_root)}

    async def fake_prepare(args, *, call_native):
        assert args == {"package_root": str(package_root)}
        (package_root / "member_map.json").write_text(
            _json.dumps(
                {
                    "actor_sets": [
                        {
                            "members": [
                                {"definition_object_id": "d0", "created_object_ids": ["c0"]},
                                {"definition_object_id": "d1", "created_object_ids": ["c1a", "c1b"]},
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return {"phase": "prepared"}

    async def fake_compile(args, *, call_native):
        assert args == {"package_root": str(package_root)}
        (package_root / "track.json").write_text(
            _json.dumps(
                {
                    "object_frames": [
                        {
                            "frame_index": 1,
                            "object_transforms": [
                                {"object_id": "c0", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
                                {"object_id": "c1a", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
                                {"object_id": "c1b", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
                            ],
                        },
                        {
                            "frame_index": 2,
                            "object_transforms": [
                                {"object_id": "c0", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
                                {"object_id": "c1a", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 5], [0, 0, 0, 1]]},
                                {"object_id": "c1b", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 5], [0, 0, 0, 1]]},
                            ],
                        },
                    ],
                    "camera_frames": [
                        {"frame_index": 1, "camera": cam},
                        {"frame_index": 2, "camera": cam},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {"phase": "compiled"}

    async def fake_capture(args, *, call_native):
        capture_calls.append(args)
        return {"passes": [{"run_root": str(package_root / "sim"), "frames_written": 2}]}

    class FakeNative:
        def __init__(self):
            self.opened = []

        async def __call__(self, endpoint, method="GET", data=None, *, port=None):
            if endpoint == "/document" and method == "GET":
                return {"success": True, "data": {"path": "C:/live/Pearson.3dm", "modified": False}}
            if endpoint == "/block/objects-detailed":
                return {
                    "success": True,
                    "data": {"objects": [{"id": "d0", "index": 0}, {"id": "d1", "index": 1}]},
                }
            if endpoint == "/document/open" and method == "POST":
                self.opened.append(data["path"])
                return {"success": True, "data": {}}
            raise AssertionError(f"unexpected {endpoint} {method} {data}")

    monkeypatch.setattr(sx, "resolve_canvas_roles", fake_resolve)
    monkeypatch.setattr(sx, "harvest_samples", fake_harvest)
    monkeypatch.setattr(dtp, "package_take", fake_package)
    monkeypatch.setattr(dprep, "prepare_take", fake_prepare)
    monkeypatch.setattr(dwc, "compile_take", fake_compile)
    monkeypatch.setattr(dwcap, "capture_take", fake_capture)

    fake_native = FakeNative()
    result = asyncio.run(
        sx.run_simulation_export(
            {
                "take_id": "take1",
                "actor_set_id": "actor_x",
                "block_name": "BLK",
                "source_top_level_object_id": "src1",
                "output_root": str(tmp_path),
                "frame_count": 2,
                "fps": 24,
                "units": "millimeters",
                "display_modes": ["Shaded"],
                "capture_mode": "Shaded",
                "resolution": {"width": 640, "height": 360},
                "clock_denominator": 240,
            },
            call_native=fake_native,
        )
    )
    assert result["prepared"] == "prepared"
    assert result["compiled"] == "compiled"
    assert result["capture"]["frames_written"] == 2
    assert capture_calls == [
        {
            "package_root": str(package_root),
            "passes": [{"type": "display_mode", "pass_id": "sim", "display_mode": "Shaded"}],
            "resolution": {"width": 640, "height": 360},
        }
    ]
    assert fake_native.opened == ["C:/live/Pearson.3dm"]
