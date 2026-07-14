"""Synthetic sealed-program declarations shared by validation-kernel tests."""

from __future__ import annotations

import json
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
    implementation_source_closure_for_modules,
    implementation_source_for_module,
    runtime_dependency_closure_for_modules,
    runtime_implementation_fingerprint,
)
from rook.validation_kernel.budget import LM9A_BUDGET_MANIFEST
from rook.validation_kernel.canonical_json import canonical_fingerprint, canonical_json_bytes
from rook.validation_kernel.owned_json import JsonObject, JsonString, own_trusted_json
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


class StaticService:
    @staticmethod
    def run(*_: object) -> None:
        return None


class UnboundService:
    def run(self, *_: object) -> None:
        return None


class DisguisedStaticService:
    @staticmethod
    def run(*_: object) -> None:
        return None


disguised_class_function = DisguisedStaticService.run
disguised_class_function.__qualname__ = disguised_class_function.__name__


RUNTIME_REGISTRY: dict[tuple[str, str], object] = {}

INVOCATION_MANDATORY_SHELLS = (
    ("/task_envelope", "object"),
    ("/authority_artifacts", "array"),
    ("/validation_context", "object"),
    ("/validation_context/environment_snapshots", "array"),
    ("/validation_context/policy_registries", "array"),
    ("/validation_context/payload_schema_registry", "object"),
    ("/validation_context/capability_registry", "object"),
    ("/validation_context/vocabularies", "object"),
    ("/validation_context/vocabularies/semantic_authority_codes", "object"),
    ("/validation_context/vocabularies/semantic_capability_codes", "object"),
    ("/validation_context/vocabularies/worker_slot_codes", "object"),
    ("/validation_context/vocabularies/semantic_materiality_codes", "object"),
    ("/validation_context/vocabularies/semantic_value_schemas", "object"),
)


def make_assembler_profile_candidate(
    *,
    program_id: str = "synthetic.validation_program:v1",
    assembler_kind: str = "deterministic_fixture",
    permitted_clock_sources: tuple[str, ...] | None = None,
) -> JsonObject:
    if permitted_clock_sources is None:
        permitted_clock_sources = (
            ("deterministic_fixture",)
            if assembler_kind == "deterministic_fixture"
            else ("trusted_system_clock",)
        )
    candidate: dict[str, object] = {
        "schema": "rook.trusted_bundle_assembler_profile:v1",
        "profile_id": f"synthetic.{assembler_kind}:v1",
        "assembler_kind": assembler_kind,
        "assembler_id": f"synthetic.{assembler_kind}:v1",
        "assembler_version": "v1",
        "implementation_fingerprint": "sha256:" + "1" * 64,
        "permitted_program_ids": [program_id],
        "permitted_clock_sources": list(permitted_clock_sources),
    }
    unsigned = own_trusted_json(candidate)
    candidate["profile_fingerprint"] = canonical_fingerprint(unsigned)
    owned = own_trusted_json(candidate)
    if type(owned) is not JsonObject:
        raise AssertionError("synthetic assembler profile must be an object")
    return owned


def make_validation_bundle_bytes(
    *,
    trusted_clock_source: str = "deterministic_fixture",
    task_session_id: object = "synthetic.task_session:v1",
    environment_session_id: object = None,
    capability_registry_session_id: object = "synthetic.capability_session:v1",
    validation_context_updates: dict[str, object] | None = None,
    bundle_updates: dict[str, object] | None = None,
) -> bytes:
    validation_context: dict[str, object] = {
        "evaluated_at": "2026-07-12T12:00:00Z",
        "trusted_clock_source": trusted_clock_source,
        "task_session_id": task_session_id,
        "environment_session_id": environment_session_id,
        "capability_registry_session_id": capability_registry_session_id,
        "environment_snapshots": [],
        "policy_registries": [],
        "payload_schema_registry": {},
        "capability_registry": {},
        "vocabularies": {
            "semantic_authority_codes": {},
            "semantic_capability_codes": {},
            "worker_slot_codes": {},
            "semantic_materiality_codes": {},
            "semantic_value_schemas": {},
        },
    }
    if validation_context_updates is not None:
        validation_context.update(validation_context_updates)
    bundle: dict[str, object] = {
        "schema": "rook.planner_graph_recipe_validation_bundle:v1",
        "task_envelope": {},
        "authority_artifacts": [],
        "validation_context": validation_context,
    }
    if bundle_updates is not None:
        bundle.update(bundle_updates)
    return json.dumps(bundle, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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


def _output_schema(*, invocation_shells: bool) -> object:
    validation_context_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
    }
    root_properties: dict[str, object] = {
        "body": {
            "type": "object",
            "properties": {
                "closed": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "optional": {"type": "string"},
                "\ue000": {"type": "string"},
                "\U00010000": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "validation_context": validation_context_schema,
        "phases": {"type": "array", "items": {"type": "string"}},
        "validation_budget": {
            "type": "object",
            "additionalProperties": False,
        },
        "report_fingerprint": {"type": "string"},
    }
    required = [
        "body",
        "validation_context",
        "phases",
        "validation_budget",
        "report_fingerprint",
    ]
    if invocation_shells:
        validation_context_schema["properties"] = {
            "evaluated_at": {"type": "string"},
            "trusted_clock_source": {"type": "string"},
            "task_session_id": {"type": "string"},
            "environment_session_id": {"type": ["string", "null"]},
            "capability_registry_session_id": {"type": "string"},
            "environment_snapshots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            "policy_registries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            "payload_schema_registry": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "capability_registry": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "vocabularies": {
                "type": "object",
                "properties": {
                    "semantic_authority_codes": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "semantic_capability_codes": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "worker_slot_codes": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "semantic_materiality_codes": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "semantic_value_schemas": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
        }
        root_properties["task_envelope"] = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        root_properties["authority_artifacts"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
        required.extend(("task_envelope", "authority_artifacts"))

    value = own_trusted_json(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": root_properties,
            "required": required,
            "additionalProperties": False,
        }
    )
    return admit_schema("synthetic.report:v1", value, PAYLOAD_PROFILE)


def make_program_contribution(
    *, invocation_shells: bool = False
) -> ValidationProgramContribution:
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
    output_schema = _output_schema(invocation_shells=invocation_shells)

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
    writable_body_paths = ("/body", "/phases", "/validation_context")
    mandatory_shells = (("/validation_context", "object"),)
    if invocation_shells:
        writable_body_paths += ("/task_envelope", "/authority_artifacts")
        mandatory_shells = INVOCATION_MANDATORY_SHELLS
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
        kernel_owned_paths=("/report_fingerprint", "/validation_budget"),
        budget_receipt_path="/validation_budget",
        writable_body_paths=writable_body_paths,
        mandatory_shells=mandatory_shells,
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
    implementation_sources = implementation_source_closure_for_modules(
        tuple(modules)
    )

    dependencies = runtime_dependency_closure_for_modules(
        tuple(modules),
        tuple(name for name, _ in PAYLOAD_PROFILE.runtime_dependencies),
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
    "INVOCATION_MANDATORY_SHELLS",
    "MutableCallable",
    "MutableService",
    "RUNTIME_REGISTRY",
    "StaticService",
    "UnboundService",
    "alternate_beta_runner",
    "beta_runner",
    "canonical_json_bytes",
    "disguised_class_function",
    "extra_export_validator",
    "immutable_record_dispatch",
    "make_closure",
    "make_assembler_profile_candidate",
    "make_program_contribution",
    "make_validation_bundle_bytes",
    "replace_runtime_component",
)
