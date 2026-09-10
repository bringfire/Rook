# RookChat First-Use Configuration Interface

**Status:** Proposed specification for independent review. No implementation, plan execution, credential access, login, model contact, build or deployment is authorized. The commands and message types below are proposed interfaces, not commands available in the installed runtime.

## 1. Purpose And Baseline

RookChat presents and edits configuration; Prime owns its meaning, validation, persistence and application. Prime is the only harness. This specification closes the interface-design portion of Phase 2 of the [roadmap](../plans/2026-09-08-rookchat-post-milestone-roadmap.md); it does not qualify customer onboarding or replace the remaining release gates.

Source inspected: Rook `292287f76a3d085dd113210d3677bf6fbe665444`; Prime `b71badc503f650cd7c10c4acd1206a8406aa0a0b`. The existing Prime runtime is `4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579`. None is changed by this document. The unresolved `knowledge/gh/notes/teaching_4f2b9009.json` modification remains untouched.

The installed panel currently offers requested model/reasoning at conversation creation, not account management. Health reports Prime-managed authentication ownership, not authenticated account status. Session initialization and "Prime ready" do not prove inference access. The historical developer-only OAuth procedure is not customer onboarding and must not be shipped as such.

## 2. Ownership And Customer Journey

The ordinary workflow uses RookChat branding. Provider names and the configured account/endpoint route remain visible and truthful. Runtime version/identity belongs in diagnostics. Do not claim an exact billing identity unless Prime supplies authoritative information.

| Stage | Required presentation and behavior |
| --- | --- |
| First opening | Read nonsecret configuration before creating a conversation. Show account connection, endpoint, model and reasoning controls; no automatic inference or login. A missing dedicated directory means unconfigured, not permission to adopt ambient credentials. |
| Connect | Offer Prime-supported OAuth, literal API-key methods and local Ollama without a cloud account. Show browser authorization and required provider instructions, requested input, cancellation and actual save outcome. No developer terminal, invented user credential or standalone Prime UI is required. |
| Select | Show Prime's catalog/capabilities and saved defaults separately from authentication status. Catalog presence and configured credentials are not verified model access. Save performs validation/persistence only. |
| First prompt | Explicit Send creates/uses the ordinary production conversation. Show starting, preparing and sending only from observed stages; do not fabricate percentage progress or call a model while opening settings. Existing preparation errors remain actionable and distinct from authentication errors. |
| Return | Read the dedicated configuration without automatic OAuth refresh or inference. Show saved defaults for new conversations and actual effective settings for an attached conversation when available. Do not relogin automatically. |
| Failure/cancel | Keep input and operation outcomes separate from cleanup. Do not retry login/writes automatically. An explicit nonsecret status re-read shows current observable configuration; an indistinguishable credential replacement remains unknown, not reconciled by presence/type. |

Rook owns presentation and conversation/process association; the official SDK owns ACP transport; Prime owns reasoning and conversational state; Rook owns Rhino/GH operations and authority. No replacement conversation manager, provider catalog, credential store, inference loop, private conversation protocol or mutation replay is introduced.

## 3. Invocation And Early Dispatch

Proposed configuration invocation, using the verified packaged executable without a shell:

```text
<verified-runtime>/pi.exe configuration --stdio --configuration-policy rookchat
```

RookChat settings use the existing authenticated local Python service. That service starts one short-lived child for one operation, supplies private redirected stdin, consumes stdout, observes exit and retains ownership through cleanup. Reuse existing bounded subprocess/I/O utilities where applicable; do not use the ACP conversation owner or send ACP close requests to this child. No new resident service is needed.

Prime must recognize this exact configuration command before owned-worker setup, `maybeStartDaemonEarly`, `main()`, migrations, project settings/resources, session/model initialization, updater, tracing startup, MCP or kernel startup. Import-time effects count: importing agent startup and then taking an early return is insufficient. Normal proxy/TLS support needed by OAuth remains available. Invalid command forms refuse without falling through into interactive/daemon mode. Existing `pi config` retains its unrelated package-resource selection behavior.

The proposed finite selector `--configuration-policy rookchat` also accompanies Rook's ordinary ACP launch, before any configuration resolution. It selects one explicit Prime-owned authority policy, not a pluggable policy system. Configuration mode requires it; existing Prime invocations without it retain their behavior. No environment alias or general operation dispatcher is added.

