from __future__ import annotations

import ast
import copy
import inspect
import json
from collections.abc import Mapping

import pytest

import rook.agent.local_worker_adapter as adapter_module
from rook.agent.local_worker_adapter import (
    LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
    RAW_OUTPUT_EXCERPT_LIMIT,
    LocalWorkerAdapterRecord,
    LocalWorkerTransport,
    TransportError,
    run_local_worker_adapter,
)
from rook.agent.local_worker_prompt_artifact import (
    LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
    LOCAL_WORKER_PROMPT_TEXT_VERSION,
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
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
)


def _loaded_response() -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id="draft_repair_params",
            rationale="Draft repair parameters.",
            input={"code": "A = 42.0;", "mode": "body"},
        )
    )


def _record(**overrides) -> LocalWorkerAdapterRecord:
    values = {
        "schema": LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
        "status": "response_loaded",
        "prompt_schema": LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        "prompt_text_version": LOCAL_WORKER_PROMPT_TEXT_VERSION,
        "response": _loaded_response(),
        "failure_reason": None,
        "raw_output_excerpt": None,
    }
    values.update(overrides)
    return LocalWorkerAdapterRecord(**values)


def test_record_schema_constant() -> None:
    assert LOCAL_WORKER_ADAPTER_RECORD_SCHEMA == "rook.local_worker_adapter_record:v1"
    assert RAW_OUTPUT_EXCERPT_LIMIT == 500


def test_transport_error_is_exception_subclass() -> None:
    assert issubclass(TransportError, Exception)
    assert not issubclass(KeyboardInterrupt, TransportError)


def test_loaded_record_is_coherent() -> None:
    record = _record()
    assert record.status == "response_loaded"
    assert record.failure_reason is None
    assert record.raw_output_excerpt is None
    assert isinstance(record.response, LocalWorkerTurnResponse)


def test_loaded_record_rejects_failure_fields() -> None:
    with pytest.raises(ValueError):
        _record(failure_reason="transport_error:declared")
    with pytest.raises(ValueError):
        _record(raw_output_excerpt="{}")
    with pytest.raises(ValueError):
        _record(response=None)


def test_failure_record_requires_matching_reason_prefix() -> None:
    record = _record(
        status="transport_error",
        response=None,
        failure_reason="transport_error:declared",
    )
    assert record.failure_reason == "transport_error:declared"
    with pytest.raises(ValueError):
        _record(
            status="transport_error",
            response=None,
            failure_reason="raw_output_invalid:empty",
        )
    with pytest.raises(ValueError):
        _record(status="transport_error", response=None, failure_reason=None)
    with pytest.raises(ValueError):
        _record(
            status="raw_output_invalid",
            response=_loaded_response(),
            failure_reason="raw_output_invalid:empty",
        )


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("transport_error", "transport_error:declared"),
        ("transport_error", "transport_error:unexpected:RuntimeError"),
        ("raw_output_invalid", "raw_output_invalid:not_text:dict"),
        ("raw_output_invalid", "raw_output_invalid:empty"),
        ("raw_output_invalid", "raw_output_invalid:json_decode"),
        ("raw_output_invalid", "raw_output_invalid:not_mapping"),
        ("response_payload_invalid", "response_payload_invalid:unknown_kind"),
    ],
)
def test_every_taxonomy_reason_is_constructible(status, reason) -> None:
    record = _record(status=status, response=None, failure_reason=reason)
    assert record.failure_reason == reason


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("raw_output_invalid", "raw_output_invalid:made_up"),
        ("transport_error", "transport_error:whatever"),
        ("transport_error", "transport_error:unexpected:"),
        ("transport_error", "transport_error:unexpected:Run Time!"),
        ("raw_output_invalid", "raw_output_invalid:not_text:"),
        ("raw_output_invalid", "raw_output_invalid:empty:extra"),
        ("response_payload_invalid", "response_payload_invalid:"),
        ("response_payload_invalid", "response_payload_invalid:bad detail"),
        ("transport_error", "transport_error:"),
        ("transport_error", "transport_error:declared:extra"),
    ],
)
def test_off_taxonomy_reasons_are_rejected(status, reason) -> None:
    with pytest.raises(ValueError):
        _record(status=status, response=None, failure_reason=reason)


