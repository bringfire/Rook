# Deployed Progressive Discovery Smoke Design

**Status:** Approved for implementation on 2026-07-14

## Goal

Certify that an agent running under the existing lean MCP profile can discover,
inspect, and invoke tools that are intentionally absent from its directly
advertised tool list. The proof must run against the deployed AppData Python
runtime and must include a live Grasshopper target when live smoke is requested.

## Scope

This change extends tests and deployment validation only. It does not change:

- the `rook_tools_ls`, `rook_tools_search`, `rook_tools_read`, or
  `rook_tools_call` schemas;
- the capability-index search or ranking algorithm;
- lean or readonly profile membership;
- dispatch, targeting, or safety policy.

If the new tests expose inadequate search behavior, that result is reported as a
failure for separate evaluation rather than repaired as part of this work.

## Deployed Progressive Gate

Extend `scripts/lm_surface_smoke.py progressive` to prove all of the following:

1. `PYTHONPATH` is empty and `rook`, `rook.server`, and the capability modules
   import from the invoked interpreter's `site-packages`.
2. The lean catalog advertises all four progressive gateways.
3. Representative hidden tools are not directly advertised under lean.
4. Realistic intent phrases return the expected existing tool within a small,
   explicit result window. The initial cases cover script editing, script pins,
   C# script creation, Grasshopper status, and canvas snapshots.
5. Exact-name search still resolves the existing DG-009 Grasshopper aliases.
6. `rook_tools_read` returns a dispatchable object schema for every pinned
   discovery target.
7. `rook_tools_call` successfully invokes a hidden, Rhino-independent,
   non-mutating target (`agent_status`) and returns its expected result shape.

The smoke fails closed with a specific message for missing gateways, profile
leakage, missing search results, invalid schemas, non-dispatchable records, or a
failed hidden-tool invocation.

## Live Grasshopper Gate

Extend `scripts/deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke`
so its fresh smoke process uses the public progressive gateway for a hidden live
target:

1. Search for Grasshopper status using a realistic intent phrase.
2. Require `gh_status` in the returned candidates.
3. Read and validate the `gh_status` schema.
4. Invoke `gh_status` through `rook_tools_call` and require success.

The existing direct Rhino ping, direct Grasshopper status control, Chirp
component creation, error inspection, and undo cleanup remain in place. This
separates a bridge/plugin failure from a progressive-gateway failure.

## Deployment and Release-Readiness Integration

For the release runtime contract, `deploy-local-testing.ps1` runs the progressive
smoke after effective-runtime verification using the installed AppData venv with
an empty `PYTHONPATH`. Explicit repo-venv development mode is not described as a
deployed-runtime proof and reports that this gate was skipped.

`validate-local-testing-stack.ps1 -ReleaseReadiness` records the progressive
smoke as its own fail-closed gate artifact after installed-runtime verification.
This preserves the exact command, stdout, stderr, duration, and failure label in
the release-readiness evidence.

## Test Strategy

- Add unit tests for realistic-query result validation, schema validation, and
  hidden-call result validation before changing the smoke implementation.
- Preserve the existing profile and meta-tool regression suites.
- Add PowerShell guard coverage proving local deploy and release-readiness invoke
  the deployed progressive gate in the correct modes.
- Run the targeted Python suites, PowerShell guard suites, a payload-only AppData
  deployment, the deployed progressive smoke, and the live Grasshopper smoke.

## Success Criteria

- Existing search behavior passes the realistic intent matrix without runtime
  search changes.
- A hidden tool completes the deployed lean `search -> read -> call` chain.
- A live hidden Grasshopper tool completes the same chain through the installed
  runtime.
- The proof fails if imports resolve to repository source instead of deployed
  `site-packages`.
- No tool schema, exposure profile, ranking algorithm, or dispatch behavior is
  modified.
