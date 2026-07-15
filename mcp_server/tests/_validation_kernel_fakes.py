"""Synthetic sealed-program declarations shared by validation-kernel tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, make_dataclass, replace
from types import MappingProxyType
from typing import Any

from rook.validation_kernel.phase_contract import (
    ExportTypeSpec,
    ImmutableCallableRecord,
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
)
from rook.validation_kernel.phase_engine import KernelIssue, NamedOutput, RunnerResult
from rook.validation_kernel.program import (
    _fixed_parser_profile_spec,
    implementation_source_closure_for_modules,
    implementation_source_for_module,
    runtime_dependency_closure_for_modules,
    runtime_implementation_fingerprint,
)
from rook.validation_kernel.budget import (
    LM9A_BUDGET_MANIFEST,
    create_budget_ledger,
)
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    canonical_fingerprint_metered,
    canonical_json_bytes,
    sha256_prefixed,
)
from rook.validation_kernel.owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonObject,
    JsonString,
    own_trusted_json,
)
from rook.validation_kernel.schema_profile import (
    CORE_PROFILE,
    InstanceBinding,
    PAYLOAD_PROFILE,
    admit_schema,
    evaluate_schema,
)
from rook.validation_kernel.parser import parse_owned_json


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


@dataclass(frozen=True, slots=True)
class SyntheticPhaseIndex:
    identity: str
    source: JsonObject
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticMutablePhaseIndex:
    identity: str
    mutable_payload: dict[str, object]


SyntheticWidePhaseIndex = make_dataclass(
    "SyntheticWidePhaseIndex",
    ((f"field_{index}", int) for index in range(2_000)),
    frozen=True,
    slots=True,
)
SYNTHETIC_WIDE_PHASE_INDEX = SyntheticWidePhaseIndex(*range(2_000))


@dataclass(frozen=True, slots=True)
class AuthoredRunnerResult:
    diagnostics: tuple[KernelIssue, ...]
    compile_blockers: tuple[KernelIssue, ...]
    outputs: tuple[NamedOutput, ...]
    status: str
    kernel_work_units_delta: int


class SyntheticString(str):
    pass


class HostileArgsError(Exception):
    @property
    def args(self) -> tuple[object, ...]:
        raise RuntimeError("hostile args property executed")


class _HostileTypeMetadata(type):
    def __getattribute__(cls, name: str) -> object:
        if name in ("__module__", "__qualname__"):
            raise RuntimeError("hostile type metadata executed")
        return super().__getattribute__(name)


class HostileTypeMetadataError(Exception, metaclass=_HostileTypeMetadata):
    pass


class HugeTypeMetadataError(Exception):
    pass


HugeTypeMetadataError.__module__ = "m" * 100_000
HugeTypeMetadataError.__qualname__ = "q" * 100_000


class HostileExceptionArgument:
    def __str__(self) -> str:
        raise RuntimeError("hostile exception argument stringified")

    def __repr__(self) -> str:
        raise RuntimeError("hostile exception argument represented")


def phase_index_export_validator(value: object) -> bool:
    return type(value) in (
        SyntheticPhaseIndex,
        SyntheticMutablePhaseIndex,
        SyntheticWidePhaseIndex,
    )


def phase_text_export_validator(value: object) -> bool:
    return type(value) is JsonString


KERNEL_STRING_EXPORT_CALLS: list[object] = []


def rejecting_kernel_string_export_validator(value: object) -> bool:
    KERNEL_STRING_EXPORT_CALLS.append(value)
    return False


def raising_kernel_string_export_validator(value: object) -> bool:
    raise RuntimeError("sealed export validator failed")


def non_boolean_kernel_string_export_validator(value: object) -> object:
    return JsonString("not-a-boolean")


def _runner_state_text(state: JsonObject, name: str) -> str:
    value = state[name]
    if type(value) is not JsonString:
        raise TypeError("synthetic runner state must contain strings")
    return value.value


def _diagnostic(severity: str, *, code: str = "synthetic_error") -> KernelIssue:
    return KernelIssue(
        classification="diagnostic",
        code=code,
        severity=severity,
        subject_id="synthetic.subject",
        path="/recipe",
        related_paths=("/validation_context",),
        bounded_message=f"Synthetic {severity} diagnostic.",
        detail_sha256=None,
    )


def _blocker() -> KernelIssue:
    return KernelIssue(
        classification="compile_blocker",
        code="synthetic_blocker",
        severity=None,
        subject_id="synthetic.subject",
        path="/recipe",
        related_paths=(),
        bounded_message="Synthetic compile blocker.",
        detail_sha256=None,
    )


def _api_diagnostic(code: str, path: str) -> KernelIssue:
    return KernelIssue(
        classification="diagnostic",
        code=code,
        severity="error",
        subject_id="synthetic.subject",
        path=path,
        related_paths=(),
        bounded_message="Synthetic validation evidence.",
        detail_sha256=None,
    )


def validation_api_runner_dispatch(
    state: JsonObject, inputs: object, helpers: object
) -> object:
    phase_name = _runner_state_text(state, "phase_name")
    scenario = _runner_state_text(state, "scenario")

    if scenario == "integrity_failure":
        return object()
    if phase_name == "companion_artifacts":
        if tuple(inputs) != ("validation_bundle",):  # type: ignore[arg-type]
            raise AssertionError("companion phase received undeclared inputs")
        bundle = inputs["validation_bundle"][0]  # type: ignore[index]
        if type(bundle) is not JsonObject:
            raise AssertionError("companion phase received a non-object bundle")
        context = bundle["validation_context"]
        if type(context) is not JsonObject:
            raise AssertionError("companion phase received no validation context")
        snapshots = context["environment_snapshots"]
        if type(snapshots) is not JsonArray:
            raise AssertionError("companion phase received malformed snapshots")
        diagnostics = (
            (
                _api_diagnostic(
                    "synthetic_companion_invalid",
                    "/validation_context/environment_snapshots",
                ),
            )
            if snapshots
            else ()
        )
        return RunnerResult(
            diagnostics=diagnostics,
            compile_blockers=(),
            outputs=(),
        )

    if phase_name != "schema":
        raise AssertionError(f"unknown synthetic API phase: {phase_name}")
    if tuple(inputs) != ("recipe", "recipe_parse_evidence"):  # type: ignore[arg-type]
        raise AssertionError("schema phase received undeclared inputs")
    recipe = inputs["recipe"][0]  # type: ignore[index]
    parse_evidence = inputs["recipe_parse_evidence"][0]  # type: ignore[index]
    malformed = type(recipe) is JsonNull and type(parse_evidence) is JsonObject
    if not malformed and (
        type(recipe) is not JsonObject or type(parse_evidence) is not JsonNull
    ):
        raise AssertionError("schema phase received inconsistent recipe evidence")
    return RunnerResult(
        diagnostics=(
            (_api_diagnostic("synthetic_recipe_invalid", "/recipe"),)
            if malformed
            else ()
        ),
        compile_blockers=(),
        outputs=(),
    )


def phase_engine_runner_dispatch(
    state: JsonObject, inputs: object, helpers: object
) -> object:
    phase_name = _runner_state_text(state, "phase_name")
    scenario = _runner_state_text(state, "scenario")

    if phase_name == "audit":
        if tuple(inputs) != ("policy",):  # type: ignore[arg-type]
            raise AssertionError("audit received undeclared inputs")
        if scenario == "immutability_probe":
            policy_values = inputs["policy"]  # type: ignore[index]
            try:
                policy_values[0] = JsonString("changed")
            except TypeError:
                pass
            else:
                raise AssertionError("bound input values are mutable")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=())

    if phase_name == "beta":
        if tuple(inputs) != ("alpha_value",):  # type: ignore[arg-type]
            raise AssertionError("beta received undeclared inputs")
        alpha_values = inputs["alpha_value"]  # type: ignore[index]
        alpha_index = alpha_values[0]
        if type(alpha_index) is SyntheticWidePhaseIndex:
            alpha_identity = "wide-index"
        elif type(alpha_index) is SyntheticPhaseIndex:
            alpha_identity = alpha_index.identity
        else:
            raise AssertionError("beta received the wrong exact named output")
        if scenario == "immutability_probe":
            try:
                alpha_index.identity = "changed"  # type: ignore[misc]
            except (AttributeError, TypeError):
                pass
            else:
                raise AssertionError("semantic index is mutable")
            try:
                alpha_index.source["nested"] = JsonString("changed")  # type: ignore[index]
            except TypeError:
                pass
            else:
                raise AssertionError("owned nested mapping is mutable")
            try:
                alpha_values += (alpha_index,)
            except (AttributeError, TypeError):
                pass
        if scenario == "many_10000":
            return RunnerResult(
                diagnostics=(),
                compile_blockers=(),
                outputs=(
                    NamedOutput(
                        "beta_value",
                        tuple(JsonString(str(index)) for index in range(10_000)),
                    ),
                ),
            )
        return RunnerResult(
            diagnostics=(),
            compile_blockers=(),
            outputs=(NamedOutput("beta_value", (JsonString(alpha_identity),)),),
        )

    if tuple(inputs) != ("recipe",):  # type: ignore[arg-type]
        raise AssertionError("alpha received undeclared inputs")
    recipe_values = inputs["recipe"]  # type: ignore[index]
    recipe = recipe_values[0]
    if type(recipe) is not JsonObject:
        raise AssertionError("alpha received a non-object recipe")
    output = NamedOutput(
        "alpha_value",
        (SyntheticPhaseIndex("alpha-index", recipe, ("/recipe",)),),
    )

    if scenario == "boundary_matrix":
        case_value = recipe["case_id"]
        if type(case_value) is not JsonString:
            raise AssertionError("boundary case ID must be a string")
        case_id = case_value.value
        if case_id.startswith("boundary.success"):
            attempt_count = 1
            terminal = "passed"
        elif case_id.startswith("boundary.blocked"):
            attempt_count = 2
            terminal = "blocked"
        elif case_id.startswith("boundary.failed"):
            attempt_count = 3
            terminal = "failed"
        else:
            attempt_count = 1
            terminal = "passed"
        binding = InstanceBinding(
            artifact_id=f"artifact:{case_id}",
            artifact_fingerprint=canonical_fingerprint(recipe),
            instance_pointer="",
        )
        for _ in range(attempt_count):
            helpers.evaluate_schema(  # type: ignore[attr-defined]
                "synthetic.core_positive:v1",
                recipe,
                instance_binding=binding,
            )
        if terminal == "blocked":
            return RunnerResult(
                diagnostics=(),
                compile_blockers=(_blocker(),),
                outputs=(output,),
            )
        if terminal == "failed":
            return RunnerResult(
                diagnostics=(_diagnostic("error"),),
                compile_blockers=(),
                outputs=(),
            )
        return RunnerResult(
            diagnostics=(), compile_blockers=(), outputs=(output,)
        )

    if scenario == "passed":
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario == "schema_issue_stress":
        view = helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.issue_stress:v1",
            recipe,
            instance_binding=InstanceBinding(
                artifact_id="synthetic.recipe",
                artifact_fingerprint=canonical_fingerprint(recipe),
                instance_pointer="",
            ),
        )
        if hasattr(view, "reservation"):
            raise AssertionError("runner received an accounting receipt")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario == "wide_index":
        return RunnerResult(
            diagnostics=(),
            compile_blockers=(),
            outputs=(NamedOutput("alpha_value", (SYNTHETIC_WIDE_PHASE_INDEX,)),),
        )
    if scenario == "blocked":
        return RunnerResult(diagnostics=(), compile_blockers=(_blocker(),), outputs=(output,))
    if scenario == "failed":
        return RunnerResult(diagnostics=(_diagnostic("error"),), compile_blockers=(), outputs=())
    if scenario == "error_precedence":
        return RunnerResult(
            diagnostics=(_diagnostic("error"),),
            compile_blockers=(_blocker(),),
            outputs=(),
        )
    if scenario == "warning_information":
        return RunnerResult(
            diagnostics=(_diagnostic("warning"), _diagnostic("information")),
            compile_blockers=(),
            outputs=(output,),
        )
    if scenario == "duplicate_diagnostic":
        issue = _diagnostic("error")
        return RunnerResult(
            diagnostics=(issue, issue), compile_blockers=(), outputs=()
        )
    if scenario == "duplicate_blocker":
        issue = _blocker()
        return RunnerResult(
            diagnostics=(), compile_blockers=(issue, issue), outputs=(output,)
        )
    if scenario == "cross_list_issue":
        issue = _diagnostic("error")
        return RunnerResult(
            diagnostics=(issue,), compile_blockers=(issue,), outputs=()
        )
    if scenario == "unregistered_issue":
        return RunnerResult(
            diagnostics=(_diagnostic("error", code="synthetic_unregistered"),),
            compile_blockers=(),
            outputs=(),
        )
    if scenario == "wrong_classification":
        issue = KernelIssue(
            classification="compile_blocker",
            code="synthetic_error",
            severity=None,
            subject_id=None,
            path=None,
            related_paths=(),
            bounded_message="Wrong classification.",
            detail_sha256=None,
        )
        return RunnerResult(diagnostics=(issue,), compile_blockers=(), outputs=())
    if scenario == "non_exact_issue_fields":
        issue = KernelIssue(
            classification=SyntheticString("diagnostic"),  # type: ignore[arg-type]
            code=SyntheticString("synthetic_error"),
            severity=SyntheticString("error"),  # type: ignore[arg-type]
            subject_id=None,
            path=None,
            related_paths=(),
            bounded_message="Non-exact issue fields.",
            detail_sha256=None,
        )
        return RunnerResult(diagnostics=(issue,), compile_blockers=(), outputs=())
    if scenario == "duplicate_output":
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output, output))
    if scenario == "extra_output":
        return RunnerResult(
            diagnostics=(),
            compile_blockers=(),
            outputs=(output, NamedOutput("extra", (JsonString("extra"),))),
        )
    if scenario == "missing_output":
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=())
    if scenario == "blocked_missing_output":
        return RunnerResult(diagnostics=(), compile_blockers=(_blocker(),), outputs=())
    if scenario == "wrong_type":
        return RunnerResult(
            diagnostics=(),
            compile_blockers=(),
            outputs=(NamedOutput("alpha_value", (JsonString("wrong"),)),),
        )
    if scenario == "mutable_output":
        return RunnerResult(
            diagnostics=(),
            compile_blockers=(),
            outputs=(
                NamedOutput(
                    "alpha_value",
                    (SyntheticMutablePhaseIndex("mutable", {"items": []}),),
                ),
            ),
        )
    if scenario == "wrong_cardinality":
        value = SyntheticPhaseIndex("second-index", recipe, ("/second",))
        return RunnerResult(
            diagnostics=(),
            compile_blockers=(),
            outputs=(NamedOutput("alpha_value", (output.values[0], value)),),
        )
    if scenario == "output_on_failed":
        return RunnerResult(
            diagnostics=(_diagnostic("error"),), compile_blockers=(), outputs=(output,)
        )
    if scenario == "authored_fields":
        return AuthoredRunnerResult((), (), (output,), "passed", 999)
    if scenario in ("oversized_exception", "oversized_exception_alt"):
        raise RuntimeError(scenario + ":" + ("x" * 20_000))
    if scenario == "oversized_integer_exception":
        raise RuntimeError(10**20_000)
    if scenario == "hostile_args_exception":
        raise HostileArgsError("private hostile argument")
    if scenario == "hostile_type_metadata_exception":
        raise HostileTypeMetadataError("private hostile metadata")
    if scenario == "huge_type_metadata_exception":
        raise HugeTypeMetadataError("bounded metadata")
    if scenario == "nested_cyclic_custom_exception":
        cycle: list[object] = []
        cycle.append(cycle)
        nested: object = (cycle, HostileExceptionArgument())
        for _ in range(64):
            nested = (nested,)
        raise RuntimeError(nested)
    if scenario == "work_accounting":
        helpers.charge_work_units(7)  # type: ignore[attr-defined]
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario == "schema_audit":
        binding = InstanceBinding(
            artifact_id="synthetic.recipe",
            artifact_fingerprint=canonical_fingerprint(recipe),
            instance_pointer="",
        )
        first = helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.report:v1", recipe, instance_binding=binding
        )
        second = helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.report:v1", recipe, instance_binding=binding
        )
        if hasattr(first, "reservation") or hasattr(second, "reservation"):
            raise AssertionError("runner received an accounting receipt")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario.startswith("schema_binding_"):
        left = recipe["left"]
        right = recipe["right"]
        if type(left) is not JsonObject or type(right) is not JsonObject:
            raise AssertionError("binding probes require two object subtrees")
        root_fingerprint = canonical_fingerprint(recipe)
        instance = right
        pointer = "/right"
        artifact_fingerprint = root_fingerprint
        if scenario == "schema_binding_wrong_artifact":
            artifact_fingerprint = "sha256:" + ("0" * 64)
        elif scenario == "schema_binding_missing_pointer":
            pointer = "/missing"
        elif scenario == "schema_binding_wrong_subtree":
            pointer = "/left"
        elif scenario == "schema_binding_detached_instance":
            instance = JsonObject(tuple(right.members))
        else:
            raise AssertionError("unknown schema binding probe")
        helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.report:v1",
            instance,
            instance_binding=InstanceBinding(
                artifact_id="artifact:fixture-recipe",
                artifact_fingerprint=artifact_fingerprint,
                instance_pointer=pointer,
            ),
        )
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario == "schema_audit_order":
        nested = recipe["nested"]
        if type(nested) is not JsonObject:
            raise AssertionError("schema audit order requires a nested object")
        first = helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.report:v1",
            nested,
            instance_binding=InstanceBinding(
                artifact_id="synthetic.recipe",
                artifact_fingerprint=canonical_fingerprint(recipe),
                instance_pointer="/nested",
            ),
        )
        second = helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.report:v1",
            recipe,
            instance_binding=InstanceBinding(
                artifact_id="synthetic.recipe",
                artifact_fingerprint=canonical_fingerprint(recipe),
                instance_pointer="",
            ),
        )
        if hasattr(first, "reservation") or hasattr(second, "reservation"):
            raise AssertionError("runner received an accounting receipt")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario == "schema_audit_equal_shape":
        left = recipe["left"]
        right = recipe["right"]
        if type(left) is not JsonObject or type(right) is not JsonObject:
            raise AssertionError("equal-shape audit requires two object subtrees")
        root_fingerprint = canonical_fingerprint(recipe)
        views = (
            helpers.evaluate_schema(  # type: ignore[attr-defined]
                "synthetic.report:v1",
                left,
                instance_binding=InstanceBinding(
                    artifact_id="artifact:fixture-recipe",
                    artifact_fingerprint=root_fingerprint,
                    instance_pointer="/left",
                ),
            ),
            helpers.evaluate_schema(  # type: ignore[attr-defined]
                "synthetic.report:v1",
                right,
                instance_binding=InstanceBinding(
                    artifact_id="artifact:fixture-recipe",
                    artifact_fingerprint=root_fingerprint,
                    instance_pointer="/right",
                ),
            ),
        )
        if any(hasattr(view, "reservation") for view in views):
            raise AssertionError("runner received an accounting receipt")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario == "schema_fill_report_rejection":
        binding = InstanceBinding(
            artifact_id="artifact:fixture-recipe",
            artifact_fingerprint=canonical_fingerprint(recipe),
            instance_pointer="",
        )
        for _ in range(8):
            view = helpers.evaluate_schema(  # type: ignore[attr-defined]
                "synthetic.report:v1", recipe, instance_binding=binding
            )
            if hasattr(view, "reservation"):
                raise AssertionError("runner received an accounting receipt")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    if scenario in (
        "schema_then_budget_failure",
        "schema_then_integrity_failure",
        "schema_then_internal_failure",
    ):
        view = helpers.evaluate_schema(  # type: ignore[attr-defined]
            "synthetic.report:v1",
            recipe,
            instance_binding=InstanceBinding(
                artifact_id="synthetic.recipe",
                artifact_fingerprint=canonical_fingerprint(recipe),
                instance_pointer="",
            ),
        )
        if hasattr(view, "reservation"):
            raise AssertionError("runner received an accounting receipt")
        if scenario == "schema_then_integrity_failure":
            return object()
        if scenario == "schema_then_internal_failure":
            raise RuntimeError("synthetic failure after schema evaluation")
        helpers.charge_work_units(1_000_000)  # type: ignore[attr-defined]
        raise AssertionError("synthetic budget failure did not terminate")
    if scenario == "immutability_probe":
        if hasattr(helpers, "ledger") or hasattr(helpers, "context"):
            raise AssertionError("runner received private engine authority")
        try:
            inputs["recipe"] = ()  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("bound input mapping is mutable")
        try:
            recipe["nested"] = JsonString("changed")  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("invocation input is mutable")
        return RunnerResult(diagnostics=(), compile_blockers=(), outputs=(output,))
    raise AssertionError(f"unknown synthetic phase-engine scenario: {scenario}")


def _projection_state_strings(state: JsonObject, field_name: str) -> tuple[str, ...]:
    value = state[field_name]
    if type(value) is not JsonArray or any(type(item) is not JsonString for item in value):
        raise AssertionError("synthetic projection state is malformed")
    return tuple(item.value for item in value)


def report_projection(
    state: JsonObject, envelope: object, builder: object
) -> object:
    from rook.validation_kernel.reporting import (
        ReportBuilder,
        ReportProjectionEnvelope,
    )

    if type(state) is not JsonObject:
        raise AssertionError("projection state must be exact owned JSON")
    if type(envelope) is not ReportProjectionEnvelope:
        raise AssertionError("projection received an inexact envelope")
    if type(builder) is not ReportBuilder:
        raise AssertionError("projection received an inexact builder")
    for forbidden in (
        "ledger",
        "program",
        "runners",
        "runtime_bindings",
        "clock",
        "files",
        "providers",
        "raw_recipe_bytes",
        "raw_validation_bundle_bytes",
        "context",
    ):
        if hasattr(envelope, forbidden) or hasattr(builder, forbidden):
            raise AssertionError(f"projection received forbidden authority: {forbidden}")
    try:
        envelope.program_id = "changed"  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("projection envelope is mutable")

    scenario_value = state["scenario"]
    shells_value = state["invocation_shells"]
    schema_probe_value = state["schema_probe"]
    artifact_identity_value = state["artifact_identity"]
    if (
        type(scenario_value) is not JsonString
        or type(shells_value) is not JsonBoolean
        or type(schema_probe_value) is not JsonString
        or type(artifact_identity_value) is not JsonBoolean
    ):
        raise AssertionError("synthetic projection scenario is malformed")
    scenario = scenario_value.value
    schema_probe = schema_probe_value.value
    if scenario == "return_host_graph":
        return {"forged": True}
    if scenario == "return_owned_graph":
        return own_trusted_json({"forged": True})
    if scenario == "raise":
        raise RuntimeError("synthetic projection failure")
    if scenario == "unknown_path":
        builder.put("/body/unknown", JsonString("forged"))
        return None
    if scenario == "kernel_path":
        builder.put("/validation_budget", own_trusted_json({}))
        return None
    if scenario == "wrong_shape":
        builder.put("/phases", JsonString("not-an-array"))
        return None
    if scenario == "projection_overflow":
        builder.put(
            "/phases",
            JsonArray(tuple(JsonString("overflow") for _ in range(131_073))),
        )
        return None

    evidence = envelope.invocation_evidence
    if type(evidence) is not JsonObject:
        raise AssertionError("invocation evidence must be an exact owned object")
    validation_bundle = evidence["validation_bundle"]
    if type(validation_bundle) is not JsonObject:
        raise AssertionError("validation bundle evidence must be an exact owned object")

    body_optional = (
        "x" * 2_097_152
        if scenario == "canonical_overflow"
        else envelope.program_id
    )
    body: dict[str, object] = {"closed": {}, "optional": body_optional}
    if schema_probe:
        body["probe"] = _report_schema_probe_instance(schema_probe)
    builder.put("/body", own_trusted_json(body))
    if artifact_identity_value.value:
        builder.put(
            "/artifact_identity",
            JsonObject(
                tuple(
                    (JsonString(field_name), evidence[field_name])
                    for field_name in (
                        "recipe_input_payload_sha256",
                        "validation_bundle_input_payload_sha256",
                        "recipe_value_fingerprint",
                        "validation_bundle_fingerprint",
                    )
                )
            ),
        )
    builder.put("/phases", JsonArray(()))
    for result in envelope.phase_results:
        builder.append("/phases", JsonString(f"{result.phase_name}:{result.status}"))

    required = frozenset(_projection_state_strings(state, "required_for_compile_phases"))
    status_by_phase = {result.phase_name: result.status for result in envelope.phase_results}
    valid = not any(
        issue.severity == "error"
        for result in envelope.phase_results
        for issue in result.diagnostics
    )
    has_blockers = any(result.compile_blockers for result in envelope.phase_results)
    compile_ready = (
        valid
        and not has_blockers
        and all(status_by_phase.get(phase_name) == "passed" for phase_name in required)
    )
    builder.put("/valid", JsonBoolean(valid))
    if scenario != "missing_field":
        builder.put("/compile_ready", JsonBoolean(compile_ready))

    if shells_value.value:
        builder.put("/task_envelope", validation_bundle["task_envelope"])
        builder.put("/authority_artifacts", validation_bundle["authority_artifacts"])
        builder.put("/validation_context", validation_bundle["validation_context"])
    else:
        builder.put("/validation_context", own_trusted_json({}))

    if scenario == "duplicate_field":
        builder.put("/valid", JsonBoolean(valid))
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
    implementation_fingerprint: str = "sha256:" + "1" * 64,
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
        "implementation_fingerprint": implementation_fingerprint,
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


def _report_schema_probe_schema(probe: str) -> dict[str, object]:
    probes: dict[str, dict[str, object]] = {
        "const": {"type": "string", "const": "expected"},
        "enum": {"type": "string", "enum": ["expected", "other"]},
        "minProperties": {"type": "object", "minProperties": 2},
        "maxProperties": {"type": "object", "maxProperties": 1},
        "exclusiveMinimum": {"type": "number", "exclusiveMinimum": 1},
        "exclusiveMaximum": {"type": "number", "exclusiveMaximum": 1},
        "multipleOf": {"type": "number", "multipleOf": 2},
        "allOf": {
            "allOf": [{"type": "string"}, {"const": "expected"}],
        },
        "anyOf": {
            "anyOf": [{"const": "expected"}, {"const": "other"}],
        },
        "oneOf": {
            "oneOf": [{"type": "number"}, {"type": "integer"}],
        },
    }
    try:
        return probes[probe]
    except KeyError:
        raise AssertionError(f"unknown report schema probe: {probe}") from None


def _report_schema_probe_instance(probe: str) -> object:
    instances: dict[str, object] = {
        "const": "actual",
        "enum": "actual",
        "minProperties": {"only": 1},
        "maxProperties": {"first": 1, "second": 2},
        "exclusiveMinimum": 1,
        "exclusiveMaximum": 1,
        "multipleOf": 3,
        "allOf": "actual",
        "anyOf": "actual",
        "oneOf": 1,
    }
    try:
        return instances[probe]
    except KeyError:
        raise AssertionError(f"unknown report schema probe: {probe}") from None


def _output_schema(
    *,
    invocation_shells: bool,
    report_schema_probe: str | None,
    artifact_identity: bool,
) -> object:
    observed_fields = (
        "recipe_input_bytes",
        "validation_bundle_input_bytes",
        "maximum_container_depth",
        "maximum_number_token_chars",
        "parsed_nodes",
        "maximum_object_members",
        "maximum_array_items",
        "decoded_string_bytes",
        "parser_work_units",
        "semantic_references",
        "schema_evaluation_shape_units",
        "diagnostics",
        "compile_blockers",
        "kernel_phase_work_units",
        "report_projection_fields",
        "report_seal_reserved_work_units",
    )
    validation_context_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
    }
    body_properties: dict[str, object] = {
        "closed": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "optional": {"type": "string"},
        "\ue000": {"type": "string"},
        "\U00010000": {"type": "string"},
    }
    body_schema: dict[str, object] = {
        "type": "object",
        "properties": body_properties,
        "additionalProperties": False,
    }
    if report_schema_probe is not None:
        body_properties["probe"] = _report_schema_probe_schema(report_schema_probe)
        body_schema["required"] = ["probe"]
    root_properties: dict[str, object] = {
        "body": {
            **body_schema,
        },
        "validation_context": validation_context_schema,
        "phases": {"type": "array", "items": {"type": "string"}},
        "validation_budget": {
            "type": "object",
            "properties": {
                "budget_profile": {"type": "string"},
                "limits_fingerprint": {
                    "type": "string",
                },
                "observed": {
                    "type": "object",
                    "properties": {
                        field_name: {"type": "integer", "minimum": 0}
                        for field_name in observed_fields
                    },
                    "required": list(observed_fields),
                    "additionalProperties": False,
                },
            },
            "required": ["budget_profile", "limits_fingerprint", "observed"],
            "additionalProperties": False,
        },
        "valid": {"type": "boolean"},
        "compile_ready": {"type": "boolean"},
        "report_fingerprint": {
            "type": "string",
        },
    }
    required = [
        "body",
        "validation_context",
        "phases",
        "validation_budget",
        "valid",
        "compile_ready",
        "report_fingerprint",
    ]
    if artifact_identity:
        root_properties["artifact_identity"] = {
            "type": "object",
            "properties": {
                "recipe_input_payload_sha256": {"type": "string"},
                "validation_bundle_input_payload_sha256": {"type": "string"},
                "recipe_value_fingerprint": {"type": ["string", "null"]},
                "validation_bundle_fingerprint": {"type": "string"},
            },
            "required": [
                "recipe_input_payload_sha256",
                "validation_bundle_input_payload_sha256",
                "recipe_value_fingerprint",
                "validation_bundle_fingerprint",
            ],
            "additionalProperties": False,
        }
        required.append("artifact_identity")
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
    profile = CORE_PROFILE if report_schema_probe is not None else PAYLOAD_PROFILE
    return admit_schema("synthetic.report:v1", value, profile)


def make_program_contribution(
    *,
    invocation_shells: bool = False,
    required_for_compile_phases: tuple[str, ...] = ("alpha", "beta"),
    report_projection_scenario: str = "normal",
    report_schema_probe: str | None = None,
    artifact_identity: bool = False,
) -> ValidationProgramContribution:
    parser_profile = _fixed_parser_profile_spec()
    tokenizer = parser_profile.tokenizer
    parser = parser_profile.parser
    canonicalizer = parser_profile.canonicalizer
    ledger = parser_profile.ledger
    schema_profile = CORE_PROFILE if report_schema_probe is not None else PAYLOAD_PROFILE
    evaluator = _component(
        schema_profile.profile_id,
        schema_profile.evaluator_id,
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
    projection_state = own_trusted_json(
        {
            "invocation_shells": invocation_shells,
            "required_for_compile_phases": list(required_for_compile_phases),
            "scenario": report_projection_scenario,
            "schema_probe": report_schema_probe or "",
            "artifact_identity": artifact_identity,
        }
    )
    if type(projection_state) is not JsonObject:
        raise AssertionError("synthetic projection state must be an object")
    projection_target = ImmutableCallableRecord(
        function=report_projection,
        state=projection_state,
    )
    projection_component = _component(
        "synthetic.report_projection:v1",
        "synthetic.report_projection_impl:v1",
        projection_target,
    )
    output_schema = _output_schema(
        invocation_shells=invocation_shells,
        report_schema_probe=report_schema_probe,
        artifact_identity=artifact_identity,
    )

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

    writable_body_paths = (
        "/body",
        "/compile_ready",
        "/phases",
        "/valid",
        "/validation_context",
    )
    if artifact_identity:
        writable_body_paths += ("/artifact_identity",)
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
        required_for_compile_phases=required_for_compile_phases,
        kernel_owned_paths=("/report_fingerprint", "/validation_budget"),
        budget_receipt_path="/validation_budget",
        writable_body_paths=writable_body_paths,
        mandatory_shells=mandatory_shells,
        outer_envelope_field_count=21,
    )

    runtime_pairs = (
        ("tokenizer", tokenizer, parse_owned_json),
        ("parser", parser, parse_owned_json),
        ("canonicalizer", canonicalizer, canonical_fingerprint_metered),
        ("ledger", ledger, create_budget_ledger),
        ("schema_evaluator", evaluator, evaluate_schema),
        ("runner", alpha, alpha_runner),
        ("runner", audit, audit_runner),
        ("runner", beta, beta_runner),
        ("export_type", alpha_export, alpha_export_validator),
        ("export_type", beta_export, beta_export_validator),
        ("report_projection", projection_component, projection_target),
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
        tuple(name for name, _ in schema_profile.runtime_dependencies),
    )
    return ValidationProgramContribution(
        program_id="synthetic.validation_program:v1",
        budget_manifest=LM9A_BUDGET_MANIFEST,
        parser_profile=parser_profile,
        schema_evaluator_profiles=(
            SchemaEvaluatorSpec(profile=schema_profile, evaluator=evaluator),
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


def make_phase_engine_contribution(
    *,
    alpha_scenario: str = "passed",
    audit_scenario: str = "passed",
    beta_scenario: str = "passed",
    alpha_permitted_statuses: tuple[str, ...] = ("passed", "blocked"),
    alpha_required_statuses: tuple[str, ...] = ("passed", "blocked"),
    audit_ordering_after: tuple[str, ...] = ("alpha",),
    invocation_cardinality: str = "exactly_one",
    beta_output_type: str = "synthetic.beta:v1",
    beta_export_validator: object = phase_text_export_validator,
    beta_output_cardinality: str = "zero_or_one",
    required_for_compile_phases: tuple[str, ...] = ("alpha", "beta"),
    report_projection_scenario: str = "normal",
    report_schema_probe: str | None = None,
    artifact_identity: bool = False,
) -> ValidationProgramContribution:
    contribution = make_program_contribution(
        invocation_shells=True,
        required_for_compile_phases=required_for_compile_phases,
        report_projection_scenario=report_projection_scenario,
        report_schema_probe=report_schema_probe,
        artifact_identity=artifact_identity,
    )
    if alpha_scenario == "schema_issue_stress":
        stress_schema_value = own_trusted_json(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["items"],
                "additionalProperties": False,
            }
        )
        if type(stress_schema_value) is not JsonObject:
            raise AssertionError("stress schema must be an object")
        stress_schema = admit_schema(
            "synthetic.issue_stress:v1",
            stress_schema_value,
            PAYLOAD_PROFILE,
        )
        contribution = replace(
            contribution,
            schemas=(*contribution.schemas, stress_schema),
            runtime_bindings=(
                *contribution.runtime_bindings,
                RuntimeBinding(
                    binding_kind="schema",
                    binding_id=stress_schema.schema_id,
                    implementation_fingerprint=stress_schema.schema_fingerprint,
                    target=stress_schema,
                ),
            ),
        )

    def runner_record(phase_name: str, scenario: str) -> ImmutableCallableRecord:
        state = own_trusted_json(
            {"phase_name": phase_name, "scenario": scenario}
        )
        assert type(state) is JsonObject
        return ImmutableCallableRecord(function=phase_engine_runner_dispatch, state=state)

    alpha_target = runner_record("alpha", alpha_scenario)
    audit_target = runner_record("audit", audit_scenario)
    beta_target = runner_record("beta", beta_scenario)
    alpha = _component("alpha", "synthetic.engine.alpha:v1", alpha_target)
    audit = _component("audit", "synthetic.engine.audit:v1", audit_target)
    beta = _component("beta", "synthetic.engine.beta:v1", beta_target)
    alpha_export = _component(
        "synthetic.alpha:v1",
        "synthetic.engine_export.alpha:v1",
        phase_index_export_validator,
    )
    beta_export = _component(
        beta_output_type,
        "synthetic.engine_export.beta:v1",
        beta_export_validator,
    )

    phase_by_name = {phase.phase_name: phase for phase in contribution.phases}
    alpha_phase = phase_by_name["alpha"]
    alpha_binding = replace(
        alpha_phase.input_bindings[0], cardinality=invocation_cardinality
    )
    alpha_output = replace(
        alpha_phase.provided_outputs[0],
        permitted_on_statuses=alpha_permitted_statuses,
        required_on_statuses=alpha_required_statuses,
    )
    phases = (
        replace(
            alpha_phase,
            input_bindings=(alpha_binding,),
            provided_outputs=(alpha_output,),
        ),
        replace(phase_by_name["audit"], ordering_after=audit_ordering_after),
        replace(
            phase_by_name["beta"],
            provided_outputs=(
                replace(
                    phase_by_name["beta"].provided_outputs[0],
                    output_type=beta_output_type,
                    cardinality=beta_output_cardinality,
                ),
            ),
        ),
    )

    retained_bindings = tuple(
        binding
        for binding in contribution.runtime_bindings
        if binding.binding_kind not in ("runner", "export_type")
    )
    runtime_bindings = retained_bindings + (
        _binding("runner", alpha, alpha_target),
        _binding("runner", audit, audit_target),
        _binding("runner", beta, beta_target),
        _binding("export_type", alpha_export, phase_index_export_validator),
        _binding("export_type", beta_export, beta_export_validator),
    )
    RUNTIME_REGISTRY.clear()
    RUNTIME_REGISTRY.update(
        {
            (binding.binding_kind, binding.binding_id): binding.target
            for binding in runtime_bindings
        }
    )
    invocation_inputs = (
        replace(
            contribution.invocation_inputs[0], cardinality=invocation_cardinality
        ),
    )
    return replace(
        contribution,
        phases=phases,
        runners=(alpha, audit, beta),
        invocation_inputs=invocation_inputs,
        export_types=(
            ExportTypeSpec(
                export_type="synthetic.alpha:v1", validator=alpha_export
            ),
            ExportTypeSpec(
                export_type=beta_output_type, validator=beta_export
            ),
        ),
        runtime_bindings=runtime_bindings,
    )


def make_validation_api_contribution(
    *,
    companion_scenario: str = "normal",
    schema_scenario: str = "normal",
    report_projection_scenario: str = "normal",
) -> ValidationProgramContribution:
    contribution = make_program_contribution(
        invocation_shells=True,
        required_for_compile_phases=("companion_artifacts", "schema"),
        report_projection_scenario=report_projection_scenario,
        artifact_identity=True,
    )

    def runner_record(phase_name: str, scenario: str) -> ImmutableCallableRecord:
        state = own_trusted_json(
            {"phase_name": phase_name, "scenario": scenario}
        )
        assert type(state) is JsonObject
        return ImmutableCallableRecord(
            function=validation_api_runner_dispatch,
            state=state,
        )

    companion_target = runner_record("companion_artifacts", companion_scenario)
    schema_target = runner_record("schema", schema_scenario)
    companion = _component(
        "companion_artifacts",
        "synthetic.api.companion_artifacts:v1",
        companion_target,
    )
    schema = _component("schema", "synthetic.api.schema:v1", schema_target)
    phases = (
        PhaseSpec(
            phase_name="companion_artifacts",
            ordering_after=(),
            input_bindings=(
                InputBinding(
                    input_name="validation_bundle",
                    source_kind="invocation_input",
                    source_input="validation_bundle",
                    source_constant=None,
                    source_phase=None,
                    source_output=None,
                    expected_type="kernel.json_object:v1",
                    cardinality="exactly_one",
                ),
            ),
            provided_outputs=(),
            runner_id="companion_artifacts",
            permitted_diagnostic_codes=("synthetic_companion_invalid",),
            permitted_blocker_codes=(),
        ),
        PhaseSpec(
            phase_name="schema",
            ordering_after=(),
            input_bindings=(
                InputBinding(
                    input_name="recipe",
                    source_kind="invocation_input",
                    source_input="recipe",
                    source_constant=None,
                    source_phase=None,
                    source_output=None,
                    expected_type="kernel.json_value:v1",
                    cardinality="exactly_one",
                ),
                InputBinding(
                    input_name="recipe_parse_evidence",
                    source_kind="invocation_input",
                    source_input="recipe_parse_evidence",
                    source_constant=None,
                    source_phase=None,
                    source_output=None,
                    expected_type="kernel.json_value:v1",
                    cardinality="exactly_one",
                ),
            ),
            provided_outputs=(),
            runner_id="schema",
            permitted_diagnostic_codes=("synthetic_recipe_invalid",),
            permitted_blocker_codes=(),
        ),
    )
    retained_bindings = tuple(
        binding
        for binding in contribution.runtime_bindings
        if binding.binding_kind != "runner"
    )
    runtime_bindings = retained_bindings + (
        _binding("runner", companion, companion_target),
        _binding("runner", schema, schema_target),
    )
    RUNTIME_REGISTRY.clear()
    RUNTIME_REGISTRY.update(
        {
            (binding.binding_kind, binding.binding_id): binding.target
            for binding in runtime_bindings
        }
    )
    return replace(
        contribution,
        invocation_inputs=(
            InvocationInputSpec(
                input_name="recipe",
                value_type="kernel.json_value:v1",
                cardinality="exactly_one",
            ),
            InvocationInputSpec(
                input_name="recipe_parse_evidence",
                value_type="kernel.json_value:v1",
                cardinality="exactly_one",
            ),
            InvocationInputSpec(
                input_name="validation_bundle",
                value_type="kernel.json_object:v1",
                cardinality="exactly_one",
            ),
        ),
        phases=phases,
        runners=(companion, schema),
        issue_vocabulary=(
            IssueSpec(
                code="synthetic_companion_invalid",
                classification="diagnostic",
            ),
            IssueSpec(
                code="synthetic_recipe_invalid",
                classification="diagnostic",
            ),
        ),
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


class ImmutableArtifactStore:
    """Exact-object artifact store used by release-conformance tests."""

    __slots__ = ("_artifacts", "resolved_refs")

    def __init__(self, artifacts: dict[str, object]) -> None:
        self._artifacts = MappingProxyType(dict(artifacts))
        self.resolved_refs: list[str] = []

    def resolve_exact_bytes(self, content_ref: str) -> object:
        self.resolved_refs.append(content_ref)
        return self._artifacts.get(content_ref)


@dataclass(frozen=True, slots=True)
class BoundaryCampaignFixture:
    program: object
    assembler_profile: object
    gate_profile: object
    recipe_bytes: bytes
    bundle_bytes: bytes
    trusted_bundle: object
    campaign_bytes: bytes
    campaign_fingerprint: str
    validation_golden_key: str
    fixture_context: object


def _boundary_fingerprinted(
    value: dict[str, object], fingerprint_field: str
) -> dict[str, object]:
    unsigned = {
        key: item for key, item in value.items() if key != fingerprint_field
    }
    return {
        **unsigned,
        fingerprint_field: canonical_fingerprint(own_trusted_json(unsigned)),
    }


def _boundary_case_set_fingerprint(
    cases: list[dict[str, object]],
) -> str:
    pairs = [
        {
            "case_id": case["case_id"],
            "case_fingerprint": case["case_fingerprint"],
        }
        for case in sorted(cases, key=lambda item: str(item["case_id"]))
    ]
    return canonical_fingerprint(own_trusted_json(pairs))


def validation_golden_key(
    program: object,
    recipe_bytes: bytes,
    bundle_bytes: bytes,
    assembler_profile: object,
) -> str:
    """Address one expected validation envelope by all invocation identities."""

    return canonical_fingerprint(
        own_trusted_json(
            {
                "program_fingerprint": program.program_fingerprint,
                "recipe_input_payload_sha256": sha256_prefixed(recipe_bytes),
                "validation_bundle_input_payload_sha256": sha256_prefixed(
                    bundle_bytes
                ),
                "assembler_profile_fingerprint": (
                    assembler_profile.profile_fingerprint
                ),
            }
        )
    )


def make_boundary_campaign_fixture(
    *,
    expected_results: Mapping[str, Mapping[str, object]],
    recipe_bytes: bytes = b'{"case_id":"boundary.success","value":"ok"}',
    bundle_bytes: bytes | None = None,
    alpha_scenario: str = "boundary_matrix",
    core_bytes: bytes = b'{"value":"ok"}',
    assembler_implementation_fingerprint: str = "sha256:" + "1" * 64,
    gate_callable: object | None = None,
    wide_core_schema: bool = False,
) -> BoundaryCampaignFixture:
    """Build the exact sealed validation/conformance boundary fixture."""

    import rook.validation_kernel.conformance as conformance_module
    from rook.validation_kernel.conformance import seal_conformance_gate_profile
    from rook.validation_kernel.invocation import (
        issue_trusted_validation_bundle,
        seal_trusted_bundle_assembler_profile,
    )
    from rook.validation_kernel.program import compose_and_seal_program

    if bundle_bytes is None:
        bundle_bytes = make_validation_bundle_bytes()
    program = compose_and_seal_program(
        make_conformance_program_contribution(
            alpha_scenario=alpha_scenario,
            artifact_identity=True,
            wide_core_schema=wide_core_schema,
        )
    )
    assembler_profile = seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate(
            implementation_fingerprint=assembler_implementation_fingerprint
        )
    )
    if gate_callable is None:
        gate_callable = conformance_module._execute_conformance_gate
    gate_profile = seal_conformance_gate_profile(
        make_conformance_gate_profile_candidate(gate_callable),
        gate_callable,  # type: ignore[arg-type]
    )
    trusted_bundle = issue_trusted_validation_bundle(
        assembler_profile,
        bundle_bytes,
    )
    golden_key = validation_golden_key(
        program,
        recipe_bytes,
        bundle_bytes,
        assembler_profile,
    )
    try:
        expected_result = dict(expected_results[golden_key])
    except KeyError:
        raise AssertionError(
            f"no static validation golden for exact key {golden_key}"
        ) from None
    fixture_id = (
        "fixture.boundary_report"
        if expected_result["result_kind"] == "published_report"
        else "fixture.boundary_control_failure"
    )

    core_ref = "artifact:boundary-core-positive"
    fixture_ref = "artifact:boundary-fixture"
    recipe_ref = "artifact:boundary-recipe"
    bundle_ref = "artifact:boundary-bundle"
    fixture_manifest = _boundary_fingerprinted(
        {
            "schema": "rook.validation_conformance_fixture:v1",
            "fixture_id": fixture_id,
            "recipe_input": {
                "content_ref": recipe_ref,
                "input_payload_sha256": sha256_prefixed(recipe_bytes),
            },
            "validation_bundle_input": {
                "content_ref": bundle_ref,
                "input_payload_sha256": sha256_prefixed(bundle_bytes),
            },
            "assembler_profile_fingerprint": (
                assembler_profile.profile_fingerprint
            ),
            "expected_result": expected_result,
        },
        "fixture_fingerprint",
    )
    fixture_bytes = canonical_json_bytes(own_trusted_json(fixture_manifest))

    core_schema = next(
        schema
        for schema in program.schemas
        if schema.profile_id == CORE_PROFILE.profile_id
    )
    core_value = json.loads(core_bytes)
    core_case = _boundary_fingerprinted(
        {
            "case_id": "core.boundary_positive",
            "case_kind": "core_schema_positive",
            "schema_case": {
                "schema_id": core_schema.schema_id,
                "schema_fingerprint": core_schema.schema_fingerprint,
                "instance_fingerprint": canonical_fingerprint(
                    own_trusted_json(core_value)
                ),
                "instance_content_ref": core_ref,
            },
            "fixture_case": None,
        },
        "case_fingerprint",
    )
    fixture_case = _boundary_fingerprinted(
        {
            "case_id": fixture_id,
            "case_kind": "semantic_fixture",
            "schema_case": None,
            "fixture_case": {
                "fixture_fingerprint": fixture_manifest[
                    "fixture_fingerprint"
                ],
                "fixture_content_ref": fixture_ref,
                "recipe_input_payload_sha256": sha256_prefixed(recipe_bytes),
                "validation_bundle_input_payload_sha256": sha256_prefixed(
                    bundle_bytes
                ),
                "assembler_profile_fingerprint": (
                    assembler_profile.profile_fingerprint
                ),
            },
        },
        "case_fingerprint",
    )
    cases = [core_case, fixture_case]
    campaign: dict[str, object] = {
        "schema": "rook.validation_conformance_campaign:v1",
        "campaign_id": "synthetic.boundary_campaign:v1",
        "campaign_version": "v1",
        "program_id": program.program_id,
        "program_fingerprint": program.program_fingerprint,
        "required_gate_profile_fingerprint": (
            gate_profile.gate_profile_fingerprint
        ),
        "required_cases": sorted(cases, key=lambda item: str(item["case_id"])),
        "required_case_set_fingerprint": _boundary_case_set_fingerprint(
            cases
        ),
    }
    campaign = _boundary_fingerprinted(campaign, "campaign_fingerprint")
    campaign_bytes = canonical_json_bytes(own_trusted_json(campaign))

    store = ImmutableArtifactStore(
        {
            core_ref: core_bytes,
            fixture_ref: fixture_bytes,
            recipe_ref: recipe_bytes,
            bundle_ref: bundle_bytes,
        }
    )
    fixture_context = conformance_module._issue_trusted_conformance_fixture_context(
        store,
        (assembler_profile,),
    )
    return BoundaryCampaignFixture(
        program=program,
        assembler_profile=assembler_profile,
        gate_profile=gate_profile,
        recipe_bytes=recipe_bytes,
        bundle_bytes=bundle_bytes,
        trusted_bundle=trusted_bundle,
        campaign_bytes=campaign_bytes,
        campaign_fingerprint=str(campaign["campaign_fingerprint"]),
        validation_golden_key=golden_key,
        fixture_context=fixture_context,
    )


def make_conformance_gate_profile_candidate(gate_callable: object) -> JsonObject:
    candidate: dict[str, object] = {
        "schema": "rook.validation_conformance_gate_profile:v1",
        "gate_profile_id": "rook.validation_conformance_gate:lm9a_v1",
        "gate_profile_version": "v1",
        "gate_implementation_fingerprint": runtime_implementation_fingerprint(
            gate_callable
        ),
        "budget_profile": LM9A_BUDGET_MANIFEST.profile_id,
        "limits_fingerprint": LM9A_BUDGET_MANIFEST.limits_fingerprint,
        "campaign_input_byte_limit": 4_194_304,
        "referenced_case_content_byte_limit": 4_194_304,
    }
    candidate["gate_profile_fingerprint"] = canonical_fingerprint(
        own_trusted_json(candidate)
    )
    owned = own_trusted_json(candidate)
    if type(owned) is not JsonObject:
        raise AssertionError("synthetic conformance gate profile must be an object")
    return owned


def alternate_conformance_gate(
    profile: object,
    program: object,
    raw_campaign_bytes: bytes,
    captured_context: object,
) -> object:
    """Independent sealed test binding with unchanged gate semantics."""

    import rook.validation_kernel.conformance as conformance_module

    return conformance_module._execute_conformance_gate(
        profile,
        program,
        raw_campaign_bytes,
        captured_context,
    )


def make_conformance_program_contribution(
    *,
    alpha_scenario: str = "passed",
    wide_core_schema: bool = False,
    artifact_identity: bool = False,
) -> ValidationProgramContribution:
    """Add one unused, domain-neutral core schema to the synthetic program."""

    contribution = make_phase_engine_contribution(
        alpha_scenario=alpha_scenario,
        artifact_identity=artifact_identity,
    )
    core_schema_host: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": True,
    }
    if wide_core_schema:
        core_schema_host["$defs"] = {
            f"unused_{index:04d}": {} for index in range(2_100)
        }
    core_schema_value = own_trusted_json(core_schema_host)
    if type(core_schema_value) is not JsonObject:
        raise AssertionError("synthetic core schema must be an object")
    core_schema = admit_schema(
        "synthetic.core_positive:v1",
        core_schema_value,
        CORE_PROFILE,
    )
    core_evaluator = _component(
        CORE_PROFILE.profile_id,
        CORE_PROFILE.evaluator_id,
        evaluate_schema,
    )
    return replace(
        contribution,
        schema_evaluator_profiles=(
            *contribution.schema_evaluator_profiles,
            SchemaEvaluatorSpec(profile=CORE_PROFILE, evaluator=core_evaluator),
        ),
        schemas=(*contribution.schemas, core_schema),
        runtime_bindings=(
            *contribution.runtime_bindings,
            _binding("schema_evaluator", core_evaluator, evaluate_schema),
            RuntimeBinding(
                binding_kind="schema",
                binding_id=core_schema.schema_id,
                implementation_fingerprint=core_schema.schema_fingerprint,
                target=core_schema,
            ),
        ),
    )


__all__ = (
    "alternate_conformance_gate",
    "BoundaryCampaignFixture",
    "ImmutableArtifactStore",
    "INVOCATION_MANDATORY_SHELLS",
    "HugeTypeMetadataError",
    "KERNEL_STRING_EXPORT_CALLS",
    "MutableCallable",
    "MutableService",
    "RUNTIME_REGISTRY",
    "SYNTHETIC_WIDE_PHASE_INDEX",
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
    "make_boundary_campaign_fixture",
    "make_conformance_gate_profile_candidate",
    "make_conformance_program_contribution",
    "make_phase_engine_contribution",
    "make_program_contribution",
    "make_validation_api_contribution",
    "make_validation_bundle_bytes",
    "non_boolean_kernel_string_export_validator",
    "raising_kernel_string_export_validator",
    "rejecting_kernel_string_export_validator",
    "replace_runtime_component",
    "SyntheticMutablePhaseIndex",
    "SyntheticPhaseIndex",
    "SyntheticWidePhaseIndex",
    "validation_golden_key",
)
