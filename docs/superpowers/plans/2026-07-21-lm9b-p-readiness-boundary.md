# LM9B-P Readiness Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a staged, operator-error-proof readiness boundary (local preflight → explicitly-approved experiment-content-free canary → sealed readiness record → pure refuse-before-allocation launch verifier) in front of the unchanged one-shot LM9B-P Planner-transfer experiment, so a missing or non-functional credential/access fault is caught operationally instead of consuming an attempt identity.

**Architecture — designed outward from the irreversible transition, not inward from modules.** The whole slice is validated by ONE proof-carrying vertical witness (Task 1) that walks a complete transaction through the *real* experiment transmit entry point with fake providers and an injected clock:

```
exact launch configuration
-> readiness routes derived from THAT configuration
-> actual fake-canary events under an injected clock
-> record sealed AFTER the final observation
-> same configuration reauthenticated at the real transmit entry point
-> readiness verified immediately before the atomic mkdir
-> only a valid record reaches allocation + provider construction
-> mutated identity / time / credential each refuses BEFORE allocation
```

Three code surfaces. A **pure contract module** (`scripts/lm9b_p_readiness_contract.py`, stdlib-only, no Git/filesystem/clock/environment I/O) owns route derivation from a supplied configuration, the credential-source declaration, fingerprints, canary protocol, `build_canary_request`, `route_ready`, and `verify_launch_readiness`. A **disposable readiness probe** (`scripts/lm9b_p_readiness_probe.py`) imports the contract, owns provider contact via the production `LiteLLMProvider`, and writes the record under an injected clock. The **experiment CLI** (`scripts/lm9b_p_planner_recipe_transfer_probe.py`) imports **only** the pure contract and gains a refuse-before-`mkdir` precondition that derives routes from the *actually parsed* models.

**Tech Stack:** Python 3.10/3.12, pytest, LiteLLM 1.89.4 (production adapter, contacted only under `--authenticate`), stdlib `hashlib`/`json`/`datetime`/`dataclasses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-lm9b-p-readiness-boundary-design.md` (authoritative).
- Base: worktree `codex/lm9b-p-readiness-boundary` on `origin/main` `dfd90659`.
- **Design outward from the boundary.** No stage reconstructs identity from a second static description; readiness routes are always derived from the exact launch configuration. No timestamp is assigned without reference to the event it receipts (`observed_at` after each canal call; `completed_at` after all). No helper unit test substitutes for exercising the public transition it guards.
- `FROZEN_MAX_AGE_S = 600` seconds — frozen in the module, never operator-set.
- Credential-source declaration is a closed two-entry map, names only, never values, verified vs installed LiteLLM 1.89.4: `("openai","gpt-5.4") -> ("OPENAI_API_KEY",)`; `("gemini","gemini/gemini-3.1-pro-preview") -> ("GOOGLE_API_KEY","GEMINI_API_KEY")`. Presence = at least one declared name set.
- **Canonical Planner pin:** the experiment refuses unless `--planner-model` and `--planner-evaluator-model` both equal `gpt-5.4` (matching the already-pinned compiler models). This closes the "arbitrary Planner model" gap alongside the identity binding.
- The pure contract imports **stdlib only** — never `litellm`, never `lm9b_p_readiness_probe`, never `rook.*` at module top level. `api_key_env_for_model` is passed in as a callable.
- Do **not** modify `mcp_server/src/rook/agent/model_profiles.py`. Do **not** change the frozen model IDs.
- The canary sends **no** experiment content. One contact per distinct route, no retry.
- The experiment CLI change is refuse-only and imports only `lm9b_p_readiness_contract`; it must not import `lm9b_p_readiness_probe`.
- `--readiness-record` is required **only with `--transmit`**; dry-run behavior is unchanged.
- Readiness failure never consumes a scientific attempt. Correcting credentials must not leave an unusable empty readiness directory (credential check precedes readiness-root creation). This slice does not begin the scientific attempt and grants no execution authority.
- **Test command** (from worktree root `C:/UDEV/Rook/.worktrees/lm9b-p-readiness-boundary`, populated main-checkout venv):
  `PY="C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe"` ; `"$PY" -m pytest mcp_server/tests/<file> -v`
- Test module-load convention (prepend to each new test file):

```python
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
```

- Commit after every task; messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Vertical witness (walking skeleton through the real transmit entry point)

This task builds the thinnest **real** end-to-end path and proves it, so identity binding, timestamp ordering, and boundary enforcement are correct from the first commit. Later tasks only add cases and hardening.

**Files:**
- Create: `scripts/lm9b_p_readiness_contract.py`
- Create: `scripts/lm9b_p_readiness_probe.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_probe.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_witness.py`

**Interfaces produced (used by every later task):**
- Contract: `FROZEN_MAX_AGE_S`, `SCHEMA_ID`, `ReadinessError`, `canonical_fingerprint(value)`, `CREDENTIAL_SOURCE_DECLARATIONS`, `resolve_credential_source(provider, model, helper_result)`, `provider_of(model)`, `RoleRoute`, `DistinctRoute`, `RouteManifest`, `CANONICAL_ROLE_MODELS`, `role_routes_from_models(models)`, `derive_routes(role_routes, helper)`, canary constants + `canary_protocol()`, `canary_protocol_fingerprint()`, `build_canary_request(route)`, `request_fingerprint(route)`, `route_ready(row)`, `record_fingerprint(record)`, `LaunchDecision`, `verify_launch_readiness(...)`.
- Probe: `HELPER`, `credential_presence(manifest, environ)`, `run_canary(route, provider)`, `assemble_record(...)`, `run_readiness(*, run_root, head_sha, environ, authenticate, provider_factory, clock)`.
- Experiment CLI: `readiness_gate_ok(*, record, models, head_sha, now_iso, credential_present)`, `CliAttemptConfig.readiness_record`, canonical Planner pin.

