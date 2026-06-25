# Installer Net8 Registration Anchor Design

## Goal

Move the Rhino 8 standalone companion registration anchor from the `net7.0` managed companion payload to the `net8.0` managed companion payload, while preserving the existing multi-runtime payload packaging.

This is a focused installer correctness slice so other installer work can build on the intended main behavior without mixing unrelated changes.

## Current Problem

The installer packages managed companion payloads for:

- `net8.0`
- `net7.0`
- `net48`

But the Rhino plugin enumeration metadata currently registers the managed companion `RuiFile` and `PlugIn\FileName` against the `net7.0` child payload. That makes `net7.0` look like the direct standalone Rhino anchor even though the installer already treats `net8.0` as the .NET 8 runtime payload required for standalone Rhino and Rhino.Inside/Revit .NET 8 hosts.

## Design

Change only the installer registration anchor and the guard tests around it.

In `installer/RookSetup.iss`:

- Set companion registry `RuiFile` to `RookNative\net8.0\Rook.rui`.
- Set companion registry `PlugIn\FileName` to `RookNative\net8.0\Rook.rhp`.
- Set post-install companion registration verification to check `RookNative\net8.0\Rook.rhp`.
- Keep the explicit existence checks for `net8.0` and `net48` payloads.
- Update the missing-`net8.0` message so it names standalone Rhino as affected, not only Rhino.Inside/Revit.

In `scripts/tests/release-installer-guards.tests.ps1`:

- Assert the installer packages `net8.0`, `net7.0`, and `net48` companion `Rook.rhp` payloads.
- Assert `net8.0` is the standalone Rhino registration anchor.
- Assert `net7.0` is not the standalone Rhino registration anchor.
- Rename the net7 built-payload message from "registered-anchor" to "fallback" so the tests describe the intended role.

## Out of Scope

- No release version bump.
- No installer rebuild artifact committed.
- No change to which companion runtime folders are packaged.
- No removal of the `net7.0` payload.
- No change to native plugin registration.
- No change to Rhino.Inside/Revit `net48` checks.

## Review and Verification

The PR should contain only:

- this spec
- the implementation plan
- `installer/RookSetup.iss`
- `scripts/tests/release-installer-guards.tests.ps1`

Verification should include:

- the installer guard test script
- `git diff --check`
- a final diff review confirming no unrelated files entered the PR

The full release build and install smoke are not required for this PR because this slice changes installer registration text/paths and the existing guard script is the intended review gate.
