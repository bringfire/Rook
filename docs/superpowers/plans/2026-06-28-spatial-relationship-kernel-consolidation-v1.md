# Spatial Relationship Kernel Consolidation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small pure read-model adapter that normalizes existing projected relationship claims and existing exact-topology signals into one `Claim -> Evidence -> Verdict` report.

**Architecture:** Create one focused Python module, `rook.scene.relationship_kernel`, that reads the current `SceneGraphAnalytics.graph` only. It does not call Rhino, does not sync, does not project, does not infer new claims, does not mutate claim status, and does not add a public MCP tool. Tests build synthetic `SceneGraphAnalytics` graphs with `relationship_fact_v1`, `adjacent_exact`, and exact-refutation annotations to prove the canonical contract before any live Rhino work.

**Tech Stack:** Python, NetworkX `MultiDiGraph` via `SceneGraphAnalytics`, pytest.

---

## File Structure

- Create: `mcp_server/src/rook/scene/relationship_kernel.py`
  - Owns constants, pure normalization helpers, and `query_relationship_kernel_report(...)`.
  - Reads `relationship_fact_v1` claim edges, `adjacent_exact` support edges, exact-refutation annotations, and optional marker evidence records supplied by the caller.
  - Produces structured `claims`, `evidence`, `interfaceRecords`, and `verdicts`.
- Create: `mcp_server/tests/test_relationship_kernel.py`
  - Pure unit tests only. No Rhino, no MCP tool dispatch, no live route calls.
- Do not modify: `mcp_server/src/rook/server.py`, `mcp_server/src/rook/agent/tool_dispatcher.py`, `mcp_server/src/rook/agent/tool_groups.py`, or `mcp_server/src/rook/targeting.py`.
  - This slice intentionally adds no public tool.

## Contract Summary

Report shape:

```python
{
    "success": True,
    "schema": "rook.relationship_kernel_report.v1",
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
    "diagnostics": {},
}
```

Canonical verdicts:

```python
"satisfied"
"contradicted"
"unverified"
"not_applicable"
```

Evidence strength order, for reporting only:

```python
("none", "marker_hint", "bbox_observation", "exact_topology", "explicit_connector")
```

The implementation must never treat missing `adjacent_exact` as contradiction. `contradicted`
requires explicit exact-refutation evidence for the same claim object pair.

---

### Task 1: Relationship Claim Normalization

**Files:**
- Create: `mcp_server/tests/test_relationship_kernel.py`
- Create: `mcp_server/src/rook/scene/relationship_kernel.py`

- [ ] **Step 1: Write failing tests for constants, empty report, claim normalization, and filters**

Create `mcp_server/tests/test_relationship_kernel.py` with this initial content:

```python
from __future__ import annotations

from rook.scene.scene_graph import SceneGraphAnalytics


def _empty_scene_graph() -> SceneGraphAnalytics:
    return SceneGraphAnalytics()


def _claim_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("column-owner", name="column_01")
    sg.graph.add_node("slab-owner", name="slab_01")
    sg.graph.add_node("door-owner", name="door_01")
    sg.graph.add_node("wall-owner", name="wall_01")
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="relationship_fact:architectural:supports",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="column_01.top_point_supports_slab_01.underside_region",
        fromFeature="column_01.top_point",
        toFeature="slab_01.underside_region",
        fromFeatureObjectId="feature-column-top",
        toFeatureObjectId="feature-slab-underside",
        contactKind="point_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "door-owner",
        "wall-owner",
        key="relationship_fact:architectural:hosted",
        relationship="hosted_by",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="hosted_by",
        relationshipFactId="door_01.body_hosted_by_wall_01.host_region",
        fromFeature="door_01.body",
        toFeature="wall_01.host_region",
        fromFeatureObjectId="feature-door-body",
        toFeatureObjectId="feature-wall-host",
        contactKind="body_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "column-owner",
        "wall-owner",
        key="spatial-near",
        relationship="near",
        distance=0.2,
    )
    return sg


def test_relationship_kernel_constants():
    from rook.scene import relationship_kernel as kernel

    assert kernel.REPORT_SCHEMA == "rook.relationship_kernel_report.v1"
    assert kernel.CLAIM_PROJECTION_KIND == "relationship_fact_v1"
    assert kernel.EXACT_RELATIONSHIP == "adjacent_exact"
    assert kernel.EVIDENCE_STRENGTH_ORDER == (
        "none",
        "marker_hint",
        "bbox_observation",
        "exact_topology",
        "explicit_connector",
    )


def test_relationship_kernel_empty_report_without_claims():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    result = query_relationship_kernel_report(_empty_scene_graph())

    assert result == {
        "success": True,
        "schema": "rook.relationship_kernel_report.v1",
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
        "diagnostics": {"noRelationshipClaims": 1},
    }


def test_relationship_kernel_normalizes_relationship_fact_edges_to_claims():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    result = query_relationship_kernel_report(
        _claim_graph(),
        graph_source="architectural_relationship_fixture",
        graph_revision="a001",
        poses=["architectural_reference"],
    )

    assert result["success"] is True
    assert result["counts"]["relationshipClaimCount"] == 2
    assert result["counts"]["verdictCount"] == 2
    assert result["counts"]["byVerdict"] == {"not_applicable": 1, "unverified": 1}
    assert [claim["relationshipClaimId"] for claim in result["claims"]] == [
        "column_01.top_point_supports_slab_01.underside_region",
        "door_01.body_hosted_by_wall_01.host_region",
    ]
    supports = result["claims"][0]
    assert supports["relationshipType"] == "supports"
    assert supports["fromObjectId"] == "column-owner"
    assert supports["toObjectId"] == "slab-owner"
    assert supports["fromFeature"] == "column_01.top_point"
    assert supports["toFeature"] == "slab_01.underside_region"
    assert supports["contactKind"] == "point_to_region"
    assert supports["provenance"] == "authored_architectural_fixture"
    assert supports["status"] == "accepted"
    assert supports["claimTypeField"] == "supports"
    assert "method" not in supports


def test_relationship_kernel_filters_claims_without_treating_fuzzy_edges_as_claims():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    result = query_relationship_kernel_report(
        _claim_graph(),
        relationship_types=["supports"],
        object_ids=["column-owner"],
    )

    assert result["counts"]["relationshipClaimCount"] == 1
    assert result["claims"][0]["relationshipType"] == "supports"
    assert result["diagnostics"]["filteredByRelationshipType"] == 1
    assert "near" not in {claim["relationshipType"] for claim in result["claims"]}
```

