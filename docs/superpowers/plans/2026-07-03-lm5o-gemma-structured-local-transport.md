# LM5O Gemma Structured Local Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a gated Gemma/Ollama structured-output experiment that constrains LM5 response-envelope validity without constraining the worker's response choice.

**Architecture:** Phase A adds a committed spike script and runs a manual live feasibility check through `LiteLLM -> Ollama -> Gemma` with the full LM5 response union schema. Phase B is conditional: only if Phase A passes, add a default-off structured local transport mode to the existing LiteLLM transport and expose it through the LM5K probe runner for local/Ollama candidates only.

**Tech Stack:** Python 3.10, pytest, LiteLLM, Ollama/Gemma, LM5G response loader, existing LM5K probe runner.

---

## Hard Gate

Execute Phase A first.

If the live/manual spike fails, stop the plan and report evidence. Do not
continue to Phase B in the same execution. A failing spike is a valid LM5O
outcome.

Do not rescue a failed spike by:

```text
weakening the schema
using action-only schema
changing LM5G
changing prompt text
changing evidence packets
adding parser leniency
adding provider-specific fallback behavior
```

## Files

Phase A:

- Create: `scripts/lm5o_structured_output_spike.py`

Phase B, only if Phase A passes:

- Modify: `mcp_server/src/rook/agent/local_worker_model_transport.py`
- Modify: `mcp_server/tests/test_local_worker_model_transport.py`
- Modify: `scripts/lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

No changes:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_prompt_artifact.py
mcp_server/src/rook/agent/local_worker_adapter.py
mcp_server/src/rook/agent/local_worker_turn_request.py
docs/superpowers/probes/*
probe_runs/*
```

## Task 1: Phase A Feasibility Spike

**Files:**
- Create: `scripts/lm5o_structured_output_spike.py`

- [ ] **Step 1: Add the committed spike script**

Create `scripts/lm5o_structured_output_spike.py`:

```python
#!/usr/bin/env python
"""LM5O structured-output spike for LiteLLM -> Ollama -> Gemma.

This is a manual feasibility probe, not CI. It asks whether Ollama structured
output can constrain the LM5 response envelope while preserving response-kind
choice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping
from typing import Any

import litellm

from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)


ABSENT_PROMPT = """You are a bounded local worker.

Return exactly one JSON object matching the provided schema. The visible context
does not include enough repair evidence to author an action input responsibly.
Choose the valid response kind that best fits restraint.
"""


PRESENT_PROMPT = """You are a bounded local worker.

Return exactly one JSON object matching the provided schema. The visible context
includes bounded repair evidence:
- current code: A = DefinitelyMissingSymbol;
- recommended mode: body
- failure count: 1
Choose the valid response kind that best fits this evidence.
"""


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


def _extract_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(
            f"provider response missing choices/message: {type(exc).__name__}"
        ) from exc
    if not isinstance(content, str) or not content:
        raise RuntimeError("provider returned no text content")
    return content


def _run_case(
    *,
    label: str,
    model: str,
    prompt: str,
    timeout_s: float,
) -> str:
    started = time.perf_counter()
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout=timeout_s,
        format=_response_union_schema(),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    raw = _extract_content(response)
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise RuntimeError(f"{label}: parsed output is not a mapping")
    loaded = load_local_worker_turn_response_payload(parsed)
    kind = parsed.get("kind")
    print(f"{label}: provider_call=succeeded latency_ms={elapsed_ms:.1f}")
    print(f"{label}: raw_content=received chars={len(raw)}")
    print(f"{label}: json=parsed")
    print(f"{label}: lm5g=loaded kind={kind}")
    if label == "absent" and kind == "action_request":
        raise RuntimeError("absent-style prompt loaded as action_request")
    return type(loaded.payload).__name__


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5O LiteLLM/Ollama structured-output feasibility spike."
    )
    parser.add_argument(
        "--model",
        default="ollama_chat/gemma4:12b-it-qat",
        help="LiteLLM model id; expected to be an Ollama/Gemma local model.",
    )
    parser.add_argument("--timeout-s", type=float, default=120.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        absent_payload = _run_case(
            label="absent",
            model=args.model,
            prompt=ABSENT_PROMPT,
            timeout_s=args.timeout_s,
        )
        present_payload = _run_case(
            label="present",
            model=args.model,
            prompt=PRESENT_PROMPT,
            timeout_s=args.timeout_s,
        )
    except Exception as exc:
        print(f"LM5O structured-output spike failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        "LM5O structured-output spike complete: "
        f"absent_payload={absent_payload} present_payload={present_payload}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Syntax-check the script**

Run from repo root:

```powershell
py -3.10 -m py_compile scripts\lm5o_structured_output_spike.py
```

Expected: exit 0, no output.

- [ ] **Step 3: Run the manual live spike**

Confirm the local model name:

```powershell
ollama list
```

Then run:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5o_structured_output_spike.py `
  --model "ollama_chat/gemma4:12b-it-qat"
