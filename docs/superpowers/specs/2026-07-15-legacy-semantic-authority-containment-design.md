# Legacy Semantic-Authority Containment Design

Date: 2026-07-15
Amended: 2026-07-18
Status: Compressed design approved in conversation; amended specification under review

## Decision

Make six exact legacy semantic tool identities undiscoverable and impossible to
execute through every current production discovery and dispatch path, while
proving that supported explicit Rhino and Grasshopper workflows still work.

This is an emergency containment campaign, not a general authorization,
executor, cache-consistency, or agent-framework redesign. The implementation
pattern is deliberately shallow: resolve an exact name, deny or omit it, and
return before tool-specific work begins.

The six identities are:

| Tool | Disposition |
|---|---|
| `gh_execute_intent` | `retired` |
| `rhino_execute_intent` | `retired` |
| `plan_and_execute` | `suspended` |
| `spawn_agent` | `suspended` |
| `gh_explore_workflow` | `suspended` |
| `gh_replay_recipe` | `suspended` |

### 2026-07-18 release-proof amendment

This amendment leaves the six-name runtime containment contract unchanged and
supersedes the earlier release-proof requirements for a full installed
six-by-seam matrix, an alternate candidate builder, generalized installed
validator, durable-hold system, and artifact-bound rollback verifier.

Release proof now uses the normal Rook release artifacts, exhaustive source
coverage, a complete 36-probe installed transport set, one installed
representative for each of the current 29 internal seams, and the two supported
live workflows. Failure handling withdraws the disposable runtime while
preserving the non-disposable RookVision gallery. This specification is the
single amended baseline from which the implementation plan must be rewritten.

There is no environment flag, maintenance profile, hidden direct-call path, or
packaged test callable that may reactivate them. A stale client calling an exact
contained identity receives a stable fail-closed tombstone under every profile.

## Triggering Failure And Product Risk

The triggering live failure was a request to create a Grasshopper sphere driven
by a radius slider. `gh_execute_intent` created the requested Sphere and Number
Slider, but also created four unrelated components, failed to set the intended
slider range and value, returned `partial_success: true` and `verified: false`,
and left Grasshopper warnings. The behavior demonstrates why an apparently
convenient prose-to-mutation executor cannot retain production authority when
its semantic selection, mutation bounds, and host verification are not reliable.

The root product risk is concealed semantic authority: a hidden model, DSPy
module, stored heuristic, knowledge selection, or autonomous loop can translate
prose into host mutation without a bounded and validated authority contract.
The response is to contain the six tool identities, not to ban model
participation or weaken explicit tools.

## Confirmed Current Evidence

The design is based on the following verified repository and runtime facts:

- All six names are present in the current full MCP surface and direct dispatch
  cases.
- The current default full surface has 428 advertised tools; enabling the three
  deprecated interactive tools produces 431.
- The current lean surface has 22 tools and advertises
  `gh_execute_intent` and `rhino_execute_intent`. Lean is an advertisement
  profile, not an execution authorization boundary.
- The current readonly surface has 148 tools and omits the six names, but exact
  tombstones must override the profile wall so stale callers receive one stable
  lifecycle result under every profile.
- Public MCP dispatch and the internal `ToolDispatcher` are independent
  execution surfaces.
- `RookAgent` currently parses arguments and emits parameter-bearing execution
  events before calling its executor. `RookChat` likewise parses arguments and
  emits tool events before dispatch.
- `RookAgent._execute_tool`, `ToolDispatcher._dispatch_inner`,
  `server._mcp_tool_executor`, and PlanGraph live dispatch are directly callable
  internal seams.
- `BootstrapRunner`, the deprecated packaged learning-agent executor, and the
  explorer HTTP executor accept arbitrary `(name, params)` calls. Their packaged
  mock executors currently return success without lifecycle awareness.
- `build_local_tools()` currently registers a separate local
  `rhino_execute_intent` implementation.
- The full-catalog writers currently live under `spawn_agent` and
  `plan_and_execute`, so suspending them without another refresh path would
  strand persisted RookChat catalogs.
- `MetricsStore.record(Observation)` updates ordinary daily and per-tool
  execution metrics and may retain intent/error content. Its ordinary recent
  deque is bounded to 50 entries, but its daily and per-tool aggregates are not.
- Substrate telemetry is append-only JSONL and contains broader session and
  operation data. Neither existing recording path satisfies the containment
  telemetry contract unchanged.
- LM9A validates deterministic artifacts but is not wired into these live
  semantic executors and is not their replacement.
- The existing profile, progressive-meta, and dispatcher baseline used during
  design review passed 95 tests. Tests that encode current positive exposure or
  old readonly precedence must be intentionally inverted.

## Authority Doctrine

### Supported model-as-actor workflows

The following remain supported and are not weakened by this campaign:

- The primary connected model inspecting host state and choosing explicit
  admitted tools.
- `gh_snapshot` or live component discovery, model reasoning, explicit
  `gh_edit`, solve/error/output inspection, and verification.
- Typed Rhino and Grasshopper mutation tools.
- `gh_create_script`, `gh_update_script`, and `gh_set_script`.
- `rhino_execute` and properly preflighted, fully scripted `rhino_command`
  calls.
- Ordinary RookChat calls to explicit admitted tools.
- Host-read-only inspection and advisory tools, plus knowledge-store
  maintenance. Knowledge output never carries mutation authority; mutation
  requires a subsequent explicit admitted tool call.
- LM9A and deterministic PlanGraph development. Live PlanGraph nodes may
  dispatch only explicit admitted identities through the same lifecycle guards.
  Validation of an artifact does not itself authorize execution.

The campaign filters current agent registries and catalogs through the lifecycle
manifest. It does not create a universal agent/tool authorization system.

### Identity-based containment

Containment follows the exact admitted tool identity, not the module that
contains its implementation. Supported tools may continue to reuse bounded
mechanical primitives formerly shared with a contained executor. In particular,
retiring `rhino_execute_intent` must not disable safe typed Rhino paths that use
shared low-level logic.

Identity-based containment does not permit renaming, proxying, re-exporting, or
delegating a contained semantic executor behind an admitted identity. An
admitted tool must preserve explicit arguments or code, deterministic safety
checks, and observable host verification. Reintroducing hidden semantic
selection or autonomous looping requires separate review.

Tests can prove that exact contained names never delegate into downstream code.
They cannot mechanically prove that a future implementation has not recreated
equivalent hidden semantic authority under a different name. That remains an
architectural review rule.

### Dormant source boundary

Legacy bodies may remain as dormant source for historical analysis and may be
exercised only by isolated tests with mocked model and host boundaries. No
production registration, exported test callable, runtime flag, or packaged
maintenance mode may bypass containment. Migration may extract bounded
primitives but may not invoke a contained entry point in production.

The local `rhino_execute_intent` handler is removed from production
`build_local_tools()` registration. Other dormant bodies need not be physically
deleted in this campaign.

## Lifecycle Manifest

### Module boundary

One pure-stdlib leaf module owns the lifecycle manifest, exact resolver,
validation, deterministic fingerprint, denial payload construction, and fixed
dispatch-origin enum. It must not import `server`, agent loops, Rhino targeting,
catalog builders, model clients, or host bridges.

The manifest is immutable after import. Runtime sites consume its resolver and
projection helpers; they do not maintain secondary lifecycle deny lists.
Existing profile, group, risk, trigger, and historical classifications may
retain latent membership because they are not lifecycle authority. Their
runtime projections are filtered through the manifest.

### Entry schema and limits

Each entry contains exactly:

- canonical `name`;
- `disposition`, either `retired` or `suspended`;
- manifest-owned `recovery` guidance;
- `restoration_criteria`;
- explicit `aliases`.

Validation is mechanical and code-owned:

- Canonical names and aliases must match `^[a-z][a-z0-9_]{0,127}$`, be ASCII,
  and be at most 128 characters.
- A canonical name or alias may identify only one manifest entry.
- Each entry may contain at most 16 aliases.
- V1 aliases are exactly empty for all six entries.
- Recovery guidance is 1 to 512 UTF-8 bytes, single-line, and contains no
  control characters.
- A suspended entry has 1 to 16 restoration criteria, each at most 256 UTF-8
  bytes, single-line, and control-character-free.
- A retired entry has exactly zero restoration criteria.

Import validation can enforce the mechanical rules and the empty retired
criteria. Whether suspended criteria have been substantively satisfied remains
a review decision.

### Manifest entries

#### `gh_execute_intent`

