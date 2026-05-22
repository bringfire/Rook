# Beta Installer Hardening Design

Date: 2026-05-21

## Purpose

Rook's beta installer should become a one-shot, signed, per-user Windows installer that works without external prerequisites beyond Rhino 8 and the user's selected MCP clients. The installer must preserve beta-user settings across frequent updates, avoid manual Rhino PluginManager repair, and ship a deterministic, scanned runtime that does not resolve dependencies on the user's machine.

This design chooses Approach A now and Approach B later:

- Approach A now: harden the existing Inno Setup per-user installer into the beta product installer.
- Approach B later: add an enterprise per-machine/MSI path when Rook is ready for managed corporate deployment.

The implementation plan that follows this spec should not execute broad installer rewrites in one step. It should break the work into release-manifest, runtime, security, migration, UX, doctor, release-publication, and enterprise-preservation milestones.

## Product Install Model

The beta product installer is a signed, self-contained, per-user Inno Setup installer. It installs without admin rights and without requiring Python, pip, Visual Studio, Rhino SDK, network access, or any external runtime beyond Rhino 8-provided runtime components that are explicitly verified as baseline dependencies.

Zero prerequisites means zero prerequisites beyond:

- Rhino 8.
- The MCP clients the user selects for configuration, such as Claude Desktop, Claude Code, or Codex CLI.

The installer owns code/runtime payloads and keeps user-owned state separate:

| Root | Ownership | Purpose |
|---|---|---|
| `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative` | installer-owned active Rhino plugin folder | `RookNative.rhp`, managed companion files, plugin-side runtime assets such as FFmpeg |
| `%LOCALAPPDATA%\Rook\app` | installer-owned app payload | MCP server source/app files, docs, manifests, support tools |
| `%LOCALAPPDATA%\Rook\runtime` | installer-owned runtime payload | bundled CPython runtime and sealed package environment |
| `%LOCALAPPDATA%\Rook\config` | user-owned durable settings | provider settings, API keys, update settings, preferences |
| `%LOCALAPPDATA%\Rook\data` | user-owned durable data | knowledge/runtime data that should survive updates |
| `%LOCALAPPDATA%\Rook\logs` | user-owned logs | install logs, doctor logs, runtime diagnostics |

Plugin-only/custom install remains available for support and debugging, but the default beta path is full install. The UI should make clear that disabling runtime/MCP components may leave Rook incomplete.

The source `install.ps1` path remains a developer/local-testing bootstrap and may continue using local Python or `uv`. It is not the beta product install path.

## Runtime And Release Artifact Closure

The release build produces two manifest views to avoid a circular signed-installer hash problem:

- `rook-payload-manifest.json`: embedded in the installer and installed locally under `%LOCALAPPDATA%\Rook\app`. It records payload/runtime inventory only and does not contain the final installer hash.
- `rook-release-manifest.json`: published with the GitHub Release. It records the final signed installer hash, installer signature/timestamp metadata, hashes for immutable release reports, and the payload manifest hash.

`rook doctor` must be able to compare the installed payload against the installed payload manifest without network access.

All hashes for signed files are recorded after signing.

### Artifact Contract

