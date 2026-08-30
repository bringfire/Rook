# RookChat Prime Task 7 Recovery Amendment

**Status:** GATE 7A V5 IMPLEMENTED OFFLINE; GATE 7B V5 REVIEW REQUIRED

## Recovery Boundary

This amendment replaces only the interrupted Task 7 runtime-topology
qualification. It does not change the approved RookChat/Prime architecture or
restart Tasks 0-6.

The dirty review worktrees remain untouched quarantines:

```text
Rook  92f1c2f0dda68a52730b10c1f7f45b0dd6bee189
  M mcp_server/tests/test_rookchat_prime_runtime_topology_harness.py

Prime 6f76ebd9d5c2f2a690c104313dd4cc92c58f3040
  M packages/coding-agent/src/cli/daemon-launch.ts
  M packages/coding-agent/test/daemon-launch.test.ts
```

The failed Gate 7B V1 evidence remains unchanged at:

```text
C:/RookEvidence/2026-08-29-rookchat-prime-runtime-topology-gate-7b-lease
```

Its leaked task-owned daemon tree was identified by PID, parent PID, process
start ticks, executable, and exact command line, then terminated once through
the retained root process handle with whole-tree cleanup. No process name,
console host, shared Prime process, or shared Rook process was targeted.

## Runtime Contract

An explicit `--rpc-runtime` choice is authoritative before any daemon side
effect. Normal parsing later selects `daemon` or `in-process`; malformed
selectors fail without speculative daemon startup. Default RPC compatibility
remains daemon-backed.

The product topology is:

```text
RookChat conversation
-> one broker-owned Prime CLI process
-> in-process AgentConnection
-> Prime-owned saved session and lease
-> Prime-owned IPython kernel and child lifecycle
-> stdio RPC back to RookChat
```

RookChat owns the direct process handle, RPC channel, broker generation UUID,
and correlated Prime session identity. Prime owns the session lease, kernel,
children, persistence, and graceful shutdown.

Windows PID ancestry, process-start ticks, WMI, PowerShell, Toolhelp polling,
and `taskkill` are not product authority. Platform process data may appear only
as failure diagnostics. No shared daemon, new supervisor, broker-owned lease,
session journal, or lifecycle protocol is introduced.

For explicit `--rpc-runtime in-process`, Prime's session lease is one atomically
created directory held for the complete `AgentSessionRuntime` lifetime. There
is no heartbeat, clock, stale threshold, or automatic takeover. Normal disposal
verifies the owning token and removes the directory. Abrupt owner loss leaves
that saved conversation locked and failed; the user starts a new conversation.
Optional lifetime-lock metadata contains no PID or process-start identity and
is diagnostic only.

Prime's default daemon and owned-session-worker paths retain their established
recoverable lease policy, including dead-worker replacement. The internal
launch paths select that policy explicitly. RookChat's lifetime policy is
selected only by the explicit in-process RPC startup path; it does not redefine
the shared daemon lease switch or retire daemon recovery behavior.

## Surgical Corrections

1. Make separate-token and equals-form `--rpc-runtime` selectors authoritative
   before speculative daemon startup. Valid values are parsed normally;
   malformed and empty values fail closed without daemon contact.
2. Obtain Prime's reported `sessionFile`, call model-free
   `set_rlm_max_depth(0, global:false)` to flush it through Prime, and only then
   require the canonical file to exist. The harness never creates or touches
   the session file.
3. Emit one exact machine-readable `session_already_active` startup outcome
   containing the canonical session path when an in-process RPC contender is
   refused. Other parser, dependency, bootstrap, or configuration failures do
   not satisfy lease qualification.
4. Remove continuous `ProcessMonitor` and whole-process-table polling. Use the
   directly owned child handles, RPC/EOF settlement, bounded direct-child
   wait/terminate/kill, isolated runtime artifacts, and existing Prime kernel
   and session-disposal tests. The isolated agent root must contain no daemon
   worker, configuration, or daemon-log artifacts.
5. Bind every reopen to both the original `sessionId` and canonical
   `sessionFile`. Normal qualifying owners must close through stdin/RPC disposal
   with exit code zero. Safety cleanup remains available, but needing terminate
   or kill makes the gate fail.

## Gate 7B V5

Gate 7B V5 is one finite model-free sequence:

1. Launch one explicit in-process RPC child offline.
2. Verify `get_state`, flush with `set_rlm_max_depth`, and admit the persisted
   canonical session file.
3. Prove a simultaneous exact-file resume emits exactly
   `session_already_active` for that canonical file.
4. Close the owner gracefully and prove exact-file reopen returns the same
   session ID and file.
5. Close the reopened owner gracefully.
6. Prove every directly owned child settled and the isolated agent root
   contains no daemon artifacts.

An offline unit test proves an abandoned lock refuses reopening regardless of
age; Gate 7B does not create or recover an unclean owner. V5 uses fresh evidence
roots. No retry, provider/model contact, Rhino, Grasshopper, MCP, deployment,
or Gate 7C contact is authorized.

## Review Gate

Implementation stops at renewed offline Gate 7A review with exact clean
recovery commits, focused model-free tests, source and Prime-bundle custody, an
unexecuted simplified V5 harness, unchanged quarantines, unchanged V1 evidence,
and absent V2/V3/V4/V5 evidence roots. Gate 7B V5 requires separate independent
authorization.
