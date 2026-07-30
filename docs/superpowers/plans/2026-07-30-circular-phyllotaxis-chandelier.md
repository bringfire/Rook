# Circular Phyllotaxis Chandelier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-destructive Grasshopper branch that produces 308 phyllotaxis-distributed fin stacks within the referenced circular surface and preserves the chandelier's centered cosine-squared droop.

**Architecture:** Create two new RhinoCode script components on the live canvas. `CircularPhyllotaxis` derives a plane, center, outer radius, and bounded point/plane field from the referenced Brep. `ChandelierSmoothLayersCircular` consumes those planes and center to generate one closed two-panel mesh stack per point with radial droop. Existing components remain unchanged.

**Tech Stack:** Rhino 8, Grasshopper, RhinoCode Python 3, RhinoCode C#, RhinoCommon, Rook MCP live-canvas tools.

## Global Constraints

- Work only in the open `Chandelier_Circular_Droop-01.gh` document.
- Preserve the existing grid branch, experimental `Phyllotaxis`, original `ChandelierSmoothLayers`, referenced surface, and preview components.
- Add no external dependencies and modify no Rook project source files.
- Use the referenced circular surface for the first pass.
- Target exactly 308 placement planes and 308 fin meshes.
- Use `fill = 0.92`, `angle = 137.508`, and `arms = 13` initially. The fill was calibrated after reading the surface's 2,950 mm trimmed radius rather than its larger underlying Brep bounds.
- Use two panels, two minimum layers, three extra central layers, 380 mm nominal fin height, 38 mm gap, 110 mm half-length, and 13 mm half-thickness.
- Check Grasshopper solve readiness and errors after every mutation batch.
- Use a fresh `gh_snapshot` epoch immediately before every `gh_edit` call.

---

### Task 1: Create `CircularPhyllotaxis`

**Live canvas changes:**
- Create: RhinoCode Python 3 component `CircularPhyllotaxis` near `(-100, 800)`.
- Consume: referenced Brep from existing surface parameter.
- Produce: `Points`, `Planes`, `Center`, `OuterRadius`, `FieldRadius`, and `Boundary`.

**Interfaces:**
- Consumes: `surface: Brep`, `count: int`, `fill: double`, `angle: double`, `arms: int`.
- Produces: point and plane trees with exactly `count` items, plus one center point, two radii, and one circular boundary curve.

- [ ] **Step 1: Capture pre-flight state**

Call `gh_status`, `gh_snapshot(include_data=false)`, and `gh_errors`. Confirm the document name is `Chandelier_Circular_Droop-01`, the solver is enabled, the canvas has no errors, and the referenced surface parameter still contains one Rhino reference.

- [ ] **Step 2: Create the Python component**

Call `gh_create_script` with `language="python"`, `name="CircularPhyllotaxis"`, `x=-100`, `y=800`, rich item input pins, rich geometry output pins, and this exact source:

```python
import Rhino
import Rhino.Geometry as rg
import Grasshopper as gh
from Grasshopper.Kernel.Data import GH_Path
import math


def fail(message):
    raise ValueError("CircularPhyllotaxis: " + message)


if surface is None:
    fail("surface is required")

geom = surface
if isinstance(geom, rg.BrepFace):
    brep = geom.DuplicateFace(False)
elif isinstance(geom, rg.Brep):
    brep = geom.DuplicateBrep()
elif isinstance(geom, rg.Surface):
    brep = geom.ToBrep()
else:
    fail("surface must be a Brep or Surface")

if brep is None or not brep.IsValid or brep.Faces.Count < 1:
    fail("surface is invalid")

tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
face = brep.Faces[0]
ok, face_plane = face.TryGetPlane(tol)
if not ok:
    fail("surface must be planar")

amp = rg.AreaMassProperties.Compute(brep)
if amp is None:
    fail("could not calculate surface center")

center = amp.Centroid
driver_plane = rg.Plane(center, face_plane.XAxis, face_plane.YAxis)

outer_radius = 0.0
for edge in brep.Edges:
    ok_circle, circle = edge.TryGetCircle(tol)
    if ok_circle and circle.Radius > outer_radius:
        outer_radius = circle.Radius

if outer_radius <= tol:
    local_copy = brep.DuplicateBrep()
    to_xy = rg.Transform.PlaneToPlane(driver_plane, rg.Plane.WorldXY)
    local_copy.Transform(to_xy)
    bbox = local_copy.GetBoundingBox(True)
    outer_radius = 0.5 * min(bbox.Max.X - bbox.Min.X, bbox.Max.Y - bbox.Min.Y)

if outer_radius <= tol:
    fail("could not derive a positive outer radius")

n = max(2, int(count))
fill_ratio = max(0.05, min(1.0, float(fill)))
step = max(1, min(n, int(arms)))
golden = math.radians(float(angle))
field_radius = outer_radius * fill_ratio

positions = []
for i in range(n):
    radius = field_radius * math.sqrt(float(i) / float(n - 1))
    theta = i * golden
    point = center + driver_plane.XAxis * (radius * math.cos(theta)) + driver_plane.YAxis * (radius * math.sin(theta))
    positions.append(point)

points_tree = gh.DataTree[rg.Point3d]()
planes_tree = gh.DataTree[rg.Plane]()
normal = driver_plane.Normal
normal.Unitize()

for arm in range(min(step, n)):
    path = GH_Path(arm)
    indices = list(range(arm, n, step))
    for j, index in enumerate(indices):
        point = positions[index]
        if j < len(indices) - 1:
            tangent = positions[indices[j + 1]] - point
        elif j > 0:
            tangent = point - positions[indices[j - 1]]
        else:
            tangent = driver_plane.XAxis
        tangent -= normal * (tangent * normal)
        if not tangent.Unitize():
            tangent = driver_plane.XAxis
        y_axis = rg.Vector3d.CrossProduct(normal, tangent)
        y_axis.Unitize()
        points_tree.Add(point, path)
        planes_tree.Add(rg.Plane(point, tangent, y_axis), path)

Points = points_tree
Planes = planes_tree
Center = center
OuterRadius = outer_radius
FieldRadius = field_radius
Boundary = rg.Circle(driver_plane, outer_radius).ToNurbsCurve()
```

Use these pins:

```json
{
  "pins_in": [
    {"name":"surface","type":"Brep","access":"item","optional":false},
    {"name":"count","type":"int","access":"item","optional":false},
    {"name":"fill","type":"double","access":"item","optional":false},
    {"name":"angle","type":"double","access":"item","optional":false},
    {"name":"arms","type":"int","access":"item","optional":false}
  ],
  "pins_out": [
    {"name":"Points","type":"Point3d","access":"tree"},
    {"name":"Planes","type":"Plane","access":"tree"},
    {"name":"Center","type":"Point3d","access":"item"},
    {"name":"OuterRadius","type":"double","access":"item"},
    {"name":"FieldRadius","type":"double","access":"item"},
    {"name":"Boundary","type":"Curve","access":"item"}
  ]
}
```

- [ ] **Step 3: Verify creation before wiring**

Capture a fresh snapshot and locate the component by nickname. Confirm the five inputs and six semantic outputs exist. Check `gh_errors`; an unwired-required-input warning is acceptable, but a compile error is not.

---

### Task 2: Create `ChandelierSmoothLayersCircular`

**Live canvas changes:**
- Create: RhinoCode C# component `ChandelierSmoothLayersCircular` near `(500, 800)`.
- Consume: one placement plane and surface center per Grasshopper data-match iteration.
- Produce: one closed mesh and one origin point per placement plane.

**Interfaces:**
- Consumes: `planes: Plane`, `center: Point3d`, integer layer controls, and numeric fin dimensions.
- Produces: `Fins: Mesh` and `Origins: Point3d`, preserving the placement tree structure.

- [ ] **Step 1: Create the C# component**

