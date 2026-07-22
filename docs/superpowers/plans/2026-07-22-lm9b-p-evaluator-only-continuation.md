# LM9B-P Evaluator-Only Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one evaluator-only continuation that verifies the immutable visibility-intervention recipe, freezes a corrected evaluator instrument in a no-contact preflight, permits at most one GPT-5.4 evaluator dispatch from an exact operator-supplied preflight binding after fresh readiness, and seals an honest derivative result or retained forensic staging.

**Architecture:** Factor the existing accepted-recipe decision equations, frozen-input construction, and evaluator provider-call request construction so the normal checkpoint and derivative path share them without reconstructing a Planner session. Add a dedicated continuation artifact module for sealed-source verification, constructive rubric-only delta, identities, closed archives, and rename reconciliation, plus a narrow CLI/orchestrator that owns preflight, readiness verification, atomic reservation, dispatch, and evidence lifecycle. The continuation may reuse the existing generic LiteLLM transport dependency but has no Planner call, compiler behavior, handoff, checkpoint-2 entry, Rhino/Grasshopper execution, or mutation path.

**Tech Stack:** Python 3.11, stdlib (`argparse`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `re`, `shutil`, `stat`, `subprocess`, `time`), existing Rook validation kernel, existing LM9B-P readiness contract/probe, existing LiteLLM adapter, pytest.

## Global Constraints

- Work only in a clean isolated worktree and `codex/` branch created explicitly from the reviewed `origin/main` commit; never modify, clean, reset, or rebase the primary checkout.
- Do not contact a provider, run a readiness canary, or perform an evaluator call during implementation or deterministic verification; all tests use fakes.
- Preserve `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-visibility-intervention` as immutable read-only evidence.
- Require root manifest SHA-256 `AC7716B7D5A61E2E6359BC0E01E145D7D17E0871FF03D1D5329710541D274C90`, checkpoint aggregate `sha256:c57c88c61715588a2071d97d73e65f41447754868d18dc8517708734d92a081e`, historical commit `15df78ee665cf8ff433a4af20e364365b779143b`, recipe raw SHA-256 `sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af`, and recipe fingerprints `sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a`.
- The original result remains `probe_inconclusive`; checkpoint 2 remains `not_evaluated`; the derivative never repairs, replaces, recovers, or rewrites it.
- Use verified archived bytes for every historical input. Replace only the historical evaluator rubric with the corrected reviewed rubric; any other source-to-instrument difference refuses before dispatch.
- Pin `rook.lm9b_p.evaluator_continuation_preflight:v1`, `rook.lm9b_p.evaluator_continuation_derivative:v1`, and `rook.lm9b_p.evaluator_continuation_post_dispatch_unsealed:v1` as the top-level artifact schema identities.
- Pin evaluator model `gpt-5.4`, provider profile `litellm.completion.tool_calling.no_parallel:v1`, temperature `0.0`, one maximum evaluator attempt, and the existing evaluator token/timeout limits.
- Treat canonical provider-call bytes as the exact value at Rook's provider-adapter boundary, not as final HTTP wire bytes.
- `dispatch_started` burns the attempt identity. Before it exists, the same preflight may be reused only with fresh explicit approval and fresh readiness when destination and staging residue are both absent. After it exists, every later evaluator contact requires a new attempt ID, destination, preflight, approval, and readiness.
- Do not add dependencies, a shadow validator, a new semantic vocabulary, generalized replay, LM9A-S, governed resolution, compiler changes, or a duplicate provider adapter.

---

## File Map

- Modify `scripts/lm9b_p_planner_recipe_transfer_support.py`: own the public evaluator system prompt, canonical provider-call request builder/materializer, quiescent-timeout fact, and one-call runner.
- Modify `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`: factor record-based frozen-input construction and the pure evaluated-recipe classification helper; keep live-session proof validation in the normal classifier.
- Modify `scripts/lm9b_p_planner_recipe_transfer_probe.py`: route the normal evaluator through the shared provider-call builder and expose the existing Planner-role adapter identity/factory without changing transport behavior.
- Modify `scripts/lm9b_p_readiness_probe.py`: allow the existing readiness machinery to emit the one-role `planner_evaluator` manifest while preserving today's default all-role CLI behavior.
- Create `scripts/lm9b_p_evaluator_only_continuation_artifacts.py`: verify the sealed source; construct the rubric-only instrument; own preflight/attempt fingerprints, Windows destination checks, closed preflight/derivative/staging schemas, checksums, retention, and rename reconciliation.
- Create `scripts/lm9b_p_evaluator_only_continuation.py`: provide the only continuation CLI and runtime orchestration; it accepts no Planner/compiler providers or inputs and never builds a handoff.
- Modify `mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py`: pin the shared classification truth table and normal live-checkpoint delegation.
- Modify `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py`: pin unchanged normal-path provider request value and evaluator adapter profile identity.
- Modify `mcp_server/tests/test_lm9b_p_readiness_probe.py`: pin the single-role readiness CLI/manifest without real contact.
- Create `mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py`: keep the continuation suite compact around one vertical witness and four parameterized tables.

### Task 1: Extract the shared decision, input, and provider-request boundaries

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py`

**Interfaces:**
- Produces: `planner_input_record_from_bytes(...) -> PlannerInputRecord`
- Produces: `frozen_planner_inputs_from_records(...) -> FrozenPlannerInputs`
- Produces: `derive_evaluated_recipe_classification(evaluator, *, final_recipe_bytes: bytes) -> str`
- Produces: `build_planner_evaluator_provider_call_request(*, system_prompt: str, user_prompt: str) -> bytes`
- Produces: `materialize_planner_evaluator_provider_call_request(raw_bytes: bytes) -> dict[str, object]`
- Produces: `run_planner_evaluation(*, provider, provider_call_request_bytes: bytes) -> PlannerEvaluationResult`
- Produces: `PlannerEvaluationResult.quiescent: bool`
- Produces: `build_planner_evaluator_provider(*, model: str, temperature: float) -> object`
- Consumes: existing `derive_probe_explicit_blockers`, evaluator tool schema/parser, `FrozenPlannerInputs`, `PlannerSessionResult`, `MechanicalGateResult`, and `_PlannerProviderAdapter`.

- [ ] **Step 1: Replace the separate controller tests with one failing shared truth-table test while retaining the live-session integrity tests**

Add this parameterized test beside the existing authority-boundary controller tests. Use the real ready and blocked recipe bytes and do not create a `PlannerSessionResult` for the pure helper.

```python
@pytest.mark.parametrize(
    ("recipe_path", "termination", "recommendation", "expected"),
    [
        (BLOCKED_RECIPE, "valid_recommendation", "semantically_faithful", "probe_candidate_blocked"),
        (READY_RECIPE, "valid_recommendation", "semantically_faithful", "probe_candidate_ready"),
        (BLOCKED_RECIPE, "valid_recommendation", "semantically_unfaithful", "probe_planner_failure"),
        (READY_RECIPE, "valid_recommendation", "semantically_unfaithful", "probe_planner_failure"),
        (BLOCKED_RECIPE, "valid_recommendation", "evaluation_inconclusive", "probe_inconclusive"),
        (READY_RECIPE, None, None, "probe_inconclusive"),
        (READY_RECIPE, "malformed", None, "probe_inconclusive"),
        (READY_RECIPE, "provider_failure", None, "probe_inconclusive"),
        (READY_RECIPE, "timeout", None, "probe_inconclusive"),
    ],
)
def test_evaluated_recipe_classification_truth_table(
    recipe_path: Path,
    termination: str | None,
    recommendation: str | None,
    expected: str,
) -> None:
    evaluator = (
        None
        if termination is None
        else SimpleNamespace(
            termination=termination,
            recommendation=recommendation,
        )
    )
    assert ARTIFACTS.derive_evaluated_recipe_classification(
        evaluator,
        final_recipe_bytes=recipe_path.read_bytes(),
    ) == expected
