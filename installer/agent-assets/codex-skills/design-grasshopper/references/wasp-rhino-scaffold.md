# Wasp Rhino Scaffold — Cross-Application Preparation

Rook's unique capability: bridge Rhino geometry and Grasshopper logic in a single
workflow. For Wasp, this means inspecting, organizing, validating, and augmenting
the Rhino scene BEFORE the GH definition touches it. The design phase doesn't just
query knowledge — it actively prepares the Rhino scene so the plan phase has clean,
validated, organized inputs.

Load this reference during the design-grasshopper explore phase when Wasp intent is
detected, AFTER the decision tree in wasp-domain-context.md identifies the concept set.

---

## The Bridge: Rhino → GH → Wasp

```
┌─── RHINO (Rook prepares) ────────────────────────────────┐
│                                                           │
│  1. Inspect scene → find candidate part geometry          │
│  2. Validate geometry → closed? scale? mesh needed?       │
│  3. Organize layers → Wasp::Parts::PartA, etc.            │
│  4. Analyze faces → propose connection points + normals   │
│  5. Create auxiliary geometry → ground plane, attractors  │
│  6. Name objects → stable references for GH parameters    │
│                                                           │
└──────────────────────┬────────────────────────────────────┘
                       │ geometry references by layer + name
                       ▼
┌─── GRASSHOPPER (skill pipeline handles) ─────────────────┐
│                                                           │
│  Reference by layer → Connection planes → Parts → Rules  │
│  → Fields → Constraints → Aggregation                    │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

---

## Step 1: Scene Inspection

Before asking the user anything about Wasp, inspect what's already there.

```python
# What objects exist?
rhino_objects()
# → Look for: closed breps, meshes, named objects, layer organization

# What layers exist?
rhino_layers()
# → Look for: existing part-like organization, geometry groups

# Document units
rhino_document()
# → Check units (meters for DisCo, any for basic aggregation)
```

### What to Look For

| Finding | Implication |
|---------|-------------|
| Closed breps on organized layers | Likely candidate parts — user has geometry ready |
| Named objects ("panel_A", "column") | User has part types in mind — use their names |
| Meshes | Ready for DisCo export, or user works in mesh |
| Open surfaces / curves only | NOT part-ready — need to create or close geometry |
| Empty scene | Need to create everything from description |
| Mixed scales (some objects 10x larger) | Possible scale mismatch — ask user |

### Present Findings

```
Rhino scene analysis:
- 3 closed breps found on layer "Parts" (box 2x1x3m, L-shape 1.5x1.5x3m, connector 0.5x0.5x0.5m)
- Units: meters (good for DisCo if needed)
- No existing layer organization for Wasp
- 1 open surface on "Design" layer (not usable as a Wasp part)
```

---

## Step 2: Geometry Validation

For each candidate part, validate it's Wasp-ready.

```python
# For each candidate brep:
rhino_geometry(guid="<object_guid>")
# → Check: type (brep/mesh), closed?, volume > 0?

rhino_is_closed(guid="<object_guid>")
# → MUST be true for Wasp Parts

rhino_is_valid(guid="<object_guid>")
# → No bad objects — Wasp silently fails on invalid geometry

rhino_measure_bbox(guid="<object_guid>")
# → Dimensions: is this a reasonable discrete part?

rhino_measure_volume(guid="<object_guid>")
# → Volume > 0 confirms it's a solid
```

### Validation Checklist

| Check | Tool | Pass Condition | If Fails |
|-------|------|---------------|----------|
| Closed | `rhino_is_closed` | true | Ask user to close, or cap holes |
| Valid | `rhino_is_valid` | true | `rhino_command("_Check")` then repair |
| Has volume | `rhino_measure_volume` | > 0 | Open surface — not a solid |
| Reasonable scale | `rhino_measure_bbox` | Dimensions > 0.01m, < 100m | Scale mismatch — ask user |
| Mesh (if DisCo) | `rhino_geometry` type | Mesh | Convert: `rhino_mesh_from_brep` |

### Ask If Validation Fails

```
Part_A (box on "Parts" layer) has an issue:
- It's an open polysurface (not closed)
(a) I can cap it (close open edges) — works if edges are planar
(b) You close it manually and tell me when ready
(c) Skip this object — it's not a part
```

---

## Step 3: Layer Organization

Create a consistent layer hierarchy that the GH definition can reference by layer name.
This is the bridge — GH geometry parameters reference by layer, making the Rhino→GH
connection clean and maintainable.

### Layer Convention

```
Wasp/
├── Parts/
│   ├── PartA          ← part geometry (1 closed brep per layer)
│   ├── PartB
│   └── PartC
├── Connections/
│   ├── PartA          ← connection reference planes/points for PartA
│   ├── PartB
│   └── PartC
├── Fields/            ← field source geometry (optional)
│   ├── Attractors     ← point objects
│   ├── Boundaries     ← curves
│   └── Surfaces       ← surface fields
├── Constraints/       ← constraint reference geometry (optional)
│   ├── GroundPlane    ← support surface
│   ├── Boundary       ← containment mesh/plane
│   └── Colliders      ← additional collision geometry
└── Output/            ← for baked aggregation results
    └── Aggregation
