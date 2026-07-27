from __future__ import annotations

import base64
import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MCP_SRC = ROOT / "mcp_server" / "src"
for entry in (SCRIPTS, MCP_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


import lm9b_p_governed_resolution_archive_evidence as ARCHIVE_EVIDENCE
import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT


PROFILE_PATH = (
    SCRIPTS
    / "lm9b_p_governed_resolution_contracts"
    / "archive_evidence_resource_profile.json"
)


def _profile() -> object:
    return ARCHIVE_EVIDENCE.admit_resolution_archive_resource_profile(
        PROFILE_PATH.read_bytes()
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _planner_row(
    *,
    call_index: int = 0,
    canonical_request_json: str = "{}",
    assistant_message: object | None = None,
) -> dict[str, object]:
    if assistant_message is None:
        assistant_message = {"role": "assistant"}
    return {
        "schema": "rook.lm9b_p.governed_resolution_call:v1",
        "call_index": call_index,
        "role": "planner",
        "request_raw_sha256": "sha256:request",
        "preceding_transcript_fingerprint": "sha256:transcript",
        "provider_timeout_s": 180.0,
        "controller_deadline_state": {"turn_index": call_index + 1},
        "role_contract_fingerprint": "sha256:role",
        "dispatch_marker_raw_sha256": "sha256:dispatch",
        "canonical_request_json": canonical_request_json,
        "provider_claimed_raw_request_b64": "e30=",
        "provider_claimed_raw_request_sha256": "sha256:adapter",
        "provider_raw_error_b64": None,
        "provider_raw_error_sha256": None,
        "raw_response_b64": "e30=",
        "raw_response_sha256": "sha256:response",
        "assistant_message": assistant_message,
        "usage": {},
        "provider_metadata": {},
        "outcome": "returned",
        "exception_type": None,
        "failure_type": None,
        "elapsed_ms": 1,
        "terminal": True,
    }


def _evaluator_row(*, call_index: int = 1) -> dict[str, object]:
    row = _planner_row(call_index=call_index)
    row["role"] = "planner_evaluator"
    row["controller_deadline_state"] = {"evaluator_call_index": 1}
    return row


def _error_row(*, role: str = "planner", call_index: int = 0) -> dict[str, object]:
    row = _planner_row(call_index=call_index)
    row.update(
        {
            "role": role,
            "provider_raw_error_b64": "e30=",
            "provider_raw_error_sha256": "sha256:error",
            "raw_response_b64": None,
            "raw_response_sha256": None,
            "assistant_message": None,
            "usage": None,
            "provider_metadata": None,
            "outcome": "raised",
            "exception_type": "ProviderCallFailure",
            "failure_type": "provider_failure",
        }
    )
    return row


def _ledger(*rows: dict[str, object]) -> bytes:
    return _canonical_bytes(
        {
            "schema": "rook.lm9b_p.governed_resolution_call_ledger:v1",
            "calls": list(rows),
        }
    )


def _planner_member(*rows: dict[str, object]) -> bytes:
    return _canonical_bytes(
        {
            "schema": "rook.lm9b_p.governed_resolution_planner_session:v1",
            "termination": "mechanically_accepted",
            "call_count": len(rows),
            "final_recipe_raw_sha256": "sha256:recipe",
            "calls": list(rows),
            "turns": [
                {
                    "turn_index": index + 1,
                    "raw_response_sha256": "sha256:response",
                    "tool_arguments_sha256": "sha256:tool",
                    "gate_status": "accepted",
                    "usage": {},
                    "elapsed_ms": 1,
                }
                for index, _row in enumerate(rows)
            ],
        }
    )


def _evaluator_member(
    row: dict[str, object],
    *,
    termination: str = "valid_recommendation",
) -> bytes:
    return _canonical_bytes(
        {
            "schema": "rook.lm9b_p.governed_resolution_evaluator:v1",
            "call_index": row["call_index"],
            "dispatched_request_b64": base64.b64encode(
                str(row["canonical_request_json"]).encode("utf-8")
            ).decode("ascii"),
            "provider_claimed_raw_request_b64": row[
                "provider_claimed_raw_request_b64"
            ],
            "provider_raw_error_b64": row["provider_raw_error_b64"],
            "raw_response_b64": row["raw_response_b64"],
            "assistant_message": row["assistant_message"],
            "usage": row["usage"],
            "provider_metadata": row["provider_metadata"],
            "termination": termination,
            "recommendation": (
                "semantically_faithful"
                if termination == "valid_recommendation"
                else None
            ),
            "evidence": [],
            "quiescent": True,
        }
    )


def _capture(callable_: object) -> object:
    try:
        return ("value", callable_())  # type: ignore[operator]
    except Exception as exc:  # noqa: BLE001 - the corpus compares public behavior
        return ("error", type(exc), str(exc))


def test_task1_profile_is_closed_and_matches_checkpoint_member_map() -> None:
    profile = _profile()
    value = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(profile)

    assert value["profile_fingerprint"] == ARCHIVE_EVIDENCE.PROFILE_FINGERPRINT
    assert {
        row["path"]: row["role"] for row in value["members"]
    } == dict(ARTIFACTS.RESOLUTION_ARCHIVE_MEMBERS)
    assert ARCHIVE_EVIDENCE.resolution_member_ceiling(
        path="call-ledger.json",
        profile=profile,
        preparse=True,
    ) == 345_068_924
    with pytest.raises(TypeError, match="closure-issued"):
        ARCHIVE_EVIDENCE.VerifiedResolutionArchiveResourceProfile()


def test_task1_call_ledger_issues_shape_for_dependent_member_parsing() -> None:
    profile = _profile()
    row = _planner_row()
    ledger, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(row),
        profile=profile,
    )
    snapshot = ARCHIVE_EVIDENCE.consume_resolution_call_shape(
        shape,
        profile=profile,
    )

    assert len(ledger["calls"]) == 1
    assert snapshot["planner_count"] == 1
    assert snapshot["evaluator_count"] == 0
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        _planner_member(row),
        path="planner-session.json",
        profile=profile,
        call_shape=shape,
    )["calls"] == [row]
    with pytest.raises(TypeError, match="closure-issued"):
        ARCHIVE_EVIDENCE.VerifiedResolutionCallShape()


