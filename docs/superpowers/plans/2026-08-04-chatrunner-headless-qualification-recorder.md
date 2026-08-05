# ChatRunner Headless Qualification Recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct silent empty ChatRunner completions, then add one operator-only JSONL recorder that consumes the existing ChatEvent stream for separately authorized headless qualification rows.

**Architecture:** First make the existing ChatRunner event stream truthful for an empty model completion. After independent approval, add one private operator script that strictly loads one reviewed row, records existing ChatEvents through async-generator backpressure, enforces frozen targeting at the yielded event boundary, and performs one eligible final snapshot through the same canonical gateway executor. No product execution loop, gateway, targeting module, HTTP protocol, or conversation store is extended.

**Tech Stack:** Python 3.12.12, pytest/pytest-asyncio, existing `ChatRunner`, `PromptBuilder`, `ToolDispatcher`, canonical MCP gateway executor, `ContextVar` Rhino request context, UTF-8 JSONL, Windows PowerShell.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-08-04-chatrunner-headless-qualification-recorder-design.md` at `fa45d4e6`.
- Begin from the existing clean worktree and branch created for this design.
- No model, provider, Ollama, MCP service, Rhino, or Grasshopper contact during implementation or review.
- Task 1 must be implemented, committed, independently reviewed, and explicitly approved before Task 2 begins.
- The empty-completion correction changes only `chat_runner.py` and its existing test module.
- The recorder changes only one operator script and one focused test module.
- The operator accepts exactly one argument: the reviewed row JSON path.
- Row fields have no CLI or environment overrides.
- Canonical MCP profile-policy enforcement remains unchanged.
- Do not add a ChatRunner recorder hook, executor wrapper, hidden drift latch, HTTP route, UI, persistence, replay, index, database, scoring layer, or new outcome taxonomy.
- JSONL complete-row limit is exactly 256 KiB including newline.
- JSONL actual-file limit is exactly 4 MiB.
- No truncation, retry, reopen, reserved tail, rejection row, or partial-row repair.
- `run_finished` proves only that the planned row sequence through itself was written and flushed. It does not prove close success, operator success, or task success.
- `chat_event.payload` is exactly `ChatEvent.to_dict()`.
- UTC timestamps are wall-clock observations; elapsed duration uses a monotonic clock.
- Report cumulative production additions and operator nonblank lines at every review.
- Stop for renewed design review before the operator exceeds 350 nonblank lines or if another production module is required. No exception is pre-authorized.
- If a test exposes a needed change outside the exact task boundary, stop with valid-red evidence instead of patching around it.

---

## File map

| File | Responsibility |
|---|---|
| `mcp_server/src/rook/agent/chat/chat_runner.py` | Existing ChatRunner loop; Task 1 adds only the empty-completion branch. |
| `mcp_server/tests/test_chat_runner.py` | Existing focused ChatRunner tests; Task 1 adds the empty-completion regression. |
| `scripts/chatrunner_headless_qualification.py` | New private operator: row admission, recorder, event consumption, targeting checks, final inspection, bounded stdout. |
| `mcp_server/tests/test_chatrunner_headless_qualification.py` | New no-contact causal tests for the operator. |
| `docs/superpowers/plans/2026-08-04-chatrunner-headless-qualification-recorder.md` | Execution ledger and reproducible verification commands. |

No other implementation file is admitted.

## Baseline

Run before Task 1:

```powershell
$Repo = 'C:/UDEV/Rook/.worktrees/chatrunner-headless-qualification-recorder-design'
Set-Location $Repo
git status --short --branch
git rev-parse HEAD
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_capability_inventory.py `
  mcp_server/tests/test_registry.py -q
```

Expected before implementation:

```text
clean worktree
166 passed
11 pre-existing warnings
zero external contact
```

---

### Task 1: Correct silent empty completion

**Mandatory stop:** Commit this task and obtain independent approval before opening or creating the recorder script.

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py:1150-1176`
- Test: `mcp_server/tests/test_chat_runner.py`

**Interfaces:**
- Consumes: the existing streamed `text_parts`, `tool_calls_acc`, `Conversation.messages`, and `ChatEvent` vocabulary.
- Produces: one existing `error` event followed by ordinary `done`, with no empty assistant history entry.

- [ ] **Step 1: Add a streaming helper that returns no text and no tool calls**

Add beside `_make_text_response()` in `test_chat_runner.py`:

```python
def _make_empty_response(prompt_tokens=10, completion_tokens=0):
    async def _gen():
        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        yield final

    return _gen()
