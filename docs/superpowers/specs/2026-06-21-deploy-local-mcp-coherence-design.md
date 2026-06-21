# Local Deploy MCP Coherence — `deploy-local-testing.ps1`

**Date:** 2026-06-21
**Type:** Local-deploy hardening (fixes two concrete defects tripped during the 2D→3D smoke)
**Branch:** `codex/deploy-local-mcp-coherence` (off `origin/main` `04a9b4c4`)

## Problem

Two defects in the **release-mode** path of `scripts/deploy-local-testing.ps1`
made a local deploy ship an MCP runtime that did not match its synced source —
and verify a different import path than it shipped.

### Defect 1 — source ↔ site-packages drift (the "lie")

- The deploy syncs `mcp_server` **source** into `%LOCALAPPDATA%\Rook\app\mcp_server`.
- `Invoke-PostInstallConfig` installs `rook` into the release venv **only from
  the bundled wheelhouse + lock** (offline). The local deploy **never rebuilds
  that wheel**, so `…\Rook\venv\Lib\site-packages\rook` is whatever the bundled
  wheel was — it can be older than the synced source (e.g. predating the
  reconstruction `rhino_2d_to_3d_*` tools).
- The **written** MCP config (`~/.claude.json` rook entry) has `PYTHONPATH: ""`
  — hardcoded empty in `installer/python_runtime_install.build_release_mcp_env`.
  So the real MCP imports `rook` from **site-packages** (the stale wheel) → the
  `rhino_2d_to_3d_*` tools are absent at runtime.
