# RookLLM Chooser Slice 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add agent-mediated, per-conversation model setting for RookChat, with validated overrides, server-side LM Studio `api_base` binding, and text feedback through the existing chat panel.

**Architecture:** A shared Python resolver validates every requested `model_override` against Slice 1 `allowed_model_overrides` and atomically binds `model/api_base`. The primary path is a ChatRunner pseudo-tool (`set_chat_model`) that stages the change during the active turn and applies it in `run_turn()`'s `finally` before `active_run_id` is cleared, so it affects the next turn even if the current turn errors or is aborted. A nonce-gated `/agent/chat/model` endpoint is a secondary out-of-band fallback and rejects active conversations with `409`.

**Tech Stack:** Python 3.13, aiohttp, pytest, LiteLLM tool-call schemas, C#/.NET Framework panel client, Eto/WebView chat surface.

---

## Scope And Invariants

This plan implements the approved design in `docs/superpowers/specs/2026-06-16-rookllm-chooser-slice2-design.md`.

Hard invariants:

- No free-form model string reaches LiteLLM. All override paths validate against `allowed_model_overrides`.
- No client-supplied `api_base` is accepted or used.
- Detected LM Studio overrides (`openai/<id>` from `local_providers["lmstudio"]["models"]`) use the server-side detected `local_providers["lmstudio"]["api_base"]`, not the active profile's `api_base`.
- `model` and `api_base` are updated atomically through `Conversation` helpers.
- Agent-tool `set_chat_model` is a synchronous-result pseudo-tool: validate, stage pending, append an inline tool result, emit `model_update`, and continue the agent turn. It does not suspend for UI response and does not return `409` because the turn is active.
- Out-of-band `/agent/chat/model` rejects while `conv.active_run_id is not None`.
- Pending model switches apply even when the current turn errors, hits abort, or exits through `finally`. The switch is independent of turn success.
- `/agent/chat/models` without `conversation_id` behaves exactly like Slice 1.

Known baseline:

- `python -m pytest tests/test_chat_server.py -q` has two unrelated knowledge graph failures on `main`: `TestKnowledgeGraphRoutes.test_knowledge_graph_returns_valid_payload` and `TestKnowledgeGraphRoutes.test_knowledge_note_found`.

---

## File Structure

Python:

- Modify `mcp_server/src/rook/agent/chat/model_status.py`
  - Add `ModelOverrideResolution`, `ModelOverrideUnavailable`, resolver helpers, and conversation-status helpers.
  - Keep local provider detection async-only.
- Modify `mcp_server/src/rook/agent/chat/conversation_store.py`
  - Add active/pending model metadata and atomic helper methods.
- Modify `mcp_server/src/rook/agent/chat/server.py`
  - Validate `/agent/chat/start` overrides.
  - Add nonce-gated `POST /agent/chat/model`.
  - Extend `GET /agent/chat/models` with optional `conversation_id`.
- Modify `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Add typed schemas for `list_chat_models` and `set_chat_model`.
  - Intercept those pseudo-tools in the tool dispatch loop.
  - Apply pending model switches in `finally` before clearing `active_run_id`.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add sentinel local tools so the model tools appear in the ChatRunner tool catalog.

Tests:

- Modify `mcp_server/tests/test_chat_model_status.py`
- Modify `mcp_server/tests/test_chat_server.py`
- Add `mcp_server/tests/test_chat_runner_model_tools.py`

C#:

- Modify `src/Rook/UI/Chat/AgentChatClient.cs`
  - Add response DTOs and `GetModelsAsync`.
  - Add `Model` and `AppliesTo` fields to `ChatEvent`.
- Modify `src/Rook/UI/Chat/AgentChatTab.cs`
  - Refresh and show text model status after start, model-update events, and turn completion.

---

## Task 1: Shared Model Override Resolver

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/model_status.py`
- Test: `mcp_server/tests/test_chat_model_status.py`

- [ ] **Step 1: Add failing resolver tests**

Append these tests to `mcp_server/tests/test_chat_model_status.py`.

```python
@pytest.mark.asyncio
async def test_resolve_allowed_model_override_rejects_unavailable(monkeypatch):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {"ollama": {"models": []}, "lmstudio": {"models": []}}

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)
    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        AsyncMock(return_value=local_providers),
    )

    with pytest.raises(model_status.ModelOverrideUnavailable) as exc_info:
        await model_status.resolve_allowed_model_override("openai/not-allowed")

    err = exc_info.value.to_payload()
    assert err == {
        "error": "Model override is not currently available. Refresh the model list and try again.",
        "code": "model_override_unavailable",
        "model_override": "openai/not-allowed",
        "allowed_model_overrides": ["anthropic/worker"],
    }


@pytest.mark.asyncio
async def test_resolve_allowed_model_override_uses_detected_lmstudio_api_base(monkeypatch):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {
        "ollama": {"models": []},
        "lmstudio": {
            "available": True,
            "api_base": "http://127.0.0.1:1234/v1",
            "models": [
                {
                    "id": "lmstudio-community/qwen",
                    "model_override": "openai/lmstudio-community/qwen",
                    "size": None,
                }
            ],
        },
    }

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)
    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        AsyncMock(return_value=local_providers),
    )

    resolution = await model_status.resolve_allowed_model_override(
        "openai/lmstudio-community/qwen"
    )

    assert resolution.model_override == "openai/lmstudio-community/qwen"
    assert resolution.api_base == "http://127.0.0.1:1234/v1"
    assert resolution.routing == "local"
    assert resolution.provider == "openai"
    assert resolution.api_base_source == "detected_lmstudio"


@pytest.mark.asyncio
async def test_resolve_allowed_model_override_uses_profile_for_profile_models(monkeypatch):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {"ollama": {"models": []}, "lmstudio": {"models": []}}

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)
    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        AsyncMock(return_value=local_providers),
    )

    resolution = await model_status.resolve_allowed_model_override("anthropic/worker")

    assert resolution.model_override == "anthropic/worker"
    assert resolution.api_base == ""
    assert resolution.routing == "cloud"
    assert resolution.provider == "anthropic"
    assert resolution.api_base_source == "none"
```

If `AsyncMock` is not already imported in this file, add:

```python
from unittest.mock import AsyncMock
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
cd C:\Users\aryan\source\repos\Rook\.worktrees\rookllm-chooser-slice2-design\mcp_server
python -m pytest tests/test_chat_model_status.py::test_resolve_allowed_model_override_rejects_unavailable tests/test_chat_model_status.py::test_resolve_allowed_model_override_uses_detected_lmstudio_api_base tests/test_chat_model_status.py::test_resolve_allowed_model_override_uses_profile_for_profile_models -q
```

Expected: failure because `ModelOverrideUnavailable` and `resolve_allowed_model_override` do not exist.

- [ ] **Step 3: Implement resolver types and helpers**

In `mcp_server/src/rook/agent/chat/model_status.py`, add imports:

```python
from dataclasses import dataclass
```

Add these definitions below `_GUARDIAN_NOTE`:

```python
_MODEL_OVERRIDE_UNAVAILABLE_MESSAGE = (
    "Model override is not currently available. Refresh the model list and try again."
)


@dataclass(frozen=True)
class ModelOverrideResolution:
    """Validated model override with server-bound routing metadata."""

    model_override: str
    api_base: str
    routing: str
    provider: str
    api_base_source: str

    def to_payload(self) -> dict:
        return {
            "model_override": self.model_override,
            "api_base": self.api_base,
            "routing": self.routing,
            "provider": self.provider,
            "api_base_source": self.api_base_source,
        }


class ModelOverrideUnavailable(ValueError):
    """Raised when a requested model override is not currently allowed."""

    def __init__(self, model_override: str, allowed_model_overrides: list[str]):
        super().__init__(_MODEL_OVERRIDE_UNAVAILABLE_MESSAGE)
        self.model_override = model_override
        self.allowed_model_overrides = allowed_model_overrides

    def to_payload(self) -> dict:
        return {
            "error": _MODEL_OVERRIDE_UNAVAILABLE_MESSAGE,
            "code": "model_override_unavailable",
            "model_override": self.model_override,
            "allowed_model_overrides": self.allowed_model_overrides,
        }
```

Add these helpers near `compute_allowed_model_overrides_async`:

```python
def _provider_for_model(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "local"


def _detected_lmstudio_api_base(
    model_override: str,
    local_providers: dict,
) -> Optional[str]:
    lmstudio = (local_providers or {}).get("lmstudio") or {}
    for model in lmstudio.get("models") or []:
        if model.get("model_override") == model_override:
            return lmstudio.get("api_base") or "http://127.0.0.1:1234/v1"
    return None


def _bound_routing(model: str, api_base: str) -> str:
    if api_base:
        return "local"
    if model.startswith("ollama_chat/") or model.startswith("ollama/"):
        return "local"
    return "cloud"


async def resolve_allowed_model_override(
    model_override: str,
    *,
    force_refresh: bool = False,
) -> ModelOverrideResolution:
    """Validate a model override and bind server-side routing metadata."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async(
        force_refresh=force_refresh
    )
    allowed_model_overrides = compute_allowed_model_overrides(
        local_providers=local_providers,
        role_status=role_status,
    )
    if model_override not in allowed_model_overrides:
        raise ModelOverrideUnavailable(model_override, allowed_model_overrides)

    lmstudio_api_base = _detected_lmstudio_api_base(model_override, local_providers)
    if lmstudio_api_base:
        api_base = lmstudio_api_base
        api_base_source = "detected_lmstudio"
    else:
        model_set = get_models()
        api_base = api_base_for_model(model_override, model_set.api_base) or ""
        api_base_source = "active_profile" if api_base else "none"

    return ModelOverrideResolution(
        model_override=model_override,
        api_base=api_base,
        routing=_bound_routing(model_override, api_base),
        provider=_provider_for_model(model_override),
        api_base_source=api_base_source,
    )
```

- [ ] **Step 4: Run resolver tests**

Run:

```powershell
python -m pytest tests/test_chat_model_status.py::test_resolve_allowed_model_override_rejects_unavailable tests/test_chat_model_status.py::test_resolve_allowed_model_override_uses_detected_lmstudio_api_base tests/test_chat_model_status.py::test_resolve_allowed_model_override_uses_profile_for_profile_models -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run full helper tests**

Run:

```powershell
python -m pytest tests/test_chat_model_status.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/model_status.py mcp_server/tests/test_chat_model_status.py
git commit -m "feat: validate chat model overrides"
```

---

## Task 2: Conversation Model State And Atomic Pending Apply

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/conversation_store.py`
- Test: `mcp_server/tests/test_chat_model_status.py`

- [ ] **Step 1: Add failing conversation state tests**

Append to `mcp_server/tests/test_chat_model_status.py`:

```python
def test_conversation_applies_model_override_atomically():
    from rook.agent.chat.conversation_store import Conversation

    conv = Conversation(id="conv_test", persona="worker")
    resolution = model_status.ModelOverrideResolution(
        model_override="openai/lmstudio-community/qwen",
        api_base="http://127.0.0.1:1234/v1",
        routing="local",
        provider="openai",
        api_base_source="detected_lmstudio",
    )

    payload = conv.apply_model_override(
        resolution,
        source="start_override",
        reason="user requested local model",
    )

    assert conv.model == "openai/lmstudio-community/qwen"
    assert conv.api_base == "http://127.0.0.1:1234/v1"
    assert conv.model_source == "start_override"
    assert conv.api_base_source == "detected_lmstudio"
    assert payload["active_model"] == "openai/lmstudio-community/qwen"
    assert payload["api_base_source"] == "detected_lmstudio"


def test_conversation_stages_and_applies_pending_model():
    from rook.agent.chat.conversation_store import Conversation

    conv = Conversation(id="conv_test", persona="worker")
    conv.model = "anthropic/worker"
    conv.api_base = ""
    conv.model_source = "persona"
    conv.api_base_source = "none"

    resolution = model_status.ModelOverrideResolution(
        model_override="ollama_chat/qwen3:30b",
        api_base="",
        routing="local",
        provider="ollama_chat",
        api_base_source="none",
    )

    staged = conv.stage_model_override(
        resolution,
        source="agent_tool",
        reason="use local qwen",
    )
    assert staged["pending_model"] == "ollama_chat/qwen3:30b"
    assert conv.model == "anthropic/worker"

    applied = conv.apply_pending_model_override()

    assert applied is not None
    assert applied["active_model"] == "ollama_chat/qwen3:30b"
    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.pending_model == ""
    assert conv.pending_api_base == ""
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_chat_model_status.py::test_conversation_applies_model_override_atomically tests/test_chat_model_status.py::test_conversation_stages_and_applies_pending_model -q
```

