from __future__ import annotations

import json
import math
from typing import Any

from ..bridge import call_rhino


PROJECTION_KIND = "relationship_fact_v1"
EVIDENCE_KIND = "relationship_geometry_evidence_v1"
EVIDENCE_METHOD = "feature_marker_position_distance"
EVIDENCE_SOURCE = "rhino_user_text_feature_positions"
DEFAULT_TOLERANCE_M = 0.01
USER_TEXT_OBJECT_GET_ROUTE = "/usertext/object-get"


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _optional_list_of_strings_is_valid(value: Any) -> bool:
    return value is None or (isinstance(value, list) and all(isinstance(item, str) for item in value))


def _invalid_list_result(name: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": f"invalid_{name}",
        "message": f"{name} must be a list of strings when supplied",
    }


def _valid_tolerance(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _invalid_tolerance_result() -> dict[str, Any]:
    return {
        "success": False,
        "error": "invalid_tolerance_m",
        "message": "tolerance_m must be a finite number greater than or equal to 0",
    }


def _empty_response(diagnostics: dict[str, int]) -> dict[str, Any]:
    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "evidenceKind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "counts": {
            "matchingRelationshipFactCount": 0,
            "evidenceRecordCount": 0,
            "measuredEvidenceCount": 0,
            "missingEvidenceCount": 0,
            "withinToleranceCount": 0,
            "outsideToleranceCount": 0,
            "hydratedFeatureObjectCount": 0,
        },
        "records": [],
        "diagnostics": diagnostics,
    }


def _projected_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (str(source), str(target), key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
    ]


def _relationship(attrs: dict[str, Any]) -> str | None:
    value = attrs.get("semanticRelationshipType") or attrs.get("relationship")
    return str(value) if value is not None else None


def _matches_filters(
    source_id: str,
    target_id: str,
    attrs: dict[str, Any],
    *,
    object_ids: list[str] | None,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    relationship_types: list[str] | None,
    relationship_fact_ids: list[str] | None,
    diagnostics: dict[str, int],
) -> bool:
    if object_ids is not None and source_id not in set(object_ids) and target_id not in set(object_ids):
        _bump(diagnostics, "filteredByObjectId")
        return False
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
    if relationship_fact_ids and attrs.get("relationshipFactId") not in set(relationship_fact_ids):
        _bump(diagnostics, "filteredByRelationshipFactId")
        return False
    return True


def _base_record(source_id: str, target_id: str, attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "relationshipFactId": attrs.get("relationshipFactId"),
        "relationship": _relationship(attrs),
        "fromObjectId": source_id,
        "toObjectId": target_id,
        "fromFeature": attrs.get("fromFeature"),
        "toFeature": attrs.get("toFeature"),
        "fromFeatureObjectId": attrs.get("fromFeatureObjectId"),
        "toFeatureObjectId": attrs.get("toFeatureObjectId"),
        "contactKind": attrs.get("contactKind"),
        "graphSource": attrs.get("graphSource"),
        "graphRevision": attrs.get("graphRevision"),
        "pose": attrs.get("pose"),
        "provenance": attrs.get("provenance"),
        "status": attrs.get("status"),
    }


def _parse_position(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list) or len(value) != 3:
        return None
    coords: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            return None
        coord = float(item)
        if not math.isfinite(coord):
            return None
        coords.append(coord)
    return (coords[0], coords[1], coords[2])


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _missing_evidence(missing: list[str], tolerance_m: float) -> dict[str, Any]:
    return {
        "kind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "status": "missing",
        "missing": missing,
        "toleranceM": tolerance_m,
        "withinTolerance": None,
        "source": EVIDENCE_SOURCE,
    }


def _measured_evidence(distance_m: float, tolerance_m: float) -> dict[str, Any]:
    return {
        "kind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "status": "measured",
        "distanceM": distance_m,
        "toleranceM": tolerance_m,
        "withinTolerance": distance_m <= tolerance_m,
        "source": EVIDENCE_SOURCE,
    }


