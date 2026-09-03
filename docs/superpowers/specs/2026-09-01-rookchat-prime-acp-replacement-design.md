# RookChat Prime ACP Replacement Design

**Status:** Approved architectural design for independent review

**Date:** 2026-09-01

**Rook design baseline:** `f840069a58d0a5ee297ae817f0b3efe7a9287512`

**Prime upstream baseline:** `c718bf3c30fd8da206ed551837cbb54f7ad15948`

**Reviewed Prime compatibility precursor:**
`9c25468b62c79fc4b1419d7800740e8e41e30467`

**Prime product compatibility patch:** one final independently reviewed commit
directly over the upstream baseline. It replaces the precursor and contains only
daemon-free ACP selection, platform-aware kernel-interpreter resolution, and
completion of Prime's standalone Python-runtime payload. Its exact commit is
frozen before the release build.

**Protocol dependencies:** Prime ACP SDK `1.3.0`; Python
`agent-client-protocol==0.12.1`

## 1. Recovery Record

The private Prime RPC integration is superseded. Its Slice 0-4 work and Gate 7
runtime-topology work must not enter the product. Those efforts accumulated a
private Prime fork for RPC settlement, daemon selection, worker authentication,
process identity, session leases, kernel preparation, and runtime control. Gate
7 also caused an unacceptable Windows process storm during qualification.

All dirty and quarantined Task 7 Rook and Prime worktrees and all retained
evidence remain historical records. They are not reset, cleaned, executed,
deleted, selectively copied, or treated as an implementation source.

The work leaves useful evidence, not reusable product machinery:

- Prime must run without starting or contacting its shared daemon.
- RookChat must own exactly one directly launched Prime process per open
  conversation.
- Prime session persistence must remain Prime-owned.
- Rook target admission, receipts, readiness, and evidence remain authoritative.
- Failed or ambiguous operations are never replayed automatically.
- Qualification evidence must be finite, frozen, and external to product code.

The replacement uses Prime's supported ACP surface plus one independently
removable compatibility patch. The reviewed `--no-daemon` precursor is folded
into that single final commit rather than extended as a patch stack. The two
additional changes make Prime's existing kernel and release paths function as
documented on Windows; they do not add a Rook protocol or kernel. No other
private Prime change is part of this design.

## 2. Objective And Scope

RookChat becomes the first-class Prime user interface inside Rhino:

```text
RookChat C# panel
-> authenticated local HTTP
-> Python chat service and ACP client
-> one Prime `--mode acp --no-daemon` process
-> Prime sessions, goals, compaction, IPython, and MCP
-> versioned `rook-full` skill and Rook MCP server
-> RookNative and the managed Grasshopper bridge
-> Rhino and Grasshopper
```

The existing panel and Python service boundary remain. ChatRunner is removed at
cutover. The Python service is the only ACP client; C# never implements ACP.

This design covers ownership, ACP lifecycle, durable identity, current-turn
streaming, bounded presentation history, Rook capability delivery, target
custody, cancellation, errors, images, model selection, authentication,
packaging, replacement, and qualification.

It does not design:

- a semantic supervisor or terminalization system;
- campaign execution inside RookChat;
- automatic replay or operation recovery;
- a credential editor;
- a Prime updater;
- historical-runtime garbage collection;
- session migration between Prime versions;
- a durable attachment or thumbnail store;
- automatic retargeting to another Rhino or Grasshopper document;
- hostile Python or arbitrary-code containment;
- compaction or IPython restoration guarantees not separately qualified.

## 3. Ownership

### 3.1 RookChat C#

RookChat C# owns user-input capture and presentation. Prime owns interpretation
of that input. The panel owns tabs, controls, live rendering, user-visible
status, and the authenticated HTTP conversation with the Python service.

### 3.2 Python Chat Service

The Python service owns:

- the durable RookChat-to-Prime association;
- the cross-service conversation `open.claim` fence;
- one optional directly owned ACP process and connection per open conversation;
- ACP request and response correlation;
- single-flight prompt admission;
- bounded current-turn projection;
- the disposable presentation cache;
- the verified Prime runtime identity;
- the immutable Rook host and Rhino-document binding;
- ACP cancellation initiation and direct-child cleanup.

It does not own reasoning, transcript reconstruction, goals, compaction,
semantic completion, tool planning, mutation truth, or operation replay.

### 3.3 Prime

Prime owns reasoning, transcript, goals, compaction, model context, provider
interaction, authentication, settings, IPython, and semantic completion.
Prime's session JSONL is the sole model-conversation authority.

### 3.4 Rook

Rook owns capability profiles, live host identity, Rhino document authority,
Grasshopper operation context, tool admission, mutations, no-op truth,
receipts, solve readiness, and host evidence.

ACP permission approval does not override Rook authority. A tool card does not
certify a mutation. Only authentic Rook results, receipts, and evidence do.

## 4. Prime Process And ACP Lifecycle

### 4.1 Direct Ownership

Each open ACP conversation has exactly one Prime process launched by the Python
service through the official Python ACP SDK. The launch uses an argument array
and the exact installed executable path. It never uses a shell, `PATH`, a
global npm installation, a Prime daemon, or process discovery.

Cleanup uses only the SDK transport and its directly owned process handle. It
never discovers, scans, or targets processes by PID or name.

Prime is launched with the approved runtime configuration, including:

```text
--mode acp
--no-daemon
--resume <exact product-assigned session file>
--no-skills
--skill <exact pinned Prime goal skill directory>
--skill <exact manifest-bound rook-full directory>
--append-system-prompt <exact rook-full/SKILL.md path>
--no-extensions
--no-context-files
--no-prompt-templates
--tools ipython
```

The Rook MCP server is declared through standard ACP `session/new` parameters.
No product-owned RPC or `AgentConnection` protocol exists.

### 4.2 Cross-Service Open Claim

Before every Prime launch, the Python service creates one `open.claim` file
atomically and exclusively. Its path is keyed by the canonical product-assigned
Prime session path as
`<claims-root>/<sha256(UTF-8 canonical-session-path)>.open.claim`. The
product-owned claims root and canonicalization version are stable product data,
recorded by the runtime compatibility contract, and must reproduce the same key
for an existing association across installation, upgrade, and rollback. The path
is never supplied by the user. If the claim already exists, RookChat returns
`session_recovery_required` before Prime starts. It does not attempt to classify
the claim as active or abandoned.

The service retains ownership of the claim for the lifetime of the resident ACP
handle. It removes the claim only after the directly owned Prime child has been
observed exited and the ACP connection has been retired. If process creation
is positively known not to have occurred, failed admission removes the claim
because no Prime child exists. A missing handle or uncertain creation outcome is
not proof that no child exists; the claim remains. Delete retains its claim
through association and artifact cleanup.

