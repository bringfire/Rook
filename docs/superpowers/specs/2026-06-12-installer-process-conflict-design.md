# Installer Process Conflict Handling Design

Date: 2026-06-12

## Purpose

Rook upgrades must complete cleanly when Claude, Codex, or other AI clients
have live Rook MCP sessions open. The 1.5.11 installer can fail late in
post-install finalization when running Rook Python processes hold files in
`%LOCALAPPDATA%\Rook`. The failure UX is also wrong: it tells users to close
Rook Python processes, which is not user-serviceable and does not work when
clients auto-respawn their MCP servers.

This design covers issue #237 and the tightly scoped #240 companion manifest
cleanup. The two fixes share the same expensive verification oracle: build the
large installer, run it over a live existing install with agent sessions open,
and inspect the resulting install/logs/manifests.

## Scope

In scope:

- Rook-specific process conflict consent before `[Files]`.
- Disabling Inno's generic close/restart application flow.
- A pre-copy PowerShell helper for process enumeration and close.
- A Python rebuild guard around private venv mutation.
- Always-present post-install logging and structured summary output.
- Minimal #240 installer hygiene: delete stale child chat manifests and write
  fresh root/child manifests.
- Automated and live installer verification.

Out of scope:

- Changing `ChatServiceManager` lookup semantics.
- Removing the root `RookChatService.json` write.
- Atomic staged venv swap.
- Broader managed companion behavior changes.
- Reworking Rook MCP or Chirp process ownership.

Tripwire: if the #240 implementation requires any `src/Rook/**` diff, #240
drops out of this PR and becomes a follow-up. The #240 portion of this PR must
remain installer/finalizer only.

## Evidence

Issue #237 records the direct failure mode:

- v1.5.11 payload copy succeeded.
- post-install finalization began.
- venv rebuild failed while installed Rook MCP processes were running.
- no `post_install.log` was written on the failure path.
- killing the installed-venv `python -m rook` processes unblocked finalization.
- clients later auto-respawned those processes, so one-time manual remediation
  was not sufficient.

The local installer topology adds a second conflict surface:

- `installer/RookSetup.iss` copies the private CPython runtime to
  `{localappdata}\Rook\python\cpython-3.11.9` during `[Files]`.
- running Rook Python processes can map files from that base runtime before
  post-install begins.
- therefore process suppression must start before `[Files]`, not only inside
  `post_install.py`.

Live process inspection on this machine showed each current Rook MCP server as
a two-process pair:

```text
venv\Scripts\python.exe -m rook                  # venvlauncher stub
python\cpython-3.11.9\python.exe -m rook         # base interpreter child
```

Pre-bundled upgrades have a related shape: their venv stub lives under
`%LOCALAPPDATA%\Rook\venv`, but the interpreter child may be the user's system
Python outside the Rook root. Killing only the stub can orphan the handle-holding
interpreter. Every sweep must therefore close matched processes and their full
descendant trees, descendants first.

Issue #240 topology was verified from code:

- `post_install.py` writes `RookChatService.json` only to the plugin root.
- `ChatServiceManager.GetManifestPath()` reads beside the loaded companion
  assembly, e.g. `RookNative\net8.0\RookChatService.json`.
- stale child manifests can shadow the fresh release posture on upgrade.

## High-Level Design

The installer owns a Rook-specific process close flow:

1. Inno disables generic Restart Manager close/restart behavior:
   `CloseApplications=no` and `RestartApplications=no`.
2. `PrepareToInstall` extracts a standalone PowerShell helper to `{tmp}`.
3. The helper performs a read-only enumeration of Rook process conflicts and
   writes a summary file plus `post_install.log`.
4. In interactive installs, Inno shows a plain-language consent dialog based on
   the summary. In `/SILENT` and `/VERYSILENT`, consent is implied.
5. After consent, the helper closes matched process roots plus descendants and
   retries to quiet. It fails closed before `[Files]` if quiet cannot be reached.
6. `[Files]` copies the installer payload.
7. `post_install.py` appends to the same `post_install.log` as its first
   install-mode action and uses rebuild guards around actual venv mutations.
8. `post_install.py` writes fresh chat manifests to the root and runtime child
   directories.
9. validation and smoke evidence prove the conflict path and #240 shape.

PowerShell handles early, pre-copy process control because no new Python payload
can be trusted yet. Python handles the rebuild guard because lineage exclusion,
retry logic, and logging are testable there.

## Inno Policy

The current `.iss` does not explicitly set `CloseApplications`,
`RestartApplications`, or `CloseApplicationsFilter`, so Inno defaults apply.
Inno's docs say `CloseApplications` defaults to `yes`,
`RestartApplications` defaults to `yes`, and the default filter is
`*.exe,*.dll,*.chm`.

This installer should set:

```ini
CloseApplications=no
RestartApplications=no
SetupLogging=yes
```

Rationale:

- The acceptance bar requires a Rook-specific explanation, not Restart Manager's
  generic files-in-use UX or reboot-required fallback.
