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


def test_prune_on_advance_removes_artifacts_and_invalidates_caches():
    proj = _projector_with_nodes("A", "B")
    g = proj._analytics.graph
    g.add_edge("A", "B", relationship="adjacent", distance=0.0)
    # Project an exact edge + annotate the bbox edge.
    proj._upsert_exact_edge("A", "B", {
        "relationship": EXACT_RELATIONSHIP, "provenance": EXACT_PROVENANCE,
        "sharedArea": 10.0, "graphSequence": 1, "engineVersion": ENGINE_VERSION})
    g["A"]["B"][0].update({"approximate": True, "exact_status": "exact_confirmed",
                           "exact_graphSequence": 1})
    # Prime analytics caches.
    proj._analytics._communities = {"group_0": ["A", "B"]}
    proj._analytics._centrality = {"A": 1.0}

    proj._purge_projection_artifacts()

    # occt edge gone; bbox edge kept but annotations stripped.
    assert not any(k == EXACT_EDGE_KEY for _, _, k in g.edges(keys=True))
    assert g.has_edge("A", "B")
    bbox = g["A"]["B"][0]
    for fld in ("approximate", "exact_status", "exact_reason",
                "exact_diagnostics", "exact_graphSequence"):
        assert fld not in bbox
    # analytics caches invalidated
    assert proj._analytics._communities is None
    assert proj._analytics._centrality is None


def test_prune_if_advanced_only_on_sequence_change():
    proj = _projector_with_nodes("A")
    proj._cache[("k",)] = {"sourceId": "A"}
    proj._cache_sequence = 5
    # Same sequence: cache preserved.
    proj._prune_if_advanced(5)
    assert proj._cache != {}
    # Advanced sequence: cache cleared + sequence updated.
    proj._prune_if_advanced(6)
    assert proj._cache == {}
    assert proj._cache_sequence == 6


import rook.scene.exact_projection as ep
from rook.scene.exact_projection import get_exact_projector


def _stub_sync(analytics, sequence):
    """Replace analytics.sync with an async no-op that sets the sequence."""
    async def _sync(port=None):
        analytics._sequence = sequence
        return {"synced": True, "sequence": sequence}
    analytics.sync = _sync  # type: ignore[assignment]


def test_project_full_payload_and_cache_hit(monkeypatch):
    proj = _projector_with_nodes("A", "B", "C", "D", "E")
    _stub_sync(proj._analytics, 7)

    calls = {"n": 0}

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None, **kw):
        calls["n"] += 1
        assert endpoint == "/scene/graph/adjacency/exact"
        assert data["objectId"] == "A"
        return {"success": True, "data": _ROUTE_PAYLOAD}

    monkeypatch.setattr(ep, "call_rhino", fake_call_rhino)

    out = asyncio.run(proj.project(["A"]))
    assert out["success"] is True
    assert out["graphSequence"] == 7
    assert out["unitsUniform"] is True
    assert out["areaUnit"] == "inches^2"
    block = out["projected"][0]
    assert block["routeStatus"] == "ok"
    assert {n["id"] for n in block["neighbors"]} == {"B", "C"}
    assert all(n["fromCache"] is False for n in block["neighbors"])
    assert out["cache"] == {"hits": 0, "misses": 1}

    # Second call: cache hit, no new route call, neighbors flagged fromCache.
    out2 = asyncio.run(proj.project(["A"]))
    assert calls["n"] == 1
    assert out2["cache"] == {"hits": 1, "misses": 0}
    assert all(n["fromCache"] is True for n in out2["projected"][0]["neighbors"])


def test_project_skipped_when_object_not_in_scene(monkeypatch):
    proj = _projector_with_nodes("A")  # 'Z' absent
    _stub_sync(proj._analytics, 1)
    monkeypatch.setattr(ep, "call_rhino", _should_not_be_called)
    out = asyncio.run(proj.project(["Z"]))
    block = out["projected"][0]
    assert block["routeStatus"] == "skipped"
    assert block["error"] == "object_not_in_scene"
    assert block["neighbors"] == []


def test_project_isolates_route_failure(monkeypatch):
    proj = _projector_with_nodes("A", "B")
    _stub_sync(proj._analytics, 1)

    async def failing(endpoint, method="GET", data=None, port=None, **kw):
        return {"success": False, "data": "boom"}

    monkeypatch.setattr(ep, "call_rhino", failing)
    out = asyncio.run(proj.project(["A"]))
    block = out["projected"][0]
    assert block["routeStatus"] == "failed"
    assert block["error"] == "boom"
    # Approximate graph still usable: no exact edges, no crash.
    assert not any(k == EXACT_EDGE_KEY for _, _, k in proj._analytics.graph.edges(keys=True))


