# LM9B-P Readiness Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a staged, operator-error-proof readiness boundary (local preflight → explicitly-approved experiment-content-free canary → sealed readiness record → pure refuse-before-allocation launch verifier) in front of the unchanged one-shot LM9B-P Planner-transfer experiment, so a missing or non-functional credential/access fault is caught operationally instead of consuming an attempt identity.

**Architecture:** Three code surfaces. A **pure contract module** (`scripts/lm9b_p_readiness_contract.py`, stdlib-only, no Git/filesystem/clock/environment I/O) owns route derivation, the credential-source declaration, fingerprints, the canary protocol constants, `build_canary_request`, `route_ready`, and `verify_launch_readiness`. A **disposable readiness probe** (`scripts/lm9b_p_readiness_probe.py`) imports the contract, owns provider contact via the production `LiteLLMProvider`, and writes the record. The **experiment CLI** (`scripts/lm9b_p_planner_recipe_transfer_probe.py`) imports **only** the pure contract and gains a refuse-before-`mkdir` precondition. The contract module never imports provider code, so importing the verifier is a pure operation.

**Tech Stack:** Python 3.10/3.12, pytest, LiteLLM 1.89.4 (production adapter, contacted only under `--authenticate`), stdlib `hashlib`/`json`/`datetime`/`dataclasses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-lm9b-p-readiness-boundary-design.md` (authoritative).
- Base: worktree `codex/lm9b-p-readiness-boundary` on `origin/main` `dfd90659`.
- `FROZEN_MAX_AGE_S = 600` seconds — frozen in the module, never operator-set.
- Credential-source declaration is a closed two-entry map, names only, never values, verified against installed LiteLLM 1.89.4: `("openai","gpt-5.4") -> ("OPENAI_API_KEY",)`; `("gemini","gemini/gemini-3.1-pro-preview") -> ("GOOGLE_API_KEY","GEMINI_API_KEY")`. Presence is satisfied when **at least one** declared name is set.
- The pure contract module imports **stdlib only** — never `litellm`, never `lm9b_p_readiness_probe`, never `rook.*` at module top level. `api_key_env_for_model` is passed in as a callable, not imported by the contract.
- Do **not** modify `mcp_server/src/rook/agent/model_profiles.py`. Do **not** change the frozen model IDs.
- The canary sends **no** experiment content (no brief, authority artifacts, R01 identifiers, rubric, recipe schema, expected output, forbidden markers). One contact per distinct route, no retry.
- The experiment CLI change is refuse-only: it imports only `lm9b_p_readiness_contract`; it must not import `lm9b_p_readiness_probe`.
- Readiness failure never consumes a scientific attempt. The LM9B-P attempt stays one-shot and behaviorally unchanged. This slice does not begin the scientific attempt and grants no execution authority.
- **Test command** (run from the worktree root `C:/UDEV/Rook/.worktrees/lm9b-p-readiness-boundary`), using the populated main-checkout venv:
  `PY="C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe"`
  `"$PY" -m pytest mcp_server/tests/<file> -v`
- Test module-load convention (copy verbatim into each new test file):

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

- Commit after every task with a `feat(lm9b-p):` or `test(lm9b-p):` message ending with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: Contract module — fingerprint, credential-source declaration, resolver

**Files:**
- Create: `scripts/lm9b_p_readiness_contract.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_contract.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `FROZEN_MAX_AGE_S: int = 600`
  - `SCHEMA_ID: str = "lm9b_p.readiness_record:v1"`
  - `class ReadinessError(ValueError)`
  - `CREDENTIAL_SOURCE_DECLARATIONS: dict[tuple[str, str], tuple[str, ...]]`
  - `def canonical_fingerprint(value: object) -> str` → `"sha256:"`-prefixed sha256 over canonical JSON
  - `def resolve_credential_source(provider: str, model: str, helper_result: str | None) -> tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

```python
# mcp_server/tests/test_lm9b_p_readiness_contract.py
# (prepend the _load_script convention block from Global Constraints)
import pytest
C = _load_script("lm9b_p_readiness_contract")

def test_frozen_constants():
    assert C.FROZEN_MAX_AGE_S == 600
    assert C.SCHEMA_ID == "lm9b_p.readiness_record:v1"

def test_canonical_fingerprint_is_stable_and_order_independent():
    a = C.canonical_fingerprint({"x": 1, "y": [1, 2]})
    b = C.canonical_fingerprint({"y": [1, 2], "x": 1})
    assert a == b and a.startswith("sha256:")
    assert C.canonical_fingerprint({"x": 2}) != a

def test_declaration_is_the_closed_two_entry_map():
    assert C.CREDENTIAL_SOURCE_DECLARATIONS == {
        ("openai", "gpt-5.4"): ("OPENAI_API_KEY",),
        ("gemini", "gemini/gemini-3.1-pro-preview"): ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    }

def test_resolver_uses_declaration_when_helper_null():
    assert C.resolve_credential_source("openai", "gpt-5.4", None) == ("OPENAI_API_KEY",)
    assert C.resolve_credential_source(
        "gemini", "gemini/gemini-3.1-pro-preview", None
    ) == ("GOOGLE_API_KEY", "GEMINI_API_KEY")

def test_resolver_accepts_helper_that_is_a_member():
    assert C.resolve_credential_source("openai", "gpt-5.4", "OPENAI_API_KEY") == ("OPENAI_API_KEY",)

def test_resolver_rejects_helper_not_in_declaration():
    with pytest.raises(C.ReadinessError):
        C.resolve_credential_source("openai", "gpt-5.4", "SOME_OTHER_KEY")

def test_resolver_fails_closed_for_unknown_route():
    with pytest.raises(C.ReadinessError):
        C.resolve_credential_source("openai", "unknown-model", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -v`