Both paths explicitly receive `PRIME_AGENT_CODING_AGENT_DIR=<Rook persistent-data root>/prime-config`, resolved from Rook's existing persistent-data paths, never a launch cwd. This is the dedicated customer location. Prime creates/owns configuration storage with private access appropriate to the user, using its existing storage helpers. The service uses a non-project working directory and does not accept a configuration-directory override from a UI request.

Only one configuration operation is admitted by the existing service at a time; overlapping requests return busy without spawning. No persistent operation registry, automatic adoption or replay. Existing Prime file locks remain necessary across independent owners; the UI busy check is not a substitute.

## 4. Configuration Authority And Literal Values

The selected Prime policy applies identically to configuration and conversation startup, including reopen. It admits the dedicated auth/settings/models files and Prime's compiled catalog/defaults. It excludes ambient provider credentials, external Prime CLI account configuration, provider/model/endpoint overrides and project-local configuration as authority for these choices. In particular, setting the agent directory alone is insufficient: startup currently enables the separate Prime CLI credential source explicitly.

Enforce this at Prime's actual authentication/model/provider consumers, including lower-level provider environment fallbacks. Preserve required Windows variables, networking proxies, CA/TLS behavior and existing unrelated launch constraints. Do not blank the environment or introduce a general environment-isolation framework. Never suppress private-provider authorization checks or use production `--offline` as an authority shortcut.

Literal handling is a consumer contract, not just input filtering:

- API-key and custom-header values from this interface are literal strings under this policy at save, status, reload, auth-source calculation and request construction. Never pass them through command/environment resolution. A key equal to the name of a populated environment variable still means those exact key bytes.
- Reject leading `!` after whitespace inspection in credential/header fields, rather than interpreting or escaping a command. Reject NUL and header line breaks. Validate without silently trimming or rewriting accepted secret bytes. Endpoints must be absolute HTTP(S) URLs without embedded userinfo, query secrets or fragments; local HTTP is allowed with an explicit insecure-transport disclosure. No shell syntax is an endpoint format.
- Existing command-backed values encountered in the dedicated directory refuse as unsupported configuration before command execution, including during status. Do not silently convert, execute, copy or delete them. Ordinary Prime behavior outside this policy is unchanged.
- No arbitrary provider JSON, command-backed values, environment-reference mode, custom executable, file path or shell operation is accepted by the interface. Advanced provider configuration outside the finite fields below is not silently rewritten by the editor.
- API keys and sensitive header values remain transient in Rook. Prime alone persists them. Do not place them in arguments, environment variables, logs, chat, telemetry, screenshots, test evidence, copied fixtures or durable Rook caches. Do not return stored secrets to populate editors; show presence and explicit replace/remove actions. Best-effort reference release is not a claim of guaranteed memory zeroization.

The policy needs a narrow extension to Prime's current `resolveConfigValue` consumers: the current resolver executes `!command` and otherwise checks `process.env[value]`. Rejecting `!` at the UI alone cannot satisfy literal semantics. Do not implement a second resolver/catalog in Rook.

No migration or credential copying from the working developer authentication directory is authorized. A future installation transition must be explicit; historical runtimes lacking this policy cannot be represented as supporting this new configuration contract. Their current manifest-driven reopen behavior is not changed by this specification. Rollout compatibility needs review before adopting a new runtime.

## 5. Finite Operations And Existing Consumers

Each invocation accepts exactly one `begin`. No inference/test-connection operation is included. OAuth connect is the only operation here permitted to contact an authentication provider; ordinary status, catalog and writes must not refresh tokens, fetch catalogs or probe endpoints. Prime's normal conversation token refresh remains Prime-owned.

