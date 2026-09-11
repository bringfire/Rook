# RookChat Configuration Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task after authorization. Steps use checkbox (`- [ ]`) syntax for tracking. This document is proposed for independent plan review, not execution authorization.

**Goal:** Provide first-use account, local-endpoint and model/default configuration in RookChat through Prime's approved finite configuration interface.

**Architecture:** The existing authenticated Python chat service owns one short-lived configuration child; Prime interprets, validates and persists its configuration. The managed panel presents the results. Actual conversation settings travel through the existing official ACP session boundary; conversation ownership and inference remain unchanged.

**Tech Stack:** Existing TypeScript/Node/Bun Prime sources, official ACP SDKs, Python asyncio/aiohttp, C# Eto/System.Text.Json, Vitest, pytest and xUnit. No additional dependency, resident service, registry or generic protocol framework.

**Spec:** [Approved configuration specification](../specs/2026-09-10-rookchat-configuration-interface-design.md), committed alone at `95aa8db5964fced88e198f0530cd7bb58396488b`. Read it with this plan; its closed wire schemas and bounds are normative, not examples to reinterpret.

## Global Constraints

- Prime is the only harness. Rook presents configuration; Prime owns interpretation, validation, persistence and application.
- Proposed command: `<verified-runtime>/pi.exe configuration --stdio --configuration-policy rookchat`. The current installed runtime does not support it.
- Dedicated directory: `PRIME_AGENT_CODING_AGENT_DIR=<Rook persistent-data root>/prime-config`, identical for configuration and supported ACP launches. No ambient account/endpoint/model authority or credential migration.
- Only these operations: `status`, `models`, `oauth.connect`, `oauth.disconnect`, `apiKey.set`, `apiKey.remove`, `endpoint.read`, `endpoint.save`, `defaults.save`.
- Ordinary fields are literal; no command-backed or environment-resolved credentials/headers. Local Ollama must work without a cloud account or user-invented key. Prime owns its nonsecret transport placeholder and supported compatibility flags.
- Status, catalog and Save do not refresh OAuth, fetch catalogs, probe endpoints or contact inference. OAuth connect has its explicit authentication network boundary; conversation refresh remains Prime-owned.
- Preserve `authorize.instructions`, correlated replies, exact internal credential readback and separate persistence/cleanup outcomes. Nonsecret status cannot establish an indistinguishable lost replacement result.
- Saved defaults affect future conversations; reopen sends no overrides. Shared credentials/endpoints are not future-only changes. No live setting mutation command is added.
- Use the spec's exact limits: read operations 20 s, writes/disconnect 30 s, OAuth 600 s; first begin within 5 s; one additional 15 s cleanup budget (10 s cooperative, remaining time exact-child termination/exit observation).
- Input record/total/count: 256 KiB / 512 KiB / 64. Output: 2 MiB / 4 MiB / 256. Stderr: 64 KiB, discard contents. Key/reply: 16 KiB; authorization URL/instructions: 8 KiB each. Preserve all collection/string limits in spec section 7.
- Preserve existing ACP, claim, mutation authority, cancellation and deployment blockers. No private conversation transport, automatic replay, new manifests, broad cleanup or process inspection.
- Leave the existing knowledge modification untouched and unstaged. Preserve accepted A+B/C and all failed evidence; no automatic requalification or live login.

## Workspaces And Review Stages

Baseline Rook HEAD is the specification commit above. Baseline Prime is `b71badc503f650cd7c10c4acd1206a8406aa0a0b`. The installed runtime remains `4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579` until separately approved adoption.

The installed developer service imports `mcp_server/src` from `rookchat-prime-acp-reset`. Therefore implementation must not edit that checkout, even without deployment. When Stage A/B execution is authorized, use the existing git-worktree workflow to create separate implementation worktrees from these exact reviewed states:

```powershell
$RookRoot = 'C:/UDEV/Rook/.worktrees/rookchat-configuration'
$PrimeRoot = 'D:/prime-agent/.worktrees/rookchat-configuration'
$Node = 'C:/Program Files/nodejs/node.exe'
$Python = 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe'
$NuGetRoot = 'C:/Users/bring/.nuget/packages/'
```

The worktree paths are proposed destinations, not directories to create during planning. If already occupied, stop and ask for a different destination rather than reuse unknown work. The Python path is an existing interpreter, not permission to modify its environment or import the developer-serving source; the command-scoped source binding below selects the isolated implementation. The current managed assets identify the NuGet root above and a Visual Studio fallback folder; revalidate required packages/adapter rather than treating that historical assets file as the new checkout's assets. The Rook implementation starts from the subsequently reviewed plan head descended from the specification commit; do not bypass the reviewed plan or copy the dirty knowledge note. Prime starts from its baseline above. Keep one concern per commit and report each parent; do not pre-invent future commit hashes.

| Stage | Tasks and delivered proof | Mandatory stop |
| --- | --- | --- |
| A: Prime interface | 1-4: authority, storage operations, short-lived protocol and actual-session reporting; focused offline tests | Independent Prime implementation review before Rook integration or real build |
| B: Rook integration | 5-7: exact-child service path, settings UI, live-state presentation; deterministic cross-boundary tests | Independent integration review before runtime adoption |
| C: Runtime adoption preparation | 8: bind accepted source/runtime/build/deploy inputs using existing workflows | Review the concrete adoption package, then obtain separate execution authorization |

One approved stage is not permission to cross the next stop. Model-free test iteration is ordinary development; record meaningful RED/GREEN evidence, not a new sealed qualification generation per test run.

### Execution Environment Admission (Before Task 1, Not Now)

