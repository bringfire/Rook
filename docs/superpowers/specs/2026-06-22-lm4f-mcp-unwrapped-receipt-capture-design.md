# LM4F — MCP-unwrapped Script Receipt Capture

**Date:** 2026-06-22
**Campaign:** Local/Internal-Models (LM) reliability — Stage 5 (live PlanGraph execution)
**Slice:** LM4F — consumer-tolerance fix unblocking LM4E
**Status:** Design approved (brainstorming), ready for implementation plan

---

## Goal

Teach the PlanGraph receipt consumer to find `script_receipt` in **both** result
envelope shapes that the production tool layer produces, so a live producer node
projects correctly regardless of which shape the executor returns. Pure-consumer
change in `plan_graph_outcomes.py`; no change to the tool-result formatter or the
MCP executor.

## Why (the live discovery, grounded)

LM4E's live run surfaced this. There are **two** documented, non-interchangeable
tool-result shapes (`_format_tool_result`, `server.py:20431`;
`docs/CURRENT_ARCHITECTURE.md` "Tool Result Surface"):

- **Internal / dispatcher envelope:** `{"success": bool, "data": {...}}`.
- **Public MCP wire:** `call_tool()` text is, on **success**, `json.dumps(data)` —
  the `data` ONLY (envelope dropped); on **failure**, `"Error: " + json.dumps(data)`.

`_mcp_tool_executor` (`server.py:743`) parses that wire text back:

- **success** → `json.loads(text)` → the **unwrapped** `data` dict, so
  `script_receipt` sits at the **top level** (`result["script_receipt"]`), and there
  is no `success`/`data` key.
- **failure** → strips `"Error: "`, parses the remainder, returns
  `{"success": False, "data": parsed}` — so `script_receipt` is **re-wrapped** at
  `result["data"]["script_receipt"]`.

The consumer `_extract_script_receipt` (`plan_graph_outcomes.py:35`) reads **only**
`result["data"]["script_receipt"]`. Therefore:

| Live case | `success` | receipt location | consumer reads it today? |
|-----------|-----------|------------------|--------------------------|
| Clean component → `usable` | unwrapped | **top-level** | **NO** → node `blocked` |
| Genuine compile error → `created_with_errors` | `False` (re-wrapped) | `data.script_receipt` | YES |

Empirically confirmed live (Rhino + GH, this build): a clean component returns the
top-level shape (the receipt is present, just one level up), and erroring bodies
(`A = DefinitelyMissingSymbol;`, `A = ;`) return the re-wrapped failure shape with
`artifact_status == "created_with_errors"` at `data.script_receipt`. So **only the
success / top-level shape is unhandled**; the failure path already works.

This is a consumer-tolerance bug, not an executor bug. The MCP success shape
("success text is `data`") is documented and load-bearing — agents in the wild may
depend on it — so the fix belongs at the PlanGraph consumer boundary, never in
`_mcp_tool_executor` / `_format_tool_result`.

## The change (single function, strictly additive)

`_extract_script_receipt` in `mcp_server/src/rook/learning/plan_graph_outcomes.py`,
**nested-first, top-level fallback**:

```python
def _extract_script_receipt(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    # Nested dispatcher / MCP-failure shape FIRST (unchanged):
    #   result["data"]["script_receipt"].
    data = result.get("data")
    if isinstance(data, dict):
        receipt = data.get("script_receipt")
        if isinstance(receipt, dict):
            return deepcopy(receipt)
    # Fallback: MCP success-unwrapped shape -- receipt at the top level.
    receipt = result.get("script_receipt")
    if isinstance(receipt, dict):
        return deepcopy(receipt)
    return None
```

**Precedence (locked: A — nested-first, top-level fallback).** The nested branch
runs first and returns exactly as today whenever a nested receipt is present, so:

- Every existing wrapped/nested path is byte-stable (same branch, same deep-copy).
- **Both-present → nested wins** with no extra branching (nested returns first).
- The only relaxation: when `data` is non-dict (the unwrapped shape has no `data`
  key), the function no longer early-returns `None` — it checks the top level.
