# Dev-Infra: Reproducible Local Deploy + CI Guardrail (Spec)

> **Status:** Draft for review (on branch `chore/dev-infra`). This is Layer B (reproducible
> provisioning + local deploy) with a Layer C (CI guardrail) outline. Authored 2026-06-17 after a
> full desktop-provisioning session exposed the gaps below.

## Goal

`main` is always in a state both dev machines (laptop `aryan`, desktop `bring`) can **build,
locally deploy, test in Rhino + Revit, and package into an installer — identically**. No change
reaches `main` that works only because of one machine's local state. Dependency drift, installer-
packaging drift, and local-deploy drift are caught **before** merge.

## Non-Goals

- Running live Rhino/Revit *functional* tests in CI (Rhino can't run headless cheaply; full Revit
  functional testing stays on the dev machines). CI covers build + unit + packaging.
- Re-architecting the installer. We fix the dev-deploy + provisioning path and add a guardrail.
- Changing the chat-selector slice (separate branch).

## Background: what this session exposed

Provisioning the `bring` desktop surfaced a cascade of machine-specific assumptions. Each is a
concrete bug with a concrete fix. The through-line: **local deploy + provisioning is neither
machine-agnostic nor enforced.**

## Part 1 — Reproducible local deploy (`scripts/deploy-local-testing.ps1` + launcher)

Bug inventory (all observed 2026-06-17 on a clean desktop), each with the fix:

1. **Missing `post_install` sibling modules.** Line ~392 copies `installer\post_install.py` but
   not its imports `process_rebuild_guard.py` / `python_runtime_install.py` → `ModuleNotFoundError`.
   **Fix:** copy all top-level `installer\*.py` modules to `InstallRoot`.

2. **`post_install` requires a bundled private Python runtime** (`…\Rook\python\cpython-3.11.9`)
   the full installer ships but the dev deploy doesn't → MCP-venv step exits 1, fails the whole
   deploy. **Fix:** a dev/`-SkipRuntimeInstall` path that reuses the existing managed/repo venv
   instead of the private runtime; or make `post_install` fall back to an existing venv under
   `%LOCALAPPDATA%\Rook\venv` rather than hard-failing.

3. **OCCT runtime DLLs not deployed.** The payload-deploy step never copies the OCCT `TK*.dll`
   next to `RookNative.rhp`, so the OCCT-linked native won't load. **Fix:** in the payload step,
   copy the documented load closure (TKernel TKMath TKG2d TKG3d TKGeomBase TKGeomAlgo TKBRep
   TKTopAlgo TKPrim TKShHealing TKBO) from `$(OcctRoot)\win64\vc14\bin` into the plugin dir.

