#!/usr/bin/env python3
"""
Extract teaching knowledge from Beginner tutorial images.

These images are from a standalone visual GH course with no .gh files.
Teaching data was extracted by visual inspection of each image.

Each image contains 1-4 clusters that may represent:
- "single": One definition teaching a concept
- "alternatives": Multiple approaches to the same goal
- "comparison": Side-by-side showing why one approach is better
- "progression": Building from simple to complex
- "culmination": Full pipeline combining prior lessons

Usage:
    python run_extract_beginner_tutorials.py [--dry-run]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

NOTES_DIR = Path(__file__).parent.parent / "knowledge" / "gh" / "notes"
SOURCE = "beginner_tutorial_visual"
COURSE = "BeginnerToAdvanced"
LEVEL = "Beginner"

def stable_id(image_name: str) -> str:
    """Generate stable note ID from image name."""
    raw = f"{COURSE}:{LEVEL}:{image_name}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"tutorial_{h}"


# ============================================================
# EXTRACTED TEACHING DATA (from visual inspection of 26 images)
# ============================================================

LESSONS = [
    # ── LESSON 1: Data Fundamentals ──
    {
        "image": "1-1",
        "name": "Data Types and Flow — Points, Lines, Divide Curve",
        "cluster_type": "single",
        "brief": "Foundational data flow: Point params → Line → Divide Curve → cross-connect divided points with Line",
        "context": (
            "Title: 'Data (point, curve, surface, ...)'. "
            "Two Point params feed a Line component. Line output → Divide Curve (Count=4 via Number Slider). "
            "A second pair of Points creates a second Line, also divided by the same slider. "
            "Panels show divided point coordinates. "
            "The divided points from both lines feed into a final Line component, connecting corresponding points across the two lines. "
            "Classic 'lacing lines between divided curves' pattern."
        ),
        "solution_principle": (
            "Data in Grasshopper flows left to right through typed connections. "
            "Point parameters reference Rhino geometry. Line creates geometry from two points. "
            "Divide Curve splits a curve into equal segments and outputs the division points. "
            "A shared Number Slider controls both divisions, ensuring matching point counts for cross-connection."
        ),
        "components": ["Point", "Line", "Divide Curve", "Number Slider", "Panel"],
        "keywords": ["data flow", "point", "line", "divide curve", "cross connection", "lacing", "division points"],
        "tags": ["beginner", "data-flow", "curve-division", "point-line", "fundamentals"],
        "trigger_intents": [
            "data types in grasshopper", "point line divide curve",
            "how to divide a curve", "connect points between curves",
            "lacing lines between curves", "grasshopper data flow basics"
        ],
    },
    {
        "image": "1-2",
        "name": "Connecting Points — Lines vs Polyline vs Merge",
        "cluster_type": "alternatives",
        "brief": "Four alternative ways to connect 3 points: individual Lines, Polyline+BooleanToggle, open Polyline, Merge→Polyline",
        "context": (
            "Four clusters showing alternative approaches to connect 3 Construct Point components (coords: 1.2,3.7 / 3.5,0.4 / 5.0,5.0). "
            "Cluster 1: Each consecutive pair feeds a Line component (3 Lines total). Naive pair-wise approach. "
            "Cluster 2: All 3 points → Polyline Vertices input. Boolean Toggle (True) → Closed input. Creates closed polyline. "
            "Cluster 3: Same Polyline setup but Closed is unchecked (False). Open polyline. "
            "Cluster 4: 3 Construct Points → Merge (D1,D2,D3) → Result → Polyline Vertices. "
            "Panel shows merged data: {1.2, 3.7, 0}, {3.5, 0.4, 0}, {5, 5, 0}. Cleanest approach using data aggregation."
        ),
        "solution_principle": (
            "Multiple ways exist to connect points into curves. Individual Line components work but don't scale. "
            "Polyline takes a list of vertices directly. Boolean Toggle controls open/closed. "
            "Merge component combines separate data streams into one ordered list — the preferred approach for collecting multiple inputs."
        ),
        "components": ["Construct Point", "Number Slider", "Line", "Polyline", "Boolean Toggle", "Merge", "Panel"],
        "keywords": ["construct point", "polyline", "merge", "boolean toggle", "closed curve", "data aggregation", "alternatives"],
        "tags": ["beginner", "alternatives", "polyline", "merge", "data-aggregation", "point-connection"],
        "trigger_intents": [
            "how to connect points", "polyline from points",
            "merge component grasshopper", "boolean toggle closed curve",
            "alternatives for connecting points", "line vs polyline"
        ],
    },
    {
        "image": "1-3",
        "name": "Point Ordering — Referenced Points, Sort Along Curve, Remove Duplicates",
        "cluster_type": "alternatives",
        "brief": "Four approaches to feeding points into Polyline: raw referenced, with more points, Sort Along Curve, removeDuplicatePts",
        "context": (
            "Four clusters dealing with point ordering challenges. "
            "Cluster 1: Point param (multiple referenced points from Rhino) → Polyline. Panel shows 13 'Referenced Point' entries. Result may be messy. "
            "Cluster 2: Same but with more referenced points, still direct → Polyline. "
            "Cluster 3: Point param → Sort Along Curve (with a Curve reference for ordering) → Polyline. Fixes ordering. "
            "Cluster 4: Point param → removeDuplicatePts → Polyline. Panel shows 15 points with coordinates, second Panel shows 12 unique points. "
            "Teaches that point order matters for polylines and provides solutions."
        ),
        "solution_principle": (
            "When referencing multiple points from Rhino, their order may not match the desired curve path. "
            "Sort Along Curve reorders points based on their position along a reference curve. "
            "removeDuplicatePts eliminates coincident points that cause zero-length segments. "
            "Both are essential cleanup steps before creating curves from referenced geometry."
        ),
        "components": ["Point", "Polyline", "Sort Along Curve", "removeDuplicatePts", "Curve", "Panel"],
        "keywords": ["point ordering", "sort along curve", "remove duplicates", "referenced points", "point cleanup"],
        "tags": ["beginner", "alternatives", "point-ordering", "data-cleanup", "sort", "duplicates"],
        "trigger_intents": [
            "sort points along curve", "remove duplicate points",
            "point ordering polyline", "referenced points wrong order",
            "clean up points before polyline", "sort along curve component"
        ],
    },
    {
        "image": "1-4",
        "name": "Curve Types — Polyline vs Interpolate vs Nurbs Curve",
        "cluster_type": "alternatives",
        "brief": "Three curve types from same points: Polyline (straight segments), Interpolate (smooth through points), Nurbs Curve (control polygon)",
        "context": (
            "Three clusters sharing the same Point param input and Panel (degree=3). "
            "Cluster 1: Point → PolyLine → output 'Polyline Curve'. Straight segments between points. "
            "Cluster 2: Point → Interpolate (Vertices, Degree, Periodic, KnotStyle) → output 'Planar Curve'. Smooth curve passing through all points. "
            "Cluster 3: Point → Nurbs Curve (Vertices, Degree, Periodic) → output 'Planar Curve'. Points act as control polygon, curve doesn't pass through them. "
            "Same inputs, three fundamentally different curve behaviors."
        ),
        "solution_principle": (
            "Grasshopper offers three primary curve types from point sets. "
            "Polyline: linear segments, fast, exact through points. "
            "Interpolate: smooth NURBS curve that passes THROUGH all points. "
            "Nurbs Curve: smooth curve where points are the CONTROL POLYGON — curve is attracted to but doesn't touch interior points. "
            "Degree parameter (Panel=3) affects smoothness. Understanding the difference is essential for surface creation downstream."
        ),
        "components": ["Point", "Polyline", "Interpolate", "Nurbs Curve", "Panel"],
        "keywords": ["curve types", "polyline", "interpolate", "nurbs curve", "control points", "degree", "smooth curve"],
        "tags": ["beginner", "alternatives", "curve-types", "nurbs", "interpolation", "control-polygon"],
        "trigger_intents": [
            "curve types grasshopper", "polyline vs interpolate vs nurbs",
            "smooth curve through points", "nurbs curve control points",
            "interpolate curve grasshopper", "difference between curve types"
        ],
    },
    {
        "image": "1-5",
        "name": "Surface Creation Methods — Boundary, Loft, Extrude Point, Ruled Surface",
        "cluster_type": "alternatives",
        "brief": "Six surface creation methods from referenced curves: Surface param, Boundary Surfaces, Loft, Extrude Point, Loft (multi-curve), Ruled Surface",
        "context": (
            "Multiple referenced Curve params and one Surface param feeding various surface creation components, all piped to Custom Preview with colour. "
            "Surface param: direct reference to Rhino surface. "
            "Colour Swatch + Panels ('red', 'yellow', '19,173,217') define preview colors. "
            "Boundary Surfaces: creates planar surfaces from closed curves (Edges → Surfaces). "
            "Loft: creates surface between curve profiles (Curves → Loft). Shown twice for different curve sets. "
            "Extrude Point: creates surface by extending a curve toward a point (Base, Point → Extrusion). "
            "Ruled Surface: creates surface between exactly two curves (Curve A, Curve B → Surface). "
            "All outputs → Custom Preview with Material for visualization."
        ),
        "solution_principle": (
            "Surfaces in Grasshopper are created from curves using different strategies depending on the input geometry. "
            "Boundary Surfaces: fills closed planar curves. Loft: skins between multiple profile curves. "
            "Extrude Point: stretches a curve to a point (conical forms). Ruled Surface: linear interpolation between two curves. "
            "Custom Preview with Colour Swatch/Panel for material allows visual differentiation."
        ),
        "components": ["Curve", "Surface", "Colour Swatch", "Panel", "Boundary Surfaces", "Loft", "Extrude Point", "Ruled Surface", "Custom Preview", "Point"],
        "keywords": ["surface creation", "boundary surfaces", "loft", "extrude point", "ruled surface", "custom preview", "colour"],
        "tags": ["beginner", "alternatives", "surface-creation", "loft", "extrude", "boundary", "visualization"],
        "trigger_intents": [
            "surface creation methods", "how to create surfaces",
            "loft between curves", "boundary surface from closed curve",
            "extrude point grasshopper", "ruled surface two curves",
            "custom preview colour", "surface from curves"
        ],
    },
    {
        "image": "1-6",
        "name": "Vectors — Unit Vectors, Vector XYZ, Vector 2Pt, Amplitude, Extrude, Move",
        "cluster_type": "single",
        "brief": "Vector fundamentals: Unit X/Y/Z, Vector XYZ, Vector Display, Vector 2Pt, Multiplication, Amplitude, Extrude, Move, Cap Holes",
        "context": (
            "Comprehensive vector lesson with multiple interconnected concepts. "
            "Top-left: Unit Z, Unit Y, Unit X components with Number Sliders (all 10.0) — scaled unit vectors. "
            "Vector XYZ with sliders (8.31, 8.36, 10.0) — arbitrary vector from components. "
            "Panel '-10,20,40' and Panel '0,0,1' show vector coordinates. "
            "Vector Display: visualizes vectors at anchor points. "
            "Vector 2Pt: creates vector between two Point params (Point A → Point B). "
            "Multiplication: scales vector by factor (slider=0). "
            "Amplitude: sets vector to specific length (slider=30). "
            "Curve + vector → Extrude (Base, Direction → Extrusion). "
            "Surface + vector → Move (Geometry, Motion → Geometry). "
            "Move output + Curve Extrude output → Custom Preview. "
            "Second Extrude → Cap Holes (closes open Brep ends)."
        ),
        "solution_principle": (
            "Vectors define direction and magnitude. Unit X/Y/Z provide axis-aligned vectors scaled by Factor. "
            "Vector XYZ constructs from components. Vector 2Pt creates from two points. "
            "Multiplication scales a vector. Amplitude sets exact length. "
            "Vectors drive Extrude (direction of extrusion) and Move (translation direction). "
            "Cap Holes closes open Brep ends after extrusion."
        ),
        "components": ["Unit Z", "Unit Y", "Unit X", "Vector XYZ", "Vector Display", "Vector 2Pt",
                        "Multiplication", "Amplitude", "Extrude", "Move", "Cap Holes", "Custom Preview",
                        "Curve", "Point", "Surface", "Number Slider", "Panel"],
        "keywords": ["vector", "unit vector", "vector xyz", "vector 2pt", "amplitude", "extrude", "move", "cap holes", "direction", "magnitude"],
        "tags": ["beginner", "vectors", "extrude", "move", "transformation", "fundamentals"],
        "trigger_intents": [
            "vectors in grasshopper", "unit vector components",
            "vector 2pt between points", "amplitude vector",
            "extrude with vector direction", "move geometry with vector",
            "cap holes brep", "vector display visualization"
        ],
    },

    # ── LESSON 2: Curves, Tangents, and Data Trees ──
    {
        "image": "2-1",
        "name": "Curve Evaluation — Raw Domain vs Reparameterized",
        "cluster_type": "comparison",
        "brief": "Side-by-side comparison: raw curve domain (0–63.6, error on parameter 40) vs reparameterized (0–1, works correctly)",
        "context": (
            "Two clusters side by side comparing curve evaluation approaches. "
            "Left cluster: Two Curve params with Domain components showing raw domains (0 to 63.60108 and 0 to 34.426273). "
            "Evaluate Curve with Number Slider at 0.0 works. Second Evaluate Curve with slider at 40.0 turns ORANGE — "
            "parameter 40 is within first curve's domain but outside second curve's domain. Error state. "
            "Right cluster: Same two curves but reparameterized (Domain shows '0 to 1'). "
            "Number Slider at 0.52 works for both curves. Evaluate Curve outputs points. "
            "Two evaluated points → Line component (connecting corresponding points). "
            "Demonstrates why reparameterization to 0–1 is essential for reliable curve evaluation."
        ),
        "solution_principle": (
            "Every curve has a parameter domain (e.g. 0 to 63.6) determined by its construction. "
            "Evaluating at a raw parameter value that falls outside a curve's domain causes errors. "
            "Reparameterize (right-click curve input, or use Reparameterize) normalizes the domain to 0–1. "
            "This makes all curves evaluatable with the same slider range, enabling cross-curve operations."
        ),
        "components": ["Curve", "Domain", "Evaluate Curve", "Number Slider", "Line", "Panel"],
        "keywords": ["curve evaluation", "reparameterize", "domain", "parameter", "normalized domain", "evaluate curve error"],
        "tags": ["beginner", "comparison", "curve-evaluation", "reparameterize", "domain", "common-error"],
        "trigger_intents": [
            "reparameterize curve", "curve domain 0 to 1",
            "evaluate curve error", "curve parameter domain",
            "why reparameterize", "normalized curve domain"
        ],
    },
    {
        "image": "2-2",
        "name": "Tangent Vectors Along a Curve — Range, Evaluate, Amplitude",
        "cluster_type": "single",
        "brief": "Evaluate curve at multiple parameters (Range 0–1) to get tangent vectors, scale with Amplitude, display with Vector Display",
        "context": (
            "Single definition with green/teal highlighted groups. "
            "Reparameterized Curve param with 3 Number Sliders. "
            "Panel '0 to 1' → Range component (Domain, Steps=10) → outputs 11 evenly spaced parameters (0, 0.1, 0.2...1.0). "
            "Range output → Evaluate Curve Parameter input. Outputs: Points (tangent locations), Tangents (direction vectors). "
            "Panel shows tangent vectors as coordinates. Second Panel shows tangent Z-components are all 0 (planar curve). "
            "Tangent output → Amplitude (Number Slider=7) → Vector Display (Anchor=points, Vector=scaled tangents). "
            "Visualizes tangent direction and magnitude at each evaluation point along the curve."
        ),
        "solution_principle": (
            "Range component generates evenly spaced values within a domain — perfect for sampling along a reparameterized (0–1) curve. "
            "Evaluate Curve returns both the Point at each parameter AND the Tangent vector (curve direction at that point). "
            "Amplitude scales vectors to a visible length for display. "
            "Vector Display shows vectors anchored at their curve points. This is the foundation for frame-based operations."
        ),
        "components": ["Curve", "Number Slider", "Panel", "Range", "Evaluate Curve", "Amplitude", "Vector Display"],
        "keywords": ["tangent vector", "range", "evaluate curve", "amplitude", "vector display", "curve sampling", "parameter space"],
        "tags": ["beginner", "curve-evaluation", "tangent", "range", "vector-display", "sampling"],
        "trigger_intents": [
            "tangent vectors along curve", "sample curve at intervals",
            "range component curve", "evaluate curve tangent",
            "display vectors along curve", "curve frame vectors"
        ],
    },
    {
        "image": "2-3",
        "name": "Tangent and Normal — Move, Rotate Vector, Curve Middle, Line",
        "cluster_type": "progression",
        "brief": "Extends tangent evaluation by adding Move (offset geometry along tangent), Rotate vector 90° for normal, Line + Curve Middle",
        "context": (
            "Builds on 2-2's tangent evaluation (green area, left). Adds new operations (purple area, right). "
            "From Evaluate Curve: Points and Tangents feed forward. "
            "Amplitude → Vector Display (same as before, showing tangents). "
            "NEW: Move component — Geometry + Motion(tangent) → moves curve copies along tangent direction. "
            "NEW: Line component (Start Point, End Point) connecting two evaluated points. "
            "Curve Middle: finds midpoint of the line. "
            "NEW: Rotate component — Vector + Axis(Unit Z) + Angle(-90 slider) → rotates tangent by -90° to get normal vector. "
            "Second Amplitude (slider=3) + second Vector Display shows the normal vectors. "
            "Panel '0,0,1' provides the rotation axis (Z-axis)."
        ),
        "solution_principle": (
            "Tangent vectors point along the curve. Rotating a tangent 90° around Z-axis gives the 2D normal (perpendicular). "
            "Move translates geometry by a vector — useful for offsetting along tangent/normal directions. "
            "Curve Middle extracts the midpoint of a line/curve. "
            "This tangent+normal pair forms a local coordinate frame at each curve point — the basis for complex structures."
        ),
        "components": ["Curve", "Evaluate Curve", "Range", "Amplitude", "Vector Display",
                        "Move", "Line", "Curve Middle", "Rotate", "Unit Z", "Number Slider", "Panel"],
        "keywords": ["normal vector", "rotate vector", "tangent normal", "curve middle", "move along tangent", "local frame", "perpendicular"],
        "tags": ["beginner", "progression", "tangent-normal", "rotate", "local-frame", "move"],
        "trigger_intents": [
            "normal vector from tangent", "rotate tangent 90 degrees",
            "perpendicular to curve", "move along tangent",
            "curve local frame", "tangent and normal vectors"
        ],
    },
    {
        "image": "2-4",
        "name": "Normal-Based Structure — Point On Curve, Flip Matrix, Interpolate, Extrude",
        "cluster_type": "progression",
        "brief": "Extends tangent/normal pipeline: Point On Curve for positioning, Move along normals, Flip Matrix to transpose, Interpolate curves, Extrude with Unit Z",
        "context": (
            "Builds on 2-3. Left side (green) is the tangent/normal evaluation. Right side adds structural operations. "
            "Point On Curve: evaluates at specific parameter → position on original curve. "
            "Move: offsets the evaluated points along the normal vectors. "
            "Extrude: extends curves along a direction. "
            "Flip Matrix: transposes a data tree — rows become columns. Critical for converting 'points per curve' into 'points per cross-section'. "
            "Interpolate: creates smooth curves through the transposed point sets. "
            "Unit Z: provides vertical extrusion direction. "
            "Param Viewer components show data tree structures at each stage. "
            "Custom Preview visualizes the result."
        ),
        "solution_principle": (
            "Flip Matrix is essential when you have points organized as 'N points on each of M curves' but need "
            "'M corresponding points across all curves' for lofting or interpolation. "
            "Point On Curve gives precise control over where along a curve to evaluate. "
            "This pattern — evaluate, offset by normal, transpose, interpolate — is a core structural workflow."
        ),
        "components": ["Curve", "Evaluate Curve", "Range", "Amplitude", "Rotate", "Move", "Line",
                        "Point On Curve", "Flip Matrix", "Interpolate", "Extrude", "Unit Z",
                        "Vector Display", "Param Viewer", "Custom Preview", "Number Slider"],
        "keywords": ["flip matrix", "transpose", "point on curve", "interpolate", "extrude", "normal offset", "structural workflow"],
        "tags": ["beginner", "progression", "flip-matrix", "interpolate", "extrude", "structural-workflow"],
        "trigger_intents": [
            "flip matrix grasshopper", "transpose data tree",
            "points across curves interpolate", "normal based structure",
            "evaluate offset transpose interpolate", "structural workflow from curve normals"
        ],
    },
    {
        "image": "2-5",
        "name": "Full Structural Pipeline — Series, Range, Gene Pool for Varied Profiles",
        "cluster_type": "progression",
        "brief": "Complete pipeline with Series for height spacing, Range for curve parameters, Gene Pool for varied radii, Extrude for solid",
        "context": (
            "Further extension of the normal-based structure. Left (green) is established pipeline. Right (pink/salmon) adds new features. "
            "Series: generates evenly spaced values (start, step, count) for vertical positioning. "
            "Range: generates parameter values for curve sampling. "
            "Gene Pool: provides individually adjustable values (shown with pink border) — each profile curve gets a different radius/offset. "
            "This creates varied cross-sections rather than uniform ones. "
            "Pipeline: evaluate curve → tangent/normal → offset by varied amounts (Gene Pool) → Flip Matrix → Interpolate → Extrude. "
            "Results in a 3D ribbed surface structure with variation."
        ),
        "solution_principle": (
            "Gene Pool provides a list of individually tweakable values — perfect for creating variation across repeated elements. "
            "Series generates arithmetic sequences for regular spacing. "
            "Combining Gene Pool (variation) with the tangent/normal structural pipeline creates organic, non-uniform structures. "
            "This is the culmination of the curve evaluation → structure workflow."
        ),
        "components": ["Curve", "Evaluate Curve", "Range", "Series", "Amplitude", "Rotate", "Move",
                        "Flip Matrix", "Interpolate", "Extrude", "Gene Pool", "Vector Display",
                        "Param Viewer", "Custom Preview", "Number Slider", "Panel"],
        "keywords": ["gene pool", "series", "varied profiles", "structural pipeline", "non-uniform", "variation"],
        "tags": ["beginner", "progression", "gene-pool", "series", "variation", "structural-pipeline", "culmination"],
        "trigger_intents": [
            "gene pool grasshopper", "series component",
            "varied cross sections", "non-uniform profiles along curve",
            "gene pool for variation", "complete structural pipeline"
        ],
    },
    {
        "image": "2-6",
        "name": "Data Matching — Longest List, Shortest List, Cross Reference",
        "cluster_type": "comparison",
        "brief": "Four panels comparing data matching modes: Longest List (repeats last), Shortest List (truncates), Cross Reference (all combinations), Longest List with graft",
        "context": (
            "Title: 'Data Matching'. Four purple-backgrounded panels showing the same operation with different matching rules. "
            "Top-left: Longest List — when lists have different lengths, the shorter list's last item is repeated. "
            "Top-middle: Shortest List — truncates to the shorter list's length. "
            "Top-right: Cross Reference — creates all possible combinations (Cartesian product). Panel shows many more results. "
            "Bottom-left: Longest List with data grafting applied — changes the tree structure. "
            "Each panel shows Param Viewer with data tree structure and a Panel with the resulting values. "
            "Rhino viewport screenshots (pink borders) show the geometric results of each matching mode."
        ),
        "solution_principle": (
            "Data matching controls how Grasshopper pairs items from lists of different lengths. "
            "Longest List (default): repeats the last item of shorter lists. "
            "Shortest List: stops at the shorter list's end — no repetition. "
            "Cross Reference: every item paired with every other item — Cartesian product. "
            "Right-click a component input to change matching mode. Understanding this is critical for controlling output quantity."
        ),
        "components": ["Number Slider", "Panel", "Param Viewer"],
        "keywords": ["data matching", "longest list", "shortest list", "cross reference", "cartesian product", "list matching", "graft"],
        "tags": ["beginner", "comparison", "data-matching", "list-operations", "cross-reference", "data-tree"],
        "trigger_intents": [
            "data matching grasshopper", "longest list vs shortest list",
            "cross reference all combinations", "list matching modes",
            "how data matching works", "cartesian product grasshopper"
        ],
    },
    {
        "image": "2-7",
        "name": "Data Tree Structure — Single List, Merge, Entwine",
        "cluster_type": "alternatives",
        "brief": "Three tree structures: single Point→Polyline (1 branch), Merge 8 Points (1 branch, 40 items), Entwine 8 Points (8 branches, 5 each)",
        "context": (
            "Title: 'Data Tree Structure'. Three clusters showing different data tree topologies. "
            "Left column: 8 individual Point→Polyline pairs (each creates one polyline from 5 referenced points). "
            "Top-right: Single Point → Polyline → Param Viewer shows '1 branch, N=1'. Just one polyline from one point set. "
            "Middle-right: 8 Point params → Merge (D1-D9) → Polyline → Param Viewer shows '1 branch, N=40'. All points flattened into one list. "
            "Bottom-right: 8 Point params → Entwine ({0;0} through {0;7}) with Flatten → Polyline → Param Viewer shows '8 branches, N=5 each'. "
            "Points organized into branches — one polyline per branch."
        ),
        "solution_principle": (
            "Merge combines all inputs into a SINGLE FLAT list (one branch). "
            "Entwine preserves SEPARATE BRANCHES for each input (one branch per point set). "
            "This distinction is fundamental: Merge → one polyline through all 40 points. Entwine → 8 separate polylines of 5 points each. "
            "Param Viewer shows the tree structure — essential for understanding data organization."
        ),
        "components": ["Point", "Polyline", "Merge", "Entwine", "Param Viewer"],
        "keywords": ["data tree", "merge", "entwine", "branches", "flatten", "param viewer", "tree structure"],
        "tags": ["beginner", "alternatives", "data-tree", "merge-vs-entwine", "branches", "tree-structure"],
        "trigger_intents": [
            "data tree structure", "merge vs entwine",
            "entwine component", "data tree branches",
            "param viewer data tree", "how data trees work"
        ],
    },
    {
        "image": "2-8",
        "name": "Data Trees — Entwine with Panels, Partition List",
        "cluster_type": "alternatives",
        "brief": "Entwine creates branched tree (8 branches of 5), Partition List splits a flat list into chunks — both create tree structure",
        "context": (
            "Title: 'Data Tree Structure' (continued). Two clusters. "
            "Top: 8 Point params → Entwine → Polyline (dashed wire = tree data). "
            "Param Viewer shows 8 branches, N=5 each. Panel on right shows per-branch data ({0;0}: 5 Referenced Points, {0;1}: 5, etc.). "
            "Bottom: Single Point param (all 40 points in one list). "
            "Param Viewer shows '1 branch, N=40'. "
            "Point List (Points, Size=0.5) for visualization. "
            "Partition List (List, Size=5 from Panel) → Chunks output. Creates tree with 8 branches of 5 from the flat list. "
            "→ Polyline (green, highlighted) shows the partitioned result matches Entwine result. "
            "Panel comparison: left shows flat list (40 items), right shows branched ({0;0}: 5 items, {0;1}: 5 items...)."
        ),
        "solution_principle": (
            "Partition List is the inverse of Flatten — it splits a flat list into branches of specified size. "
            "Both Entwine (from separate inputs) and Partition List (from flat list) can create the same tree structure. "
            "Use Entwine when data arrives as separate streams. Use Partition List when you have a flat list that needs structuring. "
            "Point List component visualizes point sizes for debugging."
        ),
        "components": ["Point", "Polyline", "Entwine", "Partition List", "Param Viewer", "Point List", "Panel"],
        "keywords": ["partition list", "entwine", "flatten inverse", "chunk list", "tree from flat", "data tree creation"],
        "tags": ["beginner", "alternatives", "partition-list", "entwine", "tree-creation", "list-operations"],
        "trigger_intents": [
            "partition list grasshopper", "split list into branches",
            "create tree from flat list", "partition list vs entwine",
            "chunk list into groups", "structure flat data into tree"
        ],
    },
    {
        "image": "2-9",
        "name": "Data Tree Operations — Tree Item, List Item, Partition, Circles on Branches",
        "cluster_type": "progression",
        "brief": "Extends tree operations: Partition List into 2 sizes, Tree Item/List Item for branch access, Circle + Surface per branch, Custom Preview",
        "context": (
            "Title: 'Data Tree Structure' (continued). Builds on 2-8 with applied tree operations. "
            "Top section: same Entwine → Polyline tree. "
            "Middle: Partition List now with TWO sizes (creating sub-branches). "
            "Second Partition List creates different grouping. Polyline output highlighted green. "
            "NEW: Tree Item — extracts a specific branch from a tree by path index. "
            "NEW: List Item — extracts specific item from a list by index. "
            "Circle component: creates circles at point positions (from extracted branch data). "
            "Surface component: surfaces from circles. "
            "Custom Preview: visualizes the selected branch's circles/surfaces. "
            "Shows how to navigate and use specific branches within a data tree."
        ),
        "solution_principle": (
            "Tree Item extracts an entire branch from a data tree by its path index. "
            "List Item extracts a single item from a list by integer index. "
            "These are the primary navigation tools for data trees — Tree Item for branches, List Item for items within branches. "
            "Combining tree navigation with geometry creation (Circle, Surface) shows practical tree usage."
        ),
        "components": ["Point", "Polyline", "Entwine", "Partition List", "Param Viewer", "Panel",
                        "Tree Item", "List Item", "Circle", "Surface", "Custom Preview"],
        "keywords": ["tree item", "list item", "branch access", "tree navigation", "index", "circle from tree", "applied data tree"],
        "tags": ["beginner", "progression", "tree-item", "list-item", "tree-navigation", "applied-data-tree"],
        "trigger_intents": [
            "tree item extract branch", "list item by index",
            "access specific branch data tree", "navigate data tree",
            "tree item list item grasshopper", "extract data from tree branch"
        ],
    },
    {
        "image": "2-10",
        "name": "Gene Pool and Data Matching — Shortest List with Circle",
        "cluster_type": "single",
        "brief": "Gene Pool (5 values) + Point (10 branches) → Shortest List matching → Circle with individual radii per point",
        "context": (
            "Single definition. Point param with 10 branches (Param Viewer: 10 branches, N=1 each). "
            "Gene Pool (pink border): 5 individually adjustable values (0.46, 0.87, 0.50, 0.50, 0.50). "
            "Shortest List: matches Point (10 branches) with Gene Pool (5 values) — truncates to 5 (Trim End mode). "
            "→ Circle (Plane=matched points, Radius=matched Gene Pool values). "
            "Output Param Viewer: 10 branches, N=1 each → flattened to match. "
            "Second Param Viewer: 1 branch, N=5 — the Gene Pool values. "
            "Result: circles at 5 of the 10 points, each with individually controlled radius from Gene Pool."
        ),
        "solution_principle": (
            "Gene Pool provides a UI for multiple individually adjustable numeric values. "
            "Shortest List matching paired with Gene Pool means each value maps to one branch/item. "
            "Trim End mode determines which items are dropped when lists don't match. "
            "This pattern — Gene Pool + Shortest List — gives individual control over repeated elements."
        ),
        "components": ["Point", "Gene Pool", "Shortest List", "Circle", "Param Viewer"],
        "keywords": ["gene pool", "shortest list", "individual control", "trim end", "circle radius", "per-element control"],
        "tags": ["beginner", "gene-pool", "data-matching", "shortest-list", "individual-control"],
        "trigger_intents": [
            "gene pool individual values", "shortest list trim",
            "gene pool circle radius", "individual control repeated elements",
            "per element parameter control", "gene pool data matching"
        ],
    },
    {
        "image": "2-11",
        "name": "Complete Curve Normal Structure — Full Pipeline with Entwine, Flip Matrix, Interpolate, Extrude",
        "cluster_type": "single",
        "brief": "Culmination: Evaluate Curve → tangent/normal vectors → Move → Entwine → Flip Matrix → Interpolate → Extrude (full ribbed structure)",
        "context": (
            "Complete single pipeline combining all Lesson 2 concepts. Left-to-right flow: "
            "Curve → Range (0 to 1, steps from slider) → Evaluate Curve → Point + Tangent. "
            "Tangent → Amplitude → Vector Display (visualization). "
            "Tangent → Amplitude → Rotate (with Unit Z axis, angle slider=270°) → normal vector → Vector Display. "
            "Move: geometry along normal. Line: tangent line. Curve Middle: line midpoint. "
            "Points → Entwine (Branch 0;0, Branch 0;1, Branch 0;2) → preserves 3 branches. "
            "Multiple Param Viewers show tree structure at each stage. "
            "Entwine → Flip Matrix → transposes branches. "
            "Flip Matrix output → Interpolate (smooth curves through transposed points). "
            "Final: Extrude along Range → Unit Z for 3D ribbed form. "
            "This is the full structural workflow from curve to 3D geometry."
        ),
        "solution_principle": (
            "This is the complete beginner structural workflow: "
            "1) Sample curve with Range → Evaluate Curve. "
            "2) Get tangent, rotate for normal. "
            "3) Move/offset points along normals. "
            "4) Entwine to organize into branches. "
            "5) Flip Matrix to transpose (rows→columns). "
            "6) Interpolate smooth curves through transposed points. "
            "7) Extrude for 3D form. "
            "Understanding each step and the data tree transformations is the key to Grasshopper fluency."
        ),
        "components": ["Curve", "Range", "Evaluate Curve", "Amplitude", "Rotate", "Unit Z",
                        "Vector Display", "Move", "Line", "Curve Middle", "Entwine",
                        "Param Viewer", "Flip Matrix", "Interpolate", "Extrude", "Number Slider", "Panel"],
        "keywords": ["complete pipeline", "structural workflow", "entwine flip matrix", "tangent normal extrude", "ribbed structure", "culmination"],
        "tags": ["beginner", "culmination", "structural-pipeline", "full-workflow", "flip-matrix", "interpolate", "extrude"],
        "trigger_intents": [
            "complete structural pipeline", "curve to 3d structure",
            "tangent normal workflow full", "entwine flip matrix interpolate",
            "ribbed structure from curve", "full grasshopper workflow beginner"
        ],
    },

    # ── LESSON 3: Applied Projects ──
    {
        "image": "3-1",
        "name": "Tower Form — Cross Reference, Partition, Explode Tree, Multi-Level Move, Loft",
        "cluster_type": "single",
        "brief": "Tower/vase: Point+sliders → Cross Reference → Circle → Partition List → Explode Tree → 3 Unit Z Moves (varying heights) → Entwine → Flip Matrix → Loft",
        "context": (
            "Applied project creating a tower/vase form. "
            "Point param + 3 Number Sliders (radii: 0.39, 0.24, 0.38). "
            "Cross Reference: creates all point-radius combinations. "
            "Circle: from cross-referenced planes and radii. "
            "Partition List (Panel=100): chunks circles into groups. "
            "Param Viewer shows '3 branches, N=100 each'. "
            "Explode Tree: splits into individual outputs ({0;0}, {0;1}, {0;2}). "
            "Three Unit Z components with different heights (0.00, 0.67, 1.35) → Move for each branch. "
            "Three Move components lift each circle group to different heights. "
            "Entwine (Branch 0;0, 0;1, 0;2) recombines → Flatten. "
            "Flip Matrix transposes. "
            "Param Viewer shows final structure. "
            "→ Loft → Custom Preview. Creates a multi-level lofted surface."
        ),
        "solution_principle": (
            "Cross Reference creates the full Cartesian product of points and radii — essential for grid-like arrangements. "
            "Partition List + Explode Tree splits a tree into individual controllable branches. "
            "Multiple Move operations at different heights creates a stacked profile structure. "
            "Entwine recombines → Flip Matrix transposes → Loft skins between profiles. "
            "This is a practical application of data tree manipulation for architectural form."
        ),
        "components": ["Point", "Number Slider", "Cross Reference", "Circle", "Partition List",
                        "Param Viewer", "Explode Tree", "Unit Z", "Move", "Entwine",
                        "Flip Matrix", "Loft", "Custom Preview", "Panel"],
        "keywords": ["tower form", "cross reference", "partition list", "explode tree", "multi-level", "loft", "stacked profiles"],
        "tags": ["beginner", "applied-project", "cross-reference", "explode-tree", "loft", "tower-form", "architectural"],
        "trigger_intents": [
            "tower form grasshopper", "cross reference circles",
            "stacked profiles loft", "explode tree branches",
            "multi level move loft", "architectural form data tree"
        ],
    },
    {
        "image": "3-2",
        "name": "Tower Form Extended — Area Centroid, Tree Item, Tree Branch, Second Loft Path",
        "cluster_type": "progression",
        "brief": "Extends tower: adds Curve reference, Area centroid for circle centers, Tree Item/Branch for selective access, second Loft path for varied form",
        "context": (
            "Builds on 3-1's tower pipeline. Adds new operations on the right side. "
            "Same left pipeline: Point → Cross Reference → Circle → Partition → Explode → Move → Entwine → Flip Matrix → Loft → Custom Preview. "
            "NEW additions: "
            "Curve param: references an existing Rhino curve. "
            "Area: extracts centroid of geometry. "
            "Point List (panel=0.99): visualizes points at size. "
            "Tree Item (Panel indices): extracts specific branches. "
            "Tree Branch: extracts entire branch by path. "
            "Additional Loft → Custom Preview for a second surface variation. "
            "Panel '0' and Panel '1' provide indices for Tree Item/Branch selection. "
            "Move + Unit Z for additional vertical positioning."
        ),
        "solution_principle": (
            "Area component provides the centroid of curves/surfaces — useful for finding circle centers. "
            "Tree Item and Tree Branch allow selective extraction from data trees for creating variations. "
            "Multiple Loft operations on different branch selections create different surface forms from the same base data."
        ),
        "components": ["Point", "Cross Reference", "Circle", "Partition List", "Explode Tree",
                        "Unit Z", "Move", "Entwine", "Flip Matrix", "Loft", "Custom Preview",
                        "Curve", "Area", "Point List", "Tree Item", "Tree Branch", "Panel", "Number Slider"],
        "keywords": ["area centroid", "tree item", "tree branch", "selective extraction", "multiple loft", "tower variation"],
        "tags": ["beginner", "progression", "tree-item", "tree-branch", "area-centroid", "tower-form", "applied-project"],
        "trigger_intents": [
            "area centroid grasshopper", "tree branch extract",
            "selective loft from tree", "tower form variation",
            "multiple surfaces from same data", "tree item tree branch difference"
        ],
    },
    {
        "image": "3-3",
        "name": "Cross Reference Data Explosion — Why 100 Branches from 3 Radii",
        "cluster_type": "single",
        "brief": "Demonstrates Cross Reference data tree: 100 points × 3 radii = 100 branches of 1 circle OR 3 branches of 100 circles depending on tree structure",
        "context": (
            "Focused explanation of Cross Reference data tree behavior. "
            "Point param (100 referenced points, Param Viewer: '100 branches, N=1'). "
            "Panel with values [0.1, 0.2, 0.3] (3 radii, Param Viewer: '1 branch, N=3'). "
            "Both feed into Circle (Plane, Radius). "
            "Output Param Viewers show two perspectives: "
            "- '100 branches, N=3 each' — each point gets 3 circles (one per radius). "
            "- OR after flattening: different arrangement. "
            "Shows how the data tree structure determines the geometric output. "
            "The visual clarity of this example helps understand why Param Viewer is essential."
        ),
        "solution_principle": (
            "Cross Reference with data trees can create unexpected branch structures. "
            "100 points (100 branches × 1) crossed with 3 radii (1 branch × 3) produces 100 branches of 3 items. "
            "Understanding input tree structure is essential for predicting output. "
            "Always check Param Viewer before and after operations that change tree structure."
        ),
        "components": ["Point", "Circle", "Panel", "Param Viewer"],
        "keywords": ["cross reference explosion", "data tree", "branch structure", "100 branches", "param viewer", "tree prediction"],
        "tags": ["beginner", "data-tree", "cross-reference", "tree-structure", "param-viewer", "debugging"],
        "trigger_intents": [
            "cross reference data tree", "why so many branches",
            "cross reference branch explosion", "predict data tree output",
            "param viewer debugging", "understand cross reference tree"
        ],
    },
    {
        "image": "3-4",
        "name": "Solid Forms — Loft+CapHoles vs Extrude+Twist",
        "cluster_type": "alternatives",
        "brief": "Two approaches to solid forms: Curve→Move+Rotate→Merge→Loft→Cap Holes (lofted solid), Curve→Extrude+Twist→Cap Holes (twisted extrusion)",
        "context": (
            "Two clusters showing alternative solid creation methods. "
            "Top: Curve → Unit Z → Move (lift copy) + Rotate (rotate copy) → Merge (original + moved + rotated) → Loft → Cap Holes → Custom Preview. "
            "Two Number Sliders control height (14.84) and rotation angle (90.0). "
            "Creates a lofted solid from original and transformed curve copies. "
            "Bottom: Same Curve → Extrude (Base + Unit Z direction). "
            "Area → Centroid → Line SDL (Start, Direction, Length) creates a twist axis. "
            "Extrusion → Twist (Geometry, Axis, Angle) → Cap Holes → Custom Preview. "
            "Creates a twisted solid extrusion. Two fundamentally different approaches to 3D form."
        ),
        "solution_principle": (
            "Loft approach: duplicate and transform a profile curve, then skin between copies. Good for controlled transitions. "
            "Extrude+Twist approach: extrude a single curve and apply a twist deformation. Good for helical/spiral forms. "
            "Cap Holes closes open Brep ends to make watertight solids. "
            "Area→Centroid→Line SDL creates a center axis for the Twist deformation. "
            "Line SDL (Start, Direction, Length) is useful for creating construction lines."
        ),
        "components": ["Curve", "Unit Z", "Move", "Rotate", "Merge", "Loft", "Cap Holes", "Custom Preview",
                        "Extrude", "Twist", "Area", "Line SDL", "Number Slider"],
        "keywords": ["solid form", "loft cap holes", "extrude twist", "twisted solid", "line sdl", "twist axis", "watertight"],
        "tags": ["beginner", "alternatives", "solid-creation", "loft", "twist", "extrude", "cap-holes"],
        "trigger_intents": [
            "create solid grasshopper", "loft vs extrude twist",
            "twisted extrusion", "cap holes make solid",
            "twist deformation grasshopper", "line sdl twist axis"
        ],
    },
    {
        "image": "3-5",
        "name": "Stacked Ellipses — Simple Series vs Linear Array with Gene Pool Variation",
        "cluster_type": "alternatives",
        "brief": "Two approaches: Ellipse+Series→Move→Loft (uniform stack) vs Ellipse→LinearArray+Rotate(GenePool)+Scale(GenePool)→Loft (varied stack)",
        "context": (
            "Two clusters showing uniform vs varied stacking. "
            "Top (simple): Point → Ellipse (Radius1=3.02, Radius2=2.69). "
            "Series (Start=1.29, Step from slider, Count=5) → Unit Z → Move. Moves ellipse copies to regular heights. "
            "→ Loft → Custom Preview. Creates a uniform vase/tube. "
            "Bottom (varied): Same Point → Ellipse. "
            "Unit Z → Linear Array (Geometry, Direction, Count=5). Creates evenly spaced copies. "
            "Area: extracts centroids of arrayed ellipses. "
            "Gene Pool (rotation angles: 0.10, 0.35, 0.95, 0.84, 1.54) → Rotate (per-ellipse rotation). "
            "Gene Pool (scale factors) → Scale (Geometry, Center=Area centroid, Factor). "
            "→ Loft → Custom Preview. Creates a varied, organic form. "
            "Area provides the proper center point for scaling each ellipse individually."
        ),
        "solution_principle": (
            "Series + Move creates uniform vertical spacing — predictable but rigid. "
            "Linear Array creates the copies, then Gene Pool drives individual Rotate and Scale per copy. "
            "Area centroid provides the correct center for per-element scaling (otherwise elements scale from origin). "
            "Gene Pool + individual transformations is the key to creating organic variation in repeated elements."
        ),
        "components": ["Point", "Ellipse", "Series", "Unit Z", "Move", "Loft", "Custom Preview",
                        "Linear Array", "Area", "Gene Pool", "Rotate", "Scale", "Number Slider"],
        "keywords": ["stacked ellipses", "linear array", "gene pool", "varied rotation", "varied scale", "organic form", "series"],
        "tags": ["beginner", "alternatives", "linear-array", "gene-pool", "scale-rotate", "organic-form"],
        "trigger_intents": [
            "stacked profiles with variation", "linear array gene pool",
            "individual rotation per copy", "scale at centroid",
            "organic loft variation", "series vs linear array"
        ],
    },
    {
        "image": "3-6",
        "name": "Surface Panelization — Diamond Panels on Lofted Form",
        "cluster_type": "progression",
        "brief": "Extends varied ellipse stack: Loft → Diamond Panels (U/V divisions) → Custom Preview with color",
        "context": (
            "Extends 3-5's varied ellipse stack. Same pipeline: Ellipse → Linear Array → Gene Pool Rotate/Scale → Loft. "
            "NEW: Loft output → Diamond Panels component (Surface, U Divisions=23, V Divisions from slider). "
            "Diamond Panels outputs: Diamond Panels geometry and Tri Panels (triangular edge panels). "
            "→ Custom Preview with panel color ('white'). "
            "Number Slider controls panel density (0.75 for scale factor). "
            "Gene Pool values still control rotation and scaling of the base ellipses. "
            "Result: a panelized facade-like surface on the organic lofted form."
        ),
        "solution_principle": (
            "Diamond Panels converts a surface into a diamond/rhombus panelization pattern. "
            "U and V Divisions control panel density in each surface direction. "
            "Tri Panels output handles the triangular panels at surface edges. "
            "This is a common architectural/facade pattern: create a smooth form, then panelize for fabrication or visual effect."
        ),
        "components": ["Point", "Ellipse", "Linear Array", "Gene Pool", "Rotate", "Scale", "Area",
                        "Loft", "Diamond Panels", "Custom Preview", "Number Slider", "Panel", "Unit Z"],
        "keywords": ["diamond panels", "panelization", "facade", "u v divisions", "surface panels", "tri panels"],
        "tags": ["beginner", "progression", "panelization", "diamond-panels", "facade", "architectural", "applied-project"],
        "trigger_intents": [
            "diamond panels grasshopper", "panelize surface",
            "facade panelization", "diamond panel u v divisions",
            "surface to panels", "panelized loft form"
        ],
    },
    {
        "image": "3-7",
        "name": "Coordinate Systems — WCS (X,Y,Z) vs LCS (U,V,W), Evaluate Surface, MD Slider",
        "cluster_type": "comparison",
        "brief": "World vs Local coordinates: Circle→Surface (WCS), then Evaluate Surface with UV point → normal vector, Circle CNR on surface, MD Slider for 2D parameter control",
        "context": (
            "Title: 'World Coordinate System (WCS) (X,Y,Z)' and 'Local Coordinate System (LCS) (U,V,W)'. "
            "Two clusters. "
            "Top: Number Slider → Circle (Radius=2) → Surface → Custom Preview. Simple surface in world coordinates. "
            "Panel shows point coordinates in XYZ: {14.745361, 11.069389, 4.962329}. "
            "Bottom: Surface param + Vector XYZ (sliders: 0.24, 0.55) → Evaluate Surface. "
            "Evaluate Surface outputs: Point (position), Normal (surface perpendicular), U direction, V direction, Frame. "
            "Normal → Amplitude → Vector Display: shows the surface normal vector. "
            "Point + Normal + Number Slider (radius=5) → Circle CNR (Center, Normal, Radius): creates a circle ON the surface aligned to its normal. "
            "→ Surface → Custom Preview. "
            "MD Slider (2D slider widget, 0.56 × 0.51): provides UV coordinates in a visual 2D grid interface."
        ),
        "solution_principle": (
            "WCS (World Coordinate System) uses global X,Y,Z. LCS (Local Coordinate System) uses surface-relative U,V,W. "
            "Evaluate Surface converts UV parameters to world-space Point + Normal + Frame. "
            "Circle CNR creates circles aligned to surface normals — geometry that 'sits on' the surface. "
            "MD Slider provides a 2D interface for UV parameter control — more intuitive than two separate sliders. "
            "This is essential for placing geometry on surfaces."
        ),
        "components": ["Number Slider", "Circle", "Surface", "Custom Preview", "Vector XYZ",
                        "Evaluate Surface", "Amplitude", "Vector Display", "Circle CNR", "MD Slider", "Panel"],
        "keywords": ["coordinate system", "wcs", "lcs", "uv", "evaluate surface", "normal", "circle cnr", "md slider", "surface frame"],
        "tags": ["beginner", "comparison", "coordinate-systems", "evaluate-surface", "surface-normal", "uv-parameters"],
        "trigger_intents": [
            "world vs local coordinates", "evaluate surface uv",
            "surface normal vector", "circle on surface normal",
            "md slider 2d parameter", "place geometry on surface",
            "wcs lcs grasshopper", "evaluate surface point normal"
        ],
    },
    {
        "image": "3-8",
        "name": "Point-to-Surface Methods — Domain², Project, Pull, Surface Closest Point",
        "cluster_type": "single",
        "brief": "Four methods for relating points to surfaces: Domain² (UV domain), Project Point, Pull Point, Surface Closest Point → Evaluate Surface for normals",
        "context": (
            "Single definition showing multiple point-to-surface operations. "
            "Surface param with Domain² showing UV domain: u:{0 To 81.708522}, v:{0 To 37.226276}. "
            "Unit X (Factor from Panel=-1): direction for projection. "
            "Project Point: projects a Point along a Direction onto a Surface Geometry. Returns projected Point + Index. "
            "Pull Point: finds the closest point on geometry to a given point (different from projection — no direction). Returns Closest Point + Distance. "
            "Surface Closest Point: similar to Pull Point but returns UV Point (parameter space coordinates). Panel shows {49.705969, 32.863947, 0}. "
            "Surface Closest Point UV output → Evaluate Surface (Point input). "
            "Evaluate Surface → Normal → Amplitude (slider=12) → Vector Display. "
            "Shows normal vector at the closest point location."
        ),
        "solution_principle": (
            "Three distinct point-to-surface operations: "
            "Project Point: projects along a specified DIRECTION (like casting a ray). "
            "Pull Point: finds nearest point on surface regardless of direction (closest in 3D space). "
            "Surface Closest Point: like Pull but returns UV PARAMETERS, not just the point — needed for Evaluate Surface. "
            "Domain² shows the raw UV domain of a surface. "
            "Chain: Surface Closest Point → UV Point → Evaluate Surface → Normal for surface-aware operations."
        ),
        "components": ["Surface", "Domain²", "Unit X", "Panel", "Project Point", "Pull Point",
                        "Surface Closest Point", "Evaluate Surface", "Amplitude", "Vector Display",
                        "Point", "Number Slider"],
        "keywords": ["project point", "pull point", "surface closest point", "domain 2d", "uv point", "surface analysis", "projection"],
        "tags": ["beginner", "point-to-surface", "project", "pull", "closest-point", "surface-analysis", "uv-parameters"],
        "trigger_intents": [
            "project point onto surface", "pull point closest",
            "surface closest point uv", "domain2 surface",
            "point to surface methods", "project vs pull vs closest point"
        ],
    },
    {
        "image": "3-9",
        "name": "Final Project — Panelized Tower with Surface Normal Extrusions",
        "cluster_type": "single",
        "brief": "Culmination: Ellipse→LinearArray→Rotate/Scale(GenePool)→Loft→Diamond Panels + Area→SurfaceClosestPoint→EvaluateSurface→Normal→Move→ExtrudePoint→CustomPreview",
        "context": (
            "Final project combining all beginner course concepts. Left-to-right pipeline: "
            "Left section (purple): Ellipse stack pipeline — Point → Ellipse → Linear Array → Gene Pool Rotate/Scale → Loft → Diamond Panels (sliders for U/V divisions and scale). "
            "→ Custom Preview. Creates the panelized tower form. "
            "Right section (white): Normal extrusion pipeline — "
            "Area: extracts centroids of diamond panels. "
            "Surface Closest Point: finds UV coordinates on the lofted surface for each panel centroid. "
            "Evaluate Surface: gets surface Normal at each UV point. "
            "Amplitude → Vector Display: visualizes normals. "
            "Multiplication: scales normals by a factor (slider=0.15). "
            "Move: offsets panel centroids along scaled normals. "
            "Extrude Point: extrudes diamond panels toward the offset points. "
            "→ Custom Preview ('white' color). "
            "Result: a diamond-panelized tower with panels extruded along surface normals — a complete architectural facade."
        ),
        "solution_principle": (
            "This project combines: data trees (Cross Reference, Partition, Entwine, Flip Matrix), "
            "transformations (Move, Rotate, Scale with Gene Pool), "
            "surface creation (Loft), panelization (Diamond Panels), "
            "surface analysis (Area centroid → Surface Closest Point → Evaluate Surface → Normal), "
            "and normal-based extrusion (Move + Extrude Point). "
            "It's the complete beginner course workflow applied to an architectural facade design."
        ),
        "components": ["Point", "Ellipse", "Linear Array", "Unit Z", "Gene Pool", "Rotate", "Scale",
                        "Area", "Loft", "Diamond Panels", "Custom Preview", "Surface Closest Point",
                        "Evaluate Surface", "Amplitude", "Vector Display", "Multiplication", "Move",
                        "Extrude Point", "Number Slider", "Panel", "Surface", "Curve"],
        "keywords": ["final project", "panelized tower", "normal extrusion", "diamond panels", "facade",
                      "surface normal", "architectural design", "complete workflow", "culmination"],
        "tags": ["beginner", "culmination", "applied-project", "panelized-facade", "normal-extrusion",
                 "diamond-panels", "architectural", "full-workflow"],
        "trigger_intents": [
            "panelized tower grasshopper", "diamond panels with normal extrusion",
            "architectural facade workflow", "complete beginner project",
            "panels extruded along surface normals", "tower with panelized facade"
        ],
    },
]


def build_note(lesson: dict) -> dict:
    """Build a KnowledgeNote dict from extracted lesson data."""
    image = lesson["image"]
    note_id = stable_id(image)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Determine lesson number from image name
    lesson_num = int(image.split("-")[0])
    lesson_labels = {1: "Data Fundamentals", 2: "Curves Tangents and Data Trees", 3: "Applied Projects"}
    category_label = lesson_labels.get(lesson_num, f"Lesson {lesson_num}")

    return {
        "note_id": note_id,
        "note_type": "teaching",
        "name": f"Beginner {image}: {lesson['name']}",
        "brief": lesson["brief"],
        "version": "1.0",
        "created": now,
        "context": lesson["context"],
        "keywords": lesson["keywords"],
        "category": f"Beginner - {category_label}",
        "tags": lesson["tags"] + ["tutorial", "visual-course", "beginner-to-advanced"],
        "trigger_intents": lesson["trigger_intents"],
        "trigger_symptoms": [],
        "components": lesson["components"],
        "solution_principle": lesson["solution_principle"],
        "anti_patterns": [],
        "preconditions": [],
        "postconditions": [],
        "links": [],  # Will be populated by deterministic evolution
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
    parser = argparse.ArgumentParser(description="Extract teaching notes from Beginner tutorial images")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    print(f"Beginner Tutorial Extraction")
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
            # Check if content changed
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("brief") == note["brief"] and existing.get("context") == note["context"]:
                print(f"  SKIP  {note_id} ({lesson['image']}) — unchanged")
                skipped += 1
                continue
            else:
                # Preserve links and usage stats from existing
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

        # Run deterministic linking
        print("Running deterministic evolution (linking)...")
        from rook.learning.knowledge_evolution import KnowledgeEvolution
        evo = KnowledgeEvolution()
        link_count = 0
        for note in tutorial_notes:
            new_links = evo.link(note, store)
            link_count += len(new_links)
        print(f"  Created {link_count} links for {len(tutorial_notes)} tutorial notes")

        # Save
        store.save()
        print(f"  Store saved. Index rebuilt.")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
