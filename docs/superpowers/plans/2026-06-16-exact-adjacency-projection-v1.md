# Exact Adjacency Projection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Python the first consumer of the production OCCT exact-adjacency route, projecting its `adjacent_exact` edges into the networkx scene-graph mirror as typed, idempotent, IFC-aligned relationship edges exposed by a new `scene_exact_neighbors` MCP tool.

**Architecture:** A read-model layer only — **zero C++ changes**. A new isolated module `scene/exact_projection.py` holds `ExactAdjacencyProjector`, which calls the existing `/scene/graph/adjacency/exact` route, prepares a per-source delta (edges + reconciliation annotations) in memory, commits it atomically into the `SceneGraphAnalytics` mirror, caches per `graphSequence`, and actively prunes stale projection artifacts when the sequence advances. Units come from the route and are never converted in Python.

**Tech Stack:** Python 3.11+, networkx `MultiDiGraph`, pytest (`asyncio.run` pattern, no live Rhino), MCP `Tool` registration in `server.py`, tool-group disclosure in `agent/tool_groups.py`.

**Spec:** `docs/superpowers/specs/2026-06-16-exact-adjacency-projection-v1-design.md` (committed `70a00dee`).

**Branch discipline:** Work only on `feature/spatial-intelligence` in worktree `C:/Users/aryan/source/repos/rook-spatial`. Verify `git branch --show-current` before every commit. **Never stage `src/Rook/Properties/launchSettings.json`** (pre-existing unrelated dirt) — stage only the explicit files each task names.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mcp_server/src/rook/scene/exact_projection.py` | The projector: route call, prepare/commit delta, cache, prune. Owns no graph. | **Create** |
| `mcp_server/tests/test_exact_projection.py` | Unit tests (no Rhino): faked route payload, idempotency, annotations, cache/prune, isolation, atomicity. | **Create** |
| `mcp_server/src/rook/scene/scene_graph.py` | NL surface gains `adjacent_exact` rendering (`_inverse_rel` + `_format_node`). | **Modify** |
| `mcp_server/src/rook/server.py` | `scene_exact_neighbors` `Tool` schema in `list_tools` + dispatch `case`. | **Modify** |
| `mcp_server/src/rook/agent/tool_groups.py` | Add `scene_exact_neighbors` to the `scene_graph` group. | **Modify (line ~452)** |
| `docs/rook_docs/occt-spike/live_verify_exact_projection.py` | Manual live wiring smoke on SpatialTest.3dm. | **Create** |

All projected facts are ephemeral, valid only for the `graphSequence` they were computed against (spec §4).

---

### Task 1: Module scaffold — constants, canonical-pair helper, `_SourceDelta`

**Files:**
- Create: `mcp_server/src/rook/scene/exact_projection.py`
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# mcp_server/tests/test_exact_projection.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.scene.exact_projection'`

- [ ] **Step 3: Write minimal implementation**

```python
# mcp_server/src/rook/scene/exact_projection.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/exact_projection.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): exact_projection module scaffold (constants, canonical pair, _SourceDelta)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Canonical idempotent edge upsert

**Files:**
- Modify: `mcp_server/src/rook/scene/exact_projection.py`
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_exact_projection.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py::test_upsert_is_idempotent_and_canonical -v`
Expected: FAIL — `AttributeError: 'ExactAdjacencyProjector' object has no attribute '_upsert_exact_edge'` (and the class does not exist yet)

- [ ] **Step 3: Write minimal implementation**

```python
# append to exact_projection.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/exact_projection.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): canonical idempotent adjacent_exact edge upsert

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Prepare + commit per-source delta (neighbors / refuted / failed / bbox annotations)

This is the core. `_prepare_source_delta` parses a route payload into an in-memory delta (no graph mutation). `_commit_source_delta` applies edges + bbox annotations in one shot and invalidates analytics caches. Prepare-then-commit gives atomicity: if prepare raises, commit is never reached.

**Files:**
- Modify: `mcp_server/src/rook/scene/exact_projection.py`
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_exact_projection.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -k "prepare_and_commit or atomicity" -v`
Expected: FAIL — `AttributeError: ... has no attribute '_prepare_source_delta'`

