# RookChat Prime Primary Backend Slices 1-2 Offline Qualification

**Date:** 2026-08-28
**Disposition:** OFFLINE QUALIFIED FOR INDEPENDENT IMPLEMENTATION REVIEW
**Product status:** OPT-IN ONLY; LEGACY `ChatRunner` REMAINS DEFAULT

## Objective

Qualify the first two bounded slices of the RookChat Prime-backend integration:

1. A Prime-generic settled `prompt_and_wait` RPC command.
2. A Rhino-owned RookChat broker, HTTP projection, and text-only `AgentChatTab` path selected only by `ROOK_CHAT_BACKEND=prime`.

The implementation follows the reviewed plan at:

`docs/superpowers/plans/2026-08-27-rookchat-prime-primary-backend-slices-1-2.md`

No provider, model turn, Rhino operation, Grasshopper operation, Rook mutation, or product smoke was authorized.

## Authorization And Source Custody

The active implementation goal named approved plan commit:

`741c97ae5be545baaca0e46821062bb6bbe6b24b`

Task 0 observed a clean coordinating worktree at that exact `HEAD` before creating either implementation worktree. No environment variable, tag, moving branch, or separate authorization store supplied the reviewed commit.

Prime started from:

`739400844f8f3f280414b0c7b9c65797208815d3`

Prime implementation head and tree before this report:

```text
commit 7690c18479c909ddea67a34e86114f7f982179a8
tree   49d249e45f18b6d747dadccb4e5ec5ef577ce549
```

Rook implementation head and tree before this report:

```text
commit fba648ffab87c6c5cbf1d300e5c9078759153bd8
tree   0829c7201022eed40d4479524951c521c077d852
```

Implementation worktrees:

```text
D:/prime-agent/.worktrees/rookchat-primary-backend
C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend
```

Historical Prime qualification worktrees were not modified.

## Implementation Commits

Prime:

```text
a158e892830500881c3a05816075eb6fc31d5ed6  refactor: share Prime headless turn settlement
7690c18479c909ddea67a34e86114f7f982179a8  feat: expose settled prompt RPC command
```

Rook:

```text
c5a6a01ce1eac257421199cb8525b249d6a7a33f  feat: add durable Prime chat registry
5641bbf1cdc346bb4ed0556048372bc3b2dd985f  feat: add owned Prime RPC process
2cfb0fdbed2ed2d7e9134a8a27e442f47d0af3d2  feat: add Prime chat broker lifecycle
d01c8e7b9a7dd68d51fc7ca2e3045409d80b2410  feat: add opt-in Prime RookChat backend
b2070d5cd316b117e95c50144d2a6d62bd8c13ae  feat: add opt-in Prime text streaming
fba648ffab87c6c5cbf1d300e5c9078759153bd8  test: qualify Prime RookChat vertical path
```

## Changed Scope

Prime changes are limited to the existing ACP/headless/RPC modes, RPC documentation, and causal tests:

```text
packages/coding-agent/docs/rpc.md
packages/coding-agent/src/modes/acp/acp-mode.ts
packages/coding-agent/src/modes/headless-turn.ts
packages/coding-agent/src/modes/rpc/rpc-client.ts
packages/coding-agent/src/modes/rpc/rpc-mode.ts
packages/coding-agent/src/modes/rpc/rpc-types.ts
packages/coding-agent/test/fixtures/rpc-client-prompt-settlement-child.mjs
packages/coding-agent/test/rpc-client-prompt-settlement.test.ts
packages/coding-agent/test/rpc-prompt-response-semantics.test.ts
```

Rook changes are limited to the Prime registry/process/protocol/broker, chat HTTP/service integration, text-only managed panel integration, and tests:

```text
mcp_server/src/rook/agent/chat/prime_backend.py
mcp_server/src/rook/agent/chat/prime_process.py
mcp_server/src/rook/agent/chat/prime_registry.py
mcp_server/src/rook/agent/chat/prime_rpc_protocol.py
mcp_server/src/rook/agent/chat/server.py
mcp_server/src/rook/agent/chat/service_main.py
mcp_server/tests/fixtures/prime_rpc_fake_child.py
mcp_server/tests/test_chat_server.py
mcp_server/tests/test_prime_backend.py
mcp_server/tests/test_prime_process.py
mcp_server/tests/test_prime_registry.py
mcp_server/tests/test_prime_rpc_protocol.py
src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs
src/Rook.Tests/UI/Chat/AgentChatPrimeLifecycleTests.cs
src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs
src/Rook/UI/Chat/AgentChatClient.cs
src/Rook/UI/Chat/AgentChatTab.cs
src/Rook/UI/Chat/ChatServiceManager.cs
src/Rook/UI/Chat/ChatTab.cs
```

## Dependency And Import Custody

Prime dependencies were installed with `npm ci` from the worktree lockfile.

```text
package-lock.json SHA-256:
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

vitest:
D:/prime-agent/.worktrees/rookchat-primary-backend/node_modules/vitest/package.json

tsx:
D:/prime-agent/.worktrees/rookchat-primary-backend/node_modules/tsx/package.json
```

Rook Python imports resolved from the implementation worktree:

```text
C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend/mcp_server/src/rook/__init__.py
C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend/mcp_server/src/rook/agent/chat/server.py
```

Managed restore assets were worktree-local:

```text
C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend/src/Rook.Tests/obj/project.assets.json
SHA-256 5F9267680E4A6D430C3A98CB60A95659A4D7DB7367079BFE3CCA69BFCBCBCBF3
```

## Prime Settlement Contract

The new `prompt_and_wait` RPC path reuses Prime's established ACP/headless sequence:

```text
capture pre-turn transcript boundary
-> AgentSession.promptAndWait()
-> waitForHeadlessCompletion()
-> inspect only the new terminal transcript
-> return one closed settlement response
```

`agent_end` remains a segment boundary and never settles a product prompt. The existing public `RpcClient.promptAndWait(): Promise<AgentEvent[]>` API remains unchanged. A distinctly named settled client method consumes the new command.

Closed failure codes are:

| Code | Meaning |
|---|---|
| `admission_failed` | Prime rejected the prompt before execution. |
| `execution_failed` | The model/provider turn failed. |
| `inspection_failed` | Turn-local terminal transcript inspection failed. |
| `settlement_unknown` | Process loss or another condition made settlement unknowable. |
| `protocol_failed` | The RPC response violated the closed protocol. |

Control commands retain a ten-second deadline. `prompt_and_wait` has no elapsed-time control deadline; it ends through settlement, cancellation, close, or process loss.

## Broker And Registry Contract

Durable records contain conversation ID, Prime session identity/path, actual model, target fingerprint, lifecycle, and schema version. Resident process handles, launch generations, subscriptions, pending prompt correlation, and pending abort correlation remain in memory only.

Target identity is:

```text
Rhino PID
+ Rhino process-start UTC ticks
+ document runtime serial
```

Lifecycle ownership is:

| Event | Durable result |
|---|---|
| create | `idle` record and exact Prime session identity |
| prompt admitted | `running` |
| raw `agent_end` | observational `segment_end`; no lifecycle settlement |
| cancel admitted | `cancel_requested` with broker-local prompt/abort/generation correlation |
| natural completion wins cancel race | `idle`, reason `completed_before_abort` |
| abort wins | `idle`, reason `aborted` |
| closed | absorbing `closed`; late callbacks cannot publish or persist |
| broker restart from running/cancel_requested | `failed`, explicit reopen required |

The registry uses one atomic file per conversation under a process-generation writer lock. Saved process IDs never restore process handles.

## Authenticated HTTP And Panel Boundary

Only a nonce-authenticated `/agent/chat/health` response exposes `backend: legacy|prime`. `AgentChatTab` obtains that identity before selecting a request schema.

Legacy start remains:

```json
{"persona":"Rook","documentSerialNumber":42}
```

Prime start is disjoint:

```json
{"action":"create","conversation_id":"conv_32_lowercase_hex_chars","target":{"rhinoPid":1234,"rhinoProcessStartUtcTicks":"638918000000000000","documentRuntimeSerial":42}}
```

