# Chirp Inference Timeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Chirp's effective 30-second inference cap with one configurable, bounded total request budget that propagates through the installed Rook release without changing model routing or migrating saved Grasshopper documents.

**Architecture:** Chirp owns an immutable startup policy (`300` default, `1800` maximum) and wraps its complete async DSPy call in one Python 3.10-compatible `asyncio.wait_for`. Generated C# receives a stable `1830`-second transport ceiling; Rook only admits a healthy sidecar, returns promptly when `/gh/script` defers verification, and uses the corrected `component_errors` vocabulary. Existing packaging and owned-host harnesses carry the exact accepted Chirp commit into payload-only local installation, installer source contracts, and one loopback-only response delayed beyond 30 seconds.

**Tech Stack:** Python 3.10-compatible asyncio, FastAPI, DSPy/LiteLLM, generated RhinoCode C#, Rook Python MCP, PowerShell release guards, Inno Setup, pytest, owned Rhino/Grasshopper runtime harness.

## Global Constraints

- Rook specification head is `026c84059558f3df523040f6eac35a7af5272ba1`; the approved plan commit must be its direct child.
- Chirp timeout work starts from immutable `master` merge `b0acae1c91243ec7bc1de58138ac17ae58fdcb05`.
- Preserve Chirp's declared Python `>=3.10` floor and Rook's shipped CPython `3.11.9`; do not change dependency metadata or lockfiles.
- Use one total inference budget: default `300`, accepted range `1..1800`, generated client ceiling `1830`, installed acceptance watchdog `1860` seconds.
- Use the full `await asyncio.wait_for(adapter.acall(signature=req.signature, inputs=req.inputs, schema=req.schema_, category=req.category, use_cache=req.cache, model=req.model), timeout=inference_timeout_seconds)` call shown in Task 1 for the aggregate deadline. Do not use `asyncio.timeout`, `shield`, worker threads, background abandonment, remaining-time arithmetic, custom retry scheduling, or a compatibility shim.
- Every `dspy.LM` receives the configured timeout; DSPy retries remain unchanged and share the one outer budget.
- `wait_for` may return after the nominal deadline while cancellation completes; the HTTP 504 must remain within the 30-second transport slack.
- Invalid timeout configuration disables only Chirp. It must not initialize models, generate source, mutate Grasshopper, or prevent Rook MCP from starting.
- `/chirp/create` performs admission and deterministic source generation only; it receives no inference deadline.
- Existing saved Grasshopper components are completely out of scope: no scan, marker, regeneration, migration, or compatibility machinery.
- Rename only the active Chirp contract from `compilation_errors` to `component_errors`; do not alter the separate `gh_create_script` compiler-diagnostic contract.
- Preserve current Opus 5 planner/default and Sonnet 5 non-planner behavior from the Chirp base.
- No native C++, managed C#, RookBIM, FFmpeg, general bridge timeout, MCP model routing, installer subsystem, dependency, version, or public-repository change belongs in the private implementation or focused acceptance.
- Public release notes and promotion occur after private acceptance and record the accepted Rook SHA, accepted Chirp SHA, and artifact hashes.

---

## File Map

### Chirp repository

| Path | Responsibility |
| --- | --- |
| `src/chirp/timeout_policy.py` | New immutable canonical `.env` loader and strict timeout parser. |
| `src/chirp/adapter.py` | Async DSPy execution and explicit timeout on every LM. |
| `src/chirp/server.py` | Startup admission, health/degraded responses, aggregate `wait_for`, and 504 taxonomy. |
| `src/chirp/rook_tool.py` | Generated C# `1830` ceiling and runtime timeout classification. |
| `src/chirp/__main__.py` | Explicit canonical `.env` load and fixed 30-second Uvicorn shutdown. |
| `templates/chirp_script_template.cs` | Current illustrative generated-client contract. |
| `templates/example_intent_to_params.cs` | Current example generated-client contract. |
| `README.md` | Active timeout configuration and forward-only generated-client behavior. |
| `tests/test_timeout_policy.py` | Strict parsing, precedence, immutability, and canonical-path tests. |
| `tests/test_adapter.py` | Async call path, LM timeout propagation, model-default preservation, and cancellation. |
| `tests/test_openrouter_passthrough.py` | Existing direct adapter consumer updated for the required timeout constructor. |
| `tests/test_server.py` | Health, degraded admission, exact 504, external cancellation, and create behavior. |
| `tests/test_rook_tool.py` | Generated source ceiling and error-code assertions. |

### Rook repository

| Path | Responsibility |
| --- | --- |
| `mcp_server/src/rook/chirp_manager.py` | Parse Chirp health and short-circuit the exact terminal configuration state. |
| `mcp_server/src/rook/server.py` | Chirp admission, actual `/gh/script` deferred response, and `component_errors`. |
| `mcp_server/src/rook/local_testing_proof.py` | Installed loopback slow-provider acceptance and the 1860-second watchdog. |
| `installer/RookSetup.iss` | Preserve existing Chirp `.env`; seed timeout only with a new keyed `.env`. |
| `installer/post_install.py` | Add timeout to newly generated Chirp `.env.example`. |
| `.agents/skills/chirp/SKILL.md` | Agent-facing timeout/error interpretation. |
| `.claude/skills/chirp/SKILL.md` | Byte-identical Chirp skill mirror. |
| `installer/agent-assets/codex-skills/chirp/SKILL.md` | Byte-identical installed Chirp skill mirror. |
| `.agents/skills/chirp-cascade/SKILL.md` | Cascade timeout/error interpretation. |
| `.claude/skills/chirp-cascade/SKILL.md` | Byte-identical cascade mirror. |
| `installer/agent-assets/codex-skills/chirp-cascade/SKILL.md` | Byte-identical installed cascade mirror. |
| `mcp_server/tests/test_chirp_manager.py` | Structured health and terminal short-circuit tests. |
| `mcp_server/tests/test_server_contract_hardening.py` | Chirp admission and deferred-verification dispatch tests. |
| `mcp_server/tests/test_local_testing_proof.py` | Slow provider, watchdog, output verification, and bounded cleanup tests. |
| `mcp_server/tests/test_chirp_timeout_contract.py` | New scoped vocabulary, mirror, and timeout ownership guard. |
| `scripts/tests/deploy-local-testing-guards.tests.ps1` | Release source propagation and `.env` non-mutation guard. |
| `scripts/tests/python-runtime-packaging.tests.ps1` | Existing unchanged gate for Chirp source/commit manifest requirements. |
| `scripts/tests/release-installer-guards.tests.ps1` | Exact installer `.env` behavior and generated example contract. |

No other production path is pre-authorized. Stop if implementation evidence requires one.

---

### Task 0: Pin both repositories and capture the RED baseline

**Files:**
- Read: `docs/superpowers/specs/2026-08-05-chirp-inference-timeout-design.md`
- Read: `docs/superpowers/plans/2026-08-05-chirp-inference-timeout.md`
- No tracked writes

**Interfaces:**
- Consumes: approved annotated tag `plan/chirp-inference-timeout-2026-08-05-approved`.
- Produces: clean Rook implementation checkout and clean Chirp timeout worktree at the exact approved bases.

- [ ] **Step 1: Verify the Rook execution pin before any edits**

Run from the Rook design worktree:

