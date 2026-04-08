"""Enhanced canvas layout engine for Grasshopper.

10-phase pipeline adapted from Engram's 19-phase Blueprint formatter.
Imports and reuses core algorithms from sugiyama.py.

Phases:
    1. Build graph from GH query + connections
    2. Detect GH_Groups, build containment tree
    3. Cycle detection (DFS, mark back-edges)
    4. Layer assignment (Coffman-Graham)
    5. Crossing minimization (barycenter)
    6. FormatY with collision detection (ported from Engram)
    7. Center branches (ported from Engram)
    8. Expand by height (ported from Engram)
    9. Group padding
   10. Finalize (anchor reset + optional grid snap)
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .sugiyama import Edge, Node, SugiyamaLayout


@dataclass
class LayoutSettings:
    """Configuration for the layout pipeline.

    Adapted from Engram's FEngramFormatterSettings.
    All defaults preserve backward-compatible behavior with the old Sugiyama layout.
    """

    # Spacing
    horizontal_gap: float = 30.0
    vertical_gap: float = 20.0

    # Style: "expanded" leaves room for readability, "compact" packs tightly
    style: str = "expanded"

    # Collision detection (Phase 6)
    collision_detection: bool = True
    collision_iterations: int = 30  # Max passes per node (Engram default)
    collision_padding: float = 5.0  # Extra clearance beyond vertical_gap

    # Expand by height (Phase 8) — keeps wire angles readable (~45 deg)
    expand_by_height: bool = True
    expand_max_dist: float = 200.0  # Max horizontal expansion (Engram default)
    wire_angle_factor: float = 0.75  # Engram's deltaY * factor - deltaX formula

    # Branch centering (Phase 7)
    center_branches: bool = True
    min_branches_for_centering: int = 3  # Engram default

    # Group awareness (Phases 2, 9)
    group_padding: float = 30.0
    keep_groups_together: bool = True

    # Grid snap (Phase 10)
    snap_to_grid: bool = False
    grid_size: float = 8.0

    # Anchor: keep one component at its current position
    anchor_guid: str | None = None


@dataclass
class GroupInfo:
    """Represents a GH_Group on the canvas."""

    guid: str
    nickname: str
    member_guids: list[str] = field(default_factory=list)
    colour: str = ""
    bounds: dict[str, float] | None = None  # {x, y, width, height}
    children_groups: list[str] = field(default_factory=list)  # Nested group GUIDs


class CanvasLayout:
    """Enhanced layout engine for Grasshopper canvas.

    10-phase pipeline adapted from Engram's FEngramBlueprintFormatter.
    Core Sugiyama algorithms (layer assignment, crossing minimization)
    are delegated to the existing SugiyamaLayout class.

    Usage:
        engine = CanvasLayout(LayoutSettings(expand_by_height=True))
        positions = engine.run(components, connections, groups)
    """

    def __init__(self, settings: LayoutSettings | None = None):
        self.settings = settings or LayoutSettings()
        self._sugiyama = SugiyamaLayout()

        # Graph data (populated during build_graph)
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.groups: dict[str, GroupInfo] = {}
        self._adjacency: dict[str, list[str]] = {}
        self._reverse_adjacency: dict[str, list[str]] = {}
        self._back_edges: set[tuple[str, str]] = set()
        self._num_layers: int = 0

    @property
    def num_layers(self) -> int:
        """Number of layers after layout assignment."""
        return self._num_layers

    # ------------------------------------------------------------------
    # Phase 1: Build graph
    # ------------------------------------------------------------------

    def build_graph(
        self,
        components: list[dict[str, Any]],
        connections: dict[str, dict[str, Any]],
        groups: list[dict[str, Any]] | None = None,
    ) -> None:
        """Build the layout graph from GH canvas data.

        Delegates to SugiyamaLayout.build_graph() for node/edge construction,
        then copies references for local use.
        """
        self._sugiyama.build_graph(components, connections)

        # Share references with the Sugiyama engine
        self.nodes = self._sugiyama.nodes
        self.edges = self._sugiyama.edges
        self._adjacency = self._sugiyama._adjacency
        self._reverse_adjacency = self._sugiyama._reverse_adjacency

        # Parse groups if provided
        if groups:
            self._parse_groups(groups)

    def _parse_groups(self, groups: list[dict[str, Any]]) -> None:
        """Parse group data from gh/groups endpoint.

        Handles both PascalCase (from C# endpoint) and lowercase keys.
        """
        for g in groups:
            # C# serializes with camelCase: Guid→guid, NickName→nickName, etc.
            guid = g.get("guid") or g.get("Guid", "")
            if not guid:
                continue
            members = g.get("members") or g.get("Members", [])
            self.groups[guid] = GroupInfo(
                guid=guid,
                nickname=g.get("nickName") or g.get("NickName") or g.get("nickname", ""),
                member_guids=[m for m in members if m in self.nodes],
                colour=g.get("colour") or g.get("Colour", ""),
                bounds=g.get("bounds") or g.get("Bounds"),
            )

    # ------------------------------------------------------------------
    # Phase 2: Detect group containment tree
    # ------------------------------------------------------------------

    def detect_group_containment(self) -> None:
        """Build parent-child relationships between nested groups."""
        group_list = list(self.groups.values())
        for i, parent in enumerate(group_list):
            parent_members = set(parent.member_guids)
            for j, child in enumerate(group_list):
                if i == j:
                    continue
                child_members = set(child.member_guids)
                # Child is nested inside parent if all its members are in parent
                if child_members and child_members.issubset(parent_members):
                    parent.children_groups.append(child.guid)

    # ------------------------------------------------------------------
    # Phase 3: Cycle detection
    # ------------------------------------------------------------------

    def mark_cycles(self) -> None:
        """Detect cycles using DFS, mark back-edges.

        Back-edges are excluded from layer assignment to prevent
        infinite loops in topological sort.
        """
        self._back_edges.clear()
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(guid: str) -> None:
            visited.add(guid)
            in_stack.add(guid)
            for succ in self._adjacency.get(guid, []):
                if succ in in_stack:
                    self._back_edges.add((guid, succ))
                elif succ not in visited:
                    dfs(succ)
            in_stack.discard(guid)

        for guid in self.nodes:
            if guid not in visited:
                dfs(guid)

    # ------------------------------------------------------------------
    # Phase 4: Layer assignment
    # ------------------------------------------------------------------

    def assign_layers(self, max_width: int = 4) -> int:
        """Assign layers using Coffman-Graham algorithm.

        Temporarily removes back-edges to ensure acyclic graph
        for topological sort.
        """
        # Temporarily remove back-edges from adjacency
        removed: list[tuple[str, str]] = []
        for src, tgt in self._back_edges:
            if tgt in self._adjacency.get(src, []):
                self._adjacency[src].remove(tgt)
                self._reverse_adjacency[tgt].remove(src)
                removed.append((src, tgt))

        self._num_layers = self._sugiyama.assign_layers_coffman_graham(
            max_width=max_width
        )

        # Restore back-edges
        for src, tgt in removed:
            self._adjacency[src].append(tgt)
            self._reverse_adjacency[tgt].append(src)

        return self._num_layers

    # ------------------------------------------------------------------
    # Phase 5: Crossing minimization
    # ------------------------------------------------------------------

    def minimize_crossings(self, iterations: int = 4) -> None:
        """Minimize edge crossings using barycenter heuristic."""
        self._sugiyama.minimize_crossings(iterations=iterations)

    # ------------------------------------------------------------------
    # Phase 6: FormatY with collision detection (CORE PORT from Engram)
    # ------------------------------------------------------------------

    def format_y_with_collision(self, start_x: float, start_y: float) -> None:
        """Position nodes with collision detection.

        Port of Engram's FormatY_Recursive. For each node (processed
        layer by layer, then by position_in_layer), try to place it
        near its connected parents' Y positions. Then iterate to
        resolve any bounding-box overlaps.

        This replaces the simple sequential stacking in SugiyamaLayout.
        """
        layers = self._sugiyama._get_layers()
        if not layers:
            return

        num_layers = max(layers.keys()) + 1

        # First: assign X positions per layer (same as Sugiyama)
        layer_x: dict[int, float] = {}
        current_x = start_x
        for layer_idx in range(num_layers):
            layer_x[layer_idx] = current_x
            layer_guids = layers.get(layer_idx, [])
            if layer_guids:
                max_width = max(self.nodes[g].width for g in layer_guids)
                gap = self.settings.horizontal_gap
                if self.settings.style == "compact":
                    gap *= 0.6
                current_x += max_width + gap

        # Assign X to all nodes
        for layer_idx in range(num_layers):
            for guid in layers.get(layer_idx, []):
                self.nodes[guid].x = layer_x[layer_idx]

        # Now: assign Y positions with collision detection
        placed_nodes: list[str] = []

        for layer_idx in range(num_layers):
            layer_guids = layers.get(layer_idx, [])
            layer_guids.sort(key=lambda g: self.nodes[g].position_in_layer)

            for guid in layer_guids:
                node = self.nodes[guid]

                # Initial Y: try to align with connected parents' average Y
                parent_guids = self._reverse_adjacency.get(guid, [])
                parent_ys = [
                    self.nodes[pg].y
                    for pg in parent_guids
                    if pg in self.nodes and self.nodes[pg].layer < node.layer
                ]

                if parent_ys:
                    node.y = sum(parent_ys) / len(parent_ys)
                else:
                    # Source node or disconnected: use sequential position
                    same_layer_placed = [
                        g for g in placed_nodes if self.nodes[g].layer == node.layer
                    ]
                    if same_layer_placed:
                        last = self.nodes[same_layer_placed[-1]]
                        node.y = last.y + last.height + self.settings.vertical_gap
                    else:
                        node.y = start_y

                # Collision resolution loop (Engram: up to 30 iterations)
                if self.settings.collision_detection:
                    total_gap = self.settings.vertical_gap + self.settings.collision_padding
                    for _ in range(self.settings.collision_iterations):
                        collision = False
                        for placed_guid in placed_nodes:
                            placed = self.nodes[placed_guid]
                            if self._rects_overlap(node, placed, total_gap):
                                push = (placed.y + placed.height + total_gap) - node.y
                                if push > 0:
                                    node.y += push
                                    collision = True
                        if not collision:
                            break

                placed_nodes.append(guid)

    @staticmethod
    def _rects_overlap(a: Node, b: Node, gap: float = 0) -> bool:
        """Check if two node bounding boxes overlap (with optional gap).

        Gap is the minimum clearance required between the two nodes.
        Applied symmetrically so argument order doesn't matter.
        """
        # Must overlap in both X and Y to be a collision
        # X overlap: nodes in the same layer column
        a_right = a.x + a.width
        b_right = b.x + b.width
        x_overlap = a.x < b_right and b.x < a_right

        # Y overlap: nodes are closer than gap
        a_bottom = a.y + a.height
        b_bottom = b.y + b.height
        y_overlap = a.y < b_bottom + gap and b.y < a_bottom + gap

        return x_overlap and y_overlap

    # ------------------------------------------------------------------
    # Phase 7: Center branches (PORT from Engram)
    # ------------------------------------------------------------------

    def center_branches(self) -> None:
        """Center fan-out children vertically around their parent.

        Port of Engram's branch centering logic. When a node has
        min_branches_for_centering or more children in the next layer,
        shift them so they're centered around the parent's vertical midpoint.
        """
        if not self.settings.center_branches:
            return

        min_branches = self.settings.min_branches_for_centering

        for guid, node in self.nodes.items():
            children = self._adjacency.get(guid, [])
            # Only center children in the immediately next layer
            next_layer_children = [
                cg
                for cg in children
                if cg in self.nodes and self.nodes[cg].layer == node.layer + 1
            ]

            if len(next_layer_children) < min_branches:
                continue

            # Calculate current children span
            child_nodes = [self.nodes[cg] for cg in next_layer_children]
            children_top = min(c.y for c in child_nodes)
            children_bottom = max(c.y + c.height for c in child_nodes)
            children_center = (children_top + children_bottom) / 2

            # Parent midpoint
            parent_center = node.y + node.height / 2

            # Shift all children
            delta = parent_center - children_center
            if abs(delta) > 1:  # Only shift if meaningful
                for child in child_nodes:
                    child.y += delta

                # Re-check collisions after centering
                if self.settings.collision_detection:
                    self._resolve_layer_collisions(node.layer + 1)

    def _resolve_layer_collisions(self, layer_idx: int) -> None:
        """Resolve any collisions within a single layer after repositioning."""
        layers = self._sugiyama._get_layers()
        layer_guids = layers.get(layer_idx, [])
        if not layer_guids:
            return

        layer_guids.sort(key=lambda g: self.nodes[g].y)
        total_gap = self.settings.vertical_gap + self.settings.collision_padding

        for i in range(1, len(layer_guids)):
            prev = self.nodes[layer_guids[i - 1]]
            curr = self.nodes[layer_guids[i]]
            min_y = prev.y + prev.height + total_gap
            if curr.y < min_y:
                curr.y = min_y

    # ------------------------------------------------------------------
    # Phase 8: Expand by height (PORT from Engram)
    # ------------------------------------------------------------------

    def expand_by_height(self) -> None:
        """Add horizontal spacing when wires would be too steep.

        Port of Engram's ExpandByHeight (EngramBlueprintFormatter.cpp:716-771).
        For each node with multiple children, if the vertical distance
        between them would make wires steeper than ~45 degrees, push
        the children's entire subtree further right.

        Formula: expand_x = deltaY * wire_angle_factor - deltaX
        Clamped to expand_max_dist.
        """
        if not self.settings.expand_by_height:
            return

        # Process layers from left to right
        layers = self._sugiyama._get_layers()
        if not layers:
            return

        # Track nodes already expanded to prevent cascading double-shifts
        # when multiple parents share downstream children
        already_expanded: set[str] = set()

        for layer_idx in sorted(layers.keys()):
            for guid in layers[layer_idx]:
                node = self.nodes[guid]
                children = self._adjacency.get(guid, [])
                if len(children) < 2:
                    continue

                largest_expand = 0.0
                for child_guid in children:
                    if child_guid not in self.nodes:
                        continue
                    child = self.nodes[child_guid]
                    delta_y = abs(child.y - node.y)
                    delta_x = abs(child.x - node.x)
                    expand_x = delta_y * self.settings.wire_angle_factor - delta_x
                    largest_expand = max(expand_x, largest_expand)

                if largest_expand <= 0:
                    continue

                largest_expand = min(largest_expand, self.settings.expand_max_dist)

                # Shift all downstream nodes (children and their subtrees) right,
                # but skip nodes already expanded by a prior parent
                downstream = self._get_downstream_nodes(guid)
                new_nodes = downstream - already_expanded
                for ds_guid in new_nodes:
                    self.nodes[ds_guid].x += largest_expand
                already_expanded.update(new_nodes)

    def _get_downstream_nodes(self, root_guid: str) -> set[str]:
        """Get all nodes reachable downstream from root (BFS, excludes root)."""
        visited: set[str] = set()
        queue = deque(self._adjacency.get(root_guid, []))
        while queue:
            guid = queue.popleft()
            if guid in visited or guid == root_guid:
                continue
            if (root_guid, guid) in self._back_edges:
                continue  # Don't follow cycles
            visited.add(guid)
            for succ in self._adjacency.get(guid, []):
                if succ not in visited:
                    queue.append(succ)
        return visited

    # ------------------------------------------------------------------
    # Phase 9: Group padding
    # ------------------------------------------------------------------

    def apply_group_padding(self) -> dict[str, dict[str, float]]:
        """Calculate expanded bounds for each group after layout.

        Returns a dict of group_guid -> {x, y, width, height} that can
        be used to resize groups via the gh/group-resize endpoint.
        """
        group_bounds: dict[str, dict[str, float]] = {}
        padding = self.settings.group_padding

        for group in self.groups.values():
            member_nodes = [
                self.nodes[mg] for mg in group.member_guids if mg in self.nodes
            ]
            if not member_nodes:
                continue

            min_x = min(n.x for n in member_nodes) - padding
            min_y = min(n.y for n in member_nodes) - padding
            max_x = max(n.x + n.width for n in member_nodes) + padding
            max_y = max(n.y + n.height for n in member_nodes) + padding

            group_bounds[group.guid] = {
                "x": min_x,
                "y": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            }

        return group_bounds

    # ------------------------------------------------------------------
    # Phase 10: Finalize (anchor reset + grid snap)
    # ------------------------------------------------------------------

    def finalize(self, start_x: float, start_y: float) -> None:
        """Reset positions relative to anchor and optionally snap to grid."""
        if not self.nodes:
            return

        # Anchor reset: shift everything so the anchor (or top-left) is at start
        if self.settings.anchor_guid and self.settings.anchor_guid in self.nodes:
            anchor = self.nodes[self.settings.anchor_guid]
            offset_x = anchor.original_x - anchor.x
            offset_y = anchor.original_y - anchor.y
        else:
            min_x = min(n.x for n in self.nodes.values())
            min_y = min(n.y for n in self.nodes.values())
            offset_x = start_x - min_x
            offset_y = start_y - min_y

        for node in self.nodes.values():
            node.x += offset_x
            node.y += offset_y

        # Grid snap
        if self.settings.snap_to_grid and self.settings.grid_size > 0:
            gs = self.settings.grid_size
            for node in self.nodes.values():
                node.x = math.floor(node.x / gs) * gs
                node.y = math.floor(node.y / gs) * gs

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        components: list[dict[str, Any]],
        connections: dict[str, dict[str, Any]],
        groups: list[dict[str, Any]] | None = None,
        start_x: float = 50,
        start_y: float = 50,
        max_layer_width: int = 4,
    ) -> dict[str, dict[str, float]]:
        """Run the complete 10-phase layout pipeline.

        Args:
            components: Component list from gh/query
            connections: Connection data keyed by guid from gh/connections
            groups: Group list from gh/groups (optional)
            start_x: Top-left X coordinate
            start_y: Top-left Y coordinate
            max_layer_width: Max components per layer

        Returns:
            Dict mapping guid -> {"guid": str, "x": float, "y": float}
        """
        if not components:
            return {}

        # Phase 1: Build graph
        self.build_graph(components, connections, groups)

        if not self.nodes:
            return {}

        # Phase 2: Detect group containment
        if self.groups:
            self.detect_group_containment()

        # Phase 3: Cycle detection
        self.mark_cycles()

        # Phase 4: Layer assignment
        self.assign_layers(max_width=max_layer_width)

        # Phase 5: Crossing minimization
        self.minimize_crossings()

        # Phase 6: FormatY with collision detection
        self.format_y_with_collision(start_x, start_y)

        # Phase 7: Center branches
        self.center_branches()

        # Phase 8: Expand by height
        self.expand_by_height()

        # Phase 9: Group padding (calculated but not applied here)
        # Group bounds are returned separately for the caller to apply

        # Phase 10: Finalize
        self.finalize(start_x, start_y)

        # Build output positions
        return {
            guid: {"guid": guid, "x": node.x, "y": node.y}
            for guid, node in self.nodes.items()
        }

    def get_group_bounds(self) -> dict[str, dict[str, float]]:
        """Get calculated group bounds after run(). Call after run()."""
        return self.apply_group_padding()