```

- [ ] **Step 2: Add the valid-red empty-completion regression**

```python
@pytest.mark.asyncio
async def test_run_turn_empty_completion_emits_error_without_assistant_history(
    runner, conversation
):
    completion = AsyncMock(return_value=_make_empty_response())
    events = []
    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        completion,
    ), _runtime_facts_patch():
        async for event in runner.run_turn(
            conversation,
            "Retain this user request",
            system_prompt="test",
        ):
            events.append(event)

    assert [event.type for event in events] == ["error", "done"]
    assert events[0].content == "Model returned no text or tool calls."
    assert conversation.messages == [
        {"role": "user", "content": "Retain this user request"}
    ]
    completion.assert_awaited_once()
    runner._tool_executor.assert_not_awaited()
    assert conversation.active_run_id is None
```

- [ ] **Step 3: Run the valid-red test**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chat_runner.py::test_run_turn_empty_completion_emits_error_without_assistant_history `
  -q
```

Expected RED: the event list lacks `error` and history contains an empty
assistant mapping.

- [ ] **Step 4: Add the minimal branch before assistant-message construction**

Immediately after reconstructing `full_text` and `tool_calls_list`, add:

```python
if not full_text and not tool_calls_list:
    yield ChatEvent(
        "error",
        content="Model returned no text or tool calls.",
    )
    break
```

Do not move or refactor the existing assistant-message construction.

- [ ] **Step 5: Run the new test and adjacent normal paths**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chat_runner.py::test_run_turn_empty_completion_emits_error_without_assistant_history `
  mcp_server/tests/test_chat_runner.py::test_run_turn_appends_user_message `
  mcp_server/tests/test_chat_runner.py::test_run_turn_tool_dispatch_roundtrip -q
```

Expected: `3 passed`.

- [ ] **Step 6: Run the complete focused baseline and syntax checks**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_capability_inventory.py `
  mcp_server/tests/test_registry.py -q
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  mcp_server/tests/test_chat_runner.py
git diff --check
```

Expected: `167 passed`, the same 11 pre-existing warnings, clean compilation,
and clean diff check.

- [ ] **Step 7: Report production growth**

```powershell
git diff --numstat fa45d4e6 -- `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  scripts/chatrunner_headless_qualification.py
```

Record the exact additions and deletions in the plan ledger. The operator script
must not exist yet.

- [ ] **Step 8: Commit Task 1 only**

```powershell
git add -- `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  mcp_server/tests/test_chat_runner.py
git commit -m "fix: refuse empty ChatRunner completions"
git show --check --stat --oneline HEAD
git status --short --branch
```

- [ ] **Step 9: Mandatory independent review stop**

Report the exact commit SHA, test/warning counts, production additions and
deletions, absence of the operator script, zero external contact, and clean
worktree. Resume only after explicit Task 1 approval is recorded in the ledger.

---

### Task 2: Strict row admission and bounded JSONL writer

**Prerequisite:** Task 1 commit has independent approval. If not, stop.

**Files:**
- Create: `scripts/chatrunner_headless_qualification.py`
- Create: `mcp_server/tests/test_chatrunner_headless_qualification.py`

**Interfaces:**
- Produces: `_QualificationRow`, `_RhinoTarget`, `_JsonlRecorder`,
  `_TraceWriteFailure`, `_load_row()`, and `_open_recorder()` for Task 3.
- Performs no model, direct-executor, canonical-executor, tool, or external
  calls; composition begins in Task 3.

- [ ] **Step 1: Create an importable operator skeleton**

Create the script with these exact public-to-tests private interfaces:

```python
#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping

_ROW_MAX_BYTES = 256 * 1024
_TRACE_MAX_BYTES = 4 * 1024 * 1024
_ROW_KEYS = frozenset({"model", "api_base", "intent", "skill_path", "rhino_target"})
_TARGET_KEYS = frozenset({"port", "process_id", "document_serial_number"})


@dataclass(frozen=True)
class _RhinoTarget:
    port: int
    process_id: int
    document_serial_number: int


@dataclass(frozen=True)
class _QualificationRow:
    source_path: Path
    source_sha256: str
    model: str
    api_base: str
    intent: str
    skill_path: Path
    skill_sha256: str
    skill_text: str
    target: _RhinoTarget


class _TraceWriteFailure(RuntimeError):
    def __init__(self, reason: str, path: Path | None) -> None:
        super().__init__("trace_write_failed")
        self.reason = reason
        self.path = path


def _load_row(path: Path) -> _QualificationRow:
    raise NotImplementedError


class _JsonlRecorder:
    def record(self, kind: str, payload: Mapping[str, Any]) -> None:
        raise NotImplementedError


def _open_recorder() -> _JsonlRecorder:
    raise NotImplementedError
```

- [ ] **Step 2: Create the test loader and fault-injectable stream**

Load the script with `importlib.util.spec_from_file_location()`, register the
module in `sys.modules`, and execute it. Add `_TraceStream` with counters and
faults for write exception, short write, flush exception, and close exception:

```python
class _TraceStream:
    def __init__(self, *, fail_write_at=None, short_write_at=None,
                 fail_flush_at=None, fail_close=False):
        self.content = bytearray()
        self.write_calls = self.flush_calls = self.close_calls = 0
        self.fail_write_at = fail_write_at
        self.short_write_at = short_write_at
        self.fail_flush_at = fail_flush_at
        self.fail_close = fail_close

    def write(self, row: bytes) -> int:
        self.write_calls += 1
        if self.write_calls == self.fail_write_at:
            raise OSError("WRITE_SENTINEL")
        if self.write_calls == self.short_write_at:
            count = max(0, len(row) - 1)
            self.content.extend(row[:count])
            return count
        self.content.extend(row)
        return len(row)

    def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_calls == self.fail_flush_at:
            raise OSError("FLUSH_SENTINEL")

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise OSError("CLOSE_SENTINEL")
```

- [ ] **Step 3: Add strict-row valid-red tests**

Use table-driven JSON mutations to prove refusal for duplicate, unknown,
missing, and non-exact fields. Add direct cases proving:

- exact positive target integers are required and `bool` refuses;
- model and intent are nonblank and retained without trimming;
- API base is credential-free loopback HTTP(S) without query or fragment;
- the resolved skill is a readable regular strict-UTF-8 file;
- row and skill SHA-256 values match exact bytes; and
- environment values do not alter admitted fields.

The duplicate-key RED must use:

```python
def test_row_loader_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "row.json"
    path.write_text(
        '{"model":"first","model":"second"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate_json_key"):
        OPERATOR._load_row(path)
```

- [ ] **Step 4: Add writer valid-red tests**

Require the flat event equation:

```python
def test_chat_event_payload_is_flat_and_exact():
    stream = _TraceStream()
    recorder = OPERATOR._JsonlRecorder(
        path=Path("trace.jsonl"),
        stream=stream,
        wall_clock=lambda: "2026-08-04T22:00:00.000000Z",
    )
    event = {"type": "tool_start", "name": "gh_edit", "params": {"epoch": 7}}
    recorder.record("chat_event", event)
    row = json.loads(bytes(stream.content))
    assert row == {
        "sequence": 1,
        "recorded_at_utc": "2026-08-04T22:00:00.000000Z",
        "kind": "chat_event",
        "payload": event,
    }
```

Add exact boundary cases for:

- complete row plus newline at 256 KiB and one byte over;
- actual file bytes at 4 MiB and an over-limit next row;
- `allow_nan=False` serialization failure;
- write exception, short write, and flush failure;
- sequence advancing only after full write and flush; and
- decreasing wall-clock timestamps remaining valid while sequence still
  increases;
- one-shot close, including close failure without retry.

- [ ] **Step 5: Run RED against the importable skeleton**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_headless_qualification.py -q
```

Expected RED comes from `NotImplementedError`, not collection failure.

- [ ] **Step 6: Implement strict row admission minimally**

Use one `object_pairs_hook`:

```python
def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result
```

Read exact bytes, decode strict UTF-8, require exact key sets and built-in types,
and parse API base with `urllib.parse.urlsplit`. Admit only `localhost`,
`127.0.0.1`, or `::1`. Hash exact row and skill bytes with SHA-256. Do not add a
generic schema loader or validation framework.

- [ ] **Step 7: Implement the private writer minimally**

Use only the specification's nine row kinds. Serialize the whole row plus
newline before writing, check both limits, require an exact built-in integer
write count equal to row length, account actual bytes, then flush. Every failure
sets recorder failure and raises `_TraceWriteFailure` with a fixed reason. Write
no rejection row.

Open beneath `%LOCALAPPDATA%/Rook/traces/` with:

```python
stream = path.open("xb", buffering=0)
```

Use a one-shot close-attempt guard. Do not seek, truncate, retry, reopen, repair,
or call `fsync`.

- [ ] **Step 8: Run Task 2 and existing recorder tests**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_headless_qualification.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py -q
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile `
  scripts/chatrunner_headless_qualification.py `
  mcp_server/tests/test_chatrunner_headless_qualification.py
git diff --check
```