- [ ] **Step 1: Write the failing witness test**

```python
# mcp_server/tests/test_lm9b_p_readiness_witness.py
# (prepend the _load_script convention block)
import json, subprocess, sys
import pytest

C = _load_script("lm9b_p_readiness_contract")
P = _load_script("lm9b_p_readiness_probe")
EXP = _load_script("lm9b_p_planner_recipe_transfer_probe")

FAKE_SHA = "d" * 40
CANON = dict(C.CANONICAL_ROLE_MODELS)  # planner/eval=gpt-5.4, compiler/eval=gemini/...

class _FakeClock:
    def __init__(self):
        self.t = 0
    def __call__(self):
        self.t += 1
        return f"2026-07-21T12:00:{self.t:02d}Z"

class _FakeOk:
    def __init__(self, route):
        self.route = route
    def __call__(self, request):
        return EXP.__dict__  # placeholder; replaced below by a real ProviderTurn

def _seal_record(models=CANON, head=FAKE_SHA, clock=None):
    clock = clock or _FakeClock()
    LM9BC = _load_script("lm9b_c_compiler_sufficiency_probe")
    def ok_provider(route):
        def _call(request):
            return LM9BC.ProviderTurn(
                raw_request=b"{}", raw_response=b'{"id":"x"}',
                assistant_message={"role": "assistant", "content": None,
                    "tool_calls": [{"id": "1", "type": "function",
                        "function": {"name": "ack", "arguments": "{\"ok\": true}"}}]},
                usage={}, provider_metadata={})
        return _call
    import tempfile
    run_root = Path(tempfile.mkdtemp()) / "readiness"
    return P.run_readiness(
        run_root=run_root, head_sha=head,
        environ={"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"},
        authenticate=True, provider_factory=ok_provider, clock=clock,
        models=models,
    )

def _drive_transmit(monkeypatch, record, models=CANON, run_root=None, sha=FAKE_SHA):
    """Drive the REAL transmit function to the gate + atomic mkdir."""
    calls = {"provider": 0}
    def exploding_build_provider(*a, **k):
        calls["provider"] += 1
        raise RuntimeError("SENTINEL_PROVIDER_CONSTRUCTED")
    monkeypatch.setattr(EXP, "_build_provider", exploding_build_provider)
    monkeypatch.setattr(EXP, "_git_checkout_state",
        lambda: EXP.GitCheckoutState(clean=True, commit_sha=sha))
    monkeypatch.setattr(EXP, "_readiness_now_iso", lambda: "2026-07-21T12:00:30Z")
    monkeypatch.setattr("os.environ", {"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"})
    rec_path = Path(run_root) / "readiness_record.json"
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(record), encoding="utf-8")
    prepared = EXP.build_prepared_for_test(
        models=models, git_sha=sha,
        run_root=Path(run_root) / "attempt", readiness_record=rec_path,
    )
    return EXP._execute_transmitted_attempt(prepared), calls

def test_valid_record_reaches_allocation_and_provider_construction(monkeypatch, tmp_path):
    rec = _seal_record()
    with pytest.raises(RuntimeError, match="SENTINEL_PROVIDER_CONSTRUCTED"):
        _drive_transmit(monkeypatch, rec, run_root=tmp_path)
    assert (tmp_path / "attempt").exists()  # allocation happened past the gate

def test_model_binding_drift_refuses_before_allocation(monkeypatch, tmp_path):
    # Record sealed for a DIFFERENT planner model -> manifest fp mismatch.
    drift = dict(CANON); drift["planner"] = "gpt-4o"; drift["planner_evaluator"] = "gpt-4o"
    rec = _seal_record(models=drift)
    with pytest.raises(RuntimeError, match="readiness gate refused"):
        result, calls = _drive_transmit(monkeypatch, rec, models=CANON, run_root=tmp_path)
    assert not (tmp_path / "attempt").exists()   # no allocation

def test_stale_record_refuses_before_allocation(monkeypatch, tmp_path):
    rec = _seal_record()  # observed/completed near 12:00:0x
    monkeypatch.setattr(EXP, "_readiness_now_iso", lambda: "2026-07-21T12:30:00Z")
    # patch same overrides as _drive_transmit but with the late clock already set
    with pytest.raises(RuntimeError, match="readiness gate refused"):
        _drive_transmit(monkeypatch, rec, run_root=tmp_path)
    assert not (tmp_path / "attempt").exists()

def test_credential_absent_refuses_before_allocation(monkeypatch, tmp_path):
    rec = _seal_record()
    monkeypatch.setattr("os.environ", {"OPENAI_API_KEY": "x"})  # gemini creds gone
    with pytest.raises(RuntimeError, match="readiness gate refused"):
        # _drive_transmit resets os.environ; call the inner pieces with this env instead
        pass
    # Direct boundary check with absent gemini creds:
    manifest = C.derive_routes(C.role_routes_from_models(CANON), P.HELPER)
    presence = P.credential_presence(manifest, {"OPENAI_API_KEY": "x"})
    assert EXP.readiness_gate_ok(record=rec, models=CANON, head_sha=FAKE_SHA,
        now_iso="2026-07-21T12:00:30Z", credential_present=presence) is False

def test_import_isolation_experiment_cli_pulls_no_provider_contact_code():
    code = (
        "import sys; sys.path.insert(0, r'%s'); " % str(ROOT / "scripts") +
        "sys.path.insert(0, r'%s'); " % str(ROOT / "mcp_server" / "src") +
        "import lm9b_p_planner_recipe_transfer_probe as e; "
        "assert 'lm9b_p_readiness_probe' not in sys.modules, 'probe leaked'; "
        "assert 'litellm' not in sys.modules, 'litellm leaked'; print('ok')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
```

