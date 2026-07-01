# Capability Index + Progressive Tool Disclosure — Phase One Design

- **Status:** Approved (architecture + review clear); data model revised 2026-06-30 to a **facet over the
  existing LM2A inventory** (do not duplicate `CapabilityRecord`). Ready for implementation plan.
- **Date:** 2026-06-30
- **Builds on:** the MCP Tool Exposure Profile campaign (spec
  `docs/superpowers/specs/2026-06-29-mcp-tool-exposure-profile-design.md`), **merged to `origin/main` via
  PR #382**; and the **LM2A capability inventory** (`rook.agent.capability_record` /
  `rook.agent.capability_inventory`). This spec **absorbs and extends** the profile work and **reuses
  (read-only) — never modifies —** the LM2A model.
- **Commit base:** Base on **`origin/main`**, which contains the *wired* profile campaign (PR #382:
  `filter_tools` / `tool_blocked` / `PUBLIC_*` present and integrated) and the LM2A capability modules.
  All `server.py` line anchors in this spec are verified against `origin/main`. Do the work in a
  dedicated branch/worktree off `origin/main`; nothing is committed on `main` directly.
- **Campaign:** Capability Index — the **public-MCP facet** of the LM2A capability inventory, delivered
  through the MCP surface.

---

## 1. Problem

The profile campaign correctly separated two axes — `lean` (context reduction, list-only) and
`readonly` (safety, enforced wall) — and built both well. But it deliberately deferred a third concern
(its own §9/§10): **dynamic, mid-session discovery of the full tool surface from a context-limited
client.** That deferral leaves a concrete, unacceptable failure standing:

> A `lean` Codex session is asked to "preview a VisionDirector camera move." `rhino_director_*`,
> `rc_*`, `rookbim_*`, `scene_*`, video — **none are in the lean floor**, and lean's escape hatch
> (`rhino_execute_intent` / `gh_execute_intent`) routes only to *geometry* typed routes. It will never
> reach `rhino_director_preview_motion`. The capability is neither **visible** nor **reachable**.

No static profile fixes this, because the need is **dynamic**:

- **`full`** re-introduces the ~90k-token firehose the campaign exists to avoid.
- **Domain slices** (the profile spec's reserved `domain × posture`) are selected by a **startup env
  var**; a running Codex session cannot switch from `lean` to `director` when the task surfaces
  mid-conversation. Static-per-session cannot serve dynamic-mid-session.

The only mechanism that breaks the ceiling is a **progressive discovery surface**: browse → search →
read-schema → call, server-side, client-agnostic, no restart. This spec builds that surface as the
**public-MCP facet of the existing LM2A capability inventory** — one canonical identity (the tool name)
with two facets: the agent-surface facet LM2A already models, and the public-MCP facet built here.

### Framing (non-negotiable)

This is **not** "make lean a little nicer." It **replaces static lean-as-ceiling with
progressive-disclosure-as-access-layer.** The existing convenience tools stay for ergonomics; the
*worldview* — "these N tools are all the client can use" — is what we discard.

---

## 2. Relationship to prior work

**Profile campaign (PR #382) — kept, unchanged:**

- `ROOK_MCP_TOOL_PROFILE = full | lean | readonly`, the pure `resolve_profile(env)`, hard-fail on
  invalid, absent ⇒ `full`.
- The **asymmetry invariant**: `lean` is list-only; `readonly` is an enforced wall.
- **`readonly` enforcement remains the audited `PUBLIC_READONLY_TOOL_NAMES` allowlist** via
  `tool_blocked()`. The facet exposes a `readonly_safe` *descriptor*, but the allowlist — not facet
  metadata — stays the enforcement authority (§8, invariant 1).
- Config-generation seams and the `tool_profile_blocked` envelope.

**LM2A capability inventory (`rook.agent.capability_record` / `capability_inventory`) — reused read-only,
never modified:**

- The existing frozen `CapabilityRecord` (`name, visibility, tiers, groups, dispatch_path, has_schema,
  risk, no_argument, mcp_only`) is the **agent-surface facet**. It is deliberately **stdlib-only** and
  decoupled; this spec **must not** add fields to it, import server-side concerns into it, or otherwise
  entangle it. (Enforced by the existing `test_capability_record_is_stdlib_only`.)
- This spec adds a **separate public-MCP facet** (`McpCapabilityRecord`, §4.2) linked to the agent facet
  **by canonical tool name**, and consumes the existing `CapabilityInventory` **read-only** for the
  agent-side link.

**Changed by this spec:**

- `lean` membership grows **18 → 22**; `readonly` **145 → 149**; `full` live `list_tools()` **429 → 433**
  (the four `rook_tools_*`; base counts are `origin/main`'s, which include `openrouter_refresh_catalog`
  in `full` + `lean`). Profile snapshot counts are **updated, not preserved**.
- `list_tools()` is refactored to project over an **unprofiled** `_all_live_tools()` source (§4.1) — a
  behavior-preserving refactor of the `filter_tools(live_tools, …)` at
  [`server.py:13373`](../../../mcp_server/src/rook/server.py).
- The dispatch path gains a **meta-tool interception point in `call_tool` ahead of
  `_call_tool_dispatch`'s recording tail** (§6). Surgical, **not** handler migration.

---

## 3. Scope

**In:**

- A new **public-MCP facet** `McpCapabilityRecord` + `CapabilityIndex` built by enriching the existing
  live tool schemas with metadata (`TOOL_GROUPS`, `TOOL_CATEGORIES`, `PUBLIC_READONLY_TOOL_NAMES`,
  dispatch-case set) **and linking each record, by name, to the LM2A `CapabilityRecord` (read-only)**.
- Four discovery tools: `rook_tools_ls`, `rook_tools_search`, `rook_tools_read`, `rook_tools_call`.
- `lean` becomes a discovery **floor**, not a ceiling; discovery tools exposed in **all three** profiles,
  scoped appropriately (§5, §7).
- `rook_tools_call` dispatch routed through the **same policy path** as native calls, preserving the
  readonly wall and the no-side-effect-on-block contract (§6).
- A minimal, dependency-free argument validator (§6.1).
- Tests proving the severe acceptance criterion (§9).

**Out (named non-goals):**

- **Modifying, extending, or entangling the LM2A model.** No new fields on
  `rook.agent.capability_record.CapabilityRecord`; no server-side or profile imports into it; no changes
  to `capability_inventory`. The MCP facet only **reads** the inventory. *(This is a hard mandate: do not
  endanger the LM campaign.)*
- Unifying the agent + MCP facets into a single canonical registry. That is future LM2 work; this phase
  keeps two linked facets.
- Moving any tool family / handler out of `server.py`.
- Replacing the audited `readonly` wall with inferred metadata. Enforcement stays the allowlist.
- LM Planner `execution_ref` binding against the index.
- Embeddings / semantic search. Search is **lexical**.
- **Adding a new Python dependency** (e.g. `jsonschema`). Validation is in-house and minimal (§6.1).
- Generating MCP tool definitions from a new canonical format. The facet **wraps** existing `Tool(...)`
  defs by reference.
- **Pruning or retuning the lean floor.** Lean stays additive (18 kept + 4 added).

---

## 4. The public-MCP facet

### 4.1 Module, dependency rule, and reuse of the LM2A inventory

New module **`mcp_server/src/rook/capability_index.py`**, holding `McpCapabilityRecord`,
`CapabilityIndex`, a pure `build_index(...)`, the query helpers (`ls`, `search`, `read`), and the minimal
validator (§6.1).

- **One-way dependency:** `capability_index.py` **must not import `server.py`**. It imports only:
  - the **type** `rook.agent.capability_record.CapabilityRecord` (stdlib-only — safe, for the
    `agent_record` link and type hints); and
  - leaf data modules for enrichment (`mcp_tool_profiles` for `PUBLIC_READONLY_TOOL_NAMES`,
    `agent.tool_groups` for `TOOL_GROUPS`, `context` for domain hints).
  It **does not** import `capability_inventory` (which pulls agent dispatch internals) — the agent
  records are **injected** (below), keeping this module light and independently testable.
- **Reuse, do not duplicate (LM2A mandate).** The agent-surface facet already exists. `build_index`
  accepts the agent records as data and links them by name; it never rebuilds or mutates them:

  ```
  build_index(
      tools: list[Tool],                              # the UNPROFILED public surface (§ P1a)
      agent_records: Mapping[str, CapabilityRecord],  # from LM2A, injected read-only ({} if unavailable)
      dispatchable_names: frozenset[str],             # public call_tool dispatch-case labels (§4.2)
  ) -> CapabilityIndex
  ```

- **Wiring (server startup, one-way):** `server.py` (or a small wiring helper it owns) calls
  `capability_inventory.build_inventory(collect_live_sources(), catalog)` **read-only**, passes
  `{r.name: r for r in inv.records}` as `agent_records`, computes `dispatchable_names` (§4.2), and calls
  `build_index(_all_live_tools(), agent_records, dispatchable_names)`. If the LM2A build raises or is
  unavailable, `agent_records = {}` and every `agent_record` is `None` — discovery still works; only the
  agent-side descriptors are absent. **A failure in the diagnostic LM2A path must never break MCP
  discovery.**

- **Unprofiled source (P1a).** `list_tools()` returns `filter_tools(live_tools, resolve_profile(...))`
  ([`server.py:13373`](../../../mcp_server/src/rook/server.py)); building the index from it would, under
  `lean`, yield an index of only the 22-tool floor. Factor an unprofiled **`_all_live_tools()`** (static
  `Tool(...)` set with the deprecated-interactive live gate at
  [`server.py:13365`](../../../mcp_server/src/rook/server.py)–:13371 applied, **no** profile filter);
  build the index from it; `list_tools()` becomes a thin projection `filter_tools(_all_live_tools(),
  profile)`.

### 4.2 `McpCapabilityRecord` (public-MCP facet, frozen)

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from rook.agent.capability_record import CapabilityRecord   # LM2A agent-surface facet (read-only)

@dataclass(frozen=True)
class McpCapabilityRecord:
    name: str                              # canonical tool name — the SHARED identity across facets
    path: str                              # "/{domain}/{group?}/{name}" — filesystem address for ls
    domain: str                            # rhino/gh/rc/director/vision/video/bim/scene/knowledge/session/meta
    groups: tuple[str, ...]                # from TOOL_GROUPS (may be empty)
    summary: str                           # first sentence of the description
    description: str                       # full Tool.description
    readonly_safe: bool                    # name in PUBLIC_READONLY_TOOL_NAMES (audited public truth)
    mcp_dispatchable: bool                 # has a public call_tool / _call_tool_dispatch path
    input_schema: Mapping[str, Any]        # reference to the live Tool.inputSchema (no new format)
    agent_record: CapabilityRecord | None  # the LM2A agent-surface facet, linked by name (None if absent)
```

**Agent-side descriptors are read from `agent_record` with an explicit source — never re-derived and
never overloaded onto MCP fields:**

```
agent_dispatchable = record.agent_record is not None and record.agent_record.dispatch_path is not None
agent_visibility   = record.agent_record.visibility if record.agent_record else None
agent_mcp_only     = record.agent_record.mcp_only   if record.agent_record else None
```

**`mcp_only` (LM2A) ≠ `mcp_dispatchable` (this facet) — do not conflate.** LM2A `mcp_only` means "visible
*only on the MCP surface relative to the internal agent/HTTP surface*" — a visibility fact about the
agent world. `mcp_dispatchable` means "callable through the **public** MCP `call_tool` path." They are
different axes. `mcp_dispatchable` is computed by this facet from `dispatchable_names`; `mcp_only` is read
from `agent_record` only for display. The index must never derive one from the other.

**`mcp_dispatchable` determination.** `dispatchable_names = {literal case "<name>": labels handled by
_call_tool_dispatch ([`server.py:13894`](../../../mcp_server/src/rook/server.py)+)} ∪ {the four
intercepted rook_tools_* meta-tools}`. The meta-tools are dispatchable via the `call_tool` interception
(§6), **not** via a dispatcher case, so they must be unioned in explicitly — otherwise they'd be
advertised yet marked non-dispatchable and hidden from their own discovery surface. Computed server-side
(AST/source scan for the case labels, plus the known meta-tool names) and injected;
`mcp_dispatchable = name in dispatchable_names`. The meta-tools therefore show `mcp_dispatchable=True` and
may appear in `ls`/`search`/`read`; the **recursion guard** (§6) — not a false `mcp_dispatchable` — is
what stops `rook_tools_call` from targeting a `rook_tools_*` tool. For the native surface this keeps
**visible ⟹ mcp_dispatchable** a *checked* fact: a tool advertised in `_all_live_tools()` but lacking a
dispatch case is `mcp_dispatchable=False` and hidden from discovery (§5.2), carrying the LM1
"visible-implies-dispatchable" invariant onto the MCP transport.

**Enrichment sources:** `domain` from name-prefix reconciled with `TOOL_CATEGORIES`/`TOOL_GROUPS`;
`groups` from `TOOL_GROUPS`; `summary` = first sentence of `Tool.description`; `readonly_safe` = `name ∈
PUBLIC_READONLY_TOOL_NAMES`; `input_schema` = the live `Tool.inputSchema` by reference.

---

## 5. The discovery surface (four tools)

- **`rook_tools_ls(path="/", depth=1)`** — browse the tool filesystem. Returns compact entries
  (`name, path, domain, groups, readonly_safe, summary`) and child paths. **No schemas.**
- **`rook_tools_search(query, domain?, readonly_safe?, limit=10)`** — **lexical** ranking over
  name + summary + domain + groups (no embeddings). Optional filters by `domain` and `readonly_safe`.
- **`rook_tools_read(name)`** — the full record for one tool: `input_schema`, full `description`,
  `domain`, `groups`, `readonly_safe`, `mcp_dispatchable`, and the agent-side descriptors
  (`agent_dispatchable`, `agent_visibility`, `agent_mcp_only`) when `agent_record` is present. (This
  **is** "describe.")
- **`rook_tools_call(name, arguments)`** — validate, then dispatch the target through the shared policy
  path (§6).

### 5.1 Profile exposure

All four tools are exposed in **full**, **lean**, and **readonly** — the facet is a canonical server
surface, not a lean hack. Scoping differs by profile:

- **full / lean:** `ls`/`search`/`read` surface the whole index (every `mcp_dispatchable` record).
- **readonly:** `ls`/`search`/`read` are **profile-scoped** — they surface `readonly_safe` capabilities
  by default, so a readonly client's "what can I do?" answer matches what it may actually run. (A future
  `include_blocked=true` browsing mode is reserved, not built.)
- **`rook_tools_call` exists in all three**, including readonly — because it does **not** bypass the
  wall. Under `readonly`, a `readonly_safe` target runs; a mutator target is blocked by the re-entered
  wall (§6). That is why `rook_tools_call` is an *allowed* readonly tool rather than a sentinel.

### 5.2 Visible ⇒ MCP-dispatchable

`ls`/`search` never surface a record with `mcp_dispatchable == false`, and `rook_tools_call` refuses one
with a clear error. This carries the LM1 "visible-implies-dispatchable" invariant onto the MCP surface,
disambiguated to the MCP transport (§4.2) and **never** conflated with LM2A `mcp_only`.

---

## 6. Dispatch safety model (the load-bearing section)

Two facts about the existing code drive the entire design:

1. The **universal recording path** — `get_phase_tracker().record_call(name)`
   ([`server.py:20850`](../../../mcp_server/src/rook/server.py)) and `_record_observation(_tool_name, …)`
   (:20863) — lives at the **tail of `_call_tool_dispatch`** (defined at :13894), keyed by the dispatched
   name.
2. The readonly **wall** `tool_blocked(name, profile)` lives **early in `call_tool`** (:20929), *before*
   `call_tool` ever invokes `_call_tool_dispatch`.

**(a) Meta-tools are intercepted in `call_tool`, after the wall and before `_call_tool_dispatch`.** If
`rook_tools_*` were ordinary `match` cases inside `_call_tool_dispatch`, the tail at :20850/:20863 would
record the *meta* tool (`rook_tools_call`) as an observation, and a forwarded target would record
*again* — a meta self-record plus a double-record. Interception before the dispatcher avoids both:

- `rook_tools_ls` / `rook_tools_search` / `rook_tools_read` are answered from the index inside
  `call_tool` and **never dispatched** — no observation, no phase tick.
- `rook_tools_call` is answered in `call_tool` too: after its guards (below) it **re-enters the same
  post-wall policy path for the target** — concretely `return await call_tool(target_name, target_args)`,
  or an equivalent `_invoke_tool_with_policy(target, args, origin="meta")` helper factored out of
  `call_tool`. The target — and only the target — reaches `_call_tool_dispatch`'s tail and is recorded
  **once, under its real name**.

**(b) A blocked target records nothing — for free.** Because the wall (:20929) precedes
`_call_tool_dispatch`, a readonly-blocked target returns the `profile_blocked_envelope` *before* the
recording tail. So `rook_tools_call("rhino_director_preview_motion")` under `readonly` blocks with **no
target observation and no phase tracking**. The meta call itself also records nothing, per (a).

**`rook_tools_call` guards, in this order — the target readonly wall fires *before* dispatchability and
validation, so a blocked target always returns the exact `tool_profile_blocked` envelope (identical to a
native call), never a validation error and never leaking schema behavior:**

1. **No meta-recursion** — reject any target in `{rook_tools_ls, rook_tools_search, rook_tools_read,
   rook_tools_call}`.
2. **Target readonly wall** — `if tool_blocked(target, profile): return profile_blocked_envelope(target,
   profile)`. This mirrors native `call_tool`, where the wall (:20929) is the first thing to fire. (The
   subsequent re-entry re-applies the wall; the check is idempotent.)
3. **MCP-dispatchable** — reject targets with `mcp_dispatchable == false` (§4.2).
4. **Argument validation** — §6.1.

**Forbidden:** `rook_tools_call` must **not** call `_call_tool_dispatch(target, …)` directly — that
skips the wall (:20929) and the targeting/document-context logic in `call_tool`, silently bypassing
`readonly`. It re-enters through `call_tool` / the shared policy helper, never the raw dispatcher.

**Origin tagging.** To keep meta-dispatched calls distinguishable in telemetry without threading a
parameter through the ~7k-line dispatcher, set a `ContextVar` (`_dispatch_origin = "meta"`) around the
target re-entry; `_record_observation` reads it (default `"native"`). Lightweight; no signature churn.

### 6.1 Argument validation (phase-one strategy)

`jsonschema` is **not** a current dependency ([`pyproject.toml`](../../../mcp_server/pyproject.toml)),
and this phase **adds no new dependency**. `rook_tools_call` validates `arguments` against the target's
`input_schema` with a **minimal in-house validator** enforcing a **deliberately small subset of common
Rook schema keywords**: `required`, `type` (JSON primitive types), `enum`, numeric `minimum`/`maximum`,
and array `items` type basics. Other keywords Rook schemas do use — `minItems` / `maxItems` /
`minLength` / `additionalProperties` / `oneOf` and the like — are **not** pre-validated and fall through
to the target handler, which remains the real backstop (handlers already validate today for native
calls). A validation failure returns a **field-level** error and does **not** dispatch. Adopting
`jsonschema` is a deliberate, separately-decided future step if schema drift makes the in-house
validator insufficient.

---

## 7. Profile integration

### 7.1 Lean floor (18 kept + 4 added = 22)

Lean keeps its existing 18 unchanged and adds the four `rook_tools_*`. **No pruning** (non-goal, §3).
Semantics, stated so reviewers don't relapse into the old worldview:

- The 18 are **always-visible boot/convenience tools** — connection, targeting, snapshot, knowledge,
  provider-catalog refresh (`openrouter_refresh_catalog`).
- The four `rook_tools_*` are the **capability access layer**.
- Lean is no longer "all Codex can use." It is "the boot tools Codex sees **before it browses the
  index**."

`gh_edit`, `rhino_execute_intent`, `gh_execute_intent` stay in the floor for now: already reviewed in the
profile campaign, common enough to justify native schema visibility, and more ergonomic than
`rook_tools_call` when the model already holds the schema. Removing them is deferred floor-tuning.

### 7.2 Membership and counts

- `PUBLIC_LEAN_TOOL_NAMES`: 18 → **22** (+ four `rook_tools_*`).
- `PUBLIC_READONLY_TOOL_NAMES`: 145 → **149** (+ four `rook_tools_*`; the three readers are pure reads,
  `rook_tools_call` is wall-protected per §6).
- Live `full` `list_tools()`: 429 → **433**.
- Profile snapshot tests are **updated** to these counts; counts are assertions of current truth, not
  frozen constraints (the membership invariants in §9 are the durable assertions).

### 7.3 Asymmetry preserved

`lean` remains list-only (no wall); `readonly` remains an enforced wall. The discovery surface composes
with both: in `lean`, `rook_tools_call` reaches anything (no wall); in `readonly`, it reaches only what
the wall permits.

---

## 8. Hard invariants

1. **Enforcement authority unchanged.** `readonly` blocking is `tool_blocked()` against the audited
   `PUBLIC_READONLY_TOOL_NAMES`. `readonly_safe` **does not enforce call permission** — it may *scope
   readonly discovery* (§5.1), but only `tool_blocked()` gates whether a call executes.
2. **No new bypass.** `rook_tools_call` re-enters through `call_tool` / the shared policy helper, never
   `_call_tool_dispatch`. The wall fires on the target identically to a native call.
3. **Visible ⇒ MCP-dispatchable.** Discovery hides `mcp_dispatchable == false`; `rook_tools_call`
   refuses it. `mcp_dispatchable` is this facet's field (public `call_tool` path) and is **never** the
   same as LM2A `mcp_only`.
4. **No meta-recursion.** `rook_tools_call` refuses `rook_tools_*` targets.
5. **Index wraps, never replaces.** `input_schema` is the live `Tool.inputSchema` by reference; the
   `Tool(...)` defs remain the source of truth for schemas.
6. **One-way dependency.** `capability_index.py` does not import `server.py`; it imports only the
   `CapabilityRecord` type and leaf data modules.
7. **Index source is unprofiled.** The index is built from `_all_live_tools()`; `list_tools()` is a
   profile projection over the same source. **The index never shrinks with the active profile**; readonly
   *query results* are scoped to `readonly_safe` by default (§5.1).
8. **Meta-tools never reach the recording tail.** `rook_tools_*` are intercepted in `call_tool` before
   `_call_tool_dispatch`; only forwarded **targets** are observed — once, under their real name. A
   blocked target is observed not at all.
9. **LM2A is untouched.** This spec does not modify or extend `rook.agent.capability_record` /
   `capability_inventory`. The MCP facet reads the inventory **read-only**, links by name, tolerates
   `agent_record == None`, and never lets an LM2A build failure break MCP discovery.

---

## 9. Testing contract

**Severe acceptance criterion (the spine):**

1. **lean reach:** with `ROOK_MCP_TOOL_PROFILE=lean`, `rook_tools_search("director preview")` surfaces
   `rhino_director_preview_motion`; `rook_tools_read` returns its schema; `rook_tools_call` dispatches
   it successfully — **no MCP restart**.
2. **readonly block (wall before validation):** with `readonly`,
   `rook_tools_call("rhino_director_preview_motion", …)` returns the `tool_profile_blocked` envelope —
   `preview_motion` is not on the audited allowlist (default-deny), proving discovery is **not** a
   bypass. **The same call with deliberately invalid `arguments` still returns `tool_profile_blocked`**
   (the target wall fires before schema validation — §6), never a validation error.
3. **full unchanged:** with `full`, native direct tool behavior and the `list_tools()` projection are
   unchanged (modulo the +4 meta-tools).

**Unprofiled-source / membership invariants (not a frozen count):**

4. **Index is not the lean projection:** under `lean`, the index contains `rhino_director_preview_motion`
   (built from `_all_live_tools()`), even though `list_tools()` under `lean` does not advertise it.
5. lean contains all original 18 **and** the four `rook_tools_*`; `rhino_director_preview_motion` is
   **not** directly advertised in lean's `list_tools()` but **is** discoverable/readable/callable via
   `rook_tools_*`.

**Facet / LM2A-reuse invariants:**

6. **Agent link by name:** an `McpCapabilityRecord` for a tool present in the injected agent inventory
   has `agent_record` set with a matching `name`; a tool absent from it has `agent_record is None`.
7. **`mcp_only` ≠ `mcp_dispatchable`:** `mcp_dispatchable` is computed only from `dispatchable_names`;
   assert the index never sets it from `agent_record.mcp_only` (construct a record with
   `agent_mcp_only=True` but `mcp_dispatchable=False`, and the reverse, and assert both round-trip).
8. **LM2A untouched:** the existing `test_capability_record_is_stdlib_only` still passes;
   `rook.agent.capability_record.CapabilityRecord` has no new fields; building the index with an empty
   `agent_records` (LM2A "unavailable") still yields a working index with all `agent_record is None`.

**Recording / safety / structure:**

9. **No record on block:** a `readonly`-blocked `rook_tools_call` target produces **no**
   `_record_observation` entry **and no** `get_phase_tracker().record_call` tick (assert both).
10. **No meta self/double record:** a successful `rook_tools_call` records **exactly one** observation,
    under the **target** name (origin `meta`), and **none** under `rook_tools_call`;
    `rook_tools_ls/search/read` record none.
11. **No raw-dispatcher bypass:** `rook_tools_call` routes through `call_tool`/the policy helper, not
    `_call_tool_dispatch` (assert a mutator target blocks under `readonly`).
12. **Recursion guard:** `rook_tools_call("rook_tools_ls")` (and the other three) is rejected.
13. **Validator coverage:** `rook_tools_call` rejects missing `required`, wrong `type`, out-of-`enum`,
    and out-of-`min/max` numeric args with field-level errors and does **not** dispatch; unsupported
    keywords pass through to the handler.
14. **Visible ⇒ MCP-dispatchable:** no `mcp_dispatchable == false` record appears in `ls`/`search`;
    `rook_tools_call` on one is refused.
15. **Readonly scoping:** under `readonly`, `ls`/`search`/`read` surface `readonly_safe` records by
    default.
16. **Index drift oracle:** every record's `readonly_safe` agrees with `PUBLIC_READONLY_TOOL_NAMES`; the
    index covers 100% of `_all_live_tools()`.

---

## 10. Out of scope (YAGNI — explicitly deferred)

- **Any modification to the LM2A model.** No new fields on `CapabilityRecord`; no changes to
  `capability_inventory`; no unification of the agent + MCP facets.
- Handler / tool-family extraction out of `server.py` (the facet *enables* it; the next spec exercises
  it, VisionDirector as the likely pilot).
- `readonly` enforcement migrating from allowlist to inferred metadata.
- LM2 Planner `execution_ref` binding against the index.
- Embeddings / semantic search; any new Python dependency (`jsonschema` included).
- `tools.listChanged`-driven native dynamic loading (the dispatcher is the client-agnostic path and
  ships first).
- Lean floor pruning.

---

## 11. Rollout and LM2 relationship

Build the vertical slice: `McpCapabilityRecord` + `CapabilityIndex` + `build_index` over
`_all_live_tools()` (with the injected LM2A `agent_records` and `dispatchable_names`), the four
`rook_tools_*` tools, the `call_tool` meta-interception + target re-entry, the in-house validator, the
profile-membership updates, and the §9 tests. `full` stays the absent-default; `readonly` stays enforced
by the audited allowlist.

**This index is the public-MCP facet of the existing LM2A capability inventory, linked by canonical tool
name.** It reuses the agent-surface facet read-only and adds the public-MCP facet the MCP surface needs.
**Future LM2 work may unify these facets into a single registry** — and may later feed the Planner's
`execution_ref` binding, generate the agent catalog, and anchor the strangler-fig decomposition of
`server.py`. Those are **named successor specs**, not this one, and none of them are permitted to
regress or entangle the LM2A model. This spec's job is to end the lean-as-ceiling failure with a vertical
slice through the real architecture — reusing what LM2A already built, duplicating nothing.

---

## 12. Successor roadmap

Phase One ships the access layer. The next work should make that layer boring, observable, and useful
in real Codex sessions before Rook commits to deeper registry unification. The sequencing matters:
validate the progressive-disclosure contract in use, then widen the architecture.

### 12.1 MCP progressive disclosure V1.1

The next spec should be a small hardening and ergonomics pass, not a grand registry rewrite.

Scope:

- Document the client pattern explicitly: `rook_tools_search` -> `rook_tools_read` ->
  `rook_tools_call`, with examples for Codex-style clients.
- Add or update release/local-smoke guidance for all three profiles: `lean`, `readonly`, and `full`.
- Make config expectations explicit: Codex gets `lean`; Claude/panel configs remain full by omission
  unless a later spec intentionally changes that default.
- Improve lexical discovery with aliases and workflow terms such as "vision director", "camera motion",
  "grasshopper edit", "bake", "road", "mesh export", and "BIM query". This remains dependency-free;
  embeddings are still deferred.
- Add lightweight telemetry for search/read/call usage: misses, validation failures, readonly blocks,
  and target tools reached through `rook_tools_call`.
- Harden the in-house validator only where real schemas or smoke tests show failures. Do not adopt full
  JSON Schema support unless evidence shows the minimal validator is the wrong long-term seam.

Non-goals:

- Do not prune the lean floor yet. The current direct 18 convenience tools stay until telemetry shows
  whether they are redundant.
- Do not move readonly enforcement into metadata. `PUBLIC_READONLY_TOOL_NAMES` remains the authority.
- Do not unify the MCP facet and LM2A facet in this phase.

### 12.2 Capability packs / tools-as-filesystem

After V1.1, Rook should consider domain context packs backed by the same public-MCP facet:

```text
/tools/index
/tools/rhino
/tools/gh
/tools/director
/tools/bim
/tools/scene
```

Each pack should be compact: tool names, domains, summaries, common workflow phrases, and links back to
`rook_tools_read` for schemas. These packs are for model context and browsing only. They must not become
an authorization source, and they must preserve the invariant:

```text
discoverable metadata != callable authority
```

Readonly clients may receive readonly-scoped packs by default; any future "show blocked capabilities"
mode must be explicit and must not change `rook_tools_call` behavior.

### 12.3 Server.py strangler pilot

Once the access layer has real usage evidence, pick one bounded tool family and extract it out of
`server.py`. VisionDirector is the likely pilot because it was the motivating lean-failure case and has
clear domain boundaries. The pilot should move only that family's definitions, metadata, handlers, and
tests into a per-domain module that registers into the public-MCP facet. This proves the strangler seam
on real code without turning Phase Two into a full `server.py` rewrite.

### 12.4 LM planner binding

Only after the MCP facet is stable should LM2 bind `execution_ref` or allowed actions to stable
capability identity. That convergence needs its own spec. The binding may use the shared canonical tool
name and public MCP dispatchability, but it must not let descriptive registry metadata become
enforcement. Planner authority, readonly authority, and runtime call authority remain explicit contracts.
