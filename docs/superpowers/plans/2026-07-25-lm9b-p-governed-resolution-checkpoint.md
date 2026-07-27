# LM9B-P Governed-Resolution Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one no-contact-qualified scientific checkpoint that gives the exact faithful blocked parent recipe and verified successor user authority to one bounded Planner revision, rejects unrelated changes before evaluator contact, independently judges semantic fidelity, and seals a publicly reconstructible experimental result.

**Architecture:** Add a thin governed-resolution layer with a pure transition/isolation module, an evidence/preflight/archive module, and a bounded orchestration module. Reuse the qualified typed-fact carrier, existing Planner controller and mechanical gate, semantic evaluator parser/builder, shared blocker/classifier, and readiness verifier; extract only the currently inline Planner turn-request builder and expose the existing mechanical feedback renderer so execution and public reconstruction share one path. This slice emits an authenticated continuation carrier but never enters the later compiler join.

**Tech Stack:** Python 3.12.12 from `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe`, standard library, existing `jsonschema==4.26.0`, pytest, Git, Windows `Path.rename()`, existing LM9B-P scripts and sealed evidence.

## Global Constraints

- Work only in `C:/UDEV/Rook/.worktrees/lm9b-p-governed-resolution-checkpoint-design` on `codex/lm9b-p-governed-resolution-checkpoint-design`; never modify, clean, reset, or rebase the primary checkout.
- Base implementation on reviewed design commit `06be3159a6f4696b34d0f434a5a69b3a92d8507e` and main baseline `d6330a61a21d56abf16af6ba3b8f1678ede2c3ec`.
- Treat `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-visibility-intervention` and evaluator derivative `sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94` as immutable read-only evidence.
- Bind carrier qualification `sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e1`; do not regenerate or reinterpret it during implementation.
- Preserve `d6330a61a21d56abf16af6ba3b8f1678ede2c3ec` as the qualification's sole commit. Bind the later resolution commit separately and prove exact forward compatibility for every reused carrier component; do not weaken the existing qualification verifier or add an ignore-commit mode.
- Make no readiness, Planner, evaluator, compiler, Rhino, Grasshopper, or mutation provider contact during implementation, testing, review, merge, or development-preflight generation.
- Use fake providers and fake readiness records in tests. Real readiness and scientific dispatch require a separately reviewed post-merge preflight and explicit authorization.
- Keep `gpt-5.4`, `litellm.completion.tool_calling.no_parallel:v1`, temperature `0.0`, Planner bounds `6 / 16,384 / 180s / 600s / 120,000 / $10`, and evaluator bounds `1 / 8,192 / 180s` unchanged.
- Preserve existing controller semantics: maximum turns, token stop, or cost stop after rejected submissions means `probe_mechanically_rejected`; provider failure or terminal timeout means `probe_inconclusive` only when complete quiescent adapter request/error evidence is retained, while incomplete raised-call evidence remains `post_dispatch_unsealed`.
- Do not add dependencies, product code, LM9A authority, a new recipe dialect, a new provider adapter, a new readiness protocol, a shadow classifier, deterministic recipe patching, automatic retry, or compiler behavior.
- Request and preserve no hidden chain-of-thought; retain only ordinary provider response, tool arguments, usage, timing, and metadata exposed by the established adapters.
- Keep radial semantic keys, radial values, clause IDs, category expectations, and count `5` in fixtures/tests/policy-instance evidence only. Neutral modules must not interpret semantic-key meaning.
- Use the exact submitted successor recipe bytes for evidence and later eligibility. Normalization is comparison-only and must never rewrite the candidate.
- Make Task 1 a complete two-turn vertical witness through fake readiness, reservation, dynamic feedback, mechanical admission, isolation, evaluation, sealing, and public verification. Stop for independent review after Task 1.
- Use TDD with valid red states: imports and real symbol ownership must succeed before a test is accepted as failing for missing behavior.
- Use `apply_patch` for source/document edits. Use non-interactive Git commands and small commits.

---

## File and ownership map

### Existing files to modify

- `scripts/lm9b_p_planner_recipe_transfer_support.py`
  - Own the pure canonical Planner turn-request builder, fresh materializer, and public mechanical-feedback renderer used by both first-authorship and resolution.
- `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`
  - Prove exact first-authorship request/feedback compatibility and builder purity.

### New transition-specific files

- `scripts/lm9b_p_governed_resolution_support.py`
  - Pure immutable resolution-input assembly, revision rendering, policy-instance construction, fieldwise isolation, residual projection, and resolution outcome equations. No I/O, Git, clock, environment, provider, archive, or compiler behavior.
- `scripts/lm9b_p_governed_resolution_artifacts.py`
  - Physical evidence loading, instrument identity, preflight, attempt binding, path safety, reservation, archive writing, forensic retention, finalization, public reconstruction, and ready-proof issuance.
- `scripts/lm9b_p_governed_resolution_probe.py`
  - CLI and bounded operational orchestration over existing readiness, Planner, evaluator, gate, and artifact components. No compiler arguments or calls.
- `scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json`
  - Code-owned neutral isolation-policy definition and model/gate projections.
- `scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json`
  - Versioned successor-current semantic rubric with unchanged recommendation vocabulary.
- `scripts/lm9b_p_governed_resolution_fixtures/radial_isolated_successor_recipe.json`
  - Reviewed static fake-provider candidate. It is test evidence, never a production template or generated artifact.

### New tests

- `mcp_server/tests/test_lm9b_p_governed_resolution_support.py`
  - Authority equations, revision renderer, policy construction, isolation gate, outcome equations, and domain-neutrality tests.
- `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`
  - Source loading, identity closure, preflight, path/race/fault handling, archive membership, public reconstruction, and ready-proof provenance tests.
- `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
  - Two-turn vertical witness, real readiness-verifier traversal with fake bytes, dynamic request ledger, terminal outcomes, structural compiler isolation, and CLI tests.

## Constructive reachability ledger

| Transition | Real producer | Accepted shape | Re-verifying consumer | Durable evidence |
|---|---|---|---|---|
| Parent source | Existing public historical/derivative verifiers | Exact sealed bytes and parser-derived evaluator result | Resolution evidence loader | Source bindings |
| Successor authority | Qualified deterministic fixture | Generic forward task envelope and bindings | Typed-fact carrier plus pure assembler | Migration and authority partition |
| Initial Planner request | Pure revision renderer | Canonical semantic request bytes | Preflight and public verifier | Instrument/request records |
| Later Planner request | Shared pure turn builder plus existing feedback renderer | Canonical adapter-boundary bytes | Per-call dispatch and public call-ledger verifier | Per-call request/transcript rows |
| Candidate recipe | GPT-5.4 Planner tool arguments or fake-provider equivalent | Complete recipe bytes | Existing mechanical gate then isolation gate | Exact candidate and gate records |
| Semantic result | Existing evaluator parser | `PlannerEvaluationResult` | Shared classifier plus resolution outcome equations | Evaluator and classification records |
| Sealed result | Resolution archive writer | Closed checksum/identity graph | Public resolution verifier | Official checkpoint identity |
| Ready continuation proof | Public verifier only | Closed ready-proof carrier | Future LM9B-C continuation | No compiler activity in this slice |

---

### Task 1: Build the first complete two-turn vertical witness

**Review gate:** This task must pass and receive independent review before Task 2 begins.

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py:1390-1650`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`
- Create: `scripts/lm9b_p_governed_resolution_support.py`
- Create: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Create: `scripts/lm9b_p_governed_resolution_probe.py`
- Create: `scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json`
- Create: `scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json`
- Create: `scripts/lm9b_p_governed_resolution_fixtures/radial_isolated_successor_recipe.json`
- Create: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`