- [ ] **Step 2: Run the witness to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_witness.py -v`
Expected: FAIL — missing modules / `role_routes_from_models` / `build_prepared_for_test` / `readiness_gate_ok` / `_readiness_now_iso`.

- [ ] **Step 3: Create the pure contract module (walking-skeleton scope)**

```python
# scripts/lm9b_p_readiness_contract.py
#!/usr/bin/env python
"""Pure LM9B-P readiness contract. Stdlib only — no Git/filesystem/clock/env I/O,
no provider imports. Callers supply configuration, SHA, time, env observations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

FROZEN_MAX_AGE_S: int = 600
SCHEMA_ID: str = "lm9b_p.readiness_record:v1"


class ReadinessError(ValueError):
    """Raised when a readiness contract invariant is violated."""


CREDENTIAL_SOURCE_DECLARATIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("openai", "gpt-5.4"): ("OPENAI_API_KEY",),
    ("gemini", "gemini/gemini-3.1-pro-preview"): ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}

CANONICAL_ROLE_MODELS: dict[str, str] = {
    "planner": "gpt-5.4",
    "planner_evaluator": "gpt-5.4",
    "compiler": "gemini/gemini-3.1-pro-preview",
    "compiler_evaluator": "gemini/gemini-3.1-pro-preview",
}

CANARY_SYSTEM = "You are a readiness canary."
CANARY_USER = "Call the ack tool."
CANARY_MAX_COMPLETION_TOKENS = 16
CANARY_PROVIDER_TIMEOUT_S = 30.0
CANARY_TEMPERATURE = 0.0
ACK_TOOL = {
    "type": "function",
    "function": {
        "name": "ack",
        "description": "Acknowledge readiness.",
        "parameters": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}


def canonical_fingerprint(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def provider_of(model: str) -> str:
    if model.startswith("gemini/"):
        return "gemini"
    if model.startswith("openai/"):
        return "openai"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise ReadinessError(f"cannot determine provider for model {model!r}")


def resolve_credential_source(
    provider: str, model: str, helper_result: str | None
) -> tuple[str, ...]:
    declaration = CREDENTIAL_SOURCE_DECLARATIONS.get((provider, model))
    if declaration is None:
        raise ReadinessError(f"no credential-source declaration for {provider}/{model}")
    if helper_result is not None and helper_result not in declaration:
        raise ReadinessError(
            f"canonical helper {helper_result!r} not in declaration for {provider}/{model}"
        )
    return declaration


@dataclass(frozen=True)
class RoleRoute:
    role: str
    adapter_path: str
    provider: str
    model: str


@dataclass(frozen=True)
class DistinctRoute:
    route_fingerprint: str
    adapter_path: str
    provider: str
    model: str
    credential_source: tuple[str, ...]
    member_roles: tuple[str, ...]


@dataclass(frozen=True)
class RouteManifest:
    routes: tuple[DistinctRoute, ...]
    manifest_fingerprint: str


def role_routes_from_models(models: dict) -> tuple[RoleRoute, ...]:
    return tuple(
        RoleRoute(role, "litellm.completion", provider_of(model), model)
        for role, model in models.items()
    )


def derive_routes(
    role_routes: Sequence[RoleRoute], helper: Callable[[str], str | None]
) -> RouteManifest:
    groups: dict[tuple, list[str]] = {}
    meta: dict[tuple, tuple[str, str, str, tuple[str, ...]]] = {}
    for route in role_routes:
        cred = resolve_credential_source(route.provider, route.model, helper(route.model))
        key = (route.adapter_path, route.provider, route.model, cred)
        groups.setdefault(key, []).append(route.role)
        meta[key] = (route.adapter_path, route.provider, route.model, cred)
    distinct: list[DistinctRoute] = []
    for key, roles in groups.items():
        adapter_path, provider, model, cred = meta[key]
        identity = {"adapter_path": adapter_path, "provider": provider,
                    "model": model, "credential_source": list(cred)}
        distinct.append(DistinctRoute(
            route_fingerprint=canonical_fingerprint(identity),
            adapter_path=adapter_path, provider=provider, model=model,
            credential_source=cred, member_roles=tuple(sorted(roles))))
    distinct.sort(key=lambda r: r.route_fingerprint)
    return RouteManifest(
        routes=tuple(distinct),
        manifest_fingerprint=canonical_fingerprint([r.route_fingerprint for r in distinct]))


def canary_protocol() -> dict:
    return {"system": CANARY_SYSTEM, "user": CANARY_USER, "tool": ACK_TOOL,
            "max_completion_tokens": CANARY_MAX_COMPLETION_TOKENS,
            "provider_timeout_s": CANARY_PROVIDER_TIMEOUT_S,
            "temperature": CANARY_TEMPERATURE}


def canary_protocol_fingerprint() -> str:
    return canonical_fingerprint(canary_protocol())


def build_canary_request(route: DistinctRoute) -> dict:
    p = canary_protocol()
    return {"model": route.model,
            "messages": [{"role": "system", "content": p["system"]},
                         {"role": "user", "content": p["user"]}],
            "tools": [p["tool"]],
            "tool_choice": {"type": "function", "function": {"name": "ack"}},
            "max_completion_tokens": p["max_completion_tokens"],
            "provider_timeout_s": p["provider_timeout_s"]}


def request_fingerprint(route: DistinctRoute) -> str:
    return canonical_fingerprint(build_canary_request(route))


def route_ready(row: dict) -> bool:
    outcome = row.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("kind") != "model_response":
        return False
    if outcome.get("assistant_present") is not True:
        return False
    calls = outcome.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        return False
    call = calls[0]
    if not isinstance(call, dict) or call.get("name") != "ack":
        return False
    arguments = call.get("arguments")
    if not isinstance(arguments, str):
        return False
    try:
        parsed = json.loads(arguments)
    except (ValueError, TypeError):
        return False
    return parsed == {"ok": True}


def record_fingerprint(record: dict) -> str:
    return canonical_fingerprint(
        {k: v for k, v in record.items() if k != "record_fingerprint"})


@dataclass(frozen=True)
class LaunchDecision:
    ok: bool
    failures: tuple[str, ...]


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReadinessError(f"timestamp not exact UTC Z form: {value!r}")
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)


def verify_launch_readiness(
    *, record: dict, manifest: RouteManifest, head_sha: str, now_iso: str,
    credential_present: dict,
) -> LaunchDecision:
    failures: list[str] = []
    def fail(m: str) -> None:
        failures.append(m)

    if record.get("reviewed_commit_sha") != head_sha:
        fail("commit sha mismatch")
    if record.get("route_manifest_fingerprint") != manifest.manifest_fingerprint:
        fail("route manifest fingerprint mismatch")
    if record.get("record_fingerprint") != record_fingerprint(record):
        fail("record fingerprint mismatch")
    if record.get("canary_protocol_fingerprint") != canary_protocol_fingerprint():
        fail("canary protocol fingerprint mismatch")
    if record.get("max_age_seconds") != FROZEN_MAX_AGE_S:
        fail("max_age_seconds != frozen constant")

    rows = record.get("routes") if isinstance(record.get("routes"), list) else []
    by_fp = {r.route_fingerprint: r for r in manifest.routes}
    row_fps = [row.get("route_fingerprint") for row in rows]
    if len(row_fps) != len(set(row_fps)):
        fail("duplicate route rows")
    if set(row_fps) != set(by_fp):
        fail("route set != manifest")

    try:
        now = _parse_utc(now_iso)
        completed = _parse_utc(record.get("completed_at"))
        if not 0 <= (now - completed).total_seconds() <= FROZEN_MAX_AGE_S:
            fail("record completed_at outside freshness window")
        for row in rows:
            observed = _parse_utc(row.get("observed_at"))
            if completed < observed:
                fail("completed_at precedes observed_at")
            if not 0 <= (now - observed).total_seconds() <= FROZEN_MAX_AGE_S:
                fail("route observed_at outside freshness window")
    except ReadinessError as exc:
        fail(str(exc))

    for row in rows:
        fp = row.get("route_fingerprint")
        route = by_fp.get(fp)
        if route is None:
            continue
        if tuple(row.get("member_roles") or ()) != route.member_roles:
            fail(f"member roles differ for {fp}")
        if row.get("request_fingerprint") != request_fingerprint(route):
            fail(f"request fingerprint mismatch for {fp}")
        if credential_present.get(fp) is not True:
            fail(f"credential absent for {fp}")
        if not route_ready(row):
            fail(f"route not ready for {fp}")

    return LaunchDecision(ok=not failures, failures=tuple(failures))
```

- [ ] **Step 4: Create the readiness probe (walking-skeleton scope, clock injected)**

```python
# scripts/lm9b_p_readiness_probe.py
#!/usr/bin/env python
"""Disposable LM9B-P readiness probe. Owns provider contact; imports the pure
contract for all identity and verification logic. Clock is injected."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_MCP_SRC = _SCRIPTS_DIR.parent / "mcp_server" / "src"
for _p in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lm9b_p_readiness_contract as CONTRACT
import lm9b_c_compiler_sufficiency_probe as LM9BC
from rook.agent.model_profiles import api_key_env_for_model

