# VIP Tree Primary Bifurcation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the live `Tree.gh` trunk into a modular strand-field pipeline and add a smooth, editable, asymmetric 3D primary bifurcation driven by two Rhino curves.

**Architecture:** The existing trunk script becomes a parent-field component that emits ordered point paths, frames, parameters, and strand identities. A separate bifurcation script conserves and transports those strands onto two editable Rhino branch spines; a final curve-builder component converts the resulting point paths into preview curves consumed by the existing native Pipe component.

**Tech Stack:** Rhino 8, Grasshopper, RhinoCode C#, RhinoCommon geometry, Grasshopper `DataTree<T>`/`GH_Path`, native Grasshopper Pipe, and Rook live Rhino/Grasshopper tools.

**Spec:** `docs/plans/2026-09-01-vip-tree-primary-bifurcation-design.md`

## Global Constraints

- Target only the Rhino document named `Tree.3dm` and its open `Tree.gh` definition in the VIP Trees study directory.
- Preserve the user's current trunk-driver curves, slider values, strand count, pipe settings, and all unrelated document content.
- Work in metres; the overall tree remains approximately 8 m high.
- Use editable Rhino curves for the base ellipse, parent spine, Primary Branch A, and Primary Branch B.
- Use no Florasynth code and introduce no external runtime or compiled helper dependency.
- Exchange only Rhino/Grasshopper-native values between scripted modules: points, planes, numbers, integers, curves, and data trees.
- Conserve every primary strand through the split; no primary strand may be created, deleted, cut, or joined at the fork.
- Default to an asymmetric approximately 60/40 allocation, with Branch A more vertical and Branch B more outward.
- Treat the fork as an overlapping transition zone rather than one exact branch point.
- Do not add secondary branches, leaves, fabrication joints, or baked strand geometry in this implementation.
- Do not impose bilateral symmetry or unseeded randomness.
- Stop at every checkpoint if `gh_errors` reports a new error or warning that cannot be corrected in one bounded pass.
- Save `Tree.3dm` through the Rhino document operation after durable Rhino changes. Because the admitted Grasshopper surface has no save endpoint, ask the user to press `Ctrl+S` in Grasshopper at final handoff.

## Artifact Map

- Modify live Rhino artifact: `F:/DWGS/73300 - Marina Bay Sands IR2/08-Studies/HOTEL STUDIES/260825 VIP + VVIP Arrivals Schematic Design/STUDIES/260831 VIP Trees/Tree.3dm`
  - Add `Primary Branch A Driver` and `Primary Branch B Driver` on `VIP Tree Guides`.
- Modify live Grasshopper artifact: `F:/DWGS/73300 - Marina Bay Sands IR2/08-Studies/HOTEL STUDIES/260825 VIP + VVIP Arrivals Schematic Design/STUDIES/260831 VIP Trees/Tree.gh`
  - Refactor the current tapered-trunk C# component into `03 | Parent Strand Field`.
  - Add two persistent Curve parameters for the Rhino branch references.
  - Add branch-control sliders.
  - Add `04 | Primary Bifurcation` C# component.
  - Add `05 | Strand Curve Builder` C# component.
  - Reconnect the existing native Pipe preview to the curve builder.
  - Add a compact persistent validation component and report panel.
- Preserve design record: `docs/plans/2026-09-01-vip-tree-primary-bifurcation-design.md`.

---

### Task 1: Admit and Capture the Current Live Baseline

**Files:**
- Read live artifact: `Tree.3dm`
- Read live artifact: `Tree.gh`
- Reference: `docs/plans/2026-09-01-vip-tree-primary-bifurcation-design.md`

**Interfaces:**
- Consumes: the currently open Rhino and Grasshopper documents
- Produces: an evidence-backed baseline containing document identity, owned component roles, current slider values, output counts, diagnostics, and four viewport captures

- [ ] **Step 1: Bind to the intended Rhino instance**

Run `rhino_instances`, then bind with `rhino_set_active_instance` by an exact `Tree.3dm` document/path match. Verify `rhino_get_active_instance` reports the VIP Trees path before any mutation.

- [ ] **Step 2: Record the current Grasshopper state**

