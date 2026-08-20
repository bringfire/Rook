"""Prime compaction-aware trace admission layered over the frozen V1 owner.

V1 remains byte-owned by historical qualification protocols. This module changes
only Prime runtime-lifecycle admission; source-event validation, closure custody,
and normalized trace semantics continue to come from V1.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

from rook import gh_behavioral_acceptance as v1


__all__ = [
    "normalize_authoring_trace",
    "seal_and_normalize_prime_source_log",
    "seal_prime_source_log",
]


def _valid_compaction_start(row: Any) -> bool:
    return (
        type(row) is dict
        and set(row) == {"type", "reason"}
        and row["type"] == "compaction_start"
        and isinstance(row["reason"], str)
        and bool(row["reason"])
    )


def _valid_session_action_update(row: Any, phases: set[str] | None) -> bool:
    if type(row) is not dict or set(row) != {"type", "actions"}:
        return False
    actions = row["actions"]
    if (
        row["type"] != "session_action_update"
        or type(actions) is not dict
        or type(actions.get("queuedCount")) is not int
        or actions["queuedCount"] != 0
        or actions.get("steering") != []
        or actions.get("followUps") != []
    ):
        return False
    if phases is None:
        return set(actions) == {"queuedCount", "steering", "followUps"}
    if set(actions) != {"queuedCount", "steering", "followUps", "active"}:
        return False
    active = actions["active"]
    return (
        type(active) is dict
        and set(active) == {"kind", "phase", "label"}
        and active["kind"] == "turn"
        and active["phase"] in phases
        and isinstance(active["label"], str)
        and bool(active["label"])
    )


def _goal_identity(agent_end: Any) -> tuple[str, str, int] | None:
    if type(agent_end) is not dict or agent_end.get("type") != "agent_end":
        return None
    messages = agent_end.get("messages")
    if type(messages) is not list:
        return None
    contexts = [
        message
        for message in messages
        if type(message) is dict
        and message.get("role") == "custom"
        and message.get("customType") == "goal_context"
    ]
    if len(contexts) != 1:
        return None
    details = contexts[0].get("details")
    if (
        type(details) is not dict
        or set(details)
        != {"kind", "goalId", "objective", "status", "continuationsUsed"}
        or details["kind"] != "continuation"
        or details["status"] != "active"
        or not isinstance(details["goalId"], str)
        or not details["goalId"]
        or not isinstance(details["objective"], str)
        or not details["objective"]
        or type(details["continuationsUsed"]) is not int
        or details["continuationsUsed"] < 0
    ):
        return None
    return (
        details["goalId"],
        details["objective"],
        details["continuationsUsed"],
    )


def _valid_compaction_bridge(rows: list[Any]) -> bool:
    if len(rows) != 6:
        return False
    start, message_start, message_end, end = rows[:4]
    return (
        _valid_compaction_start(start)
        and v1._valid_ipython_state_message(message_start, "message_start")
        and v1._valid_ipython_state_message(message_end, "message_end")
        and message_start["message"] == message_end["message"]
        and v1._valid_compaction_end(end)
        and start["reason"] == end["reason"]
        and _valid_session_action_update(rows[4], {"preparing"})
        and _valid_session_action_update(rows[5], {"committing"})
    )


def _valid_compacted_prime_terminal(runtime_rows: list[Any]) -> bool:
    session_indices = [
        index
        for index, row in enumerate(runtime_rows)
        if type(row) is dict and row.get("type") == "session"
    ]
    start_indices = [
        index
        for index, row in enumerate(runtime_rows)
        if type(row) is dict and row.get("type") == "agent_start"
    ]
    end_indices = [
        index
        for index, row in enumerate(runtime_rows)
        if type(row) is dict and row.get("type") == "agent_end"
    ]
    compaction_start_indices = [
        index
        for index, row in enumerate(runtime_rows)
        if type(row) is dict and row.get("type") == "compaction_start"
    ]
    compaction_end_indices = [
        index
        for index, row in enumerate(runtime_rows)
        if type(row) is dict and row.get("type") == "compaction_end"
    ]
    if (
        len(start_indices) < 2
        or len(start_indices) != len(end_indices)
        or len(compaction_start_indices) != len(start_indices) - 1
        or len(compaction_end_indices) != len(start_indices) - 1
        or len(session_indices) != 1
        or type(runtime_rows[session_indices[0]].get("id")) is not str
        or not runtime_rows[session_indices[0]]["id"]
        or not session_indices[0] < start_indices[0]
    ):
        return False
    if any(
        not (
            start_indices[index] < end_indices[index]
            and (
                index == len(start_indices) - 1
                or end_indices[index] < start_indices[index + 1]
            )
        )
        for index in range(len(start_indices))
    ):
        return False

    identities = [_goal_identity(runtime_rows[index]) for index in end_indices]
    if any(identity is None for identity in identities):
        return False
    goal_id, objective, first_continuation = identities[0]
    if any(
        identity != (goal_id, objective, first_continuation + index)
        for index, identity in enumerate(identities)
    ):
        return False

    for index in range(len(end_indices) - 1):
        bridge = runtime_rows[
            end_indices[index] + 1 : start_indices[index + 1]
        ]
        if not _valid_compaction_bridge(bridge):
            return False

    suffix = runtime_rows[end_indices[-1] + 1 :]
    return not suffix or (
        len(suffix) == 1 and _valid_session_action_update(suffix[0], None)
    )


def _valid_prime_semantic_terminal(runtime_rows: list[Any]) -> bool:
    return v1._valid_prime_semantic_terminal(
        runtime_rows
    ) or _valid_compacted_prime_terminal(runtime_rows)


def _project_runtime_row(row: Any) -> Any:
    """Retain only fields that participate in lifecycle admission."""

    if type(row) is not dict:
        return None
    event_type = row.get("type")
    if event_type == "agent_end":
        messages = row.get("messages")
        contexts = (
            [
                message
                for message in messages
                if type(message) is dict
                and message.get("role") == "custom"
                and message.get("customType") == "goal_context"
            ]
            if type(messages) is list
            else messages
        )
        return {"type": "agent_end", "messages": contexts}
    if event_type in {
        "agent_start",
        "compaction_start",
        "compaction_end",
        "session_action_update",
    }:
        return row
    if event_type == "session":
        return {"type": "session", "id": row.get("id")}
    if event_type in {"message_start", "message_end"}:
        message = row.get("message")
        if type(message) is dict and message.get("customType") == "ipython_state":
            return row
    return None


def _read_prime_runtime_projection(path: Path) -> tuple[str, list[Any]]:
    """Hash Prime JSONL while retaining only bounded lifecycle evidence."""

    digest = hashlib.sha256()
    rows: list[Any] = []
    first = True
    with Path(path).open("rb") as stream:
        for raw_line in stream:
            if first:
                first = False
                if raw_line.startswith(b"\xef\xbb\xbf"):
                    raise ValueError("utf8_bom_forbidden")
            if not raw_line.endswith(b"\n"):
                raise ValueError("missing_final_lf")
            if raw_line.strip() == b"":
                raise ValueError("invalid_jsonl_row")
            digest.update(raw_line)
            rows.append(_project_runtime_row(v1._strict_json_line(raw_line[:-1])))
    return digest.hexdigest().upper(), rows


def _closure(
    header: dict[str, Any],
    events: list[dict[str, Any]],
    source_payload: bytes,
    runtime_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": v1._CLOSURE_SCHEMA,
        "owner": "prime_transaction_launcher",
        "row_emitter": header["row_emitter"],
        "source_event_count": len(events),
        "final_source_sequence": len(events) - 1 if events else None,
        "source_log_sha256": v1._sha(source_payload),
        "runtime_log_sha256": runtime_sha256,
        "terminal_marker": "agent_end",
        "closed": True,
    }


def _validate_closure(
    value: Any,
    header: dict[str, Any],
    events: list[dict[str, Any]],
    source_payload: bytes,
    runtime_sha256: str,
) -> dict[str, Any]:
    expected = _closure(
        header,
        events,
        source_payload,
        runtime_sha256,
    )
    if value != expected:
        raise ValueError("source_closure_mismatch")
    return value


def _recognized_viewport_capture(event: dict[str, Any]) -> bool:
    if (
        event["target"] != "rhino_viewport"
        or event["exception"] is not None
        or event["dispatch"] != {"status": "dispatched", "target_call_count": 1}
        or event["mutation"] != v1._unknown_mutation()
        or event["result"] is None
        or event["result"].get("success") is not True
        or set(event["result"]) != {"success", "data"}
    ):
        return False
    arguments = event["arguments"]
    allowed_arguments = {
        "width",
        "height",
        "view",
        "displayMode",
        "zoomExtents",
        "transparentBackground",
        "scale",
        "drawGrid",
        "drawWorldAxes",
        "drawCPlaneAxes",
    }
    if not set(arguments).issubset(allowed_arguments):
        return False
    for name in {"width", "height"} & set(arguments):
        if type(arguments[name]) is not int or not 1 <= arguments[name] <= 4000:
            return False
    if "scale" in arguments and (
        type(arguments["scale"]) is not int or not 1 <= arguments["scale"] <= 10
    ):
        return False
    for name in {"view", "displayMode"} & set(arguments):
        if not isinstance(arguments[name], str) or not arguments[name]:
            return False
    for name in {
        "zoomExtents",
        "transparentBackground",
        "drawGrid",
        "drawWorldAxes",
        "drawCPlaneAxes",
    } & set(arguments):
        if type(arguments[name]) is not bool:
            return False

    data = event["result"]["data"]
    return (
        type(data) is dict
        and set(data)
        == {
            "displayMode",
            "filePath",
            "format",
            "height",
            "message",
            "savedToFile",
            "viewName",
            "width",
        }
        and data["savedToFile"] is True
        and data["format"] == "png"
        and isinstance(data["displayMode"], str)
        and bool(data["displayMode"])
        and isinstance(data["filePath"], str)
        and bool(data["filePath"])
        and isinstance(data["message"], str)
        and bool(data["message"])
        and isinstance(data["viewName"], str)
        and bool(data["viewName"])
        and type(data["width"]) is int
        and data["width"] > 0
        and type(data["height"]) is int
        and data["height"] > 0
    )


def _normalize_v2_event(event: dict[str, Any]) -> dict[str, Any]:
    if not _recognized_viewport_capture(event):
        return event
    normalized = copy.deepcopy(event)
    normalized["mutation"] = v1._observational_mutation()
    return normalized


def seal_prime_source_log(
    source_path: Path,
    runtime_log_path: Path,
    process_state: dict[str, Any],
) -> dict[str, Any]:
    """Seal a V1 source log after a V1 or compaction-linked Prime lifecycle."""

    header, events, source_lines = v1._open_source(Path(source_path))
    _, all_source_rows, _ = v1._read_jsonl(Path(source_path))
    if (
        header["row_emitter"] != "prime_rook_adapter"
        or len(all_source_rows) != 1 + len(events)
    ):
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
    if (
        type(process_state["owned_child_pids"]) is not list
        or process_state["owned_child_pids"]
    ):
        raise ValueError("prime_children_lingering")
    if type(process_state["exit_code"]) is not int:
        raise ValueError("invalid_exit_code")

    runtime_sha256, runtime_rows = _read_prime_runtime_projection(
        Path(runtime_log_path)
    )
    if not _valid_prime_semantic_terminal(runtime_rows):
        raise ValueError("invalid_prime_terminal_marker")
    source_payload = b"".join(source_lines)
    closure = _closure(header, events, source_payload, runtime_sha256)
    v1._append_closure(Path(source_path), closure)
    return closure


def seal_and_normalize_prime_source_log(
    source_path: Path,
    runtime_log_path: Path,
    process_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Seal and normalize while streaming a large Prime runtime only once."""

    header, events, source_lines = v1._open_source(Path(source_path))
    _, all_source_rows, _ = v1._read_jsonl(Path(source_path))
    if (
        header["row_emitter"] != "prime_rook_adapter"
        or len(all_source_rows) != 1 + len(events)
    ):
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
    if (
        type(process_state["owned_child_pids"]) is not list
        or process_state["owned_child_pids"]
    ):
        raise ValueError("prime_children_lingering")
    if type(process_state["exit_code"]) is not int:
        raise ValueError("invalid_exit_code")

    runtime_sha256, runtime_rows = _read_prime_runtime_projection(
        Path(runtime_log_path)
    )
    if not _valid_prime_semantic_terminal(runtime_rows):
        raise ValueError("invalid_prime_terminal_marker")
    source_payload = b"".join(source_lines)
    closure = _closure(header, events, source_payload, runtime_sha256)
    v1._append_closure(Path(source_path), closure)
    trace = _normalize_authoring_trace_with_runtime_evidence(
        Path(source_path), runtime_sha256, runtime_rows
    )
    return closure, trace


