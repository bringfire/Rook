# LM8L/LM8M Managed-Receipt Affine Verifier Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Replace LM8I's post-worker settle verifier with an optional LM8K managed-receipt profile and extend LM8J to produce an independently audited LM8M N=20 comparison identity without changing the historical default path.

**Architecture:** LM8I remains the single-attempt live owner and gains a profile dispatcher: settle_v1 calls the current implementation unchanged, while managed_receipt_v2 consumes the receipt emitted by the worker mutation, waits once, and performs one fenced read. LM8J remains subprocess-only; managed mode changes its run identity to LM8M and independently recomputes child receipt invariants from three bounded stage artifacts.

**Tech Stack:** Python 3.10, pytest, argparse, asyncio, JSON/JSONL artifacts, existing Rook MCP tool executor, LM8K solve-readiness receipt tools.

## Global Constraints

- Existing PlannerWorkerContractRequest, worker prompt, worker protocol, publication support, affine evidence, scalar applier, and LM8K product contracts remain unchanged.
- scripts/lm8i_affine_publication_shape_support_probe.py remains the only single-attempt affine support probe.
- scripts/lm8j_affine_support_repeatability_probe.py remains the only affine repeatability wrapper.
- settle_v1 remains the default and preserves historical commands, tool sequence, run prefixes, schemas, summaries, and decisions.
- managed_receipt_v2 changes only verification after the worker-authored gh_set_value mutation.
- Fixture readiness remains lm8i_legacy_setup_v1.
- Managed verification uses exactly one wait, one fenced read, zero settle reads, and no post-mutation gh_solve.
- readiness_wait_timeout_ms is fixed at 10000; child_attempt_timeout_s remains 600.
- No readiness status polling, second wait, sleep-based readiness, unfenced read, or settle fallback is allowed in managed mode.
- Receipt IDs are held raw only in memory and persisted only as sha256:<lowercase-hex>.
- Mutation epoch must be positive.
- Pending solution_run_epoch must be null.
- Ready solution_run_epoch must be strictly greater than the pending completed_solution_run_epoch.
- Wait and fenced-read session, mutation, solution-run, and completed-run provenance must match exactly.
- Child managed invariant failure is rejected / verifier_readiness / managed_verifier_invariant_failed.
- An accepted child with missing, malformed, or inconsistent managed artifacts becomes LM8M wrapper_error.
- Managed invariants apply only after live_set_value_dispatched is true.
- No live Rhino/Grasshopper or model run occurs in the implementation PR.
- No new dependencies, new probe scripts, gh_edit, retry, replacement attempts, Planner path, or support forcing.

---

## File Structure

**Modify: scripts/lm8i_affine_publication_shape_support_probe.py**

Owns verifier profile constants/CLI, managed receipt parsing and hashing, managed mutation/wait/read summaries, fail-closed child decisions, and profile-specific dispatch. The existing settle implementation remains callable without semantic edits.

**Modify: mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py**

Owns LM8I baseline replayability tests, fake LM8K tool responses, managed happy-path tests, exact terminal normalization, provenance mismatch tests, artifact redaction, and call-count guards.

**Modify: scripts/lm8j_affine_support_repeatability_probe.py**

Owns profile-aware LM8J/LM8M run identity, managed child command forwarding, independent child-artifact auditing, contradiction classification, attempt rows, and LM8M summary accounting.

**Modify: mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py**

Owns LM8J preservation tests, LM8M identity tests, fake managed child artifacts, independent audit tests, canonical predicate tests, and summary counter tests.

**Existing design authority: docs/superpowers/specs/2026-07-10-lm8l-managed-receipt-verifier-migration-design.md**

Do not amend the design during implementation unless review exposes a genuine contradiction.

---

### Task 1: Add The LM8I Verifier Profile Seam And Preserve settle_v1

**Files:**
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py:74-160
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py:1275-1344
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py:1830-2296
- Test: mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py:206-286
- Test: mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py:482-936

**Interfaces:**
- Produces: SETTLE_VERIFIER_PROFILE = "settle_v1"
- Produces: MANAGED_VERIFIER_PROFILE = "managed_receipt_v2"
- Produces: READINESS_WAIT_TIMEOUT_MS = 10_000
- Produces: _manifest(*, model: str, endpoint: str, temperature: float, canonical_evidence: bool, verifier_profile: str = SETTLE_VERIFIER_PROFILE) -> dict[str, Any]
- Produces: _run_probe(*, model: str, endpoint: str, temperature: float, timeout_s: float, excerpt_chars: int, run_root: str | Path, canonical_evidence: bool, verifier_profile: str = SETTLE_VERIFIER_PROFILE, tool_executor=None, publication_runner=None) -> Path
- Consumes later: Task 2 dispatches on verifier_profile; Task 4 forwards the managed profile from LM8J.

- [ ] **Step 1: Write failing CLI and manifest preservation tests**

Add exact tests:

```python
def test_cli_defaults_to_settle_v1_without_changing_canonical_shape():
    args = PROBE._args([])
    assert args.verifier_profile == PROBE.SETTLE_VERIFIER_PROFILE
    assert args.canonical_evidence is True


def test_cli_accepts_only_managed_receipt_v2_as_the_alternate_profile():
    args = PROBE._args(["--verifier-profile", "managed_receipt_v2"])
    assert args.verifier_profile == PROBE.MANAGED_VERIFIER_PROFILE

    with pytest.raises(SystemExit):
        PROBE._args(["--verifier-profile", "unknown"])

    with pytest.raises(SystemExit):
        PROBE._args(["--readiness-wait-timeout-ms", "1"])


def test_settle_manifest_is_exact_historical_shape():
    manifest = PROBE._manifest(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        canonical_evidence=True,
        verifier_profile=PROBE.SETTLE_VERIFIER_PROFILE,
    )
    assert manifest["schema"] == PROBE.SCRIPT_SCHEMA
    assert "verifier_profile" not in manifest
    assert "verifier_mechanism" not in manifest
    assert "fixture_readiness_profile" not in manifest
    assert "readiness_wait_timeout_ms" not in manifest


def test_managed_manifest_records_only_the_new_profile_metadata():
    manifest = PROBE._manifest(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=PROBE.DEFAULT_TEMPERATURE,
        canonical_evidence=True,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )
    assert manifest["verifier_profile"] == "managed_receipt_v2"
    assert manifest["verifier_mechanism"] == "managed_solve_readiness_receipt"
    assert manifest["fixture_readiness_profile"] == "lm8i_legacy_setup_v1"
    assert manifest["readiness_wait_timeout_ms"] == 10_000
```