**Interfaces:**
- Consumes:
  - `lm9b_p_planner_recipe_transfer_support.run_planner_session()`
  - `lm9b_p_planner_recipe_transfer_support.evaluate_mechanical_gate()`
  - `lm9b_p_planner_recipe_transfer_support.run_planner_evaluation()`
  - `lm9b_p_readiness_contract.verify_launch_readiness()`
  - the sealed historical carrier qualification identity at `d6330a61a21d56abf16af6ba3b8f1678ede2c3ec`
  - `lm9b_p_evaluator_only_continuation_artifacts.verify_historical_source()`
  - `lm9b_p_evaluator_only_continuation_artifacts.verify_sealed_derivative_archive()`
- Produces:
  - `build_planner_provider_call_request(*, messages, provider_timeout_s) -> bytes`
  - `build_planner_provider_call_plan(*, turn_index, messages, session_started_monotonic_s, call_started_monotonic_s) -> PlannerProviderCallPlan`
  - `materialize_planner_provider_call_request(raw_bytes: bytes) -> dict[str, object]`
  - `build_planner_mechanical_feedback_message(gate_result, tool_call_id) -> dict[str, object]`
  - `assemble_verified_resolution_inputs(*, historical_source, parent_derivative, carrier_qualification, successor_envelope_bytes, payload_schema_bytes, semantic_registry_bytes, isolation_policy_bytes, evaluation_rubric_bytes, reviewed_commit_sha) -> VerifiedResolutionInputs`
  - `render_planner_revision_request(inputs) -> RenderedRevisionRequest`
  - `evaluate_resolution_isolation(*, inputs, candidate_recipe_bytes) -> IsolationGateResult`
  - `run_resolution_attempt(*, preflight, invocation_binding, readiness_record, readiness_manifest, head_sha, now_iso, credential_present) -> ResolutionAttemptResult`
  - role adapters are constructed internally and issued only after exact route,
    model, profile, temperature, and concrete-adapter verification
  - `verify_sealed_resolution_checkpoint(archive_dir, *, expected_identity, preflight_archive, expected_preflight_fingerprint) -> SealedResolutionCheckpoint`
  - `verify_historical_carrier_qualification_compatibility(*, archive_dir, expected_identity, repo_root, consuming_commit_sha) -> VerifiedCarrierQualificationCompatibility`
  - `bind_resolution_attempt(*, instrument, attempt_id, resolution_root, destination) -> AttemptBinding`
  - `write_resolution_preflight(*, destination, instrument, attempt_binding) -> VerifiedResolutionPreflight`
  - `verify_resolution_preflight(archive_dir, *, expected_fingerprint) -> VerifiedResolutionPreflight`
  - `reserve_resolution_staging(preflight) -> Path`

- [x] **Step 1: Add import-valid API skeletons and exact contract fixtures**

Create the three new Python modules with real imports, frozen dataclasses, exact
public signatures, and `NotImplementedError("task1 walking witness")` bodies.
This is API scaffolding only; it prevents missing-module or wrong-symbol errors
from masquerading as TDD evidence.

Use these public dataclasses in `lm9b_p_governed_resolution_support.py`:

```python
@dataclass(frozen=True)
class RenderedRevisionRequest:
    renderer_id: str
    payload: Mapping[str, object]
    raw_bytes: bytes
    raw_sha256: str
    canonical_fingerprint: str


@dataclass(frozen=True)
class IsolationPolicyInstance:
    definition_id: str
    definition_fingerprint: str
    value: Mapping[str, object]
    instance_fingerprint: str


@dataclass(frozen=True)
class VerifiedResolutionInputs:
    parent_recipe_bytes: bytes
    parent_recipe: Mapping[str, object]
    successor_envelope_bytes: bytes
    successor_envelope: Mapping[str, object]
    current_authority: object
    recipe_schema: Mapping[str, object]
    normalization_profile: object
    exclusion_policy: Mapping[str, object]
    brief: str
    authoring_contract: Mapping[str, object]
    evaluation_rubric: Mapping[str, object]
    correspondence: tuple[Mapping[str, object], ...]
    migration_ledger: tuple[Mapping[str, object], ...]
    policy_instance: IsolationPolicyInstance
    inputs_fingerprint: str


@dataclass(frozen=True)
class IsolationGateResult:
    status: Literal["isolated", "isolation_rejected"]
    equations: tuple[Mapping[str, object], ...]
    bounded_differences: tuple[Mapping[str, object], ...]
    parent_residual_bytes: bytes
    candidate_residual_bytes: bytes
    result_fingerprint: str
```

Use these initial artifact/probe dataclasses:

```python
@dataclass(frozen=True)
class ResolutionInstrument:
    inputs: SUPPORT.VerifiedResolutionInputs
    initial_request: SUPPORT.RenderedRevisionRequest
    contract_manifest: Mapping[str, object]
    instrument_fingerprint: str


@dataclass(frozen=True)
class VerifiedCarrierQualificationCompatibility:
    archive_dir: Path
    historical_qualification_identity: str
    historical_commit_sha: str
    consuming_commit_sha: str
    comparison_rows: tuple[Mapping[str, object], ...]
    compatibility_fingerprint: str


@dataclass(frozen=True)
class AttemptBinding:
    attempt_id: str
    resolution_root: Path
    destination: Path
    staging_path: Path
    attempt_fingerprint: str


@dataclass(frozen=True)
class VerifiedResolutionPreflight:
    archive_dir: Path
    record: Mapping[str, object]
    preflight_fingerprint: str
    instrument_fingerprint: str
    attempt: AttemptBinding


@dataclass(frozen=True)
class SealedResolutionCheckpoint:
    archive_dir: Path
    checkpoint_identity: str
    classification: str
    exact_recipe_bytes: bytes | None
    state: str = "sealed"


@dataclass(frozen=True)
class ResolutionAttemptResult:
    classification: str | None
    planner_session: PLANNER_SUPPORT.PlannerSessionResult | None
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult | None
    isolation_result: SUPPORT.IsolationGateResult | None
    sealed_checkpoint: ARTIFACTS.SealedResolutionCheckpoint | None
    state: str
```

Create `isolation_policy.json` with schema
`rook.lm9b_p.governed_resolution_isolation_policy:v1`, definition ID
`lm9b_p.governed_resolution_isolation_policy:v1`, the nine named equations
from the design, model obligations, gate obligations, and a computed
`policy_fingerprint`.

Create the rubric with the existing rubric schema, a new rubric ID
`lm9b_p.radial_resolution_fidelity:v1`, unchanged report vocabulary, and this
generic criterion statement:

```text
Values present in verified successor authority are supplied facts, not unresolved intent or Planner inventions.
```

Its `scenario_obligations` are exactly the retained ten-by-ten and radial-height
obligations plus that supplied-authority statement. The historical obligation
that spacing is absent from task authority must not appear in the successor
rubric; add a contract assertion that rejects it.

Create the static recipe by manually copying the exact sealed parent recipe and
making only these fixture-oracle changes:

```text
source_task.fingerprint = qualified successor-envelope fingerprint
unresolved_intent = []
goal.projected_into.unresolved_intent_ids = []
maintain.radial_box_array_semantics.source_refs += exact five task-envelope fact references
authority_artifacts -= exactly the descriptors derived as removable by the
  closed reachability equation
recipe_fingerprint = independently recomputed normalized fingerprint
```

The reachability equation derives removable descriptors only when their
complete parent reference set belonged exclusively to the removed unresolved
rows and they have no surviving candidate reference. For this fixture oracle,
the derived ordered ID list is exactly `["planning_policy"]`; neutral code must
not name it. Every retained descriptor remains byte-identical and ordered, and
the planning-policy artifact remains in the verified authority snapshot.

Do not add a fixture generator to production or tests.

- [x] **Step 2: Run import/contract smoke checks**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile `
  scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py
```

Expected: PASS. Parse both JSON contracts with strict existing JSON helpers.
Any import, syntax, or symbol failure must be corrected before accepting a red
test.

- [x] **Step 3: Write failing Planner request-builder compatibility tests**

Add tests that construct the exact first-turn message list and assert the new
builder is missing behavior rather than missing imports:

```python
def test_planner_turn_request_builder_matches_existing_request_value() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    raw = SUPPORT.build_planner_provider_call_request(
        messages=messages,
        provider_timeout_s=123.5,
    )
    assert json.loads(raw) == {
        "messages": messages,
        "tools": [SUPPORT.planner_tool_definition()],
        "tool_choice": "auto",
        "max_completion_tokens": SUPPORT.PLANNER_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": 123.5,
    }


def test_planner_turn_request_materialization_is_fresh() -> None:
    raw = SUPPORT.build_planner_provider_call_request(
        messages=[{"role": "user", "content": "x"}],
        provider_timeout_s=10.0,
    )
    one = SUPPORT.materialize_planner_provider_call_request(raw)
    two = SUPPORT.materialize_planner_provider_call_request(raw)
    assert one == two
    assert one is not two
    assert one["tools"] is not two["tools"]
```

Add an AST purity test forbidding `time`, `datetime`, `random`, `uuid`, `os`,
filesystem calls, and provider calls inside the builder.

- [x] **Step 4: Run the builder tests and verify a valid red state**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py `
  -k 'planner_turn_request_builder or planner_turn_request_materialization' -q
```

Expected: FAIL because the skeleton raises `NotImplementedError` or the public
builder does not yet exist. Import/attribute failures are not valid red states.

- [x] **Step 5: Implement the sole Planner turn-request builder and feedback exposure**

Implement canonical bytes and strict fresh materialization:

```python
def build_planner_provider_call_request(
    *,
    messages: Sequence[Mapping[str, object]],
    provider_timeout_s: float,
) -> bytes:
    if type(provider_timeout_s) not in (int, float) or provider_timeout_s <= 0:
        raise ValueError("Planner provider timeout must be positive")
    value = {
        "messages": json.loads(json.dumps(list(messages), ensure_ascii=False)),
        "tools": [planner_tool_definition()],
        "tool_choice": "auto",
        "max_completion_tokens": PLANNER_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": float(provider_timeout_s),
    }
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def materialize_planner_provider_call_request(raw_bytes: bytes) -> dict[str, object]:
    value = parse_strict_json(raw_bytes)
    if type(value) is not dict:
        raise ValueError("Planner provider request must be an object")
    rebuilt = build_planner_provider_call_request(
        messages=value.get("messages", []),
        provider_timeout_s=value.get("provider_timeout_s"),
    )
    if rebuilt != raw_bytes:
        raise ValueError("Planner provider request differs from builder contract")
    return json.loads(raw_bytes)
```

Rename `_planner_feedback_message` to the public
`build_planner_mechanical_feedback_message` and update `run_planner_session()`
to call it. Replace the inline request dictionary with builder bytes plus a
fresh materialized request. Do not change stop ordering or bounds.

- [x] **Step 6: Prove existing first-authorship behavior remains exact**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py -q
```

Expected: PASS. Add assertions that captured provider-request values/canonical
bytes and feedback messages equal their pre-extraction fixtures.

- [x] **Step 7: Commit the required shared extraction**

```powershell
git add scripts/lm9b_p_planner_recipe_transfer_support.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py
git commit -m "refactor: expose planner turn request construction"
```

- [x] **Step 8: Write the failing two-turn vertical witness**

In `test_lm9b_p_governed_resolution_probe.py`, load modules by their real file
owners and define fake providers whose request lists retain deep copies.

The Planner returns:

```python
planner = FakeProvider(
    [
        planner_turn(recipe_bytes=b"{}", call_id="planner-1"),
        planner_turn(
            recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
            call_id="planner-2",
        ),
    ]
)
```

The evaluator returns one exact valid report:

```python
evaluator = FakeProvider(
    [
        evaluator_turn(
            recommendation="semantically_faithful",
            criterion_id="brief_fidelity",
            finding="The current recipe faithfully represents the brief and successor authority.",
        )
    ]
)
```

Before readiness, bind a Task-1 attempt, write the no-contact preflight, and
call `verify_resolution_preflight()` with its exact fingerprint. Pass only the
returned verified preflight carrier to the orchestrator.

Build a fake readiness record using the real `RouteManifest`, existing
`canary_protocol_fingerprint()`, exact `lm9b_p.readiness_record:v1` schema,
current commit, fresh timestamps, and one deduplicated route with member roles
`("planner", "planner_evaluator")`. Do not verify it in test setup as a
substitute for execution. The real orchestrator must call
`verify_launch_readiness(record=record, manifest=manifest, head_sha=head_sha,
now_iso=now_iso, credential_present={route.route_fingerprint: True for route in
manifest.routes})`, require `.ok is True`, and atomically reserve staging before
the first Planner call.

Assert:

```python
assert result.classification == "probe_candidate_ready"
assert result.state == "sealed"
assert len(planner.requests) == 2
assert len(evaluator.requests) == 1
assert planner.staging_existed_at_every_call == [True, True]
assert preflight.record["instrument_contracts"]["ready_proof"]["contract_id"] == (
    "lm9b_p.governed_resolution_ready_proof:v1"
)
assert not {
    "proof_instance_identity",
    "checkpoint_identity",
    "eligible_recipe_identity",
} & set(preflight.record["instrument_contracts"]["ready_proof"])
assert json.loads(planner.requests[1])["messages"][-1]["role"] in {"tool", "user"}
assert result.isolation_result.status == "isolated"
verified = ARTIFACTS.verify_sealed_resolution_checkpoint(
    result.sealed_checkpoint.archive_dir,
    expected_identity=result.sealed_checkpoint.checkpoint_identity,
)
assert verified.classification == "probe_candidate_ready"
```

Patch actual compiler-specific functions to raise and assert they remain
untouched.

- [x] **Step 9: Run the vertical witness and verify a valid red state**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py::test_task1_two_turn_vertical_witness_publicly_verifies -q
```

