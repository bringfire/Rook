# Qualification Plan for Rhino Blender and Unreal

Date: 2026-10-24. Scope: modular sci-fi architecture for UE 5.8 on desktop PC.

**Decision to make:** which native Rhino, Blender and Unreal workflows preserve accepted surface work and game setup well enough to become the foundation of Rook–Engram automation. Qualify repeatable execution, selective updates and safe rejection before implementing the production pipeline.

**Status:** plan defined; fixture construction and qualification runs have not started. All cases below begin as `NOT RUN`. The dimensions and numerical limits are proposed project acceptance targets, not measured results or universal AAA standards. Freeze them before recording the baseline; any later change to a limit must be recorded and affected cases rerun.

The recommendation from the [surface comparison](2026-10-24-surface-automation-comparison.md) remains the starting hypothesis: Rhino owns geometry and mapping intent, Blender provides mesh and surface preparation where needed, and Unreal owns final materials and gameplay. Specialist tools can later use these same fixtures and checks.

## Qualification outcomes

| Outcome | Meaning | Counts toward adoption |
|---|---|---|
| Preserved | Accepted data and associations remain unchanged, apart from documented transport precision | Required for no-op, metadata and placement-only revisions |
| Regenerated | A declared recipe updates affected data and meets all quality limits; unaffected work remains unchanged | Acceptable for procedural mapping and dependent bakes |
| Repair required | The workflow identifies exactly what cannot be preserved, retains the accepted revision and prevents partial publication | Required safe behavior for ambiguous or incompatible changes; not evidence of seamless automatic handling |
| Failed | Silent loss, a wrong association, unintended changes, invalid output, or an incorrect success report | Blocks adoption for the affected asset class |
| Blocked | A required application feature, exporter, API or environment is unavailable | Leaves that route unqualified; do not count it as a pass |

A route must pass preservation tests **and** detect deliberately bad revisions. A convincing screenshot alone cannot establish preservation. Manual repair time is recorded separately, even when the final asset looks correct.

## Baseline and working conditions

Use the previously inspected Rhino **8.36.26282.15001**, Blender **5.2.1 LTS**, and installed Unreal **5.8.4**, changelist **58902052**, as the proposed baseline. Reconfirm executable paths and builds at execution time. Record exporter/importer versions, enabled plugins, GPU and driver, render settings and all import settings. An upgrade starts a new qualification baseline.

Use an isolated fixture project and private Rhino/Blender documents. Proposed future location: `D:/RookPipelineQualification/`; this plan does not create it. Preserve a baseline copy and use a separate project copy per candidate route. Never compare routes by importing them sequentially over each other's output.

Rhino document units are millimeters with absolute tolerance **0.01 mm**. Blender scene units represent meters; Unreal uses centimeters. Establish the actual axis and handedness conversion using an asymmetric labeled XYZ calibration object and a **1000 mm** ruler. Check geometry, winding and transforms after conversion rather than comparing raw matrices from different coordinate systems.

Use Lumen and a fixed exposure for the main visual scene. Start with conventional static meshes and declared normal/tangent settings. Run a separate Nanite-on variant for eligible static modules after the base route passes. Baked-lighting UVs are a separate optional test; they are not a prerequisite for a Lumen workflow.

Record a tessellation policy that targets **0.5 mm maximum surface deviation** on visible curved surfaces. Measure the resulting mesh against the source; settings alone do not prove that tolerance. Freeze triangulation before unique texture baking and retain the exported mesh used for that bake.

## Test kit

Build these seven fixtures once, then make the controlled revisions below. Each fixture has a stable definition ID, stable part IDs, semantic material roles, module-local anchors and an explicit surface policy. Give every placed copy a distinct instance ID. Names, layer paths, list positions and face indices are diagnostic labels, not identity. Record these logical IDs alongside application-native IDs in the reference manifest. For GH, author persistent semantic keys for the fixture parts; do not manufacture continuity by manually relabeling output after a failed revision.

