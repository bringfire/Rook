# Agent Capability Recovery After `/command` Lockdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the near-term capability recovery foundation after `/command` lockdown: shared refusal envelope semantics, concrete recovery artifacts, initial audit generation, and a synthetic eval baseline.

**Architecture:** Keep native `/command` fail-closed and keep orchestration out of native routes. Add a small Python refusal-envelope helper for MCP-facing RunScript safety refusals, align native `/command` refusal payloads with the shared semantic fields, and generate markdown recovery artifacts under `docs/superpowers/capability-recovery/`. Synthetic evals are static/catalog-level in this slice; missing typed tools become ranked queue rows rather than being built here.

**Tech Stack:** Python 3.13, pytest, existing Rook MCP server module, existing native C++ command handlers, markdown documentation artifacts. No new external dependencies.

---

## Approved Spec

Implement against:

`docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md`

The spec status is now `Accepted`.

## Scope Boundary

This plan creates the recovery foundation and assessment artifacts. It does not add high-value typed tools, expand the command allowlist, or implement P2 dispatcher modal allowlisting.

Any discovered capability gap should land as a row in:

`docs/superpowers/capability-recovery/ranked-recovery-queue.md`

## File Structure

- Modify: `docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md`
  - Set status to `Accepted`.

- Create: `docs/superpowers/capability-recovery/agent-intent-map.md`
  - Top-down intent taxonomy with route coverage, feedback, owners, and verification targets.

- Create: `docs/superpowers/capability-recovery/current-tool-route-map.md`
  - Current model-facing tool catalog grouped by intent.

- Create: `docs/superpowers/capability-recovery/blocked-command-audit.md`
  - Historical/log-derived and seed blocked command observations.

- Create: `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`
  - Representative agent tasks, expected safe routes, and failure signals.

- Create: `docs/superpowers/capability-recovery/ranked-recovery-queue.md`
  - Ranked, owned recovery rows.

- Create: `mcp_server/src/rook/runscript_refusals.py`
  - Shared MCP refusal envelope builder and validator for RunScript safety refusals.

- Modify: `mcp_server/src/rook/preflight.py`
  - Use the shared envelope for `rhino_command` safety refusals.

- Modify: `mcp_server/src/rook/server.py`
  - Preserve refusal envelope fields through MCP `rhino_command` responses and add candidate typed tool advisory data where available.

- Modify: `src/RookNative/Handlers/CommandHandler.cpp`
  - Add required shared refusal-envelope fields to native `/command` uncertainty and bare-no-effect refusals.

- Modify: `mcp_server/tests/test_preflight_rhino_command_safety.py`
  - Assert MCP preflight refusal envelope semantics.

- Modify: `mcp_server/tests/test_runscript_safety_live.py`
  - Assert native live refusal envelope fields for prompt/quarantine/bare no-effect cases.

- Create: `mcp_server/tools/capability_recovery_audit.py`
  - Generates the five markdown artifacts from a curated intent seed, current tool catalog, and optional telemetry JSONL.

- Create: `mcp_server/tests/test_capability_recovery_audit.py`
  - Unit tests for artifact generation, schema completeness, and queue row validation.

- Create: `mcp_server/tests/test_agent_capability_eval_baseline.py`
  - Static eval baseline tests that verify common tasks have expected safe-route classifications or owned gap rows.

---

### Task 1: Commit Accepted Spec Status

**Files:**
- Modify: `docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md`

- [ ] **Step 1: Verify spec status is accepted**

Run:

```powershell
Select-String -Path docs\superpowers\specs\2026-05-19-agent-capability-recovery-after-command-lockdown-design.md -Pattern '^Status: Accepted$'
```

Expected: one match.

- [ ] **Step 2: Commit the status update with the plan if not already committed**

Do not stage unrelated files.

```powershell
git add docs/superpowers/specs/2026-05-19-agent-capability-recovery-after-command-lockdown-design.md
```

Expected: staged spec file only.

---

### Task 2: Shared MCP Refusal Envelope Helper

**Files:**
- Create: `mcp_server/src/rook/runscript_refusals.py`
- Test: `mcp_server/tests/test_preflight_rhino_command_safety.py`

- [ ] **Step 1: Add failing tests for the shared envelope**

Append to `mcp_server/tests/test_preflight_rhino_command_safety.py`:

```python
def test_runscript_refusal_envelope_required_fields():
    from rook.runscript_refusals import build_runscript_refusal

    response = build_runscript_refusal(
        reason="command_safety_unavailable",
        detected_command="_Line",
        safety_class="good_refusal",
        retry_allowed=False,
    )

    assert response["success"] is False
    data = response["data"]
    assert data["error"] == "run_script_safety_refusal"
    assert data["error_code"] == "run_script_safety_refusal"
    assert data["reason"] == "command_safety_unavailable"
    assert data["safety_class"] == "good_refusal"
    assert data["retry_allowed"] is False
    assert data["detected_command"] == "_Line"
    assert data["prompt_state"] == "not_checked"
    assert data["verified"] is False


def test_runscript_refusal_envelope_rejects_invalid_safety_class():
    from rook.runscript_refusals import build_runscript_refusal

    with pytest.raises(ValueError, match="invalid safety_class"):
        build_runscript_refusal(
            reason="bad",
            detected_command="_Line",
            safety_class="unsafeish",
            retry_allowed=False,
        )
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py::test_runscript_refusal_envelope_required_fields mcp_server/tests/test_preflight_rhino_command_safety.py::test_runscript_refusal_envelope_rejects_invalid_safety_class -q
```

Expected: fail because `rook.runscript_refusals` does not exist.

- [ ] **Step 3: Create the helper module**

Create `mcp_server/src/rook/runscript_refusals.py`:

```python
"""Shared RunScript safety refusal envelopes for MCP-facing code paths."""

from __future__ import annotations

from typing import Any


RUNSCRIPT_REFUSAL_ERROR = "run_script_safety_refusal"

SAFETY_CLASSES = {
    "good_refusal",
    "bad_refusal",
    "weak_refusal",
    "dangerous_recovery_blocked",
    "unknown",
}

PROMPT_STATES = {"idle", "active", "unknown", "not_checked"}


def build_runscript_refusal(
    *,
    reason: str,
    detected_command: Any = None,
    detected_intent: str | None = None,
    safety_class: str = "unknown",
    retry_allowed: bool = False,
    prompt_state: str = "not_checked",
    candidate_tools: list[dict[str, Any]] | None = None,
    missing_parameters: list[str] | None = None,
    manual_boundary: str | None = None,
    docs_hint: str | None = None,
    postcondition_hint: str | None = None,
    recovery: str | None = None,
    **extra_data: Any,
) -> dict[str, Any]:
    if safety_class not in SAFETY_CLASSES:
        raise ValueError(f"invalid safety_class: {safety_class}")
    if prompt_state not in PROMPT_STATES:
        raise ValueError(f"invalid prompt_state: {prompt_state}")
    if not isinstance(retry_allowed, bool):
        raise ValueError("retry_allowed must be a boolean")

    data: dict[str, Any] = {
        "error": RUNSCRIPT_REFUSAL_ERROR,
        "error_code": RUNSCRIPT_REFUSAL_ERROR,
        "reason": reason,
        "safety_class": safety_class,
        "retry_allowed": retry_allowed,
        "prompt_state": prompt_state,
        "verified": False,
        "recovery": recovery or "Use a typed Rook tool or a known-safe fully scripted command.",
    }
    if detected_command is not None:
        data["detected_command"] = detected_command
        data["command"] = detected_command
    if detected_intent is not None:
        data["detected_intent"] = detected_intent
    if candidate_tools is not None:
        data["candidate_tools"] = candidate_tools
    if missing_parameters is not None:
        data["missing_parameters"] = missing_parameters
        data["missing_required"] = missing_parameters
    if manual_boundary is not None:
        data["manual_boundary"] = manual_boundary
    if docs_hint is not None:
        data["docs_hint"] = docs_hint
    if postcondition_hint is not None:
        data["postcondition_hint"] = postcondition_hint
    data.update(extra_data)
    return {"success": False, "data": data}
```

- [ ] **Step 4: Run tests for the helper**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py::test_runscript_refusal_envelope_required_fields mcp_server/tests/test_preflight_rhino_command_safety.py::test_runscript_refusal_envelope_rejects_invalid_safety_class -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/runscript_refusals.py mcp_server/tests/test_preflight_rhino_command_safety.py
git commit -m "feat: add runscript refusal envelope helper"
```

---

### Task 3: MCP `rhino_command` Preflight Refusal Envelope

**Files:**
- Modify: `mcp_server/src/rook/preflight.py`
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_preflight_rhino_command_safety.py`
- Test: `mcp_server/tests/test_server_execute_safety.py`

