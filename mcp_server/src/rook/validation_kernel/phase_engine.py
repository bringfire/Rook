"""Deterministic typed phase execution over one sealed validation program."""

from __future__ import annotations

import hashlib
import re
import struct
from collections.abc import Callable, Iterator, Mapping
from dataclasses import Field, dataclass, fields, replace
from typing import Literal, cast

from .budget import MAX_CHECKED_BUDGET_INTEGER, BudgetExceeded
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
    SchemaEvaluationInputError,
    SchemaEvaluationReceipt,
    SchemaIssue,
    _SchemaEvaluationAuditEntry,
    _is_schema_evaluation_audit_entry,
    _issue_schema_evaluation_audit_entry,
    _resolve_instance_binding,
)


PhaseStatus = Literal["passed", "blocked", "failed", "not_evaluated"]
IssueSeverity = Literal["error", "warning", "information"]
_WorkCharger = Callable[[int], None]

_ISSUE_SEVERITIES = frozenset(("error", "warning", "information"))
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_ISSUE_MESSAGE_CODE_POINTS = 512
_MAX_ISSUE_PATH_CODE_POINTS = 2_048
_EXCEPTION_PROJECTION_MAX_BYTES = 4_096
_EXCEPTION_PROJECTION_MAX_ITEMS = 128
_EXCEPTION_PROJECTION_MAX_DEPTH = 16
_EXCEPTION_PROJECTION_EDGE_UNITS = 32
_EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS = 256
_EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK = (
    1 << _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS
) - 1
_TYPE_MODULE_DESCRIPTOR = type.__dict__["__module__"]
_TYPE_QUALNAME_DESCRIPTOR = type.__dict__["__qualname__"]
_EXCEPTION_PROJECTION_FALLBACK_DIGEST = hashlib.sha256(
    b"rook.phase_exception_evidence:v2\0fallback"
).digest()
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
_DATACLASS_METADATA_INSPECTION_WORK = 3
# ``fields()`` visits and attaches each admitted field. The remaining units
# cover the field-name index plus value lookup and traversal-stack attachment.
_DATACLASS_FIELD_WORK_PER_ENTRY = 5
_DATACLASS_FIELD_FIXED_WORK = 2
_DATACLASS_SLOT_WORK_PER_ENTRY = 2
_DATACLASS_SLOT_FIXED_WORK = 3


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
class _AuditedPhaseExecution:
    public_result: tuple[PhaseResult, ...] | ValidationControlFailure
    schema_evaluation_attempts: tuple[_SchemaEvaluationAuditEntry, ...]
    schema_evaluation_receipts: tuple[SchemaEvaluationReceipt, ...]

    def __init__(self) -> None:
        raise TypeError("audited phase executions are kernel-issued")


@dataclass(frozen=True, slots=True)
class _ExceptionDetailProjection:
    digest: bytes
    projected_bytes: int
    projected_items: int
    maximum_depth: int
    truncated: bool


class _ExceptionProjectionWriter:
    __slots__ = ("_digest", "projected_bytes", "truncated")

    def __init__(self) -> None:
        self._digest = hashlib.sha256(b"rook.phase_exception_evidence:v2\0")
        self.projected_bytes = 0
        self.truncated = False

    @property
    def exhausted(self) -> bool:
        return self.projected_bytes == _EXCEPTION_PROJECTION_MAX_BYTES

    @property
    def remaining(self) -> int:
        return _EXCEPTION_PROJECTION_MAX_BYTES - self.projected_bytes

    def mark_truncated(self) -> None:
        self.truncated = True

    def write(self, data: bytes) -> None:
        remaining = _EXCEPTION_PROJECTION_MAX_BYTES - self.projected_bytes
        if len(data) > remaining:
            self._digest.update(data[:remaining])
            self.projected_bytes += remaining
            self.truncated = True
            return
        self._digest.update(data)
        self.projected_bytes += len(data)

    def finish(self, *, projected_items: int, maximum_depth: int) -> bytes:
        self._digest.update(b"\x01" if self.truncated else b"\x00")
        self._digest.update(self.projected_bytes.to_bytes(8, "big"))
        self._digest.update(projected_items.to_bytes(8, "big"))
        self._digest.update(maximum_depth.to_bytes(8, "big"))
        return self._digest.digest()


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


def _phase_work_charger(
    context: _ValidationExecutionContext, phase_name: str | None
) -> _WorkCharger:
    subject_path = None if phase_name is None else _issue_subject_path(phase_name)

    def charge_work_units(amount: int) -> None:
        context.ledger.charge(
            BudgetDimension.KERNEL_PHASE_WORK_UNITS,
            amount,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=subject_path,
        )

    return charge_work_units


