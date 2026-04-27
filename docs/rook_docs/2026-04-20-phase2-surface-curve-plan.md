# Phase 2 Surface/Curve Extension Plan

**Date:** 2026-04-20
**Stage:** plan (worked-example gate pending)
**Basis:**
- `rook_docs/2026-04-20-phase2-surface-curve-spike.md` — empirical fallback
  matrix, substrate decisions, taxonomy, campaign PR slices.
- `rook_docs/2026-04-15-typed-route-gap-analysis.md` — `## Decision Record`
  (7 binding architectural rules, boundary policy, contract standards).
- `rook_docs/2026-04-17-typed-route-phase1-plan.md` — Phase 1 plan; this
  plan explicitly inherits its Common Plan patterns instead of restating.
- `rook_docs/2026-04-19-typed-route-phase2-plan.md` — Phase 2 (annotation +
  usertext) plan, closed 2026-04-19. This plan is a **Phase 2 extension**
  (Category 5 surface ops + Category 4 curve ops) and does not reopen it.

**Scope:** 5 endpoints / 7 intent keys. 4 PR slices.

---

## Plan Inputs

### Decision Record

Source: `rook_docs/2026-04-15-typed-route-gap-analysis.md` — `## Decision Record`
(signed off 2026-04-17, already load-bearing for Phase 1 + Phase 2 PR-0..PR-10).
This plan binds to:

- **Rule 1:** outer envelope `{success, data}` mandatory; structured errors.
- **Rule 2:** worker-thread JSON validation, UI-thread document-dependent validation.
- **Rule 3:** one semantic route per operation (or closed-discriminator family endpoint).
- **Rule 4:** one UndoScope per request (batch = one scope around the loop).
- **Rule 5:** creators return full `ObjectSnapshot`; mutations return sparse metadata.
- **Rule 5 cardinality convention:** singular-contract vs plural-contract routes
  declare their shape in the handler header; plural wraps even N=1 responses as
  `{objects: [...]}`.
- **Rule 6:** execution substrate explicit with rationale in handler header.
  **Reuse-vs-add distinction:** reusing an existing bridge callback does NOT
  bump `BridgeAbiVersion`; adding a new callback surface does.
- **Rule 7:** batch mode declared explicitly.
- **§3 boundary:** native-routing (durable) vs native-implementation (per-route).
- **§4 contract standards:** error-taxonomy base set, canonical param naming,
  tolerance-sourcing discipline.

### Empirical fallback matrix (spike 2026-04-20)

Source: `rook_docs/2026-04-20-phase2-surface-curve-spike.md` (live-Rhino probe).

| Candidate | Outcome | Key observation | Conclusion |
|---|---|---|---|
| EdgeSrf | cleanly | 3 lines triangle → 1 brep via `_SelId` chain | `typed route useful` |
| BlendCurves | stalled | `_-BlendCrv` rejects `_SelId`; options whitelist is bulge/continuity/reverse only | `typed route urgent` |
| Patch | stalled | `_-Patch` rejects `_SelId`; options whitelist is command_line_mode/surface_parameters only | `typed route urgent` |
| NetworkSrf | stalled | `_-NetworkSrf` rejects `_SelId`; options whitelist is Edge/Interior continuity + tol + TrimAndSplit | `typed route urgent` |
| CurveBoolean | stalled | `_-CurveBoolean` rejects `_SelId`; options whitelist is AllRegions/CombineRegions/None | `typed route urgent` |
| BlendSrf | ambiguous | `executed=true, objectsCreated=0` — silent no-op; deferred from campaign | `typed route urgent` (defer) |
| FilletSrf | cleanly | `_SelId × 2` default radius → 3 opaque breps; deferred from campaign | `typed route useful` (defer) |

**Prioritization:** 5 urgent / 2 useful of 7 live candidates. Same pattern as
Phase 1 (5 urgent / 3 useful). BlendSrf + FilletSrf deferred to a follow-up
campaign (see Non-goals).

### Current route / tool state

| Component | Path | State |
|---|---|---|
| Native `SurfaceHandler` | `src/RookNative/Handlers/SurfaceHandler.{cpp,h}` | Phase 1 — Pipe / Loft / Sweep1 / Sweep2 / Revolve routes live; managed-bridge reuse via `CreateGeometry`; `_strictAttributes` convention codified in the header. This plan extends it with `HandleEdgeSrf`, `HandlePatch`, `HandleNetworkSrf`. |
| Native `CurvesHandler` | `src/RookNative/Handlers/CurvesHandler.{cpp,h}` | Today: 12 curve-op routes on `direct-sdk` substrate. This plan adds `HandleBlendCurves` and `HandleCurveBoolean` on `managed-bridge (reuse)` substrate — **first mixed-substrate handler in the codebase**. Substrate declared per-route in file header. |
| Managed `CreateHandler` | `src/Rook/Handlers/CreateHandler.cs` | Already dispatches PIPE / LOFT / SWEEP1 / SWEEP2 / REVOLVE / INTERPOLATED_CURVE / CONTROL_POINT_CURVE; strict-attribute + plural-dispatch gating in place. This plan adds EDGE_SRF / PATCH / NETWORK_SRF / BLEND_CRV singular cases + CURVE_BOOLEAN plural case. |
| Plural insert helper | `CreateHandler.cs :: InsertBrepsAsPluralResponse` (`CreateHandler.cs:1398`) | `Brep[]`-only via `doc.Objects.AddBrep`. **PR-4 adds parallel `InsertCurvesAsPluralResponse` using `doc.Objects.AddCurve`** — NOT generalizing the Brep helper. See PR-4 sub-plan for rationale. |
| Bridge ABI | `NativeGhBridgeRegistrar.cs:20` | `BridgeAbiVersion = 12` — unchanged by this plan. All 5 new routes reuse the existing `CreateGeometry` callback; **zero ABI bump**. |
| MCP tools | `mcp_server/src/rook/server.py` | None of the 5 new tool names (`rhino_create_edge_srf`, `rhino_blend_curves`, `rhino_create_patch`, `rhino_create_network_srf`, `rhino_curve_boolean_union / _difference / _intersection`) exist today. |
| CapabilityRouter | `mcp_server/src/rook/learning/intent_runtime.py` | Phase 1 surface intents live (`create_pipe` / `create_loft` / etc.). None of the 7 new intent keys (`create_edge_srf`, `create_patch`, `create_network_srf`, `blend_curves`, `curve_boolean_union`, `curve_boolean_difference`, `curve_boolean_intersection`) exist. |
| Audit test | `mcp_server/tests/test_capability_router_phase2_coverage.py` | Phase 2 coverage-of-coverage test exists (annotation + usertext). **Hard-wired to annotation/usertext prefixes** via `PHASE2_ENDPOINT_PREFIXES = ("/annotation/", "/usertext/")` at `:68` and `/(?:annotation|usertext)/` regex in `_server_py_typed_endpoints` at `:97-105`. Extending coverage to `/surface/*` + `/curve/*` requires a sibling audit file, NOT a tuple-list extension — see §Campaign exit criterion for the refactor details and PR placement. |

