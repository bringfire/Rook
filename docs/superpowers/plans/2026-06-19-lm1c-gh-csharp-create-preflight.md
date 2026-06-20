# LM1C Grasshopper C# Script Create Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, non-live C# script creation preflight gate that rejects obvious invalid Grasshopper RhinoCode C# contracts before `/gh/create-component` mutation.

**Architecture:** Add focused preflight helpers in `mcp_server/src/rook/server.py` at the unified `_execute_gh_create_script` boundary. The helper runs after existing pin normalization and before C# wrapper construction or any Rhino call, so both `gh_create_csharp_script` and `gh_create_script(language="csharp")` share the same gate while Python creation remains unchanged.

**Tech Stack:** Python 3, pytest, existing Rook MCP server helper functions, existing `server.call_tool()` public formatting tests.

---

## File Structure

- Modify `mcp_server/src/rook/server.py`
  - Add `dataclass` and `re` imports.
  - Add `GhCSharpCreatePreflightFinding`.
  - Add pure helper functions for C# identifier validation, plugin-source detection, body-mode assignment evidence, and preflight failure formatting.
  - Wire `_execute_gh_create_script` to run the C# preflight after `_normalize_gh_script_pins` and before `_build_gh_csharp_wrapper` or `/gh/create-component`.

- Modify `mcp_server/tests/test_server_contract_hardening.py`
  - Add direct unit tests for the preflight helper.
  - Add call-path tests proving invalid C# requests do not call `/gh/create-component`.
  - Add regression coverage for `single` raw access alias behavior and raw invalid access keeping the existing normalizer failure shape.

No new files are required. Do not edit `tool_contracts.py`, `tool_dispatcher.py`, ChatRunner, public MCP formatting, or capability-registry code.

---

### Task 1: Add Failing Direct Preflight Helper Tests

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add direct helper tests near the existing `gh_create_csharp_script` tests**

Insert this block immediately before `test_gh_create_csharp_script_accepts_rich_pin_objects`:

```python
def _preflight_codes(findings):
    return {finding.code for finding in findings}


def test_gh_csharp_create_preflight_accepts_simple_body_assignment():
    findings = server._preflight_gh_csharp_create_script_contract(
        "A = Convert.ToDouble(R);",
        [{"name": "R", "type": "double"}],
        [{"name": "A", "type": "double"}],
    )

    assert findings == []


def test_gh_csharp_create_preflight_rejects_invalid_keyword_and_duplicate_pins():
    findings = server._preflight_gh_csharp_create_script_contract(
        "A = 1;",
        [{"name": "class", "type": "double"}, {"name": "A", "type": "double"}],
        [{"name": "A", "type": "double"}, {"name": "1B", "type": "Brep"}],
    )

    codes = _preflight_codes(findings)
    assert "reserved_pin_identifier" in codes
    assert "duplicate_pin_identifier" in codes
    assert "invalid_pin_identifier" in codes


def test_gh_csharp_create_preflight_rejects_normalized_invalid_access():
    findings = server._preflight_gh_csharp_create_script_contract(
        "A = 1;",
        [{"name": "R", "type": "double", "access": "matrix"}],
        [{"name": "A", "type": "double"}],
    )

    assert any(
        finding.code == "invalid_pin_access" and finding.pin == "R"
        for finding in findings
    )


@pytest.mark.parametrize(
    "code",
    [
        "public class BadComponent : GH_Component { }",
        "protected override void SolveInstance(IGH_DataAccess DA) { }",
        "protected override void RegisterInputParams(GH_InputParamManager pManager) { }",
        "protected override void RegisterOutputParams(GH_OutputParamManager pManager) { }",
        "private void Helper(IGH_DataAccess DA) { }",
    ],
)
def test_gh_csharp_create_preflight_rejects_plugin_component_source(code):
    findings = server._preflight_gh_csharp_create_script_contract(
        code,
        [],
        [{"name": "B", "type": "Brep"}],
    )

    assert any(finding.code == "plugin_component_source" for finding in findings)


def test_gh_csharp_create_preflight_requires_body_output_assignment():
    findings = server._preflight_gh_csharp_create_script_contract(
        "var radius = 5.0;",
        [],
        [{"name": "B", "type": "Brep"}],
    )

    assert any(
        finding.code == "missing_output_assignment" and finding.pin == "B"
        for finding in findings
    )


@pytest.mark.parametrize("operator", ["=", "+=", "-=", "*=", "/=", "??="])
def test_gh_csharp_create_preflight_accepts_simple_output_assignment_operators(operator):
    findings = server._preflight_gh_csharp_create_script_contract(
        f"B {operator} value;",
        [],
        [{"name": "B", "type": "Brep"}],
    )

    assert not any(finding.code == "missing_output_assignment" for finding in findings)


def test_gh_csharp_create_preflight_does_not_accept_method_call_assignment_evidence():
    findings = server._preflight_gh_csharp_create_script_contract(
        "B.Add(value);",
        [],
        [{"name": "B", "type": "object"}],
    )

    assert any(finding.code == "missing_output_assignment" for finding in findings)


def test_gh_csharp_create_preflight_skips_assignment_check_for_full_source():
    findings = server._preflight_gh_csharp_create_script_contract(
        (
            "public class Script_Instance : GH_ScriptInstance { "
            "private void RunScript(ref object B) { } }"
        ),
        [],
        [{"name": "B", "type": "object"}],
    )

    assert not any(finding.code == "missing_output_assignment" for finding in findings)
```

