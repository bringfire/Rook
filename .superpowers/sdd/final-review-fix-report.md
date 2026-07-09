LM8H final whole-branch review fixes

Date: 2026-07-09

Scope
- Updated `scripts/lm8h_affine_scalar_depth_probe.py`
- Updated `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`
- Updated `docs/superpowers/plans/2026-07-09-lm8h-affine-scalar-depth-pressure.md`

Fixes
- Clarified stale plan wording so deprecated-only exact Multiplication results gate-fail, while deprecated aliases may precede and be skipped in favor of a later active exact match.
- Added publication guards for published `action_request` payloads before `worker_action.json` is written:
  - invalid `action_id` now terminally receipts as `publication_failed` with `worker_publication_invalid_action_id`
  - forbidden non-input content markers now terminally receipt as `publication_failed` with `worker_publication_forbidden_content:<marker>`
  - existing hidden-marker and raw-GUID publication gates remain in place before `worker_action.json`
- Wrapped canonical fixture mismatches as `FixtureSetupFailure` so `_run_probe()` emits `fixture_failure_summary.json` and a specific `decision.reason`.
- Wrapped projection invariant mismatch as `FixtureSetupFailure` at scalar runtime readiness so the same fixture failure summary path is used.

Verification
- `./mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py -q`
  - Passed: `32 passed`
- `./mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_gh_affine_scalar_transform_expectation_sources.py mcp_server/tests/test_gh_affine_scalar_transform_expectation_acceptance_criteria.py mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py mcp_server/tests/test_local_worker_source_routing_validator.py -q`
  - Passed: `89 passed`
- `git diff --check origin/main..HEAD`
  - Passed with no output

Notes
- I left unrelated user dirt and untracked files untouched.

LM8H publication guard fix report

Date: 2026-07-09

Scope
- Updated `scripts/lm8h_affine_scalar_depth_probe.py`
- Updated `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`

Fix
- Closed the remaining publication guard gap by scanning the published `response_payload["input"]` subtree for forbidden markers before `worker_action.json` is written.
- Preserved the existing `action_id` allowlist check, raw GUID leak gating, and the valid numeric `input.value` path for `3.0`.
- Added a regression covering `{"input":{"value":3.0,"note":"gh_edit"}}`, asserting terminal `publication_failed`, no `worker_action.json`, and no live `gh_set_value` dispatch.

Verification
- `./mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py -q`
  - Passed: `33 passed`
- `git diff --check origin/main..HEAD`
  - Passed with no output

Notes
- I staged and committed only the targeted probe/test/report changes.