@pytest.mark.parametrize(
    "raw",
    (
        b"{}",
        b"[]",
        b'{"float":0.0,"unicode":"\\u03bb"}',
        b'{"a":1,"a":2}',
        b"\xef\xbb\xbf{}",
        b"\xff",
        b'{"n":NaN}',
        b'{"n":1e999}',
        b'{"n":' + b"1" * 1025 + b"}",
        b'{"unterminated":',
    ),
)
def test_task2_under_limit_parser_is_behaviorally_identical(raw: bytes) -> None:
    profile = _profile()
    assert _capture(lambda: PLANNER_SUPPORT.parse_archive_json(raw)) == _capture(
        lambda: ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            raw,
            path="source.json",
            profile=profile,
        )
    )


@pytest.mark.parametrize("depth", (63, 64, 65))
def test_task2_depth_vectors_match_historical_parser(depth: int) -> None:
    raw = ("[" * depth + "0" + "]" * depth).encode("ascii")
    profile = _profile()
    assert _capture(lambda: PLANNER_SUPPORT.parse_archive_json(raw)) == _capture(
        lambda: ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            raw,
            path="source.json",
            profile=profile,
        )
    )


def _json_string_of_exact_size(size: int) -> tuple[bytes, str]:
    payload = "x" * (size - 2)
    return (('"' + payload + '"').encode("ascii"), payload)


def test_task2_exact_historical_limit_matches_and_plus_one_diverges() -> None:
    profile = _profile()
    exact_raw, exact_value = _json_string_of_exact_size(
        PLANNER_SUPPORT.MAX_RECIPE_BYTES
    )
    assert PLANNER_SUPPORT.parse_archive_json(exact_raw) == exact_value
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        exact_raw,
        path="source.json",
        profile=profile,
    ) == exact_value

    over_raw, over_value = _json_string_of_exact_size(
        PLANNER_SUPPORT.MAX_RECIPE_BYTES + 1
    )
    with pytest.raises(
        PLANNER_SUPPORT.StrictJsonError,
        match="recipe_input_bytes_exceeded",
    ):
        PLANNER_SUPPORT.parse_archive_json(over_raw)
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        over_raw,
        path="instrument.json",
        profile=profile,
    ) == over_value
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_member_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            over_raw,
            path="candidate-recipe.json",
            profile=profile,
        )