### Non-goals for this campaign

- **BlendSrf** and **FilletSrf** — deferred to a follow-up campaign. Both
  require structured primitives that do not exist anywhere in the Rook
  contract today:
  - BlendSrf: edge-on-face reference `{brepId, faceIndex, edgeIndex, t0, t1, reverse, continuity}`
  - FilletSrf: UV-point-on-face reference `{brepId, faceIndex, u, v, radius}`
  Shipping these requires (a) canonical schema forms, (b) cross-handler
  serialization discipline, and (c) ≥1 non-inventor caller to validate the
  shape. Correct pattern: park with `trigger_to_revisit = "when a companion
  route needs the same schema primitive"`. Work-queue Parked entry to be
  added as part of PR-1 scope pass.
- **OffsetSrf** — already shipped as `/offset/brep` via native
  `RhinoOffsetBrep` (direct-sdk substrate, `OffsetBrepHandler.cpp`). Dropped
  from scope. Gap-analysis §Category 5 OffsetSrf row is stale hygiene; update
  bundled into PR-1 scope pass.
- **CurveBoolean region form** — `Curve.CreateBooleanRegions(curves, plane, regionPoints, combineRegions, tol)` with per-region metadata is a different operation shape (point-picker driven). Deferred from PR-4; PR-4 ships only the simple `CreateBooleanUnion / _Difference / _Intersection(curves, tol)` overloads. Region form becomes a follow-up if a workflow needs it.
- **Independent per-end continuity for BlendCurves.** RhinoCommon
  `Curve.CreateBlendCurve` accepts `cont1` + `cont2` independently. PR-1
  ships with a single `continuity` applied to both ends (matching Rhino's UI
  common case); asymmetric form is deferred.
- **Drift cleanup on existing handlers** — `SendError` → `SendErrorData`
  conversion, HTTP status convergence, batch atomicity normalization — all
  Decision Record §6 items, not in this campaign's scope. New routes inherit
  the target patterns from day one.
- **Extraction of Phase 1 surface routes into a new handler** — not needed;
  SurfaceHandler.cpp is the canonical home for `/surface/*` creators and
  absorbs the three new surface routes cleanly.
- **Workflow-weighted coverage telemetry** — valuable but independent;
  not gating this campaign.

---

## Common Plan

Patterns and defaults inherited from the Phase 1 plan's Common Plan
(`rook_docs/2026-04-17-typed-route-phase1-plan.md`). This section lists only
the **extensions and deltas** — not the full Phase 1 rules, which remain in
force verbatim.

### Substrate decision (all 5 routes)

All 5 routes: `managed-bridge (reuse)` via existing `CreateGeometry` callback
(`NativeGhBridgeRegistrar.cs:107`). Zero ABI bump. Every route adds a new
`type` string to the dispatcher in `CreateHandler.cs:150`. Rationale per route
follows the spike memo's substrate-rationale boilerplate (§Substrate Rationale
Text): RhinoCommon-only API + reuse of an existing callback surface. Crucially
different from Phase 1 Pipe, where the managed factory was already live —
**every Phase 2 Category 5/4 route adds net-new managed factory code in
`CreateHandler.cs`**.

### Handler-level defaults

All inherit from Phase 1 verbatim (Rule 1 envelope, worker-thread
`invalidInput` lambda, `ParseBodyAndDocSn`, `CRookServer::SendSuccess` /
`SendErrorData`, `_strictAttributes` opt-in, attribute bundle `{name?, layer?, color?, visible?}`).

**New convention introduced by this plan:**

- **First `managed-bridge (reuse)` extension to `CurvesHandler.cpp`** — the
  handler gains `HandleBlendCurves` and `HandleCurveBooleanX` on the
  managed-bridge substrate. Substrate is declared per-route in the function's
  leading comment block; the file header acquires a paragraph pointing at
  the mixed-substrate rhythm:

  > Substrate: 12 existing routes are `direct-sdk` native; `HandleBlendCurves`
  > and `HandleCurveBooleanX` (PR-1 + PR-4, 2026-04-20 Phase 2 extension) are
  > `managed-bridge (reuse)` via the `CreateGeometry` callback. Per-route
  > substrate is named in each handler's opening comment (Rule 6).

### BlendCurves — first strict singular-curve proof point

Phase 1 strict-attribute routes were all brep creators. BlendCurves is the
first `_strictAttributes=true` creator whose factory returns a `Curve` (not
a `Brep`). The managed singular-geometry path at `CreateHandler.cs:246`
already uses `doc.Objects.Add(geometry, attributes)` — class-agnostic —
and the attribute-application block above it (name / layer / color /
visible) operates on `ObjectAttributes` independent of geometry class. So
the risk is lower than initially feared, but not zero:

- **Serialization parity:** `RhinoSerializer.SerializeObject` must return
  the same `{id, type, layer, name, visible, color, bbox}` shape for a
  curve as for a brep. Tests must verify — existing `INTERPOLATED_CURVE`
  exercises the serializer on a curve but NOT under strict mode.
- **Strict layer-lookup on a curve:** the `layer` rejection path
  (`CreateInvalidInputException` at `CreateHandler.cs:205`) must trip
  correctly before the curve is added. Covered by a happy-path + bad-layer
  test in PR-1.
- **Color handling on curve objects:** per-object color on a curve is
  supported by `ObjectAttributes`; no geometry-specific handling needed.

Acceptance criterion for the PR-1 worked example: at least one BlendCurves
test asserts a full strict-mode failure (bad layer) AND at least one
asserts strict-mode success with all attribute bundle fields set, with
the response echoing the applied attributes.

