# Modular Plaza Café Chirp Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an editable Grasshopper definition in the active empty document where a five-node Chirp cascade produces validated architectural parameters that drive a deterministic modular café frame, operable secure shell, and coffee fitout.

**Architecture:** A planner Chirp fans shared reasoning into security, operations, and public-realm interpreters; a critic reads all reasoning streams. Typed outputs pass through one ordinary Grasshopper C# contract guard before three ordinary C# geometry builders. A manual `OpenForService` toggle transforms the same façade panels between a flush secure shell and operating canopies/counters without invoking the LLM.

**Tech Stack:** Rhino 8, Grasshopper, Rook `chirp_create`, Rook `gh_edit`, RhinoCode C# script components, RhinoCommon geometry, ordinary Grasshopper Panels/sliders/toggle/groups.

## Global Constraints

- Deliverable is the live editable Grasshopper definition; repository code is not the product.
- Target document is the active unnamed Grasshopper document with document id `551c7ab3-7c7d-449a-b498-0221e72c0153`, admitted empty during planning.
- The recorded planning epoch is advisory only; every mutation batch requires a fresh execution-time snapshot and epoch.
- Preserve any content that appears after the empty baseline unless the user explicitly authorizes changing it.
- Do not bake Rhino geometry.
- Use Chirp only for reasoning and typed parameters; use ordinary C# script nodes for deterministic geometry.
- `OpenForService` bypasses Chirp and controls only the operable-shell transformation.
- Geometry builders consume only resolved contract values, never raw generative values.
- Treat unavailable Rhino, Grasshopper, Chirp adapter, hidden script tools, or unresolved solver state as stop conditions.
- Inspect `partial_success` operation-by-operation; record committed IDs and never replay committed mutations.
- Apply at most one bounded correction per failed dependency from fresh live evidence.

---

### Task 1: Re-admit the Grasshopper target and create ordinary controls

**Files:**
- Reference: `docs/superpowers/specs/2026-08-13-plaza-cafe-chirp-cascade-design.md`
- Modify: active Grasshopper document only

**Interfaces:**
- Consumes: active Rhino/Grasshopper host, empty structural baseline.
- Produces: six ordinary controls with committed component IDs: `DesignBrief`, `SiteWidthLimitM`, `SiteDepthLimitM`, `MaxHeightM`, `TargetCupsPerHour`, `OpenForService`.

- [ ] **Step 1: Re-admit host and canvas**

Call `rhino_ping`, hidden `gh_status`, and `gh_snapshot`. Require the same active unnamed document, solver enabled, `ready_for_edit=true`, and zero components. Stop for semantic drift if the document identity or ownership boundary changed.

- [ ] **Step 2: Create controls in one bounded `gh_edit` batch**

Use a fresh epoch and these exact controls/positions:

```json
[
  {"temp_id":"T1","type":"panel","content":"Design a standalone modular café pop-up for a public plaza beside a large high-rise complex. Create a contemporary, durable kiosk whose repeated construction modules are integral to coffee service. During operating hours, upper façade panels fold upward as weather canopies and lower panels fold downward as serving counters. After hours, those panels close into a secure flush shell. Prioritize rapid assembly, legible modularity, efficient staff workflow, approachable public frontage, and a calm architectural presence appropriate to a major urban plaza.","pos":[40,180]},
  {"temp_id":"T2","type":"slider","nick":"SiteWidthLimitM","min":4.0,"max":12.0,"value":7.2,"pos":[40,360]},
  {"temp_id":"T3","type":"slider","nick":"SiteDepthLimitM","min":3.0,"max":8.0,"value":4.8,"pos":[40,420]},
  {"temp_id":"T4","type":"slider","nick":"MaxHeightM","min":2.6,"max":5.0,"value":3.6,"pos":[40,480]},
  {"temp_id":"T5","type":"slider","nick":"TargetCupsPerHour","min":20,"max":180,"value":80,"pos":[40,540]},
  {"temp_id":"T6","type":"toggle","nick":"OpenForService","value":true,"pos":[40,620]}
]
```

