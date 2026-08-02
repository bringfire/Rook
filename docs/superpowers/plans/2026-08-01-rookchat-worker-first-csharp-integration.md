# RookChat Worker-First C# Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with the review stops below. Steps use checkbox syntax for tracking.

**Goal:** Add one explicit **Build C#** action to RookChat that sends a normalized intent through the proven Worker-first C# composition and renders one bounded native result card, while leaving ordinary Chat unchanged.

**Architecture:** The managed panel adds a per-message `execution_mode`. The Python Chat handler recognizes only `worker_first_csharp_v1`, owns the stream/run lifecycle, and calls a new application-owned composition root. That root constructs the fixed Planner and Worker transports plus a create-only wrapper over the real local `ToolDispatcher`, then delegates to `run_minimal_intent_worker_initial_body_integration()`. Existing native records remain authoritative; the handler projects only the seven approved bounded fields.

**Tech Stack:** Python 3.12, aiohttp, LiteLLM, existing Rook agent/workflow modules, C# net48, Eto.Forms, System.Text.Json, pytest, xUnit.

---

## Locked Constraints

- Missing `execution_mode` follows the existing Chat path unchanged.
- The only admitted mode is `worker_first_csharp_v1`; every other supplied value refuses before model or tool construction.
- The panel alone performs `input.Trim()`. Downstream code performs no further trimming and requires exact Planner-goal equality.
- One Planner call, at most one Worker call, and at most one `gh_create_csharp_script` call. No update, repair, retry, fallback, classifier, or alternate model.
- The application root is under `mcp_server/src/rook/agent`; it is not owned by `ChatRunner`.
- The mode route does not append user or result entries to `conversation.messages`.
- The handler emits exactly `tool_start -> tool_result -> done` for a completed stream and uses one code-owned call ID: `worker_first_csharp_v1:<run_id>`.
- The complete application transaction runs through one `asyncio.to_thread` boundary; synchronous Planner and Worker calls never run on aiohttp's event loop.
- The selected Rhino `ContextVar` context propagates through that boundary, and the matching run ID remains active until the worker task is genuinely done.
- The real local surface is constructed exactly as `ToolDispatcher(local_tools=build_local_tools())`, then narrowed before dispatcher entry to one create call.
- Planner/Worker roles are the exact existing `hybrid` identities. Generation settings are temperature `0`, `max_tokens=1024`, `max_retries=0`, and timeout `120.0` seconds.
- Planner structured output uses LiteLLM `response_format`; Worker structured output uses the existing structured schema path.
- `component_created` is `true`, `false`, or `null`; absence of a receipt never automatically means `false`.
- This is an ephemeral product transaction. No archive, recorder, proof carrier, or new outcome framework is introduced.
- No provider, Worker box, Rhino, or Grasshopper contact is allowed during implementation or review.

## Transaction Lineage

```text
trimmed panel input
-> exact HTTP message + explicit mode
-> Chat mode branch and run lifecycle
-> one context-preserving worker-thread boundary
-> application-owned composition root
-> exact Planner draft adapter
-> strict existing draft loader
-> Worker-first handoff
-> create-only real local tool surface
-> retained native result
-> bounded result projection
-> existing Chat tool events
-> one panel tool card
```

No downstream value may be rebuilt beside this chain when an existing upstream record owns it.

## Planned File Surface

**Create:**

- `mcp_server/src/rook/agent/worker_first_csharp_application.py`
- `mcp_server/tests/test_worker_first_csharp_application.py`
- `mcp_server/tests/test_rookchat_worker_first_csharp_integration.py`

**Modify:**

- `mcp_server/src/rook/agent/local_worker_model_transport.py`
- `mcp_server/src/rook/agent/chat/server.py`
- `mcp_server/tests/test_local_worker_model_transport.py`
- `mcp_server/tests/test_chat_server.py`
- `src/Rook/UI/Chat/ChatTab.cs`
- `src/Rook/UI/Chat/AgentChatTab.cs`
- `src/Rook/UI/Chat/AgentChatClient.cs`
- `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`
- `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`
- this plan ledger during reconciliation

No other production file is in scope without a failing test that demonstrates a concrete contradiction.

---

## Task 1: Build the Application-Owned Composition Root

**Files:**

