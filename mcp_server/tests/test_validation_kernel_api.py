from __future__ import annotations

import copy
import importlib
import inspect
import json
import pickle
from types import SimpleNamespace

import pytest

import rook.validation_kernel as validation_kernel
from rook.validation_kernel import (
    BudgetExceededFailure,
    PublishedValidationReport,
    ValidationControlFailure,
    ValidationResult,
    compose_and_seal_program,
    validate_artifacts,
)
from rook.validation_kernel.owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonObject,
    JsonString,
)
from rook.validation_kernel.schema_profile import SchemaEvaluationReceipt

from tests._validation_kernel_fakes import (
    make_assembler_profile_candidate,
    make_phase_engine_contribution,
    make_validation_api_contribution,
    make_validation_bundle_bytes,
)


api_module = importlib.import_module("rook.validation_kernel.api")


@pytest.fixture(scope="module")
def api_program():
    return compose_and_seal_program(make_validation_api_contribution())


@pytest.fixture(scope="module")
def assembler_profile():
    return validation_kernel.seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate()
    )


def _carrier(profile: object, raw_bytes: bytes | None = None):
    return validation_kernel.issue_trusted_validation_bundle(
        profile,
        make_validation_bundle_bytes() if raw_bytes is None else raw_bytes,
    )


def _text(value: object) -> str:
    assert type(value) is JsonString
    return value.value


def _boolean(value: object) -> bool:
    assert type(value) is JsonBoolean
    return value.value


def _phase_rows(report: PublishedValidationReport) -> tuple[str, ...]:
    phases = report.value["phases"]
    assert type(phases) is JsonArray
    return tuple(_text(item) for item in phases)


def _artifact_identity(report: PublishedValidationReport) -> JsonObject:
    identity = report.value["artifact_identity"]
    assert type(identity) is JsonObject
    return identity


class _UnreadableInput:
    reads = 0

    def __len__(self) -> int:
        type(self).reads += 1
        raise AssertionError("invalid authority must stop before input scanning")

    @property
    def raw_bytes(self) -> bytes:
        type(self).reads += 1
        raise AssertionError("invalid authority must stop before carrier access")


def test_invalid_program_stops_before_any_artifact_scan() -> None:
    recipe = _UnreadableInput()
    carrier = _UnreadableInput()
    _UnreadableInput.reads = 0

    result = validate_artifacts(object(), recipe, carrier)  # type: ignore[arg-type]

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_identity_unavailable"
    assert result.artifact_role == "validation_program"
    assert result.program_fingerprint is None
    assert _UnreadableInput.reads == 0


def test_invalid_bundle_carrier_stops_before_recipe_scan(api_program: object) -> None:
    recipe = _UnreadableInput()
    carrier = _UnreadableInput()
    _UnreadableInput.reads = 0

    result = validate_artifacts(api_program, recipe, carrier)  # type: ignore[arg-type]

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_input_invalid"
    assert result.artifact_role == "validation_bundle"
    assert _UnreadableInput.reads == 0


@pytest.mark.parametrize("over_cap_role", ("recipe", "validation_bundle"))
def test_either_input_byte_cap_fails_before_hash_or_report(
    api_program: object,
    assembler_profile: object,
    over_cap_role: str,
) -> None:
    limits = {
        "recipe": 1_048_576,
        "validation_bundle": 4_194_304,
    }
    oversized = b"x" * (limits[over_cap_role] + 1)
    recipe = oversized if over_cap_role == "recipe" else b"{}"
    bundle = (
        oversized
        if over_cap_role == "validation_bundle"
        else make_validation_bundle_bytes()
    )

    result = validate_artifacts(
        api_program,
        recipe,
        _carrier(assembler_profile, bundle),
    )

    assert isinstance(result, BudgetExceededFailure)
    assert result.code == "validation_budget_exceeded"
    assert result.artifact_role == over_cap_role
    assert result.failure_stage == "preflight"
    assert result.recipe_input_payload_sha256 is None
    assert result.validation_bundle_input_payload_sha256 is None
    assert result.validation_bundle_fingerprint is None
    assert not isinstance(result, PublishedValidationReport)