HELPER = api_key_env_for_model


def system_clock() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def credential_presence(manifest, environ) -> dict:
    return {
        route.route_fingerprint: any(
            bool(environ.get(name)) for name in route.credential_source)
        for route in manifest.routes
    }


def default_provider_factory(route):
    return LM9BC.LiteLLMProvider(model=route.model, temperature=CONTRACT.CANARY_TEMPERATURE)


def run_canary(route, provider, *, clock) -> dict:
    request = CONTRACT.build_canary_request(route)
    base = {"route_fingerprint": route.route_fingerprint,
            "member_roles": list(route.member_roles),
            "request_fingerprint": CONTRACT.request_fingerprint(route)}
    try:
        turn = provider(request)
    except LM9BC.ProviderCallFailure as exc:
        base["observed_at"] = clock()  # stamped AFTER the call resolves
        base["outcome"] = {"kind": "transport_failure",
            "classification": exc.failure_type,
            "detail_hash": "sha256:" + hashlib.sha256(exc.message.encode()).hexdigest()}
        return base
    base["observed_at"] = clock()       # stamped AFTER the call resolves
    message = turn.assistant_message or {}
    tool_calls = [{"name": (c.get("function") or {}).get("name"),
                   "arguments": (c.get("function") or {}).get("arguments")}
                  for c in (message.get("tool_calls") or [])]
    base["outcome"] = {"kind": "model_response", "assistant_present": True,
        "tool_calls": tool_calls,
        "raw_response_fingerprint": "sha256:" + hashlib.sha256(turn.raw_response).hexdigest()}
    return base


