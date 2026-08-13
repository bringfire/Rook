# Grasshopper Receipt-Fenced Behavioral Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deterministic Grasshopper behavioral acceptance consume only snapshots atomically fenced by the latest terminal managed solve receipt, then express point-row and XY-grid acceptance through one small reviewed artifact/evaluator contract.

**Architecture:** The existing managed solve-readiness registry remains the only lifecycle and fence authority. Covered authoring routes expose its exact receipt, `gh_snapshot` checks that receipt and extracts data inside one managed callback, Python preserves receipts and caller-owned traces without inventing lifecycle state, and one pure module validates artifacts, traces, probes, and deterministic predicates through an injected executor.

**Tech Stack:** C# net48/net8 reflection over Grasshopper 8, `System.Text.Json`, xUnit; Python 3.12, MCP SDK, pytest, canonical UTF-8 JSONL and SHA-256.

## Global Constraints

- Treat specification commit `a77720bf0e566d055b127c919f46cdff0db6ed4b` as the contract authority.
- The authoritative contract is `docs/superpowers/specs/2026-08-12-grasshopper-receipt-fenced-behavioral-acceptance-design.md`.
- Reuse `GhSolveReceiptRegistry`; add no second receipt registry, solve scheduler, public acceptance tool, persistent service, campaign runner, model Critic, or external dependency.
- Preserve the existing `rook.gh_solve_readiness_receipt:v1` wire schema and the separate existing Python `script_receipt`.
- Preserve existing unfenced `gh_snapshot`, `gh_edit` structural snapshot, short-ID, T*/C*, flow, group, relay, and receipt compatibility except for the explicit additive or post-reservation failure-shape corrections in the specification.
- Never admit the structural snapshot embedded in `gh_edit` as behavioral evidence; it is pre-solve compatibility data only.
- Only covered terminal routes can establish acceptance custody. Any later retained preparatory or legacy mutation makes admission incomplete until a later covered terminal route commits and supersedes it.
- Do not claim protection against unobserved out-of-band changes; freshness is bounded to the closed retained source trace and the managed fence.
- Keep `/gh/create-component` capability-neutral and unchanged.
- `gh_set_script_pins` remains preparatory. The final managed `/gh/script` write owns script readiness.
- `gh_snapshot(readiness_receipt_id=...)` must call `CheckFencedRead()` and extract every snapshot field in the same managed callback before reading any output.
- Fenced typed behavioral outputs admit only actual finite `Rhino.Geometry.Point3d` values. Existing string previews remain unchanged and observational.
- The pure Python module receives an injected async executor. It must not open an MCP transport, resolve a target, launch a model, own a process, or retry a call.
- Current Prime and direct callers without the reviewed source-row wrapper and closure owner fail closed; `ToolDispatcher` itself remains recorder-free.
- No Rhino, Grasshopper, MCP runtime, model, provider, deployment, or live target contact is authorized by this plan.
- Stop if implementation requires another production module beyond the one approved pure Python module, a new model-facing route, changes to native `RookNative`, or changes to the receipt wire schema.

## File Map

### Managed production

- Modify `src/Rook/InternalBridge/GhSolveReceiptRegistry.cs`
  - Reuse existing issue, lifecycle, and fence state; add only the terminal-finalization surface needed by covered mutation owners.
- Modify `src/Rook/Handlers/GrasshopperHandler.Readiness.cs`
  - Generalize existing set-value receipt helpers into shared issue/finalize/failure helpers while retaining current callers.
- Modify `src/Rook/Handlers/GrasshopperHandler.cs`
  - Add conditional receipts to `gh_edit`, receipt-backed script writes, exact post-reservation failure objects, and atomic fenced snapshot extraction with typed point outputs.

### Python production

- Modify `mcp_server/src/rook/server.py`
  - Add fenced snapshot schema, propagate exact managed receipts through covered tools and script helpers, replace script settle sleeps with receipt waits, and retain canonical dispatch behavior.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Preserve direct-dispatch argument/result parity through existing shared helpers; do not add recording here.
- Create `mcp_server/src/rook/gh_behavioral_acceptance.py`
  - Own canonical serialization, closed artifact validation, source-row writing and closure verification primitives, trace normalization, fenced probe orchestration, snapshot projection, and deterministic predicates.
- Modify `scripts/grasshopper_point_row_acceptance.py`
  - Reduce it to a compatibility CLI over the common module; remove its independent evaluator authority.
- Modify `scripts/grasshopper_point_row_acceptance.json`
  - Express the reviewed point-row task through `rook.gh_behavioral_acceptance:v1`.

### Managed tests

- Modify `src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs`
  - Existing receipt-state and exact fence cases.
- Modify `src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs`
  - Shared issue/finalize semantics and post-reservation failure custody.
- Create `src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs`
  - Partial edit commits, zero/group-only edits, script writes, and failure responses.
- Create `src/Rook.Tests/Handlers/GrasshopperBehavioralSnapshotTests.cs`
  - Same-callback fence ordering, receipt refusals, typed point projection, truncation, and unfenced compatibility.

### Python tests

- Modify `mcp_server/tests/test_gh_solve_readiness_tools.py`
  - Public fenced snapshot request/result contract and wait correlation.
