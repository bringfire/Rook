# DG-009 GH Progressive Discovery Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Codex exact-name searches for hidden GH scripting/readiness tools discover the existing `rook_tools_*` progressive-disclosure gateway, while preserving the lean profile boundary.

**Architecture:** Keep hidden GH tools out of `PUBLIC_LEAN_TOOL_NAMES`. Enrich only the advertised `rook_tools_search`, `rook_tools_read`, and `rook_tools_call` descriptions with compact DG-009 aliases so outer Codex `tool_search` can route agents to the gateway. Add unit and deployed-runtime smoke coverage that explicitly forces `ROOK_MCP_TOOL_PROFILE=lean`, then verifies gateway metadata and internal exact-name resolution.

**Tech Stack:** Python 3.12, MCP `Tool` objects, `pytest`, existing `scripts/lm_surface_smoke.py`.

---

## File Structure

- Modify `mcp_server/src/rook/server.py`
  - Add a compact DG-009 GH alias sentence to the advertised descriptions for `rook_tools_search`, `rook_tools_read`, and `rook_tools_call`.
  - Do not change tool profile allowlists or dispatch routing.
- Modify `mcp_server/tests/test_rook_tools_meta.py`
  - Add tests proving lean-advertised gateway metadata contains exact DG-009 aliases.
  - Add tests proving `rook_tools_search` and `rook_tools_read` resolve all DG-009 names internally.
- Modify `mcp_server/tests/test_server_tool_profiles.py`
  - Add a regression that hidden GH mutators remain out of lean while the gateway remains in lean.
- Modify `scripts/lm_surface_smoke.py`
  - Add a `progressive` subcommand that runs against the deployed runtime with `ROOK_MCP_TOOL_PROFILE=lean`.
  - Validate gateway advertised metadata plus internal exact-name resolution.
- Modify `mcp_server/tests/test_lm_surface_smoke.py`
  - Test the new parser command and pure progressive-validation helper.

## Constants

Use this DG-009 exact-name set in tests and smoke code:

```python
DG009_GH_TOOL_NAMES = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_status",
    "gh_create_csharp_script",
    "gh_snapshot",
)
```

Use this hidden-mutator subset to prove lean was not widened:

```python
DG009_HIDDEN_GH_MUTATORS = {
    "gh_update_script",
    "gh_set_script_pins",
    "gh_create_csharp_script",
}
```

### Task 1: Add failing progressive metadata tests

**Files:**
- Modify: `mcp_server/tests/test_rook_tools_meta.py`
- Modify: `mcp_server/tests/test_server_tool_profiles.py`

- [ ] **Step 1: Add gateway metadata and internal-resolution tests**

Append this to `mcp_server/tests/test_rook_tools_meta.py`:

```python
DG009_GH_TOOL_NAMES = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_status",
    "gh_create_csharp_script",
    "gh_snapshot",
)


def _lean_tool_descriptions(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    return {tool.name: tool.description for tool in asyncio.run(server.list_tools())}


def test_lean_gateway_metadata_contains_dg009_exact_gh_aliases(monkeypatch):
    descriptions = _lean_tool_descriptions(monkeypatch)
    for gateway in ("rook_tools_search", "rook_tools_read", "rook_tools_call"):
        assert gateway in descriptions
        desc = descriptions[gateway]
        for tool_name in DG009_GH_TOOL_NAMES:
            assert tool_name in desc


def test_rook_tools_search_exact_dg009_gh_names_resolve_real_records(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    for tool_name in DG009_GH_TOOL_NAMES:
        found = json.loads(_text("rook_tools_search", {"query": tool_name, "limit": 10}))
        assert any(entry["name"] == tool_name for entry in found), tool_name


def test_rook_tools_read_exact_dg009_gh_names_return_schemas(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    for tool_name in DG009_GH_TOOL_NAMES:
        record = json.loads(_text("rook_tools_read", {"name": tool_name}))
        assert record["name"] == tool_name
        assert record["domain"] == "gh"
        assert record["mcp_dispatchable"] is True
        assert isinstance(record["input_schema"], dict)
        assert record["input_schema"].get("type") == "object"
```

- [ ] **Step 2: Add the lean-boundary regression**

Append this to `mcp_server/tests/test_server_tool_profiles.py`:

```python
def test_lean_keeps_dg009_hidden_gh_mutators_behind_gateway(monkeypatch):
    lean = _list_names(monkeypatch, "lean")
    assert {"rook_tools_search", "rook_tools_read", "rook_tools_call"} <= lean
    assert {
        "gh_update_script",
        "gh_set_script_pins",
        "gh_create_csharp_script",
    }.isdisjoint(lean)
```

- [ ] **Step 3: Run tests to verify the metadata test fails**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path mcp_server/src).Path
python -m pytest `
  mcp_server/tests/test_rook_tools_meta.py::test_lean_gateway_metadata_contains_dg009_exact_gh_aliases `
  mcp_server/tests/test_server_tool_profiles.py::test_lean_keeps_dg009_hidden_gh_mutators_behind_gateway `
  -q
```

