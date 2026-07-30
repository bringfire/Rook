# Radial Spiral Chandelier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the phyllotaxis placement field in the open `Chandelier_Circular_Droop-02.gh` copy with an evenly spaced 11-ring radial grid whose progressive ring phase and fin orientation reinforce the same spin.

**Architecture:** Update the existing RhinoCode Python placement component in place while preserving its generated Grasshopper input-coercion preamble, surface reference, outputs, downstream fin generator, and Custom Preview. Replace only the three obsolete placement sliders, rename the script pins and group, and verify the radial tree through live output assertions.

**Tech Stack:** Rhino 8, Grasshopper, Rook MCP tools, RhinoCode Python 3, RhinoCommon, Grasshopper data trees.

## Global Constraints

- Work only in the open `Chandelier_Circular_Droop-02.gh` copy.
- Do not save the Grasshopper document; leave the final save decision to the user.
- Preserve the referenced surface, `ChandelierSmoothLayersCircular`, its corrected hard-edge/outward mesh normals, all fin sliders, Custom Preview, and material wiring.
- Preserve current fin values: panels `2`, minimum layers `2`, extra layers `3`, fin height `380`, gap `46.874`, half-length `74.187`, and half-thickness `13`.
- Use one center point plus 11 adaptive rings.
- Use `Fill = 0.962`, `PhaseStep = 0.35`, and `FinSpin = 55` degrees initially.
- Add no external dependencies and modify no Rook source files.
- Use a fresh `gh_snapshot` epoch before every `gh_edit`.
- Check solve readiness and `gh_errors` after every mutation batch.

---

### Task 1: Establish the Failing Radial-Grid Regression

**Files:**
- Inspect: live `C:\Users\bring\OneDrive\Desktop\260730\Chandelier_Circular_Droop-02.gh`
- Reference: `docs/superpowers/specs/2026-07-30-radial-spiral-chandelier-design.md`

**Interfaces:**
- Consumes: `CircularPhyllotaxis.Points` and `CircularPhyllotaxis.Planes`
- Produces: a recorded failing assertion for the required radial tree shape

- [ ] **Step 1: Confirm the intended live document**

Call `gh_status` and require:

```text
document_name = Chandelier_Circular_Droop-02
solverEnabled = true
solutionState = PostProcess
ready_for_edit = true
```

Stop without mutating the canvas if a different Grasshopper document is active.

- [ ] **Step 2: Capture the fresh canvas mapping**

Call:

```json
{"name":"gh_snapshot","arguments":{"include_data":true,"max_preview_items":1}}
```

Resolve these stable instance GUIDs and require the expected current short IDs:

```text
CircularPhyllotaxis = afddfe28-88bc-4ef2-83f0-c6c64adead3c
ChandelierSmoothLayersCircular = d84ee26c-7472-449b-9982-55bca2dd3254
CircularPhyllotaxis short ID = C122
ChandelierSmoothLayersCircular short ID = C110
```

Require the current placement-control and group mappings:

```text
Count = C111
Fill = C112
Angle = C113
Arms = C114
Panels = C115
MinLayers = C116
ExtraLayers = C117
FinHeight = C118
Gap = C119
HalfLength = C120
HalfThickness = C121
Circular Phyllotaxis — First Pass = G6
```

If a short ID differs, resolve that object by nickname and connection role from the same snapshot before continuing.

- [ ] **Step 3: Run the radial-tree assertion before implementation**

Call `gh_inspect_output` for `Points` and assert:

```javascript
const expectedCounts = [1, 6, 13, 19, 25, 31, 38, 44, 50, 57, 63, 69];
if (result.data_count !== 416) {
  throw new Error(`RED: expected 416 radial points, got ${result.data_count}`);
}
if (result.path_count !== 12) {
  throw new Error(`RED: expected 12 radial branches, got ${result.path_count}`);
}
const actualCounts = result.branches.map(branch => branch.count);
if (JSON.stringify(actualCounts) !== JSON.stringify(expectedCounts)) {
  throw new Error(`RED: expected branch counts ${expectedCounts}, got ${actualCounts}`);
}
```

Expected result before the change:

```text
FAIL: existing phyllotaxis output has 414 points across 13 branches
```

This is the required red test. Do not weaken the expected values.

---

### Task 2: Replace the Three Placement Controls and Group

**Files:**
- Modify: live `Chandelier_Circular_Droop-02.gh` canvas

**Interfaces:**
- Consumes: fresh canvas epoch and the current short IDs from Task 1
- Produces: `Rings`, `PhaseStep`, and `FinSpin` sliders connected to placement inputs 1, 3, and 4

- [ ] **Step 1: Take a new snapshot immediately before editing**

Call `gh_snapshot(include_data=false)` and use only its returned epoch and short IDs.

- [ ] **Step 2: Apply one atomic `gh_edit` batch**

Create:

```json
[
  {
    "temp_id":"T_RINGS",
    "type":"slider",
    "nick":"Rings",
    "min":3,
    "max":20,
    "value":11,
    "pos":[-390.6,685]
  },
  {
    "temp_id":"T_PHASE",
    "type":"slider",
    "nick":"PhaseStep",
    "min":-1,
    "max":1,
    "value":0.35,
    "pos":[-390.4,741]
  },
  {
    "temp_id":"T_SPIN",
    "type":"slider",
    "nick":"FinSpin",
    "min":-90,
    "max":90,
    "value":55,
    "pos":[-390.4,769]
  }
]
```

Disconnect:

```text
C111.O0>C122.I1
C113.O0>C122.I3
C114.O0>C122.I4
```

Delete only `C111`, `C113`, and `C114`.

Connect:

```text
T_RINGS.O0>C122.I1
T_PHASE.O0>C122.I3
T_SPIN.O0>C122.I4
```

Delete `G6` and create:

```json
{
  "action":"create",
  "nick":"Circular Radial Spiral — First Pass",
  "colour":"#8064A2A0",
  "members":[
    "T_RINGS",
    "C112",
    "T_PHASE",
    "T_SPIN",
    "C115",
    "C116",
    "C117",
    "C118",
    "C119",
    "C120",
    "C121",
    "C122",
    "C110"
  ]
}
```

- [ ] **Step 3: Verify the control batch**

Poll `gh_status` until the solver is enabled, the solution state is `PostProcess`, and `ready_for_edit` is true. Call `gh_errors`.

Expected:

```text
0 errors
0 warnings
Rings = 11
Fill = 0.962
PhaseStep = 0.35
FinSpin = 55
```

The old phyllotaxis algorithm may temporarily emit 11 points; this is expected until Task 3.

---

### Task 3: Replace the Placement Algorithm In Place

**Files:**
- Modify: RhinoCode Python component instance `afddfe28-88bc-4ef2-83f0-c6c64adead3c`

**Interfaces:**
- Consumes: `surface`, `rings`, `fill`, `phase_step`, `fin_spin`
- Produces: `Points`, `Planes`, `Center`, `OuterRadius`, `FieldRadius`, `Boundary`

- [ ] **Step 1: Read and preserve the current raw RhinoCode source**

Call:

```json
{"name":"gh_set_script","arguments":{"guid":"afddfe28-88bc-4ef2-83f0-c6c64adead3c"}}
```

Require the source to contain both markers:

```text
# ── Auto-generated GH input coercion (do not edit)
n = max(2, int(count))
```

Abort if either marker is absent. This protects the reference-surface coercion that was required for the prior iteration.

- [ ] **Step 2: Update the generated input-variable assignments**

Replace exactly:

```python
count = _gh_extract_one(1, int)
if count is None: count = int(0)
fill = _gh_extract_one(2, float)
if fill is None: fill = float(0)
angle = _gh_extract_one(3, float)
if angle is None: angle = float(0)
arms = _gh_extract_one(4, int)
if arms is None: arms = int(0)
```

with:

```python
rings = _gh_extract_one(1, int)
if rings is None: rings = int(0)
fill = _gh_extract_one(2, float)
if fill is None: fill = float(0)
phase_step = _gh_extract_one(3, float)
if phase_step is None: phase_step = float(0)
fin_spin = _gh_extract_one(4, float)
if fin_spin is None: fin_spin = float(0)
```

