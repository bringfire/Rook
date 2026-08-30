# RookChat Prime Runtime Topology Gate 7A V3

**Status:** READY FOR INDEPENDENT REVIEW; GATE 7B V3 NOT EXECUTED

**Rook implementation:** `32b62a84287d65f94467d278a0fb6230ea087890`

**Prime implementation:** `99320528e69dc86877e7b8a3d3914fec4ed43dec`

## Scope

Gate 7A V2 was refused because it could observe process exit without proving the
cause or continuity of the session lifecycle. V3 corrects that one ownership
chain. It adds no daemon namespace, process monitor, supervisor, broker-owned
lease, retry loop, or product lifecycle protocol.

Gate 7B V3 has not run. No Prime CLI, kernel, provider, model, Rhino,
Grasshopper, MCP, deployment, or Gate 7C contact occurred.

## One Authority

Prime now holds one `proper-lockfile` lock for the full
`AgentSessionRuntime` lifetime:

```text
canonical session file
-> one filesystem lock
-> heartbeat while the runtime owns the session
-> normal release during runtime disposal
-> bounded stale recovery after abrupt owner loss
```

The lock uses a 10,000 ms stale threshold, a 5,000 ms heartbeat, and zero
acquisition retries. Optional owner metadata is advisory, contains no PID or
process-start identity, and cannot establish or reclaim ownership. Existing
process-identity utilities remain available to unrelated daemon ownership code;
`acquireSessionLease()` no longer calls them.

Prime emits this closed startup outcome when an in-process RPC contender loses
the exact lease:

```json
{"type":"rpc_startup_error","code":"session_already_active","sessionPath":"<canonical file>"}
```

Parser, dependency, bootstrap, and configuration failures cannot satisfy the
harness's refusal assertion.

## Causal Gate

The unexecuted V3 harness proves this finite sequence once:

```text
first owner persists session S
-> exact-file contender receives session_already_active(S)
-> first owner closes gracefully with exit 0
-> reopen returns the same session ID and file S
-> reopened owner closes gracefully with exit 0
-> crash-test owner returns the same session ID and file S
-> exact-file contender receives session_already_active(S)
-> retained crash-test handle is killed once
-> one fixed 12-second stale wait
-> one recovery launch returns the same session ID and file S
-> recovered owner closes gracefully with exit 0
```

Terminate or kill fallback remains available for safety cleanup, but it cannot
qualify `first`, `reopened`, `recovered`, or the direct vertical. Every such
owner must settle through stdin/RPC disposal with exit code zero. A contender
must exit nonzero without forced cleanup and emit exactly one matching refusal.

Explicit runtime selection is also closed before side effects. Separate-token
and equals-form `--rpc-runtime` values are parsed as `daemon` or `in-process`;
empty and malformed forms fail before speculative daemon startup.

## Portability

The harness and wrapper use `CREATE_NO_WINDOW` only when Python exposes it.
Their fallback is zero on non-Windows platforms. They contain no continuous
process-table polling, PowerShell identity probe, WMI, Toolhelp traversal,
`taskkill`, or process-name cleanup.

## Custody

```text
Prime commit  99320528e69dc86877e7b8a3d3914fec4ed43dec
Prime tree    f9020f04e3026e1e1316063b5de6533610f20a50

Prime bundle manifest identity
6B15C9F389AEDD08D08CA2E5F38F27E2F21653DAFF5F472C7FDCF78EBCED323A

Prime bundle manifest file SHA-256
24B21152AE64CCDB3DD4AB8330DF19EE9BEBE1587870E97E040739B02B4A19B2

Harness
5B31587B0707AB1FD0A95721DC7A661C2D902E8EEC52B1670312203DDDC5FADD

Wrapper
AF6E85AB64FBDC8C882C60F310E479F83C4D26C940C2354D2BDDC0A0032D668F

Recovery amendment
30871AACC529F6BDA6A1A8677441DC0204E8106C355F779CB2C649F977AF1C5E

Prime goal package
D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7

Rook package
2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678

Prime package-lock.json
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

Rook uv.lock
7BF31108A2CA69B65D9DE2936CFD7022A7E4BBE2574C3E512CBBD159B7ADE171
```

The V2 and V3 evidence roots are absent. The failed V1 evidence and both dirty
review-worktree quarantines remain untouched.

## Offline Verification

Prime:

```text
Session lease, parser, runtime, and subagent-host suites: 154 passed
Early-daemon selector cases: 18 passed, 15 skipped
TypeScript compilation: passed
Local asset copy and bundle: passed
```

Rook:

```text
Runtime contract, product adapter, harness, and wrapper: 83 passed
Changed Python compilation: passed
Prime bundle verification: passed
git diff --check and git show --check: passed
```

No process-spawning Prime integration test was used for Gate 7A V3.

## Review Stop

Gate 7A V3 stops here. Independent review must supply the exact final Rook
commit and authenticate the wrapper before Python executes it:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_runtime_topology_gate_7b.py'
$expectedWrapper = 'AF6E85AB64FBDC8C882C60F310E479F83C4D26C940C2354D2BDDC0A0032D668F'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7B V3 wrapper differs from the reviewed artifact.'
}

& $python $wrapper `
    --approved-rook-commit '<INDEPENDENT-REVIEW-SUPPLIED-EXACT-COMMIT>' `
    --approved-harness-sha256 '5B31587B0707AB1FD0A95721DC7A661C2D902E8EEC52B1670312203DDDC5FADD'

if ($LASTEXITCODE -ne 0) {
    throw "Gate 7B V3 failed with exit code $LASTEXITCODE. Do not retry."
}
```

Gate 7B V3 requires separate authorization.