- [ ] **Step 9: Report growth and enforce the stop gate**

```powershell
$Operator = 'scripts/chatrunner_headless_qualification.py'
$Nonblank = (Get-Content $Operator | Where-Object { $_.Trim().Length -gt 0 }).Count
Write-Output "OPERATOR_NONBLANK=$Nonblank"
if ($Nonblank -gt 350) { throw 'OPERATOR_GROWTH_GATE_EXCEEDED' }
git diff --numstat fa45d4e6 -- `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  scripts/chatrunner_headless_qualification.py
```

If another production module is needed or the operator exceeds 350 nonblank
lines, stop for renewed design review. Do not continue to Task 3.

- [ ] **Step 10: Commit Task 2 and stop for ownership review**

```powershell
git add -- `
  scripts/chatrunner_headless_qualification.py `
  mcp_server/tests/test_chatrunner_headless_qualification.py
git commit -m "feat: add bounded ChatRunner qualification trace"
git show --check --stat --oneline HEAD
git status --short --branch
```

Review must confirm the writer remains private, event payload is flat, no
external call path exists yet, byte failures stop without repair, and the
growth gate remains available for Task 3.

---

### Task 3: Consume ChatEvents with frozen target custody and final inspection

**Prerequisite:** Task 2 has independent approval. If not, stop.

**Files:**
- Modify: `scripts/chatrunner_headless_qualification.py`
- Test: `mcp_server/tests/test_chatrunner_headless_qualification.py`

**Interfaces:**
- Consumes: Task 2 `_QualificationRow`, `_JsonlRecorder`, and
  `_TraceWriteFailure`.
- Produces: `_run_row()`, targeting inspection helpers, production composition,
  `main()`, bounded stdout, and exactly one eligible final snapshot.

- [ ] **Step 1: Add causal async-generator test doubles**

```python
class _CausalRunner:
    def __init__(self, events, timeline):
        self._events = events
        self._timeline = timeline

    async def run_turn(self, conversation, intent, system_prompt):
        for event in self._events:
            self._timeline.append(f"yield:{event.type}")
            yield event
            self._timeline.append(f"resume:{event.type}")
```

Add a stream whose `flush()` parses the latest complete row and appends
`flush:<kind>` to the same timeline.

- [ ] **Step 2: Add the successful event-stream valid-red**

Use these exact events:

```python
events = [
    ChatEvent("tool_start", name="gh_edit", params={"epoch": 7}, tool_call_id="c1"),
    ChatEvent(
        "tool_result",
        name="gh_edit",
        result='{"success":true}',
        tool_call_id="c1",
    ),
    ChatEvent("text_delta", content="Complete"),
    ChatEvent(
        "done",
        usage={"input_tokens": 10, "output_tokens": 3, "wall_time_s": 1.2},
    ),
]
```

Assert each event flush precedes its corresponding resume, event payloads equal
`to_dict()` exactly, model/API base/intent enter the ephemeral conversation and
`run_turn()` unchanged, and the last rows are `snapshot_request`,
`snapshot_result`, `run_finished`.

Require the same fake canonical executor instance for ChatRunner gateway calls
and final inspection. Assert `run_started` contains exact row/repository/runtime
identity, skill hash, caller-prompt hash, active MCP profile, and frozen target.
Stdout contains only status and trace path.

- [ ] **Step 3: Add one real-ChatRunner no-contact vertical**

Construct the real class with one fake direct executor and one fake canonical
executor:

```python
from unittest.mock import AsyncMock, MagicMock, call, patch

from rook.agent.chat.chat_runner import ChatEvent, ChatRunner
from rook.agent.tool_registry import ToolRegistry