def test_task2_every_fixed_member_uses_its_path_specific_exact_ceiling() -> None:
    profile = _profile()
    profile_value = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )
    for member in profile_value["members"]:
        if member["formula_id"] != "fixed_member_v1":
            continue
        ceiling = int(member["fixed_ceiling_bytes"])
        assert ARCHIVE_EVIDENCE.resolution_member_ceiling(
            path=member["path"],
            profile=profile,
            preparse=True,
        ) == ceiling
        exact, expected = _json_string_of_exact_size(ceiling)
        assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            exact,
            path=member["path"],
            profile=profile,
        ) == expected
        with pytest.raises(
            ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
            match="resolution_archive_member_bytes_exceeded",
        ):
            ARCHIVE_EVIDENCE.parse_resolution_archive_member(
                exact + b" ",
                path=member["path"],
                profile=profile,
            )

    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_member_path_unknown",
    ):
        ARCHIVE_EVIDENCE.resolution_member_ceiling(
            path="unknown.json",
            profile=profile,
            preparse=True,
        )


def test_task2_actual_count_aggregate_limits_apply_at_exact_byte_boundary() -> None:
    profile = _profile()
    row = _planner_row()
    _value, baseline_shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(row),
        profile=profile,
    )
    ledger_ceiling = ARCHIVE_EVIDENCE.resolution_member_ceiling(
        path="call-ledger.json",
        profile=profile,
        call_shape=baseline_shape,
        preparse=False,
    )
    ledger_raw = _ledger(row)
    exact_ledger = ledger_raw + b" " * (ledger_ceiling - len(ledger_raw))
    _value, exact_shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        exact_ledger,
        profile=profile,
    )
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_member_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
            exact_ledger + b" ",
            profile=profile,
        )

    planner_ceiling = ARCHIVE_EVIDENCE.resolution_member_ceiling(
        path="planner-session.json",
        profile=profile,
        call_shape=exact_shape,
        preparse=False,
    )
    planner_raw = _planner_member(row)
    exact_planner = planner_raw + b" " * (planner_ceiling - len(planner_raw))
    ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        exact_planner,
        path="planner-session.json",
        profile=profile,
        call_shape=exact_shape,
    )
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_member_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            exact_planner + b" ",
            path="planner-session.json",
            profile=profile,
            call_shape=exact_shape,
        )


def test_task2_constituent_request_bound_precedes_aggregate_ceiling() -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    row = _planner_row(
        canonical_request_json="x"
        * (int(constants["planner_canonical_request_base_bytes"]) + 1)
    )
    assert len(_ledger(row)) < ARCHIVE_EVIDENCE.resolution_member_ceiling(
        path="call-ledger.json",
        profile=profile,
        preparse=True,
    )
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_canonical_request_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
            _ledger(row),
            profile=profile,
        )


def test_task2_planner_member_cannot_borrow_same_shape_from_another_ledger() -> None:
    profile = _profile()
    row = _planner_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(row),
        profile=profile,
    )
    changed = copy.deepcopy(row)
    changed["canonical_request_json"] = '{"different":true}'

    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_planner_member_ledger_mismatch",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _planner_member(changed),
            path="planner-session.json",
            profile=profile,
            call_shape=shape,
        )


def test_task2_evaluator_member_exactly_projects_authenticated_ledger_row() -> None:
    profile = _profile()
    planner = _planner_row()
    evaluator = _evaluator_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, evaluator),
        profile=profile,
    )
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        _evaluator_member(evaluator),
        path="evaluator.json",
        profile=profile,
        call_shape=shape,
    )["call_index"] == 1

    changed = json.loads(_evaluator_member(evaluator))
    changed["provider_claimed_raw_request_b64"] = "e2NoYW5nZWR9"
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_evaluator_member_ledger_mismatch",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _canonical_bytes(changed),
            path="evaluator.json",
            profile=profile,
            call_shape=shape,
        )


