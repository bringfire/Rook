# Rook–Prime Acceptance Workflow Router North Star Staging Map

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** North Star architecture hypothesis — not implementation-ready and
not authorized for execution.

This file preserves the proposed seven-stage decomposition so later evidence
can confirm, amend, split, or reject it. It is not an executable implementation
plan. No checkbox below may begin until the relevant authority handoff has been
independently qualified and this document has been rewritten from that
evidence. In particular, the first required slice is the separate offline
qualification of:

```text
user intent
-> proposed acceptance artifact
-> independent adequacy review
```

That slice changes documentation and disposable artifacts only. It does not
implement a router, compiler, evaluator, Prime adapter, profile, persistence
owner, or live qualification.

**Goal:** Build a durable Rook-owned workflow router that uses Prime for role-separated model sessions, compiles task-local acceptance contracts into one generic deterministic evaluator, survives interruption without replaying mutations, and emits final statuses only through a deterministic Policy Gate.

**Architecture:** Rook persists an append-only state/dispatch ledger and advances one closed state machine. Prime remains the external session and reasoning runtime, while existing Rook owners retain target, mutation, receipt, and fenced-evidence authority. Acceptance expressions are a sealed contribution to the existing validation kernel; no parallel parser, budget engine, agent framework, semantic registry, or task-specific predicate switch is added.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, existing Rook MCP/FastMCP server, existing `rook.validation_kernel`, Prime RPC at the qualified runtime merge, pytest, Windows PowerShell, Rhino 8/Grasshopper only in the final separately authorized live task.

## Global Constraints

- Baseline exactly `4a2adfa39657118924d57468b77ec0aa1c4b8991`.
- Qualified Prime runtime exactly `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`, containing reviewed structured-error commit `30a6621bca698ef14f64e5e45c5b1b6364148789`.
- Do not silently adopt a newer Prime branch, tag, provider adapter, or event shape.
- No new external dependency; SQLite is Python stdlib.
- Reuse `rook.validation_kernel` for bounded parsing, owned JSON, canonicalization, budgets, sealed programs, phases, and reporting.
- Every state transition and external dispatch intent is append-only and committed before the external operation.
- Never automatically replay an Actor turn, a mutation-capable Prime turn, or an ambiguous probe mutation.
- Use separate top-level Prime sessions and enforced Rook profiles for distinct authorities; prompt-only separation is insufficient.
- MCP profiles claim canonical Rook dispatch authority, not hostile-process OS containment.
- `unsupported` is a compiler diagnostic; `unproven` is a claim result; neither is a final workflow status.
- Judgment cannot override deterministic failure, broken custody, or a material missing user decision.
- Task-local intent nouns and criterion IDs never select production evaluator code.
- The generic Grasshopper geometry-evidence projection remains a separate bounded slice.
- No Rhino, Grasshopper, model, provider, or MCP contact before Task 7's explicit authorization gate.
- Each task ends in an independent review gate; later tasks do not begin until the preceding task is approved.

---

## File And Ownership Map

| File | Responsibility |
|---|---|
| `mcp_server/src/rook/acceptance_workflow_contract.py` | Exact enums, immutable records, schemas, transition/status equations, canonical record construction |
| `mcp_server/src/rook/acceptance_workflow_store.py` | SQLite append-only ledger, hash-chain verification, optimistic CAS, open-workflow queries |
| `mcp_server/src/rook/acceptance_expression.py` | Closed typed expression vocabulary, validation-kernel contribution, compilation, deterministic evaluation |
| `mcp_server/src/rook/acceptance_policy.py` | Pure final-status and next-route Policy Gate |
| `mcp_server/src/rook/prime_rpc_adapter.py` | External Prime RPC lifecycle, session/event/process custody, fakeable transport boundary |
| `mcp_server/src/rook/acceptance_workflow_router.py` | Persist-before-dispatch orchestration, role-session control, recovery, public service methods |
| `mcp_server/src/rook/mcp_tool_profiles.py` | Enforced closed workflow role profiles |
| `mcp_server/src/rook/server.py` | Three public workflow tools and lifecycle wiring only |
| `mcp_server/src/rook/agent/tool_dispatcher.py` | Direct-dispatch parity for the three workflow tools and role profile wall |
| `mcp_server/src/rook/gh_behavioral_acceptance.py` | Reuse source/probe custody; remove named predicate authority after conformance parity |
| `mcp_server/tests/fixtures/acceptance_workflow/*.json` | Task-local point-row, Cartesian-grid, stair, judgment, and recovery conformance data |
| `mcp_server/tests/test_acceptance_workflow_contract.py` | Schema, state, status, hashing, and transition tests |
| `mcp_server/tests/test_acceptance_workflow_store.py` | SQLite durability, CAS, concurrency, and corruption tests |
| `mcp_server/tests/test_acceptance_expression.py` | Parser/type/compiler/interpreter/budget/macro/conformance tests |
| `mcp_server/tests/test_acceptance_policy.py` | Policy precedence and routing tests |
| `mcp_server/tests/test_prime_rpc_adapter.py` | Fake Prime transport, event, process, runtime, and terminal tests |
| `mcp_server/tests/test_acceptance_role_profiles.py` | Complete role allow/deny inventory and direct/canonical parity |
| `mcp_server/tests/test_acceptance_workflow_router.py` | End-to-end inert orchestration and recovery tests |
| `mcp_server/tests/test_acceptance_judgment.py` | Attributed text/image judgment and Policy integration |
| `docs/CURRENT_ARCHITECTURE.md` | Updated only after production behavior is implemented and qualified |

The first six new production modules are separate because their ownership and
failure semantics differ. Do not combine them into a single campaign runner,
and do not split them further merely to reduce line counts.

