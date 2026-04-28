# Multi-Provider Phase 1 PR-4 Status

**Worktree:** `multi-provider-phase1-pr4`

**Scope:** keyed generation secret storage, legacy Gemini migration, shared managed dependency wiring, and missing-key compatibility.

**Canonical plan:** `docs/rook_docs/2026-04-27-multi-provider-phase1-plan.md`

## Current Decision

Do not add `IProviderRegistration.RequiredSecretKeys` or `SecretStatus` in PR-4.

Deferred rationale:
- Phase 1 widens credential storage and preserves submit-time missing-key failure.
- Settings UI and picker filtering are unchanged in Phase 1, so no code consumes provider secret-status metadata.
- fal, Replicate, and Tencent credential shapes are not wired yet; Phase 2 provider/settings UI work is the right point to lock the metadata contract.

PR description text to carry forward:

```md
Deferred from PR-4 plan: IProviderRegistration.RequiredSecretKeys and SecretStatus.
Reason: Phase 1 only widens credential storage and preserves submit-time missing-key behavior. No Settings UI or picker filtering consumes provider secret status yet. This metadata belongs with Phase 2 provider/settings UI work, where fal/Replicate/Tencent credential shapes can validate the final contract.
```

## Implemented

- Added `IGenerationSecretStore`, `DpapiGenerationSecretStore`, and `GenerationSecretsSettings`.
- Added keyed secret constant for Gemini: `GenerationSecretKeys.GeminiApiKey`.
- Added one-shot legacy migration from `vision.GeminiApiKeyEncrypted` into `generation_secrets["gemini.api_key"]` on `GetSecret`.
- Kept `HasSecret` and `GetPreview` metadata-only for legacy Gemini state, so settings overview does not decrypt legacy ciphertext.
- Converted `VisionSecretStore` into the compatibility shim over `IGenerationSecretStore` while preserving legacy direct-settings constructor behavior for tests and rollback compatibility.
- Threaded the shared keyed store through:
  - `RookSubsystemRoot`
  - `VisionHandler`
  - `VisionWebSurface`
  - `NativeGhBridgeRegistrar`
  - `VideoSubsystemFactory`
- Preserved Gemini missing-key message parity for `generate` and `enhance_prompt`.
- Added shared-store identity tests for the keyed store and shim backing store.

## Deferred

- `IProviderRegistration.RequiredSecretKeys`
- `SecretStatus`
- Provider secret-status registry computation
- Settings UI / picker metadata that consumes provider credential status
- Any fal/Replicate/Tencent credential UI or provider-secret shape finalization

## Remaining Before PR Publish

- [ ] Stage/include untracked generation secret files:
  - `src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs`
  - `src/Rook/Services/Vision/Generation/DpapiGenerationSecretStore.cs`
  - `src/Rook/Services/Vision/Generation/GenerationSecretsSettings.cs`
  - `src/Rook.Tests/Services/Vision/Generation/GenerationSecretStoreTests.cs`
  - `src/Rook.Tests/Services/Vision/Generation/MissingKeyErrorParityTests.cs`
- [ ] Include this status doc and the Phase 1 plan update if they are intended to be committed with PR-4.
- [ ] Run final managed verification after staging:
  - `dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore`
  - `dotnet build src/Rook/Rook.csproj --no-restore -p:RhinoPluginDir=`
  - `git diff --check`
- [ ] Confirm PR description includes the deferral note above.

## Latest Verification Evidence

Last known final-state checks in this worktree:

- `dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore`: 1230 passed, 0 failed.
- `dotnet build src/Rook/Rook.csproj --no-restore -p:RhinoPluginDir=`: passed, 0 errors.
- `git diff --check`: only LF-to-CRLF warnings on edited files.

Native `RookNative` build was not run. No native files are in PR-4 scope.
