# Alpine Hut Chirp Cascade Design

## Goal

Create a reasoning-only Chirp cascade in Grasshopper for a compact contemporary timber-and-stone hut in the Alps. The cascade coordinates architectural planning, snow structure, climate envelope, and mountain-site decisions, then checks them for cross-discipline coherence.

## Live Target and Scope

- Target the active, unnamed, empty Grasshopper document admitted during preflight.
- Create five Chirp components, one editable design-brief Panel, and one visible Panel for each component's auto-added `Reasoning` output.
- Use a hybrid fan-out-plus-critic topology.
- Do not create or bake geometry in this first version.
- Group only execution-owned objects and preserve any content that appears outside the admitted empty baseline.

## Default Design Brief

> Design a compact contemporary timber-and-stone Alpine hut for four occupants at approximately 1,800 m elevation on a south-facing mountain slope. Prioritize heavy-snow and strong-wind resilience, passive solar gain, a compact thermal envelope, durable low-maintenance materials, minimal site disturbance, and winter access on foot. Produce coordinated architectural, structural, envelope, and site guidance suitable for later parametric geometry.

## Cascade Components

### 1. Alpine Hut Planner

- Category: `planner`
- Inputs: `DesignBrief:string`
- Outputs: `FloorAreaM2:float`, `RoofPitchDeg:float`, `GlazingRatio:float`, `Occupancy:int`
- Signature: `design_brief -> floor_area_m2, roof_pitch_deg, glazing_ratio, occupancy`
- Role: translate the brief into the shared architectural intent and primary quantitative targets.

### 2. Snow Structure

- Category: `interpreter`
- Inputs: `PlannerReasoning:string`
- Outputs: `StructuralSystem:string`, `SnowLoadKnM2:float`, `PrimarySpanM:float`, `FoundationStrategy:string`
- Signature: `planner_reasoning -> structural_system, snow_load_kn_m2, primary_span_m, foundation_strategy`
- Role: interpret the planner's intent through high-altitude structural and foundation requirements.

### 3. Climate Envelope

- Category: `interpreter`
- Inputs: `PlannerReasoning:string`
- Outputs: `WallUValue:float`, `RoofUValue:float`, `SouthGlazingRatio:float`, `OverhangDepthM:float`, `EnvelopeStrategy:string`
- Signature: `planner_reasoning -> wall_u_value, roof_u_value, south_glazing_ratio, overhang_depth_m, envelope_strategy`
- Role: translate the shared intent into a cold-climate envelope and passive-solar strategy.

### 4. Mountain Site

- Category: `interpreter`
- Inputs: `PlannerReasoning:string`
- Outputs: `OrientationDeg:float`, `SlopeLimitDeg:float`, `AccessStrategy:string`, `LandscapeImpact:string`
- Signature: `planner_reasoning -> orientation_deg, slope_limit_deg, access_strategy, landscape_impact`
- Role: interpret orientation, slope, access, and minimal-disturbance siting requirements.

### 5. Alpine Critic

- Category: `critic`
- Inputs: `PlannerReasoning:string`, `StructureReasoning:string`, `EnvelopeReasoning:string`, `SiteReasoning:string`
- Outputs: `Coherent:bool`, `Issues:string`, `Recommendations:string`, `AlpineFitnessScore:float`
- Signature: `planner_reasoning, structure_reasoning, envelope_reasoning, site_reasoning -> coherent, issues, recommendations, alpine_fitness_score`
- Role: cross-check all reasoning streams and identify contradictions or missing Alpine-specific constraints.

Every Chirp also has an auto-added optional `Correction` input and auto-added `Reasoning` output; neither is declared manually.

## Topology and Layout

The brief Panel feeds the Planner. The Planner's `Reasoning` fans out to Snow Structure, Climate Envelope, Mountain Site, and the Alpine Critic. Each specialist's `Reasoning` also feeds the Alpine Critic. A dedicated Panel is connected to every `Reasoning` output for visibility.

Arrange the brief and Planner at the left, the three specialists in a vertical middle column, the Critic at the right, and the Reasoning Panels immediately downstream of their source components. Create a single group named `Contemporary Alpine Hut — Chirp Cascade` around all execution-owned objects.

## Error Handling and Preservation

- Capture a fresh snapshot and epoch immediately before each edit batch.
- Record created GUIDs, short IDs, connections, and group membership in an execution-owned ledger.
- Treat Chirp creation or adapter failures as stop conditions; do not substitute ordinary C# components.
- Inspect partial-success responses and never replay already committed mutations.
- Apply at most one bounded correction based on fresh live evidence.

## Verification

1. Confirm all five Chirp components compile and the solver is ready.
2. Confirm the brief Panel and five Reasoning Panels are connected to the intended pins.
3. Run the default Alpine brief and inspect all Reasoning outputs for domain coherence.
4. Temporarily replace the brief with a contrasting lightweight emergency-shelter scenario and verify the reasoning changes across the cascade.
5. Restore the approved contemporary timber-and-stone brief.
6. Capture a final fresh snapshot and verify zero unresolved errors, the complete topology, output visibility, and restored brief.
