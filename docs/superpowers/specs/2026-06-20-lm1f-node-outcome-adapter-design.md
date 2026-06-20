# LM1F: NodeOutcome Adapter For Tool Results And Script Receipts Design

## Status

Design draft for senior review. This document defines the LM1F slice only. It
must not be treated as approval for ChatRunner integration, PlanGraph execution,
LM2 capability registry work, verifier orchestration, retry policy, or live
Rhino/GH execution.

## Context

The local/internal model roadmap now has these completed LM1 foundations:

- LM1A: visible tools are structurally dispatchable.
- LM1B: `ToolResultView` normalizes existing tool-result truth for ChatRunner.
- LM1C: C# script preflight stops obvious invalid script payloads before GH
  mutation.
- LM1D: GH script create/update paths emit post-mutation `script_receipt`
  evidence and repair anchors.
- LM1E: `PlanGraph` stores DAG-local state, evidence, retry state, memory, and
  deterministic transitions from prepared `NodeOutcome` objects.

LM1E intentionally does not know how to create `NodeOutcome`. It only accepts
one. LM1F adds the first adapter between the truth/evidence layer and the graph
state layer:

```text
raw tool result
  -> ToolResultView
  -> script_receipt-aware NodeOutcome adapter
  -> PlanGraph reducer
```

The adapter is the narrow policy boundary that translates structured tool truth
into graph transitions. The graph reducer remains unintelligent.

## Goals

- Add a pure, non-live outcome adapter module:
  `mcp_server/src/rook/learning/plan_graph_outcomes.py`.
- Keep tool-result normalization in the import-light
  `mcp_server/src/rook/agent/chat/tool_result_view.py` module so the adapter
  does not import ChatRunner, ToolDispatcher, registry, or knowledge machinery.
- Expose exactly one public V0 helper:

```python
node_outcome_from_tool_result(result: Any) -> NodeOutcome
```

- Use `normalize_tool_result(...)` from LM1B for coarse tool truth.
- Extract `script_receipt` only from the current internal/server-shaped payload
  location: `result["data"]["script_receipt"]`.
- Interpret only the tiny documented `script_receipt["artifact_status"]` subset
  needed to choose `OutcomeStatus`.
- Package `ToolResultView` and receipt fields into `NodeEvidence`.
- Populate narrow `memory_updates` from explicit structured receipt fields.
- Keep all tests deterministic and non-live with canned result dictionaries.

## Non-Goals

- No ChatRunner integration.
- No PlanGraph execution, state walking, graph mutation, or scheduler behavior.
- No ToolDispatcher changes.
- No server/MCP wire-shape changes.
- No individual tool migration.
- No verifier calls.
- No Rhino/GH live dependency.
- No retry policy beyond returning a prepared `NodeOutcome`.
- No escalation policy beyond whatever status the mapping explicitly returns.
- No generic result ontology.
- No LM2 capability registry.
- No parsing GUIDs, messages, errors, or free-form text.
- No Claude/RookChat presentation-layer heuristics.
- No support for arbitrary external MCP result presentations in V0.

## Module Boundary

Create:

`mcp_server/src/rook/learning/plan_graph_outcomes.py`

Tests:

`mcp_server/tests/test_plan_graph_outcomes.py`

Allowed imports in `plan_graph_outcomes.py`:

- `typing.Any`
- `copy.deepcopy`
- `rook.agent.chat.tool_result_view.ToolResultView`
- `rook.agent.chat.tool_result_view.normalize_tool_result`
- `rook.learning.plan_graph.NodeOutcome`
- `rook.learning.plan_graph.NodeEvidence`

`tool_contracts.py` may re-export `ToolResultView` and
`normalize_tool_result(...)` for ChatRunner compatibility, but the adapter must
import them from `tool_result_view.py`. The data flow is:

```text
tool_result_view -> plan_graph_outcomes -> plan_graph
```

The import direction is:

```text
plan_graph_outcomes imports tool_result_view and plan_graph
tool_contracts imports tool_result_view only for compatibility re-export
tool_contracts imports neither plan_graph nor plan_graph_outcomes
plan_graph imports neither tool_contracts nor plan_graph_outcomes
```

Avoid these reversed import dependencies:

```text
tool_contracts -> plan_graph
plan_graph -> tool_contracts
```

`plan_graph.py` remains pure and import-light. `tool_contracts.py` remains
focused on model-visible tool contracts; the shared result-view normalizer lives
in `tool_result_view.py`.

## Public API

Use exactly:

```python
def node_outcome_from_tool_result(result: Any) -> NodeOutcome:
    ...
```

Private helpers are allowed for readability, for example:

```python
_extract_script_receipt(result: Any) -> dict[str, Any] | None
_status_from_view_and_receipt(
    view: ToolResultView,
    receipt: dict[str, Any] | None,
) -> str
_evidence_from_view_and_receipt(...)
_memory_updates_from_receipt(...)
```

Only `node_outcome_from_tool_result(...)` is public in V0.

## Receipt Extraction

LM1F starts with internal/server-shaped result dictionaries only.

Extract `script_receipt` only when:

```python
isinstance(result, dict)
isinstance(result.get("data"), dict)
isinstance(result["data"].get("script_receipt"), dict)
```

Do not look for top-level `script_receipt`.
Do not look for `receipt`.
Do not unwrap Claude/RookChat presentation payloads.
Do not infer receipts from strings or messages.

External MCP presentation layers may unwrap or transform fields differently.
LM1F intentionally does not handle those shapes yet.

## Outcome Status Mapping

If a recognized `script_receipt["artifact_status"]` exists, it wins over the
coarse `ToolResultView.status` for graph outcome status:

```text
artifact_status == "usable"
  -> NodeOutcome.status = "succeeded"

artifact_status in {"created_with_errors", "written_with_errors"}
  -> NodeOutcome.status = "needs_repair"

artifact_status == "verification_pending"
  -> NodeOutcome.status = "blocked"

artifact_status == "unknown"
  -> NodeOutcome.status = "blocked"
```

If a receipt exists but `artifact_status` is missing or unrecognized, fall back
to `ToolResultView.status` while still carrying the receipt as evidence. This
keeps the adapter compatible with additive receipt evolution.

Fallback mapping from `ToolResultView.status`:

```text
view.status == "success"
  -> NodeOutcome.status = "succeeded"

view.status == "failed"
  -> NodeOutcome.status = "failed"

view.status is None
  -> NodeOutcome.status = "blocked"
```

V0 deliberately maps `verification_pending` to `blocked`, not `succeeded`. The
artifact may exist, but the scaffold cannot safely advance to a clean terminal
state without verification.

## Evidence Packaging

Always call:

```python
view = normalize_tool_result(result)
```

Then build `NodeEvidence` with:

```python
NodeEvidence(
    tool_status=view.status,
    verified=view.verified,
    receipt=script_receipt,
    repair_anchor=repair_anchor,
    message=view.message or view.verification_note,
    error=view.error,
)
```

Rules:

- `ToolResultView.verification_note` must not disappear.
- `view.message` wins over `view.verification_note`.
- `view.error` maps directly to `NodeEvidence.error`.
- `receipt` is the extracted `script_receipt`, or `None`.
- `repair_anchor` comes only from `receipt["repair_anchor"]` when it is a dict.
- Do not support legacy or top-level `repair_anchor` in V0 unless a future slice
  proves an existing structured payload needs it.
- Deep-copy receipt and repair anchor before storing them in `NodeEvidence`.

## Memory Updates

LM1F should populate narrow `NodeOutcome.memory_updates` from explicit
structured receipt fields. This is adapter work, not graph intelligence.

Always return a `memory_updates` dictionary shaped like:

```python
{
    "facts": {},
    "node_summary": "...",
}
```

Populate `facts` only from structured receipt fields:

- `component_guid` from `receipt["mutation"]["component_guid"]` when it is a
  non-empty string.
- Fallback `component_guid` from `receipt["repair_anchor"]["component_guid"]`
  when mutation guid is absent.
- `repair_anchor` from `receipt["repair_anchor"]` when it is a dict.

Do not parse GUIDs from messages.
Do not parse errors.
Do not summarize transcripts.
Do not derive facts from arbitrary receipt fields.

Use only these deterministic summaries:

```text
artifact usable
artifact needs repair
verification pending
verification unknown
tool succeeded
tool failed
tool blocked
```

Summary mapping:

```text
artifact_status == "usable"
  -> "artifact usable"

artifact_status in {"created_with_errors", "written_with_errors"}
  -> "artifact needs repair"

artifact_status == "verification_pending"
  -> "verification pending"

artifact_status == "unknown"
  -> "verification unknown"

no recognized artifact_status and view.status == "success"
  -> "tool succeeded"

no recognized artifact_status and view.status == "failed"
  -> "tool failed"

no recognized artifact_status and view.status is None
  -> "tool blocked"
```

Do not use free-form `view.message` or `view.error` as `node_summary` in V0.
Those fields remain available in `NodeEvidence`.

Deep-copy `repair_anchor` and any nested facts inserted into `memory_updates`.

## Returned NodeOutcome

The adapter returns:

```python
NodeOutcome(
    status=<mapped status>,
    evidence=<packaged NodeEvidence>,
    memory_updates=<deterministic memory updates>,
    message=view.message,
    error=view.error,
)
```

`NodeOutcome.message` keeps only `view.message`, not
`view.verification_note`. The verification note is preserved through
`NodeEvidence.message` fallback.

The adapter does not increment retry counts, apply graph transitions, or inspect
the target graph. That remains `PlanGraph.apply_outcome(...)` work.

## Examples

### Compile Error Script Create

Input shape:

```python
{
    "success": False,
    "message": "Component was created, but the target script component has compile errors.",
    "data": {
        "script_receipt": {
            "version": 1,
            "operation": "create",
            "artifact_status": "created_with_errors",
            "mutation": {
                "status": "created",
                "method": "gh_create_component_then_script",
                "component_guid": "abc",
                "note": None,
            },
            "repair_anchor": {"component_guid": "abc"},
        }
    },
}
```

