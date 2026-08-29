# RookChat Prime Primary Backend Slices 3-4 Design

**Status:** USER-APPROVED; INDEPENDENT REVIEW PENDING; UNIMPLEMENTED; UNQUALIFIED

**Date:** 2026-08-29

## Purpose

This specification defines the next two product-integration slices for the
Prime-backed RookChat path:

1. Slice 3 installs and qualifies the durable product Rook package under a
   mechanically read-only capability profile.
2. Slice 4 starts a fresh full-profile conversation and qualifies authentic
   Grasshopper mutation, Prime-native goal use, receipt-fenced observation,
   and evidence-grounded completion.

The two slices share one product architecture. Read-only is a temporary
qualification profile, not a separate product persona or permanent `rook_read`
architecture. A running Slice 3 conversation is never elevated into Slice 4.

This specification reconciles and extends the retained evidence in:

- `docs/superpowers/reports/2026-08-26-rookchat-prime-primary-backend-options.md`;
- `docs/superpowers/specs/2026-08-26-rookchat-prime-primary-backend-slice-0-contract.md`;
- `docs/superpowers/reports/2026-08-27-rookchat-prime-primary-backend-slices-1-2-qualification.md`;
- `docs/superpowers/reports/2026-08-28-rookchat-prime-primary-backend-slices-1-2-live-smoke.md`;
- `docs/superpowers/specs/2026-08-13-prime-mcp-structured-error-custody-design.md`;
- `docs/superpowers/specs/2026-08-15-gh-edit-admission-authoritative-results-design.md`;
- `docs/superpowers/specs/2026-08-12-grasshopper-receipt-fenced-behavioral-acceptance-design.md`; and
- the qualified experimental `integrations/prime/skills/rook-full` and Rook
  execution skills.

Those documents are evidence and precedent. This specification is the product
decision for Slices 3-4 where they differ.

## Frozen baseline

The implementation plan must start from the separately reviewed commits named
in its implementation goal. At design time the relevant qualified baseline is:

| Owner | Identity |
| --- | --- |
| Rook Slices 1-2 product branch | `6a62c6ae2655ae9badc2fc448e6af33456c230b7` |
| Prime RookChat branch | `7690c18479c909ddea67a34e86114f7f982179a8` |

The Prime executable identity is its frozen bundle-manifest hash. The git
commit is provenance, not a substitute for bundle custody.

Slices 1-2 remain qualified only for the exact opt-in text path. ChatRunner
remains the product default and rollback backend through Slices 3-4.

## Governing decisions

The product path is:

```text
RookChat panel
-> existing local broker and durable conversation registry
-> pinned Prime RPC session
-> explicitly admitted IPython
-> one immutable product Rook package
-> product-owned payload-first rook_full adapter
-> one fresh direct MCP/stdio child per adapter call
-> canonical Rook MCP gateway
-> RookNative and managed companion
-> immutable Rhino and Grasshopper targets
```

The governing ownership split is:

- Prime owns reasoning, model/provider behavior, saved sessions, transcript,
  IPython, compaction, goals, continuation, accounting, and completion.
- The broker owns Prime process residency, command correlation, durable
  conversation records, immutable runtime/profile/target custody, and event
  relay.
- Rook owns capability admission, live host identity, Rhino and Grasshopper
  operation, mutation, solve state, receipts, and authentic evidence.
- The panel owns user interaction and rendering. It does not own an agent loop.
- The model owns implementation, repair, and evidence-grounded judgment within
  the admitted product contract.

There is no broker-owned reasoning loop, task state machine, completion
heuristic, semantic supervisor, or second goal lifecycle.

## Scope

### Included

- one immutable, versioned, product-owned Python-backed Rook skill package;
- exact Prime goal-skill and Rook package allowlisting;
- exact `--tools ipython` activation, replacing the current `--no-tools` path;
- one generic file-backed Prime system-prompt CLI input;
- effective RLM recursion depth `0` for both slices;
- contract-keyed Prime kernel environments;
- broker-visible Prime goal projection;
- model-created Prime goals for substantive Rook work;
- direct MCP/stdio `rook_full.search`, `read`, and `call`;
- immutable Rhino process-generation and document custody;
- immutable Grasshopper `GH_Document.DocumentID` custody;
- read-only Slice 3 qualification;
- full-profile Slice 4 qualification;
- structured Rook failure preservation;
- bounded per-call MCP lifecycle and cancellation; and
- model-free causal gates plus one live execution per slice.

### Excluded

- a user-facing Inspection mode or persona;
- mid-session capability escalation;
- automatic capability routing;
- Prime subagents;
- panel image input, web search, steering, and prompt rewriting;
- arbitrary Python, process, network, or hostile-kernel containment;
- a broker MCP proxy, model-visible authority token, nonce, or Prime
  host-request protocol;
- MCP connection pooling;
- campaign runners or evaluator machinery in product code;
- semantic acceptance vocabulary or runtime semantic gates;
- completion terminalization or a post-completion execution fence;
- adapter call-limit ownership or experimental source-event recording;
- runtime-contract migration or garbage collection;
- dependency lock generation for later environment reconstruction;
- packaging cutover and installer-wide product enablement; and
- making Prime the default RookChat backend.

