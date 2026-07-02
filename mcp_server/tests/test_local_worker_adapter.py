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
    TransportError,
)
from rook.agent.local_worker_prompt_artifact import (
    LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
    LOCAL_WORKER_PROMPT_TEXT_VERSION,
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