- Modify `mcp_server/tests/test_gh_script_receipts.py`
  - Exact sibling receipt preservation and script-pipeline failure shapes.
- Modify `mcp_server/tests/test_gh_update_script_defer.py`
  - Receipt-aware verification and removal of fixed settle sleeps.
- Modify `mcp_server/tests/test_gh_authoring_capability_routing.py`
  - Canonical/direct parity for every script helper and `chirp_create`.
- Create `mcp_server/tests/test_gh_behavioral_acceptance.py`
  - Closed artifacts, trace/closure custody, latest-terminal admission, probe phases, restoration, predicates, hashes, and failure precedence.
- Modify `mcp_server/tests/test_grasshopper_point_row_acceptance.py`
  - Thin-CLI compatibility and authentic retained Opus/Qwen expectations.

### Documentation

- Modify `docs/CURRENT_ARCHITECTURE.md`
  - Concise durable receipt-fenced behavioral-acceptance ownership statement after implementation is green.
- Modify this plan only for checked steps, observed verification counts, and review decisions.

## Baseline and Verification Commands

Use the repository interpreter:

```text
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe
```

The implementation lane must start clean and retain the specification commit:

```powershell
git status --short --branch
git merge-base --is-ancestor a77720bf0e566d055b127c919f46cdff0db6ed4b HEAD
git diff --check
```

The broad no-contact verification commands are:

```powershell
$NoDeploy = Join-Path (Get-Location) '.codex-no-deploy-target'
if (Test-Path -LiteralPath $NoDeploy) { throw "Expected absent no-deploy target: $NoDeploy" }
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -p:RhinoPluginDir="$NoDeploy"

& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_gh_solve_readiness_tools.py `
  mcp_server/tests/test_gh_script_receipts.py `
  mcp_server/tests/test_gh_update_script_defer.py `
  mcp_server/tests/test_gh_authoring_capability_routing.py `
  mcp_server/tests/test_gh_behavioral_acceptance.py `
  mcp_server/tests/test_grasshopper_point_row_acceptance.py `
  -q

& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m compileall -q `
  mcp_server/src/rook `
  scripts/grasshopper_point_row_acceptance.py
```

No live-smoke test is part of this plan. Files named `*_live_*` are excluded unless a later, separate authorization explicitly admits them.

---

## Task 1: Generalize managed terminal-mutation receipt custody

**Files:**

- Modify: `src/Rook/InternalBridge/GhSolveReceiptRegistry.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.Readiness.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs`
- Create: `src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs`

### Step 1: Freeze current adjacent behavior

- [x] Run the focused baseline and retain its exact counts:

```powershell
$NoDeploy = Join-Path (Get-Location) '.codex-no-deploy-target'
if (Test-Path -LiteralPath $NoDeploy) { throw "Expected absent no-deploy target: $NoDeploy" }
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -p:RhinoPluginDir="$NoDeploy" --filter `
  "FullyQualifiedName~GhSolveReceiptRegistryTests|FullyQualifiedName~GrasshopperHandlerReadinessTests|FullyQualifiedName~GhEditSolvePathSourceTests|FullyQualifiedName~GhSolvePolicyTests|FullyQualifiedName~NoSyncExpireInScriptPathTests"
```

- [x] Read the current `SetValue`, `SetScript`, and `ApplyEdit` paths end to end. Record the exact first mutation, solve scheduling, solver-ownership restoration, and response-construction points in this plan's execution ledger section.

### Step 2: Write failing registry/helper tests

- [x] Add tests proving one shared issue helper reserves before mutation and returns the existing exact receipt identity/session/mutation fields.
- [x] Add tests for finalization after schedule outcomes `scheduled`, `solver_locked`, and `unknown` without changing the existing schema.
- [x] Add tests for terminal non-ready reasons:
  - `no_solve_relevant_mutation_committed`
  - `mutation_commit_unknown`
- [x] Add tests proving an issued receipt remains available when later response projection fails.
- [x] Run the focused tests and confirm the new cases fail for missing shared behavior, not test-fixture errors.

### Step 3: Implement shared managed helpers

- [x] In `GrasshopperHandler.Readiness.cs`, extract the current set-value behavior into shared helpers with this responsibility split:

```csharp
BeginMutationReceipt(document, canvas)
    -> ensure the current document session
    -> issue one existing v1 receipt

FinalizeCommittedMutation(receiptId, solveResult)
    -> retain scheduled / solver_locked / unknown truth

FinalizeNoCommit(receiptId)
    -> terminal unknown / no_solve_relevant_mutation_committed

FinalizeUnknownCommit(receiptId)
    -> terminal unknown / mutation_commit_unknown
