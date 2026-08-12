# Prime/Qwen XY-Grid Repair-Loop Milestone

**Date:** 2026-08-12

**Result:** `fail` after the one admitted same-session repair

**Prime Agent:** `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`

**Model:** `ollama_chat/qwen3.6:35b`, reasoning `medium`, manifest SHA-256
`07D35212591FC27746F0A317C975A6D68754FB38E9053D82E25F06057AF28522`

**Rook production source:** `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`

This milestone is documentation-only. It does not change or deploy Rook, Prime, the
adapter, the skill, or either retained evaluator.

## Frozen Boundary

The exact intent was:

> Create a rectangular grid of points in the XY plane with four adjustable sliders:
> Columns=3, Rows=2, X Spacing=5, and Y Spacing=10. Anchor the grid at the origin and
> keep every Z coordinate fixed at zero.

The disposable operator admitted:

```text
one Qwen Actor turn
-> independent baseline and frozen behavioral evaluation
-> exact criterion feedback
-> one repair in the same Prime session
-> independent final baseline and frozen behavioral evaluation
-> stop
```

The complete target was Rhino PID `27816`, native port `51223`, document serial
`268435457`. The independently captured initial snapshot was empty. A prior request-only
inspection residue is preserved separately from before the user confirmed that a fresh
Grasshopper document was open. That residue does not prove the earlier canvas state; it
caused no model call or retained mutation evidence and was not reused as the target.

Frozen semantic authorities:

| Artifact | SHA-256 |
|---|---|
| Manifest | `E84121EE558A77CAB0B7C12B41FB16A327D5F86E0A6335129DE98DE52675358D` |
| Target | `3F5529662399B27316132AD8277B9710B1F7B974A098ED33EFD5CC0480E70C56` |
| Acceptance | `E429E50619C2D7037298CECFC90352641E397602A1BC9A8554B4ED48193FD77F` |
| Evaluator | `C62AE9A15D5D6578C986BFD0E56F8947501ED0CFD5DBD9BF819614B08508EF8E` |
| Operator | `B51D8F1D9456D9FA2452522AC80DD0F4C676261021E3AE937BFCE4BD89577C94` |

## Independent Outcomes

| Phase | Result | Prime time | IPython cells | Failed cells | Provider token telemetry |
|---|---|---:|---:|---:|---:|
| Initial | `fail` | 950.71s | 66 | 10 | 3,194,329 |
| Repair | `fail` | 433.29s | 18 | 7 | 1,541,285 |
| Combined | `fail` | 1,384.01s | 84 | 17 | 4,735,614 |

The token count is cumulative provider-reported operational telemetry across messages, not
unique context tokens. Ollama reported zero monetary cost.

### Initial phase

The first independent baseline contained six components and three wires:

- sliders named `Col` and `Row`;
- two panels holding `5` and `10`;
- a default Python 3 component with only two connected inputs; and
- an unconnected Point parameter with one warning.

All four required control identities were absent, no terminal point preview existed, and
diagnostics were nonzero. The evaluator therefore refused the control-dependent claims
without perturbing the canvas.

### Repair phase

The unchanged feedback contained only criterion statuses, failure identifiers, evidence,
and the original intent. Qwen continued the same Prime session. The final independent
baseline contained 19 components and nine wires:

- sliders `Cols=3`, `Rows=2`, `XSpac=5`, and `YSpac=10`;
- five panels, two Addition components, two Multiplication components, two Range
  components, two Graft Tree components, Construct Point, and a Point parameter;
- one terminal point preview, `(0,0,0)`; and
- zero errors and three warnings.

Only `Rows` matched the frozen control identity. No Range or Graft output reached Construct
Point, and the Point parameter remained unconnected. `all_z_zero` passed for the sole
observed origin point, while `adjustable_controls_present` and `clean_diagnostics` failed.
The seven control-dependent grid criteria remained `unproven`. Because control admission
failed, the operator again made zero perturbation or restoration calls.

Qwen emitted no user-visible completion text after the repair. The deterministic evaluator,
not model self-report, owned the final `fail` classification.

## Gateway And Discovery Behavior

All 84 visible IPython cells stayed within `rook_full.search`, `rook_full.read`, and
`rook_full.call`. There were zero `list_tools`, `call_tool`, private-integration, direct
HTTP, subprocess, fallback-model, or lower-level adapter attempts.

Qwen used all four canonical target capabilities needed by the experiment:
`gh_library`, `gh_batch_component_info`, `gh_edit`, and `gh_snapshot`. It searched for
Range, Addition, Multiplication, Graft Tree, Construct Point, script components, and other
candidates, and it did use GUID metadata. Discovery was nevertheless highly exploratory:
the trace includes invalid argument attempts, repeated searches and snapshots, malformed
Python cells, failed edits, deletion and reconstruction, and unresolved confusion about
Range Domain inputs and script-component ports.