Add a default-path replayability test using _fixture_responses_for_success and
_published_action(3.0). Assert the post-worker tool tail remains:

```python
assert [name for name, _ in executor.calls][-3:] == [
    "gh_set_value",
    "gh_solve",
    "gh_inspect_output",
]
assert not (run_dir / "readiness_wait_summary.json").exists()
verify = json.loads((run_dir / "verify_scalar_output_summary.json").read_text())
assert "verifier_profile" not in verify
assert "settle_read_count" not in verify
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py -q
```

Expected: FAIL because --verifier-profile and the constants/signatures do not exist.

- [ ] **Step 3: Add constants and CLI parsing**

Add beside the existing verifier constants:

```python
SETTLE_VERIFIER_PROFILE = "settle_v1"
MANAGED_VERIFIER_PROFILE = "managed_receipt_v2"
VERIFIER_PROFILES = (
    SETTLE_VERIFIER_PROFILE,
    MANAGED_VERIFIER_PROFILE,
)
READINESS_WAIT_TIMEOUT_MS = 10_000
VERIFIER_MECHANISM = "managed_solve_readiness_receipt"
FIXTURE_READINESS_PROFILE = "lm8i_legacy_setup_v1"
```

Add to _args:

```python
parser.add_argument(
    "--verifier-profile",
    choices=VERIFIER_PROFILES,
    default=SETTLE_VERIFIER_PROFILE,
)
```

Do not add a readiness timeout argument.

- [ ] **Step 4: Thread the profile without changing default artifacts**

Change _manifest to accept verifier_profile. Build the existing mapping first,
then add managed fields only for managed_receipt_v2:

```python
def _manifest(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    canonical_evidence: bool,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> dict[str, Any]:
    manifest = {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "model": model,
        "endpoint": endpoint,
        "temperature": temperature,
        "canonical_evidence": canonical_evidence,
        "attempts": 1,
        "initial_editable_value": INITIAL_EDITABLE_VALUE,
        "factor_value": FACTOR_VALUE,
        "offset_value": OFFSET_VALUE,
        "initial_observed_output": INITIAL_OBSERVED_OUTPUT,
        "expected_output_value": EXPECTED_OUTPUT_VALUE,
        "projection_id": EXPECTED_AFFINE_PROJECTION["projection_id"],
        "publication_support_enabled": True,
        "publication_support_budget": 1,
        "support_eligibility": "exact_skeletal_action_request_missing_action_id",
        "worker_retry_enabled": False,
        "planner_model": None,
        "gh_edit_enabled": False,
    }
    if verifier_profile == MANAGED_VERIFIER_PROFILE:
        manifest.update(
            {
                "verifier_profile": verifier_profile,
                "verifier_mechanism": VERIFIER_MECHANISM,
                "fixture_readiness_profile": FIXTURE_READINESS_PROFILE,
                "readiness_wait_timeout_ms": READINESS_WAIT_TIMEOUT_MS,
            }
        )
    return manifest
```

Add verifier_profile with a default to _run_probe. Pass it to _manifest. In
main, pass args.verifier_profile to _run_probe. Do not alter _decision_record
yet.

- [ ] **Step 5: Run the complete LM8I test file**

Run the same focused command.

Expected: PASS, including every pre-existing test and the new profile-seam
tests. The default replayability test must prove the old tool sequence and old
artifact shape.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lm8i_affine_publication_shape_support_probe.py mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py
git commit -m "feat(lm8l): add affine verifier profile seam"
```

---

### Task 2: Implement The Managed Happy Path And Bounded Stage Artifacts

**Files:**
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py:189-360
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py:1450-1626
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py:2220-2283
- Test: mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py

**Interfaces:**
- Produces: MANAGED_MUTATION_SCHEMA
- Produces: MANAGED_WAIT_SCHEMA
- Produces: MANAGED_VERIFY_SCHEMA
- Produces: MANAGED_DECISION_SCHEMA
- Produces: _receipt_id_sha256(receipt_id: str) -> str
- Produces: _managed_receipt_from_tool_result(result: Any) -> Mapping[str, Any] | None
- Produces: _dispatch_set_value_managed_receipt_and_verify(*, tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]], editable_component_guid: str, addition_component_guid: str, worker_value: float | int, expected_value: float | int) -> dict[str, Any]
- Produces: _dispatch_set_value_with_profile(*, verifier_profile: str, tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]], editable_component_guid: str, addition_component_guid: str, worker_value: float | int, expected_value: float | int) -> dict[str, Any]
- Consumes: Existing _dispatch_set_value_solve_and_verify for settle_v1 unchanged.
- Consumes later: Task 3 hardens all failure paths; Task 5 audits emitted schemas.

- [ ] **Step 1: Add fake LM8K receipt builders and a failing happy-path test**

Add test helpers:

```python
RECEIPT_ID = "opaque-lm8l-receipt-1"


def _receipt(
    status,
    *,
    solution_run_epoch,
    completed_solution_run_epoch,
    reason=None,
):
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": RECEIPT_ID,
        "document_session_id": "session-1",
        "mutation_epoch": 13,
        "solution_run_epoch": solution_run_epoch,
        "completed_solution_run_epoch": completed_solution_run_epoch,
        "status": status,
        "reason": reason,
    }


