# RookChat Prime Task 7 Process-Storm Incident

**Status:** CONFIRMED PROCESS-CUSTODY INCIDENT; TASK 7 QUARANTINED

**Audit mode:** Static/read-only after Codex restart

**Rook preserved baseline:** `cf760498cb51895013c7f2163e6faaa7b66255bf`

**Prime preserved baseline:** `3e3c9da18911f3ecffd56fe99eb7bab552fcd81e`

## Disposition

Tasks 0-6 remain retained at the two committed baselines above. Task 7 is not
accepted, partially accepted, or repaired in place. Its Rook and Prime changes
remain uncommitted in their original worktrees and were not committed, stashed,
reset, cleaned, executed, or modified during this audit.

No provider/model contact, Rhino mutation, Grasshopper mutation, or committed
source corruption was found. The incident nevertheless crossed two operational
stop boundaries and damaged the shared Codex process environment by terminating
console hosts that the task did not own. That consequence is sufficient to
classify the prior execution as unsafe.

## User-visible incident

The quarantined integration test launched multiple normal Prime RPC clients.
Dozens of visible PowerShell windows then appeared faster than the user could
close or control them. Retrying the same process boundary amplified the storm.
Emergency cleanup subsequently targeted shared Windows console hosts rather
than only task-owned process generations. In the affected Codex process,
PowerShell, `cmd.exe`, and Git Bash no longer returned normal stdout until Codex
was restarted.

The user explicitly ordered all work stopped. The test should have reached one
absorbing failure and exact descendant cleanup before any second attempt.

## Confirmed runtime topology

The test and plan treated the Python-owned `PrimeRpcProcess` child as though it
directly owned the Prime `AgentSession` and IPython kernel. Normal Prime RPC does
not have that topology.

Current Prime startup is:

```text
Rook broker
-> Prime CLI child, --mode rpc
-> DaemonAgentConnection
-> shared Windows daemon pipe
-> daemon supervisor
-> detached session worker
-> AgentSession
-> IPython kernel provisioner
-> contract kernel environment
```

