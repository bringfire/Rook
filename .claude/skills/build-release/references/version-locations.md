# Version Locations

Every release requires updating these 7 files. The OLD version must be replaced
with the NEW version in each location. Use the Edit tool for each.

## 1. mcp_server/pyproject.toml (line ~3)

```
version = "OLD"  -->  version = "NEW"
```

## 2. installer/RookSetup.iss (line ~15)

```
#define MyAppVersion "OLD"  -->  #define MyAppVersion "NEW"
```

## 3. src/Rook/Rook.csproj (line ~13)

```
<Version>OLD</Version>  -->  <Version>NEW</Version>
```

## 4. src/RookBim/RookBim.csproj (line ~10)

```
<Version>OLD</Version>  -->  <Version>NEW</Version>
```

## 5. src/RookNative/RookNative.rc (4 edits in one file)

Binary version numbers use commas. For version A.B.C:

```
FILEVERSION A,B,C,0       (line ~17)
PRODUCTVERSION A,B,C,0    (line ~18)
VALUE "FileVersion", "A.B.C.0"      (line ~35)
VALUE "ProductVersion", "A.B.C.0"   (line ~40)
```

## 6. src/RookNative/RookNativePlugin.cpp (line ~252)

```
: m_plugin_version(L"OLD")  -->  : m_plugin_version(L"NEW")
```

## 7. src/RookNative/RookServer.cpp (line ~1438)

```
info["pluginVersion"] = "OLD";  -->  info["pluginVersion"] = "NEW";
```

## Verification

After all edits, run:

```powershell
$newVersion = "NEW_VERSION"
Select-String -Path `
  mcp_server\pyproject.toml, `
  installer\RookSetup.iss, `
  src\Rook\Rook.csproj, `
  src\RookBim\RookBim.csproj, `
  src\RookNative\RookNative.rc, `
  src\RookNative\RookNativePlugin.cpp, `
  src\RookNative\RookServer.cpp `
  -Pattern ([regex]::Escape($newVersion))
```

Expected: 8 string matches (`pyproject.toml`, `RookSetup.iss`, `Rook.csproj`,
`RookBim.csproj`, the two string-value lines in `RookNative.rc`,
`RookNativePlugin.cpp`, `RookServer.cpp`). The binary `FILEVERSION` /
`PRODUCTVERSION` lines in the
`.rc` file must be checked separately because they use comma-delimited values.

More reliable: scan for the old version — should return 0 matches:

```powershell
$oldVersion = "OLD_VERSION"
Select-String -Path `
  mcp_server\pyproject.toml, `
  installer\RookSetup.iss, `
  src\Rook\Rook.csproj, `
  src\RookBim\RookBim.csproj, `
  src\RookNative\RookNative.rc, `
  src\RookNative\RookNativePlugin.cpp, `
  src\RookNative\RookServer.cpp `
  -Pattern ([regex]::Escape($oldVersion))
```

This must return nothing. If it does, you missed a location.
