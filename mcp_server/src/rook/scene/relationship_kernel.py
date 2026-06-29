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
EXACT_REFUTATION_METHOD = "adjacent_exact_refutation"
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
    graph: Any,
    claim: dict[str, Any],
    marker_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    support_evidence, support_interfaces = _exact_support_for_claim(graph, claim)
    refute_evidence, refute_interfaces = _exact_refutation_for_claim(graph, claim)
    marker_evidence = _marker_hint_for_claim(claim, marker_evidence_records)
    return (
        support_evidence + refute_evidence + marker_evidence,
        support_interfaces + refute_interfaces,
    )


def _pair_edges(
    graph: Any,
    first: str,
    second: str,
) -> list[tuple[str, str, str, dict[str, Any]]]:
    edges: list[tuple[str, str, str, dict[str, Any]]] = []
    for source, target, key, attrs in graph.edges(keys=True, data=True):
        if {str(source), str(target)} == {first, second}:
            edges.append((str(source), str(target), str(key), dict(attrs)))
    return edges


def _interface_id(
    claim: dict[str, Any],
    method: str,
    edge_key: str,
) -> str:
    return f"interface:{claim['relationshipClaimId']}:{method}:{edge_key}"


def _evidence_id(
    claim: dict[str, Any],
    method: str,
    edge_key: str,
) -> str:
    return f"evidence:{claim['relationshipClaimId']}:{method}:{edge_key}"


def _exact_support_for_claim(
    graph: Any,
    claim: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    from_object = claim["fromObjectId"]
    to_object = claim["toObjectId"]
    feature_paths = [claim.get("fromFeature"), claim.get("toFeature")]
    for _source, _target, key, attrs in _pair_edges(graph, from_object, to_object):
        if attrs.get("relationship") != EXACT_RELATIONSHIP:
            continue
        interface_record_id = _interface_id(claim, EXACT_RELATIONSHIP, key)
        measures = {
            "sharedArea": attrs.get("sharedArea"),
            "lengthUnit": attrs.get("lengthUnit"),
            "areaUnit": attrs.get("areaUnit"),
            "facePairs": attrs.get("facePairs"),
            "graphSequence": attrs.get("graphSequence"),
            "engineVersion": attrs.get("engineVersion"),
        }
        interface_record = {
            "interfaceRecordId": interface_record_id,
            "kind": INTERFACE_KIND,
            "interfaceType": "shared_topology",
            "method": EXACT_RELATIONSHIP,
            "source": EXACT_PROVENANCE,
            "objectIds": [from_object, to_object],
            "interfaceScope": "owner_pair",
            "featurePaths": feature_paths,
            "featureScopeVerified": False,
            "measures": measures,
        }
        evidence_record = {
            "evidenceId": _evidence_id(claim, EXACT_RELATIONSHIP, key),
            "kind": EVIDENCE_KIND,
            "relationshipClaimId": claim["relationshipClaimId"],
            "relationship": claim["relationship"],
            "method": EXACT_RELATIONSHIP,
            "strength": "exact_topology",
            "polarity": "supports",
            "status": "measured",
            "source": EXACT_PROVENANCE,
            "claimTypeField": claim["relationship"],
            "evidenceMethodField": EXACT_RELATIONSHIP,
            "interfaceRecordIds": [interface_record_id],
            "reason": "exact_topology_supports_owner_contact",
            "measures": measures,
        }
        interface_records.append(interface_record)
        evidence.append(evidence_record)
    return evidence, interface_records


def _exact_refutation_for_claim(
    graph: Any,
    claim: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    from_object = claim["fromObjectId"]
    to_object = claim["toObjectId"]
    feature_paths = [claim.get("fromFeature"), claim.get("toFeature")]
    for _source, _target, key, attrs in _pair_edges(graph, from_object, to_object):
        if attrs.get("relationship") != "adjacent":
            continue
        if attrs.get("exact_status") != "exact_refuted":
            continue
        if attrs.get("exact_graphSequence") is None:
            continue
        interface_record_id = _interface_id(claim, EXACT_REFUTATION_METHOD, key)
        measures = {
            "reason": attrs.get("exact_reason"),
            "graphSequence": attrs.get("exact_graphSequence"),
            "engineVersion": attrs.get("exact_engineVersion"),
        }
        interface_record = {
            "interfaceRecordId": interface_record_id,
            "kind": INTERFACE_KIND,
            "interfaceType": "refuted_shared_topology",
            "method": EXACT_REFUTATION_METHOD,
            "source": EXACT_PROVENANCE,
            "objectIds": [from_object, to_object],
            "interfaceScope": "owner_pair",
            "featurePaths": feature_paths,
            "featureScopeVerified": False,
            "measures": measures,
        }
        evidence_record = {
            "evidenceId": _evidence_id(claim, EXACT_REFUTATION_METHOD, key),
            "kind": EVIDENCE_KIND,
            "relationshipClaimId": claim["relationshipClaimId"],
            "relationship": claim["relationship"],
            "method": EXACT_REFUTATION_METHOD,
            "strength": "exact_topology",
            "polarity": "contradicts",
            "status": "measured",
            "source": EXACT_PROVENANCE,
            "claimTypeField": claim["relationship"],
            "evidenceMethodField": EXACT_REFUTATION_METHOD,
            "interfaceRecordIds": [interface_record_id],
            "reason": "explicit_exact_topology_refutation",
            "measures": measures,
        }
        interface_records.append(interface_record)
        evidence.append(evidence_record)
    return evidence, interface_records


def _marker_record_claim_id(record: dict[str, Any]) -> str | None:
    value = (
        record.get("relationshipFactId")
        or record.get("relationshipClaimId")
        or record.get("claimId")
    )
    return str(value) if value else None


def _marker_hint_for_claim(
    claim: dict[str, Any],
    marker_evidence_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, record in enumerate(marker_evidence_records):
        if _marker_record_claim_id(record) != claim["relationshipClaimId"]:
            continue
        marker = dict(record.get("evidence") or {})
        status = str(marker.get("status") or "missing")
        if status == "measured":
            polarity = "supports" if marker.get("withinTolerance") is True else "contradicts"
        else:
            polarity = "missing"
        evidence_record = {
            "evidenceId": f"evidence:{claim['relationshipClaimId']}:marker_hint:{index}",
            "kind": EVIDENCE_KIND,
            "relationshipClaimId": claim["relationshipClaimId"],
            "relationship": claim["relationship"],
            "method": str(marker.get("method") or "feature_marker_position_distance"),
            "strength": "marker_hint",
            "polarity": polarity,
            "status": status,
            "source": marker.get("source") or "rhino_user_text_feature_positions",
            "claimTypeField": claim["relationship"],
            "evidenceMethodField": str(
                marker.get("method") or "feature_marker_position_distance"
            ),
            "interfaceRecordIds": [],
            "reason": "feature_marker_distance_hint",
            "measures": {
                "distanceM": marker.get("distanceM"),
                "toleranceM": marker.get("toleranceM"),
                "withinTolerance": marker.get("withinTolerance"),
            },
        }
        if status == "missing":
            evidence_record["diagnostics"] = {
                "missing": list(marker.get("missing") or [])
            }
        evidence.append(evidence_record)
    return evidence


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
