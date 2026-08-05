# Bank of China Tower Reference Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, calibrate, validate, bake, and save a parametric Bank of China Tower exterior whose massing and expressed structural geometry agree convincingly with all nine supplied reference images.

**Architecture:** One execution-owned RhinoCode C# Script component generates four calibrated triangular massing sectors, transition glass, a graph-derived super-frame, curtain-wall guides, podium, roof frame, masts, landmarks, and diagnostics. Grasshopper remains the geometric source of truth; Rhino supplies saved cameras, baked review layers, viewport captures, and the final `.3dm`, while ignored JSON/Markdown artifacts retain evidence, calibration, and residuals.

**Tech Stack:** Windows, Rhino 8, Grasshopper, RhinoCode C#, RhinoCommon, Rook `rhino_*` and `gh_*` tools, JSON evidence records, and PNG viewport captures.

## Global Constraints

- Model in metres with World Z vertical and the 52 m base square centred on the World origin.
- Target an explicitly admitted Rhino document and active Grasshopper document; preserve all pre-existing content.
- Create, edit, group, bake, and clear only execution-owned objects.
- Treat analytical plans/elevations/sections as primary geometry evidence, axonometrics as orientation evidence, and photographs as validation evidence.
- Keep all low-confidence dimensions exposed as Grasshopper inputs; do not bury them as unexplained constants.
- Validate massing before enabling structure, and validate structure before enabling envelope detail.
- Require analytical landmark RMSE at or below 1% of source-image diagonal and photographic landmark RMSE at or below 2%.
- Do not use raw pixel similarity as an acceptance metric.
- Do not add Rook product features, external dependencies, interiors, BIM data, engineering analysis, or construction-detail claims.
- Use fresh Grasshopper snapshots and epochs for every mutation; inspect partial-success results before retrying.
- Bake only after the nine-source audit passes.
- Store generated outputs under ignored `artifacts/bank-of-china-tower/`; do not copy the source images into the repository.

---

## File and Live-State Map

**Create ignored execution artifacts:**

- `artifacts/bank-of-china-tower/evidence/manifest.json` — immutable source inventory and evidence precedence.
- `artifacts/bank-of-china-tower/evidence/assumptions.json` — calibrated parameters with confidence and provenance.
- `artifacts/bank-of-china-tower/validation/landmarks.json` — normalized source-image landmark observations and corresponding 3D semantic names.
- `artifacts/bank-of-china-tower/validation/score_landmarks.py` — standard-library residual calculator shared by analytical and photographic checkpoints.
- `artifacts/bank-of-china-tower/validation/camera-candidate.json` — the numeric working camera consumed by the Rhino camera/projection scripts.
- `artifacts/bank-of-china-tower/validation/cameras.json` — accepted Rhino camera parameters and residuals.
- `artifacts/bank-of-china-tower/validation/report.md` — checkpoint results and unresolved uncertainty.
- `artifacts/bank-of-china-tower/execution-ledger.json` — document identities, created IDs, mutations, bake IDs, and save receipts.
- `artifacts/bank-of-china-tower/BankOfChinaTower.gh` — editable Grasshopper definition; one explicit user Save As is allowed only if no admitted host save path exists.
- `artifacts/bank-of-china-tower/BankOfChinaTower.3dm` — layered baked Rhino deliverable.
- `artifacts/bank-of-china-tower/validation/captures/*.png` — clean Rhino captures.
- `artifacts/bank-of-china-tower/validation/overlays/*.png` — source/capture comparisons.

**Create live Grasshopper objects:**

- one `BOC Exterior Generator` RhinoCode C# Script component;
- nineteen sliders controlling geometry and detail mode;
- three evidence/usage Panels; and
- one group named `Bank of China Tower — Reference Reconstruction`.

**Create live Rhino layers at final bake:**

- `BOC::Massing`
- `BOC::Glass`
- `BOC::Structure`
- `BOC::Transfer Bands`
- `BOC::Curtain Grid`
- `BOC::Podium`
- `BOC::Roof and Masts`
- `BOC::Validation`

---

### Task 1: Admit the Live Targets and Build the Evidence Package

**Files:**

- Create: `artifacts/bank-of-china-tower/evidence/manifest.json`
- Create: `artifacts/bank-of-china-tower/evidence/assumptions.json`
- Create: `artifacts/bank-of-china-tower/validation/landmarks.json`
- Create: `artifacts/bank-of-china-tower/validation/score_landmarks.py`
- Create: `artifacts/bank-of-china-tower/execution-ledger.json`
- Reference: `docs/superpowers/specs/2026-08-05-bank-of-china-tower-reference-reconstruction-design.md`

**Interfaces:**

- Consumes: nine JPEG files under `C:/Users/aryan/Desktop/BoCTower`
- Produces: admitted document identities, a fixed source authority table, semantic landmark observations, and calibrated seed values consumed by Tasks 2-5

- [ ] **Step 1: Re-admit Rhino and Grasshopper without mutation**

Run `rhino_ping`, `rhino_document`, `rhino_objects`, `gh_status`, and `gh_snapshot`. Record Rhino document serial/path, Grasshopper document ID/name, snapshot epoch, all pre-existing Rhino object IDs, and all pre-existing Grasshopper component IDs in `execution-ledger.json`.

Stop if the active documents are ambiguous, Grasshopper has no active document, or the solver is unavailable. If either document contains pre-existing content, preserve it and record the baseline instead of clearing it.

- [ ] **Step 2: Create the immutable source manifest**

Write this exact top-level shape, filling file sizes and image dimensions from the filesystem inventory:

```json
{
  "schema_version": 1,
  "project": "bank-of-china-tower-reference-reconstruction",
  "units": "Meters",
  "source_root": "C:/Users/aryan/Desktop/BoCTower",
  "authority_order": [
    "analytical_orthographic",
    "analytical_axonometric",
    "multi_photo_agreement",
    "single_photo",
    "explicit_assumption"
  ],
  "sources": [
    {"file":"boc-07.jpg","role":"analytical_orthographic","contains":["elevation","plan_story_4","plan_story_25","plan_story_39","plan_story_51_52"]},
    {"file":"e777e6f3ae01c8bdfcb40c111a685022.jpg","role":"analytical_orthographic","contains":["elevation","section","story_landmarks","central_column_transfer"]},
    {"file":"boc-08.jpg","role":"analytical_axonometric","contains":["massing_orientation","setback_order"]},
    {"file":"boc-06.jpg","role":"analytical_axonometric","contains":["four_sector_concept","structural_expression"]},
    {"file":"boc-01.jpg","role":"photo_validation","contains":["low_oblique","two_facades","podium"]},
    {"file":"boc-02.jpg","role":"photo_validation","contains":["elevation_like","full_silhouette"]},
    {"file":"boc-03.jpg","role":"photo_validation","contains":["distant_oblique","full_silhouette","site_context"]},
    {"file":"boc-04.jpg","role":"photo_validation","contains":["oblique","setback_orientation","podium"]},
    {"file":"boc-05.jpg","role":"photo_validation","contains":["low_oblique","primary_brace_face","masts"]}
  ]
}
```

- [ ] **Step 3: Measure semantic landmarks and seed calibration parameters**

For each analytical sheet, record normalized `(u, v)` coordinates in `[0,1]` for every visible base corner, centre point, documented-plan outline vertex, major setback vertex, roof corner, and mast top. For each photograph, record at least eight distributed landmarks covering the base, two setbacks, two brace nodes, roof, and masts.

Use this record shape for each observation:

```json
{
  "source": "boc-05.jpg",
  "view": "photo",
  "name": "roof_high_corner",
  "image_width": 418,
  "image_height": 732,
  "u": 0.4213,
  "v": 0.1274,
  "confidence": "medium",
  "world_semantic": "roof_high_corner"
}
```

Seed `assumptions.json` with `base_size_m=52.0`, `podium_height_m=20.0`, sector terminal heights `112.0`, `176.0`, `232.0`, and `315.0`, mast top `367.4`, transfer levels `72.0`, `124.0`, `176.0`, `228.0`, and `280.0`, floor spacing `4.0`, brace width `2.0`, brace depth `1.2`, mullion spacing `1.5`, mast spacing `8.0`, and quarter-turn orientation `0`. Mark only the 52 m base organization as high confidence; mark every unmeasured seed as low or medium with its image provenance.

- [ ] **Step 4: Create the shared residual calculator**

Write `validation/score_landmarks.py` with this complete standard-library implementation:

```python
import json
import math
import pathlib
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: score_landmarks.py <landmarks.json> <source-file>")

path = pathlib.Path(sys.argv[1])
source = sys.argv[2]
document = json.loads(path.read_text(encoding="utf-8"))
rows = [row for row in document["observations"]
        if row["source"] == source
        and "projected_u" in row
        and "projected_v" in row]
if not rows:
    raise SystemExit("no projected observations for " + source)

squared = []
for row in rows:
    width = float(row["image_width"])
    height = float(row["image_height"])
    diagonal = math.hypot(width, height)
    dx = (float(row["projected_u"]) - float(row["u"])) * width
    dy = (float(row["projected_v"]) - float(row["v"])) * height
    error = math.hypot(dx, dy) / diagonal
    squared.append(error * error)
    print("{} {:.8f}".format(row["name"], error))

rmse = math.sqrt(sum(squared) / len(squared))
print("RMSE {:.8f} COUNT {}".format(rmse, len(rows)))
```

- [ ] **Step 5: Checkpoint evidence completeness**

Require all nine files in the manifest, at least one source observation for every required semantic landmark, finite normalized coordinates, correct image dimensions, monotonically increasing terminal/transfer levels, `mast_top_m > roof_height_m`, a runnable residual calculator, and an execution ledger containing both baseline inventories. Do not create Grasshopper geometry until this checkpoint passes.

### Task 2: Create the Parametric Exterior Generator

**Files:**

- Create live object: `BOC Exterior Generator` C# Script component
- Modify: `artifacts/bank-of-china-tower/execution-ledger.json`

**Interfaces:**

- Consumes scalar inputs `BaseSize`, `PodiumHeight`, `H0`, `H1`, `H2`, `RoofHeight`, `MastTop`, `L1`-`L5`, `FloorSpacing`, `BraceWidth`, `BraceDepth`, `MullionSpacing`, `MastSpacing`, `QuarterTurn`, and `DetailMode`
- Produces list outputs `Massing:Brep`, `Glass:Brep`, `BraceAxes:Curve`, `Braces:Brep`, `TransferBands:Brep`, `CurtainGrid:Curve`, `Podium:Brep`, `Masts:Brep`, `Landmarks:Point3d`, `LandmarkNames:string`, and `Diagnostics:string`

- [ ] **Step 1: Write the complete generator component**

Invoke `gh_create_csharp_script` at `[760, 280]` with `name="BOC Exterior Generator"` and this exact pin contract:

```json
{
  "pins_in": [
    "BaseSize:double", "PodiumHeight:double", "H0:double", "H1:double", "H2:double",
    "RoofHeight:double", "MastTop:double", "L1:double", "L2:double", "L3:double",
    "L4:double", "L5:double", "FloorSpacing:double", "BraceWidth:double",
    "BraceDepth:double", "MullionSpacing:double", "MastSpacing:double",
    "QuarterTurn:int", "DetailMode:int"
  ],
  "pins_out": [
    {"name":"Massing","type":"Brep","access":"list"},
    {"name":"Glass","type":"Brep","access":"list"},
    {"name":"BraceAxes","type":"Curve","access":"list"},
    {"name":"Braces","type":"Brep","access":"list"},
    {"name":"TransferBands","type":"Brep","access":"list"},
    {"name":"CurtainGrid","type":"Curve","access":"list"},
    {"name":"Podium","type":"Brep","access":"list"},
    {"name":"Masts","type":"Brep","access":"list"},
    {"name":"Landmarks","type":"Point3d","access":"list"},
    {"name":"LandmarkNames","type":"string","access":"list"},
    {"name":"Diagnostics","type":"string","access":"list"}
  ]
}
```

Use the following complete class code as the `code` value:

```csharp
using System;
using System.Collections.Generic;
using Rhino;
using Rhino.Geometry;

public class Script_Instance : GH_ScriptInstance
{
  private static double D(object value, double fallback)
  {
    if (value == null) return fallback;
    try { return Convert.ToDouble(value); }
    catch { return fallback; }
  }

  private static int I(object value, int fallback)
  {
    if (value == null) return fallback;
    try { return Convert.ToInt32(value); }
    catch { return fallback; }
  }

  private static Point3d AtZ(Point3d point, double z)
  {
    return new Point3d(point.X, point.Y, z);
  }

  private static Point3d Lerp(Point3d a, Point3d b, double t)
  {
    return new Point3d(
      a.X + t * (b.X - a.X),
      a.Y + t * (b.Y - a.Y),
      a.Z + t * (b.Z - a.Z));
  }

  private static Brep PlanarFace(double tolerance, params Point3d[] points)
  {
    var polyline = new Polyline(points);
    polyline.Add(points[0]);
    var curve = new PolylineCurve(polyline);
    var faces = Brep.CreatePlanarBreps(new Curve[] { curve }, tolerance);
    return faces != null && faces.Length > 0 ? faces[0] : null;
  }

  private static Brep Sector(
    Point3d outer0,
    Point3d outer1,
    Point3d center,
    double baseZ,
    double outerTopZ,
    double centerTopZ,
    double tolerance)
  {
    Point3d b0 = AtZ(outer0, baseZ);
    Point3d b1 = AtZ(outer1, baseZ);
    Point3d bc = AtZ(center, baseZ);
    Point3d t0 = AtZ(outer0, outerTopZ);
    Point3d t1 = AtZ(outer1, outerTopZ);
    Point3d tc = AtZ(center, centerTopZ);

    var faces = new List<Brep>
    {
      PlanarFace(tolerance, b0, bc, b1),
      PlanarFace(tolerance, t0, t1, tc),
      PlanarFace(tolerance, b0, b1, t1, t0),
      PlanarFace(tolerance, b1, bc, tc, t1),
      PlanarFace(tolerance, bc, b0, t0, tc)
    };
    faces.RemoveAll(face => face == null);
    var joined = Brep.JoinBreps(faces, tolerance);
    return joined != null && joined.Length > 0 ? joined[0] : null;
  }

  private static Brep MemberBox(Line axis, Vector3d faceNormal, double width, double depth)
  {
    Vector3d x = axis.Direction;
    double length = x.Length;
    if (length <= 1e-6 || !x.Unitize()) return null;

    Vector3d z = faceNormal;
    if (!z.Unitize()) z = Vector3d.XAxis;
    Vector3d y = Vector3d.CrossProduct(z, x);
    if (!y.Unitize())
    {
      z = Math.Abs(x * Vector3d.ZAxis) < 0.95 ? Vector3d.ZAxis : Vector3d.XAxis;
      y = Vector3d.CrossProduct(z, x);
      if (!y.Unitize()) return null;
    }

    var plane = new Plane(axis.PointAt(0.5), x, y);
    return new Box(
      plane,
      new Interval(-0.5 * length, 0.5 * length),
      new Interval(-0.5 * width, 0.5 * width),
      new Interval(-0.5 * depth, 0.5 * depth)).ToBrep();
  }

  private static void AddSideSystem(
    Point3d p0,
    Point3d p1,
    double baseZ,
    double topZ,
    List<double> transferLevels,
    double floorSpacing,
    double braceWidth,
    double braceDepth,
    double mullionSpacing,
    int detailMode,
    List<Curve> braceAxes,
    List<Brep> braces,
    List<Brep> bands,
    List<Curve> curtainGrid)
  {
    Vector3d side = p1 - p0;
    Vector3d normal = Vector3d.CrossProduct(side, Vector3d.ZAxis);
    normal.Unitize();

    var levels = new List<double> { baseZ };
    foreach (double level in transferLevels)
      if (level > baseZ + 1e-6 && level < topZ - 1e-6) levels.Add(level);
    levels.Add(topZ);
    levels.Sort();

    if (detailMode >= 1)
    {
      for (int i = 0; i < levels.Count - 1; i++)
      {
        double za = levels[i];
        double zb = levels[i + 1];
        var d0 = new Line(AtZ(p0, za), AtZ(p1, zb));
        var d1 = new Line(AtZ(p1, za), AtZ(p0, zb));
        braceAxes.Add(new LineCurve(d0));
        braceAxes.Add(new LineCurve(d1));
        Brep b0 = MemberBox(d0, normal, braceWidth, braceDepth);
        Brep b1 = MemberBox(d1, normal, braceWidth, braceDepth);
        if (b0 != null) braces.Add(b0);
        if (b1 != null) braces.Add(b1);
      }

      foreach (double level in levels)
      {
        var bandAxis = new Line(AtZ(p0, level), AtZ(p1, level));
        Brep band = MemberBox(bandAxis, normal, braceWidth, braceDepth);
        if (band != null) bands.Add(band);
      }
    }

    if (detailMode >= 2)
    {
      double sideLength = p0.DistanceTo(p1);
      int divisions = Math.Max(2, (int)Math.Round(sideLength / mullionSpacing));
      for (int i = 1; i < divisions; i++)
      {
        double t = i / (double)divisions;
        Point3d xy = p0 + t * (p1 - p0);
        curtainGrid.Add(new LineCurve(AtZ(xy, baseZ), AtZ(xy, topZ)));
      }
      for (double z = baseZ + floorSpacing; z < topZ - 1e-6; z += floorSpacing)
        curtainGrid.Add(new LineCurve(AtZ(p0, z), AtZ(p1, z)));
    }
  }

  private void RunScript(
    object BaseSize,
    object PodiumHeight,
    object H0,
    object H1,
    object H2,
    object RoofHeight,
    object MastTop,
    object L1,
    object L2,
    object L3,
    object L4,
    object L5,
    object FloorSpacing,
    object BraceWidth,
    object BraceDepth,
    object MullionSpacing,
    object MastSpacing,
    object QuarterTurn,
    object DetailMode,
    ref object Massing,
    ref object Glass,
    ref object BraceAxes,
    ref object Braces,
    ref object TransferBands,
    ref object CurtainGrid,
    ref object Podium,
    ref object Masts,
    ref object Landmarks,
    ref object LandmarkNames,
    ref object Diagnostics)
  {
    double size = Math.Max(1.0, D(BaseSize, 52.0));
    double podiumZ = Math.Max(0.1, D(PodiumHeight, 20.0));
    double h0 = Math.Max(podiumZ + 1.0, D(H0, 112.0));
    double h1 = Math.Max(h0 + 1.0, D(H1, 176.0));
    double h2 = Math.Max(h1 + 1.0, D(H2, 232.0));
    double roofZ = Math.Max(h2 + 1.0, D(RoofHeight, 315.0));
    double mastTopZ = Math.Max(roofZ + 1.0, D(MastTop, 367.4));
    double floor = Math.Max(0.25, D(FloorSpacing, 4.0));
    double braceW = Math.Max(0.05, D(BraceWidth, 2.0));
    double braceD = Math.Max(0.05, D(BraceDepth, 1.2));
    double mullion = Math.Max(0.25, D(MullionSpacing, 1.5));
    double mastSpacing = Math.Max(0.5, D(MastSpacing, 8.0));
    int turns = ((I(QuarterTurn, 0) % 4) + 4) % 4;
    int mode = Math.Max(0, Math.Min(2, I(DetailMode, 0)));
    double tolerance = RhinoDoc.ActiveDoc != null
      ? RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
      : 0.001;

    double half = 0.5 * size;
    var corners = new[]
    {
      new Point3d(-half, -half, 0.0),
      new Point3d( half, -half, 0.0),
      new Point3d( half,  half, 0.0),
      new Point3d(-half,  half, 0.0)
    };
    Transform rotation = Transform.Rotation(turns * 0.5 * Math.PI, Vector3d.ZAxis, Point3d.Origin);
    for (int i = 0; i < corners.Length; i++) corners[i].Transform(rotation);

    Point3d center = Point3d.Origin;
    double[] outerTops = { h0, h1, h2, roofZ };
    double[] centerTops = { h1, h2, roofZ, roofZ };
    var massing = new List<Brep>();
    var glass = new List<Brep>();
    var diagnostics = new List<string>();

    for (int i = 0; i < 4; i++)
    {
      Point3d a = corners[i];
      Point3d b = corners[(i + 1) % 4];
      Brep sector = Sector(a, b, center, podiumZ, outerTops[i], centerTops[i], tolerance);
      if (sector != null && sector.IsValid) massing.Add(sector);
      else diagnostics.Add("sector_" + i + " invalid");

      Brep outerGlass = PlanarFace(tolerance,
        AtZ(a, podiumZ), AtZ(b, podiumZ), AtZ(b, outerTops[i]), AtZ(a, outerTops[i]));
      Brep transitionGlass = PlanarFace(tolerance,
        AtZ(a, outerTops[i]), AtZ(b, outerTops[i]), AtZ(center, centerTops[i]));
      if (outerGlass != null) glass.Add(outerGlass);
      if (transitionGlass != null) glass.Add(transitionGlass);
    }

    var braceAxes = new List<Curve>();
    var braces = new List<Brep>();
    var bands = new List<Brep>();
    var curtainGrid = new List<Curve>();
    var transfers = new List<double>
    {
      D(L1, 72.0), D(L2, 124.0), D(L3, 176.0), D(L4, 228.0), D(L5, 280.0)
    };
    transfers.Sort();

    for (int i = 0; i < 4; i++)
      AddSideSystem(corners[i], corners[(i + 1) % 4], podiumZ, outerTops[i],
        transfers, floor, braceW, braceD, mullion, mode,
        braceAxes, braces, bands, curtainGrid);

    if (mode >= 1)
    {
      for (int i = 0; i < 4; i++)
      {
        Point3d t0 = AtZ(corners[i], outerTops[i]);
        Point3d t1 = AtZ(corners[(i + 1) % 4], outerTops[i]);
        Point3d tc = AtZ(center, centerTops[i]);
        Vector3d transitionNormal = Vector3d.CrossProduct(t1 - t0, tc - t0);
        var transitionAxes = new[]
        {
          new Line(t0, t1),
          new Line(t0, tc),
          new Line(t1, tc),
          new Line(Lerp(t0, t1, 0.5), tc)
        };
        foreach (Line axis in transitionAxes)
        {
          braceAxes.Add(new LineCurve(axis));
          Brep transitionMember = MemberBox(axis, transitionNormal, braceW, braceD);
          if (transitionMember != null) braces.Add(transitionMember);
        }
      }

      for (int i = 0; i < 4; i++)
      {
        double cornerTop = Math.Max(outerTops[i], outerTops[(i + 3) % 4]);
        var vertical = new Line(AtZ(corners[i], podiumZ), AtZ(corners[i], cornerTop));
        Vector3d radial = corners[i] - center;
        Brep member = MemberBox(vertical, radial, braceW, braceD);
        braceAxes.Add(new LineCurve(vertical));
        if (member != null) braces.Add(member);
      }
    }

    var podium = new List<Brep>
    {
      new Box(Plane.WorldXY,
        new Interval(-half, half),
        new Interval(-half, half),
        new Interval(0.0, podiumZ)).ToBrep()
    };

    var masts = new List<Brep>();
    Point3d highA = corners[3];
    Point3d highB = corners[0];
    Point3d outerMid = Lerp(highA, highB, 0.5);
    Point3d roofFrameCenter = Lerp(center, outerMid, 0.35);
    Vector3d mastAxis = highB - highA;
    mastAxis.Unitize();
    Point3d mast0xy = roofFrameCenter - 0.5 * mastSpacing * mastAxis;
    Point3d mast1xy = roofFrameCenter + 0.5 * mastSpacing * mastAxis;
    Vector3d mastNormal = highB - highA;
    if (mode >= 2)
    {
      var mast0 = new Line(AtZ(mast0xy, roofZ), AtZ(mast0xy, mastTopZ));
      var mast1 = new Line(AtZ(mast1xy, roofZ), AtZ(mast1xy, mastTopZ));
      double frameZ = roofZ + Math.Min(12.0, 0.25 * (mastTopZ - roofZ));
      var crossbar = new Line(AtZ(mast0xy, frameZ), AtZ(mast1xy, frameZ));
      var roofDiag0 = new Line(AtZ(mast0xy, roofZ), AtZ(mast1xy, frameZ));
      var roofDiag1 = new Line(AtZ(mast1xy, roofZ), AtZ(mast0xy, frameZ));
      Brep mb0 = MemberBox(mast0, mastNormal, 0.45, 0.45);
      Brep mb1 = MemberBox(mast1, mastNormal, 0.45, 0.45);
      Brep cb = MemberBox(crossbar, Vector3d.ZAxis, 0.45, 0.45);
      Brep rd0 = MemberBox(roofDiag0, mastNormal, 0.45, 0.45);
      Brep rd1 = MemberBox(roofDiag1, mastNormal, 0.45, 0.45);
      if (mb0 != null) masts.Add(mb0);
      if (mb1 != null) masts.Add(mb1);
      if (cb != null) masts.Add(cb);
      if (rd0 != null) masts.Add(rd0);
      if (rd1 != null) masts.Add(rd1);

      Point3d entranceA = Lerp(corners[0], corners[1], 0.36);
      Point3d entranceB = Lerp(corners[0], corners[1], 0.64);
      Vector3d entranceNormal = Vector3d.CrossProduct(corners[1] - corners[0], Vector3d.ZAxis);
      var jamb0 = new Line(AtZ(entranceA, 0.0), AtZ(entranceA, 0.72 * podiumZ));
      var jamb1 = new Line(AtZ(entranceB, 0.0), AtZ(entranceB, 0.72 * podiumZ));
      var header = new Line(AtZ(entranceA, 0.72 * podiumZ), AtZ(entranceB, 0.72 * podiumZ));
      Brep pj0 = MemberBox(jamb0, entranceNormal, 0.65, 0.65);
      Brep pj1 = MemberBox(jamb1, entranceNormal, 0.65, 0.65);
      Brep ph = MemberBox(header, entranceNormal, 0.65, 0.65);
      if (pj0 != null) podium.Add(pj0);
      if (pj1 != null) podium.Add(pj1);
      if (ph != null) podium.Add(ph);
    }

    var landmarks = new List<Point3d>();
    var landmarkNames = new List<string>();
    Action<string, Point3d> addLandmark = (name, point) =>
    {
      landmarkNames.Add(name);
      landmarks.Add(point);
    };

    for (int i = 0; i < 4; i++)
    {
      addLandmark("base_" + i, corners[i]);
      addLandmark("podium_" + i, AtZ(corners[i], podiumZ));
    }
    for (int i = 0; i < 4; i++)
    {
      addLandmark("sector_" + i + "_outer0_top", AtZ(corners[i], outerTops[i]));
      addLandmark("sector_" + i + "_outer1_top", AtZ(corners[(i + 1) % 4], outerTops[i]));
      addLandmark("sector_" + i + "_center_top", AtZ(center, centerTops[i]));
      for (int j = 0; j < transfers.Count; j++)
      {
        if (transfers[j] <= podiumZ + 1e-6 || transfers[j] >= outerTops[i] - 1e-6) continue;
        addLandmark("side_" + i + "_transfer_" + j + "_p0", AtZ(corners[i], transfers[j]));
        addLandmark("side_" + i + "_transfer_" + j + "_p1", AtZ(corners[(i + 1) % 4], transfers[j]));
      }
    }
    addLandmark("roof_center", AtZ(center, roofZ));
    addLandmark("mast_0_base", AtZ(mast0xy, roofZ));
    addLandmark("mast_1_base", AtZ(mast1xy, roofZ));
    addLandmark("mast_0_top", AtZ(mast0xy, mastTopZ));
    addLandmark("mast_1_top", AtZ(mast1xy, mastTopZ));

    diagnostics.Add("massing=" + massing.Count);
    diagnostics.Add("glass=" + glass.Count);
    diagnostics.Add("brace_axes=" + braceAxes.Count);
    diagnostics.Add("brace_solids=" + braces.Count);
    diagnostics.Add("transfer_bands=" + bands.Count);
    diagnostics.Add("curtain_grid=" + curtainGrid.Count);
    diagnostics.Add("landmark_count=" + landmarks.Count);
    diagnostics.Add("landmark_names_parallel=true");

    Massing = massing;
    Glass = glass;
    BraceAxes = braceAxes;
    Braces = braces;
    TransferBands = bands;
    CurtainGrid = curtainGrid;
    Podium = podium;
    Masts = masts;
    Landmarks = landmarks;
    LandmarkNames = landmarkNames;
    Diagnostics = diagnostics;
  }
}
```