If the Python service crashes, the claim remains even though stdin closure may
cause Prime to begin asynchronous shutdown. Reopen and Delete fail closed with
`session_recovery_required`; explicit crash recovery is deferred to a later,
separately designed operation.

The claim contains no owner metadata and uses no PID, heartbeat, expiry,
stale-owner test, takeover, polling, or automatic reclamation. Its presence is
the entire crash fence. This is not a Prime session lease and not a claim that
external programs cannot open the JSONL independently.

### 4.3 Minimal State Model

RookChat persists associations, not lifecycle. The only durable control artifact
besides the validated association is the optional `open.claim` crash fence. It
contains no lifecycle or ownership record; presence only refuses launch or
deletion until a later explicit recovery design resolves it.

Resident state is either:

```text
closed

or

open(owned open.claim, direct process handle, ACP connection,
     ACP session ID, optional prompt task)
```

Prompt completion, cancellation, forced close, and presentation failure are
operation outcomes and diagnostics. They are not durable workflow states.
There is no persisted `materializing`, `interrupted`, `suspended`,
`completed_before_cancel`, or broker-owned goal state.

### 4.4 New Conversation And Materialization

A new Rook-enabled conversation requires a valid Rook host and Rhino-document
binding. Its pre-persistence state exists only in memory:

```text
service-generated provisional conversation ID and session path
-> create open.claim exclusively
-> launch Prime
-> initialize ACP
-> verify compatible protocol and session/close capability
-> session/new
-> first user prompt
-> Prime materializes the product-assigned file
-> service validates the bounded header envelope
-> service atomically creates the complete durable association
```

A successful `initialize` must report a protocol version admitted by the pinned
ACP compatibility contract and `agentCapabilities.sessionCapabilities.close`.
Missing or incompatible required capability returns `acp_incompatible` before
the first prompt. The service retires the exact child, removes the claim only
after observing that child exited, and publishes no association. Prime `_meta`
remains optional and
non-authoritative.

Prime normally does not materialize a new session file at `session/new`; the
first prompt is therefore the sole provisional turn. No second prompt is
admitted before durable publication.

If the first prompt settles without valid create-only publication, or if Prime
exits first, the still-running service retires or observes the exact child,
removes the claim only after observing that child exited, and loses the
provisional conversation. If the service itself crashes, the claim remains. The
provisional conversation is never adopted, repaired, relaunched, or replayed
automatically. Any unpublished file or claim is outside the registry and may
only be addressed by a separately designed recovery and garbage-collection
policy.

### 4.5 Prompt And Cancellation

Only one prompt is active per conversation.

ACP `session/cancel` is a notification. Stop therefore means:

```text
send session/cancel once
-> await the original session/prompt task
-> classify the original prompt result
```

- `stopReason: cancelled` is confirmed cancellation.
- Another terminal response is the prompt's natural result.
- Failure to settle within the frozen deadline makes the operation uncertain.

When settlement is uncertain, RookChat sends no more ACP requests. It closes
the SDK transport and terminates only the exact directly owned Prime process if
the SDK fallback requires it. It does not retry or replay the prompt or any
tool call. The service removes the claim only after observing the child exited;
if it cannot, the claim remains and later access requires explicit recovery.

### 4.6 Tab Close

An idle or cleanly settled conversation closes as follows:

```text
stop accepting prompts
-> session/close
-> close stdin/transport
-> bounded wait for clean Prime exit
-> remove open.claim
-> discard resident handles
```

Every phase is bounded. If `session/close` fails or does not settle, no more ACP
requests are sent. The service closes transport/stdin, waits once, terminates
only its directly owned child if necessary, removes the claim only after that
child is observed exited, and reports unclean closure. If exit cannot be
observed, the claim remains and later access requires explicit recovery.

If a prompt is active, close first follows the cancellation path. If the prompt
cannot settle, close does not stack `session/close` onto an uncertain
connection; it retires transport and the exact child directly.

A successfully completed close leaves no Prime process resident and removes its
claim. If child exit cannot be observed, closure is incomplete, the claim
remains, and Reopen and Delete continue to refuse pending separately designed
recovery. An active Prime goal remains in Prime's persisted state; close does not
complete, clear, cancel, or semantically pause it.

### 4.7 Reopen

Reopen follows one fixed admission order:

```text
read only the exact association locator needed to derive the claim key
-> create open.claim exclusively
-> re-read and validate the complete association, session envelope, and runtime
-> launch Prime against the exact recorded session file
-> initialize ACP and revalidate required capabilities
```

If re-read or validation fails before launch, the service removes the claim and
returns the relevant availability error. A successful reopen creates a new
ephemeral ACP session ID and admits no automatic prompt or goal continuation.

The standing Rook instructions require fresh observation of external Rook state
before dependent work. No persisted reorientation flag is needed.

Target unavailability does not block access to Prime's conversation. It blocks
only target-dependent Rook operations. The panel shows that the conversation is
open while its Rook target is unavailable.

### 4.8 Delete

Delete has two entry paths. If this service already owns the claim through a
live handle, it first retires the ACP connection and directly owned Prime child
and retains the claim after observing child exit. Otherwise it reads only enough
association data to derive the claim key, creates the claim exclusively, then
re-reads and validates the complete association and owned paths. An existing
claim returns `session_recovery_required` without changing any bytes. If the
post-claim re-read or validation fails, Delete removes its newly created claim
because no child was launched and returns the relevant error without deleting
the association or artifacts.

Delete removes the exact validated per-conversation association file while
holding the claim. Physical removal of the validated product-owned Prime session
and presentation artifacts is a bounded cleanup operation whose failure is
reported honestly. The claim is removed only after that cleanup attempt finishes
and no directly owned Prime child remains.

Registry deletion and artifact deletion are not described as one atomic
transaction. Exact erasure, retention, and orphan cleanup require a separate
design. Paths must be derived from the recorded product-owned roots before any
removal.

## 5. Durable Association And Prime Session Envelope

Every durable association is complete and materialized, and is reopenable when
no claim exists and custody validation passes. It stores:

- schema version;
- service-generated conversation ID;
- canonical product-assigned Prime session path;
- nonempty durable Prime header session ID;
- canonical working directory;
- immutable runtime-contract identity;
- immutable Rook capability profile;
- immutable Rook host-generation ID and Rhino document serial;
- non-authoritative requested initial model and reasoning disclosure;
- creation and presentation metadata needed by the panel.

It does not store transcript, goal contents, compaction state, model context, or
Prime settings.

