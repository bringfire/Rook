# Minimal Intent-to-Worker Real Grasshopper Compile Milestone

**Date:** 2026-07-31

**Status:** Completed live product milestone

**Merge commit:** `90242fa4f09abf8f3b8ec994044787b61e77b446`

**Merge parents:**
`87abcc459b7f4cbc0b0bc6f06b711499260e72f2` and
`85cc7c52fad515788bf10e5e33d820bf4e5c34f0`

**Pull request:** #520, local Grasshopper script pin materialization

**Trace:**
`C:\Users\bring\AppData\Local\Rook\traces\minimal-intent-worker-real-compile-20260731T074409.901890Z-p53428-da645f64.jsonl`

**Trace size:** 24,486 bytes

**Trace SHA-256:**
`239cecb9b7b50a4fd22f19d179a0d1d6e4ee5897b1719c3f94eb4ec30cd29a59`

## Milestone

The fixed one-component specimen completed the intended hierarchy in one real
transaction:

```text
exact user intent
-> frontier Planner
-> strict four-field draft admission
-> deterministic workflow compilation
-> real Grasshopper C# component creation
-> real failed compile receipt
-> bounded local Worker action
-> receipt-bound update of the same component
-> real Grasshopper compile verification
-> native terminal success
```

This is the first observed end-to-end success of the product hierarchy in
which both model roles, deterministic orchestration, the existing typed-tool
bridge, and the real Grasshopper compiler participated in one continuous
transaction.

## Exact observed chain

The JSONL flight recorder contains 23 contiguous events, numbered `1` through
`23`, and ends with a successfully flushed `run_finished` event.

| Boundary | Observation |
|---|---|
| Run and document preparation | One RookNative target was frozen. `gh_status -> gh_document_new -> gh_status` established a fresh, empty, unsaved, editable Grasshopper document before model construction. |
| Planner | The fixed intent was sent once to `anthropic/claude-opus-4-6`. The response decoded and passed the existing strict four-field draft loader. |
| Compiler | The admitted draft compiled into the existing `gh_csharp_create_verify_repair_verify` workflow. Neither model authored graph topology, node IDs, rules, action IDs, or execution wiring. |
| Initial create | `gh_create_csharp_script` created a real component. The receipt reported `created_with_errors`, exactly one target compile error, and zero target warnings. |
| First verification | The deterministic verifier classified the create receipt as `needs_repair` and made `repair_same_component` ready. |
| Worker | The local `ollama_chat/qwen3-coder:30b-a3b-q8_0` Worker was called once. Its structured response was admitted as the existing `draft_repair_params` action. |
| Receipt-bound update | `gh_update_script` used the component GUID originating in the create receipt. The Worker-authored body was the update body; the controller supplied the GUID. |
| Reverification | The real update receipt reported `usable`, zero target errors, and zero target warnings. The verifier marked `verify_repair` successful and made `done` ready. |
| Terminal result | The existing native result ended at `terminal_node_selected:done`. `run_finished` reported `completed / native_terminal`. |

The bounded call counts were exactly:

```text
document-preparation tool calls: 3
Planner calls:                    1
Worker calls:                     1
execution tool calls:             2  (create, update)
retries or fallbacks:             0
```

The create and update receipt projections carried the same component GUID.
The transition was therefore a repair of the created component, not creation
of an unrelated replacement.

## Tuple-boundary repair confirmed

The initial live attempt had stopped before component creation because the
in-process dispatcher preserved immutable workflow tuples while the strict
server boundary correctly required JSON-array/list pin declarations. PR #520
fixed the shared product boundary, not the smoke:

```text
exact tuple pins
-> fresh lists in _normalize_gh_create_script_kwargs()
-> unchanged strict server validation
```

All three local create aliases share that normalization:

- `gh_create_script`;
- `gh_create_python_script`; and
- `gh_create_csharp_script`.

The successful live create proves that the contract-style tuple used by this
workflow now reaches the real strict handler in its admitted list form.

## What this proves

For this fixed specimen, the following major seams work together:

- a frontier Planner can reduce exact user intent to the admitted tiny semantic
  draft;
- deterministic code can compile that draft into the existing bounded
  workflow;
- the real Grasshopper create path can produce a typed failed-compile receipt;
- the local Worker can consume the current requirement and diagnostic context
  and return the one allowed repair action;
- controller-owned receipt projection can bind the repair to the exact created
  component;
- the real update path and Grasshopper compiler can produce a clean receipt;
  and
- existing graph transitions and terminal selection can complete without a
  retry, fallback, hidden repair, or model-authored topology.

The flight recorder is diagnostic telemetry that makes this production chain
inspectable. It is not an authority source, checkpoint, archive, or substitute
for the typed receipts and native result that determined execution.

## What this does not prove

This was one deliberately forced repair specimen. It does not establish:

- general user-intent coverage;
- correctness of the component's runtime output;
- repeatability across runs, models, machines, or Rhino sessions;
- arbitrary input/output interfaces or pin types;
- native Grasshopper pin typing—the final readback reported `Generic Data`,
  consistent with current script-component behavior;
- that the Worker can author a correct initial body before component creation;
- a user-facing Chat, MCP, CLI, Chirp, or other product entry point; or
- a need for additional recorder, archive, readiness, or experimental
  infrastructure.

The trace contains raw model and tool adapter-boundary content. It remains
sensitive, disposable local diagnostic material outside the repository.

## Architectural consequence and stop condition

The forced-repair implementation line stops here. The same specimen should not
be rerun merely to accumulate repetitions, and the private recorder should not
be generalized on the strength of one product path.

The next KISS slice should replace the deliberately broken compiler-owned
starter body with a normal compiler-owned Worker drafting step:

```text
validated Planner draft
-> deterministic workflow with an initial Worker drafting node
-> one Worker-authored C# body
-> first real create call
-> one deterministic compile verification
-> native result
```

That slice should preserve the proven Planner draft, deterministic compilation,
typed tool execution, receipt interpretation, and bounded Worker transport. Its
design question is how the Worker-authored initial body enters the create node
without giving either model authority over workflow topology, component
identity, tool selection, or verification meaning.
