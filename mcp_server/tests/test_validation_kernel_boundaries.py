from __future__ import annotations

import ast
import dataclasses
import importlib
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import rook.validation_kernel as validation_kernel
import pytest
from rook.validation_kernel import (
    CORE_SCHEMA_PROFILE_ID,
    PAYLOAD_SCHEMA_PROFILE_ID,
    PublishedValidationReport,
    TrustedConformanceGateResult,
    run_conformance_gate,
    validate_artifacts,
)
from rook.validation_kernel.budget import BudgetLedger, SealMeter
from rook.validation_kernel.canonical_json import canonical_fingerprint
from rook.validation_kernel.owned_json import own_trusted_json

from tests._validation_kernel_fakes import (
    SyntheticPhaseIndex,
    alternate_conformance_gate,
    make_boundary_campaign_fixture,
    make_validation_bundle_bytes,
)


api_module = importlib.import_module("rook.validation_kernel.api")


_KERNEL_SOURCE = Path(validation_kernel.__file__).parent
_FORBIDDEN_PRODUCTION_TERMS = (
    "rook.agent",
    "server.py",
    "bridge.py",
    "PlannerWorkerContractRequest",
    "RookWorkflowContract",
    "TaskSpec",
    "gh_edit",
    "Rhino",
    "Grasshopper",
    "Ollama",
    "worker model",
    "radial",
    "box array",
    "grid spacing",
)
_REVIEWED_PUBLIC_SURFACE = frozenset(
    {
        "AdmittedSchema",
        "BudgetExceededFailure",
        "BudgetManifest",
        "BudgetReceipt",
        "BudgetSnapshot",
        "CONFORMANCE_CAMPAIGN_SCHEMA",
        "CONFORMANCE_CAMPAIGN_SCHEMA_FINGERPRINT",
        "CONFORMANCE_CAMPAIGN_SCHEMA_ID",
        "CONFORMANCE_COMPLETENESS_SCHEMA",
        "CONFORMANCE_COMPLETENESS_SCHEMA_FINGERPRINT",
        "CONFORMANCE_COMPLETENESS_SCHEMA_ID",
        "CONFORMANCE_FIXTURE_SCHEMA",
        "CONFORMANCE_FIXTURE_SCHEMA_FINGERPRINT",
        "CONFORMANCE_FIXTURE_SCHEMA_ID",
        "CONFORMANCE_GATE_PROFILE_SCHEMA",
        "CONFORMANCE_GATE_PROFILE_SCHEMA_FINGERPRINT",
        "CONFORMANCE_GATE_PROFILE_SCHEMA_ID",
        "CONFORMANCE_REPORT_SCHEMA",
        "CONFORMANCE_REPORT_SCHEMA_FINGERPRINT",
        "CONFORMANCE_REPORT_SCHEMA_ID",
        "CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA",
        "CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_FINGERPRINT",
        "CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_ID",
        "CORE_PROFILE",
        "CORE_SCHEMA_PROFILE_ID",
        "ConformanceGateInvocationFailure",
        "ExportTypeSpec",
        "FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT",
        "ImmutableCallableRecord",
        "ImplementationSource",
        "InputBinding",
        "InstanceBinding",
        "InvocationInputSpec",
        "IssueSpec",
        "JsonParseError",
        "JsonParseEvidence",
        "KERNEL_CONTROL_CODES",
        "KERNEL_OWNED_REPORT_PATHS",
        "KERNEL_REPORT_FIELD_ROLES",
        "KernelIssue",
        "LM9A_BUDGET_MANIFEST",
        "LM9A_BUDGET_PROFILE_ID",
        "NamedOutput",
        "PAYLOAD_PROFILE",
        "PAYLOAD_SCHEMA_PROFILE_ID",
        "PROGRAM_MANIFEST_SCHEMA",
        "PROGRAM_MANIFEST_SCHEMA_FINGERPRINT",
        "PROGRAM_MANIFEST_SCHEMA_ID",
        "ParsedJsonValue",
        "ParserProfileSpec",
        "PhaseResult",
        "PhaseSpec",
        "ProgramCompositionError",
        "ProgramConstantSpec",
        "ProvidedOutput",
        "PublishedValidationReport",
        "REPORT_BUDGET_RECEIPT_PATH",
        "REPORT_FINGERPRINT_PATH",
        "ReportBuilder",
        "ReportProjectionEnvelope",
        "ReportProjectionSpec",
        "RunnerResult",
        "RuntimeBinding",
        "RuntimeComponentSpec",
        "RuntimeDependencySpec",
        "SchemaAdmissionError",
        "SchemaEvaluationInputError",
        "SchemaEvaluationReceipt",
        "SchemaEvaluationReservation",
        "SchemaEvaluatorSpec",
        "SchemaIssue",
        "SchemaProfile",
        "SealedConformanceGateProfile",
        "SealedTrustedBundleAssemblerProfile",
        "SealedValidationProgram",
        "TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA",
        "TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_FINGERPRINT",
        "TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID",
        "TrustedConformanceFixtureContext",
        "TrustedConformanceGateResult",
        "TrustedImmutableArtifactStore",
        "TrustedValidationBundleInput",
        "ValidationControlFailure",
        "ValidationInvocation",
        "ValidationProgramContribution",
        "ValidationResult",
        "admit_schema",
        "compose_and_seal_program",
        "evaluate_schema",
        "evaluate_schema_with_reservation",
        "execute_phase_program",
        "implementation_source_closure_for_modules",
        "implementation_source_for_module",
        "issue_trusted_validation_bundle",
        "parse_owned_json",
        "reserve_schema_evaluation",
        "run_conformance_gate",
        "runtime_dependency_closure_for_modules",
        "runtime_dependency_spec",
        "runtime_implementation_fingerprint",
        "seal_conformance_gate_profile",
        "seal_trusted_bundle_assembler_profile",
        "seal_validation_report",
        "validate_artifacts",
    }
)
_PRIVATE_AUDIT_MEMBER_NAMES = frozenset(
    {
        "_ValidationExecutionAudit",
        "audit",
        "schema_evaluation_attempts",
        "schema_evaluation_receipts",
    }
)


