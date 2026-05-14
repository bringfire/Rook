# GH Edit Partial Failure Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `gh_edit` partial and no-mutation failures impossible for RookChat agents to confuse with success, then migrate the final contract to strict failure semantics after a caller audit.

**Architecture:** Add one shared Python contract helper for `gh_edit` result classification and promotion, then wire both the direct MCP path and the chat/agent dispatcher through it. Keep Phase 1 compatibility for partial mutations, but immediately return `success: false` for no-mutation `edit_summary.errors`; Phase 3 flips partial mutations to strict failure after the audit.

**Tech Stack:** Python MCP server (`mcp_server/src/rook`), pytest contract tests (`mcp_server/tests`), managed C# Grasshopper status bridge (`src/Rook/InternalBridge`, `src/Rook/Handlers`) for the GH health slice.

---

## File Map

- Create `mcp_server/src/rook/gh_edit_contract.py`: shared `gh_edit` result classifier and contract applicator.
- Create `mcp_server/tests/test_gh_edit_contract.py`: focused unit tests for no-mutation vs partial-mutation error classification.
- Modify `mcp_server/src/rook/server.py`: replace `_attach_gh_edit_partial_warnings` with the shared helper and preserve MCP-visible payload fields.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`: apply the shared helper on chat/agent `gh_edit` results.
- Modify `mcp_server/src/rook/agent/chat/prompt_builder.py`: harden `ui_block`, partial-success, and verified-result guidance.
- Modify `mcp_server/src/rook/agent/tool_groups.py`: expose `gh_status` in the GH canvas group so agents can run the read-only health check before GH edits.
- Create `docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md`: required Phase 2 caller audit table.
- GH health files for Task 7: `src/Rook/InternalBridge/GrasshopperCore.cs`, `src/Rook/Handlers/GrasshopperHandler.cs`, and Python tool schemas/dispatchers for `gh_status` response-shape tests.

## Task 1: Shared `gh_edit` Contract Helper

**Files:**
- Create: `mcp_server/src/rook/gh_edit_contract.py`
- Test: `mcp_server/tests/test_gh_edit_contract.py`

- [ ] **Step 1: Write failing tests for no-mutation and partial-mutation errors**

Create `mcp_server/tests/test_gh_edit_contract.py`:

```python
from rook.gh_edit_contract import apply_gh_edit_contract


def test_no_mutation_edit_errors_become_failure_without_partial_success():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 0,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": ["Create failed: Centre Box not found"],
            }
        },
    }

    contracted = apply_gh_edit_contract(result, strict_partial_success=False)

    assert contracted["success"] is False
    assert contracted["verified"] is False
    assert contracted["errors"] == ["Create failed: Centre Box not found"]
    assert "partial_success" not in contracted
    assert contracted["data"]["errors"] == ["Create failed: Centre Box not found"]
    assert contracted["data"]["warnings"] == ["Create failed: Centre Box not found"]
    assert contracted["data"]["verified"] is False
    assert "failed before applying any mutations" in contracted["data"]["verification_note"]
    assert "failed before applying any mutations" in contracted["verification_note"]


def test_partial_mutation_edit_errors_are_compat_success_but_unverified():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 2,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": ["connect: param not found for 'T1.O0>T2.I3'"],
                "temp_id_map": {"T1": "G1"},
                "instance_guids": {"T1": "guid-1"},
            }
        },
    }

    contracted = apply_gh_edit_contract(result, strict_partial_success=False)

    assert contracted["success"] is True
    assert contracted["partial_success"] is True
    assert contracted["verified"] is False
    assert contracted["errors"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["partial_success"] is True
    assert contracted["data"]["errors"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["verified"] is False
    assert "partially applied" in contracted["data"]["verification_note"]
    assert "partially applied" in contracted["verification_note"]


def test_partial_mutation_edit_errors_flip_to_strict_failure_when_enabled():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 1,
                "errors": ["group: failed"],
            }
        },
    }

    contracted = apply_gh_edit_contract(result, strict_partial_success=True)

    assert contracted["success"] is False
    assert contracted["partial_success"] is True
    assert contracted["verified"] is False


