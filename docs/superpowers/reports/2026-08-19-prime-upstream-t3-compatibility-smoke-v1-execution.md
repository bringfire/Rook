# Prime Upstream T3 Compatibility Smoke V1 Execution

**Date:** 2026-08-19
**Disposition:** `incomplete — preflight import custody failed`
**Actor/model contact:** None
**T3 row executions:** Zero

## Authorized Transaction

The exact frozen single-row command was invoked once from clean Rook commit
`0493aa6e62a45f176cc470e3ee38bd22cf211822`:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/qwen38_self_termination_campaign_runner.py run `
  --protocol docs/superpowers/experiments/2026-08-19-prime-upstream-t3-compatibility-smoke-v1.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v1 `
  --document-serial 268435457
```

The runner exited `1` after 24.26 seconds during its disposable model-free
goal preflight. It did not prepare the T3 target, launch Prime's Actor, contact
Ollama/Qwen, mutate Grasshopper, run the evaluator, or retry.

## Completed Admission Work

Before the refusal, the transaction successfully retained:

- the exact frozen protocol;
- 213 passing pre-contact tests with 11 existing dependency warnings;
- clean Rook and Prime source custody;
- exact Prime commit, lineage, dependency lock, and 84-file runtime bundle;
- current installed Rook and model custody;
- the 382-tool serialized catalog; and
- a disposable kernel preflight result.

The tool surface and runtime custody matched the frozen package. The failure
occurred only when the runner admitted the preflight's resolved Python import
origins.

## Exact Failure

The preflight returned:

```text
pythonExecutable
C:/Users/bring/.prime/agent/kernel-venv/Scripts/python.exe

rlmFile
D:/prime-agent/.worktrees/rook-upstream-evaluation/prime-agent-runtime/src/rlm/__init__.py

goalFile
C:/Users/bring/.prime/agent/kernel-venv/Lib/site-packages/goal/__init__.py
```

The frozen contact boundary required both `rlm` and `goal` to resolve under:

```text
D:/prime-agent/.worktrees/rook-upstream-evaluation
```

`rlm` passed. `goal` did not, so `validate_preflight_record()` raised
`preflight_invalid` and the runner stopped before model contact.

## Diagnosis

This is an external-kernel skill-origin custody mismatch, not a Qwen or
Grasshopper result.

Prime's upstream kernel bootstrap treats `PRIME_AGENT_KERNEL_PYTHON` as an
already provisioned interpreter. It verifies that requested skill imports are
available, but it does not reinstall those skills from the supplied
`pythonSkills` package paths. The frozen runner prepended the upstream
`prime-agent-runtime/src` directory to `PYTHONPATH`, which made `rlm`
branch-local, but it did not prepend the upstream goal skill's `src`
directory. Python therefore imported the existing sealed-kernel `goal`
package.

The two goal implementations are currently byte-identical:

```text
upstream source goal SHA-256
9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A

sealed-kernel installed goal SHA-256
9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A
```

That equivalence narrows the defect but does not satisfy the approved
branch-local origin requirement. The refusal remains correct.

## Evidence

Durable evidence root:

```text
C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v1
```

The runner sealed and verified all 12 retained files:

```text
manifest SHA-256
16062DB7712A360917775F8E4D4E2572FBB5AAFA55772C3112CCD00479FA2E78

entry count
12/12

mismatches
0
```

No qualification-owned process remains.

## Disposition

Prime commit `739400844f8f3f280414b0c7b9c65797208815d3` is **not qualified** as the
reconciled Rook/Qwen baseline by this transaction. The Actor was never
contacted, so the execution supports no claim about model behavior, task
semantics, completion, or compatibility under live load.

The smallest candidate correction is to bind the upstream goal skill's exact
`src` directory into the sealed kernel's `PYTHONPATH`, alongside the already
bound upstream runtime source, and causally test both preflight and Actor
launch environments. That would create a new frozen contact package and
requires review before any new smoke authorization. This execution is not
rerun or reclassified.
