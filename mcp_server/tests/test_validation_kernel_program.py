from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable

import pytest
from jsonschema import Draft202012Validator, ValidationError, validators

import rook.validation_kernel.budget as budget_module
import rook.validation_kernel.canonical_json as canonical_json_module
import rook.validation_kernel.parser as parser_module
import rook.validation_kernel.program as program_module
from rook.validation_kernel import (
    CORE_PROFILE,
    ExportTypeSpec,
    ImmutableCallableRecord,
    ImplementationSource,
    InputBinding,
    IssueSpec,
    PROGRAM_MANIFEST_SCHEMA,
    PROGRAM_MANIFEST_SCHEMA_FINGERPRINT,
    ProgramCompositionError,
    RuntimeBinding,
    RuntimeComponentSpec,
    RuntimeDependencySpec,
    SchemaEvaluatorSpec,
    TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA,
    ValidationProgramContribution,
    compose_and_seal_program,
    implementation_source_closure_for_modules,
    implementation_source_for_module,
    runtime_dependency_closure_for_modules,
    runtime_dependency_spec,
    runtime_implementation_fingerprint,
)
from rook.validation_kernel.budget import BudgetManifest, LM9A_BUDGET_MANIFEST
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
    normalized_source_fingerprint,
)
from rook.validation_kernel.owned_json import (
    JsonObject,
    count_json_nodes,
    own_trusted_json,
)
from rook.validation_kernel.schema_profile import (
    AdmittedSchema,
    SchemaAdmissionError,
    admit_schema,
    evaluate_schema,
)
from rook.validation_kernel.invocation import _program_is_valid

from tests._validation_kernel_fakes import (
    MutableCallable,
    MutableService,
    RUNTIME_REGISTRY,
    StaticService,
    UnboundService,
    alternate_beta_runner,
    beta_runner,
    disguised_class_function,
    extra_export_validator,
    immutable_record_dispatch,
    make_closure,
    make_program_contribution,
    replace_runtime_component,
)


def _host_json(value: object) -> object:
    return json.loads(canonical_json_bytes(value))


def _replace_phase(contribution: ValidationProgramContribution, phase_name: str, **changes: object) -> ValidationProgramContribution:
    phases = tuple(
        replace(phase, **changes) if phase.phase_name == phase_name else phase
        for phase in contribution.phases
    )
    return replace(contribution, phases=phases)


def _replace_binding(
    contribution: ValidationProgramContribution,
    phase_name: str,
    binding_name: str,
    **changes: object,
) -> ValidationProgramContribution:
    phase = next(phase for phase in contribution.phases if phase.phase_name == phase_name)
    bindings = tuple(
        replace(binding, **changes) if binding.input_name == binding_name else binding
        for binding in phase.input_bindings
    )
    return _replace_phase(contribution, phase_name, input_bindings=bindings)


def _assert_rejected(contribution: ValidationProgramContribution, match: str) -> None:
    with pytest.raises(ProgramCompositionError, match=match):
        compose_and_seal_program(contribution)


def _load_temp_module(tmp_path: Path, module_name: str, source: str) -> object:
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text(source, encoding="utf-8", newline="")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_temp_package(
    tmp_path: Path,
    package_name: str,
    sources: dict[str, str],
    entry_module: str,
) -> object:
    package_path = tmp_path / package_name
    package_path.mkdir()
    for relative_path, source in sources.items():
        path = package_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="")
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        return importlib.import_module(f"{package_name}.{entry_module}")
    finally:
        sys.path.remove(str(tmp_path))


def _check_draft_2020_12_schema(schema: object) -> None:
    """Task 4 registers its owned-value checker under this draft URI."""

    draft_uri = Draft202012Validator.META_SCHEMA["$id"]
    registered = validators._META_SCHEMAS[draft_uri]
    validators._META_SCHEMAS[draft_uri] = Draft202012Validator
    try:
        Draft202012Validator.check_schema(schema)
    finally:
        validators._META_SCHEMAS[draft_uri] = registered


def _replace_beta_from_module(
    contribution: ValidationProgramContribution,
    module: object,
) -> ValidationProgramContribution:
    target = getattr(module, "runner")
    updated = replace_runtime_component(
        contribution,
        kind="runner",
        component_id="beta",
        target=target,
        implementation_id="synthetic.runner.beta:v1",
    )
    return updated


def _with_derived_source_and_dependency_authority(
    contribution: ValidationProgramContribution,
) -> ValidationProgramContribution:
    components = (
        contribution.parser_profile.tokenizer,
        contribution.parser_profile.parser,
        contribution.parser_profile.canonicalizer,
        contribution.parser_profile.ledger,
        *(spec.evaluator for spec in contribution.schema_evaluator_profiles),
        *contribution.runners,
        *(export.validator for export in contribution.export_types),
    )
    module_names = tuple(
        sorted(
            {
                component.source_module for component in components
            }
            | {contribution.report_projection.source_module}
        )
    )
    direct_dependencies = tuple(
        sorted(
            {
                name
                for spec in contribution.schema_evaluator_profiles
                for name, _ in spec.profile.runtime_dependencies
            }
        )
    )
    return replace(
        contribution,
        implementation_sources=implementation_source_closure_for_modules(
            module_names
        ),
        runtime_dependencies=runtime_dependency_closure_for_modules(
            module_names,
            direct_dependencies,
        ),
    )


def _replace_report_schema(
    contribution: ValidationProgramContribution,
    schema_host: dict[str, object],
    *,
    use_core_profile: bool = False,
) -> ValidationProgramContribution:
    profile = CORE_PROFILE if use_core_profile else contribution.schema_evaluator_profiles[0].profile
    schema = admit_schema(
        contribution.report_projection.output_schema_id,
        own_trusted_json(schema_host),
        profile,
    )
    bindings = tuple(
        replace(
            binding,
            implementation_fingerprint=schema.schema_fingerprint,
            target=schema,
        )
        if (binding.binding_kind, binding.binding_id)
        == ("schema", contribution.report_projection.output_schema_id)
        else binding
        for binding in contribution.runtime_bindings
    )
    profiles = contribution.schema_evaluator_profiles
    if use_core_profile and all(
        spec.profile.profile_id != CORE_PROFILE.profile_id for spec in profiles
    ):
        evaluator = RuntimeComponentSpec(
            component_id=CORE_PROFILE.profile_id,
            implementation_id=CORE_PROFILE.evaluator_id,
            implementation_fingerprint=runtime_implementation_fingerprint(evaluate_schema),
            source_module=evaluate_schema.__module__,
        )
        profiles = profiles + (
            SchemaEvaluatorSpec(profile=CORE_PROFILE, evaluator=evaluator),
        )
        bindings = bindings + (
            RuntimeBinding(
                binding_kind="schema_evaluator",
                binding_id=CORE_PROFILE.profile_id,
                implementation_fingerprint=evaluator.implementation_fingerprint,
                target=evaluate_schema,
            ),
        )
    return replace(
        contribution,
        schema_evaluator_profiles=profiles,
        schemas=(schema,),
        report_projection=replace(
            contribution.report_projection,
            output_schema_fingerprint=schema.schema_fingerprint,
        ),
        runtime_bindings=bindings,
    )