- [ ] **Step 3: Write minimal implementation**

```python
# add methods to ExactAdjacencyProjector
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/exact_projection.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): prepare/commit per-source delta with bbox reconciliation annotations

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Cache + active prune on graphSequence advance

**Files:**
- Modify: `mcp_server/src/rook/scene/exact_projection.py`
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_exact_projection.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -k "prune" -v`
Expected: FAIL — `AttributeError: ... has no attribute '_purge_projection_artifacts'`

- [ ] **Step 3: Write minimal implementation**

```python
# add methods to ExactAdjacencyProjector
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/exact_projection.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): sequence-keyed prune of projection artifacts + cache invalidation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `project()` orchestration + return contract + per-source isolation

**Files:**
- Modify: `mcp_server/src/rook/scene/exact_projection.py`
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_exact_projection.py
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


async def _should_not_be_called(*a, **k):
    raise AssertionError("call_rhino must not be called for a skipped source")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -k "project_" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'project'`

- [ ] **Step 3: Write minimal implementation**

```python
# add methods + module singleton to exact_projection.py
    @staticmethod
    def _cache_key(graph_sequence: int, source_id: str, candidate_scope: str) -> tuple:
        return (graph_sequence, source_id, candidate_scope, ENGINE_VERSION)

    @staticmethod
    def _empty_block(source_id: str, status: str, error: str | None) -> dict:
        return {
            "sourceId": source_id, "routeStatus": status, "error": error,
            "sourceCapability": "", "capabilitiesById": {},
            "lengthUnit": None, "areaUnit": None,
            "neighbors": [], "refuted": [], "failed": [], "diagnostics": [],
        }

    @staticmethod
    def _delta_to_block(delta: _SourceDelta) -> dict:
        return {
            "sourceId": delta.source_id, "routeStatus": delta.route_status,
            "error": delta.error, "sourceCapability": delta.source_capability,
            "capabilitiesById": delta.capabilities_by_id,
            "lengthUnit": delta.length_unit, "areaUnit": delta.area_unit,
            "neighbors": delta.neighbors, "refuted": delta.refuted,
            "failed": delta.failed, "diagnostics": delta.diagnostics,
        }

    async def _project_one(self, source_id, candidate_scope, graph_sequence, port) -> dict:
        if not self._analytics.graph.has_node(source_id):
            return self._empty_block(source_id, "skipped", "object_not_in_scene")
        try:
            resp = await call_rhino(
                "/scene/graph/adjacency/exact", "POST",
                {"objectId": source_id, "candidateScope": candidate_scope}, port=port)
        except Exception as ex:  # transport-level failure
            logger.warning("exact route raised for %s: %s", source_id, ex)
            return self._empty_block(source_id, "failed", str(ex))
        if not resp.get("success"):
            err = str(resp.get("data", "exact route failed"))
            status = "timeout" if "timeout" in err.lower() else "failed"
            return self._empty_block(source_id, status, err)
        try:
            delta = self._prepare_source_delta(source_id, resp.get("data") or {}, graph_sequence)
            self._commit_source_delta(delta)
        except Exception as ex:  # malformed payload -> isolate, graph untouched (prepare-then-commit)
            logger.warning("exact projection parse failed for %s: %s", source_id, ex)
            return self._empty_block(source_id, "failed", f"parse_error: {ex}")
        return self._delta_to_block(delta)

    async def project(self, object_ids, *, candidate_scope=DEFAULT_CANDIDATE_SCOPE, port=None) -> dict:
        await self._analytics.sync(port=port)
        graph_sequence = self._analytics.sequence
        self._prune_if_advanced(graph_sequence)

        projected: list[dict] = []
        hits = misses = 0
        unit_pairs: set[tuple] = set()
        for source_id in object_ids:
            key = self._cache_key(graph_sequence, source_id, candidate_scope)
            if key in self._cache:
                block = copy.deepcopy(self._cache[key])
                for n in block.get("neighbors", []):
                    n["fromCache"] = True
                hits += 1
            else:
                block = await self._project_one(source_id, candidate_scope, graph_sequence, port)
                self._cache[key] = copy.deepcopy(block)
                misses += 1
            projected.append(block)
            lu, au = block.get("lengthUnit"), block.get("areaUnit")
            if lu is not None or au is not None:
                unit_pairs.add((lu, au))

        result = {
            "success": True, "graphSequence": graph_sequence,
            "projected": projected, "cache": {"hits": hits, "misses": misses},
        }
        if len(unit_pairs) == 1:
            lu, au = next(iter(unit_pairs))
            result.update({"unitsUniform": True, "lengthUnit": lu, "areaUnit": au})
        else:
            # no units seen -> vacuously uniform; conflicting units -> not uniform, omit top-level
            result["unitsUniform"] = (len(unit_pairs) == 0)
        return result


_projector: ExactAdjacencyProjector | None = None


def get_exact_projector(analytics: SceneGraphAnalytics | None = None) -> ExactAdjacencyProjector:
    """Module singleton, bound to the shared scene-graph analytics mirror."""
    global _projector
    if _projector is None:
        _projector = ExactAdjacencyProjector(analytics or get_scene_graph())
    return _projector
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/exact_projection.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): project() orchestration, return contract, per-source isolation + singleton

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: NL rendering of `adjacent_exact` via get_context

**Files:**
- Modify: `mcp_server/src/rook/scene/scene_graph.py` (`_INVERSE_RELS` ~line 474; `_format_node` ~line 298–324)
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_exact_projection.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -k "exact_adjacency or inverse_rel" -v`
Expected: FAIL — `_inverse_rel("adjacent_exact")` returns `"adjacent_exact"`; rendering lacks shared-face text.