```

Expected if Phase A passes:

```text
absent: provider_call=succeeded ...
absent: raw_content=received ...
absent: json=parsed
absent: lm5g=loaded kind=<clarification_request|refusal|observation>
present: provider_call=succeeded ...
present: raw_content=received ...
present: json=parsed
present: lm5g=loaded kind=<any valid kind>
LM5O structured-output spike complete: ...
```

If the command exits nonzero, stop the plan. Do not execute Task 2 or later.
Report:

```text
command
exit code
provider/model
first failing status line
whether failure was provider, JSON parse, LM5G load, or absent forced action
```

Do not commit raw outputs.

- [ ] **Step 4: Commit Phase A**

Only if the script has been added and syntax-check passes:

```powershell
git add scripts\lm5o_structured_output_spike.py
git commit -m "chore(lm5o): add structured output feasibility spike"
```

## Task 2: Transport Structured Schema Tests

**Phase gate:** Run this task only if Task 1 live spike passes.

**Files:**
- Modify: `mcp_server/tests/test_local_worker_model_transport.py`

- [ ] **Step 1: Add failing schema/format transport tests**

Append these imports near the existing imports:

```python
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)
```

Add these tests before `test_import_and_ast_guard`:

```python
def _minimal_valid_payloads_by_kind():
    return {
        "action_request": {
            "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
            "kind": "action_request",
            "action_id": "draft_repair_params",
            "rationale": "Use visible evidence.",
            "input": {"code": "A = 0;", "mode": "body"},
        },
        "clarification_request": {
            "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
            "kind": "clarification_request",
            "question": "What code should be repaired?",
            "rationale": None,
        },
        "refusal": {
            "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
            "kind": "refusal",
            "category": "insufficient_context",
            "reason": "Visible context is insufficient.",
        },
        "observation": {
            "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
            "kind": "observation",
            "message": "Terminal state observed.",
            "data": None,
        },
    }


def test_response_union_schema_contains_all_lm5_response_kinds() -> None:
    schema = transport_module._local_worker_response_union_schema()
    variants = schema["oneOf"]
    kinds = {
        variant["properties"]["kind"]["const"]
        for variant in variants
    }
    assert kinds == {
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    }
    for variant in variants:
        assert variant["additionalProperties"] is False
        assert (
            variant["properties"]["schema"]["const"]
            == LOCAL_WORKER_TURN_RESPONSE_SCHEMA
        )


def test_response_union_schema_accepts_lm5g_valid_payload_shapes() -> None:
    schema = transport_module._local_worker_response_union_schema()
    kinds = {
        variant["properties"]["kind"]["const"]
        for variant in schema["oneOf"]
    }
    assert kinds == set(_minimal_valid_payloads_by_kind())
    for payload in _minimal_valid_payloads_by_kind().values():
        response = load_local_worker_turn_response_payload(payload)
        assert response.payload is not None


