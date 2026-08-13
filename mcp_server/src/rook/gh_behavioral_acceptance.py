"""Pure custody, probing, and evaluation for Grasshopper behavioral acceptance."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Awaitable, Callable

from .mcp_tool_profiles import PUBLIC_READONLY_TOOL_NAMES


__all__ = (
    "canonical_json_bytes",
    "append_source_event",
    "seal_prime_source_log",
    "seal_direct_source_log",
    "normalize_authoring_trace",
    "validate_acceptance_artifact",
    "run_behavioral_probe",
    "evaluate_behavioral_probe",
)


_SOURCE_SCHEMA = "rook.gh_authoring_source_log:v1"
_CLOSURE_SCHEMA = "rook.gh_authoring_source_closure:v1"
_TRACE_SCHEMA = "rook.gh_authoring_trace:v1"
_DIRECT_RUNTIME_SCHEMA = "rook.gh_direct_transaction_runtime:v1"
_PROBE_SCHEMA = "rook.gh_probe_trace:v1"
_ARTIFACT_SCHEMA = "rook.gh_behavioral_acceptance:v1"
_PROJECTION_SCHEMA = "rook.gh_behavioral_snapshot_projection:v1"
_SNAPSHOT_EVIDENCE_SCHEMA = "rook.gh_fenced_snapshot_evidence:v1"
_EVALUATION_SCHEMA = "rook.gh_behavioral_evaluation:v1"
_RECEIPT_SCHEMA = "rook.gh_solve_readiness_receipt:v1"
_WAIT_SCHEMA = "rook.gh_solve_readiness_wait_result:v1"

_SHA = re.compile(r"^[0-9A-F]{64}$")
_ROLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_CRITERION = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_COMPONENT_ID = re.compile(r"^C[1-9][0-9]*$")
_GROUP_ID = re.compile(r"^G[1-9][0-9]*$")
_GUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_FLOW = re.compile(r"^(C[1-9][0-9]*)\.O([0-9]+)>(C[1-9][0-9]*)\.I([0-9]+)$")

_EVENT_KEYS = {
    "sequence",
    "ingress",
    "target",
    "arguments",
    "result",
    "exception",
    "dispatch",
    "mutation",
}
_CLOSURE_KEYS = {
    "schema",
    "owner",
    "row_emitter",
    "source_event_count",
    "final_source_sequence",
    "source_log_sha256",
    "runtime_log_sha256",
    "terminal_marker",
    "closed",
}
_RECEIPT_KEYS = {
    "schema",
    "receipt_id",
    "document_session_id",
    "mutation_epoch",
    "solution_run_epoch",
    "completed_solution_run_epoch",
    "status",
    "reason",
    "completion_signal",
    "issued_at",
    "completed_at",
}
_PROBE_ERRORS = {
    "artifact_invalid",
    "authoring_trace_invalid",
    "probe_trace_invalid",
    "latest_terminal_receipt_missing",
    "later_unfenced_mutation",
    "receipt_correlation_failed",
    "baseline_wait_failed",
    "baseline_snapshot_failed",
    "control_binding_failed",
    "probe_value_invalid",
    "output_incomplete",
    "perturbation_dispatch_failed",
    "perturbation_receipt_invalid",
    "perturbation_wait_failed",
    "perturbation_snapshot_failed",
    "perturbation_control_mismatch",
    "restoration_dispatch_failed",
    "restoration_receipt_invalid",
    "restoration_wait_failed",
    "restoration_snapshot_failed",
    "restoration_mismatch",
}
_SCRIPT_TERMINAL_TARGETS = {
    "gh_create_script",
    "gh_create_python_script",
    "gh_create_csharp_script",
    "gh_update_script",
    "chirp_create",
}
_OBSERVATIONAL_TARGETS = frozenset(PUBLIC_READONLY_TOOL_NAMES) | {
    "gh_solve_readiness",
    "gh_wait_for_solve_readiness",
}
_ZERO_DISPATCH_REFUSALS = {
    "active_rhino_instance_unavailable",
    "invalid_arguments",
    "invalid_requested_port",
    "invalid_session_id",
    "legacy_semantic_tool_contained",
    "meta_recursion_forbidden",
    "multiple_rhino_instances",
    "not_mcp_dispatchable",
    "panel_target_config_error",
    "panel_target_locked",
    "panel_target_stale",
    "requested_port_not_discovered",
    "rhino_session_not_found",
    "rhino_target_error",
    "rhino_target_unavailable",
    "selector_conflict",
    "session_not_targetable",
    "tool_profile_blocked",
    "unknown_or_non_dispatchable",
}


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _strict_json_line(line: bytes) -> Any:
    if line.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom_forbidden")
    try:
        text = line.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_utf8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"nonfinite_json:{value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc


def canonical_json_bytes(value: Any) -> bytes:
    """Encode one canonical JSON row using the trace custody contract."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("value_not_canonical_json") from exc
    return (text + "\n").encode("utf-8", errors="strict")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _read_jsonl(path: Path) -> tuple[bytes, list[Any], list[bytes]]:
    payload = Path(path).read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom_forbidden")
    if payload and not payload.endswith(b"\n"):
        raise ValueError("missing_final_lf")
    raw_lines = payload.splitlines(keepends=True)
    if any(not line.endswith(b"\n") or line.strip() == b"" for line in raw_lines):
        raise ValueError("invalid_jsonl_row")
    values = [_strict_json_line(line[:-1]) for line in raw_lines]
    if any(canonical_json_bytes(value) != line for value, line in zip(values, raw_lines)):
        raise ValueError("noncanonical_jsonl")
    return payload, values, raw_lines


def _is_int(value: Any, *, minimum: int = 0, maximum: int | None = None) -> bool:
    return (
        type(value) is int
        and value >= minimum
        and (maximum is None or value <= maximum)
    )


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _valid_result(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"success", "data"}
        and type(value["success"]) is bool
    )


def _valid_exception(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"type", "message"}
        and isinstance(value["type"], str)
        and bool(value["type"])
        and isinstance(value["message"], str)
    )


def _valid_composite_commit_evidence(value: Any) -> bool:
    if type(value) is not dict or set(value) != {"component", "final_write"}:
        return False
    component = value["component"]
    final_write = value["final_write"]
    return (
        type(component) is dict
        and set(component) == {"guid", "short_id"}
        and all(component[key] is None or isinstance(component[key], str) for key in component)
        and type(final_write) is dict
        and set(final_write)
        == {"dispatched", "success", "solve_relevant_mutation_committed"}
        and type(final_write["dispatched"]) is bool
        and (final_write["success"] is None or type(final_write["success"]) is bool)
        and (
            final_write["solve_relevant_mutation_committed"] is None
            or type(final_write["solve_relevant_mutation_committed"]) is bool
        )
    )


def _unknown_mutation() -> dict[str, Any]:
    return {
        "classification": "unknown",
        "commit_status": "unknown",
        "commit_evidence": None,
        "solve_readiness_receipt": None,
    }


def _observational_mutation() -> dict[str, Any]:
    return {
        "classification": "observational",
        "commit_status": "none",
        "commit_evidence": None,
        "solve_readiness_receipt": None,
    }


def _result_receipt(data: Any) -> tuple[dict[str, Any] | None, bool]:
    if type(data) is not dict:
        return None, True
    raw = data.get("solve_readiness_receipt")
    if raw is None:
        return None, True
    return (raw, True) if _valid_receipt(raw) else (None, False)


def _recognized_zero_dispatch_refusal(event: dict[str, Any]) -> bool:
    result = event["result"]
    if (
        event["dispatch"]
        != {"status": "refused_before_dispatch", "target_call_count": 0}
        or type(result) is not dict
        or result.get("success") is not False
        or type(result.get("data")) is not dict
    ):
        return False
    data = result["data"]
    code = data.get("code") if isinstance(data.get("code"), str) else data.get("error")
    return isinstance(code, str) and code in _ZERO_DISPATCH_REFUSALS


def _composite_evidence(event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any] | None:
    if data.get("error") == "script_pipeline_incomplete":
        evidence = {
            "component": data.get("component"),
            "final_write": data.get("final_write"),
        }
        return evidence if _valid_composite_commit_evidence(evidence) else None
    if "solve_relevant_mutation_committed" not in data:
        return None
    committed = data["solve_relevant_mutation_committed"]
    if committed is not None and type(committed) is not bool:
        return None
    component_guid = data.get("component_guid", data.get("guid"))
    if component_guid is not None and not isinstance(component_guid, str):
        return None
    requested = event["arguments"].get("guid")
    short_id = requested if isinstance(requested, str) and _COMPONENT_ID.fullmatch(requested) else None
    return {
        "component": {"guid": component_guid, "short_id": short_id},
        "final_write": {
            "dispatched": True,
            "success": event["result"]["success"],
            "solve_relevant_mutation_committed": committed,
        },
    }


