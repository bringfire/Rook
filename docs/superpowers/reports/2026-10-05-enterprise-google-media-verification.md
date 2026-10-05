# Enterprise Google media verification

Execution branch: `codex/enterprise-google-media`. Baseline: `bc19d4afaa5b4807ea944091e33f19d3012579c2` (2026-10-05). Approved design and implementation plan accompany this report.

## Recovery map

Preserved work: `174b2675b6ff809acd16bf4627efe8abdfdbcde0`; preserved checkout remains unchanged.

- Recover Python `vertex_token_lease.py` and its focused tests, extending explicit model/location policy and original authorization binding.
- Recover managed `VertexAccessTokenContract.cs` and `ChatServiceVertexAccessTokenSource.cs` and their tests; adapt the contract and bounded transport.
- Recover only the atomic owned connection snapshot in `ChatServiceManager`; preserve current startup, ownership, shutdown, and ACP discovery.
- Add token routes to current `agent/chat/server.py`; preserve current ACP/Prime chat and configuration routes. Do not restore the old chat server wholesale.
- Retain existing Vertex DPAPI store, configuration generation rotation, readiness and text backend. Shared `region` retains text/Chirp routing semantics.
- Retain current subsystem root/native callback wiring, registries, managers, ledger, and artifact store. Apply provider injection locally after contracts and consumers are verified.

## Current Google contract

Verified 2026-10-05 against primary documentation: [image model](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image) and [Veo REST flow](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-references).

First image: `vertex_ai/gemini-3.1-flash-image`, `global` (GA model; 512/1K/2K/4K supported). First video: `vertex_ai/veo-3.1-fast-generate-001`, `us-central1`. Video submission uses `predictLongRunning`; polling uses model `fetchPredictOperation` with the full original operation name. Omitting `storageUri` requests inline Base64 video. Local stop never implies confirmed remote cancellation.

## Fresh baseline

Both commands rebuilt or imported this checkout's source; no `--no-build` used.