Missing, unknown, changed, or unauthenticated backend identity refuses before `/start`. Prime reconnect preserves the stable conversation ID and uses explicit `reopen`; it never falls back silently to create.

Prime cancel leaves the response stream alive until one correlated terminal row arrives. Tab close remains a distinct conversation-close operation. Prime launches do not copy `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` from the Rook host; legacy launch behavior is preserved.

## Model-Free Vertical Result

The vertical test ran the real aiohttp routes, durable registry, broker, subprocess protocol, and deterministic fake Prime child. It established:

```text
create exact conversation/target
-> prompt starts
-> text_delta segment-1
-> agent_end segment boundary
-> text_delta segment-2
-> agent_end segment boundary
-> no terminal row yet
-> cancel races natural completion
-> exactly one done(completed_before_abort)
-> late abort response cannot change the settled generation
-> registry retains the same conversation/session/target
-> application shutdown retires the owned child
-> legacy ChatRunner call count remains zero
```

Focused result: `1 passed`.

## Verification

Prime preflight used a fresh isolated agent/session root:

```text
C:/Users/bring/AppData/Local/Temp/rookchat-prime-final-verify-7e7487daf6d5493baac5baf4a33133c4
credential variables remaining: 0
isolated auth.json present: False
```

Exact Prime test files:

```text
test/rpc-prompt-response-semantics.test.ts
test/rpc-jsonl.test.ts
test/rpc-client-prompt-settlement.test.ts
test/suite/acp-features.test.ts
```

Result: `47 passed`; package-local `npm run build` passed; `git diff --check` passed.

Exact Rook Python qualification files:

```text
mcp_server/tests/test_prime_registry.py
mcp_server/tests/test_prime_rpc_protocol.py
mcp_server/tests/test_prime_process.py
mcp_server/tests/test_prime_backend.py
mcp_server/tests/test_chat_server.py
mcp_server/tests/test_chat_integration.py
```

Result: `182 passed, 3 failed, 18 warnings`. The three failures reproduce in the untouched source checkout and are unrelated pre-existing test debt:

1. Knowledge graph source expected `UnifiedStore`, while production returns `UnifiedStore+CommandKnowledgeStore`.
2. The first command-knowledge node selected by a stale note test contains non-JSON-serializable `ModeKnowledge`.
3. A legacy ChatRunner integration test patches an obsolete LiteLLM call/response shape and receives `error, done` rather than `text_delta, done`.

All six changed Python production modules passed `py_compile`.

Managed results:

```text
Rook.Tests.UI.Chat focused: 106 passed
full Rook.Tests:           3823 passed
```

No managed test failed.

## Contact And Process Evidence

The final Prime qualification scrubbed provider credentials, used empty isolated Prime agent/session directories, and executed only the exact model-free test list. The Rook vertical path used a Python fake child. No provider or model command was admitted.

During Task 0, one root-workspace Prime build command attempted unauthenticated public model-catalog downloads because of workspace build ordering. No model inference request or credentialed provider request occurred. Generated catalog changes were restored, and every subsequent Prime build was package-local. This setup mistake is retained here and is not counted as model contact.

Process presence or absence alone is not used as proof of network absence. The relevant evidence is the credential scrub, empty isolated auth root, exact test list, fake-child process path, and absence of any live-capable command.

## Non-Claims

This qualification does not establish:

- Prime as the product-default RookChat backend.
- Live provider/model behavior.
- Rhino, Grasshopper, or Rook mutation behavior.
- Image, tool, web, adaptive UI, or block-response support.
- Packaging, installation, deployment, or restart behavior in the shipped product.
- Token-budget enforcement or the deferred later slices.
- Universal Prime correctness outside this exact RPC and RookChat path.

## Conclusion

Slices 1-2 are offline-qualified for independent implementation review. The integration now has a Prime-owned settled prompt boundary, a Rook-owned durable/process broker, authenticated backend negotiation, a stable panel conversation identity, and correlated cancellation without replacing the default `ChatRunner` path.

No live product smoke is authorized by this report.