```

Keep the existing missing-gate, mismatched-byte, divergent-retained-gate, mechanical-rejection, and accepted-session tests. Amend the ready and blocked live-session assertions to prove `derive_checkpoint_classification()` still validates the live proof carrier and delegates to the same equations.

- [ ] **Step 2: Add failing tests for byte-supplied frozen inputs and the sole provider-call request builder**

Add these tests to `test_lm9b_p_planner_recipe_transfer_probe.py` using existing `FIXTURES`, `ARTIFACTS`, `SUPPORT`, and the evaluator request helper:

```python
def test_record_supplied_inputs_equal_fixture_loaded_inputs() -> None:
    loaded = ARTIFACTS.load_planner_inputs(FIXTURES)
    rebuilt_records = tuple(
        ARTIFACTS.planner_input_record_from_bytes(
            role=record.role,
            relative_path=record.relative_path,
            raw_bytes=record.raw_bytes,
        )
        for record in loaded.records
    )
    rebuilt = ARTIFACTS.frozen_planner_inputs_from_records(
        rebuilt_records,
        source_dir=FIXTURES,
    )
    assert rebuilt == loaded


def test_provider_call_builder_is_canonical_pure_and_materializes_fresh_values() -> None:
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=READY_RECIPE.read_bytes(),
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    rendered = ARTIFACTS.render_planner_evaluator_request(inputs, gate_result=gate)
    kwargs = {
        "system_prompt": SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT,
        "user_prompt": rendered.raw_bytes.decode("utf-8"),
    }
    first = SUPPORT.build_planner_evaluator_provider_call_request(**kwargs)
    second = SUPPORT.build_planner_evaluator_provider_call_request(**kwargs)
    assert first == second
    assert first == json.dumps(
        json.loads(first), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    one = SUPPORT.materialize_planner_evaluator_provider_call_request(first)
    two = SUPPORT.materialize_planner_evaluator_provider_call_request(first)
    assert one == two
    assert one is not two
    assert one["tools"] is not two["tools"]
```

Add a fake provider that mutates `request["tools"]` and assert the original canonical bytes remain unchanged after `run_planner_evaluation()` returns.

Also parse `inspect.getsource(build_planner_evaluator_provider_call_request)` with `ast.parse()` and reject calls or attribute reads rooted at `time`, `datetime`, `random`, `uuid`, `os`, provider adapters, or networking modules. The builder's only calls may be the tool-schema function and deterministic JSON serialization.

- [ ] **Step 3: Run the focused tests and verify the new interfaces fail before implementation**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py -q
```

Expected: FAIL because `derive_evaluated_recipe_classification`, the record constructors, the provider-call builder/materializer, and the revised runner signature do not exist.

- [ ] **Step 4: Implement record-based input construction with one validation path**

In `lm9b_p_planner_recipe_transfer_artifacts.py`, change `_planner_input_record` into a filesystem wrapper around this public byte constructor:

```python
def planner_input_record_from_bytes(
    *,
    role: str,
    relative_path: str,
    raw_bytes: bytes,
) -> PlannerInputRecord:
    expected = {role: (filename, kind) for role, filename, kind in _PLANNER_INPUT_FILES}
    if role not in expected:
        raise ValueError(f"unexpected Planner input role: {role}")
    filename, kind = expected[role]
    if relative_path != filename or type(raw_bytes) is not bytes:
        raise ValueError(f"Planner input identity mismatch: {role}")
    raw = raw_bytes
    if kind == "text":
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError(f"{filename} must not contain a UTF-8 BOM")
        try:
            decoded = raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError(f"{filename} is not UTF-8") from exc
        if "\r" in decoded or decoded.count("\n") > 1 or not decoded.endswith("\n"):
            raise ValueError(f"{filename} must contain one LF-terminated line")
        value: object = decoded[:-1]
        if not value:
            raise ValueError(f"{filename} must not be empty")
    else:
        value = parse_strict_json(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{filename} must be an object")
    return PlannerInputRecord(
        role=role,
        relative_path=filename,
        raw_sha256=sha256_prefixed(raw),
        canonical_fingerprint=fingerprint(value),
        raw_bytes=raw,
        value=_freeze_json(value),
    )
```

Implement `frozen_planner_inputs_from_records(records, *, source_dir)` by moving the complete validation body now in `load_planner_inputs()` into it. Require the exact `_PLANNER_INPUT_FILES` order and role/path set, build `FrozenPlannerAuthority` exclusively from the record values, run every existing authority/contract/rubric/exclusion/schema/freshness/fingerprint check, and return the same `FrozenPlannerInputs`. Make both `load_planner_inputs()` and `load_planner_authority_context()` read bytes and delegate; neither path may retain a second semantic validator.

- [ ] **Step 5: Implement the pure classifier and delegate only after live-session proof validation**

Place this helper beside `derive_probe_explicit_blockers()`:

```python
def derive_evaluated_recipe_classification(
    evaluator: object | None,
    *,
    final_recipe_bytes: bytes,
) -> str:
    if type(final_recipe_bytes) is not bytes:
        raise TypeError("verified final recipe bytes are required")
    if evaluator is None or getattr(evaluator, "termination", None) != "valid_recommendation":
        return "probe_inconclusive"
    recommendation = getattr(evaluator, "recommendation", None)
    if recommendation == "semantically_unfaithful":
        return "probe_planner_failure"
    if recommendation == "evaluation_inconclusive":
        return "probe_inconclusive"
    if recommendation != "semantically_faithful":
        raise ValueError("invalid evaluator recommendation for checkpoint")
    blockers = derive_probe_explicit_blockers(final_recipe_bytes)
    return "probe_candidate_blocked" if blockers else "probe_candidate_ready"
```

Leave every current `PlannerSessionResult` and `checkpoint_gate` check in `derive_checkpoint_classification()`. Replace only its final evaluator/recommendation/blocker equations with:

```python
return derive_evaluated_recipe_classification(
    evaluator,
    final_recipe_bytes=gate_final_bytes,
)
```

- [ ] **Step 6: Implement the sole canonical provider-call request builder and quiescent result fact**

Move `_PLANNER_EVALUATOR_SYSTEM_PROMPT` from the probe into the support module as `PLANNER_EVALUATOR_SYSTEM_PROMPT`. Add `quiescent: bool = True` as the final field of `PlannerEvaluationResult` so existing positional construction remains compatible. Add `quiescent: bool` to `_BoundedProviderCall`; set it false only when the worker remains alive after `join(timeout_s)`.

Implement the builder/materializer exactly once:

```python
def build_planner_evaluator_provider_call_request(
    *,
    system_prompt: str,
    user_prompt: str,
) -> bytes:
    request = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [planner_evaluator_tool_definition()],
        "tool_choice": {
            "type": "function",
            "function": {"name": "submit_planner_evaluation"},
        },
        "max_completion_tokens": PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
    }
    return json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def materialize_planner_evaluator_provider_call_request(
    raw_bytes: bytes,
) -> dict[str, object]:
    value = parse_archive_json(raw_bytes)
    if type(value) is not dict:
        raise ValueError("provider-call request must be an object")
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical != raw_bytes:
        raise ValueError("provider-call request bytes are not canonical")
    return value
```

Change `run_planner_evaluation()` to accept canonical request bytes, materialize one fresh dict, and call `_bounded_provider_call()` exactly once. Return `PlannerEvaluationResult(..., quiescent=False)` for a still-live worker; return quiescent timeout for a terminal `TimeoutError`/timeout-shaped `ProviderCallFailure`; preserve the current parser behavior for returned turns.

- [ ] **Step 7: Route the normal checkpoint through the builder and expose the existing evaluator adapter identity**

In `run_planner_checkpoint()`, build the bytes once from the public system prompt and rendered request, pass those bytes to `run_planner_evaluation()`, and retain those exact bytes in `ProviderAttemptEvidence`. Remove its local JSON provider-request serializer.

On the existing `_PlannerProviderAdapter`, expose:

```python
self.profile_identity = _PLANNER_PROVIDER_PROFILE_ID
self.identity = {
    "adapter_path": "litellm.completion",
    "model": model,
    "profile_identity": self.profile_identity,
    "temperature": temperature,
}
```

Add this public factory without copying or relocating the adapter:

```python
def build_planner_evaluator_provider(*, model: str, temperature: float) -> object:
    return _PlannerProviderAdapter(model=model, temperature=temperature)
```

Make `_build_provider()` delegate its `planner_evaluator` branch to that factory. Do not change the underlying LM9B-C-located generic transport or provider profile.

- [ ] **Step 8: Run focused tests and commit the shared extraction**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py -q
```

Expected: PASS, including the faithful-ready row and every existing live-gate integrity test.

Commit:

```powershell
git add scripts/lm9b_p_planner_recipe_transfer_support.py scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py
git commit -m "refactor: share evaluator continuation boundaries"
```

### Task 2: Verify the historical source and emit a content-addressed no-contact preflight

**Files:**
- Create: `scripts/lm9b_p_evaluator_only_continuation_artifacts.py`
- Create: `scripts/lm9b_p_evaluator_only_continuation.py`
- Create: `mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py`

**Interfaces:**
- Consumes: Task 1 record constructors, renderer, gate, classifier, builder, fingerprints, and existing `verify_sealed_planner_checkpoint_archive()`.
- Produces: `HistoricalSourcePins`, `VerifiedHistoricalSource`, `ContinuationInstrument`, `VerifiedContinuationPreflight`, `PreflightConfig`.
- Produces: `_verify_historical_source(pins)`, `verify_historical_source()`, `assemble_continuation_instrument(...)`, `emit_no_contact_preflight(config)`, `verify_preflight_archive(...)`.
- Produces: exact `PREFLIGHT_SCHEMA_ID`, `DERIVATIVE_SCHEMA_ID`, and `UNSEALED_SCHEMA_ID` constants.

- [ ] **Step 1: Write the synthetic sealed-source fixture helper and failing no-contact preflight test**

In the new test file, load scripts with the repository's existing `_load_script()` pattern. Build a temporary historical source fixture by sealing a one-turn accepted checkpoint with the blocked recipe, rewriting only the archived rubric to a historical semantic/ready vocabulary, recalculating its input manifest and checkpoint checksums, and writing a complete root `SHA256-MANIFEST.txt`. Return a `HistoricalSourcePins` whose digests match that fixture. This helper is test-only; production still calls the exact immutable pins.

Then add:

```python
def test_no_contact_preflight_binds_exact_source_delta_requests_and_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_pins = _sealed_historical_source(tmp_path / "source")
    monkeypatch.setattr(CONT_ARTIFACTS, "PRODUCTION_SOURCE_PINS", source_pins)
    monkeypatch.setattr(CONTINUATION, "_git_checkout_state", lambda: ("a" * 40, True))
    contacted = False

    def forbidden_provider_factory():
        nonlocal contacted
        contacted = True
        raise AssertionError("preflight constructed a provider")

    monkeypatch.setattr(CONTINUATION, "_build_evaluator_provider", forbidden_provider_factory)
    derivative_root = tmp_path / "derivatives"
    derivative_root.mkdir()
    preflight = CONTINUATION.emit_no_contact_preflight(
        CONTINUATION.PreflightConfig(
            output_dir=tmp_path / "preflight",
            reviewed_commit_sha="a" * 40,
            attempt_id="visibility-evaluator-01",
            derivative_root=derivative_root,
            destination=derivative_root / "visibility-evaluator-01",
        )
    )
    assert contacted is False
    assert preflight.record["schema_id"] == CONT_ARTIFACTS.PREFLIGHT_SCHEMA_ID
    assert preflight.record["reviewed_commit_sha"] == "a" * 40
    assert preflight.record["source"]["recipe_raw_sha256"] == source_pins.recipe_raw_sha256
    delta = json.loads((preflight.archive_dir / "allowed-delta-manifest.json").read_bytes())
    rows = delta["rows"]
    assert sum(row["disposition"] == "replaced_evaluator_rubric" for row in rows) == 1
    assert all(
        row["disposition"] == "replaced_evaluator_rubric"
        or row["source_raw_sha256"] == row["instrument_raw_sha256"]
        for row in rows
    )
    assert CONT_ARTIFACTS.verify_preflight_archive(
        preflight.archive_dir,
        expected_preflight_fingerprint=preflight.preflight_fingerprint,
    ) == preflight
    assert preflight.attempt_id.encode("utf-8") not in preflight.rendered_request_bytes
    assert str(preflight.destination).encode("utf-8") not in preflight.rendered_request_bytes
    assert preflight.attempt_id.encode("utf-8") not in preflight.provider_call_request_bytes
    assert str(preflight.destination).encode("utf-8") not in preflight.provider_call_request_bytes
```

Emit a second preflight at the same reviewed commit/source/instrument with a different valid attempt ID and destination. Assert equal `instrument_fingerprint` and unequal `attempt_fingerprint`. Rebuild at a different synthetic reviewed commit and assert both its instrument and attempt fingerprints change.

- [ ] **Step 2: Write the failing pre-contact mutation table**

Use one `@pytest.mark.parametrize("mutation", [...])` table. Each row first emits a valid preflight, then mutates exactly one of: root manifest/file byte, checkpoint seal, non-rubric input, corrected rubric, allowed-delta row, evaluator system prompt, renderer ID, parser report schema, recommendation meanings, tool schema, token limit, provider-call builder, readiness route/model, provider profile, reviewed commit/dirty state, rendered request bytes, canonical provider bytes, destination containment/existence, or reparse-point observation. Call the final pre-dispatch verifier with a fake provider counter and assert the counter remains zero.

Use named mutators rather than separate fixtures:

```python
@pytest.mark.parametrize(
    "mutation",
    [
        "source_manifest", "source_file", "checkpoint_seal", "non_rubric_input",
        "corrected_rubric", "allowed_delta", "system_prompt", "renderer",
        "report_schema", "recommendation_meanings", "tool_schema", "limit",
        "provider_builder", "route", "model", "profile", "commit", "dirty",
        "rendered_request", "provider_request", "destination_exists",
        "destination_escape", "reparse_ancestor",
    ],
)
def test_every_pre_contact_drift_refuses_before_evaluator_dispatch(
    prepared_preflight,
    mutation: str,
) -> None:
    calls = prepared_preflight.apply(mutation)
    with pytest.raises((ValueError, RuntimeError, FileExistsError)):
        prepared_preflight.execute()
    assert calls.evaluator == 0
    assert not prepared_preflight.dispatch_marker.exists()
```

The helper's `apply()` must contain a closed dictionary from each name to one concrete byte/object/path mutation; unknown names raise `AssertionError`.

- [ ] **Step 3: Run the new tests and verify they fail before production modules exist**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -q
```

Expected: FAIL while importing the two new continuation modules.

- [ ] **Step 4: Implement exact historical-source verification and the frozen source snapshot**

In the new artifacts module, pin:

```python
PREFLIGHT_SCHEMA_ID = "rook.lm9b_p.evaluator_continuation_preflight:v1"
DERIVATIVE_SCHEMA_ID = "rook.lm9b_p.evaluator_continuation_derivative:v1"
UNSEALED_SCHEMA_ID = "rook.lm9b_p.evaluator_continuation_post_dispatch_unsealed:v1"
PROVIDER_PROFILE_ID = "litellm.completion.tool_calling.no_parallel:v1"
EVALUATOR_MODEL = "gpt-5.4"
EVALUATOR_TEMPERATURE = 0.0
ATTEMPT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
```

Define `HistoricalSourcePins` with source root, root-manifest digest, checkpoint aggregate, historical commit/classification/checkpoint-2, recipe digest, and ratified/historical recipe fingerprints. Instantiate `PRODUCTION_SOURCE_PINS` with the exact Global Constraints values.

`_verify_historical_source(pins)` must, in this order:

1. Read the root manifest once, hash its exact bytes, and require the pin.
2. Parse only uppercase/lowercase 64-hex digest, two spaces, and a safe forward-slash relative path; reject duplicate, absolute, empty, backslash, `.`/`..`, and traversal paths.
3. Compare the manifest path set to every file under the source root except `SHA256-MANIFEST.txt`, then stream-hash every listed file. Non-continuation records such as historical compiler-control files are hash-only members of the sealed root: never parse them, expose them as controls, copy them into the derivative, or pass them to compiler code.
4. Call the existing sealed-checkpoint verifier with the pinned aggregate.
5. Strict-parse and close-check historical identity, classification, final recipe identity, input manifest, and joined aggregate; require the historical commit, `probe_inconclusive`, `not_evaluated`, no handoff, no compiler archive, and the exact recipe identities.
6. Build `PlannerInputRecord` instances only from `checkpoint-1/inputs/*` bytes named in the verified historical input manifest.
7. Return a frozen dataclass containing all continuation-relevant raw bytes and the complete verified root path/digest rows. It must expose no mutator and perform no writes.

The public `verify_historical_source()` takes no path or pin argument and delegates to `PRODUCTION_SOURCE_PINS`. The private pin-accepting function exists only for deterministic fixtures.

- [ ] **Step 5: Implement the constructive rubric-only instrument and stable identities**

`assemble_continuation_instrument()` accepts only the verified source snapshot, exact corrected-rubric bytes read by the caller, and reviewed commit. Build new input records by preserving every archived `raw_bytes` except `evaluation_rubric`, whose raw bytes are replaced. Delegate all semantic input checks to `frozen_planner_inputs_from_records()`.

Emit one closed allowed-delta row per archived manifest record with:

```python
{
    "role": source.role,
    "relative_path": source.relative_path,
    "source_raw_sha256": source.raw_sha256,
    "source_canonical_fingerprint": source.canonical_fingerprint,
    "instrument_raw_sha256": instrument.raw_sha256,
    "instrument_canonical_fingerprint": instrument.canonical_fingerprint,
    "disposition": (
        "replaced_evaluator_rubric"
        if source.role == "evaluation_rubric"
        else "byte_identical"
    ),
}
```

Require exactly one replacement and exact raw-byte equality for all other rows. Recompute the mechanical gate from the sealed recipe under the assembled frozen inputs, require mechanical acceptance and all pinned recipe identities, render the evaluator request, and call the Task 1 provider-request builder.

Build `protocol_identity` with renderer ID; report-schema and recommendation-meaning fingerprints; parser, blocker, classifier, builder, and archive contract IDs; system-prompt hash; model/profile/route/temperature/limits; and reviewed commit. Compute:

```python
instrument_fingerprint = fingerprint({
    "source": source.identity_value,
    "allowed_delta": allowed_delta,
    "protocol": protocol_identity,
    "reviewed_commit_sha": reviewed_commit_sha,
    "rendered_evaluator_request_raw_sha256": rendered.raw_sha256,
    "provider_call_request_raw_sha256": sha256_prefixed(provider_request_bytes),
})
```

Do not include attempt ID or destination in this value.

- [ ] **Step 6: Implement canonical Windows destination checks and the closed preflight archive**

Validate attempt IDs against the exact grammar and 1..64 length. Require derivative root and destination to be absolute canonical Windows paths; require destination strictly below the root with `os.path.commonpath`; require same drive/volume; reject unresolved traversal; walk every existing ancestor with `os.lstat()` and reject `stat.FILE_ATTRIBUTE_REPARSE_POINT`; require destination and deterministic staging path absent.

Compute:

```python
attempt_fingerprint = fingerprint({
    "instrument_fingerprint": instrument.instrument_fingerprint,
    "attempt_id": attempt_id,
    "canonical_destination": str(canonical_destination),
})
```

Derive the reservation path as a direct child of the approved root so no parent-creation race is needed:

```python
staging_name = (
    f".continuation-staging-{attempt_id}-"
    f"{attempt_fingerprint.removeprefix('sha256:')}"
)
staging_path = canonical_derivative_root / staging_name
```

Reject a final destination whose name begins with `.continuation-staging-`. The staging name is not an official archive identity or namespace; a post-dispatch failure is distinguished only by its required unsealed marker and schema.

Build the preflight record without its self-field, including the exact sidecar path/hash/length rows, then set:

```python
record_without_fingerprint = {
    "schema_id": PREFLIGHT_SCHEMA_ID,
    "reviewed_commit_sha": reviewed_commit_sha,
    "clean_checkout": True,
    "source": source_identity,
    "instrument": instrument_identity,
    "attempt": attempt_identity,
    "files": sidecar_rows,
}
preflight_fingerprint = fingerprint(record_without_fingerprint)
record = {
    **record_without_fingerprint,
    "preflight_fingerprint": preflight_fingerprint,
}
```

Write a preflight directory with exactly:

```text
record.json
source-binding.json
allowed-delta-manifest.json
mechanical-gate.json
rendered-evaluator-request.json
provider-call-request.json
checksums.json
```

`record.json` has exact top-level keys `schema_id`, `preflight_fingerprint`, `reviewed_commit_sha`, `clean_checkout`, `source`, `instrument`, `attempt`, and `files`. `checksums.json` contains sorted rows of `path`, `role`, `raw_sha256`, and `byte_length`, plus a canonical aggregate identity. Create the output directory with `exist_ok=False`, write exact bytes, reread each, verify closure and hashes, and never construct a provider.

`verify_preflight_archive()` must reject missing/extra paths, duplicate checksum paths, wrong schema, self-inconsistent fingerprints, malformed identities, destination drift, or a directory-shaped derivative/staging artifact.

- [ ] **Step 7: Implement the no-contact preflight orchestrator and CLI subcommand**

Define:

```python
@dataclass(frozen=True)
class PreflightConfig:
    output_dir: Path
    reviewed_commit_sha: str
    attempt_id: str
    derivative_root: Path
    destination: Path


def emit_no_contact_preflight(config: PreflightConfig) -> VerifiedContinuationPreflight:
    head, clean = _git_checkout_state()
    if not clean or head != config.reviewed_commit_sha:
        raise RuntimeError("preflight requires the clean reviewed commit")
    source = CONT_ARTIFACTS.verify_historical_source()
    corrected_rubric = CORRECTED_RUBRIC_PATH.read_bytes()
    instrument = CONT_ARTIFACTS.assemble_continuation_instrument(
        source,
        corrected_rubric_bytes=corrected_rubric,
        reviewed_commit_sha=head,
    )
    return CONT_ARTIFACTS.write_preflight_archive(config, instrument)
```

Add `preflight` CLI arguments exactly matching `PreflightConfig`. Do not add source-root, source-pin, Planner, compiler, handoff, checkpoint-2, or provider arguments. Printing the resulting preflight fingerprint is allowed; contacting readiness or a provider is not.

- [ ] **Step 8: Run the source/preflight tests and commit**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -k "preflight or source or pre_contact" -q
```

Expected: PASS; fake provider construction/call count remains zero for preflight and all mutations.

Commit:

```powershell
git add scripts/lm9b_p_evaluator_only_continuation_artifacts.py scripts/lm9b_p_evaluator_only_continuation.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py
git commit -m "feat: add evaluator continuation preflight"
```

### Task 3: Reuse one-route readiness and implement the one-dispatch evidence state machine

**Files:**
- Modify: `scripts/lm9b_p_readiness_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_readiness_probe.py`
- Modify: `scripts/lm9b_p_evaluator_only_continuation.py`
- Modify: `scripts/lm9b_p_evaluator_only_continuation_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py`

**Interfaces:**
- Consumes: existing readiness `derive_routes`, `run_readiness`, and `verify_launch_readiness`; Task 2 verified preflight/instrument snapshots; Task 1 evaluator factory/runner.
- Produces: `ExecutionConfig`, `SealedDerivative`, `PostDispatchUnsealed`, `execute_continuation(config)`.
- Produces: `reserve_staging`, `write_dispatch_started`, `seal_derivative_archive`, `retain_post_dispatch_unsealed`, `verify_sealed_derivative_archive`.

- [ ] **Step 1: Add a failing one-role readiness test without provider contact**

In `test_lm9b_p_readiness_probe.py`, call `run_readiness()` with a fake provider and `models={"planner_evaluator": "gpt-5.4"}`. Assert one route, member roles exactly `("planner_evaluator",)`, the existing schema/protocol/freshness values, and one fake call only when `authenticate=True`. Add a CLI parse test proving `--role planner_evaluator` selects that same model mapping while omission retains all four canonical roles.

- [ ] **Step 2: Add the failing vertical witness through the actual continuation entry point**

Use the verified source/preflight fixture and a real passing fake readiness record built by existing readiness helpers. Patch only `_build_evaluator_provider` to return a fake that captures and mutates its fresh request after constructing a valid `semantically_faithful` tool response. Patch actual compiler-specific behavior to raise:

```python
forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
    AssertionError("compiler-specific behavior was reached")
)
monkeypatch.setattr(PLANNER_PROBE, "run_joined_probe", forbidden)
monkeypatch.setattr(PLANNER_PROBE, "_freeze_compiler_controls", forbidden)
monkeypatch.setattr(PLANNER_ARTIFACTS, "build_lm9bc_handoff", forbidden)
```

Invoke `CONTINUATION.main(["execute", ...])`, not a helper-only path. Assert:

```python
assert fake.calls == 1
assert fake.received_canonical_bytes == preflight.provider_call_request_bytes
sealed = CONT_ARTIFACTS.verify_sealed_derivative_archive(destination)
assert sealed.classification == "probe_candidate_blocked"
assert sealed.identity["schema_id"] == CONT_ARTIFACTS.DERIVATIVE_SCHEMA_ID
assert sealed.identity["attempt_fingerprint"] == preflight.attempt_fingerprint
assert json.loads((destination / "boundary.json").read_bytes()) == {
    "schema": "rook.lm9b_p.evaluator_continuation_boundary:v1",
    "derivative_observation": True,
    "replaces_historical_result": False,
    "planner_entry": "absent",
    "compiler_entry": "absent",
    "checkpoint_2": "not_evaluated",
    "execution_permitted": False,
}
assert not any("compiler" in path.as_posix().casefold() for path in destination.rglob("*"))
assert _tree_digest(source_pins.source_root) == original_source_digest
```

Also assert the retained preflight/provider request bytes did not change when the fake mutated its request object.

- [ ] **Step 3: Add the failing post-dispatch fault-injection table**

Use one table with exact expected disposition:

```python
@pytest.mark.parametrize(
    ("fault", "expected_state", "expected_classification"),
    [
        ("provider_mutates", "sealed", "probe_candidate_blocked"),
        ("provider_exception", "sealed", "probe_inconclusive"),
        ("quiescent_timeout", "sealed", "probe_inconclusive"),
        ("malformed_report", "sealed", "probe_inconclusive"),
        ("evaluation_inconclusive", "sealed", "probe_inconclusive"),
        ("semantically_unfaithful", "sealed", "probe_planner_failure"),
        ("ambiguous_timeout", "post_dispatch_unsealed", None),
        ("interrupt_after_dispatch_marker", "post_dispatch_unsealed", None),
        ("evidence_corruption", "post_dispatch_unsealed", None),
        ("snapshot_identity_mismatch", "post_dispatch_unsealed", None),
        ("classification_failure", "post_dispatch_unsealed", None),
        ("checksum_failure", "post_dispatch_unsealed", None),
    ],
)
def test_post_dispatch_outcome_and_fault_matrix(
    executable_preflight,
    fault: str,
    expected_state: str,
    expected_classification: str | None,
) -> None:
    result = executable_preflight.execute_with(fault)
    assert executable_preflight.calls.evaluator <= 1
    if expected_state == "sealed":
        sealed = CONT_ARTIFACTS.verify_sealed_derivative_archive(result.archive_dir)
        assert sealed.classification == expected_classification
    else:
        marker = json.loads((result.staging_dir / "post_dispatch_unsealed.json").read_bytes())
        assert marker["schema_id"] == CONT_ARTIFACTS.UNSEALED_SCHEMA_ID
        assert marker["attempt_fingerprint"] == executable_preflight.attempt_fingerprint
        with pytest.raises(ValueError):
            CONT_ARTIFACTS.verify_sealed_derivative_archive(result.staging_dir)