Prime subagents are deferred to a later deliberate product slice. They are not
rejected as a future capability.

## Architecture and owners

### RookChat panel

The panel continues to use the existing broker API and settled Prime prompt
path. It:

- creates a stable conversation ID;
- supplies the current Rhino process-generation and document identity;
- supplies the current Grasshopper document identity when a GH definition is
  bound;
- renders Prime text, lifecycle, errors, model identity, and goal status;
- disables conflicting user actions while a prompt or cancellation is active;
- issues Prompt, Stop, reopen, close, and native `/goal` commands; and
- never infers model completion from `agent_end`.

The panel does not parse or execute Rook tools.

### Python broker

The broker extends the approved Slice 0-2 registry and process owner. It:

- records one immutable runtime-contract fingerprint, capability profile, and
  target binding per conversation;
- verifies package, executable, environment, and target custody before launch;
- launches Prime with one closed capability configuration;
- performs broker-only runtime preparation and recursion controls;
- projects Prime `get_state.goal` and `goal_update` without creating a shadow
  goal record;
- correlates prompt settlement and cancellation using the existing Slice 0-2
  rules; and
- refuses launch or reopen when immutable custody cannot be established.

The broker does not call Rook operations on the model's behalf.

### Prime

Prime remains the sole agent/session owner. Slices 3-4 add only three generic
RPC controls to its existing RPC mode:

```text
set_rlm_max_depth
get_rlm_max_depth_status
prepare_ipython_runtime
```

The first two delegate to Prime's existing `AgentSession` methods. The third
awaits Prime's existing kernel provisioner with a bounded deadline, surfaces
failure, and returns the actual selected interpreter path. It exposes no
arbitrary code execution.

Pinned Prime currently treats `--append-system-prompt` as literal text, not a
file path. Slice 3 therefore also adds one generic CLI option:

```text
--append-system-prompt-file <absolute path>
```

Prime opens the file itself, requires valid UTF-8, and appends its exact decoded
content without frontmatter stripping, wrappers, or normalization. Read,
decode, or path failure aborts startup. This is a generic prompt-source option,
not a Rook-specific RPC or host protocol.

Prime retains its established settled-turn sequence, retry behavior,
compaction continuation, abort behavior, goal semantics, and saved-session
format.

### Product rook-full package

The package owns:

- persistent RookChat operating instructions;
- universal target and evidence discipline;
- Prime goal-use guidance for substantive work;
- the payload-first Python API;
- adapter lifecycle and structured-error behavior; and
- domain references loaded only when relevant.

It does not own Rook admission, solve state, receipts, or semantic completion.

### Rook MCP and host

The MCP server and host own live admission:

- the MCP target resolver verifies process-generation identity before
  selecting or contacting a loopback endpoint;
- the MCP profile wall admits or rejects tools;
- the native or managed host resolves the bound Rhino document before a
  target-dependent operation;
- the managed GH callback captures, verifies, and uses one exact GH document;
  and
- Rook returns authoritative operation results, receipts, solve readiness, and
  evidence.

## Conversation creation contract

Each Prime-backed conversation is created with one immutable tuple:

```text
conversation ID
Prime saved-session identity
runtime-contract fingerprint
capability profile
Rhino PID
Rhino process-start UTC ticks
Rhino document runtime serial
optional Grasshopper document ID
```

For the Slice 3 and Slice 4 Grasshopper qualifications, the Grasshopper
document ID is required. If a general future conversation is created without a
bound GH document, `/gh/*` calls fail `grasshopper_target_unbound`; the binding
is not added later. The user starts a new conversation after selecting the
intended definition.

The allowed profiles are:

```text
readonly
full
```

The profile is part of both the durable conversation record and the runtime
contract. A `readonly` process or kernel is never elevated. Slice 4 starts a
new `full` conversation.

After Slice 4 qualification, newly created Prime-backed RookChat conversations
are intended to receive the `full` profile automatically. Existing read-only
conversations remain read-only. ChatRunner remains the product default until a
separate cutover decision.

## Exact Prime launch contract

The broker replaces the current effective `--no-tools` configuration with one
unambiguous launch. It must not pass contradictory flags and depend on argument
order.

The effective Prime launch includes:

```text
--mode rpc
--no-skills
--skill <exact pinned Prime goal skill>
--skill <exact immutable product rook-full package>
--tools ipython
--append-system-prompt-file <exact immutable rook-full/SKILL.md>
--no-extensions
--no-context-files
--no-prompt-templates
```

The exact CLI spelling must follow the pinned Prime version. The semantic
requirements above are authoritative.

Prime reads and decodes the exact `SKILL.md` bytes through the generic file
option. The broker does not read, strip frontmatter, add a `/skill:` wrapper,
parse the file, or rewrite instructions. The resulting system-prompt content
is intentionally not claimed to be byte-identical to Prime's interactive
`/skill:` expansion, which applies its own wrapper behavior.

Only the pinned goal skill and product Rook package are admitted. No ambient
skills are loaded.

