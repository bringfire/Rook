from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from rook.agent.chat import prime_process


pytestmark = pytest.mark.asyncio


class FakeStdin:
    def __init__(self, *, stall: bool = False) -> None:
        self.closed = False
        self.stall = stall

    def is_closing(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        if self.stall:
            await asyncio.Future()
        return None


@dataclass
class FakeProcess:
    wait_outcomes: list[str]
    pid: int = 101
    returncode: int | None = None
    stdin: FakeStdin = field(default_factory=FakeStdin)
    terminate_calls: int = 0
    kill_calls: int = 0

    async def wait(self) -> int:
        outcome = self.wait_outcomes.pop(0)
        if outcome == "stall":
            await asyncio.Future()
        if outcome == "graceful":
            self.returncode = 0
        elif outcome == "terminated":
            self.returncode = -15
        elif outcome == "killed":
            self.returncode = -9
        else:
            raise AssertionError(outcome)
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


def runtime(tmp_path, process: FakeProcess):
    owner = prime_process.PrimeRpcProcess(
        node_path="node.exe",
        cli_path="D:/prime/dist/cli.js",
        session_dir=tmp_path / "sessions",
        generation=7,
        cleanup_timeout_seconds=0.01,
    )
    owner._process = process
    return owner


async def test_graceful_retirement_uses_only_the_direct_handle(tmp_path) -> None:
    process = FakeProcess(["graceful"])
    owner = runtime(tmp_path, process)

    await owner.retire(0.01)

    assert process.terminate_calls == 0
    assert process.kill_calls == 0
    assert owner.cleanup_result == prime_process.OwnedCleanupResult(
        succeeded=True,
        uncertain=False,
        message="Prime direct child exited gracefully",
    )


async def test_terminate_fallback_is_retained_as_non_graceful_cleanup(tmp_path) -> None:
    process = FakeProcess(["stall", "terminated"])
    owner = runtime(tmp_path, process)

    await owner.retire(0.001)

    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert owner.cleanup_result == prime_process.OwnedCleanupResult(
        succeeded=False,
        uncertain=False,
        message="Prime direct child required terminate after graceful close timed out",
    )


async def test_kill_fallback_is_retained_as_non_graceful_cleanup(tmp_path) -> None:
    process = FakeProcess(["stall", "stall", "killed"])
    owner = runtime(tmp_path, process)

    await owner.retire(0.001)

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert owner.cleanup_result == prime_process.OwnedCleanupResult(
        succeeded=False,
        uncertain=False,
        message="Prime direct child required kill after terminate timed out",
    )


async def test_unsettled_kill_is_uncertain_and_never_widens_cleanup(tmp_path) -> None:
    process = FakeProcess(["stall", "stall", "stall"])
    owner = runtime(tmp_path, process)

    await owner.retire(0.001)

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert owner.cleanup_result == prime_process.OwnedCleanupResult(
        succeeded=False,
        uncertain=True,
        message="Prime direct child did not settle after kill",
    )


async def test_stalled_stdin_close_is_bounded_and_fails_qualification(tmp_path) -> None:
    process = FakeProcess(["graceful"], stdin=FakeStdin(stall=True))
    owner = runtime(tmp_path, process)

    await owner.retire(0.01)

    assert process.returncode == 0
    assert owner.cleanup_result == prime_process.OwnedCleanupResult(
        succeeded=False,
        uncertain=False,
        message="Prime stdin close timed out before direct child exited",
    )


async def test_nonzero_natural_exit_is_not_graceful(tmp_path) -> None:
    process = FakeProcess([])
    process.returncode = 7
    owner = runtime(tmp_path, process)

    await owner.retire(0.01)

    assert owner.cleanup_result == prime_process.OwnedCleanupResult(
        succeeded=False,
        uncertain=False,
        message="Prime direct child exited with code 7",
    )