- Create: `mcp_server/src/rook/agent/worker_first_csharp_application.py`
- Create: `mcp_server/tests/test_worker_first_csharp_application.py`
- Modify: `mcp_server/src/rook/agent/local_worker_model_transport.py`
- Modify: `mcp_server/tests/test_local_worker_model_transport.py`

### Step 0: Reconfirm the clean implementation lane and baseline

- [x] Run:

```powershell
git status --short
git rev-parse HEAD
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py `
  mcp_server/tests/test_minimal_csharp_initial_body_handoff.py `
  mcp_server/tests/test_local_worker_model_transport.py
dotnet test src/Rook.Tests/Rook.Tests.csproj `
  --filter "FullyQualifiedName~AgentChatClientParseTests|FullyQualifiedName~RookChatPanelTests"
```

- [x] Require an empty status before edits and record exact baseline counts. Stop on an unrelated failure rather than changing its code in this slice.

### Step 1: Promote the existing Worker schema builder without changing its value

- [x] Add a test proving `build_local_worker_response_schema()` returns a fresh mapping exactly equal to the current private `_local_worker_response_union_schema()` result.
- [x] Add a mutation test proving mutation of one returned schema does not affect a subsequent call.
- [x] Run the test and confirm a behavioral RED because the public function is absent:

```powershell
uv run --project mcp_server pytest -q mcp_server/tests/test_local_worker_model_transport.py -k "response_schema"
```

- [x] Make `build_local_worker_response_schema()` the public code-owned builder and retain `_local_worker_response_union_schema()` as a thin compatibility alias for existing scripts/tests. Do not change those historical callers, schema bytes, vocabulary, or response loader.
- [x] Rerun the focused test and confirm GREEN.

### Step 2: Establish an importable application skeleton and behavioral RED

- [x] Create the application module with `run_worker_first_csharp_application(intent: str) -> MinimalIntentWorkerInitialBodyIntegrationResult`, but make it raise `NotImplementedError`.
- [x] Keep the production function closed to the exact intent. Tests monkeypatch structural transport, profile, local-tool, and dispatcher constructors beneath the real root; the root accepts no factories and no arbitrary Planner-result producer.
- [x] Add tests that call the real application function and fail on missing behavior rather than during collection.

The root returns the existing integration result unchanged. It introduces no wrapper result, duplicate graph fields, or receipt copy.

### Step 3: Write valid-red role and construction tests

- [x] Prove `hybrid` is resolved before either transport or tool construction.
- [x] Prove exact built-in strings and exact role equality:

```text
Planner = anthropic/claude-opus-4-6
Worker  = ollama_chat/qwen3-coder:30b-a3b-q8_0
```

- [x] Prove profile failure, role mismatch, or equality-spoof values cause an ordinary pre-contact refusal and zero constructors.
- [x] Prove Planner kwargs contain `response_format` built from `build_minimal_planner_draft_response_schema()` and no `format`.
- [x] Prove Worker kwargs contain a fresh `build_local_worker_response_schema()` through `structured_response_schema`, without duplicated `response_format`.
- [x] Prove both transports receive exact model identity, temperature `0`, `max_tokens=1024`, `max_retries=0`, and timeout `120.0`.

### Step 4: Write valid-red create-only capability tests

- [x] Patch `build_local_tools()` and `ToolDispatcher` at construction and prove the root builds `ToolDispatcher(local_tools=build_local_tools())`.
- [x] Prove the wrapper delegates one exact `gh_create_csharp_script` request and returns the dispatcher value unchanged.
- [x] Prove every other name, especially `gh_update_script`, refuses before dispatcher entry.
- [x] Prove repeated create and equality-spoof names refuse before any second/invalid entry.

### Step 5: Implement the smallest root

- [x] Add code-owned constants for mode/profile/model/generation values.
- [x] Resolve and exact-type-check both roles before constructing either capability.
- [x] Construct both `LiteLLMWorkerTransport` instances with their role-specific schema paths.
- [x] Construct the real local dispatcher and private create-only async wrapper.
- [x] Construct the exact concrete `MinimalPlannerDraftAdapter` and call:

```python
await run_minimal_intent_worker_initial_body_integration(
    intent=intent,
    planner_adapter=planner_adapter,
    worker_transport=worker_transport,
    tool_executor=create_only_executor,
)
```

- [x] Return the exact `MinimalIntentWorkerInitialBodyIntegrationResult` without replaying or wrapping its lineage.

### Step 6: Verify and commit Task 1

- [x] Run:

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_worker_first_csharp_application.py `
  mcp_server/tests/test_local_worker_model_transport.py `
  mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py
uv run --project mcp_server python -m py_compile `
  mcp_server/src/rook/agent/worker_first_csharp_application.py `
  mcp_server/src/rook/agent/local_worker_model_transport.py
git diff --check
```

