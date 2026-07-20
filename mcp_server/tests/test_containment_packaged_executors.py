from __future__ import annotations

import sys
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.bootstrap.executor import HttpExecutor, create_mock_executor  # noqa: E402
from rook.explorer.executor import HttpExecutor as ExplorerHttpExecutor  # noqa: E402
from rook.explorer.executor import MockExecutor as ExplorerMockExecutor  # noqa: E402
from rook.learning import agent as learning_agent  # noqa: E402
from rook.learning.hybrid_investigator import HybridInvestigator  # noqa: E402
from rook.learning.investigator import Investigator  # noqa: E402
from rook.tool_lifecycle import CONTAINED_TOOLS  # noqa: E402


CONTAINED = [entry.name for entry in CONTAINED_TOOLS]


@pytest.mark.parametrize("name", CONTAINED)
def test_bootstrap_real_and_mock_executors_deny_without_http(name: str) -> None:
    assert HttpExecutor("http://127.0.0.1:1").execute(name, {})["tool"] == name
    assert create_mock_executor()(name, {})["tool"] == name


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONTAINED)
async def test_explorer_real_and_mock_executors_deny_without_http(name: str) -> None:
    for executor in (ExplorerHttpExecutor("http://127.0.0.1:1"), ExplorerMockExecutor()):
        result = await executor.execute(name, {})
        assert result.success is False
        assert result.response["tool"] == name


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONTAINED)
async def test_learning_executor_and_investigators_deny_without_models_or_hosts(name: str) -> None:
    executor = await learning_agent.create_tool_executor()
    assert (await executor(name, {}))["tool"] == name

    investigator = object.__new__(Investigator)
    experiment = await investigator._run_experiment(name, {})
    assert experiment.success is False
    assert experiment.response["tool"] == name

    hybrid = object.__new__(HybridInvestigator)
    result = await hybrid.investigate_tool(name)
    assert result.success is False
    assert result.tool == name
