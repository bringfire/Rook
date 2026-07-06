# LM6A Live Worker Splice Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic machinery for LM6A, a live worker splice probe where a bounded worker-authored action can be staged onto the live repair node and, after merge, tested against the Rhino/GH repair floor.

**Architecture:** LM6A adds one production seam for applying worker-authored action params, one script-support helper for two-pass worker publication, and one new live probe script that manually sequences create/verify/worker/apply/repair/verify. The implementation PR is deterministic only; live recon/full runs happen after merge from synced `main`.

**Tech Stack:** Python 3.10, pytest, stdlib `urllib.request`, existing Rook PlanGraph/live producer/verifier seams, existing LM5G response loader, direct Ollama `/api/chat`.

---

## File Structure

Create:

```text
mcp_server/src/rook/agent/plan_graph_worker_action_apply.py
mcp_server/tests/test_plan_graph_worker_action_apply.py
scripts/lm_worker_two_pass_publication.py
mcp_server/tests/test_lm_worker_two_pass_publication.py
scripts/lm6a_live_worker_splice_probe.py
mcp_server/tests/test_lm6a_live_worker_splice_probe.py
docs/superpowers/plans/2026-07-06-lm6a-live-worker-splice-probe.md
```

Modify:

```text
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

Do not modify:

```text
production workflow templates
template selection
mcp_server/src/rook/agent/plan_graph_param_apply.py
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_prompt_artifact.py
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
```

The new modules have these boundaries:

- `plan_graph_worker_action_apply.py`: production seam, pure copy-on-write staging of worker-authored params.
- `lm_worker_two_pass_publication.py`: script-support helper, no production imports, shared LM5R/LM6A two-pass publication mechanics.
- `lm6a_live_worker_splice_probe.py`: live-capable script, owns Phase A/Phase B orchestration, artifacts, and terminal decisions.

## Task 1: Worker-Action Applier Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_worker_action_apply.py`
- Later create: `mcp_server/src/rook/agent/plan_graph_worker_action_apply.py`

- [ ] **Step 1: Write the applier test file**

Create `mcp_server/tests/test_plan_graph_worker_action_apply.py`:

```python
from __future__ import annotations

import ast
import pathlib

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_worker_action_apply import (
    WorkerActionApplyResult,
    apply_worker_action_to_node,
)
from rook.learning.plan_graph import GraphMemory, PlanGraph, PlanGraphNode


class _NoDeepcopy:
    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def _node(node_id: str, **meta) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", metadata=dict(meta))


def _graph(nodes, facts=None) -> PlanGraph:
    return PlanGraph(
        nodes={node.id: node for node in nodes},
        memory=GraphMemory(facts=dict(facts or {})),
    )


def _valid_action_input() -> dict[str, str]:
    return {"code": "A = 0.0;", "mode": "body"}


def _valid_anchor() -> dict[str, str]:
    return {"component_guid": "GUID-1", "language": "csharp"}


def test_success_stages_worker_params_copy_on_write() -> None:
    graph = _graph([_node("repair_same_component")])

    result = apply_worker_action_to_node(
        graph,
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding=_valid_anchor(),
    )

    assert isinstance(result, WorkerActionApplyResult)
    assert result.applied is True
    assert result.reason is None
    assert result.node_id == "repair_same_component"
    assert result.params_sha256 is not None
    assert result.graph is not graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata
    assert result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "code": "A = 0.0;",
        "mode": "body",
        "language": "csharp",
    }


def test_success_copies_inputs_without_aliasing() -> None:
    graph = _graph([_node("repair_same_component")])
    action_input = _valid_action_input()
    anchor = _valid_anchor()

    result = apply_worker_action_to_node(
        graph,
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=action_input,
        anchor_binding=anchor,
    )

    action_input["code"] = "MUTATED"
    anchor["component_guid"] = "MUTATED"
    staged = result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]
    assert staged == {
        "guid": "GUID-1",
        "code": "A = 0.0;",
        "mode": "body",
        "language": "csharp",
    }


def test_unknown_node_returns_structured_failure() -> None:
    graph = _graph([_node("repair_same_component")])

    result = apply_worker_action_to_node(
        graph,
        "missing",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding=_valid_anchor(),
    )

    assert result.applied is False
    assert result.reason == "unknown_node"
    assert result.graph is graph
    assert result.params_sha256 is None


def test_graph_copy_failed_returns_structured_failure() -> None:
    graph = _graph([
        _node("repair_same_component"),
        _node("other", bad=_NoDeepcopy()),
    ])

    result = apply_worker_action_to_node(
        graph,
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding=_valid_anchor(),
    )

    assert result.applied is False
    assert result.reason == "graph_copy_failed"
    assert result.graph is graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata


def test_invalid_action_id_rejected() -> None:
    result = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="other_action",
        action_input=_valid_action_input(),
        anchor_binding=_valid_anchor(),
    )
    assert result.applied is False
    assert result.reason == "invalid_action_id"


def test_invalid_action_input_shape_rejected() -> None:
    result = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=["not", "mapping"],
        anchor_binding=_valid_anchor(),
    )
    assert result.applied is False
    assert result.reason == "invalid_action_input"


def test_unexpected_action_input_key_rejected() -> None:
    result = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input={"code": "A = 0.0;", "mode": "body", "guid": "BAD"},
        anchor_binding=_valid_anchor(),
    )
    assert result.applied is False
    assert result.reason == "unexpected_action_input_key"


def test_missing_and_invalid_code_rejected() -> None:
    missing = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input={"mode": "body"},
        anchor_binding=_valid_anchor(),
    )
    empty = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input={"code": "   ", "mode": "body"},
        anchor_binding=_valid_anchor(),
    )
    non_string = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input={"code": 123, "mode": "body"},
        anchor_binding=_valid_anchor(),
    )

    assert missing.reason == "missing_code"
    assert empty.reason == "invalid_code"
    assert non_string.reason == "invalid_code"


def test_invalid_mode_rejected() -> None:
    result = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input={"code": "A = 0.0;", "mode": "full_source"},
        anchor_binding=_valid_anchor(),
    )
    assert result.applied is False
    assert result.reason == "invalid_mode"


def test_invalid_anchor_binding_shape_rejected() -> None:
    result = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding=["not", "mapping"],
    )
    assert result.applied is False
    assert result.reason == "invalid_anchor_binding"


def test_unexpected_anchor_binding_key_rejected() -> None:
    result = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding={
            "component_guid": "GUID-1",
            "language": "csharp",
            "target_errors": [],
        },
    )
    assert result.applied is False
    assert result.reason == "unexpected_anchor_binding_key"


def test_missing_and_invalid_component_guid_rejected() -> None:
    missing = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding={"language": "csharp"},
    )
    invalid = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding={"component_guid": "", "language": "csharp"},
    )

    assert missing.reason == "missing_component_guid"
    assert invalid.reason == "invalid_component_guid"


def test_missing_and_invalid_language_rejected() -> None:
    missing = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding={"component_guid": "GUID-1"},
    )
    invalid = apply_worker_action_to_node(
        _graph([_node("repair_same_component")]),
        "repair_same_component",
        action_id="draft_repair_params",
        action_input=_valid_action_input(),
        anchor_binding={"component_guid": "GUID-1", "language": "python"},
    )

    assert missing.reason == "missing_language"
    assert invalid.reason == "invalid_language"


def test_applier_import_boundary() -> None:
    import rook.agent.plan_graph_worker_action_apply as applier

    source = pathlib.Path(applier.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
            if node.module:
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert "rook.agent.plan_graph_param_apply" not in imports
    assert "BindStepSpec" not in imports
    assert "base_params" not in source
    assert "PROBE_REPAIR_CODE" not in source
    assert "A = 42.0" not in source
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "base_params"
        for node in ast.walk(tree)
    )
```