| Artifact Class | Source Of Truth | Build / Staging Step | Validation / Scanning Gate | Signing / Integrity | Install Destination | Manifest Fields |
|---|---|---|---|---|---|---|
| `RookNative.rhp` and native DLL closure | `src/RookNative` Release x64 build | Build with pinned VS/MSVC/MFC toolset; stage `.rhp`, required sibling DLLs, and app-local VC++/MFC runtime files if required | Dependency walk distinguishes baseline Windows/Rhino DLLs from Rook-shipped DLLs; no missing non-baseline DLLs; verify x64 architecture, expected plugin GUID, version | Authenticode sign Rook-owned native binaries where practical; SHA256 after signing | `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative` | plugin id, version, build config, compiler/toolset, file hashes, dependency list, baseline DLLs, shipped VC/MFC runtime files |
| Managed companion `.rhp` and .NET closure | `src/Rook` `net7.0` Release output | Build `dotnet build src\Rook\Rook.csproj -f net7.0 -c Release`; stage `.rhp`, `.deps.json`, `.runtimeconfig.json`, DLLs, `runtimes/` | Validate `runtimeconfig` TFM is `net7.0`; no `net48` release path; Rhino 8-provided .NET runtime is an allowed baseline dependency and must be verified/documented | Authenticode sign Rook-owned managed assemblies where practical; SHA256 after signing | Rhino plugin directory | plugin id, TFM, runtime baseline, file hashes, dependency graph summary |
| Bundled CPython runtime | Pinned CPython version selected by release config | Stage Rook-owned Python runtime tree into release payload | Isolated startup check proves no user-site, no `PYTHONPATH`, no ambient PATH dependency; normal Rook startup check proves imports and `rook doctor` run using only bundled runtime and sealed packages; verify version/architecture | SHA256 runtime tree; sign Rook-owned launchers/executables where permitted | `%LOCALAPPDATA%\Rook\runtime\python\<version>` or versioned runtime root | Python version, architecture, source URL/hash, runtime file hashes, startup isolation settings |
| Sealed wheelhouse/materialized `site-packages` | Lockfile generated by release build from `mcp_server/pyproject.toml` plus approved constraints | Download wheels during release build only; materialize installed environment from wheelhouse only; no sdists, no editable installs | Hash-check wheels; vulnerability scan lockfile and final runtime; fail on malicious/yanked/high-risk packages; scan `.pth`, startup hooks, scripts, native extensions | SHA256 every wheel and installed file | Bundled runtime package directory | package name/version, wheel filename, wheel hash, installed file hashes, license, vulnerability status, exception ids |
| MCP server/app payload | `mcp_server/src/rook`, `pyproject.toml`, installer app assets | Stage source/app payload into `%LOCALAPPDATA%\Rook\app` without editable install | `rook doctor` import check against bundled runtime; verify no stale imports from repo/user Python | SHA256 staged files | `%LOCALAPPDATA%\Rook\app\mcp_server` | package version, entrypoint, staged file hashes, expected command/cwd/env |
| Knowledge stores, skills, agents, docs | `knowledge`, `.claude/skills`, `.agents/skills`, `.claude/agents`, selected docs | Stage read-only app payload; copy selected user-facing assets to checked user tool locations | Schema/parse checks for knowledge stores; verify required skill/agent files exist; no contributor-only files in release docs | SHA256 staged files | App payload plus selected user destinations | artifact type, source path, destination path, file hashes, schema/version |
| FFmpeg executable, license, provenance, source bundle manifest | Rook FFmpeg build recipe and provenance scripts | Build/stage LGPL-only `ffmpeg.exe`, license notices, provenance, and source bundle manifest | Existing FFmpeg validation gate remains blocking: license flags, official source signature, source bundle manifest, smoke extraction tests | SHA256 files; sign only if legally/technically appropriate without obscuring provenance | Rhino plugin `ffmpeg` subdirectory | version, configure flags, source archive/hash/signature, license files, source bundle manifest hash |
| Installer executable | Inno Setup script plus staged release payload | Compile final `Rook-Setup-x.y.z.exe` after all payload gates pass | Install smoke on clean profile; verify no runtime downloads; verify Rhino registration; verify MCP config points to bundled runtime | Authenticode sign and timestamp installer; publish SHA256 | GitHub Release download | installer version, AppId, SHA256, signer, timestamp authority, payload manifest hash |
| Update metadata | Payload manifest plus GitHub Release metadata | Generate `installed-version.json`, update settings, release summary, client config state | Validate semver/channel; update checker treats GitHub as awareness only, not trust root; client config state matches generated entries | Payload manifest hash included in installer; mutable state records or references payload manifest hash; signed update manifest deferred | `%LOCALAPPDATA%\Rook\app\installed-version.json`, `%LOCALAPPDATA%\Rook\config\update-settings.json`, `%LOCALAPPDATA%\Rook\config\client-config-state.json` | installed version, channel, install time, update-check setting, skipped version, payload manifest hash, selected clients, config entry fingerprints |

### Release Manifest Contract

`rook-payload-manifest.json` is the canonical inventory for installed payload files. `rook-release-manifest.json` wraps the payload manifest with final release artifact data.

Required release-manifest fields include:

- product, version, channel, build time, git commit.
- final signed installer filename, SHA256, signature subject, timestamp metadata.
- payload manifest SHA256.
- immutable report artifacts and their hashes.
- vulnerability/license exception list.
- FFmpeg provenance/source bundle manifest hash.

