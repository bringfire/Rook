# LM9B-P Readiness Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a staged, operator-error-proof readiness boundary (local preflight → explicitly-approved experiment-content-free canary → sealed readiness record → pure refuse-before-allocation launch verifier) in front of the unchanged one-shot LM9B-P Planner-transfer experiment, so a missing or non-functional credential/access fault is caught operationally instead of consuming an attempt identity.

**Architecture — designed outward from the irreversible transition.** The whole slice is anchored by ONE proof-carrying vertical witness (Task 1) that walks a complete transaction through the *real* experiment transmit entry point with fake providers and an injected clock. Routes are always derived from the exact launch configuration; timestamps receipt the events they record; the guarded `mkdir` is exercised, not just a helper. Tasks 2–4 harden that witness with focused unit matrices.

Three code surfaces: a **pure contract module** (`scripts/lm9b_p_readiness_contract.py`, stdlib-only), a **disposable readiness probe** (`scripts/lm9b_p_readiness_probe.py`, owns provider contact), and the **experiment CLI** (`scripts/lm9b_p_planner_recipe_transfer_probe.py`, imports only the pure contract; refuse-before-`mkdir` gate).

**Tech Stack:** Python 3.10/3.12, pytest, LiteLLM 1.89.4 (production adapter, contacted only under `--authenticate`), stdlib `hashlib`/`json`/`datetime`/`dataclasses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-lm9b-p-readiness-boundary-design.md` (authoritative).
- Base: worktree `codex/lm9b-p-readiness-boundary` on `origin/main` `dfd90659`.
- `FROZEN_MAX_AGE_S = 600` seconds — frozen in the module, never operator-set.
- Credential-source declaration is a closed two-entry map, names only, verified vs installed LiteLLM 1.89.4: `("openai","gpt-5.4") -> ("OPENAI_API_KEY",)`; `("gemini","gemini/gemini-3.1-pro-preview") -> ("GOOGLE_API_KEY","GEMINI_API_KEY")`. Presence = at least one declared name set.
- Canonical Planner pin: the experiment refuses unless `--planner-model` and `--planner-evaluator-model` both equal `gpt-5.4`.
- The pure contract imports **stdlib only** — never `litellm`, never `lm9b_p_readiness_probe`, never `rook.*` at module top level. `api_key_env_for_model` is passed in / deferred, not imported by the contract.
- Do **not** modify `model_profiles.py`; do **not** change frozen model IDs.
- `--readiness-record` is required **only with `--transmit`**; dry-run behavior unchanged. Readiness failure never consumes a scientific attempt; credential check precedes readiness-root creation.
- **Test command** (from worktree root, populated main-checkout venv):
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

### Task 1: Vertical readiness witness through the real transmit boundary — ✅ COMPLETE (`146b1b58`)

Reviewer-approved (independently reproduced 367 passed). Implemented as built, not as the earlier pre-execution sketch. Authoritative source is the commit; this is the reconciled summary.

**Files delivered:**
- `scripts/lm9b_p_readiness_contract.py` (pure, stdlib-only): `FROZEN_MAX_AGE_S`, `SCHEMA_ID`, `ReadinessError`, `canonical_fingerprint`, `CREDENTIAL_SOURCE_DECLARATIONS`, `resolve_credential_source`, `provider_of`, `RoleRoute`/`DistinctRoute`/`RouteManifest`, `CANONICAL_ROLE_MODELS`, `role_routes_from_models`, `derive_routes`, canary constants + `canary_protocol`/`canary_protocol_fingerprint`, `build_canary_request`/`request_fingerprint`, `route_ready`, `record_fingerprint`, `LaunchDecision`, `verify_launch_readiness(*, record, manifest, head_sha, now_iso, credential_present)`.
- `scripts/lm9b_p_readiness_probe.py` (disposable): `HELPER`, `system_clock`, `credential_presence`, `default_provider_factory`, `run_canary(route, provider, *, clock)`, `assemble_record`, `run_readiness(*, run_root, head_sha, environ, authenticate, provider_factory, clock, models)`, `main`.
- `scripts/lm9b_p_planner_recipe_transfer_probe.py` (modified): `import lm9b_p_readiness_contract as READINESS`; `import os`; `CliAttemptConfig.readiness_record: Path | None = None`; canonical Planner pin + `--readiness-record` (required only with `--transmit`) in `parse_cli_args`; `_readiness_now_iso` (monkeypatchable clock), `_launch_models`, `_readiness_manifest` (deferred `api_key_env_for_model` import), `readiness_gate_ok`; and the refuse-before-`mkdir` gate at the top of `_execute_transmitted_attempt`.
- `mcp_server/tests/test_lm9b_p_readiness_witness.py` (9 tests): valid record reaches allocation + provider construction (`TerminalControlFailureResult`, `provider_construction`/`planner`); manifest-binding drift, staleness, credential absence each refuse before allocation; canonical Planner pin `SystemExit`; `--transmit` without `--readiness-record` rejected; direct execution without a record refuses before allocation; dry run needs none; import isolation (experiment CLI import pulls no `lm9b_p_readiness_probe`).
- `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py` (modified): shared authentic passing-readiness fixture `_install_passing_readiness` + `_canonical_cli_args(..., readiness_record=...)`; 13 pre-existing transmit-path tests reconciled (real record for downstream execution tests; placeholder arg for guard-first / `_execute`-patched tests).

