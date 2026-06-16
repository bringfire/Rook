# Semantic Containment Refinement v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the scene graph's approximate bbox `contains` edges into semantic, ordinal-confidence, evidence-backed containment between actual modeled objects, exposed by a new `scene_refine_containment` MCP tool.

**Architecture:** A Python read-model layer only — **zero C++ changes**. A new isolated module `scene/containment_refinement.py` holds `ContainmentRefiner`, which (after syncing the mirror) evaluates the bbox `contains` candidates incident to queried objects using only evidence already in the mirror, classifies each into a verdict + ordinal confidence + evidence list, and atomically commits parallel `semantic:contains` edges (positive verdicts only) plus non-destructive annotations on the bbox edges. It NEVER calls the exact projector or any native route; `adjacent_exact` edges are used only if already present (as a disambiguation weakener). Request-level `graphSequence`-keyed cache with active prune on advance.

**Tech Stack:** Python 3.11+, networkx `MultiDiGraph`, pytest (`asyncio.run`, no live Rhino), MCP `Tool` registration, tool-group + targeting-policy registration.

**Spec:** `docs/superpowers/specs/2026-06-16-semantic-containment-refinement-v1-design.md` (committed `b6487122`). This plan mirrors the structure of `docs/superpowers/plans/2026-06-16-exact-adjacency-projection-v1.md`.

**Branch discipline:** Work only on `feature/spatial-intelligence` in worktree `C:/Users/aryan/source/repos/rook-spatial`. Verify `git branch --show-current` before every commit. **Never stage `src/Rook/Properties/launchSettings.json`** or the runtime artifacts `knowledge/contextual_mab.pkl` / `knowledge/gh/component_observations.json` — stage only the exact files each task names. Tests run from `mcp_server`: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest ...`. End commit messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**Hard implementation rule (atomicity):** build the entire request candidate delta first (pure, no graph writes), exclude `failed` candidates from mutation, then commit all successful candidates' edges + annotations together. **Never mutate the graph while iterating candidates.**

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mcp_server/src/rook/scene/containment_refinement.py` | `ContainmentRefiner`: candidate collection, pure evidence functions, verdict engine, prepare/commit delta, cache, prune. Owns no graph. | **Create** |
| `mcp_server/tests/test_containment_refinement.py` | Unit tests (no Rhino): evidence polarities, verdict tiers, vetoes, touching-not-veto regression, candidate dedup, atomicity, cache/prune, contract, registration. | **Create** |
| `mcp_server/src/rook/scene/scene_graph.py` | NL: render `contains_semantic` in `get_context` (`_FORWARD_RELS`/`_INVERSE_RELS`/`_edge_detail`). | **Modify** |
| `mcp_server/src/rook/server.py` | `scene_refine_containment` `Tool` schema + dispatch case (top-level failure propagation). | **Modify** |
| `mcp_server/src/rook/agent/tool_groups.py` | Add tool to `TOOL_GROUPS["scene_graph"]`. | **Modify (~line 452)** |
| `mcp_server/src/rook/agent/tool_dispatcher.py` | Agent-direct local handler in `build_local_tools()`. | **Modify (~line 1101)** |
| `mcp_server/src/rook/targeting.py` | Add tool to `_ALL_KNOWN_TOOLS` (~line 543) + `_RHINO_READ_TOOLS` (~line 701). | **Modify** |
| `docs/rook_docs/occt-spike/live_verify_containment_refinement.py` | Live wiring smoke (contract-only). | **Create** |

Semantic containment facts are ephemeral: valid only for the `graphSequence` they were computed against (spec §2).

---

### Task 1: Module scaffold — constants, `candidate_id`, dataclasses

**Files:**
- Create: `mcp_server/src/rook/scene/containment_refinement.py`
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# mcp_server/tests/test_containment_refinement.py
"""Unit tests for ContainmentRefiner — the Python read-model semantic containment layer.

No live Rhino: the scene-graph mirror is populated directly. The refiner must never
call the exact projector or any native route; adjacent_exact edges are consumed only
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.scene.containment_refinement'`

- [ ] **Step 3: Write minimal implementation**

```python
# mcp_server/src/rook/scene/containment_refinement.py
"""
Semantic Containment Refinement (v1)
====================================

