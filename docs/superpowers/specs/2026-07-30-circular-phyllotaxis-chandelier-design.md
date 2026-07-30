# Circular Phyllotaxis Chandelier Design

**Goal:** Build a non-destructive Grasshopper comparison branch that distributes approximately 300 fin stacks in a circular phyllotaxis field while preserving the existing chandelier's smooth central droop.

## Live Context

- Rhino document: `VIP Check-in lounge Chandelier.3dm`
- Grasshopper document: `Chandelier_Circular_Droop-01.gh`
- Referenced circular driver surface: approximately 7,080 mm across, centered at approximately `(-68174.4566, -5175.3158, 13100.0003)` in Rhino world coordinates.
- Selected Rhino reference block: `small droppy check-in lounge`.
- Reference block envelope: approximately 5,629 x 5,629 x 2,015 mm.
- Reference block contents: 308 closed mesh fin stacks.
- Sample reference stack: 16 vertices and 12 faces, consistent with two closed fin panels.
- The current `Phyllotaxis` script generates 3,000 points around world XY and does not use the circular surface.
- The current `ChandelierSmoothLayers` script measures droop from world origin rather than from a supplied driver center.

## Chosen Approach

Create a parallel, non-destructive branch by duplicating the two relevant script components. Keep the existing grid field, experimental Phyllotaxis script, and existing fin generator unchanged for A/B comparison.

The new placement component will derive a local plane, center, and radius from the referenced circular surface. It will generate a bounded phyllotaxis distribution directly in that plane. The new fin component will retain the existing mesh construction but measure its cosine-squared droop from the supplied surface center.

The referenced surface remains an explicit input for this first pass because it preserves the exact live position and radius with the least ambiguity. A later iteration may internalize or procedurally generate the circle.

## Alternatives Considered

1. Edit the existing scripts in place. This produces a cleaner canvas but removes immediate comparison with the grid and earlier Phyllotaxis experiments.
2. Combine placement, droop, and mesh generation into one script. This reduces component count but couples independent concerns and makes tuning and diagnosis harder.

## Components

### CircularPhyllotaxis

Duplicate the existing RhinoCode Python 3 script component and give it the nickname `CircularPhyllotaxis`.

Inputs:

| Input | Type/access | Initial value | Purpose |
|---|---|---:|---|
| `surface` | Surface, item | Existing referenced circular surface | Supplies center, local plane, and outer radius |
| `count` | Integer, item | 308 | Number of fin-stack placement planes |
| `fill` | Number, item | 0.80 | Ratio of field radius to surface outer radius |
| `angle` | Number, item | 137.508 degrees | Phyllotaxis divergence angle |
| `arms` | Integer, item | 13 | Step used to organize points into arms and calculate arm tangents |

Outputs:

| Output | Structure | Purpose |
|---|---|---|
| `Points` | Tree with `arms` branches | Placement points for inspection |
| `Planes` | Tree matching `Points` | Tangent-oriented placement planes |
| `Center` | Item | Surface center used by the droop calculation |
| `OuterRadius` | Item | Derived surface radius |
| `FieldRadius` | Item | `OuterRadius * fill` |
| `Boundary` | Item | Circular boundary preview |

Behavior:

1. Coerce the input to a valid Brep or surface and reject null, invalid, or non-planar geometry with a clear runtime message.
2. Derive the planar face frame and area centroid. Use the circular boundary to derive the outer radius; for this first horizontal circular surface, a planar bounding extent is an acceptable fallback.
3. Set `fieldRadius = outerRadius * clamp(fill, 0.05, 1.0)`.
4. For index `i` in `[0, count - 1]`, use normalized radius `fieldRadius * sqrt(i / max(1, count - 1))` and angle `i * radians(angle)`.
5. Construct points in the surface's local plane, not around world origin.
6. Group indices by the `arms` step and orient each plane's X axis along the local tangent to its arm. Use the surface normal for the plane Z axis.
7. Preserve exactly `count` points and planes.

Random rotation, probability filtering, reverse-arm outputs, and seeded variation are intentionally excluded from the first pass because the current definition does not consume them and they are not needed to validate the core composition.

### ChandelierSmoothLayersCircular

Duplicate the existing RhinoCode C# script component and give it the nickname `ChandelierSmoothLayersCircular`.

Retain the existing inputs, add `center`, and change the source of the existing `depth_radius` input:

| Input | Type/access | Source | Purpose |
|---|---|---|---|
| `center` | Point, item | `CircularPhyllotaxis.Center` | Center for radial droop distance |
| `depth_radius` | Number, item | `CircularPhyllotaxis.FieldRadius` | Radius at which additional central droop reaches zero |

Initial fin settings:

| Setting | Value |
|---|---:|
| `num_layers` | 2 |
| `min_layers` | 2 |
| `extra_layers` | 3 |
| `fin_height` | 380 mm |
| `gap` | 38 mm |
| `fin_length` | 110 mm half-length |
| `half_thickness` | 13 mm |

These values predict a center stack height of approximately 2,052 mm and an outer stack height of approximately 798 mm. The center height closely matches the selected reference block's approximately 2,015 mm overall depth. The fin length and thickness remain at their current values because a sampled reference mesh supports that scale; they should not be reduced by another two-thirds.

Droop behavior:

1. Compute radial distance in the driver plane from `center` to each placement-plane origin.
2. Preserve the existing cosine-squared falloff inside `depth_radius`.
3. Reach `min_layers` at or beyond `depth_radius` and `min_layers + extra_layers` at the center.
4. Preserve the existing alternating X/Y orientation of panels within each stack.
5. Continue producing one closed mesh per placement plane.

## Wiring

1. Referenced Surface -> `CircularPhyllotaxis.surface`
2. New `Count` slider -> `CircularPhyllotaxis.count`
3. New `Fill` slider -> `CircularPhyllotaxis.fill`
4. Existing or duplicated `Angle` slider -> `CircularPhyllotaxis.angle`
5. Existing or duplicated `Arms` slider -> `CircularPhyllotaxis.arms`
6. `CircularPhyllotaxis.Planes` -> `ChandelierSmoothLayersCircular.planes`
7. `CircularPhyllotaxis.Center` -> `ChandelierSmoothLayersCircular.center`
8. `CircularPhyllotaxis.FieldRadius` -> `ChandelierSmoothLayersCircular.depth_radius`
9. Dedicated duplicated sliders provide the fin settings listed above.
10. `ChandelierSmoothLayersCircular.Fins` -> the existing mesh preview parameter or a duplicated preview branch, without disconnecting the current source until the new output is verified.

## Layout

- Place the new input controls immediately left of `CircularPhyllotaxis`.
- Place `CircularPhyllotaxis` near the existing experimental Phyllotaxis component for comparison.
- Place `ChandelierSmoothLayersCircular` to its right.
- Group the new branch as `Circular Phyllotaxis — First Pass` with a distinct color.
- Preserve all existing components and wires outside the new branch.

## Constraints and Error Handling

- Do not assume the surface is centered at world origin.
- Angles supplied in degrees must be converted to radians once.
- Clamp `count` to at least 2 and `arms` to `[1, count]`.
- Clamp `fill` to `(0, 1]`.
- Stop cleanly with a runtime message if the surface is null, invalid, or not planar.
- Use the same tree structure for `Points` and `Planes` so Grasshopper data matching remains predictable.
- Avoid adding external dependencies or changing project source files; this work is confined to the live Grasshopper document.

## Verification

After each script and wiring batch:

1. Wait for Grasshopper to reach a ready, post-process solve state.
2. Inspect canvas errors and warnings.
3. Confirm `CircularPhyllotaxis` emits exactly 308 points and 308 planes.
4. Confirm all points lie within approximately 80% of the surface radius and are centered on the referenced surface.
5. Confirm the fin component emits exactly 308 closed meshes.
6. Confirm the projected footprint is approximately 5.6 m across.
7. Confirm the deepest central stack is approximately 2.05 m and the droop decreases smoothly toward the perimeter.
8. Compare the new branch visually against the selected Rhino reference block.

## Rollback

The first pass is additive. If it fails or is visually unsuitable, delete only the newly created components and group. The existing grid branch, earlier Phyllotaxis experiment, referenced surface, and original fin generator remain unchanged.

## Success Criteria

- A live circular phyllotaxis chandelier preview appears at the referenced surface location.
- The branch contains approximately 300 fin stacks, specifically 308 at the initial setting.
- The field footprint is approximately 5.6 m within the 7.08 m driver surface.
- The droop is centered on the surface rather than world origin and reaches approximately 2.05 m at the center.
- The fin scale visually agrees with the selected reference block.
- Grasshopper reports no runtime errors.
