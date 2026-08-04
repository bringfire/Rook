# Gradient Box Array Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a live Grasshopper definition containing a C# component and six sliders that generate a diagonal 10 by 10 gradient of solid boxes.

**Architecture:** A single RhinoCode C# Script component owns geometry generation and emits parallel `Boxes` and `Heights` lists. Six native Grasshopper sliders feed scalar parameters into the script; all created objects are grouped and remain parametric on the active canvas.

**Tech Stack:** Rhino 8, Grasshopper, RhinoCode C#, RhinoCommon `Box`/`Brep`, Rook `gh_create_csharp_script`, `gh_edit`, `gh_snapshot`, `gh_status`, and `gh_errors`.

## Global Constraints

- Target only the active, unnamed Grasshopper document.
- Preserve all pre-existing canvas content; create and group only execution-owned objects.
- Do not bake geometry into the Rhino document.
- Default to 10 by 10 boxes, 1 m square bases, 0.2 m gaps, and heights from 0.25 m to 5 m.
- Expose X count, Y count, box size, gap, minimum height, and maximum height as sliders.
- Produce flat, row-major `Boxes` and `Heights` outputs.

---

### Task 1: Create the Gradient Box C# Component

**Files:**
- Create live object: `Gradient Box Array` C# Script component in the active Grasshopper document
- Reference: `docs/superpowers/specs/2026-08-04-gradient-box-array-design.md`

**Interfaces:**
- Consumes: scalar object inputs `XCount`, `YCount`, `BoxSize`, `Gap`, `MinHeight`, and `MaxHeight`
- Produces: list outputs `Boxes:Brep` and `Heights:double`

- [ ] **Step 1: Admit the current live document**

Run `rhino_ping`, `gh_status`, and a fresh `gh_snapshot`. Record the document name, epoch, all pre-existing short IDs, and verify the solver is available before mutation.

- [ ] **Step 2: Create the C# component with its complete pin contract and source**

Invoke `gh_create_csharp_script` at canvas position `[520, 220]` with item-access input pins and list-access output pins. Use this body code:

```csharp
int nx = Math.Max(1, Convert.ToInt32(XCount));
int ny = Math.Max(1, Convert.ToInt32(YCount));
double size = Math.Max(0.001, Convert.ToDouble(BoxSize));
double gap = Math.Max(0.0, Convert.ToDouble(Gap));
double minHeight = Math.Max(0.001, Convert.ToDouble(MinHeight));
double maxHeight = Math.Max(0.001, Convert.ToDouble(MaxHeight));

var boxes = new List<Brep>();
var heights = new List<double>();
double denominator = (nx - 1) + (ny - 1);

for (int j = 0; j < ny; j++)
{
  for (int i = 0; i < nx; i++)
  {
    double t = denominator > 0.0 ? (i + j) / denominator : 0.0;
    double height = minHeight + t * (maxHeight - minHeight);
    double x0 = i * (size + gap);
    double y0 = j * (size + gap);
    var box = new Box(
      Plane.WorldXY,
      new Interval(x0, x0 + size),
      new Interval(y0, y0 + size),
      new Interval(0.0, height));
    Brep brep = box.ToBrep();
    if (brep != null)
    {
      boxes.Add(brep);
      heights.Add(height);
    }
  }
}

Boxes = boxes;
Heights = heights;
```

- [ ] **Step 3: Checkpoint the component creation**

Poll `gh_status`, capture a new snapshot, record the component GUID and fresh short ID, and run `gh_errors`. Stop before creating controls if compilation reports an error.

### Task 2: Add, Connect, and Verify Parameter Controls

**Files:**
- Create live objects: six Grasshopper number sliders and one execution-owned group
- Modify live object: connect the sliders to the Task 1 C# component

**Interfaces:**
- Consumes: the C# component short ID and fresh snapshot epoch from Task 1
- Produces: a fully connected parametric definition with 100 default boxes and 100 corresponding heights

- [ ] **Step 1: Create all six sliders and connections in one bounded batch**

Use `gh_edit` with the fresh epoch. Create sliders at X positions near `120` and Y positions `120`, `200`, `280`, `360`, `440`, and `520`:

| Temp ID | Nickname | Minimum | Maximum | Value | Target input |
| --- | --- | ---: | ---: | ---: | ---: |
| T1 | X Count | 1 | 50 | 10 | I0 |
| T2 | Y Count | 1 | 50 | 10 | I1 |
| T3 | Box Size | 0.1 | 5 | 1 | I2 |
| T4 | Gap | 0 | 5 | 0.2 | I3 |
| T5 | Min Height | 0.01 | 10 | 0.25 | I4 |
| T6 | Max Height | 0.01 | 20 | 5 | I5 |

Connect `T1.O0` through `T6.O0` to the matching C# inputs and create a group named `Gradient Box Array` containing the six sliders plus the C# component. Inspect every operation result and the returned temp-ID map; do not replay committed operations after partial success.

- [ ] **Step 2: Wait for a settled solution and inspect diagnostics**

Poll `gh_status` to a bounded timeout, then run `gh_errors`. If a resolvable owned-state defect exists, refresh the snapshot and apply one bounded correction to only the failed or unapplied operations.

- [ ] **Step 3: Verify the requested output contract**

Capture a final `gh_snapshot` with data previews. Confirm six flows target input indices 0 through 5, the C# component has no warnings or errors, `Boxes` and `Heights` each contain 100 items, and height values span 0.25 through 5. Confirm all created components are members of the execution-owned group.

- [ ] **Step 4: Report the live result**

Return the created component IDs, default parameter values, verified output counts, height range, and any remaining warnings. Do not perform global cleanup or bake geometry.