- Disposition: `retired`
- Recovery: `Rediscover the current Grasshopper surface; inspect state and components, then use explicit gh_edit or supported script tools and verify solve state, outputs, and errors.`
- Restoration criteria: empty

#### `rhino_execute_intent`

- Disposition: `retired`
- Recovery: `Rediscover the current Rhino surface; use explicit typed Rhino tools, rhino_execute, or a sanctioned preflighted rhino_command, then verify the host result.`
- Restoration criteria: empty

#### `plan_and_execute`

- Disposition: `suspended`
- Recovery: `Rediscover the current surface and perform bounded steps through explicit admitted tools; autonomous plan execution is suspended.`
- Restoration criteria:
  1. `A bounded plan contract limits admitted node identities, call counts, targets, and mutation scope.`
  2. `Every live node re-enters lifecycle and profile guards before parameters are copied or execution begins.`
  3. `Readiness, host verification, failure, and restoration evidence are deterministic and independently reviewed.`

#### `spawn_agent`

- Disposition: `suspended`
- Recovery: `Rediscover the current surface and use the connected model to call explicit admitted tools directly; autonomous agent spawning is suspended.`
- Restoration criteria:
  1. `Agent authority is bounded by admitted tool identities, explicit targets, deterministic call budgets, and stop conditions.`
  2. `Injected and local registries are filtered and every invocation independently re-enters lifecycle and profile guards.`
  3. `Live readiness, verification, restoration, and runaway-control evidence is recorded and independently approved.`

#### `gh_explore_workflow`

- Disposition: `suspended`
- Recovery: `Rediscover the current Grasshopper inspection surface and use explicit snapshot, component, or knowledge tools; semantic workflow exploration is suspended.`
- Restoration criteria:
  1. `The contract is proven host-read-only or every possible mutation is explicit, bounded, authorized, and verified.`
  2. `Knowledge or model output cannot directly carry mutation authority into a hidden executor.`
  3. `Deterministic tests and live evidence prove the bounded contract and absence of undeclared host mutation.`

#### `gh_replay_recipe`

- Disposition: `suspended`
- Recovery: `Rediscover the current Grasshopper surface and apply reviewed explicit gh_edit operations; recipe replay is suspended.`
- Restoration criteria:
  1. `Recipes use a versioned bounded schema containing only explicit admitted operations and validated arguments.`
  2. `Preflight establishes target ownership, readiness, mutation bounds, and a restoration plan before execution.`
  3. `Execution produces deterministic host verification and verified restoration or an approved durable recovery receipt.`

Recovery guidance never promises that a replacement is available under the
caller's current profile. It directs the caller to rediscover the current
surface.

### Lifecycle permanence

A `retired` tool will not return under its current semantic contract. A
`suspended` tool may return only through a separately reviewed change that
satisfies its recorded restoration criteria.

A retired entry remains as a stale-client tombstone even after its
implementation is physically deleted. Removing that tombstone is a separate
breaking-contract decision.

A suspended entry may be removed only after its restoration evidence is
recorded durably outside the manifest and approved. Removing a suspended entry
is the action that restores ordinary profile-wall behavior; no runtime override
exists.

### Deterministic fingerprint

The lifecycle fingerprint is SHA-256 over canonical UTF-8 JSON containing all
manifest entry fields. Entries are sorted by canonical name, aliases are
sorted, object keys are sorted, and JSON uses fixed `,` and `:` separators with
no insertion-order or Python-hash dependence. Restoration criteria retain their
declared tuple order.

The fingerprint is a cache refresh signal, not authorization. Every catalog is
revalidated against the live manifest regardless of whether its stored
fingerprint matches.

## Stable Denial Contract

### Inner payload

The stable inner denial payload is:

```json
{
  "code": "legacy_semantic_tool_contained",
  "tool": "<canonical-name>",
  "disposition": "retired|suspended",
  "retryable": false,
  "verified": false,
  "recovery": "<manifest-owned guidance>"
}
```

`retryable: false` means that repeating the same identity cannot succeed under
the deployed manifest. `verified: false` means no host result exists because
execution did not occur; it does not express uncertainty about the containment
decision.

Restoration criteria are not included in the runtime denial payload.

### Transport envelopes

Internal dispatchers return:

```json
{
  "success": false,
  "data": {
    "code": "legacy_semantic_tool_contained",
    "tool": "<canonical-name>",
    "disposition": "retired|suspended",
    "retryable": false,
    "verified": false,
    "recovery": "<manifest-owned guidance>"
  }
}
```

Public MCP passes that internal envelope through `_format_tool_result()` exactly
once and returns one `TextContent` whose text is `Error: <JSON inner payload>`.
Agent and dispatcher seams return the internal dictionary. Model loops serialize
it as their required protocol tool result. PlanGraph returns its typed refusal
rather than projecting the denial as a host execution result.

For a contained target of `rook_tools_call`, `_handle_meta_tool` constructs the
internal denial envelope, passes it through `_format_tool_result()` exactly once,
and returns that existing `TextContent` result. The outer `call_tool` returns the
result unchanged; it neither formats it again nor re-enters target dispatch.

## Catalog And Discovery Containment

Discovery is not authorization. Catalog filtering prevents recommendation and
selection, while every invocation boundary independently resolves lifecycle
state.

### Exact containment projection

Filtering is strict and non-coercing:

- A raw value is eligible for an exact lifecycle match only when
  `type(value) is str`.
- Matching is case-sensitive exact equality with a canonical name or explicitly
  declared alias.
- No `str()`, trimming, case-folding, prefix, substring, or fuzzy matching is
  permitted.
- Unknown names, misspellings, and near matches retain existing behavior and
  reveal no lifecycle state.

For mapping-backed catalog records, filtering inspects both the raw mapping key
and the raw embedded `function.name`. The record is omitted when either value is
an exact contained identity. Schema lists inspect their raw embedded identity
field (`function.name` for LiteLLM schemas and `name` for MCP tool records).
Local registrations inspect their raw registration key. This is a narrow
anti-hiding rule for the six identities, not a generalized name-mismatch or
catalog-collision framework. Unrelated malformed or mismatched records retain
their existing handling.

Catalog filtering emits no containment telemetry because omission is not an
invocation attempt.

### Concrete projection checklist

Implementation must inspect the current constructor, setter, registration,
cache, and final model-projection sites without replacing them with a new
registry abstraction. The checklist includes:

- `server._all_live_tools()` and every serialized `list_tools()` profile view;
- progressive capability-index construction, AST-derived dispatchability, and
  capability-index caches;
- `ToolRegistry` construction, cache load/save, and post-construction catalog
  registration;
- RookChat persisted, fallback, local, overlay, and final model-visible
  catalogs;
- raw `RookAgent` schemas, schema setters, local registration, and final
  model-visible projection;
- `ToolDispatcher(local_tools=...)`, `register_local()`, and
  `register_locals()`;
- capability-inventory unions derived from tiers, groups, routes, and local
  tools; and
- injected or prebuilt registries supplied to embedded entrypoints.

Pure registration and catalog filtering never use the telemetry-emitting
invocation guard.

Existing consumer policy remains independent. Agent-management exclusions,
profile walls, recursion rules, and consumer-specific selection continue to
apply to admitted tools. A canonical full catalog must not reintroduce tools to
a consumer that already excludes them for another reason.

### Persisted catalogs and startup refresh

Persisted catalog data carries the lifecycle fingerprint alongside its catalog.
An older plain mapping has a missing fingerprint and remains readable only
through the same revalidation path.

Every load performs exact lifecycle revalidation regardless of fingerprint.
Contained records are omitted before any model or dispatcher receives the
catalog. A missing or changed fingerprint requests refresh but is not itself an
authorization failure.

Catalog refresh is an explicit best-effort startup operation used by MCP and
embedded entrypoints. `list_tools()` remains read-only. The existing advice to
run `spawn_agent` to populate the catalog is removed.

If refresh succeeds but persistence fails, the process uses the fresh filtered
catalog in memory and reports degraded cache health. If refresh construction
fails, a previously persisted catalog may remain usable in degraded or
incomplete form after current-manifest revalidation. If no cache can be safely
revalidated, the consumer receives its existing code-owned,
lifecycle-filtered fallback or an explicit catalog-unavailable error; it must
not silently continue with an empty registry. Rejected cache content is never
merged into a fallback.

There is no runtime active-catalog, schema/build-identity, or cache-freshness
fingerprint, cache generation, or quarantine mechanism in this campaign. This
does not prohibit the external release artifact SHA-256 used to bind acceptance
evidence. A safe existing cache is not discarded merely because refresh failed.

