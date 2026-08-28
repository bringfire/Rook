# RookChat Prime Primary Backend Slices 1-2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicitly selected Prime-backed text path to RookChat, using one saved Prime RPC session per panel conversation while preserving single-flight completion, durable target/session custody, cancellation, model selection, and the unchanged default `ChatRunner` path.

**Architecture:** Prime gains one generic `prompt_and_wait` RPC command implemented from the same headless-turn sequence already used by ACP. The Python chat service becomes a narrow broker with an atomic per-conversation registry and ephemeral owned Prime processes; the existing C# panel keeps rendering the current NDJSON projection and learns only the new settled cancellation lifecycle. `ChatRunner` remains the product default while the Prime path is explicitly opt-in through Slice 2.

**Tech Stack:** TypeScript 7/Vitest (Prime), Python 3.11/aiohttp/pytest (Rook broker), C# net48/Eto/xUnit (RookChat panel), LF-delimited JSON RPC/NDJSON, Windows process ownership.

**Spec:** `docs/superpowers/specs/2026-08-26-rookchat-prime-primary-backend-slice-0-contract.md`

## Global Constraints

- This plan is unimplemented and requires independent review before any implementation step is executed.
- Prime implementation starts from exact commit `739400844f8f3f280414b0c7b9c65797208815d3` in a new worktree; the qualified `rook-upstream-evaluation` worktree remains read-only.
- Rook implementation starts from the independently reviewed plan commit in a new `codex/` worktree created with `superpowers:using-git-worktrees`.
- One RookChat conversation maps to one saved Prime session and one immutable target tuple: Rhino PID, Rhino process-start UTC ticks, and document runtime serial.
- Prime is the only model, provider, transcript, retry, compaction, and model-loop owner. The Python broker translates lifecycle and transport only.
- Raw `agent_end`, HTTP stream closure, quiet time, process liveness, and message counts never settle a product prompt.
- The first vertical is single-flight and text-only. Images, steering, follow-up, IPython, Rook tools, web search, UI blocks, worker-first execution, goals, and model-facing skills are absent.
- Initial Prime launch discovery is disabled with `--no-tools --no-extensions --no-skills --no-context-files --no-prompt-templates`.
- The only new Prime failure object is for `prompt_and_wait`; existing RPC commands retain their current string-error wire shape.
- `prompt_and_wait` failure codes are closed to `admission_failed`, `execution_failed`, `inspection_failed`, `settlement_unknown`, and `protocol_failed`, with a separate human-readable message.
- Abort correlation is broker-local. Prime's existing `abort` command and response are unchanged.
- The broker defaults remain: 10 resident Prime children, 30-minute idle retirement, and one 10-second global service-shutdown drain.
- The durable registry contains no process IDs used for ownership, process handles, pipes, pending commands, credentials, messages, or model output.
- An absent `ROOK_CHAT_BACKEND` or `ROOK_CHAT_BACKEND=legacy` selects the existing default path. `ROOK_CHAT_BACKEND=prime` explicitly selects the new path. Product-default cutover remains Slice 6 work after packaging and live qualification. The two backends never run the same turn.
- No provider, model, Rhino, Grasshopper, Rook mutation, or network contact is part of implementation qualification.

## Closed Interfaces

### Prime `prompt_and_wait`

Command:

```json
{"id":"turn UUID","type":"prompt_and_wait","message":"user text","images":[]}
```

Success:

```json
{
  "id":"turn UUID",
  "type":"response",
  "command":"prompt_and_wait",
  "success":true,
  "data":{"outcome":"completed"}
}
```

Failure:

```json
{
  "id":"turn UUID",
  "type":"response",
  "command":"prompt_and_wait",
  "success":false,
  "error":{"code":"execution_failed","message":"prime-agent turn failed: provider refused the request"}
}
```

Only `completed` and `aborted` are successful Prime outcomes. `completed_before_abort` is a broker lifecycle reason and never appears in Prime's success enum.

Failure ownership is exact:

| Code | Owner and trigger |
|---|---|
| `protocol_failed` | Parsed `prompt_and_wait` envelope has a missing/non-string ID, missing/non-string message, non-array `images`, or unsupported field type. |
| `inspection_failed` | The pre-turn boundary or post-settlement transcript cannot be read. |
| `admission_failed` | `promptAndWait()` refuses before any post-boundary message exists and a follow-up state/transcript inspection proves the connection is idle. |
| `execution_failed` | The newest post-boundary assistant terminal message has `stopReason: "error"`; its `errorMessage` supplies the human message. |
| `settlement_unknown` | Prompt admission may have occurred but headless completion, process state, or terminal settlement cannot be proven. No caller may replay automatically. |

### Broker-local cancellation record

```python
@dataclass(frozen=True)
class PendingAbort:
    abort_request_id: str
    prompt_request_id: str
    launch_generation: int
```

The broker creates this record before sending `abort`. A later abort response is interpreted only through its own request ID lookup. If the associated prompt settles `completed` first, the broker persists `idle/completed_before_abort`, removes the pending prompt, records the abort request ID as retired for that launch generation, and ignores its later response. No new Prime correlation field is added.

### Panel NDJSON projection

The Prime path emits only these Slice 2 rows:

```text
text_delta    { content }
status        { content: "agent_segment" | "cancel_requested" }
model_update  { model, applies_to }
done          { outcome: "completed" | "completed_before_abort" }
cancelled     { outcome: "aborted" }
error         { code, content, terminal: true }
```

`agent_end` may emit `status/agent_segment`; it never emits `done`.

## File Map

### Prime worktree

- Create `packages/coding-agent/src/modes/headless-turn.ts`: compaction-safe turn boundary, post-boundary terminal inspection, and shared headless-turn settlement.
- Modify `packages/coding-agent/src/modes/acp/acp-mode.ts`: call the shared helper without changing ACP wire behavior.
- Modify `packages/coding-agent/src/modes/rpc/rpc-types.ts`: add the command, closed outcomes, and command-specific failure object.
- Modify `packages/coding-agent/src/modes/rpc/rpc-mode.ts`: validate, serialize, execute, stream, and settle `prompt_and_wait`; keep `abort` independently dispatchable.
- Modify `packages/coding-agent/src/modes/rpc/rpc-client.ts`: add `promptAndWaitSettled()` and preserve `promptAndWait(): Promise<AgentEvent[]>`, collecting events through the new terminal response instead of the first `agent_end`.
- Modify `packages/coding-agent/docs/rpc.md`: document the new command and explain that `agent_end` is not prompt settlement.
- Modify `packages/coding-agent/test/rpc-prompt-response-semantics.test.ts`: causal command, failure, continuation, event-order, and abort tests.
- Modify `packages/coding-agent/test/suite/acp-features.test.ts`: prove ACP retains existing completion/failure behavior through the shared helper.

### Rook Python worktree

