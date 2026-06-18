from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECTION_KIND = "bim_relationship_v1"
PROVENANCE = "rookbim_sidecar"
REL_HOSTED_BY = "revit_hosted_by"
REL_IN_ROOM = "revit_in_room"
REL_ON_LEVEL = "revit_on_level"
ENGINE_VERSION = 1

NODE_ATTRS = (
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
    "revitRoomUniqueId",
    "revitHostUniqueId",
)


class BimProjectionValidationError(ValueError):
    """Raised when the sidecar shape is not valid for BIM relationship projection."""


@dataclass(frozen=True)
class SidecarFingerprint:
    full_hash: str
    short_id: str


@dataclass(frozen=True)
class BimElement:
    unique_id: str
    element_id: str
    category: str
    family: str
    type_name: str
    name: str
    level: str
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class BimRoom:
    unique_id: str
    room_number: str
    room_name: str
    display_name: str
    completeness: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class BimMembership:
    element_uid: str
    target_uid: str
    source: str
    confidence: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ParsedSidecar:
    schema_version: int | None
    source_path: str
    elements_by_uid: dict[str, BimElement]
    rooms_by_uid: dict[str, BimRoom]
    host_memberships: list[BimMembership]
    room_memberships: list[BimMembership]
    level_memberships: list[BimMembership]
    raw: dict[str, Any] = field(repr=False)
    diagnostics: dict[str, int] = field(default_factory=dict)


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _label_value(labels: dict[str, Any], name: str) -> str:
    entry = labels.get(name)
    if isinstance(entry, dict):
        value = entry.get("value")
        return "" if value is None else str(value)
    return "" if entry is None else str(entry)


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _room_display_name(number: str, name: str, fallback_uid: str) -> str:
    if number and name:
        return f"{number} {name}"
    if number:
        return number
    if name:
        return name
    return f"Room {fallback_uid[:8]}"


def normalize_id_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "unnamed"


def fingerprint_sidecar_path(path: str | Path) -> SidecarFingerprint:
    data = Path(path).read_bytes()
    full_hash = hashlib.sha256(data).hexdigest()
    return SidecarFingerprint(full_hash=full_hash, short_id=full_hash[:16])


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise BimProjectionValidationError(f"sidecar field {key!r} must be a list")
    return value


def _require_relationship_list(relationships: dict[str, Any], key: str) -> list[Any]:
    value = relationships.get(key)
    if not isinstance(value, list):
        raise BimProjectionValidationError(f"relationships.{key} must be a list")
    return value


def parse_sidecar_payload(
    payload: dict[str, Any],
    *,
    source_path: str = "",
    include_rooms: bool = True,
    include_levels: bool = True,
) -> ParsedSidecar:
    if not isinstance(payload, dict):
        raise BimProjectionValidationError("sidecar root must be an object")
    schema_version = payload.get("schemaVersion")
    if schema_version is not None and type(schema_version) is not int:
        raise BimProjectionValidationError("sidecar field 'schemaVersion' must be an integer or null")

    elements = _require_list(payload, "elements")
    relationships = payload.get("relationships")
    if not isinstance(relationships, dict):
        raise BimProjectionValidationError("sidecar field 'relationships' must be an object")

    host_records = _require_relationship_list(relationships, "hostMembership")
    room_records = _require_relationship_list(relationships, "roomMembership") if include_rooms else []
    level_records = _require_relationship_list(relationships, "levelMembership") if include_levels else []

    diagnostics: dict[str, int] = {}
    elements_by_uid: dict[str, BimElement] = {}
    for record in elements:
        if not isinstance(record, dict):
            _bump(diagnostics, "malformedElementRecords")
            continue
        identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
        uid = _clean_str(identity.get("uniqueId") or record.get("uniqueId") or record.get("revitUniqueId"))
        if not uid:
            _bump(diagnostics, "elementsMissingUniqueId")
            continue
        if uid in elements_by_uid:
            _bump(diagnostics, "duplicateElements")
        labels = record.get("labels") if isinstance(record.get("labels"), dict) else {}
        elements_by_uid[uid] = BimElement(
            unique_id=uid,
            element_id=_clean_str(identity.get("elementId") or record.get("elementId")),
            category=_clean_str(record.get("category")),
            family=_clean_str(record.get("family")),
            type_name=_clean_str(record.get("type")),
            name=_clean_str(record.get("name")),
            level=_label_value(labels, "level"),
            raw=record,
        )

    rooms_by_uid: dict[str, BimRoom] = {}
    rooms = payload.get("rooms", [])
    if "rooms" in payload and not isinstance(rooms, list):
        raise BimProjectionValidationError("sidecar field 'rooms' must be a list when present")
    if isinstance(rooms, list):
        for record in rooms:
            if not isinstance(record, dict):
                _bump(diagnostics, "malformedRoomRecords")
                continue
            uid = _clean_str(record.get("uniqueId") or record.get("roomId"))
            if not uid:
                _bump(diagnostics, "roomsMissingUniqueId")
                continue
            if uid in rooms_by_uid:
                _bump(diagnostics, "duplicateRooms")
            number = _clean_str(record.get("number"))
            name = _clean_str(record.get("name"))
            rooms_by_uid[uid] = BimRoom(
                unique_id=uid,
                room_number=number,
                room_name=name,
                display_name=_room_display_name(number, name, uid),
                completeness="complete",
                raw=record,
            )

    return ParsedSidecar(
        schema_version=schema_version,
        source_path=source_path,
        elements_by_uid=elements_by_uid,
        rooms_by_uid=rooms_by_uid,
        host_memberships=_parse_memberships(host_records, "hostUniqueId", "hostMembership", diagnostics),
        room_memberships=_parse_memberships(room_records, "roomUniqueId", "roomMembership", diagnostics),
        level_memberships=_parse_memberships(level_records, "levelName", "levelMembership", diagnostics),
        raw=payload,
        diagnostics=diagnostics,
    )


def _parse_memberships(
    records: list[Any],
    target_key: str,
    diagnostic_prefix: str,
    diagnostics: dict[str, int],
) -> list[BimMembership]:
    out: list[BimMembership] = []
    for record in records:
        if not isinstance(record, dict):
            _bump(diagnostics, f"malformed{diagnostic_prefix[0].upper()}{diagnostic_prefix[1:]}Records")
            continue
        element_uid = _clean_str(record.get("elementUniqueId"))
        target_uid = _clean_str(record.get(target_key))
        if not element_uid:
            _bump(diagnostics, f"{diagnostic_prefix}MissingElementUniqueId")
            continue
        if not target_uid:
            _bump(diagnostics, f"{diagnostic_prefix}MissingTarget")
            continue
        out.append(
            BimMembership(
                element_uid=element_uid,
                target_uid=target_uid,
                source=_clean_str(record.get("source")),
                confidence=_clean_str(record.get("confidence")),
                raw=record,
            )
        )
    return out


def load_sidecar_path(
    sidecar_path: str | Path,
    *,
    include_rooms: bool = True,
    include_levels: bool = True,
) -> tuple[ParsedSidecar, SidecarFingerprint]:
    path = Path(sidecar_path)
    if not path.is_file():
        raise BimProjectionValidationError(f"sidecar_path is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BimProjectionValidationError(f"sidecar JSON is invalid: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BimProjectionValidationError("sidecar root must be an object")
    return (
        parse_sidecar_payload(
            payload,
            source_path=str(path),
            include_rooms=include_rooms,
            include_levels=include_levels,
        ),
        fingerprint_sidecar_path(path),
    )
