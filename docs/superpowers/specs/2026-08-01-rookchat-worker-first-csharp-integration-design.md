# RookChat Worker-First C# Integration Design

**Date:** 2026-08-01

**Status:** Approved design for specification review

## Purpose

Expose the proven Worker-first C# path through one explicit RookChat panel
action without changing ordinary Chat behavior or the underlying product seam.

The first product vertical is:

```text
RookChat panel
-> normalized message + explicit worker_first_csharp_v1 mode
-> /agent/chat/message
-> application-owned composition root
-> one Planner
-> one Worker-authored initial body
-> deterministic workflow/compiler
-> one real or fake-backed gh_create_csharp_script call
-> deterministic receipt verification
-> existing RookChat tool card
```

Implementation and review use fake Planner, Worker, and tool capabilities. No
provider, Worker box, Rhino, or Grasshopper contact is authorized by this
slice. A real panel run remains separately authorized after merge.

## Proven foundation

The merged product seam already exposes:

```python
run_minimal_intent_worker_initial_body_integration(
    intent,
    planner_adapter=...,
    worker_transport=...,
    tool_executor=...,
)
```

That callable already owns strict Planner admission, deterministic compilation,
one Worker drafting transaction, code-only graph completion, one create call,
deterministic verification, native execution records, and the terminal result.
This slice delegates to it unchanged.

The live milestone at merge `df4bb84835648462b0700d30b758a04fad8dc00e`
proved one clean first-pass compile for the fixed specimen. The milestone is
recorded separately in
`docs/superpowers/2026-08-01-minimal-worker-first-clean-compile-milestone.md`.

## Scope

### In scope

- One **Build C#** action on `AgentChatTab`.
- One closed `execution_mode` request field on `/agent/chat/message`.
- One application-owned Worker-first composition root under `rook.agent`.
- One create-only wrapper over the real local `ToolDispatcher` surface.
- One bounded projection into existing `tool_start`, `tool_result`, and `done`
  events.
- Fake-backed panel, HTTP, application-root, integration, and tool-card tests.
- The smallest promotion of the existing Worker structured-response schema
  builder needed by a real production composition root, without changing its
  schema.

### Out of scope

- Changes to Planner draft admission, prompts, workflow contracts, templates,
  graph topology, Worker actions, receipts, or native result types.
- Chat model classification or prose-based routing.
- Ordinary Chat behavior changes.
- Conversation-history integration for Worker-first transactions.
- A second assistant prose pass.
- Repair, update, retry, fallback, alternate model, or another tool call.
- A generic application framework, event protocol, renderer, result taxonomy,
  archive, recorder, or durable evidence system.
- Grasshopper status checks, document replacement, or smoke-style preparation;
  the action uses the existing Chat-owned Rhino document context.
- MCP, CLI, Chirp, DSPy, or another product surface.
- Guaranteed interruption of an already-entered provider call.

## Closed user boundary

### Panel actions

The existing **Send** action and Enter-key submission remain unchanged. They
omit `execution_mode` and continue through `ChatRunner.run_turn()`.

`AgentChatTab` adds one dedicated **Build C#** action. It is per-message and
never sticky.

Both actions use one existing-style submission boundary:

```text
accepted_intent = input.Trim()
```

The boundary:

- refuses when `accepted_intent` is empty;
- preserves all interior whitespace;
- performs no downstream normalization;
- displays the normalized intent as the user's panel message;
- applies the existing concurrent-run guard; and
- disables Send and Build C# while either action is processing.

The Enter key continues to invoke ordinary Send only.

### HTTP payloads

Ordinary Send retains its current payload with no `execution_mode` member.

Build C# sends:

```json
{
  "conversation_id": "<existing conversation ID>",
  "message": "<accepted_intent>",
  "documentSerialNumber": 123,
  "execution_mode": "worker_first_csharp_v1"
}
```

The mode token is one closed code-owned value pinned across the managed client
and Python handler by cross-language contract tests. It enables no
configuration, override, retry, or fallback.