direct_executor = AsyncMock()
canonical_executor = AsyncMock(
    side_effect=[
        {"success": True, "data": {"matches": ["Series"]}},
        {"success": True, "data": {"epoch": 7, "components": []}},
    ]
)
runner = ChatRunner(
    tool_executor=direct_executor,
    registry=ToolRegistry(catalog={}, agent_mode=True),
    mcp_capability_executor=canonical_executor,
)
```

Patch only `litellm.acompletion` and `collect_runtime_facts`. The first fake
LiteLLM stream emits this model-authored call:

```python
{
    "name": "rook_tools_call",
    "arguments": {
        "name": "gh_library",
        "arguments": {"search": "Series"},
    },
}
```

Construct that stream with the same LiteLLM delta shape already used by
`test_chat_runner.py`:

```python
def _gateway_stream():
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        tool = MagicMock()
        tool.index = 0
        tool.id = "gateway_call"
        tool.function.name = "rook_tools_call"
        tool.function.arguments = json.dumps(
            {"name": "gh_library", "arguments": {"search": "Series"}}
        )
        chunk.choices[0].delta.tool_calls = [tool]
        chunk.usage = None
        yield chunk

    return _gen()


def _text_stream():
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Complete"
        chunk.choices[0].delta.tool_calls = None
        chunk.usage = None
        yield chunk

    return _gen()
```

The second fake stream emits ordinary text. Drive the real runner through the
operator, including its final inspection. Assert:

```python
assert canonical_executor.await_args_list == [
    call(
        "rook_tools_call",
        {"name": "gh_library", "arguments": {"search": "Series"}},
    ),
    call(
        "rook_tools_call",
        {
            "name": "gh_snapshot",
            "arguments": {"include_data": False, "max_preview_items": 0},
        },
    ),
]
direct_executor.assert_not_awaited()
```

Require exact recorded Chat event types in order:

```text
tool_start
tool_result
text_delta
done
```

and exact flat `ChatEvent.to_dict()` payloads. This test complements rather than
replaces `_CausalRunner`: real ChatRunner proves the composition seam, while the
causal fake owns deterministic fault ordering.

- [ ] **Step 4: Add pre-dispatch targeting refusal valid-red tests**

Parameterize direct `tool_start` events for top-level `port`, `session`,
`documentSerialNumber`, `rhino_set_active_instance`, and
`rhino_clear_active_instance`.

Parameterize canonical calls with the exact nested positions:

```python
ChatEvent(
    "tool_start",
    name="rook_tools_call",
    params={"name": "gh_edit", "arguments": {"port": 9999}},
)
```

Include `session`, `documentSerialNumber`, and both target-control names. Assert
`tool_start` and `qualification_refusal` flush, the generator never records
`resume:tool_start`, all executors receive zero calls, no snapshot occurs, and
no `run_finished` exists.

Add a counterexample with `{"payload": {"session": "domain value"}}` and prove
it is not recursively rejected.

- [ ] **Step 5: Add drift, incomplete-stream, and write-failure valid-red tests**

Cover separately:

- active target changes after a returned event;
- Rhino request context changes after a returned event;
- generator raises an ordinary exception;
- generator cancellation;
- normal exhaustion without `done`;
- Chat `error` followed by `done`;
- trace open or `run_started` write/flush failure before the first generator
  request;
- writer failure on `tool_start`; and
- writer failure on `tool_result`.

Require:

```text
tool_start write failure -> zero dispatch and zero snapshot
tool_result write failure -> completed current call, zero later call, zero snapshot
error + done -> snapshot eligible
exception/cancel/drift/missing done -> zero snapshot and no run_finished
```

Assert ordinary stream exceptions record type and message without traceback,
cancellation records `run_cancelled`, and pre-contact trace failure causes zero
model, direct-executor, canonical-executor, and tool calls. Inert objects may
already have been constructed.

- [ ] **Step 6: Add final-inspection valid-red tests**

The fixed call is:

```python
await canonical_executor(
    "rook_tools_call",
    {
        "name": "gh_snapshot",
        "arguments": {
            "include_data": False,
            "max_preview_items": 0,
        },
    },
)
```

Prove the request row flushes before entry; context is checked before and after;
exact returned success or operational failure becomes `snapshot_result`; either
returned result may be followed by `run_finished`; executor raise or post-call
drift leaves the request as the last applicable call boundary; and a second
inspection is unreachable.

Add one close-failure case where `run_finished` was already flushed. Require the
trace to retain that row while bounded stdout reports `trace_write_failed`,
proving the row does not claim close or operator success.

- [ ] **Step 7: Run the complete Task 3 valid-red selection**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_headless_qualification.py -q
```