Publication is create-only. The service refuses if the generated conversation
ID, registry file, or assigned session path already belongs to another
association. It never overwrites or merges an existing record.

### 5.1 Bounded Header Validation

RookChat is not a Prime session parser. It validates only the durable identity
envelope:

- canonical product-generated path beneath the product session root;
- regular file with no symlink or reparse-point escape;
- nonempty file;
- bounded first physical line;
- valid UTF-8 JSON object;
- `type == "session"`;
- supported header version;
- nonempty durable ID;
- durable ID equal to the recorded ID on reopen;
- canonically equivalent stored and recorded working directories.

RookChat does not parse, validate, migrate, repair, or reconstruct the rest of
the JSONL. Prime exclusively interprets it. If Prime rejects later contents,
open fails without file or registry repair.

### 5.2 Authority Separation

- The Prime file proves its path, header ID, working directory, and bounded
  session envelope.
- Installed manifests and launch configuration prove the runtime contract.
- Rook proves the live host, Rhino document, capability profile, and operation
  context.

Model/provider/authentication disclosure is nonsecret UI metadata. It never
overrides Prime's effective persisted settings.

## 6. ACP Stream And Presentation Cache

### 6.1 Current-Turn Transport

The Python ACP client maps standard updates to the existing authenticated HTTP
presentation boundary. Prime ACP stop reasons map without semantic invention:

| ACP stop reason | Panel outcome |
| --- | --- |
| `end_turn` | `settled` |
| `cancelled` | `cancelled` |
| `max_tokens` | `incomplete` |
| `max_turn_requests` | `incomplete` |
| `refusal` | `refused` |
| protocol or transport exception | `error` |

`settled` means only that the prompt turn ended. It does not mean the Prime
goal or user task is complete.

Tool content is preserved as ACP delivers it. Prime currently projects
`rook_full` activity primarily through the enclosing IPython call, so RookChat
does not claim that every nested Rook operation is an independent ACP tool card.

### 6.2 Bounded Callback Path

Each prompt has one ordering gate. Every ACP update callback receives a source
ordinal and has a one-second deadline covering:

```text
ordering-gate acquisition
+ projection
+ permitted coalescing
+ queue admission
```

If that complete operation cannot finish, the callback atomically signals
overflow and returns immediately. It never sends cancellation or awaits ACP
settlement from inside the callback.

Every callback is also fenced by the exact service-local Prime launch
generation, ephemeral ACP session ID, and prompt ID that created its producer.
The generation is an in-memory correlation token, not an OS process identity.
Admission rechecks the complete tuple at the ordering gate. A callback from a
retired process, replaced ACP session, settled prompt, or closed producer returns
without publishing to the panel, accumulator, or cache.

The prompt-owner task observes overflow, sends `session/cancel` once, and awaits
the original prompt task. A consumer disconnect uses the same path. The
cancellation flag is absorbing.

The live queue is bounded to 256 projected events and 4 MiB measured as UTF-8
bytes of projected panel payload. Initial coalescing is limited to adjacent,
not-yet-dequeued chunks with the same message ID for:

- `agent_message_chunk`;
- `agent_thought_chunk`.

Tool updates are not coalesced.

The current-turn accumulator is independently bounded even when the panel keeps
draining the live queue. It retains at most 256 KiB of user text and 1 MiB of
assistant text, measured as UTF-8 bytes. It tracks each field's original byte
count. When content exceeds a bound, the retained projection includes an
explicit visible truncation marker and the original byte count; omitted bytes
are never accumulated elsewhere.

### 6.3 Settlement, Cache, And Panel Drain

After Prime settles:

```text
finalize bounded turn projection
-> independently attempt cache publication
-> close the live queue producer
-> independently perform bounded panel drain
-> emit terminal panel presentation outcome
```

Cache failure does not change Prime settlement. Panel drain failure is reported
as presentation-stream failure and does not rewrite the already-settled Prime
outcome. A valid cache projection may publish even if the panel disconnected.

### 6.4 Disposable Presentation Cache

The Python service owns a cache separate from the authoritative registry. It is
never supplied to Prime and never used to infer or repair Prime state.

One settled turn is published atomically as a create-only immutable file. Here,
immutable means unchanged until whole-file eviction. Each file receives a
service-assigned monotonically increasing presentation sequence. Reopen derives
the next sequence from validated files; there is no mutable sequence ledger.
The provisional first turn is eligible for cache publication only after the
durable association has been published successfully.

Each turn may contain:

- bounded user-visible user text;
- bounded image metadata, never original image bytes;
- assistant text actually received, including partial text on cancellation;
- exact terminal ACP stop reason;
- bounded final tool-card projections.

It contains no thought chunks, raw ACP events, cumulative deltas, credentials,
secrets, or unrestricted `_meta`.

The fixed cache bounds are:

- user text: 256 KiB per turn;
- assistant text: 1 MiB per turn;
- tool content: 16 KiB per card and 1 MiB per turn;
- complete projected turn: 4 MiB;
- conversation cache: 64 MiB and 256 complete turns.

Every truncated user, assistant, tool, or metadata field carries a visible
truncation marker and its original UTF-8 byte count. If a normal bounded turn
projection cannot be constructed, the service must attempt to publish one
create-only fallback projection of at most 8 KiB containing the presentation
sequence, terminal ACP stop reason, available original byte counts, and:

> Turn presentation was unavailable. Prime retains the authoritative
> conversation state.

Failure to construct or publish that fallback remains a cache failure only; it
does not change Prime settlement or the durable association.

When a conversation limit is reached, complete lowest-sequence turns are
evicted. If the earliest retained sequence is greater than one, the panel shows:

> Earlier presentation history was omitted. Prime retains the authoritative
> conversation state.

Missing, stale, or corrupt cache data produces `presentation history
unavailable` without blocking Prime reopen.

Known Prime `_meta` indicators for goals, compaction, IPython, and UI state are
bounded and reset to unknown whenever a process/session is replaced until
freshly observed. Unknown `_meta` is limited per turn to 32 records, 16 keys per
record, 64 UTF-8 bytes per key, and 8 KiB total projected payload. Unknown values
are not fully serialized merely to measure or display them, and secret patterns
are redacted. The projection records omitted-record, omitted-key, and
omitted-value counters after any limit is reached; it does not compute an exact
byte count for unprojected arbitrary values.

## 7. Prime Goals And Product Instructions

The immutable root `rook-full/SKILL.md` is the system authorization under which
Prime may infer that clearly substantive Rook work needs a goal. Qualifying work
includes multi-step authoring, repair cycles, extended investigation, and work
likely to require continuation. Simple discussion and bounded observations
remain ordinary prompts.

