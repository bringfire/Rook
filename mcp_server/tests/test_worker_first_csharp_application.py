from __future__ import annotations

from typing import Any

import pytest

import rook.agent.worker_first_csharp_application as application
from rook.agent.minimal_intent_worker_integration import MinimalPlannerDraftAdapter
from rook.agent.model_profiles import ModelSet


_INTENT = "Create one C# component."
_PLANNER_MODEL = "anthropic/claude-opus-4-6"
_WORKER_MODEL = "ollama_chat/qwen3-coder:30b-a3b-q8_0"
_API_BASE = "http://profile.invalid/v1"


class _Transport:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs

    def send(self, prompt_artifact: dict[str, Any]) -> str:
        raise AssertionError("transport contact is not part of this unit test")


class _Dispatcher:
    def __init__(self, local_tools: dict[str, object]) -> None:
        self.local_tools = local_tools
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.response = {"success": True, "source": "dispatcher"}

    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, params))
        return self.response


class _EqualSpoof:
    def __eq__(self, other: object) -> bool:
        return True


class _Harness:
    def __init__(self, models: ModelSet | None = None) -> None:
        self.models = models or ModelSet(
            planner=_PLANNER_MODEL,
            worker=_WORKER_MODEL,
            specialist="unused-specialist",
            guardian="unused-guardian",
            dspy="unused-dspy",
            api_base=_API_BASE,
        )
        self.events: list[str] = []
        self.transport_kwargs: list[dict[str, Any]] = []
        self.transports: list[_Transport] = []
        self.local_tools = {"gh_create_csharp_script": object()}
        self.dispatchers: list[_Dispatcher] = []
        self.integration_calls: list[dict[str, Any]] = []
        self.planner_schema_calls = 0
        self.worker_schema_calls = 0
        self.native_result = object()

    def get_models(self, profile: str) -> ModelSet:
        self.events.append(f"profile:{profile}")
        return self.models

    def construct_transport(self, **kwargs: Any) -> _Transport:
        self.events.append(f"transport:{kwargs['model']}")
        self.transport_kwargs.append(kwargs)
        transport = _Transport(kwargs)
        self.transports.append(transport)
        return transport

    def build_tools(self) -> dict[str, object]:
        self.events.append("build_local_tools")
        return self.local_tools

    def construct_dispatcher(
        self,
        *,
        local_tools: dict[str, object],
    ) -> _Dispatcher:
        self.events.append("dispatcher")
        dispatcher = _Dispatcher(local_tools)
        self.dispatchers.append(dispatcher)
        return dispatcher

    def build_planner_schema(self) -> dict[str, Any]:
        self.planner_schema_calls += 1
        return {"type": "object", "title": f"planner-{self.planner_schema_calls}"}

    def build_worker_schema(self) -> dict[str, Any]:
        self.worker_schema_calls += 1
        return {"oneOf": [{"title": f"worker-{self.worker_schema_calls}"}]}

    async def run_integration(
        self,
        intent: str,
        *,
        planner_adapter: MinimalPlannerDraftAdapter,
        worker_transport: _Transport,
        tool_executor: Any,
    ) -> object:
        self.events.append("integration")
        self.integration_calls.append(
            {
                "intent": intent,
                "planner_adapter": planner_adapter,
                "worker_transport": worker_transport,
                "tool_executor": tool_executor,
            }
        )
        return self.native_result


def _install_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    models: ModelSet | None = None,
) -> _Harness:
    harness = _Harness(models)
    monkeypatch.setattr(application, "get_models", harness.get_models, raising=False)
    monkeypatch.setattr(
        application,
        "LiteLLMWorkerTransport",
        harness.construct_transport,
        raising=False,
    )
    monkeypatch.setattr(
        application,
        "build_local_tools",
        harness.build_tools,
        raising=False,
    )
    monkeypatch.setattr(
        application,
        "ToolDispatcher",
        harness.construct_dispatcher,
        raising=False,
    )
    monkeypatch.setattr(
        application,
        "run_minimal_intent_worker_initial_body_integration",
        harness.run_integration,
        raising=False,
    )
    monkeypatch.setattr(
        application,
        "build_minimal_planner_draft_response_schema",
        harness.build_planner_schema,
        raising=False,
    )
    monkeypatch.setattr(
        application,
        "build_local_worker_response_schema",
        harness.build_worker_schema,
        raising=False,
    )
    return harness


@pytest.mark.asyncio
async def test_application_constructs_fixed_hierarchy_and_returns_native_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _install_harness(monkeypatch)

    result = await application.run_worker_first_csharp_application(_INTENT)

    assert result is harness.native_result
    assert harness.events == [
        "profile:hybrid",
        f"transport:{_PLANNER_MODEL}",
        f"transport:{_WORKER_MODEL}",
        "build_local_tools",
        "dispatcher",
        "integration",
    ]
    assert harness.dispatchers[0].local_tools is harness.local_tools
    assert len(harness.integration_calls) == 1
    integration = harness.integration_calls[0]
    assert integration["intent"] == _INTENT
    assert type(integration["planner_adapter"]) is MinimalPlannerDraftAdapter
    assert integration["planner_adapter"]._transport is harness.transports[0]
    assert integration["worker_transport"] is harness.transports[1]


