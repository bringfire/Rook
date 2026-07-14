from __future__ import annotations

import base64
import importlib
import json
import socket
import sys
import time

from rook.validation_kernel import (
    PublishedValidationReport,
    TrustedConformanceGateResult,
    run_conformance_gate,
)
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
)
from rook.validation_kernel.owned_json import own_trusted_json

from tests._validation_kernel_fakes import make_boundary_campaign_fixture


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


def main() -> None:
    socket.socket = _prohibited_input  # type: ignore[assignment]
    socket.create_connection = _prohibited_input  # type: ignore[assignment]
    time.time = _prohibited_input  # type: ignore[assignment]
    time.time_ns = _prohibited_input  # type: ignore[assignment]

    api_module = importlib.import_module("rook.validation_kernel.api")
    fixture = make_boundary_campaign_fixture()
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
            "conformance_campaign_manifest": _encoded_artifact(
                fixture.campaign_bytes,
                fixture.campaign_fingerprint,
            ),
            "conformance_campaign_report": _encoded_artifact(
                campaign.report_bytes,
                campaign.report_fingerprint,
            ),
            "validation_terminal_variant": type(validation).__name__,
            "conformance_terminal_variant": type(campaign).__name__,
            "budget_fingerprint": budget_fingerprint,
            "audit_fingerprint": canonical_fingerprint(audit_value),
        }
    )
    sys.stdout.buffer.write(canonical_json_bytes(output) + b"\n")


if __name__ == "__main__":
    main()