- Process control needs one owner and one audit trail.
- Restart Manager's filter misses relevant extensions such as `.pyd`.
- Restarting raw `python -m rook` processes after install is not useful; the
  owning clients reconnect their own servers.
- `SetupLogging=yes` remains as a zero-code backstop if PowerShell itself fails
  to launch.

With Restart Manager disabled, the pre-copy helper must fail closed if it cannot
reach quiet. It must not let the installer continue into raw Inno
Abort/Retry/Ignore file-copy failures.

## Pre-Copy PowerShell Helper

The installer packages or extracts a real `.ps1` file and runs it as:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <helper.ps1> ...
```

No inline `-Command` script should be used.

The helper has two modes.

Enumeration mode:

- enumerate processes with image path under `%LOCALAPPDATA%\Rook\`;
- build matched roots where the parent is not also in the matched set;
- validate parent/child relations with creation times where available;
- walk one parent hop from each root to derive owner app names;
- write a terse summary for Inno;
- write the full table to a structured JSON sidecar;
- create/rotate `post_install.log`.

Close mode:

- close every matched root and full descendant tree, descendants first;
- retry to quiet with bounded attempts;
- fail closed on not-quiet or enumeration failure;
- return a documented exit code.

Exit-code contract:

- `0`: quiet/no conflicts remain.
- nonzero: not quiet, enumeration failure, close failure, or helper error.

Any nonzero exit means Inno stops at the preparing page with a plain-language
message. PowerShell launch failure is also fail-closed.

## Process Matching Rules

One boundary, two exclusion policies:

- Boundary: executable image path under `%LOCALAPPDATA%\Rook\`.
- Pre-copy exclusion policy: none. No installer-spawned Rook Python children
  exist yet.
- Python rebuild exclusion policy: never close the finalizer process or
  descendants of the installer/finalizer process tree.

Each sweep closes matched processes and their full descendant trees. This is
required for both current bundled installs and pre-bundled upgrades:

- bundled install: stub and base interpreter are both under Rook root;
- pre-bundled upgrade: stub is under Rook root, interpreter child may be system
  Python outside Rook root.

Descendants are closed before ancestors. Selective closing inside a matched tree
is forbidden because it can orphan handle-holding interpreter children.

PID reuse guard:

- parent PID alone is not enough;
- ancestry checks should compare process creation times;
- a true parent must have been created before the child.

The Python side must be stdlib-only. It cannot depend on `psutil` or any package
from a venv being rebuilt.

## Consent UX

The helper should present logical server roots, not raw process count. A server
root is a matched process whose parent is not in the matched set.

Owner attribution:

- one-hop parent lookup from each logical root;
- friendly map:
  - `claude.exe` -> `Claude`
  - `codex.exe` -> `Codex`
- unknown basenames are shown raw, for example `node.exe`;
- do not claim `Claude Code` from `node.exe`.

Degradation ladder:

1. count plus friendly owner names;
2. count plus mixed friendly/raw owner names;
3. count-only if owner process names cannot be resolved.

Example wording:

```text
Rook Setup found 5 running Rook agent server(s) started by Claude and Codex.