def _forge_admitted_schema(
    source: AdmittedSchema,
    *,
    value: JsonObject | None = None,
    local_reference_count: int | None = None,
    maximum_reference_depth: int | None = None,
) -> AdmittedSchema:
    forged_value = source.value if value is None else value
    forged = object.__new__(AdmittedSchema)
    for field_name, field_value in (
        ("schema_id", source.schema_id),
        ("schema_fingerprint", canonical_fingerprint(forged_value)),
        ("profile_id", source.profile_id),
        ("schema_nodes", count_json_nodes(forged_value)),
        (
            "local_reference_count",
            source.local_reference_count
            if local_reference_count is None
            else local_reference_count,
        ),
        (
            "maximum_reference_depth",
            source.maximum_reference_depth
            if maximum_reference_depth is None
            else maximum_reference_depth,
        ),
        ("value", forged_value),
    ):
        object.__setattr__(forged, field_name, field_value)
    object.__setattr__(
        forged,
        "_AdmittedSchema__issuer_capability",
        object.__getattribute__(
            source, "_AdmittedSchema__issuer_capability"
        ),
    )
    return forged


def _replace_admitted_report_schema(
    contribution: ValidationProgramContribution,
    schema: AdmittedSchema,
) -> ValidationProgramContribution:
    bindings = tuple(
        replace(
            binding,
            implementation_fingerprint=schema.schema_fingerprint,
            target=schema,
        )
        if (binding.binding_kind, binding.binding_id)
        == ("schema", contribution.report_projection.output_schema_id)
        else binding
        for binding in contribution.runtime_bindings
    )
    return replace(
        contribution,
        schemas=(schema,),
        report_projection=replace(
            contribution.report_projection,
            output_schema_fingerprint=schema.schema_fingerprint,
        ),
        runtime_bindings=bindings,
    )


def test_program_seal_rejects_forged_schema_that_bypassed_profile_admission() -> None:
    contribution = make_program_contribution()
    source = contribution.schemas[0]
    host = _host_json(source.value)
    assert isinstance(host, dict)
    host["pattern"] = "forbidden"
    forged_value = own_trusted_json(host)
    assert type(forged_value) is JsonObject
    forged = _forge_admitted_schema(source, value=forged_value)
    assert program_module._is_admitted_schema(forged) is True
    drifted = _replace_admitted_report_schema(contribution, forged)
    binding = next(
        binding
        for binding in drifted.runtime_bindings
        if (binding.binding_kind, binding.binding_id)
        == ("schema", forged.schema_id)
    )
    assert binding.target is forged
    assert binding.implementation_fingerprint == forged.schema_fingerprint

    _assert_rejected(
        drifted,
        "schema admission authority is invalid:",
    )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("local_reference_count", 1),
        ("maximum_reference_depth", 1),
    ),
)
def test_program_seal_rederives_all_schema_reference_metadata(
    field_name: str,
    field_value: int,
) -> None:
    contribution = make_program_contribution()
    forged = _forge_admitted_schema(
        contribution.schemas[0],
        **{field_name: field_value},
    )
    assert program_module._is_admitted_schema(forged) is True
    drifted = _replace_admitted_report_schema(contribution, forged)
    binding = next(
        binding
        for binding in drifted.runtime_bindings
        if (binding.binding_kind, binding.binding_id)
        == ("schema", forged.schema_id)
    )
    assert binding.target is forged
    assert binding.implementation_fingerprint == forged.schema_fingerprint

    _assert_rejected(
        drifted,
        "schema admission authority is inconsistent:",
    )


def test_static_phase_contract_rejects_duplicate_identities_and_unknown_authority() -> None:
    contribution = make_program_contribution()
    alpha = contribution.phases[0]
    _assert_rejected(replace(contribution, phases=contribution.phases + (alpha,)), "duplicate phase")
    _assert_rejected(
        _replace_phase(
            contribution,
            "alpha",
            input_bindings=alpha.input_bindings + alpha.input_bindings,
        ),
        "duplicate input",
    )
    _assert_rejected(
        _replace_phase(
            contribution,
            "alpha",
            provided_outputs=alpha.provided_outputs + alpha.provided_outputs,
        ),
        "duplicate output",
    )
    _assert_rejected(_replace_phase(contribution, "alpha", runner_id="missing"), "unknown runner")
    _assert_rejected(
        _replace_phase(contribution, "alpha", permitted_diagnostic_codes=("missing",)),
        "unknown diagnostic",
    )
    _assert_rejected(
        replace(
            contribution,
            report_projection=replace(
                contribution.report_projection,
                required_for_compile_phases=("alpha", "missing"),
            ),
        ),
        "required-for-compile",
    )


def test_bindings_are_exact_and_data_dependencies_do_not_come_from_ordering() -> None:
    contribution = make_program_contribution()
    _assert_rejected(
        _replace_binding(contribution, "beta", "alpha_value", source_phase="missing"),
        "missing producer",
    )
    _assert_rejected(
        _replace_binding(contribution, "beta", "alpha_value", source_output="missing"),
        "unknown output",
    )
    _assert_rejected(
        _replace_binding(contribution, "beta", "alpha_value", expected_type="synthetic.beta:v1"),
        "type mismatch",
    )
    _assert_rejected(
        _replace_binding(contribution, "beta", "alpha_value", cardinality="many"),
        "cardinality mismatch",
    )
    _assert_rejected(
        _replace_binding(contribution, "beta", "alpha_value", source_input="recipe"),
        "ambiguous",
    )

    sealed = compose_and_seal_program(contribution)
    assert sealed.data_dependencies == MappingProxyType(
        {"alpha": (), "audit": (), "beta": ("alpha",)}
    )
    assert sealed.scheduling_dependencies == MappingProxyType(
        {"alpha": (), "audit": ("alpha",), "beta": ("alpha",)}
    )
    assert sealed.execution_order == ("alpha", "audit", "beta")


def test_cycles_unknown_ordering_and_invalid_output_status_contracts_fail() -> None:
    contribution = make_program_contribution()
    _assert_rejected(
        _replace_phase(contribution, "alpha", ordering_after=("beta",)),
        "cycle",
    )
    _assert_rejected(
        _replace_phase(contribution, "audit", ordering_after=("missing",)),
        "ordering producer",
    )
    output = contribution.phases[0].provided_outputs[0]
    _assert_rejected(
        _replace_phase(
            contribution,
            "alpha",
            provided_outputs=(replace(output, required_on_statuses=("failed",)),),
        ),
        "required status",
    )
    _assert_rejected(
        _replace_phase(
            contribution,
            "alpha",
            provided_outputs=(replace(output, permitted_on_statuses=("not_evaluated",)),),
        ),
        "permitted status",
    )
    _assert_rejected(
        _replace_phase(
            contribution,
            "alpha",
            provided_outputs=(replace(output, output_type="missing.export:v1"),),
        ),
        "unknown export type",
    )


