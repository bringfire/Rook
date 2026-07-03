# LM5P Ollama Think + Format Compatibility Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a committed diagnostic spike script that measures direct Ollama `/api/chat` think/format behavior against the real LM5N request envelopes and full LM5 response-union schema.

**Architecture:** LM5P is script-only evidence infrastructure. The script builds real LM5N absent/present prompt artifacts, calls Ollama directly with stdlib HTTP, records bounded local JSONL evidence, and never touches production transport, parser, prompt, evidence packets, or the LM5K runner.

**Tech Stack:** Python 3.10, stdlib `urllib.request`, `urllib.error`, `json`, `argparse`, `subprocess`, `datetime`, `hashlib`, `pathlib`; existing LM5G/LM5I/LM5J public functions; pytest for deterministic script tests.

---

## Scope

Create:

```text
scripts/lm5p_ollama_think_format_spike.py
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
```

Already committed:

```text
docs/superpowers/specs/2026-07-03-lm5p-ollama-think-format-spike-design.md
```

No production module changes:

```text
mcp_server/src/rook/**/*.py
```

No changes to:

```text
scripts/lm5k_worker_probe.py
scripts/lm5o_structured_output_spike.py
mcp_server/tests/test_lm5k_worker_probe.py
local_worker_prompt_artifact.py
local_worker_model_transport.py
local_worker_turn_response.py
local_worker_turn_request.py
docs/superpowers/probes/**/*.md
```

Raw run artifacts remain ignored under:

```text
probe_runs/
```

## Current Code Anchors

Use exactly these existing public helpers:

```python
from rook.agent.local_worker_prompt_artifact import render_local_worker_prompt_artifact
from rook.agent.local_worker_turn_request import render_local_worker_turn_request_payload
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)
```

The script may import only these LM5K probe helpers:

```python
from lm5k_worker_probe import _SCENARIOS, build_probe_context
```

The script must not import or call:

```text
run_probe
run_candidate
_default_transport_factory
LiteLLMWorkerTransport
run_local_worker_adapter
run_local_worker_turn
evaluate_local_worker_scenario_result
requests
httpx
ollama
litellm
```

## Task 1: Script Schema, Modes, Response Schema, And Request Body

**Files:**
- Create: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`
- Create: `scripts/lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_lm5p_ollama_think_format_spike.py` with this initial content:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_script():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm5p_ollama_think_format_spike.py"
    )
    spec = importlib.util.spec_from_file_location(
        "lm5p_ollama_think_format_spike", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SPIKE = _load_script()


def test_mode_table_is_exact() -> None:
    assert SPIKE.DEFAULT_MODELS == ("gemma4:12b-it-qat", "gemma4:12b")
    assert SPIKE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
    assert SPIKE._MODES == {
        "free_default": {"format": False, "think": "omitted"},
        "free_think_true": {"format": False, "think": True},
        "format_default": {"format": True, "think": "omitted"},
        "format_think_true": {"format": True, "think": True},
        "format_think_false": {"format": True, "think": False},
    }


def test_response_union_schema_is_full_lm5_union() -> None:
    schema = SPIKE._response_union_schema()
    assert set(schema) == {"oneOf"}
    assert len(schema["oneOf"]) == 4

    variants = {variant["properties"]["kind"]["const"]: variant for variant in schema["oneOf"]}
    assert set(variants) == {
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    }
    for variant in variants.values():
        assert variant["type"] == "object"
        assert variant["additionalProperties"] is False
        assert variant["properties"]["schema"]["const"] == (
            "rook.local_worker_turn_response:v1"
        )

    assert variants["action_request"]["required"] == [
        "schema",
        "kind",
        "action_id",
        "rationale",
        "input",
    ]
    assert variants["action_request"]["properties"]["input"] == {
        "type": "object"
    }
    assert variants["clarification_request"]["required"] == [
        "schema",
        "kind",
        "question",
        "rationale",
    ]
    assert variants["clarification_request"]["properties"]["rationale"] == {
        "type": ["string", "null"]
    }
    assert variants["refusal"]["required"] == [
        "schema",
        "kind",
        "category",
        "reason",
    ]
    assert variants["refusal"]["properties"]["category"]["enum"] == [
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
    ]
    assert variants["observation"]["required"] == [
        "schema",
        "kind",
        "message",
        "data",
    ]
    assert variants["observation"]["properties"]["data"] == {
        "type": ["object", "null"]
    }


def test_request_body_omits_format_and_think_for_free_default() -> None:
    body = SPIKE._build_request_body(
        model="gemma4:12b",
        messages=[{"role": "user", "content": "hello"}],
        mode_name="free_default",
        temperature=0.0,
    )
    assert body == {
        "model": "gemma4:12b",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "options": {"temperature": 0.0},
    }


def test_request_body_sets_think_true_without_format() -> None:
    body = SPIKE._build_request_body(
        model="gemma4:12b",
        messages=[{"role": "user", "content": "hello"}],
        mode_name="free_think_true",
        temperature=0.0,
    )
    assert "format" not in body
    assert body["think"] is True


def test_request_body_sets_format_and_think_false() -> None:
    body = SPIKE._build_request_body(
        model="gemma4:12b",
        messages=[{"role": "user", "content": "hello"}],
        mode_name="format_think_false",
        temperature=0.0,
    )
    assert body["format"]["oneOf"]
    assert body["think"] is False
    body["format"]["oneOf"].append({"bad": True})
    second = SPIKE._build_request_body(
        model="gemma4:12b",
        messages=[{"role": "user", "content": "hello"}],
        mode_name="format_think_false",
        temperature=0.0,
    )
    assert len(second["format"]["oneOf"]) == 4


def test_request_body_rejects_unknown_mode() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown LM5P mode"):
        SPIKE._build_request_body(
            model="gemma4:12b",
            messages=[{"role": "user", "content": "hello"}],
            mode_name="bad_mode",
            temperature=0.0,
        )
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
ERROR ... FileNotFoundError ... lm5p_ollama_think_format_spike.py
```

