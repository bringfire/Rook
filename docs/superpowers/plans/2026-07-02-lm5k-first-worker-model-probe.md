# LM5K First Worker Model Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production `LiteLLMWorkerTransport` (the live seam behind LM5J's adapter) and the evidence-only probe runner script that answers: can a real model, given the LM5I envelope rendered through `lm5j.prompt_text:v1`, reliably produce a strict LM5G-loadable response that passes the LM5B/C/D/F spine?

**Architecture:** One production module implementing LM5J's `LocalWorkerTransport` protocol over sync `litellm.completion` (provider exceptions propagate unwrapped; best-effort reset-per-call telemetry; raw capture held on the transport, outside the LM5J record). One script (`scripts/lm5k_worker_probe.py`) structured as pure, importlib-testable functions: three-slot panel resolution, golden scenario × N attempts, JSONL evidence artifacts, curated-summary support. The live probe run is post-merge evidence, never a gate.

**Tech Stack:** Python 3.10-compatible code (test runtime may be 3.12), `litellm` (already a dependency), pytest. Spec: `docs/superpowers/specs/2026-07-02-lm5k-first-worker-model-probe-design.md`.

## Global Constraints

- Worktree: `C:/UDEV/Rook-lm5k`, branch `codex/lm5k-first-worker-model-probe`. All relative paths below are from `C:/UDEV/Rook-lm5k`.
- Production diff under `mcp_server/src` is exactly ONE new module: `mcp_server/src/rook/agent/local_worker_model_transport.py`. No LM5A–J production edits.
- Transport `__all__` pinned exactly: `("LiteLLMWorkerTransport", "TransportCallInfo")`, with a test asserting the tuple.
- Provider/LiteLLM exceptions propagate UNWRAPPED from `send`; `TransportError` is raised only for transport-detected conditions (missing/empty choices, `None` or non-string content). Empty-STRING content returns normally (the adapter classifies it `raw_output_invalid:empty` — model behavior evidence, not a transport defect).
- Telemetry is best-effort: `last_call_info`/`last_raw_output` reset to `None` at the top of EVERY `send`; telemetry extraction failures leave fields `None` and never affect the returned content.
- `api_base_for_model(model, profile_api_base)` is the single routing authority — the transport never re-implements provider routing.
- No provider JSON mode, `response_format`, tool calling, or structured-output enforcement anywhere.
- Panel slots resolve CLI → env (`ROOK_PROBE_LOCAL_WORKER` / `ROOK_PROBE_CHEAP_CLOUD_WORKER` / `ROOK_PROBE_CEILING_WORKER`) → safe profile inference (LOCAL slot only) → `unavailable`; resolved id and source recorded.
- Candidate status vocabulary exactly: `ran | transport_error | unavailable | skipped` (configured-but-failing is `transport_error` with attempt records, never `unavailable`).
- Metrics counted separately: `strict_loadable` (adapter `response_loaded`) and `spine_passed` (`response_loaded` AND LM5F passed); always reported as the pair.
- Generation params: `{"temperature": 0}`, recorded in the manifest.
- `probe_runs/` gitignored; full raw output written only under `--capture-raw`.
- No live model, no network, in any test or merge gate.
- Run all tests with the worktree venv created in Task 1 Step 0 (`mcp_server\.venv\Scripts\python.exe`). Never `C:/UDEV/Rook/mcp_server/.venv` — its editable install resolves `rook` to the main checkout.

---

### Task 1: `LiteLLMWorkerTransport` production module

**Files:**
- Create: `mcp_server/src/rook/agent/local_worker_model_transport.py`
- Test: `mcp_server/tests/test_local_worker_model_transport.py`

**Interfaces:**
- Consumes: `TransportError` from `rook.agent.local_worker_adapter`; `api_base_for_model(model: str, profile_api_base: Optional[str]) -> Optional[str]` from `rook.agent.model_profiles`; `litellm.completion` / `litellm.completion_cost`.
- Produces: `TransportCallInfo` (frozen dataclass: `model: str`, `latency_ms: float`, `prompt_tokens: int | None`, `completion_tokens: int | None`, `cost_usd: float | None`) and `LiteLLMWorkerTransport(model, profile_api_base=None, generation_params=None, timeout_s=120.0)` with `send(prompt_artifact) -> str` plus read-after-call attributes `last_call_info` and `last_raw_output`. Tasks 2–3's script constructs it as `LiteLLMWorkerTransport(model, profile_api_base=api_base, generation_params=GENERATION_PARAMS)`.

- [ ] **Step 0: Create the worktree venv**

```powershell
cd C:\UDEV\Rook-lm5k\mcp_server
uv venv .venv --python 3.12
uv pip install -e . --python .venv\Scripts\python.exe
.venv\Scripts\python.exe -c "import rook.agent.local_worker_adapter as m; print(m.__file__)"
```

Expected: printed path is under `C:\UDEV\Rook-lm5k\`. If not, stop (BLOCKED).

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_local_worker_model_transport.py`:

```python
from __future__ import annotations

import ast
import inspect

import pytest

import rook.agent.local_worker_model_transport as transport_module
from rook.agent.local_worker_adapter import TransportError
from rook.agent.local_worker_model_transport import (
    LiteLLMWorkerTransport,
    TransportCallInfo,
)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Usage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _Response:
    def __init__(self, content, usage=None, empty_choices=False):
        self.choices = [] if empty_choices else [_Choice(content)]
        self.usage = usage


class _FakeLitellm:
    def __init__(self, response=None, exc=None, cost=0.0012, cost_exc=None):
        self.calls = []
        self.response = response
        self.exc = exc
        self.cost = cost
        self.cost_exc = cost_exc

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response

    def completion_cost(self, completion_response):
        if self.cost_exc is not None:
            raise self.cost_exc
        return self.cost


_ARTIFACT = {
    "schema": "rook.local_worker_prompt_artifact:v1",
    "prompt_text_version": "lm5j.prompt_text:v1",
    "messages": [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "{\"k\":1}"},
    ],
}


def _transport(monkeypatch, fake, **kwargs):
    monkeypatch.setattr(transport_module, "litellm", fake)
    defaults = {"model": "openai/lmstudio-model", "profile_api_base": "http://localhost:1234/v1"}
    defaults.update(kwargs)
    return LiteLLMWorkerTransport(
        generation_params={"temperature": 0}, **defaults
    )


def test_module_all_is_exact() -> None:
    assert transport_module.__all__ == (
        "LiteLLMWorkerTransport",
        "TransportCallInfo",
    )


def test_constructor_rejects_empty_model() -> None:
    with pytest.raises(ValueError):
        LiteLLMWorkerTransport(model="")


def test_send_builds_kwargs_and_returns_content(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("hello", usage=_Usage(10, 5)))
    transport = _transport(monkeypatch, fake)
    result = transport.send(_ARTIFACT)
    assert result == "hello"
    call = fake.calls[0]
    assert call["model"] == "openai/lmstudio-model"
    assert call["messages"] == [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "{\"k\":1}"},
    ]
    assert call["temperature"] == 0
    assert call["timeout"] == 120.0
    # openai/* local model with profile api_base -> api_base forwarded
    assert call["api_base"] == "http://localhost:1234/v1"


def test_ollama_model_omits_api_base(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(
        monkeypatch, fake, model="ollama_chat/qwen3-coder:30b-a3b-q8_0"
    )
    transport.send(_ARTIFACT)
    assert "api_base" not in fake.calls[0]


def test_cloud_model_omits_api_base(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(monkeypatch, fake, model="anthropic/claude-haiku-4-5")
    transport.send(_ARTIFACT)
    assert "api_base" not in fake.calls[0]


def test_telemetry_filled_best_effort(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("hello", usage=_Usage(10, 5)))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    info = transport.last_call_info
    assert isinstance(info, TransportCallInfo)
    assert info.model == "openai/lmstudio-model"
    assert info.latency_ms >= 0
    assert info.prompt_tokens == 10
    assert info.completion_tokens == 5
    assert info.cost_usd == pytest.approx(0.0012)
    assert transport.last_raw_output == "hello"


def test_cost_failure_is_non_fatal(monkeypatch) -> None:
    fake = _FakeLitellm(
        response=_Response("hello", usage=_Usage(10, 5)),
        cost_exc=RuntimeError("no pricing"),
    )
    transport = _transport(monkeypatch, fake)
    assert transport.send(_ARTIFACT) == "hello"
    assert transport.last_call_info.cost_usd is None
    assert transport.last_call_info.prompt_tokens == 10


def test_missing_usage_is_non_fatal(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("hello", usage=None))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    assert transport.last_call_info.prompt_tokens is None
    assert transport.last_call_info.completion_tokens is None


def test_provider_exception_propagates_unwrapped(monkeypatch) -> None:
    class FakeAuthError(Exception):
        pass

    fake = _FakeLitellm(exc=FakeAuthError("bad key"))
    transport = _transport(monkeypatch, fake)
    with pytest.raises(FakeAuthError):
        transport.send(_ARTIFACT)


def test_reset_per_call(monkeypatch) -> None:
    good = _FakeLitellm(response=_Response("hello", usage=_Usage(1, 1)))
    transport = _transport(monkeypatch, good)
    transport.send(_ARTIFACT)
    assert transport.last_call_info is not None
    assert transport.last_raw_output == "hello"
    # second call fails at the provider: both attributes must be reset
    transport_module.litellm.exc = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        transport.send(_ARTIFACT)
    assert transport.last_call_info is None
    assert transport.last_raw_output is None


def test_none_content_is_declared_transport_error(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response(None))
    transport = _transport(monkeypatch, fake)
    with pytest.raises(TransportError):
        transport.send(_ARTIFACT)
    assert transport.last_raw_output is None


def test_empty_choices_is_declared_transport_error(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("x", empty_choices=True))
    transport = _transport(monkeypatch, fake)
    with pytest.raises(TransportError):
        transport.send(_ARTIFACT)


def test_empty_string_content_returns_normally(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response(""))
    transport = _transport(monkeypatch, fake)
    assert transport.send(_ARTIFACT) == ""
    assert transport.last_raw_output == ""


def test_no_structured_output_kwargs(monkeypatch) -> None:
    fake = _FakeLitellm(response=_Response("ok"))
    transport = _transport(monkeypatch, fake)
    transport.send(_ARTIFACT)
    call = fake.calls[0]
    for banned in ("response_format", "tools", "tool_choice", "functions"):
        assert banned not in call


def test_import_and_ast_guard() -> None:
    source = inspect.getsource(transport_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.update(alias.name for alias in node.names)
    banned = {
        "base_agent", "chat_runner", "tool_dispatcher", "prompt_builder",
        "local_worker_turn_harness", "local_worker_turn_disposition",
        "local_worker_scenario_evaluation", "plan_graph_live",
        "plan_graph_workflow_contract", "capability_record",
        "capability_inventory", "requests", "httpx", "aiohttp",
        "yaml", "pathlib",
    }
    assert not (imported & banned)
    assert "litellm" in imported
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd C:\UDEV\Rook-lm5k
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_model_transport.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'rook.agent.local_worker_model_transport'`.

