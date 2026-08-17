# Prime Goal Terminalization And Rook Dispatch Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify an opt-in Prime goal terminalization path that admits every promoted `rook_full` call through persisted goal-scoped leases, observes results through persisted IPython ancestry, and permanently closes the admitted Rook path when an authorized goal completes.

**Architecture:** Prime owns one persisted execution-state controller beside `GoalState`; the kernel supplies host-owned active-execution identity, `AgentSession` correlates persisted tool results, and one terminal record linearizes goal completion plus gate closure. Rook owns a promoted payload-first `rook_full` adapter that freezes each call once and executes `begin -> transport -> source record -> quiesce`; both repositories consume a byte-identical offline wire fixture, while fake transports and fault injection qualify the complete boundary without Rhino, MCP, a model, or the network.

**Tech Stack:** TypeScript 5.7, Node.js 22.8+, Vitest 4, Prime `AgentSession`/`SessionManager`/IPython kernel, Python 3.10+, pytest, MCP Python SDK test doubles, Rook `gh_behavioral_acceptance` custody helpers, PowerShell verification.

## Global Constraints

- Approved design: `docs/superpowers/specs/2026-08-17-prime-goal-terminalization-dispatch-gate-design.md`, SHA-256 `537FB29C8508AEB86F4249F9405B8AE00435F63DD48EE52E9657EDCE837A0C68`.
- Rook implementation baseline: `8435758116adbfd0672ef5d5fc91a49b84002445` plus the reviewed architecture documents on this branch.
- Prime architecture baseline: `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`. Task 0 must first cherry-pick the already-qualified structured-error commit `30a6621bc` and prove its two file blobs match exactly; do not pull the unrelated intervening Prime history.
- Work in the existing isolated Rook worktree and a fresh `codex/prime-goal-terminalization-dispatch-gate` Prime branch; do not touch either primary checkout.
- Use TDD for every production change. Record the causal RED before the minimal GREEN implementation.
- Prime is the sole owner of goal identity, generation, execution-gate state, transition persistence, terminalization, and rehydration.
- Rook is the sole owner of `rook_full.search/read/call`, target/argument freezing, MCP transport, payload projection, structured failure evidence, and source-log custody.
- Use `SessionManager.appendCustomEntryWithRollback()` as the only new persistence primitive. Do not add `fsync`, a database, a second journal, or a power-loss durability claim.
- The linearization point is successful persistence through Prime's established session persistence contract.
- Qualify only the unmodified durable adapter path. Direct `rlm.host_request`, adapter monkeypatching, and raw transport remain explicit IPython-containment gaps.
- Preserve generic Prime detached host-request fallback. Reject that fallback only for `goal.dispatch.begin` by requiring an active execution context.
- Require persisted same-branch ancestry `lease_opened -> lease_quiesced -> toolResult` before `lease_observed`. Timestamps are never causal evidence.
- A matching `toolResult -> lease_quiesced` order is permanently `recovery_required`; later quiescence cannot repair it.
- Do not implement the semantic checkpoint, PlanGraph, Worker, Reviewer, policy routing, installer integration, automatic skill discovery, deployment, or live qualification.
- Do not change Rook MCP schemas, Rhino/Grasshopper handlers, receipts, fenced snapshots, provider adapters, or prior campaign evidence.
- Public model-facing Rook API remains exactly `rook_full.search`, `rook_full.read`, and `rook_full.call`.
- All qualification is offline with fake transport and session fixtures. Model, provider, Rhino, Grasshopper, Rook MCP, deployment, and network contact are forbidden.
- Stop for renewed design review if implementation requires moving Rook transport into Prime, remote Rook revocation, a distributed commit protocol, custom durability machinery, error-text parsing, receipt changes, a second goal orchestrator, or hostile-Python containment claims.

---

## File And Ownership Map

### Prime repository: `D:/prime-agent`

