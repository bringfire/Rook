# Prime/Qwen3.8 Grasshopper Helix Behavioral Qualification Milestone

**Date:** 2026-08-15
**Classification:** Initial pass under the frozen seven-criterion contract
**Rook merge:** `4a2adfa39657118924d57468b77ec0aa1c4b8991`
**Prime merge:** `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`
**Model:** `ollama_chat/qwen3.8:27b`, reasoning `medium`

## Result

One Qwen3.8 Actor turn created an adjustable native Grasshopper helix from a
fresh canvas. The independent receipt-fenced behavioral probe passed every
frozen criterion without an Actor repair:

```text
ordered_geometry_present       pass
radial_periodic_xy              pass
monotonic_z                     pass
principal_controls_causal      pass
resolution_control_causal      pass
controls_restored              pass
clean_diagnostics              pass
```

The resulting graph contained 30 components, 36 wires, one group, 72 point
samples, and zero errors or warnings. It used five controls:

```text
Radius ×10
Height ×10
Turns ×10
Pts/turn
Start °
```

The Actor used authoritative native component discovery and one committed
`gh_edit` authoring mutation. The authored terminal receipt was
`59798db1df2bc3f48c6c036c8e8073fe`. Ten independent one-control-at-a-time
perturbation/restoration cycles completed; the final restoration receipt was
`7744e13e5d2fdadd4292f1658f590047`. No qualification-owned processes remained.

The retained graph implements:

```text
M = max(round(Turns * PtsPerTurn), 4)
t = Series(0, 1, M) / M
theta = 2*pi*Turns*t + Start
X = Radius*cos(theta)
Y = Radius*sin(theta)
Z = Height*t
Construct Point -> Interpolate Curve
```

The independent evaluation recorded radius mean `10.0`, radius spread
`3.552713678800501e-15`, angular span `18.587756533739608`, and Z span
`29.583333333333336`.

## Bounded Endpoint Caveat

The frozen evaluator passed the result correctly according to its seven
reviewed claims, but the definition has a real endpoint shortfall:

```text
M = 72
Series(0, 1, M) -> 0 through 71
t final          -> 71/72, not 1
```

Therefore the final sample does not reach the nominal height or complete turn
endpoint:

```text
observed Z span       29.583333333333336, not 30
observed angular span 18.587756533739608, not 6*pi (18.84955592153876)
```

This caveat does not retroactively change the frozen qualification verdict.
It demonstrates the intended acceptance boundary: deterministic evaluation
proves exactly the reviewed claims and no more.

## Operational Telemetry

- Prime process exit: `0`
- Prime natural termination: `true`
- Actor elapsed time: `438.2832398` seconds
- Prime session usage: `580249` input tokens, `26334` output tokens,
  `606583` total tokens
- Model-authored gateway events: `40`
- Prime IPython calls: `22`
- Evaluator evidence events: `32`
- Repairs: `0`

Provider token usage is retained as operational telemetry and is not directly
comparable across providers or tokenizers.

## Retained Evidence

Evidence root:

```text
C:/Users/bring/AppData/Local/Temp/rook-qwen38-gh-helix-qualification-v2
```

| Artifact | SHA-256 |
|---|---|
| `operator/manifest.json` | `40C3F6FA9189DD337D7982A3B808275DECDDB6269916A8C99242315790EC555C` |
| `operator/target.json` | `F195CA48F7178650A5C469E9988CC299AA3A363DC3146154E7B246FB01D58B94` |
| `operator/initial-prime.jsonl` | `AE6E4A7A99E74EB1F71CF46748F875079DBDE5BEE331A471303C261946379AFD` |
| `operator/initial-source.jsonl` | `7DD8BB922446D00F6675BA3190500A8392449AF0A9FBC75565B8813040FA1F09` |
| `operator/initial-trace.json` | `6D53D33A9AA60D2BE5E92C94A530C976A786228A63220688C53088D3B94B73F1` |
| `operator/initial-closure.json` | `4059C5E6676516A8FE6AA5C4749FD4F06F1D2ACE62D5563E8C6500345B4C82F7` |
| `operator/initial-probe.json` | `571D9F2AB789034E9E6B44A431BF826BFD198F8860C825D1CFD623F2D054C775` |
| `operator/initial-evaluation.json` | `63E114F13C55402164BD47A2710211784C816F3E69756401C0276FBA94ED7738` |
| `operator/initial-process-ledger.json` | `DF31DFDC04CC55E7CFFFC3D6B93FA87AB0517E1A3934F30D2A236FCE34EE886C` |

The interrupted V1 lane remains separate and unchanged:

```text
C:/Users/bring/AppData/Local/Temp/rook-qwen38-gh-helix-qualification-v1-interrupted.json
SHA-256 3AE91643B31106559208FE1AF3913B8B5D8423D5334C97465D04B587EB529D33
```

## Proven Claims

This milestone establishes that the qualified Prime/Rook boundary allowed the
local model to:

- translate an open geometric brief into a viable native algorithm;
- discover and inspect native Grasshopper components;
- compose a substantial arithmetic and geometric graph;
- author efficiently in one terminal mutation;
- expose five causally effective controls;
- survive independent solve-fenced perturbation and exact restoration; and
- pass the frozen behavioral contract without repair.

## Non-Claims

This milestone does not prove:

- exact nominal endpoint fidelity;
- universal Grasshopper competence;
- arbitrary task-contract generation;
- correctness outside the seven frozen criteria;
- architectural, fabrication, or building-code suitability;
- repeatability across models or installations; or
- that model prose is acceptance evidence.

The next production step is the durable Rook–Prime workflow router and closed
acceptance-expression compiler. The retained helix is a conformance specimen,
not a reason to add helix-specific production evaluation code.
