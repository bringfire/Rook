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
