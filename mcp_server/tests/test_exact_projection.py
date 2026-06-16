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