Run `gh_status`, `gh_snapshot(include_data=true)`, and `gh_errors`. Identify the existing component roles by nickname and connections rather than preserving short IDs. Record:

- the user-adjusted slider values;
- current strand and pipe output counts;
- the current parent-generator raw source from `gh_set_script` in read mode;
- all existing groups and flows; and
- the fact that the pre-change canvas has zero runtime errors and warnings.

- [ ] **Step 3: Capture the pre-change appearance**

Capture `VIP Tree - Reference Front`, `VIP Tree - Side Right`, `VIP Tree - Top`, and the standard `Perspective` view in Shaded mode with zoom extents. These images are the rollback and appearance-preservation baseline for the parent trunk.

- [ ] **Step 4: Confirm the baseline checkpoint**

Inspect the captures and the generator summary. Stop if the live state differs materially from the approved design—for example if branch drivers already exist, the parent generator has been replaced, or the pipe output is invalid.

### Task 2: Add the Two Editable Rhino Branch Drivers

**Files:**
- Modify live artifact: `Tree.3dm`

**Interfaces:**
- Consumes: existing `VIP Tree Spine Driver` and the `VIP Tree Guides` layer
- Produces: two named valid 3D interpolated curves whose starts overlap the parent flow and whose upper reaches are deliberately asymmetric

- [ ] **Step 1: Create Branch A as the stronger vertical gesture**

Use `rhino_geometry` to add a degree-3 interpolated curve named `Primary Branch A Driver` on `VIP Tree Guides`, initially passing through these metre coordinates:

```text
(-0.08, -0.05, 4.55)
(-0.17, -0.11, 4.92)
(-0.19, -0.15, 5.30)
(-0.08, -0.10, 5.72)
( 0.16,  0.02, 6.18)
( 0.42,  0.20, 6.70)
( 0.62,  0.39, 7.23)
( 0.72,  0.52, 7.72)
```

The first three points keep the curve close to the parent spine before it turns forward and upward in three dimensions.

- [ ] **Step 2: Create Branch B as the outward gesture**

Use `rhino_geometry` to add a degree-3 interpolated curve named `Primary Branch B Driver` on `VIP Tree Guides`, initially passing through:

```text
(-0.08, -0.05, 4.55)
(-0.18, -0.11, 4.90)
(-0.27, -0.16, 5.24)
(-0.46, -0.24, 5.60)
(-0.78, -0.34, 5.98)
(-1.10, -0.48, 6.38)
(-1.39, -0.63, 6.82)
(-1.58, -0.72, 7.20)
```

This child separates earlier in plan, remains lower, and terminates farther from the parent axis.

- [ ] **Step 3: Verify the driver geometry**

Query `VIP Tree Guides` and confirm exactly four named guide curves now exist. Check both new curves are valid, start within `0.10 m` of each other, and have nonzero displacement in both X and Y. Capture Front, Right, Top, and Perspective views with only guide geometry emphasized to confirm that the split is not planar or mirrored.

- [ ] **Step 4: Save the Rhino checkpoint**

Save `Tree.3dm` to its existing full path with `rhino_document_ops(action="save")`, then verify `rhino_document.modified` is false.

### Task 3: Refactor the Existing Trunk into the Parent Strand Field

**Files:**
- Modify live object: existing tapered-trunk C# component in `Tree.gh`
- Create live object: `Parent Field Contract Check` C# component and report panel

**Interfaces:**
- Consumes: `Base:Curve`, `Spine:Curve`, `Count:int`, `Sections:int`, `Gather:double`, `TrunkScale:double`, `TopScale:double`, `Twist:double`, `Weave:double`
- Produces: `ParentPaths:DataTree<Point3d>`, `Frames:List<Plane>`, `SectionT:List<double>`, `StrandIds:List<int>`, `SectionCurves:List<Curve>`, `Summary:string`

- [ ] **Step 1: Disconnect downstream preview flows before changing pins**

Take a fresh snapshot and disconnect only the current generator-to-Pipe flow and generator-to-summary-panel flow. Leave all user sliders and Rhino reference inputs connected.

- [ ] **Step 2: Install the final parent-field output contract with null field outputs**

