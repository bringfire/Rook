"""Unit tests for ContainmentRefiner — the Python read-model semantic containment layer.

No live Rhino: the scene-graph mirror is populated directly. The refiner must never
call the exact projector or any new geometry route; adjacent_exact edges are consumed only
if already present.
"""
import asyncio

import pytest

from rook.scene.containment_refinement import (
    candidate_id,
    SEMANTIC_CONTAINS_KEY,
    SEMANTIC_RELATIONSHIP,
    SEMANTIC_PROVENANCE,
    ENGINE_VERSION,
    SOLID_TYPES,
    NON_SOLID_TYPES,
)


def test_candidate_id_format():
    assert candidate_id("A", "B") == "A|contains|B"
    # directional — order matters
    assert candidate_id("B", "A") == "B|contains|A"


def test_module_constants():
    assert SEMANTIC_CONTAINS_KEY == "semantic:contains"
    assert SEMANTIC_RELATIONSHIP == "contains_semantic"
    assert SEMANTIC_PROVENANCE == "semantic_refiner"
    assert ENGINE_VERSION == 1
    assert "Brep" in SOLID_TYPES and "Extrusion" in SOLID_TYPES
    assert "Curve" in NON_SOLID_TYPES and "Point" in NON_SOLID_TYPES


from rook.scene.containment_refinement import (
    _bbox_volume, _evidence_bbox_margin, _evidence_containment_depth,
    _evidence_container_solidity, _evidence_class_pair, _evidence_volume_ratio,
    _evidence_grouping, _spans_thin_axis,
)


def _attrs(geometry_type="Brep", shape_class="compact", domain_label="",
           bbox_min=(0, 0, 0), bbox_max=(10, 10, 10), layer="L", name="n",
           thin_axis=""):
    return {
        "geometry_type": geometry_type, "shape_class": shape_class,
        "domain_label": domain_label, "bbox_min": list(bbox_min),
        "bbox_max": list(bbox_max), "layer": layer, "name": name, "thin_axis": thin_axis,
    }


def test_bbox_margin_supports_when_clear_on_all_axes():
    c = _attrs(bbox_min=(0, 0, 0), bbox_max=(10, 10, 10))
    b = _attrs(bbox_min=(2, 2, 2), bbox_max=(8, 8, 8))
    ev = _evidence_bbox_margin(c, b)
    assert ev["polarity"] == "supports"


def test_bbox_margin_weakens_when_flush_on_an_axis():
    c = _attrs(bbox_min=(0, 0, 0), bbox_max=(10, 10, 10))
    b = _attrs(bbox_min=(0, 2, 2), bbox_max=(8, 8, 8))  # flush on X-low
    ev = _evidence_bbox_margin(c, b)
    assert ev["polarity"] == "weakens"


def test_container_solidity_polarities():
    assert _evidence_container_solidity(_attrs(geometry_type="Brep"))["polarity"] == "supports"
    assert _evidence_container_solidity(_attrs(geometry_type="Curve"))["polarity"] == "disqualifies"
    assert _evidence_container_solidity(_attrs(geometry_type="Surface"))["polarity"] == "weakens"
    # Mesh/SubD: neutral -> None (neither support nor disqualify)
    assert _evidence_container_solidity(_attrs(geometry_type="Mesh")) is None
    assert _evidence_container_solidity(_attrs(geometry_type="SubD")) is None


def test_class_pair_supports_compact_weakens_thin():
    assert _evidence_class_pair(_attrs(shape_class="compact"))["polarity"] == "supports"
    assert _evidence_class_pair(_attrs(shape_class="vertical-planar", domain_label="wall"))["polarity"] == "weakens"
    assert _evidence_class_pair(_attrs(shape_class="unknown", domain_label="")) is None


def test_volume_ratio_supports_small_weakens_near():
    big = _attrs(bbox_min=(0, 0, 0), bbox_max=(10, 10, 10))   # vol 1000
    small = _attrs(bbox_min=(0, 0, 0), bbox_max=(2, 2, 2))    # vol 8 -> ratio .008
    assert _evidence_volume_ratio(big, small)["polarity"] == "supports"
    near = _attrs(bbox_min=(0, 0, 0), bbox_max=(9.7, 9.7, 9.7))  # ratio ~.91
    assert _evidence_volume_ratio(big, near)["polarity"] == "weakens"


def test_grouping_hint_shared_layer_supports():
    assert _evidence_grouping(_attrs(layer="Walls"), _attrs(layer="Walls"))["polarity"] == "supports"
    assert _evidence_grouping(_attrs(layer="Walls"), _attrs(layer="Furniture")) is None