- [x] Confirm no external contact occurred.
- [x] Commit Task 1 files:

```powershell
git add mcp_server/src/rook/agent/worker_first_csharp_application.py `
        mcp_server/src/rook/agent/local_worker_model_transport.py `
        mcp_server/tests/test_worker_first_csharp_application.py `
        mcp_server/tests/test_local_worker_model_transport.py
git commit -m "feat: add Worker-first C# application root"
```

### Mandatory Task 1 review stop

Stop for independent review before Chat routing. Confirm role construction, schema selection, and create-only enforcement occur before external entry.

---

## Task 2: Add the Explicit Chat Route and Bounded Native Projection

**Files:**

- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `mcp_server/tests/test_chat_server.py`

### Step 1: Add mode-routing valid-red tests

- [x] Prove a request without `execution_mode` still calls existing `ChatRunner.run_turn()` and never constructs the Worker-first application.
- [x] Add an invalid-mode table covering non-string values, blank strings, case changes, whitespace padding, and unknown strings. Every row refuses before application/model/tool construction.
- [x] Add one valid request using exact mode `worker_first_csharp_v1`.
- [x] Prove blank, whitespace-padded, non-string, and oversized exact-mode messages refuse rather than being trimmed again; the application receives only an exact built-in bounded string.
- [x] Run and confirm RED at the missing route branch:

```powershell
uv run --project mcp_server pytest -q mcp_server/tests/test_chat_server.py -k "worker_first_csharp"
```

### Step 2: Add lifecycle, responsiveness, and ownership tests

- [x] Inject a fake application root through `create_chat_app()` so HTTP tests never construct live capabilities.
- [x] Prove the exact branch rejects concurrent work, assigns one real run ID, clears `abort_event`, touches the conversation, and never calls `PromptBuilder` or `ChatRunner`.
- [x] Use a blocking fake application controlled by `threading.Event` objects. While it is blocked, prove an asyncio heartbeat advances and a second request for the same conversation receives `409`.
- [x] At fake dispatcher entry inside the worker thread, prove `get_rhino_request_context()` contains the exact process/document identity selected by the handler.
- [x] Cancel the request task while the fake remains blocked. Prove `abort_event` is set, `active_run_id` remains unchanged, no completed result is streamed, and the application task is not canceled.
- [x] Release the fake, wait for genuine quiescence, and prove the matching run ID then clears. A different replacement run ID must never be cleared by the old completion callback.
- [x] Prove `conversation.messages` is unchanged on success, native stop, application exception, disconnect, and deferred cancellation cleanup.
- [x] Prove an ordinary worker-task exception is retrieved and cannot produce an unhandled-task warning or leave the conversation active.

### Step 3: Add projection fixtures from owned native records

- [x] Build real result fixtures for these ownership cases:

| Case | Expected bounded facts |
|---|---|
| clean created/passed receipt and terminal `done` | success, passed, zero counts, `component_created=true` |
| created/failed receipt | failed, failed, owned counts, `component_created=true` |
| pre-create Planner or Worker stop | failed, unavailable, null counts, `component_created=false` |
| ambiguous post-dispatch failure without owned receipt | failed, unavailable, null counts, `component_created=null` |
| owned evidence proving no creation | failed, unavailable, `component_created=false` |
| ordinary application exception with no provable create boundary | failed, unavailable, null counts, `component_created=null` |

- [x] Select receipt only from the retained create producer record. Do not replay compilers, applicators, dispatchers, or graph transitions.
- [x] Require compile status exactly `passed` for owned passed verification, `failed` for owned failed verification, and `unavailable` otherwise.
- [x] Require exact built-in scalar types before interpreting receipt values.
- [x] Project terminal stage/reason through closed code-owned token sets. Unknown or model-authored values become fixed unclassified tokens and can never reach the stream verbatim.
- [x] Require the complete success equation; every missing or contradictory term yields failed.

### Step 4: Add exact event-contract tests

- [x] Prove completed stream order is exactly `tool_start`, `tool_result`, `done`.
- [x] Prove `tool_start` has no intent/parameters and uses `worker_first_csharp_v1:<run_id>`.
- [x] Prove `tool_result` reuses that ID, uses `tool_status=success|failed`, sets `verified` from the clean equation, and serializes exactly:

```text
status
terminal_stage
terminal_reason
compile_status
error_count
warning_count
component_created
```

- [x] Prove no prompts, responses, code, rationale, diagnostics, GUIDs, receipts, provider metadata, or exception text leaks.
- [x] Prove `done` remains the existing shape.

### Step 5: Implement one off-loop branch without refactoring normal Chat

- [x] Add an optional application factory to `create_chat_app()` under one private app key.
- [x] Distinguish missing mode from supplied mode. Missing follows existing Chat; non-exact supplied values refuse closed.
- [x] Preserve the existing no-mode handler structurally; extract only a tiny shared response helper if compilation requires it.
- [x] Add one private synchronous thread entry that runs the complete async application callable in a private event loop:

```python
def _run_worker_first_application_sync(application, intent):
    return asyncio.run(application(intent))