The release manifest may reference large scan reports by hash rather than installing those reports locally.

### Release Evidence Files

Every release gate produces an evidence artifact. Exact tooling can evolve, but the evidence filenames are part of the release contract:

| Evidence File | Purpose |
|---|---|
| `build-identity-report.json` | Version consistency, git commit, release dirty-state declaration if applicable |
| `native-dependency-report.json` | Native dependency walk, baseline DLL classification, Rook-shipped VC/MFC runtime closure |
| `managed-dependency-report.json` | Managed companion dependency graph and Rhino 8 .NET baseline verification |
| `python-runtime-report.json` | CPython version, architecture, startup isolation, normal Rook startup proof |
| `wheelhouse-lock-report.json` | Locked wheels, hashes, no sdists/editable installs |
| `runtime-scan-report.json` | Materialized runtime vulnerability, malicious/yanked package, `.pth`, startup-hook scan |
| `license-scan-report.json` | License inventory, prohibited/unknown license findings, notices/source-offer status |
| `ffmpeg-compliance-report.json` | FFmpeg source signature, configure flags, source bundle, smoke test results |
| `payload-manifest-validation.json` | Payload manifest schema and hash validation |
| `installer-smoke-summary.md` | Fresh/upgrade/offline install smoke results |
| `rhino-smoke-summary.md` | Rhino registration/load and `rhino_ping` smoke results |
| `mcp-client-config-report.json` | Checked client config generation, backup, parse/restore checks |
| `update-check-report.json` | Update-check behavior, no telemetry, no auto-download path |

Missing required evidence, missing manifest hashes, failed smoke tests, or undocumented exceptions block publication.

## Security, Vulnerability, And License Gates

The release pipeline is fail-closed for shipped artifacts. The installer is not produced unless build, signing, scanning, manifest, and smoke gates pass.

| Gate | Release-Blocking Checks | Output |
|---|---|---|
| Source/build identity | Clean release commit or explicitly recorded dirty state; version matches installer, plugin assemblies, Python package, manifests, docs references | `build-identity-report.json` and build identity section in release manifest |
| Native build security | x64 Release build; expected Rhino plugin GUID; no missing non-baseline DLLs; VC++/MFC closure documented; app-local runtime files included if required | `native-dependency-report.json` |
| Managed build security | `net7.0` companion only; no `net48` release artifact path; runtimeconfig verified; Rhino 8-provided .NET baseline verified | `managed-dependency-report.json` |
| Python dependency lock | Exact locked versions; wheels only; hash-pinned; no sdists; no editable installs; no build isolation/network resolution in user installer | `wheelhouse-lock-report.json` |
| Final runtime scan | Scan materialized runtime, not just lockfile; detect malicious/yanked packages, known bad versions, critical CVEs, high CVEs in shipped packages reachable by normal Rook execution, suspicious `.pth`, startup hooks, unexpected scripts/native extensions | `runtime-scan-report.json` |
| Vulnerability policy | Fail on malicious/yanked/supply-chain incidents, critical CVEs unless proven false-positive/non-shipped, high CVEs in reachable shipped packages, hash mismatches, unsigned/tampered files, dependency fetched during install | Security status in release manifest |
| License policy | Fail on prohibited licenses, unknown licenses for shipped third-party components, missing license metadata, missing notices, or missing source-offer/source-bundle material where required | `license-scan-report.json` |
| Exception process | Medium/low CVEs, non-runtime tooling issues, or non-reachable high findings may be excepted with owner, expiry, exposure analysis, mitigation, approval, and upstream tracker | `security.exceptions[]` |
| FFmpeg compliance | LGPL-only FFmpeg gate: official source signature, configure allowlist, license/provenance files, source bundle manifest, smoke extraction tests | `ffmpeg-compliance-report.json` |
| Manifest integrity | Payload manifest hashes all static payload files after signing where applicable, excluding the payload manifest itself and mutable install-state/config/data/log files; mutable install-state files record or reference the payload manifest hash; release manifest includes final installer hash and payload manifest hash | `rook-payload-manifest.json`, `rook-release-manifest.json` |
| Installer smoke | Fresh-profile install proves no Python/PyPI/network dependency; MCP config points to bundled runtime; `rook doctor` runs; Rhino plugin registration verifies | `installer-smoke-summary.md` |

