# Deployed Progressive Discovery Smoke Design

**Status:** Under review

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
4. The exact realistic-intent matrix below returns each expected existing tool
   at a rank no greater than its pinned maximum. Ranks are one-based.
5. Exact-name search still resolves the existing DG-009 Grasshopper aliases.
6. `rook_tools_read` returns a dispatchable object schema for every pinned
   discovery target.
7. The same `agent_status` target completes one full realistic-intent
   `search -> read -> call` chain and returns its pinned public wire shape.

The smoke fails closed with a specific message for missing gateways, profile
leakage, missing search results, invalid schemas, non-dispatchable records, or a
failed hidden-tool invocation.

### Pinned Gateway and Target Sets

- All advertised gateways:
  `rook_tools_ls`, `rook_tools_search`, `rook_tools_read`, `rook_tools_call`.
- Alias-bearing gateways whose descriptions must name every DG-009 target:
  `rook_tools_search`, `rook_tools_read`, `rook_tools_call`.
- Discovery targets:
  `gh_update_script`, `gh_set_script_pins`, `gh_create_csharp_script`,
  `gh_status`, `gh_snapshot`, `agent_status`.
- Targets that must be hidden from the lean advertised catalog:
  `gh_update_script`, `gh_set_script_pins`, `gh_create_csharp_script`,
  `gh_status`, `agent_status`.

`gh_snapshot` is a discovery target but is not hidden under lean; it remains a
directly advertised baseline tool.

### Pinned Realistic-Intent Matrix

| Query | Expected tool | Limit | Maximum acceptable rank |
|---|---|---:|---:|
| `edit a Grasshopper script` | `gh_update_script` | 10 | 10 |
| `change the inputs and outputs of a Grasshopper script` | `gh_set_script_pins` | 10 | 10 |
| `create a C# script component in Grasshopper` | `gh_create_csharp_script` | 10 | 10 |
| `check whether Grasshopper is ready` | `gh_status` | 10 | 10 |
| `take a snapshot of the Grasshopper canvas` | `gh_snapshot` | 10 | 10 |
| `check running agent status` | `agent_status` | 10 | 1 |

These phrases are product expectations, not test fixtures to tune around the
current scorer. A missing or out-of-rank target is an
`intent_discovery_rank_failed` finding and blocks certification. Repairing that
ranking is explicitly outside this test-only change and requires a separate
design decision.

### Read and Call Contracts

For every discovery target, `rook_tools_read` must return:

- the exact requested `name`;
- `mcp_dispatchable is true`; and
- an `input_schema` object whose JSON Schema `type` is `object`.

For `agent_status`, the smoke must first find `agent_status` from the pinned
realistic query, then read that same record, then invoke that same target through
`rook_tools_call`. The decoded successful wire result must contain `count` as an
integer and `agents` as an array.

### Deployed Origin Contract

The gate requires `PYTHONPATH=''` and checks that all of these imports resolve
under the invoked interpreter's `Lib/site-packages`:

- `rook`
- `rook.server`
- `rook.capability_index`
- `rook.agent.capability_record`
- `rook.agent.capability_inventory`
- `rook.agent.execution_profile`
- `rook.agent.profile_reconciliation`
- `rook.agent.tool_registry`

An origin failure stops the gate immediately. After origins pass, the smoke
collects every remaining discovery finding before returning nonzero so one
ranking failure does not conceal schema or dispatch evidence.

## Live Grasshopper Gate

Extend `scripts/deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke`
so its fresh smoke process uses the public progressive gateway for a hidden live
target:

1. Save the inherited `ROOK_MCP_TOOL_PROFILE`, force it to `lean` for the fresh
   smoke process, and restore it afterward.
2. Assert the lean advertised catalog includes all four gateways and excludes
   `gh_status`.
3. Run the existing direct `rhino_ping` and direct `gh_status` controls first.
4. Search for the exact hidden target name `gh_status` and require it in the
   returned candidates. The realistic-phrase behavior is independently pinned
   by the deployed intent matrix.
5. Read `gh_status` and enforce the common read contract.
6. Invoke `gh_status` through `rook_tools_call` and require success.
7. Only after the progressive chain passes, continue to the existing Chirp
   mutation and undo cleanup.

The existing direct Rhino ping, direct Grasshopper status control, Chirp
component creation, error inspection, and undo cleanup remain in place. This
separates a bridge/plugin failure from a progressive-gateway failure.

## Deployment and Release-Readiness Integration

Ordinary `deploy-local-testing.ps1` deployment remains usable even while the
realistic-intent certification is known to be blocked. It verifies the effective
runtime as it does today. When `-LiveSmoke` is requested, it additionally runs
the exact-name live Grasshopper progressive chain described above. Explicit
repo-venv development mode is not described as a deployed-runtime proof.

After deployment, the standalone deployed progressive gate is invoked with the
installed AppData venv and an empty `PYTHONPATH`. Its nonzero result blocks
certification, not the file synchronization needed to gather the rest of the
evidence.

`validate-local-testing-stack.ps1 -ReleaseReadiness` records the progressive
smoke as its own fail-closed gate artifact after installed-runtime and owned live
Rhino/Grasshopper evidence have been collected. Running it last ensures the
known ranking failure does not conceal live bridge, gateway, schema, or dispatch
results. Its failure still prevents the top-level release-readiness manifest
from reporting success.

The stable gate name is `progressive_discovery`; its stable failure label is
`progressive_discovery_failed`. The recorded command uses the installed
`%LOCALAPPDATA%\Rook\venv\Scripts\python.exe`, invokes
`scripts/lm_surface_smoke.py progressive`, and explicitly supplies an empty
`PYTHONPATH`.

## Test Strategy

- Add unit tests for realistic-query result validation, schema validation, and
  hidden-call result validation before changing the smoke implementation.
- Preserve the existing profile and meta-tool regression suites.
- Add PowerShell guard coverage proving local live smoke forces lean and
  release-readiness invokes the standalone deployed progressive gate last.
- Run the targeted Python suites, PowerShell guard suites, a payload-only AppData
  deployment, the deployed progressive smoke, and the live Grasshopper smoke.

## Success Criteria

- Existing search behavior passes the exact realistic-intent matrix without
  runtime search changes. If it does not, certification remains blocked with an
  `intent_discovery_rank_failed` finding pending a separate ranking decision.
- A hidden tool completes the deployed lean `search -> read -> call` chain.
- A live hidden Grasshopper tool completes the same chain through the installed
  runtime.
- The proof fails if imports resolve to repository source instead of deployed
  `site-packages`.
- No tool schema, exposure profile, ranking algorithm, or dispatch behavior is
  modified.

## Current Baseline

A source-runtime probe on 2026-07-14 used the exact pinned matrix above. The
first five expected Grasshopper tools were absent from their top-ten result
windows. `agent_status` ranked first for `check running agent status` and its
current wire result contained an integer `count` and an `agents` array.

Therefore the realistic-intent certification is currently blocked. The purpose
of this work is to make that gap durable and visible while continuing to collect
the exact-name, read-schema, hidden-call, deployed-origin, and live-plugin
evidence needed to distinguish search quality from gateway or dispatch failure.