Setup will close them now so Rook can be updated. Your AI tools will reconnect
after installation.
```

Use "close", not "kill" or "terminate". In silent and very-silent installs,
consent is implied, and the helper proceeds while logging the same evidence.

## Rebuild Guard

The Python watchdog is named the rebuild guard, not the finalization watchdog.
Its scope is the mutated venv resource, not all finalization.

The guard is a reusable primitive used around each actual private venv mutation:

- Rook MCP venv rebuild window.
- Chirp `.venv` rebuild window, only when Chirp is actually rebuilt.

The guard starts immediately before venv teardown and stops when pip exits
successfully. It does not run during doctor validation, config writes, manifest
writes, or install-state work unless later evidence proves those resources are
lock-sensitive.

The kill set remains the shared Rook-root boundary plus descendant trees. The
guard differs from pre-copy PowerShell only by its exclusion policy: it must
exclude the finalizer process and descendants of the finalizer process tree,
including doctor validation children.

Guard contract:

- sweep continuously during the guarded window;
- log every sweep and close attempt;
- cap close attempts per PID, around three attempts;
- log sweep exceptions and continue where possible;
- a dead guard thread while the mutation is active is a fail-loud condition;
- on venv/pip failure while guarded, sweep once more, perform one full rebuild
  retry from delete -> create -> pip, then fail loud if the retry fails;
- never resume pip into a half-written venv.

There should be separate labeled guard windows, not one long guard spanning both
Rook and Chirp. A no-op Chirp upgrade opens no Chirp guard window.

## Logging And Summary Output

`%LOCALAPPDATA%\Rook\logs\post_install.log` is the primary audit trail.

First writer of a setup run is the pre-copy PowerShell helper:

- rotate `post_install.log` to `post_install.prev.log`;
- write a run header with Rook version and UTC timestamp;
- write the preflight enumeration and close result.

PowerShell writes UTF-8 using .NET file APIs, not redirection.

`post_install.py` appends to the same log before any install-mode config reads
or other failable work. Its `main()` is wrapped by a top-level last-gasp
exception handler that logs traceback before exiting nonzero. Venv, pip, and
doctor subprocess stdout/stderr are captured into the log.

The only expected concurrent writers are the Python main thread and guard
thread, using one Python logging handler with its built-in lock. PowerShell exits
before Python begins.

The finalizer also writes a structured `post_install_summary.json` with:

- schema version;
- run start/end UTC;
- setup version;
- phase reached;
- preflight server count and owners;
- closed process counts;
- guard window labels and outcomes;
- rebuild retry count;
- manifest write paths;
- final outcome;
- failure culprit, path, PID, owner, and recommended action when known.

The summary is a support surface for future `rook doctor` consumption.

## Minimal #240 Manifest Fix

Add child manifest deletes to the existing `[InstallDelete]` section:

```ini
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\RookChatService.json"
```

Delete-then-write ordering is deliberate. If post-install dies before fresh
manifest writes, stale child manifests are already gone. A missing manifest
falls back to companion auto-generation; a stale manifest shadows with wrong
content.

`post_install.py` writes the same fresh release manifest to:

- plugin root `RookChatService.json`;
- each existing known runtime child directory: `net8.0`, `net7.0`, `net48`.

Requirements:

- no `src/Rook/**` changes;
- root and child manifests are byte-identical;
- writes use explicit `encoding="utf-8"`;
- every write is logged;
- unknown `net*` child directories produce a warning in `post_install.log`.

Keeping the root manifest is intentional. Whether the root write is dead code is
an unverified cleanup question and must not be decided in this PR.

## Failure UX

Pre-copy failure:

- stop at the preparing page;
- explain that Rook agent servers could not be closed;
- name owner apps when known;
- point to `post_install.log` and the Inno setup log.

Rebuild failure:

- fail nonzero from `post_install.py`;
- Inno shows a plain-language finalization failure message;
- message names culprit and action when known, for example:

```text
Rook Setup could not complete because python.exe (PID 1234, started by Codex)
is holding files in the Rook environment and could not be closed.

Close Codex and run Setup again.
```

Known gap:

- a process whose current working directory is under the install tree can block
  directory deletion without matching the file/image-handle model;
- retry and culprit reporting should degrade clearly rather than mysteriously.

## Verification

Automated verification:

- Python tests for rebuild guard matching, lineage exclusion, PID reuse guard,
  descendant-tree close, self/doctor exclusion, one full rebuild retry, and
  stand-down after pip success.
- PowerShell helper tests for enumeration, owner attribution, root counting,
  descendant-tree close, silent-mode behavior, exit-code contract, and
  pre-bundled venv shape where a system-Python child is outside the Rook root.
- Encoding source-pin tests extended so new log and manifest text IO uses
  explicit UTF-8.
- Post-install tests for `post_install.log` last-gasp exception capture.
- Tests that root and child chat manifests are byte-identical JSON with expected
  release fields.
- Installer guard tests for `CloseApplications=no`, `RestartApplications=no`,
  `SetupLogging=yes`, preflight helper packaging, new `[InstallDelete]`
  entries, and zero `src/Rook/**` scope for #240.

Live installer smoke before PR open:

- build a dev-versioned installer from cached/staged payloads, not the full
  release pipeline;
- run it over an existing install with Claude and Codex sessions open and Rook
  MCP servers running;
- verify the consent dialog shows correct server count and owner names;
- verify pre-copy sweep closes all stub/base-interpreter pairs with no orphaned
  children;
- verify rebuild guard windows activate and stand down at the logged boundaries;
- verify `post_install.log` starts with the rotated run header and continues
  through finalizer exit;
- verify `post_install_summary.json` parses and records counts/owners/outcome;
- verify Rook and Chirp venv rebuilds succeed as applicable;
- verify child manifests are byte-identical to root;
- verify clients reconnect after installation.

Silent smoke:

- run the same built artifact once with `/SILENT`;
- verify implied consent branch closes conflicts, logs evidence, and completes.

Pre-bundled-upgrade coverage:

- use an automated fabricated integration test, not a live matrix entry;
- create a fake root with a venv from system Python;
- run a sleep-loop from the venv;
- run the helper against the fake root;
- assert both the matched stub and out-of-boundary system-Python child die.

The live smoke is required before opening the PR because the process-tree and
installer-phase behavior cannot be proven by mocks alone. This is the same
reason #240 rides with #237: both are inspected by the same installer run.

## Implementation Units

1. Inno setup policy and preflight integration.
2. PowerShell preflight helper.
3. Python process enumeration and rebuild guard primitive.
4. Logging and summary writer.
5. #240 manifest cleanup/write parity.
6. Automated tests and release guard updates.
7. Dev installer build plus live/silent smoke evidence.

## Future Hardening

Atomic staging/swap can shrink the venv lock window, but it is not this PR.
Before adopting it, prove Windows directory swap behavior under open handles and
prove venv relocatability from staging path to final path, including entry-point
wrappers and `pyvenv.cfg`.

The root `RookChatService.json` write may be removable, but that requires a
separate verification pass across doctor validation, native/managed support
paths, and release smoke evidence.