Expected: failure because `Conversation` lacks the new fields and methods.

- [ ] **Step 3: Implement conversation state helpers**

Modify the `Conversation` dataclass in `mcp_server/src/rook/agent/chat/conversation_store.py`:

```python
@dataclass
class Conversation:
    """A single active conversation with an agent persona."""
    id: str
    persona: str
    document_serial_number: int = 0
    model: str = ""
    api_base: str = ""
    model_source: str = ""
    api_base_source: str = ""
    pending_model: str = ""
    pending_api_base: str = ""
    pending_model_source: str = ""
    pending_api_base_source: str = ""
    pending_model_reason: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    active_run_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
```

Add helper methods to `Conversation`:

```python
    def _model_payload(
        self,
        *,
        active: bool,
        applies_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        prefix = "active" if active else "pending"
        model = self.model if active else self.pending_model
        api_base = self.api_base if active else self.pending_api_base
        model_source = self.model_source if active else self.pending_model_source
        api_base_source = (
            self.api_base_source if active else self.pending_api_base_source
        )
        routing = "local" if api_base or model.startswith(("ollama_chat/", "ollama/")) else "cloud"
        payload: Dict[str, Any] = {
            f"{prefix}_model": model,
            f"{prefix}_routing": routing,
            "model_source": model_source,
            "api_base_source": api_base_source,
        }
        if applies_to:
            payload["applies_to"] = applies_to
        return payload

    def apply_model_override(
        self,
        resolution: Any,
        *,
        source: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Atomically apply an active model/api_base pair."""
        self.model = resolution.model_override
        self.api_base = resolution.api_base
        self.model_source = source
        self.api_base_source = resolution.api_base_source
        self.pending_model = ""
        self.pending_api_base = ""
        self.pending_model_source = ""
        self.pending_api_base_source = ""
        self.pending_model_reason = ""
        self.touch()
        return self._model_payload(active=True)

    def stage_model_override(
        self,
        resolution: Any,
        *,
        source: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Stage a model/api_base pair for the next turn."""
        self.pending_model = resolution.model_override
        self.pending_api_base = resolution.api_base
        self.pending_model_source = source
        self.pending_api_base_source = resolution.api_base_source
        self.pending_model_reason = reason
        self.touch()
        return self._model_payload(active=False, applies_to="next_turn")

    def apply_pending_model_override(self) -> Optional[Dict[str, Any]]:
        """Promote a staged model/api_base pair to active, if present."""
        if not self.pending_model:
            return None
        self.model = self.pending_model
        self.api_base = self.pending_api_base
        self.model_source = self.pending_model_source
        self.api_base_source = self.pending_api_base_source
        self.pending_model = ""
        self.pending_api_base = ""
        self.pending_model_source = ""
        self.pending_api_base_source = ""
        self.pending_model_reason = ""
        self.touch()
        return self._model_payload(active=True)
```

Update `list_conversations()` rows to include `api_base_source` and pending state:

```python
                "api_base_source": c.api_base_source,
                "pending_model": c.pending_model or None,
                "pending_api_base_source": c.pending_api_base_source or None,
```

- [ ] **Step 4: Run conversation tests**

Run:

```powershell
python -m pytest tests/test_chat_model_status.py::test_conversation_applies_model_override_atomically tests/test_chat_model_status.py::test_conversation_stages_and_applies_pending_model -q
```

Expected: selected tests pass.

- [ ] **Step 5: Run helper tests**

Run:

```powershell
python -m pytest tests/test_chat_model_status.py -q
```

Expected: all helper tests pass.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/conversation_store.py mcp_server/tests/test_chat_model_status.py
git commit -m "feat: track chat conversation model state"
```

**Review checkpoint:** Stop after Task 2 and surface the diff if requested. This is the state boundary every later route and pseudo-tool depends on.

---

## Task 3: Validate `/start` And Add `/agent/chat/model`

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Test: `mcp_server/tests/test_chat_server.py`

- [ ] **Step 1: Add failing `/start` and `/model` route tests**

Add these tests inside `TestChatServer` in `mcp_server/tests/test_chat_server.py`:

```python
    async def test_start_rejects_unavailable_model_override(self):
        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=AsyncMock(
                side_effect=chat_server.model_status.ModelOverrideUnavailable(
                    "openai/not-allowed",
                    ["anthropic/worker"],
                )
            ),
        ):
            resp = await self.client.post(
                "/agent/chat/start",
                json={
                    "persona": "worker",
                    "model_override": "openai/not-allowed",
                    "api_base": "http://attacker.invalid/v1",
                },
            )

        assert resp.status == 400
        data = await resp.json()
        assert data["code"] == "model_override_unavailable"
        assert data["model_override"] == "openai/not-allowed"
        assert self.store.list_conversations() == []

    async def test_start_applies_detected_lmstudio_resolution(self):
        resolution = chat_server.model_status.ModelOverrideResolution(
            model_override="openai/lmstudio-community/qwen",
            api_base="http://127.0.0.1:1234/v1",
            routing="local",
            provider="openai",
            api_base_source="detected_lmstudio",
        )
        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=AsyncMock(return_value=resolution),
        ):
            resp = await self.client.post(
                "/agent/chat/start",
                json={
                    "persona": "worker",
                    "model_override": "openai/lmstudio-community/qwen",
                    "api_base": "http://attacker.invalid/v1",
                },
            )

        assert resp.status == 200
        data = await resp.json()
        conv = self.store.get(data["conversation_id"])
        assert conv is not None
        assert conv.model == "openai/lmstudio-community/qwen"
        assert conv.api_base == "http://127.0.0.1:1234/v1"
        assert conv.api_base_source == "detected_lmstudio"
        assert data["model"] == "openai/lmstudio-community/qwen"
