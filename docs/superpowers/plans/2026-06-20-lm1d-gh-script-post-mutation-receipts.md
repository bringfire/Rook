# LM1D GH Script Post-Mutation Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add additive `data["script_receipt"]` evidence to structured GH script create/update results so local models can distinguish mutation, verification, artifact state, and repair anchors.

**Architecture:** Add a pure `gh_script_receipts.py` module that derives receipt dictionaries from facts gathered by existing server helpers. Wire receipts into `_execute_gh_create_script(...)` and `_execute_gh_update_script(...)` only after structured post-mutation data exists; keep early string failures, dispatcher behavior, ChatRunner behavior, public MCP wire compatibility, and `gh_set_script` unchanged.

**Tech Stack:** Python 3, pytest, existing Rook MCP server helpers, mocked `call_rhino`, existing `ToolResultView` adapter tests.

---

## Scope Guardrails

This plan implements only the approved LM1D spec:

- No `gh_set_script` changes.
- No PlanGraph.
- No LM2 capability registry.
- No public MCP wire-shape migration.
- No universal result-envelope redesign.
- No generic result ontology across all tools.
- No Roslyn or full C# compilation.
- No Python preflight, Python wrapper changes, or Python-specific repair semantics.
- No output-assignment hard reject.
- No ChatRunner event wiring or prompt behavior change.
- No live Rhino dependency for the first implementation tests.
- No conversion of existing early string failures into dict-shaped envelopes.

If implementation pressure points toward any of those, stop and ask for review.

---

## File Structure

- Create `mcp_server/src/rook/gh_script_receipts.py`
  - Owns pure receipt builder functions.
  - Owns verification/artifact derivation.
  - Owns repair-anchor construction.
  - Has no Rhino, server, dispatcher, ChatRunner, or MCP imports.

- Create `mcp_server/tests/test_gh_script_receipts.py`
  - Pure unit tests for receipt derivation.
  - No mocked Rhino needed.
  - Tests version, verification status precedence, count semantics, artifact derivation, warnings policy, and repair-anchor diagnostics.

- Modify `mcp_server/src/rook/server.py`
  - Import receipt builders.
  - Add a small create verification summary helper that distinguishes measured target diagnostics from unavailable `/gh/errors`.
  - Track update verification method (`gh_errors`, `gh_snapshot_fallback`, or `none`) while preserving existing flat fields.
  - Attach `data["script_receipt"]` only on structured post-mutation create/update data.

- Modify `mcp_server/tests/test_server_contract_hardening.py`
  - Add non-live create/update receipt tests using mocked `call_rhino`.
  - Assert old fields remain present.
  - Assert early string failures remain string-shaped and receipt-free.

- Modify `mcp_server/tests/test_rookchat_tool_contracts.py`
  - Add a narrow compatibility regression proving `normalize_tool_result(...)` still classifies top-level truth correctly when `script_receipt` is present.

---

## Task 1: Add Failing Pure Receipt Tests

**Files:**
- Create: `mcp_server/tests/test_gh_script_receipts.py`

- [ ] **Step 1: Write pure helper tests**

Create `mcp_server/tests/test_gh_script_receipts.py` with this content:

```python
from __future__ import annotations

from rook.gh_script_receipts import (
    build_script_receipt,
    derive_artifact_status,
    derive_verification,
)


def _base_receipt_kwargs(**overrides):
    kwargs = {
        "operation": "update",
        "language": "csharp",
        "mutation_status": "written",
        "mutation_method": "gh_script_write",
        "component_guid": "script-guid",
        "mode_used": "body",
        "wrapped": True,
        "pins_in": [{"name": "R", "type": "double"}],
        "pins_out": [{"name": "A", "type": "double"}],
        "input_code_length": 6,
        "prepared_source_length": 900,
        "full_source_detected": False,
        "component_errors": [],
        "component_warnings": [],
        "unrelated_error_count": 0,
        "unrelated_warning_count": 0,
        "verification_method": "gh_errors",
    }
    kwargs.update(overrides)
    return kwargs


def test_derive_verification_passed_uses_measured_zero_counts():
    verification = derive_verification(
        component_errors=[],
        component_warnings=[],
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_errors",
    )

    assert verification == {
        "status": "passed",
        "method": "gh_errors",
        "target_error_count": 0,
        "target_warning_count": 0,
        "unrelated_error_count": 0,
        "unrelated_warning_count": 0,
        "note": None,
    }


def test_derive_verification_failed_counts_target_errors_and_warnings():
    verification = derive_verification(
        component_errors=["The name X does not exist"],
        component_warnings=["Unused variable"],
        unrelated_error_count=2,
        unrelated_warning_count=1,
        method="gh_errors",
    )

    assert verification["status"] == "failed"
    assert verification["method"] == "gh_errors"
    assert verification["target_error_count"] == 1
    assert verification["target_warning_count"] == 1
    assert verification["unrelated_error_count"] == 2
    assert verification["unrelated_warning_count"] == 1


def test_derive_verification_deferred_wins_and_uses_unknown_counts():
    verification = derive_verification(
        component_errors=["stale should not matter"],
        component_warnings=["stale should not matter"],
        unrelated_error_count=3,
        unrelated_warning_count=4,
        method="gh_errors",
        deferred=True,
        note="Solver is locked.",
    )

    assert verification == {
        "status": "deferred",
        "method": "none",
        "target_error_count": None,
        "target_warning_count": None,
        "unrelated_error_count": None,
        "unrelated_warning_count": None,
        "note": "Solver is locked.",
    }


def test_derive_verification_not_requested_wins_after_deferred():
    verification = derive_verification(
        component_errors=["stale should not matter"],
        component_warnings=[],
        unrelated_error_count=1,
        unrelated_warning_count=0,
        method="gh_errors",
        not_requested=True,
        note="check_errors was false.",
    )

    assert verification["status"] == "not_requested"
    assert verification["method"] == "none"
    assert verification["target_error_count"] is None
    assert verification["target_warning_count"] is None
    assert verification["unrelated_error_count"] is None
    assert verification["unrelated_warning_count"] is None
    assert verification["note"] == "check_errors was false."


def test_derive_verification_unavailable_uses_attempted_method_and_unknown_counts():
    verification = derive_verification(
        component_errors=[],
        component_warnings=[],
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_snapshot_fallback",
        unavailable_note="Component C1 not found in /gh/snapshot",
    )

    assert verification == {
        "status": "unavailable",
        "method": "gh_snapshot_fallback",
        "target_error_count": None,
        "target_warning_count": None,
        "unrelated_error_count": None,
        "unrelated_warning_count": None,
        "note": "Component C1 not found in /gh/snapshot",
    }


def test_derive_artifact_status_mapping_and_warning_policy():
    assert derive_artifact_status("create", "passed") == "usable"
    assert derive_artifact_status("update", "passed") == "usable"
    assert derive_artifact_status("create", "failed") == "created_with_errors"
    assert derive_artifact_status("update", "failed") == "written_with_errors"
    assert derive_artifact_status("create", "deferred") == "verification_pending"
    assert derive_artifact_status("update", "not_requested") == "verification_pending"
    assert derive_artifact_status("create", "unavailable") == "unknown"


def test_build_script_receipt_contains_version_mutation_verification_and_repair_anchor():
    receipt = build_script_receipt(**_base_receipt_kwargs(
        component_errors=["Cannot convert Box to Brep"],
        component_warnings=["Possible null"],
        recovery_hint="Call gh_set_script_pins first.",
        requested_guid="C1",
    ))

    assert receipt["version"] == 1
    assert receipt["operation"] == "update"
    assert receipt["language"] == "csharp"
    assert receipt["mutation"] == {
        "status": "written",
        "method": "gh_script_write",
        "component_guid": "script-guid",
        "note": None,
    }
    assert receipt["verification"]["status"] == "failed"
    assert receipt["artifact_status"] == "written_with_errors"
    assert receipt["repair_anchor"] == {
        "component_guid": "script-guid",
        "requested_guid": "C1",
        "language": "csharp",
        "mode_used": "body",
        "wrapped": True,
        "pins_in": [{"name": "R", "type": "double"}],
        "pins_out": [{"name": "A", "type": "double"}],
        "source_shape": {
            "input_code_length": 6,
            "prepared_source_length": 900,
            "full_source_detected": False,
        },
        "target_errors": ["Cannot convert Box to Brep"],
        "target_warnings": ["Possible null"],
        "recovery_hint": "Call gh_set_script_pins first.",
    }


def test_build_script_receipt_omits_requested_guid_when_not_useful():
    receipt = build_script_receipt(**_base_receipt_kwargs(
        requested_guid="script-guid",
    ))

    assert "requested_guid" not in receipt["repair_anchor"]


def test_build_script_receipt_includes_requested_guid_when_caller_used_short_id():
    receipt = build_script_receipt(**_base_receipt_kwargs(
        requested_guid="C1",
        component_guid="C1",
        include_requested_guid=True,
    ))

    assert receipt["repair_anchor"]["requested_guid"] == "C1"


def test_build_script_receipt_uses_none_diagnostics_when_verification_unknown():
    receipt = build_script_receipt(**_base_receipt_kwargs(
        deferred=True,
        verification_note="Solver locked.",
    ))

    assert receipt["verification"]["status"] == "deferred"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None
    assert receipt["artifact_status"] == "verification_pending"
```

- [ ] **Step 2: Run helper tests and verify they fail**

Run:

```powershell
python -m pytest -p no:cacheprovider mcp_server/tests/test_gh_script_receipts.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rook.gh_script_receipts'`.

