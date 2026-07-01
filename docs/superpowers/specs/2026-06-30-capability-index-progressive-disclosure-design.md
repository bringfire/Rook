# Capability Index + Progressive Tool Disclosure — Phase One Design

- **Status:** Approved (review clear after wording fixes) — ready for implementation plan
- **Date:** 2026-06-30
- **Builds on:** the MCP Tool Exposure Profile campaign (spec
  `docs/superpowers/specs/2026-06-29-mcp-tool-exposure-profile-design.md`), **merged to `origin/main` via
  PR #382**. This spec **absorbs and extends** that work; it does not replace it.
- **Commit base:** Base on **`origin/main`**, which contains the *wired* profile campaign (PR #382:
  `filter_tools` / `tool_blocked` / `PUBLIC_*` present and integrated). All `server.py` line anchors in
  this spec are verified against `origin/main`. Do the work in a dedicated branch/worktree off
  `origin/main`; nothing is committed on `main` directly. *(Transient local-checkout sync state lives in
  the PR/process notes, not in this spec.)*
- **Campaign:** Capability Index — the first vertical slice of the LM2 Capability Registry, delivered
  through the MCP surface.

---

## 1. Problem

The profile campaign correctly separated two axes — `lean` (context reduction, list-only) and
`readonly` (safety, enforced wall) — and built both well. But it deliberately deferred a third concern
(its own §9/§10): **dynamic, mid-session discovery of the full tool surface from a context-limited
client.** That deferral leaves a concrete, unacceptable failure standing:

> A `lean` Codex session is asked to "preview a VisionDirector camera move." `rhino_director_*`,
> `rc_*`, `rookbim_*`, `scene_*`, video — **none are in the lean 17**, and lean's escape hatch
> (`rhino_execute_intent` / `gh_execute_intent`) routes only to *geometry* typed routes. It will never
> reach `rhino_director_preview_motion`. The capability is neither **visible** nor **reachable**.

No static profile fixes this, because the need is **dynamic**:

- **`full`** re-introduces the ~90k-token firehose the campaign exists to avoid.
- **Domain slices** (the profile spec's reserved `domain × posture`) are selected by a **startup env
  var**; a running Codex session cannot switch from `lean` to `director` when the task surfaces
  mid-conversation. Static-per-session cannot serve dynamic-mid-session.

The only mechanism that breaks the ceiling is a **progressive discovery surface**: browse → search →
read-schema → call, server-side, client-agnostic, no restart. This spec builds that surface, backed by
a **Capability Index** that is explicitly the first slice of the LM2 Capability Registry.

### Framing (non-negotiable)

This is **not** "make lean a little nicer." It **replaces static lean-as-ceiling with
progressive-disclosure-as-access-layer.** The existing convenience tools stay for ergonomics; the
*worldview* — "these N tools are all the client can use" — is what we discard.

---

## 2. Relationship to the profile campaign

**Kept, unchanged:**

- `ROOK_MCP_TOOL_PROFILE = full | lean | readonly`, the pure `resolve_profile(env)`, hard-fail on
  invalid, absent ⇒ `full`.
- The **asymmetry invariant** (§3 of the profile spec): `lean` is list-only; `readonly` is an enforced
  wall.
- **`readonly` enforcement remains the audited `PUBLIC_READONLY_TOOL_NAMES` allowlist** via
  `tool_blocked()`. The Capability Index exposes a `readonly_safe` *description*, but the allowlist —
  not index metadata — stays the enforcement authority for this phase (see §8, invariant 1).
- The config-generation seams (`doctor.py`, `install.ps1`) and the rejection-envelope contract
  (`tool_profile_blocked`).

**Changed by this spec:**

- `lean` membership grows from 17 → 21 (adds the four `rook_tools_*` tools; §7).
- `readonly` membership grows from 145 → 149 (adds the four `rook_tools_*` tools; §7).
- `full` live `list_tools()` grows 427 → 431. The profile spec's pinned-count snapshot tests are
  **updated, not preserved** — stale counts are not a design constraint.
- `list_tools()` is refactored to project over an **unprofiled** `_all_live_tools()` source so the Index
  can be built from the full surface (§4.1) — a behavior-preserving refactor of the existing
  `filter_tools(live_tools, …)` at [`server.py:13373`](../../../mcp_server/src/rook/server.py).
- The dispatch path gains a **meta-tool interception point in `call_tool` ahead of
  `_call_tool_dispatch`'s recording tail**, and `rook_tools_call` re-enters the post-wall policy path
  for its target (§6). Surgical, **not** handler migration.

---

## 3. Scope

**In:**

- A `CapabilityRecord` / `CapabilityIndex` enriched from the **existing** tool schemas plus existing
  metadata sources (`TOOL_GROUPS`, `TOOL_CATEGORIES`, `DESTRUCTIVE_TOOLS`, `PUBLIC_READONLY_TOOL_NAMES`,
  dispatchability signals).
- Four discovery tools: `rook_tools_ls`, `rook_tools_search`, `rook_tools_read`, `rook_tools_call`.
- `lean` becomes a discovery **floor**, not a ceiling; discovery tools exposed in **all three**
  profiles, scoped appropriately (§5, §7).
- `rook_tools_call` dispatch routed through the **same policy path** as native calls, preserving the
  readonly wall and the no-side-effect-on-block contract (§6).
- A minimal, dependency-free argument validator (§6.1).
- Tests proving the severe acceptance criterion (§9).

**Out (named non-goals):**

- Moving any tool family / handler out of `server.py`. (The Index is the *seam* for that later work; this
  spec does not exercise it.)
- Replacing the audited `readonly` wall with inferred posture metadata. Enforcement stays the allowlist.
- LM Planner `execution_ref` binding against the Index.
- Embeddings / semantic search as a dependency. Search is **lexical** this phase.
- **Adding a new Python dependency** (e.g. `jsonschema`). Validation is in-house and minimal (§6.1).
- Generating MCP tool definitions from a new canonical registry format. The Index **wraps** the existing
  `Tool(...)` defs by reference; it does not become their source.
- **Pruning or retuning the lean floor.** Lean stays additive (17 kept + 4 added). Floor tuning is a
  later, telemetry-driven decision.

---

## 4. The Capability Index

### 4.1 Module, dependency rule, and the unprofiled source

New module **`mcp_server/src/rook/capability_index.py`**, holding `CapabilityRecord`, `CapabilityIndex`,
a pure `build_index(tools, ...)`, and pure query helpers (`ls`, `search`, `read`).

- **One-way dependency** (mirrors the profile spec's §6): `capability_index.py` **must not import
  `server.py`**. It may import leaf data modules (`agent/tool_groups.py`, `context.py`,
  `mcp_tool_profiles.py`), none of which import `server.py`.
- **The Index is built from an *unprofiled* source — not `list_tools()`.** Today `list_tools()` returns
  `filter_tools(live_tools, resolve_profile(os.environ))` ([`server.py:13373`](../../../mcp_server/src/rook/server.py)).
  Building the Index from that would, under `lean`, yield an Index of only the 21-tool floor —
  `rook_tools_search("director")` would find nothing. Factor an unprofiled **`_all_live_tools()`**: the
  static `Tool(...)` set with the **deprecated-interactive live gate applied**
  ([`server.py:13365`](../../../mcp_server/src/rook/server.py)–:13371) but **no profile filter**. Then:
  - `INDEX = build_index(_all_live_tools())` — always the full live surface, regardless of active profile.
  - `list_tools()` becomes a thin profile **projection** over the same source:
    `filter_tools(_all_live_tools(), resolve_profile(os.environ))` — behavior-identical to today for all
    three profiles.

The Index is a **projection + enrichment** of the existing `Tool(...)` defs, never a replacement.

### 4.2 `CapabilityRecord`

| field | source | role |
|---|---|---|
| `name` | live `Tool.name` | canonical id |
| `path` | derived `/{domain}/{group?}/{name}` | filesystem address for `ls` |
| `domain` | name-prefix reconciled with `TOOL_CATEGORIES`/`TOOL_GROUPS` | `rhino`/`gh`/`rc`/`director`/`vision`/`video`/`bim`/`scene`/`knowledge`/`session`/`meta` |
| `groups` | `TOOL_GROUPS` membership | cross-links (may be empty) |
| `summary` | first sentence of `Tool.description` | cheap `ls`/`search` line |
| `posture` | `read`/`mutate`/`execute`, from `DESTRUCTIVE_TOOLS` + the profile spec's §5.3 mutation rules + the execute-set | **descriptive only** — not enforcement |
| `readonly_safe` | `name ∈ PUBLIC_READONLY_TOOL_NAMES` | surfaces the *audited* truth; descriptive |
| `mcp_dispatchable` | reachable through MCP `call_tool` / `_call_tool_dispatch` | **load-bearing** — `rook_tools_call` and discovery filter on this |
| `agent_dispatchable` | reachable through the internal RookChat/HTTP dispatcher | **reserved** for LM2; recorded, not load-bearing this phase |
| `input_schema` | **reference** to live `Tool.inputSchema` | returned verbatim by `read`; no new format |

**Dispatchability disambiguation (critical).** Rook has two distinct transports. A tool may be
MCP-callable but not internal-agent-callable, or vice-versa. `rook_tools_call` rescues **MCP** clients,
so it filters on `mcp_dispatchable` **only**. Filtering on `agent_dispatchable` would hide exactly the
MCP-only VisionDirector tools this campaign exists to surface. `agent_dispatchable` is recorded now so
the same record serves LM2 later, but it is inert here.

---

## 5. The discovery surface (four tools)

- **`rook_tools_ls(path="/", depth=1)`** — browse the tool filesystem. Returns compact entries
  (`name, path, domain, posture, readonly_safe, summary`) and child paths. **No schemas.**
- **`rook_tools_search(query, domain?, posture?, limit=10)`** — **lexical** ranking over
  name + summary + domain + groups (no embeddings). Returns compact entries.
- **`rook_tools_read(name)`** — the full record for one tool: `input_schema`, full description, `domain`,
  `posture`, `readonly_safe`, `mcp_dispatchable`. (This **is** "describe.")
- **`rook_tools_call(name, arguments)`** — validate, then dispatch the target through the shared policy
  path (§6).

### 5.1 Profile exposure

All four tools are exposed in **full**, **lean**, and **readonly** — the Index is a canonical server
surface, not a lean hack. Scoping differs by profile:

- **full / lean:** `ls`/`search`/`read` surface the whole Index (every `mcp_dispatchable` record).
- **readonly:** `ls`/`search`/`read` are **profile-scoped** — they surface `readonly_safe` capabilities
  by default, so a readonly client's "what can I do?" answer matches what it may actually run. (A future
  `include_blocked=true` browsing mode is reserved, not built.)
- **`rook_tools_call` exists in all three**, including readonly — because it does **not** bypass the
  wall. Under `readonly`, a `readonly_safe` target runs; a mutator target is blocked by the re-entered
  wall (§6). That is why `rook_tools_call` is an *allowed* readonly tool rather than a sentinel: it adds
  no bypass.

### 5.2 Visible ⇒ MCP-dispatchable

`ls`/`search` never surface a record with `mcp_dispatchable == false`, and `rook_tools_call` refuses one
with a clear error. This carries the LM1 "visible-implies-dispatchable" invariant onto the MCP surface,
disambiguated to the MCP transport (§4.2).

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

- `rook_tools_ls` / `rook_tools_search` / `rook_tools_read` are answered from the Index inside
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

**`rook_tools_call` guards, applied before re-entry:**

1. **No meta-recursion** — reject any target in `{rook_tools_ls, rook_tools_search, rook_tools_read,
   rook_tools_call}` (also stops the re-entry from looping back into interception).
2. **MCP-dispatchable** — reject targets with `mcp_dispatchable == false` (§4.2).
3. **Argument validation** — §6.1.

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

### 7.1 Lean floor (17 kept + 4 added = 21)

Lean keeps its existing 17 unchanged and adds the four `rook_tools_*`. **No pruning** (non-goal, §3).
Semantics, stated in the spec so reviewers don't relapse into the old worldview:

- The 17 are **always-visible boot/convenience tools** — connection, targeting, snapshot, knowledge.
- The four `rook_tools_*` are the **capability access layer**.
- Lean is no longer "all Codex can use." It is "the boot tools Codex sees **before it browses the
  Index**."

`gh_edit`, `rhino_execute_intent`, `gh_execute_intent` stay in the floor for now: already reviewed in
the profile campaign, common enough to justify native schema visibility, and more ergonomic than
`rook_tools_call` when the model already holds the schema. Removing them is deferred floor-tuning.

### 7.2 Membership and counts

- `PUBLIC_LEAN_TOOL_NAMES`: 17 → **21** (+ four `rook_tools_*`).
- `PUBLIC_READONLY_TOOL_NAMES`: 145 → **149** (+ four `rook_tools_*`; all four are readonly-safe — the
  three readers are pure reads, `rook_tools_call` is wall-protected per §6).
- Live `full` `list_tools()`: 427 → **431**.
- Profile snapshot tests are **updated** to these counts; counts are assertions of current truth, not
  frozen constraints (the membership invariants in §9 are the durable assertions).

### 7.3 Asymmetry preserved

`lean` remains list-only (no wall); `readonly` remains an enforced wall. The discovery surface composes
with both: in `lean`, `rook_tools_call` reaches anything (no wall); in `readonly`, it reaches only what
the wall permits.

---

## 8. Hard invariants

1. **Enforcement authority unchanged.** `readonly` blocking is `tool_blocked()` against the audited
   `PUBLIC_READONLY_TOOL_NAMES`. `posture` / `readonly_safe` **do not enforce call permission** —
   `readonly_safe` may *scope readonly discovery* (§5.1), but only `tool_blocked()` gates whether a call
   executes.
2. **No new bypass.** `rook_tools_call` re-enters through `call_tool` / the shared policy helper, never
   `_call_tool_dispatch`. The wall fires on the target identically to a native call.
3. **Visible ⇒ MCP-dispatchable.** Discovery hides `mcp_dispatchable == false`; `rook_tools_call`
   refuses it.
4. **No meta-recursion.** `rook_tools_call` refuses `rook_tools_*` targets.
5. **Index wraps, never replaces.** `input_schema` is the live `Tool.inputSchema` by reference; the
   `Tool(...)` defs remain the source of truth for schemas.
6. **One-way dependency.** `capability_index.py` does not import `server.py`.
7. **Index source is unprofiled.** The Index is built from `_all_live_tools()` (deprecated-gate applied,
   profile filter **not** applied); `list_tools()` is a profile projection over the same source.
   Discovery never shrinks with the active profile.
8. **Meta-tools never reach the recording tail.** `rook_tools_*` are intercepted in `call_tool` before
   `_call_tool_dispatch`; only forwarded **targets** are observed — once, under their real name. A
   blocked target is observed not at all.

---

## 9. Testing contract

**Severe acceptance criterion (the spine):**

1. **lean reach:** with `ROOK_MCP_TOOL_PROFILE=lean`, `rook_tools_search("director preview")` surfaces
   `rhino_director_preview_motion`; `rook_tools_read` returns its schema; `rook_tools_call` dispatches
   it successfully — **no MCP restart**.
2. **readonly block:** with `readonly`, the same
   `rook_tools_call("rhino_director_preview_motion", …)` returns the `tool_profile_blocked` envelope —
   `preview_motion` is not on the audited allowlist (default-deny), proving discovery is **not** a
   bypass.
3. **full unchanged:** with `full`, native direct tool behavior and `list_tools()` projection are
   unchanged (modulo the +4 meta-tools).

**Unprofiled-source / membership invariants (not a frozen count):**

4. **Index is not the lean projection:** under `lean`, the Index contains `rhino_director_preview_motion`
   (built from `_all_live_tools()`), even though `list_tools()` under `lean` does not advertise it.
5. lean contains all original 17 **and** the four `rook_tools_*`; `rhino_director_preview_motion` is
   **not** directly advertised in lean's `list_tools()` but **is** discoverable/readable/callable via
   `rook_tools_*`.

**Recording / safety / structure:**

6. **No record on block:** a `readonly`-blocked `rook_tools_call` target produces **no**
   `_record_observation` entry **and no** `get_phase_tracker().record_call` tick (assert both).
7. **No meta self/double record:** a successful `rook_tools_call` records **exactly one** observation,
   under the **target** name (origin `meta`), and **none** under `rook_tools_call`;
   `rook_tools_ls/search/read` record none.
8. **No raw-dispatcher bypass:** `rook_tools_call` routes through `call_tool`/the policy helper, not
   `_call_tool_dispatch` (assert the wall fires on the target — e.g. a mutator target blocks under
   `readonly`).
9. **Recursion guard:** `rook_tools_call("rook_tools_ls")` (and the other three) is rejected.
10. **Validator coverage:** `rook_tools_call` rejects missing `required`, wrong `type`, out-of-`enum`,
    and out-of-`min/max` numeric args with field-level errors and does **not** dispatch; unsupported
    keywords pass through to the handler.
11. **Visible ⇒ MCP-dispatchable:** no `mcp_dispatchable == false` record appears in `ls`/`search`;
    `rook_tools_call` on one is refused.
12. **Readonly scoping:** under `readonly`, `ls`/`search`/`read` surface `readonly_safe` records by
    default.
13. **Index drift oracle:** every record's `readonly_safe` agrees with `PUBLIC_READONLY_TOOL_NAMES`; the
    Index covers 100% of `_all_live_tools()`; the audited allowlist is the oracle.

---

## 10. Out of scope (YAGNI — explicitly deferred)

- Handler / tool-family extraction out of `server.py` (the Index *enables* it; the next spec exercises
  it, VisionDirector as the likely pilot).
- `readonly` enforcement migrating from allowlist to a registry `posture` query (allowed **only** after
  every tool has reviewed posture metadata + drift tests).
- LM2 Planner `execution_ref` binding against the Index.
- Embeddings / semantic search; any new Python dependency (`jsonschema` included).
- `tools.listChanged`-driven native dynamic loading (an opportunistic enhancement for clients that
  support it; the dispatcher is the client-agnostic path and ships first).
- Lean floor pruning.

---

## 11. Rollout and LM2 relationship

Build the vertical slice: the `CapabilityIndex` data model + `build_index` over `_all_live_tools()`, the
four `rook_tools_*` tools, the `call_tool` meta-interception + target re-entry, the in-house validator,
the profile-membership updates, and the §9 tests. `full` stays the absent-default; `readonly` stays
enforced by the audited allowlist.

The Index is deliberately shaped to **become** the LM2 Capability Registry: the same `CapabilityRecord`
that backs MCP discovery today is what the Planner will query to bind `execution_ref` tomorrow, and what
will generate the agent catalog (collapsing the duplicated MCP-vs-HTTP descriptions) and anchor the
strangler-fig decomposition of `server.py`. Those are **named successor specs**, not this one. This
spec's job is to end the lean-as-ceiling failure with a vertical slice through the real architecture —
nothing wider, nothing shallower.
