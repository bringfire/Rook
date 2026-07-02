from __future__ import annotations

import ast
import inspect

import pytest

import rook.agent.local_worker_model_transport as transport_module
from rook.agent.local_worker_adapter import TransportError
from rook.agent.local_worker_model_transport import (
    LiteLLMWorkerTransport,
    TransportCallInfo,
)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Usage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _Response:
    def __init__(self, content, usage=None, empty_choices=False):
        self.choices = [] if empty_choices else [_Choice(content)]
        self.usage = usage


class _FakeLitellm:
    def __init__(self, response=None, exc=None, cost=0.0012, cost_exc=None):
        self.calls = []
        self.response = response
        self.exc = exc
        self.cost = cost
        self.cost_exc = cost_exc

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response

    def completion_cost(self, completion_response):
        if self.cost_exc is not None:
            raise self.cost_exc
        return self.cost


_ARTIFACT = {
    "schema": "rook.local_worker_prompt_artifact:v1",
    "prompt_text_version": "lm5j.prompt_text:v1",
    "messages": [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "{\"k\":1}"},
    ],
}


def _transport(monkeypatch, fake, **kwargs):
    monkeypatch.setattr(transport_module, "litellm", fake)
    defaults = {"model": "openai/lmstudio-model", "profile_api_base": "http://localhost:1234/v1"}
    defaults.update(kwargs)
    return LiteLLMWorkerTransport(
        generation_params={"temperature": 0}, **defaults
    )


def test_module_all_is_exact() -> None:
    assert transport_module.__all__ == (
        "LiteLLMWorkerTransport",
        "TransportCallInfo",
    )


def test_constructor_rejects_empty_model() -> None:
    with pytest.raises(ValueError):
        LiteLLMWorkerTransport(model="")


def test_send_builds_kwargs_and_returns_content(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("hello", usage=_Usage(10, 5)))
    transport = _transport(monkeypatch, fake)
    result = transport.send(_ARTIFACT)
    assert result == "hello"
    call = fake.calls[0]
    assert call["model"] == "openai/lmstudio-model"
    assert call["messages"] == [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "{\"k\":1}"},
    ]
    assert call["temperature"] == 0
    assert call["timeout"] == 120.0
    # openai/* local model with profile api_base -> api_base forwarded
    assert call["api_base"] == "http://localhost:1234/v1"


def test_ollama_model_omits_api_base(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(
        monkeypatch, fake, model="ollama_chat/qwen3-coder:30b-a3b-q8_0"
    )
    transport.send(_ARTIFACT)
    assert "api_base" not in fake.calls[0]


def test_cloud_model_omits_api_base(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(monkeypatch, fake, model="anthropic/claude-haiku-4-5")
    transport.send(_ARTIFACT)
    assert "api_base" not in fake.calls[0]


def test_telemetry_filled_best_effort(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("hello", usage=_Usage(10, 5)))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    info = transport.last_call_info
    assert isinstance(info, TransportCallInfo)
    assert info.model == "openai/lmstudio-model"
    assert info.latency_ms >= 0
    assert info.prompt_tokens == 10
    assert info.completion_tokens == 5
    assert info.cost_usd == pytest.approx(0.0012)
    assert transport.last_raw_output == "hello"


def test_cost_failure_is_non_fatal(monkeypatch) -> None:
    fake = _FakeLitellm(
        response=_Response("hello", usage=_Usage(10, 5)),
        cost_exc=RuntimeError("no pricing"),
    )
    transport = _transport(monkeypatch, fake)
    assert transport.send(_ARTIFACT) == "hello"
    assert transport.last_call_info.cost_usd is None
    assert transport.last_call_info.prompt_tokens == 10


def test_missing_usage_is_non_fatal(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("hello", usage=None))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    assert transport.last_call_info.prompt_tokens is None
    assert transport.last_call_info.completion_tokens is None


def test_provider_exception_propagates_unwrapped(monkeypatch) -> None:
    class FakeAuthError(Exception):
        pass

    fake = _FakeLitellm(exc=FakeAuthError("bad key"))
    transport = _transport(monkeypatch, fake)
    with pytest.raises(FakeAuthError):
        transport.send(_ARTIFACT)


def test_reset_per_call(monkeypatch) -> None:
    good = _FakeLitellm(response=_Response("hello", usage=_Usage(1, 1)))
    transport = _transport(monkeypatch, good)
    transport.send(_ARTIFACT)
    assert transport.last_call_info is not None
    assert transport.last_raw_output == "hello"
    # second call fails at the provider: both attributes must be reset
    transport_module.litellm.exc = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        transport.send(_ARTIFACT)
    assert transport.last_call_info is None
    assert transport.last_raw_output is None


def test_none_content_is_declared_transport_error(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response(None))
    transport = _transport(monkeypatch, fake)
    with pytest.raises(TransportError):
        transport.send(_ARTIFACT)
    assert transport.last_raw_output is None


def test_empty_choices_is_declared_transport_error(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("x", empty_choices=True))
    transport = _transport(monkeypatch, fake)
    with pytest.raises(TransportError):
        transport.send(_ARTIFACT)


def test_empty_string_content_returns_normally(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response(""))
    transport = _transport(monkeypatch, fake)
    assert transport.send(_ARTIFACT) == ""
    assert transport.last_raw_output == ""


def test_no_structured_output_kwargs(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    call = fake.calls[0]
    for banned in ("response_format", "tools", "tool_choice", "functions"):
        assert banned not in call


def test_import_and_ast_guard() -> None:
    source = inspect.getsource(transport_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.update(alias.name for alias in node.names)
    banned = {
        "base_agent", "chat_runner", "tool_dispatcher", "prompt_builder",
        "local_worker_turn_harness", "local_worker_turn_disposition",
        "local_worker_scenario_evaluation", "plan_graph_live",
        "plan_graph_workflow_contract", "capability_record",
        "capability_inventory", "requests", "httpx", "aiohttp",
        "yaml", "pathlib",
    }
    assert not (imported & banned)
    assert "litellm" in imported
