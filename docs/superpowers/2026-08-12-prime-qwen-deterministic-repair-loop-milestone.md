# Prime/Qwen Deterministic Repair-Loop Milestone

**Date:** 2026-08-12

**Classification:** `repaired_pass`

**Prime Agent:** `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`

**Qwen artifact:** `ollama_chat/qwen3.6:35b`, reasoning `medium`, manifest SHA-256
`07D35212591FC27746F0A317C975A6D68754FB38E9053D82E25F06057AF28522`

**Rook production source:** `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`

This milestone is documentation-only. Recording it does not change or deploy the qualified
Prime, Rook, Rhino, Grasshopper, model, skill, adapter, evaluator, or operator runtime.

## Frozen Experiment

Exact intent:

> Create a Grasshopper definition that generates a row of points along the X axis using
> adjustable Start, Step, and Count controls, with Y and Z fixed at zero.

The disposable operator admitted one Qwen Actor turn, one independent snapshot and
deterministic evaluation, and at most one same-session repair followed by one independent
snapshot and deterministic evaluation. The evaluator alone owned completion. `fail` or
`incomplete` admitted the single repair; no model Critic, fallback model, cleanup, retry, or
third turn was available.

Frozen semantic authorities:

```text
acceptance artifact  376C429878536C01B58DB403F440DD54C612AD627299C1EA62CA533B4A39A7C0
evaluator            0CB6DE02B86D3A2B7B5D6D5F59AFC10365D0AB4D23DF1E4ED2119D136377BC80
execution skill      0F7C8D1F2D612FFB7522469C4E3D467985E8872585CA3C18DF9B46BD1A84D36E
rook_full adapter    E7577F0EC8A9B504712BC73290BB8F4C673E9677AEF952CFBFC346F206A62996
```

The initial canvas was independently verified empty at epoch `1`. The frozen target was
Rhino PID `45372`, native port `55363`, Rhino document serial `268435457`.

## Phase 1: Deterministic Refusal

Qwen created seven components and six wires:

```text
S / St / C sliders -> Series -> Construct Point
zero panels -----------------> Construct Point Y / Z
```

The graph already produced ten points beginning `(0,0,0)`, `(1,0,0)`, `(2,0,0)` with zero
runtime errors and warnings. Qwen claimed completion, but the sliders were labeled `S`, `St`,
and `C`, not the required `Start`, `Step`, and `Count` identities.

The deterministic evaluator returned `fail`:

```text
adjustable_controls_present              fail
point_count_equals_count                 unproven
first_x_equals_start                     unproven
successive_x_difference_equals_step      unproven
all_yz_zero                              pass
no_runtime_errors                        pass
```

Only the exact six ordered criterion IDs, statuses, and evaluator evidence—plus the original
intent and closed one-turn repair boundary—were returned to Qwen. The feedback did not
prescribe Series, component GUIDs, wiring, or topology.

## Phase 2: One Bounded Repair

Prime resumed the exact same native session with `--resume`. Qwen retained the same seven
component IDs and six wires. It renamed the three sliders to `Start`, `Step`, and `Count`,
varied the controls to observe the corresponding output changes, and restored defaults:

```text
Start 0 -> 5            first X 0 -> 5
Step 1 -> 3             successive difference 1 -> 3
Count 10 -> 5           point count 10 -> 5
restored                Start 0, Step 1, Count 10
```

The independent Phase 2 snapshot retained seven components and six wires, ten final points,
structurally fixed zero Y/Z, and zero errors or warnings. A fresh evaluator invocation exactly
reproduced `pass` for all six criteria.

## Operational Evidence

- Phase 1: Prime exit `0`, one final `agent_end`, 256.25 seconds, 25 IPython cells.
- Repair: Prime exit `0`, same session ID, one final `agent_end`, 99.45 seconds, 11 IPython cells.
- Provider-reported cumulative token telemetry: 428,847 Phase 1 plus 384,266 repair-added
  tokens. These are operational observations, not a normalized efficiency score.
- Both stderr files are empty; both process ledgers retain no owned process after termination.
- Visible model cells used only the supported `rook_full.search/read/call` interface.
- Strict contained-tool admission truthfully rejected one malformed `gh_inspect_output` call;
  it did not compromise the final graph or deterministic acceptance.

Evidence root:

`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1/operator`

| Artifact | SHA-256 |
|---|---|
| `target.json` | `1A2945B09D900370AC1CABDC99BAC27A802D7853D904BF3C83FC31067985CD78` |
| `initial-inspection.jsonl` | `F429D14FD6C5D9B77523C9A6BA6129A18E140F390A8D9E82771887023D404B68` |
| `initial-prime.jsonl` | `A64B83CC71BC394DFCE42A3D3979EEFB81446802A81B6DD8384F70C62CB856EB` |
| `initial-session.jsonl` | `C8C9BB48C9D92E3D9B21AD9A7E84F12020AB1DB53D5749138A5FB8C29E0E6E99` |
| `initial-process-ledger.json` | `DEF0D8023E585E2EBF3C1197AD645759504B5B6C6ED23449E23ECEC74DAD1980` |
| `phase-1-snapshot.jsonl` | `C28235180DF5E0892E7B032599D09A77436CDB3514DFD7F81AB9B22D50B739DF` |
| `evaluation-1.json` | `4554B558ADA48FACEDF3E1B437C6EFF761576E475E81FED545FFD27A14311E48` |
| `repair-feedback.json` | `BF0DE6F8D6AF7646C1D68E0546617349F926A946069C1D6111E6D26F860D6B64` |
| `repair-prime.jsonl` | `C186FD6DDAF3AB51A079BECDC8E9EEB866A528C71FEA3EE88C438A347BB41BC7` |
| `repair-session.jsonl` | `FD4DCB9CDF3BEB42175D32508B430A3341C7050DF080ABA0507B12A2303C939F` |
| `repair-process-ledger.json` | `DE1F93EA2852335D2438BCF95168576077B8A0C5B2E32D9A8623C923C4D94C72` |
| `phase-2-snapshot.jsonl` | `E090236C87D87033DB1C8251BFA6E624256C23B3AAAF362F6593AB26BB3C6536` |
| `evaluation-2.json` | `66D880B8CAA778E5852FE685FC501CDE36324E6D16540DAE854F29EF4B67051A` |

## Proven Claim And Limits

This run proves that deterministic semantic feedback enabled one local Qwen Actor to repair
an evaluator-identified acceptance defect within one bounded continuation in the same Prime
session.

The repaired defect was control naming, not component selection or topology. Phase 1 already
contained the correct Series/Construct Point graph. This run therefore does not prove repair
of incorrect wiring, wrong component selection, missing semantics, repeatability, arbitrary
acceptance compilation, general Grasshopper competence, or production readiness.

The next bounded step is exactly two unchanged repetitions on separately verified fresh
canvases. Each result remains independent and is classified as `initial_pass`,
`repaired_pass`, `fail`, or `incomplete`; no aggregate score is defined.
