# Detroit B4 Zoning Feasibility Chirp Cascade

Talk example for Rook / Chirp / Riff. One site carries the whole story: Rook
builds the canvas, Chirp reasons about it, Riff reviews the reasoning.

## Goal

A five-node Chirp cascade that reasons about a by-right mixed-use massing on a
real Detroit parcel, produces typed numbers that drive a deterministic C#
massing, and ends in a critic whose `NeedsHumanReview` boolean is the hand-off
to Riff. The reasoning is interpretive (code interpretation, neighbour impact,
height-bonus trade-off), which is what Riff exists to review.

Not a code-compliance tool. Every number is a conceptual-design input, and the
critic is required to list the assumptions it could not verify.

## Site (verified)

Parcel 14316 in Riff's study area (`Riff/GIS files_Land use Zoning/StudyArea_Zoning.gpkg`).

| Fact | Value | Source |
|---|---|---|
| Zoning | B4 General Business | GeoPackage fid 14316 |
| Parcel envelope | 259.8 ft (E-W) x 130.4 ft (N-S), 29,453 sq ft | GeoPackage, NAD83 State Plane Michigan South (ft) |
| South frontage | East 7 Mile Road | Reverse geocode of parcel edge |
| North neighbour | R2 Two-Family Residential across a narrow gap (alley) | GeoPackage fids 9533, 9535 |
| Master Plan land use | Neighborhood Commercial; Low Density Residential to north | Riff land-use GeoPackage |

## Zoning facts (Detroit City Code Chapter 50, Municode, read 2026-09-21)

| Rule | Value | Section |
|---|---|---|
| B4 commercial setbacks ("All other uses") | none required front, side, rear | 50-13-45 |
| B4 base height | 35 ft | 50-13-45, 50-13-63(1) |
| Height bonus | +1 ft per 1 ft of street width over 80 ft, max 80 ft, only where the building's outermost point is 40 ft or more from any R1, R2, R3 lot line | 50-13-63(2) |
| FAR | none for commercial; 2.00 for stand-alone multi-family | 50-13-45 |
| Dwellings above another use in B4 | no setbacks except a rear setback beginning at the lowest residential floor | 50-13-62(a) |
| Retail parking | 1 per 200 sq ft under 50,000 sq ft | 50-14-91 Schedule B |
| Restaurant parking | 3 for first 500 sq ft, then 1 per 100 sq ft | 50-14-51 |
| Office parking | 1 per 400 sq ft | 50-14-52 |
| Multi-family parking | 1.25 per unit; 0.75 within 0.5 mi of a high-frequency transit corridor | 50-14-34 |
| Parking screening at residential | opaque wall 4 to 6 ft; paving at least 10 ft from the residential lot | 50-14-342 (pre Ord. 2025-29 numbering) |

## Assumptions the critic must surface

1. East 7 Mile right-of-way is the 120 ft mile-road standard, giving a 75 ft bonus ceiling. Not confirmed from a plat.
2. DDOT Route 7 runs 15-minute service on the frontage, so the parcel very likely qualifies for the 0.75 transit parking ratio. Definition text in 50-16-242 not read.
3. Ordinance 2025-29 (Nov 2025) consolidated the screening standards; the 4 to 6 ft wall and 10 ft paving setback are the pre-amendment values.
4. Whether East 7 Mile is designated a major or secondary thoroughfare in the Master Plan of Policies was not checked.

## Units

Feet throughout, matching the code. The Grasshopper geometry is a canvas-only
massing model in feet; nothing is baked to Rhino.

## Cascade topology (hybrid fan-out + critic)

```text
DesignBrief + ZoningFacts + parcel sliders
          |
     Zoning Planner
          |
          +-- Reasoning --> Massing Interpreter  -- Reasoning --+
          +-- Reasoning --> Neighbour Interpreter -- Reasoning --+--> Coordination Critic
          +-- Reasoning --> Frontage Interpreter  -- Reasoning --+
          +---------------------------------------------------------+

Typed numbers --> Massing Guard + Builder (C#) --> parcel, floor slabs, clearance zone, stalls
```

