# LM5J Local Worker Adapter Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic socket the first live worker model will plug into: a prompt-artifact renderer over the LM5I request envelope, and a bounded adapter (`envelope -> prompt -> transport -> raw output -> LM5G load -> record`) with an exact failure-reason taxonomy — no live model, no provider, no network.

**Architecture:** Two new pure agent-layer modules following the LM5 family discipline (frozen dataclasses, strict boundary validation, stdlib-only, AST-guarded imports). The prompt renderer mechanically derives instructions from the envelope's machine-readable `response_contract` and fails closed if that interior is mutated. The adapter performs one bounded invocation returning a typed record; it never loops, retries, or evaluates.

**Tech Stack:** Python **3.10-compatible code** (the package supports 3.10+; the local test runtime may be 3.12), stdlib only (`json`, `dataclasses`, `typing.Protocol`), pytest. Spec: `docs/superpowers/specs/2026-07-02-lm5j-local-worker-adapter-contract-design.md`.

## Global Constraints

- Worktree: `C:/UDEV/Rook-lm5j`, branch `codex/lm5j-worker-adapter-contract`. All paths below are relative to `C:/UDEV/Rook-lm5j`.
- Production diff limited to exactly two new modules: `mcp_server/src/rook/agent/local_worker_prompt_artifact.py` and `mcp_server/src/rook/agent/local_worker_adapter.py`. **No LM5A–I production edits.**
- Schema constants (verbatim): `rook.local_worker_prompt_artifact:v1`, `lm5j.prompt_text:v1`, `rook.local_worker_adapter_record:v1`.
- Excerpt limit: `RAW_OUTPUT_EXCERPT_LIMIT = 500`.
- Parse policy: whitespace trim only; **no fence unwrapping** — fenced output is `raw_output_invalid:json_decode`.
- Transport call catches `Exception` only; `KeyboardInterrupt`/`SystemExit`/`BaseException` propagate.
- Failure reasons exactly per spec §4.2a; `failure_reason is None` iff `status == "response_loaded"`. The record's `__post_init__` enforces the **exact taxonomy** (not just a status prefix): `transport_error:declared`, `transport_error:unexpected:<detail>`, `raw_output_invalid:not_text:<detail>`, `raw_output_invalid:empty`, `raw_output_invalid:json_decode`, `raw_output_invalid:not_mapping`, `response_payload_invalid:<detail>` — where every `<detail>` is a non-empty ASCII alnum/underscore string.
- All new production and test code must be **Python 3.10-compatible**; Task 5 runs a `py -3.10 -m py_compile` gate over both modules and both test files.
- No live model, provider SDK, network, file IO, YAML, Capability Index, plan-graph runtime, or LM5C/D/F imports in production (tests may import LM5C/D/F).
- Prompt module never references `loads`; adapter module never references `dumps`.
- Both modules pin `__all__` exactly (reviewer requirement) with a test asserting the exact tuple.
- Run all tests with the worktree venv: `mcp_server\.venv\Scripts\python.exe` **created inside the worktree** (Task 1 Step 0). Never use `C:/UDEV/Rook/mcp_server/.venv` — its editable install resolves `rook` to the main checkout's source, not this worktree's.

---

### Task 1: Worktree venv + prompt-artifact boundary validation

**Files:**
- Create: `mcp_server/src/rook/agent/local_worker_prompt_artifact.py`
- Test: `mcp_server/tests/test_local_worker_prompt_artifact.py`

**Interfaces:**
- Consumes: `LOCAL_WORKER_TURN_REQUEST_SCHEMA` and `render_local_worker_turn_request_payload` from `rook.agent.local_worker_turn_request` (LM5I); `build_local_worker_turn_context` fixture types from `rook.agent.local_worker_turn_context` (LM5A).
- Produces: `LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA: str`, `LOCAL_WORKER_PROMPT_TEXT_VERSION: str`, `render_local_worker_prompt_artifact(request_payload: Mapping[str, Any]) -> Mapping[str, Any]` — Task 2 completes its rendering; Task 4 calls it from the adapter.

- [ ] **Step 0: Create the worktree venv**

```powershell
cd C:\UDEV\Rook-lm5j\mcp_server
uv venv .venv --python 3.12
uv pip install -e . --python .venv\Scripts\python.exe
.venv\Scripts\python.exe -c "import rook.agent.local_worker_turn_request as m; print(m.__file__)"
```

