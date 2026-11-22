# Surface Automation and Revision Preservation Comparison

Research date: 2026-10-24. Target: modular sci-fi architecture for Unreal Engine 5.8 on desktop PC. Specialist tools are in scope where justified. Automation means AI execution of deterministic workflows or skills, as specified by the user.

## Recommendation

Use Rhino and Grasshopper as the source of geometry and semantic mapping intent; Blender as the general mesh-preparation and validation worker; UVPackmaster for advanced packing within Blender when needed; RizomUV as the specialist for difficult unwrapping; and Substance Painter for assets that need unique layered texture work. Unreal owns the final material library, placed actors and gameplay.

These tools should form alternative branches. An asset should pass through only the stages it needs. A repeated wall with suitable Rhino mapping can publish directly to Unreal. A rail can receive a repeatable trim mapping in a Blender worker without an artist opening Blender. A complex housing can use RizomUV for its unwrap. A uniquely weathered hero asset can then use Painter. There must be one authoritative UV layout for each asset revision; the next application must not silently unwrap or repack it again.

My recommendation is to qualify **Rhino/GH plus a Blender worker as the core**, **UVPackmaster as the preferred packing extension**, **Painter as the preferred specialist branch for unique texture authorship**, and **RizomUV as a specialist unwrap branch when its output or saved artist time justifies the handoff**. This selects a workflow architecture, not an unmeasured claim that one solver always creates the best UVs.

Preservation has three distinct meanings:

- Retain accepted data exactly when its dependencies did not change.
- Regenerate equivalent results from a recorded recipe when the source changed in a compatible way.
- Reproject or repair authored work when exact retention is impossible, and identify what requires review.

That distinction should drive the AI's workflow selection. A generic instruction to unwrap and texture the updated model cannot express the necessary preservation policy.

## Evidence and local qualification

This comparison uses vendor documentation, the Rook/Engram source inspection, and a read-only probe of the installed Blender executable. No comparative meshes were unwrapped, packed, baked or reimported during this research. No plugins were installed.

| Item | Evidence obtained | Limit |
|---|---|---|
| Rhino 8.36 | Installed assembly version and RhinoCommon XML expose `MeshUnwrapper`, its three methods and symmetry-plane property. | Presence of an API does not qualify seam automation, UV quality or export fidelity. |
| Blender 5.2.1 LTS | A separate process started with background mode, factory startup and automatic file scripts disabled. Read-only introspection found unwrap, packing, data-transfer and baking operators. Build hash: `9e2066aef7ef`. | Operator execution and the specialist add-ons were not tested. |
| Blender MCP connection | The available connector could not connect. The separate executable probe succeeded. | A live bridge is an integration task; it is not necessary for a file-based background worker. |
| RizomUV | Current vendor release documentation and the author's RizomUVLink repository. | No installed build or license was qualified. |
| UVPackmaster | Version 4 documentation for scripting, density, packing modes and heuristic search. | Exact Blender 5.2 compatibility and unattended execution remain to be verified. |
| Painter | Current Python/remote-control documentation and 12.1 release notes. | No installed Painter build, API-version match or unattended session was qualified. |
| Unreal | Installed 5.8.4 and the existing Engram source audit in the broader report. | Full material and gameplay preservation remains an end-to-end test. |

Some Blender documentation URLs returned retrieval errors. Claims about the installed operator surface above use the executable's actual introspection, not a newer online API assumed to match it.

## Comparison by pipeline responsibility

The suitability judgments below are recommendations inferred from the capabilities reviewed. They are not benchmark scores.

| Tool | Best role for this kit | Automation fit | Preservation boundary | Decision |
|---|---|---|---|---|
| Rhino / Grasshopper | Parametric shapes, source identity, material roles, projection frames and repeatable surface intent | Strong fit through existing Rook dispatch and RhinoCommon; complete UV preparation needs additional coordination | Mapping parameters can be retained or reapplied, but arbitrary retessellation does not establish vertex/corner correspondence | Core authoring source; retain finished Rhino mapping when it passes export checks |
| Blender | General preparation, semantic selections, custom UV rules, transfer, baking support and diagnostics | Strongest general worker candidate here; installed background startup and API presence verified | Exact copying needs proven correspondence; spatial transfer needs error checks; destructive import can discard edits | Core automated worker, optional interactive finishing application |
| RizomUV | Difficult unwraps, constraint-driven editing and specialist UV layout | Current Python, replay and batch capabilities make it a credible automation backend | Saved constraints help round trips, but source topology changes still require correspondence or reconstruction | Preferred specialist unwrap candidate; avoid requiring it for simple repeatable mapping |
| UVPackmaster | Packing existing islands with density, grouping and preservation constraints | Script entry point and operation result checks documented | Packing can preserve surrounding layouts; it does not recover an old unwrap from a changed mesh | Preferred advanced Blender packing candidate; never an automatic global repack after painting |
| Substance Painter | Layered unique texturing, procedural masks, mesh-map baking and compatible revision reprojection | Documented project, layer, bake and export APIs; application/session lifecycle must be managed | Reprojection is conditional; moved parts, UV-space paint and material/texture-set changes need special handling | Preferred unique-texturing branch; keep reusable architecture on shared surfaces where suitable |

