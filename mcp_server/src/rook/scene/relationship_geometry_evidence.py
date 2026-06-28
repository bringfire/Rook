from __future__ import annotations

import math
from typing import Any


PROJECTION_KIND = "relationship_fact_v1"
EVIDENCE_KIND = "relationship_geometry_evidence_v1"
EVIDENCE_METHOD = "feature_marker_position_distance"
EVIDENCE_SOURCE = "rhino_user_text_feature_positions"
DEFAULT_TOLERANCE_M = 0.01


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

    records: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in projected_edges:
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
        record = _base_record(source_id, target_id, attrs)
        record["evidence"] = {
            "kind": EVIDENCE_KIND,
            "method": EVIDENCE_METHOD,
            "status": "missing",
            "missing": ["fromFeaturePosition", "toFeaturePosition"],
            "toleranceM": float(tolerance_m),
            "withinTolerance": None,
            "source": EVIDENCE_SOURCE,
        }
        records.append(record)

    if not records:
        diagnostics["noMatchingRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    return _response(records, diagnostics, hydrated_feature_object_count=0)