def test_clean_edit_result_is_returned_unchanged():
    result = {"success": True, "data": {"edit_summary": {"created": 1}}}

    assert apply_gh_edit_contract(result) is result
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_contract.py -q
```

Expected: import failure for `rook.gh_edit_contract`.

- [ ] **Step 3: Implement the helper**

Create `mcp_server/src/rook/gh_edit_contract.py`:

```python
"""Shared gh_edit result contract helpers.

The helper is used by both MCP-facing and chat/agent-facing paths so partial
edit semantics cannot drift between transports.
"""

from __future__ import annotations

from typing import Any


_MUTATION_COUNT_KEYS: tuple[str, ...] = (
    "created",
    "deleted",
    "values_set",
    "connected",
    "disconnected",
    "groups_created",
    "groups_deleted",
    "groups_updated",
    "grouped",
    "ungrouped",
)


def _merge_unique(*issue_lists: Any) -> list[str]:
    merged: list[str] = []
    for issues in issue_lists:
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if isinstance(issue, str) and issue not in merged:
                merged.append(issue)
    return merged


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def extract_edit_summary(result: dict[str, Any]) -> dict[str, Any] | None:
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    summary = data.get("edit_summary")
    return summary if isinstance(summary, dict) else None


def extract_edit_errors(result: dict[str, Any]) -> list[str]:
    summary = extract_edit_summary(result)
    if summary is None:
        return []
    return _merge_unique(summary.get("errors"))


def has_mutation_evidence(result: dict[str, Any]) -> bool:
    summary = extract_edit_summary(result)
    if summary is None:
        return False

    if any(_positive_int(summary.get(key)) for key in _MUTATION_COUNT_KEYS):
        return True

    for key in ("temp_id_map", "instance_guids"):
        value = summary.get(key)
        if isinstance(value, dict) and len(value) > 0:
            return True

    return bool(summary.get("mutation_applied") is True)


def apply_gh_edit_contract(
    result: dict[str, Any],
    *,
    strict_partial_success: bool = False,
) -> dict[str, Any]:
    """Promote gh_edit nested errors into the agent-visible contract.

    Phase 1 uses ``strict_partial_success=False``. Partial mutations retain
    transport compatibility via ``success: true`` but are marked unverified.
    No-mutation errors are failures immediately.
    """

    if not isinstance(result, dict):
        return result

    errors = extract_edit_errors(result)
    if not errors:
        return result

    mutation_applied = has_mutation_evidence(result)

    contracted = dict(result)
    data = contracted.get("data")
    data = dict(data) if isinstance(data, dict) else {"result": data}

    data["errors"] = _merge_unique(data.get("errors"), errors)
    data["warnings"] = _merge_unique(data.get("warnings"), errors)
    contracted["errors"] = _merge_unique(contracted.get("errors"), errors)
    contracted["verified"] = False
    data["verified"] = False

    if mutation_applied:
        contracted["partial_success"] = True
        data["partial_success"] = True
        if strict_partial_success:
            contracted["success"] = False
        verification_note = (
            "gh_edit partially applied. Inspect edit_summary.errors and the "
            "returned snapshot before continuing; remediate incrementally, "
            "undo, or clean up before retrying."
        )
    else:
        contracted["success"] = False
        contracted.pop("partial_success", None)
        data.pop("partial_success", None)
        verification_note = (
            "gh_edit failed before applying any mutations. Inspect "
            "edit_summary.errors, fix the request, then retry."
        )

    contracted["verification_note"] = verification_note
    data["verification_note"] = verification_note
    contracted["data"] = data
    return contracted
```

- [ ] **Step 4: Run the helper tests and verify they pass**

Run:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_contract.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add mcp_server/src/rook/gh_edit_contract.py mcp_server/tests/test_gh_edit_contract.py
git commit -m "test: define gh_edit partial failure contract"
```