Before `goal.create()`, the model inspects `goal.get()`. The model does not
replace or work around a pending goal. User-issued native `/goal` commands retain
Prime's existing authority, including deliberate replacement or clearing.

Prime remains the sole owner of goal identity, persistence, accounting,
continuation, pause, budget, error, and completion. RookChat may project bounded
Prime goal metadata but persists no shadow goal state and infers no completion.

Stop aborts the current prompt, not the goal. An active goal remains active.
Work resumes only after a later admitted prompt; no work runs merely because a
conversation reopened.

## 8. Rook Capability Delivery

### 8.1 Standard ACP MCP Transport

Every launch and reopen supplies one service-owned ACP stdio MCP declaration
named exactly `rook`. Prime owns MCP startup, transport, call lifetime, and
cleanup. RookChat does not add a Python facade or MCP proxy.

The portable Prime runtime manifest contains no machine-specific Rook MCP
command, arguments, working directory, or environment. The installed Python
service constructs the declaration from its already verified current
interpreter as exact `sys.executable -m rook`, without `PATH` fallback. It
supplies the closed product environment, capability profile, and immutable
host/Rhino binding from installed service configuration and the durable
association. The verified association working directory is supplied through
`session/new.cwd`; ACP stdio declarations do not carry a working-directory
field. User and model input cannot replace any of these values.

Prime's current generic MCP limits are accepted as product constraints:

- startup timeout: 20 seconds;
- call timeout: 60 seconds.

Representative Rook operations must qualify within them before product contact.
No facade or Prime timeout patch is introduced preemptively.

### 8.2 Markdown-Only Skill

Rook ships one immutable, manifest-bound `rook-full` skill package containing a
compact root `SKILL.md` and domain references. It has no `pyproject.toml`, Rook
Python package, contract-specific kernel, source-event recorder, campaign
limits, or transport implementation.

`--skill` advertises the skill but does not inject its full instructions.
Therefore the exact verified root `SKILL.md` is also supplied once through
`--append-system-prompt`. The broker does not parse or rewrite it. Domain
references are read through IPython only when relevant.

The skill requires the payload-first public path:

```python
result = await mcp.call_tool(
    "rook",
    "rook_tools_search",  # or rook_tools_read / rook_tools_call
    {"query": "...", "limit": 10},
)
```

Rook currently returns its `{success, data}` envelope as JSON text. The skill
must parse that text and inspect `success`; a `success: false` Rook envelope is
not successful merely because MCP did not set `isError`.

Prime may also see Rook's direct tools. The gateway path is required operating
guidance, not a claim that only three MCP tools exist. Rook's capability profile
and gateway admission remain the mechanical authority.

### 8.3 Capability Profiles

The capability profile is fixed at conversation creation and stored in the
association. Slice D uses a temporary `readonly` qualification profile. Slice E
and shipped Prime-backed RookChat use `full`. A running conversation is never
elevated from readonly to full.

Readonly qualification is a Rook admission configuration, not a user-facing
conversation persona and not a Python sandbox.

## 9. Rook Target And Grasshopper Context

### 9.1 Immutable Conversation Binding

The immutable Rook authority for a conversation is:

```text
Rook hostGenerationId
+ owning Rhino document runtime serial
```

RookNative creates one opaque UUID at plugin-host initialization. Discovery and
the live capability response publish the same ID. PID remains a routing hint and
diagnostic only; it is not authority.

Rook MCP verifies the exact host generation before target-dependent dispatch.
Rhino operations receive the locked document serial. Missing, stale, or
mismatched authority returns stable `target_unavailable` before native
operation dispatch.

Model-supplied ports, PIDs, document IDs, or selectors cannot override the
recorded binding through the supported adapter path. A different Rhino host or
document requires a new conversation.

### 9.2 Dynamic Grasshopper Context

Grasshopper document identity is operation context, not durable conversation
identity. This allows fully enabled work such as opening a definition and then
editing it.

The rules are:

- Document-independent GH queries require no active document identity.
- Document-scoped observations capture the active canvas and document once and
  return canonical `GH_Document.DocumentID` in `D` GUID form.
- Ordinary document-scoped mutations require a reserved top-level
  `expectedGhDocumentId` from the preceding observation.
- Explicit transitions such as `gh_document_open`, `gh_document_new`, and
  `gh_learn_directory` require no expected ID and return the resulting active
  ID.

One shared GH operation-classification predicate assigns these categories. The
same result drives direct tool-schema projection, `rook_tools_read`, nested
`rook_tools_call` validation, and dispatcher enforcement. No parallel mutation
or transition list may govern any of those boundaries.

The central dispatcher validates and removes `expectedGhDocumentId` before
validating the tool's existing schema. This applies whether the mutation arrived
through `rook_tools_call` or a direct MCP tool call.

The advertised contract makes the requirement visible. The tool-list projection
adds the reserved canonical-GUID string field to both `properties` and
`required` for every guarded document-scoped GH mutation's direct MCP input
schema, and `rook_tools_read` returns the same augmented schema.
`rook_tools_call` validates its nested arguments against that augmented target
schema. Document-independent queries, observations, and the explicit transition
tools are exempt.

At managed callback entry:

```text
capture active canvas and GH document once on the UI thread
-> read exact GH_Document.DocumentID
-> compare with expected canonical GUID
-> execute against that same captured document object
```

No handler validates one active document and later re-resolves another.

Stable failures are:

- missing expected identity: `gh_target_required`;
- invalid or noncanonical GUID: `invalid_arguments`;
- no active canvas/document: `gh_target_unavailable`;
- different active document: `gh_target_changed`.

Every successful GH mutation receipt records the actual `ghDocumentId`.
Receipt-fenced readiness and observation capture the current document once and
refuse if it differs from the receipt's document.

Changing the active definition makes an earlier expected ID stale; returning to
that same definition makes its canonical ID eligible again. Neither transition
changes the durable conversation association.

Document transitions, script creation, `gh_update_script`, `rhino_execute`,
preflighted `rhino_command`, and ordinary typed authoring remain available.

The boundary is intentionally not a hostile-code sandbox:

> Panel locking guarantees where Rook's typed operation is dispatched. It does
> not sandbox arbitrary code authored into Rhino, Grasshopper script
> components, or other programmable environments.

## 10. Permissions, Errors, And Ambiguous Mutation

### 10.1 Trusted ACP Permission Policy

RookChat ACP sessions automatically approve valid ACP permission requests.
The handler validates that option IDs are unique and nonempty and that option
kinds are valid. It chooses deterministically:

1. the first valid `allow_once` option;
2. otherwise the first valid `allow_always` option;
3. otherwise `cancelled`.

It never invents an option ID. Auto-approval is shown as unobtrusive tool status,
not a dialog. There is no user-mediated or durable permission state.

If no valid allow option exists, the handler atomically signals the prompt owner
and returns `cancelled`. The prompt owner sends `session/cancel` once. The
cancellation flag is absorbing; no later permission request for that prompt may
be approved.

Readonly remains readonly because Rook independently refuses mutations.

### 10.2 Outcome Separation

An authentic Rook result and receipt remain authoritative for that Rook
operation even if the enclosing ACP prompt later fails. ACP settlement
independently determines the prompt outcome.

If transport fails before RookChat sees an authentic Rook result, the operation
outcome is unknown until Rook is freshly observed. RookChat never assumes the
mutation failed and never replays it automatically.

An authentic success or failure envelope remains authoritative even if later
MCP-child cleanup fails. Cleanup failure is retained separately and does not
erase a receipt or structured error.

RookChat never edits or rolls back Prime's session file, never rewrites the
durable association because of an operation result, and never changes existing
presentation-cache files. It may create one bounded terminal error or
interruption projection for the failed turn.

## 11. Images, Models, And Authentication

### 11.1 Authentication

Prime exclusively owns authentication behavior, credential storage, OAuth
refresh, and provider errors.

RookChat never accepts, originates, inspects, persists, or logs credentials. It
never supplies `--api-key`. Prime resolves credentials from its own auth store
and any intentionally inherited supported environment sources.

The ACP child environment is derived from the service's normal launch
environment before any Rook installed `.env` loading, plus required runtime
fields. ACP-backed RookChat neither reads nor forwards the installed Rook
Anthropic `.env` credentials. No secret scanning is introduced to support a
stronger claim.

The existing Rook Anthropic-key facility remains temporarily for non-ACP
consumers such as Chirp, DSPy, and knowledge workflows. Those consumers migrate
separately; credentials are never copied automatically into Prime.

Missing or expired authentication displays Prime's bounded error plus explicit
guidance to open Prime interactively and run `/login` there. `/login` is not
presented as usable inside RookChat ACP. An `Open Prime Login` action and
ACP-native authentication are deferred.

RookChat displays authentication only as `Prime-managed` unless Prime later
supplies authoritative nonsecret metadata. Product code does not read
`auth.json`.

### 11.2 New-Conversation Model Selection

For a new provisional conversation, the existing panel may offer configured
Prime-compatible models and Prime's pinned reasoning values. The model list is
presentation configuration, not an independent availability catalog.

The launch uses:

```text
--model <fully-qualified-provider/model>
--thinking <optional validated level>
```

No separate `--provider` is sent for a fully qualified model. The closed
reasoning enum for this pinned Prime contract is:

```text
off, minimal, low, medium, high, xhigh, max
```

RookChat rejects every other reasoning value before launch because Prime may
warn and continue on invalid input. Prime remains responsible for validating
the selected model, model capability, and authentication.

If the user makes no selection, neither model nor thinking flag is supplied and
Prime chooses its configured default.

After durable publication, model controls become read-only. RookChat performs
no mid-session switching because current Prime ACP exposes neither config
options nor `session/set_config_option`. Reopen passes no model or thinking
override; Prime restores persisted settings.

The registry labels the values as `requested initial model` and `requested
initial reasoning`. It never presents them as verified current effective state
without authoritative Prime metadata.

### 11.3 Image Admission

The panel accepts pasted or selected PNG, JPEG, and WebP images. C# captures
them and sends them through authenticated local HTTP. Python validates them
before constructing standard ACP image content blocks. No temporary files,
image tools, or Rook transport are involved.

The fixed product limits are:

- at most 8 images per turn;
- at most 16 MiB decoded binary bytes per image;
- at most 32 MiB decoded binary bytes per turn;
- at most 48 MiB encoded HTTP request body;
- positive dimensions no greater than 16,384 pixels on either axis;
- at most 40,000,000 pixels per image.

`decoded binary bytes` means bytes after strict base64 decoding, not
decompressed pixel memory. Validation requires strict base64, magic bytes that
match the declared MIME, binary-size bounds, bounded dimensions, and maximum
pixel count. Image bytes never enter logs or diagnostics.

Before admitting an image turn, the service requires Prime initialization to
advertise `promptCapabilities.image`. Otherwise the image turn refuses before
`session/prompt`.

Original image bytes are live-transport-only in RookChat. The presentation
cache retains bounded filename label, MIME type, dimensions, binary byte count,
and SHA-256. Reopened history visibly states that the image preview is
unavailable. Durable attachment and thumbnail storage are deferred.

## 12. Runtime Packaging And Versioning

Rook packages an exact, qualified Prime standalone release artifact as a
versioned product dependency. It uses Prime's existing supported
release/standalone artifact shape; Rook does not invent a source layout or copy
selected `dist` files.

The final removable Prime compatibility commit closes two defects in that
upstream shape:

- Prime resolves the venv interpreter as `Scripts/python.exe` on Windows and
  `bin/python` on other platforms. One shared helper supplies both bootstrap and
  ready-check paths, with causal tests for `win32` and non-Windows selection.
- Prime's standalone builder copies the complete matching
  `dist/prime-agent-runtime` subtree produced by `npm run build` into
  `<standalone-root>/dist/prime-agent-runtime`. This is the location Prime's
  existing bootstrap already searches. The standalone artifact must not rely
  on the bare, unpublished `prime-agent-runtime` package name.

The Rook packager consumes that complete standalone directory unchanged. It
does not reconstruct the Python runtime from source or append selected Prime
files after the builder finishes.

The executable authority is a closed, relocatable manifest over the installed
artifact. The manifest and every byte it binds are generated into one release
staging tree, verified together, and packaged together; source control does not
retain an orphan generated manifest without its payload. All manifest paths are
relative to the runtime root, and no machine-specific Rook MCP launch path or
environment is part of this content-addressed identity. Git commits are
provenance, not runtime proof. Runtime metadata records:

- exact platform `windows` and architecture `amd64` for the Prime builder's
  `windows-x64` standalone target;
- upstream Prime commit;
- removable compatibility-patch commit, when still needed;
- installed artifact manifest SHA-256;
- expected ACP compatibility version;
- exact `rook-full` manifest identity;
- exact Python ACP SDK version;
- exact official `uv` version, executable identity, source archive, and license
  identities;
- exact relative `dist/prime-agent-runtime` root and its closed subtree
  manifest identity;
- product runtime compatibility schema.

