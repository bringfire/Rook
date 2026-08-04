# Alpine Hut Chirp Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a five-node Chirp reasoning cascade for a contemporary timber-and-stone Alpine hut in the active Grasshopper document.

**Architecture:** One Planner receives an editable brief and fans its auto-added `Reasoning` output to three domain Interpreters. A Critic reads Planner, Structure, Envelope, and Site reasoning; Panels expose every reasoning stream, and one execution-owned group contains the full cascade.

**Tech Stack:** Rhino 8, Grasshopper, Chirp adapter, DSPy signatures, Rook `chirp_create`, `gh_edit`, `gh_snapshot`, `gh_status`, `gh_errors`, and `gh_inspect_output`.

## Global Constraints

- Target only the active, unnamed Grasshopper document admitted as empty.
- Create five Chirp components, one editable brief Panel, and five Reasoning Panels.
- Do not declare the auto-added `Correction` input or `Reasoning` output manually.
- Do not create or bake geometry.
- Preserve any live state outside the admitted baseline and mutate only execution-owned objects.
- Stop on Chirp adapter or component-creation failure; do not substitute ordinary C# components.
- Use fresh snapshots and epochs for every `gh_edit` batch and inspect partial-success results.

---

### Task 1: Create the Five Chirp Components

**Files:**
- Create live objects: five Chirp C# components in the active Grasshopper document
- Reference: `docs/superpowers/specs/2026-08-04-alpine-hut-chirp-cascade-design.md`

**Interfaces:**
- Consumes: the approved pin definitions and signatures below
- Produces: five compiled Chirp component GUIDs and their fresh short IDs

- [ ] **Step 1: Re-admit the live target**

Run `rhino_ping`, `gh_status`, and `gh_snapshot`. Require an active empty document, enabled solver, `ready_for_edit=true`, and a fresh epoch. Record the document ID and any unexpected pre-existing IDs before mutation.

- [ ] **Step 2: Create Alpine Hut Planner**

Invoke `chirp_create` with:

```json
{
  "name": "Alpine Hut Planner",
  "category": "planner",
  "x": 420,
  "y": 300,
  "pins_in": ["DesignBrief:string"],
  "pins_out": ["FloorAreaM2:float", "RoofPitchDeg:float", "GlazingRatio:float", "Occupancy:int"],
  "signature": "design_brief -> floor_area_m2, roof_pitch_deg, glazing_ratio, occupancy"
}
```

- [ ] **Step 3: Create Snow Structure**

Invoke `chirp_create` with:

```json
{
  "name": "Snow Structure",
  "category": "interpreter",
  "x": 850,
  "y": 100,
  "pins_in": ["PlannerReasoning:string"],
  "pins_out": ["StructuralSystem:string", "SnowLoadKnM2:float", "PrimarySpanM:float", "FoundationStrategy:string"],
  "signature": "planner_reasoning -> structural_system, snow_load_kn_m2, primary_span_m, foundation_strategy"
}
```

- [ ] **Step 4: Create Climate Envelope**

Invoke `chirp_create` with:

```json
{
  "name": "Climate Envelope",
  "category": "interpreter",
  "x": 850,
  "y": 350,
  "pins_in": ["PlannerReasoning:string"],
  "pins_out": ["WallUValue:float", "RoofUValue:float", "SouthGlazingRatio:float", "OverhangDepthM:float", "EnvelopeStrategy:string"],
  "signature": "planner_reasoning -> wall_u_value, roof_u_value, south_glazing_ratio, overhang_depth_m, envelope_strategy"
}
```

- [ ] **Step 5: Create Mountain Site**

Invoke `chirp_create` with:

```json
{
  "name": "Mountain Site",
  "category": "interpreter",
  "x": 850,
  "y": 600,
  "pins_in": ["PlannerReasoning:string"],
  "pins_out": ["OrientationDeg:float", "SlopeLimitDeg:float", "AccessStrategy:string", "LandscapeImpact:string"],
  "signature": "planner_reasoning -> orientation_deg, slope_limit_deg, access_strategy, landscape_impact"
}
```

- [ ] **Step 6: Create Alpine Critic**

Invoke `chirp_create` with:

```json
{
  "name": "Alpine Critic",
  "category": "critic",
  "x": 1320,
  "y": 350,
  "pins_in": ["PlannerReasoning:string", "StructureReasoning:string", "EnvelopeReasoning:string", "SiteReasoning:string"],
  "pins_out": ["Coherent:bool", "Issues:string", "Recommendations:string", "AlpineFitnessScore:float"],
  "signature": "planner_reasoning, structure_reasoning, envelope_reasoning, site_reasoning -> coherent, issues, recommendations, alpine_fitness_score"
}
```