Expected: FAIL at the first `NotImplementedError("task1 walking witness")`
inside the real resolution transition, not during import, fixture loading, or
readiness verification.

- [x] **Step 10: Implement the thinnest complete walking path**

Implement only the positive path needed by the witness:

1. Verify historical source and derivative; verify the carrier qualification
   as sealed historical evidence bound only to `d6330a61`, then separately
   prove the current checkout reuses exact carrier component bytes, runtime,
   fingerprints, and contract identities.
2. Derive the verified unit-context proof from exact source authority.
3. Validate successor envelope through the existing carrier.
4. Reconstruct parent facts/bindings, partition `P/U/S`, and exact migration.
5. Compose current semantic authority with unchanged environment/policy and
   successor task envelope; keep carrier contracts in instrument context.
6. Render the canonical revision request and assemble the thin Task-1
   instrument. Bind the ready-proof contract definition and issuance equations,
   but no response-dependent proof instance, checkpoint, or recipe identity.
7. Bind the attempt, write the no-contact preflight, and publicly verify its
   exact fingerprint.
8. Inside `run_resolution_attempt()`, publicly reverify the supplied preflight,
   run the real readiness verifier over the fake readiness bytes, and atomically
   reserve direct-child staging with `exist_ok=False` before dispatch.
9. Run the existing Planner controller through a recording dispatch wrapper.
10. Independently rerun the mechanical gate on accepted bytes.
11. Apply the nine exact isolation equations and residual comparison, including
    authority-descriptor reachability.
12. Render the parent-blind evaluator request and run existing evaluator parser.
13. Derive `probe_candidate_ready` through the shared blocker/classifier plus
    resolution outcome equations.
14. Write a closed minimal archive, reread it, and publicly reconstruct every
    positive-path claim.

Mark the initial archive record with:

```json
{
  "implementation_stage": "task1_vertical_unhardened",
  "compiler_dispatch_activity": false
}
```

This label prevents the walking witness from being mistaken for the completed
instrument.

- [x] **Step 11: Run the vertical witness and focused compatibility suite**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py::test_task1_two_turn_vertical_witness_publicly_verifies `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py -q
```

Expected: PASS.

- [x] **Step 12: Commit Task 1 and stop for independent review**

```powershell
git add scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py `
  scripts/lm9b_p_governed_resolution_contracts `
  scripts/lm9b_p_governed_resolution_fixtures `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py
git commit -m "feat: add governed resolution vertical witness"
```

Stop. Provide the commit, exact test output, archive identity from the fake
witness, and clean-worktree evidence to an independent reviewer. Do not begin
Task 2 until explicitly approved.

---

### Task 2: Close source, authority, instrument, preflight, and pre-dispatch identity

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_support.py`
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Modify: `scripts/lm9b_p_governed_resolution_probe.py`
- Create: `mcp_server/tests/test_lm9b_p_governed_resolution_support.py`
- Create: `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`

**Interfaces:**
- Consumes: Task-1 public dataclasses and positive vertical path.
- Produces:
  - `load_verified_resolution_sources(*, historical_source_dir, derivative_archive, derivative_identity, carrier_qualification_archive, carrier_qualification_identity, repo_root, successor_envelope_path) -> VerifiedResolutionSources`
  - `assemble_resolution_instrument(*, sources, isolation_policy_path, evaluation_rubric_path) -> ResolutionInstrument`
  - `bind_resolution_attempt(*, instrument, attempt_id, resolution_root, destination) -> AttemptBinding`
  - `write_resolution_preflight(*, destination, instrument, attempt_binding) -> VerifiedResolutionPreflight`
  - `verify_resolution_preflight(archive_dir, *, expected_fingerprint) -> VerifiedResolutionPreflight`
  - exact closed instrument-contract manifest.

- [x] **Step 1: Write the source/authority mutation table before hardening**

Parameterize fully reclosed mutations for:

```python
AUTHORITY_MUTATIONS = (
    "missing_successor_key",
    "extra_successor_key",
    "parent_established_unresolved_overlap",
    "wrong_delta_schema",
    "wrong_delta_pointer",
    "wrong_delta_unit_context",
    "wrong_task_session",
    "retained_typed_value",
    "retained_authority_kind",
    "retained_provenance",
    "changed_environment",
    "changed_policy",
    "extra_carrier_contract",
    "typed_value_helper_drift",
    "carrier_artifact_helper_drift",
    "profile_drift",
    "registry_drift",
    "payload_schema_drift",
    "carrier_runtime_drift",
    "carrier_contract_identity_drift",
)
```

Each mutation must reclose the successor envelope, binding fingerprints,
carrier fingerprints, and authored downstream identities before expecting
refusal from the authoritative parent/successor equation.

- [x] **Step 2: Run the authority table and verify red cases expose missing equations**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  -k 'authority_mutation' -q
```

Expected: at least one reclosed mutation is incorrectly accepted by the thin
Task-1 implementation.

- [x] **Step 3: Implement physical loading and pure assembly separation**

Define:

```python
@dataclass(frozen=True)
class VerifiedResolutionSources:
    historical_source: CONT_ARTIFACTS.VerifiedHistoricalSource
    parent_derivative: CONT_ARTIFACTS.SealedDerivative
    carrier_qualification: VerifiedCarrierQualificationCompatibility
    exact_successor_bytes: bytes
    exact_contract_bytes: Mapping[str, bytes]
    reviewed_commit_sha: str
```

`load_verified_resolution_sources()` may read paths, Git, and files.
`assemble_verified_resolution_inputs()` may accept only this carrier and exact
bytes, must perform no I/O, and must construct no authority not already present
in verified artifacts.

Do not call `verify_qualification_archive()` from the later feature checkout:
that verifier correctly binds the qualification to its own commit. Instead,
verify the archived qualification's closed membership, physical destination,
checksums, aggregate identity, record, snapshot, runtime, and sole commit
`d6330a61`. Then build a distinct forward-compatibility result comparing:

```text
current lm9_semantic_typed_values.py
current lm9_typed_fact_carrier_artifacts.py
current profile, registry, and forward payload-schema bytes/fingerprints
current runtime and relevant contract identities
==
their exact qualified or d6330a61 Git-object identities
```

The typed-value helper must also equal the source hash sealed in the snapshot.
Any drift refuses before preflight. Do not modify the qualification module or
add a bypass mode. Preserve separate historical-qualification and
forward-compatibility fingerprints in all later evidence.

Implement literal set closure:

```python
if parent_established_keys & unresolved_keys:
    raise ValueError("parent established and unresolved keys overlap")
if successor_keys != parent_established_keys | unresolved_keys:
    raise ValueError("successor key set differs from P union U")