- [ ] **Step 2: Run the focused test and confirm it fails before implementation**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  -q
```

Expected: import failure for `rook.agent.plan_graph_worker_action_apply`.

## Task 2: Worker-Action Applier Implementation

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_worker_action_apply.py`
- Test: `mcp_server/tests/test_plan_graph_worker_action_apply.py`

- [ ] **Step 1: Add the applier module**

Create `mcp_server/src/rook/agent/plan_graph_worker_action_apply.py`:

```python
"""Worker-authored execution-param applier for live repair splice probes.

This module stages params authored by a bounded worker action plus trusted
anchor metadata onto one PlanGraph node. It is intentionally separate from
plan_graph_param_apply.py, which applies hidden/memory-bound params.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, TYPE_CHECKING

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


WorkerActionApplyReason = Literal[
    "unknown_node",
    "invalid_action_id",
    "invalid_action_input",
    "unexpected_action_input_key",
    "missing_code",
    "invalid_code",
    "invalid_mode",
    "invalid_anchor_binding",
    "unexpected_anchor_binding_key",
    "missing_component_guid",
    "invalid_component_guid",
    "missing_language",
    "invalid_language",
    "graph_copy_failed",
]


@dataclass(frozen=True)
class WorkerActionApplyResult:
    graph: "PlanGraph"
    applied: bool
    node_id: str
    reason: WorkerActionApplyReason | None
    params_sha256: str | None


def _params_sha256(params: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(params),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reject(
    graph: "PlanGraph",
    node_id: str,
    reason: WorkerActionApplyReason,
) -> WorkerActionApplyResult:
    return WorkerActionApplyResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        reason=reason,
        params_sha256=None,
    )


def apply_worker_action_to_node(
    graph: "PlanGraph",
    node_id: str,
    *,
    action_id: str,
    action_input: Mapping[str, Any],
    anchor_binding: Mapping[str, Any],
    allowed_action_id: str = "draft_repair_params",
) -> WorkerActionApplyResult:
    """Stage worker-authored repair params onto one node, copy-on-write.

    Expected validation failures return ``applied=False`` with a stable
    reason. The function never dispatches live work and never reads hidden
    bind/base params.
    """
    if node_id not in graph.nodes:
        return _reject(graph, node_id, "unknown_node")

    if action_id != allowed_action_id:
        return _reject(graph, node_id, "invalid_action_id")

    if not isinstance(action_input, Mapping):
        return _reject(graph, node_id, "invalid_action_input")

    extra_action_keys = set(action_input) - {"code", "mode"}
    if extra_action_keys:
        return _reject(graph, node_id, "unexpected_action_input_key")

    if "code" not in action_input:
        return _reject(graph, node_id, "missing_code")
    code = action_input.get("code")
    if not isinstance(code, str) or not code.strip():
        return _reject(graph, node_id, "invalid_code")

    mode = action_input.get("mode")
    if mode != "body":
        return _reject(graph, node_id, "invalid_mode")

    if not isinstance(anchor_binding, Mapping):
        return _reject(graph, node_id, "invalid_anchor_binding")

    extra_anchor_keys = set(anchor_binding) - {"component_guid", "language"}
    if extra_anchor_keys:
        return _reject(graph, node_id, "unexpected_anchor_binding_key")

    if "component_guid" not in anchor_binding:
        return _reject(graph, node_id, "missing_component_guid")
    component_guid = anchor_binding.get("component_guid")
    if not isinstance(component_guid, str) or not component_guid.strip():
        return _reject(graph, node_id, "invalid_component_guid")

    if "language" not in anchor_binding:
        return _reject(graph, node_id, "missing_language")
    language = anchor_binding.get("language")
    if language != "csharp":
        return _reject(graph, node_id, "invalid_language")

    params = {
        "guid": component_guid,
        "code": code,
        "mode": "body",
        "language": "csharp",
    }

    try:
        new_graph = deepcopy(graph)
    except Exception:
        return _reject(graph, node_id, "graph_copy_failed")

    new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = dict(params)
    return WorkerActionApplyResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        reason=None,
        params_sha256=_params_sha256(params),
    )


__all__ = (
    "WorkerActionApplyResult",
    "apply_worker_action_to_node",
)
```

- [ ] **Step 2: Run the applier tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  -q
```

Expected: all tests in the file pass.

- [ ] **Step 3: Commit the applier seam**

Run:

```powershell
git add mcp_server/src/rook/agent/plan_graph_worker_action_apply.py `
        mcp_server/tests/test_plan_graph_worker_action_apply.py
git commit -m "feat(lm6a): add worker action graph applier"
```

## Task 3: Shared Two-Pass Helper Tests

**Files:**
- Create: `mcp_server/tests/test_lm_worker_two_pass_publication.py`
- Later create: `scripts/lm_worker_two_pass_publication.py`

- [ ] **Step 1: Write tests for the shared helper surface**

Create `mcp_server/tests/test_lm_worker_two_pass_publication.py`:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _helper_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "lm_worker_two_pass_publication.py"


def _load_helper():
    path = _helper_path()
    spec = importlib.util.spec_from_file_location("lm_worker_two_pass_publication", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HELPER = _load_helper()


def _ollama_response(
    content: str,
    *,
    thinking: str | None = None,
    prompt_eval_count: int = 10,
    eval_count: int = 20,
) -> str:
    message: dict[str, str] = {"content": content}
    if thinking is not None:
        message["thinking"] = thinking
    return json.dumps(
        {
            "message": message,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
            "done_reason": "stop",
        }
    )


class _FakeProvider:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, endpoint: str, body: dict, timeout_s: float) -> str:
        self.calls.append(body)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)


def _request_payload() -> dict:
    return {
        "schema": "rook.local_worker_turn_request:v1",
        "context": {
            "current_node": {"node_id": "repair_same_component"},
            "allowed_actions": [
                {
                    "action_id": "draft_repair_params",
                    "kind": "draft_repair_params",
                    "description": "Draft replacement C# body repair parameters.",
                    "input_schema": {"type": "object", "required": ["code", "mode"]},
                }
            ],
            "knowledge": [],
        },
    }


def test_public_constants_match_lm5r() -> None:
    assert HELPER.PASS1_DECISION_INSTRUCTION_VERSION == "lm5s.pass1_decision_instruction:v2"
    assert HELPER.STATUSES == (
        "pass1_provider_error",
        "pass1_decision_invalid",
        "pass2_provider_error",
        "pass2_lm5g_invalid",
        "pass2_invariant_violation",
        "published",
    )


