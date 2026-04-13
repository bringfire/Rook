# Version Locations

Every release requires updating these 6 files. The OLD version must be replaced
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

## 4. src/RookNative/RookNative.rc (4 edits in one file)

Binary version numbers use commas. For version A.B.C:

```
FILEVERSION A,B,C,0       (line ~17)
PRODUCTVERSION A,B,C,0    (line ~18)
VALUE "FileVersion", "A.B.C.0"      (line ~35)
VALUE "ProductVersion", "A.B.C.0"   (line ~40)
```

## 5. src/RookNative/RookNativePlugin.cpp (line ~252)

```
: m_plugin_version(L"OLD")  -->  : m_plugin_version(L"NEW")
```

## 6. src/RookNative/RookServer.cpp (line ~1438)

```
info["pluginVersion"] = "OLD";  -->  info["pluginVersion"] = "NEW";
```

## Verification

After all edits, run:

```bash
grep -rn "NEW_VERSION" --include="*.toml" --include="*.iss" --include="*.csproj" --include="*.rc" --include="*.cpp" installer/ mcp_server/pyproject.toml src/
```

Expected: 6 string matches (`pyproject.toml`, `RookSetup.iss`, `Rook.csproj`,
the two string-value lines in `RookNative.rc`, `RookNativePlugin.cpp`,
`RookServer.cpp`). The binary `FILEVERSION` / `PRODUCTVERSION` lines in the
`.rc` file must be checked separately because they use comma-delimited values.

More reliable: grep for the old version — should return 0 matches:

```bash
grep -rn "OLD_VERSION" --include="*.toml" --include="*.iss" --include="*.csproj" --include="*.rc" --include="*.cpp" installer/ mcp_server/pyproject.toml src/
```

This must return nothing. If it does, you missed a location.