```

Use existing carrier functions for forward-envelope validation, parent-value
reconstruction, partition, and exact migration. Derive the value-free map from
parent unresolved rows and successor bindings without values or typed-value
fingerprints.

- [x] **Step 4: Implement closed semantic-authority and carrier-instrument composition**

Build the current gate authority from:

```text
semantic authority:
  exact unchanged environment
  exact unchanged planning policy
  exact successor task envelope replacing parent task envelope

instrument context:
  exact qualified forward payload schema
  exact semantic-value registry/profile/helper identities
  exact successor-aware payload-registry record
```

The successor-aware payload registry must contain the historical environment
schema and exact forward task-payload schema, update its version/fingerprint,
and contain no third entry. It is code-owned instrument support, not a semantic
artifact. Validate the successor envelope through the typed-fact carrier before
the existing mechanical gate sees the composed authority.

Do not modify `evaluate_mechanical_gate()`.

- [x] **Step 5: Implement the complete instrument-contract manifest**

Create a closed mapping with exact IDs and source-derived fingerprints for:

```python
CONTRACT_IDS = {
    "blocker_projection": "lm9b_p.explicit_blocker_projection:v1",
    "classifier": "lm9b_p.evaluated_recipe_classification:v1",
    "outcome_equations": "lm9b_p.governed_resolution_outcome_equations:v1",
    "archive_seal": "lm9b_p.governed_resolution_archive_seal:v1",
    "public_verifier": "lm9b_p.governed_resolution_public_verifier:v1",
    "ready_proof": "lm9b_p.governed_resolution_ready_proof:v1",
    "readiness_schema": READINESS.SCHEMA_ID,
    "readiness_verifier": "lm9b_p.readiness_launch_verifier:v1",
}
```

Include readiness `canary_protocol_fingerprint()`, exact role-derived
`RouteManifest.manifest_fingerprint`, `FROZEN_MAX_AGE_S`, blocker/classifier
source identities, outcome table fingerprint, closed archive membership,
sealing/finalization equations, public verifier source identity, and ready-proof
field/issuance equations. Recompute `instrument_fingerprint` from the complete
closed manifest; the reviewed commit is an additional input, not a substitute.
Record the historical qualification identity/commit and the separate
forward-compatibility fingerprint in distinct rows.

The ready-proof row binds only contract ID
`lm9b_p.governed_resolution_ready_proof:v1`, closed fields, issuance predicate,
and reconstruction equations. The preflight must contain no future proof
instance, instance fingerprint, checkpoint identity, or eligible recipe
identity; add a test that rejects any such response-dependent field.

- [x] **Step 6: Write preflight and attempt-binding red tests**

Add exact cases:

```python
PRECONTACT_REFUSALS = (
    "wrong_commit",
    "dirty_checkout",
    "altered_preflight",
    "altered_qualification_identity",
    "altered_contract_manifest",
    "invalid_attempt_id",
    "reused_attempt_id",
    "outside_root",
    "destination_exists",
    "staging_exists",
    "reparse_point",
    "filesystem_mismatch",
    "invocation_fingerprint",
)
```

Every case asserts Planner/evaluator counters remain zero and no
`dispatch_started` marker exists.

- [x] **Step 7: Implement preflight, path validation, and atomic reservation**

Use the exact attempt grammar:

```python
ATTEMPT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
ATTEMPT_ID_MAX_LENGTH = 64
```

Require a canonical absolute direct-child destination under an approved root,
reject reparse ambiguity, and verify staging/final destination share a
filesystem. Atomically reserve with `Path.mkdir(exist_ok=False)` only after
public preflight verification, internal readiness verification, and all other
pre-dispatch checks.

Serialize top-level preflight schema
`rook.lm9b_p.governed_resolution_preflight:v1`, every individual instrument
contract row, aggregate `instrument_fingerprint`, `attempt_fingerprint`, initial
semantic request bytes, role call budgets, zero compiler budget, and invocation
binding fields. The invocation record states only the supplied preflight
fingerprint, transmit flag, commit, readiness identity, and attempt identity;
it never claims the harness authenticated human authorization.

Before the first dispatch, the same preflight/attempt may be invoked again only
with renewed explicit invocation, fresh readiness, exact unchanged inputs, and
no destination or staging residue. There is no automatic readiness retry. The
first durable dispatch marker permanently consumes both identities.

- [x] **Step 8: Add readiness drift/refusal coverage**

Use the existing verifier for stale, missing, extra-role, wrong-model,
wrong-route, wrong-canary-protocol, wrong-manifest, wrong-commit, and missing
credential-presence rows. Do not modify readiness protocol code.

- [x] **Step 9: Run Task-2 focused suites**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py -q
```

Expected: PASS with all pre-dispatch cases proving zero dispatch.

- [x] **Step 10: Commit Task 2**

```powershell
git add scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py
git commit -m "feat: close resolution authority and preflight"
```

---

### Task 3: Harden fieldwise isolation and residual equality

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_support.py`
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Modify: `scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_support.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`

**Interfaces:**
- Consumes: `VerifiedResolutionInputs`, candidate bytes, existing normalization profile.
- Produces: complete `IsolationPolicyInstance` and independently recomputable `IsolationGateResult`.

- [x] **Step 1: Write the parameterized isolation mutation table**

Partition candidate mutations by the first boundary they truthfully reach after
independently recomputing recipe fingerprints and canonical order where
applicable:

```python
ISOLATION_REACHABLE_MUTATIONS = (
    "goal_statement",
    "affected_clause_statement",
    "missing_required_reference",
    "invariant",
    "postcondition",
)
MECHANICAL_REJECTION_MUTATIONS = (
    "wrong_source_task_fingerprint",
    "other_source_descriptor_field",
    "retained_unresolved_row",
    "new_unresolved_row",
    "wrong_goal_unresolved_ids",
    "affected_clause_id",
    "affected_clause_category",
    "affected_clause_location",
    "extra_reference",
    "duplicate_reference",
    "noncanonical_reference_order",
    "assumption",
    "derived_fact",
    "capability",
    "shape",
    "worker_slot",
    "authority_descriptor",
    "remove_retained_descriptor",
    "retain_derived_removable_descriptor",
    "add_authority_descriptor",
    "reorder_authority_descriptors",
    "mutate_retained_authority_descriptor",
    "unrelated_reference",
)
FINGERPRINT_RESUBMISSION_MUTATIONS = (
    "claimed_fingerprint",
)
```

Assert the mechanical gate first. Only the five mechanically accepted rows may
be evaluated as completed `isolation_rejected` outcomes. The other rows stop at
their observed mechanical or fingerprint-resubmission boundary.

- [x] **Step 2: Write policy-integrity control-failure tests**

Cover malformed or ambiguous parent/policy states:

```python
POLICY_CONTROL_FAILURES = (
    "unresolved_parent_clause_id",
    "multiply_resolved_parent_clause_id",
    "overlapping_equation_ownership",
    "duplicate_erased_location",
    "unconsumed_erased_location",
    "normalization_identity_mismatch",
    "policy_instance_fingerprint",
    "parent_proof_carrier",
)
```

These cases must raise a closed instrument error before issuing an isolation
verdict.

- [x] **Step 3: Verify the thin isolation implementation fails the new table**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  -k 'isolation_mutation or policy_control_failure' -q
```