```

- [x] Keep `BeginSetValueReceipt`, `FinalizeSetValueReceipt`, and `MarkSetValueMutationFailed` as thin compatibility delegates if existing tests or source callers require their names.
- [x] Do not add receipt-ID syntax validation, Python-owned epochs, or another scheduling path.

### Step 4: Make direct set-value and set-script writes receipt-complete

- [x] Preserve pre-validation and pre-reservation failure strings exactly.
- [x] On success after reservation, return:

```json
{
  "solve_relevant_mutation_committed": true,
  "solve_readiness_receipt": {}
}
```

alongside existing success fields.
- [x] On any post-reservation exception, return the closed object with exact `error`, exact possibly-empty `Exception.Message`, tri-state `solve_relevant_mutation_committed`, and the exact receipt or null as specified.
- [x] If the mutator completed before a later failure, schedule once if still needed and finalize the same receipt.
- [x] If commitment is known false, finalize `no_solve_relevant_mutation_committed`; if unknowable, finalize `mutation_commit_unknown`.
- [x] Ensure script reads (`gh_set_script` without `script`) issue no receipt and remain observational.

### Step 5: Make `gh_edit` commitment conditional and monotonic

- [x] Add one explicit solve-relevant commit count using only created, deleted, values-set, connected, and disconnected operations.
- [x] Reserve before the first solve-relevant edit mutation owned by the route.
- [x] Preserve per-operation errors and committed counts through later failures.
- [x] A positive count schedules exactly once after restoring solver ownership, finalizes the exact receipt, and exposes it at `result.data.solve_readiness_receipt` even on partial failure.
- [x] A zero-commit edit does not schedule merely to manufacture readiness; if a receipt was reserved, finalize it non-ready.
- [x] A group-only edit keeps its current behavior, has no ready receipt, and cannot qualify as terminal acceptance evidence.
- [x] Leave the embedded structural snapshot in place for compatibility but label it pre-solve in comments and never route it to the evaluator.

### Step 6: Add causal route tests

- [x] Cover successful `gh_set_value` and source-writing `gh_set_script` with exact managed receipts.
- [x] Cover throwing mutators before commit, after known commit, and with unknown commitment; assert exact object shapes and maybe-empty messages.
- [x] Cover `gh_edit`:
  - full success with solve-relevant commits;
  - partial success after at least one commit;
  - exception after a commit;
  - zero-commit;
  - group-only;
  - schedule locked/unknown.
- [x] Assert partial results never lose earlier committed counts or receipt identity.
- [x] Assert a positive committed edit schedules once and a group-only/zero-commit edit schedules zero times.

### Step 7: Verify and review Task 1

- [x] Run the focused command from Step 1 plus the new test class.
- [x] Run the complete managed suite.
- [x] Run `git diff --check` and report production additions/deletions.
- [x] Commit only Task 1 changes.
- [x] Stop for mandatory independent review. Do not begin Task 2 until receipt ownership, partial-commit custody, and zero/group-only behavior are approved.

---

## Task 2: Make fenced snapshots atomic and behaviorally typed

**Files:**

- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs`
- Create: `src/Rook.Tests/Handlers/GrasshopperBehavioralSnapshotTests.cs`

### Step 1: Write failing fence-order tests

- [x] Build a hostile snapshot fixture whose first data/property/output read records an event or throws unless the fence gate has already succeeded.
- [x] Add a successful ordering assertion:

```text
managed callback entered
-> CheckFencedRead
-> fence accepted
-> structural/data/output extraction begins
-> callback returns
```

- [x] Add pending, stale, superseded, solver-locked, replaced-document, unknown-receipt, and wrong-document tests that assert zero snapshot data reads.
- [x] Add a test proving `CheckFencedRead()` and extraction occur in the same callback rather than two queued callbacks.

### Step 2: Implement the closed fenced request

- [x] Extend `TakeSnapshot` parsing so `readiness_receipt_id` is optional for legacy calls but, when present, must be a nonblank actual string.
- [x] Require `include_data=true` and integer `max_preview_items` in `1..1000` for fenced calls.
- [x] Enter one managed callback, call `_solveReceiptRegistry.CheckFencedRead(receiptId, gh.Document!)`, refuse on any non-ready gate, and only then read snapshot state.
- [x] Return exact root `readiness_fence` correlation with receipt ID, document session, mutation epoch, solution run epoch, and completed solution run epoch.
- [x] Keep unfenced response keys and string previews byte-shape compatible.

### Step 3: Add fenced-only typed point outputs

- [x] During the same fenced callback, inspect output volatile data without solving, recomputing, or a second target call.
- [x] Emit `behavioral_point_outputs` only for fenced requests.
- [x] Admit only runtime values that are actual `Rhino.Geometry.Point3d` and whose X/Y/Z are finite.
- [x] Retain component short ID, output index/name, exact total count, `complete`, and point triples.
- [x] Set `complete=false` when count exceeds `max_preview_items`, any value is not a Point3d, any coordinate is nonfinite, or projection is incomplete.
- [x] Never parse `ToString()` output and never use string previews for typed acceptance.

### Step 4: Add compatibility and causal tests

- [x] Assert the successful fence exactly matches a ready terminal wait receipt.
- [x] Assert every refusal reads no component, flow, diagnostic, preview, or point output.
- [x] Assert mixed/nonpoint and nonfinite output is retained as incomplete, never coerced.
- [x] Assert truncation is truthful and no second read occurs.
- [x] Assert a normal unfenced snapshot has the existing exact key shape and no `readiness_fence` or `behavioral_point_outputs`.
- [x] Assert the `gh_edit` embedded snapshot does not contain fenced additions and is not accepted by any managed behavioral helper.

### Step 5: Verify and review Task 2

- [x] Run:

```powershell
$NoDeploy = Join-Path (Get-Location) '.codex-no-deploy-target'
if (Test-Path -LiteralPath $NoDeploy) { throw "Expected absent no-deploy target: $NoDeploy" }
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -p:RhinoPluginDir="$NoDeploy" --filter `
  "FullyQualifiedName~GhSolveReceiptRegistryTests|FullyQualifiedName~GrasshopperHandlerReadinessTests|FullyQualifiedName~GrasshopperTerminalMutationReceiptTests|FullyQualifiedName~GrasshopperBehavioralSnapshotTests"
```

- [x] Run the complete managed suite, compilation, and whitespace checks.
- [x] Commit only Task 2 changes.
- [x] Stop for mandatory independent review. Do not begin Python propagation until same-callback fence-before-read ordering and unfenced compatibility are approved.

---

## Task 3: Propagate managed readiness through every Python model-facing route

**Files:**

- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/tests/test_gh_solve_readiness_tools.py`
- Modify: `mcp_server/tests/test_gh_script_receipts.py`
- Modify: `mcp_server/tests/test_gh_update_script_defer.py`
- Modify: `mcp_server/tests/test_gh_authoring_capability_routing.py`

### Step 1: Write failing schema and propagation tests

- [x] Assert `gh_snapshot` publicly admits optional `readiness_receipt_id` and preserves the exact fenced request through canonical and direct dispatch.
- [x] Add one exact managed terminal receipt fixture and assert identity, session, mutation, and nullable pre-run epochs pass through unchanged.
- [x] Add success and failure coverage for:
  - `gh_create_script`;
  - `gh_create_python_script`;
  - `gh_create_csharp_script`;
  - `gh_update_script`;
  - `chirp_create`.
- [x] Assert `solve_readiness_receipt` is a sibling of, never nested inside, `script_receipt`.
- [x] Assert aliases retain object equality and do not rebuild or rename receipt fields.

### Step 2: Replace fixed settle timing with receipt readiness

- [x] Remove `_await_gh_solve_settle` and `verification_settle_seconds` from script verification paths rather than treating them as evidence.
- [x] After the final `/gh/script` write, require exact booleans `solve_relevant_mutation_committed` and exact managed `solve_readiness_receipt`.
- [x] For eager verification, call existing `gh_wait_for_solve_readiness` with the exact receipt ID and proceed only on a ready terminal result.
- [x] For deferred verification, return the captured receipt immediately without sleeping.
- [x] A missing, malformed, contradictory, timed-out, or terminal non-ready receipt returns the closed `script_pipeline_incomplete` object with phase `solve_readiness`.

### Step 3: Implement monotonic composite failure data

- [x] Add one private constructor in `server.py` for the exact closed script-pipeline failure object; do not create another module.
- [x] At every phase, carry forward exact committed preparatory flags, known component identity, final-write dispatch/success/commit values, exact managed receipt, and existing Python `script_receipt`.
- [x] Do not erase a final managed receipt if post-write verification fails.
- [x] Do not infer commit from top-level success.
- [x] Keep `gh_set_script_pins` receipt-free and preparatory.

### Step 4: Preserve canonical/direct parity

- [x] Ensure canonical `_call_tool_dispatch` and direct `ToolDispatcher` reach the same helpers and return equivalent receipt/result shapes.
- [x] Keep profile, containment, schema, target routing, and script-authoring handoff precedence unchanged.
- [x] Assert each helper makes one final source-write target call and no hidden replay.
- [x] Assert `chirp_create` preserves the same managed receipt from its final shared script helper.

### Step 5: Verify and review Task 3

- [x] Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_gh_solve_readiness_tools.py `
  mcp_server/tests/test_gh_script_receipts.py `
  mcp_server/tests/test_gh_update_script_defer.py `
  mcp_server/tests/test_gh_authoring_capability_routing.py `
  -q
