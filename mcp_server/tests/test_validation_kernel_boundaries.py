from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
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
    assert all(not hasattr(validation_kernel, name) for name in forbidden)
    assert "_ValidationExecutionAudit" not in inspect.get_annotations(
        validation_kernel.ValidationResult
    )


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


def _synchronized_round(
    cases: tuple[_BoundaryCase, ...],
    invoke: object,
) -> dict[str, object]:
    barrier = threading.Barrier(8)

    def worker(case: _BoundaryCase) -> object:
        barrier.wait()
        return invoke(case)  # type: ignore[operator]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = tuple(executor.submit(worker, case) for case in cases)
        return {
            case.case_id: future.result()
            for case, future in zip(cases, futures, strict=True)
        }


def _assert_public_case_isolation(
    snapshots: dict[str, dict[str, object]],
) -> None:
    assert len({repr(snapshot) for snapshot in snapshots.values()}) == 8
    reports = [
        snapshot for snapshot in snapshots.values() if snapshot["report_present"]
    ]
    assert len(reports) == 6
    assert len({snapshot["report_fingerprint"] for snapshot in reports}) == 6
    assert len({repr(snapshot["raw_input_hashes"]) for snapshot in reports}) == 6
    assert len({repr(snapshot["budget_counters"]) for snapshot in reports}) == 6
    failures = [
        snapshot for snapshot in snapshots.values() if not snapshot["report_present"]
    ]
    assert {
        dict(snapshot["failure_fields"])["code"] for snapshot in failures
    } == {"validator_integrity_failure", "validation_budget_exceeded"}


def test_public_concurrent_invocations_are_isolated_for_ten_barrier_rounds() -> None:
    fixture = make_boundary_campaign_fixture()
    cases = _boundary_cases()
    serial = {
        case.case_id: _public_snapshot(
            validate_artifacts(
                fixture.program,
                case.recipe_bytes,
                fixture.trusted_bundle,
            )
        )
        for case in cases
    }
    _assert_public_case_isolation(serial)

    for _ in range(10):
        concurrent = _synchronized_round(
            cases,
            lambda case: validate_artifacts(
                fixture.program,
                case.recipe_bytes,
                fixture.trusted_bundle,
            ),
        )
        assert {
            case_id: _public_snapshot(result)
            for case_id, result in concurrent.items()
        } == serial

    forbidden = {
        "_ValidationExecutionAudit",
        "schema_evaluation_attempts",
        "schema_evaluation_receipts",
    }
    assert forbidden.isdisjoint(validation_kernel.__all__)
    for snapshot in serial.values():
        assert forbidden.isdisjoint(snapshot)


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
    _assert_public_case_isolation(public_oracles)

    for case in cases[:6]:
        marker = f"artifact:{case.case_id}"
        own_rows = repr(audit_oracles[case.case_id]["attempt_rows"])
        assert marker in own_rows
        assert all(
            marker not in repr(other["attempt_rows"])
            for other_id, other in audit_oracles.items()
            if other_id != case.case_id
        )
    assert all(
        audit["program_id"] == fixture.program.program_id
        and audit["program_fingerprint"] == fixture.program.program_fingerprint
        for audit in audit_oracles.values()
    )
    assert all(
        case.case_id not in repr(
            (
                audit_oracles[case.case_id]["program_id"],
                audit_oracles[case.case_id]["program_fingerprint"],
            )
        )
        for case in cases
    )

    for _ in range(10):
        concurrent = _synchronized_round(
            cases,
            lambda case: api_module._validate_artifacts_with_audit(
                fixture.program,
                case.recipe_bytes,
                fixture.trusted_bundle,
            ),
        )
        for case_id, outcome in concurrent.items():
            assert _public_snapshot(outcome.public_result) == public_oracles[case_id]
            assert _audit_snapshot(outcome.audit) == audit_oracles[case_id]
            assert api_module._is_validation_execution_audit(
                outcome.audit, fixture.program
            )

    assert all(
        "audit" not in json.loads(result.canonical_bytes)
        for result in (
            outcome.public_result for outcome in private_oracles.values()
        )
        if type(result) is PublishedValidationReport
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


def test_over_budget_schema_fixture_fails_the_aggregate_release_decision() -> None:
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
    core = next(
        row
        for row in report["result_rows"]
        if row["case_kind"] == "core_schema_positive"
    )
    assert core["outcome"] == "failed"
    assert core["failure_code"] == "validation_budget_exceeded"
    attempt = core["schema_evaluations"][0]
    assert attempt["attempt_status"] == "reservation_rejected"
    assert attempt["evaluator_invoked"] is False


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
