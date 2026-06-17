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
        normalized[str(element_unique_id)] = value

    return normalized


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

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    fixture = validate_fixture_payload(sidecar, validation)
    return LoadedFixture(paths=paths, fixture=fixture)


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