- [ ] **Step 1: Add failing tests for preflight envelope fields**

Update existing assertions in `mcp_server/tests/test_preflight_rhino_command_safety.py` so safety refusals assert the shared fields. Add this helper:

```python
def assert_runscript_refusal(data, *, reason: str, command: str | None = None):
    assert data["error"] == "run_script_safety_refusal"
    assert data["error_code"] == "run_script_safety_refusal"
    assert data["reason"] == reason
    assert data["safety_class"] in {
        "good_refusal",
        "bad_refusal",
        "weak_refusal",
        "dangerous_recovery_blocked",
        "unknown",
    }
    assert isinstance(data["retry_allowed"], bool)
    assert data["prompt_state"] == "not_checked"
    assert data["verified"] is False
    if command is not None:
        assert data["detected_command"] == command
```

Update the unavailable-store test:

```python
def test_rejects_when_knowledge_store_unavailable():
    result = preflight_rhino_command("_Line", knowledge_store=None)

    assert result is not None
    assert result["success"] is False
    assert_runscript_refusal(
        result["data"],
        reason="command_safety_unavailable",
        command="_Line",
    )
    assert result["data"]["candidate_tools"][0]["tool"] == "rhino_create_line"
```

- [ ] **Step 2: Add failing MCP direct-call test**

Append to `mcp_server/tests/test_server_execute_safety.py`:

```python
@pytest.mark.asyncio
async def test_rhino_command_safety_refusal_preserves_shared_envelope(monkeypatch):
    from rook import server

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("rhino_command refusal must happen before call_rhino")

    monkeypatch.setattr(server, "call_rhino", fail_call_rhino)
    monkeypatch.setattr(server.command_learner, "knowledge_store", None)

    response = await server.call_tool("rhino_command", {"command": "_Line"})
    payload = json.loads(response[0].text)
    data = payload["data"]

    assert payload["success"] is False
    assert data["error_code"] == "run_script_safety_refusal"
    assert data["reason"] == "command_safety_unavailable"
    assert data["safety_class"] == "good_refusal"
    assert data["retry_allowed"] is False
    assert data["detected_command"] == "_Line"
    assert data["candidate_tools"][0]["tool"] == "rhino_create_line"
```

If `json` is not imported in this file, add `import json` at the top.

- [ ] **Step 3: Run failing tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py::test_rhino_command_safety_refusal_preserves_shared_envelope -q
```

Expected: failures on missing `error_code`, `safety_class`, `retry_allowed`, or `candidate_tools`.

- [ ] **Step 4: Update preflight to use helper**

In `mcp_server/src/rook/preflight.py`, replace the local `RUNSCRIPT_REFUSAL_ERROR` and `_runscript_safety_refusal` body with:

```python
from .runscript_refusals import RUNSCRIPT_REFUSAL_ERROR, build_runscript_refusal


def _candidate_tools_for_command(command: Any, reason: str) -> list[dict[str, Any]]:
    if not isinstance(command, str):
        return []
    normalized = command.lstrip("_-!").lower()
    if normalized == "line":
        return [
            {
                "tool": "rhino_create_line",
                "reason": "Line creation is deterministic when start and end points are supplied.",
                "required_parameters": ["start", "end"],
            }
        ]
    if normalized in {"circle", "arc", "polyline", "curve"}:
        return [
            {
                "tool": "rhino_create",
                "reason": "Use typed geometry creation with explicit parameters.",
                "required_parameters": ["type", "parameters"],
            }
        ]
    if reason == "command_safety_unavailable":
        return [
            {
                "tool": "typed_rook_tool_catalog",
                "reason": "Command safety metadata is unavailable; choose a typed tool by intent.",
                "required_parameters": ["intent-specific schema"],
            }
        ]
    return []


def _runscript_safety_refusal(
    reason: str,
    command: Any = None,
    mode: Any = None,
    **extra_data: Any,
) -> dict[str, Any]:
    missing_required = extra_data.pop("missing_required", None)
    candidate_tools = extra_data.pop(
        "candidate_tools",
        _candidate_tools_for_command(command, reason),
    )
    return build_runscript_refusal(
        reason=reason,
        detected_command=command,
        safety_class="good_refusal",
        retry_allowed=False,
        prompt_state="not_checked",
        candidate_tools=candidate_tools,
        missing_parameters=missing_required,
        mode=mode,
        **extra_data,
    )
