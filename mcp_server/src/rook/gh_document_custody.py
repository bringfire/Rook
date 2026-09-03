"""Grasshopper document-scope classification for public MCP dispatch."""

from __future__ import annotations

import copy
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator, Mapping

from .mcp_tool_profiles import PUBLIC_READONLY_TOOL_NAMES


EXPECTED_GH_DOCUMENT_ID_ARGUMENT = "expectedGhDocumentId"
INTERNAL_GH_DISPATCH_ARGUMENT = "_rookInternalGhDispatch"
INTERNAL_GH_SCOPE_FIELD = "_rookGhDispatchScope"
INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD = "_rookExpectedGhDocumentId"

_EXPECTED_GH_DOCUMENT_ID_SCHEMA = {
    "type": "string",
    "description": (
        "Canonical Grasshopper DocumentID observed immediately before this mutation."
    ),
}


class GhToolClassification(str, Enum):
    DOCUMENT_INDEPENDENT = "document_independent"
    OBSERVATION = "observation"
    MUTATION = "mutation"
    TRANSITION = "transition"


_DOCUMENT_INDEPENDENT_GH_TOOLS = frozenset(
    {
        "gh_component_search",
        "gh_library",
        "gh_categories",
    }
)

_GH_TRANSITION_TOOLS = frozenset(
    {
        "gh_document_open",
        "gh_document_new",
        "gh_learn_directory",
    }
)


@dataclass(frozen=True)
class GhDispatchContext:
    classification: GhToolClassification
    expected_gh_document_id: str | None


class GhDocumentCustodyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_CURRENT_GH_DISPATCH: ContextVar[GhDispatchContext | None] = ContextVar(
    "_CURRENT_GH_DISPATCH", default=None
)
_CURRENT_GH_DOCUMENT_ID: ContextVar[str | None] = ContextVar(
    "_CURRENT_GH_DOCUMENT_ID", default=None
)


def classify_gh_tool(name: str) -> GhToolClassification | None:
    """Classify one public Grasshopper tool, or return ``None`` for other tools."""
    if not name.startswith("gh_"):
        return None
    if name in _DOCUMENT_INDEPENDENT_GH_TOOLS:
        return GhToolClassification.DOCUMENT_INDEPENDENT
    if name in _GH_TRANSITION_TOOLS:
        return GhToolClassification.TRANSITION
    if name in PUBLIC_READONLY_TOOL_NAMES:
        return GhToolClassification.OBSERVATION
    return GhToolClassification.MUTATION