| File | Change | Sole responsibility |
|---|---|---|
| `prime-agent-runtime/src/rlm/mcp_base.py` | Adopt exact qualified commit `30a6621bc` | Preserve structured MCP failure results required by the V5 adapter contract. |
| `prime-agent-runtime/test/test_mcp_base.py` | Adopt exact qualified commit `30a6621bc` | Preserve the 22-assertion structured-error qualification seam. |
| `packages/coding-agent/src/core/goal-execution.ts` | Create | Closed execution records, replay, lease state machine, completion authorization, terminalization, and closed error codes. |
| `packages/coding-agent/src/core/goals.ts` | Modify | Public completion-preparation response types and serialization only; existing unconfigured goal behavior remains intact. |
| `packages/coding-agent/src/core/kernel/index.ts` | Modify | Host-owned active execution context, including IPython tool-call and kernel execution identities. |
| `packages/coding-agent/src/core/tools/ipython.ts` | Modify | Pass the model tool-call identity into `KernelManager.execute()`. |
| `packages/coding-agent/src/core/agent-session.ts` | Modify | Optional controller activation, host-handler wiring, tool-result observation, goal lifecycle hooks, and terminal record adoption. |
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
| Qualified structured MCP failure prerequisite | Task 0 |
| Failure and cooperative-containment model | Global constraints; Tasks 5, 6, and 7 |
| Existing ownership and selected owners | File map; Tasks 1 through 5 |
| Conditional activation and legacy compatibility | Tasks 3 and 4 |
| Prime execution state and persisted transitions | Task 1 |
| Active execution identity and detached fallback | Task 2 |
| Lease opening, quiescence, result observation, and concurrency | Tasks 1, 2, 3, 5, and 6 |
| Pre-completion authorization and invalidation | Tasks 1 and 4 |
| Single-record terminalization | Tasks 1 and 4 |
| Recovery table and no-replay behavior | Tasks 1, 4, and 6 |
| Payload-first adapter promotion and failure precedence | Task 5 |
| Closed host-request admission and error codes | Tasks 1, 2, 3, and 5 |
| Prime, adapter, persistence, and boundary causal tests | Tasks 1 through 6 |
| Production exclusions, stop conditions, and bounded adoption claim | Global constraints and Task 7 |

---

### Task 0: Restore The Qualified Structured MCP Error Prerequisite

**Files:**
- Modify by exact cherry-pick: `D:/prime-agent/prime-agent-runtime/src/rlm/mcp_base.py`
- Modify by exact cherry-pick: `D:/prime-agent/prime-agent-runtime/test/test_mcp_base.py`

**Interfaces:**
- Consumes: Prime architecture baseline `c98941a2a5cf40faecf9b4648ac3c304abf48fd3` and reviewed commit `30a6621bc`.
- Produces: `McpToolError.structured_content` with unchanged text/exception behavior for Task 5; no coding-agent lifecycle change.

- [ ] **Step 1: Create the isolated Prime implementation branch at the audited baseline**

```powershell
git -C D:/prime-agent status --short
git -C D:/prime-agent switch -c codex/prime-goal-terminalization-dispatch-gate c98941a2a5cf40faecf9b4648ac3c304abf48fd3
```

Expected: clean worktree on the exact audited architecture baseline.

- [ ] **Step 2: Cherry-pick only the qualified structured-error commit**

```powershell
git -C D:/prime-agent cherry-pick 30a6621bc
```

Do not merge `fork/main`, `origin/main`, or the intervening Prime history. If cherry-pick conflicts, abort it and stop for continuity review.

- [ ] **Step 3: Verify exact source and test blob custody**

```powershell
$paths = @(
  'prime-agent-runtime/src/rlm/mcp_base.py',
  'prime-agent-runtime/test/test_mcp_base.py'
)
foreach ($path in $paths) {
  $reviewed = git -C D:/prime-agent rev-parse "30a6621bc:$path"
  $current = git -C D:/prime-agent rev-parse "HEAD:$path"
  if ($reviewed -ne $current) { throw "structured-error blob mismatch: $path" }
}
```

