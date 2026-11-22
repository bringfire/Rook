"""Closed Prime RPC shapes used by the opt-in RookChat broker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, cast


PromptFailureCode = Literal[
    "admission_failed",
    "execution_failed",
    "inspection_failed",
    "settlement_unknown",
    "protocol_failed",
]
PromptOutcome = Literal["completed", "aborted"]
RlmMaxDepthSource = Literal["default", "env", "global", "inherited", "chat"]

_PROMPT_FAILURE_CODES = frozenset(
    {
        "admission_failed",
        "execution_failed",
        "inspection_failed",
        "settlement_unknown",
        "protocol_failed",
    }
)


class PrimeProtocolError(RuntimeError):
    """A Prime JSONL row violates the admitted wire contract."""


@dataclass(frozen=True)
class PromptSettlement:
    request_id: str
    outcome: PromptOutcome | None
    error_code: PromptFailureCode | None
    error_message: str | None


@dataclass(frozen=True)
class RlmMaxDepthStatus:
    max_depth: int
    source: RlmMaxDepthSource


@dataclass(frozen=True)
class IpythonRuntimePreparation:
    interpreter_path: str
    rook_full_file: str
    goal_file: str


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PrimeProtocolError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    if frozenset(value) != expected:
        raise PrimeProtocolError(f"{label} has an invalid closed shape")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PrimeProtocolError(f"{label} must be a non-empty string")
    return value


def _successful_response_data(
    response: Any,
    *,
    command: str,
    label: str,
) -> tuple[str, Mapping[str, Any]]:
    payload = _mapping(response, label)
    _exact_keys(
        payload,
        frozenset({"id", "type", "command", "success", "data"}),
        label,
    )
    if payload["type"] != "response" or payload["command"] != command:
        raise PrimeProtocolError(f"{label} command does not match")
    request_id = _nonempty_string(payload["id"], f"{label} id")
    if payload["success"] is not True:
        raise PrimeProtocolError(f"{label} did not succeed")
    return request_id, _mapping(payload["data"], f"{label} data")


def parse_rlm_max_depth_status(
    response: Any,
    *,
    expected_command: Literal[
        "get_rlm_max_depth_status", "set_rlm_max_depth"
    ],
) -> RlmMaxDepthStatus:
    _, data = _successful_response_data(
        response,
        command=expected_command,
        label="RLM max-depth response",
    )
    _exact_keys(data, frozenset({"maxDepth", "source"}), "RLM max-depth data")
    max_depth = data["maxDepth"]
    source = data["source"]
    if type(max_depth) is not int or max_depth < 0:
        raise PrimeProtocolError("RLM max depth must be a nonnegative integer")
    if source not in {"default", "env", "global", "inherited", "chat"}:
        raise PrimeProtocolError("RLM max-depth source is invalid")
    return RlmMaxDepthStatus(
        max_depth=max_depth,
        source=cast(RlmMaxDepthSource, source),
    )


def parse_ipython_runtime_preparation(
    response: Any,
) -> IpythonRuntimePreparation:
    _, data = _successful_response_data(
        response,
        command="prepare_ipython_runtime",
        label="IPython runtime preparation response",
    )
    _exact_keys(
        data,
        frozenset({"interpreterPath", "rookFullFile", "goalFile", "callables"}),
        "IPython runtime preparation data",
    )
    paths: dict[str, str] = {}
    for key in ("interpreterPath", "rookFullFile", "goalFile"):
        value = _nonempty_string(data[key], f"IPython runtime {key}")
        if not Path(value).is_absolute():
            raise PrimeProtocolError(f"IPython runtime {key} must be absolute")
        paths[key] = value
    callables = _mapping(data["callables"], "IPython runtime callables")
    _exact_keys(
        callables,
        frozenset({"search", "read", "call"}),
        "IPython runtime callables",
    )
    if any(callables[name] is not True for name in ("search", "read", "call")):
        raise PrimeProtocolError("IPython runtime callables are unavailable")
    return IpythonRuntimePreparation(
        interpreter_path=paths["interpreterPath"],
        rook_full_file=paths["rookFullFile"],
        goal_file=paths["goalFile"],
    )


def parse_prompt_settlement(response: Any) -> PromptSettlement:
    payload = _mapping(response, "prompt settlement response")
    if payload.get("type") != "response":
        raise PrimeProtocolError("prompt settlement must be a response")
    if payload.get("command") != "prompt_and_wait":
        raise PrimeProtocolError("prompt settlement command does not match")
    request_id = _nonempty_string(payload.get("id"), "prompt settlement id")
    success = payload.get("success")
    if type(success) is not bool:
        raise PrimeProtocolError("prompt settlement success must be boolean")

    if success:
        _exact_keys(
            payload,
            frozenset({"id", "type", "command", "success", "data"}),
            "prompt settlement success",
        )
        data = _mapping(payload["data"], "prompt settlement data")
        _exact_keys(data, frozenset({"outcome"}), "prompt settlement data")
        outcome = data["outcome"]
        if outcome not in {"completed", "aborted"}:
            raise PrimeProtocolError("prompt settlement outcome is invalid")
        return PromptSettlement(
            request_id=request_id,
            outcome=cast(PromptOutcome, outcome),
            error_code=None,
            error_message=None,
        )

    _exact_keys(
        payload,
        frozenset({"id", "type", "command", "success", "error"}),
        "prompt settlement failure",
    )
    error = _mapping(payload["error"], "prompt settlement error")
    _exact_keys(error, frozenset({"code", "message"}), "prompt settlement error")
    code = error["code"]
    if code not in _PROMPT_FAILURE_CODES:
        raise PrimeProtocolError("prompt settlement failure code is invalid")
    message = _nonempty_string(error["message"], "prompt settlement error message")
    return PromptSettlement(
        request_id=request_id,
        outcome=None,
        error_code=cast(PromptFailureCode, code),
        error_message=message,
    )


def project_prime_event(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    event_type = event.get("type")
    if event_type == "message_update":
        update = event.get("assistantMessageEvent")
        if not isinstance(update, dict) or update.get("type") != "text_delta":
            return None
        delta = update.get("delta")
        if not isinstance(delta, str) or not delta:
            return None
        return {"type": "text_delta", "content": delta}
    if event_type == "model_change":
        model = event.get("model")
        if not isinstance(model, dict):
            return None
        provider = model.get("provider")
        model_id = model.get("id")
        thinking = event.get("thinkingLevel")
        if (
            not isinstance(provider, str)
            or not provider
            or not isinstance(model_id, str)
            or not model_id
            or (thinking is not None and not isinstance(thinking, str))
        ):
            return None
        return {
            "type": "model_update",
            "provider": provider,
            "model": model_id,
            "thinking": thinking,
        }
    if event_type == "agent_end":
        return {"type": "status", "status": "segment_end"}
    return None