Do not commit yet. These are intentionally failing tests until Task 2 implements the helper.

---

## Task 2: Implement Pure Receipt Helper

**Files:**
- Create: `mcp_server/src/rook/gh_script_receipts.py`
- Test: `mcp_server/tests/test_gh_script_receipts.py`

- [ ] **Step 1: Add the helper module**

Create `mcp_server/src/rook/gh_script_receipts.py` with this content:

```python
from __future__ import annotations

from typing import Any, Literal, Sequence


Operation = Literal["create", "update"]
MutationStatus = Literal["created", "written", "failed", "not_attempted"]
MutationMethod = Literal["gh_create_component_then_script", "gh_script_write"]
VerificationStatus = Literal["passed", "failed", "deferred", "unavailable", "not_requested"]
VerificationMethod = Literal["gh_errors", "gh_snapshot_fallback", "none"]
ArtifactStatus = Literal[
    "usable",
    "created_with_errors",
    "written_with_errors",
    "verification_pending",
    "unknown",
]


def _copy_pin_list(value: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    return [dict(pin) for pin in value if isinstance(pin, dict)]


def _diagnostics(value: Sequence[Any] | None) -> list[Any]:
    if value is None:
        return []
    return list(value)


def _unknown_count(status: VerificationStatus) -> bool:
    return status in ("deferred", "unavailable", "not_requested")


def derive_verification(
    *,
    component_errors: Sequence[Any] | None,
    component_warnings: Sequence[Any] | None,
    unrelated_error_count: int | None,
    unrelated_warning_count: int | None,
    method: VerificationMethod,
    deferred: bool = False,
    not_requested: bool = False,
    unavailable_note: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Derive target-scoped verification evidence for a GH script receipt."""
    if deferred:
        status: VerificationStatus = "deferred"
        return {
            "status": status,
            "method": "none",
            "target_error_count": None,
            "target_warning_count": None,
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "note": note,
        }

    if not_requested:
        status = "not_requested"
        return {
            "status": status,
            "method": "none",
            "target_error_count": None,
            "target_warning_count": None,
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "note": note,
        }

    if unavailable_note:
        status = "unavailable"
        return {
            "status": status,
            "method": method,
            "target_error_count": None,
            "target_warning_count": None,
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "note": unavailable_note,
        }

    errors = _diagnostics(component_errors)
    warnings = _diagnostics(component_warnings)
    status = "failed" if errors else "passed"
    return {
        "status": status,
        "method": method,
        "target_error_count": len(errors),
        "target_warning_count": len(warnings),
        "unrelated_error_count": unrelated_error_count if unrelated_error_count is not None else 0,
        "unrelated_warning_count": unrelated_warning_count if unrelated_warning_count is not None else 0,
        "note": note,
    }


def derive_artifact_status(
    operation: Operation,
    verification_status: VerificationStatus,
) -> ArtifactStatus:
    if verification_status == "passed":
        return "usable"
    if verification_status == "failed":
        return "created_with_errors" if operation == "create" else "written_with_errors"
    if verification_status in ("deferred", "not_requested"):
        return "verification_pending"
    return "unknown"


def build_script_receipt(
    *,
    operation: Operation,
    language: str,
    mutation_status: MutationStatus,
    mutation_method: MutationMethod,
    component_guid: str,
    mode_used: str | None,
    wrapped: bool | None,
    pins_in: Sequence[dict[str, Any]] | None,
    pins_out: Sequence[dict[str, Any]] | None,
    input_code_length: int,
    prepared_source_length: int,
    full_source_detected: bool,
    component_errors: Sequence[Any] | None,
    component_warnings: Sequence[Any] | None,
    unrelated_error_count: int | None,
    unrelated_warning_count: int | None,
    verification_method: VerificationMethod,
    requested_guid: str | None = None,
    include_requested_guid: bool = False,
    recovery_hint: str | None = None,
    deferred: bool = False,
    not_requested: bool = False,
    unavailable_note: str | None = None,
    verification_note: str | None = None,
    mutation_note: str | None = None,
) -> dict[str, Any]:
    verification = derive_verification(
        component_errors=component_errors,
        component_warnings=component_warnings,
        unrelated_error_count=unrelated_error_count,
        unrelated_warning_count=unrelated_warning_count,
        method=verification_method,
        deferred=deferred,
        not_requested=not_requested,
        unavailable_note=unavailable_note,
        note=verification_note,
    )
    verification_status = verification["status"]
    diagnostics_unknown = _unknown_count(verification_status)

    repair_anchor: dict[str, Any] = {
        "component_guid": component_guid,
        "language": language,
        "mode_used": mode_used,
        "wrapped": wrapped,
        "pins_in": _copy_pin_list(pins_in),
        "pins_out": _copy_pin_list(pins_out),
        "source_shape": {
            "input_code_length": input_code_length,
            "prepared_source_length": prepared_source_length,
            "full_source_detected": full_source_detected,
        },
        "target_errors": None if diagnostics_unknown else _diagnostics(component_errors),
        "target_warnings": None if diagnostics_unknown else _diagnostics(component_warnings),
        "recovery_hint": recovery_hint,
    }
    if requested_guid and (include_requested_guid or requested_guid != component_guid):
        repair_anchor["requested_guid"] = requested_guid

    return {
        "version": 1,
        "operation": operation,
        "language": language,
        "mutation": {
            "status": mutation_status,
            "method": mutation_method,
            "component_guid": component_guid,
            "note": mutation_note,
        },
        "verification": verification,
        "artifact_status": derive_artifact_status(operation, verification_status),
        "repair_anchor": repair_anchor,
    }
```