def test_task2_evaluator_member_limit_is_exact_and_count_derived() -> None:
    profile = _profile()
    planner = _planner_row()
    evaluator = _evaluator_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, evaluator),
        profile=profile,
    )
    ceiling = ARCHIVE_EVIDENCE.resolution_evaluator_member_ceiling(
        evaluator_count=1,
        profile=profile,
    )
    member = _evaluator_member(evaluator)
    exact = member + b" " * (ceiling - len(member))
    ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        exact,
        path="evaluator.json",
        profile=profile,
        call_shape=shape,
    )
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_member_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            exact + b" ",
            path="evaluator.json",
            profile=profile,
            call_shape=shape,
        )


def test_task2_indexed_formula_arithmetic_is_exact() -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    increment = (
        int(constants["planner_assistant_projection_bytes"])
        + int(constants["planner_feedback_projection_bytes"])
        + int(constants["planner_request_turn_framing_bytes"])
    )
    previous_request = int(constants["planner_canonical_request_base_bytes"])
    previous_row = ARCHIVE_EVIDENCE.resolution_call_row_ceiling(
        role="planner",
        ordinal=1,
        profile=profile,
    )
    for turn in range(1, ARCHIVE_EVIDENCE.MAX_PLANNER_CALLS):
        next_request = previous_request + increment
        next_row = ARCHIVE_EVIDENCE.resolution_call_row_ceiling(
            role="planner",
            ordinal=turn + 1,
            profile=profile,
        )
        # Only request JSON escaping and adapter base64 change between rows.
        expected_delta = (
            int(constants["json_string_escape_multiplier"]) * increment
            + 4
            * (
                (
                    (
                        previous_request
                        + increment
                        + int(constants["adapter_request_overhead_bytes"])
                        + 2
                    )
                    // 3
                )
            )
            - 4
            * (
                (
                    (
                        previous_request
                        + int(constants["adapter_request_overhead_bytes"])
                        + 2
                    )
                    // 3
                )
            )
        )
        assert next_row - previous_row == expected_delta
        previous_request = next_request
        previous_row = next_row

    assert ARCHIVE_EVIDENCE.resolution_call_row_ceiling(
        role="planner_evaluator",
        ordinal=1,
        profile=profile,
    ) == 33_772_890
    assert ARCHIVE_EVIDENCE.resolution_evaluator_member_ceiling(
        evaluator_count=1,
        profile=profile,
    ) == 35_083_610
    assert ARCHIVE_EVIDENCE.resolution_member_ceiling(
        path="call-ledger.json",
        profile=profile,
        preparse=True,
    ) == 345_068_924


@pytest.mark.parametrize("turn", range(1, 7))
def test_task2_every_planner_request_turn_has_an_exact_field_bound(turn: int) -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    request_ceiling = int(constants["planner_canonical_request_base_bytes"]) + (
        turn - 1
    ) * (
        int(constants["planner_assistant_projection_bytes"])
        + int(constants["planner_feedback_projection_bytes"])
        + int(constants["planner_request_turn_framing_bytes"])
    )
    exact = _planner_row(
        call_index=turn - 1,
        canonical_request_json="x" * request_ceiling,
    )
    ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
        row=exact,
        profile=profile,
    )
    over = copy.deepcopy(exact)
    over["canonical_request_json"] += "x"
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_canonical_request_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
            row=over,
            profile=profile,
        )


@pytest.mark.parametrize(
    ("field", "constant", "rejection"),
    (
        (
            "raw_response_b64",
            "planner_raw_response_bytes",
            "resolution_archive_raw_response_bytes_exceeded",
        ),
        (
            "assistant_message",
            "planner_assistant_projection_bytes",
            "resolution_archive_assistant_projection_bytes_exceeded",
        ),
        ("usage", "usage_bytes", "resolution_archive_usage_bytes_exceeded"),
        (
            "provider_metadata",
            "provider_metadata_bytes",
            "resolution_archive_provider_metadata_bytes_exceeded",
        ),
    ),
)
def test_task2_returned_field_bounds_refuse_plus_one(
    field: str,
    constant: str,
    rejection: str,
) -> None:
    profile = _profile()
    ceiling = int(
        ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(profile)[
            "constants"
        ][constant]
    )
    row = _planner_row()
    if field == "raw_response_b64":
        row[field] = base64.b64encode(b"x" * ceiling).decode("ascii")
    else:
        # {"x":""} occupies eight canonical bytes.
        row[field] = {"x": "x" * (ceiling - 8)}
    ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
        row=row,
        profile=profile,
    )
    if field == "raw_response_b64":
        row[field] = base64.b64encode(b"x" * (ceiling + 1)).decode("ascii")
    else:
        row[field] = {"x": "x" * (ceiling - 7)}
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match=rejection,
    ):
        ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
            row=row,
            profile=profile,
        )


