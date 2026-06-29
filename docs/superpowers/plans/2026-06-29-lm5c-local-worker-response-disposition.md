# LM5C Local Worker Response Disposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the deterministic LM5C disposition gate that records one compact gate receipt for one LM5B-validated worker response.

**Architecture:** Add one new agent-layer module that delegates admissibility to LM5B, maps the returned `LocalWorkerTurnAttemptRecord` to a coherent `LocalWorkerTurnDispositionRecord`, and exports only the disposition vocabulary, record, and public dispose function. The module does not inspect the LM5A context directly, parse payloads, freeze JSON, route, execute, continue streams, call models, or import LM4 runtime/compiler seams.

**Tech Stack:** Python dataclasses, `Literal` type alias, pytest, AST import/call boundary checks.

---

## File Structure

Create:

- `mcp_server/src/rook/agent/local_worker_turn_disposition.py`
  - Owns LM5C disposition vocabulary.
  - Owns `LocalWorkerTurnDispositionRecord`.
  - Owns `dispose_local_worker_turn_response(...)`.
  - Imports LM5A context type and LM5B response/attempt/validator types only.

- `mcp_server/tests/test_local_worker_turn_disposition.py`
  - Unit tests for mapping behavior, record coherence, delegation, TypeError propagation, public surface, and production boundary.
  - One small integration proof with a real LM5A context built from the known repair workflow.

Do not modify:

- `mcp_server/src/rook/agent/local_worker_turn_context.py`
- `mcp_server/src/rook/agent/local_worker_turn_response.py`
- package `__init__` files
- runtime/stream/provider/compiler modules
- RookChat, server, dispatcher, native, managed, or knowledge files

---

## Task 1: Add Failing LM5C Tests

**Files:**

- Create: `mcp_server/tests/test_local_worker_turn_disposition.py`

- [ ] **Step 1: Create the test file**