def _expected_mutation(event: dict[str, Any]) -> dict[str, Any]:
    if event["exception"] is not None or event["dispatch"]["status"] == "unknown":
        return _unknown_mutation()
    if event["dispatch"]["status"] == "refused_before_dispatch":
        return _observational_mutation() if _recognized_zero_dispatch_refusal(event) else _unknown_mutation()
    target = event["target"]
    result = event["result"]
    if type(result) is not dict:
        return _unknown_mutation()
    data = result["data"]
    if target == "gh_set_script" and "script" not in event["arguments"]:
        return _observational_mutation()
    if target in _OBSERVATIONAL_TARGETS:
        return _observational_mutation()
    if target == "gh_set_script_pins":
        return {
            "classification": "preparatory",
            "commit_status": "none",
            "commit_evidence": {
                "success": result["success"],
                "target_dispatched": True,
            },
            "solve_readiness_receipt": None,
        }
    if target == "gh_edit":
        summary = data.get("edit_summary") if type(data) is dict else None
        keys = {"created", "deleted", "values_set", "connected", "disconnected"}
        if (
            type(summary) is not dict
            or not keys <= set(summary)
            or any(not _is_int(summary[key]) for key in keys)
        ):
            return _unknown_mutation()
        receipt, receipt_valid = _result_receipt(data)
        if not receipt_valid:
            return _unknown_mutation()
        evidence = {key: summary[key] for key in keys}
        committed = sum(evidence.values()) > 0
        return {
            "classification": "terminal",
            "commit_status": "committed" if committed else "none",
            "commit_evidence": evidence,
            "solve_readiness_receipt": receipt,
        }
    if target in {"gh_set_value", "gh_set_script"}:
        if type(data) is not dict or "solve_relevant_mutation_committed" not in data:
            return _unknown_mutation()
        committed = data["solve_relevant_mutation_committed"]
        if committed is not None and type(committed) is not bool:
            return _unknown_mutation()
        receipt, receipt_valid = _result_receipt(data)
        if not receipt_valid:
            return _unknown_mutation()
        return {
            "classification": "terminal",
            "commit_status": (
                "unknown" if committed is None else "committed" if committed else "none"
            ),
            "commit_evidence": {
                "solve_relevant_mutation_committed": committed
            },
            "solve_readiness_receipt": receipt,
        }
    if target in _SCRIPT_TERMINAL_TARGETS:
        if type(data) is not dict:
            return _unknown_mutation()
        evidence = _composite_evidence(event, data)
        receipt, receipt_valid = _result_receipt(data)
        if evidence is None or not receipt_valid:
            return _unknown_mutation()
        final_write = evidence["final_write"]
        if final_write["dispatched"] is not True:
            return {
                "classification": "preparatory",
                "commit_status": "none",
                "commit_evidence": evidence,
                "solve_readiness_receipt": receipt,
            }
        committed = final_write["solve_relevant_mutation_committed"]
        return {
            "classification": "terminal",
            "commit_status": (
                "unknown" if committed is None else "committed" if committed else "none"
            ),
            "commit_evidence": evidence,
            "solve_readiness_receipt": receipt,
        }
    if target.startswith("gh_"):
        return {
            "classification": "legacy",
            "commit_status": "committed" if result["success"] else "unknown",
            "commit_evidence": {
                "success": result["success"],
                "target_dispatched": True,
            },
            "solve_readiness_receipt": None,
        }
    return _unknown_mutation()


def _validate_mutation_projection(event: dict[str, Any]) -> None:
    if event["mutation"] != _expected_mutation(event):
        raise ValueError("mutation_projection_mismatch")


def _validate_event(value: Any, sequence: int, *, probe: bool = False) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _EVENT_KEYS:
        raise ValueError("invalid_event_shape")
    if value["sequence"] != sequence:
        raise ValueError("invalid_event_sequence")
    admitted_ingress = {"operator_probe"} if probe else {
        "canonical_gateway",
        "direct_dispatch",
    }
    if value["ingress"] not in admitted_ingress:
        raise ValueError("invalid_event_ingress")
    if not isinstance(value["target"], str) or not value["target"]:
        raise ValueError("invalid_event_target")
    if type(value["arguments"]) is not dict:
        raise ValueError("invalid_event_arguments")
    has_result = value["result"] is not None
    has_exception = value["exception"] is not None
    if has_result == has_exception:
        raise ValueError("invalid_event_outcome")
    if has_result and not _valid_result(value["result"]):
        raise ValueError("invalid_event_result")
    if has_exception and not _valid_exception(value["exception"]):
        raise ValueError("invalid_event_exception")
    dispatch = value["dispatch"]
    if type(dispatch) is not dict or set(dispatch) != {"status", "target_call_count"}:
        raise ValueError("invalid_event_dispatch")
    expected_counts = {
        "dispatched": 1,
        "refused_before_dispatch": 0,
        "unknown": None,
    }
    if dispatch["status"] not in expected_counts or dispatch["target_call_count"] != expected_counts[dispatch["status"]]:
        raise ValueError("invalid_event_dispatch")
    mutation = value["mutation"]
    if type(mutation) is not dict or set(mutation) != {
        "classification",
        "commit_status",
        "commit_evidence",
        "solve_readiness_receipt",
    }:
        raise ValueError("invalid_event_mutation")
    if mutation["classification"] not in {
        "observational",
        "terminal",
        "preparatory",
        "legacy",
        "unknown",
    } or mutation["commit_status"] not in {"none", "committed", "unknown"}:
        raise ValueError("invalid_event_mutation")
    if mutation["commit_evidence"] is not None and type(mutation["commit_evidence"]) is not dict:
        raise ValueError("invalid_event_mutation")
    receipt = mutation["solve_readiness_receipt"]
    if receipt is not None and not _valid_receipt(receipt):
        raise ValueError("invalid_event_receipt")
    if has_exception and (
        dispatch != {"status": "unknown", "target_call_count": None}
        or mutation["classification"] != "unknown"
        or mutation["commit_status"] != "unknown"
        or mutation["commit_evidence"] is not None
        or receipt is not None
    ):
        raise ValueError("invalid_exception_event")
    _validate_mutation_projection(value)
    return value


def _open_source(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[bytes]]:
    _, rows, raw_lines = _read_jsonl(path)
    if not rows:
        raise ValueError("source_log_empty")
    header = rows[0]
    if (
        type(header) is not dict
        or set(header) != {"schema", "row_emitter"}
        or header["schema"] != _SOURCE_SCHEMA
        or header["row_emitter"] not in {"prime_rook_adapter", "direct_transaction_wrapper"}
    ):
        raise ValueError("invalid_source_header")
    events: list[dict[str, Any]] = []
    for sequence, row in enumerate(rows[1:]):
        if type(row) is dict and row.get("type") == "closure":
            if sequence != len(rows) - 2:
                raise ValueError("event_after_closure")
            break
        events.append(_validate_event(row, sequence))
    expected_rows = 1 + len(events)
    return header, events, raw_lines[:expected_rows]


def append_source_event(path: Path, event: dict[str, Any]) -> None:
    """Append one canonical event to an existing unclosed source log."""

    path = Path(path)
    header, events, raw_lines = _open_source(path)
    _, all_rows, _ = _read_jsonl(path)
    if len(all_rows) != 1 + len(events):
        raise ValueError("source_log_closed")
    _validate_event(event, len(events))
    expected_ingress = (
        "canonical_gateway"
        if header["row_emitter"] == "prime_rook_adapter"
        else "direct_dispatch"
    )
    if event["ingress"] != expected_ingress:
        raise ValueError("row_emitter_ingress_mismatch")
    with path.open("ab") as stream:
        stream.write(canonical_json_bytes(event))
        stream.flush()
        os.fsync(stream.fileno())


def _closure(
    header: dict[str, Any],
    events: list[dict[str, Any]],
    source_payload: bytes,
    runtime_payload: bytes,
) -> dict[str, Any]:
    prime = header["row_emitter"] == "prime_rook_adapter"
    return {
        "schema": _CLOSURE_SCHEMA,
        "owner": "prime_transaction_launcher" if prime else "direct_transaction_wrapper",
        "row_emitter": header["row_emitter"],
        "source_event_count": len(events),
        "final_source_sequence": len(events) - 1 if events else None,
        "source_log_sha256": _sha(source_payload),
        "runtime_log_sha256": _sha(runtime_payload),
        "terminal_marker": "agent_end" if prime else "transaction_closed",
        "closed": True,
    }


def _append_closure(path: Path, closure: dict[str, Any]) -> None:
    with Path(path).open("ab") as stream:
        stream.write(canonical_json_bytes({"type": "closure", "source_closure": closure}))
        stream.flush()
        os.fsync(stream.fileno())


def seal_prime_source_log(
    source_path: Path,
    runtime_log_path: Path,
    process_state: dict[str, Any],
) -> dict[str, Any]:
    """Seal a Prime source log only after the runtime owner is terminal."""

    header, events, source_lines = _open_source(Path(source_path))
    _, all_source_rows, _ = _read_jsonl(Path(source_path))
    if header["row_emitter"] != "prime_rook_adapter" or len(all_source_rows) != 1 + len(events):
        raise ValueError("source_not_sealable")
    if type(process_state) is not dict or set(process_state) != {
        "terminated",
        "stdout_eof",
        "owned_child_pids",
        "exit_code",
    }:
        raise ValueError("invalid_process_state")
    if process_state["terminated"] is not True or process_state["stdout_eof"] is not True:
        raise ValueError("prime_not_terminal")
    if type(process_state["owned_child_pids"]) is not list or process_state["owned_child_pids"]:
        raise ValueError("prime_children_lingering")
    if type(process_state["exit_code"]) is not int:
        raise ValueError("invalid_exit_code")
    runtime_payload, runtime_rows, _ = _read_jsonl(Path(runtime_log_path))
    terminal_indices = [index for index, row in enumerate(runtime_rows) if type(row) is dict and row.get("type") == "agent_end"]
    if terminal_indices != [len(runtime_rows) - 1]:
        raise ValueError("invalid_prime_terminal_marker")
    source_payload = b"".join(source_lines)
    closure = _closure(header, events, source_payload, runtime_payload)
    _append_closure(Path(source_path), closure)
    return closure


