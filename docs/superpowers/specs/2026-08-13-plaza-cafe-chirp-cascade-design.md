# Modular Plaza Café Chirp Cascade Design

## Goal

Create a coordinated Chirp reasoning cascade and deterministic Grasshopper geometry system for a standalone café pop-up in a public plaza near a large high-rise complex. The design must read as contemporary architecture while making its modular construction and daily operations visibly useful: the same repeated façade modules that secure the kiosk after hours become canopies and serving counters when it opens.

The first implementation produces editable conceptual geometry in Grasshopper. It is not a fabrication, structural-engineering, accessibility, fire-safety, food-service, or certified security package.

## Live Target and Preservation Boundary

- Target the active, unnamed, empty Grasshopper document admitted during preflight.
- Re-admit the live document immediately before mutation and use its fresh epoch.
- Create only the cascade, controls, reasoning panels, deterministic geometry components, previews, and groups described here.
- Treat every created component as execution-owned and maintain an ID ledger throughout execution.
- Preserve any content that appears after the empty baseline unless the user explicitly authorizes its modification.
- Do not bake Rhino geometry in this first version.

## Default Design Brief

> Design a standalone modular café pop-up for a public plaza beside a large high-rise complex. Create a contemporary, durable kiosk whose repeated construction modules are integral to coffee service. During operating hours, upper façade panels fold upward as weather canopies and lower panels fold downward as serving counters. After hours, those panels close into a secure flush shell. Prioritize rapid assembly, legible modularity, efficient staff workflow, approachable public frontage, and a calm architectural presence appropriate to a major urban plaza.

## User Controls

Create the following ordinary Grasshopper controls at the left of the definition:

| Control | Type | Default | Range | Consumer |
|---|---|---:|---:|---|
| `DesignBrief` | Panel | Default brief above | n/a | Café Planner |
| `SiteWidthLimitM` | Slider | 7.2 | 4.0–12.0 | Café Planner, contract guard |
| `SiteDepthLimitM` | Slider | 4.8 | 3.0–8.0 | Café Planner, contract guard |
| `MaxHeightM` | Slider | 3.6 | 2.6–5.0 | Café Planner, contract guard |
| `TargetCupsPerHour` | Slider | 80 | 20–180, integer | Coffee Operations Planner |
| `OpenForService` | Toggle | `true` | n/a | Operable Shell only |

`OpenForService` is deliberately deterministic and bypasses the LLM cascade. The cascade decides dimensions and operating requirements; the user controls the current physical state.

## Cascade Topology

Use a hybrid fan-out-plus-critic topology:

```text
Design brief + site limits
          |
     Café Planner
          |
          +-- Reasoning --> Modular Security Designer -- Reasoning --+
          +-- Reasoning --> Coffee Operations Planner  -- Reasoning --+--> Coordination Critic
          +-- Reasoning --> Public-Realm Architect      -- Reasoning --+
          +----------------------------------------------------------+

Typed numerical outputs --> deterministic contract guard --> C# geometry builders
```

Reasoning carries shared intent. Typed numerical outputs form the geometry contract. The critic is advisory and visible; it does not inject nondeterministic values into the geometry path.

## Chirp Components and Signatures

Every Chirp receives the standard auto-added optional `Correction` input and auto-added `Reasoning` output. Neither is declared manually.

### 1. Café Planner

- Category: `planner`
- Inputs:
  - `DesignBrief:string`
  - `SiteWidthLimitM:float`
  - `SiteDepthLimitM:float`
  - `MaxHeightM:float`
- Outputs:
  - `KioskWidthM:float`
  - `KioskDepthM:float`
  - `KioskHeightM:float`
  - `BayCount:int`
- Signature: `design_brief, site_width_limit_m, site_depth_limit_m, max_height_m -> kiosk_width_m, kiosk_depth_m, kiosk_height_m, bay_count`
- Role: establish the shared concept, footprint, overall height, and repeated-bay rhythm while respecting the user-supplied site envelope.