---

### Task 1: Closed Workflow Contract And Durable Ledger

**Files:**
- Create: `mcp_server/src/rook/acceptance_workflow_contract.py`
- Create: `mcp_server/src/rook/acceptance_workflow_store.py`
- Create: `mcp_server/tests/test_acceptance_workflow_contract.py`
- Create: `mcp_server/tests/test_acceptance_workflow_store.py`

**Interfaces:**
- Produces: `WorkflowState`, `WorkflowStatus`, `WorkflowRole`, `RecordKind`, `EffectClass`, `Idempotency`, `TransitionReason` string enums.
- Produces: `WorkflowRecord`, `WorkflowHead`, `ContractFailure`, and `AppendResult` frozen exact-type records.
- Produces: `admit_transition(state_before, state_after, reason) -> None | ContractFailure`.
- Produces: `build_workflow_record(candidate: Mapping[str, object], previous: WorkflowRecord | None) -> WorkflowRecord | ContractFailure`.
- Produces: `AcceptanceWorkflowStore.open(path: Path)`, `.append(record, expected_head_sha256)`, `.head(workflow_id)`, `.records(workflow_id)`, `.open_workflows()`, and `.verify(workflow_id)`.
- Consumes: `canonical_json_bytes()` and `canonical_fingerprint()` from `rook.validation_kernel.canonical_json`.

- [ ] **Step 1: Write RED tests for exact enums, transition pairs, terminal immutability, and state/status equations.**

Use parameterized cases that enumerate every table row from the specification
and an explicit cross-product refusal set. Include exact-type cases where
`True` is refused as an integer, enum subclasses are refused, and an unknown
state/reason is refused.

```python
@pytest.mark.parametrize(
    ("before", "after", "reason"),
    [
        (None, "intent_received", "workflow_created"),
        ("contract_compiling", "actor_running", "contract_compiled"),
        ("policy_deciding", "completed", "policy_verified"),
    ],
)
def test_admitted_transition_is_exact(before, after, reason):
    assert admit_transition(before, after, reason) is None


@pytest.mark.parametrize("terminal", ["completed", "rejected", "incomplete"])
def test_terminal_state_has_no_outgoing_transition(terminal):
    failure = admit_transition(terminal, "intent_received", "workflow_created")
    assert failure.code == "transition_not_admitted"
```

- [ ] **Step 2: Run the contract tests and require RED for missing owners.**

Run:

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_acceptance_workflow_contract.py -q
```

Expected: collection or import failure naming
`rook.acceptance_workflow_contract`.

- [ ] **Step 3: Implement exact enums, immutable records, and the closed transition matrix.**

Use `str, Enum` plus frozen/slotted dataclasses. Construct the transition map
once as an immutable mapping keyed by exact `(before, after, reason)` strings.
Expose no transition mutator or registration function.

```python
class WorkflowState(str, Enum):
    INTENT_RECEIVED = "intent_received"
    CONTRACT_DESIGNING = "contract_designing"
    CONTRACT_COMPILING = "contract_compiling"
    AWAITING_USER_DECISION = "awaiting_user_decision"
    ACTOR_RUNNING = "actor_running"
    EVIDENCE_COLLECTING = "evidence_collecting"
    EVALUATING = "evaluating"
    REPAIRING = "repairing"
    JUDGING = "judging"
    POLICY_DECIDING = "policy_deciding"
    COMPLETED = "completed"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"
```

Implement `public_status_for_state()` using the exact state/status equation;
nonfinal active states return `None`.

- [ ] **Step 4: Add RED tests for canonical record construction and hash chaining.**

Cover exact key sets, 64-character lowercase hashes, sequence zero for the
first record, prior-hash equality thereafter, evidence-kind/owner closure,
Prime/Rook nullable fields, and one-bit mutation of a prior record.

```python
def test_record_hash_is_canonical_and_chained(first_candidate, second_candidate):
    first = build_workflow_record(first_candidate, None)
    second = build_workflow_record(second_candidate, first)
    assert second.previous_record_sha256 == first.record_sha256
    assert second.record_sha256 == canonical_fingerprint(second.without_hash())
```

- [ ] **Step 5: Implement record admission and canonical hashing without mutable caller custody.**

Convert admitted raw mappings to owned immutable values before validation.
Never retain a caller list/dict reference. Validate record-kind-specific
payloads and exact evidence vocabularies. Compute the record hash only after
all fields are admitted.

- [ ] **Step 6: Run contract tests and require GREEN.**

Run the Step 2 command. Expected: all tests pass.

- [ ] **Step 7: Write RED SQLite tests for atomic append, CAS, restart, and corruption.**

Use `tmp_path`; never use the real application-state database. Cover:

- WAL enabled;
- one transaction appends one complete record;
- wrong expected head refuses without a row;
- duplicate `(workflow_id, sequence)`, operation ID, Prime message ID, and
  receipt correlation refuse;
- two connections racing the same head produce one success and one CAS refusal;
- reopening reconstructs the same head;
- broken prior hash or edited payload makes `verify()` fail closed; and
- `open_workflows()` excludes terminal states.

```python
def test_two_writers_cannot_advance_same_head(store_path, head, left, right):
    first = AcceptanceWorkflowStore.open(store_path)
    second = AcceptanceWorkflowStore.open(store_path)
    assert first.append(left, expected_head_sha256=head.record_sha256).ok is True
    refused = second.append(right, expected_head_sha256=head.record_sha256)
    assert refused.code == "workflow_head_changed"