**Verification at commit:** witness 9 + experiment probe 176 + support/artifacts/constructive-witness adjacent = 367 passed; `py_compile` and `git diff --check` clean.

Note: the canonical Planner pin and dry-run/`--readiness-record` behavior are proven inside the Task 1 witness, so they are **not** repeated as a separate task.

---

### Task 2: Verifier equation matrix + schema-ID guard

The contract implements the verifier from Task 1; this task adds the explicit refusal matrix and the one new code guard (`schema_id`).

**Files:**
- Modify: `scripts/lm9b_p_readiness_contract.py` (add the `schema_id` check)
- Test: `mcp_server/tests/test_lm9b_p_readiness_verifier.py`

**Interfaces:** Consumes `verify_launch_readiness`, `derive_routes`, `record_fingerprint`, `request_fingerprint`, `canary_protocol_fingerprint`, `SCHEMA_ID`, `FROZEN_MAX_AGE_S`.

- [ ] **Step 1: Write the matrix test** (prepend `_load_script`; one refusal per equation, including `schema_id`)

```python
import copy, pytest
C = _load_script("lm9b_p_readiness_contract")
HEAD = "d" * 40
MODELS = dict(C.CANONICAL_ROLE_MODELS)

def _manifest():
    return C.derive_routes(C.role_routes_from_models(MODELS), lambda _m: None)

def _fresh(now="2026-07-21T12:00:10Z", observed="2026-07-21T12:00:05Z"):
    m = _manifest()
    rows = [{"route_fingerprint": r.route_fingerprint, "member_roles": list(r.member_roles),
             "observed_at": observed, "request_fingerprint": C.request_fingerprint(r),
             "outcome": {"kind": "model_response", "assistant_present": True,
                 "tool_calls": [{"name": "ack", "arguments": '{"ok": true}'}],
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

def _reseal(rec):
    rec["record_fingerprint"] = C.record_fingerprint(rec); return rec

def test_happy_path_permits():
    assert _verify(_fresh()) is True

def test_schema_id_mismatch_refuses():
    r = _fresh(); r["schema_id"] = "lm9b_p.readiness_record:v2"; assert _verify(_reseal(r)) is False

def test_sha_mismatch_refuses():
    r = _fresh(); r["reviewed_commit_sha"] = "e"*40; assert _verify(_reseal(r)) is False

def test_manifest_fp_mismatch_refuses():
    r = _fresh(); r["route_manifest_fingerprint"] = "sha256:x"; assert _verify(_reseal(r)) is False

def test_record_fp_mismatch_refuses():
    r = _fresh(); r["record_fingerprint"] = "sha256:x"; assert _verify(r) is False

def test_protocol_fp_mismatch_refuses():
    r = _fresh(); r["canary_protocol_fingerprint"] = "sha256:x"; assert _verify(_reseal(r)) is False

def test_max_age_field_mismatch_refuses():
    r = _fresh(); r["max_age_seconds"] = 1200; assert _verify(_reseal(r)) is False

def test_missing_route_refuses():
    r = _fresh(); r["routes"] = r["routes"][:1]; assert _verify(_reseal(r)) is False

def test_duplicate_route_refuses():
    r = _fresh(); r["routes"] = [r["routes"][0], copy.deepcopy(r["routes"][0])]; assert _verify(_reseal(r)) is False

def test_member_roles_mismatch_refuses():
    r = _fresh(); r["routes"][0]["member_roles"] = ["planner"]; assert _verify(_reseal(r)) is False

def test_request_binding_mismatch_refuses():
    r = _fresh(); r["routes"][0]["request_fingerprint"] = "sha256:x"; assert _verify(_reseal(r)) is False

def test_stale_record_refuses():
    assert _verify(_fresh(now="2026-07-21T12:00:00Z"), now="2026-07-21T12:20:00Z") is False

def test_future_record_refuses():
    assert _verify(_fresh(now="2026-07-21T12:10:00Z"), now="2026-07-21T12:00:00Z") is False

def test_stale_route_observed_at_refuses():
    assert _verify(_fresh(now="2026-07-21T12:00:10Z", observed="2026-07-21T11:40:00Z")) is False

def test_completed_precedes_observed_refuses():
    r = _fresh(now="2026-07-21T12:00:00Z", observed="2026-07-21T12:00:30Z")
    assert _verify(_reseal(r), now="2026-07-21T12:00:31Z") is False

def test_credential_absent_refuses():
    r = _fresh(); pres = {row["route_fingerprint"]: True for row in r["routes"]}
    pres[r["routes"][0]["route_fingerprint"]] = False; assert _verify(r, present=pres) is False

def test_route_unready_refuses():
    r = _fresh(); r["routes"][0]["outcome"]["kind"] = "transport_failure"; assert _verify(_reseal(r)) is False
```

