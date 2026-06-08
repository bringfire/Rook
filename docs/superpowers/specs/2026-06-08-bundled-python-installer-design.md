# Bundled Python Installer Design

Date: 2026-06-08

## Purpose

The public Rook installer must install MCP, chat, Chirp, and Python-backed
features without relying on user-installed Python, live PyPI downloads, resolver
drift, PATH state, or relocatable prebuilt virtual environments.

The release-grade direction is a sealed installer payload:

- a private CPython runtime staged during release build,
- two virtual environments created at install time,
- one offline wheelhouse,
- two fully pinned hash-locked requirements files,
- deterministic validation and manifest evidence.

Public/full MCP and Chirp installation must never discover PATH Python. Dev,
source, and explicit support workflows may keep their user-Python flexibility.

## Sources And Constraints

- Python's Windows NuGet package is a reduced-size Python environment with a
  `tools\python.exe` layout and supports exact `-Version 3.x.y` staging during
  release build.
- Python's Windows embeddable package is not the default for Rook because normal
  pip dependency management is not supported for that distribution.
- Pip supports offline local wheel installs via `--no-index --find-links`.
- Pip hash-checking mode requires a fully pinned and hashed dependency graph.
- `pip-audit` reports known Python package vulnerabilities; it is not proof that
  no vulnerabilities exist.

## Architecture

The public/full Rook installer will ship a complete private Python runtime and
offline dependency payload. The release build, not the user's machine, stages the
official Python NuGet `python` package at one exact version, verifies the
`.nupkg` SHA256, extracts its `tools\` runtime, and packages that extracted
runtime into the installer.

Installed layout:

```text
%LOCALAPPDATA%\Rook\
  python\
    cpython-3.11.9\
      python.exe
      Lib\
      DLLs\
      Scripts\
      runtime support files
  venv\                         # Rook MCP + chat service
  data\
    install-state.json           # install-time state for venv/config validation
  app\
    mcp_server\
    chirp\
      .venv\                    # Chirp service, preserving CHIRP_HOME contract
    python-wheelhouse\
    requirements-rook-lock.txt
    requirements-chirp-lock.txt
    python-runtime-manifest.json # release/runtime/wheelhouse/audit manifest