The exact-mode server boundary requires a built-in string that is nonblank and
already canonical under `message == message.strip()`. It does not trim again.

## Closed mode routing

`/agent/chat/message` branches only after ordinary JSON, conversation,
document-context, and concurrent-run checks:

```text
execution_mode absent
-> existing ChatRunner path byte-for-byte behaviorally unchanged

execution_mode == worker_first_csharp_v1
-> Worker-first handler path

every other present value
-> fixed unsupported_execution_mode refusal
-> no response stream preparation
-> no application-root, model, or tool construction
```

There is no content classifier, prose inference, implicit opt-in, or fallback
from the exact mode to the broad Chat agent.

Application-root construction is lazy. Missing and unknown modes do not resolve
the hybrid profile, build the root, or construct any capability.

## Ownership

### RookChat owns the view and request lifecycle

For the exact mode, the HTTP handler owns only:

- the normalized intent supplied by the panel;
- existing conversation lookup and concurrency;
- one real code-owned run ID;
- `abort_event.clear()` before the transaction;
- `conversation.touch()` at lifecycle boundaries;
- the Rhino request context;
- one off-event-loop execution boundary around the complete application
  transaction;
- streaming the three existing Chat events;
- clearing the matching run ID only after the off-loop transaction is
  quiescent; and
- connection/cancellation cleanup.

The exact-mode path does **not** append either the user request or a synthetic
assistant result to `conversation.messages`. That list remains ChatRunner model
history. The user action is already rendered by the panel and the outcome is
rendered by the tool card. Cross-mode conversational memory is not claimed.

### The application root owns the transaction

A narrow module under `mcp_server/src/rook/agent` owns the production
composition. It is not under `rook.agent.chat` and does not depend on
`ChatRunner`.

The application root:

1. resolves the existing `hybrid` profile;
2. requires exactly:
   - Planner: `anthropic/claude-opus-4-6`;
   - Worker: `ollama_chat/qwen3-coder:30b-a3b-q8_0`;
3. validates both role identities before constructing either transport or the
   tool surface;
4. constructs the Planner and Worker transports with the same reviewed live
   settings:
   - temperature `0`;
   - `max_tokens=1024`;
   - `max_retries=0`;
   - timeout `120.0` seconds;
5. gives the Planner the existing minimal-draft JSON schema through Anthropic's
   LiteLLM `response_format` path;
6. gives the Worker the unchanged local-worker response union schema through
   the existing structured-response path;
7. constructs the real local tool surface exactly as:

   ```python
   ToolDispatcher(local_tools=build_local_tools())
   ```

8. wraps that dispatcher in the create-only executor; and
9. calls `run_minimal_intent_worker_initial_body_integration()` once.

The existing private Worker response-schema implementation becomes one public,
code-owned builder because this is the first production composition root that
needs it. The schema bytes and semantics do not change, and no registry or
general schema framework is added.

Tests replace the transport and dispatcher constructors beneath this real
application root. They do not replace the root or the proven integration.

### One worker-thread boundary owns synchronous model execution

`LiteLLMWorkerTransport.send()` and both existing model adapters are
synchronous. The aiohttp handler therefore does not invoke the application
coroutine directly on its event loop.

The handler enters the existing Rhino request context and starts the complete
application transaction through one `asyncio.to_thread` boundary. A small
thread entry function owns a private `asyncio.run()` for the application
coroutine. Profile resolution, both transport constructions and calls,
deterministic compilation, Worker execution, and the create-only tool call all
occur inside that one off-loop transaction.

`asyncio.to_thread` copies the current `contextvars` context. The existing
Rhino request context must therefore be visible at dispatcher entry in the
worker thread. This is constructively tested; the implementation does not add
an alternate port argument or reconstruct the context from request fields.

