# RookChat GH Script Tier-0 Affordance Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GH script creation/update tools visible in the initial RookChat agent tool surface so weaker local models do not treat `gh_errors` as the only available GH script-adjacent affordance.

**Architecture:** Add the script creation/update tools to `AGENT_TIER_0` only. Keep strict schemas and strict `gh_errors` argument rejection unchanged. Lock the behavior with non-live tests over actual initial active schemas and a first-round transcript flow.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, existing RookChat `ChatRunner`, `ToolRegistry`, and tool tier definitions.

---

## Branch And Hygiene

- Work on `codex/rookchat-gh-script-tier0-affordance`.
- Keep `knowledge/contextual_mab.pkl` and `knowledge/substrate_observations.jsonl` unstaged.
- Do not deploy or run live Rhino as part of this implementation plan.
- Do not change C# panel files, tool schemas, dispatcher malformed-call behavior, or prompt text.

---

## File Structure

- Modify `mcp_server/src/rook/agent/tool_groups.py`
  - Add GH script creation/update tools to `AGENT_TIER_0`.

- Modify `mcp_server/tests/test_rookchat_tool_schema_golden.py`
  - Add tests for the default initial active schema set exposed by a default `ChatRunner`.

- Modify `mcp_server/tests/test_rookchat_tool_transcripts.py`
  - Add a transcript regression proving `gh_create_csharp_script` can run in the first tool round without a preceding `request_tools` result.

---

## Task 1: Initial Active Schema Affordance Tests

**Files:**
- Modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`
- Later implementation target: `mcp_server/src/rook/agent/tool_groups.py`

- [ ] **Step 1: Write failing initial-active-schema tests**

Append this code to `mcp_server/tests/test_rookchat_tool_schema_golden.py`:

```python
def _initial_agent_schemas():
    from rook.agent.chat.chat_runner import ChatRunner

    return _schema_by_name(ChatRunner()._registry.get_active_schemas())


def test_initial_agent_schemas_include_csharp_script_creation_affordance():
    schemas = _initial_agent_schemas()

    assert "gh_create_csharp_script" in schemas
    csharp_params = schemas["gh_create_csharp_script"]["function"]["parameters"]
    assert csharp_params["additionalProperties"] is False
    assert csharp_params["required"] == ["code", "pins_in", "pins_out"]