```

Keep `RUNSCRIPT_REFUSAL_ERROR` import-compatible for existing tests/imports.

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server/src/rook/preflight.py mcp_server/src/rook/runscript_refusals.py mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py
git commit -m "feat: preserve structured runscript refusals"
```

---

### Task 4: Native `/command` Refusal Envelope Alignment

**Files:**
- Modify: `src/RookNative/Handlers/CommandHandler.cpp`
- Test: `mcp_server/tests/test_runscript_safety_live.py`

- [ ] **Step 1: Add failing live assertions for native refusal fields**

In `mcp_server/tests/test_runscript_safety_live.py`, strengthen `_assert_command_uncertain_failure`:

```python
def _assert_command_uncertain_failure(payload: dict[str, Any]) -> None:
    data = payload.get("data")
    assert payload.get("success") is False
    assert isinstance(data, dict)
    assert data.get("verified") is False
    assert data.get("executed") is not True
    assert data.get("state_uncertain") is True
    assert data.get("error_code") in {
        "native_command_interactive_prompt",
        "native_command_prompt_unknown",
        "native_command_timeout",
        "native_command_state_uncertain",
        "native_command_bare_no_effect_unverified",
    }
    assert data.get("reason")
    assert data.get("safety_class") in {"good_refusal", "unknown"}
    assert isinstance(data.get("retry_allowed"), bool)
    assert data.get("prompt_state") in {"active", "unknown", "idle", "not_checked"}
    assert (
        data.get("waitingFor")
        or data.get("error_code") in {
            "native_command_prompt_unknown",
            "native_command_timeout",
            "native_command_state_uncertain",
            "native_command_bare_no_effect_unverified",
        }
    )
```

- [ ] **Step 2: Run live collection only**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest --collect-only mcp_server/tests/test_runscript_safety_live.py -q
```

Expected: 14 tests collected.

- [ ] **Step 3: Update native refusal builders**

In `src/RookNative/Handlers/CommandHandler.cpp`, add a helper inside the anonymous namespace:

```cpp
void AddSharedRefusalEnvelope(
    nlohmann::json& data,
    const char* errorCode,
    const char* reason,
    const char* safetyClass,
    bool retryAllowed,
    const char* promptState)
{
    data["error_code"] = errorCode;
    data["reason"] = reason;
    data["safety_class"] = safetyClass;
    data["retry_allowed"] = retryAllowed;
    data["prompt_state"] = promptState;
}
```

Call this helper in:

- `BuildCommandInteractiveError`: `errorCode="native_command_interactive_prompt"`, `reason="interactive_prompt_detected"`, `safetyClass="good_refusal"`, `retryAllowed=false`, `promptState="active"`.
- `BuildCommandTimeoutError`: `errorCode="native_command_timeout"`, `reason="command_timeout"`, `safetyClass="good_refusal"`, `retryAllowed=false`, `promptState="unknown"`.
- `BuildCommandStateUncertainError`: `errorCode="native_command_state_uncertain"`, `reason="command_state_uncertain"`, `safetyClass="good_refusal"`, `retryAllowed=true`, `promptState=prompt.empty() ? "unknown" : "active"`.
- `BuildCommandPromptUnknownError`: overwrite `error_code` with `native_command_prompt_unknown`, `reason="prompt_read_unknown"`, `prompt_state="unknown"`.
- `BuildCommandBareNoEffectUnverifiedError`: overwrite `error_code` with `native_command_bare_no_effect_unverified`, `reason="bare_command_no_effect_unverified"`, `prompt_state="unknown"`.

Keep existing `code` fields for backward compatibility.

- [ ] **Step 4: Build native Release**

Run:

```powershell
cmd /c 'call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207'
```

Expected: `Build succeeded. 0 Warning(s). 0 Error(s).`

- [ ] **Step 5: Run focused non-live tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run live smoke after deploy**

Deploy Release output:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild
```

Run:

```powershell
python scripts\run_rhino_runtime_harness.py --smoke runscript-safety
python scripts\run_rhino_runtime_harness.py --smoke runscript-safety-hooks
```

Expected:

- normal smoke succeeds with `10 passed`
- hook smoke succeeds with `4 passed`
- manifests have `timed_out=false`, `unrecovered=false`, and cleanup `graceful_exit`