- [ ] Establish isolated worktrees and verify their exact bases. Record current worktree status without reading the knowledge note or credentials.
- [ ] Bind existing Node/Python/.NET tools and worktree-local Prime dependencies from its unchanged lock. Do not resolve Vitest, Vite, tsx or workspace packages through another Prime checkout. Where restoration is necessary, obtain scoped dependency-preparation approval first; use ordinary lock-based restoration, no copied node_modules, package upgrades, postinstall helper downloads or broad build. Package-local Vitest aliases point workspace imports at source; build only any actually required ignored outputs after explicit approval.
- [ ] For Rook tests, use an existing approved Python interpreter with the new worktree's `mcp_server/src` on the command-scoped import path, and verify imported `rook` resolves there. Bind existing managed NuGet assets/adapter and Rhino 8 assemblies explicitly. A missing test dependency is a preparation stop, not a zero-test pass or permission to restore online.
- [ ] Use short test-local roots, synthetic credentials and local-only fixtures. Do not run legacy network-capable package-manager collections, `npm run test:ci`, kernel bootstrap CLI, product CLI outside the configuration-only entrypoint, or full Prime builds.

## Consumer-First Operation Map

All nine actions use one managed `AgentChatClient.RunConfigurationAsync` path and one authenticated `POST /agent/chat/configuration` stream. Reply and cancellation use the two control routes in Task 5. This is one operation per child, not a persistent configuration session.

`D` below means the deliberately resolved `data_root/prime-config`. Files named below belong to Prime, never a Rook serializer. Test names are required causal cases in the named task's focused file, not claims of already passing tests.

| UI action / operation | Exact Prime consumer and source | Persistence/result proof | Causal case |
| --- | --- | --- | --- |
| Open settings / `status` | AuthStorage.getAuthStatus, ModelRegistry.getProviderAuthStatus, SettingsManager getters; D plus compiled catalog | No write-success claim; presence/route/defaults only, unknown access | `status_does_not_refresh_or_resolve_commands` (2, 5) |
| Choose provider / `models` | ModelRegistry.getAll filtered by exact provider; pi-ai reasoning capability helpers | Catalog only; access unverified, no dynamic authorization refresh | `models_are_catalog_not_account_access` (2, 6) |
| Connect/reconnect / `oauth.connect` | Registered provider callbacks through AuthStorage.login; D/auth.json | Intended complete credential compared to persisted readback inside Prime; safe terminal result | `oauth_reconnect_checks_intended_credential`, `device_instructions_survive` (2, 3, 6) |
| Disconnect / `oauth.disconnect` | AuthStorage.logout using only D, then verified absence | Removal, not remote revocation or other-process invalidation | `disconnect_does_not_touch_external_prime_cli` (2) |
| Replace key / `apiKey.set` | AuthStorage.set; D/auth.json | Exact intended literal bytes, not presence/type | `key_b_must_replace_key_a` (2, 5) |
| Remove key / `apiKey.remove` | AuthStorage.removeVerified; D/auth.json | Absent, type mismatch refuses; no real models.json fallback | `key_remove_cannot_reveal_fallback` (1, 2) |
| Edit endpoint / `endpoint.read` | ModelRegistry's owned D/models.json projection | Safe editable values, header names only; unsupported fields refuse | `endpoint_read_never_returns_header_secrets` (2, 6) |
| Save endpoint/Ollama / `endpoint.save` | Same ModelRegistry schema/semantic validators and new narrow disk writer; D/models.json | Validate, lock/merge, write, reload; preserve compatibility/headers/unrelated entries | `ollama_reaches_real_request_builder_without_account` (2) |
| Save future defaults / `defaults.save` | Exact model lookup, supported reasoning levels, SettingsManager setters/flush/drainErrors/readback; D/settings.json | Actual persisted defaults, no inference or session setter | `defaults_flush_failure_is_not_saved` (2, 7) |

## File And Interface Map

Paths in Prime tasks are relative to `$PrimeRoot`; Rook tasks to `$RookRoot`. Existing files below were located in the baseline. New files are explicitly identified. Do not restructure neighboring modules. If a new production owner is required outside a task's scope, stop for a bounded scope review rather than silently expanding.

### Task 1: Prime Configuration Authority At Real Consumers

**Modify (Prime):** `packages/coding-agent/src/cli/args.ts`, `src/main.ts`, `src/core/auth-storage.ts`, `src/core/model-registry.ts`, `src/core/resolve-config-value.ts`, `src/core/sdk.ts` (the latter paths are within the coding-agent package).

**Create (Prime):** `packages/coding-agent/src/core/configuration-policy.ts`; `packages/coding-agent/test/configuration-policy.test.ts`.

**Neighbor tests:** `args.test.ts`, `auth-storage.test.ts`, `resolve-config-value.test.ts`, `model-registry.test.ts`, `no-approve-startup-composition.test.ts` in the same test directory; select implicated hermetic cases, not unrelated suites.

**Interfaces:** Introduce the finite `ConfigurationPolicy = "standard" | "rookchat"`; add an optional policy to existing AuthStorage options and ModelRegistry construction, defaulting to standard. Standard is the absent-selector behavior, not another exposed CLI choice. The CLI parses the exact approved flag before source resolution. Do not infer it from an environment alias. Reuse the existing first-standalone-`--` split; reject duplicate/malformed policy selectors before startup.

```typescript
export type ConfigurationPolicy = "standard" | "rookchat";
export function resolveLiteralConfigurationValue(value: string): string;
// Reject NUL and command-backed syntax; return accepted bytes unchanged.
// This function does not inspect process.env or execute a command.
```