## Rhino and Grasshopper

Rhino 8's UV Editor provides pinning, straightening and curve constraints with conformal, angle-based and as-rigid-as-possible unwrap choices. These warrant testing Rhino as a finished UV authoring tool. [McNeel overview](https://www.rhino3d.com/features/rendering/uv-mapping/)

The installed RhinoCommon documentation exposes `MeshUnwrapper.Unwrap(MeshUnwrapMethod)` and `SymmetryPlane`. Rook already registers box, planar, cylindrical and spherical mapping routes, and its box handler takes controlled repeat dimensions and a frame. Those are useful deterministic primitives. The inspected public mapping routes do not constitute a complete seam, unwrap, pack and validate service. [Installed API](<C:/Program Files/Rhino 8/System/RhinoCommon.xml:28773>), [route registration](../../src/RookNative/RookServer.cpp#L1829), [box handler](../../src/RookNative/Handlers/TextureMappingHandler.cpp#L339)

**Recommended automation:** let the GH definition describe a surface's role and mapping rule while it still knows the construction logic. For example, publish a border's longitudinal direction, a trim region and a physical width; publish a panel's mapping origin and repeat size. The recipe can regenerate its UVs after a dimension change. Store semantic references rather than relying solely on BRep face indices or GH list positions.

**Preservation limitation:** the same logical surface can produce a different render mesh after editing or retessellation. Matching object IDs or vertex counts does not prove a correspondence between mesh corners. Preserve native mapping intent separately from the derived mesh, and compare the actual exported result.

Rhino supports mapping channels and primitive projections; its documented default surface mapping can mismatch across polysurface seams. Its UV pack action scales visible charts to fit the unit square, which is not by itself a pixels-per-meter guarantee. [Mapping reference](https://docs.mcneel.com/rhino/8/help/en-us/properties/texturemapping.htm)

For this workstation, use the current Rook execution boundary. Separate headless Rhino hosting is possible, but a headless document is not automatically an independent, fully configured batch service. Existing Rook tests already use private headless documents for UV mapping fixtures; these tests were inspected, not run. Future RhinoCommon additions should use the established companion boundary where required. [Existing UV fixture](../../mcp_server/tests/test_uv_box_mapping_live.py#L1), [Rook architecture](../../docs/CURRENT_ARCHITECTURE.md)

## Blender

The installed background probe returned Blender **5.2.1 LTS** and `background: true`. Its exposed operators include:

- `bpy.ops.uv.unwrap`, with method, margin and iteration controls.
- `bpy.ops.uv.pack_islands`, with rotation, scale, margin and pin controls.
- `bpy.ops.object.data_transfer`, with topology/spatial mapping selectors, layer selection and maximum-distance controls.
- `bpy.ops.object.bake`.

This makes Blender a suitable execution host for repeatable preparation scripts and add-ons. A future worker should set its object, mode, selections, UV layers and settings explicitly. The presence of an operator does not establish that it will run successfully in every context.

**Recommended automation:** a versioned worker recipe receives a published mesh, semantic groups and a surface specification. It verifies input identity, preserves approved UVs, applies required mapping/unwrap operations, invokes the selected packer, checks the result and writes a candidate artifact. Keep artist finishing files separate from disposable imported meshes.

**Preservation strategy:** copy UVs exactly only when vertex/face-corner correspondence is established. If geometry changes with compatible semantic regions, regenerate the relevant mapping rule. Spatial transfer is a fallback for suitable nearby surfaces, with distance and orientation checks and visual comparison. It is not an identity system. Thin surfaces, opposite sides and repeated nearby parts are specifically useful rejection fixtures.

Native packing is the baseline against which the additional packing tools should be judged. A direct data/API implementation is preferable for reliable batch execution where available; UI operator use must supply a verified context. The AI should invoke a stored worker rather than reconstruct its steps from the current Blender selection.

## RizomUV

The vendor dates the **RizomUV 2027** release to **October 8, 2026**. It documents Python as the default scripting language, replayable command logs, headless execution, and saving UV constraints, pins, brush maps and a symmetry plane in FBX. That makes preservation of the *UV editing setup* a meaningful capability to evaluate. It does not establish that another application preserves those custom fields when rewriting FBX, or that they remap onto a newly tessellated Rhino mesh. [Vendor release](https://www.rizomuv.com/feature/rizomuv-2027-release-features/)

The RizomUVLink author documents Python control, request/response execution and raised exceptions. Its `headless=True` mode requires build **2027.0.417 or later** and still needs a desktop session; it is not a displayless Windows-service deployment. Multiple instances also require consideration of license tokens. Qualify the exact application and bridge together. [Author's integration documentation](https://github.com/RemiArq/RizomUVLink)

**Recommended automation:** use a recorded unwrap recipe for difficult housings and junctions, with semantic seam/group inputs and a preserved constraint project. Return the resulting layout to the pipeline with an explicit correspondence check. If Rizom owns packing for an asset, subsequent Blender/Painter stages must consume that accepted layout unchanged. If a recipe deliberately uses Rizom only to unwrap and UVPackmaster to pack, record that division and do not run a second uncontrolled pack.

**Adoption condition:** choose it for a module class when it reduces distortion or manual correction enough to justify its handoff. Its richer constraint tools and integration are reasons to test it, not measurements of superiority over Rhino or Blender.

## UVPackmaster

The vendor's script example runs packing from Blender, explicitly resets and assigns parameters, selects a packing mode and checks the engine return code. It requires a working packer engine. The example demonstrates scriptability; it is not local proof of background operation with Blender 5.2.1. [Script entry point](https://uvpackmaster.com/doc4/blender/4.0.2/48-other-topics/3-running-from-script/)

Density tools can set a target and pack at fixed scale, with per-island and grouped controls. `Pack To Others` packs selected islands around unselected ones. These features are useful for keeping accepted layouts stable while adding work, subject to available space and correct island correspondence. [Density controls](https://uvpackmaster.com/doc4/blender/4.1.1/37-texel-density/), [packing around existing islands](https://uvpackmaster.com/doc4/blender/latest/20-packing-functionalities/20-packing-to-others/)

**Critical determinism finding:** heuristic search randomizes attempts, runs within a time budget and can use multiple CPU/GPU devices. An identical script should therefore not be assumed to yield an identical layout. [Heuristic search](https://uvpackmaster.com/doc4/blender/latest/20-packing-functionalities/40-heuristic-search/)

**Recommended automation:** use explicit settings and stable input ordering, qualify repeatability, and save accepted layouts as versioned outputs. An unchanged input should reuse its accepted layout. An optimization pass may search for a better layout before publication; routine revisions should preserve locked work and flag when it no longer fits. A fresh layout is a new surface revision, even if it improves packing efficiency.

UVPackmaster's built-in AI assistant is relevant prior art: it can save parameterized scripts and rerun them without another model request, with script-environment version metadata. Our orchestration can use the direct scripting interface; adopting the built-in assistant is not required. [AI script replay](https://www.uvpackmaster.com/doc4/blender/latest/38-ai-assistant/)

## Substance Painter

Painter's documented remote-control entry runs Python or JavaScript in the application after startup with remote scripting enabled. Despite the tutorial's headless title, the instructions establish a running-application control path, not a verified displayless service on this machine. [Remote-control tutorial](https://experienceleague.adobe.com/en/docs/substance-3d-dev/painter-python/tutorials/remote-control)

The project API documents asynchronous `reload_mesh`, `MeshReloadingSettings(preserve_strokes=True)`, automatic-unwrap controls and readiness events. The completion callback must succeed before downstream work. On existing authored projects, explicitly disable automatic UV recomputation unless the selected revision procedure calls for it. The documented auto-unwrap settings can otherwise discard seams, charts and packing. [Project API](https://experienceleague.adobe.com/en/docs/substance-3d-dev/painter-python/api/substancepainter-package/project)

The layer API can insert fills, generators, masks, groups and smart materials. This supports versioned material templates and bounded parameter changes. Preserve artist-owned layers when updating recipe-owned layers; repeated execution must not append duplicate material stacks. [Layer editing API](https://experienceleague.adobe.com/en/docs/substance-3d-dev/painter-python/api/substancepainter-package/layerstack-module/edition)

The baking API configures maps and launches asynchronous baking with completion events. The export API supports JSON configurations, presets and result status, including warnings. This provides a documented path for reload → rebake affected maps → export textures, with state-based completion checks at each stage. [Baking API](https://experienceleague.adobe.com/en/docs/substance-3d-dev/painter-python/api/substancepainter-package/baking), [export API](https://experienceleague.adobe.com/en/docs/substance-3d-dev/painter-python/api/substancepainter-package/export)

Painter 12.1 added hard-surface auto-unwrapping, skew correction and automatic rebaking. Include its initial unwrap as a candidate for suitable unique assets. The new UI option was not found under an explicit `hard_surface` field in the reviewed project API, so verify its exact scripting exposure before promising full automation. [12.1 release notes](https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/release-notes/version-12-1)

**Preservation limitation:** reprojection can handle compatible mesh/UV changes, but Adobe identifies limitations around moved geometry, unit/scale changes and strokes authored in 2D UV space. Material-ID changes can also disrupt texture-set associations. Prefer stable IDs and fill/generator layers driven by reproducible masks where they suit the art direction. Preserve the `.spp` project and a previous accepted texture export. [Reprojection behavior](https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/features/uv-reprojection), [project configuration](https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/interface/project-configuration)

## Workflow options and choice

| Option | Benefit | Cost or limitation | Recommendation |
|---|---|---|---|
| Rhino mapping directly to Unreal | Shortest route and strongest connection to parametric source intent | Native UV tooling and export behavior must cover each surface class | Use for repeatable modules with satisfactory mapping; keep it as a first-class route |
| Rhino to Blender preparation, with selected specialists | General automation host, shared validation and flexible artistic branches | Requires a reliable publication contract and worker adapters | Recommended overall architecture |
| All assets through RizomUV and Painter | Consistent specialist stages for unique UVs and paint | Extra processing and additional surface dependencies on simple repeated architecture | Use for asset classes that require it, not as the universal route |

For most corridor structure, establish a trim/tiling library first and publish geometry with repeatable mapping. For complex housings, add the specialist unwrap stage. For uniquely painted hero modules, add Painter after the UV layout is accepted. Texture source tools can also author shared materials and trim sheets without opening a separate painting project for every instance in the level.

At the Unreal boundary, preserve named material roles and stable asset references. A role may be implemented as a slot, mask, trim or parameter; avoid turning every semantic distinction into a new draw section automatically. Author final engine materials explicitly and validate normal conventions, channel packing, color spaces and the target project's material framework.

## Handling Rhino revisions

This table is a proposed execution policy. It prevents the AI from treating every change as a full rebuild.

| Detected change | Preserve | Recompute or review |
|---|---|---|
| No relevant input changes | Mesh, UV layout, textures and material assignments | Return a no-op report; do not rerun optimization |
| Placement only | Asset geometry, mapping and textures | Update only source-owned instance transforms; respect Unreal overrides |
| Name or layer only | Semantic identity and surface artifacts | Metadata and organization; reject ambiguous identity matches |
| Geometry changed with proven corner correspondence | UVs, roles and layer stack | Mapping stretch and geometry-dependent bakes; shape-dependent gameplay checks |
| Geometry changed with a repeatable mapping recipe | Recipe and material definitions | Regenerate affected mapping from semantic intent; validate density and seams |
| Retessellation with unchanged shape | Material roles and potentially transferable UV intent | Establish new correspondence; validate transfers and tangent/bake dependencies |
| Topology or part layout changed | Previous accepted revision and unaffected parts | Reconstruct affected regions, reproject where justified, flag uncertainty |
| Packing changed | Material identities and authored project | Texture reprojection/rebake or repaint review; never treat it as harmless housekeeping |
| Material role or texture-set identity changed | Unaffected roles and layers | Explicit role migration and association checks |
| Recipe, plugin or solver upgraded | Accepted artifacts until qualified | Treat as a pipeline revision and rerun the qualification set |

Keep parts in stable module-local coordinates during surface work; level placement belongs to the instance. This reduces accidental changes to painting/reprojection coordinates when a designer moves a door in the level. A genuine change to part position inside the module still requires review.

Use one deliberate tessellation boundary for an authored UV asset. If Rhino publishes its final mesh, preserve that representation through finishing. If the selected CAD translator generates the final mesh, run authored UV work after that generation. Feeding an unwrapped asset into another unconditional tessellation/remesh step defeats its correspondence assumptions.

## AI execution of deterministic skills

The AI should reason about intent, select an eligible recipe, supply bounded parameters, interpret diagnostics and propose repairs. Fixed executors should perform the numerical operations. A new artistic strategy or changed script becomes a new recipe version; routine production execution reuses the accepted version.

Each future skill needs a concrete contract:

| Skill responsibility | Input and preconditions | Result required before advancing |
|---|---|---|
| Inspect source revision | Source IDs, previous accepted revision, units and semantic groups | Classified changes, ambiguous matches and dependency invalidations |
| Prepare surfaces | Known geometry representation, mapping policy and selected solver | Candidate mesh, all channel/role mappings, numerical UV diagnostics |
| Refresh authored textures | Associated finishing project, compatible revision class and fixed settings | Completed reload/bake/export, preserved layer associations, output texture manifest |
| Validate Unreal candidate | Stable destination asset, material library and preparation recipe | Imported channels/roles, shading comparisons, collision and reference checks |
| Publish accepted revision | Passing checks and resolved surface conflicts | Updated asset references, provenance and recoverable previous revision |

These are proposed responsibilities, not tools or skills already implemented in Rook/Engram.

Record source revision, geometry/corner topology, UV layout, role mapping, recipe/script version, application/add-on build, relevant solver settings and output artifacts. Normalize volatile metadata when detecting no-op changes. Record seeds only where the selected API actually exposes them; a seed must not be invented as a determinism guarantee.

Distinguish repeatable execution from bit-identical output. A controlled command sequence can still contain a randomized optimizer or hardware-sensitive computation. Cache accepted artifacts, test reruns, compare outputs at an appropriate level, and flag unexplained differences. Exact identities, role associations and preserved UVs should be checked exactly; float-based quality measurements may need documented tolerances.

The executor should wait for application readiness and actual operation completion, not arbitrary sleeps. Verify task status plus produced files and data. A timeout must not be retried blindly if the previous mutation might still be running. Serialize dependent work per application session and identify the target project/document explicitly.

For incremental updates, operate on candidate copies and record the accepted revision before publication. A failed texture reprojection should leave the previously accepted asset usable. If both a source recipe and an artist changed the same property, report the conflict instead of choosing whichever operation ran last.

AI visual inspection is useful for seams, grain direction and wear placement. It should supplement numerical checks for UV coverage, distortion, material mapping and references. A plausible screenshot cannot prove that a channel or texture set survived.

## Required qualification before production work

The [Rhino Blender and Unreal qualification plan](2026-10-24-rhino-blender-unreal-qualification-plan.md) defines the initial seven fixtures, controlled revisions, measurable acceptance checks and adoption gates. Specialist comparisons can reuse its accepted baselines after the core routes are qualified.

Use the same small asset set and source revisions across competing routes: a flat panel with a bevel, a curved multi-surface corner, a long trim rail, a mirrored/nested module and a hero panel with paint in both 3D and UV space. Attach one published module to a working Unreal door Blueprint.

1. Establish the best native Rhino and Blender baselines. Check checker patterns, trim orientation, density, seams, normals and all transferred channels.
2. Compare Blender packing with UVPackmaster and the difficult unwraps with RizomUV. Measure artist correction time as well as packing, distortion and memory use.
3. Compare the unique-texture branch with Painter, including its auto-unwrap only as an explicitly chosen initial preparation alternative.
4. Apply no-op export, dimension changes, changed tessellation, reordered source objects, a new bevel, a moved part, new islands and changed material roles.
5. Verify unchanged islands and identities, changed-region quality, texture reprojection, duplicate-free reruns and propagation into Unreal without replacing gameplay actors.
6. Interrupt an operation, restart the applications and resume from recorded state. Verify that stale or partially completed work cannot be published as successful.

Report distortion and density by relevant surface, padding at useful mip levels, unintended overlaps, trim deviation, normal-map seams, preserved paint landmarks, manual corrections, update time and runtime cost. Do not rank a tool by packing percentage alone or invent aggregate quality scores before the measurements exist.

The research recommendation is ready. Production adoption remains conditional on the same-fixture results, particularly exact-version scripting, Rhino mesh correspondence, UVPackmaster rerun behavior, Rizom constraint transport and Painter reprojection. The first implementation should be the smallest shared publication and validation contract that enables these comparisons, after the workflow choice is accepted.

## Relationship to existing Rook and Engram work

The current source audit found manifest naming disagreement, incomplete material assignment and import settings not forwarded through the Engram helper. Resolve that shared contract before adding multiple application adapters. Preserve separate definition and instance identities, and make UV/material dependencies explicit. FragmentsUnreal's separation of logical identity from rendering instances and its separate override data remain relevant patterns.

See the [broader pipeline research](2026-10-24-rhino-blender-unreal-pipeline-research.md) for the repository revisions, source links, Dataprep/Interchange comparison and gameplay-preservation requirements.
