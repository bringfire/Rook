import pytest

from rook.scene import calibration as cal


def _sidecar():
    return {
        "schemaVersion": 1,
        "elements": [
            {
                "identity": {"uniqueId": "uid-wall", "elementId": 101, "source": "revit"},
                "elementId": 101,
                "category": "Walls",
                "family": "Basic Wall",
                "type": "Generic - 200mm",
                "name": "Wall 101",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high", "missingReason": None},
                    "hostId": {"value": None, "source": "unavailable", "confidence": "low", "missingReason": "no_host"},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high", "missingReason": None},
                },
            },
            {
                "identity": {"uniqueId": "uid-door", "elementId": 202, "source": "revit"},
                "elementId": 202,
                "category": "Doors",
                "family": "Single Flush",
                "type": "0915 x 2134mm",
                "name": "Door 202",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high", "missingReason": None},
                    "hostId": {"value": "uid-wall", "source": "revit_api", "confidence": "high", "missingReason": None},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high", "missingReason": None},
                },
            },
        ],
        "rooms": [
            {"uniqueId": "room-1", "number": "101", "name": "Office", "level": {"value": "L1"}}
        ],
        "relationships": {
            "hostMembership": [
                {"elementUniqueId": "uid-door", "hostUniqueId": "uid-wall", "source": "revit_api", "confidence": "high"}
            ],
            "roomMembership": [
                {"elementUniqueId": "uid-door", "roomUniqueId": "room-1", "source": "revit_api", "confidence": "high"},
                {"elementUniqueId": "uid-wall", "roomUniqueId": "room-1", "source": "revit_api", "confidence": "high"},
            ],
            "levelMembership": [
                {"elementUniqueId": "uid-door", "levelName": "L1", "source": "revit_api", "confidence": "high"},
                {"elementUniqueId": "uid-wall", "levelName": "L1", "source": "revit_api", "confidence": "high"},
            ],
        },
    }


def _validation():
    return {
        "schemaVersion": 1,
        "counts": {"resolved": 2, "exportedBrep": 2, "exportedMesh": 0, "exportedBboxProxy": 0, "failed": 0},
        "relationships": {
            "hostMembership": {"count": 1},
            "roomMembership": {"count": 2},
            "levelMembership": {"count": 2},
        },
        "objects": {"objectCount": 2, "withUniqueIdCount": 2},
    }


def test_validate_fixture_requires_relationship_indexes():
    sidecar = _sidecar()
    del sidecar["relationships"]["hostMembership"]

    with pytest.raises(cal.FixtureValidationError) as exc:
        cal.validate_fixture_payload(sidecar, _validation())

    assert "hostMembership" in str(exc.value)


def test_validate_fixture_normalizes_real_sidecar_shape():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())

    assert fixture.elements_by_unique_id["uid-door"]["labels"]["hostId"]["value"] == "uid-wall"
    assert fixture.relationships["hostMembership"] == {"uid-door": "uid-wall"}
    assert fixture.relationships["roomMembership"]["uid-wall"] == "room-1"
    assert fixture.relationships["levelMembership"]["uid-door"] == "L1"