def test_machine_ids_are_ascii_and_set_like_fields_use_utf16_order() -> None:
    contribution = make_program_contribution()
    _assert_rejected(
        _replace_phase(contribution, "alpha", runner_id="runner.\N{SNOWMAN}:v1"),
        "ASCII machine",
    )
    projection = replace(
        contribution.report_projection,
        writable_body_paths=(
            "/body/\ue000",
            "/body/\U00010000",
            "/body",
            "/phases",
            "/validation_context",
        ),
    )
    sealed = compose_and_seal_program(replace(contribution, report_projection=projection))
    manifest = json.loads(sealed.manifest_bytes)
    paths = manifest["report_projection"]["writable_body_paths"]
    assert paths.index("/body/\U00010000") < paths.index("/body/\ue000")


def test_program_and_assembler_schemas_are_valid_and_recursively_closed() -> None:
    schemas = (PROGRAM_MANIFEST_SCHEMA, TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA)
    for owned_schema in schemas:
        schema = _host_json(owned_schema)
        _check_draft_2020_12_schema(schema)
        stack = [schema]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                if current.get("type") == "object":
                    assert current.get("additionalProperties") is False
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)

    sealed = compose_and_seal_program(make_program_contribution())
    manifest = json.loads(sealed.manifest_bytes)
    validator = Draft202012Validator(_host_json(PROGRAM_MANIFEST_SCHEMA))
    validator.validate(manifest)
    manifest["phases"][0]["input_bindings"][0]["unknown"] = True
    with pytest.raises(ValidationError):
        validator.validate(manifest)

    assembler = {
        "schema": "rook.trusted_bundle_assembler_profile:v1",
        "profile_id": "synthetic.assembler:v1",
        "assembler_kind": "deterministic_fixture",
        "assembler_id": "synthetic.assembler:v1",
        "assembler_version": "v1",
        "implementation_fingerprint": "sha256:" + "1" * 64,
        "permitted_program_ids": ["synthetic.validation_program:v1"],
        "permitted_clock_sources": ["deterministic_fixture"],
        "profile_fingerprint": "sha256:" + "2" * 64,
    }
    assembler_validator = Draft202012Validator(
        _host_json(TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA)
    )
    assembler_validator.validate(assembler)
    assembler["unknown"] = True
    with pytest.raises(ValidationError):
        assembler_validator.validate(assembler)


def test_claimed_component_fingerprints_are_recomputed_by_fixed_seal() -> None:
    contribution = make_program_contribution()
    bad_runner = replace(
        contribution.runners[0],
        implementation_fingerprint="sha256:" + "0" * 64,
    )
    _assert_rejected(
        replace(contribution, runners=(bad_runner,) + contribution.runners[1:]),
        "fingerprint mismatch",
    )
    bad_source = replace(
        contribution.implementation_sources[0],
        source_fingerprint="sha256:" + "0" * 64,
    )
    _assert_rejected(
        replace(
            contribution,
            implementation_sources=(bad_source,) + contribution.implementation_sources[1:],
        ),
        "source fingerprint mismatch",
    )
    bad_profile = replace(
        contribution.schema_evaluator_profiles[0].profile,
        profile_fingerprint="sha256:" + "0" * 64,
    )
    _assert_rejected(
        replace(
            contribution,
            schema_evaluator_profiles=(
                replace(
                    contribution.schema_evaluator_profiles[0],
                    profile=bad_profile,
                ),
            ),
        ),
        "schema profile fingerprint mismatch",
    )


def test_report_projection_declares_exact_kernel_authority_and_no_overlap() -> None:
    contribution = make_program_contribution()
    projection = contribution.report_projection
    mutations = (
        (replace(projection, budget_receipt_path="/other"), "budget receipt"),
        (replace(projection, fingerprint_excluded_paths=()), "fingerprint exclusion"),
        (replace(projection, outer_envelope_field_count=20), "outer envelope"),
        (
            replace(
                projection,
                budget_receipt_path="/other_receipt",
                kernel_owned_paths=("/other_receipt", "/report_fingerprint"),
            ),
                "budget receipt",
        ),
        (
            replace(
                projection,
                writable_body_paths=projection.writable_body_paths + ("/validation_budget/observed",),
            ),
            "kernel-owned",
        ),
    )
    for candidate, message in mutations:
        _assert_rejected(replace(contribution, report_projection=candidate), message)


def test_kernel_report_roles_cannot_be_redefined_by_candidate_schema() -> None:
    contribution = make_program_contribution()
    extra_host = _host_json(contribution.schemas[0].value)
    assert isinstance(extra_host, dict)
    extra_properties = extra_host["properties"]
    assert isinstance(extra_properties, dict)
    extra_properties["kernel_extra"] = {"type": "string"}
    extra = _replace_report_schema(contribution, extra_host)
    extra = replace(
        extra,
        report_projection=replace(
            extra.report_projection,
            kernel_owned_paths=extra.report_projection.kernel_owned_paths
            + ("/kernel_extra",),
            outer_envelope_field_count=22,
        ),
    )
    _assert_rejected(extra, "fixed kernel-owned report paths")

    renamed_host = _host_json(contribution.schemas[0].value)
    assert isinstance(renamed_host, dict)
    renamed_properties = renamed_host["properties"]
    assert isinstance(renamed_properties, dict)
    renamed_properties["renamed_budget"] = renamed_properties.pop(
        "validation_budget"
    )
    required = renamed_host["required"]
    assert isinstance(required, list)
    required[required.index("validation_budget")] = "renamed_budget"
    renamed = _replace_report_schema(contribution, renamed_host)
    renamed = replace(
        renamed,
        report_projection=replace(
            renamed.report_projection,
            kernel_owned_paths=("/renamed_budget", "/report_fingerprint"),
            budget_receipt_path="/renamed_budget",
        ),
    )
    _assert_rejected(renamed, "fixed budget receipt path")

    fingerprint_host = _host_json(contribution.schemas[0].value)
    assert isinstance(fingerprint_host, dict)
    fingerprint_properties = fingerprint_host["properties"]
    assert isinstance(fingerprint_properties, dict)
    fingerprint_properties["renamed_fingerprint"] = fingerprint_properties.pop(
        "report_fingerprint"
    )
    fingerprint_required = fingerprint_host["required"]
    assert isinstance(fingerprint_required, list)
    fingerprint_required[
        fingerprint_required.index("report_fingerprint")
    ] = "renamed_fingerprint"
    renamed_fingerprint = _replace_report_schema(
        contribution,
        fingerprint_host,
    )
    renamed_fingerprint = replace(
        renamed_fingerprint,
        report_projection=replace(
            renamed_fingerprint.report_projection,
            report_fingerprint_path="/renamed_fingerprint",
            fingerprint_excluded_paths=("/renamed_fingerprint",),
            kernel_owned_paths=(
                "/renamed_fingerprint",
                "/validation_budget",
            ),
        ),
    )
    _assert_rejected(renamed_fingerprint, "fixed role")

    _assert_rejected(
        replace(
            contribution,
            report_projection=replace(
                contribution.report_projection,
                kernel_owned_paths=("/validation_budget",),
            ),
        ),
        "fixed kernel-owned report paths",
    )


