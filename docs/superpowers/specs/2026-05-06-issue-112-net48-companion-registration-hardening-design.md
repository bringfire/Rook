# Issue 112: net48 Companion Registration Hardening

## Context

`src/Rook/Rook.csproj` intentionally multi-targets `net7.0;net48`, but Rhino 8 deployment requires the `net7.0` companion output for WebView-backed surfaces. `RookWebSurface` only attempts WebView2 virtual-host setup in `NET7_0_OR_GREATER` builds; a `net48` companion can load and register, but Vision and Knowledge Graph panels fall back to the minimal unavailable HTML instead of the real embedded WebView content.

Issue #112 tracks the remaining install/register paths that can still deploy or register a broken `net48` companion. PR #102 changed priority order, but it did not remove every fallback. The accepted invariant for this work is:

No installer or registration path, automatic or explicit, can silently register `net48` as the active Rhino 8 Rook companion.

## Scope

In scope:

- Remove automatic `net48` companion fallback/reuse/success paths from `install.ps1`.
- Remove automatic `net48` companion discovery from `scripts/register-companion.ps1`.
- Validate every final companion `RhpPath` in `scripts/register-companion.ps1`, whether user-supplied, colocated with `RookNative.rhp`, or discovered from repo build outputs.
- Reject a resolved path with an exact `net48` path segment, case-insensitive.
- Use the same failure message wherever the validation rejects a path:
  `net48 Rook companion builds are not supported for registration; use the net7.0 Rook.rhp output.`
- Add lightweight script-level regression coverage for automatic fallback text and explicit `net48` rejection.

Out of scope:

- Changing `src/Rook/Rook.csproj` target frameworks.
- Removing `net48` support from tests or managed compile paths.
- Changing native plugin build or registration behavior except where it delegates to companion registration.
- Adding an override for legacy `net48` companion registration. Current architecture does not document a supported Rhino 8 scenario for that.

## Design

### install.ps1

`Step-BuildCompanion` becomes deployable-`net7.0` only.

Dry-run behavior:

- If `src\Rook\bin\Release\net7.0\Rook.rhp` exists, report reuse of that build.
- Otherwise report that the installer would build the managed companion.
- Do not mention or inspect `src\Rook\bin\Release\net48\Rook.rhp`.

Runtime behavior:

- Reuse only `src\Rook\bin\Release\net7.0\Rook.rhp`.
- If no reusable `net7.0` build exists, run the existing `dotnet build src/Rook -c Release`.
- After build, success requires `src\Rook\bin\Release\net7.0\Rook.rhp`.
- If build succeeds but the `net7.0` output is still missing, fail the companion step with a clear diagnostic that Rhino 8 companion deployment requires the `net7.0` output.

This keeps native deployment untouched, but the existing release-package path needs its own guard because `plugin\Rook.rhp` does not carry a target framework segment in the path. When `install.ps1` runs in release-package mode, accepting `plugin\Rook.rhp` should require adjacent net7 runtime metadata, at minimum `plugin\Rook.runtimeconfig.json` with `runtimeOptions.tfm` equal to `net7.0`. If that metadata is missing or names another target framework, the companion step should hard-fail instead of deploying the package companion. This makes the release-package branch consistent with the source-build branch: only a Rhino 8 `net7.0` companion is deployable.

### scripts/register-companion.ps1

Auto-discovery keeps the existing priority shape:

1. Colocated `Rook.rhp` next to the registered `RookNative.rhp`.
2. Repo build outputs for development registration.

The repo build output candidate list is narrowed to `net7.0` only:

- `src\Rook\bin\Debug\net7.0\Rook.rhp`
- `src\Rook\bin\Release\net7.0\Rook.rhp`

After explicit input or auto-discovery produces a final `$RhpPath`, the script validates it before registry writes and before success output. Validation resolves the path for existing files, then rejects an exact path segment equal to `net48`, case-insensitive. Matching by path segment avoids false positives from unrelated folder names such as `net48-notes`.

`install.ps1` normally reaches companion registration through `scripts/register-rooknative-suite.ps1` when the native plugin is present; that suite script delegates companion registration to `register-companion.ps1`. The implementation should keep validation centralized in `register-companion.ps1` so both the direct companion path and the suite registration path share the same rejection rule. `install.ps1` should not duplicate registry-level validation beyond selecting or rejecting the deployable companion output before copy.

The validation gate must run before:

- `Write-Host "Registering companion: ..."`
- any registry `Set-ItemProperty`
- verification success output

## Error Handling

The user-facing rejection is intentionally direct:

`net48 Rook companion builds are not supported for registration; use the net7.0 Rook.rhp output.`

For missing files, preserve the existing `File not found: <path>` behavior. A non-existent explicit fake path does not need to produce the `net48` message in production. Tests that assert the `net48` rejection should create a temporary fake `Rook.rhp` under a `net48` path so validation reaches the intended branch after path existence checks.

`install.ps1` should record the hard failure through its existing `Add-InstallError` summary path, so JSON/dry-run consumers keep the current result contract.

## Tests

Add lightweight PowerShell/script regression coverage.

Text scan guard:

- Assert `install.ps1` no longer contains automatic fallback path strings such as `bin\Release\net48\Rook.rhp`.
- Assert `scripts/register-companion.ps1` no longer contains `net48` in the repo build candidate array.
- Do not forbid every `net48` mention, because comments and validation error text may legitimately mention it.

Release-package guard:

- Create a temporary release-package-shaped directory containing `plugin\Rook.rhp` without `plugin\Rook.runtimeconfig.json`, or with a runtimeconfig whose `runtimeOptions.tfm` is not `net7.0`.
- Exercise the companion package validation path directly if extracted, or through the smallest script entry point that can run without touching Rhino registry state.
- Assert the package companion is rejected before deployment.

Explicit registration rejection:

- Create a temporary directory ending in `net48`.
- Create an empty fake `Rook.rhp` in that directory.
- Invoke `scripts/register-companion.ps1 -RhpPath <temp>\net48\Rook.rhp`.
- Assert non-zero exit and the exact rejection message.
- The test should also make clear that registry writes did not happen for this fake path, either by validating the script exits before registry operations or by using a temporary path that never reaches those operations due to the validation gate.

Existing verification:

- `dotnet build src\Rook\Rook.csproj -f net7.0 -c Release`

Native build verification is not required for this issue because the change is restricted to managed companion selection and registration scripts.

## Acceptance Criteria

- `install.ps1` cannot reuse, build-success-select, or dry-run-plan a known repo `net48` companion output.
- `install.ps1` cannot deploy a release-package `plugin\Rook.rhp` unless adjacent runtime metadata identifies it as `net7.0`.
- `scripts/register-companion.ps1` cannot auto-discover a `net48` companion output.
- `scripts/register-companion.ps1 -RhpPath <path-with-net48-segment>\Rook.rhp` fails before any registry write.
- The `net48` rejection uses exact path-segment matching, case-insensitive.
- The rejection message is clear and identical across validation sites.
- Script regression coverage pins both automatic fallback removal and explicit `net48` rejection.
