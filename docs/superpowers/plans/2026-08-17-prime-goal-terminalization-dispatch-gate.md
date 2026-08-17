# Prime Goal Terminalization And Rook Dispatch Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify an opt-in Prime goal terminalization path that admits every promoted `rook_full` call through persisted goal-scoped leases, observes results through persisted IPython ancestry, and permanently closes the admitted Rook path when an authorized goal completes.

**Architecture:** Prime owns one persisted execution-state controller beside `GoalState`; the kernel binds each host request to its originating Jupyter parent, `AgentSession` owns the active-branch goal-entry epoch and correlates persisted tool results, and one terminal record linearizes goal completion plus gate closure. Rook owns a promoted payload-first `rook_full` adapter that freezes each call once and executes `begin -> transport -> source record -> quiesce`; both repositories consume a byte-identical offline wire fixture, while fake transports and fault injection qualify the complete boundary without Rhino, MCP, a model, or the network.

**Tech Stack:** TypeScript 5.7, Node.js 22.8+, Vitest 4, Prime `AgentSession`/`SessionManager`/IPython kernel, Python 3.10+, pytest, MCP Python SDK test doubles, Rook `gh_behavioral_acceptance` custody helpers, PowerShell verification.

## Global Constraints

- Approved design: `docs/superpowers/specs/2026-08-17-prime-goal-terminalization-dispatch-gate-design.md`, SHA-256 `537FB29C8508AEB86F4249F9405B8AE00435F63DD48EE52E9657EDCE837A0C68`.
- Rook implementation baseline: `8435758116adbfd0672ef5d5fc91a49b84002445` plus the reviewed architecture documents on this branch.
- Prime architecture baseline: `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`. Task 0 must first cherry-pick the already-qualified structured-error commit `30a6621bc` and prove its two file blobs match exactly; do not pull the unrelated intervening Prime history.
- Work in the existing isolated Rook worktree and the dedicated Prime worktree `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate` on branch `codex/prime-goal-terminalization-dispatch-gate`; do not switch, edit, install from, or run tests against either primary checkout.
- Safety-relevant identity is captured at origin, persisted by one owner, and carried explicitly. Do not infer authority from the currently active cell, wall clock snapshot, checkout, branch, interpreter import path, process state, or other ambient state.
- This custody rule orders the tasks; it is not a new runtime framework. Add no generalized custody service, registry, or abstraction.
- The persisted usage epoch is the exact entry ID of the latest `thread_goal_state` entry on the active branch when that entry is valid. A malformed latest entry is `recovery_required`; do not skip backward. Do not add a counter or field to `GoalState`; install a new epoch only after that goal-state entry persists successfully.
- Use TDD for every production change. Record the causal RED before the minimal GREEN implementation.
- Prime is the sole owner of goal identity, generation, execution-gate state, transition persistence, terminalization, and rehydration.
- Rook is the sole owner of `rook_full.search/read/call`, target/argument freezing, MCP transport, payload projection, structured failure evidence, and source-log custody.
- Use `SessionManager.appendCustomEntryWithRollback()` as the only new persistence primitive. Do not add `fsync`, a database, a second journal, or a power-loss durability claim.
- The linearization point is successful persistence through Prime's established session persistence contract.
- Qualify only the unmodified durable adapter path. Direct `rlm.host_request`, adapter monkeypatching, and raw transport remain explicit IPython-containment gaps.
- Preserve generic Prime detached host-request fallback. Reject that fallback only for `goal.dispatch.begin` by requiring the comm message's `parent_header.msg_id` to equal the current `activeExecution.requestMsgId` and by requiring the bound IPython tool-call identity.
- Require persisted same-branch ancestry `lease_opened -> lease_quiesced -> toolResult` before `lease_observed`. Timestamps are never causal evidence.
- A matching `toolResult -> lease_quiesced` order is permanently `recovery_required`; later quiescence cannot repair it.
- Do not implement the semantic checkpoint, PlanGraph, Worker, Reviewer, policy routing, installer integration, automatic skill discovery, deployment, or live qualification.
- Do not change Rook MCP schemas, Rhino/Grasshopper handlers, receipts, fenced snapshots, provider adapters, or prior campaign evidence.
- Public model-facing Rook API remains exactly `rook_full.search`, `rook_full.read`, and `rook_full.call`.
- All qualification is offline with fake transport and session fixtures. Model, provider, Rhino, Grasshopper, Rook MCP, deployment, and network contact are forbidden.
- Do not begin Task 0 or create the Prime implementation worktree until this corrected plan receives one renewed independent review and explicit approval.
- Stop for renewed design review if Jupyter does not preserve the originating comm `parent_header.msg_id` when an old detached task fires during a newer active cell. Do not fall back to the newer execution.
- Stop for renewed design review if implementation requires moving Rook transport into Prime, remote Rook revocation, a distributed commit protocol, custom durability machinery, error-text parsing, receipt changes, a second goal orchestrator, a generalized custody substrate, or hostile-Python containment claims.

---

## File And Ownership Map

### Prime repository

- Read-only primary checkout: `D:/prime-agent` at `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`.
- Sole implementation worktree: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate`.

| File | Change | Sole responsibility |
|---|---|---|
| `prime-agent-runtime/src/rlm/mcp_base.py` | Adopt exact qualified commit `30a6621bc` | Preserve structured MCP failure results required by the V5 adapter contract. |
| `prime-agent-runtime/test/test_mcp_base.py` | Adopt exact qualified commit `30a6621bc` | Preserve the 22-assertion structured-error qualification seam. |
| `packages/coding-agent/src/core/goal-execution.ts` | Create | Closed execution records, persisted goal-entry epoch type, replay, lease state machine, completion authorization, terminalization, and closed error codes. |
| `packages/coding-agent/src/core/goals.ts` | Modify | Public completion-preparation response types only; persisted `GoalState` shape remains byte-compatible. |
| `packages/coding-agent/src/core/kernel/index.ts` | Modify | Origin-bound active execution context from the comm parent message, IPython tool-call identity, and kernel execution identity. |
| `packages/coding-agent/src/core/tools/ipython.ts` | Modify | Pass the model tool-call identity into `KernelManager.execute()`. |
| `packages/coding-agent/src/core/agent-session.ts` | Modify | Persisted goal-entry epoch ownership, optional controller activation, host-handler wiring, tool-result observation, goal lifecycle hooks, and terminal record adoption. |
| `packages/coding-agent/src/index.ts` | Modify | Export the controller interfaces needed by an integration host without exporting internal mutation methods. |
| `packages/coding-agent/skills/goal/src/goal/__init__.py` | Modify | Add the public `prepare_completion(candidate)` wrapper. |
| `packages/coding-agent/test/goal-execution.test.ts` | Create | Pure state, persistence, replay, concurrency, authorization, and fault-injection coverage. |
| `packages/coding-agent/test/kernel-host-request-context.test.ts` | Create | Active/detached host context and tool-call identity coverage. |
| `packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts` | Create | Live-kernel cooperative lease, same-cell refusal, and skill wrapper coverage. |
| `packages/coding-agent/test/suite/agent-session-goal.test.ts` | Modify | Configured/unconfigured goal behavior, observation ordering, supersession, and terminalization integration. |
| `packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json` | Create | Prime-side copy of the exact adapter/host wire vectors consumed by tests. |

### Rook repository: `C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger`

| File | Change | Sole responsibility |
|---|---|---|
| `integrations/prime/rook-full/src/rook_full/__init__.py` | Create | Durable versioned adapter source and the only public `rook_full` API. |
| `integrations/prime/rook-full/tests/test_rook_full.py` | Create | Payload-first, evidence, descriptor, lease, failure-precedence, and zero-retry tests. |
| `integrations/prime/rook-full/tests/fixtures/rook-goal-dispatch-wire-v1.json` | Create | Byte-identical Rook-side wire vectors consumed by adapter tests. |
| `docs/superpowers/reports/2026-08-17-prime-goal-terminalization-dispatch-gate-qualification.md` | Create | Evidence-led offline qualification result and bounded adoption claim. |
| `docs/superpowers/plans/2026-08-17-prime-goal-terminalization-dispatch-gate.md` | Modify during execution | Append commands, RED/GREEN counts, commit identities, fixture hash, and final scope reconciliation. |

### Cross-owner wire

The two fixture files must be byte-identical. They contain only protocol examples, not runtime state or authorization secrets:

```json
{
  "schema": "prime.rook_goal_dispatch_wire:v1",
  "begin": {
    "type": "goal.dispatch.begin",
    "payload": {
      "schema": "rook_full.dispatch_descriptor:v1",
      "adapter_version": "rook_full:v1",
      "operation_kind": "call",
      "capability_name": "gh_snapshot",
      "call_id": "call-0001",
      "target_identity_sha256": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
      "canonical_arguments_sha256": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
      "source_log_identity": "source-log-0001"
    }
  },
  "begin_response": {
    "schema": "prime.goal_dispatch_lease:v1",
    "lease_id": "lease-0001",
    "goal_id": "goal-0001",
    "goal_generation": "generation-0001",
    "call_id": "call-0001",
    "transition_sequence_opened": 1
  },
  "quiesce": {
    "type": "goal.dispatch.quiesce",
    "payload": {
      "schema": "rook_full.dispatch_quiescence:v1",
      "lease_id": "lease-0001",
      "call_id": "call-0001",
      "source_event_sequence": 1,
      "source_event_sha256": "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
    }
  },
  "quiesce_response": {
    "schema": "prime.goal_dispatch_quiescence:v1",
    "lease_id": "lease-0001",
    "call_id": "call-0001",
    "transition_sequence_quiesced": 2
  }
}
```

The fixture deliberately omits `ipythonToolCallId`, `kernelExecutionId`, goal identity, and generation from the model-controlled begin request. Prime supplies and binds those values from host state.

---

## Specification Coverage

| Approved specification area | Owning plan work |
|---|---|
| Origin-bound temporal authority custody | Global constraints; Tasks 0 through 4 |
| Qualified structured MCP failure prerequisite | Task 0 |
| Failure and cooperative-containment model | Global constraints; Tasks 5, 6, and 7 |
| Existing ownership and selected owners | File map; Tasks 1 through 5 |
| Conditional activation and legacy compatibility | Tasks 3 and 4 |
| Prime execution state and persisted transitions | Task 1 |
| Origin-bound active execution identity and detached fallback | Task 2 |
| Persisted goal-entry usage epoch and legacy goal-byte compatibility | Tasks 1, 3, and 4 |
| Lease opening, quiescence, result observation, and concurrency | Tasks 1, 2, 3, 5, and 6 |
| Pre-completion authorization and invalidation | Tasks 1 and 4 |
| Single-record terminalization | Tasks 1 and 4 |
| Recovery table and no-replay behavior | Tasks 1, 4, and 6 |
| Payload-first adapter promotion and failure precedence | Task 5 |
| Closed host-request admission and error codes | Tasks 1, 2, 3, and 5 |
| Prime, adapter, persistence, and boundary causal tests | Tasks 1 through 6 |
| Production exclusions, stop conditions, and bounded adoption claim | Global constraints and Task 7 |

---

### Task 0: Establish Hermetic Prime Custody And Restore The Qualified Error Prerequisite

**Files:**
- Create worktree: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate`
- Modify by exact cherry-pick: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/prime-agent-runtime/src/rlm/mcp_base.py`
- Modify by exact cherry-pick: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/prime-agent-runtime/test/test_mcp_base.py`