Expected: the printed path is under `C:\UDEV\Rook-lm5j\` (NOT `C:\UDEV\Rook\`). If it is not, stop and fix the install before proceeding.

- [ ] **Step 1: Write the failing boundary tests**

Create `mcp_server/tests/test_local_worker_prompt_artifact.py`:

```python
from __future__ import annotations

import ast
import copy
import inspect
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
    assert LOCAL_WORKER_PROMPT_TEXT_VERSION == "lm5j.prompt_text:v1"


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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd C:\UDEV\Rook-lm5j
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_prompt_artifact.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'rook.agent.local_worker_prompt_artifact'`.

- [ ] **Step 3: Implement the boundary (module skeleton + validation)**

Create `mcp_server/src/rook/agent/local_worker_prompt_artifact.py`:

```python
"""LM5J local-worker prompt artifact renderer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from rook.agent.local_worker_turn_request import LOCAL_WORKER_TURN_REQUEST_SCHEMA

LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA = "rook.local_worker_prompt_artifact:v1"
LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5j.prompt_text:v1"

__all__ = (
    "LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA",
    "LOCAL_WORKER_PROMPT_TEXT_VERSION",
    "render_local_worker_prompt_artifact",
)

_TOP_LEVEL_KEYS = frozenset(
    {"schema", "context", "response_schema", "response_contract"}
)
_CONTRACT_KEYS = frozenset(
    {"kinds", "field_sets", "required_nullable_fields", "refusal_categories"}
)

_INSTRUCTION_TEXT = (
    "You are a bounded Rook worker resolving exactly one workflow node.\n"
    "The user content is a request envelope as JSON: the workflow context\n"
    "you may rely on and the contract your reply must follow.\n"
    "Reply with exactly one JSON object and nothing else: no code fences,\n"
    "no markdown, no commentary before or after the object.\n"
    "The object must follow exactly one of the allowed reply envelopes\n"
    "listed below, using exactly the listed entries."
)


def render_local_worker_prompt_artifact(
    request_payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    payload = _require_request_envelope(request_payload)
    contract = _require_response_contract(payload["response_contract"])
    response_schema = payload["response_schema"]
    if not isinstance(response_schema, str) or not response_schema:
        raise ValueError(
            "request payload response_schema must be a non-empty string"
        )
    system_text = (
        _INSTRUCTION_TEXT + "\n\n" + _render_contract_text(response_schema, contract)
    )
    user_text = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return {
        "schema": LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        "prompt_text_version": LOCAL_WORKER_PROMPT_TEXT_VERSION,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
    }


def _require_request_envelope(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("request payload must be a mapping")
    for key in value.keys():
        if not isinstance(key, str):
            raise TypeError("request payload keys must be strings")
    if set(value.keys()) != _TOP_LEVEL_KEYS:
        raise ValueError(
            f"request payload keys must be exactly {sorted(_TOP_LEVEL_KEYS)!r}"
        )
    schema = value["schema"]
    if not isinstance(schema, str):
        raise TypeError("request payload schema must be a string")
    if schema != LOCAL_WORKER_TURN_REQUEST_SCHEMA:
        raise ValueError(f"unsupported request payload schema: {schema!r}")
    return value


def _require_response_contract(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("response_contract must be a mapping")
    if set(value.keys()) != _CONTRACT_KEYS:
        raise ValueError(
            f"response_contract keys must be exactly {sorted(_CONTRACT_KEYS)!r}"
        )
    kinds = _require_str_sequence(value["kinds"], "response_contract kinds")
    field_sets = value["field_sets"]
    if not isinstance(field_sets, Mapping):
        raise TypeError("response_contract field_sets must be a mapping")
    if set(field_sets.keys()) != set(kinds):
        raise ValueError(
            "response_contract field_sets keys must exactly cover kinds"
        )
    for kind in kinds:
        _require_str_sequence(
            field_sets[kind], f"response_contract field_sets[{kind!r}]"
        )
    nullable = value["required_nullable_fields"]
    if not isinstance(nullable, Mapping):
        raise TypeError(
            "response_contract required_nullable_fields must be a mapping"
        )
    for kind, fields in nullable.items():
        if not isinstance(kind, str) or kind not in kinds:
            raise ValueError(
                "response_contract required_nullable_fields keys must be kinds"
            )
        _require_str_sequence(
            fields, f"response_contract required_nullable_fields[{kind!r}]"
        )
    _require_str_sequence(
        value["refusal_categories"], "response_contract refusal_categories"
    )
    return value


def _require_str_sequence(value: object, context: str) -> Sequence[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{context} must be a sequence of strings")
    if not value:
        raise ValueError(f"{context} must be non-empty")
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{context} entries must be non-empty strings")
    return value


def _render_contract_text(
    response_schema: str, contract: Mapping[str, Any]
) -> str:
    kinds = contract["kinds"]
    lines = [
        "Declared reply schema value: " + response_schema,
        "Allowed reply kinds: " + ", ".join(kinds),
    ]
    for kind in kinds:
        lines.append(
            "Fields for " + kind + ": " + ", ".join(contract["field_sets"][kind])
        )
    nullable = contract["required_nullable_fields"]
    for kind in kinds:
        if kind in nullable:
            lines.append(
                "Required but nullable for "
                + kind
                + ": "
                + ", ".join(nullable[kind])
            )
    lines.append(
        "Refusal categories: " + ", ".join(contract["refusal_categories"])
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_prompt_artifact.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git -C C:\UDEV\Rook-lm5j add mcp_server/src/rook/agent/local_worker_prompt_artifact.py mcp_server/tests/test_local_worker_prompt_artifact.py
git -C C:\UDEV\Rook-lm5j commit -m "feat(lm5j): prompt artifact boundary validation"
```

---

### Task 2: Prompt-artifact rendering guarantees

**Files:**
- Modify: `mcp_server/tests/test_local_worker_prompt_artifact.py` (append tests only)
- Modify: `mcp_server/src/rook/agent/local_worker_prompt_artifact.py` (only if a test exposes a defect — the Task 1 implementation is intended to already satisfy these)

**Interfaces:**
- Consumes: Task 1's module as written.
- Produces: the pinned artifact shape `{"schema", "prompt_text_version", "messages": [{"role": "system", ...}, {"role": "user", ...}]}` that Task 4's adapter passes to transports.

- [ ] **Step 1: Append the rendering tests**

Append to `mcp_server/tests/test_local_worker_prompt_artifact.py`:

```python
import json


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


def test_instruction_constant_has_no_kind_or_field_literals() -> None:
    payload = _request_payload()
    contract = payload["response_contract"]
    instruction = prompt_module._INSTRUCTION_TEXT
    for kind in contract["kinds"]:
        assert kind not in instruction
        for field in contract["field_sets"][kind]:
            if field in {"schema", "kind"}:
                continue
            assert field not in instruction
    for category in contract["refusal_categories"]:
        assert category not in instruction


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
```

- [ ] **Step 2: Run tests**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_prompt_artifact.py -v
```

Expected: all PASS (Task 1's implementation already provides these guarantees). If any fail, fix the module — the tests are the contract, not the implementation.

- [ ] **Step 3: Commit**

```powershell
git -C C:\UDEV\Rook-lm5j add mcp_server/tests/test_local_worker_prompt_artifact.py mcp_server/src/rook/agent/local_worker_prompt_artifact.py
git -C C:\UDEV\Rook-lm5j commit -m "test(lm5j): pin prompt artifact rendering guarantees"
```

---

### Task 3: Adapter record types

**Files:**
- Create: `mcp_server/src/rook/agent/local_worker_adapter.py`
- Test: `mcp_server/tests/test_local_worker_adapter.py`

**Interfaces:**
- Consumes: `LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA`, `LOCAL_WORKER_PROMPT_TEXT_VERSION` (Task 1); `LocalWorkerTurnResponse`, `WorkerActionRequest` from `rook.agent.local_worker_turn_response`.
- Produces: `LOCAL_WORKER_ADAPTER_RECORD_SCHEMA: str`, `RAW_OUTPUT_EXCERPT_LIMIT: int`, `TransportError(Exception)`, `LocalWorkerTransport` (Protocol with `send(prompt_artifact: Mapping[str, Any]) -> str`), `LocalWorkerAdapterRecord` frozen dataclass — Task 4 adds `run_local_worker_adapter` beside them.

- [ ] **Step 1: Write the failing record tests**

Create `mcp_server/tests/test_local_worker_adapter.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_adapter.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'rook.agent.local_worker_adapter'`.

- [ ] **Step 3: Implement the record module**

Create `mcp_server/src/rook/agent/local_worker_adapter.py`:

```python
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
```

(`run_local_worker_adapter` and its helpers arrive in Task 4; `json`,
`render_local_worker_prompt_artifact`, and
`load_local_worker_turn_response_payload` imports are placed now so the module
is complete after Task 4 without touching the import block. `__all__` already
names `run_local_worker_adapter`; the Task 3 test run does not import it, so
this is safe.)

- [ ] **Step 4: Run tests to verify they pass**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_adapter.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git -C C:\UDEV\Rook-lm5j add mcp_server/src/rook/agent/local_worker_adapter.py mcp_server/tests/test_local_worker_adapter.py
git -C C:\UDEV\Rook-lm5j commit -m "feat(lm5j): adapter record types and coherence validation"
```

---

### Task 4: `run_local_worker_adapter` and the failure taxonomy

**Files:**
- Modify: `mcp_server/src/rook/agent/local_worker_adapter.py` (append functions)
- Modify: `mcp_server/tests/test_local_worker_adapter.py` (append tests)

**Interfaces:**
- Consumes: Task 1's renderer, Task 3's record types, LM5G's `load_local_worker_turn_response_payload(payload: Mapping) -> LocalWorkerTurnResponse` (raises `TypeError`/`ValueError` on rejection).
- Produces: `run_local_worker_adapter(request_payload: Mapping[str, Any], transport: LocalWorkerTransport) -> LocalWorkerAdapterRecord` — Task 5's integration test and LM5K both consume exactly this.

- [ ] **Step 1: Append the failing adapter-flow tests**

Append to `mcp_server/tests/test_local_worker_adapter.py`. Test files are self-contained in this repo, so the context fixture is duplicated: copy the entire `_context()` function **character-for-character from Task 1 Step 1 of this plan** (the 100-line `LocalWorkerTurnContext(...)` builder starting `def _context() -> LocalWorkerTurnContext:`) into the position marked below, then add the rest:

```python
from rook.agent.local_worker_adapter import run_local_worker_adapter
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


# ... paste _context() here verbatim from test_local_worker_prompt_artifact.py ...


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
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_adapter.py -v
```

Expected: FAIL — `ImportError: cannot import name 'run_local_worker_adapter'`.

- [ ] **Step 3: Append the adapter implementation**

Append to `mcp_server/src/rook/agent/local_worker_adapter.py`:

```python
def run_local_worker_adapter(
    request_payload: Mapping[str, Any],
    transport: LocalWorkerTransport,
) -> LocalWorkerAdapterRecord:
    prompt_artifact = render_local_worker_prompt_artifact(request_payload)
    send = getattr(transport, "send", None)
    if not callable(send):
        raise TypeError(
            "transport must provide a callable send(prompt_artifact)"
        )
    try:
        raw_output = send(prompt_artifact)
    except TransportError:
        return _failure_record("transport_error", "transport_error:declared", None)
    except Exception as exc:  # noqa: BLE001 — deliberate Exception-only boundary
        return _failure_record(
            "transport_error",
            "transport_error:unexpected:" + _safe_detail(type(exc).__name__),
            None,
        )
    if not isinstance(raw_output, str):
        return _failure_record(
            "raw_output_invalid",
            "raw_output_invalid:not_text:" + _safe_detail(type(raw_output).__name__),
            None,
        )
    excerpt = _excerpt(raw_output)
    text = raw_output.strip()
    if not text:
        return _failure_record(
            "raw_output_invalid", "raw_output_invalid:empty", excerpt
        )
    try:
        parsed = json.loads(text)
    except ValueError:
        return _failure_record(
            "raw_output_invalid", "raw_output_invalid:json_decode", excerpt
        )
    if not isinstance(parsed, Mapping):
        return _failure_record(
            "raw_output_invalid", "raw_output_invalid:not_mapping", excerpt
        )
    try:
        response = load_local_worker_turn_response_payload(parsed)
    except (TypeError, ValueError) as exc:
        return _failure_record(
            "response_payload_invalid",
            "response_payload_invalid:" + _safe_detail(str(exc)),
            excerpt,
        )
    return LocalWorkerAdapterRecord(
        schema=LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
        status="response_loaded",
        prompt_schema=LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        prompt_text_version=LOCAL_WORKER_PROMPT_TEXT_VERSION,
        response=response,
        failure_reason=None,
        raw_output_excerpt=None,
    )


def _failure_record(
    status: AdapterStatus,
    failure_reason: str,
    raw_output_excerpt: str | None,
) -> LocalWorkerAdapterRecord:
    return LocalWorkerAdapterRecord(
        schema=LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
        status=status,
        prompt_schema=LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        prompt_text_version=LOCAL_WORKER_PROMPT_TEXT_VERSION,
        response=None,
        failure_reason=failure_reason,
        raw_output_excerpt=raw_output_excerpt,
    )


def _excerpt(raw_output: str) -> str | None:
    text = raw_output[:RAW_OUTPUT_EXCERPT_LIMIT]
    cleaned = "".join(
        ch if ch == " " or ch.isprintable() else "_" for ch in text
    )
    return cleaned if cleaned else None


def _safe_detail(value: str) -> str:
    cleaned = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch == "_")) else "_"
        for ch in value[:_DETAIL_LIMIT]
    )
    detail = cleaned.strip("_")
    return detail if detail else "unclassified"
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_adapter.py -v
```

Expected: all PASS. Two exact-string assertions to watch: `test_lm5g_rejection_is_response_payload_invalid` pins sanitized prefixes of LM5G's actual messages (`unsupported local worker turn response schema: ...` and `unknown local worker response kind: ...` — see `local_worker_turn_response.py:201,216`); if either assertion fails, fix the test's expected prefix to the sanitizer's true output, never the LM5G message.

- [ ] **Step 5: Commit**

```powershell
git -C C:\UDEV\Rook-lm5j add mcp_server/src/rook/agent/local_worker_adapter.py mcp_server/tests/test_local_worker_adapter.py
git -C C:\UDEV\Rook-lm5j commit -m "feat(lm5j): bounded adapter invocation with exact failure taxonomy"
```

---

### Task 5: Integration proof and the full gate

**Files:**
- Modify: `mcp_server/tests/test_local_worker_adapter.py` (append the integration test)

**Interfaces:**
- Consumes: everything from Tasks 1–4, plus `compile_workflow_contract` (LM4W), `build_local_worker_turn_context` (LM5A), `run_local_worker_turn` (LM5D: `(context, worker: Callable[[LocalWorkerTurnContext], LocalWorkerTurnResponse]) -> LocalWorkerTurnHarnessRecord`), `LocalWorkerScenarioExpectation`/`evaluate_local_worker_scenario_result` (LM5F).
- Produces: the offline dress rehearsal for LM5K — the probe replaces only `_EnvelopeReadingTransport` with a live provider.

- [ ] **Step 1: Append the integration test**

Append to `mcp_server/tests/test_local_worker_adapter.py`:

```python
from rook.agent.local_worker_scenario_evaluation import (
    LocalWorkerScenarioExpectation,
    evaluate_local_worker_scenario_result,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
from rook.agent.local_worker_turn_context import build_local_worker_turn_context
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


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5j_adapter_contract",
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
                    "name": "LM5JAdapterContract",
                    "x": 350,
                    "y": 1420,
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
                        bindings={"guid": ("repair_anchor", "component_guid")},
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
        metadata={"trace": {"slice": "LM5J"}},
    )


def _compiled_context():
    scaffold = compile_workflow_contract(_repair_contract())
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts["repair_anchor"] = {"component_guid": "component-123"}
    graph.memory.facts["component_guid"] = "component-123"
    return build_local_worker_turn_context(
        scaffold,
        graph,
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script components use body-style code",
                content={"source": "test fixture", "trust": "high"},
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={"type": "object", "required": ["code", "mode"]},
            ),
        ),
    )


class _EnvelopeReadingTransport:
    """Deterministic fake model: reads the allowed action from the prompt
    artifact's user JSON and answers a strict action_request payload."""

    def send(self, prompt_artifact):
        envelope = json.loads(prompt_artifact["messages"][1]["content"])
        actions = envelope["context"]["allowed_actions"]
        action_id = actions[0]["action_id"]
        return json.dumps(
            {
                "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
                "kind": "action_request",
                "action_id": action_id,
                "rationale": "Draft repair parameters for the failed component.",
                "input": {"code": "A = 42.0;", "mode": "body"},
            }
        )


