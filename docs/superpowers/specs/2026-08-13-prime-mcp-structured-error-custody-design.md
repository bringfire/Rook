# Prime MCP Structured Error Custody

**Status:** Design ready for independent review

**Date:** 2026-08-13

**Rook baseline:** `17a59b5ff24920efa6c2928262a4f0317b04d949`

**Prime audit:** local `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`; upstream
`7787f07415d843b9a800f6a4720e0c739bd608e5`

**Preserved Gate B V2 manifest:**
`030165216D5D1AF56ABCA2F4195D8424AB0EA6FAF65915CBDB5D915AF35E3AD3`

## Purpose

Preserve an MCP server's authentic structured failure result through Prime Agent without
making a failed tool call look successful, then let Rook apply its existing deterministic
dispatch and mutation classifications to that evidence.

The required boundary is:

```text
MCP CallToolResult
-> preserve exact structuredContent and legacy text
-> raise enriched McpToolError
-> recorder retains the authentic structured result
-> original error still reaches Prime
-> Rook applies existing mutation classifications
-> latest committed terminal receipt supersedes earlier receipts
```

This is a generic MCP-runtime correction and a bounded Rook integration correction. It is
not a Rook-specific Prime fork, a new receipt system, an exception parser, or a retry layer.

## Triggering Evidence

Gate A already passed and must not run again. The consumed Gate B V2 evidence at
`C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v2` remains byte-for-byte
unchanged.

That retained run contains, in order:

1. a known `rook_tools_read` refusal that dispatched zero target calls;
2. a failed `gh_edit` envelope reporting committed mutations and an exact readiness
   receipt;
3. a later successful `gh_edit` with a newer committed terminal receipt; and
4. a later observational snapshot.

Rook correctly classified the first two failed calls as unknown because Prime discarded
their `structuredContent` before raising `McpToolError`. No production code may reconstruct
those results from the retained exception strings. The retained evidence is historical
custody and a fixture source only; the repaired boundary is proven by offline causal tests
and one fresh Gate B run.

## Audited Ownership

Prime's current and upstream `prime-agent-runtime/src/rlm/mcp_base.py` both raise
`McpToolError` from `_parse_result()` before reading `structuredContent`. Upstream contains
no existing correction to reuse.

The owners remain:

```text
Prime MCP runtime
  owns CallToolResult projection and failed-call exception behavior

Gate B rook_full adapter
  owns correlating one attempted gateway call with one source event

Rook gh_behavioral_acceptance
  owns source-event validation, dispatch/mutation projection, receipt selection,
  probing, and deterministic evaluation

Prime native session
  owns evidence that the original McpToolError remained visible to the Actor
```

Prime imports no Rook modules or concepts. Rook imports no Prime module in production.
The disposable adapter is the only integration point.

## Considered Approaches

### 1. Enriched `McpToolError` plus result-first Rook recording — selected

Prime retains exact `structuredContent` on the exception. The adapter records a valid
structured failure as a Rook result event and then re-raises the same exception. This keeps
failed-call control flow and authentic capability evidence simultaneously, without changing
the closed Rook event schema.

### 2. Put both result and exception in each Rook event — rejected

This would change the source-event schema, normalization, validation, and every existing
fixture merely to duplicate an exception already retained by Prime's independently hashed
runtime stream.

### 3. Parse JSON from `str(McpToolError)` — rejected

Legacy text is presentation, not structured custody. Parsing it would be Rook-specific,
ambiguous, lossy, and vulnerable to text changes. It is prohibited in production and tests.

## Prime Contract

`McpToolError` remains a `RuntimeError` and gains exactly one public evidence field:

```python
McpToolError(message: str, structured_content: Any = None)

exception.structured_content
```

The field is the exact object returned by the MCP SDK as `CallToolResult.structuredContent`.
Prime does not copy, normalize, validate, interpret, or serialize it. `super().__init__()`
receives the same message as today, so `str(exception)` remains exactly:

```text
joined TextContent text, when any text exists
otherwise "MCP tool returned an error"
```

`_parse_result()` reads `structuredContent` once before the `isError` branch. Its behavior is:

| MCP outcome | Prime result |
|---|---|
| `isError=true`, structured content present | raise `McpToolError` with exact field value |
| `isError=true`, no structured content | raise same legacy `McpToolError`; field is `None` |
| success with structured content | return exact structured value as today |
| success with text only | return joined text as today |
| transport/session exception | propagate the original ordinary exception unchanged |

There is exactly one `session.call_tool()` invocation. No retry, second session, fallback,
text parsing, Rook import, receipt logic, refusal taxonomy, or mutation interpretation is
admitted.

## Rook Recorder Contract

The existing closed source-event schema remains unchanged: exactly one of `result` and
`exception` is nonnull.

`gh_behavioral_acceptance` adds one public helper for an MCP error outcome. Its conceptual
contract is:

```python
append_canonical_gateway_error_source_event(
    source_path,
    target,
    arguments,
    *,
    exception,
    structured_content,
) -> event
```

The helper accepts an ordinary Python `Exception`; it does not import or name
`McpToolError`. It applies this complete rule:

```text
structured_content is exactly a dict
and keys are exactly {"success", "data"}
and success is exactly false
  -> append the exact structured_content as a result event

otherwise
  -> append the exception as an exception/unknown event
```

The exact `arguments` snapshot is captured before the awaited gateway call. Existing
canonical JSON validation and write/fsync custody apply. No structured value is synthesized
from the exception message.

The disposable adapter handles the Prime exception as follows:

```text
catch McpToolError
-> pass the same exception and its structured_content field to the public Rook helper
-> append exactly one source event
-> re-raise the same exception object
```

If source-event validation or persistence itself raises, that recorder failure must not
replace the already-authentic `McpToolError`. The adapter re-raises the original exception;
the missing event prevents source closure and makes the run incomplete. It does not invent
a fallback row or retry the write.

A normal result continues through `append_canonical_gateway_source_event(result=...)`.
Any other exception continues through the existing exception/unknown path and is re-raised.
The adapter never swallows, replaces, retries, or converts an exception into a successful
return.

For an enriched MCP failure, the Rook source event intentionally has `exception=null`
because it owns the authentic capability result. Prime's independently retained and hashed
native session owns proof that the original exception remained visible. These two records
are correlated by the frozen call order, target, arguments, source closure, and runtime hash;
neither record impersonates the other.

## Dispatch And Mutation Projection

Existing Rook classification remains authoritative:

```text
known structured zero-dispatch refusal
-> dispatch refused_before_dispatch / target_call_count 0
-> observational mutation

structured gh_edit, including success=false
-> exact edit_summary counts determine committed versus none
-> exact valid solve_readiness_receipt retained
-> terminal mutation

successful later gh_edit
-> same existing terminal classification

read-only snapshot
-> observational mutation
```

The zero-dispatch refusal vocabulary is not expanded for this slice. A structured failure
on an observational target is observational only when it proves one existing recognized
zero-dispatch refusal. An unrecognized refusal/error code, missing refusal evidence, or
otherwise unexplained failed observational result is mutation-unknown and blocks admission.
This conservative rule does not affect a failed `gh_edit` whose exact existing commit
projection proves a partial terminal mutation.

## Admission And Receipt Selection

Admission must fail closed across the complete trace, not only after the selected receipt.
Before choosing a receipt, Rook rejects the trace if any event has:

- a nonnull exception;
- dispatch status `unknown`;
- mutation classification `unknown`; or
- mutation commit status `unknown`.

Known preparatory, legacy, observational, zero-commit terminal, and committed terminal
events retain their existing meaning. Among committed terminal events, the latest event's
valid receipt supersedes every earlier receipt. After that selected event, only
observational events are admissible. Any later preparatory, legacy, zero-commit terminal,
or committed terminal event remains `later_unfenced_mutation`.

