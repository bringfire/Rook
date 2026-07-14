"""Closed declarations consumed by validation-program composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from .budget import BudgetManifest
from .owned_json import JsonObject, JsonValue
from .schema_profile import AdmittedSchema, SchemaProfile


Cardinality = Literal["exactly_one", "zero_or_one", "many"]
SourceKind = Literal["invocation_input", "program_constant", "phase_output"]
PhaseOutputStatus = Literal["passed", "blocked", "failed"]
IssueClassification = Literal["diagnostic", "compile_blocker"]
RuntimeBindingKind = Literal[
    "tokenizer",
    "parser",
    "canonicalizer",
    "ledger",
    "schema",
    "schema_evaluator",
    "runner",
    "export_type",
    "report_projection",
]


class ProgramCompositionError(ValueError):
    """A candidate contribution cannot be sealed as one exact program."""


@dataclass(frozen=True, slots=True)
class InputBinding:
    input_name: str
    source_kind: SourceKind
    source_input: str | None
    source_constant: str | None
    source_phase: str | None
    source_output: str | None
    expected_type: str
    cardinality: Cardinality


@dataclass(frozen=True, slots=True)
class ProvidedOutput:
    output_name: str
    output_type: str
    cardinality: Cardinality
    permitted_on_statuses: tuple[PhaseOutputStatus, ...]
    required_on_statuses: tuple[PhaseOutputStatus, ...]


@dataclass(frozen=True, slots=True)
class PhaseSpec:
    phase_name: str
    ordering_after: tuple[str, ...]
    input_bindings: tuple[InputBinding, ...]
    provided_outputs: tuple[ProvidedOutput, ...]
    runner_id: str
    permitted_diagnostic_codes: tuple[str, ...]
    permitted_blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvocationInputSpec:
    input_name: str
    value_type: str
    cardinality: Cardinality


@dataclass(frozen=True, slots=True)
class ProgramConstantSpec:
    constant_name: str
    value_type: str
    cardinality: Cardinality
    value: JsonValue


@dataclass(frozen=True, slots=True)
class IssueSpec:
    code: str
    classification: IssueClassification


@dataclass(frozen=True, slots=True)
class RuntimeComponentSpec:
    component_id: str
    implementation_id: str
    implementation_fingerprint: str
    source_module: str


@dataclass(frozen=True, slots=True)
class ParserProfileSpec:
    profile_id: str
    tokenizer: RuntimeComponentSpec
    parser: RuntimeComponentSpec
    canonicalizer: RuntimeComponentSpec
    ledger: RuntimeComponentSpec
    tokenizer_version: str
    parser_version: str
    owned_value_abi: str
    canonicalization_version: str


@dataclass(frozen=True, slots=True)
class SchemaEvaluatorSpec:
    profile: SchemaProfile
    evaluator: RuntimeComponentSpec


@dataclass(frozen=True, slots=True)
class ExportTypeSpec:
    export_type: str
    validator: RuntimeComponentSpec


@dataclass(frozen=True, slots=True)
class ReportProjectionSpec:
    projection_id: str
    implementation_id: str
    implementation_fingerprint: str
    source_module: str
    output_schema_id: str
    output_schema_fingerprint: str
    report_fingerprint_path: str
    fingerprint_excluded_paths: tuple[str, ...]
    input_envelope_fields: tuple[str, ...]
    required_for_compile_phases: tuple[str, ...]
    kernel_owned_paths: tuple[str, ...]
    budget_receipt_path: str
    writable_body_paths: tuple[str, ...]
    mandatory_shells: tuple[tuple[str, Literal["object", "array"]], ...]
    outer_envelope_field_count: int


@dataclass(frozen=True, slots=True)
class ImplementationSource:
    module_name: str
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class RuntimeDependencySpec:
    distribution_name: str
    expected_version: str
    behavior_files: tuple[str, ...]
    distribution_fingerprint: str


@dataclass(frozen=True, slots=True)
class RuntimeBinding:
    binding_kind: RuntimeBindingKind
    binding_id: str
    implementation_fingerprint: str
    target: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ImmutableCallableRecord:
    """The one allowed callable-instance shape; all state is owned JSON."""

    function: Callable[..., object] = field(repr=False, compare=False)
    state: JsonObject

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.function(self.state, *args, **kwargs)


@dataclass(frozen=True, slots=True)
class ValidationProgramContribution:
    program_id: str
    budget_manifest: BudgetManifest
    parser_profile: ParserProfileSpec
    schema_evaluator_profiles: tuple[SchemaEvaluatorSpec, ...]
    schemas: tuple[AdmittedSchema, ...]
    invocation_inputs: tuple[InvocationInputSpec, ...]
    program_constants: tuple[ProgramConstantSpec, ...]
    phases: tuple[PhaseSpec, ...]
    runners: tuple[RuntimeComponentSpec, ...]
    issue_vocabulary: tuple[IssueSpec, ...]
    export_types: tuple[ExportTypeSpec, ...]
    report_projection: ReportProjectionSpec
    implementation_sources: tuple[ImplementationSource, ...]
    runtime_dependencies: tuple[RuntimeDependencySpec, ...]
    runtime_bindings: tuple[RuntimeBinding, ...]


__all__ = (
    "Cardinality",
    "ExportTypeSpec",
    "ImmutableCallableRecord",
    "ImplementationSource",
    "InputBinding",
    "InvocationInputSpec",
    "IssueSpec",
    "ParserProfileSpec",
    "PhaseSpec",
    "ProgramCompositionError",
    "ProgramConstantSpec",
    "ProvidedOutput",
    "ReportProjectionSpec",
    "RuntimeBinding",
    "RuntimeComponentSpec",
    "RuntimeDependencySpec",
    "SchemaEvaluatorSpec",
    "ValidationProgramContribution",
)