- [ ] **Step 2: Verify compilation before creating controls**

Poll `gh_status`, capture a fresh `gh_snapshot`, and run `gh_errors`. Require one compiled `BOC Exterior Generator`, exactly eleven named outputs, zero errors, four valid massing items, eight glass faces, one podium item, equal nonzero `Landmarks`/`LandmarkNames` counts, required base/sector/transfer/roof/mast semantic names, and `DetailMode=0` behavior with no braces, transfer bands, curtain grid, or roof/mast solids.

Record the component GUID, short ID, input indices, output indices, and fresh epoch in the execution ledger. Stop if the component does not satisfy the pin contract; do not create sliders against an uncertain pin order.

### Task 3: Add Controls and Calibrate the Primary Massing

**Files:**

- Create live objects: nineteen sliders, three Panels, and one execution-owned group
- Modify: `artifacts/bank-of-china-tower/evidence/assumptions.json`
- Modify: `artifacts/bank-of-china-tower/execution-ledger.json`
- Create: analytical captures under `artifacts/bank-of-china-tower/validation/captures/`

**Interfaces:**

- Consumes: generator ID/pin map and Task 1 calibrated seeds
- Produces: connected controls and an accepted four-sector massing at `DetailMode=0`

- [ ] **Step 1: Create and connect all controls in one bounded `gh_edit` batch**