- [ ] **Step 2: Run the direct helper tests and verify they fail**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_accepts_simple_body_assignment `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_invalid_keyword_and_duplicate_pins `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_normalized_invalid_access `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_plugin_component_source `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_requires_body_output_assignment `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_accepts_simple_output_assignment_operators `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_does_not_accept_method_call_assignment_evidence `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_skips_assignment_check_for_full_source `
  -q
```

Expected: FAIL with `AttributeError: module 'rook.server' has no attribute '_preflight_gh_csharp_create_script_contract'`.

- [ ] **Step 3: Leave the red tests uncommitted**

Do not commit yet. The tests become green in Task 2.

---

### Task 2: Implement Pure C# Create Preflight Helper

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add imports**

Change the top import block in `mcp_server/src/rook/server.py` from:

```python
import ast
import asyncio
import copy
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any
```

to:

```python
import ast
import asyncio
import copy
import json
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
```

- [ ] **Step 2: Add the preflight helper code**

Insert this block immediately after `_gh_create_script_result_from_data` and before `_execute_gh_create_script`:

```python
@dataclass(frozen=True)
class GhCSharpCreatePreflightFinding:
    code: str
    message: str
    field: str | None = None
    pin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.field is not None:
            result["field"] = self.field
        if self.pin is not None:
            result["pin"] = self.pin
        return result


_GH_CSHARP_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_GH_CSHARP_RESERVED_KEYWORDS = frozenset({
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch",
    "char", "checked", "class", "const", "continue", "decimal", "default",
    "delegate", "do", "double", "else", "enum", "event", "explicit",
    "extern", "false", "finally", "fixed", "float", "for", "foreach",
    "goto", "if", "implicit", "in", "int", "interface", "internal", "is",
    "lock", "long", "namespace", "new", "null", "object", "operator",
    "out", "override", "params", "private", "protected", "public",
    "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof",
    "stackalloc", "static", "string", "struct", "switch", "this", "throw",
    "true", "try", "typeof", "uint", "ulong", "unchecked", "unsafe",
    "ushort", "using", "virtual", "void", "volatile", "while",
})

_GH_CSHARP_PLUGIN_SOURCE_PATTERNS: tuple = (
    (
        "class_extends_gh_component",
        re.compile(r"\bclass\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)*GH_Component\b"),
    ),
    ("solve_instance", re.compile(r"\bSolveInstance\s*\(")),
    ("register_input_params", re.compile(r"\bRegisterInputParams\s*\(")),
    ("register_output_params", re.compile(r"\bRegisterOutputParams\s*\(")),
    ("igh_data_access", re.compile(r"\bIGH_DataAccess\b")),
    ("gh_input_param_manager", re.compile(r"\bGH_InputParamManager\b")),
    ("gh_output_param_manager", re.compile(r"\bGH_OutputParamManager\b")),
)


def _gh_csharp_is_body_source(code: str) -> bool:
    return "class Script_Instance" not in code and "void RunScript" not in code


def _gh_csharp_has_output_assignment(code: str, output_name: str) -> bool:
    escaped = re.escape(output_name)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_\.]){escaped}\s*(?:\?\?=|\+=|-=|\*=|/=|=(?!=))",
    )
    return bool(pattern.search(code))