- [ ] Add RED cases in `configuration-policy.test.ts` using real AuthStorage/ModelRegistry in temporary directories. Plant different synthetic values in auth.json, external Prime CLI config and environment. Poison command execution. Assert Rook policy resolves the dedicated literal even when it equals an environment-variable name; standard policy retains existing behavior. Cover auth-source tokens, headers, fallback, missing credentials and stale/refresh paths, not only the public resolver.
- [ ] Implement the policy at candidate selection and actual request-auth/header resolution. Set `usePrimeCliConfig:false` for this policy and bypass environment/command fallback in every relevant auth candidate/token path. Preserve normal OAuth refresh and private Prime-inference authorization under the selected dedicated source. Missing real auth returns failure before `sdk.ts` calls `streamSimple`; it must not pass an absent key into a provider that then consults environment.
- [ ] Audit the actual downstream adapter used for each offered method. `openai-completions`/Responses explicitly prefer a provided key; Vertex and Bedrock have additional ADC/profile/project/region routes. Methods that cannot be represented under this finite dedicated configuration must be reported unsupported, not silently fall through to ambient credentials. Do not implement enterprise credential workflows or patch all provider SDKs. If a required supported method cannot be isolated at the existing Prime consumer, stop with the exact caller/consumer gap for review. Ollama and openai-codex cannot be deferred by this check.
- [ ] Propagate the same parsed policy through `main.ts`'s AuthStorage creation and session services into the actual SDK registry; preserve project denial, explicit skills and existing launch behavior. Do not construct a second config tree in Rook.
- [ ] Run focused RED/GREEN and selected neighbors using the command convention below. Commit this concern in Prime only after named assertions are green.