```powershell
$rookRoot = (Get-Location).Path
$specHead = '026c84059558f3df523040f6eac35a7af5272ba1'
$tag = 'plan/chirp-inference-timeout-2026-08-05-approved'
$tagHead = (git rev-parse "$tag^{}" ).Trim()
$head = (git rev-parse HEAD).Trim()
$parent = (git rev-parse HEAD^).Trim()
if ($tagHead -ne $head) { throw "Approval tag resolves to $tagHead, expected $head" }
if ($parent -ne $specHead) { throw "Plan parent is $parent, expected $specHead" }
if (git status --porcelain) { throw 'Rook worktree is dirty before execution' }
$planPaths = @(git diff-tree --no-commit-id --name-only -r HEAD)
if ($planPaths.Count -ne 1 -or $planPaths[0] -ne 'docs/superpowers/plans/2026-08-05-chirp-inference-timeout.md') {
    throw "Unexpected plan commit scope: $($planPaths -join ', ')"
}
```

Expected: the tag resolves to the plan commit, its direct parent is the approved specification, the plan commit changes one file, and the worktree is clean.

- [ ] **Step 2: Create an isolated Chirp timeout worktree from the immutable base**

```powershell
$chirpRepo = 'C:\Users\aryan\source\repos\Chirp'
$chirpBase = 'b0acae1c91243ec7bc1de58138ac17ae58fdcb05'
$chirpWorktree = 'C:\Users\aryan\source\repos\Chirp\.worktrees\chirp-inference-timeout'
git -C $chirpRepo fetch origin --prune
if ((git -C $chirpRepo rev-parse origin/master).Trim() -ne $chirpBase) {
    throw 'Chirp origin/master moved; stop for provenance review'
}
if (Test-Path -LiteralPath $chirpWorktree) {
    throw "Chirp worktree path already exists: $chirpWorktree"
}
git -C $chirpRepo worktree add $chirpWorktree -b codex/chirp-inference-timeout $chirpBase
if (git -C $chirpWorktree status --porcelain) { throw 'New Chirp worktree is dirty' }
```

Expected: a clean `codex/chirp-inference-timeout` worktree whose `HEAD` is exactly `b0acae1c91243ec7bc1de58138ac17ae58fdcb05`.

- [ ] **Step 3: Create ignored worktree-local test environments**

For Rook:

```powershell
Set-Location "$rookRoot\mcp_server"
uv sync --frozen --extra test --python "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
.\.venv\Scripts\python.exe -c "import sys, importlib.metadata as m; assert sys.version_info[:2] == (3, 11); print(m.version('rook-mcp'))"
.\.venv\Scripts\python.exe -m pip check
```

For Chirp:

```powershell
Set-Location $chirpWorktree
& "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
```

Expected: both ignored `.venv` directories are usable; no tracked dependency file changes.

- [ ] **Step 4: Run the unchanged focused baseline**

```powershell
Set-Location $chirpWorktree
.\.venv\Scripts\python.exe -m pytest tests -q

Set-Location "$rookRoot\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_chirp_manager.py `
    tests/test_server_contract_hardening.py `
    tests/test_local_testing_proof.py -q

Set-Location $rookRoot
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
```

Expected: current focused tests pass. Record their exact counts. Do not run a repository-wide suite.

- [ ] **Step 5: Record the intended RED assertions before production edits**

Add no files yet. Confirm these searches expose the defect:

```powershell
rg -n 'TimeSpan\.FromSeconds\(30\)' "$chirpWorktree\src\chirp\rook_tool.py" "$chirpWorktree\templates"
rg -n 'load_dotenv\(\)' "$chirpWorktree\src\chirp\server.py" "$chirpWorktree\src\chirp\__main__.py"
rg -n 'compilation_errors' "$rookRoot\mcp_server\src\rook\server.py" "$rookRoot\mcp_server\src\rook\local_testing_proof.py"
```

Expected: the generated client contains the 30-second cap, Chirp searches for `.env`, and the active Chirp Rook paths contain the old response name. These are the RED baseline facts; unrelated `gh_create_script` uses of `compilation_errors` remain valid.

**Checkpoint:** stop if either repository moved, either baseline is dirty, dependency files changed, or focused baseline failures are unexplained.

---

### Task 1: Add Chirp's immutable timeout policy and async aggregate deadline

**Files:**
- Create: `src/chirp/timeout_policy.py`
- Create: `tests/test_timeout_policy.py`
- Modify: `src/chirp/adapter.py`
- Modify: `src/chirp/server.py`
- Modify: `src/chirp/__main__.py`
- Modify: `tests/test_adapter.py`
- Modify: `tests/test_openrouter_passthrough.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: canonical Chirp home from `CHIRP_HOME`, otherwise the package repository/install root.
- Produces: `InferenceTimeoutPolicy`, `load_canonical_environment() -> Path`, `read_inference_timeout_policy() -> InferenceTimeoutPolicy`, and `ChirpAdapter.acall()`.
- `InferenceTimeoutPolicy.timeout_seconds` is an integer only when valid; invalid policy exposes only the stable code and fixed safe message.

- [ ] **Step 1: Write strict timeout-policy tests**

Create `tests/test_timeout_policy.py` with table-driven cases for absence, `1`, `300`, `1800`, and invalid values:

```python
import os
from pathlib import Path

import pytest

from chirp.timeout_policy import (
    DEFAULT_INFERENCE_TIMEOUT_SECONDS,
    INVALID_TIMEOUT_CODE,
    INVALID_TIMEOUT_MESSAGE,
    load_canonical_environment,
    read_inference_timeout_policy,
)


@pytest.mark.parametrize(
    "raw",
    ["", "0", "1801", "-1", "+300", "300.0", "3e2", "300s", " 300", "300 ", "٣٠٠", "9" * 5000],
)
def test_invalid_timeout_values_disable_chirp(monkeypatch, tmp_path: Path, raw):
    monkeypatch.setenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", raw)
    policy = read_inference_timeout_policy(tmp_path)
    assert policy.timeout_seconds is None
    assert policy.error_code == INVALID_TIMEOUT_CODE
    assert policy.error_message == INVALID_TIMEOUT_MESSAGE


