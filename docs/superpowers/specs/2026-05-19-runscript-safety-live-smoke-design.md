# RunScript Safety Live Smoke Harness Design

Date: 2026-05-19

## Summary

The RunScript P0/P1 containment branch needs a live Rhino smoke suite before it can be treated as merge-ready. Unit tests and a native build prove the intended branches compile and preserve wrapper contracts, but they do not prove Rhino's live prompt behavior, native quarantine behavior, or recovery behavior under an owned process.

The smoke suite should be runtime-only. Build, deployment, and registration remain explicit prerequisites. The harness launches one owned Rhino process, validates that the tests are bound to that process, runs a focused safety suite, and cleans up or force-kills only that owned process.

The suite is intentionally narrow: it tests the safety contracts introduced by this branch, not broad Rhino regression behavior.

## Goals

- Validate `rhino_command` fail-closed behavior for unclassified commands.
- Validate a harmless native `/command` allow path.
- Validate MCP `rhino_command` allow behavior only when explicit safe metadata is present in the process under test.
- Validate native `/command` does not report success when Rhino enters or may have entered an interactive prompt.
- Validate subsequent native `/command` calls are refused while native command state is uncertain.
- Validate `/command/prompt` preserves success and failure envelopes.
- Validate `/command/cancel` clears native command uncertainty only after verified idle recovery.
- Validate normal-mode `/command/start` and `/command/send` are refused.
- Validate prompt-driving learning surfaces are absent or refused in normal and panel-locked paths where the live harness can do so cheaply.
- Validate deterministic failure branches for prompt-read unknown, command wait timeout, and cancel-unverified behavior through guarded test-only hooks.
- Ensure prompt-state tests cannot leave the suite running against a stuck Rhino prompt.

## Non-Goals

- Do not build, deploy, register, or select the installed Rook runtime inside the smoke suite.
- Do not test attached user Rhino sessions.
- Do not test P2 dispatcher modal allowlisting for all mutation routes.
- Do not use visual checks unless a future contract cannot be asserted by endpoint state.
- Do not drive complex or destructive Rhino commands.
- Do not keep autonomous prompt driving as a test utility.
- Do not add hooks that execute arbitrary commands, sleep Rhino indefinitely, or globally alter dispatcher behavior.

## Harness Shape

Add two runtime harness smoke modes:

`runscript-safety`

`runscript-safety-hooks`

The normal mode runs the non-hooked suite with Rhino launched in a sanitized normal-mode environment. The hook mode launches Rhino with native RunScript safety test hooks enabled before the Rhino process starts.

Both modes run under the existing `scripts/run_rhino_runtime_harness.py` owned-process flow. The harness is still responsible for launching Rhino, waiting for the owned discovery record, binding the smoke command to the exact owned PID and port, capturing artifacts, and cleanup.

The command/cwd pair is pinned:

- cwd: `<repo_root>/mcp_server`
- normal command: `python -m pytest tests/test_runscript_safety_live.py -m "requires_rhino and runscript_safety_live and not runscript_safety_hooks" -v`
- hook command: `python -m pytest tests/test_runscript_safety_live.py -m "requires_rhino and runscript_safety_live and runscript_safety_hooks" -v`

Both modes must set a finite harness smoke timeout. The initial implementation should choose a conservative fixed timeout, such as 120 seconds, and make it visible in the harness invocation/result. The timeout is a harness-level guard for pytest hangs and is separate from per-request HTTP timeouts inside the test helpers.

The live test file is:

`mcp_server/tests/test_runscript_safety_live.py`

All tests in the file use:

- `pytest.mark.requires_rhino`
- `pytest.mark.runscript_safety_live`

Hooked tests additionally use:

- `pytest.mark.runscript_safety_hooks`

The file must fail fast if pytest-xdist or another parallel execution mode is detected. These tests mutate global Rhino command prompt state and must run serially.

## Rhino Launch Environment

Native hook and interactive-learning gates are read by the Rhino-hosted native plugin process, not by the pytest subprocess. Therefore environment decisions that affect native behavior must be applied before launching Rhino.

For `runscript-safety`, the harness must launch Rhino with normal-mode-sensitive variables explicitly unset, at minimum:

- `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING`
- `ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS`