- [ ] **Step 3: Implement the module**

Create `mcp_server/src/rook/agent/local_worker_model_transport.py`:

```python
"""LM5K LiteLLM-backed local worker transport (implements LM5J's protocol)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import litellm

from rook.agent.local_worker_adapter import TransportError
from rook.agent.model_profiles import api_base_for_model

__all__ = (
    "LiteLLMWorkerTransport",
    "TransportCallInfo",
)


@dataclass(frozen=True)
class TransportCallInfo:
    model: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None


class LiteLLMWorkerTransport:
    """Sync LocalWorkerTransport over litellm.completion.

    Provider/LiteLLM exceptions propagate unwrapped (the LM5J adapter
    classifies them as transport_error:unexpected:<ClassName>).
    TransportError is raised only for transport-detected conditions.
    Telemetry is best-effort and reset at the top of every send.
    """

    def __init__(
        self,
        model: str,
        profile_api_base: str | None = None,
        generation_params: Mapping[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        self.model = model
        self.profile_api_base = profile_api_base
        self.generation_params = dict(generation_params or {})
        self.timeout_s = timeout_s
        self.last_call_info: TransportCallInfo | None = None
        self.last_raw_output: str | None = None

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.last_call_info = None
        self.last_raw_output = None
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(m) for m in prompt_artifact["messages"]],
            "timeout": self.timeout_s,
        }
        kwargs.update(self.generation_params)
        api_base = api_base_for_model(self.model, self.profile_api_base)
        if api_base:
            kwargs["api_base"] = api_base
        started = time.perf_counter()
        response = litellm.completion(**kwargs)
        latency_ms = (time.perf_counter() - started) * 1000.0
        content = _extract_content(response)
        self.last_raw_output = content
        self.last_call_info = _best_effort_call_info(
            self.model, latency_ms, response
        )
        return content


def _extract_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise TransportError(
            f"provider response missing choices/message: {type(exc).__name__}"
        ) from exc
    if not isinstance(content, str):
        raise TransportError("provider returned no text content")
    return content


def _best_effort_call_info(
    model: str, latency_ms: float, response: Any
) -> TransportCallInfo:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    try:
        usage = getattr(response, "usage", None)
        if usage is not None:
            pt = getattr(usage, "prompt_tokens", None)
            ct = getattr(usage, "completion_tokens", None)
            prompt_tokens = pt if isinstance(pt, int) else None
            completion_tokens = ct if isinstance(ct, int) else None
    except Exception:
        prompt_tokens = None
        completion_tokens = None
    try:
        cost = litellm.completion_cost(completion_response=response)
        cost_usd = float(cost) if cost is not None else None
    except Exception:
        cost_usd = None
    return TransportCallInfo(
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )
```

Note: the spec's §3.1 sketch shows a dataclass; a plain class with explicit
`__init__` validation is the equivalent deliberate choice here (mutable
telemetry attributes plus constructor validation without dataclass
`field` machinery). This is sanctioned — do not convert to a dataclass.