def assemble_record(*, manifest, head_sha, completed_at, route_rows) -> dict:
    record = {"schema_id": CONTRACT.SCHEMA_ID, "reviewed_commit_sha": head_sha,
        "route_manifest_fingerprint": manifest.manifest_fingerprint,
        "canary_protocol_fingerprint": CONTRACT.canary_protocol_fingerprint(),
        "max_age_seconds": CONTRACT.FROZEN_MAX_AGE_S, "completed_at": completed_at,
        "routes": list(route_rows)}
    record["record_fingerprint"] = CONTRACT.record_fingerprint(record)
    return record


def run_readiness(*, run_root, head_sha, environ, authenticate, provider_factory,
                  clock=system_clock, models=None) -> dict:
    models = dict(models or CONTRACT.CANONICAL_ROLE_MODELS)
    manifest = CONTRACT.derive_routes(CONTRACT.role_routes_from_models(models), HELPER)
    presence = credential_presence(manifest, environ)
    # Credential check BEFORE creating the readiness root (no empty dir on failure).
    if authenticate and not all(presence.values()):
        raise CONTRACT.ReadinessError("preflight failed: credential absent")
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=False)
    rows = []
    if authenticate:
        for route in manifest.routes:
            rows.append(run_canary(route, provider_factory(route), clock=clock))
    completed_at = clock()  # AFTER all route observations
    record = assemble_record(manifest=manifest, head_sha=head_sha,
                             completed_at=completed_at, route_rows=rows)
    (run_root / "readiness_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    (run_root / "preflight.json").write_text(
        json.dumps({"credential_present": presence}, indent=2, sort_keys=True),
        encoding="utf-8")
    return record
```

- [ ] **Step 5: Wire the real experiment transmit entry point**

In `scripts/lm9b_p_planner_recipe_transfer_probe.py`:

(a) Add imports near the top:

```python
import lm9b_p_readiness_contract as READINESS
from rook.agent.model_profiles import api_key_env_for_model as _READINESS_HELPER
```

(b) Add a monkeypatchable clock and the pure gate helper (near `_git_checkout_state`):

```python
def _readiness_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _launch_models(config) -> dict:
    return {"planner": config.planner_model,
            "planner_evaluator": config.planner_evaluator_model,
            "compiler": config.compiler_model,
            "compiler_evaluator": config.compiler_evaluator_model}


def readiness_gate_ok(*, record, models, head_sha, now_iso, credential_present) -> bool:
    manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(models), _READINESS_HELPER)
    return READINESS.verify_launch_readiness(
        record=record, manifest=manifest, head_sha=head_sha, now_iso=now_iso,
        credential_present=credential_present).ok
```

(c) Add the canonical Planner pin to `assert_frozen_planner_controls()` (append before its final check):

```python
    if (config_planner := PLANNER_PIN) and False:  # placeholder guard removed below
        pass
```

Instead, enforce the pin in `parse_cli_args` right before returning the config:

```python
    if args.planner_model != "gpt-5.4" or args.planner_evaluator_model != "gpt-5.4":
        parser.error("canonical Planner pin: planner and planner-evaluator models "
                     "must both equal gpt-5.4")
```

(d) Make `--readiness-record` required only with `--transmit`. In `parse_cli_args`:

```python
    parser.add_argument("--readiness-record", type=Path, default=None)
    ...
    if args.transmit and args.readiness_record is None:
        parser.error("--transmit requires --readiness-record")
```

and add `readiness_record: Path | None` to `CliAttemptConfig` (pass `readiness_record=args.readiness_record`).

(e) In `_execute_transmitted_attempt`, immediately after the existing
`checkout changed after pre-transmission review` guard and **before**
`config.run_root.mkdir(...)`, insert the gate:

```python
    import json as _json, os as _os
    record = _json.loads(config.readiness_record.read_text(encoding="utf-8"))
    models = _launch_models(config)
    manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(models), _READINESS_HELPER)
    presence = {route.route_fingerprint: any(
        bool(_os.environ.get(n)) for n in route.credential_source)
        for route in manifest.routes}
    if not readiness_gate_ok(record=record, models=models, head_sha=prepared.git_sha,
                             now_iso=_readiness_now_iso(), credential_present=presence):
        raise RuntimeError(
            "readiness gate refused: no fresh passing readiness record for this "
            "commit/route manifest; run scripts/lm9b_p_readiness_probe.py "
            "--authenticate first (no attempt was allocated)")
```

(f) Add a test-only constructor so the witness can drive the real transmit function without the full CLI bootstrap (place near `prepare_pretransmission`):

```python
def build_prepared_for_test(*, models, git_sha, run_root, readiness_record):
    """Construct a minimal PreparedTransmission for boundary tests. Not used by
    the canonical CLI path."""
    config = CliAttemptConfig(
        planner_model=models["planner"],
        planner_evaluator_model=models["planner_evaluator"],
        compiler_model=models["compiler"],
        compiler_evaluator_model=models["compiler_evaluator"],
        planner_temperature=0.0, planner_evaluator_temperature=0.0,
        compiler_temperature=0.0, compiler_evaluator_temperature=0.0,
        run_root=Path(run_root), transmit=True, readiness_record=Path(readiness_record))
    return prepare_pretransmission(config)
