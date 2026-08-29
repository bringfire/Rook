from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from contextlib import AsyncExitStack
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rlm.mcp_base import McpToolError


__all__ = ("search", "read", "call")


_LAUNCH_TIMEOUT_SECONDS = 30.0
_INITIALIZE_TIMEOUT_SECONDS = 30.0
_CALL_TIMEOUT_SECONDS = 180.0
_CLOSE_TIMEOUT_SECONDS = 15.0
_CANONICAL_DECIMAL = re.compile(r"^[1-9][0-9]*$")
_MAX_INT64 = (1 << 63) - 1
_BOOTSTRAP_ENV_KEYS = (
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "PROGRAMDATA",
)
_SELECTOR_EXPECTATIONS = {
    "processId": "process_id",
    "process_id": "process_id",
    "processStartUtcTicks": "process_start_utc_ticks",
    "rhinoProcessStartUtcTicks": "process_start_utc_ticks",
    "documentSerialNumber": "document_serial_number",
    "documentRuntimeSerial": "document_serial_number",
    "grasshopperDocumentId": "grasshopper_document_id",
    "capabilityProfile": "capability_profile",
    "toolProfile": "capability_profile",
}
_UNVERIFIABLE_SELECTORS = frozenset({"port", "session", "sessionId", "session_id"})


class RookFullError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        phase_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase_code = phase_code


_last_call_diagnostic: ContextVar[dict[str, Any]] = ContextVar(
    "rook_full_last_call_diagnostic",
    default={},
)


@dataclass(frozen=True)
class _ProductConfiguration:
    command: str
    cwd: str
    install_root: str
    data_root: str
    cache_root: str
    chirp_home: str
    capability_profile: str
    process_id: int
    process_start_utc_ticks: str
    document_serial_number: int
    grasshopper_document_id: str | None
    child_environment: dict[str, str]


def _invalid(message: str) -> RookFullError:
    return RookFullError("rook_full_invalid_arguments", message)


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or not value:
        raise _invalid(f"missing or invalid {name}")
    return value


def _absolute_file(name: str) -> str:
    value = _required_environment(name)
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise _invalid(f"missing or invalid {name}")
    return str(path)


def _absolute_directory(name: str) -> str:
    value = _required_environment(name)
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise _invalid(f"missing or invalid {name}")
    return str(path)


def _positive_decimal(name: str) -> tuple[str, int]:
    value = _required_environment(name)
    if _CANONICAL_DECIMAL.fullmatch(value) is None:
        raise _invalid(f"missing or invalid {name}")
    parsed = int(value)
    if parsed > _MAX_INT64:
        raise _invalid(f"missing or invalid {name}")
    return value, parsed


