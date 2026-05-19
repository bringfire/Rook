# Agent Capability Recovery After `/command` Lockdown

Date: 2026-05-19
Status: Accepted

## Decision

Native `/command` remains fail-closed. It is a controlled execution primitive, not an agent capability surface.

Capability recovery after the lockdown must happen through:

- typed MCP tools and typed native/managed routes
- MCP/intent-layer routing with explicit schemas
- structured refusal advisories
- narrow safe command metadata
- explicit manual boundaries

`/command` refusal is expected behavior. Lack of typed recovery for common deterministic intent is the product gap.

## Definitions

**Good refusal:** The requested command or intent is unsafe, interactive, ambiguous, under-parameterized, or outside autonomous execution. The refusal provides either a clear typed alternative or a clear manual boundary.

**Bad refusal:** The requested intent is common, deterministic Rhino work, but there is no discoverable typed route for an agent to use.

**Weak refusal:** A typed route exists, but the tool name, description, schema, examples, or feedback contract make the agent unlikely to find it, use it correctly, or trust the result.

**Dangerous recovery:** Any broad command allowlist, hidden fallback, prompt-driving path, or advisory message that encourages repeated raw command attempts instead of typed recovery.

## Capability Matrix Schema

The assessment artifact is a matrix of agent intents, not Rhino command names. Each row must be actionable and closeable.

Columns:

- `Intent`
- `Existing typed route`
- `Model-facing tool`
- `Feedback quality`
- `Postcondition / Verification Signal`
- `Former command fallback`
- `Safety class`
- `Gap severity`
- `Recommended action`
- `Owner`
- `Verification target`
- `Status`

Allowed `Recommended action` values:

- `tool_description_fix`
- `schema_fix`
- `typed_route_addition`
- `structured_refusal_advisory`
- `safe_command_metadata`
- `manual_boundary`
- `no_action`

Allowed `Verification target` values:

- `synthetic_eval_task`
- `unit_or_integration_test`
- `live_rhino_smoke_test`
- `telemetry_query`
- `documentation_update`

Every recovery path must have an owner and a verification target. Rows without both fields are not ready for implementation planning.

## Safe Command Metadata Gate

Safe command metadata is allowed only for narrow deterministic cases. It is an output of the capability matrix, not an input assumption.

A command can be promoted only if all criteria pass:

- fully scripted from supplied parameters
- non-interactive under normal and error conditions
- input-validated before execution
- prompt-idle checked after execution
- backed by an observable postcondition
- documented as a typed capability or internal implementation detail

There are no partial exceptions. If any criterion is not met, the command remains refused or must be represented by a typed route/manual boundary.

## Structured Refusal Contract

Refusals should be machine-readable and useful to agents. A refusal should not only say that raw command execution failed; it should identify the next safe route when one exists.

Native `/command` and MCP-facing refusal paths must share the same semantic envelope, even if the transport wrapper differs. Native HTTP routes may return this object under their existing `data` error payload. MCP tools must preserve the same field names under their MCP `data` payload. Layers may add fields, but they must not rename or invert the required fields.

Required fields:

- `error_code`: stable machine-readable code, such as `run_script_safety_refusal`, `native_command_state_uncertain`, or `typed_route_required`.
- `reason`: concise human-readable reason for refusal.
- `safety_class`: one of `good_refusal`, `bad_refusal`, `weak_refusal`, `dangerous_recovery_blocked`, or `unknown`.
- `retry_allowed`: boolean. `true` means the same layer can retry after supplying missing structured parameters or after verified recovery. `false` means retrying the same raw command path is not expected to help.

Conditionally required fields:

- `detected_command`: required when the refusal is tied to a concrete raw Rhino command string.
- `detected_intent`: required when the refusing layer can classify the higher-level modeling intent.
- `prompt_state`: required when Rhino command prompt state influenced the refusal. Values should be `idle`, `active`, `unknown`, or `not_checked`.
- `candidate_tools`: required when one or more typed alternatives are known. Each entry should include `tool`, `reason`, and `required_parameters`.
- `missing_parameters`: required when a candidate typed route exists but the request lacks required structured parameters.
- `manual_boundary`: required when the correct recovery is human/manual rather than typed automation.

