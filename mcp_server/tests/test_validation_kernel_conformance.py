from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import dataclass, replace
from types import MappingProxyType, SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

import rook.validation_kernel.conformance as conformance_module
import rook.validation_kernel.api as api_module
import rook.validation_kernel.reporting as reporting_module
from rook.validation_kernel import (
    ConformanceGateInvocationFailure,
    PublishedValidationReport,
    SealedConformanceGateProfile,
    TrustedConformanceFixtureContext,
    TrustedConformanceGateResult,
    ValidationControlFailure,
    validate_artifacts,
)
from rook.validation_kernel.conformance import seal_conformance_gate_profile
from rook.validation_kernel.invocation import (
    issue_trusted_validation_bundle,
    seal_trusted_bundle_assembler_profile,
)
from rook.validation_kernel.kernel_schemas import (
    CONFORMANCE_CAMPAIGN_SCHEMA,
    CONFORMANCE_COMPLETENESS_SCHEMA,
    CONFORMANCE_FIXTURE_SCHEMA,
    CONFORMANCE_GATE_PROFILE_SCHEMA,
    CONFORMANCE_REPORT_SCHEMA,
    CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA,
)
from rook.validation_kernel.program import compose_and_seal_program
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
    sha256_prefixed,
)
from rook.validation_kernel.budget import BudgetLedger, LM9A_BUDGET_MANIFEST
from rook.validation_kernel.control import BudgetDimension
from rook.validation_kernel.owned_json import JsonObject, own_trusted_json
from rook.validation_kernel.schema_profile import (
    CORE_SCHEMA_PROFILE_ID,
    InstanceBinding,
    evaluate_schema,
)

from tests._validation_kernel_fakes import (
    ImmutableArtifactStore,
    make_assembler_profile_candidate,
    make_conformance_gate_profile_candidate,
    make_conformance_program_contribution,
    make_validation_bundle_bytes,
    validation_golden_key,
)


_CORE_REF = "artifact:core-positive"
_FIXTURE_REF = "artifact:fixture-report-pass"
_RECIPE_REF = "artifact:fixture-recipe"
_BUNDLE_REF = "artifact:fixture-bundle"
_CONFORMANCE_GOLDEN_EXPECTATIONS = MappingProxyType(
    {
        # default / generic fixture ID
        "sha256:c943db0ad9a6118f2bbb6576b187dd69181e3aa6e8e2f5a260150789fb7ce7b6": {
            "result_kind": "published_report",
            "report_schema_id": "synthetic.report:v1",
            "report_fingerprint": "sha256:4fe3191569179f320ba144b7eacf996167fe68585dc396370df61a1f2d1bf183",
            "control_failure_stage": None,
            "control_failure_code": None,
            "control_failure_artifact_role": None,
        },
        # equal-shaped semantic subtrees
        "sha256:7d8b253aeb832d5fa4ef0d406e197b8fc06f7d5b6826b589f05c4dede623dbb3": {
            "result_kind": "published_report",
            "report_schema_id": "synthetic.report:v1",
            "report_fingerprint": "sha256:459b4d1f62de23add6d34f0419691989415d36bb1df2033cee9b55e842fb85dc",
            "control_failure_stage": None,
            "control_failure_code": None,
            "control_failure_artifact_role": None,
        },
        # wide core schema
        "sha256:a80c4541a3e004f627b212fddf4389b106dd7550bd5aa86ec4c1e673ec60ab58": {
            "result_kind": "published_report",
            "report_schema_id": "synthetic.report:v1",
            "report_fingerprint": "sha256:4fe3191569179f320ba144b7eacf996167fe68585dc396370df61a1f2d1bf183",
            "control_failure_stage": None,
            "control_failure_code": None,
            "control_failure_artifact_role": None,
        },
        # raw recipe byte cap
        "sha256:7d5e9f93aed28dabe707542fea45d3af9b56c919711a63a84b61f87f42edfe98": {
            "result_kind": "control_failure",
            "report_schema_id": None,
            "report_fingerprint": None,
            "control_failure_stage": "preflight",
            "control_failure_code": "validation_budget_exceeded",
            "control_failure_artifact_role": "recipe",
        },
        # malformed recipe
        "sha256:78ffb6cacde2b2004eccecc06f91117a14c5965070c2a3463ccf64b622cc1604": {
            "result_kind": "control_failure",
            "report_schema_id": None,
            "report_fingerprint": None,
            "control_failure_stage": "validation",
            "control_failure_code": "validator_integrity_failure",
            "control_failure_artifact_role": "phase_engine",
        },
        # accepted schema evaluation followed by integrity failure
        "sha256:cf8368ab344f0ff972558dd1718b71ff8edb51c6c65d0d45bdd309f6e73bce9d": {
            "result_kind": "control_failure",
            "report_schema_id": None,
            "report_fingerprint": None,
            "control_failure_stage": "validation",
            "control_failure_code": "validator_integrity_failure",
            "control_failure_artifact_role": "phase_engine",
        },
        # final report reservation rejection
        "sha256:e20d14176b69be8d9fcaa39f4050c859d9e3d0ba241a837f3aa2f3d8732ac10c": {
            "result_kind": "control_failure",
            "report_schema_id": None,
            "report_fingerprint": None,
            "control_failure_stage": "validation",
            "control_failure_code": "validation_budget_exceeded",
            "control_failure_artifact_role": "report_seal",
        },
        # ordered semantic schema audit
        "sha256:3c9cea17ce26dfb55fbcb39f3265241ac0ef94e2781f44906b0973d210ecf2bb": {
            "result_kind": "published_report",
            "report_schema_id": "synthetic.report:v1",
            "report_fingerprint": "sha256:a99cb70a407fe961c3c45632313afcf9dac9f95f6f9abb707d5c157d2ff8cf39",
            "control_failure_stage": None,
            "control_failure_code": None,
            "control_failure_artifact_role": None,
        },
    }
)


def _owned_object(value: object) -> JsonObject:
    owned = own_trusted_json(value)
    assert type(owned) is JsonObject
    return owned


def _fingerprinted(value: dict[str, object], field: str) -> dict[str, object]:
    unsigned = {key: item for key, item in value.items() if key != field}
    return {**unsigned, field: canonical_fingerprint(_owned_object(unsigned))}


def _case_set_fingerprint(cases: list[dict[str, object]]) -> str:
    pairs = [
        {
            "case_id": case["case_id"],
            "case_fingerprint": case["case_fingerprint"],
        }
        for case in sorted(cases, key=lambda item: str(item["case_id"]))
    ]
    return canonical_fingerprint(own_trusted_json(pairs))


def _reseal_campaign(campaign: dict[str, object]) -> bytes:
    cases = campaign["required_cases"]
    assert type(cases) is list
    campaign["required_cases"] = sorted(cases, key=lambda item: item["case_id"])
    campaign["required_case_set_fingerprint"] = _case_set_fingerprint(cases)
    campaign.pop("campaign_fingerprint", None)
    campaign["campaign_fingerprint"] = canonical_fingerprint(
        _owned_object(campaign)
    )
    return canonical_json_bytes(_owned_object(campaign))


@dataclass(frozen=True)
class CampaignFixture:
    campaign: dict[str, object]
    campaign_bytes: bytes
    artifacts: dict[str, object]
    fixture_context: TrustedConformanceFixtureContext


