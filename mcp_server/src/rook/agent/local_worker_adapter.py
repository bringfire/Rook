"""LM5J local-worker adapter contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from rook.agent.local_worker_prompt_artifact import (
    LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
    LOCAL_WORKER_PROMPT_TEXT_VERSION,
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnResponse,
    load_local_worker_turn_response_payload,
)

LOCAL_WORKER_ADAPTER_RECORD_SCHEMA = "rook.local_worker_adapter_record:v1"
RAW_OUTPUT_EXCERPT_LIMIT = 500

__all__ = (
    "LOCAL_WORKER_ADAPTER_RECORD_SCHEMA",
    "RAW_OUTPUT_EXCERPT_LIMIT",
    "LocalWorkerAdapterRecord",
    "LocalWorkerTransport",
    "TransportError",
    "run_local_worker_adapter",
)

AdapterStatus = Literal[
    "response_loaded",
    "response_payload_invalid",
    "raw_output_invalid",
    "transport_error",
]
_STATUSES = frozenset(
    {
        "response_loaded",
        "response_payload_invalid",
        "raw_output_invalid",
        "transport_error",
    }
)
_DETAIL_LIMIT = 120


class TransportError(Exception):
    """Declared transport failure raised by LocalWorkerTransport.send."""


class LocalWorkerTransport(Protocol):
    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        """Return raw model output text, or raise TransportError."""
        ...


@dataclass(frozen=True)
class LocalWorkerAdapterRecord:
    schema: str
    status: AdapterStatus
    prompt_schema: str
    prompt_text_version: str
    response: LocalWorkerTurnResponse | None
    failure_reason: str | None
    raw_output_excerpt: str | None

    def __post_init__(self) -> None:
        if self.schema != LOCAL_WORKER_ADAPTER_RECORD_SCHEMA:
            raise ValueError("record schema must be the LM5J record schema")
        if self.status not in _STATUSES:
            raise ValueError(f"unknown adapter status: {self.status!r}")
        if self.prompt_schema != LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA:
            raise ValueError("prompt_schema must be the LM5J prompt schema")
        if self.prompt_text_version != LOCAL_WORKER_PROMPT_TEXT_VERSION:
            raise ValueError(
                "prompt_text_version must be the LM5J prompt text version"
            )
        if self.status == "response_loaded":
            if not isinstance(self.response, LocalWorkerTurnResponse):
                raise ValueError(
                    "response_loaded records require a loaded response"
                )
            if self.failure_reason is not None:
                raise ValueError(
                    "response_loaded records require failure_reason None"
                )
            if self.raw_output_excerpt is not None:
                raise ValueError(
                    "response_loaded records require raw_output_excerpt None"
                )
            return
        if self.response is not None:
            raise ValueError("failure records require response None")
        if not isinstance(self.failure_reason, str):
            raise ValueError("failure records require a failure_reason string")
        _require_taxonomy_reason(self.status, self.failure_reason)
        if self.raw_output_excerpt is not None:
            if (
                not isinstance(self.raw_output_excerpt, str)
                or not self.raw_output_excerpt
                or len(self.raw_output_excerpt) > RAW_OUTPUT_EXCERPT_LIMIT
            ):
                raise ValueError(
                    "raw_output_excerpt must be a non-empty bounded string"
                )


_EXACT_REASON_TAILS = {
    "transport_error": frozenset({"declared"}),
    "raw_output_invalid": frozenset({"empty", "json_decode", "not_mapping"}),
    "response_payload_invalid": frozenset(),
}
_DETAIL_REASON_TAILS = {
    "transport_error": frozenset({"unexpected"}),
    "raw_output_invalid": frozenset({"not_text"}),
    "response_payload_invalid": frozenset(),
}


def _require_taxonomy_reason(status: str, reason: str) -> None:
    head = status + ":"
    if not reason.startswith(head):
        raise ValueError(
            "failure_reason must start with the record status prefix"
        )
    rest = reason[len(head):]
    if status == "response_payload_invalid":
        _require_safe_detail(rest)
        return
    if rest in _EXACT_REASON_TAILS[status]:
        return
    tail, sep, detail = rest.partition(":")
    if sep and tail in _DETAIL_REASON_TAILS[status]:
        _require_safe_detail(detail)
        return
    raise ValueError(f"failure_reason not in the LM5J taxonomy: {reason!r}")


def _require_safe_detail(detail: str) -> None:
    if not detail:
        raise ValueError("failure_reason detail must be non-empty")
    for ch in detail:
        if not (ch.isascii() and (ch.isalnum() or ch == "_")):
            raise ValueError(
                "failure_reason detail must be ASCII alnum/underscore"
            )
