# LM1C Grasshopper C# Script Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic C# script preflight that rejects obvious RhinoCode C# script contract violations before Grasshopper create/update mutations.

**Architecture:** Add a small importable C# preflight module with a shared full-source predicate, then wire it into the existing `server.py` create/update helpers after normalization and before mutation. Keep dispatcher, ChatRunner event handling, MCP wire shape, `gh_set_script`, and live Rhino behavior unchanged.

**Tech Stack:** Python 3, pytest, existing Rook MCP server helpers, `ToolDispatcher`, mocked `call_rhino`.

---

## Scope Guardrails

This plan implements only the approved LM1C spec:

- No `gh_set_script` migration.
- No full C# compilation or Roslyn integration.
- No output-assignment hard reject.
- No public MCP wire-shape change.
- No ChatRunner event wiring.
- No live Rhino dependency.
- No PlanGraph.
- No capability registry.
- No broad dispatcher refactor.
- No generated recipe/example expansion.

If implementation pressure points toward any of those, stop and ask for review.

---

## File Structure

- Create `mcp_server/src/rook/gh_csharp_preflight.py`
  - Owns `CSharpScriptPreflightResult`.
  - Owns `is_recognized_csharp_full_source(...)`.
  - Owns `preflight_csharp_script(...)`.
  - Has no Rhino, Grasshopper, dispatcher, ChatRunner, or MCP imports.

- Create `mcp_server/tests/test_gh_csharp_preflight.py`
  - Unit tests for the helper.
  - No mocked Rhino needed.
  - Tests all hard-reject and explicit non-reject cases.

- Modify `mcp_server/src/rook/server.py`
  - Import the helper module.
  - Replace the duplicated full-source predicate in `_build_gh_csharp_wrapper(...)`.
  - Replace the duplicated full-source predicate in `_prepare_gh_update_script_source(...)`.
  - Call preflight in `_execute_gh_create_script(...)` before `/gh/create-component`.
  - Call preflight in `_execute_gh_update_script(...)` after runtime/pin discovery and before `/gh/script` write.

- Modify `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
  - Add non-live create-path mutation-blocking tests for local alias and unified C# script creation.
  - Add a regression that alias normalization still feeds preflight through the normalized `code` field.
  - Add a Python unaffected regression.

- Modify `mcp_server/tests/test_server_contract_hardening.py`
  - Add update-path mutation-blocking test with mocked read calls and no `/gh/script` write.
  - Add server-level regression that `_prepare_gh_update_script_source(...)` uses the shared full-source predicate.
  - Add optional narrow `ToolResultView` regression only if not already covered well enough by LM1B tests.

---

## Task 1: Add Failing Helper Tests

**Files:**
- Create: `mcp_server/tests/test_gh_csharp_preflight.py`

- [ ] **Step 1: Write helper tests**

Create `mcp_server/tests/test_gh_csharp_preflight.py` with this content:

```python
from __future__ import annotations

import copy

import pytest

from rook.gh_csharp_preflight import (
    is_recognized_csharp_full_source,
    preflight_csharp_script,
)


def _result(code, pins_in=None, pins_out=None, mode="auto"):
    return preflight_csharp_script(
        code=code,
        pins_in=[] if pins_in is None else pins_in,
        pins_out=[] if pins_out is None else pins_out,
        mode=mode,
    )


def test_valid_body_style_code_with_valid_pins_passes():
    result = _result(
        "A = Convert.ToDouble(R);",
        pins_in=[{"name": "R", "type": "double"}],
        pins_out=[{"name": "A", "type": "double"}],
        mode="body",
    )

    assert result.ok is True
    assert result.message is None
    assert result.code is None


def test_valid_recognized_full_source_passes():
    code = (
        "using System;\n"
        "public class Script_Instance : GH_ScriptInstance {\n"
        "  private void RunScript(object R, ref object A) { A = R; }\n"
        "}\n"
    )

    result = _result(
        code,
        pins_in=[{"name": "R"}],
        pins_out=[{"name": "A"}],
        mode="full_source",
    )

    assert is_recognized_csharp_full_source(code) is True
    assert result.ok is True