- [ ] **Step 4: Run tests to verify they pass**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_model_transport.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git -C C:\UDEV\Rook-lm5k add mcp_server/src/rook/agent/local_worker_model_transport.py mcp_server/tests/test_local_worker_model_transport.py
git -C C:\UDEV\Rook-lm5k commit -m "feat(lm5k): LiteLLM worker transport behind the LM5J seam"
```

---

### Task 2: Probe script pure logic (resolution, status, metrics)

**Files:**
- Create: `scripts/lm5k_worker_probe.py`
- Create: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `.gitignore` (append the probe_runs entry)

**Interfaces:**
- Consumes: nothing from Task 1 yet (pure logic only in this task).
- Produces (script module attributes Task 3 extends and tests import via importlib): `SLOT_LABELS: dict`, `ENV_VARS: dict`, `GENERATION_PARAMS = {"temperature": 0}`, `parse_candidate_spec(spec: str) -> tuple[str, str | None]`, `profile_inferred_local(worker_model: str, profile_api_base: str | None) -> tuple[str, str | None] | None`, `resolve_slot(slot, cli_value, env_value, profile_worker, profile_api_base, skipped) -> dict`, `classify_candidate_status(adapter_statuses: list) -> str`, `attempt_metrics(attempt: dict) -> tuple[bool, bool]`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_lm5k_worker_probe.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_script()


def test_slot_vocabulary() -> None:
    assert PROBE.SLOT_LABELS == {
        "local": "local_worker_candidate",
        "cheap": "cheap_cloud_worker_candidate",
        "ceiling": "ceiling_worker_candidate",
    }
    assert PROBE.ENV_VARS == {
        "local": "ROOK_PROBE_LOCAL_WORKER",
        "cheap": "ROOK_PROBE_CHEAP_CLOUD_WORKER",
        "ceiling": "ROOK_PROBE_CEILING_WORKER",
    }
    assert PROBE.GENERATION_PARAMS == {"temperature": 0}


def test_parse_candidate_spec() -> None:
    assert PROBE.parse_candidate_spec("ollama_chat/qwen3:8b") == (
        "ollama_chat/qwen3:8b",
        None,
    )
    assert PROBE.parse_candidate_spec(
        "openai/lmstudio-model@http://localhost:1234/v1"
    ) == ("openai/lmstudio-model", "http://localhost:1234/v1")
    with pytest.raises(ValueError):
        PROBE.parse_candidate_spec("@http://x")


def test_profile_inference_local_only_for_local_shaped_models() -> None:
    assert PROBE.profile_inferred_local("ollama_chat/qwen3:8b", None) == (
        "ollama_chat/qwen3:8b",
        None,
    )
    assert PROBE.profile_inferred_local(
        "openai/lmstudio-model", "http://localhost:1234/v1"
    ) == ("openai/lmstudio-model", "http://localhost:1234/v1")
    # openai/* WITHOUT api_base is ambiguous -> not safely inferable
    assert PROBE.profile_inferred_local("openai/lmstudio-model", None) is None
    # cloud models are never a local inference
    assert (
        PROBE.profile_inferred_local("anthropic/claude-haiku-4-5", None) is None
    )


def test_resolve_slot_order_cli_env_profile_none() -> None:
    cli = PROBE.resolve_slot(
        "local",
        cli_value="ollama_chat/a:1",
        env_value="ollama_chat/b:1",
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (cli["model"], cli["source"], cli["status"]) == (
        "ollama_chat/a:1",
        "cli",
        None,
    )
    env = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value="ollama_chat/b:1",
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (env["model"], env["source"]) == ("ollama_chat/b:1", "env")
    prof = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value=None,
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (prof["model"], prof["source"]) == ("ollama_chat/c:1", "profile")
    none = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value=None,
        profile_worker="anthropic/claude-haiku-4-5",
        profile_api_base=None,
        skipped=False,
    )
    assert (none["model"], none["source"], none["status"]) == (
        None,
        "none",
        "unavailable",
    )


def test_cheap_and_ceiling_never_profile_inferred() -> None:
    for slot in ("cheap", "ceiling"):
        resolution = PROBE.resolve_slot(
            slot,
            cli_value=None,
            env_value=None,
            profile_worker="ollama_chat/c:1",
            profile_api_base=None,
            skipped=False,
        )
        assert resolution["status"] == "unavailable"
        assert resolution["source"] == "none"


def test_skipped_slot() -> None:
    resolution = PROBE.resolve_slot(
        "ceiling",
        cli_value="anthropic/claude-sonnet-5",
        env_value=None,
        profile_worker="x",
        profile_api_base=None,
        skipped=True,
    )
    assert resolution["status"] == "skipped"
    assert resolution["model"] is None


def test_candidate_status_classification() -> None:
    assert PROBE.classify_candidate_status(
        ["transport_error", "transport_error"]
    ) == "transport_error"
    assert PROBE.classify_candidate_status(
        ["transport_error", "raw_output_invalid"]
    ) == "ran"
    assert PROBE.classify_candidate_status(["response_loaded"]) == "ran"
    with pytest.raises(ValueError):
        PROBE.classify_candidate_status([])


def test_attempt_metrics_pair() -> None:
    loaded_passed = {"adapter_status": "response_loaded", "evaluation_passed": True}
    loaded_failed = {"adapter_status": "response_loaded", "evaluation_passed": False}
    invalid = {"adapter_status": "raw_output_invalid", "evaluation_passed": None}
    assert PROBE.attempt_metrics(loaded_passed) == (True, True)
    assert PROBE.attempt_metrics(loaded_failed) == (True, False)
    assert PROBE.attempt_metrics(invalid) == (False, False)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py -v
```

Expected: FAIL loading the script (file not found).

- [ ] **Step 3: Create the script with the pure logic**

Create `scripts/lm5k_worker_probe.py`:

```python
#!/usr/bin/env python
"""LM5K first worker model probe — evidence harness, never a CI gate.

Runs the golden repair-workflow envelope against a three-slot model panel
through the production LiteLLMWorkerTransport and the LM5J adapter, then
evaluates loaded responses through the LM5B/C/D/F spine. Writes evidence
artifacts to a gitignored probe_runs/ directory.

Doctrine: probe results are evidence, not pass/fail. See
docs/superpowers/specs/2026-07-02-lm5k-first-worker-model-probe-design.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SLOTS = ("local", "cheap", "ceiling")
SLOT_LABELS = {
    "local": "local_worker_candidate",
    "cheap": "cheap_cloud_worker_candidate",
    "ceiling": "ceiling_worker_candidate",
}
ENV_VARS = {
    "local": "ROOK_PROBE_LOCAL_WORKER",
    "cheap": "ROOK_PROBE_CHEAP_CLOUD_WORKER",
    "ceiling": "ROOK_PROBE_CEILING_WORKER",
}
GENERATION_PARAMS = {"temperature": 0}
DEFAULT_ATTEMPTS = 5
SCENARIO_WORKFLOW_ID = "lm5k_first_probe"

_LOCAL_PREFIXES = ("ollama_chat/", "ollama/")


def parse_candidate_spec(spec: str) -> tuple[str, str | None]:
    """'model[@api_base]' -> (model, api_base or None)."""
    model, sep, api_base = spec.partition("@")
    if not model:
        raise ValueError(f"invalid candidate spec: {spec!r}")
    return model, (api_base if sep and api_base else None)


def profile_inferred_local(
    worker_model: str, profile_api_base: str | None
) -> tuple[str, str | None] | None:
    """Safe profile inference for the LOCAL slot only (spec 4.1 rule 3)."""
    if worker_model.startswith(_LOCAL_PREFIXES):
        return worker_model, profile_api_base
    if worker_model.startswith("openai/") and profile_api_base:
        return worker_model, profile_api_base
    return None


def resolve_slot(
    slot: str,
    cli_value: str | None,
    env_value: str | None,
    profile_worker: str,
    profile_api_base: str | None,
    skipped: bool,
) -> dict:
    """Resolve one panel slot. status None means resolved-and-runnable."""
    base = {"slot": slot, "label": SLOT_LABELS[slot]}
    if skipped:
        return {**base, "model": None, "api_base": None,
                "source": "skip", "status": "skipped"}
    if cli_value:
        model, api_base = parse_candidate_spec(cli_value)
        return {**base, "model": model, "api_base": api_base,
                "source": "cli", "status": None}
    if env_value:
        model, api_base = parse_candidate_spec(env_value)
        return {**base, "model": model, "api_base": api_base,
                "source": "env", "status": None}
    if slot == "local":
        inferred = profile_inferred_local(profile_worker, profile_api_base)
        if inferred is not None:
            model, api_base = inferred
            return {**base, "model": model, "api_base": api_base,
                    "source": "profile", "status": None}
    return {**base, "model": None, "api_base": None,
            "source": "none", "status": "unavailable"}


def classify_candidate_status(adapter_statuses: list) -> str:
    """For an attempted candidate: transport_error iff ALL attempts were.

    An attempted candidate has at least one attempt by definition —
    all([]) is vacuously true and would fabricate transport_error from
    zero evidence, so empty input is a caller error.
    """
    if not adapter_statuses:
        raise ValueError("attempted candidate requires at least one attempt")
    if all(status == "transport_error" for status in adapter_statuses):
        return "transport_error"
    return "ran"


def attempt_metrics(attempt: Mapping[str, Any]) -> tuple[bool, bool]:
    """(strict_loadable, spine_passed) for one attempt record."""
    strict = attempt["adapter_status"] == "response_loaded"
    spine = strict and attempt.get("evaluation_passed") is True
    return strict, spine
```

- [ ] **Step 4: Append the probe_runs gitignore entry**