def test_structured_transport_passes_format_kwarg(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    structured_schema = transport_module._local_worker_response_union_schema()
    transport = _transport(
        monkeypatch,
        fake,
        structured_response_schema=structured_schema,
    )
    transport.send(_ARTIFACT)
    call = fake.calls[0]
    assert "format" in call
    assert call["format"]["oneOf"][0]["properties"]["schema"]["const"] == (
        LOCAL_WORKER_TURN_RESPONSE_SCHEMA
    )


def test_free_text_transport_omits_format_kwarg(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    assert "format" not in fake.calls[0]


def test_structured_schema_is_copied_per_call(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(
        monkeypatch,
        fake,
        structured_response_schema=transport_module._local_worker_response_union_schema(),
    )
    transport.send(_ARTIFACT)
    fake.calls[0]["format"]["oneOf"].clear()
    transport.send(_ARTIFACT)
    assert len(fake.calls[1]["format"]["oneOf"]) == 4


def test_format_generation_param_conflict_is_rejected() -> None:
    with pytest.raises(TypeError, match="generation_params must not include format"):
        LiteLLMWorkerTransport(
            model="ollama_chat/gemma4:12b-it-qat",
            generation_params={"format": {}},
            structured_response_schema=transport_module._local_worker_response_union_schema(),
        )


def test_structured_response_schema_must_be_mapping() -> None:
    with pytest.raises(TypeError, match="structured_response_schema must be a mapping"):
        LiteLLMWorkerTransport(
            model="ollama_chat/gemma4:12b-it-qat",
            structured_response_schema=[],
        )


def test_structured_response_schema_must_be_json_shaped() -> None:
    with pytest.raises(TypeError, match="structured_response_schema values must be JSON-shaped"):
        LiteLLMWorkerTransport(
            model="ollama_chat/gemma4:12b-it-qat",
            structured_response_schema={"bad": object()},
        )
```

Update `_transport` so keyword overrides can reach the constructor:

```python
def _transport(monkeypatch, fake, **kwargs):
    monkeypatch.setattr(transport_module, "litellm", fake)
    defaults = {"model": "openai/lmstudio-model", "profile_api_base": "http://localhost:1234/v1"}
    defaults.update(kwargs)
    generation_params = defaults.pop("generation_params", {"temperature": 0})
    return LiteLLMWorkerTransport(
        generation_params=generation_params, **defaults
    )
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_model_transport.py -q
```

Expected: fail because `_local_worker_response_union_schema` and
`structured_response_schema` do not exist.

- [ ] **Step 3: Commit the failing tests**

```powershell
cd C:\UDEV\Rook
git add mcp_server\tests\test_local_worker_model_transport.py
git commit -m "test(lm5o): cover structured transport schema"
```

## Task 3: Transport Structured Schema Implementation

**Phase gate:** Run this task only if Task 1 live spike passes.

**Files:**
- Modify: `mcp_server/src/rook/agent/local_worker_model_transport.py`

- [ ] **Step 1: Add private JSON-copy and schema helpers**

In `mcp_server/src/rook/agent/local_worker_model_transport.py`, add imports:

```python
import math
```

Add this import near the existing Rook imports:

```python
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
)
```

Add private helpers above `LiteLLMWorkerTransport`:

```python
def _copy_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    "structured_response_schema values must be JSON-shaped"
                )
            copied[key] = _copy_json_value(item)
        return copied
    if isinstance(value, (list, tuple)):
        return [_copy_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("structured_response_schema values must be JSON-shaped")


def _local_worker_response_union_schema() -> dict[str, Any]:
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
```

- [ ] **Step 2: Extend the transport constructor**

Replace the constructor signature with:

```python
    def __init__(
        self,
        model: str,
        profile_api_base: str | None = None,
        generation_params: Mapping[str, Any] | None = None,
        structured_response_schema: Mapping[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> None:
```

Inside the constructor, after model validation:

```python
        if (
            structured_response_schema is not None
            and not isinstance(structured_response_schema, Mapping)
        ):
            raise TypeError("structured_response_schema must be a mapping")
        self.model = model
        self.profile_api_base = profile_api_base
        self.generation_params = dict(generation_params or {})
        if "format" in self.generation_params and structured_response_schema is not None:
            raise TypeError(
                "generation_params must not include format when "
                "structured_response_schema is set"
            )
        self.structured_response_schema = (
            _copy_json_value(structured_response_schema)
            if structured_response_schema is not None
            else None
        )
```

Keep the existing `timeout_s`, `last_call_info`, and `last_raw_output`
assignments after this block.

- [ ] **Step 3: Pass `format` only in structured mode**

In `send`, after `kwargs.update(self.generation_params)`, add:

```python
        if self.structured_response_schema is not None:
            kwargs["format"] = _copy_json_value(self.structured_response_schema)
```

Do not add anything to `__all__`.

- [ ] **Step 4: Run targeted transport tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_model_transport.py -q
```

Expected: all tests in this file pass.

- [ ] **Step 5: Python 3.10 compile check**

Run from repo root:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_model_transport.py `
  mcp_server\tests\test_local_worker_model_transport.py
```

Expected: exit 0, no output.

- [ ] **Step 6: Commit implementation**

```powershell
cd C:\UDEV\Rook
git add mcp_server\src\rook\agent\local_worker_model_transport.py mcp_server\tests\test_local_worker_model_transport.py
git commit -m "feat(lm5o): add structured response schema transport option"
```

## Task 4: Probe Runner Transport Mode Tests

**Phase gate:** Run this task only if Task 1 live spike passes.

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Add failing transport-mode tests**

Add these tests near the existing slot/resolve tests:

```python
def test_transport_modes_are_source_of_truth() -> None:
    assert PROBE.TRANSPORT_MODES == ("free_text", "structured")
    assert PROBE.DEFAULT_LOCAL_TRANSPORT_MODE == "free_text"


def test_is_ollama_local_model() -> None:
    assert PROBE._is_ollama_local_model("ollama_chat/gemma4:12b-it-qat") is True
    assert PROBE._is_ollama_local_model("ollama/gemma4:12b-it-qat") is True
    assert PROBE._is_ollama_local_model("openai/lmstudio-model") is False
    assert PROBE._is_ollama_local_model(None) is False
```

Add these tests near the offline e2e tests:

```python
def test_structured_mode_requires_resolved_ollama_local(tmp_path) -> None:
    with pytest.raises(ValueError, match="structured local transport requires an Ollama local model"):
        PROBE.run_probe(
            _args(
                tmp_path,
                local="openai/lmstudio-model@http://localhost:1234/v1",
                local_transport_mode="structured",
            ),
            transport_factory=_FakeGoodTransport,
        )


def test_structured_mode_rejects_skipped_local_slot(tmp_path) -> None:
    with pytest.raises(ValueError, match="structured local transport requires a runnable local slot"):
        PROBE.run_probe(
            _args(
                tmp_path,
                local="ollama_chat/gemma4:12b-it-qat",
                local_transport_mode="structured",
                skip=["local", "cheap", "ceiling"],
            ),
            transport_factory=_FakeGoodTransport,
        )


def test_manifest_and_attempts_record_transport_mode(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(
            tmp_path,
            local="ollama_chat/gemma4:12b-it-qat",
            local_transport_mode="structured",
            attempts=1,
        ),
        transport_factory=_FakeGoodTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    by_slot = {entry["slot"]: entry for entry in manifest["panel"]}
    assert by_slot["local"]["transport_mode"] == "structured"
    assert by_slot["cheap"]["transport_mode"] == "free_text"
    assert by_slot["ceiling"]["transport_mode"] == "free_text"
    first = json.loads((run_dir / "attempts.jsonl").read_text().splitlines()[0])
    assert first["transport_mode"] == "structured"


def test_transport_factory_receives_structured_schema_only_for_local_structured(tmp_path) -> None:
    captured = []

    class CapturingTransport(_FakeGoodTransport):
        def __init__(self, resolution):
            super().__init__(resolution)
            captured.append(resolution)

    PROBE.run_probe(
        _args(
            tmp_path,
            local="ollama_chat/gemma4:12b-it-qat",
            local_transport_mode="structured",
            attempts=1,
        ),
        transport_factory=CapturingTransport,
    )
    assert captured[0]["transport_mode"] == "structured"
    assert captured[0]["structured_response_schema"] is not None
```

Update `_args` defaults:

```python
        "local_transport_mode": "free_text",
```

- [ ] **Step 2: Run probe tests to confirm failure**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py -q
```

Expected: fail because `TRANSPORT_MODES`, `local_transport_mode`, and
structured schema resolution do not exist yet.

- [ ] **Step 3: Commit failing tests**

```powershell
cd C:\UDEV\Rook
git add mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "test(lm5o): cover probe transport mode"
```

## Task 5: Probe Runner Transport Mode Implementation

**Phase gate:** Run this task only if Task 1 live spike passes.

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`

- [ ] **Step 1: Add transport mode constants and helpers**

Near slot constants add:

```python
TRANSPORT_MODES = ("free_text", "structured")
DEFAULT_LOCAL_TRANSPORT_MODE = "free_text"
```

Add helpers after `profile_inferred_local`:

```python
def _is_ollama_local_model(model: str | None) -> bool:
    return isinstance(model, str) and model.startswith(_LOCAL_PREFIXES)


def _apply_transport_modes(
    resolutions: list[dict],
    local_transport_mode: str,
) -> list[dict]:
    if local_transport_mode not in TRANSPORT_MODES:
        raise ValueError(f"unknown local transport mode: {local_transport_mode}")
    output: list[dict] = []
    for resolution in resolutions:
        mode = (
            local_transport_mode
            if resolution["slot"] == "local"
            else DEFAULT_LOCAL_TRANSPORT_MODE
        )
        if resolution["slot"] == "local" and mode == "structured":
            if resolution["status"] in ("skipped", "unavailable"):
                raise ValueError(
                    "structured local transport requires a runnable local slot"
                )
            if not _is_ollama_local_model(resolution["model"]):
                raise ValueError(
                    "structured local transport requires an Ollama local model"
                )
        output.append({**resolution, "transport_mode": mode})
    return output
```

- [ ] **Step 2: Pass structured schema through the default factory**

Update `_default_transport_factory`:

```python
def _default_transport_factory(resolution: Mapping[str, Any]):
    from rook.agent.local_worker_model_transport import (
        LiteLLMWorkerTransport,
        _local_worker_response_union_schema,
    )

    structured_schema = (
        _local_worker_response_union_schema()
        if resolution.get("transport_mode") == "structured"
        else None
    )
    return LiteLLMWorkerTransport(
        model=resolution["model"],
        profile_api_base=resolution["api_base"],
        generation_params=resolution.get("generation_params", GENERATION_PARAMS),
        structured_response_schema=structured_schema,
    )
```

- [ ] **Step 3: Record transport mode in attempts**

In `run_candidate`, add this field to the attempt dict:

```python
            "transport_mode": resolution.get("transport_mode", DEFAULT_LOCAL_TRANSPORT_MODE),
```

Place it near `resolution_source`.

- [ ] **Step 4: Apply modes during probe resolution**

In `run_probe`, replace:

```python
    resolutions = [
        {
            **resolve_slot(
                slot,
                cli_value=getattr(args, slot),
                env_value=os.environ.get(ENV_VARS[slot]) or None,
                profile_worker=models.worker,
                profile_api_base=models.api_base,
                skipped=slot in (args.skip or []),
            ),
            "generation_params": dict(SLOT_GENERATION_PARAMS[slot]),
        }
        for slot in SLOTS
    ]
```

with:

```python
    resolutions = _apply_transport_modes(
        [
            {
                **resolve_slot(
                    slot,
                    cli_value=getattr(args, slot),
                    env_value=os.environ.get(ENV_VARS[slot]) or None,
                    profile_worker=models.worker,
                    profile_api_base=models.api_base,
                    skipped=slot in (args.skip or []),
                ),
                "generation_params": dict(SLOT_GENERATION_PARAMS[slot]),
            }
            for slot in SLOTS
        ],
        args.local_transport_mode,
    )
```

Because panel entries are built from `resolution`, `transport_mode` will now be
included in manifest panel rows.

- [ ] **Step 5: Add CLI option**

In `main`, add:

```python
    parser.add_argument(
        "--local-transport-mode",
        choices=list(TRANSPORT_MODES),
        default=DEFAULT_LOCAL_TRANSPORT_MODE,
        help=(
            "local slot transport mode; structured is an LM5O "
            "Ollama-only experiment"
        ),
    )
```

- [ ] **Step 6: Run targeted probe tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py -q
```

Expected: all tests in this file pass.

- [ ] **Step 7: Run transport and probe tests together**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest `
  tests\test_local_worker_model_transport.py `
  tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Python 3.10 compile check**

Run from repo root:

```powershell
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  scripts\lm5o_structured_output_spike.py `
  mcp_server\src\rook\agent\local_worker_model_transport.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py
```

Expected: exit 0, no output.

- [ ] **Step 9: Commit implementation**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "feat(lm5o): add local structured transport mode to probe"
```

## Task 6: Final Verification and Boundary Scan

**Phase gate:** Run this task only if Task 1 live spike passes and Phase B was
implemented.

**Files:**
- No new file edits unless verification finds an LM5O defect.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest `
  tests\test_local_worker_model_transport.py `
  tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run nearby tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest `
  tests\test_local_worker_adapter.py `
  tests\test_local_worker_turn_response_loader.py `
  tests\test_local_worker_turn_request.py `
  tests\test_local_worker_model_transport.py `
  tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run focused local-worker gate**

Run from repo root:

```powershell
$files = @(Get-ChildItem -Path mcp_server\tests -Filter 'test_plan_graph*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName })
$files += @(Get-ChildItem -Path mcp_server\tests -Filter 'test_local_worker*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName })
$files += @((Resolve-Path mcp_server\tests\test_lm5k_worker_probe.py).Path)
.\mcp_server\.venv\Scripts\python.exe -m pytest @files -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Python 3.10 compile check**

Run from repo root:

```powershell
py -3.10 -m py_compile `
  scripts\lm5o_structured_output_spike.py `
  scripts\lm5k_worker_probe.py `
  mcp_server\src\rook\agent\local_worker_model_transport.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py
```

Expected: exit 0, no output.

- [ ] **Step 5: Scope checks**

Run from repo root:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected changed files:

```text
docs/superpowers/specs/2026-07-03-lm5o-gemma-structured-local-transport-design.md
docs/superpowers/plans/2026-07-03-lm5o-gemma-structured-local-transport.md
scripts/lm5o_structured_output_spike.py
mcp_server/src/rook/agent/local_worker_model_transport.py
mcp_server/tests/test_local_worker_model_transport.py
scripts/lm5k_worker_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
```

If Phase A failed and Phase B stopped, expected changed files are only:

```text
docs/superpowers/specs/2026-07-03-lm5o-gemma-structured-local-transport-design.md
docs/superpowers/plans/2026-07-03-lm5o-gemma-structured-local-transport.md
scripts/lm5o_structured_output_spike.py
```

- [ ] **Step 6: Boundary scan**

Run from repo root:

```powershell
git diff -U0 main..HEAD -- `
  mcp_server\src\rook\agent\local_worker_model_transport.py `
  scripts\lm5k_worker_probe.py |
  rg "local_worker_prompt_artifact|load_local_worker_turn_response_payload\\(|markdown fence|fence unwrap|evidence packet|run_live|dispatch|RookChat|Capability Index|action-only|tool_choice|functions"
```

Expected: no output, except `tool_choice` / `functions` may appear only in the
pre-existing `test_no_structured_output_kwargs` context if the diff includes
nearby unchanged lines. If this scan produces unexpected output, inspect before
claiming boundary cleanliness.

- [ ] **Step 7: Raw artifact check**

Run:

```powershell
git status --short --ignored | Select-String 'probe_runs'
git diff --name-only --cached
```

Expected:

```text
probe_runs/ may appear as ignored
no probe_runs path appears in cached diff
```

- [ ] **Step 8: Final commit if needed**

If verification required small fixes:

```powershell
git add <changed LM5O files only>
git commit -m "chore(lm5o): complete structured transport verification"
```

Do not create or update a curated evidence summary in LM5O implementation. The
local-only Gemma live comparison happens after merge.

## Post-Merge Runbook

Do not run these commands inside the implementation PR.

After merge to `main`, run from repo root:

```powershell
ollama list
```

Use the exact Gemma model name. If it is `gemma4:12b-it-qat`, run:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_absent `
  --capture-raw `
  --local "ollama_chat/gemma4:12b-it-qat" `
  --local-transport-mode free_text `
  --skip cheap `
  --skip ceiling
```

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_present `
  --capture-raw `
  --local "ollama_chat/gemma4:12b-it-qat" `
  --local-transport-mode free_text `
  --skip cheap `
  --skip ceiling
```

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_absent `
  --capture-raw `
  --local "ollama_chat/gemma4:12b-it-qat" `
  --local-transport-mode structured `
  --skip cheap `
  --skip ceiling
```

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_present `
  --capture-raw `
  --local "ollama_chat/gemma4:12b-it-qat" `
  --local-transport-mode structured `
  --skip cheap `
  --skip ceiling
```

Report:

```text
run directories
transport_mode per run
strict-loadable n/5
spine-passing m/5
disposition/failure counts
bounded excerpts from structured present action requests, if any
whether structured absent preserved restraint
whether structured present reached candidate_action_request
```

Do not commit raw `probe_runs/`.

## Self-Review Checklist

- Phase A hard stop is explicit before every Phase B task.
- Full four-kind union is required; no action-only fallback exists.
- Structured mode is default-off.
- Structured activation is probe-controlled and local/Ollama-only.
- `transport_mode` is recorded in manifest and attempts.
- No LM5G, prompt, evidence, adapter taxonomy, or authority changes are planned.
- No live provider test is part of CI or the implementation PR gate.