def _checked_bulk_work_units(
    item_count: int, per_item: int, *, fixed: int = 0
) -> int:
    if fixed > MAX_CHECKED_BUDGET_INTEGER:
        return MAX_CHECKED_BUDGET_INTEGER
    if per_item and item_count > (
        MAX_CHECKED_BUDGET_INTEGER - fixed
    ) // per_item:
        return MAX_CHECKED_BUDGET_INTEGER
    return fixed + (item_count * per_item)


def _checked_work_sum(*amounts: int) -> int:
    total = 0
    for amount in amounts:
        if amount > MAX_CHECKED_BUDGET_INTEGER - total:
            return MAX_CHECKED_BUDGET_INTEGER
        total += amount
    return total


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


def _projection_uint(value: int) -> bytes:
    if value >= 1 << 128:
        return b"\xff" * 16
    return value.to_bytes(16, "big")


def _project_exception_string(
    writer: _ExceptionProjectionWriter, value: str
) -> None:
    length = len(value)
    if length <= _EXCEPTION_PROJECTION_EDGE_UNITS * 2:
        prefix_count = length
        suffix_count = 0
        locally_truncated = False
    else:
        prefix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        suffix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        locally_truncated = True
        writer.mark_truncated()
    writer.write(b"S")
    writer.write(_projection_uint(length))
    writer.write(prefix_count.to_bytes(2, "big"))
    writer.write(suffix_count.to_bytes(2, "big"))
    writer.write(b"\x01" if locally_truncated else b"\x00")
    for index in range(prefix_count):
        writer.write(ord(value[index]).to_bytes(4, "big"))
    for index in range(length - suffix_count, length):
        writer.write(ord(value[index]).to_bytes(4, "big"))


def _project_exception_bytes(
    writer: _ExceptionProjectionWriter, value: bytes
) -> None:
    length = len(value)
    if length <= _EXCEPTION_PROJECTION_EDGE_UNITS * 2:
        prefix_count = length
        suffix_count = 0
        locally_truncated = False
    else:
        prefix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        suffix_count = _EXCEPTION_PROJECTION_EDGE_UNITS
        locally_truncated = True
        writer.mark_truncated()
    writer.write(b"Y")
    writer.write(_projection_uint(length))
    writer.write(prefix_count.to_bytes(2, "big"))
    writer.write(suffix_count.to_bytes(2, "big"))
    writer.write(b"\x01" if locally_truncated else b"\x00")
    writer.write(value[:prefix_count])
    if suffix_count:
        writer.write(value[length - suffix_count :])


def _project_type_identity(
    writer: _ExceptionProjectionWriter, value_type: type[object]
) -> None:
    for marker, descriptor in (
        (b"M", _TYPE_MODULE_DESCRIPTOR),
        (b"Q", _TYPE_QUALNAME_DESCRIPTOR),
    ):
        writer.write(marker)
        try:
            component = descriptor.__get__(value_type, type)
        except BaseException:
            component = None
        if type(component) is str:
            _project_exception_string(writer, component)
        else:
            writer.write(b"?")


