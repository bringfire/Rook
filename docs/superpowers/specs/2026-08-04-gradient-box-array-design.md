# Gradient Box Array Grasshopper Design

## Goal

Create a parametric Grasshopper definition that generates a rectangular grid of solid boxes whose heights increase linearly along the grid diagonal.

## Live Target and Scope

- Target the active, unnamed Grasshopper document, which was empty at design time.
- Create only execution-owned components; do not bake geometry into Rhino.
- Use one C# Script component for the geometry logic and six connected number sliders for user control.
- Group and label the created components without modifying unrelated canvas state.

## Inputs and Defaults

| Input | Slider range | Default | Behavior |
| --- | ---: | ---: | --- |
| X Count | 1-50, integer | 10 | Number of boxes along world X |
| Y Count | 1-50, integer | 10 | Number of boxes along world Y |
| Box Size | 0.1-5 m | 1 m | Width and depth of each square box |
| Gap | 0-5 m | 0.2 m | Clear spacing between neighboring boxes |
| Min Height | 0.01-10 m | 0.25 m | Height at grid coordinate `(0, 0)` |
| Max Height | 0.01-20 m | 5 m | Height at grid coordinate `(X Count - 1, Y Count - 1)` |

The C# component will clamp counts to at least one, dimensions to positive values, and gap to a nonnegative value. If the minimum exceeds the maximum, the requested values remain valid and produce a descending gradient.

## Geometry and Data Flow

For grid indices `i` and `j`, the box base corner is:

`(i * (Box Size + Gap), j * (Box Size + Gap), 0)`

The normalized diagonal parameter is:

`t = (i + j) / ((X Count - 1) + (Y Count - 1))`

When the denominator is zero, `t` is zero. Height is the linear interpolation `Min Height + t * (Max Height - Min Height)`. Each item is a closed axis-aligned Brep extending upward from the world XY plane.

## Outputs

- `Boxes`: flat list of closed box Breps in row-major order.
- `Heights`: flat list of corresponding numeric heights in the same order.

## Error Handling

The script will avoid invalid intervals and division by zero. Slider ranges provide the normal operating boundary, while script-side clamping protects the component if values are supplied from another source later.

## Verification

After creation, capture a fresh Grasshopper snapshot and verify:

- six sliders are connected to the intended C# inputs;
- the component compiles with no errors or warnings;
- the default output contains 100 Breps and 100 heights;
- preview values span 0.25 m to 5 m;
- the definition remains editable through all six sliders.