```

- [x] Run Python compilation and a static scan proving no script verification call site uses `_await_gh_solve_settle`, `verification_settle_seconds`, or a fixed `asyncio.sleep` as readiness evidence.
- [x] Commit only Task 3 changes.
- [x] Stop for mandatory independent review. Do not build the evaluator until every covered Python route retains the managed receipt exactly and direct/canonical parity is approved.

---

## Task 4: Build the one pure trace, probe, and deterministic acceptance owner

**Files:**

- Create: `mcp_server/src/rook/gh_behavioral_acceptance.py`
- Create: `mcp_server/tests/test_gh_behavioral_acceptance.py`
- Modify: `scripts/grasshopper_point_row_acceptance.py`
- Modify: `scripts/grasshopper_point_row_acceptance.json`
- Modify: `mcp_server/tests/test_grasshopper_point_row_acceptance.py`
- Create: `mcp_server/tests/fixtures/grasshopper_behavioral_acceptance/legacy-evaluations.json`
- Create: `mcp_server/tests/fixtures/grasshopper_behavioral_acceptance/opus-final-inspection.jsonl`
- Create: `mcp_server/tests/fixtures/grasshopper_behavioral_acceptance/qwen-final-inspection.jsonl`

### Step 1: Define the small public Python surface in tests

- [x] Keep the module surface closed to these responsibilities:

```python
canonical_json_bytes(value) -> bytes
append_source_event(path, event) -> None
seal_prime_source_log(source_path, runtime_log_path, process_state) -> dict
seal_direct_source_log(source_path, runtime_log_path) -> dict
normalize_authoring_trace(source_path, runtime_log_path) -> dict
validate_acceptance_artifact(value) -> dict
run_behavioral_probe(artifact, authoring_trace, executor) -> dict
evaluate_behavioral_probe(artifact, authoring_trace, probe_trace) -> dict
```

- [x] Implementations may use private dataclasses/helpers, but no class or function may open transport, resolve target, launch process, call a model, retry, or mutate outside the injected executor.
- [x] The exact source closure owner remains outside the row emitter: Prime adapter emits rows; outer launcher seals only after process termination, stdout EOF, one final `agent_end`, and all owned child exits. The module merely exposes strict primitives those owners call.

### Step 2: Write canonical serialization and source-custody tests

- [x] Require strict UTF-8 without BOM, sorted keys, no insignificant whitespace, and one trailing LF.
- [x] Reject duplicate JSON keys, extra keys, reordered/gapped/duplicate sequences, events after closure, mismatched counts, bad hashes, nonfinal terminal marker, and valid prefixes without closure.
- [x] For Prime closure, test missing/duplicate/nonfinal `agent_end`, missing EOF, nonterminated process, and lingering owned children.
- [x] For direct closure, require exactly one canonical `rook.gh_direct_transaction_runtime:v1` row and exact count equality; any post-marker call invalidates custody.
- [x] Record Python exceptions as exact module plus qualname and exact `str(exc)`, including empty strings.
- [x] Assert `CancelledError`, `KeyboardInterrupt`, `SystemExit`, and other `BaseException` paths remain unclosed.

### Step 3: Write latest-terminal admission tests

- [x] Normalize canonical gateway, direct dispatch, and operator probe rows into exact `rook.gh_authoring_trace:v1` events.
- [x] Require receipt identity/session/mutation equality between authoring result, terminal wait, and fenced snapshot; use the terminal wait as lifecycle epoch authority.
- [x] Admit only the receipt owned by the latest covered terminal mutation in the complete retained trace.
- [x] Refuse if any later preparatory or legacy mutation appears.
- [x] Cover:
  - latest terminal `gh_edit` with positive commit;
  - committed partial `gh_edit`;
  - zero/group-only edit;
  - script pin preparation followed by final script write;
  - pin-only or failed final write;
  - later legacy mutation;
  - pending, stale, superseded, locked, replaced-document, and unknown receipts;
  - refusal of `gh_edit` embedded structural snapshot.
- [x] State in test names that unobserved out-of-band mutation is outside the claim.

### Step 4: Validate the closed acceptance artifact

- [x] Strictly validate exact top-level, control, output, criterion, and argument keys.
- [x] Reject booleans as numbers, nonfinite values, invalid IDs, duplicate roles/criteria, unknown predicates, unsupported selector kinds, incompatible role kinds, and noncanonical bytes/hash.
- [x] Implement exactly the v1 predicate vocabulary from the specification; do not add grid- or point-row-specific branches.

### Step 5: Implement fenced probe orchestration

- [x] Call the injected executor only for the reviewed sequence:

```text
terminal wait
-> fenced baseline snapshot
-> for each control in artifact order:
     one gh_set_value perturbation
     one terminal wait
     one fenced snapshot
     one gh_set_value restoration
     one terminal wait
     one fenced snapshot
```

- [x] Emit exact `rook.gh_probe_trace:v1` rows for every call and stop at the first failed dispatch, receipt, wait, snapshot, output, control-isolation, or restoration check.
- [x] Require exactly one perturbation receipt and one distinct restoration receipt per control.
- [x] Perturb one control at a time and verify all other bound controls remain exact.
- [x] Restore the exact original slider value and require byte-identical canonical normalized projection after each restoration.
- [x] Never issue a second read with a larger bound, retry a call, repair the canvas, or continue after compromised restoration.

### Step 6: Implement projection and predicates

- [x] Build exact `rook.gh_behavioral_snapshot_projection:v1` from admitted fenced data only.
- [x] Bind controls by unique exact nickname and closed slider shape.
- [x] Select exactly one complete terminal point output; unknown, multiple, truncated, nonpoint, or missing evidence remains incomplete/unproven.
- [x] Evaluate expected finite point multisets for sequence and Cartesian predicates with exact multiplicity/count and the artifact's numeric tolerance only for coordinates.
- [x] Derive the exact `rook.gh_behavioral_evaluation:v1` result and failure precedence; no score or majority vote.

### Step 7: Migrate the point-row compatibility CLI

- [x] Replace independent point-row evaluation logic with calls into `rook.gh_behavioral_acceptance`.
- [x] Convert `scripts/grasshopper_point_row_acceptance.json` to the closed artifact schema without changing the reviewed intent or acceptance meaning.
- [x] Retain authentic fixture expectations:
  - Opus evidence passes all six reviewed criteria.
  - Qwen evidence fails exactly `adjustable_step_present` and `point_count_equals_count` under the compatibility report mapping.
- [x] Ensure unfamiliar/unsupported topology remains incomplete or unproven rather than guessed.

### Step 8: Verify and review Task 4

- [x] Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_gh_behavioral_acceptance.py `
  mcp_server/tests/test_grasshopper_point_row_acceptance.py `
  -q

& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m compileall -q `
  mcp_server/src/rook/gh_behavioral_acceptance.py `
  scripts/grasshopper_point_row_acceptance.py
```