- [ ] **Step 3: Add the minimal script scaffold**

Create `scripts/lm5p_ollama_think_format_spike.py`:

```python
#!/usr/bin/env python
"""LM5P direct Ollama think/format compatibility spike.

Manual diagnostic only. Writes bounded local evidence under probe_runs/.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_SCHEMA = "rook.lm5p_ollama_think_format_spike:v1"
DEFAULT_MODELS = ("gemma4:12b-it-qat", "gemma4:12b")
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 1
DEFAULT_TEMPERATURE = 0.0
EXCERPT_CHARS = 500

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lm5k_worker_probe import _SCENARIOS, build_probe_context  # noqa: E402
from rook.agent.local_worker_prompt_artifact import (  # noqa: E402
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_request import (  # noqa: E402
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import (  # noqa: E402
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)

_MODES = {
    "free_default": {"format": False, "think": "omitted"},
    "free_think_true": {"format": False, "think": True},
    "format_default": {"format": True, "think": "omitted"},
    "format_think_true": {"format": True, "think": True},
    "format_think_false": {"format": True, "think": False},
}


def _response_union_schema() -> dict[str, Any]:
    def schema_prop() -> dict[str, str]:
        return {"const": LOCAL_WORKER_TURN_RESPONSE_SCHEMA}

    return {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "action_id", "rationale", "input"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "action_request"},
                    "action_id": {"type": "string"},
                    "rationale": {"type": "string"},
                    "input": {"type": "object"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "question", "rationale"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "clarification_request"},
                    "question": {"type": "string"},
                    "rationale": {"type": ["string", "null"]},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "category", "reason"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "refusal"},
                    "category": {
                        "enum": [
                            "unsafe",
                            "insufficient_context",
                            "unsupported_action",
                            "out_of_scope",
                        ]
                    },
                    "reason": {"type": "string"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "message", "data"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "observation"},
                    "message": {"type": "string"},
                    "data": {"type": ["object", "null"]},
                },
            },
        ]
    }


def _build_request_body(
    *,
    model: str,
    messages: Sequence[Mapping[str, str]],
    mode_name: str,
    temperature: float,
) -> dict[str, Any]:
    try:
        mode = _MODES[mode_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P mode: {mode_name}") from exc

    body: dict[str, Any] = {
        "model": model,
        "messages": [dict(message) for message in messages],
        "stream": False,
        "options": {"temperature": temperature},
    }
    if mode["format"]:
        body["format"] = copy.deepcopy(_response_union_schema())
    if mode["think"] != "omitted":
        body["think"] = mode["think"]
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LM5P direct Ollama think/format compatibility spike."
    )
    parser.parse_args(argv)
    print("LM5P scaffold only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "test(lm5p): add Ollama think format spike scaffold"
```