def test_projection_writable_paths_resolve_exact_closed_schema_shapes() -> None:
    contribution = make_program_contribution()
    valid = replace(
        contribution,
        report_projection=replace(
            contribution.report_projection,
            writable_body_paths=contribution.report_projection.writable_body_paths
            + ("/body/optional", "/phases/0"),
        ),
    )
    compose_and_seal_program(valid)

    open_host = _host_json(contribution.schemas[0].value)
    assert isinstance(open_host, dict)
    open_body = open_host["properties"]["body"]
    assert isinstance(open_body, dict)
    del open_body["additionalProperties"]
    _assert_rejected(
        _replace_report_schema(contribution, open_host),
        "explicitly closed",
    )

    untyped_host = _host_json(contribution.schemas[0].value)
    assert isinstance(untyped_host, dict)
    untyped_body = untyped_host["properties"]["body"]
    assert isinstance(untyped_body, dict)
    del untyped_body["type"]
    _assert_rejected(
        _replace_report_schema(contribution, untyped_host),
        "ambiguous schema branch",
    )

    for keyword, value in (
        ("patternProperties", {"^extra$": {"type": "string"}}),
        ("unevaluatedProperties", False),
    ):
        ambiguous_object_host = _host_json(contribution.schemas[0].value)
        assert isinstance(ambiguous_object_host, dict)
        ambiguous_object_body = ambiguous_object_host["properties"]["body"]
        assert isinstance(ambiguous_object_body, dict)
        ambiguous_object_body[keyword] = value
        with pytest.raises(SchemaAdmissionError, match="forbidden keyword"):
            _replace_report_schema(
                contribution,
                ambiguous_object_host,
                use_core_profile=True,
            )

    for path, message in (
        ("/body/missing", "does not exist"),
        ("/body/optional/child", "closed or scalar"),
        ("/body/closed/missing", "does not exist"),
    ):
        _assert_rejected(
            replace(
                contribution,
                report_projection=replace(
                    contribution.report_projection,
                    writable_body_paths=contribution.report_projection.writable_body_paths
                    + (path,),
                ),
            ),
            message,
        )

    scalar_host = _host_json(contribution.schemas[0].value)
    assert isinstance(scalar_host, dict)
    scalar_body = scalar_host["properties"]["body"]
    assert isinstance(scalar_body, dict)
    scalar_properties = scalar_body["properties"]
    assert isinstance(scalar_properties, dict)
    scalar_properties["scalar_with_properties"] = {
        "type": "string",
        "properties": {"child": {"type": "string"}},
        "additionalProperties": False,
    }
    scalar = _replace_report_schema(contribution, scalar_host)
    scalar = replace(
        scalar,
        report_projection=replace(
            scalar.report_projection,
            writable_body_paths=scalar.report_projection.writable_body_paths
            + ("/body/scalar_with_properties/child",),
        ),
    )
    _assert_rejected(scalar, "closed or scalar")

    ambiguous_host = _host_json(contribution.schemas[0].value)
    assert isinstance(ambiguous_host, dict)
    body_schema = ambiguous_host["properties"]["body"]
    assert isinstance(body_schema, dict)
    body_properties = body_schema["properties"]
    assert isinstance(body_properties, dict)
    body_properties["ambiguous"] = {
        "anyOf": [{"type": "string"}, {"type": "integer"}]
    }
    ambiguous = _replace_report_schema(
        contribution,
        ambiguous_host,
        use_core_profile=True,
    )
    ambiguous = replace(
        ambiguous,
        report_projection=replace(
            ambiguous.report_projection,
            writable_body_paths=ambiguous.report_projection.writable_body_paths
            + ("/body/ambiguous",),
        ),
    )
    _assert_rejected(ambiguous, "ambiguous schema branch")


def test_candidate_canonicalizer_cannot_choose_program_fingerprint() -> None:
    contribution = make_program_contribution()
    sealed = compose_and_seal_program(contribution)
    repeated = compose_and_seal_program(contribution)
    assert repeated.program_fingerprint == sealed.program_fingerprint
    assert repeated.manifest_bytes == sealed.manifest_bytes
    manifest = json.loads(sealed.manifest_bytes)
    asserted_fingerprint = manifest.pop("program_fingerprint")
    assert asserted_fingerprint == sealed.program_fingerprint
    assert canonical_fingerprint(own_trusted_json(manifest)) == asserted_fingerprint
    assert sealed.resolve_manifest_bytes(asserted_fingerprint) == sealed.manifest_bytes
    with pytest.raises(KeyError):
        sealed.resolve_manifest_bytes("sha256:" + "0" * 64)
    assert PROGRAM_MANIFEST_SCHEMA_FINGERPRINT == canonical_fingerprint(PROGRAM_MANIFEST_SCHEMA)


def _custom_budget(profile_id: str) -> BudgetManifest:
    base = make_program_contribution().budget_manifest
    identity = own_trusted_json(
        {
            "profile_id": profile_id,
            "limits": _host_json(base.limits),
            "admission_order": "bundle_then_recipe_v1",
            "accounting_rules": "lm9a_kernel_controlled_v1",
            "seal_algorithm": "fixed_report_seal_v1",
        }
    )
    return BudgetManifest(
        profile_id=profile_id,
        limits=base.limits,
        limits_fingerprint=canonical_fingerprint(identity),
    )


def _insufficient_seal_budget() -> BudgetManifest:
    base = make_program_contribution().budget_manifest
    limits = _host_json(base.limits)
    assert isinstance(limits, dict)
    limits["report_seal_work_units"] = 1
    owned_limits = own_trusted_json(limits)
    assert isinstance(owned_limits, JsonObject)
    identity = own_trusted_json(
        {
            "profile_id": base.profile_id,
            "limits": limits,
            "admission_order": "bundle_then_recipe_v1",
            "accounting_rules": "lm9a_kernel_controlled_v1",
            "seal_algorithm": "fixed_report_seal_v1",
        }
    )
    return BudgetManifest(
        profile_id=base.profile_id,
        limits=owned_limits,
        limits_fingerprint=canonical_fingerprint(identity),
    )


def test_program_seal_rejects_an_insufficient_fixed_allowance() -> None:
    contribution = make_program_contribution()
    _assert_rejected(
        replace(contribution, budget_manifest=_insufficient_seal_budget()),
        "fixed LM9A budget manifest",
    )


def test_program_seal_requires_the_exact_fixed_lm9a_budget_manifest() -> None:
    contribution = make_program_contribution()
    for candidate in (
        _custom_budget("synthetic.budget:v2"),
        replace(LM9A_BUDGET_MANIFEST),
    ):
        _assert_rejected(
            replace(contribution, budget_manifest=candidate),
            "fixed LM9A budget manifest",
        )

    assert _program_is_valid(compose_and_seal_program(contribution)) is True


