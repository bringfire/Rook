from __future__ import annotations

from copy import deepcopy
import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rlm import McpIntegration
from rlm.mcp_base import McpToolError
from rook import gh_behavioral_acceptance as _acceptance


__all__ = ("search", "read", "call")


_COMMAND = "C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe"
_CWD = "C:/Users/bring/AppData/Local/Rook/app/mcp_server"
_STATIC_ENV = {
    "PYTHONPATH": "",
    "PYTHONHOME": "",
    "ROOK_INSTALL_ROOT": "C:/Users/bring/AppData/Local/Rook/app",
    "ROOK_DATA_DIR": "C:/Users/bring/AppData/Local/Rook/data",
    "ROOK_MODE": "release",
    "DSPY_CACHEDIR": "C:/Users/bring/AppData/Local/Rook/data/dspy-cache",
    "ROOK_DSPY_RESTRICT_PICKLE": "1",
    "CHIRP_HOME": "C:/Users/bring/AppData/Local/Rook/app/chirp",
    "ROOK_MCP_TOOL_PROFILE": "full",
    "ROOK_MCP_TARGET_MODE": "panel_locked",
}
_TARGET_ENV = (
    "ROOK_MCP_TARGET_PROCESS_ID",
    "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER",
)
_SOURCE_LOG_ENV = "ROOK_GH_AUTHORING_SOURCE_LOG"
_CALL_LIMIT_ENV = "ROOK_GATEWAY_CALL_LIMIT"
_gateway_call_count = 0


def _positive_environment_value(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.isascii() or not value.isdigit() or int(value) <= 0:
        raise RuntimeError(f"missing or invalid {name}")
    return value


def _reserve_gateway_call() -> None:
    global _gateway_call_count
    limit = int(_positive_environment_value(_CALL_LIMIT_ENV))
    if _gateway_call_count >= limit:
        raise RuntimeError("rook_gateway_call_limit_exceeded")
    _gateway_call_count += 1


class _RookFull(McpIntegration):
    server = "rook-full"

    async def _open_session(self, stack: AsyncExitStack) -> ClientSession:
        env = {
            **_STATIC_ENV,
            **{name: _positive_environment_value(name) for name in _TARGET_ENV},
        }
        parameters = StdioServerParameters(
            command=_COMMAND,
            args=["-m", "rook"],
            cwd=_CWD,
            env=env,
        )
        errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
        read, write = await stack.enter_async_context(
            stdio_client(parameters, errlog=errlog)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session


_integration = _RookFull()


def _is_closed_result_envelope(value) -> bool:
    return (
        type(value) is dict
        and set(value) == {"success", "data"}
        and type(value["success"]) is bool
    )


async def _recorded_call(target: str, arguments: dict, operation):
    source_path = os.environ[_SOURCE_LOG_ENV]
    retained_arguments = deepcopy(arguments)
    _reserve_gateway_call()
    try:
        result = await operation
    except McpToolError as exc:
        _acceptance.append_canonical_gateway_error_source_event(
            source_path,
            target,
            retained_arguments,
            exception=exc,
            structured_content=exc.structured_content,
        )
        raise
    except Exception as exc:
        _acceptance.append_canonical_gateway_source_event(
            source_path,
            target,
            retained_arguments,
            exception=exc,
        )
        raise
    if not _is_closed_result_envelope(result):
        error = RuntimeError("rook_full_malformed_result")
        _acceptance.append_canonical_gateway_source_event(
            source_path,
            target,
            retained_arguments,
            exception=error,
        )
        raise error
    _acceptance.append_canonical_gateway_source_event(
        source_path,
        target,
        retained_arguments,
        result=result,
    )
    if result["success"] is False:
        raise RuntimeError("rook_full_unsuccessful_result")
    return result["data"]


async def search(query: str):
    arguments = {"query": query}
    return await _recorded_call(
        "rook_tools_search",
        arguments,
        _integration.call_tool("rook_tools_search", arguments),
    )


async def read(name: str):
    arguments = {"name": name}
    return await _recorded_call(
        "rook_tools_read",
        arguments,
        _integration.call_tool("rook_tools_read", arguments),
    )


async def call(name: str, arguments: dict):
    return await _recorded_call(
        name,
        arguments,
        _integration.call_tool(
            "rook_tools_call",
            {"name": name, "arguments": arguments},
        ),
    )