Expected: FAIL — `No module named ... lm9b_p_readiness_contract` / attribute errors.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/lm9b_p_readiness_contract.py
#!/usr/bin/env python
"""Pure LM9B-P readiness contract: routes, fingerprints, canary protocol, and
launch verification. Stdlib only — no Git/filesystem/clock/environment I/O, no
provider imports. Callers supply current SHA, time, and env observations."""

from __future__ import annotations

import hashlib
import json

FROZEN_MAX_AGE_S: int = 600
SCHEMA_ID: str = "lm9b_p.readiness_record:v1"


class ReadinessError(ValueError):
    """Raised when a readiness contract invariant is violated."""


# Closed, reviewed credential-source map. Names only, never values. Verified
# against installed LiteLLM 1.89.4 (OpenAI: OPENAI_API_KEY; Gemini completion
# get_api_key: GOOGLE_API_KEY then GEMINI_API_KEY). Presence is satisfied when
# at least one declared name is set.
CREDENTIAL_SOURCE_DECLARATIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("openai", "gpt-5.4"): ("OPENAI_API_KEY",),
    ("gemini", "gemini/gemini-3.1-pro-preview"): ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}


def canonical_fingerprint(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def resolve_credential_source(
    provider: str, model: str, helper_result: str | None
) -> tuple[str, ...]:
    declaration = CREDENTIAL_SOURCE_DECLARATIONS.get((provider, model))
    if declaration is None:
        raise ReadinessError(f"no credential-source declaration for {provider}/{model}")
    if helper_result is not None and helper_result not in declaration:
        raise ReadinessError(
            f"canonical helper {helper_result!r} is not in the declared "
            f"credential source for {provider}/{model}"
        )
    return declaration
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py mcp_server/tests/test_lm9b_p_readiness_contract.py
git commit -m "feat(lm9b-p): readiness contract fingerprint and credential-source resolver

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Contract module — frozen role routes, derivation, manifest fingerprint

**Files:**
- Modify: `scripts/lm9b_p_readiness_contract.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_contract.py`

**Interfaces:**
- Consumes: `resolve_credential_source`, `canonical_fingerprint` (Task 1).
- Produces:
  - `@dataclass(frozen=True) class RoleRoute` with `role, adapter_path, provider, model`
  - `@dataclass(frozen=True) class DistinctRoute` with `route_fingerprint, adapter_path, provider, model, credential_source: tuple[str, ...], member_roles: tuple[str, ...]`
  - `@dataclass(frozen=True) class RouteManifest` with `routes: tuple[DistinctRoute, ...], manifest_fingerprint: str`
  - `READINESS_ROLE_ROUTES: tuple[RoleRoute, ...]` (the four frozen roles)
  - `def derive_routes(role_routes, helper) -> RouteManifest` where `helper: Callable[[str], str | None]`

- [ ] **Step 1: Write the failing test**

```python
def _null_helper(model):
    return None

def test_role_routes_cover_four_roles():
    roles = sorted(r.role for r in C.READINESS_ROLE_ROUTES)
    assert roles == ["compiler", "compiler_evaluator", "planner", "planner_evaluator"]

def test_derive_routes_dedupes_to_two_with_member_roles():
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, _null_helper)
    assert len(manifest.routes) == 2  # frozen-config assertion only
    by_provider = {r.provider: r for r in manifest.routes}
    assert set(by_provider) == {"openai", "gemini"}
    assert by_provider["openai"].member_roles == ("planner", "planner_evaluator")
    assert by_provider["gemini"].member_roles == ("compiler", "compiler_evaluator")
    assert by_provider["openai"].credential_source == ("OPENAI_API_KEY",)
    assert by_provider["gemini"].credential_source == ("GOOGLE_API_KEY", "GEMINI_API_KEY")

def test_manifest_fingerprint_is_deterministic_and_order_independent():
    m1 = C.derive_routes(C.READINESS_ROLE_ROUTES, _null_helper)
    reordered = tuple(reversed(C.READINESS_ROLE_ROUTES))
    m2 = C.derive_routes(reordered, _null_helper)
    assert m1.manifest_fingerprint == m2.manifest_fingerprint

def test_derive_routes_fails_closed_on_unknown_route():
    bad = C.READINESS_ROLE_ROUTES + (
        C.RoleRoute("extra", "litellm.completion", "openai", "mystery-model"),
    )
    with pytest.raises(C.ReadinessError):
        C.derive_routes(bad, _null_helper)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -k "derive or role_routes or manifest_fingerprint" -v`
Expected: FAIL — `RoleRoute` / `derive_routes` undefined.

- [ ] **Step 3: Write minimal implementation**

Add imports at the top of the module (after existing imports):

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass
```

Append:

```python
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


READINESS_ROLE_ROUTES: tuple[RoleRoute, ...] = (
    RoleRoute("planner", "litellm.completion", "openai", "gpt-5.4"),
    RoleRoute("planner_evaluator", "litellm.completion", "openai", "gpt-5.4"),
    RoleRoute("compiler", "litellm.completion", "gemini", "gemini/gemini-3.1-pro-preview"),
    RoleRoute("compiler_evaluator", "litellm.completion", "gemini", "gemini/gemini-3.1-pro-preview"),
)


def _grouping_key(route: RoleRoute, credential_source: tuple[str, ...]) -> tuple:
    return (route.adapter_path, route.provider, route.model, credential_source)


def derive_routes(
    role_routes: Sequence[RoleRoute],
    helper: Callable[[str], str | None],
) -> RouteManifest:
    groups: dict[tuple, list[str]] = {}
    meta: dict[tuple, tuple[str, str, str, tuple[str, ...]]] = {}
    for route in role_routes:
        credential_source = resolve_credential_source(
            route.provider, route.model, helper(route.model)
        )
        key = _grouping_key(route, credential_source)
        groups.setdefault(key, []).append(route.role)
        meta[key] = (route.adapter_path, route.provider, route.model, credential_source)
    distinct: list[DistinctRoute] = []
    for key, roles in groups.items():
        adapter_path, provider, model, credential_source = meta[key]
        identity = {
            "adapter_path": adapter_path,
            "provider": provider,
            "model": model,
            "credential_source": list(credential_source),
        }
        distinct.append(
            DistinctRoute(
                route_fingerprint=canonical_fingerprint(identity),
                adapter_path=adapter_path,
                provider=provider,
                model=model,
                credential_source=credential_source,
                member_roles=tuple(sorted(roles)),
            )
        )
    distinct.sort(key=lambda r: r.route_fingerprint)
    manifest_fingerprint = canonical_fingerprint(
        [r.route_fingerprint for r in distinct]
    )
    return RouteManifest(routes=tuple(distinct), manifest_fingerprint=manifest_fingerprint)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -v`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py mcp_server/tests/test_lm9b_p_readiness_contract.py
git commit -m "feat(lm9b-p): derive deduped route manifest from frozen roles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Contract module — canary protocol, protocol fingerprint, request builder

**Files:**
- Modify: `scripts/lm9b_p_readiness_contract.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_contract.py`

**Interfaces:**
- Consumes: `DistinctRoute`, `canonical_fingerprint`.
- Produces:
  - `ACK_TOOL: dict` — throwaway forced tool `ack(ok: boolean)`
  - `CANARY_SYSTEM`, `CANARY_USER`, `CANARY_MAX_COMPLETION_TOKENS`, `CANARY_PROVIDER_TIMEOUT_S`, `CANARY_TEMPERATURE`
  - `def canary_protocol() -> dict`
  - `def canary_protocol_fingerprint() -> str`
  - `def build_canary_request(route: DistinctRoute) -> dict`
  - `def request_fingerprint(route: DistinctRoute) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_canary_protocol_is_experiment_content_free():
    proto = C.canary_protocol()
    blob = C.json.dumps(proto)
    for forbidden in ("brief", "authority", "R01", "rubric", "recipe", "planner_graph_recipe"):
        assert forbidden.lower() not in blob.lower()
    assert proto["tool"]["function"]["name"] == "ack"

def test_protocol_fingerprint_is_stable():
    assert C.canary_protocol_fingerprint() == C.canary_protocol_fingerprint()
    assert C.canary_protocol_fingerprint().startswith("sha256:")

def test_build_canary_request_binds_model_and_forces_ack():
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, lambda m: None)
    route = manifest.routes[0]
    req = C.build_canary_request(route)
    assert req["model"] == route.model
    assert req["messages"][0]["role"] == "system"
    assert req["tool_choice"]["function"]["name"] == "ack"
    assert req["tools"][0]["function"]["name"] == "ack"

