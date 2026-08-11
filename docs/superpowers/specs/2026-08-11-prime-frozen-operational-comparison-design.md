# Prime Frozen Operational Model Comparison Design

**Status:** Design and plan amended for runtime-resolution custody; awaiting renewed independent review
**Date:** 2026-08-11
**Baseline:** `06534f371b173308179164189e54b722a34f8a24`
**Branch:** `codex/prime-frozen-control-local-comparison-design`

## Purpose

This design defines one two-row, operator-owned qualification of two models in the
existing Prime Agent and Rook execution system:

```text
Control: anthropic/claude-opus-4-6
Local:   ollama_chat/qwen3.6:35b
```

It is an **operational agent comparison**. Each model receives the reasoning
configuration a competent operator would normally use. It is not a weights-only
comparison and does not force either model into an artificial no-reasoning mode.

The comparison asks how each frozen operational row handles the same Grasshopper
authoring intent through the same reviewed capability boundary. It does not introduce a
new agent runtime, evaluator, score, recorder, skill router, or Rook product behavior.

The exact intent is:

> Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.

## Qualified foundation

The comparison starts from these already reviewed identities:

| Owner | Frozen identity |
|---|---|
| Rook repository and deployment | merge `06534f371b173308179164189e54b722a34f8a24` |
| Prime Agent repository | commit `c98941a2a5cf40faecf9b4648ac3c304abf48fd3` |
| `rook_full` adapter | SHA-256 `E7577F0EC8A9B504712BC73290BB8F4C673E9677AEF952CFBFC346F206A62996` |
| reviewed execution skill | SHA-256 `0F7C8D1F2D612FFB7522469C4E3D467985E8872585CA3C18DF9B46BD1A84D36E` |
| referenced checkpoint | SHA-256 `76A7C0CFF04DEF83A75519A546AC812804AC32BBF30CC14609A6D52950248964` |

The adapter's supported public Python API remains exactly:

```python
__all__ = ("search", "read", "call")
```

Those functions remain structurally bound to the canonical Rook meta-tools:

```text
search -> rook_tools_search
read   -> rook_tools_read
call   -> rook_tools_call
```

Rook retains discovery, schemas, validation, profile policy, targeting, dispatch, and
receipts. Prime retains the agent loop, IPython execution, provider interaction, session
record, and usage reporting.

The comparison does not re-qualify the adapter or component-discovery implementation.
Their exact hashes and deployment custody are preconditions.

## Runtime-resolution custody invariant

Every runtime claim follows one ownership chain:

```text
declared identity
-> runtime resolution
-> observation at the layer that owns the effective outcome
-> retained correlated evidence
```

Configured or on-disk input state cannot stand in for the effective runtime fact:

```text
intercepted transport exception != Prime-observed terminal outcome
deployed file alone             != payload selected by a running Rhino process
mutable Ollama tag              != immutable local model artifact
```

Prime stream events own the no-contact provider outcome. A clean standard Release
deployment, exact companion registration, and a later fresh Rhino process own Rook
runtime selection. Ollama's exact manifest plus its config/layer digests own the local
model artifact. Each correlation is retained before the corresponding row may run.

The reasoning and credential decisions rely on reviewed Prime source at commit
`c98941a2a5cf40faecf9b4648ac3c304abf48fd3`:

- `D:/prime-agent/packages/agent/src/agent.ts:475` shows that Prime `off` omits a
  reasoning request rather than forcing provider reasoning off;
- `D:/prime-agent/packages/ai/src/providers/openai-completions.ts` owns the
  OpenAI-compatible reasoning payload and converts transport exceptions into terminal
  stream `error` events;
- `D:/prime-agent/packages/ai/src/providers/anthropic.ts` owns the Anthropic adaptive
  thinking and effort payload and converts transport exceptions into terminal stream
  `error` events;
- `D:/prime-agent/packages/coding-agent/src/core/auth-storage.ts:810` owns runtime,
  stored-auth, and environment credential precedence;
- `D:/prime-agent/packages/ai/src/env-api-keys.ts:100` gives Anthropic OAuth precedence
  over the API key within environment credentials.