### Expected discovery snapshots

The current acceptance-test snapshots become:

| Surface | Before | After |
|---|---:|---:|
| Default unprofiled/full | 428 | 422 |
| Interactive-enabled full | 431 | 425 |
| Lean | 22 | 20 |
| Readonly | 148 | 148 |

The counts are assertions against the current candidate, not a replacement for
exact absence tests.

## Execution Containment

### Raw-name and ordering contract

Invocation guards match only when `type(name) is str` and the raw value exactly
equals a manifest identity. They never coerce, trim, normalize, or fuzzy-match.

After only the transport framing and authentication needed to obtain the raw
tool name, and before all tool-specific validation or argument access, an exact
contained identity resolves to the stable tombstone. The guard precedes schema
validation, argument decoding, profile eligibility, capability-index lookup,
knowledge middleware, model invocation, target selection, and host dispatch.

This ordering is a narrow tombstone exception, not a weakening of readonly.
Exact contained identities return `legacy_semantic_tool_contained` under every
profile. Active mutating tools under readonly still return
`tool_profile_blocked`. Unknown and near-match names retain existing
non-enumerating readonly behavior and emit no containment telemetry.

For `rook_tools_call`, the implementation inspects only the raw target `name`
field before capability-index construction, target profile checks, or access to
nested `arguments`. The ordinary path may perform its current coercion and
validation only after the target fails to match the manifest.

### Concrete execution checklist

Each current execution seam gets a small explicit resolver call and early
return. The campaign does not introduce a universal wrapper or executor
framework. Required seams are:

- public MCP `server.call_tool`;
- progressive `server._handle_meta_tool` for `rook_tools_call`;
- `server._call_tool_dispatch`;
- `server._mcp_tool_executor`;
- `ToolDispatcher.dispatch` and `ToolDispatcher._dispatch_inner`;
- any direct local-call helper that remains a production `(name, params)`
  executor seam;
- the `RookAgent` model tool-call loop before JSON argument parsing;
- `RookAgent._execute_tool`;
- `RookAgent._execute_local_tool` when retained as a directly callable
  production seam;
- the `RookChat` model tool-call loop before JSON argument parsing and normal
  tool events;
- PlanGraph live execution immediately after raw `execution_ref` resolution and
  before parameter copying; and
- the direct private `_handle_spawn_agent` and `_handle_plan_and_execute`
  entries before tasks, models, or plans are created.

Three additional packaged arbitrary-name executor families have an explicit
disposition in this campaign:

- `bootstrap/runner.py`: `BootstrapRunner.run_test` guards immediately after
  reading only the raw `test.tool`, before dependency checks or any branch that
  can read or copy `test.params`. Its local `_mock_executor` also guards direct
  calls and cannot return mock success for a contained identity.
- `learning/agent.py`: the callable returned by `create_tool_executor()` guards
  before endpoint selection, parameter transformation, or `call_rhino`.
- `explorer/executor.py`: `HttpExecutor.execute` and `MockExecutor.execute` guard
  before endpoint resolution, parameter access, timing, or HTTP work. Their sync
  wrappers delegate only to the guarded async method and do not record a second
  denial.

The paired packaged executors in `bootstrap/executor.py`, including
`HttpExecutor.execute` and the callable returned by `create_mock_executor()`,
receive the same guard. No production or packaged mock executor may report
success for a contained identity. All of these guards use the existing
`internal_handler` origin.

Dictionary-returning executors use the stable internal denial envelope. An
executor whose established API returns `ExecutionResult` preserves that wrapper
with `success=false`, an empty parameter projection, the stable internal denial
envelope as refusal detail, and no claimed host result.

`BootstrapRunner.run_test` preserves its `TestResult` API with the canonical
tool name, `params={}`, `actual=TestOutcome.ERROR`, the stable internal denial
envelope in `response`, `error_message="legacy_semantic_tool_contained"`, and no
created IDs or execution duration. It returns before updating `completed_tests`.
Existing `record_to_knowledge` behavior skips `ERROR`, so the refusal is
ineligible for knowledge, MAB, completion, or adaptive recording. This adapter
and the `ExecutionResult` adapter are narrow return-type preservation rules, not
a general executor framework.

Any additional production function discovered during implementation that
accepts a tool identity and parameters and can reach an implementation must
either receive the same shallow guard or be documented and proven to be an
isolated test-only seam. This inventory requirement does not authorize a
general executor rewrite.

### Structural exact-once behavior

Exactly-once denial is structural:

1. The first denying boundary makes one containment recording attempt.
2. It immediately returns the boundary-appropriate refusal.
3. No downstream guard or execution path is reached.

There is no `ContextVar`, ambient denial scope, deduplication token, or
inherited "already checked" state. A caller that directly invokes a deeper
boundary creates a new attempt and makes one new recording attempt. With an
operational sink, each attempt produces exactly one ring record. Sequential and
sibling attempts remain distinct. A nested meta-dispatch attempt records once
because the meta boundary denies before re-entering public dispatch.

Every guard independently consults the manifest. Prior checking can never act
as authorization.

### RookAgent protocol behavior

Abort, steering-interrupt, and exhausted-call-budget checks remain before
containment. A skipped call is not a denied invocation and emits no containment
event.

For an eligible denied call, RookAgent:

- increments `calls_this_turn`;
- appends exactly one protocol `role: tool` result using the original
  `tool_call_id`;
- does not JSON-decode or otherwise inspect the raw argument text;
- emits no normal tool-start or tool-end event;
- performs no knowledge, executor, model, target, or host work; and
- never enters successful-tool-use or adaptive history, observations,
  substrate analytics, or failure adaptation.

The assistant message necessarily retains raw argument text for protocol
validity. Containment does not copy that text into execution structures, logs,
telemetry, or observations.

### RookChat protocol behavior

RookChat has a round limit rather than a per-call budget. A denied call:

- consumes the current tool round;
- sets `meta_only_round = false` so it cannot trigger the false "stuck loading
  tools" diagnosis;
- appends exactly one protocol tool result with the original tool-call ID;
- remains outside `tools_used` and progressive adaptation;
- emits no normal `tool_start` or `tool_result` event; and
- does not decode, inspect, log, or execute raw arguments.

RookChat necessarily received an upstream model response containing the denied
call. The invariant is that containment causes no downstream or
containment-triggered model invocation.

After the protocol denial is appended, the already-connected primary model may
continue normally on a later turn or round under its existing call and round
budgets. In this design, "no downstream model invocation" means that neither
containment machinery nor a dormant implementation invokes a model; it does not
forbid ordinary continuation by the primary conversation model.

### PlanGraph behavior

After resolving the raw `execution_ref`, and before copying node parameters,
PlanGraph checks lifecycle state. A contained identity returns a typed
`tool_lifecycle_denied` not-applied refusal with the input graph unchanged. The
stable inner denial payload may be carried as refusal detail.

The denial does not pass through ordinary host-result projection, create an
execution outcome, or manufacture a host receipt for work that never occurred.
No broader PlanGraph outcome redesign is part of this campaign.

### Downstream exclusion

A denied invocation must not reach:

- tool-specific argument or schema validation;
- implementation bodies or dormant local handlers;
- knowledge injection or command selection;
- downstream or containment-triggered model invocation;
- Rhino or Grasshopper targeting, discovery, or host calls;
- ordinary `Observation` recording or substrate JSONL;
- successful-tool-use or adaptive history; or
- host-receipt generation.

The protocol result and PlanGraph typed refusal are intentional refusal paths,
not downstream execution.

## Containment Telemetry

### Event contract

Every exact invocation attempt rejected by lifecycle containment makes exactly
one recording attempt for an event named `containment_denial`. With an
operational sink, that attempt appends exactly one ring record. Its closed
payload contains exactly:

```json
{
  "tool": "<canonical-name>",
  "disposition": "retired|suspended",
  "origin": "<fixed-enum-origin>",
  "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffffZ"
}
```

The timestamp is system-generated UTC ISO 8601 with six fractional-second
digits and a terminal `Z`.

The fixed origin enum is:

- `public_mcp`;
- `progressive_meta`;
- `server_dispatch`;
- `rook_agent`;
- `rook_chat`;
- `plan_graph`;
- `tool_dispatcher`; and
- `internal_handler`.

Origin is code-owned. It never contains profile data or caller-supplied text.
Retired and suspended entries use the same event shape; only `disposition` and
manifest recovery guidance differ in the separate denial payload.

Origins map deterministically to the first denying boundary:

| Boundary | Origin |
|---|---|
| Public MCP `call_tool` | `public_mcp` |
| Progressive `rook_tools_call` target guard | `progressive_meta` |
| `_call_tool_dispatch` or `_mcp_tool_executor` | `server_dispatch` |
| RookAgent loop or direct RookAgent execution seam | `rook_agent` |
| RookChat loop | `rook_chat` |
| PlanGraph live execution | `plan_graph` |
| `ToolDispatcher` execution seam | `tool_dispatcher` |
| Direct `_handle_spawn_agent`, `_handle_plan_and_execute`, bootstrap, learning, or explorer executor seam | `internal_handler` |

### Privacy and persistence

The event records no arguments, aliases, prompts, user content, tool-call IDs,
user or document identifiers, hashes, stack traces, geometry, target details,
or host state.

Containment reuses the existing metrics file, persistence, and inspection
machinery, but stores events in a dedicated `containment_denials` deque with
`maxlen=50`. It does not pass through ordinary `Observation` recording or
substrate JSONL. No new file, service, remote collection, or generalized event
framework is introduced.

Each Python interpreter records through its process-local canonical
`MetricsStore` returned by `get_metrics_store()`. The singleton and ring are
explicitly process-local; `metrics.json` is not treated as cross-process
synchronization or authoritative aggregation. The ring reuses that store's
configured existing path and save/load machinery on a best-effort basis.

Every test or acceptance exercise snapshots the live ring of each runtime
process participating in that exercise through its small read-only accessor.
An inaccessible participating process makes the evidence gate blocked; an MCP
process snapshot must not be presented as evidence about a separate RookChat
process. This campaign does not add cross-process locking, merging, or a
telemetry collection service.

The accessor snapshot includes the process's OS process ID and an opaque start
token generated once for that interpreter, alongside the defensive ring copy.
These fields are accessor metadata, not containment-event payload fields. Every
before/after comparison pins both values. A restart, process replacement, or
token change invalidates the evidence and requires a fresh baseline.

V1 adds no containment counters; the bounded ring is sufficient. Any later
counter proposal must remain within a fixed keyspace derived solely from the six
canonical tools and fixed origins and requires separate review.

A small read-only metrics accessor returns a defensive snapshot of the ring for
tests and live-gate before/after comparison. Recording is visible through that
accessor immediately and participates in the existing metrics save lifecycle.

The one recording attempt occurs after exact lifecycle resolution but before
tool-specific validation, argument access, implementation entry, downstream
model invocation, targeting, or host dispatch. A recording or persistence
failure may leave no ring record, but it is swallowed and never alters, delays,
or weakens the denial response. Release evidence nevertheless requires a
reachable accessor, stable process identity/start token, and exactly one
observed record for every denial probe.

Discovery omission, malformed or near-match names, skipped model calls, and
supported callers using shared safe primitives emit no containment event. The
event is operational containment evidence, not an approval, workflow event,
successful-execution record, or host receipt.

## Guidance And Documentation Cleanup

Current model-visible guidance must stop recommending contained tools or using
them as active examples. The implementation audit covers:

- RookChat prompt construction, fallback descriptions, and catalog-refresh
  advice;
- RookAgent worker and persona instructions;
- active architecture and agent documentation;
- installer-provided prompts, skills, and agent assets;
- capability groups, examples, and current tests that positively recommend a
  contained identity; and
- active work queues or runbooks that could be mistaken for current execution
  instructions.

Guidance must direct callers to rediscover the current admitted surface and use
explicit tools. It must not imply that LM9A currently executes replacement
work, that a replacement is available under readonly, or that running
`spawn_agent` refreshes the catalog.

Dated evidence, postmortems, and historical specifications remain intact unless
they present themselves as current instructions. An active-looking historical
document receives a visible supersession note rather than having its evidence
rewritten.

## Automated Verification

### Manifest and denial contract

Tests pin:

- the six canonical identities and exact dispositions;
- empty V1 aliases;
- all validation limits and invalid-manifest failure cases;
- each manifest-owned recovery string and suspended restoration criteria;
- deterministic canonical serialization and SHA-256 fingerprinting;
- exact resolution with `type(name) is str` and no coercion;
- the inner denial payload and internal envelope; and
- public MCP formatting as one `TextContent` containing
  `Error: <JSON inner payload>`.

### Discovery and cache containment

Tests prove:

- every concrete catalog and final model-projection site omits all six names;
- mapping keys and embedded `function.name` are independently checked;
- schema lists and local registrations use their specified raw identity;
- every cache load revalidates even when the lifecycle fingerprint matches;
- missing or changed fingerprints request refresh;
- refresh failure can retain only a safely revalidated older catalog;
- successful construction plus persistence failure uses the fresh in-memory
  catalog;
- unsafe or unreadable caches never merge rejected content into fallbacks;
- `list_tools()` is read-only;
- registration filtering emits no containment telemetry;
- consumer-specific policy remains intact; and
- surface snapshots are exactly 422, 425, 20, and 148 while exact absence is
  asserted independently.

### Execution bypass matrix

Every applicable concrete boundary is exercised for its contained identities.
The matrix covers public MCP, progressive meta-dispatch, direct server dispatch,
`_mcp_tool_executor`, ToolDispatcher public and inner seams, RookAgent's model
loop and direct execution methods, RookChat's model loop, PlanGraph live
execution, the private spawn/plan handlers, BootstrapRunner, bootstrap HTTP and
mock executors, the learning-agent executor, and explorer HTTP and mock
executors.

For each denied attempt, spies prove:

- the boundary-specific refusal shape is correct;
- exactly one containment recording attempt occurs and, with an operational
  sink, exactly one closed-schema ring record results;
- no arguments are decoded, inspected, copied, or logged by containment;
- no tool-specific validation, knowledge middleware, implementation, downstream
  or containment-triggered model, target, or host call occurs;
- no ordinary execution event, observation, substrate record, adaptation, or
  host receipt occurs; and
- telemetry failure leaves the same denial response.

Additional tests prove:

- repeated and sibling attempts each make one recording attempt and each append
  one record when the sink is operational;
- nested meta-dispatch records once and does not reach public redispatch;
- `rook_tools_call` formats the denial once inside `_handle_meta_tool` and
  `call_tool` returns the same `TextContent` result unchanged;
- a direct deeper-boundary call is a new attempt and records once;
- skipped RookAgent calls emit no denial event;
- RookAgent protocol history, counters, and adaptation follow the approved
  semantics;
- RookChat round accounting cannot misclassify denial as a meta-only round;
- the connected primary model may continue after denial under existing budgets
  without containment invoking any additional model;
- PlanGraph returns typed refusal with the graph unchanged and parameters
  untouched;
- malformed and near-match names retain ordinary behavior and emit no lifecycle
  telemetry;
- full, lean, and readonly all return the same tombstone for an exact identity;
- active readonly-blocked tools retain `tool_profile_blocked`;
- stale catalogs, injected registries, local handlers, and direct private calls
  cannot bypass containment;
- `BootstrapRunner` returns the pinned empty-parameter `TestResult` refusal
  before dependency handling and never marks or knowledge-records it;
- packaged mock executors never report success for a contained identity; and
- safe typed Rhino paths and shared low-level primitives remain functional after
  `rhino_execute_intent` retirement.

Telemetry tests separately force recording failure and prove one recording
attempt, zero resulting ring records, and an unchanged denial. Accessor tests pin
process ID/start-token stability and invalidate a comparison after simulated
process replacement.

The test suite does not claim to mechanically detect semantic renaming or
proxying.

### Supported-path regression

Ordinary unit and integration coverage must prove that admitted typed Rhino and
Grasshopper tools, `rhino_execute`, sanctioned script mutation,
`gh_create_script`, `gh_update_script`, `gh_set_script`, `gh_edit`, live
inspection, and safe shared Rhino primitives remain callable under their
existing profile and targeting rules.

Existing profile, progressive-discovery, dispatcher, targeting, RookChat,
RookAgent, PlanGraph, metrics, and documentation suites remain green after
intentional expectation changes.

## Authorized Live Preservation Gate

The paired live gate is release acceptance, not unattended CI. It runs only
against newly created, explicitly named scratch Rhino and Grasshopper targets
owned by the gate. Every scenario and rerun creates a fresh target; an existing
document or definition is never opened or reused. The gate never uses a
contained identity or dormant implementation.

