"""The stdio MCP server must survive the first lazy import of the learning stack.

Regression for the 1.6.0 install smoke: the first tool call that reached the
lazily imported bandit stack (``rook.knowledge._contextual_ready`` -> mabwiser
-> numpy) never answered. numpy's bundled OpenBLAS calls ``fstat`` on the
standard descriptors from its DLL initializer; with the transport's blocking
``ReadFile`` pending on the stdin pipe that ``fstat`` waits forever (CRT file
lock, then kernel pipe serialization), so the import deadlocked the server
inside ``LoadLibrary`` (see ``rook/win_stdio.py``).

``knowledge_query`` with ``depth="raw"`` skips the consolidated command
shortcut and falls through to ``query_knowledge``, which probes the contextual
bandit and therefore imports numpy, all without a Rhino instance. This drives
the real server over stdio, exactly as Claude Code / Codex do, and requires an
answer within a bound. Without the polling stdin reader the first call hangs
until the client gives up.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

_SRC = Path(__file__).resolve().parents[1] / "src"
_DEADLINE_SECONDS = 60.0

# depth="raw" is load-bearing: any other depth answers "create cone" from the
# consolidated command table and never touches the bandit import.
_CALLS = (
    ("knowledge_query", {"intent": "create cone", "depth": "raw"}),
    ("knowledge_query", {"intent": "loft surface", "depth": "raw"}),
    ("knowledge_query", {"intent": "loft surface", "depth": "quick"}),
)


def _server_params() -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    env.pop("ROOK_LOG_LEVEL", None)
    env["ANTHROPIC_API_KEY"] = ""
    return StdioServerParameters(command=sys.executable, args=["-m", "rook"], cwd=str(_SRC.parent), env=env)


async def _drive(tmp_path: Path) -> dict[str, float]:
    timings: dict[str, float] = {}
    with open(tmp_path / "server-stderr.log", "w", encoding="utf-8") as errlog:
        async with stdio_client(_server_params(), errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=_DEADLINE_SECONDS)
                for name, arguments in _CALLS:
                    started = time.perf_counter()
                    result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=_DEADLINE_SECONDS)
                    timings[f"{name}:{arguments['intent']}:{arguments['depth']}"] = time.perf_counter() - started
                    assert result.content, name
                    assert not result.isError, (name, result.content[0])
    return timings


def test_stdio_server_answers_after_the_lazy_learning_import(tmp_path: Path) -> None:
    timings = asyncio.run(_drive(tmp_path))
    assert len(timings) == len(_CALLS), timings
    # A bounded answer is the contract; the first raw call pays the lazy import.
    assert all(t < _DEADLINE_SECONDS for t in timings.values()), timings


@pytest.mark.skipif(sys.platform != "win32", reason="Windows pipe semantics")
def test_polling_stdin_installs_only_for_pipes() -> None:
    from rook import win_stdio

    # Under pytest stdin is usually not a pipe; the installer must leave it alone.
    original = sys.stdin
    try:
        installed = win_stdio.install_polling_stdin()
        if installed:
            assert isinstance(sys.stdin.buffer.raw, win_stdio.PollingPipeReader)
        else:
            assert sys.stdin is original
    finally:
        sys.stdin = original
