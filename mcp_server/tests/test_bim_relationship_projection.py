import json

import pytest

from rook.scene import bim_relationship_projection as bim


def _sidecar() -> dict:
    return {
        "schemaVersion": 1,
        "elements": [
            {
                "identity": {
                    "uniqueId": "uid-wall",
                    "elementId": 100,
                    "documentTitle": "Model A",
                },
                "category": "Walls",
                "family": "Basic Wall",
                "type": "Generic 200mm",
                "name": "Wall Type",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high"},
                    "hostId": {"value": None, "source": "unavailable", "confidence": None},
                    "containingRoomId": {"value": None, "source": "unavailable", "confidence": None},
                },
            },
            {
                "identity": {
                    "uniqueId": "uid-door",
                    "elementId": 200,
                    "documentTitle": "Model A",
                },
                "category": "Doors",
                "family": "Single-Flush",
                "type": "0915 x 2134mm",
                "name": "Door Type",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high"},
                    "hostId": {"value": 100, "source": "revit_api", "confidence": "high"},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high"},
                },
            },
        ],
        "rooms": [
            {
                "uniqueId": "room-1",
                "roomId": "room-1",
                "number": "101",
                "name": "Office",
                "geometryRepresentation": "room_mesh",
                "referenceGeometry": True,
            }
        ],
        "relationships": {
            "hostMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "hostUniqueId": "uid-wall",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "roomMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "roomUniqueId": "room-1",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "levelMembership": [
                {
                    "elementUniqueId": "uid-wall",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
                {
                    "elementUniqueId": "uid-door",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
            ],
        },
    }


def test_module_constants():
    assert bim.PROJECTION_KIND == "bim_relationship_v1"
    assert bim.PROVENANCE == "rookbim_sidecar"
    assert bim.REL_HOSTED_BY == "revit_hosted_by"
    assert bim.REL_IN_ROOM == "revit_in_room"
    assert bim.REL_ON_LEVEL == "revit_on_level"
    assert bim.ENGINE_VERSION == 1


def test_node_attrs_include_bim_projection_annotations():
    assert {
        "rookbimJoined",
        "rookbimSidecarFingerprint",
        "rookbimSidecarPath",
        "rookbimGraphSequence",
        "revitUniqueId",
        "revitElementId",
        "revitCategory",
        "revitFamily",
        "revitType",
        "revitName",
        "revitLevel",
    }.issubset(set(bim.NODE_ATTRS))


def test_parse_sidecar_payload_normalizes_real_export_shape():
    sidecar = bim.parse_sidecar_payload(_sidecar(), source_path="C:/tmp/shell.sidecar.json")

    assert sidecar.schema_version == 1
    assert sidecar.source_path == "C:/tmp/shell.sidecar.json"
    assert set(sidecar.elements_by_uid) == {"uid-wall", "uid-door"}
    assert sidecar.elements_by_uid["uid-door"].category == "Doors"
    assert sidecar.elements_by_uid["uid-door"].element_id == "200"
    assert sidecar.elements_by_uid["uid-door"].family == "Single-Flush"
    assert sidecar.elements_by_uid["uid-door"].type_name == "0915 x 2134mm"
    assert sidecar.elements_by_uid["uid-door"].name == "Door Type"
    assert sidecar.elements_by_uid["uid-door"].level == "L1"
    assert sidecar.rooms_by_uid["room-1"].display_name == "101 Office"
    assert sidecar.host_memberships[0].element_uid == "uid-door"
    assert sidecar.host_memberships[0].target_uid == "uid-wall"
    assert sidecar.room_memberships[0].target_uid == "room-1"
    assert sidecar.level_memberships[0].target_uid == "L1"


def test_parse_sidecar_payload_requires_object_root():
    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload([])

    assert "root" in str(exc.value)


def test_parse_sidecar_payload_requires_integer_or_null_schema_version():
    payload = _sidecar()
    payload["schemaVersion"] = "1"

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload)

    assert "schemaVersion" in str(exc.value)


def test_parse_sidecar_payload_rejects_boolean_schema_version():
    payload = _sidecar()
    payload["schemaVersion"] = True

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload)

    assert "schemaVersion" in str(exc.value)


