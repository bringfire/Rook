# OpenRouter Core Provider Plumbing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenRouter a first-class, robust LiteLLM provider across Rook's existing model-selection paths (profiles, env overrides, DSPy role, Chirp) with a refreshable catalog cache — no new UI.

**Architecture:** A small reusable `OpenRouterCatalog` service (`refresh()` is the only networked path; `load()` is pure-disk) backed by a human-curated favorites file and a generated metadata cache. A conservative `api_key_env_for_model()` helper replaces a hardcoded Anthropic-key assumption in DSPy and feeds optional, non-degrading health reporting. Routing is fixed by adding `openrouter/` to the native-cloud prefix set.

**Tech Stack:** Python 3, LiteLLM (pinned `1.89.4`), DSPy (`>=2.6`), `httpx`, `pytest`. Design spec: [`docs/superpowers/specs/2026-06-29-openrouter-core-provider-plumbing-design.md`](../specs/2026-06-29-openrouter-core-provider-plumbing-design.md).

## Global Constraints

- **No new UI, no chat-server HTTP endpoint, no C# changes.** (Those are Spec B.)
- **`refresh()` is the only code that networks.** `load()` and all routing are network-free. (Invariant I2.)
- **Routing is never blocked by the cache.** Missing/stale/corrupt cache still routes a configured `openrouter/` model. (I1.)
- **Atomic cache writes only** — temp file + `os.replace`. (I4.)
- **Deterministic tests, zero live network** — HTTP is mocked / `_fetch_models` is monkeypatched; one gated live smoke is skipped unless `OPENROUTER_LIVE_SMOKE` is set.
- **Cache file:** `knowledge/generated/openrouter_catalog_cache.json` — gitignored, `schema_version` = 1, safe to delete (I7). Written via `resolve_writable_knowledge_path("generated", "openrouter_catalog_cache.json")`.
- **Favorites file:** `knowledge/openrouter_favorites.json` — checked in, human-authored, IDs in LiteLLM form (`openrouter/...`). Read via `resolve_readable_knowledge_path("openrouter_favorites.json")`.
- **Helper conservatism (I5/I6):** `api_key_env_for_model` returns a key env name ONLY for single-env-var providers (OpenRouter, Anthropic, real-cloud OpenAI); `None` for local (Ollama, LM Studio) and multi-auth/unknown (Azure/Bedrock/Vertex/...).
- **Health is optional/non-degrading (I3):** a missing `OPENROUTER_API_KEY` never makes a non-OpenRouter setup read as degraded; Anthropic-only stays green.
- **Run pytest from `mcp_server/`** (e.g. `cd mcp_server && python -m pytest tests/test_x.py -v`); Chirp tests run from `C:/Users/aryan/source/repos/Chirp`.
- **Commit after every task** with the shown message; end messages with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: `openrouter/` routing fix

**Files:**
- Modify: `mcp_server/src/rook/agent/model_profiles.py:60-85` (`_NATIVE_CLOUD_PREFIXES`)
- Test: `mcp_server/tests/test_model_profiles_openrouter.py`

**Interfaces:**
- Consumes: existing `api_base_for_model(model, profile_api_base) -> Optional[str]`.
- Produces: nothing new (behavioral fix only).

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_model_profiles_openrouter.py`:

```python
from rook.agent.model_profiles import api_base_for_model


def test_openrouter_never_gets_profile_api_base():
    # openrouter is a native-cloud provider; even inside a mixed profile that
    # carries a local api_base (e.g. lmstudio), it must route to OpenRouter.
    assert api_base_for_model(
        "openrouter/anthropic/claude-3.7-sonnet", "http://127.0.0.1:1234/v1"
    ) is None


def test_openrouter_no_profile_api_base():
    assert api_base_for_model("openrouter/openai/gpt-4o", None) is None


def test_lmstudio_local_still_gets_api_base():
    # Regression guard: the openai/ local case is unchanged by the openrouter fix.
    assert api_base_for_model(
        "openai/lmstudio-model", "http://127.0.0.1:1234/v1"
    ) == "http://127.0.0.1:1234/v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_model_profiles_openrouter.py -v`
Expected: `test_openrouter_never_gets_profile_api_base` FAILS (returns the api_base, not `None`).

- [ ] **Step 3: Add the prefix**

In `mcp_server/src/rook/agent/model_profiles.py`, inside the `_NATIVE_CLOUD_PREFIXES` frozenset (after `"mistral/",`), add:

```python
    "openrouter/",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_model_profiles_openrouter.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/model_profiles.py mcp_server/tests/test_model_profiles_openrouter.py
git commit -m "$(printf 'feat(openrouter): route openrouter/ as native cloud\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: `api_key_env_for_model()` helper

**Files:**
- Modify: `mcp_server/src/rook/agent/model_profiles.py` (add after `api_base_for_model`, ~line 143)
- Test: `mcp_server/tests/test_model_profiles_openrouter.py` (extend)

**Interfaces:**
- Consumes: existing module constant `_OPENAI_CLOUD_MODEL_PREFIXES`.
- Produces: `api_key_env_for_model(model: str, profile_api_base: Optional[str] = None) -> Optional[str]` — used by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_model_profiles_openrouter.py`:

```python
from rook.agent.model_profiles import api_key_env_for_model


def test_key_env_openrouter():
    assert api_key_env_for_model("openrouter/anthropic/claude-3.7-sonnet") == "OPENROUTER_API_KEY"


def test_key_env_anthropic():
    assert api_key_env_for_model("anthropic/claude-opus-4-6") == "ANTHROPIC_API_KEY"


def test_key_env_openai_cloud():
    assert api_key_env_for_model("openai/gpt-4o") == "OPENAI_API_KEY"


def test_key_env_openai_local_lmstudio_is_none():
    assert api_key_env_for_model("openai/lmstudio-model", "http://127.0.0.1:1234/v1") is None


def test_key_env_ollama_is_none():
    assert api_key_env_for_model("ollama_chat/qwen3:30b") is None


def test_key_env_multiauth_providers_are_none():
    assert api_key_env_for_model("azure/gpt-4") is None
    assert api_key_env_for_model("bedrock/anthropic.claude") is None
    assert api_key_env_for_model("gemini/gemini-1.5-pro") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_model_profiles_openrouter.py -v -k key_env`
Expected: FAIL with `ImportError: cannot import name 'api_key_env_for_model'`.

- [ ] **Step 3: Write the helper**

In `mcp_server/src/rook/agent/model_profiles.py`, immediately after `api_base_for_model` (before the `# ── Default profiles data ──` comment), add:

```python
# Provider prefixes whose auth is a single well-known env var.  Intentionally
# conservative: providers with non-trivial auth (Azure, Bedrock, Vertex, ...)
# are omitted so we never invent a FOO_API_KEY — LiteLLM/DSPy surface their own
# auth errors instead.
_SINGLE_ENV_KEY_PREFIXES: Dict[str, str] = {
    "openrouter/": "OPENROUTER_API_KEY",
    "anthropic/": "ANTHROPIC_API_KEY",
}


def api_key_env_for_model(model: str, profile_api_base: Optional[str] = None) -> Optional[str]:
    """Return the env var name holding the API key for ``model``, or ``None``.

    Conservative and routing-aware.  Returns a key env name ONLY for providers
    whose auth is a single well-known env var (OpenRouter, Anthropic, real
    OpenAI cloud).  Returns ``None`` for local providers (Ollama, LM Studio /
    OpenAI-compatible) and for multi-auth/unknown providers (Azure, Bedrock,
    Vertex, ...), letting LiteLLM/DSPy surface provider-specific auth errors.

    Shares the same ``openai/`` cloud-vs-local disambiguation as
    ``api_base_for_model`` so the two cannot drift.

    Args:
        model: LiteLLM model identifier.
        profile_api_base: Accepted for signature parity with
            ``api_base_for_model``; ``openai/`` locality is decided by the model
            family, so this argument does not currently change the result.

    Returns:
        Env var name (e.g. ``"OPENROUTER_API_KEY"``) or ``None``.
    """
    if model.startswith("ollama_chat/") or model.startswith("ollama/"):
        return None

    slash_idx = model.find("/")
    if slash_idx <= 0:
        return None  # bare / unknown

    prefix = model[:slash_idx + 1]
    if prefix in _SINGLE_ENV_KEY_PREFIXES:
        return _SINGLE_ENV_KEY_PREFIXES[prefix]

    if prefix == "openai/":
        model_name = model[slash_idx + 1:]
        if any(model_name.startswith(p) for p in _OPENAI_CLOUD_MODEL_PREFIXES):
            return "OPENAI_API_KEY"
        return None  # local OpenAI-compatible server (LM Studio, vLLM)

    return None  # multi-auth / unknown provider
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_model_profiles_openrouter.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/model_profiles.py mcp_server/tests/test_model_profiles_openrouter.py
git commit -m "$(printf 'feat(openrouter): add conservative api_key_env_for_model helper\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: DSPy provider-aware key resolution

**Files:**
- Modify: `mcp_server/src/rook/learning/dspy_config.py:167-175` (`configure_dspy`) and `:260-277` (`configure_dspy_for_optimization`)
- Test: `mcp_server/tests/test_dspy_openrouter_keys.py`

**Interfaces:**
- Consumes: `api_key_env_for_model` (Task 2).
- Produces: unchanged public signatures of `configure_dspy(...)` and `configure_dspy_for_optimization(...)`; behavior now provider-aware.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_dspy_openrouter_keys.py`:

```python
import pytest
import rook.learning.dspy_config as dc


class _StubLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture(autouse=True)
def stub_dspy(monkeypatch):
    monkeypatch.setattr(dc.dspy, "LM", _StubLM)
    monkeypatch.setattr(dc.dspy, "configure", lambda **kw: None)


def test_openrouter_role_uses_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lm = dc.configure_dspy(model="openrouter/anthropic/claude-3.7-sonnet")
    assert lm.kwargs["api_key"] == "sk-or-test"
    assert "api_base" not in lm.kwargs  # openrouter routes natively (Task 1)


def test_openrouter_role_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        dc.configure_dspy(model="openrouter/anthropic/claude-3.7-sonnet")


def test_anthropic_still_requires_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        dc.configure_dspy(model="anthropic/claude-opus-4-6")


def test_explicit_api_key_overrides_missing_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    lm = dc.configure_dspy(model="openrouter/x/y", api_key="explicit-key")
    assert lm.kwargs["api_key"] == "explicit-key"


def test_optimization_openrouter_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    teacher, student = dc.configure_dspy_for_optimization(
        teacher_model="openrouter/anthropic/claude-3.7-sonnet",
        student_model="openrouter/anthropic/claude-haiku",
    )
    assert teacher.kwargs["api_key"] == "sk-or-test"
    assert student.kwargs["api_key"] == "sk-or-test"


def test_optimization_explicit_key_override(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    teacher, student = dc.configure_dspy_for_optimization(
        teacher_model="openrouter/x/y", student_model="openrouter/a/b", api_key="explicit",
    )
    assert teacher.kwargs["api_key"] == "explicit"
    assert student.kwargs["api_key"] == "explicit"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_dspy_openrouter_keys.py -v`
Expected: FAIL — `test_openrouter_role_uses_openrouter_key` raises `ValueError: ANTHROPIC_API_KEY ...` (the current hardcoded demand).

- [ ] **Step 3a: Fix `configure_dspy`**

In `mcp_server/src/rook/learning/dspy_config.py`, replace the block at lines 167-175:

```python
    if not is_local:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable required for cloud models. "
                "Set it with: export ANTHROPIC_API_KEY='your-key-here'\n"
                "For local models, set the 'active' profile to 'local' or 'lmstudio' "
                "in knowledge/model_profiles.json"
            )
```

with:

```python
    if not is_local:
        from ..agent.model_profiles import api_key_env_for_model
        key_env = api_key_env_for_model(model, api_base)
        if not api_key and key_env:
            api_key = os.environ.get(key_env)
            if not api_key:
                raise ValueError(
                    f"{key_env} environment variable required for model '{model}'. "
                    f"Set it (e.g. export {key_env}='your-key-here'), pass api_key=, "
                    "or select a local profile in knowledge/model_profiles.json."
                )
        # key_env is None for multi-auth/unknown providers (Azure, Bedrock, ...);
        # leave api_key unset and let LiteLLM/DSPy surface provider-specific errors.
```

- [ ] **Step 3b: Fix `configure_dspy_for_optimization`**

In the same file, replace lines 260-277 (the `# Require API key if either model is cloud` block through the end of the kwargs assembly, i.e. up to and including the `if student_base:` block):

```python
    # Require API key if either model is cloud
    if not teacher_is_local or not student_is_local:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required for cloud models")

    teacher_kwargs = dict(model=teacher_model, temperature=0.7, max_tokens=4096, cache=True)
    student_kwargs = dict(model=student_model, temperature=0.3, max_tokens=2048, cache=True)
    # API key goes to cloud models; local models ignore it
    if api_key:
        if not teacher_is_local:
            teacher_kwargs["api_key"] = api_key
        if not student_is_local:
            student_kwargs["api_key"] = api_key
    if teacher_base:
        teacher_kwargs["api_base"] = teacher_base
    if student_base:
        student_kwargs["api_base"] = student_base
```

with:

```python
    # Resolve a provider-correct key per cloud model.  An explicit api_key=
    # overrides env lookup for all cloud models; multi-auth/unknown providers
    # resolve to None and let LiteLLM surface their own auth errors.
    from ..agent.model_profiles import api_key_env_for_model

    def _resolve_key(mdl: str, mdl_is_local: bool) -> Optional[str]:
        if mdl_is_local:
            return None
        if api_key:
            return api_key
        key_env = api_key_env_for_model(mdl)
        if key_env:
            val = os.environ.get(key_env)
            if not val:
                raise ValueError(
                    f"{key_env} environment variable required for model '{mdl}'. "
                    "Set it or pass api_key=."
                )
            return val
        return None

    teacher_key = _resolve_key(teacher_model, teacher_is_local)
    student_key = _resolve_key(student_model, student_is_local)

    teacher_kwargs = dict(model=teacher_model, temperature=0.7, max_tokens=4096, cache=True)
    student_kwargs = dict(model=student_model, temperature=0.3, max_tokens=2048, cache=True)
    if teacher_key:
        teacher_kwargs["api_key"] = teacher_key
    if student_key:
        student_kwargs["api_key"] = student_key
    if teacher_base:
        teacher_kwargs["api_base"] = teacher_base
    if student_base:
        student_kwargs["api_base"] = student_base
```

