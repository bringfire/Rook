from __future__ import annotations

from typing import Any

PROJECTION_KIND = "bim_relationship_v1"
PROVENANCE = "rookbim_sidecar"
REL_HOSTED_BY = "revit_hosted_by"
REL_IN_ROOM = "revit_in_room"
REL_ON_LEVEL = "revit_on_level"
BIM_REFERENCE_NODE_KINDS = {"rookbim_room", "rookbim_level"}

VALID_MODES = {
    "object_context",
    "room_members",
    "level_members",
    "hosted_elements",
    "relationship_scan",
}
VALID_DETAILS = {"ids", "compact", "full"}

MODE_LIMITS = {
    "object_context": (10, 50),
    "room_members": (100, 500),
    "level_members": (100, 500),
    "hosted_elements": (100, 500),
    "relationship_scan": (20, 100),
}

GEOMETRY_ATTR_PREFIXES = ("bbox_",)
GEOMETRY_ATTRS = {
    "max_dim",
    "mid_dim",
    "min_dim",
    "elongation",
    "flatness",
    "thinness",
    "volume",
    "centroid_z",
    "base_z",
    "top_z",
    "primary_axis",
    "thin_axis",
}
RAW_SIDECAR_ATTRS = {
    "rawSidecarPayload",
    "raw_sidecar_payload",
    "revitSidecarPayload",
    "revit_sidecar_payload",
    "rookbimSidecarPayload",
    "rookbim_sidecar_payload",
    "sidecarPayload",
    "sidecar_payload",
    "sidecarRaw",
    "sidecar_raw",
}


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_projected_bim_edge(attrs: dict[str, Any], relationship: str | None = None) -> bool:
    rel = attrs.get("relationship")
    if relationship is not None and rel != relationship:
        return False
    return (
        attrs.get("projectionKind") == PROJECTION_KIND
        and attrs.get("provenance") == PROVENANCE
        and rel in {REL_HOSTED_BY, REL_IN_ROOM, REL_ON_LEVEL}
    )


def _projection_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (source, target, key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if _is_projected_bim_edge(attrs)
    ]


def _projection_nodes(graph: Any) -> list[tuple[str, dict[str, Any]]]:
    return [
        (node_id, dict(attrs))
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
        and attrs.get("provenance") == PROVENANCE
        and attrs.get("nodeKind") in BIM_REFERENCE_NODE_KINDS
    ]


def _projected_joined_nodes(graph: Any) -> list[tuple[str, dict[str, Any]]]:
    return [
        (node_id, dict(attrs))
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
        and attrs.get("provenance") == PROVENANCE
        and attrs.get("rookbimJoined")
    ]


def _sidecar_fingerprints(graph: Any, edges: list[tuple[str, str, Any, dict[str, Any]]]) -> list[str]:
    values: set[str] = set()
    for _, attrs in _projection_nodes(graph):
        fp = _clean_str(attrs.get("sidecarFingerprint") or attrs.get("rookbimSidecarFingerprint"))
        if fp:
            values.add(fp)
    for _, _, _, attrs in edges:
        fp = _clean_str(attrs.get("sidecarFingerprint") or attrs.get("rookbimSidecarFingerprint"))
        if fp:
            values.add(fp)
    for _, attrs in graph.nodes(data=True):
        if attrs.get("rookbimJoined"):
            fp = _clean_str(attrs.get("rookbimSidecarFingerprint") or attrs.get("sidecarFingerprint"))
            if fp:
                values.add(fp)
    return sorted(values)


def _relationship_counts(edges: list[tuple[str, str, Any, dict[str, Any]]]) -> dict[str, int]:
    counts = {REL_HOSTED_BY: 0, REL_IN_ROOM: 0, REL_ON_LEVEL: 0}
    for _, _, _, attrs in edges:
        rel = attrs.get("relationship")
        if rel in counts:
            counts[rel] += 1
    return counts


def _effective_limit(mode: str, limit: int | None = None, sample_limit: int | None = None) -> int:
    default, maximum = MODE_LIMITS[mode]
    raw = sample_limit if mode == "relationship_scan" else limit
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(0, min(value, maximum))


def _invalid(
    message: str,
    *,
    graph_sequence: int,
    bim_projection_present: bool,
    fingerprints: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": "invalid_bim_query_input",
        "message": message,
        "bimProjectionPresent": bim_projection_present,
        "graphSequence": graph_sequence,
        "sidecarFingerprints": fingerprints or [],
    }