def test_parse_sidecar_payload_requires_enabled_sections():
    payload = _sidecar()
    del payload["relationships"]["roomMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "roomMembership" in str(exc.value)


def test_parse_sidecar_payload_requires_host_membership():
    payload = _sidecar()
    del payload["relationships"]["hostMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "hostMembership" in str(exc.value)


def test_parse_sidecar_payload_requires_enabled_level_section():
    payload = _sidecar()
    del payload["relationships"]["levelMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "levelMembership" in str(exc.value)


def test_parse_sidecar_payload_allows_disabled_room_section():
    payload = _sidecar()
    del payload["relationships"]["roomMembership"]

    sidecar = bim.parse_sidecar_payload(payload, include_rooms=False, include_levels=True)

    assert sidecar.room_memberships == []


def test_parse_sidecar_payload_requires_rooms_list_when_present():
    payload = _sidecar()
    payload["rooms"] = {"room-1": {"name": "Office"}}

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload)

    assert "rooms" in str(exc.value)
    assert "list" in str(exc.value)


def test_parse_sidecar_payload_allows_missing_rooms_section():
    payload = _sidecar()
    del payload["rooms"]

    sidecar = bim.parse_sidecar_payload(payload)

    assert sidecar.rooms_by_uid == {}


def test_parse_sidecar_payload_diagnoses_malformed_elements_and_missing_uid():
    payload = _sidecar()
    payload["elements"].extend([
        "not-an-element",
        {"identity": {"elementId": 300}, "category": "Windows"},
    ])

    sidecar = bim.parse_sidecar_payload(payload)

    assert set(sidecar.elements_by_uid) == {"uid-wall", "uid-door"}
    assert sidecar.diagnostics["malformedElementRecords"] == 1
    assert sidecar.diagnostics["elementsMissingUniqueId"] == 1


def test_parse_sidecar_payload_diagnoses_duplicate_elements_last_record_wins():
    payload = _sidecar()
    payload["elements"].append({
        "identity": {"uniqueId": "uid-door", "elementId": 201},
        "category": "Doors",
        "family": "Replacement",
        "type": "Replacement Type",
        "name": "Replacement Door",
        "labels": {"level": {"value": "L2"}},
    })

    sidecar = bim.parse_sidecar_payload(payload)

    assert sidecar.diagnostics["duplicateElements"] == 1
    assert sidecar.elements_by_uid["uid-door"].element_id == "201"
    assert sidecar.elements_by_uid["uid-door"].family == "Replacement"
    assert sidecar.elements_by_uid["uid-door"].level == "L2"


def test_parse_sidecar_payload_diagnoses_malformed_rooms_and_duplicate_rooms():
    payload = _sidecar()
    payload["rooms"].extend([
        "not-a-room",
        {"number": "102", "name": "No Id"},
        {"uniqueId": "room-1", "number": "103", "name": "Replacement"},
    ])

    sidecar = bim.parse_sidecar_payload(payload)

    assert sidecar.diagnostics["malformedRoomRecords"] == 1
    assert sidecar.diagnostics["roomsMissingUniqueId"] == 1
    assert sidecar.diagnostics["duplicateRooms"] == 1
    assert sidecar.rooms_by_uid["room-1"].display_name == "103 Replacement"


def test_parse_sidecar_payload_diagnoses_malformed_and_incomplete_memberships():
    payload = _sidecar()
    payload["relationships"]["hostMembership"].extend([
        "not-a-membership",
        {"hostUniqueId": "uid-wall"},
        {"elementUniqueId": "uid-door"},
    ])

    sidecar = bim.parse_sidecar_payload(payload)

    assert len(sidecar.host_memberships) == 1
    assert sidecar.diagnostics["malformedHostMembershipRecords"] == 1
    assert sidecar.diagnostics["hostMembershipMissingElementUniqueId"] == 1
    assert sidecar.diagnostics["hostMembershipMissingTarget"] == 1


def test_fingerprint_uses_file_content(tmp_path):
    path_a = tmp_path / "a.sidecar.json"
    path_b = tmp_path / "b.sidecar.json"
    path_c = tmp_path / "c.sidecar.json"
    path_a.write_text(json.dumps(_sidecar(), sort_keys=True), encoding="utf-8")
    path_b.write_text(json.dumps(_sidecar(), sort_keys=True), encoding="utf-8")
    changed = _sidecar()
    changed["elements"][0]["category"] = "Modified Walls"
    path_c.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")

    fp_a = bim.fingerprint_sidecar_path(path_a)
    fp_b = bim.fingerprint_sidecar_path(path_b)
    fp_c = bim.fingerprint_sidecar_path(path_c)

    assert fp_a == fp_b
    assert fp_a != fp_c
    assert fp_a.short_id != fp_c.short_id
    assert len(fp_a.short_id) == 16
    assert fp_a.full_hash
