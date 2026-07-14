"""Independent release conformance authority for one sealed validation program."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Literal, Protocol, cast

from jsonschema import Draft202012Validator

from .api import (
    _AuditedValidationOutcome,
    _is_validation_execution_audit,
    _validate_artifacts_with_audit,
)
from .budget import (
    LM9A_BUDGET_MANIFEST,
    BudgetExceeded,
    BudgetLedger,
    SealMeter,
    _SealMeterExceeded,
)
from .canonical_json import (
    CanonicalJsonError,
    canonical_fingerprint,
    canonical_json_bytes,
    sha256_prefixed,
    utf16_sort_key,
)
from .control import ValidationControlFailure
from .invocation import (
    SealedTrustedBundleAssemblerProfile,
    _profile_is_valid,
    _program_is_valid,
    issue_trusted_validation_bundle,
)
from .kernel_schemas import (
    CONFORMANCE_CAMPAIGN_SCHEMA,
    CONFORMANCE_CAMPAIGN_SCHEMA_ID,
    CONFORMANCE_FIXTURE_SCHEMA,
    CONFORMANCE_FIXTURE_SCHEMA_ID,
    CONFORMANCE_GATE_PROFILE_SCHEMA,
    CONFORMANCE_GATE_PROFILE_SCHEMA_ID,
    CONFORMANCE_REPORT_SCHEMA,
    CONFORMANCE_REPORT_SCHEMA_ID,
)
from .owned_json import (
    JsonArray,
    JsonObject,
    JsonValue,
    count_json_nodes,
    own_trusted_json,
)
from .parser import JsonParseError, ParsedJsonValue, parse_owned_json
from .program import SealedValidationProgram, runtime_implementation_fingerprint
from .reporting import PublishedValidationReport
from .schema_profile import (
    CORE_SCHEMA_PROFILE_ID,
    AdmittedSchema,
    InstanceBinding,
    SchemaEvaluationReceipt,
)


CAMPAIGN_INPUT_BYTE_LIMIT = 4_194_304
REFERENCED_CASE_CONTENT_BYTE_LIMIT = 4_194_304
_REPORT_CANONICAL_BYTE_LIMIT = 2_097_152
_INVOCATION_SHAPE_LIMIT = 16_000_000
_GATE_PROFILE_FIELDS = frozenset(
    (
        "schema",
        "gate_profile_id",
        "gate_profile_version",
        "gate_implementation_fingerprint",
        "budget_profile",
        "limits_fingerprint",
        "campaign_input_byte_limit",
        "referenced_case_content_byte_limit",
        "gate_profile_fingerprint",
    )
)
_GATE_PROFILE_ISSUER = object()
_FIXTURE_CONTEXT_ISSUER = object()
_GATE_RESULT_ISSUER = object()


class TrustedImmutableArtifactStore(Protocol):
    def resolve_exact_bytes(self, content_ref: str) -> bytes | None: ...


@dataclass(frozen=True, slots=True, init=False, eq=False)
class SealedConformanceGateProfile:
    schema: str
    gate_profile_id: str
    gate_profile_version: str
    gate_implementation_fingerprint: str
    budget_profile: str
    limits_fingerprint: str
    campaign_input_byte_limit: int
    referenced_case_content_byte_limit: int
    gate_profile_fingerprint: str
    profile_bytes: bytes
    _gate_callable: Callable[..., object]
    _issuer_capability: object

    def __init__(self) -> None:
        raise TypeError("conformance gate profiles are created only by the fixed seal")


@dataclass(frozen=True, slots=True)
class ConformanceGateInvocationFailure:
    stage: str
    code: str
    gate_profile_fingerprint: str | None
    program_fingerprint: str | None
    campaign_input_size: int
    campaign_input_sha256: str | None
    bounded_detail_sha256: str
    report_emitted: Literal[False] = False
    trusted_gate_result_issued: Literal[False] = False


class TrustedConformanceFixtureContext:
    """Opaque release-issued authority over one exact store and profile set."""

    __slots__ = (
        "_artifact_store",
        "_assembler_profiles",
        "_profiles_by_fingerprint",
        "_issuer_capability",
    )

    def __init__(self) -> None:
        raise TypeError("conformance fixture contexts are release-issued")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("conformance fixture contexts are immutable")

    def __copy__(self) -> object:
        raise TypeError("conformance fixture contexts cannot be copied")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("conformance fixture contexts cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("conformance fixture contexts cannot be serialized")


class TrustedConformanceGateResult:
    """Opaque gate-issued carrier for one complete canonical aggregate report."""

    __slots__ = (
        "_report_bytes",
        "_report_fingerprint",
        "_decision",
        "_gate_profile",
        "_issuer_capability",
    )

    def __init__(self) -> None:
        raise TypeError("conformance gate results are gate-issued")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("conformance gate results are immutable")

    @property
    def report_bytes(self) -> bytes:
        return self._report_bytes

    @property
    def report_fingerprint(self) -> str:
        return self._report_fingerprint

    @property
    def decision(self) -> str:
        return self._decision

    def __copy__(self) -> object:
        raise TypeError("conformance gate results cannot be copied")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("conformance gate results cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("conformance gate results cannot be serialized")


class _GateIntegrityFailure(RuntimeError):
    """A trusted gate invariant prevented complete evidence."""


class _GateBudgetFailure(RuntimeError):
    """Gate-controlled work exceeded a fixed sealed limit."""


class _GateReportSealFailure(RuntimeError):
    """Aggregate projection or canonical report sealing failed."""


def _host_value(value: JsonValue) -> object:
    return json.loads(canonical_json_bytes(value))


def _owned_object(value: object) -> JsonObject:
    owned = own_trusted_json(value)
    if type(owned) is not JsonObject:
        raise _GateIntegrityFailure("expected an owned object")
    return owned


def _schema_accepts(value: JsonValue, schema: JsonObject) -> bool:
    try:
        validator = Draft202012Validator(cast(dict[str, object], _host_value(schema)))
        return next(validator.iter_errors(_host_value(value)), None) is None
    except Exception as error:
        raise _GateIntegrityFailure("bootstrap schema validation failed") from error


def _profile_host(
    profile: SealedConformanceGateProfile,
    *,
    include_fingerprint: bool,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": profile.schema,
        "gate_profile_id": profile.gate_profile_id,
        "gate_profile_version": profile.gate_profile_version,
        "gate_implementation_fingerprint": profile.gate_implementation_fingerprint,
        "budget_profile": profile.budget_profile,
        "limits_fingerprint": profile.limits_fingerprint,
        "campaign_input_byte_limit": profile.campaign_input_byte_limit,
        "referenced_case_content_byte_limit": (
            profile.referenced_case_content_byte_limit
        ),
    }
    if include_fingerprint:
        value["gate_profile_fingerprint"] = profile.gate_profile_fingerprint
    return value


def seal_conformance_gate_profile(
    candidate: JsonObject,
    gate_callable: Callable[..., object],
) -> SealedConformanceGateProfile:
    """Seal one closed profile together with one exact release-selected callable."""

    if type(candidate) is not JsonObject:
        raise TypeError("gate profile candidate must be an exact JsonObject")
    if frozenset(candidate) != _GATE_PROFILE_FIELDS:
        raise ValueError("gate profile fields are not exact")
    if not _schema_accepts(candidate, CONFORMANCE_GATE_PROFILE_SCHEMA):
        raise ValueError("gate profile does not satisfy its closed schema")
    try:
        implementation_fingerprint = runtime_implementation_fingerprint(gate_callable)
    except Exception as error:
        raise TypeError("gate callable is not a sealable runtime binding") from error
    host = cast(dict[str, object], _host_value(candidate))
    if implementation_fingerprint != host["gate_implementation_fingerprint"]:
        raise ValueError("gate callable fingerprint does not match the profile")
    if (
        host["budget_profile"] != LM9A_BUDGET_MANIFEST.profile_id
        or host["limits_fingerprint"]
        != LM9A_BUDGET_MANIFEST.limits_fingerprint
        or host["campaign_input_byte_limit"] != CAMPAIGN_INPUT_BYTE_LIMIT
        or host["referenced_case_content_byte_limit"]
        != REFERENCED_CASE_CONTENT_BYTE_LIMIT
    ):
        raise ValueError("gate profile does not bind the fixed LM9A limits")
    asserted_fingerprint = cast(str, host.pop("gate_profile_fingerprint"))
    computed_fingerprint = canonical_fingerprint(_owned_object(host))
    if asserted_fingerprint != computed_fingerprint:
        raise ValueError("gate profile fingerprint mismatch")
    final_host = {**host, "gate_profile_fingerprint": computed_fingerprint}
    final_value = _owned_object(final_host)
    sealed = object.__new__(SealedConformanceGateProfile)
    for field_name, value in final_host.items():
        object.__setattr__(sealed, field_name, value)
    object.__setattr__(sealed, "profile_bytes", canonical_json_bytes(final_value))
    object.__setattr__(sealed, "_gate_callable", gate_callable)
    object.__setattr__(sealed, "_issuer_capability", _GATE_PROFILE_ISSUER)
    return sealed


def _gate_profile_status(profile: object) -> str:
    if type(profile) is not SealedConformanceGateProfile:
        return "not_sealed"
    try:
        if profile._issuer_capability is not _GATE_PROFILE_ISSUER:
            return "not_sealed"
        unsigned = _owned_object(_profile_host(profile, include_fingerprint=False))
        if canonical_fingerprint(unsigned) != profile.gate_profile_fingerprint:
            return "runtime_invalid"
        final = _owned_object(_profile_host(profile, include_fingerprint=True))
        if canonical_json_bytes(final) != profile.profile_bytes:
            return "runtime_invalid"
        if (
            runtime_implementation_fingerprint(profile._gate_callable)
            != profile.gate_implementation_fingerprint
        ):
            return "runtime_invalid"
        if not _schema_accepts(final, CONFORMANCE_GATE_PROFILE_SCHEMA):
            return "runtime_invalid"
        return "valid"
    except Exception:
        return "runtime_invalid"


def _issue_trusted_conformance_fixture_context(
    artifact_store: TrustedImmutableArtifactStore,
    assembler_profiles: tuple[SealedTrustedBundleAssemblerProfile, ...],
) -> TrustedConformanceFixtureContext:
    if not callable(getattr(artifact_store, "resolve_exact_bytes", None)):
        raise TypeError("fixture context requires an immutable artifact store")
    if type(assembler_profiles) is not tuple or any(
        not _profile_is_valid(profile) for profile in assembler_profiles
    ):
        raise TypeError("fixture context requires exact sealed assembler profiles")
    by_fingerprint: dict[str, SealedTrustedBundleAssemblerProfile] = {}
    for profile in assembler_profiles:
        if profile.profile_fingerprint in by_fingerprint:
            raise ValueError("duplicate assembler profile fingerprint")
        by_fingerprint[profile.profile_fingerprint] = profile
    context = object.__new__(TrustedConformanceFixtureContext)
    object.__setattr__(context, "_artifact_store", artifact_store)
    object.__setattr__(context, "_assembler_profiles", assembler_profiles)
    object.__setattr__(
        context,
        "_profiles_by_fingerprint",
        MappingProxyType(by_fingerprint),
    )
    object.__setattr__(context, "_issuer_capability", _FIXTURE_CONTEXT_ISSUER)
    return context


def _capture_fixture_context(
    value: object,
) -> tuple[
    TrustedImmutableArtifactStore,
    MappingProxyType[str, SealedTrustedBundleAssemblerProfile],
] | None:
    if type(value) is not TrustedConformanceFixtureContext:
        return None
    try:
        if value._issuer_capability is not _FIXTURE_CONTEXT_ISSUER:
            return None
        profiles = value._assembler_profiles
        by_fingerprint = value._profiles_by_fingerprint
        store = value._artifact_store
        if (
            type(profiles) is not tuple
            or type(by_fingerprint) is not MappingProxyType
            or not callable(getattr(store, "resolve_exact_bytes", None))
        ):
            return None
        for profile in profiles:
            if (
                not _profile_is_valid(profile)
                or by_fingerprint.get(profile.profile_fingerprint) is not profile
            ):
                return None
        return store, by_fingerprint
    except Exception:
        return None


def _failure(
    *,
    stage: str,
    code: str,
    gate_profile_fingerprint: str | None,
    program_fingerprint: str | None,
    campaign_input_size: int,
    campaign_input_sha256: str | None,
    detail: str,
) -> ConformanceGateInvocationFailure:
    bounded = (stage + "\0" + code + "\0" + detail[:256]).encode("utf-8")
    return ConformanceGateInvocationFailure(
        stage=stage,
        code=code,
        gate_profile_fingerprint=gate_profile_fingerprint,
        program_fingerprint=program_fingerprint,
        campaign_input_size=campaign_input_size,
        campaign_input_sha256=campaign_input_sha256,
        bounded_detail_sha256=sha256_prefixed(bounded),
    )


def _issue_gate_result(
    *,
    report_bytes: bytes,
    report_fingerprint: str,
    decision: str,
    gate_profile: SealedConformanceGateProfile,
) -> TrustedConformanceGateResult:
    result = object.__new__(TrustedConformanceGateResult)
    object.__setattr__(result, "_report_bytes", report_bytes)
    object.__setattr__(result, "_report_fingerprint", report_fingerprint)
    object.__setattr__(result, "_decision", decision)
    object.__setattr__(result, "_gate_profile", gate_profile)
    object.__setattr__(result, "_issuer_capability", _GATE_RESULT_ISSUER)
    return result


def _gate_result_is_valid(
    result: object,
    profile: SealedConformanceGateProfile,
) -> bool:
    try:
        return (
            type(result) is TrustedConformanceGateResult
            and result._issuer_capability is _GATE_RESULT_ISSUER
            and result._gate_profile is profile
            and type(result._report_bytes) is bytes
            and type(result._report_fingerprint) is str
            and result._decision in ("passed", "failed")
        )
    except Exception:
        return False


def run_conformance_gate(
    gate_profile: SealedConformanceGateProfile,
    program: SealedValidationProgram,
    raw_campaign_bytes: bytes,
    fixture_context: TrustedConformanceFixtureContext,
) -> TrustedConformanceGateResult | ConformanceGateInvocationFailure:
    """Capture release authority first, then invoke its exact bound gate."""

    input_size = len(raw_campaign_bytes) if type(raw_campaign_bytes) is bytes else 0
    profile_status = _gate_profile_status(gate_profile)
    if profile_status != "valid":
        return _failure(
            stage="gate_authority",
            code=(
                "gate_profile_not_sealed"
                if profile_status == "not_sealed"
                else "gate_profile_runtime_binding_invalid"
            ),
            gate_profile_fingerprint=None,
            program_fingerprint=None,
            campaign_input_size=input_size,
            campaign_input_sha256=None,
            detail=profile_status,
        )
    selected_profile = gate_profile
    selected_callable = gate_profile._gate_callable
    captured_context = _capture_fixture_context(fixture_context)
    if captured_context is None:
        return _failure(
            stage="gate_authority",
            code="gate_execution_failed",
            gate_profile_fingerprint=selected_profile.gate_profile_fingerprint,
            program_fingerprint=None,
            campaign_input_size=input_size,
            campaign_input_sha256=None,
            detail="fixture_context_invalid",
        )
    if not _program_is_valid(program):
        return _failure(
            stage="program_authority",
            code=(
                "program_not_sealed"
                if type(program) is not SealedValidationProgram
                else "program_runtime_binding_invalid"
            ),
            gate_profile_fingerprint=selected_profile.gate_profile_fingerprint,
            program_fingerprint=None,
            campaign_input_size=input_size,
            campaign_input_sha256=None,
            detail="program_authority_invalid",
        )
    if type(raw_campaign_bytes) is not bytes:
        return _failure(
            stage="campaign_admission",
            code="campaign_content_unavailable",
            gate_profile_fingerprint=selected_profile.gate_profile_fingerprint,
            program_fingerprint=program.program_fingerprint,
            campaign_input_size=0,
            campaign_input_sha256=None,
            detail="campaign_not_exact_bytes",
        )
    try:
        result = selected_callable(
            selected_profile,
            program,
            raw_campaign_bytes,
            captured_context,
        )
    except Exception:
        campaign_hash = (
            sha256_prefixed(raw_campaign_bytes)
            if len(raw_campaign_bytes) <= selected_profile.campaign_input_byte_limit
            else None
        )
        return _failure(
            stage="gate_execution",
            code="gate_execution_failed",
            gate_profile_fingerprint=selected_profile.gate_profile_fingerprint,
            program_fingerprint=program.program_fingerprint,
            campaign_input_size=len(raw_campaign_bytes),
            campaign_input_sha256=campaign_hash,
            detail="bound_gate_callable_failed",
        )
    if type(result) is ConformanceGateInvocationFailure:
        return result
    if _gate_result_is_valid(result, selected_profile):
        return result
    return _failure(
        stage="gate_execution",
        code="gate_execution_failed",
        gate_profile_fingerprint=selected_profile.gate_profile_fingerprint,
        program_fingerprint=program.program_fingerprint,
        campaign_input_size=len(raw_campaign_bytes),
        campaign_input_sha256=(
            sha256_prefixed(raw_campaign_bytes)
            if len(raw_campaign_bytes) <= selected_profile.campaign_input_byte_limit
            else None
        ),
        detail="bound_gate_return_invalid",
    )


def _parse_gate_json(raw: bytes, artifact_role: str) -> ParsedJsonValue:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    parser_role = "recipe" if "recipe" in artifact_role else "validation_bundle"
    return parse_owned_json(raw, artifact_role=parser_role, ledger=ledger)


def _campaign_identity_error(campaign: dict[str, object]) -> str | None:
    cases = cast(list[dict[str, object]], campaign["required_cases"])
    case_ids = [cast(str, case["case_id"]) for case in cases]
    case_fingerprints = [cast(str, case["case_fingerprint"]) for case in cases]
    if case_ids != sorted(case_ids, key=utf16_sort_key):
        return "campaign_schema_failed"
    if len(case_ids) != len(set(case_ids)) or len(case_fingerprints) != len(
        set(case_fingerprints)
    ):
        return "campaign_schema_failed"
    for case in cases:
        asserted = cast(str, case["case_fingerprint"])
        unsigned = {key: value for key, value in case.items() if key != "case_fingerprint"}
        if canonical_fingerprint(_owned_object(unsigned)) != asserted:
            return "campaign_fingerprint_mismatch"
    pairs = [
        {
            "case_id": case["case_id"],
            "case_fingerprint": case["case_fingerprint"],
        }
        for case in cases
    ]
    if canonical_fingerprint(own_trusted_json(pairs)) != campaign[
        "required_case_set_fingerprint"
    ]:
        return "campaign_case_set_fingerprint_mismatch"
    asserted_campaign = cast(str, campaign["campaign_fingerprint"])
    unsigned_campaign = {
        key: value
        for key, value in campaign.items()
        if key != "campaign_fingerprint"
    }
    if canonical_fingerprint(_owned_object(unsigned_campaign)) != asserted_campaign:
        return "campaign_fingerprint_mismatch"
    return None


def _derive_campaign_integrity(
    campaign: dict[str, object],
    profile: SealedConformanceGateProfile,
    program: SealedValidationProgram,
) -> dict[str, object]:
    program_matches = (
        campaign["program_id"] == program.program_id
        and campaign["program_fingerprint"] == program.program_fingerprint
    )
    gate_matches = (
        campaign["required_gate_profile_fingerprint"]
        == profile.gate_profile_fingerprint
    )
    required_core_ids = {
        schema.schema_id
        for schema in program.schemas
        if schema.profile_id == CORE_SCHEMA_PROFILE_ID
    }
    campaign_core_ids = {
        cast(dict[str, object], case["schema_case"])["schema_id"]
        for case in cast(list[dict[str, object]], campaign["required_cases"])
        if case["case_kind"] == "core_schema_positive"
    }
    missing = sorted(required_core_ids - campaign_core_ids, key=utf16_sort_key)
    extra = sorted(campaign_core_ids - required_core_ids, key=utf16_sort_key)
    failures: list[str] = []
    if not program_matches:
        failures.append("campaign_program_binding_mismatch")
    if not gate_matches:
        failures.append("campaign_gate_profile_binding_mismatch")
    if missing:
        failures.append("campaign_core_schema_coverage_missing")
    if extra:
        failures.append("campaign_core_schema_coverage_extra")
    return {
        "program_binding_matches": program_matches,
        "gate_profile_binding_matches": gate_matches,
        "core_schema_coverage_matches_program": not missing and not extra,
        "missing_core_schema_case_ids": missing,
        "extra_core_schema_case_ids": extra,
        "failure_codes": failures,
        "passed": not failures,
    }


def _resolve_case_bytes(
    store: TrustedImmutableArtifactStore,
    content_ref: str,
) -> bytes | None:
    try:
        raw = store.resolve_exact_bytes(content_ref)
    except Exception:
        return None
    if type(raw) is not bytes or len(raw) > REFERENCED_CASE_CONTENT_BYTE_LIMIT:
        return None
    return memoryview(raw).tobytes()


def _profile_for_schema(program: SealedValidationProgram, schema: AdmittedSchema) -> object:
    for evaluator_spec in program.schema_evaluator_profiles:
        if evaluator_spec.profile.profile_id == schema.profile_id:
            return evaluator_spec
    raise _GateIntegrityFailure("schema evaluator profile is unavailable")


def _attempt_row(
    *,
    evaluation_index: int,
    schema: AdmittedSchema,
    instance_binding: InstanceBinding,
    instance: JsonValue,
    receipt: SchemaEvaluationReceipt,
    per_evaluation_limit: int,
) -> dict[str, object]:
    reservation = receipt.reservation
    if not reservation.accepted:
        status = "reservation_rejected"
        attempted = None
        aggregate_after = None
    elif receipt.evaluator_invoked and receipt.evaluation_passed is not None:
        status = "evaluation_completed"
        attempted = reservation.attempted_shape_units
        aggregate_after = reservation.aggregate_after
    elif receipt.evaluator_invoked:
        status = "evaluator_failed"
        attempted = reservation.attempted_shape_units
        aggregate_after = reservation.aggregate_after
    else:
        raise _GateIntegrityFailure("schema receipt has an invalid status")
    return {
        "evaluation_index": evaluation_index,
        "schema_id": schema.schema_id,
        "schema_fingerprint": schema.schema_fingerprint,
        "instance_binding": {
            "artifact_id": instance_binding.artifact_id,
            "artifact_fingerprint": instance_binding.artifact_fingerprint,
        },
        "instance_pointer": instance_binding.instance_pointer,
        "instance_fingerprint": canonical_fingerprint(instance),
        "attempt_status": status,
        "schema_nodes": schema.schema_nodes,
        "instance_nodes": count_json_nodes(instance),
        "attempted_shape_units": attempted,
        "per_evaluation_limit": per_evaluation_limit,
        "aggregate_before_reservation": reservation.aggregate_before,
        "aggregate_after_reservation": aggregate_after,
        "evaluator_invoked": receipt.evaluator_invoked,
        "evaluation_passed": receipt.evaluation_passed,
        "failure_code": receipt.failure_code,
    }


def _attempt_summary(attempts: list[dict[str, object]]) -> tuple[int, bool, bool]:
    aggregate = 0
    within_per_evaluation = True
    within_invocation = True
    for attempt in attempts:
        after = attempt["aggregate_after_reservation"]
        if type(after) is int:
            aggregate = after
        failure_code = attempt["failure_code"]
        if failure_code == "per_evaluation_limit_exceeded":
            within_per_evaluation = False
        elif failure_code == "invocation_shape_limit_exceeded":
            within_invocation = False
        elif failure_code == "shape_product_overflow":
            within_per_evaluation = False
            within_invocation = False
    return aggregate, within_per_evaluation, within_invocation


def _failed_row(
    case: dict[str, object],
    *,
    failure_code: str,
    schema_case_result: dict[str, object] | None,
    fixture_case_result: dict[str, object] | None,
    attempts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    actual_attempts = [] if attempts is None else attempts
    aggregate, within_per, within_invocation = _attempt_summary(actual_attempts)
    return {
        "result_index": -1,
        "case_id": case["case_id"],
        "case_kind": case["case_kind"],
        "case_fingerprint": case["case_fingerprint"],
        "outcome": "failed",
        "schema_case_result": schema_case_result,
        "fixture_case_result": fixture_case_result,
        "schema_evaluations": actual_attempts,
        "aggregate_schema_evaluation_shape_units": aggregate,
        "invocation_shape_limit": _INVOCATION_SHAPE_LIMIT,
        "within_every_per_evaluation_limit": within_per,
        "within_invocation_limit": within_invocation,
        "failure_code": failure_code,
    }


def _execute_core_case(
    case: dict[str, object],
    program: SealedValidationProgram,
    store: TrustedImmutableArtifactStore,
    schema_ledger: BudgetLedger,
) -> dict[str, object]:
    schema_case = cast(dict[str, object], case["schema_case"])
    schema = next(
        (
            candidate
            for candidate in program.schemas
            if candidate.schema_id == schema_case["schema_id"]
            and candidate.schema_fingerprint == schema_case["schema_fingerprint"]
            and candidate.profile_id == CORE_SCHEMA_PROFILE_ID
        ),
        None,
    )
    if schema is None:
        return _failed_row(
            case,
            failure_code="case_execution_failed",
            schema_case_result={"instance_schema_valid": None},
            fixture_case_result=None,
        )
    content_ref = cast(str, schema_case["instance_content_ref"])
    raw = _resolve_case_bytes(store, content_ref)
    if raw is None:
        return _failed_row(
            case,
            failure_code="case_content_unavailable",
            schema_case_result={"instance_schema_valid": None},
            fixture_case_result=None,
        )
    try:
        parsed = _parse_gate_json(raw, "conformance_core_instance")
    except (BudgetExceeded, JsonParseError):
        return _failed_row(
            case,
            failure_code="case_execution_failed",
            schema_case_result={"instance_schema_valid": None},
            fixture_case_result=None,
        )
    if parsed.value_fingerprint != schema_case["instance_fingerprint"]:
        return _failed_row(
            case,
            failure_code="case_fingerprint_mismatch",
            schema_case_result={"instance_schema_valid": None},
            fixture_case_result=None,
        )
    evaluator_spec = _profile_for_schema(program, schema)
    evaluator = program.resolve_runtime_binding(
        "schema_evaluator", evaluator_spec.evaluator.component_id
    )
    if (
        runtime_implementation_fingerprint(evaluator)
        != evaluator_spec.evaluator.implementation_fingerprint
    ):
        raise _GateIntegrityFailure("schema evaluator binding changed")
    binding = InstanceBinding(
        artifact_id=content_ref,
        artifact_fingerprint=parsed.value_fingerprint,
        instance_pointer="",
    )
    receipt = evaluator(
        schema,
        parsed.value,
        instance_binding=binding,
        ledger=schema_ledger,
    )
    if type(receipt) is not SchemaEvaluationReceipt:
        raise _GateIntegrityFailure("schema evaluator returned no exact receipt")
    attempt = _attempt_row(
        evaluation_index=0,
        schema=schema,
        instance_binding=binding,
        instance=parsed.value,
        receipt=receipt,
        per_evaluation_limit=evaluator_spec.profile.per_evaluation_shape_limit,
    )
    completed = attempt["attempt_status"] == "evaluation_completed"
    instance_valid = attempt["evaluation_passed"] if completed else None
    if attempt["attempt_status"] == "reservation_rejected":
        failure_code = "validation_budget_exceeded"
    elif not completed or instance_valid is not True:
        failure_code = "schema_evaluation_failed"
    else:
        failure_code = None
    if failure_code is not None:
        return _failed_row(
            case,
            failure_code=failure_code,
            schema_case_result={"instance_schema_valid": instance_valid},
            fixture_case_result=None,
            attempts=[attempt],
        )
    aggregate, within_per, within_invocation = _attempt_summary([attempt])
    return {
        "result_index": -1,
        "case_id": case["case_id"],
        "case_kind": case["case_kind"],
        "case_fingerprint": case["case_fingerprint"],
        "outcome": "passed",
        "schema_case_result": {"instance_schema_valid": True},
        "fixture_case_result": None,
        "schema_evaluations": [attempt],
        "aggregate_schema_evaluation_shape_units": aggregate,
        "invocation_shape_limit": _INVOCATION_SHAPE_LIMIT,
        "within_every_per_evaluation_limit": within_per,
        "within_invocation_limit": within_invocation,
        "failure_code": None,
    }


def _expected_fixture_identity(expected: dict[str, object]) -> dict[str, object]:
    return {
        "expected_result_kind": expected["result_kind"],
        "expected_report_schema_id": expected["report_schema_id"],
        "expected_result_fingerprint": expected["report_fingerprint"],
        "expected_control_failure_stage": expected["control_failure_stage"],
        "expected_control_failure_code": expected["control_failure_code"],
        "expected_control_failure_artifact_role": expected[
            "control_failure_artifact_role"
        ],
    }


def _actual_fixture_identity(result: object) -> dict[str, object]:
    if type(result) is PublishedValidationReport:
        return {
            "actual_result_kind": "published_report",
            "actual_report_schema_id": result.schema_id,
            "actual_result_fingerprint": result.report_fingerprint,
            "actual_control_failure_stage": None,
            "actual_control_failure_code": None,
            "actual_control_failure_artifact_role": None,
        }
    if isinstance(result, ValidationControlFailure):
        return {
            "actual_result_kind": "control_failure",
            "actual_report_schema_id": None,
            "actual_result_fingerprint": None,
            "actual_control_failure_stage": result.failure_stage,
            "actual_control_failure_code": result.code,
            "actual_control_failure_artifact_role": result.artifact_role,
        }
    return {
        "actual_result_kind": "unavailable",
        "actual_report_schema_id": None,
        "actual_result_fingerprint": None,
        "actual_control_failure_stage": None,
        "actual_control_failure_code": None,
        "actual_control_failure_artifact_role": None,
    }


def _fixture_identity_result(
    expected: dict[str, object],
    actual_result: object,
) -> dict[str, object]:
    expected_identity = _expected_fixture_identity(expected)
    actual_identity = _actual_fixture_identity(actual_result)
    expected_signature = (
        expected_identity["expected_result_kind"],
        expected_identity["expected_report_schema_id"],
        expected_identity["expected_result_fingerprint"],
        expected_identity["expected_control_failure_stage"],
        expected_identity["expected_control_failure_code"],
        expected_identity["expected_control_failure_artifact_role"],
    )
    actual_signature = (
        actual_identity["actual_result_kind"],
        actual_identity["actual_report_schema_id"],
        actual_identity["actual_result_fingerprint"],
        actual_identity["actual_control_failure_stage"],
        actual_identity["actual_control_failure_code"],
        actual_identity["actual_control_failure_artifact_role"],
    )
    return {
        **expected_identity,
        **actual_identity,
        "result_identity_matches": expected_signature == actual_signature,
    }


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _walk_instances(root: JsonValue) -> tuple[tuple[str, JsonValue], ...]:
    found: list[tuple[str, JsonValue]] = []
    stack: list[tuple[str, JsonValue]] = [("", root)]
    while stack:
        pointer, value = stack.pop()
        found.append((pointer, value))
        if type(value) is JsonObject:
            for key, child in reversed(value.members):
                stack.append((pointer + "/" + _pointer_token(str(key)), child))
        elif type(value) is JsonArray:
            for index in range(len(value.items) - 1, -1, -1):
                stack.append((pointer + "/" + str(index), value.items[index]))
    return tuple(found)


def _map_internal_audit_receipt(
    receipt: SchemaEvaluationReceipt,
    *,
    evaluation_index: int,
    program: SealedValidationProgram,
    parsed_roots: tuple[tuple[str, ParsedJsonValue], ...],
) -> dict[str, object]:
    attempted = receipt.reservation.attempted_shape_units
    if attempted is None:
        raise _GateIntegrityFailure("rejected semantic receipt lacks bound identity")
    candidates: list[tuple[AdmittedSchema, str, str, str, JsonValue, object]] = []
    for schema in program.schemas:
        evaluator_spec = _profile_for_schema(program, schema)
        for artifact_id, parsed in parsed_roots:
            for pointer, instance in _walk_instances(parsed.value):
                if schema.schema_nodes * count_json_nodes(instance) == attempted:
                    candidates.append(
                        (
                            schema,
                            artifact_id,
                            parsed.value_fingerprint,
                            pointer,
                            instance,
                            evaluator_spec,
                        )
                    )
    if len(candidates) != 1:
        raise _GateIntegrityFailure("semantic audit identity is not uniquely recoverable")
    schema, artifact_id, artifact_fingerprint, pointer, instance, evaluator_spec = (
        candidates[0]
    )
    binding = InstanceBinding(
        artifact_id=artifact_id,
        artifact_fingerprint=artifact_fingerprint,
        instance_pointer=pointer,
    )
    return _attempt_row(
        evaluation_index=evaluation_index,
        schema=schema,
        instance_binding=binding,
        instance=instance,
        receipt=receipt,
        per_evaluation_limit=evaluator_spec.profile.per_evaluation_shape_limit,
    )


def _semantic_attempt_rows(
    outcome: _AuditedValidationOutcome,
    *,
    program: SealedValidationProgram,
    recipe_ref: str,
    recipe_bytes: bytes,
    bundle_ref: str,
    bundle_bytes: bytes,
) -> list[dict[str, object]]:
    if not _is_validation_execution_audit(outcome.audit, program):
        raise _GateIntegrityFailure("semantic validation audit is not authentic")
    receipts = outcome.audit.schema_evaluation_receipts
    attempts: list[dict[str, object]] = []
    report_receipt: SchemaEvaluationReceipt | None = None
    internal_receipts = receipts
    if type(outcome.public_result) is PublishedValidationReport:
        if not receipts:
            raise _GateIntegrityFailure("published report audit is missing")
        report_receipt = receipts[-1]
        internal_receipts = receipts[:-1]
    parsed_roots: list[tuple[str, ParsedJsonValue]] = []
    for artifact_id, raw, role in (
        (recipe_ref, recipe_bytes, "conformance_fixture_recipe_identity"),
        (bundle_ref, bundle_bytes, "conformance_fixture_bundle_identity"),
    ):
        try:
            parsed_roots.append((artifact_id, _parse_gate_json(raw, role)))
        except (BudgetExceeded, JsonParseError):
            continue
    for index, receipt in enumerate(internal_receipts):
        attempts.append(
            _map_internal_audit_receipt(
                receipt,
                evaluation_index=index,
                program=program,
                parsed_roots=tuple(parsed_roots),
            )
        )
    if report_receipt is not None:
        report = cast(PublishedValidationReport, outcome.public_result)
        schema = next(
            (
                candidate
                for candidate in program.schemas
                if candidate.schema_id == report.schema_id
                and candidate.schema_fingerprint
                == program.report_projection.output_schema_fingerprint
            ),
            None,
        )
        if schema is None:
            raise _GateIntegrityFailure("published report schema is unavailable")
        expected_units = schema.schema_nodes * count_json_nodes(report.value)
        if report_receipt.reservation.attempted_shape_units != expected_units:
            raise _GateIntegrityFailure("published report audit is reordered or mismatched")
        evaluator_spec = _profile_for_schema(program, schema)
        binding = InstanceBinding(
            artifact_id="artifact:validation-report",
            artifact_fingerprint=report.report_fingerprint,
            instance_pointer="",
        )
        attempts.append(
            _attempt_row(
                evaluation_index=len(attempts),
                schema=schema,
                instance_binding=binding,
                instance=report.value,
                receipt=report_receipt,
                per_evaluation_limit=evaluator_spec.profile.per_evaluation_shape_limit,
            )
        )
    return attempts


def _execute_fixture_case(
    case: dict[str, object],
    program: SealedValidationProgram,
    store: TrustedImmutableArtifactStore,
    profiles: MappingProxyType[str, SealedTrustedBundleAssemblerProfile],
) -> dict[str, object]:
    fixture_case = cast(dict[str, object], case["fixture_case"])
    fixture_ref = cast(str, fixture_case["fixture_content_ref"])
    fixture_raw = _resolve_case_bytes(store, fixture_ref)
    unavailable_identity = _fixture_identity_result(
        {
            "result_kind": "control_failure",
            "report_schema_id": None,
            "report_fingerprint": None,
            "control_failure_stage": "preflight",
            "control_failure_code": "validation_input_invalid",
            "control_failure_artifact_role": "combined",
        },
        object(),
    )
    if fixture_raw is None:
        return _failed_row(
            case,
            failure_code="case_content_unavailable",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    try:
        parsed_fixture = _parse_gate_json(
            fixture_raw, "conformance_fixture_manifest"
        )
    except (BudgetExceeded, JsonParseError):
        return _failed_row(
            case,
            failure_code="case_execution_failed",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    if (
        type(parsed_fixture.value) is not JsonObject
        or not _schema_accepts(parsed_fixture.value, CONFORMANCE_FIXTURE_SCHEMA)
    ):
        return _failed_row(
            case,
            failure_code="case_execution_failed",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    fixture = cast(dict[str, object], _host_value(parsed_fixture.value))
    asserted_fixture = cast(str, fixture["fixture_fingerprint"])
    unsigned_fixture = {
        key: value for key, value in fixture.items() if key != "fixture_fingerprint"
    }
    if (
        canonical_fingerprint(_owned_object(unsigned_fixture)) != asserted_fixture
        or asserted_fixture != fixture_case["fixture_fingerprint"]
        or fixture["fixture_id"] != case["case_id"]
    ):
        return _failed_row(
            case,
            failure_code="case_fingerprint_mismatch",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    recipe_descriptor = cast(dict[str, object], fixture["recipe_input"])
    bundle_descriptor = cast(
        dict[str, object], fixture["validation_bundle_input"]
    )
    assembler_fingerprint = cast(str, fixture["assembler_profile_fingerprint"])
    if (
        recipe_descriptor["input_payload_sha256"]
        != fixture_case["recipe_input_payload_sha256"]
        or bundle_descriptor["input_payload_sha256"]
        != fixture_case["validation_bundle_input_payload_sha256"]
        or assembler_fingerprint
        != fixture_case["assembler_profile_fingerprint"]
    ):
        return _failed_row(
            case,
            failure_code="case_fingerprint_mismatch",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    recipe_ref = cast(str, recipe_descriptor["content_ref"])
    bundle_ref = cast(str, bundle_descriptor["content_ref"])
    recipe_raw = _resolve_case_bytes(store, recipe_ref)
    bundle_raw = _resolve_case_bytes(store, bundle_ref)
    if recipe_raw is None or bundle_raw is None:
        return _failed_row(
            case,
            failure_code="case_content_unavailable",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    if (
        sha256_prefixed(recipe_raw) != recipe_descriptor["input_payload_sha256"]
        or sha256_prefixed(bundle_raw)
        != bundle_descriptor["input_payload_sha256"]
    ):
        return _failed_row(
            case,
            failure_code="case_fingerprint_mismatch",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    profile = profiles.get(assembler_fingerprint)
    if profile is None or not _profile_is_valid(profile):
        return _failed_row(
            case,
            failure_code="case_execution_failed",
            schema_case_result=None,
            fixture_case_result=unavailable_identity,
        )
    try:
        trusted_bundle = issue_trusted_validation_bundle(profile, bundle_raw)
        outcome = _validate_artifacts_with_audit(
            program, recipe_raw, trusted_bundle
        )
    except Exception as error:
        raise _GateIntegrityFailure("semantic fixture invocation failed") from error
    if type(outcome) is not _AuditedValidationOutcome:
        raise _GateIntegrityFailure("semantic fixture returned no audited outcome")
    attempts = _semantic_attempt_rows(
        outcome,
        program=program,
        recipe_ref=recipe_ref,
        recipe_bytes=recipe_raw,
        bundle_ref=bundle_ref,
        bundle_bytes=bundle_raw,
    )
    expected = cast(dict[str, object], fixture["expected_result"])
    identity = _fixture_identity_result(expected, outcome.public_result)
    aggregate, within_per, within_invocation = _attempt_summary(attempts)
    passed = bool(identity["result_identity_matches"] and within_per and within_invocation)
    if passed:
        failure_code = None
    elif not within_per or not within_invocation:
        failure_code = "validation_budget_exceeded"
    else:
        failure_code = "case_execution_failed"
    return {
        "result_index": -1,
        "case_id": case["case_id"],
        "case_kind": case["case_kind"],
        "case_fingerprint": case["case_fingerprint"],
        "outcome": "passed" if passed else "failed",
        "schema_case_result": None,
        "fixture_case_result": identity,
        "schema_evaluations": attempts,
        "aggregate_schema_evaluation_shape_units": aggregate,
        "invocation_shape_limit": _INVOCATION_SHAPE_LIMIT,
        "within_every_per_evaluation_limit": within_per,
        "within_invocation_limit": within_invocation,
        "failure_code": failure_code,
    }


def _execute_campaign_cases(
    campaign: dict[str, object],
    program: SealedValidationProgram,
    captured_context: tuple[
        TrustedImmutableArtifactStore,
        MappingProxyType[str, SealedTrustedBundleAssemblerProfile],
    ],
) -> list[dict[str, object]]:
    store, profiles = captured_context
    schema_ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    rows: list[dict[str, object]] = []
    cases = cast(list[dict[str, object]], campaign["required_cases"])
    for result_index, case in enumerate(cases):
        if case["case_kind"] == "core_schema_positive":
            row = _execute_core_case(case, program, store, schema_ledger)
        else:
            row = _execute_fixture_case(case, program, store, profiles)
        row["result_index"] = result_index
        rows.append(row)
    return rows


def _derive_campaign_completeness(
    required_cases: object,
    result_rows: object,
) -> dict[str, object]:
    required = cast(tuple[dict[str, object], ...], tuple(required_cases))
    rows = cast(tuple[dict[str, object], ...], tuple(result_rows))
    required_by_id = {cast(str, case["case_id"]): case for case in required}
    rows_by_id: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        rows_by_id.setdefault(cast(str, row["case_id"]), []).append(row)
    required_ids = set(required_by_id)
    row_ids = set(rows_by_id)
    missing = sorted(required_ids - row_ids, key=utf16_sort_key)
    extra = sorted(row_ids - required_ids, key=utf16_sort_key)
    duplicate = sorted(
        (case_id for case_id, matches in rows_by_id.items() if len(matches) > 1),
        key=utf16_sort_key,
    )
    kind_mismatch: list[str] = []
    fingerprint_mismatch: list[str] = []
    for case_id in required_ids & row_ids:
        expected = required_by_id[case_id]
        matches = rows_by_id[case_id]
        if any(row["case_kind"] != expected["case_kind"] for row in matches):
            kind_mismatch.append(case_id)
        if any(
            row["case_fingerprint"] != expected["case_fingerprint"]
            for row in matches
        ):
            fingerprint_mismatch.append(case_id)
    kind_mismatch.sort(key=utf16_sort_key)
    fingerprint_mismatch.sort(key=utf16_sort_key)
    complete = not (
        missing or extra or duplicate or kind_mismatch or fingerprint_mismatch
    ) and len(rows) == len(required)
    return {
        "required_case_count": len(required),
        "result_row_count": len(rows),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
        "duplicate_case_ids": duplicate,
        "case_kind_mismatch_ids": kind_mismatch,
        "case_fingerprint_mismatch_ids": fingerprint_mismatch,
        "complete": complete,
    }


def _report_gate(profile: SealedConformanceGateProfile) -> dict[str, object]:
    host = _profile_host(profile, include_fingerprint=True)
    host.pop("schema")
    return host


def _project_aggregate_report(
    *,
    campaign: dict[str, object],
    program: SealedValidationProgram,
    profile: SealedConformanceGateProfile,
    campaign_integrity: dict[str, object],
    result_rows: list[dict[str, object]],
) -> dict[str, object]:
    completeness = _derive_campaign_completeness(
        tuple(cast(list[dict[str, object]], campaign["required_cases"])),
        tuple(result_rows),
    )
    all_passed = bool(
        completeness["complete"]
        and result_rows
        and all(row["outcome"] == "passed" for row in result_rows)
    )
    every_bound = all(
        row["within_every_per_evaluation_limit"]
        and row["within_invocation_limit"]
        for row in result_rows
    )
    passed = bool(
        campaign_integrity["passed"] and all_passed and every_bound
    )
    return {
        "schema": CONFORMANCE_REPORT_SCHEMA_ID,
        "program_id": program.program_id,
        "program_fingerprint": program.program_fingerprint,
        "campaign_id": campaign["campaign_id"],
        "campaign_fingerprint": campaign["campaign_fingerprint"],
        "required_case_set_fingerprint": campaign[
            "required_case_set_fingerprint"
        ],
        "gate": _report_gate(profile),
        "campaign_integrity": campaign_integrity,
        "result_rows": result_rows,
        "completeness": completeness,
        "all_case_outcomes_passed": all_passed,
        "decision": "passed" if passed else "failed",
    }


def _count_projection_fields(value: object) -> int:
    fields = 0
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            fields += len(current)
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
    return fields


def _canonicalize_aggregate_report(
    value: JsonObject,
    meter: SealMeter,
) -> bytes:
    try:
        raw = canonical_json_bytes(value, max_bytes=_REPORT_CANONICAL_BYTE_LIMIT)
        meter.charge_canonical_bytes(len(raw))
        return raw
    except (CanonicalJsonError, _SealMeterExceeded) as error:
        raise _GateReportSealFailure("aggregate canonical serialization failed") from error


def _seal_aggregate_report(
    *,
    campaign: dict[str, object],
    program: SealedValidationProgram,
    profile: SealedConformanceGateProfile,
    campaign_integrity: dict[str, object],
    result_rows: list[dict[str, object]],
) -> TrustedConformanceGateResult:
    try:
        projected = _project_aggregate_report(
            campaign=campaign,
            program=program,
            profile=profile,
            campaign_integrity=campaign_integrity,
            result_rows=result_rows,
        )
        ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
        receipt = ledger.reserve_report_seal_and_freeze()
        meter = SealMeter(receipt)
        meter.charge_projection_fields(_count_projection_fields(projected) + 1)
        unsigned = _owned_object(projected)
        first_bytes = _canonicalize_aggregate_report(unsigned, meter)
        report_fingerprint = sha256_prefixed(first_bytes)
        final_value = _owned_object(
            {**projected, "report_fingerprint": report_fingerprint}
        )
        final_bytes = _canonicalize_aggregate_report(final_value, meter)
        if not _schema_accepts(final_value, CONFORMANCE_REPORT_SCHEMA):
            raise _GateReportSealFailure("aggregate report schema failed")
        return _issue_gate_result(
            report_bytes=final_bytes,
            report_fingerprint=report_fingerprint,
            decision=cast(str, projected["decision"]),
            gate_profile=profile,
        )
    except (_GateReportSealFailure, _SealMeterExceeded):
        raise
    except Exception as error:
        raise _GateReportSealFailure("aggregate report projection failed") from error


def _execute_conformance_gate(
    profile: SealedConformanceGateProfile,
    program: SealedValidationProgram,
    raw_campaign_bytes: bytes,
    captured_context: tuple[
        TrustedImmutableArtifactStore,
        MappingProxyType[str, SealedTrustedBundleAssemblerProfile],
    ],
) -> TrustedConformanceGateResult | ConformanceGateInvocationFailure:
    input_size = len(raw_campaign_bytes)
    profile_fingerprint = profile.gate_profile_fingerprint
    program_fingerprint = program.program_fingerprint
    if input_size > profile.campaign_input_byte_limit:
        return _failure(
            stage="campaign_admission",
            code="campaign_admission_failed",
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=None,
            detail="campaign_input_limit",
        )
    admitted = memoryview(raw_campaign_bytes).tobytes()
    campaign_hash = sha256_prefixed(admitted)
    try:
        parsed = _parse_gate_json(admitted, "conformance_campaign")
    except (BudgetExceeded, JsonParseError):
        return _failure(
            stage="campaign_parse",
            code="campaign_parse_failed",
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=campaign_hash,
            detail="bounded_campaign_parse",
        )
    if (
        type(parsed.value) is not JsonObject
        or not _schema_accepts(parsed.value, CONFORMANCE_CAMPAIGN_SCHEMA)
    ):
        return _failure(
            stage="campaign_schema",
            code="campaign_schema_failed",
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=campaign_hash,
            detail="closed_campaign_schema",
        )
    campaign = cast(dict[str, object], _host_value(parsed.value))
    identity_error = _campaign_identity_error(campaign)
    if identity_error is not None:
        return _failure(
            stage=(
                "campaign_schema"
                if identity_error == "campaign_schema_failed"
                else "campaign_identity"
            ),
            code=identity_error,
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=campaign_hash,
            detail="campaign_identity",
        )
    campaign_integrity = _derive_campaign_integrity(campaign, profile, program)
    try:
        result_rows = (
            _execute_campaign_cases(campaign, program, captured_context)
            if campaign_integrity["passed"]
            else []
        )
    except _GateBudgetFailure:
        return _failure(
            stage="gate_execution",
            code="gate_budget_exceeded",
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=campaign_hash,
            detail="gate_budget",
        )
    except _GateIntegrityFailure:
        return _failure(
            stage="gate_execution",
            code="gate_execution_failed",
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=campaign_hash,
            detail="gate_integrity",
        )
    try:
        return _seal_aggregate_report(
            campaign=campaign,
            program=program,
            profile=profile,
            campaign_integrity=campaign_integrity,
            result_rows=result_rows,
        )
    except (_GateReportSealFailure, _SealMeterExceeded):
        return _failure(
            stage="report_seal",
            code="gate_report_seal_failed",
            gate_profile_fingerprint=profile_fingerprint,
            program_fingerprint=program_fingerprint,
            campaign_input_size=input_size,
            campaign_input_sha256=campaign_hash,
            detail="aggregate_report_seal",
        )


__all__ = (
    "ConformanceGateInvocationFailure",
    "SealedConformanceGateProfile",
    "TrustedConformanceFixtureContext",
    "TrustedConformanceGateResult",
    "TrustedImmutableArtifactStore",
    "run_conformance_gate",
    "seal_conformance_gate_profile",
)
