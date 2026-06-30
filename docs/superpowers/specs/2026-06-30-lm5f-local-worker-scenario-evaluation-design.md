# LM5F - Local Worker Scenario Evaluation Design

**Date:** 2026-06-30
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker boundary
**Predecessors:** LM5A local worker turn context, LM5B response contract, LM5C response disposition, LM5D one-turn harness, LM5E deterministic scenario suite

---

## 1. Goal

LM5F adds a deterministic scenario evaluation receipt layer over existing LM5D
harness records.

The production layer answers one question:

```text
Did an already-produced LocalWorkerTurnHarnessRecord match a compact
scenario expectation?
```

LM5F does not run workers, build contexts, define scenario catalogs, parse model
output, call a model, render prompts, dispatch tools, mutate graphs, continue
streams, read files, write reports, or integrate RookChat.

The intended chain is:

```text
LocalWorkerScenarioExpectation
+ LocalWorkerTurnHarnessRecord
-> LocalWorkerScenarioResult

tuple[LocalWorkerScenarioResult]
-> LocalWorkerScenarioReport
```

LM5E remains the story suite. LM5F names the measuring stick that future canned
workers and model probes can reuse without reinventing evaluation semantics
inside the noisy model layer.

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
```

Add one test file:

```text
mcp_server/tests/test_local_worker_scenario_evaluation.py
```

Do not edit LM5A-E production or test modules as part of LM5F:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/tests/test_local_worker_turn_scenarios.py
```

If LM5F exposes a genuine bug in LM5A-E, treat that as a separate finding rather
than bundling a production fix into this slice.

---

## 3. Public Surface

Export exactly:

```python
__all__ = (
    "LocalWorkerScenarioExpectation",
    "LocalWorkerScenarioCheck",
    "LocalWorkerScenarioResult",
    "LocalWorkerScenarioReport",
    "evaluate_local_worker_scenario_result",
    "build_local_worker_scenario_report",
)
```

Do not export:

- scalar type aliases;
- reason constants;
- category constants;
- helper functions;
- batch evaluators;
- scenario runners;
- report writers or serializers;
- model/probe types.

Production imports are limited to:

- `dataclasses`;
- `collections.abc.Mapping`;
- `types.MappingProxyType`;
- LM5B vocabulary and validation-failure types;
- LM5C disposition vocabulary;
- LM5D `HarnessStatus` and `LocalWorkerTurnHarnessRecord`.

Production must not import:

- LM5A `LocalWorkerTurnContext`;
- `run_local_worker_turn`;
- worker callable types;
- LM4 workflow compiler, stream, provider, or provenance modules;
- RookChat, model, prompt, server, dispatcher, or tool execution surfaces;
- file, JSON, YAML, path, timestamp, or environment APIs.

---

## 4. Data Model

All public dataclasses are frozen and validate coherence in `__post_init__`.
They are safe to construct directly; evaluator/build functions are normal paths,
not the only safe paths.

### LocalWorkerScenarioExpectation

```python
@dataclass(frozen=True)
class LocalWorkerScenarioExpectation:
    scenario_id: str
    category: str
    expected_status: HarnessStatus
    expected_disposition: WorkerResponseDisposition | None = None
    expected_harness_failure: str | None = None
    expected_attempt_valid: bool | None = None
    expected_attempt_failure: WorkerResponseValidationFailure | None = None
    expected_action_id: str | None = None
    expected_response_kind: WorkerResponseKind | None = None
    expected_workflow_id: str | None = None
    expected_contract_fingerprint: str | None = None
    expected_reason: str | None = None
```

Validation:

- `scenario_id` and `category` are non-empty strings.
- `expected_status` is validated against the existing LM5D `HarnessStatus`
  vocabulary.
- `expected_disposition` is validated against the existing LM5C
  `WorkerResponseDisposition` vocabulary when present.
- `expected_attempt_failure` is validated against the existing LM5B
  `WorkerResponseValidationFailure` vocabulary when present.
- `expected_response_kind` is validated against the existing LM5B
  `WorkerResponseKind` vocabulary when present.
- `expected_harness_failure`, `expected_action_id`,
  `expected_workflow_id`, `expected_contract_fingerprint`, and
  `expected_reason` are non-empty strings when present.
- `expected_attempt_valid` is `bool | None`.

`None` means "not checked." LM5F does not provide a separate "expect actual
None" sentinel in this slice.

### LocalWorkerScenarioCheck

```python
@dataclass(frozen=True)
class LocalWorkerScenarioCheck:
    field: str
    expected: str | bool | None
    actual: str | bool | None
    passed: bool
    reason: str
```

