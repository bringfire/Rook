# RookChat Prime Primary Backend Options

**Date:** 2026-08-26
**Status:** Architecture exploration; no implementation authorization
**Decision already supplied:** Prime replaces `ChatRunner` as RookChat's primary
model backend

## Executive conclusion

The system is ready to begin this migration. The correct change is not to put
Prime beside `ChatRunner`, nor to wrap Prime in the suspended Planner/Reviewer
architecture. It is to remove duplicate model-runtime ownership from RookChat:

```text
RookChat              owns conversation UI, user interaction, and document scope
Prime                 owns model execution, sessions, context, providers, skills,
                      IPython, compaction, cancellation, and continuation
Rook                  owns Rhino/Grasshopper identity, mutation, solve readiness,
                      receipts, diagnostics, and authentic observation
the selected model    owns design reasoning and evidence-grounded judgment
the user              retains acceptance and consequential authorization
```

Two implementation shapes are viable:

1. **Option A, RPC-first replacement:** retain the existing C# panel and local
   Python chat service, replace `ChatRunner` with one Prime RPC process per
   RookChat conversation, and translate Prime events into the existing NDJSON
   panel stream. This is the recommended first product vertical.
2. **Option B, AgentConnection-native bridge:** replace the Python chat service
   with a narrow Node service using Prime's `DaemonAgentConnection`. This is the
   stronger resident-session architecture, but it has a larger packaging and
   maintenance commitment.

Option A is not a fake seam. Prime documents RPC as a supported embedding mode,
and a branch-local, model-free probe on the qualified Prime baseline successfully
returned session, model, compaction, queue, and goal state. It also loaded the
exact external Rook skill under an explicit skill allowlist. Option A therefore
lets us validate the product loop before deciding whether resident daemon
reattachment is worth Option B's additional integration surface.

The migration should not ship the campaign runners, hidden evaluators,
acceptance vocabularies, hash manifests, or terminalization experiments. Those
remain research and qualification assets.

## Evidence reviewed

This assessment reconciles the live code with the architecture and experiment
record rather than selecting a design from one document.

### Live Rook product

- [Current Architecture](../../CURRENT_ARCHITECTURE.md)
- [Agent Architecture](../../AGENT_ARCHITECTURE.md)
- `src/Rook/UI/Chat/RookChatPanel.cs`
- `src/Rook/UI/Chat/AgentChatTab.cs`
- `src/Rook/UI/Chat/AgentChatClient.cs`
- `src/Rook/UI/Chat/ChatServiceManager.cs`
- `mcp_server/src/rook/agent/chat/server.py`
- `mcp_server/src/rook/agent/chat/chat_runner.py`
- `mcp_server/src/rook/agent/chat/conversation_store.py`
- `mcp_server/src/rook/agent/chat/model_status.py`
- `mcp_server/src/rook/bridge.py`

### Governing architectural evidence

- [Architectural Reset](../2026-08-17-coordinating-intelligence-architectural-reset.md)
- [Mechanism Dispositions](../2026-08-17-coordinating-intelligence-mechanism-dispositions.md)
- [Evidence Ledger](../2026-08-17-coordinating-intelligence-evidence-ledger.md)
- [Candidate Architectures](../2026-08-17-coordinating-intelligence-candidate-architectures.md)

### Prime and model evidence

- [Prime Upstream T3 Compatibility Smoke V3](2026-08-19-prime-upstream-t3-compatibility-smoke-v3-execution.md)
- [GPT-5.6 Sol Vessel Design Baseline V2](2026-08-20-gpt56-sol-vessel-design-baseline-v2-execution.md)
- [GPT-5.6 Sol Vessel Topology Refinement](2026-08-20-gpt56-sol-vessel-topology-refinement-v1-execution.md)
- [GPT-5.6 Sol Vessel Implementation V1](2026-08-20-gpt56-sol-vessel-implementation-v1-execution.md)
- [GPT-5.6 Sol Codex Vessel Postmortem](2026-08-20-gpt56-sol-codex-vessel-postmortem-record.md)
- [Qwen/Sol-Plan Vessel Execution](2026-08-26-qwen38-sol-plan-vessel-execution-v1.md)
- [Qwen Native/Python Authoring-Lane Screen](2026-08-19-qwen38-native-python-authoring-lane-screen-v1-execution.md)
- [Qwen Python Point-Lattice Confirmation](2026-08-19-qwen38-python-lane-point-lattice-confirmation-v1-execution.md)
- [Compact Prime Capture Qualification](2026-08-20-prime-json-event-capture-offline-qualification.md)

### Earlier RookChat prototypes