| ID | Asset and dimensions | Surface work to establish | What it exposes |
|---|---|---|---|
| F01 | Wall panel, **2000 × 3000 × 150 mm**, with a 5 mm bevel | Rhino box/planar mapping, 100 mm labeled checker, directional metal grain and a separate mask channel | Dimension changes, density, mapping origin, polysurface seams and multiple channels |
| F02 | Trim rail, **2000 × 100 × 80 mm**, with asymmetric end caps | A shared trim strip with fixed width, longitudinal repetition and an arrow showing direction | Length changes, wrong strip selection, stretching and accidental repacking |
| F03 | Curved corner, **500 mm inner radius**, 50 mm thickness, 3000 mm high, a quarter turn joined to planar ends | Compare deliberate Rhino mapping with a Blender unwrap; mark permitted seams | Retessellation, curvature changes, distortion, normals and continuity |
| F04 | Hero access panel, **800 × 600 × 120 mm**, with a 5 mm bevel and four recessed fasteners | Blender-authored unique UVs; 2048 texture set; 12 recorded paint landmarks, including a seam-crossing scratch, serial text and local wear; bake one asymmetric raised detail | Preservation of authored UVs and textures, bakes, normal conventions and material roles |
| F05 | Nested block assembly using **four F01 panels and four F02 rails**, two nesting levels | Two ordinary placements, one rotated placement and one mirrored placement; one instance-specific Unreal material override | Definition versus instance identity, nested transforms, mirrored normals and overrides |
| F06 | Door assembly: **2000 × 3000 mm** outer frame, **1200 × 2400 mm** clear opening, **1300 × 2500 × 80 mm** sliding leaf | Body, rubber and emissive roles; leaf-local mapping; frame, leaf and interaction anchors | Persistent gameplay actor, animation, references, collision and material attachment |
| F07 | Transfer rejection coupons: two thin plates **10 mm apart**, opposite-facing surfaces, and three visually identical repeated tabs | Different labeled UV patterns on each side/tab, with recorded part identity | Nearest-surface transfer choosing the wrong side or repeated part |

Use authored diagnostic images and materials, not only a checker: labeled axes, a trim index, asymmetric tangent-space normal detail, roughness bands, a metallic mask and an emissive strip. Final Unreal materials live outside importer-owned output. Associate roles such as `body`, `seal` and `emissive` with these materials; roles need not each become a separate draw section.

Assemble a simple **8 m long × 4 m wide × 3 m high** corridor and a fixture display area. Put F06 across the corridor at X = 4 m. Reserve three named instances for transform tests: one source-owned, one Unreal-owned and one with an explicit Unreal override. Save their exact transforms in the baseline record.

### Channel contract

| Purpose | Intended Unreal channel | Rule |
|---|---|---|
| `SURFACE` | UV0 | Tile/trim mapping on F01–F03 and F06; unique layout on F04; overlap allowed only where declared |
| `MASK` | UV1 | Independent unique masks/landmarks on F01 and F04; use a visibly different diagnostic from UV0 |
| `LIGHTMAP` | UV2, only in the optional lighting variant | Unique charts, validated separately at the selected lightmap resolution |

