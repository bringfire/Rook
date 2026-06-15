"""Sugiyama algorithm for hierarchical graph layout.

Used by gh_canvas_cleanup to organize Grasshopper components
based on their wire dependencies.

The Sugiyama algorithm has 4 phases:
1. Graph building - Convert GH components/connections to nodes/edges
2. Layer assignment - Assign each node to a layer based on dependency depth
3. Crossing minimization - Reorder nodes within layers to reduce wire crossings
4. Coordinate assignment - Calculate final X/Y positions
"""

from dataclasses import dataclass, field
from typing import Any


def _iter_dicts(value: Any):
    """Yield dicts from a dict or a shallow list of dicts."""
    if isinstance(value, dict):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _get_any(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _coord(data: Any, lower_key: str, upper_key: str, default: float) -> float:
    if not isinstance(data, dict):
        return default
    value = _get_any(data, lower_key, upper_key, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Node:
    """A node in the layout graph (represents a GH component)."""

    guid: str
    name: str
    width: float
    height: float
    original_x: float
    original_y: float

    # Assigned during layout
    layer: int = -1
    position_in_layer: int = -1
    x: float = 0.0
    y: float = 0.0


@dataclass
class Edge:
    """A directed edge (represents a GH wire)."""

    source_guid: str
    target_guid: str


class SugiyamaLayout:
    """Sugiyama algorithm implementation for GH canvas layout.

    Usage:
        layout = SugiyamaLayout()
        layout.build_graph(components, connections)
        layout.assign_layers()
        layout.minimize_crossings()
        positions = layout.calculate_positions(
            start_x=50, start_y=50,
            horizontal_gap=30, vertical_gap=20
        )
    """

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._adjacency: dict[str, list[str]] = {}  # guid -> [target_guids]
        self._reverse_adjacency: dict[str, list[str]] = {}  # guid -> [source_guids]

    def build_graph(
        self,
        components: list[dict[str, Any]],
        connections: dict[str, dict[str, Any]],
    ) -> None:
        """Build graph from GH query and connection data.

        Args:
            components: List of component dicts from gh_query
            connections: Dict mapping guid -> connection info from gh_snapshot
        """
        # Build nodes from components
        for comp in components:
            if not isinstance(comp, dict):
                continue
            guid = _get_any(comp, "guid", "Guid")
            if not guid:
                continue
            pos = _get_any(comp, "position", "Position", default={})
            size = _get_any(comp, "size", "Size", default={})

            self.nodes[guid] = Node(
                guid=guid,
                name=_get_any(comp, "name", "Name", default="Unknown"),
                width=_coord(size, "width", "Width", 100),
                height=_coord(size, "height", "Height", 40),
                original_x=_coord(pos, "x", "X", 0),
                original_y=_coord(pos, "y", "Y", 0),
            )
            self._adjacency[guid] = []
            self._reverse_adjacency[guid] = []

        # Build edges from connections
        seen_edges: set[tuple[str, str]] = set()

        for guid, conn_data in connections.items():
            if guid not in self.nodes:
                continue

            # Process outputs -> recipients
            # Handle both formats:
            # - Test format: {"outputs": [{"recipients": [{"recipientComponentGuid": "..."}]}]}
            # - API format: {"outputs": [{"componentGuid": "..."}]}
            for conn_item in _iter_dicts(conn_data):
                outputs = _get_any(conn_item, "outputs", "Outputs", default=[])
                if not isinstance(outputs, list):
                    continue
                for output in outputs:
                    if not isinstance(output, dict):
                        continue
                    # Try API format first (componentGuid directly on output)
                    target_guid = _get_any(
                        output,
                        "componentGuid",
                        "ComponentGuid",
                        "recipientComponentGuid",
                        "RecipientComponentGuid",
                    )
                    if target_guid and target_guid in self.nodes:
                        edge_key = (guid, target_guid)
                        if edge_key not in seen_edges:
                            seen_edges.add(edge_key)
                            self.edges.append(Edge(source_guid=guid, target_guid=target_guid))
                            self._adjacency[guid].append(target_guid)
                            self._reverse_adjacency[target_guid].append(guid)
                    else:
                        # Fall back to nested recipients format.
                        recipients = _get_any(output, "recipients", "Recipients", default=[])
                        if not isinstance(recipients, list):
                            continue
                        for recipient in recipients:
                            if not isinstance(recipient, dict):
                                continue
                            target_guid = _get_any(
                                recipient,
                                "componentGuid",
                                "ComponentGuid",
                                "recipientComponentGuid",
                                "RecipientComponentGuid",
                            )
                            if target_guid and target_guid in self.nodes:
                                edge_key = (guid, target_guid)
                                if edge_key not in seen_edges:
                                    seen_edges.add(edge_key)
                                    self.edges.append(Edge(source_guid=guid, target_guid=target_guid))
                                    self._adjacency[guid].append(target_guid)
                                    self._reverse_adjacency[target_guid].append(guid)

    def assign_layers(self) -> int:
        """Assign nodes to layers using longest path from sources.

        Uses topological sort with longest path calculation.
        Nodes with no inputs start at layer 0.

        Returns:
            Number of layers
        """
        from collections import deque

        # Find nodes with no inputs (sources)
        sources = [guid for guid, preds in self._reverse_adjacency.items() if not preds]

        # Initialize layers
        for node in self.nodes.values():
            node.layer = -1

        # Set sources to layer 0
        for guid in sources:
            self.nodes[guid].layer = 0

        # Process in topological order
        # For each node, layer = max(predecessor layers) + 1
        in_degree = {guid: len(preds) for guid, preds in self._reverse_adjacency.items()}
        queue = deque(sources)

        while queue:
            guid = queue.popleft()
            current_layer = self.nodes[guid].layer

            for target in self._adjacency[guid]:
                # Update target's layer to be at least current + 1
                self.nodes[target].layer = max(
                    self.nodes[target].layer,
                    current_layer + 1
                )

                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)

        # Handle any remaining nodes (disconnected) - set to layer 0
        for node in self.nodes.values():
            if node.layer == -1:
                node.layer = 0

        # Return number of layers
        if not self.nodes:
            return 0
        return max(node.layer for node in self.nodes.values()) + 1

    def assign_layers_coffman_graham(self, max_width: int = 4) -> int:
        """Assign layers using Coffman-Graham algorithm with width constraint.

        Unlike longest-path, this spreads nodes horizontally by limiting
        how many nodes can be in each layer. Better for human readability.

        Algorithm:
        1. Label nodes in reverse topological order
        2. Assign layers bottom-up, placing each node in the first layer
           that has room AND where all successors are in later layers

        Args:
            max_width: Maximum nodes per layer (default: 4)

        Returns:
            Number of layers
        """
        if not self.nodes:
            return 0

        # Step 1: Topological sort (Kahn's algorithm)
        in_degree = {guid: len(preds) for guid, preds in self._reverse_adjacency.items()}
        queue = [guid for guid, deg in in_degree.items() if deg == 0]
        topo_order = []

        while queue:
            # Sort by original_y for stable ordering among equals
            queue.sort(key=lambda g: self.nodes[g].original_y)
            guid = queue.pop(0)
            topo_order.append(guid)

            for succ in self._adjacency[guid]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # Step 2: Assign layers (process in reverse topo order = sinks first)
        # Each node goes in the earliest layer where:
        #   - All successors are in later layers
        #   - Layer has room (< max_width)

        layers: dict[int, list[str]] = {}  # layer_idx -> [guids]
        node_layer: dict[str, int] = {}

        for guid in reversed(topo_order):
            successors = self._adjacency[guid]

            if not successors:
                # Sink node - find first layer with room, starting from 0
                target_layer = 0
                while target_layer in layers and len(layers[target_layer]) >= max_width:
                    target_layer += 1
            else:
                # Must be before all successors
                min_succ_layer = min(node_layer[s] for s in successors)
                # Try layers before min_succ_layer, starting from closest
                target_layer = min_succ_layer - 1
                while target_layer >= 0 and target_layer in layers and len(layers[target_layer]) >= max_width:
                    target_layer -= 1

                if target_layer < 0:
                    # No room before successors - need to shift everything
                    # Insert new layer at position 0 and shift all existing layers
                    for g, l in node_layer.items():
                        node_layer[g] = l + 1
                        self.nodes[g].layer = l + 1
                    new_layers = {l + 1: guids for l, guids in layers.items()}
                    layers = new_layers
                    target_layer = 0

            # Assign to target layer
            if target_layer not in layers:
                layers[target_layer] = []
            layers[target_layer].append(guid)
            node_layer[guid] = target_layer
            self.nodes[guid].layer = target_layer

        # Normalize layers to start from 0
        if layers:
            min_layer = min(layers.keys())
            if min_layer != 0:
                for guid in self.nodes:
                    self.nodes[guid].layer -= min_layer

        return max(self.nodes[g].layer for g in self.nodes) + 1 if self.nodes else 0

    def _get_layers(self) -> dict[int, list[str]]:
        """Group nodes by layer."""
        layers: dict[int, list[str]] = {}
        for guid, node in self.nodes.items():
            if node.layer not in layers:
                layers[node.layer] = []
            layers[node.layer].append(guid)
        return layers

    def _barycenter(self, guid: str, fixed_layer_positions: dict[str, int]) -> float:
        """Calculate barycenter (average position) of connected nodes in adjacent layer."""
        predecessors = self._reverse_adjacency.get(guid, [])
        successors = self._adjacency.get(guid, [])

        connected = [g for g in predecessors + successors if g in fixed_layer_positions]

        if not connected:
            # No connections - use original Y position as tiebreaker
            return self.nodes[guid].original_y

        return sum(fixed_layer_positions[g] for g in connected) / len(connected)

    def minimize_crossings(self, iterations: int = 4) -> None:
        """Minimize edge crossings using barycenter heuristic.

        Sweeps alternately down and up through layers, reordering nodes
        by the average position of their neighbors in the adjacent fixed layer.

        Args:
            iterations: Number of down-up sweep pairs
        """
        layers = self._get_layers()
        if not layers:
            return

        num_layers = max(layers.keys()) + 1

        # Initial ordering: by original Y position
        for layer_idx, guids in layers.items():
            guids.sort(key=lambda g: self.nodes[g].original_y)
            for pos, guid in enumerate(guids):
                self.nodes[guid].position_in_layer = pos

        for _ in range(iterations):
            # Sweep down (layer 0 is fixed, reorder 1, 2, ...)
            for layer_idx in range(1, num_layers):
                if layer_idx not in layers:
                    continue

                # Fixed layer positions from layer above
                fixed_positions = {
                    guid: self.nodes[guid].position_in_layer
                    for guid in layers.get(layer_idx - 1, [])
                }

                # Sort current layer by barycenter
                layer_guids = layers[layer_idx]
                layer_guids.sort(key=lambda g: self._barycenter(g, fixed_positions))

                for pos, guid in enumerate(layer_guids):
                    self.nodes[guid].position_in_layer = pos

            # Sweep up (last layer is fixed, reorder ..., 1, 0)
            for layer_idx in range(num_layers - 2, -1, -1):
                if layer_idx not in layers:
                    continue

                # Fixed layer positions from layer below
                fixed_positions = {
                    guid: self.nodes[guid].position_in_layer
                    for guid in layers.get(layer_idx + 1, [])
                }

                # Sort current layer by barycenter
                layer_guids = layers[layer_idx]
                layer_guids.sort(key=lambda g: self._barycenter(g, fixed_positions))

                for pos, guid in enumerate(layer_guids):
                    self.nodes[guid].position_in_layer = pos

    def calculate_positions(
        self,
        start_x: float = 50,
        start_y: float = 50,
        horizontal_gap: float = 30,
        vertical_gap: float = 20,
    ) -> dict[str, dict[str, float]]:
        """Calculate final X/Y positions for all nodes.

        Args:
            start_x: Left edge X coordinate
            start_y: Top edge Y coordinate
            horizontal_gap: Gap between layers (columns)
            vertical_gap: Gap between nodes in same layer (rows)

        Returns:
            Dict mapping guid -> {guid, x, y}
        """
        layers = self._get_layers()
        if not layers:
            return {}

        num_layers = max(layers.keys()) + 1

        # Calculate layer X positions based on max width in each layer
        layer_x: dict[int, float] = {}
        current_x = start_x

        for layer_idx in range(num_layers):
            layer_x[layer_idx] = current_x

            # Find max width in this layer
            layer_guids = layers.get(layer_idx, [])
            if layer_guids:
                max_width = max(self.nodes[g].width for g in layer_guids)
                current_x += max_width + horizontal_gap

        # Calculate Y positions within each layer
        positions: dict[str, dict[str, float]] = {}

        for layer_idx in range(num_layers):
            layer_guids = layers.get(layer_idx, [])

            # Sort by position_in_layer
            layer_guids.sort(key=lambda g: self.nodes[g].position_in_layer)

            current_y = start_y
            for guid in layer_guids:
                node = self.nodes[guid]
                node.x = layer_x[layer_idx]
                node.y = current_y

                positions[guid] = {
                    "guid": guid,
                    "x": node.x,
                    "y": node.y,
                }

                current_y += node.height + vertical_gap

        return positions