- [ ] **Step 2: Run the tests and verify they fail because the module does not exist**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py -q
```

Expected: failures with `ImportError` or `ModuleNotFoundError` for `relationship_kernel`.

- [ ] **Step 3: Implement claim normalization**

Create `mcp_server/src/rook/scene/relationship_kernel.py` with:

```python
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
CONTACT_LIKE_RELATIONSHIPS = {"connects", "supports", "touches", "abuts"}
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
    return value is None or (isinstance(value, list) and all(isinstance(item, str) for item in value))


def _invalid_list_result(name: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": f"invalid_{name}",
        "message": f"{name} must be a list of strings when supplied",
    }


def _relationship(attrs: dict[str, Any]) -> str | None:
    value = attrs.get("semanticRelationshipType") or attrs.get("relationship")
    return str(value) if value is not None else None


def _claim_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (str(source), str(target), key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if attrs.get("projectionKind") == CLAIM_PROJECTION_KIND
    ]


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
    return True


def _claim_from_edge(source_id: str, target_id: str, edge_key: Any, attrs: dict[str, Any]) -> dict[str, Any]:
    relationship_type = _relationship(attrs)
    relationship_claim_id = str(
        attrs.get("relationshipClaimId")
        or attrs.get("relationshipFactId")
        or f"{source_id}|{relationship_type}|{target_id}|{edge_key}"
    )
    return {
        "relationshipClaimId": relationship_claim_id,
        "relationshipType": relationship_type,
        "fromObjectId": source_id,
        "toObjectId": target_id,
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
        "sourceMode": attrs.get("sourceMode"),
        "claimTypeField": relationship_type,
        "storage": {
            "projectionKind": attrs.get("projectionKind"),
            "edgeKey": str(edge_key),
        },
    }


def _physical_obligation(claim: dict[str, Any]) -> str:
    relationship_type = str(claim.get("relationshipType") or "")
    contact_kind = str(claim.get("contactKind") or "")
    if relationship_type in NOT_APPLICABLE_RELATIONSHIPS:
        return "not_applicable"
    if relationship_type in CONTACT_LIKE_RELATIONSHIPS and contact_kind in CONTACT_LIKE_KINDS:
        return "exact_adjacency_applicable"
    return "not_applicable"