def test_successful_action_publication_returns_row_and_payload() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                '{"kind":"action_request","action_id":"draft_repair_params"}',
                thinking="I can act.",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "action_request",
                        "action_id": "draft_repair_params",
                        "rationale": "Criteria are sufficient.",
                        "input": {"code": "A = 0.0;", "mode": "body"},
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "published"
    assert result.row["pass1_kind"] == "action_request"
    assert result.row["pass2_response_kind"] == "action_request"
    assert result.row["action_id_preserved"] is True
    assert result.row["lm5g_loadable"] is True
    assert result.response_payload == {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Criteria are sufficient.",
        "input": {"code": "A = 0.0;", "mode": "body"},
    }
    assert provider.calls[0]["think"] is True
    assert provider.calls[1]["think"] is False
    assert provider.calls[1]["format"]["properties"]["action_id"]["const"] == (
        "draft_repair_params"
    )


def test_successful_clarification_publication_returns_payload() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "Need value?",
                        "rationale": None,
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "published"
    assert result.row["pass1_kind"] == "clarification_request"
    assert result.response_payload["kind"] == "clarification_request"


def test_pass1_provider_error_maps_to_status() -> None:
    def provider(_endpoint: str, _body: dict, _timeout_s: float) -> str:
        raise RuntimeError("provider down")

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass1_provider_error"
    assert result.row["failure_reason"] == "pass1_provider_error:RuntimeError"
    assert result.response_payload is None


def test_pass1_decision_invalid_maps_to_status() -> None:
    provider = _FakeProvider([_ollama_response("plain prose only")])

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass1_decision_invalid"
    assert result.row["failure_reason"] == "pass1_no_json_object"
    assert result.response_payload is None


def test_pass2_lm5g_invalid_maps_to_status() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass2_lm5g_invalid"
    assert result.row["failure_reason"] == "pass2_lm5g_load_failed:ValueError"
    assert result.response_payload is None


def test_invariant_violation_maps_to_status_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "Changed kind.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass2_invariant_violation"
    assert result.row["failure_reason"] == "pass2_kind_changed"
    assert result.row["lm5g_loadable"] is True
    assert result.response_payload is None


def test_observation_action_anomaly_is_scored_from_parsed_objects_only() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Decision: draft_repair_params",
                        "data": {"action_id": "draft_repair_params"},
                    }
                ),
                thinking="draft_repair_params in thinking is not scored separately",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "Visible state.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "published"
    assert result.row["pass1_observation_action_intent_anomaly"] is True
    assert result.row["pass1_observation_action_intent_reasons"] == [
        "observation_data_action_id_allowed",
        "observation_message_mentions_allowed_action_id",
    ]
    assert result.row["observation_action_intent_anomaly"] is True
    assert result.response_payload["kind"] == "observation"
```

- [ ] **Step 2: Run the helper tests and confirm import failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q
```

Expected: import failure for `scripts/lm_worker_two_pass_publication.py`.

## Task 4: Shared Two-Pass Helper Implementation

**Files:**
- Create: `scripts/lm_worker_two_pass_publication.py`
- Modify later: `scripts/lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Create the helper module from LM5R mechanics**

Create `scripts/lm_worker_two_pass_publication.py` by moving the following LM5R logic without behavior changes:

```text
PASS1_DECISION_INSTRUCTION_VERSION
_PASS1_DECISION_INSTRUCTION
STATUSES
RESPONSE_KINDS
_excerpt
_sha256_text
_extract_first_json_object
_parse_pass1_decision
_json_value_contains_allowed_action_id
_observation_action_intent_reasons
_allowed_action_ids_from_request
_set_combined_observation_anomaly
_schema_const_prop
_single_kind_response_schema
_FORMATTER_SYSTEM_TEXT
_formatter_messages
_build_pass2_body
_post_ollama_chat
_provider_message_fields
```

Add the helper-specific result dataclass and public function:

```python
@dataclass(frozen=True)
class TwoPassPublicationResult:
    row: dict[str, Any]
    response_payload: dict[str, Any] | None


def run_two_pass_worker_publication(
    request_payload: Mapping[str, Any],
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    post_chat: Callable[[str, dict[str, Any], float], str] = _post_ollama_chat,
) -> TwoPassPublicationResult:
    ...
```

Inside `run_two_pass_worker_publication`, derive pass-1 messages from the request payload:

```python
from rook.agent.local_worker_prompt_artifact import (
    render_local_worker_prompt_artifact,
)

prompt_artifact = render_local_worker_prompt_artifact(request_payload)
messages = [dict(message) for message in prompt_artifact["messages"]]
messages.append({"role": "user", "content": _PASS1_DECISION_INSTRUCTION})
```

The row should use the same field names as LM5R’s old `_empty_attempt_row`,
except that scenario/attempt may be filled by LM5R after the helper returns:

```python
row = {
    "model": model,
    "status": None,
    "failure_reason": None,
    "pass1_provider_status": None,
    "pass1_kind": None,
    "pass1_action_id": None,
    "pass1_refusal_category": None,
    "pass1_decision_sha256": None,
    "pass1_content_excerpt": None,
    "pass1_content_sha256": None,
    "pass1_thinking_present": False,
    "pass1_thinking_chars": 0,
    "pass1_thinking_sha256": None,
    "pass1_prompt_eval_count": None,
    "pass1_eval_count": None,
    "pass2_provider_status": None,
    "pass2_schema_kind": None,
    "pass2_response_kind": None,
    "pass2_action_id": None,
    "pass2_refusal_category": None,
    "pass2_content_excerpt": None,
    "pass2_content_sha256": None,
    "pass2_prompt_eval_count": None,
    "pass2_eval_count": None,
    "kind_preserved": None,
    "action_id_preserved": None,
    "refusal_category_preserved": None,
    "lm5g_loadable": False,
    "pass1_observation_action_intent_anomaly": False,
    "pass1_observation_action_intent_reasons": [],
    "pass2_observation_action_intent_anomaly": False,
    "pass2_observation_action_intent_reasons": [],
    "observation_action_intent_anomaly": False,
    "observation_action_intent_reasons": [],
}
```

When publication succeeds:

```python
row["status"] = "published"
return TwoPassPublicationResult(row=row, response_payload=dict(parsed_response))
```

For all provider/parse/load/invariant failures:

```python
return TwoPassPublicationResult(row=row, response_payload=None)
```

End with:

```python
__all__ = (
    "PASS1_DECISION_INSTRUCTION_VERSION",
    "STATUSES",
    "TwoPassPublicationResult",
    "run_two_pass_worker_publication",
)
```

- [ ] **Step 2: Run the helper tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q
```

Expected: all helper tests pass.

- [ ] **Step 3: Commit the helper**

Run:

```powershell
git add scripts/lm_worker_two_pass_publication.py `
        mcp_server/tests/test_lm_worker_two_pass_publication.py
git commit -m "feat(lm6a): extract two-pass worker publication helper"
```

## Task 5: Refactor LM5R To Use The Shared Helper

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Add behavior-preservation tests before refactor**

In `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`, add:

```python
def test_lm5r_pass1_instruction_identity_matches_shared_helper() -> None:
    import lm_worker_two_pass_publication as helper

    assert (
        PROBE.PASS1_DECISION_INSTRUCTION_VERSION
        == helper.PASS1_DECISION_INSTRUCTION_VERSION
    )
    assert PROBE._sha256_text(PROBE._PASS1_DECISION_INSTRUCTION) == PROBE._sha256_text(
        helper._PASS1_DECISION_INSTRUCTION
    )