- [ ] **Step 7: Commit**

```powershell
git add src/RookNative/Handlers/CommandHandler.cpp mcp_server/tests/test_runscript_safety_live.py
git commit -m "feat: align native command refusal envelopes"
```

---

### Task 5: Capability Recovery Artifact Generator

**Files:**
- Create: `mcp_server/tools/capability_recovery_audit.py`
- Create: `mcp_server/tests/test_capability_recovery_audit.py`
- Create directory: `docs/superpowers/capability-recovery/`

- [ ] **Step 1: Write failing generator tests**

Create `mcp_server/tests/test_capability_recovery_audit.py`:

```python
from pathlib import Path

from mcp_server.tools.capability_recovery_audit import (
    INTENT_SEED,
    RecoveryRow,
    render_agent_intent_map,
    render_ranked_recovery_queue,
    validate_recovery_rows,
)


def test_intent_seed_covers_required_categories():
    intents = {row["intent"] for row in INTENT_SEED}
    assert "create line from two points" in intents
    assert "modify object transform" in intents
    assert "recover uncertain command state" in intents
    assert "solve Grasshopper document" in intents


def test_validate_recovery_rows_requires_owner_and_verification():
    rows = [
        RecoveryRow(
            intent="create line from two points",
            existing_typed_route="rhino_create_line",
            model_facing_tool="rhino_create_line",
            feedback_quality="strong",
            postcondition="object_ids",
            former_command_fallback="_Line",
            safety_class="good_refusal",
            gap_severity="low",
            recommended_action="no_action",
            owner="Rook MCP",
            verification_target="synthetic_eval_task",
            status="covered",
        )
    ]
    validate_recovery_rows(rows)


def test_validate_recovery_rows_rejects_missing_owner():
    rows = [
        RecoveryRow(
            intent="create circle",
            existing_typed_route="",
            model_facing_tool="",
            feedback_quality="weak",
            postcondition="",
            former_command_fallback="_Circle",
            safety_class="bad_refusal",
            gap_severity="high",
            recommended_action="typed_route_addition",
            owner="",
            verification_target="synthetic_eval_task",
            status="open",
        )
    ]
    try:
        validate_recovery_rows(rows)
    except ValueError as exc:
        assert "owner" in str(exc)
    else:
        raise AssertionError("missing owner must fail validation")


def test_rendered_artifacts_include_matrix_headers(tmp_path: Path):
    rows = [
        RecoveryRow(
            intent="create line from two points",
            existing_typed_route="rhino_create_line",
            model_facing_tool="rhino_create_line",
            feedback_quality="strong",
            postcondition="object_ids",
            former_command_fallback="_Line",
            safety_class="good_refusal",
            gap_severity="low",
            recommended_action="no_action",
            owner="Rook MCP",
            verification_target="synthetic_eval_task",
            status="covered",
        )
    ]

    intent_map = render_agent_intent_map(rows)
    queue = render_ranked_recovery_queue(rows)

    assert "| Intent | Existing typed route | Model-facing tool |" in intent_map
    assert "| Gap severity | Intent | Recommended action | Owner | Verification target | Status |" in queue
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
$env:PYTHONPATH='.;mcp_server/src'; python -m pytest mcp_server/tests/test_capability_recovery_audit.py -q
```

Expected: fail because `mcp_server.tools.capability_recovery_audit` does not exist.

- [ ] **Step 3: Create generator module**