The handler retains a task representing the off-loop transaction. Its matching
`active_run_id` remains installed until that task is genuinely done. If the
client disconnects or cancels the handler while the worker task is still
running, the handler sets `abort_event`, stops streaming, and defers run-ID
cleanup until the task completes. It does not cancel, detach as available work,
or replace the underlying provider transaction.

This is one execution-context boundary, not an async transport refactor,
dedicated scheduler, retry system, or generalized background-job framework.

### The create-only executor owns capability restriction

The executor accepts exactly `gh_create_csharp_script` and delegates it once to
the constructed dispatcher's `dispatch()` method. Every other tool name,
including `gh_update_script`, refuses before dispatcher entry.

The wrapper does not rewrite create parameters, inspect generated code, add a
repair path, or authorize a second call.

## Handler lifecycle

The exact-mode path uses this sequence:

```text
validate request, mode, conversation, and concurrency
-> assign code-owned run ID
-> clear abort event
-> touch conversation
-> prepare NDJSON response
-> emit tool_start
-> enter existing Rhino request context
-> start complete application root in one worker-thread event loop
-> await its task without blocking aiohttp
-> project returned native aggregate
-> emit tool_result
-> emit done
-> touch conversation
-> clear matching run ID after worker task quiescence
```

The tool-call identity is code-owned and unique per run:

```text
worker_first_csharp_v1:<run_id>
```

The exact same ID appears in `tool_start` and `tool_result`.

The handler maintains `abort_event`, observes connection cancellation, and
clears its matching run ID only after the off-loop task is done. It does not
guarantee cancellation of a Planner or Worker provider call that has already
been entered. This slice adds no transport refactor, scheduler, retry, or
provider cancellation framework.

## Existing Chat event representation

The exact-mode stream contains only:

```text
tool_start
tool_result
done
```

There is no assistant text event.

### `tool_start`

`tool_start` contains:

- `type = "tool_start"`;
- `name = "worker_first_csharp_v1"`; and
- the code-owned `tool_call_id`.

It contains no `params`, intent, prompt, or other payload.

### Bounded result object

The handler projects only ownership-backed facts from the returned native
aggregate:

```json
{
  "status": "success",
  "terminal_stage": "terminal",
  "terminal_reason": "terminal_node_selected:done",
  "compile_status": "passed",
  "error_count": 0,
  "warning_count": 0,
  "component_created": true
}
```

The fields are closed:

- `status`: `success` or `failed`;
- `terminal_stage`: a bounded safe native token or `null`;
- `terminal_reason`: a bounded code-owned native token or `null`;
- `compile_status`: `passed`, `failed`, or `unavailable`;
- `error_count`: exact nonnegative integer or `null`;
- `warning_count`: exact nonnegative integer or `null`; and
- `component_created`: exact boolean or `null`.

Terminal fields pass through a small closed safe-token projector. Anything not
admitted becomes `native_reason_unclassified`; model-authored or exception text
is never exported.

Receipt facts are read from the create producer's retained native receipt.
`error_count` and `warning_count` are the receipt's exact target error and target
warning counts. The projector does not rerun the workflow, reconstruct graph
lineage, or trust an unowned node.

Compile status is closed:

```text
passed      iff owned create receipt verification status == passed
failed      iff owned create receipt verification status == failed
unavailable otherwise
```

Creation state is also evidence-sensitive:

```text
true  iff an owned create receipt proves mutation status == created
false iff native evidence proves create was not entered or did not create
null  iff the mutation outcome cannot be proven
```

Success is exact:

```text
status == success iff
  terminal_stage == terminal
  terminal_reason == terminal_node_selected:done
  create receipt mutation status == created
  create receipt verification status == passed
  error_count == 0
  warning_count == 0
```

Every other condition yields `status == failed`.

When no owned create receipt exists, compile status is unavailable and both
counts are `null`. `component_created` is false only when native evidence proves
the create boundary was not entered or did not create; it is `null` after an
ambiguous post-dispatch or aggregate-construction failure.

### `tool_result`

