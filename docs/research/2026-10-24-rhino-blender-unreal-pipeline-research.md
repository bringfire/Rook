# Rhino Blender and Unreal Pipeline Research for Modular Sci Fi Architecture

Research date: 2026-10-24. Target: UE 5.8 on desktop PC, confirmed by the user.

Confirmed scope: include specialist tools where their contribution justifies them. Evaluate quality, revision reliability, artist time, automation, exact-version compatibility and the cost of an additional handoff. Rhino, Blender and Unreal are the core applications; the comparison is not restricted to them.

Automation means AI execution of deterministic workflows or skills. The [deeper surface automation comparison](2026-10-24-surface-automation-comparison.md) examines the five tools' actual APIs, revision boundaries, repeatability and recommended roles. It extends this report's initial UV assessment.

The next evaluation step is defined in the [Rhino Blender and Unreal qualification plan](2026-10-24-rhino-blender-unreal-qualification-plan.md): seven test fixtures, twenty baseline/revision cases and explicit checks for surfaces, placement, gameplay and recovery.

The goal is to model a modular architectural kit in Rhino and Grasshopper, finish surfaces in Blender or Unreal, and revise the source geometry without rebuilding materials, placement, or gameplay. The strongest candidate starts by designing the surface system alongside the kit: material families, trim sheets, mapping rules and texture budgets. It then publishes a reusable asset library through a direct route or an optional specialist finishing branch, with persistent Unreal actors referencing those assets. Datasmith and Visual Dataprep deserve a direct comparison with that approach before implementation. FragmentsUnreal supplies useful implementation ideas, particularly identity mapping and separate overrides, but its custom runtime geometry pipeline should earn its place through a measured benefit.

This is a research assessment and proposed qualification process. The source inspection and installed-engine inventory are complete; cross-application import, revision, visual-quality, and packaged-game tests have not been run. The architectural recommendation remains provisional until those tests establish what the exact software combination preserves.

## Findings that change the decision

1. **Unreal already provides much of the preparation machinery.** Dataprep can express repeatable preparation recipes; Interchange supplies import pipelines; Data Validation checks asset rules. These are different responsibilities. Rook and Engram should orchestrate them where suitable instead of duplicating each subsystem.
2. **Datasmith supports useful reimport preservation, with specific boundaries.** It tracks actor transforms and material assignments, among other properties. It does not track arbitrary mesh edits or parent-material graph edits. Preserving an assignment is not the same as preserving UV painting or a gameplay reference through deletion and recreation. [Epic override reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/datasmith-plugins-overview)
3. **The current Rook–Engram handoff has concrete source-level gaps.** Manifest field names disagree, material assignment is unfinished in the inspected helper, and advertised import controls are not forwarded to its C++ import call. A successful first import cannot establish a reliable revision workflow.
4. **Blender should be optional per asset.** Frequently revised architectural panels can use repeatable mapping and Unreal materials. Assets with unique UVs, baked detail, or custom decal layouts benefit from a deliberate Blender finishing stage with a clear revision boundary.
5. **Stable identity matters before transport speed.** A fast live link that changes object identity can lose downstream work. A slower reproducible import that retains asset and instance identity may be the better production foundation.

## Local baseline

| Component | Inspected baseline | Practical consequence |
|---|---|---|
| Rook | `C:/UDEV/Rook`, commit `807bfed490c70cca6fb928ed0f7336a8947b2d80` | Existing native game-export handler and Python tools are the starting point. |
| Engram | `D:/Engram-source`, commit `e994b04d4573640b7a6384c824112a1895a30ade` | Reference checkout of the requested repository; source capabilities below refer to this revision. |
| FragmentsUnreal | `D:/FragmentsUnreal`, commit `99fba3b451748e015a3a02d0eb182dd178794018` | Full clone requested by the user. Compatibility and performance on this machine remain to be qualified. |
| Installed target engine | `C:/Program Files/Epic Games/UE_5.8`, **5.8.4**, changelist `58902052` | Use this installation for a future qualification project. |
| Separate engine source | `D:/UnrealEngine`, **5.8.2** | Helpful for source inspection, but its defaults are not proof of the installed 5.8.4 runtime behavior. |
| Blender installations | Blender 5.2.1 LTS verified through a read-only background API probe; a Blender 4.5 directory was also observed earlier | Background startup and UV/bake operator presence are verified. Asset operations and add-on compatibility remain unqualified. |

The installed Dataprep descriptor is neither Beta nor Experimental and is disabled by default. Interchange is enabled by default; the separate **Datasmith Interchange** plugin is marked Experimental. These are three distinct descriptors, so the stability label of one must not be applied to the others. [Installed Dataprep descriptor](<C:/Program Files/Epic Games/UE_5.8/Engine/Plugins/Enterprise/DataprepEditor/DataprepEditor.uplugin>), [Datasmith Interchange descriptor](<C:/Program Files/Epic Games/UE_5.8/Engine/Plugins/Experimental/Enterprise/DatasmithInterchange/DatasmithInterchange.uplugin>)

## Where each application is best suited

These assignments are recommendations for this project, not restrictions on what the applications can do.

| Responsibility | Proposed owner | Reason and handoff |
|---|---|---|
| Dimensions, construction logic, module variants, curved surfaces, repetition rules | Rhino and Grasshopper | Retain the editable parametric source. Publish deliberate mesh representations, pivots, identities, and semantic material roles. |
| UV art direction, trim placement, mesh-specific detail, texture baking, unique wear and decals | Blender when needed | Use a finishing file associated with a source module. Record whether upstream revisions can be reapplied procedurally or require renewed art work. |
| Final shader behavior, material instances, lighting, collision behavior, navigation, gameplay and platform performance | Unreal | Judge the result in the engine that will ship it. Keep gameplay actors and authored materials independent of disposable import output. |
| Export validation, preparation recipes, provenance, change summaries, repeatable updates | Rook and Engram | Coordinate the applications, invoke existing import/preparation features, and report conflicts. The missing value is a dependable contract across tools. |