def _project_exception_integer(
    writer: _ExceptionProjectionWriter, value: int
) -> None:
    negative = value < 0
    sign = b"\x01" if negative else b"\x00"
    bit_length = value.bit_length()
    magnitude_length = max(1, (bit_length + 7) // 8)
    length_record = _projection_uint(magnitude_length)
    full_header = b"I" + sign + b"F" + length_record
    if len(full_header) + magnitude_length <= writer.remaining:
        magnitude = -value if negative else value
        writer.write(full_header)
        writer.write(magnitude.to_bytes(magnitude_length, "big"))
        return

    writer.mark_truncated()
    if negative:
        high_window = _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
        low_window = _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
    else:
        high_shift = max(
            bit_length - _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS,
            0,
        )
        high_window = (
            value >> high_shift
        ) & _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
        low_window = value & _EXCEPTION_PROJECTION_INTEGER_SAMPLE_MASK
    sample_bytes = _EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS // 8
    writer.write(b"I" + sign + b"T")
    writer.write(_projection_uint(bit_length))
    writer.write(length_record)
    writer.write(_EXCEPTION_PROJECTION_INTEGER_SAMPLE_BITS.to_bytes(2, "big"))
    writer.write(high_window.to_bytes(sample_bytes, "big"))
    writer.write(low_window.to_bytes(sample_bytes, "big"))


def _project_exception_scalar(
    writer: _ExceptionProjectionWriter, value: object
) -> None:
    value_type = type(value)
    if value is None:
        writer.write(b"N")
    elif value_type is bool:
        writer.write(b"B\x01" if value else b"B\x00")
    elif value_type is int:
        _project_exception_integer(writer, value)
    elif value_type is float:
        writer.write(b"F")
        writer.write(struct.pack(">d", value))
    elif value_type is str:
        _project_exception_string(writer, value)
    elif value_type is bytes:
        _project_exception_bytes(writer, value)
    else:
        writer.write(b"U")
        _project_type_identity(writer, value_type)


def _build_exception_detail_projection(
    exception: BaseException,
) -> _ExceptionDetailProjection:
    writer = _ExceptionProjectionWriter()
    writer.write(b"E")
    _project_type_identity(writer, type(exception))
    writer.write(b"A")
    try:
        arguments = BaseException.args.__get__(exception, BaseException)
    except BaseException:
        arguments = ()
        writer.mark_truncated()

    stack: list[tuple[object, int]] = [(arguments, 0)]
    projected_items = 0
    maximum_depth = 0
    while stack and not writer.exhausted:
        if projected_items == _EXCEPTION_PROJECTION_MAX_ITEMS:
            writer.mark_truncated()
            break
        value, depth = stack.pop()
        projected_items += 1
        maximum_depth = max(maximum_depth, depth)

        if type(value) is not tuple:
            _project_exception_scalar(writer, value)
            continue

        length = len(value)
        if depth >= _EXCEPTION_PROJECTION_MAX_DEPTH:
            child_count = 0
            depth_limited = bool(length)
        else:
            available_items = (
                _EXCEPTION_PROJECTION_MAX_ITEMS - projected_items - len(stack)
            )
            child_count = min(length, max(available_items, 0))
            depth_limited = False
        children_truncated = child_count < length
        if children_truncated:
            writer.mark_truncated()
        writer.write(b"T")
        writer.write(_projection_uint(length))
        writer.write(child_count.to_bytes(2, "big"))
        writer.write(b"\x01" if depth_limited else b"\x00")
        writer.write(b"\x01" if children_truncated else b"\x00")
        for index in range(child_count - 1, -1, -1):
            stack.append((value[index], depth + 1))

    if stack:
        writer.mark_truncated()
    digest = writer.finish(
        projected_items=projected_items,
        maximum_depth=maximum_depth,
    )
    return _ExceptionDetailProjection(
        digest=digest,
        projected_bytes=writer.projected_bytes,
        projected_items=projected_items,
        maximum_depth=maximum_depth,
        truncated=writer.truncated,
    )


def _exception_detail_projection(
    exception: BaseException,
) -> _ExceptionDetailProjection:
    try:
        return _build_exception_detail_projection(exception)
    except BaseException:
        return _ExceptionDetailProjection(
            digest=_EXCEPTION_PROJECTION_FALLBACK_DIGEST,
            projected_bytes=0,
            projected_items=0,
            maximum_depth=0,
            truncated=True,
        )


def _bounded_exception_evidence(exception: BaseException) -> bytes:
    return _exception_detail_projection(exception).digest


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


def _audited_phase_execution(
    public_result: tuple[PhaseResult, ...] | ValidationControlFailure,
    attempts: tuple[_SchemaEvaluationAuditEntry, ...],
) -> _AuditedPhaseExecution:
    if type(attempts) is not tuple or any(
        not _is_schema_evaluation_audit_entry(attempt) for attempt in attempts
    ):
        raise TypeError("audited phase execution requires exact audit entries")
    receipts = tuple(attempt.receipt for attempt in attempts)
    outcome = object.__new__(_AuditedPhaseExecution)
    object.__setattr__(outcome, "public_result", public_result)
    object.__setattr__(outcome, "schema_evaluation_attempts", attempts)
    object.__setattr__(outcome, "schema_evaluation_receipts", receipts)
    return outcome


def _has_only_dataclass_slots(
    value_type: type[object],
    field_definitions: tuple[Field[object], ...],
    charge_work_units: _WorkCharger,
) -> bool:
    dataclass_names: set[str] = set()
    for field_definition in field_definitions:
        dataclass_names.add(field_definition.name)

    mro = type.__getattribute__(value_type, "__mro__")
    charge_work_units(len(mro))
    slot_count = 0
    for base in mro:
        slots = type.__getattribute__(base, "__dict__").get("__slots__", ())
        if type(slots) is str:
            count = 1
        elif type(slots) is tuple:
            count = len(slots)
        else:
            return False
        if count > MAX_CHECKED_BUDGET_INTEGER - slot_count:
            slot_count = MAX_CHECKED_BUDGET_INTEGER
            break
        slot_count += count

    charge_work_units(
        _checked_bulk_work_units(
            slot_count,
            _DATACLASS_SLOT_WORK_PER_ENTRY,
            fixed=_DATACLASS_SLOT_FIXED_WORK,
        )
    )
    slot_names: set[str] = set()
    for base in mro:
        slots = type.__getattribute__(base, "__dict__").get("__slots__", ())
        if type(slots) is str:
            slot_names.add(slots)
        else:
            for slot in cast(tuple[str, ...], slots):
                slot_names.add(slot)
    slot_names.discard("__weakref__")
    return slot_names == dataclass_names


def _is_transitively_immutable(
    root: object, charge_work_units: _WorkCharger
) -> bool:
    charge_work_units(3)
    stack = [root]
    seen: dict[int, None] = {}
    while stack:
        charge_work_units(1)
        value = stack.pop()
        value_type = type(value)
        if value_type is JsonArray:
            charge_work_units(1)
            identity = id(value)
            if identity in seen:
                continue
            charge_work_units(1)
            seen[identity] = None
            index = len(value.items)
            while index:
                index -= 1
                charge_work_units(2)
                stack.append(value.items[index])
            continue
        if value_type is JsonObject:
            charge_work_units(1)
            identity = id(value)
            if identity in seen:
                continue
            charge_work_units(1)
            seen[identity] = None
            index = len(value.members)
            while index:
                index -= 1
                charge_work_units(2)
                stack.append(value.members[index][1])
            continue
        if value_type in _OWNED_VALUE_TYPES or value_type in _SCALAR_IMMUTABLE_TYPES:
            continue
        identity = id(value)
        charge_work_units(1)
        if identity in seen:
            continue
        charge_work_units(1)
        seen[identity] = None
        if value_type is tuple:
            index = len(value)
            while index:
                index -= 1
                charge_work_units(2)
                stack.append(value[index])
            continue
        if isinstance(value, type):
            return False
        charge_work_units(_DATACLASS_METADATA_INSPECTION_WORK)
        try:
            field_metadata = type.__getattribute__(
                value_type, "__dataclass_fields__"
            )
            parameters = type.__getattribute__(
                value_type, "__dataclass_params__"
            )
        except AttributeError:
            return False
        try:
            object.__getattribute__(value, "__dict__")
        except AttributeError:
            has_instance_dict = False
        else:
            has_instance_dict = True
        if (
            type(field_metadata) is not dict
            or parameters.frozen is not True
            or has_instance_dict
        ):
            return False
        admitted_field_count = len(field_metadata)
        charge_work_units(
            _checked_bulk_work_units(
                admitted_field_count,
                _DATACLASS_FIELD_WORK_PER_ENTRY,
                fixed=_DATACLASS_FIELD_FIXED_WORK,
            )
        )
        field_definitions = fields(value_type)
        if len(field_definitions) > admitted_field_count:
            return False
        if not _has_only_dataclass_slots(
            value_type, field_definitions, charge_work_units
        ):
            return False
        index = len(field_definitions)
        while index:
            index -= 1
            field_definition = field_definitions[index]
            stack.append(object.__getattribute__(value, field_definition.name))
    return True


def _cardinality_is_valid(cardinality: Cardinality, count: int) -> bool:
    if cardinality == "exactly_one":
        return count == 1
    if cardinality == "zero_or_one":
        return count <= 1
    return cardinality == "many"


def _owned_source_values(
    value: JsonValue,
    cardinality: Cardinality,
    charge_work_units: _WorkCharger,
) -> tuple[object, ...]:
    if cardinality == "exactly_one":
        charge_work_units(2)
        return (value,)
    if cardinality == "zero_or_one":
        if type(value) is JsonNull:
            return ()
        charge_work_units(2)
        return (value,)
    if cardinality == "many":
        if type(value) is not JsonArray:
            raise _IntegrityError("many-valued owned input is not an owned array")
        return cast(tuple[object, ...], value.items)
    raise _IntegrityError("input cardinality is not closed")


def _value_matches_type(
    program: SealedValidationProgram,
    expected_type: str,
    value: object,
    *,
    require_export_validator: bool = False,
    charge_work_units: _WorkCharger,
) -> bool:
    charge_work_units(1)
    builtin_types = _BUILTIN_TYPE_IDS.get(expected_type)
    if builtin_types is not None and type(value) not in builtin_types:
        return False
    if builtin_types is not None and not require_export_validator:
        return True
    charge_work_units(1)
    if ("export_type", expected_type) not in program.runtime_binding_keys:
        raise _IntegrityError("bound input type has no sealed validator")
    charge_work_units(1)
    validator = program.resolve_runtime_binding("export_type", expected_type)
    try:
        charge_work_units(1)
        accepted = validator(value)  # type: ignore[operator]
    except Exception as exception:
        if require_export_validator:
            raise _IntegrityError("sealed export validator raised") from None
        raise _RuntimeComponentError(exception) from exception
    if type(accepted) is not bool:
        raise _IntegrityError("export validator returned a non-boolean result")
    return accepted


def _provided_output(
    phase: PhaseSpec, output_name: str, charge_work_units: _WorkCharger
) -> ProvidedOutput | None:
    for output in phase.provided_outputs:
        charge_work_units(1)
        if output.output_name == output_name:
            return output
    return None


def _resolve_binding(
    context: _ValidationExecutionContext,
    phase_by_name: Mapping[str, PhaseSpec],
    results_by_name: Mapping[str, PhaseResult],
    binding: InputBinding,
    charge_work_units: _WorkCharger,
) -> tuple[object, ...] | object:
    program = context.invocation.program
    if binding.source_kind == "invocation_input":
        source_name = cast(str, binding.source_input)
        try:
            charge_work_units(1)
            source = context.invocation.invocation_inputs[source_name]
        except KeyError as exception:
            raise _IntegrityError("captured invocation input is missing") from exception
        values = _owned_source_values(
            source, binding.cardinality, charge_work_units
        )
    elif binding.source_kind == "program_constant":
        source_name = cast(str, binding.source_constant)
        try:
            charge_work_units(1)
            source = program.resolve_program_constant(source_name)
        except KeyError as exception:
            raise _IntegrityError("sealed program constant is missing") from exception
        values = _owned_source_values(
            source, binding.cardinality, charge_work_units
        )
    elif binding.source_kind == "phase_output":
        source_phase_name = cast(str, binding.source_phase)
        source_output_name = cast(str, binding.source_output)
        charge_work_units(1)
        source_phase = phase_by_name.get(source_phase_name)
        charge_work_units(1)
        provider = results_by_name.get(source_phase_name)
        if source_phase is None or provider is None:
            raise _IntegrityError("bound producer has no prior result")
        if provider.status in ("failed", "not_evaluated"):
            return _UNAVAILABLE
        output_spec = _provided_output(
            source_phase, source_output_name, charge_work_units
        )
        if output_spec is None:
            raise _IntegrityError("bound producer output declaration is missing")
        named = None
        for output in provider.outputs:
            charge_work_units(1)
            if output.output_name == source_output_name:
                named = output
                break
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
        if binding.cardinality == "many":
            charge_work_units(1)
        if not _is_transitively_immutable(value, charge_work_units):
            raise _IntegrityError("bound input is not transitively immutable")
        if not _value_matches_type(
            program,
            binding.expected_type,
            value,
            charge_work_units=charge_work_units,
        ):
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
    charge_work_units: _WorkCharger,
) -> KernelIssue:
    charge_work_units(1)
    if type(issue) is not KernelIssue:
        raise _IntegrityError("runner issue is not an exact KernelIssue")
    if type(issue.classification) is not str or type(issue.code) is not str:
        raise _IntegrityError("runner issue identity fields are not exact strings")
    if issue.classification != classification:
        raise _IntegrityError("runner issue classification is wrong")
    charge_work_units(1)
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
    for path in issue.related_paths:
        charge_work_units(1)
        if not _bounded_scalar_string(path, _MAX_ISSUE_PATH_CODE_POINTS) or not _valid_pointer(
            path
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
    charge_work_units: _WorkCharger,
) -> tuple[tuple[KernelIssue, ...], tuple[KernelIssue, ...]]:
    if type(result.diagnostics) is not tuple:
        raise _IntegrityError("diagnostics collection is not an exact tuple")
    if type(result.compile_blockers) is not tuple:
        raise _IntegrityError("compile blocker collection is not an exact tuple")
    subject_path = _issue_subject_path(phase.phase_name)
    charge_work_units(2)
    diagnostics: list[KernelIssue] = []
    seen_diagnostics: dict[KernelIssue, None] = {}
    for issue in result.diagnostics:
        context.ledger.charge(
            BudgetDimension.DIAGNOSTICS,
            1,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=subject_path,
        )
        validated = _validate_issue(
            issue,
            classification="diagnostic",
            permitted_codes=phase.permitted_diagnostic_codes,
            charge_work_units=charge_work_units,
        )
        charge_work_units(1)
        if validated in seen_diagnostics:
            raise _IntegrityError("runner returned a duplicate diagnostic")
        charge_work_units(1)
        seen_diagnostics[validated] = None
        charge_work_units(1)
        diagnostics.append(validated)
    charge_work_units(2)
    blockers: list[KernelIssue] = []
    seen_blockers: dict[KernelIssue, None] = {}
    for issue in result.compile_blockers:
        context.ledger.charge(
            BudgetDimension.COMPILE_BLOCKERS,
            1,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=subject_path,
        )
        validated = _validate_issue(
            issue,
            classification="compile_blocker",
            permitted_codes=phase.permitted_blocker_codes,
            charge_work_units=charge_work_units,
        )
        charge_work_units(1)
        if validated in seen_blockers:
            raise _IntegrityError("runner returned a duplicate compile blocker")
        charge_work_units(1)
        seen_blockers[validated] = None
        charge_work_units(1)
        blockers.append(validated)
    charge_work_units(len(diagnostics) + len(blockers) + 2)
    return tuple(diagnostics), tuple(blockers)


