# #300 — post_install Degraded-Reuse When Bundled CPython Absent

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** dev-infra / local deploy (not LM/runtime behavior)
**Branch:** `codex/issue-300-post-install-degraded-reuse`
**Issue:** https://github.com/bringfire/Rook/issues/300

> **Branch-note:** there is no `chore/dev-infra` branch (the earlier memory note is
> stale); the dev-infra spec already lives on `main`. This slice uses its own
> `codex/` branch and does not touch any LM feature branch.

---

## Summary

`scripts/deploy-local-testing.ps1` (release mode) cannot complete on a machine
whose bundled private CPython runtime is absent, **even though a usable release
venv already exists**. `post_install.py` → `install_mcp_server` →
`_install_from_wheelhouse` gates on `_ensure_private_runtime_inputs`, which
returns False (printing *"Missing private Python runtime"*) the moment the
bundled CPython / wheelhouse are absent, so `_install_from_wheelhouse` returns
`None`. `main()` then prints "MCP server installation failed" and `return 1`
([post_install.py:1193-1196]), the PowerShell `Invoke-PostInstallConfig` throws,
and the deploy aborts **before** reaching the canonical
`Install-ReleaseSourceIntoVenv` (source mirror) and `Test-EffectiveRuntime`
(runtime verification) steps. The operator is forced to mirror source by hand.

This fix adds a **degraded-reuse** path: when the private-runtime provisioning
inputs are incomplete but a usable release venv already exists, reuse that venv
instead of failing — so config refresh completes and the existing PowerShell
flow runs the source mirror + runtime verification automatically.

## Scope (confirmed)

**Reuse existing venv only.** Do NOT create a venv from `sys.executable` or any
system Python in this slice (that would change runtime provenance — a separate
decision). Three cases:

- **Bundled CPython present** → current behavior, unchanged.
- **Provisioning inputs incomplete (e.g. bundled CPython absent) AND a usable
  release venv python already exists** → degraded reuse: do not rebuild the venv,
  do not install from the missing wheelhouse, log an explicit warning, record a
  degraded summary outcome, and return the existing venv python so config refresh
  continues and PowerShell proceeds to `Install-ReleaseSourceIntoVenv` +
  `Test-EffectiveRuntime`.
- **Provisioning inputs incomplete AND no venv exists** → fail clearly
  (current behavior: return `None`).

## Design

### Single change: `installer/post_install.py` — `_install_from_wheelhouse`

Today the function opens with:

```python
    if not _ensure_private_runtime_inputs(layout, lock):
        _record_venv_rebuild_summary(
            layout.rook_root, runtime_name, label, 0, "failed", "inputs"
        )
        return None
```

Replace with a degraded-reuse branch that checks for an existing usable venv
before failing:

```python
    if not _ensure_private_runtime_inputs(layout, lock):
        existing_python = get_venv_python(venv_dir)
        if existing_python.exists():
            # Degraded reuse: the bundled private runtime / wheelhouse are absent
            # (e.g. a local source deploy on a box without the private CPython),
            # but a usable venv already exists. Do NOT rebuild it and do NOT
            # install from the missing wheelhouse -- reuse the existing
            # interpreter so config refresh continues and the caller
            # (deploy-local-testing.ps1) still runs Install-ReleaseSourceIntoVenv
            # + Test-EffectiveRuntime, which are the real success gate. See #300.
            _INSTALL_LOGGER.warning(
                "%s: bundled private runtime/wheelhouse inputs incomplete; "
                "reusing existing venv at %s (degraded mode -- no rebuild, no "
                "wheelhouse install). Source mirror + runtime verification still "
                "run downstream.",
                label,
                existing_python,
            )
            print(
                f"{label}: reusing existing venv at {existing_python} "
                f"(degraded mode; private runtime inputs incomplete)."
            )
            _record_venv_rebuild_summary(
                layout.rook_root, runtime_name, label, 0, "reused_existing", "inputs"
            )
            return existing_python
        _record_venv_rebuild_summary(
            layout.rook_root, runtime_name, label, 0, "failed", "inputs"
        )
        return None
```

- `get_venv_python(venv_dir)` already exists ([post_install.py:141]) and returns
  `venv_dir/Scripts/python.exe` (Windows) / `venv_dir/bin/python` (POSIX).