`tool_result` contains:

- `type = "tool_result"`;
- `name = "worker_first_csharp_v1"`;
- the same `tool_call_id` as `tool_start`;
- `result` equal to the compact JSON serialization of the bounded object;
- `tool_status` exactly `success` when `status == success`, otherwise
  `failed`; and
- `verified` equal to the exact clean-compile success equation.

No prompts, model responses, generated code, rationale, GUID, raw receipt,
exception text, or invented explanation appears in the stream.

### Panel summary

`AgentChatTab.BuildToolSummary()` adds one small branch for
`worker_first_csharp_v1`. It renders only the bounded compile state and counts,
for example:

```text
Compiled cleanly (0 errors, 0 warnings)
Compile failed (2 errors, 1 warning)
Worker-first C# stopped before compile
```

This is not a generic renderer framework. Other tool summaries remain
unchanged.

### `done`

`done` uses the existing Chat event and panel completion behavior. It carries no
new result type or assistant prose.

## Failure behavior

Expected product stops return the same card shape:

| Boundary | Card projection | Downstream work |
|---|---|---|
| Planner adapter/admission | failed, compile unavailable | zero Worker and tool calls |
| Worker adapter/disposition/action | failed, compile unavailable | zero tool calls |
| Create dispatch failure | failed, owned receipt facts when present | no retry or second tool |
| Compile failure receipt | failed, exact counts and created state | no repair or update |
| Clean compile | success under the exact equation | done |
| Ordinary application exception | failed, native fields unavailable | no exception text or fallback |
| Create-only capability refusal | failed native dispatch stop | zero dispatcher calls for the rejected name |

Unknown modes use the pre-stream HTTP refusal and do not produce a tool card.

Client disconnect or cancellation may end the stream before `tool_result` or
`done`. Cleanup sets the abort event immediately but clears the matching run ID
only after the off-loop transaction is quiescent. No completed card is claimed
when it was not delivered.

## Managed panel mechanics

The base `ChatTab` gains only the smallest reusable UI mechanism needed for one
additional message action:

- retain the button row;
- allow `AgentChatTab` to add one secondary action;
- route Send and Build C# through the same trim/blank/concurrency/processing
  helper; and
- disable all registered message-action buttons while processing.

`ClaudeCodeTab` and other tabs add no secondary action and retain their current
layout and behavior.

`AgentChatClient` keeps the existing ordinary-send method unchanged and adds a
dedicated Worker-first send method. That method alone includes the exact mode
field. It consumes the existing NDJSON `ChatEvent` contract.

## Deterministic fake-backed vertical

The principal test traverses:

```text
Build C# request contract
-> real /agent/chat/message handler
-> real exact-mode lifecycle and Rhino request context
-> real application root
-> fake one-call Planner transport
-> real Planner adapter and strict draft loader
-> real Worker-first compositor and workflow compiler
-> fake one-call Worker transport through the real adapter
-> create-only executor
-> causally responsive fake create dispatcher
-> real receipt interpretation and native result
-> bounded event projector
-> tool_start / tool_result / done
-> existing panel tool-card handling contract
```

The causal fake create dispatcher:

- accepts only `gh_create_csharp_script`;
- checks the fixed tool-owned pins, name, position, call order, and Worker body;
- derives its receipt from the actual received parameters;
- rejects unexpected parameters or a second call; and
- makes no Rhino or Grasshopper contact.

## Test obligations

### Managed client and panel

- Ordinary Send and Enter omit `execution_mode`.
- Build C# includes exactly `worker_first_csharp_v1`.
- Both paths use `Trim()` once, preserve interior whitespace, and reject empty
  normalized input.
- Build C# is per-message and not sticky.
- Both buttons share the processing guard and are disabled during work.
- Enter continues to select ordinary Send.
- The tool card uses the same start/result ID and displays clean or failed
  compile counts through the one name-specific summary branch.
- Existing tool-card behavior for every other tool is unchanged.

