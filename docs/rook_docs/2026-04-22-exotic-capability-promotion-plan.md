# Exotic Capability Promotion: Doctrine and First-Exemplar Plan

**Date:** 2026-04-22
**Author:** bringfire + Claude (reviewed against Codex)
**Status:** Design record and implementation plan; ready for Codex review then build
**Related:**
- `2026-04-15-typed-route-gap-analysis.md` — theory-of-capability shift this doc extends
- `2026-04-22-exotic-capability-promotion-design.md` — earlier design draft; this doc formalizes it
- `2026-04-17-typed-route-phase1-plan.md` — substrate precedent (direct-sdk arrays)
- `2026-04-10-public-skills-brainstorm.md` — origin of the script-library proposal this doc constrains

---

## Executive Summary

The typed-route gap analysis corrected the original theory of capability that shaped early Rook: that an AI harness should simulate a human at the command line. This document applies the same correction to a second source of capability ideas — user-authored Rhino Python scripts — and turns the result into a binding doctrine plus a concrete first-exemplar implementation plan.

The core claim is narrow and should not be conflated with "ship a script library":

> **Agents do not reduce the need for typed contracts. They increase the set of operations worth promoting to typed contracts in the first place.**

User-authored scripts are the right source of promotion candidates. They are not the right shipped runtime substrate. A script library deployed alongside the installer — where agents read, adapt, and execute scripts as the primary mechanism for exotic capabilities — recreates the exact failure modes the command-string era demonstrated: opaque execution, late validation, weak outputs, drift across consumers, and discovery-by-prompt-trick. The typed-route doctrine from the gap analysis applies without modification.

What changes in this document:

1. A promotion pipeline (Stage 0–6) that turns script-originated capabilities into typed routes with binding doctrine on classification, substrate selection, and historical cleanup.
2. Contract standards specific to exotic capabilities — where they differ from Phase 1 primitives (seedable randomness, sampled intermediate state in response, explicit rejection of accepted-but-ignored parameters).
3. Discovery doctrine for the three real consumer classes (internal HTTP agents, MCP clients, in-repo LLMs).
4. A full worked plan for the first exemplar: `POST /block/distribute-along-curve`, promoted from `DistributeBlocksAlongCurve.py`. Handler home, schema, substrate, route registration, MCP tool, CapabilityRouter entry, and a layered test plan.

Decisions that require empirical resolution are flagged explicitly at the end. Everything else is settled.

---

## Why This Document Exists

The gap analysis (2026-04-15) focused on operations Rhino itself exposes as commands. Its inventory was closed: ~196 learned commands, with 106 already typed and a bounded set of remaining gaps. That document is the doctrine for canonical-capability promotion.

A separate class of capabilities does not sit inside Rhino's command vocabulary at all. They are user-authored: distribute blocks along a curve, populate site furniture along a road, scatter trees with spacing rules and random yaw, orient instances to frames sampled from a surface. These are operations users keep reaching for in ad-hoc scripts because Rhino does not ship them as first-class commands.

The agent moment changes the economics of promoting these. Before, turning a script into a command was architecturally expensive and semantically lossy — commands required human-oriented prompts, options, and modal flow. Now, a typed route with camelCase parameters, enum modes, seeded randomness, and a structured response is straightforwardly accessible to an agent that can compile fuzzy user intent ("scatter trees along this road") into exact typed arguments. The surface is simpler, the contract is stronger, and the consumer is better.

This creates a new promotion backlog. The doctrine for handling it cannot be "expand the script-reference folder and teach agents to adapt" — that is the command-string fallback reborn. The doctrine must be an extension of the typed-route gap analysis, applied to a new source.

The 2026-04-22 design draft (`exotic-capability-promotion-design.md`) established the rules at a doctrinal level. This document formalizes those rules, resolves the open questions the draft left, and lands the first exemplar plan in implementation-ready form.

---

## Theory Continuity: This Is the Gap Analysis Applied to a New Source

The gap analysis established seven architectural rules binding on new typed routes (Decision Record §2). Those rules do not change for exotic capabilities. Every promoted exotic route inherits them:

1. Outer envelope `{success, data}` with structured error payloads.
2. Two-stage validation (worker thread JSON / UI thread document state).
3. One semantic route per operation, or a family endpoint with closed discriminator.
4. One `UndoScope` per request.
5. Response contract by operation class with declared cardinality.
6. Execution substrate is explicit per route with rationale.
7. Batch mode declared explicitly.

What differs for exotic capabilities is **intake**. Gap-analysis intake starts from the Rhino command vocabulary. Exotic intake starts from a user-authored script with an interactive shell and a load-bearing algorithm tangled together. The promotion pipeline in §5 is the disentanglement protocol.

This doc therefore does not introduce a new philosophy. It adds a source-side pipeline to the existing typed-route doctrine.

---

## Hard Constraints from the Live Repo

These are enforced by code, not by convention. A proposal that conflicts with them is dead on arrival.

### 1. Interactive `rhinoscriptsyntax.Get*` calls are refused before dispatch

`rhino_execute` preflight at `mcp_server/src/rook/server.py` (`_find_blocking_rhinoscriptsyntax_call`, ~line 10883) scans submitted code for `rs.GetObject`, `GetObjects`, `GetString`, `GetInteger`, `GetReal`, and related prompt forms. On match, the script is rejected with an explanatory error and never sent to Rhino. The original `DistributeBlocksAlongCurve.py` uses five such calls and is therefore unrunnable as-is through any agent path. This is not a soft preference; it is a runtime guard.

### 2. Typed routes are the preferred substrate

`CLAUDE.md` line 143 states the policy directly: typed routes over scripts. `rhino_execute` and `rhino_command` have built-in error handling and preflight, but typed routes remain canonical because they validate inputs, track created objects, and avoid edge cases where a Rhino command pops a native dialog that blocks the UI thread.

### 3. Three consumer classes, not one

