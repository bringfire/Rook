# Prime/Qwen Deterministic Repair-Loop Repeatability Milestone

**Date:** 2026-08-12

**Results:** V1 `repaired_pass`; V2 `initial_pass`; V3 `repaired_pass`

**Prime Agent:** `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`

**Model:** `ollama_chat/qwen3.6:35b`, reasoning `medium`, manifest SHA-256
`07D35212591FC27746F0A317C975A6D68754FB38E9053D82E25F06057AF28522`

**Rook production source:** `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`

This milestone is documentation-only. It did not change or deploy the qualified product
runtime, and it does not modify any retained qualification evidence.

## Frozen Boundary

All three runs used the exact intent:

> Create a Grasshopper definition that generates a row of points along the X axis using
> adjustable Start, Step, and Count controls, with Y and Z fixed at zero.

They held the Actor, model artifact, reasoning, Prime runtime, execution skill, `rook_full`
adapter, acceptance artifact, evaluator, evidence contract, and orchestration behavior
constant. Each run started on an independently verified empty canvas and admitted:

```text
one Actor turn
-> one independent snapshot and deterministic evaluation
-> exact criterion feedback only after fail or incomplete
-> at most one repair in the same Prime session
-> one independent final snapshot and evaluation
-> pass or stop
```

Frozen semantic authorities:

| Artifact | SHA-256 |
|---|---|
| Acceptance | `376C429878536C01B58DB403F440DD54C612AD627299C1EA62CA533B4A39A7C0` |
| Evaluator | `0CB6DE02B86D3A2B7B5D6D5F59AFC10365D0AB4D23DF1E4ED2119D136377BC80` |
| Execution skill | `0F7C8D1F2D612FFB7522469C4E3D467985E8872585CA3C18DF9B46BD1A84D36E` |
| `rook_full` adapter | `E7577F0EC8A9B504712BC73290BB8F4C673E9677AEF952CFBFC346F206A62996` |
| Operator | `804BBD9ECBCC294523A4184889CB5EB0E7D34CC625279C258C09BC8346CE7FCD` |

## Independent Outcomes

| Run | Initial outcome | Repair | Final classification | Prime time | IPython cells | Provider token telemetry |
|---|---|---|---|---:|---:|---:|
| V1 | `fail` | Used | `repaired_pass` | 256.25s + 99.45s | 25 + 11 | 428,847 + 384,266 |
| V2 | `pass` | Not used | `initial_pass` | 181.08s | 27 | 499,831 |
| V3 | `fail` | Used | `repaired_pass` | 277.63s + 72.31s | 24 + 5 | 750,038 + 258,226 |

V1's functional point-row graph used `S`, `St`, and `C` slider nicknames. Exact evaluator
feedback admitted one repair, after which Qwen renamed the controls, exercised their output
relationships, restored defaults, and passed all six criteria.

V2 built an accepted seven-component, six-wire graph on its first turn. Its independent
snapshot contained five points beginning `(0,0,0)`, `(1,0,0)`, `(2,0,0)`, structurally
fixed Y/Z, and zero errors or warnings.

V3's first graph was also mechanically functional, but its `S`, `St`, and `Ct` controls did
not satisfy the frozen identities. Exactly one criterion, `adjustable_controls_present`,
failed and carried these three failure IDs:

```text
adjustable_start_present
adjustable_step_present
adjustable_count_present
```

The dependent cardinality/start/step criteria were `unproven`; fixed Y/Z and clean
diagnostics passed. The unchanged deterministic feedback admitted one repair. In the same
Prime session, Qwen replaced and reconnected only the three execution-owned sliders as
`Start`, `Step`, and `Count`. The independent final snapshot contained seven components,
six wires, ten points beginning `(0,0,0)`, `(5,0,0)`, `(10,0,0)`, structurally fixed Y/Z,
and zero errors or warnings. All six criteria passed.

Visible model cells in every run used only `rook_full.search/read/call`. No private adapter,
`list_tools`, `call_tool`, fallback model, operator rerun, cleanup, or third Actor turn was
used. All retained stderr files are empty and all process ledgers end with zero owned
processes.

## Evidence Custody

Common frozen target and empty-state hashes for these same-process disposable canvases:

| Artifact | SHA-256 |
|---|---|
| `target.json` | `1A2945B09D900370AC1CABDC99BAC27A802D7853D904BF3C83FC31067985CD78` |
| `initial-inspection.jsonl` | `F429D14FD6C5D9B77523C9A6BA6129A18E140F390A8D9E82771887023D404B68` |

V1 evidence root:
`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1/operator`