def test_lm5r_status_vocabulary_matches_shared_helper() -> None:
    import lm_worker_two_pass_publication as helper

    assert PROBE.STATUSES == helper.STATUSES
```

Update existing `_run_attempt` assertions only if needed to allow `_run_attempt`
to call the helper. Preserve these exact fields in rows:

```text
scenario
attempt
model
status
failure_reason
pass1_kind
pass2_response_kind
kind_preserved
action_id_preserved
refusal_category_preserved
lm5g_loadable
pass1_observation_action_intent_anomaly
pass1_observation_action_intent_reasons
pass2_observation_action_intent_anomaly
pass2_observation_action_intent_reasons
observation_action_intent_anomaly
observation_action_intent_reasons
```

- [ ] **Step 2: Refactor LM5R imports and constants**

In `scripts/lm5r_two_pass_publication_probe.py`, import the shared helper:

```python
from lm_worker_two_pass_publication import (
    PASS1_DECISION_INSTRUCTION_VERSION,
    STATUSES,
    _PASS1_DECISION_INSTRUCTION,
    _post_ollama_chat,
    _sha256_text,
    run_two_pass_worker_publication,
)
```

Keep LM5R constants:

```python
SCRIPT_SCHEMA = "rook.lm5r_two_pass_publication_probe:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 5
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
EXCERPT_CHARS = 500
```

Remove duplicated helper functions from LM5R only after tests pass against the
shared helper. Keep `_pass1_messages_for_scenario(...)` if tests still use it,
but it should render the request payload and append the imported
`_PASS1_DECISION_INSTRUCTION`.

- [ ] **Step 3: Replace `_run_attempt` internals**

Change LM5R `_run_attempt` to build the request payload and call the helper:

```python
def _run_attempt(
    *,
    model: str,
    scenario: str,
    attempt: int,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    post_chat: Any = _post_ollama_chat,
) -> dict[str, Any]:
    _messages, request_payload = _pass1_messages_for_scenario(scenario)
    result = run_two_pass_worker_publication(
        request_payload,
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
        post_chat=post_chat,
    )
    row = dict(result.row)
    row["scenario"] = scenario
    row["attempt"] = attempt
    return row
```

If the helper no longer needs `_messages`, keep `_pass1_messages_for_scenario`
for compatibility tests and use its returned `request_payload`.

- [ ] **Step 4: Run LM5R and helper tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all pass. Existing LM5R manifest and summary tests must still pass.

- [ ] **Step 5: Commit LM5R helper reuse**

Run:

```powershell
git add scripts/lm5r_two_pass_publication_probe.py `
        mcp_server/tests/test_lm5r_two_pass_publication_probe.py
git commit -m "refactor(lm6a): reuse two-pass worker publication helper"
```

## Task 6: LM6A Script Static Utilities And Contract Tests

**Files:**
- Create: `scripts/lm6a_live_worker_splice_probe.py`
- Create/modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Write initial LM6A script tests**

Create `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from rook.agent.local_worker_source_routing_validator import (
    validate_worker_visible_source_routing,
)


def _script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "lm6a_live_worker_splice_probe.py"


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location("lm6a_live_worker_splice_probe", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])
    assert args.phase == "full"
    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0


def test_cli_receipt_recon_phase() -> None:
    args = PROBE._args(["--phase", "receipt_recon"])
    assert args.phase == "receipt_recon"


def test_bind_free_contract_removes_only_repair_bind_step() -> None:
    contract = PROBE._lm6a_bind_free_contract()
    repair_rules = [rule for rule in contract.rules if rule.node_id == "repair_same_component"]
    assert len(repair_rules) == 1
    repair_rule = repair_rules[0]
    assert len(repair_rule.steps_by_seen_count) == 1
    assert repair_rule.steps_by_seen_count[0].node_id == "repair_same_component"
    assert repair_rule.steps_by_seen_count[0].__class__.__name__ == "ProducerStepSpec"


def test_bind_free_contract_keeps_node_identities_and_refs() -> None:
    contract = PROBE._lm6a_bind_free_contract()

    assert [initial.node_id for initial in contract.initial_params] == ["create_script"]
    assert {rule.node_id for rule in contract.rules} == {
        "create_script",
        "verify_create",
        "repair_same_component",
        "verify_repair",
    }
    assert {
        ref.node_id: ref.execution_ref
        for ref in contract.expected_refs
    } == {
        "create_script": "gh_create_csharp_script:v1",
        "repair_same_component": "gh_update_script:v1",
    }


def test_bind_free_contract_contains_no_hidden_repair_answer() -> None:
    rendered = json.dumps(PROBE._contract_to_jsonable(PROBE._lm6a_bind_free_contract()), sort_keys=True)
    assert "PROBE_REPAIR_CODE" not in rendered
    assert "A = 42.0" not in rendered
    assert "base_params" not in rendered


def test_routing_artifact_is_static_valid() -> None:
    report = validate_worker_visible_source_routing(PROBE._LM6A_ROUTING_ARTIFACT)
    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()


def test_worker_visible_acceptance_criteria_projection_excludes_lm5w_metadata() -> None:
    packet = {
        "schema": "rook.acceptance_criteria_packet:v1",
        "source_set": {"source_classes": ["pin_contract"], "source_paths": ["x"]},
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": "create_script.initial_execution_params.pins_out",
                "source_class": "pin_contract",
            }
        ],
        "unresolved_intent": [],
        "fingerprint": "sha256:demo",
    }

    visible = PROBE._legacy_acceptance_criteria_projection(packet)

    assert visible == {
        "source": PROBE.ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": "create_script.initial_execution_params.pins_out",
            }
        ],
    }
    rendered = json.dumps(visible, sort_keys=True)
    assert "source_class" not in rendered
    assert "source_set" not in rendered
    assert "fingerprint" not in rendered
    assert "rook.acceptance_criteria_packet:v1" not in rendered
```

- [ ] **Step 2: Add a script skeleton**

Create `scripts/lm6a_live_worker_splice_probe.py` with constants, CLI, routing
artifact, bind-free contract builder, and projection helper only:

```python
#!/usr/bin/env python
"""LM6A live worker splice probe.

Deterministic implementation plus post-merge live evidence script. The script
manually sequences create/verify/worker/apply/repair/verify and writes bounded
local artifacts under probe_runs/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from lm5k_worker_probe import (
    ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
    REPAIR_TARGET_ERROR,
    _probe_contract,
)


SCRIPT_SCHEMA = "rook.lm6a_live_worker_splice_probe:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_PHASE = "full"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
PHASES = ("receipt_recon", "full")
DECISIONS = (
    "accepted",
    "rejected",
    "worker_declined",
    "gate_failed",
    "publication_failed",
)

_LM6A_ROUTING_ARTIFACT = {
    "schema": "rook.worker_visible_source_routing:v1",
    "routes": [
        {
            "node_id": "repair_same_component",
            "visible_sources": [
                {
                    "route_id": "repair_pin_contract",
                    "source_class": "pin_contract",
                    "source_path": "create_script.initial_execution_params.pins_out",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_expected_outcome",
                    "source_class": "verifier_outcome",
                    "source_path": "workflow_contract.rules.verify_repair.expected_outcome",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_target_diagnostics",
                    "source_class": "receipt_diagnostic",
                    "source_path": (
                        "create_script.receipt.script_receipt.repair_anchor."
                        "target_errors"
                    ),
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_body_mode_convention",
                    "source_class": "convention",
                    "source_path": "script_body_gotcha",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
            ],
        }
    ],
}


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LM6A live worker splice probe.")
    parser.add_argument("--phase", choices=PHASES, default=DEFAULT_PHASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--run-dir", default="probe_runs")
    return parser.parse_args(argv)


def _lm6a_bind_free_contract():
    from rook.agent.plan_graph_workflow_contract import (
        ProducerStepSpec,
        RookWorkflowContract,
        WorkflowNodeRule,
    )

    base = _probe_contract()
    rules = []
    for rule in base.rules:
        if rule.node_id == "repair_same_component":
            rules.append(
                WorkflowNodeRule(
                    node_id="repair_same_component",
                    steps_by_seen_count=(ProducerStepSpec(node_id="repair_same_component"),),
                )
            )
        else:
            rules.append(rule)
    return RookWorkflowContract(
        workflow_id="lm6a_live_worker_splice",
        template=base.template,
        initial_params=base.initial_params,
        expected_refs=base.expected_refs,
        rules=tuple(rules),
        terminal_node_ids=base.terminal_node_ids,
        max_steps=base.max_steps,
        metadata={
            **dict(base.metadata),
            "trace": {
                "slice": "LM6A",
                "contract_variant": "worker_binds_repair_params",
            },
        },
    )


def _contract_to_jsonable(contract) -> dict[str, Any]:
    return {
        "workflow_id": contract.workflow_id,
        "initial_params": [
            {
                "node_id": initial.node_id,
                "execution_params": dict(initial.execution_params),
            }
            for initial in contract.initial_params
        ],
        "expected_refs": [
            {
                "node_id": ref.node_id,
                "execution_ref": ref.execution_ref,
            }
            for ref in contract.expected_refs
        ],
        "rules": [
            {
                "node_id": rule.node_id,
                "steps_by_seen_count": [
                    step.__class__.__name__
                    for step in rule.steps_by_seen_count
                ],
            }
            for rule in contract.rules
        ],
        "metadata": dict(contract.metadata),
    }


def _legacy_acceptance_criteria_projection(packet: Mapping[str, Any]) -> dict[str, Any]:
    criteria = packet.get("criteria")
    if not isinstance(criteria, list):
        raise ValueError("acceptance criteria packet criteria missing")
    return {
        "source": ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
        "criteria": [
            {
                "criterion_id": item["criterion_id"],
                "description": item["description"],
                "source": item["source"],
            }
            for item in criteria
        ],
    }


def main(argv: list[str] | None = None) -> int:
    _args(argv)
    raise SystemExit("LM6A runtime flow is implemented in later tasks")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the LM6A static tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: tests in this file pass.

## Task 7: LM6A Phase A And Artifact Helpers With Fakes

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add tests for Phase A gate and artifact helpers**

Append to `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`:

```python
def test_decision_for_gate_failed_is_bounded() -> None:
    decision = PROBE._decision_record(
        decision="gate_failed",
        reason="phase_a_routability_failed",
        phase="receipt_recon",
    )

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "phase_a_routability_failed"
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
    rendered = json.dumps(decision, sort_keys=True)
    assert "A = 42.0" not in rendered
    assert "PROBE_REPAIR_CODE" not in rendered


def test_hidden_answer_scan_rejects_visible_leak() -> None:
    assert PROBE._hidden_answer_leaks({"code": "A = 42.0;"}) == ["A = 42.0"]
    assert PROBE._hidden_answer_leaks({"text": "PROBE_REPAIR_CODE"}) == [
        "PROBE_REPAIR_CODE"
    ]
    assert PROBE._hidden_answer_leaks({"code": "A = 0.0;"}) == []
```

Add a fake Phase A test that monkeypatches internals:

```python
def test_phase_a_gate_fails_when_routability_not_evaluated(monkeypatch, tmp_path) -> None:
    class _Report:
        valid = True
        routability_evaluated = False
        static_diagnostics = ()
        routability_diagnostics = ()

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", lambda *args, **kwargs: {
        "graph": object(),
        "workflow_contract": PROBE._lm6a_bind_free_contract(),
        "convention_packets": (),
        "live_create_summary": {},
        "verify_create_summary": {},
    })
    monkeypatch.setattr(PROBE, "validate_worker_visible_source_routing", lambda *args, **kwargs: _Report())

    recon = PROBE._run_phase_a_recon(run_dir=tmp_path, agent=None)

    assert recon["decision"]["decision"] == "gate_failed"
    assert recon["decision"]["reason"] == "phase_a_routability_not_evaluated"
```

- [ ] **Step 2: Implement Phase A helper skeletons**

Add to `scripts/lm6a_live_worker_splice_probe.py`:

```python
import hashlib
from datetime import datetime, timezone

from rook.agent.local_worker_acceptance_criteria import (
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_source_routing_validator import (
    validate_worker_visible_source_routing,
)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hidden_answer_leaks(value: Any) -> list[str]:
    rendered = json.dumps(value, sort_keys=True, default=str)
    leaks = []
    for needle in ("PROBE_REPAIR_CODE", "A = 42.0", "BindStepSpec.base_params.code"):
        if needle in rendered:
            leaks.append(needle)
    return leaks


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    live_repair_dispatched: bool = False,
    verify_repair_ran: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema": "rook.lm6a_decision:v1",
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "live_repair_dispatched": live_repair_dispatched,
        "verify_repair_ran": verify_repair_ran,
        **extra,
    }
```

Define `_run_phase_a_recon(...)` in terms of smaller helpers:

```python
def _run_phase_a_recon(*, run_dir: Path, agent: Any) -> dict[str, Any]:
    live = _run_live_create_and_verify(agent=agent)
    report = validate_worker_visible_source_routing(
        _LM6A_ROUTING_ARTIFACT,
        workflow_contract=live["workflow_contract"],
        graph=live["graph"],
        convention_packets=live["convention_packets"],
        worker_node_ids=("repair_same_component",),
    )
    if report.routability_evaluated is not True:
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_routability_not_evaluated",
            phase="receipt_recon",
        )
        return {"decision": decision, **live}
    errors = [
        diagnostic
        for diagnostic in (*report.static_diagnostics, *report.routability_diagnostics)
        if diagnostic.severity == "error"
    ]
    if errors:
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_routability_failed",
            phase="receipt_recon",
        )
        return {"decision": decision, "routing_report": report, **live}

    sources = extract_acceptance_criteria_sources(
        workflow_contract=live["workflow_contract"],
        graph=live["graph"],
        convention_packets=live["convention_packets"],
    )
    packet = assemble_acceptance_criteria_packet(sources)
    visible = _legacy_acceptance_criteria_projection(packet)
    if _hidden_answer_leaks(visible):
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_hidden_answer_leak",
            phase="receipt_recon",
        )
        return {"decision": decision, "acceptance_criteria_packet": packet, **live}
    return {
        "decision": None,
        "routing_report": report,
        "acceptance_criteria_packet": packet,
        "legacy_acceptance_criteria": visible,
        **live,
    }