def test_record_rejects_unknown_status_and_wrong_constants() -> None:
    with pytest.raises(ValueError):
        _record(status="prompt_rendered", response=None,
                failure_reason="prompt_rendered:x")
    with pytest.raises(ValueError):
        _record(schema="rook.other:v1")
    with pytest.raises(ValueError):
        _record(prompt_schema="rook.other:v1")
    with pytest.raises(ValueError):
        _record(prompt_text_version="lm5j.prompt_text:v999")


def test_excerpt_bounds_enforced_on_record() -> None:
    ok = _record(
        status="raw_output_invalid",
        response=None,
        failure_reason="raw_output_invalid:empty",
        raw_output_excerpt="x" * RAW_OUTPUT_EXCERPT_LIMIT,
    )
    assert len(ok.raw_output_excerpt) == RAW_OUTPUT_EXCERPT_LIMIT
    with pytest.raises(ValueError):
        _record(
            status="raw_output_invalid",
            response=None,
            failure_reason="raw_output_invalid:empty",
            raw_output_excerpt="x" * (RAW_OUTPUT_EXCERPT_LIMIT + 1),
        )
    with pytest.raises(ValueError):
        _record(
            status="raw_output_invalid",
            response=None,
            failure_reason="raw_output_invalid:empty",
            raw_output_excerpt="",
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
    return copy.deepcopy(dict(payload))


class _StaticTransport:
    def __init__(self, raw_output) -> None:
        self.raw_output = raw_output
        self.sent_artifacts: list = []

    def send(self, prompt_artifact):
        self.sent_artifacts.append(prompt_artifact)
        return self.raw_output


class _RaisingTransport:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def send(self, prompt_artifact):
        raise self.exc


def _valid_response_payload() -> dict:
    return {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Draft repair parameters for the failed component.",
        "input": {"code": "A = 42.0;", "mode": "body"},
    }


def test_happy_path_loads_response() -> None:
    transport = _StaticTransport(json.dumps(_valid_response_payload()))
    record = run_local_worker_adapter(_request_payload(), transport)
    assert record.status == "response_loaded"
    assert record.failure_reason is None
    assert record.raw_output_excerpt is None
    assert record.response.payload.action_id == "draft_repair_params"
    sent = transport.sent_artifacts[0]
    assert sent["schema"] == LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA


def test_leading_trailing_whitespace_is_trimmed() -> None:
    raw = "\n  " + json.dumps(_valid_response_payload()) + "  \n"
    record = run_local_worker_adapter(_request_payload(), _StaticTransport(raw))
    assert record.status == "response_loaded"


def test_fenced_output_is_invalid_no_unwrapping() -> None:
    fenced = "```json\n" + json.dumps(_valid_response_payload()) + "\n```"
    record = run_local_worker_adapter(_request_payload(), _StaticTransport(fenced))
    assert record.status == "raw_output_invalid"
    assert record.failure_reason == "raw_output_invalid:json_decode"
    assert record.raw_output_excerpt.startswith("```json")


def test_prose_wrapped_json_is_invalid() -> None:
    raw = "Here is my answer: " + json.dumps(_valid_response_payload())
    record = run_local_worker_adapter(_request_payload(), _StaticTransport(raw))
    assert record.status == "raw_output_invalid"
    assert record.failure_reason == "raw_output_invalid:json_decode"


def test_empty_and_whitespace_output() -> None:
    for raw in ("", "   \n\t  "):
        record = run_local_worker_adapter(
            _request_payload(), _StaticTransport(raw)
        )
        assert record.status == "raw_output_invalid"
        assert record.failure_reason == "raw_output_invalid:empty"


def test_non_mapping_json_output() -> None:
    record = run_local_worker_adapter(
        _request_payload(), _StaticTransport(json.dumps([1, 2, 3]))
    )
    assert record.status == "raw_output_invalid"
    assert record.failure_reason == "raw_output_invalid:not_mapping"


def test_non_string_transport_return() -> None:
    record = run_local_worker_adapter(
        _request_payload(), _StaticTransport({"already": "parsed"})
    )
    assert record.status == "raw_output_invalid"
    assert record.failure_reason == "raw_output_invalid:not_text:dict"
    assert record.raw_output_excerpt is None


def test_lm5g_rejection_is_response_payload_invalid() -> None:
    bad = _valid_response_payload()
    bad["schema"] = "rook.other:v1"
    record = run_local_worker_adapter(
        _request_payload(), _StaticTransport(json.dumps(bad))
    )
    assert record.status == "response_payload_invalid"
    assert record.failure_reason.startswith(
        "response_payload_invalid:unsupported_local_worker_turn_response_schema"
    )
    unknown_kind = _valid_response_payload()
    unknown_kind["kind"] = "poetry"
    record = run_local_worker_adapter(
        _request_payload(), _StaticTransport(json.dumps(unknown_kind))
    )
    assert record.status == "response_payload_invalid"
    assert record.failure_reason.startswith(
        "response_payload_invalid:unknown_local_worker_response_kind"
    )


def test_declared_transport_error() -> None:
    record = run_local_worker_adapter(
        _request_payload(), _RaisingTransport(TransportError("provider down"))
    )
    assert record.status == "transport_error"
    assert record.failure_reason == "transport_error:declared"
    assert record.raw_output_excerpt is None


def test_unexpected_exception_is_classified() -> None:
    record = run_local_worker_adapter(
        _request_payload(), _RaisingTransport(RuntimeError("boom"))
    )
    assert record.status == "transport_error"
    assert record.failure_reason == "transport_error:unexpected:RuntimeError"


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(3)])
def test_base_exceptions_propagate(exc) -> None:
    with pytest.raises(type(exc)):
        run_local_worker_adapter(_request_payload(), _RaisingTransport(exc))


