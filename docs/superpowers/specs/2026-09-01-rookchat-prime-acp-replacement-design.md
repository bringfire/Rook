# RookChat Prime ACP Replacement Design

**Status:** Approved architectural design for independent review

**Date:** 2026-09-01

**Rook design baseline:** `f840069a58d0a5ee297ae817f0b3efe7a9287512`

**Prime upstream baseline:** `c718bf3c30fd8da206ed551837cbb54f7ad15948`

**Current reviewed Prime compatibility precursor:**

`1b9dfabb04901de4823d259c88b39dfc78ec3b34`

This precursor is one independently reviewed commit directly over the Prime
upstream baseline. It is implementation evidence, not the final release
identity. Before another build, its bounded concerns and the two product-
security corrections in section 12 are organized as a short independently
reviewed patch series over the same upstream baseline. The exact final series
head is the single Prime identity recorded by a runtime manifest.

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

The replacement uses Prime's supported ACP surface plus a short ordered series
of independently removable compatibility patches. Each patch owns one bounded
concern; one exact reviewed final head identifies the complete runtime source.
The series does not add a Rook protocol, kernel, daemon, trust database, or
release subsystem. No other private Prime change is part of this design.

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
--append-system-prompt <exact verified UTF-8 contents of rook-full/SKILL.md>
--no-extensions
--no-context-files
--no-prompt-templates
--no-approve
--tools ipython
```

`--no-approve` is one immutable parsed Boolean established before the first
automatic project-resource access. Global migrations, global settings, Prime
authentication, and explicitly supplied CLI resources remain admitted. During
startup and resume before model work, no automatic project-resource discovery,
loading, project-settings access, or project migration occurs. This includes
project-local packages, extensions, skills, prompt templates, themes,
`SYSTEM.md`, `APPEND_SYSTEM.md`, AGENTS/CLAUDE context files, and migration
inputs at both the launch working directory and a resumed session's stored
working directory.

`--no-approve` preserves Prime's user-global prompt authority. Because RookChat
does not pass `--system-prompt`, the user-global `<agentDir>/SYSTEM.md`
(`~/.prime/agent/SYSTEM.md` under the default layout) remains eligible as the
base system prompt and may affect Prime's base instructions. The exact verified
`rook-full/SKILL.md` body is supplied separately through
`--append-system-prompt`; that explicit append source suppresses automatic
`APPEND_SYSTEM.md` discovery for the launch. The selector creates no trust
database, prompt, permission workflow, or lifecycle state, and it does not
change RookChat's separately defined ACP permission auto-approval policy. It is
not a filesystem sandbox: after model work begins, admitted IPython and Rook
tools may intentionally access project files within their own authority.

The reviewed Prime baseline confines managed `fd`/`rg` acquisition to
postinstall, interactive mode, and agents-view mode. Direct in-process ACP
composition calls neither `ensureTool()` nor `ensureToolWithStatus()`, so
RookChat adds no inert helper-download selector. A source-level ACP composition
test owns that non-reachability invariant. Slice B separately records the
allowlisted host/port destinations observed by its configured CONNECT proxy
and verifies that managed-helper artifacts were not created. This does not
prove encrypted URL paths, extractor invocation, or exhaustive network
containment. A future Prime baseline that makes
managed acquisition reachable from ACP requires a new bounded security review
before adoption; RookChat does not preemptively add policy machinery for an
unreachable path.

Production RookChat never passes Prime's broad `--offline` flag. Before process
creation, the service removes every inherited `PI_OFFLINE` key case-
insensitively from the Prime child environment. `--offline` remains admitted
only in the isolated Slice B qualification protocol described in section 15.

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
Therefore the broker reads the manifest-verified root `SKILL.md`, enforces its
frozen byte limit, strictly decodes it as UTF-8, and supplies those exact
decoded contents once through `--append-system-prompt` without rewriting them.
Domain references are read through IPython only when relevant.

The launch limits are fixed:

```text
rook-full/SKILL.md maximum: 16,384 UTF-8 bytes
complete rendered Windows command line maximum: 30,000 UTF-16 code units,
including the terminating null
```

Both limits are enforced before process creation.

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

Rook packages an exact, qualified Prime standalone Windows artifact as a
versioned product dependency. Prime remains an upstream dependency: Rook uses
Prime's existing `windows-x64` artifact shape, does not reconstruct selected
Prime files, and does not add another executable topology.

The earlier bespoke Windows build-toolchain custody design is superseded by
this section and has no product or release authority. Build-machine provenance
and installed-runtime authority are deliberately separate:

```text
reviewed Git source + ordinary build record
-> Prime's complete upstream ZIP
-> one closed Rook runtime manifest over every shipped byte
```

The upstream baseline remains
`c718bf3c30fd8da206ed551837cbb54f7ad15948`. The currently reviewed precursor
`1b9dfabb04901de4823d259c88b39dfc78ec3b34` proves the first four corrections,
but is not release authority. Before another Prime build, the final source is
organized as a linear, independently reviewed patch series with one concern per
commit, in this order:

1. daemon-free in-process ACP selection through `--no-daemon`;
2. platform-aware Prime kernel-interpreter resolution;
3. complete `dist/prime-agent-runtime` inclusion in the standalone artifact;
4. explicit frozen-model-catalog binary builds;
5. project-resource denial through `--no-approve`.

The exact commit and parent of every series member are recorded at the Prime
compatibility review gate. The exact final series head is the one Prime source
identity used by the build, runtime manifest, qualification protocol, and
installed product. The series is maintenance structure, not runtime machinery:
it adds no patch registry, dynamic selection, or second product contract.

Before that final head is approved, one named upstream review gate compares
`5c2750bdc3c99cc4225c1167a3484371a7a221ab` (bounded kernel stderr) with the
pinned baseline and series. The gate records exactly one decision:

- adopt it as a separately attributable upstream backport in the reviewed
  ancestry immediately after concern 2, with its focused kernel tests; or
- defer it with the observed conflict/risk and required future qualification.

No new real Prime build is admitted until that decision is independently
approved. Upstream `7f21fa3435cd1c63724b6e427edb3a60a309c266`
(native ACP MCP tools) is explicitly deferred because it changes Rook's model-
visible tool contract and still requires `cpython`; adopting it requires a
separate product decision. No other Prime patch is part of Task 10.

### 12.1 Git-Owned Source Custody

The build uses a clean Prime checkout in a Linux-native filesystem. A
materialized Windows working tree, Windows `node_modules`, ignored Windows
build output, or a checkout under `/mnt/c`, `/mnt/d`, DrvFS, or another
Windows-hosted mount is never a build input.

The reviewed commit reaches the Linux environment through Git custody only:

- clone or fetch it from an authoritative Git remote; or
- for the current local reviewed commit, create a Git bundle containing that
  commit, transfer the bundle into the Linux filesystem, verify it with Git,
  and clone from it.

Copying a materialized checkout is prohibited. The Linux checkout is detached
at the exact independently approved final series head. Before the build it must
prove:

```text
HEAD == the exact approved final Prime series head
first-parent ancestry == the exact approved ordered series over c718bf3c30fd8da206ed551837cbb54f7ad15948
tracked worktree clean
package-lock.json present as one regular file
package-lock.json SHA-256 recorded
```

Ignored build directories have no pre-build authority and begin absent in the
fresh checkout.

### 12.2 Portable Ubuntu Build Boundary

The first supported local build environment is Ubuntu 24.04 under WSL2. WSL2
is a developer and release-machine dependency only. It never enters RookChat,
the installer, the installed Prime runtime, or the customer installation.

The local Windows release command selects the installed `Ubuntu-24.04` WSL2
distribution. The portable Bash build entrypoint itself requires Ubuntu 24.04
and a Linux-native build root but contains no WSL-specific requirement. The
same entrypoint can therefore run directly in Ubuntu CI later. Moving release
execution to CI is an operational change, not a product redesign.

The supported environment supplies:

- Node.js `>=22.8.0` and its npm;
- Rook-qualified Bun `1.3.14`;
- Git;
- `zip` and `unzip` from the Ubuntu build environment; and
- the ordinary Ubuntu commands `bash`, `sh`, `dirname`, `rm`, `mkdir`, `cp`,
  `ls`, `env`, `timeout`, `sha256sum`, `uname`, `findmnt`, `readlink`, and
  `head`.

Bun `1.3.14` is a Rook-qualified build version, not an upstream Prime
requirement. The observed Node, npm, Bun, Git, `zip`, and `unzip` versions are
recorded as diagnostic provenance. They are not executable manifests or
product runtime authority.

Each invocation creates a fresh build-only `HOME` and `TMPDIR`. Before launch,
the portable entrypoint resolves every required build tool, requires both its
command path and canonical target to be regular Linux-native executable files
outside `/mnt/*`, and constructs a Linux-only `PATH` from the unique parent
directories of those admitted command paths while preserving their original
admitted `PATH` precedence. Inside the exact clean child environment, every
required command is resolved again before the builder starts. Its command path
and canonical target must equal the pair admitted during preflight, and Node
and Bun must still satisfy their admitted versions. Conflicting same-name
executables, changed precedence, or any mismatch refuses before the builder.
Windows executables and inherited Windows `PATH` entries are never build
inputs.

The Prime builder deliberately receives only `HOME`, the constructed `PATH`,
`LANG`, `LC_ALL`, `TMPDIR`, and `CI`. The executing Bash process may add only
its finite bookkeeping variables `PWD`, `SHLVL`, and `_`. Provider credentials,
API keys, Prime configuration overrides, inherited `NPM_CONFIG_*` values,
and arbitrary ambient variables are not inherited.

By default, no proxy or network-setting variable is admitted. A reviewed local
or CI release invocation may explicitly supply only `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, and `NO_PROXY`. The launcher first clears ambient environment
values and then inserts only the deliberately supplied members of that closed
set; lowercase, mixed-case, and other network-setting names are refused. The
diagnostic build record retains only the supplied variable names, never their
potentially credential-bearing values. These environment rules are
invocation-local isolation, not an executable manifest or another build
authority artifact.

From the clean Linux checkout, the portable entrypoint invokes exactly:

```bash
timeout --kill-after=30s 1800s \
  ./scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog
```

It does not pass `--skip-deps`; Prime's builder remains responsible
for obtaining the Windows native dependencies needed for cross-compilation.
GNU `timeout` owns the one bounded command. No Windows PID lookup, process
scan, kill by name, WSL distribution termination, or custom process supervisor
is introduced.

Prime's build may contact npm for ordinary build dependencies, but frozen mode
must not contact any public model-catalog source. It deliberately skips refresh;
read-only source, broken network, or a swallowed generator failure is not an
acceptable substitute. It does not perform provider inference. A network or
build failure rejects that invocation. A later deterministic build may start
from another fresh Git-owned checkout; partial output is never resumed or adopted.

Before accepting or hashing an output, the entrypoint rechecks:

```text
HEAD remains the exact approved final Prime series head
first-parent ancestry remains the exact approved ordered series
tracked worktree remains clean
package-lock.json SHA-256 equals its pre-build SHA-256
packages/coding-agent/binaries/pi-windows-x64.zip exists as one regular file
```

This post-build check intentionally rejects output if Prime's own build changes
tracked generated source. Task 10 does not normalize, repair, or silently
accept such a change.

The entrypoint hashes `pi-windows-x64.zip` and emits a small human-readable
build record containing the commit, parent, pre/post lockfile hash, observed
tool versions, exact command, start/end timestamps, outcome, and ZIP SHA-256.
The record is release provenance only. It is not canonicalized, shipped, or
consulted by RookChat.

Each attempt also owns one create-only `build-console.log` beside its build
record. The wrapper redirects complete builder stdout/stderr into that file,
preserves the real command exit status, and emits the retained text after
settlement. Failure to create or retain the log rejects the attempt. This is
diagnostic capture, not another evidence or authority system.

Dependency vulnerability classification is not part of build admission. The
builder's native console output is retained, but any follow-up `npm audit`
belongs to a separately authorized, explicitly time- and byte-bounded diagnostic
after the build gate settles. Its result cannot grant or revoke artifact
authority. Until that diagnostic runs, reported dependency findings remain
unclassified. `npm audit fix`, dependency changes, and audit data in product
runtime are prohibited.

Focused Prime tests prove frozen mode leaves the checked-in catalog unchanged,
does not invoke its refresh boundary, and compiles a known committed marker;
ordinary mode still selects refresh, and unknown or malformed flag forms refuse.
The subsequent real build proves post-build HEAD, tracked cleanliness, lockfile
hash, and that the produced binary contains the committed
`global.openai.gpt-5.6-sol` marker but not the failed-v1 refresh-only
`anthropic.claude-fable-5-1` marker.

### 12.3 One Archive Transfer Boundary

Prime's upstream-produced
`packages/coding-agent/binaries/pi-windows-x64.zip` is the sole Linux-to-Windows
transfer unit:

```text
hash ZIP in Linux
-> copy ZIP into a fresh Windows staging generation
-> verify the identical SHA-256 on Windows
-> extract the complete archive without selecting files
```

The Windows staging generation is unique and empty. Before extraction, trusted
Rook release tooling validates every ZIP entry. It rejects rooted paths, path
traversal, empty or noncanonical names, case-insensitive normalized-path
collisions, link entries, reparse-point escapes, and any destination outside
the new payload root. Extraction never overlays an existing directory.

A failed transfer or extraction has no authority and is never repaired,
resumed, or adopted. A later Windows assembly attempt uses another empty
staging generation and may consume the same independently approved build ZIP
and hash, reverifying the archive from the beginning. A failed Linux build
requires a new build attempt and review. The ZIP hash remains build provenance;
it is not the installed runtime identity.

### 12.4 Final Payload Assembly

Windows assembly starts exclusively from the complete verified ZIP. It first
requires the Prime artifact shape used by Rook, including:

- `pi.exe`;
- Prime's `package.json`, `README.md`, and `CHANGELOG.md`;
- Prime's complete assets, documentation, examples, and skills;
- Prime's goal skill at `skills/goal`; and
- the complete `dist/prime-agent-runtime` subtree emitted by Prime's build.

Rook does not rebuild or select files from those Prime-owned subtrees. Assembly
adds exactly three fixed inputs before manifest generation:

1. The tracked Markdown-only `rook-full` skill at `skills/rook-full`.
2. Official `uv` 0.12.3 and its two license files under `tools/uv/`.
3. An exact reviewed copy of Prime's root license at
   `notices/prime-agent/LICENSE`.

Before any Rook-owned assembly write, the packager requires these reserved
destinations to be absent from the extracted Prime payload:

```text
runtime-manifest.json
skills/rook-full
tools/uv
notices/prime-agent
```

A collision refuses before any Rook-owned addition or manifest write. The
extracted Prime payload remains unchanged, and the failed staging generation
gains no authority. Every addition is create-only; the packager never overlays,
merges, repairs, or removes bytes at a reserved destination.

Only `rook-full` and `uv` are additional executable or product dependencies.
Prime's root license is legal notice material. Its tracked source is the
unchanged `LICENSE` at upstream commit
`c718bf3c30fd8da206ed551837cbb54f7ad15948`: 1,105 bytes with SHA-256
`B288615FB31DC504623582FB790A28E6D86BC2F5C1396845AF555E43386DA5A0`.
The final runtime manifest binds the exact installed notice bytes.

The release preparation supplies predownloaded `uv` inputs. The packager does
not perform network acquisition. The offline packager itself rechecks all three
inputs' regular-file shape, byte ceiling, and frozen SHA-256 before assembly,
then consumes the retained verified bytes rather than reopening input paths:

```text
uv archive
  source: https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip
  SHA-256: B23350C79E8AD0192B8124AF13A0F17E8D4E4549524785E1AEF389AE5A06990E
  maximum: 134217728 bytes

LICENSE-APACHE
  source: https://raw.githubusercontent.com/astral-sh/uv/0.12.3/LICENSE-APACHE
  SHA-256: C71D239DF91726FC519C6EB72D318EC65820627232B2F796219E87DCF35D0AB4
  maximum: 1048576 bytes

LICENSE-MIT
  source: https://raw.githubusercontent.com/astral-sh/uv/0.12.3/LICENSE-MIT
  SHA-256: 860E3D7A86B84E6A7012C7A635FC64DF475CEBC6CCE34DFEB73A5982EC58176C
  maximum: 1048576 bytes
```

The `uv` archive is safely inspected and must contain the expected Windows
`uv.exe`. Assembly installs only that executable plus the two separately
verified license files at their fixed runtime paths. No ambient `uv`, Hermes
installation, Rook virtual environment, or PATH-discovered executable can
satisfy packaging.

### 12.5 One Runtime Manifest

`runtime-manifest.json` is the sole executable contract for the installed
Prime runtime. It contains only relocatable product facts and has exactly these
top-level keys:

```text
schemaVersion
platform
architecture
upstreamCommit
compatibilityPatchCommit
acpProtocolVersion
pythonAcpSdkVersion
executable
goalSkill
rookSkill
rookSkillManifestSha256
claimKeyVersion
uv
pythonRuntime
files
```

New assembly uses these exact scalar values:

```text
schemaVersion = 1
platform = "windows"
architecture = "amd64"
upstreamCommit = "c718bf3c30fd8da206ed551837cbb54f7ad15948"
compatibilityPatchCommit = the exact approved final Prime series head
executable = "pi.exe"
goalSkill = "skills/goal"
rookSkill = "skills/rook-full"
claimKeyVersion = 1
```

`compatibilityPatchCommit` retains its schema-v1 field name but identifies the
final reviewed head of the complete ordered compatibility series, not an
omnibus one-commit patch. `acpProtocolVersion` and `pythonAcpSdkVersion` equal
the pinned product ACP contract. `rookSkillManifestSha256` is the canonical
recursive identity of the complete installed `skills/rook-full` subtree.

The closed `uv` object has exactly `version`, `executable`, `source`,
`sourceArchiveSha256`, and `licenses`. New assembly identifies version `0.12.3`, fixed
path `tools/uv/uv.exe`, the frozen archive source and hash above, and exactly
the two installed relative license paths.

The closed `pythonRuntime` object has exactly `root`, `manifestSha256`, and
`sourceCommit`. Its root is `dist/prime-agent-runtime`; new assembly records the
approved final Prime series head, and its subtree hash covers every regular file
under that root. This diagnostic subtree identity never replaces any outer
file row.

Exact new-build pins are not historical-runtime compatibility requirements.
Creation admits the currently approved build inputs above. Verification and
reopen instead bind the recorded runtime ID to its unchanged bytes and the
supported schema, platform, architecture, ACP/SDK, claim, and relative-path
contract. Recorded upstream and optional compatibility commits are lowercase
40-hex values (the compatibility commit may be null); `pythonRuntime.sourceCommit`
must equal the compatibility commit when present, otherwise the upstream commit.
Historical `uv.version` is a canonical three-part numeric version with no
leading zeros; its source must be the official Windows archive URL for that
recorded version, its source hash is uppercase 64-hex, and executable/license
paths remain fixed. These provenance values are bound by the recorded runtime
ID, not compared with the newest build pins. No updater, migration, repair, or
substitution is implied, and a runtime missing its recorded approval/association
cannot gain authority merely by supplying different provenance.

For every regular payload file except `runtime-manifest.json`, `files` contains
one row with exactly:

```text
path: canonical forward-slash relative path
bytes: nonnegative integer raw byte length
sha256: uppercase 64-hex SHA-256
```

Rows sort by path using ordinal comparison. The file set is closed: missing,
extra, changed, non-regular, linked, escaped, or duplicate-normalized paths
refuse. Absolute build or install paths, WSL paths, build-tool identities,
credentials, and Rook MCP launch commands are invalid manifest content.

One Rook-owned Python implementation creates and verifies the manifest. It
serializes UTF-8 without BOM, sorted object keys, compact separators, no Unicode
normalization, and exactly one terminal LF. The uppercase SHA-256 of those exact
bytes is the runtime ID. A small hand-frozen test vector fixes exact input rows,
expected canonical manifest bytes, and expected runtime ID so generator and
verifier cannot agree on the same accidental serialization change.

Shared artifact verification also reads the root `skills/rook-full/SKILL.md`
with a 16,384-byte UTF-8 ceiling, strictly decodes it, and binds the retained
text to the verified file row. Creation, packaging, promotion, and loading all
refuse invalid text before runtime publication or pointer advancement. Launch
uses that retained exact text; the path-dependent 30,000-UTF-16-unit rendered
command-line check remains at the launch boundary.

The staging directory is created as a unique sibling under the final release
`runtimes` parent. After complete verification, publication is:

```text
verified staging
-> derive runtime ID
-> destination = runtimes/<runtime-id>
-> same-volume create-only directory move
```

An existing destination is never overlaid or repaired. Trusted Rook tooling
verifies it completely against the same manifest and runtime ID and reuses it
only if verification succeeds; otherwise publication refuses without modifying
either directory.

### 12.6 Trusted Installation And Selection

The Rook installer carries one already assembled and verified runtime payload.
Customers install only Rook. Installation performs no Prime build, WSL launch,
Node, npm, Bun, `zip`, `unzip`, or separate Prime installation.

The installer's ordinary file table may populate only a unique incoming
directory. It must not write directly to `prime/runtimes/<runtime-id>`,
`prime/current.json`, or any historical runtime sibling. A Rook-owned promotion
implementation delivered by the signed/current Rook release verifies and
publishes the incoming runtime. Incoming `pi.exe` or Python code from the
incoming payload never verifies or publishes itself.

Local deployment invokes the same Rook-owned promotion implementation from the
reviewed worktree. Installation invokes its installed equivalent. Upgrade and
repair cleanup explicitly exclude `prime/runtimes/**` and persistent ACP data.

The pointer `prime/current.json` is bounded canonical UTF-8 JSON with no BOM,
exactly one terminal LF, and exactly this object:

```json
{"runtimeId":"<64 uppercase hexadecimal characters>"}
```

The promotion implementation writes a same-directory temporary file and
atomically replaces the pointer only after the selected installed runtime has
verified. There is no directory scan or fallback to a presumed latest runtime.

A new conversation reads `current.json` once, validates that complete snapshot,
verifies its selected runtime, records the runtime ID in the durable
association, and launches only that recorded ID. A later pointer change cannot
alter the admitted conversation. Existing conversations reopen only with their
recorded runtime ID.

Installed runtimes are immutable siblings. New Rook releases may add a newer
qualified sibling and advance `current.json`; they do not modify existing
runtimes. Historical runtime siblings remain through install, upgrade, repair,
and release rollback. Reference counting and garbage collection remain
deferred.

Before every launch or reopen, trusted production code revalidates the recorded
runtime ID, canonical manifest bytes, closed file set, platform, architecture,
ACP and SDK compatibility, Prime executable, skill identities, bundled `uv`,
Prime Python runtime subtree, and required notices. Missing or mismatched bytes
return `runtime_unavailable` before Prime starts. `pi.exe` is selected only by
its verified absolute path; there is no PATH, npm, global Prime, or user-install
fallback.

The running Python service supplies the Rook MCP declaration from its own
verified `sys.executable` with fixed arguments `-m rook`. Machine-local Rook MCP
paths never enter the Prime runtime manifest.

### 12.7 Mutable Prime Support State

Prime's executable payload is immutable, but Prime's supported mutable state
remains outside it:

- Prime credentials and user settings remain Prime-owned;
- product-assigned session files remain under the Rook data root;
- presentation history remains under the Rook data root;
- non-expiring `open.claim` fences remain under the Rook data root; and
- Prime kernel state remains in Prime's supported mutable location.

Persistent ACP data lives under `%LOCALAPPDATA%/Rook/data/rookchat/acp/v1`,
outside `{app}` and every runtime directory. Install, upgrade, repair, rollback,
and uninstall-with-data-retention leave sessions, associations, claims, and
presentation files untouched. Normal uninstall may remove `{app}` and its Prime
runtimes; it still preserves ACP data unless the user explicitly authorizes
data deletion. A later installation without a conversation's recorded runtime
returns `runtime_unavailable` rather than substituting another version.

The Prime child environment removes these inherited keys by case-insensitive
exact-name comparison:

```text
PI_PACKAGE_DIR
PRIME_AGENT_KERNEL_PYTHON
PRIME_AGENT_KERNEL_VENV
PRIME_AGENT_INSTALL_UV
VIRTUAL_ENV
PYTHONHOME
PYTHONPATH
PYTHONDONTWRITEBYTECODE
PYTHONPYCACHEPREFIX
```

It also removes every inherited key whose case-insensitive name begins with
`UV_`, then inserts exactly:

```text
UV_CACHE_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/cache
UV_PYTHON_INSTALL_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/python
UV_PYTHON_PREFERENCE=only-managed
UV_PYTHON_NO_REGISTRY=1
UV_PYTHON_INSTALL_REGISTRY=0
UV_NO_CONFIG=1
```

It additionally establishes `PYTHONDONTWRITEBYTECODE=1` after scrubbing inherited
bytecode-policy overrides. Prime passes that standard policy into its Python
processes, so ordinary imports of editable goal/runtime source do not write
bytecode into the immutable payload. The verifier does not ignore `.pyc` or
`__pycache__`; an import-then-reverify fixture must preserve the full closed file
set. This adds no kernel or Prime-owned-state implementation to Rook.

The manifest-verified `tools/uv` directory is prepended to the remaining child
`PATH`. Prime then owns Python acquisition, virtual-environment creation,
package installation, bootstrap versioning, and kernel lifetime. RookChat does
not create a contract-specific kernel or install Prime Python dependencies.

The first Prime session may begin kernel prewarm. The first IPython or Rook
operation may wait while bundled `uv` downloads Python, installs the
manifest-bound Prime runtime source, and resolves Prime's default Python
packages. This requires internet access and may take time, but requires no
separate customer installation. Failure is a Prime-owned tool failure;
RookChat does not retry, repair, or substitute a kernel.

Ambient Prime skills, extensions, MCP servers, context files, and prompt
templates remain excluded by the explicit launch configuration. Prime-owned
credentials and selected user settings are intentional mutable inputs.

### 12.8 Public-Seam Verification And Review Gates

Task 10 verifies complete entrypoints rather than extracted private helpers or
requirement phrases. Its bounded model-free tests cover:

1. The portable Bash entrypoint against a temporary Git repository and fake
   upstream builder, proving source admission, Linux-filesystem refusal,
   allowlisted environment, exact argv, GNU timeout, post-build custody, and ZIP
   hashing. Harness or infrastructure failure is distinct from an expected
   refusal.
2. The real Windows packager CLI over complete synthetic ZIPs, proving transfer
   hash custody, safe whole-archive extraction, fixed additions, the frozen
   manifest oracle, and tamper rejection.
3. The shared Rook-owned promotion entrypoint, proving that installer and local
   deployment pass exact roots to the same implementation; neither may publish
   final runtime directories or `current.json` independently.
4. Installer, upgrade, repair, rollback, and uninstall fixtures, proving staged
   installation, historical-runtime preservation where applicable, and ACP
   data retention.
5. The actual installed-verifier entrypoint over a complete minimal install
   fixture, proving missing, changed, extra, relocated, or substituted authority
   refuses and no success report is published after failure.
6. Production runtime selection through `load_and_verify_runtime()` and
   `build_prime_argv()`, proving the manifest-selected `pi.exe` becomes
   `argv[0]` without launching it.

Implementation of these public seams and tests stops for independent review
before a real Prime build runs. The same review freezes the ordered Prime patch
series, its exact final head, the `5c2750bd` adoption or deferral decision, and
the causal source tests for project-resource denial and ACP non-reachability of
managed helper acquisition.
After approval, the real build starts from a fresh Git-owned Linux checkout and
applies the post-build checks, transfers one ZIP, assembles one Windows payload,
verifies one runtime manifest, and stages the installer input. Prime itself is
not launched during Task 10. The exact archive hash, runtime ID, manifest,
installed layout verification, and source states are retained for review.

The actual packaged `pi.exe` lifecycle runs only in the separately authorized
external model-free Slice B qualification on Windows:

```text
initialize
-> session/new
-> session/close
-> EOF
-> clean exit
```

That external gate uses isolated Prime and Rook data roots, a daemon tripwire,
the bundled runtime, and no global Prime or PATH fallback. The lifecycle alone
does not claim kernel qualification. Slice B's separate deterministic-provider
path qualifies cold bundled-`uv` bootstrap, Prime's kernel, and fresh Rook MCP
delivery without contacting an external model.

The upgrade loop remains finite:

```text
new Prime upstream
-> determine which compatibility patches are still needed
-> build the supported Windows artifact in Ubuntu
-> run frozen ACP compatibility gates
-> publish a new immutable Rook runtime sibling
-> use it for new conversations
```

If reconciliation, build, assembly, or qualification fails, the current Rook
release remains on its last known-good runtime. No emergency compatibility
layer enters product runtime.

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

The only Prime compatibility surface is the short removable patch series
described in section 12. Each commit owns one bounded upstream-compatible
concern, and one exact final head identifies the complete runtime source.

## 15. Qualification

Qualification remains external to product runtime. It progresses through one
model-free pre-contact review gate and three separately authorized live gates.

### 15.1 Model-Free Pre-Contact Qualification: Slices A And B

Before creating any execution or evidence directory, admission requires the
exact independently reviewed qualification commit supplied by the execution
authorization. A mandatory `--expected-qualification-commit` argument carries
that literal; it is never inferred from current HEAD or from the protocol.
Require a clean worktree at exactly that HEAD, the protocol at its fixed
tracked path, and exact Git-blob bytes for the protocol, common runner,
pre-contact runner, and deterministic provider. Loaded qualification modules
must resolve to those same worktree files. A clean descendant or an alternate
protocol path cannot qualify. The protocol's product implementation commit and
source-input checks remain separate from this qualification-code identity.
Bounded, read-only Git subprocesses are permitted during admission to establish
that custody; they remain subject to exact-child ownership and cleanup.

The same read-only admission calls the production closed-file runtime loader,
compares the complete runtime contract with the protocol, constructs new and
reopen argv for the prospective session path, and checks the full final child
environment and hash. Both roots must be absent. No Prime, test, provider/proxy,
MCP, kernel, or other contact-capable process/service is started, and no workspace
or evidence directory is created, until all checks pass.
Pass that admitted preparation into Slice B; do not defer full payload
verification until after Slice A or replace the admitted session path later.

The protocol freezes one `qualificationConversationId`, exactly 32 lowercase
UUID hex characters. Before root creation, derive its path with the existing
`AcpDataPaths.session_path(qualificationConversationId)` under the protocol's
workspace-owned Rook data root: `.../sessions/<qualificationConversationId>.jsonl`.
Do not construct `AssociationStore` during admission. After admission and root
creation, construct `ProvisionalAssociation` with that same frozen ID, admitted
path, and admitted fields; validate the resulting Prime session header and use
the real `AssociationStore.publish()` path. Slice A retains coverage of ordinary
`reserve_provisional()` allocation. No new product allocator API or duplicated
UUID/path generator is needed.

Execution uses one fresh disposable workspace and one separate small evidence
directory. Their canonical paths are protocol inputs; neither may contain the
other or overlap source or runtime payloads. All mutable homes, sessions,
claims, presentation, temporary files, uv cache, managed Python, and kernel
files live in the workspace. Evidence receives only explicitly selected logs,
results, hashes, and bounded session-header evidence. Never recursively adopt,
hash, or chmod the workspace as evidence, and never reuse it for another run.
Workspace deletion is permitted only after every exact owned process and thread
has been observed stopped. If cleanup remains uncertain, retain the complete
workspace unchanged as non-authoritative diagnostic state; never reuse or adopt
it.

Evidence is limited to 16,777,216 bytes per file, 67,108,864 bytes in total, and
64 regular files, including admission, terminal, index, and seal files. Every
write or selected-file copy checks these limits before retaining bytes;
terminal/index/seal capacity is reserved. Unknown files, links, oversized
inputs, or excess entries refuse rather than becoming evidence by discovery.
Sealing covers only admitted evidence files. A large kernel or cache file in
the workspace cannot consume evidence capacity or make sealing traverse it.

Direct qualification children remain owned from successful spawn through
observed exit. Timeout, overflow, caller cancellation, Ctrl+C, and any other
exception use the same shielded cleanup of the retained handle, with terminate
then kill and a bounded wait within the existing 30-second cleanup deadline.
Unobserved exit is a failure; cancel pipe readers and settle them boundedly
instead of waiting forever for EOF. Preserve and re-raise the triggering
exception. Local provider/proxy shutdown likewise requires each exact owned
thread to stop after its bounded join before copying journals or reporting
success; a live thread makes closure incomplete.

One protected finalization path covers admission-record writes as well as
execution. Attempt `result.json` once, create-only, then seal once. If result
publication or sealing fails, report that failure separately through bounded
runner diagnostics and nonzero exit, preserving any original exception. Never
recreate a terminal result to report a seal error or report failed sealing as
successful qualification.

#### Slice A: Product Boundary With Fake ACP Agent

```text
C# panel
-> authenticated HTTP
-> Python ACP broker
-> official Python ACP SDK
-> deterministic fake ACP agent
```

Resolve the Python, .NET, Node, and PowerShell executable paths before launch.
Build one small Slice A environment from explicit Windows/runtime essentials
and workspace-owned home/temp paths, with only the tool directories required
by the frozen commands on PATH. Do not inherit `os.environ`: provider secrets,
proxy values, `PI_*`, `UV_*`, `PYTHONPATH`, `PYTHONHOME`, Node/npm overrides,
ambient pytest controls, and arbitrary execution-policy values are excluded.
Any required addition must be explicit and nonsecret. Causal tests seed those
values and assert their absence at the subprocess boundary.

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
- production launch inclusion of `--no-approve`, absence of production
  `--offline`, and case-insensitive removal of inherited `PI_OFFLINE` from the
  final child environment;
- direct ACP startup/composition never reaching Prime's managed `fd`/`rg`
  acquisition boundary;
- exact service-owned `rook` MCP declaration injection;
- structured Rook success and refusal-envelope projection;
- direct and `rook_tools_read` GH mutation schemas advertising the required
  `expectedGhDocumentId` field, with transition tools exempt;
- accumulator, truncation-marker, original-byte-count, fallback-projection, and
  exact unknown-`_meta` limits;
- identical permission auto-approval behavior under readonly and full profiles;
- directly owned cleanup and all normal-close failure branches;
- no PID scan, PowerShell, process surveillance, or process-name cleanup.

#### Slice B: Staged Prime Payload And Cold Kernel Bootstrap

Use the exact assembled/staged Prime runtime payload verified through the
production loader, isolated Prime directories in the execution workspace, a
local deterministic fake provider, and a unique daemon-socket tripwire. This
does not qualify an installed Rook product; that remains the later promotion
gate. No external provider, model, Rook, Rhino, or Grasshopper contact occurs.

Before `session/new`, the gate proves that fresh `HOME`, `USERPROFILE`,
`APPDATA`, `LOCALAPPDATA`, `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, and the
derived Prime kernel root contain no reusable kernel or managed Python. The
runner removes every inherited `UV_*` key case-insensitively and then inserts
only the protocol-owned `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`,
`UV_PYTHON_PREFERENCE=only-managed`, `UV_PYTHON_NO_REGISTRY=1`,
`UV_PYTHON_INSTALL_REGISTRY=0`, and `UV_NO_CONFIG=1` values. It proves the
resulting final Prime child environment contains exactly those admitted `UV_*`
keys, so an installed or registered Python and ambient uv policy cannot satisfy
the gate. Only this isolated Slice B protocol adds Prime's broad `--offline`
flag. That qualification-only control suppresses unrelated updater and catalog
traffic; it is not a RookChat product launch argument and does not put the
separately admitted `uv` bootstrap into offline mode. A qualification-owned
CONNECT proxy admits only the frozen host/port destinations for clients using
the configured proxy, while loopback serves the deterministic provider and
Rook MCP double. Before inserting that proxy, the runner removes
all inherited `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` keys
case-insensitively. It then inserts only the protocol-owned proxy URL and
loopback bypass and asserts the complete final proxy map. The frozen host
allowlist is exactly
`github.com`, `api.github.com`, `objects.githubusercontent.com`,
`release-assets.githubusercontent.com`, `releases.astral.sh`, `pypi.org`, and
`files.pythonhosted.org`, on port 443. Cold bootstrap must produce at least one
`proxy_admitted` event and every observed admitted destination must be allowlisted.
Destination refusals, connection-establishment failures, internal forwarding
faults, exceeded bounds, malformed evidence, qualification-initiated interruption
and unobserved cleanup remain hard failures. Only a Python `ConnectionError`
raised directly by socket `send`, `recv`, or `shutdown(SHUT_WR)` during forwarding,
without a qualification stop request, may be recorded as `proxy_transport_aborted`.
Its bounded record must retain the admitted authority, operation, socket side,
direction, exception class/error codes, pending bytes, EOF/write-shutdown and stop
state. Classification is not inferred from error numbers, byte counts or text.
A valid abort record only permits the remaining validators to run: every existing
cold-kernel, runtime/source-identity, provider, MCP, filesystem, persistence,
cancellation and cleanup check must execute and pass. Encrypted connection closure
does not substitute for any check. Successful evidence retains the full bounded
abort journal and count, described as "observed transport aborts, cause undetermined".
No retry or replay is added. Historical `proxy_forward_failed` records, including
failed V4, are not relabeled or waived. An empty or start/stop-only ledger fails.
The bounded ledger describes observed configured
destinations only: CONNECT cannot inspect encrypted URL paths, and proxy
environment variables do not prevent direct network access. No firewall, TLS
interception, process polling, or product network machinery is added.

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
- hostile project fixtures at both the launch and resumed-session working
  directories, proving `--no-approve` performs no automatic project-resource
  discovery, loading, project-settings access, or project migration during
  startup/resume before model work, while global auth/settings and explicit
  goal/Rook skills remain. This is not a filesystem-sandbox claim about later
  model-initiated IPython or Rook access;
- managed `fd`/`rg` executables and their Prime-owned download directories
  absent before and after the staged payload's ACP lifecycle. The source
  composition test remains the authority that ACP never invokes helper
  acquisition; proxy destinations cannot substitute for that causal test;
- lazy MCP startup through the staged Prime payload;
- selection of `Scripts/python.exe` from the newly created Windows venv;
- installation of the manifest-bound local `dist/prime-agent-runtime` rather
  than a registry fallback;
- cancellation during an MCP call and session-close MCP cleanup;
- fresh MCP server establishment after same-file reopen;
- required launch configuration and excluded ambient resources;
- staged runtime manifest identity;
- zero daemon-tripwire contact;
- no surviving directly owned child after clean close.

The combined model-free pre-contact gate checks replacement and installation
contracts through source and staged fixtures:

- no ChatRunner execution path, backend selector, credential-health route, or
  tool loop remains;
- only Python imports the ACP SDK;
- installation, upgrade, rollback, and uninstall with data retention preserve
  ACP session data, presentation data, and `open.claim` fences;
- cleanup uses directly owned handles only.

Slices A and B have separate technical results but one pre-contact independent
review gate. These results do not establish installed-product qualification.

### 15.2 Slice C: Prime-Managed Authentication And Image

Use one frozen tiny image task with a known vision-capable subscription model.
Freeze the requested fully qualified model and reasoning arguments, image bytes
and hash, prompt, runtime manifest, and all finite limits.

Slice C has two explicitly separate proofs. Deterministic tests cover the
production panel -> authenticated local HTTP -> Python image validation ->
exact ACP content-block handoff. The separately authorized live test uses the
existing production ACP launch/transport components with an explicit empty MCP
declaration to exercise packaged Prime authentication and image handling.

The live test does not exercise the panel, HTTP routes, or conversation manager.
The unchanged production conversation manager supplies Rook MCP; do not strip
that declaration, rely on the model avoiding tools, add a production test mode,
or recreate the manager for qualification. This split does not prove a live
panel-to-model image round trip. Full product-path qualification with Rook
enabled remains in the later integration gates.

The claim is `exact requested model and reasoning arguments` unless
authoritative returned metadata proves the effective model. The reported OAuth
save confirmation and clean CLI exit establish developer login, not model
access. Bind `PRIME_AGENT_CODING_AGENT_DIR` explicitly to the approved private
directory in the Prime child environment. Qualification must not inspect or
copy credentials, include them in evidence/logs/fixtures, or target their
directory for cleanup. Prime alone may perform its normal token refresh.
Describe the live result as a Prime-managed authenticated subscription call
unless nonsecret authoritative evidence establishes a more specific claim.
Product code never reads `auth.json`.

The pinned Codex provider does not transmit an output-token cap. Wall-clock,
retained-output, answer-length, cancellation, and close limits are not provider
token or subscription-usage ceilings. Record returned usage when available;
otherwise report it unavailable. Cancellation does not establish immediate
cessation of server-side processing. Do not patch Prime to manufacture a cap.

The deterministic answer must depend on visible image content. This one live
version executes once after independent authorization, with no Rook MCP server,
Rhino or Grasshopper contact, retry, or prompt repair. Approval of this narrowed
qualification claim must precede runner implementation and execution review.

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
- production launches deny ambient project resources and managed helper
  downloads without enabling Prime's broad offline policy;
- Rook remains the sole authority for host operations and evidence;
- Grasshopper mutations use explicit optimistic document concurrency;
- Prime authentication remains Prime-owned;
- model selection is limited to supported new-conversation launch arguments;
- the exact installed Prime artifact and skill bytes are manifest-bound;
- ChatRunner and Task 7 product machinery are absent;
- the model-free pre-contact gate and separately authorized live gates pass without evidence
  overwrite or automatic retry.