Note: `Optional` is already imported in `dspy_config.py` (used in existing signatures).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_dspy_openrouter_keys.py -v`
Expected: PASS (6 passed). Then run the existing DSPy tests to confirm no regression:
Run: `cd mcp_server && python -m pytest tests/test_dspy_integration.py -v`
Expected: PASS (unchanged).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/learning/dspy_config.py mcp_server/tests/test_dspy_openrouter_keys.py
git commit -m "$(printf 'feat(openrouter): provider-aware DSPy key resolution (both entry points)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: Active-model-gated, non-degrading provider health + `.env.example`

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/runtime_health.py` — `collect_runtime_facts` signature (`:15`), llm_state (`:58-66`), fact lines (`:131-134`)
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py:1038` (pass the active conversation model)
- Modify: `mcp_server/.env.example`
- Test: `mcp_server/tests/test_runtime_health_providers.py`

**Interfaces:**
- Consumes: `api_key_env_for_model` (Task 2); `model_profiles.get_models()` for the default-model fallback.
- Produces: `_llm_state(active_model: str | None = None) -> dict`, `_effective_default_model() -> str` (module-private); `collect_runtime_facts(include_gh=False, active_model=None)`.

**Why active-model gating (not any-key):** the approved spec requires the *active/effective* model's key to drive `llm.configured`. An "any key present" rule marks chat healthy with only `OPENROUTER_API_KEY` set while the active profile still resolves to Anthropic — the real turn then fails. Health gates on the model that will actually run: `conversation.model` during a turn, or the worker-role default at the generic health endpoint.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_runtime_health_providers.py`:

```python
import rook.agent.chat.runtime_health as rh


def test_active_anthropic_model_with_key_is_green(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = rh._llm_state(active_model="anthropic/claude-opus-4-6")
    assert state["configured"] is True
    assert state["provider_keys"]["OPENROUTER_API_KEY"] is False


def test_openrouter_active_model_missing_key_is_unconfigured(monkeypatch):
    # Anthropic key present but irrelevant: the ACTIVE model is openrouter.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = rh._llm_state(active_model="openrouter/anthropic/claude-3.7-sonnet")
    assert state["configured"] is False
    assert "OPENROUTER_API_KEY" in state["message"]


def test_active_local_model_is_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    state = rh._llm_state(active_model="ollama_chat/qwen3:30b")
    assert state["configured"] is True


def test_default_path_gates_on_effective_model(monkeypatch):
    # No active model -> resolve the effective default and gate on IT, not any key.
    monkeypatch.setattr(rh, "_effective_default_model", lambda: "openrouter/x/y")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")  # present but irrelevant
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = rh._llm_state()
    assert state["configured"] is False
    assert "OPENROUTER_API_KEY" in state["message"]


def test_provider_key_map_is_informational(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    state = rh._llm_state(active_model="anthropic/claude-opus-4-6")
    assert state["provider_keys"]["OPENROUTER_API_KEY"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_runtime_health_providers.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute '_llm_state'`.

- [ ] **Step 3a: Add the `_llm_state` helper**

In `mcp_server/src/rook/agent/chat/runtime_health.py`, add this function just above `async def collect_runtime_facts` (after the logger line ~13):

```python
def _provider_key_state() -> dict[str, bool]:
    return {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.environ.get("OPENROUTER_API_KEY")),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
    }


def _effective_default_model() -> str:
    """Resolve the model a default chat turn would use (worker role).

    Used only when no explicit active model is available (e.g. the generic
    health endpoint).  Mirrors resolve_model_and_base's worker fallback.
    """
    try:
        from ...agent.model_profiles import get_models
        models = get_models()
        return models.worker or "anthropic/claude-sonnet-4-6"
    except Exception:
        return "anthropic/claude-sonnet-4-6"


def _llm_state(active_model: str | None = None) -> dict[str, Any]:
    """Health gated on the active/effective model's required key (I3).

    Gates ``configured`` on the key the active model actually needs: the
    conversation model during a turn, or the worker-role default otherwise.
    Local and multi-auth/unknown providers are treated as configured (no single
    required env var).  The full provider-key map is reported informationally.
    """
    from ...agent.model_profiles import api_key_env_for_model
    provider_keys = _provider_key_state()
    model = active_model or _effective_default_model()
    provider = model.split("/", 1)[0] if "/" in model else "unknown"
    key_env = api_key_env_for_model(model)

    if key_env is None:
        return {
            "configured": True,
            "provider": provider,
            "message": f"Active model '{model}' needs no single required key env var.",
            "active_model": model,
            "provider_keys": provider_keys,
        }

    configured = bool(os.environ.get(key_env))
    return {
        "configured": configured,
        "provider": provider,
        "message": (
            f"{key_env} is configured for active model '{model}'."
            if configured
            else f"{key_env} is missing for active model '{model}'. "
                 "Set it in the environment or mcp_server/.env."
        ),
        "active_model": model,
        "provider_keys": provider_keys,
    }
```

- [ ] **Step 3b: Thread the active model through `collect_runtime_facts`**

Change the signature at line 15 to:

```python
async def collect_runtime_facts(
    include_gh: bool = False, active_model: str | None = None
) -> dict[str, Any]:
```

and replace the `llm_state = { ... }` literal at lines 58-66 with:

```python
    llm_state = _llm_state(active_model)
```

- [ ] **Step 3c: Pass the conversation model from the chat turn**

In `mcp_server/src/rook/agent/chat/chat_runner.py:1038`, replace:

```python
        runtime_facts = await collect_runtime_facts(include_gh=False)
```

with:

```python
        runtime_facts = await collect_runtime_facts(
            include_gh=False, active_model=conversation.model
        )
```

(The generic health endpoint at `server.py:185` stays `collect_runtime_facts(include_gh=include_gh)` — it has no conversation, so `_llm_state` resolves the worker-role default.)

- [ ] **Step 3d: Make the fact lines provider-neutral**

Replace lines 131-134 in `_build_verified_fact_lines`:

```python
    if llm_state.get("configured"):
        lines.append("Anthropic API key is configured for chat turns.")
    else:
        lines.append("Anthropic API key is missing; explain this explicitly instead of attempting a model call.")
```

with:

```python
    if llm_state.get("configured"):
        lines.append("An LLM provider API key is configured for chat turns.")
    else:
        lines.append("No LLM provider API key is configured for the active model; explain this explicitly instead of attempting a model call.")
```

- [ ] **Step 3e: Document the env var**

