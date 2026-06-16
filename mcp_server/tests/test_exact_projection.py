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