- [ChatRunner MCP Capability-Parity Bridge](../specs/2026-08-04-chatrunner-mcp-capability-parity-bridge-design.md)
- [ChatRunner Headless Recorder](../specs/2026-08-04-chatrunner-headless-qualification-recorder-design.md)
- [Worker-First C# RookChat Integration](../specs/2026-08-01-rookchat-worker-first-csharp-integration-design.md)

Those prototypes contain useful tests and lessons, but they do not define the
new product runtime. The Worker-first path was deliberately isolated from
ordinary conversation and later hidden. The ChatRunner parity bridge solved a
real tool-surface mismatch, but Prime makes that second model loop unnecessary.

## What exists today

The current product path is:

```text
C# RookChat panel
-> local nonce-protected aiohttp chat service
-> ChatRunner and in-memory ConversationStore
-> LiteLLM provider call
-> ChatRunner progressive tool registry and execution policy
-> ToolDispatcher or canonical MCP gateway
-> bridge.py
-> RookNative and managed Grasshopper bridge
-> Rhino / Grasshopper
```

RookChat is presently much more than a view. It independently owns:

- provider selection and LiteLLM invocation;
- conversation messages and cancellation repair;
- prompt construction and runtime-health injection;
- a 50-round model/tool loop and meta-only loop policy;
- progressive tool disclosure;
- tool dispatch and result annotation;
- model discovery, eligibility, and routing;
- an in-memory conversation lifetime; and
- a custom event projection into the panel.

The relevant implementation is substantial:

| Current owner | Lines |
|---|---:|
| `chat_runner.py` | 1,495 |
| `server.py` | 1,135 |
| `model_status.py` | 685 |
| `conversation_store.py` | 182 |

Prime already owns the first seven responsibilities with stronger session,
compaction, provider, queue, and recovery behavior. Keeping them in both places
would make the migration a permanent synchronization problem.

## What should be preserved

The current RookChat product has several good seams that should survive.

### C# panel and document lifecycle

`RookChatPanel` already maintains separate tab collections per Rhino document.
Each `AgentChatTab` retains the document serial number captured when it is
created. The panel already streams NDJSON, displays assistant text and tool
cards, handles cancellation, applies model updates, and reconnects after the
local chat service restarts.

This is the right user and document boundary. It should not become an agent
runtime.

### Local service supervision

`ChatServiceManager` already:

- starts one hidden local service for the Rhino process;
- uses a per-service nonce on non-health requests;
- discovers an OS-assigned port;
- validates an installed runtime manifest;
- tails service logs without inheriting Rhino's file handles; and
- restarts and health-checks the service.

Option A can retain this entire process boundary. The Python service becomes a
Prime process/session broker rather than an LLM runtime.

### Rook's panel lock and host truth

The existing Claude integration and `rook_full` adapter establish the intended
targeting pattern:

```text
ROOK_MCP_TARGET_MODE=panel_locked
ROOK_MCP_TARGET_PROCESS_ID=<captured Rhino process>
ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER=<captured document>
```

Rook remains the only owner of target identity, mutation, solve readiness,
receipts, diagnostics, and host evidence. Prime must not recreate those facts.

### Existing panel HTTP contract

The C# client already knows stable product concepts:

```text
health
start conversation
set model
send/stream message
cancel/stop
structured UI response
```

Those concepts still apply. Keeping the HTTP and NDJSON boundary stable during
the first migration prevents a backend replacement from becoming a panel
rewrite.

## What Prime has already established

The active experimental baseline is:

```text
Prime commit   739400844f8f3f280414b0c7b9c65797208815d3
base upstream  f8f0036c
fork delta     one structured MCP-error patch, two files
```

The compatibility smoke established the exact Prime/Rook execution path with a
branch-local `rlm`, content-equivalent external-kernel `goal`, a complete
Grasshopper repair, control exercise/restoration, and normal completion.

Prime's supported local integration surfaces include:

- `--mode rpc`, a public JSONL subprocess protocol;
- `AgentConnection`, the TypeScript UI-to-execution boundary;
- `DaemonAgentConnection`, with resident workers, snapshots, cursors, and
  reconnect;
- ACP, a standard but narrower external protocol;
- saved sessions, compaction, steering, follow-up, and cancellation;
- model and resource catalogs;
- image input;
- explicit external skills;
- OAuth-backed frontier providers and local model providers; and
- the bundled Serper web-search skill.

### Model-free probes performed for this assessment

On the exact `739400844` worktree, `--mode rpc` returned a valid `get_state`
response on Windows with:

```text
session identity and file
selected model and thinking level
streaming and compaction state
queue state
goal state
```

A second model-free RPC launch used:

```text
--no-skills
--skill <exact Rook skill path>
```

and `get_commands` returned exactly the selected external skill. This proves an
explicit skill allowlist is possible. Without `--no-skills`, the same launch
also exposed Prime's built-in goal, attach-image, compact, websearch, and agent
skills.

No provider, Rhino, Grasshopper, or Rook call occurred in either probe.

## Product ownership model

The new primary path should obey this table.

| Responsibility | Owner |
|---|---|
| Text composer, attachments, tabs, visible transcript | RookChat C# |
| User confirmation and consequential authorization | RookChat C# |
| Rhino process and document selection | RookChat C# plus Rook target admission |
| Conversation-to-Prime-session mapping | Local backend bridge |
| Model catalog, provider call, reasoning level | Prime |
| Durable conversation history | Prime session store |
| Prompt/tool loop, queues, cancellation, compaction | Prime |
| Skill loading and IPython | Prime |
| Rook capability discovery and calls | Productized `rook_full` adapter |
| Rhino/GH mutation and observation | Rook |
| Open-ended design and completion judgment | Selected model |
| Final acceptance | User |

The local backend bridge must remain intentionally thin. It may translate
events, supervise processes, and bind product identity. It must not build
prompts, choose tools, interpret geometry, retry model behavior, or maintain a
second conversation history.

## Product requirements learned from the experiments

These are not speculative feature requests. Each corresponds to observed value
or an observed failure.

1. **Images are first-class input.** Sol's strongest design result began from
   actual image blocks. RookChat currently displays images but does not submit
   image attachments in `AgentChatClient.SendMessageStreamingAsync`.
2. **Viewport images must reach the model.** Structural snapshots alone do not
   establish visual quality. The Qwen multimodal and Codex Vessel runs improved
   when the model could inspect real captures.
3. **Web search is an advisory capability.** Published dimensions and counts
   materially informed the successful Codex Vessel hypothesis. Prime already
   has an explicit Serper skill and credential owner. Search cannot override
   live Rook evidence.
4. **User steering is normal, not failure.** The successful Codex run used a
   consequential user correction to expose a wrong graph despite passing
   counts and connectivity.
5. **The model needs durable context and compaction.** Long tasks crossed
   multiple model calls and one successful compaction. Prime owns this.
6. **Final evidence must be fresh and receipt-fenced for mutating work.** This is
   skill guidance backed by Rook receipts, not a semantic acceptance service.
7. **Local models remain optional.** Qwen provided useful bounded execution but
   repeatedly showed weaker topology judgment and high orientation cost. The
   default product model should not be chosen to preserve a local-model
   experiment.
8. **A scripting lane is valuable but not universal.** The Python lane reduced
   discovery and produced credible results across multiple compact geometry
   families. It should remain explicitly selected rather than silently routed.
9. **Operational traces must be compact.** The 3.54 GB capture came from
   cumulative event serialization, not model context. The product should retain
   Prime's session plus bounded operational logs, not a duplicate raw stream.
10. **Truthful Rook feedback is more valuable than semantic supervision.** The
    connection-truthfulness repair changed the agent's ability to reason about
    the actual canvas. This remains the deterministic priority.

## Adoption gaps that are real

Prime is qualified for the experimental path, but the following product work
is still required.

### Runtime packaging

The qualified Prime baseline lives in a development worktree. A shipped product
cannot depend on `D:/prime-agent/...` or a moving global installation.

The product must either:

- bundle a pinned Prime distribution and compatible Node runtime; or
- declare and verify a separately installed Prime prerequisite.

Bundling is the stronger eventual product posture. The integration vertical can
start against the pinned worktree while packaging remains a separate gate.

### Productize the Rook adapter core

The experimental `rook_full` adapter proves the valuable contract:

```python
await rook_full.search(query)
await rook_full.read(name)
await rook_full.call(name, arguments)
```

and returns validated capability payloads while preserving structured failures.
Its current file is not directly shippable: it hard-codes local installation
paths and includes campaign-specific source-log and lifetime call-limit
requirements.

The product slice should promote only the three-function payload contract and
panel-locked environment binding into an installed package. Runtime paths come
from the installed Rook manifest or environment. Research-only acceptance and
campaign quota ownership do not move with it.

### Authentication onboarding

Prime already stores provider OAuth and API-key credentials in its own
`auth.json`; RookChat must not copy secrets into its configuration. The first
product slice can:

- report configured/unconfigured provider status;
- use Prime's model catalog; and
- open Prime's supported login flow when credentials are missing.

An embedded RookChat OAuth UI is optional later work, not a backend prerequisite.

### Image composer

The panel needs an attachment button/drop target and a bounded message payload
containing image bytes and MIME type. Prime RPC already accepts this shape.

### Tool presentation

Prime's model-facing tool is IPython. The first product vertical should render
an IPython execution card and its result. It must not parse Python source to
pretend that nested `rook_full` calls are first-class Prime tools.

If users later need one card per Rook operation, add a truthful Rook-owned
progress projection. Do not infer it from cell text in the initial migration.

### Goal semantics

The backend replacement does not require every message to become a persistent
Prime goal. Ordinary conversation should use ordinary Prime prompts. An
explicit execution/task mode may start a goal and load a completion-disciplined
skill. This keeps the suspended terminalization work out of the cutover.

## Option A: RPC-first replacement

### Shape

```text
RookChat C# panel
-> existing local HTTP/NDJSON chat service
-> PrimeRpcConversation
-> prime-agent --mode rpc
-> Prime AgentSession + IPython + explicit skills
-> product rook_full adapter
-> Rook MCP gateway
-> RookNative / companion
-> Rhino / Grasshopper
```

### New production owners

The Python chat service gains three small owners:

1. **Prime RPC process:** starts the exact pinned Prime command, writes
   correlated JSONL commands, reads events, and stops the owned process.
2. **Durable conversation registry:** stores one atomically replaced file per
   panel-stable RookChat conversation ID, containing a schema version, Prime
   session ID/file, selected model, immutable Rhino target fingerprint, and last
   lifecycle state. The target fingerprint is Rhino PID plus the Rhino
   process-start UTC fingerprint plus document runtime serial. The Python broker
   owns this serializable registry.
   The C# tab creates and retains the stable ID across chat-service reconnects
   instead of discarding it. Prime, not the registry, remains the transcript
   owner.
3. **Event projector:** converts Prime's public events to the existing RookChat
   stream without interpreting design meaning.

The registry is a directory of small atomically replaced broker records, not
another message store or transcript database. A namespace-wide writer lock
serializes updates without rewriting sibling conversation files. Process
handles, pipe objects, launch generation, pending command, and activity
timestamp are owned only by the broker's in-memory runtime table and are never
reconstructed from a persisted PID. Each Rhino process generation has one
registry namespace and one writer. No generalized backend framework is needed.
One narrow interface is enough to keep handlers testable:

```text
start
state/models
prompt_and_wait(images)
set model/thinking
abort
close
```

### Launch policy

Each conversation launch binds:

- exact Prime executable/bundle identity;
- exact Rhino process and document environment;
- one dedicated Prime session directory or resumable session file;
- configured model and reasoning level;
- IPython as the model-facing tool;
- no context-file, extension, template, or ambient skill discovery;
- an explicit skill allowlist; and
- per-session operational log paths.

The initial allowlist should be small and visible in product configuration:

```text
Rook runtime skill
goal skill only for explicit task mode
websearch when configured
compact when agent-callable compaction is desired
optional Grasshopper Python lane only when explicitly selected
```

User-uploaded images travel directly in RPC `prompt.images`; they do not need a
model-visible filesystem skill. Keep `attach-image` disabled initially. It may
be admitted later for a separately defined need, such as letting the model load
a Rook-produced viewport file that is not already in the prompt.

### Event projection

| Prime event | RookChat projection |
|---|---|
| text delta | existing `text_delta` |
| IPython tool start | existing `tool_start`, name `ipython` |
| IPython update/end | existing `tool_result` with bounded display data |
| image content/result | additive image event and existing image renderer |
| model/thinking change | existing/additive model state event |
| compaction/status | additive status event |
| extension UI request | existing `ui_block` where shapes correspond |
| `agent_end` | bounded agent-segment status only; never product `done` |
| correlated `prompt_and_wait` settlement | existing `done`, completed-before-cancel, cancelled, or failed |
| runtime error | existing `error` |

The projector retains only deltas needed for the live UI and the final terminal
message. Prime's own session is the durable transcript.

### Session behavior

The first vertical is deliberately single-flight. Its conversation lifecycle is:

```text
idle -> running -> idle
idle -> running -> cancel_requested -> idle (aborted | completed_before_abort) | failed
idle | running | cancel_requested -> failed on process or protocol loss
```

A normal panel message sends correlated `prompt_and_wait` only from `idle`.
Slice 1 must expose Prime's established ACP headless-turn sequence through the
public RPC surface: capture a compaction-safe pre-turn transcript boundary, call
`AgentSession.promptAndWait()`, await `waitForHeadlessCompletion()`, then inspect
only the new terminal transcript for provider/model failure. Raw `agent_end`,
`isStreaming` polling, quiet timers, or counts of agent segments cannot settle a
product turn. Submission remains disabled while `running` or
`cancel_requested`; there is no mid-run `steer` or `follow_up` in the first
vertical. One conversation-scoped abort endpoint sends Prime `abort`. The panel
displays `cancel_requested` and refuses another prompt until the correlated
Prime-owned prompt settlement reports completion, abort, or failure. If natural
completion wins the race after cancellation is requested, the broker records
`completed_before_abort` and ignores the later abort response for that completed
command generation. Local stream cancellation, `agent_end`, and non-streaming
observations alone never declare the conversation idle.

The C# tab keeps its stable conversation ID across a chat-service restart. The
broker uses that ID to read the atomic registry, verifies the same Rhino PID,
process-start fingerprint, and document serial, opens the exact saved Prime
session in a new RPC process, and refreshes the panel from `get_messages`. A
missing registry/session or target mismatch fails restoration rather than
silently creating new history or rebinding Rook authority. A persisted
`running` or `cancel_requested` state becomes `failed` with an interruption
reason on broker restart; it never becomes `idle` by inference. Recovery from
`failed` requires an explicit reopen operation or a new conversation. Seamless
recovery of a turn that was in flight is not promised. That remains Option B's
main advantage.

Session persistence is separate from process residency. Initial resource policy
preserves the current finite defaults: at most 10 resident Prime RPC children
per broker and retirement after 30 idle minutes. Idle retirement closes the
owned process/kernel but preserves the registry entry and Prime session. To
admit another resident child, the broker retires the least-recently-used idle
child; if all 10 are `running` or `cancel_requested`, launch is refused with a
capacity error.

The in-memory runtime table owns the process handle, monotonically increasing
launch generation, pipes, pending command, and activity timestamp. Events from
a retired generation are ignored. Tab close marks the conversation closed and retires its child; it is not an
automatic session deletion. Document close retires the child and marks the
immutable target unavailable, so later restoration cannot acquire Rook mutation
authority for a replacement document. Service shutdown atomically preserves the
registry, requests abort for active children, and uses one 10-second global
drain window before terminating remaining owned process trees. Cleanup is
idempotent. Prime session files remain subject to an explicit product retention
policy rather than process-lifetime deletion.

### Advantages

- Preserves the C# panel and current local service contract.
- Replaces the duplicated LLM loop quickly.
- Uses a documented Prime embedding protocol.
- Supports Sol, local models, images, skills, compaction, cancellation, and
  saved sessions.
- Can be tested with a fake RPC subprocess and recorded Prime events.
- Keeps Node/Prime process handling outside Rhino.
- Creates a real vertical before committing to daemon-specific APIs.

### Costs and risks

- One Prime process per active tab.
- A service or RPC process loss requires session reopen rather than transparent
  cursor-based reattachment.
- Public RPC streaming still carries cumulative partial objects alongside
  deltas; the projector must consume deltas and avoid retaining cumulative
  copies.
- Prime extension UI and resource catalogs need explicit mapping into the
  existing HTTP API.
- The product still ships a Python broker plus Node/Prime.

### Qualification sequence

1. Model-free RPC protocol, ACP-equivalent headless prompt settlement across
   compaction continuation and multiple `agent_end` segments, transcript-visible
   provider failure, cancel-versus-completion races, exact skill allowlist, model
   catalog, image payload, cancellation, and process cleanup tests.
2. Recorded-event projection tests against the existing C# event parser.
3. One text-only Sol session with no Rook access.
4. One known read-only Rook inspection under the captured document lock.
5. One previously qualified small Grasshopper smoke with final receipt custody.
6. One image-plus-web design conversation using direct RPC image input.
7. Service restart and saved-session restoration with no mutation in flight.
8. Capacity, idle retirement, tab/document close, and bounded service-shutdown
   cleanup tests.

The cutover can proceed after these product behaviors pass. It does not require
replaying the historical campaign corpus.

## Option B: AgentConnection-native bridge

### Shape

```text
RookChat C# panel
-> local HTTP/NDJSON Prime bridge written in Node/TypeScript
-> Prime DaemonAgentConnection
-> Prime daemon supervisor and resident session worker
-> AgentSession + IPython + explicit skills
-> product rook_full adapter
-> Rook MCP gateway
-> Rhino / Grasshopper
```

The Node bridge replaces the Python chat service. It uses the same client-side
boundary as Prime's own interactive UI.

### Why it is architecturally attractive

`AgentConnection` is explicitly designed to keep a rich UI transport-agnostic
while a separate owner runs providers, tools, kernels, queues, compaction,
scheduling, persistence, and descendants. `DaemonAgentConnection` adds:

- resident workers that survive UI detachment;
- coherent snapshots on attach;
- generation-aware event cursors;
- bounded reconnect and resynchronization;
- idempotent command IDs and uncertain-mutation refusal;
- model and resource snapshots;
- session navigation and trees; and
- serializable extension UI requests.

This most closely matches the desired final ownership model.

### Advantages

- Strongest session continuity across panel and bridge restarts.
- Native access to Prime state, resource, model, queue, and session APIs.
- No duplicate conversation store.
- Better long-term support for steering, session navigation, subagent
  observation, schedules, and richer Prime UI integration.
- Avoids adapting a subprocess public protocol back into TypeScript concepts.

### Costs and risks

- Introduces and ships a new Node service rather than reusing the installed
  Python chat service.
- Directly depends on Prime's local TypeScript contracts. Prime documents that
  some `AgentConnection` types reuse internal message/model types and are not a
  stable hosted-network promise.
- Requires daemon startup, attach, cursor, snapshot, and bridge lifecycle tests.
- Requires new installer and service-manifest work immediately.
- Makes the first backend cutover depend on resident-session recovery behavior
  that ordinary single-user RookChat may not initially need.

### Qualification sequence

1. Model-free Node bridge creation and `DaemonAgentConnection` attach.
2. Session snapshot, detach, bridge restart, reattach, and transcript refresh.
3. Command-ID and uncertain-result handling through a killed bridge process.
4. Model catalog, explicit skills, images, auth status, and extension UI.
5. The same known Rook inspection and Grasshopper smoke used for Option A.
6. Rhino document close/reopen behavior with a resident Prime session that can
   no longer mutate its former document.

### When to choose it first

Choose Option B as the first implementation only if these are day-one product
requirements:

- active model work must survive panel/service/Rhino UI detachment;
- multiple UI clients must attach to one live Prime session;
- Prime session trees and extension UI are core initial features; or
- replacing the Python chat service is already an accepted packaging change.

Otherwise its added surface is premature.

## Rejected primary options

### Direct ACP from C#

ACP is a useful standard compatibility surface and would resemble the existing
Claude subprocess tab. It supports prompts, images, cancellation, text,
reasoning, and IPython tool events.

It is not the best primary RookChat backend because it intentionally exposes a
narrower session model. Prime-only goals, compaction control, resource catalog,
queues, session navigation, and extension UI live in `_meta` or are absent. One
session per process is also fixed. ACP remains a useful fallback or future
external-client compatibility path.

### Direct daemon protocol from Python or C#

Rejected. It would bypass Prime's `AgentConnection` adapter and make Rook own
framing, protocol versions, snapshots, cursors, reconnect, and command journals.
That is exactly the integration burden Prime already encapsulates.

### In-process AgentSession in the existing Python service

Rejected. Prime's SDK is TypeScript. Embedding it in Python would require a
language bridge while still exposing lower-level runtime ownership. RPC is the
supported KISS boundary for a Python host.

### Rewrite RookChat as the suspended Planner/Worker/Reviewer system

Rejected. The architectural reset and mechanism disposition pass explicitly
suspend the seven-stage router and legacy autonomous role stack. The empirical
model/Rook loop produced the relevant product evidence.

### Keep ChatRunner as fallback intelligence

Rejected as a normal product path. It preserves duplicate provider, history,
prompt, tool, and cancellation ownership. A short-lived feature flag for
rollback during migration is reasonable; dual active backends are not.

## Recommended path

Proceed with **Option A, RPC-first replacement**, while preserving a clean
internal boundary that can later be implemented by Option B.

This recommendation is based on four facts:

1. The existing C# panel and Python service already provide useful product
   lifecycle and document scoping.
2. Prime RPC is a supported, functioning Windows embedding path on the qualified
   baseline.
3. RPC exposes the capabilities needed for the first product version and later
   growth, including images, models, thinking, skills, sessions, cancellation,
   compaction, and deferred steering.
4. The unresolved question is product integration quality, not another agent
   architecture. Option A answers it with the fewest simultaneous changes.

Do not implement Option A and Option B in parallel. After the vertical is used
in RookChat, evaluate one concrete question:

> Is saved-session reopen after a bridge restart adequate, or does RookChat need
> transparent attachment to still-running sessions?

If reopen is adequate, Option A can remain the product architecture. If live
reattachment is materially valuable, replace the bridge internals with Option B
while keeping the panel HTTP contract and Rook ownership unchanged.

## Recommended implementation slices

### Slice 0: product contract

Freeze a short contract, not another broad North Star:

- the Python broker's directory of atomic per-conversation records durably owns
  the mapping from one panel-stable RookChat conversation ID to one schema
  version, Prime session ID/file, selected model, immutable target fingerprint,
  and last lifecycle state;
- process handles, generations, pipes, pending commands, and activity timestamps
  are in-memory runtime state only;
- each Rhino process generation owns one registry directory and one
  namespace-wide writer lock, and sibling records survive independent updates;
- the C# tab retains that stable conversation ID across service reconnects;
- one captured Rhino PID/process-start fingerprint/document-serial tuple is
  immutable for that session's Rook authority;
- target restoration requires that exact tuple and never rebinds an old session
  to a replacement target;
- Prime is the only model/history/tool-loop owner;
- Rook is the only host-truth owner;
- the bridge translates but does not reason;
- product completion requires a prompt-correlated settlement owned by Prime and
  exposed through the existing ACP headless-turn sequence; raw `agent_end` is
  only an agent-segment boundary;
- the initial lifecycle is `idle -> running -> cancel_requested -> idle/failed`,
  including explicit `aborted` and `completed_before_abort` race outcomes, with
  normal completion also returning `running -> idle`;
- persisted `running` or `cancel_requested` restores as `failed`, and recovery
  requires explicit reopen or a new conversation;
- the first vertical has no mid-run steering or follow-up;
- session persistence is independent from bounded process residency;
- user images use direct RPC prompt attachments while `attach-image` remains
  disabled;
- capacity, idle retirement, tab/document close, service shutdown, and bounded
  process/kernel cleanup are deterministic;
- ordinary prompts and explicit execution goals remain distinct;
- no ambient skills, context files, extensions, or templates enter the initial
  runtime; and
- no campaign evaluator or acceptance artifact enters product execution.

### Slice 1: model-free RPC backend

Implement process startup, strict LF JSONL framing, request correlation, a
Prime-owned correlated `prompt_and_wait` settlement, the per-conversation atomic
registry,
stable session/target identity, split durable/in-memory ownership, `get_state`,
model catalog, set model/thinking, conversation-scoped abort, finite residency,
and bounded clean shutdown. Use a fake Prime child and branch-local real offline
probes. Do not begin Slice 2 until prompt settlement has a concrete RPC contract
and causal tests spanning compaction continuation, transcript-visible provider
failure, and cancellation racing natural completion.

No Rhino or provider contact is needed.

### Slice 2: panel streaming cutover

Route one existing `AgentChatTab` through Prime. Preserve text streaming,
errors, done, status, and model selection. Replace immediate local cancellation
with `cancel_requested` until backend quiescence is confirmed. Keep submission
disabled during `running` and `cancel_requested`; do not add steering. Replace
personas with one Rook session identity for the first vertical rather than
translating legacy persona prompts into Prime.

At this point `ChatRunner` is bypassed but retained behind a rollback flag.

### Slice 3: product Rook adapter and target lock

Install the environment-driven payload-first adapter. Launch the Prime session
with the captured process/document environment. Prove a read-only inspection
cannot drift to another open document.

### Slice 4: one known mutating smoke

Use the current qualified Prime baseline and a small previously successful
Grasshopper task. Require:

- authentic Rook mutation;
- local repair if needed;
- final receipt wait and same-receipt snapshot;
- clean completion or honest incomplete report;
- no hidden evaluator feedback; and
- panel cancellation that stops future model activity.

### Slice 5: images, web, and later steering

Add direct RPC panel attachments, image result rendering, and the explicit
Serper skill. Evaluate steering as a separate addition after the single-flight
lifecycle is qualified. Admit `attach-image` only if a concrete model-requested
local-file workflow requires it. Keep webpage fetching outside this slice unless
a specific product need and containment policy are separately defined.

### Slice 6: persistence and cutover

Restore a saved Prime conversation after chat-service restart, render its
transcript, and refuse Rook mutation if the original document no longer exists.
Then make Prime the default backend, retain ChatRunner only as a temporary
rollback flag, and remove it after a short stabilization period.

### Slice 7: packaging

Bundle or explicitly provision:

- pinned Prime distribution;
- compatible Node runtime;
- external kernel/bootstrap;
- product Rook adapter;
- explicit skills;
- version/health diagnostics; and
- Prime-owned credentials.

Run the existing upstream compatibility smoke pattern against the packaged
bytes. Do not run the historical campaign suite as an installer gate.

## Validation matrix

This is the full product matrix. The first implementation plan covers only the
Slice 1-2 rows: backend ownership, durable session/target identity, text and
error projection, cancellation lifecycle, and cleanup. Later rows remain design
context rather than work authorized by that plan.

| Area | Required evidence |
|---|---|
| Backend ownership | No LiteLLM call or ChatRunner loop on Prime path |
| Session | Stable conversation ID and exact Prime session ID/file survive broker restart through the single-writer, per-conversation atomic registry |
| Target | Exact Rhino PID/process-start fingerprint/document serial bound before model contact |
| Model | Prime catalog and selected provider/model/reasoning shown |
| Auth | Credential status only; no secret copied through RookChat |
| Skills | Exact allowlist reported; ambient resources excluded |
| Text | Delta stream, final message, and error projection; raw `agent_end` never emits product `done` |
| Images | User image reaches Prime; model image result reaches panel |
| Web | Serper search succeeds or reports missing credential clearly |
| Tool | IPython start/result shown without parsing nested Python |
| Rook | Structured failure survives through Prime and panel |
| Mutation | Receipt, readiness, and same-receipt final observation |
| Steering | Deferred; later addition cannot weaken the qualified single-flight lifecycle |
| Cancellation | UI remains `cancel_requested` until correlated prompt settlement; natural completion records `completed_before_abort`; no new prompt or automatic mutation replay |
| Compaction | Session continues and UI receives a bounded status event |
| Restart | Transcript reloads; in-flight ambiguity is reported honestly |
| Storage | Prime session plus bounded logs; no cumulative stream archive |
| Cleanup | Capacity, idle retirement, tab/document close, and service shutdown close owned processes within the bounded policy |

## Primary risks and controls

### Target lifetime

A Prime session may outlive its Rhino document. The bridge must treat target
identity as immutable and Rook must refuse a missing/replaced target. Resuming a
conversation does not automatically restore mutation authority to a new
document. PID alone is insufficient: the binding includes the C# host-observed
Rhino process-start UTC fingerprint and document runtime serial.

### Ambient Prime resources

Prime can discover built-in and user skills. Initial RookChat launches should
use `--no-skills`, `--no-extensions`, `--no-context-files`, and
`--no-prompt-templates`, then add the exact approved skills explicitly.

### IPython authority

Prime's kernel runs as the user and is not an OS sandbox. Panel locking governs
the supported Rook adapter path; it does not prevent hostile Python from using
filesystem, process, or network access. Preserve this as an explicit product
boundary. Do not reopen the suspended terminalization protocol to imply stronger
containment.

### Fork maintenance

The active Prime baseline differs from upstream by the structured MCP-error
patch. Keep that patch isolated, track upstream, and qualify updates with one
known compatibility task. Do not rebase historical evidence.

### Event volume

Never archive every cumulative RPC `message_update`. Project deltas to the UI,
use terminal messages and Prime's saved session for history, and retain bounded
Rook operational events separately.

### Model-facing finality

`goal.complete()` is behavioral finality, not hostile-kernel containment. The
product should rely on the proven skill discipline and authentic final evidence,
not the suspended host terminalization design.

### Scope creep through UI parity

The first vertical does not need every Prime TUI feature. Model catalog, prompt,
tool activity, confirmed cancel, bounded process cleanup, and session restore
are sufficient. Images, web search, steering, compaction status, session trees,
schedules, subagent dashboards, and rich extension widgets can follow observed
demand.

## What should not move into production

- The seven-stage acceptance workflow router.
- Phase A or Phase B semantic manifests as runtime requirements.
- Hidden campaign evaluators.
- The terminalization/dispatch-gate protocol.
- Campaign hash manifests and pre-contact ceremony.
- The 3.54 GB raw event-capture pattern.
- Automatic Sol-to-Qwen delegation.
- Legacy Planner/Guardian/Conductor routing.
- ChatRunner's duplicated provider and tool loop.
- Automatic Python/native lane selection before it is empirically justified.

The reusable qualification assets are narrower: known smoke tasks, exact
runtime identity checks, structured-error tests, final receipt custody tests,
image delivery tests, compaction continuation tests, and bounded event-capture
regressions.

## Decision summary

The most grounded starting point is:

```text
existing RookChat panel and local HTTP service
-> Prime RPC session per tab
-> explicit Prime model and skill allowlist
-> productized payload-first rook_full adapter
-> existing panel-locked Rook runtime
```

This gives RookChat the full intelligence harness that the experiments actually
validated while preserving the simplest ownership model. It also creates a
clean evidence-driven decision later: remain on RPC if session reopen is
adequate, or adopt `DaemonAgentConnection` if resident reattachment proves
materially valuable.

The concise [Slice 0 product contract](../specs/2026-08-26-rookchat-prime-primary-backend-slice-0-contract.md)
is the next independent-review artifact. Only after it is approved should an
implementation plan cover Slices 1-2. It should not plan all eight slices or
become another architecture search.
