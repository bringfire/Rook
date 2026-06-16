"""
Exact Adjacency Projection (v1)
===============================

Read-model layer projecting the production OCCT exact-adjacency engine's output
(POST /scene/graph/adjacency/exact) into the networkx scene-graph mirror as typed,
IFC-aligned `adjacent_exact` relationship edges.

Spec: docs/superpowers/specs/2026-06-16-exact-adjacency-projection-v1-design.md

Invariants:
  - No C++ changes; only consumes the existing native route.
  - Units come from the route (lengthUnit/areaUnit); Python never converts.
  - Exact facts are ephemeral, valid only for the graphSequence they were computed
    against; projection artifacts are pruned when the sequence advances.
  - Projection runs ONLY on explicit scene_exact_neighbors calls — never during
    sync()/diff. No internal graph-walk; no whole-model sweep.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from ..bridge import call_rhino
from .scene_graph import SceneGraphAnalytics, get_scene_graph

logger = logging.getLogger(__name__)

EXACT_EDGE_KEY = "occt:adjacent_exact"
EXACT_RELATIONSHIP = "adjacent_exact"
EXACT_PROVENANCE = "occt"
ENGINE_VERSION = 2
DEFAULT_CANDIDATE_SCOPE = "broad_phase_default"

# Capabilities for which a "candidate considered but no edge" is a true geometric
# refutation (no shared face). Anything else means the pair could not be evaluated.
EVALUABLE_CAPS = {"exact_brep", "partial_exact_brep"}

# Projection-owned annotation fields stamped onto bbox edges (stripped on prune).
_BBOX_ANNOTATION_FIELDS = (
    "approximate",
    "exact_status",
    "exact_reason",
    "exact_diagnostics",
    "exact_graphSequence",
)


def _canonical_pair(id_a: str, id_b: str) -> tuple[str, str]:
    """Canonical orientation (min, max) for the symmetric adjacency fact."""
    return (id_a, id_b) if id_a <= id_b else (id_b, id_a)


@dataclass
class _SourceDelta:
    """A prepared-but-not-committed projection for one queried source id."""

    source_id: str
    route_status: str = "ok"  # ok | failed | timeout | skipped
    error: str | None = None
    source_capability: str = ""
    length_unit: str | None = None
    area_unit: str | None = None
    capabilities_by_id: dict = field(default_factory=dict)
    # (canon_src, canon_tgt, attrs) tuples to upsert
    edge_upserts: list = field(default_factory=list)
    # (id_a, id_b, annotation_dict) — annotation applied to an existing bbox edge if present
    bbox_annotations: list = field(default_factory=list)
    neighbors: list = field(default_factory=list)
    refuted: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)


class ExactAdjacencyProjector:
    """Projects exact OCCT adjacency edges into a SceneGraphAnalytics mirror.

    Owns no graph of its own — reads/writes the analytics mirror, which stays the
    single source of truth. Caches per-source results keyed by graphSequence.
    """

    def __init__(self, analytics: SceneGraphAnalytics) -> None:
        self._analytics = analytics
        self._cache: dict[tuple, dict] = {}
        self._cache_sequence: int = -1

    def _upsert_exact_edge(self, id_a: str, id_b: str, attrs: dict) -> None:
        """Idempotent upsert of the symmetric adjacency fact as one canonical edge.

        MultiDiGraph.add_edge with a fixed key updates the existing edge's data
        in place when (canon_src, canon_tgt, EXACT_EDGE_KEY) already exists — so
        re-projecting from the other endpoint never creates a parallel duplicate.
        """
        canon_src, canon_tgt = _canonical_pair(id_a, id_b)
        self._analytics.graph.add_edge(
            canon_src, canon_tgt, key=EXACT_EDGE_KEY, **attrs
        )