| Artifact | SHA-256 |
|---|---|
| Frozen manifest | `776D36F9006053D2A198D276C76C09A135B319E7985E324DD32E47C68780C2D7` |
| `initial-prime.jsonl` | `A64B83CC71BC394DFCE42A3D3979EEFB81446802A81B6DD8384F70C62CB856EB` |
| `initial-session.jsonl` | `C8C9BB48C9D92E3D9B21AD9A7E84F12020AB1DB53D5749138A5FB8C29E0E6E99` |
| `initial-process-ledger.json` | `DEF0D8023E585E2EBF3C1197AD645759504B5B6C6ED23449E23ECEC74DAD1980` |
| `initial-stderr.txt` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `phase-1-snapshot.jsonl` | `C28235180DF5E0892E7B032599D09A77436CDB3514DFD7F81AB9B22D50B739DF` |
| `evaluation-1.json` | `4554B558ADA48FACEDF3E1B437C6EFF761576E475E81FED545FFD27A14311E48` |
| `repair-feedback.json` | `BF0DE6F8D6AF7646C1D68E0546617349F926A946069C1D6111E6D26F860D6B64` |
| `repair-prime.jsonl` | `C186FD6DDAF3AB51A079BECDC8E9EEB866A528C71FEA3EE88C438A347BB41BC7` |
| `repair-session.jsonl` | `FD4DCB9CDF3BEB42175D32508B430A3341C7050DF080ABA0507B12A2303C939F` |
| `repair-process-ledger.json` | `DE1F93EA2852335D2438BCF95168576077B8A0C5B2E32D9A8623C923C4D94C72` |
| `repair-stderr.txt` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `phase-2-snapshot.jsonl` | `E090236C87D87033DB1C8251BFA6E624256C23B3AAAF362F6593AB26BB3C6536` |
| `evaluation-2.json` | `66D880B8CAA778E5852FE685FC501CDE36324E6D16540DAE854F29EF4B67051A` |

V2 evidence root:
`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v2/operator`

| Artifact | SHA-256 |
|---|---|
| Frozen manifest | `7C5A0BFD068E896AFA8C8336EEB26C98C392CB119FB553A7E5E4743B69CF17E1` |
| `initial-prime.jsonl` | `228A7C65E3644B1750E2356EA381561BF705A3BA3CA660B517789D93A596129D` |
| `initial-session.jsonl` | `A9356C4A624E75ADEAB5BB990C20DF15D0C2B6785FE424FAEFFA41DDE5A68539` |
| `initial-process-ledger.json` | `F75DDD783CA77F9EBB66047720806C171D11263305CA9FF88B3BFF53FB3EB3A4` |
| `initial-stderr.txt` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `phase-1-snapshot.jsonl` | `F38070ABD2C302729F3F926FDFD27B18336D39E3B3265C2BBA7A0E1C0AE921F6` |
| `evaluation-1.json` | `BCADFC55953BBBF193E1B19FCEF2C111201887AF3F005B1E484171F7E1A09BFB` |

V3 evidence root:
`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v3/operator`

| Artifact | SHA-256 |
|---|---|
| Frozen manifest | `69EEF6B6EBAD2B813681553DC7D20AE903DB4D39ED367C98F21EC45C1BF06A0C` |
| `initial-prime.jsonl` | `C96DD16840FFD1344CA49C13E8AC9035A0FBACBADDEFBF5B192C52AFCE0CBA15` |
| `initial-session.jsonl` | `9E518F7EEABBFC79EF6F872468F3BD22FBEA7E6C692D2F9DDBD98F13CAF67965` |
| `initial-process-ledger.json` | `652F4613393C124A720A0F6B49C05527AA2878E41BD766C2FAFFD28B16D1A1D3` |
| `initial-stderr.txt` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `phase-1-snapshot.jsonl` | `126A4F567A9435B0404BA3FFBB6B110F5FFEACB689997E0C04A92C7DD4E92F30` |
| `evaluation-1.json` | `6BAC48350C105F276CA0633E0146D728A2B25728E0AFED86C06B6F38ABDD5A01` |
| `repair-feedback.json` | `B245083AD708E1836BCA1927EF8FDCB21F3259F195422672AAAF0E2BA7E83FDB` |
| `repair-prime.jsonl` | `BF3756AE788B879134621767B03785DC124701AE8F23D84E3AFD772E95A6C7DB` |
| `repair-session.jsonl` | `594099E4A82DFA0EE3D0315DE71C800DBCC289BB3E145C3FF6E55B714628D0D0` |
| `repair-process-ledger.json` | `5BD1612EE40747C12A6D0F23DB9E0236FC91D7B23383505B77A19794F936E539` |
| `repair-stderr.txt` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `phase-2-snapshot.jsonl` | `76EBCAB552A358B71D0CB9D818B228193A5F0014079831812488B0BB6A2E6627` |
| `evaluation-2.json` | `03D4083E59710D8120F97936EF085D2D909531FD6005317EAF2232CDB77BBE72` |

The completed cross-run execution ledger is retained at
`C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repeatability-v1/execution-ledger.json`,
SHA-256 `BC138E7381662F3783B3C15DA8D612BA38E8437CAD142F75B7DF21D2931703C1`.

## Bounded Claim And Non-Claims

Three independent fresh-canvas runs establish that this fixed local Actor and deterministic
acceptance boundary repeatedly reached `pass` within the admitted maximum of one repair.
They also show that deterministic feedback can convert a specific acceptance failure into a
passing result without a model Critic or operator repair.

This does not prove arbitrary Grasshopper competence, general acceptance compilation,
repair of an incorrect computational topology or component choice, a second intent,
cross-model behavior, production readiness, or acceptable efficiency. Provider token counts
and elapsed times are operational observations, not an aggregate score.
