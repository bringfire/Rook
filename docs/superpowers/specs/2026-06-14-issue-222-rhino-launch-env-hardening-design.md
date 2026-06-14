# Issue #222 Rhino Launch Environment Hardening Design

## Context

Issue #251's launch gate found that MCP-wrapped `rhino_workbench_launch`
returned `workbench_exited_before_bind` before RookNative discovery. The direct
async control succeeded from a shell parent. The focused #222 probe isolated the
cause:

- The Codex-launched Rook MCP server environment lacks `windir`.
- Launching Rhino with that exact environment reproduces `0xE0434352`.
- Adding only `windir=C:\Windows` to the same environment lets the owned
  launcher bind and close cleanly.
- Windows Application Event Log reports `.NET Runtime` Event ID `1026`:
  `MS.Internal.FontCache.Util` throws `System.UriFormatException` during
  Rhino/Eto/WPF startup.

The defect is a Python launcher-environment hardening bug. It is not a transport
timeout, registry/server-death bug, or the unrelated C# handle-inheritance issue
already fixed in the chat-service spawn path.

## Goal

Make every Python-owned Rhino launch pass through one environment policy seam so
Rhino receives the Windows startup essentials it needs even when the parent MCP
or harness process was launched with a stripped environment.

This fix must preserve the existing `LaunchOutcome` return contract. #251
delegation remains blocked until this fix lands, is deployed to the bound MCP
runtime, and the approved #251 launch gate reruns cleanly.

## Non-Goals

- Do not implement #251 `rhino_launch` delegation in this slice.
- Do not build a hermetic allowlisted Rhino environment yet.
- Do not add handle-isolation work. The known handle-inheritance defect was a
  different C#/.NET Framework spawn path and is not present on Python
  `subprocess.Popen`.
- Do not add Windows known-folder API sourcing for customizable profile paths.
  Only the proven OS invariants are actively sourced from the OS.

## Environment Policy

Add one Python launch-environment seam in `mcp_server/src/rook/rhino_launch.py`:
`build_launch_env(base_env=None, os_info=None)`.

The parent environment is an input, not an authority. Today the parent may be
Codex MCP, a harness, or a shell. Later it may be a daemon, CI, nested
orchestration, or a router-plane launch context. All Python Rhino launch sites
must use the same helper so policy changes stay in one function.

### Source Rules

`base_env` defaults to `os.environ`, copied immediately. The helper must not
mutate `base_env` or `os.environ`.

`os_info` is injectable for tests. The production provider is lazy and
Windows-guarded so the module imports and pure unit tests run on non-Windows
hosts.

### OS Invariants

These values are OS facts, not parent preferences. They are authoritatively set
from OS discovery even when the parent supplied a value:

- `windir`
- `SystemRoot`
- `SystemDrive`

Production discovery uses `GetWindowsDirectoryW` to discover the Windows
directory, validates that it exists, and derives `SystemDrive` from it. If
discovery fails, the helper uses conservative `C:\Windows` and `C:` fallbacks
and records the fallback in the policy report. A silent discovery failure must
not authoritatively set garbage.

### Parent-Customizable Essentials

These may be intentionally customized by the parent, so they are backfilled only
when absent or empty:

- `TEMP`
- `TMP`
- `USERPROFILE`
- `APPDATA`
- `LOCALAPPDATA`
- `ProgramData`
- `PATH`

Backfill uses only cheap derivation:

- `ProgramData` from `SystemDrive`.
- `APPDATA` and `LOCALAPPDATA` from `USERPROFILE` when present.
- `TEMP` and `TMP` from `LOCALAPPDATA` or `USERPROFILE` when present.

If a value is absent and not cheaply derivable, record it as
`missing_unresolved`. Do not fabricate a value and do not add
`SHGetKnownFolderPath` or other known-folder API sourcing in this slice.

`PATH` is backfill-if-absent only. A present-but-minimal `PATH` is an accepted
limitation for this fix. Rhino is launched by full path, and Windows loads from
the executable directory and system directories independently of `PATH`; the
remaining risk is a plugin that shells out to a tool expected on `PATH`. That
case is outside the proven defect and should be diagnosed from future
instrumentation if it appears.

## Instrumentation

`build_launch_env()` returns an env plus a compact deterministic report. The
report records sorted lists or mappings for:

- `authoritative`: OS invariants set from OS discovery.
- `backfilled`: parent-customizable values derived because they were absent or
  empty.
