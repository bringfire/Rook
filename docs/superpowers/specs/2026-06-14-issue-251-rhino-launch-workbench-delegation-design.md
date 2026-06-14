# Issue #251: `rhino_launch` Workbench Delegation Design

## Status

Approved design. Implementation must start with the live diagnostic gate; no
delegation code is allowed until the gate classification is reviewed.

## Problem

`rhino_launch` is still implemented as a legacy detached-launch path in
`mcp_server/src/rook/server.py`. It hardcodes
`C:/Program Files/Rhino 8/System/Rhino.exe`, starts Rhino with detached
`Popen`, polls `/ping`, and returns bare string failures such as
`"Rhino failed to start within Ns"`.

The hardened owned launch path already exists behind `rhino_workbench_launch`
through `workbench.launch_owned_workbench()`. That path uses resolved
executables, PID-correlated discovery, owned-session registry rows, structured
failure envelopes, and launcher readiness evidence.

The design goal is to keep `rhino_launch` as a compatibility name while removing
the legacy detached-launch behavior, but only if the MCP-wrapped owned launcher
is sound enough to delegate to.

## Non-Goals

- Do not design an async job-handle or keepalive transport fix inside #251.
- Do not repair stale active-target bindings from `rhino_launch`.
- Do not redefine multi-instance bridge selection for the already-running path.
- Do not kill non-owned Rhino processes or clear recovery/profile state without
  explicit user approval.

## Considered Approaches

### Recommended: Gate-First Narrow Delegation

Run a classified live MCP gate first. If the gate clears, or routes only to the
existing #222 recovery-modal launcher-hardening class, make `rhino_launch` a thin
compatibility wrapper over the owned launcher. This is the selected approach.

### Deprecate `rhino_launch`

Return a structured deprecation response telling callers to use
`rhino_workbench_launch`. This is a fallback only if delegation proves infeasible.
It is less ergonomic because agents naturally ask for the simpler launch tool.

### Async Launch Handle

Return quickly with a job/session handle and poll for readiness. This may be the
right shape for a separate transport issue if the gate proves a contract-changing
transport bug. It is intentionally deferred and is not part of #251.

## Blocking Gate

The first deliverable is a recorded live diagnostic gate for
`rhino_workbench_launch` through MCP. The gate is a classifier, not a yes/no
probe.

### Static Timeout Comparison

Before any launch run, compare:

- owned launcher readiness ceiling: current default `readinessTimeoutSeconds = 90`;
- actual MCP client per-call timeout, if discoverable from the current client
  path.

The MCP client timeout is a separate layer and must not be inferred from the
launcher default. If it cannot be identified, record it as `unknown` and do not
classify a timeout mechanism by inspection.

If readiness timeout is greater than or equal to the discovered client timeout,
record that as a likely client-timeout mechanism before the live run. The run
then confirms behavior rather than discovering that relationship from elapsed
time.

### Clean-State Protocol

Snapshot evidence before cleanup:

- all `Rhino.exe` PIDs;
- which PIDs are Rook-owned workbench sessions;
- window titles where available;
- recovery/crash-modal presence;
- relevant discovery files and owned-session registry rows.

Then clean only Rook-owned workbench sessions through `rhino_workbench_close`.
Do not use raw process kill for owned workbenches. If non-owned Rhino processes
remain, stop and ask the user before closing them. Do not clear recovery or
profile state; record it as evidence.

Clean state is not the same as cold state. Record whether the run is cold or
warm. A gate cannot classify `clear` from a warm-only or unknown-client-timeout
success.

### MCP-Wrapped Test Arm

Invoke `rhino_workbench_launch` through MCP. Do not call
`launch_owned_workbench()` directly for the test arm.

Capture evidence out-of-band so a real transport death does not destroy the only
observation channel:

- MCP server stderr/log output;
- MCP server process liveness polled externally;
- launched Rhino process liveness;
- owned registry rows;
- discovery files and discovery log evidence;
- recovery/modal/window state;
- elapsed time and returned payload if the call returns.

Stdio closed with server alive maps to client-timeout unless other evidence
points elsewhere. Stdio closed with server dead maps to server-death.

When needed, run with a short `readinessTimeoutSeconds` to distinguish a
structured readiness failure from blocking until an outer timeout.

### Conditional Direct Control

Run the direct control only when the MCP arm fails, is ambiguous, succeeds
without obvious headroom against known timeout constants, or when the client
timeout is unknown. Unknown client timeout always triggers the control and
prevents `clear`; the result is `unverified` unless another failure bucket is
proven.

Before the control, re-clean to the same baseline. Do not run the control
against state contaminated by a failed MCP launch.

The control must run in an equivalent async in-process context that awaits
`launch_owned_workbench()`. It localizes the fault boundary but does not by
itself name the transport mechanism.

### Gate Outcomes

- `clear`: at least one cold MCP-wrapped success with known timeout headroom and
  no contradictory out-of-band evidence.
- `unverified`: the run did not reproduce a failure but lacks enough evidence to
  classify clear, such as unknown client timeout or warm-only success.
- `client_timeout`: client or transport patience expires while server remains
  alive.
- `event_loop_starvation`: server survives but cannot service transport while
  launch is in flight. This would be surprising because the owned launcher
  already offloads readiness work, so it requires explicit evidence.
- `server_death`: MCP server exits or crashes mid-call.
- `recovery_modal_222`: Rhino survives or hangs behind crash-recovery/modal
  state and never publishes readiness. This routes to #222.

Time is evidence only. Success is deterministic state: PID-correlated discovery
plus ping readiness through `LaunchOutcome.ok`. Time remains an outer readiness
ceiling, never a success/failure/retry predicate.

## Routing Decision