Security exceptions are allowed only outside fail-closed categories. Each exception must include:

- package/artifact.
- version/hash.
- CVE/advisory id.
- severity.
- why Rook is or is not exposed.
- mitigation.
- owner.
- expiry date.
- upstream tracking URL.
- approval timestamp.

Expired exceptions block release.

## Signing Requirements

Signing order:

1. Build native and managed artifacts.
2. Stage runtime closure.
3. Sign signable payload binaries where appropriate.
4. Record hashes for signed payload files after signing.
5. Generate `rook-payload-manifest.json`.
6. Compile Inno installer with the payload manifest embedded.
7. Authenticode sign and timestamp installer.
8. Hash final signed installer.
9. Generate and publish `rook-release-manifest.json`.

Requirements:

- Installer must be Authenticode signed and timestamped.
- Signable Rook-owned executables/DLLs should be signed where practical.
- Timestamp verification is release-blocking.
- Signature subject/publisher is recorded in the release manifest.
- SmartScreen reputation is not treated as guaranteed, even with EV/OV signing.
- Unsigned third-party binaries must have provenance and hashes recorded. If signing them would confuse provenance/licensing, record that explicitly.

## Migration And Update Behavior

Migration is a transaction: discover old state, preserve user-owned settings, install and validate new runtime, rewrite supported checked client configs, switch active Rhino/runtime state, then retire stale active paths. The installer never executes old runtime code.

| Phase | Behavior | Failure Handling |
|---|---|---|
| Old-state discovery | Read known prior locations: `%LOCALAPPDATA%\Rook\venv`, `%LOCALAPPDATA%\Rook\app`, old MCP config entries, old `.env` files, old chat service manifests, old plugin folder. Static file reads only. | Discovery failures become warnings unless they block preserving known user config. |
| Secret/config migration | Parse `.env`, config JSON/TOML, provider settings, update settings, skipped version, and preferences as text. Move/copy values into `%LOCALAPPDATA%\Rook\config`. Redact secrets in logs. Preserve ACLs where possible. | If config parse fails, preserve original file, warn user, and continue with default config. Never delete unreadable config. |
| Config ACL validation | Verify `%LOCALAPPDATA%\Rook\config` exists and is not broadly writable/readable beyond the current user and expected system/admin principals. | Warn if plaintext secrets exist and permissions appear broad. DPAPI/Credential Manager is deferred unless implemented separately. |
| Risk inspection | Inspect old runtime files statically: `*.dist-info/METADATA`, `RECORD`, `direct_url.json`, `.pth`, startup files, scripts. No `pip`, no imports, no Python from that environment. | If known-bad runtime is found, warn that API keys may already be compromised and should be rotated. Continue migration of settings only. |
| Rhino plugin backup | Before replacing active plugin folder, create a timestamped/manifest-named backup of prior Rook plugin files and manifest. | If backup fails, block upgrade unless no previous plugin folder exists. |
| New payload install | Install versioned app/runtime payload and stage plugin files separately. Do not switch client configs or active plugin folder yet. | If copy/verify fails, leave existing active config and plugin folder untouched. |
| New payload validation | Verify payload manifest, static file hashes, staged plugin files, bundled Python startup isolation, normal `rook doctor`, and MCP command/cwd/env shape against the staged payload. | If validation fails, keep old active config and active plugin folder untouched, and leave new payload in failed/quarantine state for logs. |
| Rhino plugin activation | After staged files verify, replace the active plugin folder, write HKCU Rhino registration to the active folder, and verify registration points to the active `RookNative.rhp` and companion `.rhp`. | If activation or registration verification fails, restore the prior plugin folder and prior registration where possible. |
| Client config rewrite | Transactionally update only checked supported clients. Backup original with timestamp/manifest name, write temp file, parse/verify temp, then replace. Rook entry points to bundled runtime only. | If rewrite fails, restore backup and report exact config path. |
| Active switch | Write `installed-version.json`, current payload pointers, client config state, and Rhino plugin activation state only after payload validation, Rhino activation, registration verification, and config rewrite succeed. | No active switch if any critical gate fails. |
| Old runtime quarantine | After successful switch, rename old Rook-managed venv/runtime to stale/quarantine location or mark for cleanup. Do not quarantine user-owned config/data/logs. | If quarantine fails due locks/permissions, leave old runtime but ensure no generated MCP config points to it. |
| Rollback | Restore prior client config and prior Rhino plugin folder where possible. Runtime rollback is best-effort beta support, not silent auto-rollback. | On rollback failure, show manual remediation and preserve all backups. |