```

Implement fault selection only in test fakes/monkeypatches; do not add a production `fault` argument.

- [ ] **Step 4: Run the focused tests and verify they fail before execution exists**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -k "role or vertical or post_dispatch" -q
```

Expected: FAIL because one-role CLI selection and the execution state machine are not implemented.

- [ ] **Step 5: Add one-role selection to the existing readiness probe**

Add repeatable `--role` choices from `CONTRACT.CANONICAL_ROLE_MODELS`. If omitted, retain the existing all-role dictionary. If supplied, build:

```python
selected_models = {
    role: CONTRACT.CANONICAL_ROLE_MODELS[role]
    for role in dict.fromkeys(args.role)
}
```

Pass `selected_models` to the existing `run_readiness()`; do not change the readiness schema, route derivation, canary protocol, or 600-second freshness rule. The operational evaluator-only command is:

```powershell
$readinessRoot = Join-Path $PWD 'lm9b-p-evaluator-readiness'
$reviewedCommit = git rev-parse HEAD
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe scripts/lm9b_p_readiness_probe.py --run-root $readinessRoot --reviewed-commit-sha $reviewedCommit --role planner_evaluator --authenticate
```

Document this command only in CLI help/docstrings; do not execute it during implementation.

- [ ] **Step 6: Implement final pre-dispatch verification and atomic reservation**