Validation:

- `field` is a non-empty stable field path such as `status`, `disposition`,
  `attempt.failure`, or `context.contract_fingerprint`.
- `expected` and `actual` are scalar only: `str | bool | None`.
- `passed` is a bool.
- `reason` is exactly:
  - `matched:<field>` when `passed is True`;
  - `mismatched:<field>` when `passed is False`.

LM5F does not use a separate `missing:<field>` reason. A missing or wrong-plane
actual value is represented as `actual=None` and `mismatched:<field>`.

### LocalWorkerScenarioResult

```python
@dataclass(frozen=True)
class LocalWorkerScenarioResult:
    scenario_id: str
    category: str
    context_workflow_id: str
    context_contract_fingerprint: str
    passed: bool
    checks: tuple[LocalWorkerScenarioCheck, ...]
    reason: str
```

Validation:

- string fields are non-empty.
- `checks` accepts a list or tuple and is normalized to a tuple.
- every check is a `LocalWorkerScenarioCheck`.
- at least one check is required.
- `passed == all(check.passed for check in checks)`.
- if all checks pass, `reason == "passed"`.
- otherwise, `reason == f"failed:{first_failed_check.field}"`.

`context_workflow_id` and `context_contract_fingerprint` always copy the actual
anchors from the evaluated `LocalWorkerTurnHarnessRecord`. A result remains
traceable after it leaves the harness record behind.

### LocalWorkerScenarioReport

```python
@dataclass(frozen=True)
class LocalWorkerScenarioReport:
    total: int
    passed: int
    failed: int
    results: tuple[LocalWorkerScenarioResult, ...]
    failure_fields: Mapping[str, int]
    failure_reasons: Mapping[str, int]
    failure_categories: Mapping[str, int]
```

Validation:

- `results` accepts a list or tuple and is normalized to a tuple.
- empty `results` raises `ValueError`.
- every result is a `LocalWorkerScenarioResult`.
- duplicate `scenario_id` values raise `ValueError`.
- `total == len(results)`.
- `passed == count(result.passed)`.
- `failed == total - passed`.
- grouping maps are accepted as `Mapping`, freeze-copied into
  `MappingProxyType`, and validated for non-empty string keys.
- grouping map values are positive integers; `bool` is rejected.
- groupings contain failed results only:
  - `failure_fields`: first failed check field -> count;
  - `failure_reasons`: result reason -> count;
  - `failure_categories`: result category -> count.

No passed-category counts are included in LM5F.

---

## 5. Plane Separation

LM5F preserves LM5D's distinction between harness-level failures and
LM5B/LM5C attempt/disposition outcomes.

For `expected_status != "completed"`:

Allowed expected fields:

```text
expected_status
expected_harness_failure
expected_reason
expected_workflow_id
expected_contract_fingerprint
```

Forbidden expected fields:

```text
expected_disposition
expected_attempt_valid
expected_attempt_failure
expected_action_id
expected_response_kind
```

For `expected_status == "completed"`:

Required:

```text
expected_disposition
```

Allowed:

```text
expected_attempt_valid
expected_attempt_failure
expected_action_id
expected_response_kind
expected_reason
expected_workflow_id
expected_contract_fingerprint
```

Forbidden:

```text
expected_harness_failure
```

The split is strict:

- `expected_harness_failure` is only for LM5D failure statuses such as
  `invalid_response` and `worker_error`.
- `expected_attempt_failure` is only for completed typed responses where LM5B
  produced an inadmissible attempt.

Examples:

```python
LocalWorkerScenarioExpectation(
    scenario_id="execution_ref_as_action",
    category="authority_boundary",
    expected_status="completed",
    expected_disposition="blocked",
    expected_attempt_valid=False,
    expected_attempt_failure="unknown_action_id",
)
```

```python
LocalWorkerScenarioExpectation(
    scenario_id="raw_dict_return",
    category="harness_failure",
    expected_status="invalid_response",
    expected_harness_failure="response_type_invalid",
)
```

A wrong actual plane is evaluation evidence, not API misuse. If an expectation
expects a completed response but the actual record is `worker_error`, the result
contains failed checks, with dependent completed-plane actuals represented as
`None`.

Exceptions are for malformed API inputs or incoherent artifacts, not for scenario
misses.

---

## 6. Evaluation Behavior

### Single Result

```python
def evaluate_local_worker_scenario_result(
    expectation: LocalWorkerScenarioExpectation,
    record: LocalWorkerTurnHarnessRecord,
) -> LocalWorkerScenarioResult:
    ...
```