def test_adapter_composes_with_lm4w_lm5a_lm5i_lm5d_and_lm5f() -> None:
    context = _compiled_context()
    request_payload = copy.deepcopy(
        dict(render_local_worker_turn_request_payload(context))
    )

    record = run_local_worker_adapter(request_payload, _EnvelopeReadingTransport())
    assert record.status == "response_loaded"
    assert record.response.payload.action_id == "draft_repair_params"
    assert record.response.payload.action_id != (
        request_payload["context"]["current_node"]["execution_ref"]
    )

    harness_record = run_local_worker_turn(
        context, lambda received: record.response
    )
    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="adapter_contract_offline_chain",
            category="adapter_integration",
            expected_status="completed",
            expected_disposition="candidate_action_request",
            expected_attempt_valid=True,
            expected_action_id="draft_repair_params",
            expected_response_kind="action_request",
            expected_workflow_id=context.workflow.workflow_id,
            expected_contract_fingerprint=context.workflow.contract_fingerprint,
        ),
        harness_record,
    )
    assert harness_record.status == "completed"
    assert result.passed is True
```

- [ ] **Step 2: Run the new test**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_adapter.py::test_adapter_composes_with_lm4w_lm5a_lm5i_lm5d_and_lm5f -v
```

Expected: PASS.

