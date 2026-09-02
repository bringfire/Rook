from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION, run_agent, update_agent_message_text, update_agent_thought_text
from acp.schema import (
    AgentCapabilities,
    ClientCapabilities,
    CloseSessionResponse,
    Implementation,
    NewSessionResponse,
    PermissionOption,
    PromptCapabilities,
    PromptResponse,
    SessionCapabilities,
    SessionCloseCapabilities,
    ToolCallStart,
)


class EventJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n"):
            pass
        self._path = path

    def append(self, event: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
            handle.flush()


class FakeAgent:
    def __init__(self, scenario: dict[str, Any], journal: EventJournal) -> None:
        self._scenario = scenario
        self._journal = journal
        self._client: Any | None = None
        self._cancelled = asyncio.Event()

    def on_connect(self, client: Any) -> None:
        self._client = client

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> Any:
        self._journal.append(
            {
                "method": "initialize",
                "protocolVersion": protocol_version,
                "clientCapabilities": None
                if client_capabilities is None
                else client_capabilities.model_dump(by_alias=True, exclude_none=True),
                "clientInfo": None
                if client_info is None
                else client_info.model_dump(by_alias=True, exclude_none=True),
                "meta": kwargs or None,
            }
        )
        advertise_close = self._scenario.get("advertise_close", True)
        capabilities = None
        if not self._scenario.get("null_agent_capabilities", False):
            capabilities = AgentCapabilities(
                prompt_capabilities=None
                if self._scenario.get("null_prompt_capabilities", False)
                else PromptCapabilities(image=self._scenario.get("image_capability", True)),
                session_capabilities=None
                if self._scenario.get("null_session_capabilities", False)
                else SessionCapabilities(close=SessionCloseCapabilities() if advertise_close else None),
            )
        return {
            "protocolVersion": self._scenario.get("protocol_version", PROTOCOL_VERSION),
            "agentCapabilities": None
            if capabilities is None
            else capabilities.model_dump(by_alias=True, exclude_none=False),
            "agentInfo": Implementation(
                name="rook-fake-acp-agent",
                title="Rook Fake ACP Agent",
                version="1.0.0",
            ).model_dump(by_alias=True, exclude_none=True),
        }

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        self._journal.append(
            {
                "method": "session/new",
                "cwd": cwd,
                "additionalDirectories": additional_directories,
                "mcpServers": [
                    server.model_dump(by_alias=True, exclude_none=True)
                    for server in (mcp_servers or [])
                ],
                "meta": kwargs or None,
            }
        )
        return NewSessionResponse(session_id=self._scenario["session_id"])

    async def prompt(self, session_id: str, prompt: list[Any], **kwargs: Any) -> PromptResponse:
        self._journal.append(
            {
                "method": "session/prompt",
                "sessionId": session_id,
                "prompt": [block.model_dump(by_alias=True, exclude_none=True) for block in prompt],
                "meta": kwargs or None,
            }
        )
        stderr_bytes = int(self._scenario.get("stderr_bytes", 0))
        self._write_stderr(stderr_bytes // 2)

        if permission := self._scenario.get("permission"):
            if self._client is None:
                raise RuntimeError("ACP client connection was not established")
            tool_call = ToolCallStart(
                session_update="tool_call",
                tool_call_id=permission.get("tool_call_id", "fake-tool-call"),
                title=permission.get("title", "Fake tool call"),
                status="pending",
            )
            options = [PermissionOption.model_validate(option) for option in permission["options"]]
            response = await self._client.request_permission(
                session_id=session_id,
                tool_call=tool_call,
                options=options,
            )
            self._journal.append(
                {
                    "event": "permission_response",
                    "response": response.model_dump(by_alias=True, exclude_none=True),
                }
            )

        if self._client is None:
            raise RuntimeError("ACP client connection was not established")
        for index, update in enumerate(self._scenario.get("updates", [])):
            kind = update["kind"]
            if kind == "agent_message_chunk":
                payload = update_agent_message_text(str(update["text"]))
            elif kind == "agent_thought_chunk":
                payload = update_agent_thought_text(str(update["text"]))
            else:
                raise ValueError(f"Unsupported fake update kind: {kind}")
            self._journal.append(
                {
                    "event": "session_update",
                    "sourceOrdinal": index,
                    "update": payload.model_dump(by_alias=True, exclude_none=True),
                }
            )
            await self._client.session_update(session_id=session_id, update=payload)

        self._write_stderr(stderr_bytes - (stderr_bytes // 2))
        if self._scenario.get("hang_prompt", False):
            await self._cancelled.wait()
            stop_reason = "cancelled"
        else:
            stop_reason = self._scenario["stop_reason"]
        return PromptResponse(stop_reason=stop_reason)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self._journal.append(
            {"method": "session/cancel", "sessionId": session_id, "meta": kwargs or None}
        )
        self._cancelled.set()

    async def close_session(self, session_id: str, **kwargs: Any) -> CloseSessionResponse:
        self._journal.append(
            {"method": "session/close", "sessionId": session_id, "meta": kwargs or None}
        )
        if self._scenario.get("close_error", False):
            raise RuntimeError("configured close failure")
        return CloseSessionResponse()

    @staticmethod
    def _write_stderr(byte_count: int) -> None:
        remaining = byte_count
        chunk = b"x" * (8 * 1024)
        while remaining > 0:
            payload = chunk[: min(len(chunk), remaining)]
            sys.stderr.buffer.write(payload)
            sys.stderr.buffer.flush()
            remaining -= len(payload)


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    return parser.parse_known_args()


async def _main() -> None:
    args, retained_argv = _parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    journal = EventJournal(args.journal)
    journal.append({"event": "process_start", "argv": retained_argv})
    await run_agent(FakeAgent(scenario, journal), use_unstable_protocol=True)


if __name__ == "__main__":
    asyncio.run(_main())