Read-model layer that refines the scene graph's approximate bbox `contains` edges into
semantic, ordinal-confidence, evidence-backed containment between actual modeled objects.

Spec: docs/superpowers/specs/2026-06-16-semantic-containment-refinement-v1-design.md

Invariants:
  - No C++ changes; reasons only over evidence already in the mirror.
  - NEVER calls the exact projector or any native route. adjacent_exact edges are used
    only if already present (a disambiguation weakener), never fetched.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/containment_refinement.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): containment_refinement scaffold (constants, candidate_id, _CandidateResult)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pure evidence functions

Pure functions over node-attr dicts → `{signal, polarity, detail}` items. No graph access, fully unit-testable.

**Files:**
- Modify: `mcp_server/src/rook/scene/containment_refinement.py`
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_containment_refinement.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "bbox_margin or solidity or class_pair or volume_ratio or grouping or thin_axis" -v`
Expected: FAIL — `ImportError`/`AttributeError` (functions not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# append to containment_refinement.py
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
    # NOTE: user-strings are NOT in the mirror's node attrs; v1 uses layer only.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (9 tests total)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/containment_refinement.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): pure evidence functions for containment refinement

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Verdict engine

Maps evidence + the penetration flag → `(verdict, confidence, reason)`. Encodes the two hard vetoes and the additive ordinal mapping (spec §4).

**Files:**
- Modify: `mcp_server/src/rook/scene/containment_refinement.py`
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_containment_refinement.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "verdict" -v`
Expected: FAIL — `_verdict_from_evidence` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to containment_refinement.py
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
    if len(supports) > len(weakens) and (has_margin or has_solid):
        return "contains_semantic", "low", "weak_positive_containment"
    return "insufficient_evidence", "none", "insufficient_evidence"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (16 tests total)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/containment_refinement.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): verdict engine (two vetoes + additive ordinal confidence)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Refiner class — candidate collection + per-candidate evaluation

**Files:**
- Modify: `mcp_server/src/rook/scene/containment_refinement.py`
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_containment_refinement.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "candidate_collection or evaluate_candidate or never_calls" -v`
Expected: FAIL — `ContainmentRefiner` / methods not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# append to containment_refinement.py
class ContainmentRefiner:
    """Refines bbox `contains` candidates into semantic containment in a SceneGraphAnalytics mirror.

    Owns no graph; reads/refines the analytics mirror. Reasons only over evidence already
    present — never calls the exact projector or any native route.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (20 tests total)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/containment_refinement.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): refiner candidate collection + per-candidate evaluation (read-model only)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Prepare + commit request-level delta (edges, annotations, atomicity)

`_prepare_request_delta` is **pure** (no graph writes): evaluates all candidates, catches per-candidate exceptions into `failed` results, and computes planned edge upserts + bbox annotations for non-failed candidates. `_commit_request_delta` applies them all in one pass. Build-whole-delta-then-commit — never mutate while iterating.

**Files:**
- Modify: `mcp_server/src/rook/scene/containment_refinement.py`
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_containment_refinement.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "prepare_is_pure or no_semantic_edge or atomicity" -v`
Expected: FAIL — `_prepare_request_delta` / `_commit_request_delta` / `_RequestDelta` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add a dataclass near _CandidateResult
@dataclass
class _RequestDelta:
    """Prepared (not yet committed) refinement for one request."""
    graph_sequence: int
    results: list = field(default_factory=list)            # list[_CandidateResult]
    edge_upserts: list = field(default_factory=list)       # (container, contained, attrs)
    annotations: list = field(default_factory=list)        # (container, contained, ann_dict)


# add methods to ContainmentRefiner
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (23 tests total)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/containment_refinement.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): request-level prepare/commit delta (atomic, semantic edges + bbox annotations)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Cache, prune, and `refine()` orchestration + return contract

**Files:**
- Modify: `mcp_server/src/rook/scene/containment_refinement.py`
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_containment_refinement.py
import rook.scene.containment_refinement as cr
from rook.scene.containment_refinement import get_containment_refiner


def _stub_sync(analytics, sequence):
    async def _sync(port=None):
        analytics._sequence = sequence
        return {"synced": True, "sequence": sequence}
    analytics.sync = _sync  # type: ignore[assignment]


