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
   deploy. **Fix (decided):** add an **explicit dev-runtime flag** to `deploy-local-testing.ps1`
   (e.g. `-UseRepoVenv` / `-DevPythonRuntime <path>`) that reuses the repo/managed venv. The full
   installer / `post_install` release path must still **fail loudly** if the bundled private
   runtime is missing — **no silent fallback** (silent fallback would mask release-packaging bugs).

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
   without `/agent/chat/models` → 404 (this is what blanked the model selector). **Fix (decided):**
   dev deploy writes `ROOK_PROJECT_ROOT` to the repo and manifest generation honors it. Do **not**
   broadly reorder auto-gen to prefer any detected repo over the release install — without a strong
   guard that risks release builds picking up a repo. With no `ROOK_PROJECT_ROOT`, the release
   install stays the release install.

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

- **`OCCT_ROOT` convention on every machine** — the target single source of truth for OCCT
  location; no machine depends on another's user path. `OCCT_ROOT` is **set (persistent) on both
  machines**, and both have built native with it set, but via an **inline** env var, not yet from
  a genuinely fresh shell that inherited the persistent value — so persistent-env fresh-shell build
  verification on both machines is still **pending**.
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

- **Native build** — the TFM Rhino loads (net8.0). Needs OCCT: restore the relocatable OCCT
  install artifact (the 35 MB install tree produced this session), set `OCCT_ROOT`, build. **The
  durable source of truth is a versioned release asset** (survives cache eviction, shareable with
  dev machines); **Actions cache is only an acceleration layer** keyed off the artifact version.
  *This is the key enabler — it avoids a 30–60 min OCCT source build per CI run.*
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

## Cross-machine effect & the explicit-inputs principle

These deploy changes affect **both** machines the same way — but only after they land in `main`
and each machine pulls them. The intended effect is positive: laptop and desktop both stop
depending on hidden local state and use the same deploy rules. Concretely:

- **OCCT:** both use `OCCT_ROOT` (laptop `C:\Users\aryan\…\build-rook`, desktop `C:\OCCT\build-rook`).
  The deploy reads the env var, so paths differ but behavior matches.
- **Python/chat runtime:** deploy explicitly uses the repo/dev runtime instead of accidentally
  falling back to an old release install — so neither machine tests stale chat code.
- **Manifest location:** deploy writes the chat manifest where the loaded companion actually reads
  it, so both launch the intended server.
- **TFM registration:** deploy registers the runtime Rhino actually loads, so the two machines
  don't silently load different companion builds.
- **OCCT DLL closure:** deploy copies the required `TK*.dll` beside the native plugin on both, so
  native-load behavior is reproducible.
- **Revit/RookBim:** each machine supplies its own Revit path; the build/deploy flow is identical.

**Design rule (load-bearing):** the risk is making deploy "too clever" so it silently falls back
to machine-specific paths. Prefer **explicit inputs** over magic: `OCCT_ROOT`, `ROOK_PROJECT_ROOT`,
explicit `RevitInstallDir`, explicit dev-runtime flag. The other machine is never *broken* — it
just needs those inputs set once, after which the **same command works on both**.

## Sequencing

1. **Part 1** deploy-script + launcher fixes — highest leverage; makes both machines deploy
   cleanly and removes today's manual workarounds. Shipped as the focused **PR 1–4 groups** above,
   each landing with its deploy-smoke regression check.
2. **Part 2** OCCT default cleanup (tiny PR) + the "install tree" doc.
3. **Part 3** `AGENT_SETUP.md`.
4. **Part 4** CI, built on 1–3 (and the cached-OCCT artifact from Part 2).

## Decisions (resolved 2026-06-17 review)

1. **Dev runtime:** explicit dev-runtime flag (`-UseRepoVenv`/`-DevPythonRuntime`); **no silent
   fallback** — the release `post_install` path still fails loudly if the bundled private runtime
   is missing.
2. **Auto-gen:** rely on `ROOK_PROJECT_ROOT` for dev; do **not** broadly prefer a detected repo
   over the release install without a strong guard. No `ROOK_PROJECT_ROOT` → release stays release.
3. **CI OCCT artifact:** a **versioned release asset** is the durable source of truth; Actions
   cache is acceleration only.
4. **PR scope:** focused, reviewable groups — **not** all of Part 1 at once.

### PR grouping (decided)

- **PR 1 (runtime/manifest group):** copy all `installer/*.py` modules needed by `post_install`
  (bug 1); explicit dev-runtime flag (bug 2); write the chat manifest into the loaded TFM subdirs
  + set `ROOK_PROJECT_ROOT` in dev deploy (bugs 4 + 5); deploy-smoke checks for all of these.
- **PR 2:** OCCT DLL deploy closure (bug 3) + its deploy-smoke check.
- **PR 3:** TFM registration fix (bug 6).
- **PR 4:** launcher robustness — single-spawn + honor the pinned interpreter (bug 7).
