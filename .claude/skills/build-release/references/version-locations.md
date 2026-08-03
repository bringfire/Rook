# Version Locations

Every release requires 14 edits across these 10 files. Replace the old version with
the new semantic version (`X.Y.Z`) in every location.

## 1. `mcp_server/pyproject.toml` — 1 edit

```toml
version = "OLD"  # -> "NEW"
```

## 2. `mcp_server/uv.lock` — 1 local-project edit

Do not edit the lock manually. After changing `pyproject.toml`, run `uv lock` and
require the resulting diff to change only the local `rook-mcp` project version. Stop
if a third-party package, version, source, or hash changes.

## 3. `installer/RookSetup.iss` — 1 edit

```text
#define MyAppVersion "OLD"  ->  #define MyAppVersion "NEW"
```

## 4. `src/Rook/Rook.csproj` — 1 edit

```xml
<Version>OLD</Version>  <!-- -> NEW -->
```

## 5. `src/RookBim/RookBim.csproj` — 1 edit

```xml
<Version>OLD</Version>  <!-- -> NEW -->
```

## 6. `src/RookNative/RookNative.rc` — 4 edits

For version `A.B.C`:

```text
FILEVERSION A,B,C,0
PRODUCTVERSION A,B,C,0
VALUE "FileVersion", "A.B.C.0"
VALUE "ProductVersion", "A.B.C.0"
```

## 7. `src/RookNative/RookNativePlugin.cpp` — 1 edit

```cpp
: m_plugin_version(L"OLD")  // -> NEW
```

## 8. `src/RookNative/RookServer.cpp` — 1 edit

```cpp
kRookNativePluginVersion = "OLD";  // -> NEW
```

## 9. `.claude-plugin/plugin.json` — 1 edit

```json
"version": "NEW"
```

## 10. `.claude-plugin/marketplace.json` — 2 edits

Update both `metadata.version` and `plugins[0].version` to `NEW`.

## Verification

Run `uv lock` after the source version change, inspect its bounded diff, and then run:

```powershell
$newVersion = 'NEW_VERSION'
$versionPaths = @(
  'mcp_server/pyproject.toml',
  'mcp_server/uv.lock',
  'installer/RookSetup.iss',
  'src/Rook/Rook.csproj',
  'src/RookBim/RookBim.csproj',
  'src/RookNative/RookNative.rc',
  'src/RookNative/RookNativePlugin.cpp',
  'src/RookNative/RookServer.cpp',
  '.claude-plugin/plugin.json',
  '.claude-plugin/marketplace.json'
)

Select-String -Path $versionPaths -Pattern ([regex]::Escape($newVersion))
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Metadata
claude plugin validate --strict .
```

Expect 12 dotted-version matches: one in each ordinary version surface, two resource
string values, and two marketplace values. Verify the two comma-delimited resource
version lines separately. Finally scan these same ten files for the old version; it
must not remain.