```

For this task, `_run_live_create_and_verify` may be a temporary fail-closed
stub that raises until Task 10 implements real live sequencing:

```python
def _run_live_create_and_verify(*, agent: Any) -> dict[str, Any]:
    raise RuntimeError("live create/verify is implemented in Task 10")
```

This is allowed because deterministic tests monkeypatch it before the real
live sequencing task.

- [ ] **Step 3: Run LM6A tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: tests pass.

- [ ] **Step 4: Commit LM6A static/Phase A scaffolding**

Run:

```powershell
git add scripts/lm6a_live_worker_splice_probe.py `
        mcp_server/tests/test_lm6a_live_worker_splice_probe.py
git commit -m "feat(lm6a): add live splice probe scaffold"
```

## Task 8: LM6A Decision Mapping With Fakes

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add tests for worker/publication/action decision mapping**

Append:

```python
def _published_payload(kind: str, **extra) -> dict:
    payload = {"schema": "rook.local_worker_turn_response:v1", "kind": kind}
    payload.update(extra)
    return payload


def test_publication_failed_decision_for_invalid_publication() -> None:
    decision = PROBE._decision_from_worker_publication(
        publication_row={"status": "pass2_lm5g_invalid", "failure_reason": "bad"},
        response_payload=None,
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "bad"
    assert decision["live_repair_dispatched"] is False


def test_worker_declined_clarification() -> None:
    decision = PROBE._decision_from_worker_publication(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": False,
            "observation_action_intent_reasons": [],
        },
        response_payload=_published_payload(
            "clarification_request",
            question="Need desired value?",
            rationale=None,
        ),
    )

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_clarified"


def test_worker_declined_observation_anomaly() -> None:
    decision = PROBE._decision_from_worker_publication(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": True,
            "observation_action_intent_reasons": ["observation_data_action_id_allowed"],
        },
        response_payload=_published_payload("observation", message="x", data=None),
    )

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observation_action_intent_anomaly"


def test_worker_action_apply_failure_maps_to_rejected() -> None:
    class _ApplyResult:
        applied = False
        reason = "invalid_mode"
        params_sha256 = None

    decision = PROBE._decision_from_worker_action_apply(_ApplyResult())

    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
```

- [ ] **Step 2: Implement decision mapping helpers**

Add to `scripts/lm6a_live_worker_splice_probe.py`:

```python
def _decision_from_worker_publication(
    *,
    publication_row: Mapping[str, Any],
    response_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    status = publication_row.get("status")
    if status != "published" or response_payload is None:
        return _decision_record(
            decision="publication_failed",
            reason=str(publication_row.get("failure_reason") or status),
            phase="worker_publication",
        )

    kind = response_payload.get("kind")
    if kind == "action_request":
        return None
    if kind == "clarification_request":
        reason = "worker_clarified"
    elif kind == "refusal":
        reason = "worker_refused"
    elif kind == "observation":
        reason = (
            "worker_observation_action_intent_anomaly"
            if publication_row.get("observation_action_intent_anomaly") is True
            else "worker_observed"
        )
    else:
        reason = "worker_unknown_non_action"
    return _decision_record(
        decision="worker_declined",
        reason=reason,
        phase="worker_publication",
        worker_response_kind=str(kind),
        observation_action_intent_anomaly=bool(
            publication_row.get("observation_action_intent_anomaly")
        ),
        observation_action_intent_reasons=list(
            publication_row.get("observation_action_intent_reasons") or []
        ),
    )


def _decision_from_worker_action_apply(apply_result: Any) -> dict[str, Any]:
    return _decision_record(
        decision="rejected",
        reason=f"worker_action_apply_failed:{apply_result.reason}",
        phase="worker_action_apply",
        worker_action_apply={
            "applied": False,
            "reason": apply_result.reason,
            "params_sha256": apply_result.params_sha256,
        },
    )
```

- [ ] **Step 3: Run LM6A decision tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: tests pass.

## Task 9: LM6A Live Sequencing And Artifact Writing

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add fake full-flow tests**

Append:

```python
def test_full_flow_stops_after_recon_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(PROBE, "_run_phase_a_recon", lambda **kwargs: {
        "decision": None
    })

    run_dir = PROBE._run_probe(
        phase="receipt_recon",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "gate_passed"
    assert decision["reason"] == "receipt_recon_passed"


def test_full_flow_action_apply_rejection_writes_decision(monkeypatch, tmp_path) -> None:
    class _ApplyResult:
        applied = False
        reason = "invalid_mode"
        params_sha256 = None

    monkeypatch.setattr(PROBE, "_run_phase_a_recon", lambda **kwargs: {
        "decision": None,
        "graph": object(),
        "anchor_binding": {"component_guid": "GUID-1", "language": "csharp"},
        "request_payload": {"context": {"allowed_actions": []}},
    })
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", lambda *args, **kwargs: type(
        "Result",
        (),
        {
            "row": {"status": "published", "observation_action_intent_anomaly": False},
            "response_payload": {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "rationale": "Acting.",
                "input": {"code": "A = 0.0;", "mode": "bad"},
            },
        },
    )())
    monkeypatch.setattr(PROBE, "apply_worker_action_to_node", lambda *args, **kwargs: _ApplyResult())

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert not (run_dir / "live_repair_summary.json").exists()
    assert (run_dir / "worker_action.json").exists()
```

- [ ] **Step 2: Implement run directory, manifest, and main flow**

Add imports:

```python
from rook.agent.plan_graph_worker_action_apply import apply_worker_action_to_node
from lm_worker_two_pass_publication import run_two_pass_worker_publication
```

Implement run-dir creation:

```python
def _git_short_sha() -> str:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(run_root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / f"lm6a-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir
```

Implement `_run_probe(...)`:

```python
def _run_probe(
    *,
    phase: str,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    agent: Any,
) -> Path:
    run_dir = _new_run_dir(run_root)
    _write_json(
        run_dir / "manifest.json",
        {
            "script_schema": SCRIPT_SCHEMA,
            "git_commit": _git_short_sha(),
            "phase": phase,
            "model": model,
            "endpoint": endpoint,
            "temperature": temperature,
            "raw_artifacts": "local evidence under probe_runs; do not commit",
        },
    )

    recon = _run_phase_a_recon(run_dir=run_dir, agent=agent)
    if recon.get("routing_report") is not None:
        _write_json(run_dir / "routing_validation.json", _routing_report_json(recon["routing_report"]))
    if recon.get("acceptance_criteria_packet") is not None:
        _write_json(run_dir / "acceptance_criteria_packet.json", recon["acceptance_criteria_packet"])
    if recon.get("decision") is not None:
        _write_json(run_dir / "decision.json", recon["decision"])
        return run_dir
    if phase == "receipt_recon":
        decision = _decision_record(
            decision="gate_passed",
            reason="receipt_recon_passed",
            phase="receipt_recon",
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    publication = run_two_pass_worker_publication(
        recon["request_payload"],
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
    )
    _write_json(run_dir / "worker_publication_row.json", publication.row)
    decision = _decision_from_worker_publication(
        publication_row=publication.row,
        response_payload=publication.response_payload,
    )
    if decision is not None:
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    response_payload = publication.response_payload
    action_input = response_payload["input"]
    _write_json(run_dir / "worker_action.json", response_payload)
    apply_result = apply_worker_action_to_node(
        recon["graph"],
        "repair_same_component",
        action_id=response_payload["action_id"],
        action_input=action_input,
        anchor_binding=recon["anchor_binding"],
    )
    if apply_result.applied is not True:
        _write_json(run_dir / "decision.json", _decision_from_worker_action_apply(apply_result))
        return run_dir

    final = _dispatch_repair_and_verify(
        graph=apply_result.graph,
        agent=agent,
        params_sha256=apply_result.params_sha256,
        run_dir=run_dir,
    )
    _write_json(run_dir / "decision.json", final["decision"])
    return run_dir
```