def test_absence_uses_builtin_default(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", raising=False)
    policy = read_inference_timeout_policy(tmp_path)
    assert policy.timeout_seconds == DEFAULT_INFERENCE_TIMEOUT_SECONDS == 300
    assert policy.error_code is None


def test_process_environment_wins_over_canonical_env(monkeypatch, tmp_path: Path):
    (tmp_path / ".env").write_text("CHIRP_INFERENCE_TIMEOUT_SECONDS=600\n", encoding="utf-8")
    monkeypatch.setenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", "900")
    assert read_inference_timeout_policy(tmp_path).timeout_seconds == 900


def test_present_invalid_process_value_does_not_fall_through(monkeypatch, tmp_path: Path):
    (tmp_path / ".env").write_text("CHIRP_INFERENCE_TIMEOUT_SECONDS=600\n", encoding="utf-8")
    monkeypatch.setenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", "bad")
    assert read_inference_timeout_policy(tmp_path).error_code == INVALID_TIMEOUT_CODE


@pytest.mark.parametrize("raw", ["", " 300", "300 ", '"300"', "300 # seconds"])
def test_canonical_env_timeout_is_not_normalized(monkeypatch, tmp_path: Path, raw):
    monkeypatch.delenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", raising=False)
    (tmp_path / ".env").write_text(
        f"CHIRP_INFERENCE_TIMEOUT_SECONDS={raw}\n", encoding="utf-8"
    )
    assert read_inference_timeout_policy(tmp_path).error_code == INVALID_TIMEOUT_CODE


def test_policy_is_immutable_after_startup(monkeypatch, tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("CHIRP_INFERENCE_TIMEOUT_SECONDS=600\n", encoding="utf-8")
    monkeypatch.delenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", raising=False)
    policy = read_inference_timeout_policy(tmp_path)
    env_path.write_text("CHIRP_INFERENCE_TIMEOUT_SECONDS=900\n", encoding="utf-8")
    assert policy.timeout_seconds == 600


def test_canonical_env_does_not_follow_working_directory(monkeypatch, tmp_path: Path):
    chirp_home = tmp_path / "chirp-home"
    other = tmp_path / "other"
    chirp_home.mkdir()
    other.mkdir()
    (chirp_home / ".env").write_text(
        "CHIRP_INFERENCE_TIMEOUT_SECONDS=600\n", encoding="utf-8"
    )
    (other / ".env").write_text(
        "CHIRP_INFERENCE_TIMEOUT_SECONDS=900\n", encoding="utf-8"
    )
    monkeypatch.delenv("CHIRP_INFERENCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.chdir(other)
    assert read_inference_timeout_policy(chirp_home).timeout_seconds == 600


def test_python_floor_and_timeout_primitive_remain_python_310_compatible():
    root = Path(__file__).resolve().parents[1]
    assert 'requires-python = ">=3.10"' in (root / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    active_source = "\n".join(
        (root / relative).read_text(encoding="utf-8")
        for relative in (
            "src/chirp/server.py",
            "src/chirp/adapter.py",
            "src/chirp/__main__.py",
        )
    )
    assert "asyncio.timeout" not in active_source
    assert active_source.count("timeout_graceful_shutdown=30") == 2
```

- [ ] **Step 2: Run the policy tests and confirm RED**

```powershell
Set-Location $chirpWorktree
.\.venv\Scripts\python.exe -m pytest tests/test_timeout_policy.py -q
```

Expected: collection fails because `chirp.timeout_policy` does not exist.

- [ ] **Step 3: Implement the small immutable policy module**

Create `src/chirp/timeout_policy.py` with these exact public values and shapes:

```python
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping

from dotenv import dotenv_values

TIMEOUT_ENV_NAME = "CHIRP_INFERENCE_TIMEOUT_SECONDS"
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 300
MAX_INFERENCE_TIMEOUT_SECONDS = 1800
TRANSPORT_SLACK_SECONDS = 30
ACCEPTANCE_SLACK_SECONDS = 30
GENERATED_CLIENT_TIMEOUT_SECONDS = (
    MAX_INFERENCE_TIMEOUT_SECONDS + TRANSPORT_SLACK_SECONDS
)
ACCEPTANCE_WATCHDOG_SECONDS = (
    GENERATED_CLIENT_TIMEOUT_SECONDS + ACCEPTANCE_SLACK_SECONDS
)
INVALID_TIMEOUT_CODE = "chirp_invalid_inference_timeout"
INVALID_TIMEOUT_MESSAGE = (
    "Chirp is disabled because CHIRP_INFERENCE_TIMEOUT_SECONDS must contain "
    "only ASCII digits and resolve to 1–1800 seconds."
)
_ASCII_WHOLE_SECONDS = re.compile(r"[0-9]+", re.ASCII)
_TIMEOUT_ASSIGNMENT = re.compile(
    rf"^\s*(?:export\s+)?{re.escape(TIMEOUT_ENV_NAME)}\s*="
)


@dataclass(frozen=True)
class InferenceTimeoutPolicy:
    timeout_seconds: int | None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def enabled(self) -> bool:
        return self.timeout_seconds is not None


def canonical_chirp_home(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    configured = source.get("CHIRP_HOME")
    return Path(configured) if configured else Path(__file__).resolve().parents[2]


def _invalid_policy() -> InferenceTimeoutPolicy:
    return InferenceTimeoutPolicy(None, INVALID_TIMEOUT_CODE, INVALID_TIMEOUT_MESSAGE)


def _parse_timeout(*, present: bool, raw: str | None) -> InferenceTimeoutPolicy:
    if not present:
        return InferenceTimeoutPolicy(DEFAULT_INFERENCE_TIMEOUT_SECONDS)
    if raw is None or _ASCII_WHOLE_SECONDS.fullmatch(raw) is None:
        return _invalid_policy()
    try:
        seconds = int(raw)
    except ValueError:
        return _invalid_policy()
    if not 1 <= seconds <= MAX_INFERENCE_TIMEOUT_SECONDS:
        return _invalid_policy()
    return InferenceTimeoutPolicy(seconds)


def _read_exact_file_timeout(env_path: Path) -> tuple[bool, str | None]:
    if not env_path.is_file():
        return False, None
    prefix = f"{TIMEOUT_ENV_NAME}="
    values: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            values.append(line[len(prefix):])
        elif _TIMEOUT_ASSIGNMENT.match(line):
            return True, None
    if not values:
        return False, None
    if len(values) != 1:
        return True, None
    return True, values[0]


def load_canonical_environment(
    chirp_home: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> Path:
    source = os.environ if environ is None else environ
    home = canonical_chirp_home(source) if chirp_home is None else Path(chirp_home)
    env_path = home / ".env"
    if env_path.is_file():
        for key, value in dotenv_values(env_path).items():
            if key != TIMEOUT_ENV_NAME and value is not None:
                source.setdefault(key, value)
    return env_path


def read_inference_timeout_policy(
    chirp_home: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> InferenceTimeoutPolicy:
    source = os.environ if environ is None else environ
    env_path = load_canonical_environment(chirp_home, source)
    if TIMEOUT_ENV_NAME in source:
        return _parse_timeout(present=True, raw=source[TIMEOUT_ENV_NAME])
    present, raw = _read_exact_file_timeout(env_path)
    return _parse_timeout(present=present, raw=raw)
```

Do not log or return `raw`.

- [ ] **Step 4: Add failing async adapter/server tests**

Update every adapter-test constructor to `ChirpAdapter(inference_timeout_seconds=300)`. Change each fake DSPy program from `__call__` to `async def acall`, await `adapter.acall()`, and require both default and override `dspy.LM` calls to include `timeout=300` without changing their model assertions.

Add these server behaviors to `tests/test_server.py`:

```python
import asyncio
import json
import time

import pytest

import chirp.adapter as adapter_module
import chirp.server as server


def _call_request() -> server.CallRequest:
    return server.CallRequest(
        signature="input -> result",
        inputs={"input": "x"},
        schema={"result": "string"},
        cache=False,
    )


@pytest.mark.asyncio
async def test_wait_for_timeout_cancels_fake_provider_and_returns_504(monkeypatch):
    cancelled = asyncio.Event()
    provider_calls = 0

    class FakeProviderProgram:
        def __init__(self, _signature):
            pass

        async def acall(self, **_inputs):
            nonlocal provider_calls
            provider_calls += 1
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

    monkeypatch.setitem(adapter_module._MODULE_MAP, "ChainOfThought", FakeProviderProgram)
    monkeypatch.setattr(server, "inference_timeout_seconds", 0.02)
    started = time.monotonic()
    response = await server.chirp_call(_call_request())
    elapsed = time.monotonic() - started
    assert response.status_code == 504
    assert json.loads(response.body) == {
        "error": "chirp_inference_timeout",
        "details": "Chirp inference exceeded its configured total request budget.",
        "timeout_seconds": 0.02,
    }
    assert provider_calls == 1
    assert cancelled.is_set()
    assert elapsed < 0.5
    await asyncio.sleep(0.05)
    assert provider_calls == 1


@pytest.mark.asyncio
async def test_external_cancellation_is_not_timeout(monkeypatch):
    entered = asyncio.Event()

    async def blocked_acall(**_kwargs):
        entered.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(server.adapter, "acall", blocked_acall)
    task = asyncio.create_task(server.chirp_call(_call_request()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
```

Add import-reload tests with `CHIRP_INFERENCE_TIMEOUT_SECONDS=bad` proving invalid configuration returns the specification's exact health HTTP 200 and exact 503 bodies for both endpoints while a patched `ChirpAdapter` constructor is never called. In the external-cancellation test, the only accepted outcome is the raised `CancelledError`; no response body may be returned.

- [ ] **Step 5: Run async tests and confirm RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_adapter.py tests/test_openrouter_passthrough.py tests/test_server.py -q
```

Expected: failures because the adapter and endpoint are still synchronous and no policy admission exists.

- [ ] **Step 6: Convert the adapter and server without adding retry machinery**

In `adapter.py`, make only these mechanical changes inside the existing class: require `inference_timeout_seconds` in `__init__`, store it, initialize every LM with that timeout, rename `call` to `acall`, and await the existing DSPy program:

```python
class ChirpAdapter:
    def __init__(self, *, inference_timeout_seconds: int) -> None:
        self._inference_timeout_seconds = inference_timeout_seconds

    def _make_lm(self, model: str) -> dspy.LM:
        kwargs: dict = {"timeout": self._inference_timeout_seconds}
        provider_cfg = self._providers.get(model)
        if provider_cfg:
            if "api_base" in provider_cfg:
                kwargs["api_base"] = provider_cfg["api_base"]
            api_key_env = provider_cfg.get("api_key_env")
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    kwargs["api_key"] = api_key
        return dspy.LM(model, **kwargs)

    async def acall(
        self,
        signature: str,
        inputs: dict,
        schema: dict[str, str],
        *,
        category: str | None = None,
        use_cache: bool | None = None,
        model: str | None = None,
    ) -> dict:
        if override_lm is not None:
            with dspy.context(lm=override_lm):
                prediction = await predict.acall(**inputs)
        else:
            prediction = await predict.acall(**inputs)
```

All current cache-key, correction, category, typed-signature, coercion, usage, result, and cache-write statements stay in their current order around this async substitution. Do not retain a synchronous `call` alias.

In `server.py`, replace the implicit dotenv load and unconditional adapter construction with this one-time startup state:

```python
inference_timeout_policy = read_inference_timeout_policy()
inference_timeout_seconds = inference_timeout_policy.timeout_seconds
adapter = (
    ChirpAdapter(inference_timeout_seconds=inference_timeout_seconds)
    if inference_timeout_seconds is not None
    else None
)


def _invalid_timeout_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": INVALID_TIMEOUT_CODE,
            "details": INVALID_TIMEOUT_MESSAGE,
        },
    )
```

Both `/chirp/create` and `/chirp/call` return `_invalid_timeout_response()` before accessing `adapter` or generating source when `inference_timeout_policy.enabled` is false. Healthy and disabled `/health` bodies match the specification byte-for-field and remain HTTP 200. After this admission, make `/chirp/call` async and use exactly:

```python
try:
    result = await asyncio.wait_for(
        adapter.acall(
            signature=req.signature,
            inputs=req.inputs,
            schema=req.schema_,
            category=req.category,
            use_cache=req.cache,
            model=req.model,
        ),
        timeout=inference_timeout_seconds,
    )
except asyncio.TimeoutError:
    return JSONResponse(
        status_code=504,
        content={
            "error": "chirp_inference_timeout",
            "details": "Chirp inference exceeded its configured total request budget.",
            "timeout_seconds": inference_timeout_seconds,
        },
    )
except asyncio.CancelledError:
    raise
```

Compute `effective_model` only after admission because `adapter` is absent in degraded mode. Keep the existing success/error tracing and generic 500 response after these two branches. `/chirp/create` does not call `wait_for`.

- [ ] **Step 7: Pin canonical startup and bounded Uvicorn shutdown**

Remove both bare `load_dotenv()` calls. `server.py` obtains its one immutable timeout policy through `read_inference_timeout_policy()`, which loads unrelated variables only from the canonical file while parsing this setting from its exact assignment. `__main__.py` calls `load_canonical_environment()` before reading port/reload settings, then uses:

```python
config = uvicorn.Config(
    "chirp.server:app",
    host="127.0.0.1",
    timeout_graceful_shutdown=30,
)
```

Pass the same fixed shutdown value to the reload-mode `uvicorn.run`. Do not derive it from inference configuration.

- [ ] **Step 8: Run the Chirp policy/runtime GREEN gate**

```powershell
.\.venv\Scripts\python.exe -m pytest `
    tests/test_timeout_policy.py `
    tests/test_adapter.py `
    tests/test_openrouter_passthrough.py `
    tests/test_server.py -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: all focused tests pass, cancellation reaches the fake DSPy/provider coroutine, and no dependency metadata changes.

- [ ] **Step 9: Commit the Chirp policy/runtime slice**

```powershell
git add src/chirp/timeout_policy.py src/chirp/adapter.py src/chirp/server.py src/chirp/__main__.py tests/test_timeout_policy.py tests/test_adapter.py tests/test_openrouter_passthrough.py tests/test_server.py
git commit -m "fix: bound Chirp inference with one timeout policy"
```

**Checkpoint:** review this commit before generated-client work. Reject any model-default, dependency, lockfile, or unrelated server change.

---

### Task 2: Raise the generated-client ceiling and classify runtime timeouts

**Files:**
- Modify: `src/chirp/rook_tool.py`
- Modify: `templates/chirp_script_template.cs`
- Modify: `templates/example_intent_to_params.cs`
- Modify: `tests/test_rook_tool.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Chirp HTTP 504 code `chirp_inference_timeout` and maximum policy `1800`.
- Produces: generated RhinoCode C# with `1830` transport ceiling and `chirp_transport_timeout` classification.

- [ ] **Step 1: Write failing generated-source assertions**

In `tests/test_rook_tool.py`, generate one normal inference-capable script and assert:

```python
assert "TimeSpan.FromSeconds(1830)" in script
assert "HttpStatusCode.GatewayTimeout" in script
assert "chirp_inference_timeout" in script
assert "catch (TaskCanceledException)" in script
assert "chirp_transport_timeout" in script
assert ".GetAwaiter().GetResult()" in script
assert "TimeSpan.FromSeconds(30)" not in script
```

Retain the existing deterministic-only assertion that no `HttpClient` is generated.

- [ ] **Step 2: Run the generated-source test and confirm RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rook_tool.py -q
```

Expected: the new assertions fail against the 30-second generated client.

- [ ] **Step 3: Update the generator and the two active templates**

Import `GENERATED_CLIENT_TIMEOUT_SECONDS` from `chirp.timeout_policy`, emit `using System.Net;` and `using System.Threading.Tasks;`, and generate the timeout line from that derived constant. The rendered C# remains:

```csharp
private static readonly HttpClient _client = new HttpClient()
{
    Timeout = TimeSpan.FromSeconds(1830)
};
```

Replace blocking `.Result` calls with `.GetAwaiter().GetResult()` and classify responses/cancellation:

```csharp
var response = _client.PostAsync(url, content).GetAwaiter().GetResult();
var body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();

if (response.StatusCode == HttpStatusCode.GatewayTimeout)
    throw new Exception($"chirp_inference_timeout: {body}");
if (!response.IsSuccessStatusCode)
    throw new Exception($"Chirp error ({response.StatusCode}): {body}");
```

Add this catch before the existing `HttpRequestException` and generic branches:

```csharp
catch (TaskCanceledException)
{
    throw new Exception("chirp_transport_timeout: Chirp transport exceeded its 1830-second safety ceiling.");
}
```

Apply the same contract to both active template examples. Do not add runtime configuration to generated C#.

- [ ] **Step 4: Correct active Chirp documentation**

In `README.md`, add only:

- `CHIRP_INFERENCE_TIMEOUT_SECONDS`, default `300`, valid `1..1800`, read at startup.
- the aggregate-budget meaning across retries;
- the stable generated-client ceiling of `1830`;
- `chirp_inference_timeout` versus `chirp_transport_timeout`;
- forward-only behavior for newly generated components.

Do not add saved-document migration instructions or rewrite model-default documentation.

- [ ] **Step 5: Run the complete Chirp GREEN gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip check
rg -n 'TimeSpan\.FromSeconds\(30\)' src/chirp templates
git diff --check
```

Expected: the full Chirp suite passes and the search returns no active 30-second generated-client literal.

- [ ] **Step 6: Commit the generated-client slice**

```powershell
git add src/chirp/rook_tool.py templates/chirp_script_template.cs templates/example_intent_to_params.cs tests/test_rook_tool.py README.md
git commit -m "fix: prevent generated Chirps from preempting inference"
```

- [ ] **Step 7: Review and merge the Chirp PR before Rook release acceptance**

```powershell
git status --short
git diff --check b0acae1c91243ec7bc1de58138ac17ae58fdcb05..HEAD
git log --oneline b0acae1c91243ec7bc1de58138ac17ae58fdcb05..HEAD
```

Push `codex/chirp-inference-timeout`, open a Chirp PR to `master`, run the full Chirp gate, and use a regular merge commit. Record the reviewed head and resulting two-parent merge SHA as `$acceptedChirpSha`. Do not squash the model-default prerequisite into this PR; it is already in the first-parent base.

**Checkpoint:** Rook packaging and installed acceptance remain blocked until the exact accepted Chirp merge is known.

---

### Task 3: Make Rook fail closed on Chirp configuration and honor deferred script verification

**Files:**
- Modify: `mcp_server/src/rook/chirp_manager.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_chirp_manager.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

**Interfaces:**
- Consumes: Chirp health `status`, `error.code`, and `error.message`; `/gh/script` response stored in `script_result`.
- Produces: `ensure_chirp_running()` result with optional `error_code`; Chirp create data with received `verification_deferred` and `solve_scheduled`.

- [ ] **Step 1: Write failing structured-health tests**

Extend `test_chirp_manager.py` with exact healthy, terminal-disabled, malformed, and still-starting responses. The terminal case must prove no additional sleep/poll occurs:

```python
@pytest.mark.asyncio
async def test_discovered_terminal_timeout_config_short_circuits_without_polling(monkeypatch):
    sleeps = []
    health_calls = 0

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_health(_host, _port):
        nonlocal health_calls
        health_calls += 1
        return {
            "status": "disabled",
            "version": "0.1.0",
            "error": {
                "code": "chirp_invalid_inference_timeout",
                "message": chirp_manager.INVALID_TIMEOUT_MESSAGE,
            },
        }

    monkeypatch.setattr(chirp_manager.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)
    monkeypatch.setattr(
        chirp_manager,
        "_find_live_discovery",
        lambda: {"host": "127.0.0.1", "port": 9900, "pid": 1234},
    )
    result = await chirp_manager.ensure_chirp_running()
    assert result["running"] is False
    assert result["error_code"] == "chirp_invalid_inference_timeout"
    assert health_calls == 1
    assert sleeps == []
```

Healthy response returns `running=True`; other unreachable or nonterminal payloads retain the existing 45-second behavior.

- [ ] **Step 2: Write failing Chirp admission and deferred-verification tests**

In `test_server_contract_hardening.py`, add:

1. Terminal invalid config returns `success=False` before constructing the Chirp HTTP client or calling any Rhino route.
2. Inference-capable creation receives:

```python
{"success": True, "data": {"verification_deferred": True, "solve_scheduled": True}}
```

from `/gh/script`; it must not call `asyncio.sleep` or `/gh/errors`, and its result contains those two booleans but no `component_errors`.
3. Deterministic-only creation still performs the short delay and `/gh/errors` even when the script response carries deferred scheduling fields.
4. Non-deferred verification reports only `component_errors`, never the old Chirp field.

- [ ] **Step 3: Run the Rook contract tests and confirm RED**

```powershell
Set-Location "$rookRoot\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_chirp_manager.py tests/test_server_contract_hardening.py -q
```

Expected: failures because health is boolean-only and Chirp create always probes `/gh/errors`.

- [ ] **Step 4: Parse health without creating a lifecycle framework**

Define only these two mirrored wire constants in `chirp_manager.py` because Rook and Chirp run in separate environments:

```python
INVALID_TIMEOUT_CODE = "chirp_invalid_inference_timeout"
INVALID_TIMEOUT_MESSAGE = (
    "Chirp is disabled because CHIRP_INFERENCE_TIMEOUT_SECONDS must contain "
    "only ASCII digits and resolve to 1–1800 seconds."
)
```

Replace `_health_check() -> bool` with `_read_health() -> dict | None`. It accepts only HTTP 200 JSON objects. Add one local helper that maps:

```python
{"status": "ok"}
```

to the current running result, and maps only:

```python
{
    "status": "disabled",
    "error": {
        "code": "chirp_invalid_inference_timeout",
        "message": INVALID_TIMEOUT_MESSAGE,
    },
}
```

to:

```python
{
    "running": False,
    "host": host,
    "port": port,
    "error": INVALID_TIMEOUT_MESSAGE,
    "error_code": "chirp_invalid_inference_timeout",
}
```

Use this helper at every existing fast path and startup poll. Any other payload continues normal polling; do not add more terminal states.

- [ ] **Step 5: Reject terminal misconfiguration before generation or mutation**

In the `chirp_create` case, keep required-argument checks first, then call `ensure_chirp_running`. For the exact terminal code return:

```python
{
    "success": False,
    "data": {
        "error": "chirp_invalid_inference_timeout",
        "details": chirp_status["error"],
    },
}
```

Do not construct `httpx.AsyncClient`, normalize pins, call `/chirp/create`, or call a Grasshopper route after that result.

- [ ] **Step 6: Read the actual `/gh/script` response and skip only unsafe verification**

After successful injection:

```python
script_data = script_result.get("data")
if not isinstance(script_data, dict):
    script_data = {}
verification_deferred = script_data.get("verification_deferred") is True
solve_scheduled = script_data.get("solve_scheduled")

data = {
    "component_guid": str(component_guid),
    "pins_in": chirp_pin_defs_in,
    "pins_out": chirp_pin_defs_out,
    "position": {"x": cx, "y": cy},
    "signature": signature,
    "category": chirp_result.get("category", category),
    "name": chirp_result.get("name", chirp_name),
    "verification_deferred": verification_deferred,
    "solve_scheduled": solve_scheduled,
}
```

For `verification_deferred and not deterministic_only`, return this data immediately. Otherwise retain the focused delay and `/gh/errors`. If target messages are observed, add:

```python
data["component_errors"] = component_errors
data["warning"] = "Component placed but has component errors"
```

Do not alter the separate `gh_create_script` `compilation_errors` contract.

- [ ] **Step 7: Run the Rook admission/deferred GREEN gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chirp_manager.py tests/test_server_contract_hardening.py -q
git diff --check
```

Expected: all new and existing focused contracts pass.

- [ ] **Step 8: Commit the Rook runtime boundary**

```powershell
Set-Location $rookRoot
git add mcp_server/src/rook/chirp_manager.py mcp_server/src/rook/server.py mcp_server/tests/test_chirp_manager.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix: admit Chirp through bounded timeout health"
```

**Checkpoint:** review before installer or harness work. No Rook call should surround actual inference, and deterministic-only verification must remain intact.

---

### Task 4: Correct shipped Chirp vocabulary, guidance, and installer environment behavior

**Files:**
- Create: `mcp_server/tests/test_chirp_timeout_contract.py`
- Modify: `.agents/skills/chirp/SKILL.md`
- Modify: `.claude/skills/chirp/SKILL.md`
- Modify: `installer/agent-assets/codex-skills/chirp/SKILL.md`
- Modify: `.agents/skills/chirp-cascade/SKILL.md`
- Modify: `.claude/skills/chirp-cascade/SKILL.md`
- Modify: `installer/agent-assets/codex-skills/chirp-cascade/SKILL.md`
- Modify: `installer/RookSetup.iss`
- Modify: `installer/post_install.py`
- Modify: `mcp_server/src/rook/local_testing_proof.py` (vocabulary only in this task)
- Modify: `mcp_server/tests/test_local_testing_proof.py` (vocabulary fixtures only in this task)
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Test: `scripts/tests/python-runtime-packaging.tests.ps1` (run unchanged)
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

**Interfaces:**
- Consumes: exact Chirp error codes and accepted Chirp commit.
- Produces: byte-identical skill mirrors, exact `.env` preservation, and fail-closed release guards.

- [ ] **Step 1: Write the focused contract guard first**

Create `test_chirp_timeout_contract.py` to:

- extract only the `case "chirp_create":` block through the next `case "gh_errors":` and assert `compilation_errors` is absent while `component_errors` is present;
- assert `local_testing_proof._chirp_validation_failure` reads `component_errors`;
- assert the unrelated `_execute_gh_create_script` block still contains `compilation_errors`;
- compare the recursive relative-file inventory and bytes for each three-way skill mirror;
- assert both skill bodies describe the three exact codes and do not instruct whole-operation retries after partial creation.

Use source slicing anchored by exact function/case names; do not scan historical docs or reach into a sibling Chirp checkout. Chirp's own Task 1 test pins its Python floor and timeout primitive.

- [ ] **Step 2: Add failing PowerShell guards for installer cases**

In `release-installer-guards.tests.ps1`, require a Chirp-specific function that checks `FileExists(Dir + '\.env')` before any `SaveStringToFile`, writes the key and `CHIRP_INFERENCE_TIMEOUT_SECONDS=300` only for a missing file, and is called only when the API key is nonempty. Require the existing generic MCP key behavior to remain unchanged.

In `deploy-local-testing-guards.tests.ps1`, extract `Sync-ChirpPayload` and assert it calls the existing `Sync-Directory` path while the shared exact exclude list still contains `.env`; assert the function contains no `.env` copy, delete, or validation operation.

Leave `python-runtime-packaging.tests.ps1` unchanged. Its existing `chirp_git_sha`, source archive, clean source, wheel build, temporary installation, import-origin, and `pip check` contracts are the packaging gate. Task 6 separately imports `chirp.server` and `chirp.timeout_policy` from the installed candidate; do not expand the wheelhouse builder for this correction.

- [ ] **Step 3: Run the new guards and confirm RED**

```powershell
Set-Location "$rookRoot\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_chirp_timeout_contract.py tests/test_local_testing_proof.py -q
Set-Location $rookRoot
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
```

Expected: focused failures for old vocabulary, missing guidance, and missing exact installer timeout behavior; the unchanged Python packaging guard remains green.

- [ ] **Step 4: Update authoritative skills, then copy bytes to mirrors**

In `.agents/skills/chirp/SKILL.md` and `.agents/skills/chirp-cascade/SKILL.md`, add concise handling:

- `chirp_invalid_inference_timeout`: configuration terminal; report it and do not mutate Grasshopper.
- `chirp_inference_timeout`: total inference budget exhausted; do not call it compilation failure.
- `chirp_transport_timeout`: generated client hit its outer safety ceiling; inspect sidecar/provider state.
- `component_errors`: messages actually observed from the Grasshopper component.
- after any partial component creation, inspect current state and retry only missing work.

Then copy each authoritative tree recursively to `.claude` and installer mirrors and prove byte equality. Do not add timeout recipes to Wasp references.

In `local_testing_proof.py` and its existing fixtures, change only Chirp-create response reads and messages from `compilation_errors` to `component_errors`. Do not change the separate `gh_create_script` compiler-diagnostic vocabulary. Task 5 adds the slow-provider behavior after this atomic consumer correction is green.

- [ ] **Step 5: Preserve existing Chirp `.env` and seed only a missing keyed file**

Keep the existing `WriteEnvFile` behavior for MCP. Add one Chirp-specific helper in `RookSetup.iss`:

```pascal
procedure WriteChirpEnvFileIfMissing(const Dir, ApiKey: String);
var
  EnvPath: String;
  Content: String;
begin
  EnvPath := Dir + '\.env';
  if FileExists(EnvPath) then
  begin
    Log('Preserving existing Chirp .env: ' + EnvPath);
    Exit;
  end;
  Content := '# Auto-generated by Rook installer' + #13#10 +
    'ANTHROPIC_API_KEY=' + ApiKey + #13#10 +
    'CHIRP_INFERENCE_TIMEOUT_SECONDS=300' + #13#10;
  ForceDirectories(Dir);
  SaveStringToFile(EnvPath, Content, False);
  Log('Wrote new Chirp .env to ' + Dir);
end;
```

Call it only inside the existing `ApiKey <> ''` branch when Chirp is selected. With no key, do not create `.env`.

In `post_install.py`, add the uncommented line below to newly created Chirp `.env.example` content:

```text
CHIRP_INFERENCE_TIMEOUT_SECONDS=300
```

Retain the existing `if not chirp_example.exists()` guard. Do not rewrite an existing example and do not alter the existing installed `.env`.

- [ ] **Step 6: Run the shipped-surface GREEN gate**

```powershell
Set-Location "$rookRoot\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_chirp_timeout_contract.py tests/test_local_testing_proof.py -q
Set-Location $rookRoot
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
git diff --check
```

Expected: exact source guards pass; all six skill mirrors are byte-identical.

- [ ] **Step 7: Commit the shipped-surface slice**

```powershell
git add .agents/skills/chirp .agents/skills/chirp-cascade .claude/skills/chirp .claude/skills/chirp-cascade installer/agent-assets/codex-skills/chirp installer/agent-assets/codex-skills/chirp-cascade installer/RookSetup.iss installer/post_install.py mcp_server/src/rook/local_testing_proof.py mcp_server/tests/test_chirp_timeout_contract.py mcp_server/tests/test_local_testing_proof.py scripts/tests/deploy-local-testing-guards.tests.ps1 scripts/tests/release-installer-guards.tests.ps1
git commit -m "fix: ship the Chirp timeout contract"
```

**Checkpoint:** verify only Chirp's contract was renamed. Existing compiler-known `gh_create_script` responses remain unchanged.

---

### Task 5: Add bounded installed slow-response acceptance

**Files:**
- Modify: `mcp_server/src/rook/local_testing_proof.py`
- Modify: `mcp_server/tests/test_local_testing_proof.py`

**Interfaces:**
- Consumes: installed Chirp source/wheel, `_call_tool_dispatch`, owned Rhino harness, `gh_inspect_output`, and the 1860-second smoke timeout already supported by `run_rhino_runtime_harness`.
- Produces: loopback-only delayed OpenAI-compatible provider and installed proof of a successful inference lasting more than 30 seconds.

- [ ] **Step 1: Write failing provider/watchdog/cleanup tests**

Add tests using a `0.02`-second injected delay, never 35 seconds in the unit suite. Prove:

- server binds only `127.0.0.1` on port `0` and exposes the assigned positive port;
- it records one expected `/v1/chat/completions` request;
- its assistant content is exactly `[[ ## result ## ]]\nslow-ok\n\n[[ ## completed ## ]]`;
- context cleanup stops the server thread within five seconds, including body failure;
- body and cleanup failures are both retained when both occur;
- a simulated 1860-second watchdog failure still enters provider, sidecar, and owned-host `finally` cleanup;
- `owned_release_readiness_gate` passes `smoke_timeout_seconds=1860`;
- the slow smoke sets `CHIRP_MODEL` and `CHIRP_PROVIDERS` only inside a restoring environment boundary;
- successful acceptance observes `slow-ok`, elapsed time above the injected delay, no timeout code, no `component_errors`, and owned-state cleanup;
- `_chirp_validation_failure` uses only `component_errors`.

- [ ] **Step 2: Run the harness tests and confirm RED**

```powershell
Set-Location "$rookRoot\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_local_testing_proof.py -q
```

Expected: new provider and watchdog assertions fail.

- [ ] **Step 3: Implement one loopback provider context**

Use one single-request `HTTPServer(("127.0.0.1", 0), Handler)` and one owned `threading.Event`. The handler must:

- accept only `POST /v1/chat/completions`;
- record request JSON under the current harness artifact directory;
- wait for the injected delay with `stop_event.wait(delay)` rather than `time.sleep(delay)`;
- exit without attempting a success response when cleanup sets the event;
- otherwise return HTTP 200 with one OpenAI-compatible `chat.completion` object, one assistant choice whose content is exactly `[[ ## result ## ]]\nslow-ok\n\n[[ ## completed ## ]]`, and integer prompt/completion/total usage fields;
- suppress default HTTP logging.

Only one provider request is expected, so concurrency is prohibited. The context manager's `finally` first sets `stop_event`, then calls `shutdown()`, `server_close()`, and `thread.join(timeout=5)` on the sole server thread. Assert that thread is no longer alive. Preserve body and cleanup failures separately, including both when both occur. Do not start another process or use the internet.

- [ ] **Step 4: Extend the installed smoke with one real delayed inference**

Keep the existing deterministic/progressive owned checks. Inside the same owned cleanup boundary, add one distinct non-deterministic Chirp check:

1. Start the loopback provider with production delay `35.0` seconds.
2. Set and later restore:

```python
CHIRP_MODEL = "openai/rook-timeout-acceptance"
CHIRP_PROVIDERS = json.dumps({
    "openai/rook-timeout-acceptance": {
        "api_base": f"http://127.0.0.1:{provider_port}/v1",
        "api_key_env": "CHIRP_TIMEOUT_ACCEPTANCE_API_KEY",
    }
})
CHIRP_TIMEOUT_ACCEPTANCE_API_KEY = "loopback-only"
CHIRP_INFERENCE_TIMEOUT_SECONDS = "300"
```

3. Create one non-deterministic classifier with optional `Input:string`, `Result:string`, and signature `input -> result`.
4. Require `chirp_create.data.verification_deferred is True`, `solve_scheduled is True`, and no `component_errors`.
5. Poll `gh_inspect_output` with `{"guid": component_guid, "param": "Result"}` at the existing 250-millisecond harness interval until it reports `slow-ok`; rely on the outer 1860-second harness watchdog rather than adding another deadline.
6. After output appears, call `gh_errors` once and require no messages for the owned component.
7. Verify provider receipt, elapsed duration greater than 30 seconds, and absence of all three failure vocabularies.
8. Restore only owned Grasshopper state through the existing bounded cleanup path.

Pass `smoke_timeout_seconds=1860` to `run_rhino_runtime_harness`. That timeout begins only after owned Rhino readiness because the harness launches the smoke command after readiness succeeds. Existing bounded Rhino cleanup remains in its `finally` path.

- [ ] **Step 5: Run the harness GREEN gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_local_testing_proof.py tests/test_chirp_timeout_contract.py -q
git diff --check
```

Expected: tests use short injected delays, verify bounded cleanup, and pass without launching Rhino.

- [ ] **Step 6: Commit the installed-acceptance slice**

```powershell
Set-Location $rookRoot
git add mcp_server/src/rook/local_testing_proof.py mcp_server/tests/test_local_testing_proof.py
git commit -m "test: prove slow installed Chirp inference"
```

**Checkpoint:** no general harness or runtime-harness file changes are permitted. Stop if the existing `smoke_timeout_seconds` seam proves insufficient.

---

### Task 6: Integrated review, merge order, payload installation, and live acceptance

**Files:**
- No production edits expected
- Evidence output: ignored Python payload and live-harness directories plus PR descriptions
- Later public promotion: one release-note mention of `component_errors` and timeout behavior

**Interfaces:**
- Consumes: accepted Chirp merge SHA, reviewed Rook head, existing release builder/deployer/installer.
- Produces: accepted private Rook merge SHA, provenance-bound installed Python payload, and green installed slow-response manifest.

- [ ] **Step 1: Run the integrated focused source gate**

```powershell
Set-Location $chirpWorktree
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip check

Set-Location "$rookRoot\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_chirp_manager.py `
    tests/test_server_contract_hardening.py `
    tests/test_local_testing_proof.py `
    tests/test_chirp_timeout_contract.py -q
.\.venv\Scripts\python.exe -m pip check

Set-Location $rookRoot
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
git diff --check
```

Expected: all focused tests and guards pass. Do not run a repository-wide suite.

- [ ] **Step 2: Enforce fail-closed changed-path scopes**

```powershell
$chirpAllowed = @(
    'README.md',
    'src/chirp/__main__.py',
    'src/chirp/adapter.py',
    'src/chirp/rook_tool.py',
    'src/chirp/server.py',
    'src/chirp/timeout_policy.py',
    'templates/chirp_script_template.cs',
    'templates/example_intent_to_params.cs',
    'tests/test_adapter.py',
    'tests/test_openrouter_passthrough.py',
    'tests/test_rook_tool.py',
    'tests/test_server.py',
    'tests/test_timeout_policy.py'
)
$rookAllowed = @(
    '.agents/skills/chirp-cascade/SKILL.md',
    '.agents/skills/chirp/SKILL.md',
    '.claude/skills/chirp-cascade/SKILL.md',
    '.claude/skills/chirp/SKILL.md',
    'installer/agent-assets/codex-skills/chirp-cascade/SKILL.md',
    'installer/agent-assets/codex-skills/chirp/SKILL.md',
    'installer/post_install.py',
    'installer/RookSetup.iss',
    'mcp_server/src/rook/chirp_manager.py',
    'mcp_server/src/rook/local_testing_proof.py',
    'mcp_server/src/rook/server.py',
    'mcp_server/tests/test_chirp_manager.py',
    'mcp_server/tests/test_chirp_timeout_contract.py',
    'mcp_server/tests/test_local_testing_proof.py',
    'mcp_server/tests/test_server_contract_hardening.py',
    'scripts/tests/deploy-local-testing-guards.tests.ps1',
    'scripts/tests/release-installer-guards.tests.ps1'
)
$chirpPaths = @(git -C $chirpWorktree diff --name-only b0acae1c91243ec7bc1de58138ac17ae58fdcb05..HEAD)
$rookPaths = @(git -C $rookRoot diff --name-only plan/chirp-inference-timeout-2026-08-05-approved..HEAD)
$unexpectedChirp = @($chirpPaths | Where-Object { $_ -notin $chirpAllowed })
$unexpectedRook = @($rookPaths | Where-Object { $_ -notin $rookAllowed })
if ($unexpectedChirp.Count -gt 0) { throw "Unexpected Chirp paths: $($unexpectedChirp -join ', ')" }
if ($unexpectedRook.Count -gt 0) { throw "Unexpected Rook paths: $($unexpectedRook -join ', ')" }
git -C $chirpWorktree diff --check b0acae1c91243ec7bc1de58138ac17ae58fdcb05..HEAD
git -C $rookRoot diff --check plan/chirp-inference-timeout-2026-08-05-approved..HEAD
```

Expected: no dependency metadata, lockfile, native, managed, RookBIM, or unrelated harness path.

- [ ] **Step 3: Re-verify the already accepted Chirp merge**

Task 2 produced `$acceptedChirpSha`; do not merge Chirp a second time. Fetch `origin/master`, require it still points to `$acceptedChirpSha`, require that commit's first parent to be the reviewed current `master` base and its second parent to be the reviewed timeout head, and require both parent repositories to be clean. Stop if Chirp advanced after review; do not silently package a later commit.

- [ ] **Step 4: Review and merge the Rook PR without squashing**

Open the Rook PR against current `main`, record the exact reviewed head, verify zero unexpected overlap and a clean synthetic merge, then use a regular merge commit. Verify first parent is checked current `main`, second parent is the reviewed Rook head, and `origin/main` points to the resulting `$acceptedRookSha`.

The PR description must state that repository-wide tests were intentionally excluded and cite the exact focused counts.

- [ ] **Step 5: Create clean sibling release checkouts at the two accepted SHAs**

Use one unique temporary parent so Rook's existing sibling-Chirp discovery and `RookSetup.iss` both resolve the exact accepted checkout without a junction:

```powershell
$releaseRoot = Join-Path $env:TEMP ("rook-chirp-timeout-release-" + [guid]::NewGuid().ToString('N'))
$releaseRook = Join-Path $releaseRoot 'Rook'
$releaseChirp = Join-Path $releaseRoot 'Chirp'
New-Item -ItemType Directory -Path $releaseRoot | Out-Null
git -C 'C:\Users\aryan\source\repos\Rook' worktree add --detach $releaseRook $acceptedRookSha
git -C 'C:\Users\aryan\source\repos\Chirp' worktree add --detach $releaseChirp $acceptedChirpSha
if ((git -C $releaseRook rev-parse HEAD).Trim() -ne $acceptedRookSha) { throw 'Detached Rook SHA mismatch' }
if ((git -C $releaseChirp rev-parse HEAD).Trim() -ne $acceptedChirpSha) { throw 'Detached Chirp SHA mismatch' }
if (git -C $releaseRook status --porcelain) { throw 'Detached Rook checkout is dirty' }
if (git -C $releaseChirp status --porcelain) { throw 'Detached Chirp checkout is dirty' }
if ((Resolve-Path (Join-Path $releaseRook '..\Chirp')).Path -ne (Resolve-Path $releaseChirp).Path) {
    throw 'Accepted Chirp checkout is not the Rook release checkout sibling'
}
```

Preserve these two owned worktrees through acceptance. Do not remove them while evidence or artifacts still reference their paths.

- [ ] **Step 6: Build and validate the sealed Python payload**

Derive the current Rook version from `mcp_server/pyproject.toml`; do not bump it here. Stage the pinned Python runtime, build the wheelhouse from the accepted Chirp checkout, and validate it:

```powershell
$version = ((Select-String -LiteralPath "$releaseRook\mcp_server\pyproject.toml" -Pattern '^version = "([0-9]+\.[0-9]+\.[0-9]+)"$').Matches[0].Groups[1].Value)
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\python-runtime\stage-rook-python-runtime.ps1" -RepoRoot $releaseRook
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\python-runtime\build-rook-python-wheelhouse.ps1" -Version $version -RepoRoot $releaseRook -ChirpRoot $releaseChirp
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\validate-python-wheelhouse.ps1" -Version $version -RepoRoot $releaseRook
```

Read `python-runtime-manifest.json` and require exact `rook_git_sha == $acceptedRookSha`, `chirp_git_sha == $acceptedChirpSha`, CPython `3.11.9`, `rook-mcp` current version, `mcp==1.28.1`, Chirp `0.1.0`, both imports, both `pip check`s, and no MCP 2.x wheel.

- [ ] **Step 7: Install the candidate through canonical payload-only deployment without changing `.env`**

Before deployment, record whether `%LOCALAPPDATA%\Rook\app\chirp\.env` exists and hash it when present. With Rhino, Revit, Grasshopper, Rook MCP, and Chirp processes safely closed, run the canonical release payload-only deployment. This intentionally leaves installed native, managed, RookBIM, and FFmpeg artifacts untouched while installing the accepted Rook/Chirp Python payload:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\deploy-local-testing.ps1" -Configuration Release -PayloadOnly
```

Require installed `chirp.timeout_policy` and `chirp.server` to import from `%LOCALAPPDATA%\Rook\app\chirp\.venv`, installed Chirp source bytes to match the detached accepted checkout, both `%LOCALAPPDATA%\Rook\venv` and `%LOCALAPPDATA%\Rook\app\chirp\.venv` `pip check`s to pass, and the prior `.env` presence/hash to remain identical.

- [ ] **Step 8: Re-run the installer source contract against the accepted Rook merge**

Run the source-only installer guard from the detached accepted Rook checkout:

```powershell
Push-Location $releaseRook
try {
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
} finally {
    Pop-Location
}
```

Require the exact preserve/create/no-create `.env` branches and `.env.example` contract to pass. A compiled installer, native/managed/RookBIM/FFmpeg rebuild, and installer repair cycle belong to the later release build from the accepted merge; do not pull them into this correction. The installed live gate remains valid because Step 7 used the supported local deployment and exact sealed payload.

- [ ] **Step 9: Run the installed >30-second acceptance once**

With no user Rhino/Grasshopper session running, invoke the installed private Python:

```powershell
$liveArtifactRoot = Join-Path $releaseRook '.scratch\chirp-inference-timeout-live'
& "$env:LOCALAPPDATA\Rook\venv\Scripts\python.exe" -m rook.local_testing_proof owned-release-readiness `
    --out (Join-Path $liveArtifactRoot 'result.json') `
    --artifact-root $liveArtifactRoot `
    --rhino-exe "C:\Program Files\Rhino 8\System\Rhino.exe" `
    --readiness-timeout 90 `
    --cleanup-timeout 15
```

Read the JSON result and harness manifest mechanically. Require:

- installed-source provenance for both accepted SHAs;
- provider bound to loopback on an owned random port and exactly one expected request;
- inference elapsed time greater than 30 seconds;
- `slow-ok` in the created component's `Result` output;
- no `chirp_inference_timeout`, `chirp_transport_timeout`, or `component_errors`;
- watchdog recorded as `1860` and started after Rhino readiness;
- owned Grasshopper component removed;
- provider, Chirp sidecar, Rhino, and Rook MCP cleanup bounded and successful.

Stop on any failure. Do not increase a timeout, modify global configuration, or substitute source-worktree MCP execution.

- [ ] **Step 10: Hand off public promotion separately**

After private acceptance, promote from detached `$acceptedRookSha` and `$acceptedChirpSha`. The one-time release note states:

- newly generated Chirps use a bounded 300-second total inference budget configurable up to 1800 seconds;
- timeout failures are `chirp_inference_timeout` or `chirp_transport_timeout`;
- the corrected Chirp response field is `component_errors`.

The public tag targets the reviewed public promotion commit and records both private source SHAs and artifact hashes. Public work does not alter or block the already accepted private commits.

---

## Self-Review Checklist

- [ ] Every specification section maps to a task: current chain, policy, configuration, admission, taxonomy, deployment, and installed acceptance.
- [ ] No placeholder, compatibility alias, retry framework, migration machinery, or unsupported timeout remains.
- [ ] `ChirpAdapter.acall`, `InferenceTimeoutPolicy`, `component_errors`, and all four timeout constants use the same names in every task.
- [ ] Rook's separate compiler-known `gh_create_script.compilation_errors` contract is preserved.
- [ ] The Chirp PR merges first; packaging consumes its immutable merge SHA.
- [ ] The Rook PR uses deterministic focused gates; installed acceptance runs from the resulting private merge and sealed Chirp payload.
- [ ] Public promotion is a later provenance handoff, not private acceptance ancestry.