**Interfaces:**
- Consumes: Prime architecture baseline `c98941a2a5cf40faecf9b4648ac3c304abf48fd3` and reviewed commit `30a6621bc`.
- Produces: `McpToolError.structured_content` with unchanged text/exception behavior for Task 5; no coding-agent lifecycle change.

- [ ] **Step 1: Create the isolated Prime worktree at the audited baseline**

```powershell
$primeRoot = 'D:/prime-agent'
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'

if ((git -C $primeRoot status --short)) { throw "Prime primary checkout is dirty" }
if ((git -C $primeRoot rev-parse HEAD) -ne 'c98941a2a5cf40faecf9b4648ac3c304abf48fd3') {
  throw "Prime primary checkout is not at the audited baseline"
}
if (Test-Path -LiteralPath $prime) { throw "Prime implementation worktree already exists: $prime" }

git -C $primeRoot worktree add -b codex/prime-goal-terminalization-dispatch-gate $prime c98941a2a5cf40faecf9b4648ac3c304abf48fd3
if ($LASTEXITCODE -ne 0) { throw "Prime worktree creation failed" }
if ((git -C $prime rev-parse HEAD) -ne 'c98941a2a5cf40faecf9b4648ac3c304abf48fd3') {
  throw "Prime worktree baseline mismatch"
}
if ((git -C $prime status --short)) { throw "Prime implementation worktree is not clean" }
```

Expected: the primary checkout remains untouched and one clean linked worktree exists at the exact audited baseline.

- [ ] **Step 2: Cherry-pick only the qualified structured-error commit**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime cherry-pick 30a6621bc
```

Do not merge `fork/main`, `origin/main`, or the intervening Prime history. If cherry-pick conflicts, abort it and stop for continuity review.

- [ ] **Step 3: Verify exact source and test blob custody**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
$paths = @(
  'prime-agent-runtime/src/rlm/mcp_base.py',
  'prime-agent-runtime/test/test_mcp_base.py'
)
foreach ($path in $paths) {
  $reviewed = git -C $prime rev-parse "30a6621bc:$path"
  $current = git -C $prime rev-parse "HEAD:$path"
  if ($reviewed -ne $current) { throw "structured-error blob mismatch: $path" }
}
```

- [ ] **Step 4: Materialize branch-local JavaScript dependencies without network fallback**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Push-Location $prime
try {
  npm ci --offline --ignore-scripts
  if ($LASTEXITCODE -ne 0) { throw "Offline Prime dependency installation failed" }
} finally {
  Pop-Location
}
if ((git -C $prime status --short)) { throw "Dependency installation changed tracked Prime files" }
```

Expected: dependencies are materialized from the local npm cache using the reviewed lockfile. If offline installation cannot complete, stop for environment review; do not borrow the primary checkout's `node_modules`, add a junction, or permit network fallback.

- [ ] **Step 5: Reproduce the qualified runtime test seam without provider contact**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = "$prime/prime-agent-runtime/src"
  & $python -c "from pathlib import Path; import rlm.mcp_base as m; actual=Path(m.__file__).resolve(); expected=Path(r'$prime/prime-agent-runtime/src').resolve(); assert actual.is_relative_to(expected), (actual, expected); print(actual)"
  if ($LASTEXITCODE -ne 0) { throw "Prime runtime import custody failed" }
  & $python -m pytest "$prime/prime-agent-runtime/test/test_mcp_base.py" -q
  if ($LASTEXITCODE -ne 0) { throw "Prime structured-error tests failed" }
} finally {
  if ($null -eq $previousPythonPath) {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  } else {
    $env:PYTHONPATH = $previousPythonPath
  }
}
```

Expected: `rlm.mcp_base.__file__` resolves under the dedicated worktree and all structured MCP runtime tests pass with no network entry.

- [ ] **Step 6: Record the cherry-pick identity and stop for prerequisite review**

```powershell
$primeRoot = 'D:/prime-agent'
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime log -1 --oneline
git -C $prime status --short
git -C $prime diff --check c98941a2a5cf40faecf9b4648ac3c304abf48fd3..HEAD
if ((git -C $primeRoot rev-parse HEAD) -ne 'c98941a2a5cf40faecf9b4648ac3c304abf48fd3') {
  throw "Prime primary checkout moved"
}
if ((git -C $primeRoot status --short)) { throw "Prime primary checkout changed" }
```

**Mandatory review gate:** Confirm the primary checkout stayed untouched, only the two qualified runtime files changed in the linked worktree, both blobs equal `30a6621bc`, JavaScript dependencies came from the reviewed lockfile without network or primary-checkout reuse, the Python test imported the linked-worktree runtime, and no unrelated upstream Prime behavior entered the implementation branch.

---

### Task 1: Prime Persisted Goal-Entry Epoch And Execution State Machine

