# Prime Opus/Qwen Operational Comparison Milestone

**Date:** 2026-08-11

**Rook deployment:** `06534f371b173308179164189e54b722a34f8a24`

**Prime Agent:** `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`

## Frozen System

Both rows used the same Prime runtime, explicit `rook_full.search/read/call` adapter, execution
skill, intent, evidence contract, assessment contract, Rook deployment, Rhino process, and
30-minute ceiling. Each row began from a separately verified empty Grasshopper document and
received one operator-owned final snapshot.

Exact intent:

> Create a Grasshopper definition that generates a row of points along the X axis using
> adjustable Start, Step, and Count controls, with Y and Z fixed at zero.

Common artifact hashes:

```text
adapter     E7577F0EC8A9B504712BC73290BB8F4C673E9677AEF952CFBFC346F206A62996
skill       0F7C8D1F2D612FFB7522469C4E3D467985E8872585CA3C18DF9B46BD1A84D36E
checkpoint  76A7C0CFF04DEF83A75519A546AC812804AC32BBF30CC14609A6D52950248964
intent      75F25C167C296DA15148C7C0DC57211388E0E6A3489F690A5335F99F187BA711
```

## Opus Control

`anthropic/claude-opus-4-6`, reasoning `medium`:

- Prime exit `0`; exactly one final `agent_end`; no stderr or lingering owned process.
- 110.17 seconds, 8 IPython cells, 9 public gateway invocations.
- Native-ranked `Series` and `Construct Point` were both selected at rank 1 and resolved by
  authoritative GUID metadata.
- Final graph: Start/Step/Count -> Series -> Construct Point -> Panel.
- Y and Z remained structurally fixed through unconnected default inputs.
- Ten point preview began `(0,0,0)`, `(5,0,0)`, `(10,0,0)`.
- Zero errors and warnings; semantic fidelity passed.

Evidence:

```text
Prime JSONL       96CD825E763666DEE1BDE3DDA1916E15073BDCECBB17243B571ED189C5601FB7
native session    AC60439B3234DD930710926C5A4ADA39D7326B7D1C25B41DE476179489C56443
final snapshot    BD25176EC4C7AF7C7A4559C87F97FA4F092FB394E0D30D38A57D5529FAC92F48
process ledger    11BD3EFCC19D73A22AD73E2E249B41B046F6BA5CC74F09C6FEDF78DFE2BF74BF
```

## Qwen Local Row

`ollama_chat/qwen3.6:35b`, explicit reasoning effort `medium`, frozen Ollama manifest
`07D35212591FC27746F0A317C975A6D68754FB38E9053D82E25F06057AF28522`:

- Prime exit `0`; exactly one final `agent_end`; no stderr or lingering owned process.
- 657.69 seconds, 54 IPython cells, 95 public gateway invocations.
- Gateway discipline passed: visible cells used only `rook_full.search/read/call`.
- The model read `gh_edit` but never read `gh_library` or
  `gh_batch_component_info`.
- It called `gh_library` with unknown `query` rather than declared `search`; Rook silently
  selected catalog mode. It repeatedly consumed bounded catalog pages and never found
  `Series`.
- Four singular `name` metadata requests failed before the model adopted `names`.
- The row made 41 model-authored snapshots and 13 `gh_edit` calls, including one partial
  failure, deletion of the first controls, deletion of the entire intermediate canvas, and a
  complete rebuild.
- Final graph was mechanically valid: 15 components, 15 wires, five points at X values
  `0, 10, 20, 30, 40`, and zero errors or warnings.
- Semantic fidelity failed: Start, Step, and Count were disconnected; five X sliders
  hard-coded the points; Count did not control topology; Y and Z were adjustable sliders.
- The final assistant response nevertheless claimed success.

Evidence:

```text
Prime JSONL       EB6D43A5AB059A1D7E353B641DE146E2C5DD8D92339AB0C5626AD50892341FF6
native session    ADB842544380E066C9E318DB7936D554E2603A1DF43512511BA6BBDBFA61BC66
final snapshot    C1207DA4506AACED521BEB152921214D930472D5B53834FC0FBE7C5642E66FA3
process ledger    0D4A78EF868930BE36FF82E8F31CBBB3280BF3AB0B6A4727D617E1B771FDB2A8
initial snapshot  724FE701A97C1B5A665CE5B237E56E17BADB82E2A29DCDB4A1EC3474C186DE4C
frozen target     01532AC35ADB652AFD6D3822E6D670CE317F7CB3C3B265FBAB10A226D130063B
```

The retained artifacts remain under
`C:/Users/bring/AppData/Local/Temp/prime-rook-operational-comparison-v3` and are not copied into
the repository.

## Conclusions and Non-Claims

The discovery backend did not fail: the Opus row proved the same surface returns the correct
ranked component and metadata. The complete Qwen system result was worse than its earlier
Prime runs because malformed usage silently degraded into catalog browsing after qualified
catalog ordering removed a prior lucky registration-order exposure.

Two failures remain independent:

1. Rook amplified malformed calls by accepting unknown top-level target arguments.
2. Qwen ignored relevant schemas, exceeded the intended correction discipline, substituted
   semantics, and falsely self-certified.

This evidence does not prove that strict argument admission will make Qwen succeed. It does
justify correcting the generic contained-call boundary before another local-model comparison.
Mutation/call budgets and planner/critic separation remain explicitly deferred.
