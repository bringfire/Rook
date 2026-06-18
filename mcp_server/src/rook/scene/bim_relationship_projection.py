from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from .scene_graph import SceneGraphAnalytics

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


@dataclass(frozen=True)
class RuntimeObjectRecord:
    object_id: str
    user_strings: dict[str, Any]


@dataclass(frozen=True)
class JoinedRuntimeObject:
    object_id: str
    revit_unique_id: str
    revit_element_id: str
    revit_category: str


@dataclass(frozen=True)
class RuntimeJoinMap:
    by_object_id: dict[str, JoinedRuntimeObject]
    by_revit_uid: dict[str, JoinedRuntimeObject]
    diagnostics: dict[str, int]


@dataclass(frozen=True)
class EligibleObjects:
    object_ids: set[str]
    revit_uids: set[str]
    diagnostics: dict[str, int]


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


def _collision_resistant_id_segment(value: str) -> str:
    return f"{normalize_id_segment(value)}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def build_runtime_join_map(records: list[RuntimeObjectRecord]) -> RuntimeJoinMap:
    by_object_id: dict[str, JoinedRuntimeObject] = {}
    diagnostics: dict[str, int] = {}

    for record in records:
        uid = _clean_str(record.user_strings.get("revit.uniqueId"))
        if not uid:
            _bump(diagnostics, "objectsMissingRevitUniqueId")
            continue
        if record.object_id in by_object_id:
            _bump(diagnostics, "duplicateRuntimeObjectIds")
        joined = JoinedRuntimeObject(
            object_id=record.object_id,
            revit_unique_id=uid,
            revit_element_id=_clean_str(record.user_strings.get("revit.elementId")),
            revit_category=_clean_str(record.user_strings.get("revit.category")),
        )
        by_object_id[record.object_id] = joined

    by_revit_uid: dict[str, JoinedRuntimeObject] = {}
    for joined in by_object_id.values():
        if joined.revit_unique_id in by_revit_uid:
            _bump(diagnostics, "duplicateRuntimeRevitUniqueIds")
        by_revit_uid[joined.revit_unique_id] = joined

    return RuntimeJoinMap(by_object_id=by_object_id, by_revit_uid=by_revit_uid, diagnostics=diagnostics)


def _category_matches(joined: JoinedRuntimeObject, sidecar: ParsedSidecar, filters: set[str]) -> bool:
    if not filters:
        return True
    element = sidecar.elements_by_uid.get(joined.revit_unique_id)
    candidates = {
        joined.revit_category.strip().lower(),
        (element.category.strip().lower() if element else ""),
    }
    return any(candidate in filters for candidate in candidates if candidate)


def select_eligible_objects(
    join: RuntimeJoinMap,
    sidecar: ParsedSidecar,
    *,
    object_ids: list[str] | None = None,
    category_filters: list[str] | None = None,
) -> EligibleObjects:
    requested = set(join.by_object_id.keys()) if object_ids is None else set(object_ids)
    filters = {item.strip().lower() for item in (category_filters or []) if item and item.strip()}
    diagnostics: dict[str, int] = {}
    object_out: set[str] = set()
    uid_out: set[str] = set()

    for object_id in requested:
        joined = join.by_object_id.get(object_id)
        if joined is None:
            _bump(diagnostics, "requestedObjectNotJoinable")
            continue
        if joined.revit_unique_id not in sidecar.elements_by_uid:
            _bump(diagnostics, "joinedObjectMissingFromSidecar")
            continue
        if not _category_matches(joined, sidecar, filters):
            _bump(diagnostics, "filteredByCategory")
            continue
        object_out.add(object_id)
        uid_out.add(joined.revit_unique_id)

    return EligibleObjects(object_ids=object_out, revit_uids=uid_out, diagnostics=diagnostics)


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


def _base_projection_attrs(
    sidecar: ParsedSidecar,
    fingerprint: SidecarFingerprint,
    analytics: SceneGraphAnalytics,
) -> dict[str, Any]:
    return {
        "projectionKind": PROJECTION_KIND,
        "provenance": PROVENANCE,
        "rookbimSidecarFingerprint": fingerprint.short_id,
        "rookbimSidecarPath": sidecar.source_path,
        "rookbimGraphSequence": analytics.sequence,
        "rookbimEngineVersion": ENGINE_VERSION,
    }


def room_node_id(fingerprint: SidecarFingerprint, room_uid: str) -> str:
    return f"rookbim:{fingerprint.short_id}:room:{_collision_resistant_id_segment(room_uid)}"


