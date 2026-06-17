"""Offline calibration fixture parsing and report schema helpers.

Revit sidecar labels and relationship indexes are post-hoc evaluation data for
calibration only. This module intentionally does not call runtime scene graph
projection, containment refinement, or mutation paths.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MODE_LIVE = "live_threshold_calibration"
MODE_OFFLINE = "offline_fixture_validation"
REQUIRED_RELATIONSHIPS = (
    "hostMembership",
    "roomMembership",
    "levelMembership",
)

_RELATIONSHIP_VALUE_KEYS = {
    "hostMembership": "hostUniqueId",
    "roomMembership": "roomUniqueId",
    "levelMembership": "levelName",
}


class FixtureValidationError(ValueError):
    """Raised when a calibration fixture bundle is missing required data."""


@dataclass(frozen=True)
class FixturePaths:
    model3dm: str
    sidecar: str
    validation: str


@dataclass(frozen=True)
class FixtureData:
    sidecar: dict[str, Any]
    validation: dict[str, Any]
    elements_by_unique_id: dict[str, dict[str, Any]]
    relationships: dict[str, dict[str, Any]]
    rooms_by_unique_id: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class LoadedFixture:
    paths: FixturePaths
    fixture: FixtureData


def json_dumps(value: Any) -> str:
    """Serialize fixture JSON consistently for tests and report artifacts."""
    return json.dumps(value, indent=2, sort_keys=True)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixtureValidationError(f"{name} must be an object")
    return value


def validate_fixture_payload(
    sidecar_payload: dict[str, Any],
    validation_payload: dict[str, Any],
) -> FixtureData:
    """Validate and normalize the Revit fixture sidecar and validation payloads."""
    sidecar = _require_dict(sidecar_payload, "sidecar")
    validation = _require_dict(validation_payload, "validation")

    elements = sidecar.get("elements")
    if not isinstance(elements, list):
        raise FixtureValidationError("sidecar.elements must be a list")

    elements_by_unique_id: dict[str, dict[str, Any]] = {}
    for index, element in enumerate(elements):
        element_dict = _require_dict(element, f"sidecar.elements[{index}]")
        unique_id = _element_unique_id(element_dict)
        if not unique_id:
            raise FixtureValidationError(f"sidecar.elements[{index}] is missing a unique id")
        if unique_id in elements_by_unique_id:
            raise FixtureValidationError(f"duplicate element unique id: {unique_id}")
        elements_by_unique_id[unique_id] = element_dict

    rooms = sidecar.get("rooms", [])
    if rooms is None:
        rooms = []
    if not isinstance(rooms, list):
        raise FixtureValidationError("sidecar.rooms must be a list when present")

    rooms_by_unique_id: dict[str, dict[str, Any]] = {}
    for index, room in enumerate(rooms):
        room_dict = _require_dict(room, f"sidecar.rooms[{index}]")
        unique_id = room_dict.get("uniqueId")
        if isinstance(unique_id, str) and unique_id:
            rooms_by_unique_id[unique_id] = room_dict

    relationships = _normalize_relationships(sidecar)
    _validate_relationship_integrity(
        relationships,
        elements_by_unique_id=elements_by_unique_id,
        rooms_by_unique_id=rooms_by_unique_id,
    )
    _validate_relationship_counts(relationships, validation)

    return FixtureData(
        sidecar=sidecar,
        validation=validation,
        elements_by_unique_id=elements_by_unique_id,
        relationships=relationships,
        rooms_by_unique_id=rooms_by_unique_id,
    )


def _element_unique_id(element: dict[str, Any]) -> str | None:
    identity = element.get("identity")
    if isinstance(identity, dict):
        unique_id = identity.get("uniqueId")
        if isinstance(unique_id, str) and unique_id:
            return unique_id

    for key in ("uniqueId", "revitUniqueId"):
        unique_id = element.get(key)
        if isinstance(unique_id, str) and unique_id:
            return unique_id

    return None


def _normalize_relationships(sidecar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    relationships = _require_dict(sidecar.get("relationships"), "sidecar.relationships")
    normalized: dict[str, dict[str, Any]] = {}

    for relationship_name in REQUIRED_RELATIONSHIPS:
        if relationship_name not in relationships:
            raise FixtureValidationError(f"sidecar.relationships.{relationship_name} is required")
        normalized[relationship_name] = _normalize_membership(
            relationships[relationship_name],
            relationship_name=relationship_name,
            value_key=_RELATIONSHIP_VALUE_KEYS[relationship_name],
        )

    return normalized


def _normalize_membership(
    membership: Any,
    *,
    relationship_name: str,
    value_key: str,
) -> dict[str, Any]:
    if isinstance(membership, dict):
        return dict(membership)

    if not isinstance(membership, list):
        raise FixtureValidationError(f"sidecar.relationships.{relationship_name} must be a list or object")

    normalized: dict[str, Any] = {}
    for index, record in enumerate(membership):
        record_dict = _require_dict(
            record,
            f"sidecar.relationships.{relationship_name}[{index}]",
        )
        element_unique_id = record_dict.get("elementUniqueId")
        value = record_dict.get(value_key)
        if not element_unique_id:
            raise FixtureValidationError(
                f"sidecar.relationships.{relationship_name}[{index}] is missing elementUniqueId"
            )
        if value is None:
            continue
        element_key = str(element_unique_id)
        if element_key in normalized:
            raise FixtureValidationError(
                f"duplicate {relationship_name} relationship for element {element_key}"
            )
        normalized[element_key] = value

    return normalized


def _validate_relationship_integrity(
    relationships: dict[str, dict[str, Any]],
    *,
    elements_by_unique_id: dict[str, dict[str, Any]],
    rooms_by_unique_id: dict[str, dict[str, Any]],
) -> None:
    for element_unique_id, host_unique_id in relationships["hostMembership"].items():
        _require_known_element("hostMembership", "source element", element_unique_id, elements_by_unique_id)
        _require_known_element("hostMembership", "target host", host_unique_id, elements_by_unique_id)

    for element_unique_id, room_unique_id in relationships["roomMembership"].items():
        _require_known_element("roomMembership", "source element", element_unique_id, elements_by_unique_id)
        if room_unique_id not in rooms_by_unique_id:
            raise FixtureValidationError(f"roomMembership target room {room_unique_id} is not in rooms")

    for element_unique_id, level_name in relationships["levelMembership"].items():
        _require_known_element("levelMembership", "source element", element_unique_id, elements_by_unique_id)
        if not isinstance(level_name, str) or not level_name:
            raise FixtureValidationError(
                f"levelMembership level name for element {element_unique_id} must be a non-empty string"
            )


def _require_known_element(
    relationship_name: str,
    role: str,
    unique_id: Any,
    elements_by_unique_id: dict[str, dict[str, Any]],
) -> None:
    if unique_id not in elements_by_unique_id:
        raise FixtureValidationError(f"{relationship_name} {role} {unique_id} is not in elements")


def _validate_relationship_counts(
    relationships: dict[str, dict[str, Any]],
    validation: dict[str, Any],
) -> None:
    validation_relationships = validation.get("relationships")
    if validation_relationships is None:
        return
    if not isinstance(validation_relationships, dict):
        raise FixtureValidationError("validation.relationships must be an object when present")

    for relationship_name in REQUIRED_RELATIONSHIPS:
        validation_record = validation_relationships.get(relationship_name)
        if validation_record is None:
            continue
        if not isinstance(validation_record, dict):
            raise FixtureValidationError(f"validation.relationships.{relationship_name} must be an object")
        expected_count = validation_record.get("count")
        if expected_count is None:
            continue
        if expected_count != len(relationships[relationship_name]):
            raise FixtureValidationError(
                f"{relationship_name} count mismatch: validation has "
                f"{expected_count}, sidecar has {len(relationships[relationship_name])}"
            )


def load_fixture_bundle(paths: FixturePaths) -> LoadedFixture:
    """Read and validate a 3dm/sidecar/validation fixture bundle."""
    model_path = Path(paths.model3dm)
    sidecar_path = Path(paths.sidecar)
    validation_path = Path(paths.validation)

    for name, path in (
        ("model3dm", model_path),
        ("sidecar", sidecar_path),
        ("validation", validation_path),
    ):
        if not path.exists():
            raise FixtureValidationError(f"{name} path does not exist: {path}")

    sidecar = _read_json_file(sidecar_path, "sidecar")
    validation = _read_json_file(validation_path, "validation")
    fixture = validate_fixture_payload(sidecar, validation)
    return LoadedFixture(paths=paths, fixture=fixture)


def _read_json_file(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureValidationError(f"invalid {label} JSON at {path}: {exc}") from exc


def build_offline_fixture_validation_report(
    fixture: FixtureData,
    *,
    paths: FixturePaths,
    fixture_id: str,
) -> dict[str, Any]:
    """Build the offline report envelope before runtime metrics are computed."""
    relationship_indexes = {
        name: name in fixture.relationships
        for name in REQUIRED_RELATIONSHIPS
    }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": MODE_OFFLINE,
        "generatedAt": _utc_now_iso(),
        "fixtures": [
            {
                "fixtureId": fixture_id,
                "paths": {
                    "model3dm": paths.model3dm,
                    "sidecar": paths.sidecar,
                    "validation": paths.validation,
                },
                "summary": {
                    "metricsComputed": False,
                    "elementCount": len(fixture.elements_by_unique_id),
                    "roomCount": len(fixture.rooms_by_unique_id),
                    "relationshipIndexes": relationship_indexes,
                },
                "metrics": {},
                "candidates": [],
            }
        ],
    }