@pytest.mark.asyncio
async def test_application_constructs_role_specific_transport_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _install_harness(monkeypatch)

    await application.run_worker_first_csharp_application(_INTENT)

    assert harness.transport_kwargs == [
        {
            "model": _PLANNER_MODEL,
            "profile_api_base": _API_BASE,
            "generation_params": {
                "temperature": 0,
                "max_tokens": 1024,
                "max_retries": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "minimal_planner_draft",
                        "strict": True,
                        "schema": {"type": "object", "title": "planner-1"},
                    },
                },
            },
            "structured_response_schema": None,
            "timeout_s": 120.0,
        },
        {
            "model": _WORKER_MODEL,
            "profile_api_base": _API_BASE,
            "generation_params": {
                "temperature": 0,
                "max_tokens": 1024,
                "max_retries": 0,
            },
            "structured_response_schema": {
                "oneOf": [{"title": "worker-1"}]
            },
            "timeout_s": 120.0,
        },
    ]


@pytest.mark.asyncio
async def test_application_builds_fresh_role_schemas_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _install_harness(monkeypatch)

    await application.run_worker_first_csharp_application(_INTENT)
    await application.run_worker_first_csharp_application(_INTENT)

    assert harness.planner_schema_calls == 2
    assert harness.worker_schema_calls == 2
    assert harness.transport_kwargs[0]["generation_params"]["response_format"][
        "json_schema"
    ]["schema"]["title"] == "planner-1"
    assert harness.transport_kwargs[2]["generation_params"]["response_format"][
        "json_schema"
    ]["schema"]["title"] == "planner-2"
    assert harness.transport_kwargs[1]["structured_response_schema"] == {
        "oneOf": [{"title": "worker-1"}]
    }
    assert harness.transport_kwargs[3]["structured_response_schema"] == {
        "oneOf": [{"title": "worker-2"}]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("planner", "worker"),
    [
        ("anthropic/wrong", _WORKER_MODEL),
        (_PLANNER_MODEL, "ollama_chat/wrong"),
        (_EqualSpoof(), _WORKER_MODEL),
        (_PLANNER_MODEL, _EqualSpoof()),
    ],
)
async def test_application_refuses_role_mismatch_before_construction(
    monkeypatch: pytest.MonkeyPatch,
    planner: object,
    worker: object,
) -> None:
    models = ModelSet(
        planner=planner,  # type: ignore[arg-type]
        worker=worker,  # type: ignore[arg-type]
        specialist="unused-specialist",
        guardian="unused-guardian",
        dspy="unused-dspy",
    )
    harness = _install_harness(monkeypatch, models=models)

    with pytest.raises(ValueError, match="profile_role_mismatch"):
        await application.run_worker_first_csharp_application(_INTENT)

    assert harness.events == ["profile:hybrid"]
    assert harness.transport_kwargs == []
    assert harness.dispatchers == []
    assert harness.integration_calls == []


@pytest.mark.asyncio
async def test_application_profile_failure_precedes_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _install_harness(monkeypatch)

    def fail_profile(profile: str) -> ModelSet:
        harness.events.append(f"profile:{profile}")
        raise RuntimeError("profile unavailable")

    monkeypatch.setattr(application, "get_models", fail_profile, raising=False)

    with pytest.raises(RuntimeError, match="profile unavailable"):
        await application.run_worker_first_csharp_application(_INTENT)

    assert harness.events == ["profile:hybrid"]
    assert harness.transport_kwargs == []
    assert harness.dispatchers == []


@pytest.mark.asyncio
async def test_create_only_executor_delegates_one_create_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _install_harness(monkeypatch)
    await application.run_worker_first_csharp_application(_INTENT)
    executor = harness.integration_calls[0]["tool_executor"]
    params = {"code": "A = 1.0;"}

    result = await executor("gh_create_csharp_script", params)

    assert result is harness.dispatchers[0].response
    assert harness.dispatchers[0].calls[0][0] == "gh_create_csharp_script"
    assert harness.dispatchers[0].calls[0][1] is params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    ["gh_update_script", "gh_create_script", _EqualSpoof(), None],
)
async def test_create_only_executor_refuses_other_names_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: object,
) -> None:
    harness = _install_harness(monkeypatch)
    await application.run_worker_first_csharp_application(_INTENT)
    executor = harness.integration_calls[0]["tool_executor"]

    with pytest.raises(ValueError, match="tool_not_allowed"):
        await executor(tool_name, {"code": "A = 1.0;"})

    assert harness.dispatchers[0].calls == []


@pytest.mark.asyncio
async def test_create_only_executor_refuses_repeat_before_second_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _install_harness(monkeypatch)
    await application.run_worker_first_csharp_application(_INTENT)
    executor = harness.integration_calls[0]["tool_executor"]

    await executor("gh_create_csharp_script", {"code": "A = 1.0;"})
    with pytest.raises(ValueError, match="create_already_dispatched"):
        await executor("gh_create_csharp_script", {"code": "A = 2.0;"})

    assert len(harness.dispatchers[0].calls) == 1