## Chirp components

Every Chirp gets the auto-added `Correction` input and `Reasoning` output.

### 1. Zoning Planner (planner)

- Inputs: `DesignBrief:string`, `ZoningFacts:string`, `ParcelWidthFt:float`, `ParcelDepthFt:float`
- Outputs: `FloorCount:int`, `GroundFloorUse:string`, `UpperFloorUse:string`, `TargetHeightFt:float`, `PursueHeightBonus:bool`
- Signature: `design_brief, zoning_facts, parcel_width_ft, parcel_depth_ft -> floor_count, ground_floor_use, upper_floor_use, target_height_ft, pursue_height_bonus`
- Role: decide programme and overall height strategy, including whether to chase the 50-13-63(2) bonus given the R2 lot line 130 ft away.

### 2. Massing Interpreter (interpreter)

- Inputs: `MassingRationale:string` (planner Reasoning), `ParcelDepthFt:float`, `TargetHeightFt:float`, `FloorCount:int`
- Outputs: `FootprintWidthFt:float`, `FootprintDepthFt:float`, `UpperFloorToFloorFt:float`, `StepbackStartFloor:int`, `StepbackDepthFt:float`
- Signature: `massing_rationale, parcel_depth_ft, target_height_ft, floor_count -> footprint_width_ft, footprint_depth_ft, upper_floor_to_floor_ft, stepback_start_floor, stepback_depth_ft`
- Build note: the first version asked for a single `floor_to_floor_ft`. The interpreter
  said in its own reasoning that it was reporting the 14 ft ground floor because the
  schema only allowed one number, and the massing came out at 42 ft instead of 35 ft.
  Renaming the field to `upper_floor_to_floor_ft` fixed it (10.5 ft). Signatures are prompts.

### 3. Neighbour Interpreter (interpreter)

- Inputs: `MassingRationale:string`, `NorthEdgeCondition:string`, `TargetHeightFt:float`
- Outputs: `RearBufferFt:float`, `NorthFacadeMaxHeightFt:float`, `ScreeningWallHeightFt:float`, `NeighborRiskLevel:string`
- Signature: `massing_rationale, north_edge_condition, target_height_ft -> rear_buffer_ft, north_facade_max_height_ft, screening_wall_height_ft, neighbor_risk_level`

### 4. Frontage Interpreter (interpreter)

- Inputs: `MassingRationale:string`, `FrontageCondition:string`, `ParcelWidthFt:float`, `GroundFloorUse:string`
- Outputs: `GroundFloorHeightFt:float`, `ActiveFrontageRatio:float`, `ParkingStallCount:int`, `ParkingLocation:string`, `EntranceOffsetFt:float`
- Signature: `massing_rationale, frontage_condition, parcel_width_ft, ground_floor_use -> ground_floor_height_ft, active_frontage_ratio, parking_stall_count, parking_location, entrance_offset_ft`

### 5. Coordination Critic (critic)

- Inputs: `PlannerReasoning:string`, `MassingReasoning:string`, `NeighborReasoning:string`, `FrontageReasoning:string`
- Outputs: `ConflictCount:int`, `TopConflict:string`, `UnverifiedAssumptions:string`, `Confidence:float`, `NeedsHumanReview:bool`
- Signature: `planner_reasoning, massing_reasoning, neighbor_reasoning, frontage_reasoning -> conflict_count, top_conflict, unverified_assumptions, confidence, needs_human_review`
- Role: cross-check the three domain readings against the planner, name the deciding conflict, list what could not be verified, and decide whether a person must look. The boolean is the Riff hand-off.

## User controls

