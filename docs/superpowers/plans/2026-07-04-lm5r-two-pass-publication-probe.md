# LM5R Two-Pass Publication Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostic two-pass Ollama probe that separates free worker decision from constrained LM5G publication.

**Architecture:** Add a new sibling script, `scripts/lm5r_two_pass_publication_probe.py`, plus deterministic tests. The script reuses the real LM5N request envelopes, asks Gemma for a free pass-1 decision, then asks the same model to publish that decision through a single-kind schema. It writes local ignored evidence under `probe_runs/` and makes no production `mcp_server/src` changes.

**Tech Stack:** Python 3.10-compatible script code, stdlib `argparse`/`json`/`urllib`, pytest, direct Ollama REST, existing LM5I/J/G public functions.

---

## File Structure

Create:

```text
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
docs/superpowers/plans/2026-07-04-lm5r-two-pass-publication-probe.md
```

Already committed spec:

```text
docs/superpowers/specs/2026-07-04-lm5r-two-pass-publication-probe-design.md
```

Do not modify:

```text
mcp_server/src/rook/**/*.py
scripts/lm5k_worker_probe.py
scripts/lm5p_ollama_think_format_spike.py
docs/superpowers/probes/*.md
```

`probe_runs/` artifacts are local evidence only and must remain untracked.

---

## Task 1: Script Scaffold, CLI, and Real Scenario Prompts

**Files:**
- Create: `scripts/lm5r_two_pass_publication_probe.py`
- Create: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Write the initial test scaffold**

Create `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`:

```python
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm5r_two_pass_publication_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm5r_two_pass_publication_probe",
        path,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_script()
```

Add constants and argument tests:

```python
def test_constants_are_pinned() -> None:
    assert PROBE.SCRIPT_SCHEMA == "rook.lm5r_two_pass_publication_probe:v1"
    assert PROBE.DEFAULT_MODEL == "gemma4:12b-it-qat"
    assert PROBE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
    assert PROBE.DEFAULT_ATTEMPTS == 5
    assert PROBE.DEFAULT_TEMPERATURE == 0
    assert PROBE.EXCERPT_CHARS == 500
    assert PROBE.STATUSES == (
        "pass1_provider_error",
        "pass1_decision_invalid",
        "pass2_provider_error",
        "pass2_lm5g_invalid",
        "pass2_invariant_violation",
        "published",
    )


def test_args_defaults_and_custom_values() -> None:
    defaults = PROBE._args([])
    assert defaults.model == PROBE.DEFAULT_MODEL
    assert defaults.scenarios == list(PROBE.SCENARIO_NAMES)
    assert defaults.attempts == 5
    assert defaults.excerpt_chars == 500

    custom = PROBE._args(
        [
            "--model",
            "gemma4:12b-it-qat",
            "--scenario",
            "evidence_absent_like",
            "--scenario",
            "evidence_present_like",
            "--attempts",
            "5",
            "--excerpt-chars",
            "1200",
        ]
    )
    assert custom.model == "gemma4:12b-it-qat"
    assert custom.scenarios == [
        "evidence_absent_like",
        "evidence_present_like",
    ]
    assert custom.attempts == 5
    assert custom.excerpt_chars == 1200


def test_args_reject_invalid_scenario_and_non_positive_attempts() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--scenario", "missing"])

    with pytest.raises(SystemExit):
        PROBE._args(["--attempts", "0"])
```

Add real scenario prompt tests:

```python
def test_pass1_messages_use_real_lm5n_envelopes() -> None:
    messages, envelope = PROBE._pass1_messages_for_scenario("evidence_absent_like")

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    assert envelope["context"]["current_node"]["node_id"] == "repair_same_component"
    assert [packet["packet_id"] for packet in envelope["context"]["knowledge"]] == [
        "script_body_gotcha"
    ]
    assert "decision JSON object" in messages[-1]["content"]


def test_pass1_messages_evidence_present_include_evidence_packet() -> None:
    _messages, envelope = PROBE._pass1_messages_for_scenario("evidence_present_like")

    assert [packet["packet_id"] for packet in envelope["context"]["knowledge"]] == [
        "script_body_gotcha",
        "lm5n_repair_evidence",
    ]
```

Add help and static guard tests:

```python
def test_script_help_runs_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    python = repo_root / "mcp_server" / ".venv" / "Scripts" / "python.exe"
    result = subprocess.run(
        [str(python), "scripts/lm5r_two_pass_publication_probe.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LM5R two-pass worker publication probe." in result.stdout


def test_script_static_import_and_call_guards() -> None:
    tree = ast.parse(_script_path().read_text(encoding="utf-8"))
    forbidden_modules = {"requests", "httpx", "ollama", "litellm"}
    forbidden_names = {
        "run_probe",
        "run_candidate",
        "_default_transport_factory",
        "LiteLLMWorkerTransport",
        "run_local_worker_adapter",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
    }

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".", 1)[0])
                imported_names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".", 1)[0])
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    assert imported_modules.isdisjoint(forbidden_modules)
    assert imported_names.isdisjoint(forbidden_names)
    assert called_names.isdisjoint(forbidden_names)
    assert {"_SCENARIOS", "build_probe_context"} <= imported_names
```

- [ ] **Step 2: Run the scaffold tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: import failure because `scripts/lm5r_two_pass_publication_probe.py` does not exist.

- [ ] **Step 3: Create the initial script**

Create `scripts/lm5r_two_pass_publication_probe.py`:

```python
#!/usr/bin/env python
"""LM5R direct Ollama two-pass worker publication probe.

Manual live diagnostic only. It renders real LM5N request envelopes, asks
Ollama/Gemma for a free worker decision, then asks the same model to publish
that decision through a single-kind LM5 response schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rook.agent.local_worker_prompt_artifact import (
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)
from lm5k_worker_probe import _SCENARIOS, build_probe_context


SCRIPT_SCHEMA = "rook.lm5r_two_pass_publication_probe:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 5
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
EXCERPT_CHARS = 500

STATUSES = (
    "pass1_provider_error",
    "pass1_decision_invalid",
    "pass2_provider_error",
    "pass2_lm5g_invalid",
    "pass2_invariant_violation",
    "published",
)

RESPONSE_KINDS = (
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
)

_SCENARIO_MAP = {
    "evidence_absent_like": "evidence_absent",
    "evidence_present_like": "evidence_present",
}

_PASS1_DECISION_INSTRUCTION = """\
Return a small decision JSON object for this worker turn.

The object must contain kind. Required per kind:
- action_request: action_id
- clarification_request: question
- refusal: category and reason
- observation: message

Optional fields: rationale, intent, action_input_intent, known_inputs,
data_intent.

Do not return a strict LM5 response envelope in this pass. This pass decides
only. The next pass will publish the chosen kind.
"""


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5R two-pass worker publication probe."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        choices=SCENARIO_NAMES,
        default=None,
    )
    parser.add_argument("--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS)
    parser.add_argument(
        "--excerpt-chars",
        type=_positive_int,
        default=EXCERPT_CHARS,
    )
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)
    if args.scenarios is None:
        args.scenarios = list(SCENARIO_NAMES)
    return args


def _pass1_messages_for_scenario(
    scenario_name: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    try:
        probe_scenario_name = _SCENARIO_MAP[scenario_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5R scenario: {scenario_name}") from exc

    context = build_probe_context(_SCENARIOS[probe_scenario_name])
    request_payload = render_local_worker_turn_request_payload(context)
    prompt_artifact = render_local_worker_prompt_artifact(request_payload)
    messages = [dict(message) for message in prompt_artifact["messages"]]
    messages.append({"role": "user", "content": _PASS1_DECISION_INSTRUCTION})
    return messages, request_payload


def _excerpt(value: str | None, excerpt_chars: int = EXCERPT_CHARS) -> str | None:
    if value is None:
        return None
    return value[:excerpt_chars]


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    _args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run Task 1 tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "test(lm5r): scaffold two-pass probe"
```

---

## Task 2: Pass-1 Decision Extraction and Validation

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Add tests for balanced JSON extraction**

Add these tests:

```python
def test_extract_first_json_object_accepts_surrounding_prose() -> None:
    text = 'before {"kind": "clarification_request", "question": "Need code?"} after'

    assert PROBE._extract_first_json_object(text) == (
        '{"kind": "clarification_request", "question": "Need code?"}'
    )


def test_extract_first_json_object_handles_strings_and_nested_objects() -> None:
    text = 'x {"kind":"action_request","known_inputs":{"code":"A = { value;"},"action_id":"draft_repair_params"} y'

    assert json.loads(PROBE._extract_first_json_object(text)) == {
        "kind": "action_request",
        "known_inputs": {"code": "A = { value;"},
        "action_id": "draft_repair_params",
    }


def test_extract_first_json_object_returns_none_when_absent() -> None:
    assert PROBE._extract_first_json_object("plain prose only") is None
```

- [ ] **Step 2: Add tests for pass-1 decision validation**

Add these tests:

```python
def test_parse_pass1_decision_accepts_minimum_valid_decisions() -> None:
    assert PROBE._parse_pass1_decision(
        '{"kind":"clarification_request","question":"Need code?"}'
    ) == (
        {
            "kind": "clarification_request",
            "question": "Need code?",
        },
        None,
    )
    assert PROBE._parse_pass1_decision(
        '{"kind":"action_request","action_id":"draft_repair_params"}'
    ) == (
        {
            "kind": "action_request",
            "action_id": "draft_repair_params",
        },
        None,
    )
    assert PROBE._parse_pass1_decision(
        '{"kind":"refusal","category":"out_of_scope","reason":"No authority."}'
    )[1] is None
    assert PROBE._parse_pass1_decision(
        '{"kind":"observation","message":"Already terminal."}'
    )[1] is None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("plain prose", "pass1_no_json_object"),
        ("{not json}", "pass1_json_invalid:JSONDecodeError"),
        ('{"kind":"unknown"}', "pass1_unknown_kind"),
        ('{"kind":"action_request"}', "pass1_missing_action_id"),
        ('{"kind":"clarification_request"}', "pass1_missing_question"),
        ('{"kind":"refusal","reason":"No."}', "pass1_missing_refusal_category"),
        ('{"kind":"refusal","category":"out_of_scope"}', "pass1_missing_refusal_reason"),
        ('{"kind":"observation"}', "pass1_missing_observation_message"),
        ('{"kind":"observation","message":"ok","rationale":null}', "pass1_optional_rationale_type_invalid"),
        ('{"kind":"observation","message":"ok","known_inputs":[]}', "pass1_optional_known_inputs_type_invalid"),
        ('{"kind":"action_request","action_id":"draft_repair_params","action_input_intent":[]}', "pass1_optional_action_input_intent_type_invalid"),
        ('{"kind":"observation","message":"ok","data_intent":[]}', "pass1_optional_data_intent_type_invalid"),
        ('{"kind":"observation","message":"ok","rationale":{}}', "pass1_optional_rationale_type_invalid"),
        ('{"kind":"observation","message":"ok","intent":{}}', "pass1_optional_intent_type_invalid"),
    ],
)
def test_parse_pass1_decision_rejects_invalid_shapes(
    content: str,
    reason: str,
) -> None:
    decision, failure_reason = PROBE._parse_pass1_decision(content)

    assert decision is None
    assert failure_reason == reason


def test_parse_pass1_decision_records_recursion_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_recursion(_text: str) -> object:
        raise RecursionError("nested too deeply")

    monkeypatch.setattr(PROBE.json, "loads", raise_recursion)

    decision, failure_reason = PROBE._parse_pass1_decision(
        '{"kind":"clarification_request","question":"Need code?"}'
    )

    assert decision is None
    assert failure_reason == "pass1_json_invalid:RecursionError"
```

- [ ] **Step 3: Run Task 2 tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_extract_first_json_object_accepts_surrounding_prose `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_extract_first_json_object_handles_strings_and_nested_objects `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_extract_first_json_object_returns_none_when_absent `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_parse_pass1_decision_accepts_minimum_valid_decisions `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_parse_pass1_decision_rejects_invalid_shapes `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_parse_pass1_decision_records_recursion_error `
  -q
