# RookChat Prime Runtime-Topology Amendment

**Status:** PROPOSED; INDEPENDENT REVIEW REQUIRED

**Amends:** `2026-08-29-rookchat-prime-primary-backend-slices-3-4-design.md`

**Scope:** Prime RPC process topology and Task 7 qualification only

## Decision

RookChat will launch Prime RPC through a small, Prime-generic, explicitly
selected in-process runtime mode.

The public selector is:

```text
--mode rpc --rpc-runtime in-process
```

`--rpc-runtime` is a closed enum with `daemon` and `in-process`. Its default is
`daemon`, preserving Prime's current behavior for every existing caller. It is
valid only with `--mode rpc`; contradictory or unknown values fail at argument
admission. `in-process` also rejects `--daemon-socket` and every daemon-attach
form before daemon readiness, session creation, or lease acquisition. The
command cannot describe both a direct owner and a daemon owner.

This is not an embedded Prime fork inside Python. RookChat still launches one
Prime Node child and speaks the existing JSONL RPC protocol. The selector only
chooses which already-existing Prime `AgentConnection` implementation backs
that protocol.

## Source-grounded topology

Prime already has both required RPC paths.

### Existing daemon-backed default

Normal RPC currently satisfies `shouldUseDaemonClientRuntime()` and creates a
`DaemonAgentConnection`. See
[`main.ts:225`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L225),
[`main.ts:231`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L231),
and
[`main.ts:1515`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L1515).

The effective ownership is:

```text
RookChat broker
-> RPC client process
-> daemon supervisor
-> detached session worker
-> AgentSession
-> IPython kernel
```

The Windows daemon socket defaults to one global named pipe. A temporary agent
directory does not alter that endpoint.

### Existing in-process implementation