Record source mapping IDs, Blender UV layer names and export ordering, and the resulting Unreal indices. Rhino channel numbers must not be assumed to map directly to Unreal indices. A route that drops `MASK` cannot qualify for assets requiring it, even if UV0 looks correct. Rhino mapping channels hold projection parameters and can be assigned independently to textures. [Rhino mapping reference](https://docs.mcneel.com/rhino/8/help/en-us/properties/texturemapping.htm)

### Gameplay fixture

Create a small test-only door Blueprint and place it once in the persistent gameplay level. It references imported frame/leaf meshes through persistent components; it is not a disposable actor generated by a scene import. Record an explicit qualification instance ID, the editor actor identity, component names, mesh references, attachments, collision profiles, tags, material overrides and editable properties.

Use these test values: `AccessCode = QALAB`, `OpenDistance = 140 cm`, `OpenDuration = 1.0 s`, and an external trigger referencing that exact door instance. A separate counter records open/close completion callbacks. The leaf translates along its local horizontal slide axis; its UVs and local material details must move with it. Set a distinctive editor property override so replacement with a fresh default actor is detectable.

Use a test capsule with **34 cm radius and 90 cm half-height**. Its path runs along the corridor from X = 2 m to X = 6 m, centered on the doorway. Test the same path with the door closed and open. These dimensions define this fixture's collision test, not final game design requirements.

Run timing assertions at a fixed **60 Hz simulation step**, without counting editor pauses or import time. The gameplay fixture owns trigger/capsule collision and interaction behavior; the mesh preparation recipe owns explicitly designated mesh collision only. Snapshot both so regeneration cannot erase gameplay-owned collision.

## Candidate routes

Compare each asset against its route's own accepted baseline, then compare route quality and repair cost. The direct route and Blender branch may legitimately create different initial layouts. They must meet the same surface intent and preservation checks.

| Route | Procedure to qualify | Initial scope |
|---|---|---|
| A | Rhino exporter to `.udatasmith`, then ordinary Datasmith import/reimport and explicit scene synchronization | All fixtures for import integrity; F01–F03, F05 and F06 for Rhino-owned surface work |
| B | Publish an explicit Rhino mesh to FBX; Blender imports without remeshing, preserves or authors UVs, then exports FBX to one explicitly identified Unreal importer | All fixtures; F04 is the required authored-surface branch |
| C | Route A input through a minimal Dataprep recipe, followed by repeated Execute and Commit | F01, F05 and F06 first; broaden only after identity and re-execution pass |
| D | Direct `.3dm` import using the installed Datasmith CAD translator, with its tessellation behavior recorded | F01, F03 and F05 diagnostic comparison with A; promote only if useful |

Rhino's Datasmith exporter uses Rhino tessellation settings and recognizes repeated blocks as instances. That makes A a useful baseline, but does not establish that every channel or future revision survives. [Epic Rhino integration](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-datasmith-with-rhino-in-unreal-engine)

For B, explicitly identify whether the Unreal FBX import path uses Interchange or the legacy importer; save the relevant settings. Do not combine their results under one route label. If the Rhino FBX handoff drops required channels or identity, mark that result and evaluate a separately named alternate handoff. Do not silently reconstruct missing data and count the original transfer as preserved.

C's initial recipe only selects tagged content, substitutes approved materials, organizes output and applies a declared collision policy. Disable merge, remesh, UV generation and pivot changes. Dataprep's Import, Execute and Commit stages affect temporary and committed content differently; ordinary reimport success does not establish repeated Commit behavior. [Dataprep overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/dataprep-overview-in-unreal-engine)

Keep generated scene actors in an import/staging level. Measure their identity and duplication behavior independently from the persistent gameplay level. If a route only works by replacing imported scene actors, it may still qualify as an asset-preparation route, but cannot be labeled safe for direct gameplay-level synchronization.

For Datasmith, record asset reimport and level synchronization as separate operations. Epic documents tracked overrides, scene reconciliation and limitations around overwritten mesh geometry and parent material graphs. [Datasmith reimport behavior](https://dev.epicgames.com/documentation/en-us/unreal-engine/datasmith-reimport-workflow-in-unreal-engine)

Direct Link, live editing during play, custom Fragments rendering and specialist applications are deferred until the saved-file paths pass. No live-link speed advantage can compensate for failed preservation.

## Pass and fail checks

Every check produces machine-readable measurements where practical, plus fixed-view evidence for visual properties. Establish correspondence before measuring preservation: equal vertex counts or identical names are insufficient. Compare source data, the published mesh, the Blender result and Unreal's imported source mesh at the relevant boundaries.

### Identity and geometry

| Check | Pass condition |
|---|---|
| I01 Definition and instance identity | Every expected ID resolves exactly once; renamed/reordered objects retain their associations; duplicated instances get new instance IDs; shared definitions remain shared unless an explicit mirrored variant is required |
| I02 Topology correspondence | Exact UV reuse has a verified face-corner correspondence, including seam splits. Ambiguous matches stop that reuse operation; they never fall back silently to list order or proximity |
| I03 Geometry and anchors | The 1 m ruler and module connection anchors differ by at most **0.1 mm** after conversion. Visible tessellation deviation is at most **0.5 mm**. Intended size changes match the revision; unintended geometry changes are absent |
| I04 Reference stability | Published asset references remain resolvable at their recorded paths; persistent gameplay actors/components are not deleted and recreated. A redirector alone is not proof that identity was retained |

Store normalized content fingerprints for geometry, UVs, roles and dependencies. Exclude timestamps, editor session IDs and unrelated serialization noise. Preserve exact authored UV values on unchanged source/Blender meshes; allow the documented transport tolerance below across application formats. Compare explicit samples as well as fingerprints so a bad normalization cannot conceal loss.

### UVs and surface quality

| Check | Pass condition |
|---|---|
| U01 Preserved layouts | On unchanged, corresponded regions, authored UVs are unchanged; after transport the maximum drift is **0.1 texel** at the declared texture resolution and material UV scale. No seams, islands or channels disappear |
| U02 Density and stretch | Proposed base density is **1024 texels/m** on designated visible faces. At least **95% of their surface area** is within **±5%** of the target in both principal texture directions; no non-exempt sample exceeds **±10%**. Thin bevel exceptions are marked before testing and reported separately |
| U03 Trim behavior | Strip identity is unchanged; transverse border drift is at most **0.5 texel**; rail length changes repeat along the rail, preserve strip width and preserve the anchored end's phase. Directional grain/arrows follow the recorded local axis |
| U04 Unique UV validity | No undeclared overlap, flipped charts, zero-area charts or non-finite coordinates. Unique F04 charts remain in their declared tile. Intentional mirrored/stacked regions are explicitly listed and excluded only from overlap tests |
| U05 Padding and mips | F04's 2048 layout has at least **16 base-level texels** between unrelated islands and **8 texels** to a non-wrapping tile boundary, with matching texture dilation. Inspect mips 0–3; no visible cross-island color/normal bleed. This is not a guarantee for smaller mips or every filter footprint |
| U06 Paint landmarks | All 12 F04 landmarks remain associated with the correct semantic region. On unchanged regions, UV-space drift is at most **0.5 texel**. Changed regions meet their stated new placement or are flagged for repair; serial text remains readable and correctly oriented |
| U07 Shading and bake dependencies | Tangent-space normal orientation, hard edges and allowed seams match the accepted reference in neutral and grazing light. Geometry/triangulation/tangent changes invalidate dependent bakes and require rebake or repair; stale maps cannot count as accepted output |
| U08 Moving geometry | F06's local texture landmarks stay attached through the full door travel; there is no unintended world-space swimming |

Measure density per material use, including texture dimensions and shader tiling. Use triangle-area weighting and a local UV-to-surface differential for the two principal directions. A whole-mesh average or UV packing percentage cannot pass U02 on its own. Measure trim width and longitudinal scale independently.

For preserved areas on changed geometry, define expected correspondence and exempt regions **before** evaluation. For a resized procedural wall, preserving physical texture size may require regenerated UV values; classify that as Regenerated, not exact preservation. For F04, a repack changes the relationship to painted textures and must be treated as a new surface revision.

Capture a 2048-pixel diagnostic view with fixed camera, exposure and unlit material outputs, plus close and grazing-light views under the game material. Compare unchanged masks/landmarks numerically. Temporal lighting screenshots support review but are not tested with a blanket pixel-equality rule. The user acts as art reviewer for visible seam quality and readability; AI inspection supplies annotations, not sole approval.

### Materials and placement

| Check | Pass condition |
|---|---|
| M01 Role association | Every semantic region resolves to the intended Unreal material. Reordering slots or changing labels cannot swap body, seal and emissive surfaces |
| M02 Authored materials | Material graph, instance parameters, texture references and per-instance overrides outside import ownership remain unchanged unless explicitly revised. Missing roles produce a named failure rather than a default-material substitution |
| M03 Texture interpretation | Declared color-space settings, normal convention, channel packing, compression and material UV channel selection match the baseline. Diagnostic roughness/metal/emissive values appear in the intended channels |
| P01 Transform ownership | Geometry-only updates change no instance transforms. Source-owned moves apply once; Unreal-owned transforms remain unchanged. Conflicting edits to an override produce a conflict report before publication |
| P02 Transform accuracy | Position and anchor error is at most **0.1 mm**, rotation error at most **0.01°**, and relative scale error at most **0.00001** after conversion. Check local and world transforms, parents, pivots and mirror parity |
| P03 Scene integrity | No duplicate actors/components, unintended meshes/materials, unexpected parent changes or unintended deletions. Expected new parts are enumerated; removed parts with downstream references require explicit disposition |

### Gameplay and recovery

| Check | Pass condition |
|---|---|
| G01 Persistent setup | Door actor identity, persistent components, external trigger reference, tags, editable values, attachments and collision profiles survive import, synchronization, save and reopen |
| G02 Door behavior | Locked interaction does not open the door. One valid interaction opens it once, travels **140 cm ±0.1 cm** in **1.0 s ± one simulation frame**, and produces one completion callback. Close works identically. Twenty cycles produce exactly twenty open and twenty close callbacks |
| G03 Collision | The capsule is blocked by the closed door and passes the open doorway; it never clips through frame/wall surfaces. Mesh revisions update geometry-dependent collision or block acceptance pending repair. Existing gameplay collision ownership is respected |
| G04 Dependent setup | Declared sockets/anchors and child attachments remain correct. A removed attachment anchor or insufficient clearance is reported before acceptance. If navigation is enabled, a dedicated path test must reflect the declared door/navigation policy after rebuild |
| G05 Packaged behavior | A Windows packaged fixture build loads the revised assets and passes G02/G03 with Rhino, Blender, Rook and Engram services stopped. Editor-only success is insufficient |
| R01 Repeatability | Three runs from the same baseline and inputs produce equal normalized results within declared float tolerances, including one run after application restart. No duplicate side effects occur |
| R02 Failure and rollback | Interrupted or failed processing leaves the accepted revision usable. No mixed mesh/UV/material revision is published. Restoring the previous accepted revision restores references, surfaces and gameplay behavior |

The target is editor revision preservation, not retention of transient in-play door state during a hot update. Gameplay tests start from a defined state. Compare stable IDs, object paths and properties across restart, not process memory addresses.

## Controlled revision matrix

Reset to the accepted baseline before each independent test. Then run the cumulative sequence listed afterward. Apply the same edits to each eligible route; keep expected outcomes and affected regions in a revision record.

| Case | Exact change | Expected result and required checks |
|---|---|---|
| T00 | Initial import and authored baseline | Establish all applicable I/U/M/P/G checks. A broken initial asset cannot become the preservation reference |
| T01 | Save/export/reimport with no semantic change, three times | Preserve all accepted content and associations; report redundant work separately. I01–I04, U01, M01–M03, P01–P03, R01 |
| T02 | Rename F01 and its layer; reorder exported objects and material slots | Identity, masks and assignments remain correct. I01/I02, U01, M01, P03 |
| T03 | Move one source-owned instance **1000 mm** and rotate it **90°**; rerun | Only that instance changes, exactly once. Surface artifacts remain unchanged. P01/P02, U01/U08 |
| T04 | Move an Unreal-owned instance; make conflicting source and Unreal edits on the overridden instance | Preserve Unreal ownership; report the conflict; no partial application. P01–P03, R02 |
| T05 | Increase F01 width **2000 → 2400 mm**, retaining its reference edge | Regenerate procedural mapping at the same physical scale; preserve roles and placements. I03, U02, M01, P01 |
| T06 | Extend F02 **2000 → 3000 mm**, keeping its first end fixed | Preserve trim width, strip and phase; extend longitudinal repetition. U02/U03, M01 |
| T07 | Change only F03 tessellation to produce more triangles | Same shape within tolerance; semantic roles survive. Reuse UVs only with proven correspondence, otherwise regenerate or flag repair. I02/I03, U01/U02/U07 |
| T08 | Change F03 radius **500 → 650 mm**, fixing the first end's anchor and tangent; derive the far end's new anchor from the revised quarter turn | The first anchor stays fixed and the far anchor matches the revised source; validate unwrap quality and normals. No silent stretch or false exact-preservation claim. I03, U02/U07 |
| T09 | Change F04 bevel **5 → 10 mm** and add a **40 × 40 mm** cutout in a premarked blank region | Unaffected paint/roles remain; affected UVs and bakes regenerate or produce precise repair regions. U01/U04/U06/U07, M01, R02 |
| T10 | Add a **40 × 40 mm** raised plate to F04 as a new island, then separately attempt a full repack | Adding may use free space only if locked islands and quality limits survive. Repacking a painted layout must require texture migration/new surface acceptance; never accept stale textures. U01/U04–U07 |
| T11 | Swap material slot order without changing roles; separately rename a role without a migration | First edit preserves associations; second produces a missing-role conflict. M01/M02, R02 |
| T12 | Recompute GH output, insert an item before existing items and reorder branches | Existing logical parts retain IDs despite changed list positions; the new item alone gets a new ID. Ambiguity stops publication. I01/I02, P03 |
| T13 | Delete and recreate a source part with the same name; separately duplicate a part carrying a copied ID | No name-based accidental reassociation; duplicate IDs are rejected. Explicit identity migration is required where continuity is intended. I01, I04, R02 |
| T14 | Increase one nested F02 rail length **2000 → 2100 mm**, move one child **100 mm** along local X, and reflect one assembly placement across its local YZ plane | Correct definition updates and composed transforms; unaffected instances retain overrides. I01, U07, M02, P01–P03 |
| T15 | Increase F06 leaf thickness **80 → 100 mm**; separately remove an attachment anchor or narrow the clear opening to **600 mm** | Compatible update preserves setup and passes door tests. Incompatible update stops with the precise anchor/clearance failure. G01–G04, R02 |
| T16 | Transfer F07 UVs after reordering tabs and moving one plate **6 mm** toward the other plate's old position | Correct semantic correspondence or explicit rejection; no opposite-side/neighbor leakage. I02, U01/U06, R02 |
| T17 | Express identical geometry in meters instead of millimeters; separately omit units | Declared conversion yields the same physical result. Missing units blocks processing rather than guessing. I03, U02, P02 |
| T18 | Remove an instance with an Unreal override or gameplay reference | Report pending removal and affected references; keep accepted gameplay intact until disposition. I04, M02, P03, G01 |
| T19 | Interrupt after export, after Blender processing, and during Unreal staging/commit; restart and retry | Reconcile operation status, retain/restore accepted content and avoid duplicates. Ambiguous completion must be inspected before retry. R01/R02, I04, G01 |

For C, run T01–T04 and T14/T15 by repeating the **full Dataprep Execute and Commit** operation, not by substituting ordinary reimport. Run both asset update and scene synchronization for routes that claim layout synchronization.

Run a cumulative sequence **T02 → T05 → T06 → T14 → T15 compatible change → T01**, save and reopen, then package and test. Also restore the original accepted revision and rerun G01–G03. Independent passes do not demonstrate that repeated revisions compose correctly.

## AI execution contract

Qualification begins with recorded native procedures and minimal disposable measurement scripts where needed. Production adapters, public skills and orchestration are built only after the route decisions. The scripts are test instruments, not an assumed existing Rook–Engram feature.

For each check, record whether the application enforces it natively, a test script detects it, or a human performs it. A manually detected conflict can establish the required policy and expose a missing adapter, but cannot qualify automatic conflict handling. Likewise, manually restoring a project proves the recovery procedure, not unattended recovery. Report native capability and remaining automation work separately.

| Step | Inputs and preconditions | Required result |
|---|---|---|
| Inspect | Explicit document/project, accepted revision, source IDs, units and ownership | Classified change list, dependencies and identity conflicts |
| Prepare | Recorded recipe/version, exact settings and validated representation | Candidate mesh/surface artifacts; preserved and invalidated regions listed |
| Import and stage | Candidate artifact hashes, destination mapping and known importer settings | Completed import with asset/channel/material/reference measurements |
| Verify | Case ID and its expected result | Actual measurements, visual evidence, gameplay outcomes and failures |
| Accept or reject | All required checks resolved | One consistent accepted revision, or unchanged previous revision with a repair report |

The AI selects an eligible recipe and supplies bounded inputs. Executors perform the recorded operations. No new freeform workflow is generated during a rerun. Recipe edits, solver changes and changed import settings create a new version and rerun affected qualification cases.

Wait for actual application readiness and operation completion, verify outputs, and serialize dependent mutations per application session. Timeouts must record whether the operation is still running. Retrying an unknown mutation without reconciliation fails R02. Accepted output reuse is preferred for unchanged inputs; record cache reuse separately from a cold rebuild.

For every run, retain: route and case IDs; app/plugin builds; source and accepted revisions; input/output hashes; definition/instance/part mappings; ownership; UV/channel/role associations; recipe parameters; expected versus actual changes; check measurements; screenshots; gameplay logs; warnings; wall time and active artist minutes; and the final outcome. Case IDs are permanent so failures can become future regression tests.

Logical fingerprints cover source geometry, tessellation, UV layouts, material roles, textures, bakes and placement independently. A placement-only change must not invalidate the texture set. A changed bake dependency must invalidate its maps even when the UV fingerprint is unchanged.

## Execution order and adoption gates

| Gate | Work | Exit condition |
|---|---|---|
| 0 | Freeze environment, fixture definitions, ownership, thresholds and measurement methods | No ambiguous units, identities, target applications or expected results |
| 1 | Build T00 references and run A/B first-import checks; screen C/D | Each continuing route imports its required channels, roles and geometry correctly |
| 2 | Run T01–T08 and T11–T14/T17 | Routine changes preserve identity and downstream work; procedural assets update without surface repair |
| 3 | Run T09/T10/T16 and dependent bake checks | Authored surfaces survive compatible edits; incompatible changes are identified before publication |
| 4 | Run T15/T18/T19, cumulative revisions, reopen, rollback and packaged tests | Gameplay, recovery and persistent references survive the entire lifecycle |
| 5 | Compare accepted quality, artist repair time, execution cost and runtime cost | Select routes by asset class and list the smallest missing capabilities worth implementing |

Stop a route at the earliest structural failure and record the cause. Continue independent routes. Do not build a custom workaround merely to hide a failed native baseline; log the required adapter separately so its cost informs the decision.

All supported routine revisions must pass their required checks. No lost materials, incorrect UV associations, replaced gameplay actors, broken references, transform resets or partial commits are acceptable. Compatible authored revisions must retain unaffected work; topology changes may legitimately require local repair, whose extent and time must be reported.

A correctly rejected negative test passes the safety check but does not count as automatic revision support. Report the supported revision classes explicitly. A route that rejects every edit is safe but does not meet the seamless-workflow objective.

Record cold and warm update time, manual interventions, affected/rebuilt asset counts, triangle counts, draw sections, texture residency and GPU frame time on a fixed corridor camera path. Require **zero active artist repair minutes** for no-op, metadata, placement-only and accepted procedural dimension changes. Use measurements to set later performance budgets; the unknown target GPU makes a universal frame-time pass limit premature.

Choose the simplest route that passes for each asset class: direct Rhino for procedural modules where successful, the Blender branch for authored surface work, and Dataprep where repeated execution preserves the required assets and associations. Retain a single authoritative accepted surface representation per asset revision.

The qualification results should produce a supported-workflow table, an exception/repair list and a prioritized implementation backlog. The existing [repository audit](2026-10-24-rhino-blender-unreal-pipeline-research.md) already identifies Rook–Engram manifest, material assignment and import-setting gaps; keep those adapter defects separate from native application failures. Only after the baseline results should we decide which gaps to fix, which native facilities to orchestrate and whether a specialist tool materially improves the weak asset classes.
