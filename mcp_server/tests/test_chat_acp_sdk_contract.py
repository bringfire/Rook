from __future__ import annotations

import asyncio
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.schema import (
    AgentMessageChunk,
    ClientCapabilities,
    Implementation,
    RequestPermissionResponse,
    TextContentBlock,
)


MCP_SERVER_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = MCP_SERVER_ROOT / "pyproject.toml"
FAKE_AGENT = Path(__file__).resolve().parent / "fixtures" / "fake_acp_agent.py"


def test_python_acp_sdk_is_exactly_pinned() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert "agent-client-protocol==0.12.1" in project["project"]["dependencies"]


class _RecordingClient:
    def __init__(self) -> None:
        self.message_text: list[str] = []

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        del session_id, kwargs
        if isinstance(update, AgentMessageChunk) and isinstance(update.content, TextContentBlock):
            self.message_text.append(update.content.text)

    async def request_permission(self, **kwargs: Any) -> RequestPermissionResponse:
        raise AssertionError(f"Unexpected permission request: {kwargs!r}")


@dataclass(frozen=True)
class _FakeRunResult:
    methods: list[str]
    received_message_text: list[str]
    stderr_bytes_written: int
    exit_code: int


async def _run_fake_agent(tmp_path: Path, scenario: dict[str, Any]) -> _FakeRunResult:
    scenario_path = tmp_path / "scenario.json"
    journal_path = tmp_path / "journal.jsonl"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

    client = _RecordingClient()
    process = None
    stderr_task: asyncio.Task[bytes] | None = None
    async with spawn_agent_process(
        client,
        sys.executable,
        str(FAKE_AGENT),
        "--scenario",
        str(scenario_path),
        "--journal",
        str(journal_path),
        transport_kwargs={"stderr": asyncio.subprocess.PIPE, "shutdown_timeout": 5.0},
    ) as (connection, process):
        assert process.stderr is not None
        stderr_task = asyncio.create_task(process.stderr.read())
        initialized = await connection.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(name="rook-test", version="1.0.0"),
        )
        assert initialized.protocol_version == PROTOCOL_VERSION
        opened = await connection.new_session(cwd=str(tmp_path), mcp_servers=[])
        prompted = await connection.prompt(
            session_id=opened.session_id,
            prompt=[text_block("test prompt")],
        )
        assert prompted.stop_reason == scenario["stop_reason"]
        await connection.close_session(session_id=opened.session_id)

    assert process is not None
    assert stderr_task is not None
    stderr = await stderr_task
    journal = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    return _FakeRunResult(
        methods=[row["method"] for row in journal if "method" in row],
        received_message_text=client.message_text,
        stderr_bytes_written=len(stderr),
        exit_code=process.returncode if process.returncode is not None else await process.wait(),
    )


@pytest.mark.asyncio
async def test_fake_agent_runs_initialize_new_prompt_close_and_eof(tmp_path: Path) -> None:
    result = await _run_fake_agent(
        tmp_path,
        {
            "session_id": "fake-session-1",
            "updates": [{"kind": "agent_message_chunk", "text": "hello"}],
            "stop_reason": "end_turn",
            "stderr_bytes": 0,
        },
    )

    assert result.methods == ["initialize", "session/new", "session/prompt", "session/close"]
    assert result.received_message_text == ["hello"]
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_fake_agent_emits_source_order_beyond_stderr_pipe_capacity(tmp_path: Path) -> None:
    expected = [str(value) for value in range(64)]
    result = await _run_fake_agent(
        tmp_path,
        {
            "session_id": "fake-session-2",
            "updates": [{"kind": "agent_message_chunk", "text": value} for value in expected],
            "stop_reason": "end_turn",
            "stderr_bytes": 2 * 1024 * 1024,
        },
    )

    assert result.received_message_text == expected
    assert result.stderr_bytes_written == 2 * 1024 * 1024
    assert result.exit_code == 0