Use the fresh Task 2 epoch. Create sliders with these ranges and seed values, arranged in two vertical columns left of the generator:

| Input | Range | Seed |
| --- | ---: | ---: |
| BaseSize | 40-65 | 52 |
| PodiumHeight | 8-35 | 20 |
| H0 | 80-150 | 112 |
| H1 | 140-210 | 176 |
| H2 | 200-270 | 232 |
| RoofHeight | 280-330 | 315 |
| MastTop | 330-385 | 367.4 |
| L1 | 45-100 | 72 |
| L2 | 90-150 | 124 |
| L3 | 140-205 | 176 |
| L4 | 190-255 | 228 |
| L5 | 245-305 | 280 |
| FloorSpacing | 3-5 | 4 |
| BraceWidth | 0.5-4 | 2 |
| BraceDepth | 0.25-3 | 1.2 |
| MullionSpacing | 0.75-3 | 1.5 |
| MastSpacing | 3-15 | 8 |
| QuarterTurn | 0-3 integer | 0 |
| DetailMode | 0-2 integer | 0 |

Connect each slider to the matching input index from the fresh pin map. Add Panels containing the evidence precedence, the `DetailMode` meanings (`0 massing`, `1 structure`, `2 envelope/secondary`), and the landmark naming convention. Group all execution-owned components as `Bank of China Tower — Reference Reconstruction`. Inspect every operation result and temp-ID mapping before continuing.