Use `gh_set_script_pins` to preserve the nine existing inputs and replace the outputs with the six outputs listed above. Update the existing script temporarily so it emits empty field collections and the summary `PARENT FIELD NOT IMPLEMENTED`. This creates the interface without claiming the behavior exists.

- [ ] **Step 3: Write and run the failing parent contract check**

Create a small C# validation component with inputs `Paths`, `Frames`, `T`, `Ids`, `ExpectedCount`, and `ExpectedSections`, and outputs `Pass` and `Report`. Connect it to the new parent outputs and the existing Count/Sections sliders. Use this validation body:

```csharp
bool ok = Paths != null && Frames != null && T != null && Ids != null;
var failures = new List<string>();
int n = Math.Max(1, Convert.ToInt32(ExpectedCount));
int m = Math.Max(2, Convert.ToInt32(ExpectedSections));

if (!ok) failures.Add("one or more parent-field outputs are null");
else
{
  if (Paths.BranchCount != n) failures.Add($"paths {Paths.BranchCount} != {n}");
  for (int i = 0; i < Paths.BranchCount; i++)
    if (Paths.Branch(i).Count != m)
      failures.Add($"path {i} has {Paths.Branch(i).Count} points, expected {m}");
  if (Frames.Count != m) failures.Add($"frames {Frames.Count} != {m}");
  if (T.Count != m) failures.Add($"parameters {T.Count} != {m}");
  if (Ids.Count != n || Ids.Distinct().Count() != n)
    failures.Add("strand identities are not unique and complete");
}

Pass = failures.Count == 0;
Report = Pass ? $"PASS | parent field {n} x {m}" : "FAIL | " + string.Join("; ", failures);
```

Run `gh_errors` and inspect `Pass`; expected result is `false` with the null/empty-output report.

- [ ] **Step 4: Refactor the parent generator with focused helper methods**

Replace the monolithic body with a script organized around these exact responsibilities:

```csharp
static double Clamp(double x, double a, double b) => Math.Max(a, Math.Min(b, x));
static double Smooth3(double x) { x = Clamp(x, 0.0, 1.0); return x * x * (3.0 - 2.0 * x); }
static Plane[] BuildTransportFrames(Curve spine, Plane basePlane, int sections);
static void SampleBase(Curve baseCurve, Plane basePlane, int count, out double[] x, out double[] y);
static double ParentScale(double t, double gather, double trunkScale, double topScale);
static Point3d ApplyWeave(Point3d center, Plane frame, double x, double y,
                          double t, double phase, double amount);
```

For strand `i` and section `j`, retain the current visual equations:

```csharp
double t = (double)j / (sectionCount - 1);
double scale = ParentScale(t, gather, trunkScale, topScale);
double envelope = Math.Sin(Math.PI * t);
double localAngle = weaveAmount * 0.055 * envelope *
  Math.Sin(4.0 * Math.PI * t + phase * 1.61803398875);
double pulse = 1.0 + weaveAmount * 0.025 * envelope *
  Math.Sin(6.0 * Math.PI * t + phase);
```

Store each strand's ordered points in `ParentPaths` under path `{i}`, append its integer identity to `StrandIds`, and emit one transported `Plane` and normalized parameter per section. Keep the existing gathering, taper, twist, and weave behavior numerically unchanged so identical inputs preserve the parent appearance.

- [ ] **Step 5: Verify the parent contract turns green**

Wait for a settled solution, then run `gh_errors` and inspect the validation outputs. Require:

- `Pass = true`;
- one point-tree branch per current strand;
- one point per current section in every branch;
- matching frame and parameter counts; and
- zero Grasshopper errors or warnings.

Capture the same four views using temporary curves made from `ParentPaths`, and compare them to Task 1. The pre-split trunk gesture must remain visually unchanged.

### Task 4: Reference the Branch Drivers and Add Bifurcation Controls

**Files:**
- Modify live artifact: `Tree.gh`

**Interfaces:**
- Consumes: Rhino objects named `Primary Branch A Driver` and `Primary Branch B Driver`
- Produces: two persistent Curve references and seven branch-control values

- [ ] **Step 1: Add persistent Rhino references**