**Files:**
- Create: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/core/goal-execution.ts`
- Create: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/goal-execution.test.ts`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/index.ts`

**Interfaces:**
- Consumes: `SessionManager.appendCustomEntryWithRollback()`, `SessionManager.getBranch()`, `GoalState`, the exact persisted active-branch `thread_goal_state` entry ID supplied as an opaque `GoalUsageEpoch`, injected clock/ID functions, and an injected `GoalCompletionAdmissionController`.
- Produces: `GoalUsageEpoch`, `GoalExecutionController`, `GoalCompletionAdmissionController`, `GoalExecutionError`, closed wire validators, and `GOAL_EXECUTION_CUSTOM_TYPE` for Tasks 3 and 4. It does not create or increment a usage counter.

- [ ] **Step 1: Write the state-machine RED tests**

Create table-driven tests with these exact cases:

```typescript
const causalCases = [
  "initial state persists generation zero before becoming usable",
  "lease open installs memory only after persistence",
  "lease open persistence failure leaves state and branch unchanged",
  "quiescence retains exact source event identity",
  "duplicate stale wrong-goal wrong-generation and wrong-call quiescence refuse",
  "all leases in one tool call must quiesce before observation",
  "sibling branch tool result cannot observe a lease",
  "tool result before one mixed-cell quiescence enters recovery_required",
  "later quiescence cannot repair reverse ordering",
  "rehydration rejects sequence gaps and contradictory records",
  "rehydration never replays transport or transition side effects",
  "serialized begin and prepare races admit exactly one winner",
  "initialization requires the exact persisted goal-state entry identity",
  "a different persisted goal-state entry identity refuses lease and completion transitions",
] as const;
```

Use an actual temporary `SessionManager`, a deterministic `now()` sequence, and deterministic IDs. Create each `GoalUsageEpoch` by appending a real `thread_goal_state` entry and retaining its returned entry ID. Assert branch entry IDs and parent ancestry, not timestamps or numeric counters.

- [ ] **Step 2: Run the focused RED suite**

Run:

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/goal-execution.test.ts
```

Expected: FAIL because `src/core/goal-execution.ts` and its exported types do not exist.

- [ ] **Step 3: Implement the closed records and public controller surface**

Define these exact public types before implementing transitions:

```typescript
export const GOAL_EXECUTION_CUSTOM_TYPE = "thread_goal_execution_state";
export const GOAL_EXECUTION_SCHEMA = "prime.goal_execution_state:v1";

export type GoalExecutionGateState = "open" | "completion_pending" | "recovery_required" | "closed";
export type DispatchLeasePhase = "opened" | "quiesced" | "observed";
export type GoalUsageEpoch = string;

export interface GoalDispatchDescriptor {
  schema: "rook_full.dispatch_descriptor:v1";
  adapter_version: "rook_full:v1";
  operation_kind: "search" | "read" | "call";
  capability_name: string;
  call_id: string;
  target_identity_sha256: string;
  canonical_arguments_sha256: string;
  source_log_identity: string;
}

export interface ActiveIpythonExecutionIdentity {
  ipythonToolCallId: string;
  kernelExecutionId: string;
}

export interface GoalCompletionBindings {
  targetIdentity: string;
  sourceTraceEpoch: string;
  sourceTracePrefixIdentity: string;
  latestReceiptIdentity?: string;
  citedEvidenceIdentities: string[];
  budgetPolicyIdentity: string;
  budgetPolicyVersion: string;
  fixedBudgetLimits: Record<string, number>;
  completionDeadline: number;
  requestedDisposition: string;
}

export interface GoalCompletionAuthorization extends GoalCompletionBindings {
  authorizationId: string;
  goalId: string;
  goalGeneration: string;
  supersessionChain: string[];
  discreteUsageEpoch: GoalUsageEpoch;
}

export interface DispatchLeaseState {
  leaseId: string;
  descriptor: GoalDispatchDescriptor;
  phase: DispatchLeasePhase;
  ipythonToolCallId: string;
  kernelExecutionId: string;
  openedEntryId: string;
  quiescedEntryId?: string;
  observedEntryId?: string;
  sourceEventSequence?: number;
  sourceEventSha256?: string;
}

export interface GoalExecutionState {
  goalId: string;
  goalGeneration: string;
  transitionSequence: number;
  discreteUsageEpoch: GoalUsageEpoch;
  gateState: GoalExecutionGateState;
  leases: DispatchLeaseState[];
  pendingAuthorization: GoalCompletionAuthorization | null;
  terminalRecordId: string | null;
}

export interface GoalDispatchLeaseResponse {
  schema: "prime.goal_dispatch_lease:v1";
  lease_id: string;
  goal_id: string;
  goal_generation: string;
  call_id: string;
  transition_sequence_opened: number;
}

export interface GoalDispatchQuiescenceRequest {
  schema: "rook_full.dispatch_quiescence:v1";
  lease_id: string;
  call_id: string;
  source_event_sequence: number;
  source_event_sha256: string;
}

export interface GoalDispatchQuiescedResponse {
  schema: "prime.goal_dispatch_quiescence:v1";
  lease_id: string;
  call_id: string;
  transition_sequence_quiesced: number;
}

export interface GoalCompletionPrepared {
  disposition: "authorized";
  gate_state: "completion_pending";
}

export interface GoalCompletionAdmissionController {
  authorize(input: {
    candidate: Record<string, unknown>;
    goal: GoalState;
    goalGeneration: string;
    discreteUsageEpoch: GoalUsageEpoch;
  }): Promise<GoalCompletionBindings>;
  isCompletionBudgetAdmissible(input: {
    authorization: GoalCompletionAuthorization;
    goal: GoalState;
  }): boolean;
}
```

Export one `GoalExecutionError` whose `.code` is restricted to the spec's closed codes. Human text may be included but no caller parses it.

- [ ] **Step 4: Implement persistence-first transitions and replay**

Use one internal method for every state change:

```typescript
private persistAndInstall(record: GoalExecutionRecordV1, next: GoalExecutionState): string {
  const entryId = this.sessionManager.appendCustomEntryWithRollback(
    GOAL_EXECUTION_CUSTOM_TYPE,
    record,
  );
  this.state = next;
  return entryId;
}
```

The initial state record uses transition sequence `0`, a host-generated generation, an open gate, no leases, and no authorization. Rehydration walks only `sessionManager.getBranch()` for the active leaf, accepts one valid ordered prefix, and returns `recovery_required` for unknown schema versions, gaps, impossible phases, or records from a sibling branch.

`GoalUsageEpoch` is not serialized into `GoalState`. It is the existing session-entry identity that already owns the persisted goal bytes. Before initialization and every later transition, walk the current active branch and require the supplied or state-bound ID to equal its latest `thread_goal_state` entry, require that entry's data to be valid, and require its normalized goal identity to match the bound goal. A malformed latest entry is `recovery_required`; never skip backward to an older valid entry. Begin, preparation, and terminalization additionally require the exact epoch supplied by `AgentSession`; quiescence and observation recheck the epoch already bound into controller state.

Implement exact methods:

```typescript
initializeGoal(goal: GoalState, discreteUsageEpoch: GoalUsageEpoch): GoalExecutionState;
rehydrate(goal: GoalState, discreteUsageEpoch: GoalUsageEpoch): GoalExecutionState;
beginDispatch(descriptor: GoalDispatchDescriptor, execution: ActiveIpythonExecutionIdentity, goal: GoalState, discreteUsageEpoch: GoalUsageEpoch): Promise<GoalDispatchLeaseResponse>;
quiesceDispatch(input: GoalDispatchQuiescenceRequest): Promise<GoalDispatchQuiescedResponse>;
observePersistedToolResult(input: { entryId: string; ipythonToolCallId: string }): Promise<void>;
prepareCompletion(input: { candidate: Record<string, unknown>; goal: GoalState; discreteUsageEpoch: GoalUsageEpoch }): Promise<GoalCompletionPrepared>;
abortPendingAuthorization(reason: string): Promise<void>;
terminalize(input: { goal: GoalState; discreteUsageEpoch: GoalUsageEpoch; completionTime: number }): Promise<GoalState>;
snapshot(): Readonly<GoalExecutionState>;
```

`initializeGoal()` creates sequence zero only for a newly persisted active goal with no execution records for that goal/generation. `rehydrate()` replays the active branch and never creates a missing open state; an active goal without one compatible execution prefix becomes `recovery_required` as required by the specification.

Serialize every post-initialization operation through one controller-owned promise tail. `prepareCompletion()` must hold that serialized ownership across the injected admission await, so either a lease open persists first and preparation refuses, or authorization persists first and the later begin refuses. Do not add timeouts or a second scheduler.

`observePersistedToolResult()` must call `getBranch(entryId)` and require every matching lease's persisted `openedEntryId` and `quiescedEntryId` to occur before the exact tool-result entry in that same path. An open matching lease or reverse order sets `recovery_required` and can never be changed to observed by a later quiescence. Derive `supersessionChain` from ordered persisted non-idle `thread_goal_state` goal IDs on that same branch; never accept a chain supplied by the model or integration controller.

- [ ] **Step 5: Add authorization, deadline, budget, and terminal persistence tests**

Cover these exact outcomes:

```typescript
it("open lease blocks completion authorization");
it("completion_pending blocks new leases");
it("concurrent begin and prepare have one persisted winner");
it("authorization write failure leaves goal active and gate open");
it("wall clock advances without invalidating authorization before deadline");
it("deadline and completion-time budget predicate refuse completion");
it("a newly persisted goal-state entry identity aborts authorization persistently");
it("elapsed wall time alone does not change the persisted goal-entry identity");
it("terminal write failure leaves authorization pending and goal active");
it("terminal record closes gate and consumes authorization once");
it("lost terminal response followed by retry returns duplicate_completion");
it("new goal generation cannot inherit prior leases or authorization");
```

The terminal record contains the complete next `GoalState` and closed gate. No second `thread_goal_state` append occurs on the configured terminal path.

- [ ] **Step 6: Run the complete controller suite and build type check**

Run:

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/goal-execution.test.ts
npm run build
```

Expected: all focused tests pass; build exits `0`.

- [ ] **Step 7: Commit the Prime state-machine slice**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime add packages/coding-agent/src/core/goal-execution.ts packages/coding-agent/src/index.ts packages/coding-agent/test/goal-execution.test.ts
git -C $prime commit -m "feat: add persisted goal execution state"
```

**Mandatory review gate:** Independently review replay ordering, sibling-branch rejection, mixed multi-lease behavior, persistence-before-memory, opaque persisted-entry epoch use, and the absence of a counter, transport, or Rook semantics from this controller.

---

### Task 2: Prime Active IPython Execution Custody

**Files:**
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/core/kernel/index.ts`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/core/tools/ipython.ts`
- Create: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/kernel-host-request-context.test.ts`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/agent-session-recursion.test.ts`

**Interfaces:**
- Consumes: the incoming Jupyter comm message's `parent_header.msg_id`, existing kernel `ActiveExecution`, `ExecuteOptions`, generic `HostRequestHandler`, and IPython tool `toolCallId`.
- Produces: a second, origin-bound `HostRequestContext` argument. Task 3 uses it to admit `goal.dispatch.begin`; existing handlers continue receiving `cellSourceCode` in their payload for compatibility.

- [ ] **Step 1: Write RED tests for active and detached requests**

The tests must prove:

```typescript
it("passes tool call and kernel execution identities during an active cell");
it("marks a detached request inactive while preserving last-cell source fallback");
it("marks an old detached request inactive when it fires during a newer active cell");
it("does not synthesize a tool-call identity for direct kernel execute without one");
it("keeps generic detached rlm host requests working");
```

For the idle detached case, schedule `asyncio.create_task(rlm.host_request("test.detached", {"value": 1}))`, let the originating cell become idle, then release the task. Assert `context.activeExecution === false` while the legacy payload still contains `cellSourceCode`.

For the cross-cell case, hold the same old detached task, start a second cell, and release the task while the second cell is active. Assert the incoming comm retains the first cell's `parent_header.msg_id`, `context.activeExecution === false`, and no identity from the second cell appears in the context. If the real kernel test cannot observe the originating parent ID, stop for renewed design review; do not weaken the assertion or substitute the current execution.

- [ ] **Step 2: Run the focused RED tests**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/kernel-host-request-context.test.ts test/agent-session-recursion.test.ts
```

Expected: the new context assertions fail because the handler currently receives only one payload argument and `ExecuteOptions` has no tool-call identity.

- [ ] **Step 3: Add host-owned execution context without changing generic fallback**

In `kernel/index.ts`, add:

```typescript
export interface HostRequestContext {
  activeExecution: boolean;
  requestParentMessageId?: string;
  cellSourceCode?: string;
  ipythonToolCallId?: string;
  kernelExecutionId?: string;
}

export type HostRequestHandler = (
  payload: Record<string, unknown>,
  context: HostRequestContext,
) => Promise<Record<string, unknown>>;

export interface ExecuteOptions {
  signal?: AbortSignal;
  onStream?: (chunk: string, name: "stdout" | "stderr") => void;
  onLateSentAgentMessage?: (message: KernelSentAgentMessage) => void;
  maxOutputChars?: number;
  internal?: boolean;
  ipythonToolCallId?: string;
}
```

Pass `(incoming.parent_header as { msg_id?: unknown }).msg_id` from `handleCommMessage()` through `startHostRequestFromComm()` into `handleHostRequest()`. Treat it as present only when it is a nonempty string. Keep the existing payload behavior and supply the origin-correlated context separately:

```typescript
const requestParentMessageId =
  typeof parentMessageId === "string" && parentMessageId.length > 0
    ? parentMessageId
    : undefined;
const execution = this.activeExecution;
const belongsToActiveExecution =
  execution !== undefined && requestParentMessageId === execution.requestMsgId;
const cellSourceCode = execution?.code ?? this.lastCellCode;
return handler(
  Object.assign({}, data, { cellSourceCode }),
  {
    activeExecution: belongsToActiveExecution,
    requestParentMessageId,
    cellSourceCode,
    ipythonToolCallId: belongsToActiveExecution
      ? execution.opts.ipythonToolCallId
      : undefined,
    kernelExecutionId: belongsToActiveExecution
      ? execution.requestMsgId
      : undefined,
  },
);
```

The comm parent identity is captured at receipt and carried as an argument. `handleHostRequest()` must not reread or reconstruct it later. The current active execution is used only for an exact equality check; it is never used as the request's origin.

Existing one-argument handlers remain behaviorally compatible because JavaScript ignores the additional argument.

- [ ] **Step 4: Pass the model tool-call identity into kernel execution**

In `executeWithBusyKernelChoice()`, pass:

```typescript
result: await m.execute(code, {
  signal,
  onStream,
  ipythonToolCallId: toolCallId,
  onLateSentAgentMessage: onLateSentAgentMessage
    ? (message) => onLateSentAgentMessage(toolCallId, message)
    : undefined,
}),
```

Do not alter bootstrap/internal executions or Prime's last-cell source behavior.

- [ ] **Step 5: Run the kernel and recursion suites**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/kernel-host-request-context.test.ts test/agent-session-recursion.test.ts
npm run build
```

Expected: active context, detached context, and existing recursion tests pass.

- [ ] **Step 6: Commit the Prime execution-context slice**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime add packages/coding-agent/src/core/kernel/index.ts packages/coding-agent/src/core/tools/ipython.ts packages/coding-agent/test/kernel-host-request-context.test.ts packages/coding-agent/test/agent-session-recursion.test.ts
git -C $prime commit -m "feat: expose active ipython host context"
```

**Mandatory review gate:** Confirm dispatch identity comes from the comm parent at origin, an old detached request cannot borrow a newer active cell, detached fallback is preserved generically, and no model-supplied payload field can make an inactive execution active.

---

### Task 3: AgentSession Dispatch Lease And Tool-Result Observation Wiring

**Files:**
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/core/agent-session.ts`
- Create: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/suite/agent-session-goal.test.ts`

**Interfaces:**
- Consumes: `GoalExecutionController`, `GoalUsageEpoch`, `HostRequestContext`, the Prime-side wire fixture, persisted `thread_goal_state` entry identities, and persisted `toolResult` messages.
- Produces: the sole `GoalUsageEpoch` owner in `AgentSession`, optional configured handlers `goal.dispatch.begin` and `goal.dispatch.quiesce`, persisted result observation, and an AgentSession-owned controller instance.

- [ ] **Step 1: Freeze the Prime wire fixture and write handler RED tests**

Add the exact fixture from the plan's cross-owner wire section. Tests must parse it strictly and prove:

```typescript
it("does not register dispatch handlers without an admission controller");
it("rehydrates a configured active goal without compatible execution state as recovery_required");
it("rejects begin when HostRequestContext is inactive");
it("rejects begin when the active context lacks an ipython tool-call identity");
it("rejects an old detached request released during a newer active execution");
it("binds begin to host-owned tool-call and kernel execution identities");
it("quiesce may arrive after the cell becomes inactive");
it("unknown and open request fields refuse before transition state access");
it("loads the usage epoch from the latest goal-state entry when it is valid");
it("refuses a malformed latest goal-state entry instead of skipping backward");
it("does not load a sibling branch goal-state entry as the usage epoch");
it("installs a new usage epoch only after goal-state persistence succeeds");
it("keeps unconfigured persisted GoalState data byte-compatible and adds no epoch field");
```

- [ ] **Step 2: Run the AgentSession RED cases**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/suite/agent-session-goal.test.ts
```

Expected: configured handler assertions fail because `AgentSessionConfig` has no completion controller and no dispatch handlers exist.

- [ ] **Step 3: Add opt-in controller construction and closed handlers**