- Managed: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter 'FullyQualifiedName~Services.Vision|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~ChatServiceManagerTests' --verbosity minimal`: **1465 passed, 0 failed, 0 skipped**.
- Python: existing Vertex auth, OAuth, backend, runtime integration, acceptance harness files: **150 passed**, 11 existing DSPy deprecation warnings. Interpreter reused from the main checkout's virtual environment; source came from this worktree.

Full baseline logs are retained in the execution scratch workspace. Infrastructure baseline is not acceptance of forthcoming source changes.

## Acceptance status

Implementation and available automated checks pass. The full regression gate is incomplete because its existing external Prime real-producer fixture is unavailable. Memory acceptance passed on this host. Installed live acceptance is not run: no pilot project or desktop client has been selected and no browser consent has been performed. No live jobs have been submitted. These results do not establish installed Google production assurance.

## Token checkpoint

Recovered only token-specific code and the owned connection helper. Fresh checks: 216 Python tests passed (11 existing warnings), 39 managed tests passed. Tests cover nonce/origin/method/body admission, authorization rotation before/during refresh, original binding mismatch, location-specific cached reuse, caller/deadline cancellation, and publication interface. Existing managed Chirp retirement/same-port relaunch tests passed. Explicit shared-region save regression verifies protected OAuth preservation, fresh generation, changed text kwargs and exact regional readiness URL. Inspected startup refactor and bounded adapter before advancing.

## Publication and race checkpoint

Fresh managed media/handler suite passed 1,547 tests before repetition. Nine deterministic guarded-manager cases passed 25 repeated runs. Final rebuild also includes original-binding copy and restart-preservation assertions. Per-running-job transition gates re-read the durable terminal state; no network or sidecar call runs under the gate. Local stop persists Interrupted before cancellation, retains accepted original handles returned after stop, and performs no remote cancel. Guards run before creation and completion; failed final guards and cancellation remove only the new artifact. Completed jobs remain completed. Existing remote cancellation behavior passed. A null-valued existing Replicate metadata test caught a cloning regression; cloning now preserves null values.

Task4: explicit global OAuth image provider reuses Gemini request encoding and existing inline artifact types. Shared root registry reaches panel and native callback. Fresh focused472/broader651 managed and14 Python tests passed. Synchronous handler publication failures before/after creation preserve only input artifacts; unknown qualified Vertex models cannot fall back to AI Studio.
Task5: rebuilt925 video/generation tests passed. Tests cover one submission, original operation binding, per-read retry binding, disconnect, inline output, conflicting/empty/remote output rejection and separate Vertex person-generation mapping. Status persists no video data; result refetch decodes once. All provider errors omit upstream detail.
Task6:88 Vertex Python tests and220 managed configuration/token tests pass. Full configuration suite additionally requires an unrelated existing Prime producer checkout at D:/prime-agent/.worktrees/rookchat-configuration; missing loader causes one Python failure and its dependent managed producer-fixture failure. The220 count excludes that unavailable managed fixture check. No replacement fixture was fabricated. Setup guide explains pilot and firm onboarding prerequisites.
Task7:354 rebuilt managed tests,90 Python media contracts and Node execution of panel module passed. UI behavior test proves two simultaneous calls dispatch once, unknown submission never auto-retries, next deliberate request warns, local stop differs from confirmed completion, and Vertex price renders unavailable. Existing Gemini/API-key defaults remain first.

## Fresh source verification and memory checkpoint

Fresh `dotnet build src/Rook/Rook.csproj --configuration Debug` built net48 and net8.0: 0 errors, 274 existing/target-platform warnings. The required broad rebuilt managed filter ran 2,465 tests: 2,464 passed, one failed because `ROOK_TASK7_HTTP_FIXTURE` cannot be produced without the missing external Prime checkout/loader. A fresh run excluding exactly that prerequisite-dependent test passed all 2,464 tests. No product test was changed to hide the missing prerequisite.

All Vertex Python suites plus vision/video MCP contracts: 293 passed, 11 DSPy deprecation warnings. The updated acceptance-validator and Node panel behavior checks then passed five tests. Provider-to-manager synthetic acceptance passed completion, disconnect, and restart behavior through existing registries, ledger and artifact store; it made no real Google calls.

Memory probes ran five fresh x64 testhosts after rebuilding the affected test source. Fixtures emit UTF-8/Base64 into the existing capped reader without retaining a second expected payload. Each probe measures terminal status without decode, result decode, artifact publication and cleanup. The 250 MiB case also rejects one byte above the decoded cap before decoding. Separate stream tests enforce actual-read cap and cancellation. Samplers read process working/private memory every 10 ms and retain the OS peak working set. GC counters, managed-live diagnostics and weak references are supplementary; process peaks are the primary measurements.

| Decoded MiB | Concurrent jobs | OS peak working MiB | Sampled peak private MiB | Live managed delta after cleanup MiB | Payload references retained |
|---:|---:|---:|---:|---:|---|
| 1 | 1 | 131.3 | 103.7 | 1.17 | none |
| 16 | 1 | 229.0 | 219.6 | 0.17 | none |
| 64 | 1 | 354.4 | 509.7 | 0.17 | none |
| 250 | 1 | 1093.8 | 1752.3 | 0.17 | none |
| 250 | 2 | 1962.3 | 3424.3 | 0.17 | none |

This host has approximately 63.6 GiB visible RAM; no additional memory limit was imposed by the probe. No OOM occurred. Maximum concurrency remains two and the decoded cap remains 250 MiB. All weak references to encoded/decoded payload arrays were dead after cleanup/full GC; assertions enforce that condition. Earlier smaller-case retained process memory prompted this diagnostic, rather than being silently accepted. The memory result is host-specific and uses synthetic bytes, so it does not prove MP4 playback or a universal system minimum.

Sanitized raw memory measurements and tested-assembly provenance are stored next to this report. Installed live acceptance remains separate: one image and three videos, including actual refresh, disconnect and restart. Local stop/race coverage is automated within the agreed budget. The source harness runs automated/memory gates and validates an operator's sanitized installed-session evidence; it does not create billed jobs or implement a production invalidation endpoint.

## Independent review and final source verification

The independent whole-branch review found four important gaps: disconnect cancellation after mutex admission; read-deadline interruption; dispatched-submit stop classification; and insufficient live proof. Focused fixes were committed as `d56353b7`, `95ce2fce`, `5746d560`, `9026370e`, and `bc5ae8dd`. Follow-up review reproduced one additional stop interval after an unknown submission returned but before its failure was committed; a new deterministic barrier test failed against the prior source and passed after outcome classification and settlement were captured under the same transition gate. The closed unknown marker survives both status and queue adapters. No raw provider code/detail is exposed by that UI marker.

Final independent follow-up on `bc5ae8dded237b9d33e87da0b868cf8babfea96c` closed all four original source findings with no new actionable finding. The reviewer independently ran 25 validator/Node checks and whitespace checks; they did not claim independent managed builds, memory probes, installed OAuth, or Google execution. Synchronous panel images now have an explicit evidence shape with null job/ledger fields and a request correlation label; manager-backed images require their real ledger transitions.

The primary final source checks at that exact clean source commit rebuilt **net48, net7.0 and net8.0**, with 0 errors and 472 existing/target-platform warnings. Fresh broad managed checks excluding exactly the unavailable external Prime producer-fixture test passed **2,470 tests**. Python Vertex and media MCP suites passed **315 tests**, with 11 existing DSPy deprecation warnings. The full unexcluded managed gate remains prerequisite-incomplete because the previously documented external producer fixture is unavailable; no passing full-gate claim is made.

The final five fresh-host memory probes passed after the final rebuild. Tested net48 assembly SHA-256: `b75fd35ac5ba29592eadcfac89a4bba9c3a8503be3270d0b6bf35b1e43a49289`; modification UTC `2026-10-05T16:47:20.781749+00:00`. The source patch was empty and there were no untracked source files. Updated raw measurements replace the adjacent memory JSON, with this exact source/assembly provenance.

| Decoded MiB | Concurrent jobs | OS peak working MiB | Sampled peak private MiB | Live managed delta after cleanup MiB | Payload references retained |
|---:|---:|---:|---:|---:|---|
| 1 | 1 | 142.3 | 114.0 | 1.17 | none |
| 16 | 1 | 242.3 | 232.4 | 0.17 | none |
| 64 | 1 | 356.5 | 509.1 | 0.16 | none |
| 250 | 1 | 1100.6 | 1754.0 | 0.17 | none |
| 250 | 2 | 1961.6 | 3417.0 | 0.20 | none |

Host and synthetic-media limitations above still apply. Live pilot preparation has reached Google's private sign-in page only. No deployment, OAuth consent, or live generation has occurred. The user selected a Workspace practice pilot and requires all Google account/project information, downloaded client files and private evidence to remain outside all repositories/worktrees. The live harness rejects repository input/output paths; examples use synthetic labels. This report contains only code/test provenance, without a Google account or project identifier. Installed/live acceptance remains **not run** and the agreed budget remains one image/three videos.