For this task, `_dispatch_repair_and_verify(...)` may be a fake-friendly
fail-closed stub that raises unless monkeypatched. Task 10 fills the real live
path.

- [ ] **Step 3: Run LM6A fake-flow tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: tests pass.

## Task 10: Live Create/Verify And Repair/Verify Functions

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add deterministic tests for summary shapers**

Append:

```python
def test_live_summary_extracts_bounded_repair_anchor() -> None:
    summary = PROBE._live_result_summary(
        node_id="create_script",
        tool_name="gh_create_csharp_script",
        node_status="succeeded",
        outcome_status="needs_repair",
        verified=False,
        receipt={
            "language": "csharp",
            "artifact_status": "created_with_errors",
            "verification": {"status": "failed", "target_error_count": 1},
            "repair_anchor": {
                "component_guid": "GUID-1",
                "language": "csharp",
                "target_errors": [PROBE.REPAIR_TARGET_ERROR],
            },
        },
    )

    assert summary["repair_anchor"] == {
        "component_guid": "GUID-1",
        "language": "csharp",
        "target_errors": [PROBE.REPAIR_TARGET_ERROR],
    }
    assert summary["receipt_sha256"] is not None
```

- [ ] **Step 2: Implement live summary helper**

Add:

```python
def _live_result_summary(
    *,
    node_id: str,
    tool_name: str | None,
    node_status: str | None,
    outcome_status: str | None,
    verified: bool | None,
    receipt: Mapping[str, Any] | None,
    params_sha256: str | None = None,
) -> dict[str, Any]:
    repair_anchor = None
    receipt_sha256 = None
    if isinstance(receipt, Mapping):
        receipt_sha256 = _sha256_json(receipt)
        anchor = receipt.get("repair_anchor")
        if isinstance(anchor, Mapping):
            target_errors = anchor.get("target_errors")
            repair_anchor = {
                "component_guid": anchor.get("component_guid"),
                "language": anchor.get("language"),
            }
            if isinstance(target_errors, list):
                repair_anchor["target_errors"] = [
                    str(item)[:300] for item in target_errors[:3]
                ]
    summary = {
        "node_id": node_id,
        "tool_name": tool_name,
        "node_status": node_status,
        "outcome_status": outcome_status,
        "verified": verified,
        "receipt_status": receipt.get("artifact_status") if isinstance(receipt, Mapping) else None,
        "repair_anchor": repair_anchor,
        "receipt_sha256": receipt_sha256,
    }
    if params_sha256 is not None:
        summary["params_sha256"] = params_sha256
    return summary
```

- [ ] **Step 3: Implement real live create/verify helper**

Use the patterns from `mcp_server/tests/test_live_repair_chain_live.py`.

Add:

```python
def _extract_script_receipt(graph: Any, node_id: str) -> dict[str, Any] | None:
    evidence = graph.nodes[node_id].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        return None
    return dict(evidence.receipt)
```

Implement `_run_live_create_and_verify`:

```python
def _run_live_create_and_verify(*, agent: Any) -> dict[str, Any]:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
    from rook.agent.plan_graph_workflow_contract import compile_workflow_contract
    from rook.learning.plan_graph_runner import apply_verifier_step

    contract = _lm6a_bind_free_contract()
    scaffold = compile_workflow_contract(contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = dict(
        contract.initial_params[0].execution_params
    )

    create_result = _await(agent.run_live_producer_node(graph, "create_script"))
    graph = create_result.graph
    verify_create = apply_verifier_step(graph, "verify_create", "create_script")
    graph = verify_create.graph
    receipt = _extract_script_receipt(graph, "create_script")
    live_create_summary = _live_result_summary(
        node_id="create_script",
        tool_name=create_result.tool_name,
        node_status=graph.nodes["create_script"].status,
        outcome_status=str(create_result.outcome_status),
        verified=graph.nodes["create_script"].evidence.verified
        if graph.nodes["create_script"].evidence is not None
        else None,
        receipt=receipt,
    )
    verify_create_summary = {
        "verifier_node_id": "verify_create",
        "source_node_id": "create_script",
        "applied": verify_create.applied,
        "outcome_status": verify_create.outcome_status,
    }
    anchor = receipt.get("repair_anchor") if isinstance(receipt, Mapping) else None
    anchor_binding = {
        "component_guid": anchor.get("component_guid") if isinstance(anchor, Mapping) else None,
        "language": anchor.get("language") if isinstance(anchor, Mapping) else None,
    }
    from lm5k_worker_probe import _script_body_gotcha_packet
    return {
        "workflow_contract": contract,
        "graph": graph,
        "convention_packets": (_script_body_gotcha_packet(),),
        "anchor_binding": anchor_binding,
        "live_create_summary": live_create_summary,
        "verify_create_summary": verify_create_summary,
    }
```

Implement `_await` safely:

```python
def _await(awaitable):
    import asyncio

    return asyncio.run(awaitable)
```

If an existing event loop is a problem in tests, keep tests monkeypatched and
document live script should be run as a normal process.

- [ ] **Step 4: Implement real repair/verify helper**

Add:

```python
def _dispatch_repair_and_verify(
    *,
    graph: Any,
    agent: Any,
    params_sha256: str | None,
    run_dir: Path,
) -> dict[str, Any]:
    from rook.learning.plan_graph_runner import apply_verifier_step

    repair_result = _await(agent.run_live_producer_node(graph, "repair_same_component"))
    graph = repair_result.graph
    repair_receipt = _extract_script_receipt(graph, "repair_same_component")
    _write_json(
        run_dir / "live_repair_summary.json",
        _live_result_summary(
            node_id="repair_same_component",
            tool_name=repair_result.tool_name,
            node_status=graph.nodes["repair_same_component"].status,
            outcome_status=str(repair_result.outcome_status),
            verified=graph.nodes["repair_same_component"].evidence.verified
            if graph.nodes["repair_same_component"].evidence is not None
            else None,
            receipt=repair_receipt,
            params_sha256=params_sha256,
        ),
    )
    if repair_result.applied is not True:
        return {
            "decision": _decision_record(
                decision="rejected",
                reason=f"live_repair_failed:{repair_result.reason}",
                phase="live_repair",
                live_repair_dispatched=True,
                verify_repair_ran=False,
            )
        }

    verify_repair = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    _write_json(
        run_dir / "verify_repair_summary.json",
        {
            "verifier_node_id": "verify_repair",
            "source_node_id": "repair_same_component",
            "applied": verify_repair.applied,
            "outcome_status": verify_repair.outcome_status,
        },
    )
    accepted = verify_repair.applied is True and verify_repair.outcome_status == "succeeded"
    return {
        "decision": _decision_record(
            decision="accepted" if accepted else "rejected",
            reason="verify_repair_succeeded" if accepted else "verify_repair_failed",
            phase="verify_repair",
            live_repair_dispatched=True,
            verify_repair_ran=True,
        )
    }
```