Require exactly one replacement.

- [ ] **Step 3: Replace the phyllotaxis body with the radial algorithm**

Replace the source from:

```python
n = max(2, int(count))
```

through:

```python
Boundary = rg.Circle(driver_plane, outer_radius).ToNurbsCurve()
```

with this complete body:

```python
ring_count = max(1, min(20, int(rings)))
fill_ratio = max(0.05, min(1.0, float(fill)))
phase_fraction = max(-1.0, min(1.0, float(phase_step)))
spin_degrees = max(-90.0, min(90.0, float(fin_spin)))
spin_radians = math.radians(spin_degrees)
field_radius = outer_radius * fill_ratio
ring_pitch = field_radius / float(ring_count)

points_tree = gh.DataTree[rg.Point3d]()
planes_tree = gh.DataTree[rg.Plane]()
normal = driver_plane.Normal
if not normal.Unitize():
    fail("surface normal is invalid")

center_x = driver_plane.XAxis
center_x.Unitize()
center_y = rg.Vector3d.CrossProduct(normal, center_x)
center_y.Unitize()
center_path = GH_Path(0)
points_tree.Add(center, center_path)
planes_tree.Add(rg.Plane(center, center_x, center_y), center_path)

phase = 0.0
cos_spin = math.cos(spin_radians)
sin_spin = math.sin(spin_radians)

for ring_index in range(1, ring_count + 1):
    radius = ring_pitch * float(ring_index)
    point_count = max(6, int(round(2.0 * math.pi * radius / ring_pitch)))
    bay = 2.0 * math.pi / float(point_count)
    phase += phase_fraction * bay
    path = GH_Path(ring_index)

    for point_index in range(point_count):
        theta = phase + float(point_index) * bay
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        radial = driver_plane.XAxis * cos_theta + driver_plane.YAxis * sin_theta
        if not radial.Unitize():
            fail("could not calculate radial direction")
        tangent = rg.Vector3d.CrossProduct(normal, radial)
        if not tangent.Unitize():
            fail("could not calculate tangent direction")
        x_axis = radial * cos_spin + tangent * sin_spin
        if not x_axis.Unitize():
            fail("could not calculate fin direction")
        y_axis = rg.Vector3d.CrossProduct(normal, x_axis)
        if not y_axis.Unitize():
            fail("could not calculate fin plane")

        point = center + radial * radius
        points_tree.Add(point, path)
        planes_tree.Add(rg.Plane(point, x_axis, y_axis), path)

Points = points_tree
Planes = planes_tree
Center = center
OuterRadius = outer_radius
FieldRadius = field_radius
Boundary = rg.Circle(driver_plane, outer_radius).ToNurbsCurve()
```

Also replace:

```python
raise ValueError("CircularPhyllotaxis: " + message)
```

with:

```python
raise ValueError("CircularRadialSpiral: " + message)
```

Require one replacement for each source block.

- [ ] **Step 4: Write the exact raw source**

Build `updatedSource` from the source read in Step 1 by applying the three exact replacements from Steps 2–3. Require each old block to occur once before replacing it, then call:

```javascript
const writeResult = await tools.mcp__rook__rook_tools_call({
  name: "gh_set_script",
  arguments: {
    guid: "afddfe28-88bc-4ef2-83f0-c6c64adead3c",
    script: updatedSource
  }
});
```

`updatedSource` must still contain the complete generated coercion preamble, `_gh_extract_one`, the surface/Brep coercion, the radial body, and all six output assignments. Do not send only the body, and do not use `gh_update_script`; a prior body-only update dropped the reference-geometry coercion preamble.

- [ ] **Step 5: Rename the component and input pins**

Call `gh_set_script_pins`:

```json
{
  "guid":"afddfe28-88bc-4ef2-83f0-c6c64adead3c",
  "name":"CircularRadialSpiral",
  "description":"Evenly spaced adaptive radial rings with progressive phase and spiral fin orientation.",
  "input_updates":[
    {"index":0,"name":"surface","nick":"surface","type":"Surface","access":"item","optional":false},
    {"index":1,"name":"rings","nick":"rings","type":"int","access":"item","optional":false},
    {"index":2,"name":"fill","nick":"fill","type":"double","access":"item","optional":false},
    {"index":3,"name":"phase_step","nick":"phase_step","type":"double","access":"item","optional":false},
    {"index":4,"name":"fin_spin","nick":"fin_spin","type":"double","access":"item","optional":false}
  ]
}
```

Do not replace output pins; their existing names and tree access modes are correct.

- [ ] **Step 6: Verify compilation and solve health**

Poll `gh_status` to a bounded 30-second timeout until:

```text
solverEnabled = true
solutionState = PostProcess
ready_for_edit = true
```

Then call `gh_errors`. Expected: zero errors and zero warnings.

---

### Task 4: Run the Green Regression and Visual Verification

**Files:**
- Inspect: live `Chandelier_Circular_Droop-02.gh`
- Inspect: Rhino shaded viewport

**Interfaces:**
- Consumes: final `CircularRadialSpiral` and `ChandelierSmoothLayersCircular` outputs
- Produces: verified radial placement, fin tree, preview wiring, and viewport result

- [ ] **Step 1: Re-run the radial-tree assertion**

Call `gh_inspect_output` on `Points` and `Planes`.

Require both outputs to satisfy:

```javascript
const expectedCounts = [1, 6, 13, 19, 25, 31, 38, 44, 50, 57, 63, 69];
assert(result.data_count === 416);
assert(result.path_count === 12);
assert(JSON.stringify(result.branches.map(b => b.count)) === JSON.stringify(expectedCounts));
```

Expected result: PASS for both outputs.

- [ ] **Step 2: Verify the driver dimensions**

Inspect:

```text
Center
OuterRadius
FieldRadius
```

Expected:

```text
Center ≈ (-68174.4566, -5175.3158, 13100.0003)
OuterRadius ≈ 2950.0
FieldRadius ≈ 2837.9
```

- [ ] **Step 3: Verify the fin output**

Call `gh_inspect_output` for `ChandelierSmoothLayersCircular.Fins`.

Require:

```text
data_count = 416
path_count = 12
branch counts = 1, 6, 13, 19, 25, 31, 38, 44, 50, 57, 63, 69
preview type = Rhino.Geometry.Mesh
```

- [ ] **Step 4: Verify the preserved mesh-normal correction**

Read the fin script with `gh_set_script` in get mode and require all markers:

```text
mesh.UnifyNormals()
mesh.Unweld(Math.PI / 6.0, true)
mesh.Normals.ComputeNormals()
mesh.SolidOrientation() < 0
mesh.Flip(true, true, true)
```

- [ ] **Step 5: Verify final canvas wiring and diagnostics**

Call a final `gh_snapshot(include_data=true, max_preview_items=2)` and `gh_errors`.

Require:

```text
CircularRadialSpiral.Planes -> ChandelierSmoothLayersCircular.planes
CircularRadialSpiral.Center -> ChandelierSmoothLayersCircular.center
CircularRadialSpiral.FieldRadius -> ChandelierSmoothLayersCircular.depth_radius
ChandelierSmoothLayersCircular.Fins -> existing Custom Preview.Geometry
0 errors
0 warnings
```

- [ ] **Step 6: Capture and inspect the result**

Focus the Grasshopper canvas on the radial group and call `gh_canvas_image`.

Capture the active Rhino viewport at 1200 × 900 in Shaded mode:

```json
{
  "name":"rhino_viewport",
  "arguments":{
    "width":1200,
    "height":900,
    "displayMode":"Shaded",
    "drawGrid":false,
    "drawWorldAxes":false,
    "drawCPlaneAxes":false
  }
}
```

Visually require:

- no large outer gaps or crowded inner ring;
- one clearly centered deepest fin stack;
- visible concentric organization;
- ring drift and fin orientation turning in the same direction;
- hard, clean fin shading without the former smoothed-edge artifact.

- [ ] **Step 7: Leave the file unsaved**

Confirm `gh_status.document_name` ends with `*`. Report that the live iteration is ready for review and requires an explicit Grasshopper save to persist.