```

Expected: failures because the extraction and parsing helpers do not exist.

- [ ] **Step 4: Implement balanced extraction and decision validation**

Add these helpers after `_sha256_text`:

```python
def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _optional_string(decision: Mapping[str, Any], key: str) -> bool:
    return key not in decision or isinstance(decision[key], str)


def _optional_mapping_or_string(decision: Mapping[str, Any], key: str) -> bool:
    return (
        key not in decision
        or isinstance(decision[key], str)
        or isinstance(decision[key], Mapping)
    )


def _optional_mapping(decision: Mapping[str, Any], key: str) -> bool:
    return key not in decision or isinstance(decision[key], Mapping)


def _parse_pass1_decision(content: str) -> tuple[dict[str, Any] | None, str | None]:
    object_text = _extract_first_json_object(content)
    if object_text is None:
        return None, "pass1_no_json_object"

    try:
        parsed = json.loads(object_text)
    except (json.JSONDecodeError, RecursionError) as exc:
        return None, f"pass1_json_invalid:{type(exc).__name__}"

    if not isinstance(parsed, Mapping):
        return None, "pass1_decision_not_mapping"

    decision = dict(parsed)
    kind = decision.get("kind")
    if not isinstance(kind, str) or kind not in RESPONSE_KINDS:
        return None, "pass1_unknown_kind"

    if kind == "action_request" and not isinstance(decision.get("action_id"), str):
        return None, "pass1_missing_action_id"
    if kind == "clarification_request" and not isinstance(decision.get("question"), str):
        return None, "pass1_missing_question"
    if kind == "refusal":
        if not isinstance(decision.get("category"), str):
            return None, "pass1_missing_refusal_category"
        if not isinstance(decision.get("reason"), str):
            return None, "pass1_missing_refusal_reason"
    if kind == "observation" and not isinstance(decision.get("message"), str):
        return None, "pass1_missing_observation_message"

    if not _optional_string(decision, "rationale"):
        return None, "pass1_optional_rationale_type_invalid"
    if not _optional_string(decision, "intent"):
        return None, "pass1_optional_intent_type_invalid"
    if not _optional_mapping_or_string(decision, "action_input_intent"):
        return None, "pass1_optional_action_input_intent_type_invalid"
    if not _optional_mapping(decision, "known_inputs"):
        return None, "pass1_optional_known_inputs_type_invalid"
    if not _optional_mapping_or_string(decision, "data_intent"):
        return None, "pass1_optional_data_intent_type_invalid"

    return decision, None
```

- [ ] **Step 5: Run Task 2 tests to verify GREEN**

Run the same selected pytest command. Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5r): validate pass one decisions"
```

---

## Task 3: Single-Kind Publication Schemas and Formatter Prompt

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Add tests for single-kind schemas**

Add tests:

```python
def test_single_kind_schema_action_request_const_pins_kind_and_action_id() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "action_request", "action_id": "draft_repair_params"}
    )

    assert "oneOf" not in schema
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema", "kind", "action_id", "rationale", "input"]
    assert schema["properties"]["schema"]["const"] == "rook.local_worker_turn_response:v1"
    assert schema["properties"]["kind"]["const"] == "action_request"
    assert schema["properties"]["action_id"]["const"] == "draft_repair_params"
    assert schema["properties"]["input"]["type"] == "object"


def test_single_kind_schema_clarification_request_shape() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "clarification_request", "question": "Need code?"}
    )

    assert "oneOf" not in schema
    assert schema["required"] == ["schema", "kind", "question", "rationale"]
    assert schema["properties"]["kind"]["const"] == "clarification_request"
    assert schema["properties"]["question"]["type"] == "string"
    assert schema["properties"]["rationale"]["type"] == ["string", "null"]


def test_single_kind_schema_refusal_const_pins_category() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "refusal", "category": "out_of_scope", "reason": "No authority."}
    )

    assert schema["required"] == ["schema", "kind", "category", "reason"]
    assert schema["properties"]["kind"]["const"] == "refusal"
    assert schema["properties"]["category"]["const"] == "out_of_scope"


def test_single_kind_schema_observation_shape() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "observation", "message": "Done."}
    )

    assert schema["required"] == ["schema", "kind", "message", "data"]
    assert schema["properties"]["kind"]["const"] == "observation"
    assert schema["properties"]["data"]["type"] == ["object", "null"]
```

- [ ] **Step 2: Add tests for pass-2 formatter body**

Add tests:

```python
def test_formatter_messages_are_not_lm5j_worker_messages() -> None:
    request_payload = {"schema": "rook.local_worker_turn_request:v1", "context": {}}
    decision = {"kind": "clarification_request", "question": "Need code?"}
    schema = PROBE._single_kind_response_schema(decision)

    messages = PROBE._formatter_messages(request_payload, decision, schema)

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "formatting an already-made Rook worker decision" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["request_envelope"] == request_payload
    assert payload["decision"] == decision
    assert payload["kind"] == "clarification_request"
    assert payload["response_schema"] == "rook.local_worker_turn_response:v1"
    assert payload["single_kind_schema"] == schema


def test_pass2_request_body_uses_single_kind_format_and_think_false() -> None:
    request_payload = {"schema": "rook.local_worker_turn_request:v1", "context": {}}
    decision = {"kind": "action_request", "action_id": "draft_repair_params"}
    schema = PROBE._single_kind_response_schema(decision)

    body = PROBE._build_pass2_body(
        model="gemma4:12b-it-qat",
        request_payload=request_payload,
        decision=decision,
        single_kind_schema=schema,
        temperature=0,
    )

    assert body["model"] == "gemma4:12b-it-qat"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["format"] == schema
    assert body["format"] is not schema
    assert body["messages"] == PROBE._formatter_messages(
        request_payload,
        decision,
        schema,
    )
```