## Task 2: Wire MCP `gh_edit` Through the Shared Contract

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_gh_edit_postmortem.py`

- [ ] **Step 1: Extend MCP tests for no-mutation and partial-mutation behavior**

In `mcp_server/tests/test_gh_edit_postmortem.py`, update `_decode_response` so
structured error payloads remain inspectable:

```python
def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        raw = text[len("Error: "):]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        return {"success": False, "data": data}
    return {"success": True, "data": json.loads(text)}
```

Then add:

```python
@pytest.mark.asyncio
async def test_gh_edit_no_mutation_errors_return_failure(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        return {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 0,
                    "deleted": 0,
                    "values_set": 0,
                    "connected": 0,
                    "disconnected": 0,
                    "errors": ["Create failed: Centre Box not found"],
                }
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", AsyncMock())
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "create": []})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["verified"] is False
    assert payload["data"]["errors"] == ["Create failed: Centre Box not found"]
    assert "failed before applying any mutations" in payload["data"]["verification_note"]


@pytest.mark.asyncio
async def test_gh_edit_partial_mutation_response_contains_visible_contract(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        return {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 1,
                    "errors": ["connect: unknown target 'T2'"],
                    "temp_id_map": {"T1": "R1"},
                }
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", AsyncMock())
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "create": []})
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["partial_success"] is True
    assert payload["data"]["errors"] == ["connect: unknown target 'T2'"]
    assert payload["data"]["warnings"] == ["connect: unknown target 'T2'"]
    assert payload["data"]["verified"] is False
    assert "partially applied" in payload["data"]["verification_note"]
```

Update the existing `test_gh_edit_surfaces_edit_summary_errors_as_warnings` fixture so its fake summary includes mutation evidence:

```python
"edit_summary": {
    "created": 1,
    "errors": ["set_values exception: value must be numeric"],
}
```

and assert:

```python
assert payload["data"]["partial_success"] is True
assert payload["data"]["errors"] == ["set_values exception: value must be numeric"]
```

- [ ] **Step 2: Run the MCP postmortem tests and verify failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_postmortem.py -q
```

Expected: new assertions fail because `server.py` has not used the shared contract helper yet.

- [ ] **Step 3: Replace local partial-warning helper usage**

In `mcp_server/src/rook/server.py`, import:

```python
from .gh_edit_contract import apply_gh_edit_contract
```

In the `case "gh_edit"` branch, replace:

```python
result = _attach_gh_edit_partial_warnings(result)
```

with:

```python
result = apply_gh_edit_contract(result, strict_partial_success=False)
```

Leave `_extract_gh_edit_partial_issues` and `_attach_gh_edit_partial_warnings` in place only if other tests still import them. If `rg "_attach_gh_edit_partial_warnings|_extract_gh_edit_partial_issues" mcp_server` shows no external usage after this change, delete both helpers from `server.py` and update imports accordingly.

- [ ] **Step 4: Run focused MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_postmortem.py -q
```

Expected: postmortem tests pass.

- [ ] **Step 5: Run server contract tests that touch `gh_edit`**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_component_deprecation.py mcp_server/tests/test_server_contract_hardening.py -q
```

Expected: pass. If failures assert old `warnings`-only behavior, update them to assert top-level/data-level `errors` and `partial_success` according to the spec.

- [ ] **Step 6: Commit Task 2**

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_gh_edit_postmortem.py mcp_server/tests/test_server_component_deprecation.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix: surface gh_edit contract in mcp path"
```

## Task 3: Wire Chat/Agent Dispatcher Through the Same Contract

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Test: `mcp_server/tests/test_dispatcher_safety.py`

- [ ] **Step 1: Add dispatcher tests for partial and no-mutation errors**

In `mcp_server/tests/test_dispatcher_safety.py`, inside `TestDispatcherVerification`, add:

```python
@pytest.mark.asyncio
async def test_gh_edit_no_mutation_errors_are_not_success(self, dispatcher):
    mock_result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 0,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": ["Create failed: Centre Box not found"],
            }
        },
    }

    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
        mock_rhino.return_value = mock_result
        result = await dispatcher.dispatch("gh_edit", {"epoch": 9, "create": []})

    assert mock_rhino.call_count == 1
    assert result["success"] is False
    assert result["verified"] is False
    assert result["errors"] == ["Create failed: Centre Box not found"]
    assert "partial_success" not in result


