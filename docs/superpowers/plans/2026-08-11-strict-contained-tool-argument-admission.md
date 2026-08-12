# Strict Contained-Tool Argument Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `rook_tools_call` target reject unknown top-level arguments from its authoritative live schema before target dispatch.

**Architecture:** Extend the existing pure `capability_index.validate_arguments(schema, arguments)` owner with deterministic top-level unknown-field validation. Keep `server._handle_meta_tool()` guard ordering and the existing `invalid_arguments` envelope unchanged; focused causal tests prove malformed discovery/metadata calls make zero target calls.

**Tech Stack:** Python 3.11, pytest, MCP Python SDK, existing Rook capability index and meta-tool dispatcher.

## Global Constraints

- Baseline is exact merge `06534f371b173308179164189e54b722a34f8a24` plus the approved specification commit.
- No new production module or dependency.
- No aliases, spelling correction, retry, fallback, recursive JSON Schema validator, Prime change, skill change, prompt change, call budget, planner, or critic.
- Preserve direct `server.call_tool()` and ChatRunner behavior.
- Preserve recursion, readonly-wall, dispatchability, and object-admission ordering.
- An unknown-field refusal makes zero target, Rhino, Grasshopper, provider, or external calls.

---

### Task 1: Strict generic top-level admission

**Files:**
- Modify: `mcp_server/src/rook/capability_index.py:134-160`
- Modify: `mcp_server/tests/test_capability_index.py:157-180`
- Modify: `mcp_server/tests/test_rook_tools_meta.py:137-145`

**Interfaces:**
- Consumes: `validate_arguments(schema: Mapping, arguments: Mapping) -> list[str]`
- Produces: the same signature and existing error list, with deterministic unknown-field evidence first
- Preserves: `server._handle_meta_tool()` and its existing `invalid_arguments` envelope

- [ ] **Step 1: Add pure RED regressions for unknown fields**

Add to `test_capability_index.py`:

```python
def test_validate_arguments_rejects_unknown_fields_with_complete_accepted_list():
    schema = {
        "type": "object",
        "properties": {
            "search": {"type": "string"},
            "limit": {"type": "integer"},
            "exact": {"type": "boolean"},
        },
    }
    assert validate_arguments(schema, {"zeta": 1, "query": "Series"}) == [
        "unknown fields: query, zeta; accepted fields: exact, limit, search"
    ]


def test_validate_arguments_reports_no_accepted_fields_for_zero_argument_schema():
    assert validate_arguments(
        {"type": "object", "properties": {}}, {"query": "Series"}
    ) == ["unknown fields: query; accepted fields: <none>"]


def test_validate_arguments_unknown_error_precedes_existing_errors():
    schema = {
        "type": "object",
        "required": ["limit"],
        "properties": {"limit": {"type": "integer"}},
    }
    assert validate_arguments(schema, {"query": "Series"}) == [
        "unknown fields: query; accepted fields: limit",
        "limit: required field missing",
    ]
```