def test_spans_thin_axis_detects_penetration():
    # container is a flat slab (thin on Z); contained spans full Z extent -> penetration
    c = _attrs(bbox_min=(0, 0, 0), bbox_max=(10, 10, 1), thin_axis="Z")
    b = _attrs(bbox_min=(2, 2, 0), bbox_max=(3, 3, 1))  # flush top & bottom on Z
    assert _spans_thin_axis(c, b) is True
    b2 = _attrs(bbox_min=(2, 2, 0.2), bbox_max=(3, 3, 0.8))  # inset on Z
    assert _spans_thin_axis(c, b2) is False


from rook.scene.containment_refinement import _verdict_from_evidence


def _ev(signal, polarity):
    return {"signal": signal, "polarity": polarity, "detail": ""}


def test_verdict_not_a_solid_veto():
    ev = [_ev("container_solidity", "disqualifies")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=False)
    assert (verdict, conf, reason) == ("disqualified", "none", "not_a_solid")


def test_verdict_penetration_veto():
    ev = [_ev("class_pair", "weakens"), _ev("bbox_margin", "weakens")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=True)
    assert (verdict, conf, reason) == ("disqualified", "none", "likely_penetration")


def test_verdict_high_when_solid_margin_class_no_weakens():
    ev = [_ev("container_solidity", "supports"), _ev("bbox_margin", "supports"),
          _ev("class_pair", "supports"), _ev("bbox_volume_ratio", "supports")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=False)
    assert verdict == "contains_semantic" and conf == "high"


def test_verdict_medium_with_one_weakener():
    ev = [_ev("container_solidity", "supports"), _ev("bbox_margin", "supports"),
          _ev("bbox_volume_ratio", "weakens")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=False)
    assert verdict == "contains_semantic" and conf == "medium"


def test_verdict_low_when_thin_positive():
    ev = [_ev("bbox_margin", "supports"), _ev("class_pair", "weakens"),
          _ev("grouping_hint", "supports")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=False)
    assert verdict == "contains_semantic" and conf == "low"


def test_verdict_insufficient_when_unknown_solidity_no_class():
    # Mesh container: no solidity evidence, only bbox margin -> cannot responsibly assert
    ev = [_ev("bbox_margin", "supports")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=False)
    assert verdict == "insufficient_evidence" and conf == "none"


def test_verdict_touching_exact_alone_does_not_veto():
    # Regression guard: touching_exact weakens but, with strong containment, stays semantic.
    ev = [_ev("container_solidity", "supports"), _ev("bbox_margin", "supports"),
          _ev("class_pair", "supports"), _ev("touching_exact", "weakens")]
    verdict, conf, reason = _verdict_from_evidence(ev, penetration=False)
    assert verdict == "contains_semantic"  # NOT disqualified


from rook.scene.containment_refinement import ContainmentRefiner
from rook.scene.scene_graph import SceneGraphAnalytics


def _refiner(nodes: dict, contains_edges=(), exact_edges=()) -> ContainmentRefiner:
    """nodes: {id: attrs}; contains_edges: [(container, contained)]; exact_edges: [(a,b)]."""
    sg = SceneGraphAnalytics()
    for nid, attrs in nodes.items():
        sg.graph.add_node(nid, **attrs)
    for u, v in contains_edges:
        sg.graph.add_edge(u, v, relationship="contains", distance=0, overlap=0, direction="")
    for a, b in exact_edges:
        lo, hi = sorted((a, b))
        sg.graph.add_edge(lo, hi, key="occt:adjacent_exact", relationship="adjacent_exact")
    return ContainmentRefiner(sg)


def test_candidate_collection_both_roles_and_dedup():
    r = _refiner(
        {"A": _attrs(), "B": _attrs(), "C": _attrs()},
        contains_edges=[("A", "B"), ("C", "A")],
    )
    # Query A: it is container of B and contained of C -> two candidates.
    cands = r._candidate_contains_edges(["A"])
    assert set(cands) == {("A", "B"), ("C", "A")}
    # Query both A and C: the (C,A) candidate must appear once (dedup by ordered pair).
    cands2 = r._candidate_contains_edges(["A", "C"])
    assert sorted(cands2) == [("A", "B"), ("C", "A")]


