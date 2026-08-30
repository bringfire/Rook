# RookChat Prime Runtime Topology Gate 7A V5

**Status:** OFFLINE IMPLEMENTATION COMPLETE; GATE 7B V5 NOT AUTHORIZED

## Disposition

Gate 7A V4 is preserved as rejected. Its non-expiring lifetime lease was
coherent for RookChat's explicit in-process topology, but it was selected by a
shared lease switch and therefore also changed Prime's default daemon and
owned-worker recovery behavior. Its Gate 7B wrapper also bound a stale manifest
file hash and would have refused before execution.

V5 closes those two promotion boundaries without changing the intended
RookChat topology:

```text
explicit --rpc-runtime in-process
-> lifetime lease for the complete AgentSessionRuntime
-> graceful token-verified release permits reopen
-> abnormal loss leaves that saved conversation locked and failed
-> user starts a new conversation

default daemon or owned-session-worker
-> existing recoverable lease policy
-> existing dead-worker replacement behavior remains admitted
```

Gate 7B was not launched. The V2, V3, V4, and V5 evidence roots remain absent.

## Lease Policy Split

Prime now has an explicit internal lease-policy selector. The in-process RPC
startup path selects `lifetime`. The daemon supervisor and owned-session-worker
launch paths select `recoverable`, overriding any ambient lifetime value before
their child session starts. Existing callers without an explicit policy retain
the recoverable default.

The lifetime algorithm remains deliberately small:

```text
canonical saved-session file
-> atomic lock-directory creation
-> exact same-session contention refusal
-> owning-token release removes only that generation
```

It has no heartbeat, clock, stale threshold, PID/process-start authority,
process probing, takeover, or cached third-party release callback. An abandoned
lifetime lock is never reclaimed in Slices 3-4.

The recoverable path preserves Prime's prior version-1 owner metadata and
dead-owner reclamation for daemon-owned sessions. A recoverable caller refuses
a lifetime owner rather than reclaiming it. Conversely, lifetime mode refuses
the legacy version-1 `.lock` shape with the canonical
`session_already_active` outcome and never removes it.

## Causal Coverage

Focused model-free Prime tests establish:

- explicit in-process configuration selects the lifetime policy;
- daemon and owned-worker configuration select the recoverable policy;
- a dead version-1 daemon owner is reclaimed by the recoverable policy;
- a lifetime owner refuses same-session contention without stale takeover;
- a legacy version-1 lock is refused in lifetime mode with the exact canonical
  session error and remains present;
- normal lifetime release remains token verified;
- parser, runtime-event, owned-worker, daemon-runtime, agents-view, and
  subagent-host compatibility cases remain green; and
- the complete source and test tree typechecks.

The process-spawning daemon recovery test was intentionally not executed at
this offline gate. V5 proves policy selection and recoverable lease behavior
with model-free tests; it does not claim a new live qualification of Prime's
daemon lifecycle.

Focused Rook tests establish:

- the V5 wrapper uses the recovery worktrees and fresh V5 evidence roots;
- its frozen manifest file hash equals the exact checked-in V5 manifest bytes;
- any commit, harness, bundle, frozen-file, root, or entry-point drift refuses
  before a Gate 7B entry runs;
- a failed lease stage cannot launch the direct vertical; and
- the simplified harness retains its bounded, transition-based evidence shape.

## Documented Recovery Contract

The active Task 7 plan and both runtime-topology amendments now use one
consistent rule:

- explicit in-process abnormal loss leaves that saved conversation failed and
  locked for these slices; a new conversation is required;
- normal in-process close releases the lifetime lock and permits exact-file
  reopen; and
- Prime's default daemon and owned-worker recovery behavior remains unchanged.

There is no claim of automatic same-file RookChat crash recovery, and no new
supervisor, broker lease, storage fence, process monitor, retry, or takeover
protocol was added.

## Custody

```text
Prime commit
b17ca17c1ce685b59e4710713ecd80114325017a

Prime tree
67bd71f3e0a91637db6c3a7d191283a50fc0aad0

Rook Gate 7A V5 implementation commit
8800f48cb3ccd60b35856d8d54bd2f538ff34fae

Rook implementation tree
699791c3eb9ec0ad73fb29d38e0d3dca37997e86

Prime bundle manifest identity
8C68BEF6C0EA3221262365F8F3F0AE147A8A4EB17435C60FB6AE2D2024448771

Prime bundle manifest file SHA-256
9240920623FAD90FC4E19FB892B89B3C56F905B9E08A09E6CF0FE9D83B229AED

Harness SHA-256
958781571FA8BCA953CA5F077E7E38B89AFDD60C4F8B1A341D09C7B59D852ED2

Wrapper SHA-256
5A3E3B210BAE6842650D135885884CBA01FCE8E916F4CD786519C468C579F51D

Slices 3-4 plan SHA-256
C4626D90640396D75E517D35AFB9F2C9A9F6E35B9ABF50273098D4CD79D42E6B

Runtime-topology amendment SHA-256
2C5D8570C2A3B2CF3133DAA3A4078D623F3763CFA195AB6839124AC8DFC8B126

Task 7 recovery amendment SHA-256
E0FB72C6C249D0035D91276699692DBBC84232DBEDB500147787453C773A910A

Prime goal package manifest
D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7

Rook package manifest
2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678

Prime package-lock.json
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

Rook uv.lock
7BF31108A2CA69B65D9DE2936CFD7022A7E4BBE2574C3E512CBBD159B7ADE171
```

The V5 manifest was generated only after Prime commit `b17ca17c1` was clean.
Two clean same-commit bundle runs reproduced the manifest identity above.
Historical V1 evidence, the rejected V2-V4 reports, and both quarantined Task 7
worktrees remain unchanged.

## Offline Verification

Prime:

```text
Focused lease and compatibility tests: 76 passed
Repository-wide source and test TypeScript check: passed
Production TypeScript build and bundle: passed
Clean same-commit bundle reproduction: passed
```

Rook:

```text
Runtime contract, product adapter, harness, and wrapper: 84 passed
Harness and wrapper Python compilation: passed
V5 bundle manifest verification: 86/86 entries
```

No Prime CLI, daemon, kernel, provider, model, Rhino, Grasshopper, MCP,
deployment, Gate 7B transaction, or process cleanup action was launched by this
V5 qualification.

## Review Stop

Gate 7A V5 stops here. Independent review must authenticate the wrapper before
Python executes it and supply the exact final clean Rook commit:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_runtime_topology_gate_7b.py'
$expectedWrapper = '5A3E3B210BAE6842650D135885884CBA01FCE8E916F4CD786519C468C579F51D'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7B V5 wrapper differs from the reviewed artifact.'
}

& $python $wrapper `
    --approved-rook-commit '<INDEPENDENT-REVIEW-SUPPLIED-EXACT-COMMIT>' `
    --approved-harness-sha256 '958781571FA8BCA953CA5F077E7E38B89AFDD60C4F8B1A341D09C7B59D852ED2'

if ($LASTEXITCODE -ne 0) {
    throw "Gate 7B V5 failed with exit code $LASTEXITCODE. Do not retry."
}
```

Gate 7B V5 requires separate independent authorization.
