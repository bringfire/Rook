# Prime Upstream T3 Compatibility Smoke V3 Pre-Contact Gate

**Date:** 2026-08-19
**Status:** Frozen for final live-contact review; execution not authorized
**Rhino/Qwen/Ollama contact:** None

## Purpose

V3 is the live-contact transition from the independently approved V2
model-free gate. It changes no task, model, skill, adapter, Rook build, Prime
runtime, budget, evaluator, retry rule, or evidence policy. It authorizes one
T3 Actor execution only after the frozen runner completes all pre-contact
verification, runtime custody, tool-surface custody, and the model-free goal
preflight before target preparation.

V1 and V2 remain unchanged:

```text
V1 protocol SHA-256
512A0843FB8D59DC25F5C8C81B40C296C06DA7DA06778CA86AC82C6C2B711BCD

V2 protocol SHA-256
D8F125BCFDC5E3D88E7845A6602FE46B52894652E3FF9FCB7D648FAF5B743687

V2 evidence manifest SHA-256
9F11C365F80D9325D146818BCA514A6312F530EB6DB036BB2E0754B479D44BD3
```

V1 remains `incomplete`. V2 remains a model-free pass and cannot enter
`run_campaign`.

## Frozen Package

Package commit:

```text
bc134fdd
```

| Artifact | SHA-256 |
|---|---|
| V3 protocol | `41213B8823A90EA4FF95F815A74C815037FBE3CB34D8DC984541394B57D962A5` |
| Campaign runner | `7A81222EA54B0E70BA506EACA4EA805E9132945BC0C83AB1FDDD008ECF292085` |
| Runner tests | `393A1B9EA59C824C3BBFD3DC5DDD71B0D8DEC690E7112F614FD809C2090312FC` |
| Existing adjudication | `211B3345822021B17EEB04B14060A1914B2BEDFDA75FB4B685D7E2FF72C4A814` |
| Prime result commit | `739400844f8f3f280414b0c7b9c65797208815d3` |
| Prime result tree | `4d782187c6898aa8352045dd597bab6a3819029c` |
| Prime runtime bundle | `4C5BC52CDAE882144E851600048711756E4BB28B400DF4A25B206D0F1263A106` |

The V3 protocol differs from V2 only in:

```text
schema
purpose
precontactGate -> contactMode
evidence root v2 -> v3
current runner SHA-256
```

All remaining protocol fields compare exactly equal after excluding those
five transition fields.

## Contact Boundary

The exact V3 contact record is:

```json
{
  "mode": "single_t3_live_contact",
  "evidenceRoot": "C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v3",
  "actorContactAuthorized": true
}
```

The runner refuses an alternate evidence root before creating any directory.
V2 remains separately protected by
`precontact_protocol_not_live_executable`; a direct regression invokes
`run_campaign`, observes that refusal, and proves its proposed evidence root
was not created.

For V3, the existing runner sequence remains:

```text
validate frozen protocol and exact evidence root
-> run configured offline tests
-> verify frozen source evidence
-> verify Rook and Prime runtime custody
-> verify the frozen tool surface
-> run the model-free goal.get()/goal.complete() preflight
-> verify the sealed Python environment
-> prepare the T3 target
-> execute one Actor row
-> run the silent post-run evaluator
-> seal and verify evidence
```

The same goal content-equivalence contract remains frozen:

```text
sealed goal path
C:/Users/bring/.prime/agent/kernel-venv/Lib/site-packages/goal/__init__.py

upstream goal path
D:/prime-agent/.worktrees/rook-upstream-evaluation/packages/coding-agent/skills/goal/src/goal/__init__.py

both SHA-256
9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A
```

Fork-modified `rlm` remains required under the exact Prime worktree. Dirty
tracked or untracked Prime source, goal path or byte drift, runtime bundle or
lineage drift, model/Rook/skill/adapter drift, failed offline verification,
failed goal preflight, or tool-surface drift stops before target preparation.

## Offline Verification

Fresh verification from the package worktree produced:

```text
pytest:      222 passed, 11 existing warnings
compilation: passed
JSON parse:  passed
diff check:  passed
Prime tree:  clean at 739400844f8f3f280414b0c7b9c65797208815d3
V3 root:     absent
```

The tests cover direct V2 live refusal, V3 operational parity, exact V3
contact admission, and rejection of root drift before directory creation.

No Rhino target preparation, MCP call, Prime Actor, Ollama request, Qwen
inference, evaluator execution, retry, or tuning occurred.

## Proposed Command

After explicit independent authorization, execute exactly once:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/qwen38_self_termination_campaign_runner.py run `
  --protocol docs/superpowers/experiments/2026-08-19-prime-upstream-t3-compatibility-smoke-v3.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v3 `
  --document-serial 268435457
```

No retry, accepted-smoke import, tuning, or alternate root is admitted.

## Disposition

V3 is frozen and ready for final live-contact review. It is not an execution
result and does not yet qualify Prime commit `739400844` for the Rook/Qwen
path. The V3 evidence root remains absent.
