# RookChat Tool-Schema Contract Hardening Design

Date: 2026-06-17
Branch: `codex/rookchat-tool-schema-contract-hardening`

## Context

The RookChat Grasshopper one-box testing exposed a deeper class of failures than
ordinary prompt tuning:

- `gh_create_csharp_script` was documented and advertised before RookChat could
  dispatch it locally.
- fallback/local schemas did not always match MCP/server schemas.
- `gh_errors` is a no-argument tool at dispatch time, but the fallback catalog
  advertised it as accepting arbitrary arguments.
- local models then legally attached script-creation arguments to `gh_errors`,
  and the dispatcher rejected the call later.
- panel feedback originally made some application failures look like neutral
  completion.

Those failures are tool-contract failures. The model can still be weak, but it
should not be asked to infer hidden contracts from permissive or inconsistent
schemas. Before more model comparison, prompt tuning, or outer-loop harness
optimization, Rook needs a deterministic contract layer that proves what the
model sees matches what the dispatcher will accept.

## Goal

Create a RookChat tool-schema contract hardening slice that makes the model-visible
tool surface testable, closed by default, and consistent across the MCP server,
local dispatcher, fallback catalog, cached catalog, and active ChatRunner registry.

The immediate outcome is not "make every local model good." The outcome is:

- Rook can distinguish platform contract bugs from model failures.
- schema drift is caught before live Rhino testing.
- no-argument tools are advertised as no-argument tools.
- dispatcher validation and schema validation agree.
- future prompt or harness optimization has a stable evaluator.

## Non-Goals

- No production implementation in this design commit.
- No live Rhino requirement for automated contract tests.
- No Workbench, launcher, session topology, or Rhino process lifecycle changes.
- No broad model-behavior prompt tuning.
- No attempt to make `gemma4:12b` pass by weakening tool semantics.
- No new external dependency in the first implementation PR.
- No staging or reverting `knowledge/contextual_mab.pkl` or
  `knowledge/substrate_observations.jsonl`.
- No immediate `metaharness` integration as the source of truth for correctness.

## Design Principles

### Tool schemas are contracts

A function schema is not merely documentation. It is the contract shown to the
model before tool selection. If the schema says arbitrary keys are allowed, the
model is allowed to send arbitrary keys.

### Closed by default

Every model-visible tool parameter object should use:

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

unless the tool intentionally accepts arbitrary user-defined keys. Open object
schemas require an explicit allowlist entry and rationale.

### Dispatcher and schema must agree

If a dispatcher rejects unexpected arguments, the schema must not allow them. If
the schema marks a field as required, the dispatcher must treat it as required
or document a narrower runtime rule. Compatibility aliases such as
`source -> code` are allowed only when they are intentional, tested, and local to
the tool family.

### One visible contract path

Rook currently has several schema sources:

- MCP schemas from `server.py::list_tools()`
- cache-loaded schemas in `ToolRegistry`
- fallback schemas in `ChatRunner`
- local override schemas in `_build_local_tool_catalog()`
- dispatcher validation and transform functions

The first hardening slice should not rewrite the whole tool system, but it must
introduce a single contract policy used to audit or normalize every schema before
it is exposed to the model.

### Measure before optimizing

`metaharness` is useful later as an outer-loop optimizer for prompts, descriptions,
routing, or harness files. It should not replace deterministic contract tests.
First build the evaluator; then optimize against it.

## Proposed Architecture

### 1. Contract Policy Module

Add a small Python contract policy module for chat-visible schemas, for example:

`mcp_server/src/rook/agent/chat/tool_contracts.py`

Responsibilities:

- normalize model-visible schemas into a consistent LiteLLM function shape;
- enforce `type: object` for function parameters;
- enforce `additionalProperties: false` by default;
- apply explicit allowlist exceptions for genuinely dynamic object maps;
- provide zero-argument schema helpers;
- provide named overrides for known fallback/local gaps such as `gh_errors`;
- expose audit helpers used by tests and startup diagnostics.

