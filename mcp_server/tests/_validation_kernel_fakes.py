"""Synthetic sealed-program declarations shared by validation-kernel tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from rook.validation_kernel import (
    ExportTypeSpec,
    ImplementationSource,
    InputBinding,
    InvocationInputSpec,
    IssueSpec,
    ParserProfileSpec,
    PhaseSpec,
    ProgramConstantSpec,
    ProvidedOutput,
    ReportProjectionSpec,
    RuntimeBinding,
    RuntimeComponentSpec,
    SchemaEvaluatorSpec,
    ValidationProgramContribution,
    implementation_source_for_module,
    runtime_dependency_spec,
    runtime_implementation_fingerprint,
)
from rook.validation_kernel.budget import LM9A_BUDGET_MANIFEST
from rook.validation_kernel.canonical_json import canonical_json_bytes
from rook.validation_kernel.owned_json import JsonString, own_trusted_json
from rook.validation_kernel.schema_profile import (
    PAYLOAD_PROFILE,
    admit_schema,
    evaluate_schema,
)


def fake_tokenizer(*args: object, **kwargs: object) -> tuple[object, ...]:
    return args + tuple(sorted(kwargs.items()))


def fake_parser(value: object) -> object:
    return value


def candidate_canonicalizer(_: object) -> bytes:
    """A valid runtime binding that must never certify the program manifest."""

    return b"candidate-controlled-canonicalization"


def fake_ledger_factory() -> tuple[str]:
    return ("ledger",)


def alpha_runner(*_: object) -> tuple[str]:
    return ("alpha",)


def audit_runner(*_: object) -> tuple[str]:
    return ("audit",)


def beta_runner(*_: object) -> tuple[str]:
    return ("beta",)


def alternate_beta_runner(*_: object) -> tuple[str]:
    return ("beta-alternate",)


def alpha_export_validator(_: object) -> bool:
    return True


def beta_export_validator(_: object) -> bool:
    return True


def extra_export_validator(_: object) -> bool:
    return True


def report_projection(_: object, __: object) -> None:
    return None


def immutable_record_dispatch(state: object, *_: object) -> object:
    return state


def make_closure() -> object:
    captured = "mutable authority"

    def closure(*_: object) -> str:
        return captured

    return closure


class MutableCallable:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_: object) -> int:
        self.calls += 1
        return self.calls


class MutableService:
    def run(self, *_: object) -> None:
        return None


RUNTIME_REGISTRY: dict[tuple[str, str], object] = {}


def _component(component_id: str, implementation_id: str, target: object) -> RuntimeComponentSpec:
    function = getattr(target, "function", None)
    module_name = (
        function.__module__
        if function is not None
        else getattr(target, "__module__", None)
    )
    if type(module_name) is not str:
        raise AssertionError("synthetic runtime target has no source module")
    return RuntimeComponentSpec(
        component_id=component_id,
        implementation_id=implementation_id,
        implementation_fingerprint=runtime_implementation_fingerprint(target),
        source_module=module_name,
    )


def _binding(kind: str, component: RuntimeComponentSpec, target: object) -> RuntimeBinding:
    return RuntimeBinding(
        binding_kind=kind,
        binding_id=component.component_id,
        implementation_fingerprint=component.implementation_fingerprint,
        target=target,
    )


def _output_schema() -> object:
    value = own_trusted_json(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "body": {"type": "object", "additionalProperties": False},
                "validation_context": {
                    "type": "object",
                    "additionalProperties": False,
                },
                "phases": {"type": "array", "items": {"type": "string"}},
                "budget_receipt": {
                    "type": "object",
                    "additionalProperties": False,
                },
                "report_fingerprint": {"type": "string"},
            },
            "required": [
                "body",
                "validation_context",
                "phases",
                "budget_receipt",
                "report_fingerprint",
            ],
            "additionalProperties": False,
        }
    )
    return admit_schema("synthetic.report:v1", value, PAYLOAD_PROFILE)


def make_program_contribution() -> ValidationProgramContribution:
    tokenizer = _component("synthetic.tokenizer:v1", "synthetic.tokenizer_impl:v1", fake_tokenizer)
    parser = _component("synthetic.parser:v1", "synthetic.parser_impl:v1", fake_parser)
    canonicalizer = _component(
        "synthetic.canonicalizer:v1",
        "synthetic.canonicalizer_impl:v1",
        candidate_canonicalizer,
    )
    ledger = _component("synthetic.ledger:v1", "synthetic.ledger_impl:v1", fake_ledger_factory)
    evaluator = _component(
        PAYLOAD_PROFILE.profile_id,
        PAYLOAD_PROFILE.evaluator_id,
        evaluate_schema,
    )
    alpha = _component("alpha", "synthetic.runner.alpha:v1", alpha_runner)
    audit = _component("audit", "synthetic.runner.audit:v1", audit_runner)
    beta = _component("beta", "synthetic.runner.beta:v1", beta_runner)
    alpha_export = _component(
        "synthetic.alpha:v1",
        "synthetic.export.alpha:v1",
        alpha_export_validator,
    )
    beta_export = _component(
        "synthetic.beta:v1",
        "synthetic.export.beta:v1",
        beta_export_validator,
    )
    projection_component = _component(
        "synthetic.report_projection:v1",
        "synthetic.report_projection_impl:v1",
        report_projection,
    )
    output_schema = _output_schema()

    phases = (
        PhaseSpec(
            phase_name="alpha",
            ordering_after=(),
            input_bindings=(
                InputBinding(
                    input_name="recipe",
                    source_kind="invocation_input",
                    source_input="recipe",
                    source_constant=None,
                    source_phase=None,
                    source_output=None,
                    expected_type="kernel.json_object:v1",
                    cardinality="exactly_one",
                ),
            ),
            provided_outputs=(
                ProvidedOutput(
                    output_name="alpha_value",
                    output_type="synthetic.alpha:v1",
                    cardinality="exactly_one",
                    permitted_on_statuses=("passed", "blocked"),
                    required_on_statuses=("passed",),
                ),
            ),
            runner_id="alpha",
            permitted_diagnostic_codes=("synthetic_error",),
            permitted_blocker_codes=("synthetic_blocker",),
        ),
        PhaseSpec(
            phase_name="audit",
            ordering_after=("alpha",),
            input_bindings=(
                InputBinding(
                    input_name="policy",
                    source_kind="program_constant",
                    source_input=None,
                    source_constant="policy",
                    source_phase=None,
                    source_output=None,
                    expected_type="kernel.string:v1",
                    cardinality="exactly_one",
                ),
            ),
            provided_outputs=(),
            runner_id="audit",
            permitted_diagnostic_codes=(),
            permitted_blocker_codes=(),
        ),
        PhaseSpec(
            phase_name="beta",
            ordering_after=(),
            input_bindings=(
                InputBinding(
                    input_name="alpha_value",
                    source_kind="phase_output",
                    source_input=None,
                    source_constant=None,
                    source_phase="alpha",
                    source_output="alpha_value",
                    expected_type="synthetic.alpha:v1",
                    cardinality="exactly_one",
                ),
            ),
            provided_outputs=(
                ProvidedOutput(
                    output_name="beta_value",
                    output_type="synthetic.beta:v1",
                    cardinality="zero_or_one",
                    permitted_on_statuses=("passed",),
                    required_on_statuses=(),
                ),
            ),
            runner_id="beta",
            permitted_diagnostic_codes=(),
            permitted_blocker_codes=(),
        ),
    )

    parser_profile = ParserProfileSpec(
        profile_id="synthetic.parser_profile:v1",
        tokenizer=tokenizer,
        parser=parser,
        canonicalizer=canonicalizer,
        ledger=ledger,
        tokenizer_version="synthetic-tokenizer-v1",
        parser_version="synthetic-parser-v1",
        owned_value_abi="rook.owned_json:v1",
        canonicalization_version="rook.canonical_json:v1",
    )
    projection = ReportProjectionSpec(
        projection_id=projection_component.component_id,
        implementation_id=projection_component.implementation_id,
        implementation_fingerprint=projection_component.implementation_fingerprint,
        source_module=projection_component.source_module,
        output_schema_id=output_schema.schema_id,
        output_schema_fingerprint=output_schema.schema_fingerprint,
        report_fingerprint_path="/report_fingerprint",
        fingerprint_excluded_paths=("/report_fingerprint",),
        input_envelope_fields=(
            "program_identity",
            "invocation_evidence",
            "phase_specs",
            "phase_results",
        ),
        required_for_compile_phases=("alpha", "beta"),
        kernel_owned_paths=("/budget_receipt", "/report_fingerprint"),
        budget_receipt_path="/budget_receipt",
        writable_body_paths=("/body", "/phases", "/validation_context"),
        mandatory_shells=(("/validation_context", "object"),),
        outer_envelope_field_count=21,
    )

    runtime_pairs = (
        ("tokenizer", tokenizer, fake_tokenizer),
        ("parser", parser, fake_parser),
        ("canonicalizer", canonicalizer, candidate_canonicalizer),
        ("ledger", ledger, fake_ledger_factory),
        ("schema_evaluator", evaluator, evaluate_schema),
        ("runner", alpha, alpha_runner),
        ("runner", audit, audit_runner),
        ("runner", beta, beta_runner),
        ("export_type", alpha_export, alpha_export_validator),
        ("export_type", beta_export, beta_export_validator),
        ("report_projection", projection_component, report_projection),
    )
    runtime_bindings = tuple(
        _binding(kind, component, target)
        for kind, component, target in runtime_pairs
    ) + (
        RuntimeBinding(
            binding_kind="schema",
            binding_id=output_schema.schema_id,
            implementation_fingerprint=output_schema.schema_fingerprint,
            target=output_schema,
        ),
    )
    RUNTIME_REGISTRY.clear()
    RUNTIME_REGISTRY.update(
        {(binding.binding_kind, binding.binding_id): binding.target for binding in runtime_bindings}
    )

    modules = sorted(
        {
            component.source_module
            for component in (
                tokenizer,
                parser,
                canonicalizer,
                ledger,
                evaluator,
                alpha,
                audit,
                beta,
                alpha_export,
                beta_export,
                projection_component,
            )
        }
    )
    implementation_sources = tuple(
        implementation_source_for_module(module_name) for module_name in modules
    )

    dependencies = tuple(
        runtime_dependency_spec(name)
        for name, _ in PAYLOAD_PROFILE.runtime_dependencies
    )
    return ValidationProgramContribution(
        program_id="synthetic.validation_program:v1",
        budget_manifest=LM9A_BUDGET_MANIFEST,
        parser_profile=parser_profile,
        schema_evaluator_profiles=(
            SchemaEvaluatorSpec(profile=PAYLOAD_PROFILE, evaluator=evaluator),
        ),
        schemas=(output_schema,),
        invocation_inputs=(
            InvocationInputSpec(
                input_name="recipe",
                value_type="kernel.json_object:v1",
                cardinality="exactly_one",
            ),
        ),
        program_constants=(
            ProgramConstantSpec(
                constant_name="policy",
                value_type="kernel.string:v1",
                cardinality="exactly_one",
                value=JsonString("synthetic-policy-v1"),
            ),
        ),
        phases=phases,
        runners=(alpha, audit, beta),
        issue_vocabulary=(
            IssueSpec(code="synthetic_error", classification="diagnostic"),
            IssueSpec(code="synthetic_blocker", classification="compile_blocker"),
        ),
        export_types=(
            ExportTypeSpec(
                export_type="synthetic.alpha:v1",
                validator=alpha_export,
            ),
            ExportTypeSpec(
                export_type="synthetic.beta:v1",
                validator=beta_export,
            ),
        ),
        report_projection=projection,
        implementation_sources=implementation_sources,
        runtime_dependencies=dependencies,
        runtime_bindings=runtime_bindings,
    )


def replace_runtime_component(
    contribution: ValidationProgramContribution,
    *,
    kind: str,
    component_id: str,
    target: object,
    implementation_id: str | None = None,
) -> ValidationProgramContribution:
    component = _component(
        component_id,
        implementation_id or f"{component_id}.implementation:v2",
        target,
    )
    bindings = tuple(
        binding
        if (binding.binding_kind, binding.binding_id) != (kind, component_id)
        else _binding(kind, component, target)
        for binding in contribution.runtime_bindings
    )
    sources = {source.module_name: source for source in contribution.implementation_sources}
    sources[component.source_module] = implementation_source_for_module(component.source_module)
    if kind == "runner":
        runners = tuple(
            component if runner.component_id == component_id else runner
            for runner in contribution.runners
        )
        return replace(
            contribution,
            runners=runners,
            implementation_sources=tuple(sources.values()),
            runtime_bindings=bindings,
        )
    raise AssertionError(f"unsupported synthetic replacement kind: {kind}")


__all__ = (
    "MutableCallable",
    "MutableService",
    "RUNTIME_REGISTRY",
    "alternate_beta_runner",
    "beta_runner",
    "canonical_json_bytes",
    "extra_export_validator",
    "immutable_record_dispatch",
    "make_closure",
    "make_program_contribution",
    "replace_runtime_component",
)