- [ ] **Step 2: Resolve tower orientation once**

Capture standard `Front`, `Right`, `Back`, `Left`, `Top`, and `Perspective` views with `rhino_viewport`, `zoomExtents=true`, grid/axes disabled, and `Arctic` or `Shaded` display. Compare the sector termination order against `boc-08.jpg` and the plan sequence in `boc-07.jpg`.

Change only `QuarterTurn` until the documented plan evolution and axonometric orientation agree. Record the accepted integer in `assumptions.json`; after this checkpoint, do not rotate the model to repair a single photograph.

- [ ] **Step 3: Calibrate base, podium, sector terminals, roof, and masts**

Keep `DetailMode=0`. Adjust `PodiumHeight`, `H0`, `H1`, `H2`, `RoofHeight`, `MastTop`, and `MastSpacing` against analytical normalized landmarks. Re-capture the affected orthographic view after each bounded parameter batch and compute normalized landmark RMSE.

After writing projected coordinates into the relevant landmark rows, run:

```powershell
python artifacts/bank-of-china-tower/validation/score_landmarks.py artifacts/bank-of-china-tower/validation/landmarks.json boc-07.jpg
```

Repeat with the current analytical source filename; the printed `RMSE` is the checkpoint value.

Accept massing only when:

- `Massing` contains four valid closed bodies;
- the documented plan states have the correct topology;
- every analytical orthographic sheet is at or below 1% normalized RMSE;
- setback order/orientation agrees with both axonometrics; and
- no parameter change improves one accepted analytical view by violating another.

After acceptance, join the parallel `LandmarkNames` and `Landmarks` outputs by index and update every matching semantic landmark row in `landmarks.json` with its resolved `world: [x,y,z]` coordinate.