4. **Chat manifest written to the wrong directory.** Deploy writes `RookChatService.json` to the
   **parent** plugin dir, but `ChatServiceManager.GetManifestPath()` reads it from the **loaded
   TFM subdir** (e.g. `net8.0\`). The subdir has none → the companion **auto-generates** one.
   **Fix:** write `RookChatService.json` into each TFM subdir (net48/net7.0/net8.0), matching the
   one the loaded plugin actually reads.

5. **Auto-gen prefers the release install over the dev repo.** `TryAutoGenerateManifest` picks a
   root by priority `ROOK_PROJECT_ROOT → ancestor .mcp.json → release install root`. On a dev box
   with no `ROOK_PROJECT_ROOT` and a plugin dir under `AppData\McNeel` (no repo ancestor), it
   falls to the **release install root** → emits a `ROOK_MODE=release` manifest → a stale `rook`
   without `/agent/chat/models` → 404 (this is what blanked the model selector). **Fix:** dev
   deploy sets `ROOK_PROJECT_ROOT` to the repo; and/or reorder auto-gen to prefer a detected repo
   checkout over the release root when one is present.

6. **Wrong-TFM registration.** Deploy registers `net7.0\Rook.rhp` but Rhino 8 loads the **net8.0**
   companion. **Fix:** register the TFM matching the active Rhino runtime (net8.0 for current
   Rhino 8), or register all TFMs consistently.

7. **Launcher robustness (`ChatServiceManager.cs`).** Two chat servers spawn per launch; the
   manifest's pinned interpreter isn't honored (falls back to `where python` → system 3.10).
   **Fix:** single-spawn; honor the pinned `pythonPath`; don't silently fall through to
   `DiscoverPython()` when a pinned interpreter exists.

Acceptance for Part 1: on a clean machine with prerequisites present, **one** `deploy-local-testing`
invocation produces a loadable native (with OCCT DLLs), the correct-TFM companion, a dev chat
manifest in the right place, and a working chat server — no manual workarounds.

## Part 2 — OCCT made machine-agnostic

- **`OCCT_ROOT` convention on every machine** (done on both). The single source of truth for OCCT
  location; no machine depends on another's user path.
- **Neutralize the vcxproj hardcoded default** (`C:\Users\aryan\…` → `C:\OCCT\build-rook`) in
  `RookNative.vcxproj` + `OcctPrimitiveTests.vcxproj`. Safe now that both machines resolve via
  `OCCT_ROOT`. Its own tiny PR.
- **Codify "ship the OCCT *install* tree, never the build tree."** Build-tree `inc\` headers are
  absolute-path forwarders into the source checkout and are non-relocatable. Provide a documented
  "make relocatable OCCT install" step (cmake `--install`, or resolve forwarders → real headers)
  that yields `inc` + `win64\vc14\{lib,bin}`.

## Part 3 — `AGENT_SETUP.md` fresh-machine checklist

Canonical, reproducible bring-up for any new machine (or a wipe):
- VS 2022 + C++ workload (`VC.Tools.x86.x64`); dotnet; Revit (for RookBim, with its install path).
- Repo venv via `uv` (mcp_server).
- OCCT install tree at `C:\OCCT\build-rook` + `setx OCCT_ROOT`.
- `setx ROOK_PROJECT_ROOT <repo>` (so the chat runtime resolves to the dev tree).
- The one deploy command + the verify steps (rhino_ping, OCCT smoke, chat `/models` 200).

## Part 4 — CI guardrail (Layer C outline)

GitHub Actions on every PR; branch protection on `main` requires green.

- **Native build** — the TFM Rhino loads (net8.0). Needs OCCT: **restore a cached relocatable
  OCCT install artifact** (the 35 MB install tree produced this session) from Actions cache or a
  release asset, set `OCCT_ROOT`, build. *This cached-artifact approach is the key enabler — it
  avoids a 30–60 min OCCT source build per CI run.*
- **Managed build** — companion (all TFMs) + RookBim built against **Revit reference assemblies**
  (RookBim.csproj already parameterizes `-RevitInstallDir`; CI uses a reference-assembly NuGet or
  stub, not a full Revit install).
- **Test** — C# (xUnit) + Python (pytest) suites.
- **Packaging gate** — build the Inno Setup installer (`ISCC` on `installer\RookSetup.iss`) so
  packaging breakage is caught at PR time.
- **Deploy smoke** (optional/cheap) — static validation that the deploy script copies the files it
  must (OCCT DLLs, post_install modules, TFM manifests) — i.e. regression tests for the Part 1 bugs.
- **Hard parts, decided:** OCCT in CI → cached install artifact (solved). Revit in CI → build
  against reference assemblies; functional Revit testing stays on dev machines. Rhino in CI → not
  run; live Rhino smoke stays on-machine. CI's job is to prevent *build/dependency/packaging/
  deploy* drift, not to replace on-machine functional verification.

## Part 5 — Process (Layer D)

Branch-per-task → PR → review → CI-green-before-merge; both machines track the same `main`. Short
`CONTRIBUTING`/AGENTS note codifies it.

## Sequencing

1. **Part 1** deploy-script + launcher fixes — highest leverage; makes both machines deploy
   cleanly and removes today's manual workarounds. Each fix should land with a deploy-smoke
   regression check.
2. **Part 2** OCCT default cleanup (tiny PR) + the "install tree" doc.
3. **Part 3** `AGENT_SETUP.md`.
4. **Part 4** CI, built on 1–3 (and the cached-OCCT artifact from Part 2).

## Open questions for review

1. Dev deploy vs private runtime (bug #2): add a `-SkipRuntimeInstall`/dev flag, or make
   `post_install` fall back to an existing venv? (Affects whether dev boxes ever need the bundled
   cpython.)
2. Auto-gen reorder (bug #5): is preferring a detected repo checkout over the release root on dev
   machines acceptable, or do we keep release-priority and rely solely on `ROOK_PROJECT_ROOT`?
3. CI native build: cache the OCCT install tree in **Actions cache** vs a **versioned release
   asset** (the latter is more durable across cache evictions and shareable with dev machines).
4. Scope of the first PR: all of Part 1 at once, or one bug-fix-per-PR with its deploy-smoke check?
