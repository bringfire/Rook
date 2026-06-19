# LM1B: RookChat Tool Result View Design

## Status

Design approved for implementation planning. This document defines the LM1B
slice only. It must not be treated as approval for a dispatcher refactor or a
result-envelope migration.

## Context

LM1A closed the first local-model reliability gap by proving that visible
RookChat local-profile tools have a structural dispatch path. The next gap is
result truth at the ChatRunner and dispatcher boundary.

Today, `ChatRunner` decorates `tool_result` events with a small boolean-centric
status classifier and separate ad hoc verification-field extraction. That is
good enough for a few known shapes, but it leaves the model-visible truth layer
implicit. Local/internal models need a stable adapter that interprets existing
tool results consistently without changing how tools execute or how public MCP
responses are formatted.

The public MCP wire shape is load-bearing and remains unchanged:

- internal tool dispatch returns dicts such as `{ "success": bool, "data": ... }`;
- public MCP `call_tool()` still renders success as the `data` payload only and
  failure as `Error: ...`;
- ChatRunner conversation history still stores the raw serialized tool result.

## Goals

- Introduce a shared internal `ToolResultView` adapter for model-visible tool
  result interpretation.
- Use that adapter at the ChatRunner tool-call consumption boundary.
- Preserve current raw result serialization and conversation history content.
- Preserve current `ToolDispatcher.dispatch()` return semantics.
- Add non-live tests for representative dispatcher-shaped results and
  ChatRunner-intercepted results.
- Make the next result-truth step mechanically reusable without beginning a
  full result-envelope redesign.

## Non-Goals

- No dispatcher refactor.
- No public MCP wire-shape change.
- No migration of individual tools to a new result envelope.
- No `ui_block` behavior change.
- No full result ontology or result-envelope redesign.
- No Rhino live dependency.
- No PlanGraph, C# preflight, workflow-tool, or capability-registry work.

## Architecture

LM1B adds `ToolResultView` and `normalize_tool_result(...)` to
`mcp_server/src/rook/agent/chat/tool_contracts.py`.

That module's scope broadens from "tool schema contracts" to
"model-visible tool contracts":

- model-visible schema normalization and auditing;
- visible-tool dispatchability auditing;
- model-visible tool result interpretation.

`ToolDispatcher.dispatch()` remains non-invasive in this slice. Dispatcher
outputs may be used in adapter tests, but dispatcher execution and return
semantics do not change.

## ToolResultView Contract

`ToolResultView` should be plain immutable data:

```python
@dataclass(frozen=True)
class ToolResultView:
    status: Literal["success", "failed"] | None
    verified: bool | None
    verification_note: str | None
    message: str | None
    error: str | None
```

The adapter function is:

```python
def normalize_tool_result(result: Any) -> ToolResultView:
    ...
```

The function must be structural and side-effect free:

- no tool execution;
- no Rhino calls;
- no MCP formatting;
- no mutation of the input result;
- no exceptions for unfamiliar result shapes.

For non-dict results, every field in the view is `None`.

## Truth Precedence

The adapter has one explicit truth system:

1. Top-level `success` / `ok` wins.
2. Nested `data.success` / `data.ok` applies only when top-level truth is absent.
3. Top-level `error`, then nested `data.error`, implies failure only when no
   explicit boolean truth exists.
4. Never infer truth from a field named `status`.

Only actual bool values count for `success`, `ok`, and `verified`. The adapter
must not coerce truth-like values such as `"true"`, `"false"`, `0`, or `1`.

An error implies failure only when it is truthy or non-empty and no explicit
boolean truth exists. For example, `{ "success": true, "error": "legacy warning" }`
normalizes to `status == "success"`.

Informational extraction is independent from status:

- top-level `message` wins over nested `data.message`;
- top-level `error` wins over nested `data.error`;
- `message` and `error` do not override explicit boolean truth.

`message` and `error` fields on `ToolResultView` should only be populated from
string values. A truthy non-string `error` may imply `status == "failed"` when
no explicit boolean truth exists, but it must not be stringified into
`view.error`.

## Verification Precedence

Verification extraction is also explicit:

1. Top-level `verified` wins when it is an actual bool.
2. Nested `data.verified` applies only when top-level `verified` is absent.
3. Top-level `verification_note` wins when it is a string.
4. Nested `data.verification_note` applies only when top-level
   `verification_note` is absent.

The compatibility fallback is intentionally narrow:

- only nested `data.verified is False`;
- and no nested `data.verification_note`;
- and nested `data.message` is a string;
- then `verification_note` may fall back to nested `data.message`.

Top-level `verified=False` plus top-level `message` must not create a
verification note. A top-level message is not newly treated as a verification
note unless an explicit top-level `verification_note` is present.

## ChatRunner Integration

ChatRunner should consume the adapter only after preserving today's raw result
serialization path.

The order is load-bearing:

1. Produce the raw result through the existing path:
   - chat-model pseudo-tool result;
   - meta-tool result;
   - dispatcher result from `_tool_executor`;
   - exception wrapper result.
2. Compute `result_str` from the raw result exactly as ChatRunner does today.
3. Append the raw serialized `result_str` to conversation history exactly as
   today.
4. Derive `ToolResultView` from the raw result.
5. Use the view only to decorate `ChatEvent` fields:
   - `tool_status = view.status`;
   - `verified = view.verified`;
   - `verification_note = view.verification_note`.

The adapter must not become the serialized object stored in conversation
history.

`_classify_tool_status(...)` must not remain as a second truth system. The
implementation should either remove it or reduce it to:

```python
return normalize_tool_result(result).status
```

## ui_block Scope

`ui_block` is explicitly out of scope for LM1B.

It is ChatRunner-intercepted, but today it emits a `ui_block` event and appends
tool content without emitting a `tool_result` event. LM1B must not change that
behavior. The design may document `ui_block` as a non-`tool_result` intercepted
path, but implementation must not route it through the new event-decoration
adapter.

## Tests

All LM1B tests should be non-live and deterministic.

Adapter unit tests should cover:

- top-level failure beats nested success;
- top-level success beats nested failure;
- top-level success beats nested error;
- nested success works when top-level truth is absent;
- error-only result becomes failed;
- truthy non-string error can imply failure but does not populate `view.error`;
- non-dict result returns all `None`;
- string `status` is ignored;
- non-bool truth-like values are ignored;
- top-level message wins over nested message;
- top-level string error wins over nested string error;
- non-string message/error values are not stringified into the view;
- top-level verification wins over nested verification;
- nested `verified=False` without nested note falls back to nested message;
- top-level `verified=False` plus top-level message does not create a
  verification note.

ChatRunner tests should prove the adapter decorates:

- chat-model pseudo-tool results;
- meta-tool results;
- dispatcher tool results;
- exception wrapper results.

ChatRunner tests should also assert raw history preservation:

- `result_str` is computed from the same raw serialization path as before;
- the stored tool message content equals that raw `result_str`;
- `ToolResultView` does not participate in serialization.

ChatRunner tests should not validate `ToolResultView.message` or
`ToolResultView.error` through ChatRunner unless ChatRunner consumes those
fields in this slice. Those fields are adapter-level concerns for LM1B.

## Acceptance Criteria

- A shared `ToolResultView` and `normalize_tool_result(...)` exist in the
  model-visible contract layer.
- ChatRunner event decoration uses the adapter for all current `tool_result`
  paths.
- `_classify_tool_status(...)` is removed or delegates to the adapter.
- Raw conversation tool content is unchanged.
- `ui_block` behavior is unchanged.
- `ToolDispatcher.dispatch()` behavior is unchanged.
- Public MCP `_format_tool_result()` behavior is unchanged.
- Non-live tests cover adapter precedence, ChatRunner event decoration, and raw
  history preservation.

## Risks And Carry-Forward

The adapter creates a stable internal interpretation layer, but it does not
make every individual tool truthful. Some tools may still return ambiguous
legacy payloads. That is acceptable for LM1B. Later slices can migrate specific
tool families or introduce richer operation/verification/artifact statuses once
the boundary adapter is in place.

The next implementation plan should stay narrow: add the adapter, wire
ChatRunner event decoration through it, test the representative result shapes,
and stop.
