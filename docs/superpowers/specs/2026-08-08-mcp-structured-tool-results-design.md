# MCP Structured Tool Results Design

**Status:** Proposed
**Baseline:** `02918747d38412419954c86fa3167a421eadfea4`
**Scope:** One backward-compatible correction at Rook's public MCP tool-result boundary

## Purpose

Rook currently renders every completed tool result as a single `TextContent` item. On
success the text is JSON for the internal `data` value; on failure it is the same data
prefixed with `Error: `. This public text contract is established and must remain
byte-for-byte unchanged.

Generic MCP clients nevertheless receive neither `structuredContent` nor truthful
`isError` for ordinary Rook failure envelopes. Prime Agent consequently treats successful
results as strings and ordinary Rook failures as successful strings. Its Python cells must
parse JSON manually and cannot distinguish a returned refusal from a normal text result by
the MCP contract.

This slice adds the internal Rook result envelope to the public MCP response as structured
metadata while retaining the existing text exactly.

## Context From Prime V4

Prime V4 established that a local model can use the supported `search`, `read`, and `call`
Python affordance without exposing Rook's complete catalog or bypassing the canonical MCP
gateway. It built a mechanically functioning Grasshopper definition, but exact semantic
fidelity was not established:

- Start and Step sliders were mechanically identifiable by their wiring but had blank
  nicknames;
- Y and Z sliders were requested with equal bounds, but Grasshopper materialized a small
  nonzero range;
- the model nevertheless described the result as exact and fixed.

V4 is therefore gateway-qualified, mechanically successful, and semantically incomplete.
Its adapter, skill, intent, and evidence remain frozen. This specification addresses only
the MCP result ergonomics revealed by that run.

## Existing Ownership

The internal dispatcher already owns the authoritative envelope:

```text
{
  "success": boolean,
  "data": any JSON-compatible value
}
```

`server._format_tool_result()` is the sole existing conversion from that envelope to the
legacy text surface. `server.call_tool()` is also called directly by internal Python code,
tests, ChatRunner composition, and nested canonical dispatch. Those consumers must continue
receiving the existing `list[TextContent]` result.

The MCP Python SDK can return a `CallToolResult` containing both unstructured content and
structured content. That public request boundary is the correct owner of the additive
projection.

## Public Result Contract

For every ordinary completed Rook tool envelope, the public MCP result is:

```text
structuredContent = {
  "success": exact internal success boolean,
  "data": exact internal data value
}

isError = not success
content = existing TextContent, byte-for-byte unchanged
```

The envelope supports object, array, string, number, boolean, and null data without a
second schema or result taxonomy. It is the existing internal envelope, not a Prime-specific
projection.

Examples:

```text
internal: {"success": true, "data": ["a", 2]}
content text: unchanged existing JSON text for ["a", 2]
structuredContent: {"success": true, "data": ["a", 2]}
isError: false

internal: {"success": false, "data": {"error": "invalid_arguments"}}
content text: unchanged existing Error-prefixed JSON text
structuredContent: {"success": false, "data": {"error": "invalid_arguments"}}
isError: true
```

`isError` is derived from the authoritative internal boolean before text formatting. No
model interpretation, text-prefix inference, or reparsing of formatted output may determine
the classification.

Unexpected exceptions that escape before Rook produces an internal envelope retain the MCP
SDK's existing exception behavior. This slice does not create an exception taxonomy or
fabricate structured data for such failures.

## Boundary Shape

The implementation separates two uses of the same canonical execution path:

```text
internal caller
-> canonical envelope execution
-> existing _format_tool_result()
-> existing list[TextContent]

public MCP request
-> same canonical envelope execution
-> existing _format_tool_result() for content
-> additive CallToolResult(structuredContent, isError)
```

The public MCP adapter is thin and code-owned. It does not alter targeting, profile checks,
argument validation, dispatch, native receipts, observation recording, or text formatting.
No public output schema is added.

The existing internal `server.call_tool()` surface remains a text-content adapter for its
current callers. ChatRunner continues to use its existing injected canonical gateway and
existing MCP-to-agent conversion unchanged.

## Canonical Gateway Semantics

The four `rook_tools_*` operations use the same public contract as direct tool calls.

For `rook_tools_call`, the structured envelope describes the invoked target's result
directly:

```text
rook_tools_call(name="gh_snapshot", arguments=...)
-> {"success": <gh_snapshot success>, "data": <gh_snapshot data>}
```

It must not become:

```text
{"success": true, "data": {"success": <target success>, "data": ...}}
```

The canonical gateway continues to enforce recursion, containment, profile, dispatchability,
schema, targeting, and native dispatch rules before returning the target envelope. Discovery
operations retain their own ordinary result envelopes.

## Client Consequences

MCP clients that read only `content` observe exactly the current wire text.

Clients that prefer `structuredContent` receive the uniform envelope. Prime Agent will
therefore return the envelope dictionary for successful Rook calls. When Rook returns an
ordinary failed envelope, Prime checks `isError` first and raises its existing `McpToolError`.
That behavior is truthful and requires no Prime change.

Internal Rook and ChatRunner callers do not cross the public MCP projection and therefore
retain their current results and behavior.

## Verification

Focused, no-contact tests cover the registered public MCP request boundary rather than only
calling the internal `server.call_tool()` helper.

Table-driven success cases use exact data values of:

- object;
- array;
- string;
- number;
- boolean;
- null.

Failure cases use:

- object data;
- string data.

Every case proves:

- `content` is byte-for-byte equal to the existing formatter output;
- `structuredContent` is exactly `{"success": boolean, "data": value}`;
- `isError` is exactly the inverse of the internal success boolean;
- arguments reach the existing canonical owner unchanged at its ingress;
- dispatch occurs exactly once.

Additional causal tests prove:

- a direct MCP target call returns its native envelope;
- `rook_tools_call` returns that same target envelope without double wrapping;
- gateway refusal remains policy-owned and is marked `isError=true`;
- internal `server.call_tool()` still returns the existing `list[TextContent]`;
- existing shared text parsers still parse the unchanged content;
- ChatRunner's injected canonical gateway result conversion remains unchanged;
- no external provider, Prime, Rhino, Grasshopper, or MCP subprocess contact occurs.

## Scope And Hard Stops

Production scope is limited to `mcp_server/src/rook/server.py`. Focused Python tests and a
concise architecture-contract documentation update may accompany it.

Stop before implementation expansion if the correction requires:

- a Prime change;
- a ChatRunner change;
- managed Grasshopper or native code changes;
- a second production module;
- `outputSchema` additions;
- new result classes, protocols, parsers, or receipt taxonomies;
- changes to public legacy text;
- duplicated dispatch, targeting, profile, or validation logic.

## Explicit Deferrals

This slice does not address:

- Number Slider equal or inverted range admission and normalization evidence;
- authoritative Grasshopper input default or connection-required metadata;
- Prime session reuse or MCP connection pooling;
- model critics, scoring, retries, or semantic evaluation machinery;
- ChatRunner's fallback catalog;
- V4 skill or prompt tuning;
- any new agent, harness, compiler, or product UI behavior.

Slider admission and component-default metadata remain separate product findings with
different owners. They require their own evidence-led designs before the next unchanged
comparison run.

## Claims

If implemented and verified, this slice may claim only that public Rook MCP clients receive
an additive, truthful structured projection of the existing internal result envelope while
legacy text and internal callers remain compatible.

It does not claim improved model judgment, Grasshopper semantic correctness, broader skill
compatibility, or successful live qualification.