Create two Curve parameters in the existing Rhino-driver area, nickname them `Primary Branch A` and `Primary Branch B`, and set persistent references by Rhino object ID discovered from a fresh `rhino_objects` query. Hide their Grasshopper previews so the Rhino guide curves remain the authoritative visible drivers.

- [ ] **Step 2: Add the initial branch controls**

Create and group these sliders under `04 | PRIMARY SPLIT CONTROLS`:

| Nickname | Minimum | Maximum | Initial value | Meaning |
| --- | ---: | ---: | ---: | --- |
| Split Ratio A | 0.35 | 0.65 | 0.60 | Fraction of parent strands assigned to A |
| Transition Length | 0.40 | 1.60 | 1.00 | Metres over which offsets reorganize |
| Seam Rotation | 0.00 | 1.00 | 0.08 | Normalized rotation of the two split boundaries |
| Throat Crossover | 0.00 | 1.00 | 0.25 | Central seam interaction without reassignment |
| Taper A | 0.10 | 0.80 | 0.42 | End-to-start field scale on Branch A |
| Taper B | 0.10 | 0.80 | 0.36 | End-to-start field scale on Branch B |
| Twist A | -1.00 | 1.00 | 0.12 | Child A turns |
| Twist B | -1.00 | 1.00 | -0.08 | Child B turns |
| Child Sections | 18 | 72 | 36 | Samples along each child spine |

The table contains nine controls; keep them together in one group and preserve their exact initial values for the first visual study.

- [ ] **Step 3: Verify references and controls**

Run `gh_snapshot` and confirm both Curve parameters contain one valid curve, all nine sliders have the intended values, and no current component reports an error or warning.

### Task 5: Build the Primary Bifurcation Component with Contract-First Validation

**Files:**
- Create live object: `04 | Primary Bifurcation` C# component
- Create live object: `Primary Split Contract Check` C# component and report panel

**Interfaces:**
- Consumes: `ParentPaths:DataTree<Point3d>`, `ParentFrames:List<Plane>`, `SectionT:List<double>`, `ParentIds:List<int>`, `BranchA:Curve`, `BranchB:Curve`, and the nine controls from Task 4
- Produces: `FullPaths:DataTree<Point3d>`, `ChildAPaths:DataTree<Point3d>`, `ChildBPaths:DataTree<Point3d>`, `IdsA:List<int>`, `IdsB:List<int>`, `Summary:string`

- [ ] **Step 1: Create the bifurcation component as a compiling stub**

Create the scripted component with the exact pin contract above. Its initial body emits empty trees and `PRIMARY SPLIT NOT IMPLEMENTED`. Connect all parent outputs, Rhino references, and sliders, but do not connect it to the Pipe preview.

- [ ] **Step 2: Write and run the failing split contract check**

Create a C# validation component connected to `FullPaths`, both child trees, both child-ID lists, and the parent-ID list. Use these invariants:

```csharp
var allChildIds = IdsA.Concat(IdsB).ToList();
var failures = new List<string>();
if (IdsA.Count + IdsB.Count != ParentIds.Count)
  failures.Add("child strand total differs from parent total");
if (allChildIds.Distinct().Count() != ParentIds.Count)
  failures.Add("child identities contain duplicates or omissions");
if (!allChildIds.OrderBy(x => x).SequenceEqual(ParentIds.OrderBy(x => x)))
  failures.Add("child identity union differs from parent identities");
if (FullPaths.BranchCount != ParentIds.Count)
  failures.Add("full path count differs from parent strand count");
if (ChildAPaths.BranchCount != IdsA.Count || ChildBPaths.BranchCount != IdsB.Count)
  failures.Add("child tree paths do not match child identity lists");

Pass = failures.Count == 0;
Report = Pass
  ? $"PASS | conserved {ParentIds.Count}: A={IdsA.Count}, B={IdsB.Count}"
  : "FAIL | " + string.Join("; ", failures);
```

Expected initial result: `Pass = false` and empty-output failures.

- [ ] **Step 3: Implement deterministic strand partitioning**

Clamp the requested ratio to `[0.35, 0.65]`, then calculate:

```csharp
int n = ParentIds.Count;
int countA = Math.Max(2, Math.Min(n - 2, (int)Math.Round(n * ratioA)));
int seam = ((int)Math.Round(Clamp(seamRotation, 0.0, 1.0) * n)) % n;
var rotated = Enumerable.Range(0, n).Select(k => (seam + k) % n).ToList();
var indicesA = rotated.Take(countA).ToList();
var indicesB = rotated.Skip(countA).ToList();
```

Preserve original strand IDs and cyclic order inside each child. Do not alternate indices, randomize them, or duplicate seam strands.

- [ ] **Step 4: Build parallel-transport frames along each child spine**

Use the same minimal-rotation frame logic as the parent field. Initialize each child frame from the final parent frame projected perpendicular to the child start tangent. Require both child curves to be valid and longer than the requested transition length; otherwise emit empty trees and a specific summary message.

- [ ] **Step 5: Transport each contiguous sector into a child field**

For each child, sample `Child Sections` centers and frames. Let `s` be normalized child length, `q = Smooth5(childLength * s / transitionLength)`, and use:

```csharp
static double Smooth5(double x)
{
  x = Math.Max(0.0, Math.Min(1.0, x));
  return x * x * x * (x * (x * 6.0 - 15.0) + 10.0);
}

double childScale = Math.Sqrt((double)childCount / parentCount);
double taper = 1.0 + (childEndScale - 1.0) * Smooth5(s);
double theta = 2.0 * Math.PI * localRank / childCount + 2.0 * Math.PI * childTwist * s;
Vector3d childOffset = childFrame.XAxis * (radiusX * childScale * taper * Math.Cos(theta))
                     + childFrame.YAxis * (radiusY * childScale * taper * Math.Sin(theta));
Point3d point = childCenter + (1.0 - q) * parentSectorOffset + q * childOffset;
```

Use each assigned strand's parent offset at the transition start as `parentSectorOffset`. Apply `Throat Crossover` only to strands within the nearest 15% of either sector boundary: add a signed sinusoidal angular bias that reaches its maximum at `q = 0.5` and returns to zero at `q = 1.0`. This creates central interaction without moving an identity to the other child.

- [ ] **Step 6: Assemble every full path without geometric joins**

For each strand identity, copy its ordered parent points only through the transition-start section, then append the generated child points beginning at index 1 so the shared starting point is not duplicated. Store the result under path `{strandId}` in `FullPaths`; store the generated child-only points under the same identity path in the appropriate child tree.

Reject a result if the distance from the final retained parent point to the first appended child point exceeds `0.35 m`. Report the offending strand ID in `Summary` instead of emitting a misleading curve.

- [ ] **Step 7: Verify the split contract turns green**

Wait for a settled solution and require:

- `Pass = true`;
- the child counts sum to the current parent strand count;
- the ID sets are disjoint and their union equals the parent IDs;
- every full path contains more points than its retained parent portion;
- the summary reports the actual rounded allocation; and
- `gh_errors` reports zero errors and warnings.

### Task 6: Add the Modular Curve Builder and Restore Pipe Preview

**Files:**
- Create live object: `05 | Strand Curve Builder` C# component
- Modify live object: existing native Pipe component and its group

**Interfaces:**
- Consumes: `Paths:DataTree<Point3d>` from `Primary Bifurcation`
- Produces: `Curves:List<Curve>`, `ValidIds:List<int>`, `Summary:string`

- [ ] **Step 1: Create a failing curve-output check**

Create the curve builder as a stub returning empty lists. Connect `FullPaths` to it and connect its `Curves` output to a panel or validation component that compares `Curves.Count` to `ParentIds.Count`. Confirm the check fails before adding curve construction.

- [ ] **Step 2: Implement one curve per full path**

Use this construction rule for each nonempty path:

```csharp
for (int b = 0; b < Paths.BranchCount; b++)
{
  GH_Path path = Paths.Paths[b];
  int id = path.Indices[path.Indices.Length - 1];
  var points = Paths.Branch(b).ToList();
  if (points.Count < 4) failures.Add($"strand {id} has fewer than four points");
  else
  {
    Curve curve = Curve.CreateInterpolatedCurve(points, 3, CurveKnotStyle.Chord);
    if (curve == null || !curve.IsValid) failures.Add($"strand {id} curve is invalid");
    else { curves.Add(curve); validIds.Add(id); }
  }
}
```

