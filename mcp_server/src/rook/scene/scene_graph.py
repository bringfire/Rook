"""
Scene Graph Analytics
=====================

Syncs graph data from the active Rhino bridge into a NetworkX DiGraph,
then provides graph algorithms and LLM-friendly natural language formatting.

Architecture:
    The Rhino plugin owns the live graph (nodes, edges, RTree).
    Python fetches snapshots via HTTP, builds a NetworkX mirror,
    and adds analytics that are expensive/awkward in C# (community
    detection, centrality, shortest path, containment tree).

Sync strategy:
    - On-demand: fetches when an agent/tool asks, not continuously
    - Incremental: uses /scene/graph/diff with sequence tracking
    - Cached: NetworkX graph cached until next sync
"""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx

from ..bridge import call_rhino

logger = logging.getLogger(__name__)

# Module-level singleton
_instance: SceneGraphAnalytics | None = None


def get_scene_graph() -> SceneGraphAnalytics:
    """Get or create the singleton SceneGraphAnalytics instance."""
    global _instance
    if _instance is None:
        _instance = SceneGraphAnalytics()
    return _instance


class SceneGraphAnalytics:
    """NetworkX mirror of the Rhino scene graph with graph algorithms."""

    def __init__(self) -> None:
        # MultiDiGraph (not DiGraph) so parallel edges with different
        # relationships are preserved. The C++ ComputePairRelationships
        # function (SceneGraph.cpp) can emit multiple SceneEdges for the
        # same (sourceId, targetId) pair — e.g., a column whose top
        # touches a slab's bottom is both `intersects` (bbox overlap) and
        # `supports` (vertical adjacency with horizontal coverage).
        # DiGraph collapsed those silently; MultiDiGraph stores all of them.
        self.graph = nx.MultiDiGraph()
        self._sequence: int = 0
        # Cached algorithm results — invalidated on sync
        self._communities: dict[str, list[str]] | None = None
        self._centrality: dict[str, float] | None = None

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    @property
    def sequence(self) -> int:
        return self._sequence

    # ================================================================
    # Sync from Rhino
    # ================================================================

    async def sync(self, port: int | None = None) -> dict[str, Any]:
        """Sync graph from C#. Uses diff if we have a prior sequence, else full fetch.

        Returns summary of what changed.
        """
        if self._sequence == 0:
            return await self._full_sync(port)
        return await self._diff_sync(port)

    async def _full_sync(self, port: int | None = None) -> dict[str, Any]:
        """Full graph fetch — used on first call or after clear."""
        result = await call_rhino("/scene/graph", "GET", {"depth": "full"}, port=port)
        if not result.get("success"):
            return {"synced": False, "error": result.get("data", "Unknown error")}

        data = result["data"]
        self.graph.clear()
        self._invalidate_caches()

        # C++ HandleSceneGraph (full depth) emits camelCase / lowercase keys.
        # See SceneGraphHandler.cpp HandleSceneGraph + SerializeNodeFull/EdgeFull.
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        self._sequence = data.get("sequence", 0)

        for node in nodes:
            self._add_node(node)

        for edge in edges:
            self._add_edge(edge)

        return {
            "synced": True,
            "mode": "full",
            "nodes": len(nodes),
            "edges": len(edges),
            "sequence": self._sequence,
        }

    async def _diff_sync(self, port: int | None = None) -> dict[str, Any]:
        """Incremental sync via diff endpoint."""
        result = await call_rhino(
            "/scene/graph/diff", "POST",
            {"since_sequence": self._sequence},
            port=port,
        )
        if not result.get("success"):
            # Fall back to full sync on diff failure
            logger.warning("Diff sync failed, falling back to full sync")
            return await self._full_sync(port)

        data = result["data"]
        # C++ HandleSceneGraphDiff emits camelCase keys.
        new_seq = data.get("currentSequence", self._sequence)

        # If the Rhino-side sequence is behind ours (e.g., graph was cleared), do full sync
        if new_seq < self._sequence:
            return await self._full_sync(port)

        added = data.get("addedNodes", [])
        removed = data.get("removedNodeIds", [])
        modified = data.get("modifiedNodes", [])
        added_edges = data.get("addedEdges", [])
        removed_edges = data.get("removedEdges", [])

        changes = len(added) + len(removed) + len(modified) + len(added_edges) + len(removed_edges)

        if changes > 0:
            self._invalidate_caches()

        for node_id in removed:
            if self.graph.has_node(node_id):
                self.graph.remove_node(node_id)

        for node in modified:
            nid = node.get("id", "")
            if self.graph.has_node(nid):
                self.graph.nodes[nid].update(self._node_attrs(node))

        for node in added:
            self._add_node(node)

        for edge in removed_edges:
            # The diff endpoint uses SerializeEdge (compact), which writes
            # source/target/rel — different from SerializeEdgeFull's
            # sourceId/targetId/relationship. Accept either via fallback.
            src = edge.get("sourceId") or edge.get("source") or ""
            tgt = edge.get("targetId") or edge.get("target") or ""
            rel = edge.get("relationship") or edge.get("rel") or ""
            if not self.graph.has_edge(src, tgt):
                continue
            # MultiDiGraph: self.graph[src][tgt] is a {key: data} dict of
            # parallel edges. Find the specific edge whose relationship
            # matches and remove it by key. Remove only one matching edge
            # per RemovedEdges entry — the C++ side emits one diff entry
            # per removed edge, so we mirror that 1:1.
            edge_dict = self.graph[src][tgt]
            for key, data in list(edge_dict.items()):
                if data.get("relationship") == rel:
                    self.graph.remove_edge(src, tgt, key=key)
                    break

        for edge in added_edges:
            self._add_edge(edge)

        self._sequence = new_seq

        return {
            "synced": True,
            "mode": "diff",
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "added_edges": len(added_edges),
            "removed_edges": len(removed_edges),
            "sequence": self._sequence,
        }

    def _add_node(self, node: dict) -> None:
        nid = node.get("id", "")
        if not nid:
            return
        self.graph.add_node(nid, **self._node_attrs(node))

    def _add_edge(self, edge: dict) -> None:
        # Accept both edge formats:
        #   SerializeEdgeFull (full sync): sourceId / targetId / relationship
        #   SerializeEdge (diff sync):     source / target / rel
        src = edge.get("sourceId") or edge.get("source") or ""
        tgt = edge.get("targetId") or edge.get("target") or ""
        if not src or not tgt:
            return
        self.graph.add_edge(
            src, tgt,
            relationship=edge.get("relationship") or edge.get("rel") or "",
            distance=edge.get("distance", 0),
            overlap=edge.get("overlap", 0),
            direction=edge.get("direction", ""),
        )

    @staticmethod
    def _node_attrs(node: dict) -> dict:
        """Extract node attributes from Rhino JSON.

        C++ side uses camelCase keys (see SerializeNodeFull / SerializeNodeCompact
        in src/RookNative/Handlers/SceneGraphHandler.cpp). Compact nodes from the
        diff endpoint carry only id/name/layer/label/shapeClass/domainLabel —
        all other fields (metrics, bbox, creation metadata) default to zero/empty.
        """
        metrics = node.get("metrics", {})
        return {
            "name": node.get("name", ""),
            "layer": node.get("layer", ""),
            "geometry_type": node.get("geometryType", ""),
            "shape_class": node.get("shapeClass", ""),
            "domain_label": node.get("domainLabel", ""),
            "confidence": node.get("classConfidence", 0),
            "bbox_min": node.get("bboxMin", [0, 0, 0]),
            "bbox_max": node.get("bboxMax", [0, 0, 0]),
            "max_dim": metrics.get("maxDim", 0),
            "mid_dim": metrics.get("midDim", 0),
            "min_dim": metrics.get("minDim", 0),
            "elongation": metrics.get("elongation", 0),
            "flatness": metrics.get("flatness", 0),
            "thinness": metrics.get("thinness", 0),
            "volume": metrics.get("volume", 0),
            "centroid_z": metrics.get("centroidZ", 0),
            "base_z": metrics.get("baseZ", 0),
            "top_z": metrics.get("topZ", 0),
            "primary_axis": metrics.get("primaryAxis", ""),
            "thin_axis": metrics.get("thinAxis", ""),
            "created_by": node.get("createdBy", ""),
            "creation_intent": node.get("creationIntent", ""),
            "creation_command": node.get("creationCommand", ""),
        }

    def _invalidate_caches(self) -> None:
        self._communities = None
        self._centrality = None

    # ================================================================
    # Natural Language Context
    # ================================================================

    def get_context(self, object_ids: list[str]) -> str:
        """Natural-language spatial summary for agent consumption.

        Example output:
            WALL "Wall-01" (vertical-planar, 10.0 x 0.2 x 3.0)
            - Layer: "Walls-Ground"
            - Created by: rhino_execute_intent ("create a wall...")
            - Supports: SLAB "Floor-01" (above, 0.01m gap)
            - Adjacent to: WALL "Wall-02" (east, touching)
        """
        parts = []
        for oid in object_ids:
            if not self.graph.has_node(oid):
                parts.append(f"Object '{oid}' not in scene graph.")
                continue
            parts.append(self._format_node(oid))
        return "\n\n".join(parts)

    def _format_node(self, node_id: str) -> str:
        """Format a single node with its relationships."""
        attrs = self.graph.nodes[node_id]
        label = attrs.get("domain_label") or attrs.get("shape_class") or "unknown"
        name = attrs.get("name") or node_id[:8]
        dims = f"{attrs.get('max_dim', 0):.1f} x {attrs.get('mid_dim', 0):.1f} x {attrs.get('min_dim', 0):.1f}"

        lines = [f'{label.upper()} "{name}" ({attrs.get("shape_class", "?")}, {dims})']

        layer = attrs.get("layer", "")
        if layer:
            lines.append(f'  Layer: "{layer}"')

        created_by = attrs.get("created_by", "")
        intent = attrs.get("creation_intent", "")
        if created_by:
            intent_part = f' ("{intent}")' if intent else ""
            lines.append(f"  Created by: {created_by}{intent_part}")

        bim_lines = self._format_bim_block(node_id, attrs)
        lines.extend(bim_lines)
        suppress_compacted_bim_edges = bool(attrs.get("rookbimJoined") and bim_lines)

        # Outgoing edges (this node is source)
        for _, target, edata in self.graph.out_edges(node_id, data=True):
            rel = edata.get("relationship", "?")
            if suppress_compacted_bim_edges and rel in _COMPACT_BIM_RELATIONSHIPS:
                continue
            t_attrs = self.graph.nodes.get(target, {})
            t_label = (t_attrs.get("domain_label") or t_attrs.get("shape_class") or "?").upper()
            t_name = t_attrs.get("displayName") or t_attrs.get("name") or target[:8]
            lines.append(f'  {_forward_rel(rel)}: {t_label} "{t_name}"{_edge_detail(edata)}')

        # Incoming edges (this node is target)
        for source, _, edata in self.graph.in_edges(node_id, data=True):
            rel = edata.get("relationship", "?")
            if suppress_compacted_bim_edges and rel in _COMPACT_BIM_RELATIONSHIPS:
                continue
            s_attrs = self.graph.nodes.get(source, {})
            s_label = (s_attrs.get("domain_label") or s_attrs.get("shape_class") or "?").upper()
            s_name = s_attrs.get("displayName") or s_attrs.get("name") or source[:8]
            inverse = _inverse_rel(rel)
            lines.append(f'  {inverse}: {s_label} "{s_name}"{_edge_detail(edata)}')

        return "\n".join(lines)

    def _format_bim_block(self, node_id: str, attrs: dict[str, Any]) -> list[str]:
        if not attrs.get("rookbimJoined"):
            return []

        category = attrs.get("revitCategory", "")
        family = attrs.get("revitFamily", "")
        type_name = attrs.get("revitType", "")
        title_parts = [str(part) for part in (category, family, type_name) if part]
        title = " | ".join(title_parts) if title_parts else "joined"
        lines = [f"  BIM: {title}"]

        element_id = attrs.get("revitElementId", "")
        unique_id = attrs.get("revitUniqueId", "")
        revit_parts = []
        if element_id:
            revit_parts.append(f"element {element_id}")
        if unique_id:
            revit_parts.append(f"uniqueId {unique_id}")
        if revit_parts:
            lines.append(f"    Revit: {', '.join(revit_parts)}")

        rooms = self._bim_targets(node_id, "revit_in_room")
        levels = self._bim_targets(node_id, "revit_on_level")
        hosted_by = self._bim_targets(node_id, "revit_hosted_by")
        host_count = sum(
            1 for _, _, edata in self.graph.in_edges(node_id, data=True)
            if edata.get("relationship") == "revit_hosted_by"
        )

        if rooms:
            lines.append(f"    Room: {self._format_limited_names(rooms)}")
        if levels:
            lines.append(f"    Level: {self._format_limited_names(levels)}")
        if hosted_by:
            lines.append(f"    Hosted by: {self._format_limited_names(hosted_by)}")
        if host_count:
            suffix = "element" if host_count == 1 else "elements"
            lines.append(f"    Hosts: {host_count} {suffix}")

        return lines

    def _bim_targets(self, node_id: str, relationship: str) -> list[str]:
        names: list[str] = []
        for _, target, edata in self.graph.out_edges(node_id, data=True):
            if edata.get("relationship") != relationship:
                continue
            t_attrs = self.graph.nodes.get(target, {})
            name = t_attrs.get("displayName") or t_attrs.get("name") or target[:8]
            names.append(str(name))
        return names

    @staticmethod
    def _format_limited_names(names: list[str], limit: int = 3) -> str:
        shown = names[:limit]
        suffix = f", +{len(names) - limit} more" if len(names) > limit else ""
        return ", ".join(shown) + suffix

    # ================================================================
    # Graph Algorithms
    # ================================================================

    def find_path(self, id_a: str, id_b: str) -> list[str]:
        """Shortest spatial path between two objects."""
        undirected = self.graph.to_undirected()
        try:
            return nx.shortest_path(undirected, id_a, id_b)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def community_detection(self) -> dict[str, list[str]]:
        """Cluster objects into spatial groups using Louvain method.

        Returns dict mapping community_id -> list of node IDs.
        """
        if self._communities is not None:
            return self._communities

        if self.graph.number_of_nodes() == 0:
            self._communities = {}
            return self._communities

        undirected = self.graph.to_undirected()
        try:
            communities = nx.community.louvain_communities(undirected, seed=42)
            self._communities = {
                f"group_{i}": list(comm)
                for i, comm in enumerate(communities)
            }
        except Exception:
            self._communities = {}

        return self._communities

    def centrality(self) -> dict[str, float]:
        """Degree centrality — which objects are most spatially connected."""
        if self._centrality is not None:
            return self._centrality

        if self.graph.number_of_nodes() == 0:
            self._centrality = {}
            return self._centrality

        self._centrality = nx.degree_centrality(self.graph)
        return self._centrality

    def containment_tree(self) -> dict:
        """Build hierarchical containment view from 'contains' edges.

        Returns a nested dict: {node_id: {children: [...], label: ...}}
        """
        # Find all "contains" edges
        contains_edges = [
            (u, v) for u, v, d in self.graph.edges(data=True)
            if d.get("relationship") == "contains"
        ]

        # Build a tree (contained objects are children)
        children: dict[str, list[str]] = {}
        contained: set[str] = set()
        for parent, child in contains_edges:
            children.setdefault(parent, []).append(child)
            contained.add(child)

        # Roots are nodes that contain others but aren't contained themselves
        roots = [n for n in children if n not in contained]
        # Also include isolated nodes (no containment edges)
        all_in_containment = set(children.keys()) | contained
        isolated = [n for n in self.graph.nodes if n not in all_in_containment]

        def build_subtree(nid: str) -> dict:
            attrs = self.graph.nodes.get(nid, {})
            label = attrs.get("domain_label") or attrs.get("shape_class") or "unknown"
            result: dict[str, Any] = {
                "id": nid,
                "label": label,
                "name": attrs.get("name", ""),
            }
            if nid in children:
                result["children"] = [build_subtree(c) for c in children[nid]]
            return result

        return {
            "roots": [build_subtree(r) for r in roots],
            "isolated_count": len(isolated),
        }

    def get_stats(self) -> dict[str, Any]:
        """Graph statistics summary."""
        rel_counts: dict[str, int] = {}
        for _, _, d in self.graph.edges(data=True):
            rel = d.get("relationship", "unknown")
            rel_counts[rel] = rel_counts.get(rel, 0) + 1

        class_counts: dict[str, int] = {}
        for _, d in self.graph.nodes(data=True):
            label = d.get("domain_label") or d.get("shape_class") or "unclassified"
            class_counts[label] = class_counts.get(label, 0) + 1

        components = nx.number_weakly_connected_components(self.graph) if self.node_count > 0 else 0

        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "components": components,
            "density": nx.density(self.graph) if self.node_count > 1 else 0,
            "classifications": class_counts,
            "relationships": rel_counts,
            "sequence": self._sequence,
        }

    def export_json(self) -> dict:
        """Export as JSON Graph Format (jsongraphformat.info)."""
        nodes = {}
        for nid, attrs in self.graph.nodes(data=True):
            nodes[nid] = {
                "label": attrs.get("domain_label") or attrs.get("shape_class") or "",
                "metadata": {k: v for k, v in attrs.items()},
            }

        edges = []
        for src, tgt, attrs in self.graph.edges(data=True):
            edges.append({
                "source": src,
                "target": tgt,
                "relation": attrs.get("relationship", ""),
                "metadata": {k: v for k, v in attrs.items()},
            })

        return {
            "graph": {
                "type": "scene_graph",
                "directed": True,
                "metadata": {"sequence": self._sequence},
                "nodes": nodes,
                "edges": edges,
            }
        }