def _campaign_fixture(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
    *,
    recipe_bytes: bytes = b'{"nested":{"value":1}}',
    fixture_id: str | None = None,
) -> CampaignFixture:
    bundle_bytes = make_validation_bundle_bytes()
    golden_key = validation_golden_key(
        program,
        recipe_bytes,
        bundle_bytes,
        assembler_profile,
    )
    try:
        expected_result = dict(_CONFORMANCE_GOLDEN_EXPECTATIONS[golden_key])
    except KeyError:
        raise AssertionError(
            f"no static validation golden for exact key {golden_key}"
        ) from None

    fixture_manifest = _fingerprinted(
        {
            "schema": "rook.validation_conformance_fixture:v1",
            "fixture_id": (
                fixture_id
                if fixture_id is not None
                else (
                    "fixture.report_pass"
                    if expected_result["result_kind"] == "published_report"
                    else "fixture.control_failure_expected"
                )
            ),
            "recipe_input": {
                "content_ref": _RECIPE_REF,
                "input_payload_sha256": sha256_prefixed(recipe_bytes),
            },
            "validation_bundle_input": {
                "content_ref": _BUNDLE_REF,
                "input_payload_sha256": sha256_prefixed(bundle_bytes),
            },
            "assembler_profile_fingerprint": assembler_profile.profile_fingerprint,  # type: ignore[attr-defined]
            "expected_result": expected_result,
        },
        "fixture_fingerprint",
    )
    fixture_bytes = canonical_json_bytes(_owned_object(fixture_manifest))

    core_schema = next(
        schema
        for schema in program.schemas  # type: ignore[attr-defined]
        if schema.profile_id == CORE_SCHEMA_PROFILE_ID
    )
    core_bytes = b'{"value":"ok"}'
    core_value = own_trusted_json({"value": "ok"})
    core_case = _fingerprinted(
        {
            "case_id": "core.synthetic_positive",
            "case_kind": "core_schema_positive",
            "schema_case": {
                "schema_id": core_schema.schema_id,
                "schema_fingerprint": core_schema.schema_fingerprint,
                "instance_fingerprint": canonical_fingerprint(core_value),
                "instance_content_ref": _CORE_REF,
            },
            "fixture_case": None,
        },
        "case_fingerprint",
    )
    fixture_case = _fingerprinted(
        {
            "case_id": str(fixture_manifest["fixture_id"]),
            "case_kind": "semantic_fixture",
            "schema_case": None,
            "fixture_case": {
                "fixture_fingerprint": fixture_manifest["fixture_fingerprint"],
                "fixture_content_ref": _FIXTURE_REF,
                "recipe_input_payload_sha256": sha256_prefixed(recipe_bytes),
                "validation_bundle_input_payload_sha256": sha256_prefixed(
                    bundle_bytes
                ),
                "assembler_profile_fingerprint": assembler_profile.profile_fingerprint,  # type: ignore[attr-defined]
            },
        },
        "case_fingerprint",
    )
    cases = [core_case, fixture_case]
    campaign = {
        "schema": "rook.validation_conformance_campaign:v1",
        "campaign_id": "synthetic.kernel_conformance:v1",
        "campaign_version": "v1",
        "program_id": program.program_id,  # type: ignore[attr-defined]
        "program_fingerprint": program.program_fingerprint,  # type: ignore[attr-defined]
        "required_gate_profile_fingerprint": gate_profile.gate_profile_fingerprint,
        "required_cases": cases,
        "required_case_set_fingerprint": _case_set_fingerprint(cases),
    }
    campaign_bytes = _reseal_campaign(campaign)
    artifacts: dict[str, object] = {
        _CORE_REF: core_bytes,
        _FIXTURE_REF: fixture_bytes,
        _RECIPE_REF: recipe_bytes,
        _BUNDLE_REF: bundle_bytes,
    }
    store = ImmutableArtifactStore(artifacts)
    context = conformance_module._issue_trusted_conformance_fixture_context(
        store,
        (assembler_profile,),
    )
    return CampaignFixture(campaign, campaign_bytes, artifacts, context)


@pytest.fixture(scope="module")
def program() -> object:
    return compose_and_seal_program(make_conformance_program_contribution())


@pytest.fixture(scope="module")
def assembler_profile() -> object:
    return seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate()
    )


@pytest.fixture(scope="module")
def gate_profile() -> SealedConformanceGateProfile:
    return seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )


@pytest.fixture()
def campaign(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
) -> CampaignFixture:
    return _campaign_fixture(program, gate_profile, assembler_profile)


def _report(result: object) -> dict[str, object]:
    assert type(result) is TrustedConformanceGateResult
    report = json.loads(result.report_bytes)
    assert type(report) is dict
    return report