Add to `AgentSessionConfig`:

```typescript
goalCompletionAdmissionController?: GoalCompletionAdmissionController;
```

When present, construct one `GoalExecutionController` owned by `AgentSession`. When absent, do not construct it and do not register lease or preparation handlers.

Add one nonserialized field to `AgentSession`:

```typescript
private _goalUsageEpoch?: GoalUsageEpoch;
```

Keep the existing `_loadPersistedGoalState()` path byte-for-byte for unconfigured sessions. Add a configured-only helper that walks only `sessionManager.getBranch()` from its active leaf and returns the normalized goal plus the exact entry ID of the latest `thread_goal_state` entry when valid:

```typescript
private _loadPersistedGoalStateWithEpoch():
  | { status: "none"; goal: GoalState }
  | { status: "valid"; goal: GoalState; usageEpoch: GoalUsageEpoch }
  | { status: "invalid"; goal: GoalState } {
  const branch = this.sessionManager.getBranch();
  for (let index = branch.length - 1; index >= 0; index--) {
    const entry = branch[index];
    if (entry.type === "custom" && entry.customType === GOAL_STATE_CUSTOM_TYPE) {
      if (!isPersistedGoalState(entry.data)) {
        return { status: "invalid", goal: emptyGoalState() };
      }
      return {
        status: "valid",
        goal: normalizeGoalState(entry.data),
        usageEpoch: entry.id,
      };
    }
  }
  return { status: "none", goal: emptyGoalState() };
}
```

A configured session with a malformed latest goal-state entry or an active goal without an epoch enters `recovery_required`; it must not fall back to an older entry. An unconfigured session continues calling the existing loader and retains existing outward behavior.

Keep the existing `_persistGoalState()` and unconfigured `_setGoalState()` ordering unchanged. Add a configured-only persistence helper that returns the existing entry identity and rolls back if persistence fails:

```typescript
private _persistConfiguredGoalState(goal: GoalState): GoalUsageEpoch {
  return this.sessionManager.appendCustomEntryWithRollback(
    GOAL_STATE_CUSTOM_TYPE,
    goal,
  );
}
```

In `_setGoalState()`, retain the current implementation exactly when the controller is absent. When configured, normalize first, persist through `_persistConfiguredGoalState()` when requested, and only then install both `_goalState` and `_goalUsageEpoch`. For configured `persist: false`, preserve the prior epoch. Do not add `discreteUsageEpoch`, `goalUsageEpoch`, or any other new property to the serialized `GoalState`; the entry ID is the epoch. Rehydration installs the returned pair from the same active-branch scan.

On configured session startup, call `rehydrate(goal, usageEpoch)` only when the loaded goal is active and the exact epoch exists. A malformed/missing epoch or incompatible execution prefix becomes `recovery_required`. After `_startGoal()` successfully persists a fresh active goal and installs its returned epoch, call `initializeGoal(this._goalState, this._requireGoalUsageEpoch())`; never initialize before goal persistence and never synthesize an epoch for an idle branch.

Add the required accessor in this task because dispatch consumes it immediately:

```typescript
private _requireGoalUsageEpoch(): GoalUsageEpoch {
  if (!this._goalUsageEpoch) {
    throw new GoalExecutionError("recovery_required");
  }
  return this._goalUsageEpoch;
}
```

Register exact internal handlers:

```typescript
handlers["goal.dispatch.begin"] = async (payload, context) => {
  const descriptor = validateDispatchHostPayload(payload);
  if (
    !context.activeExecution ||
    !context.requestParentMessageId ||
    context.requestParentMessageId !== context.kernelExecutionId ||
    !context.ipythonToolCallId ||
    !context.kernelExecutionId
  ) {
    throw new GoalExecutionError("execution_not_active");
  }
  return await this._goalExecution!.beginDispatch(descriptor, {
    ipythonToolCallId: context.ipythonToolCallId,
    kernelExecutionId: context.kernelExecutionId,
  }, this.goalState, this._requireGoalUsageEpoch());
};

handlers["goal.dispatch.quiesce"] = async (payload) =>
  await this._goalExecution!.quiesceDispatch(validateQuiescenceHostPayload(payload));
```

`rlm.host_request()` flattens the caller payload with `type`, and the kernel adds the compatibility-only `cellSourceCode`. Each validator first requires its exact `type`, removes only those two bridge-owned fields, and then validates the remaining closed descriptor or quiescence shape. Validation rejects every other unknown field and wrong scalar type before reading current goal or gate state; neither `type` nor `cellSourceCode` contributes authorization.

The handler receives origin identity only through `HostRequestContext`; it never reads `activeExecution` itself and never substitutes the current cell when the parent does not match.

- [ ] **Step 4: Observe only after the tool result entry persists**

In `_processAgentEvent()`, retain the entry ID returned from the existing append:

```typescript
const persistedEntryId = this.sessionManager.appendMessage(event.message);
if (event.message.role === "toolResult" && this._goalExecution) {
  await this._goalExecution.observePersistedToolResult({
    entryId: persistedEntryId,
    ipythonToolCallId: event.message.toolCallId,
  });
}
```

Do not observe at `message_start`, before `appendMessage()`, or from in-memory agent state. If message persistence throws, no observation transition may exist.

- [ ] **Step 5: Add the detached and mixed-cell causal regressions**

Cover all four persisted orders:

```text
opened -> quiesced -> toolResult -> observed
opened -> quiesced -> process exit -> toolResult missing -> recovery_required
opened -> toolResult -> quiesced -> recovery_required
opened(A,B) -> quiesced(A) -> toolResult -> quiesced(B) -> recovery_required
```

Add a sibling-branch case where a matching `toolResult` exists outside `getBranch(quiescedEntryId)`. It must not observe the lease.

Add a persistence-custody case that captures the current epoch, advances wall time without persisting a goal entry, and proves the epoch is unchanged. Then persist one byte-identical-shape `thread_goal_state` update, prove the returned entry ID becomes the new epoch only after persistence succeeds, and prove an authorization bound to the prior ID refuses.

- [ ] **Step 6: Run focused AgentSession and controller tests**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/goal-execution.test.ts test/suite/agent-session-goal.test.ts
npm run build
```

Expected: all tests pass, including the reviewer's sibling-branch and late second-lease refinements.

- [ ] **Step 7: Commit the Prime dispatch-wiring slice**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime add packages/coding-agent/src/core/agent-session.ts packages/coding-agent/test/suite/agent-session-goal.test.ts packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json
git -C $prime commit -m "feat: gate goal-scoped dispatch leases"
```

**Mandatory review gate:** Confirm result observation follows the exact persisted tool-result entry on the same branch, every mixed-cell lease must quiesce before that entry, the goal usage epoch is one existing active-branch entry identity, persistence precedes epoch installation, and serialized legacy goal bytes contain no new field.

---

### Task 4: Prime Completion Preparation And Terminalization

**Files:**
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/core/goals.ts`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/src/core/agent-session.ts`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/skills/goal/src/goal/__init__.py`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/suite/agent-session-goal.test.ts`
- Create: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts`

**Interfaces:**
- Consumes: observed leases and the injected `GoalCompletionAdmissionController`.
- Produces: `await goal.prepare_completion(candidate)`, configured terminalization, same-cell post-completion refusal, and unchanged legacy completion when no controller is configured.

- [ ] **Step 1: Write completion and compatibility RED tests**

Cover:

```typescript
it("keeps legacy goal.complete unchanged when controller is absent");
it("requires prepare_completion when controller is configured");
it("keeps goal.get observational during completion_pending");
it("refuses preparation while a lease is open or merely quiesced");
it("authorizes after all leases are observed in a prior tool result");
it("steering supersession and a new persisted goal-state entry abort pending authorization");
it("wall-clock accounting without persistence does not change the usage epoch");
it("unconfigured goal-state JSON is byte-identical to the legacy closed key set");
it("terminal persistence failure leaves authorization pending and goal active");
it("successful terminal persistence installs complete goal and closed gate");
it("same-cell rook begin after goal.complete refuses before fake transport");
it("lost completion response cannot append a second terminal record");
it("rehydration derives complete goal and closed gate from one terminal record");
```

- [ ] **Step 2: Run the completion RED suites**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/suite/agent-session-goal.test.ts test/kernel-goal-dispatch-skill.test.ts
```

Expected: `prepare_completion` import/handler tests fail and configured `goal.complete()` still bypasses authorization.

- [ ] **Step 3: Add the Python skill wrapper**

Update the module to expose exactly:

```python
__all__ = ("get", "create", "prepare_completion", "complete")


async def prepare_completion(candidate: dict) -> dict:
    if type(candidate) is not dict:
        raise TypeError("candidate must be a dict")
    return await host_request("goal.prepare_completion", {"candidate": candidate})
```

Do not expose authorization IDs, goal generations, usage epochs, or internal lease calls to the skill.

- [ ] **Step 4: Wire configured preparation and terminalization**

Keep the existing synchronous `goal.get/create/complete` return behavior when no controller is configured. Widen `handleGoalHostRequest()` to return `GoalHostResponse | GoalCompletionPrepared | Promise<GoalHostResponse | GoalCompletionPrepared>` and move configured preparation/completion into async private helpers:

```typescript
case "goal.prepare_completion":
  if (!this._goalExecution) {
    throw new Error("goal completion preparation is not available in this session");
  }
  return this._goalExecution.prepareCompletion({
    candidate: validateCompletionCandidate(payload),
    goal: this.goalState,
    discreteUsageEpoch: this._requireGoalUsageEpoch(),
  });

case "goal.complete":
  return this._goalExecution
    ? this._completeConfiguredGoalFromHost()
    : goalHostResponse(this._completeGoalFromHost(), true);
```

The configured helper owns the awaited terminal transition:

```typescript
private async _completeConfiguredGoalFromHost(): Promise<GoalHostResponse> {
  const current = this._goalWithAccountedWallClock();
  const completed = await this._goalExecution!.terminalize({
    goal: current,
    discreteUsageEpoch: this._requireGoalUsageEpoch(),
    completionTime: Date.now(),
  });
  this._installPersistedTerminalGoal(completed);
  return goalHostResponse(this._goalState, true);
}
```

Register `goal.prepare_completion` only when the execution controller exists. Keep `goal.get/create/complete` registration under the existing `includeGoals` boundary and have each kernel handler return `await Promise.resolve(this.handleGoalHostRequest(type, payload))` so legacy synchronous and configured asynchronous results share one bridge.

`_installPersistedTerminalGoal()` updates memory, accounting, queue state, and emitted UI state without appending another goal record. The controller has already persisted the sole terminal record.

- [ ] **Step 5: Connect persisted-entry invalidation hooks without changing `GoalState` bytes**

Do not modify the `GoalState` interface, `emptyGoalState()`, `normalizeGoalState()`, or serialized goal payload with an epoch field. `AgentSession._goalUsageEpoch` is the exact latest persisted `thread_goal_state` entry ID installed by Task 3.

Use Task 3's `_requireGoalUsageEpoch()` accessor to pass that exact ID to completion authorization and terminalization; lease opening already uses it. Call persisted authorization abort before admitted steering, goal supersession, clear/pause, resume, accepted assistant-message accounting, or any other operation that will persist a changed `thread_goal_state`. Persist the changed goal next; only successful persistence may replace `_goalUsageEpoch` with the returned entry ID. If abort or goal persistence fails, do not install a new in-memory goal or epoch.

Rehydration takes the goal and epoch from the same active-branch entry. A sibling entry, model-provided value, elapsed wall-clock value, or execution transition sequence can never become the usage epoch. Do not compare continuously changing `timeUsedSeconds` for authorization identity; check only exact epoch equality, the explicit deadline, and the completion-time budget predicate.

Add a byte-custody regression that persists representative idle, active, paused, budget-limited, complete, and error goals with the controller absent and compares each custom-entry `data` JSON to the baseline expected keys and values. Assert no `discreteUsageEpoch` or `goalUsageEpoch` key exists.

- [ ] **Step 6: Add process-crash and replay qualification**

Inject failure before and after each persisted phase and assert:

```text
authorization write failure -> active/open
authorized without terminal record -> active/recovery_required on restart
torn terminal line -> active/recovery_required
valid terminal record -> complete/closed
valid terminal record plus lost reply -> duplicate_completion on retry
```

Use Prime's existing session parser behavior for torn trailing JSONL; do not add a custom repairer.

- [ ] **Step 7: Run the complete Prime focused seam and build**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/goal-execution.test.ts test/kernel-host-request-context.test.ts test/kernel-goal-dispatch-skill.test.ts test/kernel-goal-skill.test.ts test/agent-session-recursion.test.ts test/suite/agent-session-goal.test.ts
npm run build
```

Expected: all focused tests pass; existing unconfigured goal and detached-recursion behavior remains green.

- [ ] **Step 8: Commit the Prime terminalization slice**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime add packages/coding-agent/src/core/goals.ts packages/coding-agent/src/core/agent-session.ts packages/coding-agent/skills/goal/src/goal/__init__.py packages/coding-agent/test/suite/agent-session-goal.test.ts packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts
git -C $prime commit -m "feat: terminalize authorized goals atomically"
```

**Mandatory review gate:** Confirm one persisted terminal record owns both complete goal and closed gate, no configured path mutates memory or epoch before persistence, the epoch is always an active-branch goal-entry ID, and unconfigured Prime goal bytes are unchanged.

---

### Task 5: Promote The Durable Rook `rook_full` Adapter

**Files:**
- Create: `integrations/prime/rook-full/src/rook_full/__init__.py`
- Create: `integrations/prime/rook-full/tests/test_rook_full.py`
- Create: `integrations/prime/rook-full/tests/fixtures/rook-goal-dispatch-wire-v1.json`

**Interfaces:**
- Consumes: `rlm.host_request`, `McpIntegration`, `McpToolError`, `rook.gh_behavioral_acceptance.canonical_json_bytes()`, and the canonical gateway source-event appenders.
- Produces: only `search(query)`, `read(name)`, and `call(name, arguments)`; internal lease operations remain module-private.

- [ ] **Step 1: Copy and freeze the reviewed V5 behavior as RED contract tests**

Import the production source directly by adding `integrations/prime/rook-full/src` to the test path. Stub `mcp`, `rlm`, and transport entry so tests remain offline. Preserve every qualified V5 assertion with these exact test names and outcomes:

```text
test_success_records_exact_envelope_then_returns_same_payload_object
  -> returned value is result["data"] by object identity
  -> one flushed source row retains the complete original envelope

test_mcp_error_records_structured_content_then_reraises_same_object
  -> raised exception is the exact fake McpToolError object
  -> message and structured_content remain unchanged
  -> one error source row is retained

test_returned_failure_records_then_refuses
  -> {success:false,data} is retained once
  -> RuntimeError("rook_full_unsuccessful_result") is raised

test_malformed_or_open_envelope_records_unknown_then_refuses
  -> missing, extra, or wrong-typed envelope fields each retain one unknown event
  -> RuntimeError("rook_full_malformed_result") is raised

test_recorder_failure_wins_over_transport_success_or_failure
  -> the exact recorder exception escapes in both cases
  -> quiescence host request count remains zero

test_mutating_returned_payload_cannot_change_flushed_source_bytes
  -> source bytes and SHA-256 are identical before and after payload mutation

test_exactly_one_terminal_source_event_exists_per_transport_entry
  -> success, returned failure, MCP error, and non-MCP error each append one row
  -> transport and source-event counts remain equal
```

Use the retained V5 test file at `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-repair-loop-v5/operator/test_adapter_payload_contract.py` as read-only evidence when transcribing fixtures; do not import or mutate that retained evidence root.

- [ ] **Step 2: Add lease and immutable-descriptor RED tests**

Use the Rook-side wire fixture and assert exact order:

```text
goal.dispatch.begin
one fake transport entry
one source event append
goal.dispatch.quiesce
payload return or qualified exception
```

Test all three public operations. Mutate the caller's arguments and target environment while the awaited `begin` is suspended; transport, source event, and hashes must still derive from the original frozen bytes.

Add zero-entry assertions for missing handlers, begin refusal, nonfinite input, unsupported JSON input, and malformed target identity.

Add these exact quiescence-precedence cases before implementing `_raise_quiescence_failure()`:

```text
test_quiescence_failure_after_transport_success_raises_lifecycle_error
  -> the source event is retained
  -> no payload is returned
  -> RuntimeError("rook_full_quiescence_failed") is raised

test_transport_exception_is_reraised_by_identity_when_quiescence_also_fails
  -> the raised object is the exact transport exception
  -> the quiescence exception is retained as __context__
  -> the source event retains the transport failure

test_transport_exception_explicit_cause_survives_quiescence_failure
  -> the raised object is the exact transport exception
  -> its preexisting __cause__ is unchanged
  -> the quiescence exception is retained as __context__
```

