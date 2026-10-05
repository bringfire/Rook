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

Automated implementation acceptance: not run. Memory acceptance: not run. Installed live acceptance: not run; requires desktop OAuth client configuration, billed project, approved identity, and one-image/three-video budget. No live jobs have been submitted.

## Token checkpoint

Recovered only token-specific code and the owned connection helper. Fresh checks: 216 Python tests passed (11 existing warnings), 39 managed tests passed. Tests cover nonce/origin/method/body admission, authorization rotation before/during refresh, original binding mismatch, location-specific cached reuse, caller/deadline cancellation, and publication interface. Existing managed Chirp retirement/same-port relaunch tests passed. Explicit shared-region save regression verifies protected OAuth preservation, fresh generation, changed text kwargs and exact regional readiness URL. Inspected startup refactor and bounded adapter before advancing.

## Publication and race checkpoint

Fresh managed media/handler suite passed 1,547 tests before repetition. Nine deterministic guarded-manager cases passed 25 repeated runs. Final rebuild also includes original-binding copy and restart-preservation assertions. Per-running-job transition gates re-read the durable terminal state; no network or sidecar call runs under the gate. Local stop persists Interrupted before cancellation, retains accepted original handles returned after stop, and performs no remote cancel. Guards run before creation and completion; failed final guards and cancellation remove only the new artifact. Completed jobs remain completed. Existing remote cancellation behavior passed. A null-valued existing Replicate metadata test caught a cloning regression; cloning now preserves null values.
`nTask4: explicit global OAuth image provider reuses Gemini request encoding and existing inline artifact types. Shared root registry reaches panel and native callback. Fresh focused472/broader651 managed and14 Python tests passed. Synchronous handler publication failures before/after creation preserve only input artifacts; unknown qualified Vertex models cannot fall back to AI Studio.
Task5: rebuilt925 video/generation tests passed. Tests cover one submission, original operation binding, per-read retry binding, disconnect, inline output, conflicting/empty/remote output rejection and separate Vertex person-generation mapping. Status persists no video data; result refetch decodes once. All provider errors omit upstream detail.
Task6:88 Vertex Python tests and220 managed configuration/token tests pass. Full configuration suite additionally requires an unrelated existing Prime producer checkout at D:/prime-agent/.worktrees/rookchat-configuration; missing loader causes one Python failure and its dependent managed producer-fixture failure. The220 count excludes that unavailable managed fixture check. No replacement fixture was fabricated. Setup guide explains pilot and firm onboarding prerequisites.
