"""
Semantic Containment Refinement (v1)
====================================

Read-model layer that refines the scene graph's approximate bbox `contains` edges into
semantic, ordinal-confidence, evidence-backed containment between actual modeled objects.

Spec: docs/superpowers/specs/2026-06-16-semantic-containment-refinement-v1-design.md

Invariants:
  - No C++ changes; reasons only over evidence already in the mirror.
  - The ONLY native interaction is the existing SceneGraphAnalytics.sync() mirror refresh.
    Never calls the exact projector, the exact-adjacency route, a point-in-solid route, or
    any new geometry route. adjacent_exact edges are used only if already present (a
    disambiguation weakener), never fetched.
  - Verdicts are semantic + ordinal confidence, NEVER geometrically exact (closure is
    unverifiable from current mirror metadata). No contains_exact in this slice.
  - Facts are ephemeral, valid only for the graphSequence they were computed against;
    artifacts are pruned when the sequence advances.
  - Explicit object-set tool only; no graph-walk, no whole-model sweep, no baseline-sync work.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

from .scene_graph import SceneGraphAnalytics, get_scene_graph

logger = logging.getLogger(__name__)

SEMANTIC_CONTAINS_KEY = "semantic:contains"
SEMANTIC_RELATIONSHIP = "contains_semantic"
SEMANTIC_PROVENANCE = "semantic_refiner"
ENGINE_VERSION = 1

# An already-projected exact-adjacency edge (Projection v1) is recognized by this
# relationship. We read it if present; we never create or fetch it here.
ADJACENT_EXACT_RELATIONSHIP = "adjacent_exact"

# geometry_type buckets (src/RookNative/Models/DocumentHelpers.h :: ObjectTypeToString).
SOLID_TYPES = {"Brep", "Extrusion"}                  # plausible container solid (closure unverified)
NON_SOLID_TYPES = {                                  # cannot be a container -> not_a_solid hard veto
    "Point", "PointSet", "Curve", "Light",
    "Annotation", "TextDot", "Hatch", "ClipPlane",
}
# Mesh / SubD / InstanceReference: unknown closure -> neutral (no solidity evidence emitted;
# handled by the fall-through in _evidence_container_solidity, not a named set).
OPEN_SURFACE_TYPES = {"Surface"}                          # open -> weakens

# Thin container classes (penetration risk). Checked against shape_class AND domain_label.
THIN_CLASSES = {
    "vertical-planar", "thin-vertical", "thin-horizontal", "horizontal-slab",
    "wall", "column", "beam", "slab", "floor",
}
# Compact/solid container classes that positively support containment.
COMPACT_CONTAINER_CLASSES = {"compact", "block"}

# Projection-owned annotation fields stamped onto bbox contains edges (stripped on prune).
_CONTAINMENT_ANNOTATION_FIELDS = (
    "containment_status",
    "containment_confidence",
    "containment_reason",
    "containment_evidence",
    "containment_graphSequence",
)

# --- Named, tunable thresholds (ordinal model — not probabilities) ---
MARGIN_EPS = 1e-6            # clearance beyond this on an axis counts as positive (else flush)
DEPTH_MEANINGFUL_FRAC = 0.05  # contained inset >= 5% of container extent on an axis = meaningful
DEPTH_MIN_AXES = 2          # meaningful inset required on >= this many axes for depth-supports
VOLUME_RATIO_SMALL = 0.5    # contained bbox vol <= 50% of container -> supports
VOLUME_RATIO_NEAR = 0.9     # contained bbox vol >= 90% of container -> weakens (near-coincident)

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def candidate_id(container_id: str, contained_id: str) -> str:
    """Stable directional candidate identity."""
    return f"{container_id}|contains|{contained_id}"


@dataclass
class _CandidateResult:
    """Evaluation result for one ordered (container, contained) candidate."""

    candidate_id: str
    container_id: str
    contained_id: str
    verdict: str = "insufficient_evidence"  # contains_semantic | insufficient_evidence | disqualified | failed
    confidence: str = "none"                # high | medium | low | none
    reason: str | None = None
    evidence: list = field(default_factory=list)
    error: str | None = None                # set only when verdict == "failed"


@dataclass
class _RequestDelta:
    """Prepared (not yet committed) refinement for one request."""
    graph_sequence: int
    results: list = field(default_factory=list)            # list[_CandidateResult]
    edge_upserts: list = field(default_factory=list)       # (container, contained, attrs)
    annotations: list = field(default_factory=list)        # (container, contained, ann_dict)


def _bbox_volume(attrs: dict) -> float:
    mn = attrs.get("bbox_min") or [0, 0, 0]
    mx = attrs.get("bbox_max") or [0, 0, 0]
    return (max(0.0, mx[0] - mn[0]) * max(0.0, mx[1] - mn[1]) * max(0.0, mx[2] - mn[2]))


def _axis_clearances(c: dict, b: dict) -> list[tuple[float, float]]:
    """(low_clearance, high_clearance) of contained b within container c, per axis."""
    cmn, cmx = c.get("bbox_min") or [0, 0, 0], c.get("bbox_max") or [0, 0, 0]
    bmn, bmx = b.get("bbox_min") or [0, 0, 0], b.get("bbox_max") or [0, 0, 0]
    return [(bmn[i] - cmn[i], cmx[i] - bmx[i]) for i in range(3)]


def _evidence_bbox_margin(c: dict, b: dict) -> dict:
    cl = _axis_clearances(c, b)
    flush = [("X", "Y", "Z")[i] for i, (lo, hi) in enumerate(cl) if lo <= MARGIN_EPS or hi <= MARGIN_EPS]
    if flush:
        return {"signal": "bbox_margin", "polarity": "weakens",
                "detail": f"flush on {','.join(flush)}"}
    return {"signal": "bbox_margin", "polarity": "supports", "detail": "positive clearance all axes"}


def _evidence_containment_depth(c: dict, b: dict) -> dict:
    cmn, cmx = c.get("bbox_min") or [0, 0, 0], c.get("bbox_max") or [0, 0, 0]
    cl = _axis_clearances(c, b)
    meaningful = 0
    for i, (lo, hi) in enumerate(cl):
        ext = cmx[i] - cmn[i]
        if ext <= 0:
            continue
        if (min(lo, hi) / ext) >= DEPTH_MEANINGFUL_FRAC:
            meaningful += 1
    if meaningful >= DEPTH_MIN_AXES:
        return {"signal": "containment_depth", "polarity": "supports",
                "detail": f"meaningful inset on {meaningful} axes"}
    return {"signal": "containment_depth", "polarity": "weakens",
            "detail": f"shallow inset ({meaningful} axes)"}


def _evidence_container_solidity(c: dict) -> dict | None:
    gt = c.get("geometry_type", "")
    if gt in SOLID_TYPES:
        return {"signal": "container_solidity", "polarity": "supports", "detail": gt}
    if gt in NON_SOLID_TYPES:
        return {"signal": "container_solidity", "polarity": "disqualifies", "detail": f"not_a_solid:{gt}"}
    if gt in OPEN_SURFACE_TYPES:
        return {"signal": "container_solidity", "polarity": "weakens", "detail": f"open:{gt}"}
    return None  # Mesh/SubD/InstanceReference/unknown -> neutral (closure unknown)


def _evidence_class_pair(c: dict) -> dict | None:
    classes = {c.get("shape_class", ""), c.get("domain_label", "")}
    if classes & COMPACT_CONTAINER_CLASSES:
        return {"signal": "class_pair", "polarity": "supports", "detail": "compact/block container"}
    if classes & THIN_CLASSES:
        thin = ",".join(sorted(x for x in classes & THIN_CLASSES if x))
        return {"signal": "class_pair", "polarity": "weakens", "detail": f"thin container ({thin})"}
    return None


def _evidence_volume_ratio(c: dict, b: dict) -> dict | None:
    cv = _bbox_volume(c)
    if cv <= 0:
        return None
    ratio = _bbox_volume(b) / cv
    if ratio <= VOLUME_RATIO_SMALL:
        return {"signal": "bbox_volume_ratio", "polarity": "supports", "detail": f"ratio {ratio:.3f}"}
    if ratio >= VOLUME_RATIO_NEAR:
        return {"signal": "bbox_volume_ratio", "polarity": "weakens", "detail": f"near-coincident {ratio:.3f}"}
    return None


def _evidence_grouping(c: dict, b: dict) -> dict | None:
    # v1 is LAYER-ONLY. Name- and user-string-based grouping are DEFERRED: user strings are
    # not in the mirror's node attrs, and name heuristics are noisy. Revisit when the mirror
    # carries normalized grouping metadata.
    cl, bl = c.get("layer", ""), b.get("layer", "")
    if cl and cl == bl:
        return {"signal": "grouping_hint", "polarity": "supports", "detail": f"shared layer '{cl}'"}
    return None


def _spans_thin_axis(c: dict, b: dict) -> bool:
    """True if contained fills the container's thin dimension (flush both sides) = penetration."""
    cmn, cmx = c.get("bbox_min") or [0, 0, 0], c.get("bbox_max") or [0, 0, 0]
    axis = _AXIS_INDEX.get(c.get("thin_axis", ""))
    if axis is None:
        exts = [cmx[i] - cmn[i] for i in range(3)]
        axis = exts.index(min(exts))
    bmn, bmx = b.get("bbox_min") or [0, 0, 0], b.get("bbox_max") or [0, 0, 0]
    low, high = bmn[axis] - cmn[axis], cmx[axis] - bmx[axis]
    return low <= MARGIN_EPS and high <= MARGIN_EPS