- The deploy's **own** RuntimeContract sets `$releasePythonPathEntries =
  @("…\mcp_server\src")`, and `Test-EffectiveRuntime` runs its check with
  `PYTHONPATH` = that src dir and asserts `rook.__file__` starts with
  `WorkingDirectory\src\rook`. So the deploy **verifies a source-tree import**
  while the shipped MCP uses site-packages. The check passes; the runtime is
  broken. Split-brain.

### Defect 2 — bootstrap python self-deletes its own interpreter

- `Resolve-BootstrapPython` returns the **first** candidate, which is
  `$VenvPython = …\Rook\venv\Scripts\python.exe` (the release venv).
- `Invoke-PostInstallConfig` runs `post_install.py` with that interpreter.
  `post_install` Step 1 → `_install_from_wheelhouse` → `_create_venv` calls
  `shutil.rmtree(venv_dir)` whenever `needs_venv_recreate` is true (payload/
  version bump) or on any first-attempt retry. Deleting the venv kills the
  running interpreter → silent **exit 1, no traceback**. Intermittent: only
  when a recreate is actually needed (e.g. deploying a newer commit).

## Decision

One tightly-scoped local-deploy-hardening change, **entirely inside
`deploy-local-testing.ps1`**, release-mode only. Remove the split-brain by
making the local deploy produce — and verify — the runtime shape it actually
ships: `rook` current in site-packages, empty `PYTHONPATH`, tools present.

## Scope (the slice)

1. **`Resolve-BootstrapPython` excludes the venv it may recreate.** Do not offer
   `$VenvPython` as a bootstrap candidate (post_install rmtree-recreates that
   venv). Keep the remaining candidates in order — system `python`
   (non-WindowsApps), `py -3`, then `%LOCALAPPDATA%\Programs\Python\Python3{14..10}`.
   If none resolve, keep the existing `throw "Python 3.10+ was not found."`.
   `-UseRepoVenv` / `-DevPythonRuntime` (`Resolve-DevPythonRuntime`) are a
   separate path and stay untouched.

2. **`Invoke-PostInstallConfig` still builds the release venv from the
   wheelhouse** — unchanged. (post_install.py and the wheelhouse/lock contract
   are out of scope.)

3. **New release-only step: mirror the synced source into the release venv
   site-packages.** After `Invoke-PostInstallConfig` succeeds, for release mode
   only, mirror the `rook` package directory:
   - source: `<InstallRoot>\mcp_server\src\rook`
   - dest: `<venvRoot>\Lib\site-packages\rook`

   **Why a mirror, not `pip install`:** `mcp_server/pyproject.toml` declares the
   **hatchling** build backend, which the release venv does not carry. A
   `pip install --no-build-isolation --no-index <source>` would fail (no backend,
   offline can't fetch one — verified). A directory mirror is deterministic,
   fully offline, and avoids build-backend/wheelhouse churn. Reuse the existing
   `Sync-Directory` (`robocopy /MIR`), which excludes `__pycache__`/`*.pyc` and
   **purges stale dest files** so old modules can't linger. Only the `rook`
   package dir is mirrored; the wheelhouse `rook-*.dist-info` sibling is left
   intact for metadata. Result: the importable `rook` (incl. `rook.server`) under
   `…\venv\Lib\site-packages\rook` is the current source.
   - **No internet fallback.** The mirror is offline by construction. If source
     or venv preconditions are missing, throw and stop — do not restore a
     `PYTHONPATH=src` shadow to paper over it.

4. **Release `PythonPathEntries = @()`.** Set the release RuntimeContract's
   `$releasePythonPathEntries = @()` so its `PYTHONPATH` is empty — matching the
   real MCP config. This flows to the chat-service manifest (already emits
   `PYTHONPATH = ''` for release) and to verification. Dev mode keeps
   `$devPythonPathEntries = @(<repo>\mcp_server\src)` unchanged.

5. **Verification tests the real path.** Change `Test-EffectiveRuntime` so that
   in **release** mode it runs with empty `PYTHONPATH` (falls out of #4) and
   asserts:
   - `rook.__file__` resolves **under** `<RuntimeRoot>\venv\Lib\site-packages\rook`
     (not `…\mcp_server\src\rook`), and
   - all **seven** `rhino_2d_to_3d_*` tools (`models, submit, jobs, status,
     cancel, result, import`) appear in the rook MCP server's advertised tool
     list (enumerate the registered tool names and assert membership) — matching
     the actual reconstruction preflight surface, not a subset.
   In **dev** mode it keeps the existing behavior (PYTHONPATH=src, assert import
   from `WorkingDirectory\src\rook`). The release branch is the guard that fails
   loudly if drift ever recurs.

5b. **Mode-branch the chat-manifest validation.** `Test-ChatServiceManifestAtPath`
   assumed `PythonPathEntries[0]` exists; with release now `@()` it would throw.
   Branch by mode: **dev** still requires `pythonPathEntries[0] == src`; **release**
   requires `pythonPathEntries` empty/absent **and** the manifest `environment.PYTHONPATH`
   empty/absent (matching the empty-PYTHONPATH MCP config).

6. **Dev runtime modes keep their source `PYTHONPATH`.** `-UseRepoVenv` /
   `-DevPythonRuntime` and the dev RuntimeContract are unchanged; dev is
   *meant* to import from the repo source tree.

## Out of scope (do not touch)

- `installer/python_runtime_install.py` (incl. `build_release_mcp_env`,
  `needs_venv_recreate`, wheelhouse/lock/hash validation).
- `post_install.py` and the offline-wheelhouse install path.
- Release installer packaging / the real (non-local) install flow.
- Dev runtime modes and their source-PYTHONPATH behavior.
- Any C#/native/MCP-tool code. No new dependencies.

## Testing / verification

This is a PowerShell deploy-script change; its load-bearing guards are the
in-script assertions, exercised by actually running a local release deploy:

- **Drift guard (primary):** the modified `Test-EffectiveRuntime` release branch
  — empty `PYTHONPATH`, `rook.__file__` under site-packages, `rhino_2d_to_3d_models`
  listed. A stale-wheel deploy now fails the deploy instead of shipping silently.
- **Bootstrap-python guard:** assert the resolved bootstrap interpreter is not
  `$VenvPython` (the venv about to be recreated) before invoking post_install.
- **Manual full-deploy validation** (the real proof, run by the user with Rhino
  + rook MCP stopped): a clean release deploy completes, and a from-scratch
  `python -m rook` (empty `PYTHONPATH`, release venv) advertises all seven
  `rhino_2d_to_3d_*` tools. Prerequisite reminder: VS Installer dir on PATH for
  the native build batch's bare `vswhere.exe`.

## Review notes (folded into the plan)

1. **Bootstrap exclusion compares normalized resolved paths.** Don't naive
   string-compare `$candidate -ne $VenvPython`. Resolve both paths when they
   exist and compare case-insensitively with normalized separators (Windows
   casing/slashes can otherwise let the same venv sneak back in).
2. **Mirror ordering is load-bearing:** the source mirror (#3) runs
   **after** the AppData payload sync (`Sync-AppPayload`, so the current source
   is present in `…\app\mcp_server`) **and after** `Invoke-PostInstallConfig`
   (so the release venv exists). Both preconditions must hold.
3. **Verification asserts `rook.server.__file__`**, not only `rook.__file__`.
   The failure was specifically a stale `rook\server.py`; the package root is a
   useful check, but `rook.server.__file__` under `…\venv\Lib\site-packages\rook`
   is the decisive proof. Assert both, but `rook.server` is the load-bearing one.

## Risks

- **Mirror timestamp semantics (#3).** `robocopy /MIR` makes dest match source
  (copies changed files, purges extras). In the real drift case the synced source
  is newer than the stale wheel, so it is copied. `dist-info` is a sibling dir and
  is untouched. Stale `__pycache__` is excluded from the mirror but harmless —
  Python recompiles when the mirrored source's mtime differs. The release
  verification (`rook.server.__file__` under site-packages + tools present) is the
  backstop if anything is off.
- **No system/bundled python (#1).** If `$VenvPython` was the only interpreter,
  excluding it makes `Resolve-BootstrapPython` throw. Acceptable: a local deploy
  already requires a bootstrap python, and the existing candidates cover it.