### Config Rewrite Contract

Generated MCP entries must be idempotent and reversible.

Supported clients:

- Claude Desktop.
- Claude Code.
- Codex CLI.

Client behavior:

- Supported clients are selected by default only if detected.
- User can uncheck each supported client.
- Installer modifies only checked clients.
- Installer updates only Rook's generated server entry.
- Unrelated user MCP servers are preserved.
- Timestamped backups are created before changes.
- JSON/TOML is validated after writing.
- Forward-slash normalized paths are used where needed for Codex compatibility.

Deterministic generated environment:

- `ROOK_INSTALL_ROOT`.
- `ROOK_RUNTIME_ROOT`.
- `ROOK_CONFIG_DIR`.
- `ROOK_DATA_DIR`.
- `ROOK_MODE=release`.
- `PYTHONPATH` and `PYTHONHOME` cleared or controlled.

Existing user config wins only for user-owned preferences and secrets. User config cannot override release runtime path, `ROOK_MODE`, generated MCP command, generated environment security settings, or startup isolation.

The installer blocks if known generated Rook entries in checked supported client configs still point to system Python or old Rook venvs. Unknown/custom configs are reported by `rook doctor` but do not necessarily block install.

The installer writes `%LOCALAPPDATA%\Rook\config\client-config-state.json` after successful config rewrite. This state file is the durable record used by repair, uninstall, and `rook doctor` to identify generated Rook entries without relying on heuristics. It records:

- selected clients.
- config file paths.
- timestamped backup paths.
- generated entry marker/fingerprint.
- generated command, cwd, and environment shape.
- payload manifest hash used when the entry was generated.
- whether the entry was installed, skipped, restored, or left untouched.

Uninstall and repair remove or update only entries matching this recorded generated-entry state. Ambiguous entries that point to Rook paths but do not match the state file are warned and left alone unless explicit purge/advanced cleanup is selected.

### Update Behavior

Beta update checks are awareness-only.

- Enabled by default through a visible installer checkbox.
- Stored in `%LOCALAPPDATA%\Rook\config\update-settings.json`.
- Checks GitHub Releases at most once daily.
- Sends no telemetry, API keys, project paths, machine IDs, or installed manifest body.
- Supports opt-out and "skip this version."
- Offline/network failure is quiet and visible only in `rook doctor`.
- GitHub metadata is not a trust root.
- No auto-download, no auto-run, no self-update.
- User manually downloads the signed installer from GitHub Releases.
- A signed update manifest may be added later before GitHub metadata becomes a trust source.
- Auto-update is later still and requires a trust/update policy model.

Frequent beta updates should not force reconfiguration:

- API keys and provider settings persist across updates.
- Installer should not ask for API keys if existing config is present.
- Existing preferences/secrets win over bundled defaults.
- Payload/runtime directories are replaceable; config/data/logs are durable.
- Old payload cleanup happens only after the new payload validates.

If migration detects prior active use of a known-compromised runtime/package:

- Do not execute it.
- Preserve/migrate settings.
- Warn that credentials may have been exposed before this installer ran.
- Recommend rotating affected API keys.
- Record a redacted warning in install logs and `rook doctor`.

## Installer UX And Operational Behavior

The installer should feel like a normal beta product installer, not a developer bootstrap script.