def test_request_fingerprint_differs_across_distinct_routes():
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, lambda m: None)
    fps = {C.request_fingerprint(r) for r in manifest.routes}
    assert len(fps) == len(manifest.routes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -k "canary or protocol or build_canary or request_fingerprint" -v`
Expected: FAIL — protocol/build helpers undefined.

- [ ] **Step 3: Write minimal implementation**

Append:

```python
CANARY_SYSTEM: str = "You are a readiness canary."
CANARY_USER: str = "Call the ack tool."
CANARY_MAX_COMPLETION_TOKENS: int = 16
CANARY_PROVIDER_TIMEOUT_S: float = 30.0
CANARY_TEMPERATURE: float = 0.0

ACK_TOOL: dict = {
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


def canary_protocol() -> dict:
    return {
        "system": CANARY_SYSTEM,
        "user": CANARY_USER,
        "tool": ACK_TOOL,
        "max_completion_tokens": CANARY_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": CANARY_PROVIDER_TIMEOUT_S,
        "temperature": CANARY_TEMPERATURE,
    }


def canary_protocol_fingerprint() -> str:
    return canonical_fingerprint(canary_protocol())


def build_canary_request(route: DistinctRoute) -> dict:
    proto = canary_protocol()
    return {
        "model": route.model,
        "messages": [
            {"role": "system", "content": proto["system"]},
            {"role": "user", "content": proto["user"]},
        ],
        "tools": [proto["tool"]],
        "tool_choice": {"type": "function", "function": {"name": "ack"}},
        "max_completion_tokens": proto["max_completion_tokens"],
        "provider_timeout_s": proto["provider_timeout_s"],
    }


def request_fingerprint(route: DistinctRoute) -> str:
    return canonical_fingerprint(build_canary_request(route))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -v`
Expected: PASS (15 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py mcp_server/tests/test_lm9b_p_readiness_contract.py
git commit -m "feat(lm9b-p): canary protocol constants and request binding

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Contract module — `route_ready` and record fingerprint

**Files:**
- Modify: `scripts/lm9b_p_readiness_contract.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_contract.py`

**Interfaces:**
- Consumes: `canonical_fingerprint`.
- Produces:
  - `def route_ready(row: dict) -> bool` — validates the `ack` conformance from evidence
  - `def record_fingerprint(record: dict) -> str` — fingerprint over the record excluding `record_fingerprint`

- [ ] **Step 1: Write the failing test**

```python
def _ok_row():
    return {
        "route_fingerprint": "sha256:aaa",
        "member_roles": ["planner", "planner_evaluator"],
        "observed_at": "2026-07-21T11:59:59Z",
        "request_fingerprint": "sha256:req",
        "outcome": {
            "kind": "model_response",
            "assistant_present": True,
            "tool_calls": [{"name": "ack", "arguments": "{\"ok\": true}"}],
            "raw_response_fingerprint": "sha256:resp",
        },
    }

def test_route_ready_accepts_conforming_ack():
    assert C.route_ready(_ok_row()) is True

@pytest.mark.parametrize("mutate", [
    lambda o: o.update(kind="transport_failure"),
    lambda o: o.update(assistant_present=False),
    lambda o: o.update(tool_calls=[]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "{\"ok\": true}"},
                                   {"name": "ack", "arguments": "{\"ok\": true}"}]),
    lambda o: o.update(tool_calls=[{"name": "nope", "arguments": "{\"ok\": true}"}]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "{\"ok\": false}"}]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "not json"}]),
    lambda o: o.update(tool_calls=[{"name": "ack"}]),  # arguments missing entirely
])
def test_route_ready_rejects_nonconforming(mutate):
    row = _ok_row()
    mutate(row["outcome"])
    assert C.route_ready(row) is False