@pytest.mark.parametrize("code", [None, 123, ["A = R;"]])
def test_non_string_code_fails(code):
    result = _result(code, pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "invalid_code"
    assert "code must be a non-empty string" in result.message


def test_empty_code_fails():
    result = _result("   \n\t", pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "invalid_code"
    assert "code must be a non-empty string" in result.message


@pytest.mark.parametrize("name", ["1A", "bad-name", "with space", "A.B"])
def test_invalid_pin_identifier_fails(name):
    result = _result("A = 1;", pins_out=[{"name": name}])

    assert result.ok is False
    assert result.code == "invalid_pin_name"
    assert name in result.message


@pytest.mark.parametrize("name", ["class", "namespace", "object", "ref"])
def test_reserved_keyword_pin_name_fails(name):
    result = _result("A = 1;", pins_out=[{"name": name}])

    assert result.ok is False
    assert result.code == "reserved_pin_name"
    assert name in result.message


def test_duplicate_pin_name_fails_case_sensitive_only():
    duplicate = _result(
        "A = R;",
        pins_in=[{"name": "A"}],
        pins_out=[{"name": "A"}],
    )
    distinct_by_case = _result(
        "a = A;",
        pins_in=[{"name": "A"}],
        pins_out=[{"name": "a"}],
    )

    assert duplicate.ok is False
    assert duplicate.code == "duplicate_pin_name"
    assert distinct_by_case.ok is True


@pytest.mark.parametrize(
    "code",
    [
        "public class MyComponent : GH_Component { }",
        "public class MyComponent:GH_Component { }",
        "public class MyComponent : Grasshopper.Kernel.GH_Component { }",
        "protected override void SolveInstance(IGH_DataAccess DA) { }",
        "protected override void RegisterInputParams(GH_InputParamManager pManager) { }",
        "protected override void RegisterOutputParams(GH_OutputParamManager pManager) { }",
    ],
)
def test_grasshopper_plugin_component_patterns_fail(code):
    result = _result(code, pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "wrong_component_category"
    assert "RhinoCode C# Script" in result.message


def test_plugin_component_pattern_fails_even_with_runscript_token():
    code = (
        "public class MyComponent : GH_Component {\n"
        "  private void RunScript(object R, ref object A) { A = R; }\n"
        "}\n"
    )

    result = _result(code, pins_in=[{"name": "R"}], pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "wrong_component_category"


def test_unrecognized_class_declaration_fails_in_body_mode():
    result = _result("public class Helper { }", pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "body_contains_class"
    assert "full source" in result.message


def test_top_level_using_fails_in_body_mode():
    result = _result("using Rhino.Geometry;\nA = new Point3d();", pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "body_contains_using"
    assert "body-style" in result.message


def test_top_level_using_allowed_in_recognized_full_source_mode():
    code = (
        "using Rhino.Geometry;\n"
        "public class Script_Instance : GH_ScriptInstance {\n"
        "  private void RunScript(ref object A) { A = Point3d.Origin; }\n"
        "}\n"
    )

    result = _result(code, pins_out=[{"name": "A"}], mode="auto")

    assert result.ok is True


def test_missing_output_assignment_is_not_a_hard_reject():
    result = _result(
        "var value = 1;",
        pins_out=[{"name": "A"}],
        mode="body",
    )

    assert result.ok is True


def test_helper_does_not_mutate_pin_inputs():
    pins_in = [{"name": "R", "type": "double"}]
    pins_out = [{"name": "A", "type": "double"}]
    before_in = copy.deepcopy(pins_in)
    before_out = copy.deepcopy(pins_out)

    result = _result("A = R;", pins_in=pins_in, pins_out=pins_out)

    assert result.ok is True
    assert pins_in == before_in
    assert pins_out == before_out
```

- [ ] **Step 2: Run helper tests and confirm they fail for missing module**

Run:

```powershell
pytest mcp_server/tests/test_gh_csharp_preflight.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'rook.gh_csharp_preflight'
```

- [ ] **Step 3: Keep failing helper tests local**

Do not commit the intentionally red helper tests. Leave
`mcp_server/tests/test_gh_csharp_preflight.py` unstaged until Task 2 makes the
helper tests green, then commit the tests and helper together.

---

## Task 2: Implement Helper And Shared Full-Source Predicate

**Files:**
- Create: `mcp_server/src/rook/gh_csharp_preflight.py`
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_gh_csharp_preflight.py`
- Test: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add the helper module**

Create `mcp_server/src/rook/gh_csharp_preflight.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_CSHARP_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOP_LEVEL_USING_RE = re.compile(r"^\s*using\s+[A-Za-z_][A-Za-z0-9_.]*\s*;", re.MULTILINE)
_CLASS_DECLARATION_RE = re.compile(r"\bclass\s+[A-Za-z_][A-Za-z0-9_]*\b")
_GH_COMPONENT_SUBCLASS_RE = re.compile(
    r":\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)*GH_Component\b"
)
_WRONG_COMPONENT_PATTERNS: tuple[str, ...] = (
    "SolveInstance",
    "RegisterInputParams",
    "RegisterOutputParams",
    "IGH_DataAccess",
    "GH_InputParamManager",
    "GH_OutputParamManager",
)

_CSHARP_RESERVED_KEYWORDS = frozenset({
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


@dataclass(frozen=True)
class CSharpScriptPreflightResult:
    ok: bool
    message: str | None = None
    code: str | None = None


def is_recognized_csharp_full_source(code: Any) -> bool:
    return isinstance(code, str) and (
        "class Script_Instance" in code or "void RunScript" in code
    )


def _failure(code: str, message: str) -> CSharpScriptPreflightResult:
    return CSharpScriptPreflightResult(ok=False, message=message, code=code)


def _pin_name(pin: Mapping[str, Any]) -> Any:
    return pin.get("name")


def _validate_pin_names(
    pins_in: Sequence[Mapping[str, Any]],
    pins_out: Sequence[Mapping[str, Any]],
) -> CSharpScriptPreflightResult | None:
    seen: set[str] = set()
    for direction, pins in (("input", pins_in), ("output", pins_out)):
        for pin in pins:
            name = _pin_name(pin)
            if not isinstance(name, str) or not name.strip():
                return _failure("invalid_pin_name", f"C# {direction} pin name must be a non-empty string.")
            stripped = name.strip()
            if not _CSHARP_IDENTIFIER_RE.match(stripped):
                return _failure(
                    "invalid_pin_name",
                    f"C# {direction} pin name '{stripped}' is not a valid C# identifier.",
                )
            if stripped in _CSHARP_RESERVED_KEYWORDS:
                return _failure(
                    "reserved_pin_name",
                    f"C# {direction} pin name '{stripped}' is a reserved C# keyword.",
                )
            if stripped in seen:
                return _failure(
                    "duplicate_pin_name",
                    f"C# pin name '{stripped}' is duplicated across the script signature.",
                )
            seen.add(stripped)
    return None


def preflight_csharp_script(
    *,
    code: Any,
    pins_in: Sequence[Mapping[str, Any]],
    pins_out: Sequence[Mapping[str, Any]],
    mode: str = "auto",
) -> CSharpScriptPreflightResult:
    if not isinstance(code, str) or not code.strip():
        return _failure("invalid_code", "C# script code must be a non-empty string.")

    pin_failure = _validate_pin_names(pins_in, pins_out)
    if pin_failure is not None:
        return pin_failure

    if _GH_COMPONENT_SUBCLASS_RE.search(code):
        return _failure(
            "wrong_component_category",
            (
                "C# script preflight failed because the code looks like a "
                "Grasshopper GH_Component plugin. RhinoCode C# Script expects "
                "body code or Script_Instance/RunScript source."
            ),
        )

    for pattern in _WRONG_COMPONENT_PATTERNS:
        if pattern in code:
            return _failure(
                "wrong_component_category",
                (
                    "C# script preflight failed because the code looks like a "
                    "Grasshopper GH_Component plugin. RhinoCode C# Script expects "
                    "body code or Script_Instance/RunScript source."
                ),
            )

    full_source = is_recognized_csharp_full_source(code)
    selected_mode = str(mode or "auto").strip().lower()
    body_style = selected_mode == "body" or (selected_mode == "auto" and not full_source)

    if body_style and _CLASS_DECLARATION_RE.search(code):
        return _failure(
            "body_contains_class",
            "C# body-style code cannot contain a class declaration; provide recognized full source instead.",
        )

    if body_style and _TOP_LEVEL_USING_RE.search(code):
        return _failure(
            "body_contains_using",
            "C# body-style code cannot contain top-level using directives.",
        )

    return CSharpScriptPreflightResult(ok=True)
```

- [ ] **Step 2: Run helper tests**

Run:

```powershell
pytest mcp_server/tests/test_gh_csharp_preflight.py -q
```

Expected:

```text
15 passed
```

The exact count may differ if parametrization expands differently. All tests in
the file must pass.

- [ ] **Step 3: Replace wrapper full-source detection**

Modify `mcp_server/src/rook/server.py` imports near the other local imports:

```python
from rook.gh_csharp_preflight import (
    is_recognized_csharp_full_source,
    preflight_csharp_script,
)
```

Then update `_build_gh_csharp_wrapper(...)`:

```python
    # Detect full-class code - pass through unchanged
    if is_recognized_csharp_full_source(code):
        return code
```

Do not change wrapper output formatting.

- [ ] **Step 4: Replace update full-source detection**

Inside `_prepare_gh_update_script_source(...)`, replace:

```python
        is_full_source = "class Script_Instance" in code or "void RunScript" in code
```

with:

```python
        is_full_source = is_recognized_csharp_full_source(code)
```

- [ ] **Step 5: Add shared-predicate regression tests**

Add these tests near the existing C# update source preparation tests in
`mcp_server/tests/test_server_contract_hardening.py`:

```python
def test_gh_csharp_wrapper_uses_shared_full_source_predicate():
    from rook.gh_csharp_preflight import is_recognized_csharp_full_source

    code = "public class Script_Instance : GH_ScriptInstance { }"

    assert is_recognized_csharp_full_source(code) is True
    assert server._build_gh_csharp_wrapper(
        code,
        pins_in=[{"name": "R"}],
        pins_out=[{"name": "A"}],
    ) == code


def test_gh_update_script_uses_shared_full_source_predicate():
    from rook.gh_csharp_preflight import is_recognized_csharp_full_source

    code = "private void RunScript(object R, ref object A) { A = R; }"

    assert is_recognized_csharp_full_source(code) is True
    prepared = server._prepare_gh_update_script_source(
        code=code,
        mode="auto",
        runtime={"component_type": "CSharpScriptComponent"},
        inputs=[{"name": "R"}],
        outputs=[{"name": "A"}],
        python_preamble=True,
    )

    assert prepared == {"source": code, "mode_used": "full_source", "wrapped": False}
```

- [ ] **Step 6: Run helper and server source-prep tests**

Run:

```powershell
pytest mcp_server/tests/test_gh_csharp_preflight.py mcp_server/tests/test_server_contract_hardening.py -q -k "gh_csharp_preflight or csharp_wrapper or gh_update_script_csharp or shared_full_source"
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit helper and shared predicate**

Run:

```powershell
git add mcp_server/src/rook/gh_csharp_preflight.py mcp_server/src/rook/server.py mcp_server/tests/test_gh_csharp_preflight.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: add C# script preflight helper"
```

---

## Task 3: Wire Create-Path Preflight Before `/gh/create-component`

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`

- [ ] **Step 1: Add failing create-path tests**

Append these tests to `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
@pytest.mark.asyncio
async def test_csharp_create_preflight_rejects_before_create_component(monkeypatch):
    from rook import server

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"guid": "created-guid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_create_script(
        "csharp",
        {
            "code": "public class MyComponent : GH_Component { }",
            "pins_in": [],
            "pins_out": ["A:object"],
        },
        port=9876,
        tool_name="gh_create_csharp_script",
    )

    assert result["success"] is False
    assert result["data"].startswith("C# script preflight failed:")
    assert calls == []


@pytest.mark.asyncio
async def test_unified_csharp_create_preflight_rejects_before_create_component(monkeypatch):
    from rook import server

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"guid": "created-guid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_create_script(
        "csharp",
        {
            "language": "csharp",
            "code": "using Rhino.Geometry;\nA = Point3d.Origin;",
            "pins_in": [],
            "pins_out": ["A:Point3d"],
        },
        port=9876,
        tool_name="gh_create_script",
    )

    assert result["success"] is False
    assert "top-level using" in result["data"]
    assert calls == []


@pytest.mark.asyncio
async def test_python_create_path_is_not_csharp_preflighted(monkeypatch):
    from rook import server

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        if endpoint == "/gh/create-component":
            return {"success": True, "data": {"guid": "python-guid"}}
        return {"success": True, "data": {}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server.asyncio, "sleep", AsyncMock())

    result = await server._execute_gh_create_script(
        "python",
        {
            "language": "python",
            "code": "A = 1",
            "pins_in": [],
            "pins_out": ["A:int"],
        },
        port=9876,
        tool_name="gh_create_script",
    )

    assert result["success"] is True
    assert calls[0][0] == "/gh/create-component"
```

Also add this import at the top of the file:

```python
from unittest.mock import AsyncMock
```

- [ ] **Step 2: Run create-path tests and confirm the new C# tests fail**

Run:

```powershell
pytest mcp_server/tests/test_rookchat_gh_script_creation_parity.py -q -k "preflight or python_create_path"
```

Expected before wiring:

```text
FAILED ... assert calls == []
```

The Python unaffected test may pass before wiring. The C# tests should fail
because `/gh/create-component` is still called.

- [ ] **Step 3: Wire create preflight in `_execute_gh_create_script(...)`**

In `mcp_server/src/rook/server.py`, after `pin_defs_in` and `pin_defs_out` are
normalized and after the existing "must provide pins" check, add:

```python
        if language == "csharp":
            preflight = preflight_csharp_script(
                code=code,
                pins_in=pin_defs_in,
                pins_out=pin_defs_out,
                mode="auto",
            )
            if not preflight.ok:
                return {
                    "success": False,
                    "data": f"C# script preflight failed: {preflight.message}",
                }
```

This block must appear before:

```python
        # Language-specific code preparation
```

and before any `call_rhino("/gh/create-component", ...)`.

- [ ] **Step 4: Run create-path tests**

Run:

```powershell
pytest mcp_server/tests/test_rookchat_gh_script_creation_parity.py -q -k "preflight or python_create_path"
```

Expected: selected tests pass.

- [ ] **Step 5: Commit create-path wiring**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_rookchat_gh_script_creation_parity.py
git commit -m "feat: preflight C# script creation before GH mutation"
```

---

## Task 4: Wire Update-Path Preflight Before `/gh/script` Write

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add failing update source-prep and mutation-blocking tests**

Add these tests near the existing `gh_update_script` tests in
`mcp_server/tests/test_server_contract_hardening.py`:

```python
def test_gh_update_script_csharp_preflight_rejects_body_using_before_wrap():
    with pytest.raises(ValueError, match="C# script preflight failed:"):
        server._prepare_gh_update_script_source(
            code="using Rhino.Geometry;\nA = Point3d.Origin;",
            mode="body",
            runtime={"component_type": "CSharpScriptComponent"},
            inputs=[],
            outputs=[{"name": "A", "type": "Point3d"}],
            python_preamble=True,
        )


@pytest.mark.asyncio
async def test_gh_update_script_csharp_preflight_blocks_script_write(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data or {}))
        if endpoint == "/gh/script" and method == "POST" and data == {"guid": "target-guid"}:
            return {
                "success": True,
                "data": {"Type": "CSharpScriptComponent"},
            }
        if endpoint == "/gh/component" and method == "GET":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [],
                        "Outputs": [{"Name": "A", "TypeName": "Point3d"}],
                    }
                },
            }
        raise AssertionError(f"unexpected mutation/read: {endpoint} {method} {data}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_update_script(
        {
            "guid": "target-guid",
            "language": "csharp",
            "code": "using Rhino.Geometry;\nA = Point3d.Origin;",
            "mode": "body",
        },
        port=9876,
    )

    assert result["success"] is False
    assert result["data"].startswith("gh_update_script failed: C# script preflight failed:")
    assert calls == [
        ("/gh/script", "POST", {"guid": "target-guid"}),
        ("/gh/component", "GET", {"guid": "target-guid"}),
    ]
```

- [ ] **Step 2: Run update tests and confirm they fail**

Run:

```powershell
pytest mcp_server/tests/test_server_contract_hardening.py -q -k "csharp_preflight"
```

Expected before wiring:

```text
FAILED ... DID NOT RAISE <class 'ValueError'>
```

or a failure showing `/gh/script` write was attempted.

- [ ] **Step 3: Wire preflight into `_prepare_gh_update_script_source(...)`**

Inside the C# runtime branch of `_prepare_gh_update_script_source(...)`, after
`is_full_source = is_recognized_csharp_full_source(code)`, add preflight before
any return/wrap:

```python
        preflight_mode = "full_source" if (
            selected_mode == "full_source" or (selected_mode == "auto" and is_full_source)
        ) else "body"
        preflight = preflight_csharp_script(
            code=code,
            pins_in=inputs,
            pins_out=outputs,
            mode=preflight_mode,
        )
        if not preflight.ok:
            raise ValueError(f"C# script preflight failed: {preflight.message}")
```

Keep the existing full-source mode validation immediately after this block:

```python
        if selected_mode == "full_source":
            if not is_full_source:
                raise ValueError("C# full_source mode requires Script_Instance or RunScript source")
            return {"source": code, "mode_used": "full_source", "wrapped": False}
```

This preserves the current update failure wrapper:

```python
{"success": False, "data": "gh_update_script failed: C# script preflight failed: ..."}
```

- [ ] **Step 4: Run update tests**

Run:

```powershell
pytest mcp_server/tests/test_server_contract_hardening.py -q -k "csharp_preflight or gh_update_script_csharp"
```

Expected: selected tests pass.

- [ ] **Step 5: Commit update-path wiring**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: preflight C# script updates before script write"
```

---

## Task 5: Add Non-Live Integration Regressions And Boundary Checks

**Files:**
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Optional Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Add dispatcher alias normalization regression**

Add this test to `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
@pytest.mark.asyncio
async def test_dispatcher_csharp_alias_normalized_script_reaches_preflight(monkeypatch):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"guid": "created-guid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_csharp_script",
        {
            "params": {
                "script": "public class MyComponent : GH_Component { }",
                "pins_out": [{"name": "A", "type": "object"}],
            },
            "name": "Invalid Component",
        },
    )

    assert result["success"] is False
    assert result["data"].startswith("C# script preflight failed:")
    assert calls == []
```

- [ ] **Step 2: Add `gh_set_script` non-migration regression**

Add this test to `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
def test_gh_set_script_transform_remains_raw_escape_hatch():
    from rook.agent.tool_dispatcher import _transform_gh_set_script

    endpoint, method, payload = _transform_gh_set_script(
        {
            "guid": "script-guid",
            "script": "public class MyComponent : GH_Component { }",
        }
    )

    assert endpoint == "/gh/script"
    assert method == "POST"
    assert payload == {
        "guid": "script-guid",
        "script": "public class MyComponent : GH_Component { }",
    }
```

- [ ] **Step 3: Add optional ToolResultView regression if useful**

If LM1B coverage does not already make this redundant, add this small test to
`mcp_server/tests/test_rookchat_tool_contracts.py`:

```python
def test_tool_result_view_marks_csharp_preflight_failure_failed():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    view = normalize_tool_result({
        "success": False,
        "data": "C# script preflight failed: C# body-style code cannot contain top-level using directives.",
    })

    assert view.status == "failed"
```

Do not add ChatRunner event/history tests. LM1C does not change ChatRunner.

- [ ] **Step 4: Run boundary tests**

Run:

```powershell
pytest mcp_server/tests/test_rookchat_gh_script_creation_parity.py mcp_server/tests/test_rookchat_tool_contracts.py -q -k "preflight or gh_set_script_transform or ToolResultView or tool_result_view"
```

Expected: selected tests pass.

- [ ] **Step 5: Commit boundary regressions**

Run:

```powershell
git add mcp_server/tests/test_rookchat_gh_script_creation_parity.py mcp_server/tests/test_rookchat_tool_contracts.py
git commit -m "test: cover LM1C non-live mutation boundaries"
```

If `test_rookchat_tool_contracts.py` was not changed because the optional test
was skipped, omit it from `git add`.

---

## Task 6: Focused Verification And Hygiene

**Files:**
- Verify only; no planned code changes.

- [ ] **Step 1: Run helper tests**

Run:

```powershell
pytest mcp_server/tests/test_gh_csharp_preflight.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run focused create/update/script contract tests**

Run:

```powershell
pytest `
  mcp_server/tests/test_rookchat_gh_script_creation_parity.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  -q -k "csharp or gh_create_script or gh_update_script or preflight or gh_set_script_transform or tool_result_view"
```

Expected: all selected tests pass.

- [ ] **Step 3: Run adjacent RookChat contract tests**

Run:

```powershell
pytest `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_gh_script_creation_parity.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 4: Compile changed Python files**

Run:

```powershell
python -m py_compile `
  mcp_server/src/rook/gh_csharp_preflight.py `
  mcp_server/src/rook/server.py
```

Expected: no output and exit code 0.

- [ ] **Step 5: Run diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

- `git diff --check` exits 0.
- No unrelated files are staged or modified.
- Runtime/cache artifacts remain unstaged and uncommitted if present.

- [ ] **Step 6: Final commit if verification changed files**

If verification revealed tiny test or formatting fixes, commit them:

```powershell
git add <specific changed files>
git commit -m "test: verify LM1C C# preflight"
```

If no files changed, do not create an empty commit.

---

## Review Checkpoints

Use Subagent-Driven execution with review after:

- Task 2: helper contract and shared predicate are the core semantic boundary.
- Task 4: update-path wiring is the highest-risk mutation boundary.
- Task 6: final verification before PR.

Stop immediately if an implementation task requires:

- touching `chat_runner.py`;
- changing public MCP formatting;
- changing `ToolDispatcher.dispatch()` semantics;
- validating raw `gh_set_script`;
- adding C# compilation;
- rejecting missing output assignment.

Those are outside LM1C.

---

## Self-Review Against Spec

- Shared helper outside `server.py`: Task 2.
- Shared full-source predicate: Task 2.
- Create preflight before `/gh/create-component`: Task 3.
- Update preflight before `/gh/script` write: Task 4.
- Deterministic non-live tests: Tasks 1, 3, 4, 5.
- Existing result shape and LM1B interaction: Tasks 3, 4, optional Task 5.
- `gh_set_script` escape hatch preserved: Task 5.
- No output-assignment hard reject: Task 1.
- No ChatRunner event wiring: scope guardrails and review checkpoints.
- No live Rhino: all commands are plain pytest/py_compile.