Expected: FAIL for unimplemented equations or accepted unauthorized changes.

- [x] **Step 4: Implement exact policy-instance derivation**

Resolve each authenticated parent `affected_clause_id` to exactly one category
and canonical pointer. Seal the category/pointer into the instance. The neutral
gate branches on structural category and pointer, never radial names. The radial
fixture oracle separately asserts every category is `maintains`.

Build exact required reference objects from successor bindings and prove:

```python
if parent_reference_ids & required_reference_ids:
    return isolation_rejection("required_reference_already_present")
if candidate_reference_ids != parent_reference_ids | required_reference_ids:
    return isolation_rejection("reference_set_changed")
if len(candidate_reference_ids) != len(candidate_references):
    return isolation_rejection("duplicate_reference")
if candidate_references != normalize_reference_order(candidate_references):
    return isolation_rejection("reference_order")
```

- [x] **Step 5: Implement named equations and residual ownership**

Evaluate in this exact order:

```text
source_descriptor
resolved_unresolved_rows
authority_descriptor_reachability
goal_unresolved_projection
clause_ownership
authority_reference_additions
affected_clause_residual
recipe_fingerprint
global_residual_equality
```

Each equation emits one closed evidence row with exact owned pointers, input
hashes, status, and bounded differences. Remove a pointer from residual
projections only after its owning equation passes. Reject prefix masks,
overlapping owners, and unconsumed locations.

Compare canonical normalized residual bytes directly. Keep original candidate
bytes untouched.

- [x] **Step 6: Add a positive non-radial policy-mechanics witness**

Construct pure comparison inputs for a test-only recipe pair using unrelated
clause IDs and semantic keys but the same structural occurrence categories.
Prove the policy mechanics accept without claiming that the pair traversed the
closure-issued authority carrier or public gate, and without adding any
semantic-key or radial branch to source.

Scan neutral sources:

```powershell
rg -n "box_footprint|grid_spacing|minimum_height|maximum_height|radial_box_array|maintain\.radial" `
  scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py
```

Expected: no matches.

- [x] **Step 7: Run Task-3 suites**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py -q
```

Expected: PASS.

- [x] **Step 8: Commit Task 3**

```powershell
git add scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  docs/superpowers/plans/2026-07-25-lm9b-p-governed-resolution-checkpoint.md
git commit -m "feat: enforce exact resolution isolation"
```

---

### Task 4: Close bounded orchestration, evaluator blindness, and call-ledger outcomes

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_support.py`
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Modify: `scripts/lm9b_p_governed_resolution_probe.py`
- Modify: `scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`

**Interfaces:**
- Consumes: exact preflight, internally constructed fake/real role adapters,
  existing controller/evaluator/classifier.
- Produces: closed call ledger, terminal `ResolutionAttemptResult`, parent-blind evaluator request, and deterministic outcome evidence.

- [x] **Step 1: Write the complete outcome table**

Parameterize:

```python
OUTCOME_CASES = (
    ("max_turns", "probe_mechanically_rejected", 0),
    ("token_stop", "probe_mechanically_rejected", 0),
    ("cost_stop", "probe_mechanically_rejected", 0),
    ("planner_provider_failure", "probe_inconclusive", 0),
    ("planner_terminal_timeout", "probe_inconclusive", 0),
    ("isolation_rejected", "probe_resolution_isolation_failure", 0),
    ("semantic_unfaithful", "probe_planner_failure", 1),
    ("semantic_faithful", "probe_candidate_ready", 1),
    ("evaluation_inconclusive", "probe_inconclusive", 1),
    ("evaluator_malformed", "probe_inconclusive", 1),
    ("evaluator_provider_failure", "probe_inconclusive", 1),
)
```

Assert isolation rejection has zero evaluator calls and every terminal state has
no later call.

- [x] **Step 2: Write evaluator-visibility and request-drift tests**

Decode the exact evaluator semantic request and assert it contains:

```python
assert set(request) == {
    "schema",
    "renderer_id",
    "attempt_context",
    "brief",
    "authority_context",
    "final_recipe_json",
    "final_recipe_raw_sha256",
    "evaluation_rubric",
    "evaluation_report_contract",
}
```

Assert it contains no separate parent recipe, correspondence, policy instance,
isolation report, deterministic approval, expected classification, session
transcript, or compiler context. Scan keys and scalar values. Permit opaque
R01-labelled identities only where exact authenticated successor authority
retains them; do not rewrite that authority.

Mutate system prompt, tool schema, profile, model, limits, dynamic timeout,
feedback, report contract, and rubric after reclosing authored fingerprints;
execution must refuse because the preflight instrument differs.

- [x] **Step 3: Implement per-call canonical staging and fresh materialization**

For each Planner/evaluator call:

```text
persist and reread preflight, attempt, and fresh readiness bytes in staging
-> freeze execution to staged bytes and the verified in-memory snapshot
build canonical adapter-boundary bytes
-> bind preceding transcript/gate state and contiguous call index
-> persist
-> reread exact bytes
-> materialize fresh request object
-> write dispatch_started
-> consume the closure-issued adapter bound to the readiness route
-> call that configured adapter exactly once
-> capture complete response/error evidence
-> publish one immutable terminal row only after the owned context joins
```

After reservation, do not reread the external historical archive, derivative,
qualification, or fixture files. Reconstruct every later claim from the frozen
snapshot, staged bytes, and captured provider evidence.

The attempt-level consumption marker is written by the first call. Per-call
markers remain contiguous and role-bound. A provider mutation test must prove
retained bytes remain unchanged.

- [x] **Step 4: Implement parent-blind evaluator rendering and dispatch predicate**

Render only after independent mechanical acceptance and isolation success. Use
the new rubric with existing report schema, recommendation meanings, tool
definition, provider-request builder, and parser. Do not include controller
gate-success statements in model-visible content.

- [x] **Step 5: Implement closed resolution outcome equations**

Call `derive_evaluated_recipe_classification()` only after isolation passes.
Map shared outcomes as follows:

```python
if shared == "probe_candidate_blocked":
    raise ResolutionIntegrityError("blocked outcome is unreachable after isolation")
if shared in {"probe_candidate_ready", "probe_planner_failure", "probe_inconclusive"}:
    return shared
raise ResolutionIntegrityError("shared classifier returned an invalid outcome")
```

Isolation rejection is derived before evaluator construction. Mechanical and
provider terminations retain existing controller meanings.

- [x] **Step 6: Implement public call-ledger reconstruction**

Prove:

- contiguous indexes from zero;
- `1..N` Planner calls and `0..1` evaluator calls;
- Planner roles precede evaluator role;
- no calls after terminal state;
- each request reconstructs from prior transcript, gate, builder, timeout, and
  fixed controls;
- each dynamic timeout derives from controller-captured preceding deadline
  state through the shared call-plan builder;
- concrete adapters and adapter-authored requested model/profile metadata match
  authorized role identities;
- captured LiteLLM request bytes equal the shared pure projection of the exact
  Rook request and authorized adapter configuration;
- a sealable `ProviderCallFailure` retains hashed `raw_request` and `raw_error`,
  with the request independently rederived through that same projection;
- an unexpected exception or incomplete/contradictory failure carrier yields
  `post_dispatch_unsealed`, never a sealable inconclusive result;
- provider-returned identity metadata is preserved without claiming equality
  with the requested model/profile;
- aggregate token/cost/time values obey existing bounds and stop ordering;
- no unknown or compiler role exists.

Record exact derived stop cause separately from classification.

- [x] **Step 7: Add ambiguous timeout and still-live execution tests**

Use an owned fake execution context that remains joinable. Prove a terminally
raised/returned timeout with joined context may seal inconclusive, while a
still-live or ambiguous context yields `post_dispatch_unsealed` with no
classification.

- [x] **Step 8: Run Task-4 suites**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py -q
```