The broker sets `PRIME_AGENT_KERNEL_VENV` to the environment selected by the
runtime-contract fingerprint. Effective RLM maximum depth must be `0` before
model contact, so the root Actor cannot create Prime children during Slices
3-4.

## Product package and source manifest

The installed package layout is:

```text
%LOCALAPPDATA%/Rook/agent-contracts/<package-manifest-sha256>/rook-full/
  SKILL.md
  pyproject.toml
  src/
    rook_full/
      __init__.py
  references/
    ...
  package-manifest.json
```

`SKILL.md` owns universal product behavior. Grasshopper execution guidance
belongs in `references/` and is read only when relevant. Slices 3-4 introduce
no separate domain skill.

The canonical package manifest has this closed conceptual shape:

```json
{
  "schemaVersion": 1,
  "files": [
    {
      "path": "SKILL.md",
      "size": 123,
      "sha256": "UPPERCASE SHA-256"
    }
  ]
}
```

Rules:

- paths are relative, forward-slash normalized, and sorted ordinally;
- every admitted regular source file beneath the package root is included;
- references are included recursively;
- symlinks, junctions, reparse-point escapes, duplicate normalized paths, and
  paths outside the package root are rejected;
- the manifest excludes itself;
- exclusions are closed to `__pycache__`, `*.pyc`, `.pytest_cache`, `build`,
  and `dist`; and
- no unlisted file is admitted as package authority.

The SHA-256 of the canonical manifest bytes is the package identity.
Individual `SKILL.md`, adapter, and `pyproject.toml` hashes remain diagnostics.

The precise immutability claim is:

> Admitted source files are immutable and manifest-bound. Excluded generated
> caches carry no authority and may be created or removed.

Package directories are never modified in place.

## Runtime-contract fingerprint

One canonical runtime-contract record binds at least:

```json
{
  "schemaVersion": 1,
  "prime": {
    "bundleManifestSha256": "...",
    "gitCommitProvenance": "..."
  },
  "goalSkill": {
    "pathIdentity": "relative identity",
    "manifestSha256": "..."
  },
  "rookPackage": {
    "packageManifestSha256": "...",
    "skillSha256": "...",
    "adapterSha256": "...",
    "projectMetadataSha256": "..."
  },
  "capabilityProfile": "readonly",
  "rlmMaxDepth": 0,
  "runtimeCompatibilityVersion": 1
}
```

The canonical record's SHA-256 is the runtime-contract fingerprint. It selects:

```text
%LOCALAPPDATA%/Rook/agent-kernels/<runtime-contract-sha256>/
```

Conversations with the identical contract may share that environment.
Different contracts never do. Prime's existing environment-scoped bootstrap
lock serializes simultaneous preparation of the same environment.

Old package directories and environments remain retained while any durable
conversation record references them. Migration and garbage collection are
later product work.

## Runtime preparation and reopen

### First use

An absent environment is expected on the first use of a new runtime contract.
The broker:

1. verifies the Prime bundle, package manifest, paths, and contract record;
2. launches Prime with the contract-keyed environment path;
3. calls broker-only `set_rlm_max_depth` with `0` and `global: false`;
4. calls `get_rlm_max_depth_status` and requires exactly
   `{maxDepth: 0, source: "chat"}`;
5. calls `prepare_ipython_runtime` with a bounded deadline;
6. requires successful preparation and an interpreter path beneath the exact
   contract environment;
7. runs a fixed model-free import probe with that interpreter; and
8. records successful environment preparation in the durable conversation
   record before admitting the first model prompt.

The import probe has no arbitrary input. It proves:

- `rook_full.__file__` resolves beneath the recorded immutable package path;
- `goal.__file__` resolves beneath the recorded Prime goal-skill path;
- `rook_full.search`, `rook_full.read`, and `rook_full.call` are callable; and
- the interpreter is the one returned by Prime.

Preparation timeout, provisioning failure, partial environment state, wrong
interpreter, or wrong import origin fails before model contact. A failed first
preparation may be retried only after explicit cleanup by qualification or
product setup code; a partial directory is never treated as prepared.

### Reopen

Reopen verifies all recorded bytes and paths before Prime starts. It then:

1. requires the already-prepared environment to exist and match the contract;
2. launches the exact saved Prime session;
3. calls `get_rlm_max_depth_status` without writing it;
4. requires exactly `{maxDepth: 0, source: "chat"}`;
5. calls `prepare_ipython_runtime` only to await and inspect the existing
   selected runtime, not to reconstruct a missing environment; and
6. repeats the fixed import-origin probe.

A missing or incomplete referenced environment fails
`runtime_contract_unavailable`. Reopen never silently rebuilds it because
Prime dependency resolution is not yet fully content-locked. Future
migration/package-lock work may add explicit reconstruction.

The broker also fails `runtime_contract_unavailable` when any admitted package
file, package manifest, goal skill, Prime executable identity, diagnostic hash,
or path-root check differs.

## RLM recursion custody

Prime settings precedence means `RLM_MAX_DEPTH=0` alone is insufficient.