- [ ] **Step 2: Run helper tests**

Run:

```powershell
python -m pytest -p no:cacheprovider mcp_server/tests/test_gh_script_receipts.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit helper tests and implementation**

Run:

```powershell
git add mcp_server/src/rook/gh_script_receipts.py mcp_server/tests/test_gh_script_receipts.py
git commit -m "feat: add GH script receipt helper"
```

---

## Task 3: Wire Create-Path Receipts

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add create receipt tests**

Append these tests near the existing `gh_create_script` compile-error tests in
`mcp_server/tests/test_server_contract_hardening.py`:

```python
@pytest.mark.asyncio
async def test_gh_create_csharp_script_compile_error_adds_script_receipt(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": component_guid, "errors": ["Cannot convert Box to Brep"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = new Box();",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["component_guid"] == component_guid
    assert data["compilation_errors"] == ["Cannot convert Box to Brep"]

    receipt = data["script_receipt"]
    assert receipt["version"] == 1
    assert receipt["operation"] == "create"
    assert receipt["language"] == "csharp"
    assert receipt["mutation"]["status"] == "created"
    assert receipt["mutation"]["method"] == "gh_create_component_then_script"
    assert receipt["verification"]["status"] == "failed"
    assert receipt["verification"]["method"] == "gh_errors"
    assert receipt["verification"]["target_error_count"] == 1
    assert receipt["artifact_status"] == "created_with_errors"
    assert receipt["repair_anchor"]["component_guid"] == component_guid
    assert receipt["repair_anchor"]["mode_used"] == "body"
    assert receipt["repair_anchor"]["wrapped"] is True
    assert receipt["repair_anchor"]["source_shape"]["input_code_length"] == len("B = new Box();")
    assert receipt["repair_anchor"]["source_shape"]["prepared_source_length"] == data["code_length"]
    assert receipt["repair_anchor"]["source_shape"]["full_source_detected"] is False
    assert receipt["repair_anchor"]["target_errors"] == ["Cannot convert Box to Brep"]
    assert receipt["repair_anchor"]["target_warnings"] == []


@pytest.mark.asyncio
async def test_gh_create_script_verification_unavailable_keeps_success_and_adds_unknown_receipt(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {"success": False, "data": "gh errors unavailable"}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = null;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["component_guid"] == component_guid
    assert "compilation_errors" not in data

    receipt = data["script_receipt"]
    assert receipt["verification"] == {
        "status": "unavailable",
        "method": "gh_errors",
        "target_error_count": None,
        "target_warning_count": None,
        "unrelated_error_count": None,
        "unrelated_warning_count": None,
        "note": "/gh/errors failed or returned malformed data; target compile state is unknown.",
    }
    assert receipt["artifact_status"] == "unknown"
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None


@pytest.mark.asyncio
async def test_gh_create_script_malformed_success_verification_is_unavailable(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {"success": True, "data": {}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = null;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is True
    receipt = payload["data"]["script_receipt"]
    assert receipt["verification"]["status"] == "unavailable"
    assert receipt["verification"]["method"] == "gh_errors"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["artifact_status"] == "unknown"


@pytest.mark.asyncio
async def test_gh_create_python_script_structured_success_adds_script_receipt(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": [], "warnings": []}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_python_script",
        {
            "code": "A = 1",
            "pins_in": [],
            "pins_out": ["A:int"],
            "name": "Python Maker",
        },
    ))

    assert payload["success"] is True
    receipt = payload["data"]["script_receipt"]
    assert receipt["version"] == 1
    assert receipt["operation"] == "create"
    assert receipt["language"] == "python"
    assert receipt["verification"]["status"] == "passed"
    assert receipt["artifact_status"] == "usable"
```

- [ ] **Step 2: Run the create receipt tests and verify they fail**

Run:

```powershell
python -m pytest -p no:cacheprovider `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_compile_error_adds_script_receipt `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_verification_unavailable_keeps_success_and_adds_unknown_receipt `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_malformed_success_verification_is_unavailable `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_python_script_structured_success_adds_script_receipt `
  -q
```

Expected: FAIL because `script_receipt` is not present yet.

- [ ] **Step 3: Import receipt helpers in `server.py`**

Near the existing `gh_csharp_preflight` import in `mcp_server/src/rook/server.py`, add:

```python
from .gh_script_receipts import build_script_receipt
```

- [ ] **Step 4: Add create verification summary helper**

Replace `_gh_create_script_component_errors(...)` or add this adjacent helper and
update callers to use it:

```python
def _summarize_gh_create_script_verification(errors_result: Any, component_guid: str) -> dict[str, Any]:
    unavailable_note = "/gh/errors failed or returned malformed data; target compile state is unknown."
    if isinstance(errors_result, dict) and errors_result.get("success") is False:
        return {
            "component_errors": [],
            "component_warnings": [],
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "unavailable_note": unavailable_note,
        }

    data = errors_result
    if isinstance(errors_result, dict) and (
        "success" in errors_result
        or _dict_get_ci(errors_result, "data") is not None
    ):
        wrapped_data = _dict_get_ci(errors_result, "data")
        if wrapped_data is None:
            return {
                "component_errors": [],
                "component_warnings": [],
                "unrelated_error_count": None,
                "unrelated_warning_count": None,
                "unavailable_note": unavailable_note,
            }
        data = wrapped_data
    if not isinstance(data, dict):
        return {
            "component_errors": [],
            "component_warnings": [],
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "unavailable_note": unavailable_note,
        }

    errors = _dict_get_ci(data, "errors")
    warnings = _dict_get_ci(data, "warnings")
    if not isinstance(errors, list) or not isinstance(warnings, list):
        return {
            "component_errors": [],
            "component_warnings": [],
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "unavailable_note": unavailable_note,
        }

    component_guid_lower = str(component_guid).lower()
    component_errors: list[Any] = []
    component_warnings: list[Any] = []
    unrelated_error_count = 0
    unrelated_warning_count = 0

    for entry in errors:
        entry_guid = _dict_get_ci(entry, "guid") if isinstance(entry, dict) else None
        messages = _dict_get_ci(entry, "errors") if isinstance(entry, dict) else entry
        normalized = _gh_update_script_messages(messages)
        if isinstance(entry_guid, str) and entry_guid.lower() == component_guid_lower:
            component_errors.extend(normalized)
        else:
            unrelated_error_count += len(normalized)

    for entry in warnings:
        entry_guid = _dict_get_ci(entry, "guid") if isinstance(entry, dict) else None
        messages = _dict_get_ci(entry, "warnings") if isinstance(entry, dict) else entry
        normalized = _gh_update_script_messages(messages)
        if isinstance(entry_guid, str) and entry_guid.lower() == component_guid_lower:
            component_warnings.extend(normalized)
        else:
            unrelated_warning_count += len(normalized)

    return {
        "component_errors": component_errors,
        "component_warnings": component_warnings,
        "unrelated_error_count": unrelated_error_count,
        "unrelated_warning_count": unrelated_warning_count,
        "unavailable_note": None,
    }
```

Keep `_gh_create_script_component_errors(...)` only if other tests still use it;
otherwise replace its usage with the new summary helper.

- [ ] **Step 5: Attach create receipts after script write and verification check**

In `_execute_gh_create_script(...)`, after `full_script` is created, compute
source-shape facts:

```python
input_code_length = len(code)
prepared_source_length = len(full_script)
if language == "csharp":
    full_source_detected = is_recognized_csharp_full_source(code)
    mode_used = "full_source" if full_source_detected else "body"
    wrapped = not full_source_detected
else:
    full_source_detected = False
    mode_used = "body"
    wrapped = bool(full_script != code)
```

Then replace the existing `component_errors` collection with:

```python
verification_summary = _summarize_gh_create_script_verification(errors_result, component_guid)
component_errors = verification_summary["component_errors"]
component_warnings = verification_summary["component_warnings"]
```

When constructing `data`, preserve existing fields and add:

```python
data["script_receipt"] = build_script_receipt(
    operation="create",
    language=language,
    mutation_status="created",
    mutation_method="gh_create_component_then_script",
    component_guid=component_guid,
    mode_used=mode_used,
    wrapped=wrapped,
    pins_in=pin_defs_in,
    pins_out=pin_defs_out,
    input_code_length=input_code_length,
    prepared_source_length=prepared_source_length,
    full_source_detected=full_source_detected,
    component_errors=component_errors,
    component_warnings=component_warnings,
    unrelated_error_count=verification_summary["unrelated_error_count"],
    unrelated_warning_count=verification_summary["unrelated_warning_count"],
    verification_method="gh_errors",
    unavailable_note=verification_summary["unavailable_note"],
)
```

Keep existing compile-error fields:

```python
if component_errors:
    data["compilation_errors"] = component_errors
    data["warning"] = "Component placed but has compilation errors"
```

- [ ] **Step 6: Run create receipt tests**

Run the same four-test command from Step 2.

Expected: PASS.

- [ ] **Step 7: Commit create wiring**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: add GH script create receipts"
```

---

## Task 4: Wire Update-Path Receipts

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add update receipt tests**

Append these tests near the existing `gh_update_script` tests in
`mcp_server/tests/test_server_contract_hardening.py`:

```python
@pytest.mark.asyncio
async def test_gh_update_script_compile_error_adds_script_receipt(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {"Params": {"Inputs": [{"Name": "R"}], "Outputs": [{"Name": "A"}]}},
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": "cs-guid", "errors": ["The name X does not exist"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = X;", "mode": "body"},
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["component_errors"] == ["The name X does not exist"]
    receipt = data["script_receipt"]
    assert receipt["version"] == 1
    assert receipt["operation"] == "update"
    assert receipt["language"] == "csharp"
    assert receipt["mutation"]["status"] == "written"
    assert receipt["mutation"]["method"] == "gh_script_write"
    assert receipt["verification"]["status"] == "failed"
    assert receipt["verification"]["method"] == "gh_errors"
    assert receipt["artifact_status"] == "written_with_errors"
    assert receipt["repair_anchor"]["component_guid"] == "cs-guid"
    assert receipt["repair_anchor"]["pins_in"] == [{"name": "R"}]
    assert receipt["repair_anchor"]["pins_out"] == [{"name": "A"}]
    assert receipt["repair_anchor"]["target_errors"] == ["The name X does not exist"]
    assert "Current inputs are R; outputs are A." in receipt["repair_anchor"]["recovery_hint"]


@pytest.mark.asyncio
async def test_gh_update_script_deferred_receipt_uses_unknown_diagnostics(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {
                "success": True,
                "data": {
                    "guid": "cs-guid",
                    "verification_deferred": True,
                    "solver_locked": True,
                },
            }
        if route == "/gh/component":
            return {
                "success": True,
                "data": {"Params": {"Inputs": [], "Outputs": [{"Name": "A"}]}},
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = 1;", "mode": "body"},
    ))

    assert payload["success"] is True
    receipt = payload["data"]["script_receipt"]
    assert receipt["verification"]["status"] == "deferred"
    assert receipt["verification"]["method"] == "none"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["artifact_status"] == "verification_pending"
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None


@pytest.mark.asyncio
async def test_gh_update_script_check_errors_false_receipt_is_not_requested(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {"Params": {"Inputs": [], "Outputs": [{"Name": "A"}]}},
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = 1;", "mode": "body", "check_errors": False},
    ))

    receipt = payload["data"]["script_receipt"]
    assert receipt["verification"]["status"] == "not_requested"
    assert receipt["verification"]["method"] == "none"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["artifact_status"] == "verification_pending"


@pytest.mark.asyncio
async def test_gh_update_script_error_check_failed_receipt_is_unavailable(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {"Params": {"Inputs": [], "Outputs": [{"Name": "A"}]}},
            }
        if route == "/gh/errors":
            return {"success": False, "data": "gh errors unavailable"}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = 1;", "mode": "body"},
    ))

    receipt = payload["data"]["script_receipt"]
    assert receipt["verification"]["status"] == "unavailable"
    assert receipt["verification"]["method"] == "gh_errors"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["artifact_status"] == "unknown"


