# Typed Route Gap Analysis: Closing the Command-String Fallback

**Date:** 2026-04-15
**Author:** bringfire + Claude
**Status:** Analysis complete, ready for implementation planning
**Related:** `intent_runtime.py` CapabilityRouter, `smart_executor.py` fallback chain

---

## Executive Summary

This document is not just a route inventory. It is a correction to the original
theory of capability that shaped early Rook (then RhinoClaude).

The original assumption was that an AI harness should expose Rhino the way a
human uses Rhino: through commands, prompts, and interactive command-line
dialogue. That assumption treated Rhino's command UI as if it were the right
machine interface simply because it is a strong human interface.

That turned out to be largely wrong. Rhino's command system is optimized for
human-in-the-loop use, not machine-to-machine contracts. Prompt-driven semantics
are useful for human guidance, but weak as an execution substrate for agents.
Interactive grammars also expose ambiguity too late: the model often discovers
missing context only after starting execution.

The replacement theory is now clearer: agents are empowered by explicit tool
schemas, progressive capability discovery, typed routes, structured validation,
and rich error feedback. On that model, a "gap" is not just a missing endpoint.
It is any missing machine-usable contract for a common intent. That includes:
- missing native or managed routes
- missing MCP schemas over existing routes
- missing CapabilityRouter coverage over existing typed tools
- weak response payloads that prevent reliable chaining

**Current coverage: 106 typed operations in the CapabilityRouter out of ~196
commands in the knowledge store (54%).** The remaining operations still rely on
command-oriented execution paths often enough that the old theory remains
load-bearing in practice.

The most critical gaps are surface creation operations (Loft, Sweep, Pipe,
Revolve) and general array operations. These are common intents that still lack
clean machine-usable contracts.

The command system is therefore being repositioned, not treated as the primary
execution model. Policy for this document:
- typed routes are the default execution path
- `rhino_command` remains fallback-only during migration
- the interactive command protocol survives as a narrow escape hatch for
  genuinely ambiguity-heavy operations where picker-style interaction is part of
  the operation semantics

This framing also changes how to think about legacy infrastructure. The old
theory did not just leave route gaps; it also built systems to sustain itself:
command observation, command learning, command consolidation, interactive
command dialogue, and `rhino_command` as a first-class path. As typed coverage
grows, those systems should shrink to their durable residual roles: fallback,
route discovery, and test material drawn from real observations.

## Theory of Capability Shift

### Early Theory: Human-Style Command Use Would Empower the Model

Early Rook assumed that exposing Rhino commands interactively would fully
empower Claude Code. The reasoning was understandable: Rhino's command line and
option prompts encode real semantic guidance for human users, so perhaps that
guidance could serve as the model's operating substrate too.

That theory was productive as a bootstrap. It created a working harness, an
observation corpus, and a fallback path that prevented total dead-ends. But it
also biased the system toward simulating a human at the command line instead of
giving the model first-class machine contracts.

### What We Learned

The command model is valuable, but not as the default execution substrate.

- Human-oriented prompt flows are not stable machine contracts
- Command grammars hide ambiguity until execution has already begun
- Opaque command strings are poor inputs for validation, planning, and recovery
- Thin command responses are poor outputs for chaining downstream operations

### New Principle: Machine-Usable Contracts Beat Command Simulation

The harness should optimize for explicit contracts:

- clear input schemas
- progressive capability discovery
- typed endpoints with early validation
- structured outputs rich enough for chaining and recovery
- precise error feedback that helps the model repair its own requests

### Consequence: Two Kinds of Cleanup

This analysis therefore surfaces two parallel consequences of the old theory:

1. **Contract gaps** — common intents that still lack typed, machine-usable
   execution paths
2. **Overgrown legacy scaffolding** — command-learning and interactive-command
   infrastructure that was appropriate as bootstrap scaffolding, but should
   contract as typed coverage grows

Some pieces of that old system still have affirmative value:

- the command observations corpus is real test material for new typed routes
- command knowledge can still help identify promotion candidates
- the interactive protocol remains useful for the narrow class of operations
  that genuinely require ambiguity resolution during execution

The rest of this document focuses primarily on the first consequence: the
highest-value contract gaps in the current runtime.

---

## Why This Matters

### Cost of the Command-String Fallback

When `rhino_execute_intent` encounters an operation without a typed route:

```
Intent: "loft through these 5 curves"
  |
  v
CapabilityRouter.has_direct_route("loft") -> False
  |
  v  (fast path fails, fall to slow path)
CommandKnowledgeStore.search("loft")
  |  +1 DSPy call: IntentResolver selects command + mode
  |  +1 DSPy call: SyntaxBuilder fills parameters
  v
SmartExecutor._execute_command("_-Loft _SelID a _Enter")
  |
  v  (if command stalls at "Select curve..." prompt)
_execute_interactive() -> multi-round prompt loop
```