Slices 3-4 add generic RPC commands backed by existing `AgentSession` methods:

```text
set_rlm_max_depth(maxDepth, global)
get_rlm_max_depth_status()
```

For a new conversation, the broker sets `0` with `global: false` and requires
the readback source to be `chat`. On reopen it only reads and verifies. It does
not silently repair drift. These commands are broker-only and are not exposed
as panel actions.

Any other value or source refuses prompt admission. This defers all Prime
subagent execution during these slices without removing the capability from
Prime.

## Immutable target identity

### Rhino process generation

The durable base target is:

```text
Rhino PID
+ Rhino processStartUtcTicks
+ Rhino document runtime serial
```

`processStartUtcTicks` is the canonical positive decimal representation of the
same UTC tick value currently captured by the C# panel:

```text
Process.GetCurrentProcess().StartTime.ToUniversalTime().Ticks
```

RookNative discovery must independently compute the Rhino process creation
time from the Rhino process itself and publish the equivalent .NET UTC tick
value as a canonical decimal string. It must not copy the broker's value.

The MCP resolver requires an exact PID and parsed tick match before selecting
or contacting a loopback endpoint. Missing, malformed, noncanonical, or
mismatched ticks fail closed. There is no PID-only fallback and no native
nonce.

Every target-dependent operation carries the locked Rhino document runtime
serial. RookNative or the managed companion resolves that serial and refuses
before the requested operation if the document is absent or mismatched.

The broker owns expected-identity custody. The MCP gateway verifies the live
process generation before dispatch. Rhino/RookNative owns authoritative
process, document, mutation, solve, receipt, and evidence truth.

### Grasshopper document

Grasshopper's active definition is not selected by the Rhino document serial.
For every conversation admitted to `/gh/*`, the durable target therefore also
contains the exact nonempty `GH_Document.DocumentID`, normalized once to GUID
`D` format.

The locked value flows only through:

```text
broker durable target
-> sanitized Prime environment
-> unmodified rook_full adapter
-> closed MCP child environment
-> managed callback context
```

At managed callback entry, the GH bridge performs one indivisible operation:

```text
capture Grasshopper.Instances.ActiveCanvas once
-> capture its active GH_Document once
-> read exact GH_Document.DocumentID
-> parse and compare with the bound GUID
-> invoke the requested handler against that same captured document object
```

The handler must not re-read `ActiveCanvas` or resolve another GH document
after validation. Existing handlers that do so must receive the captured
document through the managed callback context.

Missing canvas, missing document, `Guid.Empty`, malformed bound GUID, closed
definition, or changed active definition refuses at managed callback entry
before invoking the requested handler operation.

No fallback to `DocumentGuid`, `InstanceGuid`, display names, arbitrary
strings, or other identifiers is admitted.

## Extended PanelTargetLock

The existing `PanelTargetLock` is extended. It is not replaced by a second
target abstraction.

In product `panel_locked` mode the following are mandatory:

```text
positive process_id
canonical positive process_start_utc_ticks
positive document_serial_number
canonical nonempty grasshopper_document_id for /gh/*
```

Missing or malformed base lock values prevent every adapter method from
launching an MCP child. A missing GH identity permits non-GH methods but causes
all `/gh/*` calls to fail `grasshopper_target_unbound`.

Within the supported `rook_full` API, explicit routing selectors may only agree
with the immutable lock. Conflicting port, session, PID, process tick, Rhino
document, GH document, or profile selectors fail. Model payload fields never
replace the lock.

Direct environment modification, monkeypatching, or raw transport remains
outside Slices 3-4.

## Adapter package and environment

The experimental adapter is productized without carrying campaign ownership.
The product version removes:

- hard-coded user paths;
- source-event recording;
- campaign gateway call limits; and
- campaign behavioral-acceptance imports.

It retains:

- payload validation;
- one fresh MCP/stdio session per call;
- closed result-envelope validation;
- structured Rook failure preservation;
- bounded launch/initialize/call/cancel/close behavior; and
- the public payload-first API.

Installed executable, working directory, install root, data root, and cache
paths come from a broker-validated product configuration. The adapter does not
accept them as model arguments.

Each MCP child receives a closed allowlisted environment. It contains only:

- minimal Windows bootstrap fields required by the pinned Rook runtime
  (`SystemRoot`, `WINDIR`, `COMSPEC`, `TEMP`, `TMP`, `USERPROFILE`,
  `LOCALAPPDATA`, `APPDATA`, and `PROGRAMDATA`);
- a product-constructed `PATH` containing the installed Rook environment and
  required Windows system directory, not the ambient parent `PATH`;
- product runtime fields (`ROOK_INSTALL_ROOT`, `ROOK_DATA_DIR`, `ROOK_MODE`,
  `DSPY_CACHEDIR`, `ROOK_DSPY_RESTRICT_PICKLE`, and `CHIRP_HOME`);
- closed Python isolation fields (`PYTHONHOME` and `PYTHONPATH` set to the
  product-defined empty values where required);
