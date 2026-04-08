#!/usr/bin/env python3
"""
Extract teaching knowledge from Expert tutorial images.

These images are from a standalone visual GH course with no .gh files.
Teaching data was extracted by visual inspection of each image.

Usage:
    python run_extract_expert_tutorials.py [--dry-run]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

NOTES_DIR = Path(__file__).parent.parent / "knowledge" / "gh" / "notes"
SOURCE = "expert_tutorial_visual"
COURSE = "BeginnerToAdvanced"
LEVEL = "Expert"

def stable_id(image_name: str) -> str:
    raw = f"{COURSE}:{LEVEL}:{image_name}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"tutorial_{h}"


# ============================================================
# EXTRACTED TEACHING DATA (from visual inspection of 30 images)
# ============================================================

LESSONS = [
    # ── LESSON 7 (continued from Professional): Advanced Mesh and Voronoi ──
    {
        "image": "7-8",
        "name": "Box Morph with MultiPipe Mesh — Surface Box, Bounding Box, Scale",
        "cluster_type": "single",
        "brief": "Morphs grouped curve geometry into surface box cells, then converts to a MultiPipe mesh with custom preview.",
        "context": (
            "A Surface parameter feeds into Surface Box along with a Construct Domain2 (built from two Number Sliders at 5) "
            "through Divide Domain2 to set U Count and V Count segments. Surface Box Height is set by a Number Slider at 10.00. "
            "The resulting Twisted Box list is accessed via List Item with a Number Slider index at 2, and a Panel shows 3 groups "
            "of 100 objects each. A referenced Curve is grouped with Group, then Bounding Box extracts the box. The bounding box "
            "is sent to Volume (for Centroid) and to a Panel showing 'Flat Box'. An Extrude component with direction '0,0,1' and "
            "a Panel value of 1 creates volume from the flat box. Scale uses the Volume Centroid as Center and Factor 1 to "
            "normalize. Box Morph takes the Geometry (grouped curves), Reference (scaled bounding box), and Target (surface "
            "twisted boxes). The morphed output goes through Ungroup, then into MultiPipe (with StrutSize from a Panel value "
            "of 1). The resulting Pipe feeds into a Mesh component, then Custom Preview with a 'white' material Panel."
        ),
        "solution_principle": (
            "Box Morph requires a proper reference box matching the geometry's bounding volume — using Bounding Box + Extrude "
            "to create the reference, then Scale to normalize, ensures the morph maps correctly onto each Surface Box cell. "
            "MultiPipe converts curve networks into smooth mesh pipes."
        ),
        "components": ["Surface", "Surface Box", "Construct Domain2", "Divide Domain2", "Number Slider", "List Item",
                        "Panel", "Curve", "Group", "Bounding Box", "Volume", "Extrude", "Scale", "Box Morph",
                        "Ungroup", "MultiPipe", "Mesh", "Custom Preview"],
        "keywords": ["box morph", "surface box", "multipipe", "bounding box", "scale", "extrude", "morph curves",
                      "mesh pipe", "paneling", "twisted box"],
        "tags": ["expert", "box-morph", "multipipe", "mesh", "paneling", "surface-subdivision"],
        "trigger_intents": [
            "how to use box morph with surface box",
            "morph curves onto a subdivided surface",
            "multipipe mesh from morphed curve network",
            "box morph reference box setup with bounding box",
            "panel a surface with curve geometry using box morph",
            "convert morphed curves to mesh with MultiPipe"
        ],
    },
    {
        "image": "7-9",
        "name": "Populate 3D vs Evaluate Box with Cross Reference — Point Distribution Methods",
        "cluster_type": "comparison",
        "brief": "Compares random point population inside a 3D region (Populate 3D) with structured grid point generation using Evaluate Box and Cross Reference.",
        "context": (
            "Two separate definitions. Top: A Geometry parameter connects to Populate 3D's Region input. A Number Slider "
            "set to 1000 feeds the Count input, generating 1000 random points within the bounding region. Bottom: The same "
            "Geometry parameter connects to Evaluate Box's Box input. A Panel with value 10 feeds into Range (Steps), producing "
            "0-to-1 parameter values. The Range output connects to Cross Reference (Holistic mode) on both List A and List B "
            "inputs. The two Cross Reference outputs feed into Evaluate Box's U and V parameter inputs, while Range also "
            "connects to W parameter. Evaluate Box outputs Points for display. This creates a structured 3D grid of points "
            "evaluated at regular intervals within the box."
        ),
        "solution_principle": (
            "Populate 3D generates random points within a volume, while Evaluate Box with Cross Reference creates a structured "
            "parametric grid. Cross Reference in Holistic mode creates all combinations of U, V, W parameters, essential for "
            "filling a 3D volume with evenly-spaced points."
        ),
        "components": ["Geometry", "Populate 3D", "Number Slider", "Panel", "Range", "Cross Reference",
                        "Evaluate Box", "Point"],
        "keywords": ["populate 3d", "evaluate box", "cross reference", "holistic", "range", "point grid",
                      "random points", "structured grid", "3d points", "parametric volume"],
        "tags": ["expert", "comparison", "point-population", "cross-reference", "evaluate-box", "3d-grid"],
        "trigger_intents": [
            "random vs structured points inside a box",
            "how to use Populate 3D in Grasshopper",
            "evaluate box with cross reference for 3D grid",
            "create grid of points inside a volume",
            "cross reference holistic mode for 3D parameters",
            "distribute points evenly in a bounding box"
        ],
    },
    {
        "image": "7-10",
        "name": "Construct Mesh from Vertices and Faces — Manual Mesh Definition with Colours",
        "cluster_type": "single",
        "brief": "Manually constructs a mesh from point vertices and face index definitions (triangles and quads), with per-vertex colours and Unify Mesh.",
        "context": (
            "A Panel with value 1.5 feeds into Point List (Size input). The Point parameter provides vertex positions. "
            "A Panel displays face definitions: 'T{3;2;6}', 'Q{6;2;1;0}', 'T{0;7;1}' — T for triangles, Q for quads with "
            "vertex indices. These feed Construct Mesh (Vertices, Faces, Colours inputs). Multiple Colour Swatch components "
            "(red, green, cyan, pink, etc.) feed into Merge (D1 through D8), whose Result connects to Colours. Output Panel "
            "shows 'Mesh (V:8 F:5)'. The mesh passes through Unify Mesh, outputting Count=3 confirming unified normals."
        ),
        "solution_principle": (
            "Meshes are defined by vertex positions and face index lists. T{} defines triangles (3 indices) and Q{} defines "
            "quads (4 indices). Per-vertex colours are applied via the Colours input. Unify Mesh ensures consistent normal "
            "directions across all faces."
        ),
        "components": ["Panel", "Point List", "Point", "Construct Mesh", "Colour Swatch", "Merge", "Unify Mesh"],
        "keywords": ["construct mesh", "mesh faces", "mesh vertices", "triangle", "quad", "vertex colour",
                      "unify mesh", "mesh topology", "face index"],
        "tags": ["expert", "mesh", "construct-mesh", "vertex-colour", "mesh-topology"],
        "trigger_intents": [
            "how to manually construct a mesh in Grasshopper",
            "define mesh faces with triangle and quad indices",
            "construct mesh from vertices and face definitions",
            "apply per-vertex colours to a mesh",
            "unify mesh normals in Grasshopper",
            "mesh topology T and Q face notation"
        ],
    },
    {
        "image": "7-11",
        "name": "Voronoi to Lofted Surfaces with Subdivision Mesh — Populate 2D, Flip Matrix, Ruled Surface",
        "cluster_type": "culmination",
        "brief": "Generates a 2D Voronoi pattern, lofts cell edges into surfaces, joins into a Brep, converts to mesh, and applies Weighted Loop Subdivision for a smooth organic form.",
        "context": (
            "A Point and Curve set up the Voronoi boundary. Populate 2D receives Region from Curve, Count~90, Seed~361. "
            "Voronoi Cells feed into Entwine (with Flatten), then Flip Matrix, then Loft. Param Viewer shows 90 branches. "
            "Scale takes Populate 2D points with Factor 5, Move offsets with Unit Z (factor~0.26). Ruled Surface takes "
            "Curve A and B from Voronoi cells and offset edges. Both Loft and Ruled Surface feed Merge, then Brep Join. "
            "Mesh Brep converts to mesh, then Weighted Loop Subdivision (Level 1) smooths. Extrude at bottom extrudes the "
            "surface. Custom Preview with GRAY material."
        ),
        "solution_principle": (
            "Full pipeline combining Voronoi tessellation, data tree manipulation (Entwine + Flip Matrix), surface generation "
            "(Loft + Ruled Surface), Brep joining, meshing, and subdivision smoothing. Flip Matrix transposes Voronoi cell edge "
            "lists so Loft creates surfaces across cells. Weighted Loop Subdivision smooths the mesh into an organic form."
        ),
        "components": ["Point", "Curve", "Number Slider", "Populate 2D", "Voronoi", "Entwine", "Flip Matrix",
                        "Loft", "Param Viewer", "Scale", "Panel", "Move", "Unit Z", "Surface", "Ruled Surface",
                        "Merge", "Brep Join", "Mesh Brep", "Weighted Loop Subdivision", "Extrude", "Custom Preview"],
        "keywords": ["voronoi", "loft", "flip matrix", "ruled surface", "brep join", "mesh brep", "loop subdivision",
                      "populate 2d", "entwine", "organic mesh", "voronoi surface"],
        "tags": ["expert", "culmination", "voronoi", "loft", "subdivision", "mesh", "data-trees"],
        "trigger_intents": [
            "voronoi pattern to smooth subdivision mesh",
            "loft voronoi cells into surfaces",
            "flip matrix with entwine for voronoi lofting",
            "weighted loop subdivision on joined brep mesh",
            "voronoi to organic mesh pipeline",
            "populate 2D voronoi with ruled surface and loft"
        ],
    },

    # ── LESSON 8: Mesh Operations and Digital Fabrication ──
    {
        "image": "8-1",
        "name": "Mesh Construction from Points — Construct Mesh, Concatenate, Partition List",
        "cluster_type": "progression",
        "brief": "Four approaches to constructing meshes from point grids: direct face indices, string-built face definitions, parameterized vertex indexing, and partitioned face lists",
        "context": (
            "Four definition blocks in a 2x2 grid. Top-left: Point feeds Point List (Size=2), Panel shows coordinates, "
            "Construct Mesh (Vertices+Faces) produces Mesh (V:6 F:5), Unify Mesh outputs count=2. Top-right: Concatenate "
            "builds strings from Number Sliders (6,5) with text fragments. Bottom-left: Points through Deconstruct (X/Y/Z) "
            "feed Concatenate with 'T{', ';', '}' fragments to build face strings like T{0;1;5}. Bottom-right: Point+Point "
            "List through Partition List (Size=3) splits into groups for triangle faces, then Concatenate builds face strings "
            "for Construct Mesh."
        ),
        "solution_principle": (
            "Meshes are built from vertex lists and face index definitions. Understanding the T{v0;v1;v2} face syntax and how "
            "to programmatically generate face indices from point lists using Concatenate and Partition List is fundamental to "
            "custom mesh creation."
        ),
        "components": ["Point", "Point List", "Construct Mesh", "Unify Mesh", "Concatenate", "Number Slider",
                        "Panel", "Deconstruct", "Partition List", "List Item"],
        "keywords": ["mesh", "construct mesh", "vertices", "faces", "triangulation", "face index",
                      "concatenate", "partition list", "mesh topology"],
        "tags": ["expert", "progression", "mesh", "construction", "face-indices", "string-building"],
        "trigger_intents": [
            "how to construct mesh from points",
            "build mesh face indices programmatically",
            "mesh vertex and face definition in grasshopper",
            "create triangular mesh from point grid",
            "concatenate face index strings for mesh construction",
            "partition list for mesh face groups"
        ],
    },
    {
        "image": "8-2",
        "name": "Mesh Face Operations — Mesh Surface, Deconstruct Mesh, Cull Index, Mesh Explode, CombineAndClean",
        "cluster_type": "progression",
        "brief": "Three approaches to mesh face manipulation: basic surface meshing, mesh joining from multiple surfaces, and advanced face culling with random reduction and mesh explosion/recombination",
        "context": (
            "Three definition blocks. Top-left: Surface feeds Divide Surface (Count=2), Points to Construct Mesh producing "
            "Mesh (V:6 F:5), then Unify Mesh. Top-right: Multiple Surfaces feed Mesh components, Mesh Join produces "
            "Mesh (V:28 F:8), CombineAndClean produces Mesh (V:18 F:8) showing vertex welding. Bottom: Surface feeds "
            "Mesh Surface (V Count=11), Deconstruct Mesh extracts Vertices/Faces/Colours/Normals. Cull Index removes face "
            "at index 0, Cull Pattern (0,0;1,1) and Random Reduce (70%) filter faces. Mesh Explode with List Item selects "
            "individual faces. Results go through CombineAndClean and Mesh Join."
        ),
        "solution_principle": (
            "Mesh manipulation requires understanding vertex-face relationships. Culling, reducing, and exploding faces "
            "while maintaining vertex integrity is key to custom mesh editing workflows."
        ),
        "components": ["Surface", "Divide Surface", "Point List", "Construct Mesh", "Mesh Surface",
                        "Deconstruct Mesh", "Cull Index", "Cull Pattern", "Random Reduce", "Mesh Explode",
                        "List Item", "CombineAndClean", "Mesh Join", "Custom Preview", "Panel", "Number Slider"],
        "keywords": ["mesh", "deconstruct mesh", "cull faces", "mesh explode", "mesh join",
                      "combine clean", "cull index", "random reduce", "face manipulation"],
        "tags": ["expert", "progression", "mesh", "face-culling", "deconstruct", "mesh-operations"],
        "trigger_intents": [
            "how to remove specific mesh faces",
            "cull mesh faces by index or pattern",
            "deconstruct and reconstruct mesh with fewer faces",
            "mesh explode and recombine individual faces",
            "join and clean multiple meshes",
            "random reduce mesh faces in grasshopper"
        ],
    },
    {
        "image": "8-3",
        "name": "Mesh Checker Pattern with Offset Surface — Cull Pattern, Face Boundaries, Ruled Surface",
        "cluster_type": "single",
        "brief": "Creates a checker pattern on a surface by meshing, culling alternating faces, extracting face boundaries as curves, then lofting between original and offset surface boundaries with Ruled Surface",
        "context": (
            "Two parallel pipelines. Top: Surface feeds Mesh Surface (Count=10), Deconstruct Mesh, Cull Pattern (0,0;1,1;2,1) "
            "filters alternating faces, Construct Mesh, Face Boundaries extracts curves for Ruled Surface as Curve A, Custom "
            "Preview red. Bottom: Same Surface feeds Offset Surface (distance=2), identical Mesh/Cull/Construct/Face Boundaries "
            "chain, output feeds Ruled Surface as Curve B, Custom Preview white. Merge combines Number Sliders (1,0,0,1) for "
            "the cull pattern. Ruled Surface creates side walls between face boundaries on original and offset surfaces."
        ),
        "solution_principle": (
            "Combining mesh face culling with surface offsetting and ruled surface lofting between corresponding face boundaries "
            "creates volumetric patterns from flat surfaces — a powerful fabrication-oriented technique."
        ),
        "components": ["Surface", "Mesh Surface", "Deconstruct Mesh", "Cull Pattern", "Construct Mesh",
                        "Face Boundaries", "Ruled Surface", "Offset Surface", "Custom Preview", "Merge",
                        "Number Slider", "Panel"],
        "keywords": ["checker pattern", "mesh cull pattern", "face boundaries", "ruled surface",
                      "offset surface", "volumetric pattern", "fabrication"],
        "tags": ["expert", "mesh", "pattern", "checker", "ruled-surface", "offset", "fabrication"],
        "trigger_intents": [
            "create checker pattern on surface with mesh",
            "cull alternating mesh faces for pattern",
            "ruled surface between face boundaries",
            "3D extruded checker pattern from mesh",
            "offset surface with matching face culling",
            "mesh face boundaries to ruled surface lofting"
        ],
    },
    {
        "image": "8-4",
        "name": "TriRemesh with Triangle Mapping — TriRemesh, Face Boundaries, Triangle Mapping",
        "cluster_type": "single",
        "brief": "Remeshes a surface into triangles using TriRemesh, extracts face boundaries, then maps geometry onto each triangular face using Triangle Mapping for panelization",
        "context": (
            "Surface feeds TriRemesh (Iterations=3). Triangulation output connects to Face Boundaries which extracts boundary "
            "curves. Two parallel Triangle Mapping setups: each has Geometry param (object to map), Curve param (source triangle), "
            "and Face Boundaries (target triangles). Triangle Mapping maps content from source to every target face. Output goes "
            "to Custom Preview with white material."
        ),
        "solution_principle": (
            "TriRemesh creates high-quality triangulations of arbitrary surfaces, and Triangle Mapping enables mapping any "
            "geometry from a source triangle onto every face — the foundation for triangular panelization and digital "
            "fabrication patterns."
        ),
        "components": ["Surface", "TriRemesh", "Face Boundaries", "Triangle Mapping", "Geometry", "Curve",
                        "Custom Preview", "Number Slider", "Panel"],
        "keywords": ["triremesh", "triangle mapping", "panelization", "triangulation", "face boundaries",
                      "remesh", "digital fabrication", "triangular panels"],
        "tags": ["expert", "mesh", "triremesh", "panelization", "triangle-mapping", "fabrication"],
        "trigger_intents": [
            "triangular panelization with TriRemesh",
            "map geometry onto triangular mesh faces",
            "TriRemesh and Triangle Mapping workflow",
            "remesh surface into triangles for fabrication",
            "panel design on triangulated surface",
            "triangle mapping for consistent face paneling"
        ],
    },
    {
        "image": "8-5",
        "name": "Digital Fabrication Pipeline — TriRemesh, Mesh Explode, Weighted Loop Subdivision, Weaverbird Mesh Thicken",
        "cluster_type": "culmination",
        "brief": "Full digital fabrication pipeline: TriRemesh a surface, explode into faces, apply subdivision smoothing, and thicken with Weaverbird for fabrication-ready geometry",
        "context": (
            "Header: 'Digital Fabrication (Material - Structural Design - Detail Design - Fabrication Method - Algorithm Design)'. "
            "Surface feeds TriRemesh (Iterations=3). Dual output feeds forward. Mesh Explode with Panel {0} produces M,N,A. "
            "List Item selects meshes. Subdivision level=5 feeds Weighted Loop Subdivision. Output goes to Weaverbird's "
            "Mesh Thicken (Distance=0.5). Custom Preview displays with white material."
        ),
        "solution_principle": (
            "Digital fabrication requires a complete pipeline: TriRemesh for quality meshing, explosion for individual panel "
            "access, subdivision for smoothing, and mesh thickening for physical materiality."
        ),
        "components": ["Surface", "TriRemesh", "Mesh Explode", "List Item", "Weighted Loop Subdivision",
                        "Weaverbird's Mesh Thicken", "Custom Preview", "Number Slider", "Panel"],
        "keywords": ["digital fabrication", "triremesh", "mesh explode", "subdivision", "weighted loop",
                      "weaverbird", "mesh thicken", "fabrication pipeline", "dual mesh"],
        "tags": ["expert", "culmination", "fabrication", "triremesh", "subdivision", "weaverbird", "mesh-thicken"],
        "trigger_intents": [
            "digital fabrication pipeline in grasshopper",
            "TriRemesh to Weaverbird mesh thicken workflow",
            "subdivide and thicken mesh panels for fabrication",
            "weighted loop subdivision on exploded mesh faces",
            "complete fabrication workflow from surface to panels",
            "mesh thicken with Weaverbird for physical fabrication"
        ],
    },
    {
        "image": "8-6",
        "name": "Mesh Subdivision and Thickening — TriRemesh, Snub, Weaverbird",
        "cluster_type": "single",
        "brief": "Remeshes a surface with TriRemesh, applies Snub+3 and Fan+3 mesh dual operations, then subdivides and thickens using Weaverbird plugins for a panelized facade effect.",
        "context": (
            "Surface feeds TriRemesh (iterations=5). Triangulation output goes through Data Dam to both Snub+3 (T0=0.39, "
            "T1=0.32, N=5) and Mesh Explode to Fan+3 (0.29). Snub output goes through Data Dam to Weighted Loop Subdivision, "
            "then Weaverbird's Mesh Thicken (Distance=-0.5). Fan output goes to Weaverbird's Laplacian Smoothing. Custom "
            "Preview with white material."
        ),
        "solution_principle": (
            "TriRemesh creates clean triangulated meshes, then topological operators like Snub and Fan create complex polygon "
            "patterns from simple triangulations. Subdivision smooths the result while Mesh Thicken gives it physical depth — "
            "core pipeline for parametric facade panels."
        ),
        "components": ["Surface", "TriRemesh", "Number Slider", "Snub+3", "Data Dam", "Mesh Explode",
                        "Fan+3", "Weighted Loop Subdivision", "Weaverbird's Laplacian Smoothing",
                        "Weaverbird's Mesh Thicken", "Custom Preview", "Panel"],
        "keywords": ["triremesh", "snub", "fan", "mesh dual", "subdivision", "weaverbird", "mesh thicken",
                      "laplacian smoothing", "facade", "topological"],
        "tags": ["expert", "mesh", "weaverbird", "subdivision", "facade", "topology"],
        "trigger_intents": [
            "how to create panelized mesh facade from surface",
            "triremesh with snub and fan dual operations",
            "weaverbird mesh thicken and subdivision pipeline",
            "convert surface to decorative mesh pattern with weaverbird",
            "mesh topology manipulation snub fan dual grasshopper",
            "weighted loop subdivision with mesh thickening"
        ],
    },
    {
        "image": "8-7",
        "name": "Weave Pattern Facade with Weaverbird — TriRemesh, Weave, Picture Frame, Catmull Clark",
        "cluster_type": "single",
        "brief": "Creates a woven facade pattern by remeshing a surface, applying Weave and Picture Frame operations via Weaverbird, then subdividing with Catmull Clark and thickening.",
        "context": (
            "Two parallel paths from Surface. Top: TriRemesh, Triangulation to Weave (T0=0.39, T1=0.19), to Weaverbird's "
            "Mesh Window and Picture Frame, through Data Dam to Weighted Catmull Clark Subdivision, then Mesh Thicken "
            "(Distance=0.2). Bottom (purple): Mesh Surface (Count=10, U/V=10), to Mesh Window and Picture Frame (Distance=0.6), "
            "through Continuum (multiple sliders), another Picture Frame, Data Dam, Catmull Clark, Mesh Thicken. Custom Preview "
            "with white material."
        ),
        "solution_principle": (
            "Weaverbird's Weave, Mesh Window, and Picture Frame transform simple meshes into intricate woven/framed patterns. "
            "Combining with Catmull Clark subdivision creates smooth architectural facade patterns."
        ),
        "components": ["Surface", "TriRemesh", "Number Slider", "Weave", "Weaverbird's Mesh Window",
                        "Weaverbird's Picture Frame", "Data Dam", "Weighted Catmull Clark Subdivision",
                        "Weaverbird's Mesh Thicken", "Mesh Surface", "Continuum", "Custom Preview", "Panel", "Mesh"],
        "keywords": ["weave", "picture frame", "mesh window", "catmull clark", "weaverbird", "facade",
                      "woven pattern", "mesh thicken", "subdivision"],
        "tags": ["expert", "mesh", "weaverbird", "facade", "weave", "catmull-clark", "pattern"],
        "trigger_intents": [
            "create woven mesh facade pattern with weaverbird",
            "weaverbird picture frame and mesh window for facade",
            "catmull clark subdivision with weave pattern",
            "architectural woven panel from surface using weaverbird",
            "mesh window and picture frame weaverbird pipeline",
            "two approaches to mesh facade weave vs picture frame"
        ],
    },
    {
        "image": "8-8",
        "name": "Image Sampler Color to Mesh — Image Sampler, Surface Closest Point, Construct Mesh",
        "cluster_type": "single",
        "brief": "Image Sampler extracts color data from an image using UV coordinates, then applies those colors to a remeshed surface via Surface Closest Point and Construct Mesh.",
        "context": (
            "Top: Panel with UV coordinates, MD Sliders feed Image Sampler displaying a rhinoceros photo. Outputs color "
            "values ('241,238,249' and '78,70,59') through Multiplication (*255) and Deconstruct. Bottom: Surface feeds "
            "TriRemesh (edge length=0.1) with Dual. Deconstruct Mesh Vertices feed Surface Closest Point with original "
            "Surface. UV Point output goes to Image Sampler. Colors through Multiplication and Deconstruct feed Construct "
            "Mesh Colours input to rebuild mesh with image-sampled per-vertex colors."
        ),
        "solution_principle": (
            "Image Sampler maps 2D image data onto 3D geometry by using UV coordinates from Surface Closest Point. "
            "Pipeline: remesh surface, get vertices, find UV positions, sample colors, reconstruct mesh with vertex colors. "
            "Enables image-driven mesh coloring for visualization and fabrication."
        ),
        "components": ["Panel", "MD Slider", "Image Sampler", "Multiplication", "Deconstruct", "Surface",
                        "TriRemesh", "Deconstruct Mesh", "Surface Closest Point", "Construct Mesh"],
        "keywords": ["image sampler", "color", "UV coordinates", "surface closest point", "construct mesh",
                      "vertex colors", "texture mapping", "image driven"],
        "tags": ["expert", "image-sampler", "color", "mesh", "UV", "texture"],
        "trigger_intents": [
            "map image colors onto mesh surface in grasshopper",
            "image sampler with surface closest point UV mapping",
            "apply texture colors to remeshed surface vertices",
            "how to use image sampler for mesh vertex coloring",
            "extract RGB color data from image onto 3D surface",
            "construct mesh with colors from image sampler"
        ],
    },
    {
        "image": "8-9",
        "name": "Image-Driven Mesh Scaling and Thickening — Image Sampler, Area, Scale, Fillet",
        "cluster_type": "single",
        "brief": "Uses Image Sampler grayscale values to drive per-face scaling of a remeshed surface, creating variable-density openings that are filleted, subdivided, and thickened into a perforated facade.",
        "context": (
            "Surface feeds TriRemesh (iterations=15). Face Boundaries extracts curves, Area outputs Centroid and Area. "
            "Centroids go to Surface Closest Point providing UV Points to Image Sampler (grayscale rhino image). Brightness "
            "values (0.57, 0.62, 0.86...) feed Scale Factor, with Face Boundaries as Geometry and Centroid as Center. "
            "Scaled faces to Surface, then Fillet (radius=0.3). Filleted curves to Simple Mesh, Combine&Clean, "
            "Weighted Loop Subdivision (level=2), Weaverbird's Mesh Thicken (distance~0.07). Custom Preview white."
        ),
        "solution_principle": (
            "Image Sampler values can drive per-face scaling — bright pixels create larger openings, dark pixels smaller ones. "
            "This image-to-geometry pipeline (remesh, sample, scale, fillet, subdivide, thicken) is the standard approach "
            "for perforated facade panels where the perforation pattern comes from an image."
        ),
        "components": ["Surface", "TriRemesh", "Face Boundaries", "Area", "Surface Closest Point",
                        "Image Sampler", "Scale", "Fillet", "Simple Mesh", "CombineAndClean",
                        "Weighted Loop Subdivision", "Weaverbird's Mesh Thicken", "Custom Preview",
                        "Panel", "Number Slider"],
        "keywords": ["image sampler", "face scale", "perforated facade", "face boundaries", "area centroid",
                      "fillet", "mesh thicken", "brightness", "grayscale", "perforation"],
        "tags": ["expert", "image-sampler", "facade", "perforation", "mesh", "weaverbird", "scaling"],
        "trigger_intents": [
            "image driven perforated facade panel grasshopper",
            "scale mesh faces by image sampler brightness values",
            "create variable perforation pattern from image on surface",
            "image sampler to face scaling pipeline for facade",
            "perforated mesh facade with fillet and subdivision",
            "remesh surface and scale faces by grayscale image"
        ],
    },
    {
        "image": "8-10",
        "name": "Full Parametric Facade Pipeline — Circle Array, Mesh, Graph Mapper, Snub, Gradient Color",
        "cluster_type": "culmination",
        "brief": "Complete facade pipeline: circles on offset curve, boundary surface, multiple meshing strategies, TriRemesh, vertex displacement via Graph Mapper, Snub topology with height variation, subdivision, thickening, and gradient coloring.",
        "context": (
            "6 stages. Stage 1: Circle (R=22.56) to Offset Curve (-4.95), Divide Curve (Count=3) to smaller Circles (R=2.78). "
            "Stage 2: Merge, Boundary Surfaces, multiple mesh strategies (Mesh Surface count=100, Mesh Brep with Settings, "
            "Simple Mesh), TriRemesh. Stage 3: Pull Point Distance feeds Remap Numbers (target 30), through Graph Mapper "
            "(exponential curve) into Unit Z, Move displaces vertices, Construct Mesh. Stage 4: Second TriRemesh, Deconstruct "
            "to get Z component, Bounds, Remap (0.99 to 0.05) into Snub+0 (panel=0.4) for height-varying topology. Stage 5: "
            "Deconstruct Z through Bounds, Remap (0 to 1) into Gradient (green-yellow-red). Stage 6: Construct Mesh with "
            "colors, Weighted Loop Subdivision (L=2), Weaverbird's Mesh Thicken (0.1). Custom Preview."
        ),
        "solution_principle": (
            "Culminating pipeline combining curve-based geometry, multiple meshing strategies, Graph Mapper vertex displacement, "
            "Snub topology with spatially-varying parameters driven by vertex position, gradient coloring, and subdivision/"
            "thicken output. Demonstrates chaining analytical data through remapping to drive both geometry and visuals."
        ),
        "components": ["Circle", "Number Slider", "Offset Curve", "Divide Curve", "Merge", "Boundary Surfaces",
                        "Mesh Surface", "Mesh Brep", "Simple Mesh", "Brep", "TriRemesh", "Deconstruct Mesh",
                        "Curve", "Pull Point", "Remap Numbers", "Bounds", "Graph Mapper", "Unit Z", "Move",
                        "Construct Mesh", "Deconstruct", "Snub+0", "Gradient", "Weighted Loop Subdivision",
                        "Weaverbird's Mesh Thicken", "Custom Preview", "Panel", "Param Viewer"],
        "keywords": ["facade pipeline", "circle array", "offset curve", "meshing strategies", "triremesh",
                      "graph mapper", "vertex displacement", "snub", "gradient color", "height mapping",
                      "remap", "subdivision", "mesh thicken", "culmination"],
        "tags": ["expert", "culmination", "facade", "mesh", "graph-mapper", "snub", "gradient",
                 "weaverbird", "displacement", "pipeline"],
        "trigger_intents": [
            "complete parametric facade pipeline with mesh operations",
            "circle array to displaced mesh with gradient coloring",
            "graph mapper vertex displacement with snub topology",
            "full expert grasshopper facade from curves to thickened mesh",
            "height-driven snub variation with gradient mesh coloring",
            "combine meshing remapping displacement subdivision thickening"
        ],
    },

    # ── LESSON 9: Path Mapper, Volumetric Modeling, Advanced Coloring ──
    {
        "image": "9-1",
        "name": "Random Surface Displacement — Divide Surface, Random, Move, Surface From Points",
        "cluster_type": "single",
        "brief": "Divides a surface into points, displaces them randomly along Z using random vectors, then reconstructs a new surface from the moved points.",
        "context": (
            "Surface feeds Divide Surface (U=10, V=15). Points output to panel showing 176 items. Domain '-1 to 1' feeds "
            "Random (Number=176, Seed=262). Random output feeds Unit Z Factor, producing random Z vectors. Divide Surface "
            "Points and Unit Z vectors feed Move. Move output feeds Surface From Points with original U Count. Boolean Toggle "
            "(True) feeds Interpolate input. Custom Preview with gray material. Tree Statistics confirms Paths={0}, Length=176."
        ),
        "solution_principle": (
            "Full pattern of surface-to-points-to-surface reconstruction with random displacement — divide a surface, "
            "generate matched random vectors using List Length to sync counts, move points, and rebuild preserving the "
            "original U count and interpolation setting."
        ),
        "components": ["Surface", "Divide Surface", "List Length", "Panel", "Param Viewer", "Random",
                        "Unit Z", "Move", "Surface From Points", "Custom Preview", "Boolean Toggle",
                        "Number Slider", "Tree Statistics", "Point"],
        "keywords": ["surface displacement", "random", "divide surface", "surface from points", "move",
                      "random vectors", "surface reconstruction", "noise", "terrain"],
        "tags": ["expert", "surface", "random", "displacement", "reconstruction", "data-matching"],
        "trigger_intents": [
            "randomly displace surface points",
            "create noisy terrain from surface",
            "divide surface and rebuild with random offset",
            "surface from points with random Z displacement",
            "random surface deformation grasshopper",
            "reconstruct surface after moving division points"
        ],
    },
    {
        "image": "9-2",
        "name": "Attractor-Driven Mesh Panel Facade — Pull Point, Graph Mapper, Weaverbird Picture Frame, TriRemesh",
        "cluster_type": "culmination",
        "brief": "Full facade pipeline: divides surface, random displacement with attractor-based color and inset variation using Pull Point, Graph Mapper, Weaverbird Picture Frame, subdivision, TriRemesh, and Mesh Thicken.",
        "context": (
            "Mega-wide definition with multiple stages. Stage 1: Surface into Divide Surface (U=20, V=30), 651 points. "
            "Random (N=316, Seed=123, Range=-1 to 1) feeds Unit Z. Pull Point with attractor. Stage 2: Mesh FromPoints, "
            "Mesh Explode, Area centroids, Pull Point distances through Bounds, Remap Numbers. Weaverbird Picture Frame "
            "with Gene Pool (13.02, 26.11, 12.50, 21.87). Stage 3: Remap through Graph Mapper (sigmoid), Gradient "
            "(red-orange-yellow-blue). Second Remap+Graph Mapper (target 45 to 2) controls Picture Frame Distance. "
            "Mesh Join, Weld Mesh. Stage 4: Weighted Loop Subdivision (L=2), TriRemesh (Length=0.5), Deconstruct Mesh, "
            "Pull Point distances through Gradient for vertex colors. Construct Mesh with colors. Weaverbird Mesh Thicken "
            "(Distance=1). Custom Preview."
        ),
        "solution_principle": (
            "Complete expert facade workflow: surface displacement, mesh panelization with Weaverbird Picture Frame, "
            "attractor-driven variation (inset depth and color), subdivision smoothing, TriRemesh for clean topology, "
            "and mesh thickening. Graph Mapper curves control the distribution of attractor effects."
        ),
        "components": ["Surface", "Divide Surface", "List Length", "Random", "Unit Z", "Pull Point", "Point",
                        "Move", "Mesh FromPoints", "Mesh Explode", "Area", "Bounds", "Remap Numbers",
                        "Graph Mapper", "Gradient", "Weaverbird's Picture Frame", "Mesh Surface", "Gene Pool",
                        "Panel", "Param Viewer", "Number Slider", "Mesh Join", "Weld Mesh",
                        "Weighted Loop Subdivision", "TriRemesh", "Deconstruct Mesh", "Construct Mesh",
                        "Weaverbird's Mesh Thicken", "Custom Preview"],
        "keywords": ["facade", "panelization", "attractor", "pull point", "graph mapper", "weaverbird",
                      "picture frame", "mesh thicken", "triremesh", "vertex color", "gradient", "inset"],
        "tags": ["expert", "culmination", "facade", "mesh", "attractor", "weaverbird", "panelization",
                 "vertex-color", "subdivision"],
        "trigger_intents": [
            "attractor-driven facade panelization",
            "weaverbird picture frame with variable inset",
            "mesh facade with vertex coloring by distance",
            "surface to mesh panels with subdivision and thickening",
            "graph mapper to control attractor falloff on facade",
            "complete parametric facade pipeline grasshopper"
        ],
    },
    {
        "image": "9-3",
        "name": "Mesh Vertex Color by Closest Point Distance — TriRemesh, Deconstruct Mesh, Gradient",
        "cluster_type": "comparison",
        "brief": "Compares simple line-distance method vs full TriRemesh pipeline with closest-point distance, remapping, and gradient coloring on a Brep mesh.",
        "context": (
            "Two clusters. Top-left (simple): Point and Surface feed InvVist (Count=200, Distance=60), Line connects "
            "Start/End, Distance measured. Bottom (full pipeline, purple): Curve to Boundary Surfaces to Brep. TriRemesh "
            "with Feature. Deconstruct Mesh extracts Vertices. Point attractor feeds InvVist, Distance computed. Bounds "
            "produces domain (1.87 to 6.25). Deconstruct Domain extracts for Gradient Lower/Upper limits. Distances feed "
            "Gradient Parameter. Gradient (red-orange-yellow-blue) produces colors. Construct Mesh with Vertices, Faces, "
            "Colors. Custom Preview."
        ),
        "solution_principle": (
            "Production-quality mesh coloring requires TriRemesh for clean topology, Deconstruct/Construct Mesh for vertex "
            "color injection, Bounds + Deconstruct Domain for automatic range detection, and Gradient for mapping scalar "
            "distances to visual color."
        ),
        "components": ["Point", "Surface", "Curve", "Boundary Surfaces", "Brep", "TriRemesh",
                        "Deconstruct Mesh", "Construct Mesh", "InvVist", "Line", "Distance", "Average",
                        "Number", "Bounds", "Deconstruct Domain", "Gradient", "Custom Preview", "Panel"],
        "keywords": ["vertex color", "mesh coloring", "closest point", "distance", "gradient", "triremesh",
                      "deconstruct mesh", "construct mesh", "attractor color", "brep mesh"],
        "tags": ["expert", "comparison", "mesh", "vertex-color", "distance", "gradient", "triremesh"],
        "trigger_intents": [
            "color mesh vertices by distance to point",
            "triremesh with gradient vertex coloring",
            "distance-based mesh color mapping",
            "automatic bounds for gradient color range",
            "construct mesh with vertex colors from distance",
            "brep to colored triangulated mesh"
        ],
    },
    {
        "image": "9-4",
        "name": "Alternating Geometry via Path Mapper Modulus — Circle/Polygon Pattern",
        "cluster_type": "single",
        "brief": "Uses Partition List and Path Mapper with modulus expression to split points into two alternating groups for circle and polygon geometry",
        "context": (
            "Point (60 pts) feeds Partition List (Size=20, 3 branches), then Partition List (Size=5, 12 branches of 5). "
            "Path Mapper uses expression {A;B}{i} -> {(A+B)%2}{i}, remapping 12 branches into 2 based on even/odd. "
            "Explode Tree separates {0} and {1} (each N=30). Circle (R=1.33) to Surface to Custom Preview red. "
            "Polygon (R=1.33) to Surface to Custom Preview green. Annotation panels show the math: A+B and (A+B)%2. "
            "Separate Modulus example shows 20%3=2."
        ),
        "solution_principle": (
            "Path Mapper's modulus expression {(A+B)%2} on multi-level branch indices creates a checkerboard alternation "
            "pattern, enabling different geometry types at alternating grid positions without explicit conditional logic."
        ),
        "components": ["Point", "Partition List", "Param Viewer", "Panel", "Point List", "Path Mapper",
                        "Explode Tree", "Number Slider", "Circle", "Polygon", "Surface", "Custom Preview", "Modulus"],
        "keywords": ["path mapper", "modulus", "alternating", "checkerboard", "partition list",
                      "branch remapping", "circle", "polygon", "data tree", "expression"],
        "tags": ["expert", "path-mapper", "data-trees", "modulus", "alternating-pattern", "branch-manipulation"],
        "trigger_intents": [
            "how to alternate geometry types using path mapper",
            "checkerboard pattern with data tree branch indices",
            "path mapper modulus expression for alternating groups",
            "split points into two alternating sets with partition list",
            "use modulus on branch paths to create pattern variation",
            "assign different geometry to even and odd grid positions"
        ],
    },
    {
        "image": "9-5",
        "name": "Alternating Geometry via Path Mapper with Division/Modulus — MultiPipe",
        "cluster_type": "progression",
        "brief": "Extends Path Mapper alternation using combined modulus and integer division expressions to create 20 branches, then interpolates curves for MultiPipe mesh output",
        "context": (
            "Same data prep as 9-4: Point (60 pts) through double Partition List. Path Mapper uses expression "
            "{A;B}{i} -> {(A+B)%2 ; B\\2} combining modulus AND integer division to remap 12 branches into 20. "
            "Param Viewer confirms 20 branches. Output feeds Interpolate (Vertices, Degree, Periodic, KnotStyle). "
            "Curves feed MultiPipe (NodeSize, EndOffset, Stratification, Segments). Custom Preview with color '0;0.9'. "
            "Annotation panels show B\\2 creating sub-groupings. Reference: Division (13/5=2.6), Integer Division "
            "(13/5=2), Modulus (13%5=3)."
        ),
        "solution_principle": (
            "Combining modulus and integer division in Path Mapper expressions ({(A+B)%2 ; B\\2}) creates multi-level "
            "branch hierarchies from flat grids, enabling complex spatial groupings that can be interpolated into curves "
            "for mesh generation via MultiPipe."
        ),
        "components": ["Point", "Partition List", "Param Viewer", "Panel", "Point List", "Path Mapper",
                        "Interpolate", "Number Slider", "MultiPipe", "Custom Preview", "Division",
                        "Integer Division", "Modulus"],
        "keywords": ["path mapper", "integer division", "modulus", "multipipe", "interpolate",
                      "branch hierarchy", "curve network", "mesh pipe", "expression"],
        "tags": ["expert", "progression", "path-mapper", "data-trees", "integer-division", "multipipe"],
        "trigger_intents": [
            "path mapper with integer division and modulus combined",
            "create curve network from point grid using path mapper",
            "multipipe from interpolated curves through data tree branches",
            "combine modulus and integer division in path mapper expression",
            "generate mesh pipe network from structured point data",
            "how to create multi-level branch paths from flat indices"
        ],
    },
    {
        "image": "9-6",
        "name": "Full Pipeline: Points to Volumetric Mesh — Curve To Volume, TriRemesh, Weaverbird",
        "cluster_type": "culmination",
        "brief": "Complete pipeline from structured points through path mapper, interpolation, volumetric conversion, smoothing, remeshing, subdivision, and Weaverbird thickening.",
        "context": (
            "Extends 9-5 pipeline into full volumetric mesh workflow. Left: Point (60 pts) through double Partition List, "
            "Path Mapper {A;B}{i} -> {(A+B)%2 ; B\\2} to 20 branches. Middle: Interpolate creates curves. "
            "Create Settings (Voxel Size=1, Bandwidth, Isovalue, Adaptivity). Curve To Volume (Curves, Radius=1.5, Settings). "
            "Smooth Volume. Volume to Mesh. Right: TriRemesh (Length=1), Weighted Loop Subdivision, Snub+3 (T0=0.720, "
            "T1=0.756), Weaverbird's Mesh Thicken (Distance=0.05). Custom Preview gray."
        ),
        "solution_principle": (
            "A full fabrication-ready pipeline chains data tree manipulation (Path Mapper), curve interpolation, volumetric "
            "modeling (Curve To Volume + Smooth Volume), mesh conversion, remeshing, subdivision, and Weaverbird operations "
            "to transform abstract point structures into physically realizable 3D mesh objects."
        ),
        "components": ["Point", "Partition List", "Param Viewer", "Panel", "Point List", "Path Mapper",
                        "Interpolate", "Curve To Volume", "Create Settings", "Smooth Volume", "Volume to Mesh",
                        "TriRemesh", "Weighted Loop Subdivision", "Snub+3", "Weaverbird's Mesh Thicken",
                        "Number Slider", "Custom Preview"],
        "keywords": ["volumetric", "curve to volume", "smooth volume", "triremesh", "weaverbird",
                      "mesh thicken", "snub", "subdivision", "path mapper", "fabrication"],
        "tags": ["expert", "culmination", "volumetric-modeling", "mesh-processing", "weaverbird",
                 "triremesh", "fabrication-pipeline"],
        "trigger_intents": [
            "full pipeline from points to thickened mesh structure",
            "curve to volume with smooth volume and triremesh workflow",
            "weaverbird mesh thicken with snub subdivision pipeline",
            "volumetric modeling from interpolated curves in grasshopper",
            "convert curve network to remeshed thickened mesh",
            "complete fabrication pipeline with path mapper and weaverbird"
        ],
    },

    # ── LESSON 10: Applied Expert Projects ──
    {
        "image": "10-1",
        "name": "Space Frame Structure — Isotrim, Weave, Brep Edges, Pipe, Extrude",
        "cluster_type": "culmination",
        "brief": "Builds a parametric space frame from a subdivided plane surface using isotrim panels, weaved point patterns, pipe members, and node spheres with multi-material preview.",
        "context": (
            "Starts with Construct Domain (-40 to 40) into Plane Surface, moved via Unit Z (20.00). Divide Domain2 (count=5) "
            "and Isotrim extract sub-surfaces. Explode extracts curve segments, Point On Curve (0.500) gets midpoints, "
            "Discontinuity extracts corners. Unit Z creates vertical offsets. Two Move components with Unit Z feed into Weave "
            "to interleave streams. Lines between points, Loft creates surfaces. Area centroids with Negative+Unit Z+Move "
            "create downward-displaced geometry. Deconstruct Brep, Brep Edges extract naked edges. Unit Vector, Reverse, "
            "Multiplication (0.20) create offsets. Three Pipe components (radii 0.20, 0.30, 0.55). Extrude creates panels. "
            "Three Custom Previews: WHITE (panels), GRAY (pipes), RED (Sphere nodes)."
        ),
        "solution_principle": (
            "Space frames require multi-level structural logic — subdivide into panels, extract midpoints and corners at "
            "different heights, weave point streams for diagonal bracing, materialize as pipes of varying radii with node "
            "spheres."
        ),
        "components": ["Construct Domain", "Plane Surface", "Move", "Unit Z", "Number Slider", "Divide Domain2",
                        "Isotrim", "Explode", "Point On Curve", "Discontinuity", "Subtraction", "Point List",
                        "Weave", "Line", "Loft", "Area", "Negative", "Deconstruct Brep", "Brep Edges",
                        "Unit Vector", "Reverse", "Multiplication", "Pipe", "Extrude", "Sphere",
                        "Custom Preview", "Panel", "Param Viewer"],
        "keywords": ["space frame", "structure", "isotrim", "weave", "pipe", "brep edges", "node sphere",
                      "truss", "architectural structure", "multi-material"],
        "tags": ["expert", "culmination", "space-frame", "structure", "isotrim", "weave", "pipe", "architectural"],
        "trigger_intents": [
            "how to build a space frame in grasshopper",
            "parametric truss structure from subdivided surface",
            "isotrim to pipe structural members",
            "weave points for diagonal bracing pattern",
            "multi-material custom preview with pipes and panels",
            "space frame with node spheres and tube members"
        ],
    },
    {
        "image": "10-2",
        "name": "Undulating Facade Panel System — Graph Mapper, Pull Point, Contour, Loft, Extrude",
        "cluster_type": "culmination",
        "brief": "Creates a wavy facade panel system by deforming a rectangular surface with attractor-driven Graph Mapper displacement, then slicing with dual-direction contours lofted and extruded into panels.",
        "context": (
            "XZ Plane feeds Rectangle (15x4), Boundary Surfaces, Divide Surface (U=50, V=25). MD Slider (0.39;0.22) "
            "feeds Evaluate Surface for attractor point. Pull Point finds distance to division points. Bounds, "
            "Remap Numbers (target 0.6 to 0.9). Graph Mapper (sinusoidal wave, ~4 periods). Multiplication (2.44), "
            "Unit Y, Reverse, Move displaces points. Surface From Points reconstructs. Two Contour components "
            "(Unit X, distances 0.20 and 0.50). Loft, Extrude with Unit X. Custom Preview GRAY."
        ),
        "solution_principle": (
            "Facade panels combine surface deformation with sectioning — Pull Point distances through Graph Mapper create "
            "proximity-based undulation, dual-direction Contour slicing with Loft and Extrude turns organic surface into "
            "buildable panel strips."
        ),
        "components": ["XZ Plane", "Rectangle", "Boundary Surfaces", "Divide Surface", "MD Slider",
                        "Evaluate Surface", "Pull Point", "Bounds", "Remap Numbers", "Graph Mapper",
                        "Multiplication", "Unit Y", "Reverse", "Move", "Surface From Points", "Contour",
                        "Unit X", "Loft", "Extrude", "Custom Preview", "Number Slider"],
        "keywords": ["facade", "panel system", "graph mapper", "pull point", "attractor", "contour",
                      "loft", "extrude", "undulating", "surface deformation", "wave pattern"],
        "tags": ["expert", "culmination", "facade", "attractor", "graph-mapper", "contour", "panels"],
        "trigger_intents": [
            "attractor-driven undulating facade panels",
            "graph mapper wave deformation on surface",
            "contour and loft facade panel system",
            "pull point distance to graph mapper displacement",
            "parametric wavy facade from rectangular surface",
            "dual direction contour slicing for panel strips"
        ],
    },
    {
        "image": "10-3",
        "name": "Parametric Tower — Rotate, Offset Curve, Extrude, Ruled Surface, Weave, Loft",
        "cluster_type": "culmination",
        "brief": "Constructs a parametric tower by stacking and rotating floor plate curves at incremental heights, creating extruded floor slabs, offset facade walls, ruled surface connections, and woven lofted skin.",
        "context": (
            "Two Curve references (floor plates). Series (step=3.00, count=35) generates heights via Unit Z. Both curves "
            "moved up with Move. Area centroids extracted, Line+Curve Middle finds midpoint. Two Rotate components twist "
            "curves around midpoint (angle step=10). Extrude creates floor slabs. Offset Curve (distance=-1.00) creates "
            "facade setback. Unit Z+Extrude+Cap Holes for walls, Custom Preview WHITE. Merge two curve streams, "
            "Ruled Surface with Offset Surface (0.02) for connections, Custom Preview GRAY. Weave interleaves curves, "
            "Loft with Offset Surface for continuous twisted skin."
        ),
        "solution_principle": (
            "Parametric towers combine stacking (Series+Unit Z+Move), progressive rotation, and multiple facade systems — "
            "Extrude+Cap Holes for slabs, Offset Curve for setbacks, Ruled Surface for connections, Weave+Loft+Offset "
            "Surface for continuous skin."
        ),
        "components": ["Curve", "Series", "Unit Z", "Move", "Area", "Line", "Curve Middle", "Rotate",
                        "Surface", "Number Slider", "Extrude", "Offset Curve", "Negative", "Subtraction",
                        "Cap Holes", "Merge", "Ruled Surface", "Offset Surface", "Weave", "Loft", "Custom Preview"],
        "keywords": ["tower", "parametric tower", "rotate", "floor plates", "facade", "ruled surface",
                      "offset curve", "offset surface", "weave", "loft", "stacking", "twisting"],
        "tags": ["expert", "culmination", "tower", "rotation", "facade", "ruled-surface", "weave", "architectural"],
        "trigger_intents": [
            "parametric twisting tower with floor plates",
            "rotate and stack curves for tower massing",
            "ruled surface facade between floor levels",
            "weave and loft twisted tower skin",
            "offset curve for facade wall setback in tower",
            "complete parametric tower with multiple facade systems"
        ],
    },
    {
        "image": "10-4",
        "name": "Field Line Hair System — Point Charge, Spin Force, Merge Fields, Field Line, Pipe",
        "cluster_type": "single",
        "brief": "Uses vector fields (Point Charge + Spin Force) to generate field lines from circle division points, piped into a hair-like system on a surface",
        "context": (
            "XY Plane + Slider (30) to Plane Surface, Custom Preview RED. Area Centroid, Scale (0.85), "
            "Populate Geometry (count=20, seed=149). Point Charge (charge=3, decay=2.5) from populated points. "
            "Spin Force (strength~150, radius~150). Merge Fields combines both. Circle (R=12) divided by "
            "Divide Curve, seed points for Field Line (steps, accuracy from sliders). Extrude with Unit Z (1.20). "
            "Pipe (R=0.1), Custom Preview WHITE."
        ),
        "solution_principle": (
            "Vector fields (Point Charge for radial attraction, Spin Force for rotational curl) can be merged and sampled "
            "via Field Line to produce organic flowing curve networks — foundation for hair, flow visualization, and "
            "wind-driven generative patterns."
        ),
        "components": ["XY Plane", "Plane Surface", "Custom Preview", "Area", "Scale", "Populate Geometry",
                        "Point Charge", "Spin Force", "Merge Fields", "Circle", "Divide Curve", "Field Line",
                        "Extrude", "Unit Z", "Pipe", "Number Slider", "Panel"],
        "keywords": ["field lines", "vector field", "point charge", "spin force", "merge fields",
                      "hair system", "organic curves", "flow lines", "populate geometry"],
        "tags": ["expert", "fields", "vector-fields", "generative", "organic", "flow", "pipe"],
        "trigger_intents": [
            "create hair-like strands using vector fields",
            "use point charge and spin force to generate flow lines",
            "field line grasshopper definition with merged fields",
            "organic flowing curves from vector field on surface",
            "generate field lines from point charges and pipe them",
            "vector field flow visualization in grasshopper"
        ],
    },
    {
        "image": "10-5",
        "name": "Populate Solid Brep with Brep|Plane Sections — Solid Union, Plane Normal, Pipe",
        "cluster_type": "single",
        "brief": "Populates random points inside a solid union of boxes, computes plane normals from vectors to origin, intersects with brep to get section curves, then pipes them for a porcupine-like effect",
        "context": (
            "Domain Box (-20 TO 20, -10 TO 10, 90) feeds Populate 3D (count=24, seed=336). Points become centers for "
            "Center Box (X=12, Y=12). Solid Union merges boxes. Offset Surface (distance=2.02). Populate 3D (count=71, "
            "seed=248) inside solid. Vector 2Pt (point to origin 0,0,0), Unitize, Plane Normal creates oriented planes. "
            "Brep|Plane intersects solid, section curves feed Pipe (R=0.20), Custom Preview WHITE. Solid brep in GRAY. "
            "Second section: Contour (distance=3.00), Offset Curve (0.77), Extrude (Unit Z 0.30), Cap Holes."
        ),
        "solution_principle": (
            "Populating points inside a solid and using vector-to-origin with Plane Normal creates radially-oriented section "
            "planes. Intersecting with Brep|Plane produces spike-like curves for piping — demonstrating how brep intersection "
            "with populate creates porcupine/spike effects on complex solids."
        ),
        "components": ["Domain Box", "Populate 3D", "Center Box", "Solid Union", "Offset Surface",
                        "Populate Geometry", "Vector 2Pt", "Plane Normal", "Brep | Plane", "Curve", "Pipe",
                        "Custom Preview", "Contour", "Unit Z", "Offset Curve", "Extrude", "Cap Holes",
                        "Number Slider", "Panel"],
        "keywords": ["solid union", "populate 3D", "brep plane intersection", "plane normal", "vector 2pt",
                      "pipe", "contour", "porcupine", "section curves", "center box"],
        "tags": ["expert", "brep", "solid", "intersection", "populate", "section", "pipe"],
        "trigger_intents": [
            "populate points inside a solid and create spike curves",
            "brep plane intersection from populated points",
            "solid union of boxes with porcupine pipe effect",
            "use plane normal and brep plane to section a solid",
            "random section curves through a solid brep piped",
            "contour and offset curve detail on solid geometry"
        ],
    },
    {
        "image": "10-6",
        "name": "Iterative Fractal Branching Tree with Anemone Loop — Perp Frame, Polygon, Amplitude",
        "cluster_type": "culmination",
        "brief": "Full iterative fractal tree pipeline using Anemone Loop to recursively branch lines into polygonal child segments with perpendicular framing, vector amplitude scaling, and pipe/sphere visualization",
        "context": (
            "Largest definition in the course (27773x6263px). Two major regions. Top (white): Construct Point + Unit Z "
            "feed Line SDL (length=20). Button triggers Loop Start (Anemone, repeat~3). Loop body: End Points extracts "
            "Start/End, Vector 2Pt computes direction, Unit Vector, Amplitude scales. Perp Frame evaluates at parameters "
            "(5.53, count=4). Polygon (segments=3, triangles) Exploded to Vertices. removeDuplicatePts, Point List, "
            "Division (/3=6.6). Move repositions using Amplitude vector. Line creates new segments. Loop End feeds back. "
            "Param Viewer shows 256 branches first iteration, 2304 second — exponential growth. Output: Pipe (R=0.10) "
            "Custom Preview GRAY, End Points to Sphere (R=0.40) Custom Preview RED. Bottom (purple): complete duplicate "
            "of inner loop logic for the recursive body."
        ),
        "solution_principle": (
            "Anemone's Loop Start/End enables true iterative recursion in Grasshopper for fractal geometry. Each iteration "
            "feeds output lines back as input, creating exponentially branching tree structures. Perpendicular framing, "
            "polygonal vertex extraction, and vector amplitude scaling achieve L-system-like branching without scripting."
        ),
        "components": ["Construct Point", "Unit Z", "Line SDL", "Number Slider", "Button", "Loop Start",
                        "Loop End", "End Points", "Vector 2Pt", "Unit Vector", "Amplitude", "Curve",
                        "Construct Domain", "Perp Frame", "Polygon", "Explode", "removeDuplicatePts",
                        "Point List", "Division", "Move", "Point", "Line", "Param Viewer", "Panel",
                        "Pipe", "Sphere", "Custom Preview"],
        "keywords": ["fractal", "branching", "tree", "iteration", "loop", "anemone", "recursive",
                      "L-system", "perpendicular frame", "polygon vertices", "vector amplitude",
                      "exponential growth", "pipe", "sphere joints"],
        "tags": ["expert", "culmination", "iteration", "fractal", "anemone", "recursion", "branching",
                 "tree-structure", "loop", "vector-math"],
        "trigger_intents": [
            "how to create a fractal branching tree in Grasshopper",
            "iterative recursion with Anemone Loop Start End",
            "L-system branching structure using loops",
            "recursive line subdivision with polygon vertices",
            "exponential branching with perpendicular frames",
            "fractal tree with pipe visualization and sphere joints"
        ],
    },
    {
        "image": "10-7",
        "name": "Twisted Lofted Louver with Flow — Rectangle, Twist, Flow, Rotate, Loft, Offset Surface",
        "cluster_type": "single",
        "brief": "Creates a twisted rectangular profile, maps it onto a curved path using Flow, then arrays with Rotate and lofts into an offset solid louver panel system",
        "context": (
            "Number Sliders feed Rectangle. Deconstruct Brep gets Edges/Faces/Vertices. Two List Item pick edges, "
            "two Curve Middle extract midpoints defining twist axis. Multiplication (slider*360) feeds Twist around axis. "
            "Boolean Toggle controls twist. Explode gets segments. Line connects midpoints. Flow maps twisted profiles "
            "from Base to Target (Circle). Param Viewer shows tree structure. Rotate (angle from slider), Loft creates "
            "surfaces. Offset Surface (with Create Solid toggle) thickens. Explode Tree separates for Custom Preview "
            "WHITE and RED."
        ),
        "solution_principle": (
            "Flow remaps geometry from a straight reference to a curved target — combined with Twist for profile deformation "
            "and Loft for surface generation, creates complex architectural louver or facade panel systems."
        ),
        "components": ["Rectangle", "Deconstruct Brep", "List Item", "Curve Middle", "Multiplication",
                        "Twist", "Boolean Toggle", "Explode", "Line", "Circle", "Flow", "Param Viewer",
                        "Rotate", "Loft", "Offset Surface", "Explode Tree", "Custom Preview", "Number Slider"],
        "keywords": ["twist", "flow", "loft", "louver", "facade", "rotate", "offset surface",
                      "spatial mapping", "profile", "architectural"],
        "tags": ["expert", "flow", "twist", "loft", "facade", "architectural", "spatial-mapping"],
        "trigger_intents": [
            "twist a profile and flow it along a curve",
            "create twisted louver panels with flow component",
            "map geometry from straight to curved path using flow",
            "lofted facade panels with twist deformation",
            "use flow to remap twisted rectangles onto a surface",
            "architectural louver system with rotate and loft"
        ],
    },
    {
        "image": "10-8",
        "name": "Peacock Plugin Triangulated Pipe Structure — Arc, Graph Mapper, Triangle Panels B, Random Cull",
        "cluster_type": "single",
        "brief": "Uses Peacock plugin's Triangle Panels B to panelize a lofted surface from graph-mapped arcs, randomly culls panels and pipes the edges for a triangulated structural frame",
        "context": (
            "Title 'PEACOCK'. Range (0 TO 360, steps=20) feeds Rotate on XZ Plane. Second Range feeds Graph Mapper "
            "(curve, domain -0.75 TO 0.75) modulating radius. Arc components create arcs at rotated planes. "
            "Loft (slider=50). Rectangle (0.01) feeds Pipe Custom (R=0.75). Triangle Panels B (Peacock, U/V divisions). "
            "Pipe (R=0.02) for framing. List Length, Division /2, Random (seed=123), Cull Index removes random panels. "
            "Custom Preview WHITE for panels, GRAY and RED via List Item for selected elements."
        ),
        "solution_principle": (
            "Peacock's Triangle Panels B provides triangulated panelization of freeform surfaces. Combined with random "
            "culling via Cull Index, creates perforated structural frames — extending GH's native panelization for "
            "architectural facade design."
        ),
        "components": ["XZ Plane", "Range", "Rotate", "Graph Mapper", "Arc", "Loft", "Rectangle",
                        "Pipe Custom", "Triangle Panels B", "Pipe", "List Length", "Division", "Random",
                        "Cull Index", "List Item", "Custom Preview", "Number Slider", "Curve", "Panel"],
        "keywords": ["peacock", "triangle panels", "panelization", "triangulation", "random cull",
                      "pipe custom", "graph mapper", "arc", "loft", "facade", "lattice"],
        "tags": ["expert", "peacock-plugin", "panelization", "triangulation", "facade", "lattice", "random-cull"],
        "trigger_intents": [
            "triangulate a lofted surface using peacock plugin",
            "create triangulated facade panels with random openings",
            "peacock triangle panels B with pipe frame structure",
            "graph mapper controlled rotational loft with panelization",
            "randomly cull triangulated panels for perforated facade",
            "use peacock to panelize a vase form with triangles"
        ],
    },
    {
        "image": "10-9",
        "name": "Twisted Polygon Facade with Solid Difference Framing — Perp Frames, Weave, Boundary Surfaces",
        "cluster_type": "culmination",
        "brief": "Creates twisted polygonal tube along a curve, builds boundary surfaces from interleaved division points, extrudes along normals, uses solid difference with piped centroid curves for framed facade.",
        "context": (
            "Curve with Perp Frames (Count=47). Polygons (R=8.52, Segments=4) at each frame, rotated via Graph Mapper "
            "(domain 15:270, linear ramp). Scaled (Factor=0.85) using Area centroids. Both original and scaled polygons "
            "divided (Count=12), Dispatch separates alternating points. Two Dispatch streams feed Weave with Boolean "
            "Toggle (True). Interpolate creates curves. Boundary Surfaces from closed curves. Area centroids, "
            "Surface Closest Point, Evaluate Surface for normals. Division (0.50) scales normal, Extrude along normal. "
            "Split Brep with Plane Surface (-100 TO 100) as cutter. List Item (index 0) selects half. Area centroids "
            "of results to Interpolate, Pipe (R=1.25). Solid Difference subtracts pipes from panels. Custom Preview "
            "WHITE (panels) and RED (pipe frame)."
        ),
        "solution_principle": (
            "Full parametric facade: twisting polygons along curve with Graph Mapper rotation, Dispatch+Weave to interleave "
            "division points from scaled/unscaled copies creating diamond-pattern boundary surfaces, extrusion along normals, "
            "Solid Difference with piped centroid curves for hollow framed panels."
        ),
        "components": ["Curve", "Perp Frames", "Polygon", "Rotate", "Number Slider", "Range", "Graph Mapper",
                        "Scale", "Area", "Divide Curve", "Dispatch", "Weave", "Boolean Toggle", "Interpolate",
                        "Boundary Surfaces", "Surface Closest Point", "Evaluate Surface", "Division", "Extrude",
                        "Split Brep", "Plane Surface", "Panel", "List Item", "Pipe", "Solid Difference",
                        "Custom Preview"],
        "keywords": ["facade", "twisted polygon", "perp frames", "graph mapper", "dispatch", "weave",
                      "boundary surfaces", "solid difference", "pipe frame", "extrude normal",
                      "diamond pattern", "parametric panel"],
        "tags": ["expert", "culmination", "facade", "solid-difference", "perp-frames", "graph-mapper",
                 "weave", "boundary-surfaces"],
        "trigger_intents": [
            "create twisted polygon facade along curve",
            "parametric panel system with solid difference framing",
            "dispatch and weave interleaved boundary surfaces",
            "extrude surfaces along normals and split with plane",
            "graph mapper progressive rotation of polygons along path",
            "diamond pattern facade with pipe frame subtraction"
        ],
    },
    {
        "image": "10-10",
        "name": "Woven Cylindrical Surface — Shatter, Flip Matrix, Sift Pattern, Loft",
        "cluster_type": "culmination",
        "brief": "Divides a circle into segments, creates vertical lines, shatters with shifted data trees, uses Sift Pattern to separate alternating segments, displaces in opposite directions, and lofts into a woven cylindrical surface.",
        "context": (
            "Circle (R=35) divided by Divide Curve (Count=6). Series generates indices. Shift List offsets pattern. "
            "Unit Z creates vertical vectors. Line SDL creates vertical lines. Pipe (R=1.00) Custom Preview RED. "
            "Second Divide Curve subdivides lines, Shatter breaks them. Flip Matrix transposes tree (24 branches N=10 "
            "to 10 branches N=24). Tree Statistics extracts paths, Repeat Data, Tree Branch selects. Sift Pattern "
            "separates Output 0 and 1. Curve Middle finds midpoints, Curve Closest Point on reference lines, "
            "Vector 2Pt computes directions. Negative inverts one vector. Amplitude (1.50) scales both. Two Move "
            "components displace groups in opposite directions. Combine Data, Loft (0.62). Offset Surface. "
            "Custom Preview WHITE."
        ),
        "solution_principle": (
            "Advanced data tree manipulation for weaving: Flip Matrix transposes row/column organization of shattered curve "
            "segments, Sift Pattern separates alternating segments, then perpendicular displacement via Curve Middle + "
            "Curve Closest Point + Vector 2Pt pushes alternating segments in opposite directions before lofting into "
            "a woven surface structure."
        ),
        "components": ["Circle", "Number Slider", "Divide Curve", "List Length", "Series", "Shift List",
                        "Multiplication", "Unit Z", "Line SDL", "Pipe", "Custom Preview", "Shatter",
                        "Flip Matrix", "Param Viewer", "Tree Statistics", "Repeat Data", "Tree Branch",
                        "Construct Point", "Sift Pattern", "Curve", "Curve Middle", "Curve Closest Point",
                        "Vector 2Pt", "Negative", "Amplitude", "Move", "Combine Data", "Loft",
                        "Offset Surface"],
        "keywords": ["weaving", "woven surface", "flip matrix", "sift pattern", "shatter", "shift list",
                      "curve middle", "curve closest point", "vector 2pt", "amplitude", "loft",
                      "cylindrical weave", "data tree transpose", "alternating displacement"],
        "tags": ["expert", "culmination", "weaving", "data-trees", "flip-matrix", "sift-pattern",
                 "loft", "vector-displacement", "cylindrical"],
        "trigger_intents": [
            "create woven cylindrical surface from circle divisions",
            "use flip matrix and sift pattern for weaving pattern",
            "shatter curves and displace alternating segments for weave",
            "data tree manipulation for basket weave surface",
            "loft alternating displaced curve segments into woven structure",
            "transpose data trees with flip matrix for weaving"
        ],
    },
]


def build_note(lesson: dict) -> dict:
    image = lesson["image"]
    note_id = stable_id(image)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    lesson_num = int(image.split("-")[0])
    lesson_labels = {
        7: "Advanced Mesh and Voronoi",
        8: "Mesh Operations and Digital Fabrication",
        9: "Path Mapper Volumetric Modeling Advanced Coloring",
        10: "Applied Expert Projects",
    }
    category_label = lesson_labels.get(lesson_num, f"Lesson {lesson_num}")

    return {
        "note_id": note_id,
        "note_type": "teaching",
        "name": f"Expert {image}: {lesson['name']}",
        "brief": lesson["brief"],
        "version": "1.0",
        "created": now,
        "context": lesson["context"],
        "keywords": lesson["keywords"],
        "category": f"Expert - {category_label}",
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
    parser = argparse.ArgumentParser(description="Extract teaching notes from Expert tutorial images")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    print(f"Expert Tutorial Extraction")
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