def _rows_by_id(report: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = report["result_rows"]
    assert type(rows) is list
    return {str(row["case_id"]): row for row in rows}


def test_conformance_attempt_row_resolves_exact_root_pointer_and_instance(
    program: object,
) -> None:
    schema = next(
        candidate
        for candidate in program.schemas  # type: ignore[attr-defined]
        if candidate.profile_id == CORE_SCHEMA_PROFILE_ID
    )
    root = _owned_object(
        {
            "left": {"value": "ok"},
            "right": {"value": "ok"},
        }
    )
    instance = root["right"]
    assert type(instance) is JsonObject
    root_fingerprint = canonical_fingerprint(root)
    correct = InstanceBinding(
        artifact_id="artifact:core-positive",
        artifact_fingerprint=root_fingerprint,
        instance_pointer="/right",
    )
    receipt = evaluate_schema(
        schema,
        instance,
        instance_binding=correct,
        ledger=BudgetLedger(LM9A_BUDGET_MANIFEST),
    )

    row = conformance_module._attempt_row(
        evaluation_index=0,
        schema=schema,
        instance_binding=correct,
        instance_root=root,
        instance_root_fingerprint=root_fingerprint,
        instance=instance,
        receipt=receipt,
        per_evaluation_limit=8_000_000,
    )

    assert row["instance_fingerprint"] == canonical_fingerprint(instance)
    detached = JsonObject(tuple(instance.members))
    invalid = (
        (
            InstanceBinding(
                artifact_id=correct.artifact_id,
                artifact_fingerprint="sha256:" + ("0" * 64),
                instance_pointer="/right",
            ),
            instance,
        ),
        (
            InstanceBinding(
                artifact_id=correct.artifact_id,
                artifact_fingerprint=root_fingerprint,
                instance_pointer="/missing",
            ),
            instance,
        ),
        (
            InstanceBinding(
                artifact_id=correct.artifact_id,
                artifact_fingerprint=root_fingerprint,
                instance_pointer="/left",
            ),
            instance,
        ),
        (correct, detached),
    )
    for candidate_binding, candidate_instance in invalid:
        with pytest.raises(
            conformance_module._GateIntegrityFailure,
            match="instance binding",
        ):
            conformance_module._attempt_row(
                evaluation_index=0,
                schema=schema,
                instance_binding=candidate_binding,
                instance_root=root,
                instance_root_fingerprint=root_fingerprint,
                instance=candidate_instance,
                receipt=receipt,
                per_evaluation_limit=8_000_000,
            )


def test_release_authority_is_sealed_opaque_and_nonforgeable(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    assert type(gate_profile) is SealedConformanceGateProfile
    with pytest.raises(TypeError):
        SealedConformanceGateProfile()
    with pytest.raises(TypeError):
        TrustedConformanceFixtureContext()
    with pytest.raises(TypeError):
        TrustedConformanceGateResult()

    serialized_profile = json.loads(gate_profile.profile_bytes)
    failure = conformance_module.run_conformance_gate(
        serialized_profile,  # type: ignore[arg-type]
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    assert type(failure) is ConformanceGateInvocationFailure
    assert failure.stage == "gate_authority"
    assert failure.code == "gate_profile_not_sealed"
    assert failure.report_emitted is False
    assert failure.trusted_gate_result_issued is False

    selected = copy.deepcopy(campaign.campaign)
    selected["gate_callable"] = "campaign.selected.callable"
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        _reseal_campaign(selected),
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.code == "campaign_schema_failed"


def test_gate_seal_rejects_writable_function_metadata_spoof() -> None:
    gate_callable = conformance_module._execute_conformance_gate
    namespace: dict[str, object] = {}
    exec(
        compile(
            "def _execute_conformance_gate(*args, **kwargs):\n    return None\n",
            "<conformance-gate-spoof>",
            "exec",
        ),
        namespace,
    )
    spoof = namespace["_execute_conformance_gate"]
    assert callable(spoof)
    spoof.__module__ = gate_callable.__module__  # type: ignore[attr-defined]
    spoof.__name__ = gate_callable.__name__  # type: ignore[attr-defined]
    spoof.__qualname__ = gate_callable.__qualname__  # type: ignore[attr-defined]
    candidate = make_conformance_gate_profile_candidate(gate_callable)

    with pytest.raises(TypeError, match="not a sealable runtime binding"):
        seal_conformance_gate_profile(candidate, spoof)  # type: ignore[arg-type]


def test_campaign_admission_is_exact_bounded_and_hashes_only_admitted_bytes(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    exact_limit = b" " * 4_194_304
    admitted = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        exact_limit,
        campaign.fixture_context,
    )
    assert type(admitted) is ConformanceGateInvocationFailure
    assert admitted.campaign_input_size == 4_194_304
    assert admitted.campaign_input_sha256 == sha256_prefixed(exact_limit)

    rejected = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        exact_limit + b"x",
        campaign.fixture_context,
    )
    assert type(rejected) is ConformanceGateInvocationFailure
    assert rejected.stage == "campaign_admission"
    assert rejected.code == "campaign_admission_failed"
    assert rejected.campaign_input_size == 4_194_305
    assert rejected.campaign_input_sha256 is None


def test_invalid_program_and_unavailable_campaign_fail_before_identity(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    invalid_program = conformance_module.run_conformance_gate(
        gate_profile,
        object(),  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    assert type(invalid_program) is ConformanceGateInvocationFailure
    assert invalid_program.stage == "program_authority"
    assert invalid_program.code == "program_not_sealed"
    assert invalid_program.program_fingerprint is None

    unavailable_campaign = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        bytearray(campaign.campaign_bytes),  # type: ignore[arg-type]
        campaign.fixture_context,
    )
    assert type(unavailable_campaign) is ConformanceGateInvocationFailure
    assert unavailable_campaign.stage == "campaign_admission"
    assert unavailable_campaign.code == "campaign_content_unavailable"
    assert unavailable_campaign.campaign_input_size == 0
    assert unavailable_campaign.campaign_input_sha256 is None


@pytest.mark.parametrize(
    ("raw", "code"),
    (
        (b'{"schema":', "campaign_parse_failed"),
        (b'{"schema":1,"schema":2}', "campaign_parse_failed"),
        (b"{}", "campaign_schema_failed"),
    ),
)
def test_unconstructable_campaigns_never_emit_reports(
    raw: bytes,
    code: str,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        raw,
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.code == code
    assert result.report_emitted is False
    assert result.trusted_gate_result_issued is False


def test_campaign_identity_mismatch_is_an_invocation_failure(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    host = copy.deepcopy(campaign.campaign)
    host["campaign_fingerprint"] = "sha256:" + "0" * 64
    raw = canonical_json_bytes(_owned_object(host))
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        raw,
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.stage == "campaign_identity"
    assert result.code == "campaign_fingerprint_mismatch"


def test_case_set_fingerprint_mismatch_prevents_report_authority(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    host = copy.deepcopy(campaign.campaign)
    host["required_case_set_fingerprint"] = "sha256:" + "8" * 64
    host.pop("campaign_fingerprint")
    host["campaign_fingerprint"] = canonical_fingerprint(_owned_object(host))
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        canonical_json_bytes(_owned_object(host)),
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.stage == "campaign_identity"
    assert result.code == "campaign_case_set_fingerprint_mismatch"


@pytest.mark.parametrize(
    "mismatch",
    ("program", "gate", "coverage"),
)
def test_constructable_campaign_integrity_mismatch_is_a_failed_empty_report(
    mismatch: str,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    host = copy.deepcopy(campaign.campaign)
    if mismatch == "program":
        host["program_fingerprint"] = "sha256:" + "0" * 64
    elif mismatch == "gate":
        host["required_gate_profile_fingerprint"] = "sha256:" + "1" * 64
    else:
        host["required_cases"] = [
            case
            for case in host["required_cases"]
            if case["case_kind"] != "core_schema_positive"
        ]
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        _reseal_campaign(host),
        campaign.fixture_context,
    )
    report = _report(result)
    assert report["decision"] == "failed"
    assert report["result_rows"] == []
    assert report["campaign_integrity"]["passed"] is False


@pytest.mark.parametrize("content", (None, b'{"value":"changed"}'))
def test_missing_or_mismatched_core_content_has_no_schema_attempt(
    content: object,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
    campaign: CampaignFixture,
) -> None:
    artifacts = dict(campaign.artifacts)
    artifacts[_CORE_REF] = content
    context = conformance_module._issue_trusted_conformance_fixture_context(
        ImmutableArtifactStore(artifacts),
        (assembler_profile,),
    )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        context,
    )
    row = _rows_by_id(_report(result))["core.synthetic_positive"]
    assert row["outcome"] == "failed"
    assert row["schema_evaluations"] == []
    assert row["schema_case_result"] == {"instance_schema_valid": None}
    assert row["fixture_case_result"] is None


def test_referenced_content_cap_is_inclusive_and_checked_before_parsing(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
    campaign: CampaignFixture,
) -> None:
    failures: list[str] = []
    for content in (b" " * 4_194_304, b" " * 4_194_305):
        artifacts = dict(campaign.artifacts)
        artifacts[_CORE_REF] = content
        context = conformance_module._issue_trusted_conformance_fixture_context(
            ImmutableArtifactStore(artifacts),
            (assembler_profile,),
        )
        result = conformance_module.run_conformance_gate(
            gate_profile,
            program,  # type: ignore[arg-type]
            campaign.campaign_bytes,
            context,
        )
        row = _rows_by_id(_report(result))["core.synthetic_positive"]
        failures.append(row["failure_code"])
        assert row["schema_evaluations"] == []
    assert failures == ["case_execution_failed", "case_content_unavailable"]


def test_successful_campaign_seals_exact_identity_and_attempt_rows(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    report = _report(result)
    assert report["decision"] == "passed"
    assert report["program_fingerprint"] == program.program_fingerprint  # type: ignore[attr-defined]
    assert report["campaign_fingerprint"] == campaign.campaign["campaign_fingerprint"]
    assert report["gate"]["gate_profile_fingerprint"] == gate_profile.gate_profile_fingerprint
    assert [row["result_index"] for row in report["result_rows"]] == [0, 1]
    assert [row["case_id"] for row in report["result_rows"]] == sorted(
        row["case_id"] for row in report["result_rows"]
    )
    core = _rows_by_id(report)["core.synthetic_positive"]
    attempt = core["schema_evaluations"][0]
    assert attempt["attempt_status"] == "evaluation_completed"
    assert attempt["aggregate_after_reservation"] == (
        attempt["aggregate_before_reservation"]
        + attempt["attempted_shape_units"]
    )
    assert attempt["evaluator_invoked"] is True
    assert attempt["evaluation_passed"] is True
    assert core["schema_case_result"]["instance_schema_valid"] is True
    fixture = _rows_by_id(report)["fixture.report_pass"]
    assert fixture["schema_case_result"] is None
    assert fixture["fixture_case_result"]["result_identity_matches"] is True

    unsigned = dict(report)
    asserted = unsigned.pop("report_fingerprint")
    assert canonical_fingerprint(_owned_object(unsigned)) == asserted


def test_static_golden_rejects_a_deterministic_wrong_validator(
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
) -> None:
    real = api_module._validate_artifacts_with_audit
    calls = 0
    golden_before = tuple(
        (key, tuple(sorted(value.items())))
        for key, value in _CONFORMANCE_GOLDEN_EXPECTATIONS.items()
    )

    def deterministically_wrong(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        outcome = real(*args, **kwargs)
        wrong = ValidationControlFailure(
            failure_stage="validation",
            code="validator_integrity_failure",
            artifact_role="phase_engine",
            program_id=program.program_id,  # type: ignore[attr-defined]
            program_fingerprint=program.program_fingerprint,  # type: ignore[attr-defined]
            subject_path=None,
            message="Validator integrity check failed.",
            detail_sha256=None,
        )
        return replace(outcome, public_result=wrong)

    monkeypatch.setattr(
        api_module,
        "_validate_artifacts_with_audit",
        deterministically_wrong,
    )
    monkeypatch.setattr(
        conformance_module,
        "_validate_artifacts_with_audit",
        deterministically_wrong,
    )
    fixture = _campaign_fixture(program, gate_profile, assembler_profile)
    assert calls == 0

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        fixture.campaign_bytes,
        fixture.fixture_context,
    )

    report = _report(result)
    row = _rows_by_id(report)["fixture.report_pass"]
    identity = row["fixture_case_result"]
    assert calls == 1
    assert report["decision"] == "failed"
    assert row["outcome"] == "failed"
    assert identity["expected_result_kind"] == "published_report"
    assert identity["actual_result_kind"] == "control_failure"
    assert identity["result_identity_matches"] is False
    assert golden_before == tuple(
        (key, tuple(sorted(value.items())))
        for key, value in _CONFORMANCE_GOLDEN_EXPECTATIONS.items()
    )


def test_fixture_machine_id_accepts_third_generic_identity(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
) -> None:
    fixture_id = "fixture.generic_third_case"
    fixture = _campaign_fixture(
        program,
        gate_profile,
        assembler_profile,
        fixture_id=fixture_id,
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        fixture.campaign_bytes,
        fixture.fixture_context,
    )

    report = _report(result)
    assert report["decision"] == "passed"
    assert _rows_by_id(report)[fixture_id]["outcome"] == "passed"


def test_semantic_attempt_rows_use_authenticated_entries_without_reparsing(
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    assembler_profile: object,
    campaign: CampaignFixture,
) -> None:
    recipe_bytes = campaign.artifacts[_RECIPE_REF]
    bundle_bytes = campaign.artifacts[_BUNDLE_REF]
    assert type(recipe_bytes) is bytes
    assert type(bundle_bytes) is bytes
    trusted_bundle = issue_trusted_validation_bundle(
        assembler_profile, bundle_bytes  # type: ignore[arg-type]
    )
    outcome = conformance_module._validate_artifacts_with_audit(
        program,
        recipe_bytes,
        trusted_bundle,
    )

    def forbidden_reparse(*_: object, **__: object) -> object:
        raise AssertionError("semantic audit consumption reparsed fixture inputs")

    monkeypatch.setattr(conformance_module, "_parse_gate_json", forbidden_reparse)

    attempts = conformance_module._semantic_attempt_rows(
        outcome,
        program=program,
    )

    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["schema_id"] == outcome.public_result.schema_id
    assert attempt["instance_binding"]["artifact_id"] == program.program_id  # type: ignore[index,union-attr]


@pytest.mark.parametrize(
    ("failure_point", "dimension"),
    (
        ("second_canonical", "report_canonical_bytes"),
        ("second_meter_charge", "report_seal_work_units"),
    ),
)
def test_semantic_case_records_no_report_attempt_when_second_pass_seal_fails(
    failure_point: str,
    dimension: str,
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    state = {"failure_calls": 0, "evaluation_calls": 0}
    observed_dimensions: list[str] = []
    real_evaluate = reporting_module.evaluate_schema_with_reservation
    real_validate = conformance_module._validate_artifacts_with_audit

    def evaluation_spy(*args: object, **kwargs: object) -> object:
        state["evaluation_calls"] += 1
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(
        reporting_module, "evaluate_schema_with_reservation", evaluation_spy
    )
    if failure_point == "second_canonical":
        real_canonical = reporting_module.canonical_json_bytes

        def fail_second_canonical(
            value: object, *, max_bytes: int | None = None
        ) -> bytes:
            state["failure_calls"] += 1
            if state["failure_calls"] == 2:
                raise reporting_module.CanonicalJsonSizeError(
                    2_097_152, 2_097_153
                )
            return real_canonical(value, max_bytes=max_bytes)

        monkeypatch.setattr(
            reporting_module,
            "canonical_json_bytes",
            fail_second_canonical,
        )
    else:
        real_meter = reporting_module.SealMeter

        class FailingReportSealMeter(real_meter):
            def charge_canonical_bytes(self, byte_count: int) -> None:
                state["failure_calls"] += 1
                if state["failure_calls"] == 2:
                    raise reporting_module._SealMeterExceeded(
                        reporting_module.BudgetDimension.REPORT_SEAL_WORK_UNITS,
                        262_144,
                        262_145,
                    )
                super().charge_canonical_bytes(byte_count)

        monkeypatch.setattr(
            reporting_module,
            "SealMeter",
            FailingReportSealMeter,
        )

    def audited_validation_spy(*args: object, **kwargs: object) -> object:
        outcome = real_validate(*args, **kwargs)
        observed_dimensions.append(outcome.public_result.budget_dimension)
        return outcome

    monkeypatch.setattr(
        conformance_module,
        "_validate_artifacts_with_audit",
        audited_validation_spy,
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )

    report = _report(result)
    row = _rows_by_id(report)["fixture.report_pass"]
    identity = row["fixture_case_result"]
    assert report["decision"] == "failed"
    assert row["outcome"] == "failed"
    assert identity["actual_result_kind"] == "control_failure"
    assert identity["actual_control_failure_code"] == (
        "validation_budget_exceeded"
    )
    assert identity["actual_control_failure_artifact_role"] == "report_seal"
    assert row["failure_code"] == "case_execution_failed"
    assert row["schema_evaluations"] == []
    assert row["aggregate_schema_evaluation_shape_units"] == 0
    assert state == {"failure_calls": 2, "evaluation_calls": 0}
    assert observed_dimensions == [dimension]


def test_equal_shaped_semantic_subtrees_keep_exact_ordered_identity(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_conformance_program_contribution(
            alpha_scenario="schema_audit_equal_shape"
        )
    )
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )
    recipe_bytes = b'{"left":{"value":1},"right":{"value":2}}'
    fixture = _campaign_fixture(
        program,
        gate_profile,
        assembler_profile,
        recipe_bytes=recipe_bytes,
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )

    report = _report(result)
    row = _rows_by_id(report)["fixture.report_pass"]
    first, second, _ = row["schema_evaluations"]
    parsed = own_trusted_json(json.loads(recipe_bytes))
    assert first["attempted_shape_units"] == second["attempted_shape_units"]
    assert first["instance_binding"] == {
        "artifact_id": _RECIPE_REF,
        "artifact_fingerprint": canonical_fingerprint(parsed),
    }
    assert second["instance_binding"] == first["instance_binding"]
    assert first["instance_pointer"] == "/left"
    assert second["instance_pointer"] == "/right"
    assert first["instance_fingerprint"] == canonical_fingerprint(parsed["left"])
    assert second["instance_fingerprint"] == canonical_fingerprint(parsed["right"])


def test_repeated_core_evaluations_use_fresh_per_case_accounting(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    host = copy.deepcopy(campaign.campaign)
    first = next(
        case
        for case in host["required_cases"]
        if case["case_kind"] == "core_schema_positive"
    )
    second = copy.deepcopy(first)
    second["case_id"] = "core.synthetic_positive.second"
    second.update(_fingerprinted(second, "case_fingerprint"))
    host["required_cases"].append(second)
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        _reseal_campaign(host),
        campaign.fixture_context,
    )
    report = _report(result)
    assert report["decision"] == "passed"
    core_attempts = [
        row["schema_evaluations"][0]
        for row in report["result_rows"]
        if row["case_kind"] == "core_schema_positive"
    ]
    assert len(core_attempts) == 2
    assert core_attempts[0]["aggregate_before_reservation"] == 0
    assert core_attempts[1]["aggregate_before_reservation"] == 0
    assert core_attempts[0]["aggregate_after_reservation"] == core_attempts[1][
        "aggregate_after_reservation"
    ]
    assert core_attempts[1]["attempted_shape_units"] == core_attempts[0][
        "attempted_shape_units"
    ]


def test_real_reservation_rejection_records_exact_nullable_fields(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_conformance_program_contribution(wide_core_schema=True)
    )
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )
    fixture = _campaign_fixture(program, gate_profile, assembler_profile)
    host = copy.deepcopy(fixture.campaign)
    large_instance = {"value": "ok"}
    large_instance.update({f"field_{index:04d}": index for index in range(4_000)})
    large_value = own_trusted_json(large_instance)
    large_bytes = canonical_json_bytes(large_value)
    core_case = next(
        case
        for case in host["required_cases"]
        if case["case_kind"] == "core_schema_positive"
    )
    core_case["schema_case"]["instance_fingerprint"] = canonical_fingerprint(
        large_value
    )
    core_case.update(_fingerprinted(core_case, "case_fingerprint"))
    artifacts = dict(fixture.artifacts)
    artifacts[_CORE_REF] = large_bytes
    context = conformance_module._issue_trusted_conformance_fixture_context(
        ImmutableArtifactStore(artifacts),
        (assembler_profile,),
    )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,
        _reseal_campaign(host),
        context,
    )
    row = _rows_by_id(_report(result))["core.synthetic_positive"]
    attempt = row["schema_evaluations"][0]
    assert attempt["attempt_status"] == "reservation_rejected"
    assert attempt["aggregate_after_reservation"] is None
    assert attempt["attempted_shape_units"] is None
    assert attempt["evaluator_invoked"] is False
    assert attempt["evaluation_passed"] is None
    assert row["aggregate_schema_evaluation_shape_units"] == attempt[
        "aggregate_before_reservation"
    ]
    assert row["failure_code"] == "validation_budget_exceeded"


def test_accepted_then_rejected_core_cases_keep_fresh_per_case_accounting(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_conformance_program_contribution(wide_core_schema=True)
    )
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )
    fixture = _campaign_fixture(program, gate_profile, assembler_profile)
    host = copy.deepcopy(fixture.campaign)
    first = next(
        case
        for case in host["required_cases"]
        if case["case_kind"] == "core_schema_positive"
    )
    large_instance = {"value": "ok"}
    large_instance.update({f"field_{index:04d}": index for index in range(4_000)})
    large_value = own_trusted_json(large_instance)
    second = copy.deepcopy(first)
    second["case_id"] = "core.synthetic_positive.rejected"
    second["schema_case"]["instance_content_ref"] = "artifact:core-positive-large"
    second["schema_case"]["instance_fingerprint"] = canonical_fingerprint(
        large_value
    )
    second.update(_fingerprinted(second, "case_fingerprint"))
    host["required_cases"].append(second)
    artifacts = dict(fixture.artifacts)
    artifacts["artifact:core-positive-large"] = canonical_json_bytes(large_value)
    context = conformance_module._issue_trusted_conformance_fixture_context(
        ImmutableArtifactStore(artifacts),
        (assembler_profile,),
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,
        _reseal_campaign(host),
        context,
    )

    rows = _rows_by_id(_report(result))
    first_attempt = rows["core.synthetic_positive"]["schema_evaluations"][0]
    rejected_row = rows["core.synthetic_positive.rejected"]
    rejected_attempt = rejected_row["schema_evaluations"][0]
    assert rejected_attempt["attempt_status"] == "reservation_rejected"
    assert first_attempt["aggregate_before_reservation"] == 0
    assert first_attempt["aggregate_after_reservation"] > 0
    assert rejected_attempt["aggregate_before_reservation"] == 0
    assert rejected_row["aggregate_schema_evaluation_shape_units"] == 0


def test_raw_recipe_uses_stricter_validation_cap_after_gate_resolution(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
) -> None:
    recipe = b'{"padding":"' + (b"x" * 1_048_576) + b'"}'
    assert 1_048_576 < len(recipe) < 4_194_304
    fixture = _campaign_fixture(
        program,
        gate_profile,
        assembler_profile,
        recipe_bytes=recipe,
    )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    report = _report(result)
    assert report["decision"] == "passed"
    identity = _rows_by_id(report)["fixture.control_failure_expected"][
        "fixture_case_result"
    ]
    assert identity["actual_control_failure_code"] == "validation_budget_exceeded"
    assert identity["result_identity_matches"] is True


def test_control_failure_fixture_matches_complete_runtime_identity(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
) -> None:
    fixture = _campaign_fixture(
        program,
        gate_profile,
        assembler_profile,
        recipe_bytes=b"{",
    )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    report = _report(result)
    assert report["decision"] == "passed"
    row = _rows_by_id(report)["fixture.control_failure_expected"]
    identity = row["fixture_case_result"]
    assert identity["expected_result_kind"] == "control_failure"
    assert identity["actual_result_kind"] == "control_failure"
    assert identity["expected_report_schema_id"] is None
    assert identity["actual_report_schema_id"] is None
    assert identity["result_identity_matches"] is True


def test_missing_manifest_uses_honest_unknown_fixture_identity(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
    campaign: CampaignFixture,
) -> None:
    artifacts = dict(campaign.artifacts)
    artifacts[_FIXTURE_REF] = None
    context = conformance_module._issue_trusted_conformance_fixture_context(
        ImmutableArtifactStore(artifacts),
        (assembler_profile,),
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        context,
    )

    row = _rows_by_id(_report(result))["fixture.report_pass"]
    assert row["failure_code"] == "case_content_unavailable"
    assert row["fixture_case_result"] is None


@pytest.mark.parametrize("failure", ("missing_recipe", "changed_recipe", "profile"))
def test_post_manifest_failures_preserve_expected_identity_and_actual_unavailable(
    failure: str,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
    campaign: CampaignFixture,
) -> None:
    artifacts = dict(campaign.artifacts)
    profiles: tuple[object, ...] = (assembler_profile,)
    if failure == "missing_recipe":
        artifacts[_RECIPE_REF] = None
    elif failure == "changed_recipe":
        artifacts[_RECIPE_REF] = b'{"changed":true}'
    else:
        profiles = ()
    fixture_manifest = json.loads(campaign.artifacts[_FIXTURE_REF])
    expected = fixture_manifest["expected_result"]
    context = conformance_module._issue_trusted_conformance_fixture_context(
        ImmutableArtifactStore(artifacts),
        profiles,  # type: ignore[arg-type]
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        context,
    )

    row = _rows_by_id(_report(result))["fixture.report_pass"]
    identity = row["fixture_case_result"]
    assert identity["expected_result_kind"] == expected["result_kind"]
    assert identity["expected_report_schema_id"] == expected["report_schema_id"]
    assert identity["expected_result_fingerprint"] == expected[
        "report_fingerprint"
    ]
    assert identity["actual_result_kind"] == "unavailable"
    assert identity["actual_report_schema_id"] is None
    assert identity["actual_result_fingerprint"] is None
    assert identity["actual_control_failure_stage"] is None
    assert identity["actual_control_failure_code"] is None
    assert identity["actual_control_failure_artifact_role"] is None
    assert identity["result_identity_matches"] is False


def test_fixture_result_field_mismatch_fails_even_when_result_kind_matches(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    assembler_profile: object,
    campaign: CampaignFixture,
) -> None:
    manifest = json.loads(campaign.artifacts[_FIXTURE_REF])
    manifest["expected_result"]["report_fingerprint"] = "sha256:" + "9" * 64
    manifest = _fingerprinted(manifest, "fixture_fingerprint")
    host = copy.deepcopy(campaign.campaign)
    fixture_case = next(
        case for case in host["required_cases"] if case["case_kind"] == "semantic_fixture"
    )
    fixture_case["fixture_case"]["fixture_fingerprint"] = manifest["fixture_fingerprint"]
    fixture_case.update(_fingerprinted(fixture_case, "case_fingerprint"))
    artifacts = dict(campaign.artifacts)
    artifacts[_FIXTURE_REF] = canonical_json_bytes(_owned_object(manifest))
    context = conformance_module._issue_trusted_conformance_fixture_context(
        ImmutableArtifactStore(artifacts),
        (assembler_profile,),
    )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        _reseal_campaign(host),
        context,
    )
    row = _rows_by_id(_report(result))["fixture.report_pass"]
    assert row["outcome"] == "failed"
    assert row["fixture_case_result"]["actual_result_kind"] == "published_report"
    assert row["fixture_case_result"]["result_identity_matches"] is False


def test_semantic_internal_rejected_reservation_is_reported_from_exact_entry(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_conformance_program_contribution(
            alpha_scenario="schema_then_integrity_failure"
        )
    )
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )
    recipe_bytes = b'{"items":[' + b",".join([b"0"] * 10_600) + b"]}"
    fixture = _campaign_fixture(
        program,
        gate_profile,
        assembler_profile,
        recipe_bytes=recipe_bytes,
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )

    report = _report(result)
    row = _rows_by_id(report)["fixture.control_failure_expected"]
    assert len(row["schema_evaluations"]) == 1
    attempt = row["schema_evaluations"][0]
    assert attempt["attempt_status"] == "reservation_rejected"
    assert attempt["failure_code"] == "per_evaluation_limit_exceeded"
    assert attempt["instance_binding"]["artifact_id"] == "synthetic.recipe"
    assert attempt["instance_pointer"] == ""
    assert attempt["instance_fingerprint"] == canonical_fingerprint(
        own_trusted_json(json.loads(recipe_bytes))
    )


def test_final_report_rejected_reservation_uses_content_addressed_candidate(
    assembler_profile: object,
) -> None:
    program = compose_and_seal_program(
        make_conformance_program_contribution(
            alpha_scenario="schema_fill_report_rejection"
        )
    )
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )
    recipe_bytes = b'{"items":[' + b",".join([b"0"] * 10_520) + b"]}"
    fixture = _campaign_fixture(
        program,
        gate_profile,
        assembler_profile,
        recipe_bytes=recipe_bytes,
    )

    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )

    report = _report(result)
    row = _rows_by_id(report)["fixture.control_failure_expected"]
    assert len(row["schema_evaluations"]) == 9
    final_attempt = row["schema_evaluations"][-1]
    assert final_attempt["attempt_status"] == "reservation_rejected"
    assert final_attempt["failure_code"] == "invocation_shape_limit_exceeded"
    assert final_attempt["instance_binding"]["artifact_id"] == (
        "artifact:validation-report-candidate"
    )
    assert final_attempt["instance_binding"]["artifact_fingerprint"] == (
        final_attempt["instance_fingerprint"]
    )
    assert final_attempt["aggregate_before_reservation"] > 0
    assert row["aggregate_schema_evaluation_shape_units"] == final_attempt[
        "aggregate_before_reservation"
    ]