Emit no partial curve list when any path is invalid; return the complete failure report instead. Set `Summary` to `PASS | N continuous strand curves` only when every path succeeds.

- [ ] **Step 3: Reconnect the native Pipe preview**

Connect `Curves` to the existing Pipe's rail input. Preserve the user's current Wire Radius, Pipe Caps, and Fit Rail values. Hide previews for the parent field, bifurcation point trees, Rhino-reference parameters, and curve builder so only the Pipe component previews the final wire geometry.

- [ ] **Step 4: Reorganize the canvas by responsibility**

Create or rename groups so the live definition reads left-to-right:

1. `01 | RHINO DRIVERS`
2. `02 | PARENT TRUNK CONTROLS`
3. `03 | PARENT STRAND FIELD`
4. `04 | PRIMARY SPLIT CONTROLS`
5. `05 | PRIMARY BIFURCATION`
6. `06 | CURVE + PIPE PREVIEW`
7. `07 | CONTRACT CHECKS`

Keep native components visible; do not create clusters or hide the data-flow boundary inside a single oversized component.

- [ ] **Step 5: Verify complete geometry output**

Inspect `Curves` and Pipe outputs. Require one valid curve and one pipe Brep per parent strand, with zero empty branches, zero runtime errors, and zero warnings.

### Task 7: Tune the First Asymmetric Fork and Complete the Review Gate

**Files:**
- Modify live artifacts: `Tree.3dm` and `Tree.gh`

**Interfaces:**
- Consumes: the complete modular pipeline and the four saved evaluation views
- Produces: a saved Rhino study and an unsaved-but-ready Grasshopper definition awaiting the user's `Ctrl+S`

- [ ] **Step 1: Establish the initial asymmetric study**

Begin with the approved defaults: approximately 60% of strands to Branch A, 40% to Branch B, one-metre transition, modest seam rotation, and limited central crossover. Adjust only execution-owned branch controls and the two new Rhino curves; do not change the user's parent-trunk sliders during this tuning pass.

- [ ] **Step 2: Evaluate the Front view**

Capture `VIP Tree - Reference Front`. Require a dense shared throat, a smooth visual separation, a stronger upward bundle, and no hard Y-junction, detached curves, or mirrored silhouette.

- [ ] **Step 3: Evaluate Right, Top, and Perspective**

Capture `VIP Tree - Side Right`, `VIP Tree - Top`, and standard `Perspective`. Require visible depth separation between the child spines and no view in which the primary fork collapses into a flat planar split.

- [ ] **Step 4: Apply at most one bounded visual correction pass**

If the transition is technically valid but visually unconvincing, adjust only these controls or driver points:

- Branch A/B Rhino control points;
- Split Ratio A;
- Transition Length;
- Seam Rotation;
- Throat Crossover; and
- child taper/twist.

Do not expand scope into secondary branching. After the correction, recapture all four views and rerun the contract checks.

- [ ] **Step 5: Run the final verification checkpoint**

Run `gh_status`, `gh_errors`, and `gh_snapshot(include_data=true)`. Inspect parent paths, full paths, both child fields, final curves, and pipe output. Confirm every acceptance criterion in the spec with fresh evidence.

- [ ] **Step 6: Save and hand off**

Save `Tree.3dm` to its existing path and verify the Rhino document is not modified. Report the final strand allocation, transition settings, output counts, four image paths, and any remaining visual limitations. Ask the user to press `Ctrl+S` in Grasshopper because `Tree.gh` will remain marked modified.

## Execution Checkpoints

- **Checkpoint A — Parent preserved:** Task 3 contract passes and the four pre-split views match the baseline.
- **Checkpoint B — Topology valid:** Task 5 conserves every strand and produces two asymmetric child fields without errors.
- **Checkpoint C — Geometry restored:** Task 6 produces one curve and pipe per strand.
- **Checkpoint D — Visual review:** Task 7 passes all four views before any secondary branch work begins.