@pytest.mark.asyncio
async def test_gh_update_script_snapshot_failure_receipt_uses_snapshot_method(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "resolved-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {"Params": {"Inputs": [], "Outputs": [{"Name": "A"}]}},
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {"errors": [{"guid": "other-guid", "errors": ["Other"]}], "warnings": []},
            }
        if route == "/gh/snapshot":
            return {"success": False, "data": "snapshot unavailable"}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "C1", "code": "A = 1;", "mode": "body"},
    ))

    receipt = payload["data"]["script_receipt"]
    assert receipt["verification"]["status"] == "unavailable"
    assert receipt["verification"]["method"] == "gh_snapshot_fallback"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["repair_anchor"]["requested_guid"] == "C1"
```

- [ ] **Step 2: Run update receipt tests and verify they fail**

Run:

```powershell
python -m pytest -p no:cacheprovider `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_update_script_compile_error_adds_script_receipt `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_update_script_deferred_receipt_uses_unknown_diagnostics `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_update_script_check_errors_false_receipt_is_not_requested `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_update_script_error_check_failed_receipt_is_unavailable `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_update_script_snapshot_failure_receipt_uses_snapshot_method `
  -q
```

Expected: FAIL because `script_receipt` is not attached on update yet.

- [ ] **Step 3: Track update verification method and not-requested state**

Inside `_execute_gh_update_script(...)`, initialize before the deferred/check
branch:

```python
verification_method = "gh_errors"
check_errors_requested = bool(arguments.get("check_errors", True))
```

In the deferred branch, set:

```python
verification_method = "none"
```

Change:

```python
elif bool(arguments.get("check_errors", True)):
```

to:

```python
elif check_errors_requested:
```

In the `else` branch for disabled checks, set:

```python
verification_method = "none"
error_summary = _empty_gh_update_script_error_summary()
```

When snapshot fallback replaces `error_summary`, set:

```python
verification_method = "gh_snapshot_fallback"
```

Also set `verification_method = "gh_snapshot_fallback"` when
`snapshot_check_failed` is added.

- [ ] **Step 4: Attach update receipts**

After existing `recovery_hint` logic and before returning
`_gh_update_script_result_from_data(data)`, add:

```python
unavailable_note = None
if data.get("snapshot_check_failed"):
    unavailable_note = data["snapshot_check_failed"]