- [ ] **Step 3: Verify committed controls**

Inspect `edit_summary.temp_id_map`, refresh `gh_snapshot`, and record the six short IDs. Require six objects, no errors, and exact displayed values.

### Task 2: Create the five Chirps and wire the reasoning cascade

**Files:**
- Reference: `docs/superpowers/specs/2026-08-13-plaza-cafe-chirp-cascade-design.md`
- Modify: active Grasshopper document only

**Interfaces:**
- Consumes: six control IDs from Task 1.
- Produces: five Chirp IDs, exact declared pins plus auto-added `Correction` and `Reasoning`, five reasoning Panels, two critic review Panels, and verified reasoning topology.

- [ ] **Step 1: Create Chirps in dependency order with `chirp_create`**

Use the exact component names, positions, categories, pins, and signatures:

```yaml
Café Planner @ [420, 250]:
  category: planner
  pins_in: [DesignBrief:string, SiteWidthLimitM:float, SiteDepthLimitM:float, MaxHeightM:float]
  pins_out: [KioskWidthM:float, KioskDepthM:float, KioskHeightM:float, BayCount:int]
  signature: design_brief, site_width_limit_m, site_depth_limit_m, max_height_m -> kiosk_width_m, kiosk_depth_m, kiosk_height_m, bay_count

Modular Security Designer @ [760, 60]:
  category: interpreter
  pins_in: [PlannerReasoning:string, KioskWidthM:float, BayCount:int]
  pins_out: [BayWidthM:float, FrameSectionM:float, PanelThicknessM:float, LockingZoneCount:int, UpperPanelOpenAngleDeg:float, LowerPanelOpenAngleDeg:float]
  signature: planner_reasoning, kiosk_width_m, bay_count -> bay_width_m, frame_section_m, panel_thickness_m, locking_zone_count, upper_panel_open_angle_deg, lower_panel_open_angle_deg

Coffee Operations Planner @ [760, 330]:
  category: interpreter
  pins_in: [PlannerReasoning:string, TargetCupsPerHour:int, KioskDepthM:float]
  pins_out: [CounterHeightM:float, CounterDepthM:float, ServiceOpeningWidthM:float, EquipmentRunLengthM:float, StaffAisleWidthM:float, StorageDepthM:float]
  signature: planner_reasoning, target_cups_per_hour, kiosk_depth_m -> counter_height_m, counter_depth_m, service_opening_width_m, equipment_run_length_m, staff_aisle_width_m, storage_depth_m

Public-Realm Architect @ [760, 600]:
  category: interpreter
  pins_in: [PlannerReasoning:string, KioskHeightM:float, KioskWidthM:float, BayCount:int]
  pins_out: [CanopyProjectionM:float, SignageBandHeightM:float, FacadeRevealDepthM:float, PlazaSetbackM:float, OpenTransparencyRatio:float, MaterialStrategy:string]
  signature: planner_reasoning, kiosk_height_m, kiosk_width_m, bay_count -> canopy_projection_m, signage_band_height_m, facade_reveal_depth_m, plaza_setback_m, open_transparency_ratio, material_strategy

Coordination Critic @ [1120, 790]:
  category: critic
  pins_in: [PlannerReasoning:string, SecurityReasoning:string, OperationsReasoning:string, PublicRealmReasoning:string]
  pins_out: [Coherent:bool, Issues:string, Recommendations:string, PlazaCafeFitnessScore:float]
  signature: planner_reasoning, security_reasoning, operations_reasoning, public_realm_reasoning -> coherent, issues, recommendations, plaza_cafe_fitness_score
```

After each creation, capture a fresh snapshot, identify the new component by nickname, record its full and short IDs, and verify the actual pin ordering before creating the next dependency.

- [ ] **Step 2: Create reasoning and review Panels**