- [ ] **Step 3: Write minimal implementation**

In `scene_graph.py`, add to `_INVERSE_RELS` (the dict near line 474):

```python
    "adjacent_exact": "adjacent to (exact)",
```

In `_format_node`, replace the out-edge detail block (currently lines ~306–312) with a helper-based version that renders exact edges from their own `areaUnit`. Add this module-level helper near `_inverse_rel`:

```python
def _edge_detail(edata: dict) -> str:
    """Trailing detail string for an edge line (exact area, distance, direction)."""
    if edata.get("relationship") == "adjacent_exact":
        area = edata.get("sharedArea")
        unit = edata.get("areaUnit", "")
        if area is not None:
            return f", shared face {area:.2f} {unit}".rstrip()
        return ""
    dist = edata.get("distance", 0)
    direction = edata.get("direction", "")
    detail = ""
    if dist > 0:
        detail = f", {dist:.2f}m"
    if direction:
        detail += f", {direction}"
    return detail
```

Then in `_format_node`, the out-edges loop becomes:

```python
        for _, target, edata in self.graph.out_edges(node_id, data=True):
            rel = edata.get("relationship", "?")
            t_attrs = self.graph.nodes.get(target, {})
            t_label = (t_attrs.get("domain_label") or t_attrs.get("shape_class") or "?").upper()
            t_name = t_attrs.get("name") or target[:8]
            lines.append(f'  {rel}: {t_label} "{t_name}"{_edge_detail(edata)}')
```

and the in-edges loop becomes:

```python
        for source, _, edata in self.graph.in_edges(node_id, data=True):
            rel = edata.get("relationship", "?")
            s_attrs = self.graph.nodes.get(source, {})
            s_label = (s_attrs.get("domain_label") or s_attrs.get("shape_class") or "?").upper()
            s_name = s_attrs.get("name") or source[:8]
            inverse = _inverse_rel(rel)
            lines.append(f'  {inverse}: {s_label} "{s_name}"{_edge_detail(edata)}')
```

This preserves existing distance/direction behavior for bbox edges (the `_edge_detail` else-branch reproduces it) and adds shared-face rendering for `adjacent_exact`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py tests/test_scene_graph.py -v`
Expected: PASS — new NL tests pass AND existing `test_scene_graph.py` still green (no regression in distance/direction rendering).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/scene/scene_graph.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): render adjacent_exact edges in get_context (shared face from areaUnit)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: MCP tool registration (dispatch + schema + tool group)

All three coordinated edits (spec §2). Unit-test the deterministic part (group membership); the schema + dispatch are exercised by the live smoke in Task 8.

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`Tool(...)` list in `list_tools` ~line 11063; dispatch `case` ~line 19127)
- Modify: `mcp_server/src/rook/agent/tool_groups.py` (line 452, `scene_graph` group)
- Test: `mcp_server/tests/test_exact_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_exact_projection.py
def test_tool_registered_in_scene_graph_group():
    from rook.agent.tool_groups import TOOL_GROUPS  # noqa: WPS433
    assert "scene_exact_neighbors" in TOOL_GROUPS["scene_graph"]