elif data.get("error_check_failed"):
    unavailable_note = data["error_check_failed"]

data["script_receipt"] = build_script_receipt(
    operation="update",
    language=data.get("detected_language", "unknown"),
    mutation_status="written",
    mutation_method="gh_script_write",
    component_guid=resolved_guid,
    mode_used=prepared["mode_used"],
    wrapped=prepared["wrapped"],
    pins_in=inputs,
    pins_out=outputs,
    input_code_length=len(code),
    prepared_source_length=len(prepared["source"]),
    full_source_detected=(
        runtime["detected_language"] == "csharp"
        and prepared["mode_used"] == "full_source"
        and not prepared["wrapped"]
    ),
    component_errors=data.get("component_errors", []),
    component_warnings=data.get("component_warnings", []),
    unrelated_error_count=data.get("unrelated_error_count"),
    unrelated_warning_count=data.get("unrelated_warning_count"),
    verification_method=verification_method,
    requested_guid=guid,
    include_requested_guid=_is_gh_short_id(guid),
    recovery_hint=data.get("recovery_hint"),
    deferred=bool(data.get("verification_deferred")),
    not_requested=not check_errors_requested,
    unavailable_note=unavailable_note,
    verification_note=data.get("verification_note"),
)
```

- [ ] **Step 5: Run update receipt tests**

Run the same five-test command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit update wiring**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: add GH script update receipts"
```