def _optional_canonical_guid(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise _invalid(f"missing or invalid {name}") from error
    if parsed.int == 0 or str(parsed) != value:
        raise _invalid(f"missing or invalid {name}")
    return value


def _load_product_configuration() -> _ProductConfiguration:
    command = _absolute_file("ROOK_MCP_PYTHON_EXECUTABLE")
    cwd = _absolute_directory("ROOK_MCP_WORKING_DIRECTORY")
    install_root = _absolute_directory("ROOK_INSTALL_ROOT")
    data_root = _absolute_directory("ROOK_DATA_DIR")
    cache_root = _absolute_directory("DSPY_CACHEDIR")
    chirp_home = _absolute_directory("CHIRP_HOME")
    if _required_environment("ROOK_MODE") != "release":
        raise _invalid("ROOK_MODE must equal release")
    if _required_environment("ROOK_DSPY_RESTRICT_PICKLE") != "1":
        raise _invalid("ROOK_DSPY_RESTRICT_PICKLE must equal 1")
    profile = _required_environment("ROOK_MCP_TOOL_PROFILE")
    if profile not in {"readonly", "full"}:
        raise _invalid("ROOK_MCP_TOOL_PROFILE must be readonly or full")
    if _required_environment("ROOK_MCP_TARGET_MODE") != "panel_locked":
        raise _invalid("ROOK_MCP_TARGET_MODE must equal panel_locked")
    process_id_text, process_id = _positive_decimal(
        "ROOK_MCP_TARGET_PROCESS_ID"
    )
    ticks, _ = _positive_decimal("ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS")
    serial_text, serial = _positive_decimal(
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER"
    )
    grasshopper_document_id = _optional_canonical_guid(
        "ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID"
    )

    bootstrap = {name: _required_environment(name) for name in _BOOTSTRAP_ENV_KEYS}
    windows_system = str(Path(bootstrap["SystemRoot"]) / "System32")
    child_environment = {
        **bootstrap,
        "PATH": os.pathsep.join((str(Path(command).parent), windows_system)),
        "ROOK_INSTALL_ROOT": install_root,
        "ROOK_DATA_DIR": data_root,
        "ROOK_MODE": "release",
        "DSPY_CACHEDIR": cache_root,
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
        "CHIRP_HOME": chirp_home,
        "PYTHONHOME": "",
        "PYTHONPATH": "",
        "ROOK_MCP_TOOL_PROFILE": profile,
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": process_id_text,
        "ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS": ticks,
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": serial_text,
    }
    if grasshopper_document_id is not None:
        child_environment[
            "ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID"
        ] = grasshopper_document_id
    return _ProductConfiguration(
        command=command,
        cwd=cwd,
        install_root=install_root,
        data_root=data_root,
        cache_root=cache_root,
        chirp_home=chirp_home,
        capability_profile=profile,
        process_id=process_id,
        process_start_utc_ticks=ticks,
        document_serial_number=serial,
        grasshopper_document_id=grasshopper_document_id,
        child_environment=child_environment,
    )


def _require_nonempty_string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise _invalid(f"{label} must be a nonempty string")
    return value


def _locked_arguments(
    arguments: dict[str, Any], configuration: _ProductConfiguration
) -> dict[str, Any]:
    if type(arguments) is not dict:
        raise _invalid("arguments must be an exact dictionary")
    frozen = deepcopy(arguments)
    if any(name in frozen for name in _UNVERIFIABLE_SELECTORS):
        raise _invalid("explicit routing selector cannot agree with the locked target")
    if any(name.startswith("ROOK_MCP_") for name in frozen):
        raise _invalid("model arguments cannot set product authority fields")
    for selector, attribute in _SELECTOR_EXPECTATIONS.items():
        if selector not in frozen:
            continue
        expected = getattr(configuration, attribute)
        if frozen[selector] != expected:
            raise _invalid(f"{selector} conflicts with the locked target")
        del frozen[selector]
    return frozen


def _closed_result_envelope(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"success", "data"}
        and type(value["success"]) is bool
    )


def _result_text(result: Any) -> str:
    texts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(texts)


def _parse_result(result: Any) -> tuple[Any, bool]:
    structured = getattr(result, "structuredContent", None)
    if not _closed_result_envelope(structured):
        raise RookFullError(
            "rook_full_malformed_result",
            "Rook returned no closed structured result envelope",
        )
    if getattr(result, "isError", False) or structured["success"] is False:
        data = structured["data"]
        message = _result_text(result)
        if not message and isinstance(data, dict):
            message = str(data.get("message") or data.get("error") or "")
        raise McpToolError(
            message or "Rook tool returned an error",
            structured_content=structured,
        )
    return structured["data"], True


async def _close_stack(stack: AsyncExitStack) -> tuple[bool, str | None]:
    try:
        await asyncio.wait_for(stack.aclose(), timeout=_CLOSE_TIMEOUT_SECONDS)
    except BaseException as error:
        return False, f"{type(error).__name__}: {error}"
    return True, None


def _set_diagnostic(
    *,
    startup_seconds: float | None,
    authentic_envelope_received: bool,
    cleanup_succeeded: bool,
    cleanup_error: str | None,
) -> None:
    _last_call_diagnostic.set(
        {
            "startupSeconds": startup_seconds,
            "authenticEnvelopeReceived": authentic_envelope_received,
            "cleanupSucceeded": cleanup_succeeded,
            "cleanupError": cleanup_error,
        }
    )