- `inherited`: relevant values left from the parent.
- `missing_unresolved`: values absent and not cheaply derivable.
- `fallback_used`: any OS discovery fallback used.

The report is attached to launch evidence as optional `launchEnv`. It must be
JSON serializable through `LaunchEvidence.to_dict()` and must not change the
semantic `LaunchOutcome` contract.

The report is the evidence pump for future policy evolution. If heterogeneous
launch parents repeatedly produce harmful inherited values, this one seam can
later evolve toward a hermetic allowlist with evidence. This slice does not make
that move.

## Launch Wiring

`launch_owned_workbench()` builds the env once and uses it consistently:

```python
launch_env = build_launch_env(os.environ)
started = start_rhino_process(
    exe,
    requested_scheme=requested,
    env=launch_env.env,
    popen=lambda argv: subprocess.Popen(argv, env=launch_env.env),
)
```

The redundancy is intentional. The call declares the env through
`start_rhino_process(env=...)`, and the patchable local `Popen` lambda honors the
same env. If a future edit removes the override lambda, the default
`start_rhino_process` popen path still uses the controlled env instead of
silently reverting to parent inheritance.

`runtime_harness` keeps its existing override behavior:

1. Start from `os.environ`.
2. Apply `launch_env_overrides`.
3. Run `build_launch_env()` over the result.
4. Pass the built env both to `start_rhino_process(env=...)` and the patchable
   harness `Popen` lambda.

This means harness overrides cannot override `windir`, `SystemRoot`, or
`SystemDrive`; those are now authoritative OS invariants. Existing source and
test grep found no harness override for those three keys.

## Tests

Unit tests for `build_launch_env()` live in `mcp_server/tests/test_rhino_launch.py`:

- Missing `windir` produces authoritative `windir`, `SystemRoot`, and
  `SystemDrive`.
- Present-wrong `windir`, `SystemRoot`, or `SystemDrive` is overwritten from
  injected OS discovery.
- OS discovery failure uses fallback and reports fallback use.
- Parent-customizable values are cheap-derived only when possible.
- Unresolvable customizable values are recorded in `missing_unresolved`, not
  fabricated.
- The function does not mutate the passed `base_env`.
- Report lists are sorted and stable.
- Report categorization is correct: invariant in `authoritative`, derived value
  in `backfilled`, untouched relevant parent value in `inherited`, unresolved
  value in `missing_unresolved`.
- Present `PATH` is inherited and not merged.
- `LaunchEvidence.to_dict()` with `launchEnv` survives `json.dumps`.
- Tests inject `os_info`; they do not require real Win32 calls and must run on
  non-Windows CI.

Unit tests for launch wiring:

- `mcp_server/tests/test_workbench.py`: `launch_owned_workbench()` passes the
  built env into the `workbench.subprocess.Popen` lambda while preserving
  monkeypatchability, and failure/success launch evidence includes `launchEnv`.
- `mcp_server/tests/test_runtime_harness.py`: harness
  `launch_env_overrides` apply before `build_launch_env()`, harness `Popen`
  receives the built env, and the launch evidence/manifest includes the report.

## Live Verification

Live verification must exercise the runtime that the MCP client is actually
bound to. The prior probe showed Codex binds to the installed AppData runtime,
not necessarily the repo `.venv`. Before the live MCP rerun, either deploy the
fix to the installed runtime or explicitly repoint the Codex binding to the repo
runtime. A green live rerun against old installed code is not evidence.

Required live checks after deployment or repointing:

1. Start from no live `Rhino.exe` and no owned workbench sessions.
2. From the fixed MCP binding, run `rhino_workbench_launch`.
3. Expected: launch binds successfully, returns a structured success envelope,
   and `launchEnv` reports authoritative `windir`/`SystemRoot`/`SystemDrive`.
4. Close the owned session through `rhino_workbench_close`.
5. Confirm no live `Rhino.exe` process remains.
6. Rerun the approved #251 launch gate. Only after that gate classifies `clear`
   should #251 delegation proceed.

## Routing

This is a separate #222 launcher-hardening PR. #251 remains sequenced behind it.
Because the fix preserves the `LaunchOutcome` contract, #251 does not need a
transport redesign. After this fix lands and the approved gate reruns cleanly,
#251 can implement the already-approved `rhino_launch` delegation.