Provider semantics are corroborated by the official
[Ollama thinking](https://docs.ollama.com/capabilities/thinking),
[Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility),
[Qwen thinking](https://qwenlm.github.io/blog/qwen3/), and
[Anthropic authentication](https://platform.claude.com/docs/en/manage-claude/authentication)
documentation. The no-contact captures remain the executable authority for the exact
frozen rows.

## Approaches considered

### 1. Two isolated sibling rows — selected

Each row has its own disposable Prime agent directory, kernel, session state, memories,
working directory, evidence directory, and Grasshopper target. Common artifacts are
copied byte-for-byte and verified by hash.

This prevents the control model from contaminating the local row through files, Prime
state, learned refinements, or reuse of the mutated canvas. The rows deliberately share
one freshly deployed Rhino process to preserve loaded-runtime custody; the comparison
does not claim Rhino process-state isolation between rows.

### 2. One shared Prime root with two evidence directories — rejected

This saves a small amount of disk duplication but allows control-owned state and file
writes to influence the local row. Detecting that contamination after the fact is weaker
than preventing it.

### 3. Manual launches with post-run comparison — rejected

This avoids an operator package but does not establish exact row custody, one-shot
behavior, cross-row parity, evidence correlation, or target sequencing.

## Frozen system equation

The intended invariant is:

```text
same Prime Agent commit
+ same explicit rook_full adapter bytes
+ same execute-grasshopper skill bytes
+ same Rook merge and full-profile deployment
+ same exact intent
+ same Prime invocation policy
+ same evidence and assessment contract
+ equivalent fresh empty target state
+ same freshly deployed Rhino process and native port
+ separately verified medium reasoning requests
+ predeclared provider/model route
-> two operational rows differing only through an explicit allowlist
```

The two rows intentionally differ in model implementation, provider protocol, endpoint,
credential mode, provider-specific reasoning representation, isolated absolute paths,
and sequentially frozen target identity. Those differences are reported rather than
hidden.

## Isolation model

The disposable comparison root contains two complete sibling roots:

```text
control/
local/
```

Each sibling owns exactly one:

- isolated Prime agent directory;
- isolated Prime settings and model configuration;
- isolated IPython kernel and dependency environment;
- isolated Prime session and memory state;
- isolated working directory;
- isolated stdout, stderr, and final-inspection evidence directory;
- immutable non-target row;
- later-created target record;
- one-shot launch marker.

Neither row may read or reuse the other row's session, memories, evidence, target, or
working files. The experiment does not claim OS sandboxing: Prime's IPython kernel still
runs with the operator's filesystem and process permissions. Isolation here establishes
experimental custody, not a security boundary.

Built-in skills are disabled, packages and extensions are empty, and Prime is invoked
with its existing offline/update-suppression and no-extension controls. The reviewed
Rook execution skill is explicitly loaded by code-owned path. Provider inference remains
the only permitted model-network activity.

## Two-part row identity

Each row is sealed in two parts.

### Immutable non-target row

Before the control target is created, both rows freeze every non-target fact:

```text
schema
rowId
provider
model
modelArtifactIdentity
apiBase
credentialMode
reasoningRequest
reasoningCaptureHash
intent
repositoryIdentities
artifactHashes
dependencyHashes
primeInvocation
limits
evidenceContractHash
assessmentContractHash
isolatedPaths
```

The non-target row is never rewritten after its hash enters the comparison manifest.

### Sequential target record

Each row later receives one separately hashed target record containing exactly:

```text
processId
nativePort
documentSerialNumber
initialSnapshotRequestHash
initialSnapshotResultHash
initialStateVerified
```

A complete live row identity is:

```text
non-target row SHA-256
+ target record SHA-256
+ row manifest SHA-256
```

This split permits target B to be created after the control review without changing any
model, prompt, skill, adapter, setting, acceptance rule, or interpretation contract.

## Cross-row parity contract

### Byte-identical common artifacts

The following must be byte-identical between sibling roots:

- `rook_full` adapter;
- reviewed execution skill;
- checkpoint reference;
- frozen dependency specification;
- exact intent artifact;
- operator launcher;
- final inspector;
- evidence contract;
- assessment contract.

### Parsed parity

`agent/settings.json` must be parsed-equal without normalization. Model definitions, row
files, and manifests may contain row-specific values. Their parity normalizer may replace
only the following exact JSON Pointer leaf paths with one common sentinel.

`agent/models.json`:

```text
/providers/ollama_chat/baseUrl
/providers/ollama_chat/api
/providers/ollama_chat/apiKey
/providers/ollama_chat/compat/supportsDeveloperRole
/providers/ollama_chat/compat/supportsReasoningEffort
/providers/ollama_chat/models/0/id
/providers/ollama_chat/models/0/reasoning
```

`operator/row.json`:

```text
/rowId
/provider
/model
/apiBase
/credentialMode
/reasoningRequest/providerApiShape
/reasoningRequest/providerWire/anthropicThinkingType
/reasoningRequest/providerWire/anthropicEffort
/reasoningRequest/providerWire/qwenReasoningEffort
/reasoningCaptureHash
/modelArtifactIdentity/kind
/modelArtifactIdentity/providerModelId
/modelArtifactIdentity/ollamaManifestPath
/modelArtifactIdentity/ollamaManifestSha256
/modelArtifactIdentity/config/mediaType
/modelArtifactIdentity/config/digest
/modelArtifactIdentity/config/size
/modelArtifactIdentity/layers/0/mediaType
/modelArtifactIdentity/layers/0/digest
/modelArtifactIdentity/layers/0/size
/modelArtifactIdentity/layers/1/mediaType
/modelArtifactIdentity/layers/1/digest
/modelArtifactIdentity/layers/1/size
/modelArtifactIdentity/layers/2/mediaType
/modelArtifactIdentity/layers/2/digest
/modelArtifactIdentity/layers/2/size
/limits/anthropicWorkspaceLabel
/limits/anthropicWorkspaceSpendLimitUsd
/isolatedPaths/root
/isolatedPaths/agentDir
/isolatedPaths/kernelPython
/isolatedPaths/workingDir
/isolatedPaths/stdout
/isolatedPaths/stderr
/isolatedPaths/sessionDir
/isolatedPaths/initialInspection
/isolatedPaths/finalInspection
```

The non-target `operator/manifest.json` may differ only at these escaped JSON Pointer
keys:

```text
/agent~1models.json
/operator~1row.json
/operator~1reasoning-capture.json
```

After target B is later frozen, `operator/target.json` parity permits exactly:

```text
/documentSerialNumber
/initialSnapshotRequestHash
/initialSnapshotResultHash
```

`processId`, `nativePort`, `initialStateVerified`, and the target schema must remain equal.
The target-phase manifest
may additionally differ only at:

```text
/operator~1target.json
/operator~1initial-inspection.jsonl
```

For each differing pointer admitted by that maximum allowlist, normalization records
exactly:

```text
file
pointer
controlPresent
controlValue
localPresent
localValue
```

and then replaces that exact leaf with a common sentinel in both parsed copies. Missing
parents are created only along that exact pointer for comparison. No ancestor object,
array, or arbitrary subtree may be removed. The normalized documents must then be deeply
equal. An extra nested property, extra array item, value change at any unlisted pointer,
or presence change at any unlisted pointer refuses parity. Allowlisted paths whose values
and presence are already equal need no replacement and do not appear in the difference
report.

The ordered complete non-target path/value report is frozen before target A. A separate
ordered target path/value report is created only after target B is frozen; it does not
rewrite the pre-control report. The comparison does not claim complete settings files are
byte-identical.

## Model and provider custody

### Control row

```text
provider:       built-in anthropic
model:          claude-opus-4-6
row identity:   anthropic/claude-opus-4-6
endpoint:       official Anthropic API
credentialMode: environment_api_key
```

No custom Anthropic provider, proxy, base URL, credential resolver, or provider alias is
permitted.

### Local row

```text
provider:       ollama_chat
model:          qwen3.6:35b
row identity:   ollama_chat/qwen3.6:35b
endpoint:       explicit credential-free loopback Ollama /v1 endpoint
API shape:      openai-completions
```

`credential-free` means the URL contains no embedded credentials. The Ollama
compatibility declaration retains:

```text
reasoning: true
supportsDeveloperRole: false
supportsReasoningEffort: true
```

The mutable local tag is not the artifact identity. Before target A, the local row freezes
the installed manifest at:

```text
C:/Users/bring/.ollama/models/manifests/registry.ollama.ai/library/qwen3.6/35b
```

with exact SHA-256:

```text
07D35212591FC27746F0A317C975A6D68754FB38E9053D82E25F06057AF28522
```

and exact manifest-owned identities:

```text
config:
  mediaType: application/vnd.docker.container.image.v1+json
  digest: sha256:5d1c86a949f7f3b5e75370e129765af7526f0cc1812a9de21a541da042596faa
  size: 462

layers[0]:
  mediaType: application/vnd.ollama.image.model
  digest: sha256:f5ee307a2982106a6eb82b62b2c00b575c9072145a759ae4660378acda8dcf2d
  size: 23938321664

layers[1]:
  mediaType: application/vnd.ollama.image.license
  digest: sha256:5f3a3c817e78f5b8a4ad2d2c458a3e4b2cce470d6c12642c4eeb12cb8a9bf51d
  size: 11357

layers[2]:
  mediaType: application/vnd.ollama.image.params
  digest: sha256:86eff881e8d2c2b1caa3966ba775d007f76a693d8541d0973b1bd2aab4214a43
  size: 94
```

For each digest, remove the `sha256:` prefix and append the lowercase hexadecimal suffix
to `C:/Users/bring/.ollama/models/blobs/sha256-`. Every resulting content-addressed file
must exist with the exact manifest-declared size. The config/layer values and manifest
hash are retained in the immutable non-target row and rechecked immediately before the
Qwen row without invoking Ollama. Tag resolution, manifest mismatch, missing blob, or
size mismatch refuses the local row. This custody does not claim that every
multi-gigabyte blob was independently rehash-scanned by the qualification.

`modelArtifactIdentity` has one closed shape in both rows. The control uses
`kind="remote_provider_model_id"`, its exact provider model ID, and null Ollama fields.
The local row uses `kind="ollama_manifest_v2"`, its exact provider model ID, the values
above, and no null Ollama field. The control's three layer slots exist with null fields so
the cross-row difference remains mechanically leaf-allowlisted rather than excluding an
arbitrary subtree. Both objects contain exactly the listed keys, one config object, and
three ordered layer objects; an extra field, missing field, or different array length
refuses parity.

There is no model picker, provider fallback, default model resolution, or environment
override for either row.

## Reasoning custody

Both rows explicitly set Prime `thinkingLevel` to `medium`. Neither row uses `off`, and
neither relies on provider defaults.

Before any target or live row is created, a no-contact request-capture preflight uses:

- Prime's exact resolved model record;
- Prime's actual provider request builder;
- the exact isolated settings and model configuration;
- dummy credentials;
- intercepted transport that cannot contact a provider.

The capture occurs after payload and header construction but before network entry.

The interceptor and provider own different observations. The interceptor retains exact
private state proving:

```text
fetch entered exactly once
+ exact request captured
+ code-owned sentinel thrown before any saved/delegate fetch entry
+ zero saved/delegate fetch entries
```

The Anthropic and OpenAI SDKs wrap that thrown sentinel as `APIConnectionError`; Prime
therefore cannot observe the original sentinel message. Prime owns the provider outcome.
The capture consumes the returned stream normally and retains the exact event while
requiring the frozen real provider builders to produce exactly:

```text
one event
+ event.type == "error"
+ event.reason == "error"
+ event.error.stopReason == "error"
+ event.error.errorMessage == "Connection error."
+ zero done or additional events
```

The original sentinel is evidence only in interceptor-owned state. It is never required
to survive the SDK wrapper in the Prime event. Zero interceptor entry, a second fetch,
any saved/delegate fetch entry, an unexpected provider-wrapper outcome, `done`, or an
additional stream event refuses the capture.

### Required Opus capture

```text
thinking.type == "adaptive"
output_config.effort == "medium"
x-api-key == dummy sentinel
Authorization is absent
```

### Required Qwen capture

```text
reasoning_effort == "medium"
every outbound message role != "developer"
```

The Qwen capture also proves the request uses the frozen loopback endpoint and exact
provider/model record. The absence of a `developer` role causally verifies the frozen
`supportsDeveloperRole=false` compatibility setting at the outbound request boundary. A
boolean thinking-enable form is not admitted once
`reasoning_effort="medium"` has been proven available through the frozen Prime/Ollama
configuration.

The capture records exact provider-wire field presence and values, endpoint identity,
and a SHA-256 of the credential-redacted request evidence. It never records a real
credential. A missing, omitted, defaulted, or different reasoning field blocks both live
rows.

All shared Prime invocation settings are equal. Provider-owned model metadata and
provider-specific translations are retained explicitly, not misrepresented as byte-equal
wire requests.

## Anthropic credential and spend custody

The control uses a dedicated Anthropic workspace and workspace-scoped API key. The
workspace has a reviewed, operator-acceptable spend limit configured before contact.
The exact numeric limit and a credential-free workspace label are frozen in the control
non-target row. The comparison does not contain or infer the secret key.

The live child process requires:

```text
ANTHROPIC_API_KEY present and nonblank
ANTHROPIC_OAUTH_TOKEN absent
isolated auth.json contains no anthropic entry
no --api-key runtime override
no custom credential resolver
no alternate provider
```

Prime credential precedence is therefore unable to replace the intended environment API
key with runtime, stored, or OAuth credentials. The operator records only closed custody
facts, credential mode, and the configured spend ceiling. The real key is never logged,
copied, hashed, or written into a manifest.

The Qwen row has no remote-provider credential and uses only the frozen loopback Ollama
endpoint.

## Hard safety ceiling

Each live row has an absolute wall-clock ceiling of 30 minutes measured by an
operator-owned monotonic clock immediately before Prime process start. The clock ends
only after the final-inspection result is flushed or the row becomes ineligible for final
inspection.

```text
elapsed < 30 minutes
-> row may continue normally

elapsed >= 30 minutes
-> preserve the existing evidence prefix
-> mark the row incomplete
-> permit no operator retry or cleanup
-> block the second row pending independent review
```

If the ceiling arrives before natural Prime termination, terminate only the
qualification-owned Prime process tree and perform no final snapshot. If it arrives after
Prime termination while final inspection is pending or in flight, make no additional
inspection call, preserve the request or result prefix that already exists, and do not
terminate Rhino or Rook. In both cases the row is incomplete.

Timeout termination is a pre-authorized safety action, not an operator repair. It does
not revert or modify the Grasshopper canvas.

Prime's own provider retry behavior remains Prime-owned and is retained as evidence. The
operator, adapter, and qualification add no provider retry, MCP retry, rerun, or fallback.

## Release deployment and running-Rhino custody

Before target A, create a clean detached deployment checkout at exact Rook merge
`06534f371b173308179164189e54b722a34f8a24`. With Rhino and MCP processes stopped, run
exactly:

```powershell
./scripts/deploy-local-testing.ps1 -Configuration Release
```

Do not pass `-PayloadOnly`, `-SkipBuild`, `-UseRepoVenv`, `-DevPythonRuntime`,
`-AllowRunning`, or another deployment mode. Retain the complete deployment transcript,
exit code, start/completion wall-clock observations, exact checkout SHA, and hashes for:

```text
source and installed site-packages rook/server.py
source-build and deployed RookNative.rhp
source-build and deployed net8.0/Rook.rhp
```

The standard deployment explicitly registers
`.../RookNative/net8.0/Rook.rhp`. Retain the exact companion registry `FileName`, require
that exact normalized path, and refuse `net48`, `net7.0`, or a root-level fallback. This
pins the selected managed payload as `net8.0` for this campaign.

Only after successful deployment does the operator start Rhino. Retain the Rhino PID,
process creation identity/time, the Rook Chat panel-open line emitted by the newly loaded
companion, and the equation:

```text
deployment completed
AND net8.0 companion registration/hash was retained before Rhino start
AND Rhino process creation occurred after deployment completion
AND Rook Chat executed in that fresh process
-> campaign runtime-custody chain established
```

This is causal startup evidence, not an in-memory byte dump. On-disk hashes alone make no
loaded-binary claim. There is no deployment, payload replacement, or Rhino restart
between rows; Prime's ordinary per-call MCP subprocess lifecycle remains unchanged.
Targets A and B use the same exact Rhino PID and creation identity. Before every target
snapshot and model row, recheck that PID/creation identity, the registered `net8.0` path,
and all deployment hashes remain unchanged. Any drift stops the campaign; do not repair
it within this qualification.

## Sequential target custody

Target B is not created or frozen before the control run.

### Control sequence

```text
freeze all non-target artifacts for both rows
-> independently review hashes and parity
-> deploy exact Rook merge through the standard Release path
-> start one fresh Rhino process after deployment and retain runtime custody
-> create fresh empty disposable target A
-> corroborate exact PID, native port, listener owner, and document serial
-> take exactly one operator-owned initial snapshot
-> require the exact empty-state predicate below
-> freeze target A and its initial-snapshot evidence
-> obtain separate control-run authorization
-> run Opus once
-> retain final evidence
-> independently review the control row
```

### Local sequence

Only after the control review:

```text
reverify every local non-target artifact against its pre-control hash
-> require the same unchanged Rhino PID and creation identity
-> create fresh empty disposable target B
-> corroborate exact PID, native port, listener owner, and document serial
-> take exactly one operator-owned initial snapshot
-> require the exact empty-state predicate below
-> freeze target B and its initial-snapshot evidence
-> obtain separate local-run authorization
-> run Qwen once
-> retain final evidence
```

The two targets must be distinct Grasshopper documents with equivalent initial evidence
inside the same freshly started Rhino process. Their complete target triples and canvas
custody remain distinct even when the Rhino document serial is the same. No second Rhino
process, deployment, or restart is admitted between rows.

The initial snapshot uses the same canonical Rook gateway and reconstructed panel lock as
the row. Its exact fixed request is:

```text
rook_tools_call(
  name="gh_snapshot",
  arguments={"include_data": true, "max_preview_items": 3}
)
```

The exact empty-state predicate is:

```text
components == []
AND flows == []
AND (groups is absent OR groups == [])
AND (relays is absent OR relays == [])
AND diagnostics.total == 0
AND diagnostics.errors == 0
AND diagnostics.warnings == 0
```

Every clause is required. In particular, zero components and diagnostics do not make a
group-only or relay-only canvas empty.

Initial-snapshot failure, nonempty state, diagnostics, target drift, or evidence-write
failure prevents that row from being frozen and permits no model contact.

## Live row execution

Each row permits exactly:

- one Prime process;
- one Prime session;
- one exact user turn;
- natural model reasoning and correction within that turn;
- calls through the supported `rook_full.search/read/call` API;
- model-authored repeated inspections from fresh live evidence;
- the reviewed skill's one bounded correction after partial success, limited to failed or
  unapplied operations that remain authorized and semantically unchanged;
- model-authored cleanup of disposable execution-owned fixtures when the reviewed skill
  calls for it;
- existing Prime-owned continuation behavior within the frozen limits;
- one operator-owned final inspection when eligible.

It permits no:

- operator follow-up message;
- operator retry or campaign rerun;
- adapter retry or hidden automatic MCP replay;
- operator-authored canvas cleanup, reset, repair, correction, or fallback;
- alternate skill, model, provider, tool route, or target;
- modification of Rook or Prime between rows.

Model-authored inspection and correction are ordinary recorded agent behavior, not
operator retries. The operator does not intercept or pre-approve each such call. Replaying
already committed work, exceeding the skill's single correction, or modifying unrelated
pre-existing state is retained as model-discipline evidence rather than prevented by a
second qualification policy layer.

The intent reaches Prime byte-for-byte unchanged.

## Natural termination and final inspection

Normal Prime termination means the launcher observes natural process termination and the
required Prime JSONL and native session evidence are present, unique, and structurally
valid. Exit code may be nonzero. A model-declared task failure can therefore remain an
eligible observed outcome.

The final inspection equation is:

```text
normal Prime termination
+ evidence healthy
+ done/terminal lifecycle observed
+ no timeout, cancellation, forced termination, or custody refusal
+ zero qualification-owned Prime, IPython kernel, or Rook MCP child processes remain
+ frozen PID/port/listener/document still match
-> exactly one operator-owned final gh_snapshot
```

The final inspection reconstructs the exact panel lock from the row. It does not claim a
Prime subprocess's process-local context survived termination. It uses the same canonical
gateway and exact request as the initial snapshot.

An ordinary agent error followed by natural termination still permits inspection.
Evidence failure, target drift, cancellation, generator/process exception, timeout, or
missing terminal evidence permits zero final-inspection calls. A qualification-owned
Prime, kernel, or MCP process is identified from the operator-recorded process tree; any
such process still alive after Prime termination makes the row incomplete, blocks final
inspection, and receives no implicit cleanup.

The snapshot request and result are retained separately from Prime's session. They are
not manufactured Prime events. A request-write failure causes zero calls. A result-write
failure occurs after one call, preserves request evidence, fabricates no result, and makes
the row incomplete.

The final snapshot is evidence, not a verdict. It may establish controls, topology,
previews, and diagnostics, but it may not fully establish runtime semantics.

## Evidence contract

Each row retains:

- immutable non-target row and hash;
- target record and hash;
- row and comparison manifests;
- exact provider, model, credential mode, and credential-free API base;
- credential-redacted no-contact reasoning request capture;
- repository, deployment, adapter, skill, checkpoint, operator, inspector, settings, and
  dependency hashes;
- the campaign's standard Release deployment transcript, selected `net8.0` registration,
  pre-start payload hashes, and fresh Rhino process-start correlation;
- the local row's exact Ollama manifest hash, config/layer digests and sizes, and
  content-addressed blob existence/size observations;
- initial-snapshot request and exact result;
- Prime JSON stdout;
- Prime stderr;
- exactly one native Prime session record;
- exact visible IPython cells;
- exact model-authored public adapter calls and returned results;
- Prime's final response and lifecycle facts;
- final-snapshot request and exact result when eligible;
- wall-clock elapsed duration from a monotonic clock;
- Prime/provider-reported usage and token fields exactly as observed;
- closed completion or incompletion facts without an aggregate score.

Existing Prime evidence owns visible reasoning, code cells, tool arguments, tool results,
and provider usage. The qualification does not reconstruct hidden reasoning, raw provider
wire traffic, or calls not present in retained evidence.

The visible cells can directly prove use of `rook_full.search/read/call`. Internal mapping
to canonical meta-tools is established by the pre-contact adapter hash and inert
delegation tests; there is no separate live event observing that private dispatch.

## Assessment contract

Each row receives five independent conclusions.

### Gateway discipline

Report:

- every visible use of `rook_full.search/read/call`;
- any attempted lower-level, private, direct, or introspective bypass;
- whether the full MCP catalog was exposed;
- exact canonical mapping justified by adapter hash and inert tests, with its evidence
  limitation stated.

Gateway discipline does not imply task success.

### Discovery behavior

Report:

- the first explicit semantic plan present in visible evidence before first mutation, or
  state that none was retained;
- every discovery query and returned option consumed by the model;
- rank and source kind of selected candidates;
- GUID metadata reads and ambiguity handling;
- invalid discovery or metadata calls;
- irrelevant candidates consumed;
- elapsed time, visible cells, and usage before first mutation.

Do not infer hidden reasoning or require a prescribed topology or tool sequence.

### Mechanical outcome

Report from authentic receipts and final snapshot:

- created components and their types;
- wires and topology;
- control values and ranges;
- point previews where available;
- runtime errors and warnings;
- partial edits and corrections.

A clean diagnostic state is not semantic success.

### Semantic fidelity

Ask exactly:

> Do the retained tool records and final snapshot establish independent adjustable Start, Step, and Count controls producing the requested point row along X, with Y and Z structurally fixed at zero and no runtime errors? Any unsupported part remains explicitly unproven.

This conclusion distinguishes adjustable controls from merely present sliders, fixed zero
from small nonzero ranges, point data from numeric ranges, and plausible wiring from
actual semantics.

### Cost and latency

Report independently:

- wall-clock duration;
- visible IPython cell count;
- public adapter call count;
- calls and time before first mutation;
- cumulative usage fields and tokens reported by each provider;
- timeout or provider retry observations.

Provider token totals are **not directly comparable**. Tokenization, caching, reasoning
accounting, input/output categorization, and usage reporting differ between Anthropic and
Ollama. They remain per-row operational telemetry and never become a normalized score.

## Comparison rule

There is no aggregate score, winner equation, or compensating metric.

```text
gateway discipline
discovery behavior
mechanical outcome
semantic fidelity
cost/latency
```

remain separate. Semantic success cannot excuse gateway bypass. Mechanical success
cannot establish semantic fidelity. Low cost cannot offset an incorrect graph.

If both rows complete with healthy evidence, a final table may place their five
conclusions side-by-side. If either row is incomplete, retain both row facts but make no
comparative superiority claim.

## Failure and promotion boundaries

| Condition | Result |
|---|---|
| No-contact reasoning capture disagrees with the frozen contract | Freeze neither live row; no target or provider contact |
| Common artifact or parsed parity mismatch | Freeze neither live row |
| Release deployment, `net8.0` registration, or fresh-Rhino ordering is incomplete | Create neither target; no model contact |
| Deployed payload, registration, Rhino PID/creation identity, or startup evidence drifts between rows | Stop campaign; no repair or local row |
| Qwen manifest/config/layer/blob identity disagrees with the frozen local artifact | Refuse the local row without Ollama inference |
| Anthropic credential or spend custody fails | Refuse control before provider contact |
| Initial target or snapshot fails | Refuse that row before model contact |
| Control model reports failure but terminates naturally with healthy evidence | Take final snapshot; retain valid control outcome; local row may proceed after review |
| Control reaches 30 minutes or has infrastructure/custody failure | Preserve prefix; make no new inspection call; mark incomplete; block local row pending review |
| Control completes but any non-target artifact changes afterward | Refuse local target creation |
| Local target or snapshot fails | Refuse local model contact |
| A qualification-owned Prime, kernel, or MCP process remains after termination | Mark that row incomplete; zero final-inspection calls; no implicit cleanup |
| Either row has evidence or final-inspection failure | Mark that row incomplete; no operator retry, repair, or fabricated evidence |

Independent control review cannot change local artifacts or interpretation. It may only
authorize proceeding with the already frozen local non-target row or stop the campaign.

## No-contact verification requirements

Before target A exists, deterministic tests must prove:

1. Exact common-artifact hashes and byte parity.
2. Parsed equality after sentinel-normalizing only the exact JSON Pointer allowlist;
   adding one extra nested difference must refuse parity.
3. No pre-existing Prime session, stdout, stderr, snapshot, or launch marker in either row.
4. Isolated settings disable built-in skills, packages, and extensions.
5. Exact Prime and Rook repository/deployment identities.
6. Adapter public API and canonical delegation remain unchanged.
7. Both model identifiers and API bases are exact and have no fallback.
8. Opus request capture produces adaptive thinking, medium effort, and API-key headers.
9. Qwen request capture produces explicit `reasoning_effort="medium"`; inserting one
   outbound `developer` message must refuse the capture.
10. Both provider captures retain two correlated observations: interceptor-owned state
    proves one fetch entry, the exact request, the code-owned sentinel throw, and zero
    saved/delegate fetch entries; Prime-owned state contains exactly one terminal `error`
    event with the frozen provider-wrapper fields above and no `done` or additional event.
    Zero interceptor entry, a second fetch, an unexpected terminal wrapper, or an extra
    event refuses.
11. Anthropic OAuth, stored auth, CLI API-key override, and alternate providers refuse.
12. The real Anthropic key cannot enter row, manifest, stdout, capture, or hash evidence.
13. The local manifest hash, config/layer identities, and every content-addressed blob
    path/size match; a changed tag manifest, digest, missing blob, or wrong size refuses.
14. The 30-minute monotonic timeout before Prime termination causes zero final-inspection
    calls; a timeout after one inspection request permits no additional call. Both retain
    their exact evidence prefix and block the second row.
15. Target records cannot exist during the initial inert review.
16. One-shot evidence refuses any consumed sibling before process or host entry.
17. The empty-state projector accepts the exact empty predicate and rejects component-,
    flow-, group-, relay-, error-, or warning-bearing snapshots; group-only and relay-only
    cases are causal regressions.
18. A fake model may author repeated fresh inspections and exactly one bounded correction;
    all calls are retained while operator retries and hidden MCP replay remain zero.
19. A lingering qualification-owned Prime, kernel, or MCP child prevents final inspection.
20. Final inspection uses the exact frozen target and exact canonical snapshot request.

These tests use intercepted providers, fake process boundaries, and inert target records.
They contact no model, Anthropic API, Ollama, Rhino, Grasshopper, Rook MCP, or other live
system.

## Anti-quagmire boundary

This qualification adds no Rook or Prime repository production code. Its eventual
operator artifacts remain disposable and outside both repositories. The durable Rook
change for this slice is this specification, the later plan, and the eventual compact
comparison milestone.

Do not add:

- another agent runner or provider abstraction;
- a generic evaluation campaign or scoring framework;
- a database, trace index, replay engine, or retention service;
- a new recorder or event taxonomy;
- prompt tuning after observing the control;
- off-mode rows or additional models;
- a model-selected skill route;
- a Planner/Critic or delegation layer;
- MCP session pooling or Prime runtime modifications;
- Rook discovery, schema, tool, `gh_edit`, or `gh_snapshot` changes;
- operator/adapter cleanup, reset, repair, fallback, replay, or retry machinery beyond
  the frozen timeout safety action.

If the comparison requires a Rook product change, Prime product change, another model
row, another user turn, another final inspection, or a reusable evaluation subsystem,
stop and return for a new design decision.

## Claims and non-claims

A successful two-row comparison may establish only how these exact operational rows
performed on this exact intent against two equivalent empty live targets under the
retained evidence.

It does not prove:

- general model superiority;
- repeatability across runs, machines, models, or plugin catalogs;
- equivalent token accounting;
- equivalent internal reasoning effort;
- hidden-reasoning quality;
- OS-level isolation;
- an in-memory byte dump of the loaded managed plugin;
- an independent full-content rehash of the 23.9 GB Ollama model layer;
- arbitrary Grasshopper competence;
- mutation safety outside Rook's existing authority wall;
- that Prime should replace ChatRunner;
- that one model's result justifies changing Rook between rows.

The comparison answers a narrower and useful question:

> How does each selected model perform when run as a competent operator would configure
> it, while Prime, Rook, the reviewed skill, task, evidence contract, and acceptance
> criteria remain frozen?

## Authorized sequence after planning

This specification authorizes no implementation or contact. The later plan must preserve
these gates:

```text
construct both disposable non-target rows with inert tests
-> mandatory independent pre-contact review
-> separately authorize standard Release deployment from the exact merge
-> start one fresh Rhino process after deployment and retain runtime custody
-> prepare target A candidate
-> independently review deployment/startup correlation and target A candidate together
-> separately authorize target A initial snapshot
-> freeze target A and stop
-> separately authorize the Opus run
-> independently review Opus evidence
-> require the same unchanged Rhino PID and creation identity
-> separately authorize target B creation and initial snapshot
-> freeze target B and stop
-> separately authorize the Qwen run
-> independently review both rows
-> write one compact milestone without changing product code
```

No target, model, provider, Ollama, Rhino, Grasshopper, Prime live session, or Rook MCP
contact is authorized by this design document.
