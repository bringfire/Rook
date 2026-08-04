# ChatRunner MCP Capability-Parity Bridge Design

**Date:** 2026-08-04
**Baseline:** `8baf325a459ec9bb53cae24b1af0fab452b3001e`
**Status:** Proposed prerequisite to the explicit-skill local top-level agent qualification

## Purpose

Make `ChatRunner` a real client of Rook's existing canonical MCP progressive-disclosure gateway:

```text
rook_tools_ls
rook_tools_search
rook_tools_read
rook_tools_call
```

This is a bounded foundational slice. It gives the existing ChatRunner model/tool loop policy-controlled access to the existing MCP capability surface without copying hundreds of tools into `ToolDispatcher` or adding individual ChatRunner routes for every missing capability.

The explicit-skill local-agent qualification remains paused until this bridge is implemented, independently reviewed, merged, and deployed.

## Evidence and current mismatch

`ChatRunner` already owns the interactive model loop, conversation state, streaming events, direct tool execution, and its older `request_tools` / `search_tools` progressive-disclosure surface.

The reviewed `execute-grasshopper` skill also relies on the canonical MCP gateway when an admitted tool is hidden. Its method requires capabilities including `gh_library` and `gh_batch_component_info`. Both are already present and dispatchable through the MCP server's capability index and `rook_tools_call`, but neither is generally available through ChatRunner's direct `ToolDispatcher` surface.

The MCP server already owns:

- the complete live tool catalog;
- capability-index construction;
- profile-scoped listing, search, and read;
- target schema validation;
- meta-tool recursion refusal;
- contained-tool refusal;
- dispatchability checks;
- Rhino targeting and host policy;
- ordinary target dispatch;
- target observations and receipts; and
- MCP `TextContent` to agent-result conversion.

Reimplementing any of those behaviors in ChatRunner would create a second capability system. Adding individual Grasshopper routes would begin an open-ended parity backlog.

## Architectural boundary

The bridge is:

```text
ChatRunner
-> canonical rook_tools_* schemas
-> injected scope-bound canonical executor
-> existing MCP capability index and policy path
-> existing target implementation, observation, and receipts
```

Ownership remains explicit:

| Concern | Owner |
|---|---|
| Model loop, Chat events, conversation messages | `ChatRunner` |
| Chat-local authority ceiling | `ChatRunner` construction |
| Four gateway names and schemas | one shared canonical MCP contract source |
| Active MCP profile | existing MCP profile resolver |
| Effective authority | canonical MCP gateway executor |
| Capability index and target schema | existing MCP server |
| Targeting, validation, dispatch, observations, receipts | existing `call_tool()` path |
| MCP-to-agent result shape | existing canonical conversion |

`ChatRunner` does not import `rook.server`. The production Chat service composition root supplies the real canonical executor. Tests may inject a no-contact executor with the same callable boundary.

## Single-sourced schemas

The four existing MCP `Tool` definitions become available from one lightweight code-owned schema source. The MCP server consumes that source when building its live tool list. ChatRunner consumes the same source through the existing MCP-to-LiteLLM schema conversion.

There is no second hand-written ChatRunner version of the schemas.

The visible ChatRunner schemas must equal the current normalized LiteLLM projection of the canonical MCP definitions, including names, descriptions, properties, required fields, and closed-object normalization.

Schema exposure is capability-dependent:

```text
canonical executor supplied
-> expose all four rook_tools_* schemas

canonical executor absent
-> expose none of the rook_tools_* schemas
```

A bare `ChatRunner` must never advertise a tool it cannot execute.

The existing direct tools and existing `request_tools` / `search_tools` schemas remain unchanged.

## Authority intersection

ChatRunner's `tool_access` value is a code-owned local ceiling fixed when the runner is constructed. It is exactly one of:

```text
full
readonly
```

The model cannot provide, modify, or override this value in any gateway request.

The MCP process continues to resolve its active profile through the existing canonical profile resolver. The canonical gateway executor computes effective authority for every invocation:

```text
effective authority
= intersection of fixed ChatRunner tool_access and active MCP profile
```

For the existing profiles, the concrete rule is:

```text
ChatRunner readonly OR MCP readonly
-> effective profile readonly

otherwise
-> retain the active MCP profile
```

Retaining the active profile preserves today's `lean` advertisement behavior while never weakening a read-only wall.

The required equations are:

```text
ChatRunner readonly + MCP full     -> readonly
ChatRunner full     + MCP readonly -> readonly
ChatRunner full     + MCP full     -> full
```

The executor passes this explicit effective profile into the existing canonical meta-tool policy path. ChatRunner does not copy `PUBLIC_READONLY_TOOL_NAMES`, `tool_blocked()`, the capability index, or target validation.

For `rook_tools_call`, the existing meta handler performs its guard sequence under the effective profile before re-entering `call_tool()` for the target. The target then retains the normal MCP process wall, targeting, host policy, dispatch, observation, and receipt behavior. Either layer may make authority more restrictive; neither can widen it.

Discovery is scoped by the same effective profile. A read-only ChatRunner cannot use `rook_tools_ls`, `rook_tools_search`, or `rook_tools_read` to enumerate hidden write capabilities while the process runs full.

## ChatRunner dispatch behavior

The four gateway names are ChatRunner-intercepted capabilities only when the canonical executor exists.

For a gateway call, ChatRunner:

1. decodes the model's tool arguments using its existing tool-call handling;
2. passes the exact decoded name and arguments to the injected canonical executor;
3. awaits exactly one executor call;
4. retains the converted result in the existing conversation tool message;
5. emits the existing `tool_start` and `tool_result` events; and
6. continues the existing model loop.

ChatRunner performs no gateway-specific target lookup, argument validation, profile check, target selection, result interpretation, or receipt construction.

The existing canonical MCP-to-agent conversion is reused unchanged. The bridge does not claim object identity or raw MCP wire equality across that adapter. It claims that no additional ChatRunner-specific conversion is introduced.

The existing direct executor remains authoritative for every non-gateway ChatRunner tool. Gateway support does not move direct tools behind MCP, rename them, or change their schemas.

The existing meta-only loop guard remains applicable to discovery. `rook_tools_ls`, `rook_tools_search`, and `rook_tools_read` are discovery-only calls. A `rook_tools_call` invocation is an execution call because its target is dispatched through the canonical path.

## Production composition

The Chat service composition root constructs the production runner with:

- the requested fixed `tool_access` ceiling; and
- one canonical executor already bound to that ceiling.

The executor is provided by the MCP owner and invokes the existing scoped meta-tool path. The composition root does not receive the capability index and cannot dispatch a target itself.

This dependency is optional for other ChatRunner callers. Omitting it preserves the prior direct-only surface exactly.

No environment variable, model argument, tool argument, or skill text can alter the runner's local authority ceiling.

## Required no-contact tests

### Schema and exposure

- With no canonical executor, a bare ChatRunner exposes no `rook_tools_*` schema.
- With a canonical executor, exactly the four existing gateway schemas are active.
- Each visible schema equals the existing canonical MCP-to-LiteLLM projection.
- Existing direct ChatRunner schema names and schemas are otherwise unchanged.
- Existing `request_tools` and `search_tools` remain active and retain their behavior.

### Capability discovery and dispatch

Through the ChatRunner-visible gateway and the real capability index:

- `rook_tools_search` discovers `gh_library` and `gh_batch_component_info`;
- `rook_tools_read` returns each existing target schema;
- `rook_tools_call` accepts valid arguments for each target;
- exact decoded target arguments reach the canonical target owner unchanged;
- the canonical MCP-to-agent result conversion reaches ChatRunner unchanged; and
- each delegate is entered exactly once.

The target dispatch is patched at the canonical no-contact boundary. No Rhino, Grasshopper, model, or Worker call occurs.

### Authority and policy

Table-driven tests prove:

```text
ChatRunner readonly + MCP full     -> readonly discovery and call refusal
ChatRunner full     + MCP readonly -> readonly discovery and call refusal
ChatRunner full     + MCP full     -> full discovery and admitted call
```

Additional regressions prove that existing behavior remains active for:

- Rhino target and document context propagation;
- meta-tool recursion refusal;
- contained-tool refusal;
- unknown or non-dispatchable targets;
- non-object target arguments;
- target-schema validation failures; and
- profile refusal before target dispatch.

Refusal tests assert zero target dispatch.

### No duplicated capability system

Tests and source inspection establish that:

- ChatRunner contains no capability index;
- ChatRunner contains no target dispatch table;
- the four schemas have one source;
- `gh_library` and `gh_batch_component_info` are not added to ChatRunner's direct dispatcher or direct groups;
- gateway target calls re-enter the existing `call_tool()` path; and
- ordinary target observations remain recorded once under the target name and existing meta origin.

### Existing behavior

The focused ChatRunner, ToolRegistry, visible-dispatchability, MCP profile, targeting, containment, and `rook_tools_*` suites remain green. The known unrelated baseline failure remains separately accounted for and must not change signature.

## Failure behavior

- Invalid construction scope refuses before a runner is exposed.
- A missing canonical executor means the four tools are absent, not present-but-failing.
- Canonical policy refusals are returned through the existing MCP-to-agent conversion.
- Canonical executor exceptions retain the existing bounded agent-executor behavior.
- ChatRunner does not retry, fall back to direct dispatch, or substitute a target.
- Failure of a gateway target does not cause ChatRunner to load or invoke a similarly named direct tool.

## Scope

This slice may change only the modules needed to:

- single-source the four existing gateway schemas;
- expose them conditionally in ChatRunner;
- construct a scope-bound canonical executor;
- compose that executor into the production Chat service; and
- add focused deterministic tests and concise design/plan documentation.

It does not add individual Grasshopper routes, tools, groups, or aliases.

## Non-goals and non-claims

This slice does not:

- qualify any model;
- contact a model, Worker, Rhino, or Grasshopper during development or review;
- promise compatibility with every Rook skill;
- add filesystem, shell, artifact-writing, user-question, lifecycle-hook, or skill-transition support;
- select skills automatically;
- create Worker or subagent delegation;
- turn ChatRunner into a durable workflow engine;
- replace PlanGraph, Reactor-style execution, OpenProse, or the deterministic compositional harness;
- add a provider abstraction, tool registry, capability database, benchmark, trace system, or archive; or
- change product model routing.

The bounded claim after implementation is:

> ChatRunner supports the canonical Rook MCP capability-discovery and invocation protocol under the intersection of its local authority ceiling and the active MCP profile.

## Qualification continuation gate

The explicit-skill local top-level agent qualification resumes only after this prerequisite bridge:

1. passes its no-contact tests;
2. receives independent implementation review;
3. merges normally; and
4. is deployed from the clean merge SHA.

The later qualification still requires separate design approval and separate authorization before any model, Rhino, or Grasshopper contact.