```

(Confirmed: the dict is `TOOL_GROUPS: Dict[str, List[str]]` at `tool_groups.py:102`, with the `"scene_graph"` group at line 452.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -k "tool_registered" -v`
Expected: FAIL — `assert 'scene_exact_neighbors' in [...]`

- [ ] **Step 3: Write minimal implementation**

3a. In `agent/tool_groups.py`, line 452 group — add the tool:

```python
    "scene_graph": [
        "scene_graph", "scene_context", "scene_query",
        "scene_stats", "scene_classify", "scene_overlay",
        "scene_exact_neighbors",
    ],
```

3b. In `server.py`, in `list_tools` immediately after the `scene_stats` `Tool(...)` (~line 11073), add:

```python
        Tool(
            name="scene_exact_neighbors",
            description="""Project EXACT (OCCT shared-face) adjacency for specific objects into the scene graph.

For each object id, computes precise boundary adjacency via the native OCCT engine and returns its exact neighbors with shared-face area and face-pair detail. Use this when approximate bbox 'adjacent' is not enough and you need to know what *actually* touches an object (e.g. which walls truly abut a floorplate). Progressive disclosure: call again with newly discovered neighbor ids to expand the exact frontier. Approximate bbox edges are preserved and annotated, never replaced.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs to compute exact neighbors for (1..N)",
                    },
                    "candidate_scope": {
                        "type": "string",
                        "enum": ["broad_phase_default"],
                        "description": "Candidate-set policy (v1: broad_phase_default only)",
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"},
                },
                "required": ["object_ids"],
            },
        ),
```

3c. In `server.py`, in the dispatch `match` (after `case "scene_stats":` ~line 19135), add:

```python
        case "scene_exact_neighbors":
            object_ids = arguments.get("object_ids", [])
            if not object_ids:
                result = {"success": False, "data": "Missing object_ids parameter"}
            else:
                from .scene.scene_graph import get_scene_graph
                from .scene.exact_projection import get_exact_projector
                sg = get_scene_graph()
                projector = get_exact_projector(sg)
                payload = await projector.project(
                    object_ids,
                    candidate_scope=arguments.get("candidate_scope", "broad_phase_default"),
                    port=port,
                )
                result = {"success": True, "data": payload}
```

- [ ] **Step 4: Run test + import sanity**

Run: `cd mcp_server && python -m pytest tests/test_exact_projection.py -k "tool_registered" -v`
Expected: PASS

Run: `cd mcp_server && python -c "import rook.server"`
Expected: no SyntaxError / ImportError (the new `Tool` + `case` parse and import cleanly).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_exact_projection.py
git commit -m "feat(spatial): register scene_exact_neighbors MCP tool (schema + dispatch + group)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Live wiring smoke (manual, Rhino open on SpatialTest.3dm)

Proves end-to-end wiring against the real route; does **not** revalidate the OCCT engine (that's the engine's own gate). urllib only — never curl.

**Files:**
- Create: `docs/rook_docs/occt-spike/live_verify_exact_projection.py`

- [ ] **Step 1: Write the live smoke script**

