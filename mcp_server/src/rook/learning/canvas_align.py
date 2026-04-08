"""Canvas alignment utilities for surgical component positioning.

Three tools for fine-grained control over component layout:
- align_components: Align selection to a common edge/center
- distribute_components: Space components evenly
- straighten_wires: Align connected components for clean wires
"""

from __future__ import annotations

from typing import Any


def align_positions(
    components: list[dict[str, Any]],
    direction: str,
    anchor: str = "median",
) -> list[dict[str, float]]:
    """Calculate aligned positions for components.

    Args:
        components: List of {guid, position: {x, y}, size: {width, height}}
        direction: "top", "bottom", "left", "right", "center_h", "center_v"
        anchor: "first", "last", "median", "min", "max"

    Returns:
        List of {guid, x, y} with new positions
    """
    if not components or len(components) < 2:
        return []

    def get_pos(c: dict) -> tuple[float, float]:
        pos = c.get("position") or {"x": 0, "y": 0}
        return float(pos.get("x", 0)), float(pos.get("y", 0))

    def get_size(c: dict) -> tuple[float, float]:
        size = c.get("size") or {"width": 100, "height": 40}
        return float(size.get("width", 100)), float(size.get("height", 40))

    # Calculate the anchor value based on direction and anchor mode
    if direction in ("top", "bottom", "center_v"):
        values = []
        for c in components:
            x, y = get_pos(c)
            w, h = get_size(c)
            if direction == "top":
                values.append(y)
            elif direction == "bottom":
                values.append(y + h)
            else:  # center_v
                values.append(y + h / 2)

        target = _pick_anchor(values, anchor)

        results = []
        for c in components:
            x, y = get_pos(c)
            w, h = get_size(c)
            if direction == "top":
                new_y = target
            elif direction == "bottom":
                new_y = target - h
            else:  # center_v
                new_y = target - h / 2
            results.append({"guid": c["guid"], "x": x, "y": new_y})
        return results

    elif direction in ("left", "right", "center_h"):
        values = []
        for c in components:
            x, y = get_pos(c)
            w, h = get_size(c)
            if direction == "left":
                values.append(x)
            elif direction == "right":
                values.append(x + w)
            else:  # center_h
                values.append(x + w / 2)

        target = _pick_anchor(values, anchor)

        results = []
        for c in components:
            x, y = get_pos(c)
            w, h = get_size(c)
            if direction == "left":
                new_x = target
            elif direction == "right":
                new_x = target - w
            else:  # center_h
                new_x = target - w / 2
            results.append({"guid": c["guid"], "x": new_x, "y": y})
        return results

    return []


def distribute_positions(
    components: list[dict[str, Any]],
    axis: str,
    spacing: float | None = None,
) -> list[dict[str, float]]:
    """Calculate evenly distributed positions for components.

    Args:
        components: List of {guid, position: {x, y}, size: {width, height}}
        axis: "horizontal" or "vertical"
        spacing: Fixed spacing between components (None = equal distribution)

    Returns:
        List of {guid, x, y} with new positions
    """
    if not components or len(components) < 2:
        return []

    def get_pos(c: dict) -> tuple[float, float]:
        pos = c.get("position") or {"x": 0, "y": 0}
        return float(pos.get("x", 0)), float(pos.get("y", 0))

    def get_size(c: dict) -> tuple[float, float]:
        size = c.get("size") or {"width": 100, "height": 40}
        return float(size.get("width", 100)), float(size.get("height", 40))

    if axis == "horizontal":
        # Sort by X position
        sorted_comps = sorted(components, key=lambda c: get_pos(c)[0])

        if spacing is not None:
            # Fixed spacing: place each component after the previous
            results = []
            current_x = get_pos(sorted_comps[0])[0]
            for c in sorted_comps:
                x, y = get_pos(c)
                w, h = get_size(c)
                results.append({"guid": c["guid"], "x": current_x, "y": y})
                current_x += w + spacing
            return results
        else:
            # Equal distribution: spread between first and last positions
            first_x = get_pos(sorted_comps[0])[0]
            last_x = get_pos(sorted_comps[-1])[0]
            total_span = last_x - first_x

            if total_span <= 0 or len(sorted_comps) < 2:
                return []

            step = total_span / (len(sorted_comps) - 1)
            results = []
            for i, c in enumerate(sorted_comps):
                x, y = get_pos(c)
                results.append({"guid": c["guid"], "x": first_x + i * step, "y": y})
            return results

    elif axis == "vertical":
        # Sort by Y position
        sorted_comps = sorted(components, key=lambda c: get_pos(c)[1])

        if spacing is not None:
            results = []
            current_y = get_pos(sorted_comps[0])[1]
            for c in sorted_comps:
                x, y = get_pos(c)
                w, h = get_size(c)
                results.append({"guid": c["guid"], "x": x, "y": current_y})
                current_y += h + spacing
            return results
        else:
            first_y = get_pos(sorted_comps[0])[1]
            last_y = get_pos(sorted_comps[-1])[1]
            total_span = last_y - first_y

            if total_span <= 0 or len(sorted_comps) < 2:
                return []

            step = total_span / (len(sorted_comps) - 1)
            results = []
            for i, c in enumerate(sorted_comps):
                x, y = get_pos(c)
                results.append({"guid": c["guid"], "x": x, "y": first_y + i * step})
            return results

    return []