## Task 2: Real LM5N Prompt Envelopes And Static Boundary Guard

**Files:**
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`
- Modify: `scripts/lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Add failing tests for real envelopes and guard**

Append these tests:

```python
def test_prompt_messages_use_real_lm5n_absent_envelope() -> None:
    messages = SPIKE._messages_for_scenario("evidence_absent_like")
    assert [message["role"] for message in messages] == ["system", "user"]
    envelope = json.loads(messages[1]["content"])
    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    context = envelope["context"]
    assert context["current_node"]["node_id"] == "repair_same_component"
    packet_ids = [packet["packet_id"] for packet in context["knowledge"]]
    assert packet_ids == ["script_body_gotcha"]
    assert context["current_node"]["has_execution_params"] is False


def test_prompt_messages_use_real_lm5n_present_envelope() -> None:
    messages = SPIKE._messages_for_scenario("evidence_present_like")
    envelope = json.loads(messages[1]["content"])
    context = envelope["context"]
    packet_ids = [packet["packet_id"] for packet in context["knowledge"]]
    assert packet_ids == ["script_body_gotcha", "lm5n_repair_evidence"]
    evidence = context["knowledge"][1]
    assert evidence["kind"] == "evidence"
    assert evidence["content"]["state"] == "post_verify_pre_bind"


def test_prompt_messages_reject_unknown_scenario() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown LM5P scenario"):
        SPIKE._messages_for_scenario("bad_scenario")


def test_static_guard_forbids_runner_adapter_and_non_stdlib_http() -> None:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(SPIKE))
    imported_modules = set()
    imported_names = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    assert not {"requests", "httpx", "ollama", "litellm"} & imported_modules
    forbidden_names = {
        "run_probe",
        "run_candidate",
        "_default_transport_factory",
        "LiteLLMWorkerTransport",
        "run_local_worker_adapter",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
    }
    assert not forbidden_names & imported_names
    assert not forbidden_names & called_names
    assert {"_SCENARIOS", "build_probe_context"} <= imported_names
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
FAILED ... AttributeError: module 'lm5p_ollama_think_format_spike' has no attribute '_messages_for_scenario'
```

- [ ] **Step 3: Implement real LM5N prompt artifact rendering**

Add this function after `_build_request_body`:

```python
def _messages_for_scenario(scenario_name: str) -> list[dict[str, str]]:
    scenario_map = {
        "evidence_absent_like": _SCENARIOS["evidence_absent"],
        "evidence_present_like": _SCENARIOS["evidence_present"],
    }
    try:
        scenario = scenario_map[scenario_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P scenario: {scenario_name}") from exc

    context = build_probe_context(scenario)
    request_payload = render_local_worker_turn_request_payload(context)
    artifact = render_local_worker_prompt_artifact(request_payload)
    messages = artifact["messages"]
    if not isinstance(messages, list):
        raise TypeError("prompt artifact messages must be a list")
    return [dict(message) for message in messages]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
10 passed
```

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "feat(lm5p): render real LM5N spike prompts"
```

## Task 3: Row Classification, Bounded Evidence, And Hashing

**Files:**
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`
- Modify: `scripts/lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Add failing tests for classification**

Append these tests:

```python
def test_excerpt_and_hash_are_bounded() -> None:
    text = "abcdef" * 120
    assert SPIKE._excerpt(text) == text[:500]
    assert SPIKE._sha256_text(text) == (
        "a774b01707c1f8c098d7f16731417bc41f269298ffb4a896b716ce5829c8ce7d"
    )
    assert SPIKE._excerpt(None) is None
    assert SPIKE._sha256_text(None) is None


