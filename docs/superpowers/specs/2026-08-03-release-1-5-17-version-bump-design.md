# Rook 1.5.17 Mechanical Version-Bump Design

**Date:** 2026-08-03

**Design baseline:** `8baf325a459ec9bb53cae24b1af0fab452b3001e` (`origin/main`)

**Status:** Approved design, pending written-spec review

## Purpose

Create one mechanically reviewable pull request that changes Rook's declared release
version from `1.5.16` to `1.5.17`. Version truth comes first; artifacts, acceptance,
public promotion, and publication begin only from the resulting private merge commit.

The planning documents remain on their own planning branch. They are not included in
the version-bump pull request, whose changed-path contract is exactly ten files.

## Change boundary

The bump contains 14 version edits across exactly these ten files:

| File | Required edit |
|---|---|
| `mcp_server/pyproject.toml` | Package version |
| `mcp_server/uv.lock` | Generated local `rook-mcp` version plus the accepted `uv 0.11.3` marker normalization |
| `installer/RookSetup.iss` | `MyAppVersion` |
| `src/Rook/Rook.csproj` | Project version |
| `src/RookBim/RookBim.csproj` | Project version |
| `src/RookNative/RookNative.rc` | `FILEVERSION`, `PRODUCTVERSION`, `FileVersion`, and `ProductVersion` |
| `src/RookNative/RookNativePlugin.cpp` | Plug-in version |
| `src/RookNative/RookServer.cpp` | Server-reported plug-in version |
| `.claude-plugin/plugin.json` | Plug-in manifest version |
| `.claude-plugin/marketplace.json` | Marketplace metadata version and plug-in version |

No other file or field changes. Outside the generated lock normalization, avoid
incidental whitespace, ordering, or formatting movement. Commit the complete bump
atomically as one commit.

## Version and lock flow

Record the exact current `origin/main` SHA before editing and create the bump branch
from that commit. Change `mcp_server/pyproject.toml` to `1.5.17`; this is the canonical
version from which verification derives the expected value. Update every other
declared version field to match.

Never edit `mcp_server/uv.lock` manually. Use the installed official generator at
`C:\Users\aryan\.local\bin\uv.exe`, record its path, version, and SHA-256, and
require version `uv 0.11.3`. Run that binary normally after changing
`pyproject.toml`.

The accepted generated lock diff is exactly `60` deletions and `60` additions:

- one local `rook-mcp` version replacement from `1.5.16` to `1.5.17`; and
- 59 dependency-edge marker-normalization replacements.

For every marker replacement, removing only the `marker` attribute from the old and
new dependency edge must leave byte-identical package name, package version, source,
and dependency target text. No third-party package version, dependency target,
source, resolution, wheel, or hash may change. Any different generated movement
stops the work for review.

## Verification contract

Before committing and again at the reviewed head:

1. Derive `1.5.17` from `mcp_server/pyproject.toml` and require every other declared
   version field to match, including all four native resource values and both
   marketplace fields.
2. Require the changed-path set to equal the ten-file inventory above.
3. Use `git diff --numstat` against the recorded bump base and require this exact
   diff shape: each of the seven ordinary non-lock files reports `1` deletion and
   `1` addition; `src/RookNative/RookNative.rc` reports `4` deletions and `4`
   additions; `.claude-plugin/marketplace.json` reports `2` deletions and `2`
   additions; and `mcp_server/uv.lock` reports `60` deletions and `60` additions.
   The totals must be exactly `73` deletions and `73` additions.
4. Inspect every hunk in the normal Git diff. Outside `uv.lock`, every removed
   version token must be `1.5.16`, every added version token must be `1.5.17`, and
   no other content may change. In `uv.lock`, require exactly the one project-version
   pair and 59 marker-only pairs defined above. This is a review step, not a new
   script or versioning framework.
5. Inspect the lock structurally and require its sole semantic change to be the local
   `rook-mcp` version; the 59 additional pairs are serializer normalization only.
6. Check only the declared version fields for remaining `1.5.16`. Historical text and
   unrelated dependency versions are not searched or rewritten.
7. Run:
   - `scripts/tests/release-surface-hygiene.tests.ps1`
   - `claude plugin validate --strict .`
   - `uv lock --check --directory mcp_server`
   - `git diff --check`

Do not run the built-payload installer guard. This pull request produces no build
payload, and release builds begin only after the bump merges.

Any unexpected path, lock movement, version mismatch, or failed focused gate stops
the work. Do not repair unrelated failures or expand the pull request.

## Integration and provenance

Immediately before merge, refresh private `origin/main`. Compare its changes since
the recorded bump base against the ten-file inventory and require zero overlapping
paths. Require a clean synthetic merge. If either check fails, stop for review rather
than rebasing or absorbing unrelated work without approval.

Merge with a regular two-parent merge commit. After merging, verify:

- the first parent is the checked current private `main` commit;
- the second parent is the reviewed ten-file bump head; and
- private `origin/main` points to the merge commit.

Record that private merge SHA. It is the sole source provenance for builds,
installation, live acceptance, and artifact hashes.

Public provenance remains separate:

- the private merge SHA identifies source and artifacts;
- the later public promotion merge SHA identifies public plug-in, documentation, and
  release-note content; and
- the public release tag targets the reviewed public promotion commit while recording
  the private source SHA and validated artifact hashes.

## Explicitly out of scope

- Release notes or roadmap changes.
- Source, dependency, schema, behavior, test-harness, or documentation corrections.
- Builds, wheelhouse or runtime staging, installer compilation, installation,
  deployment, or live-host acceptance.
- Public `rook-release` changes, promotion, tags, or release publication.
- A reusable version-bump script or release-management framework.

Those activities occur only after this mechanical bump merges and must use the
recorded private merge SHA where source or artifact provenance is required.