- [ ] **Step 4: Reproduce the qualified runtime test seam without provider contact**

```powershell
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python -m pytest D:/prime-agent/prime-agent-runtime/test/test_mcp_base.py -q
```

Expected: all structured MCP runtime tests pass with no network entry.

- [ ] **Step 5: Record the cherry-pick identity and stop for prerequisite review**

```powershell
git -C D:/prime-agent log -1 --oneline
git -C D:/prime-agent status --short
git -C D:/prime-agent diff --check c98941a2a5cf40faecf9b4648ac3c304abf48fd3..HEAD
```

**Mandatory review gate:** Confirm only the two qualified runtime files changed, both blobs equal `30a6621bc`, and no unrelated upstream Prime behavior entered the implementation branch.

---

### Task 1: Prime Persisted Goal Execution State Machine

**Files:**
- Create: `D:/prime-agent/packages/coding-agent/src/core/goal-execution.ts`
- Create: `D:/prime-agent/packages/coding-agent/test/goal-execution.test.ts`
- Modify: `D:/prime-agent/packages/coding-agent/src/index.ts`

**Interfaces:**
- Consumes: `SessionManager.appendCustomEntryWithRollback()`, `SessionManager.getBranch()`, `GoalState`, injected clock/ID functions, and an injected `GoalCompletionAdmissionController`.
- Produces: `GoalExecutionController`, `GoalCompletionAdmissionController`, `GoalExecutionError`, closed wire validators, and `GOAL_EXECUTION_CUSTOM_TYPE` for Tasks 3 and 4.

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
] as const;
```

Use an actual temporary `SessionManager`, a deterministic `now()` sequence, and deterministic IDs. Assert branch entry IDs and parent ancestry, not timestamps.

- [ ] **Step 2: Run the focused RED suite**

Run:

```powershell
cd D:/prime-agent/packages/coding-agent
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
  discreteUsageEpoch: number;
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
  discreteUsageEpoch: number;
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
    discreteUsageEpoch: number;
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

Implement exact methods:

```typescript
initializeGoal(goal: GoalState): GoalExecutionState;
beginDispatch(descriptor: GoalDispatchDescriptor, execution: ActiveIpythonExecutionIdentity, goal: GoalState): Promise<GoalDispatchLeaseResponse>;
quiesceDispatch(input: GoalDispatchQuiescenceRequest): Promise<GoalDispatchQuiescedResponse>;
observePersistedToolResult(input: { entryId: string; ipythonToolCallId: string }): Promise<void>;
prepareCompletion(input: { candidate: Record<string, unknown>; goal: GoalState }): Promise<GoalCompletionPrepared>;
abortPendingAuthorization(reason: string): Promise<void>;
terminalize(input: { goal: GoalState; completionTime: number }): Promise<GoalState>;
snapshot(): Readonly<GoalExecutionState>;
```

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
it("discrete usage change aborts authorization persistently");
it("terminal write failure leaves authorization pending and goal active");
it("terminal record closes gate and consumes authorization once");
it("lost terminal response followed by retry returns duplicate_completion");
it("new goal generation cannot inherit prior leases or authorization");
```

The terminal record contains the complete next `GoalState` and closed gate. No second `thread_goal_state` append occurs on the configured terminal path.

- [ ] **Step 6: Run the complete controller suite and build type check**

Run:

```powershell
cd D:/prime-agent/packages/coding-agent
npm test -- test/goal-execution.test.ts
npm run build
```

Expected: all focused tests pass; build exits `0`.

- [ ] **Step 7: Commit the Prime state-machine slice**

```powershell
git -C D:/prime-agent add packages/coding-agent/src/core/goal-execution.ts packages/coding-agent/src/index.ts packages/coding-agent/test/goal-execution.test.ts
git -C D:/prime-agent commit -m "feat: add persisted goal execution state"
```

**Mandatory review gate:** Independently review replay ordering, sibling-branch rejection, mixed multi-lease behavior, persistence-before-memory, and the absence of transport or Rook semantics from this controller.

---

### Task 2: Prime Active IPython Execution Custody

**Files:**
- Modify: `D:/prime-agent/packages/coding-agent/src/core/kernel/index.ts`
- Modify: `D:/prime-agent/packages/coding-agent/src/core/tools/ipython.ts`
- Create: `D:/prime-agent/packages/coding-agent/test/kernel-host-request-context.test.ts`
- Modify: `D:/prime-agent/packages/coding-agent/test/agent-session-recursion.test.ts`

**Interfaces:**
- Consumes: the existing kernel `ActiveExecution`, `ExecuteOptions`, generic `HostRequestHandler`, and IPython tool `toolCallId`.
- Produces: a second, host-owned `HostRequestContext` argument. Task 3 uses it to admit `goal.dispatch.begin`; existing handlers continue receiving `cellSourceCode` in their payload for compatibility.

- [ ] **Step 1: Write RED tests for active and detached requests**

The tests must prove:

```typescript
it("passes tool call and kernel execution identities during an active cell");
it("marks a detached request inactive while preserving last-cell source fallback");
it("does not synthesize a tool-call identity for direct kernel execute without one");
it("keeps generic detached rlm host requests working");
```

For the detached case, schedule `asyncio.create_task(rlm.host_request("test.detached", {"value": 1}))`, let the originating cell become idle, then release the task. Assert `context.activeExecution === false` while the legacy payload still contains `cellSourceCode`.

- [ ] **Step 2: Run the focused RED tests**

```powershell
cd D:/prime-agent/packages/coding-agent
npm test -- test/kernel-host-request-context.test.ts test/agent-session-recursion.test.ts
```

Expected: the new context assertions fail because the handler currently receives only one payload argument and `ExecuteOptions` has no tool-call identity.

- [ ] **Step 3: Add host-owned execution context without changing generic fallback**

In `kernel/index.ts`, add:

```typescript
export interface HostRequestContext {
  activeExecution: boolean;
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

At host dispatch, keep the existing payload behavior and supply the context separately:

```typescript
const execution = this.activeExecution;
const cellSourceCode = execution?.code ?? this.lastCellCode;
return handler(
  Object.assign({}, data, { cellSourceCode }),
  {
    activeExecution: execution !== undefined,
    cellSourceCode,
    ipythonToolCallId: execution?.opts.ipythonToolCallId,
    kernelExecutionId: execution?.requestMsgId,
  },
);
```

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
cd D:/prime-agent/packages/coding-agent
npm test -- test/kernel-host-request-context.test.ts test/agent-session-recursion.test.ts
npm run build
```

Expected: active context, detached context, and existing recursion tests pass.

- [ ] **Step 6: Commit the Prime execution-context slice**

```powershell
git -C D:/prime-agent add packages/coding-agent/src/core/kernel/index.ts packages/coding-agent/src/core/tools/ipython.ts packages/coding-agent/test/kernel-host-request-context.test.ts packages/coding-agent/test/agent-session-recursion.test.ts
git -C D:/prime-agent commit -m "feat: expose active ipython host context"
```

**Mandatory review gate:** Confirm dispatch identity is host-owned, detached fallback is preserved generically, and no model-supplied payload field can make an inactive execution active.

---

### Task 3: AgentSession Dispatch Lease And Tool-Result Observation Wiring

**Files:**
- Modify: `D:/prime-agent/packages/coding-agent/src/core/agent-session.ts`
- Create: `D:/prime-agent/packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json`
- Modify: `D:/prime-agent/packages/coding-agent/test/suite/agent-session-goal.test.ts`

**Interfaces:**
- Consumes: `GoalExecutionController`, `HostRequestContext`, the Prime-side wire fixture, and persisted `toolResult` messages.
- Produces: optional configured handlers `goal.dispatch.begin` and `goal.dispatch.quiesce`, persisted result observation, and an AgentSession-owned controller instance.

- [ ] **Step 1: Freeze the Prime wire fixture and write handler RED tests**

Add the exact fixture from the plan's cross-owner wire section. Tests must parse it strictly and prove:

```typescript
it("does not register dispatch handlers without an admission controller");
it("rehydrates a configured active goal without compatible execution state as recovery_required");
it("rejects begin when HostRequestContext is inactive");
it("rejects begin when the active context lacks an ipython tool-call identity");
it("binds begin to host-owned tool-call and kernel execution identities");
it("quiesce may arrive after the cell becomes inactive");
it("unknown and open request fields refuse before transition state access");
```

- [ ] **Step 2: Run the AgentSession RED cases**

```powershell
cd D:/prime-agent/packages/coding-agent
npm test -- test/suite/agent-session-goal.test.ts
```

Expected: configured handler assertions fail because `AgentSessionConfig` has no completion controller and no dispatch handlers exist.

- [ ] **Step 3: Add opt-in controller construction and closed handlers**

Add to `AgentSessionConfig`:

```typescript
goalCompletionAdmissionController?: GoalCompletionAdmissionController;
```

When present, construct one `GoalExecutionController` owned by `AgentSession`. When absent, do not construct it and do not register lease or preparation handlers.

Register exact internal handlers:

```typescript
handlers["goal.dispatch.begin"] = async (payload, context) => {
  if (!context.activeExecution || !context.ipythonToolCallId || !context.kernelExecutionId) {
    throw new GoalExecutionError("execution_not_active");
  }
  return await this._goalExecution!.beginDispatch(validateDispatchHostPayload(payload), {
    ipythonToolCallId: context.ipythonToolCallId,
    kernelExecutionId: context.kernelExecutionId,
  }, this.goalState);
};

handlers["goal.dispatch.quiesce"] = async (payload) =>
  await this._goalExecution!.quiesceDispatch(validateQuiescenceHostPayload(payload));
```

`rlm.host_request()` flattens the caller payload with `type`, and the kernel adds the compatibility-only `cellSourceCode`. Each validator first requires its exact `type`, removes only those two bridge-owned fields, and then validates the remaining closed descriptor or quiescence shape. Validation rejects every other unknown field and wrong scalar type before reading current goal or gate state; neither `type` nor `cellSourceCode` contributes authorization.

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

- [ ] **Step 6: Run focused AgentSession and controller tests**

```powershell
cd D:/prime-agent/packages/coding-agent
npm test -- test/goal-execution.test.ts test/suite/agent-session-goal.test.ts
npm run build
```

Expected: all tests pass, including the reviewer's sibling-branch and late second-lease refinements.

- [ ] **Step 7: Commit the Prime dispatch-wiring slice**

```powershell
git -C D:/prime-agent add packages/coding-agent/src/core/agent-session.ts packages/coding-agent/test/suite/agent-session-goal.test.ts packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json
git -C D:/prime-agent commit -m "feat: gate goal-scoped dispatch leases"
```

**Mandatory review gate:** Confirm result observation follows the exact persisted tool-result entry on the same branch and that every mixed-cell lease must quiesce before that entry.

---

### Task 4: Prime Completion Preparation And Terminalization

**Files:**
- Modify: `D:/prime-agent/packages/coding-agent/src/core/goals.ts`
- Modify: `D:/prime-agent/packages/coding-agent/src/core/agent-session.ts`
- Modify: `D:/prime-agent/packages/coding-agent/skills/goal/src/goal/__init__.py`
- Modify: `D:/prime-agent/packages/coding-agent/test/suite/agent-session-goal.test.ts`
- Create: `D:/prime-agent/packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts`

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
it("steering supersession and discrete usage changes abort pending authorization");
it("terminal persistence failure leaves authorization pending and goal active");
it("successful terminal persistence installs complete goal and closed gate");
it("same-cell rook begin after goal.complete refuses before fake transport");
it("lost completion response cannot append a second terminal record");
it("rehydration derives complete goal and closed gate from one terminal record");
```

- [ ] **Step 2: Run the completion RED suites**

```powershell
cd D:/prime-agent/packages/coding-agent
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
    completionTime: Date.now(),
  });
  this._installPersistedTerminalGoal(completed);
  return goalHostResponse(this._goalState, true);
}
```

Register `goal.prepare_completion` only when the execution controller exists. Keep `goal.get/create/complete` registration under the existing `includeGoals` boundary and have each kernel handler return `await Promise.resolve(this.handleGoalHostRequest(type, payload))` so legacy synchronous and configured asynchronous results share one bridge.

`_installPersistedTerminalGoal()` updates memory, accounting, queue state, and emitted UI state without appending another goal record. The controller has already persisted the sole terminal record.

- [ ] **Step 5: Connect invalidation hooks**

Add `discreteUsageEpoch: number` to `GoalState`, initialize and normalize it to `0` for old sessions, and increment it in the same persisted goal-state update that accounts each accepted assistant message. The execution controller reads that persisted value when opening a lease, authorizing completion, and terminalizing; rehydration derives the current value from the active persisted `GoalState` rather than inventing an execution transition. Call persisted authorization abort before admitted steering, goal supersession, clear/pause, or resume changes the bound goal. Do not compare continuously changing `timeUsedSeconds` for authorization identity; check only the explicit deadline and completion-time budget predicate.

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
cd D:/prime-agent/packages/coding-agent
npm test -- test/goal-execution.test.ts test/kernel-host-request-context.test.ts test/kernel-goal-dispatch-skill.test.ts test/kernel-goal-skill.test.ts test/agent-session-recursion.test.ts test/suite/agent-session-goal.test.ts
npm run build
```

Expected: all focused tests pass; existing unconfigured goal and detached-recursion behavior remains green.

- [ ] **Step 8: Commit the Prime terminalization slice**

```powershell
git -C D:/prime-agent add packages/coding-agent/src/core/goals.ts packages/coding-agent/src/core/agent-session.ts packages/coding-agent/skills/goal/src/goal/__init__.py packages/coding-agent/test/suite/agent-session-goal.test.ts packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts
git -C D:/prime-agent commit -m "feat: terminalize authorized goals atomically"
```

**Mandatory review gate:** Confirm one persisted terminal record owns both complete goal and closed gate, no configured path mutates memory before persistence, and unconfigured Prime behavior is byte-contract compatible.

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

- [ ] **Step 3: Run the adapter RED suite**

```powershell
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python -m pytest integrations/prime/rook-full/tests/test_rook_full.py -q
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
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python -m pytest integrations/prime/rook-full/tests/test_rook_full.py mcp_server/tests/test_gh_behavioral_acceptance.py -q
& $python -m py_compile integrations/prime/rook-full/src/rook_full/__init__.py integrations/prime/rook-full/tests/test_rook_full.py
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
- Modify: `D:/prime-agent/packages/coding-agent/test/kernel-goal-dispatch-skill.test.ts`
- Modify: `D:/prime-agent/packages/coding-agent/test/goal-execution.test.ts`
- Modify: `integrations/prime/rook-full/tests/test_rook_full.py`
- Modify: both `rook-goal-dispatch-wire-v1.json` fixture copies only if the reviewed protocol itself requires correction; any fixture change requires renewed cross-owner review before tests continue.

**Interfaces:**
- Consumes: both production implementations and the exact shared wire vectors.
- Produces: one offline end-to-end claim over the unmodified adapter path and declared process-crash model.

- [ ] **Step 1: Compare the wire fixture bytes before running integration tests**

```powershell
$primeFixture = 'D:/prime-agent/packages/coding-agent/test/fixtures/rook-goal-dispatch-wire-v1.json'
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

- [ ] **Step 4: Mutation-test the two reviewer-required causal invariants**

Temporarily make each mutation separately and prove focused tests fail, then restore production bytes:

1. Permit `getBranch()` membership without requiring `quiescedEntryId` before the tool-result entry. The sibling/reverse-order tests must fail.
2. Observe every quiesced lease when one matching lease remains open. The mixed multi-lease test must fail.

Record the exact failing test counts; verify `git diff` shows no remaining mutation.

- [ ] **Step 5: Run both focused seams and builds**

```powershell
cd D:/prime-agent/packages/coding-agent
npm test -- test/goal-execution.test.ts test/kernel-host-request-context.test.ts test/kernel-goal-dispatch-skill.test.ts test/kernel-goal-skill.test.ts test/agent-session-recursion.test.ts test/suite/agent-session-goal.test.ts
npm run build

cd C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python -m pytest integrations/prime/rook-full/tests/test_rook_full.py mcp_server/tests/test_gh_behavioral_acceptance.py -q
& $python -m py_compile integrations/prime/rook-full/src/rook_full/__init__.py integrations/prime/rook-full/tests/test_rook_full.py
```

Expected: both focused seams and both builds/compilations pass without live contact.

- [ ] **Step 6: Run broader regression suites**

```powershell
cd D:/prime-agent/packages/coding-agent
npm test

cd C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python -m pytest mcp_server/tests -m "not requires_rhino" --ignore=mcp_server/tests/test_dspy_integration.py --ignore=mcp_server/tests/test_e2e_agents.py -q
```

The two ignored modules explicitly perform provider or live Rhino contact and are outside this offline slice. Record exact pass/fail/skip/warning counts. Any failure not already present at the two baselines must be resolved or independently proven unrelated before proceeding.

- [ ] **Step 7: Commit any integration-test-only corrections separately**

If Task 6 required test-only additions, commit them in their owning repository without squashing production commits:

```powershell
git -C D:/prime-agent add packages/coding-agent/test
git -C D:/prime-agent commit -m "test: qualify goal dispatch terminalization"

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
git -C D:/prime-agent status --short
git -C D:/prime-agent diff --check
git -C D:/prime-agent log --oneline c98941a2a5cf40faecf9b4648ac3c304abf48fd3..HEAD

git status --short
git diff --check
git log --oneline f2d67b55b6f009c962722f0ed20124fc9080943d..HEAD
```

Confirm Prime changes only the mapped Prime owners/tests and Rook changes only the adapter, tests, plan, and qualification report.

- [ ] **Step 3: Run final prohibited-surface scans**

```powershell
git -C D:/prime-agent diff --name-only c98941a2a5cf40faecf9b4648ac3c304abf48fd3..HEAD
git diff --name-only 8435758116adbfd0672ef5d5fc91a49b84002445..HEAD
rg -n "fsync|Rhino|Grasshopper|goal\.dispatch" D:/prime-agent/packages/coding-agent/src/core/goal-execution.ts D:/prime-agent/packages/coding-agent/src/core/agent-session.ts
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
- [ ] `lease_quiesced` must precede the exact tool-result entry on the same branch.
- [ ] Sibling branches and late second leases are rejected causally.
- [ ] Configured terminalization uses one persisted terminal record; unconfigured behavior is unchanged.
- [ ] Recorder and exception precedence matches V5 exactly.
- [ ] One frozen descriptor owns lease, transport, and evidence values.
- [ ] The two wire fixtures are byte-identical and consumed by real tests on both sides.
- [ ] No task introduces live contact, deployment, a semantic checkpoint, hostile-Python containment, or stronger durability language.
- [ ] Every implementation task ends in an independently reviewable commit.
- [ ] No placeholders, provisional APIs, or unowned production decisions remain.