Define `ExecutionConfig` with only `preflight_dir`, `expected_preflight_fingerprint`, `readiness_record`, `credential_preflight`, and `transmit`. The function signature is exactly:

```python
def execute_continuation(
    config: ExecutionConfig,
) -> SealedDerivative | PostDispatchUnsealed:
```

Before constructing a provider or creating staging:

1. Require `transmit is True` and exact supplied preflight fingerprint.
2. Verify preflight closure, clean `HEAD`, source archive, corrected rubric, delta, independent gate, renderer, report schema/meanings, system prompt, limits, canonical provider request, model/profile/route, and absent destination/staging.
3. Derive the readiness manifest from exactly `{"planner_evaluator": "gpt-5.4"}` and the existing credential helper; parse/reread the readiness record and credential preflight; call existing `verify_launch_readiness()` with the existing clock and environment-presence rules.
4. Construct the existing evaluator adapter and independently require its model, temperature, and `profile_identity` to equal the instrument; readiness itself does not attest profile.
5. Freeze one in-memory `ExecutionSnapshot` containing all source/instrument/preflight/readiness/request bytes.
6. Atomically create deterministic staging with `mkdir(exist_ok=False)` on the same volume. Persist and reread the snapshot and exact preflight/readiness/request bytes. From this line onward, do not read the historical source or corrected fixture path again.