| UX Area | Behavior |
|---|---|
| Default install mode | Full beta install: Rhino plugins, bundled runtime, MCP server, knowledge stores, skills/agents, docs, update checker setting |
| Custom/plugin-only mode | Available for support/debug; UI warns that disabling runtime/MCP may leave Rook incomplete |
| Admin posture | No admin required; runs per-user with `PrivilegesRequired=lowest`; if elevated as a different user, warn that Rhino will not see per-user registration for the intended user |
| Running host block | Abort install/upgrade if Rhino, Rhino.Inside.Revit, or Revit is running; explain plugin registration/loading state and DLL lock risk |
| Python prerequisite | No Python prerequisite page; no user/system Python discovery for release install |
| API key handling | Preserve existing config; missing keys do not fail install; optional configure-now writes only to durable config with redaction and permission checks |
| Update checks | Visible checkbox: "Check GitHub Releases for Rook updates", checked by default; explain no telemetry and no auto-install |
| Install progress | Show product-level steps: copy plugins, install runtime, migrate settings, configure checked MCP clients, verify install |
| Completion page | Show next steps: restart Rhino/Revit/Rhino.Inside host, restart selected MCP clients, run `rook doctor` or `rhino_ping`; mention logs path and unconfigured providers |
| Failure messages | Include what failed, whether prior install was preserved/restored, log path, and concrete remediation |
| Logs | Write install logs under `%LOCALAPPDATA%\Rook\logs\install\<timestamp>\`; redact secrets; include manifest validation summaries |
| Uninstall | Remove app/runtime/plugin files and Rook MCP entries that match `client-config-state.json`; preserve config/secrets/data/logs by default |
| Repair/reinstall | Idempotent: preserve settings, refresh payload/runtime, rewrite checked generated MCP entries, reverify |
| Upgrade | Backup old plugin/app/runtime state, install staged payload, validate, switch active state, quarantine stale runtime/plugin backup |
| Rollback on critical failure | Restore prior Rhino plugin folder and supported checked client configs where possible; preserve backups on failure |
| Security warning | If compromised old runtime evidence is found, warn that keys may need rotation; do not block settings migration solely because compromise is suspected |
| Offline behavior | Installer works offline after download; update check is skipped/fails quietly if offline |

API-key entry is optional and secondary. The installer is not the primary secrets UI unless the configure-now path writes to the durable config location with redaction and permissions checks. If providers are unconfigured, the completion page and `rook doctor` tell the user what is missing.

Restart guidance means restart Rhino/Revit/Rhino.Inside host and MCP clients, not Windows. A Windows reboot is requested only for a concrete locked-file condition, and that condition is exceptional and logged.

Uninstall removes only Rook entries that match `client-config-state.json`. Unknown/custom entries pointing to Rook paths are warned and left alone unless explicit purge/advanced cleanup is chosen.

### Failure Message Shape

Blocking failures should use this structure:

```text
Rook could not complete the upgrade.

Failed step:
  Rhino plugin registration verification

What happened:
  Rook copied the new plug-in files, but Rhino registration did not point to the staged RookNative.rhp.

Recovery:
  Your previous Rook plug-in folder was restored.
  Close Rhino/Revit and run the installer again as the same Windows user who runs Rhino.

Log:
  %LOCALAPPDATA%\Rook\logs\install\2026-05-21T...\
