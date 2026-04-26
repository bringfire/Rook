# Phase 1 Typed Route Plan

**Date:** 2026-04-17
**Stage:** plan (worked-example gate pending)
**Basis:** `rook_docs/2026-04-15-typed-route-gap-analysis.md` — `## Decision Record` (signed off 2026-04-17). This plan binds Phase 1 route work to the 7 architectural rules, boundary policy, and contract standards established there. The plan does not re-litigate Decision Record rules; if a rule proves too vague or too strong for a real route, the Record is amended formally, not carved around.

---

## Plan Inputs

### Decision Record

Source: `rook_docs/2026-04-15-typed-route-gap-analysis.md` — `## Decision Record` (7 binding rules + boundary policy + contract standards + drift cleanup ordering + 4 open plan-stage questions).

Rules referenced throughout this plan:
- **Rule 1:** outer envelope `{success, data}` mandatory; structured errors as target
- **Rule 2:** worker-thread JSON validation, UI-thread document-dependent validation
- **Rule 3:** one semantic route per operation (or closed-discriminator family endpoint)
- **Rule 4:** one UndoScope per request (batch = one scope around the loop)
- **Rule 5:** creators return full `ObjectSnapshot`; mutations return sparse metadata
- **Rule 6:** execution substrate explicit with rationale in handler header
- **Rule 7:** batch mode declared explicitly (atomic / best-effort / partial-success)

### Empirical interactive-fallback matrix

Source: `rook_docs/2026-04-17-typed-route-phase1-spike.md` (2026-04-17 run).

| Command | Outcome | Key observation | Conclusion |
|---|---|---|---|
| Loft | stalled | 15s timeout; multi-`_SelId` not supported | `typed route urgent` |
| Sweep1 | stalled | HTTP 400; multi-step selection rejected | `typed route urgent` |
| Sweep2 | ambiguous | silent no-op; `executed=true` with 0 objects | `typed route urgent` |
| Pipe | cleanly | 1 object created | `typed route useful` |
| Revolve | cleanly | 1 object created | `typed route useful` |
| ArrayRectangular | stalled | 15s timeout; `_Rectangular` option form rejected | `typed route urgent` |
| ArrayLinear | stalled | HTTP 400; command form rejected | `typed route urgent` |
| ArrayPolar | cleanly | 5 objects created | `typed route useful` |

**Prioritization:** 5 urgent (Loft, Sweep1, Sweep2, ArrayRectangular, ArrayLinear), 3 useful (Pipe, Revolve, ArrayPolar).

**Substrate finding carried forward:** Sweep2 returned `executed=true, objectsCreated=0` — a silent failure where the command-string parser accepts the syntax but no geometry forms. Reinforces Rule 2 (document-dependent validation on the UI thread) and the choice to prefer typed routes with pre-validation over command substrates even where the command path "runs."

### Current route / tool state

| Component | Path | State |
|---|---|---|
| MCP tool `rhino_loft` | `mcp_server/src/rook/server.py:2149` | **stale** — routes to `/create` with `type=LOFT` which `CreateHandler.cpp:662` rejects |
| MCP tool `rhino_sweep` | `mcp_server/src/rook/server.py:2164` | **stale** — routes to `/create` with `type=SWEEP1` which `CreateHandler.cpp:662` rejects |
| Native `/create` handler | `src/RookNative/Handlers/CreateHandler.cpp:662` | rejects LOFT / SWEEP1 / PIPE / REVOLVE as unknown types |
| C# companion `CreateHandler` | `src/Rook/Handlers/CreateHandler.cs` | has `CreatePipe` (line 649, uses `Brep.CreatePipe`), `CreateRevolve`, `CreateExtrude`; wired into `NativeGhBridgeRegistrar` (ABI v12) at line 26 — but no active HTTP route directs to these managed factories today |
| Bridge ABI | `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs:20` | `BridgeAbiVersion = 12` |
| MCP tools `rhino_pipe`, `rhino_revolve`, `rhino_sweep1`, `rhino_sweep2`, `rhino_array_*` | — | do not exist |

### Non-goals for Phase 1

Explicit boundaries to prevent scope creep:

- **Patch / NetworkSrf / BlendSrf / FilletSrf / OffsetSrf** — Phase 2 (Contract Gap Category 5)
- **Text / annotation / dimensions / hatch** — Phase 2 (Contract Gap Category 7)
- **User text / document user text** — Phase 2 (Contract Gap Category 9)
- **Deformations** (Twist, Bend, Taper, Shear, Flow, Orient) — Phase 3
- **`CreateHandler` multiplexing split** — deferred per Decision Record §6 drift cleanup step 6
- **Drift cleanup on existing handlers** (structured errors, HTTP status convergence, batch atomicity normalization) — separate track per Decision Record §6 steps 1–5; Phase 1 new routes inherit the target patterns from day one but do not rewrite existing handlers
- **Workflow-weighted coverage telemetry** — valuable but independent; not gating Phase 1

---

## Common Plan

Patterns and defaults that apply to every Phase 1 route. Each route's sub-plan references this section by rule number rather than restating.

### Native-routing vs native-implementation

Two decisions are in play on every route and should not be conflated:

- **Native routing** is a durable architectural commitment: `RookNative`
  owns the HTTP / public surface, contract enforcement, validation staging,
  threading, and request lifecycle. Not revisited per route.
- **Native implementation** is a per-route empirical choice: does the
  geometry work run in native C++ SDK, or does the route delegate to
  managed RhinoCommon via the companion bridge? Judged on capability
  coverage and implementation risk, not language preference.

Every Phase 1 sub-plan makes the implementation choice explicit in its
execution block. The answer is never "C++ is better" or "managed is cheaper"
— it is "this operation's capability surface and risk profile make this
substrate the right one." For modern geometry factories (surface creation
beyond basic primitives, SpaceMorph, SubD, advanced mesh), managed is the
default substrate because that is where the canonical capability lives. For
primitives, booleans, offsets, transforms, managed delegation would be
reinvention.

A substrate decision test (see below) makes the per-route judgment
consistent across routes.

### Substrate decision test

Use this test for every Phase 1 route. The output is not just a label
(`direct-sdk`, `managed-bridge`, `runscript`) but a short rationale that
states why one substrate earns the work and what the rejected substrates
fail to provide.

**Question 1: Why should this stay native?**

Choose `direct-sdk` when most of the following are true:

- The operation is directly reachable through Rhino's native C++ SDK using
  patterns already present in `RookNative` (primitives, booleans, offsets,
  transforms, object iteration, attribute edits).
- Native implementation keeps the contract simpler than bridge delegation
  would. A second substrate would add coordination cost without adding
  capability.
- The route needs fine-grained document inspection or mutation steps that
  are already expressed cleanly in native handlers.
- There is no meaningful capability advantage on the RhinoCommon side.

Reject `direct-sdk` when "native" is only a style preference. Native
implementation must buy either clearer control, lower risk, or less
architectural surface area.

**Question 2: Why should this delegate?**

Choose `managed-bridge` when any of the following are true:

- RhinoCommon is the canonical capability surface for the operation
  (`Brep.CreatePipe`, loft/sweep factories, SpaceMorph families, SubD
  builders, higher-level mesh factories).
- The codebase already has a mature managed implementation that would be
  duplicated by a native rewrite.
- Past crash history, state ownership, or SDK reachability already pushed
  this family of work into the companion.
- Reusing an existing callback surface keeps the public architecture clean
  while avoiding unnecessary ABI growth.

Delegation is not "managed is cheaper." It is justified when managed owns
the real capability and native would only be a thinner, riskier reimplementation.

**Question 3: What does one choice give that the other does not?**

This is the forcing question. Write one concrete sentence in the route plan:

- `direct-sdk` gives us `X` that `managed-bridge` does not.
- or `managed-bridge` gives us `Y` that `direct-sdk` does not.

If the answer is vague ("cleaner", "more native", "less weird"), the
decision is not ready. The difference must be purposeful.

**Bridge reuse vs bridge growth (Rule 6).**

If delegation wins, ask one more question:

- Can the route reuse an existing callback surface?