If any step before `dispatch_started` fails, never invoke the adapter. Remove only the exact reserved staging path after revalidating its containment and absence of a dispatch marker; if removal fails, residue blocks preflight reuse.

- [ ] **Step 7: Implement dispatch, complete evaluator failures, and conservative unsealed retention**

Materialize and validate a fresh provider request from staged canonical bytes. Then write, flush/fsync, and reread these exact fields from the frozen snapshot:

```python
dispatch_started = {
    "schema": "rook.lm9b_p.evaluator_continuation_dispatch_started:v1",
    "attempt_id": snapshot.attempt_id,
    "attempt_fingerprint": snapshot.attempt_fingerprint,
    "provider_call_request_raw_sha256": sha256_prefixed(
        snapshot.provider_call_request_bytes
    ),
}
```

Only after that durable marker call `run_planner_evaluation()` once through a recording wrapper. Preserve canonical pre-call bytes separately from the fresh mutable object.

For a valid recommendation, call the shared pure classifier with staged verified recipe bytes. For provider exception, terminal/quiescent timeout, malformed report, or `evaluation_inconclusive`, write complete evidence and derive `probe_inconclusive`. For a still-live timeout or any failure in evidence persistence/readback, staged identity verification, classification, checksum closure, or sealing, write best-effort `post_dispatch_unsealed.json` with the exact unsealed schema ID, failure locus, attempt/preflight/instrument identities, dispatch fact, and partial per-file forensic hashes. Never assign a derivative identity or classification to unsealed staging.