- Create `mcp_server/src/rook/agent/chat/prime_rpc_protocol.py`: closed wire parsing, command IDs, response errors, and Slice 2 event projection.
- Create `mcp_server/src/rook/agent/chat/prime_registry.py`: target/model/lifecycle records, namespace lock, strict load validation, and atomic per-conversation writes.
- Create `mcp_server/src/rook/agent/chat/prime_process.py`: owned child launch, strict JSONL read/write, response correlation, generation filtering, and bounded termination.
- Create `mcp_server/src/rook/agent/chat/prime_backend.py`: resident table, lifecycle transitions, registry/process coordination, prompt streaming, cancel races, LRU retirement, and shutdown.
- Modify `mcp_server/src/rook/agent/chat/server.py`: route prime/legacy requests without sharing a turn; add explicit cancel/reopen/close behavior.
- Modify `mcp_server/src/rook/agent/chat/service_main.py`: accept the Rhino process-start fingerprint and construct the configured backend.
- Create `mcp_server/tests/fixtures/prime_rpc_fake_child.py`: deterministic JSONL child for adversarial event and process ordering.
- Create `mcp_server/tests/test_prime_rpc_protocol.py`.
- Create `mcp_server/tests/test_prime_registry.py`.
- Create `mcp_server/tests/test_prime_process.py`.
- Create `mcp_server/tests/test_prime_backend.py`.
- Modify `mcp_server/tests/test_chat_server.py`.

### Rook C# worktree

- Modify `src/Rook/UI/Chat/ChatServiceManager.cs`: pass the exact Rhino process-start UTC ticks and expose backend status.
- Modify `src/Rook/UI/Chat/AgentChatClient.cs`: stable conversation/target requests, explicit reopen/cancel/close, and new terminal fields.
- Modify `src/Rook/UI/Chat/ChatTab.cs`: allow `AgentChatTab` to defer local stop finalization while leaving `ClaudeCodeTab` unchanged.
- Modify `src/Rook/UI/Chat/AgentChatTab.cs`: retain conversation identity across service reconnect, keep the stream open during cancel, and finalize only on settled events.
- Modify `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`.
- Modify `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`.
- Create `src/Rook.Tests/UI/Chat/AgentChatPrimeLifecycleTests.cs`.

---

### Task 0: Create Hermetic Implementation Worktrees

**Files:**
- No repository file changes.
- Creates worktree: `D:/prime-agent/.worktrees/rookchat-primary-backend`
- Creates worktree: `C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend`

**Interfaces:**
- Consumes: exact Prime baseline `739400844f8f3f280414b0c7b9c65797208815d3` and the independently approved plan commit.
- Produces: branch-local Prime dependencies plus a Rook Python import environment used by every later task.

- [ ] **Step 1: Capture the independently reviewed plan commit**

Run only after the amended plan receives spot review:

```powershell
$coord = 'C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger'
$reviewedPlanCommit = (git -C $coord rev-parse HEAD).Trim()
if ((git -C $coord status --porcelain).Length -ne 0) {
    throw 'Coordinating worktree must be clean before implementation setup.'
}
$reviewedPlanCommit
```

Record this commit in the eventual qualification report; do not substitute a moving branch name.

- [ ] **Step 2: Create both dedicated implementation worktrees**

```powershell
git -C D:/prime-agent worktree add `
  D:/prime-agent/.worktrees/rookchat-primary-backend `
  -b codex/rookchat-primary-backend `
  739400844f8f3f280414b0c7b9c65797208815d3

git -C C:/UDEV/Rook worktree add `
  C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend `
  -b codex/rookchat-prime-primary-backend `
  $reviewedPlanCommit
```

Expected: both commands create new worktrees; neither historical qualification worktree is modified.