Create one Panel immediately to the right of each Chirp for `Reasoning`, plus `Issues` and `Recommendations` Panels to the right of the critic. Record their committed IDs.

- [ ] **Step 3: Wire controls, typed dependencies, reasoning fan-out, and review Panels**

Construct flow strings from the fresh snapshot's actual parameter indices, not assumed indices. Required semantic connections are:

```text
DesignBrief -> Café Planner.DesignBrief
SiteWidthLimitM -> Café Planner.SiteWidthLimitM
SiteDepthLimitM -> Café Planner.SiteDepthLimitM
MaxHeightM -> Café Planner.MaxHeightM
Café Planner.Reasoning -> each specialist.PlannerReasoning
Café Planner.Reasoning -> Coordination Critic.PlannerReasoning
Café Planner.KioskWidthM -> Modular Security Designer.KioskWidthM
Café Planner.BayCount -> Modular Security Designer.BayCount
TargetCupsPerHour -> Coffee Operations Planner.TargetCupsPerHour
Café Planner.KioskDepthM -> Coffee Operations Planner.KioskDepthM
Café Planner.KioskHeightM -> Public-Realm Architect.KioskHeightM
Café Planner.KioskWidthM -> Public-Realm Architect.KioskWidthM
Café Planner.BayCount -> Public-Realm Architect.BayCount
each specialist.Reasoning -> matching Coordination Critic reasoning input
each Chirp.Reasoning -> its dedicated Panel
Coordination Critic.Issues -> Issues Panel
Coordination Critic.Recommendations -> Recommendations Panel
```

- [ ] **Step 4: Checkpoint the cascade**

Poll `gh_status` to a fixed timeout, then inspect `gh_errors` and `gh_snapshot`. Require every requested flow to exist. Chirp inference may still be running; distinguish expected transient empty outputs from compile, adapter, or wiring errors.

### Task 3: Create and validate the deterministic contract guard

**Files:**
- Modify: active Grasshopper document only

**Interfaces:**
- Consumes: all raw numeric Chirp outputs plus site limits.
- Produces: `ResolvedKioskWidthM:double`, `ResolvedKioskDepthM:double`, `ResolvedKioskHeightM:double`, `ResolvedBayCount:int`, `ResolvedBayWidthM:double`, `ResolvedFrameSectionM:double`, `ResolvedPanelThicknessM:double`, `ResolvedLockingZoneCount:int`, `ResolvedUpperPanelOpenAngleDeg:double`, `ResolvedLowerPanelOpenAngleDeg:double`, `ResolvedCounterHeightM:double`, `ResolvedCounterDepthM:double`, `ResolvedServiceOpeningWidthM:double`, `ResolvedEquipmentRunLengthM:double`, `ResolvedStaffAisleWidthM:double`, `ResolvedStorageDepthM:double`, `ResolvedCanopyProjectionM:double`, `ResolvedSignageBandHeightM:double`, `ResolvedFacadeRevealDepthM:double`, `ResolvedPlazaSetbackM:double`, `ResolvedOpenTransparencyRatio:double`, and `ContractStatus:string`; later builders consume only these outputs.

- [ ] **Step 1: Create `Café Contract Guard` with `gh_create_csharp_script` at `[1410, 290]`**

Define item-access inputs for the three site limits and every raw numeric output listed in the spec. Define item-access outputs using the same semantic names prefixed `Resolved`, plus `ContractStatus:string`.

- [ ] **Step 2: Implement exact deterministic normalization**

The C# body must use finite-value fallbacks and these formulas:

```csharp
resolvedWidth = Clamp(rawWidth, 4.0, siteWidthLimit, 7.2);
resolvedDepth = Clamp(rawDepth, 3.0, siteDepthLimit, 4.8);
resolvedHeight = Clamp(rawHeight, 2.6, maxHeight, 3.6);
resolvedBayCount = ClampInt(rawBayCount, 2, 6, 4);
resolvedBayWidth = resolvedWidth / resolvedBayCount;
resolvedFrameSection = Clamp(rawFrameSection, 0.06, 0.20, 0.10);
resolvedPanelThickness = Clamp(rawPanelThickness, 0.03, Math.Min(0.12, resolvedFrameSection * 0.9), 0.06);
resolvedServiceOpening = Clamp(rawServiceOpening, 0.8, Math.Max(0.8, resolvedBayWidth - 2.0 * resolvedFrameSection), Math.Max(0.8, resolvedBayWidth - 2.0 * resolvedFrameSection));
resolvedCounterHeight = Clamp(rawCounterHeight, 0.85, 1.10, 0.95);
resolvedCounterDepth = Clamp(rawCounterDepth, 0.45, 0.80, 0.60);
resolvedStaffAisle = Clamp(rawStaffAisle, 0.90, Math.Max(0.90, resolvedDepth - resolvedCounterDepth - 0.50), 1.10);
resolvedEquipmentRun = Clamp(rawEquipmentRun, 1.20, Math.Max(1.20, resolvedWidth - 0.60), Math.Max(1.20, resolvedWidth - 0.80));
resolvedStorageDepth = Clamp(rawStorageDepth, 0.35, 0.75, 0.55);
resolvedUpperAngle = Clamp(rawUpperAngle, 70.0, 110.0, 92.0);
resolvedLowerAngle = Clamp(rawLowerAngle, 70.0, 100.0, 90.0);
resolvedCanopy = Clamp(rawCanopy, 0.70, 1.80, 1.20);
resolvedSignageBand = Clamp(rawSignageBand, 0.25, 0.65, 0.40);
resolvedReveal = Clamp(rawReveal, 0.03, 0.30, 0.10);
resolvedSetback = Clamp(rawSetback, 1.50, 6.00, 3.00);
resolvedTransparency = Clamp(rawTransparency, 0.25, 0.85, 0.55);
resolvedLockingZones = ClampInt(rawLockingZones, 2, 8, resolvedBayCount + 1);
```

Record every fallback or clamp in `ContractStatus`. Never emit NaN, infinity, negative dimensions, or an opening wider than its bay.

- [ ] **Step 3: Wire raw values to the guard and verify outputs**

Use a fresh snapshot to resolve actual pin indices, connect all required raw values, poll solver state, and inspect the guard output preview. Require finite values, resolved width/depth/height within site limits, and exact `ResolvedBayWidthM = ResolvedKioskWidthM / ResolvedBayCount`.

### Task 4: Create the three ordinary C# geometry builders

**Files:**
- Modify: active Grasshopper document only

**Interfaces:**
- Consumes: only resolved contract outputs, `TargetCupsPerHour`, and direct `OpenForService`.
- Produces: RhinoCommon Breps, planes, curves, fitout status, and editable Grasshopper preview geometry.

- [ ] **Step 1: Create `Kiosk Frame` at `[1920, 120]`**

Inputs: resolved width, depth, height, bay count, bay width, frame section, façade reveal, signage-band height. Outputs: `FrameBreps:list`, `PlinthBrep:item`, `BayPlanes:list`, `FixedShellBreps:list`, `FootprintCurve:item`.

Implement a world-XY kiosk from `(0,0,0)` to `(W,D,H)`. Use `Rhino.Geometry.Box(...).ToBrep()` for a 0.15 m plinth, front/back modular posts at every bay boundary, front/back perimeter beams, back and side shell panels, roof skin, and a front signage band. Emit one front-facing `Plane` per bay and a closed rectangular footprint curve.

- [ ] **Step 2: Compile and verify `Kiosk Frame` before downstream work**

Poll solver state and inspect `gh_errors`. Require nonempty frame, plinth, bay-plane, shell, and footprint outputs with bay-plane count equal to resolved bay count.

- [ ] **Step 3: Create `Operable Shell` at `[1920, 480]`**