For a sci-fi kit, use Rhino/GH for panel proportions, wall openings, corridor sections, repeatable ribs and attachment locations. Use Blender where controlled UV placement, trim alignment, baked details or unique damage materially improve the result. Use Unreal to tune painted metal, rubber, glass, emissive strips, decals and lighting under the actual game's rendering conditions.

There are two legitimate layout workflows. Rhino/GH can publish both modules and their placements, or publish the kit while Unreal owns assembly. A hybrid is also possible by assigning layout ownership per room or collection. The rule must be explicit: an instance moved by a designer in Unreal should not silently snap back during a geometry update.

## UV mapping and surface authoring

Surface design should begin alongside module design. Decide which panel borders use which trims, which directions brushed metal follows, where rubber seals and emissive strips sit, and how repeated pieces receive variation. Those choices affect geometry boundaries and mapping; deferring all of them until after modeling creates avoidable rework. Insomniac's documented Ultimate Trim workflow is useful production precedent for designing a shared trim layout, mapping tools and shader together. It is a case study, not proof that its exact layout fits this kit. [GDC presentation overview](https://gdcvault.com/play/1022323/The-Ultimate-Trim-Texturing-Techniques)

### Separate the surface authoring responsibilities

| Responsibility | What must be decided | Proposed tool evaluation |
|---|---|---|
| Surface system | Material families, trim dimensions, texture density, variation and memory budgets | Establish in Unreal with representative Rhino modules and authored texture sources. |
| Mapping and unwrapping | Projection frames or seams, island shape, distortion, orientation and continuity | Compare Rhino 8 with Blender on the same modules; evaluate a specialist only for a demonstrated gap. |
| Packing | Fixed density, padding, permitted overlaps, locked trims, tile allocation | Test native tools, UVPackmaster and optionally RizomUV. Packing efficiency alone is insufficient. |
| Texture authoring and baking | Reusable maps, unique paint, masks, normal maps and geometric bake dependencies | Blender baseline; optional Substance Painter for unique layered texturing and revision handling. |
| Runtime materials | Shader features, material instances, texture interpretation, lighting response and cost | Unreal owns the final rendering contract. |
| Publication and revision | Channel/role mapping, preservation, invalidation and quality reports | Rook and Engram coordinate the chosen tools and record the result. |

### Rhino 8 is a serious candidate