If yes, prefer reuse and do **not** bump `BridgeAbiVersion`.
If no, name the new callback surface and state why a new seam is worth the
ABI growth instead of routing through an existing managed entry point.

**Worked application: Pipe**

- Why not `direct-sdk`? Because `Pipe` is not a "basic primitive/boolean/
  offset/transform" case. The canonical factory in this codebase is the
  RhinoCommon call `Brep.CreatePipe`, already wrapped in
  `CreateHandler.CreatePipe`.
- Why `managed-bridge`? Because it gives us a proven geometry factory and
  existing route-adjacent implementation without adding a new public plugin
  surface.
- What does it give that native does not? A direct call to the mature pipe
  factory already present in the companion; native C++ would only add a
  second implementation path or a less-direct command/script workaround.
- Reuse or add? Reuse. `CreateGeometry` already exists, so `/surface/pipe`
  should route through an adapter on top of the current callback rather than
  inventing a new ABI seam.

### Handler-level defaults

**Response envelope (Rule 1).** All new handlers use `{success: bool, data: T}` with LayerOps-style structured errors `{errorCode, errorMessage}` as `data` on failure. Use `CRookServer::SendSuccess` for success and `CRookServer::SendErrorData` for every error path — worker-thread schema errors, main-thread document-dependent errors, and the top-level catch-all. `CRookServer::SendError` (string-only) is **not used** by Phase 1 routes; string-only envelopes break the contract. The PR-1 pattern is the canonical reference: a local `invalidInput` lambda at the top of the handler that wraps `SendErrorData` with `{errorCode: "invalid_input", errorMessage: <text>}`, invoked at every worker-thread validation failure site.

**Validation staging (Rule 2).** Worker thread parses JSON and validates shape / types / required fields / XOR exclusivity. On any shape error the handler returns via the `invalidInput` lambda (structured `{errorCode:"invalid_input", errorMessage}` via `SendErrorData`) — `std::invalid_argument` thrown by helpers like `ParseUuid` / `ParseUuids` is caught locally and rewrapped through the same path. Main-thread lambda validates document-dependent preconditions (object existence, type compatibility, closure state) and throws `std::invalid_argument` for input-semantic errors / `std::runtime_error` for Rhino-side failures; the `.get()` boundary catches both and emits structured errors via `SendErrorData` (mapping `invalid_argument` → `invalid_input` when the input was semantically malformed, otherwise → route-specific code like `not_found` / `operation_failed`).

**Error taxonomy base set.** Every new handler defines at minimum:
- `invalid_input` — schema-level or semantic input error
- `not_found` — referenced object does not exist
- `operation_failed` — Rhino-side operation returned no result or invalid output

Handler-specific codes extend this base (e.g. Pipe adds `invalid_radius`).

**Tolerance sourcing (Decision Record §4).** Optional `tolerance` parameter; defaults to `doc.ModelAbsoluteTolerance` when omitted. Plan-stage decision per route: required or optional. Never hardcoded.

**UndoScope (Rule 4).** One `UndoScope` per request. Batch operations (array family) wrap a single scope around the per-item loop. Per-item success/failure reported in response; undo remains atomic.

**Response shape by operation class (Rule 5 + cardinality convention).**
- **Singular-contract creators** (Pipe, Revolve): bare `ObjectSnapshot` — `{id, type, layer, name, visible, color, bbox}`. Route contract guarantees one object per invocation; first-or-default applied at the bridge boundary when the underlying factory returns an array.
- **Plural-contract creators** (Loft, Sweep1, Sweep2): `{objects: [ObjectSnapshot, ...]}` unconditionally, per Rule 5 cardinality convention. `Brep.CreateFromLoft` and `Brep.CreateFromSweep` can produce multiple disjoint Breps, and discarding would lose information. Plan-stage execution block declares the cardinality contract per route.
- **Arrays** (ArrayLinear, ArrayRectangular, ArrayPolar): `{createdCount, ids, mode, + mode-specific fields}` (mutation-class per Rule 5). Source object is preserved; `ids` enumerates new copies only (ArrayPolar empirical: `count: 6` input produced 5 new ids).

**Substrate declaration (Rule 6).** Each handler header records the substrate (`direct-sdk` / `runscript` / `managed-bridge`) with the rationale for the choice over the other two.

**Batch mode (Rule 7).** Single-object routes (all surface creators) are N/A. Array routes declare mode explicitly — all three default to `atomic` (all-or-nothing per Decision Record §4).

