#!/usr/bin/env python3
"""
Extract teaching knowledge from Intermediate tutorial images.

These images are from a standalone visual GH course with no .gh files.
Teaching data was extracted by visual inspection of each image.

Each image contains 1-4 clusters that may represent:
- "single": One definition teaching a concept
- "alternatives": Multiple approaches to the same goal
- "comparison": Side-by-side showing why one approach is better
- "progression": Building from simple to complex
- "culmination": Full pipeline combining prior lessons

Usage:
    python run_extract_intermediate_tutorials.py [--dry-run]
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
SOURCE = "intermediate_tutorial_visual"
COURSE = "BeginnerToAdvanced"
LEVEL = "Intermediate"

def stable_id(image_name: str) -> str:
    """Generate stable note ID from image name."""
    raw = f"{COURSE}:{LEVEL}:{image_name}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"tutorial_{h}"


# ============================================================
# EXTRACTED TEACHING DATA (from visual inspection of 28 images)
# ============================================================

LESSONS = [
    # ── LESSON 3: Attraction Algorithms ──
    {
        "image": "3-10",
        "name": "Point Attractor — Distance-Based Circle Sizing",
        "cluster_type": "single",
        "brief": "Point attractor pattern: Grid points → Distance to attractor → Bounds → Remap Numbers (2.5 to 5) → Circle radius. Distance-based sizing.",
        "context": (
            "Title: 'Attraction Algorithm'. "
            "Grid of points (from referenced geometry). Attractor Point param defines the attractor location. "
            "Line component connects each grid point to the attractor. "
            "Distance component measures the length of each line. "
            "Bounds component finds the min/max range of all distances. "
            "Remap Numbers: Source domain from Bounds, Target domain '2.5 to 5' (from Construct Domain with Number Sliders). "
            "Remapped values → Circle Radius input, with grid points as Circle Plane input. "
            "Result: circles whose radius varies based on distance from the attractor point. "
            "Closer to attractor = smaller radius (2.5), farther = larger (5), or vice versa depending on remap direction."
        ),
        "solution_principle": (
            "The attractor pattern is: 1) Measure distance from each element to attractor, "
            "2) Find the range of all distances (Bounds), "
            "3) Remap distances to desired output range (Remap Numbers), "
            "4) Use remapped values as geometry parameters (radius, height, scale, etc.). "
            "Bounds+Remap Numbers together normalize any distance range to your desired output range. "
            "This is the foundational attractor algorithm in Grasshopper."
        ),
        "components": ["Point", "Line", "Distance", "Bounds", "Remap Numbers", "Construct Domain", "Circle", "Number Slider"],
        "keywords": ["attractor", "distance", "remap numbers", "bounds", "circle sizing", "point attractor", "parametric variation"],
        "tags": ["intermediate", "attractor", "remap", "distance", "parametric-variation", "fundamentals"],
        "trigger_intents": [
            "point attractor grasshopper", "distance based sizing",
            "remap numbers bounds", "attractor circle radius",
            "how to create attractor pattern", "distance remap pattern"
        ],
    },
    {
        "image": "3-11",
        "name": "Curve Attractor — Distance-Based Scaling with Loft",
        "cluster_type": "single",
        "brief": "Curve attractor: Distance to curve → Bounds → Remap (0.95 to 0.2) → Scale at Area centroid → Entwine → Flip Matrix → Loft",
        "context": (
            "Extends the attractor concept to a Curve attractor instead of a Point. "
            "Grid of surfaces/panels. Curve param is the attractor shape. "
            "Distance measures from each panel's Area centroid to the curve. "
            "Bounds → Remap Numbers with target domain '0.95 to 0.2' (inverting: closer panels scale DOWN to 0.2). "
            "Scale component: Geometry=panels, Center=Area centroid, Factor=remapped distance. "
            "Scaled panels → Entwine → Flip Matrix → Loft → Custom Preview. "
            "The Entwine → Flip Matrix → Loft chain creates lofted surfaces between corresponding panels."
        ),
        "solution_principle": (
            "Curve attractors use the same Distance → Bounds → Remap pattern but with a Curve reference instead of a Point. "
            "Inverting the remap range (0.95 to 0.2) means closer elements get SMALLER values. "
            "Scale at Area centroid ensures panels scale from their own centers, not from origin. "
            "Entwine → Flip Matrix → Loft is the standard pattern for creating surfaces between organized panel sets."
        ),
        "components": ["Curve", "Distance", "Bounds", "Remap Numbers", "Construct Domain", "Area", "Scale",
                        "Entwine", "Flip Matrix", "Loft", "Custom Preview", "Number Slider"],
        "keywords": ["curve attractor", "scale at centroid", "remap inverse", "entwine flip matrix loft", "panel scaling"],
        "tags": ["intermediate", "attractor", "curve-attractor", "scale", "loft", "entwine-flip-loft"],
        "trigger_intents": [
            "curve attractor grasshopper", "scale panels by distance to curve",
            "entwine flip matrix loft pattern", "distance based panel scaling",
            "attractor with curve reference", "scale at centroid pattern"
        ],
    },
    {
        "image": "3-12",
        "name": "Curve Attractor — Distance-Based Extrusion Height",
        "cluster_type": "single",
        "brief": "Curve attractor driving extrusion: Distance → Remap (1 to 6) → Unit Z → Extrude → Cap Holes. Height varies by distance to attractor curve.",
        "context": (
            "Same attractor pattern but driving extrusion height instead of scale. "
            "Grid panels with Curve attractor. "
            "Distance → Bounds → Remap Numbers with target '1 to 6'. "
            "Remapped values → Unit Z (Factor) → creates vectors of varying height. "
            "Extrude component (highlighted green): Base=panels, Direction=Unit Z vectors → Extrusion output. "
            "Cap Holes: closes open ends of extrusions to create solids. "
            "→ Custom Preview. "
            "Result: a field of extruded panels whose height varies based on proximity to the attractor curve."
        ),
        "solution_principle": (
            "The attractor remap output can drive ANY parameter — not just scale. "
            "Here it drives Unit Z Factor to create varying extrusion heights. "
            "Extrude takes a Base surface and Direction vector. "
            "Cap Holes converts open extrusions into closed Breps (solids). "
            "This pattern — remap to Unit Z to Extrude — is the standard height-field approach."
        ),
        "components": ["Curve", "Distance", "Bounds", "Remap Numbers", "Construct Domain",
                        "Unit Z", "Extrude", "Cap Holes", "Custom Preview", "Number Slider"],
        "keywords": ["extrusion height", "attractor extrude", "unit z factor", "cap holes", "height field", "varying extrusion"],
        "tags": ["intermediate", "attractor", "extrude", "height-field", "cap-holes", "unit-z"],
        "trigger_intents": [
            "attractor extrusion height", "distance based extrusion",
            "remap to extrude height", "unit z varying height",
            "height field from attractor", "extrude panels by distance"
        ],
    },
    {
        "image": "3-13",
        "name": "Attractor with Scale AND Twist — Two Remap Channels",
        "cluster_type": "single",
        "brief": "Two Remap Numbers from same distance: one drives Scale factor, another drives Twist angle (0 to 90). Scale → Extrude → Line SDL → Twist.",
        "context": (
            "Extends attractor concept to TWO simultaneous parameters from the same distance measurement. "
            "Distance to attractor curve → Bounds. "
            "Remap Numbers #1: target domain for scale factor. "
            "Remap Numbers #2: target domain '0 to 90' for twist angle. "
            "Scale: resizes panels by distance-driven factor at Area centroid. "
            "Extrude: creates solids from scaled panels using Unit Z. "
            "Line SDL (Start, Direction, Length): creates twist axis at each panel centroid along Z. "
            "Twist (Geometry, Axis, Angle): twists the extruded solid by the second remapped value. "
            "Boolean Toggle controls whether twist is applied. "
            "Result: panels that are both scaled and twisted based on attractor distance."
        ),
        "solution_principle": (
            "A single Distance measurement can drive MULTIPLE Remap Numbers with different target domains. "
            "Each remapped output controls a different parameter (scale factor, twist angle, etc.). "
            "Line SDL creates the axis line needed for Twist deformation. "
            "This multi-channel remap pattern is the key to rich attractor-driven designs."
        ),
        "components": ["Curve", "Distance", "Bounds", "Remap Numbers", "Construct Domain", "Area",
                        "Scale", "Unit Z", "Extrude", "Line SDL", "Twist", "Boolean Toggle",
                        "Custom Preview", "Number Slider"],
        "keywords": ["multi-channel remap", "scale and twist", "two parameters", "line sdl", "twist deformation",
                      "attractor multi-parameter"],
        "tags": ["intermediate", "attractor", "multi-channel", "twist", "scale", "line-sdl", "advanced-attractor"],
        "trigger_intents": [
            "attractor scale and twist", "two remap from same distance",
            "multi parameter attractor", "twist by attractor distance",
            "line sdl twist axis", "distance drives multiple parameters"
        ],
    },
    {
        "image": "3-14",
        "name": "Three-Channel Attractor — Scale, Height, and Twist",
        "cluster_type": "progression",
        "brief": "Three Remap Numbers: scale (0.7→0.4), height (1→4), twist (0→90). Full attractor with scale + variable extrusion + twist.",
        "context": (
            "Extends 3-13 with THREE separate Remap Numbers channels from the same distance measurement. "
            "Remap #1: target '0.7 to 0.4' — scale factor (closer=smaller). "
            "Remap #2: target '1 to 4' — extrusion height (closer=shorter, farther=taller). "
            "Remap #3: target '0 to 90' — twist angle. "
            "Pipeline: Scale (at centroid) → Extrude (Unit Z with remapped height) → Twist (with Line SDL axis, remapped angle). "
            "Each parameter independently controlled by its own Remap Numbers but sharing the same distance source. "
            "Result: complex attractor-driven form where panels near the curve are small/short/twisted less, "
            "panels far from the curve are large/tall/twisted more."
        ),
        "solution_principle": (
            "Three-channel remap extends the multi-parameter attractor to maximum expressiveness. "
            "Each Remap Numbers component has its own target domain controlling one geometric parameter. "
            "The shared distance source ensures all parameters are correlated — creating a coherent spatial gradient. "
            "This is the standard approach for rich attractor-driven parametric facades."
        ),
        "components": ["Curve", "Distance", "Bounds", "Remap Numbers", "Construct Domain", "Area",
                        "Scale", "Unit Z", "Extrude", "Line SDL", "Twist", "Custom Preview", "Number Slider"],
        "keywords": ["three channel remap", "scale height twist", "multi-parameter attractor",
                      "spatial gradient", "parametric facade", "attractor variation"],
        "tags": ["intermediate", "progression", "attractor", "three-channel", "facade", "spatial-gradient"],
        "trigger_intents": [
            "three parameter attractor", "scale height twist from distance",
            "full attractor pipeline", "spatial gradient facade",
            "rich attractor-driven form", "three remap channels"
        ],
    },
    {
        "image": "3-15",
        "name": "Multiple Attractors — Merge + Pull Point for Closest Distance",
        "cluster_type": "single",
        "brief": "Multiple attractors: Merge (Point + Curve) → Pull Point → shortest distance from each panel to ANY attractor → Remap → Scale → Entwine → Flip Matrix → Loft",
        "context": (
            "Uses MULTIPLE attractor sources combined via Merge. "
            "Point param (point attractor) + Curve param (curve attractor) → Merge. "
            "Pull Point: finds closest point on merged attractors to each panel centroid. Returns Closest Point + Distance. "
            "Pull Point automatically selects the NEAREST of all merged attractors per panel. "
            "Distance → Bounds → Remap Numbers with target '0.2 to 0.95'. "
            "Scale: at Area centroid with remapped factor. "
            "Scaled panels → Entwine → Flip Matrix → Loft → Custom Preview. "
            "Result: panels respond to WHICHEVER attractor is closest, creating a complex influence field."
        ),
        "solution_principle": (
            "Merge multiple attractor geometries (points, curves, surfaces) into one set. "
            "Pull Point finds the closest point across ALL merged attractors — automatically selecting the nearest one. "
            "This creates a multi-source influence field without needing conditional logic. "
            "The rest of the pipeline (Remap → Scale → Entwine → Flip Matrix → Loft) is the same standard pattern."
        ),
        "components": ["Point", "Curve", "Merge", "Pull Point", "Distance", "Bounds", "Remap Numbers",
                        "Construct Domain", "Area", "Scale", "Entwine", "Flip Matrix", "Loft",
                        "Custom Preview", "Number Slider"],
        "keywords": ["multiple attractors", "merge attractors", "pull point", "closest distance", "influence field",
                      "multi-source attractor"],
        "tags": ["intermediate", "attractor", "multiple-attractors", "pull-point", "merge", "influence-field"],
        "trigger_intents": [
            "multiple attractors grasshopper", "merge point and curve attractor",
            "pull point closest distance", "multi-source attractor",
            "combined attractor influence", "nearest attractor pattern"
        ],
    },
    {
        "image": "3-16",
        "name": "Hexagonal Panelization with Normal Extrusion — Hex Cells Attractor",
        "cluster_type": "single",
        "brief": "Hexagon Cells (U=35,V=25) → Surface Closest Point → Evaluate Surface → Normal → Amplitude (Remap: -0.05 to -1.5) → Move + Extrude Point → Custom Preview",
        "context": (
            "Hexagonal panelization with attractor-driven normal extrusion. "
            "Surface param → Hexagon Cells (LunchBox plugin, U=35, V=25). Creates hexagonal panels on surface. "
            "Point attractor for driving variation. "
            "Area centroids of hex panels → Surface Closest Point → Evaluate Surface → Normal vectors. "
            "Distance from centroids to attractor → Bounds → Remap Numbers target '-0.05 to -1.5'. "
            "Negative values make the panels extrude INWARD. "
            "Amplitude: scales normal vectors by remapped distance values. "
            "Move: offsets panel centroids along scaled normals. "
            "Extrude Point: extrudes hex panels toward offset points. "
            "→ Custom Preview. "
            "Result: hex-panelized surface with inward extrusions varying by attractor distance."
        ),
        "solution_principle": (
            "Hexagon Cells (from LunchBox plugin) creates hexagonal panelization on a surface. "
            "Surface Closest Point → Evaluate Surface → Normal gives per-panel surface normal vectors. "
            "Negative Remap target values create inward extrusions (into the surface). "
            "Combining panelization + attractor + normal extrusion creates parametric facade effects. "
            "This pattern works with any panel type (hex, quad, diamond, triangle)."
        ),
        "components": ["Surface", "Hexagon Cells", "Point", "Area", "Surface Closest Point", "Evaluate Surface",
                        "Distance", "Bounds", "Remap Numbers", "Construct Domain", "Amplitude", "Move",
                        "Extrude Point", "Custom Preview", "Number Slider"],
        "keywords": ["hexagon cells", "hex panelization", "normal extrusion", "attractor facade", "lunchbox",
                      "inward extrusion", "surface normal"],
        "tags": ["intermediate", "panelization", "hexagon", "attractor", "normal-extrusion", "facade", "lunchbox"],
        "trigger_intents": [
            "hexagonal panelization", "hex cells attractor",
            "normal extrusion panels", "inward extrusion surface",
            "hexagon cells lunchbox", "hex panel facade attractor"
        ],
    },
    {
        "image": "3-17",
        "name": "Quad Panel Attractor with Scale and Normal Move — Two Pull Points",
        "cluster_type": "single",
        "brief": "Quad Panels (25x25) + two Pull Point attractors with different Remap targets (0.2-0.7 and 0.5-2) → Scale + Normal Move → Entwine → Flip Matrix → Loft",
        "context": (
            "Complex quad panel attractor with TWO separate Pull Point attractor sources and two effect channels. "
            "Surface → Quad Panels (25×25). "
            "Two separate Pull Point attractor sources (two Point params at different locations). "
            "Pull Point #1 → Distance → Bounds → Remap (target '0.2 to 0.7') → Scale at Area centroid. "
            "Pull Point #2 → Distance → Bounds → Remap (target '0.5 to 2') → Amplitude of surface Normal. "
            "Area centroids → Surface Closest Point → Evaluate Surface → Normal → Amplitude (driven by Remap #2). "
            "Move: offsets panels along scaled normals. "
            "Scaled+Moved panels → Entwine → Flip Matrix → Loft → Custom Preview. "
            "Two attractors drive two different parameters (scale and normal offset) independently."
        ),
        "solution_principle": (
            "Multiple independent attractors can each drive a DIFFERENT geometric parameter. "
            "Attractor 1 → Remap → Scale factor. Attractor 2 → Remap → Normal offset magnitude. "
            "This creates a rich parametric field where two spatial gradients interact. "
            "Quad Panels provides regular grid panelization. "
            "The Entwine → Flip Matrix → Loft pattern converts panel sets into a lofted surface."
        ),
        "components": ["Surface", "Quad Panels", "Point", "Pull Point", "Distance", "Bounds", "Remap Numbers",
                        "Construct Domain", "Area", "Scale", "Surface Closest Point", "Evaluate Surface",
                        "Amplitude", "Move", "Entwine", "Flip Matrix", "Loft", "Custom Preview", "Number Slider"],
        "keywords": ["quad panels", "two attractors", "independent parameters", "scale and normal offset",
                      "dual attractor", "parametric field"],
        "tags": ["intermediate", "attractor", "dual-attractor", "quad-panels", "scale", "normal-offset", "complex-field"],
        "trigger_intents": [
            "two attractors different parameters", "dual point attractor",
            "quad panel scale and normal", "independent attractor channels",
            "two pull points grasshopper", "complex attractor field"
        ],
    },

    # ── LESSON 4: Surface Creation, List Operations, Filtering ──
    {
        "image": "4-1",
        "name": "Surface Creation Alternatives — Boundary, Loft, Network Surface, Patch Surface",
        "cluster_type": "alternatives",
        "brief": "Four surface creation methods: Curve→Surface, Boundary Surfaces, Network Surface (U+V curves), Patch Surface (tolerance=35) → Custom Preview",
        "context": (
            "Four clusters showing alternative surface creation approaches. "
            "Cluster 1: Curve param → Surface (direct, for simple closed curves). "
            "Cluster 2: Boundary Surfaces — creates planar fill from closed boundary edges. "
            "Cluster 3: Network Surface — takes Curves U (one direction) + Curves V (perpendicular direction) → Surface. "
            "Requires curves in TWO directions forming a network grid. "
            "Cluster 4: Patch Surface — creates a smooth surface approximation from curves/points. "
            "Tolerance slider (~35) controls how closely the patch follows input geometry. "
            "All outputs → Custom Preview for comparison. "
            "Shows when each method is appropriate based on input geometry type."
        ),
        "solution_principle": (
            "Surface choice depends on input: "
            "Direct Surface: closed planar curves only. "
            "Boundary Surfaces: closed curves needing planar fill. "
            "Network Surface: when you have curves in TWO perpendicular directions (U and V). "
            "Patch Surface: when you have scattered curves/points and need an approximation (tolerance-controlled). "
            "Network Surface is the most controlled (exact interpolation), Patch is the most flexible (approximate fit)."
        ),
        "components": ["Curve", "Surface", "Boundary Surfaces", "Network Surface", "Patch Surface",
                        "Custom Preview", "Number Slider"],
        "keywords": ["surface creation", "boundary surfaces", "network surface", "patch surface", "surface alternatives",
                      "tolerance", "u v curves"],
        "tags": ["intermediate", "alternatives", "surface-creation", "network-surface", "patch-surface", "boundary-surfaces"],
        "trigger_intents": [
            "surface creation methods intermediate", "network surface u v curves",
            "patch surface tolerance", "boundary surface vs network surface",
            "which surface method to use", "surface creation alternatives"
        ],
    },
    {
        "image": "4-2",
        "name": "Iso Curves and Network Surface — MD Slider vs Range-Generated",
        "cluster_type": "alternatives",
        "brief": "Two approaches: Iso Curve with MD Sliders → Network Surface (manual control), vs Range → Vector XYZ → Iso Curve → Rebuild Curve → Network Surface (parametric)",
        "context": (
            "Two clusters showing different approaches to creating Network Surfaces from Iso Curves. "
            "Top cluster: Iso Curve component with MD Sliders (2D slider providing UV coordinates). "
            "Multiple Iso Curves at manually positioned UV locations → Network Surface. "
            "Direct, manual control over iso curve placement. "
            "Bottom cluster: Range component generates evenly spaced parameters. "
            "Range → Vector XYZ → generates UV coordinates systematically. "
            "Iso Curve extracts curves at each generated UV parameter. "
            "Rebuild Curve: adjusts the curve degree/control points for better surface fitting. "
            "Rebuilt iso curves → Network Surface. "
            "Parametric, adjustable approach using Range for systematic iso curve extraction."
        ),
        "solution_principle": (
            "Iso Curve extracts curves from a surface at specific UV parameters. "
            "MD Slider gives visual 2D control but is manual. "
            "Range generates systematic, evenly-spaced parameters — better for repeatable, adjustable results. "
            "Rebuild Curve may be needed to make iso curves compatible for Network Surface (matching degree/knots). "
            "Range-based extraction is the preferred parametric approach."
        ),
        "components": ["Surface", "Iso Curve", "MD Slider", "Range", "Vector XYZ", "Rebuild Curve",
                        "Network Surface", "Number Slider", "Panel"],
        "keywords": ["iso curve", "network surface", "md slider", "range generation", "rebuild curve",
                      "uv extraction", "parametric iso curves"],
        "tags": ["intermediate", "alternatives", "iso-curve", "network-surface", "rebuild-curve", "parametric-extraction"],
        "trigger_intents": [
            "iso curve from surface", "network surface from iso curves",
            "range generated iso curves", "rebuild curve for network surface",
            "md slider iso curve", "extract iso curves parametrically"
        ],
    },
    {
        "image": "4-3",
        "name": "Shatter Curve — Split and Pipe Segments",
        "cluster_type": "single",
        "brief": "Shatter curve at Range parameters → List Item to select segments → Pipe (radius slider) → Cap Holes. Splitting curves into segments.",
        "context": (
            "Single definition showing curve segmentation. "
            "Curve param → Shatter component (Curve, Parameters from Range output). "
            "Range generates evenly spaced parameter values along the curve. "
            "Shatter splits the curve at those parameters into individual segments. "
            "List Item: selects specific segments from the shattered curve list by index. "
            "Selected segments → Pipe component (Curve, Radius from slider) → creates tubular geometry. "
            "Cap Holes: closes the open ends of pipes. "
            "Demonstrates how to work with individual curve segments after splitting."
        ),
        "solution_principle": (
            "Shatter splits a curve at specified parameter values into separate segments. "
            "Range generates the split parameters (evenly spaced). "
            "List Item selects specific segments by index for individual processing. "
            "Pipe creates tubular geometry from curves — radius controls thickness. "
            "Cap Holes closes open Brep ends. "
            "This Shatter → select → process pattern is fundamental for working with curve segments."
        ),
        "components": ["Curve", "Range", "Shatter", "List Item", "Pipe", "Cap Holes", "Number Slider"],
        "keywords": ["shatter curve", "split curve", "pipe", "list item", "curve segments", "cap holes"],
        "tags": ["intermediate", "curve-operations", "shatter", "pipe", "list-item", "segmentation"],
        "trigger_intents": [
            "shatter curve into segments", "split curve at parameters",
            "pipe from curve segment", "list item select segment",
            "curve segmentation grasshopper", "shatter range pipe pattern"
        ],
    },
    {
        "image": "4-4",
        "name": "Cull Pattern and Dispatch — Boolean List Filtering",
        "cluster_type": "single",
        "brief": "Cull Pattern with boolean patterns (True/False) to filter lists. Also Dispatch for splitting into two outputs. Polygon and Circle at filtered points.",
        "context": (
            "Demonstrates boolean-based list filtering operations. "
            "Cull Pattern: takes a List and a boolean Pattern (True/False values). "
            "True items are kept, False items are removed. "
            "Panel shows boolean data patterns being used. "
            "Dispatch: similar to Cull Pattern but splits into TWO output lists (List A = True items, List B = False items). "
            "Both filtered lists used to create geometry: "
            "Polygon component at True-filtered points. "
            "Circle component at other points (or vice versa). "
            "Shows how boolean patterns control which elements receive which geometry."
        ),
        "solution_principle": (
            "Cull Pattern removes items where the pattern is False — filters to ONE output. "
            "Dispatch splits items into TWO outputs based on the pattern — nothing is lost. "
            "Boolean patterns can be manually defined or generated by comparison components. "
            "This is the foundation for selective geometry creation — different geometry at different points."
        ),
        "components": ["Cull Pattern", "Dispatch", "Polygon", "Circle", "Panel", "Point"],
        "keywords": ["cull pattern", "dispatch", "boolean filter", "list filtering", "true false", "selective geometry"],
        "tags": ["intermediate", "list-operations", "cull-pattern", "dispatch", "boolean-filtering"],
        "trigger_intents": [
            "cull pattern grasshopper", "dispatch true false",
            "boolean list filtering", "filter points by pattern",
            "cull pattern vs dispatch", "selective geometry creation"
        ],
    },
    {
        "image": "4-5",
        "name": "Conditional Statements — Boolean Logic for Filtering",
        "cluster_type": "single",
        "brief": "Conditional algorithms using boolean logic: comparison operators generate True/False patterns for filtering geometry through Cull Pattern.",
        "context": (
            "Demonstrates conditional statement patterns in Grasshopper using boolean operations. "
            "Multiple filtering stages using comparison operators (Larger Than, Smaller Than, Equality). "
            "Comparison outputs generate boolean (True/False) patterns. "
            "These boolean patterns feed into Cull Pattern or Dispatch to filter geometry. "
            "Shows how mathematical conditions translate to geometric selection. "
            "Multiple levels of conditional filtering can be chained for complex selection logic."
        ),
        "solution_principle": (
            "Conditional logic in Grasshopper uses comparison components that output boolean values. "
            "Larger Than, Smaller Than, Equality produce True/False for each element. "
            "These booleans feed Cull Pattern or Dispatch for filtering. "
            "Chaining comparisons creates multi-criteria selection. "
            "This replaces 'if statements' from text programming."
        ),
        "components": ["Larger Than", "Smaller Than", "Equality", "Cull Pattern", "Dispatch",
                        "Number Slider", "Panel"],
        "keywords": ["conditional", "boolean logic", "comparison", "larger than", "filter chain",
                      "conditional algorithm", "multi-criteria"],
        "tags": ["intermediate", "boolean-logic", "conditional", "comparison", "filtering", "algorithm"],
        "trigger_intents": [
            "conditional logic grasshopper", "boolean comparison filter",
            "larger than smaller than", "if statement grasshopper",
            "conditional filtering", "comparison operators grasshopper"
        ],
    },
    {
        "image": "4-6",
        "name": "Point in Curves — Geometric Containment Test",
        "cluster_type": "single",
        "brief": "Point in Curves → Equality → Cull Pattern → Circle. Tests whether points are inside closed curves for spatial filtering.",
        "context": (
            "Demonstrates geometric containment testing. "
            "Grid of Points. Closed Curve references (regions). "
            "Point in Curves: tests whether each point falls inside the closed curve(s). "
            "Returns relationship values (0=outside, 1=inside, 2=on boundary). "
            "Equality: compares against 1 (inside) to produce boolean True/False. "
            "Cull Pattern: filters points to only those INSIDE the curves. "
            "Circle: creates circles at the filtered (inside) points. "
            "Custom Preview shows circles only within the curve boundaries."
        ),
        "solution_principle": (
            "Point in Curves (or Point in Curve) tests geometric containment — is a point inside a closed curve? "
            "Returns 0 (outside), 1 (inside), 2 (coincident/on boundary). "
            "Equality comparison converts the result to boolean for Cull Pattern. "
            "This enables region-based geometry filtering — only create geometry where points are inside specific areas."
        ),
        "components": ["Point", "Curve", "Point in Curves", "Equality", "Cull Pattern", "Circle",
                        "Custom Preview", "Panel"],
        "keywords": ["point in curve", "containment test", "inside outside", "region filter",
                      "geometric containment", "spatial selection"],
        "tags": ["intermediate", "containment", "point-in-curve", "boolean-filtering", "spatial-selection"],
        "trigger_intents": [
            "point in curves test", "is point inside curve",
            "geometric containment grasshopper", "filter points inside region",
            "point containment test", "region based filtering"
        ],
    },
    {
        "image": "4-7",
        "name": "Boolean Gates — Gate AND vs Gate OR for Spatial Filtering",
        "cluster_type": "comparison",
        "brief": "Two clusters: Gate And vs Gate Or. Deconstruct Point → X,Y → Larger Than → Gate And/Or → Cull Pattern → Circle. Shows AND vs OR logic difference.",
        "context": (
            "Side-by-side comparison of AND vs OR boolean logic for spatial filtering. "
            "Both clusters start with grid of Points → Deconstruct Point → X and Y coordinates. "
            "Larger Than: compares X and Y against threshold values. Produces two boolean lists. "
            "Left cluster: Gate And — BOTH conditions must be True (X > threshold AND Y > threshold). "
            "Selects only points in the upper-right quadrant. "
            "Right cluster: Gate Or — EITHER condition can be True (X > threshold OR Y > threshold). "
            "Selects points in three quadrants (upper-left + upper-right + lower-right). "
            "Both → Cull Pattern → Circle → Custom Preview. "
            "Visually demonstrates the difference between AND (intersection) and OR (union) logic."
        ),
        "solution_principle": (
            "Gate And requires ALL boolean inputs to be True (logical intersection). "
            "Gate Or requires ANY boolean input to be True (logical union). "
            "Deconstruct Point separates X,Y,Z for individual coordinate comparisons. "
            "This pattern — decompose → compare → combine boolean logic → filter — enables complex spatial selection criteria."
        ),
        "components": ["Point", "Deconstruct Point", "Larger Than", "Gate And", "Gate Or",
                        "Cull Pattern", "Circle", "Custom Preview", "Number Slider"],
        "keywords": ["gate and", "gate or", "boolean gate", "and vs or", "spatial filtering",
                      "deconstruct point", "logical intersection", "logical union"],
        "tags": ["intermediate", "comparison", "boolean-logic", "gate-and", "gate-or", "spatial-filtering"],
        "trigger_intents": [
            "gate and vs gate or", "boolean and or grasshopper",
            "spatial filtering with logic gates", "and intersection or union",
            "deconstruct point filter coordinates", "combine boolean conditions"
        ],
    },
    {
        "image": "4-8",
        "name": "Dispatch for Alternating Geometry — Circle vs Polygon at Division Points",
        "cluster_type": "single",
        "brief": "Divide Curve → Dispatch with pattern (1,0) → List A → Circle, List B → Polygon. Alternating geometry types at division points.",
        "context": (
            "Demonstrates Dispatch for creating alternating geometry patterns. "
            "Curve → Divide Curve (Number from slider) → Division Points. "
            "Dispatch: Pattern '1,0' (alternating True/False). "
            "List A (True items, odd indices) → Circle component. "
            "List B (False items, even indices) → Polygon component. "
            "Result: alternating circles and polygons along the divided curve. "
            "The Dispatch pattern '1,0' creates a simple alternating selection. "
            "Pattern '1,0,0' would select every third item, etc."
        ),
        "solution_principle": (
            "Dispatch with a repeating boolean pattern creates alternating selections from a list. "
            "Pattern '1,0' alternates: item 0 → List A, item 1 → List B, item 2 → List A, etc. "
            "This enables different geometry types at alternating positions. "
            "The pattern repeats cyclically — '1,0,0' gives every-third-item selection."
        ),
        "components": ["Curve", "Divide Curve", "Dispatch", "Circle", "Polygon", "Number Slider", "Panel"],
        "keywords": ["dispatch alternating", "alternating geometry", "boolean pattern", "circle polygon",
                      "cyclic dispatch", "divide curve dispatch"],
        "tags": ["intermediate", "dispatch", "alternating-pattern", "divide-curve", "geometry-variation"],
        "trigger_intents": [
            "alternating geometry along curve", "dispatch pattern 1 0",
            "circle and polygon alternating", "dispatch cyclic pattern",
            "different geometry at alternating points", "dispatch for variation"
        ],
    },
    {
        "image": "4-9",
        "name": "Dispatch for Alternating Pipe Sizes — Different Radii per Segment",
        "cluster_type": "single",
        "brief": "Shatter → Dispatch (pattern 0,1,1) → two Pipe components with radii 1.3 vs 2.6. Alternating thick and thin pipes along shattered curve.",
        "context": (
            "Extends Dispatch concept to curve segment processing. "
            "Curve → Shatter (at parameters) → Segments. "
            "Dispatch with pattern '0,1,1' (1 thin, 2 thick repeating). "
            "List A (pattern=0 items) → Pipe (Radius=1.3, thin). "
            "List B (pattern=1 items) → Pipe (Radius=2.6, thick). "
            "Additional Curve reference piped with yet another radius. "
            "Result: shattered curve with alternating thin and thick pipe segments. "
            "Pattern '0,1,1' means every third segment is thin, the other two are thick."
        ),
        "solution_principle": (
            "Dispatch pattern '0,1,1' creates a 1:2 alternation ratio (one thin, two thick). "
            "Different Pipe radii on each Dispatch output create visual/structural variation. "
            "Shatter + Dispatch + different processing per output is a powerful pattern for varied repetition. "
            "The pattern can be any boolean sequence for complex rhythms."
        ),
        "components": ["Curve", "Shatter", "Dispatch", "Pipe", "Number Slider", "Panel", "Range"],
        "keywords": ["dispatch pipe sizes", "alternating thickness", "shatter dispatch", "varied pipe radius",
                      "segment processing", "boolean rhythm"],
        "tags": ["intermediate", "dispatch", "pipe", "shatter", "alternating-size", "segment-variation"],
        "trigger_intents": [
            "alternating pipe sizes", "shatter dispatch different radius",
            "varied thickness along curve", "dispatch pattern 0 1 1",
            "different pipe radius per segment", "rhythmic segment variation"
        ],
    },
    {
        "image": "4-10",
        "name": "Dispatch for Alternating Scale — Scale Up and Scale Down Segments",
        "cluster_type": "single",
        "brief": "Shatter → Dispatch → two Scale components (Subtraction/Addition for factors) → Ruled Surface. Alternating enlarged/reduced segments.",
        "context": (
            "Extends Dispatch to scale-based variation of curve segments. "
            "Curve → Shatter → Segments → Dispatch (pattern separates alternating segments). "
            "List A → Area (centroid) → Scale with factor from Subtraction (e.g. 1 - 0.2 = 0.8, scale down). "
            "List B → Area (centroid) → Scale with factor from Addition (e.g. 1 + 0.2 = 1.2, scale up). "
            "Scale Factor slider (e.g. 0.2) drives both Addition and Subtraction. "
            "Scaled segments from both lists → Ruled Surface (connects corresponding segments). "
            "Result: alternating enlarged and reduced curve segments with ruled surfaces between them."
        ),
        "solution_principle": (
            "Dispatch + dual processing (one path scales up, other scales down) creates rhythmic size variation. "
            "Using Addition/Subtraction with the same slider value ensures symmetric variation. "
            "Scale at Area centroid ensures segments scale from their own centers. "
            "Ruled Surface connects corresponding scaled segments to create a continuous surface."
        ),
        "components": ["Curve", "Shatter", "Dispatch", "Area", "Scale", "Subtraction", "Addition",
                        "Ruled Surface", "Number Slider", "Range"],
        "keywords": ["alternating scale", "scale up down", "dispatch scale", "ruled surface",
                      "addition subtraction", "symmetric variation"],
        "tags": ["intermediate", "dispatch", "scale", "alternating-size", "ruled-surface", "symmetric"],
        "trigger_intents": [
            "alternating scale segments", "dispatch scale up down",
            "symmetric scale variation", "ruled surface alternating",
            "shatter dispatch scale", "enlarge reduce alternating"
        ],
    },
    {
        "image": "4-11",
        "name": "Random Dispatch + Number Types — Random Pattern and Division/Integer/Round",
        "cluster_type": "alternatives",
        "brief": "Two clusters: Random (0-1) → Round → Dispatch pattern for random alternation + Scale → Ruled Surface. Bottom: Division vs Integer Division vs Integer vs Round comparison.",
        "context": (
            "Two distinct clusters. "
            "Top: Random-based Dispatch. Number Slider (count=38) → Range → Shatter. "
            "Panel '0 to 1' → Random component (Range, Number, Seed from slider=374). "
            "Panel shows random values (0.113, 0.556, 0.190, ...). "
            "Round (Nearest): rounds to 0 or 1 → creates random boolean pattern. "
            "Panel shows rounded values (0,1,0,0,0,0,0,0,0,1...). "
            "Random pattern → Dispatch → two paths with Scale (Subtraction/Addition factors, slider=0.45). "
            "Area centroids → Scale → Ruled Surface → Custom Preview. "
            "Result: randomly alternating enlarged/reduced segments. "
            "Bottom (purple background): Number type comparison. "
            "Two sliders (8, 3). Division: 8/3 = 2.666667. Integer Division: 8/3 = 2. "
            "Integer component: rounds to nearest integer (3). "
            "Round: Nearest=3, Floor=2, Ceiling=3. Shows different rounding behaviors."
        ),
        "solution_principle": (
            "Random (0-1) → Round creates random 0/1 boolean patterns for stochastic Dispatch. "
            "This replaces the fixed patterns (1,0 or 0,1,1) with randomized selection. "
            "Seed parameter makes the random pattern reproducible. "
            "Division vs Integer Division: regular gives decimal, Integer gives truncated integer. "
            "Round has three modes: Nearest, Floor (round down), Ceiling (round up)."
        ),
        "components": ["Number Slider", "Range", "Shatter", "Random", "Round", "Dispatch",
                        "Area", "Scale", "Subtraction", "Addition", "Ruled Surface", "Custom Preview",
                        "Division", "Integer Division", "Integer", "Panel"],
        "keywords": ["random dispatch", "random boolean pattern", "round", "integer division",
                      "stochastic", "seed", "number types", "floor ceiling"],
        "tags": ["intermediate", "alternatives", "random", "dispatch", "number-types", "round", "stochastic"],
        "trigger_intents": [
            "random dispatch pattern", "random boolean grasshopper",
            "round to 0 or 1", "integer division vs division",
            "stochastic geometry variation", "random alternating pattern"
        ],
    },
    {
        "image": "4-12",
        "name": "List Operation Alternatives — Five Colored Groups Comparing Methods",
        "cluster_type": "alternatives",
        "brief": "Five colored groups (purple, cyan, yellow, pink, tan) each showing a different list manipulation operation with panel outputs for comparison.",
        "context": (
            "Five distinctly colored groups showing different list operations side by side. "
            "Each group takes similar input data and applies a different list manipulation technique. "
            "Purple (top): basic list operation with panel output. "
            "Cyan: variation with additional list processing. "
            "Yellow: another list manipulation approach. "
            "Pink: list operation with different parameter. "
            "Tan/beige (bottom): final list operation variant. "
            "Each group shows input panels, the operation component, and output panels for comparison. "
            "Teaches the different list manipulation tools available and their distinct behaviors."
        ),
        "solution_principle": (
            "Grasshopper provides multiple list manipulation operations, each with distinct behavior. "
            "Comparing their outputs side-by-side with panels reveals how each transforms data differently. "
            "Understanding these differences is essential for correctly organizing data in complex definitions."
        ),
        "components": ["Panel", "List Item", "Number Slider"],
        "keywords": ["list operations", "list manipulation", "comparison", "data organization", "list alternatives"],
        "tags": ["intermediate", "alternatives", "list-operations", "data-manipulation", "comparison"],
        "trigger_intents": [
            "list operations comparison", "different list manipulations",
            "grasshopper list tools", "compare list operations",
            "data organization methods", "list manipulation alternatives"
        ],
    },
    {
        "image": "4-13",
        "name": "Sub List — Selecting Panel Ranges with Domain",
        "cluster_type": "alternatives",
        "brief": "Five Sub List operations with different domains (0-27, 14-27, 13-25, 42-81, 62-48) showing how domain ranges select different subsets of quad panels.",
        "context": (
            "Demonstrates Sub List component for range-based data selection. "
            "Quad Panels on a surface provide the input panel list. "
            "Five purple-highlighted groups, each with Sub List component using a different Domain: "
            "Sub List #1: Domain '0 to 27' — selects first 28 panels. "
            "Sub List #2: Domain '14 to 27' — selects middle range. "
            "Sub List #3: Domain '13 to 25' — similar middle range with different bounds. "
            "Sub List #4: Domain '42 to 81' — selects a later range. "
            "Sub List #5: Domain '62 to 48' — REVERSED domain (end < start) selects items in reverse order. "
            "Each Sub List → Quad Panels output → Custom Preview with different visualization. "
            "Shows how domain ranges control which subset of panels is selected."
        ),
        "solution_principle": (
            "Sub List extracts a contiguous range of items from a list using a Domain (start, end). "
            "Different domains select different panel subsets — useful for region-specific operations. "
            "Reversed domains (end < start) return items in reverse order. "
            "Sub List is more efficient than multiple List Item calls for extracting ranges."
        ),
        "components": ["Surface", "Quad Panels", "Sub List", "Construct Domain", "Custom Preview",
                        "Number Slider", "Panel"],
        "keywords": ["sub list", "range selection", "domain", "panel subset", "contiguous range",
                      "reversed domain", "region selection"],
        "tags": ["intermediate", "alternatives", "sub-list", "list-operations", "range-selection", "quad-panels"],
        "trigger_intents": [
            "sub list range grasshopper", "select range from list",
            "sub list domain", "panel subset selection",
            "extract contiguous range", "sub list reversed domain"
        ],
    },
    {
        "image": "4-14",
        "name": "Sub List Applied — Panel Selection with Image Sampler Pipeline",
        "cluster_type": "progression",
        "brief": "Extends Sub List: multiple panel range selections → processing pipeline with image sampling and surface operations for facade patterning.",
        "context": (
            "Builds on 4-13's Sub List concept with a more complex processing pipeline. "
            "Top section: Multiple purple groups with Sub List domain ranges (similar to 4-13) selecting different panel subsets. "
            "Each Sub List outputs to Quad Panels operations. "
            "Some groups include image/preview output components. "
            "Bottom section: Extended horizontal pipeline with many processing components. "
            "Includes image sampling, surface operations, and custom preview outputs. "
            "Demonstrates how Sub List range selection integrates into larger definition workflows."
        ),
        "solution_principle": (
            "Sub List enables region-specific processing within a larger definition. "
            "Different panel ranges can feed different processing pipelines. "
            "This pattern — select range → process → preview — enables selective facade treatments."
        ),
        "components": ["Surface", "Quad Panels", "Sub List", "Construct Domain", "Custom Preview",
                        "Number Slider", "Panel", "Image Sampler"],
        "keywords": ["sub list pipeline", "panel range processing", "facade patterning",
                      "image sampler", "selective processing"],
        "tags": ["intermediate", "progression", "sub-list", "image-sampler", "facade-pattern", "selective-processing"],
        "trigger_intents": [
            "sub list with processing pipeline", "panel range processing",
            "image sampler panels", "selective facade treatment",
            "sub list in complex definition", "range based panel processing"
        ],
    },
    {
        "image": "4-15",
        "name": "Image Sampler on Panels — Pixel Values Driving Geometry",
        "cluster_type": "progression",
        "brief": "Image Sampler component maps pixel brightness to panel parameters. Sub List selections + image-driven parameter variation for facade effect.",
        "context": (
            "Extends 4-14. Shows the Image Sampler component in detail. "
            "Top: Same Sub List panel range selections as 4-13/4-14. "
            "Bottom: Extended pipeline using Image Sampler. "
            "Image Sampler maps XY coordinates to pixel values from a referenced image. "
            "Pixel brightness/color → numeric values → drive geometry parameters (scale, extrusion, color). "
            "Panel centroids provide the XY coordinates for sampling. "
            "The pipeline connects panel positions to image-derived values to geometry operations. "
            "Result: panels whose properties are driven by an image — classic image-based facade patterning."
        ),
        "solution_principle": (
            "Image Sampler maps spatial (XY) coordinates to pixel values from an image file. "
            "The brightness/color at each panel's centroid position becomes a numeric driver. "
            "This enables image-driven parametric design — any image becomes a control surface. "
            "Common uses: facade pattern from image, topographic surfaces from heightmaps, "
            "gradient-based material assignment."
        ),
        "components": ["Surface", "Quad Panels", "Sub List", "Image Sampler", "Custom Preview",
                        "Number Slider", "Panel", "Area"],
        "keywords": ["image sampler", "pixel driven", "image based design", "facade pattern",
                      "brightness to parameter", "heightmap", "image control"],
        "tags": ["intermediate", "progression", "image-sampler", "facade", "pixel-driven", "parametric-image"],
        "trigger_intents": [
            "image sampler grasshopper", "pixel values drive geometry",
            "image based facade pattern", "brightness to parameter",
            "image driven design", "image sampler panel parameters"
        ],
    },
    {
        "image": "4-16",
        "name": "Complex Panelization Pipeline — Sub List, Repeat, Trim, Surfaces",
        "cluster_type": "culmination",
        "brief": "Green-themed complex definition: Sub List ranges → panel processing → Repeat/Trim/Extend → surface creation → Brep operations → Custom Preview. Combines many Lesson 4 concepts.",
        "context": (
            "Green-themed culmination of Lesson 4 concepts. Complex multi-stage definition. "
            "Left section: Multiple green groups with Sub List and Quad Panels at different domain ranges. "
            "Panel processing with various operations. "
            "Middle section: Intermediate processing with Cull/Selection operations. "
            "Right section: Complex assembly including: "
            "Repeat: duplicates elements. "
            "Trim/Extend: adjusts curve/surface boundaries. "
            "Surface creation: creates surfaces from processed curves. "
            "Brep operations: boolean or trimming operations on surfaces/solids. "
            "Custom Preview with color. "
            "This is a full applied pipeline combining Sub List, Dispatch, surface operations, and Brep operations."
        ),
        "solution_principle": (
            "Complex definitions combine multiple Lesson 4 concepts: "
            "Sub List for range selection, Dispatch for filtering, "
            "surface creation and Brep operations for geometry processing, "
            "Custom Preview for visualization. "
            "The green groups organize related operations visually. "
            "This pattern of composing simple operations into complex pipelines is the essence of advanced Grasshopper."
        ),
        "components": ["Surface", "Quad Panels", "Sub List", "Construct Domain", "Dispatch",
                        "Repeat", "Custom Preview", "Number Slider", "Panel", "Brep"],
        "keywords": ["complex pipeline", "sub list repeat", "brep operations", "facade assembly",
                      "multi-stage processing", "combined operations"],
        "tags": ["intermediate", "culmination", "complex-pipeline", "sub-list", "brep", "facade-assembly"],
        "trigger_intents": [
            "complex panelization pipeline", "combine sub list dispatch surface",
            "multi-stage grasshopper definition", "advanced panel processing",
            "complex facade assembly", "combining intermediate concepts"
        ],
    },

    # ── LESSON 5: List Manipulation and Panelization ──
    {
        "image": "5-2",
        "name": "Insert Items and Replace Items — List Modification Operations",
        "cluster_type": "alternatives",
        "brief": "Left: Insert Items shown 4 times inserting at different positions + Replace Items. Right: practical application with Gene Pool → Vector XYZ → Interpolate → Network Surface.",
        "context": (
            "Two sections. "
            "Left: Four Insert Items examples showing insertion at different list positions. "
            "Panel inputs (A,B,C,D,E / 1,2,3,4,5) with Panel index controlling insertion position. "
            "Output panels show how inserted items shift existing items. "
            "Replace Items: similar but REPLACES instead of inserting (no shift). "
            "Right: Practical application. "
            "Curve and Point references → Insert Items (inserting points into curve data). "
            "Gene Pool → Vector XYZ → creates varied 3D vectors. "
            "Merge: combines data streams. "
            "Point → Move (by Gene Pool vectors) → Interpolate (smooth curve through moved points). "
            "Insert Items: inserts additional curves into the curve list. "
            "Final curves → Network Surface → Custom Preview. "
            "Also shows Ext (Rail), Sweep1, Sweep2, Loft, Patch Surface as orange component icons — "
            "alternative surface creation methods from the modified curve network."
        ),
        "solution_principle": (
            "Insert Items adds new items at a specified index, pushing existing items down. "
            "Replace Items overwrites items at a specified index without shifting. "
            "Insert Items is useful for adding curves to a network for Network Surface creation. "
            "Gene Pool → Vector XYZ creates varied displacement vectors for organic form. "
            "The right side shows a practical workflow: modify a curve network, then create a surface."
        ),
        "components": ["Insert Items", "Replace Items", "Panel", "Point", "Curve", "Gene Pool",
                        "Vector XYZ", "Merge", "Move", "Interpolate", "Network Surface", "Custom Preview"],
        "keywords": ["insert items", "replace items", "list modification", "gene pool vectors",
                      "network surface from modified curves", "curve insertion"],
        "tags": ["intermediate", "alternatives", "insert-items", "replace-items", "list-modification",
                 "network-surface", "gene-pool"],
        "trigger_intents": [
            "insert items grasshopper", "replace items in list",
            "add items to list at position", "insert curves network surface",
            "gene pool vector xyz", "modify curve network for surface"
        ],
    },
    {
        "image": "5-3.",
        "name": "Weave vs Merge — Interleaving vs Concatenating Lists",
        "cluster_type": "comparison",
        "brief": "Five rows comparing Merge (concatenates: A,B,C,D,E,1,2,3,4,5) vs Weave (interleaves: A,1,B,2,C,3...). Practical applications with Polygon and Loft.",
        "context": (
            "Five rows comparing Merge and Weave operations. "
            "Row 1: Two panels (A-E and 1-5) → Merge gives (A,B,C,D,E,1,2,3,4,5) vs Weave gives (A,1,B,2,C,3,D,4,E,5). "
            "Row 2: Similar with different data showing concatenation vs interleaving. "
            "Row 3: Weave with 3 inputs showing more complex interleaving (A,1,α,B,2,β,...). "
            "Row 4: Weave output → Polygon. Weave interleaves point sets so polygons alternate between sources. "
            "Row 5: Weave → Loft. Interleaved curves create a loft that weaves between two curve sets. "
            "Key insight: Merge puts all of list A first, then all of list B. "
            "Weave alternates: one from A, one from B, one from A, etc."
        ),
        "solution_principle": (
            "Merge CONCATENATES: all items from input 1, then all from input 2. Order: A,A,A,B,B,B. "
            "Weave INTERLEAVES: alternates items from each input. Order: A,B,A,B,A,B. "
            "Weave with 3+ inputs interleaves cyclically. "
            "Use Weave when you need alternating patterns from two data sources. "
            "Use Merge when you need all items from one source followed by all from another."
        ),
        "components": ["Merge", "Weave", "Panel", "Polygon", "Loft", "Point"],
        "keywords": ["weave", "merge", "interleave", "concatenate", "alternating lists",
                      "weave vs merge", "list combination"],
        "tags": ["intermediate", "comparison", "weave", "merge", "interleave", "list-operations"],
        "trigger_intents": [
            "weave vs merge grasshopper", "interleave lists",
            "weave component", "alternate items from two lists",
            "merge concatenate vs weave interleave", "weave for alternating pattern"
        ],
    },
    {
        "image": "5-4",
        "name": "Map to Surface — Triangle Panels Remapped Between Surfaces",
        "cluster_type": "single",
        "brief": "Triangle Panels C (U=33, V=9) → Scale at centroid (0.8) → Map to Surface (source→target) × 2 → Entwine (Flatten) → Flip Matrix → Loft. Panel transfer between surfaces.",
        "context": (
            "Demonstrates the Map to Surface component for transferring geometry between surfaces. "
            "Source Surface → Triangle Panels C (U Divisions=33, V Divisions=9) → Panels. "
            "Curve (extract from panels) → Area (centroid) → Scale (Factor=0.8). "
            "Two Map to Surface components: "
            "Map #1: Curve (scaled panels), Source surface → Target surface #1 → mapped curves. "
            "Map #2: Same curves, Source surface → Target surface #2 → mapped curves. "
            "Both mapped outputs → Entwine (with Flatten) → Flip Matrix → Loft. "
            "Result: triangular panel pattern from one surface transferred to two target surfaces, "
            "then lofted between corresponding panels."
        ),
        "solution_principle": (
            "Map to Surface transfers 2D geometry from one surface's parameter space to another surface. "
            "Source surface defines the UV coordinates of the input geometry. "
            "Target surface receives the geometry at corresponding UV positions. "
            "This enables defining a pattern once and applying it to different surface shapes. "
            "Scale at centroid before mapping adjusts panel gap/overlap. "
            "Entwine + Flip Matrix + Loft connects corresponding panels between surfaces."
        ),
        "components": ["Surface", "Triangle Panels C", "Curve", "Area", "Scale", "Map to Surface",
                        "Entwine", "Flip Matrix", "Loft", "Number Slider"],
        "keywords": ["map to surface", "triangle panels", "surface remapping", "panel transfer",
                      "uv mapping", "pattern transfer", "surface correspondence"],
        "tags": ["intermediate", "map-to-surface", "panelization", "triangle-panels", "surface-remapping"],
        "trigger_intents": [
            "map to surface grasshopper", "transfer panels between surfaces",
            "triangle panels map surface", "remap geometry to surface",
            "surface to surface mapping", "pattern transfer between surfaces"
        ],
    },
    {
        "image": "5-6",
        "name": "Diamond Panel Curve Manipulation — Discontinuity, Bridge, Mirror, Patch Surface",
        "cluster_type": "single",
        "brief": "Diamond Panels → Discontinuity → List Item/Point List → Bridge → Nurbs Curve → Mirror (YZ+XY) → Line SDL → Move → Merge → Patch Surface → Custom Preview",
        "context": (
            "Complex single definition working with Diamond Panels and curve manipulation. "
            "Surface → Diamond Panels (Number Slider for U divisions). "
            "Discontinuity: extracts vertices/edges from panel curves. "
            "List Item: selects specific elements. Point List: visualizes points. "
            "Bridge (or similar): connects points/curves. "
            "Nurbs Curve: creates smooth curves through points. "
            "Area → Point On Curve → Nurbs Curve path. "
            "Mirror × 2: YZ Plane mirror + XY Plane mirror. Creates symmetric copies. "
            "Line SDL: creates construction lines (Start, Direction, Length). "
            "Move: offsets geometry. "
            "Unit Y: provides Y-direction vector. Number Slider: 0.71 for parameter. "
            "Merge: combines original + mirrored geometry. "
            "→ Patch Surface (Edge Curves input). "
            "→ Move → Custom Preview ('white'). "
            "Result: Diamond panels deconstructed, curves mirrored symmetrically, surfaces patched back."
        ),
        "solution_principle": (
            "Discontinuity extracts the vertices/kinks of a curve — essential for decomposing panel edges. "
            "Mirror creates symmetric copies across planes (YZ, XY). "
            "Bridge connects separate curve segments. "
            "Patch Surface creates surfaces from boundary curves — flexible for irregular shapes. "
            "This pattern — decompose panels → manipulate curves → mirror → patch — creates complex symmetric facade elements."
        ),
        "components": ["Surface", "Diamond Panels", "Discontinuity", "List Item", "Point List",
                        "Bridge", "Nurbs Curve", "Area", "Point On Curve", "Mirror", "YZ Plane",
                        "XY Plane", "Line SDL", "Move", "Unit Y", "Merge", "Patch Surface",
                        "Custom Preview", "Number Slider"],
        "keywords": ["diamond panels", "discontinuity", "bridge curves", "mirror symmetry",
                      "patch surface", "panel curve manipulation", "facade element"],
        "tags": ["intermediate", "diamond-panels", "curve-manipulation", "mirror", "patch-surface", "facade-element"],
        "trigger_intents": [
            "diamond panel curve manipulation", "discontinuity vertices",
            "mirror panel curves", "bridge curves grasshopper",
            "patch surface from mirror curves", "symmetric facade element"
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
    lesson_labels = {
        3: "Attraction Algorithms",
        4: "Surface Creation and List Operations",
        5: "List Manipulation and Panelization",
    }
    category_label = lesson_labels.get(lesson_num, f"Lesson {lesson_num}")

    return {
        "note_id": note_id,
        "note_type": "teaching",
        "name": f"Intermediate {image}: {lesson['name']}",
        "brief": lesson["brief"],
        "version": "1.0",
        "created": now,
        "context": lesson["context"],
        "keywords": lesson["keywords"],
        "category": f"Intermediate - {category_label}",
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
            "step_number": int(image.replace(".", "").split("-")[1]),
            "cluster_type": lesson["cluster_type"],
            "components_demonstrated": {c: 1 for c in lesson["components"]},
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Extract teaching notes from Intermediate tutorial images")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    print(f"Intermediate Tutorial Extraction")
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
        for tn in tutorial_notes:
            new_links = evo.link(tn, store)
            link_count += len(new_links)
        print(f"  Created {link_count} links for {len(tutorial_notes)} tutorial notes")

        # Save
        store.save_all()
        print(f"  Store saved. Index rebuilt.")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