```

- [x] Inside the existing Rhino request context, create exactly one task around `asyncio.to_thread(_run_worker_first_application_sync, application, message)`. Construct and invoke the application root only inside that worker-thread transaction.
- [x] Await the task through `asyncio.shield()` so cancellation of the aiohttp handler never marks the underlying worker task canceled.
- [x] On normal completion, project the owned result, emit result/done, touch the conversation, retrieve the task result/exception, and clear the matching run ID.
- [x] On connection loss or cancellation while work continues, set abort, stop streaming, attach one code-owned done callback that retrieves the eventual result/exception and clears only the matching run ID, and return without claiming provider cancellation.
- [x] Catch ordinary application exceptions (never `BaseException`) at this boundary and emit the same bounded failed card with native fields unavailable, counts `null`, and `component_created=null`; never export exception type/text.
- [x] Do not add an executor, scheduler, retry, transport wrapper, or generalized background-job abstraction beyond this one `to_thread` task.
- [x] Never append to `conversation.messages`.

### Step 6: Verify and commit Task 2

- [x] Run:

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_worker_first_csharp_application.py `
  mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py
uv run --project mcp_server python -m py_compile mcp_server/src/rook/agent/chat/server.py
git diff --check
```

- [x] Commit route files:

```powershell
git add mcp_server/src/rook/agent/chat/server.py mcp_server/tests/test_chat_server.py
git commit -m "feat: route explicit RookChat Worker-first requests"
```

### Mandatory Task 2 review stop

Stop for independent review. Verify nullable mutation truth, receipt ownership, ordinary Chat preservation, no history pollution, and exact event vocabulary.

---

## Task 3: Add the Dedicated Build C# Panel Action

**Files:**

- Modify: `src/Rook/UI/Chat/ChatTab.cs`
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Modify: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`
- Modify: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`

### Step 1: Pin managed request JSON with behavioral REDs

- [x] Prove ordinary `SendMessageStreamingAsync()` still omits `execution_mode`.
- [x] Prove a dedicated Build C# client call sends the normalized message and exact `execution_mode="worker_first_csharp_v1"` with existing conversation/document fields.
- [x] Prove no generic mode/model/intent override surface is added.
- [x] Run and confirm RED because the dedicated method is absent:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AgentChatClientParseTests"
```

### Step 2: Implement the smallest client seam

- [x] Keep ordinary send unchanged.
- [x] Add `SendWorkerFirstCSharpStreamingAsync()` that shares private HTTP/event parsing but authors the closed mode itself.
- [x] Do not add a mode argument to ordinary send.
- [x] Rerun client tests to GREEN.

### Step 3: Add panel-action valid-red tests

- [x] Add only the smallest test-visible action seam needed by the existing UI tests.
- [x] Prove Send and Enter trim through existing behavior, invoke ordinary send, and omit mode.
- [x] Prove Build C# uses exactly `input.Trim()`, refuses empty, preserves interior whitespace, invokes only the dedicated client method, and is non-sticky.
- [x] Prove both actions share concurrent-run guards and both disable during processing.
- [x] Prove double submission across the two actions is impossible.