def _verdict_from_evidence(evidence: list, penetration: bool) -> tuple[str, str, str | None]:
    """Map accumulated evidence (+ penetration flag) to (verdict, confidence, reason).

    Two hard vetoes: not_a_solid (a disqualifies-polarity item) and likely_penetration.
    Otherwise additive ordinal mapping. Confidence is ordinal, never probabilistic.
    """
    if any(e["polarity"] == "disqualifies" for e in evidence):
        return "disqualified", "none", "not_a_solid"
    if penetration:
        return "disqualified", "none", "likely_penetration"

    supports = [e for e in evidence if e["polarity"] == "supports"]
    weakens = [e for e in evidence if e["polarity"] == "weakens"]
    sig = lambda name, pol: any(e["signal"] == name and e["polarity"] == pol for e in evidence)  # noqa: E731

    has_solid = sig("container_solidity", "supports")
    has_margin = sig("bbox_margin", "supports")
    has_class = sig("class_pair", "supports")

    if has_solid and has_margin and has_class and not weakens:
        return "contains_semantic", "high", "strong_clearance_plausible_container"
    if has_solid and has_margin and len(weakens) <= 1:
        return "contains_semantic", "medium", "clear_containment_minor_gaps"
    if len(supports) >= 2 and len(supports) > len(weakens) and (has_margin or has_solid):
        return "contains_semantic", "low", "weak_positive_containment"
    return "insufficient_evidence", "none", "insufficient_evidence"


