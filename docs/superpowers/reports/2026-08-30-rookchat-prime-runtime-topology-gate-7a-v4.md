# RookChat Prime Runtime Topology Gate 7A V4

**Status:** OFFLINE IMPLEMENTATION COMPLETE; GATE 7B V4 NOT AUTHORIZED

## Disposition

Gate 7A V3 is preserved as rejected. Its time-based `proper-lockfile` takeover
could let a delayed former owner invoke a cached release callback after a
successor acquired the same session, removing the successor's lock without a
fencing primitive.

V4 removes takeover rather than attempting to patch that race:

```text
atomic lifetime-lock directory creation
-> exact same-session contender refusal
-> normal owning-token release permits reopen
-> unclean owner loss leaves the saved session locked and failed
-> user starts a new conversation
```

There is no heartbeat, stale threshold, PID/process-start liveness decision,
lock polling, automatic recovery, or former-owner release callback in the
RookChat session lease. Process identity helpers retained elsewhere in Prime
remain unrelated diagnostics for existing daemon behavior and do not govern
this lease.

## Prime Correction

`acquireSessionLease()` canonicalizes the saved-session file, derives one
session-keyed path, and atomically creates its lock directory. Existing
directories return the exact structured `session_already_active` refusal for
the canonical session file. Owner metadata lives inside that directory and
contains a random token, optional diagnostic session ID, canonical file,
version, and creation time. It contains no PID or process-start identity.

Normal `SessionLease.release()` verifies the token, removes `owner.json`, then
removes the now-empty lock directory. Any missing, malformed, or mismatched
metadata fails closed. A failed acquisition cleans up only its own unpublished
directory when possible; cleanup failure leaves it locked.

The previously stale `agents-view-missing-cwd` test now constructs the complete
current lease shape. The repository-wide `tsgo --noEmit` check includes the
test tree, so another constructor drift is a compile failure rather than a
transpile-only false pass.

## Gate 7B V4 Shape

The unexecuted model-free lease sequence now has only three direct children:

```text
first owner persists canonical session S
-> exact --resume S contender receives session_already_active(S)
-> first owner closes gracefully with exit 0
-> exact --resume S returns the original session ID and file
-> reopened owner closes gracefully with exit 0
```

The separate direct vertical remains admitted only after that lease result
passes and custody is reverified. The wrapper remains absorbing: a failed or
raised lease result cannot launch the direct vertical. V4 does not manufacture
an owner crash, wait on a clock, recover a stale lock, retry, poll the Windows
process table, or invoke Gate 7C.

## Causal Coverage

Offline tests establish:

- a live owner refuses a second owner with the typed canonical-session error;
- an abandoned lock refuses regardless of age;
- manually aging a live owner's directory does not permit supersession;
- normal release permits a replacement owner;
- symlink aliases bind to the same canonical session;
- owner metadata contains no process authority and release removes the lock;
- the exact RPC refusal remains machine-readable and session-bound;
- the complete constructor test surface typechecks;
- the Gate 7B harness uses only first/refused/reopened generations;
- every qualifying owner requires graceful zero exit; and
- wrapper custody, fresh-root refusal, and lease-before-direct ordering remain
  unchanged.

## Custody

```text
Prime commit
51e047fc2cf1d45b93a0e75eed961a7d958cda02

Prime tree
5b50a8826284ec48345c1f366a930321fa69332b

Rook Gate 7A V4 implementation commit
0e052ca69117b7bd851032e90cf726a300017711

Prime bundle manifest identity
8685FC1DB52E834DA19841D5F7BB539EA2BFECD0D574F242374D8A07D4022DFA

Prime bundle manifest file SHA-256
0D5FE79029C89A6EC591146766DA253A0FD6582B0E1380BEB377546502F6FE7D

Harness SHA-256
6607C6EDD2E5C7337C6CCD2EB614802BC2CE118B228120C45603E77E9CDD9DAF

Wrapper SHA-256
3CC910F95B9C4073B635E81B8DC73376C66A6A9EA9653B5C163CFA437BC52159

Recovery amendment SHA-256
E50B015B5DBA224BCFB35508C1FF230E10C4E04417A25D92FED4002952861E56

Prime goal package manifest
D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7

Rook package manifest
2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678

Prime package-lock.json
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

Rook uv.lock
7BF31108A2CA69B65D9DE2936CFD7022A7E4BBE2574C3E512CBBD159B7ADE171
```

The V2, V3, and V4 Gate 7B evidence roots are absent. Historical V1 evidence,
the rejected V3 report, and both quarantine worktrees remain unchanged.

## Offline Verification

Prime:

```text
Lease, parser, runtime, agents-view, subagent-host, resume, and bootstrap unit
tests: 185 passed
Early-daemon selector-only cases: 20 passed, 125 skipped
Repository-wide source and test TypeScript check: passed
Production TypeScript build, asset copy, and bundle: passed
```

Rook:

```text
Runtime contract, product adapter, harness, and wrapper: 83 passed
```

One exploratory command also included the complete Windows daemon-launch test
file. Eight socket-listener cases returned `listen EACCES` while the other 210
tests passed. That command is not used as Gate 7A evidence; the reviewed
selector-only subset above passed independently. No Prime CLI, daemon, kernel,
provider, model, Rhino, Grasshopper, MCP, deployment, or Gate 7B transaction
was launched.

## Review Stop

Gate 7A V4 stops here. Independent review must authenticate the wrapper before
Python executes it and supply the exact final Rook commit:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_runtime_topology_gate_7b.py'
$expectedWrapper = '3CC910F95B9C4073B635E81B8DC73376C66A6A9EA9653B5C163CFA437BC52159'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7B V4 wrapper differs from the reviewed artifact.'
}

& $python $wrapper `
    --approved-rook-commit '<INDEPENDENT-REVIEW-SUPPLIED-EXACT-COMMIT>' `
    --approved-harness-sha256 '6607C6EDD2E5C7337C6CCD2EB614802BC2CE118B228120C45603E77E9CDD9DAF'

if ($LASTEXITCODE -ne 0) {
    throw "Gate 7B V4 failed with exit code $LASTEXITCODE. Do not retry."
}
```

Gate 7B V4 requires separate independent authorization.