Create `mcp_server/tools/capability_recovery_audit.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ALLOWED_ACTIONS = {
    "tool_description_fix",
    "schema_fix",
    "typed_route_addition",
    "structured_refusal_advisory",
    "safe_command_metadata",
    "manual_boundary",
    "no_action",
}

ALLOWED_VERIFICATION_TARGETS = {
    "synthetic_eval_task",
    "unit_or_integration_test",
    "live_rhino_smoke_test",
    "telemetry_query",
    "documentation_update",
}

INTENT_SEED = [
    {"intent": "create line from two points", "category": "create geometry"},
    {"intent": "create circle from center and radius", "category": "create geometry"},
    {"intent": "modify object transform", "category": "modify geometry"},
    {"intent": "select objects by type or id", "category": "select/query/measure"},
    {"intent": "measure bounding box", "category": "select/query/measure"},
    {"intent": "assign layer", "category": "organize"},
    {"intent": "assign material", "category": "materials"},
    {"intent": "add text annotation", "category": "annotate"},
    {"intent": "capture viewport image", "category": "view/capture"},
    {"intent": "import model file", "category": "import/export"},
    {"intent": "mutate block definition object", "category": "blocks"},
    {"intent": "solve Grasshopper document", "category": "Grasshopper workflows"},
    {"intent": "recover uncertain command state", "category": "recovery/state"},
]


@dataclass(frozen=True)
class RecoveryRow:
    intent: str
    existing_typed_route: str
    model_facing_tool: str
    feedback_quality: str
    postcondition: str
    former_command_fallback: str
    safety_class: str
    gap_severity: str
    recommended_action: str
    owner: str
    verification_target: str
    status: str


def validate_recovery_rows(rows: list[RecoveryRow]) -> None:
    for row in rows:
        if not row.owner:
            raise ValueError(f"owner is required for intent: {row.intent}")
        if row.recommended_action not in ALLOWED_ACTIONS:
            raise ValueError(f"invalid recommended_action for intent {row.intent}: {row.recommended_action}")
        if row.verification_target not in ALLOWED_VERIFICATION_TARGETS:
            raise ValueError(f"invalid verification_target for intent {row.intent}: {row.verification_target}")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines) + "\n"


def render_agent_intent_map(rows: list[RecoveryRow]) -> str:
    validate_recovery_rows(rows)
    return "# Agent Intent Map\n\n" + _table(
        [
            "Intent",
            "Existing typed route",
            "Model-facing tool",
            "Feedback quality",
            "Postcondition / Verification Signal",
            "Former command fallback",
            "Safety class",
            "Gap severity",
            "Recommended action",
            "Owner",
            "Verification target",
            "Status",
        ],
        [
            [
                row.intent,
                row.existing_typed_route,
                row.model_facing_tool,
                row.feedback_quality,
                row.postcondition,
                row.former_command_fallback,
                row.safety_class,
                row.gap_severity,
                row.recommended_action,
                row.owner,
                row.verification_target,
                row.status,
            ]
            for row in rows
        ],
    )


def render_ranked_recovery_queue(rows: list[RecoveryRow]) -> str:
    validate_recovery_rows(rows)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    ranked = sorted(rows, key=lambda row: severity_order.get(row.gap_severity, 99))
    return "# Ranked Recovery Queue\n\n" + _table(
        ["Gap severity", "Intent", "Recommended action", "Owner", "Verification target", "Status"],
        [
            [
                row.gap_severity,
                row.intent,
                row.recommended_action,
                row.owner,
                row.verification_target,
                row.status,
            ]
            for row in ranked
        ],
    )
```

- [ ] **Step 4: Run generator tests**

Run:

```powershell
$env:PYTHONPATH='.;mcp_server/src'; python -m pytest mcp_server/tests/test_capability_recovery_audit.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/tools/capability_recovery_audit.py mcp_server/tests/test_capability_recovery_audit.py
git commit -m "feat: add capability recovery audit generator"
```

---

### Task 6: Seed Capability Recovery Artifacts

**Files:**
- Create: `docs/superpowers/capability-recovery/agent-intent-map.md`
- Create: `docs/superpowers/capability-recovery/current-tool-route-map.md`
- Create: `docs/superpowers/capability-recovery/blocked-command-audit.md`
- Create: `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`
- Create: `docs/superpowers/capability-recovery/ranked-recovery-queue.md`
- Modify: `mcp_server/tools/capability_recovery_audit.py`
- Test: `mcp_server/tests/test_capability_recovery_audit.py`

- [ ] **Step 1: Add tests for artifact writing**

Append to `mcp_server/tests/test_capability_recovery_audit.py`:

```python
from mcp_server.tools.capability_recovery_audit import write_default_artifacts


def test_write_default_artifacts_creates_required_files(tmp_path: Path):
    write_default_artifacts(tmp_path)

    expected = {
        "agent-intent-map.md",
        "current-tool-route-map.md",
        "blocked-command-audit.md",
        "synthetic-eval-baseline.md",
        "ranked-recovery-queue.md",
    }
    assert expected == {path.name for path in tmp_path.iterdir()}
    for name in expected:
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "Agent Capability Recovery" in text or "Recovery" in text
```

- [ ] **Step 2: Implement artifact writing**

Add to `mcp_server/tools/capability_recovery_audit.py`:

```python
DEFAULT_ROWS = [
    RecoveryRow(
        intent="create line from two points",
        existing_typed_route="native create route or typed MCP create tool",
        model_facing_tool="rhino_create_line or rhino_create",
        feedback_quality="needs verification",
        postcondition="object_ids and objectsCreated",
        former_command_fallback="_Line",
        safety_class="good_refusal",
        gap_severity="medium",
        recommended_action="schema_fix",
        owner="Rook MCP",
        verification_target="synthetic_eval_task",
        status="open",
    ),
    RecoveryRow(
        intent="recover uncertain command state",
        existing_typed_route="/command/prompt and /command/cancel",
        model_facing_tool="rhino_command_interactive_prompt and rhino_command_interactive_cancel",
        feedback_quality="strong",
        postcondition="verified idle prompt and state_uncertain cleared",
        former_command_fallback="interactive start/send",
        safety_class="good_refusal",
        gap_severity="low",
        recommended_action="structured_refusal_advisory",
        owner="RookNative",
        verification_target="live_rhino_smoke_test",
        status="covered",
    ),
]


def render_current_tool_route_map(rows: list[RecoveryRow]) -> str:
    validate_recovery_rows(rows)
    return "# Current Tool Route Map\n\nAgent Capability Recovery route inventory.\n\n" + _table(
        ["Intent", "Model-facing tool", "Existing typed route", "Feedback quality", "Postcondition / Verification Signal"],
        [
            [row.intent, row.model_facing_tool, row.existing_typed_route, row.feedback_quality, row.postcondition]
            for row in rows
        ],
    )


def render_blocked_command_audit(rows: list[RecoveryRow]) -> str:
    validate_recovery_rows(rows)
    return "# Blocked Command Audit\n\nAgent Capability Recovery blocked command seed audit.\n\n" + _table(
        ["Former command fallback", "Intent", "Safety class", "Recommended action", "Status"],
        [
            [row.former_command_fallback, row.intent, row.safety_class, row.recommended_action, row.status]
            for row in rows
            if row.former_command_fallback
        ],
    )


def render_synthetic_eval_baseline(rows: list[RecoveryRow]) -> str:
    validate_recovery_rows(rows)
    return "# Synthetic Eval Baseline\n\nAgent Capability Recovery eval baseline.\n\n" + _table(
        ["Intent", "Expected route", "Disallowed route", "Success signal"],
        [
            [row.intent, row.model_facing_tool or row.existing_typed_route, "raw rhino_command", row.postcondition]
            for row in rows
        ],
    )


def write_default_artifacts(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(DEFAULT_ROWS)
    validate_recovery_rows(rows)
    artifacts = {
        "agent-intent-map.md": render_agent_intent_map(rows),
        "current-tool-route-map.md": render_current_tool_route_map(rows),
        "blocked-command-audit.md": render_blocked_command_audit(rows),
        "synthetic-eval-baseline.md": render_synthetic_eval_baseline(rows),
        "ranked-recovery-queue.md": render_ranked_recovery_queue(rows),
    }
    for name, text in artifacts.items():
        (output_dir / name).write_text(text, encoding="utf-8")
```

- [ ] **Step 3: Add CLI entrypoint**

Add to bottom of `mcp_server/tools/capability_recovery_audit.py`:

```python
def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "docs" / "superpowers" / "capability-recovery"
    write_default_artifacts(output_dir)
    print(f"Wrote capability recovery artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and generate artifacts**

Run:

```powershell
$env:PYTHONPATH='.;mcp_server/src'; python -m pytest mcp_server/tests/test_capability_recovery_audit.py -q
python mcp_server/tools/capability_recovery_audit.py
```

Expected:

- tests pass
- five markdown files are written under `docs/superpowers/capability-recovery/`

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/tools/capability_recovery_audit.py mcp_server/tests/test_capability_recovery_audit.py docs/superpowers/capability-recovery
git commit -m "docs: seed agent capability recovery artifacts"
```

---

### Task 7: Synthetic Agent Eval Baseline Tests

**Files:**
- Create: `mcp_server/tests/test_agent_capability_eval_baseline.py`
- Modify: `docs/superpowers/capability-recovery/synthetic-eval-baseline.md`
- Modify: `docs/superpowers/capability-recovery/ranked-recovery-queue.md`

- [ ] **Step 1: Add static eval baseline test**

