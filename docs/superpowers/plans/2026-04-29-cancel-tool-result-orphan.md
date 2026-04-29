# Cancel-Tool-Result Orphan Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user clicks Stop mid-tool-call, the conversation history must remain Anthropic-API-valid so the next user message succeeds instead of failing with `tool_use ids were found without tool_result blocks immediately after`.

**Architecture:** Add a private repair helper that walks `conversation.messages`, finds each assistant message with `tool_calls`, and inserts synthetic `{"error":"cancelled by user"}` tool-result entries immediately after the existing contiguous run of tool messages — before any non-tool message — for any tool_call_id that's missing a result. Call from two sites in `run_turn`: top-of-run (before the new user message lands, so prior cancelled turns self-heal) and outer `finally` (proactive on the way out, pure dict mutation, no yield).

**Tech Stack:** Python 3.12, pytest, asyncio, litellm.

---

## Background

A user-driven Architect failed in today's ui-block-roundtrip smoke test with:

```
LLM error: litellm.BadRequestError: AnthropicException - messages.6: tool_use ids were found
without tool_result blocks immediately after: toolu_01T13zregQTKhCVBkqB3cbgq.
Each tool_use block must have a corresponding tool_result block in the next message.
```

Triage (full diagnosis in conversation):

1. `chat_runner.py:526` appends `assistant_msg` (with `tool_calls`) to `conversation.messages` BEFORE any tool dispatch.
2. `chat_runner.py:580–603` wraps `await self._tool_executor(...)` in `try/except Exception`. **`asyncio.CancelledError` is `BaseException`-derived in Python 3.8+ and is NOT caught.**
3. `chat_runner.py:613–627` yields the `tool_result` event and appends `{role:"tool", tool_call_id, content}` to `conversation.messages` — both OUTSIDE the inner try. Cancellation skips them.
4. `conv.abort_event` is set by `handle_message`'s except clause AFTER the generator is already abandoned — not useful as an internal poll.

The same orphan hazard exists at `yield ChatEvent("tool_start", ...)` (line 571), the `ui_block` path (lines 556–569), and the meta-tool path (lines 574–576) — anywhere control yields between `assistant_msg` append and `tool_result` append. The richer "wrap dispatch in `except BaseException`" alternative is rejected: it doesn't cover yield-point cancellations and risks swallowing cancellation semantics.

The fix is a self-healing repair helper. Reviewer-approved corrections applied:
- **P1 (ordering):** call repair BEFORE the new user message lands, so synthetic tool_results stay adjacent to the assistant tool_use they answer (not after the new user message).
- **P2 (no global ID scan):** per-assistant contiguous-run scan, insertions land at the end of the existing tool-message run.

## File Structure

