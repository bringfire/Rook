# RookChat Astra Support Implementation Plan

> For agentic workers: use superpowers:executing-plans after scope approval; stop at the review gates below. This document does not authorize implementation or runtime activity.

**Goal:** Make `openai-codex/gpt-6-astra` selectable through RookChat with correct reasoning and request semantics under an explicit initial client-capacity policy, without disguising unknown server limits.

**Architecture:** Prime owns model metadata, validation, requests and context management. Rook presents Prime's existing catalog and actual ACP session state. No new provider, transport, configuration service or readiness system.

**Tech Stack:** Existing TypeScript/Vitest Prime packages; existing Python ACP/configuration boundary and managed RookChat; pinned Node/Bun build pipeline.

**Spec:** The user-approved Astra requirement in this conversation and `../specs/2026-09-10-rookchat-configuration-interface-design.md`. No new comprehensive specification.

## Baseline and constraints

- Prime root P: `D:/prime-agent/.worktrees/rookchat-configuration`, clean at `dacbeab26b705e7d07b55ae6f8cd3e95ceb5458b`.
- Rook root R: `C:/UDEV/Rook/.worktrees/rookchat-configuration`, HEAD `75faba2cdfd05ad6355a58cf00fb05f975ac1b2d`. Earlier `mcp_server/tests/test_chat_acp_conversation.py` changes remain unstaged; do not include them. Preserve the older worktree's knowledge modification.
- Planning pass: source/documentation reads only; this plan is the sole new file. No tests, builds, dependencies, model requests, credentials or installed changes.
- Do not change saved defaults automatically, migrate historical conversations, change credential ownership, or broaden into an upstream merge. Prime publication remains held.
- Implementation stays isolated; build, assembly, installation and live access each require their existing separate authorization. Preserve the unresolved shipped dependency advisory and historical failure evidence.

## Evidence and capability table

