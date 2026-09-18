"""Grasshopper document-scope classification for public MCP dispatch."""

from __future__ import annotations

import copy
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator, Mapping

EXPECTED_GH_DOCUMENT_ID_ARGUMENT = "expectedGhDocumentId"
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
        "gh_add_pattern",
        "gh_categories",
        "gh_component_search",
        "gh_consolidate",
        "gh_constraints",
        "gh_end_exploration",
        "gh_knowledge_query",
        "gh_knowledge_reload",
        "gh_library",
        "gh_migration_status",
        "gh_pattern_links",
        "gh_pattern_stats",
        "gh_query_observations",
        "gh_query_patterns",
        "gh_record_investigation",
        "gh_record_learning",
        "gh_record_pattern_use",
        "gh_reflect",
        "gh_save_pattern",
        "gh_save_recipe",
        "gh_session_current",
        "gh_session_end",
        "gh_session_history",
        "gh_session_note",
        "gh_start_exploration",
        "gh_structure_query",
        "gh_validate_latency",
        "gh_validate_regression",
        "gh_validate_scenarios",
    }
)

_GH_OBSERVATION_TOOLS = frozenset(
    {
        "gh_batch_component_info",
        "gh_canvas_image",
        "gh_errors",
        "gh_extract_recipe",
        "gh_get_reference",
        "gh_inspect_output",
        "gh_learn_canvas",
        "gh_selection",
        "gh_snapshot",
        "gh_solve_readiness",
        "gh_status",
        "gh_upgrade_recipe",
        "gh_wait_for_solve_readiness",
    }
)

_GH_MUTATION_TOOLS = frozenset(
    {
        "chirp_create",
        "gh_align",
        "gh_bake_output",
        "gh_canvas_cleanup",
        "gh_canvas_focus",
        "gh_canvas_zoom",
        "gh_clear",
        "gh_clear_reference",
        "gh_cluster",
        "gh_connect",
        "gh_create_csharp_script",
        "gh_create_python_script",
        "gh_create_script",
        "gh_distribute",
        "gh_edit",
        "gh_explore_component",
        "gh_explore_deep",
        "gh_investigate",
        "gh_move",
        "gh_preview",
        "gh_set_reference",
        "gh_set_script",
        "gh_set_script_pins",
        "gh_set_value",
        "gh_straighten_wires",
        "gh_undo",
        "gh_update_script",
    }
)

_GH_TRANSITION_TOOLS = frozenset(
    {
        "gh_document_open",
        "gh_document_new",
        "gh_learn_directory",
    }
)

_GH_TOOL_CLASSIFICATIONS = {
    **{
        name: GhToolClassification.DOCUMENT_INDEPENDENT
        for name in _DOCUMENT_INDEPENDENT_GH_TOOLS
    },
    **{name: GhToolClassification.OBSERVATION for name in _GH_OBSERVATION_TOOLS},
    **{name: GhToolClassification.MUTATION for name in _GH_MUTATION_TOOLS},
    **{name: GhToolClassification.TRANSITION for name in _GH_TRANSITION_TOOLS},
}


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
_CURRENT_GH_CUSTODY_ERROR: ContextVar[str | None] = ContextVar(
    "_CURRENT_GH_CUSTODY_ERROR", default=None
)


def classify_gh_tool(name: str) -> GhToolClassification | None:
    """Classify one public Grasshopper tool, or return ``None`` for other tools."""
    return _GH_TOOL_CLASSIFICATIONS.get(name)


