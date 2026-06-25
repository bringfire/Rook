# Installer Finalizing Progress UX Design

## Context

Rook's public installer performs important post-install finalization after the normal file-copy progress has effectively reached the end. Today `CurStepChanged(ssPostInstall)` calls `RunPostInstallSetup()`, which launches bundled Python with:

```pascal
Exec(PythonExe, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
```

That blocking call is intentional. It preserves the installer's fail-closed behavior: `post_install.py` must complete successfully before setup can be treated as complete, and a nonzero result aborts installation.

The user-facing problem is perception. First-time setup can take 10-12 minutes while the standard green progress bar appears complete. Users reasonably read that as a stuck or failed installer even though private Python setup, bundled wheel installation, MCP client configuration, skill deployment, and validation are still running.

## Goal

Add a clear, truthful post-install finalization page so users know the installer is still working during the long finalization step.

The first branch is strictly UX/perception-only. It does not change `post_install.py`, process orchestration, runtime setup semantics, or staged progress reporting.

## Non-Goals

- Do not move post-install finalization to the `[Run]` section.
- Do not change `installer/post_install.py`.
- Do not replace blocking `Exec(... ewWaitUntilTerminated ...)`.
- Do not fake determinate percentages.
- Do not add phase telemetry, log polling, or child-process wait loops.
- Do not move setup work to first Rhino/Rook startup.

## Design

Add a dedicated Inno Setup output marquee page around the long-running child process inside `RunPostInstallSetup()`.

The page should be created/shown only after `PostInstallSelected()` has passed and the private Python existence check has passed. Missing-runtime failures should keep using the existing direct critical error path; they should not flash or show the finalization page.

Once the installer is ready to launch `post_install.py`, show the page immediately before the blocking `Exec` call and hide it in a `try..finally`-style block after the child process returns or launch handling completes. The existing failure handling remains inside `RunPostInstallSetup()`: launch failure and nonzero exit code still show critical error dialogs and return `False`, causing `CurStepChanged(ssPostInstall)` to `Abort`.

User-facing copy:

- Caption: `Finalizing Rook`
- Description: `First-time setup can take 10-12 minutes. The installer is still working.`
- Body/detail: `This step configures private Python, bundled wheels, MCP entries, skills, and validation.`

The page should use marquee/indeterminate progress, not `SetProgress`. If Inno's marquee animation freezes during the blocking `Exec`, that is acceptable for Phase 1 as long as the page and copy render before the wait. A real installer run must record whether the animation continues while the child process runs.

## Implementation Boundary

Expected files:

- `installer/RookSetup.iss`
- `scripts/tests/release-installer-guards.tests.ps1`

Avoid touching other files in Phase 1.

While touching `installer/RookSetup.iss`, fix the stale source-section comment that says `post_install.py` is "used by [Run]". The accurate contract is that `post_install.py` is packaged as a payload and launched from Pascal script so the installer can gate on the child process exit code.

## Guard Tests

Update release installer guards to pin the important behavior:

- `RunPostInstallSetup()` remains Pascal-script gated.
- `post_install.py` is still not run from `[Run]`; this should be checked by parsing or regexing the `[Run]` section rather than relying only on one exact literal line.
- `Exec(PythonExe, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)` remains present.
- Nonzero `ResultCode` still produces a critical failure path and returns `False`.
- The installer defines and uses a `Finalizing Rook` marquee/output page around post-install finalization.
- The finalization page is shown only after component selection and private Python existence checks pass.
- The finalization page is hidden in a protected cleanup path after the blocking child process returns.
- The copy includes `10-12 minutes` and `installer is still working`.
- The copy names the real work: private Python, bundled wheels, MCP entries, skills, and validation.
- The post-install finalization page does not use fake determinate progress via `SetProgress`.

## Manual Verification

Build and run a local installer from a release-prepared tree. During first-time install or a representative repair install:

1. Confirm the standard file-copy progress does not leave the user staring only at a completed green bar.
2. Confirm the `Finalizing Rook` page appears before the long `post_install.py` wait.
3. Confirm the copy clearly says the step can take 10-12 minutes and that the installer is still working.
4. Observe whether the marquee animation continues while `Exec` waits.
5. Confirm success still reaches the final installer page.
6. Confirm a simulated nonzero `post_install.py` result still aborts setup.

## Follow-Up: Phase 2

If Phase 1 is not enough, a later branch can add phase-level telemetry. That should be designed separately because it likely requires `post_install.py` to emit durable phase status and Inno to launch the child process with a polling loop while preserving exit-code semantics manually.

Phase 2 should not be bundled into this branch.
