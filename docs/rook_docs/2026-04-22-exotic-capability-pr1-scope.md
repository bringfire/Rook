# PR1 Scope: `POST /block/distribute-along-curve`

**Date:** 2026-04-22
**Author:** bringfire + Claude (reviewed by Codex, three rounds)
**Status:** Implementation-ready. No further design review expected unless scope materially changes.
**Related:**
- `2026-04-22-exotic-capability-promotion-plan.md` — doctrine and first-exemplar design
- `2026-04-17-typed-route-phase1-plan.md` — substrate precedent (`ArrayHandler.cpp`)
- `2026-04-15-typed-route-gap-analysis.md` — architectural rules

---

## Goal

Land one typed route (native direct-sdk) that distributes block instances along a curve with three methods, seeded randomness, and atomic rollback. Promote `DistributeBlocksAlongCurve.py` to a frozen reference artifact.

## Repo boundary

This is a **paired cross-repo change**, not a single PR.

- **Rook code PR** — items 1–6 below. Implementation work.
- **rook_docs changes** — items 7–8 below. `rook_docs` is not versioned with Rook (no `.git`); handle adjacent to the code PR but do not bundle them. The Rook PR must not wait on the rook_docs change or vice versa.

## In scope — Rook code PR

| # | File | Change |
|---|---|---|
| 1 | [src/RookNative/Handlers/BlocksHandler.h](src/RookNative/Handlers/BlocksHandler.h) | Declare `HandleBlockDistributeAlongCurve`. Declare `HandleBlockDebugFailNextInstance` (internal debug, matches `ArrayHandler.h` precedent for `HandleDebugFailNextCopy`). |
| 2 | [src/RookNative/Handlers/BlocksHandler.cpp](src/RookNative/Handlers/BlocksHandler.cpp) | Implement `HandleBlockDistributeAlongCurve` sibling to `HandleBlockArrayInstances` (line 3059). Substrate: direct-sdk native. **Replicate** the `StructuredError` + `SendStructuredError` pattern locally in this file's anonymous namespace — ArrayHandler's versions are file-local and not directly reusable. Future extraction of these into `Infrastructure/` as shared helpers is explicitly out of scope. Opening comment states: direct-sdk substrate, atomic-with-rollback batch mode, closed error-code set, seeded `std::mt19937`. One `UndoScope(pDoc, L"Distribute Blocks Along Curve")` + explicit mid-loop rollback via `pDoc->DeleteObject` on already-created copies. Also implement `HandleBlockDebugFailNextInstance` with `DebugRoutesEnabledOrRefuse` env gate and a static `std::atomic<int> g_debugFailInstanceIndex{0}` analogous to `g_debugFailCopyIndex` in ArrayHandler. |
| 3 | [src/RookNative/RookServer.cpp](src/RookNative/RookServer.cpp) | Register two routes adjacent to `/block/array-instances` (line 1344): `m_server->Post("/block/distribute-along-curve", ...)` and `m_server->Post("/block/_debug/fail-next-instance", ...)`. Debug route follows the pattern at line 1154 for `/array/_debug/fail-next-copy`. |
| 4 | [mcp_server/src/rook/server.py](mcp_server/src/rook/server.py) | `Tool(name="rhino_block_distribute_along_curve", ...)` in `list_tools()` adjacent to `rhino_block_array_instances` (line 4145). `case "rhino_block_distribute_along_curve":` dispatch adjacent to existing case (line 11206). **The debug route is NOT exposed as an MCP tool** (matches ArrayHandler precedent — debug routes are native-only, test-harness-only). |
| 5 | [mcp_server/src/rook/learning/intent_runtime.py](mcp_server/src/rook/learning/intent_runtime.py) | `routes["block_distribute_along_curve"] = RouteSpec(...)` in `_build_route_table()`. Add `"block_distribute_along_curve"` to the existing `"blocks"` tuple in `CATEGORIES` (line 1341) — not a new tuple. The existing test `test_all_block_ops` at [test_intent_runtime.py:419](mcp_server/tests/test_intent_runtime.py#L419) picks up the new operation automatically. |
| 6 | `mcp_server/tests/test_block_distribute_along_curve_live.py` (new file, matches `test_array_linear_live.py` precedent) | Live-route test file containing both contract tests (early-return paths) and integration tests (full execution). Runs against the live native server — consistent with the existing test harness; no new no-Rhino unit layer introduced. |

## In scope — rook_docs changes (separate, not part of Rook PR)

| # | Path | Change |
|---|---|---|
| 7 | `rook_docs/script-reference/promoted/DistributeBlocksAlongCurve.py` | Move from `C:\Users\aryan\Documents\RhinoScripts\`. Header stamp: `# PROMOTED 2026-04-22 to POST /block/distribute-along-curve (rhino_block_distribute_along_curve). Reference artifact — do not invoke at runtime.` Creates the `promoted/` subdirectory (first use). |
| 8 | `rook_docs/work-queue.md` | Mark the exemplar landed. |

## Out of scope — explicit exclusions

- `preview` mode (additive future PR)
- Attribute inputs `layer`/`color`/`visible`/`name`/`material` — chain via `rhino_block_set_instance_properties` / `rhino_block_set_instance_visibility` post-creation
- `sourceInstanceIds` alias (Q4 — additive post-soak)
- Generic `/array/along-curve` for arbitrary objects (different copy primitive; separate route)
- `/block/distribute-on-surface`, `/block/distribute-in-region` (future family)
- `BlockPlacementHandler.cpp` extraction (defer until 2+ placement routes land)
- Extraction of `StructuredError` / `SendStructuredError` into `Infrastructure/` shared helpers (separate refactor)
- Drift cleanup of existing `HandleBlockArrayInstances` which still uses `SendError(ex.what())` (gap-analysis drift-cleanup target 1; separate PR)
- `IntentPlanner` enhancement (Q7a follow-up, only if recognition rate is low)
- Parameter satisfiability via selection context (Q7b)
- Thin Rhino command wrapper

## Test plan

All tests live in the one new `test_block_distribute_along_curve_live.py` file. Harness is live-route — consistent with `test_array_linear_live.py`.

### Contract tests — early-return paths

These tests require the live native server but do not need curve/block fixtures because they fail before dispatch or early in the UI-thread call.

| Test | Assert |
|---|---|
| `method=fill` with `spacing` present | `{success: false, data: {errorCode: "invalid_input", ...}}` |
| `method=fixedSpacing` with `count` or `placement` | `invalid_input` |
| `method=fixedCount` with `distribution` | `invalid_input` |
| `keepUpright=true` with `orientation="world"` | `invalid_input` |
| `scaleMode="randomRange"` with `minScale > maxScale` | `invalid_input` |
| Missing `curveId` / `blockNames` / `method` | `invalid_input`, names the missing field |
| Empty `blockNames: []` | `invalid_input` |
| Malformed JSON body | 4xx / parse error |
| Bogus `curveId` | `not_found` |
| All-missing `blockNames: ["Missing"]` | `empty_pool` |

### Integration tests — full execution paths

Require a live curve + live block definitions in a fixture document.

| Test | Assert |
|---|---|
| Each `method` × valid companion fields | 200 with success payload; `seedUsed` present when `seed` omitted |
| `fill`/`even` `count=10` `seed=42` | Deterministic `sampledPositions` across two calls |
| `fill`/`random` `count=10` `seed=42` | Deterministic across two calls |
| `fixedSpacing` `spacing=3.0` `spacingVariation=0` | Positions at exact multiples of 3 |
| `fixedSpacing` `spacingVariation=0.5` `seed=42` | Deterministic across two calls |
| `fixedCount` `placement=start\|center\|end` | Positions match placement spec |
| `orientation=followCurve` on near-vertical tangent sample | World-X fallback path exercised; `vertical_tangent_guard` warning emitted |
| `orientation=world` | Transforms use world-XY source plane |
| `rotationMode=random` `seed=42` | Deterministic yaw angles |
| `scaleMode=randomRange` `min=0.8 max=1.2 seed=42` | Deterministic scales |
| Zero-length curve | `invalid_geometry` |
| Success → Rhino undo | Single undo step removes all created instances |
| Mid-loop failure via `POST /block/_debug/fail-next-instance` with `ROOK_ENABLE_DEBUG_ROUTES=1` | `operation_failed`, zero instances remain, structured error payload |

### Operation-recognition test (Q7a smoke)

**Harness:** `await planner.plan(prompt)` where `planner = IntentPlanner(router)`. Assert `plan.operation == "block_distribute_along_curve"` on the returned `ExecutionPlan`. The prompts are pure natural-language strings — [intent_planner.py:134](mcp_server/src/rook/learning/intent_planner.py#L134) signature is `plan(intent: str, context: dict | None)` with no separate typed-argument parameter.

**Scope:** recognition only. Does not assert anything about parameter population. A recognized plan may have empty/default params because the prompts contain no concrete `curveId` or `blockNames` — that is expected and acceptable. Full parameter satisfiability is Q7b, out of scope.

**Example prompts** (pure NL, no embedded arguments):
- `"distribute blocks along this curve"`
- `"scatter blocks along the path"`
- `"array these blocks along the curve"`
- `"populate this curve with blocks"`
- `"place blocks along path"`
- Plus 5 edge/variant phrasings

**Target:** ≥80% of the 10 prompts return `block_distribute_along_curve` as the operation.

This test is distinct from two other surfaces that are NOT exercised here:
- `plan_direct(operation=..., params=...)` — explicit routing, bypasses the extractor
- Direct MCP tool call — handler execution only, bypasses the planner

## Merge gate (draft → final)

1. Contract + integration tests green locally (native server running).
2. Operation-recognition smoke test hit rate ≥80%.
3. If recognition rate <80%: pause. File Q7a follow-up as a sibling PR before merging; do not expand this PR's scope mid-flight.
4. Codex PR-level review on the draft.
5. User review; squash merge per PR workflow.

## Resolved decisions

| # | Decision |
|---|---|
| A | **`CATEGORIES` grouping: existing `"blocks"` tuple.** No new category; test coverage propagates via existing `test_all_block_ops`. |
| B | **`sampledPositions` echo threshold: 1000.** Above → `null` with `sampledPositionsOmittedReason: "count_exceeds_echo_limit"`. |
| C | **Debug seam in this PR: yes, explicitly scoped.** Three artifacts: header declaration (item 1), implementation with env gate (item 2), route registration as native-only (item 3). Not an MCP tool (item 4 exclusion). |
| D | **Handler home: `BlocksHandler.cpp`.** Extract into `BlockPlacementHandler.cpp` when a second placement route lands. |
| E | **Script move + work-queue update: separate from the Rook PR.** Items 7–8 are rook_docs changes, handled adjacent but not bundled. |

## Risk callouts (non-blocking, explicit)

- **Q1** — `sampledPositions` payload size at high counts. Mitigated by threshold (decision B).
- **Q7a** — Operation recognition rate. Mitigated by merge gate (step 3).
- **Q7b** — Parameter satisfiability from selection context. Explicitly out of scope.

## Schema reference (from doctrine doc)

For reviewer convenience, the request/response shapes. Full rationale in `2026-04-22-exotic-capability-promotion-plan.md` §Worked Example Stage 3.

**Request** (MCP wire format, camelCase):

```json
{
  "curveId": "uuid",
  "blockNames": ["Tree_A", "Tree_B"],
  "method": "fill" | "fixedSpacing" | "fixedCount",
  "count": 24,
  "spacing": 3.0,
  "spacingVariation": 0.4,
  "distribution": "even" | "random",
  "placement": "start" | "center" | "end",
  "orientation": "followCurve" | "world",
  "keepUpright": true,
  "rotationMode": "none" | "random",
  "scaleMode": "fixed" | "randomRange",
  "minScale": 0.8,
  "maxScale": 1.2,
  "seed": 42
}
```

**Success response** (plural-creator cardinality):

```json
{
  "success": true,
  "data": {
    "createdCount": 24,
    "instanceIds": ["uuid", "..."],
    "mode": "fill",
    "parametersUsed": {
      "distribution": "even",
      "orientation": "followCurve",
      "keepUpright": true,
      "rotationMode": "none",
      "scaleMode": "fixed"
    },
    "seedUsed": 42,
    "sampledPositions": [[x, y, z], "..."],
    "sampledParameters": [t0, t1, "..."],
    "warnings": []
  }
}
```

**Error codes** (closed set for this handler):

| Code | Condition |
|---|---|
| `invalid_input` | Schema / mode validation failure |
| `not_found` | `curveId` does not resolve OR no `blockNames` entry resolves to a live idef |
| `invalid_geometry` | Curve has zero length OR is degenerate per tolerance |
| `empty_pool` | `blockNames` non-empty but zero resolved (all missing) |
| `operation_failed` | Mid-loop `CreateInstanceObject` failure; rollback succeeded |
| `rollback_failed` | Mid-loop failure occurred AND rollback cleanup partially failed |

---

This scope is implementation-ready. Begin with item 1 (header) through item 6 (test file) in that order. Items 7–8 happen adjacent to, not bundled with, the Rook PR.
