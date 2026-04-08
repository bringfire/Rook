"""Enrich recipe notes from v2 pattern graph data.

Generates factual briefs, descriptions, contexts, and tags from
the actual component types and flows in each recipe's v2 pattern graph.
No Rhino/GH connection or LLM calls needed.

Usage:
    cd mcp_server
    python run_enrich_recipes.py [--dry-run]
"""

import argparse
import json
import glob
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NOTES_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge", "gh", "notes")
PATTERNS_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge", "gh", "patterns")


def clean_component_type(type_str: str) -> str:
    """Strip Component_ prefix and clean up type name.

    'Component_DivideSurface' -> 'DivideSurface'
    'Component_MeshBrepSimple' -> 'MeshBrepSimple'
    'Param_Point' -> 'Point (param)'
    'slider' -> skip (input)
    'panel' -> skip (input)
    """
    if type_str.startswith("Component_"):
        return type_str[len("Component_"):]
    if type_str.startswith("Param_"):
        return type_str[len("Param_"):] + " (param)"
    return type_str


def type_to_tag(type_str: str) -> str | None:
    """Convert a component type to a meaningful tag.

    Returns None for types that shouldn't become tags (sliders, panels, etc.)
    """
    if type_str in ("slider", "panel", "toggle", "button"):
        return None
    if type_str.startswith("Param_"):
        return None

    name = type_str.replace("Component_", "")

    # Map common component names to semantic tags
    tag_map = {
        # Surface operations
        "Loft": "loft",
        "PlaneSurface": "surface-creation",
        "BoundarySurfaces": "surface-creation",
        "Extrude": "extrude",
        "Pipe": "pipe",
        "Sweep1": "sweep",
        "Sweep2": "sweep",
        "RevolveSurface": "revolve",
        "OffsetSurface": "surface-offset",
        # Curve operations
        "Polyline": "polyline",
        "PolyLine": "polyline",
        "NurbsCurve": "nurbs-curve",
        "InterpolateCurve": "interpolate-curve",
        "Circle": "circle",
        "Arc": "arc",
        "Line": "line",
        "Ellipse": "ellipse",
        # Division / analysis
        "DivideCurve": "curve-division",
        "DivideSurface": "surface-division",
        "EvaluateCurve": "curve-evaluation",
        "EvaluateSurface": "surface-evaluation",
        # Geometry
        "DeconstructBrep": "brep-deconstruction",
        "BrepEdges": "brep-analysis",
        "BrepFaces": "brep-analysis",
        "ConstructPoint": "point-construction",
        "MovePoint": "point-manipulation",
        "Deconstruct": "deconstruction",
        # Mesh
        "MeshBrepSimple": "mesh-from-brep",
        "MeshSurface": "mesh-from-surface",
        "MeshJoin": "mesh-join",
        "WeaverBird": "mesh-subdivision",
        # Transform
        "Move": "move",
        "Rotate": "rotate",
        "Scale": "scale",
        "Mirror": "mirror",
        "Orient": "orient",
        # Math
        "Graph": "graph-mapper",
        "GraphMapper": "graph-mapper",
        "Expression": "expression",
        "Evaluate": "expression",
        # Data
        "ListItem": "list-operations",
        "Dispatch": "data-dispatch",
        "FlattenTree": "data-flatten",
        "GraftTree": "data-graft",
        "Merge": "data-merge",
        "RemapNumbers": "remap",
        "Bounds": "domain-bounds",
        "Series": "series",
        "Range": "range",
        # Display
        "CustomPreview": "custom-preview",
        "Gradient": "gradient-display",
        "ColourSwatch": "colour",
    }

    if name in tag_map:
        return tag_map[name]

    # Fall back to kebab-case of name
    # SplitCamelCase: "DivideSurface" -> "divide-surface"
    parts = re.sub(r"([A-Z])", r" \1", name).strip().lower().split()
    if len(parts) >= 2:
        return "-".join(parts[:3])

    return name.lower()


def analyze_graph(graph: dict) -> dict:
    """Analyze a v2 graph to extract factual metadata.

    Returns dict with:
        main_components: list of cleaned type names (no sliders/panels)
        slider_count: number of sliders
        panel_count: number of panels
        total_count: total component count
        flow_count: number of connections
        tags: derived tags from component types
        input_types: list of input component nicknames
    """
    components = graph.get("components", [])
    flows = graph.get("flows", [])

    main_types = []
    slider_count = 0
    panel_count = 0
    input_nicks = []
    tags = set()

    for comp in components:
        ctype = comp.get("type", "")
        if ctype == "slider":
            slider_count += 1
            nick = comp.get("nick", "")
            if nick:
                input_nicks.append(nick)
        elif ctype == "panel":
            panel_count += 1
        else:
            cleaned = clean_component_type(ctype)
            if cleaned and "(param)" not in cleaned:
                main_types.append(cleaned)

            tag = type_to_tag(ctype)
            if tag:
                tags.add(tag)

    # Count frequency to find the main processing chain
    type_counts = Counter(main_types)
    # Deduplicate while preserving first-occurrence order
    seen = set()
    unique_types = []
    for t in main_types:
        if t not in seen:
            seen.add(t)
            unique_types.append(t)

    return {
        "main_components": unique_types,
        "slider_count": slider_count,
        "panel_count": panel_count,
        "total_count": len(components),
        "flow_count": len(flows),
        "tags": sorted(tags),
        "input_nicks": input_nicks,
        "type_counts": type_counts,
    }