### CurveBoolean — plural-curve helper scope

PR-4's single largest implementation item: add
`InsertCurvesAsPluralResponse(doc, curves, attributes, factoryName)` next
to `InsertBrepsAsPluralResponse` at `CreateHandler.cs:1398`. Rationale:

- Keeps the well-understood Brep helper untouched.
- Leaves generalization (one helper dispatching per `GeometryBase`
  subclass) as an optional later-hygiene step, judged on third-caller
  pressure.
- Cleanly signals the substrate distinction: today only LOFT / SWEEP1 /
  SWEEP2 route through `InsertBrepsAsPluralResponse`; CURVE_BOOLEAN
  routes through `InsertCurvesAsPluralResponse`.

The parallel helper is ~30–40 lines and straightforward — call
`doc.Objects.AddCurve(curve, attributes)`, enforce non-empty on return,
build `{objects: [snapshot, ...]}` payload. Atomicity rule unchanged:
any failure mid-loop MUST throw `CreateOperationFailedException` to let
the enclosing `BeginUndoRecord`/`doc.Undo()` roll back.

### Taxonomy (inherited from spike memo §Campaign exit criterion)

| Intent | Endpoint | Tool name | Expected `CATEGORIES` bucket |
|---|---|---|---|
| `create_edge_srf` | `/surface/edge` | `rhino_create_edge_srf` | `creation` |
| `create_patch` | `/surface/patch` | `rhino_create_patch` | `creation` |
| `create_network_srf` | `/surface/network` | `rhino_create_network_srf` | `creation` |
| `blend_curves` | `/curve/blend` | `rhino_blend_curves` | `curves` |
| `curve_boolean_union` | `/curve/boolean` (`operation=union`) | `rhino_curve_boolean_union` | `curves` |
| `curve_boolean_difference` | `/curve/boolean` (`operation=difference`) | `rhino_curve_boolean_difference` | `curves` |
| `curve_boolean_intersection` | `/curve/boolean` (`operation=intersection`) | `rhino_curve_boolean_intersection` | `curves` |

Adding 4 entries to `CATEGORIES["curves"]` (blend_curves + 3 curve_boolean_*) updates the `test_all_curve_ops` count constant at `test_intent_runtime.py:392` from **12 → 16**. That edit lands in whichever PR adds the curve intents; currently split across PR-1 (adds `blend_curves`) and PR-4 (adds 3 `curve_boolean_*`). Both PRs must touch the same test constant; no shared-state conflict because the edits are numeric and monotonic.

---

## Worked Example: `/surface/edge`

EdgeSrf is chosen as the worked example because it is (a) the simplest
surface creator in the campaign, (b) the only `useful`-labeled surface
candidate (scripted form works, typed route still wins on response
quality), and (c) inherits the Pipe substrate pattern with zero surprises
— validating the "pure inheritance" premise before PRs 2–4 extend it with
net-new plural-helper / big-knob-API / multi-intent-single-endpoint
complexity.

### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Substrate** | `managed-bridge (reuse)` — native HTTP entry delegates to C# companion via the existing `CreateGeometry` bridge callback (`NativeGhBridgeRegistrar.cs:107`). New `type: "EDGE_SRF"` in `CreateHandler.cs:150` singular switch. No ABI bump. | Rule 6; Decision Record §3 |
| **Substrate rationale** | `Brep.CreateEdgeSurface(IEnumerable<Curve> curves)` is a RhinoCommon-only static factory. No native C++ SDK equivalent. Native re-implementation would require building a new native C++ factory path from scratch (no `RhinoEdgeSrf` exists). Managed-bridge reuse (a) inherits the Phase 1 `_strictAttributes` attribute contract and (b) extends an existing callback surface at zero ABI cost. | Rule 6; §3 condition (a) |
| **Native/managed owner** | **Native owns:** HTTP route registration, JSON parse, curveIds schema validation (count 2..4, each a valid UUID), attribute bundle syntactic check, dispatch to `DispatchToManagedCreate`. **Managed owns:** new `CreateEdgeSrf(doc, request)` method in `CreateHandler.cs`, factory invocation (`Brep.CreateEdgeSurface`), attribute application on the returned Brep, `doc.Objects.AddBrep`, `ObjectSnapshot` serialization. | §3 |
| **Route path** | `POST /surface/edge` | Rule 3 |
| **Handler / file** | Native: `src/RookNative/Handlers/SurfaceHandler.cpp :: HandleEdgeSrf` (new function; header declaration in `SurfaceHandler.h`). Managed: `src/Rook/Handlers/CreateHandler.cs :: CreateEdgeSrf` (new private method). Singular dispatch at `CreateHandler.cs:150` gains `"EDGE_SRF" => CreateEdgeSrf(doc, request)`. | Rule 3 |
| **MCP tool impact** | New tool `rhino_create_edge_srf` in `server.py`. No conflicts. | §5 naming alignment |
| **CapabilityRouter impact** | New entry `"create_edge_srf" → /surface/edge` in `intent_runtime.py`. Required params: `curveIds`. Optional: `name`, `layer`, `color`, `visible`. Added to `CATEGORIES["creation"]` alongside `create_loft` / `create_pipe`. | §5; Spike memo §Campaign exit criterion |
| **Input schema** | `curveIds: [uuid] REQUIRED`, min length 2, max length 4, each a valid UUID; attribute bundle `{name?, layer?, color?, visible?}` per Common Plan. No tolerance, no loftType, no other knobs. | Rule 2 |
| **Tolerance rule** | **Omitted from schema.** `Brep.CreateEdgeSurface` takes no tolerance parameter. Follows Loft/Revolve precedent where the API doesn't expose tolerance. | §4 |
| **Undo / batch mode** | Single-object route; one `UndoScope` (via `BeginUndoRecord`/`doc.Undo()` in the enclosing managed handler). Not batch-capable. N/A for Rule 7. | Rule 4 |
| **Result cardinality policy** | **Singular contract.** `Brep.CreateEdgeSurface` returns a single `Brep?`. Null result → `operation_failed` (error code from `CreateOperationFailedException`). | Rule 5 |
| **Response shape** | Creator class → bare `ObjectSnapshot` `{id, type, layer, name, visible, color, bbox}`. | Rule 5 |
| **Error taxonomy** | Base set (`invalid_input`, `not_found`, `operation_failed`) + route-specific `invalid_curve_count` for count outside 2..4. Layer / color / visible strict rejections surface as `invalid_input` from the managed path. | Rule 1 |
| **Tests** | `tests/live_rhino/test_edge_srf_characterization.py`: (a) 3 lines triangle → 1 brep (happy path; spike probe geometry); (b) 2 parallel lines with gap → 1 brep (**empirically verified 2026-04-20 via spike — factory accepts disconnected inputs; contract does NOT promise boundary closure**); (c) 4 lines quad → 1 brep (max count boundary); (d) 1 curve → `invalid_curve_count` (worker-thread rejection); (e) 5 curves → `invalid_curve_count` (**worker-thread rejection — API specced 2-4 but `_-EdgeSrf` command UI happily takes 5 per 2026-04-20 probe; the typed route enforces the API-documented upper bound ≤ 4 explicitly**); (f) malformed UUID → `invalid_input`; (g) non-curve ID (point object) → `invalid_input` (managed doc-dependent path); (h) unknown layer with strict mode → `invalid_input` (managed-strict path); (i) malformed color → `invalid_input`; (j) happy path with full attribute bundle → verify response echoes applied attrs; (k) **`test_factory_permissive_smoke`** — pathological input (zero-length curve pair, or 4 disjoint far-apart lines) succeeds with valid ObjectSnapshot; pins the factory's permissive behavior as a contract observation per Acceptance Gate #5 amendment. Following PR #51 harness pattern. | — |
| **PR slice** | **PR-1 (worked example, bundled with BlendCurves).** Establishes the Phase 2 extension pattern on both surface and curve namespaces simultaneously. See BlendCurves sub-plan for the curve-namespace details. | — |

