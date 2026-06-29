"""Internal relationship claim/evidence/verdict read model.

This module intentionally does not register an MCP tool. It normalizes existing
scene-graph edges into the consolidation spine described by the spatial
relationship kernel specs: Claim -> Evidence -> Verdict -> View.
"""

from __future__ import annotations

from typing import Any

REPORT_SCHEMA = "rook.relationship_kernel_report.v1"
CLAIM_PROJECTION_KIND = "relationship_fact_v1"
EXACT_RELATIONSHIP = "adjacent_exact"
EXACT_PROVENANCE = "occt"
EVIDENCE_KIND = "relationship_evidence_v1"
INTERFACE_KIND = "interface_record_v1"
EVIDENCE_STRENGTH_ORDER = (
    "none",
    "marker_hint",
    "bbox_observation",
    "exact_topology",
    "explicit_connector",
)
CONTACT_LIKE_RELATIONSHIPS = {"connects", "touches", "abuts"}
CONTACT_LIKE_KINDS = {
    "point_to_point",
    "point_to_region",
    "edge_to_edge",
    "edge_to_region",
    "face_to_face",
    "face_to_region",
    "boundary_to_face",
}
NOT_APPLICABLE_RELATIONSHIPS = {"hosted_by", "penetrates"}


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _optional_list_of_strings_is_valid(value: Any) -> bool:
    return value is None or (
        isinstance(value, list) and all(isinstance(item, str) for item in value)
    )


def _invalid_list_result(field: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": f"invalid_{field}",
        "message": f"{field} must be a list of strings when supplied.",
    }


def _relationship(attrs: dict[str, Any]) -> str:
    value = attrs.get("semanticRelationshipType") or attrs.get("relationship")
    return str(value or "")


def _claim_edges(graph: Any) -> list[tuple[str, str, str, dict[str, Any]]]:
    edges: list[tuple[str, str, str, dict[str, Any]]] = []
    for source, target, key, attrs in graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") == CLAIM_PROJECTION_KIND:
            edges.append((str(source), str(target), str(key), dict(attrs)))
    return edges


def _matches_filters(
    claim: dict[str, Any],
    *,
    object_ids: list[str] | None,
    relationship_types: list[str] | None,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    diagnostics: dict[str, int],
) -> bool:
    if object_ids is not None and (
        claim["fromObjectId"] not in object_ids and claim["toObjectId"] not in object_ids
    ):
        _bump(diagnostics, "filteredByObjectScope")
        return False
    if relationship_types is not None and claim["relationship"] not in relationship_types:
        _bump(diagnostics, "filteredByRelationshipType")
        return False
    if graph_source is not None and claim.get("graphSource") != graph_source:
        _bump(diagnostics, "filteredByGraphSource")
        return False
    if graph_revision is not None and claim.get("graphRevision") != graph_revision:
        _bump(diagnostics, "filteredByGraphRevision")
        return False
    if poses is not None and claim.get("pose") not in poses:
        _bump(diagnostics, "filteredByPose")
        return False
    return True


def _claim_from_edge(
    source: str,
    target: str,
    key: str,
    attrs: dict[str, Any],
) -> dict[str, Any]:
    relationship = _relationship(attrs)
    return {
        "relationshipClaimId": str(
            attrs.get("relationshipFactId")
            or attrs.get("relationshipClaimId")
            or f"{source}:{key}:{target}"
        ),
        "relationship": relationship,
        "claimTypeField": relationship,
        "fromObjectId": source,
        "toObjectId": target,
        "fromFeature": attrs.get("fromFeature"),
        "toFeature": attrs.get("toFeature"),
        "fromFeatureObjectId": attrs.get("fromFeatureObjectId"),
        "toFeatureObjectId": attrs.get("toFeatureObjectId"),
        "contactKind": attrs.get("contactKind"),
        "provenance": attrs.get("provenance"),
        "confidence": attrs.get("confidence"),
        "status": attrs.get("status"),
        "graphSource": attrs.get("graphSource"),
        "graphRevision": attrs.get("graphRevision"),
        "pose": attrs.get("pose"),
        "physicalObligation": attrs.get("physicalObligation")
        or attrs.get("physical_obligation"),
        "edgeKey": key,
    }


def _physical_obligation(claim: dict[str, Any]) -> dict[str, Any]:
    relationship = claim["relationship"]
    contact_kind = claim.get("contactKind")
    if relationship in NOT_APPLICABLE_RELATIONSHIPS:
        return {
            "applicable": False,
            "reason": "no_v1_physical_obligation",
        }
    if relationship == "supports":
        if claim.get("physicalObligation") == "direct_contact":
            return {
                "applicable": True,
                "reason": "exact_adjacency_applicable",
            }
        return {
            "applicable": False,
            "reason": "no_v1_physical_obligation",
        }
    if relationship in CONTACT_LIKE_RELATIONSHIPS and contact_kind in CONTACT_LIKE_KINDS:
        return {
            "applicable": True,
            "reason": "exact_adjacency_applicable",
        }
    return {
        "applicable": False,
        "reason": "no_v1_physical_obligation",
    }