def _preflight_gh_csharp_create_script_contract(
    code: str,
    pins_in: list[dict[str, Any]],
    pins_out: list[dict[str, Any]],
) -> list[GhCSharpCreatePreflightFinding]:
    findings: list[GhCSharpCreatePreflightFinding] = []
    seen_names: dict[str, str] = {}

    for field, pins in (("pins_in", pins_in), ("pins_out", pins_out)):
        for pin in pins:
            name = str(pin.get("name") or "")
            if not _GH_CSHARP_IDENTIFIER_RE.match(name):
                findings.append(GhCSharpCreatePreflightFinding(
                    code="invalid_pin_identifier",
                    message=f"Pin name '{name}' is not a valid C# identifier.",
                    field=field,
                    pin=name,
                ))
            elif name in _GH_CSHARP_RESERVED_KEYWORDS:
                findings.append(GhCSharpCreatePreflightFinding(
                    code="reserved_pin_identifier",
                    message=f"Pin name '{name}' is a reserved C# keyword.",
                    field=field,
                    pin=name,
                ))

            access = pin.get("access")
            if access is not None and access not in {"item", "list", "tree"}:
                findings.append(GhCSharpCreatePreflightFinding(
                    code="invalid_pin_access",
                    message=(
                        f"Pin '{name}' has normalized access '{access}'. "
                        "Expected one of item, list, tree."
                    ),
                    field=field,
                    pin=name,
                ))

            if name in seen_names:
                findings.append(GhCSharpCreatePreflightFinding(
                    code="duplicate_pin_identifier",
                    message=(
                        f"Pin name '{name}' appears in both the C# RunScript "
                        "parameter namespace and cannot be duplicated."
                    ),
                    field=field,
                    pin=name,
                ))
            else:
                seen_names[name] = field

    for _pattern_name, pattern in _GH_CSHARP_PLUGIN_SOURCE_PATTERNS:
        if pattern.search(code):
            findings.append(GhCSharpCreatePreflightFinding(
                code="plugin_component_source",
                message=(
                    "C# script components require RhinoCode Script_Instance or "
                    "body-style RunScript code, not a GH_Component plugin class."
                ),
                field="code",
            ))
            break

    if _gh_csharp_is_body_source(code):
        for pin in pins_out:
            name = str(pin.get("name") or "")
            if _GH_CSHARP_IDENTIFIER_RE.match(name) and not _gh_csharp_has_output_assignment(code, name):
                findings.append(GhCSharpCreatePreflightFinding(
                    code="missing_output_assignment",
                    message=(
                        f"Output pin '{name}' is declared but body-style C# code "
                        "does not visibly assign it."
                    ),
                    field="pins_out",
                    pin=name,
                ))

    return findings


def _gh_csharp_create_preflight_failure(
    findings: list[GhCSharpCreatePreflightFinding],
    pins_in: list[dict[str, Any]],
    pins_out: list[dict[str, Any]],
) -> dict[str, Any]:
    message = "C# script preflight failed."
    data = {
        "message": message,
        "preflight_errors": [finding.to_dict() for finding in findings],
        "pins_in": pins_in,
        "pins_out": pins_out,
    }
    return {
        "success": False,
        "message": message,
        "data": data,
    }
```

- [ ] **Step 3: Run the direct helper tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_accepts_simple_body_assignment `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_invalid_keyword_and_duplicate_pins `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_normalized_invalid_access `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_plugin_component_source `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_requires_body_output_assignment `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_accepts_simple_output_assignment_operators `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_does_not_accept_method_call_assignment_evidence `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_skips_assignment_check_for_full_source `
  -q
```

Expected: PASS.

- [ ] **Step 4: Run Python syntax check for touched modules**

Run:

```powershell
python -m py_compile `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_server_contract_hardening.py
```

Expected: no output and exit code 0.

- [ ] **Step 5: Commit the helper and direct tests**

Run:

```powershell
git add -- mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: add gh csharp create preflight helper"
```

Do not stage `knowledge/gh/component_observations.json`.

---

### Task 3: Add Failing Call-Path Preflight Tests

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add call-path tests after the direct preflight tests**

Insert this block after `test_gh_csharp_create_preflight_skips_assignment_check_for_full_source`:

```python
@pytest.mark.asyncio
async def test_gh_create_csharp_script_preflight_failure_does_not_create_component(
    monkeypatch, patched_server
):
    call_rhino_mock = AsyncMock(side_effect=AssertionError("preflight should prevent Rhino calls"))
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = null;",
            "pins_in": [],
            "pins_out": ["1B:Brep"],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == "C# script preflight failed."
    assert any(
        error["code"] == "invalid_pin_identifier" and error["pin"] == "1B"
        for error in data["preflight_errors"]
    )
    assert data["pins_out"] == [{"name": "1B", "type": "Brep"}]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_gh_create_script_csharp_preflight_failure_does_not_create_component(
    monkeypatch, patched_server
):
    call_rhino_mock = AsyncMock(side_effect=AssertionError("preflight should prevent Rhino calls"))
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "public class BadComponent : GH_Component { }",
            "pins_in": [],
            "pins_out": ["B:Brep"],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == "C# script preflight failed."
    assert any(
        error["code"] == "plugin_component_source"
        for error in data["preflight_errors"]
    )
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_gh_create_csharp_script_preflight_failure_has_public_parseable_message(
    monkeypatch, patched_server
):
    call_rhino_mock = AsyncMock(side_effect=AssertionError("preflight should prevent Rhino calls"))
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "var radius = 5.0;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
        },
    )
    text = response[0].text
    assert text.startswith("Error: ")
    public_payload = json.loads(text[len("Error: "):])

    assert public_payload["message"] == "C# script preflight failed."
    assert public_payload["preflight_errors"][0]["code"] == "missing_output_assignment"
    assert public_payload["pins_out"] == [{"name": "B", "type": "Brep"}]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_gh_create_csharp_script_raw_single_access_still_normalizes_to_item(
    monkeypatch, patched_server
):
    recorded_calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        recorded_calls.append((route, method, payload))
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "single-access-guid"}}
        if route == "/gh/script-params":
            assert payload["inputs"] == [{
                "name": "R",
                "type": "double",
                "access": "item",
                "optional": True,
            }]
            return {"success": True, "data": {"Guid": "single-access-guid"}}
        if route == "/gh/script":
            return {"success": True, "data": {"Guid": "single-access-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "A = Convert.ToDouble(R);",
            "pins_in": [{"name": "R", "type": "double", "access": "single"}],
            "pins_out": [{"name": "A", "type": "double"}],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["pins_in"][0]["access"] == "item"
    assert any(route == "/gh/create-component" for route, _, _ in recorded_calls)


@pytest.mark.asyncio
async def test_gh_create_csharp_script_raw_invalid_access_keeps_normalizer_failure_shape(
    monkeypatch, patched_server
):
    call_rhino_mock = AsyncMock(side_effect=AssertionError("normalizer should prevent Rhino calls"))
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "A = 1;",
            "pins_in": [{"name": "R", "type": "double", "access": "matrix"}],
            "pins_out": [{"name": "A", "type": "double"}],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is False
    assert isinstance(payload["data"], str)
    assert "Invalid pin access 'matrix'" in payload["data"]
    assert "preflight_errors" not in payload["data"]
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_gh_create_script_python_does_not_run_csharp_output_assignment_preflight(
    monkeypatch, patched_server
):
    recorded_calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        recorded_calls.append((route, method, payload))
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "python-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": "python-guid"}}
        if route == "/gh/script":
            return {"success": True, "data": {"Guid": "python-guid"}}
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": []}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "gh_create_script",
        {
            "language": "python",
            "code": "print('no output assignment')",
            "pins_in": [],
            "pins_out": ["B:Brep"],
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["component_guid"] == "python-guid"
    assert any(route == "/gh/create-component" for route, _, _ in recorded_calls)
```

- [ ] **Step 2: Run the new call-path tests and verify they fail before wiring**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_preflight_failure_does_not_create_component `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_csharp_preflight_failure_does_not_create_component `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_preflight_failure_has_public_parseable_message `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_raw_single_access_still_normalizes_to_item `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_raw_invalid_access_keeps_normalizer_failure_shape `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_python_does_not_run_csharp_output_assignment_preflight `
  -q
```

Expected: FAIL for the preflight-failure tests because `_execute_gh_create_script` has not yet called the helper and the fake `call_rhino` raises when the create pipeline reaches Rhino. The `single` and raw-invalid-access tests may already pass; the command is still red until the C# failure tests pass.

- [ ] **Step 3: Leave the red call-path tests uncommitted**

Do not commit yet. The tests become green in Task 4.

---

### Task 4: Wire Preflight Into the Unified C# Create Path

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add the C# preflight call in `_execute_gh_create_script`**

Replace this block:

```python
        # Language-specific code preparation
        if language == "python":
            preamble = _build_gh_python_preamble(pin_defs_in)
            postamble = _build_gh_python_output_postamble(pin_defs_out)
            full_script = preamble + code + postamble
        else:  # csharp
            full_script = _build_gh_csharp_wrapper(code, pin_defs_in, pin_defs_out)
```

with:

```python
        # Language-specific code preparation
        if language == "python":
            preamble = _build_gh_python_preamble(pin_defs_in)
            postamble = _build_gh_python_output_postamble(pin_defs_out)
            full_script = preamble + code + postamble
        else:  # csharp
            preflight_findings = _preflight_gh_csharp_create_script_contract(
                str(code),
                pin_defs_in,
                pin_defs_out,
            )
            if preflight_findings:
                return _gh_csharp_create_preflight_failure(
                    preflight_findings,
                    pin_defs_in,
                    pin_defs_out,
                )
            full_script = _build_gh_csharp_wrapper(code, pin_defs_in, pin_defs_out)
```

This preserves the current language gate. Do not add new accepted values such as `"CSharp"` or `"c#"`.

- [ ] **Step 2: Run the call-path tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_preflight_failure_does_not_create_component `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_csharp_preflight_failure_does_not_create_component `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_preflight_failure_has_public_parseable_message `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_raw_single_access_still_normalizes_to_item `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_csharp_script_raw_invalid_access_keeps_normalizer_failure_shape `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_create_script_python_does_not_run_csharp_output_assignment_preflight `
  -q
```

Expected: PASS.

- [ ] **Step 3: Run direct helper tests again**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_accepts_simple_body_assignment `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_invalid_keyword_and_duplicate_pins `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_normalized_invalid_access `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_rejects_plugin_component_source `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_requires_body_output_assignment `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_accepts_simple_output_assignment_operators `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_does_not_accept_method_call_assignment_evidence `
  mcp_server/tests/test_server_contract_hardening.py::test_gh_csharp_create_preflight_skips_assignment_check_for_full_source `
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit the wiring and call-path tests**

Run:

```powershell
git add -- mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix: preflight gh csharp script creation"
```

Do not stage `knowledge/gh/component_observations.json`.

---

### Task 5: Focused Regression Verification

**Files:**
- Verify: `mcp_server/src/rook/server.py`
- Verify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Run the full focused script-create and update contract subset**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_server_contract_hardening.py `
  -k "gh_create_csharp_script or gh_create_script or gh_create_python_script or gh_update_script_compile_failure_returns_failed or gh_update_script_unrelated_canvas_errors_remain_success or gh_update_script_target_warnings_remain_success or gh_update_script_error_check_failure_is_visible or gh_update_script_check_errors_false_skips_gh_errors" `
  -q
```

Expected: PASS. Existing `datetime.utcnow()` deprecation warnings from GH session history may appear and are not part of LM1C.

- [ ] **Step 2: Run RookChat schema and transcript guardrails**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  mcp_server/tests/test_rookchat_gh_script_creation_parity.py `
  mcp_server/tests/test_rookchat_tool_transcripts.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  -q
```

Expected: PASS. LM1C must not change the RookChat visible schema surface or dispatchability gate.

- [ ] **Step 3: Run Python syntax checks**

Run:

```powershell
python -m py_compile `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_server_contract_hardening.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short
git diff --stat
git diff -- mcp_server/src/rook/server.py
git diff -- mcp_server/tests/test_server_contract_hardening.py
```

Expected:

- `git diff --check` exits 0.
- Only `mcp_server/src/rook/server.py` and `mcp_server/tests/test_server_contract_hardening.py` are changed for LM1C.
- `knowledge/gh/component_observations.json` may still appear as a pre-existing unstaged artifact and must remain unstaged unless the user explicitly asks otherwise.
- No changes appear in `tool_contracts.py`, `tool_dispatcher.py`, ChatRunner, public MCP formatter code outside the existing helper boundary, or capability-registry code.

- [ ] **Step 5: Commit any final verification fixes**

If Step 1 or Step 2 required a narrow fix in the LM1C files, run:

```powershell
git add -- mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "test: verify gh csharp create preflight"
```

If all verification passed with no uncommitted LM1C changes, do not create an empty commit.

---

## Self-Review

- **Spec coverage:** The plan implements the pure server-boundary preflight, covers both C# create entry points, runs after normalization and before mutation, preserves `single` raw access alias behavior, keeps raw invalid access outside `preflight_errors`, and tests no `/gh/create-component` calls for invalid preflight cases.
- **Placeholder scan:** No placeholder tasks remain; every code-changing task includes exact code blocks and every verification step includes exact commands and expected results.
- **Type consistency:** The plan uses `GhCSharpCreatePreflightFinding`, `_preflight_gh_csharp_create_script_contract`, and `_gh_csharp_create_preflight_failure` consistently across tests and implementation.