```

Release packaging builds wheels for `rook-mcp` and `chirp`; public install does
not use `pip install -e`. Both venvs install from one union wheelhouse, but each
uses its own fully pinned, hash-locked requirements file.

Venv invalidation is deterministic:

- The Rook venv is invalidated by changes to the Python runtime identity or
  `requirements-rook-lock.txt`.
- The Chirp venv is invalidated by changes to the Python runtime identity or
  `requirements-chirp-lock.txt`.
- Recreate means deleting the old venv and installing from the bundled
  wheelhouse again; no patch-in-place upgrade.

Generated Claude/Codex MCP configs and `RookChatService.json` point to
`%LOCALAPPDATA%\Rook\venv\Scripts\python.exe`. `CHIRP_HOME` points to
`%LOCALAPPDATA%\Rook\app\chirp`, preserving the current Chirp service contract.

OCR/Tesseract is explicitly out of scope for this release. `pytesseract` should
move out of default dependencies into an optional extra or be excluded from the
public lock unless a real OCR packaging plan exists. Release guards should fail
if hard OCR imports appear without that plan.

## Build And Packaging Pipeline

Release build adds a Python packaging stage after checkout of the exact release
SHA and before `.iss` source verification and ISCC compilation. This stage is
release-only; dev/source workflows can keep their current user-Python
flexibility. The staged Python payload, wheelhouse, lockfiles, and manifest must
be newer than `$buildStartedAt`, like native and managed outputs.

The packaging stage reads pinned runtime metadata from a repo-owned file:

```text
installer/python-runtime/python-runtime.json
```

Example fields:

```json
{
  "schema_version": 1,
  "python_nuget_package": "python",
  "python_version": "3.11.9",
  "nupkg_sha256": "64-character uppercase SHA256 hex digest",
  "target_platform": "win_amd64",
  "python_abi": "cp311"
}
```

The 1.5.10 release design targets Python NuGet `python` version `3.11.9`
unless compatibility testing explicitly qualifies a different exact version
before implementation. The version is never floating.

The stage then:

1. Downloads the official NuGet package during release build only.
2. Verifies the `.nupkg` SHA256.
3. Extracts `tools\` into `installer/runtime/python/cpython-3.11.9/`.
4. Builds non-editable wheels for `rook-mcp==1.5.10` and `chirp==0.1.0`
   for the current release line. Because Chirp is a sibling repository, the
   release build must record the Chirp repo git SHA, verify the Chirp worktree
   is clean, and record a Chirp source archive hash or equivalent vendored
   source manifest before building the Chirp wheel.
5. Generates `requirements-rook-lock.txt` and `requirements-chirp-lock.txt`.
6. Builds one union wheelhouse containing every wheel needed by either lockfile.
7. Fails if any source distribution is present in the final public installer
   wheelhouse. If an upstream package is available only as an sdist, the release
   build must build and audit a compatible wheel during staging, then package
   only that built wheel.

Vulnerability, provenance, and integrity checks:

- temp-install both lockfiles from the local wheelhouse using
  `--isolated --no-index --find-links --require-hashes`;
- verify every package installed from the public wheelhouse is a wheel
  compatible with the pinned interpreter's accepted tag set, including valid
  pure-Python and ABI-stable wheels such as `py3-none-any` and `abi3`;
- run `pip check` after each temp install;
- run `pip-audit` against the installed temp venvs so it audits the exact
  wheelhouse result;
- verify every wheel hash;
- collect package license/provenance metadata for Python and third-party wheels;
- smoke import Rook dependencies and Chirp dependencies;
- smoke import shipped vision modules: `cv2`, `PIL`, `numpy`, `skimage`;
- guard against hard `pytesseract` imports unless OCR packaging is added.

Release validation must prove `import rook` and `import chirp` resolve from
their respective venv `site-packages`, not from source trees. `{app}\mcp_server`
and `{app}\chirp` may remain working directories/config roots, but release config
must not add `{app}\mcp_server\src` or `{app}\chirp\src` to `PYTHONPATH`.

The packaging stage writes:

```text
installer/runtime/python-runtime-manifest.json
```

or the equivalent staged path that Inno packages into
`%LOCALAPPDATA%\Rook\app\python-runtime-manifest.json`.

Manifest requirements:

- `schema_version: 1`;
- CPython NuGet package/version/hash;
- target interpreter/platform identity and accepted wheel tag set;
- each wheel's actual compatibility tags;
- extracted runtime hash or file manifest;
- Rook source git SHA and clean-state evidence;
- Chirp sibling repository git SHA, clean-state evidence, and source archive hash
  or equivalent vendored source manifest;
- lockfile hashes;
- wheel hashes and tags;
- license/provenance summary;
- `pip check` results;
- audit result summary;
- temp install verification summary;
- import `__file__` paths;
- generated UTC timestamp;
- release version, Rook git SHA, and Chirp source identity.

The release workflow documentation and guard tests must stay synchronized in
both `.agents` and `.claude`, including:

- build-release skill pipeline;
- `.iss` source path checklist;
- release artifact validator;
- `scripts/tests/release-installer-guards.tests.ps1`.

The public installer packages the staged artifacts. It does not run NuGet,
download wheels, or resolve dependencies on the user machine.

## Installer And Post-Install Behavior

The public/full installer removes the user-Python prerequisite for MCP/Chirp.
Component labels and prerequisite checks no longer say Python 3.10+ is required
from the user. Python discovery remains allowed only in dev/source/support flows,
not in the public/full MCP/Chirp install path.

Inno packages:

- private CPython runtime under `{localappdata}\Rook\python\cpython-3.11.9`;
- union wheelhouse under `{app}\python-wheelhouse`;
- `requirements-rook-lock.txt`;
- `requirements-chirp-lock.txt`;
- `python-runtime-manifest.json`;
- `post_install.py`.

Post-install uses only the private runtime:

```powershell
%LOCALAPPDATA%\Rook\python\cpython-3.11.9\python.exe -m venv %LOCALAPPDATA%\Rook\venv
%LOCALAPPDATA%\Rook\venv\Scripts\python.exe -m pip --isolated install `
  --no-index `
  --find-links %LOCALAPPDATA%\Rook\app\python-wheelhouse `
  --require-hashes `
  -r %LOCALAPPDATA%\Rook\app\requirements-rook-lock.txt
```

For Chirp:

```powershell
%LOCALAPPDATA%\Rook\python\cpython-3.11.9\python.exe -m venv %LOCALAPPDATA%\Rook\app\chirp\.venv
%LOCALAPPDATA%\Rook\app\chirp\.venv\Scripts\python.exe -m pip --isolated install `
  --no-index `
  --find-links %LOCALAPPDATA%\Rook\app\python-wheelhouse `
  --require-hashes `
  -r %LOCALAPPDATA%\Rook\app\requirements-chirp-lock.txt