- **Rook-internal agents** (Planner, Workers) call `127.0.0.1:{port}` HTTP routes directly. They do not use MCP.
- **MCP clients** (Claude Code, Codex via MCP) discover tool schemas through the MCP server's tool-list.
- **In-repo LLMs** (Claude Code, Codex reading files directly) consume prose instructions via `CLAUDE.md`, `AGENTS.md`, skill markdown, and nearby source code.

A capability that is only discoverable via one of these three paths is effectively invisible to the other two. The gap analysis's §3 boundary policy already implies this, but this document makes it explicit: **discovery is a first-class contract**, not a consequence of implementation.

### 4. One load-bearing implementation per capability

Once a typed route ships, the originating script is not a shipped parallel implementation of the same algorithm. That is drift by construction. Historical scripts live in `rook_docs/` as frozen reference artifacts; keyboard-driven Rhino UX (if still useful) is a thin wrapper that calls the typed handler, not a copy of its logic.

### 5. Direct-sdk native is the default substrate when reachable

Phase 1 settled this in the gap analysis Decision Record §3: "default to native C++ direct SDK when the capability is reachable that way and the implementation is direct and stable." Managed-bridge delegation is reserved for RhinoCommon-only APIs, established managed-side state ownership, or known native-path crash patterns. Exotic capabilities inherit this default.

---

## Doctrine: The Five Rules for Script-Originated Capabilities

The 2026-04-22 design draft proposed nine rules. These consolidate and harden to five; the rest are implied by the gap analysis doctrine they extend.

### Rule E1 — Classification happens before implementation

Every script-originated capability lands in exactly one of three buckets:

| Bucket | Shape | Target |
|---|---|---|
| **Reusable operation primitive** | Stable algorithm, bounded parameter space, single input→output transformation | Typed route |
| **Multi-step workflow** | Value is in sequencing, auditing, interviewing, combining multiple primitives | Skill that composes typed routes |
| **Exploratory / niche / weakly bounded** | Not yet stable enough to schema-ize; parameter space open-ended | Reference artifact in `rook_docs/` only; agents do not depend on it |

A capability's bucket is not negotiable mid-implementation. If classification is unclear, it belongs in the third bucket until the ambiguity is resolved.

### Rule E2 — Parameterization beats adaptation

A capability promoted to a typed route must be expressible as `(stable executable body, structured parameter block)`. If "the agent edits 40 lines of the script body" is part of the runtime plan, the contract is underspecified — go back to Stage 3 contract design. Free-form `# ADAPT:` markers are a prototyping aid, not a production contract.

### Rule E3 — Interactive prompts are not contract surface

Every `rs.Get*` call in the source script becomes, on promotion, one of three things:

1. A required typed input.
2. A typed input with a documented default.
3. A skill-level interview question in the orchestrating skill (never in the typed route itself).

Typed routes accept structured arguments and fail fast on missing required fields. They do not pause for input.

### Rule E4 — Randomness must support deterministic replay

Any capability that exposes randomness (distribution variation, scale ranges, rotation jitter) accepts an optional `seed` parameter and echoes the `seedUsed` in the success payload. When `seed` is omitted, the handler generates one (e.g., from `std::random_device`) and echoes it. Without this, debugging, test repeatability, and user trust all degrade. This is not a nice-to-have.

### Rule E5 — Response payloads carry forward chaining state

Gap analysis Rule 5 already declares creators return full `ObjectSnapshot` arrays and mutations return sparse metadata. Exotic capabilities frequently sit between the two: they create instances (creator-like) but compute rich intermediate state (sampled positions, curve parameters, frames) that downstream operations need.

For placement and distribution routes specifically, success payloads carry:

- `createdCount: int`
- `instanceIds: [uuid]` (or `objectIds: [uuid]` for non-instance creators)
- `mode: string` — the discriminator actually taken
- `parametersUsed: object` — echo of inputs plus any defaulted fields
- `seedUsed: int` — when randomness is involved
- `sampledPositions: [[x,y,z]]` — optional but strongly preferred; enables "re-run with these exact positions" and downstream reasoning
- `warnings: [string]` — structured skip/clamp messages (e.g., curve tangent failure at sample k)

The cardinality contract is **plural creator**, per gap analysis Rule 5. Response shape is `{createdCount, instanceIds: [...], ...}` even when `count = 1`. Never bare snapshot.

---

## The Promotion Pipeline

Every script-originated capability passes through these stages. Skipping stages is drift.

### Stage 0 — Intake

Record the capability as a candidate:

- source artifact path
- author / provenance
- the real problem it solves (one sentence)
- how often users reach for it
- which bucket it is likely to land in (Rule E1)

Intake is lightweight — a single entry in a candidate inventory. It is not a full design.

### Stage 1 — Algorithm extraction

Separate the source script into two layers:

- **Interactive shell** — object pickers, prompt strings, print statements, `EnableRedraw` toggles, global random without seed
- **Load-bearing algorithm** — geometry math, sampling logic, transform composition, frame construction, validation invariants

Only the second layer is a candidate for promotion. The first is discarded.

### Stage 2 — Classification

Apply Rule E1. Most candidates should land as primitives; some belong as skills; a few as reference artifacts. Record the classification with a one-sentence justification.

### Stage 3 — Contract design (pre-code)

Write the contract before writing any handler code:

- Route namespace and path
- MCP tool name (canonical form: `rhino_<verb>_<noun>` per gap analysis §5)
- CapabilityRouter intent key
- Input schema (camelCase, closed enums where possible, explicit required vs optional)
- Defaulting rules (document-derived defaults explicit, never hardcoded)
- Response payload (per Rule E5)
- Error taxonomy (closed set per gap analysis §4)
- UndoScope / rollback behavior
- Randomness / seed behavior (Rule E4)
- Intent vocabulary and natural-language triggers — primary surface is the operation key itself (what the DSPy extractor sees on the internal fast path); secondary surface is the MCP tool description (for external MCP clients). RouteSpec description is documentation-only today.