Before authorization, a read-only preflight verifies that any prior active
Rhino document or Grasshopper definition is either absent or restorable to its
declared observable pre-state projection through today's admitted
document-lifecycle operations. Unsaved, dirty, unidentified, or otherwise
non-reopenable user state blocks the gate before scratch creation. The gate does
not add new document-lifecycle authority to make restoration possible.

Immediately before each scenario's first host mutation, the operator grants
explicit authorization covering the named scratch target and the complete
bounded mutation, verification, and restoration sequence. Authorization cannot
carry across Rhino and Grasshopper targets or across reruns. Target or state
drift requires reauthorization.

The authorization may cover creation and disposal of the named scratch target
as part of its declared lifecycle. It does not authorize mutation of the user's
active work.

### Rhino scenario

The Rhino scenario:

1. records the prior active-document identity;
2. creates a fresh named gate-owned scratch document for this run;
3. pins the observable pre-state projection before the test mutation;
4. uses only admitted explicit Rhino tools to apply a uniquely marked,
   deterministic geometry mutation;
5. exercises the supported typed or scripted route that preserves the safe
   capability formerly shared beneath `rhino_execute_intent`;
6. verifies observable geometry, object identity/attributes, document state,
   and the expected result;
7. executes only the authorized restoration path; and
8. verifies the declared pre-state projection and scratch-document lifecycle
   are restored, including the prior active-document identity.

The Rhino pre-state projection includes the prior active-document identity,
scratch-document lifecycle, and explicitly declared relevant document and
object state. It does not imply equality of timestamps, undo-stack internals,
caches, or other volatile state unless the scenario explicitly declares and
controls them.

### Grasshopper scenario

The Grasshopper scenario:

1. records the prior active Grasshopper definition and canvas identity, or
   verifies that no definition or canvas is active;
2. creates a fresh named gate-owned scratch definition for this run;
3. pins its observable pre-state projection;
4. uses live discovery and explicit `gh_edit` operations to place a Number
   Slider and Sphere;
5. explicitly configures the slider range and value and wires it to the Sphere;
6. solves the definition and verifies component identities, settings, wires,
   topology, outputs, solve state, and errors;
7. executes only the authorized restoration path, including disposal of the
   scratch definition; and
8. restores and verifies the prior active definition and canvas identity, or
   the verified prior absence, together with the declared pre-state projection
   and scratch-definition lifecycle.

The Grasshopper pre-state projection includes the prior active definition and
canvas identity or verified absence, component identities and settings, wires,
topology, errors, and any other document state declared before mutation. It does
not imply equality of solver counters, timestamps, undo-stack internals,
volatile caches, or other uncontrolled state.

### Gate failure semantics

Each scenario snapshots the dedicated containment-denial ring in every runtime
process participating in that scenario before and after and requires zero new
events in all of them. This proves the supported workflow did not route through
a contained identity.

On failure, the gate stops all further forward mutation. If ownership remains
certain, it enters only the already authorized restoration path. If ownership
becomes ambiguous, it performs no further mutation and preserves evidence.
Passing always requires verified restoration; attempted cleanup is never
sufficient.

Unexpected user state, a wrong target, an unverifiable result, unexpected
Grasshopper warnings or errors, restoration mismatch, or containment-telemetry
activity fails the scenario and preserves diagnostic artifacts.

### RookVision gallery preservation

The runtime is disposable. The RookVision gallery is not.

The protected root is `%APPDATA%\Rook\artifacts`, as defined by
`RookPaths.ArtifactsRoot`. Existing RookVision artifacts are non-disposable and
never part of installation, withdrawal, or cleanup. Containment acceptance and
withdrawal tooling never treats their contents as mutation, cleanup, or payload
inputs. Their path, type, and file-size inventory is read-only acceptance
evidence. No campaign code deletes, renames, moves, truncates, overwrites, or
recursively cleans the protected root, any of its descendants, or
`%APPDATA%\Rook` as a parent. Acceptance evidence is stored elsewhere.

Gallery verification is phase-aware because normal Rook startup performs
established gallery maintenance:

- With Rhino and Rook quiesced, the inventory immediately before and after
  installation must have exact path, type, and file-size equality.
- During live acceptance, every pre-existing non-transient path must remain
  present with the same type, and every pre-existing non-`manifest.json` file
  must retain its size. Current startup reconciliation or backfill may add only
  `poster.jpg`, `start_frame.jpg`, or `end_frame.jpg` beneath a pre-existing
  finalized artifact directory; it may not add a directory. Existing startup
  maintenance may change `manifest.json` sizes in those pre-existing artifact
  directories. Every other new gallery path fails the gate.
- With Rhino and Rook quiesced, the inventory immediately before and after
  withdrawal or uninstallation must again have exact path, type, and file-size
  equality.

Inventory never follows reparse points. The only excluded pre-existing residue
is the deletion residue already defined by `ArtifactStore`: `*.deleting.tmp`
trees and empty GUID directories. Real gallery-file contents are never read or
hashed. This is a deletion and truncation safeguard, not byte-integrity
certification.

Any mismatch or unverifiable inventory produces
`artifact_preservation_failed`, blocks publication, and stops forward testing.
The gate performs no gallery repair. If bounded runtime withdrawal remains
safe, it may continue, but it must remain categorically outside the protected
root.

A focused regression uses a synthetic sentinel tree and verifies exact sentinel
bytes through installation, the same-application legacy-log migration,
failed-candidate withdrawal, and uninstallation.
No real-gallery hashing, backup, restoration, artifact-management subsystem, or
parent-directory cleanup is added.

## Rollout And Release Posture

### Atomic campaign boundary

The shipped containment change contains only:

- the lifecycle manifest and exact resolver;
- catalog filtering, load-time revalidation, and the startup refresh path;
- shallow early-return guards at the inventoried execution boundaries;
- the dedicated bounded containment-denial ring and read-only accessor;
- removal of the local semantic intent handler from production registration;
- current guidance cleanup; and
- the single installer-level legacy-log migration described below.

Exhaustive source tests, installed-runtime probes, and the two authorized live
scenarios are campaign evidence, not public runtime features. Release-only
acceptance and live-gate code resides outside the public `rook-mcp` package.

These parts ship together. A candidate must never filter discovery while an
identified dispatch path remains executable, or deny execution while leaving a
contained identity advertised.

### Legacy uninstall-log migration

The existing Rook installer retains its exact public `AppId`, per-user
privilege mode, x64 install mode, application directory, and uninstall-files
directory. Its `[Setup]` section adds exactly:

```ini
UninstallLogMode=overwrite
```

This is an intentional legacy-log migration, not an installer redesign. A
successful eligible same-application upgrade replaces rather than appends the
prior uninstall log, so recursive `%APPDATA%\Rook` deletion actions shipped by
older public installers cannot remain in the upgraded public uninstall
authority. Ordinary users require no manual uninstall or pre-cleanup. The
directive remains until a separately reviewed migration proves every supported
upgrade path safe. `post_install.py`, the current uninstall cleanup, the public
`AppId`, and all other installer behavior remain unchanged by this campaign.

One bounded Windows PowerShell 5.1 regression generates and compiles a
disposable Inno Setup 6 legacy/candidate pair. The pair uses one fresh synthetic
AppId shared only by those two fixture versions, identical privilege/bitness and
literal test-owned install/uninstall-log paths, and no real Rook AppId,
known-folder constant, registry target, runtime root, configuration path, or
gallery path. The legacy fixture records an unsafe recursive deletion against
only a synthetic gallery sentinel and omits the directive so Inno's documented
append default applies. The candidate fixture projects the reviewed production
`UninstallLogMode=overwrite` directive and otherwise supplies only the minimal
uninstall path needed for this proof.

Fixture generation reads only the raw `UninstallLogMode` assignment from the
production `RookSetup.iss` `[Setup]` section. Before implementation, no
assignment produces no candidate-fixture directive and therefore the real
append-behavior red. After implementation, exactly one assignment whose value is
exactly `overwrite` is projected verbatim. Any other value, duplicate, malformed
section placement, or independent hardcoded fixture mode is an infrastructure
failure and cannot satisfy either red or green.

The control and preservation sentinels share an ordinary non-reparse synthetic
root that is a sibling of, not equal to or beneath, every candidate application,
runtime, configuration, Temp-cleanup, setup-delete, uninstall-delete, and
`post_install.py` cleanup target. The generated candidate is statically checked
not to name that root or any ancestor of it. Only the legacy fixture's exact
unsafe entry targets it. Final test-root teardown occurs only after every
preservation assertion and is not candidate cleanup evidence.