def _derive_status(
    diagnostics: tuple[KernelIssue, ...],
    blockers: tuple[KernelIssue, ...],
    charge_work_units: _WorkCharger,
) -> Literal["passed", "blocked", "failed"]:
    for issue in diagnostics:
        charge_work_units(1)
        if issue.severity == "error":
            return "failed"
    charge_work_units(1)
    if blockers:
        return "blocked"
    return "passed"


def _validate_outputs(
    program: SealedValidationProgram,
    phase: PhaseSpec,
    raw_outputs: object,
    status: Literal["passed", "blocked", "failed"],
    charge_work_units: _WorkCharger,
) -> tuple[NamedOutput, ...]:
    if type(raw_outputs) is not tuple:
        raise _IntegrityError("runner outputs are not an exact tuple")
    charge_work_units(
        _checked_bulk_work_units(
            len(phase.provided_outputs), 2, fixed=1
        )
    )
    declarations: dict[str, ProvidedOutput] = {}
    for output in phase.provided_outputs:
        declarations[output.output_name] = output
    charge_work_units(1)
    accepted: dict[str, NamedOutput] = {}
    for raw_output in raw_outputs:
        charge_work_units(1)
        if type(raw_output) is not NamedOutput:
            raise _IntegrityError("runner output is not an exact NamedOutput")
        if type(raw_output.output_name) is not str:
            raise _IntegrityError("runner output name is not an exact string")
        charge_work_units(1)
        if raw_output.output_name in accepted:
            raise _IntegrityError("runner returned a duplicate output")
        charge_work_units(1)
        declaration = declarations.get(raw_output.output_name)
        if declaration is None:
            raise _IntegrityError("runner returned an undeclared output")
        if type(raw_output.values) is not tuple:
            raise _IntegrityError("runner output values are not an exact tuple")
        if not _cardinality_is_valid(declaration.cardinality, len(raw_output.values)):
            raise _IntegrityError("runner output cardinality is wrong")
        for value in raw_output.values:
            if declaration.cardinality == "many":
                charge_work_units(1)
            if not _is_transitively_immutable(value, charge_work_units):
                raise _IntegrityError("runner output is not transitively immutable")
            if not _value_matches_type(
                program,
                declaration.output_type,
                value,
                require_export_validator=True,
                charge_work_units=charge_work_units,
            ):
                raise _IntegrityError("runner output has the wrong sealed type")
        charge_work_units(1)
        accepted[raw_output.output_name] = raw_output

    for output_name, output in declarations.items():
        charge_work_units(1)
        charge_work_units(1)
        if output_name in accepted and status not in output.permitted_on_statuses:
            raise _IntegrityError("runner output is forbidden on derived status")
        charge_work_units(1)
        if output_name not in accepted and status in output.required_on_statuses:
            raise _IntegrityError("runner omitted an output required by derived status")
    charge_work_units(len(accepted) + 1)
    output_names = tuple(accepted)
    sort_units = 0
    if output_names:
        sort_units = _checked_bulk_work_units(
            len(output_names),
            (max(2, len(output_names)) - 1).bit_length(),
        )
    charge_work_units(
        _checked_work_sum(
            sort_units,
            _checked_bulk_work_units(len(output_names), 1, fixed=2),
        )
    )
    sorted_names = sorted(output_names, key=utf16_sort_key)
    ordered: list[NamedOutput] = []
    for name in sorted_names:
        charge_work_units(2)
        ordered.append(accepted[name])
    charge_work_units(len(ordered) + 1)
    return tuple(ordered)


