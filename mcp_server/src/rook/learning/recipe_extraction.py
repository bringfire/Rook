"""
Recipe Extraction - Extract workflow recipes from GH canvas.

Provides:
- DraftRecipe: A recipe draft awaiting human approval
- extract_recipe: Analyze canvas and produce DraftRecipe (dispatches v1 or v2)
- extract_recipe_v1: Legacy extraction from canvas_state + connections_data
- extract_recipe_v2: Snapshot-based extraction producing v2 graph format

Part of the Recipe Learning System (complementary to A-MEM).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .recipe_classification import classify_recipe

logger = logging.getLogger("rook.recipe_extraction")


@dataclass
class DraftRecipe:
    """A recipe draft extracted from canvas, awaiting human approval.

    Similar to DraftPattern in reflection.py but for successful workflows
    rather than struggle sequences.
    """

    draft_id: str
    """Unique ID for this draft."""

    components: list[dict]
    """Components in the recipe: [{"guid": str, "name": str, "type": str}, ...]"""

    wiring: list[dict]
    """Connections: [{"from": guid, "from_param": str, "to": guid, "to_param": str}, ...]"""

    input_structure: dict
    """Input configuration: {"sliders": [...], "panels": [...]} with semantic roles."""

    output_type: str
    """What the recipe produces: "curve", "surface", "brep", "points", etc."""

    # Classification (from DSPy or heuristics)
    suggested_name: str = ""
    """DSPy-suggested name for the recipe."""

    detected_tags: list[str] = field(default_factory=list)
    """Pattern type tags detected from components."""

    suggested_intents: list[str] = field(default_factory=list)
    """Phrases that should match this recipe."""

    description: str = ""
    """One-sentence description of what the recipe creates."""

    # Metadata
    source_definition: str = ""
    """Original .ghx filename if extracted from a file."""

    created: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    """ISO timestamp when draft was created."""

    # v2 fields
    graph: Optional[dict] = None
    """v2 graph format: {"components": [...], "flows": [...], "subgraphs": []}"""

    schema_version: str = "1.0"
    """Schema version: "1.0" for legacy v1 drafts, "2.0" for snapshot-based v2."""

    @classmethod
    def create(
        cls,
        components: list[dict],
        wiring: list[dict],
        input_structure: dict,
        output_type: str,
        source_definition: str = "",
    ) -> "DraftRecipe":
        """Create a new draft recipe with generated ID."""
        return cls(
            draft_id=f"draft_{uuid4().hex[:8]}",
            components=components,
            wiring=wiring,
            input_structure=input_structure,
            output_type=output_type,
            source_definition=source_definition,
        )

    def to_dict(self) -> dict:
        """Convert to dict for MCP response."""
        result = {
            "draft_id": self.draft_id,
            "schema_version": self.schema_version,
            "component_count": len(self.components),
            "connection_count": len(self.graph.get("flows", [])) if self.graph else len(self.wiring),
            "components": self.components,
            "wiring": self.wiring,
            "input_structure": self.input_structure,
            "output_type": self.output_type,
            "suggested_name": self.suggested_name,
            "detected_tags": self.detected_tags,
            "suggested_intents": self.suggested_intents,
            "description": self.description,
            "source_definition": self.source_definition,
            "created": self.created,
        }
        if self.graph is not None:
            result["graph"] = self.graph
        return result


# =============================================================================
# Canvas Analysis Functions (used by v1)
# =============================================================================

# Input component types
INPUT_TYPES = {"GH_NumberSlider", "GH_Panel", "GH_BooleanToggle", "Param_GenericObject"}

# Output type mapping based on component type
OUTPUT_TYPE_MAP = {
    "Component_PipeSurface": "brep",
    "Component_Pipe": "brep",
    "Component_Loft": "brep",
    "Component_Extrusion": "brep",
    "Component_BrepJoin": "brep",
    "Component_Cap": "brep",
    "Component_InterpCurve": "curve",
    "Component_PolyLine": "curve",
    "Component_Circle": "curve",
    "Component_Arc": "curve",
    "Component_Line": "curve",
    "Component_ConstructPoint": "points",
    "Component_Sphere": "surface",
    "Component_Box": "brep",
    "GH_CustomPreviewComponent": "display",
}

# Also map snapshot-style type names (GH_ prefix stripped) for v2
_SNAPSHOT_OUTPUT_TYPE_MAP = {
    "PipeSurface": "brep",
    "Pipe": "brep",
    "Loft": "brep",
    "Extrusion": "brep",
    "BrepJoin": "brep",
    "Cap": "brep",
    "InterpCurve": "curve",
    "PolyLine": "curve",
    "Circle": "curve",
    "Arc": "curve",
    "Line": "curve",
    "ConstructPoint": "points",
    "Sphere": "surface",
    "Box": "brep",
    "CustomPreviewComponent": "display",
}
# Merge the Component_ prefixed names too
for _k, _v in list(OUTPUT_TYPE_MAP.items()):
    _SNAPSHOT_OUTPUT_TYPE_MAP[_k] = _v


def identify_inputs(components: list[dict]) -> list[dict]:
    """Identify input components (sliders, panels, toggles).

    Args:
        components: List of component dicts with 'type' field

    Returns:
        List of components that are input types
    """
    return [c for c in components if c.get("type") in INPUT_TYPES]


def identify_outputs(
    components: list[dict],
    connections: list[dict],
) -> list[dict]:
    """Identify output/terminal components.

    A component is an output if:
    - It has no outgoing connections, OR
    - It's a preview/display component

    Args:
        components: List of component dicts
        connections: List of connection dicts with 'from' field

    Returns:
        List of output components
    """
    # GUIDs that have outgoing connections
    sources = {c["from"] for c in connections}

    outputs = []
    for comp in components:
        guid = comp.get("guid")
        comp_type = comp.get("type", "")

        # Preview components are always outputs
        if "Preview" in comp_type or "Display" in comp_type:
            outputs.append(comp)
        # Components with no outgoing connections are outputs
        elif guid not in sources and comp_type not in INPUT_TYPES:
            outputs.append(comp)

    return outputs


def infer_output_type(outputs: list[dict]) -> str:
    """Infer the output type from output components.

    Args:
        outputs: List of output component dicts

    Returns:
        Output type string: "curve", "surface", "brep", "points", "display", "unknown"
    """
    for comp in outputs:
        comp_type = comp.get("type", "")
        if comp_type in OUTPUT_TYPE_MAP:
            output = OUTPUT_TYPE_MAP[comp_type]
            # Skip display, look for actual geometry
            if output != "display":
                return output

    # If only display found, return that
    for comp in outputs:
        comp_type = comp.get("type", "")
        if comp_type in OUTPUT_TYPE_MAP:
            return OUTPUT_TYPE_MAP[comp_type]

    return "unknown"


def build_connection_list(connections_data: dict) -> list[dict]:
    """Build flat connection list from gh_snapshot connection data.

    Args:
        connections_data: Dict mapping component GUID to connection info
            {guid: {"inputs": [{"name": str, "sources": [{"guid": str, "param": str}]}]}}

    Returns:
        List of connection dicts: [{"from": guid, "from_param": str, "to": guid, "to_param": str}]
    """
    connections = []

    for target_guid, comp_data in connections_data.items():
        for input_info in comp_data.get("inputs", []):
            param_name = input_info.get("name", "")
            for source in input_info.get("sources", []):
                connections.append({
                    "from": source.get("guid", ""),
                    "from_param": source.get("param", "output"),
                    "to": target_guid,
                    "to_param": param_name,
                })

    return connections


# =============================================================================
# Semantic Inference (used by v1)
# =============================================================================

# Parameter name patterns for role inference
PARAM_ROLE_MAP = {
    # Radius-related
    "R": "radius",
    "Radius": "radius",
    "Rad": "radius",
    # Count-related
    "Count": "count",
    "N": "count",
    "Number": "count",
    # Step/increment
    "Step": "step_size",
    "Increment": "step_size",
    # Amplitude/scale
    "Target": "amplitude",  # Remap target domain
    "Factor": "scale",
    "Scale": "scale",
    "Amplitude": "amplitude",
    # Domain
    "Domain": "domain",
    "A": "domain_start",
    "B": "domain_end",
    # Position
    "X": "x_coordinate",
    "Y": "y_coordinate",
    "Z": "z_coordinate",
    # Height
    "Height": "height",
    "H": "height",
}


def infer_input_semantics(
    inputs: list[dict],
    connections: list[dict],
    components: list[dict],
) -> dict:
    """Infer semantic roles for input components.

    Analyzes what each input is connected to and infers its purpose
    based on parameter names and target components.

    Args:
        inputs: List of input component dicts (sliders, panels)
        connections: List of connection dicts
        components: All components for context lookup

    Returns:
        Dict with "sliders" and "panels" lists, each item having:
        - guid: Component GUID
        - role: Inferred semantic role
        - connected_to: Target component name
        - param: Target parameter name
    """
    # Build GUID -> component lookup
    guid_to_comp = {c.get("guid"): c for c in components}

    # Build source GUID -> connection lookup
    source_connections: dict[str, list[dict]] = {}
    for conn in connections:
        from_guid = conn.get("from")
        if from_guid:
            if from_guid not in source_connections:
                source_connections[from_guid] = []
            source_connections[from_guid].append(conn)

    result: dict[str, list[dict]] = {"sliders": [], "panels": []}

    for inp in inputs:
        guid = inp.get("guid")
        inp_type = inp.get("type", "")

        # Find connections from this input
        conns = source_connections.get(guid, [])

        if inp_type == "GH_Panel":
            # Panels are text inputs
            result["panels"].append({
                "guid": guid,
                "role": "text",
                "connected_to": conns[0].get("to") if conns else None,
                "param": conns[0].get("to_param") if conns else None,
            })
        elif "Slider" in inp_type:
            # Infer role from connection target
            role = "parameter"  # Default
            connected_to = None
            param = None

            if conns:
                conn = conns[0]  # Use first connection for role inference
                param = conn.get("to_param", "")
                target_guid = conn.get("to")
                target_comp = guid_to_comp.get(target_guid, {})
                connected_to = target_comp.get("name")

                # Check parameter name against known patterns
                if param in PARAM_ROLE_MAP:
                    role = PARAM_ROLE_MAP[param]

            result["sliders"].append({
                "guid": guid,
                "role": role,
                "connected_to": connected_to,
                "param": param,
            })

    return result


# =============================================================================
# v1 Extraction (legacy: canvas_state + connections_data)
# =============================================================================

def extract_recipe_v1(
    canvas_state: dict,
    connections_data: dict,
    source_definition: str = "",
    use_dspy: bool = True,
) -> DraftRecipe:
    """Extract a recipe from canvas state (v1 legacy format).

    Uses gh_query canvas state and per-component connection data.
    Produces a v1 DraftRecipe with instance GUIDs in wiring.

    Args:
        canvas_state: Dict with "objects" list from gh_query
        connections_data: Dict mapping component GUID to connection info
        source_definition: Original .ghx filename (optional)
        use_dspy: Whether to use DSPy for classification (default: True)

    Returns:
        DraftRecipe ready for human review (schema_version="1.0")
    """
    components = canvas_state.get("objects", [])

    # Build connection list
    wiring = build_connection_list(connections_data)

    # Identify inputs and outputs
    inputs = identify_inputs(components)
    outputs = identify_outputs(components, wiring)

    # Infer output type
    output_type = infer_output_type(outputs)

    # Infer input semantics
    input_structure = infer_input_semantics(inputs, wiring, components)

    # Classify the recipe
    component_names = [c.get("name", "") for c in components]
    classification = classify_recipe(
        component_names=component_names,
        connection_summary=_build_connection_summary(components, wiring),
        use_dspy=use_dspy,
    )

    # Create draft
    draft = DraftRecipe.create(
        components=components,
        wiring=wiring,
        input_structure=input_structure,
        output_type=output_type,
        source_definition=source_definition,
    )

    # Add classification results
    draft.suggested_name = classification["suggested_name"]
    draft.detected_tags = classification["tags"]
    draft.suggested_intents = classification["intents"]
    draft.description = classification["description"]

    return draft


# =============================================================================
# v2 Extraction (snapshot-based, produces R-prefixed graph)
# =============================================================================

# Regex to replace C-prefixed IDs with R-prefixed IDs in flow strings
_FLOW_CID_RE = re.compile(r"C(\d+)")


def _transform_component_v2(component: dict, r_id: str) -> dict:
    """Transform a single snapshot component into a v2 recipe component.

    Args:
        component: Snapshot component dict (with C-prefixed id, type, etc.)
        r_id: The R-prefixed ID to assign (e.g., "R1")

    Returns:
        Transformed component dict for the v2 graph
    """
    is_param = component.get("is_param", False)
    value_info = component.get("value", {}) or {}
    value_type = value_info.get("type", "")

    entry: dict = {
        "id": r_id,
    }

    if is_param and value_type:
        # For params, use the value type (slider, panel, toggle, etc.)
        entry["type"] = value_type
    else:
        # For regular components, use the snapshot type name
        entry["type"] = component.get("type", "")

    # Nick — always include (for params it's the user-given name like "Radius")
    nick = component.get("nick", "")
    if nick:
        entry["nick"] = nick

    # Name — include for regular components (not params) if present and different from nick
    if not is_param:
        name = component.get("name", "")
        if name and name != nick:
            entry["name"] = name

    # Position
    pos = component.get("pos")
    if pos is not None:
        entry["pos"] = pos

    # Type-specific fields for params
    if is_param and value_type == "slider":
        entry["min"] = value_info.get("min")
        entry["max"] = value_info.get("max")
        entry["value"] = value_info.get("val")
    elif is_param and value_type == "panel":
        entry["content"] = value_info.get("val", "")
    elif is_param and value_type == "toggle":
        entry["value"] = value_info.get("val")

    return entry


def _transform_flow_v2(flow: str, id_map: dict[str, str]) -> str:
    """Replace C-prefixed IDs in a flow string with R-prefixed IDs.

    Args:
        flow: Flow string like "C1.O0>C2.I1"
        id_map: Mapping from C-IDs to R-IDs, e.g. {"C1": "R1", "C2": "R2"}

    Returns:
        Transformed flow string like "R1.O0>R2.I1"
    """
    def _replace(match: re.Match) -> str:
        c_id = match.group(0)  # e.g., "C1"
        return id_map.get(c_id, c_id)  # fall back to original if not mapped

    return _FLOW_CID_RE.sub(_replace, flow)


# Annotation types: panels are data components (only unconnected ones are annotations),
# Scribbles and Markups are always annotations (never part of dataflow)
ANNOTATION_TYPES = {"panel", "Scribble", "Markup", "scribble", "markup"}


def _extract_annotations_v2(
    components: list[dict], flows: list[str]
) -> list[dict]:
    """Extract annotation panels, scribbles, and markups with nearby components.

    Teaching/documentation content that is NOT wired into the dataflow:
    - Unconnected Panels: positioned near components they describe
    - Scribbles: free-form text drawn on the canvas (never connected)
    - Markups: structured annotations (never connected)

    These are linked to their nearest non-annotation components via
    Euclidean distance.

    Args:
        components: v2 graph components (R-prefixed IDs, with pos and type)
        flows: v2 flow strings like "R1.O0>R2.I1"

    Returns:
        List of annotation dicts, each with id, type, text, pos, and nearby IDs.
        Empty list if no annotations found.
    """
    import math

    # 1. Find all R-IDs that participate in flows
    connected_ids: set[str] = set()
    for flow in flows:
        # Format: "R1.O0>R2.I1"
        if ">" not in flow:
            continue
        parts = flow.split(">")
        for part in parts:
            rid = part.split(".")[0]
            connected_ids.add(rid)

    # 2. Separate annotations from target (non-annotation) components
    annotation_comps: list[dict] = []
    target_components: list[dict] = []

    for comp in components:
        cid = comp.get("id", "")
        ctype = comp.get("type", "")
        pos = comp.get("pos")

        if ctype.lower() in {t.lower() for t in ANNOTATION_TYPES}:
            # Panels: only unconnected ones are annotations
            if ctype.lower() == "panel" and cid in connected_ids:
                continue  # Connected panels are data, not annotations
            # Get text from either 'content' or 'text' field (Scribbles use 'text')
            text = (comp.get("content") or comp.get("text") or "").strip()
            if text and pos:
                annotation_comps.append({**comp, "_annotation_type": ctype})
        elif pos:
            target_components.append(comp)

    if not annotation_comps or not target_components:
        return []

    # 3. For each annotation, find nearby components
    MAX_NEIGHBORS = 8
    annotations: list[dict] = []

    for ann in annotation_comps:
        px, py = ann["pos"]
        ann_type = ann["_annotation_type"]

        # Compute distances to all target components
        distances: list[tuple[float, str]] = []
        for tc in target_components:
            tx, ty = tc["pos"]
            dist = math.sqrt((px - tx) ** 2 + (py - ty) ** 2)
            distances.append((dist, tc["id"]))

        distances.sort(key=lambda x: x[0])

        if not distances:
            continue

        # Adaptive radius: 2x distance to nearest component
        nearest_dist = distances[0][0]
        radius = max(nearest_dist * 2.0, 1.0)

        # Collect neighbors within radius, capped at MAX_NEIGHBORS
        nearby: list[str] = []
        for dist, rid in distances[:MAX_NEIGHBORS]:
            if dist <= radius:
                nearby.append(rid)

        if nearby:
            text = (ann.get("content") or ann.get("text") or "").strip()
            entry = {
                "panel_id": ann["id"],  # Keep panel_id for backward compat
                "type": ann_type,
                "text": text,
                "pos": ann["pos"],
                "nearby": nearby,
            }
            annotations.append(entry)

    return annotations


def _infer_output_type_v2(components: list[dict], flows: list[str]) -> str:
    """Infer output type from v2 snapshot components and flows.

    A component is an output if it has no outgoing flows.
    Uses the snapshot-style type names.

    Args:
        components: List of snapshot component dicts
        flows: List of flow strings (C-prefixed, pre-transform)

    Returns:
        Output type string
    """
    # Parse flows to find which C-IDs have outgoing connections
    sources = set()
    for flow in flows:
        # Format: "C1.O0>C2.I1" — source is before ">"
        parts = flow.split(">")
        if len(parts) == 2:
            source_part = parts[0]  # "C1.O0"
            dot_idx = source_part.find(".")
            if dot_idx > 0:
                sources.add(source_part[:dot_idx])

    # Find terminal components (no outgoing connections, not params)
    outputs = []
    for comp in components:
        c_id = comp.get("id", "")
        comp_type = comp.get("type", "")
        is_param = comp.get("is_param", False)

        if "Preview" in comp_type or "Display" in comp_type:
            outputs.append(comp)
        elif c_id not in sources and not is_param:
            outputs.append(comp)

    # Map to output type
    for comp in outputs:
        comp_type = comp.get("type", "")
        if comp_type in _SNAPSHOT_OUTPUT_TYPE_MAP:
            out = _SNAPSHOT_OUTPUT_TYPE_MAP[comp_type]
            if out != "display":
                return out

    for comp in outputs:
        comp_type = comp.get("type", "")
        if comp_type in _SNAPSHOT_OUTPUT_TYPE_MAP:
            return _SNAPSHOT_OUTPUT_TYPE_MAP[comp_type]

    return "unknown"


def _build_flow_summary_v2(components: list[dict], flows: list[str]) -> str:
    """Build a human-readable connection summary from snapshot flows for DSPy.

    Args:
        components: Snapshot component dicts
        flows: Flow strings like "C1.O0>C2.I1"

    Returns:
        Summary string describing data flow
    """
    if not flows:
        return "Components not connected"

    # Build C-ID -> name/nick lookup
    id_to_name: dict[str, str] = {}
    for comp in components:
        c_id = comp.get("id", "")
        name = comp.get("name") or comp.get("nick") or comp.get("type", "?")
        id_to_name[c_id] = name

    # Describe flows (limit to 5 for brevity)
    descriptions = []
    for flow in flows[:5]:
        parts = flow.split(">")
        if len(parts) == 2:
            src_part = parts[0]  # "C1.O0"
            dst_part = parts[1]  # "C2.I1"
            src_id = src_part.split(".")[0]
            dst_id = dst_part.split(".")[0]
            src_name = id_to_name.get(src_id, "?")
            dst_name = id_to_name.get(dst_id, "?")
            descriptions.append(f"{src_name} -> {dst_name}")
        else:
            descriptions.append(flow)

    summary = "; ".join(descriptions)
    if len(flows) > 5:
        summary += f" (and {len(flows) - 5} more connections)"

    return summary


def extract_recipe_v2(
    snapshot: dict,
    source_definition: str = "",
    use_dspy: bool = True,
) -> DraftRecipe:
    """Extract a recipe from a gh_snapshot response (v2 format).

    Transforms the snapshot into a v2 graph with R-prefixed IDs,
    stripping runtime data. The resulting graph is directly replayable
    by swapping R-IDs to T-IDs and submitting to gh_edit.

    Args:
        snapshot: Dict from gh_snapshot response (has components, flows, groups, epoch)
        source_definition: Original .ghx filename (optional)
        use_dspy: Whether to use DSPy for classification (default: True)

    Returns:
        DraftRecipe with graph field populated (schema_version="2.0")
    """
    snap_components = snapshot.get("components", [])
    snap_flows = snapshot.get("flows", [])

    # Step 1: Build ID mapping — C{n} -> R{n} sequentially
    id_map: dict[str, str] = {}
    for idx, comp in enumerate(snap_components, start=1):
        c_id = comp.get("id", "")
        r_id = f"R{idx}"
        id_map[c_id] = r_id

    # Step 2: Transform components
    graph_components = []
    for comp in snap_components:
        c_id = comp.get("id", "")
        r_id = id_map.get(c_id, c_id)
        graph_components.append(_transform_component_v2(comp, r_id))

    # Step 3: Transform flows — replace C-IDs with R-IDs
    graph_flows = [_transform_flow_v2(flow, id_map) for flow in snap_flows]

    # Step 4: Build the graph dict (no runtime data)
    graph = {
        "components": graph_components,
        "flows": graph_flows,
        "subgraphs": [],  # Phase 3 will populate
    }

    # Step 4.5: Extract annotations from unconnected panels
    # Teaching/documentation panels positioned near component groups encode
    # semantic structure — the panel text describes what the group does.
    annotations = _extract_annotations_v2(graph_components, graph_flows)
    if annotations:
        graph["annotations"] = annotations

    # Step 5: Infer output type from snapshot data
    output_type = _infer_output_type_v2(snap_components, snap_flows)

    # Step 6: Classify the recipe
    # Extract component names from snapshot for classification
    component_names = []
    for comp in snap_components:
        # Prefer name, fall back to nick, then type
        name = comp.get("name") or comp.get("nick") or comp.get("type", "")
        component_names.append(name)

    classification = classify_recipe(
        component_names=component_names,
        connection_summary=_build_flow_summary_v2(snap_components, snap_flows),
        use_dspy=use_dspy,
    )

    # Step 7: Build v2 input structure from graph components
    input_structure: dict[str, list[dict]] = {"sliders": [], "panels": []}
    for gc in graph_components:
        gc_type = gc.get("type", "")
        if gc_type == "slider":
            input_structure["sliders"].append({
                "id": gc["id"],
                "nick": gc.get("nick", ""),
                "min": gc.get("min"),
                "max": gc.get("max"),
                "value": gc.get("value"),
            })
        elif gc_type == "panel":
            input_structure["panels"].append({
                "id": gc["id"],
                "nick": gc.get("nick", ""),
                "content": gc.get("content", ""),
            })

    # Step 8: Create DraftRecipe with v2 graph
    draft = DraftRecipe.create(
        components=graph_components,
        wiring=[],  # v2 uses flows in graph, not wiring list
        input_structure=input_structure,
        output_type=output_type,
        source_definition=source_definition,
    )
    draft.graph = graph
    draft.schema_version = "2.0"

    # Add classification results
    draft.suggested_name = classification["suggested_name"]
    draft.detected_tags = classification["tags"]
    draft.suggested_intents = classification["intents"]
    draft.description = classification["description"]

    return draft


# =============================================================================
# Recipe Migration (v1 → v2 merge)
# =============================================================================


def merge_v2_into_pattern(pattern, draft: DraftRecipe) -> None:
    """Merge v2 draft fields into an existing v1 pattern, preserving A-MEM metadata.

    Updates exactly 6 recipe fields: graph, schema_version, wiring,
    input_structure, output_type, components_needed. All other fields
    (links, tags, trigger_intents, confidence, evolution, etc.) are untouched.

    Args:
        pattern: PatternNote to upgrade (mutated in place)
        draft: DraftRecipe from extract_recipe_v2()
    """
    pattern.graph = draft.graph
    pattern.schema_version = "2.0"
    pattern.wiring = []
    pattern.input_structure = draft.input_structure
    pattern.output_type = draft.output_type
    pattern.components_needed = [
        c.get("name") or c.get("nick") or c.get("type", "")
        for c in draft.components
    ]


# Recipe Replay (v2 graph → gh_edit document)
# =============================================================================

# Regex to replace R-prefixed IDs with T-prefixed IDs in flow strings
_FLOW_RID_RE = re.compile(r"R(\d+)")


def recipe_to_edit(
    graph: dict,
    offset: tuple[int, int] = (0, 0),
) -> dict:
    """Convert a v2 recipe graph into a gh_edit document.

    Replaces R-prefixed IDs with T-prefixed IDs and applies
    position offset. The returned dict is ready to submit to
    the /gh/edit endpoint (minus the epoch, which the caller adds).

    Args:
        graph: v2 recipe graph with "components", "flows", and optional "subgraphs"
        offset: (x, y) position offset to apply to all components

    Returns:
        dict with "create", "connect" arrays suitable for gh_edit
    """
    create_array: list[dict] = []
    connect_array: list[str] = []

    # Step 1: Transform components → create array
    for comp in graph.get("components", []):
        r_id = comp.get("id", "")
        # Swap R→T prefix
        t_id = _FLOW_RID_RE.sub(r"T\1", r_id) if r_id.startswith("R") else r_id

        comp_type = comp.get("type", "")

        # Apply position offset
        pos = comp.get("pos")
        if pos is not None and len(pos) >= 2:
            pos = [pos[0] + offset[0], pos[1] + offset[1]]

        if comp_type == "slider":
            entry: dict = {
                "temp_id": t_id,
                "type": "slider",
                "nick": comp.get("nick", ""),
                "min": comp.get("min"),
                "max": comp.get("max"),
                "value": comp.get("value"),
            }
            if pos is not None:
                entry["pos"] = pos
        elif comp_type == "panel":
            entry = {
                "temp_id": t_id,
                "type": "panel",
                "content": comp.get("content", ""),
            }
            if pos is not None:
                entry["pos"] = pos
        elif comp_type == "toggle":
            entry = {
                "temp_id": t_id,
                "type": "toggle",
                "value": comp.get("value"),
            }
            if pos is not None:
                entry["pos"] = pos
        else:
            # Regular component — use guid if present, otherwise fall back to name
            entry = {
                "temp_id": t_id,
            }
            guid = comp.get("guid")
            if guid:
                entry["guid"] = guid
            else:
                # Prefer display name ("Sphere"), fall back to type ("Component_Sphere")
                entry["name"] = comp.get("name") or comp_type
            if pos is not None:
                entry["pos"] = pos

        create_array.append(entry)

    # Step 2: Transform flows → connect array (R→T prefix swap)
    for flow in graph.get("flows", []):
        # Replace R-prefixed IDs with T-prefixed: "R1.O0>R2.I1" → "T1.O0>T2.I1"
        t_flow = _FLOW_RID_RE.sub(r"T\1", flow)
        connect_array.append(t_flow)

    # Step 3: Build the edit document
    return {
        "create": create_array,
        "connect": connect_array,
    }


# =============================================================================
# Main Entry Point (dispatches v1 or v2)
# =============================================================================

def extract_recipe(
    canvas_state: dict | None = None,
    connections_data: dict | None = None,
    snapshot: dict | None = None,
    source_definition: str = "",
    use_dspy: bool = True,
) -> DraftRecipe:
    """Extract a recipe from canvas. Uses v2 (snapshot) if snapshot provided, else v1.

    Args:
        canvas_state: (v1) Dict with "objects" list from gh_query
        connections_data: (v1) Dict mapping component GUID to connection info
        snapshot: (v2) Dict from gh_snapshot response
        source_definition: Original .ghx filename (optional)
        use_dspy: Whether to use DSPy for classification (default: True)

    Returns:
        DraftRecipe ready for human review
    """
    if snapshot is not None:
        return extract_recipe_v2(snapshot, source_definition, use_dspy)
    return extract_recipe_v1(
        canvas_state=canvas_state or {},
        connections_data=connections_data or {},
        source_definition=source_definition,
        use_dspy=use_dspy,
    )


# =============================================================================
# Helpers
# =============================================================================

def _build_connection_summary(components: list[dict], wiring: list[dict]) -> str:
    """Build a human-readable connection summary for DSPy.

    Args:
        components: List of component dicts
        wiring: List of connection dicts

    Returns:
        Summary string describing data flow
    """
    if not wiring:
        return "Components not connected"

    # Build GUID -> name lookup
    guid_to_name = {c.get("guid"): c.get("name", "?") for c in components}

    # Describe connections
    connections_desc = []
    for conn in wiring[:5]:  # Limit to 5 for brevity
        from_name = guid_to_name.get(conn["from"], "?")
        to_name = guid_to_name.get(conn["to"], "?")
        connections_desc.append(f"{from_name} -> {to_name}.{conn.get('to_param', '?')}")

    summary = "; ".join(connections_desc)
    if len(wiring) > 5:
        summary += f" (and {len(wiring) - 5} more connections)"

    return summary