| Operation | Input | Prime consumer and required interface work |
| --- | --- | --- |
| `status` | `{}` | `AuthStorage.getAuthStatus`, `ModelRegistry.getProviderAuthStatus`, SettingsManager getters. Return safe presence/route/default information without `getApiKey`, command evaluation or network refresh. |
| `models` | `{provider}` | Existing loaded ModelRegistry and model reasoning-capability functions. Return exact catalog selectors and supported levels for that provider; do not call `refreshAvailableModels` or confuse a configured source with verified access. |
| `oauth.connect` | `{provider}` | Registered OAuth provider and `AuthStorage.login` callbacks. Reconnect uses the same operation after explicit confirmation. Verify storage outcome after OAuth completion. |
| `oauth.disconnect` | `{provider}` | Existing `AuthStorage.logout`, restricted to dedicated configuration. Verify removal. This is not a claim of remote token revocation or invalidation of credentials already loaded by another process. |
| `apiKey.set` | `{provider,key}` | `AuthStorage.set` with literal key semantics and verified persistence. Nonempty valid syntax does not establish provider acceptance. |
| `apiKey.remove` | `{provider}` | Existing verified AuthStorage removal; preserve its failure behavior. Refuse a credential-type mismatch rather than silently logging out OAuth. |
| `endpoint.read` | `{provider}` | Nonsecret projection of the existing dedicated ModelRegistry configuration. Return editable endpoint/model fields and header names, never header values or keys. No endpoint probe. |
| `endpoint.save` | `{provider,baseUrl,api,authHeader,headers,models,compat?}` | Prime-owned writer extending existing models.json loading/schema/semantic validation, including the supported local Ollama route. Rook does not write this file. Preserve unrelated provider entries and refuse unsupported existing fields on the edited entry rather than discarding them. |
| `defaults.save` | `{provider,model,reasoning}` | Exact model resolution and supported-reasoning validation, then SettingsManager setters, `flush`, error checks and persisted readback. No live session mutation. |

`provider`, `model`, `api` and reasoning choices must be resolved by Prime. Rook can check message shape and bounds but cannot introduce provider validation rules or claim setter return equals successful storage.

The endpoint editor exposes a deliberately small subset of Prime's model definition: each model has `id` and `name` strings, `reasoning` Boolean, `input` (unique `text`/`image` values), and positive integer `contextWindow` and `maxTokens`. `api` identifies an existing Prime adapter and `authHeader` is Boolean. `headers` is the closed union `{action:"keep"}` or `{action:"replace",values:{<header-name>:<literal-string>}}`. Keep preserves existing headers within Prime; replacement requires explicit UI confirmation and an empty map means removal. A new entry with keep starts without headers. This permits endpoint editing without returning stored secrets. Optional `compat` is the closed object `{supportsDeveloperRole?:boolean,supportsReasoningEffort?:boolean}`, using Prime's existing OpenAI-compatible settings. Omitted keys preserve existing values; on a new entry Prime supplies the supported route's defaults. No arbitrary compatibility objects or per-model endpoint/header overrides in this first interface. Editing a provider entry with other unsupported advanced fields returns `unsupported_configuration` without modification.

Real custom-endpoint credentials reuse the dedicated AuthStorage entry, not a duplicate credential in models.json. A concrete existing gap is that ModelRegistry's custom-model validation currently requires `providerConfig.apiKey`, even when AuthStorage can supply request authentication. The proposed Prime-owned writer/validator extension must accept the dedicated stored credential instead. A route requiring real authentication must refuse missing credentials; a transport placeholder must never rescue that refusal.

Local Ollama is required, not an optional adapter combination. Prime must provide the explicitly selected `ollama` provider route through `openai-completions`, with an editable validated local endpoint (documented default `http://localhost:11434/v1`) and user-selected local model ID. No cloud account or user-invented key is required. Pinned Prime documents `apiKey:"ollama"` because its adapter requires a nonempty key while Ollama ignores it. Prime owns supplying that nonsecret transport placeholder, or a narrow equivalent anonymous-endpoint adaptation, through its real validation and request path. Rook neither invents nor stores it as an account credential. This behavior applies only to the explicitly selected supported Ollama route, not arbitrary missing-key providers. Preserve Prime's compatibility settings for that route, including `supportsDeveloperRole:false` and `supportsReasoningEffort:false` where needed; the editor must not reject or discard them. Configuration Save remains offline and does not establish that the server is running or the selected model is installed.