- `ROOK_MCP_TOOL_PROFILE`;
- `ROOK_MCP_TARGET_MODE=panel_locked`;
- the bound PID, process ticks, Rhino serial, and GH document ID; and
- any other field explicitly added to the versioned runtime compatibility
  contract after review.

No ambient target/profile variables, provider API keys, arbitrary parent
environment fields, or model-supplied environment values are inherited.

Target values are custody data, not secrets or bearer credentials. This design
does not claim hostile Python containment.

## Payload-first API

The model-facing Python surface is exactly:

```python
await rook_full.search(query)
await rook_full.read(name)
await rook_full.call(name, arguments)
```

Contracts:

### search

```text
input:  one nonempty string query
route:  rook_tools_search
output: exact JSON-compatible data payload from the successful Rook envelope
```

### read

```text
input:  one nonempty string capability name
route:  rook_tools_read
output: exact JSON-compatible data payload from the successful Rook envelope
```

### call

```text
input:  one nonempty string capability name + one exact dictionary of arguments
route:  rook_tools_call
output: exact JSON-compatible data payload from the successful Rook envelope
```

The adapter validates types before launch and deep-copies the call descriptor
once. Lease, transport, and result handling use the same frozen name and
arguments. `call` does not expose an alternate direct-tool route.

`search` and `read` remain subject to valid package/profile/target
configuration even when a particular query does not contact Rhino. A malformed
product lock fails before any child launch.

## Read-only profile

Slice 3 fixes `ROOK_MCP_TOOL_PROFILE=readonly` at conversation creation.

The canonical Rook profile wall remains default-deny. `rook_tools_call`
performs the read-only check before nested dispatch and then re-enters the
normal tool policy path. A mutator cannot be reached by naming it through the
meta-tool.

The live Slice 3 task demonstrates normal read-only behavior. Mechanical
enforcement belongs to model-free causal tests, not to stochastic model
behavior.

## Full profile

Slice 4 starts a fresh conversation and fixes
`ROOK_MCP_TOOL_PROFILE=full`. It uses the same package, API, target lock,
transport, and evidence discipline as Slice 3.

The profile does not bypass canonical tool schemas, host admission, document
resolution, receipts, solve readiness, or fenced observation.

## Structured result and failure semantics

Rook's closed public envelope remains authoritative:

```json
{
  "success": true,
  "data": {}
}
```

or:

```json
{
  "success": false,
  "data": {
    "error": "stable_rook_error",
    "message": "human-readable detail"
  }
}
```

Rook MCP emits an unsuccessful public result as MCP `isError` while retaining
the complete structured envelope. Prime's `McpToolError.structured_content`
must preserve it. The observed chain is:

```text
Rook envelope
-> MCP result
-> adapter/IPython
-> Prime event and saved session history
-> broker relay
-> panel
```

The broker does not translate a Rook error into a different semantic code.

Adapter-owned failures use a small closed family:

```text
rook_full_invalid_arguments
rook_full_launch_failed
rook_full_initialize_timeout
rook_full_call_timeout
rook_full_malformed_result
rook_full_outcome_uncertain
rook_full_close_failed
```

Each has a stable code and separate human-readable message.

The precedence rule is:

> An authentic Rook success or failure envelope remains authoritative even if
> subsequent child cleanup fails. Cleanup failure is retained separately and
> never erases the receipt or structured error. If no authentic envelope was
> received, the outcome is uncertain and is never replayed automatically.

For an authentic Rook failure plus cleanup failure, the adapter re-raises the
same `McpToolError`; cleanup is retained as lifecycle context without replacing
an existing explicit cause. For authentic success plus cleanup failure, the
successful payload remains the operation result and cleanup is retained in the
adapter/process diagnostic channel. Neither case authorizes replay.

## Per-call MCP lifecycle

Every adapter invocation owns one child and these bounded phases:

```text
validate frozen call descriptor
-> launch installed MCP process
-> initialize MCP session
-> perform one search/read/call
-> receive authentic envelope or explicit transport outcome
-> close session
-> graceful child exit
-> process-tree termination if grace expires
-> reap child
```

Launch, initialize, call, and close have separately configured finite
deadlines. A call timeout does not prove that mutation did or did not commit;
without an authentic envelope it returns `rook_full_outcome_uncertain` and is
not automatically retried.

Stop propagates through the real owners:

```text
panel Stop
-> broker sends correlated Prime abort
-> Prime cancels the active turn and IPython execution
-> adapter/MCP context closes
-> owned child exits or its process tree is terminated
-> Prime prompt settles
```

The broker does not directly own the MCP child. Qualification must prove the
causal propagation and absence of orphan processes.

Connection pooling is deferred. Qualification records per-call startup latency
descriptively. It is not a pass gate because no threshold is frozen in this
design.

## Persistent product instructions

The immutable `SKILL.md` is the standing RookChat product contract across
turns, compaction, and reopen. It tells the model:

- how to import and use `rook_full`;
- to read exact contracts before calls;
- to preserve target and evidence custody;
- to use fresh post-solve receipt-fenced evidence;
- to repair locally from authentic failures;
- when Prime goals are appropriate;
- how Stop and target loss affect ongoing work; and
- that `goal.complete()` must be the final tool action.