Behavior:

- `expectation` must be `LocalWorkerScenarioExpectation`; otherwise `TypeError`.
- `record` must be `LocalWorkerTurnHarnessRecord`; otherwise `TypeError`.
- The function emits checks only for fields explicitly expected plus required
  implied fields.
- `status` is always checked.
- `disposition` is checked for completed expectations because it is required.
- `expected_reason`, if present, creates an exact `reason` check against
  `record.reason`.
- workflow id and contract fingerprint checks are emitted only when their
  expectation fields are present.
- actual anchors are always copied into the result.

LM5F evaluates only compact receipt fields:

```text
status
harness.failure
reason
disposition
attempt.valid
attempt.failure
attempt.action_id
attempt.response_kind
context.workflow_id
context.contract_fingerprint
```

LM5F never inspects:

```text
action input contents
clarification wording
observation wording
refusal explanation
knowledge packet contents
domain correctness
repair quality
response payload objects
```

### Report

```python
def build_local_worker_scenario_report(
    results: tuple[LocalWorkerScenarioResult, ...] | list[LocalWorkerScenarioResult],
) -> LocalWorkerScenarioReport:
    ...
```

Behavior:

- `results` must be a list or tuple; otherwise `TypeError`.
- empty results raise `ValueError`.
- every item must be `LocalWorkerScenarioResult`; otherwise `TypeError`.
- duplicate `scenario_id` values raise `ValueError`.
- output result order preserves caller order.
- failure groupings are computed from failed results only.

No batch evaluator is included. Callers can loop over `(expectation, record)`
pairs themselves and then call `build_local_worker_scenario_report(...)`.

---

## 7. Immutability

LM5F uses deep-enough immutability for a scalar receipt layer:

- all public dataclasses are frozen;
- sequence fields normalize to tuples;
- report grouping maps are `MappingProxyType`;
- grouping maps are freeze-copied at construction/build time;
- caller mutation after construction cannot alter checks, results, or reports;
- no JSON freezer is needed because LM5F stores no payloads.

---

## 8. Explicit Non-Goals

LM5F does not add:

- scenario catalogs;
- canned workers;
- context builders;
- worker runners;
- model calls;
- prompt rendering;
- raw model-output parsing;
- retry, fallback, critic, or oversight loops;
- action authorization;
- action dispatch or execution;
- graph mutation;
- stream execution;
- live Rhino/GH coverage;
- RookChat integration;
- file, JSON, or YAML loaders;
- report writers;
- serialization helpers;
- report fingerprints;
- timestamps;
- run ids;
- model ids;
- worker ids;
- report-of-reports or stochastic sampling.

LM5F is not a general evaluation framework. It is the first stable receipt shape
for comparing already-produced local-worker harness outcomes against compact
expectations.

---

## 9. Tests

Add:

```text
mcp_server/tests/test_local_worker_scenario_evaluation.py
```

Unit coverage should include:

- `__all__` surface;
- expectation validation for literal vocabularies and plane separation;
- check coherence and scalar validation;
- result coherence;
- report count/grouping coherence;
- immutable grouping maps and caller mutation isolation;
- completed action result pass;
- completed blocked unknown-action result pass;
- wrong-plane actual outcome produces failed result, not an exception;
- `invalid_response` and `worker_error` expectation paths;
- optional exact reason checks;
- optional workflow id/fingerprint checks;
- duplicate scenario id rejection;
- empty report rejection;
- API type errors.

Integration coverage should include one or two small real-chain tests:

```text
LM5A context
-> LM5B response
-> LM5D harness record
-> LM5F evaluation result/report
```

Tests may import LM5A builders and LM5D runner for this integration proof.
Production may not.

Do not edit `mcp_server/tests/test_local_worker_turn_scenarios.py` in LM5F.

---

## 10. Verification

Targeted:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Nearby:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Focused PlanGraph/local-worker gate:

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Static/scope checks:

- `git diff --check`;
- production diff exactly
  `mcp_server/src/rook/agent/local_worker_scenario_evaluation.py`;
- test diff adds only
  `mcp_server/tests/test_local_worker_scenario_evaluation.py`;
- no LM5A-E production or test edits;
- no `base_agent.py`, `src/Rook`, `src/RookNative`, or knowledge-store drift;
- AST/import guard for the LM5F production module forbidding compiler, stream,
  runtime, model, prompt, dispatcher, file, JSON, YAML, path, timestamp, and
  environment surfaces.

No live, model, RookChat, stream, dispatcher, or file-output test belongs to
LM5F.