Catch `BaseException` only around the post-dispatch evidence lifecycle so process interruption retains staging; re-raise `KeyboardInterrupt`/`SystemExit` after best-effort marking if the CLI must preserve conventional termination.

- [ ] **Step 8: Implement the exact derivative archive and closed verifier**

Write only this closed membership (the `when available` leaves are declared by `evaluator/attempt/capture.json` and still checksummed):

```text
identity.json
source/binding.json
source/SHA256-MANIFEST.txt
source/checkpoint-checksums.json
source/original-identity.json
source/original-classification.json
source/final-recipe.json
source/final-recipe-identity.json
source/inputs/attempt_context.json
source/inputs/radial_brief.txt
source/inputs/task_envelope.json
source/inputs/environment_snapshot.json
source/inputs/planning_policy.json
source/inputs/payload_schema_registry.json
source/inputs/capability_registry.json
source/inputs/semantic_authority_code_vocabulary.json
source/inputs/semantic_capability_code_vocabulary.json
source/inputs/worker_slot_code_vocabulary.json
source/inputs/semantic_materiality_code_vocabulary.json
source/inputs/semantic_value_schema_registry.json
source/inputs/planner_recipe_probe_schema.json
source/inputs/recipe_normalization_profile.json
source/inputs/planner_authoring_contract.json
source/inputs/planner_exclusion_policy.json
source/inputs/planner_evaluation_rubric.json
instrument/allowed-delta-manifest.json
instrument/corrected-evaluator-rubric.json
instrument/protocol-identity.json
instrument/mechanical-gate.json
preflight/record.json
preflight/rendered-evaluator-request.json
preflight/provider-call-request.json
launch/invocation-binding.json
readiness/readiness-record.json
readiness/credential-preflight.json
dispatch/dispatch-started.json
evaluator/attempt/capture.json
evaluator/attempt/provider-call-request.json
evaluator/attempt/adapter-request.bin               # when available
evaluator/attempt/response.bin                      # when available
evaluator/attempt/error.bin                         # when available
evaluator/attempt/usage.json                        # when available
evaluator/attempt/tool-arguments/000.bin            # first argument, when available; additional arguments use contiguous zero-padded indices
evaluator/result.json
decision/classification.json
boundary.json
checksums.json
```