def generate_brief(name: str, analysis: dict) -> str:
    """Generate a factual brief from graph analysis."""
    main = analysis["main_components"]

    # Show up to 5 main component types in the chain
    if len(main) > 5:
        chain = " → ".join(main[:5]) + f" +{len(main) - 5} more"
    elif main:
        chain = " → ".join(main)
    else:
        chain = "(no main components)"

    parts = [f"{name}: {chain}"]

    counts = []
    if analysis["total_count"]:
        counts.append(f"{analysis['total_count']} components")
    if analysis["slider_count"]:
        counts.append(f"{analysis['slider_count']} sliders")
    if analysis["flow_count"]:
        counts.append(f"{analysis['flow_count']} connections")

    if counts:
        parts.append(f"({', '.join(counts)})")

    return " ".join(parts)


def generate_solution_principle(name: str, analysis: dict) -> str:
    """Generate a factual solution principle from graph analysis."""
    main = analysis["main_components"]

    if not main:
        return f"Grasshopper definition: {name}"

    # Describe the processing chain
    if len(main) <= 8:
        chain = " → ".join(main)
    else:
        chain = " → ".join(main[:6]) + f" → ... → {main[-1]}"

    parts = [f"Processing chain: {chain}."]

    if analysis["input_nicks"]:
        nicks = ", ".join(analysis["input_nicks"][:6])
        if len(analysis["input_nicks"]) > 6:
            nicks += f" +{len(analysis['input_nicks']) - 6} more"
        parts.append(f"Inputs: {nicks}.")

    return " ".join(parts)


def enrich_recipe(note: dict, pattern: dict) -> tuple[dict, list[str]]:
    """Enrich a recipe note from its v2 pattern graph.

    Returns (enriched_note, list_of_changes).
    """
    changes = []
    recipe = pattern.get("recipe", {})
    graph = recipe.get("graph", {})
    source_def = recipe.get("source_definition", "")
    name = note.get("name", "")

    if not graph or not graph.get("components"):
        return note, changes

    analysis = analyze_graph(graph)

    # Brief
    old_brief = note.get("brief", "")
    generic_briefs = [
        "Surface created from curves",
        "Parametric workflow",
        "Curve-based form creation",
        "Point-based parametric",
    ]
    if any(old_brief.startswith(g) for g in generic_briefs) or old_brief == name:
        new_brief = generate_brief(name, analysis)
        note["brief"] = new_brief
        changes.append(f"brief: {new_brief[:60]}")

    # Solution principle
    old_sp = note.get("solution_principle", "")
    if any(old_sp.startswith(g) for g in generic_briefs) or not old_sp:
        new_sp = generate_solution_principle(name, analysis)
        note["solution_principle"] = new_sp
        changes.append(f"solution_principle: {new_sp[:60]}")

    # Context
    old_ctx = note.get("context", "")
    if any(old_ctx.startswith(g) for g in generic_briefs) or not old_ctx:
        new_ctx = f"Extracted from: {source_def}" if source_def else f"Grasshopper definition: {name}"
        note["context"] = new_ctx
        changes.append(f"context: {new_ctx[:60]}")

    # Tags — replace generic tags with graph-derived ones
    old_tags = set(note.get("tags", []))
    generic_tags = {
        "parametric", "surface-creation", "point-sequence",
        "curve-based", "trigonometric", "pipe-output",
        "curve-division", "panelization", "mathematical-functions",
    }
    new_graph_tags = set(analysis["tags"])

    if new_graph_tags:
        # Keep non-generic old tags, add graph-derived ones
        kept_tags = old_tags - generic_tags
        merged_tags = sorted(kept_tags | new_graph_tags)
        if set(merged_tags) != old_tags:
            note["tags"] = merged_tags
            added = new_graph_tags - old_tags
            removed = old_tags & generic_tags - new_graph_tags
            if added or removed:
                changes.append(f"tags: +{len(added)}/-{len(removed)}")

    return note, changes


def main():
    parser = argparse.ArgumentParser(description="Enrich recipe notes from v2 pattern graphs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    args = parser.parse_args()

    recipe_files = sorted(glob.glob(os.path.join(NOTES_DIR, "recipe_*.json")))
    print(f"Found {len(recipe_files)} recipe note files")

    enriched = 0
    skipped = 0
    no_pattern = 0

    for filepath in recipe_files:
        with open(filepath, encoding="utf-8") as f:
            note = json.load(f)

        nid = note.get("note_id", "")
        pid = nid.replace("recipe_", "")
        name = note.get("name", "")

        # Load corresponding v2 pattern
        pattern_path = os.path.join(PATTERNS_DIR, f"{pid}.json")
        if not os.path.exists(pattern_path):
            no_pattern += 1
            continue

        with open(pattern_path, encoding="utf-8") as f:
            pattern = json.load(f)

        enriched_note, changes = enrich_recipe(note, pattern)

        if changes:
            enriched += 1
            if args.dry_run:
                print(f"  WOULD ENRICH {name}: {'; '.join(changes)}")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(enriched_note, f, indent=2, ensure_ascii=False)
                print(f"  ENRICHED {name}: {len(changes)} fields")
        else:
            skipped += 1

    print(f"\n=== Summary ===")
    print(f"Enriched: {enriched}")
    print(f"Skipped (already enriched or no changes): {skipped}")
    print(f"No matching pattern: {no_pattern}")
    print(f"Total: {len(recipe_files)}")

    if args.dry_run:
        print("\nDry run — no files modified.")


if __name__ == "__main__":
    main()