def level_node_id(fingerprint: SidecarFingerprint, level_name: str) -> str:
    return f"rookbim:{fingerprint.short_id}:level:{_collision_resistant_id_segment(level_name)}"


def host_edge_key(fingerprint: SidecarFingerprint, element_uid: str, host_uid: str) -> str:
    return (
        f"rookbim:hosted_by:{fingerprint.short_id}:"
        f"{element_uid}:{host_uid}"
    )


def room_edge_key(fingerprint: SidecarFingerprint, element_uid: str, room_uid: str) -> str:
    return (
        f"rookbim:in_room:{fingerprint.short_id}:"
        f"{element_uid}:{room_uid}"
    )


def level_edge_key(fingerprint: SidecarFingerprint, element_uid: str, level_name: str) -> str:
    return (
        f"rookbim:on_level:{fingerprint.short_id}:"
        f"{element_uid}:{_collision_resistant_id_segment(level_name)}"
    )


def _annotate_joined_node(
    graph: nx.MultiDiGraph,
    object_id: str,
    joined: JoinedRuntimeObject,
    element: BimElement,
    base_attrs: dict[str, Any],
) -> bool:
    if not graph.has_node(object_id):
        return False
    graph.nodes[object_id].update({
        **base_attrs,
        "rookbimJoined": True,
        "revitUniqueId": joined.revit_unique_id,
        "revitElementId": joined.revit_element_id or element.element_id,
        "revitCategory": joined.revit_category or element.category,
        "revitFamily": element.family,
        "revitType": element.type_name,
        "revitName": element.name,
        "revitLevel": element.level,
    })
    return True


def _ensure_room_node(
    graph: nx.MultiDiGraph,
    sidecar: ParsedSidecar,
    fingerprint: SidecarFingerprint,
    room_uid: str,
    base_attrs: dict[str, Any],
    diagnostics: dict[str, int],
) -> tuple[str, bool]:
    node_id = room_node_id(fingerprint, room_uid)
    created = not graph.has_node(node_id)
    room = sidecar.rooms_by_uid.get(room_uid)
    if room is None:
        _bump(diagnostics, "roomReferenceMissingRecord")
        display_name = _room_display_name("", "", room_uid)
        attrs = {
            "id": node_id,
            "nodeKind": "rookbim_room",
            "roomUniqueId": room_uid,
            "displayName": display_name,
            "name": display_name,
            "domain_label": "room",
            "shape_class": "bim-reference",
            "recordCompleteness": "sparse",
        }
    else:
        attrs = {
            "id": node_id,
            "nodeKind": "rookbim_room",
            "roomUniqueId": room.unique_id,
            "roomNumber": room.room_number,
            "roomName": room.room_name,
            "displayName": room.display_name,
            "name": room.display_name,
            "domain_label": "room",
            "shape_class": "bim-reference",
            "recordCompleteness": room.completeness,
        }
    graph.add_node(node_id, **base_attrs, **attrs)
    return node_id, created


def _ensure_level_node(
    graph: nx.MultiDiGraph,
    fingerprint: SidecarFingerprint,
    level_name: str,
    base_attrs: dict[str, Any],
) -> tuple[str, bool]:
    node_id = level_node_id(fingerprint, level_name)
    created = not graph.has_node(node_id)
    graph.add_node(
        node_id,
        **base_attrs,
        id=node_id,
        nodeKind="rookbim_level",
        levelName=level_name,
        displayName=level_name,
        name=level_name,
        domain_label="level",
        shape_class="bim-reference",
        recordCompleteness="sparse",
    )
    return node_id, created


def _edge_attrs(
    relationship: str,
    membership: BimMembership,
    base_attrs: dict[str, Any],
) -> dict[str, Any]:
    return {
        **base_attrs,
        "relationship": relationship,
        "source": membership.source,
        "confidence": membership.confidence,
    }