def test_evaluate_candidate_high_confidence():
    r = _refiner({
        "BOX": _attrs(geometry_type="Brep", shape_class="compact",
                      bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
        "SM": _attrs(geometry_type="Brep", shape_class="compact",
                     bbox_min=(2, 2, 2), bbox_max=(4, 4, 4), layer="X"),
    }, contains_edges=[("BOX", "SM")])
    res = r._evaluate_candidate("BOX", "SM")
    assert res.verdict == "contains_semantic" and res.confidence == "high"


def test_evaluate_candidate_touching_exact_used_only_if_present():
    # Pre-seed an adjacent_exact edge -> touching_exact evidence appears.
    r = _refiner({
        "BOX": _attrs(geometry_type="Brep", shape_class="compact",
                      bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
        "SM": _attrs(geometry_type="Brep", shape_class="compact",
                     bbox_min=(2, 2, 2), bbox_max=(4, 4, 4)),
    }, contains_edges=[("BOX", "SM")], exact_edges=[("BOX", "SM")])
    res = r._evaluate_candidate("BOX", "SM")
    assert any(e["signal"] == "touching_exact" for e in res.evidence)


def test_refiner_never_calls_exact_projector(monkeypatch):
    import rook.scene.exact_projection as ep
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("refiner must not call the exact projector")

    monkeypatch.setattr(ep, "get_exact_projector", boom)
    r = _refiner({"BOX": _attrs(), "SM": _attrs(bbox_min=(2, 2, 2), bbox_max=(4, 4, 4))},
                 contains_edges=[("BOX", "SM")])
    r._evaluate_candidate("BOX", "SM")
    assert called["n"] == 0


def test_prepare_is_pure_then_commit_writes_edges_and_annotations():
    r = _refiner({
        "BOX": _attrs(geometry_type="Brep", shape_class="compact",
                      bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
        "SM": _attrs(geometry_type="Brep", shape_class="compact",
                     bbox_min=(2, 2, 2), bbox_max=(4, 4, 4)),
    }, contains_edges=[("BOX", "SM")])
    g = r._analytics.graph

    delta = r._prepare_request_delta(["BOX"], graph_sequence=5)
    # prepare must not mutate the graph
    assert not any(k == SEMANTIC_CONTAINS_KEY for _, _, k in g.edges(keys=True))
    assert "containment_status" not in g["BOX"]["SM"][0]

    r._commit_request_delta(delta)
    # positive verdict -> one semantic edge BOX->SM
    se = [(u, v, k) for u, v, k in g.edges(keys=True) if k == SEMANTIC_CONTAINS_KEY]
    assert se == [("BOX", "SM", SEMANTIC_CONTAINS_KEY)]
    edge = g["BOX"]["SM"][SEMANTIC_CONTAINS_KEY]
    assert edge["relationship"] == "contains_semantic" and edge["provenance"] == "semantic_refiner"
    assert edge["verdict"] == "contains_semantic" and edge["confidence"] == "high"
    # bbox contains edge annotated
    bbox = g["BOX"]["SM"][0]
    assert bbox["containment_status"] == "contains_semantic"
    assert bbox["containment_confidence"] == "high"
    assert isinstance(bbox["containment_evidence"], list)


def test_disqualified_and_insufficient_make_no_semantic_edge_but_annotate():
    r = _refiner({
        "WALL": _attrs(geometry_type="Brep", shape_class="vertical-planar", domain_label="wall",
                       bbox_min=(0, 0, 0), bbox_max=(10, 0.2, 10), thin_axis="Y"),
        "COL": _attrs(geometry_type="Brep", shape_class="thin-vertical", domain_label="column",
                      bbox_min=(2, 0, 0), bbox_max=(3, 0.2, 10)),  # spans Y (thin) -> penetration
    }, contains_edges=[("WALL", "COL")])
    g = r._analytics.graph
    r._commit_request_delta(r._prepare_request_delta(["WALL"], graph_sequence=1))
    assert not any(k == SEMANTIC_CONTAINS_KEY for _, _, k in g.edges(keys=True))
    assert g["WALL"]["COL"][0]["containment_status"] == "disqualified"
    assert g["WALL"]["COL"][0]["containment_reason"] == "likely_penetration"


def test_commit_atomicity_failed_candidate_no_partial_mutation(monkeypatch):
    r = _refiner({
        "BOX": _attrs(geometry_type="Brep", shape_class="compact",
                      bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
        "SM": _attrs(geometry_type="Brep", shape_class="compact",
                     bbox_min=(2, 2, 2), bbox_max=(4, 4, 4)),
        "BAD": _attrs(bbox_min=(1, 1, 1), bbox_max=(3, 3, 3)),
    }, contains_edges=[("BOX", "SM"), ("BOX", "BAD")])
    g = r._analytics.graph
    orig_eval = r._evaluate_candidate

    def maybe_raise(container, contained):
        if contained == "BAD":
            raise ValueError("boom")
        return orig_eval(container, contained)

    monkeypatch.setattr(r, "_evaluate_candidate", maybe_raise)
    delta = r._prepare_request_delta(["BOX"], graph_sequence=1)
    r._commit_request_delta(delta)
    # SM committed; BAD failed -> no semantic edge, no annotation for BAD
    assert g.has_edge("BOX", "SM", key=SEMANTIC_CONTAINS_KEY)
    assert "containment_status" not in g["BOX"]["BAD"][0]
    bad = next(res for res in delta.results if res.contained_id == "BAD")
    assert bad.verdict == "failed" and bad.error