Also assert recorder failure remains primary and prevents quiescence, so these cases cannot accidentally supersede the qualified V5 recorder-precedence contract.

- [ ] **Step 3: Run the adapter RED suite**

```powershell
$rook = 'C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger'
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = @(
    "$rook/integrations/prime/rook-full/src",
    "$rook/mcp_server/src",
    "$prime/prime-agent-runtime/src"
  ) -join [IO.Path]::PathSeparator
  & $python -c "from pathlib import Path; import rlm.mcp_base as m; actual=Path(m.__file__).resolve(); expected=Path(r'$prime/prime-agent-runtime/src').resolve(); assert actual.is_relative_to(expected), (actual, expected)"
  if ($LASTEXITCODE -ne 0) { throw "Adapter test runtime import custody failed" }
  & $python -m pytest "$rook/integrations/prime/rook-full/tests/test_rook_full.py" -q
  if ($LASTEXITCODE -eq 0) { throw "Adapter RED suite unexpectedly passed" }
} finally {
  if ($null -eq $previousPythonPath) {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  } else {
    $env:PYTHONPATH = $previousPythonPath
  }
}
```

Expected: FAIL because the durable adapter source does not exist.

- [ ] **Step 4: Implement one immutable call descriptor**

Use a frozen dataclass containing canonical bytes rather than a mutable dictionary:

```python
@dataclass(frozen=True)
class _FrozenCall:
    operation_kind: str
    capability_name: str
    call_id: str
    source_arguments_bytes: bytes
    canonical_arguments_sha256: str
    target_identity_bytes: bytes
    target_identity_sha256: str
    source_log_path: str
    source_log_identity: str

    def source_arguments(self) -> dict:
        return json.loads(self.source_arguments_bytes.decode("utf-8"))

    def target_identity(self) -> dict:
        return json.loads(self.target_identity_bytes.decode("utf-8"))
```

Freeze source arguments, target process/document, static transport configuration, and source-log path before the first await. Canonicalize once with `canonical_json_bytes()`, hash those exact bytes, and reconstruct fresh transport/evidence values only from the frozen bytes. Never pass the caller's original dictionary to transport.

- [ ] **Step 5: Implement cooperative lease ordering around the V5 contract**

The core function has this exact ownership order:

```python
async def _recorded_call(frozen: _FrozenCall):
    lease = await host_request("goal.dispatch.begin", frozen.begin_payload())
    transport_result = None
    transport_error = None
    try:
        transport_result = await _transport_once(frozen)
    except Exception as exc:
        transport_error = exc

    source_event = _record_transport_outcome(frozen, transport_result, transport_error)
    try:
        await host_request(
            "goal.dispatch.quiesce",
            frozen.quiescence_payload(lease, source_event),
        )
    except Exception as close_error:
        return _raise_quiescence_failure(transport_error, close_error)

    if transport_error is not None:
        raise transport_error
    return _admit_payload(transport_result)
```

`_record_transport_outcome()` must raise the exact recorder exception and skip quiescence when recording fails. `_raise_quiescence_failure()` raises a closed lifecycle error after transport success, but after a transport exception it re-raises the same exception object and retains the close error in `__context__` without overwriting an explicit `__cause__`.

- [ ] **Step 6: Preserve the exact public projection and zero-retry behavior**

Implement:

```python
async def search(query: str):
    return await _dispatch("search", "rook_tools_search", {"query": query})


async def read(name: str):
    return await _dispatch("read", "rook_tools_read", {"name": name})


async def call(name: str, arguments: dict):
    if type(arguments) is not dict:
        raise TypeError("arguments must be a dict")
    return await _dispatch("call", name, arguments)
```

For `call`, derive transport target `rook_tools_call` and transport arguments `{"name": capability_name, "arguments": frozen_source_arguments}` from the frozen descriptor. Search/read transport and source targets remain identical. Lease metadata never enters the returned payload or Rook source-event schema.

- [ ] **Step 7: Run adapter, acceptance-helper, and compilation tests**

```powershell
$rook = 'C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger'
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = @(
    "$rook/integrations/prime/rook-full/src",
    "$rook/mcp_server/src",
    "$prime/prime-agent-runtime/src"
  ) -join [IO.Path]::PathSeparator
  & $python -c "from pathlib import Path; import rlm.mcp_base as m; actual=Path(m.__file__).resolve(); expected=Path(r'$prime/prime-agent-runtime/src').resolve(); assert actual.is_relative_to(expected), (actual, expected)"
  if ($LASTEXITCODE -ne 0) { throw "Adapter test runtime import custody failed" }
  & $python -m pytest "$rook/integrations/prime/rook-full/tests/test_rook_full.py" "$rook/mcp_server/tests/test_gh_behavioral_acceptance.py" -q
  if ($LASTEXITCODE -ne 0) { throw "Adapter tests failed" }
  & $python -m py_compile "$rook/integrations/prime/rook-full/src/rook_full/__init__.py" "$rook/integrations/prime/rook-full/tests/test_rook_full.py"
  if ($LASTEXITCODE -ne 0) { throw "Adapter compilation failed" }
} finally {
  if ($null -eq $previousPythonPath) {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  } else {
    $env:PYTHONPATH = $previousPythonPath
  }
}
```

Expected: all tests pass with zero transport retries and no source schema changes.

- [ ] **Step 8: Commit the Rook adapter slice**

```powershell
git add integrations/prime/rook-full/src/rook_full/__init__.py integrations/prime/rook-full/tests/test_rook_full.py integrations/prime/rook-full/tests/fixtures/rook-goal-dispatch-wire-v1.json
git commit -m "feat: add prime-gated rook adapter"
```

**Mandatory review gate:** Confirm descriptor bytes own lease, transport, and evidence; V5 exception precedence remains exact; no public begin/quiesce functions exist; and no installer or live-runtime wiring was added.

---

### Task 6: Cross-Owner Offline Vertical And Crash Matrix

**Files:**
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts`
- Modify: `D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate/packages/coding-agent/test/goal-execution.test.ts`
- Modify: `integrations/prime/rook-full/tests/test_rook_full.py`
- Modify: both `rook-goal-dispatch-wire-v1.json` fixture copies only if the reviewed protocol itself requires correction; any fixture change requires renewed cross-owner review before tests continue.

**Interfaces:**
- Consumes: both production implementations and the exact shared wire vectors.
- Produces: one offline end-to-end claim over the unmodified adapter path and declared process-crash model.

- [ ] **Step 1: Compare the wire fixture bytes before running integration tests**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
$primeFixture = "$prime/packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json"
$rookFixture = 'C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger/integrations/prime/rook-full/tests/fixtures/rook-goal-dispatch-wire-v1.json'
$primeHash = (Get-FileHash $primeFixture -Algorithm SHA256).Hash
$rookHash = (Get-FileHash $rookFixture -Algorithm SHA256).Hash
if ($primeHash -ne $rookHash) { throw "Prime/Rook dispatch fixture mismatch" }
$primeHash
```

Record the shared hash in the plan ledger.

- [ ] **Step 2: Add the full active-cell transaction test**

The Prime live-kernel test must execute one cell whose fake adapter protocol uses the fixture's exact begin and quiesce payloads. The fake transport counter increments only after begin succeeds. After kernel completion, persist the real IPython tool result through `AgentSession`, then assert one observed lease.

Execute a second cell:

```python
await goal.prepare_completion({"requested_disposition": "complete"})
await goal.complete()
try:
    await rook_full.call("gh_snapshot", {})
except RuntimeError as exc:
    post_completion_error = str(exc)
```

Assert the final call refuses before the fake transport counter changes. The test does not claim raw Python containment.

- [ ] **Step 3: Add the complete crash/failure injection matrix**

Inject at least these exact boundaries:

```text
before lease_opened persistence
after lease_opened before transport
after transport before source append
after source append before lease_quiesced
after lease_quiesced before host response
after host response before adapter return
after adapter return before toolResult persistence
after toolResult persistence before lease_observed
after completion_authorized before goal_terminalized
after goal_terminalized before host response
```

For each prefix, restart from the session file and assert the recovery table from the specification. No case may automatically replay transport, source append, quiescence, observation, or completion.

- [ ] **Step 4: Mutation-test the reviewer-required causal invariants**

Temporarily make each mutation separately and prove focused tests fail, then restore production bytes:

1. Permit `getBranch()` membership without requiring `quiescedEntryId` before the tool-result entry. The sibling/reverse-order tests must fail.
2. Observe every quiesced lease when one matching lease remains open. The mixed multi-lease test must fail.
3. Mark a host request active whenever any execution exists, without comparing the comm parent ID. The old-detached-task-during-new-cell test must fail.
4. Replace the persisted goal-entry ID comparison with a numeric counter or current in-memory goal check. The stale-epoch completion and legacy-byte tests must fail.