def test_kernel_owned_runtime_profile_is_fixed_to_invoked_implementations() -> None:
    contribution = make_program_contribution()
    profile = contribution.parser_profile
    bindings = {
        (binding.binding_kind, binding.binding_id): binding.target
        for binding in contribution.runtime_bindings
    }

    assert bindings[("tokenizer", profile.tokenizer.component_id)] is parser_module.parse_owned_json
    assert bindings[("parser", profile.parser.component_id)] is parser_module.parse_owned_json
    assert (
        bindings[("canonicalizer", profile.canonicalizer.component_id)]
        is canonical_json_module.canonical_fingerprint_metered
    )
    assert bindings[("ledger", profile.ledger.component_id)] is getattr(
        budget_module, "create_budget_ledger", None
    )

    _assert_rejected(
        replace(
            contribution,
            parser_profile=replace(profile, owned_value_abi="rook.owned_json:v2"),
        ),
        "fixed parser profile",
    )


def test_every_manifest_authority_category_moves_program_identity(
    tmp_path: Path,
) -> None:
    base = make_program_contribution()
    baseline = compose_and_seal_program(base).program_fingerprint

    changed: dict[str, ValidationProgramContribution] = {}
    core_evaluator = RuntimeComponentSpec(
        component_id=CORE_PROFILE.profile_id,
        implementation_id=CORE_PROFILE.evaluator_id,
        implementation_fingerprint=runtime_implementation_fingerprint(evaluate_schema),
        source_module=evaluate_schema.__module__,
    )
    changed["profile"] = replace(
        base,
        schema_evaluator_profiles=base.schema_evaluator_profiles
        + (SchemaEvaluatorSpec(profile=CORE_PROFILE, evaluator=core_evaluator),),
        runtime_bindings=base.runtime_bindings
        + (
            RuntimeBinding(
                binding_kind="schema_evaluator",
                binding_id=CORE_PROFILE.profile_id,
                implementation_fingerprint=core_evaluator.implementation_fingerprint,
                target=evaluate_schema,
            ),
        ),
    )
    extra_schema_value = own_trusted_json(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "string",
        }
    )
    extra_schema = admit_schema("synthetic.extra_schema:v1", extra_schema_value, base.schema_evaluator_profiles[0].profile)
    changed["schema"] = replace(
        base,
        schemas=base.schemas + (extra_schema,),
        runtime_bindings=base.runtime_bindings
        + (
            RuntimeBinding(
                binding_kind="schema",
                binding_id=extra_schema.schema_id,
                implementation_fingerprint=extra_schema.schema_fingerprint,
                target=extra_schema,
            ),
        ),
    )
    alpha_output = base.phases[0].provided_outputs[0]
    changed["phase"] = _replace_phase(
        base,
        "alpha",
        provided_outputs=(replace(alpha_output, required_on_statuses=("passed", "blocked")),),
    )
    changed["binding"] = _replace_binding(base, "alpha", "recipe", input_name="recipe_value")
    changed["ordering"] = _replace_phase(base, "beta", ordering_after=("audit",))
    changed["runner"] = replace(
        base,
        runners=(replace(base.runners[0], implementation_id="synthetic.runner.alpha:v2"),)
        + base.runners[1:],
    )
    changed["issue"] = replace(
        base,
        issue_vocabulary=base.issue_vocabulary
        + (IssueSpec(code="synthetic_information", classification="diagnostic"),),
    )
    extra_component = RuntimeComponentSpec(
        component_id="synthetic.extra:v1",
        implementation_id="synthetic.export.extra:v1",
        implementation_fingerprint=runtime_implementation_fingerprint(extra_export_validator),
        source_module=extra_export_validator.__module__,
    )
    changed["export"] = replace(
        base,
        export_types=base.export_types
        + (ExportTypeSpec(export_type="synthetic.extra:v1", validator=extra_component),),
        runtime_bindings=base.runtime_bindings
        + (
            RuntimeBinding(
                binding_kind="export_type",
                binding_id=extra_component.component_id,
                implementation_fingerprint=extra_component.implementation_fingerprint,
                target=extra_export_validator,
            ),
        ),
    )
    dependency_runner = _load_temp_module(
        tmp_path,
        "synthetic_dependency_identity",
        "import idna\ndef runner(*args):\n    return idna\n",
    )
    changed["runtime_dependency"] = _with_derived_source_and_dependency_authority(
        _replace_beta_from_module(base, dependency_runner)
    )
    changed["projection"] = replace(
        base,
        report_projection=replace(
            base.report_projection,
            writable_body_paths=base.report_projection.writable_body_paths + ("/body/optional",),
        ),
    )

    fingerprints = {
        category: compose_and_seal_program(candidate).program_fingerprint
        for category, candidate in changed.items()
    }
    assert all(fingerprint != baseline for fingerprint in fingerprints.values())
    assert len(set(fingerprints.values())) == len(fingerprints)


def test_normalized_source_change_moves_identity_and_import_guards_are_closed(tmp_path: Path) -> None:
    base = make_program_contribution()
    first = _load_temp_module(
        tmp_path,
        "synthetic_source_a",
        "def runner(*args):\r\n    return ('a',)\r\n",
    )
    second = _load_temp_module(
        tmp_path,
        "synthetic_source_b",
        "def runner(*args):\n    return ('b',)\n",
    )
    first_contribution = _replace_beta_from_module(base, first)
    second_contribution = _replace_beta_from_module(base, second)
    first_program = compose_and_seal_program(first_contribution)
    second_program = compose_and_seal_program(second_contribution)
    assert first_program.program_fingerprint != second_program.program_fingerprint
    assert implementation_source_for_module(first.__name__).source_fingerprint == normalized_source_fingerprint(
        Path(first.__file__).read_bytes()
    )

    dynamic = _load_temp_module(
        tmp_path,
        "synthetic_dynamic_import",
        "def runner(*args):\n    return __import__('math')\n",
    )
    _assert_rejected(_replace_beta_from_module(base, dynamic), "dynamic import")
    dynamic_importlib = _load_temp_module(
        tmp_path,
        "synthetic_importlib_import",
        "import importlib\ndef runner(*args):\n    return importlib.import_module('math')\n",
    )
    _assert_rejected(
        _replace_beta_from_module(base, dynamic_importlib),
        "dynamic import",
    )

    helper = tmp_path / "synthetic_hidden_helper.py"
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        undeclared = _load_temp_module(
            tmp_path,
            "synthetic_undeclared_import",
            "import synthetic_hidden_helper\ndef runner(*args):\n    return synthetic_hidden_helper.VALUE\n",
        )
        _assert_rejected(
            _replace_beta_from_module(base, undeclared),
            "missing implementation source",
        )
    finally:
        sys.path.remove(str(tmp_path))

    undeclared_dependency = _load_temp_module(
        tmp_path,
        "synthetic_undeclared_dependency",
        "import idna\ndef runner(*args):\n    return idna\n",
    )
    dependency_contribution = _replace_beta_from_module(
        base, undeclared_dependency
    )
    _assert_rejected(dependency_contribution, "missing runtime dependency")
    compose_and_seal_program(
        _with_derived_source_and_dependency_authority(dependency_contribution)
    )

    unresolved_dependency = _load_temp_module(
        tmp_path,
        "synthetic_unresolved_dependency",
        (
            "def runner(*args):\n"
            "    import synthetic_distribution_that_does_not_exist\n"
            "    return synthetic_distribution_that_does_not_exist\n"
        ),
    )
    _assert_rejected(
        _replace_beta_from_module(base, unresolved_dependency),
        "cannot be resolved to product, standard-library, or distribution authority",
    )