```

### Creating Layers

```python
# Create the Wasp layer hierarchy
rhino_layer_create(name="Wasp", color="128,128,128")
rhino_layer_create(name="Wasp::Parts", color="200,80,80")
rhino_layer_create(name="Wasp::Parts::PartA", color="200,80,80")
rhino_layer_create(name="Wasp::Parts::PartB", color="80,200,80")
rhino_layer_create(name="Wasp::Connections", color="80,80,200")
rhino_layer_create(name="Wasp::Connections::PartA", color="80,80,200")
# ... etc., based on how many parts are identified
```

### Moving Geometry to Layers

```python
# Move one approved existing object without moving unrelated layer contents.
rhino_execute(code="""
import System
import Rhino
doc = Rhino.RhinoDoc.ActiveDoc
obj = doc.Objects.FindId(System.Guid('<guid>'))
layer_index = doc.Layers.FindByFullPath('Wasp::Parts::PartA', -1)
if obj is None or layer_index < 0:
    raise Exception('object or target layer not found')
attrs = obj.Attributes.Duplicate()
attrs.LayerIndex = layer_index
if not doc.Objects.ModifyAttributes(obj, attrs, True):
    raise Exception('failed to update object layer')
doc.Views.Redraw()
""")
rhino_objects(layer="Wasp::Parts::PartA")

# Or create typed geometry on the target layer from the start:
rhino_create(
    type="BOX",
    origin=[0, 0, 0],
    width=2,
    depth=1,
    height=3,
    layer="Wasp::Parts::PartA",
)
```

### Naming Objects

```python
# Name objects for stable GH parameter references
rhino_execute(code="""
import System
import Rhino
doc = Rhino.RhinoDoc.ActiveDoc
for raw_id, name in [
    ('<part-a-guid>', 'PartA_geo'),
    ('<part-b-guid>', 'PartB_geo'),
]:
    obj = doc.Objects.FindId(System.Guid(raw_id))
    if obj is None:
        raise Exception('object not found: ' + raw_id)
    attrs = obj.Attributes.Duplicate()
    attrs.Name = name
    if not doc.Objects.ModifyAttributes(obj, attrs, True):
        raise Exception('failed to rename: ' + raw_id)
doc.Views.Redraw()
""")
rhino_objects(name="PartA_geo")
rhino_objects(name="PartB_geo")
```

---

## Step 4: Connection Analysis

The hardest prerequisite. Connections define WHERE parts mate and in WHAT DIRECTION.
Claude analyzes the geometry and proposes connections; the user approves.

### Analysis Protocol

```python
# For each part:

# 1. Get face information
rhino_brep_faces(guid="<part_guid>")
# → Returns face list with: index, area, centroid, normal

# 2. For each face, get the outward normal
rhino_surface_normal(guid="<part_guid>", u=0.5, v=0.5)
# → Normal vector at face center (the connection direction)

# 3. Compute face centers for connection placement
rhino_measure_centroid(guid="<part_guid>")
# → Or use face centroids from brep_faces

# 4. Classify faces by orientation
# Top faces: normal ≈ (0,0,1) → "ceiling" connection type
# Bottom faces: normal ≈ (0,0,-1) → "floor" connection type
# Side faces: normal ⊥ Z → "wall" connection type
```

### Connection Proposal Heuristics

Based on geometry analysis + architectural intent:

| Part Shape | Typical Connections | Connection Types |
|---|---|---|
| **Box / rectangular panel** | 4 side faces (edges) | "wall" or "panel_edge" |
| **Column (tall, narrow)** | Top + bottom | "ceiling", "floor" |
| **Beam (long, horizontal)** | Both ends | "beam_end" |
| **L-shape / bracket** | Open faces at each arm end | "arm_end" |
| **Floor slab (flat, wide)** | Top + bottom, possibly edges | "floor", "ceiling", "slab_edge" |
| **Connector (small cube)** | All 6 faces | "universal" |

### Presenting Connection Proposals

```
Connection analysis for PartA (box 2m x 1m x 3m):