**Per-invocation cost of fallback vs typed route:**
- +2-3 LLM inference calls (100-300ms latency each)
- Interactive mode risk (command may stall requiring user prompts)
- Confidence penalty (fallback paths get `confidence * 0.7`)
- No input validation (bad params only caught after Rhino executes)
- Poor response signal (no type, layer, bbox — model can't chain operations)

### Response Quality Contrast

**Typed route response** (`/create` with type=SPHERE):
```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "Brep",
    "layer": "Default",
    "name": "Sphere1",
    "visible": true,
    "bbox": { "min": [-5, -5, -5], "max": [5, 5, 5] },
    "color": [128, 128, 128]
  }
}
```

**Command-string response** (`/command` with `_-Loft ...`):
```json
{
  "success": true,
  "data": {
    "command": "_-Loft _SelID abc123 _Enter",
    "executed": true,
    "objectsCreated": 1,
    "objectIds": ["..."],
    "error": null
  }
}
```

The typed route gives the model **type, layer, bbox, visibility, color** — enabling
spatial reasoning, operation chaining, and error recovery. The command-string
response gives an echo of the input and a count.

---

## Current Typed Route Coverage

### CapabilityRouter: 106 Operations (from `_build_route_table()`)

Source: `mcp_server/src/rook/learning/intent_runtime.py` lines 224-972

These counts are useful as rough backlog sizing only. They are **not** the
primary success metric for the harness. Under the theory-of-capability shift
described above, the real success metric is workflow-weighted: how many common
agent intents can execute through stable machine-usable contracts without
falling back to command-oriented paths.

#### Creation (20 operations) — GOOD
| Operation | Endpoint | Types |
|-----------|----------|-------|
| `create_point` | `/create` | POINT |
| `create_line` | `/create` | LINE |
| `create_polyline` | `/create` | POLYLINE |
| `create_circle` | `/create` | CIRCLE |
| `create_arc` | `/create` | ARC |
| `create_rectangle` | `/create` | RECTANGLE |
| `create_box` | `/create` | BOX |
| `create_sphere` | `/create` | SPHERE |
| `create_cylinder` | `/create` | CYLINDER |
| `create_cone` | `/create` | CONE |
| `create_extrusion` | `/create` | EXTRUDE (curve + direction) |
| `create_interpolated_curve` | `/create` | INTERPOLATED_CURVE |
| `create_control_point_curve` | `/create` | CONTROL_POINT_CURVE |
| `create_mesh_box` | `/mesh/box` | Mesh box |
| `create_mesh_sphere` | `/mesh/sphere` | Mesh sphere |
| `create_mesh_cylinder` | `/mesh/cylinder` | Mesh cylinder |
| `create_mesh_cone` | `/mesh/cone` | Mesh cone |
| `create_subd_box` | `/subd/box` | SubD box |
| `create_subd_sphere` | `/subd/sphere` | SubD sphere |
| `create_subd_cylinder` | `/subd/cylinder` | SubD cylinder |

#### Transform (6 operations) — COMPLETE
| Operation | Endpoint |
|-----------|----------|
| `move` | `/transform` |
| `rotate` | `/transform` |
| `scale` | `/transform` |
| `mirror` | `/transform` |
| `copy` | `/copy` |
| `delete` | `/delete` |

#### Boolean (4 operations) — COMPLETE
`boolean_union`, `boolean_difference`, `boolean_intersection`, `boolean_split`
— all via `/boolean`

#### Surface/Edge Operations (3 operations) — MINIMAL
| Operation | Endpoint |
|-----------|----------|
| `fillet_edge` | `/fillet` |
| `chamfer_edge` | `/chamfer` |
| `offset_brep` | `/offset/brep` |

#### Curve Operations (12 operations) — GOOD
`join_curves`, `explode_curve`, `divide_curve`, `extend_curve`, `trim_curve`,
`split_curve`, `rebuild_curve`, `fillet_curves`, `project_curve`, `pull_curve`,
`offset_curve`, `offset_curve_on_surface`

#### Intersection (5 operations) — COMPLETE
`intersect_curves`, `intersect_curve_surface`, `intersect_curve_brep`,
`intersect_breps`, `intersect_plane`

#### Split/Trim (4 operations) — COMPLETE
`split_brep`, `trim_brep`, `split_face`, `split_disjoint_breps`

#### Mesh (8 operations) — GOOD
`mesh_from_brep`, `mesh_boolean`, `mesh_repair`, `mesh_smooth`, `mesh_weld`,
`mesh_unweld`, `mesh_reduce`, `quad_remesh`

#### SubD (6 operations) — GOOD
`subd_from_mesh`, `subd_from_surface`, `subd_subdivide`, `subd_crease`,
`subd_to_brep`, `subd_to_mesh`

#### Layers (7 operations) — GOOD
`create_layer`, `delete_layer`, `set_layer_visibility`, `lock_layer`,
`set_current_layer`, `set_layer_properties`, `set_layer_properties_batch`

#### Blocks (31 operations) — EXCELLENT
Comprehensive coverage: definition CRUD, instance manipulation, property
mutation (layers, materials, colors, names, user strings) in single + batch,
transforms, linking, purge, find, detailed inspection.

#### Groups (2), Materials (7), Selection (1), Document (3), IO (2), Game Export (3)
Adequately covered for current needs.

---

## The Gaps

This section focuses on the highest-value contract gaps created by the
command-first era. Phase 1 is not just "top of daily modeling"; it is the set
of common intents whose current treatment is still largely command-oriented
instead of contract-oriented.

### Legacy Scaffolding: Stale MCP Contracts

**Critical finding:** `rhino_loft` and `rhino_sweep` are defined as MCP tools
in `server.py` (lines 1733-1761) and route to `/create` with `type=LOFT` and
`type=SWEEP1`. But the C++ `CreateHandler.cpp` does NOT handle these types
(line 694: `throw std::invalid_argument("Unknown or unsupported geometry type")`).

These are stale contracts rather than durable capability. They currently fail at
runtime and should be either:
- New type handling in CreateHandler, or
- Dedicated handler files (preferred for complex operations)

### Contract Gap Category 1: Surface Creation (P0 — highest impact)

These are common intents still missing machine-usable contracts. In the current
system they are handled primarily through command-era execution paths.

| Operation | Rhino Command | What it does | Complexity |
|-----------|--------------|--------------|------------|
| **Loft** | `_-Loft` | Surface through profile curves | Medium — needs curve selection, loft type (normal/loose/tight/straight), closed option |
| **Sweep1** | `_-Sweep1` | Profile along single rail curve | Medium — rail + profiles, alignment options |
| **Sweep2** | `_-Sweep2` | Profile between two rail curves | Medium — 2 rails + profiles |
| **Pipe** | `_-Pipe` | Tube around centerline curve | Simple — curve + radius (optionally variable) |
| **Revolve** | `_-Revolve` | Rotate profile around axis | Simple — curve + axis + angle |
| **ExtrudeSrf** | `_-ExtrudeSrf` | Extrude a surface face | Simple — surface + direction + distance |
| **Cap** | `_-Cap` | Cap planar openings | Simple — polysurface ID, auto-detects holes |

**RhinoCommon API availability:** All have direct SDK methods:
- `Brep.CreateFromLoft()` / `Brep.CreateFromLoftRebuild()`
- `Brep.CreateFromSweep()` (1-rail and 2-rail overloads)
- `Brep.CreatePipe()`
- `Brep.CreateFromRevSurface()` / `RevSurface.Create()`
- `Brep.CreateFromOffsetFace()` — extrude face
- `Brep.CapPlanarHoles()`

**Implementation approach:** New `SurfaceHandler.cpp` with typed routes:
- `POST /surface/loft` — curveIds, loftType, closed
- `POST /surface/sweep1` — railId, profileIds, options
- `POST /surface/sweep2` — rail1Id, rail2Id, profileIds, options
- `POST /surface/pipe` — curveId, radius (or radii array for variable)
- `POST /surface/revolve` — curveId, axisStart, axisEnd, angle
- `POST /surface/extrude` — brepId, faceIndex, direction, distance
- `POST /surface/cap` — brepId

### Contract Gap Category 2: Array Operations (P0)

Arrays are fundamental to architectural modeling. General object arrays still
lack typed contracts in the intent runtime even though block-instance arraying
already exists as a typed specialized route.

| Operation | Rhino Command | What it does | Complexity |
|-----------|--------------|--------------|------------|
| **ArrayLinear** | `_-ArrayLinear` | Linear array | Simple — ids, direction, count, distance |
| **ArrayRectangular** | `_-Array` | Rectangular grid array | Medium — ids, xCount, yCount, xSpacing, ySpacing |
| **ArrayPolar** | `_-ArrayPolar` | Circular array | Medium — ids, center, count, angle |

**RhinoCommon API:** Transform-based (apply incremental transforms in a loop).
No single `Array` method, but trivially composable from `Transform.Translation()`
and `Transform.Rotation()` + `doc.Objects.Transform()`.

**Implementation approach:** New `ArrayHandler.cpp`:
- `POST /array/linear` — ids, direction, count, distance
- `POST /array/rectangular` — ids, xCount, yCount, xSpacing, ySpacing, (optional: zCount, zSpacing)
- `POST /array/polar` — ids, center, axis, count, angle (total or per-step)

### Contract Gap Category 3: Missing Primitives (P1)

| Operation | What it does | Complexity |
|-----------|-------------|------------|
| **Ellipse** | Ellipse by center + radii or foci | Simple |
| **Torus** | Torus surface | Simple — center, majorRadius, minorRadius |
| **Polygon** | Regular polygon | Simple — center, radius, sides |
| **Helix** | Helical curve | Medium — axis, radius, pitch/turns |
| **Spiral** | Spiral curve (expanding helix) | Medium — axis, startRadius, endRadius, turns |

**Implementation approach:** Extend `CreateHandler.cpp` with new type cases:
- `ELLIPSE` — center, xRadius, yRadius (or semiAxis1, semiAxis2)
- `TORUS` — center, majorRadius, minorRadius
- `POLYGON` — center, radius, sides
- `HELIX` — axisStart, axisEnd, radius, turns (or pitch)
- `SPIRAL` — axisStart, axisEnd, startRadius, endRadius, turns

### Contract Gap Category 4: Curve Creation (P1)

| Operation | What it does | Complexity |
|-----------|-------------|------------|
| **BlendCrv** | Smooth blend between curve ends | Medium — curve1Id, curve2Id, continuity |
| **CurveBoolean** | Boolean on planar closed curves | Medium — curveIds, operation, point |

**Implementation approach:** Extend `CurvesHandler.cpp`:
- `POST /curve/blend` — curve1Id, curve2Id, continuity (position/tangent/curvature)
- `POST /curve/boolean` — curveIds, operation (union/intersection/difference), regionPoint

### Contract Gap Category 5: Advanced Surface Operations (P1)

| Operation | What it does | Complexity |
|-----------|-------------|------------|
| **Patch** | Surface from boundary curves/points | Medium |
| **NetworkSrf** | Surface from curve network | Medium |
| **EdgeSrf** | Surface from 2-4 edges | Simple |
| **BlendSrf** | Smooth transition between surfaces | Complex |
| **FilletSrf** | Round edge between surfaces | Medium |
| **OffsetSrf** | Offset surface by distance | Simple |

**Implementation approach:** Extend `SurfaceHandler.cpp`:
- `POST /surface/patch` — curveIds, pointIds, spans, flexibility
- `POST /surface/network` — uCurveIds, vCurveIds, continuity
- `POST /surface/edge` — curveIds (2-4)
- `POST /surface/blend` — face1Id, face2Id, edge1, edge2, continuity
- `POST /surface/fillet` — face1Id, face2Id, radius
- `POST /surface/offset` — brepId, distance, solid, tolerance

### Contract Gap Category 6: Deformation / Spatial Transforms (P2)

| Operation | What it does | Complexity |
|-----------|-------------|------------|
| **Orient** | Place objects by reference/target frames | Medium |
| **Twist** | Twist objects around axis | Medium |
| **Bend** | Bend objects along spine | Medium |
| **Taper** | Taper objects along axis | Medium |
| **Shear** | Shear objects | Medium |
| **Flow** | Flow along surface | Complex |
| **FlowAlongSrf** | Flow from flat to target surface | Complex |

**Implementation approach:** Extend `GeometryOpsHandler.cpp` or new
`DeformHandler.cpp`. Most of these map to `SpaceMorph` subclasses in
RhinoCommon — `TwistSpaceMorph`, `BendSpaceMorph`, `TaperSpaceMorph`, etc.

### Contract Gap Category 7: Annotation & Text (P2)

| Operation | What it does | Complexity |
|-----------|-------------|------------|
| **Text** | 2D text annotation | Simple |
| **TextObject** | 3D text geometry (curves/surfaces) | Medium |
| **Dot** | Text dot (always faces camera) | Simple |
| **Dim** (linear) | Linear dimension | Medium |
| **DimRadius** | Radius dimension | Medium |
| **DimDiameter** | Diameter dimension | Medium |
| **Leader** | Leader with text | Medium |
| **Hatch** | Hatch pattern fill | Medium |

**Note:** `CreateHandler.cpp` already has partial TEXT and DIMENSION_LINEAR
handling (lines 664-668), but these are not in the CapabilityRouter. Need to
verify they work, add them to the router, and extend for remaining annotation
types.

**2026-04-19 Phase 2 substrate decision.** Annotation routes ship as
`direct-sdk native` in a new `AnnotationHandler.cpp`, NOT as managed-bridge
reuse through `CreateGeometry`. Rationale: (a) managed annotation path at
`src/Rook/Handlers/CreateHandler.cs:93-121` early-returns before the
`_strictAttributes` attribute block at `:181`, so strict-attrs are not
applied today; (b) managed TEXT regresses fidelity vs. native — native
persists annotation-level overrides at `src/RookNative/Handlers/CreateHandler.cpp:558-563`
(`SetTextHeight`, `SetAnnotationFont`, `SetAnnotationBold`, `SetAnnotationItalic`,
`SetAnnotationFacename`) that managed does not replicate; (c) `DIMENSION_LINEAR`
and `DIMENSION_ALIGNED` both call `LinearDimension.Create(AnnotationType.Aligned, ...)`
at `:1009` and `:1045` — they are not actually distinct on the managed side
today, and the new contract should not bake that collapse in; (d) native
`/create?type=TEXT|DIMENSION_LINEAR` is entirely in-process today, so
routing through managed would introduce a new `bridge_unavailable`/503
availability mode. Extraction path: promote existing native factories at
`CreateHandler.cpp:514-615` into `AnnotationHandler.cpp`, then add the
remaining annotation variants (ALIGNED/RADIUS/DIAMETER/ANGLE/LEADER/DOT)
natively one route at a time. `HATCH` deferred from Phase 2 critical path
pending an SDK spike on `CRhinoDoc::AddHatchObject`. Campaign plan:
`rook_docs/2026-04-19-typed-route-phase2-plan.md`.

### Contract Gap Category 8: Selection Variants (P2)

Currently the router has a single `select_objects` operation that routes to
`/select` with flexible filters (ids, layer, type, name, all, clear, invert,
bbox). This is likely sufficient — the Rhino-style `SelCrv`, `SelMesh`, etc.
can be expressed as `select_objects` with `type: "Curve"`, `type: "Mesh"`.

However, this area already contains contract gaps even before adding new
predicates. The current machine contract does not line up cleanly across layers:

- the router advertises `name`, while the native handler currently implements
  `namePattern`
- the router advertises `bbox`, while the native handler currently expects
  `bboxMin` and `bboxMax`

Those schema/handler mismatches should be fixed first.

After that, some selection predicates are still missing from the `/select`
handler:
- `SelClosedCrv` / `SelOpenCrv` — closed/open curve filter
- `SelDup` — duplicate geometry
- `SelSmall` — small objects by tolerance
- `SelShortCrv` — short curves

These could be added as optional filter params to the existing `/select` endpoint.

**2026-04-19 Phase 2 substrate decision.** The drift cleanup is hygiene,
not substrate. Phase 2 PR-0 lands `additive compatibility` (not deprecation):
the handler accepts `name` (exact match) AND `namePattern` (wildcard) in
parallel, plus nested `bbox:{min,max}` alongside flat `bboxMin`/`bboxMax`.
Mixed `name` + `namePattern` in one request is rejected as `invalid_input`
(the two predicates express different matching strategies on the same
field; combining them is almost always caller confusion). Deprecation of
the flat `namePattern`/`bboxMin`/`bboxMax` form is deferred to a
post-soak PR after telemetry or grep confirms no live callers rely on
the old shape. New predicates (`SelClosedCrv`, `SelOpenCrv`, `SelDup`,
`SelSmall`, `SelShortCrv`) are Phase 3, not bundled into Phase 2. Campaign
plan: `rook_docs/2026-04-19-typed-route-phase2-plan.md`.

### Contract Gap Category 9: User Text / Object Attributes (P1)

| Operation | What it does |
|-----------|-------------|
| **SetUserText** | Set key-value user text on objects |
| **GetUserText** | Read user text from objects |
| **SetDocumentUserText** | Set document-level key-value data |
| **GetDocumentUserText** | Read document-level key-value data |

These are critical for any BIM or data-enriched workflow. Currently no typed
route exists. Would need a new handler or extension of ObjectsHandler.

**2026-04-19 Phase 2 substrate decision.** User-text routes ship as
`direct-sdk native` in a new `UserTextHandler.cpp`. Rationale:
`ON_3dmObjectAttributes::SetUserString` and `pDoc->SetUserString` are raw
SDK with no RhinoCommon affordance advantage; the block-user-strings path
already proves the native-only substrate at
`src/RookNative/Handlers/BlocksHandler.cpp:2551` (object) and `:3068` (doc).
Convention added for doc-level writes: a reserved-prefix denylist
(`RookBlock::` and future `Rook*::` reservations) rejects writes that
would shadow subsystem-owned namespaces, surfacing a new error code
`reserved_namespace`. Read routes are unrestricted. Object-level routes
are not subject to the denylist (per-object attributes have no
cross-subsystem contract today). Migration of the existing block
user-string paths onto the new handler is explicitly out of scope —
block metadata stays where it is; Phase 2 adds new routes, not rewrites
storage. Campaign plan:
`rook_docs/2026-04-19-typed-route-phase2-plan.md`.

---

## Legacy Scaffolding to Right-Size

### Stale MCP Contracts with No Backend

| MCP Tool | Routes to | C++ Handler | Status |
|----------|-----------|-------------|--------|
| `rhino_loft` | `/create` type=LOFT | CreateHandler | **STALE** — type not handled |
| `rhino_sweep` | `/create` type=SWEEP1 | CreateHandler | **STALE** — type not handled |

These should either be wired to real handlers or removed so the MCP surface
matches actual durable capability.

### Command Learning Infrastructure (right-size candidate)

The entire command-learning system was built to serve the naive command model:

| Component | Location | Size | Purpose |
|-----------|----------|------|---------|
| `command_observer.py` | `mcp_server/src/rook/learning/` | ~960 lines | Record interactive command dialogues |
| `command_learner.py` | `mcp_server/src/rook/learning/` | ~500 lines | DSPy + MABWiser command selection |
| `command_consolidator.py` | `mcp_server/src/rook/learning/` | ~1,736 lines | DSPy pattern extraction |
| `command_knowledge.json` | `knowledge/commands/` | 319 KB | 83 commands, 147 modes, 307 gotchas |
| `command_observations.json` | `knowledge/commands/` | 1.2 MB | Raw dialogue captures |
| `learning_roadmap.json` | `knowledge/commands/` | 150 KB | Systematic learning plan |
| `condensed_command_knowledge.json` | `knowledge/commands/` | 174 KB | Tiered token-optimized knowledge |
| 13+ MCP tools | `server.py` | ~600 lines | Interactive learning, experiment, consolidate |

As typed coverage increases, this infrastructure should shrink toward its
residual durable roles:

- fallback support during migration
- route-discovery input for promotion candidates
- test material drawn from real command observations

Practical right-sizing plan:
1. Keep it as fallback support during migration
2. Audit what still falls through as typed coverage expands
3. Deprecate interactive learning tools first (already partially done: `rhino_command_learn` is hard-disabled)
4. Eventually gate `rhino_command` behind a flag or reduce it to a narrow escape hatch

### Interactive Command Protocol (narrow-survivor candidate)

Four C++ routes + four MCP tools for interactive dialogue:
- `POST /command/start`, `POST /command/send`, `GET /command/prompt`, `POST /command/cancel`
- `rhino_command_interactive_start`, `_send`, `_prompt`, `_cancel`

This should follow the same right-sizing trajectory as the broader command
system. Its durable role is narrower: operations where ambiguity resolution
during execution is genuinely part of the semantics, not just an artifact of a
human-oriented UI.

---

## Decision Record

This section resolves the architectural, contract, and policy questions that the
surrounding gap analysis depends on. It is the binding output of a consistency
audit of existing C++ handlers (`BooleanHandler`, `CreateHandler`,
`BlocksHandler`, `LayerOpsHandler`, `GeometryOpsHandler`, `SplitTrimHandler`)
plus the C# companion bridge (`src/Rook/InternalBridge/`), filtered by one test:
does the difference from alternatives add purposeful value, or is it accidental
variation? Anything codified here is a rule future typed routes must follow.
Anything listed as an open question is deferred to the plan stage.

### 1. Strategic framing

**Optimization target.** The primary goal is to give agents machine-usable
contracts for common modeling intents. Latency, reliability, and response
quality are downstream symptoms, not separate priorities. Ship contracts that
are unambiguous at the schema level, validate early, and return structured
output sufficient for chaining.

**Success metric.** Workflow-weighted reachability, not route count. The measure
is: of high-frequency agent intents observed in practice, what fraction execute
through stable typed contracts without falling back to command-oriented paths?
Route-count coverage remains useful only as a rough backlog signal.

**End state for `rhino_command`.** Fallback-only during migration, then narrow
escape hatch for operations where ambiguity resolution is genuinely part of the
semantics (not an artifact of a human-oriented UI). Not retired entirely.

*Why this framing:* The theory-of-capability shift above makes coverage-by-count
the wrong measure. Counting rewards typing the easiest 196 commands;
workflow-weighting rewards typing the commands that actually run in practice.

### 2. Architectural rules (gold extracted from the audit)

These seven rules are binding on all new typed routes and are the convergence
target for existing drift.

1. **Outer response envelope is mandatory: `{success: bool, data: T}`.**
   Structured error payloads (`{errorCode, errorMessage}` as `data`) are the
   target shape. String-only error data is transitional — acceptable for
   existing code during cleanup, not for new routes.

2. **Two-stage validation.** Pure JSON / schema validation happens on the
   worker thread before dispatch. Document-dependent validation (object
   existence, layer presence, type checks against Rhino state) happens on the
   UI thread before mutation. Main-thread code throws classified exceptions
   (currently `std::invalid_argument` for input errors, `std::runtime_error`
   for Rhino-side failures — no formal taxonomy yet); the `.get()` boundary
   catches and converts to structured error response.

3. **One semantic route per operation, or a family endpoint with a closed,
   substrate-shared discriminator.** `/boolean` with
   `operation: union|difference|intersection|split` is a legitimate family
   endpoint — one substrate, fixed discriminator set. Avoid broad polymorphic
   endpoints where the discriminator is open and substrates diverge across
   cases.

4. **One UndoScope per request.** Batch operations wrap a single UndoScope
   around the per-item loop. Per-item success/failure is reported in the
   response; undo remains atomic.

5. **Response contract by operation class:** creators return full
   `ObjectSnapshot` (`{id, type, layer, name, visible, color, bbox}`);
   mutations return sparse metadata (`{count, ids, operation-specific}`);
   queries return the queried shape. This is a *contract*, not a performance
   optimization — agents depend on it for reasoning.

   **Cardinality convention for creators.** A creator route's response shape
   depends on its declared cardinality contract (stated in the handler
   header and in the route's plan-stage execution block):

   - **Singular contract** — the route always returns one object. Response
     is bare `ObjectSnapshot`. Pipe is singular-by-design: the route takes
     first-or-default from `Brep.CreatePipe`'s array return and declares it
     singular. Revolve and basic primitives are singular by SDK shape.
   - **Plural contract** — the route returns all objects produced, wrapped
     as `{objects: [ObjectSnapshot, ...]}` unconditionally, even when
     N = 1. Loft and Sweep default here because their RhinoCommon factories
     can produce multiple disjoint Breps, and discarding would lose
     information the agent needs for chaining.

   A route that sometimes returns bare and sometimes returns an array
   depending on runtime cardinality is drift — pick one contract per
   route and enforce it.

6. **Execution substrate is explicit per route.** Direct Rhino C++ SDK,
   `RunScript` + diff tracking, or managed callback via P/Invoke are three
   distinct choices with different failure modes and threading implications.
   Each new route records its substrate *and* the rationale for choosing it
   over the other two (native-reachability, managed API requirement, crash
   history) in the handler header. Substrate without rationale is substrate
   by accident. For managed-bridge routes, additionally distinguish whether
   the route **reuses an existing bridge callback** (e.g. `CreateGeometry`)
   or **adds a new callback surface** (which bumps `BridgeAbiVersion` per
   §3 discipline). Reusing is the default; adding is a deliberate
   architectural choice that must be argued on clarity grounds, not
   presented as a technical necessity.

7. **Batch mode is declared explicitly.** Each batch-capable route declares
   one of three modes in its handler header and response contract: *atomic*
   (all-or-nothing within one UndoScope, rollback on any failure),
   *best-effort* (attempt all items, report aggregate success), or
   *partial-success with per-item reporting* (response carries per-item
   status array). Implicit batch semantics are drift; explicit declaration
   makes the contract inspectable.

### 3. Boundary and ownership

Native vs. companion is **deliberate mixed ownership**, not drift. Two
separable decisions are at play, and the policy binds them distinctly:

- **Native routing** — `RookNative` is and remains the sole HTTP / public
  surface. This is a durable architectural commitment: one place for
  contract enforcement, validation, threading, and request lifecycle. Not
  revisited per route.
- **Native implementation** — whether a route's *geometry work* runs in
  native C++ SDK or delegates to managed RhinoCommon via the companion. A
  per-route empirical choice, judged on capability coverage and
  implementation risk, not on language preference.

The C++ native plugin is the sole HTTP server; some routes execute in-process
(direct SDK), others delegate to the C# companion via an ABI-registered bridge
(`NativeGhBridgeRegistrar`, `BridgeAbiVersion = 12`). Block routes notably
shifted to companion-backed implementations after native-path crash
reproductions.

What *is* drift today: route-ownership policy lives in handler comments
rather than as a binding rule. **Policy (codified here):**

- Default to native C++ direct SDK when the capability is reachable that way
  and the implementation is direct and stable.
- Delegate to the C# companion when (a) the capability requires
  RhinoCommon-only APIs, (b) managed-side state ownership is already
  established (canonical example: the block-handler family, where
  `InstanceDefinition` lifecycle and reference tracking are already owned by
  the companion), or (c) native-path crash patterns are known and
  reproducible. The decision is recorded in the handler's opening comment
  with rationale and in the per-route entry of this Decision Record's Phase
  plan.
- For modern geometry factories (surface creation beyond basic primitives,
  SpaceMorph deformations, SubD operations, advanced mesh), condition (a)
  applies **by default** — RhinoCommon is the canonical capability surface.
  Native direct-SDK remains the right choice for basic primitives, booleans,
  offsets, transforms, and operations with established C++ SDK coverage.
  The presumption is substrate-per-coverage, not language preference.
- Companion delegation that *adds a new bridge callback* bumps
  `BridgeAbiVersion` per the established append-only discipline. **Reusing
  an existing callback does not bump the version.**
- Grasshopper routes remain permanently companion-backed (no C++ GH API).

**Open (plan stage):** which Phase 1 surface operations reach RhinoCommon-only
APIs that require companion delegation. Tentative read: Loft, Pipe, Revolve,
Sweep1 are plausibly native-reachable; Patch, NetworkSrf, BlendSrf almost
certainly companion-only. Resolved per-operation in the plan stage.

### 4. Contract standards

**Error taxonomy.** Each handler defines a small closed set of error codes
(`invalid_input`, `not_found`, `operation_failed`, plus handler-specific).
`SendError` vs. `SendErrorData` usage must be consistent within and across
handlers — `SendErrorData` for structured payloads, `SendError` for transitional
string errors during cleanup only.

**Input schema.** Canonical parameter names: `id` for single-object operations,
`ids: [uuid]` for multi-object, role-based names (`cutterIds`, `railId`) for
multi-actor operations. Ingress aliasing is legitimate but policed: aliases are
defined in the handler's parse helper, not invented ad-hoc in request bodies.

**Alias / back-compat policy.** Existing alias shims (e.g. `BlocksHandler
::ParseUuidsFromAliases` accepting `["ids", "objectIds"]`) are preserved. New
routes ship with the canonical name only; aliases are added reactively to fix
real migration breaks, not proactively.

**Batch atomicity** *(target for new routes; existing handlers are mixed)*.
Current behavior is inconsistent: `LayerOpsHandler` is explicitly best-effort
(batch wraps in one UndoScope but per-item failures do not roll back), while
`GeometryOps` delete is partial-success (`success = (deletedCount > 0)` with
`failedIds` in data). Target for new routes: each batch declares its mode
explicitly per Rule 7. Default mode for new routes is atomic (all-or-nothing
within one UndoScope) unless partial-success or best-effort is intentional and
justified in the handler header.

**HTTP status semantics** *(target convergence, not current practice)*.
Current native behavior (`RookServer.cpp`) sets HTTP 400 for both `SendError`
and `SendErrorData`. Target for new routes: HTTP 200 on any envelope that
deserializes, including `{success: false}`; HTTP 4xx/5xx reserved for
request-level failures (malformed JSON, route not found, unrecoverable server
error). Rationale: `{success}` is the agent-observable outcome channel; HTTP
status is the transport channel. Existing handlers converge during the drift
cleanup pass.

**Tolerance sourcing.** Operations that require geometric tolerance accept an
optional `tolerance` parameter; default is `doc.ModelAbsoluteTolerance` when
omitted. Whether tolerance is *required* vs. *optional* is a per-operation
decision in the plan stage, but the naming and default are fixed here. Never
hardcoded.

### 5. Naming (layer alignment)

For each new operation, the intent key, MCP tool name, route path, and handler
function name must be derivable from each other. Canonical form:

| Layer | Example |
|---|---|
| Intent key | `create_pipe` |
| MCP tool name | `rhino_create_pipe` |
| Route path | `POST /surface/pipe` |
| Handler function | `HandleCreatePipe` (or `HandlePipe` within `SurfaceHandler`) |

Existing cross-layer mismatches (`name` vs. `namePattern`, `bbox` vs.
`bboxMin` / `bboxMax` in the selection handler) must be fixed before any new
selection predicates are added — a pre-condition of Contract Gap Category 8.

### 6. Drift cleanup ordering

Before adding new typed routes, the following drift is corrected in this order:

1. **Structured error responses everywhere.** Adopt `LayerOps`
   `{errorCode, errorMessage}` pattern. Fix `SendError` vs. `SendErrorData`
   inconsistency. Highest leverage — unblocks agent error-recovery and
   learning.
2. **Route ownership + execution substrate policy** recorded per existing
   route. Each handler's opening comment names its substrate and its
   native-vs-companion decision with rationale. Preserves the deliberate
   boundary and makes it inspectable.
3. **Canonical input schema + alias cleanup.** Fix `/select` contract mismatch
   first (`name` vs. `namePattern`, `bbox` vs. `bboxMin`/`bboxMax`), then
   document alias policy per handler.
4. **Batch mode declaration per route** (Rule 7). Each batch-capable handler
   states its mode — atomic, best-effort, or partial-success — in the header
   and response contract. Higher architectural leverage than cosmetic
   normalization because batch semantics are currently implicit and
   inconsistent.
5. **Optional parameter bundle normalization.** Creators accept
   `{name?, layer?, color?, visible?}` top-level; mutators use
   `{set: {field: value}, mode?}`; operations use `{updateAttributes: {...}}`
   for post-op cosmetics. Includes fixing the silent color-ignore bug at
   `CreateHandler.cpp:107`.
6. **Deferred: `CreateHandler` multiplexing split.** Real drift, but route
   churn with broad blast radius and client-migration cost. Defer until 1–5
   are done and the cost is justified by agent-behavior data.

### 7. Open questions (plan stage)

Genuinely unresolved; tracked as plan-stage decisions, not blockers for
drafting:

- **Per-operation substrate assignments for Phase 1 targets** (Loft / Sweep1
  / Sweep2 / Pipe / Revolve / Array*). Resolved by reading RhinoCommon API
  availability per op.
- **Empirical interactive-fallback matrix for Phase 1.** Which Phase 1
  commands actually stall with scripted prefixes in Rhino 8? One-session lab
  spike grounds prioritization within the phase.
- **Sweep1 + Sweep2 as one handler or two.** Shared alignment semantics argue
  for one; distinct input shapes argue for two. Resolved per-op in the plan.
- **`rhino_loft` / `rhino_sweep` legacy handling.** Remove-and-re-add in a
  precursor PR, or fix in-place when the real handler ships? Low-stakes but
  needs a call.

---

## Implementation Roadmap

### Phase 1: Fundamentals (covers ~80% of daily modeling)

This phase targets the most important contract gaps inherited from the original
command-first premise: common modeling intents that should be first-class
machine contracts but still fall through to command-oriented execution.

**New handler: `SurfaceHandler.cpp`**
- `POST /surface/loft` — Loft through curves
- `POST /surface/sweep1` — Single-rail sweep
- `POST /surface/sweep2` — Two-rail sweep
- `POST /surface/pipe` — Pipe around curve
- `POST /surface/revolve` — Revolve profile
- `POST /surface/extrude-face` — Extrude surface face
- `POST /surface/cap` — Cap planar holes

**New handler: `ArrayHandler.cpp`**
- `POST /array/linear` — Linear array
- `POST /array/rectangular` — Rectangular grid
- `POST /array/polar` — Circular array

**Extend `CreateHandler.cpp`:**
- `ELLIPSE` — center, xRadius, yRadius
- `TORUS` — center, majorRadius, minorRadius
- `POLYGON` — center, radius, sides
- `HELIX` — axis, radius, turns/pitch
- `SPIRAL` — axis, startRadius, endRadius, turns

**For each new operation:**
1. C++ handler with input validation + structured response
2. Route registration in `RookServer.cpp`
3. MCP tool in `server.py` with proper schema
4. CapabilityRouter entry in `intent_runtime.py`
5. Fix dead `rhino_loft` / `rhino_sweep` to point at new handler

**Estimated new operations: ~15**
**Post-Phase 1 route-count coverage: ~121/196 (62%) — up from 54%**

### Phase 2: Professional Modeling

**Extend `SurfaceHandler.cpp`:**
- `POST /surface/patch` — Patch surface
- `POST /surface/network` — Network surface
- `POST /surface/edge` — Edge surface
- `POST /surface/blend` — Blend surface
- `POST /surface/fillet` — Surface fillet
- `POST /surface/offset` — Surface offset

**Extend `CurvesHandler.cpp`:**
- `POST /curve/blend` — Curve blend
- `POST /curve/boolean` — Curve boolean

**New handler: `AnnotationHandler.cpp` (or extend CreateHandler):**
- `POST /annotation/dot` — Text dot
- `POST /annotation/text` — 2D annotation text
- `POST /annotation/dim-linear` — Linear dimension
- `POST /annotation/leader` — Leader

**New handler: `UserTextHandler.cpp`:**
- `POST /usertext/set` — Set object user text
- `GET /usertext/get` — Get object user text
- `POST /usertext/document-set` — Set document user text
- `GET /usertext/document-get` — Get document user text

**Extend `/select` handler:**
- Add `closedCurves`, `openCurves`, `duplicates`, `small` filter params

**Estimated new operations: ~16**
**Post-Phase 2 route-count coverage: ~137/196 (70%)**

### Phase 3: Advanced Operations

**New handler: `DeformHandler.cpp`:**
- `POST /deform/twist` — Twist
- `POST /deform/bend` — Bend
- `POST /deform/taper` — Taper
- `POST /deform/shear` — Shear
- `POST /deform/orient` — Orient by frames
- `POST /deform/flow` — Flow along surface

**Remaining primitives in CreateHandler:**
- `TUBE` — Tube (thick-walled cylinder)
- `PYRAMID` — Pyramid
- `ELLIPSOID` — 3D ellipsoid

**Estimated new operations: ~9**
**Post-Phase 3 route-count coverage: ~146/196 (74%)**

### Phase 4: Long Tail + Deprecation

- Audit remaining ~50 commands — many are viewport/UI commands that may not
  need typed routes (camera manipulation, display modes — already have typed
  viewport/display routes)
- Deprecate interactive learning tools
- Gate `rhino_command` behind a flag for emergency use only
- Remove dead MCP tools
- Archive command knowledge data (keep for reference, stop active use)

---

## Implementation Pattern

For each new typed route, follow this exact pattern:

### 1. C++ Handler (e.g., `SurfaceHandler.cpp`)

```cpp
void HandleLoft(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Parse + validate on worker thread
    std::vector<ON_UUID> curveIds;
    try {
        curveIds = ParseUuids(body, "curveIds");
        if (curveIds.size() < 2)
            throw std::invalid_argument("Loft requires at least 2 curves");
    } catch (...) { ... }

    // Execute on UI thread
    auto future = Dispatch([docSn, curveIds, ...]() -> WriteResult {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Loft");

        // Resolve curves, call RhinoCommon, create Brep
        // ...

        WriteResult wr;
        wr.success = true;
        wr.data = Serializer::SerializeObject(snapshot);
        return wr;
    });
}
```

### 2. Route Registration (`RookServer.cpp`)

```cpp
svr.Post("/surface/loft", Handlers::HandleLoft);
```

### 3. MCP Tool (`server.py`)

```python
Tool(
    name="rhino_loft",
    description="Create a lofted surface through profile curves.",
    inputSchema={
        "type": "object",
        "properties": {
            "curveIds": {
                "type": "array", "items": {"type": "string"},
                "description": "GUIDs of profile curves (minimum 2)"
            },
            "loftType": {
                "type": "string",
                "enum": ["Normal", "Loose", "Tight", "Straight"],
                "description": "Loft fitting type (default: Normal)"
            },
            "closed": {
                "type": "boolean",
                "description": "Close the loft (default: false)"
            },
        },
        "required": ["curveIds"]
    }
)
```

### 4. CapabilityRouter Entry (`intent_runtime.py`)

```python
routes["loft"] = RouteSpec(
    endpoint="/surface/loft",
    required_params=("curveIds",),
    optional_params=("loftType", "closed", "name", "layer"),
    description="Loft surface through profile curves",
)
```

### 5. CATEGORIES Update

```python
"surface_creation": (
    "loft", "sweep1", "sweep2", "pipe", "revolve",
    "extrude_face", "cap",
),
```

---

## Key RhinoCommon API References

### Surface Creation
| Operation | RhinoCommon Method |
|-----------|-------------------|
| Loft | `Brep.CreateFromLoft(curves, start, end, loftType, closed)` |
| Sweep1 | `Brep.CreateFromSweep(rail, shapes, closed, tolerance)` |
| Sweep2 | `Brep.CreateFromSweep(rail1, rail2, shapes, closed, tolerance)` |
| Pipe | `Brep.CreatePipe(rail, radius, localBlending, cap, fitRail, tolerance, angleToleranceRadians)` |
| Revolve | `RevSurface.Create(curve, axis, startAngle, endAngle)` then `.ToBrep()` |
| ExtrudeFace | `Brep.CreateFromOffsetFace()` or extrude face curves |
| Cap | `brep.CapPlanarHoles(tolerance)` |
| Patch | `Brep.CreatePatch(geometry, startSurface, ...)` |
| NetworkSrf | `NurbsSurface.CreateNetworkSurface(...)` |
| EdgeSrf | `NurbsSurface.CreateEdgeSurface(curves)` |
| BlendSrf | `Brep.CreateBlendSurface(face1, edge1, ...)` |
| FilletSrf | `Brep.CreateFilletSurface(face1, uv1, face2, uv2, radius, ...)` |
| OffsetSrf | `Brep.CreateOffsetBrep(brep, distance, solid, ...)` |

### Array Operations
| Operation | Approach |
|-----------|----------|
| Linear | Loop: `Transform.Translation(direction * i) + doc.Objects.Transform()` |
| Rectangular | Double loop: `Translation(xDir * i + yDir * j)` |
| Polar | Loop: `Transform.Rotation(angle * i, axis, center)` |

### Primitives
| Type | RhinoCommon |
|------|-------------|
| Ellipse | `new Ellipse(plane, xRadius, yRadius)` |
| Torus | `new Torus(plane, majorRadius, minorRadius)` |
| Polygon | `Polyline` from computed vertices |
| Helix | `NurbsCurve.CreateSpiral(axisStart, axisDir, ...)` |
| Spiral | `NurbsCurve.CreateSpiral(...)` with varying radius |

### Deformation
| Operation | RhinoCommon |
|-----------|-------------|
| Twist | `TwistSpaceMorph` |
| Bend | `BendSpaceMorph` |
| Taper | `TaperSpaceMorph` |
| Shear | `Transform.Shear(plane, x, y, z)` |
| Orient | `Transform.PlaneToPlane(source, target)` |
| Flow | `FlowSpaceMorph` |

---

## Metrics and Success Criteria

The table below uses route-count coverage as a rough planning signal only. It is
useful for backlog sizing, but it is not the primary success metric. The real
measure is whether high-frequency workflows stop falling through to
command-oriented execution.

| Metric | Current | Phase 1 | Phase 2 | Phase 3 |
|--------|---------|---------|---------|---------|
| Typed operations | 106 | ~121 | ~137 | ~146 |
| Route-count coverage (of 196 learned commands) | 54% | 62% | 70% | 74% |
| Surface creation routes | 0 | 7 | 13 | 13 |
| Array routes | 0 | 3 | 3 | 3 |
| Avg LLM calls for covered ops | 1 | 1 | 1 | 1 |
| Avg LLM calls for uncovered ops | 2-3 | 2-3 | 2-3 | 2-3 |
| Interactive fallback risk | High | Medium | Low | Low |

Primary success criteria:

- the model can create a lofted surface, swept profile, pipe, or polar array
  without touching `rhino_command`
- common workflows shift from command-oriented fallthrough to stable typed
  contracts with structured outputs
- route-count coverage rises, but only as a secondary indicator of harness
  maturity

---

## Emerging Gap: Director Actor Capture Contract

**Logged:** 2026-07-02

RookVisionDirector now has strict v2 actor metadata persistence and runtime
reading through `rhino_director_write_actor_metadata_v2` and
`rhino_director_read_actor_metadata_v2`. Those tools define the durable
`.rook/...` ref protocol and the file shape for ActorSet, ActorSubset,
ActorGrouping, and SelectionSnapshot metadata.

That is not the same as a complete capture/classification contract. The current
writer accepts a supplied semantic bundle; it does not yet own the full product
workflow for:

- capturing current live Rhino object facts for an animation candidate set;
- deriving accepted actor subsets from explicit classifier inputs;
- deriving accepted band/grouping metadata from current geometry;
- producing clean Director metadata without relying on a previous prototype
  metadata file as a scaffold.

This gap surfaced during Pearson V2 recovery. The clean project target is a
portable `.3dm + .rook` pair whose Director metadata looks freshly captured for
that file and can travel to another machine without any original v1 metadata.
For the transitional Pearson V2 dataset, it is acceptable to use the old curated
v1 metadata only as an accepted-decision scaffold for membership and band
grouping, then rewrite clean v2 metadata from current live model facts through
the production v2 writer.

This should not become the long-term authoring model. The durable fix is a
Director capture/classifier tool or component contract that emits the semantic
bundle from current Rhino state using explicit inputs and validated classifier
parameters. Once that exists, recovery or transport should never require
consulting an older metadata schema to reconstruct ActorSet, ActorSubset, or
ActorGrouping structure.

## Appendix A: Complete CapabilityRouter Operation List (106)

```
# Creation (20)
create_point, create_line, create_polyline, create_circle, create_arc,
create_rectangle, create_box, create_sphere, create_cylinder, create_cone,
create_extrusion, create_interpolated_curve, create_control_point_curve,
create_mesh_box, create_mesh_sphere, create_mesh_cylinder, create_mesh_cone,
create_subd_box, create_subd_sphere, create_subd_cylinder

# Transform (6)
move, rotate, scale, mirror, copy, delete

# Boolean (4)
boolean_union, boolean_difference, boolean_intersection, boolean_split

# Surface/Edge (3)
fillet_edge, chamfer_edge, offset_brep

# Curves (12)
join_curves, explode_curve, divide_curve, extend_curve, trim_curve,
split_curve, rebuild_curve, fillet_curves, project_curve, pull_curve,
offset_curve, offset_curve_on_surface

# Intersection (5)
intersect_curves, intersect_curve_surface, intersect_curve_brep,
intersect_breps, intersect_plane

# Split/Trim (4)
split_brep, trim_brep, split_face, split_disjoint_breps

# Mesh (8)
mesh_from_brep, mesh_boolean, mesh_repair, mesh_smooth, mesh_weld,
mesh_unweld, mesh_reduce, quad_remesh

# SubD (6)
subd_from_mesh, subd_from_surface, subd_subdivide, subd_crease,
subd_to_brep, subd_to_mesh

# Layers (7)
create_layer, delete_layer, set_layer_visibility, lock_layer,
set_current_layer, set_layer_properties, set_layer_properties_batch

# Blocks (31)
create_block, insert_block, explode_block, delete_block, rename_block,
set_block_layers, set_block_layers_batch, set_block_materials,
set_block_materials_batch, set_block_object_colors, set_block_object_colors_batch,
set_block_object_user_strings, set_block_object_user_strings_batch,
set_block_object_names, set_block_object_names_batch,
transform_block_instance, transform_block_instance_batch,
purge_blocks, replace_block_geometry, replace_block_object_geometry,
transform_block_object, replace_block_instance, replace_block_instance_batch,
reset_block_instance_scale, link_block, unlink_block, refresh_block,
find_block_instances, block_objects_detailed, set_block_instance_visibility

# Groups (2)
create_group, ungroup

# Materials (7)
create_material, delete_material, assign_material,
uv_box_mapping, uv_planar_mapping, uv_cylinder_mapping, uv_sphere_mapping

# Selection (1)
select_objects

# Document (3)
save_document, new_document, set_units

# IO (2)
import_file, export_file

# Game Export (3)
tag_semantic, validate_export, game_export
```

## Appendix B: C++ Handler Files (36)

```
src/RookNative/Handlers/
  AnalysisHandler.cpp          — 13 analysis routes
  BlocksHandler.cpp            — 38 block routes
  BooleanHandler.cpp           — 1 boolean route
  CommandHandler.cpp           — 2 routes (/command, /execute) ← NAIVE MODEL
  CommandInteractiveHandler.cpp — 4 routes (start/send/prompt/cancel) ← NAIVE MODEL
  CreateHandler.cpp            — 1 route (/create, 13 types)
  CurvesHandler.cpp            — 12 curve operation routes
  DisplayModeHandler.cpp       — 2 routes
  DocumentHandler.cpp          — 2 routes
  DocumentOpsHandler.cpp       — 6 routes
  FilletChamferHandler.cpp     — 2 routes
  GameExportHandler.cpp        — 5 routes
  GeometryHandler.cpp          — geometry query
  GeometryOpsHandler.cpp       — 5 routes (delete/transform/copy/undo/redo)
  GrasshopperProxyHandler.cpp  — ~36 GH routes
  GroupsHandler.cpp            — 4 routes
  GumballContextHandler.cpp    — 6 routes
  GumballHandler.cpp           — 4 routes
  ImportExportHandler.cpp      — 2 routes
  IntersectionHandler.cpp      — 6 routes
  LayerOpsHandler.cpp          — 12 routes
  LayersHandler.cpp            — 1 route (GET /layers)
  LinetypesHandler.cpp         — 2 routes
  MaterialsHandler.cpp         — 5 routes
  MeasureHandler.cpp           — 12 routes
  MeshHandler.cpp              — 12 routes
  ObjectsHandler.cpp           — 3 routes
  OffsetBrepHandler.cpp        — 1 route
  PromptHandler.cpp            — 5 routes
  SceneGraphHandler.cpp        — 8 routes
  SelectionHandler.cpp         — 2 routes
  SessionHandler.cpp           — 4 routes
  SplitTrimHandler.cpp         — 4 routes
  SubDHandler.cpp              — 9 routes
  TextureMappingHandler.cpp    — 4 routes
  ViewportHandler.cpp          — 3 routes
```
