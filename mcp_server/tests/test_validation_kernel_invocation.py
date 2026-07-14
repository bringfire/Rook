from __future__ import annotations

import copy
import importlib
import json
import pickle
from dataclasses import fields as dataclass_fields
from dataclasses import replace as dataclass_replace
from types import SimpleNamespace

import pytest

import rook.validation_kernel as validation_kernel
from rook.validation_kernel import (
    ValidationControlFailure,
    compose_and_seal_program,
)
from rook.validation_kernel.budget import BudgetLedger
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
    sha256_prefixed,
)
from rook.validation_kernel.owned_json import JsonObject

from tests._validation_kernel_fakes import (
    INVOCATION_MANDATORY_SHELLS,
    make_assembler_profile_candidate,
    make_program_contribution,
    make_validation_bundle_bytes,
)


def _program():
    return compose_and_seal_program(make_program_contribution())


def _invocation_program():
    return compose_and_seal_program(
        make_program_contribution(invocation_shells=True)
    )


def _sealed_profile(*, assembler_kind: str = "deterministic_fixture"):
    return validation_kernel.seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate(assembler_kind=assembler_kind)
    )


def _issue(profile: object, raw_bytes: bytes):
    return validation_kernel.issue_trusted_validation_bundle(profile, raw_bytes)


def _build(program: object, recipe: object, carrier: object):
    module = importlib.import_module("rook.validation_kernel.invocation")
    return module._build_validation_execution_context(program, recipe, carrier)


def _carrier(profile: object, raw_bytes: bytes | None = None):
    return _issue(
        profile,
        make_validation_bundle_bytes() if raw_bytes is None else raw_bytes,
    )


def _host_json(value: object) -> object:
    return json.loads(canonical_json_bytes(value))


def _bundle_host() -> dict[str, object]:
    value = json.loads(make_validation_bundle_bytes())
    assert type(value) is dict
    return value


def test_invocation_resolves_the_sealed_fixed_ledger_and_parser_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    binding_lookups: list[tuple[str, str]] = []
    real_resolve = type(program).resolve_runtime_binding

    def resolve_spy(self: object, kind: str, component_id: str) -> object:
        binding_lookups.append((kind, component_id))
        return real_resolve(self, kind, component_id)

    monkeypatch.setattr(type(program), "resolve_runtime_binding", resolve_spy)

    result = _build(program, b"{}", _carrier(profile))

    assert not isinstance(result, ValidationControlFailure)
    assert ("ledger", program.parser_profile.ledger.component_id) in binding_lookups
    assert ("parser", program.parser_profile.parser.component_id) in binding_lookups


def _bundle_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def test_sealed_profiles_and_bundle_carriers_cannot_be_constructed_or_copied() -> None:
    candidate = make_assembler_profile_candidate()
    profile = validation_kernel.seal_trusted_bundle_assembler_profile(candidate)

    with pytest.raises(TypeError):
        validation_kernel.SealedTrustedBundleAssemblerProfile()
    with pytest.raises(TypeError):
        validation_kernel.TrustedValidationBundleInput()
    with pytest.raises(TypeError):
        _issue(candidate, b"{}")
    with pytest.raises(TypeError):
        _issue(
            SimpleNamespace(
                profile_id=profile.profile_id,
                profile_fingerprint=profile.profile_fingerprint,
            ),
            b"{}",
        )

    raw = make_validation_bundle_bytes()
    carrier = _issue(profile, raw)
    assert carrier.raw_bytes is raw
    assert not hasattr(profile, "_seal_capability")
    assert not hasattr(profile, "_issuer_capability")
    assert not hasattr(carrier, "_issuer_capability")
    for field_name, replacement in (
        ("_raw_bytes", b"{}"),
        ("_profile", object()),
    ):
        with pytest.raises(AttributeError):
            setattr(carrier, field_name, replacement)
    with pytest.raises(AttributeError):
        del carrier._raw_bytes


