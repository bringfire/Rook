"""Fixed LM9A budget manifest, invocation ledger, and report-seal meter."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, replace

from .canonical_json import canonical_fingerprint
from .control import (
    ArtifactRole,
    BudgetDimension,
    BudgetExceededFailure,
    FailureStage,
)
from .owned_json import JsonObject, own_trusted_json


LM9A_BUDGET_PROFILE_ID = "rook.validation_budget:lm9a_v1"
SCHEMA_EVALUATION_SHAPE_METRIC_ID = (
    "rook.schema_evaluation_shape:max_schema_or_expansion_times_instance:v1"
)
SCHEMA_EVALUATION_SHAPE_FORMULA = (
    "max(schema_nodes,evaluation_expansion_units)*instance_nodes"
)
MAX_CHECKED_BUDGET_INTEGER = sys.maxsize

_LIMIT_VALUES: dict[BudgetDimension, int] = {
    BudgetDimension.RECIPE_INPUT_BYTES: 1_048_576,
    BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES: 4_194_304,
    BudgetDimension.CONTAINER_DEPTH: 64,
    BudgetDimension.NUMBER_TOKEN_CHARS: 1_024,
    BudgetDimension.PARSED_NODES: 100_000,
    BudgetDimension.OBJECT_MEMBERS: 16_384,
    BudgetDimension.ARRAY_ITEMS: 16_384,
    BudgetDimension.DECODED_STRING_BYTES: 2_097_152,
    BudgetDimension.PARSER_WORK_UNITS: 500_000,
    BudgetDimension.SEMANTIC_REFERENCES: 25_000,
    BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS: 16_000_000,
    BudgetDimension.DIAGNOSTICS: 1_024,
    BudgetDimension.COMPILE_BLOCKERS: 1_024,
    BudgetDimension.KERNEL_PHASE_WORK_UNITS: 1_000_000,
    BudgetDimension.REPORT_CANONICAL_BYTES: 2_097_152,
    BudgetDimension.REPORT_PROJECTION_FIELDS: 131_072,
    BudgetDimension.REPORT_SEAL_WORK_UNITS: 262_144,
}

_SNAPSHOT_FIELDS = {
    BudgetDimension.RECIPE_INPUT_BYTES: "recipe_input_bytes",
    BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES: "validation_bundle_input_bytes",
    BudgetDimension.CONTAINER_DEPTH: "maximum_container_depth",
    BudgetDimension.NUMBER_TOKEN_CHARS: "maximum_number_token_chars",
    BudgetDimension.PARSED_NODES: "parsed_nodes",
    BudgetDimension.OBJECT_MEMBERS: "maximum_object_members",
    BudgetDimension.ARRAY_ITEMS: "maximum_array_items",
    BudgetDimension.DECODED_STRING_BYTES: "decoded_string_bytes",
    BudgetDimension.PARSER_WORK_UNITS: "parser_work_units",
    BudgetDimension.SEMANTIC_REFERENCES: "semantic_references",
    BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS: "schema_evaluation_shape_units",
    BudgetDimension.DIAGNOSTICS: "diagnostics",
    BudgetDimension.COMPILE_BLOCKERS: "compile_blockers",
    BudgetDimension.KERNEL_PHASE_WORK_UNITS: "kernel_phase_work_units",
    BudgetDimension.REPORT_PROJECTION_FIELDS: "report_projection_fields",
    BudgetDimension.REPORT_SEAL_WORK_UNITS: "report_seal_reserved_work_units",
}

_MAXIMUM_DIMENSIONS = frozenset(
    {
        BudgetDimension.RECIPE_INPUT_BYTES,
        BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES,
        BudgetDimension.CONTAINER_DEPTH,
        BudgetDimension.NUMBER_TOKEN_CHARS,
        BudgetDimension.OBJECT_MEMBERS,
        BudgetDimension.ARRAY_ITEMS,
    }
)

_LEDGER_ONLY_DIMENSIONS = frozenset(_SNAPSHOT_FIELDS) - {
    BudgetDimension.REPORT_SEAL_WORK_UNITS
}


class BudgetInputError(ValueError):
    """A budget operation received an invalid internal argument."""


class BudgetLedgerFrozen(RuntimeError):
    """The report receipt was frozen and no ledger mutation remains legal."""


class BudgetExceeded(RuntimeError):
    """A ledger operation exceeded a fixed inclusive limit."""

    def __init__(self, failure: BudgetExceededFailure) -> None:
        self.failure = failure
        super().__init__(failure.message)


class _SealMeterExceeded(RuntimeError):
    """Package-private signal for Task 8 to catch and map.

    Task 8 must emit ``validation_budget_exceeded`` with
    ``artifact_role=report_seal`` after adding sealed program/report context.
    Task 2 cannot construct that complete public envelope.
    """

    def __init__(self, dimension: BudgetDimension, limit: int, observed_lower_bound: int) -> None:
        self.dimension = dimension.value
        self.limit = limit
        self.observed_lower_bound = observed_lower_bound
        super().__init__("Report seal budget exceeded.")


@dataclass(frozen=True, slots=True)
class BudgetManifest:
    """The release-fixed limits and the fingerprint that binds their policy."""

    profile_id: str
    limits: JsonObject
    limits_fingerprint: str


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """An immutable observation of invocation-owned ledger counters."""

    recipe_input_bytes: int
    validation_bundle_input_bytes: int
    maximum_container_depth: int
    maximum_number_token_chars: int
    parsed_nodes: int
    maximum_object_members: int
    maximum_array_items: int
    decoded_string_bytes: int
    parser_work_units: int
    semantic_references: int
    schema_evaluation_shape_units: int
    diagnostics: int
    compile_blockers: int
    kernel_phase_work_units: int
    report_projection_fields: int
    report_seal_reserved_work_units: int

    def with_report_seal_reservation(self, work_units: int) -> "BudgetSnapshot":
        """Return a new snapshot with the fixed seal allowance recorded."""

        return replace(self, report_seal_reserved_work_units=work_units)


@dataclass(frozen=True, slots=True)
class BudgetReceipt:
    """The fixed report receipt, deliberately detached from serializer work."""

    budget_profile: str
    limits_fingerprint: str
    observed: BudgetSnapshot


_SCHEMA_SHAPE_RESERVATION_ISSUER = object()


@dataclass(frozen=True)
class SchemaShapeReservation:
    """The checked result of reserving one schema-evaluation product."""

    __slots__ = (
        "accepted",
        "shape_metric_id",
        "schema_nodes",
        "evaluation_expansion_units",
        "shape_basis_units",
        "instance_nodes",
        "attempted_shape_units",
        "aggregate_before",
        "aggregate_after",
        "rejection_reason",
        "_ledger_origin",
        "_issuer_capability",
        "_issued_signature",
    )

    accepted: bool
    shape_metric_id: str
    schema_nodes: int
    evaluation_expansion_units: int
    shape_basis_units: int
    instance_nodes: int
    attempted_shape_units: int | None
    aggregate_before: int
    aggregate_after: int | None
    rejection_reason: str | None

    @classmethod
    def _issue(
        cls,
        token: object = None,
        *,
        accepted: bool,
        shape_metric_id: str,
        schema_nodes: int,
        evaluation_expansion_units: int,
        shape_basis_units: int,
        instance_nodes: int,
        attempted_shape_units: int | None,
        aggregate_before: int,
        aggregate_after: int | None,
        rejection_reason: str | None,
        ledger_origin: object,
    ) -> "SchemaShapeReservation":
        if token is not _SCHEMA_SHAPE_RESERVATION_ISSUER:
            raise TypeError("invalid schema-shape reservation issuer")
        value = cls(
            accepted=accepted,
            shape_metric_id=shape_metric_id,
            schema_nodes=schema_nodes,
            evaluation_expansion_units=evaluation_expansion_units,
            shape_basis_units=shape_basis_units,
            instance_nodes=instance_nodes,
            attempted_shape_units=attempted_shape_units,
            aggregate_before=aggregate_before,
            aggregate_after=aggregate_after,
            rejection_reason=rejection_reason,
        )
        object.__setattr__(
            value,
            "_ledger_origin",
            ledger_origin,
        )
        object.__setattr__(
            value,
            "_issuer_capability",
            _SCHEMA_SHAPE_RESERVATION_ISSUER,
        )
        object.__setattr__(
            value,
            "_issued_signature",
            _schema_shape_reservation_signature(value),
        )
        return value


def _schema_shape_reservation_signature(
    value: SchemaShapeReservation,
) -> tuple[object, ...]:
    return (
        id(value),
        value.accepted,
        value.shape_metric_id,
        value.schema_nodes,
        value.evaluation_expansion_units,
        value.shape_basis_units,
        value.instance_nodes,
        value.attempted_shape_units,
        value.aggregate_before,
        value.aggregate_after,
        value.rejection_reason,
        id(object.__getattribute__(value, "_ledger_origin")),
    )


def _is_issued_schema_shape_reservation(value: object) -> bool:
    if type(value) is not SchemaShapeReservation:
        return False
    try:
        capability = object.__getattribute__(
            value,
            "_issuer_capability",
        )
        signature = object.__getattribute__(
            value,
            "_issued_signature",
        )
        return (
            capability is _SCHEMA_SHAPE_RESERVATION_ISSUER
            and signature == _schema_shape_reservation_signature(value)
        )
    except (AttributeError, TypeError):
        return False


def _is_schema_shape_reservation_for_ledger(
    value: object,
    ledger: object,
) -> bool:
    if not _is_issued_schema_shape_reservation(value) or type(ledger) is not BudgetLedger:
        return False
    try:
        reservation_origin = object.__getattribute__(value, "_ledger_origin")
        ledger_origin = object.__getattribute__(ledger, "_schema_shape_origin")
        return reservation_origin is ledger_origin
    except (AttributeError, TypeError):
        return False


def _owned_limit_object() -> JsonObject:
    owned = own_trusted_json(
        {dimension.value: limit for dimension, limit in _LIMIT_VALUES.items()}
    )
    if type(owned) is not JsonObject:
        raise AssertionError("fixed limits must seal as an owned object")
    return owned


def _manifest_fingerprint(limits: JsonObject) -> str:
    binding = own_trusted_json(
        {
            "profile_id": LM9A_BUDGET_PROFILE_ID,
            "limits": {dimension.value: limit for dimension, limit in _LIMIT_VALUES.items()},
            "admission_order": "bundle_then_recipe_v1",
            "accounting_rules": "lm9a_kernel_controlled_v2",
            "schema_evaluation_shape_metric": {
                "metric_id": SCHEMA_EVALUATION_SHAPE_METRIC_ID,
                "formula": SCHEMA_EVALUATION_SHAPE_FORMULA,
            },
            "seal_algorithm": "fixed_report_seal_v1",
        }
    )
    return canonical_fingerprint(binding)


_LIMITS = _owned_limit_object()
LM9A_BUDGET_MANIFEST = BudgetManifest(
    profile_id=LM9A_BUDGET_PROFILE_ID,
    limits=_LIMITS,
    limits_fingerprint=_manifest_fingerprint(_LIMITS),
)


def _require_dimension(value: object) -> BudgetDimension:
    if type(value) is not BudgetDimension:
        raise BudgetInputError("budget dimension must be an exact BudgetDimension")
    return value


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise BudgetInputError(f"{field_name} must be a nonnegative exact integer")
    return value


def _failure_stage(artifact_role: ArtifactRole | str) -> FailureStage:
    if artifact_role in (
        ArtifactRole.PHASE_ENGINE,
        ArtifactRole.REPORT_SEAL,
        ArtifactRole.PHASE_ENGINE.value,
        ArtifactRole.REPORT_SEAL.value,
    ):
        return FailureStage.VALIDATION
    return FailureStage.PREFLIGHT


class BudgetLedger:
    """The single mutable accounting authority for one validation invocation."""

    __slots__ = (
        "_manifest",
        "_observed",
        "_frozen",
        "_receipt",
        "_report_seal_claimed",
        "_schema_shape_origin",
        "_lock",
    )

    def __init__(self, manifest: BudgetManifest) -> None:
        if type(manifest) is not BudgetManifest:
            raise BudgetInputError("budget ledger requires an exact BudgetManifest")
        if manifest is not LM9A_BUDGET_MANIFEST:
            raise BudgetInputError("budget ledger requires the fixed LM9A manifest")
        self._manifest = manifest
        self._observed = {
            field_name: 0
            for dimension, field_name in _SNAPSHOT_FIELDS.items()
            if dimension is not BudgetDimension.REPORT_SEAL_WORK_UNITS
        }
        self._observed["report_seal_reserved_work_units"] = 0
        self._frozen = False
        self._receipt: BudgetReceipt | None = None
        self._report_seal_claimed = False
        self._schema_shape_origin = object()
        self._lock = threading.Lock()

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise BudgetLedgerFrozen("Budget ledger is frozen.")

    def _limit_for(self, dimension: BudgetDimension) -> int:
        return _LIMIT_VALUES[dimension]

    def _raise_exceeded(
        self,
        dimension: BudgetDimension,
        limit: int,
        observed_lower_bound: int,
        *,
        artifact_role: ArtifactRole | str,
        subject_path: str | None,
    ) -> None:
        failure = BudgetExceededFailure(
            failure_stage=_failure_stage(artifact_role),
            code="validation_budget_exceeded",
            artifact_role=artifact_role,
            program_id=None,
            program_fingerprint=None,
            subject_path=subject_path,
            message="Validation budget exceeded.",
            detail_sha256=None,
            budget_dimension=dimension,
            limit=limit,
            observed_lower_bound=observed_lower_bound,
        )
        raise BudgetExceeded(failure)

    def charge(
        self,
        dimension: BudgetDimension,
        amount: int,
        *,
        artifact_role: ArtifactRole | str,
        subject_path: str | None,
    ) -> None:
        """Charge one closed dimension before the caller mutates owned state."""

        dimension = _require_dimension(dimension)
        amount = _require_nonnegative_integer(amount, "budget amount")
        if dimension not in _LEDGER_ONLY_DIMENSIONS:
            raise BudgetInputError("budget dimension is reserved for report sealing")
        with self._lock:
            self._ensure_mutable()
            field_name = _SNAPSHOT_FIELDS[dimension]
            current = self._observed[field_name]
            proposed = (
                max(current, amount)
                if dimension in _MAXIMUM_DIMENSIONS
                else current + amount
            )
            limit = self._limit_for(dimension)
            if proposed > limit:
                self._raise_exceeded(
                    dimension,
                    limit,
                    proposed,
                    artifact_role=artifact_role,
                    subject_path=subject_path,
                )
            self._observed[field_name] = proposed

    def reserve_schema_shape(
        self,
        *,
        schema_nodes: int,
        evaluation_expansion_units: int,
        instance_nodes: int,
        per_evaluation_limit: int,
    ) -> SchemaShapeReservation:
        """Reserve the checked conservative schema-work product once."""

        schema_nodes = _require_nonnegative_integer(schema_nodes, "schema node count")
        evaluation_expansion_units = _require_nonnegative_integer(
            evaluation_expansion_units,
            "schema evaluation expansion count",
        )
        instance_nodes = _require_nonnegative_integer(instance_nodes, "instance node count")
        per_evaluation_limit = _require_nonnegative_integer(
            per_evaluation_limit, "per-evaluation limit"
        )
        shape_basis_units = max(schema_nodes, evaluation_expansion_units)
        with self._lock:
            self._ensure_mutable()
            aggregate_before = self._observed["schema_evaluation_shape_units"]
            aggregate_limit = self._limit_for(
                BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS
            )
            aggregate_remaining = aggregate_limit - aggregate_before

            if (
                schema_nodes > MAX_CHECKED_BUDGET_INTEGER
                or evaluation_expansion_units > MAX_CHECKED_BUDGET_INTEGER
                or shape_basis_units > MAX_CHECKED_BUDGET_INTEGER
                or instance_nodes > MAX_CHECKED_BUDGET_INTEGER
                or per_evaluation_limit > MAX_CHECKED_BUDGET_INTEGER
            ):
                return SchemaShapeReservation._issue(
                    _SCHEMA_SHAPE_RESERVATION_ISSUER,
                    accepted=False,
                    shape_metric_id=SCHEMA_EVALUATION_SHAPE_METRIC_ID,
                    schema_nodes=schema_nodes,
                    evaluation_expansion_units=evaluation_expansion_units,
                    shape_basis_units=shape_basis_units,
                    instance_nodes=instance_nodes,
                    attempted_shape_units=None,
                    aggregate_before=aggregate_before,
                    aggregate_after=None,
                    rejection_reason="shape_product_overflow",
                    ledger_origin=self._schema_shape_origin,
                )

            if shape_basis_units:
                per_evaluation_instances = per_evaluation_limit // shape_basis_units
                aggregate_remaining_instances = aggregate_remaining // shape_basis_units
                if instance_nodes > per_evaluation_instances:
                    return SchemaShapeReservation._issue(
                        _SCHEMA_SHAPE_RESERVATION_ISSUER,
                        accepted=False,
                        shape_metric_id=SCHEMA_EVALUATION_SHAPE_METRIC_ID,
                        schema_nodes=schema_nodes,
                        evaluation_expansion_units=evaluation_expansion_units,
                        shape_basis_units=shape_basis_units,
                        instance_nodes=instance_nodes,
                        attempted_shape_units=None,
                        aggregate_before=aggregate_before,
                        aggregate_after=None,
                        rejection_reason="per_evaluation_limit_exceeded",
                        ledger_origin=self._schema_shape_origin,
                    )
                if instance_nodes > aggregate_remaining_instances:
                    return SchemaShapeReservation._issue(
                        _SCHEMA_SHAPE_RESERVATION_ISSUER,
                        accepted=False,
                        shape_metric_id=SCHEMA_EVALUATION_SHAPE_METRIC_ID,
                        schema_nodes=schema_nodes,
                        evaluation_expansion_units=evaluation_expansion_units,
                        shape_basis_units=shape_basis_units,
                        instance_nodes=instance_nodes,
                        attempted_shape_units=None,
                        aggregate_before=aggregate_before,
                        aggregate_after=None,
                        rejection_reason="invocation_shape_limit_exceeded",
                        ledger_origin=self._schema_shape_origin,
                    )

            attempted = shape_basis_units * instance_nodes
            aggregate_after = aggregate_before + attempted
            self._observed["schema_evaluation_shape_units"] = aggregate_after
            return SchemaShapeReservation._issue(
                _SCHEMA_SHAPE_RESERVATION_ISSUER,
                accepted=True,
                shape_metric_id=SCHEMA_EVALUATION_SHAPE_METRIC_ID,
                schema_nodes=schema_nodes,
                evaluation_expansion_units=evaluation_expansion_units,
                shape_basis_units=shape_basis_units,
                instance_nodes=instance_nodes,
                attempted_shape_units=attempted,
                aggregate_before=aggregate_before,
                aggregate_after=aggregate_after,
                rejection_reason=None,
                ledger_origin=self._schema_shape_origin,
            )

    def _snapshot_unlocked(self) -> BudgetSnapshot:
        return BudgetSnapshot(**self._observed)

    def snapshot(self) -> BudgetSnapshot:
        """Return a value snapshot with no mutable reference to this ledger."""

        with self._lock:
            return self._snapshot_unlocked()

    def claim_report_seal(self) -> bool:
        """Claim this invocation's sole report attempt without charging work."""

        with self._lock:
            if self._report_seal_claimed:
                return False
            self._ensure_mutable()
            self._report_seal_claimed = True
            return True

    def reserve_report_seal_and_freeze(self) -> BudgetReceipt:
        """Atomically record the fixed allowance and freeze every counter."""

        with self._lock:
            self._ensure_mutable()
            reservation = self._limit_for(BudgetDimension.REPORT_SEAL_WORK_UNITS)
            frozen_observed = dict(self._observed)
            frozen_observed["report_seal_reserved_work_units"] = reservation
            receipt = BudgetReceipt(
                budget_profile=self._manifest.profile_id,
                limits_fingerprint=self._manifest.limits_fingerprint,
                observed=BudgetSnapshot(**frozen_observed),
            )
            self._observed["report_seal_reserved_work_units"] = reservation
            self._receipt = receipt
            self._frozen = True
            return receipt