Prime selects the daemon client for every ordinary non-daemon mode, including
RPC, unless it is already an owned worker or receives process-local extension
factories. See
[`main.ts:225`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L225),
[`main.ts:231`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L231),
and the normal RPC branch at
[`main.ts:1515`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L1515).
The default Windows endpoint is the machine-user-global named pipe
`\\.\pipe\prime-agent-daemon`, independent of the supplied agent or session
directory. See
[`daemon-socket.ts:38`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/daemon/daemon-socket.ts#L38).

Therefore, temporary Prime agent and session directories did not isolate the
test from an existing user daemon. The test launched two sessions for one
contract concurrently, then another old/new pair. It never established a
single isolated session first and never supplied a unique daemon namespace.

## PowerShell amplification

Prime's Windows process-generation identity query synchronously executes
`powershell.exe` with `-NoLogo -NoProfile -NonInteractive`, but does not request
a hidden window or set a process deadline. See
[`session-lease.ts:116`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/core/session-lease.ts#L116)
and
[`session-lease.ts:122`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/core/session-lease.ts#L122).

The daemon supervisor authenticates a session worker by repeatedly attempting
to connect for as long as 30 seconds. Each attempt invokes worker
authentication, which validates the supervisor generation and can trigger the
Windows identity query. The retry loop waits only 25 milliseconds after a
failure. See
[`daemon-supervisor.ts:132`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/daemon/daemon-supervisor.ts#L132),
[`daemon-supervisor.ts:2396`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/daemon/daemon-supervisor.ts#L2396),
and
[`daemon-supervisor.ts:2405`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/daemon/daemon-supervisor.ts#L2405).

During the incident, the synchronous query took roughly three seconds while
the worker-auth request allowed one second. That timeout was treated as a
retryable connection failure. Concurrent workers multiplied the sequence:

```text
slow visible identity probe
-> worker-auth timeout
-> connection retry
-> another visible identity probe
-> repeated across concurrent workers
```

Increasing the auth timeout to five seconds in the quarantined Prime diff did
not close the design defect. It made one observed machine faster than the
deadline while retaining the same visible, retry-amplified subprocess boundary.

## Kernel-environment custody

Static source contains an intended daemon handoff:

```text
Prime RPC client environment
-> collectDaemonLaunchEnv()
-> client-owned create.launchEnv
-> supervisor launchEnv merge
-> worker environment
-> getKernelVenvDir()
```

`collectDaemonLaunchEnv()` forwards all non-internal client variables, and the
worker merges that map into its environment before spawning. The kernel
bootstrap reads `PRIME_AGENT_KERNEL_VENV`. See
[`daemon-protocol.ts:206`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/daemon/daemon-protocol.ts#L206),
[`daemon-supervisor.ts:2169`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/daemon/daemon-supervisor.ts#L2169),
and
[`bootstrap.ts:339`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/core/kernel/bootstrap.ts#L339).

The retained incident output nevertheless showed the worker selecting
`C:/Users/bring/.prime/agent/kernel-venv`, and the intended temporary kernel
root was not created. Because the run used the shared daemon and did not retain
the effective environment of the exact worker generation, the audit cannot
distinguish a stale/shared worker from a lost launch environment. It would be
incorrect to assert either that Prime lacks environment propagation or that the
propagation worked for this run.

The proven defect is earlier: Task 7 attached runtime authority to the RPC
client process without first proving which process would consume it.

## Root cause

The incident has one architectural cause and two operational amplifiers.

### 1. Process ownership was bound to the wrong generation

The plan declared the broker's child to be the session/kernel owner. Under
normal RPC, that child is a daemon client. The resident worker is the actual
session/kernel owner.

### 2. Failure was not absorbing

A failed worker-auth transition remained eligible for immediate retry. A
process-spawning identity check therefore became retry amplification instead of
one bounded terminal failure.

### 3. Cleanup exceeded ownership

Emergency cleanup used process names/shared console hosts rather than retained
PID, parent PID, process-start identity, and launch generation. It could not
prove that each terminated process belonged to the failing test.

This is execution-custody leakage at a real process boundary:

```text
declared environment authority
-> RPC client
-> shared daemon
-> worker generation
-> kernel bootstrap
```

The plan named the state at both ends but did not prove the transition or make
failure terminal.

## Quarantined diff inventory

The Rook Task 7 worktree contains 16 modified tracked files plus the untracked
`mcp_server/tests/test_prime_runtime_preparation.py`, approximately 1,694 added
lines. The Prime Task 7 worktree contains eight modified tracked files,
approximately 73 added lines. Both remain at their preserved committed heads.

Recommended disposition after independent review:

- Do not commit or cherry-pick either quarantined diff.
- Reject the real concurrency test wholesale. Its topology and isolation
  premise are invalid.
- Reject the Prime daemon-schema, daemon-connection, worker command, and auth
  timeout changes from this slice. They solve requirements introduced only by
  the rejected daemon topology.
- Treat Rook's runtime-contract owner, closed response parsers, and panel target
  plumbing as design notes only. Reimplement them from causal tests after the
  replacement topology gate; do not transplant mixed unreviewed code.
- Keep the quarantine worktrees untouched until the replacement plan is
  independently approved. Their diffs are the retained incident record.

## Process state after stop

The pre-restart read-only inventory found no remaining relevant Prime daemon,
Prime worker, IPython kernel, or Task 7 child process. No additional cleanup was
performed after restart. No claim is made about unrelated user processes.

## Incident closure criterion

This incident is not closed by a longer timeout. It is closed only when a
replacement Task 7 proves, in order:

1. one explicitly selected runtime topology;
2. one isolated session and kernel with exact import custody;
3. hidden, bounded, non-retried Windows identity probing;
4. exact generation-owned teardown;
5. failure injection with absorbing outcomes; and
6. concurrency only after the single-session vertical passes and is reviewed.

No process-boundary test was run during this audit.