def test_profile_documented_copy_and_serialization_paths_are_closed() -> None:
    profile = _sealed_profile()
    profile_type = validation_kernel.SealedTrustedBundleAssemblerProfile

    for operation in (
        lambda: copy.copy(profile),
        lambda: copy.deepcopy(profile),
        lambda: pickle.loads(pickle.dumps(profile)),
        profile.__reduce__,
        lambda: profile.__reduce_ex__(pickle.HIGHEST_PROTOCOL),
    ):
        with pytest.raises(TypeError, match="cannot be copied or serialized"):
            operation()
    with pytest.raises(TypeError):
        dataclass_replace(profile)

    copied_fields = {
        field.name: getattr(profile, field.name)
        for field in dataclass_fields(profile)
    }
    with pytest.raises(TypeError):
        profile_type(**copied_fields)
    assert "_create" not in profile_type.__dict__

    field_lookalike = SimpleNamespace(**copied_fields)
    serialized_fields = json.loads(profile.profile_bytes)
    serialized_lookalike = SimpleNamespace(**serialized_fields)
    assert serialized_lookalike.profile_fingerprint == profile.profile_fingerprint
    for lookalike in (copied_fields, field_lookalike, serialized_lookalike):
        with pytest.raises(TypeError, match="valid sealed profile"):
            _issue(lookalike, b"{}")


def test_carrier_documented_copy_and_serialization_paths_are_closed() -> None:
    profile = _sealed_profile()
    raw = make_validation_bundle_bytes()
    carrier = _carrier(profile, raw)
    carrier_type = validation_kernel.TrustedValidationBundleInput

    for operation in (
        lambda: copy.copy(carrier),
        lambda: copy.deepcopy(carrier),
        lambda: pickle.loads(pickle.dumps(carrier)),
        carrier.__reduce__,
        lambda: carrier.__reduce_ex__(pickle.HIGHEST_PROTOCOL),
    ):
        with pytest.raises(TypeError, match="cannot be copied or serialized"):
            operation()
    with pytest.raises(TypeError):
        dataclass_replace(carrier)
    with pytest.raises(TypeError):
        carrier_type(profile=profile, raw_bytes=raw)
    assert "_create" not in carrier_type.__dict__


def test_unsealed_and_lookalike_carriers_fail_without_reading_artifacts() -> None:
    program = _program()

    class CarrierLookalike:
        reads = 0

        @property
        def raw_bytes(self) -> bytes:
            self.reads += 1
            return make_validation_bundle_bytes()

    lookalike = CarrierLookalike()
    result = _build(program, b"{}", lookalike)

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_input_invalid"
    assert result.program_id == program.program_id
    assert lookalike.reads == 0


def test_carrier_profile_must_permit_the_exact_sealed_program() -> None:
    program = _program()
    profile = validation_kernel.seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate(program_id="synthetic.other_program:v1")
    )
    carrier = _issue(profile, make_validation_bundle_bytes())

    result = _build(program, b"{}", carrier)

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_identity_unavailable"
    assert result.artifact_role == "validation_program"


def test_program_fingerprint_must_still_match_its_sealed_manifest() -> None:
    program = _program()
    object.__setattr__(program, "program_fingerprint", "sha256:" + "0" * 64)

    class CarrierLookalike:
        reads = 0

        @property
        def raw_bytes(self) -> bytes:
            self.reads += 1
            return make_validation_bundle_bytes()

    carrier = CarrierLookalike()
    result = _build(program, b"{}", carrier)

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_identity_unavailable"
    assert result.program_id is None
    assert carrier.reads == 0


@pytest.mark.parametrize(
    ("assembler_kind", "trusted_clock_source"),
    (
        ("deterministic_fixture", "deterministic_fixture"),
        ("trusted_host_ingress", "trusted_system_clock"),
    ),
)
def test_each_assembler_kind_accepts_only_its_exact_clock(
    assembler_kind: str,
    trusted_clock_source: str,
) -> None:
    program = _program()
    profile = _sealed_profile(assembler_kind=assembler_kind)
    carrier = _issue(
        profile,
        make_validation_bundle_bytes(trusted_clock_source=trusted_clock_source),
    )

    result = _build(program, b"{}", carrier)

    assert not isinstance(result, ValidationControlFailure)
    assert result.invocation.assembler_profile is profile