In `mcp_server/.env.example`, add under the existing key section:

```bash
# Optional — enables OpenRouter models (openrouter/...). Get a key at https://openrouter.ai/keys
OPENROUTER_API_KEY=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_runtime_health_providers.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/chat/runtime_health.py mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/.env.example mcp_server/tests/test_runtime_health_providers.py
git commit -m "$(printf 'feat(openrouter): active-model-gated, non-degrading provider health\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: Catalog module — ID normalization, favorites loader, seed files

**Files:**
- Create: `mcp_server/src/rook/providers/__init__.py` (empty, if missing)
- Create: `mcp_server/src/rook/providers/openrouter_catalog.py`
- Create: `knowledge/openrouter_favorites.json`
- Modify: `.gitignore` (repo root)
- Test: `mcp_server/tests/test_openrouter_catalog.py`

**Interfaces:**
- Produces: `to_openrouter_id(litellm_id) -> str`, `to_litellm_id(catalog_id) -> str`, `Favorite` dataclass (`id`, `notes`, `tags`), `load_favorites(path=None) -> list[Favorite]`, module constants `CACHE_SCHEMA_VERSION`, `OPENROUTER_MODELS_ENDPOINT`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_openrouter_catalog.py`:

```python
import json
import rook.providers.openrouter_catalog as cat


def test_to_helpers_roundtrip():
    assert cat.to_openrouter_id("openrouter/anthropic/claude-x") == "anthropic/claude-x"
    assert cat.to_litellm_id("anthropic/claude-x") == "openrouter/anthropic/claude-x"
    # idempotent: already-prefixed ids are unchanged
    assert cat.to_litellm_id("openrouter/anthropic/claude-x") == "openrouter/anthropic/claude-x"
    assert cat.to_openrouter_id("anthropic/claude-x") == "anthropic/claude-x"


def test_load_favorites_dict_and_string(tmp_path):
    p = tmp_path / "openrouter_favorites.json"
    p.write_text(json.dumps([
        {"id": "openrouter/anthropic/claude-3.7-sonnet", "notes": "n", "tags": ["planner"]},
        "openrouter/openai/gpt-4o",
    ]), encoding="utf-8")
    favs = cat.load_favorites(p)
    assert [f.id for f in favs] == [
        "openrouter/anthropic/claude-3.7-sonnet", "openrouter/openai/gpt-4o"]
    assert favs[0].tags == ("planner",)


def test_load_favorites_missing_file_is_empty(tmp_path):
    assert cat.load_favorites(tmp_path / "nope.json") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.providers.openrouter_catalog'`.

- [ ] **Step 3a: Create the providers package marker (if missing)**

Create `mcp_server/src/rook/providers/__init__.py` with a single line:

```python
"""Provider catalog/services for Rook (OpenRouter, ...)."""
```

- [ ] **Step 3b: Create the module skeleton with normalization + favorites**

Create `mcp_server/src/rook/providers/openrouter_catalog.py`:

```python
"""OpenRouter model catalog: curated favorites + refreshable metadata cache.

Network is confined to refresh().  load() is pure-disk.  Routing never reads
this module — a missing/stale/corrupt cache never blocks routing a configured
openrouter/ model.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

CACHE_SCHEMA_VERSION = 1
OPENROUTER_MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"
STALE_AFTER_SECONDS = 7 * 24 * 3600  # freshness is observable, never enforced on routing

_FAVORITES_PARTS = ("openrouter_favorites.json",)
_CACHE_PARTS = ("generated", "openrouter_catalog_cache.json")
_OPENROUTER_PREFIX = "openrouter/"


def to_openrouter_id(litellm_id: str) -> str:
    """``openrouter/anthropic/claude-x`` -> ``anthropic/claude-x`` (strip one prefix)."""
    if litellm_id.startswith(_OPENROUTER_PREFIX):
        return litellm_id[len(_OPENROUTER_PREFIX):]
    return litellm_id


def to_litellm_id(catalog_id: str) -> str:
    """``anthropic/claude-x`` -> ``openrouter/anthropic/claude-x`` (add one prefix)."""
    if catalog_id.startswith(_OPENROUTER_PREFIX):
        return catalog_id
    return _OPENROUTER_PREFIX + catalog_id


@dataclass(frozen=True)
class Favorite:
    id: str  # LiteLLM form, e.g. "openrouter/anthropic/claude-3.7-sonnet"
    notes: Optional[str] = None
    tags: tuple[str, ...] = ()


def load_favorites(path: Optional[Path] = None) -> list[Favorite]:
    """Read curated favorites (human-authored).  Missing/invalid file -> empty list."""
    fav_path = path or resolve_readable_knowledge_path(*_FAVORITES_PARTS)
    fav_path = Path(fav_path)
    if not fav_path.exists():
        return []
    try:
        raw = json.loads(fav_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    favorites: list[Favorite] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            favorites.append(Favorite(id=entry))
        elif isinstance(entry, dict) and entry.get("id"):
            favorites.append(Favorite(
                id=entry["id"],
                notes=entry.get("notes"),
                tags=tuple(entry.get("tags", []) or ()),
            ))
    return favorites
```

- [ ] **Step 3c: Seed the favorites file**

Create `knowledge/openrouter_favorites.json`:

```json
[
  {
    "id": "openrouter/anthropic/claude-3.7-sonnet",
    "notes": "Tool-capable; example curated entry. Run openrouter_refresh_catalog to populate metadata.",
    "tags": ["tools"]
  }
]
```

- [ ] **Step 3d: Ignore the generated cache**

Append to the repo-root `.gitignore`:

```gitignore
# Generated provider catalog caches (disposable; see Spec A)
knowledge/generated/
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_catalog.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/providers/__init__.py mcp_server/src/rook/providers/openrouter_catalog.py knowledge/openrouter_favorites.json .gitignore mcp_server/tests/test_openrouter_catalog.py
git commit -m "$(printf 'feat(openrouter): catalog module skeleton (id normalization + favorites)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: Catalog `load()` — pure-disk cache reader

**Files:**
- Modify: `mcp_server/src/rook/providers/openrouter_catalog.py`
- Test: `mcp_server/tests/test_openrouter_catalog.py` (extend)

**Interfaces:**
- Consumes: `Favorite`, `load_favorites`, `to_openrouter_id`, constants (Task 5).
- Produces: `ModelMetadata`, `CatalogView`, `load(favorites_path=None, cache_path=None, now=None) -> CatalogView`, and the private `_read_cache(path) -> Optional[dict]`, `_cache_path(path=None) -> Path`, `_is_stale(fetched_at, now=None) -> bool` (reused by Task 7).

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_openrouter_catalog.py`:

```python
from datetime import datetime, timezone, timedelta


def _write_cache(path, models, fetched_at="2026-06-29T00:00:00+00:00"):
    path.write_text(json.dumps({
        "schema_version": cat.CACHE_SCHEMA_VERSION,
        "source_endpoint": cat.OPENROUTER_MODELS_ENDPOINT,
        "fetched_at": fetched_at,
        "last_refresh_attempt_at": fetched_at,
        "last_refresh_error": None,
        "models": models,
    }), encoding="utf-8")


def test_load_present_returns_known_metadata(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    _write_cache(cache, {"openrouter/anthropic/claude-3.7-sonnet": {
        "openrouter_id": "anthropic/claude-3.7-sonnet",
        "canonical_slug": "anthropic/claude-3.7-sonnet",
        "supported_parameters": ["tools"], "pricing": {"prompt": "1"},
        "context_length": 200000, "display_name": "Claude 3.7 Sonnet"}})
    view = cat.load(favorites_path=fav, cache_path=cache)
    assert view.cache_present is True
    m = view.models[0]
    assert m.metadata_state == "known"
    assert "tools" in m.supported_parameters
    assert m.context_length == 200000


def test_load_missing_cache_marks_unknown(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    view = cat.load(favorites_path=fav, cache_path=tmp_path / "absent.json")
    assert view.cache_present is False
    assert view.models[0].metadata_state == "unknown"


def test_load_corrupt_cache_marks_unknown(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    cache.write_text("{ not json", encoding="utf-8")
    view = cat.load(favorites_path=fav, cache_path=cache)
    assert view.cache_present is False
    assert view.models[0].metadata_state == "unknown"


def test_load_stale_returns_metadata_with_stale_state(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    old = "2020-01-01T00:00:00+00:00"
    _write_cache(cache, {"openrouter/anthropic/claude-3.7-sonnet": {
        "openrouter_id": "anthropic/claude-3.7-sonnet", "canonical_slug": None,
        "supported_parameters": ["tools"], "pricing": {}, "context_length": 1,
        "display_name": "x"}}, fetched_at=old)
    view = cat.load(favorites_path=fav, cache_path=cache,
                    now=datetime(2021, 1, 1, tzinfo=timezone.utc))
    assert view.stale is True
    assert view.models[0].metadata_state == "stale"
    assert "tools" in view.models[0].supported_parameters  # metadata still returned
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_catalog.py -v -k load`
Expected: FAIL with `AttributeError: module ... has no attribute 'load'`.

- [ ] **Step 3: Implement `load()` and helpers**

Append to `mcp_server/src/rook/providers/openrouter_catalog.py`:

```python
@dataclass
class ModelMetadata:
    litellm_id: str
    openrouter_id: str
    canonical_slug: Optional[str]
    supported_parameters: list[str]
    pricing: dict[str, Any]
    context_length: Optional[int]
    display_name: Optional[str]
    metadata_state: str = "known"  # "known" | "unknown" | "stale"


@dataclass
class CatalogView:
    models: list[ModelMetadata]
    fetched_at: Optional[str]
    last_refresh_attempt_at: Optional[str]
    last_refresh_error: Optional[dict]
    cache_present: bool
    stale: bool


def _cache_path(path: Optional[Path] = None) -> Path:
    return Path(path) if path is not None else resolve_writable_knowledge_path(*_CACHE_PARTS)


def _read_cache(path: Path) -> Optional[dict]:
    """Return the cache dict, or None when missing/corrupt/schema-mismatched."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    return data


def _is_stale(fetched_at: Optional[str], now: Optional[datetime] = None) -> bool:
    if not fetched_at:
        return False  # no successful fetch yet -> models are "unknown", not "stale"
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - ts).total_seconds() > STALE_AFTER_SECONDS


def load(
    favorites_path: Optional[Path] = None,
    cache_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> CatalogView:
    """Pure-disk view of curated favorites enriched with cached metadata."""
    favorites = load_favorites(favorites_path)
    cache = _read_cache(_cache_path(cache_path))
    fetched_at = cache.get("fetched_at") if cache else None
    attempt_at = cache.get("last_refresh_attempt_at") if cache else None
    last_error = cache.get("last_refresh_error") if cache else None
    models_map = (cache or {}).get("models", {}) or {}
    stale = _is_stale(fetched_at, now)

    models: list[ModelMetadata] = []
    for fav in favorites:
        entry = models_map.get(fav.id)
        if entry is None:
            models.append(ModelMetadata(
                litellm_id=fav.id, openrouter_id=to_openrouter_id(fav.id),
                canonical_slug=None, supported_parameters=[], pricing={},
                context_length=None, display_name=None, metadata_state="unknown"))
        else:
            models.append(ModelMetadata(
                litellm_id=fav.id,
                openrouter_id=entry.get("openrouter_id", to_openrouter_id(fav.id)),
                canonical_slug=entry.get("canonical_slug"),
                supported_parameters=list(entry.get("supported_parameters", []) or []),
                pricing=dict(entry.get("pricing", {}) or {}),
                context_length=entry.get("context_length"),
                display_name=entry.get("display_name"),
                metadata_state="stale" if stale else "known"))

    return CatalogView(
        models=models, fetched_at=fetched_at, last_refresh_attempt_at=attempt_at,
        last_refresh_error=last_error, cache_present=cache is not None, stale=stale)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_catalog.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/providers/openrouter_catalog.py mcp_server/tests/test_openrouter_catalog.py
git commit -m "$(printf 'feat(openrouter): pure-disk catalog load() with stale/unknown states\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 7: Catalog `refresh()` — networked, atomic, failure-observable

**Files:**
- Modify: `mcp_server/src/rook/providers/openrouter_catalog.py`
- Test: `mcp_server/tests/test_openrouter_catalog.py` (extend)

**Interfaces:**
- Consumes: `load_favorites`, `to_litellm_id`, `_cache_path`, `_read_cache`, constants (Tasks 5/6).
- Produces: `RefreshResult` dataclass, `refresh(api_key=None, favorites_path=None, cache_path=None, now=None, client=None) -> RefreshResult`, private `_fetch_models(api_key, client=None) -> list[dict]`, `_atomic_write_json(path, data)`, `_write_failure(...)`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_openrouter_catalog.py`:

```python
FIXTURE = [
    {"id": "anthropic/claude-3.7-sonnet", "canonical_slug": "anthropic/claude-3.7-sonnet",
     "name": "Anthropic: Claude 3.7 Sonnet", "context_length": 200000,
     "pricing": {"prompt": "0.000003", "completion": "0.000015"},
     "supported_parameters": ["tools", "tool_choice"]},
    {"id": "meta-llama/llama-3-8b", "canonical_slug": "meta-llama/llama-3-8b",
     "name": "Meta Llama 3 8B", "context_length": 8192,
     "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": []},
]


def _favorites(tmp_path, ids):
    p = tmp_path / "openrouter_favorites.json"
    p.write_text(json.dumps([{"id": i} for i in ids]), encoding="utf-8")
    return p


def test_refresh_normalizes_ids_and_matches_favorite(tmp_path, monkeypatch):
    monkeypatch.setattr(cat, "_fetch_models", lambda key, client=None: FIXTURE)
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])
    cache = tmp_path / "cache.json"
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    assert res.success is True
    assert res.models_fetched == 2
    assert res.favorites_matched == 1
    assert res.unknown_favorites == []          # bare catalog id matched LiteLLM favorite
    stored = json.loads(cache.read_text())["models"]
    assert "openrouter/anthropic/claude-3.7-sonnet" in stored
    assert stored["openrouter/anthropic/claude-3.7-sonnet"]["openrouter_id"] == "anthropic/claude-3.7-sonnet"


def test_refresh_flags_unknown_favorite(tmp_path, monkeypatch):
    monkeypatch.setattr(cat, "_fetch_models", lambda key, client=None: FIXTURE)
    fav = _favorites(tmp_path, ["openrouter/does/not-exist"])
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=tmp_path / "c.json")
    assert res.unknown_favorites == ["openrouter/does/not-exist"]


def test_refresh_missing_key_writes_status_only(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])
    cache = tmp_path / "c.json"
    res = cat.refresh(api_key=None, favorites_path=fav, cache_path=cache)
    assert res.success is False
    assert res.last_refresh_error["code"] == "missing_api_key"
    data = json.loads(cache.read_text())
    assert data["models"] == {}
    assert data["fetched_at"] is None


def test_failed_refresh_preserves_prior_models(tmp_path, monkeypatch):
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])
    cache = tmp_path / "c.json"
    monkeypatch.setattr(cat, "_fetch_models", lambda key, client=None: FIXTURE)
    cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    good = json.loads(cache.read_text())["models"]

    def _boom(key, client=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(cat, "_fetch_models", _boom)
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    assert res.success is False
    after = json.loads(cache.read_text())
    assert after["models"] == good                      # data preserved
    assert after["last_refresh_error"]["code"] == "fetch_failed"
    assert after["fetched_at"] is not None              # last success retained


def test_corrupt_prior_cache_failed_refresh_status_only(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text("{ not json", encoding="utf-8")
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])

    def _boom(key, client=None):
        raise RuntimeError("down")

    monkeypatch.setattr(cat, "_fetch_models", _boom)
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    assert res.success is False
    data = json.loads(cache.read_text())
    assert data["models"] == {}                         # no trusted prior data -> status-only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_catalog.py -v -k refresh`
Expected: FAIL with `AttributeError: module ... has no attribute 'refresh'`.

- [ ] **Step 3: Implement `refresh()` and helpers**

Append to `mcp_server/src/rook/providers/openrouter_catalog.py`:

```python
@dataclass
class RefreshResult:
    success: bool
    models_fetched: int
    favorites_matched: int
    unknown_favorites: list[str]
    cache_path: str
    source_endpoint: str
    fetched_at: Optional[str]
    last_refresh_error: Optional[dict]


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _fetch_models(api_key: str, client: Optional[httpx.Client] = None) -> list[dict]:
    """GET OpenRouter /models and return the ``data`` list. The only networked call."""
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        resp = client.get(
            OPENROUTER_MODELS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        body = resp.json()
    finally:
        if owns:
            client.close()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        raise ValueError("OpenRouter /models response missing 'data' list")
    return data


def _write_failure(cpath: Path, attempt_at: str, fav_ids: list[str], error: dict) -> "RefreshResult":
    prior = _read_cache(cpath)
    if prior and isinstance(prior.get("models"), dict):
        payload = dict(prior)
        payload["last_refresh_attempt_at"] = attempt_at
        payload["last_refresh_error"] = error
        models_map = prior["models"]
    else:
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "source_endpoint": OPENROUTER_MODELS_ENDPOINT,
            "fetched_at": None,
            "last_refresh_attempt_at": attempt_at,
            "last_refresh_error": error,
            "models": {},
        }
        models_map = {}
    _atomic_write_json(cpath, payload)
    unknown = [fid for fid in fav_ids if fid not in models_map]
    return RefreshResult(
        success=False, models_fetched=len(models_map),
        favorites_matched=len(fav_ids) - len(unknown), unknown_favorites=unknown,
        cache_path=str(cpath), source_endpoint=OPENROUTER_MODELS_ENDPOINT,
        fetched_at=payload.get("fetched_at"), last_refresh_error=error)


def refresh(
    api_key: Optional[str] = None,
    favorites_path: Optional[Path] = None,
    cache_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    client: Optional[httpx.Client] = None,
) -> RefreshResult:
    """Fetch the OpenRouter catalog and atomically update the cache.

    Never raises on network/auth/JSON failure — returns ``success=False`` and
    preserves prior catalog data (or writes a status-only cache when there is no
    trusted prior data).  This is the only networked path in the module.
    """
    cpath = _cache_path(cache_path)
    attempt_at = (now or datetime.now(timezone.utc)).isoformat()
    fav_ids = [f.id for f in load_favorites(favorites_path)]

    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return _write_failure(cpath, attempt_at, fav_ids,
                              {"code": "missing_api_key",
                               "message": "OPENROUTER_API_KEY is not set."})
    try:
        models_raw = _fetch_models(key, client)
    except Exception as exc:  # network, HTTP status, malformed JSON
        return _write_failure(cpath, attempt_at, fav_ids,
                              {"code": "fetch_failed", "message": str(exc)})

    models_map: dict[str, dict] = {}
    for model in models_raw:
        catalog_id = model.get("id")
        if not catalog_id:
            continue
        models_map[to_litellm_id(catalog_id)] = {
            "openrouter_id": catalog_id,
            "canonical_slug": model.get("canonical_slug"),
            "supported_parameters": list(model.get("supported_parameters", []) or []),
            "pricing": dict(model.get("pricing", {}) or {}),
            "context_length": model.get("context_length"),
            "display_name": model.get("name"),
        }

    unknown = [fid for fid in fav_ids if fid not in models_map]
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "source_endpoint": OPENROUTER_MODELS_ENDPOINT,
        "fetched_at": attempt_at,
        "last_refresh_attempt_at": attempt_at,
        "last_refresh_error": None,
        "models": models_map,
    }
    _atomic_write_json(cpath, payload)
    return RefreshResult(
        success=True, models_fetched=len(models_map),
        favorites_matched=len(fav_ids) - len(unknown), unknown_favorites=unknown,
        cache_path=str(cpath), source_endpoint=OPENROUTER_MODELS_ENDPOINT,
        fetched_at=attempt_at, last_refresh_error=None)
```

- [ ] **Step 4: Run the full catalog suite**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_catalog.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/providers/openrouter_catalog.py mcp_server/tests/test_openrouter_catalog.py
git commit -m "$(printf 'feat(openrouter): networked refresh() with atomic, failure-observable cache\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 8: MCP tool `openrouter_refresh_catalog` (with targeting policy)