- [ ] **Step 3: Install exact Prime dependencies from the lockfile**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend
npm ci
```

Expected: `package-lock.json` remains unchanged and worktree status stays clean.

- [ ] **Step 4: Prove Node dependency resolution is branch-local**

```powershell
$prime = [IO.Path]::GetFullPath('D:/prime-agent/.worktrees/rookchat-primary-backend')
Set-Location $prime
$vitest = (& node -e "console.log(require.resolve('vitest/package.json'))").Trim()
$tsx = (& node -e "console.log(require.resolve('tsx/package.json'))").Trim()
foreach ($resolved in @($vitest, $tsx)) {
    if (-not [IO.Path]::GetFullPath($resolved).StartsWith($prime, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Node dependency resolved outside Prime worktree: $resolved"
    }
}
npx tsx -e "import './packages/coding-agent/src/modes/rpc/rpc-mode.ts'; console.log('prime-source-import-ok')"
git status --short
```

Expected: both package paths are under the new Prime worktree, the source import prints `prime-source-import-ok`, and status is empty.

- [ ] **Step 5: Prove Rook Python imports are branch-local**

```powershell
$rook = [IO.Path]::GetFullPath('C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend')
$env:PYTHONPATH = "$rook/mcp_server/src"
$env:ROOK_IMPLEMENTATION_ROOT = $rook
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -c @'
import os
from pathlib import Path
import rook
import rook.agent.chat.server
root = Path(os.environ["ROOK_IMPLEMENTATION_ROOT"]).resolve()
for module in (rook, rook.agent.chat.server):
    path = Path(module.__file__).resolve()
    if root not in path.parents:
        raise SystemExit(f"import escaped Rook worktree: {path}")
    print(path)
'@
git -C $rook status --short
```

Expected: both module paths are under the new Rook worktree and status is empty. Keep this `PYTHONPATH` for every later Python command.

- [ ] **Step 6: Record custody without committing generated dependencies**

```powershell
git -C D:/prime-agent/.worktrees/rookchat-primary-backend rev-parse HEAD
git -C D:/prime-agent/.worktrees/rookchat-primary-backend rev-parse HEAD^{tree}
git -C C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend rev-parse HEAD
git -C C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend rev-parse HEAD^{tree}
Get-FileHash D:/prime-agent/.worktrees/rookchat-primary-backend/package-lock.json -Algorithm SHA256
```

Expected: Prime HEAD is the exact baseline, Rook HEAD is the reviewed plan commit, and both worktrees are clean. Task 0 creates no commit.

### Task 1: Share Prime's Proven Headless-Turn Sequence

**Files:**
- Create: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/headless-turn.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/acp/acp-mode.ts`
- Test: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/test/suite/acp-features.test.ts`
- Test: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/test/rpc-prompt-response-semantics.test.ts`

**Interfaces:**
- Consumes: `AgentConnection.getMessages()`, `promptAndWait()`, `waitForHeadlessCompletion()`, and existing `AgentMessage` terminal fields.
- Produces: `runHeadlessTurn(connection, message, options): Promise<HeadlessTurnResult>` and `HeadlessTurnError.code` for Task 2.

- [ ] **Step 1: Add RED tests for transcript identity and terminal classification**

Add cases proving that the boundary survives copied message objects and compaction-rematerialized messages, ignores an old failed assistant message, classifies a new `stopReason: "error"` as `execution_failed`, and classifies a new `stopReason: "aborted"` as the successful `aborted` outcome.

```typescript
it("classifies only the post-boundary assistant failure", async () => {
  const connection = fakeConnection({
    before: [assistant({ timestamp: 1, stopReason: "error", errorMessage: "old" })],
    after: [
      assistant({ timestamp: 1, stopReason: "error", errorMessage: "old" }),
      assistant({ timestamp: 2, stopReason: "error", errorMessage: "new provider failure" }),
    ],
  });

  await expect(runHeadlessTurn(connection, "hello")).rejects.toMatchObject({
    code: "execution_failed",
    message: "new provider failure",
  });
});
```

- [ ] **Step 2: Run the RED tests**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run `
  test/rpc-prompt-response-semantics.test.ts `
  test/suite/acp-features.test.ts
```

Expected: failures because `headless-turn.ts` and `runHeadlessTurn` do not exist.

- [ ] **Step 3: Implement the shared helper with phase-owned failures**

Use this public surface:

```typescript
export type HeadlessTurnOutcome = "completed" | "aborted";
export type HeadlessTurnFailureCode =
  | "admission_failed"
  | "execution_failed"
  | "inspection_failed"
  | "settlement_unknown";

export interface HeadlessTurnResult {
  outcome: HeadlessTurnOutcome;
  autonomous: AgentAutonomousStatus;
}

export class HeadlessTurnError extends Error {
  constructor(
    public readonly code: HeadlessTurnFailureCode,
    message: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "HeadlessTurnError";
  }
}

export async function runHeadlessTurn(
  connection: AgentConnection,
  message: string,
  options?: AgentConnectionPromptOptions,
): Promise<HeadlessTurnResult>;
```

Implementation order is fixed:

1. Capture message identities and stable `(role, timestamp, stopReason, errorMessage)` keys.
2. Call `connection.promptAndWait()`.
3. Call `connection.waitForHeadlessCompletion()`.
4. Read the transcript again and inspect only post-boundary assistant messages.
5. Return `aborted` for `stopReason: "aborted"`, throw `execution_failed` for `stopReason: "error"`, otherwise return `completed`.

If `promptAndWait()` throws, read messages and state once. Return `admission_failed` only when there is no post-boundary message and `getState()` proves `isStreaming === false` and `isCompacting === false`; otherwise return `settlement_unknown`. A failed verification read is `settlement_unknown`, because admission can no longer be disproven. A pre- or post-turn transcript read outside that recovery branch is `inspection_failed`. A `waitForHeadlessCompletion()` exception is always `settlement_unknown`.

- [ ] **Step 4: Replace ACP's private boundary/failure helpers with the shared helper**

Keep ACP's local `AbortController`, notifications, and stop-reason mapping. Its request body becomes:

```typescript
const result = await runHeadlessTurn(
  connection,
  text,
  images.length > 0 ? { images } : undefined,
);
const meta = autonomousMeta(result.autonomous);
if (meta) {
  await ctx.client.notify(acp.methods.client.session.update, {
    sessionId: params.sessionId,
    update: { sessionUpdate: "session_info_update", _meta: meta },
  });
}
return {
  stopReason: acpStopReason({
    cancelled: abort.signal.aborted || result.outcome === "aborted",
    autonomous: result.autonomous,
  }),
};
```

Map `HeadlessTurnError` back to ACP's existing thrown error behavior. Do not expose the new RPC code object through ACP.

- [ ] **Step 5: Run focused Prime tests and build**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run `
  test/rpc-prompt-response-semantics.test.ts `
  test/suite/acp-features.test.ts
npm run build
```

Expected: both files pass and the package builds.

- [ ] **Step 6: Commit the shared Prime helper**

```powershell
git add packages/coding-agent/src/modes/headless-turn.ts `
  packages/coding-agent/src/modes/acp/acp-mode.ts `
  packages/coding-agent/test/suite/acp-features.test.ts `
  packages/coding-agent/test/rpc-prompt-response-semantics.test.ts
git commit -m "refactor: share Prime headless turn settlement"
```

### Task 2: Add the Prime-Generic `prompt_and_wait` RPC Command

**Files:**
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/rpc/rpc-types.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/rpc/rpc-mode.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/rpc/rpc-client.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/docs/rpc.md`
- Test: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/test/rpc-prompt-response-semantics.test.ts`
- Test: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/test/rpc.test.ts`

**Interfaces:**
- Consumes: `runHeadlessTurn()` and `HeadlessTurnError` from Task 1.
- Produces: the exact `prompt_and_wait` command/response schema consumed by `PrimeRpcProcess` in Task 4.

- [ ] **Step 1: Add RED wire tests for all five failure codes**

Test malformed ID/message/images as `protocol_failed`; pre-admission refusal as `admission_failed`; transcript error as `execution_failed`; transcript-read failure as `inspection_failed`; and post-admission/headless wait loss as `settlement_unknown`.

```typescript
expect(lines).toContainEqual({
  id: "turn-1",
  type: "response",
  command: "prompt_and_wait",
  success: false,
  error: { code: "execution_failed", message: "provider refused the request" },
});
```

- [ ] **Step 2: Add RED causal event-order tests**

Use the existing fake `AgentConnection` to prove:

```text
prompt_and_wait sent
-> text event emitted
-> first agent_end emitted
-> original promptAndWait resolves
-> compaction continuation emits a second agent segment
-> waitForHeadlessCompletion resolves
-> exactly one prompt_and_wait terminal response emitted
```

Also prove `abort` returns its own correlated response while `prompt_and_wait` remains pending, and prove a second prompt command uses the existing serialized prompt lane.

- [ ] **Step 3: Run the RED RPC tests**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/rpc-prompt-response-semantics.test.ts
```

Expected: failures because the command and response variants are absent.

- [ ] **Step 4: Add closed TypeScript wire types**

```typescript
export type RpcPromptAndWaitErrorCode =
  | "admission_failed"
  | "execution_failed"
  | "inspection_failed"
  | "settlement_unknown"
  | "protocol_failed";

export interface RpcPromptAndWaitError {
  code: RpcPromptAndWaitErrorCode;
  message: string;
}

export interface RpcPromptAndWaitData {
  outcome: "completed" | "aborted";
}
```

Add a required non-empty string `id` for `prompt_and_wait`. Do not change the generic string error used by existing RPC commands.

- [ ] **Step 5: Validate and dispatch without buffering ordinary events**

Add `validatePromptAndWaitCommand(parsed)` before the unsafe `RpcCommand` cast. Invalid known-command envelopes emit the command-specific `protocol_failed` object. Add `prompt_and_wait` to `promptCommandTail`, but leave `promptResponsePending` exclusive to the immediate-ack `prompt` command so streamed text and segment events remain visible while settlement is pending.

```typescript
case "prompt_and_wait": {
  const result = await runHeadlessTurn(connection, command.message, {
    images: command.images,
    source: "rpc",
  });
  return success(id, command.type, { outcome: result.outcome });
}
```

Catch `HeadlessTurnError` and emit its closed object. Unexpected exceptions from this command become `settlement_unknown`; they must not fall through to the generic string-error helper.

- [ ] **Step 6: Add a settled client method without breaking `promptAndWait()`**

Add a distinctly named settlement method:

```typescript
async promptAndWaitSettled(
  message: string,
  images?: ImageContent[],
  timeout = 60000,
): Promise<RpcPromptAndWaitData> {
  const response = await this.send({
    type: "prompt_and_wait",
    message,
    images,
  }, timeout);
  return this.getPromptAndWaitData(response);
}
```

Preserve the existing public contract exactly:

```typescript
async promptAndWait(
  message: string,
  images?: ImageContent[],
  timeout = 60000,
): Promise<AgentEvent[]> {
  const events: AgentEvent[] = [];
  const unsubscribe = this.onEvent((event) => events.push(event));
  try {
    await this.promptAndWaitSettled(message, images, timeout);
    return events;
  } finally {
    unsubscribe();
  }
}
```

This uses the existing `send(command, timeout)` timer rather than adding another timer. Existing callers continue receiving `AgentEvent[]`; the only behavioral correction is that collection ends at the correlated terminal response instead of the first `agent_end`. Event listeners continue receiving stream events independently. `getPromptAndWaitData()` preserves `error.code` and `error.message` on a typed `RpcPromptAndWaitCommandError`.

Extend `rpc.test.ts` to keep its existing returned-event assertions and add a two-segment case proving both segments are present before `promptAndWait()` resolves.

- [ ] **Step 7: Document the command and the non-authority of `agent_end`**

Add one `prompt_and_wait` section to `docs/rpc.md` with the exact command, success, failure, and abort behavior from **Closed Interfaces**. State explicitly that `agent_end` is a segment event and clients must use the correlated command response for prompt settlement.

- [ ] **Step 8: Run Prime RPC, ACP, client, and build verification**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run `
  test/rpc-prompt-response-semantics.test.ts `
  test/rpc-jsonl.test.ts `
  test/rpc.test.ts `
  test/suite/acp-features.test.ts
npm run build
git diff --check
```

Expected: all focused tests and build pass; no model starts.

- [ ] **Step 9: Commit the generic Prime RPC command**

```powershell
git add packages/coding-agent/src/modes/rpc/rpc-types.ts `
  packages/coding-agent/src/modes/rpc/rpc-mode.ts `
  packages/coding-agent/src/modes/rpc/rpc-client.ts `
  packages/coding-agent/docs/rpc.md `
  packages/coding-agent/test/rpc-prompt-response-semantics.test.ts `
  packages/coding-agent/test/rpc.test.ts
git commit -m "feat: expose settled prompt RPC command"
```

### Task 3: Implement the Durable Conversation Registry

**Files:**
- Create: `mcp_server/src/rook/agent/chat/prime_registry.py`
- Create: `mcp_server/tests/test_prime_registry.py`

**Interfaces:**
- Consumes: the exact Slice 0 JSON record.
- Produces: `TargetFingerprint`, `PrimeModelSelection`, `LifecycleRecord`, `PrimeConversationRecord`, and `PrimeConversationRegistry` for Task 5.

- [ ] **Step 1: Write RED record and lock tests**

Cover strict required/allowed keys, exact target equality, canonical decimal process-start ticks, path-safe conversation IDs, atomic replacement, prior-record survival on `os.replace` failure, two sibling files surviving independent writes, a second writer lock refusing, and startup reconciliation of `running`/`cancel_requested` to `failed/broker_restart_interrupted`.

```python
def test_independent_updates_do_not_rewrite_sibling(tmp_path):
    registry = open_registry(tmp_path, pid=1234, start_ticks="638918000000000000")
    registry.write(record("conv_" + "a" * 32, state="idle"))
    sibling = registry.write(record("conv_" + "b" * 32, state="idle"))
    sibling_bytes = sibling.read_bytes()

    registry.write(record("conv_" + "a" * 32, state="failed"))

    assert sibling.read_bytes() == sibling_bytes
```

- [ ] **Step 2: Run the RED registry tests**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_registry.py -q
```

Expected: import failure because `prime_registry.py` is absent.

- [ ] **Step 3: Implement closed immutable records**

```python
@dataclass(frozen=True)
class TargetFingerprint:
    rhino_pid: int
    rhino_process_start_utc_ticks: str
    document_runtime_serial: int

@dataclass(frozen=True)
class PrimeModelSelection:
    provider: str
    id: str
    thinking: str | None

@dataclass(frozen=True)
class LifecycleRecord:
    state: Literal["idle", "running", "cancel_requested", "failed", "closed"]
    reason: str | None
    updated_at_utc: str

@dataclass(frozen=True)
class PrimeConversationRecord:
    schema_version: Literal[1]
    conversation_id: str
    prime_session_id: str
    prime_session_path: str
    model: PrimeModelSelection
    target: TargetFingerprint
    last_lifecycle: LifecycleRecord
```

Reject unknown/missing keys at every nested level. Resolve `prime_session_path` to an absolute path but never follow it to infer a different session identity.

- [ ] **Step 4: Implement namespace ownership and atomic writes**

The namespace is:

```python
registry_root / f"{rhino_pid}-{rhino_process_start_utc_ticks}"
```

Hold a one-byte `msvcrt.locking(..., LK_NBLCK, 1)` lock on `.writer.lock` for the registry object's lifetime. Write UTF-8 JSON with sorted keys and compact separators to a same-directory unique temporary file, flush and `os.fsync()`, then `os.replace()`. Clean only the unpublished temporary file on failure. The existing valid record must remain byte-identical.

- [ ] **Step 5: Implement restart reconciliation**

`reconcile_interrupted_records()` acquires the namespace lock, reads each file strictly, and replaces only `running` and `cancel_requested` with:

```json
{"state":"failed","reason":"broker_restart_interrupted"}
```

It returns the changed conversation IDs for health diagnostics. It never changes `idle`, `failed`, or `closed`.

- [ ] **Step 6: Run registry tests and static compilation**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_registry.py -q
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m py_compile `
  mcp_server/src/rook/agent/chat/prime_registry.py
```

- [ ] **Step 7: Commit the registry**

```powershell
git add mcp_server/src/rook/agent/chat/prime_registry.py `
  mcp_server/tests/test_prime_registry.py
git commit -m "feat: add durable Prime chat registry"
```

### Task 4: Implement the Owned Prime RPC Process

**Files:**
- Create: `mcp_server/src/rook/agent/chat/prime_rpc_protocol.py`
- Create: `mcp_server/src/rook/agent/chat/prime_process.py`
- Create: `mcp_server/tests/fixtures/prime_rpc_fake_child.py`
- Create: `mcp_server/tests/test_prime_rpc_protocol.py`
- Create: `mcp_server/tests/test_prime_process.py`

**Interfaces:**
- Consumes: Task 2's command-specific wire shapes.
- Produces:

```python
class PrimeRpcProcess:
    generation: int

    async def start(self) -> PrimeRuntimeState: ...
    async def command(
        self,
        command: dict[str, Any],
        *,
        expected_command: str,
    ) -> dict[str, Any]: ...
    def subscribe(
        self,
        listener: Callable[[int, dict[str, Any]], None],
    ) -> Callable[[], None]: ...
    async def retire(self, grace_seconds: float) -> None: ...
```

`PrimeRuntimeState` contains only `session_id`, absolute `session_path`, `provider`, `model_id`, and `thinking`.

- [ ] **Step 1: Write RED strict-wire and launch tests**

Cover LF-only JSON, duplicate/unknown response IDs, malformed response objects, wrong command correlation, structured prompt failures, stale-generation output, process exit with pending commands, a 64 MiB line ceiling, exact argument arrays, session resume, and idempotent retirement.

The expected new-session argument array is exact:

```python
[
    node_path,
    cli_path,
    "--mode", "rpc",
    "--session-dir", session_dir,
    "--no-tools",
    "--no-extensions",
    "--no-skills",
    "--no-context-files",
    "--no-prompt-templates",
]
```

Add `--model provider/id` and `--thinking level` only when configured. Resume appends `--resume`, then the exact registry path. Never construct a shell command string and never pass `--api-key`.

- [ ] **Step 2: Run RED process tests**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_rpc_protocol.py `
  mcp_server/tests/test_prime_process.py -q
```

- [ ] **Step 3: Implement the closed parser and event projector**

`prime_rpc_protocol.py` must expose:

```python
PromptFailureCode = Literal[
    "admission_failed",
    "execution_failed",
    "inspection_failed",
    "settlement_unknown",
    "protocol_failed",
]

@dataclass(frozen=True)
class PromptSettlement:
    request_id: str
    outcome: Literal["completed", "aborted"] | None
    error_code: PromptFailureCode | None
    error_message: str | None
```

`project_prime_event()` maps text deltas, model changes, and `agent_end` segment status only. Unknown events are ignored for Slice 2, not guessed into the product vocabulary.

- [ ] **Step 4: Implement process launch and response correlation**

Use `asyncio.create_subprocess_exec(*argv, stdin=PIPE, stdout=PIPE, stderr=PIPE)`. A reader task owns stdout and resolves pending futures by exact request ID and expected command. Session events are delivered to subscribers without blocking response correlation. Each process has a monotonically assigned launch generation supplied by the backend; callbacks include that generation.

The strict reader uses chunked LF detection with a 64 MiB per-row ceiling. EOF with an unterminated non-empty row is a protocol failure. Stderr is retained in a bounded 256 KiB tail for diagnostics and never enters model/session records.

- [ ] **Step 5: Implement bounded process retirement**

`retire(grace_seconds)` closes stdin, waits within the caller's remaining deadline, calls `terminate()`, then on Windows uses `taskkill /PID <pid> /T /F` only for the process it created. It never acts on a PID restored from disk. Every pending command fails once with `PrimeProcessLost`.

- [ ] **Step 6: Make the fake child script scenario-driven**

The fake child accepts `--scenario` and supports:

```text
complete
two_segments_then_complete
provider_failure
prompt_pending_until_abort
complete_before_abort_response
malformed_json
wrong_response_id
exit_mid_prompt
stale_generation
```

It echoes `get_state`, `get_available_models`, `set_model`, `set_thinking_level`, `prompt_and_wait`, and `abort` with deterministic IDs and no model/network access.

- [ ] **Step 7: Run focused process tests and compile**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_rpc_protocol.py `
  mcp_server/tests/test_prime_process.py -q
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m py_compile `
  mcp_server/src/rook/agent/chat/prime_rpc_protocol.py `
  mcp_server/src/rook/agent/chat/prime_process.py `
  mcp_server/tests/fixtures/prime_rpc_fake_child.py
```

- [ ] **Step 8: Commit the process boundary**

```powershell
git add mcp_server/src/rook/agent/chat/prime_rpc_protocol.py `
  mcp_server/src/rook/agent/chat/prime_process.py `
  mcp_server/tests/fixtures/prime_rpc_fake_child.py `
  mcp_server/tests/test_prime_rpc_protocol.py `
  mcp_server/tests/test_prime_process.py
git commit -m "feat: add owned Prime RPC process"
```

### Task 5: Implement Broker Lifecycle, Cancellation, and Residency

**Files:**
- Create: `mcp_server/src/rook/agent/chat/prime_backend.py`
- Create: `mcp_server/tests/test_prime_backend.py`

**Interfaces:**
- Consumes: `PrimeConversationRegistry` from Task 3 and `PrimeRpcProcess` from Task 4.
- Produces:

```python
class PromptSubscription:
    def __aiter__(self) -> AsyncIterator[dict[str, Any]]: ...
    async def close(self) -> None: ...

class PromptSubscriptionBuffer:
    MAX_ROWS = 128
    MAX_NONTERMINAL_ROWS = 127

    def publish(self, row: dict[str, Any]) -> None: ...
    async def next(self) -> dict[str, Any]: ...

class PrimeChatBackend:
    async def create(
        self,
        conversation_id: str,
        target: TargetFingerprint,
    ) -> PrimeConversationRecord: ...
    async def reopen(
        self,
        conversation_id: str,
        target: TargetFingerprint,
    ) -> PrimeConversationRecord: ...
    async def start_prompt(
        self,
        conversation_id: str,
        message: str,
    ) -> PromptSubscription: ...
    async def cancel(self, conversation_id: str) -> LifecycleRecord: ...
    async def close(self, conversation_id: str) -> LifecycleRecord: ...
    async def models(self, conversation_id: str) -> list[dict[str, Any]]: ...
    async def set_model(
        self,
        conversation_id: str,
        provider: str,
        model_id: str,
        thinking: str | None,
    ) -> PrimeModelSelection: ...
    async def retire_document(self, target: TargetFingerprint) -> None: ...
    async def shutdown(self) -> None: ...
```

- [ ] **Step 1: Write the RED lifecycle matrix**

Add these exact tests, one per independently reviewable invariant:

```text
test_one_prompt_has_one_correlated_settlement
test_multiple_agent_end_events_do_not_settle_prompt
test_cancel_stays_requested_until_aborted_settlement
test_natural_completion_wins_cancel_race_once
test_process_loss_marks_failed_without_replay
test_saved_running_rehydrates_failed
test_saved_cancel_requested_rehydrates_failed
test_failed_requires_explicit_reopen
test_pid_reuse_with_new_start_ticks_is_rejected
test_document_serial_mismatch_is_rejected
test_second_registry_writer_refuses
test_sibling_registry_updates_are_independent
test_stale_launch_generation_event_is_ignored
test_atomic_registry_failure_preserves_previous_record
test_capacity_retires_lru_idle_only
test_capacity_refuses_when_every_child_is_active
test_idle_retirement_preserves_session_record
test_tab_close_cancels_and_closes
test_document_retirement_never_rebinds_target
test_shutdown_uses_one_global_ten_second_deadline
test_slow_subscriber_coalesces_text_without_blocking_settlement
test_partial_model_update_reconciles_actual_runtime_state
test_failed_model_reconciliation_marks_conversation_failed
```

The causal cancel-race test must assert broker-local correlation:

```python
assert backend.pending_abort == PendingAbort(
    abort_request_id="abort-2",
    prompt_request_id="prompt-1",
    launch_generation=7,
)

fake.emit_response("prompt-1", outcome="completed")
assert registry.load(conversation_id).last_lifecycle.reason == "completed_before_abort"

fake.emit_abort_response("abort-2")
assert registry.load(conversation_id).last_lifecycle.reason == "completed_before_abort"
assert stream.terminal_count == 1
```

- [ ] **Step 2: Run RED backend tests**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_backend.py -q
```

- [ ] **Step 3: Implement runtime-only ownership**

```python
@dataclass
class ResidentPrimeConversation:
    process: PrimeRpcProcess
    launch_generation: int
    pending_prompt_id: str | None
    pending_abort: PendingAbort | None
    last_activity_monotonic: float
    prompt_task: asyncio.Task[None] | None
```

This object is never serialized. `PrimeChatBackend` owns one dictionary keyed by conversation ID and one monotonically increasing generation counter.

- [ ] **Step 4: Implement explicit create and reopen**

`create` refuses an existing registry file, launches a new session, calls `get_state`, requires non-empty `sessionId` and absolute `sessionFile`, and only then writes `idle`. `reopen` requires an existing `idle` or `failed` record, exact target equality, exact session path existence, and a resumed `get_state` with the same session ID/path. `closed`, missing, or target-mismatched records refuse without launching a model turn.

- [ ] **Step 5: Implement prompt settlement independently of the HTTP reader**

`start_prompt()` changes `idle -> running` atomically before dispatch and creates a broker-owned background task. The task alone receives the correlated settlement and persists lifecycle; subscription buffering never owns settlement.

Each attached `PromptSubscription` uses a nonblocking `PromptSubscriptionBuffer` with this exact overflow contract:

1. At most 127 nonterminal rows are retained, reserving one slot for a terminal row.
2. Adjacent pending `text_delta` rows are concatenated in order.
3. At pressure, pending `status` rows are discarded first because they are observational and cannot settle the turn.
4. A new `model_update` replaces an older pending `model_update`; if no such row or status row can be replaced, it is omitted because the panel refreshes authoritative model state after settlement.
5. After those reductions, all pending text rows are concatenated in original order into one `text_delta`; text bytes are never dropped.
6. Exactly one terminal `done`, `cancelled`, or terminal `error` occupies the reserved slot. Publishing a second terminal row is a broker invariant failure and cannot alter durable lifecycle.
7. `publish()` never awaits the UI consumer, so response correlation remains live. `next()` waits on an `asyncio.Condition` owned by the buffer.
8. Closing the subscription clears its buffer, wakes its waiter, and unregisters it. It does not cancel the prompt task or change lifecycle.

The slow-consumer regression publishes 1,000 numbered text deltas plus 200 duplicate segment statuses without consuming, then settles the prompt. It asserts `len(buffer) <= 128`, exact concatenated text `"0,1,...,999,"`, one terminal row, and a resolved command future before the consumer drains the buffer.

Map Prime results exactly:

```text
running + completed              -> idle / reason null / done(completed)
running + aborted                -> idle / reason aborted / cancelled(aborted)
cancel_requested + completed     -> idle / completed_before_abort / done(completed_before_abort)
cancel_requested + aborted       -> idle / aborted / cancelled(aborted)
any prompt_and_wait failure      -> failed / same stable code / terminal error
process or protocol loss         -> failed / settlement_unknown / terminal error
```

No failure path replays the prompt.

- [ ] **Step 6: Implement cancel with broker-local correlation**

`cancel()` accepts only `running`, persists `cancel_requested`, records `PendingAbort`, and sends Prime's unchanged `abort`. It returns after the abort command response or transport refusal, not after prompt settlement. A repeated cancel is an idempotent `cancel_requested` response for the same generation. Natural completion retires the pending abort locally as defined in **Closed Interfaces**.

- [ ] **Step 7: Implement models and finite residency**

`models()` projects `get_available_models` to stable IDs `provider/model`. `set_model()` is allowed only from `idle` and follows one reconciliation rule:

```text
attempt set_model
-> attempt set_thinking_level when requested
-> always read get_state
-> persist the actual provider/model/thinking returned by Prime
```

If both mutations and readback succeed, return success. If either mutation fails but readback succeeds, persist the actual state, keep lifecycle `idle` with reason `model_update_failed_reconciled`, and return a failed operation containing the actual selection. If readback fails after either mutation was attempted, persist lifecycle `failed/model_reconciliation_failed`, retire the child, and require explicit reopen before another prompt or model change. The causal regression makes `set_model` succeed, `set_thinking_level` fail, and `get_state` return the new model with the old thinking level; registry and response must both report that exact actual state.

At 10 residents, retire the least-recently-used `idle` child; refuse with `capacity_exhausted` when all residents are `running` or `cancel_requested`. A periodic task retires children idle for 1,800 seconds without closing their records.

- [ ] **Step 8: Implement close, document retirement, and global shutdown**

`close()` persists `closed`, requests abort if active, and retires the child. `retire_document(target)` retires matching children and leaves records non-rebindable. `shutdown()` uses one absolute deadline 10 seconds from entry, requests cancel for all active children, awaits their prompt tasks within the shared remainder, then kills only still-owned process trees. Repeated calls are no-ops.

- [ ] **Step 9: Run the complete model-free broker suite**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_registry.py `
  mcp_server/tests/test_prime_rpc_protocol.py `
  mcp_server/tests/test_prime_process.py `
  mcp_server/tests/test_prime_backend.py -q
```

Expected: all tests pass with the fake child only.

- [ ] **Step 10: Commit broker lifecycle**

```powershell
git add mcp_server/src/rook/agent/chat/prime_backend.py `
  mcp_server/tests/test_prime_backend.py
git commit -m "feat: add Prime chat broker lifecycle"
```

### Task 6: Add Prime as an Explicit HTTP Backend Option

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `mcp_server/src/rook/agent/chat/service_main.py`
- Modify: `mcp_server/tests/test_chat_server.py`

**Interfaces:**
- Consumes: `PrimeChatBackend` from Task 5.
- Produces: stable HTTP/NDJSON endpoints consumed by `AgentChatClient` in Task 7.

- [ ] **Step 1: Add RED HTTP tests for backend exclusivity**

Inject both a fake Prime backend and a fake legacy runner. Prove absent `ROOK_CHAT_BACKEND` and explicit `legacy` both select `ChatRunner`, explicit `prime` never calls `ChatRunner`, and an invalid value refuses application startup. Prime mode rejects `execution_mode` and `/agent/chat/ui-response` with `unsupported_in_prime_text_slice`.

- [ ] **Step 2: Add RED request-custody and lifecycle tests**

Cover exact create/reopen target JSON, target mismatch, stable conversation ID, model projection, set-model idle-only behavior, partial model-update reconciliation, failed model reconciliation, `cancel_requested`, completed-before-abort, aborted, process failure, stream disconnect not producing idle, explicit close, and app cleanup invoking one bounded backend shutdown.

- [ ] **Step 3: Run RED HTTP tests**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_chat_server.py -q
```

- [ ] **Step 4: Add exact service configuration**

`service_main.py` gains required `--rhino-process-start-utc-ticks` and reads:

```text
ROOK_CHAT_BACKEND=prime|legacy  # optional; absent means legacy
ROOK_PRIME_NODE_PATH=<absolute node.exe>
ROOK_PRIME_CLI_PATH=<absolute cli.js>
ROOK_PRIME_MODEL=<optional provider/model>
ROOK_PRIME_THINKING=<optional valid Prime level>
ROOK_PRIME_REGISTRY_ROOT=<optional absolute override for tests/development>
```

Prime mode refuses startup before binding HTTP if node, CLI, model syntax, thinking level, or registry root is invalid. The absent/legacy path does not require Prime configuration and preserves the existing product default. No credential value is read or copied by Rook.

- [ ] **Step 5: Inject one backend owner into `create_chat_app`**

Add typed app keys for backend mode and `PrimeChatBackend`. App cleanup calls `shutdown()` once. Keep existing `ConversationStore`, `PromptBuilder`, and `ChatRunner` construction only on the legacy branch.

The model endpoint projects Task 5 reconciliation without hiding partial application:

```text
success                                 -> HTTP 200 with actual provider/model/thinking
model_update_failed_reconciled          -> HTTP 409 with stable code, message, and actual provider/model/thinking
model_reconciliation_failed             -> HTTP 502 with stable code and message; conversation requires reopen
```

The HTTP tests assert both failure responses and the registry's corresponding actual or failed state.

- [ ] **Step 6: Freeze the start/reopen HTTP request**

```json
{
  "action":"create",
  "conversation_id":"conv_32_lowercase_hex_chars",
  "target":{
    "rhinoPid":1234,
    "rhinoProcessStartUtcTicks":"638918000000000000",
    "documentRuntimeSerial":42
  }
}
```

`action` is exactly `create` or `reopen`. Prime mode ignores persona routing and returns one identity label `Rook`; legacy mode retains its existing persona contract. The response includes `backend: "prime"` or `"legacy"` so the panel can select stop behavior.

- [ ] **Step 7: Add explicit cancel and preserve close**

Register `POST /agent/chat/cancel` for turn cancellation. Keep `POST /agent/chat/stop` as explicit conversation close. A disconnected `/message` reader only unsubscribes its UI sink; it does not call cancel, write idle, or close the conversation.

- [ ] **Step 8: Stream only the closed Slice 2 projection**

The Prime branch of `/message` sends one `prompt_and_wait` and forwards the rows defined in **Panel NDJSON projection**. It writes `done`, `cancelled`, or terminal `error` only from the broker settlement. The legacy branch remains byte-compatible with existing tests.

- [ ] **Step 9: Run focused HTTP and broker tests**

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_registry.py `
  mcp_server/tests/test_prime_rpc_protocol.py `
  mcp_server/tests/test_prime_process.py `
  mcp_server/tests/test_prime_backend.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_chat_integration.py -q
```

- [ ] **Step 10: Commit the opt-in server path**

```powershell
git add mcp_server/src/rook/agent/chat/server.py `
  mcp_server/src/rook/agent/chat/service_main.py `
  mcp_server/tests/test_chat_server.py
git commit -m "feat: add opt-in Prime RookChat backend"
```

### Task 7: Add the Opt-In Prime Path to `AgentChatTab`

**Files:**
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Modify: `src/Rook/UI/Chat/ChatTab.cs`
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`
- Modify: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`
- Modify: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`
- Create: `src/Rook.Tests/UI/Chat/AgentChatPrimeLifecycleTests.cs`

**Interfaces:**
- Consumes: Task 6's HTTP request/response and NDJSON rows.
- Produces: one text-only Prime-backed `AgentChatTab` path selected only when the service reports `backend: "prime"`; the legacy path remains the unchanged default.

- [ ] **Step 1: Add RED launch-argument tests**

Extract an internal pure `BuildServiceArguments()` helper and assert the host passes its real fingerprint:

```csharp
Assert.Equal(
    "-m rook.agent.chat.service_main --port 0 --owner rhino-panel " +
    "--rhino-process-id 1234 --rhino-process-start-utc-ticks 638918000000000000",
    ChatServiceManager.BuildServiceArguments(1234, "638918000000000000"));
```

The production value comes from `Process.GetCurrentProcess().StartTime.ToUniversalTime().Ticks.ToString(CultureInfo.InvariantCulture)` and is captured once per `ChatServiceManager` process lifetime.

- [ ] **Step 2: Add RED client serialization and parsing tests**

Use the existing injected `HttpClient` constructor to assert exact create, reopen, cancel, and close bodies. Add fields:

```csharp
public sealed class ChatTargetFingerprint
{
    public int RhinoPid { get; set; }
    public string RhinoProcessStartUtcTicks { get; set; } = "";
    public uint DocumentRuntimeSerial { get; set; }
}

public class ChatEvent
{
    public string? Outcome { get; set; }
    public string? Code { get; set; }
    public bool? Terminal { get; set; }
}
```

- [ ] **Step 3: Add RED UI-lifecycle tests through pure helpers**

Add internal static helpers to `ChatTab`/`AgentChatTab` and test:

```csharp
Assert.True(AgentChatTab.DefersLocalStopCompletion("prime"));
Assert.False(AgentChatTab.DefersLocalStopCompletion("legacy"));
Assert.True(AgentChatTab.IsSettledTerminalEvent("done"));
Assert.True(AgentChatTab.IsSettledTerminalEvent("cancelled"));
Assert.False(AgentChatTab.IsSettledTerminalEvent("status"));
```

Also assert that reconnect chooses `reopen`, keeps the same stable conversation ID, and does not clear it before the request.

- [ ] **Step 4: Run RED C# chat tests**

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore `
  --filter "FullyQualifiedName~Rook.Tests.UI.Chat"
```

- [ ] **Step 5: Pass the process-start fingerprint from the C# host**

Replace the inline service argument string with `BuildServiceArguments(CurrentRhinoProcessId, RhinoProcessStartUtcTicks)`. Keep process handles and service ownership exactly where they are today.

- [ ] **Step 6: Make the tab own a stable conversation ID**

Create once in the `AgentChatTab` constructor:

```csharp
private readonly string _stableConversationId = "conv_" + Guid.NewGuid().ToString("N");
```

Initial `InitializeAsync()` sends `action: "create"`. `ReconnectToServiceAsync()` keeps the ID, obtains the new service URI/nonce, and sends `action: "reopen"`. It never silently falls back from failed reopen to create. A user-visible action may create a new tab/conversation instead.

- [ ] **Step 7: Separate cancel from stream disposal and conversation close**

In Prime mode, `OnStopRequested()` starts `CancelAsync()` and leaves the message stream token alive. Add this base hook:

```csharp
protected virtual bool DeferStopCompletion => false;
```

`ChatTab.OnStopClicked()` preserves current behavior when false. When true, it calls `OnStopRequested()`, leaves `_isProcessing` true, leaves input disabled, and displays `Cancelling...`. `ClaudeCodeTab` and legacy AgentChat remain unchanged.

- [ ] **Step 8: Finalize only settled terminal events**

Prime event handling is exact:

```text
status/cancel_requested       -> status only; processing remains true
status/agent_segment          -> optional status only
done/completed                -> finalize, ready, processing false
done/completed_before_abort   -> finalize, completed-before-cancel, processing false
cancelled/aborted             -> finalize, stopped, processing false
terminal error                -> finalize, failed, processing false; require reopen/new conversation
```

Tab close still cancels the local stream token, calls `StopAsync` to close the conversation, and releases the WebView. User cancel does not call `StopAsync`.

- [ ] **Step 9: Keep model selection Prime-owned**

Consume the Prime-projected model list and call `/agent/chat/model`. Disable Apply while processing/cancelling. Do not use `model_status.py` routing on the Prime path and do not translate persona prompts.

On HTTP 409 `model_update_failed_reconciled`, replace the selectors with the returned actual provider/model/thinking and show the operation failure. On HTTP 502 `model_reconciliation_failed`, show the failed/reopen-required state. Never leave the panel displaying the requested selection as though it were authoritative after a failed update.

- [ ] **Step 10: Run focused and full managed tests**

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore `
  --filter "FullyQualifiedName~Rook.Tests.UI.Chat"
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore
```

- [ ] **Step 11: Commit the opt-in panel path**

```powershell
git add src/Rook/UI/Chat/ChatServiceManager.cs `
  src/Rook/UI/Chat/AgentChatClient.cs `
  src/Rook/UI/Chat/ChatTab.cs `
  src/Rook/UI/Chat/AgentChatTab.cs `
  src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs `
  src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs `
  src/Rook.Tests/UI/Chat/AgentChatPrimeLifecycleTests.cs
git commit -m "feat: add opt-in Prime text streaming"
```

### Task 8: Model-Free End-to-End Qualification and Documentation

**Files:**
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Create: `docs/superpowers/reports/2026-08-27-rookchat-prime-primary-backend-slices-1-2-qualification.md`
- Test: all files changed by Tasks 1-7.

**Interfaces:**
- Consumes: the complete Prime command, fake child broker, HTTP routes, and C# client/panel behavior.
- Produces: an independently reviewable offline qualification record; no live product claim.

- [ ] **Step 1: Add one model-free vertical test**

Start the aiohttp app with the fake child, create a conversation, stream two text deltas and two `agent_end` segments, race cancel against natural completion, and assert:

```text
no done before prompt_and_wait response
exactly one done(completed_before_abort)
late abort response ignored
same conversation/session IDs in registry
registry target equals supplied target
no process remains owned after shutdown
legacy runner call count remains zero
```

- [ ] **Step 2: Run all Prime-focused tests and build**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run `
  test/rpc-prompt-response-semantics.test.ts `
  test/rpc-jsonl.test.ts `
  test/rpc.test.ts `
  test/suite/acp-features.test.ts
npm run build
git diff --check
```

- [ ] **Step 3: Run all Rook broker/chat tests and compilation**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_prime_registry.py `
  mcp_server/tests/test_prime_rpc_protocol.py `
  mcp_server/tests/test_prime_process.py `
  mcp_server/tests/test_prime_backend.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_chat_integration.py -q
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m py_compile `
  mcp_server/src/rook/agent/chat/prime_registry.py `
  mcp_server/src/rook/agent/chat/prime_rpc_protocol.py `
  mcp_server/src/rook/agent/chat/prime_process.py `
  mcp_server/src/rook/agent/chat/prime_backend.py `
  mcp_server/src/rook/agent/chat/server.py `
  mcp_server/src/rook/agent/chat/service_main.py
```

- [ ] **Step 4: Run managed tests**

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore `
  --filter "FullyQualifiedName~Rook.Tests.UI.Chat"
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore
```

- [ ] **Step 5: Prove scope and absence of live contact**

```powershell
git status --short
git diff --check
git -C D:/prime-agent/.worktrees/rookchat-primary-backend status --short
git -C D:/prime-agent/.worktrees/rookchat-primary-backend diff --check
Get-Process Rhino,ollama -ErrorAction SilentlyContinue
```

The report records commands and results but makes no claim that Rhino/Ollama being absent proves network absence by itself. The test fixtures and launch arguments establish that no provider/model command was used.

- [ ] **Step 6: Update architecture status narrowly**

State that the text-only `AgentChatTab` can use Prime RPC only when `ROOK_CHAT_BACKEND=prime`, that absent/legacy configuration remains the product default, that product-default cutover remains deferred to Slice 6, and that images, tools, Rook mutation, web, packaging, and live qualification remain unimplemented.

- [ ] **Step 7: Write the offline qualification report**

Include exact Rook and Prime commits, tree hashes, changed-file scope, test counts, registry/process lifecycle rows, error-code matrix, abort race result, fake-child custody, and explicit non-claims. Record any failure honestly; do not weaken a gate to obtain a pass.

- [ ] **Step 8: Commit documentation and final verification**

```powershell
git add docs/CURRENT_ARCHITECTURE.md `
  docs/superpowers/reports/2026-08-27-rookchat-prime-primary-backend-slices-1-2-qualification.md
git commit -m "docs: qualify Prime-backed RookChat text path"
git status --short
git log -8 --oneline
```

Expected: clean Rook and Prime implementation worktrees. Stop for independent implementation review. Do not run a provider, Rhino, Grasshopper, Rook mutation, or product smoke until separately authorized.

## Implementation Authorization Gate

This plan is the stopping point for the current slice. Before Task 1 begins, an independent reviewer must verify:

1. the closed `prompt_and_wait` error object and phase ownership;
2. ACP/helper/RPC reuse without a second Prime lifecycle interpretation;
3. broker-local abort correlation using `PendingAbort` rather than a new Prime field;
4. durable registry versus in-memory process ownership;
5. target fingerprint and explicit reopen behavior;
6. rollback exclusivity and text-only scope; and
7. test coverage for compaction continuation, provider failure, cancel races, sibling registry files, stale generations, capacity, and bounded shutdown.

No implementation execution, live contact, or additional architecture work is authorized by this document alone.