def test_initial_agent_schemas_keep_gh_errors_zero_argument():
    schemas = _initial_agent_schemas()

    assert schemas["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_initial_agent_schemas_include_script_create_update_family():
    schemas = _initial_agent_schemas()

    for tool_name in (
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
        "gh_update_script",
    ):
        assert tool_name in schemas
        assert schemas[tool_name]["function"]["parameters"]["additionalProperties"] is False
```

- [ ] **Step 2: Run tests to verify red**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py -q
```

Expected failure:

```text
AssertionError: assert 'gh_create_csharp_script' in schemas
```

or equivalent missing-key assertion for the new initial active schema tests.

- [ ] **Step 3: Stop at red**

Do not implement until the failing tests prove the initial schema affordance is missing.

---

## Task 2: Add GH Script Tools To Agent Tier 0

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Test: `mcp_server/tests/test_rookchat_tool_schema_golden.py`

- [ ] **Step 1: Add script tools to `AGENT_TIER_0`**

In `mcp_server/src/rook/agent/tool_groups.py`, update `AGENT_TIER_0` from:

```python
AGENT_TIER_0: Set[str] = (TIER_0 - {"gh_execute_intent"}) | {
    "gh_snapshot",
    "session_history",       # per-command success/failure for post-execution verification
    "rhino_command_interactive_prompt",  # Rhino prompt state — detect non-idle after execution
    "ui_block",              # Adaptive UI pseudo-tool (intercepted by ChatRunner)
}
```

to:

```python
AGENT_TIER_0: Set[str] = (TIER_0 - {"gh_execute_intent"}) | {
    "gh_snapshot",
    "gh_create_script",
    "gh_create_python_script",
    "gh_create_csharp_script",
    "gh_update_script",
    "session_history",       # per-command success/failure for post-execution verification
    "rhino_command_interactive_prompt",  # Rhino prompt state — detect non-idle after execution
    "ui_block",              # Adaptive UI pseudo-tool (intercepted by ChatRunner)
}
```

Do not remove `gh_errors` from `TIER_0` or `READONLY_TIER_0`.

- [ ] **Step 2: Run schema golden tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Commit Task 1-2**

Stage only:

```powershell
git add mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_rookchat_tool_schema_golden.py
git commit -m "fix(chat): expose GH script tools in initial agent surface"
```

---

## Task 3: First-Round Transcript Regression

**Files:**
- Modify: `mcp_server/tests/test_rookchat_tool_transcripts.py`

- [ ] **Step 1: Add first-round transcript test**

Append this test to `mcp_server/tests/test_rookchat_tool_transcripts.py`:

```python
@pytest.mark.asyncio
async def test_csharp_script_creation_can_run_first_round_without_request_tools():
    tool_results = {
        "gh_create_csharp_script": {
            "success": True,
            "data": {
                "component_guid": "script-guid",
                "name": "Box Maker",
                "pins_out": ["B:Brep"],
            },
        },
        "gh_errors": {
            "success": True,
            "data": {"errorCount": 0, "warningCount": 0},
        },
    }
    dispatched = []

    async def executor(name, params):
        dispatched.append(name)
        if name == "request_tools":
            raise AssertionError("request_tools must not be needed for first-round script creation")
        return tool_results[name]

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(
            _ToolCall(
                "call_create",
                "gh_create_csharp_script",
                {
                    "code": (
                        "var box = new Rhino.Geometry.Box("
                        "Rhino.Geometry.Plane.WorldXY, "
                        "new Rhino.Geometry.Interval(0, 10), "
                        "new Rhino.Geometry.Interval(0, 10), "
                        "new Rhino.Geometry.Interval(0, 10)); "
                        "B = box.ToBrep();"
                    ),
                    "pins_in": [],
                    "pins_out": ["B:Brep"],
                    "name": "Box Maker",
                },
            )
        ),
        _tool_stream(_ToolCall("call_errors", "gh_errors", {})),
        _text_stream("Created Box Maker. gh_errors returned 0 errors and 0 warnings."),
    ]

    events, conv = await _collect_events(runner, responses)

    tool_result_events = [
        event for event in events
        if event.type == "tool_result"
    ]
    assert [event.name for event in tool_result_events] == [
        "gh_create_csharp_script",
        "gh_errors",
    ]
    assert "request_tools" not in [event.name for event in tool_result_events]
    assert dispatched == ["gh_create_csharp_script", "gh_errors"]
    assert tool_result_events[0].tool_status == "success"
    assert tool_result_events[1].tool_status == "success"
    assert conv.messages[-1]["role"] == "assistant"
    assert "0 errors" in conv.messages[-1]["content"]
```

This explicitly locks the reviewer note: no `request_tools` result appears before `gh_create_csharp_script`.

- [ ] **Step 2: Run transcript tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_transcripts.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Commit Task 3**

Stage only:

```powershell
git add mcp_server/tests/test_rookchat_tool_transcripts.py
git commit -m "test(chat): allow first-round GH script creation transcript"
```

---

## Task 4: Focused Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run hotfix-focused Python tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py tests/test_rookchat_tool_transcripts.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 2: Run prompt/runner regression tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_prompt_builder.py tests/test_chat_runner.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Check branch and whitespace**

Run:

```powershell
cd C:\UDEV\Rook
git fetch origin --prune
git rev-list --left-right --count origin/main...HEAD
git diff --check origin/main...HEAD
git status --short --branch
```

Expected:

- branch is current with `origin/main`;
- `git diff --check` exits 0;
- working-tree dirt remains limited to:

```text
 M knowledge/contextual_mab.pkl
 M knowledge/substrate_observations.jsonl
```

- [ ] **Step 4: Request review**

Summarize:

- root cause: `gh_errors` was visible before script creation tools;
- change: GH script create/update tools added to `AGENT_TIER_0`;
- no schema loosening, no malformed-call auto-routing, no prompt hacks;
- test evidence;
- no live Rhino/deploy claim.

Do not merge locally without review approval.

---

## Self-Review

### Spec Coverage

- Initial affordance fix: Task 2 changes `AGENT_TIER_0`.
- Keep `gh_errors` strict: Task 1 verifies zero-argument schema remains exposed.
- Verify active schemas, not only set membership: Task 1 uses `ChatRunner()._registry.get_active_schemas()`.
- First-round behavior: Task 3 proves `gh_create_csharp_script` can run before any `request_tools` result.
- Non-goals: no task changes schemas, dispatcher routing, prompt text, C# UI, deploy scripts, or live Rhino behavior.

### Placeholder Scan

No placeholder markers are intentionally present. Commands and expected outcomes are concrete.

### Type Consistency

The plan uses existing names exactly:

- `AGENT_TIER_0`
- `ChatRunner`
- `_schema_by_name`
- `_ToolCall`
- `_tool_stream`
- `_text_stream`
- `gh_create_csharp_script`
- `gh_errors`