### HTTP routing and lifecycle

- Missing mode invokes the existing runner exactly as before.
- Unknown, non-string, or misspelled mode refuses before application/model/tool
  construction.
- Exact mode never invokes `ChatRunner.run_turn()`.
- Canonical normalized intent reaches the application root unchanged.
- Padded or blank exact-mode messages refuse rather than being normalized again.
- Conversation concurrency returns the existing 409 behavior.
- Exact mode assigns one real run ID, clears abort, touches the conversation,
  propagates Rhino context into the off-loop transaction, and clears the run ID
  only after that transaction is quiescent.
- `conversation.messages` remains unchanged on success, native stops,
  operational exceptions, and cancellation.
- A blocking-fake application leaves the aiohttp event loop responsive: a
  heartbeat advances and a concurrent request receives `409`.
- Connection cancellation sets abort but cannot clear the run ID while the
  off-loop application is still running. The matching ID clears after the
  worker task finishes.
- Dispatcher entry in the worker thread observes the exact Rhino request
  context selected by the handler.

### Application root and capability construction

- Role resolution occurs before either transport or tool construction.
- Role mismatch produces zero transport and dispatcher constructions.
- Planner constructor receives `response_format` and no `format`.
- Worker constructor receives the unchanged Worker schema through `format` and
  no duplicate schema.
- Both calls use temperature `0`, `max_tokens=1024`, `max_retries=0`, and timeout
  `120.0`.
- The root constructs `ToolDispatcher(local_tools=build_local_tools())`.
- The create-only executor delegates one exact create call.
- `gh_update_script`, substitutions, repeats, and every other name refuse before
  dispatcher entry.

### Native projection and leakage

- The success witness satisfies every success equation.
- Mutating any one equation produces `failed`.
- Compile-error receipts retain exact counts and component-created state.
- Missing receipts produce unavailable/null compile fields and an
  evidence-sensitive false-or-null creation field.
- Planner and Worker stops before create prove `component_created = false`.
- An ambiguous failure after create dispatch begins but before an owned receipt
  exists yields `component_created = null`.
- An owned created receipt yields `component_created = true`; owned evidence
  that create did not occur yields false.
- Receipt selection comes from the create producer's retained record.
- The event sequence is exactly start, result, done.
- Start contains no parameters or intent.
- Result JSON contains only the seven bounded keys.
- Tool status is exactly `success` or `failed`.
- Verified equals the clean-compile equation.
- Prompts, responses, Worker code, rationale, GUIDs, raw receipts, exception
  messages, and sentinel values never reach the stream or panel summary.

### Call counts and stop paths

- Success: one Planner, one Worker, one create.
- Planner stop: one Planner, zero Worker, zero tool.
- Worker stop: one Planner, one Worker, zero tool.
- Compile failure: one Planner, one Worker, one create, zero update.
- No retry, repair, fallback, assistant prose pass, or second tool call exists.

## Non-claims

This slice proves only that the existing RookChat panel and HTTP lifecycle can
view one fake-backed execution of the independently owned Worker-first
application path.

It does not prove:

- live provider, Worker-box, Rhino, or Grasshopper integration through the
  panel;
- runtime output correctness;
- broad intent or interface coverage;
- repeatability;
- cross-mode conversation memory;
- cancellation of synchronous provider calls already entered; or
- a generalized user-intent routing architecture.

After review, implementation, merge, and a green fake-backed vertical, one
separately authorized panel run may exercise the already-proven real hierarchy.

## Stop condition

The slice is complete when:

- ordinary Chat remains unchanged;
- Build C# explicitly routes one normalized intent through the real
  application root with fake capabilities;
- the existing panel shows the bounded tool card;
- all expected stop paths preserve exact call prefixes;
- the create-only boundary is enforced before dispatcher entry; and
- no external system was contacted during implementation or review.

No additional harness, recorder, prompt, compiler, workflow, or product-surface
work belongs in this slice.