def augment_gh_input_schema(
    name: str,
    schema: Mapping[str, Any],
    *,
    panel_locked: bool = False,
) -> dict[str, Any]:
    """Project the reserved concurrency field into guarded mutation schemas."""
    projected = copy.deepcopy(dict(schema))
    if (
        not panel_locked
        or classify_gh_tool(name) is not GhToolClassification.MUTATION
    ):
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
    name: str,
    arguments: Mapping[str, Any],
    *,
    panel_locked: bool = False,
) -> GhDispatchContext | None:
    """Validate public GH custody arguments without changing the caller mapping."""
    if not panel_locked:
        return None
    classification = classify_gh_tool(name)
    if classification is None:
        return None

    forbidden = sorted(
        key
        for key in arguments
        if key in {
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
    name: str,
    arguments: Mapping[str, Any],
    *,
    panel_locked: bool = False,
) -> tuple[dict[str, Any], GhDispatchContext | None]:
    """Separate the reserved public field from ordinary tool arguments."""
    prepared = dict(arguments)
    context = validate_public_gh_dispatch(
        name,
        prepared,
        panel_locked=panel_locked,
    )
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
    error_token = _CURRENT_GH_CUSTODY_ERROR.set(None)
    try:
        yield
    finally:
        _CURRENT_GH_CUSTODY_ERROR.reset(error_token)
        _CURRENT_GH_DOCUMENT_ID.reset(document_token)
        _CURRENT_GH_DISPATCH.reset(token)


def _gh_custody_failure(error: str) -> dict[str, Any]:
    messages = {
        "gh_target_changed": "The active Grasshopper document changed before dispatch.",
        "gh_target_unavailable": (
            "The Grasshopper operation did not return an authenticated "
            "document identity."
        ),
    }
    return {
        "success": False,
        "data": {"error": error, "message": messages[error]},
    }


def observe_gh_document_id(result: Mapping[str, Any]) -> dict[str, Any]:
    """Latch and reconcile managed document identity for this dispatch scope."""
    projected = dict(result)
    context = current_gh_dispatch_context()
    if context is None:
        return projected

    if result.get("success") is not True:
        data = result.get("data")
        error = data.get("error") if isinstance(data, Mapping) else None
        if (
            context.classification is not GhToolClassification.TRANSITION
            and error in {"gh_target_changed", "gh_target_unavailable"}
        ):
            _CURRENT_GH_CUSTODY_ERROR.set(error)
        return projected
    if context.classification is GhToolClassification.DOCUMENT_INDEPENDENT:
        return projected

    data = result.get("data")
    if not isinstance(data, Mapping):
        _CURRENT_GH_CUSTODY_ERROR.set("gh_target_unavailable")
        return _gh_custody_failure("gh_target_unavailable")
    raw = data.get("ghDocumentId")
    if not isinstance(raw, str):
        _CURRENT_GH_CUSTODY_ERROR.set("gh_target_unavailable")
        return _gh_custody_failure("gh_target_unavailable")
    try:
        parsed = uuid.UUID(raw)
    except ValueError:
        _CURRENT_GH_CUSTODY_ERROR.set("gh_target_unavailable")
        return _gh_custody_failure("gh_target_unavailable")
    if parsed.int == 0 or raw != str(parsed):
        _CURRENT_GH_CUSTODY_ERROR.set("gh_target_unavailable")
        return _gh_custody_failure("gh_target_unavailable")

    observed = _CURRENT_GH_DOCUMENT_ID.get()
    expected = context.expected_gh_document_id
    if context.classification is GhToolClassification.OBSERVATION:
        expected = observed

    if expected is not None and raw != expected:
        _CURRENT_GH_CUSTODY_ERROR.set("gh_target_changed")
        return _gh_custody_failure("gh_target_changed")

    if context.classification is GhToolClassification.TRANSITION or observed is None:
        _CURRENT_GH_DOCUMENT_ID.set(raw)
    return projected


def clear_observed_gh_document_id() -> None:
    """Require a later managed call to establish a fresh document identity."""
    _CURRENT_GH_DOCUMENT_ID.set(None)


def project_current_gh_document_id(
    result: Mapping[str, Any], context: GhDispatchContext | None
) -> dict[str, Any]:
    """Project the final observed identity onto one document-scoped result."""
    projected = dict(result)
    if (
        context is None
        or context.classification is GhToolClassification.DOCUMENT_INDEPENDENT
    ):
        return projected
    custody_error = _CURRENT_GH_CUSTODY_ERROR.get()
    if custody_error is not None:
        return _gh_custody_failure(custody_error)
    if projected.get("success") is not True:
        return projected
    document_id = _CURRENT_GH_DOCUMENT_ID.get()
    data = projected.get("data")
    if document_id is None or not isinstance(data, Mapping):
        return {
            "success": False,
            "data": {
                "error": "gh_target_unavailable",
                "message": (
                    "The Grasshopper operation did not return an authenticated "
                    "document identity."
                ),
            },
        }
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
    expected = context.expected_gh_document_id
    if context.classification is GhToolClassification.OBSERVATION:
        expected = _CURRENT_GH_DOCUMENT_ID.get()
    if expected is not None:
        projected[INTERNAL_EXPECTED_GH_DOCUMENT_ID_FIELD] = expected
    return projected