### Stage 4 — Substrate decision

Apply gap-analysis §3 policy in this order:

1. **Native direct-sdk** — default when the capability reaches C++ SDK cleanly. No ABI bump. No bridge crossing.
2. **Managed-bridge reuse** — when the capability needs RhinoCommon-only APIs (SubD, modern surface factories, SpaceMorph) and an existing bridge callback suffices. No ABI bump.
3. **Managed-bridge new callback** — when managed APIs are needed AND no existing callback maps. Bumps `BridgeAbiVersion`. Must be argued on clarity grounds, not presented as technical necessity.
4. **Script/command fallback** — never the target design. Permitted only as a temporary spike or migration bridge, with a written exit plan.

Record the choice and its rationale in the handler's opening comment per gap-analysis §2 Rule 6.

### Stage 5 — Implementation

A capability is not promoted until all of these ship together:

1. HTTP route registered in `RookServer.cpp`
2. C++ handler (or C# companion handler for managed-bridge paths) with structured error responses
3. MCP tool definition in `server.py` with full schema and dispatch
4. CapabilityRouter `_routes` entry in `intent_runtime.py` (registered operation key, required/optional params, description) — this is the load-bearing routing artifact
5. `CATEGORIES` grouping update (cosmetic; keeps introspection clean but not a routing gate)
6. Test coverage at the layers the capability reaches
7. Documentation touching: handler header, MCP tool description, any affected skill docs

Partial promotions that land the route but omit the `_routes` entry or MCP tool are drift the moment they merge. Landing all seven in one PR is the target.

**Routing registration vs. language recognition.** These are separable concerns and the doctrine should not conflate them:

- **Routing registration** — the `_routes` entry is the load-bearing artifact. Once the operation key is in `_routes`, `CapabilityRouter.route()` and `has_direct_route()` return it, and downstream dispatch can reach the native endpoint.
- **Language recognition for internal fast-path planning** — the DSPy extractor in `IntentPlanner` sees `available_operations = self._router.list_operations()` and nothing else ([intent_planner.py:259](mcp_server/src/rook/learning/intent_planner.py#L259)). Operation-key quality is therefore the primary language-recognition aid on the internal path. Rich semantic keys (`block_distribute_along_curve`) give the extractor tokens to match against; opaque keys do not.
- **Language recognition for external MCP clients** — the MCP tool description is read by MCP-side tool-selection logic in the client. This is the client-visible prose surface.
- **Prose documentation** — handler headers and this doc provide domain-language context for in-repo LLMs reading files directly.

`RouteSpec.description` exists on every `_routes` entry and is readable by any code that holds a `RouteSpec` reference, but it is **not** surfaced through any of the CapabilityRouter's public introspection APIs (`list_operations()` returns keys; `categories()` at [intent_runtime.py:1439](mcp_server/src/rook/learning/intent_runtime.py#L1439) returns the `CATEGORIES` grouping map) and it is **not confirmed** to be in the fast-path planner prompt today. Use it for documentation purposes and as a future hook; do not rely on it as the routing surface.

No separate pre-DSPy keyword table for Rhino typed routes exists today: `knowledge/gh/sparse_index.json` is a Grasshopper-component GUID cache ([`GHSparseIndex` docstring explicitly marks it deprecated and GH-only](mcp_server/src/rook/learning/gh_knowledge.py#L66)), not a Rhino-capability routing surface. If empirical testing shows operation-key matching is insufficient (Q7 below), the follow-up fix lives in `IntentPlanner` — either enriching extractor inputs with descriptions, adding a regex-extraction layer, or introducing a dedicated Rhino keyword table — not by overloading the sparse index.

### Stage 6 — Historical cleanup

Once the typed route ships:

- The original script moves to `rook_docs/script-reference/promoted/` as a frozen reference artifact with a header pointing at the typed route that replaced it, OR it is deleted entirely if the reference value is low.
- Any keyboard-driven Rhino UX (if still useful) becomes a thin `.py` command that gathers prompts via `rs.GetObject` and POSTs to the typed route. It does not re-implement the algorithm.
- Candidate inventory entry marked `promoted`.

There are never two shipped implementations of the same algorithm. Drift starts here; prevent it here.

---

## Contract Standards Specific to Exotic Capabilities

The gap analysis Decision Record §4 covers canonical contract standards. The following additions or specializations apply to exotic capabilities.

### Naming convention

| Layer | Example |
|---|---|
| Operation key (routing + language recognition) | `block_distribute_along_curve` |
| MCP tool | `rhino_block_distribute_along_curve` |
| Route path | `POST /block/distribute-along-curve` |
| Handler function | `HandleBlockDistributeAlongCurve` |

The operation key deserves special attention. `IntentPlanner` caches `self._router.list_operations()` (operation keys only, no descriptions) and feeds that list to the DSPy extractor as `available_operations` ([intent_planner.py:128, 259](mcp_server/src/rook/learning/intent_planner.py#L128)). That means the operation key is the primary natural-language recognition surface for internal fast-path planning, not the RouteSpec description. Choose keys that carry domain vocabulary: `block_distribute_along_curve` beats `block_dac` or `distribute_v1` because the DSPy extractor has words to match against.

Namespace selection follows the closest-precedent rule: the route lives under the namespace that owns the primary artifact class it manipulates. Block-instance creation lives under `/block/*` because `HandleBlockArrayInstances` already owns that neighborhood. A generic `/array/along-curve` that works on arbitrary object IDs (Breps, meshes, points) would live under `/array/*` as a sibling to the Phase 1 array trio.

### Seed / randomness

- Optional `seed: integer` in the input schema.
- Handler uses `std::mt19937` seeded with the user-supplied value, or with `std::random_device{}()` when omitted.
- Success payload echoes `seedUsed: integer` unconditionally when the route exposes randomness.
- Handlers must not use the C `rand()` family or unseeded sources. Deterministic replay depends on this.

### Sampled intermediate state

For placement and distribution routes, the handler commonly computes intermediate arrays (sampled curve parameters, frames, per-instance transforms). These SHOULD appear in the success payload when bandwidth allows:

- `sampledPositions: [[x, y, z]]` for point-like samples
- `sampledParameters: [t]` for curve parameters (enables re-running with `method: "exact"` in a future PR)
- Omit when `count` is very large (> ~10000) and replace with `"sampledPositions": null, "sampledPositionsOmittedReason": "count_exceeds_echo_limit"`. Threshold to be resolved in first-PR review.

### Preview / dry-run

Preview mode is a legitimate future addition but is NOT shipped in PR 1. Do not accept a `preview` field that the handler silently ignores — an accepted-but-ignored parameter is a footgun: an agent that sets `preview: true` expecting no mutation will cause mutation anyway.

Adding `preview: boolean` later is trivially backward-compatible (JSON schemas with new optional fields are additive), so no schema reservation is needed now. When preview lands, the target behavior is: `preview: true` runs sampling and transform composition but skips `CreateInstanceObject`, returning the full success payload shape minus `instanceIds` (empty array) and with `mode: "<original>+preview"`. The agent can then inspect `sampledPositions` and re-invoke with `preview: false`.

### Error taxonomy for exotic routes

Beyond the gap-analysis §4 closed set (`invalid_input`, `not_found`, `operation_failed`), exotic capabilities commonly need:

- `invalid_geometry` — a supplied curve/surface is degenerate, self-intersecting, or below tolerance
- `rollback_failed` — mid-loop failure occurred AND cleanup of already-created copies partially failed (rare; distinct from `operation_failed` because some copies may have persisted)
- `empty_pool` — the source resolution produced zero candidates (e.g., `blockNames` contained only missing definitions)

Each handler declares its error codes at the top; the set is closed per handler.

---

## Discovery Across Three Consumer Classes

Apply to every promoted exotic route. All three surfaces are mandatory, not alternative.

### Internal HTTP agents

Discovery mechanism: direct HTTP introspection is not part of the current native server (no `/openapi` endpoint). Instead, the Planner and Workers consume the CapabilityRouter's route table in `intent_runtime.py`. A promoted route is discoverable to internal agents **once its `routes["<op>"] = RouteSpec(...)` entry lands in `_build_route_table()`**. The `CapabilityRouter.route()` and `has_direct_route()` methods consult `self._routes` only ([intent_runtime.py:1425](mcp_server/src/rook/learning/intent_runtime.py#L1425)); this is the load-bearing artifact for routing discoverability.

`CATEGORIES` at the bottom of the module is grouping metadata (exposed via `CapabilityRouter.categories()` at [intent_runtime.py:1443](mcp_server/src/rook/learning/intent_runtime.py#L1443)), not a routing gate. It is still worth updating for introspection and any UI that groups operations by family, but its omission does not make a route undiscoverable — the `_routes` entry is sufficient.

Loss mode: `_routes` entry missing → internal agents cannot invoke the route through intent runtime; they must hardcode HTTP POST. This is drift. CATEGORIES omission is cosmetic drift only.

### MCP clients

Discovery mechanism: MCP tool-list response served by `server.py`. A promoted route is discoverable **once its `Tool(name=..., inputSchema={...})` block lands in `list_tools()` and its `case "rhino_..."` branch lands in `call_tool()`**.

Loss mode: Tool omitted → MCP clients (including Codex via MCP) cannot see the capability at all.

### In-repo LLMs

Discovery mechanism: prose and source. A promoted exotic route is discoverable **once it is referenced in at least one of**: `CLAUDE.md` top-tier list (for load-bearing capabilities), skill docs that use it (for workflow-orchestrated use), or source-adjacent documentation (handler header and, for the exemplar exotic family, an entry in this doctrine doc's worked-example section).

AGENTS.md mirror: for capabilities important enough to change agent behavior, the guidance appearing in `CLAUDE.md` should be mirrored into `AGENTS.md` to cover Codex sessions. First-exemplar scope: no CLAUDE.md/AGENTS.md change needed; the promotion pipeline itself is the behavior change and belongs in this design doc and in the work-queue pointer.

### Candidate catalog (optional, deferred)

A lightweight `rook_docs/exotic-capability-candidates.yaml` could track candidates through the pipeline with fields (`candidateId`, `status`, `sourceScript`, `proposedRoute`, `classification`, `owner`, `openQuestions`). This is explicitly **not a script catalog** — it catalogs **promotion state**, not runtime artifacts. Deferred until the first exemplar ships and a second candidate emerges; building the catalog before there is a queue is premature.

---

## Anti-Patterns (What This Doctrine Rejects)

Listed here so the boundaries are not re-litigated downstream.

### A1 — "Ship the script, let agents adapt"

The shape proposed in `2026-04-10-public-skills-brainstorm.md` §"Infrastructure: Script Library" as the `adapt-then-run` tier. Rejected because:

- `rhino_execute` refuses interactive prompts by preflight; the shipped script cannot run as-is.
- Free-form mutation of an executable body expands the attack surface. A typed route's small validated argument shape minimizes it.
- `# ADAPT:` markers signal where to edit, not how; they cannot enforce invariants.
- Discovery devolves to "skill markdown points at file path" — works for Claude Code, fails for Codex and internal HTTP agents.

This doctrine does not ship shipped-script runtime. It ships typed routes.

### A2 — "The script library is useful as a reference, so let agents adapt it"

A reference is not a runtime. `rook_docs/script-reference/` and `rook_docs/script-reference/promoted/` are harvest sources for algorithm discovery and test material. Agents may read them at implementation time as design inputs; they are not invoked at runtime.

Cloned reference repos (`rhinopython/`, `rhino-developer-samples/`, etc., currently in `script-reference/`) stay where they are. Provenance and license are clear. Runtime is not.

### A3 — "Skip the MCP tool because the internal agents already use the route"

Rejected. A capability that skips one of the three consumer classes is invisible to part of the user base. If a promotion is not worth writing an MCP tool for, the capability is not important enough to promote yet — keep it as a reference script in bucket 3.

### A4 — "Keep the original script as a manual utility alongside the typed route"

Rejected by Rule 5-supporting policy: one load-bearing implementation per algorithm. If the keyboard-driven Rhino command is valuable, it is a thin wrapper that calls the typed route. Not a duplicated implementation.

### A5 — "Generalize to arbitrary objects in the first PR"

Rejected for the first exemplar. Block-scoped is tighter and ships faster. The generic `/array/along-curve` for Breps/meshes/points is a separate route in a separate PR with separate substrate consideration (instance creation vs object duplication). Gap-analysis Rule 6 ("reusing is the default; adding is a deliberate architectural choice") applies: do not widen scope without evidence.

---

## Worked Example: `POST /block/distribute-along-curve`

Full promotion plan for the first exemplar. Source artifact: `C:\Users\aryan\Documents\RhinoScripts\DistributeBlocksAlongCurve.py`.

### Stage 0 — Intake

| Field | Value |
|---|---|
| candidateId | `block_distribute_along_curve_v1` |
| sourceScript | `DistributeBlocksAlongCurve.py` (bringfire-authored, Rhino Python / IronPython) |
| problemSolved | Populating site elements (trees, furniture, lights, bollards) along paths with controlled spacing, scale, and orientation |
| reachFrequency | High — demonstrated repeatedly in landscape, urban design, and roadside workflows |
| initialBucket | Primitive (Rule E1) |

### Stage 1 — Algorithm extraction

The source script is 312 lines. The interactive shell (discardable) is lines 17–133 (three `rs.Get*` helpers and `GetDistributionSettings`) plus the `main()` dispatcher (270–311). The load-bearing algorithm (promotable) is `DistributeBlocksAlongCurve()` at lines 135–268:

- Curve length-parameterization and three distribution methods (`fill_curve` even/random, `fixed_spacing` with variation, `fixed_count` with start/center/end placement)
- Upright-frame construction at lines 222–244: project tangent to XY, guard against vertical tangents (|x_axis| < 0.001 → use world X), `PlaneToPlane` from world XY to target
- Transform composition order: align (PlaneToPlane) → rotate around world Z → scale from point
- Per-position: random block selection, `AddInstanceObject(idefIndex, transform)`

This is the capability. The interactive shell is discarded.

### Stage 2 — Classification

**Primitive.** The value is the placement algorithm, not sequencing. A skill might eventually orchestrate "capture site furniture from these references, then distribute along road hierarchy" — that is a Rule E1 bucket-2 composition, and would *use* this primitive.

### Stage 3 — Contract design

**Route:** `POST /block/distribute-along-curve`

**MCP tool:** `rhino_block_distribute_along_curve`

**CapabilityRouter intent:** `block_distribute_along_curve`

**Input schema (camelCase, MCP wire format):**

```json
{
  "curveId": "uuid",                          // required
  "blockNames": ["string"],                   // required; min 1; random-pick pool
  "method": "fill" | "fixedSpacing" | "fixedCount",  // required; closed enum
  "count": 24,                                // required when method=fill or fixedCount
  "spacing": 3.0,                             // required when method=fixedSpacing or fixedCount
  "spacingVariation": 0.4,                    // optional; default 0; only valid with fixedSpacing
  "distribution": "even" | "random",          // optional; default "even"; only valid with fill
  "placement": "start" | "center" | "end",    // optional; default "start"; only valid with fixedCount
  "orientation": "followCurve" | "world",     // optional; default "followCurve"
  "keepUpright": true,                        // optional; default true; invalid when orientation="world"
  "rotationMode": "none" | "random",          // optional; default "none"
  "scaleMode": "fixed" | "randomRange",       // optional; default "fixed"
  "minScale": 0.8,                            // required when scaleMode=randomRange; must be > 0
  "maxScale": 1.2,                            // required when scaleMode=randomRange; must be >= minScale
  "seed": 42                                  // optional; handler generates one if omitted
}
```

**Mode validation (worker thread, pre-dispatch):**

- `method = "fill"` requires `count`; rejects `spacing`, `placement`.
- `method = "fixedSpacing"` requires `spacing`; rejects `count`, `placement`, `distribution`.
- `method = "fixedCount"` requires `count` and `spacing`; rejects `distribution`.
- `scaleMode = "randomRange"` requires `minScale` and `maxScale`; rejects `minScale > maxScale`.
- `keepUpright` is rejected as `invalid_input` when `orientation = "world"`. The field only has meaning under `orientation = "followCurve"`, and silently ignoring it would be the same accepted-but-ignored footgun the doctrine rejects for `preview`. Consistent rule: if a parameter has no effect in the selected mode, reject it; do not document-no-op it.

**Scope cut: attribute composition is out of this route.** `layer`, `color`, `visible`, `name`, and `material` are deliberately NOT accepted by this route. Created instances inherit the current layer, by-layer color, and default visibility. An agent that needs non-default attributes chains `rhino_block_set_instance_properties` or `rhino_block_set_instance_visibility` against the returned `instanceIds`. Rationale: the exotic part of this route is sampling, orientation, transforms, rollback, and reproducibility — attribute application is routine and already has typed tools. Keeping them out of PR 1 tightens the schema, avoids duplicating attribute-validation logic, and preserves a clean agent chain.

**Success response (cardinality = plural creator):**

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

`warnings` example entries:

- `"sample_k_frame_failed: curve FrameAt failed at t=0.42, sample skipped"`
- `"vertical_tangent_guard: sample_12 used world X fallback"`
- `"missing_block_definition: 'Tree_C' not found, removed from pool"`

**Error taxonomy (closed set for this handler):**

| Code | Condition |
|---|---|
| `invalid_input` | Schema / mode validation failure |
| `not_found` | `curveId` does not resolve OR no `blockNames` entry resolves to a live idef |
| `invalid_geometry` | Curve has zero length OR is degenerate per tolerance |
| `empty_pool` | `blockNames` non-empty but zero resolved (all missing) |
| `operation_failed` | Mid-loop `CreateInstanceObject` failure; rollback succeeded |
| `rollback_failed` | Mid-loop failure occurred AND rollback cleanup partially failed |

**Defaulting rules:**

- Tolerance for length-parameterization: `pDoc->AbsoluteTolerance()`.
- Created instances inherit Rhino's standard defaults (current layer, by-layer color, default visibility) via the underlying `CreateInstanceObject` call. These are handler-internal implementation details, not part of the route's contract — the route accepts no attribute fields (see scope cut in §Schema).

**UndoScope behavior:** one `UndoScope(pDoc, L"Distribute Blocks Along Curve")` wraps the entire operation. On mid-loop failure, handler explicitly deletes copies created earlier in the request before throwing `StructuredError{"operation_failed", ...}`. This matches the `ArrayHandler.cpp` precedent: "UndoScope is NOT transactional rollback" — the handler owns rollback.

**Batch mode (gap-analysis Rule 7):** **atomic with rollback**. Declared in handler header.

**Randomness:** `std::mt19937` seeded with user-supplied `seed` or `std::random_device{}()`. Used for: `spacingVariation` jitter (fixedSpacing mode), position draw (fill+random), block pool selection, rotation, scale range.

### Stage 4 — Substrate decision

**Direct-sdk native C++.** No ABI bump, no bridge crossing.

Rationale (recorded in handler opening comment):

- Block instance creation is already native: `pDoc->m_instance_definition_table.CreateInstanceObject(idefIndex, xform, ...)` is the existing path used by `HandleBlockArrayInstances` in `BlocksHandler.cpp:3059`.
- Curve evaluation is native: `ON_Curve::GetLength`, `ON_Curve::GetNormalizedArcLengthPoint`, `ON_Curve::FrameAt`, `ON_Curve::TangentAt` are all OpenNURBS C++ APIs with no RhinoCommon-only affordance.
- Transform composition is native: `ON_Xform::PlaneToPlane`, `ON_Xform::Rotation`, `ON_Xform::ScaleTransformation`.
- No SubD, no SpaceMorph, no modern surface factory — nothing that would route to managed per gap-analysis §3 default-by-coverage rule.

Precedent: `ArrayHandler.cpp` ships Phase 1's array trio with this exact substrate shape, including `StructuredError{code, message}`, explicit mid-loop rollback, and seeded-random test seam (`/array/_debug/fail-next-copy`). Follow the same pattern here.

### Stage 5 — Implementation plan

**Handler home decision:** extend `BlocksHandler.cpp` with `HandleBlockDistributeAlongCurve`, sibling to `HandleBlockArrayInstances` at line 3059.

Rationale: one new route does not justify a new handler file. The block-instance creation family is already colocated in `BlocksHandler.cpp`. If 2+ subsequent placement routes land (`/block/distribute-on-surface`, `/block/distribute-in-region`), extract a `BlockPlacementHandler.cpp` in the second-promotion PR; extracting now is premature.

**PR artifact list** (all in one PR):

1. **C++ handler** — `src/RookNative/Handlers/BlocksHandler.cpp`:
   - Declare `HandleBlockDistributeAlongCurve` in `BlocksHandler.h`.
   - Opening comment block names substrate (direct-sdk), batch mode (atomic with rollback), randomness source (`std::mt19937`), error-code closed set.
   - Worker-thread validation → `CMainThreadDispatcher::Instance().Dispatch(...)` → UI-thread execution with `UndoScope` and mid-loop rollback.
   - Use `StructuredError` pattern from `ArrayHandler.cpp`, not the `SendError(ex.what())` pattern from the existing `HandleBlockArrayInstances` (which is gap-analysis drift-cleanup target 1).

2. **Route registration** — `src/RookNative/RookServer.cpp`:
   ```cpp
   m_server->Post("/block/distribute-along-curve",
       [this](const httplib::Request& req, httplib::Response& res) {
           Handlers::HandleBlockDistributeAlongCurve(req, res);
       });
   ```
   Register adjacent to `/block/array-instances` (currently at line 1344).

3. **MCP tool** — `mcp_server/src/rook/server.py`:
   - Add `Tool(name="rhino_block_distribute_along_curve", description=..., inputSchema=...)` to `list_tools()`, adjacent to `rhino_block_array_instances` (line 4145).
   - Add `case "rhino_block_distribute_along_curve": result = await call_rhino("/block/distribute-along-curve", "POST", arguments)` to dispatch, adjacent to the existing block-array-instances case (line 11206).
   - Description copy: "Distribute block instances along a curve with three methods (fill/fixedSpacing/fixedCount), seeded randomness for reproducibility, and frame-aligned orientation with upright guard. Atomic mode: one undo record plus server-side rollback on mid-loop failure. Plural creator cardinality."

4. **CapabilityRouter entry** — `mcp_server/src/rook/learning/intent_runtime.py`:
   ```python
   routes["block_distribute_along_curve"] = RouteSpec(
       endpoint="/block/distribute-along-curve",
       required_params=("curveId", "blockNames", "method"),
       optional_params=(
           "count", "spacing", "spacingVariation",
           "distribution", "placement",
           "orientation", "keepUpright",
           "rotationMode", "scaleMode", "minScale", "maxScale",
           "seed",
       ),
       description=(
           "Distribute block instances along a curve. Methods: fill (even/random "
           "sampling over full curve length), fixedSpacing (constant spacing with "
           "optional variation), fixedCount (N copies at fixed spacing, "
           "start/center/end placement). Supports seeded randomness, frame-aligned "
           "orientation with upright guard, optional random scale and yaw. "
           "Natural-language triggers: distribute/scatter/array/place/populate "
           "blocks along curve/path/road."
       ),
   )
   ```
   Note: `optional_params` matches the MCP schema exactly (no `preview`, no `name`, no `layer`/`color`/`visible` — attribute composition is out of scope per the scope cut in Stage 3). The `description` field is populated as documentation and as a future hook if extractor inputs are later enriched; it is **not** confirmed to be on the DSPy fast path today (per §Language recognition). The load-bearing natural-language surface for internal planning is the operation key `block_distribute_along_curve` itself — chosen for high token density against the expected intent phrasing ("distribute blocks along curve," "scatter blocks along path," etc.).

5. **CATEGORIES update** — grouping metadata only, not load-bearing for routing. Add `block_distribute_along_curve` to an existing relevant tuple (candidate: a new single-entry `"block_placement"` tuple adjacent to the existing block-family entries, or fold into an existing grouping if one fits). Resolve during implementation review.

6. **Tests** — three layers (see §10 for the layered test convention):
   - **Unit (worker-thread parse/validate):** mode-validation matrix (each `method` with valid and invalid companion fields), seed echo when omitted, mode-specific field rejection.
   - **Integration (UI-thread live Rhino):** fill/even + fill/random with fixed seed = deterministic result; fixedSpacing with variation + seed = deterministic; fixedCount with start/center/end placement; `keepUpright` on near-vertical curve sample; `invalid_geometry` on zero-length curve; `empty_pool` on `blockNames = ["Missing"]`; rollback behavior via `/block/_debug/fail-next-instance` (add test seam matching `ArrayHandler`'s pattern).
   - **Agent-level (operation recognition only):** the DSPy extractor resolves natural-language intents to the operation key `block_distribute_along_curve` for phrasings like "distribute blocks along this curve," "scatter blocks along a path," "array these block definitions along the curve." This test is **recognition-only** — it does not exercise parameter population. Selection-driven phrasing ("scatter these trees along the road") is **out of scope for PR 1**: `IntentPlanner._inject_context_ids` ([intent_planner.py:584](mcp_server/src/rook/learning/intent_planner.py#L584)) injects `selected_ids` only for ID-based ops, not typed fields like `blockNames` or `curveId`, so the caller must supply explicit `curveId` and `blockNames` in the intent arguments. End-to-end selection-driven chaining is Q7 territory.

7. **Documentation:**
   - Handler header (opening comment block with contract summary)
   - MCP tool description (already in artifact 3)
   - This doc's worked-example section (already present)
   - `rook_docs/work-queue.md` entry marking the exemplar landed
   - No `CLAUDE.md` update required for this single-route exemplar; revisit if the exotic-placement family grows to 3+ routes

### Stage 6 — Historical cleanup

- Move `DistributeBlocksAlongCurve.py` to `rook_docs/script-reference/promoted/DistributeBlocksAlongCurve.py` with a header comment: `# PROMOTED 2026-04-22 to POST /block/distribute-along-curve (rhino_block_distribute_along_curve). This file is a reference artifact only — do not invoke at runtime.`
- Mark candidate-inventory entry as `promoted`.
- If a keyboard-driven Rhino command remains desirable, a thin wrapper command is possible but is explicitly **deferred and underspecified**. Any such wrapper must resolve the native server's OS-assigned port via the discovery file at `%TEMP%/rook/instance-{PID}-native.json` ([CURRENT_ARCHITECTURE.md:36-46](docs/CURRENT_ARCHITECTURE.md#L36-L46)); a hardcoded-port urllib call will not work. A simpler alternative is a Python command executed in-process that resolves the active `CRhinoDoc` and calls an internal helper shared with the handler, avoiding the HTTP path entirely. Design the wrapper when there is demonstrated user demand; do not attempt it in the first PR.

---

## Generalization Path (Explicitly Not First PR)

After the block-scoped exemplar lands and the pattern holds, plausible next routes in the exotic-placement family:

1. **`POST /array/along-curve`** — generic object-ID distribution. Input takes `objectIds: [uuid]` of arbitrary objects (Breps, meshes, points, curves, surfaces); handler duplicates + transforms via `CRhinoDoc::TransformObject(..., bCopy=true)` (same primitive as `ArrayHandler.cpp`). Substrate: direct-sdk native in `ArrayHandler.cpp`. Shares sampling code with block variant via an extracted helper.

2. **`POST /block/distribute-on-surface`** — UV-grid or Poisson-disk sample over a surface with frame orientation. Substrate: direct-sdk native; adds surface sampling primitives.

3. **`POST /block/distribute-in-region`** — 2D region fill (planar-closed-curves). Substrate: direct-sdk native; composable with 2D Poisson-disk sampler.

Extracting a `BlockPlacementHandler.cpp` becomes justified when #2 or #3 lands. At that point, migrate `HandleBlockDistributeAlongCurve` into the new file in the same PR that adds the second member.

An explicit generic "scatter primitive" abstraction is NOT justified until at least two of the above ship. Premature abstraction risks coupling; gap-analysis Rule 6 applies.

---

## Open Questions

Real remaining uncertainty. Does not block first-PR draft.

### Q1 — Sampled-position echo threshold

At what `count` does `sampledPositions` cost more context than it saves? Target: resolve during implementation review by measuring payload size at representative counts (100, 500, 1000, 5000). Proposed default threshold: 1000. Above the threshold the handler returns `"sampledPositions": null, "sampledPositionsOmittedReason": "count_exceeds_echo_limit"` so the agent can still reason about whether to re-request with a smaller count.

### Q2 — Handler-home decision for the second placement route

Confirmed first-PR home: extend `BlocksHandler.cpp`. If `/block/distribute-on-surface` is the second member, does it share enough infrastructure with along-curve to justify co-location in a new `BlockPlacementHandler.cpp`, or does surface-sampling belong adjacent to other surface ops? **Defer to second-PR scoping; do not pre-commit in this doc.**

### Q3 — `CATEGORIES` grouping for the first entry

`CATEGORIES` in `intent_runtime.py` groups routes for downstream consumption. A single-entry `"block_placement"` tuple is cleanest for future expansion but feels thin for one member. Alternative: add to existing `"blocks"` tuple (if it exists) or `"array"` tuple (semantic match but cross-namespace). **Resolve during implementation review.**

### Q4 — Source-pool ergonomics

First-PR input uses `blockNames: [string]` as the pool. Should the route ALSO accept `sourceInstanceIds: [uuid]` and derive the idef set from live selection? Pro: matches common agent flow (user selects instances, agent reads them). Con: expands input-validation surface for PR 1. **Proposal:** ship with `blockNames` only; add `sourceInstanceIds` as an additive alias in a post-soak PR per the Phase 2 alias-policy convention.

### Q5 — Candidate catalog

Deferred per §8. Revisit when a second exotic candidate emerges — then decide whether to ship `rook_docs/exotic-capability-candidates.yaml` or continue ad-hoc tracking in `work-queue.md`.

### Q6 — Separate Rhino intent-vocabulary surface

This doc assumes no separate pre-DSPy keyword table for Rhino typed routes exists today — `knowledge/gh/sparse_index.json` is explicitly GH-only, and `IntentPlanner` does not load anything comparable for the Rhino side.

If a keyword-table or intent-vocabulary file for Rhino operations does exist and this doc missed it, this assumption is wrong and Stage 5 artifact 4 should add a step for that file. Flag for verification during implementation review — grep for Rhino operation keys in any `knowledge/` or `intent*` file outside `knowledge/gh/`. If nothing surfaces, the assumption holds and the doctrine stands as written.

### Q7 — IntentPlanner: operation recognition vs. parameter satisfiability

These are two separate questions, both empirical, both tested before merge. The doc distinguishes them because the follow-up work is different.

**Q7a — Operation recognition.** Does the DSPy extractor reliably select `block_distribute_along_curve` from phrasing like "distribute blocks along this curve," "scatter blocks along a path," "populate curve with these blocks"?

- Procedure: ship the `_routes` entry and MCP tool in a draft; run a ~10-prompt smoke test against the DSPy extractor.
- If hit rate ≥80% on clearly-matching phrasing: operation-key quality alone is sufficient; merge as planned.
- If hit rate is low: follow-up in `IntentPlanner` — enrich extractor inputs with route descriptions, add regex extraction for high-value domain verbs ("scatter," "distribute," "populate"), or introduce a dedicated Rhino keyword table. Scope as a tight sibling PR, not folded into the exemplar.

**Q7b — Parameter satisfiability.** Even when recognition works, can the planner populate the route's typed fields (`curveId`, `blockNames`, `method`, etc.) from natural-language context?

- Current `_inject_context_ids` at [intent_planner.py:584](mcp_server/src/rook/learning/intent_planner.py#L584) auto-injects `selected_ids` for a closed set of ID-based ops. It does **not** auto-inject `blockNames`, `curveId`, or any other typed field not in that set.
- For PR 1, agent flow is: caller supplies `curveId` and `blockNames` explicitly in the intent arguments, OR calls the MCP tool directly with those fields. End-to-end "scatter these trees along the road" from pure selection context does **not** work today.
- If demand emerges for selection-driven invocation, the follow-up is in the planner's context-injection layer — teach it to pull `curveId` from `selected_ids` when exactly one selected object is a curve, and teach it to resolve `blockNames` from selected instances' idefs. Scope as a separate PR after measuring demand.

The two questions have different diagnostic surfaces. Test them independently. Do not conflate "the planner picks the right operation" with "the planner can run the operation end-to-end from a selection."

---

## Roadmap

### Phase A (now) — Land the doctrine

- This document (promotion doctrine + first-exemplar plan) reviewed by Codex.
- Resolve Codex findings in a revision pass; re-check against `2026-04-22-exotic-capability-promotion-design.md` for consistency.
- Mark the earlier design doc as superseded by this plan for implementation purposes; design doc remains as design-history record.

### Phase B — Ship the first exemplar

One PR containing all Stage 5 artifacts for `POST /block/distribute-along-curve`. Per established scoping rhythm (scoping feedback memory): written scope pass in chat before code → Codex review → implement.

### Phase C — Build the family, not a zoo

After the exemplar ships and is used:

- Queue ≤ 3 neighboring candidates (`/array/along-curve`, `/block/distribute-on-surface`, or similar) against the same pipeline.
- Re-evaluate doctrine after candidate #3; adjust this doc if the pattern needs refinement.
- Do not accept a flood of script promotions before the pattern is proven across 3 exemplars.

### Phase D — Candidate catalog (conditional)

Only if candidate volume justifies. Defer until Phase C surfaces 2+ new candidates.

---

## Net Decision

Rook does **not** ship a general script library as a parallel runtime substrate. That shape reproduces the command-string era in a new form.

Rook **does**:

1. Accept script-originated capabilities as intake for typed-route promotion.
2. Apply the classification rule (primitive / skill / reference) before any implementation.
3. Promote reusable primitives to typed routes with direct-sdk native substrate by default.
4. Enforce one load-bearing implementation per algorithm after promotion; scripts become frozen reference artifacts or disappear.
5. Require all three discovery surfaces (CapabilityRouter + MCP tool + prose) for any promoted route.

The agent moment does not change the load-bearing contract. Semantic reasoning happens in the agent; execution happens through typed routes. What the agent moment does change is the size of the worth-promoting set — because compiling fuzzy intent into exact arguments is now cheap.

First exemplar: `POST /block/distribute-along-curve` from `DistributeBlocksAlongCurve.py`. Block-scoped, direct-sdk native, atomic with rollback, seeded randomness, plural-creator response. One PR, all artifacts. Reviewed by Codex before build.

This plan is binding doctrine for all future script-originated capability work, subject to revision after Phase C review.
