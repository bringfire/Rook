from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from rook.agent.chat import prime_process


pytestmark = pytest.mark.asyncio


@dataclass
class FakeProcess:
    pid: int
    returncode: int | None = None
    stdin: object | None = None
    exited: asyncio.Event | None = None

    async def wait(self):
        if self.returncode is None:
            if self.exited is None:
                await asyncio.Future()
            else:
                await self.exited.wait()
        return self.returncode

    def terminate(self):
        return None


def _owner():
    return prime_process.OwnedProcessGeneration(
        launch_generation=7,
        identity=prime_process.ProcessIdentity(pid=101, parent_pid=55, start_utc_ticks="638880485801234567"),
    )


async def test_windows_fallback_is_hidden_bounded_generation_qualified_and_single_attempt() -> None:
    calls = []
    process = FakeProcess(pid=101)

    async def taskkill(spec):
        calls.append(spec)
        process.returncode = -9
        return 0

    result = await prime_process.run_owned_windows_fallback(
        process=process,
        expected_owner=_owner(),
        launch_generation=7,
        identity_query=lambda _pid: _owner().identity,
        taskkill=taskkill,
        timeout_seconds=0.1,
    )

    assert result.succeeded is True
    assert result.uncertain is False
    assert len(calls) == 1
    assert calls[0].argv == ("taskkill.exe", "/PID", "101", "/T", "/F")
    assert calls[0].creationflags != 0


@pytest.mark.parametrize(
    ("generation", "observed"),
    (
        (8, (101, 55, "638880485801234567")),
        (7, (101, 55, "638880485801234568")),
        (7, None),
    ),
)
async def test_windows_fallback_refuses_uncertain_or_stale_identity_without_widening(
    generation: int,
    observed: tuple[int, int, str] | None,
) -> None:
    calls = []

    async def taskkill(spec):
        calls.append(spec)
        return 0

    observed_identity = (
        None
        if observed is None
        else prime_process.ProcessIdentity(
            pid=observed[0],
            parent_pid=observed[1],
            start_utc_ticks=observed[2],
        )
    )
    result = await prime_process.run_owned_windows_fallback(
        process=FakeProcess(pid=101),
        expected_owner=_owner(),
        launch_generation=generation,
        identity_query=lambda _pid: observed_identity,
        taskkill=taskkill,
        timeout_seconds=0.1,
    )

    assert result.succeeded is False
    assert result.uncertain is True
    assert calls == []


async def test_windows_fallback_timeout_is_terminal_and_not_retried() -> None:
    attempts = 0

    async def stalled_taskkill(_spec):
        nonlocal attempts
        attempts += 1
        await asyncio.Future()

    result = await prime_process.run_owned_windows_fallback(
        process=FakeProcess(pid=101),
        expected_owner=_owner(),
        launch_generation=7,
        identity_query=lambda _pid: _owner().identity,
        taskkill=stalled_taskkill,
        timeout_seconds=0.001,
    )

    assert result.succeeded is False
    assert result.uncertain is True
    assert attempts == 1


async def test_windows_fallback_requires_the_direct_child_exit_to_settle() -> None:
    attempts = 0

    async def taskkill(_spec):
        nonlocal attempts
        attempts += 1
        return 0

    result = await prime_process.run_owned_windows_fallback(
        process=FakeProcess(pid=101),
        expected_owner=_owner(),
        launch_generation=7,
        identity_query=lambda _pid: _owner().identity,
        taskkill=taskkill,
        timeout_seconds=0.001,
    )

    assert result.succeeded is False
    assert result.uncertain is True
    assert "direct child exit" in (result.message or "")
    assert attempts == 1


async def test_prime_retire_uses_only_the_generation_qualified_windows_fallback(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    process = FakeProcess(pid=101)

    async def taskkill(spec):
        calls.append(spec)
        process.returncode = -9
        return 0

    monkeypatch.setattr(prime_process.sys, "platform", "win32")
    runtime = prime_process.PrimeRpcProcess(
        node_path="node.exe",
        cli_path="D:/prime/dist/cli.js",
        session_dir=tmp_path / "sessions",
        generation=7,
        identity_query=lambda _pid: _owner().identity,
        taskkill=taskkill,
        fallback_timeout_seconds=0.1,
    )
    runtime._process = process
    runtime._owned_process_generation = _owner()

    await runtime.retire(0)

    assert len(calls) == 1
    assert runtime.cleanup_result == prime_process.OwnedCleanupResult(True, False)