Call `gh_create_script` with `language="csharp"`, `name="ChandelierSmoothLayersCircular"`, `x=500`, `y=800`, the pins below, and this exact full source:

```csharp
using System;
using Rhino.Geometry;
using Grasshopper.Kernel.Types;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object planes,
        object center,
        object num_layers,
        object min_layers,
        object extra_layers,
        object depth_radius,
        object fin_height,
        object gap,
        object fin_length,
        object half_thickness,
        ref object Fins,
        ref object Origins)
    {
        Plane plane;
        if (planes is Plane p)
            plane = p;
        else if (planes is GH_Plane ghp)
            plane = ghp.Value;
        else
            return;

        Point3d centerPoint;
        if (center is Point3d cp)
            centerPoint = cp;
        else if (center is GH_Point ghcp)
            centerPoint = ghcp.Value;
        else
            return;

        int panelCount = Math.Max(1, Convert.ToInt32(num_layers));
        int minimumLayers = Math.Max(1, Convert.ToInt32(min_layers));
        int additionalLayers = Math.Max(0, Convert.ToInt32(extra_layers));
        double droopRadius = Math.Max(1.0, Convert.ToDouble(depth_radius));
        double nominalHeight = Math.Max(1e-6, Convert.ToDouble(fin_height));
        double panelGap = Math.Max(0.0, Convert.ToDouble(gap));
        double halfLength = Math.Max(1e-6, Convert.ToDouble(fin_length));
        double halfThickness = Math.Max(1e-6, Convert.ToDouble(half_thickness));

        Point3d origin = plane.Origin;
        Origins = origin;

        double distance = origin.DistanceTo(centerPoint);
        double falloff = 0.0;
        if (distance < droopRadius)
        {
            double ratio = distance / droopRadius;
            double cosine = Math.Cos(ratio * Math.PI / 2.0);
            falloff = cosine * cosine;
        }

        double smoothLayers = minimumLayers + additionalLayers * falloff;
        double totalDroop = (smoothLayers - 1.0) * (nominalHeight + panelGap) + nominalHeight;
        double panelHeight = (totalDroop - (panelCount - 1) * panelGap) / panelCount;
        panelHeight = Math.Max(1e-6, panelHeight);

        Vector3d xDirection = plane.XAxis;
        Vector3d yDirection = plane.YAxis;
        Vector3d downAxis = plane.ZAxis;
        if (!xDirection.Unitize() || !yDirection.Unitize() || !downAxis.Unitize())
            return;

        Mesh mesh = new Mesh();
        for (int layer = 0; layer < panelCount; layer++)
        {
            double topOffset = layer * (panelHeight + panelGap);
            double bottomOffset = topOffset + panelHeight;
            Vector3d direction = layer % 2 == 0 ? xDirection : yDirection;
            Vector3d normal = Vector3d.CrossProduct(direction, downAxis);
            if (!normal.Unitize())
                return;
            Vector3d thicknessOffset = normal * halfThickness;

            Point3d topCenter = origin - downAxis * topOffset;
            Point3d bottomCenter = origin - downAxis * bottomOffset;
            Point3d a = topCenter - direction * halfLength;
            Point3d b = topCenter + direction * halfLength;
            Point3d c = bottomCenter + direction * halfLength;
            Point3d d = bottomCenter - direction * halfLength;

            int vertex = mesh.Vertices.Count;
            mesh.Vertices.Add(a + thicknessOffset);
            mesh.Vertices.Add(b + thicknessOffset);
            mesh.Vertices.Add(c + thicknessOffset);
            mesh.Vertices.Add(d + thicknessOffset);
            mesh.Vertices.Add(b - thicknessOffset);
            mesh.Vertices.Add(a - thicknessOffset);
            mesh.Vertices.Add(d - thicknessOffset);
            mesh.Vertices.Add(c - thicknessOffset);

            mesh.Faces.AddFace(vertex, vertex + 1, vertex + 2, vertex + 3);
            mesh.Faces.AddFace(vertex + 4, vertex + 5, vertex + 6, vertex + 7);
            mesh.Faces.AddFace(vertex, vertex + 3, vertex + 6, vertex + 5);
            mesh.Faces.AddFace(vertex + 1, vertex + 4, vertex + 7, vertex + 2);
            mesh.Faces.AddFace(vertex, vertex + 5, vertex + 4, vertex + 1);
            mesh.Faces.AddFace(vertex + 3, vertex + 2, vertex + 7, vertex + 6);
        }

        mesh.Normals.ComputeNormals();
        mesh.Compact();
        Fins = mesh;
    }
}
```