Rhino 8 added a redesigned UV Editor, pinning, edge straightening and alignment to curves. Its unwrap choices include conformal, angle-based and as-rigid-as-possible methods. These features justify testing Rhino for finished architectural UVs instead of assuming every asset needs to leave it. [McNeel UV feature guide](https://www.rhino3d.com/features/rendering/uv-mapping/)

The mapping documentation also covers multiple channels, primitive projections and packing. Packing uniformly rescales the visible UV meshes into the unit square; that alone does not establish the requested pixels-per-meter density. Default surface mapping follows surface structure and can mismatch across polysurface seams. A NURBS parameterization therefore needs validation before it is treated as a finished texture layout. [Rhino texture mapping reference](https://docs.mcneel.com/rhino/8/help/en-us/properties/texturemapping.htm)

The installed `RhinoCommon.dll` reports **Rhino 8.36**, file version `8.36.26282.15001`. Its accompanying API documentation contains `MeshUnwrapper`, including `Unwrap(MeshUnwrapMethod)`. This gives us an existing solver to evaluate for automation; it does not establish automated seam planning, full UI-feature parity or production-quality packing. The public online API currently describes a Rhino 9 build, so the local Rhino 8 API evidence is relevant. [Installed API](<C:/Program Files/Rhino 8/System/RhinoCommon.xml:28773>), [public API](https://mcneel.github.io/rhinocommon-api-docs/api/RhinoCommon/html/T_Rhino_Geometry_MeshUnwrapper.htm)

Rook already registers box, planar, cylindrical and spherical mapping routes. Its box mapping supports a controlled frame, mapping channel and repeat dimensions. The inspected mapping handlers and MCP declarations do not expose a complete seam-selection, unwrap, packing and UV-quality workflow. Extending that capability is an option to evaluate after choosing a workflow, not a prerequisite for testing Rhino's existing UI. If a future implementation uses RhinoCommon, respect the managed companion boundary. [Native routes](../../src/RookNative/RookServer.cpp#L1829), [box implementation](../../src/RookNative/Handlers/TextureMappingHandler.cpp#L339)

McNeel separately documents newer **beta** work on unwrap reliability, symmetry, constraints and matching UV scale. These are promising capabilities to watch, but the beta announcement is not evidence that every improvement ships in the installed Rhino 8.36 build. [McNeel developer announcement](https://discourse.mcneel.com/t/rhino-beta-feature-uv-editing-improvements/207885)

### Choose a mapping strategy per module class

| Surface class | Proposed strategy | Revision behavior to prove |
|---|---|---|
| Broad wall and floor surfaces | Physically scaled planar/box mapping with shared tiling textures | Resizing a panel retains texture scale and direction. Explicitly choose whether the origin stays centered or anchored to a connection edge. |
| Ribs, borders, rails and repeated panels | Trim sheets with deliberate strip assignments and longitudinal direction | Length changes repeat or extend the intended trim; they do not stretch its width or move it into another strip. |
| Curved housings and complex junctions | Selected seams, controlled unwrap and density-aware packing | Curvature changes remain within distortion limits or trigger a surface revision. |
| Hero assets with unique wear or graphics | Authored UVs, baked maps and layered paint | Reimport preserves compatible work and identifies the maps or strokes requiring repair. |
| Room-scale dirt and repeated-module variation | Unreal decals and controlled material variation, with appropriate coordinate choices | Variation survives mesh replacement and does not move unexpectedly when a door or module moves. |

For procedural pieces, store the *mapping recipe* as source intent: mapping frame, physical repeat size, semantic trim region, seam intent where representable, density class and channel purpose. Reapply it to revised geometry. This is a proposed Rook/GH opportunity, especially where the definition already knows which faces form a border, panel or seal. A deterministic solver alone does not guarantee stable charts after topology changes; the semantic rules and comparison checks still matter.

For authored pieces, preserve the finishing project and its connection to the published mesh. Repacking existing islands can move every painted feature even when the geometry is unchanged. A generic auto-pack step must therefore be disabled or constrained for a locked trim layout or painted texture set.

### Specialist tools worth comparing

Specialist evaluation is in scope at the user's request. The initial comparisons are Rhino/Blender unwrapping against RizomUV, native packing against UVPackmaster, and Blender texture authoring against Substance Painter for unique assets. Use the same representative geometry and revision sequence for each comparison. Adoption should follow demonstrated benefit; this scope decision does not select a product or require a purchase.

Blender remains a strong finishing candidate because it can keep mesh edits, UV work and texture work together. Zen UV and DECALmachine add focused trim-authoring workflows already listed below. UVPackmaster provides explicit texel-density settings and packing at fixed scale, including density tiers and per-island controls. This addresses a different problem from simply making islands fill the available square. [UVPackmaster density tools](https://uvpackmaster.com/doc4/blender/4.1.1/37-texel-density/)

RizomUV Virtual Spaces is a specialist unwrap/packing candidate with constrained unwrapping, grouped packing, island locking and similar-island handling. Compare artist time, distortion, density and repeatability against Rhino and Blender before adding another application. The presence of an advanced packer does not solve source identity or revision reconciliation. [RizomUV capabilities](https://www.rizomuv.com/virtual-spaces/)

Substance Painter deserves evaluation if unique wear, paint and layered masks become a substantial part of the kit. Its UV reprojection recomputes layers and strokes after mesh changes, including similar topology changes. Adobe documents limits: substantial UV changes undermine 2D-view strokes, moved parts can defeat world-space reprojection, and unit changes can disrupt scale. It is a useful revision mechanism, not a guarantee for arbitrary redesigns. [Painter UV reprojection](https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/features/uv-reprojection)

Painter's project settings also warn that material-ID changes can disable existing texture sets. Stable role names must survive the entire chain, including texture authoring. Its normal-map convention settings distinguish Unreal and Blender, another reason to validate a concrete export preset. [Painter project configuration](https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/interface/project-configuration)

### Unreal preparation and material ownership

Unreal's UV Editor and Geometry Scripting can participate in preparation and repair. The documented `Apply Texel Density UVScaling` operation is an existing automation candidate. Dataprep can coordinate other preparation, but a successful recipe execution should not be mistaken for an artist-approved UV layout. [Texel-density API](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/GeometryScript/UVs/ApplyTexelDensityUVScaling?lang=en-US)

Keep final Unreal material definitions and authored instances separate from replaceable import output. Map source roles to approved materials and texture sets; do not depend on full shader-graph equivalence between applications. A semantic role need not become its own material slot: some distinctions can be encoded in masks, trims or instance parameters. Compare the resulting rendering cost instead of assigning one shader slot to every surface distinction.

World-aligned projection is an option for suitable static surfaces, but moving geometry can exhibit texture swimming. It also does not produce a unique paint layout or replace all directional trim work. Test local coordinates or authored UVs for moving doors and mechanisms. [Epic texturing functions](https://dev.epicgames.com/documentation/en-us/unreal-engine/texturing-material-functions-in-unreal-engine)

Document channels by purpose and verify their actual indices after transfer. Base/trim mapping, unique masks and baked-lighting UVs have different overlap rules. Material textures may intentionally tile or overlap; lightmap layouts require unique space when that lighting path is used. Do not automatically reserve a lightmap channel for every asset, or assume a Rhino channel number maps directly to the same Unreal index. [Unreal UV channels](https://dev.epicgames.com/documentation/unreal-engine/using-uv-channels-with-static-meshes-in-unreal-engine?lang=en-US)

### Surface acceptance tests

Add the following to the corridor qualification before choosing a route:

- Show a diagnostic checker and directional pattern in Rhino, the finishing application and Unreal. Compare orientation, scale and continuity after import.
- Measure effective texel density per material use, including shader tiling. A single texture dimension and aggregate UV-area number cannot describe every material on a multi-material asset.
- Verify trim borders, padding at relevant mip levels, intended overlaps, mirrored normal-map behavior and distortion under close viewing.
- Bake and compare normal maps using the actual published triangulation and tangent settings. Any geometric bake inputs must be regenerated or reviewed after dependent geometry changes.
- Resize a wall, lengthen a rail, alter a bevel and move a door. Compare repeatable mappings with authored UVs and any reprojection result.
- Reimport multiple channels and material roles through each candidate translator. Use visible diagnostics so a missing channel cannot pass merely because a mesh imported.
- Profile representative Unreal materials, including texture memory and shader cost, under the chosen lighting setup. A high packing percentage is not the overall quality score.

The decision should follow the results: use Rhino directly wherever it meets the quality and revision criteria, bring in Blender or a specialist where it improves the outcome, and make every asset's surface dependencies explicit.

## Unreal capabilities to evaluate before custom development

### Datasmith and Rhino

Epic documents both Rhino file import and an exporter workflow. The Rhino integration carries scene organization, block instancing, materials and user text, with Direct Link available for iterative synchronization. This makes it the natural baseline for a Rhino-authored scene. Qualify direct `.3dm` import separately from `.udatasmith` export: translator behavior, tessellation and identity should not be assumed equivalent. Match the exporter to the target engine version. [Rhino interoperability](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-datasmith-with-rhino-in-unreal-engine), [supported formats and applications](https://dev.epicgames.com/documentation/unreal-engine/datasmith-supported-software-and-file-types)

Datasmith can reimport an entire scene or individual assets. Scene reimport and synchronization of placed scene actors are separate steps. Geometry changes and parent-material reconstruction can overwrite work that is outside the override contract; Epic recommends separating modified assets where necessary. An independent material library and explicit synchronization policy are therefore useful even if Datasmith wins the comparison. [Reimport workflow](https://dev.epicgames.com/documentation/en-us/unreal-engine/datasmith-reimport-workflow-in-unreal-engine)

Direct Link is attractive for preview and iteration, but it is not evidence that arbitrary gameplay actors, hand-edited UVs, or a Dataprep recipe will survive or rerun correctly. Those are separate acceptance tests.

### Visual Dataprep

Dataprep provides a preparation asset containing inputs, selection rules, operations and an output consumer. Its preview-and-commit workflow makes a recipe reviewable before it produces project content. Parameterized Dataprep Instances can share a recipe while varying inputs or settings. [Dataprep overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/dataprep-overview-in-unreal-engine), [Dataprep Instances](https://dev.epicgames.com/documentation/unreal-engine/working-with-dataprep-instances-in-unreal-engine?lang=en-US)

Relevant built-in operations include material substitution through a table, tags and metadata, collision generation, LOD creation, mesh substitution, merging, pivot changes and output organization. This could implement much of a modular-kit preparation policy. Merging and remeshing need particular care: they change the granularity or surface data on which identity, UVs and gameplay attachment may depend. [Operation reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/dataprep-operation-reference-in-unreal-engine)

The installed 5.8.4 headers expose `UEditorDataprepAssetLibrary::ExecuteDataprep`, plus producer-management functions. Engram could invoke this existing API after a recipe is established. It need not invent a replacement recipe engine. [Installed scripting API](<C:/Program Files/Epic Games/UE_5.8/Engine/Plugins/Enterprise/DataprepEditor/Source/DataprepEditorScriptingUtilities/Public/EditorDataprepAssetLibrary.h:61>)

Qualification must establish the identity and overwrite behavior of **re-executing and committing a recipe**, not merely the behavior of ordinary Datasmith reimport. A successful Dataprep first pass is insufficient.

### Interchange and file reimport

Interchange separates translation from configurable processing and asset creation. It offers scripting/extensibility and retains pipeline information for reimport. It is a strong candidate for the Blender-to-Unreal asset branch, while Datasmith remains a distinct scene-oriented route. [Interchange import documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-assets-using-interchange-in-unreal-engine)

There is a version discrepancy worth resolving in the fixture: the current online page still describes FBX support as experimental, while the separate local 5.8.2 source initializes `GInterchangeEnableFBXImport` to `true`. Do not select or reject FBX solely from that label; record which importer actually processes the file in installed 5.8.4 and test its reimport behavior. [Local FBX translator](D:/UnrealEngine/Engine/Plugins/Interchange/Runtime/Source/Import/Private/Fbx/InterchangeFbxTranslator.cpp:34)

Epic's FBX material documentation describes material-name matching during reimport. That supports testing stable slot names rather than relying on numeric slot order. It is not proof that every exporter and Interchange configuration implements identical matching. [FBX material pipeline](https://dev.epicgames.com/documentation/unreal-engine/fbx-material-pipeline-in-unreal-engine)

### Data Assets and Data Validation

Visual Dataprep and Data Assets solve different problems. A Data Asset stores structured project data; a Primary Data Asset additionally supports Asset Manager identification and bundles. A module definition could eventually hold a mesh reference, material roles, connection points, collision policy and allowed gameplay class. This is a proposed project use, not an automatic import feature. [Data Assets](https://dev.epicgames.com/documentation/en-us/unreal-engine/data-assets-in-unreal-engine)

Asset Manager helps control discovery, loading, auditing, cooking and chunking. Use it if the size and loading needs of the module library justify it; a small first kit does not require a custom asset-management framework. [Asset management](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-management-in-unreal-engine)

Data Validation can check naming, dependencies and project-specific asset rules, including through command-line validation. It is a suitable home for checks such as missing material roles, invalid pivots, unexpected collision, broken module references and exceeded budgets. Rook should validate source intent; Engram should validate the resulting Unreal assets. [Data Validation](https://dev.epicgames.com/documentation/unreal-engine/data-validation-in-unreal-engine)

### UV editing and geometry preparation inside Unreal

Unreal's UV Editor offers seam editing, layout and automatic UV generation; its documentation labels it Beta. That means an all-Rhino-and-Unreal route is worth testing for straightforward architectural assets. It does not make imported-mesh UV edits immune to replacement on reimport. [UV Editor](https://dev.epicgames.com/documentation/unreal-engine/uv-editor-in-unreal-engine?lang=en-US)

Geometry Scripting supplies mesh-processing and analysis operations, but its Dynamic Mesh representation has different rendering characteristics from shared Static Mesh assets. Prefer it for preparation where useful, with deliberate output to the shipping asset representation. [Geometry Scripting](https://dev.epicgames.com/documentation/en-us/unreal-engine/geometry-scripting-users-guide-in-unreal-engine)

### Assembly and rendering

Level Instances can package reusable actor collections, including gameplay setups. Packed Level Blueprints target static mesh arrangements optimized for rendering. Use that distinction when separating a static corridor shell from doors, triggers and other interactive actors. Level Instances alone do not provide an automatic streaming strategy outside a World Partition world. [Level Instancing](https://dev.epicgames.com/documentation/en-us/unreal-engine/level-instancing-in-unreal-engine)

Unreal's instanced Static Mesh components provide a native baseline for repeated modules. Nanite supplies a geometry-rendering option, but it does not replace material, collision, UV or gameplay design. Compare these existing systems against FragmentsUnreal using the same scene before adopting custom batching or LOD behavior. [Instanced Static Meshes](https://dev.epicgames.com/documentation/unreal-engine/instanced-static-mesh-component-in-unreal-engine), [Nanite](https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine)

PCG can handle Unreal-side assembly and dressing through mesh or actor spawning. Give each generated population a single owner so GH regeneration and PCG regeneration do not compete. The documented experimental GPU procedural instancing route excludes capabilities including collision, navigation and HLOD generation, making it a poor default for structural gameplay geometry. [PCG node reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/procedural-content-generation-framework-node-reference-in-unreal-engine), [GPU processing limitations](https://dev.epicgames.com/documentation/unreal-engine/using-pcg-with-gpu-processing-in-unreal-engine?lang=en-US)

Substrate is another version-sensitive decision. Epic states that new projects enable it by default, while existing projects upgrading to 5.7 or later retain the previous material path unless opted in. GBuffer choices trade rendering cost and fidelity, and explicit material conversion is not automatically reversible. Inspect the actual target project's rendering settings before establishing a master-material library or choosing a bridge that generates materials. [Substrate overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/overview-of-substrate-materials-in-unreal-engine)

## Existing plugins and alternative workflows

The evaluation labels below are recommendations based on capabilities and compatibility evidence, not benchmark rankings.

| Candidate | Useful contribution | Assessment for this project |
|---|---|---|
| Rhino 8 Content Cache | Updates baked content without deleting it first. | First native GH baseline. Test identity through reordered trees, changed counts and document restart. [McNeel](https://www.rhino3d.com/features/grasshopper/content-cache/) |
| eleFront | Attributes, blocks, references and controlled baking. | Useful existing ecosystem; its documented BakeName flow removes prior objects and creates replacements. Use persistent semantic keys if native object identity changes. [Author's bake documentation](https://elefront.via.inc/docs/eleFront%20Primer/Bake/) |
| Datasmith exporter and Direct Link | Rhino scene transfer and iterative synchronization. | Essential baseline; qualify preview, publish and reimport separately. [Epic Rhino guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-datasmith-with-rhino-in-unreal-engine) |
| `import_3dm` for Blender | Imports Rhino data with options for blocks, layers and material handling. | Inspect and test as the optional Blender entry point. Its source uses document units and separate conversion handlers; repeated import is not itself a promise to preserve manual edits. [Repository](https://github.com/jesterKing/import_3dm), [reader implementation](https://raw.githubusercontent.com/jesterKing/import_3dm/master/import_3dm/read3dm.py) |
| RenderFlo | Vendor advertises direct `.3dm` import and reload into Blender. | Alternate entry-point candidate. Qualify UV retention, object matching and exact Blender support before adoption. [Blender Extensions listing](https://extensions.blender.org/add-ons/id-renderflo/) |
| Epic Send to Unreal | Automates exports from Blender collections into Unreal. | Compare against plain file export as a convenience layer. The repository/quickstart does not establish this machine's Blender 5.2 and UE 5.8.4 combination as tested. [Quickstart](https://github.com/EpicGames/BlenderTools/blob/main/docs/send2ue/introduction/quickstart.md) |
| Blender For Unreal Engine | Authoring/export helpers including collision, sockets and LOD workflows. | Strong alternative for the game-asset branch; test exact versions and material-slot reimport. [Author's repository](https://github.com/xavier150/Blender-For-UnrealEngine-Addons) |
| Blender IO Datasmith | Community Datasmith importer/exporter with scene hierarchy, instancing and material support. | Worth comparing if Blender must participate in a scene-oriented Datasmith route. It adds its own UE plugin and material conventions. [Repository](https://github.com/botero-dev/bl_datasmith) |
| GFBlenderBridge | In-memory transfer; author describes UE override reconciliation, identity and mesh updates. | Particularly relevant prior art. README names UE 5.7/5.8 and Blender 5.2+, but these are project claims, not local validation. Some payloads, including UDIM images, are explicitly unsupported. [Repository](https://github.com/ahaczewski/GFBlenderBridge) |
| Mindesk | Commercial Rhino/GH-to-Unreal live workflow; vendor advertises persistent material application. | Relevant precedent. Public download notes reviewed here name Rhino 8 and UE 5.3; UE 5.8 compatibility requires separate evidence. [Workflow](https://mindeskvr.com/unreal/), [release notes](https://mindeskvr.com/download/) |
| Speckle | Geometry and metadata exchange across applications. | Do not assume an actively maintained Unreal route: the official Unreal connector repository was archived on May 12, 2026 and describes the legacy v2 connector. [Official repository](https://github.com/specklesystems/speckle-unreal) |
| USD | Layered scene composition and references. | Consider when shared scene composition becomes a real requirement. It adds another identity/material/import boundary and does not automatically preserve Unreal gameplay. [Epic USD overview](https://dev.epicgames.com/documentation/unreal-engine/universal-scene-description-in-unreal-engine?lang=en-US) |
| Houdini Engine | Established procedural recook and bake workflow. | Valuable architectural precedent: separate editable procedural output from published native assets. No reason yet to replace the user's Grasshopper expertise. [SideFX integration](https://www.sidefx.com/docs/houdini/unreal/intro.html) |

For optional Blender surfacing, DECALmachine provides trim/decal authoring and atlas-export workflows, and Zen UV provides trim placement and texel-density tools. They improve asset authorship rather than solve source identity or reimport preservation. Qualify exported textures and meshes in Unreal instead of assuming an older engine-specific material example applies unchanged. [DECALmachine](https://machin3.io/DECALmachine/docs/), [atlas export](https://machin3.io/DECALmachine/docs/export_atlas/), [Zen UV trims](https://zenmastersteam.github.io/Zen-UV/latest/trimsheet_operators/), [texel density](https://zenmastersteam.github.io/Zen-UV/4.5/texel_density/)

Blender materials should have an explicit transfer contract. Standard exchange represents selected shading models and texture relationships, not arbitrary Blender node behavior. Bake procedural appearance when necessary or author equivalent Unreal materials. Substance's Unreal integration and node translators such as TransMat are optional alternatives, with their own supported representations and dependencies. They do not remove the need to decide which application owns the final shader. [Blender glTF material documentation](https://docs.blender.org/manual/en/5.0/addons/import_export/scene_gltf2.html), [Substance integration](https://www.adobe.com/products/substance3d/plugins/substance-in-unreal-engine.html), [TransMat repository](https://github.com/SpectralVectors/TransMat/)

## Three architectures to compare

| Approach | Workflow | Best fit | Main cost or risk |
|---|---|---|---|
| Scene through Datasmith and Dataprep | Rhino/GH scene → Datasmith → preparation recipe → Unreal scene | GH remains the main author of room layout and repeated geometry. | Qualify imported hierarchy, recipe regeneration and overrides carefully; gameplay cannot depend on replaceable imported actors. |
| Reusable assets with optional Blender finishing | Rhino/GH module → direct import or Blender → stable Unreal mesh asset → persistent UE actors and assemblies | Modular sci-fi kit reused across playable levels. | Requires explicit asset identity, material roles and publishing rules; unique UV work needs controlled revision handling. |
| Broad live or layered scene exchange | Multiple applications connected through a live bridge, USD or custom representation | Continuous cross-application scene composition is itself a central requirement. | Largest compatibility and ownership surface; interactive synchronization can conceal destructive conflicts. |

**Provisional preference: the second approach, with Datasmith/Dataprep retained as a candidate import and preparation route.** These are not mutually exclusive engine features. The architectural choice is who owns assets and placed actors; the translator can be selected independently for each asset class.

For example, changing a door-frame profile in Rhino should update a stable frame mesh. The existing Unreal door Blueprint retains its trigger, animation settings, interaction logic and level transform. If the revision changes the opening or hinge position, a geometric validation must still flag a possible gameplay mismatch. Keeping references intact is necessary but does not prove the revised door works.

An optional GH layout publication would carry stable instance IDs and transforms separately from the module geometry. Unreal could then apply source-owned placement changes while retaining explicitly authored instance overrides. That reconciliation is project work to design and test; no inspected bridge currently establishes the complete contract.

### Proposed daily authoring workflow

1. **Model and classify in Rhino/GH.** Work with reusable module definitions and meaningful part roles. Set the module origin, connection locations and material-role names before downstream finishing. Keep source geometry editable.
2. **Publish a candidate revision.** Rook validates the source and records geometry, identities, units, placement intent and the chosen preparation settings. Present a change summary so a rename can be distinguished from a replacement or deletion.
3. **Take the appropriate surfacing branch.** Simple repeatable modules go directly to Unreal preparation. Modules needing unique UVs or baked detail enter their associated Blender finishing file. The two branches must not compete to overwrite the same final mesh.
4. **Prepare and inspect in Unreal.** The selected translator and recipe produce the mesh candidate; resolve material roles against the authored Unreal library. Inspect shading, pivots, collision and dimensions before publishing the update to assets referenced by the level.
5. **Assemble and author gameplay.** Place module assets, reusable room assemblies and interactive Blueprints. Store designer overrides independently from source placement intent. GH can supply layout candidates where it owns the layout.
6. **Revise through the same route.** A profile change in Rhino repeats the recorded preparation. Engram reports the assets affected and any invalidated surfacing or gameplay assumptions. A failed check leaves the previous accepted revision available.

This describes the desired experience after qualification; it is not a claim that the current tools already implement these steps end to end.

| Module class | Suggested surface treatment | Revision expectation |
|---|---|---|
| Frequently resized walls, floors and structural ribs | Repeatable mapping and reusable Unreal materials; parameterized trim placement where practical. | Most dimension changes should be regenerable. Check density, orientation and seams. |
| Detailed but reusable panels and door frames | Blender trim alignment, controlled normals and optional baked detail; Unreal owns final material instances. | Compatible changes may be reapplied; changes to borders, bevels or openings can require UV/bake review. |
| Hero panel, unique damage or signage | Deliberate unique UVs, textures and decals in a finishing file. | Preserve the published asset reference, but treat incompatible source topology as a new art revision. |
| Interactive door or mechanism | Separate visual modules plus an Unreal gameplay Blueprint. | Geometry can update without replacing the Blueprint; connection, clearance and collision checks remain mandatory. |

## What preserving revisions actually requires

The following is a proposed contract for evaluating the candidate workflows.

| Identity or ownership rule | Why it matters |
|---|---|
| Source document ID plus persistent module definition ID | A rename, layer move or export filename change should not create a new module accidentally. |
| Persistent instance ID distinct from the module ID | Many placements may reference the same mesh while retaining different transforms, material overrides and gameplay associations. |
| Stable material-role names | `PaintedMetal`, `RubberSeal`, `Glass` and `Emissive` are meaningful across revisions. Numeric face or slot indices are fragile. |
| Explicit geometry, surface and placement ownership | Two importers must not independently overwrite the same asset; the system must know whether a material or transform is authored or generated. |
| Source revision and processing recipe recorded together | The same geometry with different tessellation or preparation settings is a different derived result. |
| Explicit deletion and split/merge handling | Removing a source item must produce a reviewable change, not silently delete an actor with gameplay references. |
| Repeatable update with a change report | Running the same publication twice should not duplicate assets, actors, materials or provenance entries. |

Grasshopper tree paths, object names and array positions are useful descriptors but poor sole identities. Native Rhino UUIDs are useful where preserved; bake workflows that replace objects need an explicit semantic identity carried as metadata. The fixture must distinguish these cases rather than assuming one universal identifier.

| Revision class | Expected handling |
|---|---|
| Source rename or layer reorganization | Update descriptive metadata while retaining identity and references. |
| Placement-only change | Update source-owned transforms; retain or flag designer overrides according to policy. |
| Dimension change with compatible topology | Rebuild geometry and repeat deterministic preparation; verify mapping and collision. |
| Retessellation, bevel change or topology change | Preserve asset/material-role identity where possible; reassess UVs, baked maps, vertex data and sockets. |
| New material role or changed role partition | Reconcile by role and report unmapped roles; do not guess from slot index. |
| Split, merge or deletion | Require explicit identity migration or retirement behavior; preserve unrelated gameplay objects. |

Blender's Data Transfer modifier can copy attributes through topology or spatial mappings, making it worth testing as one recovery technique. Spatial similarity is not proof that a changed panel received the artist's intended UVs or wear pattern. [Blender Data Transfer](https://docs.blender.org/manual/en/3.6/modeling/modifiers/modify/data_transfer.html)

For frequently revised structural modules, favor repeatable mapping, trim rules and reusable surface materials. For hero assets with unique painting or baked details, make the surfacing boundary explicit and report when a new source revision invalidates that work. This is more dependable than promising arbitrary topology changes will preserve every downstream edit.

## Asset quality criteria

These are proposed acceptance criteria, to be assigned numeric budgets after the target PC and visual requirements are chosen.

| Area | Required evidence |
|---|---|
| Tessellation | Curves and bevels meet silhouette quality at expected viewing distance. Compare Rhino render meshes with the CAD translator using a curved, trimmed and multi-surface fixture. |
| Shading | Check seams, imported normals, smoothing and tangent-space normal maps under grazing light. Evaluate triangulation consistently across baking and import. |
| Modularity | Unit conversion, grid spacing, pivots, connection locations and bounds are stable. Include mirrored, nested and nonuniformly scaled instances. |
| UVs and textures | Consistent texel density, intentional trim orientation, sufficient padding and appropriate texture channels. Distinguish material UVs from any lightmap requirement. |
| Materials | Stable role mapping, intentional opacity/emissive behavior and bounded shader complexity. Verify texture color space, normal-map convention and channel packing. |
| Collision and gameplay | Traversable openings, appropriate simple collision, working interaction volumes and valid navigation after geometry changes. |
| Runtime | Measure frame time, memory, visible instance/actor counts, material cost and streaming behavior in a representative room and packaged build. |

Do not choose a universal triangle count, texture resolution or frame-rate target before the representative scene and target hardware are specified. The goal is visual quality within a measured budget. For a close-view sci-fi corridor, surface transitions, panel proportions, trim consistency and lighting response deserve as much attention as raw polygon density.

## What to take from FragmentsUnreal

The inspected implementation separates logical elements from rendering instances. Its element records include local/global identifiers and a model identifier; the actor implementation maps instance hits back to logical IDs. That is directly useful for selecting, inspecting and tracking repeated modules without requiring a full actor for every purely visual piece. These IDs still need a durable mapping back to Rhino/GH across exports. [Element records](D:/FragmentsUnreal/Source/FragmentsUnreal/Public/Utils/FragmentsUtils.h:293), [instance mapping](D:/FragmentsUnreal/Source/FragmentsUnreal/Public/Fragment/Fragment.h:180)

Its versioned sidecar keeps material replacements and placement separate from source geometry. Adapt that separation, but replace color-based source material keys with semantic material-role identities for this pipeline. The current key builder takes RGBA and a glass flag; equal colors are not reliable identifiers for different artistic roles. [Override structures and key API](D:/FragmentsUnreal/Source/FragmentsUnreal/Public/Importer/FragmentOverrides.h:10)

The async importer and frame-budget coordinator offer patterns for responsive processing and progress reporting. Reuse these ideas if profiling shows preparation or scene updates blocking the editor. A budget constant or a source comment is not a performance result for our kit. [Importer API](D:/FragmentsUnreal/Source/FragmentsUnreal/Public/Importer/FragmentsImporterSubsystem.h:43), [budget coordinator](D:/FragmentsUnreal/Source/FragmentsUnreal/Public/Utils/FrameBudgetCoordinator.h:23)

Custom streaming, HISM grouping, proxy meshes and LOD processing should be benchmarked against native Unreal alternatives before adoption. Grouping everything by rendering similarity can erase the module, material or gameplay boundaries needed for safe revisions. Static architecture and interactive objects need different treatment.

The current Fragments route is a `.frag` importer. Rook emits `.3dm` plus a JSON manifest; a direct Rhino-to-Fragments publishing path would therefore be new work. Runtime loading also introduces a packaged-file and path-management obligation. For this first modular level, a fully cooked native-asset output is the simpler candidate to qualify. [Rook export](../../src/RookNative/Handlers/GameExportHandler.cpp#L328), [Fragments load entry](D:/FragmentsUnreal/Source/FragmentsUnreal/Public/Importer/FragmentsImporterSubsystem.h:44)

## Current Rook and Engram gaps

These findings come from the inspected source revisions. They identify work to resolve before a production claim, rather than results of an end-to-end execution test.

| Finding | Evidence | Effect on the proposed workflow |
|---|---|---|
| Manifest naming mismatch | Rook writes `materialMap`, `levelPlacement`, `rhinoUuid`, `semanticType`; Engram reads snake-case equivalents. [Writer](../../src/RookNative/Handlers/GameExportHandler.cpp#L111), [reader](D:/Engram-source/Content/Python/editor/manifest_reader.py:95) | Direct handoff can miss settings and fall back from identity matching to names. Establish a versioned contract with migration/normalization rules. |
| Material-map helper lacks assignment | `_apply_material_map` initializes `assigned = 0` and returns it without assigning materials to the supplied meshes. [Implementation](D:/Engram-source/Content/Python/editor/manifest_reader.py:181) | Creating a material instance is not proof that an imported module uses it. |
| Placement settings are summarized rather than applied | The placement section reads offset/scale and may load a level after import, but does not transform the imported actors. [Implementation](D:/Engram-source/Content/Python/editor/manifest_reader.py:437) | Treat actual actor placement and target-world selection as unqualified. |
| Exposed import settings are not forwarded | Python exposes tessellation/lightmap/material controls, but calls C++ with only file and destination. C++ invokes `ImportScene`. [Python call](D:/Engram-source/Content/Python/editor/import_tools.py:70), [C++ helper](D:/Engram-source/Source/EngramEditor/Private/EngramDatasmithHelpers.cpp:12) | Do not claim quality presets work until settings reach the selected translator and are checked on output. |
| Matching/provenance centers on mesh assets | The matcher returns a mapping keyed by asset path and uses UUID/name matching. [Matcher](D:/Engram-source/Content/Python/editor/manifest_reader.py:113), [provenance function](D:/Engram-source/Content/Python/editor/manifest_reader.py:481) | Shared module definitions and placed instances need distinct records. Name fallback must report ambiguity. |
| Standalone `.3dm` construction needs qualification | The export creates a fresh `ONX_Model` and copies selected layers, materials and object geometry. [Exporter](../../src/RookNative/Handlers/GameExportHandler.cpp#L341) | Verify document units, nested block definitions, material dependencies and render-mesh availability. The inspected copying logic does not establish complete fidelity. |
| Editor orchestration must remain separate from shipped gameplay | `EngramRuntime` is declared `Editor`; `EngramEditor` is `UncookedOnly`. [Descriptor](D:/Engram-source/Engram.uplugin:16) | Author ordinary runtime assets/Blueprints for the game. Do not make packaged gameplay depend on Engram's editor services. |

Rook's existing ownership boundaries also matter: Grasshopper work and certain block-definition mutations remain companion-backed through the native bridge. Any future export or identity work touching those areas must keep the native and managed sides consistent. [Canonical Rook architecture](../../docs/CURRENT_ARCHITECTURE.md)

## Qualification before implementation

Use a small, deliberately difficult corridor fixture rather than a production level. Include a straight and curved wall, floor and ceiling tile, a beveled panel, repeated and nested blocks, a mirrored module, a multi-material door frame, an emissive strip, glass, and one uniquely surfaced hero panel. In Unreal, add a door Blueprint with an interaction trigger and saved settings, a manually moved module, a per-instance material override, collision and navigation.

Compare three bounded routes with the same source: direct Rhino Datasmith; Rhino Datasmith through Dataprep; and an optional Blender-finished asset route using one qualified exporter. Test live-link tools only after those outputs are understood, so speed can be judged against correctness.

| Test | Pass condition |
|---|---|
| Publish twice without source changes | No duplicate meshes, actors or materials; stable references and a truthful no-change report. |
| Change Rhino units or export from a different document location | Physical scale remains correct; file location is not mistaken for module identity. |
| Rename an object, move layers, reorder GH data | Existing module/instance identity survives or an explicit migration is requested. |
| Change dimensions and curvature | Expected geometry updates; placed actors, material roles and gameplay settings remain associated. |
| Change tessellation or topology | Invalid surface data is detected; the pipeline does not silently claim UV/bake preservation. |
| Reorder/add material roles | Existing roles resolve correctly and new roles are reported for mapping. |
| Add, remove, split and merge modules | Change report identifies additions and retirements without deleting unrelated gameplay work. |
| Move one instance and override one material in UE | The selected ownership policy is honored after source update and recipe rerun. |
| Change door geometry | Trigger references remain valid, and collision, traversal, hinge/socket behavior and navigation still pass. |
| Restart all applications and repeat | Identity, provenance and update settings are persisted rather than dependent on session state. |
| Re-execute Dataprep and commit | Asset paths, source associations and protected work behave as expected after recipe regeneration. |
| Cook and run without authoring applications | Assets, textures, collision and gameplay work in the packaged game without missing editor-only dependencies or source paths. |

Record source IDs, asset paths, instance associations, material-role mappings, transforms, UV/normal diagnostics, gameplay checks and before/after images. Measure first import, incremental update and preparation time separately. Compare runtime performance with a representative repeated scene, not just one module. Use Unreal's existing asset validation where possible and add targeted regression coverage only after the chosen route is concrete.

## Decisions to settle next

1. Does Rhino/GH own the overall layout, only the reusable kit, or specified regions of the level? This determines placement reconciliation.
2. Which module classes need Blender finishing, and which can use repeatable mapping and Unreal materials? This determines where topology changes become art revisions.
3. Which exact engine, Blender, exporter and plugin versions pass the fixture? Pin that combination before adopting a convenience bridge.
4. What are the reference visual quality, target PC specification, resolution and frame-time budget? These determine tessellation, material and texture budgets.
5. Which preparation operations can be expressed by Dataprep or Interchange, and what minimal coordination is still missing in Rook/Engram? Resolve the manifest and ownership contract before broad feature work.

The first deliverable after these decisions should be comparative qualification results and a chosen ownership contract. A production corridor and a larger pipeline implementation should follow that evidence.
