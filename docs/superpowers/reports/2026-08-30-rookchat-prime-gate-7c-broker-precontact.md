# RookChat Prime Gate 7C Broker Pre-Contact Report

**Status:** OFFLINE IMPLEMENTATION COMPLETE; GATE 7C EXECUTION NOT AUTHORIZED

## Scope

This package implements only the work authorized after the accepted Gate 7B
run:

- direct in-process Prime launch custody in the product process owner;
- v2 first-use and reopen preparation in the existing broker;
- model-free failure injection;
- one single-session Gate 7C broker harness; and
- one absorbing admission wrapper with a frozen configuration artifact.

It does not wire or contact the panel, start Prime, prepare a real kernel, send
a prompt, contact a provider, or contact Rhino, Grasshopper, or Rook. Gate 7C,
concurrency, and live product contact remain unauthorized.

## Retained Baselines

- Rook parent before this implementation: `30e5a0a7`
- Prime: `46dbf2749d64446820fbf31e52d8766e5ee87be9`
- Prime worktree: clean and unchanged
- Gate 7B: accepted and not rerun
- Gate 7C evidence root:
  `C:/RookEvidence/2026-08-30-rookchat-prime-gate-7c-broker-v1`
- Gate 7C evidence root at this gate: absent

## Implemented Boundary

`PrimeRuntimeProcessFactory` is the shared production seam consumed by the
unexecuted harness. Immediately before constructing a child it rechecks:

- exact Node and `uv.exe` hashes;
- `uv.exe` directory precedence in the child `PATH`;
- the complete Prime `dist/bundle` and `dist/skills` manifest;
- the runtime-contract fingerprint and admitted package bytes;
- the exact goal and Rook skill paths; and
- the immutable profile, PID, process-start ticks, Rhino document serial, and
  Grasshopper document ID projected into the sanitized child environment.

The process owner now uses only its direct child handle. Normal retirement is
stdin/EOF plus a bounded zero-exit wait. Handle-local terminate and kill are
safety cleanup only and are reported as non-graceful. A stalled stdin close,
nonzero natural exit, or unsettled kill cannot qualify. There is no Toolhelp,
PowerShell identity probe, `taskkill`, process-tree enumeration, name-based
cleanup, retry, or replacement process.

The v2 broker sequence is:

```text
launch and get_state
-> write pending v2 record
-> set chat-local recursion depth 0
-> read back exact {maxDepth: 0, source: chat}
-> await fixed IPython preparation
-> verify interpreter and import origins
-> write prepared v2 record
-> prompt admission becomes possible
```

Reopen verifies the recorded contract, prepared environment, interpreter,
session ID, and canonical session file before admitting the resident. It reads
recursion state without repairing it. A failed transition retires the exact
resident, records `runtime_contract_unavailable` when a pending record exists,
creates no replacement process, and performs no replay.

## Admission Custody

The admission wrapper accepts only the independently reviewed Rook commit.
Every other Gate 7C input is frozen in one canonical JSON artifact and bound by
SHA-256. The wrapper constructs the complete harness argument list from that
artifact; callers cannot substitute the Prime bundle or provenance, Node or
`uv.exe`, product package, runtime roots, profile, target, model, conversation,
result path, or evidence root.

The frozen broker-only transaction uses the accepted Prime commit and bundle,
the immutable `rook-full` package, `openai-codex/gpt-5.6-sol` at `xhigh`, the
`readonly` profile, one synthetic four-part target, one fixed conversation ID,
and isolated runtime roots beneath the Gate 7C evidence root. The selector is
retained as runtime custody only: the harness sends no prompt and runs Prime
with `--offline`.

Exact `.gitattributes` rules preserve the reviewed wrapper and harness as LF
text and the configuration as byte-preserved data, so clean checkouts do not
change these three authority hashes through line-ending conversion.

The wrapper registers the reviewed harness module in `sys.modules` before
executing it. A causal test loads the actual harness through this default path,
without replacing the harness invoker.

After all pre-admission hashes and clean commits pass, the wrapper creates the
fresh evidence root and atomically writes `admission.json`. The compact record
retains:

- wrapper, harness, and configuration SHA-256 values;
- approved Rook and Prime commits;
- Python executable, wrapper path, harness path, and exact constructed harness
  arguments;
