"""Deterministic typed phase execution over one sealed validation program."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Literal, cast

from .budget import BudgetExceeded
from .canonical_json import utf16_sort_key
from .control import (
    ArtifactRole,
    BudgetDimension,
    FailureStage,
    ValidationControlFailure,
    make_control_failure,
)
from .invocation import _ValidationExecutionContext
from .owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
)
from .phase_contract import Cardinality, InputBinding, PhaseSpec, ProvidedOutput
from .program import SealedValidationProgram
from .schema_profile import (
    InstanceBinding,
    SchemaEvaluationReceipt,
    SchemaIssue,
)


PhaseStatus = Literal["passed", "blocked", "failed", "not_evaluated"]
IssueSeverity = Literal["error", "warning", "information"]

_ISSUE_SEVERITIES = frozenset(("error", "warning", "information"))
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_ISSUE_MESSAGE_CODE_POINTS = 512
_MAX_ISSUE_PATH_CODE_POINTS = 2_048
_MAX_EXCEPTION_PREFIX_CODE_POINTS = 2_048
_UNAVAILABLE = object()
_OWNED_VALUE_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)
_SCALAR_IMMUTABLE_TYPES = (type(None), bool, int, float, str, bytes)
_BUILTIN_TYPE_IDS: dict[str, tuple[type[object], ...]] = {
    "kernel.json_value:v1": _OWNED_VALUE_TYPES,
    "kernel.json_null:v1": (JsonNull,),
    "kernel.boolean:v1": (JsonBoolean,),
    "kernel.string:v1": (JsonString,),
    "kernel.number:v1": (JsonNumber,),
    "kernel.json_array:v1": (JsonArray,),
    "kernel.json_object:v1": (JsonObject,),
}


@dataclass(frozen=True, slots=True)
class KernelIssue:
    classification: Literal["diagnostic", "compile_blocker"]
    code: str
    severity: IssueSeverity | None
    subject_id: str | None
    path: str | None
    related_paths: tuple[str, ...]
    bounded_message: str
    detail_sha256: str | None


@dataclass(frozen=True, slots=True)
class NamedOutput:
    output_name: str
    values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class RunnerResult:
    diagnostics: tuple[KernelIssue, ...]
    compile_blockers: tuple[KernelIssue, ...]
    outputs: tuple[NamedOutput, ...]


@dataclass(frozen=True, slots=True)
class PhaseResult:
    phase_name: str
    status: PhaseStatus
    diagnostics: tuple[KernelIssue, ...]
    compile_blockers: tuple[KernelIssue, ...]
    outputs: tuple[NamedOutput, ...]
    kernel_work_units_delta: int


@dataclass(frozen=True, slots=True)
class _SchemaEvaluationView:
    evaluation_passed: bool | None
    bounded_errors: tuple[SchemaIssue, ...]
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class _PhaseInputs(Mapping[str, tuple[object, ...]]):
    _members: tuple[tuple[str, tuple[object, ...]], ...]

    def __getitem__(self, key: str) -> tuple[object, ...]:
        if type(key) is not str:
            raise KeyError(key)
        for name, values in self._members:
            if name == key:
                return values
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self._members)

    def __len__(self) -> int:
        return len(self._members)


class _PhaseHelperFacade:
    """A narrow immutable surface whose closures retain engine authority."""

    __slots__ = ("__charge_work_units", "__evaluate_schema", "__sealed")

    def __init__(
        self,
        charge_work_units: Callable[[int], None],
        evaluate_schema: Callable[
            [str, JsonValue, InstanceBinding], _SchemaEvaluationView
        ],
    ) -> None:
        object.__setattr__(self, "_PhaseHelperFacade__charge_work_units", charge_work_units)
        object.__setattr__(self, "_PhaseHelperFacade__evaluate_schema", evaluate_schema)
        object.__setattr__(self, "_PhaseHelperFacade__sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("phase helper facade is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("phase helper facade is immutable")

    def charge_work_units(self, amount: int) -> None:
        self.__charge_work_units(amount)

    def evaluate_schema(
        self,
        schema_id: str,
        instance: JsonValue,
        *,
        instance_binding: InstanceBinding,
    ) -> _SchemaEvaluationView:
        return self.__evaluate_schema(schema_id, instance, instance_binding)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class _PhaseExecutionAudit:
    program_id: str
    program_fingerprint: str
    schema_evaluation_receipts: tuple[SchemaEvaluationReceipt, ...]

    def __init__(self) -> None:
        raise TypeError("phase execution audits are kernel-issued")

    def __copy__(self) -> object:
        raise TypeError("phase execution audits cannot be copied")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("phase execution audits cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("phase execution audits cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("phase execution audits cannot be serialized")


class _IntegrityError(RuntimeError):
    def __init__(self, evidence: str) -> None:
        self.evidence = evidence
        super().__init__("phase engine integrity failure")


class _RuntimeComponentError(RuntimeError):
    def __init__(self, exception: Exception) -> None:
        self.exception = exception
        super().__init__("sealed runtime component failed")


def _issue_subject_path(phase_name: str) -> str:
    token = phase_name.replace("~", "~0").replace("/", "~1")
    return f"/phases/{token}"


def _integrity_failure(
    program: SealedValidationProgram | None,
    phase_name: str | None,
    evidence: str,
) -> ValidationControlFailure:
    phase_evidence = "<engine>" if phase_name is None else phase_name
    detail = f"rook.phase_integrity:v1\0{phase_evidence}\0{evidence}".encode(
        "utf-8"
    )
    return make_control_failure(
        failure_stage=FailureStage.VALIDATION,
        code="validator_integrity_failure",
        artifact_role=ArtifactRole.PHASE_ENGINE,
        program_id=None if program is None else program.program_id,
        program_fingerprint=None if program is None else program.program_fingerprint,
        subject_path=None if phase_name is None else _issue_subject_path(phase_name),
        message="Validator integrity check failed.",
        detail=detail,
    )


def _bounded_exception_evidence(exception: Exception) -> bytes:
    digest = hashlib.sha256(b"rook.phase_exception_evidence:v1\0")
    type_name = f"{type(exception).__module__}.{type(exception).__qualname__}"
    digest.update(type_name.encode("utf-8", "backslashreplace"))
    args = exception.args
    digest.update(len(args).to_bytes(8, "big"))
    for argument in args[:4]:
        digest.update(b"\0")
        if type(argument) is str:
            digest.update(b"str\0")
            digest.update(len(argument).to_bytes(16, "big"))
            prefix = argument[:_MAX_EXCEPTION_PREFIX_CODE_POINTS]
            digest.update(prefix.encode("utf-8", "backslashreplace"))
        elif type(argument) is bytes:
            digest.update(b"bytes\0")
            digest.update(len(argument).to_bytes(16, "big"))
            digest.update(argument[:4_096])
        elif argument is None:
            digest.update(b"none")
        elif type(argument) is bool:
            digest.update(b"bool\1" if argument else b"bool\0")
        elif type(argument) is int:
            magnitude = abs(argument)
            bit_length = magnitude.bit_length()
            digest.update(b"int\0")
            digest.update(b"-" if argument < 0 else b"+")
            digest.update(bit_length.to_bytes(16, "big"))
            low = magnitude & ((1 << 256) - 1)
            high = magnitude >> max(0, bit_length - 256)
            digest.update(high.to_bytes(32, "big"))
            digest.update(low.to_bytes(32, "big"))
        elif type(argument) is float:
            digest.update(b"float\0")
            digest.update(argument.hex().encode("ascii"))
        else:
            argument_type = f"{type(argument).__module__}.{type(argument).__qualname__}"
            digest.update(b"typed\0")
            digest.update(argument_type.encode("utf-8", "backslashreplace"))
    return digest.digest()


def _internal_failure(
    program: SealedValidationProgram | None,
    phase_name: str | None,
    exception: Exception,
) -> ValidationControlFailure:
    return make_control_failure(
        failure_stage=FailureStage.VALIDATION,
        code="validator_internal_failure",
        artifact_role=ArtifactRole.PHASE_ENGINE,
        program_id=None if program is None else program.program_id,
        program_fingerprint=None if program is None else program.program_fingerprint,
        subject_path=None if phase_name is None else _issue_subject_path(phase_name),
        message="Validator internal failure.",
        detail=_bounded_exception_evidence(exception),
    )


def _budget_failure(
    exception: BudgetExceeded, program: SealedValidationProgram
) -> ValidationControlFailure:
    return replace(
        exception.failure,
        program_id=program.program_id,
        program_fingerprint=program.program_fingerprint,
    )


def _make_execution_audit(
    program: SealedValidationProgram,
    receipts: tuple[SchemaEvaluationReceipt, ...],
) -> _PhaseExecutionAudit:
    audit = object.__new__(_PhaseExecutionAudit)
    object.__setattr__(audit, "program_id", program.program_id)
    object.__setattr__(audit, "program_fingerprint", program.program_fingerprint)
    object.__setattr__(audit, "schema_evaluation_receipts", receipts)
    return audit


def _has_only_dataclass_slots(value: object) -> bool:
    value_type = type(value)
    if hasattr(value, "__dict__"):
        return False
    dataclass_names = {field.name for field in fields(value)}
    slot_names: set[str] = set()
    for base in value_type.__mro__:
        slots = base.__dict__.get("__slots__", ())
        if type(slots) is str:
            slot_names.add(slots)
        else:
            slot_names.update(cast(tuple[str, ...], slots))
    slot_names.discard("__weakref__")
    return slot_names == dataclass_names


def _is_transitively_immutable(root: object) -> bool:
    stack = [root]
    seen: set[int] = set()
    while stack:
        value = stack.pop()
        value_type = type(value)
        if value_type in _OWNED_VALUE_TYPES or value_type in _SCALAR_IMMUTABLE_TYPES:
            continue
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        if value_type is tuple:
            stack.extend(value)
            continue
        if not is_dataclass(value) or isinstance(value, type):
            return False
        parameters = getattr(value_type, "__dataclass_params__", None)
        if parameters is None or parameters.frozen is not True:
            return False
        if not _has_only_dataclass_slots(value):
            return False
        stack.extend(getattr(value, field.name) for field in fields(value))
    return True


def _cardinality_is_valid(cardinality: Cardinality, count: int) -> bool:
    if cardinality == "exactly_one":
        return count == 1
    if cardinality == "zero_or_one":
        return count <= 1
    return cardinality == "many"


def _owned_source_values(value: JsonValue, cardinality: Cardinality) -> tuple[object, ...]:
    if cardinality == "exactly_one":
        return (value,)
    if cardinality == "zero_or_one":
        return () if type(value) is JsonNull else (value,)
    if cardinality == "many":
        if type(value) is not JsonArray:
            raise _IntegrityError("many-valued owned input is not an owned array")
        return cast(tuple[object, ...], value.items)
    raise _IntegrityError("input cardinality is not closed")


def _value_matches_type(
    program: SealedValidationProgram, expected_type: str, value: object
) -> bool:
    builtin_types = _BUILTIN_TYPE_IDS.get(expected_type)
    if builtin_types is not None:
        return type(value) in builtin_types
    if ("export_type", expected_type) not in program.runtime_binding_keys:
        raise _IntegrityError("bound input type has no sealed validator")
    validator = program.resolve_runtime_binding("export_type", expected_type)
    try:
        accepted = validator(value)  # type: ignore[operator]
    except Exception as exception:
        raise _RuntimeComponentError(exception) from exception
    if type(accepted) is not bool:
        raise _IntegrityError("export validator returned a non-boolean result")
    return accepted


def _provided_output(
    phase: PhaseSpec, output_name: str
) -> ProvidedOutput | None:
    for output in phase.provided_outputs:
        if output.output_name == output_name:
            return output
    return None


def _resolve_binding(
    context: _ValidationExecutionContext,
    phase_by_name: Mapping[str, PhaseSpec],
    results_by_name: Mapping[str, PhaseResult],
    binding: InputBinding,
) -> tuple[object, ...] | object:
    program = context.invocation.program
    if binding.source_kind == "invocation_input":
        source_name = cast(str, binding.source_input)
        try:
            source = context.invocation.invocation_inputs[source_name]
        except KeyError as exception:
            raise _IntegrityError("captured invocation input is missing") from exception
        values = _owned_source_values(source, binding.cardinality)
    elif binding.source_kind == "program_constant":
        source_name = cast(str, binding.source_constant)
        try:
            source = program.resolve_program_constant(source_name)
        except KeyError as exception:
            raise _IntegrityError("sealed program constant is missing") from exception
        values = _owned_source_values(source, binding.cardinality)
    elif binding.source_kind == "phase_output":
        source_phase_name = cast(str, binding.source_phase)
        source_output_name = cast(str, binding.source_output)
        source_phase = phase_by_name.get(source_phase_name)
        provider = results_by_name.get(source_phase_name)
        if source_phase is None or provider is None:
            raise _IntegrityError("bound producer has no prior result")
        if provider.status in ("failed", "not_evaluated"):
            return _UNAVAILABLE
        output_spec = _provided_output(source_phase, source_output_name)
        if output_spec is None:
            raise _IntegrityError("bound producer output declaration is missing")
        named = next(
            (
                output
                for output in provider.outputs
                if output.output_name == source_output_name
            ),
            None,
        )
        if named is None:
            if provider.status in output_spec.required_on_statuses:
                raise _IntegrityError("provider omitted a promised required output")
            return _UNAVAILABLE
        values = named.values
    else:
        raise _IntegrityError("input source kind is not closed")

    if not _cardinality_is_valid(binding.cardinality, len(values)):
        raise _IntegrityError("bound input cardinality is invalid")
    if binding.cardinality == "zero_or_one" and not values:
        return _UNAVAILABLE
    for value in values:
        if not _is_transitively_immutable(value):
            raise _IntegrityError("bound input is not transitively immutable")
        if not _value_matches_type(program, binding.expected_type, value):
            raise _IntegrityError("bound input has the wrong sealed type")
    return values


def _valid_pointer(value: str) -> bool:
    if value == "":
        return True
    if not value.startswith("/"):
        return False
    index = 0
    while index < len(value):
        if value[index] == "~":
            if index + 1 == len(value) or value[index + 1] not in ("0", "1"):
                return False
            index += 2
        else:
            index += 1
    return True


def _bounded_scalar_string(value: object, limit: int) -> bool:
    if type(value) is not str or len(value) > limit:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _validate_issue(
    issue: object,
    *,
    classification: Literal["diagnostic", "compile_blocker"],
    permitted_codes: tuple[str, ...],
) -> KernelIssue:
    if type(issue) is not KernelIssue:
        raise _IntegrityError("runner issue is not an exact KernelIssue")
    if type(issue.classification) is not str or type(issue.code) is not str:
        raise _IntegrityError("runner issue identity fields are not exact strings")
    if issue.classification != classification:
        raise _IntegrityError("runner issue classification is wrong")
    if issue.code not in permitted_codes:
        raise _IntegrityError("runner issue code is not registered for the phase")
    if classification == "diagnostic":
        if type(issue.severity) is not str or issue.severity not in _ISSUE_SEVERITIES:
            raise _IntegrityError("diagnostic severity is not closed")
    elif issue.severity is not None:
        raise _IntegrityError("compile blocker cannot author diagnostic severity")
    if issue.subject_id is not None and not _bounded_scalar_string(
        issue.subject_id, _MAX_ISSUE_PATH_CODE_POINTS
    ):
        raise _IntegrityError("issue subject identity is invalid")
    if issue.path is not None and (
        not _bounded_scalar_string(issue.path, _MAX_ISSUE_PATH_CODE_POINTS)
        or not _valid_pointer(issue.path)
    ):
        raise _IntegrityError("issue path is invalid")
    if type(issue.related_paths) is not tuple:
        raise _IntegrityError("issue related paths are not an exact tuple")
    if any(
        not _bounded_scalar_string(path, _MAX_ISSUE_PATH_CODE_POINTS)
        or not _valid_pointer(path)
        for path in issue.related_paths
    ):
        raise _IntegrityError("issue related path is invalid")
    if not _bounded_scalar_string(
        issue.bounded_message, _MAX_ISSUE_MESSAGE_CODE_POINTS
    ):
        raise _IntegrityError("issue message is not bounded")
    if issue.detail_sha256 is not None and (
        type(issue.detail_sha256) is not str
        or _SHA256_RE.fullmatch(issue.detail_sha256) is None
    ):
        raise _IntegrityError("issue detail fingerprint is invalid")
    return issue


def _validate_issues(
    context: _ValidationExecutionContext,
    phase: PhaseSpec,
    result: RunnerResult,
) -> tuple[tuple[KernelIssue, ...], tuple[KernelIssue, ...]]:
    if type(result.diagnostics) is not tuple:
        raise _IntegrityError("diagnostics collection is not an exact tuple")
    if type(result.compile_blockers) is not tuple:
        raise _IntegrityError("compile blocker collection is not an exact tuple")
    subject_path = _issue_subject_path(phase.phase_name)
    diagnostics: list[KernelIssue] = []
    for issue in result.diagnostics:
        context.ledger.charge(
            BudgetDimension.DIAGNOSTICS,
            1,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=subject_path,
        )
        diagnostics.append(
            _validate_issue(
                issue,
                classification="diagnostic",
                permitted_codes=phase.permitted_diagnostic_codes,
            )
        )
    blockers: list[KernelIssue] = []
    for issue in result.compile_blockers:
        context.ledger.charge(
            BudgetDimension.COMPILE_BLOCKERS,
            1,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=subject_path,
        )
        blockers.append(
            _validate_issue(
                issue,
                classification="compile_blocker",
                permitted_codes=phase.permitted_blocker_codes,
            )
        )
    return tuple(diagnostics), tuple(blockers)


def _derive_status(
    diagnostics: tuple[KernelIssue, ...],
    blockers: tuple[KernelIssue, ...],
) -> Literal["passed", "blocked", "failed"]:
    if any(issue.severity == "error" for issue in diagnostics):
        return "failed"
    if blockers:
        return "blocked"
    return "passed"


def _validate_outputs(
    program: SealedValidationProgram,
    phase: PhaseSpec,
    raw_outputs: object,
    status: Literal["passed", "blocked", "failed"],
) -> tuple[NamedOutput, ...]:
    if type(raw_outputs) is not tuple:
        raise _IntegrityError("runner outputs are not an exact tuple")
    declarations = {
        output.output_name: output for output in phase.provided_outputs
    }
    accepted: dict[str, NamedOutput] = {}
    for raw_output in raw_outputs:
        if type(raw_output) is not NamedOutput:
            raise _IntegrityError("runner output is not an exact NamedOutput")
        if type(raw_output.output_name) is not str:
            raise _IntegrityError("runner output name is not an exact string")
        if raw_output.output_name in accepted:
            raise _IntegrityError("runner returned a duplicate output")
        declaration = declarations.get(raw_output.output_name)
        if declaration is None:
            raise _IntegrityError("runner returned an undeclared output")
        if type(raw_output.values) is not tuple:
            raise _IntegrityError("runner output values are not an exact tuple")
        if not _cardinality_is_valid(declaration.cardinality, len(raw_output.values)):
            raise _IntegrityError("runner output cardinality is wrong")
        for value in raw_output.values:
            if not _is_transitively_immutable(value):
                raise _IntegrityError("runner output is not transitively immutable")
            if not _value_matches_type(program, declaration.output_type, value):
                raise _IntegrityError("runner output has the wrong sealed type")
        accepted[raw_output.output_name] = raw_output

    for output_name, output in declarations.items():
        if output_name in accepted and status not in output.permitted_on_statuses:
            raise _IntegrityError("runner output is forbidden on derived status")
        if output_name not in accepted and status in output.required_on_statuses:
            raise _IntegrityError("runner omitted an output required by derived status")
    return tuple(accepted[name] for name in sorted(accepted, key=utf16_sort_key))


def _helper_facade(
    context: _ValidationExecutionContext,
    phase: PhaseSpec,
    audit_receipts: list[SchemaEvaluationReceipt],
) -> _PhaseHelperFacade:
    program = context.invocation.program
    schema_by_id = {schema.schema_id: schema for schema in program.schemas}
    subject_path = _issue_subject_path(phase.phase_name)

    def charge_work_units(amount: int) -> None:
        context.ledger.charge(
            BudgetDimension.KERNEL_PHASE_WORK_UNITS,
            amount,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=subject_path,
        )

    def evaluate_bound_schema(
        schema_id: str,
        instance: JsonValue,
        instance_binding: InstanceBinding,
    ) -> _SchemaEvaluationView:
        if type(schema_id) is not str:
            raise _IntegrityError("schema helper requires an exact schema identity")
        schema = schema_by_id.get(schema_id)
        if schema is None:
            raise _IntegrityError("schema helper requested an unsealed schema")
        try:
            evaluator = program.resolve_runtime_binding(
                "schema_evaluator", schema.profile_id
            )
            receipt = evaluator(  # type: ignore[operator]
                schema,
                instance,
                instance_binding=instance_binding,
                ledger=context.ledger,
            )
        except BudgetExceeded:
            raise
        except _IntegrityError:
            raise
        except Exception as exception:
            raise _RuntimeComponentError(exception) from exception
        if type(receipt) is not SchemaEvaluationReceipt:
            raise _IntegrityError("schema evaluator returned a non-receipt")
        audit_receipts.append(receipt)
        return _SchemaEvaluationView(
            evaluation_passed=receipt.evaluation_passed,
            bounded_errors=receipt.bounded_errors,
            failure_code=receipt.failure_code,
        )

    return _PhaseHelperFacade(charge_work_units, evaluate_bound_schema)


def _validate_runner_result(result: object) -> RunnerResult:
    if type(result) is not RunnerResult:
        raise _IntegrityError("runner returned an unauthorized result shape")
    return result


def _not_evaluated_result(phase_name: str) -> PhaseResult:
    return PhaseResult(
        phase_name=phase_name,
        status="not_evaluated",
        diagnostics=(),
        compile_blockers=(),
        outputs=(),
        kernel_work_units_delta=0,
    )


def _execute_phase_program_with_audit(
    context: _ValidationExecutionContext,
) -> (
    tuple[tuple[PhaseResult, ...], _PhaseExecutionAudit]
    | ValidationControlFailure
):
    """Execute one context and retain exact adapter receipts on a private path."""

    if type(context) is not _ValidationExecutionContext:
        return _integrity_failure(None, None, "execution context is not kernel-issued")
    program = context.invocation.program
    if type(program) is not SealedValidationProgram:
        return _integrity_failure(None, None, "execution program is not sealed")
    phase_by_name = {phase.phase_name: phase for phase in program.phases}
    if (
        len(phase_by_name) != len(program.phases)
        or len(program.execution_order) != len(program.phases)
        or frozenset(program.execution_order) != frozenset(phase_by_name)
    ):
        return _integrity_failure(program, None, "sealed execution order is inconsistent")

    results: list[PhaseResult] = []
    results_by_name: dict[str, PhaseResult] = {}
    audit_receipts: list[SchemaEvaluationReceipt] = []
    for phase_name in program.execution_order:
        phase = phase_by_name[phase_name]
        try:
            bound_members: list[tuple[str, tuple[object, ...]]] = []
            unavailable = False
            for binding in phase.input_bindings:
                resolved = _resolve_binding(
                    context, phase_by_name, results_by_name, binding
                )
                if resolved is _UNAVAILABLE:
                    unavailable = True
                else:
                    bound_members.append(
                        (binding.input_name, cast(tuple[object, ...], resolved))
                    )
            if unavailable:
                phase_result = _not_evaluated_result(phase_name)
                results.append(phase_result)
                results_by_name[phase_name] = phase_result
                continue

            bound_members.sort(key=lambda item: utf16_sort_key(item[0]))
            inputs = _PhaseInputs(tuple(bound_members))
            helpers = _helper_facade(context, phase, audit_receipts)
            runner = program.resolve_runtime_binding("runner", phase.runner_id)
            before = context.ledger.snapshot()
            try:
                raw_result = runner(inputs, helpers)  # type: ignore[operator]
            except BudgetExceeded:
                raise
            except _IntegrityError:
                raise
            except _RuntimeComponentError:
                raise
            except Exception as exception:
                raise _RuntimeComponentError(exception) from exception
            after = context.ledger.snapshot()
            work_delta = (
                after.kernel_phase_work_units - before.kernel_phase_work_units
            )
            if work_delta < 0:
                raise _IntegrityError("phase work accounting moved backwards")

            runner_result = _validate_runner_result(raw_result)
            diagnostics, blockers = _validate_issues(
                context, phase, runner_result
            )
            status = _derive_status(diagnostics, blockers)
            outputs = _validate_outputs(
                program, phase, runner_result.outputs, status
            )
            phase_result = PhaseResult(
                phase_name=phase_name,
                status=status,
                diagnostics=diagnostics,
                compile_blockers=blockers,
                outputs=outputs,
                kernel_work_units_delta=work_delta,
            )
            results.append(phase_result)
            results_by_name[phase_name] = phase_result
        except BudgetExceeded as exception:
            return _budget_failure(exception, program)
        except _IntegrityError as exception:
            return _integrity_failure(program, phase_name, exception.evidence)
        except _RuntimeComponentError as exception:
            return _internal_failure(program, phase_name, exception.exception)
        except Exception as exception:
            return _internal_failure(program, phase_name, exception)

    frozen_results = tuple(results)
    audit = _make_execution_audit(program, tuple(audit_receipts))
    return frozen_results, audit


def execute_phase_program(
    context: _ValidationExecutionContext,
) -> tuple[PhaseResult, ...] | ValidationControlFailure:
    """Execute the sealed phase DAG or return one pre-publication control failure."""

    execution = _execute_phase_program_with_audit(context)
    if isinstance(execution, ValidationControlFailure):
        return execution
    return execution[0]


__all__ = (
    "KernelIssue",
    "NamedOutput",
    "PhaseResult",
    "RunnerResult",
    "execute_phase_program",
)
