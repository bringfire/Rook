from pathlib import Path

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