### Step 4: Implement the one-button extension

- [x] Add the smallest secondary-action callback/label seam to `ChatTab` without changing non-agent tabs.
- [x] Add **Build C#** beside existing actions and share blank/concurrency/processing behavior.
- [x] Keep keyboard submission bound only to Send.
- [x] In `AgentChatTab`, call the dedicated client method and reuse the existing event/card lifecycle.

### Step 5: Add the tiny name-specific summary

- [x] Test `BuildToolSummary()` for clean success, compile failure counts, unavailable/null creation, and malformed bounded JSON.
- [x] Show only bounded compile state/counts/creation certainty; never show diagnostics, code, GUIDs, prompts, model content, or raw JSON.
- [x] Keep every other tool name on the existing generic summary.
- [x] Implement one exact-name branch; no renderer registry or generic framework.

### Step 6: Verify and commit Task 3

- [x] Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj `
  --filter "FullyQualifiedName~AgentChatClientParseTests|FullyQualifiedName~RookChatPanelTests"
dotnet build src/Rook/Rook.csproj --configuration Debug
git diff --check
```

- [x] Confirm no external contact occurred.
- [x] Commit managed files:

```powershell
git add src/Rook/UI/Chat/ChatTab.cs `
        src/Rook/UI/Chat/AgentChatTab.cs `
        src/Rook/UI/Chat/AgentChatClient.cs `
        src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs `
        src/Rook.Tests/UI/Chat/RookChatPanelTests.cs
git commit -m "feat: add explicit Build C# Chat action"
```

### Mandatory Task 3 review stop

Stop for independent review. Verify ordinary Send/Enter is unchanged, Build C# is non-sticky, and the UI displays only bounded facts.

---

## Task 4: Prove the Complete Fake-Backed Product Vertical

**Files:**

- Create: `mcp_server/tests/test_rookchat_worker_first_csharp_integration.py`
- Modify only if a test proves an omission: files already listed in Tasks 1–3
- Modify: this plan for final reconciliation

### Step 1: Build a valid-red HTTP vertical using real product seams

- [x] Start a real aiohttp test app through `create_chat_app()` and use the real mode route plus real application root.
- [x] Inject only structural fakes at approved boundaries: one-call Planner transport, one-call Worker transport through the real adapter/harness, and patched local dispatcher execution.
- [x] Make the fake Planner inspect the actual prompt and return the exact four-field payload with `goal` equal to normalized intent.
- [x] Make the fake Worker inspect actual context before returning one `draft_create_body` response.
- [x] Make fake create derive its receipt from actual tool name, pins, Worker body, call order, and request. Unexpected input fails closed.
- [x] Confirmed the new vertical was behaviorally green against the completed
  Task 1–3 seams. No production omission was found, so no artificial RED or
  product change was introduced.

### Step 2: Prove exact success

- [x] Assert:

```text
HTTP request
-> one Planner
-> strict draft admission
-> one Worker
-> one gh_create_csharp_script
-> deterministic receipt verification
-> tool_start
-> tool_result
-> done
```

- [x] Prove zero update, repair, retry, fallback, ChatRunner, or prose calls.
- [x] Prove code equals admitted Worker code while pins/name/position/tool/topology remain compiler-owned.
- [x] Prove clean seven-field result and no excluded payload leakage.
- [x] Prove Rhino context at dispatcher entry, unchanged conversation history, and cleared run ID.

### Step 3: Prove the closed stop-prefix matrix

- [x] Parameterize:

| Stop | Planner | Worker | Create | Projection |
|---|---:|---:|---:|---|
| unknown mode | 0 | 0 | 0 | refusal before root |
| Planner transport failure | 1 | 0 | 0 | failed/unavailable/false |
| malformed or goal-mismatch draft | 1 | 0 | 0 | failed/unavailable/false |
| Worker refusal or malformed response | 1 | 1 | 0 | failed/unavailable/false |
| compile-failure receipt | 1 | 1 | 1 | failed/failed/true |
| ambiguous create dispatch | 1 | 1 | 1 | failed/unavailable/null |
| clean compile | 1 | 1 | 1 | success/passed/true |

- [x] Require stable start/result/done for each completed mode stream.
- [x] Require the run ID to remain active while the off-loop task is blocked, then clear after quiescence; do not claim provider-call cancellation.
- [x] Prove malformed native evidence fails safely and never becomes clean success.