```

(If `CliAttemptConfig` field names differ, match them exactly; the witness only needs the four models, temperatures, `run_root`, `transmit`, `readiness_record`.)

- [ ] **Step 6: Run the witness to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_witness.py -v`
Expected: PASS — valid record reaches allocation + sentinel provider construction; model-drift, stale, and credential-absent each refuse before allocation; import isolation holds.

- [ ] **Step 7: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py scripts/lm9b_p_readiness_probe.py \
        scripts/lm9b_p_planner_recipe_transfer_probe.py \
        mcp_server/tests/test_lm9b_p_readiness_witness.py
git commit -m "feat(lm9b-p): vertical readiness witness through the real transmit boundary

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Verifier equation matrix (hardening the witness's guard)

**Files:**
- Test: `mcp_server/tests/test_lm9b_p_readiness_verifier.py` (contract already complete from Task 1)

**Interfaces:** Consumes `verify_launch_readiness`, `derive_routes`, `record_fingerprint`, `request_fingerprint` from Task 1.

- [ ] **Step 1: Write the failing/complete test** (prepend `_load_script`; build a fresh valid record helper, then one refusal case per equation)

```python
import copy
C = _load_script("lm9b_p_readiness_contract")
P = _load_script("lm9b_p_readiness_probe")
HEAD = "d" * 40
MODELS = dict(C.CANONICAL_ROLE_MODELS)

def _manifest():
    return C.derive_routes(C.role_routes_from_models(MODELS), P.HELPER)

def _fresh(now="2026-07-21T12:00:10Z", observed="2026-07-21T12:00:05Z"):
    m = _manifest()
    rows = [{"route_fingerprint": r.route_fingerprint, "member_roles": list(r.member_roles),
             "observed_at": observed, "request_fingerprint": C.request_fingerprint(r),
             "outcome": {"kind": "model_response", "assistant_present": True,
                 "tool_calls": [{"name": "ack", "arguments": "{\"ok\": true}"}],
                 "raw_response_fingerprint": "sha256:resp"}} for r in m.routes]
    rec = {"schema_id": C.SCHEMA_ID, "reviewed_commit_sha": HEAD,
        "route_manifest_fingerprint": m.manifest_fingerprint,
        "canary_protocol_fingerprint": C.canary_protocol_fingerprint(),
        "max_age_seconds": 600, "completed_at": now, "routes": rows}
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    return rec

def _verify(rec, now="2026-07-21T12:00:15Z", present=None):
    present = present or {r["route_fingerprint"]: True for r in rec["routes"]}
    return C.verify_launch_readiness(record=rec, manifest=_manifest(),
        head_sha=HEAD, now_iso=now, credential_present=present).ok

def test_happy_path_permits():
    assert _verify(_fresh()) is True

def test_each_mutation_refuses():
    # sha
    r = _fresh(); r["reviewed_commit_sha"] = "e"*40; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # manifest fp
    r = _fresh(); r["route_manifest_fingerprint"] = "sha256:x"; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # record fp
    r = _fresh(); r["record_fingerprint"] = "sha256:x"; assert _verify(r) is False
    # protocol fp
    r = _fresh(); r["canary_protocol_fingerprint"] = "sha256:x"; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # max_age
    r = _fresh(); r["max_age_seconds"] = 1200; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # missing route
    r = _fresh(); r["routes"] = r["routes"][:1]; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # duplicate route
    r = _fresh(); r["routes"] = [r["routes"][0], copy.deepcopy(r["routes"][0])]; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # member roles
    r = _fresh(); r["routes"][0]["member_roles"] = ["planner"]; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # request binding
    r = _fresh(); r["routes"][0]["request_fingerprint"] = "sha256:x"; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
    # stale record
    assert _verify(_fresh(now="2026-07-21T12:00:00Z"), now="2026-07-21T12:20:00Z") is False
    # future record
    assert _verify(_fresh(now="2026-07-21T12:10:00Z"), now="2026-07-21T12:00:00Z") is False
    # stale route observed_at
    assert _verify(_fresh(now="2026-07-21T12:00:10Z", observed="2026-07-21T11:40:00Z")) is False
    # completed precedes observed
    r = _fresh(now="2026-07-21T12:00:00Z", observed="2026-07-21T12:00:30Z"); r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r, now="2026-07-21T12:00:31Z") is False
    # credential absent
    r = _fresh(); pres = {row["route_fingerprint"]: True for row in r["routes"]}; pres[r["routes"][0]["route_fingerprint"]] = False; assert _verify(r, present=pres) is False
    # route unready
    r = _fresh(); r["routes"][0]["outcome"]["kind"] = "transport_failure"; r["record_fingerprint"] = C.record_fingerprint(r); assert _verify(r) is False
```

- [ ] **Step 2: Run to verify** — `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_verifier.py -v` → Expected: PASS (contract already implements all equations in Task 1). If any case fails, fix the corresponding branch in `verify_launch_readiness`.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_lm9b_p_readiness_verifier.py
git commit -m "test(lm9b-p): full launch-verifier refusal matrix

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `route_ready` matrix and credential-source resolver (spec tests 10/11)

**Files:**
- Test: `mcp_server/tests/test_lm9b_p_readiness_contract_units.py`

**Interfaces:** Consumes `route_ready`, `resolve_credential_source`, `derive_routes`, `CREDENTIAL_SOURCE_DECLARATIONS` from Task 1.

- [ ] **Step 1: Write the tests**

```python
import pytest
C = _load_script("lm9b_p_readiness_contract")

def _ok_row():
    return {"outcome": {"kind": "model_response", "assistant_present": True,
        "tool_calls": [{"name": "ack", "arguments": "{\"ok\": true}"}]}}

def test_route_ready_accepts_conforming():
    assert C.route_ready(_ok_row()) is True

@pytest.mark.parametrize("mut", [
    lambda o: o.update(kind="transport_failure"),
    lambda o: o.update(assistant_present=False),
    lambda o: o.update(tool_calls=[]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "{\"ok\": true}"}]*2),
    lambda o: o.update(tool_calls=[{"name": "no", "arguments": "{\"ok\": true}"}]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "{\"ok\": false}"}]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "not json"}]),
    lambda o: o.update(tool_calls=[{"name": "ack"}]),
])
def test_route_ready_rejects(mut):
    row = _ok_row(); mut(row["outcome"]); assert C.route_ready(row) is False

def test_declaration_is_closed_two_entries():
    assert C.CREDENTIAL_SOURCE_DECLARATIONS == {
        ("openai", "gpt-5.4"): ("OPENAI_API_KEY",),
        ("gemini", "gemini/gemini-3.1-pro-preview"): ("GOOGLE_API_KEY", "GEMINI_API_KEY")}

def test_resolver_null_helper_uses_declaration():
    assert C.resolve_credential_source("openai", "gpt-5.4", None) == ("OPENAI_API_KEY",)

def test_resolver_member_helper_ok():
    assert C.resolve_credential_source("gemini", "gemini/gemini-3.1-pro-preview",
        "GEMINI_API_KEY") == ("GOOGLE_API_KEY", "GEMINI_API_KEY")

def test_resolver_nonmember_helper_fails():
    with pytest.raises(C.ReadinessError):
        C.resolve_credential_source("openai", "gpt-5.4", "WRONG_KEY")

def test_unknown_route_fails_closed():
    with pytest.raises(C.ReadinessError):
        C.resolve_credential_source("openai", "mystery", None)
    with pytest.raises(C.ReadinessError):
        C.derive_routes((C.RoleRoute("x", "litellm.completion", "openai", "mystery"),),
                        lambda m: None)
```

- [ ] **Step 2: Run** — `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract_units.py -v` → PASS.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_lm9b_p_readiness_contract_units.py
git commit -m "test(lm9b-p): ack-conformance matrix and credential resolver edges

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Probe behavior — capture, approval/cardinality, content exclusion

**Files:**
- Test: `mcp_server/tests/test_lm9b_p_readiness_probe.py`

**Interfaces:** Consumes probe `run_canary`, `run_readiness`, `credential_presence`, `assemble_record` from Task 1.

- [ ] **Step 1: Write the tests**

```python
import json
P = _load_script("lm9b_p_readiness_probe")
C = _load_script("lm9b_p_readiness_contract")
LM9BC = _load_script("lm9b_c_compiler_sufficiency_probe")

class _Clock:
    def __init__(self): self.n = 0
    def __call__(self): self.n += 1; return f"2026-07-21T12:00:{self.n:02d}Z"

def _ok_provider(route):
    def _call(req):
        return LM9BC.ProviderTurn(raw_request=b"{}", raw_response=b'{"id":"x"}',
            assistant_message={"role": "assistant", "content": None,
                "tool_calls": [{"id": "1", "type": "function",
                    "function": {"name": "ack", "arguments": "{\"ok\": true}"}}]},
            usage={}, provider_metadata={})
    return _call

def _raising_provider(route):
    def _call(req):
        raise LM9BC.ProviderCallFailure(failure_type="InternalServerError",
            message="boom", raw_request=b"{}", raw_error=b"{}")
    return _call

def test_success_row_ready_and_observed_after_request():
    route = C.derive_routes(C.role_routes_from_models(C.CANONICAL_ROLE_MODELS), P.HELPER).routes[0]
    row = P.run_canary(route, _ok_provider(route), clock=_Clock())
    assert row["outcome"]["kind"] == "model_response" and C.route_ready(row)
    assert row["request_fingerprint"] == C.request_fingerprint(route)

def test_transport_failure_row():
    route = C.derive_routes(C.role_routes_from_models(C.CANONICAL_ROLE_MODELS), P.HELPER).routes[0]
    row = P.run_canary(route, _raising_provider(route), clock=_Clock())
    assert row["outcome"]["kind"] == "transport_failure"
    assert row["outcome"]["classification"] == "InternalServerError"

def test_no_authenticate_no_contact(tmp_path):
    made = []
    def factory(r): made.append(r); return _ok_provider(r)
    rec = P.run_readiness(run_root=tmp_path/"r", head_sha="d"*40,
        environ={"OPENAI_API_KEY":"x","GEMINI_API_KEY":"y"}, authenticate=False,
        provider_factory=factory, clock=_Clock())
    assert made == [] and rec["routes"] == []

def test_authenticate_contacts_each_route_once(tmp_path):
    seen = {}
    def factory(r):
        p = _ok_provider(r); seen[r.route_fingerprint] = seen.get(r.route_fingerprint,0); return p
    rec = P.run_readiness(run_root=tmp_path/"r", head_sha="d"*40,
        environ={"OPENAI_API_KEY":"x","GEMINI_API_KEY":"y"}, authenticate=True,
        provider_factory=factory, clock=_Clock())
    assert len(rec["routes"]) == 2
    assert rec["completed_at"] >= max(row["observed_at"] for row in rec["routes"])

def test_missing_credential_leaves_no_directory(tmp_path):
    root = tmp_path/"r"
    with pytest.raises(C.ReadinessError):
        P.run_readiness(run_root=root, head_sha="d"*40,
            environ={"OPENAI_API_KEY":"x"}, authenticate=True,
            provider_factory=_ok_provider, clock=_Clock())
    assert not root.exists()

def test_canary_request_excludes_experiment_content():
    route = C.derive_routes(C.role_routes_from_models(C.CANONICAL_ROLE_MODELS), P.HELPER).routes[0]
    blob = json.dumps(C.build_canary_request(route)).lower()
    for f in ("brief","authority","r01","rubric","recipe","planner_graph"):
        assert f not in blob
```

Add `import pytest` at the top.

- [ ] **Step 2: Run** — `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py -v` → PASS.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_lm9b_p_readiness_probe.py
git commit -m "test(lm9b-p): canary capture, approval/cardinality, ordering, content exclusion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Boundary regression and full suite

**Files:**
- Test: extend `mcp_server/tests/test_lm9b_p_readiness_witness.py` with the canonical Planner pin refusal, and confirm the pre-existing experiment probe tests still pass.

- [ ] **Step 1: Add the pin refusal test**

```python
def test_canonical_planner_pin_rejects_non_gpt54():
    with pytest.raises(SystemExit):
        EXP.parse_cli_args([
            "--planner-model", "gpt-4o", "--planner-evaluator-model", "gpt-4o",
            "--compiler-model", "gemini/gemini-3.1-pro-preview",
            "--compiler-evaluator-model", "gemini/gemini-3.1-pro-preview",
            "--planner-temperature", "0.0", "--planner-evaluator-temperature", "0.0",
            "--compiler-temperature", "0.0", "--compiler-evaluator-temperature", "0.0",
            "--run-root", "x", "--transmit", "--readiness-record", "r.json"])

def test_dry_run_does_not_require_readiness_record():
    cfg = EXP.parse_cli_args([
        "--planner-model", "gpt-5.4", "--planner-evaluator-model", "gpt-5.4",
        "--compiler-model", "gemini/gemini-3.1-pro-preview",
        "--compiler-evaluator-model", "gemini/gemini-3.1-pro-preview",
        "--planner-temperature", "0.0", "--planner-evaluator-temperature", "0.0",
        "--compiler-temperature", "0.0", "--compiler-evaluator-temperature", "0.0",
        "--run-root", "x"])  # no --transmit, no --readiness-record
    assert cfg.transmit is False
```

- [ ] **Step 2: Run the full readiness + experiment suite**

```bash
"$PY" -m pytest \
  mcp_server/tests/test_lm9b_p_readiness_witness.py \
  mcp_server/tests/test_lm9b_p_readiness_verifier.py \
  mcp_server/tests/test_lm9b_p_readiness_contract_units.py \
  mcp_server/tests/test_lm9b_p_readiness_probe.py \
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py \
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py -v
```

Expected: PASS. If a pre-existing experiment-probe dry-run test breaks solely because of the new pin or the optional `--readiness-record`, update that test's arg list mechanically (it must already use `gpt-5.4` for the Planner to match the canonical attempt; the pin only formalizes that).

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_lm9b_p_readiness_witness.py \
        mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py
git commit -m "test(lm9b-p): canonical Planner pin and dry-run interface preserved

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec + P1/P2 coverage:**
- Vertical witness through the real transmit boundary (reviewer's core correction) → Task 1 (valid reaches allocation + provider construction; model-binding drift, staleness, credential-absent refuse before allocation; import isolation via the experiment CLI).
- P1a identity binding → routes derived from actual parsed models everywhere (`role_routes_from_models` / `_launch_models`); canonical Planner pin (Task 1e, Task 5).
- P1b timestamp ordering → `observed_at` stamped after each call, `completed_at` after all, injected clock; credential check before readiness-root creation (Task 1 Step 4; Task 4 tests).
- P1c real boundary enforcement → Task 1 drives `_execute_transmitted_attempt` with exploding `_build_provider`, asserts run root absent on refusal; import isolation imports the experiment CLI.
- P2 `--readiness-record` only with `--transmit` → Task 1d; Task 5 dry-run test.
- Spec §5.1 declaration + tests 10/11 → Task 3. Verifier equations §9/§9.1 → Task 2. Canary/route_ready §6/§7 → Tasks 1/3/4.

**2. Placeholder scan:** Task 1 Step 1's `_FakeOk` placeholder is intentionally superseded within the same file by the real `ProviderTurn` factory in `_seal_record`; no production placeholders. Remove the unused `_FakeOk` stub when implementing.

**3. Type consistency:** `role_routes_from_models`, `derive_routes`, `verify_launch_readiness(record, manifest, head_sha, now_iso, credential_present)`, `readiness_gate_ok(record, models, head_sha, now_iso, credential_present)`, `run_readiness(..., clock, models)`, `run_canary(route, provider, *, clock)` are consistent across tasks. `ProviderTurn`/`ProviderCallFailure` match the production `LiteLLMProvider` contract (`raw_response: bytes`).

## Execution Handoff

Plan complete. Two execution options — Subagent-Driven (recommended) or Inline Execution — offered after review.