@pytest.mark.asyncio
async def test_gh_edit_partial_errors_are_promoted_for_chat_agents(self, dispatcher):
    mock_result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 1,
                "errors": ["connect: param not found for 'T19.O0>T20.I2'"],
                "instance_guids": {"T19": "guid-19"},
            }
        },
    }

    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
        mock_rhino.return_value = mock_result
        result = await dispatcher.dispatch("gh_edit", {"epoch": 9, "connect": []})

    assert mock_rhino.call_count == 1
    assert result["success"] is True
    assert result["partial_success"] is True
    assert result["verified"] is False
    assert result["errors"] == ["connect: param not found for 'T19.O0>T20.I2'"]
    assert "before continuing" in result["verification_note"]
```

- [ ] **Step 2: Run dispatcher tests and verify failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_dispatcher_safety.py::TestDispatcherVerification -q
```

Expected: new `gh_edit` contract assertions fail.

- [ ] **Step 3: Apply the helper in the dispatcher bridge path**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, import:

```python
from ..gh_edit_contract import apply_gh_edit_contract
```

In `ToolDispatcher._dispatch_inner`, in the `BRIDGE_ROUTES` branch after:

```python
result = await call_rhino(endpoint, method, data, port)
```

add:

```python
if name == "gh_edit":
    result = apply_gh_edit_contract(result, strict_partial_success=False)
```

Keep this before the existing warning log so no-mutation `gh_edit` errors log as failures.

- [ ] **Step 4: Run dispatcher tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_dispatcher_safety.py::TestDispatcherVerification -q
```

Expected: pass.

- [ ] **Step 5: Run chat runner tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_chat_runner.py -q
```

Expected: pass. If verification hoisting tests fail, preserve their existing behavior for non-`gh_edit` tools and add a `gh_edit`-specific assertion instead of weakening the contract.

- [ ] **Step 6: Commit Task 3**

```powershell
git add mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_dispatcher_safety.py
git commit -m "fix: surface gh_edit contract in agent dispatcher"
```

## Task 4: Prompt Contract and GH Status Tool Discoverability

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/prompt_builder.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Test: `mcp_server/tests/test_chat_prompt_builder.py`

- [ ] **Step 1: Add failing prompt regression tests**

In `mcp_server/tests/test_chat_prompt_builder.py`, add:

```python
from rook.agent.tool_groups import TOOL_GROUPS


def test_system_prompt_treats_in_chat_ui_as_ui_block_signal():
    prompt = PromptBuilder().build_system("worker")

    assert "here in chat" in prompt
    assert "ui_block" in prompt
    assert "Do not substitute Grasshopper sliders" in prompt


def test_system_prompt_requires_remediation_for_unverified_tool_results():
    prompt = PromptBuilder().build_system("worker")

    assert "verified=false" in prompt
    assert "partial_success" in prompt
    assert "edit_summary.errors" in prompt
    assert "not safe to build on" in prompt


def test_gh_canvas_group_includes_status_health_check():
    assert "gh_status" in TOOL_GROUPS["gh_canvas"]
```

- [ ] **Step 2: Run prompt tests and verify failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_chat_prompt_builder.py -q
```

Expected: new prompt string assertions and the `gh_status` group assertion fail.

- [ ] **Step 3: Update base prompt guidance**

In `mcp_server/src/rook/agent/chat/prompt_builder.py`, extend `_BASE_INSTRUCTIONS` in the `Interactive UI Blocks` section with:

```text
When the user asks for UI "here in chat", "in this panel", "in the chat panel",
or similar spatial references to the conversation UI, treat that as a direct
signal to call `ui_block`. Do not substitute Grasshopper sliders or a
Grasshopper definition unless the user explicitly asks for Grasshopper, a GH
canvas, or a GH-native parametric definition.
```

Add a new subsection after `Verification`:

```text
## Partial and Unverified Tool Results