def create_budget_ledger(manifest: BudgetManifest) -> BudgetLedger:
    """Create the invocation-private ledger bound by the fixed program."""

    return BudgetLedger(manifest)


class SealMeter:
    """Post-freeze report-seal accounting with no reference to any ledger."""

    __slots__ = ("_canonical_bytes", "_projection_fields", "_work_units")

    def __init__(self, receipt: BudgetReceipt) -> None:
        if type(receipt) is not BudgetReceipt:
            raise BudgetInputError("seal meter requires an exact frozen BudgetReceipt")
        if (
            receipt.budget_profile != LM9A_BUDGET_PROFILE_ID
            or receipt.limits_fingerprint != LM9A_BUDGET_MANIFEST.limits_fingerprint
            or receipt.observed.report_seal_reserved_work_units
            != _LIMIT_VALUES[BudgetDimension.REPORT_SEAL_WORK_UNITS]
        ):
            raise BudgetInputError("seal meter requires a valid fixed-profile receipt")
        self._canonical_bytes = 0
        self._projection_fields = 0
        self._work_units = 0

    @property
    def canonical_bytes(self) -> int:
        return self._canonical_bytes

    @property
    def projection_fields(self) -> int:
        return self._projection_fields

    @property
    def work_units(self) -> int:
        return self._work_units

    def _charge_work(self, amount: int) -> None:
        limit = _LIMIT_VALUES[BudgetDimension.REPORT_SEAL_WORK_UNITS]
        observed = self._work_units + amount
        if observed > limit:
            raise _SealMeterExceeded(
                BudgetDimension.REPORT_SEAL_WORK_UNITS, limit, observed
            )
        self._work_units = observed

    def charge_canonical_bytes(self, byte_count: int) -> None:
        """Charge one complete canonical serialization after checking its byte cap."""

        byte_count = _require_nonnegative_integer(byte_count, "canonical byte count")
        byte_limit = _LIMIT_VALUES[BudgetDimension.REPORT_CANONICAL_BYTES]
        if byte_count > byte_limit:
            raise _SealMeterExceeded(
                BudgetDimension.REPORT_CANONICAL_BYTES, byte_limit, byte_count
            )
        work_units = (byte_count + 63) // 64
        self._charge_work(work_units)
        self._canonical_bytes += byte_count

    def charge_projection_fields(self, field_count: int) -> None:
        """Charge precomputed projection work without writing it into a receipt."""

        field_count = _require_nonnegative_integer(field_count, "projection field count")
        field_limit = _LIMIT_VALUES[BudgetDimension.REPORT_PROJECTION_FIELDS]
        observed = self._projection_fields + field_count
        if observed > field_limit:
            raise _SealMeterExceeded(
                BudgetDimension.REPORT_PROJECTION_FIELDS, field_limit, observed
            )
        self._charge_work(field_count)
        self._projection_fields = observed


__all__ = (
    "BudgetDimension",
    "BudgetExceeded",
    "BudgetInputError",
    "BudgetLedger",
    "BudgetLedgerFrozen",
    "BudgetManifest",
    "BudgetReceipt",
    "BudgetSnapshot",
    "create_budget_ledger",
    "LM9A_BUDGET_MANIFEST",
    "LM9A_BUDGET_PROFILE_ID",
    "MAX_CHECKED_BUDGET_INTEGER",
    "SCHEMA_EVALUATION_SHAPE_FORMULA",
    "SCHEMA_EVALUATION_SHAPE_METRIC_ID",
    "SchemaShapeReservation",
    "SealMeter",
)
