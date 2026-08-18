# Qwen3.8 Self-Termination Campaign V2 Execution

Date: 2026-08-18

Classification: **not qualified**

## Scope

This campaign tested Qwen3.8 under Prime's active-goal loop with the versioned
Rook adapter and skill, hard per-row limits, fresh Grasshopper documents, and
silent post-run evaluation. It did not provide semantic evaluator feedback to
the Actor.

The frozen execution order was `T3 -> T1 -> T2 -> T4`. The successful T3 smoke
was retained from its one authentic model run and admitted into the cohort only
after its manifest, protocol, Prime goal context, completion state, resource
usage, semantic result, and process custody were independently reverified. T3
was not rerun.

## Implementation

Runner commits, in order:

```text
59fb86b8  test: add bounded Qwen self-termination campaign runner
34e7115d  fix: align campaign operator with MCP payload projection
4b5d31f3  fix: reuse prepared campaign operator directory
be668638  fix: admit verified campaign smoke evidence
```

Executed command:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/qwen38_self_termination_campaign_runner.py run `
  --protocol docs/superpowers/experiments/2026-08-18-qwen38-self-termination-campaign-v2.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v2-cohort `
  --document-serial 268435457 `
  --accepted-smoke-root C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v2-attempt3
```

The runner exited `0` after completing all four ordered rows. `complete` in the
runner summary means execution closure, not campaign qualification.

## Row Results

| Row | Semantic | Goal | Budget | Custody | Seconds | Provider tokens | Gateway calls |
|---|---|---|---|---|---:|---:|---:|
| T3 repair | pass | complete | pass | pass | 523.172 | 1,764,508 | 39 |
| T1 exact row | pass | complete | pass | pass | 438.141 | 950,269 | 49 |
| T2 open grid | incomplete | budget_limited | fail | fail | 641.063 | 2,007,542 | 41 |
| T4 helix | incomplete | budget_limited | fail | fail | 649.953 | 2,051,780 | 0 |

T3 passed all eight point-row criteria after repairing the seeded definition.
T1 independently passed all eight criteria on a fresh empty canvas and called
`goal.complete()`.

T2's last model-observed state followed its last mutation. It contained 29
components, 34 wires, four sliders (`W=12`, `H=8`, `sX=1.2`, `sY=1.2`), 88
points, and zero errors or warnings. Qwen exhausted the provider-token ceiling
while investigating parameter data representation. It neither completed its
goal nor established the requested behavioral evidence, so no semantic pass is
claimed.

T4 made no Rook adapter calls. Its normal IPython kernel repeatedly exited
before resolving ports because `ntsecuritycon` was unavailable during Jupyter
connection-file creation. Prime continued the active goal until the provider
ceiling stopped the row. This is an infrastructure failure, not a helix
performance verdict.

## Enforcement

The runner mechanically enforced:

- Prime goal token budget: 2,000,000;
- outer provider-reported token ceiling: 2,000,000;
- wall-clock ceiling: 1,800 seconds;
- gateway-call ceiling: 150 calls before transport.

T2 and T4 were stopped by the provider ceiling. Both retained stdout EOF and
zero lingering owned processes. Their custody status is still `fail` because
the enforced termination exited nonzero and did not produce normal goal
closure.

## Qualification Failure

The shared external kernel was not actually sealed against Actor mutation.
The runner pinned its Python executable but did not preflight `rook_full` in a
normal Prime kernel or hash the complete kernel and installed Rook Python
support environments before and after each row.

The retained traces prove configuration-changing behavior:

- T1 ran `pywin32_postinstall.py -install` in the installed Rook venv.
- T2 attempted `uv pip install` into the shared Prime kernel.
- T2 used `curl` to download a pywin32 wheel.
- T2 copied pywin32 binaries into the shared Prime kernel.
- T4 subsequently failed during kernel startup on missing `ntsecuritycon`.

Therefore the rows did not execute against one unchanged Python environment.
The campaign cannot qualify cross-row self-termination behavior, even though
T3 and T1 remain authentic individual passes.

## Evidence

Durable cohort root:

```text
C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v2-cohort
```

Independent manifest verification:

```text
entries: 84
mismatches: 0
SHA-256: C13EA609167F47A060C59FD29E8060C92D74735D413833D2C253EC8A4D04E32E
live qualification-owned processes: 0
```

Retained T3 root and manifest:

```text
C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v2-attempt3
3AB9D5B54A4DB6BC4CFD78A381349B4F10740FA0C4906FA8841F1FEA6064E5FE
```

Pre-execution adjacent verification passed `132` tests with `11` existing
DSPy warnings. The separate legacy point-row CLI suite retained four existing
CRLF/canonical-byte failures and was not used by this runner.

## Next Bounded Correction

The next cohort must:

1. supply the required Windows pywin32 import and DLL paths before Prime starts;
2. preflight a normal Prime kernel that imports `goal`, `rlm`, and `rook_full`;
3. freeze and verify recursive manifests for the shared Prime kernel and
   installed Rook Python environment before and after every row;
4. classify any environment drift as a custody failure that stops the cohort;
5. instruct the Actor to report adapter-import failure immediately without
   installing, downloading, copying, or modifying runtime dependencies.

No terminalization protocol, semantic supervisor, or new acceptance vocabulary
is justified by this result.