Expected: the gateway metadata test fails because at least one DG-009 alias is not present in the current `rook_tools_*` descriptions. The lean-boundary regression should pass.

### Task 2: Enrich `rook_tools_*` advertised metadata

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_rook_tools_meta.py`
- Test: `mcp_server/tests/test_server_tool_profiles.py`

- [ ] **Step 1: Add compact aliases to `rook_tools_search`**

In `mcp_server/src/rook/server.py`, update the `description` for `Tool(name="rook_tools_search", ...)` to include this final sentence inside the existing parenthesized string:

```python
"Exact hidden GH aliases resolve through this gateway, including "
"gh_update_script, gh_set_script_pins, gh_status, gh_create_csharp_script, "
"and gh_snapshot."
```

The resulting description should still say this is the catalog search gateway and should not imply those tools are directly advertised in lean.

- [ ] **Step 2: Add compact aliases to `rook_tools_read`**

Update the `description` for `Tool(name="rook_tools_read", ...)` to include this final sentence:

```python
"Use this after searching exact hidden GH names such as gh_update_script, "
"gh_set_script_pins, gh_status, gh_create_csharp_script, and gh_snapshot."
```

- [ ] **Step 3: Add compact aliases to `rook_tools_call`**

Update the `description` for `Tool(name="rook_tools_call", ...)` to include this final sentence:

```python
"For hidden GH tools discovered by name, this invokes targets such as "
"gh_update_script, gh_set_script_pins, gh_status, gh_create_csharp_script, "
"and gh_snapshot through the normal policy path."
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path mcp_server/src).Path
python -m pytest `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_tool_profiles.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1-2 changes**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_rook_tools_meta.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "fix(capability-index): expose GH aliases through progressive gateway metadata"
```

### Task 3: Add lean deployed-runtime progressive smoke

**Files:**
- Modify: `scripts/lm_surface_smoke.py`
- Modify: `mcp_server/tests/test_lm_surface_smoke.py`

- [ ] **Step 1: Add pure validation helper tests**

Append this to `mcp_server/tests/test_lm_surface_smoke.py`:

```python
def test_progressive_parser_accepts_progressive():
    args = SMOKE.build_parser().parse_args(["progressive"])
    assert args.command == "progressive"


def test_progressive_gateway_metadata_validation_requires_aliases():
    catalog = {
        "rook_tools_search": {"description": "Search gh_update_script gh_set_script_pins gh_status gh_create_csharp_script gh_snapshot"},
        "rook_tools_read": {"description": "Read gh_update_script gh_set_script_pins gh_status gh_create_csharp_script gh_snapshot"},
        "rook_tools_call": {"description": "Call gh_update_script gh_set_script_pins gh_status gh_create_csharp_script gh_snapshot"},
    }
    assert SMOKE.progressive_gateway_metadata_failures(catalog) == []
    bad = dict(catalog)
    bad["rook_tools_search"] = {"description": "Search tools"}
    assert "rook_tools_search missing gh_update_script" in SMOKE.progressive_gateway_metadata_failures(bad)


def test_progressive_search_validation_requires_exact_records():
    search_results = {
        name: [{"name": name, "domain": "gh"}]
        for name in SMOKE.DG009_GH_TOOL_NAMES
    }
    assert SMOKE.progressive_search_failures(search_results) == []
    bad = dict(search_results)
    bad["gh_update_script"] = [{"name": "gh_set_script", "domain": "gh"}]
    assert "rook_tools_search did not return gh_update_script" in SMOKE.progressive_search_failures(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path mcp_server/src).Path
python -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py::test_progressive_parser_accepts_progressive `
  mcp_server/tests/test_lm_surface_smoke.py::test_progressive_gateway_metadata_validation_requires_aliases `
  mcp_server/tests/test_lm_surface_smoke.py::test_progressive_search_validation_requires_exact_records `
  -q
```

Expected: failures for missing parser command and missing helper functions.

- [ ] **Step 3: Add constants and validation helpers**

In `scripts/lm_surface_smoke.py`, after `_EXPECTED_EXCLUDED`, add:

```python
DG009_GH_TOOL_NAMES = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_status",
    "gh_create_csharp_script",
    "gh_snapshot",
)

PROGRESSIVE_GATEWAY_NAMES = (
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
)


def progressive_gateway_metadata_failures(catalog: dict) -> list[str]:
    failures: list[str] = []
    for gateway in PROGRESSIVE_GATEWAY_NAMES:
        record = catalog.get(gateway)
        if not isinstance(record, dict):
            failures.append(f"{gateway} missing from lean catalog")
            continue
        description = str(record.get("description") or "")
        for tool_name in DG009_GH_TOOL_NAMES:
            if tool_name not in description:
                failures.append(f"{gateway} missing {tool_name}")
    return failures