```

## Testing And Release Process

The release process is a gated pipeline. The installer is produced only after build, packaging, security, install, and doctor checks pass.

| Layer | Required Gates |
|---|---|
| Source/version gates | Version consistency across installer, native plugin, managed companion, Python package, manifests, docs references; release commit recorded |
| Unit tests | Existing C#/Python/native-adjacent guard tests relevant to installer, runtime selection, config generation, plugin lifecycle, and release guard scripts |
| Installer guard tests | Static tests for Inno script: no `net48` release path, no Python prerequisite, no `pip install`/PyPI install path, plugin host process block, registry verification, manifest inclusion, bundled runtime inclusion, FFmpeg inclusion |
| Runtime closure tests | Native dependency walk against explicit Windows/Rhino baseline; managed dependency check against Rhino 8 .NET baseline; CPython startup isolation; normal `rook doctor` using bundled runtime |
| Security tests | Lockfile/wheel hash verification, no sdists, no editable installs, vulnerability scan, license scan, `.pth`/startup hook scan, materialized runtime scan, forbidden package/version denylist |
| Migration tests | Synthetic old installs: system-Python MCP config, old Rook venv, old `.env`, existing API key, malformed config, ambiguous custom entry, suspicious `.pth`, known-bad package metadata; prove no old Python execution |
| Installer smoke tests | Fresh Windows user/profile-style install; upgrade over prior beta; repair/reinstall; uninstall preserve mode; uninstall purge/advanced mode if shipped |
| Rhino smoke tests | Rhino 8 closed during install; install verifies HKCU registration; launch Rhino and `rhino_ping`; Rhino.Inside/Revit host closed block; companion load does not require manual PluginManager registration |
| MCP client config tests | Checked clients only; unchecked clients untouched; unrelated MCP entries preserved; generated Rook entries point to bundled runtime; timestamped backups; invalid config restore path works |
| Update checker tests | Default-on setting visible; opt-out persists; GitHub unavailable/offline is non-fatal; no telemetry fields sent; no auto-download/auto-run path exists |
| Artifact publication tests | Payload manifest installed; release manifest published; report hashes match; signed installer hash matches release manifest; immutable scan reports uploaded with hashes |

### Clean-Machine Smoke Matrix

Minimum smoke coverage before a beta release:

- No Python installed or Python absent from PATH.
- Python installed but ignored by release installer.
- Existing prior Rook venv/config migration.
- Rhino installed, Rhino closed.
- Rhino/Revit running, installer blocks.
- Claude/Codex absent: installer succeeds without modifying those configs.
- Claude/Codex present but unchecked: untouched.
- Claude/Codex checked: config generated and validated.
- Network disabled: installer succeeds and does not attempt PyPI/package/runtime downloads.
- Offline install after downloading installer.
- Upgrade with existing API key preserved.

### Release Artifact Publication

GitHub Release includes:

- signed `Rook-Setup-x.y.z.exe`.
- `Rook-Setup-x.y.z.exe.sha256`.
- `rook-release-manifest.json`.
- `rook-payload-manifest.json`.
- SBOM.
- `build-identity-report.json`.
- `native-dependency-report.json`.
- `managed-dependency-report.json`.
- `python-runtime-report.json`.
- `wheelhouse-lock-report.json`.
- `runtime-scan-report.json`.
- `license-scan-report.json`.
- `ffmpeg-compliance-report.json`.
- `payload-manifest-validation.json`.
- `installer-smoke-summary.md`.
- `rhino-smoke-summary.md`.
- `mcp-client-config-report.json`.
- `update-check-report.json`.
- FFmpeg source bundle manifest and compliance payload.

The release manifest records hashes for all published reports. Reports do not need to be installed locally unless needed for `rook doctor`.

Any missing required report, missing manifest hash, failed smoke, or undocumented exception blocks publication.

## Local `rook doctor` Requirements

`rook doctor` should report:

- installed version/channel.
- payload manifest presence and schema validity.
- missing/tampered critical files.
- client config state presence and schema validity.
- MCP config command/cwd/env target.
- whether checked supported client configs point to bundled runtime.
- old Rook venvs or system-Python Rook entries still active.
- plugin folder manifest/hash status.
- Rhino registration status.
- signature status for installer/payload where locally inspectable.
- vulnerability/license exception summary for the installed build.
- update-check status and latest known version, if checked.
- unconfigured providers and remediation.

## Future Enterprise Path Constraints

The beta installer must avoid blocking a later enterprise installer:

- Keep app/runtime/config/data/log roots abstracted.
- Keep per-user assumptions localized to installer configuration.
- Do not write mutable user state into app/runtime directories.
- Keep generated client config idempotent and reversible.
- Keep plugin registration code factored so HKCU and later HKLM/per-machine registration can share validation logic.
- Preserve stable product identity/AppId and plugin GUIDs.
- Keep update-check behavior policy-controlled in design, even if policy controls are later.
- Document install roots and allowlisting targets.
- Avoid relying on user profile paths inside runtime code except through explicit env/config values.

Deferred until Approach B:

- MSI/WiX or commercial MSI authoring.
- Per-machine `Program Files` install root.
- HKLM Rhino plugin registration.
- Managed admin policy controls.
- Enterprise proxy/update channel.
- Silent install/uninstall contract.
- SCCM/GPO/Intune deployment docs.
- Signed update manifest, before GitHub metadata becomes a trust source.
- Auto-update, later still and only after trust/update policy exists.
- DPAPI/Credential Manager secrets storage if not done during beta.
- McNeel Zoo licensing integration.

## Implementation Plan Shape

The implementation plan should split into these milestones:

1. Payload/runtime manifest and release artifact model.
2. Bundled Python runtime and sealed wheelhouse/runtime.
3. Runtime, security, and license gates.
4. Installer migration, transaction, and rollback behavior.
5. UX and config generation changes.
6. `rook doctor` verification.
7. Release publication flow and smoke matrix.
8. Enterprise path documentation constraints.

Each milestone should produce tests and evidence artifacts before proceeding to the next layer.