```

Add these tests inside `TestChatServer` too:

```python
    async def test_set_conversation_model_rejects_while_active(self):
        conv = self.store.create("worker")
        conv.active_run_id = "running"

        resp = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": conv.id,
                "model_override": "anthropic/worker",
            },
        )

        assert resp.status == 409
        data = await resp.json()
        assert data["code"] == "conversation_processing"

    async def test_set_conversation_model_applies_when_inactive(self):
        conv = self.store.create("worker")
        resolution = chat_server.model_status.ModelOverrideResolution(
            model_override="ollama_chat/qwen3:30b",
            api_base="",
            routing="local",
            provider="ollama_chat",
            api_base_source="none",
        )

        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=AsyncMock(return_value=resolution),
        ):
            resp = await self.client.post(
                "/agent/chat/model",
                json={
                    "conversation_id": conv.id,
                    "model_override": "ollama_chat/qwen3:30b",
                    "api_base": "http://attacker.invalid/v1",
                },
            )

        assert resp.status == 200
        data = await resp.json()
        assert data["conversation_id"] == conv.id
        assert data["active_model"] == "ollama_chat/qwen3:30b"
        assert conv.model == "ollama_chat/qwen3:30b"
        assert conv.api_base == ""
```

Add this test inside `TestChatServerWithNonce`:

```python
    async def test_set_conversation_model_requires_nonce(self):
        resp = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": "conv_missing",
                "model_override": "anthropic/worker",
            },
        )
        assert resp.status == 403
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_chat_server.py::TestChatServer::test_start_rejects_unavailable_model_override tests/test_chat_server.py::TestChatServer::test_start_applies_detected_lmstudio_resolution tests/test_chat_server.py::TestChatServer::test_set_conversation_model_rejects_while_active tests/test_chat_server.py::TestChatServer::test_set_conversation_model_applies_when_inactive tests/test_chat_server.py::TestChatServerWithNonce::test_set_conversation_model_requires_nonce -q
```

Expected: failures because `/start` is not validating and `/agent/chat/model` is not registered.

- [ ] **Step 3: Refactor `/start` to validate overrides before storing rejected conversations**

In `mcp_server/src/rook/agent/chat/server.py`, update `handle_start` immediately after this existing line:

```python
    builder = request.app.get(_BUILDER_KEY) or _get_builder()
```

```python
    resolved_model, resolved_base = builder.resolve_model_and_base(persona)
    model_override = body.get("model_override")
    override_resolution = None
    if model_override:
        try:
            override_resolution = await model_status.resolve_allowed_model_override(
                model_override
            )
        except model_status.ModelOverrideUnavailable as exc:
            return web.json_response(exc.to_payload(), status=400)
```

Then create the conversation and apply model atomically:

```python
    try:
        conv = store.create(persona, document_serial_number=document_serial_number)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=429)

    if override_resolution is not None:
        conv.apply_model_override(
            override_resolution,
            source="start_override",
            reason="model_override supplied to /agent/chat/start",
        )
    else:
        conv.model = resolved_model
        conv.api_base = resolved_base or ""
        conv.model_source = "persona"
        conv.api_base_source = "prompt_builder" if conv.api_base else "none"