Faces found: 6
 - Face 0: bottom (2x1m, normal -Z) → proposed: "floor" connection
 - Face 1: top (2x1m, normal +Z) → proposed: "ceiling" connection
 - Face 2: front (2x3m, normal +Y) → proposed: "wall" connection
 - Face 3: back (2x3m, normal -Y) → proposed: "wall" connection
 - Face 4: left (1x3m, normal -X) → proposed: "wall_narrow" connection
 - Face 5: right (1x3m, normal +X) → proposed: "wall_narrow" connection

Recommendation: Use faces 2-5 (4 wall connections) for a facade panel assembly.
Skip top/bottom unless parts should also stack vertically.

(a) Accept all 6 connections (stacks + tiles)
(b) Accept 4 side connections only (tiles, no stacking)
(c) Accept 2 connections (front + back only, linear assembly)
(d) Custom selection — tell me which faces
```

### Creating Connection Reference Geometry

After user approves, create reference geometry in Rhino that the GH definition
will use to define Wasp connections:

```python
# For each approved connection:
# Create a point at the face center on the Connections layer
point = rhino_create(
    type="POINT",
    point=[1, 0.5, 1.5],
    layer="Wasp::Connections::PartA",
    name="PartA_conn_wall_front",
)
rhino_geometry(id=point["id"])

# The direction vector comes from the face normal — recorded in the design doc,
# used by GH's "Connection From Direction" component
```

**Alternative approach:** Instead of creating reference geometry for connections,
record the face normals and centroids in the design document and let the GH
definition construct connection planes procedurally (using Vector and Plane
components). This is cleaner for parametric workflows where part geometry might
change size.

---

## Step 5: Auxiliary Geometry

Based on the decision tree results, create supporting geometry.

### Ground Plane (for constrained aggregation)

```python
# If constraints are needed:
rhino_layer_create(name="Wasp::Constraints::GroundPlane", color="180,180,180")
ground_boundary = rhino_create(
    type="RECTANGLE",
    origin=[-50, -50, 0],
    width=100,
    height=100,
    layer="Wasp::Constraints::GroundPlane",
    name="GroundPlaneBoundary",
)
rhino_geometry(id=ground_boundary["id"])
```

### Attractor Points (for field-driven density)

```python
# If field-driven placement is needed:
rhino_layer_create(name="Wasp::Fields::Attractors", color="255,200,0")
# Ask user where attractors should go, or propose from design intent:
# "Dense near the entrance" → place attractor points near entrance coordinates
attractor = rhino_create(
    type="POINT",
    point=[10, 0, 0],
    layer="Wasp::Fields::Attractors",
    name="EntranceAttractor",
)
rhino_geometry(id=attractor["id"])
```

### Boundary Mesh (for containment)

```python
# If parts must stay within a volume:
rhino_layer_create(name="Wasp::Constraints::Boundary", color="180,180,255")
# Create or reference the boundary geometry
# Often this is an existing building envelope or site boundary
```

---

## Step 6: Geometry Creation (When Scene is Empty)

If the user has NO geometry and wants Claude to create parts:

### Simple Architectural Parts

```python
# Facade panel (rectangular box)
panel = rhino_create(
    type="BOX", origin=[0,0,0], width=2, depth=0.1, height=3,
    layer="Wasp::Parts::Panel", name="Panel_geo",
)

# Column (tall, narrow)
column = rhino_create(
    type="CYLINDER", center=[0,0,0], radius=0.3, height=4,
    layer="Wasp::Parts::Column", name="Column_geo",
)

# Connector (small cube at joints)
connector = rhino_create(
    type="BOX", origin=[0,0,0], width=0.5, depth=0.5, height=0.5,
    layer="Wasp::Parts::Connector", name="Connector_geo",
)