def test_task2_adapter_and_error_field_bounds_refuse_plus_one() -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    row = _planner_row()
    adapter_ceiling = int(constants["planner_canonical_request_base_bytes"]) + int(
        constants["adapter_request_overhead_bytes"]
    )
    row["provider_claimed_raw_request_b64"] = base64.b64encode(
        b"x" * adapter_ceiling
    ).decode("ascii")
    ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
        row=row,
        profile=profile,
    )
    row["provider_claimed_raw_request_b64"] = base64.b64encode(
        b"x" * (adapter_ceiling + 1)
    ).decode("ascii")
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_adapter_request_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
            row=row,
            profile=profile,
        )

    error = _error_row()
    error["provider_raw_error_b64"] = base64.b64encode(
        b"x" * int(constants["planner_raw_error_bytes"])
    ).decode("ascii")
    ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
        row=error,
        profile=profile,
    )
    error["provider_raw_error_b64"] = base64.b64encode(
        b"x" * (int(constants["planner_raw_error_bytes"]) + 1)
    ).decode("ascii")
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_raw_error_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
            row=error,
            profile=profile,
        )


def test_task2_evaluator_fields_use_their_own_closed_limits() -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    request_ceiling = int(constants["evaluator_canonical_request_bytes"])
    row = _evaluator_row(call_index=6)
    row["canonical_request_json"] = "x" * request_ceiling
    row["raw_response_b64"] = base64.b64encode(
        b"x" * int(constants["evaluator_raw_response_bytes"])
    ).decode("ascii")
    row["assistant_message"] = {
        "x": "x" * (int(constants["evaluator_assistant_projection_bytes"]) - 8)
    }
    ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
        row=row,
        profile=profile,
    )

    for field, value, rejection in (
        (
            "canonical_request_json",
            "x" * (request_ceiling + 1),
            "resolution_archive_canonical_request_bytes_exceeded",
        ),
        (
            "raw_response_b64",
            base64.b64encode(
                b"x" * (int(constants["evaluator_raw_response_bytes"]) + 1)
            ).decode("ascii"),
            "resolution_archive_raw_response_bytes_exceeded",
        ),
        (
            "assistant_message",
            {
                "x": "x"
                * int(constants["evaluator_assistant_projection_bytes"])
            },
            "resolution_archive_assistant_projection_bytes_exceeded",
        ),
    ):
        changed = copy.deepcopy(row)
        changed[field] = value
        with pytest.raises(
            ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
            match=rejection,
        ):
            ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
                row=changed,
                profile=profile,
            )


def test_task2_fixed_row_projection_has_an_independent_bound() -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    ceiling = int(constants["row_framing_bytes"])
    variable_fields = {
        "canonical_request_json",
        "provider_claimed_raw_request_b64",
        "provider_raw_error_b64",
        "raw_response_b64",
        "assistant_message",
        "usage",
        "provider_metadata",
    }
    row = _planner_row()
    row["controller_deadline_state"] = {"padding": ""}
    projection = {
        key: row[key] for key in sorted(set(row) - variable_fields)
    }
    padding = ceiling - len(_canonical_bytes(projection))
    row["controller_deadline_state"] = {"padding": "x" * padding}
    assert len(
        _canonical_bytes(
            {key: row[key] for key in sorted(set(row) - variable_fields)}
        )
    ) == ceiling
    ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
        row=row,
        profile=profile,
    )
    row["controller_deadline_state"]["padding"] += "x"
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_fixed_row_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
            row=row,
            profile=profile,
        )