def _helper_facade(
    context: _ValidationExecutionContext,
    phase: PhaseSpec,
    audit_attempts: list[_SchemaEvaluationAuditEntry],
    charge_work_units: _WorkCharger,
) -> _PhaseHelperFacade:
    program = context.invocation.program
    charge_work_units(
        _checked_bulk_work_units(len(program.schemas), 2, fixed=1)
    )
    schema_by_id = {}
    for schema in program.schemas:
        schema_by_id[schema.schema_id] = schema
    profile_by_id = {
        evaluator_spec.profile.profile_id: evaluator_spec.profile
        for evaluator_spec in program.schema_evaluator_profiles
    }

    def evaluate_bound_schema(
        schema_id: str,
        instance: JsonValue,
        instance_binding: InstanceBinding,
    ) -> _SchemaEvaluationView:
        if type(schema_id) is not str:
            raise _IntegrityError("schema helper requires an exact schema identity")
        charge_work_units(1)
        schema = schema_by_id.get(schema_id)
        if schema is None:
            raise _IntegrityError("schema helper requested an unsealed schema")
        profile = profile_by_id.get(schema.profile_id)
        if profile is None:
            raise _IntegrityError("schema helper profile is not sealed")
        charge_work_units(2)
        invocation = context.invocation
        sources = (
            (invocation.recipe_value, invocation.recipe_value_fingerprint),
            (
                invocation.validation_bundle,
                invocation.validation_bundle_fingerprint,
            ),
        )
        resolved_instance = None
        for source_root, source_fingerprint in sources:
            if (
                source_root is None
                or source_fingerprint
                != instance_binding.artifact_fingerprint
            ):
                continue
            try:
                resolved_instance = _resolve_instance_binding(
                    instance_root=source_root,
                    instance_root_fingerprint=source_fingerprint,
                    instance=instance,
                    instance_binding=instance_binding,
                    charge_work_units=charge_work_units,
                )
            except SchemaEvaluationInputError:
                continue
            break
        if resolved_instance is None:
            raise _IntegrityError(
                "schema helper instance binding does not select a captured source"
            )
        try:
            charge_work_units(1)
            evaluator = program.resolve_runtime_binding(
                "schema_evaluator", schema.profile_id
            )
            charge_work_units(5)
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
        try:
            audit_attempts.append(
                _issue_schema_evaluation_audit_entry(
                    schema=schema,
                    instance=instance,
                    resolved_instance_binding=resolved_instance,
                    receipt=receipt,
                    per_evaluation_limit=profile.per_evaluation_shape_limit,
                    ledger=context.ledger,
                )
            )
        except SchemaEvaluationInputError as exception:
            raise _IntegrityError(
                "schema evaluator returned mismatched audit evidence"
            ) from exception
        return _SchemaEvaluationView(
            evaluation_passed=receipt.evaluation_passed,
            bounded_errors=receipt.bounded_errors,
            failure_code=receipt.failure_code,
        )

    charge_work_units(3)
    return _PhaseHelperFacade(charge_work_units, evaluate_bound_schema)


