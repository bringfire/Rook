# Rook 1.5.17 Release Hygiene Design

Date: 2026-08-03

Status: approved boundary awaiting written-spec review

Baseline: `6eacc2e1fc2a77c73dda0f54b5dd6558a0cd9465`

## Goal

Make the existing Rook release workflow truthful and mechanically ready for a
separate `1.5.17` version-bump pull request. This change corrects release metadata,
active guidance, the build-release procedure, and its focused guards. It does not
change runtime behavior or produce release artifacts.

## Non-goals

- Do not bump any file to `1.5.17` in this pull request.
- Do not change runtime routing, tool schemas, Grasshopper behavior, RookBIM behavior,
  dependency versions, or lock resolution.
- Do not build, install, deploy, tag, or publish a release.
- Do not modify `bringfire/rook-release`; public promotion remains a later reviewed
  pull request.
- Do not merge or incorporate any currently open Rook pull request.
- Do not repair panel behavior, expand Wasp support, or reopen completed RUI,
  RoadCreator/RookRoads, or Grasshopper-cascade implementations.
- Preserve historical specifications, plans, reports, and archived documents.

## 1. Version and package metadata contract

The private release source has ten version-bearing files:

1. `mcp_server/pyproject.toml`
2. `mcp_server/uv.lock`
3. `installer/RookSetup.iss`
4. `src/Rook/Rook.csproj`
5. `src/RookBim/RookBim.csproj`
6. `src/RookNative/RookNative.rc`
7. `src/RookNative/RookNativePlugin.cpp`
8. `src/RookNative/RookServer.cpp`
9. `.claude-plugin/plugin.json`
10. `.claude-plugin/marketplace.json`

This hygiene pull request makes all ten agree on the current version `1.5.16`.
The later version-bump pull request must update all ten to `1.5.17`.

After changing `mcp_server/pyproject.toml`, the version-bump procedure regenerates
`mcp_server/uv.lock` and requires its diff to change only the local `rook-mcp`
project version. Any third-party package or hash movement stops the bump for review.

`build-rook-python-wheelhouse.ps1` must require an explicit semantic version. It
must not carry a default release version.

The two private Claude plugin manifests are promotion inputs. Their descriptions
must be client-neutral, must not advertise RoadCreator/RookRoads or general road
design, and must point to `bringfire/rook-release` as the public repository.

## 2. Active guidance contract

The following active documents are corrected without rewriting their unrelated
content:

- `README.md`
- `QUICK_START.md`
- `AGENT_SETUP.md`
- `mcp_server/README.md`
- `installer/pre-install-readme.txt`
- `BUILDING.md`

The Windows release installer bundles CPython 3.11.9 and therefore does not require
system Python. Source-development instructions may still state their actual Python
requirements.

Tool availability is profile-dependent. Active guidance must not advertise a stale
global tool count. It distinguishes the broad Claude profile from the Codex lean
profile and its progressive-discovery gateways.

`gh_edit` is a batched mutation request with operation-level outcomes, possible
partial success, scheduling evidence, and required verification. Active guidance
must not call the whole request atomic.

The supported release/build instructions do not build RookRoads. Removing that one
developer command does not delete or refactor dormant compatibility code.

## 3. Repository and update metadata contract

The public product, support, and update destination is
`https://github.com/bringfire/rook-release`.

The exact stale `bringfire/Rhino_AI` values are corrected in:

- `src/RookNative/RookNativePlugin.cpp`
- `src/Rook/Properties/AssemblyInfo.cs`
- `scripts/register-rooknative-suite.ps1`
- `scripts/register-companion.ps1`

The installer already owns the correct public values and remains unchanged. No
general metadata service or new abstraction is introduced.

## 4. Release workflow contract

The mirrored `.agents` and `.claude` build-release skills and their version-location
references remain byte-identical.

The workflow performs these bounded stages:

1. Run the focused release-surface and existing installer guards.
2. Merge a ten-file version-bump pull request.
3. Build every artifact from the exact resulting private `main` SHA.
4. Validate the wheelhouse, FFmpeg bundle, installer, and installed runtime.
5. Run standalone Rhino and Rhino.Inside.Revit/RookBIM acceptance.
6. Create and merge a separate reviewed promotion pull request in
   `bringfire/rook-release`, recording the private source SHA and artifact hashes.
7. Publish `vX.Y.Z` from `bringfire/rook-release`, targeting the reviewed public
   promotion commit and attaching the validated artifacts.

The private repository is source provenance; it is not the public release target.

## 5. Permanent focused guard

Add one small PowerShell release-surface guard under `scripts/tests/`. It fails when:

- the ten version-bearing surfaces disagree;
- the build-release inventory omits one of those surfaces;
- the wheelhouse builder has a default version;
- active installer guidance requires system Python;
- active guidance calls the full `gh_edit` request atomic or publishes a stale exact
  tool count;
- active metadata contains `bringfire/Rhino_AI`, unsupported road claims, or stale
  public repository URLs;
- the mirrored build-release skill/reference pairs differ;
- the workflow attempts to publish the public release in the private repository.

The guard reads files only. It does not load Rhino, build binaries, resolve
dependencies, contact GitHub, or mutate tracked state.

## 6. Roadmap evidence

Update the active release-surface roadmap to record the completed RoadCreator/RookRoads
containment, RUI suppression, and Grasshopper skill-cascade corrections. Record this
hygiene work as progress on active documentation, metadata, public promotion, upgrade
cleanup, contract wording, and release guards without falsely marking unfinished live
acceptance or public promotion complete.

## Verification

1. Run the new guard before implementation and require it to fail on the identified
   baseline mismatches.
2. Run it after implementation and require success.
3. Run the existing release-installer guard suite.
4. Parse both Claude plugin manifests as JSON.
5. Run `uv lock --check` against `mcp_server` without changing `uv.lock`.
6. Verify mirrored build-release files byte-for-byte.
7. Run `git diff --check` and an exact changed-path allowlist.

No native, managed, Python product, installer, or live-host build is required because
this pull request changes metadata, documentation, release procedure, and guards only.
The eventual `1.5.17` candidate receives the complete build/install/live acceptance.
