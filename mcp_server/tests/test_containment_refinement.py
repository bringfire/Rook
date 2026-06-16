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