def test_product_source_declarations_equal_the_exact_transitive_reachable_set(
    tmp_path: Path,
) -> None:
    package_name = "synthetic_product_closure"
    entry = _load_temp_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "from .reexported import PACKAGE_MARKER\n",
            "entry.py": (
                "from . import helper\n"
                "def runner(*args):\n"
                "    return helper.result()\n"
            ),
            "helper.py": (
                "from .deep import VALUE\n"
                "def result():\n"
                "    return VALUE\n"
            ),
            "deep.py": "VALUE = ('sealed',)\n",
            "reexported.py": "PACKAGE_MARKER = 'reachable-via-package-init'\n",
            "unrelated.py": "VALUE = 'not behavior'\n",
        },
        "entry",
    )
    contribution = _replace_beta_from_module(make_program_contribution(), entry)
    reachable_names = {
        package_name,
        f"{package_name}.entry",
        f"{package_name}.helper",
        f"{package_name}.deep",
        f"{package_name}.reexported",
    }
    sources = {
        source.module_name: source for source in contribution.implementation_sources
    }
    sources.update(
        {
            module_name: implementation_source_for_module(module_name)
            for module_name in reachable_names
        }
    )
    exact = replace(contribution, implementation_sources=tuple(sources.values()))

    sealed = compose_and_seal_program(exact)
    manifested = {
        item["module_name"]
        for item in json.loads(sealed.manifest_bytes)["implementation_sources"]
        if item["module_name"].startswith(package_name)
    }
    assert manifested == reachable_names

    missing = tuple(
        source
        for source in exact.implementation_sources
        if source.module_name != f"{package_name}.deep"
    )
    _assert_rejected(
        replace(exact, implementation_sources=missing),
        "missing implementation source",
    )
    _assert_rejected(
        replace(
            exact,
            implementation_sources=exact.implementation_sources
            + (implementation_source_for_module(f"{package_name}.unrelated"),),
        ),
        "extra implementation source",
    )


def test_package_initializers_are_full_behavior_sources(tmp_path: Path) -> None:
    package_name = "synthetic_initializer_closure"
    entry = _load_temp_package(
        tmp_path,
        package_name,
        {
            "__init__.py": (
                "def helper():\n"
                "    from .secret import VALUE\n"
                "    return VALUE\n"
            ),
            "entry.py": (
                f"import {package_name}.submodule\n"
                "def runner(*args):\n"
                f"    return {package_name}.helper()\n"
            ),
            "submodule.py": "MARKER = 'reachable'\n",
            "secret.py": "VALUE = ('sealed-secret',)\n",
            "unrelated.py": "VALUE = 'not behavior'\n",
        },
        "entry",
    )
    contribution = _with_derived_source_and_dependency_authority(
        _replace_beta_from_module(make_program_contribution(), entry)
    )
    expected = {
        package_name,
        f"{package_name}.entry",
        f"{package_name}.secret",
        f"{package_name}.submodule",
    }
    derived = {
        source.module_name
        for source in contribution.implementation_sources
        if source.module_name == package_name
        or source.module_name.startswith(package_name + ".")
    }
    assert derived == expected

    sealed = compose_and_seal_program(contribution)
    manifested = {
        item["module_name"]
        for item in json.loads(sealed.manifest_bytes)["implementation_sources"]
        if item["module_name"] == package_name
        or item["module_name"].startswith(package_name + ".")
    }
    assert manifested == expected

    missing_secret = tuple(
        source
        for source in contribution.implementation_sources
        if source.module_name != f"{package_name}.secret"
    )
    _assert_rejected(
        replace(contribution, implementation_sources=missing_secret),
        "missing implementation source",
    )
    _assert_rejected(
        replace(
            contribution,
            implementation_sources=contribution.implementation_sources
            + (implementation_source_for_module(f"{package_name}.unrelated"),),
        ),
        "extra implementation source",
    )


def test_all_lexical_imports_close_direct_and_aliased_package_helpers(
    tmp_path: Path,
) -> None:
    relative_closures: dict[str, set[str]] = {}
    alias_entry: object | None = None
    alias_contribution: ValidationProgramContribution | None = None
    alias_fingerprint: str | None = None
    alias_package_name = ""

    for mode, runner_body in (
        ("direct", "    return {package}.helper()\n"),
        (
            "alias",
            "    package_alias = {package}\n"
            "    return package_alias.helper()\n",
        ),
    ):
        package_name = f"synthetic_lexical_{mode}"
        entry = _load_temp_package(
            tmp_path,
            package_name,
            {
                "__init__.py": (
                    "def helper():\n"
                    "    from .secret import VALUE\n"
                    "    return VALUE\n"
                ),
                "entry.py": (
                    f"import {package_name}.submodule\n"
                    "def runner(*args):\n"
                    + runner_body.format(package=package_name)
                ),
                "secret.py": "VALUE = ('sealed-secret',)\n",
                "submodule.py": "MARKER = 'reachable'\n",
                "unrelated.py": "VALUE = 'not behavior'\n",
            },
            "entry",
        )
        contribution = _with_derived_source_and_dependency_authority(
            _replace_beta_from_module(make_program_contribution(), entry)
        )
        expected = {
            package_name,
            f"{package_name}.entry",
            f"{package_name}.secret",
            f"{package_name}.submodule",
        }
        declared = {
            source.module_name
            for source in contribution.implementation_sources
            if source.module_name == package_name
            or source.module_name.startswith(package_name + ".")
        }
        assert declared == expected
        relative_closures[mode] = {
            module_name.removeprefix(package_name) for module_name in declared
        }

        sealed = compose_and_seal_program(contribution)
        manifested = {
            item["module_name"]
            for item in json.loads(sealed.manifest_bytes)["implementation_sources"]
            if item["module_name"] == package_name
            or item["module_name"].startswith(package_name + ".")
        }
        assert manifested == expected

        if mode == "alias":
            alias_entry = entry
            alias_contribution = contribution
            alias_fingerprint = sealed.program_fingerprint
            alias_package_name = package_name

    assert relative_closures["direct"] == relative_closures["alias"]
    assert relative_closures["alias"] == {
        "",
        ".entry",
        ".secret",
        ".submodule",
    }
    assert alias_entry is not None
    assert alias_contribution is not None
    assert alias_fingerprint is not None

    _assert_rejected(
        replace(
            alias_contribution,
            implementation_sources=tuple(
                source
                for source in alias_contribution.implementation_sources
                if source.module_name != f"{alias_package_name}.secret"
            ),
        ),
        "missing implementation source",
    )

    secret_path = tmp_path / alias_package_name / "secret.py"
    secret_path.write_text(
        "VALUE = ('changed-secret',)\n",
        encoding="utf-8",
        newline="",
    )
    changed = compose_and_seal_program(
        _with_derived_source_and_dependency_authority(
            _replace_beta_from_module(make_program_contribution(), alias_entry)
        )
    )
    assert changed.program_fingerprint != alias_fingerprint


