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

## 3. installer/post_install.py (line ~342)

```
version = "OLD"  -->  version = "NEW"
```

## 4. src/Rook/Rook.csproj (line ~13)

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

## 6. src/RookNative/RookNativePlugin.cpp (line ~236)

```
: m_plugin_version(L"OLD")  -->  : m_plugin_version(L"NEW")
```

## 7. src/RookNative/RookServer.cpp (line ~1384)

```
info["pluginVersion"] = "OLD";  -->  info["pluginVersion"] = "NEW";
```

## Verification

After all edits, run:

```bash
grep -rn "NEW_VERSION" --include="*.toml" --include="*.iss" --include="*.csproj" --include="*.rc" --include="*.cpp" --include="*.py" installer/ mcp_server/pyproject.toml src/
```

Expected: 8 matches (pyproject.toml:1, RookSetup.iss:1, post_install.py:1,
Rook.csproj:1, RookNative.rc:4 — but grep finds the string in the FileVersion
and ProductVersion lines which is 2, plus the binary versions won't match the
string pattern, so actually expect ~6-8 depending on format).

More reliable: grep for the old version — should return 0 matches:

```bash
grep -rn "OLD_VERSION" --include="*.toml" --include="*.iss" --include="*.csproj" --include="*.rc" --include="*.cpp" --include="*.py" installer/ mcp_server/pyproject.toml src/
```

This must return nothing. If it does, you missed a location.
