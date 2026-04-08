#!/usr/bin/env python3
"""
Extract teaching knowledge from Professional tutorial images.

These images are from a standalone visual GH course with no .gh files.
Teaching data was extracted by visual inspection of each image.

Usage:
    python run_extract_professional_tutorials.py [--dry-run]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

NOTES_DIR = Path(__file__).parent.parent / "knowledge" / "gh" / "notes"
SOURCE = "professional_tutorial_visual"
COURSE = "BeginnerToAdvanced"
LEVEL = "Professional"

def stable_id(image_name: str) -> str:
    raw = f"{COURSE}:{LEVEL}:{image_name}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"tutorial_{h}"


LESSONS = [
    # ── LESSON 6: Advanced Data Tree and Structural Patterns ──
    {
        "image": "6-1",
        "name": "Shift List — Pipe Structure Between Shifted Circle Divisions",
        "cluster_type": "single",
        "brief": "Shift List shifts list items by offset with wrap. Two circles → Merge → Flip Matrix → Divide Curve → Explode Tree → Tree Branch → Shift List → Line → Pipe → Custom Preview.",
        "context": (
            "Top-left demonstrates Shift List: Panel (A-F) → Shift List (shift=-2, Wrap=True) → Panel (C,D,E,F,A,B). "
            "Items shift by offset; Wrap cycles items back to start. Boolean Toggle controls Wrap. "
            "Main definition: Two Circles (radii 4.56 and 12.00). Construct Point (0,0,16.86) → Move → creates upper circle. "
            "Surface → Extrude (direction Panel '0,0,0.25'). "
            "Merge two circles → Flip Matrix → Divide Curve (Count=30). "
            "Explode Tree splits branches. Tree Branch (Path=0 and Path=1) extracts individual circle divisions. "
            "Shift List (shift=-10, Wrap) offsets point indices on one circle. "
            "Line (Start Point from branch 0, End Point from shifted branch 1) → Pipe (Radius=0.25) → Custom Preview ('GRAY'). "
            "Point List (Size=1.00) for visualization. "
            "Result: diagonal pipe connections between division points on two vertically offset circles."
        ),
        "solution_principle": (
            "Shift List rotates list items by an offset. Wrap=True cycles items around. "
            "Connecting points from one circle to SHIFTED points on another creates diagonal structural connections. "
            "Tree Branch extracts specific branches by path. Explode Tree splits all branches. "
            "This Shift List pattern is fundamental for creating diagrid/lattice structures between two curves."
        ),
        "components": ["Panel", "Shift List", "Boolean Toggle", "Circle", "Construct Point", "Move",
                        "Surface", "Extrude", "Merge", "Flip Matrix", "Divide Curve", "Explode Tree",
                        "Tree Branch", "Line", "Pipe", "Custom Preview", "Point List", "Number Slider"],
        "keywords": ["shift list", "wrap", "pipe structure", "diagrid", "lattice", "divide curve",
                      "explode tree", "tree branch", "shifted connections"],
        "tags": ["professional", "shift-list", "structural", "diagrid", "pipe", "tree-operations"],
        "trigger_intents": [
            "shift list grasshopper", "diagrid pipe structure",
            "connect shifted division points", "lattice between circles",
            "shift list wrap pattern", "structural connections between curves"
        ],
    },
    {
        "image": "6-2",
        "name": "Gene Pool Shift — Varied Connections with PolyLine and Loft",
        "cluster_type": "progression",
        "brief": "Extends 6-1: Gene Pool replaces fixed shift for individual control. Graft Tree + Shift List → PolyLine → Flip Matrix → Pipe + Loft. Two outputs: piped lines and lofted surface.",
        "context": (
            "Builds on 6-1's two-circle pipe structure. "
            "Gene Pool (pink border) replaces the fixed Shift List offset — each division point gets its own shift value. "
            "Graft Tree restructures data for per-point control. "
            "Divide Curve (Count=30) → Shift List with Gene Pool offsets. "
            "Shifted points → PolyLine (Vertices, Closed) instead of just Line. "
            "Flip Matrix → PolyLine connections. "
            "Two outputs: Pipe (Radius=0.23, with Caps) → Custom Preview ('GRAY') for structural members. "
            "Also Loft → Custom Preview for surface visualization. "
            "Multiple Param Viewers track data tree structure: 1 branch, 2 branches, 30 branches. "
            "Result: varied, non-uniform connection patterns controlled by Gene Pool."
        ),
        "solution_principle": (
            "Gene Pool replaces fixed parameters with individually adjustable values per element. "
            "Graft Tree ensures each Gene Pool value maps to one division point. "
            "PolyLine creates connected paths through multiple points (vs Line for just two points). "
            "Two simultaneous outputs — Pipe for solid members, Loft for surface — show the same data in different forms."
        ),
        "components": ["Circle", "Construct Point", "Move", "Surface", "Extrude", "Merge",
                        "Flip Matrix", "Divide Curve", "Gene Pool", "Graft Tree", "Shift List",
                        "PolyLine", "Pipe", "Loft", "Custom Preview", "Param Viewer", "Number Slider"],
        "keywords": ["gene pool shift", "graft tree", "polyline", "varied connections", "pipe and loft",
                      "individual shift control", "non-uniform lattice"],
        "tags": ["professional", "progression", "gene-pool", "shift-list", "graft-tree", "polyline", "loft"],
        "trigger_intents": [
            "gene pool shift list", "varied lattice connections",
            "graft tree per element control", "polyline from shifted points",
            "pipe and loft from same data", "non-uniform structural pattern"
        ],
    },
    {
        "image": "6-3",
        "name": "Two Surface Methods — Ruled Surface vs Entwine+Flip Matrix+Loft",
        "cluster_type": "comparison",
        "brief": "Two methods from same shifted-circle data: METHOD #01 Ruled Surface (pink) vs METHOD #02 Entwine → Flip Matrix → Loft (purple). Plus Scale with second Gene Pool.",
        "context": (
            "Extends 6-2 with two explicit output methods labeled and color-coded. "
            "Same base: two circles, Gene Pool shifts, Divide Curve pipeline. "
            "METHOD #01 (pink background): Ruled Surface (Curve A, Curve B) → Custom Preview ('GRAY'). "
            "Creates ruled surfaces between corresponding shifted polylines — linear interpolation. "
            "METHOD #02 (purple background): Entwine → Flip Matrix → Loft → Custom Preview ('GRAY'). "
            "Creates smooth lofted surfaces between the polylines. "
            "Additional: Scale (bottom area) with a second Gene Pool for per-element scale variation. "
            "Divide Curve for the scaled geometry. Many Param Viewers throughout. "
            "Shows the same structural data rendered as two fundamentally different surface types."
        ),
        "solution_principle": (
            "Ruled Surface creates LINEAR interpolation between two curves — faceted, fast, predictable. "
            "Entwine → Flip Matrix → Loft creates SMOOTH interpolation — organic, more complex. "
            "Choice depends on desired aesthetic: ruled for structural/angular, loft for flowing/smooth. "
            "Multiple Gene Pools can drive different parameters (shift + scale) from the same base geometry."
        ),
        "components": ["Circle", "Move", "Extrude", "Merge", "Flip Matrix", "Divide Curve",
                        "Gene Pool", "Graft Tree", "Shift List", "PolyLine", "Ruled Surface",
                        "Entwine", "Loft", "Scale", "Custom Preview", "Param Viewer", "Number Slider"],
        "keywords": ["ruled surface vs loft", "two methods", "surface comparison", "linear vs smooth",
                      "dual gene pool", "method comparison"],
        "tags": ["professional", "comparison", "ruled-surface", "loft", "entwine-flip-loft", "dual-gene-pool"],
        "trigger_intents": [
            "ruled surface vs loft", "two surface methods comparison",
            "linear vs smooth surface", "ruled surface from shifted curves",
            "entwine flip matrix loft vs ruled surface", "which surface method to use"
        ],
    },
    {
        "image": "6-4",
        "name": "Three Surface Methods — Ruled Surface, Entwine+Loft, Extended Pipeline",
        "cluster_type": "alternatives",
        "brief": "Three labeled methods from same data: METHOD #01 (orange), METHOD #02 (purple), METHOD #03 (purple). Plus parameter exploration clusters below.",
        "context": (
            "Three explicitly labeled methods for generating surfaces from the shifted-circle structural data. "
            "METHOD #01 (orange background): First surface approach — likely Ruled Surface or direct surface creation. "
            "METHOD #02 (purple background): Second approach — likely Entwine + Flip Matrix + Loft. "
            "METHOD #03 (purple background): Extended pipeline with additional components — more complex surface treatment. "
            "Bottom section: Multiple small isolated clusters showing parameter exploration. "
            "Different configurations of the Gene Pool, Shift List, and surface creation components. "
            "These small clusters demonstrate how changing parameters affects the output — "
            "a parameter study approach to understanding the definition's behavior."
        ),
        "solution_principle": (
            "Complex definitions benefit from trying multiple output methods and comparing results. "
            "Labeling methods (#01, #02, #03) with colored groups aids visual organization. "
            "Parameter exploration clusters (small isolated groups) help understand sensitivity to changes. "
            "This approach — build one data pipeline, fork into multiple output methods — is efficient professional practice."
        ),
        "components": ["Circle", "Move", "Divide Curve", "Gene Pool", "Shift List",
                        "Ruled Surface", "Entwine", "Flip Matrix", "Loft", "Custom Preview",
                        "Param Viewer", "Number Slider"],
        "keywords": ["three methods", "parameter exploration", "surface alternatives", "labeled methods",
                      "professional workflow", "color-coded groups"],
        "tags": ["professional", "alternatives", "three-methods", "parameter-study", "workflow-organization"],
        "trigger_intents": [
            "compare three surface methods", "parameter exploration grasshopper",
            "labeled method groups", "professional workflow organization",
            "fork data into multiple outputs", "surface method comparison"
        ],
    },
    {
        "image": "6-5",
        "name": "Double Partition List — Nested Tree Structure with Shift Paths",
        "cluster_type": "single",
        "brief": "Point (N=30) → Partition List (15) → 2 branches → Partition List (3) → 10 branches of 3 → PolyLine → Shift Paths (Offset=-1) → 2 branches → Loft.",
        "context": (
            "Demonstrates nested Partition List for multi-level tree structuring. "
            "Point param → Param Viewer: '1 branch, N=30'. "
            "Point List (Size=2) for visualization. "
            "Partition List #1 (Size=15): splits 30 items into 2 branches of 15. "
            "Param Viewer: '2 branches, N=15 each'. "
            "Partition List #2 (Size=3): splits each branch further. "
            "Param Viewer: '10 branches, N=3 each'. Tree paths: {0;0;0} through {0;1;4}. "
            "PolyLine (Vertices, Closed): creates closed triangles from each group of 3 points. "
            "Shift Paths (Offset=-1, shown in green): removes one level of tree depth. "
            "Param Viewer after shift: '2 branches' (collapsed from 10). "
            "→ Loft: lofts between the two branch groups. "
            "Final Param Viewer: '2 branches, N=1 and N=5'. "
            "Shows how nested partitioning creates hierarchical tree structure and Shift Paths simplifies it."
        ),
        "solution_principle": (
            "Double Partition List creates nested tree structure: first split divides into major groups, "
            "second split divides into sub-groups. "
            "Shift Paths changes the tree path depth — Offset=-1 removes the deepest level, collapsing sub-branches. "
            "This is essential for controlling how Loft/Flip Matrix operate on nested data. "
            "Understanding tree depth and Shift Paths is key to professional-level data tree manipulation."
        ),
        "components": ["Point", "Point List", "Partition List", "PolyLine", "Shift Paths",
                        "Loft", "Param Viewer", "Number Slider", "Panel"],
        "keywords": ["double partition list", "nested tree", "shift paths", "tree depth", "hierarchical structure",
                      "collapse branches", "multi-level partition"],
        "tags": ["professional", "data-tree", "partition-list", "shift-paths", "nested-structure", "tree-depth"],
        "trigger_intents": [
            "double partition list", "nested tree structure",
            "shift paths offset", "collapse tree depth",
            "multi-level partition grasshopper", "hierarchical data tree"
        ],
    },
    {
        "image": "6-6",
        "name": "Point Movement Patterns — Duplicate Data, Cull+Weave, Dispatch+Weave",
        "cluster_type": "alternatives",
        "brief": "Five purple clusters: basic Point→Move→PolyLine, Duplicate Data effect, Cull Pattern+Move→Weave→PolyLine, Dispatch+Weave→PolyLine, Partition List tree transformation.",
        "context": (
            "Five purple-background clusters showing different point manipulation patterns. "
            "Cluster 1 (top-left): Point → Unit Y → Move → PolyLine. Simple: move all points in Y and connect. "
            "Panel shows coordinate values. "
            "Cluster 2 (top-middle): Point → Unit Y → Move → PolyLine. With Duplicate Data showing "
            "how duplicating data affects the pattern. Panel shows duplication effects. "
            "Cluster 3 (top-right): Point → Cull Pattern (two patterns) → two culled sets. "
            "Each Cull Pattern output → Move (different Y offsets) → Weave → PolyLine. "
            "Creates zigzag/alternating movement patterns by culling, moving differently, then weaving back. "
            "Panels: '0,0,0' and '0,2,0' show the offset values. "
            "Cluster 4 (right): Point → Dispatch → two paths → Weave → PolyLine. "
            "Similar to Cull but using Dispatch. Panels: '0,0' / '0,1' / '1,1'. "
            "Cluster 5 (bottom-left): Point → Partition List → Param Viewer (13 branches) → PolyLine. "
            "Move → Unit Y → PolyLine. Shows partitioned movement."
        ),
        "solution_principle": (
            "Different point manipulation patterns create different geometric results: "
            "Direct Move: uniform offset. "
            "Duplicate Data: repeats items for pattern generation. "
            "Cull Pattern + different Moves + Weave: alternating offsets create zigzag patterns. "
            "Dispatch + Weave: similar alternation with two-output splitting. "
            "Partition List: restructures flat data for group-wise operations. "
            "Weave recombines alternating streams — the key component for zigzag/undulating patterns."
        ),
        "components": ["Point", "Unit Y", "Move", "PolyLine", "Duplicate Data", "Cull Pattern",
                        "Dispatch", "Weave", "Partition List", "Param Viewer", "Panel", "Number Slider"],
        "keywords": ["point movement patterns", "duplicate data", "cull weave", "dispatch weave",
                      "zigzag pattern", "alternating offset", "point manipulation"],
        "tags": ["professional", "alternatives", "point-patterns", "weave", "zigzag", "cull-dispatch"],
        "trigger_intents": [
            "zigzag point pattern", "cull pattern weave",
            "alternating point offsets", "dispatch weave pattern",
            "duplicate data grasshopper", "point movement pattern alternatives"
        ],
    },
    {
        "image": "6-7",
        "name": "4Point Surface and Cull Index — Surfaces from Point Subsets",
        "cluster_type": "alternatives",
        "brief": "Left: Sub List → Explode Tree → 4Point Surface from point subsets. Right: Partition List → Cull Index → PolyLine → Merge → Surface → Brep Join.",
        "context": (
            "Two purple clusters showing different approaches to creating surfaces from point data. "
            "Left cluster: Point param → Point List (Size=0.5). "
            "Param Viewer: 1 branch, then 3 branches after Sub List. "
            "Sub List with domains ('0 to 27', '1 to 28', '2 to 29') — three overlapping ranges. "
            "Explode Tree → 4Point Surface (Corner A, B, C, D). "
            "Creates quad surfaces from groups of 4 points taken from overlapping list ranges. "
            "Right cluster: Point → Point List (Size=0.6). "
            "Partition List (Size=3) → splits points into groups of 3. "
            "Two Cull Index operations with different index patterns from Panels ('0,0 / 1,-1 / 2,-2'). "
            "Each Cull Index selects specific items from each partition. "
            "→ Partition List (Size=3) → PolyLine (Vertices, Closed) → closed triangles. "
            "Merge two sets → Surface. "
            "Brep Join: joins surfaces into a closed Brep (green Param Viewer shows success). "
            "Two approaches to structured surface creation from point data."
        ),
        "solution_principle": (
            "4Point Surface creates a quad surface from exactly 4 corner points — needs careful point selection. "
            "Sub List with overlapping ranges creates sliding windows over point data. "
            "Cull Index removes specific items by index — useful for extracting specific elements from partitioned data. "
            "Brep Join combines separate surfaces into a single Brep — green Param Viewer confirms closed result. "
            "Both methods demonstrate how point data organization determines surface topology."
        ),
        "components": ["Point", "Point List", "Sub List", "Explode Tree", "4Point Surface",
                        "Partition List", "Cull Index", "PolyLine", "Merge", "Surface",
                        "Brep Join", "Param Viewer", "Panel", "Number Slider"],
        "keywords": ["4point surface", "cull index", "sub list overlapping", "brep join",
                      "quad surface from points", "point to surface", "sliding window"],
        "tags": ["professional", "alternatives", "4point-surface", "cull-index", "brep-join", "surface-from-points"],
        "trigger_intents": [
            "4point surface grasshopper", "cull index points",
            "quad surface from point grid", "brep join surfaces",
            "sub list overlapping ranges", "create surfaces from point data"
        ],
    },

    # ── LESSON 7: Advanced List Ops, Planes, Orient, Isotrim ──
    {
        "image": "7-1",
        "name": "List Extraction Methods — List Item, Cull Index, Cull Pattern, Cull Nth",
        "cluster_type": "alternatives",
        "brief": "Three approaches: Char Sequence → List Item (indices 2,6,8,10,12 → C,G,I,K,A) + Cull Index (removes those indices), Cull Pattern (0,0,1 cycle), Cull Nth (frequency=3).",
        "context": (
            "Three clusters comparing list extraction/filtering methods. All use Char Sequence (Count=12) → A through L. "
            "Cluster 1: List Item (Index from Panel: 2,6,8,10,12) → extracts items at those indices: C,G,I,K,A (Wrap brings 12 back to A). "
            "Cull Index (same Indices: 2,6,8,10,12) → REMOVES those indices, keeps the rest: B,D,E,F,H,J. "
            "List Item SELECTS specific indices. Cull Index REMOVES specific indices. Complementary operations. "
            "Cluster 2: Cull Pattern (Pattern from Panel: 0,0,1) → removes every 3rd item: keeps B,C,E,F,H,I,K,L. "
            "Pattern cycles: 0=keep, 1=remove (repeating). "
            "Cluster 3: Cull Nth (Cull frequency from Panel: 3) → removes every Nth item: A,B,D,E,G,H,J,K. "
            "Every 3rd item (C,F,I,L) is removed."
        ),
        "solution_principle": (
            "List Item: SELECTS items at specific indices (positive selection). "
            "Cull Index: REMOVES items at specific indices (negative selection). "
            "Cull Pattern: removes/keeps based on repeating boolean pattern. 0=keep, 1=remove. "
            "Cull Nth: removes every Nth item — simple frequency-based culling. "
            "Choose based on whether you know WHICH items you want (List Item), "
            "WHICH to remove (Cull Index), or want PATTERN-based filtering (Cull Pattern/Nth)."
        ),
        "components": ["Number Slider", "Char Sequence", "Panel", "List Item", "Cull Index",
                        "Cull Pattern", "Cull Nth"],
        "keywords": ["list item", "cull index", "cull pattern", "cull nth", "list extraction",
                      "index selection", "frequency culling", "char sequence"],
        "tags": ["professional", "alternatives", "list-operations", "cull-index", "cull-pattern", "cull-nth"],
        "trigger_intents": [
            "list item vs cull index", "cull pattern vs cull nth",
            "list extraction methods", "remove items by index",
            "frequency based culling", "select vs remove from list"
        ],
    },
    {
        "image": "7-2",
        "name": "Set Operations — Create Set, Member Index, Set Intersection/Union/Difference, SubSet",
        "cluster_type": "alternatives",
        "brief": "Set theory in GH: Create Set (remove duplicates), Member Index (find items), Item Index, Find Similar Member, Set Intersection/Union/Difference, SubSet test. Practical: shared points → Circle.",
        "context": (
            "Comprehensive set operations tutorial with multiple clusters. "
            "Top-left: Panel (A,B,F,S,H,S,F,R,T,T,Y) → List Item (index=4) → 'H'. "
            "Item Index: searches for 'H' in list → returns index 4. Finds BY VALUE. "
            "Left: Panel → Member Index (Member: H,S,T) → Index output shows positions. Count shows frequency. "
            "Top-right: Create Set → removes duplicates: (A,B,F,S,H,R,T,Y) — unique values only. "
            "Middle-right: Two panels (Set A and Set B). "
            "Set Intersection: items in BOTH sets (A,S,R,Y). "
            "Set Union: ALL unique items from both sets. "
            "Set Difference: items in A but NOT in B (B,F,H,F,T,T). "
            "SubSet: tests if Set B is a subset of Set A → Panel shows 'False'. "
            "Bottom-left: Curve → Divide Curve → Points. Find Similar Member (Data=division points, Set=Point reference) "
            "→ Hit + Index. Finds which division points match referenced points. "
            "Bottom-right: Two Point params → Set Intersection → shared points → Circle (Radius=4). "
            "Practical application: create circles at points common to both sets."
        ),
        "solution_principle": (
            "Create Set removes duplicates — essential for clean data. "
            "Member Index finds WHERE an item appears and HOW MANY times. "
            "Set Intersection: items in BOTH sets (AND logic). "
            "Set Union: items in EITHER set (OR logic). "
            "Set Difference: items in A but not B (subtraction). "
            "SubSet: tests containment relationship. "
            "Find Similar Member: spatial matching — finds which elements match between datasets. "
            "Set operations enable powerful geometric selection based on spatial relationships."
        ),
        "components": ["Panel", "List Item", "Item Index", "Member Index", "Create Set",
                        "Set Intersection", "Set Union", "Set Difference", "SubSet",
                        "Curve", "Divide Curve", "Find Similar Member", "Point", "Circle",
                        "Point List", "Number Slider"],
        "keywords": ["set operations", "create set", "member index", "set intersection", "set union",
                      "set difference", "subset test", "find similar member", "item index"],
        "tags": ["professional", "alternatives", "set-operations", "data-manipulation", "spatial-matching"],
        "trigger_intents": [
            "set operations grasshopper", "create set remove duplicates",
            "set intersection union difference", "member index find item",
            "find similar member points", "subset test grasshopper"
        ],
    },
    {
        "image": "7-3",
        "name": "Plane Construction — Construct Plane, Standard Planes, Primitives from Planes",
        "cluster_type": "single",
        "brief": "Construct Plane from Point + two Curve→Vector axes. Plane → Rectangle (domain-sized), Cone (Base+Radius+Length), Circle. Standard planes: YZ, XZ, XY.",
        "context": (
            "Demonstrates plane construction and use. "
            "Top: Construct Plane — Point param → Origin, Curve → Vector → X-Axis, Curve → Vector → Y-Axis. "
            "Creates a plane defined by a point and two direction vectors. "
            "Plane output feeds: "
            "Rectangle: Plane + X Size (Panel '-20 to 50' as domain) + Y Size (Panel '-50 to 25') + Radius. "
            "Domain-based sizing allows asymmetric rectangles. "
            "Cone: Base (Plane) + Radius (slider=12) + Length (slider=34) → creates cone on the plane. "
            "Standard plane components: YZ Plane, XZ Plane, XY Plane — each with Origin input. "
            "Circle: Plane + Radius (slider=17). "
            "Plane param at bottom for referencing existing Rhino planes. "
            "Number Sliders: 100, 11 for additional parameters."
        ),
        "solution_principle": (
            "Planes are defined by an Origin point and two axes (X-Axis, Y-Axis). Z-Axis is computed as cross product. "
            "Construct Plane builds from geometry (Point + Curves converted to Vectors). "
            "YZ/XZ/XY Plane provide standard planes at any origin — quick construction without custom vectors. "
            "Planes drive all oriented geometry: Rectangle, Circle, Cone — everything that needs a 'base'. "
            "Rectangle X/Y Size accepts domains for asymmetric sizing (e.g., '-20 to 50' gives width 70 offset left)."
        ),
        "components": ["Point", "Curve", "Vector", "Construct Plane", "Rectangle", "Cone",
                        "Circle", "YZ Plane", "XZ Plane", "XY Plane", "Plane", "Number Slider", "Panel"],
        "keywords": ["construct plane", "plane from vectors", "rectangle domain", "cone",
                      "yz xz xy plane", "oriented geometry", "plane construction"],
        "tags": ["professional", "planes", "construct-plane", "oriented-geometry", "primitives"],
        "trigger_intents": [
            "construct plane grasshopper", "plane from point and vectors",
            "rectangle from plane domain", "cone on plane",
            "standard planes yz xz xy", "oriented geometry on plane"
        ],
    },
    {
        "image": "7-4",
        "name": "Plane Normal, Center Box, Deconstruct/Reconstruct Plane",
        "cluster_type": "progression",
        "brief": "Plane Normal from Point+Curve. Divide Surface → Plane Normal → Center Box (5×5×4) array. Evaluate Surface → Deconstruct Plane → modify axes → Construct Plane → second Cone.",
        "context": (
            "Three levels of plane operations. "
            "Top: Point + Curve → Plane Normal (Origin + Z-Axis). Simplest plane construction — just origin and normal direction. "
            "Middle: Surface → Divide Surface (U=15, V=17) → Points + Normals. "
            "Plane Normal (Origin=Points, Z-Axis=Normals) → Center Box (X=5, Y=5, Z=4). "
            "→ Custom Preview ('white'). "
            "Creates an array of boxes aligned to surface normals at each division point. "
            "Bottom: Surface → Evaluate Surface (MD Slider: 0.12, 0.43) → Point, Normal, U direction, V direction, Frame. "
            "Plane Normal → Center Box → Custom Preview. "
            "Also: Cone (Radius=12, Length=29) from the Plane Normal. "
            "Deconstruct Plane → Origin, X-Axis, Y-Axis, Z-Axis (extracts plane components). "
            "→ Construct Plane (reassemble with potentially modified axes) → second Cone (Radius=10, Length=23). "
            "Shows deconstructing and reconstructing planes to modify orientation."
        ),
        "solution_principle": (
            "Plane Normal creates a plane from just Origin and Z-Axis direction — the most common construction. "
            "Divide Surface + Plane Normal → Center Box creates surface-aligned box arrays. "
            "Deconstruct Plane extracts individual components (Origin, X/Y/Z axes). "
            "You can modify individual axes, then Construct Plane reassembles. "
            "This decompose-modify-recompose pattern enables fine control over plane orientation."
        ),
        "components": ["Point", "Curve", "Plane Normal", "Surface", "Divide Surface",
                        "Center Box", "Custom Preview", "Evaluate Surface", "MD Slider",
                        "Cone", "Deconstruct Plane", "Construct Plane", "Number Slider", "Panel"],
        "keywords": ["plane normal", "center box", "divide surface", "deconstruct plane",
                      "reconstruct plane", "surface aligned boxes", "plane decomposition"],
        "tags": ["professional", "progression", "plane-normal", "center-box", "divide-surface",
                 "deconstruct-plane", "surface-aligned"],
        "trigger_intents": [
            "plane normal grasshopper", "center box on surface",
            "divide surface box array", "deconstruct plane modify",
            "surface aligned boxes", "plane normal from surface"
        ],
    },
    {
        "image": "7-5",
        "name": "Orient and Transform — Place Geometry on Surface with Rotation",
        "cluster_type": "single",
        "brief": "Orient maps geometry from source plane to target plane on surface. Divide Surface → Plane Normal → Cone. Evaluate Surface → Rotate Plane → Orient Brep. Also Transform + Inverse Transform, Scale, Move.",
        "context": (
            "Demonstrates Orient for placing geometry on surfaces. "
            "Divide Surface → Plane Normal → Cone (Radius=12, Length=43). Background cones at division points. "
            "Evaluate Surface (MD Slider: 0.4, 0.19) → surface point and normal for a single target location. "
            "Rotate Plane: rotates the evaluated plane by angle (slider=44.84°). "
            "Brep reference (imported geometry). "
            "Orient: Geometry=Brep, Source=XY Plane (from Point at origin), Target=Rotated Plane from surface. "
            "Maps the Brep FROM the origin plane TO the surface location with rotation. "
            "→ Custom Preview ('white'). "
            "Transform: Geometry + Transform matrix from Orient → same result (reusing the transform). "
            "Inverse Transform: reverses the orientation — maps back from surface to origin. "
            "Scale (Factor=0.6) + Move (Vector from Vector 2Pt) → additional Custom Preview ('white'). "
            "Shows the full Orient workflow for placing and transforming geometry on surfaces."
        ),
        "solution_principle": (
            "Orient maps geometry from a Source plane to a Target plane — the standard 'place on surface' operation. "
            "Source plane is typically XY at origin (where the geometry was modeled). "
            "Target plane comes from surface evaluation (Plane Normal or Evaluate Surface Frame). "
            "Rotate Plane adds rotation before placement. "
            "Transform reuses Orient's matrix. Inverse Transform reverses the operation. "
            "This Orient workflow is essential for distributing complex geometry across surfaces."
        ),
        "components": ["Surface", "Divide Surface", "Plane Normal", "Cone", "Evaluate Surface",
                        "MD Slider", "Rotate Plane", "Brep", "Orient", "Transform",
                        "Inverse Transform", "Point", "XY Plane", "Scale", "Move",
                        "Vector 2Pt", "Custom Preview", "Number Slider", "Panel"],
        "keywords": ["orient", "transform", "inverse transform", "place on surface", "rotate plane",
                      "source target plane", "geometry distribution"],
        "tags": ["professional", "orient", "transform", "place-on-surface", "rotate-plane",
                 "geometry-distribution"],
        "trigger_intents": [
            "orient geometry on surface", "transform place on surface",
            "orient source target plane", "rotate plane before orient",
            "distribute geometry across surface", "inverse transform grasshopper"
        ],
    },
    {
        "image": "7-6",
        "name": "Isotrim — Surface Subdivision by Domain",
        "cluster_type": "alternatives",
        "brief": "Two approaches: manual Construct Domain² → Isotrim (top), and Divide Domain² (U/V Count) → Isotrim for systematic subdivision (bottom). List Item selects patches.",
        "context": (
            "Two approaches to surface subdivision using Isotrim. "
            "Top: Surface → Group → Bounding Box (context). "
            "Manual domain specification: Panel values (0 to 0.5, 0.5 to 1) → Construct Domain² → Isotrim. "
            "Isotrim (Surface, Domain) trims the surface to the specified UV sub-domain. "
            "List Item (Index=3) selects a specific patch → Custom Preview ('white'). "
            "Bottom: Surface → Domain² → Panel shows raw UV domains: u:{0 To 99.345873}, v:{0 To 115.897906}. "
            "Construct Domain² + Divide Domain² (U Count=2, V Count=2) → Segments output. "
            "Panel shows sub-domains: u:{0 To 49.67} v:{0 To 57.95}, etc. "
            "→ Isotrim → surface patches. List Item → Custom Preview ('white'). "
            "Divide Domain² automatically creates evenly spaced sub-domains — more systematic than manual."
        ),
        "solution_principle": (
            "Isotrim (Isothermal Trim) extracts a sub-surface defined by a 2D domain (UV range). "
            "Manual approach: define Construct Domain² with explicit UV ranges. "
            "Systematic approach: Divide Domain² splits the full UV domain into equal parts by U/V Count. "
            "Domain² shows the full UV extent of a surface. "
            "Isotrim preserves the original surface parameterization — it's a trim, not a rebuild. "
            "This is the foundation for surface-based panelization in professional workflows."
        ),
        "components": ["Surface", "Group", "Bounding Box", "Panel", "Construct Domain²",
                        "Isotrim", "Domain²", "Divide Domain²", "List Item", "Custom Preview",
                        "Number Slider"],
        "keywords": ["isotrim", "surface subdivision", "domain2", "divide domain2", "uv domain",
                      "surface trim", "construct domain2", "surface patches"],
        "tags": ["professional", "alternatives", "isotrim", "surface-subdivision", "domain",
                 "divide-domain", "panelization"],
        "trigger_intents": [
            "isotrim grasshopper", "surface subdivision by domain",
            "divide domain2 isotrim", "construct domain2",
            "surface patching uv domain", "isotrim surface panels"
        ],
    },
    {
        "image": "7-7",
        "name": "Isotrim Applied — Surface Box, Deconstruct Brep, Box Morph",
        "cluster_type": "progression",
        "brief": "Three levels: Isotrim basics (top), Isotrim → Surface Box → Deconstruct Brep → Sphere (middle), Isotrim → Surface Box → Box Morph with reference geometry (bottom, green).",
        "context": (
            "Three progressive applications of Isotrim. "
            "Top: Same Isotrim pattern — Surface + Construct Domain² → Isotrim → Custom Preview + List Item. Review of 7-6. "
            "Middle: Surface → Construct Domain² → Divide Domain² → Isotrim → Surface Box. "
            "Surface Box creates a box volume from each surface patch. "
            "Deconstruct Brep → Faces. Sphere component. Custom Preview. "
            "Shows how to extract box volumes from Isotrim patches and decompose them. "
            "Bottom (green): Full Box Morph workflow. "
            "Surface → Divide Domain² → Isotrim → Surface Box → used as target boxes. "
            "Separate reference: Surface + Bounding Box → Volume → used as source box. "
            "Box Morph: maps reference geometry from source Bounding Box into each target Surface Box. "
            "List Item selects specific morphed elements. "
            "Custom Preview ('white'). "
            "Box Morph deforms the reference geometry to fit each surface box — the most powerful "
            "panelization technique for placing complex geometry on arbitrary surfaces."
        ),
        "solution_principle": (
            "Surface Box creates a 3D box volume aligned to each Isotrim surface patch. "
            "Deconstruct Brep extracts faces from the box for further operations. "
            "Box Morph is the key operation: maps geometry from a reference bounding box INTO each Surface Box. "
            "The reference geometry gets deformed to match the target surface curvature. "
            "Workflow: 1) Divide Domain² → Isotrim → Surface Box (targets), "
            "2) Reference geometry → Bounding Box (source), "
            "3) Box Morph (reference, source box, target boxes). "
            "This is the professional standard for distributing complex geometry across curved surfaces."
        ),
        "components": ["Surface", "Construct Domain²", "Divide Domain²", "Isotrim", "Surface Box",
                        "Deconstruct Brep", "Sphere", "Bounding Box", "Volume", "Box Morph",
                        "List Item", "Custom Preview", "Number Slider", "Panel"],
        "keywords": ["box morph", "surface box", "isotrim", "deconstruct brep", "geometry morphing",
                      "panelization", "reference geometry", "surface deformation"],
        "tags": ["professional", "progression", "box-morph", "surface-box", "isotrim", "panelization",
                 "geometry-morphing"],
        "trigger_intents": [
            "box morph grasshopper", "surface box morph",
            "isotrim surface box", "morph geometry onto surface",
            "panelization box morph", "deform reference geometry to surface"
        ],
    },
]


def build_note(lesson: dict) -> dict:
    image = lesson["image"]
    note_id = stable_id(image)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    lesson_num = int(image.split("-")[0])
    lesson_labels = {
        6: "Advanced Data Tree and Structural Patterns",
        7: "Advanced List Ops Planes Orient Isotrim",
    }
    category_label = lesson_labels.get(lesson_num, f"Lesson {lesson_num}")

    return {
        "note_id": note_id,
        "note_type": "teaching",
        "name": f"Professional {image}: {lesson['name']}",
        "brief": lesson["brief"],
        "version": "1.0",
        "created": now,
        "context": lesson["context"],
        "keywords": lesson["keywords"],
        "category": f"Professional - {category_label}",
        "tags": lesson["tags"] + ["tutorial", "visual-course", "beginner-to-advanced"],
        "trigger_intents": lesson["trigger_intents"],
        "trigger_symptoms": [],
        "components": lesson["components"],
        "solution_principle": lesson["solution_principle"],
        "anti_patterns": [],
        "preconditions": [],
        "postconditions": [],
        "links": [],
        "times_used": 0,
        "times_succeeded": 0,
        "retrieval_count": 0,
        "last_accessed": None,
        "last_verified": now,
        "citations": [],
        "created_from": SOURCE,
        "last_evolved": None,
        "evolved_by": [],
        "evolution_history": [],
        "type_data": {
            "course": COURSE,
            "level": LEVEL,
            "image": f"{image}.jpg",
            "lesson_number": lesson_num,
            "step_number": int(image.split("-")[1]),
            "cluster_type": lesson["cluster_type"],
            "components_demonstrated": {c: 1 for c in lesson["components"]},
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Extract teaching notes from Professional tutorial images")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    print(f"Professional Tutorial Extraction")
    print(f"{'=' * 50}")
    print(f"Lessons to process: {len(LESSONS)}")
    print(f"Output directory: {NOTES_DIR}")
    print()

    created = 0
    updated = 0
    skipped = 0

    for lesson in LESSONS:
        note = build_note(lesson)
        note_id = note["note_id"]
        path = NOTES_DIR / f"{note_id}.json"

        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("brief") == note["brief"] and existing.get("context") == note["context"]:
                print(f"  SKIP  {note_id} ({lesson['image']}) — unchanged")
                skipped += 1
                continue
            else:
                note["links"] = existing.get("links", [])
                note["times_used"] = existing.get("times_used", 0)
                note["times_succeeded"] = existing.get("times_succeeded", 0)
                note["retrieval_count"] = existing.get("retrieval_count", 0)
                note["last_accessed"] = existing.get("last_accessed")
                action = "UPDATE"
                updated += 1
        else:
            action = "CREATE"
            created += 1

        if args.dry_run:
            print(f"  {action} {note_id} ({lesson['image']}): {lesson['name']}")
            print(f"         cluster_type={lesson['cluster_type']}, components={len(lesson['components'])}")
        else:
            path.write_text(json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  {action} {note_id} ({lesson['image']}): {lesson['name']}")

    print()
    print(f"Results: {created} created, {updated} updated, {skipped} skipped")

    if not args.dry_run and (created > 0 or updated > 0):
        print()
        print("Rebuilding unified index...")
        from rook.learning.unified_store import get_unified_store, reset_unified_store
        reset_unified_store()
        store = get_unified_store()
        total = len(store._notes)
        tutorial_notes = [n for n in store._notes.values()
                          if n.created_from == SOURCE]
        print(f"  Store: {total} total notes, {len(tutorial_notes)} from this extraction")

        print("Running deterministic evolution (linking)...")
        from rook.learning.knowledge_evolution import KnowledgeEvolution
        evo = KnowledgeEvolution()
        link_count = 0
        for tn in tutorial_notes:
            new_links = evo.link(tn, store)
            link_count += len(new_links)
        print(f"  Created {link_count} links for {len(tutorial_notes)} tutorial notes")

        store.save_all()
        print(f"  Store saved. Index rebuilt.")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
