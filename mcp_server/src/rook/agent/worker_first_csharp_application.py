"""Application-owned composition root for Worker-first C# creation."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from rook.agent.local_worker_model_transport import (
    LiteLLMWorkerTransport,
    build_local_worker_response_schema,
)
from rook.agent.minimal_intent_worker_integration import (
    MinimalIntentWorkerInitialBodyIntegrationResult,
    MinimalPlannerDraftAdapter,
    build_minimal_planner_draft_response_schema,
    run_minimal_intent_worker_initial_body_integration,
)
from rook.agent.model_profiles import get_models
from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

__all__ = ("run_worker_first_csharp_application",)

_PROFILE = "hybrid"
_PLANNER_MODEL = "anthropic/claude-opus-4-6"
_WORKER_MODEL = "ollama_chat/qwen3-coder:30b-a3b-q8_0"
_TIMEOUT_S = 120.0
_MAX_OUTPUT_TOKENS = 1024
_MAX_RETRIES = 0
_CREATE_TOOL = "gh_create_csharp_script"


def _planner_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "minimal_planner_draft",
            "strict": True,
            "schema": build_minimal_planner_draft_response_schema(),
        },
    }


def _create_only_executor(
    dispatcher: ToolDispatcher,
) -> Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]:
    create_dispatched = False

    async def execute(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal create_dispatched
        if type(tool_name) is not str or tool_name != _CREATE_TOOL:
            raise ValueError("tool_not_allowed")
        if create_dispatched:
            raise ValueError("create_already_dispatched")
        create_dispatched = True
        return await dispatcher.dispatch(tool_name, params)

    return execute


async def run_worker_first_csharp_application(
    intent: str,
) -> MinimalIntentWorkerInitialBodyIntegrationResult:
    """Run the fixed Planner/Worker/create composition for one exact intent."""
    models = get_models(_PROFILE)
    if (
        type(models.planner) is not str
        or models.planner != _PLANNER_MODEL
        or type(models.worker) is not str
        or models.worker != _WORKER_MODEL
    ):
        raise ValueError("profile_role_mismatch")

    planner_transport = LiteLLMWorkerTransport(
        model=models.planner,
        profile_api_base=models.api_base,
        generation_params={
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "max_retries": _MAX_RETRIES,
            "response_format": _planner_response_format(),
        },
        structured_response_schema=None,
        timeout_s=_TIMEOUT_S,
    )
    worker_transport = LiteLLMWorkerTransport(
        model=models.worker,
        profile_api_base=models.api_base,
        generation_params={
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "max_retries": _MAX_RETRIES,
        },
        structured_response_schema=build_local_worker_response_schema(),
        timeout_s=_TIMEOUT_S,
    )
    dispatcher = ToolDispatcher(local_tools=build_local_tools())
    return await run_minimal_intent_worker_initial_body_integration(
        intent=intent,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=_create_only_executor(dispatcher),
    )