- A non-dict top-level `script_receipt` falls through to `None`.

`_repair_anchor(receipt)` derives from the returned receipt, so the repair anchor
follows automatically once the receipt is found at either location. No other
function changes.

## Out of scope (explicitly unchanged)

- `_mcp_tool_executor` and `_format_tool_result` — documented, load-bearing; not
  touched.
- `normalize_tool_result` — left as-is. For the unwrapped success shape it yields
  `status=None, verified=None` (the payload carries no `success`/`verified` key).
  That is harmless: the producer projection (`project_receipt_outcome`,
  `_producer_success`) sets `verified=True` from `artifact_status == "usable"`,
  overriding the carried value. **No invented `tool_status == "success"`
  inference.**
- No change to the producer projection, the reducer, or any LM4A–E module.

## Data flow proven

```
raw top-level MCP success payload (script_receipt at top level)
  -> node_evidence_from_tool_result            (receipt now FOUND via fallback)
  -> project_receipt_outcome(role=artifact_producer)   (usable -> succeeded, verified True)
  -> reducer apply_outcome                      (node.status = "succeeded")
```

## Tests (`mcp_server/tests/test_plan_graph_outcomes.py`)

1. **Nested shape regression.** `{"success": True, "data": {"script_receipt": {...}}}`
   still extracts the receipt and **deep-copies** it (mutating the return does not
   touch the input).
2. **Top-level shape (the fix).** `{"script_receipt": {...}, "component_guid": ...}`
   (no `data` key) extracts the receipt and deep-copies it.
3. **Both present → nested wins.** A result carrying distinguishable receipts at
   both `data.script_receipt` and top level returns the nested one.
4. **Non-dict top-level receipt ignored.** `{"script_receipt": "not a dict"}` →
   `None` (falls through), and the non-dict `data` early-relaxation does not raise.
5. **`node_evidence_from_tool_result` on a top-level `usable` payload.** Returns a
   `NodeEvidence` whose `receipt` is the usable receipt and whose
   `repair_anchor.component_guid` is present; `tool_status is None` and
   `verified is None` (the unwrapped payload carries neither — grounded, not
   over-asserted).
6. **Producer payoff through the real consumer path.** Build a ready
   `artifact_producer` node and call **`apply_producer_result(graph, node_id,
   raw)`** with a top-level `usable` MCP-success payload (NOT
   `project_receipt_outcome` directly — drive the exact path LM4E uses:
   `raw -> node_evidence_from_tool_result -> producer projection -> reducer`).
   Assert `result.outcome_status == "succeeded"`, the updated node
   `status == "succeeded"`, and the updated node `evidence.verified is True`.

## Verification gates

- New + existing `test_plan_graph_outcomes.py` green.
- Full focused PlanGraph gate from the repo root: **≥ 236 passed** (LM4F's new
  tests add to the count; no existing test regresses).
- `py_compile` clean on `plan_graph_outcomes.py` and the test file.
- Production diff confined to the single function `_extract_script_receipt` in
  `plan_graph_outcomes.py` (plus its tests + this spec/plan).

## Constraints (Global)

- Pure-consumer change; only `_extract_script_receipt` in `plan_graph_outcomes.py`
  is modified in production code.
- Nested-first, top-level fallback; both-present → nested wins; defensive ordering,
  not a new semantic branch.
- Do NOT change `_mcp_tool_executor`, `_format_tool_result`, or
  `normalize_tool_result`. No `tool_status` inference.
- Deterministic; no model calls; no live tools; no HTTP; no Rhino.
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Focused PlanGraph gate runs from the **repo root** (purity probes use
  repo-root-relative paths).

## Relationship to LM4E

LM4F unblocks LM4E. After LM4F merges to `main`, LM4E (`codex/lm4e-live-producer-smoke`,
PR #332) rebases onto the new `main` and swaps its broken-body to the empirically
confirmed `A = DefinitelyMissingSymbol;` (`pins_out=["A:double"]`, yields
`created_with_errors` on this build; `B = new Box();` does not error on this build).
The clean LM4E test then passes because the top-level `usable` receipt reaches the
consumer.