def test_private_audit_lookalike_or_program_mismatch_aborts_the_gate(
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    real = conformance_module._validate_artifacts_with_audit

    def forged(*args: object, **kwargs: object) -> object:
        outcome = real(*args, **kwargs)
        return SimpleNamespace(
            public_result=outcome.public_result,
            audit=SimpleNamespace(
                program_id=program.program_id,  # type: ignore[attr-defined]
                program_fingerprint=program.program_fingerprint,  # type: ignore[attr-defined]
                schema_evaluation_receipts=outcome.audit.schema_evaluation_receipts,
            ),
        )

    monkeypatch.setattr(conformance_module, "_validate_artifacts_with_audit", forged)
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.stage == "gate_execution"
    assert result.code == "gate_execution_failed"
    assert result.campaign_input_sha256 == sha256_prefixed(campaign.campaign_bytes)


def test_missing_or_differently_bound_exact_audit_aborts_the_gate(
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    real = conformance_module._validate_artifacts_with_audit
    calls = 0

    def missing_then_mismatched(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        outcome = real(*args, **kwargs)
        if calls == 1:
            return SimpleNamespace(public_result=outcome.public_result)
        object.__setattr__(outcome.audit, "program_fingerprint", "sha256:" + "7" * 64)
        return outcome

    monkeypatch.setattr(
        conformance_module,
        "_validate_artifacts_with_audit",
        missing_then_mismatched,
    )
    for _ in range(2):
        result = conformance_module.run_conformance_gate(
            gate_profile,
            program,  # type: ignore[arg-type]
            campaign.campaign_bytes,
            campaign.fixture_context,
        )
        assert type(result) is ConformanceGateInvocationFailure
        assert result.code == "gate_execution_failed"
        assert result.trusted_gate_result_issued is False


@pytest.mark.parametrize("mutation", ("receipts", "attempts", "both"))
def test_reordered_kernel_issued_audit_aborts_before_report_publication(
    monkeypatch: pytest.MonkeyPatch,
    assembler_profile: object,
    mutation: str,
) -> None:
    program = compose_and_seal_program(
        make_conformance_program_contribution(alpha_scenario="schema_audit_order")
    )
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(
            conformance_module._execute_conformance_gate
        ),
        conformance_module._execute_conformance_gate,
    )
    fixture = _campaign_fixture(program, gate_profile, assembler_profile)
    real = conformance_module._validate_artifacts_with_audit

    def reordered(*args: object, **kwargs: object) -> object:
        outcome = real(*args, **kwargs)
        receipts = outcome.audit.schema_evaluation_receipts
        attempts = outcome.audit.schema_evaluation_attempts
        if mutation in ("receipts", "both"):
            object.__setattr__(
                outcome.audit,
                "schema_evaluation_receipts",
                tuple(reversed(receipts)),
            )
        if mutation in ("attempts", "both"):
            object.__setattr__(
                outcome.audit,
                "schema_evaluation_attempts",
                tuple(reversed(attempts)),
            )
        return outcome

    monkeypatch.setattr(
        conformance_module,
        "_validate_artifacts_with_audit",
        reordered,
    )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,
        fixture.campaign_bytes,
        fixture.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.code == "gate_execution_failed"
    assert result.report_emitted is False


@pytest.mark.parametrize(
    ("exception_type", "code"),
    (
        (conformance_module._GateIntegrityFailure, "gate_execution_failed"),
        (conformance_module._GateBudgetFailure, "gate_budget_exceeded"),
    ),
)
def test_caught_gate_failures_after_campaign_identity_emit_no_partial_report(
    exception_type: type[Exception],
    code: str,
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise exception_type("forced")

    monkeypatch.setattr(conformance_module, "_execute_campaign_cases", fail)
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.code == code
    assert result.gate_profile_fingerprint == gate_profile.gate_profile_fingerprint
    assert result.program_fingerprint == program.program_fingerprint  # type: ignore[attr-defined]
    assert result.report_emitted is False
    assert result.trusted_gate_result_issued is False


@pytest.mark.parametrize("failure_call", (0, 1, 2))
def test_projection_and_both_report_serializations_fail_atomically(
    failure_call: int,
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    if failure_call == 0:
        def fail_projection(*args: object, **kwargs: object) -> object:
            raise conformance_module._GateReportSealFailure("projection")

        monkeypatch.setattr(
            conformance_module, "_project_aggregate_report", fail_projection
        )
    else:
        real = conformance_module._canonicalize_aggregate_report
        calls = 0

        def fail_serialization(*args: object, **kwargs: object) -> bytes:
            nonlocal calls
            calls += 1
            if calls == failure_call:
                raise conformance_module._GateReportSealFailure("serialization")
            return real(*args, **kwargs)

        monkeypatch.setattr(
            conformance_module,
            "_canonicalize_aggregate_report",
            fail_serialization,
        )
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    assert type(result) is ConformanceGateInvocationFailure
    assert result.stage == "report_seal"
    assert result.code == "gate_report_seal_failed"
    assert result.report_emitted is False
    assert result.trusted_gate_result_issued is False


@pytest.mark.parametrize(
    ("meter_method", "dimension", "limit", "expected_code"),
    (
        (
            "charge_projection_fields",
            BudgetDimension.REPORT_PROJECTION_FIELDS,
            131_072,
            "gate_budget_exceeded",
        ),
        (
            "charge_canonical_bytes",
            BudgetDimension.REPORT_CANONICAL_BYTES,
            2_097_152,
            "gate_report_seal_failed",
        ),
        (
            "_charge_work",
            BudgetDimension.REPORT_SEAL_WORK_UNITS,
            262_144,
            "gate_report_seal_failed",
        ),
    ),
)
def test_aggregate_report_meter_failures_preserve_dimension_classification(
    meter_method: str,
    dimension: BudgetDimension,
    limit: int,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    def exceed(*args: object, **kwargs: object) -> None:
        raise conformance_module._SealMeterExceeded(
            dimension,
            limit,
            limit + 1,
        )

    monkeypatch.setattr(conformance_module.SealMeter, meter_method, exceed)
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )

    assert type(result) is ConformanceGateInvocationFailure
    assert result.stage == "report_seal"
    assert result.code == expected_code
    assert result.report_emitted is False
    assert result.trusted_gate_result_issued is False


def test_completeness_is_case_id_based_and_receipts_duplicate_evidence() -> None:
    required = (
        {"case_id": "a", "case_kind": "core_schema_positive", "case_fingerprint": "fa"},
        {"case_id": "b", "case_kind": "semantic_fixture", "case_fingerprint": "fb"},
    )
    exact = (
        {"result_index": 0, **required[1]},
        {"result_index": 1, **required[0]},
    )
    assert conformance_module._derive_campaign_completeness(required, exact)["complete"] is True

    duplicate = (*exact, {"result_index": 2, **required[0]})
    evidence = conformance_module._derive_campaign_completeness(required, duplicate)
    assert evidence["duplicate_case_ids"] == ["a"]
    assert evidence["result_row_count"] == 3
    assert evidence["complete"] is False

    mismatched = (
        exact[0],
        {**exact[1], "case_kind": "semantic_fixture", "case_fingerprint": "wrong"},
        {"result_index": 2, "case_id": "extra", "case_kind": "semantic_fixture", "case_fingerprint": "fx"},
    )
    evidence = conformance_module._derive_campaign_completeness(required, mismatched)
    assert evidence["extra_case_ids"] == ["extra"]
    assert evidence["case_kind_mismatch_ids"] == ["a"]
    assert evidence["case_fingerprint_mismatch_ids"] == ["a"]
    assert evidence["complete"] is False


def test_campaign_cap_seals_256_full_rows_and_rejects_257(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    baseline_result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    baseline_report = _report(baseline_result)
    template_case = next(
        case
        for case in campaign.campaign["required_cases"]
        if case["case_kind"] == "semantic_fixture"
    )
    template_row = next(
        row
        for row in baseline_report["result_rows"]
        if row["case_kind"] == "semantic_fixture"
    )
    cases: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for index in range(256):
        case = copy.deepcopy(template_case)
        case["case_id"] = f"fixture.campaign_cap.{index:03d}"
        case = _fingerprinted(case, "case_fingerprint")
        row = copy.deepcopy(template_row)
        row.update(
            {
                "result_index": index,
                "case_id": case["case_id"],
                "case_fingerprint": case["case_fingerprint"],
            }
        )
        cases.append(case)
        rows.append(row)

    campaign_256 = copy.deepcopy(campaign.campaign)
    campaign_256["required_cases"] = cases
    campaign_256 = json.loads(_reseal_campaign(campaign_256))
    campaign_schema = Draft202012Validator(
        json.loads(canonical_json_bytes(CONFORMANCE_CAMPAIGN_SCHEMA))
    )
    assert campaign_schema.is_valid(campaign_256)

    projected = conformance_module._project_aggregate_report(
        campaign=campaign_256,
        program=program,
        profile=gate_profile,
        campaign_integrity=baseline_report["campaign_integrity"],
        result_rows=rows,
    )
    sealed = conformance_module._seal_aggregate_report(
        campaign=campaign_256,
        program=program,
        profile=gate_profile,
        campaign_integrity=baseline_report["campaign_integrity"],
        result_rows=rows,
    )
    assert type(sealed) is TrustedConformanceGateResult
    assert conformance_module._count_projection_fields(projected) + 1 <= 131_072
    assert (
        len(canonical_json_bytes(_owned_object(projected)))
        + len(sealed.report_bytes)
        <= 4_194_304
    )
    assert len(json.loads(sealed.report_bytes)["result_rows"]) == 256

    overflow_case = copy.deepcopy(template_case)
    overflow_case["case_id"] = "fixture.campaign_cap.256"
    overflow_case = _fingerprinted(overflow_case, "case_fingerprint")
    campaign_257 = copy.deepcopy(campaign_256)
    campaign_257["required_cases"].append(overflow_case)
    campaign_257 = json.loads(_reseal_campaign(campaign_257))
    errors = tuple(campaign_schema.iter_errors(campaign_257))
    assert errors
    assert any(tuple(error.path) == ("required_cases",) for error in errors)


def test_all_conformance_schemas_are_valid_and_recursively_closed() -> None:
    schemas = (
        CONFORMANCE_GATE_PROFILE_SCHEMA,
        CONFORMANCE_CAMPAIGN_SCHEMA,
        CONFORMANCE_FIXTURE_SCHEMA,
        CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA,
        CONFORMANCE_COMPLETENESS_SCHEMA,
        CONFORMANCE_REPORT_SCHEMA,
    )
    schema_hosts = [json.loads(canonical_json_bytes(schema)) for schema in schemas]
    clean_check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json,sys; "
                "from jsonschema import Draft202012Validator as V; "
                "[V.check_schema(value) for value in json.load(sys.stdin)]"
            ),
        ],
        input=json.dumps(schema_hosts),
        text=True,
        capture_output=True,
        check=False,
    )
    assert clean_check.returncode == 0, clean_check.stderr
    for host in schema_hosts:
        pending = [host]
        while pending:
            value = pending.pop()
            if type(value) is dict:
                if value.get("type") == "object" and "properties" in value:
                    assert value.get("additionalProperties") is False
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)


def test_attempt_schema_mechanically_closes_status_field_relationships() -> None:
    schema = json.loads(canonical_json_bytes(CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA))
    validator = Draft202012Validator(schema)
    fingerprint = "sha256:" + "1" * 64
    completed = {
        "evaluation_index": 0,
        "schema_id": "schema.synthetic:v1",
        "schema_fingerprint": fingerprint,
        "instance_binding": {
            "artifact_id": "artifact:synthetic",
            "artifact_fingerprint": fingerprint,
        },
        "instance_pointer": "",
        "instance_fingerprint": fingerprint,
        "attempt_status": "evaluation_completed",
        "schema_nodes": 1,
        "instance_nodes": 1,
        "attempted_shape_units": 1,
        "per_evaluation_limit": 2_000_000,
        "aggregate_before_reservation": 0,
        "aggregate_after_reservation": 1,
        "evaluator_invoked": True,
        "evaluation_passed": True,
        "failure_code": None,
    }
    assert validator.is_valid(completed)
    rejected = {
        **completed,
        "attempt_status": "reservation_rejected",
        "attempted_shape_units": None,
        "aggregate_after_reservation": None,
        "evaluator_invoked": False,
        "evaluation_passed": None,
        "failure_code": "per_evaluation_limit_exceeded",
    }
    evaluator_failed = {
        **completed,
        "attempt_status": "evaluator_failed",
        "evaluation_passed": None,
        "failure_code": "schema_evaluator_failed",
    }
    assert validator.is_valid(rejected)
    assert validator.is_valid(evaluator_failed)

    adversarial = []
    value = copy.deepcopy(completed)
    value["failure_code"] = "instance_schema_failed"
    adversarial.append(value)
    value = copy.deepcopy(completed)
    value["evaluation_passed"] = False
    adversarial.append(value)
    value = copy.deepcopy(rejected)
    value["failure_code"] = None
    adversarial.append(value)
    value = copy.deepcopy(rejected)
    value["evaluator_invoked"] = True
    adversarial.append(value)
    value = copy.deepcopy(evaluator_failed)
    value["evaluation_passed"] = False
    adversarial.append(value)
    value = copy.deepcopy(evaluator_failed)
    value["failure_code"] = None
    adversarial.append(value)

    for invalid in adversarial:
        assert not validator.is_valid(invalid), invalid


def test_fixture_identity_schema_closes_expected_actual_and_match_variants(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    report = _report(result)
    validator = Draft202012Validator(
        json.loads(canonical_json_bytes(CONFORMANCE_REPORT_SCHEMA))
    )
    assert validator.is_valid(report)
    row_index = next(
        index
        for index, row in enumerate(report["result_rows"])
        if row["case_kind"] == "semantic_fixture"
    )

    def changed(**fields: object) -> dict[str, object]:
        candidate = copy.deepcopy(report)
        identity = candidate["result_rows"][row_index]["fixture_case_result"]
        identity.update(fields)
        return candidate

    invalid_reports = (
        changed(expected_report_schema_id=None),
        changed(expected_control_failure_code="unexpected"),
        changed(actual_report_schema_id=None),
        changed(actual_control_failure_stage="validation"),
        changed(
            actual_result_kind="unavailable",
            actual_report_schema_id="synthetic.report:v1",
            actual_result_fingerprint=None,
            actual_control_failure_stage=None,
            actual_control_failure_code=None,
            actual_control_failure_artifact_role=None,
            result_identity_matches=False,
        ),
        changed(
            actual_result_kind="unavailable",
            actual_report_schema_id=None,
            actual_result_fingerprint=None,
            actual_control_failure_stage=None,
            actual_control_failure_code=None,
            actual_control_failure_artifact_role=None,
            result_identity_matches=True,
        ),
        changed(
            actual_result_kind="control_failure",
            actual_report_schema_id=None,
            actual_result_fingerprint=None,
            actual_control_failure_stage="validation",
            actual_control_failure_code="validator_integrity_failure",
            actual_control_failure_artifact_role="phase_engine",
            result_identity_matches=True,
        ),
        changed(
            expected_result_kind="control_failure",
            expected_report_schema_id="synthetic.report:v1",
            expected_result_fingerprint="sha256:" + "2" * 64,
            expected_control_failure_stage="validation",
            expected_control_failure_code="validator_integrity_failure",
            expected_control_failure_artifact_role="phase_engine",
        ),
    )
    for invalid in invalid_reports:
        assert not validator.is_valid(invalid)


def test_core_result_schema_requires_matching_single_attempt_evidence(
    program: object,
    gate_profile: SealedConformanceGateProfile,
    campaign: CampaignFixture,
) -> None:
    result = conformance_module.run_conformance_gate(
        gate_profile,
        program,  # type: ignore[arg-type]
        campaign.campaign_bytes,
        campaign.fixture_context,
    )
    report = _report(result)
    report_schema = json.loads(canonical_json_bytes(CONFORMANCE_REPORT_SCHEMA))
    row_schema = report_schema["properties"]["result_rows"]["items"]
    validator = Draft202012Validator(row_schema)
    core = copy.deepcopy(
        next(
            row
            for row in report["result_rows"]
            if row["case_kind"] == "core_schema_positive"
        )
    )
    assert validator.is_valid(core)
    successful_attempt = core["schema_evaluations"][0]

    rejected_attempt = {
        **successful_attempt,
        "attempt_status": "reservation_rejected",
        "attempted_shape_units": None,
        "aggregate_after_reservation": None,
        "evaluator_invoked": False,
        "evaluation_passed": None,
        "failure_code": "per_evaluation_limit_exceeded",
    }
    evaluator_failed_attempt = {
        **successful_attempt,
        "attempt_status": "evaluator_failed",
        "evaluation_passed": None,
        "failure_code": "schema_evaluator_failed",
    }
    completed_invalid_attempt = {
        **successful_attempt,
        "evaluation_passed": False,
        "failure_code": "instance_schema_failed",
    }

    honest_rejected = {
        **core,
        "outcome": "failed",
        "schema_case_result": {"instance_schema_valid": None},
        "schema_evaluations": [rejected_attempt],
        "aggregate_schema_evaluation_shape_units": rejected_attempt[
            "aggregate_before_reservation"
        ],
        "within_every_per_evaluation_limit": False,
        "failure_code": "validation_budget_exceeded",
    }
    honest_evaluator_failed = {
        **core,
        "outcome": "failed",
        "schema_case_result": {"instance_schema_valid": None},
        "schema_evaluations": [evaluator_failed_attempt],
        "failure_code": "schema_evaluation_failed",
    }
    honest_completed_invalid = {
        **core,
        "outcome": "failed",
        "schema_case_result": {"instance_schema_valid": False},
        "schema_evaluations": [completed_invalid_attempt],
        "failure_code": "schema_evaluation_failed",
    }
    honest_pre_attempt_failure = {
        **core,
        "outcome": "failed",
        "schema_case_result": {"instance_schema_valid": None},
        "schema_evaluations": [],
        "aggregate_schema_evaluation_shape_units": 0,
        "failure_code": "case_content_unavailable",
    }
    for valid in (
        honest_rejected,
        honest_evaluator_failed,
        honest_completed_invalid,
        honest_pre_attempt_failure,
    ):
        assert validator.is_valid(valid), valid

    impossible = (
        {**core, "schema_evaluations": []},
        {**core, "schema_evaluations": [rejected_attempt]},
        {**core, "schema_evaluations": [evaluator_failed_attempt]},
        {
            **core,
            "schema_case_result": {"instance_schema_valid": False},
        },
        {
            **honest_rejected,
            "failure_code": "schema_evaluation_failed",
        },
        {
            **honest_evaluator_failed,
            "failure_code": "validation_budget_exceeded",
        },
        {
            **honest_completed_invalid,
            "outcome": "passed",
            "failure_code": None,
        },
        {
            **honest_pre_attempt_failure,
            "failure_code": "validation_budget_exceeded",
        },
    )
    for invalid in impossible:
        assert not validator.is_valid(invalid), invalid
