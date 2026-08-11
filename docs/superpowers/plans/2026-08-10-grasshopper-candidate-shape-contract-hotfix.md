# Grasshopper Candidate Shape Contract Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make catalog, search, and ambiguity candidate shapes explicit and executable across managed serialization and Python validation.

**Architecture:** Managed Grasshopper remains the sole candidate producer and projects one of three explicit shapes. Python strictly validates the corresponding public result shape. One test-only JSON fixture is the shared cross-language authority; no production registry, schema service, fallback, or runtime dependency is added.

**Tech Stack:** C#/.NET 8 and net48, xUnit, Python 3.12, pytest, JSON.

## Global Constraints

- Preserve the approved catalog, search, and ambiguity field contracts exactly.
- Do not weaken Python validation or admit multiple shapes for one context.
- Do not change search ranking, eligibility, metadata, provenance, audit, `gh_edit`, `gh_snapshot`, T*/C*, or receipts.
- No Rhino, Grasshopper, MCP, or model contact before independent implementation review.
- The later live qualification has a maximum of five read-only host calls and requires separate authorization.

---

### Task 1: Shared candidate-shape contract

**Files:**
- Create: `mcp_server/tests/fixtures/grasshopper_component_candidate_shapes.json`
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs`
- Modify: `mcp_server/src/rook/server.py`
- Create: `mcp_server/src/rook/grasshopper_component_contract.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/tests/test_grasshopper_component_discovery_coherence.py`

**Interfaces:**
- Consumes: the approved identity fields and three existing candidate contexts.
- Produces: explicit managed `Catalog`, `Search`, and `Ambiguity` projection modes; strict Python validation for each context; one shared fixture matrix.

- [x] **Step 1: Add the shared JSON fixture and RED managed test**

  The fixture contains exactly one `catalog`, one `search`, and one `ambiguity` candidate. The managed test serializes real handler outputs for all three contexts and compares each `JsonElement` structurally with the matching fixture object.

- [x] **Step 2: Run the managed contract class and verify RED**

  Run:

  ```powershell
  dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release --filter FullyQualifiedName~GrasshopperComponentDiscoveryContractTests --no-restore
  ```

  Expected: the ambiguity fixture comparison fails because managed output omits `nativeScore` and `matchSource`.

- [x] **Step 3: Replace the boolean managed projection switch with three explicit modes**

  `Catalog` emits identity fields only. `Search` emits identity plus finite numeric `nativeScore` and its existing `matchSource`. `Ambiguity` emits identity plus `nativeScore: null` and `matchSource: "exact_name"`.

- [x] **Step 4: Run the managed contract class and verify GREEN**

  Run the command from Step 2. Expected: all tests pass.

- [x] **Step 5: Add RED Python fixture/projection tests**

  Load the same fixture file. Prove catalog and search responses retain their one admitted shape, ambiguity passes the real `_project_gh_batch_component_info_result`, and cross-shape substitutions fail as malformed.

- [x] **Step 6: Run the Python discovery seam and verify RED**

  Run:

  ```powershell
  $env:PYTHONPATH = "$PWD/mcp_server/src"
  & C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
    mcp_server/tests/test_grasshopper_component_discovery_coherence.py -q
  ```

  Expected: strict catalog/search projection is absent or ambiguity disagrees with the shared fixture.

- [x] **Step 7: Add one explicit Python candidate-shape validator and apply it at existing boundaries**

  Use a closed string mode (`catalog`, `search`, `ambiguity`), not a boolean. Catalog forbids match fields; search requires a finite JSON number plus `native_search | exact_name`; ambiguity requires null plus `exact_name`. Preserve audit and existing top-level MCP projection behavior.

- [x] **Step 8: Run both focused seams and verify GREEN**

  Run the commands from Steps 2 and 6. Expected: all tests pass with only existing warnings.

- [x] **Step 9: Run adjacent seams, compilation, and diff checks**

  Run the prescribed managed and Python discovery/gateway seams, `python -m compileall`, `git diff --check`, and a scope scan proving no protected execution surface changed.

- [x] **Step 10: Commit and stop for independent review**

  Commit the fixture, production corrections, tests, and this plan. Report exact scope, additions/deletions, fixture hash, RED/GREEN evidence, test counts, and worktree state. Do not create a live row or contact any runtime.

## Execution Ledger

- Managed RED: `44 passed, 1 failed`; the shared ambiguity fixture expected
  `nativeScore: null` and `matchSource: exact_name`, while managed serialization omitted
  both fields.
- Managed GREEN: focused `45/45`; complete managed suite `3723/3723`.
- Python RED: `44 passed, 3 failed`; catalog/search cross-shape substitutions were
  accepted by the previously unvalidated library path.
- Python GREEN: focused `47/47`; prescribed adjacent seam `310/310` with `77` existing
  warnings.
- Knowledge baseline: `67 passed`, with exactly the two pre-existing
  `TestGHOperationMapping` failures.
- Shared fixture SHA-256:
  `B22EDF2B309F81FB34B9F5706BD952368836B23021D88EBF5D546E3C9B19D570`.
- No Rhino, Grasshopper, MCP, or model call was made. The existing managed test build
  target copied `Rook.rhp` into the local plugin directory; the running Rhino process was
  not restarted or contacted and therefore did not load this build.

### Task 2: Independent-review hardening

- [x] Add RED regressions for direct-dispatch cross-shape acceptance, oversized JSON
  integers, each invalid score/source field, ambiguity substituted into catalog, an
  unknown managed match source, and an unknown managed shape value.
- [x] Extract the candidate/library projection into one pure Python contract module.
- [x] Apply the same projector to canonical MCP and direct `ToolDispatcher` dispatch.
- [x] Make native-score validation total and managed shape selection exhaustive.
- [x] Run the focused, adjacent, complete managed, knowledge-baseline, compilation,
  fixture, scope, and protected-surface checks.
- [x] Amend the existing commit and stop for renewed independent review.

Review-hardening RED evidence:

- Python: the oversized integer raised `OverflowError`; four direct-dispatch
  cross-shape cases returned raw success. The other single-field cases already refused.
- Managed: `45` tests passed and the two new exhaustiveness tests failed because an
  unknown match source and enum value `99` were accepted.

Review-hardening GREEN evidence:

- Managed focused: `47/47`; complete managed suite: `3725/3725`.
- Python focused: `60/60` with `11` existing warnings.
- Prescribed adjacent Python seam: `323/323` with `76` existing warnings.
- Knowledge baseline: `67 passed`, with exactly the same two pre-existing
  `TestGHOperationMapping` failures.
- No Rhino, Grasshopper, MCP, model, deployment, or five-call qualification contact.

### Task 3: Exact-search source evidence

- [x] Derive both legal Search forms from the shared search fixture.
- [x] Prove managed non-exact serialization emits `native_search` and managed exact
  serialization emits `exact_name`.
- [x] Run the four request/source combinations through canonical MCP and direct
  `ToolDispatcher`, accepting only the two context-correct pairs.
- [x] Mutation-test the Python matrix by temporarily removing the request-context check,
  then restore production byte-for-byte.
- [x] Run final verification and amend the existing commit.

The mutation run produced exactly `4 failed, 4 passed`: both wrong-context source
substitutions failed on both Python surfaces while both legal forms still passed. After
restoration, the managed focused seam passed `49/49` and the Python focused seam passed
`68/68` with `11` existing warnings. The complete managed suite passed `3727/3727`,
the prescribed Python seam passed `331/331` with `83` existing warnings, and the
knowledge seam retained exactly its two documented failures with `67` passing tests.
Production remained byte-identical to the reviewed implementation throughout the
committed delta.