@pytest.mark.parametrize(
    ("assembler_kind", "permitted_clock_sources"),
    (
        ("deterministic_fixture", ("trusted_system_clock",)),
        ("trusted_host_ingress", ("deterministic_fixture",)),
        ("deterministic_fixture", ("deterministic_fixture", "trusted_system_clock")),
    ),
)
def test_profile_seal_rejects_clock_authority_broader_than_assembler_kind(
    assembler_kind: str,
    permitted_clock_sources: tuple[str, ...],
) -> None:
    candidate = make_assembler_profile_candidate(
        assembler_kind=assembler_kind,
        permitted_clock_sources=permitted_clock_sources,
    )

    with pytest.raises(ValueError, match="clock"):
        validation_kernel.seal_trusted_bundle_assembler_profile(candidate)


@pytest.mark.parametrize(
    ("assembler_kind", "wrong_clock"),
    (
        ("deterministic_fixture", "trusted_system_clock"),
        ("trusted_host_ingress", "deterministic_fixture"),
    ),
)
def test_bundle_clock_must_match_captured_profile_authority(
    assembler_kind: str,
    wrong_clock: str,
) -> None:
    program = _program()
    profile = _sealed_profile(assembler_kind=assembler_kind)
    carrier = _issue(
        profile,
        make_validation_bundle_bytes(trusted_clock_source=wrong_clock),
    )

    result = _build(program, b"{}", carrier)

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_input_invalid"
    assert result.artifact_role == "validation_bundle"
    assert result.subject_path == "/validation_context/trusted_clock_source"


def test_invalid_session_identity_cannot_establish_trusted_context() -> None:
    program = _program()
    profile = _sealed_profile()
    carrier = _issue(
        profile,
        make_validation_bundle_bytes(task_session_id="not a machine id"),
    )

    result = _build(program, b"{}", carrier)

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_input_invalid"
    assert result.subject_path == "/validation_context/task_session_id"


def test_exact_byte_types_are_checked_before_length_or_conversion() -> None:
    program = _invocation_program()
    profile = _sealed_profile()

    class SpyBytes(bytes):
        length_reads = 0

        def __len__(self) -> int:
            type(self).length_reads += 1
            return super().__len__()

    recipe_spy = SpyBytes(b"{}")
    result = _build(program, recipe_spy, _carrier(profile))
    assert isinstance(result, ValidationControlFailure)
    assert result.artifact_role == "recipe"
    assert SpyBytes.length_reads == 0

    bundle_spy = SpyBytes(make_validation_bundle_bytes())
    with pytest.raises(TypeError, match="exact built-in bytes"):
        _issue(profile, bundle_spy)
    assert SpyBytes.length_reads == 0

    issued = _carrier(profile)
    object.__setattr__(issued, "_raw_bytes", bundle_spy)
    result = _build(program, b"{}", issued)
    assert isinstance(result, ValidationControlFailure)
    assert result.artifact_role == "validation_bundle"
    assert SpyBytes.length_reads == 0


def test_over_cap_pair_records_both_lengths_and_never_copies_or_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("rook.validation_kernel.invocation")
    program = _invocation_program()
    profile = _sealed_profile()
    recipe = b"r" * 1_048_577
    bundle = b"b" * 4_194_305

    def forbidden(_: bytes) -> bytes:
        raise AssertionError("over-cap inputs must not be copied or hashed")

    monkeypatch.setattr(module, "_copy_exact_bytes", forbidden)
    monkeypatch.setattr(module, "sha256_prefixed", forbidden)

    result = _build(program, recipe, _carrier(profile, bundle))

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_budget_exceeded"
    assert result.artifact_role == "combined"
    assert result.recipe_input_payload_sha256 is None
    assert result.validation_bundle_input_payload_sha256 is None
    assert result.validation_bundle_fingerprint is None
    assert _host_json(result.metadata) == {
        "recipe_input_byte_limit": 1_048_576,
        "recipe_input_bytes": len(recipe),
        "validation_bundle_input_byte_limit": 4_194_304,
        "validation_bundle_input_bytes": len(bundle),
    }