def augment_gh_input_schema(name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project the reserved concurrency field into guarded mutation schemas."""
    projected = copy.deepcopy(dict(schema))
    if classify_gh_tool(name) is not GhToolClassification.MUTATION:
        return projected

    properties = dict(projected.get("properties") or {})
    properties[EXPECTED_GH_DOCUMENT_ID_ARGUMENT] = dict(
        _EXPECTED_GH_DOCUMENT_ID_SCHEMA
    )
    projected["properties"] = properties
    required = list(projected.get("required") or [])
    if EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in required:
        required.append(EXPECTED_GH_DOCUMENT_ID_ARGUMENT)
    projected["required"] = required
    return projected


def validate_public_gh_dispatch(
    name: str, arguments: Mapping[str, Any]
) -> GhDispatchContext | None:
    """Validate public GH custody arguments without changing the caller mapping."""
    classification = classify_gh_tool(name)
    if classification is None:
        return None

    forbidden = sorted(
        key
        for key in arguments
        if key in {
            INTERNAL_GH_DISPATCH_ARGUMENT,
            INTERNAL_GH_SCOPE_FIELD,
            INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD,
        }
    )
    if forbidden:
        raise GhDocumentCustodyError(
            "invalid_arguments",
            f"service-owned fields are not accepted: {', '.join(forbidden)}",
        )

    raw_expected = arguments.get(EXPECTED_GH_DOCUMENT_ID_ARGUMENT)
    if classification is not GhToolClassification.MUTATION:
        if EXPECTED_GH_DOCUMENT_ID_ARGUMENT in arguments:
            raise GhDocumentCustodyError(
                "invalid_arguments",
                f"{EXPECTED_GH_DOCUMENT_ID_ARGUMENT} is not accepted for {name}",
            )
        return GhDispatchContext(classification, None)

    if EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in arguments:
        raise GhDocumentCustodyError(
            "gh_target_required",
            f"{EXPECTED_GH_DOCUMENT_ID_ARGUMENT} is required for {name}",
        )
    if not isinstance(raw_expected, str):
        raise GhDocumentCustodyError(
            "invalid_arguments",
            f"{EXPECTED_GH_DOCUMENT_ID_ARGUMENT} must be a canonical GUID string",
        )
    try:
        parsed = uuid.UUID(raw_expected)
    except (AttributeError, ValueError):
        raise GhDocumentCustodyError(
            "invalid_arguments",
            f"{EXPECTED_GH_DOCUMENT_ID_ARGUMENT} must be a canonical GUID string",
        ) from None
    canonical = str(parsed)
    if parsed.int == 0 or raw_expected != canonical:
        raise GhDocumentCustodyError(
            "invalid_arguments",
            f"{EXPECTED_GH_DOCUMENT_ID_ARGUMENT} must use lowercase D format",
        )
    return GhDispatchContext(classification, canonical)


def prepare_public_gh_dispatch(
    name: str, arguments: Mapping[str, Any]
) -> tuple[dict[str, Any], GhDispatchContext | None]:
    """Separate the reserved public field from ordinary tool arguments."""
    prepared = dict(arguments)
    context = validate_public_gh_dispatch(name, prepared)
    if context is None:
        return prepared, None
    prepared.pop(EXPECTED_GH_DOCUMENT_ID_ARGUMENT, None)
    return prepared, context


def current_gh_dispatch_context() -> GhDispatchContext | None:
    return _CURRENT_GH_DISPATCH.get()


@contextmanager
def gh_dispatch_scope(context: GhDispatchContext | None) -> Iterator[None]:
    token = _CURRENT_GH_DISPATCH.set(context)
    document_token = _CURRENT_GH_DOCUMENT_ID.set(None)
    try:
        yield
    finally:
        _CURRENT_GH_DOCUMENT_ID.reset(document_token)
        _CURRENT_GH_DISPATCH.reset(token)


def observe_gh_document_id(result: Mapping[str, Any]) -> None:
    """Retain one authentic managed document identity for this dispatch scope."""
    if result.get("success") is not True:
        return
    data = result.get("data")
    if not isinstance(data, Mapping):
        return
    raw = data.get("ghDocumentId")
    if not isinstance(raw, str):
        return
    try:
        parsed = uuid.UUID(raw)
    except ValueError:
        return
    if parsed.int != 0 and raw == str(parsed):
        _CURRENT_GH_DOCUMENT_ID.set(raw)


def project_current_gh_document_id(
    result: Mapping[str, Any], context: GhDispatchContext | None
) -> dict[str, Any]:
    """Project the final observed identity onto one document-scoped result."""
    projected = dict(result)
    if (
        context is None
        or context.classification is GhToolClassification.DOCUMENT_INDEPENDENT
        or projected.get("success") is not True
    ):
        return projected
    document_id = _CURRENT_GH_DOCUMENT_ID.get()
    if document_id is None:
        return projected
    data = projected.get("data")
    if not isinstance(data, Mapping):
        return projected
    projected_data = dict(data)
    projected_data["ghDocumentId"] = document_id
    projected["data"] = projected_data
    return projected


def apply_gh_dispatch_to_http_data(
    endpoint: str, data: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Attach the current service-owned GH context to one GH bridge request."""
    context = current_gh_dispatch_context()
    if context is None or not endpoint.startswith("/gh/"):
        return dict(data) if data is not None else None

    projected = dict(data) if data is not None else {}
    projected[INTERNAL_GH_SCOPE_FIELD] = context.classification.value
    if context.expected_gh_document_id is not None:
        projected[INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD] = (
            context.expected_gh_document_id
        )
    return projected
