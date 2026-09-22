# V-Ray for Rhino through Rook: workflow and field notes

Last updated: 2026-09-18. First verified against `Vray_Testbed.3dm`, Rhino 8,
V-Ray for Rhino 7.40.02 (core 7.40.03), and an NVIDIA RTX 4070 Laptop GPU.

This is a practical record of live scene work, not a specification for a new
Rook integration. It records what worked, what failed, and what to verify next.
Plugin names, parameter schemas, import behavior, and device IDs can vary by
installation. Inspect the active scene before applying the examples.

## The main lesson

Validate one complete asset before repeating the workflow: import, scale,
place, bind materials, check texture paths, and render its transparency.
An import command returning successfully is not evidence that its materials
are complete. A plausible viewport color is not evidence of a correct shader.

## Demonstrated access

| Area | Verified in this session | Limits of the evidence |
| --- | --- | --- |
| Live scene | Execute Rhino Python through Rook and obtain the V-Ray plugin object | Bind to the intended Rhino document first |
| Materials | Assign Rhino render materials; inspect V-Ray nodes and parameters; repair textures and shader connections | Generic Cosmos import conversion is not reliable for every asset |
| Cosmos | Browse the local Cosmos service, download assets, import standard materials, and use downloaded proxy geometry | Direct Cosmos model import rejected the tested lavender; no universal importer established |
| Geometry | Inspect bounds, scale and place proxies, and set UV mapping through RhinoCommon | Proxy preview meshes differ from render geometry |
| Environment | Set a Cosmos HDRI bitmap and rotation, disable the document sun, and enable camera exposure controls | This was one daylight setup |
| Camera | Set camera location, target, and lens through Rhino scripting | Composition still needs visual inspection |
| Rendering | Select an RTX device, start production rendering, set resolution/output, and obtain RGB, denoiser, and effects-result images | No performance benchmark or optimal-quality claim |

The installed AppSDK at `C:/Program Files/Chaos/V-Ray/AppSDK` was available,
but the successful renders used the V-Ray plugin inside Rhino. Standalone
AppSDK rendering and transfer of a complete Rhino scene were not demonstrated.

## Recommended sequence

1. **Identify the target.** Discover the active Rook/Rhino instance. Check its
   document path, renderer, units, object count, and bounds. Do not reuse an old
   PID, port, object GUID, or the historical assumption of port 9876.
2. **Record the baseline.** Record existing geometry, material assignments,
   camera, and environment. Work within the requested scene; do not rescale the
   user's original objects to accommodate an imported prop.
3. **Prepare one representative asset.** Choose an asset with the properties
   that matter. For vegetation, include textured leaves and opacity cutouts.
4. **Complete its download.** Wait for files and Cosmos status to indicate
   completion before import. Avoid overlapping download/update/import commands.
5. **Import and immediately inspect bounds.** Normalize the new prop's size
   relative to the existing scene, then place it on the ground.
6. **Validate its complete material graph.** Check object assignment, proxy
   slots, material IDs, shader texture inputs, bitmap paths, and opacity.
7. **Render a small proof.** Check leaves, flowers, cutouts, reflections, scale,
   and placement. A shaded/Arctic/Rendered viewport is insufficient evidence.
8. **Repeat the validated process.** Add the remaining assets and materials.
9. **Compose and light.** Set the camera, environment, exposure, and output.
10. **Render and inspect the output.** Confirm a newly written image and a
    completed render, then inspect that image. Report any remaining defects.
11. **Record persistence.** State where images and supporting files were saved
    and whether the Rhino document itself was saved. Saving an image does not
    save the scene.

## Avoid interactive command stalls

The user explicitly identified repeated interactive Rhino prompts as a major
blocker. Prefer direct RhinoCommon and V-Ray APIs. When a command is necessary,
use a verified fully supplied command string and run one operation at a time.

- The Rook UV box-mapping command stalled on interactive Rhino prompts in this
  session. Direct `TextureMapping.CreateBoxMapping` and `SetTextureMapping`
  worked without a command-line prompt.
- An unsupported Cosmos import opened a modal error dialog and blocked Rhino's
  scripting thread. Do not repeatedly queue scripts against a blocked UI.
- Download completion triggered Cosmos update activity. Do not assume that a
  returned download command means it is safe to import immediately.