@pytest.mark.parametrize(
    ("field", "value", "rejection"),
    (
        (
            "provider_claimed_raw_request_b64",
            "not-base64",
            "resolution_archive_adapter_request_base64_invalid",
        ),
        (
            "raw_response_b64",
            "e30",
            "resolution_archive_raw_response_base64_invalid",
        ),
    ),
)
def test_task2_base64_fields_require_canonical_rfc4648(
    field: str,
    value: str,
    rejection: str,
) -> None:
    profile = _profile()
    row = _planner_row()
    row[field] = value
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match=rejection,
    ):
        ARCHIVE_EVIDENCE.validate_resolution_call_field_bounds(
            row=row,
            profile=profile,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "both_branches",
        "neither_branch",
        "raised_with_response",
        "unknown_outcome",
        "partial_error",
    ),
)
def test_task2_branch_exclusivity_precedes_call_shape_issuance(
    mutation: str,
) -> None:
    profile = _profile()
    row = _planner_row()
    if mutation == "both_branches":
        row["provider_raw_error_b64"] = "e30="
        row["provider_raw_error_sha256"] = "sha256:error"
    elif mutation == "neither_branch":
        row["raw_response_b64"] = None
        row["raw_response_sha256"] = None
    elif mutation == "raised_with_response":
        row["outcome"] = "raised"
        row["exception_type"] = "ProviderCallFailure"
        row["failure_type"] = "provider_failure"
    elif mutation == "unknown_outcome":
        row["outcome"] = "unknown"
    else:
        row = _error_row()
        row["provider_raw_error_sha256"] = None
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_call_branch_invalid",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
            _ledger(row),
            profile=profile,
        )


def test_task2_raised_planner_call_has_no_turn_summary() -> None:
    profile = _profile()
    row = _error_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(row),
        profile=profile,
    )
    member = json.loads(_planner_member(row))
    member["termination"] = "provider_failure"
    member["final_recipe_raw_sha256"] = None
    member["turns"] = []
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        _canonical_bytes(member),
        path="planner-session.json",
        profile=profile,
        call_shape=shape,
    )["turns"] == []


def test_task2_evaluator_absence_and_termination_are_shape_closed() -> None:
    profile = _profile()
    planner = _planner_row()
    _ledger_value, no_evaluator = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner),
        profile=profile,
    )
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_evaluator_member_shape_invalid",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _canonical_bytes({}),
            path="evaluator.json",
            profile=profile,
            call_shape=no_evaluator,
        )

    evaluator = _evaluator_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, evaluator),
        profile=profile,
    )
    changed = json.loads(_evaluator_member(evaluator))
    changed["termination"] = "provider_failure"
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_evaluator_member_termination_mismatch",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _canonical_bytes(changed),
            path="evaluator.json",
            profile=profile,
            call_shape=shape,
        )

    raised = _error_row(role="planner_evaluator", call_index=1)
    _ledger_value, raised_shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, raised),
        profile=profile,
    )
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        _evaluator_member(raised, termination="provider_failure"),
        path="evaluator.json",
        profile=profile,
        call_shape=raised_shape,
    )["termination"] == "provider_failure"


@pytest.mark.parametrize(
    ("field", "value", "rejection"),
    (
        ("recommendation", {}, "resolution_archive_evaluator_result_shape_invalid"),
        ("evidence", {}, "resolution_archive_evaluator_result_shape_invalid"),
        ("quiescent", 1, "resolution_archive_evaluator_result_shape_invalid"),
    ),
)
def test_task2_evaluator_parsed_result_shape_is_closed(
    field: str,
    value: object,
    rejection: str,
) -> None:
    profile = _profile()
    planner = _planner_row()
    evaluator = _evaluator_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, evaluator),
        profile=profile,
    )
    changed = json.loads(_evaluator_member(evaluator))
    changed[field] = value
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match=rejection,
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _canonical_bytes(changed),
            path="evaluator.json",
            profile=profile,
            call_shape=shape,
        )