- [x] Run a source scan proving the module has no MCP transport construction, model/provider import, process launch, retry loop, target resolution, sleep-based readiness, or task-specific component GUID/name.
- [x] Report nonblank production additions. Stop if this module grows beyond the reviewed responsibilities or recreates a second evaluator authority.
- [x] Commit only Task 4 changes.
- [ ] Stop for mandatory independent review before documentation reconciliation.

---

## Task 5: Reconcile architecture and run final no-contact verification

**Files:**

- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Modify: `docs/superpowers/plans/2026-08-12-grasshopper-receipt-fenced-behavioral-acceptance.md`

### Step 1: Reconcile the durable architecture statement

- [ ] Add one concise section stating:

```text
covered terminal authoring receipt
+ complete caller-owned trace custody
+ managed atomic solve/read fence
-> behaviorally admissible snapshot
-> deterministic artifact evaluation
```

- [ ] State the bounded freshness non-claim and the separate identities of `script_receipt` and `solve_readiness_receipt`.
- [ ] Do not add campaign, model, provider, qualification, or witness-specific prose to `CURRENT_ARCHITECTURE.md`.

### Step 2: Run complete verification

- [ ] Run the complete managed suite:

```powershell
$NoDeploy = Join-Path (Get-Location) '.codex-no-deploy-target'
if (Test-Path -LiteralPath $NoDeploy) { throw "Expected absent no-deploy target: $NoDeploy" }
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -p:RhinoPluginDir="$NoDeploy"
```

- [ ] Run the focused Python seam from the Baseline section, then the complete non-live Python suite used by the repository's `rook:test` skill.
- [ ] Run compilation and `git diff --check`.
- [ ] Verify exact production owners:

```powershell
git diff --name-only a77720bf0e566d055b127c919f46cdff0db6ed4b -- `
  src/Rook `
  mcp_server/src/rook `
  scripts
