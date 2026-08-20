# Prime Upstream T3 Compatibility Smoke V2 Pre-Contact Gate

**Date:** 2026-08-19
**Status:** Model-free preflight passed; live smoke not authorized
**Rhino/Qwen/Ollama contact:** None

## Purpose

V2 corrects only the custody rule that stopped V1. Fork-modified `rlm` must
still resolve from the exact Prime worktree. The unchanged `goal` skill is
admitted from Prime's normal sealed external-kernel installation only when its
exact path and bytes match the exact frozen upstream source.

V1 remains unchanged and honestly classified `incomplete`:

```text
V1 protocol SHA-256
512A0843FB8D59DC25F5C8C81B40C296C06DA7DA06778CA86AC82C6C2B711BCD

V1 evidence manifest SHA-256
16062DB7712A360917775F8E4D4E2572FBB5AAFA55772C3112CCD00479FA2E78
```

No V1 protocol, evidence, report, or classification was edited or reused.

## Frozen V2 Package

The model-free gate ran from clean package commit:

```text
eb9ced1ee466b7c4266a5b904db863ad0c46819b
```

Frozen inputs:

| Artifact | SHA-256 |
|---|---|
| V2 protocol | `D8F125BCFDC5E3D88E7845A6602FE46B52894652E3FF9FCB7D648FAF5B743687` |
| Campaign runner | `F294B1BFA8B3E7F4A1F688B4B352A7B3F9FD8251CC72367919FB4C1C50D9E770` |
| Existing adjudication | `211B3345822021B17EEB04B14060A1914B2BEDFDA75FB4B685D7E2FF72C4A814` |
| Upstream Prime result commit | `739400844f8f3f280414b0c7b9c65797208815d3` |
| Upstream Prime result tree | `4d782187c6898aa8352045dd597bab6a3819029c` |
| Prime runtime bundle | `4C5BC52CDAE882144E851600048711756E4BB28B400DF4A25B206D0F1263A106` |

The task, Qwen model, medium thinking level, Prime/Rook/adapter versions,
historical T3 skill and checkpoint, tool surface, budgets, no-retry rule, and
silent evaluator remain unchanged from the frozen V1 package.

## Content-Equivalence Contract

The exact admitted files are:

```text
sealed external-kernel goal
C:/Users/bring/.prime/agent/kernel-venv/Lib/site-packages/goal/__init__.py

upstream goal source
D:/prime-agent/.worktrees/rook-upstream-evaluation/packages/coding-agent/skills/goal/src/goal/__init__.py
```

Runtime custody established:

```text
sealed goal bytes       2,040
upstream goal bytes     2,040
sealed goal SHA-256     9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A
upstream goal SHA-256   9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A
equivalent              true
```

The disposable preflight independently observed:

```text
goalFile
C:/Users/bring/.prime/agent/kernel-venv/Lib/site-packages/goal/__init__.py

rlmFile
D:/prime-agent/.worktrees/rook-upstream-evaluation/prime-agent-runtime/src/rlm/__init__.py

goal.get()
active, 2,000,000-token budget

goal.complete()
complete
```

Any alternate goal path, missing file, hash change, one-byte divergence,
non-branch-local `rlm`, dirty Prime worktree, or existing lineage/bundle/import
drift remains fail-closed.

## Model-Free Execution

The exact command was:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/qwen38_self_termination_campaign_runner.py preflight `
  --protocol docs/superpowers/experiments/2026-08-19-prime-upstream-t3-compatibility-smoke-v2.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v2
```

Result:

```text
status          pass
modelContact    false
targetContact   false
goalStatus      complete
tests           219 passed, 11 existing warnings
owned processes 0
```

No tool-surface query, Rhino target preparation, MCP mutation, Prime Actor,
Ollama request, Qwen inference, evaluator, retry, or tuning occurred.

## Evidence

Durable evidence root:

```text
C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v2
```

Independent verification reproduced:

```text
entry count          10/10
mismatches           0
manifest SHA-256     9F11C365F80D9325D146818BCA514A6312F530EB6DB036BB2E0754B479D44BD3
```

Runtime custody retains both goal paths, both hashes and byte counts, the
equivalence result, branch-local `rlm`, Prime lineage, clean worktrees, runtime
bundle, current Rook, model content, and every frozen historical input.

## Disposition

The narrow content-equivalence custody rule is qualified offline for this
exact sealed external kernel and Prime worktree. It preserves Prime's
supported external-kernel behavior instead of injecting a checkout path for
an unchanged skill.

This does not qualify Prime commit `739400844` under live Rook/Qwen execution.
The V2 protocol is explicitly preflight-only and cannot launch the Actor path.
Any live smoke package or authorization remains a subsequent reviewed step.