Tool results with `partial_success: true` or `verified=false` are not safe to
build on. For `gh_edit`, inspect `edit_summary.errors`, the returned snapshot,
and any top-level `errors` before continuing. A partial edit may have already
created components, so do not blindly retry the same batch; remediate
incrementally, undo, or clean up before retrying.
```

In `mcp_server/src/rook/agent/tool_groups.py`, add `gh_status` to the
`gh_canvas` group next to `gh_snapshot`:

```python
"gh_canvas": [
    "gh_status", "gh_snapshot", "gh_edit", "gh_undo",
    ...
],
```

- [ ] **Step 4: Run prompt tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_chat_prompt_builder.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add mcp_server/src/rook/agent/chat/prompt_builder.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_chat_prompt_builder.py
git commit -m "fix: guide chat agents toward ui blocks and partial remediation"
```

## Task 5: Phase 2 Caller Audit Document

**Files:**
- Create: `docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md`

- [ ] **Step 1: Gather call sites**

Run:

```powershell
rg -n "gh_edit|/gh/edit|edit_summary|partial_success|_record_gh_to_session|record_gh_to_session|fallback to sequential|falling back to sequential|success\\]" mcp_server src docs -g "*.py" -g "*.cs" -g "*.md"
```

Expected: output includes `mcp_server/src/rook/server.py`, `mcp_server/src/rook/agent/tool_dispatcher.py`, `mcp_server/src/rook/learning/recipe_extraction.py`, `mcp_server/src/rook/learning/gh_session_history.py`, and tests that mention `success`.

- [ ] **Step 2: Create the audit table**

Create `docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md`:

```markdown
# GH Edit Caller Audit

Date: 2026-05-14

Spec: `docs/superpowers/specs/2026-05-14-gh-edit-partial-failure-contract-design.md`

## Contract States

| State | Required Shape | Retry Rule |
| --- | --- | --- |
| Full success | `success: true`, no `partial_success`, no top-level `errors` | Safe to build on. |
| No-mutation failure | `success: false`, `verified: false`, top-level `errors`, no `partial_success` | Safe to retry only after fixing input. |
| Partial mutation failure | Phase 1: `success: true`, `partial_success: true`, `verified: false`, top-level `errors`; Phase 3: `success: false` with the same partial metadata | Not automatically retryable. Inspect snapshot/edit summary, then remediate, undo, clean up, or deliberately retry with duplicate prevention. |

## Call Sites

| Area | File / Function | Current Behavior | Required Phase 1 Behavior | Required Phase 3 Behavior | Tests |
| --- | --- | --- | --- | --- | --- |
| Chat dispatcher/tool card | `mcp_server/src/rook/agent/tool_dispatcher.py::ToolDispatcher._dispatch_inner` | Bridge result passed through and chat sees top-level `success`. | Apply shared contract; no-mutation errors become failures; partial mutations are unverified with top-level errors. | Shared helper strict flag flips partial mutation `success` to false. | `mcp_server/tests/test_dispatcher_safety.py::TestDispatcherVerification` |
| Session history recording | `mcp_server/src/rook/server.py::_record_gh_to_session` and the `case "gh_edit"` recording branch | Existing logic marks nested edit errors as partial, but the branch records only inside `if result.get("success")`. | Preserve top-level errors and partial outcome. | Continue recording partial outcome even when top-level success is false. | `mcp_server/tests/test_gh_edit_postmortem.py::test_record_gh_to_session_marks_edit_summary_errors_as_partial` plus Phase 3 branch test |
| Batched GH intent fallback | `mcp_server/src/rook/server.py` lines matching `edit_result = await call_rhino("/gh/edit", ...)` and `if edit_result.get("success")` | Branches on `edit_result.get("success")`; failed batch falls back to sequential execution. | Branch on `partial_success` before fallback and avoid blind duplicate-producing retry. | Branch on strict failure plus retained partial metadata. | Add a regression in the existing GH intent batch/fallback test area or create `mcp_server/tests/test_gh_edit_contract.py` coverage for the branch helper extracted from this code. |
| GH session learning/history | `mcp_server/src/rook/learning/gh_session_history.py` | Records result details from caller. | Store promoted errors and partial outcome. | Store promoted errors and partial outcome with strict failure. | Existing session history tests plus one promoted-error assertion |
| Direct MCP tool response | `mcp_server/src/rook/server.py::call_tool` | Successful MCP responses serialize only `result.data`. | Duplicate `errors`, `warnings`, `partial_success`, `verified`, and `verification_note` under `data` so direct callers can see the contract. | Strict failure response must preserve parseable error details. | `mcp_server/tests/test_gh_edit_postmortem.py` |
| Tests asserting `success` | `mcp_server/tests` grep results | Some tests may encode compatibility success. | Compatibility assertions allowed only for mutation-evidence partials. | Update to expect strict failure for all non-empty `edit_summary.errors`. | Tracked in Phase 3 task |
```