```

- [ ] **Step 8: Implement the append-only SQLite store.**

Create tables with primary/unique constraints for workflow sequence,
operation IDs, Prime message IDs, and receipt correlations. Store canonical
record bytes plus indexed routing columns. Use `BEGIN IMMEDIATE`, verify the
expected head inside the same transaction, insert, commit, and then return.
There is no update or delete API.

- [ ] **Step 9: Run the complete Task 1 seam.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest `
  mcp_server/tests/test_acceptance_workflow_contract.py `
  mcp_server/tests/test_acceptance_workflow_store.py -q
python -m compileall -q `
  mcp_server/src/rook/acceptance_workflow_contract.py `
  mcp_server/src/rook/acceptance_workflow_store.py
git diff --check
```

Expected: all tests pass, compilation succeeds, diff check is silent.

- [ ] **Step 10: Commit Task 1 and stop for independent review.**

```powershell
git add `
  mcp_server/src/rook/acceptance_workflow_contract.py `
  mcp_server/src/rook/acceptance_workflow_store.py `
  mcp_server/tests/test_acceptance_workflow_contract.py `
  mcp_server/tests/test_acceptance_workflow_store.py
git commit -m "feat: add durable acceptance workflow ledger"
```

Review gate: no Task 2 work begins until transition completeness, immutable
record custody, SQLite CAS, and corruption refusal are independently approved.

---

### Task 2: Generic Acceptance Compiler, Evaluator, And Policy Gate

**Files:**
- Create: `mcp_server/src/rook/acceptance_expression.py`
- Create: `mcp_server/src/rook/acceptance_policy.py`
- Modify: `mcp_server/src/rook/gh_behavioral_acceptance.py`
- Create: `mcp_server/tests/test_acceptance_expression.py`
- Create: `mcp_server/tests/test_acceptance_policy.py`
- Create: `mcp_server/tests/fixtures/acceptance_workflow/point_row.json`
- Create: `mcp_server/tests/fixtures/acceptance_workflow/cartesian_grid.json`
- Create: `mcp_server/tests/fixtures/acceptance_workflow/stair_symbolic.json`
- Create: `mcp_server/tests/fixtures/acceptance_workflow/legacy_results.json`

**Interfaces:**
- Consumes: `ValidationProgramContribution`, `compose_and_seal_program()`, and
  `validate_artifacts()` from `rook.validation_kernel`.
- Produces: `seal_acceptance_program() -> SealedValidationProgram`.
- Produces: `compile_acceptance_contract(raw_contract_bytes: bytes, trusted_bundle: TrustedValidationBundleInput) -> PublishedValidationReport | ValidationControlFailure`.
- Produces: `evaluate_compiled_acceptance(compiled_report, binding_bytes, evidence_bytes) -> PublishedValidationReport | ValidationControlFailure`.
- Produces: `policy_decision(contract, claims, judgments, user_decisions, custody, budgets) -> PolicyDecision`.
- Preserves: existing source-trace admission, receipt correlation, probe execution, and restoration logic from `gh_behavioral_acceptance.py`.

- [ ] **Step 1: Freeze the three conformance fixtures before evaluator code.**

Encode point-row and the reviewed six-control Cartesian grid as closed
expression contracts. Encode the stair only with symbolic roles and generic
expressions for currently expressible claims; geometry-dependent unsupported
claims must compile to exact diagnostics until the separate evidence slice
exists. Include no `C*` IDs in contracts.

The point-count claim must use data, not a named branch:

```json
{
  "id": "point_count_equals_count",
  "authority": "deterministic_required",
  "expression": {
    "op": "equal",
    "args": [
      {"op":"collection_count","args":[{"op":"role","role":"points"}]},
      {"op":"field","source":{"op":"role","role":"countControl"},"name":"integerValue"}
    ]
  }
}
```

- [ ] **Step 2: Write RED schema/type/budget tests for every expression form and primitive operation.**

Parameterize exact admitted and rejected node shapes. Include:

- extra/missing keys;
- unknown operation;
- wrong arity;
- length compared to angle;
- exact float equality refusal;
- missing explicit tolerance;
- nonfinite values;
- depth, node, quantifier, collection, dependency-byte, and work limits;
- boolean supplied for integer;
- mutable input changed after call; and
- unknown evidence field.

- [ ] **Step 3: Run the expression tests and require RED.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_acceptance_expression.py -q
```

Expected: import failure for `rook.acceptance_expression`.

- [ ] **Step 4: Implement one sealed validation-kernel contribution.**

Create a `ValidationProgramContribution` with exact contract, binding,
evidence, and report schemas; compile/type/evaluate phases; closed issue
vocabulary; fixed budgets; and one report projection. Seal it using
`compose_and_seal_program()`. Do not expose a mutable operation registry.

The expression dispatcher is keyed only by the closed `op` vocabulary:

```python
_OP_EVALUATORS: Mapping[str, Callable[[EvalContext, OwnedNode], EvalValue]] = (
    MappingProxyType({
        "literal": _eval_literal,
        "role": _eval_role,
        "field": _eval_field,
        "equal": _eval_equal,
        "approx_equal": _eval_approx_equal,
        "for_all": _eval_for_all,
    })
)
```

The real mapping must contain every operation listed in the specification and
no task or criterion name. Seal-time checks require the mapping, type rules,
budget costs, and manifest vocabulary to have identical key sets.

- [ ] **Step 5: Add RED evaluator tests for exact arithmetic and three-valued logic.**

Cover all strong-Kleene rows, empty `for_all`/`any`, integer values beyond
`2**53`, dimensional arithmetic, division by zero, truncation, sampled
precision, missing/unsupported/error evidence, and quantifier short-circuit
work accounting.

```python
def test_zero_tolerance_does_not_collapse_large_integers(program):
    result = evaluate_expression(
        program,
        equal(literal_integer(2**53), literal_integer(2**53 + 1)),
    )
    assert result.boolean3 == "false"