The native session contains 3 statically parseable `search` sites, 1 `read` site, and 184
`call` sites across syntactically valid cells. Those are source observations, not an exact
live MCP-call count: loops, branches, and three syntax-error cells prevent that inference.
The live trace does not independently observe internal meta-tool dispatch; the frozen
adapter hash and delegation tests bind the public calls to canonical envelopes.

## Comparison With The Point-Row Loop

| Property | Point row V1-V3 | XY grid V1 |
|---|---|---|
| Independent runs | 3 | 1 |
| Final outcomes | 3 passes | 1 fail |
| Maximum repair | 1 | 1 |
| Acceptance basis | Reviewed primitive semantics plus snapshot evidence | Topology-neutral control perturbations plus Cartesian output evidence |
| Typical successful graph | 7 components / 6 wires | No accepted graph |
| Representative repaired run | 36 cells, 813,113 token telemetry, 355.70s | 84 cells, 4,735,614 token telemetry, 1,384.01s |
| Live perturbation evidence | Qwen varied and restored Start, Step, Count | Not reached because exact control admission failed |

The reusable boundary is real but small:

- target, lifecycle, terminal-evidence, and same-session custody;
- strict request/result evidence rows;
- deterministic criterion envelopes and exact feedback;
- one-control-at-a-time set/snapshot/restore mechanics; and
- exact normalized restoration checks.

The task-specific layer remained substantial:

- exact control labels, baseline values, and probe values;
- terminal-point-output selection;
- point-preview parsing and completeness;
- Cartesian-product cardinality and coordinate expectations; and
- origin and fixed-Z constants.

The grid implementation added roughly 600 and deleted 476 lines across the evaluator,
inspection, and launcher relative to the point-row V3 forms. This is evidence against a
third bespoke evaluator. Behavioral probing removes component-GUID and topology
assumptions from the semantic criteria, but this run reached only its admission boundary;
it does not yet prove the full perturb/restore path on a second domain.

The supported next architectural move is therefore limited to extracting a small common
custody/probe/result core from the two implementations. Control bindings and domain
expectations must remain reviewed data. A semantic registry, generalized evaluation
framework, model Critic, or third task-specific evaluator is not justified by this run.

## Evidence Custody

Disposable evidence root:
`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-xy-grid-repair-loop-v1/operator`

| Artifact | SHA-256 |
|---|---|
| Initial Prime JSONL | `2BF9843B99F7D3CE18330C6E74D483AC51E78A3BF7F43778FE23772F12C8DE17` |
| Initial native session | `04382D0768B7D1CD15B777F2129B16613050754DDCBD494078E427CA752D2811` |
| Initial process ledger | `A943F48C09033DA468A0A21683581F4F664AECFDA3CB0E617DB73751779C91F7` |
| Phase 1 probe | `46BFF9CFBB255D0282764B3503892D024A6281D2FBBCDB809BA4ECBBF358CE9C` |
| Evaluation 1 | `94F0247F96897EA7BC0F59C24E1E99A5D695BD90BA3549387C1E1A1D6D264931` |
| Repair feedback | `9E1975F0E8928C033E304D66FF019EB84A6DAD5595E36EBBB60DF2A4C78E15A8` |
| Repair Prime JSONL | `D204668A9C7BD78835FD92CCDEC880C38A770DB787825F1138B1ABF36CC05A0F` |
| Repaired native session | `A822B0DE20922E87445CBDCE343C4BBA4AC795397858E6D26D5FA93290EE8185` |
| Repair process ledger | `8DE77AB6558C537B6D20590D1A6748E8B93CFBDD56EED073A490ED9F116927CA` |
| Phase 2 probe | `7A30E2354EF6E794E6CAA3BC5E9C03C8055C40222CC1D01035C421AC14B4C9AF` |
| Evaluation 2 | `361E8978886B2502BBB7BA7E6E7A325C277013B0A4320DE5F2FD42347F2A0CC5` |
| Both stderr files | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |

The completed execution ledger is retained at
`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-xy-grid-repair-loop-v1/execution-ledger.json`,
SHA-256 `7695487F533B8DD0229D50EBD768FDBA6EFF69F325CED8AF41330341E59652EE`.

Both Prime phases terminated naturally with exit code `0`. No qualification-owned process
remains. There was no operator rerun, adapter retry, cleanup, fallback model, third Actor
turn, or second repair.

## Bounded Conclusion

The deterministic boundary worked: it rejected a plausible-looking but nonfunctional grid,
provided exact failure evidence, admitted one same-session repair, and rejected the still
nonfunctional result. The repair increased graph complexity but did not establish the
requested control identities or causal grid behavior.

This proves failure detection and bounded repair custody on a second semantic domain. It
does not prove successful topology repair, successful behavioral probing on that domain,
general Grasshopper competence, acceptable efficiency, or readiness for a reusable
evaluation framework.