The broker does not prepend a hidden first-turn `/skill:` command or rewrite
every user prompt.

## Prime goal semantics

This immutable RookChat product contract is the explicit system authorization
under which the model may infer that qualifying substantive Rook work needs a
goal.

The model may call `goal.create()` only for clearly substantive work:

- multi-step authoring;
- repair cycles;
- extended investigation; or
- work likely to require continuation.

Simple questions, discussion, and bounded observation remain ordinary prompts.

Before `goal.create()`, the model calls `goal.get()`. The model cannot
supersede a pending nonterminal goal through `goal.create()`, including active,
paused, or budget-limited states. It must not create a replacement goal or work
around the existing one.

User-issued native Prime `/goal` commands retain their existing authority.
They may deliberately replace an objective, pause, resume, clear, or use
Prime's existing `stop` alias for clear. This user authority is not granted to
model-created goals.

The Slice 4 product contract requires the model to establish an active goal
before substantive mutation. Slices 3-4 do not make goal state a Rook gateway
prerequisite. Failure to create the goal is a qualification failure, not a
host mutation refusal.

Prime remains the sole owner of goal identity, persistence, continuation,
compaction, accounting, status, and completion. The broker stores no parallel
goal lifecycle.

## Goal projection in RookChat

The broker preserves Prime's existing state and events:

- `get_state.goal` supplies the current authoritative state at launch/reopen;
- `goal_update` supplies live updates; and
- existing `/goal` commands travel through the settled prompt route.

The panel displays at least the Prime objective and status so the user can see
why work may continue. This is a live projection, not a durable broker goal
record.

## Stop with an active goal

Stop aborts the current prompt, not the goal. Settlement has three possible
outcomes:

```text
confirmed abort + cleanup settled
-> broker idle
-> active goal remains active

work completed before abort won
-> broker records completed_before_abort
-> stale abort response is ignored

abort or cleanup outcome uncertain
-> broker failed
-> never idle by assumption
```

No model activity continues after a confirmed abort until another ordinary
prompt is admitted. Because the goal remains active, `/goal resume` is not
required. A later user interjection may be answered, after which Prime may
continue the active goal. `/goal resume` applies after an explicit pause or
another Prime-native state that admits resume.

Stop is never described as cancelling, clearing, pausing, or completing a
goal.

## Completion behavior

`goal.complete()` records the model's completion judgment. It does not certify
semantic correctness.

The product contract requires:

1. the last actual committed, solve-relevant mutation leaves the selected
   defaults restored;
2. readiness is awaited for that mutation's receipt;
3. a fenced snapshot uses the same receipt;
4. the model reasons from the retained evidence without another tool call;
5. `goal.complete()` is the final Actor tool action; and
6. only final text follows.

Any later Actor tool action, including Rook, IPython, or goal operations, makes
the Slice 4 live run incomplete. This is behavioral qualification, not a new
terminalization mechanism.

An audited no-op does not create a mutation receipt and cannot serve as the
final committed mutation.

## Reopen and target loss

Reopen restores the exact saved Prime session only after runtime-contract
custody passes. Goal status remains exactly as Prime persisted it:

- active remains active;
- paused remains paused;
- complete remains complete;
- budget-limited remains budget-limited;
- errored remains errored; and
- cleared remains cleared.

The broker does not infer or repair goal status.

A process-generation mismatch fails before Prime launch and leaves the saved
session untouched. If the process remains valid but the Rhino or GH document
is absent, switched, or closed, Rook refuses target-dependent work without
changing Prime goal bytes. An active goal therefore remains active and cannot
silently migrate to another target.

The user may resolve the condition through the native goal controls or by
starting a new correctly bound conversation. There is no silent retargeting.

A closed conversation is absorbing and cannot be reopened implicitly.

## Slice 3 model-free qualification

Slice 3 must pass model-free causal coverage before live contact.

### Runtime and package custody

- file-backed system-prompt loading preserves the exact valid UTF-8 content;
- missing, unreadable, or invalid-UTF-8 system-prompt files fail startup;
- valid manifest and runtime contract admit first preparation;
- package or diagnostic byte drift refuses before Prime;
- path escape or unlisted source refuses;
- preparation timeout and preparation failure are surfaced;
- a partial environment after failed preparation is not admitted;
- wrong interpreter or import origin refuses;
- referenced environment missing on reopen refuses without rebuild;
- `set_rlm_max_depth(0, global:false)` plus exact readback succeeds for a new
  session;
- reopen refuses any depth/status drift without repairing it;
- two simultaneous same-contract conversations share one stable environment;
  and
- simultaneous old/new contracts retain their own imported `rook_full` bytes.

### Target custody

- complete PID/ticks/Rhino serial lock admits the matching host;
- missing or malformed lock fields prevent child launch;
- same PID with different process ticks refuses before HTTP/native dispatch;
- wrong Rhino document serial produces no requested operation;
- explicit model selectors cannot replace the lock;
- GH calls without a bound GH ID refuse;
- missing, wrong, closed, or switched GH document refuses at managed callback
  entry;
