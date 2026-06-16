# Rook Chat Model Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Slice 1 read-only model visibility for the RookChat panel through `GET /agent/chat/models`.

**Architecture:** Put model-resolution and local-provider detection in a focused Python helper under `rook.agent.chat`, then have the aiohttp chat server expose that helper through a nonce-gated endpoint. The helper must mirror real runtime resolution: planner and worker are env-aware, personas use `PromptBuilder.resolve_model_and_base()`, routing derives from `api_base_for_model()`, and local detection is bounded behind a short-TTL cache.

**Tech Stack:** Python 3, aiohttp chat server, pytest/aiohttp test utilities, existing `rook.agent.model_profiles`, `rook.agent.config`, and `rook.agent.chat.prompt_builder`.

---

## File Structure

- Create `mcp_server/src/rook/agent/chat/model_status.py`
  - Builds the `/agent/chat/models` payload.
  - Owns env-aware role resolution.
  - Owns local-provider detection normalization and short-TTL cache.
  - Owns `compute_allowed_model_overrides()` for Slice 1 endpoint and Slice 2 `/start` validation.
- Modify `mcp_server/src/rook/agent/chat/server.py`
  - Adds `handle_models()`.
  - Registers `GET /agent/chat/models`.
  - Sets `Cache-Control: no-store` on the response.
- Create `mcp_server/tests/test_chat_model_status.py`
  - Unit tests for helper behavior without aiohttp.
  - Resets the helper's module-level local-provider cache around each test.
- Modify `mcp_server/tests/test_chat_server.py`
  - Endpoint-level tests for response shape, nonce enforcement, and cache-control header.

---

### Task 1: Model Status Helper Tests

**Files:**
- Create: `mcp_server/tests/test_chat_model_status.py`
- Test target to be created later: `mcp_server/src/rook/agent/chat/model_status.py`

- [ ] **Step 1: Write failing tests for env-aware role resolution and allowed overrides**

Create `mcp_server/tests/test_chat_model_status.py` with this initial content:

```python
import pytest
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.chat import model_status
from rook.agent.model_profiles import ModelSet


@pytest.fixture(autouse=True)
def reset_model_status_cache():
    model_status.reset_local_provider_status_cache()
    yield
    model_status.reset_local_provider_status_cache()


def test_roles_apply_planner_and_worker_env_overrides(monkeypatch):
    monkeypatch.delenv("ROOK_MODEL_PROFILE", raising=False)
    monkeypatch.setenv("ROOK_PLANNER_MODEL", "anthropic/env-planner")
    monkeypatch.setenv("ROOK_WORKER_MODEL", "ollama_chat/env-worker")
    model_set = ModelSet(
        planner="anthropic/profile-planner",
        worker="anthropic/profile-worker",
        specialist="anthropic/profile-specialist",
        guardian="anthropic/profile-guardian",
        dspy="anthropic/profile-dspy",
        api_base=None,
    )
    monkeypatch.setattr(model_status, "get_active_profile_name", lambda: "cloud")
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: model_set,
    )

    roles = model_status.build_role_status()["roles"]

    assert roles["planner"]["profile_model"] == "anthropic/profile-planner"
    assert roles["planner"]["effective_model"] == "anthropic/env-planner"
    assert roles["planner"]["source"] == "env"
    assert roles["worker"]["profile_model"] == "anthropic/profile-worker"
    assert roles["worker"]["effective_model"] == "ollama_chat/env-worker"
    assert roles["worker"]["source"] == "env"
    assert roles["worker"]["routing"] == "local"


def test_allowed_overrides_use_effective_models_and_detected_local(monkeypatch):
    monkeypatch.delenv("ROOK_MODEL_PROFILE", raising=False)
    monkeypatch.setenv("ROOK_WORKER_MODEL", "anthropic/env-worker")
    model_set = ModelSet(
        planner="anthropic/profile-planner",
        worker="anthropic/profile-worker",
        specialist="anthropic/profile-specialist",
        guardian="anthropic/profile-guardian",
        dspy="anthropic/profile-dspy",
        api_base=None,
    )
    monkeypatch.setattr(model_status, "get_active_profile_name", lambda: "cloud")
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: model_set,
    )
    local_providers = {
        "ollama": {
            "available": True,
            "models": [
                {
                    "id": "qwen3:30b",
                    "model_override": "ollama_chat/qwen3:30b",
                    "size": None,
                }
            ],
            "recommended_model_override": "ollama_chat/qwen3:30b",
            "error": None,
        },
        "lmstudio": {
            "available": False,
            "models": [],
            "recommended_model_override": None,
            "api_base": "http://127.0.0.1:1234/v1",
            "error": "connection refused",
        },
    }

    allowed = model_status.compute_allowed_model_overrides(
        local_providers=local_providers
    )

    assert "anthropic/env-worker" in allowed
    assert "anthropic/profile-worker" not in allowed
    assert "ollama_chat/qwen3:30b" in allowed
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_chat_model_status.py -q
```

