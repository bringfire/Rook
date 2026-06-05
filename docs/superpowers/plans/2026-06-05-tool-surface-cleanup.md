# Tool Surface Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize parsing of the public MCP `call_tool()` wire shape into one blessed leaf module, migrate the router-plane live harnesses (p3–p6) onto it, and pin `server._format_tool_result()` with a contract test so the formatter and its inverse parser cannot silently drift.

**Architecture:** A new parser-only leaf module `mcp_server/src/rook/tool_result.py` reads the wire shape (`call_tool()` returns `list[TextContent]`; success text is `json.dumps(data)` — the `data` only; failure text is `"Error: " + (json.dumps(data) | str(data))`). It imports nothing from `server` — the `call_tool` dependency is injected — so it stays a leaf and the contract test is the only place the two sides meet. The four router-plane live harnesses drop their duplicated `_text`/`_json` helpers and call the module. The strict success parser (raises instead of returning a silent `{}`) is the behavioral improvement.

**Tech Stack:** Python 3.10+ (editable install — pure-Python edits need no rebuild for pytest), `pytest`, `mcp.types.TextContent`. Spec: `docs/superpowers/specs/2026-06-05-tool-surface-cleanup-design.md`.

**Pytest binary:** `mcp_server/.venv/Scripts/python.exe -m pytest`

---

## Setup

- [ ] **Create the feature branch off `main`** (spec is already on `main`+origin):

```bash
cd C:/Users/aryan/source/repos/Rook
git checkout main
git checkout -b feature/tool-surface-cleanup
```

---

## Task 1: Module + text-level primitives (`text_from_call_tool_result`, `is_error_result`)

**Files:**
- Create: `mcp_server/src/rook/tool_result.py`
- Test: `mcp_server/tests/test_tool_result.py`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_tool_result.py`:

```python
import asyncio
import json

import pytest
from mcp.types import TextContent

from rook import server
from rook.tool_result import (
    call_tool_data,
    is_error_result,
    parse_call_tool_data,
    parse_call_tool_error,
    text_from_call_tool_result,
)


def _wire(text: str) -> list[TextContent]:
    """Build a call_tool()-shaped result list carrying exactly `text`."""
    return [TextContent(type="text", text=text)]


def test_text_from_result_returns_payload():
    assert text_from_call_tool_result(_wire("hello")) == "hello"


def test_text_from_empty_result_is_blank():
    assert text_from_call_tool_result([]) == ""


def test_is_error_result_true_on_error_prefix():
    assert is_error_result(_wire("Error: boom")) is True


def test_is_error_result_false_on_success_text():
    assert is_error_result(_wire(json.dumps({"ok": 1}))) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -v`
Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'rook.tool_result'`.

- [ ] **Step 3: Create the module with the two text primitives**

Create `mcp_server/src/rook/tool_result.py`:

```python
"""Read the public MCP ``call_tool()`` wire shape — the inverse of
``server._format_tool_result``.

``call_tool()`` returns ``list[TextContent]``. On success the single text item is
``json.dumps(data)`` (the ``data`` only). On failure it is
``"Error: " + (json.dumps(data) | str(data))``. These helpers parse that wire shape and
import nothing from ``server`` (``call_tool`` is injected), so this stays a leaf module.

See ``docs/CURRENT_ARCHITECTURE.md`` "Tool Result Surface" and issue #218.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

_ERROR_PREFIX = "Error: "


def text_from_call_tool_result(result: Any) -> str:
    """The single text payload of a ``call_tool()`` result list (``""`` if empty)."""
    if not result:
        return ""
    return result[0].text


def is_error_result(result: Any) -> bool:
    """True iff the wire text is a failure. Text-based only — no JSON, no inference."""
    return text_from_call_tool_result(result).startswith(_ERROR_PREFIX)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/tool_result.py mcp_server/tests/test_tool_result.py
git commit -m "feat(tool-surface): tool_result module + text_from_call_tool_result/is_error_result"
```

---

## Task 2: `parse_call_tool_data` (strict success parser)

**Files:**
- Modify: `mcp_server/src/rook/tool_result.py`
- Test: `mcp_server/tests/test_tool_result.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_tool_result.py`:

```python
def test_parse_data_returns_success_dict():
    assert parse_call_tool_data(_wire(json.dumps({"a": 1, "b": [2]}))) == {"a": 1, "b": [2]}


def test_parse_data_raises_on_error_result():
    with pytest.raises(ValueError):
        parse_call_tool_data(_wire("Error: nope"))


def test_parse_data_raises_on_non_json():
    with pytest.raises(ValueError):
        parse_call_tool_data(_wire("not json at all"))


def test_parse_data_raises_on_non_dict_json():
    # success text that parses to a JSON list/str/number is a contract violation
    with pytest.raises(ValueError):
        parse_call_tool_data(_wire(json.dumps([1, 2, 3])))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -k parse_data -v`
Expected: FAIL — `ImportError`/`AttributeError` (`parse_call_tool_data` not defined yet; the import at the top of the test file fails).

- [ ] **Step 3: Implement `parse_call_tool_data`**

Append to `mcp_server/src/rook/tool_result.py`:

```python
def parse_call_tool_data(result: Any) -> dict[str, Any]:
    """SUCCESS-only: the parsed ``data`` dict.

    Raises ``ValueError`` if the result is an error, the text is not JSON, or the parsed
    JSON is not a dict. Never returns ``{}`` silently.
    """
    text = text_from_call_tool_result(result)
    if text.startswith(_ERROR_PREFIX):
        raise ValueError(f"expected a success result, got an error: {text!r}")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"success text is not JSON: {text!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"success data is not a dict (got {type(data).__name__}): {text!r}"
        )
    return data
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/tool_result.py mcp_server/tests/test_tool_result.py
git commit -m "feat(tool-surface): strict parse_call_tool_data (raises on error/non-JSON/non-dict)"
```

---

## Task 3: `parse_call_tool_error` (failure parser, dict-or-raw)

**Files:**
- Modify: `mcp_server/src/rook/tool_result.py`
- Test: `mcp_server/tests/test_tool_result.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_tool_result.py`:

```python
def test_parse_error_returns_dict_for_json_error():
    res = _wire("Error: " + json.dumps({"code": "rhino_session_not_found", "retryable": False}))
    assert parse_call_tool_error(res) == {"code": "rhino_session_not_found", "retryable": False}


def test_parse_error_returns_raw_string_for_plain_error():
    assert parse_call_tool_error(_wire("Error: boom")) == "boom"


def test_parse_error_returns_raw_string_for_brace_non_json():
    # the tricky case: looks JSON-ish (has a brace) but is not valid JSON -> raw, no raise
    assert parse_call_tool_error(_wire("Error: {not json")) == "{not json"


def test_parse_error_raises_on_success_result():
    with pytest.raises(ValueError):
        parse_call_tool_error(_wire(json.dumps({"ok": 1})))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -k parse_error -v`
Expected: FAIL — import of `parse_call_tool_error` fails (not defined yet).

- [ ] **Step 3: Implement `parse_call_tool_error`**

Append to `mcp_server/src/rook/tool_result.py`:

```python
def parse_call_tool_error(result: Any) -> dict[str, Any] | str:
    """FAILURE-only: the error payload — a dict when JSON, else the raw string.

    Raises ``ValueError`` if the result is actually a success.
    """
    text = text_from_call_tool_result(result)
    if not text.startswith(_ERROR_PREFIX):
        raise ValueError(f"expected an error result, got a success: {text!r}")
    payload = text[len(_ERROR_PREFIX):]
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return payload
    return parsed if isinstance(parsed, dict) else payload
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/tool_result.py mcp_server/tests/test_tool_result.py
git commit -m "feat(tool-surface): parse_call_tool_error (dict-or-raw, robust to brace non-JSON)"
```

---

## Task 4: `call_tool_data` (DI convenience)

**Files:**
- Modify: `mcp_server/src/rook/tool_result.py`
- Test: `mcp_server/tests/test_tool_result.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_tool_result.py`:

```python
def test_call_tool_data_returns_success_dict():
    async def fake_call_tool(name, arguments):
        assert name == "some_tool" and arguments == {"x": 1}
        return _wire(json.dumps({"ok": True}))

    assert asyncio.run(call_tool_data(fake_call_tool, "some_tool", {"x": 1})) == {"ok": True}


def test_call_tool_data_propagates_error_as_valueerror():
    async def fake_call_tool(name, arguments):
        return _wire("Error: boom")

    with pytest.raises(ValueError):
        asyncio.run(call_tool_data(fake_call_tool, "some_tool", {}))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -k call_tool_data -v`