Expected: PASS.

- [x] **Step 9: Commit Task 4**

```powershell
git add scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py `
  scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py
git commit -m "feat: close resolution attempt outcomes"
```

- [x] **Step 10: Close Task-4 executable-transition provenance review**

Remove caller-supplied provider capabilities; construct closure-issued role
adapters from the verified route and role contracts. Derive and verify the
exact captured LiteLLM invocation through one shared pure projection. Keep
adapter-authored requested model/profile fields distinct from preserved
provider-returned metadata, with no requested/returned equality claim. Derive
dynamic timeouts from controller-captured
deadline state, publish immutable terminal rows only after evidence capture and
owned-context join, retain and reconstruct `ProviderCallFailure` request/error
evidence, refuse incomplete raised-call evidence as unsealed, and state/test
evaluator visibility as parent/comparison blindness with authenticated opaque
historical identity tokens preserved.

---

### Task 5: Close archive provenance, forensic retention, and ready-proof issuance

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Modify: `scripts/lm9b_p_governed_resolution_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`

**Interfaces:**
- Consumes: terminal attempt evidence from Task 4.
- Produces:
  - `seal_resolution_checkpoint(*, staging_dir, preflight, attempt_result) -> SealedResolutionCheckpoint`
  - `retain_post_dispatch_unsealed(*, evidence_dir, preflight, failure_locus) -> PostDispatchUnsealed`
  - `reconcile_resolution_rename(*, staging_dir, destination, expected_identity) -> SealedResolutionCheckpoint | PostDispatchUnsealed`
  - `issue_resolution_ready_proof(sealed_checkpoint, *, preflight_archive, expected_preflight_fingerprint) -> VerifiedResolutionReady`
  - `consume_resolution_ready_proof(proof, *, preflight_archive, expected_preflight_fingerprint) -> VerifiedResolutionReady`

- [x] **Step 1: Write the response-capture failure forensic-retention test**

Have a provider return, then inject failure while serializing its response
evidence before terminal publication. Require retained
`post_dispatch_unsealed` staging with the dispatch marker, canonical Rook
request, any captured LiteLLM request bytes, a precise capture failure locus,
no terminal row, no classification, and no automatic retry. This is the first
Task-5 red test; do not begin archive sealing over an escaping exception.

- [x] **Step 2: Define the exact closed archive membership in one constant**

Create `RESOLUTION_ARCHIVE_MEMBERS` with explicit role/path pairs for identity,
launch, source, instrument, authority, migration, correspondence, readiness,
Planner calls, candidate/gates, isolation, optional evaluator, outcome,
boundary, and checksums. Optional evaluator members are controlled only by one
closed classification/dispatch predicate; arbitrary missing/extra files fail.

Use top-level schema `rook.lm9b_p.governed_resolution_checkpoint:v1` and
unsealed marker `rook.lm9b_p.governed_resolution_post_dispatch_unsealed:v1`.

- [x] **Step 3: Write fully reclosed provenance-substitution tests**

For each case, alter authority evidence, consistently update every authored
downstream fingerprint/checksum/identity, and require public refusal:

```python
PROVENANCE_SUBSTITUTIONS = (
    "successor_authority",
    "initial_revision_request",
    "planner_tool_arguments",
    "mechanical_gate",
    "isolation_verdict",
    "evaluator_tool_arguments",
    "blocker_projection",
    "classification",
    "readiness_contract",
    "archive_contract",
    "ready_proof_contract",
    "call_order",
    "physical_destination",
)
```

Expected: current thin verifier accepts at least one case before hardening.

- [x] **Step 4: Implement writer/reread/checksum closure**

Before finalization, reread every staged file and prove source, execution
snapshot, preflight, instrument manifest, attempt, request, readiness,
classification, and ready-proof identities equal pre-dispatch values. Compute
the official checkpoint identity from the closed sorted checksum aggregate.

The writer never trusts authored evaluator result, isolation verdict,
classification, launch record, or dispatch record without reconstructing it.

- [x] **Step 5: Implement public constructive verification**

The public verifier must reload production-pinned source and code-owned
contracts, then rederive the complete graph specified in Design Section 19.
Require `archive.resolve() == canonical_destination` for official verification.
Use a private staging verifier before rename; never weaken the public location
contract. Public verification must also consume an independently supplied
preflight archive and expected fingerprint, physically verify its exact closed
record/request bytes, and compare the checkpoint instrument and attempt only
against that verified source. The checkpoint cannot reconstruct or authorize
its own preflight provenance.

- [x] **Step 6: Implement post-dispatch forensic retention**

Retain attempt/preflight identities, readiness bytes, dispatch markers,
canonical requests, returned evidence, failure locus, and best-effort hashes.
No classification or official checkpoint identity is allowed. Never delete
already-written post-dispatch evidence during cleanup.

If only an invalid final destination remains, best-effort write the unsealed
marker there.

- [x] **Step 7: Implement no-clobber rename and reconciliation**

Use `Path.rename()` on the same filesystem. Do not use `Path.replace()`.
Parameterize:

```python
RENAME_CASES = (
    "destination_appears_before_rename",
    "rename_succeeds_then_raises",
    "invalid_destination_only",
    "staging_only",
    "both_exist",
)
```

After any exception once rename begins, including destination-verification
failure after rename returns, reconcile staging and destination and verify the
final destination against exact expected identity/checksums before declaring
success. A transient verification failure followed by successful
reconstruction is sealed; ambiguous material remains unsealed with no result.

- [x] **Step 8: Implement the reconstructible resolution-ready proof carrier**

Define:

```python
@dataclass(frozen=True)
class VerifiedResolutionReady:
    checkpoint: SealedResolutionCheckpoint
    exact_recipe_bytes: bytes
    recipe_fingerprint: str
    successor_authority_records: tuple[object, ...]
    mechanical_gate_fingerprint: str
    isolation_result_fingerprint: str
    contract_fingerprint: str
```

Only the public verifier may issue it after reconstructing
`probe_candidate_ready`. Bind contract ID
`lm9b_p.governed_resolution_ready_proof:v1`, closed fields, issuance predicate,
and source fingerprint to the instrument manifest. A manually constructed
dataclass carries no authority: `consume_resolution_ready_proof()` must rerun
the public archive verifier at the identity-bound physical destination with an
independently supplied physical preflight archive and expected preflight
fingerprint, then compare every field before returning. No raw unchecked issuer
is exported.

- [x] **Step 9: Run Task-5 suites**

Run:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py -q
```