- GUID comparison uses exact `GH_Document.DocumentID` values; and
- a test double that returns the intended GH document during validation and a
  decoy during a hypothetical later lookup cannot redirect the operation,
  because validation and execution consume the same captured object.

### Profiles, transport, and errors

- readonly direct mutators refuse before dispatch;
- readonly nested `rook_tools_call` cannot reach a mutator;
- full profile reaches an admitted fake mutation path;
- child environment contains only the closed allowlist;
- authentic Rook success survives later cleanup failure;
- authentic Rook structured failure survives adapter, Prime, broker, and panel
  projection, including later cleanup failure;
- no-envelope transport loss produces uncertain outcome and no replay;
- Stop during launch, initialize, and call leaves no owned child;
- close timeout terminates and reaps the process tree; and
- late completion after cancellation cannot publish into a retired prompt.

### Goal and broker lifecycle

- Prime rejects model `goal.create()` when a nonterminal goal already exists in
  active, paused, or budget-limited state;
- user `/goal <objective>` supersession remains native and intentional;
- Stop covers confirmed abort, completed-before-abort, and uncertain cleanup;
- a user interjection after Stop can be answered before automatic active-goal
  continuation;
- active, paused, complete, and cleared goals reopen unchanged;
- document loss refuses Rook work without altering goal bytes; and
- a closed conversation cannot reopen.

## Slice 3 live observational qualification

Qualification setup is external to product behavior. Before Prime contact it
creates:

- one deterministic partially broken adjustable X-axis point-row GH
  definition;
- one distinct decoy GH definition;
- exact component, control, wire, diagnostic, and known-defect facts;
- canonical `DocumentID` values for both definitions; and
- structural snapshots of both definitions.

The intended definition is active when the fresh `readonly` conversation is
created. The conversation is immutably bound to its GH `DocumentID`.

The exact model prompt is:

> Inspect the currently bound Grasshopper definition without modifying it.
> Report its existing controls, components, wiring, current errors or
> warnings, and whether the intended adjustable X-axis point-row behavior
> appears complete. Stop after giving an evidence-grounded assessment.

The live run qualifies ordinary read-only behavior, not enforcement of the
profile wall. It passes only when:

- the exact runtime/package/target preflight passed before contact;
- the model created no Prime goal;
- the Actor attempted no mutation and received no mutation receipt;
- all Rook operations resolved against the intended captured GH document;
- no operation resolved against the decoy identity;
- both definitions match their structural baselines afterward;
- the final answer accurately reports the frozen finite fixture facts;
- Prime and broker settle normally; and
- retained evidence is sealed and verified before interpretation.

Exterior review compares the answer to the frozen finite fixture after
settlement. No evaluator result or correction enters the runtime loop.

The run occurs once. There is no retry, prompt repair, or configuration tuning.
Per-call startup latency is retained descriptively and has no pass threshold.

## Slice 4 fixture and fresh conversation

Slice 4 uses the same intended broken definition after Slice 3 proves it was
not changed. Qualification preserves:

- the exact seeded identities and structural baseline;
- the known defect and finite behavioral expectations;
- intended and decoy GH document IDs; and
- selected default control values.

It starts a fresh Prime conversation with a separately hashed `full` runtime
contract bound to the same intended GH document. It does not reuse, elevate,
or resume the Slice 3 conversation, process, or kernel.

The exact user prompt is:

> The current Grasshopper document contains a partially broken adjustable
> X-axis point-row definition. Repair it in place so the existing Start, Step,
> and Count controls determine the first X coordinate, spacing, and point
> count, with Y and Z fixed at zero. Preserve working components where
> practical, resolve any current errors or warnings, and verify the behavior
> before stopping.

The prompt does not mention Prime goals and does not reveal the known repair.

## Slice 4 Actor requirements

The standing product contract, not the user prompt, instructs the model to:

1. orient with read-only evidence as needed;
2. call `goal.get()`;
3. create a real Prime goal before its first substantive mutation;
4. repair locally rather than replacing useful work without evidence;
5. exercise consequential controls;
6. restore selected defaults;
7. inspect final same-receipt evidence; and
8. call `goal.complete()` as its final tool action.

These are behavioral requirements. Rook does not mechanically gate mutation on
Prime goal state. Failure makes the run incomplete.

The Actor mutation trace is bounded and attributable:

- every committed mutation has one authentic unique receipt;
- no committed operation is replayed;
- final structural changes are limited to those reasonably necessary to
  repair the seeded defect;
- useful existing components are preserved where practical;
- control perturbations are temporary;
- all selected defaults are restored;
- the decoy definition remains unchanged; and
- `R` is the receipt from the last actual committed, solve-relevant mutation
  that leaves those defaults restored.

An audited no-op is not `R` and earns no mutation or completion credit.

The Actor-owned terminal sequence is exactly:

```text
last actual committed mutation R leaves defaults restored
-> readiness wait for R
-> fenced snapshot for R
-> model-only reasoning with no further tool call
-> goal.complete()
-> final text only
-> broker settlement
```

Any later Actor tool call makes the run incomplete.

## Actor/evaluator evidence boundary