def test_record_fingerprint_ignores_its_own_field():
    rec = {"a": 1, "record_fingerprint": "sha256:stale"}
    assert C.record_fingerprint(rec) == C.record_fingerprint({"a": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -k "route_ready or record_fingerprint" -v`
Expected: FAIL — `route_ready` / `record_fingerprint` undefined.

- [ ] **Step 3: Write minimal implementation**

Append:

```python
def route_ready(row: dict) -> bool:
    outcome = row.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("kind") != "model_response":
        return False
    if outcome.get("assistant_present") is not True:
        return False
    tool_calls = outcome.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        return False
    call = tool_calls[0]
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
        {k: v for k, v in record.items() if k != "record_fingerprint"}
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py -v`
Expected: PASS (all route_ready params + record_fingerprint pass).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py mcp_server/tests/test_lm9b_p_readiness_contract.py
git commit -m "feat(lm9b-p): evidence-derived ack conformance and record fingerprint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Contract module — `verify_launch_readiness`

**Files:**
- Modify: `scripts/lm9b_p_readiness_contract.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_verifier.py`

**Interfaces:**
- Consumes: `derive_routes`, `route_ready`, `record_fingerprint`, `request_fingerprint`, `canary_protocol_fingerprint`, `FROZEN_MAX_AGE_S`.
- Produces:
  - `@dataclass(frozen=True) class LaunchDecision` with `ok: bool, failures: tuple[str, ...]`
  - `def verify_launch_readiness(*, record, head_sha, now_iso, credential_present, helper, role_routes=READINESS_ROLE_ROUTES) -> LaunchDecision` where `credential_present: dict[str, bool]` maps `route_fingerprint -> bool`, `now_iso`/`record["completed_at"]`/`observed_at` are exact UTC ISO-8601 with trailing `Z`.

- [ ] **Step 1: Write the failing test** (create the new test file with the `_load_script` block, then:)

```python
import copy
C = _load_script("lm9b_p_readiness_contract")
HEAD = "d" * 40

def _fresh_record(now="2026-07-21T12:00:00Z", observed="2026-07-21T11:59:50Z"):
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, lambda m: None)
    routes = []
    for r in manifest.routes:
        routes.append({
            "route_fingerprint": r.route_fingerprint,
            "member_roles": list(r.member_roles),
            "observed_at": observed,
            "request_fingerprint": C.request_fingerprint(r),
            "outcome": {
                "kind": "model_response",
                "assistant_present": True,
                "tool_calls": [{"name": "ack", "arguments": "{\"ok\": true}"}],
                "raw_response_fingerprint": "sha256:resp",
            },
        })
    record = {
        "schema_id": C.SCHEMA_ID,
        "reviewed_commit_sha": HEAD,
        "route_manifest_fingerprint": manifest.manifest_fingerprint,
        "canary_protocol_fingerprint": C.canary_protocol_fingerprint(),
        "max_age_seconds": C.FROZEN_MAX_AGE_S,
        "completed_at": now,
        "routes": routes,
    }
    record["record_fingerprint"] = C.record_fingerprint(record)
    return record

def _present_all(record):
    return {row["route_fingerprint"]: True for row in record["routes"]}

def _verify(record, now="2026-07-21T12:00:05Z"):
    return C.verify_launch_readiness(
        record=record, head_sha=HEAD, now_iso=now,
        credential_present=_present_all(record), helper=lambda m: None,
    )

def test_happy_path_permits():
    assert _verify(_fresh_record()).ok is True

def test_sha_mismatch_refuses():
    rec = _fresh_record()
    d = C.verify_launch_readiness(record=rec, head_sha="e" * 40,
        now_iso="2026-07-21T12:00:05Z", credential_present=_present_all(rec),
        helper=lambda m: None)
    assert d.ok is False

def test_manifest_fingerprint_mismatch_refuses():
    rec = _fresh_record()
    rec["route_manifest_fingerprint"] = "sha256:tampered"
    assert _verify(rec).ok is False

def test_record_fingerprint_mismatch_refuses():
    rec = _fresh_record()
    rec["record_fingerprint"] = "sha256:tampered"
    assert _verify(rec).ok is False

def test_protocol_fingerprint_mismatch_refuses():
    rec = _fresh_record()
    rec["canary_protocol_fingerprint"] = "sha256:tampered"
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False

def test_missing_route_refuses():
    rec = _fresh_record()
    rec["routes"] = rec["routes"][:1]
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False

def test_duplicate_route_refuses():
    rec = _fresh_record()
    rec["routes"] = [rec["routes"][0], copy.deepcopy(rec["routes"][0])]
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False

def test_altered_member_roles_refuses():
    rec = _fresh_record()
    rec["routes"][0]["member_roles"] = ["planner"]
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False

def test_request_fingerprint_mismatch_refuses():
    rec = _fresh_record()
    rec["routes"][0]["request_fingerprint"] = "sha256:wrong"
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False

def test_stale_record_refuses():
    rec = _fresh_record(now="2026-07-21T12:00:00Z")
    assert _verify(rec, now="2026-07-21T12:20:00Z").ok is False  # 1200s > 600

def test_future_timestamp_refuses():
    rec = _fresh_record(now="2026-07-21T12:10:00Z")
    assert _verify(rec, now="2026-07-21T12:00:00Z").ok is False  # completed in the future

def test_stale_route_observed_at_refuses():
    rec = _fresh_record(now="2026-07-21T12:00:00Z", observed="2026-07-21T11:40:00Z")
    assert _verify(rec, now="2026-07-21T12:00:05Z").ok is False  # observed 1205s ago

def test_missing_credential_refuses():
    rec = _fresh_record()
    presence = _present_all(rec)
    presence[rec["routes"][0]["route_fingerprint"]] = False
    d = C.verify_launch_readiness(record=rec, head_sha=HEAD,
        now_iso="2026-07-21T12:00:05Z", credential_present=presence,
        helper=lambda m: None)
    assert d.ok is False

def test_unready_route_refuses():
    rec = _fresh_record()
    rec["routes"][0]["outcome"]["kind"] = "transport_failure"
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False

def test_max_age_field_mismatch_refuses():
    rec = _fresh_record()
    rec["max_age_seconds"] = 1200
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    assert _verify(rec).ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_verifier.py -v`
Expected: FAIL — `verify_launch_readiness` undefined.

- [ ] **Step 3: Write minimal implementation**

Add near the top imports:

```python
from datetime import datetime, timezone
```

Append:

```python
@dataclass(frozen=True)
class LaunchDecision:
    ok: bool
    failures: tuple[str, ...]


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReadinessError(f"timestamp is not exact UTC Z form: {value!r}")
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)