Official pages read on 2026-09-17:
- [Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra): API context 1,050,000 tokens, output 128,000; efforts low/medium/high/xhigh/max.
- [Migration guidance](https://developers.openai.com/api/docs/guides/latest-model): Responses for tools; no none/minimal effort; omit temperature/top_p/top_logprobs. Describes optional async tools, steering and configuration-update features. The model-specific markdown URL returned an error twice; the substantive HTML guide was used.
- [Codex models](https://learn.chatgpt.com/docs/models): Astra is listed; access depends on account/client/rollout. Ultra orchestrates subagents rather than adding a model effort. Experimental cross-window notes/history retrieval is a supported-client feature, opt-in and restricted by sign-in/plan.

| Capability | Pinned-source result | Required disposition |
| --- | --- | --- |
| Catalog/configuration | Astra absent; explicit Codex list in P/packages/ai/scripts/generate-models.ts:1953. Configuration operations expose registry models. | Add only Astra to generator and checked-in catalog. Rook picker is data-driven; no model-name special case. |
| Full single-model reasoning | `getSupportedThinkingLevels`/`clampThinkingLevel` support per-model maps, including max. Existing generator's family checks miss Astra. | Explicit `{ off: null, minimal: null, xhigh: "xhigh", max: "max" }`; preserve low/medium/high. Do not alias Ultra to max. |
| Context/compaction | Prime's Codex list shares 272000; `shouldCompact` compares actual usage to model.contextWindow minus reserveTokens (default 16384). Official Codex client metadata separately records Astra default 272000 and maximum override 872000; see investigation below. | Deliberately choose 272000 for Astra, following the official client default. Retain Prime's default trigger above 255616, not Codex-equivalent compaction. Defer larger context; do not change older models. Unknown server/account limits do not block this accepted initial policy. |
| Output metadata and wire behavior | Prime's existing Codex catalog uses `CODEX_MAX_TOKENS=128000`. Shared simple options default to at most 32000, but Codex request builder does not serialize maxTokens/max_output_tokens. | Populate Astra's required numeric `maxTokens` with 128000 using that existing convention, also matching the documented API figure. This is bookkeeping, not verified subscription capacity or an enforced limit. Keep wire behavior and shared budgets unchanged; test the actual body without introducing an output parameter. |
| Text, image, tool calls, streaming | Existing Responses conversion and SSE/WebSocket paths are model-ID agnostic; tool IDs and encrypted reasoning are retained. | Reuse them; causal Astra regression through real SDK/adapter and multi-turn tool replay. Not yet Astra runtime-qualified. |
| Sampling/effort edge cases | Codex adapter forwards explicitly supplied temperature; low-level `mappedValue ?? originalEffort` revives a disabled null-mapped effort. | Narrow Astra-only parameter handling with tests of both public adapter entrypoints. Deliberately reject or normalize unsupported efforts, never accidentally forward them. Preserve older models. |
| Fast/service tier | `supportsFastMode` excludes Astra. No Rook speed control established here; regional restrictions exist. | Explicitly not enabled in this narrow plan; no claim of full speed-tier parity. Separate approval if required. |
| Async tools, mid-turn steering, dynamic reasoning | No Astra-specific implementation of these new protocols in inspected path. Existing Rook conversation-setting and submission restrictions apply. | Optional workflow extensions, not prerequisites for normal Astra chat/tools; do not activate or advertise them in this change. |
| Ultra, Pro-mode product behavior, experimental context-management features | Not established by selecting a model ID. Prime's normal summary compaction is not Codex's experimental notes/search mechanism. | Do not claim full Codex-client feature parity. These require distinct scope decisions, not invented effort values. |

The interpretation proposed for approval is full supported *single-model* Astra operation within existing RookChat workflows. If "full potential" includes the optional client/workflow features above, that is an explicit extension, not something this plan silently satisfies.

## Focused capacity investigation: 2026-09-17

Read-only public-source investigation completed at official OpenAI Codex commit
`7498521d288b9b3b96ffba4eedf089d8d6e06a84`, resolved through GitHub's public commits
API. Files were retrieved at that exact revision in memory; no client, account
cache, credentials or inference endpoint was opened. Third-party search results
and issue anecdotes were not used as capacity authority.

- [Bundled catalog](https://github.com/openai/codex/blob/7498521d288b9b3b96ffba4eedf089d8d6e06a84/codex-rs/models-manager/models.json): Astra has `context_window=272000`, `max_context_window=872000`, and `auto_compact_token_limit=null`. No maximum-output field is present in this model entry. These are official client metadata, not a server-capacity measurement. Its Ultra picker entry describes automatic delegation, not an extra wire effort.
- [Override consumer](https://github.com/openai/codex/blob/7498521d288b9b3b96ffba4eedf089d8d6e06a84/codex-rs/models-manager/src/model_info.rs): `with_config_overrides` caps a selected context window at `max_context_window`.
- [Metadata semantics](https://github.com/openai/codex/blob/7498521d288b9b3b96ffba4eedf089d8d6e06a84/codex-rs/protocol/src/openai_models.rs): the maximum is documented as a config-override limit. The client defaults to 95% usable context and derives its auto-compaction limit at 90% of the resolved window. For 272000 those are 258400 and 244800; for an 872000 override, 828400 and 784800. These arithmetic values are Codex policy, not Prime defaults or independent server limits.
- [Catalog owner](https://github.com/openai/codex/blob/7498521d288b9b3b96ffba4eedf089d8d6e06a84/codex-rs/models-manager/src/manager.rs): supports authenticated remote catalog refresh and replacement of matching bundled model metadata. The bundled file cannot certify an individual account's current allowance.

**Disposition:** there is now authoritative evidence for a 272000 client default
and an 872000 client override ceiling, but not for the absolute subscription
server context/output contract. Prime's 16384 reserve is its own policy; simply
setting 872000 would put its trigger above 855616, unlike Codex's 784800 threshold.
Do not equate these thresholds or silently import one client's safety policy.
Prime still transmits no explicit maximum-output field; its internal maxTokens
value neither proves nor enforces a 32000 or 128000 subscription output cap.

This focused public investigation stops here. The user accepted an initial 272000
client-context policy while keeping subscription server/output limits unknown.
Larger-context operation, including the official client's 872000 override ceiling,
is deferred. No account-metadata investigation or giant-context stress test is
needed for this integration. The API's 1050000/128000 figures remain separate from
subscription-route guarantees. The policy decision does not authorize runtime
build, adoption or live checks.

## Gate 0: accepted initial client policy (closed)

- [x] Inspect published official client/model metadata and consumers at a fixed revision; record findings above and distinguish default, override ceiling, headroom and compaction threshold. No personal cache, auth file or account data inspection.
- [x] Accept `contextWindow: 272000` deliberately following the official client default, not merely inheriting an older model's value. Absolute server capacity and individual account allowance remain unverified; that uncertainty is not an initial-integration blocker.
- [x] Retain Prime's existing compaction policy: default reserve 16384, no trigger at 255616, trigger above 255616. Preserve existing reserve overrides and disabled-compaction behavior. Do not claim Codex-equivalent compaction.
- [x] Specify `maxTokens: 128000` using the generator's existing `CODEX_MAX_TOKENS` convention and the same value in the frozen catalog. This required numeric metadata is bookkeeping, not evidence of a subscription output allowance. Do not present it as a verified or enforced route limit.
- [x] Keep the transmitted output behavior unchanged: no new `max_output_tokens` or other output-limit parameter, no change to shared simple-options budgets. Test absence of output-limit fields rather than asserting an enforced 32000 or 128000 cap.
- [x] Defer larger context and further capacity investigation. Proceed with the bounded catalog/reasoning/adapter coverage; retain separate source review and build/adoption gates.

## Task 1: catalog and request compatibility (Prime source review)

**Modify only:** P/packages/ai/scripts/generate-models.ts; P/packages/ai/src/models.generated.ts; P/packages/ai/src/providers/openai-codex-responses.ts if parameter tests require it.

**Tests:** create P/packages/ai/test/astra-models.test.ts; extend P/packages/ai/test/openai-codex-stream.test.ts and P/packages/ai/test/model-catalog-build-mode.test.ts.

**Interfaces:** `getModel`, `getSupportedThinkingLevels`, `clampThinkingLevel`, `streamSimpleOpenAICodexResponses`, `streamOpenAICodexResponses`; same catalog/result schemas as today.

- [ ] RED: assert the real catalog returns Astra, exactly five supported efforts, text/image input, `contextWindow: 272000` and bookkeeping `maxTokens: 128000`. A useful exact assertion is `expect(getSupportedThinkingLevels(model)).toEqual(["low", "medium", "high", "xhigh", "max"])`.
- [ ] RED: use synthetic tokens and intercepted transport to capture actual request bodies for every supported effort, default/omitted effort, explicit off/minimal/none cases and explicit temperature. Verify no effort downshift for high/xhigh/max, no unsupported sampling fields, and unchanged Sol controls. Test low-level and simple entrypoints; spelling-only tests are insufficient.
- [ ] RED: capture both entrypoints' actual request bodies with default and explicit shared output-budget options. Assert unchanged omission of output-limit fields; do not infer server enforcement from catalog metadata or a mocked response.
- [ ] Make the entrypoint outcomes explicit: configuration save refuses unsupported choices; the existing simple/SDK normalization may turn off/minimal into low, with actual session reporting low. The low-level Astra adapter rejects explicitly unsupported none/minimal (and runtime-invalid off) before transport rather than falling through a null map. Omitted effort stays omitted unless separately justified. Assert no request on rejection and unchanged high/xhigh/max on valid calls. Omit Astra's unsupported sampling parameters; do not apply this policy globally to older models. This is proposed correction behavior, not an implemented change.
- [ ] Implement the narrow catalog/map change and any demonstrated adapter correction. Keep generator and frozen catalog consistent; do not execute the network-wide model refresh. Do not add generic provider abstractions or change shared simple-options budgets to address a nonexistent wire cap.
- [ ] GREEN: synthetic SSE and WebSocket completion, image input, tool request/result continuation, encrypted reasoning replay and cancellation. All external calls refuse unless intercepted; all resources settle within existing fixture bounds. Frozen build mode must retain Astra without catalog refresh.
- [ ] Review source diff, RED/GREEN, exact executed counts and unchanged lockfile. Commit only after source approval.

## Task 2: prove configuration-to-session and capacity (source review)

**Tests only initially:** P/packages/coding-agent/test/configuration-operations.test.ts; P/packages/coding-agent/test/configuration-policy.test.ts; P/packages/coding-agent/test/compaction.test.ts; P/packages/coding-agent/test/compaction-summary-reasoning.test.ts; P/packages/coding-agent/test/acp-effective-settings.test.ts.

**Existing consumers to trace, not preapproved production edits:** P/packages/coding-agent/src/core/sdk.ts, core/agent-session.ts, core/compaction/compaction.ts and modes/acp/acp-mode.ts; R/mcp_server/src/rook/agent/chat/configuration_protocol.py; R/src/Rook/UI/Chat/AgentChatClient.Configuration.cs and RookChatConfigurationDialog.cs.

- [ ] Synthetic store: real `models` reports Astra/efforts with access unverified; `defaults.save` accepts each supported effort, refuses off/minimal/ultra and verifies persistence without changing an existing session. No opening/refresh autosave.
- [ ] Drive real SDK creation using those saved defaults and the dedicated policy into captured real-adapter requests. Assert exact model/effort and dedicated credentials; do not manually supply only an adapter model and call it end-to-end proof.
- [ ] Assert actual ACP settings report the session's Astra/effort, not merely defaults; retain ordering/unknown-state controls. Rook's current string-based catalog/effort consumers require no new interface.
- [ ] Compaction: use synthetic usage counts with Astra's 272000 context and the existing default reserve. Assert no trigger at 255616 and a trigger at 255617, retain disabled-compaction/reserve-override controls and unchanged older-model thresholds. Test model lookup into session context accounting, not only the pure predicate. No huge prompts or larger-context qualification.
- [ ] Verify summary generation retains valid reasoning and tool/result continuity. Distinguish summary-budget options from what the Codex request body actually sends; do not assert an unenforced output bound.
- [ ] If these tests reveal a production change outside Task 1, report the exact failing consumer and smallest extension before editing it. No generic compaction redesign or capacity claim based solely on mocked server acceptance.

Proposed focused commands (not executed; existing dependencies only), from P:

```powershell
Push-Location packages/ai
..\..\node_modules\.bin\vitest.cmd run test/astra-models.test.ts test/openai-codex-stream.test.ts test/model-catalog-build-mode.test.ts
Pop-Location
Push-Location packages/coding-agent
..\..\node_modules\.bin\vitest.cmd run test/configuration-operations.test.ts test/configuration-policy.test.ts test/compaction.test.ts test/compaction-summary-reasoning.test.ts test/acp-effective-settings.test.ts
Pop-Location
node_modules\.bin\tsgo.cmd --noEmit
```

Capture each exit before the next command; stop on failure, no automatic retry. Use the existing bounded process runner for outer ownership. Review fixture cleanup before adding cases; each synthetic child/thread/socket must settle. Run non-writing Biome checks on changed files, not the root `npm run check` that includes `--write` and unrelated checks. Missing dependencies require a separate preparation decision, not an install. No broad ACP legacy-suite rerun.

## Task 3: runtime adoption, separately approved after source

- [ ] Freeze the reviewed Prime commit/parent. Reuse R/scripts/build-prime-acp-runtime.sh and its existing Windows-x64 WSL pipeline (Bun 1.3.14, frozen catalog). Keep ZIP/build record/exit/lockfile evidence; no rebuild loop.
- [ ] Rook source identity scope: R/mcp_server/src/rook/agent/chat/prime_runtime_artifact.py, prime_runtime.py and R/mcp_server/tests/test_chat_prime_runtime.py plus directly necessary existing packaging assertions. Add the new commit while retaining c2055d6a/dacbeab26 dedicated-store policy and b71badc5 historical behavior. No invented commit or runtime ID in advance.
- [ ] Run existing artifact/adoption tests; assemble with R/scripts/package-prime-acp-runtime.py only after accepted ZIP identity. Verify the complete staged payload and derived runtime identity. No assembly under the old pin.
- [ ] Prepare the existing matched deployment, not managed-only (the changed Prime and Python admission must ship together). Preserve credentials, storage protection, historical bindings and installed generations. Installation needs separate authorization and byte verification.
- [ ] Only after approved installation, a separately agreed short Astra text/tool observation may qualify actual route access and session settings. Giant-context/output stress tests and account-metadata investigation are outside this initial integration. No automatic migration of existing conversations/defaults.

## Acceptance and stop boundary

Source acceptance requires catalog-to-wire correctness, all supported single-model efforts, the accepted 272000 client policy, unchanged Prime compaction and wire-output behavior, explicit bookkeeping metadata, and causal tests. Unknown server limits are documented, not a demand for further research. Packaged/live claims require later evidence; a mocked transport cannot prove entitlement or server limits. Optional feature parity and larger-context operation remain explicitly excluded, not silently described as complete.

This amendment closes the capacity-policy decision without another specification cycle. It changes only the plan; implementation results return for source review before the existing separately authorized build/adoption process. Do not stage, commit, build, deploy, inspect credentials or initiate authentication from this planning amendment.
