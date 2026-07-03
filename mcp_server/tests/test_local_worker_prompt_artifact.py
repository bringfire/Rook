from __future__ import annotations

import ast
import copy
import inspect
import json
from collections.abc import Mapping

import pytest

import rook.agent.local_worker_prompt_artifact as prompt_module
from rook.agent.local_worker_prompt_artifact import (
    LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
    LOCAL_WORKER_PROMPT_TEXT_VERSION,
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerKnowledgePacket,
    WorkerNodeSummary,
    WorkerStepTraceSummary,
    WorkerSupplyTraceSummary,
    WorkerWorkflowSummary,
)
from rook.agent.local_worker_turn_request import (
    LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    render_local_worker_turn_request_payload,
)


def _context() -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="repair_component",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="fingerprint-123",
            compiler_id="rook.workflow_contract.compiler:v1",
            provider_id="rook.catalog_current_step_provider:v1",
            selected_template_id="gh_repair_component:v1",
            max_steps=6,
        ),
        current_graph=WorkerGraphSummary(
            node_count=3,
            node_ids=("create_script", "done", "repair_same_component"),
            ready_node_ids=("repair_same_component",),
            terminal_node_ids=("done",),
            status_counts={"pending": 1, "ready": 1, "terminal": 1},
        ),
        current_node=WorkerNodeSummary(
            node_id="repair_same_component",
            intent="repair existing C# script component",
            role="repair",
            status="ready",
            execution_ref="gh_update_script:v1",
            is_terminal=False,
            has_execution_params=True,
            memory_keys=("component_guid", "repair_anchor"),
        ),
        history=WorkerHistorySummary(
            current_step_count=2,
            supply_count=2,
            last_accepted_node_id="verify_create",
            last_execution_kind="verifier",
            last_stop_reason="needs_repair",
            recent_steps=(
                WorkerStepTraceSummary(
                    accepted_node_id="create_script",
                    execution_kind="producer",
                    ran=True,
                    failure=None,
                ),
                WorkerStepTraceSummary(
                    accepted_node_id="verify_create",
                    execution_kind="verifier",
                    ran=True,
                    failure="needs_repair",
                ),
            ),
            recent_supplies=(
                WorkerSupplyTraceSummary(
                    decision="SUPPLY",
                    reason=None,
                    selected_node_id="create_script",
                    has_envelope=True,
                ),
                WorkerSupplyTraceSummary(
                    decision="SUPPLY",
                    reason="needs_repair",
                    selected_node_id="repair_same_component",
                    has_envelope=True,
                ),
            ),
        ),
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script body mode",
                content={"source": "test fixture", "trust": "high"},
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={
                    "type": "object",
                    "required": ("code", "mode"),
                },
            ),
        ),
    )


def _request_payload() -> dict:
    payload = render_local_worker_turn_request_payload(_context())
    assert isinstance(payload, Mapping)
    return copy.deepcopy(dict(payload))


def test_schema_constants() -> None:
    assert LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA == "rook.local_worker_prompt_artifact:v1"
    assert LOCAL_WORKER_PROMPT_TEXT_VERSION == "lm5m.prompt_text:v2"


def test_module_all_is_exact() -> None:
    assert prompt_module.__all__ == (
        "LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA",
        "LOCAL_WORKER_PROMPT_TEXT_VERSION",
        "render_local_worker_prompt_artifact",
    )


def test_rejects_non_mapping_payload() -> None:
    with pytest.raises(TypeError):
        render_local_worker_prompt_artifact("not a mapping")  # type: ignore[arg-type]


def test_rejects_wrong_schema_tag() -> None:
    payload = _request_payload()
    payload["schema"] = "rook.other:v1"
    with pytest.raises(ValueError):
        render_local_worker_prompt_artifact(payload)


def test_rejects_non_string_schema_tag() -> None:
    payload = _request_payload()
    payload["schema"] = 7
    with pytest.raises(TypeError):
        render_local_worker_prompt_artifact(payload)


def test_rejects_missing_and_extra_top_level_keys() -> None:
    missing = _request_payload()
    del missing["response_contract"]
    with pytest.raises(ValueError):
        render_local_worker_prompt_artifact(missing)
    extra = _request_payload()
    extra["prompt"] = "surprise"
    with pytest.raises(ValueError):
        render_local_worker_prompt_artifact(extra)


def test_rejects_non_string_response_schema() -> None:
    payload = _request_payload()
    payload["response_schema"] = None
    with pytest.raises(ValueError):
        render_local_worker_prompt_artifact(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.__setitem__("kinds", []),
        lambda c: c.__setitem__("kinds", "action_request"),
        lambda c: c.__setitem__("kinds", ["action_request", 7]),
        lambda c: c.pop("field_sets"),
        lambda c: c.__setitem__("field_sets", []),
        lambda c: c["field_sets"].pop("refusal"),
        lambda c: c["field_sets"].__setitem__("refusal", []),
        lambda c: c["field_sets"].__setitem__("refusal", ["kind", 3]),
        lambda c: c.__setitem__("required_nullable_fields", "rationale"),
        lambda c: c["required_nullable_fields"].__setitem__("bogus_kind", ["x"]),
        lambda c: c["required_nullable_fields"].__setitem__("observation", []),
        lambda c: c.__setitem__("refusal_categories", []),
        lambda c: c.__setitem__("refusal_categories", ["unsafe", ""]),
        lambda c: c.__setitem__("surprise", ["x"]),
    ],
)
def test_mutated_response_contract_fails_closed(mutate) -> None:
    payload = _request_payload()
    mutate(payload["response_contract"])
    with pytest.raises((TypeError, ValueError)):
        render_local_worker_prompt_artifact(payload)