```python
from __future__ import annotations

import ast
import copy
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerWorkflowSummary,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
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

from rook.agent.local_worker_turn_disposition import (
    LocalWorkerTurnDispositionRecord,
    dispose_local_worker_turn_response,
)


def _minimal_context(*, action_ids: tuple[str, ...] = ("draft_bind_params",)):
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="lm5c_worker_disposition",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="a" * 64,
            compiler_id="rook_workflow_contract_compiler:v1",
            provider_id="catalog_current_step_provider:v1",
            selected_template_id="gh_csharp_create_verify_repair_verify",
            max_steps=6,
        ),
        current_graph=WorkerGraphSummary(
            node_count=0,
            node_ids=(),
            ready_node_ids=(),
            terminal_node_ids=(),
            status_counts={},
        ),
        current_node=None,
        history=WorkerHistorySummary(
            current_step_count=0,
            supply_count=0,
            last_accepted_node_id=None,
            last_execution_kind=None,
            last_stop_reason=None,
            recent_steps=(),
            recent_supplies=(),
        ),
        knowledge=(),
        allowed_actions=tuple(
            WorkerAllowedAction(
                action_id=action_id,
                kind="draft",
                description="Draft replacement C# body parameters.",
                input_schema={},
            )
            for action_id in action_ids
        ),
    )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5c_worker_disposition",
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
                    "name": "LM5CLocalWorkerDisposition",
                    "x": 350,
                    "y": 1200,
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
        metadata={"trace": {"slice": "LM5C"}},
    )


def _valid_action_attempt(
    action_id: str = "draft_bind_params",
) -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="action_request",
        failure=None,
        reason="valid_action_request",
        action_id=action_id,
        context_workflow_id="lm5c_worker_disposition",
        context_contract_fingerprint="a" * 64,
    )


def _valid_clarification_attempt() -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="clarification_request",
        failure=None,
        reason="valid_clarification_request",
        action_id=None,
        context_workflow_id="lm5c_worker_disposition",
        context_contract_fingerprint="a" * 64,
    )


def _valid_refusal_attempt() -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="refusal",
        failure=None,
        reason="valid_refusal",
        action_id=None,
        context_workflow_id="lm5c_worker_disposition",
        context_contract_fingerprint="a" * 64,
    )


def _valid_observation_attempt() -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="observation",
        failure=None,
        reason="valid_observation",
        action_id=None,
        context_workflow_id="lm5c_worker_disposition",
        context_contract_fingerprint="a" * 64,
    )


def _unknown_action_attempt(action_id: str = "invented") -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=False,
        response_kind="action_request",
        failure="unknown_action_id",
        reason=f"unknown_action_id:{action_id}",
        action_id=action_id,
        context_workflow_id="lm5c_worker_disposition",
        context_contract_fingerprint="a" * 64,
    )


def _record_for_attempt(
    attempt: LocalWorkerTurnAttemptRecord,
) -> LocalWorkerTurnDispositionRecord:
    if attempt.valid is False:
        return LocalWorkerTurnDispositionRecord(
            disposition="blocked",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"blocked:{attempt.reason}",
        )
    if attempt.response_kind == "action_request":
        return LocalWorkerTurnDispositionRecord(
            disposition="candidate_action_request",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"candidate_action_request:{attempt.action_id}",
        )
    if attempt.response_kind == "clarification_request":
        return LocalWorkerTurnDispositionRecord(
            disposition="clarification_needed",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason="clarification_needed",
        )
    if attempt.response_kind == "refusal":
        return LocalWorkerTurnDispositionRecord(
            disposition="refusal_recorded",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason="refusal_recorded",
        )
    if attempt.response_kind == "observation":
        return LocalWorkerTurnDispositionRecord(
            disposition="observation_recorded",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason="observation_recorded",
        )
    raise AssertionError(f"unsupported attempt for test fixture: {attempt!r}")


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_disposition as module

    assert module.__all__ == (
        "WorkerResponseDisposition",
        "LocalWorkerTurnDispositionRecord",
        "dispose_local_worker_turn_response",
    )
    assert "WorkerResponseDisposition" in module.__all__
    assert "_disposition_from_attempt" not in module.__all__


def test_disposition_record_is_frozen_dataclass() -> None:
    assert is_dataclass(LocalWorkerTurnDispositionRecord)
    assert LocalWorkerTurnDispositionRecord.__dataclass_params__.frozen is True


def test_disposition_record_has_only_compact_fields() -> None:
    assert tuple(field.name for field in fields(LocalWorkerTurnDispositionRecord)) == (
        "disposition",
        "attempt",
        "response_kind",
        "action_id",
        "reason",
    )


def test_valid_action_response_maps_to_candidate_action_request() -> None:
    context = _minimal_context()
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id="draft_bind_params",
            rationale="Draft repair params.",
            input={"code": "A = 42.0;"},
        )
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == "candidate_action_request"
    assert record.attempt.valid is True
    assert record.attempt.response_kind == "action_request"
    assert record.response_kind == "action_request"
    assert record.action_id == "draft_bind_params"
    assert record.reason == "candidate_action_request:draft_bind_params"


def test_valid_clarification_response_maps_to_clarification_needed() -> None:
    context = _minimal_context(action_ids=())
    response = LocalWorkerTurnResponse(
        WorkerClarificationRequest("Which component should be repaired?")
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == "clarification_needed"
    assert record.attempt.valid is True
    assert record.response_kind == "clarification_request"
    assert record.action_id is None
    assert record.reason == "clarification_needed"


def test_valid_refusal_response_maps_to_refusal_recorded() -> None:
    context = _minimal_context(action_ids=())
    response = LocalWorkerTurnResponse(
        WorkerRefusal("out_of_scope", "No allowed action fits.")
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == "refusal_recorded"
    assert record.attempt.valid is True
    assert record.response_kind == "refusal"
    assert record.action_id is None
    assert record.reason == "refusal_recorded"


def test_valid_observation_response_maps_to_observation_recorded() -> None:
    context = _minimal_context(action_ids=())
    response = LocalWorkerTurnResponse(WorkerObservation("No action requested."))

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == "observation_recorded"
    assert record.attempt.valid is True
    assert record.response_kind == "observation"
    assert record.action_id is None
    assert record.reason == "observation_recorded"


def test_unknown_action_flows_through_lm5b_and_maps_to_blocked() -> None:
    context = _minimal_context(action_ids=("draft_bind_params",))
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id="invented",
            rationale="Try an unavailable action.",
            input={},
        )
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.attempt.valid is False
    assert record.attempt.failure == "unknown_action_id"
    assert record.attempt.reason == "unknown_action_id:invented"
    assert record.disposition == "blocked"
    assert record.response_kind == "action_request"
    assert record.action_id == "invented"
    assert record.reason == "blocked:unknown_action_id:invented"


def test_blocked_disposition_preserves_attempt_kind_and_action_id() -> None:
    attempt = _unknown_action_attempt("missing")

    record = _record_for_attempt(attempt)

    assert record.attempt is attempt
    assert record.disposition == "blocked"
    assert record.response_kind == attempt.response_kind
    assert record.action_id == attempt.action_id
    assert record.reason == "blocked:unknown_action_id:missing"


@pytest.mark.parametrize(
    "attempt",
    [
        _valid_action_attempt(),
        _valid_clarification_attempt(),
        _valid_refusal_attempt(),
        _valid_observation_attempt(),
        _unknown_action_attempt(),
    ],
)
def test_disposition_record_accepts_coherent_direct_construction(
    attempt: LocalWorkerTurnAttemptRecord,
) -> None:
    record = _record_for_attempt(attempt)

    assert record.attempt is attempt


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("attempt", object()),
        ("disposition", 123),
        ("response_kind", 123),
        ("action_id", 123),
        ("reason", 123),
    ],
)
def test_disposition_record_wrong_scalar_types_rejected(
    field_name: str,
    bad_value: object,
) -> None:
    attempt = _valid_observation_attempt()
    kwargs = {
        "disposition": "observation_recorded",
        "attempt": attempt,
        "response_kind": "observation",
        "action_id": None,
        "reason": "observation_recorded",
    }
    kwargs[field_name] = bad_value

    with pytest.raises(TypeError):
        LocalWorkerTurnDispositionRecord(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"reason": ""},
        {"disposition": "invalid_response"},
        {"response_kind": "refusal"},
        {"action_id": "not-none"},
        {"disposition": "blocked"},
        {"reason": "wrong_reason"},
    ],
)
def test_valid_observation_record_rejects_incoherent_direct_construction(
    overrides: dict[str, object],
) -> None:
    attempt = _valid_observation_attempt()
    kwargs = {
        "disposition": "observation_recorded",
        "attempt": attempt,
        "response_kind": "observation",
        "action_id": None,
        "reason": "observation_recorded",
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"disposition": "candidate_action_request"},
        {"reason": "blocked:other"},
        {"response_kind": None},
        {"action_id": "other"},
    ],
)
def test_blocked_record_rejects_incoherent_direct_construction(
    overrides: dict[str, object],
) -> None:
    attempt = _unknown_action_attempt()
    kwargs = {
        "disposition": "blocked",
        "attempt": attempt,
        "response_kind": "action_request",
        "action_id": "invented",
        "reason": "blocked:unknown_action_id:invented",
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"disposition": "observation_recorded"},
        {"action_id": None},
        {"reason": "candidate_action_request:other"},
    ],
)
def test_valid_action_record_rejects_incoherent_direct_construction(
    overrides: dict[str, object],
) -> None:
    attempt = _valid_action_attempt()
    kwargs = {
        "disposition": "candidate_action_request",
        "attempt": attempt,
        "response_kind": "action_request",
        "action_id": "draft_bind_params",
        "reason": "candidate_action_request:draft_bind_params",
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("attempt", "disposition", "reason"),
    [
        (_valid_clarification_attempt(), "candidate_action_request", "clarification_needed"),
        (_valid_clarification_attempt(), "clarification_needed", "refusal_recorded"),
        (_valid_refusal_attempt(), "clarification_needed", "refusal_recorded"),
        (_valid_refusal_attempt(), "refusal_recorded", "observation_recorded"),
        (_valid_observation_attempt(), "refusal_recorded", "observation_recorded"),
    ],
)
def test_valid_non_action_records_reject_wrong_disposition_or_reason(
    attempt: LocalWorkerTurnAttemptRecord,
    disposition: str,
    reason: str,
) -> None:
    kwargs = {
        "disposition": disposition,
        "attempt": attempt,
        "response_kind": attempt.response_kind,
        "action_id": None,
        "reason": reason,
    }

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)


def test_private_disposition_helper_rejects_wrong_attempt_type() -> None:
    import rook.agent.local_worker_turn_disposition as module

    with pytest.raises(TypeError):
        module._disposition_from_attempt(object())  # type: ignore[attr-defined]


def test_monkeypatched_validator_receives_exact_context_and_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rook.agent.local_worker_turn_disposition as module

    context = _minimal_context()
    response = LocalWorkerTurnResponse(WorkerObservation("Observed."))
    fake_attempt = _valid_observation_attempt()
    received: list[tuple[LocalWorkerTurnContext, LocalWorkerTurnResponse]] = []

    def fake_validator(
        received_context: LocalWorkerTurnContext,
        received_response: LocalWorkerTurnResponse,
    ) -> LocalWorkerTurnAttemptRecord:
        received.append((received_context, received_response))
        return fake_attempt

    monkeypatch.setattr(module, "validate_local_worker_turn_response", fake_validator)

    record = module.dispose_local_worker_turn_response(context, response)

    assert received == [(context, response)]
    assert record.attempt is fake_attempt
    assert record.disposition == "observation_recorded"


def test_malformed_api_inputs_propagate_lm5b_type_error() -> None:
    context = _minimal_context()
    response = LocalWorkerTurnResponse(WorkerObservation("Observed."))

    with pytest.raises(TypeError):
        dispose_local_worker_turn_response(object(), response)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        dispose_local_worker_turn_response(context, object())  # type: ignore[arg-type]


def test_lm5b_type_error_propagates_from_dispose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rook.agent.local_worker_turn_disposition as module

    def raising_validator(
        received_context: LocalWorkerTurnContext,
        received_response: LocalWorkerTurnResponse,
    ) -> LocalWorkerTurnAttemptRecord:
        raise TypeError("bad lm5b api input")

    monkeypatch.setattr(module, "validate_local_worker_turn_response", raising_validator)

    with pytest.raises(TypeError, match="bad lm5b api input"):
        module.dispose_local_worker_turn_response(
            _minimal_context(),
            LocalWorkerTurnResponse(WorkerObservation("Observed.")),
        )


def test_real_lm5a_lm5b_chain_disposes_allowed_action_request() -> None:
    scaffold = compile_workflow_contract(_repair_contract())
    action = WorkerAllowedAction(
        action_id="draft_bind_params",
        kind="draft",
        description="Draft replacement C# body parameters.",
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    )
    context = build_local_worker_turn_context(
        scaffold,
        copy.deepcopy(scaffold.graph),
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(),
        allowed_actions=(action,),
    )
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=context.allowed_actions[0].action_id,
            rationale="Draft repair params from the LM5A turn context.",
            input={"code": "A = 42.0;"},
        )
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == "candidate_action_request"
    assert record.attempt.valid is True
    assert record.attempt.context_workflow_id == context.workflow.workflow_id
    assert (
        record.attempt.context_contract_fingerprint
        == context.workflow.contract_fingerprint
    )


def test_local_worker_disposition_module_boundary_is_gate_only() -> None:
    import rook.agent.local_worker_turn_disposition as module

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
        "dataclasses",
        "typing",
        "rook.agent.local_worker_turn_context",
        "rook.agent.local_worker_turn_response",
    }
    assert imported_modules <= allowed_import_modules

    banned_names = {
        "Any",
        "Mapping",
        "MappingProxyType",
        "math",
        "WorkerAllowedAction",
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
        "_freeze_json_value",
        "_freeze_json_mapping",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps"} & called_names)
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_disposition.py -q
```