Expected: PASS.

- [x] **Step 10: Commit Task 5**

```powershell
git add scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py
git commit -m "feat: seal governed resolution evidence"
```

---

### Task 6: Close CLI boundaries, full regression, and development preflight

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_support.py`
- Update: `docs/superpowers/plans/2026-07-25-lm9b-p-governed-resolution-checkpoint.md`

**Interfaces:**
- Consumes: completed instrument from Tasks 1–5.
- Produces: no-contact `preflight`/`verify-preflight` CLI, full structural isolation proof, reviewed feature-HEAD development preflight, and implementation handoff.

- [ ] **Step 1: Implement the closed CLI**

Expose only:

```text
preflight
verify-preflight
run
verify-checkpoint
```

`preflight` and `verify-preflight` are no-contact. `run` requires an exact
preflight fingerprint, explicit transmit flag, fresh readiness record, attempt
identity, and configured Planner/evaluator adapters. It accepts no compiler
provider, compiler evaluator, compiler fixture, handoff, or compiler run
destination.

Implementation tests invoke only no-contact commands and fake-provider direct
functions. Do not invoke operational `run` with real adapters.

- [ ] **Step 2: Add structural compiler-isolation tests**

Patch actual compiler-specific entry points to raise:

- `lm9b_p_planner_recipe_transfer_artifacts.build_lm9bc_handoff`
- `lm9b_p_planner_recipe_transfer_probe.run_joined_probe`
- `lm9b_c_compiler_sufficiency_probe.run_probe`

Prove no call occurs. Parse CLI signatures and archive membership to prove no
compiler input or evidence path can enter. Historically located generic
provider adapter imports are allowed.

- [ ] **Step 3: Add source and contract scans**

Run neutral-source radial scan and compiler vocabulary scan:

```powershell
rg -n "box_footprint|grid_spacing|minimum_height|maximum_height|radial_box_array" `
  scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py

rg -n "compiler_provider|compiler_evaluator|compiler_run_root|build_lm9bc_handoff|checkpoint_2" `
  scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py
```

Expected: no production semantic-key matches and no compiler entry/control
matches. Generic non-executing boundary-fact strings may live only in closed
archive schema constants and must be asserted by exact test allowlist.

- [ ] **Step 4: Run focused and full regressions**

Run:

```powershell
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py -q

$lm9bPTests = Get-ChildItem 'mcp_server/tests' -Filter 'test_lm9b_p_*.py' | ForEach-Object FullName
& $python -m pytest @lm9bPTests -q

& $python -m py_compile `
  scripts/lm9b_p_planner_recipe_transfer_support.py `
  scripts/lm9b_p_governed_resolution_support.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py

git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Reconcile the final implementation ledger**

Change every completed checkbox in Tasks 1–6 from `[ ]` to `[x]`, including
this reconciliation step and the immediately following final commit step.
There must be no operational unchecked checkbox in the committed plan. Do not
record fingerprints that do not exist yet and do not change narrative code
examples.

- [ ] **Step 6: Commit the final feature-HEAD implementation**

```powershell
git add scripts/lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  docs/superpowers/plans/2026-07-25-lm9b-p-governed-resolution-checkpoint.md
git commit -m "test: qualify governed resolution instrument"
git status --porcelain=v1
```

Expected: commit succeeds and status prints nothing. This commit is the feature
`HEAD` to which the development preflight binds. Make no repository commit
after the preflight is emitted.

#### Required post-commit development preflight

Choose this fresh absolute development root outside official operational
archive namespaces and derive every output name from feature `HEAD`. Run only
the no-contact command:

```powershell
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
$commit = git rev-parse HEAD
$attemptId = "dev-governed-resolution-$($commit.Substring(0, 12))"
$devRoot = 'C:/Users/bring/rook-lm9b-p-attempts/2026-07-25-governed-resolution-development'
$destination = Join-Path $devRoot $attemptId
$preflightArchive = Join-Path $devRoot "$attemptId-preflight"
$derivativeArchive = 'C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-evaluator-only-continuation/derivatives/visibility-evaluator-01'

if (-not (Test-Path -LiteralPath $devRoot)) {
  New-Item -ItemType Directory -Path $devRoot | Out-Null
}
if ((Test-Path -LiteralPath $destination) -or (Test-Path -LiteralPath $preflightArchive)) {
  throw 'development destination or preflight already exists'
}

$preflightResult = & $python `
  scripts/lm9b_p_governed_resolution_probe.py preflight `
  --historical-source 'C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-visibility-intervention' `
  --derivative-archive $derivativeArchive `
  --derivative-identity 'sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94' `
  --carrier-qualification 'C:/Users/bring/rook-lm9b-p-attempts/2026-07-23-typed-fact-carrier-post-merge/d6330a61a21d56abf16af6ba3b8f1678ede2c3ec' `
  --carrier-qualification-identity 'sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e1' `
  --attempt-id $attemptId `
  --resolution-root $devRoot `
  --destination $destination `
  --output $preflightArchive | ConvertFrom-Json
```

Before running, resolve `$devRoot` and verify it is the intended evidence root.
The destination and preflight paths must not exist. This command must not read
credentials or contact readiness/provider routes.

Immediately verify:

```powershell
& $python `
  scripts/lm9b_p_governed_resolution_probe.py verify-preflight `
  --archive $preflightResult.archive_dir `
  --expected-fingerprint $preflightResult.preflight_fingerprint
```

Expected: the public verifier accepts, reports feature `HEAD`, and reports
`execution_permitted: false` / development-only eligibility.

Prove the worktree remains clean after preflight generation:

```powershell
git status --porcelain=v1
git diff --check
```

Expected: no output from status and zero exit from diff check. The preflight
must be outside the repository.

Prepare the review handoff without provider contact. Report:

- branch and exact feature `HEAD`;
- base identity;
- changed-file scope;
- focused and full LM9B-P test counts;
- development preflight, instrument, and attempt fingerprints;
- clean checkout and `git diff --check` results;
- zero readiness, Planner, evaluator, compiler, Rhino, Grasshopper, and mutation
  contact.

Do not push, open a PR, merge, run readiness, or invoke a model without a new
explicit instruction.

---

## Post-merge operational sequence — not implementation authorization

After an independently reviewed PR is merged:

1. Create a clean checkout at the reviewed merge SHA.
2. Regenerate and publicly verify a new operational preflight.
3. Review its exact preflight, instrument, attempt, route-manifest, and
   destination identities.
4. Obtain explicit authorization naming that preflight and separately allowing
   the bounded Planner/conditional-evaluator contact envelope.
5. Run fresh content-free readiness through the existing protocol.
6. If readiness passes, immediately reverify the complete instrument-contract
   manifest, checkout, source, qualification, authority, requests, paths, and
   readiness identities.
7. Reserve staging, run the single bounded resolution attempt, and seal or
   retain evidence under the specified lifecycle.
8. If and only if the sealed result is `probe_candidate_ready`, design/review a
   separate LM9B-C continuation preflight and authorization.

No step in this implementation plan authorizes that operational sequence.