`identity.json` carries `DERIVATIVE_SCHEMA_ID`, preflight/instrument/attempt fingerprints, reviewed commit, model/profile, destination, and a noncircular `derivative_subject_fingerprint` over those facts plus the evaluator result and classification. `checksums.json` computes `derivative_archive_identity = fingerprint({"schema": checksum_schema, "records": records})` after every other file is final; that checksum aggregate is the official derivative archive identity returned by the verifier. Never embed the aggregate back into a checksummed member. `launch/invocation-binding.json` records only supplied launch values and `transmit: true`; do not claim authenticated human authorization. `decision/classification.json` carries classification plus semantic recommendation or null. `boundary.json` uses the exact vertical-witness value.

Preserve returned response/error, usage, elapsed timing, provider metadata/model identity, adapter request bytes, and tool arguments when available. Label adapter bytes as adapter/LiteLLM evidence, never HTTP wire evidence. Store no hidden chain-of-thought and request none.

The verifier must derive the allowed optional evaluator files from `evaluator/attempt/capture.json`, require every checksummed path and role, reject every unchecksummed/extra file, reject all `compiler`, `handoff`, `checkpoint-2`, and successor-policy members, recompute classification from result plus staged recipe bytes, and recheck all source/instrument/preflight identities.

- [ ] **Step 9: Run readiness and execution tests and commit**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -q
```

Expected: PASS. Every provider is a fake; the vertical witness reaches exactly one evaluator call and every outcome leaves compiler entry absent.

Commit:

```powershell
git add scripts/lm9b_p_readiness_probe.py scripts/lm9b_p_evaluator_only_continuation.py scripts/lm9b_p_evaluator_only_continuation_artifacts.py mcp_server/tests/test_lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py
git commit -m "feat: add one-dispatch evaluator continuation"
```

### Task 4: Pin attempt consumption, rename reconciliation, and closed boundary behavior

**Files:**
- Modify: `scripts/lm9b_p_evaluator_only_continuation_artifacts.py`
- Modify: `scripts/lm9b_p_evaluator_only_continuation.py`
- Modify: `mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py`

**Interfaces:**
- Consumes: Task 3 sealed/unsealed artifacts and atomic staging.
- Produces: `finalize_derivative_archive(...)`, `reconcile_derivative_rename(...)`, and permanent attempt-consumption enforcement.

- [ ] **Step 1: Add the failing rename-reconciliation table**

Use one parameterized table:

```python
@pytest.mark.parametrize(
    ("rename_case", "expected"),
    [
        ("success", "sealed"),
        ("success_then_exception", "sealed"),
        ("failure_before_move", "post_dispatch_unsealed"),
        ("invalid_destination_after_move", "ambiguous_unsealed"),
        ("both_staging_and_destination", "ambiguous_unsealed"),
    ],
)
def test_atomic_rename_reconciliation(
    sealed_staging,
    monkeypatch: pytest.MonkeyPatch,
    rename_case: str,
    expected: str,
) -> None:
    _install_rename_behavior(monkeypatch, sealed_staging, rename_case)
    result = CONT_ARTIFACTS.finalize_derivative_archive(
        sealed_staging.staging_dir,
        sealed_staging.destination,
        expected_derivative_identity=sealed_staging.derivative_identity,
    )
    assert result.state == expected
    if expected == "sealed":
        CONT_ARTIFACTS.verify_sealed_derivative_archive(
            sealed_staging.destination,
            expected_derivative_identity=sealed_staging.derivative_identity,
        )
    else:
        assert result.classification is None
```

`success_then_exception` must perform the actual same-volume rename and then raise. `failure_before_move` leaves staging and no destination. `invalid_destination_after_move` corrupts the moved destination before raising. `both_staging_and_destination` copies rather than moves before raising. Preserve all material in ambiguous cases.

- [ ] **Step 2: Add failing structural and consumption tests**

Add one test that inspects `ExecutionConfig`, `execute_continuation`, and CLI help to prove there are no Planner provider, compiler provider, compiler fixture, compiler identity, handoff, or checkpoint-2 inputs. Patch the actual compiler functions listed in Task 3 to raise and run every outcome-table row.

In the vertical witness, wrap external source-root and corrected-fixture reads with a counter that starts after atomic reservation. Permit staged-path reads and assert the external counter remains zero through classification and sealing; this pins the frozen post-verification snapshot rather than relying on a code comment.

Add one concurrent reservation test using two threads and one barrier; both target the same deterministic staging path and exactly one `mkdir(exist_ok=False)` succeeds. Add one consumption test proving:

- pre-dispatch refusal plus complete cleanup permits the same preflight only after a newly supplied fresh readiness record;
- pre-dispatch residue refuses reuse;
- durable `dispatch_started` refuses reuse forever;
- sealed archive refuses overwrite/resume/rebinding;
- unsealed staging refuses promotion under a different identity.

Add one closed-membership test that injects each of `compiler/`, `handoff/`, `checkpoint-2/`, `successor-disposition.json`, and an unknown file, then asserts derivative verification fails.

- [ ] **Step 3: Run the focused tests and verify failures before reconciliation is complete**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -k "rename or reservation or consumption or structural or membership" -q
```

