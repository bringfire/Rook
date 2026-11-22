# RookChat Prime Gate 7C Broker V2 Pre-Contact Report

**Status:** OFFLINE PACKAGE COMPLETE; GATE 7C V2 EXECUTION NOT AUTHORIZED

## Scope

This package freezes one fresh Gate 7C V2 transaction after the accepted
deadline-inversion correction at Rook commit
`6fdf27f13746799da750af2620b31449db764d65`.

It does not execute Gate 7C V2, launch Prime, prepare a kernel, contact a
provider, or contact Rhino, Grasshopper, or Rook. It does not alter Prime,
cleanup, RPC topology, process ownership, the Gate 7C harness, or V1 evidence.

## Retained V1 Failure

Gate 7C V1 remains preserved at:

`C:/RookEvidence/2026-08-30-rookchat-prime-gate-7c-broker-v1`

- `admission.json` SHA-256:
  `0D7BCAE87242A366C6EBE07FD5A91B8696A52ABD1F6A0838FAAD2E99FAAAB43A`
- `result.json` SHA-256:
  `D891E82E19B86F8C3709ADF57860F72848BB260D9A5A32AD351B6F810AA44E09`
- Classification: `failed`
- Failure: `Prime control command timed out: prepare_ipython_runtime`

No V1 input, evidence, runtime directory, or report was reused or rewritten.

## V2 Frozen Transaction

V2 uses a new canonical schema-2 configuration with:

- evidence root:
  `C:/RookEvidence/2026-08-30-rookchat-prime-gate-7c-broker-v2`;
- kernel root:
  `C:/RookEvidence/2026-08-30-rookchat-prime-gate-7c-broker-v2/runtime/kernels`;
- conversation ID: `conv_fedcba9876543210fedcba9876543210`;
- runtime preparation deadline: `150.0` seconds; and
- outer wrapper deadline: absent.

The V2 evidence root and kernel root are both absent at this gate. The wrapper
requires the kernel root to be exactly the V2 path above and refuses before
evidence creation if it already exists. A warm V1 environment cannot satisfy
that check or enter the V2 invocation.

The wrapper verifies the branch-local `prime_backend` import before evidence
creation and requires its
`RUNTIME_PREPARATION_TIMEOUT_SECONDS` value to equal the frozen `150.0`-second
contract. The admission record retains both the configured deadline and the
value observed from the reviewed import.

The wrapper itself applies no outer execution deadline. The future PowerShell
command also contains no timeout. Prime retains its internal 120-second
preparation bound, while Rook provides 30 seconds of bounded response grace.
Ordinary Rook control commands remain at 10 seconds.

## Unchanged Custody

V2 retains the accepted Gate 7C custody chain:

- exact worktree Python interpreter under `-I`;
- refusal of `PYTHONPATH` and `PYTHONHOME`;
- branch-local `rook`, `prime_backend`, and `prime_process` imports;
- frozen ten-key child environment;
- exact Prime commit and complete bundle manifest;
- immutable staged `rook-full` and goal skill identities;
- explicit in-process RPC and one directly owned Prime process;
- readonly profile and synthetic locked target; and
- absorbing success or failure evidence with no retry.

## Offline Qualification

The model-free tests prove:

- schema-2 deadline fields are closed;
- a non-null outer wrapper deadline refuses;
- an imported preparation deadline other than 150 seconds refuses;
- an existing V2 kernel root refuses before invocation;
- the exact constructed harness invocation remains frozen;
- V2 success and failure records retain deadline and kernel-root custody;
- host interpreter, imports, and admitted environment remain fixed; and
- the real production configuration loads under the exact isolated interpreter
  while both V2 roots are absent.

Results:

- V2 wrapper and harness tests: **21 passed**.
- Complete focused Gate 7C suite: **62 passed**.
- Python compilation: passed.
- Prime worktree: unchanged and clean.
- V1 evidence hashes: unchanged.
- V2 evidence root: absent.
- V2 kernel root: absent.

## Frozen Files

- Gate 7C V2 wrapper:
  `77C416EEF06BEE91C08528B9016E7449BE6B00716267173990ABB6E7036453B0`
- Unchanged Gate 7C harness:
  `2A74120496C0B65AE4A9FBDDFAD056D65F7976B2E597500ADF8AF7F8F7E920EA`
- Gate 7C V2 configuration:
  `98C910A238D21011A6AA76E88E91D73D4E52D2723625822E9B239235A9D9AC11`
- Corrected product broker:
  `4FD7A8A11FE50F9A63902E0499239CBEBCC07F66278D68B099694879E49EA9A6`
- Prime commit:
  `46dbf2749d64446820fbf31e52d8766e5ee87be9`

## Review Gate

Independent review must supply the final clean Rook package commit and
externally authenticate the V2 wrapper hash. Gate 7C V2 may then be invoked
once only. Any refusal or failed result is absorbing; no retry, timeout change,
warm-root reuse, cleanup expansion, or alternate invocation is admitted.

The only admissible future command shape is:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = `
    'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = `
    'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_gate_7c.py'
$expectedWrapper = '77C416EEF06BEE91C08528B9016E7449BE6B00716267173990ABB6E7036453B0'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7C V2 wrapper differs from the reviewed artifact.'
}

if ((Test-Path Env:PYTHONPATH) -or (Test-Path Env:PYTHONHOME)) {
    throw 'Gate 7C V2 does not admit PYTHONPATH or PYTHONHOME.'
}

& $python -I $wrapper --approved-rook-commit '<independently-reviewed-rook-commit>'
if ($LASTEXITCODE -ne 0) {
    throw "Gate 7C V2 failed with exit code $LASTEXITCODE. Do not retry."
}
```

No Gate 7C V2 command was run while preparing this report.
