"""LM5F deterministic local-worker scenario evaluation receipts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from rook.agent.local_worker_turn_response import (
    WorkerResponseKind,
    WorkerResponseValidationFailure,
)
from rook.agent.local_worker_turn_disposition import WorkerResponseDisposition
from rook.agent.local_worker_turn_harness import (
    HarnessStatus,
    LocalWorkerTurnHarnessRecord,
)

__all__ = (
    "LocalWorkerScenarioExpectation",
    "LocalWorkerScenarioCheck",
    "LocalWorkerScenarioResult",
    "LocalWorkerScenarioReport",
    "evaluate_local_worker_scenario_result",
    "build_local_worker_scenario_report",
)

ScenarioScalar = str | bool | None

_STATUSES = frozenset(HarnessStatus.__args__)
_DISPOSITIONS = frozenset(WorkerResponseDisposition.__args__)
_VALIDATION_FAILURES = frozenset(WorkerResponseValidationFailure.__args__)
_RESPONSE_KINDS = frozenset(WorkerResponseKind.__args__)


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

    def __post_init__(self) -> None:
        _require_non_empty_str(self.scenario_id, "scenario_id")
        _require_non_empty_str(self.category, "category")
        status = _require_choice(self.expected_status, _STATUSES, "expected_status")
        _require_optional_choice(
            self.expected_disposition,
            _DISPOSITIONS,
            "expected_disposition",
        )
        _require_optional_non_empty_str(
            self.expected_harness_failure,
            "expected_harness_failure",
        )
        _require_optional_bool(self.expected_attempt_valid, "expected_attempt_valid")
        _require_optional_choice(
            self.expected_attempt_failure,
            _VALIDATION_FAILURES,
            "expected_attempt_failure",
        )
        _require_optional_non_empty_str(self.expected_action_id, "expected_action_id")
        _require_optional_choice(
            self.expected_response_kind,
            _RESPONSE_KINDS,
            "expected_response_kind",
        )
        _require_optional_non_empty_str(
            self.expected_workflow_id,
            "expected_workflow_id",
        )
        _require_optional_non_empty_str(
            self.expected_contract_fingerprint,
            "expected_contract_fingerprint",
        )
        _require_optional_non_empty_str(self.expected_reason, "expected_reason")
        _validate_expectation_plane(self, status)


@dataclass(frozen=True)
class LocalWorkerScenarioCheck:
    field: str
    expected: ScenarioScalar
    actual: ScenarioScalar
    passed: bool
    reason: str

    def __post_init__(self) -> None:
        field = _require_non_empty_str(self.field, "field")
        _require_scenario_scalar(self.expected, "expected")
        _require_scenario_scalar(self.actual, "actual")
        passed = _require_bool(self.passed, "passed")
        expected_reason = f"{'matched' if passed else 'mismatched'}:{field}"
        if self.reason != expected_reason:
            raise ValueError("reason must match check outcome and field")
        if passed != (self.expected == self.actual):
            raise ValueError("passed must match expected and actual equality")


@dataclass(frozen=True)
class LocalWorkerScenarioResult:
    scenario_id: str
    category: str
    context_workflow_id: str
    context_contract_fingerprint: str
    passed: bool
    checks: tuple[LocalWorkerScenarioCheck, ...]
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty_str(self.scenario_id, "scenario_id")
        _require_non_empty_str(self.category, "category")
        _require_non_empty_str(self.context_workflow_id, "context_workflow_id")
        _require_non_empty_str(
            self.context_contract_fingerprint,
            "context_contract_fingerprint",
        )
        passed = _require_bool(self.passed, "passed")
        checks = _freeze_instance_tuple(
            self.checks,
            LocalWorkerScenarioCheck,
            "checks",
        )
        if not checks:
            raise ValueError("checks must not be empty")
        actual_passed = all(check.passed for check in checks)
        if passed != actual_passed:
            raise ValueError("passed must match check outcomes")
        expected_reason = (
            "passed" if actual_passed else f"failed:{_first_failed_check(checks).field}"
        )
        if self.reason != expected_reason:
            raise ValueError("reason must match check outcomes")
        object.__setattr__(self, "checks", checks)


@dataclass(frozen=True)
class LocalWorkerScenarioReport:
    total: int
    passed: int
    failed: int
    results: tuple[LocalWorkerScenarioResult, ...]
    failure_fields: Mapping[str, int]
    failure_reasons: Mapping[str, int]
    failure_categories: Mapping[str, int]

    def __post_init__(self) -> None:
        total = _require_non_negative_int(self.total, "total")
        passed = _require_non_negative_int(self.passed, "passed")
        failed = _require_non_negative_int(self.failed, "failed")
        results = _freeze_instance_tuple(
            self.results,
            LocalWorkerScenarioResult,
            "results",
        )
        if not results:
            raise ValueError("results must not be empty")
        _reject_duplicate_scenario_ids(results)
        if total != len(results):
            raise ValueError("total must match results length")
        actual_passed = sum(1 for result in results if result.passed)
        if passed != actual_passed:
            raise ValueError("passed must match result outcomes")
        if failed != total - passed:
            raise ValueError("failed must equal total - passed")
        if passed + failed != total:
            raise ValueError("passed and failed must sum to total")

        expected_fields, expected_reasons, expected_categories = _failure_groupings(
            results
        )
        failure_fields = _freeze_count_mapping(self.failure_fields, "failure_fields")
        failure_reasons = _freeze_count_mapping(
            self.failure_reasons,
            "failure_reasons",
        )
        failure_categories = _freeze_count_mapping(
            self.failure_categories,
            "failure_categories",
        )
        if failure_fields != expected_fields:
            raise ValueError("failure_fields do not match failed results")
        if failure_reasons != expected_reasons:
            raise ValueError("failure_reasons do not match failed results")
        if failure_categories != expected_categories:
            raise ValueError("failure_categories do not match failed results")
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "failure_fields", failure_fields)
        object.__setattr__(self, "failure_reasons", failure_reasons)
        object.__setattr__(self, "failure_categories", failure_categories)


def evaluate_local_worker_scenario_result(
    expectation: LocalWorkerScenarioExpectation,
    record: LocalWorkerTurnHarnessRecord,
) -> LocalWorkerScenarioResult:
    if not isinstance(expectation, LocalWorkerScenarioExpectation):
        raise TypeError("expectation must be LocalWorkerScenarioExpectation")
    if not isinstance(record, LocalWorkerTurnHarnessRecord):
        raise TypeError("record must be LocalWorkerTurnHarnessRecord")

    checks = [_check("status", expectation.expected_status, record.status)]
    if expectation.expected_status == "completed":
        checks.append(
            _check(
                "disposition",
                expectation.expected_disposition,
                _record_disposition(record),
            )
        )
        if expectation.expected_attempt_valid is not None:
            checks.append(
                _check(
                    "attempt.valid",
                    expectation.expected_attempt_valid,
                    _record_attempt_valid(record),
                )
            )
        if expectation.expected_attempt_failure is not None:
            checks.append(
                _check(
                    "attempt.failure",
                    expectation.expected_attempt_failure,
                    _record_attempt_failure(record),
                )
            )
        if expectation.expected_action_id is not None:
            checks.append(
                _check(
                    "attempt.action_id",
                    expectation.expected_action_id,
                    _record_attempt_action_id(record),
                )
            )
        if expectation.expected_response_kind is not None:
            checks.append(
                _check(
                    "attempt.response_kind",
                    expectation.expected_response_kind,
                    _record_attempt_response_kind(record),
                )
            )
    else:
        checks.append(
            _check(
                "harness.failure",
                expectation.expected_harness_failure,
                record.failure,
            )
        )

    if expectation.expected_reason is not None:
        checks.append(_check("reason", expectation.expected_reason, record.reason))
    if expectation.expected_workflow_id is not None:
        checks.append(
            _check(
                "context.workflow_id",
                expectation.expected_workflow_id,
                record.context_workflow_id,
            )
        )
    if expectation.expected_contract_fingerprint is not None:
        checks.append(
            _check(
                "context.contract_fingerprint",
                expectation.expected_contract_fingerprint,
                record.context_contract_fingerprint,
            )
        )

    checks_tuple = tuple(checks)
    passed = all(check.passed for check in checks_tuple)
    return LocalWorkerScenarioResult(
        scenario_id=expectation.scenario_id,
        category=expectation.category,
        context_workflow_id=record.context_workflow_id,
        context_contract_fingerprint=record.context_contract_fingerprint,
        passed=passed,
        checks=checks_tuple,
        reason="passed" if passed else f"failed:{_first_failed_check(checks_tuple).field}",
    )


def build_local_worker_scenario_report(
    results: tuple[LocalWorkerScenarioResult, ...] | list[LocalWorkerScenarioResult],
) -> LocalWorkerScenarioReport:
    results_tuple = _freeze_instance_tuple(
        results,
        LocalWorkerScenarioResult,
        "results",
    )
    if not results_tuple:
        raise ValueError("results must not be empty")
    _reject_duplicate_scenario_ids(results_tuple)
    passed = sum(1 for result in results_tuple if result.passed)
    failed = len(results_tuple) - passed
    failure_fields, failure_reasons, failure_categories = _failure_groupings(
        results_tuple
    )
    return LocalWorkerScenarioReport(
        total=len(results_tuple),
        passed=passed,
        failed=failed,
        results=results_tuple,
        failure_fields=failure_fields,
        failure_reasons=failure_reasons,
        failure_categories=failure_categories,
    )


def _validate_expectation_plane(
    expectation: LocalWorkerScenarioExpectation,
    status: str,
) -> None:
    if status == "completed":
        if expectation.expected_disposition is None:
            raise ValueError("completed expectations require expected_disposition")
        if expectation.expected_harness_failure is not None:
            raise ValueError(
                "completed expectations must not set expected_harness_failure"
            )
        return

    if expectation.expected_harness_failure is None:
        raise ValueError(f"{status} expectations require expected_harness_failure")

    forbidden = {
        "expected_disposition": expectation.expected_disposition,
        "expected_attempt_valid": expectation.expected_attempt_valid,
        "expected_attempt_failure": expectation.expected_attempt_failure,
        "expected_action_id": expectation.expected_action_id,
        "expected_response_kind": expectation.expected_response_kind,
    }
    for field_name, value in forbidden.items():
        if value is not None:
            raise ValueError(f"{status} expectations must not set {field_name}")


def _check(
    field: str,
    expected: ScenarioScalar,
    actual: ScenarioScalar,
) -> LocalWorkerScenarioCheck:
    passed = expected == actual
    return LocalWorkerScenarioCheck(
        field=field,
        expected=expected,
        actual=actual,
        passed=passed,
        reason=f"{'matched' if passed else 'mismatched'}:{field}",
    )


def _record_disposition(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.disposition


def _record_attempt_valid(record: LocalWorkerTurnHarnessRecord) -> bool | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.valid


def _record_attempt_failure(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.failure


def _record_attempt_action_id(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.action_id


def _record_attempt_response_kind(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.response_kind


def _failure_groupings(
    results: tuple[LocalWorkerScenarioResult, ...],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    failure_fields: dict[str, int] = {}
    failure_reasons: dict[str, int] = {}
    failure_categories: dict[str, int] = {}
    for result in results:
        if result.passed:
            continue
        first_field = _first_failed_check(result.checks).field
        _increment(failure_fields, first_field)
        _increment(failure_reasons, result.reason)
        _increment(failure_categories, result.category)
    return failure_fields, failure_reasons, failure_categories


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _first_failed_check(
    checks: tuple[LocalWorkerScenarioCheck, ...],
) -> LocalWorkerScenarioCheck:
    for check in checks:
        if not check.passed:
            return check
    raise ValueError("checks contain no failed check")


def _reject_duplicate_scenario_ids(
    results: tuple[LocalWorkerScenarioResult, ...],
) -> None:
    seen: set[str] = set()
    for result in results:
        if result.scenario_id in seen:
            raise ValueError(f"duplicate scenario_id: {result.scenario_id!r}")
        seen.add(result.scenario_id)


def _freeze_instance_tuple(
    value: tuple[object, ...] | list[object],
    expected_type: type,
    field_name: str,
) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    for item in value:
        if not isinstance(item, expected_type):
            raise TypeError(f"{field_name} items must be {expected_type.__name__}")
    return tuple(value)


def _freeze_count_mapping(
    value: Mapping[str, int],
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied: dict[str, int] = {}
    for key, item in value.items():
        _require_non_empty_str(key, f"{field_name} key")
        copied[key] = _require_positive_int(item, f"{field_name}.{key}")
    return MappingProxyType(copied)


def _require_choice(
    value: object,
    allowed: frozenset[str],
    field_name: str,
) -> str:
    result = _require_str(value, field_name)
    if result not in allowed:
        raise ValueError(f"{field_name} has unknown value: {result!r}")
    return result


def _require_optional_choice(
    value: object,
    allowed: frozenset[str],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_choice(value, allowed, field_name)


def _require_scenario_scalar(value: object, field_name: str) -> ScenarioScalar:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    raise TypeError(f"{field_name} must be str, bool, or None")


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _require_optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    return _require_bool(value, field_name)


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_optional_non_empty_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_str(value, field_name)


def _require_non_empty_str(value: object, field_name: str) -> str:
    result = _require_str(value, field_name)
    if result == "":
        raise ValueError(f"{field_name} must not be empty")
    return result


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value