def _merge_diagnostics(*sources: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in sources:
        for key, count in source.items():
            merged[key] = merged.get(key, 0) + count
    return merged


def project_bim_relationships(
    analytics: SceneGraphAnalytics,
    sidecar: ParsedSidecar,
    fingerprint: SidecarFingerprint,
    join: RuntimeJoinMap,
    eligible: EligibleObjects,
    *,
    include_rooms: bool = True,
    include_levels: bool = True,
) -> dict[str, Any]:
    graph = analytics.graph
    base_attrs = _base_projection_attrs(sidecar, fingerprint, analytics)
    diagnostics = _merge_diagnostics(sidecar.diagnostics, join.diagnostics, eligible.diagnostics)
    counts = {
        "eligibleObjectCount": len(eligible.object_ids),
        "annotatedObjectCount": 0,
        "projectedHostEdges": 0,
        "projectedRoomEdges": 0,
        "projectedLevelEdges": 0,
        "roomNodes": 0,
        "createdRoomNodes": 0,
        "levelNodes": 0,
        "createdLevelNodes": 0,
    }

    for object_id in sorted(eligible.object_ids):
        joined = join.by_object_id.get(object_id)
        if joined is None:
            _bump(diagnostics, "eligibleObjectMissingJoin")
            continue
        element = sidecar.elements_by_uid.get(joined.revit_unique_id)
        if element is None:
            _bump(diagnostics, "eligibleObjectMissingElement")
            continue
        if _annotate_joined_node(graph, object_id, joined, element, base_attrs):
            counts["annotatedObjectCount"] += 1
        else:
            _bump(diagnostics, "eligibleObjectMissingSceneNode")

    touched_room_nodes: set[str] = set()
    touched_level_nodes: set[str] = set()

    for membership in sidecar.host_memberships:
        if membership.element_uid not in eligible.revit_uids:
            continue
        element_join = join.by_revit_uid.get(membership.element_uid)
        host_join = join.by_revit_uid.get(membership.target_uid)
        if element_join is None:
            _bump(diagnostics, "hostMembershipElementNotJoined")
            continue
        if host_join is None:
            _bump(diagnostics, "hostMembershipHostNotJoined")
            continue
        if not graph.has_node(element_join.object_id):
            _bump(diagnostics, "hostMembershipElementMissingSceneNode")
            continue
        if not graph.has_node(host_join.object_id):
            _bump(diagnostics, "hostMembershipHostMissingSceneNode")
            continue
        graph.add_edge(
            element_join.object_id,
            host_join.object_id,
            key=host_edge_key(fingerprint, membership.element_uid, membership.target_uid),
            **_edge_attrs(REL_HOSTED_BY, membership, base_attrs),
            revitElementUniqueId=membership.element_uid,
            revitHostUniqueId=membership.target_uid,
        )
        counts["projectedHostEdges"] += 1

    if include_rooms:
        for membership in sidecar.room_memberships:
            if membership.element_uid not in eligible.revit_uids:
                continue
            element_join = join.by_revit_uid.get(membership.element_uid)
            if element_join is None:
                _bump(diagnostics, "roomMembershipElementNotJoined")
                continue
            if not graph.has_node(element_join.object_id):
                _bump(diagnostics, "roomMembershipElementMissingSceneNode")
                continue
            node_id, created = _ensure_room_node(
                graph,
                sidecar,
                fingerprint,
                membership.target_uid,
                base_attrs,
                diagnostics,
            )
            touched_room_nodes.add(node_id)
            if created:
                counts["createdRoomNodes"] += 1
            graph.add_edge(
                element_join.object_id,
                node_id,
                key=room_edge_key(fingerprint, membership.element_uid, membership.target_uid),
                **_edge_attrs(REL_IN_ROOM, membership, base_attrs),
                revitElementUniqueId=membership.element_uid,
                roomUniqueId=membership.target_uid,
            )
            counts["projectedRoomEdges"] += 1

    if include_levels:
        for membership in sidecar.level_memberships:
            if membership.element_uid not in eligible.revit_uids:
                continue
            element_join = join.by_revit_uid.get(membership.element_uid)
            if element_join is None:
                _bump(diagnostics, "levelMembershipElementNotJoined")
                continue
            if not graph.has_node(element_join.object_id):
                _bump(diagnostics, "levelMembershipElementMissingSceneNode")
                continue
            node_id, created = _ensure_level_node(
                graph,
                fingerprint,
                membership.target_uid,
                base_attrs,
            )
            touched_level_nodes.add(node_id)
            if created:
                counts["createdLevelNodes"] += 1
            graph.add_edge(
                element_join.object_id,
                node_id,
                key=level_edge_key(fingerprint, membership.element_uid, membership.target_uid),
                **_edge_attrs(REL_ON_LEVEL, membership, base_attrs),
                revitElementUniqueId=membership.element_uid,
                levelName=membership.target_uid,
            )
            counts["projectedLevelEdges"] += 1

    counts["roomNodes"] = len(touched_room_nodes)
    counts["levelNodes"] = len(touched_level_nodes)
    analytics._invalidate_caches()

    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "fingerprint": fingerprint.short_id,
        "counts": counts,
        "diagnostics": diagnostics,
    }