- [ ] **Step 2: Run the pure tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'C:/UDEV/Rook/.worktrees/strict-contained-tool-argument-admission/mcp_server/src'
& 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_capability_index.py -q
```

Expected: exactly the three new tests fail because unknown fields currently pass through.

- [ ] **Step 3: Add contained-call RED regressions with zero target contact**

Add to `test_rook_tools_meta.py`:

```python
@pytest.mark.parametrize(
    ("target", "arguments", "accepted"),
    [
        ("gh_library", {"query": "Series"}, "search"),
        ("gh_batch_component_info", {"name": "Series"}, "names"),
    ],
)
def test_rook_tools_call_rejects_unknown_target_fields_before_dispatch(
    monkeypatch, target, arguments, accepted
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    dispatched = AsyncMock()
    monkeypatch.setattr(server, "call_tool", dispatched)

    result = asyncio.run(
        server._handle_meta_tool(
            "rook_tools_call",
            {"name": target, "arguments": arguments},
            server.Profile.FULL,
        )
    )
    payload = json.loads(result[0].text)

    assert payload["error"] == "invalid_arguments"
    assert payload["name"] == target
    assert payload["fields"][0].startswith("unknown fields:")
    assert accepted in payload["fields"][0]
    dispatched.assert_not_awaited()


def test_rook_tools_call_valid_target_arguments_dispatch_once_unchanged(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    dispatched = AsyncMock(return_value=[server.TextContent(type="text", text="ok")])
    monkeypatch.setattr(server, "call_tool", dispatched)
    arguments = {"search": "Series", "exact": True, "limit": 5}

    asyncio.run(
        server._handle_meta_tool(
            "rook_tools_call",
            {"name": "gh_library", "arguments": arguments},
            server.Profile.FULL,
        )
    )

    dispatched.assert_awaited_once_with("gh_library", arguments)
```

- [ ] **Step 4: Run contained-call tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'C:/UDEV/Rook/.worktrees/strict-contained-tool-argument-admission/mcp_server/src'
& 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_rook_tools_meta.py `
  -k 'unknown_target_fields or valid_target_arguments' -q
```

Expected: the unknown-field cases fail because the mocked target is awaited; the valid case passes or exposes only fixture details that must be corrected without changing its assertion.

- [ ] **Step 5: Implement the minimal validator correction**

At the start of `validate_arguments()` after `props` is computed, add:

```python
    unknown = sorted(key for key in arguments if key not in props)
    if unknown:
        accepted = sorted(props)
        errors.append(
            f"unknown fields: {', '.join(unknown)}; accepted fields: "
            f"{', '.join(accepted) if accepted else '<none>'}"
        )
```

Do not change any server dispatch code or existing validation clauses.

- [ ] **Step 6: Run focused GREEN tests**

Run:

```powershell
$env:PYTHONPATH = 'C:/UDEV/Rook/.worktrees/strict-contained-tool-argument-admission/mcp_server/src'
$python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
& $python -m pytest `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_rook_tools_meta.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Run adjacent no-contact regression seams**

Run:

```powershell
$env:PYTHONPATH = 'C:/UDEV/Rook/.worktrees/strict-contained-tool-argument-admission/mcp_server/src'
$python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
& $python -m pytest `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_lm_surface_smoke.py -q
```

Expected: all tests pass with only previously documented warnings.

- [ ] **Step 8: Verify source scope and compile**

Run:

```powershell
$python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
& $python -m py_compile `
  mcp_server/src/rook/capability_index.py `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_rook_tools_meta.py
git diff --check
git diff --stat 06534f371b173308179164189e54b722a34f8a24
git status --short
```

Expected production scope: one modified production module; tests and approved documentation only.

- [ ] **Step 9: Commit the implementation**

```powershell
git add -- `
  mcp_server/src/rook/capability_index.py `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_rook_tools_meta.py
git commit -m 'fix: reject unknown contained tool arguments'
```

---

### Task 2: Final verification and architecture reconciliation

**Files:**
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Modify: `docs/superpowers/plans/2026-08-11-strict-contained-tool-argument-admission.md`

**Interfaces:**
- Consumes: approved Task 1 behavior and test evidence
- Produces: durable architecture statement and verification ledger

- [ ] **Step 1: Add one architecture sentence**

In the progressive-disclosure gateway section of `CURRENT_ARCHITECTURE.md`, record:

```text
rook_tools_call validates the untrusted target argument object against the target's live
top-level schema before re-entering dispatch; unknown fields return invalid_arguments and do
not contact the target.
```

- [ ] **Step 2: Run the prescribed focused and adjacent seams again**

Repeat Task 1 Steps 6–8 from the committed Task 1 state. Record exact pass counts, warning
counts, production additions/deletions, and the final file scope under an execution ledger
heading at the end of this plan.

- [ ] **Step 3: Run a no-contact full Python regression suite**

Run:

```powershell
$env:PYTHONPATH = 'C:/UDEV/Rook/.worktrees/strict-contained-tool-argument-admission/mcp_server/src'
& 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe' -m pytest `
  mcp_server/tests -q
```

Record any known baseline failures by exact identity. Stop if a new failure appears.

- [ ] **Step 4: Commit reconciliation**

```powershell
git add -- docs/CURRENT_ARCHITECTURE.md `
  docs/superpowers/plans/2026-08-11-strict-contained-tool-argument-admission.md
git commit -m 'docs: reconcile strict argument admission'
```

- [ ] **Step 5: Publication and deployment gate**

Push the exact reviewed head, open a PR, verify remote base/head and scope, merge normally,
then deploy the clean merge SHA once using the standard Release path. Do not run a model until
the installed `rook/server.py` hash matches the merge source and restarted live
`rook_tools_read` exposes the expected discovery schemas.

- [ ] **Step 6: Nemotron qualification gate**

Prepare one fresh disposable Prime row by reusing the proven V3 adapter, skill, operator,
evidence, target, and assessment contracts unchanged. Change only the predeclared
provider/model/reasoning fields required for the selected installed Nemotron model. Perform
an inert provider-wire capture, freeze a fresh empty target, then execute exactly one model
row with the same intent and one final operator snapshot. No Qwen rerun belongs to this task.