def _base_success(
    *,
    mode: str,
    graph_sequence: int,
    fingerprints: list[str],
    relationship_counts: dict[str, int],
    effective_limit: int,
    query: dict[str, Any],
    results: list[Any],
    total_count: int = 0,
    truncated: bool = False,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "mode": mode,
        "bimProjectionPresent": True,
        "graphSequence": graph_sequence,
        "sidecarFingerprints": fingerprints,
        "query": query,
        "summary": {
            "relationshipCounts": relationship_counts,
            "effectiveLimit": effective_limit,
            "totalCount": total_count,
        },
        "results": results,
        "truncated": truncated,
        "diagnostics": diagnostics or {},
    }


def _display_name(graph: Any, node_id: str) -> str:
    attrs = graph.nodes.get(node_id, {})
    return _clean_str(attrs.get("displayName") or attrs.get("name") or node_id)


def _full_detail_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in attrs.items()
        if key not in GEOMETRY_ATTRS
        and key not in RAW_SIDECAR_ATTRS
        and not any(key.startswith(prefix) for prefix in GEOMETRY_ATTR_PREFIXES)
    }


def _compact_object(graph: Any, node_id: str, edge_attrs: dict[str, Any] | None = None, *, detail: str = "compact") -> Any:
    if detail == "ids":
        return node_id

    attrs = dict(graph.nodes.get(node_id, {}))
    payload: dict[str, Any] = {
        "objectId": node_id,
        "displayName": _display_name(graph, node_id),
        "name": attrs.get("name", ""),
        "category": attrs.get("revitCategory") or attrs.get("domain_label") or attrs.get("shape_class") or "",
        "family": attrs.get("revitFamily", ""),
        "type": attrs.get("revitType", ""),
        "revitUniqueId": attrs.get("revitUniqueId", ""),
        "revitElementId": attrs.get("revitElementId", ""),
        "layer": attrs.get("layer", ""),
    }
    if edge_attrs:
        payload["edge"] = {
            key: edge_attrs[key]
            for key in ("relationship", "confidence", "source", "sidecarFingerprint", "provenance")
            if key in edge_attrs
        }
    if detail == "full":
        payload["nodeAttrs"] = _full_detail_attrs(attrs)
        if edge_attrs:
            payload["edgeAttrs"] = _full_detail_attrs(dict(edge_attrs))
    return payload


def _target_facts(graph: Any, node_id: str, relationship: str, *, detail: str) -> list[Any]:
    facts = []
    for _, target, attrs in graph.out_edges(node_id, data=True):
        if _is_projected_bim_edge(attrs, relationship):
            facts.append(_compact_object(graph, target, attrs, detail=detail))
    return facts


def _incoming_hosted(graph: Any, node_id: str, *, detail: str, effective_limit: int) -> dict[str, Any]:
    rows = []
    for source, _, attrs in graph.in_edges(node_id, data=True):
        if _is_projected_bim_edge(attrs, REL_HOSTED_BY):
            rows.append(_compact_object(graph, source, attrs, detail=detail))

    total = len(rows)
    return {
        "results": rows[:effective_limit],
        "totalCount": total,
        "effectiveLimit": effective_limit,
        "truncated": total > effective_limit,
    }


def _same_target_peer_count(graph: Any, node_id: str, relationship: str) -> int:
    target_ids = {
        target
        for _, target, attrs in graph.out_edges(node_id, data=True)
        if _is_projected_bim_edge(attrs, relationship)
    }
    if not target_ids:
        return 0

    peers = {
        source
        for source, target, attrs in graph.edges(data=True)
        if target in target_ids and _is_projected_bim_edge(attrs, relationship)
    }
    return len(peers)


def _object_context(graph: Any, object_ids: list[str], *, detail: str, effective_limit: int) -> tuple[list[dict[str, Any]], bool]:
    results = []
    truncated = False

    for object_id in object_ids:
        attrs = dict(graph.nodes.get(object_id, {}))
        if not attrs.get("rookbimJoined"):
            results.append({"objectId": object_id, "bimJoined": False})
            continue

        hosted_elements = _incoming_hosted(graph, object_id, detail=detail, effective_limit=effective_limit)
        truncated = truncated or hosted_elements["truncated"]
        results.append(
            {
                "objectId": object_id,
                "bimJoined": True,
                "identity": {
                    "displayName": _display_name(graph, object_id),
                    "revitUniqueId": attrs.get("revitUniqueId", ""),
                    "revitElementId": attrs.get("revitElementId", ""),
                    "revitCategory": attrs.get("revitCategory", ""),
                    "revitFamily": attrs.get("revitFamily", ""),
                    "revitType": attrs.get("revitType", ""),
                    "revitName": attrs.get("revitName", ""),
                    "revitLevel": attrs.get("revitLevel", ""),
                },
                "hostedBy": _target_facts(graph, object_id, REL_HOSTED_BY, detail=detail),
                "rooms": _target_facts(graph, object_id, REL_IN_ROOM, detail=detail),
                "levels": _target_facts(graph, object_id, REL_ON_LEVEL, detail=detail),
                "hostedElements": hosted_elements,
                "sameRoomCount": _same_target_peer_count(graph, object_id, REL_IN_ROOM),
                "sameLevelCount": _same_target_peer_count(graph, object_id, REL_ON_LEVEL),
            }
        )

    return results, truncated