To avoid a hidden second credential route, this policy refuses models.json `apiKey` entries in the dedicated directory before fallback resolution, except Prime's exact nonsecret transport placeholder for the explicitly selected supported Ollama route. Prime must distinguish that route/value from an arbitrary credential; no environment or command resolution is permitted for the placeholder. Other entries return `unsupported_configuration` without values. Endpoint headers may not override authentication owned by the chosen adapter/AuthStorage (for example its Authorization header). Prime identifies and enforces those reserved names. Remove-key/disconnect cannot silently reveal a real endpoint-key fallback. A placeholder is neither authenticated-account evidence nor a credential to disconnect. This restriction does not apply to the agent's separately authorized tools or authoring abilities.

## 6. Wire Format

Protocol version 1 uses newline-delimited strict UTF-8 JSON on private pipes. Every message is a closed object; reject duplicate keys, unknown fields/types, malformed JSON, non-finite numbers and over-limit frames before use. A record is one JSON object followed by LF; escaped newlines inside JSON strings are not record boundaries. EOF with a partial record is a protocol failure. Stdout carries only protocol records, not banners or diagnostics.

The definitions below enumerate permitted fields; `?` means optional and is notation, not a wire key. An `operationId` is 32 lowercase hexadecimal characters assigned by Rook for this invocation, not persistent product identity. Prime-generated `requestId` is a positive, monotonically increasing integer, never reused in the invocation.

### Rook To Prime

```text
begin  = {v:1, type:"begin", operationId, operation, input}
reply  = {v:1, type:"reply", operationId, requestId, value:string}
cancel = {v:1, type:"cancel", operationId}
```

`operation` and its closed `input` are exactly the rows in section 5. Only `oauth.connect` accepts replies. A select reply is one offered choice ID, not a label or index inferred by Rook. Text/code replies are sensitive. There is no session ID, method name, arbitrary object payload or credential-directory field.

### Prime To Rook

```text
progress = {v:1, type:"progress", operationId, stage}
authorize = {v:1, type:"authorize", operationId, url, instructionCode,
             instructions?:string}
input = {v:1, type:"input", operationId, requestId, kind, label,
         secret:boolean, choices?:[{id,label}]}
result = {v:1, type:"result", operationId, outcome, persistence,
          code, data?}
```

`stage` is `loading`, `authorizing`, `awaiting_input`, `validating`, `saving` or `reading_back`. Stages describe work actually reached. `authorize` is OAuth-only, carries an HTTP(S) authorization URL without userinfo, and `instructionCode` is `open_browser`. `instructions` carries the provider's actual `onAuth.instructions` unchanged when supplied, including output-only device codes such as GitHub Copilot's code; omit it only when the provider supplies none. Rook renders it as plain text, never reconstructs it from the URL, and never substitutes an input request for output-only instructions. Treat both URL and instructions as sensitive: display only for the active user-initiated authorization, exclude from logs/evidence/caches, and clear with the operation's transient state. Rook never rewrites authorization parameters or claims to validate the remote account. Provider instructions/labels must be bounded plain text, not HTML/scripts; do not add echoed input or raw exceptions to them. Over-limit instructions refuse rather than truncating away a required code.

`input.kind` is `text`, `code` or `select`; `choices` is required only for select and IDs must be unique. At most one input request is outstanding. Prime registers it before emitting it; both service and UI bind replies to the exact operation and request. Reject unsolicited, duplicate, mismatched, late or post-cancellation replies without invoking the OAuth callback. Browser callback versus manual-input races must settle that same request only once. Cancelling clears admissibility, not ownership of cleanup. Invalid input sequencing terminates the operation with a protocol failure; never deliver it to another operation.

`result.outcome` is `completed`, `cancelled` or `failed`. `persistence` is independently `not_applicable`, `unchanged`, `saved` or `unknown`. Exactly one terminal result is permitted and no further input is accepted afterward. `code` is one of `ok`, `invalid_request`, `unsupported_configuration`, `unsupported_choice`, `authentication_failed`, `storage_failed`, `cancelled`, `deadline_exceeded`, `bounds_exceeded` or `internal_error`. Rook renders fixed safe messages; raw exception text is not protocol evidence.

