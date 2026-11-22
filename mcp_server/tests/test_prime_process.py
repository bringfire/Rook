from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from rook.agent.chat.prime_process import (
    MAX_JSONL_ROW_BYTES,
    PrimeControlTimeout,
    PrimeLaunchConfiguration,
    PrimeProcessLost,
    PrimeProtocolError,
    PrimeRpcProcess,
)
from rook.agent.chat.prime_rpc_protocol import parse_prompt_settlement


pytestmark = pytest.mark.asyncio
FIXTURE = Path(__file__).parent / "fixtures" / "prime_rpc_fake_child.py"
GH_ID = "12345678-1234-1234-1234-1234567890ab"


def launch_configuration(tmp_path: Path) -> PrimeLaunchConfiguration:
    prime_root = tmp_path / "prime"
    goal_skill = prime_root / "packages" / "coding-agent" / "skills" / "goal"
    product_root = tmp_path / "product"
    rook_skill = product_root / ("A" * 64) / "rook-full"
    kernel = tmp_path / "kernels" / ("B" * 64)
    mcp_python = tmp_path / "installed" / "venv" / "Scripts" / "python.exe"
    mcp_workdir = tmp_path / "installed" / "app" / "mcp_server"
    install_root = tmp_path / "installed" / "app"
    data_root = tmp_path / "installed" / "data"
    for directory in (
        goal_skill,
        rook_skill,
        kernel.parent,
        mcp_python.parent,
        mcp_workdir,
        data_root / "dspy-cache",
        install_root / "chirp",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (goal_skill / "SKILL.md").write_text("goal", encoding="utf-8")
    (rook_skill / "SKILL.md").write_text("rook", encoding="utf-8")
    mcp_python.touch()
    return PrimeLaunchConfiguration(
        prime_root=prime_root,
        product_root=product_root,
        goal_skill_path=goal_skill,
        rook_skill_path=rook_skill,
        system_prompt_path=rook_skill / "SKILL.md",
        kernel_environment_path=kernel,
        product_environment={
            "ROOK_MCP_PYTHON_EXECUTABLE": str(mcp_python),
            "ROOK_MCP_WORKING_DIRECTORY": str(mcp_workdir),
            "ROOK_INSTALL_ROOT": str(install_root),
            "ROOK_DATA_DIR": str(data_root),
            "DSPY_CACHEDIR": str(data_root / "dspy-cache"),
            "CHIRP_HOME": str(install_root / "chirp"),
            "ROOK_MODE": "release",
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
            "ROOK_MCP_TOOL_PROFILE": "readonly",
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_PROCESS_ID": "2468",
            "ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS": "638920000000000000",
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
            "ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID": GH_ID,
        },
    )


def make_process(
    tmp_path: Path,
    scenario: str = "complete",
    *,
    generation: int = 7,
    control_timeout_seconds: float = 0.5,
    max_row_bytes: int = MAX_JSONL_ROW_BYTES,
) -> PrimeRpcProcess:
    return PrimeRpcProcess(
        node_path=sys.executable,
        cli_path=FIXTURE,
        session_dir=tmp_path / "sessions",
        generation=generation,
        extra_args=("--scenario", scenario),
        control_timeout_seconds=control_timeout_seconds,
        max_row_bytes=max_row_bytes,
    )


async def test_exact_new_session_and_configured_argument_arrays(tmp_path: Path) -> None:
    launch = launch_configuration(tmp_path)
    plain = PrimeRpcProcess(
        node_path="node.exe",
        cli_path="D:/prime/dist/cli.js",
        session_dir=tmp_path / "sessions",
        generation=1,
        launch_configuration=launch,
    )
    configured = PrimeRpcProcess(
        node_path="node.exe",
        cli_path="D:/prime/dist/cli.js",
        session_dir=tmp_path / "sessions",
        generation=2,
        launch_configuration=launch,
        provider="openai-codex",
        model_id="gpt-5.6-sol",
        thinking="xhigh",
    )

    expected = [
        "node.exe",
        "D:/prime/dist/cli.js",
        "--mode",
        "rpc",
        "--session-dir",
        str(tmp_path / "sessions"),
        "--tools",
        "ipython",
        "--no-extensions",
        "--no-skills",
        "--skill",
        str(launch.goal_skill_path),
        "--skill",
        str(launch.rook_skill_path),
        "--no-context-files",
        "--no-prompt-templates",
        "--append-system-prompt-file",
        str(launch.system_prompt_path),
    ]
    assert plain.argv == expected
    assert configured.argv == expected + [
        "--model",
        "openai-codex/gpt-5.6-sol",
        "--thinking",
        "xhigh",
    ]
    assert "--api-key" not in plain.argv + configured.argv
    assert "--no-tools" not in plain.argv + configured.argv


async def test_prime_child_environment_replaces_ambient_product_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "effective-environment.json"
    launch = launch_configuration(tmp_path)
    monkeypatch.setenv("PRIME_AGENT_KERNEL_VENV", "C:/ambient/kernel")
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setenv("ROOK_MCP_TARGET_PROCESS_ID", "9999")
    process = PrimeRpcProcess(
        node_path=sys.executable,
        cli_path=FIXTURE,
        session_dir=tmp_path / "sessions",
        generation=1,
        launch_configuration=launch,
        extra_args=("--environment-output", str(output)),
    )

    await process.start()
    effective = json.loads(output.read_text(encoding="utf-8"))

    assert effective["PRIME_AGENT_KERNEL_VENV"] == str(
        launch.kernel_environment_path
    )
    assert effective["ROOK_MCP_TOOL_PROFILE"] == "readonly"
    assert effective["ROOK_MCP_TARGET_PROCESS_ID"] == "2468"
    assert effective["ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID"] == GH_ID
    await process.retire(1.0)


@pytest.mark.parametrize("field", ("goal_skill_path", "rook_skill_path", "system_prompt_path"))
async def test_launch_rejects_authority_paths_outside_verified_roots(
    tmp_path: Path,
    field: str,
) -> None:
    launch = launch_configuration(tmp_path)
    outside = tmp_path / "outside" / "SKILL.md"
    outside.parent.mkdir()
    outside.write_text("outside", encoding="utf-8")
    values = dict(launch.__dict__)
    values[field] = outside

    with pytest.raises(ValueError, match="verified .* root|system prompt"):
        PrimeLaunchConfiguration(**values)


async def test_api_key_argument_is_prohibited(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="api-key"):
        PrimeRpcProcess(
            node_path="node.exe",
            cli_path="D:/prime/dist/cli.js",
            session_dir=tmp_path / "sessions",
            generation=1,
            extra_args=("--api-key", "secret"),
        )


async def test_prime_child_strips_inherited_and_dotenv_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "effective-environment.json"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "inherited-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "dotenv-openai")
    monkeypatch.setenv("SERPER_API_KEY", "web-key")
    monkeypatch.setenv("AWS_PROFILE", "credential-profile")
    monkeypatch.setenv("ROOK_SESSION_NONCE", "required-nonce")
    process = PrimeRpcProcess(
        node_path=sys.executable,
        cli_path=FIXTURE,
        session_dir=tmp_path / "sessions",
        generation=1,
        extra_args=("--environment-output", str(output)),
    )

    await process.start()
    effective = json.loads(output.read_text(encoding="utf-8"))

    assert effective == {"ROOK_SESSION_NONCE": "required-nonce"}
    await process.retire(1.0)


async def test_resume_appends_exact_registry_session_path(tmp_path: Path) -> None:
    saved = tmp_path / "saved" / "session.jsonl"
    process = PrimeRpcProcess(
        node_path="node.exe",
        cli_path="D:/prime/dist/cli.js",
        session_dir=tmp_path / "sessions",
        generation=1,
        resume_session_path=saved,
    )

    assert process.argv[-2:] == ["--resume", str(saved)]


async def test_resume_runtime_reports_the_exact_saved_session_path(tmp_path: Path) -> None:
    saved = tmp_path / "saved" / "session.jsonl"
    process = PrimeRpcProcess(
        node_path=sys.executable,
        cli_path=FIXTURE,
        session_dir=tmp_path / "sessions",
        generation=1,
        resume_session_path=saved,
    )

    state = await process.start()

    assert state.session_path == str(saved.absolute())
    await process.retire(1.0)


async def test_start_returns_closed_runtime_state_and_tags_events(tmp_path: Path) -> None:
    process = make_process(tmp_path)
    events: list[tuple[int, dict]] = []
    process.subscribe(lambda generation, event: events.append((generation, event)))

    state = await process.start()
    response = await process.command(
        {"type": "prompt_and_wait", "message": "hello", "images": []},
        expected_command="prompt_and_wait",
        timeout_seconds=None,
    )
    await asyncio.sleep(0)

    assert state.session_id == "fixture-session"
    assert Path(state.session_path).is_absolute()
    assert (state.provider, state.model_id, state.thinking) == (
        "fixture",
        "model",
        None,
    )
    assert parse_prompt_settlement(response).outcome == "completed"
    assert all(generation == 7 for generation, _event in events)
    assert [event["type"] for _generation, event in events] == [
        "agent_start",
        "message_update",
        "agent_end",
    ]
    await process.retire(1.0)


async def test_two_agent_segments_arrive_before_correlated_settlement(tmp_path: Path) -> None:
    process = make_process(tmp_path, "two_segments_then_complete")
    events: list[dict] = []
    process.subscribe(lambda _generation, event: events.append(event))
    await process.start()

    response = await process.command(
        {"id": "turn-1", "type": "prompt_and_wait", "message": "hello"},
        expected_command="prompt_and_wait",
        timeout_seconds=None,
    )
    await asyncio.sleep(0)

    assert [event["type"] for event in events].count("agent_end") == 2
    assert parse_prompt_settlement(response).request_id == "turn-1"
    await process.retire(1.0)


async def test_structured_prompt_failure_is_preserved(tmp_path: Path) -> None:
    process = make_process(tmp_path, "provider_failure")
    await process.start()

    response = await process.command(
        {"type": "prompt_and_wait", "message": "hello"},
        expected_command="prompt_and_wait",
        timeout_seconds=None,
    )

    settlement = parse_prompt_settlement(response)
    assert settlement.error_code == "execution_failed"
    assert settlement.error_message == "fixture provider failure"
    await process.retire(1.0)


@pytest.mark.parametrize("scenario", ["malformed_json", "malformed_response", "wrong_response_id"])
async def test_protocol_failures_reject_pending_prompt(
    tmp_path: Path,
    scenario: str,
) -> None:
    process = make_process(tmp_path, scenario)
    await process.start()

    with pytest.raises(PrimeProtocolError):
        await process.command(
            {"type": "prompt_and_wait", "message": "hello"},
            expected_command="prompt_and_wait",
            timeout_seconds=None,
        )

    await process.retire(1.0)


async def test_duplicate_response_is_ignored_after_first_resolution(tmp_path: Path) -> None:
    process = make_process(tmp_path, "duplicate_response")
    await process.start()

    response = await process.command(
        {"type": "prompt_and_wait", "message": "hello"},
        expected_command="prompt_and_wait",
        timeout_seconds=None,
    )
    await asyncio.sleep(0.02)
    state = await process.command({"type": "get_state"}, expected_command="get_state")

    assert parse_prompt_settlement(response).outcome == "completed"
    assert state["success"] is True
    await process.retire(1.0)


async def test_process_exit_fails_pending_prompt_once(tmp_path: Path) -> None:
    process = make_process(tmp_path, "exit_mid_prompt")
    await process.start()

    with pytest.raises(PrimeProcessLost):
        await process.command(
            {"type": "prompt_and_wait", "message": "hello"},
            expected_command="prompt_and_wait",
            timeout_seconds=None,
        )

    await process.retire(1.0)


async def test_control_timeout_is_bounded_and_late_response_is_ignored(tmp_path: Path) -> None:
    process = make_process(tmp_path, "stalled_control_response")
    await process.start()

    with pytest.raises(PrimeControlTimeout, match="get_available_models"):
        await process.command(
            {"type": "get_available_models"},
            expected_command="get_available_models",
            timeout_seconds=0.05,
        )

    abort = await process.command({"type": "abort"}, expected_command="abort")
    assert abort["success"] is True
    await process.retire(1.0)


async def test_oversized_jsonl_row_fails_closed(tmp_path: Path) -> None:
    assert MAX_JSONL_ROW_BYTES == 64 * 1024 * 1024
    process = make_process(tmp_path, "oversized_row", max_row_bytes=512)
    await process.start()

    with pytest.raises(PrimeProtocolError, match="row exceeds"):
        await process.command(
            {"type": "prompt_and_wait", "message": "hello"},
            expected_command="prompt_and_wait",
            timeout_seconds=None,
        )

    await process.retire(1.0)


async def test_stderr_diagnostics_are_retained_in_a_bounded_tail(tmp_path: Path) -> None:
    process = make_process(tmp_path, "stderr_flood")
    await process.start()
    await asyncio.sleep(0.05)

    assert 0 < len(process.stderr_tail.encode("utf-8")) <= 256 * 1024
    assert set(process.stderr_tail) == {"x"}
    await process.retire(1.0)


async def test_stale_process_events_retain_their_own_generation(tmp_path: Path) -> None:
    tagged: list[int] = []
    first = make_process(tmp_path / "one", generation=10)
    second = make_process(tmp_path / "two", generation=11)
    first.subscribe(lambda generation, _event: tagged.append(generation))
    second.subscribe(lambda generation, _event: tagged.append(generation))
    await first.start()
    await second.start()

    await first.command(
        {"type": "prompt_and_wait", "message": "old"},
        expected_command="prompt_and_wait",
        timeout_seconds=None,
    )
    await second.command(
        {"type": "prompt_and_wait", "message": "current"},
        expected_command="prompt_and_wait",
        timeout_seconds=None,
    )
    await asyncio.sleep(0)

    assert 10 in tagged and 11 in tagged
    await first.retire(1.0)
    await second.retire(1.0)


async def test_retirement_is_idempotent(tmp_path: Path) -> None:
    process = make_process(tmp_path)
    await process.start()

    await process.retire(1.0)
    await process.retire(1.0)

    with pytest.raises(PrimeProcessLost):
        await process.command({"type": "get_state"}, expected_command="get_state")
