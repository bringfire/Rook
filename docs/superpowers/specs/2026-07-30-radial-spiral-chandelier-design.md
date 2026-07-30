# Radial Spiral Chandelier Design

**Goal:** Replace the circular phyllotaxis placement field in `Chandelier_Circular_Droop-02.gh` with an evenly spaced radial grid that reinforces a spiral through ring phase and fin orientation while preserving the current fin geometry, mesh-normal correction, footprint, and center droop.

## Live Context

- Rhino document: `VIP Check-in lounge Chandelier.3dm`, millimeters.
- Grasshopper document: `Chandelier_Circular_Droop-02.gh`.
- Driver surface: 5,900 mm trimmed diameter, centered at approximately `(-68174.4566, -5175.3158, 13100.0003)`.
- Current field radius: approximately 2,837.9 mm from `Fill = 0.962`.
- Existing placement component: `CircularPhyllotaxis`, instance `afddfe28-88bc-4ef2-83f0-c6c64adead3c`.
- Existing fin component: `ChandelierSmoothLayersCircular`, instance `d84ee26c-7472-449b-9982-55bca2dd3254`.
- The saved phyllotaxis file is the rollback point for this in-place iteration.

## Chosen Approach

Use adaptive concentric rings. Radial spacing is constant, and the point count on each ring is proportional to its circumference. This prioritizes a consistent visual density over continuous point-to-point spiral arms.

The spiral is reinforced in two coordinated ways:

1. Each successive ring advances by a fraction of that ring's angular bay.
2. Every fin plane rotates from the local radial direction toward the local tangent in the same handedness.

Fixed spokes were rejected because their tangential gaps grow toward the perimeter. Relaxed packing was rejected because it weakens the legibility of the radial grid and adds unnecessary solver complexity.

## Components

| Component | Grasshopper GUID | Change |
|---|---|---|
| Python 3 Script | `719467e6-7cf5-4848-99b0-c5dd57e5442c` | Update and rename to `CircularRadialSpiral` |
| C# Script | `b6ba1144-02d6-4a2d-b53c-ec62e290eeb7` | Keep `ChandelierSmoothLayersCircular` unchanged |
| Number Sliders | Existing instances | Rename and recalibrate the four placement controls |
| Custom Preview | Existing instance | Preserve current fin and material connections |

No new Grasshopper component type or external plugin is required.

## Placement Inputs

| Input | Type | Default | Range | Purpose |
|---|---|---:|---:|---|
| `surface` | Surface/Brep, item | Existing reference | n/a | Supplies center, plane, normal, and trimmed outer radius |
| `rings` | Integer, item | 11 | 3–20 | Number of concentric rings outside the center point |
| `fill` | Number, item | 0.962 | 0.50–1.00 | Ratio of field radius to trimmed surface radius |
| `phase_step` | Number, item | 0.35 | -1.00–1.00 | Fraction of each ring's angular bay added to the accumulated phase |
| `fin_spin` | Number, item | 55 degrees | -90–90 degrees | Rotation from radial toward tangential fin orientation |

The existing placement sliders are repurposed as follows:

- `Count` becomes `Rings`.
- `Fill` remains `Fill`.
- `Angle` becomes `PhaseStep`.
- `Arms` becomes `FinSpin`.

Positive `phase_step` and `fin_spin` produce the same handedness. Negative values reverse the spin.

## Radial Grid Algorithm

1. Coerce the referenced surface to a valid planar Brep.
2. Derive the surface plane and centroid, flip the normal upward when necessary, and measure the trimmed circular boundary radius.
3. Compute `field_radius = outer_radius * clamp(fill, 0.05, 1.0)`.
4. Clamp `rings` to at least one and compute `ring_pitch = field_radius / rings`.
5. Emit one point at the exact center in branch `{0}`. Its plane uses the driver plane's X axis.
6. For ring index `k = 1..rings`:
   - Set `radius = k * ring_pitch`.
   - Set `point_count = max(6, round(2 * pi * radius / ring_pitch))`. Because `radius / ring_pitch = k`, this is equivalent to `max(6, round(2 * pi * k))`.
   - Set `bay = 2 * pi / point_count`.
   - Advance the accumulated ring phase by `phase_step * bay`.
   - Place points at `phase + j * bay` for `j = 0..point_count-1`.
   - Construct a radial unit vector from the center to each point and a tangent vector from the surface normal.
   - Rotate the radial vector toward the tangent by `fin_spin` and use the result as the placement plane X axis.
   - Store the ring's points and planes in branch `{k}`.