def test_validate_fixture_rejects_duplicate_relationship_sources():
    sidecar = _sidecar()
    sidecar["relationships"]["roomMembership"].append(
        {"elementUniqueId": "uid-door", "roomUniqueId": "room-1", "source": "revit_api", "confidence": "high"}
    )
    validation = _validation()
    validation["relationships"]["roomMembership"]["count"] = 3

    with pytest.raises(cal.FixtureValidationError) as exc:
        cal.validate_fixture_payload(sidecar, validation)

    message = str(exc.value)
    assert "roomMembership" in message
    assert "uid-door" in message


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda sidecar: sidecar["relationships"]["hostMembership"].__setitem__(
                0, {**sidecar["relationships"]["hostMembership"][0], "elementUniqueId": "missing-door"}
            ),
            "hostMembership source element missing-door",
        ),
        (
            lambda sidecar: sidecar["relationships"]["hostMembership"].__setitem__(
                0, {**sidecar["relationships"]["hostMembership"][0], "hostUniqueId": "missing-wall"}
            ),
            "hostMembership target host missing-wall",
        ),
        (
            lambda sidecar: sidecar["relationships"]["roomMembership"].__setitem__(
                0, {**sidecar["relationships"]["roomMembership"][0], "elementUniqueId": "missing-door"}
            ),
            "roomMembership source element missing-door",
        ),
        (
            lambda sidecar: sidecar["relationships"]["roomMembership"].__setitem__(
                0, {**sidecar["relationships"]["roomMembership"][0], "roomUniqueId": "missing-room"}
            ),
            "roomMembership target room missing-room",
        ),
        (
            lambda sidecar: sidecar["relationships"]["levelMembership"].__setitem__(
                0, {**sidecar["relationships"]["levelMembership"][0], "elementUniqueId": "missing-door"}
            ),
            "levelMembership source element missing-door",
        ),
        (
            lambda sidecar: sidecar["relationships"]["levelMembership"].__setitem__(
                0, {**sidecar["relationships"]["levelMembership"][0], "levelName": ""}
            ),
            "levelMembership level name",
        ),
    ],
)
def test_validate_fixture_checks_relationship_referential_integrity(mutate, expected):
    sidecar = _sidecar()
    mutate(sidecar)

    with pytest.raises(cal.FixtureValidationError) as exc:
        cal.validate_fixture_payload(sidecar, _validation())

    assert expected in str(exc.value)


def test_validate_fixture_accepts_dict_relationship_maps():
    sidecar = _sidecar()
    sidecar["relationships"] = {
        "hostMembership": {"uid-door": "uid-wall"},
        "roomMembership": {"uid-door": "room-1", "uid-wall": "room-1"},
        "levelMembership": {"uid-door": "L1", "uid-wall": "L1"},
    }

    fixture = cal.validate_fixture_payload(sidecar, _validation())

    assert fixture.relationships == sidecar["relationships"]


def test_validate_fixture_accepts_top_level_unique_id_fallbacks():
    sidecar = _sidecar()
    sidecar["elements"][0].pop("identity")
    sidecar["elements"][0]["uniqueId"] = "uid-wall"
    sidecar["elements"][1].pop("identity")
    sidecar["elements"][1]["revitUniqueId"] = "uid-door"

    fixture = cal.validate_fixture_payload(sidecar, _validation())

    assert set(fixture.elements_by_unique_id) == {"uid-wall", "uid-door"}


def test_build_offline_fixture_validation_report_schema():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())

    report = cal.build_offline_fixture_validation_report(
        fixture,
        paths=cal.FixturePaths(
            model3dm="C:/tmp/shell-preset.3dm",
            sidecar="C:/tmp/shell-preset.sidecar.json",
            validation="C:/tmp/shell-preset.validation.json",
        ),
        fixture_id="shell-preset",
    )

    assert report["schemaVersion"] == 1
    assert report["mode"] == "offline_fixture_validation"
    assert len(report["fixtures"]) == 1
    fx = report["fixtures"][0]
    assert fx["fixtureId"] == "shell-preset"
    assert fx["summary"]["metricsComputed"] is False
    assert fx["summary"]["elementCount"] == 2
    assert fx["summary"]["relationshipIndexes"] == {
        "hostMembership": True,
        "roomMembership": True,
        "levelMembership": True,
    }
    assert fx["metrics"] == {}
    assert fx["candidates"] == []


def test_load_fixture_bundle_reads_three_paths(tmp_path):
    model = tmp_path / "shell-preset.3dm"
    sidecar = tmp_path / "shell-preset.sidecar.json"
    validation = tmp_path / "shell-preset.validation.json"
    model.write_bytes(b"fake-3dm-for-path-validation")
    sidecar.write_text(cal.json_dumps(_sidecar()), encoding="utf-8")
    validation.write_text(cal.json_dumps(_validation()), encoding="utf-8")

    loaded = cal.load_fixture_bundle(
        cal.FixturePaths(str(model), str(sidecar), str(validation))
    )

    assert loaded.fixture.elements_by_unique_id["uid-door"]["category"] == "Doors"
    assert loaded.paths.model3dm == str(model)