Expected: FAIL on the unimplemented reconciliation/consumption assertions.

- [ ] **Step 4: Implement rename reconciliation without deleting evidence**

Finalize checksums and expected derivative identity entirely in staging, verify them there, and use one same-volume `Path.replace()` call. On exception:

1. If destination exists, staging is absent, and destination verifies against the exact expected checksums/identity, return sealed.
2. If staging exists and destination is absent, mark staging `post_dispatch_unsealed` with failure locus `atomic_rename`.
3. If staging exists and destination exists, preserve both and return an ambiguous unsealed result.
4. If staging is absent and destination exists but does not verify, preserve destination and return an ambiguous unsealed result.
5. Never delete already-written post-dispatch evidence, never issue a classification from an ambiguous state, and never relabel partial forensic hashes as checksum closure.

Do not catch a successful verified destination as a failure merely because `Path.replace()` raised after the move.

- [ ] **Step 5: Implement permanent consumption and pre-dispatch reuse rules**

Derive staging only from the preflight-bound derivative root and attempt fingerprint. Treat either durable marker below as consumed:

```python
staging / "dispatch" / "dispatch-started.json"
destination / "dispatch" / "dispatch-started.json"
```

Before dispatch, allow retry only if the caller supplies a newly verified readiness record and neither staging nor destination exists. After dispatch, refuse every reuse regardless of classification or seal state. Never overwrite, resume, or copy a consumed attempt into another destination/identity.

- [ ] **Step 6: Run the complete continuation test file and commit**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -q
```

Expected: PASS with one vertical witness, one outcome table, one pre-contact mutation table, one post-dispatch fault table, and one rename table.

Commit:

```powershell
git add scripts/lm9b_p_evaluator_only_continuation_artifacts.py scripts/lm9b_p_evaluator_only_continuation.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py
git commit -m "test: close evaluator continuation lifecycle"
```

### Task 5: Verify the complete instrument without provider contact

**Files:**
- Modify only if verification exposes a defect: the exact implementation/test file responsible for that defect
- Verify: all files listed in the File Map

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a clean, reviewable implementation branch; no preflight against the production archive and no provider/readiness observation.

- [ ] **Step 1: Compile every touched Python module**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m py_compile scripts/lm9b_p_planner_recipe_transfer_support.py scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py scripts/lm9b_p_readiness_probe.py scripts/lm9b_p_evaluator_only_continuation_artifacts.py scripts/lm9b_p_evaluator_only_continuation.py mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py
```

Expected: exit 0 and no output.

- [ ] **Step 2: Run the focused authority, readiness, and continuation tests**

Run:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py mcp_server/tests/test_lm9b_p_readiness_contract_units.py mcp_server/tests/test_lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_readiness_verifier.py mcp_server/tests/test_lm9b_p_readiness_witness.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -q
```

Expected: PASS with no skipped continuation outcome/fault rows.

- [ ] **Step 3: Run the complete LM9B-P test family**

Run:

```powershell
$lm9bPTests = Get-ChildItem mcp_server/tests -Filter 'test_lm9b_p_*.py' | ForEach-Object { $_.FullName }
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest $lm9bPTests -q
```

Expected: all LM9B-P tests pass. Do not claim a count until this command actually runs.

- [ ] **Step 4: Prove scope, cleanliness, and absence of accidental provider operations**

Run:

```powershell
git diff --check origin/main...HEAD
git status --short --branch
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
rg -n "successor-disposition|authenticated authorization|hidden chain-of-thought|compiler_provider|compiler_fixture|handoff_destination|checkpoint_2" scripts/lm9b_p_evaluator_only_continuation.py scripts/lm9b_p_evaluator_only_continuation_artifacts.py
```

Expected: `git diff --check` exits 0; only the File Map paths changed; continuation code contains only explicit boundary/non-claim uses of forbidden concepts and no compiler construction/call input; worktree is clean after the final commit.

- [ ] **Step 5: Review the implementation against every design section**

Use `docs/superpowers/specs/2026-07-22-lm9b-p-evaluator-only-continuation-design.md` as a checklist. Confirm source pins, constructive delta, shared equations, provider request, two fingerprints, destination/reparse handling, no-contact preflight, one-role readiness, frozen snapshot, dispatch boundary, three states, archive membership, evidence matrix, rename reconciliation, compiler behavior isolation, tests, post-merge sequence, and out-of-scope exclusions each map to concrete code and at least one deterministic assertion.

- [ ] **Step 6: Commit any verification-only corrections and stop for review**

If verification required changes, rerun the failed command plus the complete LM9B-P family, then commit only those corrections:

```powershell
git add scripts/lm9b_p_planner_recipe_transfer_support.py scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py scripts/lm9b_p_readiness_probe.py scripts/lm9b_p_evaluator_only_continuation_artifacts.py scripts/lm9b_p_evaluator_only_continuation.py mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py
git commit -m "fix: close evaluator continuation verification gaps"
```

If no corrections were required, create no empty commit. Stop with the branch, commit list, exact test results, and an explicit statement that no production preflight, readiness canary, or provider call was performed.

## Post-Merge Operator Sequence (Not Authorized by This Plan)

After implementation review and merge, a separate explicit authorization must govern each operational step:

1. Create a clean worktree at the reviewed merge SHA.
2. Run only the `preflight` subcommand to emit the no-contact content-addressed preflight.
3. Obtain explicit user approval naming that exact preflight fingerprint.
4. Run the existing readiness probe with `--role planner_evaluator --authenticate` into a fresh readiness directory.
5. Invoke `execute --transmit` with the exact preflight fingerprint and readiness files.
6. Accept only a verified sealed derivative identity or a clearly marked retained `post_dispatch_unsealed` staging result.

The scientific archive determines no successor policy. A separately reviewed result note may map `probe_candidate_blocked` to governed-resolution design, `probe_planner_failure` to Planner-defect investigation, or `probe_inconclusive` to instrument follow-up.