def _verdict_for_claim(claim: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    obligation = _physical_obligation(claim)
    if obligation == "not_applicable":
        verdict = "not_applicable"
        reason = "no_v1_physical_obligation"
    elif any(item.get("polarity") == "contradicts" and item.get("strength") == "exact_topology" for item in evidence):
        verdict = "contradicted"
        reason = "explicit_exact_topology_refutation"
    elif any(item.get("polarity") == "supports" and item.get("strength") == "exact_topology" for item in evidence):
        verdict = "satisfied"
        reason = "exact_topology_supports_contact"
    else:
        verdict = "unverified"
        reason = "no_applicable_exact_topology_evidence"
    strongest = _strongest_strength(evidence)
    return {
        "relationshipClaimId": claim["relationshipClaimId"],
        "relationshipType": claim.get("relationshipType"),
        "verdict": verdict,
        "reason": reason,
        "physicalObligation": obligation,
        "strongestEvidenceStrength": strongest,
        "evidenceIds": [item["evidenceId"] for item in evidence],
    }


def _strength_rank(strength: str) -> int:
    try:
        return EVIDENCE_STRENGTH_ORDER.index(strength)
    except ValueError:
        return 0


def _strongest_strength(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "none"
    return max((str(item.get("strength") or "none") for item in evidence), key=_strength_rank)


def _empty_report(diagnostics: dict[str, int]) -> dict[str, Any]:
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
        "diagnostics": diagnostics,
    }


def _counts(
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    interface_records: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
) -> dict[str, Any]:
    by_verdict: dict[str, int] = {}
    for verdict in verdicts:
        label = str(verdict.get("verdict") or "unknown")
        by_verdict[label] = by_verdict.get(label, 0) + 1
    return {
        "relationshipClaimCount": len(claims),
        "evidenceCount": len(evidence),
        "interfaceRecordCount": len(interface_records),
        "verdictCount": len(verdicts),
        "byVerdict": dict(sorted(by_verdict.items())),
    }


def query_relationship_kernel_report(
    analytics: Any,
    *,
    object_ids: Any = None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: Any = None,
    relationship_types: Any = None,
    marker_evidence_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    for name, value in (
        ("object_ids", object_ids),
        ("poses", poses),
        ("relationship_types", relationship_types),
    ):
        if not _optional_list_of_strings_is_valid(value):
            return _invalid_list_result(name)

    diagnostics: dict[str, int] = {}
    claims: list[dict[str, Any]] = []
    for source_id, target_id, edge_key, attrs in _claim_edges(analytics.graph):
        if not _matches_filters(
            source_id,
            target_id,
            attrs,
            object_ids=object_ids,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            relationship_types=relationship_types,
            diagnostics=diagnostics,
        ):
            continue
        claims.append(_claim_from_edge(source_id, target_id, edge_key, attrs))

    claims.sort(key=lambda claim: str(claim["relationshipClaimId"]))
    if not claims:
        diagnostics["noRelationshipClaims"] = 1
        return _empty_report(diagnostics)

    evidence_by_claim: dict[str, list[dict[str, Any]]] = {claim["relationshipClaimId"]: [] for claim in claims}
    interface_records: list[dict[str, Any]] = []

    evidence: list[dict[str, Any]] = []
    for claim in claims:
        claim_evidence, claim_interfaces = _evidence_for_claim(
            analytics.graph,
            claim,
            marker_evidence_records=marker_evidence_records or [],
        )
        evidence.extend(claim_evidence)
        interface_records.extend(claim_interfaces)
        evidence_by_claim[claim["relationshipClaimId"]].extend(claim_evidence)

    verdicts = [
        _verdict_for_claim(claim, evidence_by_claim[claim["relationshipClaimId"]])
        for claim in claims
    ]

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


def _evidence_for_claim(
    graph: Any,
    claim: dict[str, Any],
    *,
    marker_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return ([], [])
```

- [ ] **Step 4: Run tests and verify Task 1 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_kernel.py mcp_server/tests/test_relationship_kernel.py
git commit -m "feat: normalize relationship claims"
```

---

### Task 2: Exact Topology Support Evidence and Interface Records

**Files:**
- Modify: `mcp_server/tests/test_relationship_kernel.py`
- Modify: `mcp_server/src/rook/scene/relationship_kernel.py`

- [ ] **Step 1: Add failing tests for `adjacent_exact` support**

Append to `mcp_server/tests/test_relationship_kernel.py`:

```python
def test_adjacent_exact_edge_becomes_exact_topology_evidence_and_interface_record():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="occt:adjacent_exact",
        relationship="adjacent_exact",
        provenance="occt",
        symmetric=True,
        canonical=True,
        sharedArea=12.5,
        lengthUnit="meters",
        areaUnit="meters^2",
        facePairs=[{"sourceFaceIndex": 1, "candidateFaceIndex": 3, "sharedArea": 12.5}],
        graphSequence=42,
        engineVersion=2,
    )

    result = query_relationship_kernel_report(sg, relationship_types=["supports"])

    assert result["counts"]["relationshipClaimCount"] == 1
    assert result["counts"]["evidenceCount"] == 1
    assert result["counts"]["interfaceRecordCount"] == 1
    interface_record = result["interfaceRecords"][0]
    assert interface_record["kind"] == "interface_record_v1"
    assert interface_record["interfaceType"] == "shared_topology"
    assert interface_record["method"] == "adjacent_exact"
    assert interface_record["source"] == "occt"
    assert interface_record["objectIds"] == ["column-owner", "slab-owner"]
    assert interface_record["measures"]["sharedArea"] == 12.5

    evidence = result["evidence"][0]
    assert evidence["relationshipClaimId"] == "column_01.top_point_supports_slab_01.underside_region"
    assert evidence["kind"] == "relationship_evidence_v1"
    assert evidence["method"] == "adjacent_exact"
    assert evidence["source"] == "occt"
    assert evidence["strength"] == "exact_topology"
    assert evidence["polarity"] == "supports"
    assert evidence["status"] == "measured"
    assert evidence["claimTypeField"] == "supports"
    assert evidence["evidenceMethodField"] == "adjacent_exact"
    assert evidence["interfaceRecordIds"] == [interface_record["interfaceRecordId"]]

    verdict = result["verdicts"][0]
    assert verdict["verdict"] == "satisfied"
    assert verdict["reason"] == "exact_topology_supports_contact"
    assert verdict["strongestEvidenceStrength"] == "exact_topology"


def test_adjacent_exact_edge_is_orientation_independent_for_claim_endpoints():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "slab-owner",
        "column-owner",
        key="occt:adjacent_exact",
        relationship="adjacent_exact",
        provenance="occt",
        sharedArea=7.0,
        areaUnit="meters^2",
    )

    result = query_relationship_kernel_report(sg, relationship_types=["supports"])

    assert result["counts"]["evidenceCount"] == 1
    assert result["evidence"][0]["polarity"] == "supports"
    assert result["verdicts"][0]["verdict"] == "satisfied"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py::test_adjacent_exact_edge_becomes_exact_topology_evidence_and_interface_record mcp_server/tests/test_relationship_kernel.py::test_adjacent_exact_edge_is_orientation_independent_for_claim_endpoints -q
```

Expected: failures because `_evidence_for_claim` returns no evidence.

- [ ] **Step 3: Implement exact topology support normalization**

In `mcp_server/src/rook/scene/relationship_kernel.py`, replace `_evidence_for_claim` and add helpers above it:

```python
def _pair_edges(graph: Any, object_a: str, object_b: str) -> list[tuple[str, str, Any, dict[str, Any]]]:
    edges: list[tuple[str, str, Any, dict[str, Any]]] = []
    for source, target in ((object_a, object_b), (object_b, object_a)):
        if not graph.has_edge(source, target):
            continue
        for key, attrs in graph[source][target].items():
            edges.append((source, target, key, dict(attrs)))
    return edges


def _interface_id(claim: dict[str, Any], method: str, source_id: str, target_id: str, edge_key: Any) -> str:
    return f"interface:{method}:{claim['relationshipClaimId']}:{source_id}:{target_id}:{edge_key}"


def _evidence_id(claim: dict[str, Any], method: str, polarity: str) -> str:
    return f"evidence:{method}:{polarity}:{claim['relationshipClaimId']}"


def _exact_support_for_claim(
    graph: Any,
    claim: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    for source_id, target_id, edge_key, attrs in _pair_edges(
        graph,
        str(claim["fromObjectId"]),
        str(claim["toObjectId"]),
    ):
        if attrs.get("relationship") != EXACT_RELATIONSHIP:
            continue
        if attrs.get("provenance") != EXACT_PROVENANCE:
            continue
        interface_id = _interface_id(claim, EXACT_RELATIONSHIP, source_id, target_id, edge_key)
        interface_record = {
            "interfaceRecordId": interface_id,
            "kind": INTERFACE_KIND,
            "interfaceType": "shared_topology",
            "method": EXACT_RELATIONSHIP,
            "source": EXACT_PROVENANCE,
            "objectIds": [str(claim["fromObjectId"]), str(claim["toObjectId"])],
            "featurePaths": [claim.get("fromFeature"), claim.get("toFeature")],
            "measures": {
                "sharedArea": attrs.get("sharedArea"),
                "areaUnit": attrs.get("areaUnit"),
                "lengthUnit": attrs.get("lengthUnit"),
                "facePairs": attrs.get("facePairs", []),
            },
            "storage": {
                "edgeKey": str(edge_key),
                "relationship": attrs.get("relationship"),
                "provenance": attrs.get("provenance"),
                "graphSequence": attrs.get("graphSequence"),
                "engineVersion": attrs.get("engineVersion"),
            },
        }
        interface_records.append(interface_record)
        evidence.append(
            {
                "relationshipClaimId": claim["relationshipClaimId"],
                "evidenceId": _evidence_id(claim, EXACT_RELATIONSHIP, "supports"),
                "kind": EVIDENCE_KIND,
                "method": EXACT_RELATIONSHIP,
                "source": EXACT_PROVENANCE,
                "strength": "exact_topology",
                "polarity": "supports",
                "status": "measured",
                "claimTypeField": claim.get("relationshipType"),
                "evidenceMethodField": EXACT_RELATIONSHIP,
                "measures": interface_record["measures"],
                "interfaceRecordIds": [interface_id],
                "diagnostics": {},
            }
        )
    return evidence, interface_records


def _evidence_for_claim(
    graph: Any,
    claim: dict[str, Any],
    *,
    marker_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence, interface_records = _exact_support_for_claim(graph, claim)
    return (evidence, interface_records)
```

- [ ] **Step 4: Run tests and verify Task 2 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_kernel.py mcp_server/tests/test_relationship_kernel.py
git commit -m "feat: normalize exact topology support evidence"
```

---

### Task 3: Exact Refutation and the Absence-Is-Not-Refutation Rule

**Files:**
- Modify: `mcp_server/tests/test_relationship_kernel.py`
- Modify: `mcp_server/src/rook/scene/relationship_kernel.py`

- [ ] **Step 1: Add failing tests for absence and explicit refutation**

Append to `mcp_server/tests/test_relationship_kernel.py`:

```python
def test_absent_adjacent_exact_does_not_contradict_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    result = query_relationship_kernel_report(_claim_graph(), relationship_types=["supports"])

    assert result["counts"]["evidenceCount"] == 0
    assert result["verdicts"][0]["verdict"] == "unverified"
    assert result["verdicts"][0]["reason"] == "no_applicable_exact_topology_evidence"


def test_exact_refuted_annotation_becomes_contradicting_evidence():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="spatial-adjacent",
        relationship="adjacent",
        exact_status="exact_refuted",
        exact_reason="no_shared_face",
        exact_graphSequence=42,
    )

    result = query_relationship_kernel_report(sg, relationship_types=["supports"])

    assert result["counts"]["evidenceCount"] == 1
    assert result["counts"]["interfaceRecordCount"] == 1
    evidence = result["evidence"][0]
    assert evidence["strength"] == "exact_topology"
    assert evidence["polarity"] == "contradicts"
    assert evidence["status"] == "measured"
    assert evidence["method"] == "adjacent_exact_refutation"
    assert evidence["measures"]["reason"] == "no_shared_face"
    assert result["verdicts"][0]["verdict"] == "contradicted"
    assert result["verdicts"][0]["reason"] == "explicit_exact_topology_refutation"


def test_exact_refuted_annotation_on_unrelated_pair_does_not_contradict_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_node("beam-owner", name="beam_01")
    sg.graph.add_edge(
        "column-owner",
        "beam-owner",
        key="spatial-adjacent",
        relationship="adjacent",
        exact_status="exact_refuted",
        exact_reason="no_shared_face",
    )

    result = query_relationship_kernel_report(sg, relationship_types=["supports"])

    assert result["counts"]["evidenceCount"] == 0
    assert result["verdicts"][0]["verdict"] == "unverified"
```

- [ ] **Step 2: Run the new refutation tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py::test_exact_refuted_annotation_becomes_contradicting_evidence mcp_server/tests/test_relationship_kernel.py::test_exact_refuted_annotation_on_unrelated_pair_does_not_contradict_claim -q
```

Expected: first test fails because no refutation evidence is produced; second may already pass.

- [ ] **Step 3: Implement exact refutation normalization**

In `mcp_server/src/rook/scene/relationship_kernel.py`, add:

```python
EXACT_REFUTATION_METHOD = "adjacent_exact_refutation"
```

Add helper above `_evidence_for_claim`:

```python
def _exact_refutation_for_claim(
    graph: Any,
    claim: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    for source_id, target_id, edge_key, attrs in _pair_edges(
        graph,
        str(claim["fromObjectId"]),
        str(claim["toObjectId"]),
    ):
        if attrs.get("exact_status") != "exact_refuted":
            continue
        interface_id = _interface_id(claim, EXACT_REFUTATION_METHOD, source_id, target_id, edge_key)
        reason = attrs.get("exact_reason") or "exact_refuted"
        interface_record = {
            "interfaceRecordId": interface_id,
            "kind": INTERFACE_KIND,
            "interfaceType": "shared_topology_refutation",
            "method": EXACT_REFUTATION_METHOD,
            "source": EXACT_PROVENANCE,
            "objectIds": [str(claim["fromObjectId"]), str(claim["toObjectId"])],
            "featurePaths": [claim.get("fromFeature"), claim.get("toFeature")],
            "measures": {
                "reason": reason,
            },
            "storage": {
                "edgeKey": str(edge_key),
                "relationship": attrs.get("relationship"),
                "exactStatus": attrs.get("exact_status"),
                "exactReason": attrs.get("exact_reason"),
                "graphSequence": attrs.get("exact_graphSequence"),
            },
        }
        interface_records.append(interface_record)
        evidence.append(
            {
                "relationshipClaimId": claim["relationshipClaimId"],
                "evidenceId": _evidence_id(claim, EXACT_REFUTATION_METHOD, "contradicts"),
                "kind": EVIDENCE_KIND,
                "method": EXACT_REFUTATION_METHOD,
                "source": EXACT_PROVENANCE,
                "strength": "exact_topology",
                "polarity": "contradicts",
                "status": "measured",
                "claimTypeField": claim.get("relationshipType"),
                "evidenceMethodField": EXACT_REFUTATION_METHOD,
                "measures": interface_record["measures"],
                "interfaceRecordIds": [interface_id],
                "diagnostics": {},
            }
        )
    return evidence, interface_records
```

Replace `_evidence_for_claim` with:

```python
def _evidence_for_claim(
    graph: Any,
    claim: dict[str, Any],
    *,
    marker_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    for builder in (_exact_support_for_claim, _exact_refutation_for_claim):
        built_evidence, built_interfaces = builder(graph, claim)
        evidence.extend(built_evidence)
        interface_records.extend(built_interfaces)
    return (evidence, interface_records)
```

- [ ] **Step 4: Run tests and verify Task 3 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py -q
```

Expected: `9 passed`.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_kernel.py mcp_server/tests/test_relationship_kernel.py
git commit -m "feat: normalize exact topology refutations"
```

---

### Task 4: Marker-Hint Evidence Normalization Without Satisfaction

**Files:**
- Modify: `mcp_server/tests/test_relationship_kernel.py`
- Modify: `mcp_server/src/rook/scene/relationship_kernel.py`

- [ ] **Step 1: Add failing tests for marker evidence strength**

Append to `mcp_server/tests/test_relationship_kernel.py`:

```python
def test_marker_evidence_is_marker_hint_and_does_not_satisfy_physical_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    marker_evidence_records = [
        {
            "relationshipFactId": "column_01.top_point_supports_slab_01.underside_region",
            "relationship": "supports",
            "evidence": {
                "kind": "relationship_geometry_evidence_v1",
                "method": "feature_marker_position_distance",
                "status": "measured",
                "distanceM": 0.0,
                "toleranceM": 0.01,
                "withinTolerance": True,
                "source": "rhino_user_text_feature_positions",
            },
        }
    ]

    result = query_relationship_kernel_report(
        _claim_graph(),
        relationship_types=["supports"],
        marker_evidence_records=marker_evidence_records,
    )

    assert result["counts"]["evidenceCount"] == 1
    evidence = result["evidence"][0]
    assert evidence["method"] == "feature_marker_position_distance"
    assert evidence["source"] == "rhino_user_text_feature_positions"
    assert evidence["strength"] == "marker_hint"
    assert evidence["polarity"] == "supports"
    assert evidence["status"] == "measured"
    assert evidence["measures"]["distanceM"] == 0.0
    assert result["verdicts"][0]["verdict"] == "unverified"
    assert result["verdicts"][0]["strongestEvidenceStrength"] == "marker_hint"


def test_missing_marker_evidence_is_missing_and_keeps_claim_unverified():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    marker_evidence_records = [
        {
            "relationshipFactId": "column_01.top_point_supports_slab_01.underside_region",
            "relationship": "supports",
            "evidence": {
                "kind": "relationship_geometry_evidence_v1",
                "method": "feature_marker_position_distance",
                "status": "missing",
                "missing": ["fromFeaturePosition"],
                "withinTolerance": None,
                "source": "rhino_user_text_feature_positions",
            },
        }
    ]

    result = query_relationship_kernel_report(
        _claim_graph(),
        relationship_types=["supports"],
        marker_evidence_records=marker_evidence_records,
    )

    evidence = result["evidence"][0]
    assert evidence["strength"] == "marker_hint"
    assert evidence["polarity"] == "missing"
    assert evidence["status"] == "missing"
    assert evidence["diagnostics"] == {"missing": ["fromFeaturePosition"]}
    assert result["verdicts"][0]["verdict"] == "unverified"
```

- [ ] **Step 2: Run marker tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py::test_marker_evidence_is_marker_hint_and_does_not_satisfy_physical_claim mcp_server/tests/test_relationship_kernel.py::test_missing_marker_evidence_is_missing_and_keeps_claim_unverified -q
```

Expected: failures because marker evidence is ignored.

- [ ] **Step 3: Implement marker evidence normalization**

In `mcp_server/src/rook/scene/relationship_kernel.py`, add helpers above `_evidence_for_claim`:

```python
def _marker_record_claim_id(record: dict[str, Any]) -> str | None:
    value = record.get("relationshipClaimId") or record.get("relationshipFactId")
    return str(value) if value else None


def _marker_hint_for_claim(
    claim: dict[str, Any],
    marker_evidence_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, record in enumerate(marker_evidence_records):
        if _marker_record_claim_id(record) != claim["relationshipClaimId"]:
            continue
        raw = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        status = str(raw.get("status") or "missing")
        within_tolerance = raw.get("withinTolerance")
        if status == "measured" and within_tolerance is True:
            polarity = "supports"
        elif status == "measured" and within_tolerance is False:
            polarity = "contradicts"
        elif status == "missing":
            polarity = "missing"
        else:
            polarity = "neutral"
        evidence.append(
            {
                "relationshipClaimId": claim["relationshipClaimId"],
                "evidenceId": f"evidence:marker_hint:{claim['relationshipClaimId']}:{index}",
                "kind": EVIDENCE_KIND,
                "method": str(raw.get("method") or "feature_marker_position_distance"),
                "source": str(raw.get("source") or "rhino_user_text_feature_positions"),
                "strength": "marker_hint",
                "polarity": polarity,
                "status": status,
                "claimTypeField": claim.get("relationshipType"),
                "evidenceMethodField": str(raw.get("method") or "feature_marker_position_distance"),
                "measures": {
                    key: raw.get(key)
                    for key in ("distanceM", "toleranceM", "withinTolerance")
                    if key in raw
                },
                "interfaceRecordIds": [],
                "diagnostics": {"missing": raw.get("missing", [])} if raw.get("missing") else {},
            }
        )
    return evidence
```

Replace `_evidence_for_claim` with:

```python
def _evidence_for_claim(
    graph: Any,
    claim: dict[str, Any],
    *,
    marker_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    interface_records: list[dict[str, Any]] = []
    for builder in (_exact_support_for_claim, _exact_refutation_for_claim):
        built_evidence, built_interfaces = builder(graph, claim)
        evidence.extend(built_evidence)
        interface_records.extend(built_interfaces)
    evidence.extend(_marker_hint_for_claim(claim, marker_evidence_records))
    return (evidence, interface_records)
```

- [ ] **Step 4: Run tests and verify Task 4 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py -q
```

Expected: `11 passed`.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_kernel.py mcp_server/tests/test_relationship_kernel.py
git commit -m "feat: normalize marker hint evidence"
```

---

### Task 5: V1 Applicability and Conflict Guardrails

**Files:**
- Modify: `mcp_server/tests/test_relationship_kernel.py`
- Modify: `mcp_server/src/rook/scene/relationship_kernel.py`

- [ ] **Step 1: Add failing tests for v1 applicability and strength conflict behavior**

Append to `mcp_server/tests/test_relationship_kernel.py`:

```python
def test_hosted_by_remains_not_applicable_even_with_adjacent_exact():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "door-owner",
        "wall-owner",
        key="occt:adjacent_exact",
        relationship="adjacent_exact",
        provenance="occt",
        sharedArea=2.0,
    )

    result = query_relationship_kernel_report(sg, relationship_types=["hosted_by"])

    assert result["counts"]["evidenceCount"] == 1
    assert result["evidence"][0]["strength"] == "exact_topology"
    assert result["verdicts"][0]["verdict"] == "not_applicable"
    assert result["verdicts"][0]["reason"] == "no_v1_physical_obligation"


def test_penetrates_is_not_applicable_to_adjacent_exact_in_v1():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = SceneGraphAnalytics()
    sg.graph.add_node("duct-owner", name="duct_01")
    sg.graph.add_node("wall-owner", name="wall_01")
    sg.graph.add_edge(
        "duct-owner",
        "wall-owner",
        key="relationship_fact:architectural:penetrates",
        relationship="penetrates",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="penetrates",
        relationshipFactId="duct_01.centerline_penetrates_wall_01.penetration_region",
        fromFeature="duct_01.centerline",
        toFeature="wall_01.penetration_region",
        contactKind="line_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "duct-owner",
        "wall-owner",
        key="occt:adjacent_exact",
        relationship="adjacent_exact",
        provenance="occt",
        sharedArea=1.0,
    )

    result = query_relationship_kernel_report(sg)

    assert result["counts"]["evidenceCount"] == 1
    assert result["verdicts"][0]["verdict"] == "not_applicable"
    assert result["verdicts"][0]["physicalObligation"] == "not_applicable"


def test_exact_refutation_beats_marker_hint_without_using_strength_order_as_higher_wins():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="spatial-adjacent",
        relationship="adjacent",
        exact_status="exact_refuted",
        exact_reason="no_shared_face",
    )
    marker_evidence_records = [
        {
            "relationshipFactId": "column_01.top_point_supports_slab_01.underside_region",
            "relationship": "supports",
            "evidence": {
                "kind": "relationship_geometry_evidence_v1",
                "method": "feature_marker_position_distance",
                "status": "measured",
                "distanceM": 0.0,
                "toleranceM": 0.01,
                "withinTolerance": True,
                "source": "rhino_user_text_feature_positions",
            },
        }
    ]

    result = query_relationship_kernel_report(
        sg,
        relationship_types=["supports"],
        marker_evidence_records=marker_evidence_records,
    )

    assert {item["strength"] for item in result["evidence"]} == {"exact_topology", "marker_hint"}
    assert {item["polarity"] for item in result["evidence"]} == {"contradicts", "supports"}
    assert result["verdicts"][0]["verdict"] == "contradicted"
    assert result["verdicts"][0]["reason"] == "explicit_exact_topology_refutation"
```

- [ ] **Step 2: Run the applicability tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py::test_hosted_by_remains_not_applicable_even_with_adjacent_exact mcp_server/tests/test_relationship_kernel.py::test_penetrates_is_not_applicable_to_adjacent_exact_in_v1 mcp_server/tests/test_relationship_kernel.py::test_exact_refutation_beats_marker_hint_without_using_strength_order_as_higher_wins -q
```

Expected: tests should pass if Task 1 verdict logic was implemented as specified. If any fail, patch only `_physical_obligation` or `_verdict_for_claim`; do not change evidence normalization.

- [ ] **Step 3: Run all relationship kernel tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py -q
```

Expected: `14 passed`.

- [ ] **Step 4: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_kernel.py mcp_server/tests/test_relationship_kernel.py
git commit -m "test: lock relationship kernel applicability rules"
```

---

### Task 6: Regression Suites and No-Public-Tool Guard

**Files:**
- Modify: `mcp_server/tests/test_relationship_kernel.py`

- [ ] **Step 1: Add guard test that this slice does not register a new MCP tool**

Append to `mcp_server/tests/test_relationship_kernel.py`:

```python
def test_relationship_kernel_is_not_registered_as_public_tool():
    from rook.agent.tool_groups import TOOL_GROUPS
    from rook import targeting

    all_grouped_tools = {tool for tools in TOOL_GROUPS.values() for tool in tools}

    assert "scene_relationship_kernel" not in all_grouped_tools
    assert "scene_relationship_kernel_report" not in all_grouped_tools
    assert "scene_relationship_kernel" not in targeting._ALL_KNOWN_TOOLS
    assert "scene_relationship_kernel_report" not in targeting._ALL_KNOWN_TOOLS
```

- [ ] **Step 2: Run the guard test**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py::test_relationship_kernel_is_not_registered_as_public_tool -q
```

Expected: `1 passed`.

- [ ] **Step 3: Run focused relationship/kernel/evidence suites**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py mcp_server/tests/test_relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence_tool.py mcp_server/tests/test_exact_projection.py -q
```

Expected: all tests pass. Expected count after this plan is at least `mcp_server/tests/test_relationship_kernel.py` 15 tests plus existing evidence/exact tests.

- [ ] **Step 4: Run semantic/projection regression suites**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py mcp_server/tests/test_relationship_profile.py mcp_server/tests/test_relationship_profile_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run whitespace and status checks**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: `git diff --check` has no output and exits 0. `git status --short --branch` shows only intentional changes before commit.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_kernel.py mcp_server/tests/test_relationship_kernel.py
git commit -m "test: guard relationship kernel as internal read model"
```

---

## Final Verification

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_kernel.py mcp_server/tests/test_relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence_tool.py mcp_server/tests/test_exact_projection.py -q

python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py mcp_server/tests/test_relationship_profile.py mcp_server/tests/test_relationship_profile_tool.py -q

git diff --check
git show --check --stat HEAD
git status --short --branch
```

Expected:

- all pytest commands pass;
- `git diff --check` passes;
- `git show --check --stat HEAD` passes;
- worktree is clean after the final commit.

Do not run live Rhino gates for this slice unless a reviewer specifically asks. This implementation is pure and deliberately avoids Rhino calls.

## Self-Review Checklist

Before handing this branch to review, verify:

- `relationship_fact_v1` is normalized as `RelationshipClaim`.
- `adjacent_exact` is normalized as `RelationshipEvidence` with `strength="exact_topology"` and `method="adjacent_exact"`.
- Exact refutation annotations are normalized as `RelationshipEvidence` with `polarity="contradicts"`.
- Missing `adjacent_exact` produces `unverified`, not `contradicted`.
- Marker evidence is `marker_hint` and cannot satisfy a physical claim in v1.
- `penetrates` and `hosted_by` are `not_applicable` for adjacent-exact verdicts in v1.
- Claim type and evidence method are separate fields in output.
- No MCP tool, server dispatch, tool group, or targeting registration was added.