For `runscript-safety-hooks`, the harness must launch Rhino with:

- `ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS=1`
- `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING` explicitly unset

The hook-enabled mode must still keep interactive command learning disabled unless a separate future test mode deliberately scopes that behavior. Do not imply pytest can enable native hooks after Rhino has already launched.

The harness should implement this as a launch environment override for the Rhino process, not as only smoke-command environment. Smoke-command environment remains for communicating port, PID, artifact dir, and pytest behavior to the test process.

## Runtime Preconditions

The harness must fail fast before running hazardous tests unless all are true:

- `ROOK_RHINO_PORT` is present and a positive integer.
- `ROOK_RHINO_PROCESS_ID` is present and a positive integer.
- Direct native `/ping` succeeds against `ROOK_RHINO_PORT`.
- The discovered runtime is the owned Rhino process represented by `ROOK_RHINO_PROCESS_ID`.
- Prompt/cancel endpoints are reachable and return the expected modern envelope shape.
- Safety hooks are disabled in `runscript-safety`.
- Safety hooks are enabled in `runscript-safety-hooks`, which means Rhino was launched with `ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS=1`.

If `/ping` or a native build marker exposes version/build metadata, the harness should record and assert it. If no such marker exists, the suite should not invent one as a prerequisite for this smoke slice; it should rely on the installed runtime prerequisite and endpoint-shape checks.

## Artifact And Hazard Sentinel Contract

The runtime harness should pass the current run artifact directory into the smoke process:

`ROOK_HARNESS_ARTIFACT_DIR=<artifact_dir>`

This value is smoke-process state, not native plugin state, so it can be supplied to pytest after Rhino is launched.

The hazardous prompt fixture writes this file when recovery cannot verify idle:

`<artifact_dir>/runscript_safety_unrecovered.json`

The sentinel records:

- failing test node id;
- owned PID and port;
- last `/command` response, if available;
- last `/command/cancel` response, if available;
- last `/command/prompt` response, if available;
- reason recovery was considered unverified;
- timestamp.

After the smoke subprocess exits, the runtime harness checks for this sentinel. If present, the run is non-green and the harness must force cleanup of only the owned Rhino process.

Force cleanup must be PID-scoped:

- use `ROOK_RHINO_PROCESS_ID` / the owned process object;
- assert the PID is the launched owned Rhino PID before killing;
- never kill by process name.

The fixture should also attempt immediate cleanup when it writes the sentinel. The harness remains the final authority and performs final owned-process cleanup even if the pytest process already attempted to kill the process.

## Prompt State Semantics

Prompt idle uses the same convention as the native branch:

- empty prompt;
- `Command`;
- strings with `Command:` prefix.

For `/command/prompt`, idle verification is:

- native response has `success=true`;
- `data.is_active=false`;
- `data.prompt` matches the idle convention.

The suite must not require `verified=true` from `/command/prompt`; prompt is an observability endpoint and does not certify recovery.

For `/command/cancel`, successful recovery is:

- native response has `success=true`;
- `data.cancelled=true`;
- `data.verified=true`;
- `data.is_active=false`;
- `data.prompt` matches the idle convention when present.

If cancel fails or prompt cannot prove idle afterward, Rhino state remains unsafe for the suite.

## Hazard Fixture

The `prompt_recovery_guard` fixture protects every test that intentionally creates an active prompt or uncertain state.

Before the test body:

- read `/command/prompt`;
- if idle cannot be confirmed, attempt `/command/cancel`;
- if idle still cannot be confirmed, write the unrecovered sentinel and stop the suite.

After the test body, in `finally`:

- call `/command/cancel`;
- read `/command/prompt`;
- require idle by the prompt-state semantics above;
- if idle cannot be confirmed, write the unrecovered sentinel, attempt owned-PID cleanup, and stop pytest with a non-zero result.

A fixture failure alone is not enough. The fixture must prevent later tests from continuing against an uncertain Rhino prompt state.

All helper calls that touch Rhino must use bounded per-request HTTP timeouts. The live suite should not rely on global pytest or harness timeout as the normal control path for stuck HTTP calls.

## Normal-Mode Test Coverage

Normal-mode tests should avoid intentionally active prompts.

They should assert:

- direct `/ping` succeeds for the owned port;
- `/command/prompt` returns the modern success envelope when Rhino is idle;
- `/command/cancel` returns success and verified idle when Rhino is already idle;
- direct native `/command/start` returns structured `interactive_command_deprecated` in normal mode;
- direct native `/command/send` returns structured `interactive_command_deprecated` in normal mode;
- MCP `rhino_command_interactive_prompt` preserves the native `/command/prompt` response;
- MCP `rhino_command_interactive_cancel` preserves the native `/command/cancel` response;
- MCP `rhino_command` rejects unclassified or unsafe commands before native `/command` is called;
- tool listings do not advertise deprecated start/send or interactive learning tools in normal mode.

The harmless native allow path should call native `/command` directly with a deterministic complete command such as `_SelNone`. This tests native `/command` success without involving MCP safety metadata.

The MCP fail-closed test must prove that native `/command` was not reached. Acceptable proof mechanisms are:

- in-process MCP execution with a monkeypatched `call_rhino` spy that asserts `/command` was never called;
- a controlled fake bridge in the same process;
- a hazardous-looking command rejected through MCP followed by prompt idle confirmation and no native command uncertainty, only if the test can make the absence of native side effects observable.

The preferred proof is an in-process spy because it directly asserts the contract and does not depend on Rhino timing.

MCP `rhino_command` allow-path testing must be explicit about process boundaries:

- If tests invoke the in-process Python MCP module, a monkeypatched temporary command knowledge store is acceptable.
- If tests invoke a real external MCP process, monkeypatching is invalid. In that case, use a controlled temporary metadata fixture/file loaded by that process.

The spec does not allow an ambiguous "monkeypatch a live MCP process" test. The chosen implementation must make clear where the safety metadata lives.

## Prompt-State Test Coverage

The prompt-state live test intentionally starts a minimal Rhino prompt using direct native `/command`.

Recommended command:

`_-Line`

The command asks for a point and creates no durable object unless completed.

Expected first `/command` result must be phrased as an invariant, not a single exact branch. Depending on Rhino timing, the response may take the active-prompt, prompt-unknown, or timeout path.

The required invariant is:

- `/command` does not return success;
- response data includes `verified=false`;
- response data indicates uncertain execution state, such as `state_uncertain=true`, `waitingFor`, or the native timeout/unknown code;
- Rook does not claim `executed=true` as a verified success.

Before recovery, the test must call native `/command` again with a harmless command such as `_SelNone` and assert refusal due to native command uncertainty. This is intentionally another `/command` call, not a broader typed mutation route, because broad modal mutation quarantine is P2 follow-up work.

Then the test recovers with `/command/cancel` and confirms idle through `/command/prompt`.

After recovery, a final native `/command` `_SelNone` may be used to prove `/command` was re-enabled only after verified cancel recovery.

## Test-Only Fault Injection Hooks

Natural Rhino behavior is appropriate for active-prompt quarantine. It is not appropriate for prompt-read timeout, command wait timeout, or post-cancel active prompt verification failures, because forcing those naturally would make the harness unstable.

Add guarded test-only hooks with these constraints:

- disabled unless `ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS=1`;
- unavailable in normal builds/runs by default;
- enabled only by launching Rhino with `ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS=1`;
- named explicitly as RunScript safety test hooks;
- located close to the native command safety code;
- one-shot by default, or explicitly reset between tests;
- tests assert the hooks are disabled by default;
- hooks exercise the same production branches as real timeout/unknown outcomes;
- hooks do not execute arbitrary commands;
- hooks do not sleep Rhino indefinitely;
- hooks do not alter dispatcher behavior globally.

Acceptable narrow hooks:

- next prompt read returns `Unknown`;
- next command future wait simulates timeout;
- next post-cancel prompt poll remains `Active`.

The hook control surface can be a native test-only endpoint or an env-gated one-shot mechanism, but tests must be able to verify default disabled behavior and reset any enabled hook deterministically. If an endpoint is used, it must refuse or be absent in `runscript-safety` and only operate in `runscript-safety-hooks`.

## Hooked Test Coverage

With hooks disabled:

- hook endpoint or control mechanism is unavailable/refused;
- normal prompt/cancel behavior remains unchanged.

With hooks enabled:

- prompt-read unknown during `/command` causes a native failure with `verified=false` and `state_uncertain=true`;
- command wait timeout causes native failure with timeout code, `verified=false`, and `state_uncertain=true`;
- post-cancel active prompt causes `/command/cancel` failure with `cancelled=false`, `verified=false`, and `state_uncertain=true`;
- after any hook-induced uncertain state, subsequent native `/command` is refused until verified cancel recovery succeeds or the owned process is killed.

## Panel And Dev-Gate Coverage

Most panel/dev-gate checks can remain Python/MCP-level because they are routing and environment-policy contracts, not live Rhino prompt behavior.

The live suite should include only low-cost assertions that do not require relaunching the MCP process under many environment combinations. If panel-locked mode requires a separate environment, keep that in the unit/contract suite unless the runtime harness grows a dedicated panel-locked smoke mode.

The required policy remains:

- normal mode does not list start/send or interactive learning tools;
- direct calls to deprecated start/send or learning tools return structured refusal;
- `ROOK_MCP_TARGET_MODE=panel_locked` cannot enable interactive command learning through normal env flags;
- dev/learning mode, if retained, is explicitly outside normal autonomous execution.

## Failure And Cleanup Policy

The smoke suite has three failure categories:

1. Preflight failure: no prompt was intentionally created. Fail normally and let harness cleanup run.
2. Non-hazardous assertion failure: fail normally and let harness cleanup run.
3. Hazardous unrecovered state: write sentinel, stop pytest, and force cleanup of the owned Rhino PID.

If hazardous recovery cannot verify idle, the suite must not keep running further tests.

If the smoke subprocess exceeds the finite harness smoke timeout, the harness must terminate the smoke process tree, mark the run non-green, check for any sentinel that was written before the hang, and then clean up the owned Rhino process. A timeout without a sentinel is still non-green and should be reported as an uncontrolled smoke timeout.

The harness manifest should record:

- normal smoke return code and output;
- configured `smoke_timeout_seconds`;
- whether the smoke command timed out;
- whether an unrecovered sentinel was found;
- sentinel path if present;
- cleanup status;
- owned PID and port.

## Review Notes Carried Into Implementation

- Prompt idle alone does not clear native quarantine. Only `/command/cancel` with verified idle recovery may clear native command uncertainty.
- `/command/prompt` is observability only and should preserve native failure.
- `/command/cancel` is recovery and should preserve native failure.
- `_SelNone` is safe for direct native `/command`, but MCP `rhino_command` requires explicit safe metadata in the actual MCP process under test.
- Native hook enablement must be decided before Rhino launches; pytest cannot enable native hooks after launch.
- Normal-mode smoke must sanitize native env gates before launching Rhino.
- The smoke mode must use a finite harness timeout plus bounded HTTP request timeouts.
- The prompt-state test should assert safety invariants, not a timing-specific branch.
- Subsequent mutation refusal in this suite means subsequent native `/command` refusal. Broad typed-route modal allowlisting is P2.
- Force-kill must target the owned PID only.

## Self-Review

- Does the design test the original incident mechanism? Yes: natural active prompt, false-success prevention, quarantine, refusal of later `/command`, and verified cancel recovery are covered.
- Does it avoid testing user Rhino? Yes: every live test runs through the existing owned runtime harness and PID-scoped cleanup.
- Does it avoid flaky natural timeout forcing? Yes: timeout and unknown branches are covered by narrow one-shot test hooks.
- Does hook enablement respect process boundaries? Yes: hook-enabled tests are a separate Rhino launch mode.
- Does it protect against pytest hangs? Yes: the harness smoke command has a finite timeout and helpers have bounded HTTP timeouts.
- Does it distinguish prompt observation from recovery verification? Yes: prompt requires success plus idle shape; cancel requires verified/cancelled/idle.
- Does it avoid relying on in-process monkeypatches for an external MCP process? Yes: MCP allow tests must either be in-process or use controlled metadata visible to the real process.
- Does it prove MCP fail-closed requests avoid native `/command`? Yes: the preferred test uses an in-process `call_rhino` spy; weaker live-state proof must make absence of side effects observable.
- Does it avoid overclaiming P2 coverage? Yes: subsequent refusal is scoped to native `/command`; broader mutation quarantine is explicitly out of scope.