def test_classifies_lm5g_loadable_response_with_thinking() -> None:
    provider_text = json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "What repair evidence is available?",
                        "rationale": None,
                    }
                ),
                "thinking": "I should avoid acting without evidence.",
            },
            "prompt_eval_count": 123,
            "eval_count": 45,
            "total_duration": 10,
            "load_duration": 2,
            "prompt_eval_duration": 3,
            "eval_duration": 4,
            "done_reason": "stop",
        }
    )
    row = SPIKE._classify_provider_text(
        provider_text=provider_text,
        base_row={
            "run_id": "run",
            "git_commit": "abc123",
            "ollama_version": "ollama version is 0.0.0",
            "model": "gemma4:12b",
            "model_id": "model-id",
            "model_quantization": "Q4_K_M",
            "scenario": "evidence_absent_like",
            "mode": "format_think_true",
            "attempt_index": 0,
            "format_enabled": True,
            "think_requested": "true",
        },
    )
    assert row["provider_status"] == "ok"
    assert row["provider_json_valid"] is True
    assert row["content_json_valid"] is True
    assert row["content_is_mapping"] is True
    assert row["schema_literal"] == "rook.local_worker_turn_response:v1"
    assert row["lm5g_loadable"] is True
    assert row["response_kind"] == "clarification_request"
    assert row["thinking_present"] is True
    assert row["thinking_chars"] == len("I should avoid acting without evidence.")
    assert row["prompt_eval_count"] == 123
    assert row["eval_count"] == 45
    assert row["done_reason"] == "stop"
    assert row["failure_reason"] is None


def test_classifies_provider_json_failure() -> None:
    row = SPIKE._classify_provider_text(
        provider_text="{not json",
        base_row={
            "run_id": "run",
            "git_commit": "abc123",
            "ollama_version": "ollama version is 0.0.0",
            "model": "gemma4:12b",
            "model_id": None,
            "model_quantization": None,
            "scenario": "evidence_present_like",
            "mode": "free_default",
            "attempt_index": 0,
            "format_enabled": False,
            "think_requested": "omitted",
        },
    )
    assert row["provider_status"] == "error"
    assert row["provider_json_valid"] is False
    assert row["failure_reason"] == "provider_json_invalid:JSONDecodeError"


def test_classifies_free_text_content_as_non_failure_evidence() -> None:
    row = SPIKE._classify_provider_text(
        provider_text=json.dumps({"message": {"content": "not json"}}),
        base_row={
            "run_id": "run",
            "git_commit": "abc123",
            "ollama_version": "ollama version is 0.0.0",
            "model": "gemma4:12b",
            "model_id": None,
            "model_quantization": None,
            "scenario": "evidence_present_like",
            "mode": "free_default",
            "attempt_index": 0,
            "format_enabled": False,
            "think_requested": "omitted",
        },
    )
    assert row["provider_status"] == "ok"
    assert row["provider_json_valid"] is True
    assert row["content_json_valid"] is False
    assert row["lm5g_loadable"] is False
    assert row["failure_reason"] == "content_json_invalid:JSONDecodeError"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
FAILED ... AttributeError ... _classify_provider_text
```

- [ ] **Step 3: Implement classification helpers**

Add these helpers after `_messages_for_scenario`:

```python
def _excerpt(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:EXCERPT_CHARS]


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _empty_result_fields() -> dict[str, Any]:
    return {
        "provider_status": "ok",
        "provider_json_valid": False,
        "content_json_valid": False,
        "content_is_mapping": False,
        "schema_literal": None,
        "lm5g_loadable": False,
        "response_kind": None,
        "message_content_excerpt": None,
        "message_content_sha256": None,
        "thinking_present": False,
        "thinking_chars": 0,
        "thinking_excerpt": None,
        "thinking_sha256": None,
        "prompt_eval_count": None,
        "eval_count": None,
        "total_duration": None,
        "load_duration": None,
        "prompt_eval_duration": None,
        "eval_duration": None,
        "done_reason": None,
        "failure_reason": None,
    }