```

Remove the old inline `from ..model_profiles import get_models, api_base_for_model` override branch. This is an intentional `/start` contract tightening: unsupported model overrides now reject instead of flowing to LiteLLM.

- [ ] **Step 4: Add `/agent/chat/model` handler and route**

Add a handler in `server.py` near `handle_start`:

```python
async def handle_set_model(request: web.Request) -> web.Response:
    """POST /agent/chat/model — set a conversation model out-of-band."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    model_override = body.get("model_override")
    if not conv_id or not model_override:
        return web.json_response(
            {"error": "Missing conversation_id or model_override"},
            status=400,
        )

    store = request.app.get(_STORE_KEY) or _get_store()
    conv = store.get(conv_id)
    if conv is None:
        return web.json_response({"error": "Conversation not found"}, status=404)

    if conv.active_run_id is not None:
        return web.json_response(
            {
                "error": "Conversation already processing. Try again after the current turn finishes.",
                "code": "conversation_processing",
            },
            status=409,
        )

    try:
        resolution = await model_status.resolve_allowed_model_override(model_override)
    except model_status.ModelOverrideUnavailable as exc:
        return web.json_response(exc.to_payload(), status=400)

    payload = conv.apply_model_override(
        resolution,
        source="panel_endpoint",
        reason=str(body.get("reason") or ""),
    )
    payload["conversation_id"] = conv.id
    payload["persona"] = conv.persona
    return web.json_response(payload)
```

Register the route in `create_chat_app()`:

```python
    app.router.add_post("/agent/chat/model", handle_set_model)
```

- [ ] **Step 5: Run route tests**

Run:

```powershell
python -m pytest tests/test_chat_server.py::TestChatServer::test_start_rejects_unavailable_model_override tests/test_chat_server.py::TestChatServer::test_start_applies_detected_lmstudio_resolution tests/test_chat_server.py::TestChatServer::test_set_conversation_model_rejects_while_active tests/test_chat_server.py::TestChatServer::test_set_conversation_model_applies_when_inactive tests/test_chat_server.py::TestChatServerWithNonce::test_set_conversation_model_requires_nonce -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/server.py mcp_server/tests/test_chat_server.py
git commit -m "feat: validate chat model mutations"
```

---

## Task 4: Conversation-Aware Agent Pseudo-Tools

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Create: `mcp_server/tests/test_chat_runner_model_tools.py`

- [ ] **Step 1: Add failing ChatRunner pseudo-tool tests**

Create `mcp_server/tests/test_chat_runner_model_tools.py`:

```python
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat.conversation_store import Conversation
from rook.agent.chat import model_status


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta):
        self.choices = [_Choice(delta)]


class _ToolDelta:
    def __init__(self, index, tool_id=None, name=None, arguments=None):
        self.index = index
        self.id = tool_id
        self.function = type(
            "Fn",
            (),
            {"name": name or "", "arguments": arguments or ""},
        )()


async def _stream_chunks(chunks):
    for chunk in chunks:
        yield chunk


def _tool_call_chunks(name, arguments):
    return [
        _Chunk(_Delta(tool_calls=[_ToolDelta(0, tool_id="tool_1")])),
        _Chunk(_Delta(tool_calls=[_ToolDelta(0, name=name)])),
        _Chunk(_Delta(tool_calls=[_ToolDelta(0, arguments=json.dumps(arguments))])),
    ]


@pytest.mark.asyncio
async def test_set_chat_model_stages_pending_and_does_not_change_current_turn(monkeypatch):
    conv = Conversation(id="conv_test", persona="worker")
    conv.model = "anthropic/current"
    conv.api_base = ""
    calls = []
    resolution = model_status.ModelOverrideResolution(
        model_override="ollama_chat/qwen3:30b",
        api_base="",
        routing="local",
        provider="ollama_chat",
        api_base_source="none",
    )

    async def fake_completion(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            return _stream_chunks(
                _tool_call_chunks(
                    "set_chat_model",
                    {
                        "model_override": "ollama_chat/qwen3:30b",
                        "reason": "user asked",
                    },
                )
            )
        return _stream_chunks([_Chunk(_Delta(content="Switched for next turn."))])

    monkeypatch.setattr(
        model_status,
        "resolve_allowed_model_override",
        AsyncMock(return_value=resolution),
    )
    monkeypatch.setattr(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}}),
    )

    runner = ChatRunner(tool_executor=AsyncMock())
    with patch("rook.agent.chat.chat_runner.litellm.acompletion", fake_completion):
        events = [
            event
            async for event in runner.run_turn(conv, "use qwen", "system")
        ]

    assert calls == ["anthropic/current", "anthropic/current"]
    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.pending_model == ""
    assert any(e.type == "model_update" and e.applies_to == "next_turn" for e in events)
    assert any(e.type == "model_update" and e.applies_to == "active" for e in events)


@pytest.mark.asyncio
async def test_set_chat_model_applies_pending_even_when_turn_errors(monkeypatch):
    conv = Conversation(id="conv_test", persona="worker")
    conv.model = "anthropic/current"
    resolution = model_status.ModelOverrideResolution(
        model_override="ollama_chat/qwen3:30b",
        api_base="",
        routing="local",
        provider="ollama_chat",
        api_base_source="none",
    )

    async def fake_completion(**kwargs):
        return _stream_chunks(
            _tool_call_chunks(
                "set_chat_model",
                {"model_override": "ollama_chat/qwen3:30b"},
            )
        )

    monkeypatch.setattr(
        model_status,
        "resolve_allowed_model_override",
        AsyncMock(return_value=resolution),
    )
    monkeypatch.setattr(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}}),
    )

    runner = ChatRunner(tool_executor=AsyncMock())
    with patch("rook.agent.chat.chat_runner.litellm.acompletion", fake_completion):
        events = []
        async for event in runner.run_turn(conv, "use qwen", "system"):
            events.append(event)
            if event.type == "model_update" and event.applies_to == "next_turn":
                conv.abort_event.set()

    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.active_run_id is None
    assert any(e.type == "model_update" and e.applies_to == "active" for e in events)


@pytest.mark.asyncio
async def test_list_chat_models_returns_inline_tool_result(monkeypatch):
    conv = Conversation(id="conv_test", persona="worker")
    conv.model = "anthropic/current"
    payload = {
        "active_profile": "cloud",
        "roles": {},
        "local_providers": {},
        "allowed_model_overrides": ["anthropic/current"],
    }

    async def fake_completion(**kwargs):
        if not conv.messages or conv.messages[-1]["role"] == "user":
            return _stream_chunks(_tool_call_chunks("list_chat_models", {}))
        return _stream_chunks([_Chunk(_Delta(content="You can use anthropic/current."))])

    monkeypatch.setattr(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}}),
    )

    runner = ChatRunner(tool_executor=AsyncMock())
    with patch("rook.agent.chat.chat_runner.litellm.acompletion", fake_completion):
        events = [
            event
            async for event in runner.run_turn(
                conv,
                "what models are available?",
                "system",
                model_payload_builder=AsyncMock(return_value=payload),
            )
        ]

    tool_messages = [m for m in conv.messages if m.get("role") == "tool"]
    assert tool_messages
    assert json.loads(tool_messages[-1]["content"])["allowed_model_overrides"] == [
        "anthropic/current"
    ]
    assert any(e.type == "tool_result" and e.name == "list_chat_models" for e in events)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_chat_runner_model_tools.py -q
```

Expected: failure because the pseudo-tools and `model_update` event fields are not implemented.

- [ ] **Step 3: Add sentinel local tools**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add sentinels in `build_local_tools()` near the `ui_block` sentinel:

```python
    async def _chat_model_sentinel(**kwargs):
        return {
            "success": False,
            "data": "chat model tools must be intercepted by ChatRunner.",
        }

    tools["list_chat_models"] = _chat_model_sentinel
    tools["set_chat_model"] = _chat_model_sentinel
```

- [ ] **Step 4: Add ChatEvent fields and typed schemas**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, add fields to `ChatEvent`:

```python
    model: Optional[str] = None
    applies_to: Optional[str] = None
```

Add them to `to_dict()`:

```python
        if self.model is not None:
            d["model"] = self.model
        if self.applies_to is not None:
            d["applies_to"] = self.applies_to
```

Add tool descriptions:

```python
    "list_chat_models": "List validated chat model overrides available for this conversation.",
    "set_chat_model": "Set this chat conversation's model for the next user turn. Accepts only validated model_override strings.",
```

Add typed schemas near `_UI_BLOCK_SCHEMA`:

```python
_LIST_CHAT_MODELS_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "list_chat_models",
        "description": _TOOL_DESCRIPTIONS["list_chat_models"],
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}


_SET_CHAT_MODEL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "set_chat_model",
        "description": _TOOL_DESCRIPTIONS["set_chat_model"],
        "parameters": {
            "type": "object",
            "properties": {
                "model_override": {
                    "type": "string",
                    "description": "One exact model_override from list_chat_models or /agent/chat/models.",
                },
                "reason": {
                    "type": "string",
                    "description": "Short explanation of why the user requested this model.",
                },
            },
            "required": ["model_override"],
            "additionalProperties": False,
        },
    },
}
```

Update `_build_local_tool_catalog()`:

```python
        if name == "list_chat_models":
            catalog[name] = _LIST_CHAT_MODELS_SCHEMA
            continue
        if name == "set_chat_model":
            catalog[name] = _SET_CHAT_MODEL_SCHEMA
            continue
```

- [ ] **Step 5: Add run_turn model payload dependency and pseudo-tool handlers**

Change the `run_turn` signature:

```python
    async def run_turn(
        self,
        conversation: Conversation,
        user_message: str,
        system_prompt: str,
        model_payload_builder: Optional[Any] = None,
    ) -> AsyncGenerator[ChatEvent, None]:
```

Add helper methods to `ChatRunner`:

```python
    async def _handle_list_chat_models(self, model_payload_builder: Optional[Any]) -> dict:
        if model_payload_builder is not None:
            payload = model_payload_builder()
            if hasattr(payload, "__await__"):
                payload = await payload
            return payload
        from . import model_status
        return await model_status.build_models_payload()

    async def _handle_set_chat_model(
        self,
        conversation: Conversation,
        params: dict,
    ) -> dict:
        from . import model_status

        model_override = params.get("model_override")
        if not model_override:
            return {
                "success": False,
                "code": "missing_model_override",
                "error": "Missing model_override",
            }

        try:
            resolution = await model_status.resolve_allowed_model_override(
                model_override
            )
        except model_status.ModelOverrideUnavailable as exc:
            payload = exc.to_payload()
            payload["success"] = False
            return payload

        payload = conversation.stage_model_override(
            resolution,
            source="agent_tool",
            reason=str(params.get("reason") or ""),
        )
        return {
            "success": True,
            "model_override": resolution.model_override,
            "routing": resolution.routing,
            "provider": resolution.provider,
            "api_base_source": resolution.api_base_source,
            "applies_to": "next_turn",
            "message": (
                "Model switch staged. The next user message in this conversation "
                f"will use {resolution.model_override}."
            ),
            **payload,
        }
```

In the tool dispatch loop, after the `ui_block` block and before ordinary dispatch, add an inline synchronous-result pseudo-tool branch:

```python
                    if tool_name in {"list_chat_models", "set_chat_model"}:
                        meta_only_round = False
                        tools_used.add(tool_name)
                        yield ChatEvent(
                            "tool_start",
                            name=tool_name,
                            params=params,
                            tool_call_id=tc.id,
                        )
                        if tool_name == "list_chat_models":
                            result = await self._handle_list_chat_models(
                                model_payload_builder
                            )
                        else:
                            result = await self._handle_set_chat_model(
                                conversation,
                                params,
                            )
                        result_str = json.dumps(result)
                        conversation.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        })
                        yield ChatEvent(
                            "tool_result",
                            name=tool_name,
                            result=result_str,
                            tool_call_id=tc.id,
                            verified=bool(result.get("success", True)),
                        )
                        if tool_name == "set_chat_model" and result.get("success"):
                            yield ChatEvent(
                                "model_update",
                                content=result["message"],
                                model=result["model_override"],
                                applies_to="next_turn",
                            )
                        continue
```

This branch returns an inline tool result and continues the agent round. It must not wait for a `ui_response`.

- [ ] **Step 6: Apply pending model in `finally` before clearing active_run_id**

In `run_turn()`'s `finally`, before `conversation.active_run_id = None`, add:

```python
            applied_model_update = conversation.apply_pending_model_override()
```

Then before the final `done` event, emit an active model update when the generator is not closing:

```python
            if applied_model_update and not closing_due_to_generator_exit:
                yield ChatEvent(
                    "model_update",
                    content=(
                        "Model switch applied. Future turns in this conversation "
                        f"will use {applied_model_update['active_model']}."
                    ),
                    model=applied_model_update["active_model"],
                    applies_to="active",
                )
```

The ordering must be:

1. patch orphaned tool calls
2. apply pending model
3. clear `active_run_id`
4. touch conversation
5. emit `model_update` and `done` when the generator is still open

This makes failure, abort, and normal completion share one pending-apply path.

- [ ] **Step 7: Run pseudo-tool tests**

Run:

```powershell
python -m pytest tests/test_chat_runner_model_tools.py -q
```

Expected: all pseudo-tool tests pass.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_chat_runner_model_tools.py
git commit -m "feat: add chat model agent tools"
```

**Review checkpoint:** Stop here if the staged-not-used-current-turn test required changes to the ChatRunner loop beyond this plan. That behavior is load-bearing.

---

## Task 5: Conversation-Aware `/agent/chat/models`

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/model_status.py`
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Test: `mcp_server/tests/test_chat_server.py`

- [ ] **Step 1: Add failing models endpoint tests**

Add to `TestChatServer`:

```python
    async def test_models_without_conversation_id_preserves_slice1_payload(self):
        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {},
            "personas": [],
            "local_providers": {},
            "allowed_model_overrides": [],
        }
        build_models_payload = AsyncMock(return_value=payload)
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=build_models_payload,
        ):
            resp = await self.client.get("/agent/chat/models")

        assert resp.status == 200
        assert await resp.json() == payload
        build_models_payload.assert_awaited_once_with(builder=self.builder)

    async def test_models_with_conversation_id_includes_conversation_status(self):
        conv = self.store.create("worker")
        conv.model = "anthropic/worker"
        conv.api_base = ""
        conv.model_source = "persona"
        conv.api_base_source = "none"
        conv.pending_model = "ollama_chat/qwen3:30b"
        conv.pending_api_base = ""
        conv.pending_model_source = "agent_tool"
        conv.pending_api_base_source = "none"

        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {},
            "personas": [],
            "local_providers": {},
            "allowed_model_overrides": [],
        }
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=AsyncMock(return_value=payload),
        ):
            resp = await self.client.get(
                f"/agent/chat/models?conversation_id={conv.id}"
            )

        assert resp.status == 200
        data = await resp.json()
        assert data["conversation"]["conversation_id"] == conv.id
        assert data["conversation"]["active_model"] == "anthropic/worker"
        assert data["conversation"]["pending_model"] == "ollama_chat/qwen3:30b"
        assert "api_base" not in data["conversation"]

    async def test_models_with_unknown_conversation_id_returns_404(self):
        resp = await self.client.get("/agent/chat/models?conversation_id=conv_missing")
        assert resp.status == 404
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_chat_server.py::TestChatServer::test_models_without_conversation_id_preserves_slice1_payload tests/test_chat_server.py::TestChatServer::test_models_with_conversation_id_includes_conversation_status tests/test_chat_server.py::TestChatServer::test_models_with_unknown_conversation_id_returns_404 -q
```

Expected: conversation-id tests fail.

- [ ] **Step 3: Add conversation payload helper**

In `mcp_server/src/rook/agent/chat/model_status.py`, add:

```python
def build_conversation_model_status(conversation) -> dict:
    """Return model visibility for one conversation without exposing api_base."""
    active_routing = _bound_routing(conversation.model, conversation.api_base)
    pending_model = conversation.pending_model or None
    pending_routing = (
        _bound_routing(conversation.pending_model, conversation.pending_api_base)
        if pending_model
        else None
    )
    return {
        "conversation_id": conversation.id,
        "persona": conversation.persona,
        "active_model": conversation.model,
        "active_routing": active_routing,
        "model_source": conversation.model_source,
        "api_base_source": conversation.api_base_source,
        "pending_model": pending_model,
        "pending_routing": pending_routing,
        "pending_model_source": conversation.pending_model_source or None,
        "pending_api_base_source": conversation.pending_api_base_source or None,
        "pending_applies_to": "next_turn" if pending_model else None,
    }
```

- [ ] **Step 4: Extend `handle_models`**

In `server.py`, update `handle_models`:

```python
async def handle_models(request: web.Request) -> web.Response:
    """GET /agent/chat/models — report active model routing and local models."""
    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    payload = await model_status.build_models_payload(builder=builder)

    conv_id = request.query.get("conversation_id")
    if conv_id:
        store = request.app.get(_STORE_KEY) or _get_store()
        conv = store.get(conv_id)
        if conv is None:
            return web.json_response(
                {"error": "Conversation not found"},
                status=404,
                headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        payload = {
            **payload,
            "conversation": model_status.build_conversation_model_status(conv),
        }

    return web.json_response(
        payload,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
```

- [ ] **Step 5: Run endpoint tests**

Run:

```powershell
python -m pytest tests/test_chat_server.py::TestChatServer::test_models_without_conversation_id_preserves_slice1_payload tests/test_chat_server.py::TestChatServer::test_models_with_conversation_id_includes_conversation_status tests/test_chat_server.py::TestChatServer::test_models_with_unknown_conversation_id_returns_404 -q
```

Expected: selected tests pass.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/model_status.py mcp_server/src/rook/agent/chat/server.py mcp_server/tests/test_chat_server.py
git commit -m "feat: report conversation model status"
```

---

## Task 6: Wire Server Handler To ChatRunner Model Tools

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Test: `mcp_server/tests/test_chat_server.py`

- [ ] **Step 1: Add failing server wiring test**

Add to `TestChatServer`:

```python
    async def test_message_passes_model_payload_builder_to_runner(self):
        captured = {}

        class CapturingRunner:
            async def run_turn(
                self,
                conv,
                message,
                system_prompt,
                model_payload_builder=None,
            ):
                captured["builder"] = model_payload_builder
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = CapturingRunner()

        start = await self.client.post("/agent/chat/start", json={"persona": "worker"})
        conv_id = (await start.json())["conversation_id"]
        resp = await self.client.post(
            "/agent/chat/message",
            json={"conversation_id": conv_id, "message": "list models"},
        )

        assert resp.status == 200
        assert captured["builder"] is not None
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=AsyncMock(return_value={"allowed_model_overrides": []}),
        ) as build_models_payload:
            payload = await captured["builder"]()
        assert payload == {"allowed_model_overrides": []}
        build_models_payload.assert_awaited_once_with(builder=self.builder)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests/test_chat_server.py::TestChatServer::test_message_passes_model_payload_builder_to_runner -q
```

Expected: failure because `handle_message` does not pass a `model_payload_builder` keyword argument.

- [ ] **Step 3: Pass builder callback from message and UI response handlers**

In `server.py`, add local builder callbacks before the existing `runner.run_turn(conv, message, system_prompt)` call in `handle_message` and before the existing `runner.run_turn(conv, user_message, system_prompt)` call in `handle_ui_response`:

```python
    async def model_payload_builder():
        return await model_status.build_models_payload(builder=builder)
```

Change calls to:

```python
            turn_events = runner.run_turn(
                conv,
                message,
                system_prompt,
                model_payload_builder=model_payload_builder,
            )
```

And for UI response:

```python
            turn_events = runner.run_turn(
                conv,
                user_message,
                system_prompt,
                model_payload_builder=model_payload_builder,
            )
```

- [ ] **Step 4: Run server wiring test**

Run:

```powershell
python -m pytest tests/test_chat_server.py::TestChatServer::test_message_passes_model_payload_builder_to_runner -q
```

Expected: selected test passes.

- [ ] **Step 5: Commit Task 6**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/server.py mcp_server/tests/test_chat_server.py
git commit -m "feat: wire chat model tools to models payload"
```

---

## Task 7: C# Text Feedback

**Files:**

- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`

- [ ] **Step 1: Add DTOs and event fields in `AgentChatClient.cs`**

Add DTOs near `ConversationInfo`:

```csharp
public class ChatConversationModelInfo
{
    [JsonPropertyName("conversation_id")]
    public string ConversationId { get; set; } = "";

    public string Persona { get; set; } = "";

    [JsonPropertyName("active_model")]
    public string ActiveModel { get; set; } = "";

    [JsonPropertyName("active_routing")]
    public string ActiveRouting { get; set; } = "";

    [JsonPropertyName("pending_model")]
    public string? PendingModel { get; set; }

    [JsonPropertyName("pending_routing")]
    public string? PendingRouting { get; set; }

    [JsonPropertyName("pending_applies_to")]
    public string? PendingAppliesTo { get; set; }

    [JsonPropertyName("api_base_source")]
    public string ApiBaseSource { get; set; } = "";
}

public class ChatModelsInfo
{
    [JsonPropertyName("conversation")]
    public ChatConversationModelInfo? Conversation { get; set; }
}
```

Add fields to `ChatEvent`:

```csharp
public string? Model { get; set; }

[JsonPropertyName("applies_to")]
public string? AppliesTo { get; set; }
```

- [ ] **Step 2: Add `GetModelsAsync`**

Add to `AgentChatClient`:

```csharp
public async Task<ChatModelsInfo> GetModelsAsync(
    Uri baseUri,
    string? conversationId = null,
    CancellationToken ct = default)
{
    var path = "/agent/chat/models";
    if (!string.IsNullOrEmpty(conversationId))
        path += "?conversation_id=" + Uri.EscapeDataString(conversationId);

    var resp = await _client.GetAsync(new Uri(baseUri, path), ct);
    resp.EnsureSuccessStatusCode();
    var json = await resp.Content.ReadAsStringAsync();
    return JsonSerializer.Deserialize<ChatModelsInfo>(json, JsonOptions)
           ?? new ChatModelsInfo();
}
```

`AgentChatClient.SetSessionNonce()` already puts `X-Rook-Session` on `_client.DefaultRequestHeaders`, so this call inherits the nonce header.

- [ ] **Step 3: Add text status refresh in `AgentChatTab.cs`**

Add field:

```csharp
private string? _activeModelLabel;
```

Add helper methods:

```csharp
private async Task RefreshModelStatusAsync(CancellationToken ct = default)
{
    var baseUri = _conversationBaseUri;
    var conversationId = _conversationId;
    if (baseUri == null || string.IsNullOrEmpty(conversationId))
        return;

    try
    {
        var models = await _client.GetModelsAsync(baseUri, conversationId, ct);
        var conv = models.Conversation;
        if (conv == null || string.IsNullOrEmpty(conv.ActiveModel))
            return;

        _activeModelLabel = conv.ActiveModel;
        var label = string.IsNullOrEmpty(conv.PendingModel)
            ? $"Model: {conv.ActiveModel}"
            : $"Model: {conv.ActiveModel}; next turn: {conv.PendingModel}";
        Application.Instance.Invoke(() => SetStatus(label, Colors.Blue));
    }
    catch
    {
        // Model status is feedback only; chat streaming remains authoritative.
    }
}

private void ApplyModelUpdateEvent(ChatEvent evt)
{
    if (string.IsNullOrEmpty(evt.Model))
        return;

    var label = evt.AppliesTo == "next_turn"
        ? $"Model: {_activeModelLabel ?? "current"}; next turn: {evt.Model}"
        : $"Model: {evt.Model}";
    if (evt.AppliesTo == "active")
        _activeModelLabel = evt.Model;
    SetStatus(label, Colors.Blue);
}
```

After `_conversationBaseUri = info.BaseUri;` in `InitializeAsync()`, add:

```csharp
_activeModelLabel = info.Model;
await RefreshModelStatusAsync();
```

In `HandleChatEvent`, add:

```csharp
                    case "model_update":
                        ApplyModelUpdateEvent(evt);
                        _ = RefreshModelStatusAsync();
                        break;
```

In the `"done"` case, before applying health status, add:

```csharp
                        _ = RefreshModelStatusAsync();
```

This is text-only feedback. Do not add a dropdown.

- [ ] **Step 4: Build managed companion**

Run from repo root:

```powershell
dotnet build src/Rook/Rook.csproj -p:Configuration=Debug
```

Expected: build succeeds. If this machine lacks a managed dependency, record the exact missing dependency in the final verification notes.

- [ ] **Step 5: Commit Task 7**

Run:

```powershell
git add src/Rook/UI/Chat/AgentChatClient.cs src/Rook/UI/Chat/AgentChatTab.cs
git commit -m "feat: show chat model status in panel"
```

---

## Task 8: Focused Verification And Known Baseline

**Files:**

- No code changes unless a focused verification failure points to a Slice 2 regression.

- [ ] **Step 1: Run helper and route tests**

Run:

```powershell
cd C:\Users\aryan\source\repos\Rook\.worktrees\rookllm-chooser-slice2-design\mcp_server
python -m pytest tests/test_chat_model_status.py tests/test_chat_runner_model_tools.py tests/test_chat_server.py::TestChatServer::test_start_rejects_unavailable_model_override tests/test_chat_server.py::TestChatServer::test_start_applies_detected_lmstudio_resolution tests/test_chat_server.py::TestChatServer::test_set_conversation_model_rejects_while_active tests/test_chat_server.py::TestChatServer::test_set_conversation_model_applies_when_inactive tests/test_chat_server.py::TestChatServerWithNonce::test_set_conversation_model_requires_nonce tests/test_chat_server.py::TestChatServer::test_models_without_conversation_id_preserves_slice1_payload tests/test_chat_server.py::TestChatServer::test_models_with_conversation_id_includes_conversation_status tests/test_chat_server.py::TestChatServer::test_models_with_unknown_conversation_id_returns_404 tests/test_chat_server.py::TestChatServer::test_message_passes_model_payload_builder_to_runner -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader chat server file**

Run:

```powershell
python -m pytest tests/test_chat_server.py -q
```

Expected: all non-knowledge graph tests pass. If these two known failures remain, report them as unrelated baseline:

- `tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload`
- `tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found`

- [ ] **Step 3: Run managed build**

Run from repo root:

```powershell
cd C:\Users\aryan\source\repos\Rook\.worktrees\rookllm-chooser-slice2-design
dotnet build src/Rook/Rook.csproj -p:Configuration=Debug
```

Expected: build succeeds or fails only for an environmental dependency that is documented exactly.

- [ ] **Step 4: Check no forbidden sync path returned**

Run:

```powershell
rg -n "def get_cached_local_provider_status\(|_run_async_from_sync|threading" mcp_server/src/rook/agent/chat/model_status.py
```

Expected: no matches.

- [ ] **Step 5: Commit verification note if docs changed**

No commit is needed if verification required no code or doc changes.

- [ ] **Step 6: Final status**

Run:

```powershell
git status -sb
git log --oneline -8
```

Expected: worktree clean, with one commit per completed implementation task.

---

## Self-Review Checklist

Spec coverage:

- Agent-mediated primary path: Task 4.
- Agent-tool no active-turn `409`: Task 4 tests.
- Current conversation / next-turn timing: Tasks 2 and 4.
- Pending switch applies on error/abort: Task 4 tests and `finally` step.
- Out-of-band `/agent/chat/model` with active `409`: Task 3.
- `/start` validation tightening: Task 3.
- Server-side `allowed_model_overrides` validation: Task 1.
- LM Studio detected `api_base`: Task 1 and Task 3 tests.
- No client `api_base`: Task 3 tests.
- `/models?conversation_id=` feedback: Task 5.
- Panel text feedback: Task 7.
- No visual selector: Task 7.
- No sync provider detection: Task 8.

Execution notes:

- The first implementation review should happen after Task 2.
- The second implementation review should happen after Task 4.
- If Task 4 cannot prove "staged model not used by later LLM rounds in the same turn," stop and revise the design before touching C#.