def test_project_does_not_cache_transient_failure(monkeypatch):
    proj = _projector_with_nodes("A", "B")
    _stub_sync(proj._analytics, 1)
    calls = {"n": 0}

    async def failing(endpoint, method="GET", data=None, port=None, **kw):
        calls["n"] += 1
        return {"success": False, "data": "request timeout"}

    monkeypatch.setattr(ep, "call_rhino", failing)
    out1 = asyncio.run(proj.project(["A"]))
    assert out1["projected"][0]["routeStatus"] == "timeout"
    # Second call must RETRY (not serve a cached failure).
    out2 = asyncio.run(proj.project(["A"]))
    assert calls["n"] == 2
    assert out2["cache"] == {"hits": 0, "misses": 1}


def test_project_rejects_unsupported_candidate_scope():
    proj = _projector_with_nodes("A")
    _stub_sync(proj._analytics, 1)
    out = asyncio.run(proj.project(["A"], candidate_scope="radius"))
    assert out["success"] is False
    assert "unsupported candidate_scope" in out["error"]


def test_project_units_not_uniform_omits_top_level(monkeypatch):
    proj = _projector_with_nodes("A", "B", "M", "N")
    _stub_sync(proj._analytics, 3)
    payload_in = {"objectId": "A", "sourceCapability": "exact_brep",
                  "lengthUnit": "inches", "areaUnit": "inches^2",
                  "edges": [{"targetId": "B", "sharedArea": 1.0, "facePairs": []}],
                  "candidates": [{"id": "B", "capability": "exact_brep"}]}
    payload_mm = {"objectId": "M", "sourceCapability": "exact_brep",
                  "lengthUnit": "millimeters", "areaUnit": "millimeters^2",
                  "edges": [{"targetId": "N", "sharedArea": 2.0, "facePairs": []}],
                  "candidates": [{"id": "N", "capability": "exact_brep"}]}

    async def fake(endpoint, method="GET", data=None, port=None, **kw):
        return {"success": True, "data": payload_in if data["objectId"] == "A" else payload_mm}

    monkeypatch.setattr(ep, "call_rhino", fake)
    out = asyncio.run(proj.project(["A", "M"]))
    assert out["unitsUniform"] is False
    assert "areaUnit" not in out  # top-level units omitted on conflict
    assert "lengthUnit" not in out
    # edge-level units remain the source of truth
    assert out["projected"][0]["areaUnit"] == "inches^2"
    assert out["projected"][1]["areaUnit"] == "millimeters^2"


def test_project_invalidates_analytics_caches_on_commit(monkeypatch):
    proj = _projector_with_nodes("A", "B")
    _stub_sync(proj._analytics, 4)
    # Pin cache_sequence to the synced sequence so _prune_if_advanced is a no-op:
    # this isolates the COMMIT path as the thing that invalidates the caches.
    proj._cache_sequence = 4
    # Prime analytics caches BEFORE projecting.
    proj._analytics._communities = {"group_0": ["A", "B"]}
    proj._analytics._centrality = {"A": 1.0}

    async def fake(endpoint, method="GET", data=None, port=None, **kw):
        return {"success": True, "data": {
            "objectId": "A", "sourceCapability": "exact_brep",
            "lengthUnit": "inches", "areaUnit": "inches^2",
            "edges": [{"targetId": "B", "sharedArea": 9.0, "facePairs": []}],
            "candidates": [{"id": "B", "capability": "exact_brep"}]}}

    monkeypatch.setattr(ep, "call_rhino", fake)
    asyncio.run(proj.project(["A"]))
    # The commit mutated the graph -> cached analytics objects dropped.
    assert proj._analytics._communities is None
    assert proj._analytics._centrality is None


async def _should_not_be_called(*a, **k):
    raise AssertionError("call_rhino must not be called for a skipped source")


from rook.scene.scene_graph import _inverse_rel


def test_get_context_renders_exact_adjacency():
    proj = _projector_with_nodes("A", "B")
    sg = proj._analytics
    sg.graph.nodes["A"]["domain_label"] = "floor"
    sg.graph.nodes["B"]["domain_label"] = "wall"
    sg.graph.nodes["B"]["name"] = "Wall-01"
    proj._upsert_exact_edge("A", "B", {
        "relationship": EXACT_RELATIONSHIP, "provenance": EXACT_PROVENANCE,
        "sharedArea": 3311.978, "areaUnit": "inches^2", "graphSequence": 1})
    text = sg.get_context(["A"])
    assert "adjacent to (exact)" in text or "exact" in text.lower()
    assert "3311.98" in text
    assert "inches^2" in text  # rendered from the edge's own areaUnit, not hardcoded


def test_inverse_rel_knows_adjacent_exact():
    assert _inverse_rel("adjacent_exact") == "adjacent to (exact)"


def test_tool_registered_in_scene_graph_group():
    from rook.agent.tool_groups import TOOL_GROUPS
    assert "scene_exact_neighbors" in TOOL_GROUPS["scene_graph"]


def test_local_handler_registered_for_agent_direct_path():
    from rook.agent.tool_dispatcher import build_local_tools
    tools = build_local_tools()
    assert "scene_exact_neighbors" in tools
    assert callable(tools["scene_exact_neighbors"])