Representative real-owner assertion (within the test's fresh temporary fixture; `AuthStorage` is production):

```typescript
const storage = AuthStorage.create(join(dir, "auth.json"), {
  usePrimeCliConfig: false, configurationPolicy: "rookchat",
});
storage.set("openai", { type: "api_key", key: "SYNTHETIC_KEY_NAME" });
process.env.SYNTHETIC_KEY_NAME = "not-the-key";
expect(await storage.getApiKey("openai")).toBe("SYNTHETIC_KEY_NAME");
// Restore the synthetic environment entry in finally/afterEach.
```

### Task 2: Prime-Owned Operations And Verified Persistence

**Modify (Prime):** `packages/coding-agent/src/core/auth-storage.ts`, `model-registry.ts`, `settings-manager.ts` in that directory.

**Create (Prime):** `packages/coding-agent/src/core/configuration-operations.ts`; `packages/coding-agent/test/configuration-operations.test.ts`.

**Read/reuse:** `packages/ai/src/api-registry.ts` (`getApiProviders`), `packages/ai/src/models.ts`, `packages/coding-agent/src/modes/interactive/auth-flows.ts`, `packages/ai/src/utils/oauth/github-copilot.ts`, `packages/coding-agent/docs/models.md`. Do not move interactive UI or duplicate provider OAuth implementations.

**Interfaces:** Define `ConfigurationBegin`, `ConfigurationEvent`, `ConfigurationResult` as the spec's closed unions, exported from `configuration-operations.ts`. `executeConfigurationOperation(begin, owners, interaction, signal): Promise<ConfigurationResult>` accepts existing real AuthStorage, SettingsManager and ModelRegistry owners for the same D. `interaction` has `emit(event):Promise<void>` and `requestInput(input):Promise<string>`; Task 3 supplies the correlated callbacks. It is not an arbitrary method registry. Use an exhaustive switch over the nine operations.

Add narrow owner methods `AuthStorage.verifyPersistedCredential(provider, intended): void` and `ModelRegistry.readConfigurationEndpoint(provider)` / `saveConfigurationEndpoint(input): Promise<void>`. The first returns no credential/fingerprint; verification occurs under the existing storage owner. Endpoint return/input types are exactly the spec's read/save shapes. Do not call `registerProvider` and declare a disk save: it registers in memory.

- [ ] Add RED tests for all operation-map cases. Use `AuthStorage.fromStorage` with a controlled backend that retains A despite a requested B write; a memory getter must not make the operation pass. Use the real file backend for positive readback. OAuth callbacks use a registered synthetic provider whose complete credential differs from the old one; external fetch is a throwing boundary.
- [ ] For known auth writes, retain the intended credential transiently inside AuthStorage's login/set path and compare the persisted value, not a subsequent mutated in-memory getter. Check initial/recorded storage errors. Type-mismatched removal refuses. Login remains provider.login -> AuthStorage persistence, with cancellation passed through. Keep disconnect's existing logout behavior and verify absence without enabling external Prime CLI auth.
- [ ] For status/models, use loaded catalog and nonsecret auth status only. Derive API choices from the existing API registry, not a Rook list. Do not call `refreshAvailableModels`, executable-model network discovery or OAuth refresh. Include the configured local Ollama route and its explicit no-account classification. Provide exact reasoning levels, not the panel's current universal list.
- [ ] Implement endpoint read/save inside ModelRegistry using its existing models.json schema and semantic validator after schema compilation is ready. Follow FileSettingsStorage's existing proper-lockfile/temporary-write/rename pattern locally for this file, including first creation and bounded cleanup. Re-read under the lock before merging; preserve unrelated entries and headers when `keep`. Verify through a fresh load. No new storage manager, whole-file editor or inferred migration.
- [ ] Preserve exact literal/header policy and refuse unsupported fields. Accept stored AuthStorage credentials for custom models. For explicit provider `ollama` with the supported OpenAI-completions route, Prime supplies the documented literal transport placeholder, not a user credential. Retain both approved compatibility Booleans through save/read/reload into actual adapter request construction. Real-auth routes still refuse missing credentials. No blanket placeholder exception or environment fallback.
- [ ] For defaults, resolve exact provider/model from the registry, validate supported reasoning, then call SettingsManager setters, await flush, inspect errors and read disk through a fresh owner. Treat partial/failed persistence truthfully; do not roll back another successfully saved concern. Do not use live `setModel`/`setThinkingLevel` methods for a future default.
- [ ] Keep directory creation within Prime and use existing private storage helpers. Test fresh/missing/unsafe directories and read/write failures with nonsecret fixtures. On Windows, do not claim POSIX mode/chmod establishes a private ACL: inspect the inherited directory protection in the future adoption admission before any real credential write. If that cannot meet the spec without a new ACL implementation, stop for that narrow review; no broad permission repair or real login is authorized by these tests.
- [ ] Run named operation tests and implicated settings/auth/model neighbors, then commit this concern. Retain a no-network result and intended-versus-observed persistence assertions without secret test output.

Concrete negative-control pattern for `verifyPersistedCredential`:

```typescript
let retained = JSON.stringify({ openai: { type: "api_key", key: "A" } });
const backend = {
  withLock: (fn: (s: string) => { result: unknown; next?: string }) => fn(retained).result,
  withLockAsync: async (fn: (s: string) => Promise<{ result: unknown; next?: string }>) =>
    (await fn(retained)).result,
}; // Deliberately ignores requested writes; test-local fault, not fake AuthStorage.
const storage = AuthStorage.fromStorage(backend as AuthStorageBackend,
  { configurationPolicy: "rookchat", usePrimeCliConfig: false });
storage.set("openai", { type: "api_key", key: "B" });
expect(() => storage.verifyPersistedCredential("openai", { type: "api_key", key: "B" })).toThrow();
```

### Task 3: Finite Stdio Command, Correlation And Bounded Exit

**Modify (Prime):** `packages/coding-agent/src/cli-main.ts`.

**Create (Prime):** `packages/coding-agent/src/cli/configuration-args.ts`, `configuration-command.ts` in that directory; `packages/coding-agent/test/configuration-command.test.ts`.

**Interfaces:** `classifyConfigurationCommand(args: readonly string[]): "configuration" | "other"` in the dependency-free `configuration-args.ts` throws on malformed configuration invocation. `runConfigurationCommand(input: Readable, output: Writable): Promise<number>` in `configuration-command.ts` reads the approved operation, constructs Task 2's owners and executes once. Production binds real pipes; tests supply streams and mock external provider callbacks only. Statically import only the pure classifier in cli-main; dynamically import the command implementation before owned-worker/daemon/main initialization. The configuration entrypoint cannot import agent startup for its side effects.

**Networking handoff:** The early return bypasses ordinary cli-main's `EnvHttpProxyAgent` initialization. Inside `runConfigurationCommand`, after admitting begin and before invoking any OAuth provider, dynamically import the existing `undici` dependency and install the same `new EnvHttpProxyAgent({ bodyTimeout: 0, headersTimeout: 0 })` with `setGlobalDispatcher`. Capture the previous dispatcher with `getGlobalDispatcher` before replacement. This must precede provider requests using global `fetch`, including OpenAI's token exchange; merely preserving proxy environment variables is insufficient. Keep ordinary cli-main's existing initialization unchanged. Do not import main/agent/daemon/kernel/MCP to obtain networking, add another proxy implementation, or disable TLS verification. The existing command deadline bounds requests despite those dispatcher timeout values.

- [ ] Add tests for real CLI selection, not merely direct function imports. Guard all agent/daemon/kernel/MCP/tracing/project-migration boundaries; only the dedicated configuration child is permitted. Unknown/repeated command flags and incomplete stdio forms must refuse without falling through to Prime interactive mode. Preserve ordinary `pi config` and ACP behavior.
- [ ] Add local-only networking RED/GREEN cases in `configuration-command.test.ts` through the actual command initialization and AuthStorage.login. Register a synthetic OAuth provider whose login performs real global `fetch` with a synthetic grant body to a bounded loopback token endpoint and returns its synthetic credential response. Use a test-local loopback proxy with an exact request/CONNECT allowlist; poison non-loopback connection/DNS attempts and unexpected destinations. With explicit `HTTP_PROXY`/`HTTPS_PROXY` pointing to that proxy and all uppercase/lowercase bypass variables cleared, require the expected proxy contact and exact endpoint request/response. In a separate case set `NO_PROXY` for the loopback endpoint, require zero proxy contacts and the same successful direct exchange. Isolate/restore all proxy variables so ambient settings cannot satisfy either case. Do not mock global fetch, EnvHttpProxyAgent, its dispatch method or the command's networking initialization; a mocked OAuth callback returning credentials without a request is not this proof. Removing initialization must make the routing case fail. These loopback HTTP controls prove dispatcher routing/bypass, not public-provider TLS or real OAuth access; they do not justify weakening certificate checks.
- [ ] Implement bounded strict UTF-8 NDJSON framing. Reuse existing parsing utilities if they reject duplicate keys; otherwise keep the duplicate-key check local to this finite codec, before JSON.parse loses them. Do not accept malformed Unicode, unknown object fields or excess records. Implement exactly the spec's result/authorize/input/progress shapes, including sensitive instructions.
- [ ] Keep one outstanding `{operationId,requestId,resolve,reject}` callback; consume it atomically on a matching reply, invalidate on cancel and terminal. Forward output-only device instructions unchanged rather than creating an input request. Reject duplicate/late/unsolicited replies; browser/manual races settle once. No prompt UI or persistent interaction state in Prime.
- [ ] Route incidental stdout away from the protocol with the existing `output-guard.ts` primitives where appropriate, but never forward raw exceptions or provider secrets to stderr. Bound both pipes and stop on overflow. Use existing provider AbortSignal support and close owned callback resources. Operation outcome is emitted only once; exit status does not replace the result.
- [ ] Own the installed EnvHttpProxyAgent in the same command try/finally as provider work, including partial startup. On completion/cancellation/failure, stop or abort owned requests, close their response bodies and restore the prior global dispatcher; close only the dispatcher this command created, not its predecessor. Await its close within the remaining existing cleanup budget, then use its destroy operation if necessary and observe settlement within that same budget. Do not add an unbounded `await close()`, a second cleanup allowance or background teardown. A saved result remains saved if networking cleanup fails, with failed/unconfirmed cleanup reported separately. The local networking tests must cover success, cancellation and failed exchange, restore globals even on assertion failure, and close all exact fixture sockets/listeners within bounded cleanup. Limit each local exchange to 5 seconds and request/response bodies to 4 KiB; no retries, public contact or retained authentication payloads.
- [ ] Test the real command with in-memory streams, byte-by-byte chunking, newline splits, invalid Unicode/duplicates, all per-field/total ceilings, saved-then-late-error, cancellation races and bounded shutdown. For the executable selection test, invoke `packages/coding-agent/src/cli.ts` through the worktree-local tsx loader only after its module origins are verified; provide the exact configuration arguments and synthetic stdin. Prohibit unrelated subprocesses and all external requests. No compiled pi.exe launch or kernel test.
- [ ] Commit the command concern with named RED/GREEN and observed fixture-child/thread settlement.

Implementation control flow to preserve (not a second dispatcher):

```typescript
import { classifyConfigurationCommand } from "./cli/configuration-args.js";
// Inside runCli, before existing startup side effects:
const args = process.argv.slice(2);
if (classifyConfigurationCommand(args) === "configuration") {
  const { runConfigurationCommand } = await import("./cli/configuration-command.js");
  // The command installs/owns the existing proxy-aware dispatcher before OAuth,
  // and settles it inside the command's existing bounded cleanup.
  process.exitCode = await runConfigurationCommand(process.stdin, process.stdout);
  return;
}
// Existing owned-worker and daemon/agent startup follows, unchanged.
```

### Task 4: Actual Effective Settings Through ACP

**Modify (Prime):** `packages/coding-agent/src/modes/acp/acp-mode.ts`, `acp-meta.ts` in the same directory.

**Create (Prime):** `packages/coding-agent/test/acp-effective-settings.test.ts`.

**Read/reuse:** `modes/agent-connection/types.ts`, `in-process-agent-connection.ts`, `acp-events.ts`. Do not change AgentConnection's transport or add Rook access to it.

**Interface:** Extend existing namespaced ACP `_meta` with `effectiveSettings:{provider:string|null,model:string|null,reasoning:string|null}` in `session/new` and `session_info_update`. Read `connection.getState()` for the actual selected/clamped settings. The existing `primeAgentMeta` namespace, SDK `_meta` support and `AcpUpdateProducer` carry it; no new request, config setter or advertised session-switch capability. This avoids presenting read-only data as editable configOptions.

- [ ] Exercise real `runAcpModeWithConnection` with the existing in-memory ACP stream fixture and controlled runtime state. Saved default A, requested B, effective C must report C. Unknown state reports null values, never a saved-default guess. Test startup/reopen and a genuine state change during a prompt.
- [ ] Merge metadata with cwd and existing fields; preserve the existing session/new response gate and ordering. Observe relevant session events (including `thinking_level_changed`) through the existing subscription and emit a fresh actual-state summary when needed; report a refreshed summary at prompt settlement as well. Do not emit a tool card or mutate settings. A failed state read must not become a false configured value.
- [ ] Test metadata using the actual JS SDK serializer; add compatibility coverage that the pinned Python NewSessionResponse/SessionInfoUpdate schema retains this existing `_meta` extension in Stage B. Do not upgrade SDK dependencies or implement private RPC.
- [ ] Run the focused gate, review Tasks 1-4 together for default Prime compatibility, commit this concern, then stop at **Stage A review**. No real Prime build or Rook integration yet.

## Stage B: Rook Integration After Stage A Approval

### Task 5: Existing Service, One Configuration Child

**Create (Rook):** `mcp_server/src/rook/agent/chat/configuration_protocol.py`, `configuration_process.py`, `configuration_http.py`; `mcp_server/tests/test_chat_configuration.py`; `mcp_server/tests/fixtures/fake_prime_configuration.py` (synthetic process behavior only).

**Modify (Rook):** `mcp_server/src/rook/agent/chat/prime_runtime.py`, `service_main.py`, `server.py`; `mcp_server/tests/test_chat_prime_runtime.py`, `test_chat_server.py`.

**Interfaces:** `configuration_protocol.py` validates only the spec's closed messages and exposes `ConfigurationBegin`, `ConfigurationResult` and safe errors. `PrimeConfigurationOperation` in `configuration_process.py` has `run(emit) -> ConfigurationSettlement`, `reply(operation_id,request_id,value)` and `cancel(operation_id)`; it holds one exact process and one outstanding input. `ConfigurationSettlement` keeps `result:ConfigurationResult|None`, `exit_code:int|None`, `cleanup:"exited"|"unconfirmed"` and `failure_code:str|None` separately. No queue of operations, durable record or general process supervisor.

The HTTP routes are transport plumbing for the approved operation set, not additional Prime operations:

```text
POST /agent/chat/configuration                 body: the closed begin message; streamed events
POST /agent/chat/configuration/reply           body: the closed reply message; 204 on admission
POST /agent/chat/configuration/cancel          body: the closed cancel message; 204 on admission
```

Reuse `cors_and_session_middleware`, nonce and existing service discovery. One app-local active slot; busy returns 409 before spawn. Wrong operation/request returns a fixed safe error. Stream Prime records, then one HTTP-only `configuration_settled` row containing the four settlement fields above. A result row means Prime reported a result, not that cleanup has completed. Final client acceptance requires settlement. All HTTP buffers are bounded; no caching or raw body/error logging. Use `Cache-Control: no-store` on configuration responses.

- [ ] Add RED tests through `create_chat_app` with real nonce/origin admission. Guard conversation creation, MCP and prompt methods so configuration cannot enter them. Test busy before spawn, stale replies, unauthorized access, stream disconnect and app shutdown while OAuth input is pending.
- [ ] Add `build_configuration_argv(contract)` in `prime_runtime.py` using the exact command and existing Windows argv validation. Use `load_and_verify_runtime`/InstalledRuntimeCatalog, not PATH lookup. Derive configuration path from existing resolved `data_root`; override case-insensitive ambient agent-directory duplicates for the supported configuration path. No secret in argv/environment. Use existing environment construction for Windows/proxy/TLS behavior without another scrub framework.
- [ ] Add an explicit code-level supported-Prime-commit set for configuration version 1, checked against the already verified `compatibility_patch_commit`. Initially empty in production until Stage C binds the reviewed final Prime head. Tests supply synthetic supported contracts. This is a finite launch compatibility check, not a new manifest or discovery probe: never launch the old installed binary with an unknown command to ask if it supports configuration. Health may report `configurationAvailable:false` while ordinary current conversations remain available.
- [ ] Spawn using existing asyncio subprocess primitives (`shell=False`, Windows hidden-window flags); drain stdout and stderr concurrently with spec bounds. Hold the monotonic operation deadline and single cleanup budget across cancellation and pipe errors. Preserve a valid saved result even if later cleanup fails. Do not call ACP owner.retire for this non-ACP child. An unconfirmed owner remains reported; do not free the active slot to overlap a new operation while settlement is uncertain.
- [ ] Implement HTTP handlers in `configuration_http.py`, register in `server.py`, construct the service dependency in `service_main.py`, and join its cleanup in the existing app shutdown hook. Do not route exceptions through `_exception_response` when its exception text could expose configuration values; fixed codes only. UI disconnect schedules cancellation but must not cancel/drop the cleanup task itself. No changes to chat transcripts, PresentationCache or discovery state.
- [ ] Run causal real-subprocess tests using only `fake_prime_configuration.py`: emit saved then hang, omit result and exit 0, exceed bounds, send invalid JSON, return instructions, race reply/cancel. Synthetic fake has no network imports or real authentication; real production process owner supplies lifetime behavior. Inspect safe final HTTP settlement, exact exit observation and absence of synthetic secret bytes from captured logs.
- [ ] Run implicated existing HTTP/runtime tests, then commit the service concern. No installed configuration or service restart.

Representative settlement assertion in `test_chat_configuration.py` (test fixture starts the production owner against the synthetic child):

```python
assert settlement.result.persistence == "saved"
assert settlement.failure_code is not None  # child failed after reporting save
assert settlement.result.outcome == "completed"
# The test must not replace this with result=None or persistence="unknown".
```

### Task 6: RookChat Settings Presentation And HTTP Consumer

**Modify (Rook):** `src/Rook/UI/Chat/AgentChatClient.cs`, `RookChatPanel.cs`, `AgentChatTab.cs`, `ChatServiceManager.cs` (only the health DTO's configuration-availability field).

**Create (Rook):** `src/Rook/UI/Chat/AgentChatClient.Configuration.cs`, `RookChatConfigurationDialog.cs`; `src/Rook.Tests/UI/Chat/RookChatConfigurationTests.cs`.

**Neighbor tests:** `RookChatPanelTests.cs`, `AgentChatClientParseTests.cs`, `AgentChatImageAdmissionTests.cs`, `AgentChatProgressTests.cs`, `ConversationCloseCoordinatorTests.cs`, `ChatServiceManagerTests.cs`.

**Interfaces:** Make AgentChatClient partial solely to share its existing authenticated HttpClient/base-URI helpers. Define the configuration DTOs and these methods in its configuration partial; no new client transport abstraction:

```csharp
Task<ConfigurationSettlement> RunConfigurationAsync(
    ConfigurationBegin begin, Func<ConfigurationEvent, Task> onEvent, CancellationToken ct);
Task ReplyConfigurationAsync(string operationId, int requestId, string value, CancellationToken ct);
Task CancelConfigurationAsync(string operationId, CancellationToken ct);
```

`ConfigurationBegin/Event/Settlement` are the spec/Task 5 shapes, with typed closed parsing and bounded strings. Create an Eto settings dialog using this client, not chat HTML/transcript rendering. Native password fields hold credentials transiently; provider instructions are plain text and clear on close. Reuse the production UI-queue pattern and synchronization guards; do not invoke synchronous WebView scripts from callbacks.

- [ ] Add RED tests using AgentChatClient's existing fake HttpMessageHandler seam and actual new parser/dialog handlers. Assert first opening requests status, not conversation/new, OAuth or inference. Unsupported current runtime shows configuration unavailable without trying the command. Each UI action in the operation map must produce the exact operation/body and no alternate JSON/file writer.
- [ ] Add settings entry from RookChatPanel. Present provider/account connection, local Ollama endpoint, model/reasoning and future defaults. Dropdowns come from Prime status/models; numeric endpoint/model fields and the two compatibility checkboxes edit only the finite schema. Never autofill secret header/key values. `headers.keep` is default for editing; replacement/removal is explicit.
- [ ] Distinguish account route from local-no-account configuration, saved defaults from requested settings, and all of those from effective session values. Keep Connect explicit. Launch the supplied authorization URL only on the user-initiated operation; preserve sensitive provider instructions/device code exactly as plain text. Bind reply buttons to the outstanding operation/request and clear them on cancellation/result/disposal.
- [ ] Display Prime's saved outcome promptly and then separately show cleanup. If the stream/exit fails after saved, do not offer a misleading automatic Save retry. Unknown key replacement remains unknown after identical status. Disable overlapping operations and Send during the new-conversation preparation UI, not existing unrelated conversations globally. Default Save never creates a conversation or performs Test connection.
- [ ] Reuse the existing new/reopen dialog semantics: new-conversation requested selectors may come from Prime's capabilities, reopen supplies no overrides. Keep unsupported/historical runtime conversations on the existing path with explicit unknown effective fields; do not fabricate a Prime configuration process result for them.
- [ ] Test instructions escaping, synthetic secrets excluded from error/log/transcript output, wrong/duplicate replies, close-before-dispatch, cancellation during save, saved plus cleanup failure, bounds and returning-user behavior. Exercise actual control handlers and HTTP parsing, not only DTO construction. Verify previous progress segmentation/composer and image-admission behavior remain unchanged.
- [ ] Run the focused managed tests with actual discovered/executed counts; commit the UI concern. No managed-only deployment yet: new UI depends on matching service and supported future runtime.

### Task 7: Configuration Launch Binding And Live Settings Projection

**Modify (Rook):** `mcp_server/src/rook/agent/chat/prime_runtime.py`, `acp_process.py`, `acp_client.py`, `acp_conversation.py`, `acp_presentation.py`, `server.py`; `src/Rook/UI/Chat/AgentChatClient.cs`, `AgentChatTab.cs`.

**Test (Rook):** `mcp_server/tests/test_chat_prime_runtime.py`, `test_chat_acp_process.py`, `test_chat_acp_client.py`, `test_chat_acp_conversation.py`, `test_chat_acp_presentation.py`, `test_chat_server.py`, `test_chat_configuration.py`; `src/Rook.Tests/UI/Chat/RookChatConfigurationTests.cs`.

**Interfaces:** Supported-runtime ACP argv adds only the approved policy selector; its environment uses the same `data_root/prime-config` binding as configuration. `RookChatAcpClient.effective_settings` holds the validated current-session summary; add `effectiveSettings` to non-durable ConversationView/HTTP status and streamed presentation status, not to durable association identity or recorded requested settings. There is no new session-setting request.

- [ ] Add RED create/reopen tests where config directory, cwd and session paths deliberately differ. Prove both production launch builders bind the same dedicated directory and supported policy; cwd still reaches the official SDK and header validation remains unchanged. Historical verified runtime contracts use their existing launch behavior, with configuration unavailable rather than silent migration.
- [ ] Parse `NewSessionResponse.field_meta` after the real Python SDK deserializes it. In `session_update`, process matching-session effective metadata before the current active-prompt early return, so idle session updates are not lost. Apply launch/session guards; wrong/retired-session data cannot overwrite current state. Null/absent fields stay unknown.
- [ ] Project known effective metadata separately from tool cards and accumulated assistant text. Preserve ordering through the existing prompt projection; status updates must not reset assistant buffers. Carry idle/current values through ConversationView and refresh the managed label on ordinary lifecycle/status updates; no polling service or private control channel.
- [ ] Run a deterministic cross-boundary fixture: Prime's real configuration command saves synthetic defaults, real settings owner loads them; in-memory real ACP composition reports different actual/clamped settings; Python SDK and HTTP serialize them; managed parser displays effective rather than requested/default. Include future default changes while a conversation remains open, reopen without overrides and malformed/missing metadata. No model, kernel or Rook MCP launch.
- [ ] Run the bounded cumulative Stage B gate and record named results/exit codes, changed-file scopes and both repository heads. Commit the integration concern and stop at **Stage B review**. No pin bump, runtime installation or existing developer configuration switch.

## Focused Command Conventions (Future Authorized Implementation Only)

Commands are run from the isolated roots defined above, not the developer-serving worktree. Dependency-origin admission precedes them. New test files below are deliverables of their task, not currently existing evidence. All tests use temporary nonsecret configuration; fixture cleanup owns only its created paths/processes.

Prime, working directory `$PrimeRoot/packages/coding-agent`:

```powershell
& $Node "$PrimeRoot/node_modules/vitest/vitest.mjs" run --config vitest.config.ts test/configuration-policy.test.ts test/configuration-operations.test.ts test/configuration-command.test.ts test/acp-effective-settings.test.ts --reporter=default
```

During each task run only its file and implicated named neighboring cases. A failing new test is RED only if its assertion demonstrates the absent behavior; import/dependency/network/cleanup errors are not accepted RED. Do not run the complete legacy package-manager suite. Existing Prime source aliases in this package-local config avoid testing built artifacts from another checkout.

Rook Python, working directory `$RookRoot/mcp_server`; `$Python` is the exact approved existing test interpreter established in environment admission, not discovered from PATH:

```powershell
$env:PYTHONPATH = "$RookRoot/mcp_server/src"
& $Python -m pytest tests/test_chat_configuration.py tests/test_chat_prime_runtime.py tests/test_chat_acp_process.py tests/test_chat_acp_client.py tests/test_chat_acp_conversation.py tests/test_chat_acp_presentation.py tests/test_chat_server.py -q
```

Apply this environment only in the test shell and restore it afterward. Test-local fixtures must block external authentication/inference and own all synthetic child cleanup. Expand only to a named causal neighbor after inspecting its contact boundaries.

Rook managed, working directory `$RookRoot`; use the package-root and Rhino assembly bindings verified during environment admission. `--no-restore` and `RhinoPluginDir=` prohibit restore/automatic plugin copy:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore -c Debug -p:RhinoPluginDir= '-p:RhinoSystemDir=C:/Program Files/Rhino 8/System' "-p:NuGetPackageRoot=$NuGetRoot" --filter 'FullyQualifiedName~RookChatConfigurationTests|FullyQualifiedName~AgentChatClientParseTests|FullyQualifiedName~RookChatPanelTests|FullyQualifiedName~AgentChatProgressTests|FullyQualifiedName~AgentChatImageAdmissionTests|FullyQualifiedName~ConversationCloseCoordinatorTests|FullyQualifiedName~ChatServiceManagerTests' --logger 'trx;LogFileName=configuration.trx' --results-directory artifacts/configuration-review/managed
```

Retain command, working directory, source head, exit and actual selected/pass/fail counts. Require a nonempty TRX with all selected tests executed/passed, not exit 0 alone. Use a fresh ordinary result directory per run so old results cannot satisfy the gate; no frozen test-count assumption until the reviewed tests exist. These are local regression records, not another qualification protocol.

## Stage C: Later Runtime Adoption Preparation Only

### Task 8: Bind Reviewed Changes To Existing Build And Deployment Consumers

**Future allowed pin/wiring scope, only after separate approval:** `mcp_server/src/rook/agent/chat/prime_runtime_artifact.py` (existing new-build Prime pin), `prime_runtime.py` (configuration compatibility set), their existing tests, and an ordinary adoption review note under `docs/superpowers/reports/`. Do not edit current.json or any installed runtime manually. No new manifest fields are needed: existing exact compatibility commit/runtime identity binds the capability.

- [ ] Freeze accepted final Prime series and Rook integration heads after A/B review. Bind the supported configuration commit in Rook and update the existing new-build pin together, with historical-runtime compatibility tests. Do not put an unbuilt runtime ID or fabricated commit in the plan. The concrete future package records actual values once those commits exist.
- [ ] Prepare a compatibility matrix: new conversations use the selected new runtime/dedicated directory; historical conversations retain their exact recorded runtime/launch contract and cannot be silently redirected. Configuration unsupported there is explicit. Decide the working developer account transition before adoption; do not copy credentials, repoint its private directory or pretend old runtime support. Preserve accepted earlier evidence at its old identities.
- [ ] Reuse the original ACP plan's named-ref Git bundle -> WSL/Linux-filesystem checkout -> upstream `--frozen-model-catalog` Windows builder -> verified ZIP transfer -> safe assembly/runtime manifest -> shared promotion path. Obtain the actual current source/tool preflight and fresh generation values for that package. The known diagnostic UTC timestamp correction remains a prerequisite before a future Prime build; do not edit old build records or silently include its implementation here.
- [ ] Reuse `scripts/python-runtime/stage-rook-python-runtime.ps1`, `scripts/python-runtime/build-rook-python-wheelhouse.ps1` with explicit actual `-ChirpRoot`, verified official `-PipBootstrapWheel`, fresh `-BuildRoot`, and existing audit policy. Carry that same selected root as `-PythonBuildRoot` to `scripts/deploy-local-testing.ps1`, plus the verified `-PrimeRuntimePayload`. Preserve source/origin/runtime checks, both blocker checks and nonzero outer exit propagation. No inherited default-path rescue or reused partial wheelhouse.
- [ ] Select the existing deployment mode for the actual changed components. Managed-only is usable later only when matching service/runtime support is installed; it is not a shortcut for this first cross-component adoption. Python-dev mode remains explicit, changes its existing manifests/sync targets and is not a customer release. Record source/installed byte comparisons and configuration preservation for whichever separately reviewed workflow is selected.
- [ ] Before real credentials, verify the dedicated directory's actual Windows protection and exact writer/ACP consumer path with synthetic data. A missing privacy or rollout guarantee blocks that live boundary. Use no auth reads, broad ACL repairs or customer directory migration during preparation.
- [ ] Prepare separate customer-experience checks for OAuth instructions/cancellation, literal API-key connection, local Ollama without cloud auth, future-default selection and first prompt/return. Keep all live contact behind explicit authorization and reviewed inputs/bounds; do not call a model to prepare the package or reuse developer OAuth as onboarding proof.
- [ ] Return the concrete adoption package for independent review and execution authorization. Do not execute WSL build, acquisition/audit, assembly, deployment, login, model/Rhino/GH or D/E here. Existing installer source-only guards versus full built-payload guards retain their proper stages; full release readiness/security/onboarding/live gates remain separate.

## Completion And Scope Accounting

| Specification requirement | Implementing task / proof |
| --- | --- |
| First-use/return UX, sole Rook presentation | 6; 8 for separately authorized installed proof |
| Early finite command, no daemon/agent startup | 3 |
| Proxy-aware global fetch before configuration OAuth, bounded dispatcher cleanup | 3; real local routing/bypass and failure controls |
| Dedicated sources, literal policy, no ambient overrides | 1, 5, 7 |
| All nine operations and real persistence owners | Operation map; 2 |
| Ollama transport and compatibility | 2; real adapter fixture, not a catalog-only test |
| OAuth instructions and correlated input | 3, 5, 6 |
| Bounded lifetime, saved versus cleanup, unknown replacement | 2, 3, 5, 6 |
| Actual session settings over official ACP | 4, 7 |
| Working installation/historical runtime preservation | Isolated workspace admission; 5 and 8 capability gates |
| No new framework or release claim from synthetic tests | Every stage stop; 8 |

Commit only each task's owned files after approval to execute that stage. Keep local synthetic evidence small and secret-free. Do not stage the knowledge note or edit the approved specification to avoid a failing implementation assertion. A genuine conflict is a review stop, not permission to add another subsystem.

**Current deliverable:** this plan only, uncommitted for independent review. No stage, test, dependency preparation, credential operation or runtime adoption has been performed by writing it.