def _evidence_for_record(
    record: dict[str, Any],
    *,
    feature_user_strings_by_id: dict[str, dict[str, Any] | None],
    tolerance_m: float,
    diagnostics: dict[str, int],
) -> dict[str, Any]:
    missing: list[str] = []
    from_feature_object_id = record.get("fromFeatureObjectId")
    to_feature_object_id = record.get("toFeatureObjectId")
    if not from_feature_object_id:
        missing.append("fromFeatureObjectId")
        _bump(diagnostics, "missingFeatureObjectId")
    if not to_feature_object_id:
        missing.append("toFeatureObjectId")
        _bump(diagnostics, "missingFeatureObjectId")
    if missing:
        return _missing_evidence(missing, tolerance_m)

    from_user_text = feature_user_strings_by_id.get(str(from_feature_object_id))
    to_user_text = feature_user_strings_by_id.get(str(to_feature_object_id))
    if from_user_text is None:
        missing.append("fromFeatureUserText")
        _bump(diagnostics, "missingFeatureUserText")
    if to_user_text is None:
        missing.append("toFeatureUserText")
        _bump(diagnostics, "missingFeatureUserText")
    if missing:
        return _missing_evidence(missing, tolerance_m)

    from_position = _parse_position(from_user_text.get("rook.graph.true_position_m"))
    to_position = _parse_position(to_user_text.get("rook.graph.true_position_m"))
    if from_position is None:
        key = (
            "missingFeaturePosition"
            if from_user_text.get("rook.graph.true_position_m") is None
            else "invalidFeaturePosition"
        )
        _bump(diagnostics, key)
        missing.append("fromFeaturePosition")
    if to_position is None:
        key = (
            "missingFeaturePosition"
            if to_user_text.get("rook.graph.true_position_m") is None
            else "invalidFeaturePosition"
        )
        _bump(diagnostics, key)
        missing.append("toFeaturePosition")
    if missing:
        return _missing_evidence(missing, tolerance_m)

    distance_m = _distance(from_position, to_position)
    evidence = _measured_evidence(distance_m, tolerance_m)
    if evidence["withinTolerance"] is False:
        _bump(diagnostics, "outsideTolerance")
    return evidence


def _response(
    records: list[dict[str, Any]],
    diagnostics: dict[str, int],
    *,
    hydrated_feature_object_count: int,
) -> dict[str, Any]:
    measured = [record for record in records if record["evidence"].get("status") == "measured"]
    missing = [record for record in records if record["evidence"].get("status") == "missing"]
    within = [
        record
        for record in measured
        if record["evidence"].get("withinTolerance") is True
    ]
    outside = [
        record
        for record in measured
        if record["evidence"].get("withinTolerance") is False
    ]
    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "evidenceKind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "counts": {
            "matchingRelationshipFactCount": len(records),
            "evidenceRecordCount": len(records),
            "measuredEvidenceCount": len(measured),
            "missingEvidenceCount": len(missing),
            "withinToleranceCount": len(within),
            "outsideToleranceCount": len(outside),
            "hydratedFeatureObjectCount": hydrated_feature_object_count,
        },
        "records": records,
        "diagnostics": diagnostics,
    }