def _managed_success_responses():
    responses = _fixture_tool_responses()
    responses.update(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"created": True}},
            "gh_set_value": {
                "success": True,
                "data": {
                    "Guid": "EDITABLE-GUID-1",
                    "Value": "3.0",
                    "solve_readiness_receipt": _receipt(
                        "pending",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "gh_wait_for_solve_readiness": {
                "success": True,
                "data": {
                    "schema": "rook.gh_solve_readiness_wait_result:v1",
                    "wait_status": "ready",
                    "receipt": _receipt(
                        "ready",
                        solution_run_epoch=42,
                        completed_solution_run_epoch=42,
                    ),
                },
            },
            "gh_inspect_output": [
                {
                    "success": True,
                    "data": {"data_count": 1, "preview": ["5.5"]},
                },
                {
                    "success": True,
                    "data": {
                        "data_count": 1,
                        "preview": ["7.5"],
                        "readiness_fenced": True,
                        "readiness_receipt_id": RECEIPT_ID,
                        "document_session_id": "session-1",
                        "mutation_epoch": 13,
                        "solution_run_epoch": 42,
                        "completed_solution_run_epoch": 42,
                    },
                },
            ],
        }
    )
    return responses
```

Add a run test that publishes _published_action(3.0), selects
MANAGED_VERIFIER_PROFILE, and asserts:

```python
tool_tail = [name for name, _ in executor.calls][-3:]
assert tool_tail == [
    "gh_set_value",
    "gh_wait_for_solve_readiness",
    "gh_inspect_output",
]
assert "gh_solve" not in tool_tail

decision = json.loads((run_dir / "decision.json").read_text())
assert decision["decision"] == "accepted"
assert decision["reason"] == "verify_scalar_output_succeeded"

mutation = json.loads((run_dir / "live_set_value_summary.json").read_text())
wait = json.loads((run_dir / "readiness_wait_summary.json").read_text())
verify = json.loads((run_dir / "verify_scalar_output_summary.json").read_text())

assert mutation["managed_mutation"]["solution_run_epoch"] is None
assert mutation["managed_mutation"]["completed_solution_run_epoch"] == 41
assert wait["solution_run_epoch"] == 42
assert verify["fenced_output_read_count"] == 1
assert verify["settle_read_count"] == 0
```

Scan all four managed artifacts and assert RECEIPT_ID is absent.

- [ ] **Step 2: Run the happy-path test and confirm RED**

Run the single new test with -v.

Expected: FAIL because managed dispatch and managed artifacts do not exist.

- [ ] **Step 3: Add schemas and receipt helpers**

Add constants:

```python
GH_READINESS_RECEIPT_SCHEMA = "rook.gh_solve_readiness_receipt:v1"
GH_READINESS_WAIT_SCHEMA = "rook.gh_solve_readiness_wait_result:v1"
MANAGED_MUTATION_SCHEMA = "rook.lm8l_managed_mutation_summary:v1"
MANAGED_WAIT_SCHEMA = "rook.lm8l_readiness_wait_summary:v1"
MANAGED_VERIFY_SCHEMA = "rook.lm8l_fenced_output_verification_summary:v1"
MANAGED_DECISION_SCHEMA = "rook.lm8l_managed_verifier_decision:v1"
```

Add exact helpers:

```python
def _is_epoch(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _receipt_id_sha256(receipt_id: str) -> str:
    return _sha256_text(receipt_id)


def _managed_receipt_from_tool_result(result: Any) -> Mapping[str, Any] | None:
    data = _tool_data(result)
    if not isinstance(data, Mapping):
        return None
    for key in ("solve_readiness_receipt", "readiness_receipt", "receipt"):
        receipt = data.get(key)
        if isinstance(receipt, Mapping):
            return receipt
    return None


def _managed_wait_data(result: Any) -> Mapping[str, Any] | None:
    data = _tool_data(result)
    return data if isinstance(data, Mapping) else None
```

Do not add recursive receipt search. Authority is the documented bounded data
envelope.

- [ ] **Step 4: Implement managed mutation, wait, and fenced read**

Create _dispatch_set_value_managed_receipt_and_verify with this exact return
contract:

```python
{
    "live_set_value_summary": dict,
    "readiness_wait_summary": dict | None,
    "verify_scalar_output_summary": dict | None,
    "decision": dict,
}
```

On the happy path:

1. Call gh_set_value once.
2. Extract and validate the pending receipt.
3. Create managed_mutation with schema, pending status, receipt hash, session,
   positive mutation epoch, null solution run, and prior completed run.
4. Call gh_wait_for_solve_readiness once with the raw ID and 10000.
5. Create readiness_wait_summary from the ready receipt.
6. Require ready run > prior completed run.
7. Call gh_inspect_output once with the same raw ID.
8. Create MANAGED_VERIFY_SCHEMA summary.
9. Return accepted only after all provenance and scalar checks pass.

Use a helper for the managed decision metadata:

```python
def _managed_decision_metadata(
    *,
    readiness_wait_count: int,
    fenced_output_read_count: int,
    settle_read_count: int,
    failed_invariants: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "managed_verifier": {
            "schema": MANAGED_DECISION_SCHEMA,
            "verifier_profile": MANAGED_VERIFIER_PROFILE,
            "verifier_mechanism": VERIFIER_MECHANISM,
            "fixture_readiness_profile": FIXTURE_READINESS_PROFILE,
            "readiness_wait_timeout_ms": READINESS_WAIT_TIMEOUT_MS,
            "readiness_wait_count": readiness_wait_count,
            "fenced_output_read_count": fenced_output_read_count,
            "settle_read_count": settle_read_count,
            "failed_invariants": list(failed_invariants),
        }
    }
```

- [ ] **Step 5: Add the profile dispatcher and artifact writing**

Keep _dispatch_set_value_solve_and_verify unchanged. Add:

```python
async def _dispatch_set_value_with_profile(
    *,
    verifier_profile: str,
    tool_executor,
    editable_component_guid: str,
    addition_component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]:
    if verifier_profile == SETTLE_VERIFIER_PROFILE:
        result = await _dispatch_set_value_solve_and_verify(
            tool_executor=tool_executor,
            editable_component_guid=editable_component_guid,
            addition_component_guid=addition_component_guid,
            worker_value=worker_value,
            expected_value=expected_value,
        )
        result["readiness_wait_summary"] = None
        return result
    if verifier_profile == MANAGED_VERIFIER_PROFILE:
        return await _dispatch_set_value_managed_receipt_and_verify(
            tool_executor=tool_executor,
            editable_component_guid=editable_component_guid,
            addition_component_guid=addition_component_guid,
            worker_value=worker_value,
            expected_value=expected_value,
        )
    raise ValueError(f"unsupported_verifier_profile:{verifier_profile}")
```

In _run_probe, call the dispatcher. Write readiness_wait_summary.json only
when non-None. Merge managed decision metadata from dispatch["decision"] into
the final _decision_record extra. Leave settle artifacts unchanged.

- [ ] **Step 6: Run LM8I tests and inspect generated fake artifacts**

Run the full LM8I test file.

Expected: PASS. Confirm the managed happy-path test proves the 1/1/0 sequence,
run advancement, exact provenance, and receipt-ID redaction.

- [ ] **Step 7: Commit**

```powershell
git add scripts/lm8i_affine_publication_shape_support_probe.py mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py
git commit -m "feat(lm8l): add receipt-fenced affine verifier"
```

---

### Task 3: Fail Closed On Managed Readiness Outcomes And Invariants

**Files:**
- Modify: scripts/lm8i_affine_publication_shape_support_probe.py
- Test: mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py

**Interfaces:**
- Produces: _normalize_readiness_failure(result: Any, stage: str) -> str
- Produces: stable failed_invariants values used by LM8M diagnostics.
- Consumes: Task 2 managed dispatch and stage schemas.
- Consumes later: Task 5 independently recomputes the same rules without importing LM8I.

- [ ] **Step 1: Write parameterized terminal-normalization tests**

Add a table covering exact shipped outcomes:

```python
@pytest.mark.parametrize(
    ("result", "stage", "expected_reason"),
    [
        (
            {
                "success": True,
                "data": {
                    "wait_status": "timeout",
                    "receipt": _receipt(
                        "pending",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                    ),
                },
            },
            "wait",
            "readiness_wait_timeout",
        ),
        (
            {
                "success": True,
                "data": {
                    "wait_status": "terminal",
                    "receipt": _receipt(
                        "unknown",
                        solution_run_epoch=None,
                        completed_solution_run_epoch=41,
                        reason="receipt_expired",
                    ),
                },
            },
            "wait",
            "readiness_receipt_expired",
        ),
        (
            {
                "success": False,
                "data": {
                    "error": "readiness_receipt_not_found_or_evicted_or_process_restarted"
                },
            },
            "wait",
            "readiness_receipt_not_found_or_evicted_or_process_restarted",
        ),
        (
            {"success": False, "data": {"error": "readiness_receipt_not_ready"}},
            "read",
            "readiness_receipt_not_ready",
        ),
    ],
)
def test_normalize_readiness_failure_preserves_product_reason(
    result, stage, expected_reason
):
    assert PROBE._normalize_readiness_failure(result, stage=stage) == expected_reason
```

Add cases for superseded, stale_solution_run, document_replaced,
solver_locked, unknown, and readiness_wait_already_active.

- [ ] **Step 2: Add failing call-budget and invariant tests**

First add full-probe mutation-terminal tests. These are distinct from terminal
wait results because no wait is allowed:

```python
@pytest.mark.parametrize(
    ("receipt_status", "receipt_reason", "expected_reason"),
    [
        ("solver_locked", "solver_locked", "readiness_receipt_solver_locked"),
        ("unknown", "scheduling_unknown", "readiness_receipt_unknown"),
    ],
)
def test_managed_terminal_mutation_receipt_stops_before_wait(
    tmp_path, receipt_status, receipt_reason, expected_reason
):
    responses = _managed_success_responses()
    responses["gh_set_value"]["data"]["solve_readiness_receipt"] = _receipt(
        receipt_status,
        solution_run_epoch=None,
        completed_solution_run_epoch=41,
        reason=receipt_reason,
    )
    executor = FakeToolExecutor(responses)

    def fake_publication_runner(payload, **_kwargs):
        return _published_action(3.0)

    run_dir = PROBE._run_probe(
        model=PROBE.DEFAULT_MODEL,
        endpoint=PROBE.DEFAULT_ENDPOINT,
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
        tool_executor=executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "rejected"
    assert decision["phase"] == "verifier_readiness"
    assert decision["reason"] == expected_reason
    names = [name for name, _ in executor.calls]
    assert names.count("gh_wait_for_solve_readiness") == 0
    assert names.count("gh_inspect_output") == 1  # fixture setup only
```

For each terminal wait outcome, run managed _run_probe and assert:

```python
assert decision["decision"] == "rejected"
assert decision["phase"] == "verifier_readiness"
assert decision["reason"] == expected_reason
assert [name for name, _ in executor.calls].count(
    "gh_wait_for_solve_readiness"
) == 1
assert [name for name, _ in executor.calls].count("gh_inspect_output") == 1
# One inspect is fixture setup only; no post-mutation inspect occurred.
```

Add separate tests for:

- missing receipt
- wrong receipt schema
- mutation_epoch 0
- pending solution_run_epoch non-null
- pending completed_solution_run_epoch missing/non-integer
- ready run <= prior completed run
- receipt hash mismatch
- session mismatch
- mutation epoch mismatch
- wait solution run != wait completed run
- read run != wait run
- read completed run != read run
- readiness_fenced false/missing
- scalar 7.5 with any provenance mismatch
- scalar mismatch with correct provenance

Every structural/count/provenance mismatch must assert:

```python
assert decision["decision"] == "rejected"
assert decision["phase"] == "verifier_readiness"
assert decision["reason"] == "managed_verifier_invariant_failed"
assert decision["managed_verifier"]["failed_invariants"]
assert decision["managed_verifier"]["readiness_wait_count"] == 1
assert decision["managed_verifier"]["fenced_output_read_count"] in (0, 1)
assert decision["managed_verifier"]["settle_read_count"] == 0
```

- [ ] **Step 3: Run the new failure tests and confirm RED**

Run only tests matching managed, readiness, provenance, and invariant.

Expected: FAIL until the normalizer and fail-closed paths are implemented.

- [ ] **Step 4: Implement exact failure normalization**

Add:

```python
READINESS_FAILURE_REASONS = {
    "readiness_receipt_superseded",
    "readiness_receipt_stale_solution_run",
    "readiness_receipt_document_replaced",
    "readiness_receipt_solver_locked",
    "readiness_receipt_unknown",
    "readiness_receipt_expired",
    "readiness_receipt_not_found_or_evicted_or_process_restarted",
    "readiness_receipt_not_ready",
    "readiness_wait_already_active",
}


def _normalize_readiness_failure(result: Any, *, stage: str) -> str:
    data = _tool_data(result)
    if isinstance(data, Mapping):
        error = data.get("error")
        if isinstance(error, str) and error in READINESS_FAILURE_REASONS:
            return error
        if stage == "wait" and data.get("wait_status") == "timeout":
            return "readiness_wait_timeout"
        receipt = data.get("receipt")
        if isinstance(receipt, Mapping):
            if (
                data.get("wait_status") == "terminal"
                and receipt.get("status") == "unknown"
                and receipt.get("reason") == "receipt_expired"
            ):
                return "readiness_receipt_expired"
            status = receipt.get("status")
            status_reason = {
                "superseded": "readiness_receipt_superseded",
                "document_replaced": "readiness_receipt_document_replaced",
                "solver_locked": "readiness_receipt_solver_locked",
                "unknown": "readiness_receipt_unknown",
                "pending": "readiness_receipt_not_ready",
            }.get(status)
            if status_reason:
                return status_reason
    return "readiness_receipt_malformed"
```

Before requiring pending status, normalize terminal mutation receipts without
calling wait:

```python
def _mutation_receipt_terminal_reason(receipt: Mapping[str, Any]) -> str | None:
    status = receipt.get("status")
    if status == "solver_locked":
        return "readiness_receipt_solver_locked"
    if status == "unknown":
        if receipt.get("reason") == "receipt_expired":
            return "readiness_receipt_expired"
        return "readiness_receipt_unknown"
    return None
```

Persist the bounded terminal mutation record, set counts to 0/0/0, and return
rejected / verifier_readiness with the exact reason. Only status pending may
proceed to gh_wait_for_solve_readiness.

Do not collapse known product errors into unknown.

- [ ] **Step 5: Implement invariant collection before acceptance**

Use a pure helper returning stable failures:

```python
def _managed_provenance_failures(
    *,
    mutation: Mapping[str, Any],
    wait: Mapping[str, Any],
    read: Mapping[str, Any],
) -> tuple[str, ...]:
    failures: list[str] = []
    mutation_epoch = mutation.get("mutation_epoch")
    if not _is_epoch(mutation_epoch) or mutation_epoch == 0:
        failures.append("mutation_epoch_not_positive")
    if mutation.get("solution_run_epoch") is not None:
        failures.append("pending_solution_run_epoch_not_null")
    prior = mutation.get("completed_solution_run_epoch")
    ready_run = wait.get("solution_run_epoch")
    if not _is_epoch(prior) or not _is_epoch(ready_run) or ready_run <= prior:
        failures.append("post_mutation_solution_run_not_advanced")
    if wait.get("completed_solution_run_epoch") != ready_run:
        failures.append("wait_completed_solution_run_mismatch")
    for field in ("receipt_id_sha256", "document_session_id", "mutation_epoch"):
        if not (
            mutation.get(field) == wait.get(field) == read.get(field)
        ):
            failures.append(f"{field}_mismatch")
    if read.get("solution_run_epoch") != ready_run:
        failures.append("read_solution_run_mismatch")
    if read.get("completed_solution_run_epoch") != ready_run:
        failures.append("read_completed_solution_run_mismatch")
    if read.get("readiness_fenced") is not True:
        failures.append("readiness_fenced_not_true")
    return tuple(failures)
```

Guard types before comparisons so malformed values produce bounded invariant
failures rather than TypeError.

- [ ] **Step 6: Run LM8I plus adjacent LM8K tests**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_gh_solve_readiness_live_smoke.py -q
```

Expected: PASS. No Rhino/GH process is required; all tests use fakes.

- [ ] **Step 7: Commit**

```powershell
git add scripts/lm8i_affine_publication_shape_support_probe.py mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py
git commit -m "fix(lm8l): fail closed on readiness invariants"
```

---

### Task 4: Add LM8M Run Identity And Managed Child Forwarding

**Files:**
- Modify: scripts/lm8j_affine_support_repeatability_probe.py:18-188
- Modify: scripts/lm8j_affine_support_repeatability_probe.py:518-710
- Test: mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py:36-190
- Test: mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py:791-959

**Interfaces:**
- Produces: SETTLE_VERIFIER_PROFILE and MANAGED_VERIFIER_PROFILE in the wrapper.
- Produces: LM8M_SCRIPT_SCHEMA = "rook.lm8m_affine_managed_receipt_repeatability_probe:v1"
- Produces: _run_identity(verifier_profile: str) -> tuple[str, str]
- Produces: _canonical_evidence(*, attempts: int, model: str, attempt_timeout_s: int, verifier_profile: str = SETTLE_VERIFIER_PROFILE) -> bool
- Produces: _lm8i_command(*, model: str, lm8i_runs_dir: Path, verifier_profile: str = SETTLE_VERIFIER_PROFILE) -> list[str]
- Consumes later: Task 5 adds managed row/audit data to this profile path.

- [ ] **Step 1: Write failing profile identity and baseline preservation tests**

Add:

```python
def test_cli_defaults_to_historical_lm8j_profile():
    args = PROBE._args([])
    assert args.verifier_profile == PROBE.SETTLE_VERIFIER_PROFILE


def test_default_run_identity_is_unchanged():
    assert PROBE._run_identity(PROBE.SETTLE_VERIFIER_PROFILE) == (
        "lm8j",
        PROBE.SCRIPT_SCHEMA,
    )


def test_managed_run_identity_is_lm8m():
    assert PROBE._run_identity(PROBE.MANAGED_VERIFIER_PROFILE) == (
        "lm8m",
        PROBE.LM8M_SCRIPT_SCHEMA,
    )


def test_default_child_command_is_exact_historical_shape(tmp_path):
    command = PROBE._lm8i_command(
        model=PROBE.DEFAULT_MODEL,
        lm8i_runs_dir=tmp_path,
        verifier_profile=PROBE.SETTLE_VERIFIER_PROFILE,
    )
    assert "--verifier-profile" not in command


def test_managed_child_command_forwards_only_profile(tmp_path):
    command = PROBE._lm8i_command(
        model=PROBE.DEFAULT_MODEL,
        lm8i_runs_dir=tmp_path,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )
    assert command[-2:] == ["--verifier-profile", "managed_receipt_v2"]
    assert "--readiness-wait-timeout-ms" not in command
```

Add canonical predicate tests showing managed mode requires N=20, Gemma,
600-second child timeout, and managed profile. The readiness timeout is a fixed
constant, not caller input.

```python
assert PROBE.READINESS_WAIT_TIMEOUT_MS == 10_000
assert PROBE._canonical_evidence(
    attempts=20,
    model="gemma4:12b-it-qat",
    attempt_timeout_s=600,
    verifier_profile="managed_receipt_v2",
) is True
assert PROBE._canonical_evidence(
    attempts=20,
    model="gemma4:12b-it-qat",
    attempt_timeout_s=599,
    verifier_profile="managed_receipt_v2",
) is False
```

- [ ] **Step 2: Run LM8J tests and confirm RED**

Run the LM8J test file.

Expected: FAIL because profile identity does not exist.

- [ ] **Step 3: Implement profile-aware CLI and identity**

Add constants mirroring LM8I without importing LM8I:

```python
SETTLE_VERIFIER_PROFILE = "settle_v1"
MANAGED_VERIFIER_PROFILE = "managed_receipt_v2"
VERIFIER_PROFILES = (SETTLE_VERIFIER_PROFILE, MANAGED_VERIFIER_PROFILE)
LM8M_SCRIPT_SCHEMA = "rook.lm8m_affine_managed_receipt_repeatability_probe:v1"
READINESS_WAIT_TIMEOUT_MS = 10_000
VERIFIER_MECHANISM = "managed_solve_readiness_receipt"
FIXTURE_READINESS_PROFILE = "lm8i_legacy_setup_v1"
```

Add --verifier-profile with default settle_v1. Add:

```python
def _run_identity(verifier_profile: str) -> tuple[str, str]:
    if verifier_profile == SETTLE_VERIFIER_PROFILE:
        return "lm8j", SCRIPT_SCHEMA
    if verifier_profile == MANAGED_VERIFIER_PROFILE:
        return "lm8m", LM8M_SCRIPT_SCHEMA
    raise ValueError(f"unsupported_verifier_profile:{verifier_profile}")
```

Use this profile-aware predicate while retaining the historical default:

```python
def _canonical_evidence(
    *,
    attempts: int,
    model: str,
    attempt_timeout_s: int,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> bool:
    if verifier_profile not in VERIFIER_PROFILES:
        return False
    return (
        attempts == DEFAULT_ATTEMPTS
        and model == DEFAULT_MODEL
        and attempt_timeout_s == DEFAULT_ATTEMPT_TIMEOUT_S
        and (
            verifier_profile != MANAGED_VERIFIER_PROFILE
            or READINESS_WAIT_TIMEOUT_MS == 10_000
        )
    )
```

Thread the profile through _new_run_dir, _manifest, _lm8i_command, _run_probe,
and main. Default parameters must preserve existing direct test calls.

- [ ] **Step 4: Preserve default schemas and add managed-only metadata**

For settle_v1, _manifest returns the exact existing mapping.

For managed_receipt_v2, replace schema with LM8M_SCRIPT_SCHEMA and add:

```python
{
    "verifier_profile": MANAGED_VERIFIER_PROFILE,
    "verifier_mechanism": VERIFIER_MECHANISM,
    "fixture_readiness_profile": FIXTURE_READINESS_PROFILE,
    "readiness_wait_timeout_ms": READINESS_WAIT_TIMEOUT_MS,
}
```

Do not add these fields to the LM8J default manifest or summary.

- [ ] **Step 5: Run LM8J tests**

Expected: PASS with both old default assertions and new LM8M identity tests.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lm8j_affine_support_repeatability_probe.py mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8m): add managed repeatability identity"
```

---

### Task 5: Independently Audit Managed Child Artifacts And Build LM8M Accounting

**Files:**
- Modify: scripts/lm8j_affine_support_repeatability_probe.py:263-603
- Modify: scripts/lm8j_affine_support_repeatability_probe.py:618-688
- Test: mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py:258-729
- Test: mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py:745-941

**Interfaces:**
- Produces: _audit_managed_child(run_dir: Path) -> dict[str, Any]
- Produces: _apply_managed_child_audit(row: dict[str, Any]) -> None
- Produces: LM8M managed attempt fields and summary counters.
- Consumes: Task 2 stage schemas and Task 4 profile identity.
- Does not import LM8I.

- [ ] **Step 1: Add realistic fake managed child artifact writer**

Add a test helper that writes all four files:

```python
def _write_managed_child_artifacts(
    run_dir: Path,
    *,
    decision="accepted",
    observed=7.5,
    receipt_hash="sha256:" + "a" * 64,
    session="session-1",
    mutation_epoch=13,
    prior_completed=41,
    solution_run=42,
):
    (run_dir / "live_set_value_summary.json").write_text(
        json.dumps(
            {
                "managed_mutation": {
                    "schema": "rook.lm8l_managed_mutation_summary:v1",
                    "receipt_schema": "rook.gh_solve_readiness_receipt:v1",
                    "receipt_status": "pending",
                    "receipt_id_sha256": receipt_hash,
                    "document_session_id": session,
                    "mutation_epoch": mutation_epoch,
                    "solution_run_epoch": None,
                    "completed_solution_run_epoch": prior_completed,
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_wait_summary.json").write_text(
        json.dumps(
            {
                "schema": "rook.lm8l_readiness_wait_summary:v1",
                "requested_timeout_ms": 10_000,
                "readiness_wait_count": 1,
                "wait_status": "ready",
                "receipt_status": "ready",
                "receipt_id_sha256": receipt_hash,
                "document_session_id": session,
                "mutation_epoch": mutation_epoch,
                "solution_run_epoch": solution_run,
                "completed_solution_run_epoch": solution_run,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "verify_scalar_output_summary.json").write_text(
        json.dumps(
            {
                "schema": "rook.lm8l_fenced_output_verification_summary:v1",
                "verifier_profile": "managed_receipt_v2",
                "readiness_wait_timeout_ms": 10_000,
                "readiness_wait_count": 1,
                "fenced_output_read_count": 1,
                "settle_read_count": 0,
                "readiness_fenced": True,
                "receipt_id_sha256": receipt_hash,
                "document_session_id": session,
                "mutation_epoch": mutation_epoch,
                "solution_run_epoch": solution_run,
                "completed_solution_run_epoch": solution_run,
                "expected_output_value": 7.5,
                "observed_output_value": observed,
                "tolerance": 1e-9,
                "matched": True,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "decision.json").write_text(
        json.dumps(
            {
                "schema": "rook.lm8i_affine_publication_shape_support_decision:v1",
                "decision": decision,
                "reason": "verify_scalar_output_succeeded",
                "phase": "verify_scalar_output",
                "canonical_evidence": True,
                "live_set_value_dispatched": True,
                "worker_publication_ran": True,
                "managed_verifier": {
                    "schema": "rook.lm8l_managed_verifier_decision:v1",
                    "verifier_profile": "managed_receipt_v2",
                    "verifier_mechanism": "managed_solve_readiness_receipt",
                    "fixture_readiness_profile": "lm8i_legacy_setup_v1",
                    "readiness_wait_timeout_ms": 10_000,
                    "readiness_wait_count": 1,
                    "fenced_output_read_count": 1,
                    "settle_read_count": 0,
                    "failed_invariants": [],
                },
            }
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 2: Write failing independent audit tests**

Assert a valid child returns:

```python
audit = PROBE._audit_managed_child(run_dir)
assert audit["performed"] is True
assert audit["valid"] is True
assert audit["failures"] == []
assert audit["readiness_wait_count"] == 1
assert audit["fenced_output_read_count"] == 1
assert audit["settle_read_count"] == 0
assert audit["post_mutation_solution_run_advanced"] is True
```

Parameterize mutations that independently change:

- each artifact missing
- invalid JSON/non-mapping
- each schema
- receipt hash format
- receipt hash equality
- session equality
- mutation epoch equality and positivity
- pending solution_run_epoch
- prior completed run type
- ready run not greater than prior
- wait completed run
- read run/completed run
- timeout
- wait status
- receipt status
- wait/read/settle counts
- readiness_fenced
- observed value/tolerance
- managed decision profile
- managed decision verifier_mechanism
- managed decision fixture_readiness_profile
- managed decision wait/read/settle counts against stage artifacts
- managed decision failed_invariants is empty for accepted children

Add accepted-child regressions where each decision field is missing or
contradictory. Nonempty failed_invariants or decision counts that disagree with
stage artifacts must make the audit invalid and the wrapper classification
wrapper_error.

Use exact stable failure strings such as mutation_artifact_missing,
mutation_epoch_not_positive, post_mutation_solution_run_not_advanced,
receipt_id_sha256_mismatch, and settle_read_count_not_zero.

- [ ] **Step 3: Run audit tests and confirm RED**

Run tests matching audit.

Expected: FAIL because audit helpers do not exist.

- [ ] **Step 4: Implement strict typed audit helpers**

Add helpers:

```python
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _is_int_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number_not_bool(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _managed_artifact(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"{path.stem}_missing"
    value = _read_json_mapping(path)
    if value is None:
        return None, f"{path.stem}_malformed"
    return value, None
```

Implement _audit_managed_child as a pure filesystem audit. It must read all
four files and build a result containing performed, valid, failures, counts,
statuses, reason, observed output, and equality booleans.

It must never read child aggregate validity booleans as authority.

- [ ] **Step 5: Apply contradiction classification after artifact copying**

After _copy_child_artifact_summaries and only for managed_receipt_v2, call:

```python
def _apply_managed_child_audit(row: dict[str, Any]) -> None:
    run_dir_value = row.get("lm8i_run_dir")
    if not run_dir_value:
        return
    audit = _audit_managed_child(Path(str(run_dir_value)))
    row.update(
        {
            "managed_verifier_audit_performed": audit["performed"],
            "managed_verifier_audit_valid": audit["valid"],
            "managed_verifier_audit_failures": audit["failures"],
            "readiness_wait_count": audit["readiness_wait_count"],
            "readiness_wait_status": audit["readiness_wait_status"],
            "readiness_failure_reason": audit["readiness_failure_reason"],
            "fenced_output_read_count": audit["fenced_output_read_count"],
            "settle_read_count": audit["settle_read_count"],
            "readiness_fenced": audit["readiness_fenced"],
            "receipt_id_hashes_match": audit["receipt_id_hashes_match"],
            "document_session_ids_match": audit["document_session_ids_match"],
            "mutation_epochs_match": audit["mutation_epochs_match"],
            "solution_run_epochs_match": audit["solution_run_epochs_match"],
            "post_mutation_solution_run_advanced": audit[
                "post_mutation_solution_run_advanced"
            ],
        }
    )
    if row.get("lm8i_decision") == "accepted" and not audit["valid"]:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = "accepted_child_managed_verifier_audit_failed"
```

A rejected child stays rejected even when its audit records failures. A child
that did not dispatch live_set_value gets audit not applicable and zero counts.

- [ ] **Step 6: Extend managed attempt rows and summary**

Only managed rows add the fields pinned in the spec. Do not change the default
LM8J row shape.

Add managed summary counters:

```python
managed_rows = [
    row for row in rows if row.get("verifier_profile") == MANAGED_VERIFIER_PROFILE
]
total_waits = sum(int(row.get("readiness_wait_count") or 0) for row in managed_rows)
total_fenced_reads = sum(
    int(row.get("fenced_output_read_count") or 0) for row in managed_rows
)
total_settle_reads = sum(
    int(row.get("settle_read_count") or 0) for row in managed_rows
)
managed_audit_pass_count = sum(
    1 for row in managed_rows if row.get("managed_verifier_audit_valid") is True
)
managed_audit_failure_count = sum(
    1
    for row in managed_rows
    if row.get("managed_verifier_audit_performed") is True
    and row.get("managed_verifier_audit_valid") is False
)
accepted_child_contradictions = sum(
    1
    for row in managed_rows
    if row.get("failure_reason") == "accepted_child_managed_verifier_audit_failed"
)

{
    "readiness_ready_count": sum(
        1 for row in managed_rows if row.get("readiness_wait_status") == "ready"
    ),
    "readiness_failure_reason_counts": _reason_counts(
        managed_rows, "readiness_failure_reason"
    ),
    "total_readiness_wait_count": total_waits,
    "total_fenced_output_read_count": total_fenced_reads,
    "total_settle_read_count": total_settle_reads,
    "managed_verifier_audit_pass_count": managed_audit_pass_count,
    "managed_verifier_audit_failure_count": managed_audit_failure_count,
    "managed_verifier_invariant_violation_count": sum(
        1
        for row in managed_rows
        if row.get("managed_verifier_audit_failures")
    ),
    "post_mutation_run_advance_failure_count": sum(
        1
        for row in managed_rows
        if "post_mutation_solution_run_not_advanced"
        in row.get("managed_verifier_audit_failures", [])
    ),
    "accepted_child_audit_contradiction_count": accepted_child_contradictions,
}
```

For managed canonical comparison success, add a reported
comparison_success boolean computed from the exact spec predicate. Do not
change canonical_evidence based on outcomes.

```python
canonical_evidence = _canonical_evidence(
    attempts=attempts,
    model=model,
    attempt_timeout_s=attempt_timeout_s,
    verifier_profile=verifier_profile,
)
comparison_success = (
    canonical_evidence is True
    and verifier_profile == MANAGED_VERIFIER_PROFILE
    and attempts == 20
    and terminal_counts["accepted"] == 20
    and managed_audit_pass_count == 20
    and total_waits == 20
    and total_fenced_reads == 20
    and total_settle_reads == 0
    and accepted_child_contradictions == 0
    and worker_action_values == [3.0] * 20
    and all(math.isclose(value, 7.5, abs_tol=1e-9) for value in observed_values)
    and leak_marker_match_count == 0
)
```

- [ ] **Step 7: Test wrapper contradiction and summary accounting**

Build rows for:

- 20 valid accepted children
- one accepted child with stale provenance
- one correctly rejected timeout child
- one worker decline with zero verifier calls

Assert the 20-valid summary has 20 waits, 20 fenced reads, zero settle reads,
20 audit passes, all worker values 3.0, all outputs 7.5, and
comparison_success true.

Add a perfect-outcome row set with canonical_evidence false, then another with
verifier_profile settle_v1. Both must report comparison_success false even
though every numerical outcome is otherwise perfect.

Assert contradictory acceptance increments wrapper_error and
accepted_child_audit_contradiction_count without incrementing rejected.

- [ ] **Step 8: Run LM8J/LM8M tests**

Run the full LM8J test file.

Expected: PASS, including unchanged default LM8J summary tests.

- [ ] **Step 9: Commit**

```powershell
git add scripts/lm8j_affine_support_repeatability_probe.py mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8m): audit managed child readiness receipts"
```

---

### Task 6: Lock Drift Guards And Run The Deterministic Implementation Gate

**Files:**
- Modify: mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py
- Modify: mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py
- Verify: scripts/lm8i_affine_publication_shape_support_probe.py
- Verify: scripts/lm8j_affine_support_repeatability_probe.py

**Interfaces:**
- Consumes all prior tasks.
- Produces final deterministic proof that the implementation changes only the approved verifier and accounting surfaces.

- [ ] **Step 1: Add static source and artifact-policy guards**

Add AST/source tests proving:

```python
def test_managed_profile_has_no_settle_fallback_or_extra_solve():
    source = inspect.getsource(PROBE)
    managed_source = inspect.getsource(
        PROBE._dispatch_set_value_managed_receipt_and_verify
    )
    assert '"gh_solve"' not in managed_source
    assert "asyncio.sleep" not in managed_source
    assert '"gh_solve_readiness"' not in managed_source


def test_lm8m_wrapper_remains_subprocess_only():
    source = _script_path().read_text(encoding="utf-8")
    assert "lm8i_affine_publication_shape_support_probe import" not in source
    assert "rook.server import" not in source
    assert "gh_set_value" not in inspect.getsource(PROBE._run_probe)
```

Keep policy strings out of overly broad raw-source bans. Test concrete imports,
calls, and subprocess command contents.

Add filesystem guards proving no files matching scripts/lm8l*.py or
scripts/lm8m*.py were added.

- [ ] **Step 2: Run focused and adjacent pytest gates**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_gh_solve_readiness_live_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run nearby scalar and worker regression gates**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py mcp_server\tests\test_lm_worker_two_pass_publication.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Compile the modified scripts**

Run:

```powershell
py -3.10 -m py_compile scripts\lm8i_affine_publication_shape_support_probe.py scripts\lm8j_affine_support_repeatability_probe.py
```

Expected: exit code 0 and no output.

- [ ] **Step 5: Run drift and scope checks**

Run:

```powershell
rg -n "gh_edit|planner_provider|retry_clean|support_forced" scripts\lm8i_affine_publication_shape_support_probe.py scripts\lm8j_affine_support_repeatability_probe.py
```

Interpret matches as policy/CLI rejection only. There must be no new dispatch
or import coupling.

Run:

```powershell
git diff --check origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected implementation-branch scope:

```text
docs/superpowers/specs/2026-07-10-lm8l-managed-receipt-verifier-migration-design.md
docs/superpowers/plans/2026-07-10-lm8l-managed-receipt-verifier-migration.md
scripts/lm8i_affine_publication_shape_support_probe.py
scripts/lm8j_affine_support_repeatability_probe.py
mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py
mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py
```

- [ ] **Step 6: Commit final guard tests if Step 1 changed tests**

```powershell
git add mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py
git commit -m "test(lm8m): lock managed verifier boundaries"
```

If Step 1 was already committed with Task 5 and the worktree is clean, do not
create an empty commit.

- [ ] **Step 7: Stop before live evidence**

Do not run LM8I or LM8J/LM8M against Rhino, Grasshopper, Ollama, or the worker
model in the implementation PR.

After review and merge, the canonical evidence command from synced main is:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8j_affine_support_repeatability_probe.py --verifier-profile managed_receipt_v2
```

The resulting run must use an lm8m-* directory. Inspect manifest.json,
attempts.jsonl, summary.json, and all accepted children's three managed stage
artifacts before writing a separate doc-only evidence PR.