Prime also constructs `AgentSessionRuntime` directly and calls
`runRpcMode(runtime)` when daemon-client selection is false. See
[`main.ts:1586`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L1586)
and
[`main.ts:1645`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/main.ts#L1645).
`runRpcMode()` wraps that runtime in `InProcessAgentConnection`; it is not a
separate or reduced RPC protocol. See
[`rpc-mode.ts:116`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/rpc/rpc-mode.ts#L116).

No public CLI selector currently reaches this branch. It is reachable only
through internal conditions such as an owned worker process or programmatic
extension factories. The product change is therefore a selector over proven
Prime behavior, not a new session implementation.

## Why in-process RPC satisfies RookChat

The existing `InProcessAgentConnection` supports the product contract:

- saved-session creation and exact-file reopen through `SessionManager` and
  `AgentSessionRuntime`;
- session replacement and event rebinding;
- prompts with images;
- direct `promptAndWait()` followed by the shared headless-completion sequence;
- goals and `goal_update` events owned by the same `AgentSession`;
- compaction, retry, and queued continuation owned by the same `AgentSession`;
- direct Stop through `requestAbort()`;
- RLM depth controls;
- explicit IPython runtime preparation;
- RPC extension-UI bridging; and
- awaited runtime disposal, including IPython snapshot flush and provisioner
  shutdown.

The relevant methods are present at
[`in-process-agent-connection.ts:333`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts#L333),
[`in-process-agent-connection.ts:382`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts#L382),
[`in-process-agent-connection.ts:394`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts#L394),
[`in-process-agent-connection.ts:495`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts#L495),
[`in-process-agent-connection.ts:544`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts#L544),
and
[`in-process-agent-connection.ts:592`](D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts#L592).

The settled prompt boundary remains the shared `runHeadlessTurn()` path, not
raw `agent_end`. Extension UI remains the existing RPC bridge. No feature needed
by Slices 3-4 depends on daemon-only cron, heartbeat, inter-agent messaging, or
fleet recovery.

## Adopted process ownership

With the explicit selector, the ownership is:

```text
RookChat broker
-> one owned Prime RPC Node child
   -> one AgentSessionRuntime
   -> one AgentSession
   -> one contract-keyed IPython kernel
```

Consequences:

- The environment supplied to the broker-owned Node child is the environment
  read by `getKernelVenvDir()` in that same process.
- The child PID and launch generation identify the session owner directly.
- For a saved session, the `in-process` selector causes Prime itself to enable
  and own its existing session lease before creating `AgentSessionRuntime`.
  Rook does not supply Prime's internal lease flags or owner identity.
- Prime still owns the saved session, goal, compaction, continuation, and
  kernel lifecycle.
- The broker still owns only residency, command correlation, cancellation,
  registry records, and exact child teardown.
- Retirement disposes the Prime runtime and kernel but preserves the saved
  session.
- Reopen starts a new explicitly in-process child with the exact recorded
  session path and runtime contract.
- A broker/process crash remains `failed` or `interrupted` under Slice 0. It
  does not gain daemon-style transparent recovery. Explicit reopen is the
  recovery operation.

This aligns the actual process topology with the durable/in-memory split already
approved in Slice 0.

The complete runtime aggregate is:

```text
one RookChat conversation
-> one saved Prime session
-> one live Prime owner process generation
-> one immutable runtime contract
-> one contract-selected kernel
-> only descendants owned by that process generation
```

Its lifecycle is admitted and closed in one order:

```text
admit topology
-> bind contract
-> acquire saved-session lease
-> prepare runtime
-> run and settle
-> dispose descendants
-> release lease
```

## Saved-session exclusivity

The selected in-process branch creates a Prime-owned lease owner identity and
enables the existing lease facility for the lifetime of that process. This is
a Prime startup decision derived from `--rpc-runtime in-process`, not ambient
authority delegated to the Rook launch environment.

For a saved session, lease acquisition occurs before `AgentSession` creation or
kernel preparation. The same policy governs any session replacement admitted by
that runtime. Graceful runtime disposal releases the lease only after owned
session and kernel disposal settles.

Qualification must prove all four existing lease outcomes:

- a second in-process child targeting the active saved session refuses before
  creating an `AgentSession` or kernel;
- graceful close releases the lease and permits explicit reopen;
- an independently live lease owner, including a broker-orphaned owner, blocks
  reopen; and
- a dead owner is recovered only through Prime's existing process-identity and
  stale-lease rules.

The first owner retains the absolute canonical `sessionFile` returned by
`get_state`. Every contender and reopen uses the same isolated agent root and
`--resume <that-exact-sessionFile>`. Sharing only `--session-dir`, session ID,
basename, suffix, or latest-session selection is insufficient because the lease
key is the canonical session-file path.

The test harness may retain an exact process handle solely for cleanup while
logically detaching the first owner from the contender. It must not create an
actually unowned process to prove the orphan case.

## Windows identity and bootstrap boundaries

On Windows, the current lease implementation can invoke a synchronous
PowerShell process-start query. That subprocess must be corrected before any
process-boundary qualification:

- `-NoLogo -NoProfile -NonInteractive` remains required;
- `windowsHide: true` is required;
- one finite process deadline is required;
- failure is terminal for that identity attempt;
- no caller retries by launching another probe; and
- tests inject the query function rather than spawning a real shell.

An in-process/native identity implementation may replace the probe later, but
it is not required to decide this topology. The Task 7 gate requires only a
hidden, bounded, single-attempt boundary.

The pinned Prime baseline also contains the known kernel-bootstrap defect that
selects `<venv>/bin/python` on Windows and launches bootstrap subprocesses
without `windowsHide`. Before contract-kernel creation, Task 7 must reconcile
the exact upstream-quality correction in Prime commit
`142045138b8679ec077f8f032d2befe66ca5606b` onto the pinned baseline. It must
not broadly advance Prime as part of this correction. If that exact patch does
not apply without semantic conflict, implementation stops for review.

The reconciled Prime commit and resulting Prime bundle-manifest hash become the
executable identity in every new runtime contract. The earlier pinned commit
remains provenance, not the executable identity after reconciliation.

### Closed Prime launched-artifact manifest

The Prime bundle manifest reuses the previously qualified `dist` bundle shape;
it is not a caller-supplied SHA label. Its closed definition is:

```text
root: <Prime worktree>/packages/coding-agent/dist
included subtrees, in this exact order: ["bundle", "skills"]
entries: every regular file recursively beneath those two subtrees
authority paths: ordinal, forward-slash paths relative to `dist`
entry value: {"bytes": <integer>, "sha256": <uppercase SHA-256>}
```

Symlinks, junctions, reparse escapes, missing subtrees, duplicate normalized
paths, and non-regular entries fail closed. There are no cache/build exclusions
inside the two admitted subtrees. The manifest document is written outside
`dist`, so it never hashes itself.

The entry map is serialized with the already approved canonical JSON encoder:
compact ASCII UTF-8, no BOM or trailing newline, ordinal key order,
`sort_keys=True`, `separators=(",", ":")`, and `ensure_ascii=True`. The uppercase
SHA-256 of those canonical entry-map bytes is `bundleManifestSha256`.
`entryCount` and `totalBytes` are retained diagnostics, not alternate identity.

The Rook runtime-contract owner generates this manifest only after the exact
Prime build succeeds. It requires `bundle/cli.js` to be present and records that
absolute file as the launched entry point. Before every Prime launch or reopen,
the broker recomputes the manifest from the recorded `dist` root, verifies the
entry point is one of its entries, and compares the resulting identity with the
conversation's runtime contract. Missing, extra, or changed admitted bytes fail
`runtime_contract_unavailable` before Prime starts. The reconciled Prime git
commit remains recorded solely as provenance.

## Descendant phases and shutdown

Cold preparation does not have a speculative fixed process count. Qualification
uses a closed phase model instead:

```text
admission and lease:
  directly owned Prime Node process
  plus at most one hidden, bounded identity probe per lease acquisition

cold runtime preparation:
  Prime plus the preflight-resolved `uv.exe` and Python executables used for
  Python installation, venv creation, readiness/package checks, and the kernel

steady state:
  exactly the directly owned Prime process plus one contract-selected kernel

shutdown:
  graceful disposal, or one generation-verified hidden `taskkill.exe` fallback
  followed by zero descendants owned by that Prime launch generation
```

The harness preflights one absolute `uv.exe` and SHA-256, puts its directory
first in the sanitized child `PATH`, and sets `PRIME_AGENT_INSTALL_UV=0`, so
bootstrap resolves that exact executable and never launches an installer shell.
Observed cold-preparation path and hash must match. It records executable path,
parent PID, PID, and process-start identity for each observed descendant through
a non-spawning Windows process snapshot. It does not repeatedly launch
PowerShell to poll process state. A daemon supervisor, daemon worker, unrelated
console host, unlisted executable type, repeated identity probe, mismatched
`uv.exe`, or helper surviving into steady state is an absorbing failure.

Graceful RPC/runtime disposal is attempted first. Windows fallback termination
is allowed only when the direct child process handle is still live and an
immediately preceding process-start check matches the retained launch
generation. `taskkill /PID <direct-child> /T /F` then runs hidden, once, under a
finite deadline. Mismatch, timeout, or uncertainty records cleanup failure and
never widens the target, retries, kills by name, or targets a console host.

Model-free process qualification passes `--offline`. That prohibits Prime
startup/provider/model traffic; it does not pretend that first-use kernel
materialization is network-free. Any separately authorized `uv` Python/package
bootstrap traffic belongs only to the cold-preparation phase and is retained as
such. No prompt or provider call is admitted.

## Contract and reopen semantics

The approved runtime-contract fingerprint and immutable package rules remain
unchanged. The topology amendment strengthens their custody:

```text
closed broker launch environment
-> directly owned Prime process
-> directly owned AgentSession
-> directly owned kernel provisioner
-> contract-keyed environment
```

First use may create the absent contract environment through Prime's existing
provisioner. Reopen requires the previously prepared environment and exact
recorded import origins; it never silently rebuilds or substitutes a newer
package.

One saved Prime session remains bound to one RookChat conversation. Reopen uses
the exact absolute session file. Goal and compaction state are reconstructed by
Prime from that file. The broker does not persist a parallel goal or replay a
settlement-unknown prompt.

## Approach comparison

| Criterion | A: explicit in-process RPC | B: dedicated RookChat daemon namespace |
|---|---|---|
| Prime code reused | Existing runtime, connection, RPC, settlement | Existing daemon supervisor, worker, recovery, and RPC |
| New Prime seam | One closed CLI selector, Prime-owned lease activation, and reviewed Windows bootstrap/probe fixes | Private socket/lifetime contract plus worker environment/recovery custody |
| Runtime-contract authority | Directly on the session/kernel owner | Relayed through client, supervisor, and worker generation |
| Saved sessions and goals | Existing `AgentSessionRuntime` and `SessionManager` | Existing worker runtime |
| Compaction and settlement | Existing in-process `AgentSession` and shared headless turn | Existing worker plus supervisor relay |
| Stop | Direct abort in owned child | Client abort through supervisor to worker |
| Cleanup | One child tree owned by broker | Client, supervisor, worker, kernel, descriptors, sockets |
| Isolation | Per-conversation process and explicit paths | Requires a unique socket, descriptor root, agent root, and recovery namespace |
| Recovery after broker crash | Explicit reopen from saved session | Potential worker adoption/recovery, with substantially more ownership |
| Concurrency | One child/session per resident conversation | Fleet managed by private supervisor |
| Upstream compatibility | Default remains daemon; generic opt-in selector | Uses daemon architecture but requires product-specific namespace discipline |
| Slices 3-4 scope | Sufficient | More machinery than the product slice needs |

## Rejected alternative

Approach B is not inherently invalid. It becomes appropriate only if RookChat
later needs Prime's daemon fleet features, such as transparent worker recovery,
daemon-owned cron/heartbeat operation, or cross-session agent messaging.

Adopting it now would require RookChat to define and qualify:

- a unique Windows named-pipe namespace;
- a dedicated descriptor and orphan-journal root;
- supervisor and worker lifetime ownership;
- launch-environment persistence across recovery;
- worker-generation authentication without visible retry amplification;
- exact supervisor/worker/kernel cleanup; and
- recovery semantics consistent with the RookChat registry.

Those are real product responsibilities, not test harness details. None is
required by Slices 3-4. Approach B is therefore deferred, not prohibited.

## Qualification invariants

Before broker integration, one reviewed model-free lease sequence followed by
one direct Prime RPC session must prove:

1. the explicit selector chooses `InProcessAgentConnection`;
2. contradictory daemon options refuse before runtime or lease acquisition;
3. no daemon socket, supervisor, or session worker is used;
4. the selected session file and agent directory are isolated;
5. saved-session lease contention, release/reopen, live-owner refusal, and
   conservative dead-owner recovery all use the same canonical resumed session
   file and satisfy the rules above;
6. the reconciled Windows bootstrap selects `Scripts/python.exe` and hides its
   subprocesses;
7. the exact contract kernel environment is selected;
8. `rook_full` and `goal` resolve from their admitted roots;
9. RLM maximum depth is `0` from chat-local state;
10. `--offline` is active and no prompt/provider call occurs;
11. prepare, close, and kernel teardown settle within finite deadlines;
12. the phase-specific descendant set is exact and reaches the stated steady
    state, including exact preflighted `uv.exe` path/hash;
13. the Windows identity probe is hidden, bounded, and attempted once; and
14. fallback teardown is generation-qualified, hidden, bounded, single-attempt,
    and limited to the direct child tree.

Any unexpected process, socket, import root, retry, or cleanup boundary is one
absorbing gate failure. It is evidence to preserve, not permission to rerun.

Only after that vertical passes and is independently reviewed may the broker
use the selector. Failure injection precedes concurrency. Same-contract and
old/new-contract concurrency are the final Task 7 checks, not the first contact
with the topology.

## Unchanged design ownership

This amendment does not change:

- the immutable Rook package, goal-skill, and kernel-contract rules;
- Prime ownership of reasoning, saved sessions, goals, compaction, continuation,
  accounting, and completion belief;
- broker ownership of process residency, registry, command correlation, and
  prompt settlement projection;
- Rook ownership of live target verification, mutation, solve state, receipts,
  and evidence;
- the Slice 3 readonly profile or fresh Slice 4 full profile;
- target binding, Grasshopper document capture, evaluator separation, or live
  qualification prompts; or
- the deferred status of subagents, images, web search, steering, containment,
  and product cutover.

No new supervisor, daemon proxy, session implementation, goal controller, or
semantic acceptance mechanism is introduced.