async def _invoke(
    tool: str,
    arguments: dict[str, Any],
    configuration: _ProductConfiguration,
) -> Any:
    parameters = StdioServerParameters(
        command=configuration.command,
        args=["-m", "rook"],
        cwd=configuration.cwd,
        env=dict(configuration.child_environment),
    )
    stack = AsyncExitStack()
    startup_seconds: float | None = None
    authentic_envelope_received = False
    value: Any = None
    primary_error: BaseException | None = None
    try:
        started = time.monotonic()
        try:
            async with asyncio.timeout(_LAUNCH_TIMEOUT_SECONDS):
                errlog = stack.enter_context(
                    open(os.devnull, "w", encoding="utf-8")
                )
                read, write = await stack.enter_async_context(
                    stdio_client(parameters, errlog=errlog)
                )
        except TimeoutError as error:
            raise RookFullError(
                "rook_full_launch_failed", "Rook MCP launch timed out"
            ) from error
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise RookFullError(
                "rook_full_launch_failed", f"Rook MCP launch failed: {error}"
            ) from error
        startup_seconds = time.monotonic() - started

        session = await stack.enter_async_context(ClientSession(read, write))
        try:
            async with asyncio.timeout(_INITIALIZE_TIMEOUT_SECONDS):
                await session.initialize()
        except TimeoutError as error:
            raise RookFullError(
                "rook_full_initialize_timeout",
                "Rook MCP initialization timed out",
            ) from error

        try:
            async with asyncio.timeout(_CALL_TIMEOUT_SECONDS):
                result = await session.call_tool(tool, arguments)
        except TimeoutError as error:
            raise RookFullError(
                "rook_full_outcome_uncertain",
                "Rook MCP call timed out without an authentic result envelope",
                phase_code="rook_full_call_timeout",
            ) from error
        value, authentic_envelope_received = _parse_result(result)
    except BaseException as error:
        primary_error = error
        if isinstance(error, McpToolError) and _closed_result_envelope(
            error.structured_content
        ):
            authentic_envelope_received = True
    cleanup_succeeded, cleanup_error = await _close_stack(stack)
    _set_diagnostic(
        startup_seconds=startup_seconds,
        authentic_envelope_received=authentic_envelope_received,
        cleanup_succeeded=cleanup_succeeded,
        cleanup_error=cleanup_error,
    )

    if primary_error is not None:
        if isinstance(primary_error, asyncio.CancelledError):
            raise primary_error
        if isinstance(primary_error, RookFullError):
            raise primary_error
        if isinstance(primary_error, McpToolError) and authentic_envelope_received:
            raise primary_error
        raise RookFullError(
            "rook_full_outcome_uncertain",
            f"Rook MCP call ended without an authentic result envelope: {primary_error}",
        ) from primary_error
    if not cleanup_succeeded and not authentic_envelope_received:
        raise RookFullError(
            "rook_full_close_failed",
            cleanup_error or "Rook MCP cleanup failed",
        )
    return value


async def search(query: str):
    frozen_query = _require_nonempty_string(query, "query")
    configuration = _load_product_configuration()
    arguments = _locked_arguments({"query": frozen_query}, configuration)
    return await _invoke("rook_tools_search", arguments, configuration)


async def read(name: str):
    frozen_name = _require_nonempty_string(name, "name")
    configuration = _load_product_configuration()
    arguments = _locked_arguments({"name": frozen_name}, configuration)
    return await _invoke("rook_tools_read", arguments, configuration)


async def call(name: str, arguments: dict):
    frozen_name = _require_nonempty_string(name, "name")
    configuration = _load_product_configuration()
    if frozen_name.startswith("gh_") and configuration.grasshopper_document_id is None:
        raise _invalid("grasshopper_target_unbound")
    frozen_arguments = _locked_arguments(arguments, configuration)
    return await _invoke(
        "rook_tools_call",
        {"name": frozen_name, "arguments": frozen_arguments},
        configuration,
    )
