"""Closed resource accounting for governed-resolution checkpoint evidence."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import sys
import weakref
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


_SCRIPTS_DIR = Path(__file__).resolve().parent
_MCP_SRC = _SCRIPTS_DIR.parent / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT


PROFILE_SCHEMA_ID = "rook.archive_evidence_resource_profile:v1"
PROFILE_ID = "rook.archive_evidence_resource_profile:lm9b_resolution_v1"
CHECKPOINT_SCHEMA_ID = "rook.lm9b_p.governed_resolution_checkpoint:v1"
PROFILE_FINGERPRINT = (
    "sha256:271d641d5b7cebc1ffa7e2f8c924eb7a9f5d0d55f36d69f91995a597af23909b"
)
MAX_PLANNER_CALLS = 6
MAX_EVALUATOR_CALLS = 1

_FORMULA_IDS = (
    "call_ledger_v1",
    "evaluator_member_v1",
    "fixed_member_v1",
    "planner_session_v1",
    "recipe_member_v1",
)
_CONSTANTS = {
    "absolute_member_ceiling_bytes": 345_068_924,
    "adapter_request_overhead_bytes": 131_072,
    "base64_denominator": 3,
    "base64_numerator": 4,
    "evaluator_assistant_projection_bytes": 1_048_576,
    "evaluator_canonical_request_bytes": 4_194_304,
    "evaluator_member_framing_bytes": 262_144,
    "evaluator_parsed_result_bytes": 1_048_576,
    "evaluator_raw_error_bytes": 524_288,
    "evaluator_raw_response_bytes": 1_048_576,
    "json_string_escape_multiplier": 6,
    "ledger_framing_bytes": 262_144,
    "max_evaluator_calls": MAX_EVALUATOR_CALLS,
    "max_planner_calls": MAX_PLANNER_CALLS,
    "max_recipe_bytes": PLANNER_SUPPORT.MAX_RECIPE_BYTES,
    "planner_assistant_projection_bytes": 2_097_152,
    "planner_canonical_request_base_bytes": 262_144,
    "planner_feedback_projection_bytes": 262_144,
    "planner_raw_error_bytes": 524_288,
    "planner_raw_response_bytes": 2_097_152,
    "planner_request_turn_framing_bytes": 65_536,
    "planner_session_framing_bytes": 262_144,
    "provider_metadata_bytes": 262_144,
    "row_framing_bytes": 65_536,
    "turn_summary_bytes": 262_144,
    "usage_bytes": 65_536,
}
_SERIALIZER = {
    "base64": "rfc4648_standard_padded:v1",
    "canonical_json": (
        "python_json_dumps.ensure_ascii_false.sort_keys_true."
        "separators_comma_colon:utf8:v1"
    ),
    "json_string_escaping": "json_worst_case_six_bytes_per_input_byte:v1",
    "utf8": "strict_no_bom:v1",
}
_MEMBER_ROWS = (
    ("authority.json", "authority", "fixed_member_v1", 4_194_304),
    ("boundary.json", "boundary", "fixed_member_v1", 1_048_576),
    ("call-ledger.json", "calls", "call_ledger_v1", None),
    ("candidate-recipe.json", "candidate", "recipe_member_v1", None),
    ("checkpoint-gate.json", "candidate", "fixed_member_v1", 2_097_152),
    ("checksums.json", "checksums", "fixed_member_v1", 1_048_576),
    ("classification.json", "outcome", "fixed_member_v1", 1_048_576),
    ("correspondence.json", "correspondence", "fixed_member_v1", 2_097_152),
    ("evaluator.json", "evaluator", "evaluator_member_v1", None),
    ("instrument.json", "instrument", "fixed_member_v1", 2_097_152),
    ("isolation.json", "isolation", "fixed_member_v1", 4_194_304),
    ("launch.json", "launch", "fixed_member_v1", 1_048_576),
    ("migration.json", "migration", "fixed_member_v1", 4_194_304),
    ("planner-session.json", "planner", "planner_session_v1", None),
    ("readiness.json", "readiness", "fixed_member_v1", 1_048_576),
    ("record.json", "identity", "fixed_member_v1", 1_048_576),
    ("source.json", "source", "fixed_member_v1", 1_048_576),
)
RESOLUTION_ARCHIVE_MEMBERS = MappingProxyType(
    {path: role for path, role, _formula, _ceiling in _MEMBER_ROWS}
)
_MEMBER_BY_PATH = MappingProxyType(
    {
        path: {
            "path": path,
            "role": role,
            "formula_id": formula,
            **(
                {"fixed_ceiling_bytes": ceiling}
                if ceiling is not None
                else {}
            ),
        }
        for path, role, formula, ceiling in _MEMBER_ROWS
    }
)
_CALL_LEDGER_FIELDS = frozenset(
    {
        "schema",
        "call_index",
        "role",
        "request_raw_sha256",
        "preceding_transcript_fingerprint",
        "provider_timeout_s",
        "controller_deadline_state",
        "role_contract_fingerprint",
        "dispatch_marker_raw_sha256",
        "canonical_request_json",
        "provider_claimed_raw_request_b64",
        "provider_claimed_raw_request_sha256",
        "provider_raw_error_b64",
        "provider_raw_error_sha256",
        "raw_response_b64",
        "raw_response_sha256",
        "assistant_message",
        "usage",
        "provider_metadata",
        "outcome",
        "exception_type",
        "failure_type",
        "elapsed_ms",
        "terminal",
    }
)
_PLANNER_MEMBER_FIELDS = frozenset(
    {
        "schema",
        "termination",
        "call_count",
        "final_recipe_raw_sha256",
        "calls",
        "turns",
    }
)
_EVALUATOR_MEMBER_FIELDS = frozenset(
    {
        "schema",
        "call_index",
        "dispatched_request_b64",
        "provider_claimed_raw_request_b64",
        "provider_raw_error_b64",
        "raw_response_b64",
        "assistant_message",
        "usage",
        "provider_metadata",
        "termination",
        "recommendation",
        "evidence",
        "quiescent",
    }
)


class ResolutionArchiveEvidenceError(ValueError):
    """A stable governed-resolution archive resource refusal."""


class VerifiedResolutionArchiveResourceProfile:
    __slots__ = ("__weakref__",)

    def __new__(cls) -> "VerifiedResolutionArchiveResourceProfile":
        raise TypeError("resolution archive resource profiles are closure-issued")


class VerifiedResolutionCallShape:
    __slots__ = ("__weakref__",)

    def __new__(cls) -> "VerifiedResolutionCallShape":
        raise TypeError("resolution call shapes are closure-issued")


@dataclass(frozen=True)
class _CallShapeSnapshot:
    profile_fingerprint: str
    planner_count: int
    evaluator_count: int
    ordered_roles: tuple[str, ...]
    ordered_indexes: tuple[int, ...]
    branch_kinds: tuple[str, ...]
    terminal_flags: tuple[bool, ...]
    ledger_sha256: str
    planner_row_bytes: tuple[bytes, ...]
    evaluator_row_bytes: tuple[bytes, ...]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _expected_profile_value() -> dict[str, object]:
    members = []
    for path, _role, _formula, _ceiling in _MEMBER_ROWS:
        members.append(copy.deepcopy(_MEMBER_BY_PATH[path]))
    return {
        "schema": PROFILE_SCHEMA_ID,
        "profile_id": PROFILE_ID,
        "checkpoint_schema_id": CHECKPOINT_SCHEMA_ID,
        "formula_ids": list(_FORMULA_IDS),
        "constants": dict(_CONSTANTS),
        "serializer": dict(_SERIALIZER),
        "members": members,
        "profile_fingerprint": PROFILE_FINGERPRINT,
    }


def _build_profile_capabilities():
    profile_snapshots: weakref.WeakKeyDictionary[
        VerifiedResolutionArchiveResourceProfile, bytes
    ] = weakref.WeakKeyDictionary()

    def admit(raw: bytes) -> VerifiedResolutionArchiveResourceProfile:
        if type(raw) is not bytes:
            raise TypeError("resolution archive resource profile bytes are required")
        value = PLANNER_SUPPORT.parse_archive_json(raw)
        expected = _expected_profile_value()
        if type(value) is not dict or value != expected:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_resource_profile_contract_mismatch"
            )
        if value["profile_fingerprint"] != PLANNER_SUPPORT.fingerprint_without(
            value, "profile_fingerprint"
        ):
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_resource_profile_fingerprint_mismatch"
            )
        if raw != _canonical_bytes(value) + b"\n":
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_resource_profile_bytes_noncanonical"
            )
        issued = object.__new__(VerifiedResolutionArchiveResourceProfile)
        profile_snapshots[issued] = _canonical_bytes(value)
        return issued

    def consume_profile(value: object) -> Mapping[str, object]:
        if type(value) is not VerifiedResolutionArchiveResourceProfile:
            raise TypeError("closure-issued resolution archive profile required")
        raw = profile_snapshots.get(value)
        if raw is None:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_resource_profile_not_issued"
            )
        parsed = PLANNER_SUPPORT.parse_archive_json(raw)
        if parsed != _expected_profile_value():
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_resource_profile_snapshot_mismatch"
            )
        return MappingProxyType(parsed)

    return admit, consume_profile


(
    admit_resolution_archive_resource_profile,
    consume_resolution_archive_resource_profile,
) = _build_profile_capabilities()


def _base64_ceiling(size: int) -> int:
    return 4 * ((size + 2) // 3)


def _json_string_ceiling(size: int, *, escape_multiplier: int) -> int:
    return 2 + escape_multiplier * size


def _planner_canonical_request_ceiling(
    turn: int, constants: Mapping[str, object]
) -> int:
    if type(turn) is not int or not 1 <= turn <= MAX_PLANNER_CALLS:
        raise ResolutionArchiveEvidenceError("resolution_archive_planner_ordinal_invalid")
    return int(constants["planner_canonical_request_base_bytes"]) + (turn - 1) * (
        int(constants["planner_assistant_projection_bytes"])
        + int(constants["planner_feedback_projection_bytes"])
        + int(constants["planner_request_turn_framing_bytes"])
    )


def _planner_row_ceiling(turn: int, constants: Mapping[str, object]) -> int:
    request = _planner_canonical_request_ceiling(turn, constants)
    adapter = request + int(constants["adapter_request_overhead_bytes"])
    return (
        int(constants["row_framing_bytes"])
        + _json_string_ceiling(
            request,
            escape_multiplier=int(constants["json_string_escape_multiplier"]),
        )
        + _base64_ceiling(adapter)
        + max(
            _base64_ceiling(int(constants["planner_raw_response_bytes"])),
            _base64_ceiling(int(constants["planner_raw_error_bytes"])),
        )
        + int(constants["planner_assistant_projection_bytes"])
        + int(constants["usage_bytes"])
        + int(constants["provider_metadata_bytes"])
    )


def _evaluator_row_ceiling(constants: Mapping[str, object]) -> int:
    request = int(constants["evaluator_canonical_request_bytes"])
    adapter = request + int(constants["adapter_request_overhead_bytes"])
    return (
        int(constants["row_framing_bytes"])
        + _json_string_ceiling(
            request,
            escape_multiplier=int(constants["json_string_escape_multiplier"]),
        )
        + _base64_ceiling(adapter)
        + max(
            _base64_ceiling(int(constants["evaluator_raw_response_bytes"])),
            _base64_ceiling(int(constants["evaluator_raw_error_bytes"])),
        )
        + int(constants["evaluator_assistant_projection_bytes"])
        + int(constants["usage_bytes"])
        + int(constants["provider_metadata_bytes"])
    )


def _call_ledger_ceiling(
    planner_count: int,
    evaluator_count: int,
    constants: Mapping[str, object],
) -> int:
    rows = planner_count + evaluator_count
    return (
        int(constants["ledger_framing_bytes"])
        + sum(
            _planner_row_ceiling(turn, constants)
            for turn in range(1, planner_count + 1)
        )
        + evaluator_count * _evaluator_row_ceiling(constants)
        + max(0, rows - 1)
    )


def _planner_session_ceiling(
    planner_count: int,
    constants: Mapping[str, object],
) -> int:
    return (
        int(constants["planner_session_framing_bytes"])
        + sum(
            _planner_row_ceiling(turn, constants)
            + int(constants["turn_summary_bytes"])
            for turn in range(1, planner_count + 1)
        )
        + max(0, planner_count - 1)
    )


def _evaluator_member_ceiling(
    evaluator_count: int,
    constants: Mapping[str, object],
) -> int:
    if type(evaluator_count) is not int or evaluator_count not in {0, 1}:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_evaluator_count_invalid"
        )
    if evaluator_count == 0:
        return 0
    return (
        int(constants["evaluator_member_framing_bytes"])
        + _evaluator_row_ceiling(constants)
        + int(constants["evaluator_parsed_result_bytes"])
    )


def resolution_call_row_ceiling(
    *,
    role: str,
    ordinal: int,
    profile: object,
) -> int:
    value = consume_resolution_archive_resource_profile(profile)
    constants = value["constants"]
    assert isinstance(constants, Mapping)
    if role == "planner":
        ceiling = _planner_row_ceiling(ordinal, constants)
    elif role == "planner_evaluator":
        if type(ordinal) is not int or ordinal != 1:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_evaluator_ordinal_invalid"
            )
        ceiling = _evaluator_row_ceiling(constants)
    else:
        raise ResolutionArchiveEvidenceError("resolution_archive_role_unknown")
    if ceiling > int(constants["absolute_member_ceiling_bytes"]):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_derived_ceiling_exceeds_absolute"
        )
    return ceiling


def resolution_evaluator_member_ceiling(
    *,
    evaluator_count: int,
    profile: object,
) -> int:
    value = consume_resolution_archive_resource_profile(profile)
    constants = value["constants"]
    assert isinstance(constants, Mapping)
    return _evaluator_member_ceiling(evaluator_count, constants)


def _strict_base64_bytes(value: object, *, rejection_id: str) -> bytes:
    if type(value) is not str:
        raise ResolutionArchiveEvidenceError(rejection_id)
    try:
        raw = value.encode("ascii")
        decoded = base64.b64decode(raw, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ResolutionArchiveEvidenceError(rejection_id) from exc
    if base64.b64encode(decoded) != raw:
        raise ResolutionArchiveEvidenceError(rejection_id)
    return decoded


def _bounded_canonical_size(
    value: object,
    *,
    ceiling: int,
    rejection_id: str,
) -> None:
    try:
        observed = len(_canonical_bytes(value))
    except (TypeError, ValueError) as exc:
        raise ResolutionArchiveEvidenceError(rejection_id) from exc
    if observed > ceiling:
        raise ResolutionArchiveEvidenceError(rejection_id)


def validate_resolution_call_field_bounds(
    *,
    row: Mapping[str, object],
    profile: object,
) -> None:
    value = consume_resolution_archive_resource_profile(profile)
    constants = value["constants"]
    assert isinstance(constants, Mapping)
    if type(row) is not dict or set(row) != _CALL_LEDGER_FIELDS:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_call_row_shape_invalid"
        )
    role = row.get("role")
    call_index = row.get("call_index")
    if type(call_index) is not int or call_index < 0:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_call_indexes_not_contiguous"
        )
    if role == "planner":
        ordinal = call_index + 1
        request_ceiling = _planner_canonical_request_ceiling(ordinal, constants)
        response_ceiling = int(constants["planner_raw_response_bytes"])
        error_ceiling = int(constants["planner_raw_error_bytes"])
        assistant_ceiling = int(constants["planner_assistant_projection_bytes"])
    elif role == "planner_evaluator":
        ordinal = 1
        request_ceiling = int(constants["evaluator_canonical_request_bytes"])
        response_ceiling = int(constants["evaluator_raw_response_bytes"])
        error_ceiling = int(constants["evaluator_raw_error_bytes"])
        assistant_ceiling = int(constants["evaluator_assistant_projection_bytes"])
    else:
        raise ResolutionArchiveEvidenceError("resolution_archive_role_unknown")

    request = row.get("canonical_request_json")
    if type(request) is not str:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_canonical_request_invalid"
        )
    if len(request.encode("utf-8")) > request_ceiling:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_canonical_request_bytes_exceeded"
        )
    adapter = _strict_base64_bytes(
        row.get("provider_claimed_raw_request_b64"),
        rejection_id="resolution_archive_adapter_request_base64_invalid",
    )
    if len(adapter) > request_ceiling + int(
        constants["adapter_request_overhead_bytes"]
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_adapter_request_bytes_exceeded"
        )

    branch = _validate_call_branch(row)
    if branch == "response":
        response = _strict_base64_bytes(
            row.get("raw_response_b64"),
            rejection_id="resolution_archive_raw_response_base64_invalid",
        )
        if len(response) > response_ceiling:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_raw_response_bytes_exceeded"
            )
        _bounded_canonical_size(
            row.get("assistant_message"),
            ceiling=assistant_ceiling,
            rejection_id="resolution_archive_assistant_projection_bytes_exceeded",
        )
        _bounded_canonical_size(
            row.get("usage"),
            ceiling=int(constants["usage_bytes"]),
            rejection_id="resolution_archive_usage_bytes_exceeded",
        )
        _bounded_canonical_size(
            row.get("provider_metadata"),
            ceiling=int(constants["provider_metadata_bytes"]),
            rejection_id="resolution_archive_provider_metadata_bytes_exceeded",
        )
    else:
        error = _strict_base64_bytes(
            row.get("provider_raw_error_b64"),
            rejection_id="resolution_archive_raw_error_base64_invalid",
        )
        if len(error) > error_ceiling:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_raw_error_bytes_exceeded"
            )

    variable_fields = {
        "canonical_request_json",
        "provider_claimed_raw_request_b64",
        "provider_raw_error_b64",
        "raw_response_b64",
        "assistant_message",
        "usage",
        "provider_metadata",
    }
    fixed_projection = {
        key: row[key] for key in sorted(_CALL_LEDGER_FIELDS - variable_fields)
    }
    _bounded_canonical_size(
        fixed_projection,
        ceiling=int(constants["row_framing_bytes"]),
        rejection_id="resolution_archive_fixed_row_bytes_exceeded",
    )
    row_ceiling = resolution_call_row_ceiling(
        role=str(role),
        ordinal=ordinal,
        profile=profile,
    )
    _bounded_canonical_size(
        dict(row),
        ceiling=row_ceiling,
        rejection_id="resolution_archive_call_row_bytes_exceeded",
    )


def resolution_member_ceiling(
    *,
    path: str,
    profile: object,
    call_shape: object | None = None,
    preparse: bool,
) -> int:
    value = consume_resolution_archive_resource_profile(profile)
    member = _MEMBER_BY_PATH.get(path)
    if member is None:
        raise ResolutionArchiveEvidenceError("resolution_archive_member_path_unknown")
    constants = value["constants"]
    assert isinstance(constants, Mapping)
    formula = member["formula_id"]
    if formula == "fixed_member_v1":
        ceiling = int(member["fixed_ceiling_bytes"])
    elif formula == "recipe_member_v1":
        ceiling = int(constants["max_recipe_bytes"])
    else:
        if preparse:
            planner_count = MAX_PLANNER_CALLS
            evaluator_count = MAX_EVALUATOR_CALLS
        else:
            shape = consume_resolution_call_shape(call_shape, profile=profile)
            planner_count = int(shape["planner_count"])
            evaluator_count = int(shape["evaluator_count"])
        if formula == "call_ledger_v1":
            ceiling = _call_ledger_ceiling(
                planner_count, evaluator_count, constants
            )
        elif formula == "planner_session_v1":
            ceiling = _planner_session_ceiling(planner_count, constants)
        elif formula == "evaluator_member_v1":
            ceiling = _evaluator_member_ceiling(evaluator_count, constants)
        else:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_formula_id_unknown"
            )
    if ceiling > int(constants["absolute_member_ceiling_bytes"]):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_derived_ceiling_exceeds_absolute"
        )
    return ceiling


def _parse_archive_with_ceiling(raw: bytes, ceiling: int) -> object:
    if type(raw) is not bytes:
        raise TypeError("resolution archive member bytes are required")
    if len(raw) > ceiling:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_member_bytes_exceeded"
        )
    if len(raw) <= PLANNER_SUPPORT.MAX_RECIPE_BYTES:
        return PLANNER_SUPPORT.parse_archive_json(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PLANNER_SUPPORT.StrictJsonError("utf8_bom")
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise PLANNER_SUPPORT.StrictJsonError("invalid_utf8") from exc
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=PLANNER_SUPPORT._reject_duplicate_pairs,
            parse_int=PLANNER_SUPPORT._parse_int,
            parse_float=PLANNER_SUPPORT._finite_float,
            parse_constant=PLANNER_SUPPORT._reject_constant,
        )
    except PLANNER_SUPPORT.StrictJsonError:
        raise
    except json.JSONDecodeError as exc:
        raise PLANNER_SUPPORT.StrictJsonError("invalid_json") from exc
    except (RecursionError, ValueError) as exc:
        raise PLANNER_SUPPORT.StrictJsonError("invalid_json") from exc
    if PLANNER_SUPPORT._json_depth(value) > PLANNER_SUPPORT.MAX_JSON_DEPTH:
        raise PLANNER_SUPPORT.StrictJsonError("json_depth_exceeded")
    return value


def _validate_call_branch(row: Mapping[str, object]) -> str:
    returned = row.get("outcome") == "returned"
    raised = row.get("outcome") == "raised"
    if returned:
        valid = (
            type(row.get("provider_claimed_raw_request_b64")) is str
            and type(row.get("provider_claimed_raw_request_sha256")) is str
            and row.get("provider_raw_error_b64") is None
            and row.get("provider_raw_error_sha256") is None
            and type(row.get("raw_response_b64")) is str
            and type(row.get("raw_response_sha256")) is str
            and type(row.get("assistant_message")) is dict
            and type(row.get("usage")) is dict
            and type(row.get("provider_metadata")) is dict
            and row.get("exception_type") is None
            and row.get("failure_type") is None
        )
        branch = "response"
    elif raised:
        valid = (
            type(row.get("provider_claimed_raw_request_b64")) is str
            and type(row.get("provider_claimed_raw_request_sha256")) is str
            and type(row.get("provider_raw_error_b64")) is str
            and type(row.get("provider_raw_error_sha256")) is str
            and row.get("raw_response_b64") is None
            and row.get("raw_response_sha256") is None
            and row.get("assistant_message") is None
            and row.get("usage") is None
            and row.get("provider_metadata") is None
            and type(row.get("exception_type")) is str
            and type(row.get("failure_type")) is str
        )
        branch = "error"
    else:
        valid = False
        branch = "unknown"
    if not valid:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_call_branch_invalid"
        )
    return branch


def _validate_resolution_call_ledger(
    raw: bytes,
    *,
    profile: object,
) -> tuple[Mapping[str, object], _CallShapeSnapshot]:
    preparse_ceiling = resolution_member_ceiling(
        path="call-ledger.json",
        profile=profile,
        preparse=True,
    )
    value = _parse_archive_with_ceiling(raw, preparse_ceiling)
    if (
        type(value) is not dict
        or set(value) != {"schema", "calls"}
        or value.get("schema")
        != "rook.lm9b_p.governed_resolution_call_ledger:v1"
        or type(value.get("calls")) is not list
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_call_ledger_shape_invalid"
        )
    calls = value["calls"]
    if not 1 <= len(calls) <= MAX_PLANNER_CALLS + MAX_EVALUATOR_CALLS:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_call_count_invalid"
        )
    roles: list[str] = []
    indexes: list[int] = []
    branches: list[str] = []
    terminals: list[bool] = []
    seen_evaluator = False
    for expected_index, row in enumerate(calls):
        if type(row) is not dict or set(row) != _CALL_LEDGER_FIELDS:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_call_row_shape_invalid"
            )
        role = row.get("role")
        if role == "planner_evaluator":
            if seen_evaluator:
                raise ResolutionArchiveEvidenceError(
                    "resolution_archive_role_order_invalid"
                )
            seen_evaluator = True
        elif role == "planner":
            if seen_evaluator:
                raise ResolutionArchiveEvidenceError(
                    "resolution_archive_role_order_invalid"
                )
        else:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_role_unknown"
            )
        if type(row.get("call_index")) is not int or row["call_index"] != expected_index:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_call_indexes_not_contiguous"
            )
        if row.get("terminal") is not True:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_call_not_terminal"
            )
        validate_resolution_call_field_bounds(row=row, profile=profile)
        roles.append(role)
        indexes.append(expected_index)
        branches.append(_validate_call_branch(row))
        terminals.append(True)
    planner_count = roles.count("planner")
    evaluator_count = roles.count("planner_evaluator")
    if (
        not 1 <= planner_count <= MAX_PLANNER_CALLS
        or evaluator_count > MAX_EVALUATOR_CALLS
        or roles != ["planner"] * planner_count + ["planner_evaluator"] * evaluator_count
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_role_cardinality_invalid"
        )
    snapshot = _CallShapeSnapshot(
        profile_fingerprint=PROFILE_FINGERPRINT,
        planner_count=planner_count,
        evaluator_count=evaluator_count,
        ordered_roles=tuple(roles),
        ordered_indexes=tuple(indexes),
        branch_kinds=tuple(branches),
        terminal_flags=tuple(terminals),
        ledger_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        planner_row_bytes=tuple(
            _canonical_bytes(row) for row in calls if row["role"] == "planner"
        ),
        evaluator_row_bytes=tuple(
            _canonical_bytes(row)
            for row in calls
            if row["role"] == "planner_evaluator"
        ),
    )
    profile_value = consume_resolution_archive_resource_profile(profile)
    constants = profile_value["constants"]
    assert isinstance(constants, Mapping)
    actual_ceiling = _call_ledger_ceiling(
        planner_count,
        evaluator_count,
        constants,
    )
    if len(raw) > actual_ceiling:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_member_bytes_exceeded"
        )
    return MappingProxyType(copy.deepcopy(value)), snapshot


def _build_call_shape_capabilities(validator):
    call_shape_snapshots: weakref.WeakKeyDictionary[
        VerifiedResolutionCallShape, _CallShapeSnapshot
    ] = weakref.WeakKeyDictionary()

    def derive(
        raw: bytes,
        *,
        profile: object,
    ) -> tuple[Mapping[str, object], VerifiedResolutionCallShape]:
        value, snapshot = validator(raw, profile=profile)
        issued = object.__new__(VerifiedResolutionCallShape)
        call_shape_snapshots[issued] = snapshot
        return value, issued

    def consume(
        value: object,
        profile: object,
    ) -> _CallShapeSnapshot:
        consumed_profile = consume_resolution_archive_resource_profile(profile)
        if type(value) is not VerifiedResolutionCallShape:
            raise TypeError("closure-issued resolution call shape required")
        snapshot = call_shape_snapshots.get(value)
        if snapshot is None:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_call_shape_not_issued"
            )
        if snapshot.profile_fingerprint != consumed_profile["profile_fingerprint"]:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_call_shape_profile_mismatch"
            )
        return snapshot

    return derive, consume


(
    _derive_resolution_call_shape,
    _consume_resolution_call_shape,
) = _build_call_shape_capabilities(_validate_resolution_call_ledger)
del _build_call_shape_capabilities


def parse_resolution_call_ledger(
    raw: bytes,
    *,
    profile: object,
) -> tuple[Mapping[str, object], VerifiedResolutionCallShape]:
    return _derive_resolution_call_shape(raw, profile=profile)


def consume_resolution_call_shape(
    value: object,
    *,
    profile: object,
) -> Mapping[str, object]:
    snapshot = _consume_resolution_call_shape(value, profile)
    return MappingProxyType(
        {
            "profile_fingerprint": snapshot.profile_fingerprint,
            "planner_count": snapshot.planner_count,
            "evaluator_count": snapshot.evaluator_count,
            "ordered_roles": snapshot.ordered_roles,
            "ordered_indexes": snapshot.ordered_indexes,
            "branch_kinds": snapshot.branch_kinds,
            "terminal_flags": snapshot.terminal_flags,
            "ledger_sha256": snapshot.ledger_sha256,
            "planner_row_sha256": tuple(
                "sha256:" + hashlib.sha256(raw).hexdigest()
                for raw in snapshot.planner_row_bytes
            ),
            "evaluator_row_sha256": tuple(
                "sha256:" + hashlib.sha256(raw).hexdigest()
                for raw in snapshot.evaluator_row_bytes
            ),
        }
    )


def _validate_planner_member_against_shape(
    value: object,
    *,
    snapshot: _CallShapeSnapshot,
    constants: Mapping[str, object],
) -> None:
    planner_returned_count = sum(
        1
        for role, branch in zip(
            snapshot.ordered_roles,
            snapshot.branch_kinds,
            strict=True,
        )
        if role == "planner" and branch == "response"
    )
    if (
        type(value) is not dict
        or set(value) != _PLANNER_MEMBER_FIELDS
        or value.get("schema")
        != "rook.lm9b_p.governed_resolution_planner_session:v1"
        or type(value.get("calls")) is not list
        or type(value.get("turns")) is not list
        or type(value.get("call_count")) is not int
        or value["call_count"] != snapshot.planner_count
        or len(value["calls"]) != snapshot.planner_count
        or len(value["turns"]) != planner_returned_count
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_planner_member_shape_invalid"
        )
    observed_rows = tuple(_canonical_bytes(row) for row in value["calls"])
    if observed_rows != snapshot.planner_row_bytes:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_planner_member_ledger_mismatch"
        )
    for turn in value["turns"]:
        _bounded_canonical_size(
            turn,
            ceiling=int(constants["turn_summary_bytes"]),
            rejection_id="resolution_archive_turn_summary_bytes_exceeded",
        )


def _evaluator_ledger_projection(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "call_index": row["call_index"],
        "dispatched_request_b64": base64.b64encode(
            str(row["canonical_request_json"]).encode("utf-8")
        ).decode("ascii"),
        "provider_claimed_raw_request_b64": row.get(
            "provider_claimed_raw_request_b64"
        ),
        "provider_raw_error_b64": row.get("provider_raw_error_b64"),
        "raw_response_b64": row.get("raw_response_b64"),
        "assistant_message": row.get("assistant_message"),
        "usage": row.get("usage"),
        "provider_metadata": row.get("provider_metadata"),
    }


def _validate_evaluator_member_against_shape(
    value: object,
    *,
    snapshot: _CallShapeSnapshot,
    constants: Mapping[str, object],
) -> None:
    if (
        snapshot.evaluator_count != 1
        or len(snapshot.evaluator_row_bytes) != 1
        or type(value) is not dict
        or set(value) != _EVALUATOR_MEMBER_FIELDS
        or value.get("schema")
        != "rook.lm9b_p.governed_resolution_evaluator:v1"
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_evaluator_member_shape_invalid"
        )
    row = PLANNER_SUPPORT.parse_archive_json(snapshot.evaluator_row_bytes[0])
    if type(row) is not dict:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_evaluator_member_shape_invalid"
        )
    expected_projection = _evaluator_ledger_projection(row)
    observed_projection = {
        key: value[key] for key in expected_projection
    }
    if _canonical_bytes(observed_projection) != _canonical_bytes(
        expected_projection
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_evaluator_member_ledger_mismatch"
        )
    termination = value.get("termination")
    if row["outcome"] == "returned":
        compatible = termination in {"valid_recommendation", "malformed"}
    else:
        compatible = termination in {"provider_failure", "timeout"}
    if not compatible:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_evaluator_member_termination_mismatch"
        )
    parsed_result = {
        "termination": termination,
        "recommendation": value.get("recommendation"),
        "evidence": value.get("evidence"),
        "quiescent": value.get("quiescent"),
    }
    if (
        type(parsed_result["termination"]) is not str
        or (
            parsed_result["recommendation"] is not None
            and type(parsed_result["recommendation"]) is not str
        )
        or type(parsed_result["evidence"]) is not list
        or type(parsed_result["quiescent"]) is not bool
    ):
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_evaluator_result_shape_invalid"
        )
    _bounded_canonical_size(
        parsed_result,
        ceiling=int(constants["evaluator_parsed_result_bytes"]),
        rejection_id="resolution_archive_evaluator_result_bytes_exceeded",
    )


def parse_resolution_archive_member(
    raw: bytes,
    *,
    path: str,
    profile: object,
    call_shape: object | None = None,
) -> object:
    if path == "call-ledger.json":
        value, _shape = parse_resolution_call_ledger(raw, profile=profile)
        return value
    dynamic = _MEMBER_BY_PATH.get(path, {}).get("formula_id") in {
        "planner_session_v1",
        "evaluator_member_v1",
    }
    if dynamic and call_shape is None:
        raise TypeError("resolution archive dynamic member requires call shape")
    if dynamic and path == "evaluator.json":
        snapshot = _consume_resolution_call_shape(call_shape, profile)
        if snapshot.evaluator_count != 1:
            raise ResolutionArchiveEvidenceError(
                "resolution_archive_evaluator_member_shape_invalid"
            )
    preparse_ceiling = resolution_member_ceiling(
        path=path,
        profile=profile,
        call_shape=call_shape,
        preparse=True,
    )
    value = _parse_archive_with_ceiling(raw, preparse_ceiling)
    actual_ceiling = resolution_member_ceiling(
        path=path,
        profile=profile,
        call_shape=call_shape,
        preparse=not dynamic,
    )
    if len(raw) > actual_ceiling:
        raise ResolutionArchiveEvidenceError(
            "resolution_archive_member_bytes_exceeded"
        )
    if dynamic:
        snapshot = _consume_resolution_call_shape(call_shape, profile)
        profile_value = consume_resolution_archive_resource_profile(profile)
        constants = profile_value["constants"]
        assert isinstance(constants, Mapping)
        if path == "planner-session.json":
            _validate_planner_member_against_shape(
                value,
                snapshot=snapshot,
                constants=constants,
            )
        else:
            _validate_evaluator_member_against_shape(
                value,
                snapshot=snapshot,
                constants=constants,
            )
    return value


__all__ = (
    "CHECKPOINT_SCHEMA_ID",
    "MAX_EVALUATOR_CALLS",
    "MAX_PLANNER_CALLS",
    "PROFILE_FINGERPRINT",
    "PROFILE_ID",
    "PROFILE_SCHEMA_ID",
    "RESOLUTION_ARCHIVE_MEMBERS",
    "ResolutionArchiveEvidenceError",
    "VerifiedResolutionArchiveResourceProfile",
    "VerifiedResolutionCallShape",
    "admit_resolution_archive_resource_profile",
    "consume_resolution_archive_resource_profile",
    "consume_resolution_call_shape",
    "parse_resolution_archive_member",
    "parse_resolution_call_ledger",
    "resolution_call_row_ceiling",
    "resolution_evaluator_member_ceiling",
    "resolution_member_ceiling",
    "validate_resolution_call_field_bounds",
)