def test_artifact_shape_is_exact() -> None:
    artifact = render_local_worker_prompt_artifact(_request_payload())
    assert set(artifact.keys()) == {"schema", "prompt_text_version", "messages"}
    assert artifact["schema"] == LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA
    assert artifact["prompt_text_version"] == LOCAL_WORKER_PROMPT_TEXT_VERSION
    messages = artifact["messages"]
    assert isinstance(messages, list) and len(messages) == 2
    assert set(messages[0].keys()) == {"role", "content"}
    assert set(messages[1].keys()) == {"role", "content"}
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_render_is_deterministic_and_key_order_independent() -> None:
    first = render_local_worker_prompt_artifact(_request_payload())
    second = render_local_worker_prompt_artifact(_request_payload())
    assert first == second
    reordered = _request_payload()
    reordered = {key: reordered[key] for key in sorted(reordered, reverse=True)}
    third = render_local_worker_prompt_artifact(reordered)
    assert third == first


def test_user_message_is_canonical_json_of_envelope() -> None:
    payload = _request_payload()
    artifact = render_local_worker_prompt_artifact(payload)
    assert json.loads(artifact["messages"][1]["content"]) == payload


def test_system_text_renders_contract_mechanically() -> None:
    payload = _request_payload()
    system_text = render_local_worker_prompt_artifact(payload)["messages"][0][
        "content"
    ]
    contract = payload["response_contract"]
    for kind in contract["kinds"]:
        assert kind in system_text
        for field in contract["field_sets"][kind]:
            assert field in system_text
    for category in contract["refusal_categories"]:
        assert category in system_text
    assert payload["response_schema"] in system_text


def test_contract_mutation_changes_system_text() -> None:
    payload = _request_payload()
    baseline = render_local_worker_prompt_artifact(_request_payload())
    payload["response_contract"]["refusal_categories"] = [
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
        "novel_category",
    ]
    changed = render_local_worker_prompt_artifact(payload)
    assert "novel_category" in changed["messages"][0]["content"]
    assert changed["messages"][0]["content"] != baseline["messages"][0]["content"]


def test_instruction_text_explains_generic_action_input_authoring_role() -> None:
    instruction = prompt_module._INSTRUCTION_TEXT
    assert "input_schema describes the shape" in instruction
    assert "action input object" in instruction
    assert "visible context" in instruction
    assert "not a list of hidden values" in instruction
    assert "If visible context is sufficient" in instruction
    assert "clarification or refusal" in instruction
    assert "always request" not in instruction.lower()
    assert "always author" not in instruction.lower()


def test_instruction_text_requires_raw_json_without_fences_or_commentary() -> None:
    instruction = prompt_module._INSTRUCTION_TEXT
    assert "Return exactly one JSON object" in instruction
    assert "Do not use markdown fences" in instruction
    assert "backticks" in instruction
    assert "language labels" in instruction
    assert "explanatory text" in instruction
    assert "before or after the JSON object" in instruction


def test_instruction_constant_has_no_hand_listed_contract_or_scenario_literals() -> None:
    payload = _request_payload()
    contract = payload["response_contract"]
    instruction = prompt_module._INSTRUCTION_TEXT

    assert "clarification" in instruction
    assert "refusal" in instruction

    banned_response_literals = {
        "action_request",
        "clarification_request",
        "observation",
        "action_id",
        "rationale",
        "question",
        "category",
        "message",
        "data",
    }
    for literal in banned_response_literals:
        assert literal not in instruction

    for category in contract["refusal_categories"]:
        assert category not in instruction

    banned_scenario_literals = {
        "draft_repair_params",
        "code",
        "mode",
        "component_guid",
        "repair_same_component",
        "RunScript",
    }
    for literal in banned_scenario_literals:
        assert literal not in instruction


def test_module_never_references_loads_or_banned_imports() -> None:
    source = inspect.getsource(prompt_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    attributes: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    banned_modules = {
        "litellm", "openai", "requests", "httpx", "aiohttp", "socket",
        "urllib", "pathlib", "yaml",
    }
    banned_symbols = {
        "model_profiles", "base_agent", "tool_dispatcher", "chat",
        "capability_record", "capability_inventory", "plan_graph_live",
        "local_worker_turn_response", "local_worker_turn_harness",
        "local_worker_turn_disposition", "local_worker_scenario_evaluation",
    }
    assert not (imported & banned_modules)
    assert not (imported & banned_symbols)
    assert "loads" not in attributes
    assert "open" not in calls