This module is a policy layer, not a second dispatcher. It should not call Rhino
or execute tools.

### 2. Schema Exposure Boundaries

Apply or audit the contract policy at every place a schema becomes visible to
the model:

- fallback catalog construction in `ChatRunner`;
- local tool catalog construction in `ChatRunner`;
- MCP tool conversion in `tool_registry.mcp_tool_to_litellm()`;
- cache-loaded catalog before registry use;
- active registry schemas returned by `ToolRegistry.get_active_schemas()`.

The implementation plan may choose to start with audits and focused overrides,
then move policy normalization upstream once tests describe the desired behavior.

### 3. Source-of-Truth Strategy

Do not make a broad rewrite that tries to generate all 392 tool schemas from one
new framework in the first PR.

Use a pragmatic staged source-of-truth rule:

- MCP/server schemas remain canonical for MCP-exposed tools.
- local ChatRunner override schemas are allowed only when the local dispatcher
  adds direct chat-only tools or fixes fallback gaps.
- every local override must have a parity test against MCP/server schema where
  the same tool exists.
- every divergence must be named as intentional in a test.

Longer term, high-value tool families such as `gh_*` script tools can migrate to
shared schema builders, but this slice should prioritize contract verification
over abstraction.

### 4. Zero-Argument Tool Discipline

Define a zero-argument tool list or derive one from existing dispatcher policy
where possible.

Required behavior:

- `gh_errors` is closed and no-argument in every visible schema path.
- any tool in `STRICT_NO_ARGUMENT_BRIDGE_TOOLS` has a closed no-argument schema
  unless a test names an exception.
- zero-argument schemas include a concise description telling the model when to
  call the tool, not what arguments to send.
- dispatcher rejection of unexpected arguments returns a corrective message, but
  the schema should prevent those calls before the model emits them.

### 5. Dispatcher/Schema Parity

Add tests that compare model-visible schema requirements with dispatcher behavior
for selected critical tool families:

- `gh_create_script`
- `gh_create_python_script`
- `gh_create_csharp_script`
- `gh_errors`
- `request_tools`
- `search_tools`
- `gh_update_script`
- representative bridge tools that accept no arguments
- representative bridge/transform tools that require arguments

This should include both positive and negative expectations:

- required arguments are present in schemas;
- invalid extra arguments are disallowed in schemas when the dispatcher rejects
  them;
- alias semantics are preserved;
- compatibility aliases are documented and do not broaden the public schema
  silently.

### 6. Model-Visible Golden Fixtures

Introduce fixture tests for what the model actually sees.

Examples:

- initial active tool schema set;
- `gh_canvas` active schema set after `request_tools("gh_canvas")`;
- local fallback catalog when no MCP cache is present;
- cached catalog after policy normalization.

The fixtures should be compact JSON snapshots or assertions over stable
invariants, not brittle full-file dumps. Important invariants include:

- no accidental `additionalProperties: true`;
- no zero-argument tool with open params;
- script creation tools carry C# body-code guidance;
- tool names are distinct;
- required fields match expected contract;
- schemas fit within a reasonable token budget for the active group.

### 7. Golden Transcript Tests

Add non-live transcript-style tests that simulate model/tool event boundaries
without Rhino:

- a clean one-box sequence:
  `request_tools` -> `gh_create_csharp_script` -> `gh_errors`;
- a bad `gh_errors` call with script-creation arguments;
- a bad `gh_create_csharp_script` call missing `code`;
- sequential streamed tool calls reusing provider indices;
- application-level `success: false` result rendering.

These tests should prove the harness surfaces useful feedback and does not
silently turn schema or dispatcher failures into neutral "Done" states.

### 8. Optional Provider Probe, Not CI Gate

Live local-model probes are valuable but should not be ordinary unit tests. Add
an optional script or documented command that can run a one-box prompt against
selected models and record transcripts:

- `ollama_chat/qwen3:14b`
- one cloud model
- any experimental local model under evaluation

The script should produce artifacts that can be attached to PRs, but merge
gates should remain deterministic until model-provider variance is better
controlled.

### 9. `metaharness` Position

`metaharness` should be considered after the contract harness exists.

Good future use:

- optimize schema descriptions;
- compare prompt variants;
- tune request-tools guidance;
- evaluate local-model harness variants against recorded benchmarks;
- track candidate diffs and validation evidence.

Bad immediate use:

- asking it to infer correctness while schema/dispatcher parity is still broken;
- using it as a replacement for deterministic contract tests;
- optimizing against a live Rhino-only benchmark as the first evaluation target.

The first spike should be limited to answering: "Can `metaharness` run our
deterministic one-box contract benchmark and produce useful candidate/evidence
ledgers?" It should not be part of this first contract-hardening PR.

## Acceptance Criteria

Automated tests:

- fallback schemas are closed by default or explicitly allowlisted;
- `gh_errors` is no-argument in fallback, local, cached, and active registry
  paths;
- local ChatRunner schemas for `gh_create_*` remain parity-compatible with
  MCP/server required fields;
- dispatcher/schema parity tests cover the critical `gh_*` script and
  verification tools;
- no model-visible active schema for `gh_canvas` accidentally permits arbitrary
  arguments except allowlisted dynamic tools;
- golden fixture tests prove the model-visible `gh_canvas` catalog contains
  distinct, accurate schemas;
- transcript tests prove bad tool calls produce actionable failures, not neutral
  completion;
- existing focused RookChat Python and panel tests still pass.

Manual verification:

- run the one-box prompt with `qwen3:14b` after deployment;
- record whether the tool sequence is:
  `request_tools` -> `gh_create_csharp_script` or unified C# create ->
  `gh_errors` -> final summary;
- run one cloud model as a sanity comparison;
- treat `gemma4:12b` as exploratory, not a merge gate.

## Implementation Boundaries

The implementation plan should be split into focused tasks:

1. policy/audit helpers;
2. zero-argument schema discipline;
3. fallback/local/MCP/catalog parity tests;
4. golden active-schema fixtures;
5. transcript tests for one-box and bad-call cases;
6. optional provider probe documentation.

Do not combine this with additional C# UI redesign, Workbench work, live deploy
automation, or broad model-behavior prompt tuning.

## Open Questions For Review

1. Should the first implementation PR fail every open object schema, or begin
   with a curated allowlist and warnings for less critical legacy tools?
2. Should cached catalogs be normalized on load, or should cache invalidation
   force rebuilding when contract policy changes?
3. Do we want a checked-in compact fixture for the entire `gh_canvas` schema set,
   or assertion-based invariants only?
4. Should the first `metaharness` spike be a separate design after this contract
   suite lands?

## Recommended Answers

1. Start with a curated allowlist. Failing every open schema immediately may
   reveal useful cleanup, but it risks turning the first PR into a 392-tool
   migration. The first gate should be strict for `gh_canvas` and warn/report
   elsewhere.
2. Normalize cached catalogs on load and include a contract-policy version in
   diagnostics. Cache invalidation can follow if stale caches keep hiding bugs.
3. Use assertion-based invariants first. Add compact fixture snapshots only for
   high-value groups once the schema shape stabilizes.
4. Yes. Treat `metaharness` as a separate spike after deterministic contract
   tests exist.

## Spec Self-Review

- Placeholders: none.
- Consistency: the spec treats MCP/server schemas as canonical while allowing
  tested local overrides; this is a staged source-of-truth strategy, not a
  contradiction.
- Scope: focused on schema contracts and deterministic tests; no production code
  implementation is included in this spec commit.
- Ambiguity: open-object handling, cache behavior, fixtures, and metaharness are
  all called out with recommended decisions for review.
