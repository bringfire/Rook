from __future__ import annotations

import base64
import importlib
import json
import socket
import sys
import time
from types import MappingProxyType

from rook.validation_kernel import (
    PublishedValidationReport,
    TrustedConformanceGateResult,
    run_conformance_gate,
    validate_artifacts,
)
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
)
from rook.validation_kernel.owned_json import own_trusted_json
from rook.validation_kernel.invocation import (
    issue_trusted_validation_bundle,
    seal_trusted_bundle_assembler_profile,
)
from rook.validation_kernel.program import compose_and_seal_program

from tests._validation_kernel_fakes import (
    make_assembler_profile_candidate,
    make_boundary_campaign_fixture,
    make_phase_engine_contribution,
    make_validation_bundle_bytes,
)


_BOUNDARY_GOLDEN_EXPECTATIONS = MappingProxyType(
    {
        "sha256:e5b4c2a28b7d08d8a79ce0070682f43823dc21145b70dfcb1c0820de499774d3": {
            "result_kind": "published_report",
            "report_schema_id": "synthetic.report:v1",
            "report_fingerprint": "sha256:c03fc4b80e6f233600848b4cfabf348ecbc6c04297e1821e137e8bfea0e582bc",
            "control_failure_stage": None,
            "control_failure_code": None,
            "control_failure_artifact_role": None,
        }
    }
)


def _prohibited_input(*_: object, **__: object) -> object:
    raise AssertionError("replay attempted ambient clock or network input")


def _receipt_value(receipt: object) -> dict[str, object]:
    reservation = receipt.reservation
    return {
        "accepted": reservation.accepted,
        "attempted_shape_units": reservation.attempted_shape_units,
        "aggregate_before": reservation.aggregate_before,
        "aggregate_after": reservation.aggregate_after,
        "rejection_reason": reservation.rejection_reason,
        "evaluator_invoked": receipt.evaluator_invoked,
        "evaluation_passed": receipt.evaluation_passed,
        "bounded_errors": [
            {
                "code": issue.code,
                "instance_path": issue.instance_path,
                "schema_path": issue.schema_path,
                "detail_sha256": issue.detail_sha256,
            }
            for issue in receipt.bounded_errors
        ],
        "failure_code": receipt.failure_code,
    }


def _attempt_value(attempt: object) -> dict[str, object]:
    binding = attempt.instance_binding
    candidate = attempt.pre_evaluation_candidate
    return {
        "schema_id": attempt.schema_id,
        "schema_fingerprint": attempt.schema_fingerprint,
        "schema_nodes": attempt.schema_nodes,
        "per_evaluation_limit": attempt.per_evaluation_limit,
        "instance_binding": {
            "artifact_id": binding.artifact_id,
            "artifact_fingerprint": binding.artifact_fingerprint,
            "instance_pointer": binding.instance_pointer,
        },
        "instance_fingerprint": attempt.instance_fingerprint,
        "instance_nodes": attempt.instance_nodes,
        "pre_evaluation_candidate": (
            None
            if candidate is None
            else {
                "candidate_kind": candidate.candidate_kind,
                "candidate_fingerprint": candidate.candidate_fingerprint,
                "projected_instance_nodes": candidate.projected_instance_nodes,
            }
        ),
        "receipt": _receipt_value(attempt.receipt),
    }


def _encoded_artifact(raw: bytes, fingerprint: str) -> dict[str, str]:
    return {
        "canonical_bytes_base64": base64.b64encode(raw).decode("ascii"),
        "fingerprint": fingerprint,
    }


def _public_schema_stress_report() -> tuple[PublishedValidationReport, int]:
    issue_count = 1_100
    program = compose_and_seal_program(
        make_phase_engine_contribution(alpha_scenario="schema_issue_stress")
    )
    profile = seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate()
    )
    trusted_bundle = issue_trusted_validation_bundle(
        profile,
        make_validation_bundle_bytes(),
    )
    recipe = b'{"items":[' + b",".join([b"0"] * issue_count) + b"]}"
    result = validate_artifacts(program, recipe, trusted_bundle)
    if type(result) is not PublishedValidationReport:
        raise AssertionError("public schema stress validation did not publish")
    return result, issue_count


def main() -> None:
    socket.socket = _prohibited_input  # type: ignore[assignment]
    socket.create_connection = _prohibited_input  # type: ignore[assignment]
    time.time = _prohibited_input  # type: ignore[assignment]
    time.time_ns = _prohibited_input  # type: ignore[assignment]

    api_module = importlib.import_module("rook.validation_kernel.api")
    fixture = make_boundary_campaign_fixture(
        expected_results=_BOUNDARY_GOLDEN_EXPECTATIONS
    )
    audited = api_module._validate_artifacts_with_audit(
        fixture.program,
        fixture.recipe_bytes,
        fixture.trusted_bundle,
    )
    validation = audited.public_result
    campaign = run_conformance_gate(
        fixture.gate_profile,
        fixture.program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    if type(validation) is not PublishedValidationReport:
        raise AssertionError("fixed replay validation did not publish a report")
    if type(campaign) is not TrustedConformanceGateResult:
        raise AssertionError("fixed replay campaign did not issue a result")
    stress_report, source_schema_issue_count = _public_schema_stress_report()
    if source_schema_issue_count <= 1_024:
        raise AssertionError("schema stress input did not exceed issue bound")

    report_host = json.loads(validation.canonical_bytes)
    budget_fingerprint = canonical_fingerprint(
        own_trusted_json(report_host["validation_budget"])
    )
    audit_value = own_trusted_json(
        {
            "program_id": audited.audit.program_id,
            "program_fingerprint": audited.audit.program_fingerprint,
            "attempts": [
                _attempt_value(attempt)
                for attempt in audited.audit.schema_evaluation_attempts
            ],
            "adapter_invocations": [
                _receipt_value(receipt)
                for receipt in audited.audit.schema_evaluation_receipts
            ],
        }
    )
    output = own_trusted_json(
        {
            "sealed_program_manifest": _encoded_artifact(
                fixture.program.manifest_bytes,
                fixture.program.program_fingerprint,
            ),
            "validation_report": _encoded_artifact(
                validation.canonical_bytes,
                validation.report_fingerprint,
            ),
            "public_schema_stress_report": _encoded_artifact(
                stress_report.canonical_bytes,
                stress_report.report_fingerprint,
            ),
            "conformance_campaign_manifest": _encoded_artifact(
                fixture.campaign_bytes,
                fixture.campaign_fingerprint,
            ),
            "conformance_campaign_report": _encoded_artifact(
                campaign.report_bytes,
                campaign.report_fingerprint,
            ),
            "validation_terminal_variant": type(validation).__name__,
            "public_schema_stress_terminal_variant": type(stress_report).__name__,
            "source_schema_issue_count": source_schema_issue_count,
            "conformance_terminal_variant": type(campaign).__name__,
            "budget_fingerprint": budget_fingerprint,
            "audit_fingerprint": canonical_fingerprint(audit_value),
        }
    )
    sys.stdout.buffer.write(canonical_json_bytes(output) + b"\n")


if __name__ == "__main__":
    main()
