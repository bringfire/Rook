from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable

import pytest
from jsonschema import Draft202012Validator, ValidationError, validators

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
    implementation_source_for_module,
    runtime_dependency_spec,
    runtime_implementation_fingerprint,
)
from rook.validation_kernel.budget import BudgetManifest
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_json_bytes,
    normalized_source_fingerprint,
)
from rook.validation_kernel.owned_json import JsonObject, own_trusted_json
from rook.validation_kernel.schema_profile import admit_schema, evaluate_schema

from tests._validation_kernel_fakes import (
    MutableCallable,
    MutableService,
    RUNTIME_REGISTRY,
    alternate_beta_runner,
    beta_runner,
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
        writable_body_paths=("/\ue000", "/\U00010000", "/body", "/phases", "/validation_context"),
    )
    sealed = compose_and_seal_program(replace(contribution, report_projection=projection))
    manifest = json.loads(sealed.manifest_bytes)
    paths = manifest["report_projection"]["writable_body_paths"]
    assert paths.index("/\U00010000") < paths.index("/\ue000")


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
            "output schema",
        ),
        (
            replace(
                projection,
                writable_body_paths=projection.writable_body_paths + ("/budget_receipt/observed",),
            ),
            "kernel-owned",
        ),
    )
    for candidate, message in mutations:
        _assert_rejected(replace(contribution, report_projection=candidate), message)


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
        "seal allowance",
    )


def test_every_manifest_authority_category_moves_program_identity() -> None:
    base = make_program_contribution()
    baseline = compose_and_seal_program(base).program_fingerprint

    changed: dict[str, ValidationProgramContribution] = {}
    changed["budget"] = replace(base, budget_manifest=_custom_budget("synthetic.budget:v2"))
    changed["parser"] = replace(
        base,
        parser_profile=replace(base.parser_profile, owned_value_abi="rook.owned_json:v2"),
    )
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
    changed["runtime_dependency"] = replace(
        base,
        runtime_dependencies=base.runtime_dependencies + (runtime_dependency_spec("attrs"),),
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
        _assert_rejected(_replace_beta_from_module(base, undeclared), "undeclared in-package")
    finally:
        sys.path.remove(str(tmp_path))

    undeclared_dependency = _load_temp_module(
        tmp_path,
        "synthetic_undeclared_dependency",
        "import attrs\ndef runner(*args):\n    return attrs\n",
    )
    dependency_contribution = _replace_beta_from_module(
        base, undeclared_dependency
    )
    _assert_rejected(dependency_contribution, "undeclared runtime dependency")
    compose_and_seal_program(
        replace(
            dependency_contribution,
            runtime_dependencies=dependency_contribution.runtime_dependencies
            + (runtime_dependency_spec("attrs"),),
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