def _strength_rank(strength: str | None) -> int:
    if strength in EVIDENCE_STRENGTH_ORDER:
        return EVIDENCE_STRENGTH_ORDER.index(strength)
    return 0


def _strongest_strength(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "none"
    return max(
        (str(item.get("strength") or "none") for item in evidence),
        key=_strength_rank,
    )


def _verdict_for_claim(
    claim: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    obligation = _physical_obligation(claim)
    if not obligation["applicable"]:
        return {
            "relationshipClaimId": claim["relationshipClaimId"],
            "verdict": "not_applicable",
            "reason": obligation["reason"],
            "strongestEvidence": _strongest_strength(evidence),
        }
    exact_refutations = [
        item
        for item in evidence
        if item.get("strength") == "exact_topology"
        and item.get("polarity") == "contradicts"
    ]
    if exact_refutations:
        return {
            "relationshipClaimId": claim["relationshipClaimId"],
            "verdict": "contradicted",
            "reason": "explicit_exact_topology_refutation",
            "strongestEvidence": _strongest_strength(evidence),
        }
    exact_support = [
        item
        for item in evidence
        if item.get("strength") == "exact_topology" and item.get("polarity") == "supports"
    ]
    if exact_support:
        return {
            "relationshipClaimId": claim["relationshipClaimId"],
            "verdict": "satisfied",
            "reason": "exact_topology_supports_owner_contact",
            "strongestEvidence": _strongest_strength(evidence),
        }
    return {
        "relationshipClaimId": claim["relationshipClaimId"],
        "verdict": "unverified",
        "reason": "no_applicable_exact_topology_evidence",
        "strongestEvidence": _strongest_strength(evidence),
    }


def _empty_report(diagnostics: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "schema": REPORT_SCHEMA,
        "counts": {
            "relationshipClaimCount": 0,
            "evidenceCount": 0,
            "interfaceRecordCount": 0,
            "verdictCount": 0,
            "byVerdict": {},
        },
        "claims": [],
        "evidence": [],
        "interfaceRecords": [],
        "verdicts": [],
        "diagnostics": diagnostics or {},
    }


def _counts(
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    interface_records: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
) -> dict[str, Any]:
    by_verdict: dict[str, int] = {}
    for verdict in verdicts:
        _bump(by_verdict, str(verdict["verdict"]))
    return {
        "relationshipClaimCount": len(claims),
        "evidenceCount": len(evidence),
        "interfaceRecordCount": len(interface_records),
        "verdictCount": len(verdicts),
        "byVerdict": by_verdict,
    }


def _evidence_for_claim(
    _graph: Any,
    _claim: dict[str, Any],
    _marker_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return [], []


def query_relationship_kernel_report(
    scene_graph: Any,
    *,
    object_ids: list[str] | None = None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: list[str] | None = None,
    relationship_types: list[str] | None = None,
    marker_evidence_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not _optional_list_of_strings_is_valid(object_ids):
        return _invalid_list_result("object_ids")
    if not _optional_list_of_strings_is_valid(poses):
        return _invalid_list_result("poses")
    if not _optional_list_of_strings_is_valid(relationship_types):
        return _invalid_list_result("relationship_types")

    diagnostics: dict[str, int] = {}
    graph = scene_graph.graph if hasattr(scene_graph, "graph") else scene_graph
    claims: list[dict[str, Any]] = []
    for source, target, key, attrs in _claim_edges(graph):
        claim = _claim_from_edge(source, target, key, attrs)
        if _matches_filters(
            claim,
            object_ids=object_ids,
            relationship_types=relationship_types,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            diagnostics=diagnostics,
        ):
            claims.append(claim)

    claims.sort(key=lambda item: item["relationshipClaimId"])
    if not claims:
        _bump(diagnostics, "noRelationshipClaims")
        return _empty_report(diagnostics)

    marker_records = marker_evidence_records or []
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    for claim in claims:
        claim_evidence, claim_interfaces = _evidence_for_claim(graph, claim, marker_records)
        evidence.extend(claim_evidence)
        interface_records.extend(claim_interfaces)
        verdicts.append(_verdict_for_claim(claim, claim_evidence))

    return {
        "success": True,
        "schema": REPORT_SCHEMA,
        "counts": _counts(claims, evidence, interface_records, verdicts),
        "claims": claims,
        "evidence": evidence,
        "interfaceRecords": interface_records,
        "verdicts": verdicts,
        "diagnostics": diagnostics,
    }