def test_exact_cap_pair_is_copied_and_hashed_once_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("rook.validation_kernel.invocation")
    program = _invocation_program()
    profile = _sealed_profile()
    base_bundle = make_validation_bundle_bytes()
    recipe = b" " * (1_048_576 - 2) + b"{}"
    bundle = b" " * (4_194_304 - len(base_bundle)) + base_bundle
    copied_lengths: list[int] = []
    hashed_lengths: list[int] = []
    copy_exact_bytes = module._copy_exact_bytes
    hash_exact_bytes = module.sha256_prefixed

    def copy_spy(raw: bytes) -> bytes:
        copied_lengths.append(len(raw))
        return copy_exact_bytes(raw)

    def hash_spy(raw: bytes) -> str:
        hashed_lengths.append(len(raw))
        return hash_exact_bytes(raw)

    monkeypatch.setattr(module, "_copy_exact_bytes", copy_spy)
    monkeypatch.setattr(module, "sha256_prefixed", hash_spy)

    result = _build(program, recipe, _carrier(profile, bundle))

    assert not isinstance(result, ValidationControlFailure)
    assert copied_lengths == [len(recipe), len(bundle)]
    assert hashed_lengths == [len(recipe), len(bundle)]
    assert result.invocation.raw_recipe_bytes is not recipe
    assert result.invocation.raw_validation_bundle_bytes is not bundle
    assert result.invocation.recipe_input_payload_sha256 == sha256_prefixed(recipe)
    assert result.invocation.validation_bundle_input_payload_sha256 == sha256_prefixed(
        bundle
    )


def test_constructable_bundle_and_valid_recipe_create_one_private_context() -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    bundle_bytes = make_validation_bundle_bytes()
    recipe_bytes = b'{"goal":"plan"}'

    result = _build(program, recipe_bytes, _carrier(profile, bundle_bytes))

    assert not isinstance(result, ValidationControlFailure)
    invocation = result.invocation
    assert invocation.program is program
    assert invocation.assembler_profile is profile
    assert type(invocation.validation_bundle) is JsonObject
    assert invocation.recipe_value is not None
    assert invocation.recipe_parse_evidence is None
    assert type(invocation.invocation_inputs) is JsonObject
    assert invocation.validation_bundle_fingerprint == canonical_fingerprint(
        invocation.validation_bundle
    )
    assert not hasattr(invocation, "ledger")
    assert type(result.ledger) is BudgetLedger


def test_constructable_bundle_keeps_malformed_recipe_as_phase_evidence() -> None:
    program = _invocation_program()
    profile = _sealed_profile()

    result = _build(program, b'{"goal":', _carrier(profile))

    assert not isinstance(result, ValidationControlFailure)
    assert result.invocation.recipe_value is None
    assert result.invocation.recipe_parse_evidence is not None
    assert result.invocation.recipe_parse_evidence.artifact_role == "recipe"
    assert result.invocation.recipe_parse_evidence.category == "invalid_syntax"


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        ("/task_envelope", None),
        ("/authority_artifacts", {}),
        ("/validation_context/vocabularies/worker_slot_codes", []),
    ),
)
def test_missing_or_wrong_container_shell_prevents_report_constructability(
    path: str,
    replacement: object,
) -> None:
    program = _invocation_program()
    assert program.report_projection.mandatory_shells == tuple(
        sorted(INVOCATION_MANDATORY_SHELLS)
    )
    profile = _sealed_profile()
    bundle = _bundle_host()
    parts = path.lstrip("/").split("/")
    parent: dict[str, object] = bundle
    for part in parts[:-1]:
        child = parent[part]
        assert type(child) is dict
        parent = child
    if replacement is None:
        del parent[parts[-1]]
    else:
        parent[parts[-1]] = replacement

    result = _build(program, b"{}", _carrier(profile, _bundle_bytes(bundle)))

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_constructability_failed"
    assert result.subject_path == path
    assert result.recipe_input_payload_sha256 is not None
    assert result.validation_bundle_input_payload_sha256 is not None
    assert result.validation_bundle_fingerprint is not None