### 2. Modular Security Designer

- Category: `interpreter`
- Inputs:
  - `PlannerReasoning:string`
  - `KioskWidthM:float`
  - `BayCount:int`
- Outputs:
  - `BayWidthM:float`
  - `FrameSectionM:float`
  - `PanelThicknessM:float`
  - `LockingZoneCount:int`
  - `UpperPanelOpenAngleDeg:float`
  - `LowerPanelOpenAngleDeg:float`
- Signature: `planner_reasoning, kiosk_width_m, bay_count -> bay_width_m, frame_section_m, panel_thickness_m, locking_zone_count, upper_panel_open_angle_deg, lower_panel_open_angle_deg`
- Role: translate modular and after-hours security intent into a repeated frame and transformable-panel system. Locking zones are conceptual geometric indicators, not certified security hardware.

### 3. Coffee Operations Planner

- Category: `interpreter`
- Inputs:
  - `PlannerReasoning:string`
  - `TargetCupsPerHour:int`
  - `KioskDepthM:float`
- Outputs:
  - `CounterHeightM:float`
  - `CounterDepthM:float`
  - `ServiceOpeningWidthM:float`
  - `EquipmentRunLengthM:float`
  - `StaffAisleWidthM:float`
  - `StorageDepthM:float`
- Signature: `planner_reasoning, target_cups_per_hour, kiosk_depth_m -> counter_height_m, counter_depth_m, service_opening_width_m, equipment_run_length_m, staff_aisle_width_m, storage_depth_m`
- Role: define the operational dimensions required for service frontage, work surfaces, equipment placeholders, storage, and staff circulation.

### 4. Public-Realm Architect

- Category: `interpreter`
- Inputs:
  - `PlannerReasoning:string`
  - `KioskHeightM:float`
  - `KioskWidthM:float`
  - `BayCount:int`
- Outputs:
  - `CanopyProjectionM:float`
  - `SignageBandHeightM:float`
  - `FacadeRevealDepthM:float`
  - `PlazaSetbackM:float`
  - `OpenTransparencyRatio:float`
  - `MaterialStrategy:string`
- Signature: `planner_reasoning, kiosk_height_m, kiosk_width_m, bay_count -> canopy_projection_m, signage_band_height_m, facade_reveal_depth_m, plaza_setback_m, open_transparency_ratio, material_strategy`
- Role: shape the kiosk's public presence, shade, signage datum, façade depth, visual openness, and conceptual material expression in relation to the high-rise plaza.

### 5. Coordination Critic

- Category: `critic`
- Inputs:
  - `PlannerReasoning:string`
  - `SecurityReasoning:string`
  - `OperationsReasoning:string`
  - `PublicRealmReasoning:string`
- Outputs:
  - `Coherent:bool`
  - `Issues:string`
  - `Recommendations:string`
  - `PlazaCafeFitnessScore:float`
- Signature: `planner_reasoning, security_reasoning, operations_reasoning, public_realm_reasoning -> coherent, issues, recommendations, plaza_cafe_fitness_score`
- Role: identify conflicts among modular construction, secure closure, coffee workflow, and public-realm expression.

Connect a dedicated Panel to every Chirp `Reasoning` output. Connect additional Panels to the critic's `Issues` and `Recommendations` outputs.

## Deterministic Geometry Contract

Generative numerical values must never be consumed blindly. Create an ordinary C# script node named `Café Contract Guard` between the Chirps and geometry builders. It validates finite values, clamps them to the user limits and the ranges below, resolves dependent dimensions, and emits a human-readable `ContractStatus`.

Core rules:

- `KioskWidthM`: 4.0 m to `SiteWidthLimitM`.
- `KioskDepthM`: 3.0 m to `SiteDepthLimitM`.
- `KioskHeightM`: 2.6 m to `MaxHeightM`.
- `BayCount`: integer 2–6.
- `ResolvedBayWidthM = KioskWidthM / BayCount`; use this canonical value instead of trusting an inconsistent generated bay width.
- `FrameSectionM`: 0.06–0.20 m.
- `PanelThicknessM`: 0.03–0.12 m and less than the frame section.
- `CounterHeightM`: 0.85–1.10 m.
- `CounterDepthM`: 0.45–0.80 m.
- `ServiceOpeningWidthM`: 0.8 m to `ResolvedBayWidthM - 2 * FrameSectionM`.
- `StaffAisleWidthM`: 0.9 m to the available interior clear depth.
- `EquipmentRunLengthM`: 1.2 m to the available interior clear width.
- `StorageDepthM`: 0.35–0.75 m.
- `UpperPanelOpenAngleDeg`: 70–110 degrees.
- `LowerPanelOpenAngleDeg`: 70–100 degrees.
- `CanopyProjectionM`: 0.7–1.8 m and no greater than the geometric reach of the upper panel.
- `SignageBandHeightM`: 0.25–0.65 m.
- `FacadeRevealDepthM`: 0.03–0.30 m.
- `OpenTransparencyRatio`: 0.25–0.85.
- `LockingZoneCount`: integer 2–8.
- `PlazaSetbackM`: 1.5–6.0 m. It is reported and visualized as an advisory clearance curve; it does not move or bake the kiosk in Rhino.

The guard exposes the canonical values using the same semantic names with a `Resolved` prefix, including `ResolvedKioskWidthM`, `ResolvedKioskDepthM`, `ResolvedKioskHeightM`, `ResolvedBayCount`, and `ResolvedBayWidthM`. Geometry builders consume only these resolved outputs, never raw Chirp values.

If an input is missing, non-finite, or irreconcilable, the guard falls back to the documented defaults, records the substitution in `ContractStatus`, and keeps the geometry deterministic. It must never emit NaN, infinity, negative dimensions, or an impossible service opening.

## Grasshopper Geometry Layer

Use ordinary C# script components for the custom geometry and typical Grasshopper controls, Panels, groups, and preview components around them. Do not ask Chirp to emit geometry objects.

### 1. Kiosk Frame

Inputs are the guarded kiosk width, depth, height, bay count, resolved bay width, frame section, façade reveal, and signage-band height.

Outputs:

- `FrameBreps`: modular posts, edge beams, and roof perimeter.
- `PlinthBrep`: a shallow transportable base/plinth.
- `BayPlanes`: ordered front service-bay reference planes.
- `FixedShellBreps`: back wall, side walls, roof skin, and signage band.
- `FootprintCurve`: kiosk footprint for site review.

The frame must remain visibly repetitive so modular logic reads architecturally rather than as concealed construction.

### 2. Operable Shell

Inputs are the guarded bay planes, kiosk dimensions, panel thickness, service-opening width, upper and lower open angles, canopy projection, locking-zone count, and `OpenForService` toggle.

Outputs:

- `UpperPanelBreps`
- `LowerPanelBreps`
- `ServiceCounterBreps`
- `HingeAxisCurves`
- `LockingZoneBreps`
- `SecurityEnvelopeBreps`

When `OpenForService = true`, upper panels rotate outward/up to form canopies and lower panels rotate outward/down to form counters. When false, both panel sets return to a flush façade plane, the counter output is empty, and conceptual locking-zone blocks become visible at panel junctions. All motion is a pure transformation of the same panel geometry, demonstrating that the modular enclosure is also the shop apparatus.

### 3. Coffee Fitout

Inputs are the guarded kiosk dimensions, counter height/depth, equipment-run length, staff-aisle width, storage depth, service-opening width, and target throughput.

Outputs:

- `WorkCounterBreps`
- `EquipmentPlaceholderBreps`
- `StorageBreps`
- `StaffZoneCurve`
- `CustomerQueueZoneCurve`
- `FitoutStatus`