- [ ] **Step 4: Save the massing checkpoint**

Update `assumptions.json` with accepted values, confidence, source files, and residuals. Append the slider mutation history and capture paths to `execution-ledger.json`. Capture a fresh `gh_snapshot` and `gh_errors`; require zero errors before enabling detail.

### Task 4: Calibrate the Super-Frame, Envelope, Podium, and Masts

**Files:**

- Modify live values: transfer levels, display-member dimensions, façade spacing, and detail mode
- Modify: `artifacts/bank-of-china-tower/evidence/assumptions.json`
- Modify: `artifacts/bank-of-china-tower/execution-ledger.json`
- Create: structural/envelope captures under `artifacts/bank-of-china-tower/validation/captures/`

**Interfaces:**

- Consumes: accepted massing, generator pin map, and analytical brace-node observations
- Produces: accepted graph-derived primary diagonals, transfer bands, curtain grid, podium, transition glass, roof frame, and twin masts

- [ ] **Step 1: Enable and calibrate the primary super-frame**

Set `DetailMode=1`, wait for a settled solve, inspect `BraceAxes`, `Braces`, and `TransferBands`, and capture four orthographic elevations. Confirm that every exposed transition face has its three boundary members plus a centre median before tuning the vertical-façade X-braces. Adjust `L1`-`L5` so every visible primary diagonal terminates at the corresponding analytical brace node. Adjust `BraceWidth` and `BraceDepth` only after node incidence is correct.

Require nonempty axes/solids, no zero-length axes, monotonic transfer levels below the roof, and major brace-node landmark RMSE at or below 1% in analytical views. If the incidence graph is wrong, update the generator script once from fresh evidence; do not compensate with member thickness.

- [ ] **Step 2: Enable and calibrate envelope-scale detail**

Set `DetailMode=2`. Confirm eight transition/outer glass faces remain present, the curtain grid is clipped to each sector height, the podium contains its base plus three entrance-frame members, and the roof/mast output contains two vertical masts, one crossbar, and two diagonal frame members. Adjust `FloorSpacing`, `MullionSpacing`, and `MastSpacing` to match the visual rhythm in `boc-01.jpg`, `boc-04.jpg`, `boc-05.jpg`, and the analytical elevations.

Treat curtain-grid failures as degradations: retain accepted massing and brace axes, report the affected side, and apply at most one bounded correction. Do not rebuild the definition around façade micro-detail.

- [ ] **Step 3: Complete the analytical checkpoint**

Capture clean Front/Right/Back/Left/Top/Perspective images. Verify silhouette, sector order, structural incidence, podium, roof, and masts against `boc-06.jpg`, `boc-07.jpg`, `boc-08.jpg`, and `e777e6f3ae01c8bdfcb40c111a685022.jpg`. Update accepted parameter evidence and append the checkpoint to the execution ledger.

### Task 5: Fit Photographic Cameras and Run the Nine-Source Audit

**Files:**

- Create: `artifacts/bank-of-china-tower/validation/cameras.json`
- Create: `artifacts/bank-of-china-tower/validation/captures/*.png`
- Create: `artifacts/bank-of-china-tower/validation/overlays/*.png`
- Create: `artifacts/bank-of-china-tower/validation/report.md`
- Modify: `artifacts/bank-of-china-tower/execution-ledger.json`

**Interfaces:**

- Consumes: accepted Grasshopper geometry and semantic 2D/3D landmarks
- Produces: saved Rhino cameras, normalized residuals, one comparison artifact per source image, and the nine-source acceptance report

- [ ] **Step 1: Fit one camera for each photographic source**

For each of `boc-01.jpg` through `boc-05.jpg`, write the current numeric candidate to `validation/camera-candidate.json`, use `rhino_execute` to apply it, then save the accepted result with `rhino_views_save` as `BOC_REF_01` through `BOC_REF_05`. The candidate file has this exact shape:

```json
{
  "source": "boc-01.jpg",
  "location": [220.0, -260.0, 120.0],
  "target": [0.0, 0.0, 150.0],
  "lens_mm": 50.0
}
```

The camera-setting script must use the verified RhinoCommon surface and read all changing values from that file:

```python
import Rhino
import json
from Rhino.Geometry import Point3d, Vector3d

path = r"C:\Users\aryan\source\repos\Rook\artifacts\bank-of-china-tower\validation\camera-candidate.json"
with open(path, "r") as stream:
    candidate = json.load(stream)

view = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
vp = view.ActiveViewport
location = Point3d(*candidate["location"])
target = Point3d(*candidate["target"])
lens = float(candidate["lens_mm"])
vp.ChangeToPerspectiveProjection(True, lens)
vp.Camera35mmLensLength = lens
vp.CameraUp = Vector3d.ZAxis
vp.SetCameraLocation(location, False)
vp.SetCameraDirection(target - location, True)
view.Redraw()
```

Begin each source with target `(0,0,150)`, a 50 mm lens, and an orbit direction inferred from the visible façades; the example location is only the `boc-01.jpg` first candidate. Adjust azimuth/elevation first, then lens/distance, then target offset/crop. Geometry remains fixed, and every candidate revision is appended to the execution ledger.

- [ ] **Step 2: Measure projected residuals**

After each candidate, project the named world landmarks to normalized viewport coordinates with:

```python
import Rhino
import json
from Rhino.Geometry import Point3d

path = r"C:\Users\aryan\source\repos\Rook\artifacts\bank-of-china-tower\validation\landmarks.json"
with open(path, "r") as stream:
    landmark_document = json.load(stream)

source_name = "boc-01.jpg"
vp = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView.ActiveViewport
size = vp.Size
rows = [row for row in landmark_document["observations"]
        if row["source"] == source_name and "world" in row]
for row in rows:
    point = Point3d(*row["world"])
    pixel = vp.WorldToClient(point)
    print("{} {:.9f} {:.9f}".format(
        row["name"],
        pixel.X / float(size.Width),
        pixel.Y / float(size.Height)))
```