The finite point-row behavioral evaluator may run only after Prime and broker
settle. Before it begins, qualification performs this boundary:

```text
Actor settlement
-> seal Actor trace and final receipt R
-> preserve Actor fenced snapshot(R)
-> record Prime goal complete state and broker settlement
-> begin a separately identified evaluator trace
-> evaluator perturbs and evaluates
-> evaluator restores
-> verify final structural equivalence
```

Evaluator receipts are never attributed to Prime, the Actor, its goal, or its
completion evidence. Actor final-receipt selection is frozen before evaluator
activity starts.

The evaluator must be the existing finite point-row evaluator and remain
byte-compatible with its previously qualified contract. If it is not
byte-compatible, the live run stops before evaluator contact for renewed
review. It is silent during Actor execution and supplies no feedback to the
model.

Evaluator perturbations are qualification activity, not product behavior.

## Slice 4 result dimensions

The report must keep four outcomes independent:

1. graph and finite behavioral result;
2. Rhino/GH target, mutation, receipt, and fenced-evidence custody;
3. Prime goal creation, live projection, and completed final state; and
4. broker/panel prompt settlement and process cleanup.

A correct graph without model-created goal completion does not qualify the
combined Slice 4 contract. A completed goal without correct target/evidence
custody also does not qualify it.

Slice 4 occurs once with no retry, prompt repair, or hidden tuning. An
incomplete or failed result is preserved honestly.

## Slice 4 pass criteria

The single live run passes only when:

- the full runtime/package/target preflight passes before model contact;
- a fresh `full` conversation is used;
- the intended GH document remains the captured execution target;
- the decoy remains unchanged;
- the model creates a Prime goal before its first mutation;
- the panel visibly projects the active goal objective/status;
- all Actor mutations satisfy the bounded attribution rules;
- no mutation is replayed;
- the final actual mutation receipt `R` leaves defaults restored;
- readiness and final snapshot use `R`;
- no Actor tool follows `goal.complete()`;
- Prime reports the goal complete at settlement;
- Actor evidence is sealed before evaluator activity;
- the finite evaluator passes and restores structural equivalence;
- evaluator receipts remain separate;
- all four result dimensions pass; and
- evidence manifests verify before the report claims success.

## Evidence and reporting

Qualification evidence is written directly to a durable non-temporary root.
Each slice receives a separate root and non-self-referential SHA-256 manifest.

Retained evidence includes only what is required to reproduce custody and
interpret the result:

- frozen configuration and hashes;
- durable conversation registry record;
- Prime saved-session bytes and relevant projected events;
- package and runtime-contract manifests;
- preflight results and effective recursion status;
- import paths and interpreter identity;
- target discovery and managed GH identity records;
- Actor Rook call/result trace available through product/runtime evidence;
- before/after intended and decoy snapshots;
- receipts, readiness result, and fenced snapshot;
- broker lifecycle and process cleanup result;
- separate evaluator trace for Slice 4; and
- per-call startup latency.

Credentials, auth files, environment values containing secrets, unrelated
sessions, and unrelated host state are excluded.

Evidence capture may use external qualification scripts, but campaign runners,
evaluators, and experiment vocabularies do not enter product code.

## Qualification order

The implementation qualification order is:

1. Prime generic RPC unit and integration tests;
2. package manifest and runtime-contract tests;
3. broker launch/reopen/import-custody tests;
4. target/profile/adapter/structured-failure tests;
5. managed capture-once GH identity tests;
6. Stop and process-cleanup causal tests;
7. goal projection and lifecycle tests;
8. complete model-free offline gate;
9. independent implementation review;
10. one Slice 3 live read-only run;
11. Slice 3 evidence sealing and independent review;
12. one fresh Slice 4 live mutation run; and
13. Slice 4 Actor/evaluator sealing, reporting, and independent review.

Slice 4 is not authorized merely because implementation tests pass. Slice 3
must first qualify the shared package, target, and observational path.

## Product result after Slice 4

If Slice 4 passes, the qualified product statement is limited to:

> On the exact pinned Prime/Rook runtime contract, a newly created opt-in
> Prime-backed RookChat conversation can receive the full Rook profile,
> reason through Prime, create and complete a Prime-native goal for substantive
> work, mutate the immutably bound Grasshopper definition through the
> product-owned rook_full adapter, and complete from authentic receipt-fenced
> evidence.

It does not establish:

- hostile Python or network containment;
- arbitrary model/provider qualification;
- universal task correctness;
- semantic completion certification;
- default-backend product cutover;
- image, web, steering, or subagent behavior;
- persistent MCP performance; or
- migration between runtime contracts or targets.

## Deferred follow-up

Potential later slices, only if product evidence justifies them, include:

- packaging and default-backend cutover;
- explicit runtime-contract migration and garbage collection;
- content-locked Python dependency reconstruction;
- Prime subagents with deliberate Rook inheritance and evidence custody;
- panel image input and visual self-observation;
- web search;
- steering UX;
- persistent MCP transport if measured startup latency is material; and
- stronger IPython/process/network containment.

None is required to implement or qualify Slices 3-4.
