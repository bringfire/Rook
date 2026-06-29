# LM5B Local Worker Response Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the deterministic worker response contract and compact admissibility record for one response against one `LocalWorkerTurnContext`.

**Architecture:** Add one output-side agent module that defines closed response dataclasses, validates/freeze response payloads at construction, and returns a compact attempt record from a context-aware validator. The module consumes only LM5A's public `LocalWorkerTurnContext` surface and does not call models, compile/load workflow artifacts, run streams, execute tools, mutate graphs, or parse raw worker output.

**Tech Stack:** Python dataclasses, `Literal` type aliases, `MappingProxyType`, pytest, AST import/call boundary checks.

---

## File Structure

Create:

- `mcp_server/src/rook/agent/local_worker_turn_response.py`
  - Owns LM5B public response dataclasses.
  - Owns local JSON-shaped freeze helper.
  - Owns `validate_local_worker_turn_response(...)`.
  - Imports only `LocalWorkerTurnContext` from LM5A production code.

- `mcp_server/tests/test_local_worker_turn_response.py`
  - Unit tests for constructor validation/freezing, closed union enforcement, attempt records, validator taxonomy, no-actions behavior, defensive invalid records, and import boundary.
  - One small offline integration proof with real LM5A `LocalWorkerTurnContext`.

Do not modify:

- `mcp_server/src/rook/agent/local_worker_turn_context.py`
- package `__init__` files
- runtime/stream/provider/compiler modules
- RookChat, server, dispatcher, native, managed, or knowledge files

---

## Task 1: Add Failing LM5B Tests

**Files:**

- Create: `mcp_server/tests/test_local_worker_turn_response.py`

- [ ] **Step 1: Create the test file**