- [ ] **Step 5: Write Phase A live summaries**

In `_run_phase_a_recon`, write:

```python
_write_json(run_dir / "live_create_summary.json", live["live_create_summary"])
_write_json(run_dir / "verify_create_summary.json", live["verify_create_summary"])
_write_json(run_dir / "phase_a_recon.json", {
    "repair_anchor_target_errors_present": True,
    "anchor_binding": live["anchor_binding"],
})
```

Before declaring Phase A pass, verify `anchor_binding` has non-empty
`component_guid` and `language == "csharp"`. On failure:

```python
decision = _decision_record(
    decision="gate_failed",
    reason="phase_a_anchor_binding_invalid",
    phase="receipt_recon",
)
```

- [ ] **Step 6: Run LM6A tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: all LM6A deterministic tests pass.

## Task 11: Main Entrypoint And Help Smoke

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add help smoke and static guard tests**

Append:

```python
def test_script_help_runs_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    python = repo_root / "mcp_server" / ".venv" / "Scripts" / "python.exe"
    result = __import__("subprocess").run(
        [str(python), "scripts/lm6a_live_worker_splice_probe.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LM6A live worker splice probe." in result.stdout


def test_script_static_forbidden_imports_and_graph_dump_guard() -> None:
    source = _script_path().read_text(encoding="utf-8")
    assert "LiteLLM" not in source
    assert "anthropic" not in source.lower()
    assert "debug-full-graph" not in source
```

The LM6A script is allowed to contain hidden-answer strings as forbidden-policy
data inside `_hidden_answer_leaks(...)`. Do not ban those strings from raw
source. Instead, keep the visible-request and decision-artifact tests that prove
the strings are not emitted.

- [ ] **Step 2: Implement `main`**

Replace the earlier fail-closed `main` body:

```python
def _build_agent():
    from rook.agent.base_agent import RookAgent
    from rook.server import _mcp_tool_executor

    return RookAgent(tool_executor=_mcp_tool_executor)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    run_dir = _run_probe(
        phase=args.phase,
        model=args.model,
        endpoint=args.endpoint,
        temperature=args.temperature,
        timeout_s=args.timeout_s,
        excerpt_chars=args.excerpt_chars,
        run_root=args.run_dir,
        agent=_build_agent(),
    )
    decision_path = run_dir / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    print(
        "LM6A live worker splice probe complete: "
        f"run_dir={run_dir} decision={decision['decision']} "
        f"reason={decision['reason']}"
    )
    return 0
```

- [ ] **Step 3: Run LM6A tests and help smoke**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: all pass, including help smoke.

- [ ] **Step 4: Commit LM6A live script**

Run:

```powershell
git add scripts/lm6a_live_worker_splice_probe.py `
        mcp_server/tests/test_lm6a_live_worker_splice_probe.py
git commit -m "feat(lm6a): add live worker splice probe script"
```

## Task 12: Final Verification And Drift Guards

**Files:**
- Verify all touched files
- No additional implementation changes unless verification fails

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Expected: all pass.

- [ ] **Step 2: Run nearby seam tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: all pass.

- [ ] **Step 3: Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\plan_graph_worker_action_apply.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  scripts\lm_worker_two_pass_publication.py `
  scripts\lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py
```

Expected: exits 0.

- [ ] **Step 4: Static diff checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected diff scope as a set:

```text
docs/superpowers/specs/2026-07-06-lm6a-live-worker-splice-probe-design.md
docs/superpowers/plans/2026-07-06-lm6a-live-worker-splice-probe.md
mcp_server/src/rook/agent/plan_graph_worker_action_apply.py
mcp_server/tests/test_plan_graph_worker_action_apply.py
scripts/lm_worker_two_pass_publication.py
mcp_server/tests/test_lm_worker_two_pass_publication.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
scripts/lm6a_live_worker_splice_probe.py
mcp_server/tests/test_lm6a_live_worker_splice_probe.py
```

- [ ] **Step 5: Forbidden drift checks**

Run:

```powershell
git diff --name-only main..HEAD | Select-String -Pattern `
  'plan_graph_param_apply.py|plan_graph_workflow_contract.py|plan_graph_templates.py|local_worker_turn_response.py|local_worker_prompt_artifact.py'
```

Expected: no output.

Run:

```powershell
rg -n "PROBE_REPAIR_CODE|A = 42\.0|BindStepSpec\.base_params|debug-full-graph" `
  scripts\lm6a_live_worker_splice_probe.py `
  mcp_server\src\rook\agent\plan_graph_worker_action_apply.py
```

Expected: no output from the applier; LM6A script may mention leak-check
strings only as forbidden policy data if tests explicitly allow that. If the
script mentions them, add or keep a static test proving they are not emitted
into worker-visible request/decision artifacts.

- [ ] **Step 6: Confirm no raw artifacts**

Run:

```powershell
git status --short
git status --short --ignored probe_runs
```

Expected: no tracked `probe_runs/` files. Ignored local runs may appear only if
someone manually ran the script; do not stage them.

- [ ] **Step 7: Commit final plan/doc or verification fixes**

If the plan was not yet committed:

```powershell
git add docs/superpowers/plans/2026-07-06-lm6a-live-worker-splice-probe.md
git commit -m "docs(lm6a): plan live worker splice probe"
```

If verification required small fixes, commit them with a focused message:

```powershell
git add <fixed files>
git commit -m "test(lm6a): tighten splice probe verification"
```

## Task 13: Implementation PR Handoff

**Files:**
- No code changes

- [ ] **Step 1: Confirm implementation PR contains no live run**

Check:

```powershell
git diff --name-only main..HEAD
git status --short --ignored probe_runs
```

Expected:

- no `probe_runs/` tracked
- no curated evidence summary doc changed
- no live evidence run required before PR

- [ ] **Step 2: PR body requirements**

The PR body should include:

```text
Summary:
- Adds worker-action graph applier for model-authored repair params.
- Extracts shared two-pass worker publication helper.
- Adds LM6A live worker splice probe script with deterministic fake coverage.

Verification:
- targeted LM6A tests
- nearby LM5/LM6 seam tests
- Python 3.10 compile
- git diff --check main..HEAD

Post-merge:
- run receipt recon:
  python scripts\lm6a_live_worker_splice_probe.py --phase receipt_recon
- if recon passes, run:
  python scripts\lm6a_live_worker_splice_probe.py

No live run artifacts committed.
```

- [ ] **Step 3: Stop before live run**

Do not run the canonical LM6A live commands in the implementation PR unless
the user explicitly changes the process. The live run is post-merge from synced
`main`.