def test_all_lexical_imports_include_every_nested_package_initializer(
    tmp_path: Path,
) -> None:
    package_name = "synthetic_nested_lexical_closure"
    entry = _load_temp_package(
        tmp_path,
        package_name,
        {
            "__init__.py": (
                "def helper():\n"
                "    from .secret import VALUE\n"
                "    return VALUE\n"
            ),
            "nested/__init__.py": "NESTED_MARKER = 'reachable'\n",
            "nested/entry.py": (
                f"import {package_name}.nested.submodule\n"
                "def runner(*args):\n"
                f"    package_alias = {package_name}\n"
                "    return package_alias.helper()\n"
            ),
            "nested/submodule.py": "SUBMODULE_MARKER = 'reachable'\n",
            "secret.py": "VALUE = ('nested-secret',)\n",
        },
        "nested.entry",
    )
    contribution = _with_derived_source_and_dependency_authority(
        _replace_beta_from_module(make_program_contribution(), entry)
    )
    expected = {
        package_name,
        f"{package_name}.nested",
        f"{package_name}.nested.entry",
        f"{package_name}.nested.submodule",
        f"{package_name}.secret",
    }
    declared = {
        source.module_name
        for source in contribution.implementation_sources
        if source.module_name == package_name
        or source.module_name.startswith(package_name + ".")
    }
    assert declared == expected


@pytest.mark.parametrize(
    "source",
    (
        "import builtins as b\ndef runner(*args):\n    return b.__import__('math')\n",
        "from builtins import __import__ as load\ndef runner(*args):\n    return load('math')\n",
        "from importlib import import_module as load\ndef runner(*args):\n    return load('math')\n",
        "import importlib as il\ndef runner(*args):\n    return il.import_module('math')\n",
        "load = __import__\ndef runner(*args):\n    return load('math')\n",
        "def runner(*args, load=__import__):\n    return load('math')\n",
        "import importlib as il\nload = il.import_module\ndef runner(*args):\n    return load('math')\n",
        "import importlib\nil = importlib\ndef runner(*args):\n    return il.import_module('math')\n",
        (
            "import builtins as b\n"
            "load = getattr(b, '__import__')\n"
            "def runner(*args):\n"
            "    return load('math')\n"
        ),
        (
            "import importlib as il\n"
            "load = getattr(il, 'import_module')\n"
            "def runner(*args):\n"
            "    return load('math')\n"
        ),
        (
            "import builtins as b\n"
            "load = b.__dict__['__import__']\n"
            "def runner(*args):\n"
            "    return load('math')\n"
        ),
        (
            "import importlib as il\n"
            "load = il.__dict__['import_module']\n"
            "def runner(*args):\n"
            "    return load('math')\n"
        ),
        (
            "import importlib\n"
            "class Holder:\n"
            "    pass\n"
            "holder = Holder()\n"
            "holder.load = importlib.import_module\n"
            "def runner(*args):\n"
            "    return holder.load('math')\n"
        ),
        (
            "import importlib\n"
            "loaders = {'module': importlib.import_module}\n"
            "def runner(*args):\n"
            "    return loaders['module']('math')\n"
        ),
        (
            "def runner(*args):\n"
            "    return __builtins__['__import__']('math')\n"
        ),
        (
            "import importlib\n"
            "def runner(*args):\n"
            "    return importlib.__dict__.get('import_module')('math')\n"
        ),
        (
            "import importlib.metadata as metadata_api\n"
            "def runner(*args):\n"
            "    return metadata_api.import_module('math')\n"
        ),
        (
            "import importlib.metadata as metadata_api\n"
            "def runner(*args):\n"
            "    return metadata_api.__dict__['import_module']('math')\n"
        ),
        (
            "import importlib.metadata as metadata_api\n"
            "def runner(*args):\n"
            "    return metadata_api.__dict__.get('import_module')('math')\n"
        ),
        (
            "import importlib.metadata as metadata_api\n"
            "def runner(*args):\n"
            "    return getattr(metadata_api, 'import_module')('math')\n"
        ),
        (
            "import importlib.metadata as metadata_api\n"
            "loader = metadata_api.import_module\n"
            "def runner(*args):\n"
            "    return loader('math')\n"
        ),
        (
            "from importlib.metadata import import_module as loader\n"
            "def runner(*args):\n"
            "    return loader('math')\n"
        ),
    ),
)
def test_dynamic_import_alias_forms_are_rejected(
    tmp_path: Path,
    source: str,
) -> None:
    module_name = f"synthetic_dynamic_alias_{abs(hash(source))}"
    module = _load_temp_module(tmp_path, module_name, source)
    _assert_rejected(
        _replace_beta_from_module(make_program_contribution(), module),
        "dynamic import",
    )


def test_static_imports_and_safe_importlib_submodules_are_allowed(
    tmp_path: Path,
) -> None:
    module = _load_temp_module(
        tmp_path,
        "synthetic_safe_static_imports",
        (
            "import math\n"
            "import importlib.metadata as metadata_api\n"
            "from importlib import util as importlib_util\n"
            "def runner(*args):\n"
            "    return math.pi, metadata_api.version, importlib_util.resolve_name\n"
        ),
    )
    compose_and_seal_program(
        _with_derived_source_and_dependency_authority(
            _replace_beta_from_module(make_program_contribution(), module)
        )
    )


def test_runtime_bindings_are_exact_and_reject_unsafe_callable_shapes() -> None:
    contribution = make_program_contribution()
    first = contribution.runtime_bindings[0]
    _assert_rejected(replace(contribution, runtime_bindings=contribution.runtime_bindings[1:]), "missing runtime binding")
    _assert_rejected(replace(contribution, runtime_bindings=contribution.runtime_bindings + (first,)), "duplicate runtime binding")
    _assert_rejected(
        replace(
            contribution,
            runtime_bindings=contribution.runtime_bindings
            + (
                RuntimeBinding(
                    binding_kind="runner",
                    binding_id="extra",
                    implementation_fingerprint=first.implementation_fingerprint,
                    target=first.target,
                ),
            ),
        ),
        "extra runtime binding",
    )
    bad = replace(first, implementation_fingerprint="sha256:" + "0" * 64)
    _assert_rejected(replace(contribution, runtime_bindings=(bad,) + contribution.runtime_bindings[1:]), "runtime binding fingerprint")

    beta_index = next(
        index
        for index, binding in enumerate(contribution.runtime_bindings)
        if (binding.binding_kind, binding.binding_id) == ("runner", "beta")
    )
    swapped = list(contribution.runtime_bindings)
    swapped[beta_index] = replace(
        swapped[beta_index],
        target=alternate_beta_runner,
    )
    _assert_rejected(
        replace(contribution, runtime_bindings=tuple(swapped)),
        "runtime component fingerprint",
    )
    for target, message in (
        (make_closure(), "closure"),
        (MutableCallable(), "callable instance"),
        (MutableService().run, "bound method"),
    ):
        bindings = list(contribution.runtime_bindings)
        bindings[beta_index] = replace(bindings[beta_index], target=target)
        _assert_rejected(replace(contribution, runtime_bindings=tuple(bindings)), message)

    for target in (StaticService.run, UnboundService.run, disguised_class_function):
        with pytest.raises(ProgramCompositionError, match="module-level"):
            replace_runtime_component(
                contribution,
                kind="runner",
                component_id="beta",
                target=target,
            )