def _matching_records(
    analytics: Any,
    *,
    object_ids: list[str] | None,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    relationship_types: list[str] | None,
    relationship_fact_ids: list[str] | None,
    diagnostics: dict[str, int],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in _projected_edges(analytics.graph):
        if not _matches_filters(
            source_id,
            target_id,
            attrs,
            object_ids=object_ids,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            relationship_types=relationship_types,
            relationship_fact_ids=relationship_fact_ids,
            diagnostics=diagnostics,
        ):
            continue
        records.append(_base_record(source_id, target_id, attrs))
    return records


def _feature_object_ids_for_records(records: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    feature_object_ids: list[str] = []
    for record in records:
        for key in ("fromFeatureObjectId", "toFeatureObjectId"):
            value = record.get(key)
            if not value:
                continue
            object_id = str(value)
            if object_id in seen:
                continue
            seen.add(object_id)
            feature_object_ids.append(object_id)
    return feature_object_ids


def _response_route_failed(response: dict[str, Any]) -> bool:
    if not response.get("success"):
        return True
    return not isinstance(response.get("data"), dict)


def _extract_user_strings(response: dict[str, Any]) -> dict[str, Any] | None:
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    user_strings = data.get("userStrings")
    return user_strings if isinstance(user_strings, dict) else None


async def _hydrate_feature_user_strings(
    feature_object_ids: list[str],
    *,
    port: int | None = None,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, int], bool]:
    user_strings_by_id: dict[str, dict[str, Any] | None] = {}
    diagnostics: dict[str, int] = {}
    failures = 0
    for object_id in feature_object_ids:
        try:
            response = await call_rhino(USER_TEXT_OBJECT_GET_ROUTE, "POST", {"id": object_id}, port=port)
        except Exception:
            failures += 1
            _bump(diagnostics, "hydrationFailures")
            user_strings_by_id[object_id] = None
            continue
        if _response_route_failed(response):
            failures += 1
            _bump(diagnostics, "hydrationFailures")
            user_strings_by_id[object_id] = None
            continue
        user_strings_by_id[object_id] = _extract_user_strings(response)
    all_failed = bool(feature_object_ids) and failures == len(feature_object_ids)
    return user_strings_by_id, diagnostics, all_failed


def query_relationship_evidence(
    analytics: Any,
    *,
    object_ids: Any = None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: Any = None,
    relationship_types: Any = None,
    relationship_fact_ids: Any = None,
    tolerance_m: Any = DEFAULT_TOLERANCE_M,
    feature_user_strings_by_id: dict[str, dict[str, Any] | None] | None = None,
    hydration_diagnostics: dict[str, int] | None = None,
) -> dict[str, Any]:
    for name, value in (
        ("object_ids", object_ids),
        ("poses", poses),
        ("relationship_types", relationship_types),
        ("relationship_fact_ids", relationship_fact_ids),
    ):
        if not _optional_list_of_strings_is_valid(value):
            return _invalid_list_result(name)
    if not _valid_tolerance(tolerance_m):
        return _invalid_tolerance_result()

    diagnostics = dict(hydration_diagnostics or {})
    projected_edges = _projected_edges(analytics.graph)
    if not projected_edges:
        diagnostics["noProjectedRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    records = _matching_records(
        analytics,
        object_ids=object_ids,
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        relationship_types=relationship_types,
        relationship_fact_ids=relationship_fact_ids,
        diagnostics=diagnostics,
    )
    for record in records:
        record["evidence"] = _evidence_for_record(
            record,
            feature_user_strings_by_id=feature_user_strings_by_id or {},
            tolerance_m=float(tolerance_m),
            diagnostics=diagnostics,
        )

    if not records:
        diagnostics["noMatchingRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    hydrated_feature_object_count = len(
        [value for value in (feature_user_strings_by_id or {}).values() if value is not None]
    )
    return _response(records, diagnostics, hydrated_feature_object_count=hydrated_feature_object_count)


async def query_relationship_evidence_for_tool(
    *,
    analytics: Any | None = None,
    object_ids: Any = None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: Any = None,
    relationship_types: Any = None,
    relationship_fact_ids: Any = None,
    tolerance_m: Any = DEFAULT_TOLERANCE_M,
    port: int | None = None,
) -> dict[str, Any]:
    for name, value in (
        ("object_ids", object_ids),
        ("poses", poses),
        ("relationship_types", relationship_types),
        ("relationship_fact_ids", relationship_fact_ids),
    ):
        if not _optional_list_of_strings_is_valid(value):
            return _invalid_list_result(name)
    if not _valid_tolerance(tolerance_m):
        return _invalid_tolerance_result()

    if analytics is None:
        from .scene_graph import get_scene_graph

        analytics = get_scene_graph()

    diagnostics: dict[str, int] = {}
    projected_edges = _projected_edges(analytics.graph)
    if not projected_edges:
        diagnostics["noProjectedRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    records = _matching_records(
        analytics,
        object_ids=object_ids,
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        relationship_types=relationship_types,
        relationship_fact_ids=relationship_fact_ids,
        diagnostics=diagnostics,
    )
    if not records:
        diagnostics["noMatchingRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    feature_object_ids = _feature_object_ids_for_records(records)
    user_strings_by_id, hydration_diagnostics, all_failed = await _hydrate_feature_user_strings(
        feature_object_ids,
        port=port,
    )
    if all_failed:
        return {
            "success": False,
            "error": "relationship_evidence_hydration_unavailable",
            "message": "Unable to read Rhino user text for any requested feature marker objects",
            "diagnostics": hydration_diagnostics,
        }

    return query_relationship_evidence(
        analytics,
        object_ids=object_ids,
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        relationship_types=relationship_types,
        relationship_fact_ids=relationship_fact_ids,
        tolerance_m=tolerance_m,
        feature_user_strings_by_id=user_strings_by_id,
        hydration_diagnostics=hydration_diagnostics,
    )