**Optional attribute bundle (Decision Record drift step 4).** All creators accept `{name?, layer?, color?, visible?}` at top level. Applied post-create via `ON_3dmObjectAttributes` before `pDoc->AddBrepObject`. Invalid values (e.g. malformed color) surface as `invalid_input` errors — not silently ignored (fixes `CreateHandler.cpp:107` bug as part of the rule's baseline).

### Shared patterns

**Worker-thread parse + dispatch template:**

```cpp
void HandleXxx(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Structured-error helper — Phase 1 routes never use SendError.
    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // Worker-thread JSON validation
    ParamsXxx params;
    try { params = ParseXxxParams(body); }
    catch (const std::invalid_argument& ex) {
        invalidInput(ex.what());
        return;
    }

    // Dispatch to UI thread
    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, params]() -> WriteResult { /* ... */ });

    // Join + convert to response. Top-level catch also emits structured
    // errors — it maps std::invalid_argument to "invalid_input" and
    // any other std::exception to "operation_failed".
    try {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else                CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::invalid_argument& ex) {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex) {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", ex.what()},
        };
        CRookServer::SendErrorData(res, err);
    }
}
```

Canonical reference: `src/RookNative/Handlers/SurfaceHandler.cpp` (PR-1) implements this shape end-to-end with the `invalidInput` lambda and structured-error catches. The older `OffsetBrepHandler.cpp` is the origin of the pattern but predates the Rule 1 tightening — use `SurfaceHandler.cpp` as the Phase 1 reference.

**Managed-bridge pattern (for companion-delegated routes).** Where a route's substrate is `managed-bridge`, the native handler's main-thread lambda calls through the bridge callback registered in `NativeGhBridgeRegistrar.cs`. Any new callback bumps `BridgeAbiVersion` from 12 → 13 (first Phase 1 bridge add) and subsequent bumps are linear. Append-only discipline per Decision Record §3.

**Test shape.** Each new route ships with live-Rhino characterization coverage following the PR #51 pattern (`tests/live_rhino/test_*_characterization.py`). Minimum coverage: happy path + at least one input-validation failure + **Rhino-side failure test when reachable; otherwise a permissiveness note in the handler header AND a dedicated `test_factory_permissive_smoke` case pinning one canonical sane input plus one pathological-looking input (zero-length / coincident / degenerate / disjoint) both succeeding — pinning the permissive behavior itself as a contract observation.** Scripted form spike (this plan's inputs) is not a test — it's evidence.

*(Permissiveness-smoke amendment added 2026-04-20 from Phase 2 surface/curve campaign after empirical probing found `Brep.CreateEdgeSurface` and `Curve.CreateBlendCurve` extremely permissive across 5+ and 3+ pathological inputs respectively. Applies retroactively to Phase 1 + Phase 2 campaigns; no retroactive PRs required — prior campaigns happened to ship routes that fail naturally. See `rook_docs/2026-04-20-phase2-surface-curve-plan.md` §Acceptance Gate #5 for the original trigger and the empirical record.)*

---

## Worked Example: `/surface/pipe`

The template route. Pipe was chosen because (a) it's the simplest of the three `cleanly`-running Phase 1 commands, (b) C# companion has a mature `CreatePipe` implementation already, so the work is wiring not invention, (c) `Brep.CreatePipe` is RhinoCommon-only with no native C++ SDK equivalent — exercises the managed-bridge substrate path, which is load-bearing for 4+ of the 8 Phase 1 routes.

### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Substrate** | `managed-bridge (reuse)` — native HTTP entry delegates to C# companion via the **existing** `CreateGeometry` bridge callback (`NativeGhBridgeRegistrar.cs:107`). No new callback; no ABI bump. | Rule 6; Decision Record §3 condition (a) |
| **Substrate rationale** | `Brep.CreatePipe` is a RhinoCommon-only static factory. No `RhinoPipe(...)` exists in the native Rhino C++ SDK surface. Reimplementing pipe geometry natively would duplicate mature managed code already live at `src/Rook/Handlers/CreateHandler.cs:649`, and the existing `CreateGeometry` callback already dispatches on a `type` discriminator that accepts `"PIPE"` (dead HTTP path today, reachable once a native route adapter points to it). | Rule 6; §3 condition (a) |
| **Native/managed owner** | **Native owns:** HTTP route registration, route-local JSON parse, schema validation (including XOR check on `radius` vs. `startRadius`+`endRadius`), dispatch to UI thread, response envelope serialization, error-taxonomy mapping. **Managed owns:** the existing `CreateGeometry` callback surface, factory invocation (`Brep.CreatePipe`), attribute application to `ObjectAttributes`, doc insertion, and `ObjectSnapshot` payload serialization returned through the bridge. Because this route reuses `CreateGeometry`, managed will still perform its own validation once forwarded the request; that duplicate validation is acceptable in PR-1 and can be reduced later only if a lower-level bridge seam proves worth adding. | §3 |
| **Route path** | `POST /surface/pipe` | Rule 3 (semantic route per operation; not multiplexed into `/create`) |
| **Handler / file** | Native: `src/RookNative/Handlers/SurfaceHandler.cpp :: HandlePipe` (new file; canonical home for Phase 1 surface creators). The handler builds a `CreateGeometry` request payload with `type: "PIPE"` and the Pipe params, calls the existing bridge callback adapter (pattern: `TryHandleManagedCreate` at `GrasshopperProxyHandler.cpp:849` — currently unused, revive/parameterize for `/surface/*` routes). Managed side reuses `CreateHandler.CreatePipe` verbatim; a later cleanup PR may promote surface creators into a dedicated `SurfaceHandler.cs`, but that is not gated on Phase 1. | Rule 3 |
| **MCP tool impact** | New tool `rhino_create_pipe` in `server.py`. Dead `rhino_loft` / `rhino_sweep` tools are retired in PR-0 (precursor), not bundled into this PR. No conflict — there is no existing `rhino_pipe` tool today. | Decision Record §5 naming alignment |
| **CapabilityRouter impact** | New entry `"create_pipe" → /surface/pipe` in `intent_runtime.py`. Required params: `curveId`. Optional: `radius`, `startRadius`, `endRadius`, `cap`, `tolerance`, `name`, `layer`, `color`, `visible`. | §5 |
| **Input schema** | `curveId: string (uuid) REQUIRED`; `radius: number OPTIONAL` (uniform); `startRadius: number OPTIONAL`, `endRadius: number OPTIONAL` (variable); XOR rule: either `radius` OR both `startRadius+endRadius`, not both and not partial; `cap: boolean OPTIONAL default true`; `tolerance: number OPTIONAL default doc.ModelAbsoluteTolerance`; attribute bundle `{name?, layer?, color?, visible?}` per Common Plan. | Rule 2; §4 |
| **Tolerance rule** | **Optional**, default `doc.ModelAbsoluteTolerance`. Single tolerance value used for both `absoluteTolerance` and `angleToleranceRadians` in `Brep.CreatePipe` (matches existing C# behavior and is acceptable for rail-extrude operations). If future precision complaints surface, add `angleTolerance` as a second optional param. | §4 |
| **Undo / batch mode** | Single-object route; one `UndoScope` per request. Not batch-capable (single rail → single brep). N/A for Rule 7. | Rule 4 |
| **Result cardinality policy** | **Single-result.** `Brep.CreatePipe` returns `Brep[]`; the existing managed implementation takes `breps.FirstOrDefault()` (`CreateHandler.cs:686`). Pipe inherits this behavior for Phase 1: if cardinality > 1 occurs, the first result is returned with no extra payload fields. Loft/Sweep sub-plans **must revisit this field** — they may choose `return-all` or `fail-on-multiple` rather than first-only. | Rule 5 |
| **Response shape** | Creator class → full `ObjectSnapshot` `{id, type, layer, name, visible, color, bbox}`. No additional top-level fields. If cap-state or radius-echo metadata proves valuable for agent reasoning, promote it via a Rule 5 amendment, not a Pipe-local carve-out. | Rule 5 |
| **Tests** | `tests/live_rhino/test_pipe_characterization.py`: (a) uniform radius happy path, (b) variable radius happy path, (c) capped vs uncapped, (d) missing `curveId` → `invalid_input`, (e) negative radius → `invalid_input`, (f) both `radius` and `startRadius` set → `invalid_input` (XOR violation), (g) non-curve `curveId` → `invalid_input` (not-a-curve case), (h) degenerate zero-length curve → `operation_failed`. Following PR #51 harness pattern. | — |
| **PR slice** | **PR-1: Pipe standalone.** Independently mergeable; no dependencies on other Phase 1 routes. Serves as the template other routes copy. Includes: `SurfaceHandler.cpp` scaffold + `HandlePipe` (native), native-side adapter that builds a validated `CreateGeometry` request and dispatches through the existing bridge callback, MCP tool `rhino_create_pipe`, CapabilityRouter entry, characterization tests. **No ABI bump.** Native and managed validation will overlap in this first slice because callback reuse is preferred over premature bridge growth. | — |

### Open Decision Record questions this example resolves

- **Per-operation substrate assignment for Pipe:** `managed-bridge (reuse)` — reuses the existing `CreateGeometry` callback, settled by the absence of a native `RhinoPipe` SDK function and the presence of mature managed implementation. No ABI bump.
- **Pipe tolerance required or optional:** optional with doc default (settled; matches existing C# semantics).
- **Pipe batch semantics:** N/A (single-rail-in, single-brep-out).
- **Pipe result cardinality:** single-result (first-or-default from `Brep.CreatePipe`'s array return). Loft/Sweep sub-plans must make their own call — the template exposes the field.

These four questions graduate from the Decision Record's plan-stage open list.

### Binding rule refs (summary)

| Rule | How Pipe applies it |
|---|---|
| 1 | `{success, data}` envelope via `SendSuccess` / `SendErrorData`; error `data` is `{errorCode, errorMessage}` |
| 2 | `curveId` / `radius` / XOR validated on worker thread; curve existence + curve-ness validated on UI thread |
| 3 | Dedicated route `/surface/pipe`, not `/create` multiplex |
| 4 | One UndoScope wrapping the managed-bridge call |
| 5 | Full `ObjectSnapshot` on success; single-result cardinality policy stated |
| 6 | Substrate `managed-bridge (reuse)` with RhinoCommon-only rationale in `SurfaceHandler.cpp` header. Reuses existing `CreateGeometry` callback; no new callback surface added. |
| 7 | N/A (not batch-capable) |
| §3 boundary | Condition (a): RhinoCommon-only API. **No ABI bump** — existing callback reused per Rule 6's reuse-vs-add distinction. |
| §4 tolerance | Optional with `doc.ModelAbsoluteTolerance` default |

---

## Acceptance Gate

Before templating the remaining 7 routes, the Pipe worked example must pass all three gate questions:

1. **Did the 12-row execution block expose all fields needed?** If a route sub-plan would leave a real decision ambiguous, add a field.
2. **Did any Decision Record rule prove too vague or too strong?** If so, amend the Record, not the Pipe plan.
3. **Does the Pipe substrate/contract choice fit current code patterns?** Specifically: is the managed-bridge delegation path sound given how `NativeGhBridgeRegistrar` is structured? Does the response-shape proposal match what other creator-class routes (e.g., `/create` with type=SPHERE) actually return?

Codex review is the primary gate check; user signs off after review.

---

## Phase 1 Route Sub-plans

Four managed-bridge surface creators filled below. Array family (direct-sdk substrate) stubbed; drafted in a separate pass after these pass gate review.

Shared across all four surface routes (not restated per-route):
- Route namespace: `/surface/*`
- Native handler file: `src/RookNative/Handlers/SurfaceHandler.cpp` (new; canonical home for Phase 1 surface creators)
- MCP tool namespace: `rhino_create_*`
- CapabilityRouter intent keys: `create_*`
- Substrate: `managed-bridge (reuse)` via existing `CreateGeometry` callback (`NativeGhBridgeRegistrar.cs:107`). **No ABI bump** for any of the four.
- Substrate rationale: underlying RhinoCommon factories (`Brep.CreateFromLoft`, `Brep.CreateFromSweep`, `RevSurface.Create`, `Brep.CreatePipe`) are managed-only; native re-implementation would duplicate mature managed code at `src/Rook/Handlers/CreateHandler.cs`.
- Native/managed owner: as per Pipe. Native = HTTP, parse, XOR validation, envelope. Managed = factory invocation, attributes, doc insertion, payload.
- Validation staging: worker-thread schema + XOR checks; UI-thread object-existence + type-check.
- UndoScope: one per request (Rule 4).
- Error taxonomy base: `invalid_input`, `not_found`, `operation_failed`. Route-specific codes listed per sub-plan.
- **Managed callback payload change (applies to all plural-contract routes — Loft, Sweep1, Sweep2):** the existing C# `CreateHandler.CreateLoft` / `CreateSweep1` / `CreateSweep2` all return `breps?.FirstOrDefault()`. Under the Rule 5 cardinality convention, plural-contract routes **must** return the full `Brep[]` from the factory, not first-or-default. This is a real refactor in the managed handlers, not a wiring change. Easy to miss in implementation; the PR-2 and PR-3 review should explicitly verify full-array pass-through is in place.

---

### `/surface/loft`

**Urgency:** urgent (spike: 15s timeout — multi-`_SelId` unsupported).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `curveIds: [uuid]` REQUIRED (min 2); `loftType: enum("Normal"\|"Loose"\|"Tight"\|"Straight"\|"Uniform"\|"Developable")` OPTIONAL default `"Normal"`; `closed: boolean` OPTIONAL default `false`; `startPoint: [x,y,z]` OPTIONAL (convergence point at loft start); `endPoint: [x,y,z]` OPTIONAL (convergence point at loft end); `tolerance: number` OPTIONAL default `doc.ModelAbsoluteTolerance`; attribute bundle per Common Plan. | Rule 2 |
| **Route / handler** | `POST /surface/loft` → `SurfaceHandler::HandleLoft`. Managed side reuses `CreateHandler.CreateLoft` (`CreateHandler.cs:438`); first-or-default of `Brep.CreateFromLoft` is **replaced** with full-array pass-through for plural contract. | Rule 3 |
| **Tolerance rule** | Optional, default `doc.ModelAbsoluteTolerance`. Passed as fit tolerance to `Brep.CreateFromLoft`. | §4 |
| **Undo / batch mode** | Single-request; one UndoScope. Not batch-capable. N/A Rule 7. | Rule 4 |
| **Result cardinality** | **Plural contract.** `Brep.CreateFromLoft` returns `Brep[]`; all Breps surface in the response. Empty result → `operation_failed` error (not an empty `{objects: []}` success). | Rule 5 cardinality convention |
| **Response shape** | `{objects: [ObjectSnapshot, ...]}` unconditionally, even when N = 1. Each snapshot is the full creator shape. | Rule 5 |
| **Route-specific error codes** | `invalid_loft_type` (enum mismatch), `insufficient_curves` (< 2), `convergence_point_conflict` (startPoint set + closed=true — closed loft with convergence points is semantically ambiguous; reject rather than silently drop). | Rule 1 |
| **Tests** | `tests/live_rhino/test_loft_characterization.py`: (a) 3 circles, Normal type, open → 1 brep; (b) 2 curves, each loftType value; (c) closed=true → closed brep; (d) startPoint set → converges at start; (e) 1 curve → `insufficient_curves`; (f) invalid loftType string → `invalid_loft_type`; (g) malformed curveId → `not_found`; (h) point-input (non-curve object) → `invalid_input`; (i) incompatible geometry that returns `Brep[]` of length 0 → `operation_failed`; (j) input that produces > 1 disjoint Breps → plural response verified. | — |
| **PR slice** | **PR-2:** Loft standalone. Merges after Pipe (PR-1) as first plural-contract validation. | — |

#### Phase 1 explicit rejections (prevent command-UI sprawl)

Rejected from this scope, deferred to future passes or user request:

- Rebuild / refit controls (`rebuildCount`, fit method beyond Normal semantics)
- Cross-section curve reversal hints (`Flip` option)
- Seam alignment picker for closed lofts (managed code uses automatic seam matching; Phase 1 does not expose it)

**Note:** all six `loftType` enum values (including `Developable`) are accepted by the schema and surface to the underlying `Brep.CreateFromLoft` call. Phase 1 characterization coverage targets the most common values (Normal, Loose, Tight); `Uniform` / `Straight` / `Developable` are best-effort and explicit additional characterization can follow when workflows exercise them.

#### Resolved Decision Record questions

- Loft substrate: `managed-bridge (reuse)`, no ABI bump.
- Loft cardinality contract: plural.
- Loft tolerance: optional with doc default.

---

### `/surface/sweep1`

**Urgency:** urgent (spike: HTTP 400 — multi-step `_SelId _Enter _SelId _Enter` rejected).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `railId: uuid` REQUIRED (single rail); `profileIds: [uuid]` REQUIRED (min 1, shape curves along the rail); `closed: boolean` OPTIONAL default `false`; `style: enum("Freeform"\|"Roadlike"\|"AlignWithSurface")` OPTIONAL default `"Freeform"`; `roadlikeFrame: {origin:[x,y,z], normal:[x,y,z]}` OPTIONAL (required iff `style == "Roadlike"`); `tolerance: number` OPTIONAL default `doc.ModelAbsoluteTolerance`; attribute bundle per Common Plan. | Rule 2 |
| **Route / handler** | `POST /surface/sweep1` → `SurfaceHandler::HandleSweep1`. Managed side reuses `CreateHandler.CreateSweep1` (`CreateHandler.cs:458`), modified for plural contract. | Rule 3 |
| **Tolerance rule** | Optional, default `doc.ModelAbsoluteTolerance`. Passed to `Brep.CreateFromSweep` 1-rail overload. | §4 |
| **Undo / batch mode** | Single-request; one UndoScope. N/A Rule 7. | Rule 4 |
| **Result cardinality** | **Plural contract.** `Brep.CreateFromSweep` returns `Brep[]`. | Rule 5 |
| **Response shape** | `{objects: [ObjectSnapshot, ...]}`. | Rule 5 |
| **Route-specific error codes** | `invalid_style` (enum mismatch); `missing_roadlike_frame` (style=Roadlike without frame); `frame_without_roadlike` (frame provided but style≠Roadlike — reject rather than silently ignore, per Decision Record attribute-bundle silent-ignore lesson); `no_profiles` (empty `profileIds`). | Rule 1 |
| **Tests** | `tests/live_rhino/test_sweep1_characterization.py`: (a) line rail + circle profile → tube; (b) curved rail + polyline profile; (c) closed=true on closed rail; (d) each style value; (e) Roadlike without frame → `missing_roadlike_frame`; (f) frame without Roadlike → `frame_without_roadlike`; (g) non-curve railId → `invalid_input`; (h) empty profileIds → `no_profiles`; (i) rail+profile incompatible (profile not touching rail) → `operation_failed`; (j) input that produces > 1 disjoint Breps → plural response verified. | — |
| **PR slice** | **PR-3** (with Sweep2): shared bridge plumbing and managed reuse pattern merge together. | — |

#### Phase 1 explicit rejections

- Rebuild / refit (`Rebuild`, `Refit`, `UntrimmedMiters` command-UI flags)
- Simple-sweep / miter-type controls (`Miter=Automatic/Coplanar/Full`)
- Closed-sweep cap style (implicit: closed=true → automatic end-caps via RhinoCommon default)
- Advanced shape-blending controls across multi-profile sweeps — multi-profile input is accepted per schema, but Phase 1 uses managed default blending only; no exposed blend-curve or blend-factor parameters
- Interactive seam picker for closed rails (managed handles automatically)

#### Resolved Decision Record questions

- Sweep1 substrate: `managed-bridge (reuse)`, no ABI bump.
- Sweep1 cardinality contract: plural.
- Sweep1 tolerance: optional with doc default.

---

### `/surface/sweep2`

**Urgency:** urgent (spike: silent no-op, `executed=true` with 0 objects — the substrate-gold failure mode that Rule 2's UI-thread validation specifically addresses).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `rail1Id: uuid` REQUIRED; `rail2Id: uuid` REQUIRED; `profileIds: [uuid]` REQUIRED (min 1, cross-section curves); `closed: boolean` OPTIONAL default `false`; `maintainHeight: boolean` OPTIONAL default `false` (2-rail-specific option; preserves cross-section height when rails diverge); `tolerance: number` OPTIONAL default `doc.ModelAbsoluteTolerance`; attribute bundle per Common Plan. | Rule 2 |
| **Route / handler** | `POST /surface/sweep2` → `SurfaceHandler::HandleSweep2`. Managed side reuses `CreateHandler.CreateSweep2` (`CreateHandler.cs:502`), modified for plural contract. Separate from Sweep1 per user adjudication (two-handler default). | Rule 3 |
| **Tolerance rule** | Optional, default `doc.ModelAbsoluteTolerance`. Passed to `Brep.CreateFromSweep` 2-rail overload. | §4 |
| **Undo / batch mode** | Single-request; one UndoScope. N/A Rule 7. | Rule 4 |
| **Result cardinality** | **Plural contract.** `Brep.CreateFromSweep` returns `Brep[]`. | Rule 5 |
| **Response shape** | `{objects: [ObjectSnapshot, ...]}`. | Rule 5 |
| **Route-specific error codes** | `rails_disconnected` (UI-thread validation: profile endpoints do not touch both rails — addresses the silent no-op spike finding); `no_profiles`; `rails_coincident` (rail1 and rail2 are the same curve or geometrically identical — use Sweep1 instead). | Rule 1, Rule 2 |
| **Tests** | `tests/live_rhino/test_sweep2_characterization.py`: (a) two parallel line rails + cross-section line → ribbon surface; (b) diverging rails + maintainHeight=true vs false; (c) closed=true on closed rails; (d) profile not touching rail1 → `rails_disconnected` (explicitly addresses the silent-no-op failure mode from the spike); (e) profile not touching rail2 → `rails_disconnected`; (f) rail1 == rail2 → `rails_coincident`; (g) empty profileIds → `no_profiles`; (h) incompatible geometry → `operation_failed`; (i) multi-disjoint-result case → plural response verified. | — |
| **PR slice** | **PR-3** (with Sweep1). Shared bridge plumbing; separate handlers per Rule 3. | — |

#### Phase 1 explicit rejections (Codex-flagged sprawl risk)

Sweep2's command UI has the widest option surface of Phase 1. Phase 1 accepts none of the following — escalation path is explicit user request, not accretion:

- Rail curvature matching modes (`SimpleSweep` vs `FullSweep` vs `Style=RoadlikeTop/Bottom`)
- Cross-section placement choice (`Position=AtRail1/AtRail2/Between`)
- Manual seam pickers for closed sweeps (managed auto-matches)
- Rail correspondence adjustment (profile-to-rail matching uses managed automatic mode; no manual reversal flag)
- Rebuild / refit modes
- Shape blending between sections (managed default; no exposed blend curve controls)

This scope limit is explicit so implementers see a closed set and don't try to mirror the interactive command's full surface.

#### Resolved Decision Record questions

- Sweep2 substrate: `managed-bridge (reuse)`, no ABI bump.
- Sweep2 cardinality contract: plural.
- Sweep2 tolerance: optional with doc default.
- Sweep1 + Sweep2 handler merge: **two separate handlers** (user adjudication 2026-04-17). Shared managed logic factored out at C# level; route-level stays distinct per Rule 3.

---

### `/surface/revolve`

**Urgency:** useful (spike: 1 object created cleanly).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `curveId: uuid` REQUIRED (profile curve); `axisStart: [x,y,z]` REQUIRED; `axisEnd: [x,y,z]` REQUIRED; `startAngle: number (degrees)` OPTIONAL default `0`; `endAngle: number (degrees)` OPTIONAL default `360`; `tolerance: number` OPTIONAL default `doc.ModelAbsoluteTolerance`; attribute bundle per Common Plan. | Rule 2 |
| **Route / handler** | `POST /surface/revolve` → `SurfaceHandler::HandleRevolve`. Managed side reuses `CreateHandler.CreateRevolve`. Axis-by-values (`axisStart`+`axisEnd`) is the canonical form — **no first-class `axisLineId`** (user adjudication 2026-04-17; agents compose from line endpoints via query if needed). | Rule 3 |
| **Tolerance rule** | Optional, default `doc.ModelAbsoluteTolerance`. Used for `RevSurface.ToBrep()` conversion tolerance where applicable. | §4 |
| **Undo / batch mode** | Single-request; one UndoScope. N/A Rule 7. | Rule 4 |
| **Result cardinality** | **Singular contract.** `RevSurface.Create` produces one surface → one Brep. | Rule 5 cardinality convention |
| **Response shape** | Bare `ObjectSnapshot`. | Rule 5 |
| **Route-specific error codes** | `axis_degenerate` (axisStart == axisEnd, length-zero axis); `angle_invalid` (startAngle == endAngle, empty sweep); `curve_intersects_axis` (profile crosses the axis line — likely produces invalid or self-intersecting output; reject upfront per Rule 2 UI-thread validation. Exact failure-mode characterization deferred to test coverage). | Rule 1, Rule 2 |
| **Tests** | `tests/live_rhino/test_revolve_characterization.py`: (a) line profile + full circle → cylinder-like Brep; (b) arc profile + full circle → sphere-like surface; (c) startAngle=90, endAngle=270 → half revolve; (d) axisStart == axisEnd → `axis_degenerate`; (e) startAngle == endAngle → `angle_invalid`; (f) profile crosses axis → `curve_intersects_axis`; (g) non-curve curveId → `invalid_input`; (h) missing axisStart → `invalid_input`. | — |
| **PR slice** | **PR-4:** Revolve standalone. Independent of Loft/Sweep; serves as second singular-cardinality validation after Pipe. | — |

#### Phase 1 explicit rejections

- Angle input in radians (canonical: degrees, aligning with knowledge-store convention for user-facing angles)
- Axis-by-line-reference (`axisLineId`) — rejected per user adjudication; composition from line endpoints is the workaround
- `DeleteInput` command-UI flag (typed routes never consume the input object)
- Auto-cap flags (Revolve's output is a RevSurface→Brep; cap semantics are intrinsic to the angle span, not a user option in Phase 1)

#### Resolved Decision Record questions

- Revolve substrate: `managed-bridge (reuse)`, no ABI bump.
- Revolve cardinality contract: singular.
- Revolve tolerance: optional with doc default.
- Revolve axis shape: **axis-by-values** (`axisStart`+`axisEnd`). No first-class geometry reference.

---

## Array Family Sub-plans

Three array routes filled below. Different substrate, different response class, drafted after the four surface routes passed review.

Shared across all three array routes (not restated per-route):
- Route namespace: `/array/*`
- Native handler file: `src/RookNative/Handlers/ArrayHandler.cpp` (new; canonical home for Phase 1 array operations)
- MCP tool namespace: `rhino_array_*`
- CapabilityRouter intent keys: `array_*`
- Substrate: `direct-sdk` (native C++). Transform loops using `ON_Xform::Translation` and `ON_Xform::Rotation`, applied via `CRhinoDoc::TransformObject` on duplicated objects.
- Substrate rationale: array operations are composable from elementary transforms. No RhinoCommon-only capability required; the native C++ SDK covers the full surface. Managed delegation would be pure reinvention.
- Native/managed owner: **native owns the full implementation.** No bridge crossing. No ABI impact.
- **Count semantics:** `total-including-source` (user lock 2026-04-17; aligns with Rhino convention). `count: 6` produces 5 new copies; response `ids` enumerates the 5 new copies only. Source objects are preserved in place.
- Response class: **mutation** (per Rule 5). Shape is `{createdCount, sourceIds, ids, mode, + mode-specific fields}`. **Not** `ObjectSnapshot` or `{objects: [...]}` — array outputs are homogeneous transforms of known sources; full per-instance snapshots would be wasteful at moderate-to-large N and rarely useful to the agent (which reasons about the collection, not each copy).
- Undo / batch mode (Rules 4, 7): **atomic**. One `UndoScope` wraps the entire array loop, AND the handler explicitly rolls back any created copies on mid-loop failure before returning `operation_failed`. `UndoScope` alone only groups operations into one undo record for user-facing Ctrl+Z; it is not a transactional rollback mechanism. Server-side atomicity requires the handler to track created uuids and call `pDoc->DeleteObject` on each before throwing. Partial-success is explicitly drift — (k−1) successful copies + 1 failure + N−k untouched is a failure mode the user/agent should never have to reason about.
- Validation staging: worker-thread parses shape + count + spacing sanity (structured `invalid_input` errors via `SendErrorData`, same pattern as PR-1); UI-thread pre-flights source object existence (bails with `not_found` before entering the loop) and captures source attributes before the loop begins.
- Error taxonomy base: `invalid_input`, `not_found`, `operation_failed`. Worker-thread shape/schema errors (malformed uuid string, wrong vector shape, wrong JSON type on a required field) surface as `invalid_input`. Semantic errors on counts/spacings use the route-specific codes below. Non-integer counts always map to `invalid_count` (per the sub-plans), not `invalid_input`.
- **Test fault-injection seam (for mid-loop-failure coverage).** Array handlers consult a process-local one-shot counter that is armed via an internal debug route `POST /array/_debug/fail-next-copy` (body: `{"index": <int>}`, 1-indexed copy attempt that should return null synthetically). The debug route is gated on `ROOK_ENABLE_DEBUG_ROUTES=1` using the same `DebugRoutesEnabledOrRefuse` precedent as `/block/_debug/*` (see `BlocksHandler.cpp:5562`). The counter auto-clears after tripping. This is **not** part of the public `/array/*` schema — no `_testFailAtCopy` field on the real routes; agents never see it. Product code MUST NOT call the debug route.

---

### `/array/linear`

**Urgency:** urgent (spike: HTTP 400 — `_-ArrayLinear` scripted form rejected in Rhino 8).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `ids: [uuid]` REQUIRED (min 1, objects to array); `direction: [x,y,z]` REQUIRED (direction vector, non-zero, normalized internally); `spacing: number` REQUIRED (distance between consecutive copies along `direction`, must be > 0); `count: int` REQUIRED (≥ 1, total including source). | Rule 2 |
| **Route / handler** | `POST /array/linear` → `ArrayHandler::HandleLinear`. Native transform loop: for k in [1, count): `T_k = ON_Xform::Translation(normalize(direction) * spacing * k)`; duplicate source(s); apply `T_k`; add to doc. Reverses direction via negative `direction` components, not via negative `spacing`. | Rule 3 |
| **Tolerance rule** | N/A — transforms are exact; no geometric tolerance involved. | §4 |
| **Undo / batch mode** | Single UndoScope around the per-copy loop; atomic mode declared (Rule 7). | Rule 4, Rule 7 |
| **Result cardinality** | Mutation-class. `createdCount = len(sourceIds) * (count - 1)` — total number of new objects across all sources, always equal to `len(ids)` in the response. | Rule 5 |
| **Response shape** | `{createdCount: int, sourceIds: [uuid], ids: [uuid], mode: "linear", direction: [x,y,z], spacing: number, count: int}`. `ids` ordered **source-major, k-minor**: all `count-1` copies of source 0 in k-order (k=1 first), then all copies of source 1, etc. For sources `[A,B]` with `count=3`: `[A_k1, A_k2, B_k1, B_k2]`. Rationale: agents typically reason about "this source's copies" more than "this step's copies" — source-major slicing gives a clean `ids[i*(count-1):(i+1)*(count-1)]` per source. | Rule 5 |
| **Route-specific error codes** | `invalid_count` (count < 1 OR non-integer — worker thread enforces `is_number_integer()`, so a JSON float like `3.5` surfaces as `invalid_count`, not `invalid_input`); `degenerate_direction` (zero-length direction vector); `invalid_spacing` (spacing ≤ 0). | Rule 1 |
| **Tests** | `mcp_server/tests/test_array_linear_live.py`: (a) single box + direction `[1,0,0]` + spacing 10 + count 5 → 4 new boxes at x=10,20,30,40; (b) multi-source (2 boxes) + count 5 → 8 new copies total, ordered source-major (first 4 ids = source 0's copies in k-order, next 4 = source 1's); (c) count=1 → no new copies, `createdCount: 0`, `ids: []`, success=true; (d) count=0 → `invalid_count`; (e) non-integer count (e.g. `3.5`) → `invalid_count`; (f) direction=`[0,0,0]` → `degenerate_direction`; (g) spacing=0 → `invalid_spacing`; (h) negative spacing → `invalid_spacing`; (i) negative direction + positive spacing → reverse-direction array (correct behavior, no error); (j) missing source id → `not_found` before the loop opens (no copies created, verify zero new objects in doc); (k) atomicity: arm `/array/_debug/fail-next-copy` with `{"index": 3}`, run a `count=5` request → handler creates 2 copies, then synthetic null on the 3rd attempt triggers cleanup → assert response is `operation_failed`, response `ids` is empty, and a follow-up `rhino_objects` count delta is zero (full rollback). Requires `ROOK_ENABLE_DEBUG_ROUTES=1` in the Rhino process environment; test skips with a clear message if the env var is missing; (l) attribute preservation: source on layer "Foo" → copies on layer "Foo". | — |
| **PR slice** | **PR-5** (with `/array/rectangular`): shared `ArrayHandler.cpp` scaffolding; both native-only; ship together. | — |

#### Phase 1 explicit rejections

- Along-curve distribution (separate operation; compose via `DivideCurve` + `transform`)
- Negative count as reverse-direction shortcut (use negative `direction` components)
- Basepoint / source-position picker (source's current position is the anchor; pre-transform if repositioning needed)
- Multi-axis linear (that's rectangular; use `/array/rectangular`)

#### Resolved Decision Record questions

- ArrayLinear substrate: `direct-sdk`, no bridge, no ABI bump.
- ArrayLinear response class: mutation.
- ArrayLinear count semantics: total-including-source.
- ArrayLinear undo / batch mode: atomic.

---

### `/array/rectangular`

**Urgency:** urgent (spike: 15s timeout — `_-Array _Rectangular` scripted form stalled).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `ids: [uuid]` REQUIRED (min 1); `xCount: int` REQUIRED (≥ 1); `yCount: int` REQUIRED (≥ 1); `zCount: int` OPTIONAL default `1`; `xSpacing: number` REQUIRED (> 0 when `xCount > 1`, else ignored); `ySpacing: number` REQUIRED (> 0 when `yCount > 1`, else ignored); `zSpacing: number` OPTIONAL (required > 0 when `zCount > 1`, else ignored/defaults 0). **Grid basis:** the active viewport's construction plane (CPlane) **at the time the request is dispatched on the UI thread** — this is the explicit source of basis state. The response echoes the exact basis used (see Response shape) so the agent can verify what orientation was applied. Phase 2 may add an optional `plane` input to make the basis fully explicit in the request; for Phase 1, active-CPlane-at-dispatch is the canonical source and it is reported back in the response. | Rule 2 |
| **Route / handler** | `POST /array/rectangular` → `ArrayHandler::HandleRectangular`. Triple-nested loop over (i, j, k) in [0, xCount) × [0, yCount) × [0, zCount); skip (0,0,0) which is the source position; compute `T = ON_Xform::Translation(i·xSpacing·cplaneX + j·ySpacing·cplaneY + k·zSpacing·cplaneZ)`; duplicate + apply + add. | Rule 3 |
| **Tolerance rule** | N/A. | §4 |
| **Undo / batch mode** | Single UndoScope; atomic mode. | Rule 4, Rule 7 |
| **Result cardinality** | Mutation-class. `createdCount = len(sourceIds) * (xCount * yCount * zCount - 1)` — total new objects across all sources, always equal to `len(ids)` in the response. | Rule 5 |
| **Response shape** | `{createdCount: int, sourceIds: [uuid], ids: [uuid], mode: "rectangular", xCount, yCount, zCount, xSpacing, ySpacing, zSpacing, planeUsed: {origin: [x,y,z], xAxis: [x,y,z], yAxis: [x,y,z], zAxis: [x,y,z]}}`. `ids` ordered **source-major, then inner X / Y / Z within each source's sub-grid**: for each source in source-order, iterate `(i, j, k)` with `i` innermost and `k` outermost (the source cell `(0,0,0)` is skipped). `planeUsed` echoes the active CPlane captured at dispatch — makes the otherwise-ambient basis state deterministic to the caller. | Rule 5 |
| **Route-specific error codes** | `invalid_count` (any count < 1 OR non-integer — worker thread enforces `is_number_integer()` on each of `xCount`/`yCount`/`zCount`); `invalid_spacing` (required spacing ≤ 0); `zspacing_required` (zCount > 1 but zSpacing missing or ≤ 0); `no_active_view` (CPlane cannot be captured because `RhinoApp().ActiveView()` is null — loud failure per the "explicit source of basis state" contract; silent fallback to world XY is explicitly rejected). | Rule 1 |
| **Tests** | `mcp_server/tests/test_array_rectangular_live.py`: (a) 2D grid 3×2×1 spacing 10×5 → 5 new copies at deterministic CPlane positions; (b) 3D grid 2×2×2 spacing 10×10×10 → 7 new copies; (c) xCount=yCount=zCount=1 → `createdCount: 0`, success=true; (d) zCount omitted (defaults 1) on a 2D grid → still succeeds; (e) xCount=0 → `invalid_count`; (f) non-integer xCount (e.g. `2.5`) → `invalid_count`; (g) xCount=3 with xSpacing=0 → `invalid_spacing`; (h) zCount=2 with zSpacing omitted → `zspacing_required`; (i) zCount=2 with zSpacing=0 → `zspacing_required`; (j) multi-source (2-object source list) with 3×2 grid → 10 new copies, ordered source-major (first 5 ids = source 0's copies inner-X/Y, then source 1's); (k) `planeUsed` round-trip: set CPlane via viewport API → dispatch → assert `planeUsed` matches; (l) atomicity: arm `/array/_debug/fail-next-copy` at a mid-grid index → assert cleanup runs, response is `operation_failed`, `ids` empty, zero net new objects in doc. Requires `ROOK_ENABLE_DEBUG_ROUTES=1`. | — |
| **PR slice** | **PR-5** (with `/array/linear`). | — |

#### Phase 1 explicit rejections

- Non-CPlane-aligned grids (use `transform` first to rotate the source or the CPlane)
- Non-uniform per-axis spacing (use repeated `/array/linear` or `DivideCurve` composition)
- Negative counts (invert direction by rotating the CPlane or pre-transforming the source)
- Basepoint / grid-origin picker (source position is the grid origin by convention)

#### Resolved Decision Record questions

- ArrayRectangular substrate: `direct-sdk`.
- ArrayRectangular response class: mutation.
- ArrayRectangular 2D-vs-3D: `zCount` optional (default 1), `zSpacing` required when `zCount > 1`.
- ArrayRectangular count semantics: total-including-source per-axis.
- ArrayRectangular undo / batch mode: atomic.

---

### `/array/polar`

**Urgency:** useful (spike: cleanly, 5 new objects from `count=6, angle=360` — validates count semantics empirically at the Rhino convention).

#### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Input schema** | `ids: [uuid]` REQUIRED (min 1); `center: [x,y,z]` REQUIRED (rotation center); `axis: [x,y,z]` OPTIONAL default `[0,0,1]` (literal world Z — **not** active CPlane Z; the literal default avoids any ambient-viewport dependency and the `no_active_view` failure mode that rectangular needs); `count: int` REQUIRED (≥ 1, total including source); `angle: number (degrees)` OPTIONAL default `360` (total sweep per user lock 2026-04-17, **not** per-step). **Negative angles are accepted as reverse-direction sweep** (parallel to linear's negative-direction acceptance). `-360` is treated as a reverse full circle, not a partial sweep — see Route/handler step formula below; `rotate: boolean` OPTIONAL default `true` (rotate each copy to align with its angular position vs. keep source orientation fixed). | Rule 2 |
| **Route / handler** | `POST /array/polar` → `ArrayHandler::HandlePolar`. **When `count == 1`, the handler still runs schema validation and source pre-flight (`ResolveSourcesOrThrow`) — only step computation and the copy loop are skipped.** Bogus uuids must surface as `not_found` even at `count=1`; the empty-success path returns `createdCount: 0, ids: []` only after sources resolve. Otherwise, step computed per signed-full-circle-aware Rhino convention: `isFullCircle = abs(abs(angle) - 360.0) < 1e-9`; `step = isFullCircle ? (angle / count) : (angle / (count - 1))`. The signed `angle` flows through both branches so `+360` produces `+360/count` and `-360` produces `-360/count` — full-circle behavior is preserved on the negative side. For partial sweeps the last copy lands at the `angle` position with sign preserved. For k in [1, count): `θ_k = step * k`; compose `T_k` from `ON_Xform::Rotation(θ_k, normalize(axis), center)` plus (when `rotate=false`) an attitude-preservation transform; duplicate + apply + add. | Rule 3 |
| **Tolerance rule** | N/A. | §4 |
| **Undo / batch mode** | Single UndoScope; atomic mode. | Rule 4, Rule 7 |
| **Result cardinality** | Mutation-class. `createdCount = len(sourceIds) * (count - 1)` — total new objects across all sources, always equal to `len(ids)` in the response. | Rule 5 |
| **Response shape** | `{createdCount: int, sourceIds: [uuid], ids: [uuid], mode: "polar", center, axis, count, angle, rotate}`. `ids` ordered **source-major, θ-minor**: for each source in source-order, iterate copies in θ-order (k=1 first, k=count−1 last). For sources `[A, B]` with `count=4`: `[A_θ1, A_θ2, A_θ3, B_θ1, B_θ2, B_θ3]`. Echoed `axis` and `angle` are the resolved values (after defaults), not the raw input. | Rule 5 |
| **Route-specific error codes** | `invalid_count` (count < 1 OR non-integer — worker thread enforces `is_number_integer()`); `degenerate_axis` (zero-length axis vector, `Length() < ON_ZERO_TOLERANCE` — same threshold as linear's `degenerate_direction`); `angle_zero_with_count` (count > 1 and `abs(angle) < 1e-9` — copies would stack on source, semantically degenerate; reject rather than silently produce N overlapping duplicates). | Rule 1 |
| **`rotate=false` reference point** | Object bounding-box center, computed via `obj->GetTightBoundingBox()` first (representation-independent — see `BlocksHandler.cpp:837` for the canonical idiom and rationale). Falls back to `obj->BoundingBox().Center()` only if `GetTightBoundingBox` returns invalid. Captured per source pre-loop. Mathematically: `T_k = Rot(-θ_k, axis, P_k) * Rot(θ_k, axis, center)` where `P_k = Rot(θ_k, axis, center) * P_S` — the net effect is a translation `(P_k - P_S)` with no orientation change. | Rule 5 reference |
| **Tests** | `mcp_server/tests/test_array_polar_live.py`: (a) **spike replication (setup geometry matters for this test):** box created at corner `[220,0,0]` with dimensions 2×2×2 (box centroid therefore at `[221,1,1]`); polar array center `[220,0,0]`, axis default `[0,0,1]`, count=6, angle=360 → 5 new copies forming an evenly-spaced ring around `[220,0,0]` at 60° intervals; baseline must match the 2026-04-17 spike result exactly. Source offset from rotation center is what produces the ring (rotating the box around its own centroid would stack copies in place). (b) partial sweep: count=4, angle=180 → 3 new copies at 60°, 120°, 180° (step = 180 / 3); (c) count=2, angle=90 → 1 new copy at 90°; (d) **`rotate=false` (fixture must defeat rotational symmetry):** source box `[10,0,0]` to `[16,1,0.5]` — asymmetric in all three dims; center `[0,0,0]`, axis `[0,0,1]`, count=5, angle=360 → step=72° (non-right-angle, non-90° to avoid bbox-symmetry false-positives). Assert: every `rotate=false` copy's tight bounding-box is dimensionally identical to the source (6×1×0.5, within ON_ZERO_TOLERANCE). Baseline `rotate=true` run with the same fixture must produce at least one copy whose bounding-box differs from 6×1×0.5 by > 1.0 unit in some axis (proves the test would catch a `rotate=false` regression that secretly rotated). A cube fixture or a 90°-aligned step would mask the bug — both explicitly avoided. (e) **count=1 with valid source** → no new copies, `createdCount: 0`, `ids: []`, success=true (verifies the count==1 guard against divide-by-zero); (f) **count=1 with bogus source uuid** → `not_found` (verifies pre-flight runs even at count=1); (g) **count=1 with valid source AND degenerate axis `[0,0,0]`** → success=true, `createdCount: 0` (pins the contract that count=1 short-circuits axis validation too — defensible because no rotation is performed); (h) count=0 → `invalid_count`; (i) non-integer count → `invalid_count`; (j) count=3, angle=0 → `angle_zero_with_count`; (k) count > 1 with axis=`[0,0,0]` → `degenerate_axis`; (l) **negative full circle:** count=4, angle=-360 → 3 new copies at -90°, -180°, -270° (step = -90°), confirming reverse full-circle behavior matches positive full-circle (no copy lands on source); (m) negative partial: count=4, angle=-180 → 3 new copies at -60°, -120°, -180°; (n) custom axis: `axis=[1,0,0]`, count=4, angle=360 → ring around X-axis (verify bbox positions); (o) **multi-source source-major ordering:** 2 boxes + count=3, angle=360 → 4 new copies, `ids[0:2]` are source 0's copies in θ-order, `ids[2:4]` are source 1's; (p) atomicity: arm `/array/_debug/fail-next-copy` mid-loop, run count=5 polar → `operation_failed`, `ids` empty, zero net new objects (requires `ROOK_ENABLE_DEBUG_ROUTES=1`; skip cleanly otherwise). | — |
| **PR slice** | **PR-6:** `/array/polar` standalone. Independent; useful-tier. | — |

#### Phase 1 explicit rejections

- Per-step angle as an input alternative (locked as total-sweep per user adjudication; if per-step is ever requested, add `stepAngle` as an alternative-XOR-with-`angle`, not in Phase 1)
- Elliptical polar array (not a standard Rhino operation; out of scope)
- Non-uniform angular distribution (Phase 1 assumes uniform step; variable angular spacing would be a separate API if ever needed)
- Basepoint other than source-to-center (agents can pre-transform if a different pivot is needed)

#### Resolved Decision Record questions

- ArrayPolar substrate: `direct-sdk`.
- ArrayPolar response class: mutation.
- ArrayPolar angle semantics: `total sweep` (not per-step). Negative angles accepted as reverse-direction sweep; `±360` both treated as full circle via `abs(abs(angle) - 360.0) < 1e-9` predicate, with sign preserved in step (`angle / count`).
- ArrayPolar count semantics: total-including-source. `count == 1` short-circuits step computation and the copy loop **after** schema validation and source pre-flight — bogus uuids surface as `not_found` even at `count=1`. The short-circuit also bypasses `degenerate_axis` validation: a `count=1, axis=[0,0,0], <valid source>` request succeeds with `createdCount: 0` because no rotation is performed and the axis value is never consumed. Defensible because the malformed input has no operational effect; pinned in test (g) so future authors don't accidentally tighten it without the discussion.
- ArrayPolar undo / batch mode: atomic.
- ArrayPolar `rotate=false` reference point: object tight bounding-box center via `GetTightBoundingBox` (preferred for representation-independence per `BlocksHandler.cpp:837`), with `BoundingBox().Center()` fallback when the tight variant returns invalid. Matches Rhino interactive Array Polar with Rotate=No.
- ArrayPolar `axis` default: literal world `[0,0,1]`, not active CPlane Z. Avoids the `no_active_view` failure mode rectangular needs; agents pass an explicit `axis` when a different orientation is needed.

---

## PR slicing

Order reflects urgency × template-proving value × independence. Phase 1 opens with a precursor cleanup; main implementation follows in sequence.

0. **PR-0 (precursor): retire dead `rhino_loft` / `rhino_sweep` MCP tools.** Dedicated cleanup PR. Removes the two stale tool registrations in `server.py` and the corresponding dead `/create` type dispatches. Must land before PR-1 so agents don't pick dead tools over typed alternatives during the Phase 1 implementation window.
1. **PR-1: `/surface/pipe`** — worked example, template for others. Creates `SurfaceHandler.cpp`; establishes the `managed-bridge (reuse)` pattern on the existing `CreateGeometry` callback. Dependency root for PR-2/3/4.
2. **PR-2: `/surface/loft`** — highest urgency; first plural-contract route; validates the managed payload refactor (FirstOrDefault → full-array pass-through).
3. **PR-3: `/surface/sweep1` + `/surface/sweep2`** — shared managed-bridge plumbing; two separate handlers per Rule 3 (user adjudication 2026-04-17).
4. **PR-4: `/surface/revolve`** — independent; useful-tier; second singular-cardinality route.
5. **PR-5: `/array/linear` + `/array/rectangular`** — creates `ArrayHandler.cpp`; shared `direct-sdk` transform-loop scaffolding; native handler family. Dependency root for PR-6.
6. **PR-6: `/array/polar`** — extends `ArrayHandler.cpp` with rotation-loop variant; independent; useful-tier.

**Dependency discipline.** Within the Surface family (PR-1→PR-2→PR-3→PR-4), each PR adds functions to `SurfaceHandler.cpp` and entries to `RookServer.cpp` / `server.py` / `intent_runtime.py`. Sequential merging avoids conflicts; parallel work on separate branches is fine but land in order. Same rule within the Array family (PR-5→PR-6). Surface and Array families are independent and can parallelize across the two threads.

**Rollback posture.** Each PR independently revertible. CapabilityRouter entries wired last in each PR (after the route is proven end-to-end), per Decision Record drift cleanup discipline.

---

## Exit criteria

Phase 1 is complete when all of the following hold:

1. All 8 typed routes merged and live in `RookServer.cpp`
2. MCP tools registered in `server.py` with canonical names (`rhino_create_*`, `rhino_array_*`)
3. CapabilityRouter entries live in `intent_runtime.py`; no Phase 1 intent falls through to command-string fallback
4. Live-Rhino characterization coverage per route
5. Dead `rhino_loft` / `rhino_sweep` tools retired
6. Bridge `BridgeAbiVersion` incremented only for routes that *add* a new callback surface, not for routes that reuse existing callbacks (per Rule 6 reuse-vs-add distinction). All four Phase 1 surface creators reuse `CreateGeometry`; no ABI bump expected from Phase 1
7. CapabilityRouter coverage test confirms all 8 Phase 1 intents (`create_pipe`, `create_loft`, `create_sweep1`, `create_sweep2`, `create_revolve`, `array_linear`, `array_rectangular`, `array_polar`) route to typed endpoints. No intent in this set falls through to command-string fallback under any invocation. Measured by unit test on `intent_runtime.py`.

---

## Git workflow (per project convention)

Phase 1 PRs follow the established `bringfire/Rook` workflow:

- **Branch naming:** `fix/` for defect fixes (e.g., PR-0 legacy-tool cleanup qualifies), `feat/` for new typed routes (PR-1 through PR-6). Branches scoped to a single PR.
- **Pre-PR verification:** build + live-Rhino characterization tests green locally before opening the PR. Each route ships with its test file per sub-plan.
- **Merge mode:** squash merge. One PR = one commit on `main`.
- **Finish sequence:** `gh pr merge --squash --delete-branch` as a single command after approval. Do not push to `main` directly.
- **Revert path:** each PR's squashed commit is independently revertible via `git revert <sha>` on a `fix/` branch followed by the same merge sequence.

---

## Open Questions

All plan-stage questions from the Decision Record are resolved. The legacy `rhino_loft` / `rhino_sweep` handling decision (precursor-remove as **PR-0**) was settled 2026-04-17 and is captured in the PR slicing above. No live architectural or operational questions remain for Phase 1.