# ================================================================
# Helpers
# ================================================================

_COMPACT_BIM_RELATIONSHIPS = frozenset({
    "revit_hosted_by",
    "revit_in_room",
    "revit_on_level",
})

_INVERSE_RELS = {
    "contains": "within",
    "supports": "supported by",
    "above": "below",
    "intersects": "intersects",
    "adjacent": "adjacent to",
    "adjacent_exact": "adjacent to (exact)",
    "near": "near",
    "contains_semantic": "within (semantic)",
    "revit_hosted_by": "Revit host for",
    "revit_in_room": "Contains Revit room member",
    "revit_on_level": "Has Revit level member",
}


def _inverse_rel(rel: str) -> str:
    return _INVERSE_RELS.get(rel, rel)


# Forward-direction display labels. Most relationships read fine as their raw name,
# but the symmetric exact-adjacency edge should read the same friendly phrase in
# both directions (it is one canonical edge serving both endpoints).
_FORWARD_RELS = {
    "adjacent_exact": "adjacent to (exact)",
    "contains_semantic": "contains (semantic)",
    "revit_hosted_by": "Hosted by Revit",
    "revit_in_room": "In Revit room",
    "revit_on_level": "On Revit level",
}


def _forward_rel(rel: str) -> str:
    return _FORWARD_RELS.get(rel, rel)


def _edge_detail(edata: dict) -> str:
    """Trailing detail string for an edge line (exact area, distance, direction)."""
    if edata.get("relationship") == "contains_semantic":
        conf = edata.get("confidence", "")
        return f" ({conf})" if conf else ""
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
