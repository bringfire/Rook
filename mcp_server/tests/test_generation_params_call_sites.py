from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.config import AgentConfig, GuardianConfig
from rook.agent.guardian import Guardian


@pytest.mark.asyncio
async def test_base_agent_sonnet_5_omits_temperature(monkeypatch):
    captured = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    agent = RookAgent(
        config=AgentConfig(model="anthropic/claude-sonnet-5", temperature=0.0),
        tool_executor=AsyncMock(),
    )

    await agent._call_model([{"role": "user", "content": "hello"}])

    assert len(captured) == 1
    assert captured[0]["model"] == "anthropic/claude-sonnet-5"
    assert "temperature" not in captured[0]
    assert captured[0]["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_guardian_sonnet_5_omits_temperature(monkeypatch):
    captured = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"making_progress": true, "confidence": 0.9}'
                    )
                )
            ]
        )

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    monkeypatch.setattr("litellm.completion_cost", lambda completion_response: 0.0)

    guardian = Guardian(
        SimpleNamespace(token_usage={"input": 0}, config=AgentConfig()),
        config=GuardianConfig(llm_analysis_model="anthropic/claude-sonnet-5"),
        task_description="test task",
    )

    await guardian._run_llm_analysis()

    assert len(captured) == 1
    assert captured[0]["model"] == "anthropic/claude-sonnet-5"
    assert "temperature" not in captured[0]
    assert captured[0]["max_tokens"] == 300