| File | Role after fix |
|---|---|
| `mcp_server/src/rook/agent/chat/chat_runner.py` | Adds `_patch_orphaned_tool_calls(messages: List[Dict]) -> int` helper; calls it at top of `run_turn` (before new user message) and inside the existing outer `finally:` (before the existing usage/yield logic). INFO-logs the patched count. |
| `mcp_server/tests/test_chat_runner.py` | Adds 6 unit tests for the helper covering no-op, last-message orphans, multi-orphan-with-following-user-message (the reviewer's specific case), multi-cancelled-turns, and synthetic content shape. Adds 1 integration test exercising `run_turn` with a `CancelledError`-raising executor. |

No other call sites need updating — `conversation.messages` is the single source of truth and the helper is self-contained.

---

## Task 1: Write Failing Unit Tests for `_patch_orphaned_tool_calls`

**Files:**
- Modify: `mcp_server/tests/test_chat_runner.py` — append 6 unit tests at the bottom of the file.

- [ ] **Step 1: Add the unit test block**

Append the following to `mcp_server/tests/test_chat_runner.py`:

```python
# ───────────────────────────────────────────────────────────────────
# _patch_orphaned_tool_calls — repairs cancelled-mid-dispatch history
# Anchored against the 2026-04-29 Stop-during-tool-call orphan bug:
# when CancelledError fires between assistant_msg append and the
# tool_result append, conversation.messages becomes Anthropic-API-
# invalid (tool_use without matching tool_result). The helper makes
# the next /message call succeed by inserting synthetic results.
# ───────────────────────────────────────────────────────────────────


def _assistant_with_tool_calls(*tool_call_ids):
    """Build an assistant message with the given tool_call_ids."""
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": "rhino_ping", "arguments": "{}"},
            }
            for tc_id in tool_call_ids
        ],
    }


def _tool_result(tool_call_id, content="ok"):
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def test_patch_orphans_returns_zero_when_history_is_valid():
    """No-op: every tool_call has a matching tool_result already."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        {"role": "user", "content": "hi"},
        _assistant_with_tool_calls("tc1"),
        _tool_result("tc1"),
    ]
    before = list(messages)
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 0
    assert messages == before


def test_patch_orphans_appends_at_end_when_no_following_message():
    """Last assistant has [tc1, tc2], only tc1 has a result, no later messages."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        {"role": "user", "content": "hi"},
        _assistant_with_tool_calls("tc1", "tc2"),
        _tool_result("tc1"),
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 1
    assert len(messages) == 4
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "tc2"
    assert json.loads(messages[3]["content"]) == {"error": "cancelled by user"}


def test_patch_orphans_inserts_multiple_at_end_in_order():
    """Last assistant has [tc1, tc2, tc3], only tc1 result present."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        _assistant_with_tool_calls("tc1", "tc2", "tc3"),
        _tool_result("tc1"),
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 2
    # Order matters — tc2 must come before tc3
    assert messages[2]["tool_call_id"] == "tc2"
    assert messages[3]["tool_call_id"] == "tc3"


def test_patch_orphans_inserts_before_user_message_not_after():
    """Reviewer's specific case: orphans + a following user message.

    Synthetic tool_results MUST go between the existing tool result and
    the user message, not after the user message — otherwise Anthropic's
    tool_use → tool_result adjacency contract is still violated.
    """
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        _assistant_with_tool_calls("tc1", "tc2", "tc3"),
        _tool_result("tc1"),
        {"role": "user", "content": "follow-up"},
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 2
    # Layout must be: assistant, tool(tc1), tool(tc2-synthetic), tool(tc3-synthetic), user
    assert [m.get("role") for m in messages] == ["assistant", "tool", "tool", "tool", "user"]
    assert messages[1]["tool_call_id"] == "tc1"
    assert messages[2]["tool_call_id"] == "tc2"
    assert messages[3]["tool_call_id"] == "tc3"
    assert messages[4]["content"] == "follow-up"


def test_patch_orphans_repairs_multiple_cancelled_turns():
    """Two prior cancelled turns, each with orphans — repair both runs."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        _assistant_with_tool_calls("tc1", "tc2"),
        _tool_result("tc1"),
        # tc2 orphaned, then a fresh user turn happened (also cancelled)
        {"role": "user", "content": "first follow-up"},
        _assistant_with_tool_calls("tc3"),
        # tc3 orphaned, no result message at all
        {"role": "user", "content": "second follow-up"},
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 2
    # First repair: tc2 inserted between tool(tc1) and the first user message
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "tc2"
    # Second repair: tc3 inserted between the second assistant and the second user
    # Layout: assistant1, tool(tc1), tool(tc2), user1, assistant2, tool(tc3), user2
    assert [m.get("role") for m in messages] == [
        "assistant", "tool", "tool", "user",
        "assistant", "tool", "user",
    ]
    assert messages[5]["tool_call_id"] == "tc3"


def test_patch_orphans_synthetic_content_is_valid_json():
    """Synthetic content must round-trip through json.loads with the agreed shape."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [_assistant_with_tool_calls("tc1")]  # no result
    _patch_orphaned_tool_calls(messages)
    assert messages[1]["role"] == "tool"
    parsed = json.loads(messages[1]["content"])
    assert parsed == {"error": "cancelled by user"}
```

- [ ] **Step 2: Run tests to confirm they fail with the right error**

```powershell
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_runner.py -v -k patch_orphans 2>&1 | Select-Object -Last 25
```

Expected: 6/6 FAIL with `ImportError: cannot import name '_patch_orphaned_tool_calls' from 'rook.agent.chat.chat_runner'`. The helper doesn't exist yet.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_chat_runner.py
git commit -m "test(chat): failing tests for tool-result orphan repair helper"
```

---

## Task 2: Implement `_patch_orphaned_tool_calls`

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py` — add the helper as a module-level private function near the top of the file (after imports, before `class ChatRunner`).

- [ ] **Step 1: Add the helper**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, find the section just before `class ChatRunner` (or before the first class definition). Add:

```python
def _patch_orphaned_tool_calls(messages: List[Dict[str, Any]]) -> int:
    """Repair conversation history left invalid by cancelled tool dispatches.

    Anthropic's API contract requires every assistant `tool_use` block to be
    followed in the next message by a matching `tool_result`. When the user
    clicks Stop mid-tool-call, ChatRunner.run_turn unwinds via
    `asyncio.CancelledError` (not caught by `except Exception`) before the
    `tool_result` append at line ~623. The orphaned `tool_use` then breaks
    the next LLM call.

    This helper walks `messages` and, for each assistant message with
    `tool_calls`, examines ONLY the contiguous run of `{role:"tool"}`
    messages that immediately follow it. Any tool_call_id from that
    assistant message that is missing from the run gets a synthetic
    `{role:"tool", tool_call_id, content:'{"error":"cancelled by user"}'}`
    entry inserted at the end of the run — before the next non-tool
    message — preserving the tool_use → tool_result adjacency that
    Anthropic requires.

    Returns the number of synthetic results inserted.
    """
    synthetic_content = json.dumps({"error": "cancelled by user"})
    patched = 0
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            expected_ids = [tc["id"] for tc in msg["tool_calls"]]

            # Locate the contiguous run of tool messages immediately after.
            run_end = i + 1
            while run_end < len(messages) and messages[run_end].get("role") == "tool":
                run_end += 1

            # Collect tool_call_ids actually present in that run.
            present_ids = {
                messages[j].get("tool_call_id")
                for j in range(i + 1, run_end)
                if messages[j].get("tool_call_id")
            }

            # Insert synthetic results for missing ids, in original order,
            # at the end of the run (before any non-tool message).
            for tc_id in expected_ids:
                if tc_id not in present_ids:
                    messages.insert(run_end, {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": synthetic_content,
                    })
                    run_end += 1
                    patched += 1

            i = run_end
        else:
            i += 1
    return patched
```

You may also need to confirm the imports at the top of the file already include `from typing import Any, Dict, List` (or equivalent). The existing module uses these types; if `Any` / `Dict` / `List` aren't imported, add them to the existing typing import line.

- [ ] **Step 2: Run unit tests to confirm they pass**

```powershell
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_runner.py -v -k patch_orphans 2>&1 | Select-Object -Last 15
```

Expected: 6/6 PASS.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/src/rook/agent/chat/chat_runner.py
git commit -m "feat(chat): add _patch_orphaned_tool_calls helper

Walks conversation.messages and inserts synthetic tool_result entries
for any assistant tool_calls that lack a matching tool_result in the
contiguous run immediately following. Preserves tool_use -> tool_result
adjacency required by Anthropic's API contract. Returns the count of
synthetic entries inserted."
```

---

## Task 3: Wire Helper into `run_turn` (Top + Finally) with Logging

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py:417-421` (top-of-run call, before user message append) and the outer `finally:` near line 654.

- [ ] **Step 1: Add the top-of-run call**

In `chat_runner.py`, find the `run_turn` method around line 403. Locate this block (around lines 415–421):

```python
        run_id = uuid.uuid4().hex[:8]
        conversation.active_run_id = run_id
        conversation.abort_event.clear()
        conversation.touch()

        # Add user message to history
        conversation.messages.append({"role": "user", "content": user_message})
```

Insert the repair call BEFORE the user-message append. Replace the block above with:

```python
        run_id = uuid.uuid4().hex[:8]
        conversation.active_run_id = run_id
        conversation.abort_event.clear()
        conversation.touch()

        # Defensive repair: if a previous turn was cancelled mid-tool-dispatch,
        # the assistant tool_use is in history without matching tool_result.
        # Repair BEFORE appending the new user message so synthetic results
        # stay adjacent to the assistant tool_use (Anthropic API contract).
        _patched_pre = _patch_orphaned_tool_calls(conversation.messages)
        if _patched_pre:
            logger.info(
                f"Conversation {conversation.id}: repaired {_patched_pre} "
                f"orphaned tool_call(s) from prior cancelled turn(s)"
            )

        # Add user message to history
        conversation.messages.append({"role": "user", "content": user_message})
```

- [ ] **Step 2: Add the outer-finally call**

Still in `chat_runner.py`, find the outer `finally:` block in `run_turn` near line 654. The existing block looks like:

```python
        finally:
            wall_time = time.time() - start_time
            conversation.active_run_id = None
            conversation.touch()
            done_usage: Dict[str, Any] = {
```

Insert the repair call as the FIRST action in the finally block. Replace the block above with:

```python
        finally:
            # Proactive repair: if THIS turn was cancelled mid-tool-dispatch,
            # repair history on the way out so the conversation stays valid
            # before the next /message arrives. Pure dict mutation; no yield.
            _patched_post = _patch_orphaned_tool_calls(conversation.messages)
            if _patched_post:
                logger.info(
                    f"Conversation {conversation.id}: repaired {_patched_post} "
                    f"orphaned tool_call(s) on turn exit (cancelled mid-dispatch)"
                )

            wall_time = time.time() - start_time
            conversation.active_run_id = None
            conversation.touch()
            done_usage: Dict[str, Any] = {
```

- [ ] **Step 3: Run the existing chat-runner tests to confirm no regressions**

```powershell
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_runner.py -v 2>&1 | Select-Object -Last 25
```

Expected: all existing tests still pass; the 6 new `patch_orphans` tests still pass.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/src/rook/agent/chat/chat_runner.py
git commit -m "fix(chat): repair orphaned tool_calls at turn boundaries

Wires _patch_orphaned_tool_calls into ChatRunner.run_turn at two sites:

- Top-of-run, BEFORE appending the new user message. Self-heals stale
  histories left by prior cancelled turns. Insertion ordering preserves
  tool_use -> tool_result adjacency (synthetic results land before the
  new user message, not after).

- Outer finally:, BEFORE the existing usage/yield logic. Proactive
  repair on the way out — pure dict mutation, no yield. Cancellation
  exits run_turn through the same finally regardless of whether the
  cancel hit at await self._tool_executor() or at any yield point.

Logs at INFO with conversation id and patched count when repair runs."
```

---

## Task 4: Integration Test — `run_turn` with `CancelledError`-Raising Executor

**Files:**
- Modify: `mcp_server/tests/test_chat_runner.py` — append one async integration test after the unit-test block from Task 1.

This test exercises the full `run_turn` flow: a mock executor raises `asyncio.CancelledError` mid-dispatch, the generator unwinds, and we assert that `conversation.messages` ends up valid (no orphaned tool_calls, synthetic content present).

- [ ] **Step 1: Add the integration test**

Append to `mcp_server/tests/test_chat_runner.py`:

```python
@pytest.mark.asyncio
async def test_run_turn_repairs_history_when_executor_raises_cancelled(conversation, runner):
    """When asyncio.CancelledError fires inside _tool_executor, the outer
    finally must repair conversation.messages so the next /message call
    has a valid Anthropic-API history.
    """
    import asyncio

    # Make the LLM emit a tool_use for rhino_ping.
    async def _stream():
        # First chunk: tool_call delta
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "toolu_test_001"
        tc_delta.function.name = "rhino_ping"
        tc_delta.function.arguments = "{}"
        delta.tool_calls = [tc_delta]
        chunk.choices = [MagicMock(delta=delta)]
        chunk.usage = None
        yield chunk
        # Final chunk: usage, no choices
        usage_chunk = MagicMock()
        usage_chunk.choices = []
        usage_chunk.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        yield usage_chunk

    # Mock executor raises CancelledError as soon as it's awaited.
    async def _cancelling_executor(name, params):
        raise asyncio.CancelledError()

    runner._tool_executor = _cancelling_executor

    with patch("rook.agent.chat.chat_runner.litellm.acompletion", new=AsyncMock(return_value=_stream())):
        with patch("rook.agent.chat.chat_runner.collect_runtime_facts", new=AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}})):
            with pytest.raises(asyncio.CancelledError):
                async for _ in runner.run_turn(conversation, "test message", "system"):
                    pass

    # Conversation history must now be valid: assistant tool_use must be
    # followed by a tool_result for toolu_test_001 (synthetic, since the
    # real executor was cancelled).
    assistant_indices = [
        i for i, m in enumerate(conversation.messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert len(assistant_indices) == 1
    asst_idx = assistant_indices[0]
    # The next message after the assistant must be a tool result for our id.
    assert conversation.messages[asst_idx + 1]["role"] == "tool"
    assert conversation.messages[asst_idx + 1]["tool_call_id"] == "toolu_test_001"
    assert json.loads(conversation.messages[asst_idx + 1]["content"]) == {"error": "cancelled by user"}
```

- [ ] **Step 2: Run the integration test**

```powershell
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_runner.py::test_run_turn_repairs_history_when_executor_raises_cancelled -v 2>&1 | Select-Object -Last 15
```

Expected: PASS. The CancelledError propagates out of `run_turn`, but the outer `finally` runs `_patch_orphaned_tool_calls` first, leaving `conversation.messages` valid.

- [ ] **Step 3: Run the full chat-runner suite**

```powershell
.venv/Scripts/python.exe -m pytest tests/test_chat_runner.py -v 2>&1 | Select-Object -Last 25
```

Expected: all tests pass (existing + 6 unit + 1 integration = 7 new).

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_chat_runner.py
git commit -m "test(chat): integration test for run_turn cancellation repair

Mocks an executor that raises asyncio.CancelledError, runs run_turn
to completion (cancellation propagates out), and asserts conversation
history was repaired by the outer-finally call to
_patch_orphaned_tool_calls — a synthetic tool_result for the orphaned
tool_call_id is present immediately after the assistant message."
```

---

## Task 5: Full Test Suite + Live Smoke Test

**Files:** Read-only verification.

- [ ] **Step 1: Run the full chat-related test suite**

```powershell
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_runner.py tests/test_chat_server.py tests/test_chat_prompt_builder.py tests/test_persona_prompt_schema.py -v 2>&1 | Select-Object -Last 30
```

Expected: same pre-existing failures only (4 failures in `TestKnowledgeGraphRoutes` and port-binding tests — already documented as unrelated on this repo). All chat-runner / chat-server / prompt tests pass.

- [ ] **Step 2: Live smoke test in the chat panel**

The chat server is editable-installed, so `chat_runner.py` changes take effect on next process spawn. Close + reopen Rhino so the C# companion respawns the chat server.

In the chat panel, ask the Architect:

```
List the layers in the current Rhino document.
```

After Architect calls a tool (e.g. `rhino_layers`) and starts streaming text, click **Stop**. Then send a follow-up message:

```
Now describe the active layer.
```

Expected: the follow-up message succeeds. The agent's response acknowledges the cancelled prior call (it sees the synthetic `{"error":"cancelled by user"}` tool result) and proceeds with the new request. Crucially, **no `litellm.BadRequestError: AnthropicException - tool_use ids were found without tool_result blocks immediately after` error.**

If the smoke test still raises the orphan error, stop and return to Phase 1 — the helper isn't being called on the right path.

- [ ] **Step 3: Final state confirmation**

```bash
git log --oneline main..HEAD
git status --short
```

Expected: 4 commits on the branch (1 failing tests, 1 helper, 1 wire-up, 1 integration test). Working tree shows only the unrelated dirty paths from prior sessions (`knowledge/...`, `install-summary.json`, plan doc).

---

## Self-Review Notes

- **Spec coverage:** Every reviewer correction lands in the plan.
  - P1 (ordering): Task 3 step 1 places the top-of-run repair call BEFORE `conversation.messages.append({"role":"user",...})`. Task 1's `test_patch_orphans_inserts_before_user_message_not_after` asserts the insertion-position invariant directly on the helper.
  - P2 (no global ID scan): Task 2's helper uses a per-assistant contiguous-run scan, not a global lookup. Task 1's `test_patch_orphans_repairs_multiple_cancelled_turns` exercises two separate runs in the same conversation.
  - Helper returns `int` patched count: Task 2 helper signature; Task 1 tests assert return values explicitly.
  - INFO logging: Task 3 steps 1 and 2 both log conditionally on `_patched_pre`/`_patched_post > 0`.
  - Reviewer's specific test case: Task 1 step 1 includes `test_patch_orphans_inserts_before_user_message_not_after` covering `[tc1, tc2, tc3] + tool(tc1) + user("follow-up")`.
  - Synthetic content shape: Task 1 step 1 includes `test_patch_orphans_synthetic_content_is_valid_json`.
  - Rejection of `except BaseException` alternative: encoded in Background. The plan adds the helper only.
- **Placeholder check:** every step shows the exact code or command. The two diff-style edits in Task 3 quote the surrounding context so the engineer can locate the insertion point even if line numbers have shifted.
- **Type/method consistency:** `_patch_orphaned_tool_calls(messages: List[Dict[str, Any]]) -> int` declared in Task 2 matches the call sites in Task 3 and the import in Task 1's tests. Synthetic content `json.dumps({"error":"cancelled by user"})` is identical across helper, unit tests, and integration test.
- **What this fix does NOT cover:** truly concurrent mutation of `conversation.messages` from outside `run_turn`. The conversation has `active_run_id` guarding against parallel runs, so this is not a real concern today. Future refactors that introduce concurrent writers would need to revisit.
- **Smoke test reliability:** The Stop-during-tool-call timing is sensitive — the user must click Stop while the agent is mid-tool. Picking a slow tool (e.g. `rhino_layers` against a real document with many layers) gives more reaction window than a fast `rhino_ping`. If the smoke test passes the first time, the path is fixed. If it doesn't reproduce, the helper at least passes its unit + integration tests — those are the durable invariants.
