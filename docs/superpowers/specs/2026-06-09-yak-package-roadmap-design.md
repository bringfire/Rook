# Rook Yak Package Roadmap Design

Date: 2026-06-09
Status: Design approved for implementation planning

## Objective

Make Yak the desired public install path for Rook while retaining the current installer as a fallback until Yak proves the full Rook lifecycle on clean machines, upgrades, repair, rollback, and uninstall.

Yak is not treated as "Inno Setup inside Rhino." Yak owns the immutable, versioned payload. Rook owns an idempotent bootstrap and doctor layer that creates, updates, and repairs the writable runtime under `%LOCALAPPDATA%/Rook`.

## Target Architecture

```text
Yak package = immutable versioned payload + embedded Python seed + locked wheelhouse
%LOCALAPPDATA%/Rook = active runtime, data, logs, config, repair state
```

The Yak package owns the immutable runtime seed, including the embedded Python distribution and locked wheelhouse. Rook bootstrap owns the writable active runtime under `%LOCALAPPDATA%/Rook`, with a stable launcher path used by MCP clients.

MCP clients must never point directly into Yak's versioned package folder. They point to a stable Rook launcher under `%LOCALAPPDATA%/Rook/bin`, which resolves the current active runtime and package manifest.

## Package Shape

The first representative Windows package should target Rhino 8 on Windows and use Yak-compatible top-level plugin layout:

```text
manifest.yml
RookNative.rhp
net8.0/
net7.0/
net48/
app/
  mcp_server/
  chirp/
  knowledge/
  scripts/
  ffmpeg/
  python-seed/
  wheels/
  bootstrap/
```

Mutable runtime state stays outside the Yak package:

```text
%LOCALAPPDATA%/Rook/
  bin/
    rook-mcp.cmd
    rook-doctor.cmd
  runtime/
    current.json
  runtimes/
    <runtime-id>/
  data/
  logs/
  config/
  discovery/
```

The current installer remains available during the transition, but the Yak roadmap should treat this layout as the desired public install model once validation passes.

## Python Runtime Direction

The roadmap stops debating whether Rook should bundle Python. The target is a Rook-owned Python seed in the Yak package.

Primary Phase 2 candidate:

```text
python-build-standalone
  x86_64-pc-windows-msvc
  standard shared Windows build, not static
  pinned Python minor version
  ABI-locked wheelhouse
```

`python-build-standalone` is the first candidate because the standard Windows MSVC builds behave like official Python for Windows distributions and can load extension modules. Static Windows builds are explicitly out of scope because they are brittle and known to have incompatibilities.

Comparison candidate:

```text
official Windows embeddable Python package
```

The embeddable package is a comparison path only. Python's Windows documentation describes it as minimal, with restricted path behavior, no bundled pip, and no support for managing dependencies with pip like a regular Python installation. It may still be useful to document rejection or a narrow viable path.

Fallback:

```text
CI-built preassembled Rook runtime image
```

This becomes the fallback architecture if `python-build-standalone + locked wheelhouse` is brittle under Rook's dependency load.

## Review Gates

### Gate 1: Yak Feasibility

Build a representative Yak package, not a toy package. It must include the RookNative plugin, managed companion payloads, FFmpeg, MCP source, Chirp source, knowledge, scripts, Python seed placeholder or real seed, and representative wheelhouse weight.

Acceptance criteria:

- Package installs locally through Yak.
- `RookNative.rhp` is discoverable and loadable by Rhino after restart.
- Package layout in Rhino's package folder is documented.
- Package size around the current 221 MB payload is accepted locally and by the Yak test server, or a McNeel-confirmed limit is recorded.
- `yak list`, `yak install`, `yak update`, and `yak uninstall` behavior is documented.
- No public default install path changes yet.

Senior review focus:

- Yak manifest correctness.
- Plugin load path and Rhino package discovery.
- Whether the package layout violates Yak top-level plugin expectations.
- Evidence for package size viability.

### Gate 2: Runtime Seed

Prove the Rook-owned Python seed strategy.

Acceptance criteria:

- `python-build-standalone` standard `x86_64-pc-windows-msvc` distribution is pinned by Python minor version and checksum.
- Static Windows builds are excluded.
- Wheelhouse is platform and ABI specific, using pinned `cp3xx-win_amd64` wheels.
- No source builds are allowed.
- Normal setup uses no PyPI and no user-installed Python.
- Missing wheel or hash mismatch fails explicitly with actionable doctor output.
- Official embeddable Python comparison is documented.
- Preassembled runtime fallback criteria are explicit.

Senior review focus:

- Dependency activation under Rook's real MCP dependency load.
- Native wheel import behavior.
- DLL loading and VC runtime requirements.
- Antivirus/signing friction.
- License obligations for redistributing Python, wheels, FFmpeg, and bundled runtime artifacts.

### Gate 3: Bootstrap And Doctor

Convert current post-install responsibilities into an idempotent bootstrap/doctor layer callable from Rook startup, a Rhino command, and the stable MCP launcher.

Acceptance criteria:

- Bootstrap creates `%LOCALAPPDATA%/Rook/bin`, `runtime/current.json`, `runtimes/<runtime-id>`, `data`, `logs`, `config`, and `discovery`.
- Bootstrap copies or materializes the active runtime from Yak's immutable seed.
- Runtime identity includes Rook version, Python version, wheel lock hash, platform, and bootstrap schema version.
- Existing compatible runtimes are reused.
- Incompatible runtimes are preserved or retired predictably.
- Deleted or corrupted runtime state repairs without reinstalling Yak.
- Doctor reports precise failure categories and next actions.