def verify_launch_readiness(
    *,
    record: dict,
    head_sha: str,
    now_iso: str,
    credential_present: dict,
    helper: Callable[[str], str | None],
    role_routes: Sequence[RoleRoute] = READINESS_ROLE_ROUTES,
) -> LaunchDecision:
    failures: list[str] = []

    def fail(msg: str) -> None:
        failures.append(msg)

    # Identity continuity
    if record.get("reviewed_commit_sha") != head_sha:
        fail("commit sha mismatch")
    manifest = derive_routes(role_routes, helper)
    if record.get("route_manifest_fingerprint") != manifest.manifest_fingerprint:
        fail("route manifest fingerprint mismatch")

    # Record integrity
    if record.get("record_fingerprint") != record_fingerprint(record):
        fail("record fingerprint mismatch")
    if record.get("canary_protocol_fingerprint") != canary_protocol_fingerprint():
        fail("canary protocol fingerprint mismatch")
    if record.get("max_age_seconds") != FROZEN_MAX_AGE_S:
        fail("max_age_seconds does not equal the frozen constant")

    rows = record.get("routes")
    rows = rows if isinstance(rows, list) else []
    by_fp = {r.route_fingerprint: r for r in manifest.routes}

    # Exact route coverage (set equality, no duplicates)
    row_fps = [row.get("route_fingerprint") for row in rows]
    if len(row_fps) != len(set(row_fps)):
        fail("duplicate route rows")
    if set(row_fps) != set(by_fp):
        fail("route set does not equal the current manifest")

    # Temporal freshness (record)
    try:
        now = _parse_utc(now_iso)
        completed = _parse_utc(record.get("completed_at"))
        record_age = (now - completed).total_seconds()
        if record_age < 0 or record_age > FROZEN_MAX_AGE_S:
            fail("record completed_at outside the frozen freshness window")
        for row in rows:
            observed = _parse_utc(row.get("observed_at"))
            if completed < observed:
                fail("completed_at precedes a route observed_at")
            age = (now - observed).total_seconds()
            if age < 0 or age > FROZEN_MAX_AGE_S:
                fail("route observed_at outside the frozen freshness window")
    except ReadinessError as exc:
        fail(str(exc))

    # Per-route: member roles, request binding, credential presence, readiness
    for row in rows:
        fp = row.get("route_fingerprint")
        route = by_fp.get(fp)
        if route is None:
            continue  # already reported by coverage
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

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_verifier.py -v`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py mcp_server/tests/test_lm9b_p_readiness_verifier.py
git commit -m "feat(lm9b-p): pure launch verifier recomputes readiness from evidence

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Readiness probe — preflight and record assembly (no provider contact)

**Files:**
- Create: `scripts/lm9b_p_readiness_probe.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_probe.py`

**Interfaces:**
- Consumes: contract module (`derive_routes`, `READINESS_ROLE_ROUTES`, `request_fingerprint`, `canary_protocol_fingerprint`, `record_fingerprint`, `SCHEMA_ID`, `FROZEN_MAX_AGE_S`), `api_key_env_for_model`.
- Produces:
  - `HELPER` (bound `api_key_env_for_model`)
  - `def credential_presence(manifest, environ) -> dict[str, bool]` — presence = any declared name set; **no** provider contact
  - `def assemble_record(*, manifest, head_sha, completed_at, route_rows) -> dict` — seals `record_fingerprint`

- [ ] **Step 1: Write the failing test**

```python
P = _load_script("lm9b_p_readiness_probe")
C = _load_script("lm9b_p_readiness_contract")

def test_credential_presence_any_declared_name_counts():
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER)
    gemini = next(r for r in manifest.routes if r.provider == "gemini")
    openai = next(r for r in manifest.routes if r.provider == "openai")
    env = {"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"}  # GOOGLE absent, GEMINI present
    presence = P.credential_presence(manifest, env)
    assert presence[gemini.route_fingerprint] is True
    assert presence[openai.route_fingerprint] is True

def test_credential_presence_false_when_all_absent():
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER)
    gemini = next(r for r in manifest.routes if r.provider == "gemini")
    presence = P.credential_presence(manifest, {"OPENAI_API_KEY": "x"})
    assert presence[gemini.route_fingerprint] is False