**Files:**
- Modify: `mcp_server/src/rook/targeting.py:148` (`_ALL_KNOWN_TOOLS`) and `:571` (`_META_TOOLS`)
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py` (`PUBLIC_LEAN_TOOL_NAMES`)
- Modify: `mcp_server/src/rook/server.py` — `list_tools()` (~line 3133) and `_call_tool_dispatch` `match` (~line 13894)
- Modify: `mcp_server/tests/test_server_tool_profiles.py` (surface-count assertions: FULL 427→428, LEAN 17→18)
- Test: `mcp_server/tests/test_openrouter_tool.py`

**Interfaces:**
- Consumes: `rook.providers.openrouter_catalog.refresh()` and `RefreshResult` (Task 7).
- Produces: the `openrouter_refresh_catalog` tool returning `{"success": bool, "data": {...}}`, classified non-Rhino (`requires_rhino=False`), exposed under FULL + LEAN, hidden+blocked under READONLY.

**Two enforcement layers must BOTH be satisfied (verified on `origin/main` @ `e7afe408`):**
1. **Rhino targeting** — `policy_for_tool` returns `UNKNOWN_TOOL_POLICY = RhinoToolPolicy(requires_rhino=True, "mutate")` for any name not in `TOOL_POLICIES` (`targeting.py:70,758`). Adding the name to `_META_TOOLS` classifies it `(False, "meta")` so it is not Rhino-routed.
2. **MCP tool-exposure profile** (landed overnight) — `list_tools()` returns `filter_tools(live_tools, resolve_profile(os.environ))` (`server.py:13373`) and `call_tool` rejects calls where `tool_blocked(name, profile)` (`server.py:20928`). The readonly wall is **already generic**, so the tool is auto-hidden+blocked under READONLY by *not* being in `PUBLIC_READONLY_TOOL_NAMES`. We DO add it to `PUBLIC_LEAN_TOOL_NAMES` (operator-facing, non-Rhino-mutating); FULL exposure is automatic.

- [ ] **Step 1: Confirm the current (defective) default**

Run: `cd mcp_server && python -c "from rook import targeting; print(targeting.policy_for_tool('openrouter_refresh_catalog').requires_rhino)"`
Expected: `True` — confirms the tool would be wrongly Rhino-routed until we classify it.

- [ ] **Step 2: Write the failing tests**

Create `mcp_server/tests/test_openrouter_tool.py`:

```python
import asyncio
from rook import targeting
from rook import mcp_tool_profiles as mtp
import rook.server as server
import rook.providers.openrouter_catalog as cat


class _T:
    def __init__(self, name):
        self.name = name


def test_tool_is_non_rhino():
    assert targeting.policy_for_tool("openrouter_refresh_catalog").requires_rhino is False