Expected: FAIL — import of `call_tool_data` fails (not defined yet).

- [ ] **Step 3: Implement `call_tool_data`**

Append to `mcp_server/src/rook/tool_result.py`:

```python
async def call_tool_data(
    call_tool: Callable[[str, dict[str, Any]], Awaitable[Any]],
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """``await call_tool(name, arguments)`` then ``parse_call_tool_data``. Strict —
    propagates ``ValueError`` if the tool returned an error result. ``call_tool`` is
    injected (callers pass ``server.call_tool``) so this module never imports ``server``.
    """
    return parse_call_tool_data(await call_tool(name, arguments))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/tool_result.py mcp_server/tests/test_tool_result.py
git commit -m "feat(tool-surface): call_tool_data DI convenience (no server import)"
```

---

## Task 5: Formatter contract test (the anti-drift pin)

**Files:**
- Test: `mcp_server/tests/test_tool_result.py`

This task imports the real `server._format_tool_result` and asserts that the parsers are its inverse. The implementations already exist, so these tests should pass on first run — if any fails, the parser and formatter disagree and the **parser** must be fixed to match the formatter (the formatter's public behavior is load-bearing; do not change it).

- [ ] **Step 1: Write the contract tests**

Append to `mcp_server/tests/test_tool_result.py`:

```python
# --- Contract: parsers are the inverse of server._format_tool_result -----------------

def test_contract_success_dict_roundtrips():
    data = {"artifacts": [{"path": "p"}], "n": 1}
    rendered = server._format_tool_result({"success": True, "data": data})
    assert not is_error_result(rendered)
    assert parse_call_tool_data(rendered) == data


def test_contract_error_dict_roundtrips():
    data = {"code": "rhino_session_not_found", "retryable": False}
    rendered = server._format_tool_result({"success": False, "data": data})
    assert is_error_result(rendered)
    assert parse_call_tool_error(rendered) == data


def test_contract_error_string_roundtrips():
    rendered = server._format_tool_result({"success": False, "data": "boom"})
    assert is_error_result(rendered)
    assert parse_call_tool_error(rendered) == "boom"


def test_contract_success_parser_rejects_error_envelope():
    rendered = server._format_tool_result({"success": False, "data": {"code": "x"}})
    with pytest.raises(ValueError):
        parse_call_tool_data(rendered)


def test_contract_error_parser_rejects_success_envelope():
    rendered = server._format_tool_result({"success": True, "data": {"k": 1}})
    with pytest.raises(ValueError):
        parse_call_tool_error(rendered)
```

- [ ] **Step 2: Run the contract tests**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -k contract -v`
Expected: 5 passed. (If a roundtrip fails, fix the parser to match `_format_tool_result`, not the formatter.)

- [ ] **Step 3: Run the whole module test file**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_tool_result.py -v`
Expected: 19 passed.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_tool_result.py
git commit -m "test(tool-surface): pin _format_tool_result with parser roundtrip contract"
```

---

## Task 6: Refactor p3 harness onto `tool_result`

**Files:**
- Modify: `mcp_server/tools/p3_session_mutation_live_harness.py`

p3 uses `_text` + a domain `_object_count` (which carries the envelope-hedge scar) and otherwise does substring smokes on error text. Per spec §5, the substring smokes stay as `text_from_call_tool_result(...)`; the success reads move to `parse_call_tool_data`; the "did it error" check moves to `is_error_result`.

- [ ] **Step 1: Add the import** (after the existing `from rook import ...` block, around line 54, keeping the `# noqa: E402` style):

```python
from rook.tool_result import (  # noqa: E402
    is_error_result,
    parse_call_tool_data,
    text_from_call_tool_result,
)
```

- [ ] **Step 2: Delete the local `_text` helper (lines 62-63) and the `_object_count` helper (lines 66-74).**

Remove:

```python
def _text(result) -> str:
    return result[0].text if result else ""


def _object_count(text: str) -> int:
    try:
        d = json.loads(text)
        if isinstance(d, dict):
            inner = d.get("data") if isinstance(d.get("data"), dict) else {}
            return int(d.get("objectCount") or inner.get("objectCount") or 0)
    except Exception:
        pass
    return -1
```

- [ ] **Step 3: Rewrite `scenario_session_routes_mutation`** to read structured success data and use the error predicate. Replace the whole function body with:

```python
async def scenario_session_routes_mutation(pid: int) -> None:
    # Prove a mutation actually LANDS in the named session: read objectCount before and
    # after, through the SAME session. Reads succeed (parse strictly); the create is an
    # outcome we inspect ("not an error" + a concrete count delta).
    sess = f"rhino-{pid}"
    before = parse_call_tool_data(await server.call_tool("rhino_document", {"session": sess}))
    create = await server.call_tool(
        "rhino_execute",
        {"session": sess, "code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"},
    )
    after = parse_call_tool_data(await server.call_tool("rhino_document", {"session": sess}))
    created_ok = not is_error_result(create)
    before_n = int(before.get("objectCount") or 0)
    after_n = int(after.get("objectCount") or 0)
    readback_ok = after_n > before_n
    _record(
        "session_routes_mutation", created_ok and readback_ok,
        f"created_ok={created_ok}, before={before_n}, after={after_n}",
    )
```

- [ ] **Step 4: Rename the remaining generic reads** in `scenario_bogus_session`, `scenario_disambiguates`, `scenario_conflict`, and `scenario_non_routed_reject`: replace every `_text(` with `text_from_call_tool_result(`. These are §5 substring smokes — the `in` / `.startswith("Error:")` checks on the returned text are unchanged. Example (`scenario_bogus_session`):

```python
async def scenario_bogus_session(pid: int) -> None:
    txt = text_from_call_tool_result(await server.call_tool(
        "rhino_execute", {"session": "rhino-99999999", "code": "print(1)"}
    ))
    _record("bogus_session_not_found", "rhino_session_not_found" in txt, txt[:160])
```

- [ ] **Step 5: Verify no leftover `_text(` / `_object_count(` references remain and the file compiles**

Run:
```bash
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tools/p3_session_mutation_live_harness.py
grep -nE "_text\(|_object_count" mcp_server/tools/p3_session_mutation_live_harness.py
```
Expected: `py_compile` exits 0; `grep` prints nothing (no leftovers).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/tools/p3_session_mutation_live_harness.py
git commit -m "refactor(p3): use rook.tool_result; remove _object_count envelope-hedge scar"
```

---

## Task 7: Refactor p4 harness onto `tool_result`

**Files:**
- Modify: `mcp_server/tools/p4_workbench_lifecycle_live_harness.py`

p4's launch/list/owned-close are success reads; the `not_owned` close (step 4) is a structured-error branch (reads `.get("code")`), so per §5 it uses `parse_call_tool_error` when the result is an error.

- [ ] **Step 1: Add the import** (after the existing `from rook import ...` block):

```python
from rook.tool_result import (  # noqa: E402
    is_error_result,
    parse_call_tool_data,
    parse_call_tool_error,
    text_from_call_tool_result,
)
```

- [ ] **Step 2: Delete the local `_text` (lines 40-41) and `_json` (lines 44-53) helpers.**

- [ ] **Step 3: Convert the success reads** — replace each `_json(_text(await server.call_tool(...)))` with `parse_call_tool_data(await server.call_tool(...))`. Sites: launch (step 1), `rhino_workbench_list` (steps 2 and 6), and the owned `rhino_workbench_close` (step 5). Example for launch:

```python
        out = parse_call_tool_data(await server.call_tool(
            "rhino_workbench_launch", {"readinessTimeoutSeconds": 120}))
        launched_session = out.get("session")
        ok = out.get("owned") is True and out.get("mode") == "workbench" and bool(launched_session)
        _record("workbench_launch", ok, f"session={launched_session} port={out.get('port')}")
```

- [ ] **Step 4: Convert the p3-route mutation (step 3)** to the error predicate:

```python
        mut = await server.call_tool(
            "rhino_execute",
            {"session": launched_session, "code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"})
        _record("p3_route_into_workbench", not is_error_result(mut),
                text_from_call_tool_result(mut)[:120])
```

- [ ] **Step 5: Convert the `not_owned` close (step 4)** — this branches on structured error data, so use `parse_call_tool_error` for the error case (§5):

```python
        # closing the RUNNER's Rhino (adopted, not owned) fails closed; does NOT kill it
        r = await server.call_tool("rhino_workbench_close", {"session": f"rhino-{runner_pid}"})
        not_owned = parse_call_tool_error(r) if is_error_result(r) else parse_call_tool_data(r)
        not_owned = not_owned if isinstance(not_owned, dict) else {}
        _record("close_adopted_is_not_owned",
                not_owned.get("code") == "not_owned", json.dumps(not_owned)[:120])
```

- [ ] **Step 6: Verify the file compiles and has no leftover helpers**

Run:
```bash
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tools/p4_workbench_lifecycle_live_harness.py
grep -nE "_text\(|_json\(|def _text|def _json" mcp_server/tools/p4_workbench_lifecycle_live_harness.py
```
Expected: `py_compile` exits 0; `grep` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/tools/p4_workbench_lifecycle_live_harness.py
git commit -m "refactor(p4): use rook.tool_result; structured not_owned via parse_call_tool_error"
```

---

## Task 8: Refactor p5 harness onto `tool_result`

**Files:**
- Modify: `mcp_server/tools/p5_registry_reclaim_live_harness.py`

p5's `call_tool` sites are success reads (launch, and the close near the end); its registry/SQL/`workbench._*` calls are not `call_tool` and are untouched.

- [ ] **Step 1: Add the import** (after the existing `from rook import ...` block):

```python
from rook.tool_result import parse_call_tool_data  # noqa: E402
```

- [ ] **Step 2: Delete the local `_text` (lines 41-42) and `_json` (lines 45-52) helpers.**

- [ ] **Step 3: Convert the launch read (step 1)** to `parse_call_tool_data`:

```python
        out = parse_call_tool_data(await server.call_tool(
            "rhino_workbench_launch", {"readinessTimeoutSeconds": 120}))
        session = out.get("session")
        _record("launch", out.get("owned") is True and bool(session), f"session={session}")
```

- [ ] **Step 4: Convert the close-after-reclaim read (harness step 4, ~line 102)** to `parse_call_tool_data` (it inspects `.get("closed")`):

```python
        closed = parse_call_tool_data(await server.call_tool(
            "rhino_workbench_close", {"session": session}))
        if closed.get("closed"):
            session = None
        _record("close_after_reclaim", closed.get("closed") is True,
                f"cleanupStatus={closed.get('cleanupStatus')}")
```

The `finally`-block close (`await server.call_tool("rhino_workbench_close", {"session": session})`) is fire-and-forget — its result is not parsed — so it needs no change. p5 has no bare `_text(...)` substring checks and no structured-error branches.

- [ ] **Step 5: Verify the file compiles and has no leftover helpers**

Run:
```bash
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tools/p5_registry_reclaim_live_harness.py
grep -nE "_text\(|_json\(|def _text|def _json" mcp_server/tools/p5_registry_reclaim_live_harness.py
```
Expected: `py_compile` exits 0; `grep` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/tools/p5_registry_reclaim_live_harness.py
git commit -m "refactor(p5): use rook.tool_result for call_tool reads"
```

---

## Task 9: Refactor p6 harness onto `tool_result`

**Files:**
- Modify: `mcp_server/tools/p6_artifact_perception_live_harness.py`

p6 is where the original footgun lived. Its `rhino_workbench_launch` is the canonical **outcome branch** (success or failure both valid); `_artifacts()`/`_rows_by_path` read success data; the close is a success read.

- [ ] **Step 1: Add the import** (the file already imports `server`, `artifacts`, and `workbench as _wb`; add the helper import alongside, keeping `# noqa: E402`):

```python
from rook.tool_result import is_error_result, parse_call_tool_data  # noqa: E402
```

- [ ] **Step 2: Delete the local `_text` (lines 54-55) and `_json` (lines 58-65) helpers.**

- [ ] **Step 3: Rewrite `_artifacts`** to parse success data directly (drop the `_json(_text(...))` wrapper):

```python
async def _artifacts() -> dict:
    return _rows_by_path(parse_call_tool_data(await server.call_tool("rhino_artifacts", {})))
```

(`_rows_by_path` is unchanged — it already operates on the parsed `{"artifacts": [...]}` dict.)

- [ ] **Step 4: Rewrite the launch site in `_attempt`** as an explicit outcome branch:

```python
    r = await server.call_tool("rhino_workbench_launch", {"readinessTimeoutSeconds": 120})
    if is_error_result(r):
        return ("launch_failed", None, None)
    out = parse_call_tool_data(r)
    session = out.get("session")
    if not (out.get("owned") and session):
        return ("launch_failed", session, None)
```

- [ ] **Step 5: Convert the owned `rhino_workbench_close` read in `main`** (the `closed = _json(_text(...))` site) to `parse_call_tool_data`:

```python
        closed = parse_call_tool_data(await server.call_tool(
            "rhino_workbench_close", {"session": session}))
        if closed.get("closed"):
            session = None
```

The other `await server.call_tool(...)` calls in p6 (`rhino_create`, `rhino_document_ops` save, `rhino_workbench_list`, `rhino_artifact_deregister`) are fire-and-forget (their results are not parsed) and need no change.

- [ ] **Step 6: Verify the file compiles and has no leftover helpers**

Run:
```bash
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/tools/p6_artifact_perception_live_harness.py
grep -nE "def _text|def _json|_json\(_text" mcp_server/tools/p6_artifact_perception_live_harness.py
```
Expected: `py_compile` exits 0; `grep` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/tools/p6_artifact_perception_live_harness.py
git commit -m "refactor(p6): use rook.tool_result; explicit launch outcome branch"
```

---

## Task 10: Baseline parity, scope note, gated live re-verify, finish

**Files:**
- Verify only (no new source).

- [ ] **Step 1: Run the full non-live gate and capture the summary**

Run:
```bash
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE
git checkout -- knowledge/ ; rm -rf knowledge/selectors
```
Expected: `test_tool_result.py` contributes **19 passed**; the `failed` and `errors` counts are **UNCHANGED** vs `main`'s baseline (the module + its tests are purely additive; the harness edits live in `mcp_server/tools/`, which pytest does not collect). Record the summary line.

- [ ] **Step 2: Confirm baseline parity against `main`**

The merge gate is: `failed` and `errors` identical to `main`; `passed` increased by exactly the new `test_tool_result.py` count (19). If `failed`/`errors` moved, investigate before proceeding — a regression, not parity.

- [ ] **Step 3: Add the scope note to issue #218**

```bash
gh issue comment 218 --body "PR establishes the blessed rook.tool_result helper, pins _format_tool_result with a roundtrip contract test, and migrates the router-plane live harnesses (p3-p6). Broad test-suite migration (~52 ad-hoc-parsing files) is intentionally deferred to opportunistic / separate low-risk cleanup."
```

- [ ] **Step 4: GATED — live re-verify the refactored harnesses (needs Rhino).**

**Checkpoint with the user before running** (launches real Rhino). The unit + contract tests cover the module; this covers the harness migration. Run at least the p6 smoke (the one whose bug motivated this), ideally p3/p4/p5 too:

```bash
mcp_server/.venv/Scripts/python.exe scripts/run_rhino_runtime_harness.py --smoke p6-artifact-perception
```
Expected: `=== P6 live smoke: 4/4 PASS ===`. (Repeat with `--smoke p3-session-mutation`, `p4-workbench-lifecycle`, `p5-registry-reclaim` as the user approves.)

- [ ] **Step 5: Finish the branch**

REQUIRED SUB-SKILL: Use **superpowers:finishing-a-development-branch**. Push + open a PR for Codex review (do not self-merge — the user pulls the merge trigger). PR body must carry: the parser-only-leaf design, the strict-success behavioral change, the contract-test pin, the surgical p3–p6 scope with the deferral note, and the baseline-parity numbers. After approval: `gh pr merge <n> --squash --delete-branch`.

---

## Notes for the implementer

- **Editable install:** pure-Python edits are picked up by pytest with no rebuild.
- **`knowledge/` hygiene:** before any commit, if `git status` shows changes under `knowledge/`, run `git checkout -- knowledge/ && rm -rf knowledge/selectors` (a test side effect, never committed).
- **Do not touch:** `server._format_tool_result` (formatter stays), `p2_bridge_diagnosis_live_harness.py` (bridge/HTTP-level), the `gh_*` harnesses, and the ~52 ad-hoc-parsing test files (deferred).
- **§5 rule (normative):** substring-via-`text_from_call_tool_result` is fine for "an error happened" / existing smoke checks; **any branch on structured error data must use `parse_call_tool_error`**.