def _classify_provider_text(
    *,
    provider_text: str,
    base_row: Mapping[str, Any],
) -> dict[str, Any]:
    row = {**base_row, **_empty_result_fields()}
    try:
        provider_payload = json.loads(provider_text)
    except json.JSONDecodeError as exc:
        row["provider_status"] = "error"
        row["provider_json_valid"] = False
        row["failure_reason"] = f"provider_json_invalid:{type(exc).__name__}"
        return row

    if not isinstance(provider_payload, Mapping):
        row["provider_status"] = "error"
        row["provider_json_valid"] = False
        row["failure_reason"] = "provider_json_invalid:not_mapping"
        return row

    row["provider_json_valid"] = True
    message = provider_payload.get("message")
    if not isinstance(message, Mapping):
        row["failure_reason"] = "message_missing"
        return row

    content = message.get("content")
    if isinstance(content, str):
        row["message_content_excerpt"] = _excerpt(content)
        row["message_content_sha256"] = _sha256_text(content)
    thinking = message.get("thinking")
    if isinstance(thinking, str) and thinking:
        row["thinking_present"] = True
        row["thinking_chars"] = len(thinking)
        row["thinking_excerpt"] = _excerpt(thinking)
        row["thinking_sha256"] = _sha256_text(thinking)

    for key in (
        "prompt_eval_count",
        "eval_count",
        "total_duration",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
        "done_reason",
    ):
        row[key] = provider_payload.get(key)

    if not isinstance(content, str) or not content:
        row["failure_reason"] = "content_missing"
        return row
    try:
        parsed_content = json.loads(content)
    except json.JSONDecodeError as exc:
        row["content_json_valid"] = False
        row["failure_reason"] = f"content_json_invalid:{type(exc).__name__}"
        return row

    row["content_json_valid"] = True
    row["content_is_mapping"] = isinstance(parsed_content, Mapping)
    if isinstance(parsed_content, Mapping):
        schema_literal = parsed_content.get("schema")
        row["schema_literal"] = schema_literal if isinstance(schema_literal, str) else None
        kind = parsed_content.get("kind")
        row["response_kind"] = kind if isinstance(kind, str) else None
        try:
            load_local_worker_turn_response_payload(parsed_content)
        except (TypeError, ValueError) as exc:
            row["lm5g_loadable"] = False
            row["failure_reason"] = f"lm5g_load_failed:{type(exc).__name__}"
            return row
        row["lm5g_loadable"] = True
        row["failure_reason"] = None
        return row

    row["failure_reason"] = "content_json_not_mapping"
    return row
```

Run this one-off command to confirm the expected SHA in the first test:

```powershell
.\mcp_server\.venv\Scripts\python.exe - <<'PY'
import hashlib
text = "abcdef" * 120
print(hashlib.sha256(text.encode("utf-8")).hexdigest())
PY
```

Expected:

```text
a774b01707c1f8c098d7f16731417bc41f269298ffb4a896b716ce5829c8ce7d
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
14 passed
```

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "feat(lm5p): classify Ollama spike responses"
```

## Task 4: CLI, Run Directory, Manifest, Metadata, And Direct HTTP Loop

**Files:**
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`
- Modify: `scripts/lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Add failing tests for manifest and local run loop**

Append these tests:

```python
def test_parse_show_metadata_extracts_model_id_and_quantization() -> None:
    text = """
    Model
      architecture        gemma3
      parameters          12.2B
      quantization        Q4_K_M

    Details
      model id            abcdef123456
    """
    assert SPIKE._parse_show_metadata(text) == {
        "model_id": "abcdef123456",
        "model_quantization": "Q4_K_M",
    }


def test_build_manifest_records_structured_model_metadata(tmp_path) -> None:
    manifest = SPIKE._build_manifest(
        run_id="lm5p-20260703T000000Z-abc123",
        git_commit="abc123",
        ollama_version="ollama version is 0.9.0",
        models=[
            {
                "model": "gemma4:12b",
                "model_id": "id1",
                "model_quantization": "Q4_K_M",
                "ollama_show_status": "ok",
                "ollama_show_excerpt": "model id id1",
            }
        ],
        attempts_per_cell=1,
        endpoint="http://localhost:11434/api/chat",
        temperature=0.0,
    )
    assert manifest["script_schema"] == "rook.lm5p_ollama_think_format_spike:v1"
    assert manifest["git_commit"] == "abc123"
    assert manifest["models"] == [
        {
            "model": "gemma4:12b",
            "model_id": "id1",
            "model_quantization": "Q4_K_M",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "model id id1",
        }
    ]
    assert manifest["scenarios"] == [
        "evidence_absent_like",
        "evidence_present_like",
    ]
    assert manifest["modes"] == list(SPIKE._MODES)
    assert manifest["raw_artifacts"] == "local evidence under probe_runs; do not commit"


def test_run_matrix_writes_attempt_rows_and_manifest(tmp_path, monkeypatch) -> None:
    provider_response = json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "noted",
                        "data": None,
                    }
                )
            },
            "eval_count": 7,
        }
    )
    calls = []

    def fake_post_json(endpoint, body, timeout_s):
        calls.append((endpoint, body, timeout_s))
        return provider_response

    monkeypatch.setattr(SPIKE, "_post_ollama_chat", fake_post_json)
    monkeypatch.setattr(SPIKE, "_git_short_sha", lambda: "abc123")
    monkeypatch.setattr(SPIKE, "_ollama_version", lambda: "ollama version is 0.9.0")
    monkeypatch.setattr(
        SPIKE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": model + "-id",
            "model_quantization": "Q4_K_M",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "show",
        },
    )
    monkeypatch.setattr(
        SPIKE,
        "_messages_for_scenario",
        lambda scenario: [{"role": "user", "content": scenario}],
    )

    run_dir = SPIKE._run_matrix(
        models=("gemma4:12b",),
        scenario_names=("evidence_absent_like",),
        mode_names=("format_think_true",),
        attempts=2,
        endpoint="http://localhost:11434/api/chat",
        temperature=0.0,
        timeout_s=15.0,
        run_root=tmp_path,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["git_commit"] == "abc123"
    assert manifest["models"][0]["model"] == "gemma4:12b"
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["model"] == "gemma4:12b"
    assert first["mode"] == "format_think_true"
    assert first["format_enabled"] is True
    assert first["think_requested"] == "true"
    assert first["lm5g_loadable"] is True
    assert first["response_kind"] == "observation"
    assert calls[0][1]["format"]["oneOf"]
    assert calls[0][1]["think"] is True
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
FAILED ... AttributeError ... _run_matrix
```