```

- [ ] **Step 6: Implement typed evaluation and canonical macro lowering.**

Use integer arithmetic for integers, `Decimal` or exact admitted decimal
representation where required by the kernel profile, and explicit finite
checks. Lower every macro before type checking the runtime program. Test the
lowered AST fingerprint and evaluator result against the equivalent primitive
AST.

- [ ] **Step 7: Add RED conformance tests proving task additions are data-only.**

Load all three fixtures through the same sealed program. Assert the same
program fingerprint for each, authentic point-row/grid classifications equal
`legacy_results.json`, stair geometry claims are exact `unsupported`
diagnostics, renaming only a claim ID preserves expression results, and editing
an expression changes the contract hash.

Add an AST/source test that production evaluator files contain none of the
fixture criterion IDs or domain roles:

```python
FORBIDDEN = {
    "tread_geometry_present",
    "width_symmetric_about_centerline",
    "point_count_equals_count",
    "treads",
    "helix",
}
```

- [ ] **Step 8: Replace named predicate authority after parity.**

Retain source-trace validation, receipt/binding correlation, phase execution,
and exact restoration in `gh_behavioral_acceptance.py`. Route claim execution
through `evaluate_compiled_acceptance()`. Remove the switch over
`controls_present`, `point_count_equals_control`,
`point_count_equals_product`, `axis_values_equal_sequence`,
`axes_form_cartesian_product`, and `axis_equals_constant` only after the
conformance fixtures pass.

- [ ] **Step 9: Write RED Policy Gate precedence tests.**

Test every outcome independently:

```python
def test_judgment_cannot_override_deterministic_failure():
    decision = policy_decision(
        contract=required_contract(),
        claims=(claim("required", "fail"),),
        judgments=(judgment("required", "accept"),),
        user_decisions=(),
        custody=valid_custody(),
        budgets=exhausted_repair_budget(),
    )
    assert decision.status == "rejected"
    assert decision.reason == "deterministic_failure"
```

Include custody failure, authority violation, repair remaining/exhausted,
admissible evidence extension, user requirement, judgment accept/reject/
uncertain, `verified`, and `accepted_with_judgment`.

- [ ] **Step 10: Implement the pure Policy Gate.**

The function receives exact immutable records and returns a frozen
`PolicyDecision(next_state, status, reason, claim_ids)`. It performs no file,
network, model, Rook, Rhino, or Grasshopper operation.

- [ ] **Step 11: Run Task 2 and adjacent legacy tests.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
$kernelTests = Get-ChildItem -LiteralPath 'mcp_server/tests' `
  -Filter 'test_validation_kernel_*.py' | ForEach-Object FullName
python -m pytest `
  mcp_server/tests/test_acceptance_expression.py `
  mcp_server/tests/test_acceptance_policy.py `
  mcp_server/tests/test_gh_behavioral_acceptance.py `
  @kernelTests -q
python -m compileall -q `
  mcp_server/src/rook/acceptance_expression.py `
  mcp_server/src/rook/acceptance_policy.py `
  mcp_server/src/rook/gh_behavioral_acceptance.py
git diff --check
```

The discovered `$kernelTests` list must contain the current thirteen
`test_validation_kernel_*.py` files. A different count blocks the command until
the full current kernel seam is identified; do not silently skip it.

- [ ] **Step 12: Commit Task 2 and stop for independent review.**

```powershell
git add `
  mcp_server/src/rook/acceptance_expression.py `
  mcp_server/src/rook/acceptance_policy.py `
  mcp_server/src/rook/gh_behavioral_acceptance.py `
  mcp_server/tests/test_acceptance_expression.py `
  mcp_server/tests/test_acceptance_policy.py `
  mcp_server/tests/fixtures/acceptance_workflow `
  mcp_server/tests/test_gh_behavioral_acceptance.py