- A render request returning is not completion evidence. Observe the V-Ray
  Frame Buffer or a newly written output file, and inspect the result.

## V-Ray scripting access

The following reflection pattern was used successfully inside Rhino via
Rook's `rhino_execute`. These are fragments to adapt after inspecting the
current document, not an unattended import script.

```python
import Rhino
import System
from System.Reflection import BindingFlags

def get_prop(obj, name, args=None):
    return obj.GetType().InvokeMember(
        name, BindingFlags.GetProperty, None, obj, args)

def call_method(obj, name, args=None):
    return obj.GetType().InvokeMember(
        name, BindingFlags.InvokeMethod, None, obj, args)

def get_param(plugin, name):
    return get_prop(plugin, "Param", [name])

def set_value(plugin, name, value):
    param = get_param(plugin, name)
    param.GetType().InvokeMember(
        "Value", BindingFlags.SetProperty, None, param, [value])

vray = Rhino.RhinoApp.GetPlugInObject("V-Ray for Rhino")
if vray is None:
    raise RuntimeError("V-Ray plugin interface is unavailable")
scene = get_prop(vray, "Scene")

# Inspect before writing. The plugin path is specific to this scene.
options = get_prop(scene, "Plugin", ["/SettingsOptions"])
for name in get_prop(options, "ParamNames"):
    param = get_param(options, name)
    print(name, get_prop(param, "TypeAsString"), get_prop(param, "Value"))

call_method(scene, "BeginChange")
try:
    set_value(options, "quality_preset", System.Int32(2))
finally:
    call_method(scene, "EndChange")
call_method(vray, "RefreshUI")
```

Use the declared parameter type: integer flags commonly require `System.Int32`,
floating-point values `System.Single`, and actual Boolean parameters
`System.Boolean`. Color and list parameters require appropriately typed arrays.
Inspect array lengths rather than treating RGB and RGBA as interchangeable.
Read values back after changes.

The installed vendor wrappers corroborate this interface and render enums:

- `C:/Program Files/Chaos/V-Ray/V-Ray for Rhinoceros/rh8VRay.py`
- `C:/Program Files/Chaos/V-Ray/V-Ray for Rhinoceros/rhVRay.py`

These local files are useful references when continuing on this machine.

## Cosmos acquisition and proxy fallback

The local Cosmos browser was accessible at `http://127.0.0.1:30305` during the
session. Discover its current endpoint rather than assuming that port persists.

These command forms worked for standard material downloads/imports:

```python
import rhinoscriptsyntax as rs

rs.Command('_vrayCosmos _Download "Exact Asset Name"', True)
# Wait for download completion before issuing the import.
rs.Command('_vrayCosmos _Import "Exact Asset Name"', True)
```

`Lavandula pinnata Sidonie 004` failed through the direct Cosmos import command
with `Unsupported Chaos Cosmos asset type`. A scanned ceramic material also
failed. That does not establish that all vegetation or scanned materials are
unsupported; the cause of that importer rejection remains unresolved.

The successful geometry fallback used downloaded files:

```python
# proxy_path and material_path must be verified, existing local paths.
rs.Command('-_vrayProxyImport "' + proxy_path + '" 0,0,0 _Enter', True)
rs.Command('-_vrayImportMaterial "' + material_path + '"', True)
```

Importing a proxy and its VRMAT separately did not reproduce a complete native
Cosmos import automatically. The material repairs below were necessary.

### Texture paths

Source VRMAT files contained relative texture references. Working copies were
written beside the study artifacts with absolute paths into the downloaded
Cosmos package's `Assets` directory. Original Cosmos files were left intact.

The session resolved references using texture basenames and package-prefixed
filenames. Future work should require an unambiguous match within the intended
package; a same-named texture from another asset is not a valid substitute.
Audit every referenced file. A file-existence audit alone cannot validate the
shader connection or texture interpretation.

## Scale, placement, mapping, and camera

The Rhino document used meters, with test objects tens of meters across. Raw
proxy imports were much larger than the test objects. The plant previews looked
like giant low-detail blobs. They were coarse proxy previews, not the foliage
that V-Ray ultimately rendered.

For this material study the props were sized relative to the existing objects;
they were not converted into a physically true-scale architectural scene.