Expected: fails with `ImportError` or `ModuleNotFoundError` because `rook.agent.chat.model_status` does not exist yet.

- [ ] **Step 3: Commit failing tests**

```powershell
git add mcp_server/tests/test_chat_model_status.py
git commit -m "test: cover chat model status resolution"
```

---

### Task 2: Model Status Helper Implementation

**Files:**
- Create: `mcp_server/src/rook/agent/chat/model_status.py`
- Test: `mcp_server/tests/test_chat_model_status.py`

- [ ] **Step 1: Add the helper module**

Create `mcp_server/src/rook/agent/chat/model_status.py`:

```python
"""Model visibility helpers for the Rook chat service."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional, Tuple

from ..config import AgentConfig
from ..model_profiles import (
    ModelSet,
    api_base_for_model,
    detect_lmstudio_models,
    detect_ollama_models,
    get_active_profile_name,
    get_models,
)
from ..personas import available_personas, get_model_role, load_display_config
from .prompt_builder import PromptBuilder

LOCAL_DETECTION_TTL_SECONDS = 45.0
LOCAL_DETECTION_TIMEOUT_SECONDS = 1.5

_local_cache_payload: Optional[Dict[str, Any]] = None
_local_cache_time: float = 0.0


def reset_local_provider_status_cache() -> None:
    global _local_cache_payload, _local_cache_time
    _local_cache_payload = None
    _local_cache_time = 0.0


def _get_profile_model_set() -> Tuple[str, str, ModelSet]:
    env_profile = os.environ.get("ROOK_MODEL_PROFILE")
    active_profile = get_active_profile_name()
    if env_profile:
        return env_profile, "env", get_models(env_profile)
    if active_profile:
        return active_profile, "file", get_models(active_profile)
    return "fallback", "fallback", get_models()


def _routing_info(model: str, profile_api_base: Optional[str]) -> Dict[str, Any]:
    base = api_base_for_model(model, profile_api_base)
    local = (
        base is not None
        or model.startswith("ollama_chat/")
        or model.startswith("ollama/")
    )
    provider = model.split("/", 1)[0] if "/" in model else "local"
    return {
        "provider": provider,
        "routing": "local" if local else "cloud",
        "api_base": base,
    }


def _role_row(
    profile_model: str,
    effective_model: str,
    source: str,
    consumer: str,
    profile_api_base: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = {
        "profile_model": profile_model,
        "effective_model": effective_model,
        "source": source,
        **_routing_info(effective_model, profile_api_base),
        "consumer": consumer,
    }
    if extra:
        row.update(extra)
    return row


def _env_or_profile(env_name: str, profile_model: str) -> tuple[str, str]:
    value = os.environ.get(env_name)
    if value:
        return value, "env"
    return profile_model, "profile"


def build_role_status() -> Dict[str, Any]:
    active_profile, profile_source, models = _get_profile_model_set()
    planner_model, planner_source = _env_or_profile("ROOK_PLANNER_MODEL", models.planner)
    worker_model, worker_source = _env_or_profile("ROOK_WORKER_MODEL", models.worker)
    guardian_default = AgentConfig().guardian_llm_model

    roles = {
        "planner": _role_row(
            models.planner,
            planner_model,
            planner_source,
            "PlannerConfig.planner_model",
            models.api_base,
        ),
        "worker": _role_row(
            models.worker,
            worker_model,
            worker_source,
            "PlannerConfig.worker_model",
            models.api_base,
        ),
        "specialist": _role_row(
            models.specialist,
            models.specialist,
            "profile",
            "persona model_role",
            models.api_base,
        ),
        "guardian": _role_row(
            models.guardian,
            guardian_default,
            "agent_config_default",
            "GuardianConfig.llm_analysis_model",
            models.api_base,
            {
                "enabled_by_default": AgentConfig().guardian_llm_analysis,
                "note": (
                    "Profile guardian role is defined, but spawned Guardian LLM "
                    "analysis currently uses AgentConfig.guardian_llm_model."
                ),
            },
        ),
        "dspy": _role_row(
            models.dspy,
            models.dspy,
            "configured_at_startup",
            "DSPy global LM",
            models.api_base,
            {"live_switchable": False},
        ),
    }
    return {
        "active_profile": active_profile,
        "profile_source": profile_source,
        "roles": roles,
    }


def _normalize_ollama(raw: Dict[str, Any]) -> Dict[str, Any]:
    models = []
    for item in raw.get("models", []) or []:
        name = item.get("name")
        if not name:
            continue
        models.append({
            "id": name,
            "model_override": f"ollama_chat/{name}",
            "size": item.get("size"),
        })
    recommended = raw.get("largest_above_4gb")
    return {
        "available": bool(raw.get("ollama_available")),
        "models": models,
        "recommended_model_override": (
            f"ollama_chat/{recommended}" if recommended else None
        ),
        "error": raw.get("error"),
    }


def _normalize_lmstudio(raw: Dict[str, Any]) -> Dict[str, Any]:
    models = []
    for item in raw.get("models", []) or []:
        model_id = item.get("id")
        if not model_id:
            continue
        models.append({
            "id": model_id,
            "model_override": f"openai/{model_id}",
            "size": None,
        })
    return {
        "available": bool(raw.get("lmstudio_available")),
        "models": models,
        "recommended_model_override": raw.get("recommended"),
        "api_base": raw.get("api_base", "http://127.0.0.1:1234/v1"),
        "error": raw.get("error"),
    }


async def _run_probe(func):
    try:
        return await asyncio.to_thread(func, timeout=LOCAL_DETECTION_TIMEOUT_SECONDS)
    except Exception as exc:
        return {"error": str(exc)}


async def refresh_local_provider_status() -> Dict[str, Any]:
    ollama_raw, lmstudio_raw = await asyncio.gather(
        _run_probe(detect_ollama_models),
        _run_probe(detect_lmstudio_models),
    )
    return {
        "ollama": _normalize_ollama(ollama_raw),
        "lmstudio": _normalize_lmstudio(lmstudio_raw),
    }


async def get_cached_local_provider_status_async(
    force_refresh: bool = False,
) -> Dict[str, Any]:
    global _local_cache_payload, _local_cache_time
    now = time.monotonic()
    if (
        not force_refresh
        and _local_cache_payload is not None
        and now - _local_cache_time < LOCAL_DETECTION_TTL_SECONDS
    ):
        return _local_cache_payload
    _local_cache_payload = await refresh_local_provider_status()
    _local_cache_time = now
    return _local_cache_payload


def get_cached_local_provider_status_snapshot() -> Optional[Dict[str, Any]]:
    return _local_cache_payload


def get_cached_local_provider_status(force_refresh: bool = False) -> Dict[str, Any]:
    global _local_cache_payload, _local_cache_time
    now = time.monotonic()
    if (
        not force_refresh
        and _local_cache_payload is not None
        and now - _local_cache_time < LOCAL_DETECTION_TTL_SECONDS
    ):
        return _local_cache_payload
    _local_cache_payload = {
        "ollama": _normalize_ollama(detect_ollama_models(timeout=LOCAL_DETECTION_TIMEOUT_SECONDS)),
        "lmstudio": _normalize_lmstudio(detect_lmstudio_models(timeout=LOCAL_DETECTION_TIMEOUT_SECONDS)),
    }
    _local_cache_time = now
    return _local_cache_payload


def compute_allowed_model_overrides(
    local_providers: Optional[Dict[str, Any]] = None,
    role_status: Optional[Dict[str, Any]] = None,
) -> list[str]:
    role_status = role_status or build_role_status()
    allowed = {
        row["effective_model"]
        for row in role_status["roles"].values()
        if row.get("effective_model")
    }
    providers = local_providers or get_cached_local_provider_status()
    for provider in providers.values():
        for model in provider.get("models", []) or []:
            override = model.get("model_override")
            if override:
                allowed.add(override)
    return sorted(allowed)


async def compute_allowed_model_overrides_async(
    force_refresh: bool = False,
) -> list[str]:
    role_status = build_role_status()
    return compute_allowed_model_overrides(
        await get_cached_local_provider_status_async(force_refresh=force_refresh),
        role_status=role_status,
    )


def build_persona_status(builder: Optional[PromptBuilder] = None) -> list[Dict[str, Any]]:
    builder = builder or PromptBuilder()
    rows = []
    for persona in available_personas():
        display = load_display_config(persona)
        resolved_model, resolved_base = builder.resolve_model_and_base(persona)
        rows.append({
            "persona": persona,
            "label": display.get("label", persona),
            "model_role": get_model_role(persona),
            "resolved_model": resolved_model,
            "routing": "local" if (
                resolved_base is not None
                or resolved_model.startswith("ollama_chat/")
                or resolved_model.startswith("ollama/")
            ) else "cloud",
        })
    return rows


async def build_models_payload(builder: Optional[PromptBuilder] = None) -> Dict[str, Any]:
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async()
    return {
        **role_status,
        "personas": build_persona_status(builder),
        "local_providers": local_providers,
        "allowed_model_overrides": compute_allowed_model_overrides(
            local_providers,
            role_status=role_status,
        ),
    }
```

