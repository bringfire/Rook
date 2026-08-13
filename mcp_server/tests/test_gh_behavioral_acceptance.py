"""Contract tests for the pure Grasshopper behavioral-acceptance owner."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from rook import gh_behavioral_acceptance as acceptance
from rook import server
from rook.learning import gh_knowledge


SHA_A = "A" * 64
SHA_B = "B" * 64


def _receipt(
    receipt_id: str = "receipt-1",
    *,
    mutation_epoch: int = 1,
    solution_epoch: int | None = None,
    status: str = "pending",
) -> dict:
    ready = status == "ready"
    epoch = solution_epoch if ready else None
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": receipt_id,
        "document_session_id": "document-session-1",
        "mutation_epoch": mutation_epoch,
        "solution_run_epoch": epoch,
        "completed_solution_run_epoch": solution_epoch or 0,
        "status": status,
        "reason": None,
        "completion_signal": "solution_end" if ready else None,
        "issued_at": "2026-08-12T12:00:00.0000000Z",
        "completed_at": "2026-08-12T12:00:01.0000000Z" if ready else None,
    }


def _event(
    sequence: int,
    target: str,
    *,
    ingress: str = "canonical_gateway",
    classification: str = "observational",
    commit_status: str = "none",
    receipt: dict | None = None,
    arguments: dict | None = None,
    data: object | None = None,
) -> dict:
    if classification == "observational":
        evidence = None
    elif target == "gh_edit":
        evidence = {
            "created": 1 if commit_status == "committed" else 0,
            "deleted": 0,
            "values_set": 0,
            "connected": 0,
            "disconnected": 0,
        }
    elif target == "gh_set_script_pins":
        evidence = {"success": True, "target_dispatched": True}
    elif target in {
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
        "gh_update_script",
        "chirp_create",
    }:
        evidence = {
            "component": {"guid": "component-guid", "short_id": None},
            "final_write": {
                "dispatched": commit_status == "committed",
                "success": True if commit_status == "committed" else None,
                "solve_relevant_mutation_committed": True if commit_status == "committed" else None,
            },
        }
    else:
        evidence = {"success": True, "target_dispatched": True}
        if classification == "legacy" and commit_status == "none":
            commit_status = "committed"
    result_data = {} if data is None else data
    if data is None and target == "gh_edit" and isinstance(evidence, dict):
        result_data = {"edit_summary": dict(evidence)}
    elif (
        data is None
        and target in {"gh_set_value", "gh_set_script"}
        and isinstance(evidence, dict)
        and "solve_relevant_mutation_committed" in evidence
    ):
        result_data = {
            "solve_relevant_mutation_committed": evidence[
                "solve_relevant_mutation_committed"
            ]
        }
    elif data is None and target in {
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
        "gh_update_script",
        "chirp_create",
    }:
        result_data = {
            "component_guid": evidence["component"]["guid"],
            "solve_relevant_mutation_committed": evidence["final_write"][
                "solve_relevant_mutation_committed"
            ],
        }
    if receipt is not None:
        assert isinstance(result_data, dict)
        result_data = result_data | {"solve_readiness_receipt": receipt}
    return {
        "sequence": sequence,
        "ingress": ingress,
        "target": target,
        "arguments": arguments or {},
        "result": {"success": True, "data": result_data},
        "exception": None,
        "dispatch": {"status": "dispatched", "target_call_count": 1},
        "mutation": {
            "classification": classification,
            "commit_status": commit_status,
            "commit_evidence": evidence,
            "solve_readiness_receipt": receipt,
        },
    }


def _trace(*events: dict) -> dict:
    return {
        "schema": "rook.gh_authoring_trace:v1",
        "source_closure": {
            "schema": "rook.gh_authoring_source_closure:v1",
            "owner": "prime_transaction_launcher",
            "row_emitter": "prime_rook_adapter",
            "source_event_count": len(events),
            "final_source_sequence": len(events) - 1 if events else None,
            "source_log_sha256": SHA_A,
            "runtime_log_sha256": SHA_B,
            "terminal_marker": "agent_end",
            "closed": True,
        },
        "events": list(events),
    }


def _artifact() -> dict:
    return {
        "schema": "rook.gh_behavioral_acceptance:v1",
        "intent": "Make a row of points.",
        "numeric_tolerance": 0.001,
        "controls": [
            {
                "role": "Start",
                "selector": {"kind": "exact_nickname", "value": "Start"},
                "value_kind": "number",
                "probe_value": 2.0,
            },
            {
                "role": "Step",
                "selector": {"kind": "exact_nickname", "value": "Step"},
                "value_kind": "number",
                "probe_value": 2.0,
            },
            {
                "role": "Count",
                "selector": {"kind": "exact_nickname", "value": "Count"},
                "value_kind": "integer",
                "probe_value": 4,
            },
        ],
        "output": {
            "kind": "terminal_points",
            "require_complete_multiset": True,
            "max_preview_items": 100,
        },
        "criteria": [
            {
                "id": "adjustable_controls_present",
                "predicate": "controls_present",
                "arguments": {"roles": ["Start", "Step", "Count"]},
            },
            {
                "id": "point_count_equals_count",
                "predicate": "point_count_equals_control",
                "arguments": {"role": "Count"},
            },
            {
                "id": "x_sequence",
                "predicate": "axis_values_equal_sequence",
                "arguments": {
                    "axis": "x",
                    "start_role": "Start",
                    "step_role": "Step",
                    "count_role": "Count",
                },
            },
            {
                "id": "y_zero",
                "predicate": "axis_equals_constant",
                "arguments": {"axis": "y", "value": 0.0},
            },
            {
                "id": "z_zero",
                "predicate": "axis_equals_constant",
                "arguments": {"axis": "z", "value": 0.0},
            },
            {
                "id": "no_runtime_errors",
                "predicate": "diagnostics_errors_equal",
                "arguments": {"value": 0},
            },
        ],
    }


def _points(start: float, step: float, count: int) -> list[list[float]]:
    return [[start + index * step, 0.0, 0.0] for index in range(count)]


def _snapshot(
    receipt: dict,
    *,
    start: float = 0.0,
    step: float = 1.0,
    count: int = 3,
) -> dict:
    return {
        "components": [
            {
                "id": "C1",
                "type": "NumberSlider",
                "nick": "Start",
                "value": {"type": "slider", "val": start, "min": -10.0, "max": 10.0},
            },
            {
                "id": "C2",
                "type": "NumberSlider",
                "nick": "Step",
                "value": {"type": "slider", "val": step, "min": -10.0, "max": 10.0},
            },
            {
                "id": "C3",
                "type": "NumberSlider",
                "nick": "Count",
                "value": {"type": "slider", "val": count, "min": 1, "max": 10},
            },
            {"id": "C4", "type": "PointProducer", "nick": "Points"},
        ],
        "flows": ["C1.O0>C4.I0", "C2.O0>C4.I1", "C3.O0>C4.I2"],
        "groups": [],
        "relays": [],
        "diagnostics": {
            "total": 4,
            "errors": 0,
            "warnings": 0,
            "error_ids": [],
            "warning_ids": [],
        },
        "readiness_fence": {
            "readiness_receipt_id": receipt["receipt_id"],
            "document_session_id": receipt["document_session_id"],
            "mutation_epoch": receipt["mutation_epoch"],
            "solution_run_epoch": receipt["solution_run_epoch"],
            "completed_solution_run_epoch": receipt["completed_solution_run_epoch"],
        },
        "behavioral_point_outputs": [
            {
                "component_id": "C4",
                "output_index": 0,
                "output_name": "P",
                "count": count,
                "complete": True,
                "points": _points(start, step, count),
                "error": None,
            }
        ],
    }


def _wait_result(receipt: dict) -> dict:
    return {
        "success": True,
        "data": {
            "schema": "rook.gh_solve_readiness_wait_result:v1",
            "wait_status": "ready",
            "receipt": receipt,
        },
    }


def _snapshot_result(receipt: dict, values: dict[str, float]) -> dict:
    return {
        "success": True,
        "data": _snapshot(
            receipt,
            start=values["Start"],
            step=values["Step"],
            count=int(values["Count"]),
        ),
    }


class _Executor:
    def __init__(self):
        self.values = {"Start": 0.0, "Step": 1.0, "Count": 3}
        self.calls: list[tuple[str, dict]] = []
        self.issued = 1
        self.pending = _receipt()

    async def __call__(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        if name == "gh_wait_for_solve_readiness":
            ready = _receipt(
                self.pending["receipt_id"],
                mutation_epoch=self.pending["mutation_epoch"],
                solution_epoch=self.pending["mutation_epoch"] + 10,
                status="ready",
            )
            return _wait_result(ready)
        if name == "gh_snapshot":
            ready = _receipt(
                self.pending["receipt_id"],
                mutation_epoch=self.pending["mutation_epoch"],
                solution_epoch=self.pending["mutation_epoch"] + 10,
                status="ready",
            )
            return _snapshot_result(ready, self.values)
        if name == "gh_set_value":
            assert set(arguments) == {"guid", "value"}
            component = arguments["guid"]
            role = {"C1": "Start", "C2": "Step", "C3": "Count"}[component]
            self.values[role] = arguments["value"]
            self.issued += 1
            self.pending = _receipt(
                f"receipt-{self.issued}", mutation_epoch=self.issued
            )
            return {
                "success": True,
                "data": {
                    "solve_relevant_mutation_committed": True,
                    "solve_readiness_receipt": self.pending,
                },
            }
        raise AssertionError(name)


def test_public_surface_is_exact_and_module_has_no_runtime_owners():
    assert acceptance.__all__ == (
        "canonical_json_bytes",
        "append_source_event",
        "append_canonical_gateway_source_event",
        "seal_prime_source_log",
        "seal_direct_source_log",
        "normalize_authoring_trace",
        "validate_acceptance_artifact",
        "run_behavioral_probe",
        "evaluate_behavioral_probe",
    )
    source = Path(acceptance.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "stdio_client",
        "McpIntegration",
        "subprocess",
        "Popen",
        "asyncio.sleep",
        "resolve_target",
        "Component_Series",
        "Construct Point",
    ):
        assert forbidden not in source


def test_canonical_json_bytes_are_strict_sorted_compact_utf8_with_one_lf():
    assert acceptance.canonical_json_bytes({"z": "é", "a": [1]}) == (
        b'{"a":[1],"z":"\xc3\xa9"}\n'
    )
    with pytest.raises(ValueError):
        acceptance.canonical_json_bytes({"bad": float("nan")})


def test_public_gateway_appender_owns_sequence_and_mutation_projection(tmp_path):
    source_path = tmp_path / "source.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    receipt = _receipt()
    expected = _event(
        0,
        "gh_edit",
        classification="terminal",
        commit_status="committed",
        receipt=receipt,
        arguments={"epoch": 1, "create": []},
    )

    actual = acceptance.append_canonical_gateway_source_event(
        source_path,
        "gh_edit",
        {"epoch": 1, "create": []},
        result=expected["result"],
    )

    assert actual == expected
    rows = [json.loads(line) for line in source_path.read_text().splitlines()]
    assert rows == [
        {
            "schema": "rook.gh_authoring_source_log:v1",
            "row_emitter": "prime_rook_adapter",
        },
        expected,
    ]


def test_public_gateway_appender_owns_exception_projection(tmp_path):
    source_path = tmp_path / "source.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    error = RuntimeError("boom")

    actual = acceptance.append_canonical_gateway_source_event(
        source_path,
        "gh_edit",
        {"epoch": 1},
        exception=error,
    )

    assert actual == {
        "sequence": 0,
        "ingress": "canonical_gateway",
        "target": "gh_edit",
        "arguments": {"epoch": 1},
        "result": None,
        "exception": {"type": "builtins.RuntimeError", "message": "boom"},
        "dispatch": {"status": "unknown", "target_call_count": None},
        "mutation": {
            "classification": "unknown",
            "commit_status": "unknown",
            "commit_evidence": None,
            "solve_readiness_receipt": None,
        },
    }


def test_public_gateway_appender_refuses_non_prime_source_owner(tmp_path):
    source_path = tmp_path / "source.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "direct_transaction_wrapper",
            }
        )
    )

    with pytest.raises(ValueError, match="invalid_gateway_source_owner"):
        acceptance.append_canonical_gateway_source_event(
            source_path,
            "gh_snapshot",
            {},
            result={"success": True, "data": {}},
        )
    assert len(source_path.read_text().splitlines()) == 1


def test_append_and_prime_seal_require_complete_runtime_custody(tmp_path):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "prime_rook_adapter"}
        )
    )
    event = _event(0, "gh_snapshot")
    acceptance.append_source_event(source_path, event)
    runtime_path.write_bytes(
        acceptance.canonical_json_bytes({"type": "message"})
        + acceptance.canonical_json_bytes({"type": "agent_end"})
    )
    process_state = {
        "terminated": True,
        "stdout_eof": True,
        "owned_child_pids": [],
        "exit_code": 0,
    }

    closure = acceptance.seal_prime_source_log(source_path, runtime_path, process_state)
    assert closure["source_event_count"] == 1
    assert closure["final_source_sequence"] == 0
    assert acceptance.normalize_authoring_trace(source_path, runtime_path)["events"] == [event]


def _retained_prime_housekeeping_suffix() -> list[dict]:
    state = {
        "role": "custom",
        "customType": "ipython_state",
        "content": "<ipython_state>\nretained kernel state\n</ipython_state>",
        "display": False,
        "timestamp": 1786621406964,
    }
    return [
        {"type": "message_start", "message": state},
        {"type": "message_end", "message": state},
        {
            "type": "compaction_end",
            "reason": "threshold",
            "result": {
                "summary": "retained summary",
                "firstKeptEntryId": "7429c411",
                "tokensBefore": 112121,
                "details": {"readFiles": [], "modifiedFiles": []},
            },
            "aborted": False,
            "willRetry": False,
        },
    ]


def test_prime_seal_accepts_agent_end_as_final_semantic_event_with_retained_suffix(tmp_path):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    runtime_rows = [
        {"type": "message"},
        {"type": "agent_end"},
        *_retained_prime_housekeeping_suffix(),
    ]
    runtime_payload = b"".join(
        acceptance.canonical_json_bytes(row) for row in runtime_rows
    )
    runtime_path.write_bytes(runtime_payload)

    closure = acceptance.seal_prime_source_log(
        source_path,
        runtime_path,
        {
            "terminated": True,
            "stdout_eof": True,
            "owned_child_pids": [],
            "exit_code": 0,
        },
    )

    assert closure["terminal_marker"] == "agent_end"
    assert closure["runtime_log_sha256"] == hashlib.sha256(
        runtime_payload
    ).hexdigest().upper()


def test_prime_runtime_preserves_valid_noncanonical_jsonl_bytes(tmp_path):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    runtime_payload = b'{"type": "agent_end", "messages": []}\n'
    runtime_path.write_bytes(runtime_payload)

    closure = acceptance.seal_prime_source_log(
        source_path,
        runtime_path,
        {
            "terminated": True,
            "stdout_eof": True,
            "owned_child_pids": [],
            "exit_code": 0,
        },
    )

    assert closure["runtime_log_sha256"] == hashlib.sha256(
        runtime_payload
    ).hexdigest().upper()
    assert acceptance.normalize_authoring_trace(source_path, runtime_path)[
        "source_closure"
    ] == closure


@pytest.mark.parametrize(
    "runtime_payload",
    [
        b'{"type":"agent_end","type":"agent_end"}\n',
        b'\xef\xbb\xbf{"type":"agent_end"}\n',
        b'{"type":"agent_end"}',
        b'{"type":"agent_end"}\n\n',
        b'{"type":NaN}\n',
        b'{"type":"message","value":1e999}\n{"type":"agent_end"}\n',
    ],
)
def test_prime_runtime_still_refuses_malformed_or_ambiguous_jsonl(
    tmp_path, runtime_payload
):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    runtime_path.write_bytes(runtime_payload)

    with pytest.raises(ValueError):
        acceptance.seal_prime_source_log(
            source_path,
            runtime_path,
            {
                "terminated": True,
                "stdout_eof": True,
                "owned_child_pids": [],
                "exit_code": 0,
            },
        )


@pytest.mark.parametrize(
    "hostile_suffix",
    [
        [{"type": "turn_start"}],
        [{"type": "message_start", "message": {"role": "assistant"}}],
        [{"type": "message_end", "message": {"role": "user"}}],
        [{"type": "tool_execution_start", "toolName": "ipython"}],
        [{"type": "tool_execution_end", "toolName": "ipython"}],
        [{"type": "mutation", "target": "gh_edit"}],
        [{"type": "unknown_housekeeping"}],
        [{"type": "agent_end"}],
        [_retained_prime_housekeeping_suffix()[0]],
        [
            _retained_prime_housekeeping_suffix()[0],
            _retained_prime_housekeeping_suffix()[1]
            | {"message": {"role": "custom", "customType": "ipython_state"}},
        ],
    ],
)
def test_prime_seal_refuses_hostile_or_unclosed_post_terminal_suffix(
    tmp_path, hostile_suffix
):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(
        acceptance.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    runtime_rows = [{"type": "agent_end"}, *hostile_suffix]
    runtime_path.write_bytes(
        b"".join(acceptance.canonical_json_bytes(row) for row in runtime_rows)
    )

    with pytest.raises(ValueError, match="invalid_prime_terminal_marker"):
        acceptance.seal_prime_source_log(
            source_path,
            runtime_path,
            {
                "terminated": True,
                "stdout_eof": True,
                "owned_child_pids": [],
                "exit_code": 0,
            },
        )
    assert b'"type":"closure"' not in source_path.read_bytes()


@pytest.mark.parametrize(
    ("runtime_rows", "state"),
    [
        ([{"type": "message"}], {"terminated": True, "stdout_eof": True, "owned_child_pids": [], "exit_code": 1}),
        ([{"type": "agent_end"}, {"type": "agent_end"}], {"terminated": True, "stdout_eof": True, "owned_child_pids": [], "exit_code": 0}),
        ([{"type": "agent_end"}, {"type": "message"}], {"terminated": True, "stdout_eof": True, "owned_child_pids": [], "exit_code": 0}),
        ([{"type": "agent_end"}], {"terminated": False, "stdout_eof": True, "owned_child_pids": [], "exit_code": None}),
        ([{"type": "agent_end"}], {"terminated": True, "stdout_eof": False, "owned_child_pids": [], "exit_code": 0}),
        ([{"type": "agent_end"}], {"terminated": True, "stdout_eof": True, "owned_child_pids": [44], "exit_code": 0}),
    ],
)
def test_prime_seal_refuses_incomplete_terminal_ownership(tmp_path, runtime_rows, state):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "prime_rook_adapter"}))
    runtime_path.write_bytes(b"".join(acceptance.canonical_json_bytes(row) for row in runtime_rows))
    with pytest.raises(ValueError):
        acceptance.seal_prime_source_log(source_path, runtime_path, state)
    assert b'"type":"closure"' not in source_path.read_bytes()


def test_direct_seal_requires_exact_runtime_marker_and_count(tmp_path):
    source_path = tmp_path / "direct.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "direct_transaction_wrapper"}))
    acceptance.append_source_event(source_path, _event(0, "gh_snapshot", ingress="direct_dispatch"))
    runtime_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_direct_transaction_runtime:v1", "source_event_count": 1, "terminal_marker": "transaction_closed"}))
    closure = acceptance.seal_direct_source_log(source_path, runtime_path)
    assert closure["owner"] == "direct_transaction_wrapper"
    assert acceptance.normalize_authoring_trace(source_path, runtime_path)["source_closure"] == closure


def test_direct_seal_refuses_wrong_count_or_extra_runtime_row(tmp_path):
    source_path = tmp_path / "direct.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "direct_transaction_wrapper"}))
    runtime_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_direct_transaction_runtime:v1", "source_event_count": 1, "terminal_marker": "transaction_closed"}))
    with pytest.raises(ValueError, match="invalid_direct_terminal_marker"):
        acceptance.seal_direct_source_log(source_path, runtime_path)

    runtime_path.write_bytes(
        acceptance.canonical_json_bytes({"schema": "rook.gh_direct_transaction_runtime:v1", "source_event_count": 0, "terminal_marker": "transaction_closed"})
        + acceptance.canonical_json_bytes({"extra": True})
    )
    with pytest.raises(ValueError, match="invalid_direct_terminal_marker"):
        acceptance.seal_direct_source_log(source_path, runtime_path)


def test_append_rejects_gaps_extra_keys_and_events_after_closure(tmp_path):
    source_path = tmp_path / "source.jsonl"
    source_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "prime_rook_adapter"}))
    with pytest.raises(ValueError):
        acceptance.append_source_event(source_path, _event(1, "gh_snapshot"))
    malformed = _event(0, "gh_snapshot") | {"extra": True}
    with pytest.raises(ValueError):
        acceptance.append_source_event(source_path, malformed)
    runtime_path = tmp_path / "runtime.jsonl"
    runtime_path.write_bytes(acceptance.canonical_json_bytes({"type": "agent_end"}))
    acceptance.seal_prime_source_log(
        source_path,
        runtime_path,
        {"terminated": True, "stdout_eof": True, "owned_child_pids": [], "exit_code": 0},
    )
    with pytest.raises(ValueError, match="source_log_closed"):
        acceptance.append_source_event(source_path, _event(0, "gh_snapshot"))


def test_normalizer_rejects_duplicate_keys_bad_hash_and_valid_prefix(tmp_path):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_text('{"schema":"rook.gh_authoring_source_log:v1","schema":"duplicate","row_emitter":"prime_rook_adapter"}\n', encoding="utf-8")
    runtime_path.write_bytes(acceptance.canonical_json_bytes({"type": "agent_end"}))
    with pytest.raises(ValueError):
        acceptance.normalize_authoring_trace(source_path, runtime_path)
    source_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "prime_rook_adapter"}))
    with pytest.raises(ValueError):
        acceptance.normalize_authoring_trace(source_path, runtime_path)


def test_normalizer_rejects_post_seal_runtime_or_source_tampering(tmp_path):
    source_path = tmp_path / "source.jsonl"
    runtime_path = tmp_path / "runtime.jsonl"
    source_path.write_bytes(acceptance.canonical_json_bytes({"schema": "rook.gh_authoring_source_log:v1", "row_emitter": "prime_rook_adapter"}))
    acceptance.append_source_event(source_path, _event(0, "gh_snapshot"))
    runtime_path.write_bytes(acceptance.canonical_json_bytes({"type": "agent_end"}))
    acceptance.seal_prime_source_log(
        source_path,
        runtime_path,
        {"terminated": True, "stdout_eof": True, "owned_child_pids": [], "exit_code": 7},
    )
    runtime_path.write_bytes(
        acceptance.canonical_json_bytes({"type": "message"})
        + acceptance.canonical_json_bytes({"type": "agent_end"})
    )
    with pytest.raises(ValueError, match="source_closure_mismatch"):
        acceptance.normalize_authoring_trace(source_path, runtime_path)


def test_exact_python_exception_shape_is_admitted_but_never_authorizes_probe():
    event = {
        "sequence": 0,
        "ingress": "canonical_gateway",
        "target": "gh_edit",
        "arguments": {},
        "result": None,
        "exception": {"type": "builtins.RuntimeError", "message": ""},
        "dispatch": {"status": "unknown", "target_call_count": None},
        "mutation": {
            "classification": "unknown",
            "commit_status": "unknown",
            "commit_evidence": None,
            "solve_readiness_receipt": None,
        },
    }
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), _trace(event), executor))
    assert probe["termination"]["error"] == "authoring_trace_invalid"
    assert executor.calls == []


@pytest.mark.parametrize("exc", [asyncio.CancelledError(), KeyboardInterrupt(), SystemExit()])
def test_baseexception_paths_are_not_captured_as_closed_events(exc):
    assert not isinstance(exc, Exception)
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    async def raise_base_exception(name: str, arguments: dict):
        raise exc

    with pytest.raises(type(exc)):
        asyncio.run(
            acceptance.run_behavioral_probe(_artifact(), trace, raise_base_exception)
        )


def test_acceptance_artifact_validation_is_closed_and_rejects_numeric_booleans():
    assert acceptance.validate_acceptance_artifact(_artifact()) == _artifact()
    bad = _artifact()
    bad["numeric_tolerance"] = True
    with pytest.raises(ValueError, match="artifact_invalid"):
        acceptance.validate_acceptance_artifact(bad)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra=True),
        lambda value: value["controls"].append(dict(value["controls"][0])),
        lambda value: value["criteria"].append(dict(value["criteria"][0])),
        lambda value: value["controls"][0].update(role="bad-role"),
        lambda value: value["criteria"][0].update(id="BadCriterion"),
        lambda value: value["output"].update(max_preview_items=True),
        lambda value: value["controls"][2].update(probe_value=4.0),
        lambda value: value["criteria"][1]["arguments"].update(role="Step"),
        lambda value: value["criteria"][2].update(predicate="unknown"),
        lambda value: value.update(numeric_tolerance=float("inf")),
    ],
)
def test_acceptance_artifact_single_field_mutations_fail_closed(mutation):
    artifact = _artifact()
    mutation(artifact)
    with pytest.raises(ValueError, match="artifact_invalid"):
        acceptance.validate_acceptance_artifact(artifact)
    bad = _artifact()
    bad["controls"][0]["selector"]["kind"] = "component_id"
    with pytest.raises(ValueError, match="artifact_invalid"):
        acceptance.validate_acceptance_artifact(bad)
    bad = _artifact()
    bad["criteria"][0]["arguments"]["roles"].append("Start")
    with pytest.raises(ValueError, match="artifact_invalid"):
        acceptance.validate_acceptance_artifact(bad)


def test_latest_terminal_receipt_allows_later_observation_while_unobserved_out_of_band_mutation_is_outside_claim():
    issued = _receipt()
    good = _trace(
        _event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued),
        _event(1, "gh_snapshot"),
    )
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), good, executor))
    assert probe["termination"] == {"status": "complete", "error": None}

    blocked = _trace(
        _event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued),
        _event(1, "gh_set_script_pins", classification="preparatory"),
    )
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), blocked, executor))
    assert probe["termination"]["error"] == "later_unfenced_mutation"
    assert executor.calls == []

    for later in (
        _event(1, "gh_edit", classification="terminal", commit_status="none"),
        _event(1, "gh_legacy_mutator", classification="legacy"),
    ):
        executor = _Executor()
        blocked = _trace(
            _event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued),
            later,
        )
        probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), blocked, executor))
        assert probe["termination"]["error"] == "later_unfenced_mutation"
        assert executor.calls == []


def test_zero_or_group_only_edit_cannot_supply_terminal_receipt():
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="none"))
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, executor))
    assert probe["termination"]["error"] == "latest_terminal_receipt_missing"
    assert executor.calls == []


@pytest.mark.parametrize(
    "status",
    ["superseded", "document_replaced", "solver_locked", "unknown"],
)
def test_nonpending_terminal_receipt_refuses_before_probe(status):
    invalid_for_probe = _receipt(status=status)
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=invalid_for_probe,
        )
    )
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, executor))
    assert probe["termination"]["error"] == "receipt_correlation_failed"
    assert executor.calls == []


def test_script_preparation_then_terminal_write_selects_final_receipt():
    issued = _receipt("script-write")
    trace = _trace(
        _event(0, "gh_set_script_pins", classification="preparatory"),
        _event(
            1,
            "gh_create_script",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        ),
    )
    executor = _Executor()
    executor.pending = issued
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, executor))
    assert probe["termination"] == {"status": "complete", "error": None}
    assert executor.calls[0] == (
        "gh_wait_for_solve_readiness",
        {"readiness_receipt_id": "script-write", "timeout_ms": 10_000},
    )


def test_partial_gh_edit_with_confirmed_commit_and_receipt_is_terminal_evidence():
    issued = _receipt()
    event = _event(
        0,
        "gh_edit",
        classification="terminal",
        commit_status="committed",
        receipt=issued,
    )
    event["result"]["success"] = False
    event["result"]["data"]["errors"] = ["later operation failed"]
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), _trace(event), executor))
    assert probe["termination"] == {"status": "complete", "error": None}


def test_gh_edit_embedded_snapshot_cannot_substitute_for_terminal_receipt():
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=None,
            data={"snapshot": {"components": []}},
        )
    )
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, executor))
    assert probe["termination"]["error"] == "authoring_trace_invalid"
    assert executor.calls == []


def test_terminal_classification_cannot_be_spoofed_by_unknown_route_or_detached_receipt():
    issued = _receipt()
    unknown = _event(
        0,
        "future_mutator",
        classification="terminal",
        commit_status="committed",
        receipt=issued,
    )
    detached = _event(
        0,
        "gh_edit",
        classification="terminal",
        commit_status="committed",
        receipt=issued,
    )
    detached["result"]["data"].pop("solve_readiness_receipt")
    for event in (unknown, detached):
        executor = _Executor()
        probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), _trace(event), executor))
        assert probe["termination"]["error"] == "authoring_trace_invalid"
        assert executor.calls == []


def test_commit_evidence_cannot_manufacture_or_hide_edit_commit():
    issued = _receipt()
    manufactured = _event(
        0,
        "gh_edit",
        classification="terminal",
        commit_status="committed",
        receipt=issued,
    )
    manufactured["mutation"]["commit_evidence"] = {
        "created": 0,
        "deleted": 0,
        "values_set": 0,
        "connected": 0,
        "disconnected": 0,
    }
    hidden = _event(0, "gh_edit", classification="terminal", commit_status="none")
    hidden["mutation"]["commit_evidence"]["connected"] = 1
    for event in (manufactured, hidden):
        probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), _trace(event), _Executor()))
        assert probe["termination"]["error"] == "authoring_trace_invalid"


def test_complete_probe_uses_exact_fenced_sequence_and_restores_each_control():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))
    executor = _Executor()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, executor))

    assert probe["termination"] == {"status": "complete", "error": None}
    names = [name for name, _ in executor.calls]
    assert names == ["gh_wait_for_solve_readiness", "gh_snapshot"] + [
        name
        for _ in range(3)
        for name in (
            "gh_set_value",
            "gh_wait_for_solve_readiness",
            "gh_snapshot",
            "gh_set_value",
            "gh_wait_for_solve_readiness",
            "gh_snapshot",
        )
    ]
    assert executor.values == {"Start": 0.0, "Step": 1.0, "Count": 3}
    assert len({event["mutation"]["solve_readiness_receipt"]["receipt_id"] for event in probe["events"] if event["target"] == "gh_set_value"}) == 6
    assert [
        arguments
        for name, arguments in executor.calls
        if name == "gh_set_value"
    ] == [
        {"guid": "C1", "value": 2.0},
        {"guid": "C1", "value": 0.0},
        {"guid": "C2", "value": 2.0},
        {"guid": "C2", "value": 1.0},
        {"guid": "C3", "value": 4},
        {"guid": "C3", "value": 3},
    ]

    result = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    assert result["status"] == "pass"
    assert [item["status"] for item in result["criteria"]] == ["pass"] * 6


def test_probe_stops_after_executor_exception_and_records_exact_exception():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class Exploding(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            if name == "gh_snapshot":
                raise RuntimeError("")
            return await super().__call__(name, arguments)

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, Exploding()))
    assert probe["termination"] == {"status": "failed", "error": "baseline_snapshot_failed"}
    assert probe["events"][-1]["exception"] == {"type": "builtins.RuntimeError", "message": ""}


def test_probe_set_value_arguments_reach_canonical_managed_boundary_unchanged(
    monkeypatch,
):
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )
    executor = _Executor()
    managed_calls: list[tuple[str, str, dict, int | None]] = []

    monkeypatch.setattr(gh_knowledge, "gh_query_operation", lambda *_: {"gotchas": []})
    monkeypatch.setattr(server, "_check_for_gh_correction", lambda *_: None)

    async def no_record(**_kwargs):
        return None

    monkeypatch.setattr(server, "_record_gh_to_session", no_record)

    async def managed(route, method="GET", payload=None, port=None, **_kwargs):
        assert route == "/gh/value"
        assert method == "POST"
        assert type(payload) is dict and set(payload) == {"guid", "value"}
        managed_calls.append((route, method, dict(payload), port))
        role = {"C1": "Start", "C2": "Step", "C3": "Count"}[payload["guid"]]
        executor.values[role] = payload["value"]
        executor.issued += 1
        executor.pending = _receipt(
            f"receipt-{executor.issued}", mutation_epoch=executor.issued
        )
        return {
            "success": True,
            "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": executor.pending,
            },
        }

    monkeypatch.setattr(server, "call_rhino", managed)

    async def canonical(name: str, arguments: dict) -> dict:
        if name == "gh_set_value":
            return await server._call_tool_dispatch(
                name, arguments | {"port": 6011}
            )
        return await executor(name, arguments)

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, canonical))

    assert probe["termination"] == {"status": "complete", "error": None}
    assert [call[2] for call in managed_calls] == [
        {"guid": "C1", "value": 2.0},
        {"guid": "C1", "value": 0.0},
        {"guid": "C2", "value": 2.0},
        {"guid": "C2", "value": 1.0},
        {"guid": "C3", "value": 4},
        {"guid": "C3", "value": 3},
    ]
    assert all(call[3] == 6011 for call in managed_calls)


def test_failed_mutation_result_remains_a_valid_monotonic_probe_prefix():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class RefusingSet(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            if name == "gh_set_value":
                self.calls.append((name, arguments))
                return {"success": False, "data": "refused"}
            return await super().__call__(name, arguments)

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, RefusingSet()))
    assert probe["termination"] == {"status": "failed", "error": "perturbation_dispatch_failed"}
    assert probe["events"][-1]["mutation"] == {
        "classification": "unknown",
        "commit_status": "unknown",
        "commit_evidence": None,
        "solve_readiness_receipt": None,
    }
    evaluation = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    assert evaluation["status"] == "incomplete"
    assert evaluation["probe"]["error"] == "perturbation_dispatch_failed"
    assert evaluation["probe"]["baseline"] is not None
    assert evaluation["probe"]["controls"][0] == {
        "role": "Start",
        "component_id": "C1",
        "original_value": 0.0,
        "probe_value": 2.0,
        "perturbation": None,
        "restoration": None,
    }


def test_failed_restoration_retains_completed_perturbation_evidence():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class RefusingRestoration(_Executor):
        def __init__(self):
            super().__init__()
            self.set_calls = 0

        async def __call__(self, name: str, arguments: dict) -> dict:
            if name == "gh_set_value":
                self.set_calls += 1
                if self.set_calls == 2:
                    self.calls.append((name, arguments))
                    return {"success": False, "data": "refused"}
            return await super().__call__(name, arguments)

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, RefusingRestoration()))
    assert probe["termination"]["error"] == "restoration_dispatch_failed"
    evaluation = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    control = evaluation["probe"]["controls"][0]
    assert control["perturbation"] is not None
    assert control["restoration"] is None
    assert "perturbation:Start" in evaluation["criteria"][0]["evidence_refs"]


def test_probe_refuses_control_cross_talk_and_compromised_restoration():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class CrossTalk(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_set_value" and arguments["guid"] == "C1" and arguments["value"] == 2.0:
                self.values["Step"] = 9.0
            return result

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, CrossTalk()))
    assert probe["termination"]["error"] == "perturbation_control_mismatch"
    assert [event["target"] for event in probe["events"]].count("gh_set_value") == 1


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda result: result["data"]["components"].pop(1),
            "control_binding_failed",
        ),
        (
            lambda result: result["data"]["behavioral_point_outputs"][0].update(
                complete=False,
                error="truncated",
            ),
            "output_incomplete",
        ),
        (
            lambda result: result["data"]["readiness_fence"].update(
                mutation_epoch=999,
            ),
            "receipt_correlation_failed",
        ),
    ],
)
def test_baseline_failure_tokens_remain_owned_by_exact_boundary(mutation, expected):
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class MutatingSnapshot(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_snapshot":
                mutation(result)
            return result

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, MutatingSnapshot()))
    assert probe["termination"]["error"] == expected
    assert [event["target"] for event in probe["events"]] == [
        "gh_wait_for_solve_readiness",
        "gh_snapshot",
    ]


def test_restoration_semantic_mismatch_stops_before_next_control():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class BadRestoration(_Executor):
        def __init__(self):
            super().__init__()
            self.set_count = 0

        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_set_value":
                self.set_count += 1
            if name == "gh_snapshot" and self.set_count == 2:
                result["data"]["diagnostics"]["warnings"] = 1
            return result

    executor = BadRestoration()
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, executor))
    assert probe["termination"]["error"] == "restoration_mismatch"
    assert [event["target"] for event in probe["events"]].count("gh_set_value") == 2


def test_evaluator_rejects_wrong_wait_arguments_even_when_results_correlate():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, _Executor()))
    probe["events"][0]["arguments"]["timeout_ms"] = 9_999
    result = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    assert result["status"] == "incomplete"
    assert result["probe"]["error"] == "probe_trace_invalid"


def test_evaluator_independently_rejects_cross_talk_in_retained_complete_trace():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, _Executor()))
    step = next(
        component
        for component in probe["events"][4]["result"]["data"]["components"]
        if component["id"] == "C2"
    )
    step["value"]["val"] = 9.0
    result = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    assert result["status"] == "incomplete"
    assert result["probe"]["error"] == "probe_trace_invalid"


def test_complete_probe_cannot_claim_a_noncommitted_or_nonpending_set_receipt():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )
    complete = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, _Executor())
    )
    noncommitted = json.loads(json.dumps(complete))
    set_event = noncommitted["events"][2]
    set_event["result"]["data"]["solve_relevant_mutation_committed"] = False
    set_event["mutation"] = {
        "classification": "terminal",
        "commit_status": "none",
        "commit_evidence": {"solve_relevant_mutation_committed": False},
        "solve_readiness_receipt": set_event["result"]["data"][
            "solve_readiness_receipt"
        ],
    }
    assert acceptance.evaluate_behavioral_probe(
        _artifact(), trace, noncommitted
    )["probe"]["error"] == "probe_trace_invalid"

    class SupersededSet(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_set_value":
                result["data"]["solve_readiness_receipt"]["status"] = "superseded"
            return result

    refused = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, SupersededSet())
    )
    assert refused["termination"]["error"] == "perturbation_receipt_invalid"


def test_probe_refuses_receipt_reuse_across_distinct_mutations():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))

    class ReusingReceipt(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_set_value" and self.issued >= 4:
                self.pending = _receipt("receipt-2", mutation_epoch=2)
                result["data"]["solve_readiness_receipt"] = self.pending
            return result

    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, ReusingReceipt()))
    assert probe["termination"]["error"] in {
        "perturbation_receipt_invalid",
        "restoration_receipt_invalid",
    }


def test_evaluator_rejects_reordered_extra_or_second_failure_events():
    issued = _receipt()
    trace = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))
    probe = asyncio.run(acceptance.run_behavioral_probe(_artifact(), trace, _Executor()))
    probe["events"].append(probe["events"][-1] | {"sequence": len(probe["events"])})
    result = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    assert result["status"] == "incomplete"
    assert result["probe"]["error"] == "probe_trace_invalid"


def test_generic_cartesian_and_product_predicates_pass_without_topology_names():
    artifact = _artifact()
    artifact["controls"] = [
        {"role": "StartX", "selector": {"kind": "exact_nickname", "value": "SX"}, "value_kind": "number", "probe_value": 2.0},
        {"role": "StepX", "selector": {"kind": "exact_nickname", "value": "DX"}, "value_kind": "number", "probe_value": 2.0},
        {"role": "CountX", "selector": {"kind": "exact_nickname", "value": "NX"}, "value_kind": "integer", "probe_value": 3},
        {"role": "StartY", "selector": {"kind": "exact_nickname", "value": "SY"}, "value_kind": "number", "probe_value": 2.0},
        {"role": "StepY", "selector": {"kind": "exact_nickname", "value": "DY"}, "value_kind": "number", "probe_value": 2.0},
        {"role": "CountY", "selector": {"kind": "exact_nickname", "value": "NY"}, "value_kind": "integer", "probe_value": 3},
    ]
    artifact["criteria"] = [
        {"id": "count_product", "predicate": "point_count_equals_product", "arguments": {"roles": ["CountX", "CountY"]}},
        {"id": "grid", "predicate": "axes_form_cartesian_product", "arguments": {"sequences": [
            {"axis": "x", "start_role": "StartX", "step_role": "StepX", "count_role": "CountX"},
            {"axis": "y", "start_role": "StartY", "step_role": "StepY", "count_role": "CountY"},
        ]}},
    ]
    assert acceptance.validate_acceptance_artifact(artifact) == artifact

    class GridExecutor:
        def __init__(self, wrong: bool = False):
            self.values = {
                "StartX": 0.0,
                "StepX": 1.0,
                "CountX": 2,
                "StartY": 0.0,
                "StepY": 10.0,
                "CountY": 2,
            }
            self.ids = {
                "C1": "StartX",
                "C2": "StepX",
                "C3": "CountX",
                "C4": "StartY",
                "C5": "StepY",
                "C6": "CountY",
            }
            self.pending = _receipt()
            self.issued = 1
            self.wrong = wrong

        def snapshot(self, receipt: dict) -> dict:
            points = [
                [
                    self.values["StartX"] + x * self.values["StepX"],
                    self.values["StartY"] + y * self.values["StepY"],
                    0.0,
                ]
                for x in range(int(self.values["CountX"]))
                for y in range(int(self.values["CountY"]))
            ]
            if self.wrong:
                points[-1][1] += 1.0
            components = [
                {
                    "id": component_id,
                    "type": "NumberSlider",
                    "nick": role.replace("Start", "S").replace("Step", "D").replace("Count", "N"),
                    "value": {
                        "type": "slider",
                        "val": self.values[role],
                        "min": -10 if "Count" not in role else 1,
                        "max": 20,
                    },
                }
                for component_id, role in self.ids.items()
            ] + [{"id": "C7", "type": "UnknownGridProducer", "nick": "Output"}]
            return {
                "success": True,
                "data": {
                    "components": components,
                    "flows": [f"{component_id}.O0>C7.I{index}" for index, component_id in enumerate(self.ids)],
                    "diagnostics": {"total": 7, "errors": 0, "warnings": 0, "error_ids": [], "warning_ids": []},
                    "readiness_fence": {
                        "readiness_receipt_id": receipt["receipt_id"],
                        "document_session_id": receipt["document_session_id"],
                        "mutation_epoch": receipt["mutation_epoch"],
                        "solution_run_epoch": receipt["solution_run_epoch"],
                        "completed_solution_run_epoch": receipt["completed_solution_run_epoch"],
                    },
                    "behavioral_point_outputs": [{
                        "component_id": "C7",
                        "output_index": 0,
                        "output_name": "P",
                        "count": len(points),
                        "complete": True,
                        "points": points,
                        "error": None,
                    }],
                },
            }

        async def __call__(self, name: str, arguments: dict) -> dict:
            if name == "gh_set_value":
                assert set(arguments) == {"guid", "value"}
                self.values[self.ids[arguments["guid"]]] = arguments["value"]
                self.issued += 1
                self.pending = _receipt(f"grid-{self.issued}", mutation_epoch=self.issued)
                return {"success": True, "data": {"solve_relevant_mutation_committed": True, "solve_readiness_receipt": self.pending}}
            ready = _receipt(self.pending["receipt_id"], mutation_epoch=self.pending["mutation_epoch"], solution_epoch=self.pending["mutation_epoch"] + 20, status="ready")
            if name == "gh_wait_for_solve_readiness":
                return _wait_result(ready)
            if name == "gh_snapshot":
                return self.snapshot(ready)
            raise AssertionError(name)

    issued = _receipt()
    authoring = _trace(_event(0, "gh_edit", classification="terminal", commit_status="committed", receipt=issued))
    executor = GridExecutor()
    probe = asyncio.run(acceptance.run_behavioral_probe(artifact, authoring, executor))
    result = acceptance.evaluate_behavioral_probe(artifact, authoring, probe)
    assert result["status"] == "pass"
    assert [item["status"] for item in result["criteria"]] == ["pass", "pass"]

    wrong_probe = asyncio.run(acceptance.run_behavioral_probe(artifact, authoring, GridExecutor(wrong=True)))
    wrong = acceptance.evaluate_behavioral_probe(artifact, authoring, wrong_probe)
    assert wrong["status"] == "fail"
    assert [item["status"] for item in wrong["criteria"]] == ["pass", "fail"]


def test_route_owned_projection_rejects_observational_legacy_mutation_and_false_edit_summary():
    issued = _receipt()
    later_connect = _event(1, "gh_connect", classification="observational")
    spoofed_edit = _event(
        0,
        "gh_edit",
        classification="terminal",
        commit_status="committed",
        receipt=issued,
    )
    spoofed_edit["result"]["data"]["edit_summary"] = {
        "created": 0,
        "deleted": 0,
        "values_set": 0,
        "connected": 0,
        "disconnected": 0,
    }
    for trace in (
        _trace(
            _event(
                0,
                "gh_edit",
                classification="terminal",
                commit_status="committed",
                receipt=issued,
            ),
            later_connect,
        ),
        _trace(spoofed_edit),
    ):
        probe = asyncio.run(
            acceptance.run_behavioral_probe(_artifact(), trace, _Executor())
        )
        assert probe["termination"]["error"] == "authoring_trace_invalid"


def test_direct_terminal_projection_is_correlated_and_retains_nonready_receipt():
    issued = _receipt()
    false_receipt = _receipt("no-commit", mutation_epoch=2, status="unknown")
    event = _event(
        1,
        "gh_set_value",
        classification="terminal",
        commit_status="none",
        receipt=false_receipt,
        data={"solve_relevant_mutation_committed": False},
    )
    event["mutation"]["commit_evidence"] = {
        "solve_relevant_mutation_committed": False
    }
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        ),
        event,
    )
    probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, _Executor())
    )
    assert probe["termination"]["error"] == "later_unfenced_mutation"

    spoofed = json.loads(json.dumps(event))
    spoofed["result"]["data"]["solve_relevant_mutation_committed"] = True
    spoofed_probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), _trace(spoofed), _Executor())
    )
    assert spoofed_probe["termination"]["error"] == "authoring_trace_invalid"


@pytest.mark.parametrize(
    ("committed", "commit_status"),
    [(False, "none"), (None, "unknown")],
)
def test_failed_direct_result_retains_exact_commit_fact_and_receipt(
    committed, commit_status
):
    issued = _receipt()
    later_receipt = _receipt(
        f"direct-{commit_status}", mutation_epoch=2, status="unknown"
    )
    event = _event(
        1,
        "gh_set_value",
        classification="terminal",
        commit_status=commit_status,
        receipt=later_receipt,
        data={"solve_relevant_mutation_committed": committed},
    )
    event["result"]["success"] = False
    event["mutation"]["commit_evidence"] = {
        "solve_relevant_mutation_committed": committed
    }
    probe = asyncio.run(
        acceptance.run_behavioral_probe(
            _artifact(),
            _trace(
                _event(
                    0,
                    "gh_edit",
                    classification="terminal",
                    commit_status="committed",
                    receipt=issued,
                ),
                event,
            ),
            _Executor(),
        )
    )
    assert probe["termination"]["error"] == "later_unfenced_mutation"


def test_recognized_zero_dispatch_refusal_is_observational_but_unknown_refusal_is_not():
    issued = _receipt()
    refused = _event(1, "gh_connect", classification="observational")
    refused["result"] = {
        "success": False,
        "data": {
            "error": "invalid_arguments",
            "name": "gh_connect",
            "fields": ["target: required"],
        },
    }
    refused["dispatch"] = {
        "status": "refused_before_dispatch",
        "target_call_count": 0,
    }
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        ),
        refused,
    )
    assert asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, _Executor())
    )["termination"] == {"status": "complete", "error": None}

    unrecognized = json.loads(json.dumps(refused))
    unrecognized["result"]["data"]["error"] = "mystery_refusal"
    probe = asyncio.run(
        acceptance.run_behavioral_probe(
            _artifact(),
            _trace(trace["events"][0], unrecognized),
            _Executor(),
        )
    )
    assert probe["termination"]["error"] == "authoring_trace_invalid"


def test_empty_point_multiset_is_incomplete_and_never_vacuously_passes():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )

    class EmptyOutput(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_snapshot":
                output = result["data"]["behavioral_point_outputs"][0]
                output["count"] = 0
                output["points"] = []
            return result

    probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, EmptyOutput())
    )
    assert probe["termination"] == {
        "status": "failed",
        "error": "output_incomplete",
    }
    result = acceptance.evaluate_behavioral_probe(_artifact(), trace, probe)
    assert result["status"] == "incomplete"
    assert all(item["status"] == "unproven" for item in result["criteria"])


def test_oversized_json_integer_is_rejected_without_projection_exception():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )

    class OversizedCoordinate(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_snapshot":
                result["data"]["behavioral_point_outputs"][0]["points"][0][0] = (
                    10**1000
                )
            return result

    probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, OversizedCoordinate())
    )
    assert probe["termination"] == {
        "status": "failed",
        "error": "output_incomplete",
    }


def test_zero_tolerance_does_not_collapse_distinct_large_json_integers():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )
    artifact = _artifact()
    artifact["numeric_tolerance"] = 0
    artifact["criteria"] = [
        {
            "id": "large_y_exact",
            "predicate": "axis_equals_constant",
            "arguments": {"axis": "y", "value": 2**53},
        }
    ]

    class DistinctLargeInteger(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_snapshot":
                for point in result["data"]["behavioral_point_outputs"][0][
                    "points"
                ]:
                    point[1] = 2**53 + 1
            return result

    probe = asyncio.run(
        acceptance.run_behavioral_probe(artifact, trace, DistinctLargeInteger())
    )
    result = acceptance.evaluate_behavioral_probe(artifact, trace, probe)

    assert probe["termination"] == {"status": "complete", "error": None}
    assert result["status"] == "fail"
    assert result["criteria"] == [
        {
            "criterion_id": "large_y_exact",
            "status": "fail",
            "failure_ids": ["large_y_exact"],
            "evidence_refs": [
                "baseline",
                "perturbation:Start",
                "restoration:Start",
                "perturbation:Step",
                "restoration:Step",
                "perturbation:Count",
                "restoration:Count",
            ],
        }
    ]


def test_failed_probe_must_match_exact_first_failure_boundary():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )
    complete = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, _Executor())
    )
    forged = json.loads(json.dumps(complete))
    forged["termination"] = {
        "status": "failed",
        "error": "restoration_dispatch_failed",
    }
    result = acceptance.evaluate_behavioral_probe(_artifact(), trace, forged)
    assert result["status"] == "incomplete"
    assert result["probe"]["error"] == "probe_trace_invalid"
    assert result["probe"]["controls"] == []

    class FailingExecutor(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            if name == "gh_set_value":
                raise RuntimeError("real failure")
            return await super().__call__(name, arguments)

    actual_failure = asyncio.run(
        acceptance.run_behavioral_probe(
            _artifact(),
            trace,
            FailingExecutor(),
        )
    )
    wrong_token = json.loads(json.dumps(actual_failure))
    wrong_token["termination"]["error"] = "restoration_dispatch_failed"
    assert acceptance.evaluate_behavioral_probe(
        _artifact(), trace, wrong_token
    )["probe"]["error"] == "probe_trace_invalid"
def test_malformed_executor_return_is_not_fabricated_as_an_exception():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )

    async def malformed(name: str, arguments: dict):
        return []

    malformed_probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, malformed)
    )
    assert malformed_probe["termination"] == {
        "status": "failed",
        "error": "probe_trace_invalid",
    }
    assert malformed_probe["events"] == []

    async def raised(name: str, arguments: dict):
        raise ValueError("invalid_executor_result")

    raised_probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, raised)
    )
    assert raised_probe["termination"]["error"] == "baseline_wait_failed"
    assert raised_probe["events"][0]["exception"] == {
        "type": "builtins.ValueError",
        "message": "invalid_executor_result",
    }


@pytest.mark.parametrize("which", ["artifact", "authoring", "probe"])
def test_noncanonical_public_inputs_have_one_explicit_failure(which):
    issued = _receipt()
    artifact = _artifact()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )
    probe = asyncio.run(
        acceptance.run_behavioral_probe(artifact, trace, _Executor())
    )
    values = {"artifact": artifact, "authoring": trace, "probe": probe}
    values[which] = json.loads(json.dumps(values[which]))
    values[which]["noncanonical"] = float("nan")
    with pytest.raises(ValueError, match="^input_not_canonical_json$"):
        acceptance.evaluate_behavioral_probe(
            values["artifact"], values["authoring"], values["probe"]
        )


def test_duplicate_group_ids_make_snapshot_projection_incomplete():
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )

    class DuplicateGroups(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_snapshot":
                group = {
                    "id": "G1",
                    "nick": "Group",
                    "description": "duplicate",
                    "colour": "#FFFFFF",
                    "members": ["C1"],
                }
                result["data"]["groups"] = [group, dict(group)]
            return result

    probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, DuplicateGroups())
    )
    assert probe["termination"] == {
        "status": "failed",
        "error": "baseline_snapshot_failed",
    }


@pytest.mark.parametrize(
    "defect",
    [
        "invalid_relay",
        "missing_output_component",
        "missing_flow_source",
        "missing_flow_target",
    ],
)
def test_projected_references_must_name_existing_component_short_ids(defect):
    issued = _receipt()
    trace = _trace(
        _event(
            0,
            "gh_edit",
            classification="terminal",
            commit_status="committed",
            receipt=issued,
        )
    )

    class BrokenReference(_Executor):
        async def __call__(self, name: str, arguments: dict) -> dict:
            result = await super().__call__(name, arguments)
            if name == "gh_snapshot":
                if defect == "invalid_relay":
                    result["data"]["relays"] = ["not-a-short-id"]
                elif defect == "missing_output_component":
                    result["data"]["behavioral_point_outputs"][0][
                        "component_id"
                    ] = "C999"
                elif defect == "missing_flow_source":
                    result["data"]["flows"][0] = "C999.O0>C4.I0"
                else:
                    result["data"]["flows"][0] = "C1.O0>C999.I0"
            return result

    probe = asyncio.run(
        acceptance.run_behavioral_probe(_artifact(), trace, BrokenReference())
    )
    assert probe["termination"] == {
        "status": "failed",
        "error": "baseline_snapshot_failed",
    }