- [ ] **Step 2: Run — the `schema_id` case fails, the rest pass**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_verifier.py -v`
Expected: `test_schema_id_mismatch_refuses` FAILS (guard not yet present); all others PASS.

- [ ] **Step 3: Add the `schema_id` guard**

In `verify_launch_readiness`, alongside the other integrity checks (before the freshness block):

```python
    if record.get("schema_id") != SCHEMA_ID:
        fail("schema_id mismatch")
```

- [ ] **Step 4: Run to verify all pass**

Run: `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_verifier.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm9b_p_readiness_contract.py mcp_server/tests/test_lm9b_p_readiness_verifier.py
git commit -m "feat(lm9b-p): verifier refusal matrix and schema-id guard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `route_ready` matrix and credential-source resolver (spec tests 10/11)

**Files:**
- Test: `mcp_server/tests/test_lm9b_p_readiness_contract_units.py`

**Interfaces:** Consumes `route_ready`, `resolve_credential_source`, `derive_routes`, `CREDENTIAL_SOURCE_DECLARATIONS`, `RoleRoute`.

- [ ] **Step 1: Write the tests**

```python
import pytest
C = _load_script("lm9b_p_readiness_contract")

def _ok_row():
    return {"outcome": {"kind": "model_response", "assistant_present": True,
        "tool_calls": [{"name": "ack", "arguments": '{"ok": true}'}]}}

def test_route_ready_accepts_conforming():
    assert C.route_ready(_ok_row()) is True

@pytest.mark.parametrize("mut", [
    lambda o: o.update(kind="transport_failure"),
    lambda o: o.update(assistant_present=False),
    lambda o: o.update(tool_calls=[]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": '{"ok": true}'}]*2),
    lambda o: o.update(tool_calls=[{"name": "no", "arguments": '{"ok": true}'}]),
    lambda o: o.update(tool_calls=[{"name": "ack", "arguments": '{"ok": false}'}]),
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

### Task 4: Probe behavior — capture, approval/cardinality, ordering, content exclusion

**Files:**
- Test: `mcp_server/tests/test_lm9b_p_readiness_probe.py`

**Interfaces:** Consumes probe `run_canary`, `run_readiness`, `credential_presence`, `assemble_record`; contract `route_ready`, `request_fingerprint`, `build_canary_request`; `lm9b_c_compiler_sufficiency_probe.ProviderTurn`/`ProviderCallFailure`.

- [ ] **Step 1: Write the tests**

```python
import json, pytest
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
                    "function": {"name": "ack", "arguments": '{"ok": true}'}}]},
            usage={}, provider_metadata={})
    return _call