```

Private Python and pip subprocesses run with a sanitized environment:

- `PYTHONHOME` cleared;
- `PYTHONPATH` cleared;
- `PIP_NO_INDEX=1`;
- `PIP_DISABLE_PIP_VERSION_CHECK=1`;
- `PIP_REQUIRE_VIRTUALENV=1` for install subprocesses.

`install-state.json` is written to:

```text
%LOCALAPPDATA%\Rook\data\install-state.json
```

Install-state requirements:

- `schema_version: 1`;
- private Python path/version/hash identity;
- Rook lockfile hash and installed venv path;
- Chirp lockfile hash and installed venv path;
- wheelhouse manifest hash;
- installed package import origins;
- exact pip command arguments;
- pip output evidence;
- `pip check` results after each real install;
- config paths written;
- validation results and timestamp.

Post-install mechanically validates that no network dependency install occurred:

- recorded pip install commands must include `--no-index`;
- recorded pip install commands must not include `--index-url` or
  `--extra-index-url`;
- pip output evidence should show local links behavior, for example
  `Looking in links:`, not `Looking in indexes:`.

Generated configs:

- Claude/Codex MCP entries use `%LOCALAPPDATA%\Rook\venv\Scripts\python.exe`;
- MCP env clears `PYTHONHOME` and `PYTHONPATH`;
- MCP cwd may remain `%LOCALAPPDATA%\Rook\app\mcp_server`;
- source paths are not added to `PYTHONPATH`;
- `RookChatService.json` uses the Rook venv Python and no
  `{app}\mcp_server\src` `pythonPathEntries` in release mode;
- `CHIRP_HOME` points to `%LOCALAPPDATA%\Rook\app\chirp`.

Post-install validation must prove:

- Rook venv Python exists and imports `rook` from venv `site-packages`;
- chat service health runs from Rook venv;
- Chirp venv Python exists and imports `chirp` from `.venv\Lib\site-packages`;
- `cv2`, `PIL`, `numpy`, and `skimage` import from the Rook venv;
- Claude/Codex/chat configs point at the installed private Rook venv;
- `CHIRP_HOME` points at installed Chirp root;
- no network dependency install occurred.

## Security, Validation, And Release Gates

Security posture is based on a sealed release payload, not trust in the user's
machine.

Build-time gates:

- exact Python NuGet version and `.nupkg` SHA256 must match
  `installer/python-runtime/python-runtime.json`;
- extracted runtime must pass `python.exe -V`, `python.exe -m venv`, and temp
  venv `python -m pip --version`;
- all dependencies must be wheels compatible with the pinned interpreter's
  accepted tag set; each wheel's actual tags must be recorded;
- source distributions must never be packaged as public installer inputs; if an
  sdist is unavoidable upstream, the release build must produce and audit a
  compatible wheel and package only that wheel;
- `rook-mcp` wheels must be built from the exact Rook release SHA/source state;
- `chirp` wheels must be built from a recorded clean Chirp sibling repo SHA and
  source archive hash or equivalent vendored source manifest;
- both lockfiles must be fully pinned and hash-locked;
- temp venv installs must use only
  `--isolated --no-index --find-links --require-hashes`;
- `pip check` runs after each temp install;
- `pip-audit` runs against the temp installed venvs;
- manifest records wheel hashes, wheel tags, Rook source identity, Chirp source
  identity, licenses/provenance, audit summary, `pip check`, and import-origin
  proof;
- release guard fails on hard `pytesseract` imports unless Tesseract packaging
  is added.

Install-time gates:

- private Python is used for venv creation;
- package install subprocesses run with sanitized env;
- pip commands and output evidence are recorded into `install-state.json`;
- post-install rejects dependency install commands that omit `--no-index` or
  include `--index-url` / `--extra-index-url`;
- post-install records local-wheelhouse evidence.

Release smoke gates:

- clean-machine install with no user Python required;
- at least one smoke should run with network blocked or disabled when feasible;
- Rook MCP imports from `%LOCALAPPDATA%\Rook\venv\Lib\site-packages`;
- Chirp imports from `%LOCALAPPDATA%\Rook\app\chirp\.venv\Lib\site-packages`;
- smoke manifest records private Python path/version;
- smoke manifest records `rook.__file__` and `chirp.__file__`;
- smoke manifest records `pip check` results;
- Claude config, Codex config, and `RookChatService.json` point to private Rook
  venv Python;
- `CHIRP_HOME` points to `%LOCALAPPDATA%\Rook\app\chirp`;
- chat service health passes from the private Rook venv;
- `rhino_ping` passes;
- Chirp live smoke passes, including `chirp_create`;
- standalone Rhino smoke passes;
- Rhino.Inside.Revit smoke passes;
- release artifact validator requires Python runtime manifest and install-state
  evidence in the smoke manifest.

Failure handling:

- if private runtime is missing or hash identity mismatches, fail with a clear
  reinstall message;
- if wheelhouse or lockfile is missing/stale, fail closed;
- if install from local wheelhouse fails, print the exact offline repair command;
- if generated configs point to a stale/source/user Python path, validation
  fails.

## Implementation Units

### 1. Python Runtime Stager

Input: `installer/python-runtime/python-runtime.json`

Output: staged CPython runtime under
`installer/runtime/python/cpython-3.11.9`.

Responsibilities:

- verify NuGet package SHA256;
- extract `tools\`;
- verify `python.exe -V`;
- verify `python.exe -m venv`;
- verify temp venv `python -m pip --version`;
- write runtime identity data for the manifest.

### 2. Wheelhouse Builder

Responsibilities:

- build non-editable `rook-mcp` and `chirp` wheels;
- generate or consume fully pinned hash lockfiles;
- produce one union wheelhouse;
- reject source distributions in the final public installer wheelhouse;
- run temp offline installs;
- run `pip check`;
- run `pip-audit`;
- run import smoke;
- prove import origins resolve to `site-packages`;
- smoke import `cv2`, `PIL`, `numpy`, `skimage`.

### 3. Python Runtime Manifest Writer

Responsibilities:

- write `python-runtime-manifest.json`;
- include `schema_version: 1`;
- include CPython NuGet identity;
- include Rook source git SHA and clean-state evidence;
- include Chirp sibling repo git SHA, clean-state evidence, and source archive
  hash or equivalent vendored source manifest;
- include lockfile hashes;
- include wheel hashes/tags;
- include license/provenance summary;
- include audit summary;
- include `pip check` results;
- include temp install results;
- include import `__file__` paths;
- include release version and Rook git SHA.

### 4. Installer Source Integration

Responsibilities:

- package staged runtime, wheelhouse, lockfiles, and manifest;
- remove public user-Python prerequisite;
- keep dev/source helpers flexible;
- update `.iss` source checklist;
- update `.agents` and `.claude` build-release docs;
- update installer guard tests.

### 5. Post-Install Runtime Manager

Responsibilities:

- create/recreate Rook and Chirp venvs from private CPython;
- install from wheelhouse only with sanitized env and hash mode;
- write `%LOCALAPPDATA%\Rook\data\install-state.json`;
- include `schema_version: 1`;
- record pip command args and pip output evidence;
- run and record `pip check`;
- record import-origin proof;
- record private Python path/version;
- record config identity.

### 6. Config Writers

Responsibilities:

- write Claude/Codex MCP entries using private Rook venv Python;
- write chat service manifest using private Rook venv Python;
- avoid release-mode source-tree `PYTHONPATH` entries;
- set `CHIRP_HOME` to installed Chirp root.

### 7. Release Validation

Responsibilities:

- require Python runtime manifest evidence;
- require install-state evidence;
- require smoke manifest private Python path/version;
- require Rook and Chirp venv paths;
- require `rook.__file__` and `chirp.__file__`;
- require `pip check` results;
- require config identity paths;
- require no-index/local-wheelhouse evidence;
- require Chirp source identity evidence in `python-runtime-manifest.json`;
- keep standalone Rhino and Rhino.Inside.Revit gates mandatory.

## Test Surface

Python unit tests:

- post-install venv invalidation;
- offline pip command construction;
- sanitized env construction;
- config path generation;
- import-origin validation;
- install-state writing;
- pip output evidence parsing;
- rejection of network/index pip flags.

PowerShell guard tests:

- `.iss` packages staged runtime, wheelhouse, lockfiles, and manifest;
- public/full MCP/Chirp no longer has user-Python prerequisite;
- public installer contains no `pip install -e`;
- wheelhouse/lockfile manifest requirements are present;
- docs stay synchronized in `.agents` and `.claude`;
- source-import paths are prohibited in release config;
- hard `pytesseract` imports fail without OCR packaging plan.

Release-build script tests:

- NuGet hash verification;
- wheel-only enforcement;
- rejection of source distributions in the final public installer wheelhouse;
- lockfile hash mode;
- manifest schema;
- Chirp sibling repo source identity and clean-state validation;
- staged payload freshness relative to `$buildStartedAt`;
- import-origin proof from temp venvs.

Negative contamination test:

- set fake user `PYTHONPATH`;
- set fake pip config/index environment variables;
- put a user Python on PATH;
- run public/full post-install path;
- prove only the private runtime and bundled wheelhouse are used.

End-to-end checks:

- ISCC installer compile;
- clean-machine install with no user Python;
- clean-machine install with network disabled or blocked when feasible;
- standalone Rhino smoke;
- Rhino.Inside.Revit smoke;
- Chirp live smoke including `chirp_create`.

## Out Of Scope

- Bundling Tesseract OCR or traineddata.
- Consolidating Chirp into the Rook MCP/chat venv.
- Prebuilding and relocating venvs.
- Using user-installed Python in the public/full MCP/Chirp install path.
- Running NuGet, PyPI, or dependency resolution on the user's machine.