| Control | Type | Default |
|---|---|---|
| `DesignBrief` | Panel | see below |
| `ZoningFacts` | Panel | condensed table above, with section numbers |
| `NorthEdgeCondition` | Panel | R2 two-family houses across an alley along the full 260 ft north edge; 50-13-63(2) requires 40 ft clearance from their lot line for any height above 35 ft; parking screening wall 4 to 6 ft and paving 10 ft off the lot line |
| `FrontageCondition` | Panel | East 7 Mile Road, assumed 120 ft right-of-way (unverified), DDOT Route 7 15-minute service, B4 requires no front setback |
| `ParcelWidthFt` | Slider | 259.8 (200 to 300) |
| `ParcelDepthFt` | Slider | 130.4 (100 to 160) |

Default brief:

> Mixed-use building on parcel 14316, East 7 Mile Road, Detroit. Ground-floor
> neighbourhood retail with a corner café, housing above, parking behind the
> building. Get as much housing as by-right zoning allows while protecting the
> two-family houses across the alley to the north. Say clearly whether the
> height bonus is worth pursuing on a lot only 130 ft deep.

## Deterministic massing (C# script, `Massing Guard + Builder`)

Consumes only typed Chirp outputs plus the two sliders. Clamps, resolves, and
builds. Never trusts a raw value.

Inputs: `ParcelWidthFt`, `ParcelDepthFt`, `TargetHeightFt`, `PursueHeightBonus`,
`FloorCount`, `GroundFloorHeightFt`, `UpperFloorToFloorFt`, `FootprintWidthFt`,
`FootprintDepthFt`, `StepbackStartFloor`, `StepbackDepthFt`, `RearBufferFt`,
`NorthFacadeMaxHeightFt`, `ScreeningWallHeightFt`, `ParkingStallCount`.

The planner's `TargetHeightFt` and `PursueHeightBonus` make the height contract
binding: the legal cap is 35 ft by right or 75 ft with the bonus, the target is
clamped under that cap, and any floor whose top exceeds the target is omitted
with a note. Without this the builder happily stacked whatever the interpreter sent.

Clamps: `FloorCount` 1 to 7; `FloorToFloorFt` 10 to 18; `GroundFloorHeightFt`
12 to 20; `RearBufferFt` 0 to 60; `StepbackDepthFt` 0 to 60;
`StepbackStartFloor` 2 to `FloorCount`; `ParkingStallCount` 0 to 60.

Resolution: footprint depth = min(requested, parcel depth minus rear buffer).
Any floor whose top is above 35 ft has its north edge pushed to at least 40 ft
from the north lot line (the 50-13-63(2) clearance), or to the step-back, whichever
is larger. Nothing exceeds 75 ft. `ContractStatus` lists every substitution.

Outputs: `ParcelCurve`, `NorthLotLine`, `ClearanceZone` (40 ft band), `Slabs`
(one Brep per floor), `ParkingStalls` (9 x 18 ft rectangles in rows behind the
building), `ContractStatus`, `ResolvedHeightFt`, `ResolvedGfaSqFt`.

## Canvas layout

Left to right: `01 Site + Brief`, `02 Chirp Cascade`, `03 Review + Critic`,
`04 Massing`. Each Reasoning output gets a Panel. Critic `TopConflict`,
`UnverifiedAssumptions`, and `NeedsHumanReview` get Panels.

## Verification

1. All five Chirps, six controls, the C# builder, reasoning and critic Panels, four groups exist; zero unresolved errors after settle.
2. Planner reasoning names the bonus trade-off explicitly. Each interpreter cites the planner's intent. Critic lists at least the right-of-way width as unverified.
3. Toggle the brief to "single-storey retail strip with front parking" and confirm every stream and the massing change.
4. Restore the default brief. Save the definition to `Riff/GH/`.

## Build record (2026-09-21)

Built live on an empty canvas with Rook. Final canvas: 5 Chirps, 6 controls,
1 C# builder, 9 Panels, 4 groups, 43 connections, zero errors or warnings.
Saved to `C:\Users\aryan\source\repos\Riff\GH\Detroit_B4_Parcel14316_ChirpCascade.gh`.

Default brief result:

| Node | Key outputs |
|---|---|
| Zoning Planner | 3 floors, target 35 ft, `PursueHeightBonus=False`; reasoning: parking, not height, is the binding constraint on a 130 ft lot |
| Massing Interpreter | 230 x 60 ft bar, upper floors 10.5 ft, step-back 5 ft from floor 2 |
| Neighbour Interpreter | 10 ft rear buffer, 35 ft north facade cap, 6 ft wall, risk Low |
| Frontage Interpreter | 14 ft ground floor, 0.95 active frontage, 50 stalls at rear, entrance offset 45 ft |
| Coordination Critic | 2 conflicts, confidence 0.58, `NeedsHumanReview=True`; top conflict: planner's ~90-stall demand vs 45-55 supply never reconciled |
| Builder | by-right regime, 3 floors, 35 ft, 39,100 sf, 50 stalls, all inputs within contract |

Contrast brief (single-storey strip, front parking, drive-through kiosk): planner
went to 1 floor at 15 ft, frontage asked for 78 stalls, builder clamped to 60 and
reported only 28 fit behind the building, critic flagged that no discipline gave
the kiosk a footprint. Every stream moved; default brief then restored.

## Riff pass (2026-09-21)

Riff's service runs from `Riff/Chirp` (`CHIRP_PORT=9900 .venv/Scripts/python -m chirp`);
the Rook Chirp sidecar is a different process (installed app copy, OS-assigned port)
with no `/api/riff` routes. The snapshot was assembled by Rook from a live
`gh_snapshot` of the open canvas: one node per Chirp, role from the nickname,
upstream IDs from the wires, typed outputs as parameters, Reasoning as rationale.
Builder script and output: `scratchpad/detroit_snapshot.json` for this session.

Import is synchronous and the presenter's Opus 5 call took about 8 minutes for five
long packets, well past a 3 minute client timeout. The server keeps working after
the client drops, so poll `GET /api/riff/snapshots/{id}` until it stops returning 404.

Result for `detroit-b4-20260921-1657`: `presentation_source=intelligent`, 19 grounded
annotations, 5 pending node reviews. Presenter:
`http://127.0.0.1:9900/riff/presenter.html?snapshot_id=detroit-b4-20260921-1657`.
State is process-local; restarting Riff loses it and the snapshot must be re-posted.

## Riff round trip (2026-09-21)

Review Matrix for `detroit-b4-20260921-1657`, reviewer Aaron Ryan, complete 17:22Z:
Planner accepted, Neighbour accepted, Frontage accepted, Critic accepted, Massing
Interpreter `request_correction` ("We should look at why the planner is making this
exact claim in the next pass").

Round trip applied by Rook to the canvas (`..._collapsed.gh`):

- A `Riff Correction -> Massing` Panel wired to the Massing Interpreter's `Correction`
  pin. It quotes the reviewer note verbatim and adds the three Riff annotations
  grounded on that node (a6 midpoint depth, a7 literal 5 ft step-back, a17 width vs
  0.95 active frontage) so the interpreter knows which claims to trace.
- A `Riff Review Matrix` Panel in a new `05 Riff Review` group recording all five
  decisions and notes.

Result of the corrected pass: the interpreter traced each number to the planner's
sentence and labelled it derived or assumed. Depth 60 ft kept (derived from the
planner's 60 x 230 = 13,800 sf arithmetic, not a midpoint); width 230 ft kept but
flagged as assumed with a ~17 ft gap to the 0.95 frontage reading; upper floors
10.5 ft derived; step-back start floor 2 cited from 50-13-62(a); step-back depth
5 ft explicitly marked as an undetermined placeholder. Numbers unchanged, provenance
now explicit. Critic confidence moved 0.52 to 0.62, top conflict is now the width
vs frontage gap, `NeedsHumanReview` still true. Builder contract unchanged: 3 floors,
35 ft, 39,100 sf, 50 stalls.

Next Riff pass should re-snapshot this state; the correction text travels with the
node as an input, so Riff will see it.

## Boundary

Conceptual massing only. Not a zoning determination, parking study, or shadow
analysis. Riff later imports the reasoning; that capture step is outside this canvas.
