# Legacy RUI surface suppression acceptance

Date: 2026-08-02

Decision: **PASS**. The reviewed candidate stopped loading, building, deploying, and registering the legacy `Rook.rui` surface; removed exact stale installed artifacts through every supported owner; and preserved the existing managed panel-command boundary in standalone Rhino and Rhino.Inside.Revit.

## Provenance and scope

- Base: `f22904c21474b616e2fe3487f686c5632bba8a37`
- Approved specification: `92d7c1581a8b26f978f8aee3aa18dea9c1f23059`
- Approved plan: `9f74a2ac1e30f5b72493e38b785574dd1206d141`
- Source/deployment implementation: `95748f88`
- Installer/release implementation: `baf9542c5aead902cf0142c603b6825e7e40f560`
- Accepted product head: `baf9542c5aead902cf0142c603b6825e7e40f560`

The candidate retains the dormant source RUI and does not change native code, RookBIM behavior, Python product code or dependencies, panel implementations, versions, or historical documents. RS-02 panel content, focus, sizing, and WebView behavior were explicitly outside this acceptance.

## Automated and build gates

- Exact pre-acceptance 14-path allowlist: pass.
- Focused managed lifecycle and panel-host tests: 42 passed.
- Source/local deployment guard: pass.
- Release-installer guard: pass.
- Initial deployment-owner TDD gates: 20 managed tests and the focused PowerShell guards passed.
- Repository-wide suite: not run, as required by the approved plan.
- Initial no-deploy `Rook.csproj` Release build: succeeded with 266 existing warnings and zero errors.
- Final companion Release rebuild: succeeded with 467 existing warnings and zero errors.
- `RookBim.csproj` was rebuilt after the final companion build: succeeded with zero warnings and zero errors.
- No managed Release output contained `Rook.rui`.

The unchanged native project was built only to stage the required installer payload, using MSVC toolset `14.44.35207`. `RookNative.rhp` was 4,553,728 bytes with SHA-256 `D4324746D14FC65468B6B0D75640D3187E04F2E2691BCB05D12EFE34EF0521BB`. No native source or project file changed.

## Deployment-owner migration

Each owner was tested against exact seeded legacy files in the `net8.0`, `net7.0`, and `net48` runtime children and an exact `RuiFile` registry value:

1. MSBuild auto-deploy removed all three files and deliberately left registry ownership unchanged.
2. `deploy-local-testing.ps1 -SkipBuild -SkipChirpInstall` removed all three files and the registry value.
3. `install.ps1 -SkipNative -SkipChirp -SkipConfig -Json` removed all three files and the registry value, and reported no companion deployment or registration error. Its non-success shell status reflected the requested partial-install flags, not a RUI failure.

The final `Rook.csproj` build was followed by the required RookBIM rebuild; no later companion rebuild invalidated the packaged net48 module.

## Release payload and installer

The pinned CPython 3.11.9 runtime and locked 1.5.16 wheelhouse were staged without tracked changes. Validation covered temporary imports, package compatibility, audits, and `pip check`. The manifest recorded Rook `baf9542c5aead902cf0142c603b6825e7e40f560`, Chirp `2eedab6c9aaa19e458cbd939889e980f781445f3`, and release `1.5.16`; the lock contained `mcp==1.28.1` and no MCP 2.x wheel.

- Installer: `installer/output/Rook-Setup-1.5.16.exe`
- Size: 245,047,760 bytes
- SHA-256: `EA99495F8EE357167460B6C4FF90534CC2BFD4070E53012C8AAB93377CF7A5A9`
- Source-path checklist: pass.

Four host-closed seeded migration-state checks passed:

1. Candidate install from an absent legacy state did not create RUI state.
2. Plugin-selected installation removed seeded legacy files and registry state.
3. Plugin-selected repair/idempotence removed reseeded legacy state.
4. Plugin-deselected installation still removed seeded legacy state.

These are bounded seeded-state checks, not claims of a literal clean-machine installation or an actual previous-version upgrade.

The installer source has a pre-existing hard-coded sibling `Chirp` path assumption. Compilation used a verified, temporary exact junction to the clean approved Chirp checkout; the junction was removed after compilation. Generalizing that release path is separate hygiene work and was not added to this candidate.

## Standalone Rhino acceptance

The standalone ping-only harness passed against the installed candidate with a 120-second cold-start allowance: ping returned `pong`, the smoke process exited `0`, cleanup was `graceful_exit`, and no host remained. The plan's default 30-second attempt expired before cold Rhino startup completed; host logs showed initialization continuing beyond that window. The unchanged candidate then passed under the bounded longer readiness window.

The installed companion self-report identified standalone Rhino, `net8.0`, completed local startup, a registered Grasshopper bridge, and registered panels. `_ShowRookChat`, `_ShowRookKnowledgeGraph`, and `_ShowRookVision` were each recognized and invoked to the existing command boundary, followed by verified idle recovery. The generic command route retained its existing fail-closed `native_command_prompt_unknown` or `native_command_bare_no_effect_unverified` receipts; this candidate neither changes nor interprets those receipts as panel-content verification.

No Rook toolbar, missing-RUI prompt, or toolbar-load warning was observed.

## Rhino.Inside.Revit acceptance

Against exactly one admitted Revit-owned discovery record:

- `GET /ping`: pass.
- `GET /bim/status`: pass.
- `GET /bim/active-document`: pass; its model-sensitive payload was discarded and is not retained here.
- Companion self-report: `processName=Revit`, `rhinoInside=true`, `runtimeChild=net48`, `targetFramework=.NETFramework,Version=v4.8`, `deferredLocalStartupComplete=true`, `startupComplete=true`, `bridgeRegistered=true`, and `panelsRegistered=true`.
- `_ShowRookChat`, `_ShowRookKnowledgeGraph`, and `_ShowRookVision`: recognized and invoked to the same existing boundary with verified idle recovery.

The user observed no missing-RUI indication. The existing Rook Chat panel opened, its health checks succeeded, and the knowledge graph request succeeded. This is bounded panel-registration/invocation parity; it is not an RS-02 panel-quality acceptance.

An unrelated third-party Grasshopper assembly load error and a dormant RookRoads startup message appeared in host output. Neither originated in this changed surface, affected the RUI checks, or authorized adjacent repair work.

## Final state

- Installed `Rook.rui` files in all three runtime children: absent.
- Companion `RuiFile` registry value: absent.
- Rhino, Revit, and Grasshopper processes: zero.
- Rook MCP processes: zero.
- Candidate worktree before this evidence commit: clean.
- Rollback: not required.

The acceptance result is therefore **PASS** for legacy RUI surface suppression and exact migration cleanup, with preserved command registration and invocation parity at the pre-existing managed panel boundary.