```

- [ ] Use diff-scoped protected-surface scans over additions and deletions, excluding diff headers, to prove no change to raw `/gh/create-component`, native Rook routes, T*/C* identity, unrelated receipt schemas, profile/containment walls, or model/provider code.
- [ ] Verify there is exactly one new production Python module and no new external dependency.

### Step 3: Self-review every contract edge

- [ ] Trace each route from caller arguments through managed mutation, receipt issue/finalization, terminal wait, fenced snapshot, trace normalization, probe, and evaluation.
- [ ] Confirm every displayed field has one owner, exact type/nullability, and closed failure behavior.
- [ ] Confirm partial observations accumulate monotonically and later failures do not erase earlier committed facts.
- [ ] Confirm all failure precedence and terminal status equations match the specification.
- [ ] Confirm no phrase, comment, or test overclaims out-of-band freshness or treats a pre-solve snapshot as behavior.

### Step 4: Commit and stop

- [ ] Commit only Task 5 documentation/checklist changes.
- [ ] Obtain final independent review of exact scope, complete verification output, contract parity, and architecture wording.
- [ ] Stop after review. Push/PR/merge, Release deployment, runtime verification, and any live behavioral qualification require separate authorization and are not part of this plan.

## Execution Ledger

During implementation, append only factual observations here: baseline counts, per-task commit hashes, independent review verdicts, final test counts, and any approved deviation. Do not use this section to change behavior without amending the specification first.

- Task 1 baseline: the original focused command passed 68/68. Its existing Release build target copied the net48 companion payload before this plan's no-deploy guard was added; no Rhino/MCP call or restart occurred, and the running net8 payload remained locked by Rhino. Every later managed command uses an explicitly absent `RhinoPluginDir`.
- Task 1 RED/GREEN: focused receipt/edit/script seam passed 86/86 with the no-deploy guard.
- Task 1 complete managed suite: the first guarded run hit the known order-sensitive `ReconstructionJobLedgerTests.List_AppliesLimitNewestFirst` failure at 3744/3745; the immediate unchanged rerun passed 3745/3745.
- Task 1 route phase audit: `SetValue` reserves after target/type/value validation and before the first `Minimum`/`Maximum`/`Value` setter, then schedules after the last committed setter and projects the receipt in the terminal response. `SetScript` reserves after target/capability/read-vs-write validation and before `SetSource`/`ScriptCode`, then schedules after dirty expiration and pin-description restoration before projecting the receipt. `ApplyEdit` reserves after epoch/admitted-array inspection and before solve suspension or the first route mutation; after mutations it restores standalone solver ownership, captures only the compatibility pre-solve structural snapshot, requests one solve when the five-field commit count is positive, and projects the same receipt in success or failure data.
- Task 1 final focused seam: 90/90 passed, including clean committed edit, partial/exceptional edit, zero/group-only edit, solver-locked scheduling, and unknown schedule acceptance.
- Task 1 final complete managed suite: the first guarded run again hit only `ReconstructionJobLedgerTests.List_AppliesLimitNewestFirst` at 3748/3749; the immediate unchanged rerun passed 3749/3749.
- Task 1 multi-target managed build: net48, net7.0, and net8.0 compiled with 268 warnings and 0 errors using the absent no-deploy target.
- Task 1 production delta before commit: 420 additions and 57 deletions across `GhSolveReceiptRegistry.cs`, `GrasshopperHandler.Readiness.cs`, and `GrasshopperHandler.cs`; `git diff --check` passed.
- Task 1 independent review of `35d7d2ee` reproduced 90/90 focused and 3749/3749 complete managed tests, then stopped Task 2 because `gh_edit` counted attempted rather than confirmed slider/property mutations, could lose a prior commit when a later setter threw, allowed missing reflected mutators to manufacture counts, and emitted a null readiness field in some group-only wrapper shapes.
- Task 1 repair makes operation counts monotonic at confirmed mutator returns, retains a prior confirmed commit through later failure, represents an indeterminate first mutator failure as unknown commitment, refuses no-op/missing-mutator operations without issuing readiness, and omits the readiness field from every zero/group-only wrapper. Causal tests cover create/delete/connect/disconnect, no-op and partial slider edits, reservation capacity, `SetScript` false/null/throwing outcomes, response-projection failure, and success/failure wrapper shapes.
- Task 1 repaired focused seam: 106/106 passed. The first repair-only run exposed and corrected a dynamic test-fixture ordering defect before the connect/disconnect reflection path was accepted.
- Task 1 repaired complete managed suite: 3765/3765 passed on the first guarded run.
- Task 1 repaired multi-target managed build: net48, net7.0, and net8.0 compiled with 268 warnings and 0 errors using the absent no-deploy target. The complete Task 1 production delta is 564 additions and 87 deletions across the same three production owners; `git diff --check` passed. No Rhino/MCP contact or deployment occurred.
- Task 1 repair review of `00d70584` reproduced 106/106 focused and 3765/3765 complete managed tests and confirmed every earlier issue closed, then identified that the real Rhino 8 `GH_Document.AddObject` and `RemoveObject` methods return Boolean and the code still counted a returned `false` as a commit. The two causal false-return tests failed RED with manufactured counts of one.
- Task 1 final host-return repair requires exact Boolean `true` before create/delete count advancement; `false` retains an operation error and zero commit, while a thrown or non-Boolean return remains unknown. Boolean `true` and `false` are causally covered for both routes.
- Task 1 final verification: 109/109 focused and 3768/3768 complete managed tests passed; net48, net7.0, and net8.0 compiled with 268 warnings and 0 errors. The complete Task 1 production delta is 582 additions and 91 deletions across the same three production owners; `git diff --check` passed. No Rhino/MCP contact or deployment occurred.
- Task 1 final independent review of `713ac187` found no P0-P3 issues, independently reproduced 109/109 focused and 3768/3768 complete managed tests, and approved Task 2.
- Task 2 RED/GREEN: the new fenced-snapshot test first failed to compile because the registry did not expose an owning-boundary fence observation; after implementation, the Task 2 focused seam passed 111/111. Hostile tests prove fence-before-object/output reads on one thread and zero data reads for invalid, pending, stale, superseded, locked, replaced, wrong-document, unknown, terminal-evicted, and missing/process-restarted receipts.
- Task 2 typed evidence: one volatile-data acquisition supplies both the compatible string preview and fenced typed projection. Only finite host `Point3d` values enter coordinate triples; truncation, count mismatch, mixed values, nonfinite coordinates, and data-access failure retain closed incomplete reasons, while all-nonpoint outputs are omitted.
- Task 2 complete managed suite: 3785/3785 passed on the first guarded run. The multi-target build compiled net48, net7.0, and net8.0 with 268 warnings and 0 errors. Task 2 production delta before commit is 298 additions and 52 deletions across `GrasshopperHandler.cs` and `GhSolveReceiptRegistry.cs`; `git diff --check` passed. No Rhino/MCP contact or deployment occurred.
- Task 2 independent review of `e625a06c` reproduced 111/111 focused and 3785/3785 complete managed tests, then refused Task 3 because fenced `TakeSnapshot` called the production readiness owner before `CheckFencedRead`; that readiness owner enumerates `document.Objects`. The review also found that the existing 16-minute ready-receipt test covered terminal eviction rather than the distinct pending-expiry fence status.
- Task 2 repair resolves the active document without enumerating data, checks the fence, and only after an allowed gate runs the readiness owner and snapshot extraction. The unfenced order is unchanged. The hostile readiness fake now reads `Objects`, so every refused receipt causally proves zero readiness and extraction reads; a pending receipt at its exact ten-minute boundary proves `readiness_receipt_expired`, while the retained 16-minute ready case proves terminal eviction.
- Task 2 repaired verification: 111/111 focused tests passed. The first complete managed run hit only the known order-sensitive `ReconstructionJobLedgerTests.List_AppliesLimitNewestFirst` failure at 3784/3785; the immediate unchanged rerun passed 3785/3785. The multi-target build compiled net48, net7.0, and net8.0 with 268 warnings and 0 errors. The complete Task 2 production delta is 309 additions and 52 deletions across the same two production owners; `git diff --check` passed. No Rhino/MCP contact or deployment occurred.
- Task 2 repaired independent review of `e3b67d9e` found no P0-P3 issues, independently reproduced 111/111 focused and 3785/3785 complete managed tests plus the three-target build, and approved Task 3.
- Task 3 RED/GREEN: the initial Python seam failed 24 tests at every absent boundary. After implementation and adversarial additions, the prescribed four-file seam passed 99/99, and the existing RookChat creation contract passed 30/30 separately. Exact receipt validation, eager ready-wait correlation, deferred no-sleep return, monotonic composite failures, fenced snapshot argument parity, script aliases, updates, and Chirp canonical/direct receipt preservation are causally covered.
- Task 3 static verification: all modified Python sources/tests compile; the two script helper ASTs contain no sleep or retired settle call; `_await_gh_solve_settle` and `verification_settle_seconds` are absent from both production owners; `git diff --check` passed. No Rhino/MCP contact or deployment occurred.
- Task 3 independent review of `7c7cb676` reproduced 99/99 prescribed tests and 30/30 RookChat parity tests, then refused Task 4 because receipt admission failures erased malformed returned evidence and used the `source_write` phase, thrown readiness waits were mislabeled `post_write_verification`, and direct Chirp entered canonical recording/metrics machinery.
- Task 3 repair separates raw returned receipt evidence from validated managed authority, assigns committed receipt-admission failures and all wait failures to `solve_readiness`, and extracts one shared recorder-free Chirp orchestration helper used by canonical and direct dispatch. Canonical alone owns session recording; direct deterministic Chirp is causally guarded against recorder entry.
- Task 3 repaired verification: 105/105 prescribed tests and 30/30 existing RookChat creation-parity tests passed. Python compilation, exact one-final-write/no-sleep AST checks, and `git diff --check` passed. No Rhino/MCP contact or deployment occurred.
- Task 4 initial RED/GREEN: the new common-module tests first failed at import because no behavioral-acceptance owner existed. The initial focused seam passed 61/61 and established canonical source closure, exact Prime/direct terminal custody, latest-terminal selection, same-receipt wait/fence correlation, one-control-at-a-time perturbation, distinct mutation receipts, restoration equality, the reviewed generic predicates, and thin point-row compatibility mapping.
- Task 4 independent review of `12f6bfdf` refused Task 5 because mutation classification trusted supplied route facts, zero-point outputs could pass constant predicates vacuously, failed prefixes did not authenticate the first failure boundary, malformed executor returns fabricated exceptions, noncanonical evaluator inputs could fail incidentally, duplicate group IDs were admitted, and the Opus/Qwen tests hardcoded hashes and outcomes without retaining the source bytes.
- Task 4 repair derives the closed route projection from exact target/arguments/dispatch/result facts, retains false/null direct commit receipts without admitting them, treats public readonly routes as observational and all other uncovered Grasshopper mutations as legacy, admits only recognized zero-dispatch refusals, requires a positive point count, rejects duplicate group IDs, and uses one strict failed-trace state machine that matches the exact first failure and forbids trailing events. Complete probes require exact positive managed commit facts and pending/ready issued receipts for every perturbation and restoration. Malformed executor returns stop as `probe_trace_invalid` without a fabricated exception; noncanonical public evaluator inputs raise the one explicit `input_not_canonical_json` boundary; oversized JSON integers fail projection without escaping through `math.isfinite`.
- Task 4 authentic compatibility anchors are now retained byte-for-byte as immutable fixtures. Tests recompute the exact Opus snapshot hash `BD25176EC4C7AF7C7A4559C87F97FA4F092FB394E0D30D38A57D5529FAC92F48` and Qwen snapshot hash `4B3E44B853D7EEC44D6052D2C4442BEB4CEE46BD3E728C14781FCDDB43C87AE8`, then derive the historical compatibility mapping from the reviewed immutable legacy-evaluation artifact. Opus maps to six passes; Qwen maps to exactly `adjustable_step_present` and `point_count_equals_count` failures, with unsupported X causality unproven.
- Task 4 repaired production boundary: `gh_behavioral_acceptance.py` has 1,985 nonblank lines and the compatibility CLI has 158. The module exposes only the eight reviewed pure functions; it has no transport construction, target resolution, model/provider import, process launch, retry loop, sleep readiness, or task-specific component GUID/name. The size implements the approved closed trace, receipt, projection, probe, and seven-predicate contracts in one owner rather than adding a second evaluator or another production module.
- Task 4 first repair review of `db5b3ed4` independently reproduced 75/75 and confirmed every earlier issue closed, then refused Task 5 because malformed relay IDs, terminal-output IDs absent from the component projection, and dangling flow endpoints could still produce an overall pass; it also found the Task 4 fixture-file inventory missing.
- Task 4 final projection repair requires every relay to be an exact component short ID, keeps component and relay identities disjoint, requires the terminal output owner to exist among projected components, and validates both flow endpoints against the component/relay universe. Causal tests cover malformed relay, dangling output owner, and dangling source/target flow endpoints. The Task 4 inventory now names all three retained fixtures.
- Task 4 final repaired verification: focused tests passed 79/79; both Python files compiled; the retained fixture hashes, forbidden-surface scan, `git diff --check`, and canonical artifact-byte check passed. No Rhino, Grasshopper, MCP, model, provider, deployment, or live target contact occurred.