- start and end timestamps;
- logical wrapper and harness exit outcomes;
- result path and SHA-256 when present; and
- one terminal `passed` or `failed` outcome with the failure text when present.

Any admitted failure rewrites that record to `failed` and is absorbing. This is
one Gate 7C admission record, not a general execution journal.

## Model-Free Coverage

The causal tests cover:

- exact launch flags and authority environment;
- bounded graceful, terminate, kill, stdin-timeout, nonzero-exit, and uncertain
  cleanup outcomes;
- pending-before-preparation ordering;
- recursion set/readback drift;
- preparation timeout and explicit failure;
- partial environment;
- wrong interpreter, Rook import, goal import, and callable shape;
- process loss;
- missing reopen environment;
- reopen without depth repair;
- launch-time Node drift after initial admission;
- one-process/no-prompt Gate 7C success;
- one-process absorbing Gate 7C failure; and
- real default harness loading;
- frozen configuration and exact constructed invocation;
- wrapper/configuration/harness hashes, clean commits, fresh root, and
  no-retry admission; and
- retained success and failure admission outcomes.

## Offline Results

- Corrected wrapper and harness gate: **11 passed**.
- Complete focused Gate 7C gate: **50 passed**.
- Retained prior bounded broker/registry/runtime/server gate excluding the ambient
  `TestKnowledgeGraphRoutes` class: **271 passed, 13 deselected**, with 18
  existing warnings.
- Python compilation: passed.
- `git diff --check`: passed.
- Changed-file line-length scan at 99 characters: passed.
- `ruff` was not available in the frozen worktree venv; no dependency was
  installed to add it.

For transparency, running the entire selected server file also produced **278
passed and 2 failures** in `TestKnowledgeGraphRoutes`. Those tests read ambient
local knowledge data: one expected `UnifiedStore` but observed
`UnifiedStore+CommandKnowledgeStore`; the other attempted to JSON-serialize an
ambient `ModeKnowledge` object. None of the files changed in this package owns
those routes or stores. The bounded Task 7 gate therefore excludes that
unrelated ambient-data class rather than changing it.

## Frozen Files

- Gate 7C harness:
  `51CB1C8DECE9348B34649CBC375CB039330686BCD28B3620861EE34A182C78F7`
- Gate 7C wrapper:
  `3A6959CA7B5DF009D3763F6BA2BABB1E8B2C3CEFD60E22756FC51F1BD6CAA008`
- Gate 7C frozen configuration:
  `8F5D0F9E0CBDCDD0107566FFF31A586AA58D42BC71FED312356E5B8B11BB373B`
- Product process owner:
  `83D8821240A37195B3C2D61E6CD81CC126ED792CC4150106E5B9666E4D8497C2`
- Product broker:
  `C765114A742049140D7D462985FEB8631C2683A5A72F670F751533B93606B844`

The accepted external runtime inputs remain:

- Node:
  `F13AC3CA23248DC389507E8FE38C34489AB7EDB3E6D6700EB6DA6A0B7E128EAF`
- `uv.exe`:
  `68A22CBAB1674647BCDA32120B214E6480F875414E3333F49F87AE99B4B0E0FA`
- Prime bundle:
  `C5A4861EFFAED21EDA75C66C218F68057B6BAF116E75E620666CF1326CE69CB7`
- Goal skill manifest:
  `D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7`
- Rook package manifest:
  `2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678`

## Review Gate

Independent review must supply the final clean Rook commit and externally
authenticate the wrapper hash before execution. The future command must use
the single fresh evidence root above and the exact frozen inputs. It may invoke
the wrapper once only. The wrapper calls the reviewed harness in-process, and
any refusal or failed result is absorbing.

The only admissible future command shape is:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = `
    'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = `
    'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_gate_7c.py'
$expectedWrapper = '3A6959CA7B5DF009D3763F6BA2BABB1E8B2C3CEFD60E22756FC51F1BD6CAA008'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7C wrapper differs from the reviewed artifact.'
}

& $python $wrapper --approved-rook-commit '<independently-reviewed-rook-commit>'
if ($LASTEXITCODE -ne 0) {
    throw "Gate 7C failed with exit code $LASTEXITCODE. Do not retry."
}
```

No Gate 7C command was run while preparing this report.