The regression first installs the legacy fixture, creates a disposable control
sentinel, performs an ordinary legacy uninstall, and requires that sentinel to
be deleted and the synthetic registration/log authority to be removed. It then
reinstalls the same compiled legacy fixture, creates a separate byte-pinned
preservation sentinel, installs the overwrite candidate, and requires the
candidate `DisplayVersion` and registered uninstall path, a changed synthetic
`unins000.dat` digest, and exactly one current app-root uninstaller/log identity.
Ordinary candidate uninstall must preserve the second sentinel exactly and end
with no registered or app-root legacy uninstaller/log authority. The real Rook
uninstall registration remains unchanged throughout; this synthetic regression
adds no new read or hash of the real gallery, whose separate phase-aware
coordinator checks remain authoritative.

Fixture installer, uninstaller, and private-Python process environments are
constructed case-insensitively from a scrubbed copy. They remove inherited
`PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`,
`DSPY_CACHEDIR`, `CHIRP_HOME`, every `ROOK_*` name, `APPDATA`, `LOCALAPPDATA`,
`USERPROFILE`, `HOMEDRIVE`, `HOMEPATH`, `HOME`, `TEMP`, `TMP`, `TMPDIR`, `PATH`,
and `NoDefaultCurrentDirectoryInExePath`. They then set only the test-owned
profile/AppData/LocalAppData/home-drive/home-path values, the test-owned Temp
child beneath the validated real known-folder LocalAppData `Temp`,
`PYTHONNOUSERSITE=1`, present-but-empty `PATH`, and
`NoDefaultCurrentDirectoryInExePath=1`; `HOME` remains absent. Before unchanged
`post_install.py --uninstall` may continue, a test-only startup guard requires
`Path.home()`, `get_runtime_root()`, `APPDATA`, `tempfile.gettempdir()`, the
private interpreter and working directory, and every configuration/runtime
destination the script can touch to resolve beneath canonical non-reparse
synthetic roots. Any mismatch exits before tool lookup or cleanup. No real Rook
configuration, runtime, registry, or gallery path is used as a mutation target
and safety never relies on detecting damage afterward.

The regression launches both real synthetic Inno uninstallers through the
production bounded observer and proves the actual original-to-TEMP-clone
identity and completion sequence, the copied private-CPython working directory
and unchanged `post_install.py --uninstall` path, and zero hostile `claude.exe`
tripwire hits.
The fixture is generated beneath one canonical non-reparse test-owned Temp root;
all generated `.iss` paths are literal and evidence remains outside every
synthetic deletion target. Compile, install, observer, or cleanup ambiguity is a
hard failure with no skip or Python-process substitute. Failure handling may
terminate only recorded fixture-owned PID/creation identities and may remove
only the proven synthetic registry key and root; it never invokes, deletes, or
repairs real Rook or gallery state. Delayed Inno TEMP self-delete residue is not
treated as registered or app-root uninstall authority.

The TDD red uses this same full fixture before the production directive exists.
It must reach the ordinary synthetic candidate uninstall and fail specifically
because the synthetic sentinel was deleted by retained legacy authority;
compiler, installer, observer, path, or cleanup failure does not satisfy that
red. After the one-line production migration is added, the same fixture must
reach the same point and preserve the sentinel exactly.

### Normal release sequence and artifact identity

Containment acceptance is additive to the existing release process. Existing
Rhino, Rhino.Inside/Revit, wheelhouse, FFmpeg, installer, smoke, and release
artifact validation remains mandatory and is not reimplemented by this
campaign.

The release sequence is:

1. merge the reviewed containment change to `main` without publishing;
2. create the normal version-bump release branch from updated `main`, complete
   and merge its reviewed release PR, then designate the resulting
   version-bumped `main` commit as the expected release SHA;
3. use the normal release process to build the unpublished installer for that
   exact SHA and version, without installing or publishing it yet;
4. start the thin containment coordinator with the expected release SHA,
   version, and installer path; it recomputes the installer digest, validates a
   fresh diagnostics root, quiesces the required processes, and records the
   pre-install gallery, environment, and uninstall-state baselines;
5. have the coordinator launch that installer with the sanitized environment,
   then, before any host starts, require exact post-install gallery equality;
6. run the existing standalone Rhino and Rhino.Inside/Revit smoke workflows
   inside the same acceptance session, beginning the live gallery phase; those
   workflows write the external smoke manifest, which is passed unchanged to
   the existing release-artifact validator; that validator retains its normal
   Git and provenance checks and emits the release manifest;
7. have the coordinator verify installed provenance and manifest identity, then
   finish the discovery, 36 transport, 29 representative internal, and paired
   live gates; and
8. publish the normal release asset set, including the independently validated
   FFmpeg source bundle and manifest, while publishing the exact accepted
   installer, smoke-manifest, and release-manifest bytes without rebuilding,
   rewriting, or repacking those three files.

The pre-install gallery baseline therefore precedes the first candidate
installation and every normal smoke launch. The post-install equality check
precedes standalone Rhino and Rhino.Inside/Revit startup. Those normal smoke
launches and the later paired live gates all occur inside the phase-aware live
gallery interval.

The containment coordinator consumes artifacts. It performs no Git, merge,
versioning, build, publication, or installer-construction operation.

After the normal smoke and release manifests exist, but before containment
discovery or denial probes begin, the coordinator requires equality across:

- the recomputed installer SHA-256 and the release-manifest installer SHA-256;
- the expected release SHA and the `git_sha` or `rook_git_sha` recorded by the
  release manifest, smoke manifest, packaged runtime manifest, and installed
  runtime manifest;
- the expected Rook product version and only these Rook product-version fields:
  release-manifest `version`, smoke-manifest `rook_version`, runtime-manifest
  `release_version`, the `rook-mcp` wheel version and metadata, the Rook
  lockfile pin, and the existing native and managed `X.Y.Z.0` file versions;
- the packaged and installed runtime-manifest bytes and SHA-256, together with
  the runtime-manifest identity recorded in install state;
- each recomputed wheel SHA-256 and its runtime-manifest declaration;
- the exact packaged Rook wheel and the installed Rook package files described
  by its wheel `RECORD`; and
- the installed Rook venv root and the origins of every loaded `rook.*` module.

Python, Rhino, Revit, Rhino.Inside, Chirp, third-party wheel, and other component
versions continue to use their existing independent validation contracts. This
campaign adds no Rook release-version field to install state.

For wheel comparison, every hash-and-size-bearing `rook/` entry in the packaged
wheel `RECORD` must match its installed file. Missing, changed, or unexpected
installed Rook source or package-data files fail acceptance; interpreter-created
`__pycache__` directories and `.pyc` files are ignored. Acceptance does not
force-import dormant modules merely to enlarge this proof. Every `rook.*` module
that a probe loads must originate beneath the verified installed package root.

The coordinator computes SHA-256 over the exact external smoke-manifest and
release-manifest bytes. It also requires semantic JSON equality between the
external smoke manifest and the release manifest's embedded `smoke` object.
The passing record binds the expected release SHA, version, installer digest,
smoke-manifest digest, and release-manifest digest. Publication independently
confirms that it is promoting those exact three files while retaining every
other asset required by the normal release contract.

### Thin deployed-runtime acceptance

Verification exercises the deployed candidate, not only source imports. Within
the single release sequence above and before installed containment probes begin,
the coordinator:

1. quiesces existing Rook MCP, RookChat, and internal-agent processes that may
   retain old registrations;
2. proves no old agent or plan tasks remain active;
3. installs the candidate runtime exactly once with the sanitized environment;
4. runs the existing normal smoke and manifest-production steps;
5. restarts containment consumers against that candidate and allows normal startup
   refresh without deleting a safely revalidated cache; and
6. confirms the six names are absent from actual model-visible surfaces before
   running the paired live gate.

Before installation, the coordinator creates a sanitized copy of the required
Windows process environment. Case-insensitively, it removes inherited
`PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`,
`DSPY_CACHEDIR`, `CHIRP_HOME`, and every key beginning with `ROOK_`, then adds
only code-owned `PYTHONNOUSERSITE=1` among those scrubbed controls for the
installer launch. Required ordinary Windows environment values remain. The
coordinator launches the installer itself with that environment. Inno Setup,
`post_install.py`, and every post-install descendant inherit the sanitized
boundary; sanitation does not begin inside Python after startup hooks could
already execute. Production post-install code may establish only its existing
validated code-owned runtime values for descendants.