def test_load_fixture_bundle_wraps_invalid_sidecar_json(tmp_path):
    model = tmp_path / "shell-preset.3dm"
    sidecar = tmp_path / "shell-preset.sidecar.json"
    validation = tmp_path / "shell-preset.validation.json"
    model.write_bytes(b"fake-3dm-for-path-validation")
    sidecar.write_text("{", encoding="utf-8")
    validation.write_text(cal.json_dumps(_validation()), encoding="utf-8")

    with pytest.raises(cal.FixtureValidationError) as exc:
        cal.load_fixture_bundle(cal.FixturePaths(str(model), str(sidecar), str(validation)))

    assert "sidecar" in str(exc.value)
    assert str(sidecar) in str(exc.value)


def test_load_fixture_bundle_wraps_invalid_validation_json(tmp_path):
    model = tmp_path / "shell-preset.3dm"
    sidecar = tmp_path / "shell-preset.sidecar.json"
    validation = tmp_path / "shell-preset.validation.json"
    model.write_bytes(b"fake-3dm-for-path-validation")
    sidecar.write_text(cal.json_dumps(_sidecar()), encoding="utf-8")
    validation.write_text("{", encoding="utf-8")

    with pytest.raises(cal.FixtureValidationError) as exc:
        cal.load_fixture_bundle(cal.FixturePaths(str(model), str(sidecar), str(validation)))

    assert "validation" in str(exc.value)
    assert str(validation) in str(exc.value)


def _runtime_objects():
    return [
        {
            "runtimeId": "rook-wall",
            "name": "Wall 101",
            "layer": "RookBim::L1::Walls",
            "userStrings": {
                "revit.uniqueId": "uid-wall",
                "revit.elementId": "101",
                "revit.category": "Walls",
            },
        },
        {
            "runtimeId": "rook-door",
            "name": "Door 202",
            "layer": "RookBim::L1::Doors",
            "userStrings": {
                "revit.uniqueId": "uid-door",
                "revit.elementId": "202",
                "revit.category": "Doors",
            },
        },
        {
            "runtimeId": "unjoined-box",
            "name": "No Revit Key",
            "layer": "Default",
            "userStrings": {},
        },
    ]


def test_build_runtime_join_map_by_revit_unique_id():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())

    join = cal.build_runtime_join_map(_runtime_objects(), fixture)

    assert join.by_runtime_id["rook-door"].revit_unique_id == "uid-door"
    assert join.by_runtime_id["rook-door"].element["category"] == "Doors"
    assert join.not_joinable["unjoined-box"] == "missing_revit_unique_id"


def test_build_candidate_records_join_endpoints_and_preserve_runtime_verdict():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    refinement = {
        "success": True,
        "graphSequence": 9,
        "refined": [
            {
                "candidateId": "rook-wall|contains|rook-door",
                "containerId": "rook-wall",
                "containedId": "rook-door",
                "verdict": "contains_semantic",
                "confidence": "high",
                "reason": "strong_clearance_plausible_container",
                "evidence": [{"signal": "bbox_margin", "polarity": "supports", "detail": "positive"}],
            }
        ],
    }

    candidates = cal.build_candidate_records(refinement, join, fixture)

    assert len(candidates) == 1
    c = candidates[0]
    assert c["candidateId"] == "rook-wall|contains|rook-door"
    assert c["container"]["revitUniqueId"] == "uid-wall"
    assert c["contained"]["revitUniqueId"] == "uid-door"
    assert c["rook"]["verdict"] == "contains_semantic"
    assert c["rook"]["confidence"] == "high"