Senior review focus:

- Idempotency.
- Partial failure recovery.
- Versioned runtime state rather than a forever single `venv`.
- Clear separation between immutable Yak payload and writable LocalAppData state.

### Gate 4: Legacy Inno Migration

Treat migration as a top risk, not a late cleanup task. Legacy AppData plugin folders, registry paths, and duplicate plugin IDs can break Yak loading before Rook gets a chance to repair itself.

Acceptance criteria:

- Yak-installed Rook detects legacy Inno install artifacts.
- Duplicate plugin IDs and stale Rhino plugin paths are identified.
- Migration either safely removes legacy load paths or gives precise cleanup instructions.
- Existing user data is preserved.
- Rollback from Yak to the current installer remains possible during transition.

Senior review focus:

- Rhino plugin registration semantics.
- Failure mode when both Yak and legacy AppData payloads exist.
- Whether migration can run early enough to prevent load conflicts.
- User data preservation.

### Gate 5: MCP And Connector Launch

Make the MCP launch path stable across Yak updates.

Acceptance criteria:

- Claude, Codex, and other MCP clients point only at `%LOCALAPPDATA%/Rook/bin/rook-mcp.cmd` or an equivalent stable launcher.
- Launcher resolves `runtime/current.json` and starts the active Rook MCP server.
- Launcher can run bootstrap/doctor before starting MCP.
- If Yak/Rook is missing, the failure points users or agents at a repair/install path.
- Client registrations survive Yak package updates.

Senior review focus:

- No client config contains versioned Yak paths.
- Stdio behavior remains compatible.
- Environment variables preserve the current release contract, including `ROOK_MODE`, `ROOK_INSTALL_ROOT`, and `ROOK_DATA_DIR` semantics or a documented successor.
- Failures are repairable by agents without requiring users to understand Python internals.

### Gate 6: Update, Rollback, And Uninstall

Prove the full lifecycle before Yak becomes the default public path.

Acceptance criteria:

- Yak update replaces the immutable payload.
- Bootstrap detects package/runtime version changes.
- Compatible runtimes are reused and incompatible runtimes are rebuilt.
- Rollback to a previous Yak package is understood.
- Yak uninstall removes the immutable package while intentionally preserving user data unless a separate cleanup command is run.
- Rook cleanup behavior is documented separately from Yak uninstall behavior.

Senior review focus:

- State transitions in `runtime/current.json`.
- User data preservation.
- Clear uninstall messaging.
- No orphaned client registrations without repair guidance.

### Gate 7: Clean-Machine Smoke

Yak cannot become the primary public path until clean-machine smoke passes.

Acceptance criteria:

- Clean Windows machine with Rhino 8 installs Rook through Yak.
- Rhino restarts and loads `RookNative`.
- Managed companion loads on demand.
- MCP launcher initializes LocalAppData runtime without user Python.
- `python -m rook` equivalent MCP startup works through the stable launcher.
- Rook discovers the native plugin through LocalAppData discovery.
- FFmpeg, Chirp, knowledge, chat, and representative MCP tools are available.
- Offline install path works after acquiring the Yak package and required package-manager metadata.
- Deleted runtime repair works.
- Update from previous Rook works.
- Uninstall/reinstall works.

Senior review focus:

- Evidence quality from a real machine, not inferred success.
- Logs and diagnostics captured for every failed smoke.
- Whether docs match actual user steps.

### Gate 8: Mac Follow-Up

Mac remains in the architecture but does not block Windows.

Acceptance criteria:

- Separate `rh8_0-mac` package plan exists.
- Mac-native Python seed, FFmpeg, paths, signing/notarization, RhinoCommon/native compatibility, and wheelhouse strategy are treated as independent validation items.

Senior review focus:

- No accidental Windows assumptions in shared bootstrap contracts.
- Clear separation between Windows release readiness and Mac research.

## Risks

- Yak may have undocumented practical limits for package size or upload behavior.
- Python runtime seed may pass simple imports but fail under Rook's full dependency load.
- Legacy Inno artifacts may cause plugin load conflicts before repair logic can run.
- MCP client registrations may become stale if they point at versioned payload paths.
- VC runtime, DLL search order, antivirus, signing, or FFmpeg licensing issues may affect clean-machine installs.
- Mac support may require a separate runtime architecture.

## Non-Goals

- Replace the current installer immediately.
- Move mutable runtime state into the Yak package folder.
- Require user-installed Python.
- Require PyPI during normal setup.
- Point MCP clients into Yak versioned package folders.
- Modify RookNative, managed companion, or MCP server behavior as part of this design document.

## References

- Yak package anatomy: https://developer.rhino3d.com/guides/yak/the-anatomy-of-a-package/
- Yak multi-target packages: https://developer.rhino3d.com/guides/yak/creating-a-multi-targeted-rhino-plugin-package/
- Yak CLI reference: https://developer.rhino3d.com/guides/yak/yak-cli-reference/
- Yak installing and managing packages: https://developer.rhino3d.com/guides/yak/installing-and-managing-packages/
- Yak package server: https://developer.rhino3d.com/guides/yak/the-package-server/
- python-build-standalone running distributions: https://gregoryszorc.com/docs/python-build-standalone/main/running.html
- python-build-standalone repository: https://github.com/astral-sh/python-build-standalone
- Astral stewardship note: https://astral.sh/blog/python-build-standalone
- Python embeddable package documentation: https://docs.python.org/3/using/windows.html#the-embeddable-package