`data` is absent on failure/cancel, except that persistence remains explicit. For completed mutations it is absent: the UI explicitly requests fresh status if needed. For `status`, it is the closed shape `{providers,defaults,apis}`, where providers contain `{id,name,methods,credentialType,configured,route,endpoint?,headerNames}`; methods are supported operation names for that provider, credentialType is `none`/`oauth`/`api_key`, configured is Boolean, route is `dedicated`/`local_no_account`/`none`, endpoint is a nonsecret base URL, and headerNames never includes values. A supported configured Ollama route reports `local_no_account`, `credentialType:"none"` and `configured:true`; the UI says local endpoint configured, not account authenticated. A placeholder cannot change that classification. IDs, names and header names are strings. `apis` is the list of existing supported adapter identifier strings supplied by Prime, not maintained by Rook. Defaults are `{provider:string|null,model:string|null,reasoning:string|null}`. Null means not saved, not an assertion about a future effective default. Status describes current observable configuration, not the success of an earlier operation whose result was lost.

For `models`, data is `{provider,models:[{id,name,input,reasoningLevels}],access:"unverified"}`. IDs are exact, not fuzzy selectors. Provider-level configured state comes from status; model authorization is not inferred. Unknown account/billing metadata is omitted, not invented. Unsupported configuration returns a safe failure rather than a partial success snapshot concealing an excluded source.

For `endpoint.read`, data is `{provider,entry:null|{baseUrl,api,authHeader,headerNames,models,compat}}`. Null means no dedicated override. Model objects use the editable fields defined above, with Prime's resolved defaults where a field was omitted on disk. `compat` contains the two supported compatibility keys when set or supplied by the route's defaults; it may be empty. Unknown/unsupported advanced configuration refuses instead of presenting a lossy editor; the supported Ollama compatibility fields and Prime-owned placeholder are not unsupported residue. Header names are strings; values never cross this read boundary.

## 7. Bounds And Completion

All bounds below are proposed fixed implementation requirements, not measured performance promises. Deadline clocks are monotonic, begin before spawn, include initialization and never reset on progress or user input. The service enforces the outer bound even if Prime cannot emit a result.

| Operation | Total operation deadline |
| --- | --- |
| `status`, `models`, `endpoint.read` | 20 seconds |
| Key set/remove, OAuth disconnect, endpoint/default save | 30 seconds |
| OAuth connect/reconnect, including user interaction | 600 seconds |

First input must be sent within 5 seconds of spawn. No deadline extension or automatic retry. OAuth provider internal retries must remain within the outer deadline; Rook adds none. The UI discloses expiry before starting authorization.

- Maximum incoming record: 256 KiB; combined stdin: 512 KiB and 64 records, including begin/cancel/replies.
- Maximum outgoing record: 2 MiB; combined stdout: 4 MiB and 256 records. Parse incrementally with byte limits before allocating an unbounded line. Exceeding any bound fails; never truncate a protocol result into success.
- Maximum key or authentication reply: 16 KiB UTF-8. Authorization URL: 8 KiB. Provider authorization instructions: 8 KiB UTF-8, counted within the same record/total stdout bounds. Labels: 512 bytes each. At most 32 choices per input and 16 input requests per OAuth operation.
- At most 256 providers and 64 adapter IDs in status and 512 models for a requested provider. At most 64 models and 32 headers in endpoint read/save; header values at most 8 KiB each, identifiers at most 256 bytes, base URL at most 4 KiB. Larger catalogs/configurations refuse with a bounded error, not silent omissions or automatic pagination.
- Drain stderr privately with a 64 KiB cumulative bound; do not retain or relay its raw contents. Overflow is an execution failure. Logs may retain byte counts, safe codes and exit status only, not pipe bodies, inputs, URLs or exceptions. HTTP/WebView diagnostic capture must apply the same exclusion to this settings route.

Use one additional 15-second cleanup budget after result, cancellation or operation deadline. Request cooperative cancellation only while the operation is active and the protocol is trustworthy. After a terminal result, only wait/drain, never send another operation. Allow up to 10 seconds for ordinary exit/settlement; if necessary use existing exact-child termination primitives and the remaining budget to observe exit. No process-name search, descendant surveillance, PID adoption, broad kill or daemon cleanup. Prime owns cancellation/closure of its OAuth callback listener and request work. If settlement is unobserved, report it; do not claim every descendant stopped merely because the child exited.

The service keeps two independent facts: the last valid terminal result (including persistence) and process cleanup (`exited` with code, or `unconfirmed`). A nonzero exit, malformed stream, output overflow or cleanup failure prevents a clean operation-success claim, but must not erase a previously verified persistence result:

| Observations | Customer outcome |
| --- | --- |
| Completed + saved + clean exit 0 | Configuration saved. This does not prove model access. |
| Saved result, then nonzero exit or unconfirmed cleanup | Configuration saved; configuration-process cleanup failed/unconfirmed. Do not repeat the write automatically. |
| Cancel observed before any write, confirmed unchanged | Cancelled; configuration unchanged. |
| Cancellation during persistence, saved result received | Configuration saved before cancellation completed; show cleanup separately. No rollback claim. |
| Result lost/invalid after a write could have started | Save outcome unknown; show cleanup separately. A later explicit status read reports current observable configuration only. Indistinguishable key replacement or OAuth reconnection remains unknown. |
| Exit 0 without a valid result | Protocol failure, not success; persistence unknown for a mutating operation. |

A UI/HTTP disconnect cancels the active operation; the service retains the exact child until bounded cleanup finishes. Clear transient secrets from UI/service references afterward. Observed exit does not erase an earlier internal failure. No durable operation journal or new lifecycle framework is required.

## 8. Persistence And Applicability

Prime checks initial load errors before mutation. Settings writes must complete `flush()`, inspect `drainErrors()` and verify persisted values through the real owner. During a known auth write, Prime retains the intended credential transiently and verifies the actual persisted credential against it through the storage owner: exact literal key bytes for key replacement, and the intended complete stored OAuth credential for login/reconnection. Presence/type alone is insufficient. Removal verifies absence. Surface recorded load/write/readback errors; an unavailable or mismatched readback cannot produce `saved`. Keep this comparison inside Prime without network refresh, returned secret material, public credential fingerprints or durable operation records. Do not swallow an earlier error by clearing it before deciding success. Endpoint writes await the existing schema validator and semantic validation, preserve unrelated entries, serialize using Prime's existing storage/locking conventions and read back through ModelRegistry. A memory getter is not disk evidence.

After a lost result, a later status process does not possess the prior operation's intended credential. Key A and key B can both appear as "API key configured"; an old and reconnected OAuth account can likewise be indistinguishable in the permitted status. Report the current observations and retain that uncertainty. Do not claim that status proved the replacement, automatically retry, ask for a secret merely to perform reconciliation, or add an operation journal/fingerprint to manufacture certainty. A known saved result still survives a subsequent cleanup failure as specified in section 7.

Each operation targets one configuration concern; no multi-store transaction or rollback is promised. For example, setting a key and saving an endpoint are two explicit operations with independently displayed outcomes. If endpoint validation needs a key first, explain that dependency. Do not erase a successfully saved key when a later endpoint save fails.

Saved model/reasoning defaults apply to future conversations only. Creation continues to distinguish explicit requested choices from defaults. Unsupported explicit choices must not be represented as accepted unchanged if Prime clamps them: report its actual effective setting on the session path. Reopen supplies no new model/reasoning overrides. No mid-conversation setting change is introduced.

Credentials and endpoints are shared configuration. Their change/removal can affect subsequent requests or refreshes from already open conversations; another process may still hold previous values. Display that fact before Save/Disconnect. Do not promise immediate revocation, coordinated hot reload, atomic switching of all sessions or future-only credential effects.

Effective settings must be supplied by Prime from the live session's actual state through the existing official ACP session response/update boundary. The minimal addition is a read-only setting summary (actual provider/model/reasoning, with unavailable fields explicitly unknown), not a setter or separate query process. Use ACP-supported fields where compatible with the pinned SDK; do not implement a private transport if schema support needs a reviewed compatibility change. The configuration snapshot cannot establish an open conversation's state. The panel labels saved defaults, requested initial choices and effective session values distinctly.

## 9. Source Anchors And Explicit Gaps

Paths below are relative to the source checkout identified in section 1, not claims that the proposed entrypoint exists.