Output:

```python
NodeOutcome.status == "needs_repair"
NodeOutcome.evidence.tool_status == "failed"
NodeOutcome.evidence.receipt["artifact_status"] == "created_with_errors"
NodeOutcome.evidence.repair_anchor == {"component_guid": "abc"}
NodeOutcome.memory_updates["facts"]["component_guid"] == "abc"
NodeOutcome.memory_updates["node_summary"] == "artifact needs repair"
```

The receipt-specific artifact status wins over the top-level failed tool status
because the graph needs a repair branch, not a generic failure branch.

### Usable Script Artifact

Input has `artifact_status == "usable"` and top-level `success=True`.

Output:

```python
NodeOutcome.status == "succeeded"
NodeOutcome.memory_updates["node_summary"] == "artifact usable"
```

### Verification Pending

Input has `artifact_status == "verification_pending"`.

Output:

```python
NodeOutcome.status == "blocked"
NodeOutcome.memory_updates["node_summary"] == "verification pending"
```

### Unknown Or Missing Receipt

Input has no recognized receipt and:

```python
{"success": False, "error": "bad input"}
```

Output:

```python
NodeOutcome.status == "failed"
NodeOutcome.evidence.error == "bad input"
NodeOutcome.memory_updates["node_summary"] == "tool failed"
```

## Test Strategy

Add `mcp_server/tests/test_plan_graph_outcomes.py`.

Required non-live tests:

- `artifact_status == "usable"` maps to `succeeded`.
- `created_with_errors` maps to `needs_repair`.
- `written_with_errors` maps to `needs_repair`.
- `verification_pending` maps to `blocked`.
- `unknown` maps to `blocked`.
- Missing receipt falls back to:
  - top-level success -> `succeeded`
  - top-level failure -> `failed`
  - no truth -> `blocked`
- Receipt with missing or unrecognized `artifact_status` falls back to
  `ToolResultView.status` while still carrying the receipt.
- `NodeEvidence` carries:
  - `tool_status`
  - `verified`
  - `message`
  - `error`
  - `receipt`
  - `repair_anchor`
- `ToolResultView.verification_note` maps to `NodeEvidence.message` only when
  `view.message` is absent.
- `NodeOutcome.message` does not use `verification_note`.
- Memory facts use `mutation.component_guid` when present.
- Memory facts fall back to `repair_anchor.component_guid` when mutation guid is
  absent.
- Memory facts include `repair_anchor` only when it is a dict.
- Memory summaries are exactly the deterministic strings listed in this spec.
- Adapter does not parse GUIDs from messages or errors.
- Adapter deep-copies receipt, repair anchor, and memory facts; mutating the
  input result after adapter creation does not mutate the returned
  `NodeOutcome`.
- Non-dict results produce a blocked `NodeOutcome` with empty evidence fields
  and `node_summary == "tool blocked"`.

Boundary tests:

- `plan_graph.py` does not import `tool_contracts` or `plan_graph_outcomes`.
- `tool_contracts.py` does not import `plan_graph` or `plan_graph_outcomes`.
- AST direct-import checks prove `plan_graph_outcomes.py` imports
  `tool_result_view.py`, not `tool_contracts.py`.
- A lightweight import probe proves importing `rook.learning.plan_graph_outcomes`
  does not load `rook.agent.tool_dispatcher`.

Suggested verification:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_rookchat_tool_contracts.py -q
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/agent/chat/tool_result_view.py mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/src/rook/learning/plan_graph_outcomes.py
rg -n "tool_contracts" mcp_server/src/rook/learning/plan_graph_outcomes.py
rg -n "plan_graph" mcp_server/src/rook/agent/chat/tool_contracts.py
rg -n "tool_contracts|plan_graph_outcomes" mcp_server/src/rook/learning/plan_graph.py
git diff --check
```

## Acceptance Criteria

- `node_outcome_from_tool_result(result: Any) -> NodeOutcome` exists in
  `rook.learning.plan_graph_outcomes`.
- The adapter is pure and non-live.
- The adapter uses `normalize_tool_result(...)`.
- The adapter extracts receipts only from `result["data"]["script_receipt"]`.
- The adapter applies only the explicit artifact-status mapping in this spec.
- Receipt with unknown/missing artifact status falls back to `ToolResultView`
  status while still carrying receipt evidence.
- `NodeEvidence` preserves `ToolResultView` fields, including
  `verification_note` through message fallback.
- `memory_updates` contains only deterministic summaries and structured facts
  from `script_receipt`.
- Receipt, repair anchor, and memory facts are copied to avoid aliasing.
- No ChatRunner, dispatcher, server, public MCP, PlanGraph reducer, or
  capability registry behavior changes.

## Future Work

Future slices may:

- feed this adapter from a graph walker/state reducer loop;
- add verifier-specific adapters that produce `NodeOutcome` directly;
- consume `NodeOutcome` in ChatRunner or a local scaffold loop;
- add capability registry references in LM2;
- support external presentation-layer result shapes once those are explicitly
  inventoried.

Those are intentionally out of scope for LM1F.