def _python_sources() -> tuple[Path, ...]:
    return tuple(sorted(_KERNEL_SOURCE.glob("*.py")))


def _imports(path: Path) -> tuple[tuple[int, str], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            found.append((node.lineno, module))
    return tuple(found)


def _declared_type_members(exported_type: type[object]) -> set[str]:
    members = set(vars(exported_type))
    members.update(getattr(exported_type, "__annotations__", ()))
    slots = getattr(exported_type, "__slots__", ())
    members.update((slots,) if type(slots) is str else slots)
    if dataclasses.is_dataclass(exported_type):
        members.update(field.name for field in dataclasses.fields(exported_type))
    return members


def _assert_public_type_has_no_audit_capability(
    export_name: str,
    exported_type: type[object],
) -> None:
    members = _declared_type_members(exported_type)
    assert _PRIVATE_AUDIT_MEMBER_NAMES.isdisjoint(members), export_name
    assert all("audit" not in member.lower() for member in members), export_name


def _assert_public_terminal_has_no_audit_capability(value: object) -> None:
    assert isinstance(
        value,
        (PublishedValidationReport, validation_kernel.ValidationControlFailure),
    )
    members = set(dir(value))
    members.update(field.name for field in dataclasses.fields(value))
    assert _PRIVATE_AUDIT_MEMBER_NAMES.isdisjoint(members)
    for member in _PRIVATE_AUDIT_MEMBER_NAMES:
        assert not hasattr(value, member)


def _assert_report_json_has_no_audit_capability(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            keys = set(current)
            assert _PRIVATE_AUDIT_MEMBER_NAMES.isdisjoint(keys)
            assert all("audit" not in key.lower() for key in keys)
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)


def test_production_kernel_has_no_host_or_domain_coupling() -> None:
    sources = _python_sources()
    assert sources
    for path in sources:
        source = path.read_text(encoding="utf-8")
        for forbidden in _FORBIDDEN_PRODUCTION_TERMS:
            assert forbidden not in source, f"{path.name} mentions {forbidden!r}"

    imported_modules = {
        module
        for path in sources
        for _, module in _imports(path)
    }
    assert all(not module.startswith("rook.agent") for module in imported_modules)


def test_parser_and_canonicalizer_keep_their_independent_boundaries() -> None:
    parser_path = _KERNEL_SOURCE / "parser.py"
    parser_source = parser_path.read_text(encoding="utf-8")
    parser_imports = _imports(parser_path)
    assert all(module != "json" for _, module in parser_imports)
    assert "json.loads" not in parser_source
    assert "JSONDecoder" not in parser_source

    canonical_path = _KERNEL_SOURCE / "canonical_json.py"
    canonical_imports = _imports(canonical_path)
    assert canonical_imports == (
        (3, "__future__"),
        (5, "hashlib"),
        (6, "typing"),
        (8, ".owned_json"),
    )


def test_package_exports_are_exactly_the_reviewed_public_surface() -> None:
    assert type(validation_kernel.__all__) is tuple
    assert len(validation_kernel.__all__) == len(set(validation_kernel.__all__))
    assert frozenset(validation_kernel.__all__) == _REVIEWED_PUBLIC_SURFACE
    for name in validation_kernel.__all__:
        assert not name.startswith("_")
        assert getattr(validation_kernel, name) is not None


def test_public_surface_cannot_retrieve_private_kernel_authority() -> None:
    forbidden = {
        "_AUDIT_ISSUER_CAPABILITY",
        "_BUNDLE_CONSTRUCTION_SENTINEL",
        "_FIXTURE_CONTEXT_ISSUER",
        "_GATE_PROFILE_ISSUER",
        "_GATE_RESULT_ISSUER",
        "_ObjectFrame",
        "_ArrayFrame",
        "_PROFILE_CONSTRUCTION_SENTINEL",
        "_SCHEMA_AUDIT_ISSUER_CAPABILITY",
        "_ValidationExecutionAudit",
        "_ValidationProgramBuilder",
        "BudgetLedger",
        "RUNTIME_REGISTRY",
        "SealMeter",
        "_runtime_bindings",
    }
    assert forbidden.isdisjoint(validation_kernel.__all__)
    for name in forbidden:
        with pytest.raises(AttributeError):
            getattr(validation_kernel, name)

    for capability_type, expected_message in (
        (
            validation_kernel.AdmittedSchema,
            "AdmittedSchema values are created only by admit_schema",
        ),
        (
            validation_kernel.SchemaEvaluationReservation,
            "SchemaEvaluationReservation values are created only by "
            "reserve_schema_evaluation",
        ),
        (
            validation_kernel.ReportBuilder,
            "ReportBuilder values are issued only by the report seal",
        ),
        (
            validation_kernel.SealedValidationProgram,
            "SealedValidationProgram values are created only by "
            "compose_and_seal_program",
        ),
        (
            validation_kernel.SealedTrustedBundleAssemblerProfile,
            "SealedTrustedBundleAssemblerProfile values are created only by "
            "the fixed seal",
        ),
        (
            validation_kernel.SealedConformanceGateProfile,
            "conformance gate profiles are created only by the fixed seal",
        ),
        (
            validation_kernel.TrustedConformanceFixtureContext,
            "conformance fixture contexts are release-issued",
        ),
        (
            validation_kernel.TrustedConformanceGateResult,
            "conformance gate results are gate-issued",
        ),
        (
            validation_kernel.TrustedValidationBundleInput,
            "TrustedValidationBundleInput values are created only by trusted "
            "issuance",
        ),
    ):
        with pytest.raises(TypeError) as denied:
            capability_type()
        assert str(denied.value) == expected_message


def test_real_public_terminal_shapes_have_no_audit_capability() -> None:
    fingerprint = "sha256:" + "1" * 64
    report = PublishedValidationReport(
        schema_id="synthetic.report:v1",
        report_fingerprint=fingerprint,
        canonical_bytes=b"{}",
        value=own_trusted_json({}),
    )
    failure = validation_kernel.ValidationControlFailure(
        failure_stage="validation",
        code="validator_integrity_failure",
        artifact_role="phase_engine",
        program_id="synthetic.validation_program:v1",
        program_fingerprint=fingerprint,
        subject_path="/synthetic",
        message="Validator integrity check failed.",
        detail_sha256=None,
    )
    assert {field.name for field in dataclasses.fields(report)} == {
        "schema_id",
        "report_fingerprint",
        "canonical_bytes",
        "value",
    }
    assert {field.name for field in dataclasses.fields(failure)} == {
        "failure_stage",
        "code",
        "artifact_role",
        "program_id",
        "program_fingerprint",
        "subject_path",
        "message",
        "detail_sha256",
    }
    _assert_public_terminal_has_no_audit_capability(report)
    _assert_public_terminal_has_no_audit_capability(failure)

    fixture = make_boundary_campaign_fixture()
    outcomes = tuple(
        validate_artifacts(
            fixture.program,
            case.recipe_bytes,
            fixture.trusted_bundle,
        )
        for case in _boundary_cases()
    )
    assert any(type(outcome) is PublishedValidationReport for outcome in outcomes)
    assert any(
        isinstance(outcome, validation_kernel.ValidationControlFailure)
        for outcome in outcomes
    )
    for outcome in outcomes:
        _assert_public_terminal_has_no_audit_capability(outcome)
        if type(outcome) is PublishedValidationReport:
            _assert_report_json_has_no_audit_capability(
                json.loads(outcome.canonical_bytes)
            )


def test_every_public_exported_type_excludes_private_audit_capability() -> None:
    exported_types = {
        name: getattr(validation_kernel, name)
        for name in validation_kernel.__all__
        if isinstance(getattr(validation_kernel, name), type)
    }
    assert exported_types
    assert "_ValidationExecutionAudit" not in exported_types
    for name, exported_type in exported_types.items():
        _assert_public_type_has_no_audit_capability(name, exported_type)


def test_complete_synthetic_campaign_replays_byte_for_byte() -> None:
    first = make_boundary_campaign_fixture()
    second = make_boundary_campaign_fixture()

    phases = {phase.phase_name: phase for phase in first.program.phases}
    beta_binding = phases["beta"].input_bindings[0]
    assert (
        beta_binding.source_kind,
        beta_binding.source_phase,
        beta_binding.source_output,
    ) == ("phase_output", "alpha", "alpha_value")
    assert phases["audit"].ordering_after == ("alpha",)
    assert all(
        binding.source_kind != "phase_output"
        for binding in phases["audit"].input_bindings
    )
    required_for_compile = frozenset(
        first.program.report_projection.required_for_compile_phases
    )
    assert {"alpha", "beta"}.issubset(required_for_compile)
    assert "audit" not in required_for_compile
    assert {schema.profile_id for schema in first.program.schemas} == {
        CORE_SCHEMA_PROFILE_ID,
        PAYLOAD_SCHEMA_PROFILE_ID,
    }
    program_manifest = json.loads(first.program.manifest_bytes)
    assert {
        (issue["code"], issue["classification"])
        for issue in program_manifest["issue_vocabulary"]
    } == {
        ("synthetic_error", "diagnostic"),
        ("synthetic_blocker", "compile_blocker"),
    }
    assert "synthetic.alpha:v1" in {
        export["export_type"] for export in program_manifest["export_types"]
    }
    immutable_export = SyntheticPhaseIndex(
        "boundary-index",
        own_trusted_json({"value": "ok"}),
        ("/value",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        immutable_export.identity = "changed"  # type: ignore[misc]
    assert first.program.report_projection.projection_id == (
        "synthetic.report_projection:v1"
    )

    first_validation = validate_artifacts(
        first.program,
        first.recipe_bytes,
        first.trusted_bundle,
    )
    second_validation = validate_artifacts(
        second.program,
        second.recipe_bytes,
        second.trusted_bundle,
    )
    assert type(first_validation) is PublishedValidationReport
    assert type(second_validation) is PublishedValidationReport

    first_campaign = run_conformance_gate(
        first.gate_profile,
        first.program,
        first.campaign_bytes,
        first.fixture_context,
    )
    second_campaign = run_conformance_gate(
        second.gate_profile,
        second.program,
        second.campaign_bytes,
        second.fixture_context,
    )
    assert type(first_campaign) is TrustedConformanceGateResult
    assert type(second_campaign) is TrustedConformanceGateResult

    assert first.program.manifest_bytes == second.program.manifest_bytes
    assert first.program.program_fingerprint == second.program.program_fingerprint
    assert first_validation.canonical_bytes == second_validation.canonical_bytes
    assert first_validation.report_fingerprint == second_validation.report_fingerprint
    assert first.campaign_bytes == second.campaign_bytes
    assert first.campaign_fingerprint == second.campaign_fingerprint
    assert first_campaign.report_bytes == second_campaign.report_bytes
    assert first_campaign.report_fingerprint == second_campaign.report_fingerprint
    assert first_campaign.decision == second_campaign.decision == "passed"

    report = json.loads(first_campaign.report_bytes)
    assert {row["case_kind"] for row in report["result_rows"]} == {
        "core_schema_positive",
        "semantic_fixture",
    }


def _integration_identities(fixture: object) -> dict[str, bytes | str]:
    validation = validate_artifacts(
        fixture.program,
        fixture.recipe_bytes,
        fixture.trusted_bundle,
    )
    campaign = run_conformance_gate(
        fixture.gate_profile,
        fixture.program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    assert type(validation) is PublishedValidationReport
    assert type(campaign) is TrustedConformanceGateResult
    return {
        "program_bytes": fixture.program.manifest_bytes,
        "program_fingerprint": fixture.program.program_fingerprint,
        "validation_bytes": validation.canonical_bytes,
        "validation_fingerprint": validation.report_fingerprint,
        "campaign_bytes": fixture.campaign_bytes,
        "campaign_fingerprint": fixture.campaign_fingerprint,
        "campaign_report_bytes": campaign.report_bytes,
        "campaign_report_fingerprint": campaign.report_fingerprint,
    }


@pytest.mark.parametrize(
    ("mutation", "changed_groups"),
    (
        (
            {"recipe_bytes": b'{"case_id":"boundary.failed.changed","value":"ok"}'},
            frozenset({"validation", "campaign", "campaign_report"}),
        ),
        (
            {
                "bundle_bytes": make_validation_bundle_bytes(
                    task_session_id="synthetic.changed_session:v1"
                )
            },
            frozenset({"validation", "campaign", "campaign_report"}),
        ),
        (
            {"alpha_scenario": "warning_information"},
            frozenset(
                {"program", "validation", "campaign", "campaign_report"}
            ),
        ),
        (
            {"core_bytes": b'{"value":"changed"}'},
            frozenset({"campaign", "campaign_report"}),
        ),
        (
            {"assembler_implementation_fingerprint": "sha256:" + "2" * 64},
            frozenset({"campaign", "campaign_report"}),
        ),
        (
            {"gate_callable": alternate_conformance_gate},
            frozenset({"campaign", "campaign_report"}),
        ),
    ),
    ids=("recipe", "bundle", "program", "core", "assembler", "gate"),
)
def test_each_behavior_bearing_boundary_moves_only_downstream_identity(
    mutation: dict[str, object],
    changed_groups: frozenset[str],
) -> None:
    baseline = _integration_identities(make_boundary_campaign_fixture())
    changed = _integration_identities(make_boundary_campaign_fixture(**mutation))

    for group in ("program", "validation", "campaign", "campaign_report"):
        keys = (f"{group}_bytes", f"{group}_fingerprint")
        if group in changed_groups:
            assert all(changed[key] != baseline[key] for key in keys)
        else:
            assert all(changed[key] == baseline[key] for key in keys)


@dataclass(frozen=True, slots=True)
class _BoundaryCase:
    case_id: str
    recipe_bytes: bytes


def _case_recipe(case_id: str, item_count: int) -> bytes:
    items = ",".join(str(index) for index in range(item_count))
    return (
        f'{{"case_id":"{case_id}","value":"ok","items":[{items}]}}'
    ).encode("ascii")


def _boundary_cases() -> tuple[_BoundaryCase, ...]:
    return (
        _BoundaryCase("boundary.success.0", _case_recipe("boundary.success.0", 0)),
        _BoundaryCase("boundary.success.1", _case_recipe("boundary.success.1", 1)),
        _BoundaryCase("boundary.success.2", _case_recipe("boundary.success.2", 2)),
        _BoundaryCase("boundary.blocked.0", _case_recipe("boundary.blocked.0", 3)),
        _BoundaryCase("boundary.blocked.1", _case_recipe("boundary.blocked.1", 4)),
        _BoundaryCase("boundary.failed.0", _case_recipe("boundary.failed.0", 5)),
        _BoundaryCase(
            "boundary.parse.0",
            b'{"case_id":"boundary.parse.0","branch":{"value":',
        ),
        _BoundaryCase(
            "boundary.budget.0",
            b'{"case_id":"boundary.budget.0","padding":"'
            + (b"x" * 1_048_576)
            + b'"}',
        ),
    )


def _failure_fields(result: object) -> tuple[tuple[str, object], ...]:
    if not dataclasses.is_dataclass(result):
        return ()
    return tuple(
        (field.name, getattr(result, field.name))
        for field in dataclasses.fields(result)
    )


def _public_snapshot(result: object) -> dict[str, object]:
    if type(result) is PublishedValidationReport:
        report = json.loads(result.canonical_bytes)
        identity = report["artifact_identity"]
        return {
            "terminal": type(result).__name__,
            "raw_input_hashes": (
                identity["recipe_input_payload_sha256"],
                identity["validation_bundle_input_payload_sha256"],
                identity["recipe_value_fingerprint"],
                identity["validation_bundle_fingerprint"],
            ),
            "budget_receipt": report["validation_budget"],
            "budget_counters": report["validation_budget"]["observed"],
            "phase_rows": tuple(report["phases"]),
            "report_present": True,
            "report_bytes": result.canonical_bytes,
            "report_fingerprint": result.report_fingerprint,
            "failure_fields": (),
        }
    return {
        "terminal": type(result).__name__,
        "raw_input_hashes": None,
        "budget_receipt": None,
        "budget_counters": None,
        "phase_rows": None,
        "report_present": False,
        "report_bytes": None,
        "report_fingerprint": None,
        "failure_fields": _failure_fields(result),
    }


def _receipt_row(receipt: object) -> tuple[object, ...]:
    reservation = receipt.reservation
    return (
        reservation.accepted,
        reservation.attempted_shape_units,
        reservation.aggregate_before,
        reservation.aggregate_after,
        reservation.rejection_reason,
        receipt.evaluator_invoked,
        receipt.evaluation_passed,
        tuple(
            (
                issue.code,
                issue.instance_path,
                issue.schema_path,
                issue.detail_sha256,
            )
            for issue in receipt.bounded_errors
        ),
        receipt.failure_code,
    )


def _attempt_row(attempt: object) -> tuple[object, ...]:
    binding = attempt.instance_binding
    candidate = attempt.pre_evaluation_candidate
    return (
        attempt.schema_id,
        attempt.schema_fingerprint,
        attempt.schema_nodes,
        attempt.per_evaluation_limit,
        (
            binding.artifact_id,
            binding.artifact_fingerprint,
            binding.instance_pointer,
        ),
        attempt.instance_fingerprint,
        attempt.instance_nodes,
        (
            None
            if candidate is None
            else (
                candidate.candidate_kind,
                candidate.candidate_fingerprint,
                candidate.projected_instance_nodes,
            )
        ),
        _receipt_row(attempt.receipt),
    )


def _audit_snapshot(audit: object) -> dict[str, object]:
    attempts = audit.schema_evaluation_attempts
    receipts = audit.schema_evaluation_receipts
    assert len(attempts) == len(receipts)
    assert all(
        attempt.receipt is receipt
        for attempt, receipt in zip(attempts, receipts, strict=True)
    )
    return {
        "program_id": audit.program_id,
        "program_fingerprint": audit.program_fingerprint,
        "attempt_rows": tuple(_attempt_row(attempt) for attempt in attempts),
        "adapter_invocation_order": tuple(
            _receipt_row(receipt) for receipt in receipts
        ),
    }


def _persistent_synchronized_campaign(
    cases: tuple[_BoundaryCase, ...],
    invoke: object,
) -> dict[str, tuple[object, ...]]:
    assert len(cases) == 8
    assert len({case.case_id for case in cases}) == 8
    barrier = threading.Barrier(8)

    def worker(case: _BoundaryCase) -> tuple[object, ...]:
        outcomes: list[object] = []
        for _ in range(10):
            barrier.wait()
            outcomes.append(invoke(case))  # type: ignore[operator]
        return tuple(outcomes)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = tuple(executor.submit(worker, case) for case in cases)
        return {
            case.case_id: future.result()
            for case, future in zip(cases, futures, strict=True)
        }


def _assert_public_case_isolation(
    snapshots: dict[str, dict[str, object]],
) -> None:
    assert len(snapshots) == 8
    identities = {
        case_id: _public_case_identity(snapshot)
        for case_id, snapshot in snapshots.items()
    }
    assert len(set(identities.values())) == 8

    report_ids = {
        case_id
        for case_id, snapshot in snapshots.items()
        if snapshot["report_present"]
    }
    failure_ids = set(snapshots) - report_ids
    assert len(report_ids) == 6
    assert len(failure_ids) == 2

    for case_id in report_ids:
        snapshot = snapshots[case_id]
        raw_hashes = snapshot["raw_input_hashes"]
        counters = snapshot["budget_counters"]
        report_fingerprint = snapshot["report_fingerprint"]
        assert type(raw_hashes) is tuple and len(raw_hashes) == 4
        assert type(counters) is dict
        assert type(report_fingerprint) is str
        own_scalars = _public_structured_scalars(snapshot)
        subject_tokens = (raw_hashes[0], raw_hashes[2], report_fingerprint)
        assert all(token in own_scalars for token in subject_tokens)

        for other_id, other in snapshots.items():
            if other_id == case_id:
                continue
            other_scalars = _public_structured_scalars(other)
            assert all(token not in other_scalars for token in subject_tokens)
            assert counters != other["budget_counters"]
            assert report_fingerprint != other["report_fingerprint"]

    failure_codes: set[object] = set()
    for case_id in failure_ids:
        snapshot = snapshots[case_id]
        fields = dict(snapshot["failure_fields"])
        subject = (fields["artifact_role"], fields["subject_path"])
        code = fields["code"]
        failure_codes.add(code)
        own_scalars = _public_structured_scalars(snapshot)
        assert fields["artifact_role"] in own_scalars
        assert code in own_scalars
        if fields["subject_path"] is not None:
            assert fields["subject_path"] in own_scalars

        for other_id, other in snapshots.items():
            if other_id == case_id:
                continue
            other_scalars = _public_structured_scalars(other)
            assert code not in other_scalars
            if other["report_present"]:
                assert fields["artifact_role"] not in other_scalars
                if fields["subject_path"] is not None:
                    assert fields["subject_path"] not in other_scalars
                continue
            other_fields = dict(other["failure_fields"])
            assert subject != (
                other_fields["artifact_role"],
                other_fields["subject_path"],
            )
            assert fields["artifact_role"] != other_fields["artifact_role"]
            assert fields["subject_path"] != other_fields["subject_path"]

    assert failure_codes == {
        "validator_integrity_failure",
        "validation_budget_exceeded",
    }


def _json_scalar_values(value: object) -> frozenset[object]:
    scalars: set[object] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
        elif current is None or type(current) in (bool, int, float, str):
            scalars.add(current)
    return frozenset(scalars)


def _public_structured_scalars(snapshot: dict[str, object]) -> frozenset[object]:
    if snapshot["report_present"]:
        report_bytes = snapshot["report_bytes"]
        assert type(report_bytes) is bytes
        return _json_scalar_values(json.loads(report_bytes))
    return frozenset(
        value
        for _, value in snapshot["failure_fields"]
        if value is None or type(value) in (bool, int, float, str)
    )


def _public_case_identity(snapshot: dict[str, object]) -> tuple[object, ...]:
    if snapshot["report_present"]:
        raw_hashes = snapshot["raw_input_hashes"]
        counters = snapshot["budget_counters"]
        assert type(raw_hashes) is tuple and len(raw_hashes) == 4
        assert type(counters) is dict
        return (
            "report",
            raw_hashes[0],
            raw_hashes[2],
            tuple(sorted(counters.items())),
            snapshot["report_fingerprint"],
        )
    fields = dict(snapshot["failure_fields"])
    return (
        "failure",
        fields["artifact_role"],
        fields["subject_path"],
        fields["code"],
        fields["detail_sha256"],
        fields.get("budget_dimension"),
        fields.get("observed_lower_bound"),
    )


def _audit_binding_rows(snapshot: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    attempt_rows = snapshot["attempt_rows"]
    assert type(attempt_rows) is tuple
    return tuple(attempt[4] for attempt in attempt_rows)


def _assert_private_case_isolation(
    cases: tuple[_BoundaryCase, ...],
    public_snapshots: dict[str, dict[str, object]],
    audit_snapshots: dict[str, dict[str, object]],
    *,
    expected_program_id: str,
    expected_program_fingerprint: str,
) -> None:
    case_ids = {case.case_id for case in cases}
    assert set(public_snapshots) == case_ids
    assert set(audit_snapshots) == case_ids
    assert all(case_id not in expected_program_id for case_id in case_ids)
    assert all(case_id not in expected_program_fingerprint for case_id in case_ids)

    combined_identities: set[tuple[object, ...]] = set()
    for case in cases:
        public = public_snapshots[case.case_id]
        audit = audit_snapshots[case.case_id]
        attempts = audit["attempt_rows"]
        receipts = audit["adapter_invocation_order"]
        bindings = _audit_binding_rows(audit)
        assert type(attempts) is tuple
        assert type(receipts) is tuple
        assert audit["program_id"] == expected_program_id
        assert audit["program_fingerprint"] == expected_program_fingerprint
        assert len(attempts) == len(receipts)
        assert tuple(attempt[-1] for attempt in attempts) == receipts

        combined_identities.add(
            (
                _public_case_identity(public),
                audit["program_id"],
                audit["program_fingerprint"],
                bindings,
                receipts,
            )
        )

        if not public["report_present"]:
            assert attempts == ()
            assert receipts == ()
            assert bindings == ()
            continue

        raw_hashes = public["raw_input_hashes"]
        report_fingerprint = public["report_fingerprint"]
        assert type(raw_hashes) is tuple and len(raw_hashes) == 4
        assert type(report_fingerprint) is str
        own_artifact_id = f"artifact:{case.case_id}"
        assert own_artifact_id in {binding[0] for binding in bindings}
        assert raw_hashes[2] in {binding[1] for binding in bindings}
        assert report_fingerprint in {binding[1] for binding in bindings}

        for other_id, other in audit_snapshots.items():
            if other_id == case.case_id:
                continue
            other_bindings = _audit_binding_rows(other)
            other_receipts = other["adapter_invocation_order"]
            assert all(binding not in other_bindings for binding in bindings)
            assert all(receipt not in other_receipts for receipt in receipts)
            assert own_artifact_id not in {
                binding[0] for binding in other_bindings
            }
            assert raw_hashes[2] not in {
                binding[1] for binding in other_bindings
            }
            assert report_fingerprint not in {
                binding[1] for binding in other_bindings
            }

    assert len(combined_identities) == 8


def test_public_concurrent_invocations_are_isolated_for_ten_barrier_rounds() -> None:
    fixture = make_boundary_campaign_fixture()
    cases = _boundary_cases()
    serial_results = {
        case.case_id: validate_artifacts(
            fixture.program,
            case.recipe_bytes,
            fixture.trusted_bundle,
        )
        for case in cases
    }
    serial = {
        case_id: _public_snapshot(result)
        for case_id, result in serial_results.items()
    }
    _assert_public_case_isolation(serial)
    for result in serial_results.values():
        _assert_public_terminal_has_no_audit_capability(result)
        if type(result) is PublishedValidationReport:
            _assert_report_json_has_no_audit_capability(
                json.loads(result.canonical_bytes)
            )

    campaign = _persistent_synchronized_campaign(
        cases,
        lambda case: validate_artifacts(
            fixture.program,
            case.recipe_bytes,
            fixture.trusted_bundle,
        ),
    )
    for round_index in range(10):
        for results in campaign.values():
            result = results[round_index]
            _assert_public_terminal_has_no_audit_capability(result)
            if type(result) is PublishedValidationReport:
                _assert_report_json_has_no_audit_capability(
                    json.loads(result.canonical_bytes)
                )
        round_snapshots = {
            case_id: _public_snapshot(results[round_index])
            for case_id, results in campaign.items()
        }
        assert round_snapshots == serial
        _assert_public_case_isolation(round_snapshots)


def test_private_audits_are_isolated_for_ten_barrier_rounds() -> None:
    fixture = make_boundary_campaign_fixture()
    cases = _boundary_cases()
    public_oracles = {
        case.case_id: _public_snapshot(
            validate_artifacts(
                fixture.program,
                case.recipe_bytes,
                fixture.trusted_bundle,
            )
        )
        for case in cases
    }
    private_oracles = {
        case.case_id: api_module._validate_artifacts_with_audit(
            fixture.program,
            case.recipe_bytes,
            fixture.trusted_bundle,
        )
        for case in cases
    }
    audit_oracles = {
        case_id: _audit_snapshot(outcome.audit)
        for case_id, outcome in private_oracles.items()
    }
    assert {
        case_id: _public_snapshot(outcome.public_result)
        for case_id, outcome in private_oracles.items()
    } == public_oracles
    for outcome in private_oracles.values():
        _assert_public_terminal_has_no_audit_capability(outcome.public_result)
        if type(outcome.public_result) is PublishedValidationReport:
            _assert_report_json_has_no_audit_capability(
                json.loads(outcome.public_result.canonical_bytes)
            )
    _assert_public_case_isolation(public_oracles)
    _assert_private_case_isolation(
        cases,
        public_oracles,
        audit_oracles,
        expected_program_id=fixture.program.program_id,
        expected_program_fingerprint=fixture.program.program_fingerprint,
    )

    campaign = _persistent_synchronized_campaign(
        cases,
        lambda case: api_module._validate_artifacts_with_audit(
            fixture.program,
            case.recipe_bytes,
            fixture.trusted_bundle,
        ),
    )
    for round_index in range(10):
        round_public: dict[str, dict[str, object]] = {}
        round_audits: dict[str, dict[str, object]] = {}
        for case_id, outcomes in campaign.items():
            outcome = outcomes[round_index]
            round_public[case_id] = _public_snapshot(outcome.public_result)
            round_audits[case_id] = _audit_snapshot(outcome.audit)
            assert round_public[case_id] == public_oracles[case_id]
            assert round_audits[case_id] == audit_oracles[case_id]
            assert api_module._is_validation_execution_audit(
                outcome.audit, fixture.program
            )
            _assert_public_terminal_has_no_audit_capability(outcome.public_result)
            if type(outcome.public_result) is PublishedValidationReport:
                _assert_report_json_has_no_audit_capability(
                    json.loads(outcome.public_result.canonical_bytes)
                )
        _assert_public_case_isolation(round_public)
        _assert_private_case_isolation(
            cases,
            round_public,
            round_audits,
            expected_program_id=fixture.program.program_id,
            expected_program_fingerprint=fixture.program.program_fingerprint,
        )


def test_fresh_process_replay_is_exact_across_hash_seeds() -> None:
    mcp_root = Path(__file__).resolve().parents[1]
    driver = Path(__file__).with_name("_validation_kernel_replay_driver.py")
    python_path = os.pathsep.join(
        (str(mcp_root / "src"), str(mcp_root))
    )
    inherited = {
        name: os.environ[name]
        for name in ("SYSTEMROOT", "WINDIR")
        if name in os.environ
    }

    outputs: list[bytes] = []
    for seed in ("0", "1", "42", "4294967295", "42"):
        completed = subprocess.run(
            [sys.executable, str(driver)],
            cwd=mcp_root,
            env={
                **inherited,
                "PYTHONHASHSEED": seed,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": python_path,
            },
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0
        assert completed.stderr == b""
        assert completed.stdout.endswith(b"\n")
        assert completed.stdout.count(b"\n") == 1
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1] == outputs[2] == outputs[3] == outputs[4]


def test_fixed_profile_positive_cases_fit_and_bind_shape_to_program() -> None:
    fixture = make_boundary_campaign_fixture()
    result = run_conformance_gate(
        fixture.gate_profile,
        fixture.program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    assert type(result) is TrustedConformanceGateResult
    assert result.decision == "passed"
    report = json.loads(result.report_bytes)

    registered_core_ids = {
        schema.schema_id
        for schema in fixture.program.schemas
        if schema.profile_id == CORE_SCHEMA_PROFILE_ID
    }
    core_rows = [
        row
        for row in report["result_rows"]
        if row["case_kind"] == "core_schema_positive"
    ]
    assert {
        row["schema_evaluations"][0]["schema_id"] for row in core_rows
    } == registered_core_ids
    assert all(row["outcome"] == "passed" for row in core_rows)
    assert all(
        row["schema_evaluations"][0]["evaluation_passed"] is True
        and row["schema_evaluations"][0]["attempted_shape_units"]
        <= row["schema_evaluations"][0]["per_evaluation_limit"]
        for row in core_rows
    )
    assert all(
        row["within_every_per_evaluation_limit"] is True
        and row["aggregate_schema_evaluation_shape_units"] <= 16_000_000
        for row in report["result_rows"]
    )

    observed_shape = sum(
        row["aggregate_schema_evaluation_shape_units"]
        for row in report["result_rows"]
    )
    assert observed_shape > 0
    assert report["program_fingerprint"] == fixture.program.program_fingerprint
    unsigned = {
        key: value
        for key, value in report.items()
        if key != "report_fingerprint"
    }
    assert canonical_fingerprint(own_trusted_json(unsigned)) == result.report_fingerprint
    rebound = {
        **unsigned,
        "program_fingerprint": "sha256:" + "0" * 64,
    }
    assert sum(
        row["aggregate_schema_evaluation_shape_units"]
        for row in rebound["result_rows"]
    ) == observed_shape
    assert canonical_fingerprint(own_trusted_json(rebound)) != result.report_fingerprint


def test_per_evaluation_admission_rejection_fails_the_aggregate_release_decision() -> None:
    large_instance = {"value": "ok"}
    large_instance.update(
        {f"field_{index:04d}": index for index in range(4_000)}
    )
    fixture = make_boundary_campaign_fixture(
        wide_core_schema=True,
        core_bytes=json.dumps(
            large_instance,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii"),
    )

    result = run_conformance_gate(
        fixture.gate_profile,
        fixture.program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    assert type(result) is TrustedConformanceGateResult
    assert result.decision == "failed"
    report = json.loads(result.report_bytes)
    assert report["decision"] == "failed"
    assert report["all_case_outcomes_passed"] is False
    core = next(
        row
        for row in report["result_rows"]
        if row["case_kind"] == "core_schema_positive"
    )
    assert core["outcome"] == "failed"
    assert core["failure_code"] == "validation_budget_exceeded"
    attempt = core["schema_evaluations"][0]
    calculated_shape_units = attempt["schema_nodes"] * attempt["instance_nodes"]
    assert attempt["schema_nodes"] == 2_110
    assert attempt["instance_nodes"] == 4_002
    assert calculated_shape_units == 8_444_220
    assert attempt["per_evaluation_limit"] == 8_000_000
    assert calculated_shape_units > attempt["per_evaluation_limit"]
    assert attempt["attempt_status"] == "reservation_rejected"
    reported_rejection_reason = attempt["failure_code"]
    assert reported_rejection_reason == "per_evaluation_limit_exceeded"
    assert attempt["attempted_shape_units"] is None
    assert attempt["aggregate_before_reservation"] == 0
    assert attempt["aggregate_after_reservation"] is None
    assert attempt["evaluator_invoked"] is False
    assert attempt["evaluation_passed"] is None
    assert core["aggregate_schema_evaluation_shape_units"] == 0
    assert core["within_every_per_evaluation_limit"] is False
    assert core["invocation_shape_limit"] == 16_000_000
    assert core["within_invocation_limit"] is True


def test_fixed_report_seal_allowance_covers_worst_permitted_work() -> None:
    fixture = make_boundary_campaign_fixture()
    validation = validate_artifacts(
        fixture.program,
        fixture.recipe_bytes,
        fixture.trusted_bundle,
    )
    assert type(validation) is PublishedValidationReport
    report = json.loads(validation.canonical_bytes)
    ledger = BudgetLedger(fixture.program.budget_manifest)
    frozen = ledger.reserve_report_seal_and_freeze()
    meter = SealMeter(frozen)

    meter.charge_projection_fields(131_072)
    meter.charge_canonical_bytes(2_097_152)
    meter.charge_canonical_bytes(2_097_152)

    assert report["validation_budget"]["observed"][
        "report_seal_reserved_work_units"
    ] == 262_144
    assert meter.projection_fields == 131_072
    assert meter.canonical_bytes == 4_194_304
    assert meter.work_units == 196_608
    assert 262_144 - meter.work_units == 65_536