def test_malformed_inner_companion_content_remains_phase_evidence() -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    bundle = _bundle_host()
    context = bundle["validation_context"]
    assert type(context) is dict
    context["payload_schema_registry"] = {"malformed": "not-a-descriptor"}

    result = _build(program, b"{}", _carrier(profile, _bundle_bytes(bundle)))

    assert not isinstance(result, ValidationControlFailure)
    assert result.invocation.recipe_parse_evidence is None


def test_malformed_bundle_stops_before_report_capability() -> None:
    program = _invocation_program()
    profile = _sealed_profile()

    result = _build(
        program,
        b'{"also":"malformed"',
        _carrier(profile, b'{"validation_context":'),
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_input_invalid"
    assert result.artifact_role == "validation_bundle"
    assert result.recipe_input_payload_sha256 is not None
    assert result.validation_bundle_input_payload_sha256 is not None
    assert result.validation_bundle_fingerprint is None


def test_malformed_recipe_and_inner_companion_content_still_create_invocation() -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    bundle = _bundle_host()
    context = bundle["validation_context"]
    assert type(context) is dict
    context["capability_registry"] = {"bad": ["inner", "content"]}

    result = _build(
        program,
        b'{"recipe":',
        _carrier(profile, _bundle_bytes(bundle)),
    )

    assert not isinstance(result, ValidationControlFailure)
    assert result.invocation.recipe_parse_evidence is not None


@pytest.mark.parametrize("exhaust_during", ("bundle", "recipe"))
def test_shared_aggregate_parse_budget_exhaustion_is_pre_report_control_failure(
    exhaust_during: str,
) -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    bundle = _bundle_host()
    if exhaust_during == "bundle":
        bundle["aggregate_load"] = [[0] * 10_000 for _ in range(10)]
        recipe = b"{}"
    else:
        bundle["aggregate_load"] = [[0] * 9_000 for _ in range(10)]
        recipe = json.dumps([0] * 12_000, separators=(",", ":")).encode("ascii")

    result = _build(program, recipe, _carrier(profile, _bundle_bytes(bundle)))

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validation_budget_exceeded"
    assert result.artifact_role == "combined"
    assert result.failure_stage == "preflight"
    assert result.recipe_input_payload_sha256 is not None
    assert result.validation_bundle_input_payload_sha256 is not None
    if exhaust_during == "bundle":
        assert result.validation_bundle_fingerprint is None
    else:
        assert result.validation_bundle_fingerprint is not None


def test_source_replacement_after_issuance_cannot_change_captured_bytes() -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    bundle_source = make_validation_bundle_bytes()
    expected_bundle = bundle_source
    carrier = _carrier(profile, bundle_source)
    bundle_source = b'{"replacement":true}'
    recipe_source = b'{"recipe":true}'

    result = _build(program, recipe_source, carrier)
    recipe_source = b'{"replacement":true}'

    assert not isinstance(result, ValidationControlFailure)
    assert carrier.raw_bytes is expected_bundle
    assert result.invocation.raw_validation_bundle_bytes == expected_bundle
    assert result.invocation.raw_validation_bundle_bytes != bundle_source
    assert result.invocation.raw_recipe_bytes == b'{"recipe":true}'
    assert result.invocation.raw_recipe_bytes != recipe_source
    with pytest.raises(TypeError, match="exact built-in bytes"):
        _issue(profile, bytearray(expected_bundle))  # type: ignore[arg-type]


def test_carrier_retains_exact_profile_object_authority_for_invocation() -> None:
    program = _invocation_program()
    profile = _sealed_profile()
    carrier = _carrier(profile)

    result = _build(program, b"{}", carrier)

    assert not isinstance(result, ValidationControlFailure)
    assert carrier._profile is profile
    assert result.invocation.assembler_profile is profile