The direct placement pattern used the proxy bounds and a ground-level anchor:

```python
# obj is the newly imported RhinoObject; height/position are in document units.
bounds = obj.Geometry.GetBoundingBox(True)
source_height = bounds.Max.Z - bounds.Min.Z
if source_height <= 0:
    raise ValueError("Cannot scale an asset with zero height")
anchor = Rhino.Geometry.Point3d(
    bounds.Center.X, bounds.Center.Y, bounds.Min.Z)
target = Rhino.Geometry.Point3d(*position)
xf = (Rhino.Geometry.Transform.Translation(target - anchor)
      * Rhino.Geometry.Transform.Scale(anchor, height / source_height))
new_id = Rhino.RhinoDoc.ActiveDoc.Objects.Transform(obj.Id, xf, True)
# Re-query new_id and verify its resulting bounds.
```

For ordinary textured test objects, this box mapping worked:

```python
interval = Rhino.Geometry.Interval(0, mapping_size)
mapping = Rhino.Render.TextureMapping.CreateBoxMapping(
    Rhino.Geometry.Plane.WorldXY, interval, interval, interval, True)
obj.SetTextureMapping(1, mapping)
```

Do not replace the imported vegetation's UV mapping with a generic box map.
Its leaf/flower atlas and opacity map depend on the asset's original UVs.

The tested camera was:

```python
rs.ViewCameraTarget("Perspective", [115, -190, 108], [18, 15, 15])
rs.ViewCameraLens("Perspective", 48)
```

Those coordinates are specific to this testbed. Compose against current bounds
and visually check the camera rather than copying them to another model.

## Material assignment and the three vegetation failures

Ordinary Rhino object assignment used
`doc.Objects.ModifyRenderMaterial(obj, render_material)`. For proxies, this was
not enough: the V-Ray geometry node had its own enabled material slots.

### 1. Pink/purple fallback colors

The imported plant proxy had `mtls_on = 1`, `ids_list = [0, 1]`, and
`mtls_list = ['', '']`. Its fallback display/render colors were mistaken for
material success. The mirror also initially rendered with a fallback color.

Copying the imported multi-material's actual material references and IDs into
the proxy slots connected the intended shaders:

```python
# Resolve these from the current scene; do not reuse old GUIDs or names.
proxy = call_method(scene, "PluginFromObject", [proxy_guid_string])
multi = get_prop(scene, "Plugin", [multi_material_name])
call_method(scene, "BeginChange")
try:
    for name in ["mtls_list", "ids_list"]:
        set_value(proxy, name, get_prop(get_param(multi, name), "Value"))
finally:
    call_method(scene, "EndChange")
```

The material ID correspondence must be preserved. Do not assume every proxy
uses IDs 0 and 1 or the same ordering.

### 2. Grey plants and mirror

After slot binding, the imported BRDFs exposed empty `diffuse_tex` connections
and default grey `diffuse_color` values. The source VRMAT contained the intended
texture graph. Binding shaders exposed an incomplete conversion rather than
fixing it.

The source used render-level parameters such as `diffuse`, `reflect`, and
`opacity`; the live Rhino interface also exposed controls such as
`diffuse_tex`, `reflect_color`, and `opacity_tex`. Restoring the appropriate
live controls from the source VRMAT recovered textures and mirror reflection.

Important details:

- Verify each destination parameter through `ParamNames` and `TypeAsString`.
- Verify each referenced node exists before connecting it.
- In this import, `@` in source node names became `_`; a second similar asset
  received `#1` suffixes. These are observed names, not a universal naming rule.
- Inspect both front and back shaders of two-sided foliage.
- A broad parameter-copy pass restored 180 controls, but still produced broken
  opacity. Do not present that pass as a proven generic VRMAT converter.

### 3. Leaves and flowers disappeared, leaving stems

The repaired opacity input initially referenced the imported intermediate
conversion chain. That rendered the leaf and flower geometry invisible.
The exact internal conversion defect was not isolated.

The verified workaround was to connect the original opacity bitmap node
directly to `opacity_tex` on both front and back BRDFs for each plant. This
bypassed the problematic imported intermediate chain without removing cutouts
or inventing replacement colors.

Exact names in this session:

| Role | Lavender 004 node |
| --- | --- |
| Front BRDF | `/Leaves_front_mtl_mtl_brdf__7` |
| Back BRDF | `/Leaves_back_mtl_mtl_brdf__9` |
| Original opacity bitmap texture | `/Leaves_op_tex_tex_mono_0` |
| Earlier failing front opacity input | `/Leaves_front_mtl_mtl_brdf__7_opacity_combine` |

Lavender 005 used the corresponding names with `#1` appended. The final change:

```python
# Verified for the two imported lavender graphs, not arbitrary vegetation.
call_method(scene, "BeginChange")
try:
    for suffix in ["", "#1"]:
        for stem in ["/Leaves_front_mtl_mtl_brdf__7",
                     "/Leaves_back_mtl_mtl_brdf__9"]:
            shader = get_prop(scene, "Plugin", [stem + suffix])
            bitmap_name = "/Leaves_op_tex_tex_mono_0" + suffix
            if get_prop(scene, "Plugin", [bitmap_name]) is None:
                raise RuntimeError("Expected opacity bitmap is missing")
            set_value(shader, "opacity_tex", bitmap_name)
finally:
    call_method(scene, "EndChange")
call_method(vray, "RefreshUI")
```

A new render visibly restored green foliage and purple flower heads on both
plants. That rendered result, not just the parameter write, verified the fix.

## Environment and render setup

The following live settings were changed and read back in this scene. These
paths are scene-specific and should be rediscovered in a different file.

| Node | Parameters used |
| --- | --- |
| `/Environment Texture/BitmapBuffer` | `file`: downloaded Cosmos HDR Map 721 EXR |
| `/Environment Texture/UVWGen` | `rotation_h = 55.0` |
| `/SettingsEnvironment` | `bg_tex_tex_on = 1`, `use_bg = 1`, `use_gi = 1`; existing environment links inspected |
| `/SettingsCamera` | `auto_exposure = 1`, `auto_white_balance = 1` |
| `/Rhino Document Sun` | `enabled = 0` |
| `/SettingsOutput` | `img_width = 1600`, `img_height = 1000`, `img_file`, `save_render_path`, `save_render = 1` |
| `/SettingsOptions` | `quality_preset = 2`, `render_mode = 107` |
| `/RenderChannelDenoiser` | `enabled = 1` |

Device selection and render invocation worked through the plugin interface:

```python
# Enumerate devices first; device 0 was the intended RTX GPU in this session.
devices = call_method(vray, "GetDeviceList", [System.Int32(2)])
selected = call_method(vray, "SetDeviceList", [
    System.Int32(2), System.Array[System.Int32]([0])])
if not selected:
    raise RuntimeError("V-Ray device selection failed")

# Vendor enums: production mode 0, RTX engine 2.
call_method(vray, "Render", [
    System.Int32(0), System.Int32(2), System.Int32(0)])
```

The last argument was used as a non-waiting render request in this session;
initialization can still delay its return. Do not confuse this call argument
with the scene's render time limit.

`time_limit = 3.0` and `time_limit_on = 1` were set with a stated intention of
three minutes. **The units and effective stopping behavior were not validated.**
Later previews completed quickly. Do not carry forward the three-minute claim
without checking the installed version and a timed render.

### Verify the final image

1. Record the render request time and intended output path.
2. Confirm that the file is newer than the request; an existing image can be
   left over from a failed or previous render.
3. Confirm rendering has ended. In this session the VFB's Abort rendering
   button was disabled and its Render button was enabled after completion.
4. Inspect the saved result. Compare RGB with denoiser/effects output when
   diagnosing fine foliage or lost detail.
5. Check material appearance, cutouts, foliage, reflections, texture scale,
   framing, exposure, and unwanted intersections. Do not equate a finished
   render with a polished final image.

## Reference scene and artifacts

Local reference scene: `H:/AI EXPERIMENTS/TESTBED/Vray_Testbed.3dm`.
The scene's save/reopen persistence was not verified after the final fixes.

| Existing object | Cosmos material applied |
| --- | --- |
| Cylinder | Wood Fine 18-42 100cm |
| Box with circular recess | Porcelain Dusk Blue Glossy 001 |
| Cone | Brass Clean 001 |
| Sphere | Glass Clear 001 |
| Ground | Concrete Simple C01 200cm |