For each immutable package root, the closed manifest includes every regular
admitted file except the manifest itself. Paths use forward-slash relative form,
sort ordinally, and bind raw byte length and SHA-256. Symlinks and reparse-point
escapes are refused. The outer manifest identity hashes canonical UTF-8 JSON
with LF line endings.

The installer places each new runtime in a new immutable sibling directory. It
never modifies an installed runtime in place. New conversations use the newest
qualified runtime; existing conversations reopen with their recorded runtime.
Historical runtimes are retained for this slice. Reference counting and garbage
collection are deferred.

Before each launch or reopen, RookChat verifies the recorded manifest and exact
runtime path beneath the installed product root. Missing or mismatched runtime
bytes return `runtime_unavailable` before Prime starts.

Prime's mutable user data remains outside the immutable executable directory:

- Prime credentials and user settings remain Prime-owned;
- product-assigned session files remain under the Rook data root;
- presentation cache remains under the Rook data root;
- non-expiring `open.claim` fences remain under the Rook data root;
- Prime kernel state remains in Prime's supported mutable location.

The immutable runtime contains the two prerequisites Prime needs to create that
mutable kernel on a clean Windows installation:

- official `uv` 0.12.3 for `x86_64-pc-windows-msvc` at
  `tools/uv/uv.exe`, including its verified Apache-2.0 and MIT license files;
- the complete matching Prime-built Python source package at
  `dist/prime-agent-runtime`.

The `uv` release inputs are frozen as:

```text
archive: https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip
archive SHA-256: B23350C79E8AD0192B8124AF13A0F17E8D4E4549524785E1AEF389AE5A06990E
LICENSE-APACHE SHA-256: C71D239DF91726FC519C6EB72D318EC65820627232B2F796219E87DCF35D0AB4
LICENSE-MIT SHA-256: 860E3D7A86B84E6A7012C7A635FC64DF475CEBC6CCE34DFEB73A5982EC58176C
```

Every file in both subtrees is bound by the one runtime manifest. RookChat
prepends the manifest-verified `tools/uv` directory to the Prime child `PATH`.
Prime then owns Python 3.11 acquisition, venv creation, package installation,
bootstrap versioning, and the mutable kernel. RookChat does not create a
contract-specific kernel or install Python dependencies itself.

Before adding the bundled `uv` directory, the child-environment builder removes
these inherited keys case-insensitively:

```text
PI_PACKAGE_DIR
PRIME_AGENT_KERNEL_PYTHON
PRIME_AGENT_KERNEL_VENV
PRIME_AGENT_INSTALL_UV
VIRTUAL_ENV
PYTHONHOME
PYTHONPATH
```

It also removes every inherited key whose case-insensitive name begins with
`UV_`, then inserts only these six product-owned values:

```text
UV_CACHE_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/cache
UV_PYTHON_INSTALL_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/python
UV_PYTHON_PREFERENCE=only-managed
UV_PYTHON_NO_REGISTRY=1
UV_PYTHON_INSTALL_REGISTRY=0
UV_NO_CONFIG=1
```

This prevents alternate indexes, mirrors, local find-links, configuration
files, offline mode, Python mirrors, credentials, or another uv policy from
replacing the installed runtime path or redirecting first bootstrap. The cache
and managed-Python bytes are mutable uv-owned support state outside the
immutable Prime artifact; their locations are product-owned but not keyed per
conversation or runtime contract. Prime may still use its supported mutable
user directories, the bundled uv defaults, ordinary system proxy settings, and
independently supplied credentials. The existing Rook `.env` credential path
remains excluded as specified in section 11.

The user installs only Rook. The first Prime session creation may begin a
background kernel prewarm, and the first IPython/Rook operation may wait while
bundled `uv` downloads Python, installs the manifest-bound Prime runtime source,
and resolves Prime's default Python packages.
That first use requires internet access and can take longer. Failure remains a
Prime-owned tool failure; RookChat does not retry, repair, or substitute a
kernel.

The Windows release build has a separate, build-only toolchain contract. Task 10
provisions one fresh, disposable MSYS2 root rather than copying selected
executables or DLLs from the shared machine installation. Its fixed bootstrap
inputs are:

```text
base: https://github.com/msys2/msys2-installer/releases/download/2026-06-11/msys2-base-x86_64-20260611.sfx.exe
base SHA-256: C105946E64E08F099AC0E4647461CE762B95333AD211777666476A9A41451D65
zip: https://mirror.msys2.org/msys/x86_64/zip-3.0-5-x86_64.pkg.tar.zst
zip SHA-256: 874E20BF625FBE577949444FAF30AB9A725DBD4886EC9BFF26459152DA7F831C
unzip: https://mirror.msys2.org/msys/x86_64/unzip-6.0-3-x86_64.pkg.tar.zst
unzip SHA-256: C98EBAC31EA92A63CF61C6190ED3E8284CCC0C29C43973F1B2C0DE2874E5ACFE
```

The provisioner verifies those hashes, extracts the base into a new short
ASCII-only path outside the source and product trees, and uses that root's
`pacman -U` with only the two verified local package archives. It performs no
repository refresh and never alters or consults the shared `C:/msys64`. The
base already supplies the declared `bash` and `libbz2` dependencies; package
installation must prove the exact `zip`, `unzip`, `bash`, and `libbz2` package
identities. The completed root is then frozen by one canonical manifest over
every regular file plus a complete sorted `pacman -Q` inventory. Build-time use
must leave that root byte-identical.

The build contract binds that whole MSYS2 root, complete manifests of the
external Node/npm and Git installations, the standalone Bun executable, all
commands actually consumed by Prime's builder, and the Windows command
processor identity. It removes every inherited `NPM_CONFIG_*` key
case-insensitively; points npm's user and global configuration at distinct,
manifest-bound empty files; and fixes both `ComSpec` and
`NPM_CONFIG_SCRIPT_SHELL` to the same manifest-bound
`C:/Windows/System32/cmd.exe`. Prime's reviewed project `.npmrc` and npm's
bound built-in configuration are the only remaining npm configuration sources.

Provisioning emits canonical contract bytes and a SHA-256 but does not authorize
a build. An independent review must supply that exact hash as
`ExpectedBuildToolchainContractSha256`; the package script verifies it before
any version probe, network access, or `npm ci`. Missing, malformed, substituted,
or changed inputs refuse without discovery, fallback, or repair. The
provisioned root is a release-machine dependency only and never enters the Rook
installer or a customer machine.

Ambient Prime skills, extensions, MCP servers, context files, and prompt
templates are excluded by the explicit launch configuration. Prime-owned
credentials and selected user settings are intentional mutable inputs.