Create `mcp_server/tests/test_agent_capability_eval_baseline.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "superpowers" / "capability-recovery" / "synthetic-eval-baseline.md"
QUEUE = ROOT / "docs" / "superpowers" / "capability-recovery" / "ranked-recovery-queue.md"


def test_synthetic_eval_baseline_blocks_raw_command_route_for_common_tasks():
    text = BASELINE.read_text(encoding="utf-8")

    assert "raw rhino_command" in text
    assert "create line from two points" in text
    assert "recover uncertain command state" in text


def test_high_severity_queue_rows_have_owner_and_verification_columns():
    text = QUEUE.read_text(encoding="utf-8")

    assert "| Gap severity | Intent | Recommended action | Owner | Verification target | Status |" in text
    for line in text.splitlines():
        if not line.startswith("| high |"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert cells[3], line
        assert cells[4], line
```

- [ ] **Step 2: Run tests**

Run:

```powershell
$env:PYTHONPATH='.;mcp_server/src'; python -m pytest mcp_server/tests/test_agent_capability_eval_baseline.py -q
```

Expected: pass if Task 6 artifacts exist.

- [ ] **Step 3: Add at least one high-severity seed row if none exist**

If the queue has no high-severity row, add this row through `DEFAULT_ROWS` in `mcp_server/tools/capability_recovery_audit.py`, regenerate artifacts, and rerun the test:

```python
RecoveryRow(
    intent="create circle from center and radius",
    existing_typed_route="needs route verification",
    model_facing_tool="needs discoverable typed tool",
    feedback_quality="weak",
    postcondition="object_ids and radius/center echo",
    former_command_fallback="_Circle",
    safety_class="bad_refusal",
    gap_severity="high",
    recommended_action="typed_route_addition",
    owner="Rook MCP",
    verification_target="synthetic_eval_task",
    status="open",
)
```

- [ ] **Step 4: Commit**

```powershell
git add mcp_server/tests/test_agent_capability_eval_baseline.py mcp_server/tools/capability_recovery_audit.py docs/superpowers/capability-recovery
git commit -m "test: add agent capability eval baseline"
```

---

### Task 8: Final Verification And PR Update

**Files:**
- No source changes expected unless verification reveals a bug.

- [ ] **Step 1: Run focused Python suite**

Run:

```powershell
$env:PYTHONPATH='.;mcp_server/src'; python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_execute_safety.py mcp_server/tests/test_capability_recovery_audit.py mcp_server/tests/test_agent_capability_eval_baseline.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run live collection**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -m pytest --collect-only mcp_server/tests/test_runscript_safety_live.py -q
```

Expected: 14 tests collected.

- [ ] **Step 3: Run native build if Task 4 changed C++**

Run:

```powershell
cmd /c 'call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207'
```

Expected: `Build succeeded. 0 Warning(s). 0 Error(s).`

- [ ] **Step 4: Run live smoke if Task 4 changed C++**

Deploy and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild
python scripts\run_rhino_runtime_harness.py --smoke runscript-safety
python scripts\run_rhino_runtime_harness.py --smoke runscript-safety-hooks
```

Expected:

- normal smoke succeeds
- hook smoke succeeds
- manifests have `timed_out=false`, `unrecovered=false`, cleanup `graceful_exit`

- [ ] **Step 5: Run diff and status checks**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- `git diff --check` exits 0
- no dirty files except any pre-existing unrelated `knowledge/gh/component_observations.json`

- [ ] **Step 6: Push and update PR**

Run:

```powershell
git push origin codex/runscript-p0-p1-containment
```

Update PR #161 with:

- spec accepted
- refusal envelope implementation status
- capability recovery artifact paths
- synthetic eval baseline status
- any live smoke/build results rerun in this plan

---

## Self-Review Checklist

- Spec coverage:
  - `/command` fail-closed is preserved by not loosening native gates.
  - Structured refusal contract is implemented in MCP and aligned in native.
  - Typed RunScript-backed routes and safe `/command` metadata remain separate categories.
  - Artifact paths match the accepted spec.
  - Every queue row has owner and verification target.

- Placeholder scan:
  - No step should contain incomplete markers or an unspecified "add tests" instruction.

- Verification:
  - Python focused suite must pass.
  - Native Release build and live smoke must be rerun if native C++ is modified.
  - `git diff --check` must pass before final handoff.