def test_task2_evaluator_parsed_result_has_exact_independent_bound() -> None:
    profile = _profile()
    constants = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(
        profile
    )["constants"]
    ceiling = int(constants["evaluator_parsed_result_bytes"])
    planner = _planner_row()
    evaluator = _evaluator_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, evaluator),
        profile=profile,
    )
    member = json.loads(_evaluator_member(evaluator))
    member["evidence"] = [{"x": ""}]
    projection = {
        "termination": member["termination"],
        "recommendation": member["recommendation"],
        "evidence": member["evidence"],
        "quiescent": member["quiescent"],
    }
    padding = ceiling - len(_canonical_bytes(projection))
    member["evidence"][0]["x"] = "x" * padding
    assert len(
        _canonical_bytes(
            {
                "termination": member["termination"],
                "recommendation": member["recommendation"],
                "evidence": member["evidence"],
                "quiescent": member["quiescent"],
            }
        )
    ) == ceiling
    ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        _canonical_bytes(member),
        path="evaluator.json",
        profile=profile,
        call_shape=shape,
    )
    member["evidence"][0]["x"] += "x"
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_evaluator_result_bytes_exceeded",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _canonical_bytes(member),
            path="evaluator.json",
            profile=profile,
            call_shape=shape,
        )


@pytest.mark.parametrize(
    "field",
    (
        "dispatched_request_b64",
        "provider_claimed_raw_request_b64",
        "provider_raw_error_b64",
        "raw_response_b64",
        "assistant_message",
        "usage",
        "provider_metadata",
    ),
)
def test_task2_every_evaluator_ledger_projection_is_exact(field: str) -> None:
    profile = _profile()
    planner = _planner_row()
    evaluator = _evaluator_row()
    _ledger_value, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(planner, evaluator),
        profile=profile,
    )
    changed = json.loads(_evaluator_member(evaluator))
    changed[field] = "changed" if changed[field] is not None else "e30="
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_evaluator_member_ledger_mismatch",
    ):
        ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            _canonical_bytes(changed),
            path="evaluator.json",
            profile=profile,
            call_shape=shape,
        )


def test_task2_call_shape_is_unforgeable_and_snapshot_closed() -> None:
    profile = _profile()
    row = _planner_row()
    ledger, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _ledger(row),
        profile=profile,
    )
    original_member = _planner_member(row)
    ledger["calls"][0]["canonical_request_json"] = '{"mutated":true}'
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        original_member,
        path="planner-session.json",
        profile=profile,
        call_shape=shape,
    )["calls"] == [row]

    forged = object.__new__(ARCHIVE_EVIDENCE.VerifiedResolutionCallShape)
    for value in (
        {"planner_count": 1, "evaluator_count": 0},
        forged,
    ):
        with pytest.raises((TypeError, ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError)):
            ARCHIVE_EVIDENCE.consume_resolution_call_shape(
                value,
                profile=profile,
            )
    for copier in (copy.copy, copy.deepcopy):
        with pytest.raises(TypeError, match="closure-issued"):
            copier(shape)

    class ForgedShape(ARCHIVE_EVIDENCE.VerifiedResolutionCallShape):
        pass

    subclassed = object.__new__(ForgedShape)
    with pytest.raises(TypeError, match="closure-issued"):
        ARCHIVE_EVIDENCE.consume_resolution_call_shape(
            subclassed,
            profile=profile,
        )


def test_task2_changed_reclosed_profile_cannot_issue_or_expand_a_shape() -> None:
    value = json.loads(PROFILE_PATH.read_bytes())
    value["constants"]["planner_raw_response_bytes"] += 1
    value["profile_fingerprint"] = PLANNER_SUPPORT.fingerprint_without(
        value,
        "profile_fingerprint",
    )
    with pytest.raises(
        ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
        match="resolution_archive_resource_profile_contract_mismatch",
    ):
        ARCHIVE_EVIDENCE.admit_resolution_archive_resource_profile(
            _canonical_bytes(value) + b"\n"
        )

    assert "_issue_resolution_call_shape" not in vars(ARCHIVE_EVIDENCE)
    assert "_build_call_shape_capabilities" not in vars(ARCHIVE_EVIDENCE)
    assert not any(name.startswith("_issue") for name in ARCHIVE_EVIDENCE.__all__)