def progressive_search_failures(search_results: dict[str, list[dict]]) -> list[str]:
    failures: list[str] = []
    for tool_name in DG009_GH_TOOL_NAMES:
        entries = search_results.get(tool_name, [])
        if not any(entry.get("name") == tool_name and entry.get("domain") == "gh" for entry in entries):
            failures.append(f"rook_tools_search did not return {tool_name}")
    return failures
```

- [ ] **Step 4: Add `run_progressive()`**

In `scripts/lm_surface_smoke.py`, after `run_external()`, add:

```python
def run_progressive() -> int:
    print("== progressive ==")
    previous_profile = os.environ.get("ROOK_MCP_TOOL_PROFILE")
    os.environ["ROOK_MCP_TOOL_PROFILE"] = "lean"
    try:
        rc = _check_origins()
        if rc != 0:
            _p("FAIL", "origin guard failed; refusing progressive disclosure smoke")
            return rc

        import asyncio

        from rook.server import call_tool, list_tools
        from rook.agent.tool_registry import build_catalog_from_mcp_tools

        tools = asyncio.run(list_tools())
        catalog = build_catalog_from_mcp_tools(tools)
        names = set(catalog)
        hidden_mutators = {"gh_update_script", "gh_set_script_pins", "gh_create_csharp_script"}
        if not set(PROGRESSIVE_GATEWAY_NAMES) <= names:
            missing = sorted(set(PROGRESSIVE_GATEWAY_NAMES) - names)
            _p("FAIL", f"lean catalog missing progressive gateways: {missing}")
            return 1
        if hidden_mutators & names:
            _p("FAIL", f"lean catalog directly advertised hidden GH mutators: {sorted(hidden_mutators & names)}")
            return 1

        metadata_failures = progressive_gateway_metadata_failures(catalog)
        if metadata_failures:
            for failure in metadata_failures:
                _p("FAIL", failure)
            return 1

        search_results: dict[str, list[dict]] = {}
        for tool_name in DG009_GH_TOOL_NAMES:
            response = asyncio.run(call_tool("rook_tools_search", {"query": tool_name, "limit": 10}))
            import json
            search_results[tool_name] = json.loads(response[0].text)
        search_failures = progressive_search_failures(search_results)
        if search_failures:
            for failure in search_failures:
                _p("FAIL", failure)
            return 1

        _p("PASS", "progressive disclosure smoke passed under lean")
        return 0
    finally:
        if previous_profile is None:
            os.environ.pop("ROOK_MCP_TOOL_PROFILE", None)
        else:
            os.environ["ROOK_MCP_TOOL_PROFILE"] = previous_profile
```

- [ ] **Step 5: Wire the parser and main dispatcher**

Update the parser choices:

```python
parser.add_argument("command", choices=("coherence", "surface", "external", "progressive"))
```

Update `main(argv)`:

```python
if args.command == "coherence":
    return run_coherence()
if args.command == "surface":
    return run_surface()
if args.command == "external":
    return run_external()
return run_progressive()
```

- [ ] **Step 6: Run smoke tests**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path mcp_server/src).Path
python -m pytest mcp_server/tests/test_lm_surface_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3 changes**

Run:

```powershell
git add scripts/lm_surface_smoke.py mcp_server/tests/test_lm_surface_smoke.py
git commit -m "test(capability-index): smoke progressive GH discovery under lean"
```

### Task 4: Final verification and review

**Files:**
- No new files.

- [ ] **Step 1: Run focused Python suite**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path mcp_server/src).Path
python -m pytest `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_lm_surface_smoke.py `
  mcp_server/tests/test_capability_index.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run a live source-path progressive smoke**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path mcp_server/src).Path
python - <<'PY'
import os
from pathlib import Path
os.environ["ROOK_MCP_TOOL_PROFILE"] = "lean"
from rook import server
import asyncio, json
async def main():
    tools = {tool.name: tool.description for tool in await server.list_tools()}
    assert "gh_update_script" not in tools
    assert "rook_tools_search" in tools
    assert "gh_update_script" in tools["rook_tools_search"]
    out = await server.call_tool("rook_tools_search", {"query": "gh_update_script", "limit": 10})
    records = json.loads(out[0].text)
    assert any(r["name"] == "gh_update_script" for r in records)
asyncio.run(main())
print("PASS")
PY
```

Expected: `PASS`.

- [ ] **Step 3: Request code review**

Request review against `origin/main` with this scope:

- Gateway metadata only.
- Lean profile must remain unchanged.
- `scripts/lm_surface_smoke.py progressive` must force `ROOK_MCP_TOOL_PROFILE=lean`.
- No LM2A, native, or managed bridge changes.

- [ ] **Step 4: Address reviewer feedback**

Fix any Critical or Important review findings. Re-run the focused suite from Step 1 after any fix.