def test_tool_is_listed_under_full(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "openrouter_refresh_catalog" in names


def test_lean_advertises_refresh():
    tools = [_T("openrouter_refresh_catalog"), _T("rhino_create")]
    names = {t.name for t in mtp.filter_tools(tools, mtp.Profile.LEAN)}
    assert "openrouter_refresh_catalog" in names


def test_readonly_hides_refresh():
    tools = [_T("openrouter_refresh_catalog")]
    assert mtp.filter_tools(tools, mtp.Profile.READONLY) == []


def test_tool_blocked_readonly_true():
    assert mtp.tool_blocked("openrouter_refresh_catalog", mtp.Profile.READONLY) is True


def test_tool_blocked_lean_false():
    assert mtp.tool_blocked("openrouter_refresh_catalog", mtp.Profile.LEAN) is False


def test_tool_dispatch_maps_result(monkeypatch):
    fake = cat.RefreshResult(
        success=True, models_fetched=2, favorites_matched=1, unknown_favorites=[],
        cache_path="X", source_endpoint=cat.OPENROUTER_MODELS_ENDPOINT,
        fetched_at="2026-06-29T00:00:00+00:00", last_refresh_error=None)
    monkeypatch.setattr(cat, "refresh", lambda *a, **k: fake)
    result = asyncio.run(server._call_tool_dispatch("openrouter_refresh_catalog", {}))
    assert result["success"] is True
    assert result["data"]["models_fetched"] == 2
    assert result["data"]["favorites_matched"] == 1
    assert result["data"]["source_endpoint"] == cat.OPENROUTER_MODELS_ENDPOINT
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_tool.py -v`
Expected: FAIL — `test_tool_is_non_rhino` (currently `True`), `test_tool_is_listed_under_full` (name absent), `test_lean_advertises_refresh` (not yet in LEAN set), and dispatch returns an unknown-tool result.

- [ ] **Step 4a: Classify the tool as non-Rhino in targeting**

In `mcp_server/src/rook/targeting.py`, add this exact line to BOTH the `_ALL_KNOWN_TOOLS` set (after `"agent_status",`, ~line 151) and the `_META_TOOLS` set (after `"agent_status",`, ~line 574):

```python
    "openrouter_refresh_catalog",
```

- [ ] **Step 4b: Advertise under LEAN (and, by omission, hide+block under READONLY)**

In `mcp_server/src/rook/mcp_tool_profiles.py`, add to the `PUBLIC_LEAN_TOOL_NAMES` frozenset (after `"gh_execute_intent",`):

```python
    "openrouter_refresh_catalog",
```

Do NOT add it to `PUBLIC_READONLY_TOOL_NAMES` — `filter_tools(READONLY)` then excludes it and `tool_blocked(name, READONLY)` returns `True` automatically. Do NOT add it to `SENTINEL_TOOL_NAMES` (a catalog refresh is idempotent and low-risk).

- [ ] **Step 4c: Register the tool schema**

In `mcp_server/src/rook/server.py`, inside `list_tools()`'s `all_tools = [` list (after the first `Tool(...)` entry, ~line 3137), add:

```python
        Tool(
            name="openrouter_refresh_catalog",
            description=(
                "Refresh the cached OpenRouter model catalog (pricing, context length, "
                "supported_parameters) for curated favorites. Networked, explicit, safe to "
                "re-run; never required for routing. Returns counts, provenance, and any "
                "favorites missing from the catalog."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
```

- [ ] **Step 4d: Add the dispatch case**

In `_call_tool_dispatch`'s `match name:` block (after the `case "rhino_instances":` entry, ~line 13907), add:

```python
        case "openrouter_refresh_catalog":
            import asyncio as _asyncio
            from .providers import openrouter_catalog as _orc
            _rr = await _asyncio.to_thread(_orc.refresh)
            result = {
                "success": _rr.success,
                "data": {
                    "models_fetched": _rr.models_fetched,
                    "favorites_matched": _rr.favorites_matched,
                    "unknown_favorites": _rr.unknown_favorites,
                    "cache_path": _rr.cache_path,
                    "source_endpoint": _rr.source_endpoint,
                    "fetched_at": _rr.fetched_at,
                    "last_refresh_error": _rr.last_refresh_error,
                },
            }
```

- [ ] **Step 4e: Update the surface-count assertions**

Adding one FULL tool and one LEAN tool shifts two pinned counts in `mcp_server/tests/test_server_tool_profiles.py` (READONLY is unchanged at 145). Make exactly these edits:
- line 29: `assert len(full) == 427` → `assert len(full) == 428`
- line 43: `assert len(lean) == 17` → `assert len(lean) == 18`
- line 60: `assert len(ro) + len(excluded) == len(full) == 427` → `assert len(ro) + len(excluded) == len(full) == 428`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_tool.py tests/test_server_tool_profiles.py -v`
Expected: PASS — 7 in `test_openrouter_tool.py`, and the existing profile suite green with the updated counts.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/src/rook/mcp_tool_profiles.py mcp_server/src/rook/server.py mcp_server/tests/test_openrouter_tool.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "$(printf 'feat(openrouter): openrouter_refresh_catalog MCP tool (non-Rhino, FULL+LEAN)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 9: Chirp confirmation (separate repo)

**Files:**
- Create: `C:/Users/aryan/source/repos/Chirp/tests/test_openrouter_passthrough.py`
- (No Chirp source changes — confirmation only.)

**Interfaces:**
- Consumes: `chirp.adapter.ChirpAdapter` and its `_make_lm` passthrough.
- Produces: a regression test proving `openrouter/...` flows through with no Anthropic demand.

- [ ] **Step 1: Write the failing/confirming test**

Create `C:/Users/aryan/source/repos/Chirp/tests/test_openrouter_passthrough.py`:

```python
import chirp.adapter as adapter_mod


class _StubLM:
    def __init__(self, model, **kwargs):
        self.model = model
        self.kwargs = kwargs


def test_openrouter_model_passes_through(monkeypatch):
    monkeypatch.setattr(adapter_mod.dspy, "LM", _StubLM)
    monkeypatch.setattr(adapter_mod.dspy, "configure", lambda **kw: None)
    monkeypatch.setenv("CHIRP_MODEL", "openrouter/anthropic/claude-3.7-sonnet")
    monkeypatch.delenv("CHIRP_PROVIDERS", raising=False)

    adapter = adapter_mod.ChirpAdapter()

    # The model string passes through verbatim; no api_key is injected — LiteLLM
    # resolves OPENROUTER_API_KEY itself, and there is no Anthropic-key demand.
    assert adapter._lm.model == "openrouter/anthropic/claude-3.7-sonnet"
    assert "api_key" not in adapter._lm.kwargs
```

- [ ] **Step 2: Run the test**

Run: `cd C:/Users/aryan/source/repos/Chirp && python -m pytest tests/test_openrouter_passthrough.py -v`
Expected: PASS (1 passed). (This is a confirmation test; Chirp already passes arbitrary model strings through, so it should pass without source changes. If it fails, the failure documents a real Chirp gap to address before claiming OpenRouter support for Chirp.)

- [ ] **Step 3: Commit (in the Chirp repo)**

```bash
cd C:/Users/aryan/source/repos/Chirp
git add tests/test_openrouter_passthrough.py
git commit -m "$(printf 'test(openrouter): confirm openrouter/ model passthrough\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

> Note: this commit lands in the Chirp repo, not the Rook worktree. Coordinate the two repos when opening PRs.

---

### Task 10: Gated live smoke + docs

**Files:**
- Create: `mcp_server/tests/test_openrouter_live_smoke.py`
- Modify: the design spec's status reference is already Approved; no spec change needed.

**Interfaces:**
- Consumes: `rook.providers.openrouter_catalog.refresh` / `load`.
- Produces: a gated, non-CI smoke test (skipped unless `OPENROUTER_LIVE_SMOKE` is set).

- [ ] **Step 1: Write the gated smoke test**

Create `mcp_server/tests/test_openrouter_live_smoke.py`:

```python
import os
import pytest

import rook.providers.openrouter_catalog as cat

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_SMOKE"),
    reason="gated: set OPENROUTER_LIVE_SMOKE=1 and OPENROUTER_API_KEY to run a real refresh",
)


def test_live_refresh_populates_cache(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text('[{"id": "openrouter/anthropic/claude-3.7-sonnet"}]', encoding="utf-8")
    cache = tmp_path / "cache.json"
    result = cat.refresh(favorites_path=fav, cache_path=cache)
    assert result.success is True, result.last_refresh_error
    assert result.models_fetched > 0
    view = cat.load(favorites_path=fav, cache_path=cache)
    # The curated model should resolve to known metadata after a real refresh.
    assert view.models[0].metadata_state == "known"
    assert "tools" in view.models[0].supported_parameters
```

- [ ] **Step 2: Verify it skips by default**

Run: `cd mcp_server && python -m pytest tests/test_openrouter_live_smoke.py -v`
Expected: SKIPPED (1 skipped) — confirms it never runs in CI without the gate.

- [ ] **Step 3: (Manual, optional) run the live smoke once before opening the PR**

Run (PowerShell): `cd mcp_server; $env:OPENROUTER_LIVE_SMOKE=1; python -m pytest tests/test_openrouter_live_smoke.py -v`
Expected: PASS against the live OpenRouter API (requires `OPENROUTER_API_KEY`). Record the outcome in the PR description per the repo's live-smoke-before-PR practice.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_openrouter_live_smoke.py
git commit -m "$(printf 'test(openrouter): gated live smoke (skipped unless OPENROUTER_LIVE_SMOKE)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Final verification

- [ ] **Run the whole new suite together**

Run: `cd mcp_server && python -m pytest tests/test_model_profiles_openrouter.py tests/test_dspy_openrouter_keys.py tests/test_runtime_health_providers.py tests/test_openrouter_catalog.py tests/test_openrouter_tool.py tests/test_openrouter_live_smoke.py -v`
Expected: all pass (live smoke SKIPPED).

- [ ] **Confirm no unintended diffs**

Run: `git status` and `git diff --stat origin/main`
Expected: only the files named across Tasks 1–8 and 10 in the Rook repo (Task 9 lives in the Chirp repo).

---

## Self-review (performed by plan author)

**Spec coverage** — every Spec A section maps to a task:
- §3.1 OpenRouterCatalog (`refresh`/`load`/normalization) → Tasks 5, 6, 7.
- §3.2 favorites + generated cache split → Tasks 5 (favorites + `.gitignore`), 7 (cache writes).
- §3.3 MCP tool → Task 8.
- §3.4 `api_key_env_for_model` helper → Task 2.
- §3.5 touch-points: routing → Task 1; DSPy (both functions) → Task 3; health (active-model-gated) + `.env.example` → Task 4; Chirp confirmation → Task 9. (Task 8 also satisfies BOTH overnight-`main` enforcement layers: the non-Rhino `targeting.py` policy AND the `mcp_tool_profiles.py` FULL/LEAN exposure + READONLY block, with surface-count tests updated 427→428 / 17→18.)
- §5 cache schema (success + failure/status-only) → Task 7.
- §6 invariants I1–I7 → I1/I2 (Task 6 load is pure-disk; routing untouched by cache), I3 (Task 4, gated on the active/effective model — not any-key), I4 (Task 7), I5/I6 (Task 2), I7 (Tasks 5/6 schema_version + `.gitignore`).
- §8 test matrix → Tasks 1–9 tests; live smoke → Task 10.

**Placeholder scan** — no TBD/TODO; every code/test step shows complete code and exact commands.

**Type/name consistency** — `api_key_env_for_model` (Task 2) is consumed verbatim in Tasks 3 & 4; `RefreshResult`/`refresh`/`load`/`to_litellm_id`/`to_openrouter_id` names are identical across Tasks 5–8; `_fetch_models` is the single monkeypatch seam used by Task 7 tests and the Task 10 live test.
