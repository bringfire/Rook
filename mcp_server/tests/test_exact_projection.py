"""Unit tests for ExactAdjacencyProjector — the Python read-model projection layer.

No live Rhino: the OCCT exact route is faked by monkeypatching
rook.scene.exact_projection.call_rhino, and the mirror graph is populated directly.
"""
import asyncio

import pytest

from rook.scene.exact_projection import (
    _canonical_pair,
    EXACT_EDGE_KEY,
    EXACT_RELATIONSHIP,
    EXACT_PROVENANCE,
    ENGINE_VERSION,
    DEFAULT_CANDIDATE_SCOPE,
)


def test_canonical_pair_is_orientation_independent():
    assert _canonical_pair("B", "A") == ("A", "B")
    assert _canonical_pair("A", "B") == ("A", "B")
    # idempotent under re-canonicalization
    a, b = _canonical_pair("zzz", "aaa")
    assert _canonical_pair(a, b) == ("aaa", "zzz")


def test_module_constants():
    assert EXACT_EDGE_KEY == "occt:adjacent_exact"
    assert EXACT_RELATIONSHIP == "adjacent_exact"
    assert EXACT_PROVENANCE == "occt"
    assert ENGINE_VERSION == 2
    assert DEFAULT_CANDIDATE_SCOPE == "broad_phase_default"


from rook.scene.exact_projection import ExactAdjacencyProjector
from rook.scene.scene_graph import SceneGraphAnalytics


def _projector_with_nodes(*node_ids) -> ExactAdjacencyProjector:
    sg = SceneGraphAnalytics()
    for nid in node_ids:
        sg.graph.add_node(nid, name=nid)
    return ExactAdjacencyProjector(sg)


def test_upsert_is_idempotent_and_canonical():
    proj = _projector_with_nodes("A", "B")
    attrs = {"relationship": EXACT_RELATIONSHIP, "provenance": EXACT_PROVENANCE,
             "sharedArea": 10.0, "graphSequence": 1}

    # Project the A->B fact (queried from A).
    proj._upsert_exact_edge("A", "B", dict(attrs))
    # Later project from B: route returns B->A; same canonical key must update, not duplicate.
    proj._upsert_exact_edge("B", "A", dict(attrs, sharedArea=10.0))

    g = proj._analytics.graph
    # Exactly one occt edge, stored canonically as (A, B).
    occt_edges = [(u, v, k) for u, v, k in g.edges(keys=True)
                  if k == EXACT_EDGE_KEY]
    assert occt_edges == [("A", "B", EXACT_EDGE_KEY)]
    assert g["A"]["B"][EXACT_EDGE_KEY]["sharedArea"] == 10.0


# A fixture route payload mirroring SpatialTest: 2 confirmed abutments,
# 1 evaluable candidate with no shared face (refuted), 1 unsupported candidate (failed).
_ROUTE_PAYLOAD = {
    "objectId": "A",
    "graphSequence": 7,
    "sourceCapability": "exact_brep",
    "lengthUnit": "inches",
    "areaUnit": "inches^2",
    "edges": [
        {"targetId": "B", "relationship": "adjacent_exact", "sharedArea": 3311.978,
         "facePairs": [{"sourceFaceIndex": 0, "candidateFaceIndex": 2, "sharedArea": 3311.978}]},
        {"targetId": "C", "relationship": "adjacent_exact", "sharedArea": 5440.438,
         "facePairs": [{"sourceFaceIndex": 1, "candidateFaceIndex": 0, "sharedArea": 5440.438}]},
    ],
    "candidates": [
        {"id": "B", "capability": "exact_brep"},
        {"id": "C", "capability": "exact_brep"},
        {"id": "D", "capability": "exact_brep"},          # considered, no edge -> refuted
        {"id": "E", "capability": "unsupported_geometry"},  # considered, no edge -> failed
    ],
}


def test_prepare_and_commit_projects_edges_and_annotations():
    proj = _projector_with_nodes("A", "B", "C", "D", "E")
    g = proj._analytics.graph
    # Pre-existing bbox 'adjacent' edges the projection should annotate.
    g.add_edge("A", "B", relationship="adjacent", distance=0.0)
    g.add_edge("A", "D", relationship="adjacent", distance=0.0)
    g.add_edge("A", "E", relationship="adjacent", distance=0.0)

    delta = proj._prepare_source_delta("A", _ROUTE_PAYLOAD, graph_sequence=7)
    # prepare must not mutate the graph yet
    assert not any(k == EXACT_EDGE_KEY for _, _, k in g.edges(keys=True))

    proj._commit_source_delta(delta)

    # Two canonical exact edges.
    occt = sorted((u, v) for u, v, k in g.edges(keys=True) if k == EXACT_EDGE_KEY)
    assert occt == [("A", "B"), ("A", "C")]
    eAB = g["A"]["B"][EXACT_EDGE_KEY]
    assert eAB["sharedArea"] == 3311.978
    assert eAB["areaUnit"] == "inches^2"
    assert eAB["provenance"] == "occt"
    assert eAB["capabilitiesById"] == {"A": "exact_brep", "B": "exact_brep"}
    assert eAB["facePairsFrom"] == "queried_source_to_candidate"

    # bbox A-B confirmed; A-D refuted; A-E failed.
    def bbox(u, v):
        return g[u][v][0]  # first (auto-keyed) bbox edge
    assert bbox("A", "B")["exact_status"] == "exact_confirmed"
    assert bbox("A", "B")["approximate"] is True
    assert bbox("A", "D")["exact_status"] == "exact_refuted"
    assert bbox("A", "D")["exact_reason"] == "no_shared_face"
    assert bbox("A", "E")["exact_status"] == "exact_failed"

    # response classification
    assert {n["id"] for n in delta.neighbors} == {"B", "C"}
    assert {r["id"] for r in delta.refuted} == {"D"}
    assert {f["id"] for f in delta.failed} == {"E"}


def test_commit_atomicity_parse_failure_leaves_graph_unmutated():
    proj = _projector_with_nodes("A", "B")
    g = proj._analytics.graph
    bad_payload = {"edges": [{"targetId": "B", "sharedArea": object()}], "candidates": "not-a-list"}
    # prepare raises on the malformed candidates; commit is never reached.
    with pytest.raises(Exception):
        delta = proj._prepare_source_delta("A", bad_payload, graph_sequence=1)
        proj._commit_source_delta(delta)
    assert not any(k == EXACT_EDGE_KEY for _, _, k in g.edges(keys=True))