- [ ] **Step 3: Implement metadata, HTTP, manifest, matrix, and CLI**

Add these helpers after `_classify_provider_text`:

```python
def _git_short_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        sha = out.stdout.strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def _ollama_version() -> str:
    try:
        out = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        value = out.stdout.strip() or out.stderr.strip()
        return value if value else "unknown"
    except Exception as exc:
        return f"unavailable:{type(exc).__name__}"


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    wanted = {label.lower() for label in labels}
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        for label in wanted:
            if lower.startswith(label):
                value = stripped[len(label):].strip()
                return value or None
    return None


def _parse_show_metadata(text: str) -> dict[str, str | None]:
    return {
        "model_id": _extract_labeled_value(text, ("model id", "model_id", "id")),
        "model_quantization": _extract_labeled_value(
            text, ("quantization", "quantization level")
        ),
    }


def _model_metadata(model: str) -> dict[str, Any]:
    try:
        out = subprocess.run(
            ["ollama", "show", model],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return {
            "model": model,
            "model_id": None,
            "model_quantization": None,
            "ollama_show_status": f"error:{type(exc).__name__}",
            "ollama_show_excerpt": None,
        }
    text = out.stdout if out.returncode == 0 else (out.stdout + out.stderr)
    parsed = _parse_show_metadata(text)
    return {
        "model": model,
        "model_id": parsed["model_id"],
        "model_quantization": parsed["model_quantization"],
        "ollama_show_status": "ok" if out.returncode == 0 else f"exit:{out.returncode}",
        "ollama_show_excerpt": _excerpt(text),
    }


def _post_ollama_chat(endpoint: str, body: Mapping[str, Any], timeout_s: float) -> str:
    data = json.dumps(dict(body)).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8")


def _build_manifest(
    *,
    run_id: str,
    git_commit: str,
    ollama_version: str,
    models: Sequence[Mapping[str, Any]],
    attempts_per_cell: int,
    endpoint: str,
    temperature: float,
) -> dict[str, Any]:
    return {
        "script_schema": SCRIPT_SCHEMA,
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "ollama_version": ollama_version,
        "models": [dict(model) for model in models],
        "scenarios": list(SCENARIO_NAMES),
        "modes": list(_MODES),
        "attempts_per_cell": attempts_per_cell,
        "endpoint": endpoint,
        "temperature": temperature,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _base_row(
    *,
    run_id: str,
    git_commit: str,
    ollama_version: str,
    model_info: Mapping[str, Any],
    scenario: str,
    mode: str,
    attempt_index: int,
) -> dict[str, Any]:
    mode_config = _MODES[mode]
    think = mode_config["think"]
    return {
        "run_id": run_id,
        "git_commit": git_commit,
        "ollama_version": ollama_version,
        "model": model_info["model"],
        "model_id": model_info["model_id"],
        "model_quantization": model_info["model_quantization"],
        "scenario": scenario,
        "mode": mode,
        "attempt_index": attempt_index,
        "format_enabled": bool(mode_config["format"]),
        "think_requested": (
            "omitted" if think == "omitted" else str(think).lower()
        ),
    }


def _run_matrix(
    *,
    models: Sequence[str],
    scenario_names: Sequence[str],
    mode_names: Sequence[str],
    attempts: int,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    run_root: Path,
) -> Path:
    git_commit = _git_short_sha()
    run_id = (
        "lm5p-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + git_commit
    )
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    ollama_version = _ollama_version()
    model_infos = [_model_metadata(model) for model in models]
    manifest = _build_manifest(
        run_id=run_id,
        git_commit=git_commit,
        ollama_version=ollama_version,
        models=model_infos,
        attempts_per_cell=attempts,
        endpoint=endpoint,
        temperature=temperature,
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    attempts_path = run_dir / "attempts.jsonl"
    counts: Counter[tuple[str, str, str, str | None]] = Counter()
    for model_info in model_infos:
        for scenario in scenario_names:
            messages = _messages_for_scenario(scenario)
            for mode in mode_names:
                for index in range(attempts):
                    base = _base_row(
                        run_id=run_id,
                        git_commit=git_commit,
                        ollama_version=ollama_version,
                        model_info=model_info,
                        scenario=scenario,
                        mode=mode,
                        attempt_index=index,
                    )
                    body = _build_request_body(
                        model=model_info["model"],
                        messages=messages,
                        mode_name=mode,
                        temperature=temperature,
                    )
                    try:
                        provider_text = _post_ollama_chat(endpoint, body, timeout_s)
                    except urllib.error.HTTPError as exc:
                        row = {**base, **_empty_result_fields()}
                        row["provider_status"] = "error"
                        row["failure_reason"] = f"http_error:{exc.code}"
                    except Exception as exc:
                        row = {**base, **_empty_result_fields()}
                        row["provider_status"] = "error"
                        row["failure_reason"] = f"provider_error:{type(exc).__name__}"
                    else:
                        row = _classify_provider_text(
                            provider_text=provider_text,
                            base_row=base,
                        )
                    counts[
                        (
                            row["model"],
                            row["scenario"],
                            row["mode"],
                            row["response_kind"],
                        )
                    ] += 1
                    with attempts_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row) + "\n")

    print(f"run: {run_dir}")
    for (model, scenario, mode, kind), count in sorted(counts.items()):
        print(f"{model:24} {scenario:22} {mode:18} {kind or '-':24} {count}")
    return run_dir
```