def seal_direct_source_log(source_path: Path, runtime_log_path: Path) -> dict[str, Any]:
    """Seal a caller-owned direct transaction after its exact terminal marker."""

    header, events, source_lines = _open_source(Path(source_path))
    _, all_source_rows, _ = _read_jsonl(Path(source_path))
    if header["row_emitter"] != "direct_transaction_wrapper" or len(all_source_rows) != 1 + len(events):
        raise ValueError("source_not_sealable")
    runtime_payload, runtime_rows, _ = _read_jsonl(Path(runtime_log_path))
    expected_runtime = {
        "schema": _DIRECT_RUNTIME_SCHEMA,
        "source_event_count": len(events),
        "terminal_marker": "transaction_closed",
    }
    if runtime_rows != [expected_runtime]:
        raise ValueError("invalid_direct_terminal_marker")
    source_payload = b"".join(source_lines)
    closure = _closure(header, events, source_payload, runtime_payload)
    _append_closure(Path(source_path), closure)
    return closure


def _validate_closure(
    value: Any,
    header: dict[str, Any],
    events: list[dict[str, Any]],
    source_payload: bytes,
    runtime_payload: bytes,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _CLOSURE_KEYS:
        raise ValueError("invalid_source_closure")
    expected = _closure(header, events, source_payload, runtime_payload)
    if value != expected or _SHA.fullmatch(value["source_log_sha256"]) is None or _SHA.fullmatch(value["runtime_log_sha256"]) is None:
        raise ValueError("source_closure_mismatch")
    return value


def normalize_authoring_trace(source_path: Path, runtime_log_path: Path) -> dict[str, Any]:
    """Validate both retained raw logs and return their closed normalized trace."""

    source_payload, source_rows, source_lines = _read_jsonl(Path(source_path))
    runtime_payload, runtime_rows, _ = _read_jsonl(Path(runtime_log_path))
    if len(source_rows) < 2:
        raise ValueError("source_log_unclosed")
    header = source_rows[0]
    if type(header) is not dict or set(header) != {"schema", "row_emitter"} or header["schema"] != _SOURCE_SCHEMA:
        raise ValueError("invalid_source_header")
    closure_row = source_rows[-1]
    if type(closure_row) is not dict or set(closure_row) != {"type", "source_closure"} or closure_row["type"] != "closure":
        raise ValueError("source_log_unclosed")
    events = [_validate_event(row, index) for index, row in enumerate(source_rows[1:-1])]
    source_hashed_payload = b"".join(source_lines[:-1])
    closure = _validate_closure(closure_row["source_closure"], header, events, source_hashed_payload, runtime_payload)
    if header["row_emitter"] == "prime_rook_adapter":
        terminals = [index for index, row in enumerate(runtime_rows) if type(row) is dict and row.get("type") == "agent_end"]
        if terminals != [len(runtime_rows) - 1]:
            raise ValueError("invalid_prime_terminal_marker")
    elif header["row_emitter"] == "direct_transaction_wrapper":
        if runtime_rows != [{"schema": _DIRECT_RUNTIME_SCHEMA, "source_event_count": len(events), "terminal_marker": "transaction_closed"}]:
            raise ValueError("invalid_direct_terminal_marker")
    else:
        raise ValueError("invalid_row_emitter")
    return {"schema": _TRACE_SCHEMA, "source_closure": closure, "events": events}


def _artifact_error() -> ValueError:
    return ValueError("artifact_invalid")


def _finite_number(value: Any) -> bool:
    return _is_number(value)


def _validate_sequence_arguments(value: Any, roles: dict[str, str]) -> None:
    if type(value) is not dict or set(value) != {
        "axis",
        "start_role",
        "step_role",
        "count_role",
    }:
        raise _artifact_error()
    if value["axis"] not in {"x", "y", "z"}:
        raise _artifact_error()
    for key in ("start_role", "step_role"):
        if roles.get(value[key]) not in {"number", "integer"}:
            raise _artifact_error()
    if roles.get(value["count_role"]) != "integer":
        raise _artifact_error()


def validate_acceptance_artifact(value: Any) -> dict[str, Any]:
    """Validate and return one closed v1 acceptance artifact."""

    if type(value) is not dict or set(value) != {
        "schema",
        "intent",
        "numeric_tolerance",
        "controls",
        "output",
        "criteria",
    }:
        raise _artifact_error()
    if value["schema"] != _ARTIFACT_SCHEMA:
        raise _artifact_error()
    if not isinstance(value["intent"], str) or not value["intent"].strip():
        raise _artifact_error()
    tolerance = value["numeric_tolerance"]
    if not _finite_number(tolerance) or tolerance < 0:
        raise _artifact_error()
    controls = value["controls"]
    if type(controls) is not list or not controls:
        raise _artifact_error()
    roles: dict[str, str] = {}
    selectors: set[str] = set()
    for control in controls:
        if type(control) is not dict or set(control) != {
            "role",
            "selector",
            "value_kind",
            "probe_value",
        }:
            raise _artifact_error()
        role = control["role"]
        selector = control["selector"]
        kind = control["value_kind"]
        probe = control["probe_value"]
        if not isinstance(role, str) or _ROLE.fullmatch(role) is None or role in roles:
            raise _artifact_error()
        if (
            type(selector) is not dict
            or set(selector) != {"kind", "value"}
            or selector["kind"] != "exact_nickname"
            or not isinstance(selector["value"], str)
            or not selector["value"].strip()
            or selector["value"] in selectors
        ):
            raise _artifact_error()
        if kind not in {"number", "integer"} or not _finite_number(probe):
            raise _artifact_error()
        if kind == "integer" and (type(probe) is not int or not -(2**31) <= probe <= 2**31 - 1):
            raise _artifact_error()
        roles[role] = kind
        selectors.add(selector["value"])
    output = value["output"]
    if (
        type(output) is not dict
        or set(output) != {"kind", "require_complete_multiset", "max_preview_items"}
        or output["kind"] != "terminal_points"
        or output["require_complete_multiset"] is not True
        or not _is_int(output["max_preview_items"], minimum=1, maximum=1000)
    ):
        raise _artifact_error()
    criteria = value["criteria"]
    if type(criteria) is not list or not criteria:
        raise _artifact_error()
    criterion_ids: set[str] = set()
    for criterion in criteria:
        if type(criterion) is not dict or set(criterion) != {"id", "predicate", "arguments"}:
            raise _artifact_error()
        criterion_id = criterion["id"]
        predicate = criterion["predicate"]
        arguments = criterion["arguments"]
        if not isinstance(criterion_id, str) or _CRITERION.fullmatch(criterion_id) is None or criterion_id in criterion_ids:
            raise _artifact_error()
        criterion_ids.add(criterion_id)
        if predicate == "controls_present":
            if type(arguments) is not dict or set(arguments) != {"roles"}:
                raise _artifact_error()
            selected = arguments["roles"]
            if type(selected) is not list or not selected or len(set(selected)) != len(selected) or any(role not in roles for role in selected):
                raise _artifact_error()
        elif predicate == "diagnostics_errors_equal":
            if type(arguments) is not dict or set(arguments) != {"value"} or not _is_int(arguments["value"], maximum=2**31 - 1):
                raise _artifact_error()
        elif predicate == "point_count_equals_control":
            if type(arguments) is not dict or set(arguments) != {"role"} or roles.get(arguments["role"]) != "integer":
                raise _artifact_error()
        elif predicate == "point_count_equals_product":
            if type(arguments) is not dict or set(arguments) != {"roles"}:
                raise _artifact_error()
            selected = arguments["roles"]
            if type(selected) is not list or not selected or len(set(selected)) != len(selected) or any(roles.get(role) != "integer" for role in selected):
                raise _artifact_error()
        elif predicate == "axis_values_equal_sequence":
            _validate_sequence_arguments(arguments, roles)
        elif predicate == "axes_form_cartesian_product":
            if type(arguments) is not dict or set(arguments) != {"sequences"} or type(arguments["sequences"]) is not list or not arguments["sequences"]:
                raise _artifact_error()
            axes: list[str] = []
            for sequence in arguments["sequences"]:
                _validate_sequence_arguments(sequence, roles)
                axes.append(sequence["axis"])
            if len(set(axes)) != len(axes):
                raise _artifact_error()
        elif predicate == "axis_equals_constant":
            if (
                type(arguments) is not dict
                or set(arguments) != {"axis", "value"}
                or arguments["axis"] not in {"x", "y", "z"}
                or not _finite_number(arguments["value"])
            ):
                raise _artifact_error()
        else:
            raise _artifact_error()
    return value


def _valid_receipt(value: Any, *, ready: bool | None = None) -> bool:
    if type(value) is not dict or set(value) != _RECEIPT_KEYS:
        return False
    if value["schema"] != _RECEIPT_SCHEMA:
        return False
    if not isinstance(value["receipt_id"], str) or not value["receipt_id"]:
        return False
    if not isinstance(value["document_session_id"], str) or not value["document_session_id"]:
        return False
    if not _is_int(value["mutation_epoch"]):
        return False
    if value["solution_run_epoch"] is not None and not _is_int(value["solution_run_epoch"]):
        return False
    if not _is_int(value["completed_solution_run_epoch"]):
        return False
    if value["status"] not in {
        "pending",
        "ready",
        "superseded",
        "document_replaced",
        "solver_locked",
        "unknown",
    }:
        return False
    if not isinstance(value["issued_at"], str) or not value["issued_at"]:
        return False
    for key in ("reason", "completion_signal", "completed_at"):
        if value[key] is not None and not isinstance(value[key], str):
            return False
    if value["status"] == "ready":
        if (
            value["solution_run_epoch"] is None
            or value["completed_solution_run_epoch"] != value["solution_run_epoch"]
            or not isinstance(value["completion_signal"], str)
            or not value["completion_signal"]
            or not isinstance(value["completed_at"], str)
            or not value["completed_at"]
        ):
            return False
    elif value["status"] == "pending":
        if value["completion_signal"] is not None or value["completed_at"] is not None:
            return False
    if ready is True and value["status"] != "ready":
        return False
    if ready is False and value["status"] == "ready":
        return False
    return True


def _valid_issued_receipt(value: Any) -> bool:
    return _valid_receipt(value) and value["status"] in {"pending", "ready"}


def _validate_authoring_trace(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"schema", "source_closure", "events"} or value["schema"] != _TRACE_SCHEMA:
        raise ValueError("authoring_trace_invalid")
    closure = value["source_closure"]
    events = value["events"]
    if type(closure) is not dict or set(closure) != _CLOSURE_KEYS or closure["schema"] != _CLOSURE_SCHEMA or closure["closed"] is not True:
        raise ValueError("authoring_trace_invalid")
    if closure["owner"] not in {"prime_transaction_launcher", "direct_transaction_wrapper"}:
        raise ValueError("authoring_trace_invalid")
    owner_fields = {
        "prime_transaction_launcher": ("prime_rook_adapter", "agent_end"),
        "direct_transaction_wrapper": ("direct_transaction_wrapper", "transaction_closed"),
    }
    if (closure["row_emitter"], closure["terminal_marker"]) != owner_fields[closure["owner"]]:
        raise ValueError("authoring_trace_invalid")
    if _SHA.fullmatch(closure["source_log_sha256"]) is None or _SHA.fullmatch(closure["runtime_log_sha256"]) is None:
        raise ValueError("authoring_trace_invalid")
    if type(events) is not list or not _is_int(closure["source_event_count"]) or closure["source_event_count"] != len(events):
        raise ValueError("authoring_trace_invalid")
    expected_final = len(events) - 1 if events else None
    if closure["final_source_sequence"] != expected_final:
        raise ValueError("authoring_trace_invalid")
    try:
        for sequence, event in enumerate(events):
            _validate_event(event, sequence)
    except ValueError as exc:
        raise ValueError("authoring_trace_invalid") from exc
    return value


def _latest_terminal_receipt(trace: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    selected: dict[str, Any] | None = None
    selected_index = -1
    for index, event in enumerate(trace["events"]):
        if event["exception"] is not None:
            return None, "authoring_trace_invalid"
        mutation = event["mutation"]
        if mutation["classification"] == "terminal" and mutation["commit_status"] == "committed":
            receipt = mutation["solve_readiness_receipt"]
            if not _valid_receipt(receipt):
                return None, "latest_terminal_receipt_missing"
            if receipt["status"] not in {"pending", "ready"}:
                return None, "receipt_correlation_failed"
            selected = receipt
            selected_index = index
    if selected is None:
        return None, "latest_terminal_receipt_missing"
    for event in trace["events"][selected_index + 1 :]:
        mutation = event["mutation"]
        if mutation["classification"] == "observational":
            continue
        return None, "later_unfenced_mutation"
    return selected, None


def _exception_value(exc: Exception) -> dict[str, str]:
    return {
        "type": f"{exc.__class__.__module__}.{exc.__class__.__qualname__}",
        "message": str(exc),
    }


def _operator_event(
    sequence: int,
    target: str,
    arguments: dict[str, Any],
    *,
    result: dict[str, Any] | None = None,
    exception: Exception | None = None,
) -> dict[str, Any]:
    if exception is not None:
        return {
            "sequence": sequence,
            "ingress": "operator_probe",
            "target": target,
            "arguments": arguments,
            "result": None,
            "exception": _exception_value(exception),
            "dispatch": {"status": "unknown", "target_call_count": None},
            "mutation": {
                "classification": "unknown",
                "commit_status": "unknown",
                "commit_evidence": None,
                "solve_readiness_receipt": None,
            },
        }
    assert result is not None
    event = {
        "sequence": sequence,
        "ingress": "operator_probe",
        "target": target,
        "arguments": arguments,
        "result": result,
        "exception": None,
        "dispatch": {"status": "dispatched", "target_call_count": 1},
        "mutation": _unknown_mutation(),
    }
    event["mutation"] = _expected_mutation(event)
    return event


def _ready_wait_outcome(
    result: Any,
    issued: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if not _valid_result(result) or result["success"] is not True:
        return None, "wait_failed"
    data = result["data"]
    if type(data) is not dict or set(data) != {"schema", "wait_status", "receipt"} or data["schema"] != _WAIT_SCHEMA or data["wait_status"] != "ready":
        return None, "wait_failed"
    receipt = data["receipt"]
    if not _valid_receipt(receipt, ready=True):
        return None, "wait_failed"
    for key in ("receipt_id", "document_session_id", "mutation_epoch"):
        if receipt[key] != issued[key]:
            return None, "receipt_correlation_failed"
    return receipt, None


def _correlated_ready_wait(result: Any, issued: dict[str, Any]) -> dict[str, Any] | None:
    return _ready_wait_outcome(result, issued)[0]


def _correlated_snapshot_data(result: Any, ready_receipt: dict[str, Any]) -> dict[str, Any] | None:
    if not _valid_result(result) or result["success"] is not True or type(result["data"]) is not dict:
        return None
    data = result["data"]
    fence = data.get("readiness_fence")
    if type(fence) is not dict or set(fence) != {
        "readiness_receipt_id",
        "document_session_id",
        "mutation_epoch",
        "solution_run_epoch",
        "completed_solution_run_epoch",
    }:
        return None
    expected = {
        "readiness_receipt_id": ready_receipt["receipt_id"],
        "document_session_id": ready_receipt["document_session_id"],
        "mutation_epoch": ready_receipt["mutation_epoch"],
        "solution_run_epoch": ready_receipt["solution_run_epoch"],
        "completed_solution_run_epoch": ready_receipt["completed_solution_run_epoch"],
    }
    return data if fence == expected else None


def _numeric_id(value: str, pattern: re.Pattern[str]) -> int:
    if pattern.fullmatch(value) is None:
        raise ValueError("invalid_short_id")
    return int(value[1:])


def _slider_value(component: Any) -> dict[str, Any] | None:
    if type(component) is not dict or component.get("type") != "NumberSlider":
        return None
    value = component.get("value")
    if type(value) is not dict or set(value) != {"type", "val", "min", "max"} or value["type"] != "slider":
        return None
    if any(not _finite_number(value[key]) for key in ("val", "min", "max")):
        return None
    if not value["min"] < value["max"] or not value["min"] <= value["val"] <= value["max"]:
        return None
    return {"type": "slider", "val": value["val"], "min": value["min"], "max": value["max"]}


def _bind_controls(artifact: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]] | None:
    components = data.get("components")
    if type(components) is not list:
        return None
    bound: list[dict[str, Any]] = []
    for definition in artifact["controls"]:
        nickname = definition["selector"]["value"]
        matches = [
            component
            for component in components
            if type(component) is dict
            and component.get("type") == "NumberSlider"
            and component.get("nick") == nickname
        ]
        if len(matches) != 1:
            return None
        component = matches[0]
        component_id = component.get("id")
        value = _slider_value(component)
        if not isinstance(component_id, str) or _COMPONENT_ID.fullmatch(component_id) is None or value is None:
            return None
        if definition["value_kind"] == "integer" and any(
            not float(value[key]).is_integer() or not -(2**31) <= value[key] <= 2**31 - 1
            for key in ("val", "min", "max")
        ):
            return None
        bound.append(
            {
                "role": definition["role"],
                "component_id": component_id,
                "type": "NumberSlider",
                "nickname": nickname,
                "value": value,
            }
        )
    return bound


def _terminal_output(data: dict[str, Any], bound: int) -> dict[str, Any] | None:
    flows = data.get("flows")
    outputs = data.get("behavioral_point_outputs")
    if type(flows) is not list or type(outputs) is not list:
        return None
    used_sources: set[tuple[str, int]] = set()
    for flow in flows:
        if not isinstance(flow, str):
            return None
        match = _FLOW.fullmatch(flow)
        if match is None:
            return None
        used_sources.add((match.group(1), int(match.group(2))))
    candidates: list[dict[str, Any]] = []
    for output in outputs:
        if type(output) is not dict or set(output) != {
            "component_id",
            "output_index",
            "output_name",
            "count",
            "complete",
            "points",
            "error",
        }:
            return None
        component_id = output["component_id"]
        output_index = output["output_index"]
        if not isinstance(component_id, str) or _COMPONENT_ID.fullmatch(component_id) is None or not _is_int(output_index):
            return None
        if (component_id, output_index) in used_sources:
            continue
        if not isinstance(output["output_name"], str) or output["complete"] is not True or output["error"] is not None:
            return None
        if (
            not _is_int(output["count"], minimum=1)
            or output["count"] > bound
            or type(output["points"]) is not list
            or not output["points"]
            or len(output["points"]) != output["count"]
        ):
            return None
        points: list[list[int | float]] = []
        for point in output["points"]:
            if type(point) is not list or len(point) != 3 or any(not _finite_number(coordinate) for coordinate in point):
                return None
            points.append([point[0], point[1], point[2]])
        candidates.append(
            {
                "component_id": component_id,
                "output_index": output_index,
                "output_name": output["output_name"],
                "count": output["count"],
                "points": sorted(points, key=lambda point: (point[0], point[1], point[2])),
            }
        )
    return candidates[0] if len(candidates) == 1 else None


def _snapshot_projection(
    artifact: dict[str, Any],
    data: dict[str, Any],
    *,
    bound_controls: list[dict[str, Any]] | None = None,
    terminal_output: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if bound_controls is None:
        bound_controls = _bind_controls(artifact, data)
    if terminal_output is None:
        terminal_output = _terminal_output(data, artifact["output"]["max_preview_items"])
    if bound_controls is None or terminal_output is None:
        return None
    raw_components = data.get("components")
    flows = data.get("flows")
    groups = data.get("groups", [])
    relays = data.get("relays", [])
    diagnostics = data.get("diagnostics")
    if type(raw_components) is not list or type(flows) is not list or type(groups) is not list or type(relays) is not list or type(diagnostics) is not dict:
        return None
    components: list[dict[str, Any]] = []
    seen_component_ids: set[str] = set()
    for component in raw_components:
        if type(component) is not dict:
            return None
        component_id = component.get("id")
        component_type = component.get("type")
        if not isinstance(component_id, str) or _COMPONENT_ID.fullmatch(component_id) is None or component_id in seen_component_ids or not isinstance(component_type, str):
            return None
        seen_component_ids.add(component_id)
        nickname = component.get("nick") if "nick" in component else component.get("name")
        if nickname is not None and not isinstance(nickname, str):
            return None
        guid = component.get("componentGuid")
        if guid is not None and (not isinstance(guid, str) or _GUID.fullmatch(guid) is None):
            return None
        components.append(
            {
                "component_id": component_id,
                "type": component_type,
                "nickname": nickname,
                "component_type_guid": guid,
            }
        )
    components.sort(key=lambda item: _numeric_id(item["component_id"], _COMPONENT_ID))
    if terminal_output["component_id"] not in seen_component_ids:
        return None
    projected_groups: list[dict[str, Any]] = []
    seen_group_ids: set[str] = set()
    for group in groups:
        if type(group) is not dict:
            return None
        group_id = group.get("id")
        if (
            not isinstance(group_id, str)
            or _GROUP_ID.fullmatch(group_id) is None
            or group_id in seen_group_ids
        ):
            return None
        seen_group_ids.add(group_id)
        projected = {
            "id": group_id,
            "nick": group.get("nick"),
            "description": group.get("description"),
            "colour": group.get("colour"),
            "members": group.get("members"),
        }
        if any(projected[key] is not None and not isinstance(projected[key], str) for key in ("nick", "description", "colour")):
            return None
        if type(projected["members"]) is not list or any(not isinstance(member, str) or _COMPONENT_ID.fullmatch(member) is None for member in projected["members"]) or len(set(projected["members"])) != len(projected["members"]):
            return None
        projected["members"] = sorted(projected["members"])
        projected_groups.append(projected)
    projected_groups.sort(key=lambda item: _numeric_id(item["id"], _GROUP_ID))
    if (
        any(
            not isinstance(relay, str) or _COMPONENT_ID.fullmatch(relay) is None
            for relay in relays
        )
        or len(set(relays)) != len(relays)
    ):
        return None
    admitted_flow_ids = seen_component_ids | set(relays)
    if len(set(flows)) != len(flows):
        return None
    for flow in flows:
        match = _FLOW.fullmatch(flow) if isinstance(flow, str) else None
        if (
            match is None
            or match.group(1) not in admitted_flow_ids
            or match.group(3) not in admitted_flow_ids
        ):
            return None
    if seen_component_ids & set(relays):
        return None
    expected_diag_keys = {"total", "errors", "warnings"}
    if not expected_diag_keys <= set(diagnostics):
        return None
    for key in expected_diag_keys:
        if not _is_int(diagnostics[key]):
            return None
    error_ids = diagnostics.get("error_ids") or []
    warning_ids = diagnostics.get("warning_ids") or []
    if (
        type(error_ids) is not list
        or type(warning_ids) is not list
        or any(
            not isinstance(value, str) or _COMPONENT_ID.fullmatch(value) is None
            for value in error_ids + warning_ids
        )
    ):
        return None
    if len(set(error_ids)) != len(error_ids) or len(set(warning_ids)) != len(warning_ids):
        return None
    return {
        "schema": _PROJECTION_SCHEMA,
        "controls": bound_controls,
        "components": components,
        "flows": sorted(flows),
        "groups": projected_groups,
        "relays": sorted(relays),
        "terminal_output": terminal_output,
        "diagnostics": {
            "total": diagnostics["total"],
            "errors": diagnostics["errors"],
            "warnings": diagnostics["warnings"],
            "error_ids": sorted(error_ids),
            "warning_ids": sorted(warning_ids),
        },
    }


def _snapshot_evidence(
    artifact: dict[str, Any],
    receipt: dict[str, Any],
    result: dict[str, Any],
) -> tuple[tuple[dict[str, Any], str] | None, str | None]:
    data = _correlated_snapshot_data(result, receipt)
    if data is None:
        return None, "receipt_correlation_failed"
    bound_controls = _bind_controls(artifact, data)
    if bound_controls is None:
        return None, "control_binding_failed"
    terminal_output = _terminal_output(data, artifact["output"]["max_preview_items"])
    if terminal_output is None:
        return None, "output_incomplete"
    projection = _snapshot_projection(
        artifact,
        data,
        bound_controls=bound_controls,
        terminal_output=terminal_output,
    )
    if projection is None:
        return None, "projection_failed"
    evidence = {
        "schema": _SNAPSHOT_EVIDENCE_SCHEMA,
        "request": {
            "include_data": True,
            "max_preview_items": artifact["output"]["max_preview_items"],
            "readiness_receipt_id": receipt["receipt_id"],
        },
        "result": result,
    }
    return (projection, _sha(canonical_json_bytes(evidence))), None


async def run_behavioral_probe(
    artifact: dict[str, Any],
    authoring_trace: dict[str, Any],
    executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Run the sole reviewed probe sequence through an injected executor."""

    try:
        artifact = validate_acceptance_artifact(artifact)
    except (TypeError, ValueError):
        return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "artifact_invalid"}, "events": []}
    try:
        trace = _validate_authoring_trace(authoring_trace)
    except (TypeError, ValueError):
        return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "authoring_trace_invalid"}, "events": []}
    issued_receipt, error = _latest_terminal_receipt(trace)
    if error is not None:
        return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": error}, "events": []}
    assert issued_receipt is not None
    events: list[dict[str, Any]] = []
    malformed_executor_result = False

    async def call(name: str, arguments: dict[str, Any], error_token: str) -> dict[str, Any] | None:
        nonlocal malformed_executor_result
        try:
            result = await executor(name, arguments)
        except Exception as exc:
            events.append(_operator_event(len(events), name, arguments, exception=exc))
            return None
        if not _valid_result(result):
            malformed_executor_result = True
            return None
        events.append(_operator_event(len(events), name, arguments, result=result))
        return result

    async def wait_and_snapshot(
        receipt: dict[str, Any],
        wait_error: str,
        snapshot_error: str,
    ) -> tuple[tuple[dict[str, Any], str, dict[str, Any]] | None, str | None]:
        wait_arguments = {"readiness_receipt_id": receipt["receipt_id"], "timeout_ms": 10_000}
        wait_result = await call("gh_wait_for_solve_readiness", wait_arguments, wait_error)
        if wait_result is None:
            return None, "probe_trace_invalid" if malformed_executor_result else wait_error
        ready_receipt, wait_outcome = _ready_wait_outcome(wait_result, receipt)
        if ready_receipt is None:
            return None, "receipt_correlation_failed" if wait_outcome == "receipt_correlation_failed" else wait_error
        snapshot_arguments = {
            "include_data": True,
            "max_preview_items": artifact["output"]["max_preview_items"],
            "readiness_receipt_id": ready_receipt["receipt_id"],
        }
        snapshot_result = await call("gh_snapshot", snapshot_arguments, snapshot_error)
        if snapshot_result is None:
            return None, "probe_trace_invalid" if malformed_executor_result else snapshot_error
        if snapshot_result["success"] is not True:
            return None, snapshot_error
        evidence, evidence_error = _snapshot_evidence(artifact, ready_receipt, snapshot_result)
        if evidence is None:
            if evidence_error == "projection_failed":
                return None, snapshot_error
            return None, evidence_error
        projection, snapshot_hash = evidence
        return (projection, snapshot_hash, ready_receipt), None

    baseline, baseline_error = await wait_and_snapshot(issued_receipt, "baseline_wait_failed", "baseline_snapshot_failed")
    if baseline is None:
        return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": baseline_error}, "events": events}
    baseline_projection, _, _ = baseline
    baseline_bytes = canonical_json_bytes(baseline_projection)
    baseline_controls = {control["role"]: control for control in baseline_projection["controls"]}
    used_receipt_ids = {issued_receipt["receipt_id"]}

    for definition in artifact["controls"]:
        role = definition["role"]
        baseline_control = baseline_controls.get(role)
        if baseline_control is None:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "control_binding_failed"}, "events": events}
        original = baseline_control["value"]["val"]
        probe_value = definition["probe_value"]
        if not baseline_control["value"]["min"] <= probe_value <= baseline_control["value"]["max"] or probe_value == original:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "probe_value_invalid"}, "events": events}
        if definition["value_kind"] == "integer" and type(probe_value) is not int:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "probe_value_invalid"}, "events": events}
        set_arguments = {"component": baseline_control["component_id"], "value": probe_value}
        set_result = await call("gh_set_value", set_arguments, "perturbation_dispatch_failed")
        if set_result is None:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "probe_trace_invalid" if malformed_executor_result else "perturbation_dispatch_failed"}, "events": events}
        if set_result["success"] is not True:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "perturbation_dispatch_failed"}, "events": events}
        data = set_result["data"]
        perturb_receipt = data.get("solve_readiness_receipt") if type(data) is dict else None
        if type(data) is not dict or data.get("solve_relevant_mutation_committed") is not True or not _valid_issued_receipt(perturb_receipt):
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "perturbation_receipt_invalid"}, "events": events}
        if perturb_receipt["receipt_id"] in used_receipt_ids:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "perturbation_receipt_invalid"}, "events": events}
        used_receipt_ids.add(perturb_receipt["receipt_id"])
        perturbed, perturb_error = await wait_and_snapshot(perturb_receipt, "perturbation_wait_failed", "perturbation_snapshot_failed")
        if perturbed is None:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": perturb_error}, "events": events}
        perturbed_projection = perturbed[0]
        perturbed_controls = {control["role"]: control for control in perturbed_projection["controls"]}
        expected_controls = {
            key: (
                control | {"value": control["value"] | {"val": probe_value}}
                if key == role
                else control
            )
            for key, control in baseline_controls.items()
        }
        if perturbed_controls != expected_controls:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "perturbation_control_mismatch"}, "events": events}
        restore_arguments = {"component": baseline_control["component_id"], "value": original}
        restore_result = await call("gh_set_value", restore_arguments, "restoration_dispatch_failed")
        if restore_result is None:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "probe_trace_invalid" if malformed_executor_result else "restoration_dispatch_failed"}, "events": events}
        if restore_result["success"] is not True:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "restoration_dispatch_failed"}, "events": events}
        restore_data = restore_result["data"]
        restore_receipt = restore_data.get("solve_readiness_receipt") if type(restore_data) is dict else None
        if (
            type(restore_data) is not dict
            or restore_data.get("solve_relevant_mutation_committed") is not True
            or not _valid_issued_receipt(restore_receipt)
            or restore_receipt["receipt_id"] in used_receipt_ids
        ):
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "restoration_receipt_invalid"}, "events": events}
        used_receipt_ids.add(restore_receipt["receipt_id"])
        restored, restore_error = await wait_and_snapshot(restore_receipt, "restoration_wait_failed", "restoration_snapshot_failed")
        if restored is None:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": restore_error}, "events": events}
        if canonical_json_bytes(restored[0]) != baseline_bytes:
            return {"schema": _PROBE_SCHEMA, "termination": {"status": "failed", "error": "restoration_mismatch"}, "events": events}
    return {"schema": _PROBE_SCHEMA, "termination": {"status": "complete", "error": None}, "events": events}


def _validate_probe_trace(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"schema", "termination", "events"} or value["schema"] != _PROBE_SCHEMA:
        raise ValueError("probe_trace_invalid")
    termination = value["termination"]
    if type(termination) is not dict or set(termination) != {"status", "error"} or termination["status"] not in {"complete", "failed"}:
        raise ValueError("probe_trace_invalid")
    if termination["status"] == "complete":
        if termination["error"] is not None:
            raise ValueError("probe_trace_invalid")
    elif termination["error"] not in _PROBE_ERRORS:
        raise ValueError("probe_trace_invalid")
    events = value["events"]
    if type(events) is not list:
        raise ValueError("probe_trace_invalid")
    try:
        for sequence, event in enumerate(events):
            _validate_event(event, sequence, probe=True)
    except ValueError as exc:
        raise ValueError("probe_trace_invalid") from exc
    return value


def _successful_event_result(event: dict[str, Any]) -> dict[str, Any] | None:
    result = event["result"]
    return result if _valid_result(result) and result["success"] is True else None


def _parse_complete_probe(
    artifact: dict[str, Any],
    authoring_trace: dict[str, Any],
    trace: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    events = trace["events"]
    expected_count = 2 + len(artifact["controls"]) * 6
    if trace["termination"] != {"status": "complete", "error": None} or len(events) != expected_count:
        return None
    cursor = 0

    def next_event(target: str) -> dict[str, Any] | None:
        nonlocal cursor
        if cursor >= len(events) or events[cursor]["target"] != target:
            return None
        event = events[cursor]
        cursor += 1
        return event

    baseline_wait = next_event("gh_wait_for_solve_readiness")
    baseline_snapshot = next_event("gh_snapshot")
    if baseline_wait is None or baseline_snapshot is None:
        return None
    wait_result = _successful_event_result(baseline_wait)
    snapshot_result = _successful_event_result(baseline_snapshot)
    if wait_result is None or snapshot_result is None:
        return None
    wait_data = wait_result["data"]
    if type(wait_data) is not dict:
        return None
    baseline_receipt = wait_data.get("receipt")
    if not _valid_receipt(baseline_receipt, ready=True):
        return None
    issued_receipt, admission_error = _latest_terminal_receipt(authoring_trace)
    if admission_error is not None or issued_receipt is None:
        return None
    if baseline_wait["arguments"] != {
        "readiness_receipt_id": issued_receipt["receipt_id"],
        "timeout_ms": 10_000,
    } or _correlated_ready_wait(wait_result, issued_receipt) != baseline_receipt:
        return None
    if baseline_snapshot["arguments"] != {
        "include_data": True,
        "max_preview_items": artifact["output"]["max_preview_items"],
        "readiness_receipt_id": baseline_receipt["receipt_id"],
    }:
        return None
    baseline_evidence, baseline_error = _snapshot_evidence(artifact, baseline_receipt, snapshot_result)
    if baseline_evidence is None:
        return None
    baseline_projection, baseline_hash = baseline_evidence
    phases: list[dict[str, Any]] = [
        {
            "id": "baseline",
            "projection": baseline_projection,
            "readiness_receipt_id": baseline_receipt["receipt_id"],
            "snapshot_sha256": baseline_hash,
        }
    ]
    baseline_controls = {control["role"]: control for control in baseline_projection["controls"]}
    controls: list[dict[str, Any]] = []
    used_receipt_ids = {issued_receipt["receipt_id"]}
    for definition in artifact["controls"]:
        role = definition["role"]
        baseline_control = baseline_controls.get(role)
        if baseline_control is None:
            return None
        original = baseline_control["value"]["val"]
        set_event = next_event("gh_set_value")
        wait_event = next_event("gh_wait_for_solve_readiness")
        snapshot_event = next_event("gh_snapshot")
        restore_event = next_event("gh_set_value")
        restore_wait_event = next_event("gh_wait_for_solve_readiness")
        restore_snapshot_event = next_event("gh_snapshot")
        if None in (set_event, wait_event, snapshot_event, restore_event, restore_wait_event, restore_snapshot_event):
            return None
        assert set_event is not None and wait_event is not None and snapshot_event is not None
        assert restore_event is not None and restore_wait_event is not None and restore_snapshot_event is not None
        if set_event["arguments"] != {"component": baseline_control["component_id"], "value": definition["probe_value"]}:
            return None
        if restore_event["arguments"] != {"component": baseline_control["component_id"], "value": original}:
            return None
        perturb_result = _successful_event_result(set_event)
        perturb_wait_result = _successful_event_result(wait_event)
        perturb_snapshot_result = _successful_event_result(snapshot_event)
        restore_result = _successful_event_result(restore_event)
        restore_wait_result = _successful_event_result(restore_wait_event)
        restore_snapshot_result = _successful_event_result(restore_snapshot_event)
        if None in (perturb_result, perturb_wait_result, perturb_snapshot_result, restore_result, restore_wait_result, restore_snapshot_result):
            return None
        assert perturb_result is not None and restore_result is not None
        perturb_data = perturb_result["data"]
        restore_data = restore_result["data"]
        if type(perturb_data) is not dict or type(restore_data) is not dict:
            return None
        perturb_issued = perturb_data.get("solve_readiness_receipt")
        restore_issued = restore_data.get("solve_readiness_receipt")
        if (
            perturb_data.get("solve_relevant_mutation_committed") is not True
            or restore_data.get("solve_relevant_mutation_committed") is not True
            or not _valid_issued_receipt(perturb_issued)
            or not _valid_issued_receipt(restore_issued)
            or perturb_issued["receipt_id"] in used_receipt_ids
            or restore_issued["receipt_id"] in used_receipt_ids
            or perturb_issued["receipt_id"] == restore_issued["receipt_id"]
        ):
            return None
        used_receipt_ids.update(
            {perturb_issued["receipt_id"], restore_issued["receipt_id"]}
        )
        assert perturb_wait_result is not None and restore_wait_result is not None
        perturb_ready = _correlated_ready_wait(perturb_wait_result, perturb_issued)
        restore_ready = _correlated_ready_wait(restore_wait_result, restore_issued)
        if perturb_ready is None or restore_ready is None:
            return None
        if wait_event["arguments"] != {"readiness_receipt_id": perturb_issued["receipt_id"], "timeout_ms": 10_000}:
            return None
        if restore_wait_event["arguments"] != {"readiness_receipt_id": restore_issued["receipt_id"], "timeout_ms": 10_000}:
            return None
        expected_perturb_snapshot = {
            "include_data": True,
            "max_preview_items": artifact["output"]["max_preview_items"],
            "readiness_receipt_id": perturb_ready["receipt_id"],
        }
        expected_restore_snapshot = expected_perturb_snapshot | {
            "readiness_receipt_id": restore_ready["receipt_id"]
        }
        if snapshot_event["arguments"] != expected_perturb_snapshot or restore_snapshot_event["arguments"] != expected_restore_snapshot:
            return None
        assert perturb_snapshot_result is not None and restore_snapshot_result is not None
        perturb_evidence, perturb_error = _snapshot_evidence(artifact, perturb_ready, perturb_snapshot_result)
        restore_evidence, restore_error = _snapshot_evidence(artifact, restore_ready, restore_snapshot_result)
        if perturb_evidence is None or restore_evidence is None:
            return None
        perturb_projection, perturb_hash = perturb_evidence
        restore_projection, restore_hash = restore_evidence
        perturbed_controls = {
            control["role"]: control for control in perturb_projection["controls"]
        }
        expected_controls = {
            key: (
                control
                | {"value": control["value"] | {"val": definition["probe_value"]}}
                if key == role
                else control
            )
            for key, control in baseline_controls.items()
        }
        if perturbed_controls != expected_controls:
            return None
        if canonical_json_bytes(restore_projection) != canonical_json_bytes(baseline_projection):
            return None
        phases.extend(
            [
                {
                    "id": f"perturbation:{role}",
                    "projection": perturb_projection,
                    "readiness_receipt_id": perturb_ready["receipt_id"],
                    "snapshot_sha256": perturb_hash,
                },
                {
                    "id": f"restoration:{role}",
                    "projection": restore_projection,
                    "readiness_receipt_id": restore_ready["receipt_id"],
                    "snapshot_sha256": restore_hash,
                },
            ]
        )
        controls.append(
            {
                "role": role,
                "component_id": baseline_control["component_id"],
                "original_value": original,
                "probe_value": definition["probe_value"],
                "perturbation": {
                    "readiness_receipt_id": perturb_ready["receipt_id"],
                    "snapshot_sha256": perturb_hash,
                },
                "restoration": {
                    "readiness_receipt_id": restore_ready["receipt_id"],
                    "snapshot_sha256": restore_hash,
                    "restored": True,
                },
            }
        )
    if cursor != len(events):
        return None
    return {
        "status": "complete",
        "baseline": {
            "readiness_receipt_id": baseline_receipt["receipt_id"],
            "snapshot_sha256": baseline_hash,
        },
        "controls": controls,
        "error": None,
    }, phases


def _retained_probe_prefix(
    artifact: dict[str, Any],
    authoring_trace: dict[str, Any],
    trace: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Authenticate the exact first failure and retain only completed phases."""

    if trace["termination"]["status"] != "failed":
        raise ValueError("probe_trace_invalid")
    result = {
        "status": "incomplete",
        "baseline": None,
        "controls": [],
        "error": trace["termination"]["error"],
    }
    phases: list[dict[str, Any]] = []
    events = trace["events"]
    cursor = 0

    def finish(error: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if trace["termination"]["error"] != error or cursor != len(events):
            raise ValueError("probe_trace_invalid")
        result["error"] = error
        return result, phases

    def call(
        target: str,
        arguments: dict[str, Any],
        failure: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        nonlocal cursor
        if cursor == len(events):
            return None, "probe_trace_invalid"
        event = events[cursor]
        if event["target"] != target or event["arguments"] != arguments:
            raise ValueError("probe_trace_invalid")
        cursor += 1
        if event["exception"] is not None:
            return None, failure
        event_result = event["result"]
        if not _valid_result(event_result) or event_result["success"] is not True:
            return None, failure
        return event_result, None

    def wait_and_snapshot(
        issued_receipt: dict[str, Any],
        wait_failure: str,
        snapshot_failure: str,
    ) -> tuple[tuple[dict[str, Any], str, dict[str, Any]] | None, str | None]:
        wait_result, failure = call(
            "gh_wait_for_solve_readiness",
            {
                "readiness_receipt_id": issued_receipt["receipt_id"],
                "timeout_ms": 10_000,
            },
            wait_failure,
        )
        if wait_result is None:
            return None, failure
        ready, wait_outcome = _ready_wait_outcome(wait_result, issued_receipt)
        if ready is None:
            return None, (
                "receipt_correlation_failed"
                if wait_outcome == "receipt_correlation_failed"
                else wait_failure
            )
        snapshot_result, failure = call(
            "gh_snapshot",
            {
                "include_data": True,
                "max_preview_items": artifact["output"]["max_preview_items"],
                "readiness_receipt_id": ready["receipt_id"],
            },
            snapshot_failure,
        )
        if snapshot_result is None:
            return None, failure
        evidence, evidence_error = _snapshot_evidence(
            artifact, ready, snapshot_result
        )
        if evidence is None:
            return None, (
                snapshot_failure
                if evidence_error == "projection_failed"
                else evidence_error
            )
        projection, snapshot_hash = evidence
        return (projection, snapshot_hash, ready), None

    issued, admission_error = _latest_terminal_receipt(authoring_trace)
    if admission_error is not None or issued is None:
        raise ValueError("probe_trace_invalid")
    baseline, failure = wait_and_snapshot(
        issued, "baseline_wait_failed", "baseline_snapshot_failed"
    )
    if baseline is None:
        return finish(failure or "probe_trace_invalid")
    baseline_projection, baseline_hash, baseline_ready = baseline
    baseline_bytes = canonical_json_bytes(baseline_projection)
    baseline_controls = {
        control["role"]: control for control in baseline_projection["controls"]
    }
    result["baseline"] = {
        "readiness_receipt_id": baseline_ready["receipt_id"],
        "snapshot_sha256": baseline_hash,
    }
    phases.append(
        {
            "id": "baseline",
            "projection": baseline_projection,
            "readiness_receipt_id": baseline_ready["receipt_id"],
            "snapshot_sha256": baseline_hash,
        }
    )
    used_receipt_ids = {issued["receipt_id"]}

    for definition in artifact["controls"]:
        role = definition["role"]
        control = baseline_controls.get(role)
        if control is None:
            return finish("control_binding_failed")
        original = control["value"]["val"]
        probe_value = definition["probe_value"]
        if (
            not control["value"]["min"] <= probe_value <= control["value"]["max"]
            or probe_value == original
            or (definition["value_kind"] == "integer" and type(probe_value) is not int)
        ):
            return finish("probe_value_invalid")

        control_result = {
            "role": role,
            "component_id": control["component_id"],
            "original_value": original,
            "probe_value": probe_value,
            "perturbation": None,
            "restoration": None,
        }
        result["controls"].append(control_result)

        set_result, failure = call(
            "gh_set_value",
            {"component": control["component_id"], "value": probe_value},
            "perturbation_dispatch_failed",
        )
        if set_result is None:
            return finish(failure or "probe_trace_invalid")
        data = set_result["data"]
        perturb_issued = (
            data.get("solve_readiness_receipt") if type(data) is dict else None
        )
        if (
            type(data) is not dict
            or data.get("solve_relevant_mutation_committed") is not True
            or not _valid_issued_receipt(perturb_issued)
            or perturb_issued["receipt_id"] in used_receipt_ids
        ):
            return finish("perturbation_receipt_invalid")
        used_receipt_ids.add(perturb_issued["receipt_id"])
        perturbed, failure = wait_and_snapshot(
            perturb_issued,
            "perturbation_wait_failed",
            "perturbation_snapshot_failed",
        )
        if perturbed is None:
            return finish(failure or "probe_trace_invalid")
        perturb_projection, perturb_hash, perturb_ready = perturbed
        expected_controls = {
            key: (
                candidate | {"value": candidate["value"] | {"val": probe_value}}
                if key == role
                else candidate
            )
            for key, candidate in baseline_controls.items()
        }
        observed_controls = {
            candidate["role"]: candidate
            for candidate in perturb_projection["controls"]
        }
        if observed_controls != expected_controls:
            return finish("perturbation_control_mismatch")

        control_result["perturbation"] = {
            "readiness_receipt_id": perturb_ready["receipt_id"],
            "snapshot_sha256": perturb_hash,
        }
        phases.append(
            {
                "id": f"perturbation:{role}",
                "projection": perturb_projection,
                "readiness_receipt_id": perturb_ready["receipt_id"],
                "snapshot_sha256": perturb_hash,
            }
        )

        restore_result, failure = call(
            "gh_set_value",
            {"component": control["component_id"], "value": original},
            "restoration_dispatch_failed",
        )
        if restore_result is None:
            return finish(failure or "probe_trace_invalid")
        restore_data = restore_result["data"]
        restore_issued = (
            restore_data.get("solve_readiness_receipt")
            if type(restore_data) is dict
            else None
        )
        if (
            type(restore_data) is not dict
            or restore_data.get("solve_relevant_mutation_committed") is not True
            or not _valid_issued_receipt(restore_issued)
            or restore_issued["receipt_id"] in used_receipt_ids
        ):
            return finish("restoration_receipt_invalid")
        used_receipt_ids.add(restore_issued["receipt_id"])
        restored, failure = wait_and_snapshot(
            restore_issued,
            "restoration_wait_failed",
            "restoration_snapshot_failed",
        )
        if restored is None:
            return finish(failure or "probe_trace_invalid")
        restore_projection, restore_hash, restore_ready = restored
        if canonical_json_bytes(restore_projection) != baseline_bytes:
            return finish("restoration_mismatch")
        control_result["restoration"] = {
            "readiness_receipt_id": restore_ready["receipt_id"],
            "snapshot_sha256": restore_hash,
            "restored": True,
        }
        phases.append(
            {
                "id": f"restoration:{role}",
                "projection": restore_projection,
                "readiness_receipt_id": restore_ready["receipt_id"],
                "snapshot_sha256": restore_hash,
            }
        )

    raise ValueError("probe_trace_invalid")


def _phase_control_values(phase: dict[str, Any]) -> dict[str, int | float]:
    return {
        control["role"]: control["value"]["val"]
        for control in phase["projection"]["controls"]
    }


def _criterion_roles(predicate: str, arguments: dict[str, Any]) -> list[str]:
    if predicate == "controls_present":
        return list(arguments["roles"])
    if predicate == "point_count_equals_control":
        return [arguments["role"]]
    if predicate == "point_count_equals_product":
        return list(arguments["roles"])
    if predicate == "axis_values_equal_sequence":
        return [arguments["start_role"], arguments["step_role"], arguments["count_role"]]
    if predicate == "axes_form_cartesian_product":
        roles: list[str] = []
        for sequence in arguments["sequences"]:
            roles.extend([sequence["start_role"], sequence["step_role"], sequence["count_role"]])
        return list(dict.fromkeys(roles))
    return []


def _applicable_phases(criterion: dict[str, Any], phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predicate = criterion["predicate"]
    if predicate in {"controls_present", "diagnostics_errors_equal", "axis_equals_constant"}:
        return phases
    roles = set(_criterion_roles(predicate, criterion["arguments"]))
    return [
        phase
        for phase in phases
        if phase["id"] == "baseline"
        or (
            phase["id"].startswith("perturbation:")
            and phase["id"].split(":", 1)[1] in roles
        )
    ]


def _close_enough(left: float | int, right: float | int, tolerance: float | int) -> bool:
    return abs(float(left) - float(right)) <= float(tolerance)


def _sequence_values(arguments: dict[str, Any], values: dict[str, int | float]) -> list[float] | None:
    count = values[arguments["count_role"]]
    if isinstance(count, bool) or not float(count).is_integer() or not 0 <= count <= 2**31 - 1:
        return None
    start = values[arguments["start_role"]]
    step = values[arguments["step_role"]]
    return [float(start) + index * float(step) for index in range(int(count))]


def _predicate_passes(
    criterion: dict[str, Any],
    phase: dict[str, Any],
    tolerance: float | int,
) -> bool | None:
    projection = phase["projection"]
    predicate = criterion["predicate"]
    arguments = criterion["arguments"]
    values = _phase_control_values(phase)
    points = projection["terminal_output"]["points"]
    if predicate == "controls_present":
        return all(role in values for role in arguments["roles"])
    if predicate == "diagnostics_errors_equal":
        return projection["diagnostics"]["errors"] == arguments["value"]
    if predicate == "point_count_equals_control":
        expected = values[arguments["role"]]
        return float(expected).is_integer() and projection["terminal_output"]["count"] == int(expected)
    if predicate == "point_count_equals_product":
        product = 1
        for role in arguments["roles"]:
            value = values[role]
            if not float(value).is_integer():
                return None
            product *= int(value)
        return projection["terminal_output"]["count"] == product
    axis_index = {"x": 0, "y": 1, "z": 2}
    if predicate == "axis_equals_constant":
        index = axis_index[arguments["axis"]]
        return all(_close_enough(point[index], arguments["value"], tolerance) for point in points)
    if predicate == "axis_values_equal_sequence":
        count_value = values[arguments["count_role"]]
        if not float(count_value).is_integer() or int(count_value) != len(points):
            return False
        expected = _sequence_values(arguments, values)
        if expected is None:
            return None
        index = axis_index[arguments["axis"]]
        observed = sorted(float(point[index]) for point in points)
        expected = sorted(expected)
        return len(observed) == len(expected) and all(_close_enough(left, right, tolerance) for left, right in zip(observed, expected))
    if predicate == "axes_form_cartesian_product":
        sequences: list[tuple[int, list[float]]] = []
        expected_count = 1
        for sequence in arguments["sequences"]:
            count_value = values[sequence["count_role"]]
            if not float(count_value).is_integer():
                return None
            expected_count *= int(count_value)
            if expected_count > len(points):
                return False
            expected = _sequence_values(sequence, values)
            if expected is None:
                return None
            sequences.append((axis_index[sequence["axis"]], expected))
        if expected_count != len(points):
            return False
        expected_tuples = sorted(itertools.product(*(sequence for _, sequence in sequences)))
        observed_tuples = sorted(tuple(float(point[index]) for index, _ in sequences) for point in points)
        return len(observed_tuples) == len(expected_tuples) and all(
            all(_close_enough(left, right, tolerance) for left, right in zip(observed, expected))
            for observed, expected in zip(observed_tuples, expected_tuples)
        )
    return None


def _incomplete_evaluation(
    artifact: dict[str, Any],
    authoring_trace: Any,
    probe_trace: Any,
    error: str,
    *,
    probe_result: dict[str, Any] | None = None,
    phases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    criteria: list[dict[str, Any]] = []
    for criterion in artifact.get("criteria", []):
        if type(criterion) is not dict or not isinstance(criterion.get("id"), str):
            continue
        applicable = _applicable_phases(criterion, phases or []) if phases else []
        criteria.append(
            {
                "criterion_id": criterion["id"],
                "status": "unproven",
                "failure_ids": [criterion["id"]],
                "evidence_refs": [phase["id"] for phase in applicable],
            }
        )
    return {
        "schema": _EVALUATION_SCHEMA,
        "status": "incomplete",
        "criteria": criteria,
        "probe": probe_result or {"status": "incomplete", "baseline": None, "controls": [], "error": error},
        "source": {
            "acceptance_sha256": _sha(canonical_json_bytes(artifact)),
            "authoring_trace_sha256": _sha(canonical_json_bytes(authoring_trace)),
            "probe_trace_sha256": _sha(canonical_json_bytes(probe_trace)),
        },
    }


def evaluate_behavioral_probe(
    artifact: dict[str, Any],
    authoring_trace: dict[str, Any],
    probe_trace: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one complete retained probe without topology-specific rules."""

    try:
        canonical_json_bytes(artifact)
        canonical_json_bytes(authoring_trace)
        canonical_json_bytes(probe_trace)
    except (TypeError, ValueError):
        raise ValueError("input_not_canonical_json") from None

    try:
        artifact = validate_acceptance_artifact(artifact)
    except (TypeError, ValueError):
        return _incomplete_evaluation(artifact if type(artifact) is dict else {}, authoring_trace, probe_trace, "artifact_invalid")
    try:
        trace = _validate_authoring_trace(authoring_trace)
    except (TypeError, ValueError):
        return _incomplete_evaluation(artifact, authoring_trace, probe_trace, "authoring_trace_invalid")
    try:
        probe = _validate_probe_trace(probe_trace)
    except (TypeError, ValueError):
        return _incomplete_evaluation(artifact, trace, probe_trace, "probe_trace_invalid")
    _, admission_error = _latest_terminal_receipt(trace)
    if admission_error is not None:
        return _incomplete_evaluation(artifact, trace, probe, admission_error)
    parsed = _parse_complete_probe(artifact, trace, probe)
    if parsed is None:
        try:
            retained_probe, retained_phases = _retained_probe_prefix(
                artifact, trace, probe
            )
        except ValueError:
            return _incomplete_evaluation(
                artifact, trace, probe, "probe_trace_invalid"
            )
        error = retained_probe["error"]
        return _incomplete_evaluation(
            artifact,
            trace,
            probe,
            error,
            probe_result=retained_probe,
            phases=retained_phases,
        )
    probe_result, phases = parsed
    criteria: list[dict[str, Any]] = []
    for criterion in artifact["criteria"]:
        applicable = _applicable_phases(criterion, phases)
        outcomes = [
            _predicate_passes(criterion, phase, artifact["numeric_tolerance"])
            for phase in applicable
        ]
        if not applicable or any(outcome is None for outcome in outcomes):
            status = "unproven"
        elif all(outcome is True for outcome in outcomes):
            status = "pass"
        else:
            status = "fail"
        criteria.append(
            {
                "criterion_id": criterion["id"],
                "status": status,
                "failure_ids": [] if status == "pass" else [criterion["id"]],
                "evidence_refs": [phase["id"] for phase in applicable],
            }
        )
    if any(item["status"] == "fail" for item in criteria):
        status = "fail"
    elif any(item["status"] == "unproven" for item in criteria):
        status = "incomplete"
    else:
        status = "pass"
    return {
        "schema": _EVALUATION_SCHEMA,
        "status": status,
        "criteria": criteria,
        "probe": probe_result,
        "source": {
            "acceptance_sha256": _sha(canonical_json_bytes(artifact)),
            "authoring_trace_sha256": _sha(canonical_json_bytes(trace)),
            "probe_trace_sha256": _sha(canonical_json_bytes(probe)),
        },
    }