Optional fields:

- `docs_hint`: short reference to relevant docs or capability-map row.
- `postcondition_hint`: expected verification signal for the candidate typed route.
- `recovery`: human-readable recovery guidance for UI clients and logs.

Refusal should be informative; recovery should be typed.

Native `/command` may return advisory data. It must not silently invoke typed tools or become a hidden orchestrator. MCP/intent layers own routing because they can preserve explicit schemas, validation, and feedback contracts.

Intent redirection is allowed only when the target typed route is explicit and fully parameterized. If parameters are missing or ambiguous, the system should advise rather than infer defaults.

## Assessment Method

Use four inputs. Recordings and logs weight the work, but they do not define the capability ontology.

### Top-Down Intent Taxonomy

Start from common Rhino agent work:

- create geometry
- modify geometry
- select/query/measure
- organize layers, groups, names, user text
- materials and object display attributes
- annotate
- view/capture
- import/export
- blocks and block-definition mutation
- Grasshopper workflows
- recovery/state

### Current Tool and Route Map

For each intent, identify whether it is covered by:

- typed MCP tool
- direct native route
- managed bridge route
- typed route implemented internally with RunScript
- safe command metadata for `/command`
- deprecated interactive route
- no route

`Typed route implemented internally with RunScript` means the model-facing capability is still a typed tool or route with explicit parameters, validation, postcondition checks, and structured feedback. RunScript is an implementation detail hidden behind the typed contract.

`Safe command metadata for /command` means the command remains available through the controlled `/command` primitive only after the safe metadata hard gate passes. This is not a second allowlist path and should remain narrow.

Coverage includes discoverability and feedback quality. A route that exists but is not obvious to the model is a weak coverage row.

### Historical Telemetry

Mine available session recordings and logs for:

- `rhino_command` call frequency
- refused command strings
- known-command fallback usage
- repeated user/model task patterns
- recovery attempts after refusal

Historical data is a prioritization signal, not the source of truth. It says what happened under the old surface, not what agents should be taught to do under the new surface.

### Synthetic Agent Evals

Create representative modeling tasks where the model receives the current tool catalog and must choose a route.

Measure:

- selected route
- task completion
- fallback attempts to blocked command strings
- missing parameters
- quality of feedback after success/failure
- whether the model can recover through typed routes

Success is not just final task completion. The eval must show that the agent used a safe, explicit route and received enough feedback to know what happened.

## Prioritization

Rank gaps by:

- workflow importance
- safety tractability
- frequency or telemetry signal
- verification quality
- whether the gap blocks larger task chains

High-severity gaps are common deterministic intents that lack discoverable typed recovery and block broader workflows.

Low-severity gaps are rare, interactive, ambiguous, unsafe, or better handled by explicit manual boundaries.

## Non-Goals

- No broad allowlist expansion.
- No hidden `/command` orchestration.
- No prompt-driving as normal recovery.
- No treating raw Rhino command count as the capability metric.
- No automatic parameter inference for ambiguous intent.
- No typed route promotion without an observable postcondition.

## Acceptance Criteria

This workstream is ready for implementation planning when:

- the top intent map exists at `docs/superpowers/capability-recovery/agent-intent-map.md`
- the blocked usage audit exists at `docs/superpowers/capability-recovery/blocked-command-audit.md`
- the current tool/route map exists at `docs/superpowers/capability-recovery/current-tool-route-map.md`
- the synthetic eval baseline exists at `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`
- the ranked recovery queue exists at `docs/superpowers/capability-recovery/ranked-recovery-queue.md`
- high-severity gaps have owners
- high-severity gaps have verification targets
- structured refusal fields are specified for `/command` and MCP-facing refusal paths
- any proposed safe command metadata promotion satisfies the full hard gate

The expected output is a ranked, testable recovery queue, not a philosophy document.