def _raising_provider(route):
    def _call(req):
        raise LM9BC.ProviderCallFailure(failure_type="InternalServerError",
            message="boom", raw_request=b"{}", raw_error=b"{}")
    return _call

def _route0():
    return C.derive_routes(C.role_routes_from_models(C.CANONICAL_ROLE_MODELS), lambda m: None).routes[0]

def test_success_row_ready_and_bound():
    route = _route0(); row = P.run_canary(route, _ok_provider(route), clock=_Clock())
    assert row["outcome"]["kind"] == "model_response" and C.route_ready(row)
    assert row["request_fingerprint"] == C.request_fingerprint(route)

def test_transport_failure_row():
    route = _route0(); row = P.run_canary(route, _raising_provider(route), clock=_Clock())
    assert row["outcome"]["kind"] == "transport_failure"
    assert row["outcome"]["classification"] == "InternalServerError"
    assert C.route_ready(row) is False

def test_no_authenticate_no_contact(tmp_path):
    made = []
    def factory(r): made.append(r); return _ok_provider(r)
    rec = P.run_readiness(run_root=tmp_path/"r", head_sha="d"*40,
        environ={"OPENAI_API_KEY":"x","GEMINI_API_KEY":"y"}, authenticate=False,
        provider_factory=factory, clock=_Clock())
    assert made == [] and rec["routes"] == []

def test_authenticate_contacts_each_route_once_and_orders_time(tmp_path):
    counts = {}
    def factory(r):
        counts.setdefault(r.route_fingerprint, 0); return _ok_provider(r)
    rec = P.run_readiness(run_root=tmp_path/"r", head_sha="d"*40,
        environ={"OPENAI_API_KEY":"x","GEMINI_API_KEY":"y"}, authenticate=True,
        provider_factory=factory, clock=_Clock())
    assert len(rec["routes"]) == 2
    assert rec["completed_at"] >= max(row["observed_at"] for row in rec["routes"])

def test_missing_credential_leaves_no_directory(tmp_path):
    root = tmp_path/"r"
    with pytest.raises(C.ReadinessError):
        P.run_readiness(run_root=root, head_sha="d"*40, environ={"OPENAI_API_KEY":"x"},
            authenticate=True, provider_factory=_ok_provider, clock=_Clock())
    assert not root.exists()

def test_canary_request_excludes_experiment_content():
    blob = json.dumps(C.build_canary_request(_route0())).lower()
    for f in ("brief","authority","r01","rubric","recipe","planner_graph"):
        assert f not in blob
```

- [ ] **Step 2: Run** — `"$PY" -m pytest mcp_server/tests/test_lm9b_p_readiness_probe.py -v` → PASS.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_lm9b_p_readiness_probe.py
git commit -m "test(lm9b-p): canary capture, approval/cardinality, ordering, content exclusion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Final verification

- [ ] **Run the whole readiness + experiment surface green**

```bash
"$PY" -m pytest \
  mcp_server/tests/test_lm9b_p_readiness_witness.py \
  mcp_server/tests/test_lm9b_p_readiness_verifier.py \
  mcp_server/tests/test_lm9b_p_readiness_contract_units.py \
  mcp_server/tests/test_lm9b_p_readiness_probe.py \
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py \
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py -v
"$PY" -m py_compile scripts/lm9b_p_readiness_contract.py scripts/lm9b_p_readiness_probe.py
git diff --check
```

Expected: all green; `py_compile` and `git diff --check` clean.

## Self-Review

**Spec + P1/P2 coverage:** vertical witness through the real boundary (Task 1 ✅); identity binding + Planner pin (Task 1); timestamp ordering + credential-before-root (Task 1 / Task 4); real boundary enforcement + import isolation (Task 1); `--readiness-record` only with `--transmit` and dry-run (Task 1); verifier equations incl. `schema_id` (Task 2); declaration + tests 10/11 (Task 3); canary/route_ready (Tasks 1/3/4).

**Placeholder scan:** no TBD/TODO; every code step shows complete code and exact commands.

**Type consistency:** `verify_launch_readiness(record, manifest, head_sha, now_iso, credential_present)`, `derive_routes(role_routes, helper)`, `role_routes_from_models`, `run_readiness(..., clock, models)`, `run_canary(route, provider, *, clock)` are consistent across tasks and match the committed Task 1 source.