- The degraded path returns a truthy `Path`, so `install_mcp_server` returns it,
  `main()`'s `if not managed_python` bail is not taken, config refresh proceeds,
  and the PowerShell release flow reaches the mirror + verify steps.
- The new summary outcome is `"reused_existing"` (distinct from `"failed"`), so
  the install summary records that degraded reuse occurred.

### No PowerShell changes

The release branch of `deploy-local-testing.ps1` (lines ~1289-1300) already runs
`Invoke-PostInstallConfig` → `Install-ReleaseSourceIntoVenv` →
`Test-EffectiveRuntime`. Once `post_install` stops aborting, those canonical
steps run automatically. `Resolve-BootstrapPython` already guarantees
`post_install` is bootstrapped by a safe non-venv interpreter — unchanged.

## Guardrails (do NOT)

- Do NOT bootstrap `post_install` with the target venv (unchanged —
  `Resolve-BootstrapPython` already excludes it).
- Do NOT create a venv from `sys.executable` / system Python in this slice.
- Do NOT recreate or modify the existing venv in the degraded path.
- Do NOT weaken `Test-EffectiveRuntime` / runtime verification. The success
  condition is **not** "post_install returned 0" — it is "the source mirror ran
  and `Test-EffectiveRuntime` proved the deployed site-packages imports the
  current `rook.server`."
- No LM / runtime behavior changes. No change to `_create_venv`,
  `_ensure_private_runtime_inputs`, `python_runtime_install.py`, or any
  `rook/agent/*` module.

## Testing

New `mcp_server/tests/test_post_install_degraded_reuse.py`, mirroring the
`_load_post_install()` loader idiom in `test_post_install_encoding.py` (insert
`installer/` on `sys.path`, load `post_install.py` via
`importlib.util.spec_from_file_location`).

1. **Degraded reuse returns the existing venv:** build a `RuntimeLayout` rooted at
   a `tmp_path` (`RuntimeLayout.from_rook_root(tmp_path, PRIVATE_PYTHON_VERSION)`)
   where `layout.private_python` does NOT exist; create the venv interpreter file
   at `get_venv_python(layout.rook_venv)` (make parent dirs + touch the file);
   monkeypatch `_ensure_private_runtime_inputs` to return `False` (simulating the
   missing bundled runtime). Assert `_install_from_wheelhouse(...)` returns that
   existing venv python path (not `None`), and that the install summary records
   `outcome == "reused_existing"` for the runtime.
2. **No venv → clear failure:** same fixture but do NOT create the venv
   interpreter file; assert `_install_from_wheelhouse(...)` returns `None` and the
   summary records `outcome == "failed"`.
3. **Inputs present → degraded branch not taken (no live pip / no process sweep):**
   monkeypatch `_ensure_private_runtime_inputs` → `True`, `_install_from_wheelhouse_once`
   → a sentinel `(Path("sentinel"), None)`, and `_make_rebuild_guard` → a no-op
   context manager (a small `contextlib.contextmanager` yielding a stub with
   empty `close_failures` and `thread_died_unexpectedly=False`, so
   `_collect_rebuild_guard_health` stays happy). Assert the function returns the
   sentinel — proving the degraded branch is bypassed when inputs are present and
   the existing happy path is untouched. (Tests 1-2 return inside the
   inputs-incomplete branch and never reach the guard, so they need no such stub.)

All deterministic; no real pip, no network, no live Rhino, no process sweep.

## Verification (post-merge, on this box — bundled CPython absent)

1. Run the release deploy: `scripts/deploy-local-testing.ps1 -Configuration
   Release -SkipBuild`. Expect it to pass the MCP/post_install step (degraded
   reuse, no manual mirror) and reach **`Install-ReleaseSourceIntoVenv`** +
   **`Test-EffectiveRuntime`**, with `Test-EffectiveRuntime` proving the deployed
   site-packages imports the current `rook.server`.
2. Re-run the LM deployed smoke (`coherence` / `surface` / `external`) — all PASS
   (sanity that the degraded reuse left a coherent runtime). This is the proof the
   manual-mirror tax is removed.

If the full deploy fails at an unrelated later step, that is out of #300 scope;
the gate for this slice is that post_install no longer aborts on the missing
bundled runtime and the mirror + verification steps run.

## File Touch List

- Modify: `installer/post_install.py` — degraded-reuse branch in
  `_install_from_wheelhouse`.
- Add: `mcp_server/tests/test_post_install_degraded_reuse.py` — tests 1-3.