- [ ] **Step 2: Run helper tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_chat_model_status.py -q
```

Expected: tests pass.

- [ ] **Step 3: Commit helper implementation**

```powershell
git add mcp_server/src/rook/agent/chat/model_status.py mcp_server/tests/test_chat_model_status.py
git commit -m "feat: add chat model status helper"
```

---

### Task 3: Endpoint Tests

**Files:**
- Modify: `mcp_server/tests/test_chat_server.py`
- Test target: `mcp_server/src/rook/agent/chat/server.py`

- [ ] **Step 1: Add failing endpoint tests**

Append these tests to `TestChatServer` in `mcp_server/tests/test_chat_server.py`:

```python
    async def test_models_endpoint_returns_payload_and_no_store(self):
        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {"worker": {"effective_model": "anthropic/test-worker"}},
            "personas": [],
            "local_providers": {
                "ollama": {
                    "available": False,
                    "models": [],
                    "recommended_model_override": None,
                    "error": "connection refused",
                },
                "lmstudio": {
                    "available": False,
                    "models": [],
                    "recommended_model_override": None,
                    "api_base": "http://127.0.0.1:1234/v1",
                    "error": "connection refused",
                },
            },
            "allowed_model_overrides": ["anthropic/test-worker"],
        }
        with patch(
            "rook.agent.chat.server.build_models_payload",
            new=AsyncMock(return_value=payload),
        ):
            resp = await self.client.get("/agent/chat/models")

        assert resp.status == 200
        assert resp.headers["Cache-Control"] == "no-store"
        data = await resp.json()
        assert data == payload