| Owner | Source anchors | Gap this specification addresses |
| --- | --- | --- |
| Early CLI dispatch | Prime `packages/coding-agent/src/cli-main.ts`, `src/main.ts`, `src/cli/public-command.ts` | New short-lived configuration branch before worker/daemon/agent initialization. Current `config` means package resources. |
| Auth and interpretation | Prime `src/core/auth-storage.ts`, `resolve-config-value.ts`, `prime-inference-auth.ts`, `modes/interactive/auth-flows.ts` under the coding-agent package | Expose existing auth callbacks safely; literal policy across real consumers; disable unrelated authority; verify persistence. Interactive UI is not the new entrypoint. |
| Defaults/endpoints/models | Prime `src/core/settings-manager.ts`, `model-registry.ts`, `model-resolver.ts`, `sdk.ts`; `packages/ai/src/models.ts` | Finite validated endpoint writer, literal values, awaited storage errors; no second catalog. Stored custom-provider auth admission needs the explicit narrow extension in section 5. |
| Effective session | Prime `src/modes/acp/acp-mode.ts`; Rook `mcp_server/src/rook/agent/chat/acp_process.py` | Current ACP initialization/new-session responses do not provide the required actual-settings report. Add through official ACP, not configuration stdio. |
| Presentation/service | Rook `src/Rook/UI/Chat/RookChatPanel.cs`, `AgentChatTab.cs`, `AgentChatClient.cs`; `mcp_server/src/rook/agent/chat/server.py`, `service_main.py`, `prime_runtime.py` | Settings presentation/authenticated service route, same deliberate directory/policy on launch, no secret transcript or durable Rook store. Preserve existing conversation owners. |

Historical authentication evidence remains in `artifacts/task12-slice-a-preflight/slice-c-login-handoff-review.md` and `developer-oauth-validation-review.md` (local evidence, not execution instructions). Do not reopen that private directory to implement this specification. No existing absence/presence assertion proves current account access.

## 10. Required Causal Proof And Review Stop

Future implementation must use focused tests against real owners with synthetic credentials, controlled storage and network/process tripwires. Fakes replace external providers, not persistence, startup dispatch or actual request construction.

- Execute the real configuration CLI with no model/account and prove no daemon, agent, MCP, kernel, project migration/resource or inference boundary is reached; malformed invocation cannot select interactive mode.
- Drive actual OAuth callbacks through one correlated input at a time; wrong operation/request, duplicate, late, cancelled and browser/manual races cannot deliver input twice or to another operation. Preserve GitHub Copilot-style synthetic device instructions from the real callback through `authorize.instructions` to plain-text presentation, without an input request or retained sensitive output; over-limit instructions refuse. UI disposal retains cleanup ownership.
- Save a synthetic key equal to an existing environment-variable name; reload and construct an actual provider request using those literal bytes. Poison command execution and prove `!` fields and stored command-backed entries refuse before access. Exercise header/auth-source paths too.
- Poison external Prime CLI auth and ambient provider/model/endpoint overrides while retaining required network/Windows inputs. Config and ACP consumers must select the same dedicated sources without changing ordinary Prime behavior outside the policy.
- Inject AuthStorage load/write failures and SettingsManager queued-write failures. Successful setters alone must not pass. With key A already stored, replacement by B must verify B, not just key presence; likewise test intended OAuth credential readback. A lost replacement result followed by identical nonsecret status must remain unknown. Test real endpoint schema readiness, stored-auth validation and readback; key removal cannot expose a hidden real endpoint credential fallback.
- Exercise the supported Ollama configuration through Prime's real validator, reload and OpenAI-compatible request builder with a local-only synthetic server boundary: no cloud account, user-entered key or ambient credential; Prime supplies its required transport placeholder/adaptation and preserves both compatibility flags in actual request construction. Status must not report the placeholder as an authenticated account. A cloud route missing a real key must still refuse, and endpoint editing must preserve the supported compatibility fields. This proposed coverage is not authorization to run a model or install Ollama now.
- Test every message/byte/time boundary, exit 0 without result, saved-then-hung/nonzero exit, result loss after persistence, cancellation before/during write and cleanup timeout. Assert separate persistence and cleanup outcomes without secret evidence.
- Verify future defaults do not mutate current/reopened settings, requested versus effective values remain distinct, and unsupported model/reasoning choices are truthful. No Save or status operation may contact inference.

This document is the review deliverable. No new harness, runbook, implementation plan, configuration action or runtime qualification is created now. A reviewed Prime extension and later runtime adoption will need their existing build/review boundaries; this specification does not authorize changing the current pinned installation or rerunning accepted A+B/C.