def test_module_functions_and_immutable_callable_records_pass_and_registry_is_captured() -> None:
    contribution = make_program_contribution()
    sealed = compose_and_seal_program(contribution)
    selected = sealed.resolve_runtime_binding("runner", "beta")
    assert selected is beta_runner
    RUNTIME_REGISTRY[("runner", "beta")] = alternate_beta_runner
    assert sealed.resolve_runtime_binding("runner", "beta") is selected

    state = own_trusted_json({"mode": "immutable"})
    assert isinstance(state, JsonObject)
    record = ImmutableCallableRecord(function=immutable_record_dispatch, state=state)
    record_contribution = replace_runtime_component(
        contribution,
        kind="runner",
        component_id="beta",
        target=record,
        implementation_id="synthetic.runner.beta_record:v1",
    )
    record_program = compose_and_seal_program(record_contribution)
    assert record_program.resolve_runtime_binding("runner", "beta") is record
    assert record(object()) is state
    manifest = json.loads(record_program.manifest_bytes)
    beta_manifest = next(
        runner for runner in manifest["runners"] if runner["component_id"] == "beta"
    )
    assert beta_manifest["callable_record_state_canonical_json"] == canonical_json_bytes(
        state
    ).decode("utf-8")
    assert beta_manifest["callable_record_state_fingerprint"] == canonical_fingerprint(
        state
    )


def test_sealed_program_storage_is_transitively_immutable_and_exact_python_identity_is_manifested() -> None:
    sealed = compose_and_seal_program(make_program_contribution())
    assert type(sealed.phases) is tuple
    assert type(sealed.data_dependencies) is MappingProxyType
    assert type(sealed.scheduling_dependencies) is MappingProxyType
    assert type(sealed.runtime_binding_keys) is tuple
    with pytest.raises(TypeError):
        sealed.data_dependencies["alpha"] = ("beta",)  # type: ignore[index]

    manifest = json.loads(sealed.manifest_bytes)
    runtime = manifest["python_runtime"]
    assert runtime == {
        "cache_tag": sys.implementation.cache_tag,
        "implementation": sys.implementation.name,
        "version": list(sys.version_info[:5]),
        "runtime_fingerprint": runtime["runtime_fingerprint"],
    }
    assert runtime["runtime_fingerprint"].startswith("sha256:")


def test_third_party_projection_has_stable_relative_hashed_records() -> None:
    assert program_module._stable_distribution_path(
        r"C:\Users\candidate\wheel\module.py"
    ) is None
    assert program_module._stable_distribution_path(
        "../candidate-cache/module.py"
    ) is None
    sealed = compose_and_seal_program(make_program_contribution())
    dependencies = json.loads(sealed.manifest_bytes)["runtime_dependencies"]
    assert dependencies
    for dependency in dependencies:
        assert dependency["distribution_fingerprint"].startswith("sha256:")
        assert dependency["file_records"]
        for record in dependency["file_records"]:
            path = record["path"]
            assert not Path(path).is_absolute()
            assert "__pycache__" not in path
            assert not path.endswith((".pyc", ".pyo"))
            assert record["sha256"].startswith("sha256:")
        for behavior_file in dependency["behavior_files"]:
            assert behavior_file["sha256"].startswith("sha256:")

    dependency = make_program_contribution().runtime_dependencies[0]
    wrong = replace(dependency, expected_version="0.invalid")
    contribution = make_program_contribution()
    _assert_rejected(
        replace(contribution, runtime_dependencies=(wrong,) + contribution.runtime_dependencies[1:]),
        "dependency version",
    )


def test_runtime_dependency_closure_is_transitive_normalized_and_exact() -> None:
    contribution = make_program_contribution()
    sealed = compose_and_seal_program(contribution)
    dependencies = json.loads(sealed.manifest_bytes)["runtime_dependencies"]
    names = [dependency["distribution_name"] for dependency in dependencies]
    expected = {
        "attrs",
        "jsonschema",
        "jsonschema-specifications",
        "packaging",
        "referencing",
        "rpds-py",
        "typing-extensions",
    }
    assert set(names) == expected
    assert len(names) == len(set(names))
    assert all(name == re.sub(r"[-_.]+", "-", name).lower() for name in names)
    for dependency in dependencies:
        requirements = dependency["active_runtime_requirements"]
        assert requirements == sorted(
            requirements,
            key=lambda requirement: requirement["distribution_name"],
        )
        assert all(
            requirement["distribution_name"] in expected
            for requirement in requirements
        )

    missing_attrs = tuple(
        dependency
        for dependency in contribution.runtime_dependencies
        if dependency.distribution_name != "attrs"
    )
    _assert_rejected(
        replace(contribution, runtime_dependencies=missing_attrs),
        "missing runtime dependency",
    )

    jsonschema_dependency = next(
        dependency
        for dependency in contribution.runtime_dependencies
        if dependency.distribution_name == "jsonschema"
    )
    assert runtime_dependency_spec("JSONSchema") == runtime_dependency_spec(
        "jsonschema"
    )
    for alias, message in (
        ("JSONSchema", "duplicate runtime dependency identity"),
        ("json_schema", "PEP 503 normalized"),
    ):
        duplicate_alias = replace(
            jsonschema_dependency,
            distribution_name=alias,
        )
        _assert_rejected(
            replace(
                contribution,
                runtime_dependencies=contribution.runtime_dependencies
                + (duplicate_alias,),
            ),
            message,
        )
    _assert_rejected(
        replace(
            contribution,
            runtime_dependencies=contribution.runtime_dependencies
            + (runtime_dependency_spec("idna"),),
        ),
        "extra runtime dependency",
    )


def test_no_partial_program_escapes_failed_one_shot_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    contribution = make_program_contribution()
    observed: list[object] = []

    original = program_module._ValidationProgramBuilder

    class ObservingBuilder(original):
        def seal(self) -> object:
            try:
                return super().seal()
            finally:
                observed.append(self)

    monkeypatch.setattr(program_module, "_ValidationProgramBuilder", ObservingBuilder)
    _assert_rejected(
        replace(contribution, phases=contribution.phases + (contribution.phases[0],)),
        "duplicate phase",
    )
    assert len(observed) == 1
    builder = observed[0]
    assert builder.consumed is True
    assert not hasattr(builder, "program")
    with pytest.raises(RuntimeError, match="consumed"):
        builder.seal()


def test_public_dataclass_contracts_are_frozen_slotted_and_closed() -> None:
    contribution = make_program_contribution()
    contracts = (
        contribution.parser_profile,
        contribution.phases[0],
        contribution.phases[0].input_bindings[0],
        contribution.phases[0].provided_outputs[0],
        contribution.report_projection,
        contribution,
    )
    for contract in contracts:
        assert not hasattr(contract, "__dict__")
        with pytest.raises((AttributeError, TypeError)):
            setattr(contract, fields(contract)[0].name, "changed")