The Rook distribution includes all required Prime licenses and notices.

The upgrade loop is finite:

```text
new Prime upstream
-> determine whether the compatibility patch is still needed
-> build Prime's supported artifact shape
-> run frozen ACP compatibility gates
-> install a new immutable Rook runtime directory
-> use it for new conversations
```

If build reconciliation or qualification fails, the current Rook release keeps
its last known-good Prime artifact. No emergency compatibility mechanism enters
product runtime.

The compatibility patch is removed when an official Prime release provides
equivalent daemon-free ACP selection, platform-correct kernel bootstrap, and a
complete standalone Python-runtime payload, and the installed-artifact
compatibility suite passes unchanged.

## 13. Replacement, Cutover, And Rollback

RookChat becomes Prime ACP. There is no backend registry, available-backend
list, default-backend selector, shared execution interface, or shipped
coexistence period.

Development and qualification occur on the isolated ACP branch. The cutover
release:

1. installs the exact qualified Prime runtime;
2. replaces ChatRunner execution with ACP process/session ownership;
3. removes ChatRunner conversation, model execution, cancellation, credential
   health, and tool-loop code;
4. removes ChatRunner-only endpoints, credential health, and model controls,
   while retaining the approved Prime creation-time model and reasoning
   selectors;
5. retains backend-neutral panel rendering, authenticated HTTP, service
   discovery, and bounded event projection;
6. leaves quarantined worktrees and historical evidence untouched.

ChatRunner conversations are ephemeral and receive no transcript migration.
There is no new ChatRunner conversation after cutover and no fallback inside the
shipped product.

Rollback is a Rook release rollback:

```text
ACP release proves unusable
-> reinstall or redeploy the previous known-good Rook release
```

A runtime safety disable may make RookChat unavailable; it never resurrects
ChatRunner.

ACP session files, presentation artifacts, and `open.claim` fences reside
outside replaceable application payloads. Installation, upgrade, rollback, and
uninstall with data retention must prove that they are not removed without
explicit user-authorized data deletion. An older release may be unable to open
newer ACP records; reinstalling the compatible ACP release restores access.

RookChat owns the durable association, directly owned ACP process and
connection, transport correlation, bounded presentation, runtime identity, and
immutable Rook binding. Prime owns reasoning, transcript, goals, compaction,
model context, and semantic completion.

## 14. Explicit Deletion And Non-Port List

The following do not enter the ACP product:

- private Prime RPC commands or clients;
- private `AgentConnection` transport;
- shared Prime daemon topology or daemon sockets as product transport;
- owned workers or worker authentication;
- PID/process-start ownership, PowerShell probes, process scanning, or process
  surveillance;
- broker-owned session leases;
- private kernel-preparation RPC or contract-specific kernel environments;
- shadow prompt lifecycle, semantic acceptance, terminalization protocol, or
  automatic replay;
- campaign runners, evaluators, or evidence manifests in product runtime;
- Gate 7 monitors, wrappers, admission journals, or topology harnesses;
- quarantined Task 7 Rook or Prime code;
- ChatRunner's model loop, tool loop, conversation store, cancellation,
  credential health, backend endpoints, and ACP-inapplicable UI controls;
- a Rook-owned MCP facade or `rook_full` Python package;
- transcript reconstruction or automatic operation replay.

The only Prime compatibility surface is the one removable commit described in
section 12. It contains the daemon-free ACP selector and the two bounded
Windows/standalone corrections required to exercise Prime's existing kernel.

## 15. Qualification

Qualification remains external to product runtime. It progresses through one
model-free pre-contact review gate and three separately authorized live gates.

### 15.1 Model-Free Pre-Contact Qualification: Slices A And B

#### Slice A: Product Boundary With Fake ACP Agent

```text
C# panel
-> authenticated HTTP
-> Python ACP broker
-> official Python ACP SDK
-> deterministic fake ACP agent
```

Model-free coverage proves:

- initialization and capability checking;
- incompatible protocol and missing `session/close` refusal before first prompt;
- provisional first-turn publication;
- two independent service instances contending for one conversation, with one
  owning `open.claim` and the other receiving `session_recovery_required` before
  launch;
- normal claim removal only after the exact child is observed exited;
- owner-service crash preserving the claim after child exit, with subsequent
  Reopen and Delete refusing without PID discovery or automatic reclamation;
- failed process creation removing its claim only when the launcher proves no
  child was created, while uncertain creation preserves the claim;
- streaming order under deliberately concurrent callbacks;
- late-callback refusal across prompt, ACP-session, and launch generations;
- stalled-consumer overflow and one cancellation path;
- permission auto-approval and absorbing cancellation;
- cache bounds, sequence ordering, eviction, corruption, and independence from
  panel drain;
- image validation and exact ACP image blocks;
- launch-time model/reasoning argument construction;
- absence of `--api-key` and reopen overrides;
- exact service-owned `rook` MCP declaration injection;
- structured Rook success and refusal-envelope projection;
- direct and `rook_tools_read` GH mutation schemas advertising the required
  `expectedGhDocumentId` field, with transition tools exempt;
- accumulator, truncation-marker, original-byte-count, fallback-projection, and
  exact unknown-`_meta` limits;
- identical permission auto-approval behavior under readonly and full profiles;
- directly owned cleanup and all normal-close failure branches;
- no PID scan, PowerShell, process surveillance, or process-name cleanup.

#### Slice B: Installed Prime Artifact And Cold Kernel Bootstrap

Use the exact installed Prime artifact, isolated Prime directories, a local
deterministic fake provider, and a unique daemon-socket tripwire. No external
provider, model, Rook, Rhino, or Grasshopper contact occurs.

