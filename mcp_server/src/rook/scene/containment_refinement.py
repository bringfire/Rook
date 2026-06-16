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
WEAK_SOLID_TYPES = {"Mesh", "SubD", "InstanceReference"}  # unknown closure -> neutral (no evidence)
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