---

## Task 5: Add Compatibility And Non-Goal Regressions

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Add server compatibility tests**

Append these tests in `mcp_server/tests/test_server_contract_hardening.py`:

```python
@pytest.mark.asyncio
async def test_gh_create_script_early_string_failure_remains_receipt_free(monkeypatch, patched_server):
    routes_called: list[str] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes_called.append(route)
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_script",
        {"code": "A = 1", "pins_out": ["A:int"]},
    ))

    assert payload["success"] is False
    assert isinstance(payload["data"], str)
    assert "script_receipt" not in payload["data"]
    assert "/gh/create-component" not in routes_called


@pytest.mark.asyncio
async def test_gh_create_script_pass_through_mutation_failure_remains_unchanged(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": False, "data": {"route": "failed", "reason": "bridge unavailable"}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {"code": "A = 1;", "pins_out": ["A:int"]},
    ))

    assert payload == {
        "success": False,
        "data": "Failed to create C# Script component: {'route': 'failed', 'reason': 'bridge unavailable'}",
    }


@pytest.mark.asyncio
async def test_gh_set_script_raw_escape_hatch_remains_without_receipt(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "raw-guid", "script": "A = 1;"}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_set_script",
        {"guid": "raw-guid", "script": "A = 1;"},
    ))

    assert payload["success"] is True
    assert payload["data"] == {"guid": "raw-guid", "script": "A = 1;"}
    assert "script_receipt" not in payload["data"]
```

- [ ] **Step 2: Add ToolResultView compatibility test**

Append this test near the existing LM1B `normalize_tool_result(...)` tests in
`mcp_server/tests/test_rookchat_tool_contracts.py`:

```python
def test_normalize_tool_result_ignores_script_receipt_for_top_level_truth():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    view = normalize_tool_result({
        "success": False,
        "message": "Component was created, but the target script component has compile errors.",
        "data": {
            "component_guid": "created-guid",
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "mutation": {
                    "status": "created",
                    "method": "gh_create_component_then_script",
                    "component_guid": "created-guid",
                    "note": None,
                },
                "verification": {
                    "status": "failed",
                    "method": "gh_errors",
                    "target_error_count": 1,
                    "target_warning_count": 0,
                    "unrelated_error_count": 0,
                    "unrelated_warning_count": 0,
                    "note": None,
                },
                "artifact_status": "created_with_errors",
                "repair_anchor": {
                    "component_guid": "created-guid",
                    "language": "csharp",
                    "mode_used": "body",
                    "wrapped": True,
                    "pins_in": [],
                    "pins_out": [{"name": "B", "type": "Brep"}],
                    "source_shape": {
                        "input_code_length": 14,
                        "prepared_source_length": 900,
                        "full_source_detected": False,
                    },
                    "target_errors": ["Cannot convert Box to Brep"],
                    "target_warnings": [],
                    "recovery_hint": None,
                },
            },
        },
    })

    assert view.status == "failed"
    assert view.message == "Component was created, but the target script component has compile errors."
```

