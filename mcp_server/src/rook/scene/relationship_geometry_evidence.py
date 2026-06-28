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

    diagnostics["noMatchingRelationshipFacts"] = 1
    return _empty_response(diagnostics)