Every later installed-Python parent and child applies the same case-insensitive
scrub. It then sets code-owned `PYTHONNOUSERSITE=1`, validated installed values
for `ROOK_INSTALL_ROOT`, `ROOK_DATA_DIR`, `ROOK_MODE=release`, and
`ROOK_DSPY_RESTRICT_PICKLE=1`, plus a validated code-owned `DSPY_CACHEDIR` and
optional code-owned `CHIRP_HOME`. A profile probe may additionally set its exact
`ROOK_MCP_TOOL_PROFILE`; only interactive discovery may set
`ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1`. `PYTHONUSERBASE`, `DSPY_MODEL`,
and all other caller-supplied source, model, cache, target, process, document,
bridge, harness, or profile overrides remain absent.

Every installed Python acceptance-probe process reports an effective `sys.path`
containing no canonical repository or worktree root, and every loaded `rook.*`
module must originate beneath the verified installed package root. Child
working directories and the acceptance output directory are fresh and outside
the checkout, installation roots, and RookVision gallery. The installer chain
does not require new production `post_install.py` reporting. A focused
startup-chain regression instead proves through inherited environment and
user-site tripwires that the sanitized installer-to-`post_install.py` descendant
and Python-grandchild chain cannot observe the removed variables or execute
user-site startup hooks.

Discovery acceptance retains the exact current snapshots: default full `422`,
interactive full `425`, lean `20`, and readonly `148`. Every surface must also
omit the six exact contained identities.

### Installed transport probes

Installed-runtime acceptance also proves execution containment, not only
discovery omission. It launches a fresh candidate process for each `full`,
`lean`, and `readonly` profile under the installed-child policy above.

For every profile, the harness invokes all six contained identities through:

- the real public MCP transport; and
- the real public `rook_tools_call` transport with each identity as its raw
  target name.

That is 36 installed transport probes: six identities, three profiles, and two
ingresses. Every direct probe must return the exact public tombstone and its
telemetry record must use `public_mcp` origin. Every progressive probe must be
formatted exactly once by `_handle_meta_tool`, returned unchanged by
`call_tool`, and use `progressive_meta` origin in telemetry. Profile choice must
not change the payload.

The installed transport harness arms fail-fast spies at tool-specific
validation, dormant implementation, downstream model, target-resolution, and
host-dispatch seams for these public probes. Any spy entry fails the probe. The
spies instrument installed candidate modules and do not substitute workspace
implementations.

Each probe takes an immediately adjacent before/after telemetry snapshot from
the participating process. The accessor must be reachable, its process ID and
start token must remain identical, and the delta must contain exactly one
matching ring record. A restart, replacement, inaccessible accessor, missing
record, duplicate record, wrong origin, or malformed payload blocks acceptance.
Per-probe comparison prevents the 50-entry ring bound from hiding earlier
records in a larger batch.

### Representative installed internal probes

Source tests retain the exhaustive six-identities-by-boundary bypass matrix.
Installed acceptance does not repeat that Cartesian product. It runs one
representative denial through each current unique internal execution seam.

The reviewed release tooling pins this current 29-seam acceptance snapshot as
literal code-owned data; it is not discovered from the candidate under test:

1. `server._call_tool_dispatch`
2. `server._mcp_tool_executor`
3. `ToolDispatcher.dispatch`
4. `ToolDispatcher._dispatch_inner`
5. `ToolDispatcher._call_local`
6. `ToolDispatcher._dispatch_with_knowledge`
7. `RookAgent._run_loop`
8. `RookAgent._execute_tool`
9. `RookAgent._execute_local_tool`
10. `ChatRunner.run_turn`
11. `rook.agent.plan_graph_live.apply_live_producer_node`
12. `BootstrapRunner.run_test`
13. `BootstrapRunner._mock_executor`
14. `bootstrap.HttpExecutor.execute`
15. `bootstrap.create_mock_executor.callable`
16. `learning.create_tool_executor.callable`
17. `Investigator.investigate_tool`
18. `Investigator.investigate_gap`
19. `Investigator.investigate_workflow`
20. `Investigator._run_experiment`
21. `HybridInvestigator.investigate_tool`
22. `HybridInvestigator.investigate_gap`
23. `LearningSession.run_investigation_cycle.tool_target`
24. `explorer.HttpExecutor.execute`
25. `explorer.HttpExecutor.execute_sync`
26. `explorer.MockExecutor.execute`
27. `explorer.MockExecutor.execute_sync`
28. `server._handle_spawn_agent`
29. `server._handle_plan_and_execute`

Each seam is paired with one literal representative contained identity in the
reviewed tooling; the assignments collectively cover all six identities. The
candidate cannot select or rewrite the inventory or assignments. `29` is a
reviewed snapshot of the current implementation, not a timeless platform
constant; changing the concrete boundary inventory requires review of this
release evidence. The rewritten reviewed implementation plan and the external
release tooling both pin the 29 representative identity assignments explicitly.

Every representative probe verifies the boundary-specific refusal shape, one
immediately adjacent containment event in the same process ID and start token,
the correct fixed origin, and zero downstream validation, implementation,
model, target, HTTP, host, observation, adaptation, or receipt entry. The
RookAgent and RookChat probes include their model-visible protocol assertions;
they do not create a duplicate installed suite.

The representative installed probe set is non-mutating and does not require an
open Rhino or Grasshopper target. It precedes the separately authorized
live-preservation scenarios.

### Thin coordinator and evidence

The coordinator begins with the pre-install baseline and sanitized installation
phase. After the existing smoke workflow and unchanged release-artifact
validator succeed, the already-running coordinator enters installed provenance,
the four discovery snapshots, the complete 36 transport probes, the pinned 29
representative internal probes, and the two authorized live scenarios. It adds
no independent Git, build, versioning, publication, smoke-schema, or
release-validation logic and does not become a generalized validation framework.

It uses a fresh output directory and writes one small digest-bound success
record atomically only after every required result passes. Focused tests cover
pre-install baseline ordering, immutable uninstall-state ownership, the Inno
same-application overwrite migration and real TEMP-clone completion barrier,
installer descendant/grandchild sanitation, provenance or manifest-semantic
mismatch, incomplete 36- or 29-probe sets, gallery mismatch, ambiguous ownership
or reparse preflight, withdrawal failure, and refusal to produce a passing
record after any failure.

### Release blockers

Release is blocked if any contained identity is discoverable or executable; any
denied invocation reaches tool-specific validation, implementation, downstream
model/target/host execution, ordinary observation or adaptation, or host-receipt
generation; telemetry violates its closed contract; either supported live
workflow fails; restoration is unverified; or supported workflows generate
containment events. Release is also blocked if the exact installer legacy-log
migration is absent or changed, or if the synthetic same-application
upgrade/uninstall regression fails.

If verification fails before publication, the candidate is not published,
forward testing stops, and concise diagnostics are preserved outside the
RookVision gallery. The diagnostics root must also be outside all four fallback
roots, every current normal-uninstaller deletion root,
`%LOCALAPPDATA%\Rook\logs`, and `%TEMP%\rook`. No automatic rollback or
restoration of an earlier Rook installation is attempted. The runtime is
disposable.

Before invoking the normal uninstaller or any fallback cleanup, the operator
must close Rhino, Revit, Claude, Codex, and every other configured Rook launcher.
The coordinator gracefully closes only hosts certainly owned by the current
gate. It stops a candidate-owned process only when both its PID and creation
identity match the process recorded by the gate. It never force-kills a user
host. Ambiguous process ownership, enumeration, or closure skips destructive
withdrawal and produces a failed/manual-withdrawal result.

Before candidate launch, while Rook is quiesced, the coordinator records a
non-following, case-insensitive inventory of immediate entries beneath the exact
canonical `%LOCALAPPDATA%\Rook\app` root matching `unins*.exe`, `unins*.dat`,
or `unins*.msg`. An absent app root is an empty baseline. An uninspectable or
reparse app root, or an uninspectable or reparse matching entry, blocks
installation. Ordinary readable non-reparse matches are inventoried and may
proceed through installation, but the baseline is immutable for the session.
If any match existed before launch, any later
candidate failure returns `manual_withdrawal_required`; the coordinator invokes
neither the normal uninstaller nor fallback, configuration, or startup-authority
cleanup. Candidate overwrite or removal of pre-existing state cannot clear this
disqualifier. The coordinator never reads, parses, or rewrites an uninstall log.
This conservative failed-session rule remains independent of the installer-level
overwrite migration: coordinator refusal protects an ambiguous acceptance
failure, while the migration protects an ordinary user's later uninstall after
a successful public upgrade. Coordinator refusal alone is not public upgrade
protection.