- [ ] **Step 3: Run Task 3 tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_single_kind_schema_action_request_const_pins_kind_and_action_id `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_single_kind_schema_clarification_request_shape `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_single_kind_schema_refusal_const_pins_category `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_single_kind_schema_observation_shape `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_formatter_messages_are_not_lm5j_worker_messages `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass2_request_body_uses_single_kind_format_and_think_false `
  -q
```

Expected: failures because schema and formatter helpers do not exist.

- [ ] **Step 4: Implement schema and formatter helpers**

Add imports at the top:

```python
import copy
```

Add these helpers after `_parse_pass1_decision`:

```python
def _schema_const_prop() -> dict[str, str]:
    return {"const": LOCAL_WORKER_TURN_RESPONSE_SCHEMA}


def _single_kind_response_schema(decision: Mapping[str, Any]) -> dict[str, Any]:
    kind = decision["kind"]
    base: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": _schema_const_prop(),
            "kind": {"const": kind},
        },
    }

    if kind == "action_request":
        base["required"] = ["schema", "kind", "action_id", "rationale", "input"]
        base["properties"].update(
            {
                "action_id": {"const": decision["action_id"]},
                "rationale": {"type": "string"},
                "input": {"type": "object"},
            }
        )
        return base

    if kind == "clarification_request":
        base["required"] = ["schema", "kind", "question", "rationale"]
        base["properties"].update(
            {
                "question": {"type": "string"},
                "rationale": {"type": ["string", "null"]},
            }
        )
        return base

    if kind == "refusal":
        base["required"] = ["schema", "kind", "category", "reason"]
        base["properties"].update(
            {
                "category": {"const": decision["category"]},
                "reason": {"type": "string"},
            }
        )
        return base

    if kind == "observation":
        base["required"] = ["schema", "kind", "message", "data"]
        base["properties"].update(
            {
                "message": {"type": "string"},
                "data": {"type": ["object", "null"]},
            }
        )
        return base

    raise ValueError(f"unknown decision kind for schema: {kind}")


_FORMATTER_SYSTEM_TEXT = """\
You are formatting an already-made Rook worker decision.
Do not change the decision kind.
Do not change action_id.
Return exactly one JSON object matching the provided single-kind schema.
Use the original request envelope only to fill fields needed by the chosen decision.
If required information is missing, preserve the chosen kind and express that
within the chosen envelope where possible; do not switch kinds.
"""