### Step 4: Run the complete focused seams

- [x] Run Python:

```powershell
uv run --project mcp_server pytest -q `
  -k "not TestKnowledgeGraphRoutes" `
  mcp_server/tests/test_rookchat_worker_first_csharp_integration.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_worker_first_csharp_application.py `
  mcp_server/tests/test_minimal_intent_worker_initial_body_integration.py `
  mcp_server/tests/test_minimal_csharp_initial_body_handoff.py `
  mcp_server/tests/test_local_worker_model_transport.py `
  mcp_server/tests/test_plan_graph_worker_create_body_apply.py `
  mcp_server/tests/test_plan_graph_current_step_runner.py
```

- [x] Run managed:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj `
  --filter "FullyQualifiedName~AgentChatClientParseTests|FullyQualifiedName~RookChatPanelTests"
dotnet build src/Rook/Rook.csproj --configuration Debug
```

- [x] Record exact counts/results in the ledger.

### Step 5: Run final static verification

- [x] Run:

```powershell
uv run --project mcp_server python -m py_compile `
  mcp_server/src/rook/agent/worker_first_csharp_application.py `
  mcp_server/src/rook/agent/local_worker_model_transport.py `
  mcp_server/src/rook/agent/chat/server.py
rg -n "gh_update_script|draft_repair_params|run_minimal_intent_worker_integration" `
  mcp_server/src/rook/agent/worker_first_csharp_application.py `
  mcp_server/src/rook/agent/chat/server.py
git diff --check
git status --short
```

- [x] Require zero forbidden-path matches in the new application/mode branch.
- [x] Review branch-base diff for exact planned scope and confirm no external contact.

### Step 6: Reconcile the plan ledger and commit

- [x] Mark completed checkboxes and record:

```text
implementation HEAD:
focused Python count:
managed Chat count:
managed build result:
git diff --check:
worktree status:
external contact: none
```

- [x] Record final non-claims: no broad intent coverage, runtime-output proof, repeatability, arbitrary interfaces, provider cancellation guarantee, durable evidence, or cross-mode memory.
- [x] Commit vertical test and ledger:

```powershell
git add mcp_server/tests/test_rookchat_worker_first_csharp_integration.py `
        docs/superpowers/plans/2026-08-01-rookchat-worker-first-csharp-integration.md
git commit -m "test: verify RookChat Worker-first C# vertical"
```

### Final verification ledger

```text
implementation HEAD through reviewed Task 3: c4501f57bbb2464b0e9c951acd04d5611c274ab8
Task 4 vertical witness: included with this ledger commit
focused Python: 172 passed, 13 unrelated knowledge-route tests deselected
managed Chat/parser: 43 passed
managed build: passed, 0 errors, 264 existing warnings
Python compilation: passed
forbidden-path scan: zero matches
git diff --check: passed
external contact: none
```

The broad `test_chat_server.py` baseline reproduced exactly its two known,
unrelated knowledge failures and no others:

```text
TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload
  meta.source was UnifiedStore+CommandKnowledgeStore, expected UnifiedStore
TestKnowledgeGraphRoutes::test_knowledge_note_found
  command-knowledge note response was 500 because ModeKnowledge is not JSON serializable
```

Final non-claims: this slice does not establish broad intent coverage,
runtime-output correctness, repeatability, arbitrary interfaces, cancellation
of an already-entered provider call, durable evidence, or cross-mode memory.

### Mandatory final implementation review stop

Stop before push, PR, merge, deployment, or live panel run. Live Planner/Worker/Rhino execution remains separately authorized after merge.

---

## Execution Strategy

Use **Inline Execution** with `superpowers:executing-plans`. The application root, event-loop boundary, route lifecycle, managed action, event projection, and vertical witness are one coupled cross-language transaction. Preserve its lineage and retain the mandatory independent review stops after Tasks 1–4.

## Completion Criterion

The slice is complete only when the fake-backed real RookChat HTTP surface proves:

```text
normalized explicit Build C# intent
-> application-owned one-Planner composition
-> context-preserving off-loop execution
-> deterministic Worker-first workflow
-> one create-only typed-tool call
-> owned clean compile receipt
-> bounded existing Chat tool card
```

Ordinary Send/Enter remains unchanged, and no external system has been contacted.