Automatic normal uninstallation additionally requires an empty pre-install
uninstall-state baseline and an unambiguous session-local empty-to-created
transition after the exact candidate process exits: ordinary non-reparse
`unins000.exe` and `unins000.dat`, at most the matching `unins000.msg`, and no
other matching state. Immediately before launch, a fresh inventory must equal
the recorded candidate-created path, type, and size inventory. Missing, extra,
mismatched, changed, reparse, or uninspectable state produces
`manual_withdrawal_required` with no destructive action. Uninstall state never
establishes installer phase, process identity, or
`verified_partial_installation`.

Aside from the setup-time legacy-log overwrite above, normal withdrawal uses the
existing uninstaller without redesigning its current runtime and configuration
cleanup. For that supervised launch, the coordinator
derives LocalAppData through the Windows known-folder API, validates its existing
`Temp` child and every intervening component as ordinary and non-reparse, removes
inherited `TEMP`, `TMP`, and `TMPDIR` case-insensitively, and sets all three to
that exact root. No caller, candidate, or ambient environment value may select
the clone root.

A bounded process observer starts before the uninstaller launch. It must attach
a live process handle to exactly one new
direct child of the recorded uninstaller identity whose creation does not
predate its parent and whose canonical ordinary non-reparse executable is
strictly beneath the coordinator's already validated code-owned Temp root. The
coordinator waits for the original uninstaller identity and then for that exact
TEMP-clone identity to exit before any post-withdrawal check or fallback. The
original exit code remains the uninstall status; clone exit is only the
completion barrier. Zero, multiple, ambiguous, raced, outside-Temp, reparse,
unattachable, reused, or timed-out clone observations produce
`manual_withdrawal_required` with no further destructive action. The later Rook
process preflight cannot substitute for this barrier, and no generalized
process framework is added.

The focused withdrawal regression observes the actual private-Python
`post_install.py --uninstall` process launched by the unchanged Inno `Exec`
path. Inside that process, it requires exactly one case-insensitive `PATH` entry
whose value is the empty string, exactly one
`NoDefaultCurrentDirectoryInExePath` entry whose value is `1`, canonical
equality between the effective working directory and the validated private
interpreter's parent, `shutil.which("claude") is None`, and an executable
`claude.exe` tripwire in that effective working directory that produces no hit.
For the pinned CPython 3.11.9 runtime, present-but-empty `PATH` is the operative
lookup suppression; `NoDefaultCurrentDirectoryInExePath=1` remains
defense-in-depth and future-runtime policy.

If emergency cleanup is required afterward,
the coordinator's fallback deletion allowlist is closed to exactly four roots
derived from Windows known-folder APIs:

- `%LOCALAPPDATA%\Rook\app`
- `%LOCALAPPDATA%\Rook\python`
- `%LOCALAPPDATA%\Rook\venv`
- `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`

Before either the normal uninstaller or fallback cleanup, a read-only preflight
derives every affected root from Windows known-folder APIs and checks every
intervening component below its known-folder anchor plus every descendant that
the operation would traverse. Any reparse point, inspection failure, or identity
ambiguity blocks destructive withdrawal. The preflight and cleanup never follow
reparse points.

Every fallback root must also have the exact expected canonical identity. The
fallback never accepts a caller-, candidate-, or manifest-supplied deletion path
and never broadens deletion after an error. The parent directories
`%LOCALAPPDATA%\Rook` and `%APPDATA%\Rook`, the protected
`%APPDATA%\Rook\artifacts` root, persistent data, configuration outside the
allowlist, and all other paths are categorically excluded.

After withdrawal, the coordinator verifies candidate-process absence and every
configured MCP, RookChat, internal-agent, native-plugin, and managed-plugin
startup authority, plus gallery preservation. If cleanup or verification is
uncertain, it reports failed/manual withdrawal and stops. It does not claim
ownership, delete more broadly, produce a passing record, or create durable-hold
or rollback machinery.

### Isolation

Implementation remains isolated in:

- Worktree: `C:/Users/aryan/source/repos/Rook/.worktrees/gh-execute-intent-root-fix`
- Branch: `codex/gh-execute-intent-root-fix`

No further implementation, pruning, or release-tooling work begins until this
amended specification and its rewritten implementation plan receive user and
senior-reviewer approval.

## Explicit Exclusions

The following are separate future decisions:

- a universal agent/tool authorization or executor framework;
- runtime active-catalog, schema/build-identity, or cache-freshness
  fingerprints; the external release artifact SHA-256 remains required;
- cache generations or quarantine machinery;
- a general malformed-registry, name-collision, or schema-freshness redesign;
- broad RookAgent, RookChat, or PlanGraph outcome redesign;
- redesigning `gh_edit` transactionality, readiness, rollback, or verification;
- mechanically detecting semantic proxying;
- integrating LM9A as a live replacement executor;
- permanent deletion of every dormant implementation;
- evaluating or restoring suspended semantic tools; and
- changing public tool names beyond the six lifecycle tombstones;
- an alternate candidate builder or installer workflow;
- a generalized release validator, immutable evidence store, durable-hold
  system, or rollback verifier;
- requiring a VM, disposable OS profile, or isolated user gallery;
- hostile-workstation or general build-hermeticity certification; and
- gallery backup, repair, restoration, or artifact-management machinery.

## Acceptance Criteria

- One immutable manifest is the only lifecycle source of truth for the six
  exact identities.
- All six identities are absent from every public, progressive, cached,
  injected, local, agent, and model-visible catalog projection.
- Every catalog load revalidates exact lifecycle state regardless of its stored
  fingerprint.
- A failed refresh may retain a safely revalidated older catalog without
  introducing cache generations or quarantine machinery.
- Every identified public and internal execution boundary denies exact
  contained identities before tool-specific validation or argument access.
- Full, lean, and readonly return the same stable tombstone for each exact
  contained identity; active readonly profile behavior remains otherwise
  unchanged.
- Every denied attempt makes exactly one privacy-preserving recording attempt;
  an operational sink produces exactly one event in its process-local bounded
  ring, while sink failure cannot weaken denial.
- Denied attempts never reach implementations, downstream or
  containment-triggered models, target resolution, hosts, ordinary observations,
  adaptive history, substrate JSONL, or host receipts.
- RookAgent, RookChat, PlanGraph, internal dispatcher, and transport protocol
  behavior matches the boundary-specific contracts in this design.
- The local `rhino_execute_intent` handler and active guidance recommending
  contained identities are absent from production surfaces.
- Supported explicit Rhino and Grasshopper operations preserve their existing
  profile, targeting, and execution behavior.
- The authorized Rhino and Grasshopper live scenarios both produce the expected
  host result, verify their declared observable state, restore that state, and
  generate zero containment events.
- Quiesced installation and withdrawal preserve the exact observable
  RookVision inventory; live acceptance preserves existing non-transient assets
  under the phase-aware maintenance allowances.
- The thin coordinator begins before the first candidate installation, records
  the quiesced gallery baseline, launches the installer with the sanitized
  environment, and verifies exact post-install gallery equality before normal
  Rhino or Rhino.Inside/Revit smoke begins.
- The accepted installer is built by the normal release process from the final
  merged, version-bumped `main` SHA; its Rook product-version fields, manifests,
  wheel, install state, installed package files, venv, loaded module origins,
  and source-free effective `sys.path` satisfy their explicit contracts.
- The deployed candidate is accepted only after old processes and tasks are
  quiesced, actual installed model-visible surfaces match `422/425/20/148` and
  omit all six names, the complete 36 transport probes pass, and the pinned 29
  representative internal probes pass alongside the exhaustive source matrix.
- Every telemetry baseline pins the participating process ID and start token;
  restart or replacement invalidates the evidence.
- The thin coordinator emits one atomic success record only after all required
  evidence passes. It binds the exact installer, external smoke-manifest, and
  release-manifest byte digests, and the embedded smoke object is semantically
  equal to the external smoke manifest.
- Publication preserves the normal release asset set and promotes the exact
  three accepted installer/smoke/release-manifest files without rebuild,
  rewrite, or repack.
- Failed candidates are withdrawn without touching the gallery. Destructive
  withdrawal requires an empty pre-install uninstall-state baseline, an
  unambiguous candidate-created uninstaller pair, unambiguous process ownership,
  the TEMP-clone completion barrier, and a no-reparse preflight; fallback cleanup
  is limited to the closed four-root allowlist, and uncertain withdrawal remains
  a manual failure.
- The implementation remains within this campaign's explicit exclusions.