- `clear`: proceed with #251 delegation.
- `recovery_modal_222`: route the launcher-hardening evidence to #222 and
  proceed with #251 delegation, because delegation improves diagnostics.
- transport class (`client_timeout`, `event_loop_starvation`, or
  `server_death`): file a separate issue with the gate artifact.
- `unverified`: do not implement delegation until the gap is resolved or the user
  explicitly accepts the risk.

If a transport class is confirmed, #251 can proceed only if the transport fix
preserves `launch_owned_workbench()`'s return contract. If the transport fix
changes the contract, such as return-fast job handles, #251 waits and aliases the
final contract. Never ship `rhino_launch` as a plain blocking alias onto a
confirmed-broken MCP path.

## Delegation Design

If routing allows #251 to proceed, `rhino_launch` remains public but no longer
contains detached-launch code.

### Control Flow

The selected ordering is:

1. `panel_target_config_error` fail-fast.
2. Reachability check.
3. Launch-ownership scope gate.
4. Owned launcher delegation.

This is fork (b): scope gates launch ownership, not reachability reporting.

`panel_target_config_error` is preserved as a specific actionable payload. It
must not collapse into the generic `workbench_requires_external_scope` response.

For valid panel-locked callers, reachable Rhino returns `already_running`.
Panel-locked callers that would need to launch get `workbench_requires_external_scope`.

### Already-Running Boundary

`already_running` is a reachability result, not an ownership result. It may
report success for a user-opened Rhino instance that has no Rook-owned workbench
row. That is intentional for the compatibility tool.

`rhino_launch` does not mutate active targeting on the already-running path. The
existing no-rebind behavior is preserved consciously. Source behavior shows the
legacy `/ping` is not necessarily routed through the active binding, so a
successful `already_running` does not prove the active binding is healthy. Stale
active-target repair belongs in explicit targeting tools or a separate issue.

Multi-instance already-running selection remains inherited from the existing
bridge discovery selection.

### Launch Path

When Rhino is not reachable and the caller is allowed to launch, `rhino_launch`
delegates to `workbench.launch_owned_workbench()`.

Every `rhino_launch` outcome includes:

```json
{"canonicalTool": "rhino_workbench_launch"}
```

This applies to success, failure, already-running, invalid-timeout, config-error,
and scope-rejection outcomes.

Explicit `timeout` maps to `readinessTimeoutSeconds`. If unset, `rhino_launch`
uses the owned launcher default of 90 seconds, not the legacy 120 seconds.
Callers needing the old ceiling can pass `timeout: 120`.

Mapped timeout validation is inherited from the owned launcher. Invalid values
return structured `invalid_readiness_timeout` instead of legacy fall-through
behavior.

Executable resolution comes only from the owned launcher. The hardcoded
`C:/Program Files/Rhino 8/System/Rhino.exe` literal is removed from the
`rhino_launch` case.

Legacy bare string failures are eliminated. Launch failures return the owned
launcher's structured envelope, including failure code, reason taxonomy, and
readiness evidence.

### Auto-Bind Asymmetry

Preserve current asymmetry:

- already-running does not auto-bind and does not repair stale active bindings;
- newly launched owned workbench may auto-bind when
  `targeting.should_auto_bind_launched_instance()` is true, adding `auto_bound`
  and `active` metadata.

## Test Plan

The live gate is a recorded classification artifact, not a unit test. Save the
gate result for review before implementation.

Unit tests must cover:

- delegation dispatch: external caller, not reachable, calls
  `workbench.launch_owned_workbench`;
- timeout mapping: explicit `timeout` passes through as
  `readinessTimeoutSeconds`;
- default timeout: unset `timeout` uses 90 seconds;
- timeout validation: invalid `timeout` surfaces structured
  `invalid_readiness_timeout`;
- config-error precedence: with Rhino reachable, config error returns the
  specific config-error payload instead of `already_running`;
- panel reachable behavior: panel-locked and reachable returns
  `already_running` without calling the launcher;
- panel launch rejection: panel-locked and not reachable returns
  `workbench_requires_external_scope` and does not launch;
- external reachable behavior: reachable external caller returns
  `already_running`, does not call the launcher, does not rebind, and includes
  `canonicalTool`;
- already-running no-rebind: existing stale-active-target test remains and
  asserts `canonicalTool` and no `auto_bound`;
- launch auto-bind asymmetry: launch success may set `auto_bound` and `active`;
  already-running never does;
- structured failure envelope: launcher failure returns structured workbench data
  with code/reason/evidence and never the old bare timeout string;
- canonical metadata: all outcomes include
  `canonicalTool: "rhino_workbench_launch"`;
- hardcoded executable source guard: the `rhino_launch` case no longer contains
  `C:/Program Files/Rhino 8/System/Rhino.exe`;
- schema/docs: tool description says `rhino_launch` is a compatibility alias for
  owned workbench launch, `timeout` default is 90, and callers should prefer
  `rhino_workbench_launch`;
- existing `rhino_launch` non-routed meta-tool policy remains.

Post-implementation live smoke is required after unit tests pass:

- run MCP-driven `rhino_launch`, not a direct helper call;
- verify `canonicalTool` and the real public wire shape;
- cover a success path, either already-running or newly launched owned workbench;
- cover a forced failure path, such as bad executable resolution or an equivalent
  controlled launch failure, proving the real structured envelope is returned and
  the old bare string is absent;
- leave the machine clean afterward through owned workbench teardown.

The smoke proves the delegated wrapper. It does not replace the pre-implementation
gate, which determines whether delegation is allowed.

## Review Cadence

1. Run the live gate and present the recorded classification artifact.
2. Reviewer approves whether routing allows #251 delegation.
3. Implement delegation only if allowed.
4. Run unit tests.
5. Run post-implementation live smoke.
6. Reviewer checks implementation and smoke before PR.