Set `source_name` to the current photograph before execution. Compute normalized Euclidean RMSE against the source observations and record camera location, target, lens, per-landmark residuals, and aggregate RMSE in `cameras.json`.

After persisting the printed projections as `projected_u` and `projected_v`, run:

```powershell
python artifacts/bank-of-china-tower/validation/score_landmarks.py artifacts/bank-of-china-tower/validation/landmarks.json boc-01.jpg
```

Repeat with the current photograph filename.

Accept each photographic camera only at or below 2% image-diagonal RMSE. If a camera cannot pass because of cropping or perspective correction, record the irreducible residual and affected landmarks; do not deform accepted geometry solely for that image.

- [ ] **Step 3: Capture and compare all nine sources**

Restore each accepted named photo view and capture at the source image's native aspect ratio and dimensions. Capture the necessary standard orthographic/axonometric views for the four analytical files. Produce one side-by-side or half-opacity comparison artifact per source file; composite sheets may contain multiple model captures in their comparison artifact.

The audit passes only when all analytical sources satisfy the 1% threshold, all feasible photographic cameras satisfy the 2% threshold, every primary diagonal has correct visible incidence, and every exception has an explicit confidence/provenance entry.

- [ ] **Step 4: Write the validation report**

`validation/report.md` must contain:

- accepted parameter values and confidence;
- one row per source image with view/camera name, landmark count, RMSE, and pass/exception;
- all remaining low-confidence assumptions;
- known non-goals and omitted details;
- capture and overlay paths; and
- a clear verdict: `accepted`, `accepted_with_documented_exceptions`, or `rejected`.

Do not proceed to bake on a `rejected` verdict.

### Task 6: Bake, Layer, Save, and Record the Training Episode

**Files:**

- Create: `artifacts/bank-of-china-tower/BankOfChinaTower.3dm`
- Create or save: `artifacts/bank-of-china-tower/BankOfChinaTower.gh`
- Modify: `artifacts/bank-of-china-tower/execution-ledger.json`
- Verify: every artifact and report from Tasks 1-5

**Interfaces:**

- Consumes: accepted generator outputs, output-index map, final snapshot epoch, and `accepted*` validation verdict
- Produces: layered Rhino geometry, durable editable Grasshopper source, saved views, complete evidence, and final handoff

- [ ] **Step 1: Reconfirm the final live state**

Run `gh_status`, `gh_snapshot`, `gh_errors`, and `gh_inspect_output` for all eleven outputs. Require the exact accepted slider values, zero unresolved errors, four massing bodies, eight glass faces, nonempty structure/envelope outputs, four podium/entrance members, five roof/mast members, equal nonzero landmark/name counts containing all audited semantic names, and diagnostics matching the accepted report.

- [ ] **Step 2: Create final Rhino layers and bake explicit outputs**

Create the eight `BOC::*` layers with `rhino_layer_create_batch`. Invoke `gh_bake_output` once per bakeable output so each call has the matching parent `layerName`, explicit generator `instanceGuid`, output name/index, `createSublayers=true`, and `clearExisting=true`. Bake `Massing`, `Glass`, `Braces`, `TransferBands`, `CurtainGrid`, `Podium`, `Masts`, and `Landmarks` to their matching parent layers. Do not use `bakeAll`; `LandmarkNames` and `Diagnostics` are not geometry.

Inspect every bake response, record baked IDs and deterministic sublayers, and verify that no baseline Rhino object was deleted or moved.

- [ ] **Step 3: Apply restrained display materials**

Use `rhino_material_ops` and layer/object assignments to give glass a desaturated blue-gray transparent material, structure/podium a light neutral metal/concrete material, and validation landmarks a conspicuous review color. Materials support reading the geometry; they are not used to hide silhouette or topology errors.

- [ ] **Step 4: Save both deliverables**

Save the Rhino document with:

```json
{
  "action": "save",
  "path": "C:/Users/aryan/source/repos/Rook/artifacts/bank-of-china-tower/BankOfChinaTower.3dm"
}
```

Save the active Grasshopper document to `C:/Users/aryan/source/repos/Rook/artifacts/bank-of-china-tower/BankOfChinaTower.gh` through a verified host-supported path. If the admitted Rook surface exposes no safe save operation, ask the user for the single explicit **Grasshopper > File > Save As** action, then verify the file exists and is nonempty before continuing.

- [ ] **Step 5: Verify durability and episode completeness**

Confirm the `.3dm` and `.gh` files exist and are nonempty. Re-open only if doing so will not disturb unsaved user state; otherwise validate through save receipts and filesystem metadata. Confirm all nine source comparison artifacts, camera records, assumptions, report, capture paths, created IDs, and accepted parameter mutations are present.

Append a final `training_episode` entry to `execution-ledger.json` containing source hashes, initial seeds, ordered parameter mutations, rejected/accepted checkpoints, final parameters, camera residuals, Grasshopper component/pin contract, baked object IDs, and deliverable paths. This record is observational training data; it does not authorize model training or upload.

- [ ] **Step 6: Final handoff**

Report the accepted fidelity verdict, final parameter summary, saved `.3dm`/`.gh` paths, validation report path, source-by-source residual table, documented exceptions, and whether the one manual Grasshopper Save As action was required. Do not claim construction accuracy or remove the execution evidence.