class ContainmentRefiner:
    """Refines bbox `contains` candidates into semantic containment in a SceneGraphAnalytics mirror.

    Owns no graph; reads/refines the analytics mirror. Reasons only over evidence already
    present — never calls the exact projector or any new geometry route.
    """

    def __init__(self, analytics: SceneGraphAnalytics) -> None:
        self._analytics = analytics
        self._cache: dict[tuple, dict] = {}
        self._cache_sequence: int = -1

    def _candidate_contains_edges(self, object_ids) -> list[tuple[str, str]]:
        """Ordered (container, contained) pairs from bbox `contains` edges incident to the ids
        in EITHER role, deduped by ordered pair."""
        g = self._analytics.graph
        seen: set[tuple[str, str]] = set()
        out: list[tuple[str, str]] = []
        for x in object_ids:
            if not g.has_node(x):
                continue
            for _u, v, d in g.out_edges(x, data=True):
                if d.get("relationship") == "contains" and (x, v) not in seen:
                    seen.add((x, v)); out.append((x, v))
            for u, _v, d in g.in_edges(x, data=True):
                if d.get("relationship") == "contains" and (u, x) not in seen:
                    seen.add((u, x)); out.append((u, x))
        return out

    def _has_adjacent_exact(self, a: str, b: str) -> bool:
        g = self._analytics.graph
        for u, v in ((a, b), (b, a)):
            if g.has_edge(u, v):
                for _k, d in g[u][v].items():
                    if d.get("relationship") == ADJACENT_EXACT_RELATIONSHIP:
                        return True
        return False

    def _evaluate_candidate(self, container_id: str, contained_id: str) -> _CandidateResult:
        g = self._analytics.graph
        c = g.nodes[container_id]
        b = g.nodes[contained_id]
        evidence: list[dict] = []
        for fn in (_evidence_container_solidity, _evidence_class_pair):
            item = fn(c)
            if item:
                evidence.append(item)
        evidence.append(_evidence_bbox_margin(c, b))
        evidence.append(_evidence_containment_depth(c, b))
        for item in (_evidence_volume_ratio(c, b), _evidence_grouping(c, b)):
            if item:
                evidence.append(item)
        if self._has_adjacent_exact(container_id, contained_id):
            evidence.append({"signal": "touching_exact", "polarity": "weakens",
                             "detail": "adjacent_exact edge present"})

        thin = bool({c.get("shape_class", ""), c.get("domain_label", "")} & THIN_CLASSES)
        penetration = thin and _spans_thin_axis(c, b)

        verdict, confidence, reason = _verdict_from_evidence(evidence, penetration)
        return _CandidateResult(
            candidate_id=candidate_id(container_id, contained_id),
            container_id=container_id, contained_id=contained_id,
            verdict=verdict, confidence=confidence, reason=reason, evidence=evidence,
        )

    def _prepare_request_delta(self, object_ids, graph_sequence: int) -> "_RequestDelta":
        """PURE: evaluate every candidate, plan mutations for non-failed ones. No graph writes."""
        delta = _RequestDelta(graph_sequence=graph_sequence)
        for container_id, contained_id in self._candidate_contains_edges(object_ids):
            try:
                res = self._evaluate_candidate(container_id, contained_id)
            except Exception as ex:  # isolate a bad candidate; no partial mutation
                logger.warning("containment eval failed for (%s,%s): %s", container_id, contained_id, ex)
                res = _CandidateResult(
                    candidate_id=candidate_id(container_id, contained_id),
                    container_id=container_id, contained_id=contained_id,
                    verdict="failed", confidence="none", reason=None, evidence=[], error=str(ex))
                delta.results.append(res)
                continue
            delta.results.append(res)
            ann = {
                "containment_status": res.verdict,
                "containment_confidence": res.confidence,
                "containment_reason": res.reason,
                "containment_evidence": res.evidence,
                "containment_graphSequence": graph_sequence,
            }
            delta.annotations.append((container_id, contained_id, ann))
            if res.verdict == "contains_semantic":
                delta.edge_upserts.append((container_id, contained_id, {
                    "relationship": SEMANTIC_RELATIONSHIP,
                    "provenance": SEMANTIC_PROVENANCE,
                    "verdict": res.verdict,
                    "confidence": res.confidence,
                    "reason": res.reason,
                    "evidence": res.evidence,
                    "graphSequence": graph_sequence,
                    "engineVersion": ENGINE_VERSION,
                }))
        return delta

    def _commit_request_delta(self, delta: "_RequestDelta") -> None:
        """Apply all planned edges + annotations in one pass; invalidate analytics caches."""
        g = self._analytics.graph
        mutated = False
        for container_id, contained_id, attrs in delta.edge_upserts:
            g.add_edge(container_id, contained_id, key=SEMANTIC_CONTAINS_KEY, **attrs)
            mutated = True
        for container_id, contained_id, ann in delta.annotations:
            if not g.has_edge(container_id, contained_id):
                continue
            for _k, edata in g[container_id][contained_id].items():
                if edata.get("relationship") == "contains":
                    edata.update(ann)
                    mutated = True
        if mutated:
            self._analytics._invalidate_caches()

    def _purge_artifacts(self) -> None:
        g = self._analytics.graph
        to_remove = [
            (u, v, k) for u, v, k, d in g.edges(keys=True, data=True)
            if k == SEMANTIC_CONTAINS_KEY or d.get("provenance") == SEMANTIC_PROVENANCE
        ]
        for u, v, k in to_remove:
            g.remove_edge(u, v, key=k)
        for _u, _v, _k, edata in g.edges(keys=True, data=True):
            for fld in _CONTAINMENT_ANNOTATION_FIELDS:
                edata.pop(fld, None)
        self._analytics._invalidate_caches()

    def _prune_if_advanced(self, graph_sequence: int) -> None:
        if graph_sequence != self._cache_sequence:
            self._purge_artifacts()
            self._cache.clear()
            self._cache_sequence = graph_sequence

    @staticmethod
    def _cache_key(graph_sequence: int, object_ids) -> tuple:
        return (graph_sequence, tuple(sorted(set(object_ids))), ENGINE_VERSION)

    def _build_payload(self, graph_sequence: int, object_ids, delta: "_RequestDelta") -> dict:
        g = self._analytics.graph
        refined = [{
            "candidateId": res.candidate_id, "containerId": res.container_id,
            "containedId": res.contained_id, "verdict": res.verdict,
            "confidence": res.confidence, "reason": res.reason,
            "evidence": res.evidence, "error": res.error,
        } for res in delta.results]

        by_source: dict[str, dict] = {}
        for x in dict.fromkeys(object_ids):  # preserve order, unique
            if not g.has_node(x):
                by_source[x] = {"status": "skipped", "error": "object_not_in_scene",
                                "asContainer": [], "asContained": []}
                continue
            as_container, as_contained, failed = [], [], False
            for res in delta.results:
                if res.container_id == x:
                    as_container.append(res.candidate_id)
                    failed = failed or res.verdict == "failed"
                if res.contained_id == x:
                    as_contained.append(res.candidate_id)
                    failed = failed or res.verdict == "failed"
            by_source[x] = {"status": "failed" if failed else "ok",
                            "error": "candidate_evaluation_failed" if failed else None,
                            "asContainer": as_container, "asContained": as_contained}
        return {"success": True, "graphSequence": graph_sequence,
                "refined": refined, "bySource": by_source}

    async def refine(self, object_ids, *, port=None) -> dict:
        await self._analytics.sync(port=port)
        graph_sequence = self._analytics.sequence
        self._prune_if_advanced(graph_sequence)

        key = self._cache_key(graph_sequence, object_ids)
        if key in self._cache:
            payload = copy.deepcopy(self._cache[key])
            payload["cache"] = {"hits": 1, "misses": 0}
            return payload

        delta = self._prepare_request_delta(object_ids, graph_sequence)
        self._commit_request_delta(delta)
        payload = self._build_payload(graph_sequence, object_ids, delta)
        payload["cache"] = {"hits": 0, "misses": 1}

        # Cache only durable outcomes: no source is `failed`.
        if all(b["status"] != "failed" for b in payload["bySource"].values()):
            cached = copy.deepcopy(payload)
            cached.pop("cache", None)
            self._cache[key] = cached
        return payload


_refiner: ContainmentRefiner | None = None


def get_containment_refiner(analytics: SceneGraphAnalytics | None = None) -> ContainmentRefiner:
    """Module singleton, bound to the shared scene-graph analytics mirror."""
    global _refiner
    if _refiner is None:
        _refiner = ContainmentRefiner(analytics or get_scene_graph())
    return _refiner