Replace any row where grep discovers a more exact file/function reference.

- [ ] **Step 3: Self-check the audit for concrete references**

Run:

```powershell
$terms = @('TB'+'D','PLACE'+'HOLDER','aro'+'und','may'+'be','follow'+'-up')
Select-String -Path docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md -Pattern $terms -SimpleMatch
```

Expected: no output.

- [ ] **Step 4: Commit Task 5**

```powershell
git add docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md
git commit -m "docs: audit gh_edit strict contract callers"
```

## Task 6: Phase 3 Strict Contract Flip

**Files:**
- Modify: `mcp_server/src/rook/gh_edit_contract.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Tests: `mcp_server/tests/test_gh_edit_contract.py`, `mcp_server/tests/test_gh_edit_postmortem.py`, `mcp_server/tests/test_dispatcher_safety.py`, audited caller tests from Task 5

- [ ] **Step 1: Update helper tests to make strict partial failure the default**

In `mcp_server/tests/test_gh_edit_contract.py`, change calls for partial mutations from:

```python
apply_gh_edit_contract(result, strict_partial_success=False)
```

to:

```python
apply_gh_edit_contract(result, strict_partial_success=True)
```

and assert:

```python
assert contracted["success"] is False
assert contracted["partial_success"] is True
```

Keep one explicit compatibility test named `test_phase1_compatibility_can_preserve_partial_success_transport_success` if the helper still supports the flag during migration.

- [ ] **Step 2: Run tests and verify strict-flip failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_contract.py mcp_server/tests/test_gh_edit_postmortem.py mcp_server/tests/test_dispatcher_safety.py::TestDispatcherVerification -q
```

Expected: failures where production still passes `strict_partial_success=False`.

- [ ] **Step 3: Flip production helper calls**

In `mcp_server/src/rook/server.py` and `mcp_server/src/rook/agent/tool_dispatcher.py`, change:

```python
apply_gh_edit_contract(result, strict_partial_success=False)
```

to:

```python
apply_gh_edit_contract(result, strict_partial_success=True)
```

- [ ] **Step 4: Update audited callers**

Use `docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md` as the checklist. For each row:

```powershell
rg -n "gh_edit|partial_success|edit_summary|success" <listed-file>
```

Change callers that branch only on `success` so partial mutation failure is handled before any retry. The required pattern is:

```python
if result.get("partial_success"):
    # Do not retry the same batch. Preserve details for remediation.
    return result
if not result.get("success"):
    # No mutation evidence: caller may fix input and retry.
    return result
```

Do not add automatic retry for partial mutations.

- [ ] **Step 5: Add strict partial session-recording regression**

In `mcp_server/tests/test_gh_edit_postmortem.py`, add:

```python
@pytest.mark.asyncio
async def test_gh_edit_strict_partial_failure_still_records_session(monkeypatch, patched_server):
    record_mock = AsyncMock()

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        return {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 1,
                    "errors": ["connect: unknown target 'T2'"],
                    "instance_guids": {"T1": "guid-1"},
                }
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", record_mock)
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "create": []})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["partial_success"] is True
    record_mock.assert_awaited_once()
```

Then update the `case "gh_edit"` recording branch in
`mcp_server/src/rook/server.py` from:

```python
if result.get("success"):
    ...
```

to:

```python
if result.get("success") or result.get("partial_success"):
    ...
```

- [ ] **Step 6: Run migration tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_contract.py mcp_server/tests/test_gh_edit_postmortem.py mcp_server/tests/test_dispatcher_safety.py mcp_server/tests/test_recipe_extraction.py mcp_server/tests/test_gh_edit_postmortem.py -q
```

Expected: pass. If a recipe replay or session-history test fails, update it to assert the three contract states explicitly.

- [ ] **Step 7: Commit Task 6**

```powershell
git add mcp_server/src/rook/gh_edit_contract.py mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md
git commit -m "fix: make partial gh_edit strict failures"
```

## Task 7: GH Status Readiness Design Implementation

**Files:**
- Modify: `src/Rook/InternalBridge/GrasshopperCore.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Test: add or extend managed tests under `src/Rook.Tests` if a test seam exists; otherwise add Python contract tests for MCP response shape with mocked HTTP.

- [ ] **Step 1: Write contract tests for status shape at the Python layer**

Create `mcp_server/tests/test_gh_status_contract.py` using mocked `call_rhino`:

```python
import json
import pytest

from rook import server


@pytest.mark.asyncio
async def test_gh_status_success_means_endpoint_executed_not_ready(monkeypatch):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/status"
        return {
            "success": True,
            "data": {
                "available": True,
                "has_active_canvas": True,
                "canvas_visible": False,
                "has_active_document": True,
                "ready_for_edit": False,
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    response = await server.call_tool("gh_status", {})
    payload = json.loads(response[0].text)

    assert payload["ready_for_edit"] is False
    assert payload["canvas_visible"] is False


@pytest.mark.asyncio
async def test_gh_snapshot_fails_closed_when_not_ready(monkeypatch):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/snapshot"
        return {
            "success": False,
            "data": {
                "error": "grasshopper_not_ready",
                "ready_for_edit": False,
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    response = await server.call_tool("gh_snapshot", {})
    payload = response[0].text

    assert payload.startswith("Error: ")
    assert "grasshopper_not_ready" in payload


@pytest.mark.asyncio
async def test_gh_edit_fails_closed_when_not_ready(monkeypatch):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        return {
            "success": False,
            "data": {
                "error": "grasshopper_not_ready",
                "ready_for_edit": False,
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: type("Store", (), {"check_deprecation_warnings": lambda self, _create: []})(),
    )
    response = await server.call_tool("gh_edit", {"epoch": 1})
    payload = response[0].text

    assert payload.startswith("Error: ")
    assert "grasshopper_not_ready" in payload
```

- [ ] **Step 2: Inspect existing managed status implementation**

Run:

```powershell
rg -n "GetStatus|ResolveContext|Activator.CreateInstance|GrasshopperStatusDto|HandleStatus|/gh/status" src/Rook
```

Expected: locate `GrasshopperCore.GetStatus`, `GrasshopperCore.ResolveContext`, and `GrasshopperHandler` status route.

- [ ] **Step 3: Split read-only status from document-creating context resolution**

In `src/Rook/InternalBridge/GrasshopperCore.cs`, add a read-only context resolver used only by `GetStatus`. It must not call `Activator.CreateInstance` for `GH_Document`. The result DTO should include:

```csharp
public bool Available { get; set; }
public bool HasActiveCanvas { get; set; }
public bool? CanvasVisible { get; set; }
public bool VisibilityUnknown { get; set; }
public bool HasActiveDocument { get; set; }
public string? DocumentId { get; set; }
public string? Name { get; set; }
public string? Path { get; set; }
public bool ReadyForEdit { get; set; }
```

