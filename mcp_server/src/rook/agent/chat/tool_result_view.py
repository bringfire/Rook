from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ToolResultView:
    status: Literal["success", "failed"] | None = None
    verified: bool | None = None
    verification_note: str | None = None
    message: str | None = None
    error: str | None = None


def _dict_field(mapping: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = mapping.get(key)
    return value if isinstance(value, dict) else None


def _bool_field(mapping: dict[str, Any] | None, key: str) -> bool | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get(key)
    return value if isinstance(value, bool) else None


def _first_bool_field(
    mapping: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> bool | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = _bool_field(mapping, key)
        if value is not None:
            return value
    return None


def _string_field(mapping: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _truthy_field(mapping: dict[str, Any] | None, key: str) -> bool:
    return isinstance(mapping, dict) and bool(mapping.get(key))


def normalize_tool_result(result: Any) -> ToolResultView:
    """Normalize legacy tool result dicts for model-visible event decoration.

    This does not execute tools, call Rhino, format MCP wire output, or mutate
    the input result. It is an internal view over today's result shapes.
    """
    if not isinstance(result, dict):
        return ToolResultView()

    data = _dict_field(result, "data")

    truth = _first_bool_field(result, ("success", "ok"))
    if truth is None:
        truth = _first_bool_field(data, ("success", "ok"))

    if truth is True:
        status: Literal["success", "failed"] | None = "success"
    elif truth is False:
        status = "failed"
    elif _truthy_field(result, "error") or _truthy_field(data, "error"):
        status = "failed"
    else:
        status = None

    top_verified = _bool_field(result, "verified")
    nested_verified = _bool_field(data, "verified")
    verified = top_verified if top_verified is not None else nested_verified

    verification_note = _string_field(result, "verification_note")
    nested_verification_note = _string_field(data, "verification_note")
    if verification_note is None:
        verification_note = nested_verification_note
    if (
        verification_note is None
        and top_verified is None
        and nested_verified is False
    ):
        verification_note = _string_field(data, "message")

    message = _string_field(result, "message")
    if message is None:
        message = _string_field(data, "message")

    error = _string_field(result, "error")
    if error is None:
        error = _string_field(data, "error")

    return ToolResultView(
        status=status,
        verified=verified,
        verification_note=verification_note,
        message=message,
        error=error,
    )