Expected RED is missing Task 3 behavior, not collection or fixture failure.

- [ ] **Step 8: Implement exact shallow targeting inspection**

```python
_TARGET_CONTROL_TOOLS = frozenset({
    "rhino_set_active_instance",
    "rhino_clear_active_instance",
})
_ROUTING_KEYS = frozenset({"port", "session", "documentSerialNumber"})


def _targeting_refusal(event: ChatEvent) -> str | None:
    if event.type != "tool_start":
        return None
    params = event.params if type(event.params) is dict else {}
    if event.name in _TARGET_CONTROL_TOOLS:
        return "target_control_forbidden"
    if event.name == "rook_tools_call":
        if params.get("name") in _TARGET_CONTROL_TOOLS:
            return "target_control_forbidden"
        arguments = params.get("arguments")
        if type(arguments) is dict and _ROUTING_KEYS.intersection(arguments):
            return "target_override_forbidden"
        return None
    if _ROUTING_KEYS.intersection(params):
        return "target_override_forbidden"
    return None
```

Do not recurse and do not move this policy into either executor.

- [ ] **Step 9: Implement production composition without another framework**

```python
dispatcher = ToolDispatcher(
    port=row.target.port,
    local_tools=build_local_tools(),
)
canonical_executor = build_mcp_capability_gateway_executor("full")
runner = ChatRunner(
    tool_executor=dispatcher.dispatch,
    tool_access="full",
    mcp_capability_executor=canonical_executor,
)
```

Create one ephemeral `Conversation` with exact row model/API base, code-owned
persona `architect`, and admitted document serial. Build the prompt from
`PromptBuilder.build_system("architect")`, one fixed separator, and exact skill
text. Hash only that caller-supplied prompt string.

Save the previous active target, set the admitted `InstanceRef`, enter
`rhino_request_context()` with the complete triple, and restore the previous
target in cleanup. Use manual `anext()` and explicit `aclose()` so no subsequent
event is requested after refusal, write failure, drift, or incomplete
termination.

- [ ] **Step 10: Implement metadata, finalization, and bounded CLI**

Before the first generator request, collect local repository/runtime facts,
open the recorder, and write/flush `run_started`. Use UTC wall clock for row
timestamps and `time.monotonic()` only for elapsed duration.

The CLI accepts exactly `sys.argv[1]` as the row path. Emit compact stdout only:

```json
{"status":"completed","trace_path":"C:/.../trace.jsonl"}
```

Closed alternatives are `refused` and `trace_write_failed`. Never emit trace
content or exception messages. Ordinary bounded paths keep stderr empty.

- [ ] **Step 11: Run tests and enforce the growth gate**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_headless_qualification.py -q
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile `
  scripts/chatrunner_headless_qualification.py `
  mcp_server/tests/test_chatrunner_headless_qualification.py
$Operator = 'scripts/chatrunner_headless_qualification.py'
$Nonblank = (Get-Content $Operator | Where-Object { $_.Trim().Length -gt 0 }).Count
Write-Output "OPERATOR_NONBLANK=$Nonblank"
if ($Nonblank -gt 350) { throw 'OPERATOR_GROWTH_GATE_EXCEEDED' }
git diff --numstat fa45d4e6 -- `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  scripts/chatrunner_headless_qualification.py
git diff --check
```

If the gate fails, do not split into another production module. Stop for renewed
design review.

- [ ] **Step 12: Commit Task 3 and stop for independent vertical review**

```powershell
git add -- `
  scripts/chatrunner_headless_qualification.py `
  mcp_server/tests/test_chatrunner_headless_qualification.py
git commit -m "feat: complete ChatRunner qualification operator"
git show --check --stat --oneline HEAD
git status --short --branch
```

Report exact tests, operator nonblank lines, cumulative production additions,
zero external contact, and clean worktree.

---

### Task 4: Final no-contact verification and plan reconciliation

**Prerequisite:** Task 3 has independent approval.