def test_assemble_record_is_verifiable(tmp_path):
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER)
    rows = []
    for r in manifest.routes:
        rows.append({
            "route_fingerprint": r.route_fingerprint,
            "member_roles": list(r.member_roles),
            "observed_at": "2026-07-21T11:59:50Z",
            "request_fingerprint": C.request_fingerprint(r),
            "outcome": {"kind": "model_response", "assistant_present": True,
                        "tool_calls": [{"name": "ack", "arguments": "{\"ok\": true}"}],
                        "raw_response_fingerprint": "sha256:resp"},
        })
    rec = P.assemble_record(manifest=manifest, head_sha="d" * 40,
        completed_at="2026-07-21T12:00:00Z", route_rows=rows)
    assert rec["schema_id"] == C.SCHEMA_ID
    assert rec["record_fingerprint"] == C.record_fingerprint(rec)
    d = C.verify_launch_readiness(record=rec, head_sha="d" * 40,
        now_iso="2026-07-21T12:00:05Z",
        credential_present={row["route_fingerprint"]: True for row in rec["routes"]},
        helper=P.HELPER)
    assert d.ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py -v`
Expected: FAIL — module / functions undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/lm9b_p_readiness_probe.py
#!/usr/bin/env python
"""Disposable LM9B-P readiness probe: local preflight and (under --authenticate)
one experiment-content-free canary per distinct route. Owns provider contact;
imports the pure contract for all identity and verification logic."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_MCP_SRC = _SCRIPTS_DIR.parent / "mcp_server" / "src"
for _p in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lm9b_p_readiness_contract as CONTRACT
from rook.agent.model_profiles import api_key_env_for_model

HELPER = api_key_env_for_model


def credential_presence(manifest, environ) -> dict:
    presence: dict[str, bool] = {}
    for route in manifest.routes:
        presence[route.route_fingerprint] = any(
            bool(environ.get(name)) for name in route.credential_source
        )
    return presence


def assemble_record(*, manifest, head_sha, completed_at, route_rows) -> dict:
    record = {
        "schema_id": CONTRACT.SCHEMA_ID,
        "reviewed_commit_sha": head_sha,
        "route_manifest_fingerprint": manifest.manifest_fingerprint,
        "canary_protocol_fingerprint": CONTRACT.canary_protocol_fingerprint(),
        "max_age_seconds": CONTRACT.FROZEN_MAX_AGE_S,
        "completed_at": completed_at,
        "routes": list(route_rows),
    }
    record["record_fingerprint"] = CONTRACT.record_fingerprint(record)
    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_readiness_probe.py
git commit -m "feat(lm9b-p): readiness preflight and record assembly

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Readiness probe — canary contact, discriminated capture, CLI

**Files:**
- Modify: `scripts/lm9b_p_readiness_probe.py`
- Test: `mcp_server/tests/test_lm9b_p_readiness_probe.py`

**Interfaces:**
- Consumes: `CONTRACT.build_canary_request`, `request_fingerprint`; production `LiteLLMProvider`, `ProviderTurn`, `ProviderCallFailure` from `lm9b_c_compiler_sufficiency_probe`; `assemble_record`, `credential_presence`.
- Produces:
  - `def run_canary(route, provider) -> dict` — one contact, discriminated evidence row (`model_response` | `transport_failure`), no retry
  - `def default_provider_factory(route) -> LiteLLMProvider`
  - `def run_readiness(*, run_root, head_sha, now_iso, environ, authenticate, provider_factory) -> dict` — preflight; if not `authenticate`, no contact; else one canary per route; writes `readiness_record.json` under `run_root`; returns the record
  - `def main(argv=None) -> int`

- [ ] **Step 1: Write the failing test**

```python
import json
LM9BC = _load_script("lm9b_c_compiler_sufficiency_probe")

class _FakeOkProvider:
    def __init__(self, route): self.route = route; self.calls = 0
    def __call__(self, request):
        self.calls += 1
        return LM9BC.ProviderTurn(
            raw_request=b"{}",
            raw_response=b'{"id":"x"}',
            assistant_message={"role": "assistant", "content": None,
                "tool_calls": [{"id": "1", "type": "function",
                    "function": {"name": "ack", "arguments": "{\"ok\": true}"}}]},
            usage={}, provider_metadata={})

class _FakeRaisingProvider:
    def __init__(self, route): self.route = route
    def __call__(self, request):
        raise LM9BC.ProviderCallFailure(failure_type="InternalServerError",
            message="boom", raw_request=b"{}", raw_error=b'{"m":"boom"}')

def test_canary_success_row_is_ready():
    route = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER).routes[0]
    row = P.run_canary(route, _FakeOkProvider(route))
    assert row["outcome"]["kind"] == "model_response"
    assert C.route_ready(row) is True
    assert row["request_fingerprint"] == C.request_fingerprint(route)

def test_canary_transport_failure_row():
    route = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER).routes[0]
    row = P.run_canary(route, _FakeRaisingProvider(route))
    assert row["outcome"]["kind"] == "transport_failure"
    assert row["outcome"]["classification"] == "InternalServerError"
    assert C.route_ready(row) is False

def test_no_authenticate_makes_no_contact(tmp_path):
    made = []
    def factory(route):
        made.append(route); return _FakeOkProvider(route)
    rec = P.run_readiness(run_root=tmp_path / "r", head_sha="d"*40,
        now_iso="2026-07-21T12:00:00Z",
        environ={"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"},
        authenticate=False, provider_factory=factory)
    assert made == []  # zero contact
    assert rec["routes"] == [] or all(r["outcome"]["kind"] == "not_contacted" for r in rec["routes"])

def test_authenticate_contacts_each_route_once(tmp_path):
    counts = {}
    def factory(route):
        prov = _FakeOkProvider(route)
        counts[route.route_fingerprint] = prov
        return prov
    rec = P.run_readiness(run_root=tmp_path / "r", head_sha="d"*40,
        now_iso="2026-07-21T12:00:00Z",
        environ={"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"},
        authenticate=True, provider_factory=factory)
    assert len(rec["routes"]) == 2
    assert all(p.calls == 1 for p in counts.values())
    assert (tmp_path / "r" / "readiness_record.json").exists()