def test_refine_contract_and_bysource():
    r = _refiner({
        "BOX": _attrs(geometry_type="Brep", shape_class="compact",
                      bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
        "SM": _attrs(geometry_type="Brep", shape_class="compact",
                     bbox_min=(2, 2, 2), bbox_max=(4, 4, 4)),
    }, contains_edges=[("BOX", "SM")])
    _stub_sync(r._analytics, 5)
    out = asyncio.run(r.refine(["BOX"]))
    assert out["success"] is True and out["graphSequence"] == 5
    assert len(out["refined"]) == 1
    cand = out["refined"][0]
    assert cand["candidateId"] == "BOX|contains|SM"
    assert cand["containerId"] == "BOX" and cand["containedId"] == "SM"
    assert cand["verdict"] == "contains_semantic"
    assert out["bySource"]["BOX"]["status"] == "ok"
    assert out["bySource"]["BOX"]["asContainer"] == ["BOX|contains|SM"]
    assert out["bySource"]["BOX"]["asContained"] == []
    assert out["cache"] == {"hits": 0, "misses": 1}
    # second identical call -> cache hit
    out2 = asyncio.run(r.refine(["BOX"]))
    assert out2["cache"] == {"hits": 1, "misses": 0}


def test_refine_skipped_when_not_in_scene():
    r = _refiner({"BOX": _attrs()})
    _stub_sync(r._analytics, 1)
    out = asyncio.run(r.refine(["GHOST"]))
    assert out["bySource"]["GHOST"]["status"] == "skipped"
    assert out["bySource"]["GHOST"]["error"] == "object_not_in_scene"


def test_refine_cache_key_dedups_duplicate_ids():
    r = _refiner({"BOX": _attrs(), "SM": _attrs(bbox_min=(2, 2, 2), bbox_max=(4, 4, 4))},
                 contains_edges=[("BOX", "SM")])
    _stub_sync(r._analytics, 1)
    asyncio.run(r.refine(["BOX"]))
    out = asyncio.run(r.refine(["BOX", "BOX"]))  # same set after dedup -> hit
    assert out["cache"] == {"hits": 1, "misses": 0}


def test_prune_on_sequence_advance_strips_artifacts_and_invalidates():
    r = _refiner({"BOX": _attrs(geometry_type="Brep", shape_class="compact",
                                bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
                  "SM": _attrs(geometry_type="Brep", shape_class="compact",
                               bbox_min=(2, 2, 2), bbox_max=(4, 4, 4))},
                 contains_edges=[("BOX", "SM")])
    g = r._analytics.graph
    _stub_sync(r._analytics, 1)
    asyncio.run(r.refine(["BOX"]))
    assert g.has_edge("BOX", "SM", key=SEMANTIC_CONTAINS_KEY)
    r._analytics._communities = {"g": ["BOX"]}
    r._analytics._centrality = {"BOX": 1.0}
    # advance the sequence and refine again -> artifacts pruned first
    _stub_sync(r._analytics, 2)
    asyncio.run(r.refine([]))
    assert not any(k == SEMANTIC_CONTAINS_KEY for _, _, k in g.edges(keys=True))
    assert "containment_status" not in g["BOX"]["SM"][0]
    assert r._analytics._communities is None and r._analytics._centrality is None


def test_get_containment_refiner_singleton_binds_scene_graph():
    a = get_containment_refiner()
    b = get_containment_refiner()
    assert a is b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "refine_ or prune_on or singleton" -v`
Expected: FAIL — `refine` / `get_containment_refiner` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add methods to ContainmentRefiner + module singleton at end of file
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (28 tests total)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/containment_refinement.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): refine() orchestration, request cache, prune-on-advance, contract

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: NL rendering of `contains_semantic` via get_context

**Files:**
- Modify: `mcp_server/src/rook/scene/scene_graph.py` (`_FORWARD_RELS` + `_INVERSE_RELS` near line 462-485; `_edge_detail`)
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_containment_refinement.py
from rook.scene.scene_graph import _inverse_rel, _forward_rel


def test_nl_forward_and_inverse_for_contains_semantic():
    assert _forward_rel("contains_semantic") == "contains (semantic)"
    assert _inverse_rel("contains_semantic") == "within (semantic)"


def test_get_context_renders_contains_semantic_with_confidence():
    r = _refiner({"BOX": _attrs(geometry_type="Brep", shape_class="compact",
                                bbox_min=(0, 0, 0), bbox_max=(10, 10, 10)),
                  "SM": _attrs(geometry_type="Brep", shape_class="compact", domain_label="panel",
                               bbox_min=(2, 2, 2), bbox_max=(4, 4, 4))},
                 contains_edges=[("BOX", "SM")])
    sg = r._analytics
    r._commit_request_delta(r._prepare_request_delta(["BOX"], graph_sequence=1))
    text = sg.get_context(["BOX"])
    assert "contains (semantic" in text
    assert "high" in text  # confidence rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "nl_forward or renders_contains_semantic" -v`
Expected: FAIL — `_forward_rel("contains_semantic")` returns `"contains_semantic"`; render lacks the phrase.

- [ ] **Step 3: Write minimal implementation**

In `scene_graph.py`, add to `_INVERSE_RELS` (dict near line 462):

```python
    "contains_semantic": "within (semantic)",
```

Add to `_FORWARD_RELS` (dict near the `_forward_rel` helper added in Projection v1):

```python
    "contains_semantic": "contains (semantic)",
```

In `_edge_detail`, add a branch BEFORE the existing `adjacent_exact` / distance/direction logic so semantic containment renders its confidence:

```python
    if edata.get("relationship") == "contains_semantic":
        conf = edata.get("confidence", "")
        return f" ({conf})" if conf else ""
```

(Place this as the first `if` inside `_edge_detail`. The existing `adjacent_exact` branch and the distance/direction else-branch are unchanged.)

- [ ] **Step 4: Run test to verify it passes (BOTH files — no regression)**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py tests/test_scene_graph.py tests/test_exact_projection.py -v`
Expected: PASS — new NL tests pass AND existing scene_graph + exact_projection tests still green.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/scene_graph.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): render contains_semantic edges in get_context (with confidence)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Tool registration (MCP dispatch + schema + group + agent-direct + targeting)

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`Tool(...)` after the `scene_exact_neighbors` Tool; dispatch `case` after `scene_exact_neighbors`)
- Modify: `mcp_server/src/rook/agent/tool_groups.py` (`scene_graph` group, ~line 452)
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py` (`build_local_tools()`, ~line 1101)
- Modify: `mcp_server/src/rook/targeting.py` (`_ALL_KNOWN_TOOLS` ~line 543; `_RHINO_READ_TOOLS` ~line 701)
- Test: `mcp_server/tests/test_containment_refinement.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_containment_refinement.py
def test_tool_in_group_and_local_handler_and_policy():
    from rook.agent.tool_groups import TOOL_GROUPS
    from rook.agent.tool_dispatcher import build_local_tools
    from rook import targeting
    assert "scene_refine_containment" in TOOL_GROUPS["scene_graph"]
    tools = build_local_tools()
    assert "scene_refine_containment" in tools and callable(tools["scene_refine_containment"])
    pol = targeting.policy_for_tool("scene_refine_containment")
    assert pol.requires_rhino is True and pol.risk == "read"
    assert "scene_refine_containment" in targeting._ALL_KNOWN_TOOLS


def test_local_handler_propagates_failure_and_missing_ids():
    from rook.agent.tool_dispatcher import build_local_tools
    handler = build_local_tools()["scene_refine_containment"]
    out = asyncio.run(handler(object_ids=[]))
    assert out["success"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "in_group or propagates_failure" -v`
Expected: FAIL — tool not registered anywhere yet.

- [ ] **Step 3: Make five edits.**

3a. `agent/tool_groups.py`, `"scene_graph"` group — append the tool:

```python
    "scene_graph": [
        "scene_graph", "scene_context", "scene_query",
        "scene_stats", "scene_classify", "scene_overlay",
        "scene_exact_neighbors", "scene_refine_containment",
    ],
```

3b. `targeting.py`, `_ALL_KNOWN_TOOLS` — add alphabetically (after `scene_query`):

```python
    "scene_query",
    "scene_refine_containment",
    "scene_stats",
```

3c. `targeting.py`, `_RHINO_READ_TOOLS` — add (after `scene_query`):

```python
    "scene_query",
    "scene_refine_containment",
    "scene_stats",
```

3d. `server.py`, in `list_tools` immediately AFTER the `scene_exact_neighbors` `Tool(...)` entry, add:

```python
        Tool(
            name="scene_refine_containment",
            description="""Refine APPROXIMATE bbox `contains` relationships into SEMANTIC, confidence-scored containment for specific objects.

For each object id, evaluates the existing bbox `contains` candidates it participates in (as container and as contained) using evidence already in the scene graph (bbox clearance, geometry type, classification, layer), and returns a verdict (contains_semantic / insufficient_evidence / disqualified) with ordinal confidence (high/medium/low) and an explicit evidence list. Semantic, never geometrically exact. Use it when bbox 'contains' is too coarse and you need to know whether an object is genuinely inside another. Approximate bbox edges are preserved and annotated, never replaced.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs to refine containment for (1..N)",
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"},
                },
                "required": ["object_ids"],
            },
        ),
```

3e. `server.py`, in the dispatch `match` immediately AFTER the `case "scene_exact_neighbors":` block, add:

```python
        case "scene_refine_containment":
            object_ids = arguments.get("object_ids", [])
            if not object_ids:
                result = {"success": False, "data": "Missing object_ids parameter"}
            else:
                from .scene.scene_graph import get_scene_graph
                from .scene.containment_refinement import get_containment_refiner
                sg = get_scene_graph()
                refiner = get_containment_refiner(sg)
                payload = await refiner.refine(object_ids, port=port)
                if not payload.get("success", True):
                    result = {"success": False, "data": payload.get("error", "containment refine failed")}
                else:
                    result = {"success": True, "data": payload}
```

3f. `agent/tool_dispatcher.py`, inside `build_local_tools()` after the `scene_exact_neighbors` handler block (before `tools["gh_update_script"] = ...`), add:

```python
    # --- scene_refine_containment (Python-side semantic containment refinement) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.containment_refinement import get_containment_refiner

        async def _scene_refine_containment(object_ids=None, port: int | None = None, **kwargs) -> dict:
            if not object_ids:
                return {"success": False, "data": "Missing object_ids parameter"}
            sg = get_scene_graph()
            refiner = get_containment_refiner(sg)
            payload = await refiner.refine(object_ids, port=port)
            if not payload.get("success", True):
                return {"success": False, "data": payload.get("error", "containment refine failed")}
            return {"success": True, "data": payload}

        tools["scene_refine_containment"] = _scene_refine_containment
    except ImportError:
        logger.debug("scene_refine_containment local tool unavailable (import failed)")
```

- [ ] **Step 4: Run tests + import sanity**

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -k "in_group or propagates_failure" -v`
Expected: PASS

Run: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && PYTHONPATH=src python -c "import rook.server; from rook.agent.tool_dispatcher import build_local_tools; from rook import targeting; assert 'scene_refine_containment' in build_local_tools(); assert targeting.policy_for_tool('scene_refine_containment').risk=='read'; print('IMPORT_SANITY_OK')"`
Expected: `IMPORT_SANITY_OK` (DSPy/ANTHROPIC_API_KEY warnings are benign).

Run the full new suite: `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py -v`
Expected: PASS (30 tests total).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/targeting.py mcp_server/tests/test_containment_refinement.py
git commit -m "feat(spatial): register scene_refine_containment (MCP schema+dispatch+group, agent-direct, targeting)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Live wiring smoke (manual, Rhino open on SpatialTest.3dm)

Contract/wiring only, NOT domain acceptance — SpatialTest may produce zero containment positives; that is acceptable if the contract is well-formed and Rhino stays stable.

**Files:**
- Create: `docs/rook_docs/occt-spike/live_verify_containment_refinement.py`

- [ ] **Step 1: Write the live smoke script**

```python
# docs/rook_docs/occt-spike/live_verify_containment_refinement.py
"""Live wiring smoke for the ContainmentRefiner (Python read-model).

Requires Rhino OPEN on C:/Users/aryan/Desktop/SpatialTest.3dm with RookNative loaded.
Imports the refiner and runs refine() over a sample of scene objects against the live
mirror, asserting a well-formed contract. CONTRACT/WIRING ONLY — SpatialTest may yield
zero semantic containment positives; that is acceptable. Verdict logic is owned by unit
tests. Port discovery uses urllib only (never curl). Pass port as argv[1] or auto-discover.

  python live_verify_containment_refinement.py [port]
"""
import asyncio
import json
import pathlib
import subprocess
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server" / "src"))

from rook.scene.scene_graph import get_scene_graph          # noqa: E402
from rook.scene.containment_refinement import get_containment_refiner  # noqa: E402


def _get(port, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def discover_port():
    try:
        pids = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process Rhino -ErrorAction SilentlyContinue).Id"], text=True).split()
    except Exception:
        pids = []
    pidset = {p.strip() for p in pids if p.strip()}
    out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
            local, pid = parts[1], parts[4]
            if "127.0.0.1:" in local and pid in pidset:
                port = int(local.rsplit(":", 1)[1])
                try:
                    _get(port, "/scene/graph/stats", 3)
                    return port
                except Exception:
                    continue
    return None


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else discover_port()
    if not port:
        print("FAIL: could not discover the native port (is Rhino open with RookNative?)")
        return 1
    print("port =", port)

    sg = get_scene_graph()
    refiner = get_containment_refiner(sg)
    fails = []

    # Sync once to learn the node ids, then refine over a bounded sample.
    asyncio.run(sg.sync(port=port))
    sample = list(sg.graph.nodes)[:25]
    out = asyncio.run(refiner.refine(sample, port=port))

    if out.get("success") is not True:
        fails.append(f"success={out.get('success')!r} error={out.get('error')!r}")
    if "graphSequence" not in out or "refined" not in out or "bySource" not in out:
        fails.append("missing top-level contract fields")
    for cand in out.get("refined", []):
        if cand["verdict"] not in {"contains_semantic", "insufficient_evidence", "disqualified", "failed"}:
            fails.append(f"bad verdict {cand['verdict']!r}")
        if cand["candidateId"] != f"{cand['containerId']}|contains|{cand['containedId']}":
            fails.append(f"bad candidateId {cand['candidateId']!r}")
    for sid, blk in out.get("bySource", {}).items():
        if blk["status"] not in {"ok", "skipped", "failed"}:
            fails.append(f"bad status {blk['status']!r} for {sid}")

    # Rhino still responsive?
    try:
        _get(port, "/scene/graph/stats", 5)
    except Exception as ex:
        fails.append(f"Rhino unresponsive after refine: {ex}")

    n_pos = sum(1 for c in out.get("refined", []) if c["verdict"] == "contains_semantic")
    print(f"refined={len(out.get('refined', []))} positives={n_pos} "
          f"(zero positives is acceptable for SpatialTest)")
    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("RESULT: ALL PASS — well-formed contract, Rhino stable (contract/wiring only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke (Rhino open on SpatialTest.3dm)**

Run: `python docs/rook_docs/occt-spike/live_verify_containment_refinement.py`
Expected: `RESULT: ALL PASS — well-formed contract, Rhino stable (contract/wiring only).`

- [ ] **Step 3: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add docs/rook_docs/occt-spike/live_verify_containment_refinement.py
git commit -m "test(spatial): live wiring smoke for containment refinement (contract-only)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Full containment + regression suites:
  `cd /c/Users/aryan/source/repos/rook-spatial/mcp_server && python -m pytest tests/test_containment_refinement.py tests/test_scene_graph.py tests/test_exact_projection.py -v`
  Expected: all green.
- [ ] `PYTHONPATH=src python -c "import rook.server"` imports cleanly.
- [ ] Live smoke passes (Rhino open on SpatialTest.3dm).
- [ ] `git status` shows only the intended files committed; `launchSettings.json` and the two `knowledge/*` runtime artifacts remain unstaged.

## Out of scope (do not implement — deferred slices)
Room/space reconstruction, `bounded_by`, hosting/apertures, circulation, zones, native point-in-solid ("Exact Containment Engine"), persistence, IFC export, any new native route, unit conversion, candidate-level cache.

## Carried-forward caveats (separate from this slice)
1. **Exact Containment Engine** (deferred): a native point-in-solid test for a geometrically-exact verdict; v1 is deliberately semantic-only.
2. **`rhino_vision_presentation`** targeting-gate drift (from main's merged #254) resolves on rebase/merge; do not duplicate here.
3. **Task 9b** (pin OCCT 7.9.3) — deferred; separate OCCT worktree/build dir, never switch the shared checkout off V8_0_0.