- [ ] **Step 3: Run compatibility tests**

Run:

```powershell
python -m pytest -p no:cacheprovider `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_early_string_failure_remains_receipt_free `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_pass_through_mutation_failure_remains_unchanged `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_set_script_raw_escape_hatch_remains_without_receipt `
  mcp_server/tests/test_rookchat_tool_contracts.py::test_normalize_tool_result_ignores_script_receipt_for_top_level_truth `
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit compatibility tests**

Run:

```powershell
git add mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_rookchat_tool_contracts.py
git commit -m "test: cover GH script receipt compatibility"
```

---

## Task 6: Focused Verification And Hygiene

**Files:**
- Verify: `mcp_server/src/rook/gh_script_receipts.py`
- Verify: `mcp_server/src/rook/server.py`
- Verify: `mcp_server/tests/test_gh_script_receipts.py`
- Verify: `mcp_server/tests/test_server_contract_hardening.py`
- Verify: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Run focused LM1D and adjacent suites**

Run:

```powershell
$tmp='C:\UDEV\Rook\.codex-pytest-tmp'
$cache='C:\UDEV\Rook\.codex-dspy-cache'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$env:TMP=$tmp
$env:TEMP=$tmp
$env:DSPY_CACHEDIR=$cache
python -m pytest -p no:cacheprovider `
  mcp_server/tests/test_gh_script_receipts.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_tool_transcripts.py `
  -q
```

Expected: PASS.

- [ ] **Step 2: Run compile check**

Run:

```powershell
python -m py_compile `
  mcp_server/src/rook/gh_script_receipts.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/chat/tool_contracts.py
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Run diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

- `git diff --check` exits `0`.
- `git status --short --branch` shows only the LM1D branch and no unstaged runtime artifacts.

- [ ] **Step 4: Remove local temp caches if created**

Run:

```powershell
$targets = @('C:\UDEV\Rook\.codex-dspy-cache','C:\UDEV\Rook\.codex-pytest-tmp')
foreach ($path in $targets) {
  if (Test-Path $path) {
    $resolved = (Resolve-Path $path).Path
    if ($resolved.StartsWith('C:\UDEV\Rook\')) {
      Remove-Item -LiteralPath $resolved -Recurse -Force
    }
  }
}
git status --short --branch
```

Expected: branch remains clean except intentional tracked changes.

- [ ] **Step 5: Commit final verification fixes if any were needed**

If Task 6 required code/test fixes, commit only those fixes:

```powershell
git add mcp_server/src/rook/gh_script_receipts.py mcp_server/src/rook/server.py mcp_server/tests/test_gh_script_receipts.py mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_rookchat_tool_contracts.py
git commit -m "test: verify LM1D GH script receipts"
```

If no fixes were needed and the working tree is clean, do not create an empty commit.

---

## Review Checkpoints

Use review checkpoints after:

- Task 2: pure helper contract is green.
- Task 4: create/update server wiring is green.
- Task 6: full focused verification and hygiene are complete.

At each checkpoint, confirm:

- No `gh_set_script` behavior change.
- No ChatRunner event wiring.
- No dispatcher refactor.
- No PlanGraph or LM2 capability work.
- Existing top-level `success` behavior remains coarse and compatible.
- Early string failures and pass-through failures remain unchanged.

---

## Self-Review Notes

Spec coverage:

- Producer-side `data["script_receipt"]`: Task 3 and Task 4.
- Pure helper module: Task 1 and Task 2.
- Current coarse truth preserved: Task 3, Task 4, Task 5.
- Unknown counts are `None`: Task 1, Task 3, Task 4.
- Deferred/unavailable/not-requested states: Task 1 and Task 4.
- Repair anchors without full source text: Task 1, Task 3, Task 4.
- Python helper-path coverage without Python repair expansion: Task 3.
- No ChatRunner behavior change: Task 5 uses `ToolResultView` only as compatibility.
- No live Rhino: every server test uses mocked `call_rhino`.

Unresolved-wording scan:

- No task uses unresolved wording.
- Every code step includes concrete code or exact command.

Type consistency:

- Receipt field names match the approved LM1D spec:
  `script_receipt`, `version`, `operation`, `language`, `mutation`,
  `verification`, `artifact_status`, and `repair_anchor`.
- Unknown diagnostic counts and target diagnostics use `None`.