def _matches(value: Any, needle: str) -> bool:
    normalized_needle = _clean_str(needle)
    return bool(normalized_needle) and _clean_str(value).casefold() == normalized_needle.casefold()


def _node_candidate(graph: Any, node_id: str, attrs: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {
        "nodeId": node_id,
        "displayName": _display_name(graph, node_id),
        **{field: attrs.get(field, "") for field in fields},
    }


def _find_room_nodes(graph: Any, *, room_id: str | None, room_name: str | None) -> tuple[list[str], list[dict[str, Any]]]:
    room_id = _clean_str(room_id)
    room_name = _clean_str(room_name)
    if not room_id and not room_name:
        raise ValueError("room_members requires room_id or room_name.")

    matches: list[tuple[str, dict[str, Any]]] = []
    fields = ["roomUniqueId", "roomNumber", "roomName", "displayName"]
    for node_id, attrs in _projection_nodes(graph):
        if attrs.get("nodeKind") != "rookbim_room":
            continue

        values = [node_id, *(attrs.get(field) for field in fields)]
        id_ok = True if not room_id else any(_matches(value, room_id) for value in values)
        name_ok = True if not room_name else any(_matches(value, room_name) for value in values)
        if id_ok and name_ok:
            matches.append((node_id, attrs))

    return [node_id for node_id, _ in matches], [
        _node_candidate(graph, node_id, attrs, fields)
        for node_id, attrs in matches
    ]


def _find_level_nodes(graph: Any, *, level_name: str | None) -> tuple[list[str], list[dict[str, Any]]]:
    level_name = _clean_str(level_name)
    if not level_name:
        raise ValueError("level_members requires level_name.")

    matches: list[tuple[str, dict[str, Any]]] = []
    fields = ["levelName", "displayName"]
    for node_id, attrs in _projection_nodes(graph):
        if attrs.get("nodeKind") != "rookbim_level":
            continue

        values = [node_id, *(attrs.get(field) for field in fields)]
        if any(_matches(value, level_name) for value in values):
            matches.append((node_id, attrs))

    return [node_id for node_id, _ in matches], [
        _node_candidate(graph, node_id, attrs, fields)
        for node_id, attrs in matches
    ]


def _incoming_members(
    graph: Any,
    target_node: str,
    relationship: str,
    *,
    detail: str,
    effective_limit: int,
) -> tuple[list[Any], int, bool]:
    if target_node not in graph:
        return [], 0, False

    rows = [
        _compact_object(graph, source, attrs, detail=detail)
        for source, _, attrs in graph.in_edges([target_node], data=True)
        if _is_projected_bim_edge(attrs, relationship)
    ]
    total = len(rows)
    return rows[:effective_limit], total, total > effective_limit


def _relationship_samples(
    graph: Any,
    edges: list[tuple[str, str, Any, dict[str, Any]]],
    *,
    effective_limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    rows = [
        {
            "relationship": attrs.get("relationship", ""),
            "source": {"objectId": source, "displayName": _display_name(graph, source)},
            "target": {"objectId": target, "displayName": _display_name(graph, target)},
            "sidecarFingerprint": _clean_str(
                attrs.get("sidecarFingerprint") or attrs.get("rookbimSidecarFingerprint")
            ),
        }
        for source, target, _, attrs in edges
    ]
    return rows[:effective_limit], len(rows) > effective_limit


def query_bim_facts(
    analytics: Any,
    *,
    mode: str,
    object_ids: list[str] | None = None,
    room_id: str | None = None,
    room_name: str | None = None,
    level_name: str | None = None,
    host_object_id: str | None = None,
    detail: str = "compact",
    limit: int | None = None,
    sample_limit: int | None = None,
) -> dict[str, Any]:
    graph = analytics.graph
    graph_sequence = int(getattr(analytics, "sequence", 0))

    edges = _projection_edges(graph)
    nodes = _projection_nodes(graph)
    joined_nodes = _projected_joined_nodes(graph)
    fingerprints = _sidecar_fingerprints(graph, edges)
    relationship_counts = _relationship_counts(edges)
    bim_projection_present = bool(edges or nodes or joined_nodes)

    if mode not in VALID_MODES:
        return _invalid(
            f"Unknown BIM facts query mode: {mode}",
            graph_sequence=graph_sequence,
            bim_projection_present=bim_projection_present,
            fingerprints=fingerprints,
        )
    if detail not in VALID_DETAILS:
        return _invalid(
            f"Unknown BIM facts detail level: {detail}",
            graph_sequence=graph_sequence,
            bim_projection_present=bim_projection_present,
            fingerprints=fingerprints,
        )

    effective_limit = _effective_limit(mode, limit=limit, sample_limit=sample_limit)

    if not bim_projection_present:
        return {
            "success": False,
            "error": "bim_projection_required",
            "message": "No BIM relationship projection is present in the scene graph. Run scene_project_bim_relationships first.",
            "bimProjectionPresent": False,
            "graphSequence": graph_sequence,
            "sidecarFingerprints": fingerprints,
        }

    if mode == "relationship_scan":
        samples, truncated = _relationship_samples(graph, edges, effective_limit=effective_limit)
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query={"detail": detail, "sampleLimit": effective_limit},
            results=samples,
            total_count=sum(relationship_counts.values()),
            truncated=truncated,
        )

    if mode == "object_context":
        if not object_ids:
            return _invalid(
                "object_context requires non-empty object_ids.",
                graph_sequence=graph_sequence,
                bim_projection_present=bim_projection_present,
                fingerprints=fingerprints,
            )

        results, truncated = _object_context(
            graph,
            object_ids,
            detail=detail,
            effective_limit=effective_limit,
        )
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query={"objectIds": object_ids, "detail": detail, "limit": effective_limit},
            results=results,
            total_count=len(results),
            truncated=truncated,
        )

    if mode == "room_members":
        try:
            node_ids, candidates = _find_room_nodes(graph, room_id=room_id, room_name=room_name)
        except ValueError as exc:
            return _invalid(
                str(exc),
                graph_sequence=graph_sequence,
                bim_projection_present=bim_projection_present,
                fingerprints=fingerprints,
            )

        query_payload = {"roomId": room_id, "roomName": room_name, "detail": detail, "limit": effective_limit}
        if len(node_ids) > 1:
            return {
                "success": False,
                "error": "ambiguous_bim_reference",
                "message": "Room selector matched multiple BIM room nodes.",
                "candidates": candidates,
                "bimProjectionPresent": True,
                "graphSequence": graph_sequence,
                "sidecarFingerprints": fingerprints,
            }
        if not node_ids:
            return _base_success(
                mode=mode,
                graph_sequence=graph_sequence,
                fingerprints=fingerprints,
                relationship_counts=relationship_counts,
                effective_limit=effective_limit,
                query=query_payload,
                results=[],
                total_count=0,
            )

        rows, total, truncated = _incoming_members(
            graph,
            node_ids[0],
            REL_IN_ROOM,
            detail=detail,
            effective_limit=effective_limit,
        )
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query=query_payload,
            results=rows,
            total_count=total,
            truncated=truncated,
        )

    if mode == "level_members":
        try:
            node_ids, candidates = _find_level_nodes(graph, level_name=level_name)
        except ValueError as exc:
            return _invalid(
                str(exc),
                graph_sequence=graph_sequence,
                bim_projection_present=bim_projection_present,
                fingerprints=fingerprints,
            )

        query_payload = {"levelName": level_name, "detail": detail, "limit": effective_limit}
        if len(node_ids) > 1:
            return {
                "success": False,
                "error": "ambiguous_bim_reference",
                "message": "Level selector matched multiple BIM level nodes.",
                "candidates": candidates,
                "bimProjectionPresent": True,
                "graphSequence": graph_sequence,
                "sidecarFingerprints": fingerprints,
            }
        if not node_ids:
            return _base_success(
                mode=mode,
                graph_sequence=graph_sequence,
                fingerprints=fingerprints,
                relationship_counts=relationship_counts,
                effective_limit=effective_limit,
                query=query_payload,
                results=[],
                total_count=0,
            )

        rows, total, truncated = _incoming_members(
            graph,
            node_ids[0],
            REL_ON_LEVEL,
            detail=detail,
            effective_limit=effective_limit,
        )
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query=query_payload,
            results=rows,
            total_count=total,
            truncated=truncated,
        )

    if mode == "hosted_elements":
        host_object_id = _clean_str(host_object_id)
        if not host_object_id:
            return _invalid(
                "hosted_elements requires host_object_id.",
                graph_sequence=graph_sequence,
                bim_projection_present=bim_projection_present,
                fingerprints=fingerprints,
            )

        rows, total, truncated = _incoming_members(
            graph,
            host_object_id,
            REL_HOSTED_BY,
            detail=detail,
            effective_limit=effective_limit,
        )
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query={"hostObjectId": host_object_id, "detail": detail, "limit": effective_limit},
            results=rows,
            total_count=total,
            truncated=truncated,
        )

    return _invalid(
        f"Mode {mode} is not implemented yet.",
        graph_sequence=graph_sequence,
        bim_projection_present=bim_projection_present,
        fingerprints=fingerprints,
    )