git commit -m "feat: compile generic acceptance expressions"
```

Review gate: reject Task 2 if a new task requires production Python changes,
if a criterion ID selects code, if a second parser/budget/report path exists,
or if the legacy named evaluator remains independently authoritative.

---

### Task 3: Prime RPC Role-Session Adapter

**Files:**
- Create: `mcp_server/src/rook/prime_rpc_adapter.py`
- Create: `mcp_server/tests/test_prime_rpc_adapter.py`
- Create: `mcp_server/tests/fixtures/acceptance_workflow/prime_events/*.jsonl`

**Interfaces:**
- Produces: `PrimeRuntimeIdentity`, `PrimeSessionSpec`, `PrimeSessionIdentity`, `PrimeTurnIntent`, `PrimeTurnOutcome`, and `PrimeReconciliation` frozen records.
- Produces: `PrimeRpcTransport` protocol with `request(method: str, params: Mapping[str, object]) -> Mapping[str, object]` and `events() -> AsyncIterator[Mapping[str, object]]`.
- Produces: `PrimeRpcAdapter.start_session(spec)`, `.prompt(session, intent)`, `.follow_up(session, intent)`, `.steer(session, message)`, `.abort(session)`, `.state(session)`, `.messages(session)`, `.statistics(session)`, and `.reconcile(session)`.
- Consumes: exact pinned Prime runtime path/commit/file hashes and router operation IDs.

- [ ] **Step 1: Capture the qualified Prime RPC contract as no-contact fixtures.**

Copy only bounded request/response/event shapes from the reviewed Prime docs and
retained qualified evidence. Fixtures must cover:

- normal terminal turn;
- one `agent_end` plus the closed `ipython_state`/`compaction_end`
  housekeeping suffix;
- provider error;
- missing, duplicate, and non-semantic-terminal lifecycle;
- post-terminal assistant/user/tool/mutation event;
- malformed event;
- interrupted process; and
- complete session statistics.

Do not retain API keys, OAuth values, arbitrary provider headers, or the
260-MiB helix runtime file as a checked-in fixture.

- [ ] **Step 2: Write RED fake-transport tests.**

Use an in-memory fake that records exact RPC method/params and yields fixture
events. Assert one session per role, exact model/provider/reasoning/settings,
stable operation ID correlation, exact terminal semantics, full stream hash,
and refusal of unexpected post-terminal events.

```python
async def test_actor_session_uses_exact_profile_and_runtime(fake_transport):
    adapter = PrimeRpcAdapter(fake_transport, pinned_runtime())
    session = await adapter.start_session(actor_spec())
    assert fake_transport.requests == [
        ("session/create", actor_spec().to_rpc_params())
    ]
    assert session.role == "actor"
    assert session.rook_profile == "workflow_actor"
```

- [ ] **Step 3: Run the adapter tests and require RED.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_prime_rpc_adapter.py -q
```

Expected: import failure for `rook.prime_rpc_adapter`.

- [ ] **Step 4: Implement the external RPC adapter without importing Prime internals.**

Resolve the exact executable/runtime files, hash them, start or attach using
the documented RPC transport, verify process PID plus creation time, and issue
only documented RPC methods. Normalize results into closed records without
interpreting Rook payloads or model prose.

The adapter must report `external_entry` separately from terminal outcome. A
transport error after external entry is not equivalent to no entry.

- [ ] **Step 5: Add RED mutation-replay and version-drift tests.**

Prove:

- missing runtime file, commit mismatch, or file-hash mismatch refuses before
  process start;
- a newer branch/tag does not satisfy the pin;
- a mutation-capable prompt with ambiguous terminal evidence is
  `not_replayable_after_external_entry`;
- a reasoning/read call proven not to enter transport may be retried with the
  same operation ID; and
- separate roles cannot reuse one top-level Prime session.

- [ ] **Step 6: Implement process/session custody and reconciliation reads.**

`reconcile()` reads Prime state/messages/statistics/session evidence and emits
a closed owner record. It does not decide the Rook workflow state. Retain exact
session file hash, event stream hash, process identity, terminal lifecycle,
message IDs, token/cost telemetry, and child IDs.

- [ ] **Step 7: Run Task 3 tests, compilation, and import-boundary scans.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_prime_rpc_adapter.py -q
python -m compileall -q mcp_server/src/rook/prime_rpc_adapter.py
rg -n "from prime|import prime|D:/prime-agent/packages" `
  mcp_server/src/rook/prime_rpc_adapter.py
git diff --check
```

Expected: tests pass; compilation passes; the import/path scan returns no
production coupling to Prime internals (the runtime path arrives through
trusted configuration).

- [ ] **Step 8: Commit Task 3 and stop for independent review.**

```powershell
git add `
  mcp_server/src/rook/prime_rpc_adapter.py `
  mcp_server/tests/test_prime_rpc_adapter.py `
  mcp_server/tests/fixtures/acceptance_workflow/prime_events
git commit -m "feat: add Prime RPC role-session adapter"
```

Review gate: use real Prime builders only in a separately reviewed no-network
capture if fixture ownership is questioned. Do not contact a provider or run a
model in Task 3.

---

### Task 4: Per-Role Rook Authority Enforcement And Public Control Tools

**Files:**
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Create: `mcp_server/tests/test_acceptance_role_profiles.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`

**Interfaces:**
- Produces: exact `Profile` enum values for six workflow profiles.
- Produces: `WorkflowAuthorityScope` admitted from trusted router environment/config, containing workflow, target, contract, receipt, binding, and probe-control scope.
- Produces: `workflow_profile_blocked_envelope(tool, profile, reason)`.
- Produces: MCP tools `rook_acceptance_start`, `rook_acceptance_status`, and `rook_acceptance_decide` backed by Task 5 service interfaces; Task 4 first wires fake service injection.

- [ ] **Step 1: Build an explicit closed caller/tool classification fixture.**

Generate a reviewed JSON fixture containing every currently advertised Rook
tool name and one classification per workflow profile:

```json
{
  "tool": "gh_edit",
  "workflow_actor": "allow_scoped",
  "workflow_evaluator": "deny",
  "workflow_judgment": "deny"
}
```

The fixture is complete against `list_tools()`. A future tool absent from the
fixture must be denied in all workflow profiles and fail the inventory test.

- [ ] **Step 2: Write RED profile-wall tests for all roles.**

For every tool/profile pair, assert advertisement and call admission. Test
canonical `call_tool()` and direct `ToolDispatcher` with identical caller-owned
arguments. Assert refusal precedes target lookup, panel enrichment, Rook bridge
dispatch, and mutation.

Add scope attacks:

- Actor uses wrong target/document;
- Evaluator mutates an unbound slider;
- Evaluator invokes `gh_edit`;
- Judgment invokes any live Rook tool;
- Designer schema profile invokes `rook_tools_call` for an authoring tool;
- meta-tool recursion attempts to bypass the wall; and
- unknown future tool.

- [ ] **Step 3: Run the role-profile tests and require RED.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_acceptance_role_profiles.py -q
```

Expected: missing profiles/scope owner.

- [ ] **Step 4: Implement exact workflow profiles and scope admission.**

Extend `Profile` with the six IDs from the specification. Unlike `lean`, every
workflow profile is an enforced default-deny wall. Resolve and validate the
trusted scope before accepting a workflow profile; missing or malformed scope
fails process startup instead of falling back to `full`.

Apply the same pure admission function in canonical and direct dispatch. Meta
tools re-enter it on the selected target tool.

- [ ] **Step 5: Add RED schemas for the three workflow control tools.**

Assert strict closed keys, exact target identity, strict positive/nonnegative
budgets with booleans rejected, contract bytes-or-null, expected ledger-head
hash, exact decision kind/payload pairing, and no arbitrary transition field.

- [ ] **Step 6: Wire the tools to an injected fake workflow service.**

Add no routing policy to `server.py` or `ToolDispatcher`. Each path validates
and delegates once to the same service method, validates the closed returned
envelope, and preserves exact data. Direct and canonical results must be
identical.

- [ ] **Step 7: Run Task 4 and complete gateway safety seams.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest `
  mcp_server/tests/test_acceptance_role_profiles.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_dispatcher_safety.py -q
python -m compileall -q `
  mcp_server/src/rook/mcp_tool_profiles.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py
git diff --check
```

- [ ] **Step 8: Commit Task 4 and stop for independent review.**

```powershell
git add `
  mcp_server/src/rook/mcp_tool_profiles.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/tests/test_acceptance_role_profiles.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py
git commit -m "feat: enforce acceptance workflow role authority"
```

Review gate: explicitly report the hostile-process nonclaim. Reject any design
that treats tool advertisement, `lean`, or a prompt as the enforcement wall.

---

### Task 5: Router, Persist-Before-Dispatch, And Crash Recovery

**Files:**
- Create: `mcp_server/src/rook/acceptance_workflow_router.py`
- Create: `mcp_server/tests/test_acceptance_workflow_router.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`

**Interfaces:**
- Consumes: Tasks 1–4 store, contract, compiler, policy, Prime adapter, role profiles, and fake workflow tool service seam.
- Produces: `AcceptanceWorkflowRouter.start(request)`, `.status(request)`, `.decide(request)`, `.advance(workflow_id)`, and `.reconcile_open_workflows()`.
- Produces: `RouterDependencies` containing fakeable Prime, Rook gateway, clock, process observer, and evidence store protocols.
- Produces: the real service instance used by canonical and direct workflow tools.

- [ ] **Step 1: Write RED persist-before-dispatch verticals.**

Use fake dependencies that assert the ledger already contains the exact intent
when called. Cover contract design, Actor prompt, fenced read, probe mutation,
judgment, and user decision. A store failure must cause zero external calls.

```python
async def test_actor_prompt_occurs_only_after_intent_commit(harness):
    async def prompt(session, intent):
        head = harness.store.head(harness.workflow_id)
        assert head.record_kind == "dispatch_intent"
        assert head.payload["operationId"] == intent.operation_id
        return completed_actor_turn()

    harness.prime.prompt_effect = prompt
    await harness.router.advance(harness.workflow_id)
    assert harness.prime.prompt_calls == 1
```

- [ ] **Step 2: Run router tests and require RED.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_acceptance_workflow_router.py -q
```

Expected: import failure for `rook.acceptance_workflow_router`.

- [ ] **Step 3: Implement creation, status, decision, and one-state advancement.**

`start()` validates the request, creates a ULID workflow ID, writes the initial
record, and schedules advancement; it does not wait for model completion.
`status()` is read-only. `decide()` uses expected-head CAS and only the exact
decision/state mappings. `advance()` handles exactly one state operation and
then reschedules from the new persisted head, preventing one unbounded call
stack.

- [ ] **Step 4: Add RED recovery-matrix tests.**

Inject process termination after each boundary:

1. before intent commit;
2. after intent commit, before external entry;
3. after idempotent read completion, before outcome commit;
4. after Actor prompt external entry, before any tool;
5. during Actor tool mutation;
6. after Rook terminal receipt, before Prime terminal;
7. after complete Actor evidence, before outcome commit;
8. during perturbation;
9. after perturbation receipt, before fenced read;
10. during restoration;
11. after restoration receipt, before evidence write; and
12. after evidence write, before state transition.

Assert the exact recovery matrix: only conclusive/idempotent cases resume;
ambiguous mutations become `incomplete`; no automatic restoration occurs.

- [ ] **Step 5: Implement startup reconciliation.**

At MCP service startup, validate every open ledger chain. For the last unmatched
intent, query only Prime and Rook owner facts, append one reconciliation record,
and either append the correlated outcome/transition or terminate truthfully.
Use ledger CAS so two router processes cannot recover the same head.

- [ ] **Step 6: Add RED duplicate and drift attacks.**

Test duplicate Actor session/message IDs, duplicate probe phase, reused receipt,
changed target PID/port/document, replaced document, changed contract hash,
changed binding after probe, mutated evidence file, lingering owned process,
and two concurrent router workers.

- [ ] **Step 7: Implement exact receipt/binding/probe custody.**

Select the latest committed terminal Actor receipt from the retained trace.
Admit the Actor binding against that receipt. For each operator probe, record
its own mutation and restoration receipts and revalidate the frozen component/
output IDs. Any unowned structural mutation terminates `incomplete`.

- [ ] **Step 8: Replace fake workflow service wiring with the real router.**

Create the store and router during MCP lifespan after configuration/profile
validation. Complete `reconcile_open_workflows()` before new starts. On shutdown,
stop admitting new advances, allow already-persisted operations to retain their
prefix, and do not mark ambiguous work complete.

- [ ] **Step 9: Run Task 5, all prior seams, and the Python suite.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest `
  mcp_server/tests/test_acceptance_workflow_contract.py `
  mcp_server/tests/test_acceptance_workflow_store.py `
  mcp_server/tests/test_acceptance_expression.py `
  mcp_server/tests/test_acceptance_policy.py `
  mcp_server/tests/test_prime_rpc_adapter.py `
  mcp_server/tests/test_acceptance_role_profiles.py `
  mcp_server/tests/test_acceptance_workflow_router.py -q
python -m pytest mcp_server/tests -q
python -m compileall -q mcp_server/src/rook
git diff --check
```

Record pre-existing unrelated failures separately and prove they are unchanged;
do not absorb or rewrite them in this slice.

- [ ] **Step 10: Commit Task 5 and stop for independent review.**

```powershell
git add `
  mcp_server/src/rook/acceptance_workflow_router.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/tests/test_acceptance_workflow_router.py
git commit -m "feat: route and recover acceptance workflows"
```

Review gate: independently inject every crash prefix. No live model or host
contact is authorized by passing inert recovery tests.

---

### Task 6: Attributed Multimodal Judgment

**Files:**
- Modify: `mcp_server/src/rook/acceptance_workflow_router.py`
- Modify: `mcp_server/src/rook/acceptance_policy.py`
- Create: `mcp_server/tests/test_acceptance_judgment.py`
- Create: `mcp_server/tests/fixtures/acceptance_workflow/judgment/*.json`

**Interfaces:**
- Consumes: separate `workflow_judgment` Prime session, exact contract claims, retained evidence hashes, and approved image attachments.
- Produces: `JudgmentRecord` with exact claim/result/model/session/evidence/confidence/rationale-hash fields.
- Preserves: Policy Gate precedence; judgment is data and never an evaluator override.

- [ ] **Step 1: Write RED judgment schema and attribution tests.**

Cover one record per requested claim, exact claim ID set and order, exact
immutable model identity, session identity, evidence hashes, image hashes,
confidence vocabulary, rationale hash, and closed result vocabulary. Reject
missing, duplicated, extra, malformed, or unrequested claim judgments.

- [ ] **Step 2: Write RED authority tests.**

Prove Judgment has no live Rook tools, cannot ask the router to mutate, cannot
change contract/binding/policy, cannot change a deterministic result, and
cannot resolve `user_required`.

- [ ] **Step 3: Run judgment tests and require RED.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_acceptance_judgment.py -q
```

- [ ] **Step 4: Implement judgment routing through the existing Prime adapter.**

Build one closed judgment request from exact claim text, authority, bounded
deterministic evidence summaries, retained artifact references, and approved
images. Use Prime's existing image attachment path. Persist dispatch intent
before session prompt and retain exact Prime evidence before admitting the
closed response.

- [ ] **Step 5: Add RED Policy integration cases.**

Test deterministic pass plus judgment accept -> `accepted_with_judgment`;
judgment reject -> `rejected`; uncertain/malformed/missing evidence ->
`needs_user_decision` or `incomplete` per contract; and deterministic fail plus
judgment accept -> deterministic failure remains authoritative.

- [ ] **Step 6: Run Task 6 and all deterministic Policy tests.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest `
  mcp_server/tests/test_acceptance_judgment.py `
  mcp_server/tests/test_acceptance_policy.py `
  mcp_server/tests/test_acceptance_workflow_router.py -q
python -m compileall -q `
  mcp_server/src/rook/acceptance_workflow_router.py `
  mcp_server/src/rook/acceptance_policy.py
git diff --check
```

- [ ] **Step 7: Commit Task 6 and stop for independent review.**

```powershell
git add `
  mcp_server/src/rook/acceptance_workflow_router.py `
  mcp_server/src/rook/acceptance_policy.py `
  mcp_server/tests/test_acceptance_judgment.py `
  mcp_server/tests/fixtures/acceptance_workflow/judgment
git commit -m "feat: add attributed acceptance judgment"
```

Review gate: use fake Prime providers and static images only. No provider or
Rhino contact occurs in Task 6.

---

### Task 7: Reconciliation, Release Verification, And Live Qualification

**Files:**
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Create: `docs/superpowers/reports/2026-08-15-rook-prime-acceptance-workflow-live-qualification.md`
- Modify only if a reviewed live defect is found: existing Task 1–6 owners and their tests

**Interfaces:**
- Consumes: exact reviewed merge SHA, exact qualified Prime runtime, clean Release deployment, fresh empty Grasshopper targets, frozen contracts, bindings, model rows, and evidence contract.
- Produces: one durable live qualification report and retained evidence hashes.

- [ ] **Step 1: Reconcile the complete implementation against the specification.**

Run source/AST checks proving:

- no task or criterion ID dispatch;
- no second parser/canonicalizer/budget/report implementation;
- no prompt-only role boundary;
- no Actor/probe replay path;
- no workflow transition API outside the closed router;
- no direct SQLite writes outside the store;
- no hidden model inside Policy Gate;
- no geometry mutation inside Judgment; and
- no adoption of an unreviewed Prime commit.

- [ ] **Step 2: Run the complete offline verification matrix.**

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests -q
python -m compileall -q mcp_server/src/rook
git diff --check
git status --short
```

Then run the repository's managed suite because existing solve-receipt and
fenced-snapshot behavior is a dependency:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release --no-restore
```

Expected: all current tests pass except independently documented unchanged
baselines. The worktree is clean after the implementation commits.

- [ ] **Step 3: Stop for complete pre-deployment independent review.**

The reviewer verifies exact commit scope, every staged gate, test counts,
Prime pin, role manifests, recovery injections, and no live artifacts. Do not
deploy from an unreviewed head.

- [ ] **Step 4: Merge normally and prepare a clean Release lane.**

After approval, merge without rebasing the reviewed commits. Create a clean
checkout at the exact merge SHA. Stage/validate the required Python runtime and
wheelhouse before any deployment mutation. Keep the dirty primary checkout
untouched.

- [ ] **Step 5: Request and perform one standard Release deployment.**

The authorization must cover only the exact reviewed command:

```powershell
& pwsh -NoProfile -File `
  'C:/UDEV/Rook/.worktrees/acceptance-workflow-router-runtime/scripts/deploy-local-testing.ps1' `
  -Configuration Release
```

Use no `-PayloadOnly`, `-SkipBuild`, `-UseRepoVenv`, or
`-DevPythonRuntime`. Let deployment refuse while Rhino/MCP processes are
running. Retain the transcript. Restart Rhino only after a successful complete
deployment.

- [ ] **Step 6: Verify effective runtime custody before any model contact.**

Retain and hash:

- merge-source `server.py` and installed release `site-packages/rook/server.py`;
- built and deployed `Rook.rhp`/`Rook.dll` selected for the actual target;
- Rhino PID and creation time after deployment;
- live MCP schema for all three workflow tools;
- exact Prime executable/runtime file hashes and merge identity; and
- exact role profile manifests.

On-disk hashes plus deployment/start ordering are custody evidence; do not
claim retrospective proof of an already-running binary.

- [ ] **Step 7: Freeze the live qualification artifacts before contact.**

Use two fresh empty Grasshopper documents in the same verified Rhino runtime:

1. model-free recovery/fencing target;
2. role-separated workflow target.

Freeze exact target PID/port/document serials, empty initial fenced/unfenced
snapshots as applicable, contract bytes, role manifests, Prime settings,
budgets, evidence paths, and acceptance rules. Hash all artifacts before the
first model call.

- [ ] **Step 8: Request one explicit authorization covering the bounded live sequence.**

The authorization must enumerate maximum model turns, repairs, read-only
evidence extensions, probe mutations/restorations, judgment calls, wall-clock
limit, spend limit, targets, and stop conditions. It must forbid rerun, cleanup,
fallback model, hidden replay, contract change, and additional host calls.

- [ ] **Step 9: Run model-free Gate A.**

Use the router APIs to exercise:

- start/status/decision state persistence;
- a known-good reviewed point-row contract;
- terminal receipt -> wait -> fenced evidence -> three control probes -> exact
  restoration -> deterministic `verified`;
- stale/superseded receipt refusal without data leakage; and
- one injected router-process restart between an idempotent read intent and its
  outcome, followed by successful reconciliation.

Gate A must prove no duplicate mutation/probe and reconstruct every transition
from the ledger. If Gate A fails, retain evidence and stop before Gate B.

- [ ] **Step 10: Run role-separated Gate B once.**

On the second fresh target:

```text
Acceptance Designer top-level Prime session
-> compile reviewed contract
-> user approval only if the frozen scenario requires it
-> Actor top-level Prime session
-> latest terminal receipt and Actor binding
-> deterministic evidence/probes/evaluation
-> at most one Actor repair when exact policy permits
-> separate read-only Judgment session for one judgment-allowed claim
-> deterministic Policy Gate
```

Retain complete Prime/Rook/ledger/process evidence. Model prose is not
acceptance evidence. Do not run a fallback model or a second campaign.

- [ ] **Step 11: Perform one post-run recovery audit without host mutation.**

Restart only the router/MCP process if that action was frozen and authorized.
Require it to reconstruct the terminal workflow from the ledger without Prime,
Rhino, or Grasshopper mutation and without duplicating a dispatch.

- [ ] **Step 12: Write the durable report and update current architecture.**

Report independently:

- state and dispatch custody;
- role authority;
- compiler/evaluator behavior;
- mechanical Grasshopper outcome;
- semantic claim results;
- judgment attribution;
- final Policy status;
- recovery behavior;
- calls, mutation counts, time, tokens, and cost; and
- exact artifacts and SHA-256 hashes.

State all nonclaims, including hostile-process containment, arbitrary intent
coverage, unimplemented geometry evidence, and provider token comparability.
Update `docs/CURRENT_ARCHITECTURE.md` only to describe behavior actually merged
and live-qualified.

- [ ] **Step 13: Run documentation and final repository checks.**

```powershell
git diff --check
git status --short
$changed = git diff --name-only 4a2adfa39657118924d57468b77ec0aa1c4b8991...HEAD
$changed
```

Verify the changed paths match reviewed production owners, tests, fixtures,
the architecture document, and report. No unrelated primary-checkout or
knowledge-counter file enters the commit.

- [ ] **Step 14: Commit the qualification documentation and stop.**

```powershell
git add `
  docs/CURRENT_ARCHITECTURE.md `
  docs/superpowers/reports/2026-08-15-rook-prime-acceptance-workflow-live-qualification.md
git commit -m "docs: record acceptance workflow qualification"
```

Do not expand the expression vocabulary or geometry evidence in response to a
single live specimen. Any defect found in Gate A or B receives its own bounded
reviewed repair; the original evidence remains unchanged.

---

## Plan-Wide Review Checklist

Before declaring this plan implemented, independently prove:

- [ ] Exactly one Rook workflow state owner exists.
- [ ] Exactly one acceptance parser/canonicalizer/budget/report path exists.
- [ ] Every external operation has a committed intent before entry.
- [ ] Every ambiguous mutation path refuses replay.
- [ ] Every role uses a separate top-level Prime session and enforced profile.
- [ ] Direct and canonical tool paths enforce identical authority.
- [ ] Unknown future tools are denied.
- [ ] No production source contains task-domain or criterion dispatch.
- [ ] Point-row and grid results preserve authentic classifications.
- [ ] Stair adds data only and unsupported geometry remains explicit.
- [ ] Judgment is attributed and cannot override deterministic failure/custody.
- [ ] Policy Gate alone emits final workflow status.
- [ ] Restart reconciliation is causal, idempotent where allowed, and
  fail-closed elsewhere.
- [ ] No provider/model/host contact occurred before the explicit live gate.
- [ ] Current architecture documentation describes only qualified behavior.