Use simple, legible solids for espresso equipment, refrigeration, washing, point of sale, and storage placeholders. These are spatial allowances rather than manufacturer-specific equipment models.

## Data Flow

1. Panels and sliders provide the design brief, site envelope, throughput target, and current operating state.
2. The Café Planner generates the global dimensions and shared reasoning.
3. Planner reasoning fans out to the three domain interpreters and the critic.
4. Specialist reasoning flows to the critic while typed outputs flow to the contract guard.
5. The contract guard normalizes the complete numeric contract and reports any substitutions.
6. Guarded values drive the three C# geometry builders.
7. `OpenForService` changes only the operable-shell transformation, so opening and closing do not trigger new LLM inference.

## Canvas Layout and Grouping

Arrange the definition from left to right:

1. `01 — Brief + Constraints`
2. `02 — Chirp Design Cascade`
3. `03 — Geometry Contract`
4. `04 — Modular Frame`
5. `05 — Operable Secure Shell`
6. `06 — Coffee Fitout`
7. `07 — Review + Critic`

The second group contains the planner, three specialists, and their local reasoning Panels. The seventh contains the critic and its review Panels, so no component needs overlapping group ownership. Use muted group colors that distinguish inputs, reasoning, contracts, geometry, and review without obscuring component warning states. Group only execution-owned components.

## Error Handling and Recovery

- Treat unavailable Rhino, Grasshopper, Chirp adapter, or required script-mutation tools as stop conditions.
- Resolve unfamiliar component identities and all script ports before mutation.
- Apply bounded edit batches with fresh snapshots and epochs.
- Inspect per-operation results because `gh_edit` may partially succeed; never replay committed operations.
- After each batch, poll solver status to a fixed timeout, inspect errors, and make at most one bounded correction from fresh evidence.
- If a Chirp fails inference, keep deterministic geometry at its last valid or documented default contract and expose the failure through Panels; do not substitute fabricated reasoning.
- Never delete or globally clean pre-existing canvas content.

## Verification and Acceptance

### Structural verification

1. Confirm all five Chirps, six user controls, the contract guard, three geometry builders, reasoning Panels, critic Panels, and seven groups exist.
2. Confirm the exact Reasoning fan-out and typed-output-to-contract connections.
3. Confirm the critic reads all four reasoning streams.
4. Confirm `OpenForService` connects only to the Operable Shell state input.
5. Confirm zero unresolved Grasshopper errors after the solver settles.

### Reasoning verification

1. Run the default plaza café brief.
2. Confirm each specialist explicitly uses the planner's intent.
3. Confirm the critic evaluates modularity, secure closure, operations, and public-realm character together.
4. Replace the brief temporarily with a compact transit-hub coffee kiosk scenario and verify that all reasoning streams and relevant typed outputs change.
5. Restore the approved default brief.

### Geometry verification

1. Confirm all guarded values are finite and within their documented limits.
2. Confirm the footprint stays within the user site envelope.
3. Confirm the frame bay count and resolved bay width agree exactly.
4. Toggle `OpenForService` off and verify a flush, continuous conceptual security envelope with no serving counters.
5. Toggle it on and verify that the same upper/lower panels become canopies and counters without changing panel count or base dimensions.
6. Confirm fitout solids remain inside the fixed shell and preserve the guarded staff aisle.
7. Confirm the advisory plaza-setback and customer-queue curves are visible for later site coordination.
8. Restore `OpenForService = true` and capture a final fresh snapshot with zero unresolved errors.

## Deliverable Boundary

The completed Grasshopper definition is a reasoning-driven conceptual design tool. It demonstrates the modular architectural system, operational layout, and open/closed transformation. Fabrication joints, transport engineering, foundations, MEP, drainage, accessibility clearance certification, food-service code, structural adequacy, wind resistance, and real security hardware remain explicit future design stages.