Added models: **Lavandula pinnata Sidonie 004**, **Lavandula pinnata Sidonie
005**, and **Mirror 001**. Environment: **HDR Map 721**.

Downloaded model packages were under
`C:/Users/aryan/Documents/Chaos Cosmos/Packages/3D_Models/`, with package folders
`Lavandula_pinnata_Sidonie_004_5f413a7b`,
`Lavandula_pinnata_Sidonie_005_9e42c2ff`, and `Mirror_001_73ed4bef`.

Working VRMAT copies and rendered outputs were saved in:
`H:/AI EXPERIMENTS/TESTBED/Rook_Cosmos_Study/`.

- `5f413a7b_3dh_Lavandula_pinnata_Sidonie_004.vrmat`
- `9e42c2ff_3dh_Lavandula_pinnata_Sidonie_005.vrmat`
- `73ed4bef_3dh_Mirror_001.vrmat`
- `Cosmos_Material_Study.png` — RGB output.
- `Cosmos_Material_Study.denoiser.png` — denoiser output.
- `Cosmos_Material_Study.effectsResult.png` — inspected final corrected image.

The working VRMAT copies contain texture-path repairs. The later shader and
proxy-slot fixes were made in the live Rhino/V-Ray scene; they were not exported
back into those VRMAT copies. Reimporting those files alone will not reproduce
the repaired scene. Preserve or reconstruct those live changes explicitly.

These paths are machine-local evidence, not bundled repository assets. Preview
renders reused the output names; earlier failure images were not retained as a
versioned comparison set.

## Troubleshooting reference

| Symptom | First inspection | Verified response in this session |
| --- | --- | --- |
| Giant plant blobs | New object bounds, document units, proxy preview mode | Scale/place only the imported objects; verify full geometry in V-Ray |
| Uniform purple/pink proxy | `mtls_on`, `mtls_list`, `ids_list` | Populate proxy material slots with the intended material references |
| Grey asset after binding | BRDF diffuse texture/color and source VRMAT | Restore missing live shader connections |
| Stems but no flowers/leaves | Front/back opacity graphs and original bitmap | Connect original opacity bitmap directly, then rerender |
| Unsupported Cosmos asset type | Exact asset, completed download, command history | Stop repeating failed import; use verified proxy fallback where applicable |
| All Rhino calls appear stuck | Modal dialog or incomplete interactive command | Resolve that UI state before sending more work |
| Old image appears unchanged | Output modification time and render status | Inspect a confirmed new result |

## Remaining work and how to extend this record

Renderer-independent mapping development is tracked separately in
[UV_MAPPING_WORKFLOW.md](UV_MAPPING_WORKFLOW.md), including the native box
mapping contract, repeat/direction controls, live tests, and deployment limits.

- Diagnose the direct Cosmos importer rejection instead of assuming its cause.
- Establish a general material conversion path; the documented repair is
  verified for these specific assets only.
- Verify save/reopen persistence of proxy assignments, shader repairs, camera,
  and environment before claiming a portable deliverable.
- Validate render time-limit units, noise thresholds, and quality controls.
- Benchmark performance before making optimization recommendations.
- Test a second category of vegetation, another manmade asset, and relocated
  texture folders before generalizing compatibility.

For each future session, append the date, Rhino/V-Ray versions, asset names and
package IDs, observed failure, exact changed parameters, render evidence,
save/reopen result, and unresolved questions. Separate **observed**, **fixed and
render-verified**, and **suspected** behavior. Do not replace a tested workaround
with an unverified explanation.

### Learning log

| Date | Finding | Evidence/status |
| --- | --- | --- |
| 2026-09-18 | Direct RhinoCommon mapping and transforms avoid the prompts encountered in command-based mapping | Executed successfully in the live testbed |
| 2026-09-18 | Cosmos geometry import and material import can succeed independently while leaving proxy slots or shader inputs incomplete | Inspected live parameter values and successive renders |
| 2026-09-18 | Direct opacity bitmap binding restores these two lavender assets | Final 1600 x 1000 effects-result image inspected; leaves and flowers visible |
| 2026-09-18 | RTX rendering, HDRI setup, camera control, and saved denoised output are accessible through the live plugin | Rendered and inspected; no general optimization benchmark |