7. Preserve the existing `Center`, `OuterRadius`, `FieldRadius`, and `Boundary` outputs.

With 11 rings, the expected ring counts are `6, 13, 19, 25, 31, 38, 44, 50, 57, 63, 69`, plus one center point, for 416 fins total.

At the current field radius, the radial pitch is approximately 258 mm. Circumferential spacing remains approximately 249–270 mm across all rings, keeping the spacing variation within about five percent.

## Fin and Droop Behavior

`ChandelierSmoothLayersCircular` remains unchanged:

- Droop is measured from the supplied surface center.
- The cosine-squared falloff and current layer calculation remain intact.
- Current fin settings remain: two panels, two minimum layers, three extra layers, 380 mm nominal height, 46.874 mm gap, 74.187 mm half-length, and 13 mm half-thickness.
- Meshes remain closed, unwelded at 30-degree creases, recomputed with hard-edge normals, and flipped when solid orientation is inward.

The radial placement tree passes through the item-access fin script without changing the branch structure.

## Wiring

1. Existing referenced surface -> `CircularRadialSpiral.surface`
2. `Rings` slider -> `CircularRadialSpiral.rings`
3. `Fill` slider -> `CircularRadialSpiral.fill`
4. `PhaseStep` slider -> `CircularRadialSpiral.phase_step`
5. `FinSpin` slider -> `CircularRadialSpiral.fin_spin`
6. `CircularRadialSpiral.Planes` -> `ChandelierSmoothLayersCircular.planes`
7. `CircularRadialSpiral.Center` -> `ChandelierSmoothLayersCircular.center`
8. `CircularRadialSpiral.FieldRadius` -> `ChandelierSmoothLayersCircular.depth_radius`
9. Existing fin sliders remain connected to the remaining fin inputs.
10. `ChandelierSmoothLayersCircular.Fins` remains connected to the existing Custom Preview.

## Constraints and Error Handling

- The surface must be planar and have a positive trimmed radius.
- Angles are entered in degrees and converted to radians exactly once.
- The center point is emitted only once; ring generation begins at one full radial pitch.
- Ring branches must remain ordered from center to perimeter.
- `point_count` is never allowed below six.
- A zero `phase_step` yields stagger-free concentric rings.
- A zero `fin_spin` yields radial fins; 90 degrees yields circumferential fins.
- Invalid surface input stops the placement script with a clear runtime message and no stale geometry.
- The imported `ChandelierSmoothLayers-02` reference component remains untouched.

## Canvas Layout

- Modify the existing placement branch in place rather than adding a parallel third generator.
- Rename the existing group to `Circular Radial Spiral — First Pass`.
- Preserve the current placement and fin component positions.
- Keep the imported reference script outside the working group.

## Verification

1. Wait for Grasshopper to reach an enabled, ready `PostProcess` solve state.
2. Confirm zero canvas errors and warnings.
3. Confirm `Points` and `Planes` each contain 416 items across 12 branches.
4. Confirm branch `{0}` contains exactly one center item.
5. Confirm ring branches contain `6, 13, 19, 25, 31, 38, 44, 50, 57, 63, 69` items.
6. Confirm `OuterRadius` remains approximately 2,950 mm and `FieldRadius` remains approximately 2,837.9 mm.
7. Confirm the fin output contains 416 closed meshes across the same 12 branches.
8. Confirm the existing Custom Preview still has the radial fin output connected.
9. Inspect the shaded viewport for hard fin edges, outward-facing normals, even center-to-edge spacing, and a coherent shared spin direction.

## Success Criteria

- The field reads first as an evenly spaced radial grid, without large outer gaps or a crowded inner ring.
- One fin anchors the exact center and preserves the deepest droop.
- Progressive ring phase creates a legible rotational drift without destroying ring structure.
- Fin orientation reinforces the same handedness as the ring phase.
- Density remains close to the current 414-fin version.
- Fin geometry, droop, corrected mesh shading, footprint, and material preview remain unchanged.
- Grasshopper reports no runtime errors or warnings.

## Rollback

The saved phyllotaxis definition remains the primary rollback. Within this copy, reverting requires restoring only the placement script, its four slider names/ranges/values, and the group nickname; the fin component and preview wiring are not changed.
