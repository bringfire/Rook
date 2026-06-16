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

    def _prepare_source_delta(self, source_id: str, data: dict, graph_sequence: int) -> _SourceDelta:
        """Parse a route payload into an in-memory delta. No graph mutation here."""
        g = self._analytics.graph
        length_unit = data.get("lengthUnit")
        area_unit = data.get("areaUnit")
        source_capability = data.get("sourceCapability", "")
        candidates = data.get("candidates") or []
        # raises if candidates is not a list of dicts -> drives commit atomicity
        cap_map = {c.get("id"): c.get("capability", "") for c in candidates if c.get("id")}
        edges = data.get("edges") or []

        delta = _SourceDelta(
            source_id=source_id, route_status="ok",
            source_capability=source_capability,
            length_unit=length_unit, area_unit=area_unit,
        )
        delta.capabilities_by_id[source_id] = source_capability

        edge_targets: set[str] = set()
        for e in edges:
            tgt = e.get("targetId")
            if not tgt:
                continue
            edge_targets.add(tgt)
            shared_area = e.get("sharedArea", 0.0)
            face_pairs = e.get("facePairs") or []
            tgt_cap = cap_map.get(tgt, "")
            delta.capabilities_by_id[tgt] = tgt_cap

            canon_src, canon_tgt = _canonical_pair(source_id, tgt)
            delta.edge_upserts.append((canon_src, canon_tgt, {
                "relationship": EXACT_RELATIONSHIP,
                "provenance": EXACT_PROVENANCE,
                "symmetric": True,
                "canonical": True,
                "queriedSourceId": source_id,
                "queriedTargetId": tgt,
                "facePairsFrom": "queried_source_to_candidate",
                "sharedArea": shared_area,
                "lengthUnit": length_unit,
                "areaUnit": area_unit,
                "facePairs": face_pairs,
                "capabilitiesById": {source_id: source_capability, tgt: tgt_cap},
                "graphSequence": graph_sequence,
                "engineVersion": ENGINE_VERSION,
            }))
            if self._has_bbox_pair(source_id, tgt):
                delta.bbox_annotations.append((source_id, tgt, {
                    "approximate": True,
                    "exact_status": "exact_confirmed",
                    "exact_graphSequence": graph_sequence,
                }))
            delta.neighbors.append({
                "id": tgt,
                "relationship": EXACT_RELATIONSHIP,
                "sharedArea": shared_area,
                "lengthUnit": length_unit,
                "areaUnit": area_unit,
                "facePairs": face_pairs,
                "targetCapability": tgt_cap,
                "fromCache": False,
            })

        for cid, cap in cap_map.items():
            if cid == source_id or cid in edge_targets:
                continue
            delta.capabilities_by_id[cid] = cap
            if cap in EVALUABLE_CAPS:
                delta.refuted.append({"id": cid, "reason": "no_shared_face"})
                ann = {"approximate": True, "exact_status": "exact_refuted",
                       "exact_reason": "no_shared_face", "exact_graphSequence": graph_sequence}
            else:
                delta.failed.append({"id": cid, "reason": cap or "unsupported_geometry",
                                     "diagnostics": []})
                ann = {"approximate": True, "exact_status": "exact_failed",
                       "exact_diagnostics": [], "exact_graphSequence": graph_sequence}
            if self._has_bbox_pair(source_id, cid):
                delta.bbox_annotations.append((source_id, cid, ann))
        return delta

    def _has_bbox_pair(self, a: str, b: str) -> bool:
        g = self._analytics.graph
        return g.has_edge(a, b) or g.has_edge(b, a)

    def _commit_source_delta(self, delta: _SourceDelta) -> None:
        """Apply the prepared delta in one shot; invalidate analytics caches if mutated."""
        if delta.route_status != "ok":
            return
        g = self._analytics.graph
        mutated = False
        for canon_src, canon_tgt, attrs in delta.edge_upserts:
            self._upsert_exact_edge(canon_src, canon_tgt, attrs)
            mutated = True
        for a, b, ann in delta.bbox_annotations:
            for u, v in ((a, b), (b, a)):
                if not g.has_edge(u, v):
                    continue
                for _key, edata in g[u][v].items():
                    if edata.get("relationship") == "adjacent":
                        edata.update(ann)
                        mutated = True
        if mutated:
            self._analytics._invalidate_caches()

    def _purge_projection_artifacts(self) -> None:
        """Remove all projection-owned edges + bbox annotations from the mirror."""
        g = self._analytics.graph
        to_remove = [
            (u, v, k) for u, v, k, d in g.edges(keys=True, data=True)
            if k == EXACT_EDGE_KEY or d.get("provenance") == EXACT_PROVENANCE
        ]
        for u, v, k in to_remove:
            g.remove_edge(u, v, key=k)
        for _u, _v, _k, edata in g.edges(keys=True, data=True):
            for fld in _BBOX_ANNOTATION_FIELDS:
                edata.pop(fld, None)
        self._analytics._invalidate_caches()

    def _prune_if_advanced(self, graph_sequence: int) -> None:
        """Purge stale projection state when the source graph sequence advances."""
        if graph_sequence != self._cache_sequence:
            self._purge_projection_artifacts()
            self._cache.clear()
            self._cache_sequence = graph_sequence
