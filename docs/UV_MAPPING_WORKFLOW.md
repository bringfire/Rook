# Renderer-independent UV mapping

## Purpose and status

This workflow turns physical texture size and object direction into native Rhino
mapping channels. Materials and render settings remain separate. It is intended
for wood grain, stone, tile, fabric, and other repeating materials where an
object's size should not change the apparent size of the texture.

The first increment evolves the ideas in the local prototype
`C:/Users/aryan/Documents/RhinoScripts/UVBoxMapping_02.py`. The prototype itself
has not been replaced. The implementation lives in Rook's native
`POST /material/uv-box` route, exposed as `rhino_apply_uv_box_mapping` in MCP.

Development status, 2026-09-18: built and tested in an isolated Rhino 8 process.
Native Debug build passed with MSVC 14.44.35207; 24 live mapping tests and 23
MCP profile tests passed. The latter emitted 11 existing DSPy deprecation warnings.
The running user sessions still use the installed build. Deployment of the
native plug-in and restart/reload of the MCP server are separate steps.

## Contract

| Input | Meaning |
| --- | --- |
| `ids` | Nonempty list of Brep, extrusion, or mesh object IDs. Block instances are not traversed. |
| `scale` | Positive document units per texture repeat, uniform on all axes. Omit for one meter converted to document units. |
| `repeat` | Optional positive `[x,y,z]` repeat lengths in document units along the mapping frame. Overrides `scale`. |
| `channel` | Integer from 1 through 2147483647, excluding Rhino's reserved channel; defaults to 1. Only this channel is replaced. |
| `frame.x_axis`, `frame.y_axis` | Supply both to choose direction explicitly. Must be nonzero and perpendicular; they are normalized. Cross product determines Z. |
| `frame.origin` | Optional pattern anchor in world coordinates. If omitted, use the object's bounds center measured in the chosen frame. |
| `documentSerialNumber` | Native HTTP document selector; tests use this to target a private headless document. |

Numbers must be finite. Unitless/custom-unit documents require explicit `scale`
or `repeat`. Repeat lengths are distances, not repeat counts. A two-meter-long
object with a half-meter repeat spans four repeats along that direction.

Example native request for grain along world Y, a two-meter repeat on X/Y of
the mapping frame, and a shared anchor in a millimeter document:

```json
{
  "ids": ["OBJECT-GUID"],
  "repeat": [2000, 2000, 2000],
  "channel": 1,
  "frame": {
    "origin": [0, 0, 0],
    "x_axis": [0, 1, 0],
    "y_axis": [-1, 0, 0]
  }
}
```

For per-object automatic direction and a 500 mm repeat, use `scale: 500` and
omit `frame`. To align a pattern across several objects, supply the same axes,
origin, repeat, and channel for all of them. Origin alone changes the anchor
while retaining each object's automatic XY direction.

## Implementation and lessons

- Build `ON_TextureMapping` with `SetBoxMapping`, then assign a mapping-table
  entry through object attributes on Rhino's main thread. No command macro,
  selection changes, or prompts are needed for box mapping.
- Use Rhino's system renderer mapping ID. Despite its name,
  `RhinoApp().RhinoRenderPlugInUUID()` returns this fixed system ID, not the
  currently selected V-Ray/other renderer ID (verified in the installed SDK).
- Read the channel back after the attribute mutation. Count an object as mapped
  only when the stored mapping ID matches. Reacquire document objects after
  mutations instead of relying on old object pointers.
- Validate channel range before converting JSON integers to native `int`; an
  oversized integer must never wrap around to another channel. Pass the SDK's
  quiet flag during assignment so failures cannot open warning dialogs.
- Preserve unrelated channels. Do not clear channels 1–8 as the prototype did.
  Do not overwrite a mesh's channel-1 texture coordinates when assigning a
  different channel merely to populate a display cache.
- Use `ON::UnitScale` instead of a handwritten unit-enum table. The prototype's
  meter/yard enum assumptions were incorrect.
- Compute bounds by transforming the geometry into the chosen frame, not by
  rotating its world-axis bounding box. Report dimensions and coverage in the
  actual mapping frame, including explicit tilted frames.
- Automatic direction considers linear Brep edges (also via extrusion Breps)
  or mesh boundary/crease edges projected onto XY. Coplanar internal mesh edges
  are ignored so triangulation does not dictate the grain direction. Direction
  groups within two degrees compete by total projected length; opposite edge
  directions are treated as equivalent. Insufficient evidence falls back to
  world XY. This is a heuristic, not semantic recognition of grain.

The response includes `mapped_count`, `repeat`, `channel`, and per-object
results. Successful entries report dimensions, mapping origin/axes,
`orientation_source`, and formatted coverage. Missing or unsupported objects
produce per-object errors; a successful HTTP envelope does not mean every
object was mapped. Uniform repeats also return `scale`; rectangular repeats
return `scale: null`. `orientation_angle` is an XY heading, not a full 3D
orientation; use the axis vectors for tilted frames.

## Practical material workflow

1. Inspect object types, document units, existing channels, and material texture
   channel choices. Avoid automatically remapping imported assets with authored
   UVs, particularly vegetation and layered proxy materials.
2. Establish the image's real-world repeat dimensions. Set a renderer-neutral
   box frame/repeat appropriate to the object's fabrication direction.
3. Check with a numbered, directional checker and then the intended material.
   A stored mapping can be correct while the material uses another channel,
   triplanar projection, or an additional texture transform.
4. For continuity across parts, use a shared frame and anchor. For independent
   parts, use per-object centers and direction overrides where needed.
5. Inspect seams, opposite-face orientation, and stretching. Box projection is
   not a substitute for unwrap on complex curved geometry.

## Verification and boundaries

Live tests are in `mcp_server/tests/test_uv_box_mapping_live.py`. They require
an explicitly selected runtime port; each test creates and disposes a private
headless document. No active user document, renderer, or selection is changed.

```powershell
$env:ROOK_UV_TEST_PORT = 'YOUR_TEST_RUNTIME_PORT'
& .\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_uv_box_mapping_live.py -q
```

Tests inspect stored RhinoCommon mappings rather than trusting HTTP success.
Coverage includes rotated Breps/meshes, preserved channels, repeated assignment,
explicit tilted frames, rectangular repeats, millimeter/meter/foot/yard units,
unitless documents, invalid input, missing objects, and the shared planar
assignment helper. The old build's invalid-channel request was observed to
succeed incorrectly before implementation.

These checks establish mapping data correctness; they do not establish visual
parity across renderers, checker-render quality, save/reopen behavior, or
performance on large scenes. Those remain acceptance checks before production
deployment. Automatic orientation is XY only; use explicit axes for tilted
geometry. Curves, points, blocks, unwrap, seam editing, random offsets, and
automatic material-size metadata are outside this increment.

Planar mapping already uses direct assignment and shares the tested helper.
Cylinder and sphere routes still use legacy interactive command code; do not
treat them as equivalent to the corrected box route. Extend them by constructing
native mappings with explicit frames and dimensions, then add mapping-readback
tests before exposing them as reliable automation.

For V-Ray-specific material/proxy issues, see [VRAY_WORKFLOW.md](VRAY_WORKFLOW.md).