```

Append this test to `TestChatServerWithNonce`:

```python
    async def test_models_endpoint_requires_nonce(self):
        resp = await self.client.get("/agent/chat/models")
        assert resp.status == 403

    async def test_models_endpoint_with_nonce_succeeds(self):
        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {},
            "personas": [],
            "local_providers": {},
            "allowed_model_overrides": [],
        }
        with patch(
            "rook.agent.chat.server.build_models_payload",
            new=AsyncMock(return_value=payload),
        ):
            resp = await self.client.get(
                "/agent/chat/models",
                headers={"X-Rook-Session": self.nonce},
            )

        assert resp.status == 200
```

- [ ] **Step 2: Run endpoint tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_chat_server.py::TestChatServer::test_models_endpoint_returns_payload_and_no_store tests/test_chat_server.py::TestChatServerWithNonce::test_models_endpoint_requires_nonce tests/test_chat_server.py::TestChatServerWithNonce::test_models_endpoint_with_nonce_succeeds -q
```

Expected: fails because `/agent/chat/models` is not registered and `build_models_payload` is not imported in `server.py`.

- [ ] **Step 3: Commit failing endpoint tests**

```powershell
git add mcp_server/tests/test_chat_server.py
git commit -m "test: cover chat models endpoint"
```

---

### Task 4: Endpoint Implementation

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Test: `mcp_server/tests/test_chat_server.py`