def test_canary_request_excludes_experiment_content():
    route = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER).routes[0]
    blob = json.dumps(C.build_canary_request(route)).lower()
    for forbidden in ("brief", "authority", "r01", "rubric", "recipe", "planner_graph"):
        assert forbidden not in blob
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py -k "canary or authenticate or excludes" -v`
Expected: FAIL — `run_canary` / `run_readiness` undefined.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/lm9b_p_readiness_probe.py` (and add imports at top: `import argparse`, `import hashlib`, `import json`, `from datetime import datetime, timezone`, plus `import lm9b_c_compiler_sufficiency_probe as LM9BC`):

```python
def default_provider_factory(route):
    return LM9BC.LiteLLMProvider(
        model=route.model, temperature=CONTRACT.CANARY_TEMPERATURE
    )


def _detail_hash(message: str) -> str:
    return "sha256:" + hashlib.sha256(message.encode("utf-8")).hexdigest()


def _now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_canary(route, provider) -> dict:
    request = CONTRACT.build_canary_request(route)
    base = {
        "route_fingerprint": route.route_fingerprint,
        "member_roles": list(route.member_roles),
        "observed_at": _now_z(),
        "request_fingerprint": CONTRACT.request_fingerprint(route),
    }
    try:
        turn = provider(request)
    except LM9BC.ProviderCallFailure as exc:
        base["outcome"] = {
            "kind": "transport_failure",
            "classification": exc.failure_type,
            "detail_hash": _detail_hash(exc.message),
        }
        return base
    message = turn.assistant_message or {}
    tool_calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        tool_calls.append({"name": fn.get("name"), "arguments": fn.get("arguments")})
    base["outcome"] = {
        "kind": "model_response",
        "assistant_present": True,
        "tool_calls": tool_calls,
        "raw_response_fingerprint": "sha256:"
        + hashlib.sha256(turn.raw_response).hexdigest(),
    }
    return base


def run_readiness(*, run_root, head_sha, now_iso, environ, authenticate,
                  provider_factory) -> dict:
    run_root = Path(run_root)
    manifest = CONTRACT.derive_routes(CONTRACT.READINESS_ROLE_ROUTES, HELPER)
    presence = credential_presence(manifest, environ)
    run_root.mkdir(parents=True, exist_ok=False)
    rows = []
    if authenticate:
        if not all(presence.values()):
            raise CONTRACT.ReadinessError("preflight failed: credential absent")
        for route in manifest.routes:
            rows.append(run_canary(route, provider_factory(route)))
    record = assemble_record(
        manifest=manifest, head_sha=head_sha, completed_at=now_iso, route_rows=rows
    )
    (run_root / "readiness_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )
    (run_root / "preflight.json").write_text(
        json.dumps({"credential_present": presence}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return record


def main(argv=None) -> int:
    import os
    parser = argparse.ArgumentParser(description="LM9B-P readiness probe")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--reviewed-commit-sha", required=True)
    parser.add_argument("--authenticate", action="store_true")
    args = parser.parse_args(argv)
    record = run_readiness(
        run_root=args.run_root, head_sha=args.reviewed_commit_sha,
        now_iso=_now_z(), environ=dict(os.environ),
        authenticate=args.authenticate, provider_factory=default_provider_factory,
    )
    ready = bool(record["routes"]) and all(
        CONTRACT.route_ready(r) for r in record["routes"]
    )
    print(json.dumps({"authenticated": args.authenticate, "ready": ready}, indent=2))
    return 0
```

Update `test_no_authenticate_makes_no_contact` expectation: with `authenticate=False`, `rec["routes"] == []` (no rows). Adjust the assertion to `assert rec["routes"] == []`.

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py -v`
Expected: PASS (all rows/contact/exclusion tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_probe.py mcp_server/tests/test_lm9b_p_readiness_probe.py
git commit -m "feat(lm9b-p): approved canary contact with discriminated capture

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Experiment CLI launch gate — refuse-before-allocation + import isolation

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_probe.py` (add `--readiness-record` arg to `parse_cli_args`/`CliAttemptConfig`; call the verifier at the top of `_execute_transmitted_attempt`, before `config.run_root.mkdir`)
- Test: `mcp_server/tests/test_lm9b_p_readiness_launch_gate.py`

**Interfaces:**
- Consumes: `lm9b_p_readiness_contract.verify_launch_readiness`, `derive_routes`, `READINESS_ROLE_ROUTES`; `api_key_env_for_model`.
- Produces: refuse-before-allocation behavior; a `CliAttemptConfig.readiness_record: Path` field.

- [ ] **Step 1: Write the failing test**