Replace `main` and add CLI parsing:

```python
def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("attempts must be positive")
    return number


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5P direct Ollama think/format compatibility spike."
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--run-root", type=Path, default=Path("probe_runs"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    models = tuple(args.models) if args.models else DEFAULT_MODELS
    try:
        _run_matrix(
            models=models,
            scenario_names=SCENARIO_NAMES,
            mode_names=tuple(_MODES),
            attempts=args.attempts,
            endpoint=args.endpoint,
            temperature=args.temperature,
            timeout_s=args.timeout_s,
            run_root=args.run_root,
        )
    except Exception as exc:
        print(f"LM5P spike setup failed: {type(exc).__name__}: {exc}")
        return 1
    return 0
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
17 passed
```

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "feat(lm5p): write direct Ollama spike evidence"
```

## Task 5: Verification And Manual Spike Gate

**Files:**
- Verify: `scripts/lm5p_ollama_think_format_spike.py`
- Verify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Run targeted deterministic tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5p_ollama_think_format_spike.py -q
```

Expected:

```text
17 passed
```

- [ ] **Step 2: Run nearby probe/transport tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Expected:

```text
all tests passed
```

The expected total is the sum of the current LM5P, LM5O transport, and LM5K probe tests. Do not run the full repository suite.

- [ ] **Step 3: Run Python 3.10 compile check**