- [ ] **Step 1: Import the payload builder**

In `mcp_server/src/rook/agent/chat/server.py`, add this import with the other chat imports:

```python
from .model_status import build_models_payload
```

- [ ] **Step 2: Add the handler**

Add this handler near `handle_personas`:

```python
async def handle_models(request: web.Request) -> web.Response:
    """GET /agent/chat/models - resolved model visibility for the chat panel."""
    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    payload = await build_models_payload(builder)
    return web.json_response(
        payload,
        headers={"Cache-Control": "no-store"},
    )
```

- [ ] **Step 3: Register the route**

In `create_chat_app()`, register the route next to the other `/agent/chat/*` routes:

```python
    app.router.add_get("/agent/chat/models", handle_models)
```

- [ ] **Step 4: Run endpoint tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_chat_server.py::TestChatServer::test_models_endpoint_returns_payload_and_no_store tests/test_chat_server.py::TestChatServerWithNonce::test_models_endpoint_requires_nonce tests/test_chat_server.py::TestChatServerWithNonce::test_models_endpoint_with_nonce_succeeds -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run helper tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_chat_model_status.py -q
```

Expected: all helper tests pass.

- [ ] **Step 6: Commit endpoint implementation**

```powershell
git add mcp_server/src/rook/agent/chat/server.py mcp_server/tests/test_chat_server.py
git commit -m "feat: expose chat model visibility endpoint"
```

---

### Task 5: Full Slice 1 Verification

**Files:**
- Verify only; no file edits expected.

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_chat_model_status.py tests/test_chat_server.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Confirm no unintended files are staged**

Run:

```powershell
git status --short
```

Expected: no staged files. Existing unrelated `third_party/ffmpeg/*` modifications may still appear unstaged and should not be touched.

- [ ] **Step 3: Record Slice 2 dependency**

Open a follow-up issue or add an implementation note in the PR body:

```text
Slice 2 should reuse rook.agent.chat.model_status.compute_allowed_model_overrides_async()
or get_cached_local_provider_status_snapshot() to validate /agent/chat/start
model_override without probing local providers on the hot path.

When Slice 2 accepts a detected LM Studio override (`openai/<id>`), it must
route that conversation with the server-side detected LM Studio api_base from
the cached local-provider status. Do not rely on the active profile api_base,
because a cloud profile has no LM Studio base and would misroute the override.
```

Expected: reviewer can see the helper is intentionally reusable and Slice 2 validation will not duplicate detection logic.

---

## Self-Review

- Spec coverage: The plan covers the approved Slice 1 endpoint, env-aware roles, persona resolution through `PromptBuilder`, bounded cached detection, no-store response, nonce enforcement, and effective-model allowed overrides.
- Scope check: The plan excludes persistent profile writes and selector UI, keeping Slice 1 independently reviewable.
- Type consistency: Function names are consistent across tasks: `reset_local_provider_status_cache`, `build_role_status`, `get_cached_local_provider_status_async`, `compute_allowed_model_overrides`, `build_persona_status`, and `build_models_payload`.
- Review feedback folded in: The plan avoids double role resolution in `build_models_payload`, resets the module-level detection cache around helper tests, and records the Slice 2 LM Studio `api_base` routing requirement.