Expected output:

```text
ModuleNotFoundError: No module named 'rook.agent.local_worker_turn_disposition'
```

If the failure is anything other than the missing production module, fix the
test file before continuing.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add mcp_server/tests/test_local_worker_turn_disposition.py
git commit -m "test(lm5c): add local worker disposition tests"
```

---

## Task 2: Implement Local Worker Response Disposition

**Files:**

- Create: `mcp_server/src/rook/agent/local_worker_turn_disposition.py`

- [ ] **Step 1: Create the production module**

```python
"""LM5C local-worker response disposition gate.

Records the deterministic gate disposition of one LM5B-validated worker
response. This module does not route, execute, retry, call models, mutate
graphs, continue streams, or authorize action requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rook.agent.local_worker_turn_context import LocalWorkerTurnContext
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerResponseKind,
    validate_local_worker_turn_response,
)

WorkerResponseDisposition = Literal[
    "blocked",
    "candidate_action_request",
    "clarification_needed",
    "refusal_recorded",
    "observation_recorded",
]

__all__ = (
    "WorkerResponseDisposition",
    "LocalWorkerTurnDispositionRecord",
    "dispose_local_worker_turn_response",
)

_DISPOSITIONS = frozenset(
    {
        "blocked",
        "candidate_action_request",
        "clarification_needed",
        "refusal_recorded",
        "observation_recorded",
    }
)
_VALID_DISPOSITION_BY_KIND = {
    "action_request": "candidate_action_request",
    "clarification_request": "clarification_needed",
    "refusal": "refusal_recorded",
    "observation": "observation_recorded",
}
_VALID_REASON_BY_KIND = {
    "clarification_request": "clarification_needed",
    "refusal": "refusal_recorded",
    "observation": "observation_recorded",
}


@dataclass(frozen=True)
class LocalWorkerTurnDispositionRecord:
    disposition: WorkerResponseDisposition
    attempt: LocalWorkerTurnAttemptRecord
    response_kind: WorkerResponseKind | None
    action_id: str | None
    reason: str

    def __post_init__(self) -> None:
        _require_attempt(self.attempt, "attempt")
        disposition = _require_str(self.disposition, "disposition")
        _require_optional_str(self.response_kind, "response_kind")
        _require_optional_str(self.action_id, "action_id")
        reason = _require_non_empty_str(self.reason, "reason")

        if disposition not in _DISPOSITIONS:
            raise ValueError(f"unknown disposition: {disposition!r}")
        if self.response_kind != self.attempt.response_kind:
            raise ValueError("response_kind must match attempt.response_kind")
        if self.action_id != self.attempt.action_id:
            raise ValueError("action_id must match attempt.action_id")

        _validate_disposition_coherence(
            disposition=disposition,
            attempt=self.attempt,
            reason=reason,
        )


def dispose_local_worker_turn_response(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnDispositionRecord:
    attempt = validate_local_worker_turn_response(context, response)
    return _disposition_from_attempt(attempt)


def _disposition_from_attempt(
    attempt: LocalWorkerTurnAttemptRecord,
) -> LocalWorkerTurnDispositionRecord:
    _require_attempt(attempt, "attempt")
    if attempt.valid is False:
        return LocalWorkerTurnDispositionRecord(
            disposition="blocked",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"blocked:{attempt.reason}",
        )

    if attempt.response_kind == "action_request":
        action_id = _require_non_empty_str(attempt.action_id, "attempt.action_id")
        return LocalWorkerTurnDispositionRecord(
            disposition="candidate_action_request",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"candidate_action_request:{action_id}",
        )

    if attempt.response_kind == "clarification_request":
        return _non_action_disposition(
            attempt,
            disposition="clarification_needed",
            reason="clarification_needed",
        )
    if attempt.response_kind == "refusal":
        return _non_action_disposition(
            attempt,
            disposition="refusal_recorded",
            reason="refusal_recorded",
        )
    if attempt.response_kind == "observation":
        return _non_action_disposition(
            attempt,
            disposition="observation_recorded",
            reason="observation_recorded",
        )

    raise ValueError(f"unsupported valid response_kind: {attempt.response_kind!r}")


def _non_action_disposition(
    attempt: LocalWorkerTurnAttemptRecord,
    *,
    disposition: WorkerResponseDisposition,
    reason: str,
) -> LocalWorkerTurnDispositionRecord:
    return LocalWorkerTurnDispositionRecord(
        disposition=disposition,
        attempt=attempt,
        response_kind=attempt.response_kind,
        action_id=attempt.action_id,
        reason=reason,
    )


def _validate_disposition_coherence(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if attempt.valid is False:
        _validate_blocked_disposition(
            disposition=disposition,
            attempt=attempt,
            reason=reason,
        )
        return

    if attempt.response_kind == "action_request":
        _validate_action_disposition(
            disposition=disposition,
            attempt=attempt,
            reason=reason,
        )
        return

    _validate_non_action_disposition(
        disposition=disposition,
        attempt=attempt,
        reason=reason,
    )


def _validate_blocked_disposition(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if disposition != "blocked":
        raise ValueError("invalid attempts require blocked disposition")
    expected_reason = f"blocked:{attempt.reason}"
    if reason != expected_reason:
        raise ValueError("blocked disposition reason must preserve attempt reason")


def _validate_action_disposition(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if disposition != "candidate_action_request":
        raise ValueError("valid action attempts require candidate_action_request")
    action_id = _require_non_empty_str(attempt.action_id, "attempt.action_id")
    expected_reason = f"candidate_action_request:{action_id}"
    if reason != expected_reason:
        raise ValueError("candidate action reason must include action_id")


def _validate_non_action_disposition(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if attempt.action_id is not None:
        raise ValueError("valid non-action dispositions require action_id to be None")

    expected_disposition = _VALID_DISPOSITION_BY_KIND.get(attempt.response_kind)
    if expected_disposition is None:
        raise ValueError(f"unsupported valid response_kind: {attempt.response_kind!r}")
    if disposition != expected_disposition:
        raise ValueError("disposition does not match attempt.response_kind")

    expected_reason = _VALID_REASON_BY_KIND.get(attempt.response_kind)
    if expected_reason is None:
        raise ValueError(f"unsupported valid response_kind: {attempt.response_kind!r}")
    if reason != expected_reason:
        raise ValueError("reason does not match attempt.response_kind")


def _require_attempt(
    value: object,
    field_name: str,
) -> LocalWorkerTurnAttemptRecord:
    if not isinstance(value, LocalWorkerTurnAttemptRecord):
        raise TypeError(f"{field_name} must be LocalWorkerTurnAttemptRecord")
    return value


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
```

- [ ] **Step 2: Run targeted tests and verify GREEN**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_disposition.py -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 3: Commit implementation**

```powershell
git add mcp_server/src/rook/agent/local_worker_turn_disposition.py mcp_server/tests/test_local_worker_turn_disposition.py
git commit -m "feat(lm5c): add local worker response disposition"
```

---

## Task 3: Run Verification Gates

**Files:**

- Verify: `mcp_server/src/rook/agent/local_worker_turn_disposition.py`
- Verify: `mcp_server/tests/test_local_worker_turn_disposition.py`

- [ ] **Step 1: Run targeted LM5C tests**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_disposition.py -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 2: Run nearby LM5/LM4 regression tests**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_disposition.py `
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
  mcp_server\tests\test_local_worker_turn_disposition.py `
  -q
```

Expected output:

```text
all tests pass
```

---

## Task 4: Run Boundary And Scope Checks

**Files:**

- Verify: `mcp_server/src/rook/agent/local_worker_turn_disposition.py`
- Verify no diff: `mcp_server/src/rook/agent/local_worker_turn_context.py`
- Verify no diff: `mcp_server/src/rook/agent/local_worker_turn_response.py`

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
mcp_server/src/rook/agent/local_worker_turn_disposition.py
```

- [ ] **Step 3: Check LM5A and LM5B source stayed untouched**

```powershell
git diff --name-only main..HEAD -- `
  mcp_server/src/rook/agent/local_worker_turn_context.py `
  mcp_server/src/rook/agent/local_worker_turn_response.py
```

Expected output: no output.

- [ ] **Step 4: Check guarded repo areas stayed untouched**

```powershell
git diff --name-only main..HEAD -- src/Rook/base_agent.py knowledge/gh/operations_knowledge.json src/Rook src/RookNative
```

Expected output: no output.

- [ ] **Step 5: Run quick production boundary scan**

```powershell
rg -n "WorkerAllowedAction|propose_next_node|map_accepted_proposal_to_step|revalidate_proposal|execute_mapped_step|run_current_mapped_step|run_current_step_stream|EnvelopeSupplyResult|CurrentStepRecord|EnvelopeSupplyRecord|PlanGraph|CompiledWorkflowScaffold|CatalogCurrentStepProvider|WorkflowProvenanceEnvelopeSource|compile_workflow_contract|load_workflow_contract_payload|snapshot_workflow_contract|RookAgent|base_agent|dispatcher|server|litellm|OpenAI|Path|open\(|import json|json\.loads|json\.dumps|yaml|MappingProxyType|from typing import Any|from collections\.abc import Mapping|import math|_freeze_json" mcp_server/src/rook/agent/local_worker_turn_disposition.py
```

Expected output: no output.

The AST guard in the test file is the primary boundary check. This `rg` scan is
a quick human-readable guard and intentionally avoids raw substring bans like
`model`.

- [ ] **Step 6: Check final worktree status**

```powershell
git status --short
```

Expected output: no output.

---

## Self-Review Checklist

- [ ] Public surface exports only `WorkerResponseDisposition`, `LocalWorkerTurnDispositionRecord`, and `dispose_local_worker_turn_response`.
- [ ] `LocalWorkerTurnDispositionRecord` nests the exact LM5B attempt record and does not carry response/context/payload fields.
- [ ] `__post_init__` checks scalar types before coherence.
- [ ] `response_kind == attempt.response_kind` and `action_id == attempt.action_id` are enforced.
- [ ] Invalid attempts map only to `blocked`.
- [ ] Blocked reasons preserve LM5B attempt reason as `blocked:<attempt.reason>`.
- [ ] Valid action requests map only to `candidate_action_request:<action_id>`.
- [ ] Valid clarification/refusal/observation map to their compact reason strings.
- [ ] `dispose_local_worker_turn_response(...)` delegates to LM5B and does not inspect context fields.
- [ ] LM5B `TypeError`s propagate.
- [ ] No retry/fallback/critic/oversight/routing/policy hints were added.
- [ ] No action authorization, dispatch, execution, schema validation, graph mutation, or stream continuation was added.
- [ ] No JSON/freezing/payload machinery was added to LM5C.
- [ ] No LM5A or LM5B production source files changed.

---

## Execution Recommendation

Use **Subagent-Driven** execution for this slice if available. LM5C is small, but
it is a gate layer downstream of LM5B and deserves a fresh review loop for
accidental routing, policy, context-inspection, or authority creep.

Inline execution is acceptable after plan approval if the implementation keeps
the RED/GREEN checkpoints and stops before PR for review.
