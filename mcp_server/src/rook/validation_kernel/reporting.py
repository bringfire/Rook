"""Deterministic report projection and non-circular publication seal."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

from .budget import (
    BudgetExceeded,
    BudgetLedger,
    BudgetLedgerFrozen,
    BudgetReceipt,
    BudgetSnapshot,
    LM9A_BUDGET_MANIFEST,
    SealMeter,
    _SealMeterExceeded,
)
from .canonical_json import (
    CanonicalJsonSizeError,
    canonical_json_bytes,
    sha256_prefixed,
)
from .control import (
    ArtifactRole,
    BudgetDimension,
    BudgetExceededFailure,
    FailureStage,
    ValidationControlFailure,
    control_failure_from_exception,
    make_control_failure,
)
from .invocation import ValidationInvocation, _ValidationExecutionContext
from .kernel_schemas import (
    BUDGET_RECEIPT_NESTED_FIELD_COUNT,
    FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT,
)
from .owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
    count_json_nodes,
    lookup_json_pointer,
)
from .phase_contract import PhaseSpec, ReportProjectionSpec
from .phase_engine import PhaseResult
from .program import (
    SealedValidationProgram,
    _host_json,
    _resolve_schema_reference,
)
from .schema_profile import (
    AdmittedSchema,
    InstanceBinding,
    SchemaEvaluationInputError,
    SchemaEvaluationReservation,
    SchemaEvaluationReceipt,
    _rejected_schema_evaluation_receipt,
    evaluate_schema_with_reservation,
    reserve_schema_evaluation,
)


_FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OWNED_VALUE_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)
_SNAPSHOT_FIELDS = (
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
_BUILDER_TOKEN = object()


class _ProjectionIntegrityError(RuntimeError):
    def __init__(self, subject_path: str | None = None) -> None:
        self.subject_path = subject_path
        super().__init__("report projection violated its sealed contract")


class _ReportConstructabilityError(RuntimeError):
    def __init__(self, subject_path: str | None = None) -> None:
        self.subject_path = subject_path
        super().__init__("projected report does not match its sealed schema")


@dataclass(frozen=True, slots=True)
class ReportProjectionEnvelope:
    program_id: str
    program_fingerprint: str
    invocation_evidence: JsonObject
    phase_specs: tuple[PhaseSpec, ...]
    phase_results: tuple[PhaseResult, ...]

    def __post_init__(self) -> None:
        if type(self.program_id) is not str or not self.program_id:
            raise TypeError("report envelope requires an exact program ID")
        if (
            type(self.program_fingerprint) is not str
            or not _FINGERPRINT_RE.fullmatch(self.program_fingerprint)
        ):
            raise TypeError("report envelope requires an exact program fingerprint")
        if type(self.invocation_evidence) is not JsonObject:
            raise TypeError("report envelope requires exact owned invocation evidence")
        if type(self.phase_specs) is not tuple or any(
            type(spec) is not PhaseSpec for spec in self.phase_specs
        ):
            raise TypeError("report envelope requires an exact phase-spec tuple")
        if type(self.phase_results) is not tuple or any(
            type(result) is not PhaseResult for result in self.phase_results
        ):
            raise TypeError("report envelope requires an exact phase-result tuple")


@dataclass(frozen=True, slots=True)
class PublishedValidationReport:
    schema_id: str
    report_fingerprint: str
    canonical_bytes: bytes
    value: JsonObject

    def __post_init__(self) -> None:
        if type(self.schema_id) is not str or not self.schema_id:
            raise TypeError("published report requires an exact schema ID")
        if (
            type(self.report_fingerprint) is not str
            or not _FINGERPRINT_RE.fullmatch(self.report_fingerprint)
        ):
            raise TypeError("published report requires an exact report fingerprint")
        if type(self.canonical_bytes) is not bytes:
            raise TypeError("published report requires exact canonical bytes")
        if type(self.value) is not JsonObject:
            raise TypeError("published report requires an exact owned object")


@dataclass(frozen=True, slots=True, init=False, eq=False)
class _AuditedReportSeal:
    public_result: PublishedValidationReport | ValidationControlFailure
    schema_evaluation_receipts: tuple[SchemaEvaluationReceipt, ...]

    def __init__(self) -> None:
        raise TypeError("audited report seals are kernel-issued")


def _audited_report_seal(
    public_result: PublishedValidationReport | ValidationControlFailure,
    receipts: tuple[SchemaEvaluationReceipt, ...],
) -> _AuditedReportSeal:
    outcome = object.__new__(_AuditedReportSeal)
    object.__setattr__(outcome, "public_result", public_result)
    object.__setattr__(outcome, "schema_evaluation_receipts", receipts)
    return outcome


@dataclass(slots=True)
class _ObjectNode:
    members: dict[str, "_BuilderNode"]


@dataclass(slots=True)
class _ArrayNode:
    items: list["_BuilderNode"]


_BuilderNode = JsonValue | _ObjectNode | _ArrayNode


@dataclass(slots=True)
class _BuilderState:
    schema: AdmittedSchema
    declaration: ReportProjectionSpec
    ledger: BudgetLedger
    root: _ObjectNode
    finished: bool = False


def _decode_pointer_token(token: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 == len(token) or token[index + 1] not in ("0", "1"):
            raise _ProjectionIntegrityError()
        decoded.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def _pointer_tokens(path: object) -> tuple[str, ...]:
    if type(path) is not str or not path.startswith("/"):
        raise _ProjectionIntegrityError()
    if path == "/":
        return ("",)
    return tuple(_decode_pointer_token(token) for token in path[1:].split("/"))


def _encode_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _child_pointer(path: str, token: str) -> str:
    return f"{path}/{_encode_pointer_token(token)}" if path else f"/{_encode_pointer_token(token)}"


def _is_projection_writable(path: str, declaration: ReportProjectionSpec) -> bool:
    if any(
        path == kernel_path
        or path.startswith(kernel_path + "/")
        or kernel_path.startswith(path + "/")
        for kernel_path in declaration.kernel_owned_paths
    ):
        return False
    return any(
        path == writable_path or path.startswith(writable_path + "/")
        for writable_path in declaration.writable_body_paths
    )


def _attachment_count(value: JsonValue) -> int:
    count = 1
    stack: list[JsonValue] = [value]
    while stack:
        current = stack.pop()
        if type(current) is JsonObject:
            count += len(current.members)
            stack.extend(member for _, member in current.members)
        elif type(current) is JsonArray:
            count += len(current.items)
            stack.extend(current.items)
    return count


def _to_builder_node(value: JsonValue) -> _BuilderNode:
    if type(value) is JsonObject:
        return _ObjectNode(
            {key.value: _to_builder_node(member) for key, member in value.members}
        )
    if type(value) is JsonArray:
        return _ArrayNode([_to_builder_node(item) for item in value.items])
    return value


def _freeze_builder_node(node: _BuilderNode) -> JsonValue:
    if type(node) is _ObjectNode:
        return JsonObject(
            tuple(
                (JsonString(name), _freeze_builder_node(member))
                for name, member in node.members.items()
            )
        )
    if type(node) is _ArrayNode:
        return JsonArray(tuple(_freeze_builder_node(item) for item in node.items))
    return cast(JsonValue, node)


def _schema_types(schema_node: dict[str, object]) -> tuple[str, ...] | None:
    declared = schema_node.get("type")
    if type(declared) is str:
        return (declared,)
    if type(declared) is list and all(type(item) is str for item in declared):
        return tuple(cast(list[str], declared))
    return None


def _value_schema_type(value: JsonValue) -> str:
    if type(value) is JsonNull:
        return "null"
    if type(value) is JsonBoolean:
        return "boolean"
    if type(value) is JsonString:
        return "string"
    if type(value) is JsonNumber:
        return "integer" if value.value.is_integer() else "number"
    if type(value) is JsonArray:
        return "array"
    return "object"


def _matches_schema_type(value: JsonValue, schema_node: dict[str, object]) -> bool:
    declared = _schema_types(schema_node)
    if declared is None:
        return True
    actual = _value_schema_type(value)
    return actual in declared or (actual == "integer" and "number" in declared)


def _schema_node_for_path(schema: AdmittedSchema, path: str) -> dict[str, object]:
    root = _host_json(schema.value)
    current: object = root
    seen_references: set[str] = set()
    raw_tokens = () if path == "" else tuple(path.split("/")[1:])
    for raw_token in raw_tokens:
        current, error = _resolve_schema_reference(
            root, current, seen_references
        )
        if error is not None or type(current) is not dict:
            raise _ProjectionIntegrityError(path)
        token = _decode_pointer_token(raw_token)
        declared = current.get("type")
        declared_types = (
            (declared,)
            if type(declared) is str
            else tuple(declared)
            if type(declared) is list
            and all(type(item) is str for item in declared)
            else ()
        )
        if "object" in declared_types:
            properties = current.get("properties")
            if (
                type(properties) is not dict
                or current.get("additionalProperties") is not False
                or token not in properties
            ):
                raise _ProjectionIntegrityError(path)
            current = properties[token]
            continue
        if "array" in declared_types:
            if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                raise _ProjectionIntegrityError(path)
            index = int(token)
            prefix_items = current.get("prefixItems")
            if type(prefix_items) is list and index < len(prefix_items):
                current = prefix_items[index]
                continue
            items = current.get("items")
            if type(items) is not dict:
                raise _ProjectionIntegrityError(path)
            current = items
            continue
        raise _ProjectionIntegrityError(path)
    current, error = _resolve_schema_reference(root, current, seen_references)
    if error is not None or type(current) is not dict:
        raise _ProjectionIntegrityError(path)
    return current


def _node_at(root: _BuilderNode, tokens: tuple[str, ...]) -> _BuilderNode:
    current = root
    for token in tokens:
        if type(current) is _ObjectNode:
            try:
                current = current.members[token]
            except KeyError:
                raise _ProjectionIntegrityError() from None
            continue
        if type(current) is _ArrayNode:
            if (
                not token
                or (token != "0" and token.startswith("0"))
                or not token.isascii()
                or not token.isdecimal()
            ):
                raise _ProjectionIntegrityError()
            index = int(token)
            if index >= len(current.items):
                raise _ProjectionIntegrityError()
            current = current.items[index]
            continue
        raise _ProjectionIntegrityError()
    return current


class ReportBuilder:
    """Kernel-issued, schema-directed projection writer."""

    __slots__ = ("__state",)

    def __init__(
        self,
        token: object = None,
        *,
        schema: AdmittedSchema | None = None,
        declaration: ReportProjectionSpec | None = None,
        ledger: BudgetLedger | None = None,
    ) -> None:
        if (
            token is not _BUILDER_TOKEN
            or type(schema) is not AdmittedSchema
            or type(declaration) is not ReportProjectionSpec
            or type(ledger) is not BudgetLedger
        ):
            raise TypeError("ReportBuilder values are issued only by the report seal")
        self.__state = _BuilderState(
            schema=schema,
            declaration=declaration,
            ledger=ledger,
            root=_ObjectNode({}),
        )

    def _ensure_open(self) -> _BuilderState:
        state = self.__state
        if state.finished:
            raise _ProjectionIntegrityError()
        return state

    def put(self, path: str, value: JsonValue) -> None:
        state = self._ensure_open()
        tokens = _pointer_tokens(path)
        if not _is_projection_writable(path, state.declaration):
            raise _ProjectionIntegrityError(path)
        if type(value) not in _OWNED_VALUE_TYPES:
            raise _ProjectionIntegrityError(path)
        schema_node = _schema_node_for_path(state.schema, path)
        if not _matches_schema_type(value, schema_node):
            raise _ProjectionIntegrityError(path)
        parent = _node_at(state.root, tokens[:-1])
        if type(parent) is not _ObjectNode:
            raise _ProjectionIntegrityError(path)
        state.ledger.charge(
            BudgetDimension.REPORT_PROJECTION_FIELDS,
            _attachment_count(value),
            artifact_role=ArtifactRole.REPORT_SEAL,
            subject_path=path,
        )
        name = tokens[-1]
        if name in parent.members:
            raise _ProjectionIntegrityError(path)
        parent.members[name] = _to_builder_node(value)

    def append(self, path: str, value: JsonValue) -> None:
        state = self._ensure_open()
        tokens = _pointer_tokens(path)
        if not _is_projection_writable(path, state.declaration):
            raise _ProjectionIntegrityError(path)
        if type(value) not in _OWNED_VALUE_TYPES:
            raise _ProjectionIntegrityError(path)
        target = _node_at(state.root, tokens)
        if type(target) is not _ArrayNode:
            raise _ProjectionIntegrityError(path)
        item_path = _child_pointer(path, str(len(target.items)))
        schema_node = _schema_node_for_path(state.schema, item_path)
        if not _matches_schema_type(value, schema_node):
            raise _ProjectionIntegrityError(item_path)
        state.ledger.charge(
            BudgetDimension.REPORT_PROJECTION_FIELDS,
            _attachment_count(value),
            artifact_role=ArtifactRole.REPORT_SEAL,
            subject_path=item_path,
        )
        target.items.append(_to_builder_node(value))

    def _finish(self) -> JsonObject:
        state = self._ensure_open()
        state.finished = True
        value = _freeze_builder_node(state.root)
        if type(value) is not JsonObject:
            raise _ReportConstructabilityError()
        for path, kind in state.declaration.mandatory_shells:
            try:
                shell = lookup_json_pointer(value, path)
            except (KeyError, ValueError):
                raise _ReportConstructabilityError(path) from None
            expected = JsonObject if kind == "object" else JsonArray
            if type(shell) is not expected:
                raise _ReportConstructabilityError(path)
        return value

    def _close(self) -> None:
        self.__state.finished = True


def _invocation_evidence(invocation: ValidationInvocation) -> JsonObject:
    profile = invocation.assembler_profile
    assembler = JsonObject(
        (
            (JsonString("profile_id"), JsonString(profile.profile_id)),
            (
                JsonString("profile_fingerprint"),
                JsonString(profile.profile_fingerprint),
            ),
            (JsonString("assembler_kind"), JsonString(profile.assembler_kind)),
            (JsonString("assembler_id"), JsonString(profile.assembler_id)),
            (
                JsonString("assembler_version"),
                JsonString(profile.assembler_version),
            ),
            (
                JsonString("implementation_fingerprint"),
                JsonString(profile.implementation_fingerprint),
            ),
        )
    )
    recipe_fingerprint: JsonValue = (
        JsonNull()
        if invocation.recipe_value_fingerprint is None
        else JsonString(invocation.recipe_value_fingerprint)
    )
    return JsonObject(
        (
            (JsonString("assembler_profile"), assembler),
            (
                JsonString("recipe_input_payload_sha256"),
                JsonString(invocation.recipe_input_payload_sha256),
            ),
            (
                JsonString("validation_bundle_input_payload_sha256"),
                JsonString(invocation.validation_bundle_input_payload_sha256),
            ),
            (JsonString("recipe_value_fingerprint"), recipe_fingerprint),
            (
                JsonString("validation_bundle_fingerprint"),
                JsonString(invocation.validation_bundle_fingerprint),
            ),
            (
                JsonString("recipe_parse_evidence"),
                invocation.invocation_inputs["recipe_parse_evidence"],
            ),
            (JsonString("validation_bundle"), invocation.validation_bundle),
        )
    )


def _receipt_value(receipt: BudgetReceipt) -> JsonObject:
    observed = receipt.observed
    observed_value = JsonObject(
        tuple(
            (
                JsonString(field_name),
                JsonNumber(float(getattr(observed, field_name)), "integer"),
            )
            for field_name in _SNAPSHOT_FIELDS
        )
    )
    return JsonObject(
        (
            (JsonString("budget_profile"), JsonString(receipt.budget_profile)),
            (
                JsonString("limits_fingerprint"),
                JsonString(receipt.limits_fingerprint),
            ),
            (JsonString("observed"), observed_value),
        )
    )


def _attach_kernel_fields(
    body: JsonObject,
    receipt: BudgetReceipt,
    report_fingerprint: str | None,
) -> JsonObject:
    members = list(body.members)
    members.append((JsonString("validation_budget"), _receipt_value(receipt)))
    if report_fingerprint is not None:
        members.append(
            (JsonString("report_fingerprint"), JsonString(report_fingerprint))
        )
    return JsonObject(tuple(members))


def _control_failure(
    *,
    program: SealedValidationProgram | None,
    code: str,
    subject_path: str | None,
    detail: bytes,
) -> ValidationControlFailure:
    return make_control_failure(
        failure_stage=FailureStage.VALIDATION,
        code=code,
        artifact_role=ArtifactRole.REPORT_SEAL,
        program_id=None if program is None else program.program_id,
        program_fingerprint=None if program is None else program.program_fingerprint,
        subject_path=subject_path,
        message={
            "validation_constructability_failed": "Validation report cannot be constructed.",
            "validator_integrity_failure": "Validator integrity check failed.",
        }[code],
        detail=detail,
    )


def _internal_failure(
    program: SealedValidationProgram, exception: BaseException
) -> ValidationControlFailure:
    return control_failure_from_exception(
        failure_stage=FailureStage.VALIDATION,
        code="validator_internal_failure",
        artifact_role=ArtifactRole.REPORT_SEAL,
        program_id=program.program_id,
        program_fingerprint=program.program_fingerprint,
        subject_path=None,
        exception=exception,
        raw_input=None,
    )


def _budget_failure(
    *,
    program: SealedValidationProgram,
    dimension: BudgetDimension | str,
    limit: int,
    observed_lower_bound: int,
    subject_path: str | None,
) -> BudgetExceededFailure:
    return BudgetExceededFailure(
        failure_stage=FailureStage.VALIDATION,
        code="validation_budget_exceeded",
        artifact_role=ArtifactRole.REPORT_SEAL,
        program_id=program.program_id,
        program_fingerprint=program.program_fingerprint,
        subject_path=subject_path,
        message="Validation budget exceeded.",
        detail_sha256=None,
        budget_dimension=dimension,
        limit=limit,
        observed_lower_bound=observed_lower_bound,
    )


def _ledger_budget_failure(
    program: SealedValidationProgram, exception: BudgetExceeded
) -> BudgetExceededFailure:
    failure = exception.failure
    return _budget_failure(
        program=program,
        dimension=failure.budget_dimension,
        limit=failure.limit,
        observed_lower_bound=failure.observed_lower_bound,
        subject_path=failure.subject_path,
    )


def _manifest_limit(dimension: BudgetDimension) -> int:
    value = LM9A_BUDGET_MANIFEST.limits[dimension.value]
    if type(value) is not JsonNumber or not value.value.is_integer():
        raise AssertionError("fixed budget limit is invalid")
    return int(value.value)


def _schema_reservation_failure(
    program: SealedValidationProgram,
    reservation: SchemaEvaluationReservation,
) -> BudgetExceededFailure:
    reason = reservation.shape_reservation.rejection_reason
    limit = (
        reservation.per_evaluation_limit
        if reason == "per_evaluation_limit_exceeded"
        else _manifest_limit(BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS)
    )
    return _budget_failure(
        program=program,
        dimension=BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS,
        limit=limit,
        observed_lower_bound=limit + 1,
        subject_path=None,
    )


def _canonical_byte_limit() -> int:
    return _manifest_limit(BudgetDimension.REPORT_CANONICAL_BYTES)


def _validate_phase_results(
    program: SealedValidationProgram, phase_results: object
) -> tuple[PhaseResult, ...]:
    if type(phase_results) is not tuple or any(
        type(result) is not PhaseResult for result in phase_results
    ):
        raise _ProjectionIntegrityError()
    names = tuple(result.phase_name for result in phase_results)
    if names != program.execution_order or len(frozenset(names)) != len(names):
        raise _ProjectionIntegrityError()
    return cast(tuple[PhaseResult, ...], phase_results)


def _seal_validation_report_with_audit(
    context: _ValidationExecutionContext,
    phase_results: tuple[PhaseResult, ...],
) -> _AuditedReportSeal:
    """Seal one report while retaining exact final schema evidence privately."""

    audit_receipts: list[SchemaEvaluationReceipt] = []
    if type(context) is not _ValidationExecutionContext:
        return _audited_report_seal(
            _control_failure(
                program=None,
                code="validator_integrity_failure",
                subject_path=None,
                detail=b"report_context_type",
            ),
            (),
        )
    invocation = context.invocation
    program = invocation.program
    if (
        type(invocation) is not ValidationInvocation
        or type(program) is not SealedValidationProgram
        or type(context.ledger) is not BudgetLedger
    ):
        return _audited_report_seal(
            _control_failure(
                program=None,
                code="validator_integrity_failure",
                subject_path=None,
                detail=b"report_context_identity",
            ),
            (),
        )
    try:
        if not context.ledger.claim_report_seal():
            raise _ProjectionIntegrityError()
        accepted_results = _validate_phase_results(program, phase_results)
        declaration = program.report_projection
        if type(declaration) is not ReportProjectionSpec:
            raise _ProjectionIntegrityError()
        schema = program.resolve_runtime_binding("schema", declaration.output_schema_id)
        if (
            type(schema) is not AdmittedSchema
            or schema.schema_fingerprint != declaration.output_schema_fingerprint
        ):
            raise _ProjectionIntegrityError()
        projection = program.resolve_runtime_binding(
            "report_projection", declaration.projection_id
        )
        if not callable(projection):
            raise _ProjectionIntegrityError()
        envelope = ReportProjectionEnvelope(
            program_id=program.program_id,
            program_fingerprint=program.program_fingerprint,
            invocation_evidence=_invocation_evidence(invocation),
            phase_specs=program.phases,
            phase_results=accepted_results,
        )
        builder = ReportBuilder(
            _BUILDER_TOKEN,
            schema=schema,
            declaration=declaration,
            ledger=context.ledger,
        )
        try:
            returned = projection(envelope, builder)
            if returned is not None:
                raise _ProjectionIntegrityError()
            body = builder._finish()
        finally:
            builder._close()
        if (
            len(_SNAPSHOT_FIELDS) + 3 != BUDGET_RECEIPT_NESTED_FIELD_COUNT
            or FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT
            != BUDGET_RECEIPT_NESTED_FIELD_COUNT + 2
        ):
            raise _ProjectionIntegrityError()
        context.ledger.charge(
            BudgetDimension.REPORT_PROJECTION_FIELDS,
            FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT,
            artifact_role=ArtifactRole.REPORT_SEAL,
            subject_path=None,
        )
        final_instance_nodes = (
            count_json_nodes(body) + FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT
        )
        schema_reservation = reserve_schema_evaluation(
            schema,
            instance_nodes=final_instance_nodes,
            ledger=context.ledger,
        )
        if not schema_reservation.shape_reservation.accepted:
            audit_receipts.append(
                _rejected_schema_evaluation_receipt(schema, schema_reservation)
            )
            return _audited_report_seal(
                _schema_reservation_failure(program, schema_reservation),
                tuple(audit_receipts),
            )
        receipt = context.ledger.reserve_report_seal_and_freeze()
    except BudgetExceeded as exception:
        return _audited_report_seal(
            _ledger_budget_failure(program, exception), tuple(audit_receipts)
        )
    except _ReportConstructabilityError as exception:
        return _audited_report_seal(
            _control_failure(
                program=program,
                code="validation_constructability_failed",
                subject_path=exception.subject_path,
                detail=b"report_schema_shape",
            ),
            tuple(audit_receipts),
        )
    except _ProjectionIntegrityError as exception:
        return _audited_report_seal(
            _control_failure(
                program=program,
                code="validator_integrity_failure",
                subject_path=exception.subject_path,
                detail=b"report_projection_contract",
            ),
            tuple(audit_receipts),
        )
    except BudgetLedgerFrozen:
        return _audited_report_seal(
            _control_failure(
                program=program,
                code="validator_integrity_failure",
                subject_path=None,
                detail=b"report_ledger_already_frozen",
            ),
            tuple(audit_receipts),
        )
    except SchemaEvaluationInputError:
        return _audited_report_seal(
            _control_failure(
                program=program,
                code="validator_integrity_failure",
                subject_path=None,
                detail=b"report_schema_reservation",
            ),
            tuple(audit_receipts),
        )
    except Exception as exception:
        return _audited_report_seal(
            _internal_failure(program, exception), tuple(audit_receipts)
        )

    try:
        if (
            receipt.observed.report_seal_reserved_work_units != 262_144
            or receipt.observed.schema_evaluation_shape_units
            != schema_reservation.shape_reservation.aggregate_after
        ):
            raise _ProjectionIntegrityError()
        meter = SealMeter(receipt)
        meter.charge_projection_fields(receipt.observed.report_projection_fields)
        fingerprint_projection = _attach_kernel_fields(body, receipt, None)
        if count_json_nodes(fingerprint_projection) != final_instance_nodes - 1:
            raise _ProjectionIntegrityError()
        projection_bytes = canonical_json_bytes(
            fingerprint_projection,
            max_bytes=_canonical_byte_limit(),
        )
        meter.charge_canonical_bytes(len(projection_bytes))
        report_fingerprint = sha256_prefixed(projection_bytes)
        final_value = _attach_kernel_fields(body, receipt, report_fingerprint)
        if count_json_nodes(final_value) != final_instance_nodes:
            raise _ProjectionIntegrityError()
        schema_evaluation = evaluate_schema_with_reservation(
            schema,
            final_value,
            instance_binding=InstanceBinding(
                artifact_id=program.program_id,
                artifact_fingerprint=report_fingerprint,
                instance_pointer="",
            ),
            reservation=schema_reservation,
        )
        if type(schema_evaluation) is SchemaEvaluationReceipt:
            audit_receipts.append(schema_evaluation)
        if (
            type(schema_evaluation) is not SchemaEvaluationReceipt
            or schema_evaluation.reservation
            is not schema_reservation.shape_reservation
            or schema_evaluation.evaluator_invoked is not True
            or type(schema_evaluation.evaluation_passed) is not bool
        ):
            raise _ProjectionIntegrityError()
        if not schema_evaluation.evaluation_passed:
            subject_path = (
                schema_evaluation.bounded_errors[0].instance_path or None
                if schema_evaluation.bounded_errors
                else None
            )
            raise _ReportConstructabilityError(subject_path)
        if schema_evaluation.failure_code is not None or schema_evaluation.bounded_errors:
            raise _ProjectionIntegrityError()
        final_bytes = canonical_json_bytes(
            final_value,
            max_bytes=_canonical_byte_limit(),
        )
        meter.charge_canonical_bytes(len(final_bytes))
    except CanonicalJsonSizeError as exception:
        return _audited_report_seal(
            _budget_failure(
                program=program,
                dimension=BudgetDimension.REPORT_CANONICAL_BYTES,
                limit=exception.limit,
                observed_lower_bound=exception.observed_lower_bound,
                subject_path=None,
            ),
            tuple(audit_receipts),
        )
    except _SealMeterExceeded as exception:
        return _audited_report_seal(
            _budget_failure(
                program=program,
                dimension=exception.dimension,
                limit=exception.limit,
                observed_lower_bound=exception.observed_lower_bound,
                subject_path=None,
            ),
            tuple(audit_receipts),
        )
    except _ReportConstructabilityError as exception:
        return _audited_report_seal(
            _control_failure(
                program=program,
                code="validation_constructability_failed",
                subject_path=exception.subject_path,
                detail=b"report_output_schema",
            ),
            tuple(audit_receipts),
        )
    except (_ProjectionIntegrityError, SchemaEvaluationInputError) as exception:
        return _audited_report_seal(
            _control_failure(
                program=program,
                code="validator_integrity_failure",
                subject_path=(
                    exception.subject_path
                    if type(exception) is _ProjectionIntegrityError
                    else None
                ),
                detail=b"report_final_shape",
            ),
            tuple(audit_receipts),
        )
    except Exception as exception:
        return _audited_report_seal(
            _internal_failure(program, exception), tuple(audit_receipts)
        )

    return _audited_report_seal(
        PublishedValidationReport(
            schema_id=declaration.output_schema_id,
            report_fingerprint=report_fingerprint,
            canonical_bytes=final_bytes,
            value=final_value,
        ),
        tuple(audit_receipts),
    )


def seal_validation_report(
    context: _ValidationExecutionContext,
    phase_results: tuple[PhaseResult, ...],
) -> PublishedValidationReport | ValidationControlFailure:
    """Project once, freeze one receipt, and publish only a complete sealed report."""

    return _seal_validation_report_with_audit(context, phase_results).public_result


__all__ = (
    "PublishedValidationReport",
    "ReportBuilder",
    "ReportProjectionEnvelope",
    "seal_validation_report",
)