def _formatter_messages(
    request_payload: Mapping[str, Any],
    decision: Mapping[str, Any],
    single_kind_schema: Mapping[str, Any],
) -> list[dict[str, str]]:
    payload = {
        "request_envelope": request_payload,
        "decision": decision,
        "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": decision["kind"],
        "single_kind_schema": single_kind_schema,
    }
    return [
        {"role": "system", "content": _FORMATTER_SYSTEM_TEXT},
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def _build_pass2_body(
    *,
    model: str,
    request_payload: Mapping[str, Any],
    decision: Mapping[str, Any],
    single_kind_schema: Mapping[str, Any],
    temperature: float,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": _formatter_messages(request_payload, decision, single_kind_schema),
        "stream": False,
        "format": copy.deepcopy(single_kind_schema),
        "think": False,
        "options": {"temperature": temperature},
    }
```

- [ ] **Step 5: Run Task 3 tests to verify GREEN**

Run the same selected pytest command. Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5r): build single-kind publication schemas"
```

---

## Task 4: Attempt Classification With Fake Providers

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Add fake provider helpers to tests**

Add helpers:

```python
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
```

- [ ] **Step 2: Add pass-1 failure tests**

Add tests:

```python
def test_run_attempt_stops_before_pass2_when_pass1_decision_missing_action_id() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"action_request"}', thinking="deciding"),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass1_decision_invalid"
    assert row["failure_reason"] == "pass1_missing_action_id"
    assert len(provider.calls) == 1
    assert row["pass1_kind"] is None
    assert row["lm5g_loadable"] is False


def test_run_attempt_records_pass1_provider_error() -> None:
    def raising_provider(endpoint: str, body: dict, timeout_s: float) -> str:
        raise RuntimeError("boom")

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=raising_provider,
    )

    assert row["status"] == "pass1_provider_error"
    assert row["failure_reason"] == "pass1_provider_error:RuntimeError"
```

- [ ] **Step 3: Add pass-2 publication tests**

Add tests:

```python
def test_run_attempt_publishes_valid_same_kind_clarification() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                '{"kind":"clarification_request","question":"Please provide the current code."}',
                thinking="need code",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "Please provide the current code.",
                        "rationale": "The request lacks code.",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "published"
    assert row["failure_reason"] is None
    assert row["pass1_kind"] == "clarification_request"
    assert row["pass2_response_kind"] == "clarification_request"
    assert row["kind_preserved"] is True
    assert row["action_id_preserved"] is None
    assert row["lm5g_loadable"] is True
    assert provider.calls[1]["think"] is False


def test_run_attempt_reports_pass2_kind_changed_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need code?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "I changed kind.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["lm5g_loadable"] is True
    assert row["status"] == "pass2_invariant_violation"
    assert row["failure_reason"] == "pass2_kind_changed"
    assert row["kind_preserved"] is False


def test_run_attempt_reports_pass2_action_id_changed_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"action_request","action_id":"draft_repair_params"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "action_request",
                        "action_id": "other_action",
                        "rationale": "Changed action.",
                        "input": {},
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["lm5g_loadable"] is True
    assert row["status"] == "pass2_invariant_violation"
    assert row["failure_reason"] == "pass2_action_id_changed"
    assert row["action_id_preserved"] is False


def test_run_attempt_reports_pass2_refusal_category_changed_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                '{"kind":"refusal","category":"out_of_scope","reason":"No authority."}'
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "refusal",
                        "category": "unsafe",
                        "reason": "Changed category.",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["lm5g_loadable"] is True
    assert row["status"] == "pass2_invariant_violation"
    assert row["failure_reason"] == "pass2_refusal_category_changed"
    assert row["refusal_category_preserved"] is False


def test_run_attempt_reports_pass2_lm5g_invalid() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need code?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "Need code?",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass2_lm5g_invalid"
    assert row["failure_reason"] == "pass2_lm5g_load_failed:ValueError"
    assert row["lm5g_loadable"] is False


def test_provider_message_fields_records_recursion_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_recursion(_text: str) -> object:
        raise RecursionError("nested too deeply")

    monkeypatch.setattr(PROBE.json, "loads", raise_recursion)

    fields, failure_reason = PROBE._provider_message_fields(
        "provider payload",
        prefix="pass1",
        excerpt_chars=500,
    )

    assert fields is None
    assert failure_reason == "pass1_provider_json_invalid:RecursionError"


def test_run_attempt_reports_pass2_content_recursion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_loads = json.loads

    def loads_with_recursion(text: str) -> object:
        if text == "RECURSIVE_CONTENT":
            raise RecursionError("nested too deeply")
        return real_loads(text)

    monkeypatch.setattr(PROBE.json, "loads", loads_with_recursion)
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need code?"}'),
            _ollama_response("RECURSIVE_CONTENT"),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass2_lm5g_invalid"
    assert row["failure_reason"] == "pass2_content_json_invalid:RecursionError"
    assert row["lm5g_loadable"] is False
```

- [ ] **Step 4: Run Task 4 tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_stops_before_pass2_when_pass1_decision_missing_action_id `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_records_pass1_provider_error `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_publishes_valid_same_kind_clarification `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_reports_pass2_kind_changed_after_lm5g_load `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_reports_pass2_action_id_changed_after_lm5g_load `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_reports_pass2_refusal_category_changed_after_lm5g_load `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_reports_pass2_lm5g_invalid `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_provider_message_fields_records_recursion_error `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_reports_pass2_content_recursion_error `
  -q
```

Expected: failures because `_run_attempt` does not exist.

- [ ] **Step 5: Implement provider parsing and `_run_attempt`**

Add helper functions after `_build_pass2_body`:

```python
def _empty_attempt_row(
    *,
    model: str,
    scenario: str,
    attempt: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "scenario": scenario,
        "attempt": attempt,
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
    }


def _post_ollama_chat(endpoint: str, body: dict[str, Any], timeout_s: float) -> str:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8")


def _provider_message_fields(
    provider_text: str,
    *,
    prefix: str,
    excerpt_chars: int,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        provider_payload = json.loads(provider_text)
    except (json.JSONDecodeError, RecursionError) as exc:
        return None, f"{prefix}_provider_json_invalid:{type(exc).__name__}"

    if not isinstance(provider_payload, Mapping):
        return None, f"{prefix}_provider_json_invalid:not_mapping"

    message = provider_payload.get("message")
    if not isinstance(message, Mapping):
        return None, f"{prefix}_message_missing"

    content = message.get("content")
    if not isinstance(content, str) or not content:
        return None, f"{prefix}_content_missing"

    thinking = message.get("thinking")
    fields = {
        "content": content,
        "content_excerpt": _excerpt(content, excerpt_chars),
        "content_sha256": _sha256_text(content),
        "thinking_present": isinstance(thinking, str) and bool(thinking),
        "thinking_chars": len(thinking) if isinstance(thinking, str) else 0,
        "thinking_sha256": _sha256_text(thinking) if isinstance(thinking, str) else None,
        "prompt_eval_count": provider_payload.get("prompt_eval_count"),
        "eval_count": provider_payload.get("eval_count"),
    }
    return fields, None


def _build_pass1_body(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": True,
        "options": {"temperature": temperature},
    }
```

Add `_run_attempt`:

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
    row = _empty_attempt_row(model=model, scenario=scenario, attempt=attempt)
    pass1_messages, request_payload = _pass1_messages_for_scenario(scenario)
    pass1_body = _build_pass1_body(
        model=model,
        messages=pass1_messages,
        temperature=temperature,
    )

    try:
        pass1_text = post_chat(endpoint, pass1_body, timeout_s)
    except urllib.error.HTTPError as exc:
        row["status"] = "pass1_provider_error"
        row["failure_reason"] = f"pass1_http_error:{exc.code}"
        row["pass1_provider_status"] = "error"
        return row
    except Exception as exc:
        row["status"] = "pass1_provider_error"
        row["failure_reason"] = f"pass1_provider_error:{type(exc).__name__}"
        row["pass1_provider_status"] = "error"
        return row

    pass1_fields, pass1_failure = _provider_message_fields(
        pass1_text,
        prefix="pass1",
        excerpt_chars=excerpt_chars,
    )
    if pass1_fields is None:
        row["status"] = "pass1_decision_invalid"
        row["failure_reason"] = pass1_failure
        row["pass1_provider_status"] = "ok"
        return row

    row["pass1_provider_status"] = "ok"
    row["pass1_content_excerpt"] = pass1_fields["content_excerpt"]
    row["pass1_content_sha256"] = pass1_fields["content_sha256"]
    row["pass1_thinking_present"] = pass1_fields["thinking_present"]
    row["pass1_thinking_chars"] = pass1_fields["thinking_chars"]
    row["pass1_thinking_sha256"] = pass1_fields["thinking_sha256"]
    row["pass1_prompt_eval_count"] = pass1_fields["prompt_eval_count"]
    row["pass1_eval_count"] = pass1_fields["eval_count"]

    decision, decision_failure = _parse_pass1_decision(pass1_fields["content"])
    if decision is None:
        row["status"] = "pass1_decision_invalid"
        row["failure_reason"] = decision_failure
        return row

    decision_text = json.dumps(decision, sort_keys=True)
    row["pass1_decision_sha256"] = _sha256_text(decision_text)
    row["pass1_kind"] = decision["kind"]
    row["pass1_action_id"] = decision.get("action_id")
    row["pass1_refusal_category"] = decision.get("category")

    single_kind_schema = _single_kind_response_schema(decision)
    row["pass2_schema_kind"] = decision["kind"]
    pass2_body = _build_pass2_body(
        model=model,
        request_payload=request_payload,
        decision=decision,
        single_kind_schema=single_kind_schema,
        temperature=temperature,
    )

    try:
        pass2_text = post_chat(endpoint, pass2_body, timeout_s)
    except urllib.error.HTTPError as exc:
        row["status"] = "pass2_provider_error"
        row["failure_reason"] = f"pass2_http_error:{exc.code}"
        row["pass2_provider_status"] = "error"
        return row
    except Exception as exc:
        row["status"] = "pass2_provider_error"
        row["failure_reason"] = f"pass2_provider_error:{type(exc).__name__}"
        row["pass2_provider_status"] = "error"
        return row

    pass2_fields, pass2_failure = _provider_message_fields(
        pass2_text,
        prefix="pass2",
        excerpt_chars=excerpt_chars,
    )
    if pass2_fields is None:
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = pass2_failure
        row["pass2_provider_status"] = "ok"
        return row

    row["pass2_provider_status"] = "ok"
    row["pass2_content_excerpt"] = pass2_fields["content_excerpt"]
    row["pass2_content_sha256"] = pass2_fields["content_sha256"]
    row["pass2_prompt_eval_count"] = pass2_fields["prompt_eval_count"]
    row["pass2_eval_count"] = pass2_fields["eval_count"]

    try:
        parsed_response = json.loads(pass2_fields["content"])
    except (json.JSONDecodeError, RecursionError) as exc:
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = f"pass2_content_json_invalid:{type(exc).__name__}"
        return row

    if not isinstance(parsed_response, Mapping):
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = "pass2_content_not_mapping"
        return row

    row["pass2_response_kind"] = parsed_response.get("kind")
    row["pass2_action_id"] = parsed_response.get("action_id")
    row["pass2_refusal_category"] = parsed_response.get("category")

    try:
        load_local_worker_turn_response_payload(parsed_response)
    except (TypeError, ValueError) as exc:
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = f"pass2_lm5g_load_failed:{type(exc).__name__}"
        return row

    row["lm5g_loadable"] = True
    row["kind_preserved"] = row["pass2_response_kind"] == row["pass1_kind"]
    row["action_id_preserved"] = (
        row["pass2_action_id"] == row["pass1_action_id"]
        if row["pass1_kind"] == "action_request"
        else None
    )
    row["refusal_category_preserved"] = (
        row["pass2_refusal_category"] == row["pass1_refusal_category"]
        if row["pass1_kind"] == "refusal"
        else None
    )

    if row["kind_preserved"] is not True:
        row["status"] = "pass2_invariant_violation"
        row["failure_reason"] = "pass2_kind_changed"
        return row
    if row["action_id_preserved"] is False:
        row["status"] = "pass2_invariant_violation"
        row["failure_reason"] = "pass2_action_id_changed"
        return row
    if row["refusal_category_preserved"] is False:
        row["status"] = "pass2_invariant_violation"
        row["failure_reason"] = "pass2_refusal_category_changed"
        return row

    row["status"] = "published"
    row["failure_reason"] = None
    return row
```

- [ ] **Step 6: Run Task 4 tests to verify GREEN**

Run the same selected pytest command. Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 4**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5r): classify two-pass attempts"
```

---

## Task 5: Run Loop, Manifest, Attempts, and Summary

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Add tests for manifest and summary helpers**

Add tests:

```python
def _summary_row(
    *,
    scenario: str = "evidence_absent_like",
    status: str = "published",
    pass1_kind: str | None = "clarification_request",
    pass2_response_kind: str | None = "clarification_request",
    kind_preserved: bool | None = True,
    action_id_preserved: bool | None = None,
    refusal_category_preserved: bool | None = None,
    lm5g_loadable: bool = True,
    failure_reason: str | None = None,
) -> dict:
    return {
        "scenario": scenario,
        "status": status,
        "pass1_kind": pass1_kind,
        "pass2_response_kind": pass2_response_kind,
        "kind_preserved": kind_preserved,
        "action_id_preserved": action_id_preserved,
        "refusal_category_preserved": refusal_category_preserved,
        "lm5g_loadable": lm5g_loadable,
        "failure_reason": failure_reason,
    }


def test_build_summary_groups_by_status_kind_and_preservation() -> None:
    rows = [
        _summary_row(),
        _summary_row(
            scenario="evidence_present_like",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=True,
        ),
        _summary_row(
            scenario="evidence_present_like",
            status="pass2_invariant_violation",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=False,
            failure_reason="pass2_action_id_changed",
        ),
    ]

    summary = PROBE._build_summary(
        run_id="lm5r-demo",
        git_commit="abc1234",
        model="gemma4:12b-it-qat",
        scenarios=["evidence_absent_like", "evidence_present_like"],
        attempts_per_scenario=5,
        rows=rows,
    )

    assert summary["run_id"] == "lm5r-demo"
    assert summary["git_commit"] == "abc1234"
    assert summary["model"] == "gemma4:12b-it-qat"
    assert summary["scenarios"] == ["evidence_absent_like", "evidence_present_like"]
    assert summary["attempts_per_scenario"] == 5
    assert summary["groups"] == [
        {
            "scenario": "evidence_absent_like",
            "status": "published",
            "pass1_kind": "clarification_request",
            "pass2_response_kind": "clarification_request",
            "kind_preserved": True,
            "action_id_preserved": None,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
        },
        {
            "scenario": "evidence_present_like",
            "status": "pass2_invariant_violation",
            "pass1_kind": "action_request",
            "pass2_response_kind": "action_request",
            "kind_preserved": True,
            "action_id_preserved": False,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {"pass2_action_id_changed": 1},
        },
        {
            "scenario": "evidence_present_like",
            "status": "published",
            "pass1_kind": "action_request",
            "pass2_response_kind": "action_request",
            "kind_preserved": True,
            "action_id_preserved": True,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
        },
    ]
```

Add run loop test:

```python
def test_run_probe_writes_manifest_attempts_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows_returned = [
        _summary_row(scenario="evidence_absent_like"),
        _summary_row(
            scenario="evidence_present_like",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=True,
        ),
    ]
    calls: list[tuple[str, int]] = []

    def fake_run_attempt(**kwargs):
        calls.append((kwargs["scenario"], kwargs["attempt"]))
        return rows_returned[len(calls) - 1]

    monkeypatch.setattr(PROBE, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(PROBE, "_git_short_sha", lambda: "abc1234")
    monkeypatch.setattr(PROBE, "_ollama_version", lambda: "ollama version is 0.31.1")
    monkeypatch.setattr(
        PROBE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": None,
            "model_quantization": "Q4_0",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "quantization        Q4_0",
        },
    )
    monkeypatch.setattr(PROBE, "_run_attempt", fake_run_attempt)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        scenarios=["evidence_absent_like", "evidence_present_like"],
        endpoint="http://fake.local/api/chat",
        temperature=0,
        attempts_per_scenario=1,
        timeout_s=9,
        excerpt_chars=500,
    )

    assert calls == [("evidence_absent_like", 1), ("evidence_present_like", 1)]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["script_schema"] == "rook.lm5r_two_pass_publication_probe:v1"
    assert manifest["git_commit"] == "abc1234"
    assert manifest["model"]["model"] == "gemma4:12b-it-qat"
    assert manifest["scenarios"] == ["evidence_absent_like", "evidence_present_like"]
    assert manifest["attempts_per_scenario"] == 1

    attempt_rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert attempt_rows == rows_returned

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["run_id"] == run_dir.name
    assert len(summary["groups"]) == 2
```

- [ ] **Step 2: Run Task 5 tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_build_summary_groups_by_status_kind_and_preservation `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_probe_writes_manifest_attempts_and_summary `
  -q
```

Expected: failures because `_build_summary` and `_run_probe` do not exist.

- [ ] **Step 3: Implement manifest, summary, writer, and run loop**

Add helper functions:

```python
def _count_strings(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if isinstance(value, str) and value:
            counts[value] += 1
    return dict(sorted(counts.items()))


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_short_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _ollama_version() -> str:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return f"unavailable:{type(exc).__name__}"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or result.stderr.strip() or "unknown"


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    normalized_labels = tuple(label.casefold() for label in labels)
    for line in text.splitlines():
        stripped = line.strip()
        folded = stripped.casefold()
        for label, folded_label in zip(labels, normalized_labels):
            if folded.startswith(folded_label):
                value = stripped[len(label) :].strip()
                if value:
                    return value
    return None


def _parse_show_metadata(text: str) -> dict[str, str | None]:
    return {
        "model_id": _extract_labeled_value(text, ("model id",)),
        "model_quantization": _extract_labeled_value(text, ("quantization",)),
    }


def _model_metadata(model: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["ollama", "show", model],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return {
            "model": model,
            "model_id": None,
            "model_quantization": None,
            "ollama_show_status": f"unavailable:{type(exc).__name__}",
            "ollama_show_excerpt": None,
        }

    text = result.stdout if result.stdout else result.stderr
    parsed = _parse_show_metadata(text)
    status = "ok" if result.returncode == 0 else f"error:{result.returncode}"
    return {
        "model": model,
        **parsed,
        "ollama_show_status": status,
        "ollama_show_excerpt": _excerpt(text),
    }
```

Add summary and run functions:

```python
def _build_summary(
    *,
    run_id: str,
    git_commit: str,
    model: str,
    scenarios: list[str],
    attempts_per_scenario: int,
    rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[
        tuple[str, str, str | None, str | None, bool | None, bool | None, bool | None],
        list[Mapping[str, Any]],
    ] = defaultdict(list)
    for row in rows:
        key = (
            row.get("scenario"),
            row.get("status"),
            row.get("pass1_kind"),
            row.get("pass2_response_kind"),
            row.get("kind_preserved"),
            row.get("action_id_preserved"),
            row.get("refusal_category_preserved"),
        )
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    for key, group_rows in sorted(grouped.items(), key=lambda item: tuple(str(part) for part in item[0])):
        (
            scenario,
            status,
            pass1_kind,
            pass2_response_kind,
            kind_preserved,
            action_id_preserved,
            refusal_category_preserved,
        ) = key
        groups.append(
            {
                "scenario": scenario,
                "status": status,
                "pass1_kind": pass1_kind,
                "pass2_response_kind": pass2_response_kind,
                "kind_preserved": kind_preserved,
                "action_id_preserved": action_id_preserved,
                "refusal_category_preserved": refusal_category_preserved,
                "attempts": len(group_rows),
                "lm5g_loadable_count": sum(
                    1 for row in group_rows if row.get("lm5g_loadable") is True
                ),
                "failure_reason_counts": _count_strings(group_rows, "failure_reason"),
            }
        )

    return {
        "run_id": run_id,
        "git_commit": git_commit,
        "model": model,
        "scenarios": scenarios,
        "attempts_per_scenario": attempts_per_scenario,
        "groups": groups,
    }


def _build_manifest(
    *,
    git_commit: str,
    ollama_version: str,
    model: dict[str, Any],
    scenarios: list[str],
    endpoint: str,
    temperature: float,
    attempts_per_scenario: int,
) -> dict[str, Any]:
    return {
        "script_schema": SCRIPT_SCHEMA,
        "git_commit": git_commit,
        "ollama_version": ollama_version,
        "model": model,
        "scenarios": scenarios,
        "endpoint": endpoint,
        "temperature": temperature,
        "attempts_per_scenario": attempts_per_scenario,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _run_probe(
    *,
    model: str,
    scenarios: list[str],
    endpoint: str,
    temperature: float,
    attempts_per_scenario: int,
    timeout_s: float,
    excerpt_chars: int,
) -> Path:
    git_commit = _git_short_sha()
    manifest = _build_manifest(
        git_commit=git_commit,
        ollama_version=_ollama_version(),
        model=_model_metadata(model),
        scenarios=scenarios,
        endpoint=endpoint,
        temperature=temperature,
        attempts_per_scenario=attempts_per_scenario,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = _REPO_ROOT / "probe_runs" / f"lm5r-{timestamp}-{git_commit}"
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json_file(run_dir / "manifest.json", manifest)

    rows: list[dict[str, Any]] = []
    attempts_path = run_dir / "attempts.jsonl"
    with attempts_path.open("w", encoding="utf-8") as attempts_file:
        for scenario in scenarios:
            for attempt in range(1, attempts_per_scenario + 1):
                row = _run_attempt(
                    model=model,
                    scenario=scenario,
                    attempt=attempt,
                    endpoint=endpoint,
                    temperature=temperature,
                    timeout_s=timeout_s,
                    excerpt_chars=excerpt_chars,
                )
                rows.append(row)
                attempts_file.write(json.dumps(row, sort_keys=True) + "\n")

    summary = _build_summary(
        run_id=run_dir.name,
        git_commit=git_commit,
        model=model,
        scenarios=scenarios,
        attempts_per_scenario=attempts_per_scenario,
        rows=rows,
    )
    _write_json_file(run_dir / "summary.json", summary)

    status_counts = Counter(row["status"] for row in rows)
    published = status_counts.get("published", 0)
    print(
        "LM5R two-pass probe complete: "
        f"run_dir={run_dir} attempts={len(rows)} published={published} "
        f"status_counts={dict(sorted(status_counts.items()))}"
    )
    return run_dir
```

Update `main`:

```python
def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    _run_probe(
        model=args.model,
        scenarios=args.scenarios,
        endpoint=args.endpoint,
        temperature=args.temperature,
        attempts_per_scenario=args.attempts,
        timeout_s=args.timeout_s,
        excerpt_chars=args.excerpt_chars,
    )
    return 0
```

- [ ] **Step 4: Run Task 5 tests to verify GREEN**

Run the same selected pytest command. Expected: both selected tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5r): write two-pass probe evidence"
```

---

## Task 6: Deterministic Gates

**Files:**
- No intended edits

- [ ] **Step 1: Run LM5R targeted tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all LM5R tests pass.

- [ ] **Step 2: Run nearby probe/transport gate**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run Python 3.10 compile gate**

Run:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

Expected: exits 0 with no output.

- [ ] **Step 4: Run whitespace and scope checks**

Run:

```powershell
cd C:\UDEV\Rook
git diff --check main..HEAD
git diff --name-only main..HEAD
git diff --name-only main..HEAD -- mcp_server\src
git diff --name-only main..HEAD -- scripts\lm5k_worker_probe.py scripts\lm5p_ollama_think_format_spike.py
git status --short --branch
```

Expected:

```text
git diff --check: no output
diff paths: LM5R spec/plan/script/test only
mcp_server/src diff: no output
LM5K/LM5P script diff: no output
status: clean except unrelated untracked items
```

- [ ] **Step 5: Run AST/source guard**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_script_static_import_and_call_guards `
  -q
```

Expected: pass.

- [ ] **Step 6: Commit only if a gate fix was required**

If a gate required a source/test fix:

```powershell
cd C:\UDEV\Rook
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "test(lm5r): complete deterministic gates"
```

If no gate fix was required, make no Task 6 commit.

---

## Task 7: Manual Canonical LM5R Evidence Run

**Files:**
- No committed edits
- Local ignored artifacts under `probe_runs/`

- [ ] **Step 1: Confirm clean tracked state before live run**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --branch
ollama --version
ollama show gemma4:12b-it-qat
```

Expected:

```text
tracked state clean except unrelated untracked items
Ollama responds
gemma4:12b-it-qat metadata is available
```

If `ollama show gemma4:12b-it-qat` fails, stop and report the exact failure. Do not substitute another model for the canonical LM5R run.

- [ ] **Step 2: Run the canonical two-pass probe**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --model "gemma4:12b-it-qat" `
  --scenario evidence_absent_like `
  --scenario evidence_present_like `
  --attempts 5 `
  --excerpt-chars 1200
```

Expected:

```text
LM5R two-pass probe complete: run_dir=... attempts=10 published=... status_counts=...
```

Do not commit anything under `probe_runs/`.

- [ ] **Step 3: Inspect local evidence**

Replace `<RUN_DIR>` with the printed run directory:

```powershell
cd C:\UDEV\Rook
(Get-Content <RUN_DIR>\attempts.jsonl).Count
Get-Content <RUN_DIR>\summary.json
```

Expected canonical row count:

```text
10
```

Report:

```text
run directory
git commit
Ollama version
model metadata
row count
status counts
pass1 kind counts
pass2 response kind counts
published count
LM5G-loadable count
kind_preserved count
action_id_preserved count for action decisions
failure_reason counts
```

- [ ] **Step 4: Pull bounded excerpts for representative rows**

Use this snippet:

```powershell
cd C:\UDEV\Rook
@'
import json
from pathlib import Path
from collections import Counter

run_dir = Path(r"<RUN_DIR>")
rows = [json.loads(line) for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
print("statuses", Counter(row["status"] for row in rows))
print("pass1 kinds", Counter(row["pass1_kind"] for row in rows))
print("pass2 kinds", Counter(row["pass2_response_kind"] for row in rows))

for scenario in ("evidence_absent_like", "evidence_present_like"):
    print(f"## {scenario}")
    for row in rows:
        if row["scenario"] != scenario:
            continue
        print(
            f"attempt={row['attempt']} status={row['status']} "
            f"pass1={row['pass1_kind']} pass2={row['pass2_response_kind']} "
            f"kind_preserved={row['kind_preserved']} action_id_preserved={row['action_id_preserved']} "
            f"failure={row['failure_reason']}"
        )
        print("PASS1:", (row.get("pass1_content_excerpt") or "")[:1200])
        print("PASS2:", (row.get("pass2_content_excerpt") or "")[:1200])
        print()
        break
'@ | .\mcp_server\.venv\Scripts\python.exe -
```

Report bounded excerpts for:

```text
one evidence_absent_like row
one evidence_present_like row
any invariant violation row
any pass1_decision_invalid row
```

- [ ] **Step 5: Confirm ignored artifacts remain uncommitted**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --ignored
git diff --name-only --cached
```

Expected:

```text
probe_runs/ may appear as ignored
git diff --name-only --cached does not include probe_runs files
```

No curated evidence doc update belongs in LM5R implementation. Wait for review of the local evidence results before writing any summary doc.