### Binding rule refs (summary)

| Rule | How EdgeSrf applies it |
|---|---|
| 1 | `{success, data}` envelope via `SendSuccess` / `SendErrorData`; error `data` is `{errorCode, errorMessage}` |
| 2 | `curveIds` count + UUID-format validated on worker thread; curve existence + curve-ness (is-a-curve) validated on UI thread (managed) |
| 3 | Dedicated route `/surface/edge`, not `/create` multiplex |
| 4 | One UndoScope wrapping the managed-bridge call (reused from managed `BeginUndoRecord`/`doc.Undo()`) |
| 5 | Full `ObjectSnapshot` on success; singular-contract cardinality policy stated |
| 6 | Substrate `managed-bridge (reuse)` with RhinoCommon-only rationale in handler header; reuses existing `CreateGeometry` callback; no new callback surface added |
| 7 | N/A (not batch-capable) |
| §3 boundary | Condition (a): RhinoCommon-only API. No ABI bump |
| §4 tolerance | N/A — API does not expose a tolerance parameter |

---

## Acceptance Gate

Before PR-2 / PR-3 / PR-4 templates are final, the PR-1 worked example
(EdgeSrf + BlendCurves) must pass all five gate questions:

1. **Did the 12-row execution block expose all fields needed?** If a
   sub-plan would leave a real decision ambiguous, add a field.
2. **Did any Decision Record rule prove too vague or too strong?** If so,
   amend the Record, not the PR-1 scope.
3. **Does the BlendCurves singular-curve strict-attribute proof point
   hold?** Verify the serialization / layer-rejection / color-handling
   paths behave identically for a curve as for a brep under
   `_strictAttributes=true`. Any surprise here is a Phase 1 common-plan
   amendment, not a PR-1 carve-out.
4. **Does the PR-4 plural-curve helper choice (parallel
   `InsertCurvesAsPluralResponse`) still read clean after PR-1 ships?**
   Trigger to revisit: if PR-1 review surfaces pressure to generalize
   the Brep helper instead, pivot PR-4's approach before that PR opens.