**Files:**
- Modify: `docs/superpowers/plans/2026-08-04-chatrunner-headless-qualification-recorder.md`
- Production/test changes: none. If a prescribed regression exposes a concrete
  defect, stop with valid-red evidence before editing.

**Interfaces:**
- Consumes: approved Task 1–3 commits.
- Produces: reproducible final evidence and a completed ledger only.

- [ ] **Step 1: Run focused recorder and ChatRunner seams**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_chatrunner_headless_qualification.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_rook_tools_meta.py -q
```

- [ ] **Step 2: Run adjacent recorder and service seams**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_capability_inventory.py `
  mcp_server/tests/test_registry.py -q
```

Any pre-existing baseline failures must match their recorded test IDs and
signatures exactly. No new failure is acceptable.

- [ ] **Step 3: Compile and scan the source surface**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  scripts/chatrunner_headless_qualification.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chatrunner_headless_qualification.py
rg -n "chatrunner_headless_qualification|_JsonlRecorder" `
  mcp_server/src/rook src scripts `
  -g '!scripts/chatrunner_headless_qualification.py'
rg -n "trace|recorder" mcp_server/src/rook/agent/chat/chat_runner.py
git diff --check
```

Expected: no recorder implementation outside the operator script and no
recorder hook in ChatRunner.

- [ ] **Step 4: Re-run growth and exact-scope checks**

```powershell
$Operator = 'scripts/chatrunner_headless_qualification.py'
$Nonblank = (Get-Content $Operator | Where-Object { $_.Trim().Length -gt 0 }).Count
Write-Output "OPERATOR_NONBLANK=$Nonblank"
if ($Nonblank -gt 350) { throw 'OPERATOR_GROWTH_GATE_EXCEEDED' }
git diff --numstat fa45d4e6 -- `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  scripts/chatrunner_headless_qualification.py
git diff --name-only fa45d4e6...HEAD
```

The complete implementation range must contain exactly:

```text
mcp_server/src/rook/agent/chat/chat_runner.py
mcp_server/tests/test_chat_runner.py
scripts/chatrunner_headless_qualification.py
mcp_server/tests/test_chatrunner_headless_qualification.py
docs/superpowers/plans/2026-08-04-chatrunner-headless-qualification-recorder.md
```

- [ ] **Step 5: Reconcile the ledger with exact evidence**

Record Task commit SHAs and approvals, test and warning counts, exact known
baseline failures, operator nonblank lines, per-file and cumulative production
growth, compilation/scans, zero external contact, and final worktree status.

- [ ] **Step 6: Commit ledger reconciliation only**

```powershell
git add -- docs/superpowers/plans/2026-08-04-chatrunner-headless-qualification-recorder.md
git commit -m "docs: reconcile ChatRunner recorder implementation"
git show --check --stat --oneline HEAD
git status --short --branch
```

Stop for independent final review. Do not push, merge, deploy, or perform live
qualification without later explicit authorization.

---

## Execution ledger

- [x] Baseline identity and 166-test result recorded.
- [x] Task 1 valid RED recorded.
- [x] Task 1 commit, growth, and independent approval recorded.
- [x] Task 2 begins only after Task 1 approval.
- [ ] Task 2 valid RED and writer/input results recorded.
- [ ] Task 2 commit, operator line count, growth, and independent approval recorded.
- [ ] Task 3 begins only after Task 2 approval.
- [ ] Task 3 causal vertical, targeting, failure, and snapshot results recorded.
- [ ] Task 3 commit, operator line count, growth, and independent approval recorded.
- [ ] Final focused and adjacent seams recorded.
- [ ] Compilation, source scans, scope, and `git diff --check` recorded.
- [ ] Zero external contact recorded.
- [ ] Final reconciliation commit and clean worktree recorded.

### Task 1 evidence

- Baseline: `9a963e823632a160e1cfaf4e70660f8646da28fa`; `166 passed`,
  11 pre-existing warnings.
- Valid RED: the empty completion emitted only `done` and retained an empty
  assistant history entry.
- Commit: `63219ab56466c5f688b62c6cf5a538ebf2195d40`.
- Verification: `167 passed`, 11 pre-existing warnings; compilation and
  `git diff --check` passed.
- Growth: ChatRunner `+7/-0`; focused tests `+40/-0`; recorder script absent.
- Independent approval: 2026-08-05; adjacent seam `3 passed`; no findings.
- External contact: none.