Record the exact failing test counts; verify `git diff` shows no remaining mutation.

- [ ] **Step 5: Run both focused seams and builds**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test -- test/goal-execution.test.ts test/kernel-host-request-context.test.ts test/kernel-goal-dispatch-skill.test.ts test/kernel-goal-skill.test.ts test/agent-session-recursion.test.ts test/suite/agent-session-goal.test.ts
npm run build

cd C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger
$rook = 'C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = @(
    "$rook/integrations/prime/rook-full/src",
    "$rook/mcp_server/src",
    "$prime/prime-agent-runtime/src"
  ) -join [IO.Path]::PathSeparator
  & $python -m pytest integrations/prime/rook-full/tests/test_rook_full.py mcp_server/tests/test_gh_behavioral_acceptance.py -q
  if ($LASTEXITCODE -ne 0) { throw "Rook focused tests failed" }
  & $python -m py_compile integrations/prime/rook-full/src/rook_full/__init__.py integrations/prime/rook-full/tests/test_rook_full.py
  if ($LASTEXITCODE -ne 0) { throw "Rook adapter compilation failed" }
} finally {
  if ($null -eq $previousPythonPath) {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  } else {
    $env:PYTHONPATH = $previousPythonPath
  }
}
```

Expected: both focused seams and both builds/compilations pass without live contact.

- [ ] **Step 6: Run broader regression suites**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
Set-Location "$prime/packages/coding-agent"
npm test

cd C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger
$rook = 'C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = @(
    "$rook/integrations/prime/rook-full/src",
    "$rook/mcp_server/src",
    "$prime/prime-agent-runtime/src"
  ) -join [IO.Path]::PathSeparator
  & $python -m pytest mcp_server/tests -m "not requires_rhino" --ignore=mcp_server/tests/test_dspy_integration.py --ignore=mcp_server/tests/test_e2e_agents.py -q
  if ($LASTEXITCODE -ne 0) { throw "Rook broad offline suite failed" }
} finally {
  if ($null -eq $previousPythonPath) {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  } else {
    $env:PYTHONPATH = $previousPythonPath
  }
}
```

The two ignored modules explicitly perform provider or live Rhino contact and are outside this offline slice. Record exact pass/fail/skip/warning counts. Any failure not already present at the two baselines must be resolved or independently proven unrelated before proceeding.

- [ ] **Step 7: Commit any integration-test-only corrections separately**

If Task 6 required test-only additions, commit them in their owning repository without squashing production commits:

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime add packages/coding-agent/test
git -C $prime commit -m "test: qualify goal dispatch terminalization"

git -C C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger add integrations/prime/rook-full/tests
git -C C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger commit -m "test: qualify prime rook dispatch boundary"
```

Skip a repository's commit when its worktree has no changes.

**Mandatory review gate:** Review all persisted prefixes, mutation-test evidence, fixture parity, full-suite results, and the exact bounded claim before writing the report.

---

### Task 7: Evidence-Led Qualification Report And Final Reconciliation

**Files:**
- Create: `docs/superpowers/reports/2026-08-17-prime-goal-terminalization-dispatch-gate-qualification.md`
- Modify: `docs/superpowers/plans/2026-08-17-prime-goal-terminalization-dispatch-gate.md`

**Interfaces:**
- Consumes: reviewed Prime/Rook commits, test transcripts, fixture hash, mutation results, and clean-worktree verification.
- Produces: a durable qualification decision with no deployment or semantic-checkpoint overclaim.

- [ ] **Step 1: Write the report from retained command output**

Use these sections:

```markdown
# Prime Goal Terminalization And Rook Dispatch Gate Qualification

## Exact Scope And Baselines
## Implemented Owners
## Prime Causal Results
## Rook Adapter Results
## Cross-Owner Wire Custody
## Persistence And Rehydration Matrix
## Mutation Evidence
## Regression Results
## Explicitly Unqualified Boundaries
## Decision
```

The decision may claim only:

> On the unmodified durable `rook_full` adapter path, Prime admits Rook transport through persisted goal-scoped cooperative leases, terminalizes an authorized goal at one Prime-owned persistence linearization point, recovers consistently from the declared process-crash cases, and refuses later same-goal adapter calls before transport.

- [ ] **Step 2: Reconcile exact repository scope**

```powershell
$primeRoot = 'D:/prime-agent'
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime status --short
git -C $prime diff --check
git -C $prime log --oneline c98941a2a5cf40faecf9b4648ac3c304abf48fd3..HEAD
if ((git -C $primeRoot rev-parse HEAD) -ne 'c98941a2a5cf40faecf9b4648ac3c304abf48fd3') {
  throw "Prime primary checkout moved"
}
if ((git -C $primeRoot status --short)) { throw "Prime primary checkout changed" }

git status --short
git diff --check
git log --oneline f2d67b55b6f009c962722f0ed20124fc9080943d..HEAD
```

Confirm Prime changes only the mapped Prime owners/tests and Rook changes only the adapter, tests, plan, and qualification report.

- [ ] **Step 3: Run final prohibited-surface scans**

```powershell
$prime = 'D:/prime-agent/.worktrees/prime-goal-terminalization-dispatch-gate'
git -C $prime diff --name-only c98941a2a5cf40faecf9b4648ac3c304abf48fd3..HEAD
git diff --name-only 8435758116adbfd0672ef5d5fc91a49b84002445..HEAD
rg -n "fsync|Rhino|Grasshopper|goal\.dispatch" "$prime/packages/coding-agent/src/core/goal-execution.ts" "$prime/packages/coding-agent/src/core/agent-session.ts"
rg -n "goalGeneration|terminalRecord|completion_authorized" integrations/prime/rook-full/src/rook_full/__init__.py
```

Interpretation:

- Prime may contain the internal `goal.dispatch` request names but no Rhino/Grasshopper capability schema.
- Rook adapter must contain no goal generation, authorization, terminal record, or persistence logic.
- Any `fsync` addition is a stop-condition violation.

- [ ] **Step 4: Append the execution ledger and commit the documentation**

Record exact commits, hashes, test counts, mutation failures, warnings, and the fact that no model/live contact occurred. Then:

```powershell
git add docs/superpowers/plans/2026-08-17-prime-goal-terminalization-dispatch-gate.md docs/superpowers/reports/2026-08-17-prime-goal-terminalization-dispatch-gate-qualification.md
git commit -m "docs: record goal terminalization qualification"
```

- [ ] **Step 5: Stop before publication or deployment**

Do not push, open a PR, merge, package, deploy, start Rhino, start MCP, or run a model. Present both clean worktrees, commit ranges, verification counts, fixture hash, and qualification decision for independent final review.

**Mandatory final review gate:** Independently verify specification coverage, both repository diffs, all test results, fixture byte parity, failure-prefix behavior, and every explicit non-claim before any publication decision.

---

## Plan Self-Review Checklist

- [ ] Every requirement in the approved design maps to a task and causal test.
- [ ] Prime and Rook ownership is singular at every handoff.
- [ ] Every safety-relevant identity is captured at origin, persisted by one owner, and carried explicitly; no generalized custody framework was added.
- [ ] All Prime edits and tests run from the dedicated linked worktree; branch-local Python import and offline JavaScript dependency custody are proven.
- [ ] An old detached request released during a newer active cell retains the old comm parent and cannot borrow the newer execution.
- [ ] `GoalUsageEpoch` is the exact latest active-branch `thread_goal_state` entry ID, changes only after successful persistence, and never enters serialized `GoalState` bytes.
- [ ] `lease_quiesced` must precede the exact tool-result entry on the same branch.
- [ ] Sibling branches and late second leases are rejected causally.
- [ ] Configured terminalization uses one persisted terminal record; unconfigured behavior is unchanged.
- [ ] Recorder and exception precedence matches V5 exactly, including transport-success close failure, same-object transport re-raise, `__context__`, and explicit `__cause__` preservation.
- [ ] One frozen descriptor owns lease, transport, and evidence values.
- [ ] The two wire fixtures are byte-identical and consumed by real tests on both sides.
- [ ] No task introduces live contact, deployment, a semantic checkpoint, hostile-Python containment, or stronger durability language.
- [ ] Every implementation task ends in an independently reviewable commit.
- [ ] No placeholders, provisional APIs, or unowned production decisions remain.