Use these pins:

```json
{
  "pins_in": [
    {"name":"planes","type":"Plane","access":"item","optional":false},
    {"name":"center","type":"Point3d","access":"item","optional":false},
    {"name":"num_layers","type":"int","access":"item","optional":false},
    {"name":"min_layers","type":"int","access":"item","optional":false},
    {"name":"extra_layers","type":"int","access":"item","optional":false},
    {"name":"depth_radius","type":"double","access":"item","optional":false},
    {"name":"fin_height","type":"double","access":"item","optional":false},
    {"name":"gap","type":"double","access":"item","optional":false},
    {"name":"fin_length","type":"double","access":"item","optional":false},
    {"name":"half_thickness","type":"double","access":"item","optional":false}
  ],
  "pins_out": [
    {"name":"Fins","type":"Mesh","access":"item"},
    {"name":"Origins","type":"Point3d","access":"item"}
  ]
}
```

- [ ] **Step 2: Verify creation before wiring**

Capture a fresh snapshot and locate the component by nickname. Confirm ten inputs and two semantic outputs exist. Check `gh_errors`; unwired-input warnings are acceptable, but compilation errors require one source correction attempt before continuing.

---

### Task 3: Create controls, wire the branch, and group it

**Live canvas changes:**
- Create 11 dedicated sliders.
- Connect the existing referenced surface and the new components.
- Create group `Circular Phyllotaxis — First Pass`.

**Interfaces:**
- Consumes: committed short IDs from the fresh post-creation snapshot.
- Produces: one fully wired, isolated branch without changing any existing wire.

- [ ] **Step 1: Capture a fresh topology and epoch**

Call `gh_snapshot(include_data=false)`. Record short IDs for the existing surface parameter, `CircularPhyllotaxis`, `ChandelierSmoothLayersCircular`, and the existing `Custom Preview`. Verify the original flow list is unchanged.

- [ ] **Step 2: Create and wire controls atomically**

Call `gh_edit` once with the fresh epoch. Create these sliders at the indicated approximate positions:

| Temp ID | Nickname | Min | Max | Value | Position |
|---|---|---:|---:|---:|---|
| T1 | Count | 50 | 600 | 308 | `[-500, 800]` |
| T2 | Fill | 0.50 | 1.00 | 0.92 | `[-500, 825]` |
| T3 | Angle | 100 | 180 | 137.508 | `[-500, 850]` |
| T4 | Arms | 1 | 34 | 13 | `[-500, 875]` |
| T5 | Panels | 1 | 6 | 2 | `[150, 800]` |
| T6 | MinLayers | 1 | 5 | 2 | `[150, 825]` |
| T7 | ExtraLayers | 0 | 8 | 3 | `[150, 850]` |
| T8 | FinHeight | 50 | 500 | 380 | `[150, 875]` |
| T9 | Gap | 0 | 100 | 38 | `[150, 900]` |
| T10 | HalfLength | 20 | 300 | 110 | `[150, 925]` |
| T11 | HalfThickness | 1 | 50 | 13 | `[150, 950]` |

Create connections using actual short IDs and actual output indices from the fresh snapshot:

```text
SURFACE.O0>CIRCULAR_PHYLLO.I0
T1.O0>CIRCULAR_PHYLLO.I1
T2.O0>CIRCULAR_PHYLLO.I2
T3.O0>CIRCULAR_PHYLLO.I3
T4.O0>CIRCULAR_PHYLLO.I4
CIRCULAR_PHYLLO.Planes>FIN_SCRIPT.I0
CIRCULAR_PHYLLO.Center>FIN_SCRIPT.I1
T5.O0>FIN_SCRIPT.I2
T6.O0>FIN_SCRIPT.I3
T7.O0>FIN_SCRIPT.I4
CIRCULAR_PHYLLO.FieldRadius>FIN_SCRIPT.I5
T8.O0>FIN_SCRIPT.I6
T9.O0>FIN_SCRIPT.I7
T10.O0>FIN_SCRIPT.I8
T11.O0>FIN_SCRIPT.I9
```

Create group `Circular Phyllotaxis — First Pass` with color `#8064A2A0` and members `T1` through `T11`, `CIRCULAR_PHYLLO`, and `FIN_SCRIPT`. Do not add the existing referenced surface or preview components to the group.

- [ ] **Step 3: Wait for the solution and verify the isolated branch**

Poll `gh_status` to a bounded 30-second timeout until the solver is enabled, the solution state is post-process, and the canvas is ready for edit. Then call `gh_errors` and `gh_snapshot(include_data=true, max_preview_items=3)`.

Expected results:

- `CircularPhyllotaxis.Points`: total count 308.
- `CircularPhyllotaxis.Planes`: total count 308.
- `Center`: approximately `(-68174.4566, -5175.3158, 13100.0003)`.
- `OuterRadius`: approximately 2,950 mm from the trimmed circular edge.
- `FieldRadius`: approximately 2,714 mm.
- Placement-point diameter: approximately 5,428 mm; projected fin envelope: approximately 5,648 mm.
- `ChandelierSmoothLayersCircular.Fins`: total count 308, each preview item a `Rhino.Geometry.Mesh`.
- No compile or runtime errors.

- [ ] **Step 4: Correct at most one script defect if required**

If a new script reports a compile/runtime error, read the exact component error and current source, apply one focused source correction with `gh_update_script`, then repeat the readiness and error checkpoint. Do not change existing components or relax the success criteria.

---

### Task 4: Connect preview and verify geometry

**Live canvas changes:**
- Add the verified `Fins` output as a source to the existing `Custom Preview` geometry input.
- Preserve its existing mesh parameter source and material source.

**Interfaces:**
- Consumes: verified `Fins` output containing 308 meshes.
- Produces: live viewport preview of the new branch using the existing material.

- [ ] **Step 1: Connect only after data verification**

Capture a fresh snapshot and epoch. Call `gh_edit` with one connection from the actual `Fins` output index to the existing `Custom Preview` geometry input index 0. Do not disconnect `Mesh -> Custom Preview` or `Material -> Custom Preview`.

- [ ] **Step 2: Run the final solve checkpoint**

Wait up to 30 seconds for a ready post-process state, then call `gh_errors`, `gh_inspect_output` for `Points`, `Planes`, `FieldRadius`, and `Fins`, plus a final `gh_snapshot`.

The final definition must have:

- 308 placement points.
- 308 placement planes.
- 308 fin meshes.
- Zero new component errors.
- A field diameter near 5,664 mm before fin overhang.
- Center droop near 2,052 mm and perimeter droop near 798 mm.
- Existing components and wires preserved.

- [ ] **Step 3: Capture visual evidence**

Capture a Grasshopper canvas image. If available, capture or inspect the Rhino viewport to confirm circular coverage, center alignment, tangent arm flow, fin scale, and smooth radial droop. Report visual mismatches as iteration notes rather than broadening this first pass.

- [ ] **Step 4: Record rollback IDs**

Record the final short IDs and instance GUIDs of all newly created components and the group. Rollback consists only of deleting those new objects and removing the added preview connection.

---

## Completion Report

Report the actual point/plane/mesh counts, derived radii, error count, preview connection state, and any visual differences from the selected reference block. State explicitly that the existing grid and earlier Phyllotaxis branches were preserved.