```python
from __future__ import annotations

import ast
import copy
import math
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from rook.agent.local_worker_turn_context import (
    WorkerAllowedAction,
    build_local_worker_turn_context,
)
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    ExpectedNodeRef,
    InitialNodeParams,
    ProducerStepSpec,
    RookWorkflowContract,
    VerifierStepSpec,
    WorkflowNodeRule,
    WorkflowTemplateRef,
    compile_workflow_contract,
)

from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
    validate_local_worker_turn_response,
)


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5b_worker_response",
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify_repair_verify",
                "language": "csharp",
            },
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                node_id="create_script",
                execution_params={
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM5BLocalWorkerResponse",
                    "x": 350,
                    "y": 1160,
                },
            ),
        ),
        expected_refs=(
            ExpectedNodeRef(
                node_id="create_script",
                execution_ref="gh_create_csharp_script:v1",
            ),
            ExpectedNodeRef(
                node_id="repair_same_component",
                execution_ref="gh_update_script:v1",
            ),
        ),
        rules=(
            WorkflowNodeRule(
                node_id="create_script",
                steps_by_seen_count=(ProducerStepSpec(node_id="create_script"),),
            ),
            WorkflowNodeRule(
                node_id="verify_create",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_create",
                        source_node_id="create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                node_id="repair_same_component",
                steps_by_seen_count=(
                    BindStepSpec(
                        node_id="repair_same_component",
                        base_params={
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        bindings={
                            "guid": ("repair_anchor", "component_guid"),
                        },
                    ),
                    ProducerStepSpec(node_id="repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                node_id="verify_repair",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_repair",
                        source_node_id="repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=("done",),
        max_steps=6,
        metadata={"trace": {"slice": "LM5B"}},
    )


def _context(*, include_actions: bool = True):
    scaffold = compile_workflow_contract(_repair_contract())
    actions = (
        (
            WorkerAllowedAction(
                action_id="draft_bind_params",
                kind="draft",
                description="Draft replacement C# body parameters.",
                input_schema={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            ),
        )
        if include_actions
        else ()
    )
    return build_local_worker_turn_context(
        scaffold,
        copy.deepcopy(scaffold.graph),
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(),
        allowed_actions=actions,
    )


def _action_request(action_id: str = "draft_bind_params") -> WorkerActionRequest:
    return WorkerActionRequest(
        action_id=action_id,
        rationale="Need to propose repair parameters.",
        input={"code": "A = 42.0;"},
    )


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_response as module

    assert set(module.__all__) == {
        "LocalWorkerTurnResponse",
        "LocalWorkerTurnAttemptRecord",
        "WorkerActionRequest",
        "WorkerClarificationRequest",
        "WorkerRefusal",
        "WorkerObservation",
        "WorkerResponseKind",
        "WorkerRefusalCategory",
        "WorkerResponseValidationFailure",
        "validate_local_worker_turn_response",
    }
    assert "WorkerResponsePayload" not in module.__all__


def test_public_dataclasses_are_frozen() -> None:
    for cls in (
        WorkerActionRequest,
        WorkerClarificationRequest,
        WorkerRefusal,
        WorkerObservation,
        LocalWorkerTurnResponse,
        LocalWorkerTurnAttemptRecord,
    ):
        assert is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_action_request_freezes_and_detaches_input() -> None:
    payload = {"nested": {"tags": ["before"]}}
    request = WorkerActionRequest(
        action_id="draft_bind_params",
        rationale="Need repair params.",
        input=payload,
    )

    payload["nested"]["tags"].append("after")

    assert request.input["nested"]["tags"] == ("before",)
    with pytest.raises(TypeError):
        request.input["nested"]["late"] = True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action_id": "", "rationale": "why", "input": {}},
        {"action_id": "draft", "rationale": "", "input": {}},
    ],
)
def test_action_request_empty_values_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkerActionRequest(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action_id": 1, "rationale": "why", "input": {}},
        {"action_id": "draft", "rationale": 1, "input": {}},
        {"action_id": "draft", "rationale": "why", "input": []},
        {"action_id": "draft", "rationale": "why", "input": {1: "bad"}},
        {"action_id": "draft", "rationale": "why", "input": {"bad": object()}},
        {"action_id": "draft", "rationale": "why", "input": {"bad": math.inf}},
        {"action_id": "draft", "rationale": "why", "input": {"bad": lambda: None}},
    ],
)
def test_action_request_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerActionRequest(**kwargs)  # type: ignore[arg-type]


def test_clarification_request_accepts_question_and_optional_rationale() -> None:
    request = WorkerClarificationRequest(
        question="Which component should be repaired?",
        rationale="The context names two candidates.",
    )

    assert request.question == "Which component should be repaired?"
    assert request.rationale == "The context names two candidates."


def test_clarification_request_empty_question_rejected() -> None:
    with pytest.raises(ValueError):
        WorkerClarificationRequest(question="")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"question": 1, "rationale": None},
        {"question": "Question?", "rationale": 1},
        {"question": None, "rationale": None},
    ],
)
def test_clarification_request_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerClarificationRequest(**kwargs)  # type: ignore[arg-type]


def test_refusal_accepts_closed_category() -> None:
    refusal = WorkerRefusal(
        category="insufficient_context",
        reason="No action can be selected from the provided context.",
    )

    assert refusal.category == "insufficient_context"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": "unknown", "reason": "No."},
        {"category": "unsafe", "reason": ""},
    ],
)
def test_refusal_bad_values_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkerRefusal(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": 1, "reason": "No."},
        {"category": "unsafe", "reason": 1},
    ],
)
def test_refusal_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerRefusal(**kwargs)  # type: ignore[arg-type]


def test_observation_freezes_and_detaches_data() -> None:
    data = {"nested": {"warnings": ["one"]}}
    observation = WorkerObservation(
        message="The graph has a repair node.",
        data=data,
    )

    data["nested"]["warnings"].append("two")

    assert observation.data is not None
    assert observation.data["nested"]["warnings"] == ("one",)
    with pytest.raises(TypeError):
        observation.data["nested"]["late"] = True


def test_observation_allows_missing_data() -> None:
    observation = WorkerObservation(message="Nothing to add.")

    assert observation.data is None


def test_observation_empty_message_rejected() -> None:
    with pytest.raises(ValueError):
        WorkerObservation(message="")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"message": 1, "data": None},
        {"message": "note", "data": []},
        {"message": "note", "data": {1: "bad"}},
        {"message": "note", "data": {"bad": object()}},
        {"message": "note", "data": {"bad": math.inf}},
    ],
)
def test_observation_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerObservation(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        WorkerActionRequest("draft_bind_params", "Need repair params.", {}),
        WorkerClarificationRequest("Which component?"),
        WorkerRefusal("out_of_scope", "Cannot answer with provided actions."),
        WorkerObservation("Observed a repair node."),
    ],
)
def test_response_accepts_exactly_one_closed_payload(payload: object) -> None:
    response = LocalWorkerTurnResponse(payload=payload)

    assert response.payload is payload


@pytest.mark.parametrize("payload", [None, {}, [], (WorkerObservation("one"),), object()])
def test_response_rejects_non_closed_payloads(payload: object) -> None:
    with pytest.raises(TypeError):
        LocalWorkerTurnResponse(payload=payload)  # type: ignore[arg-type]


def test_validator_wrong_context_type_raises_type_error() -> None:
    response = LocalWorkerTurnResponse(WorkerObservation("note"))

    with pytest.raises(TypeError):
        validate_local_worker_turn_response(object(), response)  # type: ignore[arg-type]


def test_validator_wrong_response_type_raises_type_error() -> None:
    context = _context()

    with pytest.raises(TypeError):
        validate_local_worker_turn_response(context, object())  # type: ignore[arg-type]


def test_valid_action_request_returns_compact_attempt_record() -> None:
    context = _context()
    response = LocalWorkerTurnResponse(payload=_action_request())

    record = validate_local_worker_turn_response(context, response)

    assert record == LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="action_request",
        failure=None,
        reason="valid_action_request",
        action_id="draft_bind_params",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def test_unknown_action_id_returns_invalid_attempt_record() -> None:
    context = _context()
    response = LocalWorkerTurnResponse(payload=_action_request("invented_action"))

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind == "action_request"
    assert record.failure == "unknown_action_id"
    assert record.reason == "unknown_action_id:invented_action"
    assert record.action_id == "invented_action"
    assert record.context_workflow_id == context.workflow.workflow_id
    assert record.context_contract_fingerprint == context.workflow.contract_fingerprint


def test_context_with_no_actions_still_accepts_non_action_responses() -> None:
    context = _context(include_actions=False)

    clarification = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(WorkerClarificationRequest("What should I do?")),
    )
    refusal = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(WorkerRefusal("unsupported_action", "No actions.")),
    )
    observation = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(WorkerObservation("No actions are available.")),
    )
    action = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(_action_request()),
    )

    assert clarification.valid is True
    assert refusal.valid is True
    assert observation.valid is True
    assert action.valid is False
    assert action.failure == "unknown_action_id"
    assert action.reason == "unknown_action_id:draft_bind_params"


@pytest.mark.parametrize(
    ("payload", "kind", "reason"),
    [
        (
            WorkerClarificationRequest("What should I do?"),
            "clarification_request",
            "valid_clarification_request",
        ),
        (
            WorkerRefusal("out_of_scope", "Cannot respond."),
            "refusal",
            "valid_refusal",
        ),
        (
            WorkerObservation("Observed context."),
            "observation",
            "valid_observation",
        ),
    ],
)
def test_valid_non_action_responses_use_stable_reasons(
    payload: object,
    kind: str,
    reason: str,
) -> None:
    context = _context(include_actions=False)
    response = LocalWorkerTurnResponse(payload=payload)

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is True
    assert record.response_kind == kind
    assert record.failure is None
    assert record.reason == reason
    assert record.action_id is None


def test_validator_defensively_records_payload_invalid_after_bypass() -> None:
    context = _context()
    response = LocalWorkerTurnResponse(WorkerObservation("Observed context."))
    object.__setattr__(response, "payload", object())

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind is None
    assert record.failure == "payload_invalid"
    assert record.reason == "payload_invalid:closed_payload_required"
    assert record.action_id is None


def test_validator_defensively_records_action_input_invalid_after_bypass() -> None:
    context = _context()
    action = _action_request()
    object.__setattr__(action, "input", [])
    response = LocalWorkerTurnResponse(action)

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind == "action_request"
    assert record.failure == "action_input_invalid"
    assert record.reason == "action_input_invalid:input_not_mapping"
    assert record.action_id == "draft_bind_params"


def test_attempt_record_has_only_compact_fields() -> None:
    assert tuple(field.name for field in fields(LocalWorkerTurnAttemptRecord)) == (
        "valid",
        "response_kind",
        "failure",
        "reason",
        "action_id",
        "context_workflow_id",
        "context_contract_fingerprint",
    )


def test_local_worker_response_module_boundary_is_response_contract_only() -> None:
    import rook.agent.local_worker_turn_response as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    referenced_names: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    allowed_import_modules = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "math",
        "types",
        "typing",
        "rook.agent.local_worker_turn_context",
    }
    assert imported_modules <= allowed_import_modules

    banned_names = {
        "propose_next_node",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "execute_mapped_step",
        "run_current_mapped_step",
        "run_current_step_stream",
        "EnvelopeSupplyResult",
        "CurrentStepRecord",
        "EnvelopeSupplyRecord",
        "PlanGraph",
        "CompiledWorkflowScaffold",
        "CatalogCurrentStepProvider",
        "WorkflowProvenanceEnvelopeSource",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "RookAgent",
        "base_agent",
        "dispatcher",
        "server",
        "model",
        "litellm",
        "OpenAI",
        "Path",
        "open",
        "json",
        "yaml",
        "loads",
        "dumps",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps"} & called_names)
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_response.py -q
```

