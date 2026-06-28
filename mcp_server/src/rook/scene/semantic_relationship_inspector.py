from __future__ import annotations

from typing import Any


PROJECTION_KIND = "relationship_fact_v1"
VALID_DIRECTIONS = {"both", "outgoing", "incoming"}

CORE_FACT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "contactKind",
    "provenance",
    "confidence",
    "status",
    "graphSource",
    "graphRevision",
    "pose",
)

OPTIONAL_FACT_FIELDS = (
    "semanticRelationshipType",
    "relationshipFactId",
    "sourceMode",
    "relationshipObjectId",
    "fromFeatureObjectId",
    "toFeatureObjectId",
    "engineVersion",
)


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _object_ids_are_valid(object_ids: Any) -> bool:
    return isinstance(object_ids, list) and all(isinstance(object_id, str) for object_id in object_ids)


def _dedupe_object_ids(object_ids: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for object_id in object_ids:
        if object_id in seen:
            continue
        seen.add(object_id)
        result.append(object_id)
    return result


def _node_name(graph: Any, node_id: str) -> str | None:
    attrs = graph.nodes.get(node_id, {})
    value = attrs.get("displayName") or attrs.get("name") or attrs.get("label")
    return str(value) if value else str(node_id)


def _relationship(attrs: dict[str, Any]) -> str | None:
    value = attrs.get("semanticRelationshipType") or attrs.get("relationship")
    return str(value) if value is not None else None


def _projected_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (str(source), str(target), key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
    ]


def _matches_filters(
    attrs: dict[str, Any],
    *,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    relationship_types: list[str] | None,
    status: list[str] | None,
    provenance: list[str] | None,
    diagnostics: dict[str, int],
) -> bool:
    if graph_source is not None and attrs.get("graphSource") != graph_source:
        _bump(diagnostics, "filteredByGraphSource")
        return False
    if graph_revision is not None and attrs.get("graphRevision") != graph_revision:
        _bump(diagnostics, "filteredByGraphRevision")
        return False
    if poses and attrs.get("pose") not in set(poses):
        _bump(diagnostics, "filteredByPose")
        return False
    if relationship_types and _relationship(attrs) not in set(relationship_types):
        _bump(diagnostics, "filteredByRelationshipType")
        return False
    if status and attrs.get("status") not in set(status):
        _bump(diagnostics, "filteredByStatus")
        return False
    if provenance and attrs.get("provenance") not in set(provenance):
        _bump(diagnostics, "filteredByProvenance")
        return False
    return True


def _direction_for(selected_id: str, source_id: str, target_id: str) -> str | None:
    if selected_id == source_id:
        return "outgoing"
    if selected_id == target_id:
        return "incoming"
    return None


def _fact_payload(
    graph: Any,
    *,
    selected_id: str,
    other_id: str,
    direction: str,
    attrs: dict[str, Any],
) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "direction": direction,
        "relationship": _relationship(attrs),
        "objectId": selected_id,
        "otherObjectId": other_id,
        "otherName": _node_name(graph, other_id),
    }
    for field in CORE_FACT_FIELDS:
        if field == "relationship":
            continue
        if field in attrs:
            fact[field] = attrs.get(field)
    for field in OPTIONAL_FACT_FIELDS:
        if field in attrs:
            fact[field] = attrs.get(field)
    return fact


def _line_for_fact(fact: dict[str, Any]) -> str:
    relationship = fact.get("relationship") or "relates to"
    other_name = fact.get("otherName") or fact.get("otherObjectId")
    prefix = (
        f"{relationship} {other_name}"
        if fact.get("direction") == "outgoing"
        else f"connected by {other_name}"
    )
    feature_part = ""
    if fact.get("fromFeature") and fact.get("toFeature"):
        feature_part = f" via {fact['fromFeature']} -> {fact['toFeature']}"
    details = [
        str(value)
        for value in (fact.get("contactKind"), fact.get("status"), fact.get("provenance"))
        if value
    ]
    suffix = f", {', '.join(details)}" if details else ""
    return f"{prefix}{feature_part}{suffix}"


def _empty_entry(graph: Any, object_id: str) -> dict[str, Any]:
    exists = object_id in graph.nodes
    return {
        "objectId": object_id,
        "exists": exists,
        "name": _node_name(graph, object_id) if exists else None,
        "facts": [],
        "lines": [],
    }


def query_semantic_relationships(
    analytics: Any,
    *,
    object_ids: Any,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: list[str] | None = None,
    relationship_types: list[str] | None = None,
    status: list[str] | None = None,
    provenance: list[str] | None = None,
    direction: str = "both",
) -> dict[str, Any]:
    if object_ids is None or object_ids == []:
        return {
            "success": False,
            "error": "missing_object_ids",
            "message": "scene_semantic_relationships requires object_ids in v1",
        }
    if not _object_ids_are_valid(object_ids):
        return {
            "success": False,
            "error": "invalid_object_ids",
            "message": "scene_semantic_relationships requires object_ids to be a list of strings in v1",
        }
    selected_ids = _dedupe_object_ids(object_ids)
    if direction not in VALID_DIRECTIONS:
        return {
            "success": False,
            "error": "invalid_direction",
            "message": "direction must be one of: both, outgoing, incoming",
        }

    graph = analytics.graph
    diagnostics: dict[str, int] = {}
    entries = {object_id: _empty_entry(graph, object_id) for object_id in selected_ids}
    missing_count = sum(1 for entry in entries.values() if not entry["exists"])
    if missing_count:
        diagnostics["missingSelectedObjects"] = missing_count

    projected_edges = _projected_edges(graph)
    if not projected_edges:
        diagnostics["noProjectedRelationshipFacts"] = 1
        diagnostics["projectionRequired"] = 1

    selected_existing = {object_id for object_id, entry in entries.items() if entry["exists"]}
    unique_fact_keys: set[tuple[str, str, Any]] = set()
    relationship_view_count = 0

    for source_id, target_id, key, attrs in projected_edges:
        if not _matches_filters(
            attrs,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            relationship_types=relationship_types,
            status=status,
            provenance=provenance,
            diagnostics=diagnostics,
        ):
            continue
        emitted_for_edge = False
        for selected_id in selected_ids:
            if selected_id not in selected_existing:
                continue
            fact_direction = _direction_for(selected_id, source_id, target_id)
            if fact_direction is None:
                continue
            if direction != "both" and fact_direction != direction:
                _bump(diagnostics, "filteredByDirection")
                continue
            other_id = target_id if fact_direction == "outgoing" else source_id
            fact = _fact_payload(
                graph,
                selected_id=selected_id,
                other_id=other_id,
                direction=fact_direction,
                attrs=attrs,
            )
            entries[selected_id]["facts"].append(fact)
            entries[selected_id]["lines"].append(_line_for_fact(fact))
            relationship_view_count += 1
            emitted_for_edge = True
        if emitted_for_edge:
            unique_fact_keys.add((source_id, target_id, key))

    if projected_edges and relationship_view_count == 0:
        diagnostics["noFactsForSelectedObjects"] = 1

    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "counts": {
            "requestedObjectCount": len(selected_ids),
            "existingSelectedObjectCount": len(selected_existing),
            "missingSelectedObjectCount": missing_count,
            "relationshipFactCount": len(unique_fact_keys),
            "relationshipViewCount": relationship_view_count,
        },
        "objects": [entries[object_id] for object_id in selected_ids],
        "diagnostics": diagnostics,
    }
