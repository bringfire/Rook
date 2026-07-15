"""Trusted validation-bundle issuance and invocation preflight."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from .budget import BudgetExceeded, BudgetLedger, LM9A_BUDGET_MANIFEST
from .canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
    sha256_prefixed,
    utf16_sort_key,
)
from .control import (
    ArtifactRole,
    BudgetDimension,
    BudgetExceededFailure,
    FailureStage,
    ValidationControlFailure,
    make_control_failure,
)
from .kernel_schemas import TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID
from .owned_json import (
    JsonArray,
    JsonNull,
    JsonObject,
    JsonString,
    JsonValue,
    lookup_json_pointer,
    own_trusted_json,
)
from .parser import JsonParseError, JsonParseEvidence
from .program import (
    SealedValidationProgram,
    _fixed_parser_profile_spec,
    _has_valid_runtime_binding_witness,
)


_MACHINE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UTC_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z\Z"
)
_ASSEMBLER_KINDS = frozenset(("trusted_host_ingress", "deterministic_fixture"))
_CLOCK_FOR_ASSEMBLER_KIND = {
    "trusted_host_ingress": "trusted_system_clock",
    "deterministic_fixture": "deterministic_fixture",
}
_PROFILE_FIELDS = frozenset(
    (
        "schema",
        "profile_id",
        "assembler_kind",
        "assembler_id",
        "assembler_version",
        "implementation_fingerprint",
        "permitted_program_ids",
        "permitted_clock_sources",
        "profile_fingerprint",
    )
)
_PROFILE_CONSTRUCTION_SENTINEL = object()
_BUNDLE_CONSTRUCTION_SENTINEL = object()
_PROFILE_ISSUER_CAPABILITY = object()
_BUNDLE_ISSUER_CAPABILITY = object()


@dataclass(frozen=True, slots=True, init=False, eq=False)
class SealedTrustedBundleAssemblerProfile:
    """A non-deserializable authority for trusted bundle issuance."""

    schema: str
    profile_id: str
    assembler_kind: str
    assembler_id: str
    assembler_version: str
    implementation_fingerprint: str
    permitted_program_ids: tuple[str, ...]
    permitted_clock_sources: tuple[str, ...]
    profile_fingerprint: str
    profile_bytes: bytes
    __issuer_capability: object = field(init=False, repr=False, compare=False)
    __issued_signature: tuple[object, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __init__(self) -> None:
        raise TypeError(
            "SealedTrustedBundleAssemblerProfile values are created only by the fixed seal"
        )

    def __copy__(self) -> object:
        raise TypeError("sealed assembler profiles cannot be copied or serialized")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("sealed assembler profiles cannot be copied or serialized")

    def __reduce__(self) -> object:
        raise TypeError("sealed assembler profiles cannot be copied or serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("sealed assembler profiles cannot be copied or serialized")


def _profile_issued_signature(
    profile: SealedTrustedBundleAssemblerProfile,
) -> tuple[object, ...]:
    return (
        profile,
        profile.schema,
        profile.profile_id,
        profile.assembler_kind,
        profile.assembler_id,
        profile.assembler_version,
        profile.implementation_fingerprint,
        profile.permitted_program_ids,
        profile.permitted_clock_sources,
        profile.profile_fingerprint,
        profile.profile_bytes,
    )


def _construct_sealed_assembler_profile(
    sentinel: object,
    *,
    schema: str,
    profile_id: str,
    assembler_kind: str,
    assembler_id: str,
    assembler_version: str,
    implementation_fingerprint: str,
    permitted_program_ids: tuple[str, ...],
    permitted_clock_sources: tuple[str, ...],
    profile_fingerprint: str,
    profile_bytes: bytes,
) -> SealedTrustedBundleAssemblerProfile:
    if sentinel is not _PROFILE_CONSTRUCTION_SENTINEL:
        raise TypeError("invalid assembler-profile construction authority")
    sealed = object.__new__(SealedTrustedBundleAssemblerProfile)
    object.__setattr__(sealed, "schema", schema)
    object.__setattr__(sealed, "profile_id", profile_id)
    object.__setattr__(sealed, "assembler_kind", assembler_kind)
    object.__setattr__(sealed, "assembler_id", assembler_id)
    object.__setattr__(sealed, "assembler_version", assembler_version)
    object.__setattr__(sealed, "implementation_fingerprint", implementation_fingerprint)
    object.__setattr__(sealed, "permitted_program_ids", permitted_program_ids)
    object.__setattr__(sealed, "permitted_clock_sources", permitted_clock_sources)
    object.__setattr__(sealed, "profile_fingerprint", profile_fingerprint)
    object.__setattr__(sealed, "profile_bytes", profile_bytes)
    object.__setattr__(
        sealed,
        "_SealedTrustedBundleAssemblerProfile__issuer_capability",
        _PROFILE_ISSUER_CAPABILITY,
    )
    object.__setattr__(
        sealed,
        "_SealedTrustedBundleAssemblerProfile__issued_signature",
        _profile_issued_signature(sealed),
    )
    return sealed


class TrustedValidationBundleInput:
    """Opaque carrier binding exact bytes to one sealed assembler profile."""

    __slots__ = (
        "_raw_bytes",
        "_profile",
        "_TrustedValidationBundleInput__issuer_capability",
        "_TrustedValidationBundleInput__issued_signature",
    )

    def __init__(self) -> None:
        raise TypeError(
            "TrustedValidationBundleInput values are created only by trusted issuance"
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("trusted validation bundle carriers are immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("trusted validation bundle carriers are immutable")

    def __copy__(self) -> object:
        raise TypeError(
            "trusted validation bundle carriers cannot be copied or serialized"
        )

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError(
            "trusted validation bundle carriers cannot be copied or serialized"
        )

    def __reduce__(self) -> object:
        raise TypeError(
            "trusted validation bundle carriers cannot be copied or serialized"
        )

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError(
            "trusted validation bundle carriers cannot be copied or serialized"
        )

    @property
    def raw_bytes(self) -> bytes:
        return self._raw_bytes


def _construct_trusted_validation_bundle(
    sentinel: object,
    *,
    profile: SealedTrustedBundleAssemblerProfile,
    raw_bytes: bytes,
) -> TrustedValidationBundleInput:
    if sentinel is not _BUNDLE_CONSTRUCTION_SENTINEL:
        raise TypeError("invalid trusted-bundle construction authority")
    carrier = object.__new__(TrustedValidationBundleInput)
    object.__setattr__(carrier, "_raw_bytes", raw_bytes)
    object.__setattr__(carrier, "_profile", profile)
    object.__setattr__(
        carrier,
        "_TrustedValidationBundleInput__issuer_capability",
        _BUNDLE_ISSUER_CAPABILITY,
    )
    object.__setattr__(
        carrier,
        "_TrustedValidationBundleInput__issued_signature",
        (carrier, profile, raw_bytes),
    )
    return carrier


@dataclass(frozen=True, slots=True)
class ValidationInvocation:
    program: SealedValidationProgram
    assembler_profile: SealedTrustedBundleAssemblerProfile
    raw_recipe_bytes: bytes
    raw_validation_bundle_bytes: bytes
    recipe_input_payload_sha256: str
    validation_bundle_input_payload_sha256: str
    recipe_value_fingerprint: str | None
    validation_bundle_fingerprint: str
    validation_bundle: JsonObject
    recipe_value: JsonValue | None
    recipe_parse_evidence: JsonParseEvidence | None
    invocation_inputs: JsonObject


@dataclass(frozen=True, slots=True)
class _ValidationExecutionContext:
    """Private carrier for one invocation and its sole mutable ledger."""

    invocation: ValidationInvocation
    ledger: BudgetLedger = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _ValidationInvocationFailure(ValidationControlFailure):
    recipe_input_payload_sha256: str | None
    validation_bundle_input_payload_sha256: str | None
    validation_bundle_fingerprint: str | None
    metadata: JsonObject

    def __post_init__(self) -> None:
        super(_ValidationInvocationFailure, self).__post_init__()
        for value in (
            self.recipe_input_payload_sha256,
            self.validation_bundle_input_payload_sha256,
            self.validation_bundle_fingerprint,
        ):
            if value is not None and (
                type(value) is not str or not _FINGERPRINT_RE.fullmatch(value)
            ):
                raise ValueError("invocation failure fingerprint is invalid")
        if type(self.metadata) is not JsonObject:
            raise TypeError("invocation failure metadata must be an owned object")


@dataclass(frozen=True, slots=True)
class _ValidationInvocationBudgetExceededFailure(BudgetExceededFailure):
    recipe_input_payload_sha256: str | None
    validation_bundle_input_payload_sha256: str | None
    validation_bundle_fingerprint: str | None
    metadata: JsonObject

    def __post_init__(self) -> None:
        super(_ValidationInvocationBudgetExceededFailure, self).__post_init__()
        for value in (
            self.recipe_input_payload_sha256,
            self.validation_bundle_input_payload_sha256,
            self.validation_bundle_fingerprint,
        ):
            if value is not None and (
                type(value) is not str or not _FINGERPRINT_RE.fullmatch(value)
            ):
                raise ValueError("invocation failure fingerprint is invalid")
        if type(self.metadata) is not JsonObject:
            raise TypeError("invocation failure metadata must be an owned object")


def _exact_string(value: JsonValue, field_name: str) -> str:
    if type(value) is not JsonString:
        raise ValueError(f"{field_name} must be an exact string")
    return value.value


def _machine_id(value: JsonValue, field_name: str) -> str:
    text = _exact_string(value, field_name)
    if not _MACHINE_ID_RE.fullmatch(text):
        raise ValueError(f"{field_name} must be an ASCII machine identifier")
    return text


def _fingerprint(value: JsonValue, field_name: str) -> str:
    text = _exact_string(value, field_name)
    if not _FINGERPRINT_RE.fullmatch(text):
        raise ValueError(f"{field_name} must be lowercase prefixed SHA-256")
    return text


def _string_set(value: JsonValue, field_name: str, *, machine_ids: bool) -> tuple[str, ...]:
    if type(value) is not JsonArray or not value:
        raise ValueError(f"{field_name} must be a nonempty array")
    strings = tuple(
        _machine_id(item, field_name) if machine_ids else _exact_string(item, field_name)
        for item in value
    )
    if len(frozenset(strings)) != len(strings):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(strings, key=utf16_sort_key))


def _normalized_profile_value(
    *,
    schema: str,
    profile_id: str,
    assembler_kind: str,
    assembler_id: str,
    assembler_version: str,
    implementation_fingerprint: str,
    permitted_program_ids: tuple[str, ...],
    permitted_clock_sources: tuple[str, ...],
    profile_fingerprint: str | None,
) -> JsonObject:
    host: dict[str, object] = {
        "schema": schema,
        "profile_id": profile_id,
        "assembler_kind": assembler_kind,
        "assembler_id": assembler_id,
        "assembler_version": assembler_version,
        "implementation_fingerprint": implementation_fingerprint,
        "permitted_program_ids": list(permitted_program_ids),
        "permitted_clock_sources": list(permitted_clock_sources),
    }
    if profile_fingerprint is not None:
        host["profile_fingerprint"] = profile_fingerprint
    owned = own_trusted_json(host)
    if type(owned) is not JsonObject:
        raise AssertionError("normalized assembler profile must be an object")
    return owned


def seal_trusted_bundle_assembler_profile(
    candidate: JsonObject,
) -> SealedTrustedBundleAssemblerProfile:
    """Validate, normalize, fingerprint, and seal one assembler authority."""

    if type(candidate) is not JsonObject:
        raise TypeError("assembler profile candidate must be an exact JsonObject")
    if frozenset(candidate) != _PROFILE_FIELDS:
        raise ValueError("assembler profile fields are not exact")
    schema = _exact_string(candidate["schema"], "schema")
    if schema != TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID:
        raise ValueError("assembler profile schema is invalid")
    profile_id = _machine_id(candidate["profile_id"], "profile ID")
    assembler_kind = _exact_string(candidate["assembler_kind"], "assembler kind")
    if assembler_kind not in _ASSEMBLER_KINDS:
        raise ValueError("assembler kind is invalid")
    assembler_id = _machine_id(candidate["assembler_id"], "assembler ID")
    assembler_version = _machine_id(
        candidate["assembler_version"], "assembler version"
    )
    implementation_fingerprint = _fingerprint(
        candidate["implementation_fingerprint"], "implementation fingerprint"
    )
    permitted_program_ids = _string_set(
        candidate["permitted_program_ids"],
        "permitted program IDs",
        machine_ids=True,
    )
    permitted_clock_sources = _string_set(
        candidate["permitted_clock_sources"],
        "permitted clock sources",
        machine_ids=False,
    )
    expected_clocks = (_CLOCK_FOR_ASSEMBLER_KIND[assembler_kind],)
    if permitted_clock_sources != expected_clocks:
        raise ValueError("permitted clock sources do not match assembler kind")
    asserted_fingerprint = _fingerprint(
        candidate["profile_fingerprint"], "profile fingerprint"
    )
    unsigned = _normalized_profile_value(
        schema=schema,
        profile_id=profile_id,
        assembler_kind=assembler_kind,
        assembler_id=assembler_id,
        assembler_version=assembler_version,
        implementation_fingerprint=implementation_fingerprint,
        permitted_program_ids=permitted_program_ids,
        permitted_clock_sources=permitted_clock_sources,
        profile_fingerprint=None,
    )
    computed_fingerprint = canonical_fingerprint(unsigned)
    if asserted_fingerprint != computed_fingerprint:
        raise ValueError("assembler profile fingerprint mismatch")
    final_value = _normalized_profile_value(
        schema=schema,
        profile_id=profile_id,
        assembler_kind=assembler_kind,
        assembler_id=assembler_id,
        assembler_version=assembler_version,
        implementation_fingerprint=implementation_fingerprint,
        permitted_program_ids=permitted_program_ids,
        permitted_clock_sources=permitted_clock_sources,
        profile_fingerprint=computed_fingerprint,
    )
    return _construct_sealed_assembler_profile(
        _PROFILE_CONSTRUCTION_SENTINEL,
        schema=schema,
        profile_id=profile_id,
        assembler_kind=assembler_kind,
        assembler_id=assembler_id,
        assembler_version=assembler_version,
        implementation_fingerprint=implementation_fingerprint,
        permitted_program_ids=permitted_program_ids,
        permitted_clock_sources=permitted_clock_sources,
        profile_fingerprint=computed_fingerprint,
        profile_bytes=canonical_json_bytes(final_value),
    )


def _profile_is_valid(profile: object) -> bool:
    if type(profile) is not SealedTrustedBundleAssemblerProfile:
        return False
    try:
        issuer = object.__getattribute__(
            profile,
            "_SealedTrustedBundleAssemblerProfile__issuer_capability",
        )
        issued_signature = object.__getattribute__(
            profile,
            "_SealedTrustedBundleAssemblerProfile__issued_signature",
        )
        if issuer is not _PROFILE_ISSUER_CAPABILITY:
            return False
        if (
            type(profile.schema) is not str
            or type(profile.profile_id) is not str
            or type(profile.assembler_kind) is not str
            or type(profile.assembler_id) is not str
            or type(profile.assembler_version) is not str
            or type(profile.implementation_fingerprint) is not str
            or type(profile.permitted_program_ids) is not tuple
            or type(profile.permitted_clock_sources) is not tuple
            or type(profile.profile_fingerprint) is not str
            or type(profile.profile_bytes) is not bytes
            or type(issued_signature) is not tuple
            or len(issued_signature) != 11
            or not all(
                issued is current
                for issued, current in zip(
                    issued_signature,
                    _profile_issued_signature(profile),
                    strict=True,
                )
            )
        ):
            return False
        unsigned = _normalized_profile_value(
            schema=profile.schema,
            profile_id=profile.profile_id,
            assembler_kind=profile.assembler_kind,
            assembler_id=profile.assembler_id,
            assembler_version=profile.assembler_version,
            implementation_fingerprint=profile.implementation_fingerprint,
            permitted_program_ids=profile.permitted_program_ids,
            permitted_clock_sources=profile.permitted_clock_sources,
            profile_fingerprint=None,
        )
        if canonical_fingerprint(unsigned) != profile.profile_fingerprint:
            return False
        final_value = _normalized_profile_value(
            schema=profile.schema,
            profile_id=profile.profile_id,
            assembler_kind=profile.assembler_kind,
            assembler_id=profile.assembler_id,
            assembler_version=profile.assembler_version,
            implementation_fingerprint=profile.implementation_fingerprint,
            permitted_program_ids=profile.permitted_program_ids,
            permitted_clock_sources=profile.permitted_clock_sources,
            profile_fingerprint=profile.profile_fingerprint,
        )
        return canonical_json_bytes(final_value) == profile.profile_bytes
    except (AttributeError, TypeError, ValueError):
        return False


def _trusted_bundle_is_valid(value: object) -> bool:
    if type(value) is not TrustedValidationBundleInput:
        return False
    try:
        issuer = object.__getattribute__(
            value,
            "_TrustedValidationBundleInput__issuer_capability",
        )
        issued_signature = object.__getattribute__(
            value,
            "_TrustedValidationBundleInput__issued_signature",
        )
        if (
            issuer is not _BUNDLE_ISSUER_CAPABILITY
            or type(issued_signature) is not tuple
            or len(issued_signature) != 3
        ):
            return False
        profile = object.__getattribute__(value, "_profile")
        raw_bytes = object.__getattribute__(value, "_raw_bytes")
        return (
            type(raw_bytes) is bytes
            and _profile_is_valid(profile)
            and issued_signature[0] is value
            and issued_signature[1] is profile
            and issued_signature[2] is raw_bytes
        )
    except (AttributeError, TypeError, ValueError):
        return False


def issue_trusted_validation_bundle(
    profile: SealedTrustedBundleAssemblerProfile,
    raw_bytes: bytes,
) -> TrustedValidationBundleInput:
    """Bind exact immutable bytes to one identity-bound sealed profile."""

    if not _profile_is_valid(profile):
        raise TypeError("trusted bundle issuance requires a valid sealed profile")
    if type(raw_bytes) is not bytes:
        raise TypeError("trusted bundle issuance requires exact built-in bytes")
    return _construct_trusted_validation_bundle(
        _BUNDLE_CONSTRUCTION_SENTINEL,
        profile=profile,
        raw_bytes=raw_bytes,
    )


def _owned_metadata(value: dict[str, object] | None = None) -> JsonObject:
    owned = own_trusted_json({} if value is None else value)
    if type(owned) is not JsonObject:
        raise AssertionError("invocation failure metadata must be an object")
    return owned


def _control_failure(
    *,
    code: str,
    artifact_role: ArtifactRole,
    program: SealedValidationProgram | None,
    subject_path: str | None = None,
    recipe_input_payload_sha256: str | None = None,
    validation_bundle_input_payload_sha256: str | None = None,
    validation_bundle_fingerprint: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ValidationControlFailure:
    base = make_control_failure(
        failure_stage=FailureStage.PREFLIGHT,
        code=code,
        artifact_role=artifact_role,
        program_id=None if program is None else program.program_id,
        program_fingerprint=None if program is None else program.program_fingerprint,
        subject_path=subject_path,
        message={
            "validation_input_invalid": "Validation input is invalid.",
            "validation_constructability_failed": "Validation report cannot be constructed.",
            "validator_identity_unavailable": "Validator identity is unavailable.",
        }[code],
        detail=None,
    )
    return _ValidationInvocationFailure(
        failure_stage=base.failure_stage,
        code=base.code,
        artifact_role=base.artifact_role,
        program_id=base.program_id,
        program_fingerprint=base.program_fingerprint,
        subject_path=base.subject_path,
        message=base.message,
        detail_sha256=base.detail_sha256,
        recipe_input_payload_sha256=recipe_input_payload_sha256,
        validation_bundle_input_payload_sha256=(
            validation_bundle_input_payload_sha256
        ),
        validation_bundle_fingerprint=validation_bundle_fingerprint,
        metadata=_owned_metadata(metadata),
    )


def _program_is_valid(program: object) -> bool:
    if (
        type(program) is not SealedValidationProgram
        or not _has_valid_runtime_binding_witness(program)
    ):
        return False
    try:
        identity_fields_are_valid = (
            type(program.program_id) is str
            and _MACHINE_ID_RE.fullmatch(program.program_id) is not None
            and type(program.program_fingerprint) is str
            and _FINGERPRINT_RE.fullmatch(program.program_fingerprint) is not None
            and type(program.manifest_bytes) is bytes
            and program.resolve_manifest_bytes(program.program_fingerprint)
            == program.manifest_bytes
            and program.budget_manifest is LM9A_BUDGET_MANIFEST
            and program.parser_profile == _fixed_parser_profile_spec()
        )
        if not identity_fields_are_valid:
            return False
        manifest = json.loads(program.manifest_bytes)
        if type(manifest) is not dict:
            return False
        asserted_fingerprint = manifest.pop("program_fingerprint", None)
        if asserted_fingerprint != program.program_fingerprint:
            return False
        return canonical_fingerprint(own_trusted_json(manifest)) == asserted_fingerprint
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _enrich_budget_failure(
    failure: BudgetExceededFailure,
    program: SealedValidationProgram,
    *,
    recipe_input_payload_sha256: str,
    validation_bundle_input_payload_sha256: str,
    validation_bundle_fingerprint: str | None,
) -> BudgetExceededFailure:
    return _ValidationInvocationBudgetExceededFailure(
        failure_stage=failure.failure_stage,
        code=failure.code,
        artifact_role=failure.artifact_role,
        program_id=program.program_id,
        program_fingerprint=program.program_fingerprint,
        subject_path=failure.subject_path,
        message=failure.message,
        detail_sha256=failure.detail_sha256,
        budget_dimension=failure.budget_dimension,
        limit=failure.limit,
        observed_lower_bound=failure.observed_lower_bound,
        recipe_input_payload_sha256=recipe_input_payload_sha256,
        validation_bundle_input_payload_sha256=(
            validation_bundle_input_payload_sha256
        ),
        validation_bundle_fingerprint=validation_bundle_fingerprint,
        metadata=_owned_metadata(),
    )


def _copy_exact_bytes(raw: bytes) -> bytes:
    return memoryview(raw).tobytes()


def _required_container_kind(value: JsonValue) -> str | None:
    if type(value) is JsonObject:
        return "object"
    if type(value) is JsonArray:
        return "array"
    return None


def _trusted_context_error(bundle: JsonObject) -> str | None:
    try:
        context = bundle["validation_context"]
    except KeyError:
        return "/validation_context"
    if type(context) is not JsonObject:
        return "/validation_context"

    required_machine_ids = (
        "task_session_id",
        "capability_registry_session_id",
    )
    for field_name in required_machine_ids:
        try:
            value = context[field_name]
        except KeyError:
            return f"/validation_context/{field_name}"
        if type(value) is not JsonString or not _MACHINE_ID_RE.fullmatch(value.value):
            return f"/validation_context/{field_name}"

    try:
        environment_session_id = context["environment_session_id"]
    except KeyError:
        return "/validation_context/environment_session_id"
    if type(environment_session_id) not in (JsonNull, JsonString):
        return "/validation_context/environment_session_id"
    if (
        type(environment_session_id) is JsonString
        and not _MACHINE_ID_RE.fullmatch(environment_session_id.value)
    ):
        return "/validation_context/environment_session_id"

    try:
        evaluated_at = context["evaluated_at"]
    except KeyError:
        return "/validation_context/evaluated_at"
    if type(evaluated_at) is not JsonString or not _UTC_TIMESTAMP_RE.fullmatch(
        evaluated_at.value
    ):
        return "/validation_context/evaluated_at"
    try:
        datetime.fromisoformat(evaluated_at.value[:-1] + "+00:00")
    except ValueError:
        return "/validation_context/evaluated_at"

    try:
        clock = context["trusted_clock_source"]
    except KeyError:
        return "/validation_context/trusted_clock_source"
    if type(clock) is not JsonString:
        return "/validation_context/trusted_clock_source"
    return None


def _clock_source(bundle: JsonObject) -> str:
    context = bundle["validation_context"]
    if type(context) is not JsonObject:
        raise AssertionError("trusted context was not established")
    clock = context["trusted_clock_source"]
    if type(clock) is not JsonString:
        raise AssertionError("trusted clock was not established")
    return clock.value


def _parse_evidence_value(evidence: JsonParseEvidence | None) -> JsonValue:
    if evidence is None:
        return JsonNull()
    value = own_trusted_json(
        {
            "artifact_role": evidence.artifact_role,
            "category": evidence.category,
            "subject_path": evidence.subject_path,
            "bounded_message": evidence.bounded_message,
            "detail_sha256": evidence.detail_sha256,
        }
    )
    return value


def _invocation_inputs(
    *,
    bundle: JsonObject,
    recipe_value: JsonValue | None,
    recipe_parse_evidence: JsonParseEvidence | None,
) -> JsonObject:
    return JsonObject(
        (
            (JsonString("recipe"), JsonNull() if recipe_value is None else recipe_value),
            (
                JsonString("recipe_parse_evidence"),
                _parse_evidence_value(recipe_parse_evidence),
            ),
            (JsonString("validation_bundle"), bundle),
        )
    )


def _build_validation_execution_context(
    program: SealedValidationProgram,
    raw_recipe_bytes: bytes,
    trusted_bundle: TrustedValidationBundleInput,
) -> _ValidationExecutionContext | ValidationControlFailure:
    """Run bundle-first preflight and create a report-capable invocation."""

    if not _program_is_valid(program):
        return _control_failure(
            code="validator_identity_unavailable",
            artifact_role=ArtifactRole.VALIDATION_PROGRAM,
            program=None,
        )
    if not _trusted_bundle_is_valid(trusted_bundle):
        return _control_failure(
            code="validation_input_invalid",
            artifact_role=ArtifactRole.VALIDATION_BUNDLE,
            program=program,
        )
    profile = object.__getattribute__(trusted_bundle, "_profile")
    raw_bundle_bytes = object.__getattribute__(trusted_bundle, "_raw_bytes")
    if program.program_id not in profile.permitted_program_ids:
        return _control_failure(
            code="validator_identity_unavailable",
            artifact_role=ArtifactRole.VALIDATION_PROGRAM,
            program=program,
        )
    if type(raw_recipe_bytes) is not bytes or type(raw_bundle_bytes) is not bytes:
        artifact_role = (
            ArtifactRole.RECIPE
            if type(raw_recipe_bytes) is not bytes
            else ArtifactRole.VALIDATION_BUNDLE
        )
        return _control_failure(
            code="validation_input_invalid",
            artifact_role=artifact_role,
            program=program,
        )

    recipe_length = len(raw_recipe_bytes)
    bundle_length = len(raw_bundle_bytes)
    limits = program.budget_manifest.limits
    recipe_limit_value = limits[BudgetDimension.RECIPE_INPUT_BYTES.value]
    bundle_limit_value = limits[BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES.value]
    recipe_limit = int(recipe_limit_value.value)  # type: ignore[union-attr]
    bundle_limit = int(bundle_limit_value.value)  # type: ignore[union-attr]
    if recipe_length > recipe_limit or bundle_length > bundle_limit:
        both_exceeded = (
            recipe_length > recipe_limit and bundle_length > bundle_limit
        )
        if recipe_length > recipe_limit:
            dimension = BudgetDimension.RECIPE_INPUT_BYTES
            limit = recipe_limit
            observed = recipe_length
            role = ArtifactRole.RECIPE
        else:
            dimension = BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES
            limit = bundle_limit
            observed = bundle_length
            role = ArtifactRole.VALIDATION_BUNDLE
        return _ValidationInvocationBudgetExceededFailure(
            failure_stage=FailureStage.PREFLIGHT,
            code="validation_budget_exceeded",
            artifact_role=ArtifactRole.COMBINED if both_exceeded else role,
            program_id=program.program_id,
            program_fingerprint=program.program_fingerprint,
            subject_path=None,
            message="Validation budget exceeded.",
            detail_sha256=None,
            budget_dimension=dimension,
            limit=limit,
            observed_lower_bound=observed,
            recipe_input_payload_sha256=None,
            validation_bundle_input_payload_sha256=None,
            validation_bundle_fingerprint=None,
            metadata=_owned_metadata(
                {
                    "recipe_input_byte_limit": recipe_limit,
                    "recipe_input_bytes": recipe_length,
                    "validation_bundle_input_byte_limit": bundle_limit,
                    "validation_bundle_input_bytes": bundle_length,
                }
            ),
        )

    owned_recipe_bytes = _copy_exact_bytes(raw_recipe_bytes)
    owned_bundle_bytes = _copy_exact_bytes(raw_bundle_bytes)
    recipe_sha256 = sha256_prefixed(owned_recipe_bytes)
    bundle_sha256 = sha256_prefixed(owned_bundle_bytes)
    ledger_factory = program.resolve_runtime_binding(
        "ledger", program.parser_profile.ledger.component_id
    )
    parser = program.resolve_runtime_binding(
        "parser", program.parser_profile.parser.component_id
    )
    ledger = ledger_factory(program.budget_manifest)  # type: ignore[operator]
    if type(ledger) is not BudgetLedger:
        return _control_failure(
            code="validator_identity_unavailable",
            artifact_role=ArtifactRole.VALIDATION_PROGRAM,
            program=None,
        )
    ledger.charge(
        BudgetDimension.RECIPE_INPUT_BYTES,
        recipe_length,
        artifact_role=ArtifactRole.RECIPE,
        subject_path=None,
    )
    ledger.charge(
        BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES,
        bundle_length,
        artifact_role=ArtifactRole.VALIDATION_BUNDLE,
        subject_path=None,
    )
    try:
        parsed_bundle = parser(  # type: ignore[operator]
            owned_bundle_bytes,
            artifact_role=ArtifactRole.VALIDATION_BUNDLE.value,
            ledger=ledger,
        )
    except JsonParseError:
        return _control_failure(
            code="validation_input_invalid",
            artifact_role=ArtifactRole.VALIDATION_BUNDLE,
            program=program,
            recipe_input_payload_sha256=recipe_sha256,
            validation_bundle_input_payload_sha256=bundle_sha256,
        )
    except BudgetExceeded as exc:
        return _enrich_budget_failure(
            exc.failure,
            program,
            recipe_input_payload_sha256=recipe_sha256,
            validation_bundle_input_payload_sha256=bundle_sha256,
            validation_bundle_fingerprint=None,
        )
    bundle_fingerprint = parsed_bundle.value_fingerprint
    if type(parsed_bundle.value) is not JsonObject:
        return _control_failure(
            code="validation_constructability_failed",
            artifact_role=ArtifactRole.VALIDATION_BUNDLE,
            program=program,
            subject_path="/",
            recipe_input_payload_sha256=recipe_sha256,
            validation_bundle_input_payload_sha256=bundle_sha256,
            validation_bundle_fingerprint=bundle_fingerprint,
        )
    bundle = parsed_bundle.value
    for path, required_kind in program.report_projection.mandatory_shells:
        try:
            shell = lookup_json_pointer(bundle, path)
        except KeyError:
            return _control_failure(
                code="validation_constructability_failed",
                artifact_role=ArtifactRole.VALIDATION_BUNDLE,
                program=program,
                subject_path=path,
                recipe_input_payload_sha256=recipe_sha256,
                validation_bundle_input_payload_sha256=bundle_sha256,
                validation_bundle_fingerprint=bundle_fingerprint,
            )
        if _required_container_kind(shell) != required_kind:
            return _control_failure(
                code="validation_constructability_failed",
                artifact_role=ArtifactRole.VALIDATION_BUNDLE,
                program=program,
                subject_path=path,
                recipe_input_payload_sha256=recipe_sha256,
                validation_bundle_input_payload_sha256=bundle_sha256,
                validation_bundle_fingerprint=bundle_fingerprint,
            )
    trusted_context_error = _trusted_context_error(bundle)
    if trusted_context_error is not None:
        return _control_failure(
            code="validation_input_invalid",
            artifact_role=ArtifactRole.VALIDATION_BUNDLE,
            program=program,
            subject_path=trusted_context_error,
            recipe_input_payload_sha256=recipe_sha256,
            validation_bundle_input_payload_sha256=bundle_sha256,
            validation_bundle_fingerprint=bundle_fingerprint,
        )
    if (
        _clock_source(bundle) not in profile.permitted_clock_sources
        or _clock_source(bundle) != _CLOCK_FOR_ASSEMBLER_KIND[profile.assembler_kind]
    ):
        return _control_failure(
            code="validation_input_invalid",
            artifact_role=ArtifactRole.VALIDATION_BUNDLE,
            program=program,
            subject_path="/validation_context/trusted_clock_source",
            recipe_input_payload_sha256=recipe_sha256,
            validation_bundle_input_payload_sha256=bundle_sha256,
            validation_bundle_fingerprint=bundle_fingerprint,
        )

    recipe_value: JsonValue | None
    recipe_parse_evidence: JsonParseEvidence | None
    try:
        parsed_recipe = parser(  # type: ignore[operator]
            owned_recipe_bytes,
            artifact_role=ArtifactRole.RECIPE.value,
            ledger=ledger,
        )
        recipe_value = parsed_recipe.value
        recipe_value_fingerprint = parsed_recipe.value_fingerprint
        recipe_parse_evidence = None
    except JsonParseError as exc:
        recipe_value = None
        recipe_value_fingerprint = None
        recipe_parse_evidence = exc.evidence
    except BudgetExceeded as exc:
        return _enrich_budget_failure(
            exc.failure,
            program,
            recipe_input_payload_sha256=recipe_sha256,
            validation_bundle_input_payload_sha256=bundle_sha256,
            validation_bundle_fingerprint=bundle_fingerprint,
        )

    invocation = ValidationInvocation(
        program=program,
        assembler_profile=profile,
        raw_recipe_bytes=owned_recipe_bytes,
        raw_validation_bundle_bytes=owned_bundle_bytes,
        recipe_input_payload_sha256=recipe_sha256,
        validation_bundle_input_payload_sha256=bundle_sha256,
        recipe_value_fingerprint=recipe_value_fingerprint,
        validation_bundle_fingerprint=bundle_fingerprint,
        validation_bundle=bundle,
        recipe_value=recipe_value,
        recipe_parse_evidence=recipe_parse_evidence,
        invocation_inputs=_invocation_inputs(
            bundle=bundle,
            recipe_value=recipe_value,
            recipe_parse_evidence=recipe_parse_evidence,
        ),
    )
    return _ValidationExecutionContext(invocation=invocation, ledger=ledger)


__all__ = (
    "SealedTrustedBundleAssemblerProfile",
    "TrustedValidationBundleInput",
    "ValidationInvocation",
    "issue_trusted_validation_bundle",
    "seal_trusted_bundle_assembler_profile",
)