Expected output:

```text
ModuleNotFoundError: No module named 'rook.agent.local_worker_turn_response'
```

If the failure is anything other than the missing production module, fix the test file before continuing.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add mcp_server/tests/test_local_worker_turn_response.py
git commit -m "test(lm5b): add local worker response contract tests"
```

---

## Task 2: Implement Local Worker Response Contract

**Files:**

- Create: `mcp_server/src/rook/agent/local_worker_turn_response.py`

- [ ] **Step 1: Create the production module**

```python
"""LM5B local-worker response contract.

Defines what a future local/internal worker may say back after receiving an
LM5A LocalWorkerTurnContext, and records whether that response is structurally
admissible. This module does not call models, parse worker text, execute tools,
mutate graphs, continue streams, or accept actions as execution permission.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Literal

from rook.agent.local_worker_turn_context import LocalWorkerTurnContext

WorkerResponseKind = Literal[
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
]
WorkerRefusalCategory = Literal[
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
]
WorkerResponseValidationFailure = Literal[
    "payload_invalid",
    "unknown_action_id",
    "action_input_invalid",
]

__all__ = (
    "LocalWorkerTurnResponse",
    "LocalWorkerTurnAttemptRecord",
    "WorkerActionRequest",
    "WorkerClarificationRequest",
    "WorkerRefusal",
    "WorkerObservation",
    "WorkerResponseKind",
    "WorkerRefusalCategory",
    "WorkerResponseValidationFailure",
    "validate_local_worker_turn_response",
)

_REFUSAL_CATEGORIES = frozenset(
    {
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
    }
)


@dataclass(frozen=True)
class WorkerActionRequest:
    action_id: str
    rationale: str
    input: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.action_id, "action_id")
        _require_non_empty_str(self.rationale, "rationale")
        object.__setattr__(
            self,
            "input",
            _freeze_json_mapping(self.input, "input"),
        )


@dataclass(frozen=True)
class WorkerClarificationRequest:
    question: str
    rationale: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str(self.question, "question")
        _require_optional_str(self.rationale, "rationale")


@dataclass(frozen=True)
class WorkerRefusal:
    category: WorkerRefusalCategory
    reason: str

    def __post_init__(self) -> None:
        category = _require_str(self.category, "category")
        if category not in _REFUSAL_CATEGORIES:
            raise ValueError(f"unknown refusal category: {category!r}")
        _require_non_empty_str(self.reason, "reason")


@dataclass(frozen=True)
class WorkerObservation:
    message: str
    data: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str(self.message, "message")
        if self.data is not None:
            object.__setattr__(
                self,
                "data",
                _freeze_json_mapping(self.data, "data"),
            )


WorkerResponsePayload = (
    WorkerActionRequest
    | WorkerClarificationRequest
    | WorkerRefusal
    | WorkerObservation
)
_PAYLOAD_TYPES = (
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerRefusal,
    WorkerObservation,
)


@dataclass(frozen=True)
class LocalWorkerTurnResponse:
    payload: WorkerResponsePayload

    def __post_init__(self) -> None:
        if not isinstance(self.payload, _PAYLOAD_TYPES):
            raise TypeError("payload must be a closed worker response payload")


@dataclass(frozen=True)
class LocalWorkerTurnAttemptRecord:
    valid: bool
    response_kind: WorkerResponseKind | None
    failure: WorkerResponseValidationFailure | None
    reason: str
    action_id: str | None
    context_workflow_id: str
    context_contract_fingerprint: str

    def __post_init__(self) -> None:
        _require_bool(self.valid, "valid")
        _require_optional_response_kind(self.response_kind, "response_kind")
        _require_optional_failure(self.failure, "failure")
        _require_non_empty_str(self.reason, "reason")
        _require_optional_str(self.action_id, "action_id")
        _require_non_empty_str(self.context_workflow_id, "context_workflow_id")
        _require_non_empty_str(
            self.context_contract_fingerprint,
            "context_contract_fingerprint",
        )


def validate_local_worker_turn_response(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnAttemptRecord:
    if not isinstance(context, LocalWorkerTurnContext):
        raise TypeError("context must be LocalWorkerTurnContext")
    if not isinstance(response, LocalWorkerTurnResponse):
        raise TypeError("response must be LocalWorkerTurnResponse")

    payload = response.payload
    if not isinstance(payload, _PAYLOAD_TYPES):
        return _record(
            context,
            valid=False,
            response_kind=None,
            failure="payload_invalid",
            reason="payload_invalid:closed_payload_required",
            action_id=None,
        )

    if isinstance(payload, WorkerActionRequest):
        return _validate_action_request(context, payload)
    if isinstance(payload, WorkerClarificationRequest):
        failure = _payload_invalid_reason(
            _validate_clarification_payload,
            payload,
            "clarification_request",
        )
        if failure is not None:
            return _payload_invalid_record(context, failure)
        return _record(
            context,
            valid=True,
            response_kind="clarification_request",
            failure=None,
            reason="valid_clarification_request",
            action_id=None,
        )
    if isinstance(payload, WorkerRefusal):
        failure = _payload_invalid_reason(
            _validate_refusal_payload,
            payload,
            "refusal",
        )
        if failure is not None:
            return _payload_invalid_record(context, failure)
        return _record(
            context,
            valid=True,
            response_kind="refusal",
            failure=None,
            reason="valid_refusal",
            action_id=None,
        )
    if isinstance(payload, WorkerObservation):
        failure = _payload_invalid_reason(
            _validate_observation_payload,
            payload,
            "observation",
        )
        if failure is not None:
            return _payload_invalid_record(context, failure)
        return _record(
            context,
            valid=True,
            response_kind="observation",
            failure=None,
            reason="valid_observation",
            action_id=None,
        )

    return _record(
        context,
        valid=False,
        response_kind=None,
        failure="payload_invalid",
        reason="payload_invalid:closed_payload_required",
        action_id=None,
    )


def _validate_action_request(
    context: LocalWorkerTurnContext,
    payload: WorkerActionRequest,
) -> LocalWorkerTurnAttemptRecord:
    payload_failure = _payload_invalid_reason(
        _validate_action_payload_without_input,
        payload,
        "action_request",
    )
    if payload_failure is not None:
        return _payload_invalid_record(context, payload_failure)

    action_id = payload.action_id if isinstance(payload.action_id, str) else None
    input_failure = _action_input_invalid_reason(payload.input)
    if input_failure is not None:
        return _record(
            context,
            valid=False,
            response_kind="action_request",
            failure="action_input_invalid",
            reason=input_failure,
            action_id=action_id,
        )

    allowed_action_ids = {action.action_id for action in context.allowed_actions}
    if payload.action_id not in allowed_action_ids:
        return _record(
            context,
            valid=False,
            response_kind="action_request",
            failure="unknown_action_id",
            reason=f"unknown_action_id:{payload.action_id}",
            action_id=payload.action_id,
        )

    return _record(
        context,
        valid=True,
        response_kind="action_request",
        failure=None,
        reason="valid_action_request",
        action_id=payload.action_id,
    )


def _payload_invalid_record(
    context: LocalWorkerTurnContext,
    reason: str,
) -> LocalWorkerTurnAttemptRecord:
    return _record(
        context,
        valid=False,
        response_kind=None,
        failure="payload_invalid",
        reason=reason,
        action_id=None,
    )


def _payload_invalid_reason(
    validator: object,
    payload: object,
    kind: str,
) -> str | None:
    try:
        validator(payload)  # type: ignore[operator]
    except (TypeError, ValueError):
        return f"payload_invalid:{kind}_invalid"
    return None


def _validate_action_payload_without_input(payload: WorkerActionRequest) -> None:
    _require_non_empty_str(payload.action_id, "action_id")
    _require_non_empty_str(payload.rationale, "rationale")


def _validate_clarification_payload(payload: WorkerClarificationRequest) -> None:
    _require_non_empty_str(payload.question, "question")
    _require_optional_str(payload.rationale, "rationale")


def _validate_refusal_payload(payload: WorkerRefusal) -> None:
    category = _require_str(payload.category, "category")
    if category not in _REFUSAL_CATEGORIES:
        raise ValueError(f"unknown refusal category: {category!r}")
    _require_non_empty_str(payload.reason, "reason")


def _validate_observation_payload(payload: WorkerObservation) -> None:
    _require_non_empty_str(payload.message, "message")
    if payload.data is not None:
        _freeze_json_mapping(payload.data, "data")


def _action_input_invalid_reason(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return "action_input_invalid:input_not_mapping"
    try:
        _freeze_json_mapping(value, "input")
    except TypeError:
        return "action_input_invalid:input_malformed"
    return None


def _record(
    context: LocalWorkerTurnContext,
    *,
    valid: bool,
    response_kind: WorkerResponseKind | None,
    failure: WorkerResponseValidationFailure | None,
    reason: str,
    action_id: str | None,
) -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=valid,
        response_kind=response_kind,
        failure=failure,
        reason=reason,
        action_id=action_id,
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def _freeze_json_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    frozen = _freeze_json_value(value, field_name)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return frozen


def _freeze_json_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} mapping keys must be strings")
            copied[key] = _freeze_json_value(item, f"{field_name}.{key}")
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(item, f"{field_name}[]")
            for item in value
        )
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{field_name} float values must be finite")
        return value
    raise TypeError(f"{field_name} contains unsupported JSON value")


def _require_non_empty_str(value: object, field_name: str) -> str:
    result = _require_str(value, field_name)
    if result == "":
        raise ValueError(f"{field_name} must not be empty")
    return result


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _require_optional_response_kind(
    value: object,
    field_name: str,
) -> WorkerResponseKind | None:
    if value is None:
        return None
    if value in {
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    }:
        return value  # type: ignore[return-value]
    raise ValueError(f"{field_name} has unknown response kind: {value!r}")


def _require_optional_failure(
    value: object,
    field_name: str,
) -> WorkerResponseValidationFailure | None:
    if value is None:
        return None
    if value in {
        "payload_invalid",
        "unknown_action_id",
        "action_input_invalid",
    }:
        return value  # type: ignore[return-value]
    raise ValueError(f"{field_name} has unknown failure: {value!r}")
```

- [ ] **Step 2: Run targeted tests and verify GREEN**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_response.py -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 3: Commit implementation**

```powershell
git add mcp_server/src/rook/agent/local_worker_turn_response.py mcp_server/tests/test_local_worker_turn_response.py
git commit -m "feat(lm5b): add local worker response contract"
```

---

## Task 3: Run Verification Gates

**Files:**

- Verify: `mcp_server/src/rook/agent/local_worker_turn_response.py`
- Verify: `mcp_server/tests/test_local_worker_turn_response.py`

- [ ] **Step 1: Run targeted LM5B tests**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_response.py -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 2: Run nearby LM5A/LM4 regression tests**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_response.py `
  mcp_server/tests/test_local_worker_turn_context.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_provenance.py `
  -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 3: Run focused PlanGraph/local-worker gate**

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' | Sort-Object Name | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  -q
```

Expected output:

```text
all tests pass
```

---

## Task 4: Run Boundary And Scope Checks

**Files:**

- Verify: `mcp_server/src/rook/agent/local_worker_turn_response.py`
- Verify no diff: `mcp_server/src/rook/agent/local_worker_turn_context.py`

- [ ] **Step 1: Check whitespace/diff hygiene**

```powershell
git diff --check main..HEAD
```

Expected output: no output.

- [ ] **Step 2: Check production scope**

```powershell
git diff --name-only main..HEAD -- mcp_server/src
```

Expected output:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
```

- [ ] **Step 3: Check LM5A source stayed untouched**

```powershell
git diff --name-only main..HEAD -- mcp_server/src/rook/agent/local_worker_turn_context.py
```

Expected output: no output.

- [ ] **Step 4: Check guarded repo areas stayed untouched**

```powershell
git diff --name-only main..HEAD -- src/Rook/base_agent.py knowledge/gh/operations_knowledge.json src/Rook src/RookNative
```

Expected output: no output.

- [ ] **Step 5: Run quick production boundary scan**

```powershell
rg -n "propose_next_node|map_accepted_proposal_to_step|revalidate_proposal|execute_mapped_step|run_current_mapped_step|run_current_step_stream|EnvelopeSupplyResult|CurrentStepRecord|EnvelopeSupplyRecord|PlanGraph|CompiledWorkflowScaffold|CatalogCurrentStepProvider|WorkflowProvenanceEnvelopeSource|compile_workflow_contract|load_workflow_contract_payload|snapshot_workflow_contract|RookAgent|base_agent|dispatcher|server|litellm|OpenAI|Path|open\(|import json|json\.loads|json\.dumps|yaml" mcp_server/src/rook/agent/local_worker_turn_response.py
```

Expected output: no output.

The AST guard in the test file is the primary boundary check. This `rg` scan is
a quick human-readable guard and intentionally avoids raw substring bans like
`model` or the helper name `_freeze_json_value`, which would false-fail on
valid prose/helper names.

- [ ] **Step 6: Check final worktree status**

```powershell
git status --short
```

Expected output: no output.

---

## Self-Review Checklist

- [ ] `LocalWorkerTurnResponse` is a closed, single-payload typed response.
- [ ] `WorkerResponsePayload` is not exported in `__all__`.
- [ ] Constructors validate/freeze ordinary shape safety.
- [ ] Validator raises `TypeError` only for wrong API inputs.
- [ ] Validator returns invalid records for worker-content invalidity.
- [ ] Unknown action id is the only normal invalid worker-content path.
- [ ] `action_input_invalid` is reserved for post-construction/bypassed malformed action input.
- [ ] No action input schema validation was added.
- [ ] Attempt records carry compact facts only and no full response payload.
- [ ] Production imports only `LocalWorkerTurnContext` from LM5A.
- [ ] No LM5A source file changed.
- [ ] No model/RookChat/runtime/stream/compile/load/file/JSON parser surface was added.

---

## Execution Recommendation

Use **Subagent-Driven** execution for this slice if available. LM5B is compact,
but it is the first output-side worker contract and deserves a fresh review loop
for accidental dispatch, parsing, or authority creep.

Inline execution is acceptable after plan approval if the implementation keeps
the RED/GREEN checkpoints and stops before PR for review.