```python
# docs/rook_docs/occt-spike/live_verify_exact_projection.py
"""Live wiring smoke for scene_exact_neighbors / ExactAdjacencyProjector.

Requires Rhino OPEN on C:/Users/aryan/Desktop/SpatialTest.3dm with RookNative loaded.
Proves the Python projection layer wires to the production exact route end-to-end.
Does NOT revalidate the OCCT engine (that is live_verify_occt_adjacency.py's job).

urllib only (never curl). Auto-discovers the native port or accepts argv[1].

  python live_verify_exact_projection.py [port]
"""
import json
import subprocess
import sys
import urllib.request

SOURCE = "08d4dedf-1387-453a-9938-7f3ab516b8ac"  # the floorplate (5 abutments)
EXPECT_PREFIXES = {"71065f57", "5c12cc83", "be0ca730", "7e80db98", "26b2c012"}


def get(port, path, timeout=8):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def post(port, path, body, timeout=120):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
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
                    get(port, "/scene/graph/stats", 3)
                    return port
                except Exception:
                    continue
    return None


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else discover_port()
    if not port:
        print("FAIL: could not discover the native port (is Rhino open with RookNative?)")
        return 1

    # The projection layer lives in the MCP server, not the native plugin. This smoke
    # exercises the NATIVE route the projector consumes, then mirrors the projector's
    # own logic (canonical edge + areaUnit pass-through) to prove the contract the
    # Python layer depends on is present. (Full MCP-tool exercise = manual /mcp call.)
    fails = []
    d = post(port, "/scene/graph/adjacency/exact",
             {"objectId": SOURCE, "candidateScope": "broad_phase_default"}).get("data", {})
    if d.get("areaUnit") != "inches^2":
        fails.append(f"areaUnit={d.get('areaUnit')!r}")
    if d.get("lengthUnit") != "inches":
        fails.append(f"lengthUnit={d.get('lengthUnit')!r}")
    got = {e.get("targetId", "")[:8] for e in d.get("edges", [])}
    missing = EXPECT_PREFIXES - got
    if missing:
        fails.append(f"missing abutments {missing}")
    for e in d.get("edges", []):
        if not e.get("facePairs"):
            fails.append(f"edge {e.get('targetId','')[:8]} has no facePairs")

    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print(f"RESULT: PASS — route returns 5 abutments + units + facePairs (port {port}).")
    print("Next (manual): call the scene_exact_neighbors MCP tool with object_ids=["
          f"'{SOURCE}'] and confirm projected[0].neighbors has 5 entries with "
          "fromCache False, then call again and confirm fromCache True (cache hit).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke (Rhino open on SpatialTest.3dm)**

Run: `python docs/rook_docs/occt-spike/live_verify_exact_projection.py`
Expected: `RESULT: PASS — route returns 5 abutments + units + facePairs`.

- [ ] **Step 3: Manual MCP-tool exercise**

In an MCP session against the running Rhino, call `scene_exact_neighbors` with
`{"object_ids": ["08d4dedf-1387-453a-9938-7f3ab516b8ac"]}`. Confirm:
- `projected[0].routeStatus == "ok"`, 5 neighbors, each `fromCache == false`, `areaUnit == "inches^2"`;
- a second identical call returns the same neighbors with `fromCache == true` and `cache.hits == 1`;
- `scene_context` with that id now renders `adjacent to (exact): ... shared face <area> inches^2`.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/aryan/source/repos/rook-spatial
test "$(git branch --show-current)" = "feature/spatial-intelligence"
git add docs/rook_docs/occt-spike/live_verify_exact_projection.py
git commit -m "test(spatial): live wiring smoke for exact adjacency projection

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the full projection unit suite + scene-graph regression:
  `cd mcp_server && python -m pytest tests/test_exact_projection.py tests/test_scene_graph.py -v`
  Expected: all green.
- [ ] `python -c "import rook.server"` imports cleanly.
- [ ] Live smoke + manual MCP exercise pass with Rhino open on SpatialTest.3dm.
- [ ] `git status` shows only the intended files committed; `src/Rook/Properties/launchSettings.json` still unstaged/untouched.

## Out of scope (do not implement — deferred slices)
Containment refinement, hosting/apertures, circulation, zones, Spike F, persistent native exact edges, native incremental invalidation, internal graph-walk expansion, whole-model sweep (`project_exact_all`), bounded-radius expansion, any unit conversion.

## Carried-forward caveats (separate from this slice)
1. Before the **branch** is merge/release-gated, extend the engine's `live_verify_occt_adjacency.py` to also cover wall×wall `18651.672 in²`, unsupported-geometry diagnostics, and an `exact_brep` no-neighbor case. (Engine gate, not this slice.)
2. Task 9b (pin OCCT 7.9.3) — deferred; separate OCCT worktree/build dir, never switch the shared checkout off V8_0_0. See `docs/rook_docs/occt-build.md`.