def _validate_runner_result(
    result: object, charge_work_units: _WorkCharger
) -> RunnerResult:
    charge_work_units(1)
    if type(result) is not RunnerResult:
        raise _IntegrityError("runner returned an unauthorized result shape")
    return result


def _not_evaluated_result(
    phase_name: str, charge_work_units: _WorkCharger
) -> PhaseResult:
    charge_work_units(7)
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
) -> _AuditedPhaseExecution:
    """Execute one context and retain exact adapter receipts on a private path."""

    if type(context) is not _ValidationExecutionContext:
        return _audited_phase_execution(
            _integrity_failure(None, None, "execution context is not kernel-issued"),
            (),
        )
    program = context.invocation.program
    if type(program) is not SealedValidationProgram:
        return _audited_phase_execution(
            _integrity_failure(None, None, "execution program is not sealed"),
            (),
        )
    engine_charge_work_units = _phase_work_charger(context, None)
    phase_count = len(program.phases)
    execution_count = len(program.execution_order)
    try:
        engine_charge_work_units(
            _checked_work_sum(
                _checked_bulk_work_units(phase_count, 2, fixed=1),
                _checked_bulk_work_units(execution_count, 2, fixed=1),
                _checked_bulk_work_units(phase_count, 2, fixed=1),
            )
        )
    except BudgetExceeded as exception:
        return _audited_phase_execution(_budget_failure(exception, program), ())
    phase_by_name = {
        phase.phase_name: phase for phase in program.phases
    }
    execution_names = frozenset(program.execution_order)
    declared_names = frozenset(phase_by_name)
    if (
        len(phase_by_name) != phase_count
        or execution_count != phase_count
        or execution_names != declared_names
    ):
        return _audited_phase_execution(
            _integrity_failure(
                program, None, "sealed execution order is inconsistent"
            ),
            (),
        )

    try:
        engine_charge_work_units(3)
    except BudgetExceeded as exception:
        return _audited_phase_execution(_budget_failure(exception, program), ())
    results: list[PhaseResult] = []
    results_by_name: dict[str, PhaseResult] = {}
    audit_attempts: list[_SchemaEvaluationAuditEntry] = []
    for phase_name in program.execution_order:
        charge_work_units = _phase_work_charger(context, phase_name)
        try:
            charge_work_units(1)
            phase = phase_by_name[phase_name]
            charge_work_units(1)
            bound_members: list[tuple[str, tuple[object, ...]]] = []
            unavailable = False
            for binding in phase.input_bindings:
                charge_work_units(1)
                resolved = _resolve_binding(
                    context,
                    phase_by_name,
                    results_by_name,
                    binding,
                    charge_work_units,
                )
                if resolved is _UNAVAILABLE:
                    unavailable = True
                else:
                    charge_work_units(4)
                    bound_members.append(
                        (binding.input_name, cast(tuple[object, ...], resolved))
                    )
            if unavailable:
                phase_result = _not_evaluated_result(
                    phase_name, charge_work_units
                )
                charge_work_units(2)
                results.append(phase_result)
                results_by_name[phase_name] = phase_result
                continue

            if bound_members:
                sort_units = _checked_bulk_work_units(
                    len(bound_members),
                    (max(2, len(bound_members)) - 1).bit_length(),
                )
                charge_work_units(sort_units)
            bound_members.sort(key=lambda item: utf16_sort_key(item[0]))
            charge_work_units(
                _checked_bulk_work_units(len(bound_members), 1, fixed=2)
            )
            inputs = _PhaseInputs(tuple(bound_members))
            helpers = _helper_facade(
                context, phase, audit_attempts, charge_work_units
            )
            charge_work_units(1)
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

            runner_result = _validate_runner_result(raw_result, charge_work_units)
            diagnostics, blockers = _validate_issues(
                context, phase, runner_result, charge_work_units
            )
            status = _derive_status(
                diagnostics, blockers, charge_work_units
            )
            outputs = _validate_outputs(
                program,
                phase,
                runner_result.outputs,
                status,
                charge_work_units,
            )
            charge_work_units(7)
            phase_result = PhaseResult(
                phase_name=phase_name,
                status=status,
                diagnostics=diagnostics,
                compile_blockers=blockers,
                outputs=outputs,
                kernel_work_units_delta=work_delta,
            )
            charge_work_units(2)
            results.append(phase_result)
            results_by_name[phase_name] = phase_result
        except BudgetExceeded as exception:
            return _audited_phase_execution(
                _budget_failure(exception, program), tuple(audit_attempts)
            )
        except _IntegrityError as exception:
            return _audited_phase_execution(
                _integrity_failure(program, phase_name, exception.evidence),
                tuple(audit_attempts),
            )
        except _RuntimeComponentError as exception:
            return _audited_phase_execution(
                _internal_failure(program, phase_name, exception.exception),
                tuple(audit_attempts),
            )
        except Exception as exception:
            return _audited_phase_execution(
                _internal_failure(program, phase_name, exception),
                tuple(audit_attempts),
            )

    try:
        engine_charge_work_units(
            _checked_work_sum(
                _checked_bulk_work_units(len(results), 1, fixed=1),
                _checked_bulk_work_units(
                    len(audit_attempts), 1, fixed=1
                ),
                7,
            )
        )
        frozen_results = tuple(results)
        frozen_attempts = tuple(audit_attempts)
        execution = _audited_phase_execution(frozen_results, frozen_attempts)
    except BudgetExceeded as exception:
        return _audited_phase_execution(
            _budget_failure(exception, program), tuple(audit_attempts)
        )
    return execution


def execute_phase_program(
    context: _ValidationExecutionContext,
) -> tuple[PhaseResult, ...] | ValidationControlFailure:
    """Execute the sealed phase DAG or return one pre-publication control failure."""

    return _execute_phase_program_with_audit(context).public_result


__all__ = (
    "KernelIssue",
    "NamedOutput",
    "PhaseResult",
    "RunnerResult",
    "execute_phase_program",
)