# L-bracket from two explicit boxes and a typed boolean union
arm_a = rhino_create(
    type="BOX", origin=[0,0,0], width=1.5, depth=0.3, height=0.3,
    layer="Wasp::Parts::Bracket",
)
arm_b = rhino_create(
    type="BOX", origin=[0,0,0], width=0.3, depth=1.5, height=0.3,
    layer="Wasp::Parts::Bracket",
)
bracket = rhino_boolean(operation="union", ids=[arm_a["id"], arm_b["id"]])
bracket_id = bracket["resultIds"][0]
rhino_geometry(id=bracket_id)
rhino_objects(layer="Wasp::Parts::Bracket")
```

### Ask Before Creating

```
No part geometry found in Rhino. I can create starter parts based on your intent.

Your intent: "modular facade with 3 panel types"

Proposed parts:
1. Panel_Wide (2m x 0.15m x 3m box) — main facade panel
2. Panel_Narrow (1m x 0.15m x 3m box) — filler panel
3. Panel_Corner (1m x 1m x 3m L-shape) — corner piece

Should I create these? You can adjust dimensions or describe different shapes.
```

---

## Step 7: Handoff to Design Document

After the Rhino scene is prepared, the design document captures:

```markdown
## Rhino Scene Preparation (completed during explore)

### Layers Created
| Layer | Contents | Object Count |
|-------|----------|-------------|
| Wasp::Parts::PanelWide | Main panel brep (2x0.15x3m) | 1 |
| Wasp::Parts::PanelNarrow | Filler panel brep (1x0.15x3m) | 1 |
| Wasp::Parts::PanelCorner | Corner L-shape (1x1x3m) | 1 |
| Wasp::Connections::PanelWide | Connection reference points | 4 |
| Wasp::Constraints::GroundPlane | Ground support surface | 1 |

### Geometry Validation
- All parts: closed ✓, valid ✓, volume > 0 ✓
- Units: meters ✓ (DisCo-ready)

### Connection Definitions
| Part | Face | Direction | Type | Centroid |
|------|------|-----------|------|----------|
| PanelWide | Front | (0,1,0) | wall | (1, 0.15, 1.5) |
| PanelWide | Back | (0,-1,0) | wall | (1, 0, 1.5) |
| PanelWide | Left | (-1,0,0) | panel_edge | (0, 0.075, 1.5) |
| PanelWide | Right | (1,0,0) | panel_edge | (2, 0.075, 1.5) |
| ... | ... | ... | ... | ... |

### Auxiliary Geometry
- Ground plane at Z=0 on Wasp::Constraints::GroundPlane
- 3 attractor points on Wasp::Fields::Attractors at (5,0,0), (15,0,0), (25,0,0)
```

This section becomes the **input specification** for the plan phase. The plan
phase reads it and knows exactly which Rhino layers to reference in GH parameters,
what connection directions to use, and what auxiliary geometry is available.

---

## Integration with Existing Skills

### In design-grasshopper (explore phase):

```
1. Detect Wasp intent → load wasp-domain-context.md
2. Walk decision tree → select concept set
3. *** Load wasp-rhino-scaffold.md ***
4. Inspect Rhino scene (Step 1-2)
5. Organize layers (Step 3)
6. Analyze and propose connections (Step 4) — ASK user
7. Create auxiliary geometry (Step 5)
8. If no geometry: propose and create parts (Step 6) — ASK user
9. Record everything in design doc (Step 7)
10. Continue to component selection, wiring design, etc.
```

### In plan-grasshopper (wasp-parts sub-skill):

The plan references organized Rhino layers instead of vague geometry:
```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_BREP_PARAMETER", "pos": [100, 200]}],
)
# Record T1 as $PANEL_WIDE_REF, then reference the approved Rhino object:
gh_set_reference(
    paramGuid=$PANEL_WIDE_REF,
    rhinoObjectId=$PANEL_WIDE_RHINO_ID,
)
gh_get_reference(guid=$PANEL_WIDE_REF)
```

---

## Summary: Who Provides What

| Prerequisite | User Provides | Claude/Rook Provides |
|---|---|---|
| **Part shapes** | Describes or models geometry | Creates simple shapes, validates complex ones |
| **Part organization** | Approves layer structure | Creates layers, moves/names objects |
| **Connection faces** | Approves which faces mate | Analyzes geometry, proposes connections |
| **Connection types** | Approves type labels | Suggests types from orientation analysis |
| **Connection directions** | Verifies normals look correct | Computes from face normals |
| **Ground plane** | Approves location | Creates at world origin or specified Z |
| **Field attractors** | Describes density intent | Places points from description |
| **Boundary volume** | Provides or describes | Creates simple volumes, references existing |
| **Scale/units** | Confirms units are correct | Checks and warns if mismatched |
