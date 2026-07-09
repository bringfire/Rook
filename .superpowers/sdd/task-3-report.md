Task 3 Report: LM8H Live Script Fixture And Scalar Runtime Readiness

Date: 2026-07-09
Workspace: C:/UDEV/Rook

Summary
- Implemented `scripts/lm8h_affine_scalar_depth_probe.py` as the LM8H affine sibling probe scaffold.
- Added `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py` with Task 3-focused CLI, manifest, routing, fixture, deprecated-library-selection, and scalar runtime readiness coverage.
- Kept scope deliberately pre-publication: no worker publication, no live dispatch, no retry flow, no planner flow, no `gh_edit`.

TDD Evidence
1. Red
   - Ran:
     `./mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py -q`
   - Result:
     collection failed with `FileNotFoundError` for `scripts/lm8h_affine_scalar_depth_probe.py`, which confirmed the test was asserting the missing Task 3 script surface.
2. Green
   - Re-ran the same focused file after implementation.
   - Result:
     `17 passed in 0.25s`

What Changed
- `scripts/lm8h_affine_scalar_depth_probe.py`
  - Added canonical LM8H constants and CLI defaults:
    - editable `2.0`
    - factor `2.0`
    - offset `1.5`
    - initial observed output `5.5`
    - expected output `7.5`
  - Implemented local affine routing artifact and contract payload helpers.
  - Implemented direct affine fixture creation through:
    - `gh_library`
    - `gh_create_slider`
    - `gh_create_component`
    - `gh_connect`
    - `gh_solve`
    - `gh_get_value`
    - `gh_inspect_output`
  - Enforced Multiplication proxy selection rules:
    - exact component name match
    - active/non-deprecated only
    - scan past deprecated aliases
    - GUID authority only from explicit top-level fields:
      `guid`, `Guid`, `proxyGuid`, `ProxyGuid`
  - Kept raw GUIDs out of worker-visible receipt data by using presence/hash-only visible fields.
  - Implemented affine scalar runtime readiness:
    - graph scaffold
    - static routing validation
    - affine projection invariant check
    - acceptance packet assembly
    - worker-visible projection
    - worker turn request payload assembly
  - Implemented `_run_probe(...)` only through runtime-ready artifact production, intentionally stopping before Task 4 publication/dispatch behavior.

- `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`
  - Added CLI default and forbidden-surface tests.
  - Added manifest identity checks.
  - Added source hygiene checks:
    - no LM8F/LM8G/planner/retry/`gh_edit` path coupling
    - no raw `3.0` literal in LM8H source
  - Added affine routing artifact route-id checks.
  - Added direct fixture execution tests with fake tool responses.
  - Added regression coverage for deprecated-first Multiplication lookup behavior.
  - Added top-level GUID authority coverage for component proxy extraction.
  - Added runtime readiness and projection invariant coverage.

Constraint Checks
- No live Rhino/GH run was performed.
- No Planner model added.
- No model-authored template selection added.
- No worker-authored topology/components/wires/tools/code/scripts/GUIDs added.
- No `gh_edit`.
- No retry flow.
- Canonical worker model remains `gemma4:12b-it-qat`.
- Hidden derived worker value `3.0` does not appear in LM8H source, and pre-publication LM8H request/visible artifact construction does not introduce it.

Verification
- Ran:
  `./mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py mcp_server/tests/test_gh_affine_scalar_transform_expectation_sources.py mcp_server/tests/test_gh_affine_scalar_transform_expectation_acceptance_criteria.py mcp_server/tests/test_local_worker_source_routing_validator.py -q`
- Result:
  `74 passed in 0.42s`

Commit
- Planned commit message:
  `feat(lm8h): create affine scalar live probe fixture`

Notes
- I did not modify unrelated workspace files.
- I did not commit any raw probe run artifacts.
- `_run_probe(...)` now prepares runtime-ready artifacts for Task 4 to consume, but intentionally does not implement publication or dispatch early.