- [ ] **Step 7: Checkpoint compilation and pin contracts**

Poll `gh_status`, capture a fresh snapshot, and run `gh_errors`. For each component, record its short ID, the index of every named user input, and the index of its auto-added `Reasoning` output. Require five Chirp components with zero compile errors before continuing.

### Task 2: Add Panels, Wire the Cascade, and Group It

**Files:**
- Create live objects: one brief Panel, five Reasoning Panels, and one group
- Modify live state: connect execution-owned components and Panels

**Interfaces:**
- Consumes: fresh component IDs, input indices, Reasoning output indices, and epoch from Task 1
- Produces: complete hybrid cascade topology with visible reasoning streams

- [ ] **Step 1: Create Panels and all authorized connections in one bounded batch**

Use `gh_edit` to create these Panels:

| Temp ID | Position | Content |
| --- | --- | --- |
| T1 | `[80, 300]` | Approved default Alpine hut brief |
| T2 | `[620, 20]` | `Planner Reasoning` |
| T3 | `[1080, 70]` | `Structure Reasoning` |
| T4 | `[1080, 320]` | `Envelope Reasoning` |
| T5 | `[1080, 570]` | `Site Reasoning` |
| T6 | `[1580, 350]` | `Critic Reasoning` |

The exact default brief is:

```text
Design a compact contemporary timber-and-stone Alpine hut for four occupants at approximately 1,800 m elevation on a south-facing mountain slope. Prioritize heavy-snow and strong-wind resilience, passive solar gain, a compact thermal envelope, durable low-maintenance materials, minimal site disturbance, and winter access on foot. Produce coordinated architectural, structural, envelope, and site guidance suitable for later parametric geometry.
```

Connect the brief Panel to `Alpine Hut Planner.DesignBrief`. Connect Planner `Reasoning` to Snow Structure, Climate Envelope, Mountain Site, Alpine Critic input 0, and T2. Connect Structure, Envelope, and Site `Reasoning` to Alpine Critic inputs 1, 2, and 3 and to T3, T4, and T5 respectively. Connect Critic `Reasoning` to T6. Use the indices recorded from the fresh snapshot instead of assuming output positions.

Create group `Contemporary Alpine Hut — Chirp Cascade` containing all five Chirps and six Panels. Inspect the per-operation result and temp-ID map; never replay committed operations after partial success.

- [ ] **Step 2: Checkpoint the first solved cascade**

Poll `gh_status` to a bounded timeout, run `gh_errors`, and capture a fresh snapshot. Require all expected flows, group membership, solver readiness, and no unresolved dependency before testing outputs.

### Task 3: Test Coherence, Contrast Behavior, and Restore the Brief

**Files:**
- Modify live object: execution-owned brief Panel value only
- Read live outputs: five execution-owned `Reasoning` outputs

**Interfaces:**
- Consumes: brief Panel ID, Chirp IDs, and Reasoning output indices from Tasks 1-2
- Produces: verified default reasoning, verified response to a contrasting brief, and restored final state

- [ ] **Step 1: Inspect default Reasoning outputs**

Use `gh_inspect_output` on the named `Reasoning` output of all five Chirps. Confirm nonempty text, downstream references to upstream intent, and domain-appropriate Alpine guidance. Record Critic `Coherent`, `Issues`, `Recommendations`, and `AlpineFitnessScore` if populated.

- [ ] **Step 2: Run a contrasting emergency-shelter probe**

Capture a fresh epoch and use `gh_edit.set_values` to replace only the brief Panel content with:

```text
Design an ultralight two-person emergency shelter above 2,800 m for helicopter delivery, minimal overnight occupation, extreme wind exposure, no glazing priority, and rapid seasonal removal.
```

After the solve settles, inspect all five Reasoning outputs and confirm they differ materially from the default scenario in occupancy, system weight, envelope assumptions, access, or siting logic.

- [ ] **Step 3: Restore the approved brief**

Capture a fresh epoch and restore the exact approved contemporary timber-and-stone brief with `gh_edit.set_values`. Wait for the solve and inspect the Planner and Critic Reasoning outputs to confirm restored intent.

- [ ] **Step 4: Run the final checkpoint**

Capture a final `gh_snapshot`, `gh_errors`, and relevant `gh_inspect_output` results. Verify the five Chirps, six Panels, complete topology, single group, restored brief, nonempty reasoning streams, and zero unresolved errors. Report execution-owned IDs and any remaining warnings without global cleanup or geometry baking.
