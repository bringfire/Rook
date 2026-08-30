# RookChat Prime Runtime Topology Gate 7A V2

**Status:** READY FOR INDEPENDENT REVIEW; GATE 7B V2 NOT EXECUTED

**Rook recovery implementation:** `0bda784df27bcf59134d5ed490f57aeede34e505`

**Prime implementation:** `8712f6dddfc1251d2c308380229555c87befda8e`

## Scope

This recovery replaces only the interrupted Task 7 runtime-topology
qualification. Tasks 0-6 remain preserved. It introduces no daemon namespace,
supervisor, broker-owned lease, session journal, or OS process-ownership
framework.

Gate 7B V2 has not run. No Prime CLI, IPython kernel, provider inference,
Rhino, Grasshopper, MCP, deployment, or Gate 7C contact occurred during the
qualified correction and final offline gates.

## Incident Recovery

The dirty interrupted worktrees remain untouched quarantines:

```text
Rook
  HEAD 92f1c2f0dda68a52730b10c1f7f45b0dd6bee189
  M mcp_server/tests/test_rookchat_prime_runtime_topology_harness.py

Prime
  HEAD 6f76ebd9d5c2f2a690c104313dd4cc92c58f3040
  M packages/coding-agent/src/cli/daemon-launch.ts
  M packages/coding-agent/test/daemon-launch.test.ts
```

The failed V1 evidence remains unchanged at:

```text
C:/RookEvidence/2026-08-29-rookchat-prime-runtime-topology-gate-7b-lease
```

Its retained result SHA-256 is
`BD66471C0E80F18512605D4B73B54995D7BAF7C53FF2BF0B0C8D383260AFF589`.
The complete 911-file, 9,420,898-byte V1 tree has canonical diagnostic digest
`37946022E46D5C623B70F868E4BE48020F9334AEC978A5B2AABB3D191F27D01F`.
That digest hashes sorted relative path, size, and file SHA-256 records; it is
diagnostic evidence, not a replacement manifest.

One leaked V1 daemon tree was identified before recovery work:

```text
root  PID 3448, parent 22752, start ticks 639236874964793270
      quarantined Prime cli --mode daemon --daemon-socket \\.\pipe\prime-agent-daemon
child PID 47100, parent 3448, start ticks 639236874967743819
      same quarantined Prime cli --version
```

The exact root identity was revalidated and terminated once through its
retained process handle with descendant cleanup. Both PIDs were then absent.
No process-name cleanup, console host, shared Prime process, or shared Rook
process was touched.

## Root Cause And Correction

Prime's explicit `--rpc-runtime` selection was parsed after an earlier cold
startup optimization could launch the shared daemon. Prime now excludes every
explicit `--rpc-runtime` form from speculative startup. Its normal parser
still validates and selects `daemon` or `in-process`; default RPC behavior is
unchanged.

The product topology remains:

```text
RookChat conversation
-> one directly owned Prime CLI process
-> in-process AgentConnection
-> Prime-owned saved session and lease
-> Prime-owned IPython kernel and child lifecycle
-> stdio RPC back to RookChat
```

The V2 harness is smaller than V1:

- `ProcessMonitor`, Toolhelp polling, PID ancestry, start-tick ownership,
  PowerShell probes, WMI, and `taskkill` are gone.
- The direct `Popen` handle, RPC/EOF, and bounded wait/terminate/kill govern
  only the directly owned Prime process.
- Prime owns its session lease, kernel, children, persistence, and graceful
  shutdown.
- The isolated agent root refuses daemon worker, restart/configuration, and
  daemon-log artifacts.
- A future `sessionFile` is admitted only after model-free
  `set_rlm_max_depth(0, global:false)` makes Prime persist it. The harness never
  creates or touches that file.

## Gate 7B V2

The unexecuted V2 lease entry performs one finite sequence:

1. Start one explicit in-process RPC child offline.
2. Read state, flush through Prime, and admit the canonical persisted session.
3. Prove a simultaneous exact-file resume is refused by Prime's lease.
4. Close the owner and prove exact-file reopen succeeds.
5. Terminate one owner deliberately and prove stale-lease recovery.
6. Close the final owner.
7. Require every direct child to be settled and the isolated agent root to
   contain no daemon artifacts.

The direct entry then verifies chat-local recursion depth and the prepared
kernel interpreter/import origins. The admission wrapper remains absorbing:
a failed lease result prevents the direct entry.

The fresh V2 evidence roots are absent:

```text
C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v2-lease
C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v2-direct
```

## Dependency And Build Custody

Dependency restoration used only the recovery worktrees and exact lockfiles:

```text
Prime package-lock.json
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

Rook mcp_server/uv.lock
7BF31108A2CA69B65D9DE2936CFD7022A7E4BBE2574C3E512CBBD159B7ADE171
```

One setup mistake occurred and is not part of the qualification claim. An
attempt to build the Prime AI workspace package invoked its model-generation
script, which fetched public model catalogs. It made no inference request and
launched no Prime runtime. Its generated tracked source change was discarded,
leaving only the intended Prime test and production files. All subsequent
build steps invoked local TypeScript compilation, asset copying, and bundling
directly without model-catalog generation.

The final Prime source and bundle identities are:

```text
Prime commit  8712f6dddfc1251d2c308380229555c87befda8e
Prime tree    06fc392ab3d684f74ed074098cef14048bd5f27f

Bundle manifest identity
9BEB93172D58D333BD5A13F5A5CFF07C3F44DB5F2657F29B41F513E87DDEC50C

Bundle manifest file SHA-256
E7A82A0C71F1BCE3FFE33C74F03B6E01DC3C4C9632256513D3E83C23956D8294
```

The bundle verifier reproduced the manifest identity against the actual
launched artifact path. The unchanged skill identities remain:

```text
Prime goal package D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7
Rook package       2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678
```

The preflighted executables remain:

```text
Node F13AC3CA23248DC389507E8FE38C34489AB7EDB3E6D6700EB6DA6A0B7E128EAF
uv   68A22CBAB1674647BCDA32120B214E6480F875414E3333F49F87AE99B4B0E0FA
```

## Offline Verification

Prime focused gates:

```text
Early-daemon selector: 15 passed, 15 skipped
Parser, routing, and IPython provisioner: 177 passed
Injected Windows identity and in-process lease controls: 3 passed, 6 skipped
Local TypeScript compile, asset copy, and bundle: passed
```

One broader exploratory Prime run was not used as a passing gate. It produced
204 passes and 12 existing Windows failures: fake Unix-socket paths reported
`EACCES`, and directory-lease rename cases reported `EPERM`. No timeout change,
retry, or unrelated lease/daemon repair followed.

Rook focused gates:

```text
Runtime contract, product adapter, simplified harness, and wrapper: 78 passed
Changed Python compilation: passed
Prime bundle verification: passed
git diff --check: passed
```

The reviewed execution files are:

```text
Harness BEBC9F421AB8BBB3295083F4B72775D01B95C122045A195617E29157BFACFE3A
Wrapper 8B4B29DBC5B962AE4924C20A43539968CFE9C3B1447B3896D5E1D3552155C7D8
```

## Unexecuted Command

Independent review must supply the exact final Rook review commit and must
authenticate the wrapper before Python executes it:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_runtime_topology_gate_7b.py'
$expectedWrapper = '8B4B29DBC5B962AE4924C20A43539968CFE9C3B1447B3896D5E1D3552155C7D8'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7B V2 wrapper differs from the reviewed artifact.'
}

& $python $wrapper `
    --approved-rook-commit '<INDEPENDENT-REVIEW-SUPPLIED-EXACT-COMMIT>' `
    --approved-harness-sha256 'BEBC9F421AB8BBB3295083F4B72775D01B95C122045A195617E29157BFACFE3A'

if ($LASTEXITCODE -ne 0) {
    throw "Gate 7B V2 failed with exit code $LASTEXITCODE. Do not retry."
}
```

Gate 7A V2 stops here for independent review.