def test_malformed_bundle_is_control_failure_without_semantic_report(
    api_program: object,
    assembler_profile: object,
) -> None:
    result = validate_artifacts(
        api_program,
        b'{"recipe":',
        _carrier(assembler_profile, b'{"validation_context":'),
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_input_invalid"
    assert result.artifact_role == "validation_bundle"
    assert result.recipe_input_payload_sha256 is not None
    assert result.validation_bundle_input_payload_sha256 is not None
    assert not isinstance(result, PublishedValidationReport)


def test_missing_constructability_shell_is_control_failure_without_report(
    api_program: object,
    assembler_profile: object,
) -> None:
    bundle = make_validation_bundle_bytes(bundle_updates={"task_envelope": None})

    result = validate_artifacts(
        api_program,
        b"{}",
        _carrier(assembler_profile, bundle),
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_constructability_failed"
    assert result.artifact_role == "validation_bundle"
    assert result.subject_path == "/task_envelope"
    assert not isinstance(result, PublishedValidationReport)


@pytest.mark.parametrize(
    ("recipe", "bundle", "expected_phases"),
    (
        (
            b'{"nested":',
            make_validation_bundle_bytes(),
            ("companion_artifacts:passed", "schema:failed"),
        ),
        (
            b'{"nested":{"value":1}}',
            make_validation_bundle_bytes(
                validation_context_updates={"environment_snapshots": [{}]}
            ),
            ("companion_artifacts:failed", "schema:passed"),
        ),
        (
            b'{"nested":',
            make_validation_bundle_bytes(
                validation_context_updates={"environment_snapshots": [{}]}
            ),
            ("companion_artifacts:failed", "schema:failed"),
        ),
    ),
)
def test_constructable_inputs_publish_all_independent_semantic_phase_evidence(
    api_program: object,
    assembler_profile: object,
    recipe: bytes,
    bundle: bytes,
    expected_phases: tuple[str, ...],
) -> None:
    result = validate_artifacts(
        api_program,
        recipe,
        _carrier(assembler_profile, bundle),
    )

    assert type(result) is PublishedValidationReport
    assert _phase_rows(result) == expected_phases
    assert _boolean(result.value["valid"]) is False
    assert _boolean(result.value["compile_ready"]) is False


def test_phase_integrity_failure_stops_before_report_seal(
    assembler_profile: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = compose_and_seal_program(
        make_validation_api_contribution(schema_scenario="integrity_failure")
    )
    calls = 0
    real_seal = api_module._seal_validation_report_with_audit

    def seal_spy(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real_seal(*args, **kwargs)

    monkeypatch.setattr(api_module, "_seal_validation_report_with_audit", seal_spy)

    result = validate_artifacts(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_integrity_failure"
    assert result.artifact_role == "phase_engine"
    assert calls == 0
    assert not isinstance(result, PublishedValidationReport)


def test_report_seal_failure_returns_only_control_failure(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_validation_api_contribution(
            report_projection_scenario="missing_field"
        )
    )

    result = validate_artifacts(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_constructability_failed"
    assert result.artifact_role == "report_seal"
    assert not isinstance(result, PublishedValidationReport)


def test_valid_inputs_replay_to_identical_published_report_bytes(
    api_program: object,
    assembler_profile: object,
) -> None:
    recipe = b'{"nested":{"value":1},"other":2}'
    carrier = _carrier(assembler_profile)

    first = validate_artifacts(api_program, recipe, carrier)
    second = validate_artifacts(api_program, recipe, carrier)

    assert type(first) is PublishedValidationReport
    assert type(second) is PublishedValidationReport
    assert first.canonical_bytes == second.canonical_bytes
    assert first.report_fingerprint == second.report_fingerprint
    assert first.value == second.value
    assert _phase_rows(first) == (
        "companion_artifacts:passed",
        "schema:passed",
    )


def test_recipe_member_reordering_moves_raw_hash_not_canonical_or_semantics(
    api_program: object,
    assembler_profile: object,
) -> None:
    first = validate_artifacts(
        api_program,
        b'{"nested":{"value":1},"other":2}',
        _carrier(assembler_profile),
    )
    second = validate_artifacts(
        api_program,
        b'{"other":2,"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert type(first) is PublishedValidationReport
    assert type(second) is PublishedValidationReport
    first_identity = _artifact_identity(first)
    second_identity = _artifact_identity(second)
    assert _text(first_identity["recipe_input_payload_sha256"]) != _text(
        second_identity["recipe_input_payload_sha256"]
    )
    assert _text(first_identity["recipe_value_fingerprint"]) == _text(
        second_identity["recipe_value_fingerprint"]
    )
    assert _text(first_identity["validation_bundle_fingerprint"]) == _text(
        second_identity["validation_bundle_fingerprint"]
    )
    assert _phase_rows(first) == _phase_rows(second)


def test_bundle_member_reordering_moves_raw_hash_not_canonical_or_semantics(
    api_program: object,
    assembler_profile: object,
) -> None:
    first_bundle = make_validation_bundle_bytes()
    bundle_value = json.loads(first_bundle)
    second_bundle = json.dumps(
        bundle_value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert first_bundle != second_bundle

    first = validate_artifacts(
        api_program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile, first_bundle),
    )
    second = validate_artifacts(
        api_program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile, second_bundle),
    )

    assert type(first) is PublishedValidationReport
    assert type(second) is PublishedValidationReport
    first_identity = _artifact_identity(first)
    second_identity = _artifact_identity(second)
    assert _text(first_identity["validation_bundle_input_payload_sha256"]) != _text(
        second_identity["validation_bundle_input_payload_sha256"]
    )
    assert _text(first_identity["validation_bundle_fingerprint"]) == _text(
        second_identity["validation_bundle_fingerprint"]
    )
    assert _text(first_identity["recipe_value_fingerprint"]) == _text(
        second_identity["recipe_value_fingerprint"]
    )
    assert _phase_rows(first) == _phase_rows(second)


def test_public_entrypoint_signature_and_exports_exclude_private_authority() -> None:
    signature = inspect.signature(validate_artifacts)

    assert tuple(signature.parameters) == (
        "program",
        "raw_recipe_bytes",
        "trusted_validation_bundle",
    )
    assert "raw_validation_bundle_bytes" not in signature.parameters
    assert {"ValidationResult", "validate_artifacts"}.issubset(
        validation_kernel.__all__
    )
    assert {
        "_AuditedValidationOutcome",
        "_ValidationExecutionAudit",
        "_ValidationProgramBuilder",
        "_BUNDLE_CONSTRUCTION_SENTINEL",
        "_PROFILE_CONSTRUCTION_SENTINEL",
        "_validate_artifacts_with_audit",
        "BudgetLedger",
        "SealMeter",
    }.isdisjoint(validation_kernel.__all__)


def test_public_wrapper_returns_the_private_outcomes_exact_public_object(
    api_program: object,
    assembler_profile: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = api_module._validate_artifacts_with_audit(
        api_program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )
    calls = 0

    def audited_stub(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return outcome

    monkeypatch.setattr(api_module, "_validate_artifacts_with_audit", audited_stub)

    result = validate_artifacts(api_program, b"ignored", object())  # type: ignore[arg-type]

    assert result is outcome.public_result
    assert calls == 1
    assert not hasattr(result, "schema_evaluation_receipts")
    assert not hasattr(result, "audit")


def test_private_audit_is_ordered_immutable_nonserializable_and_nonforgeable(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_phase_engine_contribution(alpha_scenario="schema_audit_order")
    )

    outcome = api_module._validate_artifacts_with_audit(
        program,
        b'{"nested":{"value":1},"larger":[1,2,3]}',
        _carrier(assembler_profile),
    )

    assert type(outcome.public_result) is PublishedValidationReport
    audit = outcome.audit
    assert type(audit) is api_module._ValidationExecutionAudit
    assert audit.program_id == program.program_id
    assert audit.program_fingerprint == program.program_fingerprint
    assert len(audit.schema_evaluation_receipts) == 3
    assert all(
        type(receipt) is SchemaEvaluationReceipt
        for receipt in audit.schema_evaluation_receipts
    )
    first, second, report = audit.schema_evaluation_receipts
    assert first.reservation.attempted_shape_units is not None
    assert second.reservation.attempted_shape_units is not None
    assert (
        first.reservation.attempted_shape_units
        < second.reservation.attempted_shape_units
    )
    assert first.reservation.aggregate_after == second.reservation.aggregate_before
    assert second.reservation.aggregate_after == report.reservation.aggregate_before
    assert report.reservation.accepted is True
    assert report.evaluator_invoked is True
    assert report.evaluation_passed is True
    assert report.failure_code is None
    assert api_module._is_validation_execution_audit(audit, program) is True

    with pytest.raises(AttributeError):
        audit.program_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        api_module._ValidationExecutionAudit()
    for operation in (
        lambda: copy.copy(audit),
        lambda: copy.deepcopy(audit),
        lambda: pickle.loads(pickle.dumps(audit)),
        audit.__reduce__,
        lambda: audit.__reduce_ex__(pickle.HIGHEST_PROTOCOL),
    ):
        with pytest.raises(TypeError):
            operation()

    copied_fields = SimpleNamespace(
        program_id=audit.program_id,
        program_fingerprint=audit.program_fingerprint,
        schema_evaluation_receipts=audit.schema_evaluation_receipts,
    )
    report_json = json.loads(outcome.public_result.canonical_bytes)

    class AuditLookalike:
        program_id = audit.program_id
        program_fingerprint = audit.program_fingerprint
        schema_evaluation_receipts = audit.schema_evaluation_receipts

    for forged in (
        audit.schema_evaluation_receipts,
        copied_fields,
        report_json,
        AuditLookalike(),
    ):
        assert api_module._is_validation_execution_audit(forged, program) is False


def test_private_audit_records_rejected_final_report_reservation(
    assembler_profile: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = compose_and_seal_program(make_phase_engine_contribution())
    real_seal = api_module._seal_validation_report_with_audit

    def exhaust_schema_budget(context: object, phase_results: object) -> object:
        for _ in range(4):
            reservation = context.ledger.reserve_schema_shape(  # type: ignore[attr-defined]
                schema_nodes=1,
                instance_nodes=4_000_000,
                per_evaluation_limit=4_000_000,
            )
            assert reservation.accepted is True
        return real_seal(context, phase_results)

    monkeypatch.setattr(
        api_module,
        "_seal_validation_report_with_audit",
        exhaust_schema_budget,
    )

    outcome = api_module._validate_artifacts_with_audit(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(outcome.public_result, BudgetExceededFailure)
    assert outcome.public_result.artifact_role == "report_seal"
    assert len(outcome.audit.schema_evaluation_receipts) == 1
    receipt = outcome.audit.schema_evaluation_receipts[0]
    assert receipt.reservation.accepted is False
    assert receipt.reservation.aggregate_before == 16_000_000
    assert receipt.reservation.aggregate_after is None
    assert receipt.evaluator_invoked is False
    assert receipt.evaluation_passed is None
    assert receipt.failure_code == "invocation_shape_limit_exceeded"


def test_private_audit_records_final_report_schema_failure(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_phase_engine_contribution(report_schema_probe="const")
    )

    outcome = api_module._validate_artifacts_with_audit(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(outcome.public_result, ValidationControlFailure)
    assert outcome.public_result.code == "validation_constructability_failed"
    assert len(outcome.audit.schema_evaluation_receipts) == 1
    receipt = outcome.audit.schema_evaluation_receipts[0]
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is False
    assert receipt.failure_code == "instance_schema_failed"


def test_private_audit_records_final_report_evaluator_failure(
    assembler_profile: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = compose_and_seal_program(make_phase_engine_contribution())
    schema_profile = importlib.import_module("rook.validation_kernel.schema_profile")
    real_seal = api_module._seal_validation_report_with_audit

    class BrokenValidator:
        def iter_errors(self, _: object) -> object:
            raise RuntimeError("synthetic final evaluator failure")

    def break_final_evaluator(context: object, phase_results: object) -> object:
        monkeypatch.setattr(
            schema_profile,
            "_validator_for",
            lambda _: BrokenValidator(),
        )
        return real_seal(context, phase_results)

    monkeypatch.setattr(
        api_module,
        "_seal_validation_report_with_audit",
        break_final_evaluator,
    )

    outcome = api_module._validate_artifacts_with_audit(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(outcome.public_result, ValidationControlFailure)
    assert outcome.public_result.code == "validator_integrity_failure"
    assert len(outcome.audit.schema_evaluation_receipts) == 1
    receipt = outcome.audit.schema_evaluation_receipts[0]
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is None
    assert receipt.failure_code == "schema_evaluator_failed"


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    (
        ("schema_then_integrity_failure", "validator_integrity_failure"),
        ("schema_then_budget_failure", "validation_budget_exceeded"),
        ("schema_then_internal_failure", "validator_internal_failure"),
    ),
)
def test_private_audit_retains_phase_receipts_on_later_control_failure(
    assembler_profile: object,
    scenario: str,
    expected_code: str,
) -> None:
    program = compose_and_seal_program(
        make_phase_engine_contribution(alpha_scenario=scenario)
    )

    outcome = api_module._validate_artifacts_with_audit(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(outcome.public_result, ValidationControlFailure)
    assert outcome.public_result.code == expected_code
    assert len(outcome.audit.schema_evaluation_receipts) == 1
    receipt = outcome.audit.schema_evaluation_receipts[0]
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is False
    assert receipt.failure_code == "instance_schema_failed"


def test_private_pre_attempt_failure_has_empty_audit_and_public_path_has_none(
    assembler_profile: object,
) -> None:
    outcome = api_module._validate_artifacts_with_audit(
        object(),  # type: ignore[arg-type]
        b"unread",
        object(),  # type: ignore[arg-type]
    )
    program = compose_and_seal_program(
        make_phase_engine_contribution(
            alpha_scenario="schema_then_integrity_failure"
        )
    )

    public_result = validate_artifacts(
        program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert isinstance(outcome.public_result, ValidationControlFailure)
    assert outcome.audit.schema_evaluation_receipts == ()
    assert isinstance(public_result, ValidationControlFailure)
    assert not hasattr(public_result, "schema_evaluation_receipts")
    assert not hasattr(public_result, "audit")


def test_orchestration_parses_each_artifact_once_without_fallback(
    api_program: object,
    assembler_profile: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_module = importlib.import_module("rook.validation_kernel.invocation")
    real_parse = invocation_module.parse_owned_json
    parsed_roles: list[str] = []

    def parse_spy(*args: object, **kwargs: object) -> object:
        parsed_roles.append(kwargs["artifact_role"])
        return real_parse(*args, **kwargs)

    monkeypatch.setattr(invocation_module, "parse_owned_json", parse_spy)

    result = validate_artifacts(
        api_program,
        b'{"nested":{"value":1}}',
        _carrier(assembler_profile),
    )

    assert type(result) is PublishedValidationReport
    assert parsed_roles == ["validation_bundle", "recipe"]