- [ ] **Step 3: Run the full local-worker gate**

```powershell
cd C:\UDEV\Rook-lm5j
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' | Sort-Object Name | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  mcp_server\tests\test_local_worker_prompt_artifact.py `
  mcp_server\tests\test_local_worker_adapter.py
```

Expected: all PASS, zero failures.

- [ ] **Step 4: Static scope checks (exact assertions)**

```powershell
git -C C:\UDEV\Rook-lm5j diff --check origin/main..HEAD
git -C C:\UDEV\Rook-lm5j diff --name-only origin/main..HEAD -- mcp_server/src
```

Expected: `diff --check` clean, and the `--name-only` output is **exactly these
two lines and nothing else** (order as git prints it):

```text
mcp_server/src/rook/agent/local_worker_adapter.py
mcp_server/src/rook/agent/local_worker_prompt_artifact.py
```

Any third line under `mcp_server/src` is a scope violation — stop and remove
the stray change before proceeding.

- [ ] **Step 4b: Python 3.10 compatibility gate**

The package supports Python 3.10+; the venv runtime does not prove 3.10
compatibility, so compile explicitly against 3.10:

```powershell
cd C:\UDEV\Rook-lm5j
py -3.10 -m py_compile mcp_server\src\rook\agent\local_worker_prompt_artifact.py mcp_server\src\rook\agent\local_worker_adapter.py mcp_server\tests\test_local_worker_prompt_artifact.py mcp_server\tests\test_local_worker_adapter.py
```

Expected: silent (exit 0). If `py -3.10` is not installed on this machine,
report that to the user as a blocker for this gate rather than skipping it
silently — do not substitute the venv's interpreter.

- [ ] **Step 5: Commit**

```powershell
git -C C:\UDEV\Rook-lm5j add mcp_server/tests/test_local_worker_adapter.py
git -C C:\UDEV\Rook-lm5j commit -m "test(lm5j): offline adapter chain through LM4W/LM5A/LM5I/LM5D/LM5F"
```

---

## Completion Criteria

- Both new modules exist with exact `__all__` tuples, pinned by tests.
- Every §4.2a failure reason exercised by an exact-string (or pinned-prefix) assertion, **and** the record's `__post_init__` rejects any off-taxonomy reason on direct construction (proved by `test_off_taxonomy_reasons_are_rejected`).
- Production and test code compile under Python 3.10 (`py -3.10 -m py_compile` gate).
- `git diff --name-only origin/main..HEAD -- mcp_server/src` lists exactly the two new modules.
- Fenced/prose/empty/non-mapping/non-text outputs all classified; `BaseException` propagates.
- Mutated `response_contract` fails closed before the transport is invoked.
- Integration test proves the LM4W → LM5A → LM5I → adapter → LM5D → LM5F chain offline.
- Production diff = exactly the two new modules; no live model, provider, or network anywhere.
- Merge remains gated on explicit user approval after review (do not merge from this plan).