Before `session/new`, the gate proves that fresh `HOME`, `USERPROFILE`,
`APPDATA`, `LOCALAPPDATA`, `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, and the
derived Prime kernel root contain no reusable kernel or managed Python. The
runner removes every inherited `UV_*` key case-insensitively and then inserts
only the protocol-owned `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`,
`UV_PYTHON_PREFERENCE=only-managed`, `UV_PYTHON_NO_REGISTRY=1`,
`UV_PYTHON_INSTALL_REGISTRY=0`, and `UV_NO_CONFIG=1` values. It proves the
resulting final Prime child environment contains exactly those admitted `UV_*`
keys, so an installed or registered Python and ambient uv policy cannot satisfy
the gate. The
installed Prime process runs with `--offline`, which suppresses Prime's
unrelated updater and catalog traffic; it does not put the separately admitted
`uv` bootstrap into offline mode. A qualification-owned, deny-by-default
outbound proxy records and admits only the frozen Python and package downloads
needed by the manifest-bound `uv`, while loopback serves the deterministic
provider and Rook MCP double. Before inserting that proxy, the runner removes
all inherited `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` keys
case-insensitively. It then inserts only the protocol-owned proxy URL and
loopback bypass and asserts the complete final proxy map. The frozen host
allowlist is exactly
`github.com`, `api.github.com`, `objects.githubusercontent.com`,
`release-assets.githubusercontent.com`, `releases.astral.sh`, `pypi.org`, and
`files.pythonhosted.org`; a required destination outside that set makes this
protocol fail and requires a separately reviewed version. No process polling or
network machinery enters product runtime.

Prime starts kernel prewarm during session creation, so the gate does not claim
that the first prompt initiates bootstrap. It proves this exact sequence:

```text
kernel, uv cache, and uv-managed Python absent before session/new
-> Prime creates its ordinary mutable kernel through bundled uv
-> first prompt executes real IPython and mcp.call_tool("rook", ...)
```

The deterministic provider proves persistence behaviorally: after reopen,
Prime receives prior conversational context and answers consistently. Product
code continues to inspect only the bounded session header envelope.

Slice B qualifies:

- `initialize -> session/new -> session/prompt -> session/close -> EOF`;
- first-turn materialization and create-only association publication;
- ordinary assistant-turn context continuity across same-file reopen;
- model-free active cancellation and clean process retirement;
- lazy MCP startup through the installed Prime artifact;
- selection of `Scripts/python.exe` from the newly created Windows venv;
- installation of the manifest-bound local `dist/prime-agent-runtime` rather
  than a registry fallback;
- cancellation during an MCP call and session-close MCP cleanup;
- fresh MCP server establishment after same-file reopen;
- required launch configuration and excluded ambient resources;
- installed artifact manifest identity;
- zero daemon-tripwire contact;
- no surviving directly owned child after clean close.

The combined model-free pre-contact gate also proves the installed replacement:

- no ChatRunner execution path, backend selector, credential-health route, or
  tool loop remains;
- only Python imports the ACP SDK;
- installation, upgrade, rollback, and uninstall with data retention preserve
  ACP session data, presentation data, and `open.claim` fences;
- cleanup uses directly owned handles only.

Slices A and B have separate technical results but one pre-contact independent
review gate.

### 15.2 Slice C: Prime-Managed Authentication And Image

Use one frozen tiny image task with a known vision-capable subscription model.
Freeze the requested fully qualified model and reasoning arguments, image bytes
and hash, prompt, runtime manifest, and all finite limits.

The claim is `exact requested model and reasoning arguments` unless
authoritative returned metadata proves the effective model. OAuth is claimed
only if the external qualification reads nonsecret Prime-owned credential
metadata proving OAuth. Otherwise the result is described as a Prime-managed
authenticated subscription call. Product code never reads `auth.json`.

The deterministic answer must depend on visible image content. This one live
version executes once, with no Rook server, Rhino contact, retry, or prompt
repair.

### 15.3 Slice D: Readonly Rook

Start one fresh conversation with the immutable `readonly` qualification
profile against one deterministic Rhino/Grasshopper fixture. Run one prompt.

The live gate proves ordinary accurate observation, target binding, MCP
injection, lazy startup, gateway parsing, document-scoped observation identity,
absence of mutation attempts or receipts, unchanged fixture state, and clean
close.

Fresh MCP establishment after reopen and mutation-wall enforcement remain
model-free cases. Slice D does not add a second stochastic live prompt.

### 15.4 Slice E: Full Rook Mutation

Start one fresh `full` conversation against the seeded adjustable X-axis
point-row defect. Use the established user-facing prompt without disclosing the
known repair.

The Actor must inspect the fixture, create a real Prime goal before substantive
mutation, repair and test through a bounded attributable mutation sequence,
preserve useful existing components, and restore selected defaults.

The terminal sequence is exact:

```text
final mutation/restoration receipt R
-> readiness bound to R
-> fenced observation bound to R
-> no further Rook calls
-> dedicated goal.complete() tool cell
-> final text only
-> ACP prompt settlement
-> seal Actor trace, receipt R, and fenced evidence
-> begin separately identified silent evaluator
```

Any Actor tool action after `goal.complete()` makes the combined qualification
incomplete. An audited no-op earns no receipt or completion credit.

The evaluator begins only after Actor settlement and evidence sealing. It may
perturb controls, verify behavior, restore defaults, and verify structural
equivalence. Its trace and receipts use a separate namespace and can never
satisfy Actor criteria.

### 15.5 Frozen Live Versions And Evidence

Before each live contact, its reviewed protocol freezes:

- wall-clock limit;
- token limit;
- process-close deadline;
- exact input and prompt hashes;
- installed runtime and skill manifests;
- model and reasoning request;
- target/profile identity;
- evaluator implementation and hash, if any;
- fresh create-only evidence root.

Each frozen live version executes once and its result is immutable. Any
correction requires a newly versioned protocol, fresh evidence root, and
separate authorization.

External evidence is bounded. It records frozen inputs, installed manifests,
protocol outcomes, bounded presentation projections, Prime session identity,
Rook receipts, fenced snapshots, directly owned process settlement, and final
outputs. It does not retain unrestricted thought streams, cumulative events, or
credentials.

Qualification reports these outcomes separately:

- ACP transport and prompt settlement;
- durable Prime identity and context continuity;
- Prime goal lifecycle;
- Rook target and receipt custody;
- token, time, and process budgets;
- graph structure and finite behavioral evaluation.

A correct graph does not hide failed custody, goal, budget, or settlement.

Compaction restoration and IPython restoration are not inferred from Slices
A-E. They require later explicit ACP qualification before becoming product
guarantees.

## 16. Acceptance Summary

The design is accepted when:

- RookChat has one shipped conversation implementation: Prime ACP;
- one directly owned Prime process serves each open conversation;
- one atomic non-expiring `open.claim` excludes concurrent RookChat owners and
  fails closed after owner-service crash without a lease protocol;
- no daemon or private Prime protocol participates;
- every durable association identifies a validated materialized Prime session;
- no broker lifecycle or transcript authority competes with Prime;
- current-turn and cached presentation are bounded;
- Rook remains the sole authority for host operations and evidence;
- Grasshopper mutations use explicit optimistic document concurrency;
- Prime authentication remains Prime-owned;
- model selection is limited to supported new-conversation launch arguments;
- the exact installed Prime artifact and skill bytes are manifest-bound;
- ChatRunner and Task 7 product machinery are absent;
- the model-free pre-contact gate and separately authorized live gates pass without evidence
  overwrite or automatic retry.