def test_excerpt_is_bounded_and_control_chars_replaced() -> None:
    raw = "x" * (RAW_OUTPUT_EXCERPT_LIMIT + 100) + "\x00\x01"
    record = run_local_worker_adapter(_request_payload(), _StaticTransport(raw))
    assert record.status == "raw_output_invalid"
    assert len(record.raw_output_excerpt) == RAW_OUTPUT_EXCERPT_LIMIT
    control = "\x00\x01\x02 tail"
    record = run_local_worker_adapter(
        _request_payload(), _StaticTransport(control)
    )
    assert "\x00" not in record.raw_output_excerpt
    assert record.raw_output_excerpt == "___ tail"


def test_full_raw_output_never_on_record() -> None:
    raw = json.dumps(_valid_response_payload()) + " trailing garbage " + "y" * 600
    record = run_local_worker_adapter(_request_payload(), _StaticTransport(raw))
    assert record.status == "raw_output_invalid"
    assert len(record.raw_output_excerpt) <= RAW_OUTPUT_EXCERPT_LIMIT
    assert record.raw_output_excerpt != raw


def test_invalid_envelope_raises_no_record() -> None:
    with pytest.raises((TypeError, ValueError)):
        run_local_worker_adapter({"schema": "wrong"}, _StaticTransport("{}"))


def test_non_callable_transport_raises() -> None:
    class _NoSend:
        pass

    with pytest.raises(TypeError):
        run_local_worker_adapter(_request_payload(), _NoSend())


def test_mutated_contract_raises_before_transport() -> None:
    payload = _request_payload()
    payload["response_contract"]["kinds"] = []
    transport = _StaticTransport("{}")
    with pytest.raises((TypeError, ValueError)):
        run_local_worker_adapter(payload, transport)
    assert transport.sent_artifacts == []


def test_adapter_module_all_and_ast_guard() -> None:
    assert adapter_module.__all__ == (
        "LOCAL_WORKER_ADAPTER_RECORD_SCHEMA",
        "RAW_OUTPUT_EXCERPT_LIMIT",
        "LocalWorkerAdapterRecord",
        "LocalWorkerTransport",
        "TransportError",
        "run_local_worker_adapter",
    )
    source = inspect.getsource(adapter_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    attributes: set[str] = set()
    calls: set[str] = set()
    handlers: list[ast.ExceptHandler] = []
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
        elif isinstance(node, ast.ExceptHandler):
            handlers.append(node)
    banned_modules = {
        "litellm", "openai", "requests", "httpx", "aiohttp", "socket",
        "urllib", "pathlib", "yaml",
    }
    banned_symbols = {
        "model_profiles", "base_agent", "tool_dispatcher", "chat",
        "capability_record", "capability_inventory", "plan_graph_live",
        "local_worker_turn_harness", "local_worker_turn_disposition",
        "local_worker_scenario_evaluation",
    }
    assert not (imported & banned_modules)
    assert not (imported & banned_symbols)
    assert "dumps" not in attributes
    assert "open" not in calls
    handler_names = {
        name.id
        for handler in handlers
        if handler.type is not None
        for name in ast.walk(handler.type)
        if isinstance(name, ast.Name)
    }
    assert "BaseException" not in handler_names