Run:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py
```

Expected:

```text
no output
```

- [ ] **Step 4: Run static scope checks**

Run:

```powershell
cd C:\UDEV\Rook
git diff --name-only main..HEAD
```

Expected output is exactly:

```text
docs/superpowers/specs/2026-07-03-lm5p-ollama-think-format-spike-design.md
docs/superpowers/plans/2026-07-03-lm5p-ollama-think-format-spike.md
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
scripts/lm5p_ollama_think_format_spike.py
```

Run:

```powershell
git diff --check main..HEAD
```

Expected:

```text
no output
```

Run:

```powershell
git diff -U0 main..HEAD -- scripts\lm5p_ollama_think_format_spike.py |
  rg "litellm|requests|httpx|from ollama|import ollama|run_probe|run_candidate|_default_transport_factory|LiteLLMWorkerTransport|run_local_worker_adapter|run_local_worker_turn|evaluate_local_worker_scenario_result"
```

Expected:

```text
no output
```

- [ ] **Step 5: Manual Ollama preflight**

Run:

```powershell
cd C:\UDEV\Rook
ollama --version
ollama list
ollama show gemma4:12b-it-qat
ollama show gemma4:12b
```

Expected:

```text
ollama --version prints a version
ollama list includes gemma4:12b-it-qat and gemma4:12b
ollama show succeeds for both models
```

If either model is missing, stop and report the missing model. Do not rewrite the script to infer another model.

- [ ] **Step 6: Run the live/manual LM5P spike**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5p_ollama_think_format_spike.py
```

Expected:

```text
prints a run directory under probe_runs\lm5p-...
prints compact count rows by model, scenario, mode, and response kind
exits with code 0 unless setup fails
```

Mechanism failure that must be reported exactly:

```text
provider_error:<ClassName>
http_error:<status>
provider_json_invalid:<ClassName>
unable to build LM5N request envelopes
```

Content JSON failures and LM5G loader failures are evidence rows, not task failures.

- [ ] **Step 7: Inspect local evidence without committing it**

Run:

```powershell
cd C:\UDEV\Rook
$latest = Get-ChildItem probe_runs -Directory -Filter "lm5p-*" |
  Sort-Object Name |
  Select-Object -Last 1
$latest.FullName
Get-Content ($latest.FullName + "\manifest.json") -Raw
Get-Content ($latest.FullName + "\attempts.jsonl") |
  Select-Object -First 5
```

Report:

```text
run directory
git commit
ollama version
models with model_id and model_quantization fields
attempt rows count
mode-by-mode response_kind counts
whether message.thinking appeared
whether format_think_true produced LM5G-loadable content
whether format_default and format_think_false show collapsed eval_count relative to free modes
```

Do not commit `probe_runs/`.

- [ ] **Step 8: Confirm ignored artifacts remain untracked**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --ignored
git diff --name-only --cached
```

Expected:

```text
probe_runs/ appears only as ignored output if shown
git diff --name-only --cached does not include probe_runs
```

- [ ] **Step 9: Commit Task 5 only if verification text changed code or tests**

If Task 5 produced no source changes, do not create a commit.

If a deterministic bug fix was required in `scripts/lm5p_ollama_think_format_spike.py` or `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`, run the targeted gates again and commit:

```powershell
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "fix(lm5p): tighten Ollama spike evidence capture"
```

## Completion Summary Required From Executor

Report:

```text
commits made after the spec/plan commits
targeted test result
nearby test result
Python 3.10 compile result
scope diff
manual spike run directory
Ollama version
model metadata availability
thinking_present counts by model/scenario/mode
lm5g_loadable counts by model/scenario/mode
response_kind counts by model/scenario/mode
failure_reason counts
confirmation that probe_runs artifacts are ignored and uncommitted
```

Do not update the curated probe evidence doc during LM5P implementation. That happens only after the spike results are reviewed.

## Self-Review Notes

Spec coverage:

```text
direct stdlib Ollama /api/chat: Task 4
real LM5N prompt envelopes: Task 2
full LM5 response union schema: Task 1
five-mode matrix: Task 1 and Task 4
bounded JSONL evidence: Task 3 and Task 4
structured manifest model metadata: Task 4
continue across provider errors: Task 4
manual live spike gate: Task 5
no production/runner/parser/prompt changes: Scope and Task 5
```

Placeholder scan:

```text
No placeholder steps.
No action-only schema.
No parser leniency.
No raw artifact commit.
```

Type consistency:

```text
_MODES uses "format" and "think".
Rows use think_requested values "omitted", "true", "false".
Manifest models are structured mappings with model_id and model_quantization.
```