Therefore the reviewed Gate B sequence is admissible only when reconstructed from authentic
structured results:

```text
known failed read             -> observational
partial committed gh_edit     -> terminal receipt R1
later committed gh_edit       -> terminal receipt R2; supersedes R1
later gh_snapshot             -> observational
selected receipt              -> R2
```

Transport exceptions, errors without structured evidence, malformed structured content,
`success=true` content attached to `McpToolError`, and unknown refusal codes remain
ineligible. When admission is ineligible, the behavioral probe executor receives zero calls.

The managed receipt registry, scheduler, fenced snapshot, behavioral probe, evaluator
semantics, and Gate A evidence do not change.

## Offline Causal Tests

### Prime

Tests use fake MCP sessions and SDK-shaped results, without network contact, and prove:

- `McpToolError` remains a `RuntimeError` and exact error text is unchanged;
- structured failure payload identity is retained exactly;
- structured-only failure uses the legacy fallback message;
- text-only failure has `structured_content is None`;
- success with structured or text results is unchanged;
- an ordinary transport exception is the same propagated exception object;
- each case enters `session.call_tool()` exactly once;
- JSON-looking exception text with absent structured content remains absent evidence; and
- no retry, result reconstruction, Rook import, or interpretation exists.

### Rook and disposable adapter

Tests use closed fixtures derived from the reviewed Gate B result shapes, never parsed
exception strings, and prove:

- the known failed read becomes an observational zero-dispatch refusal;
- partial `gh_edit` remains committed terminal with its exact receipt;
- the later successful `gh_edit` supersedes that receipt;
- the later snapshot remains observational and the newer receipt is selected;
- the adapter re-raises the same enriched exception object after one exact result event;
- a recorder validation/write failure still re-raises that original exception and leaves
  the source unclosed rather than fabricating a row;
- missing, malformed, or `success=true` structured evidence records exception/unknown;
- transport exceptions, mutation errors without structured evidence, and unknown refusal
  codes block admission;
- unknown evidence before or after a terminal event blocks admission;
- every uncertain case produces zero behavioral-probe executor calls; and
- no production or test code derives structured evidence from exception text.

## Repository And Evidence Custody

Prime and Rook changes are separate focused commits in separate repositories. Prime's
commit contains only the generic runtime correction and its tests. Rook's commit contains
only the recorder/admission correction and its tests. The future disposable Gate B sibling
is evidence infrastructure, not a production module.

Before and after offline work, the consumed Gate B V2 manifest hash must remain:

```text
030165216D5D1AF56ABCA2F4195D8424AB0EA6FAF65915CBDB5D915AF35E3AD3
```

No Rhino, Grasshopper, Rook MCP, Ollama, Qwen, or other live runtime may be contacted during
implementation or review.

## Post-Review Live Gate

Only after both commits pass offline review may the exact reviewed Prime and Rook payloads
be deployed. Gate A is not repeated. Gate B runs exactly once in a fresh sibling evidence
root against a fresh empty Grasshopper canvas, with the same Qwen model, reasoning, intent,
skill, acceptance artifact, limits, and no-repair rule. The adapter import preflight must
pass before model startup.

The run preserves Prime's native exception evidence, the authentic Rook source trace, the
latest terminal receipt, the fenced probe, and deterministic evaluation. Any runtime or
target drift, malformed custody, lingering owned process, or failed preflight stops the run
without retry.

## Bounded Claim

If the offline tests and the single fresh Gate B run pass, the supported claim is only:

> Prime preserves structured MCP failure evidence while maintaining failed-call control
> flow, allowing Rook to distinguish proven refusals, partial commits, and unknown failures
> without weakening deterministic acceptance.

This does not claim universal MCP error semantics, recovery from unknown mutations, model
semantic success, Gate A repetition, or a reusable evaluation framework.