Compute:

```csharp
ReadyForEdit = Available
    && HasActiveCanvas
    && HasActiveDocument
    && CanvasVisible != false;
VisibilityUnknown = !CanvasVisible.HasValue;
```

- [ ] **Step 4: Ensure `gh_snapshot` and `gh_edit` fail closed**

In managed GH query/edit entry points, use the same readiness semantics before returning snapshot/edit data. If readiness is false, return:

```json
{
  "success": false,
  "data": {
    "error": "grasshopper_not_ready",
    "message": "Grasshopper is not ready for edit: active canvas/document required.",
    "ready_for_edit": false
  }
}
```

Do not create a document as a side effect in `gh_snapshot` or `gh_edit`.

- [ ] **Step 5: Run available tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter Grasshopper
python -m pytest mcp_server/tests/test_gh_status_contract.py -q
```

Expected: pass. When no managed Grasshopper test seam exists for this reflection
path, record that limitation in the commit message body and rely on the Python
contract tests plus this manual Rhino validation checkpoint:

```text
Manual Rhino checkpoint:
1. Start Rhino with Grasshopper closed.
2. Call gh_status and confirm success=true only means endpoint execution.
3. Confirm ready_for_edit=false when the active canvas/document is absent or
   canvas_visible is detectably false.
4. Call gh_snapshot and gh_edit in the not-ready state and confirm both return
   success=false with error/errors containing grasshopper_not_ready.
```

- [ ] **Step 6: Commit Task 7**

```powershell
git add src/Rook/InternalBridge/GrasshopperCore.cs src/Rook/Handlers/GrasshopperHandler.cs src/Rook.Tests mcp_server/tests/test_gh_status_contract.py
git commit -m "fix: make grasshopper status readiness explicit"
```

## Task 8: Defer `gh_ensure_open` Without Blocking the Contract

**Files:**
- Modify: `docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md`

- [ ] **Step 1: Document the deferred tool**

Append this exact section to `docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md`:

```markdown
## Deferred GH Ensure Open

`gh_ensure_open` remains deferred from the gh_edit contract migration. Until it
exists, agents should call `gh_status` for diagnosis and avoid using GH when
`ready_for_edit` is false unless the user explicitly asks to open Grasshopper.
```

- [ ] **Step 2: Verify the audit records the deferral**

Run:

```powershell
rg -n "Deferred GH Ensure Open|gh_ensure_open remains deferred|ready_for_edit" docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md
```

Expected: all three phrases are present.

- [ ] **Step 3: Commit Task 8**

```powershell
git add docs/superpowers/audits/2026-05-14-gh-edit-caller-audit.md
git commit -m "docs: defer gh_ensure_open implementation"
```

## Verification Before Completion

- [ ] Run focused Python contract tests:

```powershell
python -m pytest mcp_server/tests/test_gh_edit_contract.py mcp_server/tests/test_gh_edit_postmortem.py mcp_server/tests/test_dispatcher_safety.py::TestDispatcherVerification mcp_server/tests/test_chat_prompt_builder.py -q
```

- [ ] Run broader MCP tests touched by server/dispatcher changes:

```powershell
python -m pytest mcp_server/tests/test_chat_runner.py mcp_server/tests/test_server_component_deprecation.py mcp_server/tests/test_server_contract_hardening.py -q
```

- [ ] If managed GH status code changed, run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter Grasshopper
```

- [ ] Do not claim native/Rhino build verification unless the Rhino/MFC toolchain was actually used.

## Implementation Notes

- The first implementation task must handle no-mutation `edit_summary.errors` that currently arrive with `success: true`; Phase 1 requires those to become `success: false` immediately.
- Partial mutation is not automatically retryable. Any fallback path must inspect snapshot/edit summary before retrying.
- Keep all uncommitted exploratory test edits separate from plan and implementation commits unless intentionally reused task-by-task.
