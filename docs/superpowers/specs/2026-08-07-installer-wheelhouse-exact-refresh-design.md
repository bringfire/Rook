# Installer Wheelhouse Exact Refresh Design

**Date:** 2026-08-07
**Status:** Proposed
**Release:** Rook 1.5.18 prerequisite
**Base:** `02918747d38412419954c86fa3167a421eadfea4`

## Problem

The 1.5.18 installer built from the pinned base installed successfully, and both
installed Python environments passed their version, import, and dependency
checks. The sealed source wheelhouse contained 103 files, but the installed
`%LOCALAPPDATA%\Rook\app\python-wheelhouse` contained 106 files. Three wheels
from older releases survived the upgrade:

- `huggingface_hub-1.26.1-py3-none-any.whl`
- `pydantic_settings-2.14.2-py3-none-any.whl`
- `rook_mcp-1.5.17-py3-none-any.whl`

The installer currently copies the sealed wheelhouse over the installed
directory. It does not remove files that are absent from the new payload. The
locked installation selected the correct wheels, so this did not break the
installed runtime, but it violated exact release-payload provenance.

## Decision

Treat `{app}\python-wheelhouse` as an installer-owned sealed payload. Whenever
the `mcp` or `chirp` component is selected, remove that exact directory before
the existing wheelhouse copy runs:

```iss
[InstallDelete]
Type: filesandordirs; Name: "{app}\python-wheelhouse"; Components: mcp chirp
```

The existing `[Files]` entry remains the replacement operation:

```iss
Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion
```

Inno Setup processes `[InstallDelete]` before `[Files]`. Matching component
conditions therefore make this one paired operation:

- `mcp` or `chirp` selected: exact-delete the owned directory, then install the
  current sealed wheelhouse.
- neither selected: neither delete nor copy the wheelhouse.

This applies on every install or repair run that selects either Python
component. Deletion failures use Inno Setup's existing file-operation error
handling; this correction does not add a custom failure path.

## Scope

Implementation changes exactly two files:

- `installer/RookSetup.iss`
- `scripts/tests/release-installer-guards.tests.ps1`

The guard must prove:

- `[InstallDelete]` precedes `[Files]`.
- The exact `{app}\python-wheelhouse` directory is deleted once with
  `Type: filesandordirs`.
- The deletion and replacement copy both use exactly `Components: mcp chirp`.
- The replacement copy remains present exactly once.
- No wildcard, parent-directory deletion, Pascal cleanup function, or
  post-install cleanup is introduced.

## Preservation Boundary

Do not change or remove:

- installed `.env` files;
- Python virtual environments;
- the private CPython runtime;
- installed lockfiles or the runtime manifest outside their existing copy
  behavior;
- Rook data, configuration, caches, or sibling application directories;
- local deployment behavior;
- installer component definitions;
- dependency versions, lockfiles, source code, or release version fields.

Do not add a generalized synchronization framework. The wheelhouse is the only
directory admitted to exact recursive deletion in this correction.

## Verification and Release Consequence

Permanent verification is the focused source guard plus the existing release
installer guard suite.

Acceptance must rebuild the installer from the prerequisite's immutable merge
SHA, install it over the current affected 1.5.18 installation, and prove:

- the three observed stale wheels are absent;
- source and installed wheelhouse relative-file inventories are identical;
- every corresponding wheel hash is identical;
- installed `rook-mcp==1.5.18`, `mcp==1.28.1`, and `chirp==0.1.0` remain correct;
- `pip check` passes in both installed environments.

The installer already built from `02918747` remains diagnostic evidence only.
It must not be published. Native, managed, RookBIM, Python payload, and
installer artifacts must be rebuilt from the new merged source SHA before live
host acceptance and public promotion resume.

## Rejected Alternatives

1. **Unconditional deletion** is one line but can remove a valid wheelhouse in
   a plugins-only run without reinstalling it.
2. **Post-install Python cleanup** adds ordering and failure complexity after
   payload mutation has begun.
3. **Keeping the overlay** leaves stale release objects and defeats exact
   provenance.

The component-scoped declarative deletion is the smallest correction that
keeps deletion and replacement inseparable.