```python
import json, subprocess, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_import_isolation_contract_pulls_no_provider_code():
    code = (
        "import sys; "
        "sys.path.insert(0, r'%s'); " % str(ROOT / "scripts") +
        "import lm9b_p_readiness_contract as c; "
        "assert 'lm9b_p_readiness_probe' not in sys.modules, 'probe leaked'; "
        "assert 'litellm' not in sys.modules, 'litellm leaked'; "
        "print('ok')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout

def _experiment_verifies_before_mkdir(head, record_path, run_root, now):
    EXP = _load_script("lm9b_p_planner_recipe_transfer_probe")
    C = _load_script("lm9b_p_readiness_contract")
    # Uses the same helper the record was built with.
    record = json.loads(Path(record_path).read_text())
    present = {r["route_fingerprint"]: True for r in record["routes"]}
    return EXP.readiness_gate_ok(
        record=record, head_sha=head, now_iso=now, credential_present=present
    )

def test_credential_disappearance_refuses(tmp_path):
    # Build a fresh passing record, then verify with an absent credential.
    P = _load_script("lm9b_p_readiness_probe")
    C = _load_script("lm9b_p_readiness_contract")
    EXP = _load_script("lm9b_p_planner_recipe_transfer_probe")
    manifest = C.derive_routes(C.READINESS_ROLE_ROUTES, P.HELPER)
    rows = [{
        "route_fingerprint": r.route_fingerprint, "member_roles": list(r.member_roles),
        "observed_at": "2026-07-21T11:59:50Z", "request_fingerprint": C.request_fingerprint(r),
        "outcome": {"kind": "model_response", "assistant_present": True,
            "tool_calls": [{"name": "ack", "arguments": "{\"ok\": true}"}],
            "raw_response_fingerprint": "sha256:resp"}} for r in manifest.routes]
    rec = P.assemble_record(manifest=manifest, head_sha="d"*40,
        completed_at="2026-07-21T12:00:00Z", route_rows=rows)
    absent = {r["route_fingerprint"]: False for r in rec["routes"]}
    d = EXP.readiness_gate_ok(record=rec, head_sha="d"*40,
        now_iso="2026-07-21T12:00:05Z", credential_present=absent)
    assert d is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_launch_gate.py -v`
Expected: FAIL — `readiness_gate_ok` undefined.

- [ ] **Step 3: Write minimal implementation**

In `scripts/lm9b_p_planner_recipe_transfer_probe.py`, add near the other imports:

```python
import lm9b_p_readiness_contract as READINESS
from rook.agent.model_profiles import api_key_env_for_model as _READINESS_HELPER
```

Add a pure helper (near `_git_checkout_state`):

```python
def readiness_gate_ok(*, record, head_sha, now_iso, credential_present) -> bool:
    decision = READINESS.verify_launch_readiness(
        record=record,
        head_sha=head_sha,
        now_iso=now_iso,
        credential_present=credential_present,
        helper=_READINESS_HELPER,
    )
    return decision.ok
```

Add `readiness_record: Path` to `CliAttemptConfig` and, in `parse_cli_args`, add:

```python
parser.add_argument("--readiness-record", type=Path, required=True)
```

and pass `readiness_record=args.readiness_record` when building `CliAttemptConfig`.

In `_execute_transmitted_attempt`, immediately after the existing
`checkout changed after pre-transmission review` guard and **before**
`config.run_root.mkdir(...)`, insert:

```python
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    record = _json.loads(config.readiness_record.read_text(encoding="utf-8"))
    now_iso = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = READINESS.derive_routes(
        READINESS.READINESS_ROLE_ROUTES, _READINESS_HELPER
    )
    import os as _os
    presence = {
        route.route_fingerprint: any(
            bool(_os.environ.get(name)) for name in route.credential_source
        )
        for route in manifest.routes
    }
    if not readiness_gate_ok(
        record=record, head_sha=prepared.git_sha, now_iso=now_iso,
        credential_present=presence,
    ):
        raise RuntimeError(
            "readiness gate refused: no fresh passing readiness record for this "
            "commit/route manifest; run scripts/lm9b_p_readiness_probe.py "
            "--authenticate first (no attempt was allocated)"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_launch_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full readiness + regression suite**

Run:
```bash
"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_contract.py \
  mcp_server/tests/test_lm9b_p_readiness_verifier.py \
  mcp_server/tests/test_lm9b_p_readiness_probe.py \
  mcp_server/tests/test_lm9b_p_readiness_launch_gate.py \
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py -v
```
Expected: PASS — new readiness tests plus the unchanged experiment probe tests (add the required `--readiness-record` arg to any dry-run invocation those tests construct; if a pre-existing dry-run test breaks solely because the new required arg is missing, update that test to pass a `--readiness-record` path — a mechanical arg addition, not a behavior change).

- [ ] **Step 6: Commit**

```bash
git add scripts/lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_readiness_launch_gate.py
git commit -m "feat(lm9b-p): refuse experiment launch without fresh readiness record

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- Staged boundary (§3) → Tasks 6 (preflight), 7 (canary), 8 (verifier gate).
- Code topology / pure module (§4) → Task 1–5 stdlib-only module; Task 8 import-isolation test.
- Route identity + dedup (§5) → Task 2.
- Credential-source declaration (§5.1) → Task 1 (map + resolver), Task 6 (presence), tests 10/11 in Task 1.
- Canary shape (§6) → Task 3 (protocol), Task 7 (contact + content exclusion, test 9).
- Readiness record + `route_ready` (§7, §7.1) → Task 3/4; record assembly Task 6.
- Three coordinates + attribution (§8) → Task 8 refuse-before-`mkdir`; provider contact/observation belong to the unchanged experiment.
- Launch verifier equations (§9, §9.1) → Task 5 (all equations incl. request binding, freshness, presence, coverage, integrity).
- Tests 1–11 (§10) → 1 (Task 6/8), 2 (Task 7), 3 (Task 7), 4 (Task 5 param mutations), 5 (Task 5), 6 (Task 8), 7 (Task 7), 8 (Task 8), 9 (Task 7), 10 (Task 1/2), 11 (Task 1).
- Successor (§11) → no code; the new reviewed commit SHA is supplied at readiness time and re-checked at launch (Global Constraints, Task 8).

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code and exact commands.

**3. Type consistency:** `route_fingerprint`, `member_roles`, `credential_source`, `canary_protocol_fingerprint`, `record_fingerprint`, `request_fingerprint`, `verify_launch_readiness`, `derive_routes`, `READINESS_ROLE_ROUTES`, `run_canary`, `run_readiness`, `readiness_gate_ok` are used identically across tasks. `ProviderTurn`/`ProviderCallFailure` match the production `LiteLLMProvider` contract (`raw_response: bytes`, `assistant_message` dict, `failure_type`/`message`).

## Execution Handoff

Plan complete. Two execution options — Subagent-Driven (recommended) or Inline Execution — offered after review.