Inputs: `BayPlanes:list`, resolved kiosk dimensions, bay width, panel thickness, service-opening width, counter height, upper/lower angles, canopy projection, locking-zone count, and `OpenForService`. Outputs: `UpperPanelBreps:list`, `LowerPanelBreps:list`, `ServiceCounterBreps:list`, `HingeAxisCurves:list`, `LockingZoneBreps:list`, `SecurityEnvelopeBreps:list`.

For each bay, create upper and lower front-panel boxes centered on the bay. Use the upper panel's top edge and lower panel's counter-height edge as X-axis hinges. When open, rotate both panels outward about those axes by the negative resolved angles; publish transformed lower panels as serving counters. When closed, leave both vertical and publish them together as the security envelope plus conceptual locking blocks at panel junctions. Preserve panel count and base dimensions across states.

- [ ] **Step 4: Compile and verify both shell states**

With `OpenForService=true`, require upper/lower panel counts equal to bay count and service-counter count equal to bay count. Toggle false using `gh_edit.set_values`; require zero service counters, nonempty security envelope and locking zones, then restore true.

- [ ] **Step 5: Create `Coffee Fitout` at `[1920, 850]`**

Inputs: resolved kiosk dimensions, counter height/depth, equipment-run length, staff-aisle width, storage depth, service-opening width, plaza setback, and `TargetCupsPerHour`. Outputs: `WorkCounterBreps:list`, `EquipmentPlaceholderBreps:list`, `StorageBreps:list`, `StaffZoneCurve:item`, `CustomerQueueZoneCurve:item`, `FitoutStatus:string`.

Create an internal back work counter, three simple equipment blocks sized along the guarded equipment run, under-counter storage, a staff-zone rectangle inside the shell, and an exterior customer queue rectangle offset by the resolved plaza setback. Report actual clearances and throughput target in `FitoutStatus`.

- [ ] **Step 6: Compile and verify fitout containment**

Require nonempty work counter, three equipment placeholders, storage, both zone curves, and a status string. Check all fitout solids remain within the kiosk width/depth/height and that the staff-zone width is at least the guarded aisle width.

### Task 5: Organize, stress-test, and finalize the definition

**Files:**
- Modify: active Grasshopper document only

**Interfaces:**
- Consumes: all execution-owned IDs and verified flows from Tasks 1–4.
- Produces: seven execution-owned groups, final restored controls, zero unresolved errors, and a verified final snapshot.

- [ ] **Step 1: Create seven groups from current committed IDs**

Use a fresh epoch and create exactly:

```text
01 — Brief + Constraints
02 — Chirp Design Cascade
03 — Geometry Contract
04 — Modular Frame
05 — Operable Secure Shell
06 — Coffee Fitout
07 — Review + Critic
```

The second group contains the planner, three specialists, and their local Reasoning Panels. The seventh contains only the critic and review Panels. Do not group pre-existing objects.

- [ ] **Step 2: Verify default reasoning and geometry**

Poll to a fixed timeout, inspect `gh_errors`, and capture output previews. Require all five Chirps to compile, all deterministic scripts to compile, all required flows to exist, and open-state geometry to be nonempty.

- [ ] **Step 3: Run contrasting-brief test**

Set `DesignBrief` temporarily to: `Design a compact high-throughput transit-hub coffee kiosk with minimal dwell time, robust vandal-resistant closure, and restrained industrial expression.` Wait for inference to settle and confirm specialist reasoning or typed outputs change from the default scenario.

- [ ] **Step 4: Restore approved default state**

Restore the exact approved plaza café brief and `OpenForService=true`. Wait for the solver and Chirp inferences to settle.

- [ ] **Step 5: Final verification**

Capture a fresh `gh_snapshot`, `gh_errors`, and `gh_status`. Require the expected component/group counts, complete topology, zero unresolved errors, finite contract previews, nonempty frame/shell/fitout geometry, restored default brief, and open state. Report any warning that is genuinely advisory rather than claiming a clean result.