Append to `.gitignore` (matching the file's comment-grouped style):

```text

# LM5K+ model probe evidence runs (raw evidence stays local; curated
# summaries are committed under docs/superpowers/probes/)
probe_runs/
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git -C C:\UDEV\Rook-lm5k add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py .gitignore
git -C C:\UDEV\Rook-lm5k commit -m "feat(lm5k): probe panel resolution, status, and metric logic"
```

---

### Task 3: Probe runner — scenario, attempts, evidence artifacts

**Files:**
- Modify: `scripts/lm5k_worker_probe.py` (append fixture + runner + writers + main)
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py` (append offline end-to-end tests)

**Interfaces:**
- Consumes: Task 1's `LiteLLMWorkerTransport(model, profile_api_base, generation_params)` (+ `last_call_info`, `last_raw_output`); Task 2's pure logic; `run_local_worker_adapter` (LM5J); `render_local_worker_turn_request_payload` (LM5I); `build_local_worker_turn_context` (LM5A); `compile_workflow_contract` (LM4W); `run_local_worker_turn` (LM5D); `LocalWorkerScenarioExpectation` / `evaluate_local_worker_scenario_result` (LM5F); `get_models()` from `model_profiles`.
- Produces: `build_probe_context()`, `run_candidate(resolution, attempts, run_dir, capture_raw, transport_factory) -> dict`, `build_manifest(...) -> dict`, `run_probe(args) -> Path`, `main(argv) -> int`. The transport_factory parameter (`Callable[[dict], object]`, default constructs `LiteLLMWorkerTransport`) is the offline-test injection seam.

- [ ] **Step 1: Append the runner implementation to the script**

Append to `scripts/lm5k_worker_probe.py` (imports of rook modules are function-local inside `build_probe_context` and `run_candidate` so the pure-logic module loads without the venv when only Task 2 functions are needed — keep them exactly as shown):

```python
def build_probe_context():
    """Golden scenario: the compiled repair workflow, per LM5J's integration
    test, with this probe's workflow_id."""
    import copy

    from rook.agent.local_worker_turn_context import (
        WorkerAllowedAction,
        WorkerKnowledgePacket,
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

    contract = RookWorkflowContract(
        workflow_id=SCENARIO_WORKFLOW_ID,
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
                    "name": "LM5KFirstProbe",
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
        metadata={"trace": {"slice": "LM5K"}},
    )
    scaffold = compile_workflow_contract(contract)
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
                content={"source": "probe fixture", "trust": "high"},
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


def _default_transport_factory(resolution: Mapping[str, Any]):
    from rook.agent.local_worker_model_transport import LiteLLMWorkerTransport

    return LiteLLMWorkerTransport(
        model=resolution["model"],
        profile_api_base=resolution["api_base"],
        generation_params=GENERATION_PARAMS,
    )


def run_candidate(
    resolution: Mapping[str, Any],
    attempts: int,
    run_dir: Path,
    capture_raw: bool,
    transport_factory=None,
) -> dict:
    """Run N attempts for one resolved candidate. Returns the candidate
    summary; appends one line per attempt to run_dir/attempts.jsonl."""
    from rook.agent.local_worker_adapter import run_local_worker_adapter
    from rook.agent.local_worker_scenario_evaluation import (
        LocalWorkerScenarioExpectation,
        evaluate_local_worker_scenario_result,
    )
    from rook.agent.local_worker_turn_harness import run_local_worker_turn
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    factory = transport_factory or _default_transport_factory
    transport = factory(resolution)
    context = build_probe_context()

    schema_versions = _schema_versions()
    adapter_statuses: list = []
    strict_count = 0
    spine_count = 0
    attempts_path = run_dir / "attempts.jsonl"

    for index in range(attempts):
        payload = dict(render_local_worker_turn_request_payload(context))
        record = run_local_worker_adapter(payload, transport)
        adapter_statuses.append(record.status)

        harness_status = None
        disposition = None
        evaluation_passed = None
        if record.status == "response_loaded":
            harness_record = run_local_worker_turn(
                context, lambda received: record.response
            )
            harness_status = harness_record.status
            disposition = (
                harness_record.disposition.disposition
                if harness_record.disposition is not None
                else None
            )
            result = evaluate_local_worker_scenario_result(
                LocalWorkerScenarioExpectation(
                    scenario_id="lm5k_first_probe_golden",
                    category="live_probe",
                    expected_status="completed",
                    expected_disposition="candidate_action_request",
                    expected_attempt_valid=True,
                    expected_action_id="draft_repair_params",
                    expected_response_kind="action_request",
                    expected_workflow_id=context.workflow.workflow_id,
                    expected_contract_fingerprint=(
                        context.workflow.contract_fingerprint
                    ),
                ),
                harness_record,
            )
            evaluation_passed = result.passed

        captured_raw_path = None
        raw_output = getattr(transport, "last_raw_output", None)
        if capture_raw and isinstance(raw_output, str):
            raw_dir = run_dir / "raw"
            raw_dir.mkdir(exist_ok=True)
            raw_file = raw_dir / f"{resolution['slot']}-{index}.txt"
            raw_file.write_text(raw_output, encoding="utf-8")
            captured_raw_path = str(raw_file.relative_to(run_dir))

        info = getattr(transport, "last_call_info", None)
        attempt = {
            "run_id": run_dir.name,
            "candidate_slot": resolution["label"],
            "resolved_model": resolution["model"],
            "resolution_source": resolution["source"],
            "attempt_index": index,
            "adapter_status": record.status,
            "failure_reason": record.failure_reason,
            "raw_output_excerpt": record.raw_output_excerpt,
            "harness_status": harness_status,
            "disposition": disposition,
            "evaluation_passed": evaluation_passed,
            "latency_ms": info.latency_ms if info else None,
            "prompt_tokens": info.prompt_tokens if info else None,
            "completion_tokens": info.completion_tokens if info else None,
            "cost_usd": info.cost_usd if info else None,
            "captured_raw_path": captured_raw_path,
            **schema_versions,
        }
        strict, spine = attempt_metrics(attempt)
        strict_count += int(strict)
        spine_count += int(spine)
        with attempts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(attempt) + "\n")

    return {
        "slot": resolution["slot"],
        "label": resolution["label"],
        "model": resolution["model"],
        "source": resolution["source"],
        "status": classify_candidate_status(adapter_statuses),
        "attempts": attempts,
        "strict_loadable": strict_count,
        "spine_passed": spine_count,
        "adapter_statuses": adapter_statuses,
    }


def _schema_versions() -> dict:
    from rook.agent.local_worker_adapter import (
        LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
    )
    from rook.agent.local_worker_prompt_artifact import (
        LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        LOCAL_WORKER_PROMPT_TEXT_VERSION,
    )
    from rook.agent.local_worker_turn_request import (
        LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    )
    from rook.agent.local_worker_turn_response import (
        LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    )

    return {
        "prompt_schema": LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        "prompt_text_version": LOCAL_WORKER_PROMPT_TEXT_VERSION,
        "request_schema": LOCAL_WORKER_TURN_REQUEST_SCHEMA,
        "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "record_schema": LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
    }


def _git_short_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        sha = out.stdout.strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def build_manifest(
    run_id: str,
    panel: list,
    attempts: int,
    capture_raw: bool,
) -> dict:
    return {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_short_sha(),
        "scenario_workflow_id": SCENARIO_WORKFLOW_ID,
        "generation_params": dict(GENERATION_PARAMS),
        "attempts_per_candidate": attempts,
        "capture_raw": capture_raw,
        "panel": panel,
        **_schema_versions(),
    }


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("attempts must be a positive integer")
    return number


def run_probe(args, transport_factory=None) -> Path:
    from rook.agent.model_profiles import get_models

    if (
        not isinstance(args.attempts, int)
        or isinstance(args.attempts, bool)
        or args.attempts <= 0
    ):
        raise ValueError("attempts must be a positive integer")

    models = get_models()
    resolutions = [
        resolve_slot(
            slot,
            cli_value=getattr(args, slot),
            env_value=os.environ.get(ENV_VARS[slot]) or None,
            profile_worker=models.worker,
            profile_api_base=models.api_base,
            skipped=slot in (args.skip or []),
        )
        for slot in SLOTS
    ]

    run_id = "lm5k-{}-{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        _git_short_sha(),
    )
    run_dir = Path(args.run_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    panel = []
    for resolution in resolutions:
        if resolution["status"] in ("skipped", "unavailable"):
            panel.append({**resolution, "attempts": 0,
                          "strict_loadable": 0, "spine_passed": 0})
            continue
        summary = run_candidate(
            resolution, args.attempts, run_dir, args.capture_raw,
            transport_factory=transport_factory,
        )
        panel.append({**resolution, **summary})

    manifest = build_manifest(run_id, panel, args.attempts, args.capture_raw)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"run: {run_dir}")
    for entry in panel:
        print(
            f"  {entry['slot']:8} {(entry['status'] or 'ran'):16} "
            f"{entry.get('model') or '-':40} "
            f"{entry.get('strict_loadable', 0)}/{entry.get('attempts', 0)} strict-loadable, "
            f"{entry.get('spine_passed', 0)}/{entry.get('attempts', 0)} spine-passing"
        )
    return run_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="LM5K first worker model probe (evidence, not CI)."
    )
    parser.add_argument("--local", help="local slot: MODEL[@API_BASE]")
    parser.add_argument("--cheap", help="cheap cloud slot: MODEL[@API_BASE]")
    parser.add_argument("--ceiling", help="ceiling slot: MODEL[@API_BASE]")
    parser.add_argument(
        "--skip", action="append", choices=list(SLOTS), default=[]
    )
    parser.add_argument(
        "--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS
    )
    parser.add_argument("--capture-raw", action="store_true")
    parser.add_argument("--run-dir", default="probe_runs")
    args = parser.parse_args(argv)
    run_probe(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Append the offline end-to-end tests**

Append to `mcp_server/tests/test_lm5k_worker_probe.py`:

```python
import argparse
import json


class _FakeCallInfo:
    def __init__(self):
        self.latency_ms = 12.5
        self.prompt_tokens = 100
        self.completion_tokens = 20
        self.cost_usd = 0.0001


class _FakeGoodTransport:
    """Deterministic offline model: reads the allowed action from the
    prompt artifact's user JSON (mirrors LM5J's integration transport)."""

    def __init__(self, resolution):
        self.last_call_info = None
        self.last_raw_output = None

    def send(self, prompt_artifact):
        self.last_call_info = None
        self.last_raw_output = None
        envelope = json.loads(prompt_artifact["messages"][1]["content"])
        action_id = envelope["context"]["allowed_actions"][0]["action_id"]
        raw = json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": action_id,
                "rationale": "Draft repair parameters for the failed component.",
                "input": {"code": "A = 42.0;", "mode": "body"},
            }
        )
        self.last_raw_output = raw
        self.last_call_info = _FakeCallInfo()
        return raw


class _FakeFencedTransport(_FakeGoodTransport):
    def send(self, prompt_artifact):
        raw = super().send(prompt_artifact)
        fenced = "```json\n" + raw + "\n```"
        self.last_raw_output = fenced
        return fenced


def _args(tmp_path, **overrides):
    values = {
        "local": "ollama_chat/fake:1", "cheap": None, "ceiling": None,
        "skip": ["cheap", "ceiling"], "attempts": 3,
        "capture_raw": False, "run_dir": str(tmp_path),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_offline_probe_end_to_end_good_transport(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path), transport_factory=_FakeGoodTransport
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["generation_params"] == {"temperature": 0}
    assert manifest["prompt_text_version"] == "lm5j.prompt_text:v1"
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 3
    assert local["spine_passed"] == 3
    skipped = [p for p in manifest["panel"] if p["status"] == "skipped"]
    assert len(skipped) == 2
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["run_id"] == run_dir.name
    assert first["adapter_status"] == "response_loaded"
    assert first["evaluation_passed"] is True
    assert first["disposition"] == "candidate_action_request"
    assert first["latency_ms"] == 12.5
    assert first["captured_raw_path"] is None
    assert not (run_dir / "raw").exists()


def test_offline_probe_fenced_output_counts_split(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, attempts=2), transport_factory=_FakeFencedTransport
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 0
    assert local["spine_passed"] == 0
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    assert json.loads(lines[0])["failure_reason"] == (
        "raw_output_invalid:json_decode"
    )


def test_offline_probe_capture_raw(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, attempts=1, capture_raw=True),
        transport_factory=_FakeGoodTransport,
    )
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["captured_raw_path"] == "raw/local-0.txt"
    raw_text = (run_dir / "raw" / "local-0.txt").read_text(encoding="utf-8")
    assert '"kind": "action_request"' in raw_text


def test_attempts_must_be_positive(tmp_path) -> None:
    for bad in (0, -3):
        with pytest.raises(ValueError):
            PROBE.run_probe(
                _args(tmp_path, attempts=bad),
                transport_factory=_FakeGoodTransport,
            )
    with pytest.raises(argparse.ArgumentTypeError):
        PROBE._positive_int("0")
    with pytest.raises(argparse.ArgumentTypeError):
        PROBE._positive_int("-2")
    assert PROBE._positive_int("5") == 5


def test_unavailable_slot_records_no_attempts(tmp_path, monkeypatch) -> None:
    for var in PROBE.ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)
    run_dir = PROBE.run_probe(
        _args(tmp_path, local=None, skip=["ceiling"], attempts=1),
        transport_factory=_FakeGoodTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    by_slot = {p["slot"]: p for p in manifest["panel"]}
    # cheap unresolved (no cli/env, never profile-inferred) -> unavailable
    assert by_slot["cheap"]["status"] == "unavailable"
    assert by_slot["cheap"]["attempts"] == 0
    assert by_slot["ceiling"]["status"] == "skipped"
    attempts_file = run_dir / "attempts.jsonl"
    if by_slot["local"]["status"] in ("unavailable", "skipped"):
        assert not attempts_file.exists()
```

Note on the last test: with `local=None` and no env vars, the local slot may
still resolve via profile inference if the active model profile's worker is
local-shaped. The assertions therefore only pin the cheap/ceiling slots and
make the attempts-file assertion conditional. Do not "fix" this by asserting
local is unavailable.

- [ ] **Step 3: Run the full probe test file**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py -v
```

Expected: all PASS (the offline end-to-end runs the REAL prompt renderer,
adapter, harness, and evaluator — only the transport is fake).

- [ ] **Step 4: Commit**

```powershell
git -C C:\UDEV\Rook-lm5k add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git -C C:\UDEV\Rook-lm5k commit -m "feat(lm5k): probe runner with evidence artifacts and offline end-to-end proof"
```

---

### Task 4: Gates

**Files:**
- None created; verification only (fix regressions if any gate fails).

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: the branch state the whole-branch review runs against.

- [ ] **Step 1: Full local-worker gate**

```powershell
cd C:\UDEV\Rook-lm5k
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
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py
```

Expected: all pass, zero failures.

- [ ] **Step 2: Exact scope assertion**

```powershell
git -C C:\UDEV\Rook-lm5k diff --check origin/main..HEAD
git -C C:\UDEV\Rook-lm5k diff --name-only origin/main..HEAD -- mcp_server/src
```

Expected: `diff --check` clean; `--name-only` output is exactly one line:

```text
mcp_server/src/rook/agent/local_worker_model_transport.py
```

Any second line under `mcp_server/src` is a scope violation — stop.

- [ ] **Step 3: Python 3.10 compatibility gate**

```powershell
cd C:\UDEV\Rook-lm5k
py -3.10 -m py_compile mcp_server\src\rook\agent\local_worker_model_transport.py scripts\lm5k_worker_probe.py mcp_server\tests\test_local_worker_model_transport.py mcp_server\tests\test_lm5k_worker_probe.py
```

Expected: silent, exit 0. If `py -3.10` is missing, report as a blocker —
never substitute the venv interpreter.

- [ ] **Step 4: Commit (only if fixes were needed)**

```powershell
git -C C:\UDEV\Rook-lm5k status --short
```

If Steps 1–3 required fixes, commit them with
`fix(lm5k): <what the gate caught>`; otherwise nothing to commit.

---

## Post-Merge Evidence Run (NOT part of this plan's merge gates)

After the branch merges, run the first live probe as evidence:

```powershell
cd C:\UDEV\Rook   # merged main
mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --cheap anthropic/claude-haiku-4-5 --ceiling anthropic/claude-sonnet-5
# local slot resolves from the active model profile, or pass --local explicitly
```

Then author the curated summary at
`docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md` per
spec §5.2 (paired `n/5 strict-loadable, m/5 spine-passing` counts,
failure-reason groupings, bounded excerpts only) and commit it through the
normal doc path. Model ids above are illustrative — resolve current ids at
run time; never assume a specific model is available.

## Completion Criteria

- Transport module with pinned `__all__`, reset-per-call + best-effort
  telemetry proven by tests, provider exceptions unwrapped, routing through
  `api_base_for_model`.
- Probe script: resolution order proven (CLI > env > profile-local-only >
  unavailable), candidate-status taxonomy proven including
  all-transport_error ≠ unavailable AND empty-attempts rejection
  (`classify_candidate_status([])` raises), paired metrics proven including
  the fenced-output split (strict 0 while status ran).
- Attempts validated positive at both the CLI (`_positive_int`) and
  `run_probe` (programmatic callers); 0 and negative rejected by tests.
- Offline end-to-end drives the real renderer/adapter/harness/evaluator with
  only the transport faked; `--capture-raw` behavior proven both ways.
- `probe_runs/` gitignored; production src diff = exactly the transport
  module; full gate green; 3.10 gate green.
- Merge remains gated on explicit user approval after review.