def _normalize_authoring_trace_with_runtime_evidence(
    source_path: Path,
    runtime_sha256: str,
    runtime_rows: list[Any],
) -> dict[str, Any]:
    source_payload, source_rows, source_lines = v1._read_jsonl(Path(source_path))
    if len(source_rows) < 2:
        raise ValueError("source_log_unclosed")
    header = source_rows[0]
    if (
        type(header) is not dict
        or set(header) != {"schema", "row_emitter"}
        or header["schema"] != v1._SOURCE_SCHEMA
        or header["row_emitter"] != "prime_rook_adapter"
    ):
        raise ValueError("invalid_source_header")
    closure_row = source_rows[-1]
    if (
        type(closure_row) is not dict
        or set(closure_row) != {"type", "source_closure"}
        or closure_row["type"] != "closure"
    ):
        raise ValueError("source_log_unclosed")
    events = [
        _normalize_v2_event(
            v1._validate_event(
                row,
                index,
                normalize_retained_epoch_mismatch=True,
            )
        )
        for index, row in enumerate(source_rows[1:-1])
    ]
    closure = _validate_closure(
        closure_row["source_closure"],
        header,
        events,
        b"".join(source_lines[:-1]),
        runtime_sha256,
    )
    if not _valid_prime_semantic_terminal(runtime_rows):
        raise ValueError("invalid_prime_terminal_marker")
    return {
        "schema": v1._TRACE_SCHEMA,
        "source_closure": closure,
        "events": events,
    }


def normalize_authoring_trace(
    source_path: Path, runtime_log_path: Path
) -> dict[str, Any]:
    """Normalize a trace sealed by this versioned Prime lifecycle owner."""

    runtime_sha256, runtime_rows = _read_prime_runtime_projection(
        Path(runtime_log_path)
    )
    return _normalize_authoring_trace_with_runtime_evidence(
        Path(source_path), runtime_sha256, runtime_rows
    )