5. **Rhino-side failure characterization — Common Plan amendment trigger.**
   Phase 1 Common Plan (`2026-04-17-typed-route-phase1-plan.md:257`)
   requires every new typed route to ship with "at least one Rhino-side
   failure (e.g. degenerate input)" test. Empirical probing 2026-04-20
   against both PR-1 factories:

   - `Brep.CreateEdgeSurface`: 5 attempts — 3 lines general position, 2
     parallel lines with gap, 2 coincident, 2 zero-length, 4 disjoint
     far-apart, 4-curve 3D tetrahedron path, 3 all-zero-at-origin — **all
     produced valid breps.**
   - `Curve.CreateBlendCurve` (overload 1): 3 attempts — coincident
     curves, zero-length endpoint, degenerate 2-point NURBS — **all
     produced valid blends.**

   Both factories are empirically **extremely permissive**. Rather than
   contrive a pathological input that may behave differently in Rhino 9
   or across tolerance settings, this gate **fires as a Common Plan
   amendment, landed in the source-of-truth file**
   `rook_docs/2026-04-17-typed-route-phase1-plan.md` at the **Test shape**
   line (within the ### Handler-level defaults section). The amended
   rule now reads:

   > "Rhino-side failure test when reachable; otherwise a permissiveness
   > note in the handler header AND a dedicated `test_factory_permissive_smoke`
   > case pinning one canonical sane input plus one pathological-looking
   > input (zero-length / coincident / degenerate / disjoint) both
   > succeeding — pinning the permissive behavior itself as a contract
   > observation."

   Applies retroactively to Phase 1 + Phase 2 campaigns; no retroactive
   PR required (prior campaigns happened to ship cases that fail
   naturally).

   **PR-1 implementation:** both EdgeSrf and BlendCurves ship with a
   permissiveness note in their native handler headers citing this
   amendment, AND a `test_factory_permissive_smoke` test that asserts
   both a sane input AND a pathological input return 200 with valid
   ObjectSnapshot. Drops the "at least one operation_failed" expectation
   for these two routes. All other error-code tests (invalid_input,
   invalid_curve_count, invalid_continuity, layer-strict, color-strict)
   remain unchanged.

   **Scope-pass action:** user + Codex sign off on the amendment wording
   before PR-1 implementation. If the amendment is rejected, PR-1 must
   find a genuine operation_failed case (≥3 more empirical attempts per
   route) before merging.

Codex review is the primary gate check; user signs off after review.

---

## PR Sub-plans

Shared across all 5 routes (not restated per-route):

- Route namespaces: `/surface/*` (3 routes) and `/curve/*` (2 routes)
- Native handler files: `SurfaceHandler.cpp` (+ `.h`) for surface routes;
  `CurvesHandler.cpp` (+ `.h`) for curve routes.
- MCP tool namespace: `rhino_create_*` for surface + primitive-creator curves;
  `rhino_blend_curves` and `rhino_curve_boolean_*` follow the `/curve/*`
  intent-key naming (see taxonomy in Common Plan).
- Substrate: `managed-bridge (reuse)` via `CreateGeometry` callback. No ABI
  bump on any of the 5 routes.
- Substrate rationale boilerplate: per spike memo §Substrate Rationale Text.
- Native/managed owner split: per EdgeSrf worked example.
- Validation staging: worker-thread schema; UI-thread (managed) document-
  dependent.
- UndoScope: one per request via managed `BeginUndoRecord`/`doc.Undo()`.
- Error taxonomy base: `invalid_input`, `not_found`, `operation_failed`.
  Route-specific codes listed per sub-plan.
- Response contract: singular-contract routes return bare `ObjectSnapshot`;
  plural-contract routes return `{objects: [...]}` unconditionally.
- Category membership: per taxonomy table in Common Plan.

---

### `/curve/blend` — BlendCurves (in PR-1 with EdgeSrf)

**Urgency:** urgent (spike: `_-BlendCrv` rejects `_SelId`; options whitelist is bulge/continuity/reverse only).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `curve1Id: uuid REQUIRED`; `curve2Id: uuid REQUIRED`; `continuity: enum("Position"\|"Tangency"\|"Curvature")` OPTIONAL default `"Tangency"`; attribute bundle per Common Plan. **Uses `Curve.CreateBlendCurve(curveA, curveB, continuity)` — overload 1.** No `reverse1`/`reverse2` flags, no `bulge`, no `t`-on-curve params; those belong to other overloads deferred per §Non-goals. (Earlier plan drafts specced a 6-arg reverse-flag signature that does not exist in RhinoCommon — corrected 2026-04-20 via empirical introspection of `Curve.CreateBlendCurve` overload set.) | Rule 2 |
| **Route / handler** | `POST /curve/blend` → `CurvesHandler::HandleBlendCurves` (**new** function, first managed-bridge route in CurvesHandler.cpp). Managed: new `CreateHandler.CreateBlendCurve(doc, request)` singular method; `CreateHandler.cs:150` switch gains `"BLEND_CRV" => CreateBlendCurve(doc, request)`. | Rule 3 |
| **Substrate** | `managed-bridge (reuse)` via `CreateGeometry` (new type `"BLEND_CRV"`). No ABI bump. | Rule 6 |
| **Tolerance rule** | **Omitted from schema.** `Curve.CreateBlendCurve` does not expose a tolerance parameter. | §4 |
| **Undo / batch mode** | Single-object, one UndoScope. Not batch-capable. N/A Rule 7. | Rule 4 |
| **Result cardinality** | **Singular contract.** `Curve.CreateBlendCurve` returns `Curve?`. Null result → `operation_failed`. | Rule 5 |
| **Response shape** | Bare `ObjectSnapshot` — full `{id, type, layer, name, visible, color, bbox}`. **First strict-attribute response on a curve** (not a brep). Managed serializer already supports curves in non-strict; strict parity pinned by tests (h) and (j) below. | Rule 5; Common Plan §BlendCurves proof point |
| **Route-specific error codes** | `invalid_continuity` (enum mismatch). | Rule 1 |
| **Tests** | `tests/live_rhino/test_blend_curves_characterization.py`: (a) 2 open lines with gap → 1 blend curve, continuity="Tangency" default (happy path); (b) each continuity enum value (Position/Tangency/Curvature) produces a non-null curve with measurable length difference (empirical distinction — no exact-form assertion); (c) invalid continuity string → `invalid_continuity`; (d) missing `curve1Id` → `invalid_input`; (e) non-curve ID (point object) → `invalid_input` (managed doc-dependent path); (f) unknown layer with strict → `invalid_input` (**strict-curve proof point**); (g) malformed color → `invalid_input`; (h) happy path with full attribute bundle → response echoes applied attrs (**strict-curve proof point**); (i) **`test_factory_permissive_smoke`** — pathological input (coincident curves OR zero-length + valid curve) succeeds with valid ObjectSnapshot; pins the factory's permissive behavior as a contract observation per Acceptance Gate #5 amendment. Coincident, zero-length, and degenerate curve inputs all produced valid outputs during 2026-04-20 empirical probe against overload 1; factory is permissive same as EdgeSrf. | — |
| **PR slice** | **PR-1 (bundled with EdgeSrf).** Two simplest routes, one per namespace. First mixed-substrate change to CurvesHandler.cpp. | — |

#### Explicit rejections

- Overload 2 `bulge` parameters (`bulgeA`, `bulgeB` doubles)
- Overload 3 full-control parameters (`t0`, `reverse0`, `t1`, `reverse1`,
  asymmetric continuity). "Which end to blend from" is picked by the
  factory's default-end selection; surfacing `reverse` or `t`-on-curve
  to the contract is a follow-up PR once a workflow justifies it.
- Independent per-end continuity (`continuity0` vs `continuity1`)
- Tolerance parameter (overloads 1 + 2 don't expose one; overload 3 also
  has no tolerance param)

---

### `/surface/patch` — Patch (PR-2)

**Urgency:** urgent (spike: `_-Patch` rejects `_SelId`).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `geometryIds: [uuid] REQUIRED` (min 1; curves, points, or point clouds); `startingSurfaceId: uuid` OPTIONAL; `uSpans: int` OPTIONAL default 10; `vSpans: int` OPTIONAL default 10; `flexibility: number` OPTIONAL default 1.0; `surfacePull: number` OPTIONAL default 1.0; `tolerance: number` OPTIONAL default `doc.ModelAbsoluteTolerance`; attribute bundle per Common Plan. Deferred: `trim`, `tangency`, `pointSpacing`, `fixEdges`. | Rule 2 |
| **Route / handler** | `POST /surface/patch` → `SurfaceHandler::HandlePatch`. Managed: `CreateHandler.CreatePatch(doc, request)`. New `"PATCH"` case in singular switch. | Rule 3 |
| **Substrate** | `managed-bridge (reuse)` (new type `"PATCH"`). No ABI bump. | Rule 6 |
| **Tolerance rule** | **Optional**, default `doc.ModelAbsoluteTolerance`. Factory accepts explicit tolerance. | §4 |
| **Result cardinality** | **Singular contract.** `Brep.CreatePatch` returns `Brep?`. | Rule 5 |
| **Response shape** | Bare `ObjectSnapshot`. | Rule 5 |
| **Route-specific error codes** | `invalid_spans` (`uSpans` or `vSpans` ≤ 0 or not integer); `invalid_flexibility` (`flexibility` ≤ 0); `invalid_geometry_class` (input ID is not a curve/point/point-cloud). | Rule 1 |
| **Tests** | `tests/live_rhino/test_patch_characterization.py`: (a) 4 interpolated-curve boundary → 1 brep (happy path; spike probe geometry); (b) curves + extra interior points → 1 brep fits both; (c) with startingSurfaceId → uses seed; (d) `uSpans=2` (low) → coarse fit; (e) missing `geometryIds` → `invalid_input`; (f) `uSpans=0` → `invalid_spans`; (g) `flexibility=-1` → `invalid_flexibility`; (h) brep input in `geometryIds` → `invalid_geometry_class`; (i) happy path with full attribute bundle. | — |

#### Explicit rejections

- `trim` bool flag — deferred
- `tangency` bool flag — deferred
- `pointSpacing` number — deferred
- `fixEdges` bool[] per starting-surface edge — deferred
- `preserveEdges` — deferred (not in any API overload; RhinoScript only)

Workflow evidence required before lifting any deferral.

---

### `/surface/network` — NetworkSrf (PR-3)

**Urgency:** urgent (spike: `_-NetworkSrf` rejects `_SelId`).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | XOR between two forms: **auto-detect form:** `curveIds: [uuid]` (min 2); **explicit form:** `uCurveIds: [uuid]` + `vCurveIds: [uuid]`. Additionally: `continuity: int` OPTIONAL default 1 (∈ {0,1,2} — Position/Tangency/Curvature); `edgeTolerance`, `interiorTolerance`, `angleTolerance: number` OPTIONAL (defaults from doc). Attribute bundle. XOR violation → `invalid_input`. | Rule 2 |
| **Route / handler** | `POST /surface/network` → `SurfaceHandler::HandleNetworkSrf`. Managed: `CreateHandler.CreateNetworkSrf(doc, request)`. New `"NETWORK_SRF"` case in singular switch. | Rule 3 |
| **Substrate** | `managed-bridge (reuse)` (new type `"NETWORK_SRF"`). No ABI bump. | Rule 6 |
| **Tolerance rule** | 3 optional tolerances, each with its own doc default (edge/interior → `ModelAbsoluteTolerance`; angle → `ModelAngleToleranceRadians`). | §4 |
| **Result cardinality** | **Singular contract.** Factory returns `NurbsSurface?`. Insert as brep via `Brep.CreateFromSurface(nurbsSurface)` for response-shape parity with other `/surface/*` routes (Rule 5 consistency). | Rule 5 |
| **Response shape** | Bare `ObjectSnapshot`, `type` field resolves to `"Brep"` (post-wrap). | Rule 5 |
| **Route-specific error codes** | `input_form_conflict` (both `curveIds` AND `uCurveIds`/`vCurveIds` provided); `input_form_incomplete` (one of `uCurveIds` / `vCurveIds` provided without the other); `invalid_continuity` (int not in {0,1,2}); `network_build_failed` (factory's `out int error` non-zero — message includes the numeric code where known). | Rule 1 |
| **Tests** | `tests/live_rhino/test_network_srf_characterization.py`: (a) 4 lines (2 U + 2 V as single list, auto-detect) → 1 brep (happy path; spike probe geometry); (b) explicit `uCurveIds` + `vCurveIds` → 1 brep (same result); (c) both forms provided → `input_form_conflict`; (d) only `uCurveIds` → `input_form_incomplete`; (e) `continuity=0`, `=1`, `=2` → each produces a brep (non-null); (f) `continuity=3` → `invalid_continuity`; (g) curves that don't form a network → `network_build_failed` with error message; (h) happy path with full attribute bundle. | — |

#### Explicit rejections

- Auto-insert of the raw `NurbsSurface` without brep wrap (shipped as brep
  for `ObjectSnapshot` parity with other `/surface/*` routes)
- Exposing the raw numeric error code to callers beyond the error message
  (pattern: map well-known codes to human-readable sub-messages, keep the
  enum opaque to the schema)

---

### `/curve/boolean` — CurveBoolean (PR-4, three intent keys)

**Urgency:** urgent (spike: `_-CurveBoolean` rejects `_SelId`).

PR-4 is **the most implementation-heavy PR of the campaign.** Scope:

1. **New plural-curve helper** in `CreateHandler.cs`:
   `InsertCurvesAsPluralResponse(doc, curves, attributes, factoryName)`.
   ~30–40 lines. Parallel to `InsertBrepsAsPluralResponse` at `:1398`;
   calls `doc.Objects.AddCurve`. Atomicity rule preserved.
2. **New plural-dispatch case** at `CreateHandler.cs:134` alongside
   `LOFT` / `SWEEP1` / `SWEEP2`:
   `"CURVE_BOOLEAN" => CreateCurveBooleanPlural(doc, request)`.
3. **New managed factory method** `CreateCurveBooleanPlural(doc, request)`.
   Branches on `request["operation"]` for arity check and factory selection.
4. **New native handler** `CurvesHandler::HandleCurveBoolean` on
   `managed-bridge (reuse)` substrate. Same mixed-substrate rhythm as
   `HandleBlendCurves` from PR-1.
5. **Three intent keys, one endpoint** — `curve_boolean_union` /
   `_difference` / `_intersection` all route to `POST /curve/boolean`
   with different `operation` param defaults. Mirrors the brep-boolean
   pattern.
6. **`CATEGORIES["curves"]` count update** from 13 (post-PR-1) to 16
   (adds `curve_boolean_union` / `_difference` / `_intersection`); same
   test-constant edit site as PR-1.

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `operation: enum("union"\|"difference"\|"intersection") REQUIRED`; `curveIds: [uuid]` REQUIRED — for `union`, min 2; for `difference` / `intersection`, exactly 2 (element 0 = curveA, element 1 = curveB); `tolerance: number` OPTIONAL default `doc.ModelAbsoluteTolerance`; attribute bundle per Common Plan. | Rule 2 |
| **Route / handler** | `POST /curve/boolean` → `CurvesHandler::HandleCurveBoolean`. Managed: `CreateHandler.CreateCurveBooleanPlural(doc, request)` (**plural**); new `"CURVE_BOOLEAN"` case in `CreateHandler.cs:134` strict-plural dispatch. | Rule 3 |
| **Substrate** | `managed-bridge (reuse)` (new type `"CURVE_BOOLEAN"`). No ABI bump. **Adds `InsertCurvesAsPluralResponse` helper.** | Rule 6; Common Plan §CurveBoolean plural-helper |
| **Tolerance rule** | Optional, default `doc.ModelAbsoluteTolerance`. | §4 |
| **Undo / batch mode** | Single-request, one UndoScope (via `BeginUndoRecord`). Not batch-capable across operations. Atomicity via `InsertCurvesAsPluralResponse`: any insert failure throws, `doc.Undo()` rolls back. | Rule 4; Rule 7 — atomic single-request |
| **Result cardinality** | **Plural contract.** `Curve.CreateBooleanUnion` / `_Difference` / `_Intersection` return `Curve[]?`. Null or empty result → `operation_failed` (not a successful empty response). `{objects: [...]}` unconditionally, even when N=1. | Rule 5 cardinality convention |
| **Response shape** | `{objects: [ObjectSnapshot, ...]}`. Each snapshot a full creator shape. | Rule 5 |
| **Route-specific error codes** | `invalid_operation` (enum mismatch); `invalid_curve_count` (union with < 2, or difference/intersection with != 2); `non_planar_input` (curves not coplanar — factory returns null, map the diagnostic). | Rule 1 |
| **Tests** | `tests/live_rhino/test_curve_boolean_characterization.py`: (a) union of 2 overlapping circles → multiple curves (spike probe geometry); (b) difference of 2 overlapping circles → 1 or more curves; (c) intersection → 1 or more curves; (d) union of 3 overlapping closed curves → multiple curves; (e) `operation="union"` with 1 curve → `invalid_curve_count`; (f) `operation="difference"` with 3 curves → `invalid_curve_count`; (g) `operation="xor"` → `invalid_operation`; (h) non-planar (curves in different Z planes) → `non_planar_input`; (i) disjoint closed curves, `operation="intersection"` → `operation_failed` (factory returns empty — normalize to operation_failed per cardinality rule); (j) happy path with full attribute bundle on union result; (k) plural-helper atomicity: dispatch an input that produces ≥ 2 curves and verify all inserted ids survive or all roll back (via `_debug` seam if needed — defer if debug seam wasn't re-added in Phase 2). | — |
| **PR slice** | **PR-4 standalone.** Largest implementation scope of the campaign; do not bundle. | — |

#### Explicit rejections

- Region form (`Curve.CreateBooleanRegions`) — deferred. Region-point
  picker schema is a separate concern; follow-up PR.
- `combineRegions` flag — deferred (region-form parameter).
- Expanding the helper to `InsertGeometryAsPluralResponse` generic per
  `GeometryBase` subclass — deferred; parallel helper ships first,
  generalization judged later on third-caller pressure.

---

## Campaign Exit Criterion

The existing `test_capability_router_phase2_coverage.py` is **not
extensible by tuple-list alone** — it is hard-wired to annotation/usertext
prefixes (`PHASE2_ENDPOINT_PREFIXES = ("/annotation/", "/usertext/")` at
`:68` and the regex `/(?:annotation|usertext)/` in `_server_py_typed_endpoints`
at `:97-105`). Extending coverage to `/surface/*` + `/curve/*` has two
possible shapes:

**Option A — broaden the existing audit.** Generalize `PHASE2_ENDPOINT_PREFIXES`
and the regex in the same file; rename the file / variables to drop
"phase2" if needed. Single source of truth for typed-route audit
infrastructure. Trade-off: touches the stable annotation/usertext audit
inventory in the same diff that adds 7 new intents, bigger review surface,
easier to regress Phase 2 PR-1..PR-10 coverage assertions.

**Option B — sibling audit file.** Create
`mcp_server/tests/test_capability_router_phase2_surface_curve_coverage.py`
modeled on the existing file, with its own `PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS`
tuple list. **No prefix constant** — both the route-table inventory and
the executor inventory derive from the exact endpoint set of the tuple
list (see §Sibling-file audit contents for the derivation rule). Copies
~60 lines of accessor infrastructure (`_server_py_source`,
`_executor_case_labels`, etc.) verbatim. Trade-off: some duplication, but
keeps each campaign's audit assertions self-contained and independently
reviewable.

**Recommendation: Option B (sibling file).** The duplication is stable
(accessor helpers don't change) and the campaign-scoped audit pattern
is consistent with Phase 1's `test_capability_router_phase1_coverage.py`
(which is also a separate file from `test_capability_router_phase2_coverage.py`).
If duplication bite surfaces after this campaign, extract the shared
accessors into a small helper module — hygiene PR, not campaign-scope.

### Sibling-file audit contents

New file: `mcp_server/tests/test_capability_router_phase2_surface_curve_coverage.py`.

Parameter tuples `(intent, tool_name, endpoint, category)`:

```
PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS: list[tuple[str, str, str, str]] = [
    ("create_edge_srf",            "rhino_create_edge_srf",             "/surface/edge",    "creation"),
    ("create_patch",               "rhino_create_patch",                "/surface/patch",   "creation"),
    ("create_network_srf",         "rhino_create_network_srf",          "/surface/network", "creation"),
    ("blend_curves",               "rhino_blend_curves",                "/curve/blend",     "curves"),
    ("curve_boolean_union",        "rhino_curve_boolean_union",         "/curve/boolean",   "curves"),
    ("curve_boolean_difference",   "rhino_curve_boolean_difference",    "/curve/boolean",   "curves"),
    ("curve_boolean_intersection", "rhino_curve_boolean_intersection",  "/curve/boolean",   "curves"),
]
```

**Inventory derivation — NOT prefix-based.** Raw `/surface/*` and
`/curve/*` prefixes would overcapture already-shipped routes:
`create_pipe` / `create_loft` / `create_sweep1` / `create_sweep2` /
`create_revolve` on `/surface/*`; `join_curves` / `explode_curve` /
`divide_curve` / `extend_curve` / `trim_curve` / `split_curve` /
`rebuild_curve` / `fillet_curves` / `project_curve` / `pull_curve` /
`offset_curve` / `offset_curve_on_surface` on `/curve/*`. The symmetric
coverage-of-coverage checks would then complain about Phase 1 and
pre-Phase-1 routes that have nothing to do with this campaign.

**Derivation rule:** the audit's endpoint inventory comes from the
tuple list itself, not from a prefix heuristic.

```python
PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS: frozenset[str] = frozenset(
    endpoint for _, _, endpoint, _ in PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS
)
# => {"/surface/edge", "/surface/patch", "/surface/network",
#     "/curve/blend", "/curve/boolean"}

# Executor endpoint regex matches this exact set, NOT a wildcarded prefix.
_campaign_endpoint_alt = "|".join(
    re.escape(endpoint) for endpoint in sorted(PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS)
)
# The symmetric inventory check reads server.py for call_rhino(...) invocations
# whose endpoint is in PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS, NOT whose endpoint
# starts with /surface/ or /curve/.
```

This keeps the audit strictly scoped to the 5 campaign endpoints even
though two of them share a prefix (`/curve/blend` and `/curve/boolean`)
with the 12 pre-existing `/curve/*` routes. Follow-up route additions
in either namespace are picked up by extending the tuple list —
guaranteed campaign-scoped by construction.

Four per-intent surface tests + symmetric inventory checks, shaped
identically to the existing Phase 2 annotation+usertext audit file.

### PR placement

**The sibling-audit file is added in PR-4** alongside the CurveBoolean
route itself. Rationale: the audit must assert all 7 intents exist, and
all 7 only land by PR-4; shipping the audit earlier would require
`@pytest.mark.skip` entries per yet-unshipped intent — churn. The audit
green-bar becomes a merge gate on the final PR. Earlier PRs ship without
this audit (same rhythm Phase 1 used — PR #61 bundled the Phase 1
coverage audit after all Phase 1 routes merged).

**This keeps the campaign at 4 PRs** (per §Summary table and
introduction). The audit is PR-4 scope, not a separate PR-5.

### Completeness-count updates (in-lockstep with each PR)

Two `test_intent_runtime.py` completeness tests assert hard counts on
`CATEGORIES` buckets that this campaign mutates. Schedule:

| Test | Bucket | Pre-campaign | PR-1 | PR-2 | PR-3 | PR-4 |
|---|---|---|---|---|---|---|
| `test_all_geometry_creation_ops` (`test_intent_runtime.py:378`) | `creation` | **broken: asserts 20, actual 36** (Phase 2 annotation+usertext campaigns shipped without updating this constant) | 37 (+`create_edge_srf`; also fixes stale 20→36 drift) | 38 (+`create_patch`) | 39 (+`create_network_srf`) | 39 (no change — PR-4 adds only `curves` intents) |
| `test_all_curve_ops` (`test_intent_runtime.py:392`) | `curves` | 12 (accurate) | 13 (+`blend_curves`) | 13 | 13 | 16 (+`curve_boolean_union`/`_difference`/`_intersection`) |

**PR-1 picks up the pre-existing `creation` count drift** (20 → 36 →
37) as a bundled hygiene fix. Rationale: PR-1 already has to touch the
line, and splitting the "fix stale assertion" from "advance by 1" into
a separate PR would be unnecessary ceremony for a single integer
change. The PR description notes the drift-fix explicitly so the diff
doesn't look like over-reach.

Also sweep during PR-1 implementation:

- Any other `CATEGORIES[...]` hard-count assertion that drifted since
  Phase 2 annotation+usertext (run `git grep 'len(CATEGORIES'` — covers
  the pattern). Fix forward in-lockstep.
- Stale arithmetic comment at `test_intent_runtime.py:377` — line reads
  `# 13 NURBS + 4 mesh + 3 SubD = 20` directly above the
  `assert len(geo_create) == 20` line. Update to reflect post-campaign
  composition in lockstep with the count advance. (No analogous stale
  comment exists at `intent_runtime.py:1177`; earlier drafts of this
  plan pointed at the wrong file — corrected 2026-04-20 per Codex
  review.)

---

## Git Workflow

**Branch:** `fix/phase2-surface-curve-spike` holds the spike memo + this
plan doc. A dedicated feature branch per PR (e.g. `feat/phase2-edge-srf`)
is the default; bundle PR-1 routes (EdgeSrf + BlendCurves) on a single
branch because they ship together. Follow the `feedback_pr_workflow.md`
rhythm: fix/feat branches, squash merge, test-before-PR,
`gh pr merge --squash --delete-branch` one-shot finish.

**Scope-pass discipline** (per `feedback_pr_scoping_rhythm.md`): present
the execution-block table in chat BEFORE coding each PR; user/Codex
reviews the block; implement only after sign-off. Phase 1 caught 2–3
findings per PR this way; Phase 2 annotation PRs caught 2–4 per PR.
Expect at least one round on PR-4 specifically for the plural-helper
choice.

---

## Summary

| PR | Scope | Routes | Tool names | Intent keys | Test count budget |
|----|-------|--------|------------|-------------|-------------------|
| **PR-1** | Worked example — EdgeSrf + BlendCurves | `/surface/edge` + `/curve/blend` | `rhino_create_edge_srf` + `rhino_blend_curves` | `create_edge_srf` + `blend_curves` | ~20 live-Rhino tests |
| **PR-2** | Patch | `/surface/patch` | `rhino_create_patch` | `create_patch` | ~12 live-Rhino tests |
| **PR-3** | NetworkSrf | `/surface/network` | `rhino_create_network_srf` | `create_network_srf` | ~12 live-Rhino tests |
| **PR-4** | CurveBoolean (3 intents → 1 endpoint) + plural-curve helper + sibling campaign audit file | `/curve/boolean` | `rhino_curve_boolean_{union,difference,intersection}` | `curve_boolean_union` + `_difference` + `_intersection` | ~16 live-Rhino tests + sibling audit (4 per-intent surfaces × 7 intents + symmetric inventory) |

**Total campaign:** 4 PRs, 5 endpoints, 7 intent keys, ~60 live-Rhino tests,
zero ABI bumps. Coverage target unchanged from gap-analysis §Phase 2:
~70% route-count coverage (continuation of what Phase 2 already closed
from 62% → ~70%).