def straighten_wire_positions(
    components: list[dict[str, Any]],
    connections: dict[str, dict[str, Any]],
    target_guids: list[str] | None = None,
) -> list[dict[str, float]]:
    """Calculate positions that straighten wires between connected components.

    For each pair of directly connected components, adjusts the downstream
    component's Y to align with the upstream component's output center.

    Args:
        components: List of {guid, position: {x, y}, size: {width, height}}
        connections: Connection data keyed by guid
        target_guids: Specific GUIDs to straighten (None = all)

    Returns:
        List of {guid, x, y} with adjusted positions
    """
    if not components or not connections:
        return []

    comp_map = {c["guid"]: c for c in components if "guid" in c}

    def get_pos(c: dict) -> tuple[float, float]:
        pos = c.get("position") or {"x": 0, "y": 0}
        return float(pos.get("x", 0)), float(pos.get("y", 0))

    def get_size(c: dict) -> tuple[float, float]:
        size = c.get("size") or {"width": 100, "height": 40}
        return float(size.get("width", 100)), float(size.get("height", 40))

    # Build a map of each component's single upstream parent
    # (for straightening, we align to the primary input source)
    adjustments: dict[str, tuple[float, float]] = {}

    guids_to_process = target_guids if target_guids else list(comp_map.keys())

    for guid in guids_to_process:
        if guid not in comp_map or guid not in connections:
            continue

        conn = connections[guid]
        comp = comp_map[guid]
        cx, cy = get_pos(comp)
        cw, ch = get_size(comp)

        # Find upstream sources
        # API format: componentGuid; test format: sourceComponentGuid
        sources: list[str] = []
        for inp in conn.get("inputs", []):
            for src in inp.get("sources", []):
                src_guid = src.get("componentGuid") or src.get("sourceComponentGuid")
                if src_guid and src_guid in comp_map:
                    sources.append(src_guid)

        if not sources:
            continue

        # If single source, align Y to source center
        # If multiple sources, align to average
        source_centers = []
        for sg in sources:
            sc = comp_map[sg]
            sx, sy = get_pos(sc)
            sw, sh = get_size(sc)
            source_centers.append(sy + sh / 2)

        target_center_y = sum(source_centers) / len(source_centers)
        new_y = target_center_y - ch / 2

        adjustments[guid] = (cx, new_y)

    return [
        {"guid": guid, "x": x, "y": y} for guid, (x, y) in adjustments.items()
    ]


def _pick_anchor(values: list[float], anchor: str) -> float:
    """Pick the anchor value from a list based on mode."""
    if not values:
        return 0.0

    if anchor == "first":
        return values[0]
    elif anchor == "last":
        return values[-1]
    elif anchor == "min":
        return min(values)
    elif anchor == "max":
        return max(values)
    else:  # "median" (default)
        sorted_vals = sorted(values)
        mid = len(sorted_vals) // 2
        if len(sorted_vals) % 2 == 0:
            return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
        return sorted_vals[mid]
